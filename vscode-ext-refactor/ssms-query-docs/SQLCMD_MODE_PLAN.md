# SQLCMD Mode + Scan-and-Detect Framework — Design & Execution Plan

Status: ACTIVE (2026-07-11). Journal entries land in PROGRESS.md (journal wins
over this plan on conflict).

## 0. The ask (Karl, 2026-07-11)

1. SQLCMD mode in Query Studio, like the old editor / SSMS: figure out how
   v1/STS does it, add it to the new editor.
2. Toolbar toggle button, SQLCMD on/off, like SSMS.
3. Status bar shows "SQLCMD" when on, NOTHING when off.
4. On file open, scan ~first 50 lines for SQLCMD commands; if found, prompt
   "This file has sqlcmd commands. Do you want to enable sqlcmd mode?" with
   exactly three options: Enable / Don't Enable / "Don't show again,
   auto-enable".
5. The scan must be a generic "scan and detect and act" FRAMEWORK: pluggable
   rules, each with a sampling policy (default: first N lines; a rule may ask
   for all lines), run in idle background a short time after open + sync load.
   Two rules now so the mechanism is clearly generic: SQLCMD (prompt+enable)
   and PSQL (turn off T-SQL error detection). Framework only — do NOT build
   rule functionality we don't need yet.
6. Full treatment: design doc, observability (registry-first), tests, perf
   coverage, journal.

## 1. How v1/STS does it (research digest, 2026-07-11)

- v1 editor: `mssql.toggleSqlCmd` command → `query/setexecutionoptions`
  JSON-RPC with `options.isSqlCmdMode` (per ownerUri, held server-side);
  status bar "SQLCMD: On/Off"; language flavor swapped to `sqlcmd`. No
  client-side parsing at all (queryRunner.ts:1228, statusView.ts:425).
- STS: SQLCMD lives in Microsoft.SqlTools.ManagedBatchParser
  (Lexer/Parser/BatchParserSqlCmd/BatchParserWrapper). The interactive query
  path parses ONLY (isLocalParse) — Query.cs applies side effects.
- **Only six things actually function** in STS SQLCMD mode:
  `GO [n]`, `:setvar`, `$(var)` substitution, `:r file` (include),
  `:on error exit|ignore`, `:connect server [-U u -P p]`.
  Everything else (`:out :exit :quit :reset :xml :ed :error :help :list
  :listvar :perftrace :serverlist :!!`) is recognized, then rejected with
  "Command not supported" (Parser.cs:425).
- Semantics worth copying exactly:
  - Variable lookup: `:setvar` internals first (case-insensitive), then
    process ENV VARS. Undefined `$(var)` = fatal for the whole parse
    (ThrowOnUnresolvedVariable=true).
  - `:setvar name` with no value REMOVES the variable.
  - `:connect` swaps the connection for SUBSEQUENT batches WITHIN THE RUN
    (Query.cs replaces its local queryConnection; new SqlConnection,
    Pooling=false). Integrated auth unless -U/-P given.
  - `:on error exit` → batch failure aborts the run; `ignore` → continue.
  - `:r` includes splice lines into the stream; circular includes detected.
  - Only GO is a batch separator; `GO n` repeats the batch n times.

## 2. Why Query Studio does it CLIENT-SIDE

v1 delegates parsing to STS because v1 sends whole scripts. Query Studio
already splits batches client-side (`src/sql/batchSplitter.ts`) and drives a
sequential per-batch loop (`executionOrchestrator.runCore`), with `GO n`
repeats, stopOnError, and per-batch `session.execute` on the STS2 v2 lane.
The v2 lane has no `setexecutionoptions`; adding server-held mode state would
fight the one-session/one-query model and QS's honest-error design. So:
**SQLCMD is a pure TypeScript preprocessor in front of the existing batch
loop**, mirroring STS's exact command set and error behavior. Same tokenizer
discipline as batchSplitter (reuses its exported `scanLine` so directives are
never recognized inside strings/comments — a bug class STS's lexer also
guards).

## 3. Design

### 3.1 Preprocessor (pure module) — `src/sql/sqlcmdPreprocessor.ts`

No vscode imports. Input: script text + injected seams. Output: an ordered
step plan or an honest parse error.

```
type SqlcmdStep =
  | { kind: "batch"; text: string; startLine: number }        // 0-based, input coords
  | { kind: "connect"; server: string; user?: string; password?: string; line: number }
  | { kind: "onError"; action: "exit" | "ignore"; line: number };

interface SqlcmdSeams {
  env(name: string): string | undefined;              // default: process.env
  readInclude?(rawPath: string): string | undefined;  // host wires fs + doc-dir resolution
}

parseSqlcmdScript(text, seams) →
  { ok: true; steps: SqlcmdStep[]; stats: { setvars; includes; connects; onErrors } }
| { ok: false; line: number; code: SqlcmdErrorCode; message: string }
```

Rules (STS parity):
- A directive is a line whose first non-blank char is `:` AND the line starts
  in lexer region "code" (scanLine-tracked). GO lines stay in batch text —
  `splitBatches` handles them downstream, so `GO n` keeps working untouched.
- Directives flush the current batch segment (STS attaches commands at batch
  boundaries; a flush is the same observable behavior).
- `$(var)` substitution on batch text lines, sqlcmd-style: everywhere on the
  line, including inside strings/comments (documented sqlcmd quirk). Name
  chars `[A-Za-z0-9_]`. Lookup: setvar table (case-insensitive) → env seam.
  Undefined → fatal `variableNotDefined` (STS parity). Malformed `$( ` →
  `invalidVariableName`. `:setvar` values may be double-quoted; no value
  removes the var. Substitution also applies to directive arguments
  (`:connect $(srv)` works — STS resolves server names).
- `:r`: include expansion via seam, spliced inline; included lines carry the
  include directive's line for error mapping (documented approximation);
  depth cap 16; circular include → `circularInclude`; missing/failed read →
  `includeFailed`; no seam wired → `includeFailed` (honest).
- `:on error exit|ignore` → step; anything else `badSyntax`.
- `:connect server [-U user] [-P pass]` → step (args may be quoted;
  password never appears in errors/diagnostics/logs).
- Rejected-but-recognized command list → `unsupportedCommand` with the
  command name; unknown `:foo` → `unrecognizedCommand`. Both fatal, like STS.

### 3.2 Orchestrator integration — `executionOrchestrator.ts`

`RunOptions.sqlcmd?: { seams: SqlcmdSeams; openConnectSession(step): Promise<ISqlSession> }`.

`runCore` with sqlcmd set: preprocess first. Parse error → synthesized error
message (doc-coordinate line via selectionStartLine), status "failed", zero
batches, `sqlcmd.run` marker with the error code — nothing executes (STS:
parse failure fails the query). Success → iterate steps:
- batch step → `splitBatches(step.text)` → existing inner loop unchanged
  (messages "Started executing query at Line N" use step.startLine offset;
  runBatch/timeout/rowStore untouched).
- onError step → flips a run-local `stopOnErrorDynamic` (overrides
  options.stopOnError for subsequent batches).
- connect step → `openConnectSession` swaps the session used by subsequent
  batches (orchestrator's session becomes mutable `currentSession`); emits an
  info message "Connected to <server>". Transient sessions closed in
  `finally` at run end (STS scope: the swap lives for the run only). Connect
  failure → error message + run fails (STS throws).
- SET wrappers (plan/parse modes) unchanged — they run on the binding session
  before/after runCore; sqlcmd+plan-mode composition therefore matches
  "wrapper outside the loop" semantics.
- `query.submit` marker gains `sqlcmd: true` attr; new
  `mssql.queryStudio.sqlcmd.run` instant marker with counts only
  (steps/batches/setvars/includes/connects/onError/errorCode) — never SQL
  text, never variable names/values, never server names (privacy).

### 3.3 Toggle + status bar (v1/SSMS parity, QS idiom)

- `QsSetSqlcmdModeRequest {enabled}` + `QsState.toggles.sqlcmd` (exact
  actualPlan pattern: controller field → queueStatePush).
- Toolbar button labeled `SQLCMD` after the plan buttons, `.toggled` styling
  when on (SSMS toolbar-toggle parity).
- Status bar: `SQLCMD` segment rendered ONLY when on (nothing when off — the
  ask; v1's "SQLCMD: Off" text is explicitly not wanted).
- ExecutionHost gets `sqlcmdEnabled` + a docDir hint for `:r` resolution; the
  controller wires `openConnectSession` through SqlDataPlaneService with a
  synthesized profile (integrated unless -U/-P; password lives only inside
  the auth-bundle closure).
- `mssql.queryStudio.sqlcmd.toggle` marker {enabled, source:
  user|scanPrompt|scanAuto}.
- No language-flavor swap (v1 swaps to `sqlcmd` grammar; QS's native language
  service already lexes `:`-led lines as opaque SqlCmdDirective tokens with
  no squiggles/completions — lexer.ts:264, context.ts:258, diagnostics.ts:661
  — so nothing to suppress for SQLCMD).

### 3.4 Scan-and-detect framework — `src/queryStudio/scanDetect.ts`

Pure core + thin scheduler. Framework, not a rules library.

```
type SamplingPolicy = { kind: "headLines"; lines: number } | { kind: "fullText"; maxChars?: number };
interface ScanSample { lines: string[]; totalLines: number; truncated: boolean }
interface ScanRule<T> { id: string; sampling: SamplingPolicy; detect(sample: ScanSample): T | undefined }
runScanRules(text, rules) → { id, detection }[]   // pure, no IO
```

- Sampling is per-rule; text is sliced once per distinct policy. Default
  policy for both shipped rules: headLines 50 (the ask). fullText carries a
  maxChars guard so a future "look at all lines" rule can't accidentally
  chew a 10k-line file byte-by-byte without saying so.
- Scheduler (controller-owned): ONE shot per document, `setTimeout` ~1.5s
  after the webview's first ready/state push (idle background after sync load
  — same precedent as the orphan-spill sweep timer), skipped if the document
  closed or scanning is disabled. Marker `mssql.queryStudio.scan.run`
  {rules, matched, sampledLines, ms, action} — rule ids and counts only,
  never file content.
- Master switch: `mssql.queryStudio.scan.enabled` (default true).

Shipped rules (`scanDetectRules.ts`):
1. **sqlcmd**: directive keywords at line start in code region (functional +
   recognized-rejected sets — a file full of `:out`/`:exit` is still a sqlcmd
   file). Action (controller): if already on → nothing; if
   `mssql.queryStudio.scan.autoEnableSqlcmd` → enable silently
   (source=scanAuto); else prompt EXACTLY: "This file has SQLCMD commands.
   Do you want to enable SQLCMD mode?" [Enable] [Don't Enable]
   [Don't show again, auto-enable] — third writes the setting globally AND
   enables now (source=scanPrompt). Prompt at most once per document.
2. **psql**: strong Postgres signals — `\`-led meta-commands at line start
   (\c \i \dt \set \echo \copy …), `$$` dollar-quoting, `CREATE EXTENSION`,
   `plpgsql`. Action: silently suppress native T-SQL diagnostics for THIS
   document (new per-document suppression seam in
   queryStudioLanguageService — cancel scheduler + clear markers, mirroring
   the existing `!diagnosticsEnabled()` branch), marker action=psqlSuppress.
   No prompt (the ask: "turn off TSQL error detection").

### 3.5 Observability (registry-first)

New events in perftest observability-contracts registry, regenerated and
re-vendored (core: train in perftest; vendored .generated.ts rides the qs:
train):
- `mssql.queryStudio.sqlcmd.toggle` — instant; attrs enabled
  (structuralMetadata), source (safeEnum).
- `mssql.queryStudio.sqlcmd.run` — instant; attrs steps/batches/setvars/
  includes/connects (structuralMetadata), onError+errorCode (safeEnum).
- `mssql.queryStudio.scan.run` — instant; attrs rules/matched/sampledLines/
  ms (structuralMetadata), action (safeEnum).
Privacy: counts, enums, booleans only. No SQL text, no variable names or
values, no file paths, no server names.

### 3.6 Perf posture

- Preprocessor is extension-host-side, zero webview-bundle impact; the
  toolbar/status additions are a few DOM nodes (bundle-budget test still
  gates the webview closure).
- SQLCMD OFF = zero new work on the execute path (one undefined check).
- Scan runs once per document, off the open critical path (post-load timer),
  samples ≤50 lines by default; scan.run marker carries ms so regressions
  are visible in perftest.
- Perftest scenario `querystudio-sqlcmd-run` (SC-5): open with a sqlcmd
  script (setvar/$(var)/GO 2/:on error), enable mode, run, assert
  sqlcmd.run marker + results — gate-eligible; feasibility check against the
  existing querystudio-open-autorun driver first; if the driver can't click
  webview toolbar buttons, enable via RPC test seam and journal the
  deviation.

## 4. Batches

- **SC-1** registry events + regenerate + vendor (perftest core:, vendored
  file with SC-3 qs: commit).
- **SC-2** sqlcmdPreprocessor + unit matrix (directive recognition incl.
  string/comment traps, setvar/env/undefined-fatal, unquoting, :r splice/
  circular/depth, :connect arg parsing, unsupported/unknown rejection, GO n
  passthrough, stats).
- **SC-3** orchestrator steps + ExecutionHost/controller/webview toggle +
  status bar + :connect session seam + markers + tests (fake-session runs:
  substitution visible in executed text, on-error-exit stops, connect swaps
  session + closes at end, parse error runs nothing).
- **SC-4** scanDetect framework + two rules + prompt/auto-enable/suppression
  wiring + settings + tests (sampling policies, rule matrices incl.
  false-positive traps — `::` casts are NOT sqlcmd, `\` in strings is not
  psql; scheduler once-per-doc).
- **SC-5** perftest scenario + gates + bundles + journal entries.

## 5. Test matrix (condensed)

- Preprocessor: ~30 cases across recognition/substitution/includes/connect/
  errors; property: preprocess(text with no directives, no $() ) is identity
  (modulo nothing — byte-equal single batch step).
- Orchestrator: setvar→substituted batch text on the wire; GO 2 under sqlcmd
  still repeats; :on error exit halts, ignore continues; :connect swap +
  transient close; parse error = failed + 0 executes; sqlcmd off = old path
  byte-identical.
- Scan: sqlcmd rule hit/miss matrix; psql rule hit/miss matrix; headLines
  sampling caps; fullText policy; framework runs rules independently (one
  throwing rule doesn't kill others).
- Controller: toggle round-trip state; prompt actions (3 buttons) wiring;
  auto-enable setting honored.
