# Query Studio — Execution Plan (living document)

**Created 2026-07-04.** The agent-facing build plan for Query Studio + SQL Data
Plane + MetadataService + completions port. Specs: docs 01–04 (reviewed v2) +
`query-studio-design-addendum.md` (BINDING — wins over the v2 docs). The repo
wins over any doc for a slice; deviations recorded in PROGRESS.md.
Design mock: `Query Studio.dc.html` + mockup1/2.png (visual reference).

## Branches and commit isolation (owner rule)

- Branches: `dev/query` in vscode-mssql, sqltoolsservice, perftest.
- **Foundation/core commits are SEPARATE from feature commits** (upstream PRs
  differ): prefix `core:` for changes to observability-contracts/registry,
  Debug Console core, perftest harness core, classic QueryResult page
  (grid extraction step 1-2), legacy seams, STS2 service-side. Prefix `qs:`
  for queryStudio/sqlDataPlane/sts2-binding/metadata/completions feature code.
  Never mix the two file sets in one commit.

## Binding decisions already made (addendum digest — do not relitigate)

- Names frozen: **Query Studio**, `mssql.queryStudio.*`, `Qs*` contracts,
  feature bucket `queryStudio`.
- Settings: `mssql.sqlDataPlane.enabled` + `.backend` are the ONLY data-plane
  switches (no `mssql.sts2.*` settings, ever). `preemptBackground` under
  sqlDataPlane.
- Connect marker pair: `connect.begin` → `connect.ready` (failure = ready with
  error+reason attrs; no third phase).
- `withOverlay` lives on `CatalogSnapshot` (not the handle).
- MetadataService OWNS dedicated-session lifecycle via `MetadataSessionSource`
  (one dedicated session per ServerKey, private serialized `USE` queue,
  applicationName `vscode-mssql-metadata`).
- CellValue is lazy-materialized; compact wire encoding + null bitmap crosses
  postMessage (never tagged unions); spill frames = length-prefixed JSON v1;
  ingest gate ≥100k rows/s; retained heap ≤2× wire bytes in-flight.
- Error line formula: `docLine(1-based) = selectionStartLine(1-based) +
  batch.startLine(0-based, relative to executed text) + (serverLine − 1)`.
- `QsRowsAppended` = counts only. Rows only via `QsGetRows`.
- Transaction guard (`@@TRANCOUNT`) runs on the DOCUMENT session, interactive.
- SET SHOWPLAN/STATISTICS/PARSEONLY wrappers = standalone single-statement
  batches; PARSEONLY copy = "Syntax checked"; USE executes under SHOWPLAN.
- Definition nav: in-document → QsRevealPosition; cross-file → host
  showTextDocument.
- Keybindings: F5 package-level (activeCustomEditorId when-clause) + webview;
  Ctrl+E/Ctrl+L/Ctrl+M webview-internal ONLY;
  `mssql.queryStudio.keybindingProfile: ssms|vscode` (default ssms).
- Status interop drives from tab activation (activeTextEditor is undefined
  when a webview is focused).
- Query Studio webview ships the PERF_MODE webview-mark bridge from M2.
- Monaco: ESM build, bundled local editor.worker, CSP worker-src carve-out,
  explicit MonacoEnvironment.getWorker, chunk budget 4 MB gz (CI-checked).
- STS2 wire naming reconciliation: capture = `v2/diagnostics.setCapture`
  (design's session.setCapture is wrong); all other adapter methods exist in
  CONTRACT.md (verified 2026-07-04, see foundation branch guide 07).

## STS2 contract worksheet (addendum §6 — track in PROGRESS as answered)

1. Verbatim result-stream messages (blocks M2 exit) — ANSWERED (2026-07-05,
   see language-service-docs/PROGRESS.md Entry 1): text is verbatim by
   construction on the client-bound wire (JSON escaping only; no service
   rewording/truncation/redaction). Two gaps found + FIXED service-side:
   SqlClient driver now subscribes InfoMessage (PRINT/RAISERROR≤10 were
   never delivered before), and v2/query.message now carries `line`
   (client V2MessageNotification already declared it). Preview blocker
   CLEARED.
2. Ack wire shape (AD-1→AD-2). 3. Dispose/complete ordering — ANSWERED:
   D-0011 (exactly one terminal, disposed status). 4. Structured rowsAffected
   (M2; message-parse fallback tagged). 5. SPID/server info in open result
   (M1; probe fallback). 6. Query options honored vs hints (AD-3).
7. Plan metadata (M3; heuristic+badge fallback). 8. Fatal semantics (AD-2).
9. Capture effective-mode reporting (M6) — CLIENT-SIDE ANSWERED (B7): the
   QsRunRecord stores the effective capture policy id + elevated flag at
   record time (worksheet honesty); service-side v2/diagnostics.setCapture
   remains uncalled by the client — gate exception recorded in PROGRESS
   Entry 9 (service echo of effective mode still desirable before GA).
10. v2/initialize capability schema (AD-1 first pin).

## Completions port inventory (dev/karlb/completions @ 065208582)

~31.7k insertions, 69 files. Key units:
- `copilot/sqlInlineCompletionProvider.ts` (3235) — engine/trigger/intent.
- `copilot/sqlInlineCompletionSchemaContextService.ts` (3740) — **schema
  compaction → becomes MetadataService.buildSchemaContext (MD-4, golden
  parity: Tight/Balanced/Generous/Unlimited byte-identical or recorded)**.
- `copilot/sdkLanguageModels/*` (~1.5k) — Anthropic/OpenAI/xAI providers,
  API-key resolution, catalog. `copilot/languageModels/shared/*`.
- `copilot/inlineCompletionDebug/*` (controller 2755 + store/profiles/trace
  loader/serializer/persistence) — port to new Debug Console patterns.
- `webviews/pages/InlineCompletionDebug/*` (~8k: SessionsTab 2043, Toolbar
  1939, ReplayTraceBuilder 1403, EventGrid 728, DetailPane 447…) — becomes
  Debug Console pages; **ReplayTraceBuilder is adapted into the
  GENERAL-PURPOSE replay wizard** (completions + QsRunRecord matrix runs,
  standardized formats; historical trace files must still load).
- `sharedInterfaces/inlineCompletion{Debug,Analysis}.ts` (~900),
  latencyBuckets, feature gate, settings guard, mainController wiring (84).

## Batches (large autonomous slices; each ends: tests clean, perf pair green, commits pushed-ready, PROGRESS entry)

### B1 — M0 + AD-0: editor shell, text sync, domain API, FakeBackend  [STATUS: in progress]
- core: register `mssql.queryStudio.*` marker family (17.1 + addendum 3.5)
  in observability-contracts; regenerate; re-vendor. Feature buckets:
  queryStudio.
- qs: `src/services/sqlDataPlane/api.ts` (doc 03 §4–6, §11–12 types),
  `fakeBackend.ts` (transcripts + chaos knobs), conformance harness core
  (sink-sequence assertions; §18.1 scenario list grows through AD-2/3).
- qs: queryStudio provider/registry/model/controller/textSync (doc 04 §7–8;
  echo suppression, hashes, resync valve, undo forwarding, coalescing ≤16ms,
  flush-before-execute); `sharedInterfaces/queryStudio.ts` (QS_SCHEMA_VERSION,
  QsSync*/QsState skeleton).
- qs: webview app shell (React + Monaco ESM + worker; theme bridge; layout
  per doc 01 §4–5: toolbar 35px/tabs 30px/status 24px/splitter 4px; results
  region ABSENT before first run); keybindings per addendum §4.
- qs: package.json customEditors + commands (new/openActive/openInClassic/
  duplicate/reconnect/showStatus) + settings (queryStudio.*, sqlDataPlane.*).
- Tests: registry 1-model-per-URI + multi-panel; textSync suite (typing,
  multicursor, paste, undo-after-host-edit, IME, CRLF, external change,
  hash-mismatch resync); fake conformance happy path; splitter corpus seeded.
- Gate: M0 gate (sync suite green; open marker pair; panels share model)
  + standing pair green.

### B2 — AD-1/AD-2 + M1: STS2 binding + connect
- qs: `src/services/sts2/wire/v2.ts` pinned from CONTRACT.md (worksheet #10,
  #2 answered inline); `sts2Transport.ts` (stdio lane via multiplexer child;
  spawn env registered pre-spawn); `sts2ProtocolEngine.ts` (correlation,
  demux lanes, ack/credit ledger §8.5, invariants §8.6, deadlines +
  synthesized terminals §8.7, fatal §8.8); `sts2Backend.ts`.
- qs: DocumentSessionBinding (profile-selection seam is a sanctioned legacy
  seam — CORE commit + add to STS legacy allowlist if it touches legacy
  files); connect/disconnect/change/reconnect; availability + status command;
  status-bar interop via tab activation (addendum §5.1) + unit test.
- Conformance vs FakeBackend + property tests (ledger permutations, deadline
  settlement, queue priority); live lane vs STS2 FakeDriver/Sqlite if the
  service harness allows in-repo.
- Gate: M1 (connect Sts2TestDb through STS2; no v1 fallback path exists).

### B3 — M2: execute + results core
- qs: lexerLite + batchSplitter (GO/GO n corpus incl. comments/strings/
  brackets); ExecutionOrchestrator (run shape doc 04 §12.2, continue-on-error,
  stopOnError, SET wrappers standalone batches, restore-in-finally);
  RowStore (page index, LRU, spill v1 JSON frames, caps, corrupt state) +
  spill privacy rules; MessageLog + error mapping (addendum §3.4 vector);
  QsGetRows window serving (p95 <8ms warm-spill target); cancel semantics.
- core: grid extraction steps 1–2 (IGridDataSource into classic QueryResult,
  then move shared components to `webviews/shared/resultsGrid/`) — SEPARATE
  commits, `query-10k-results` green after EACH.
- qs: step 3 Query Studio grid over QsGetRows; Messages tab; multi-result
  stacking; rows-affected (structured pref + tagged fallback); streaming
  states (follow-tail/rows-added chip); webview mark bridge; elapsed timer.
- Perf: `querystudio-open`, `querystudio-query-10k` (exploratory) both hosts
  where feasible; scenario metric names registered in contracts (core:).
- Gate: M2 (UX scripts 2–6 real; classic 10k green; qs-10k runs).

### B4 — M3: SSMS parity band
- Plans (SHOWPLAN/STATISTICS orchestration, PlanCollector heuristics +
  `planDetection: heuristic` diag, shared executionPlan extraction — core:
  commit for the extraction, qs: for the feature); results-to-text;
  ResultSerializer (CSV RFC4180/JSON/Markdown golden tests); save-as;
  selection summary/copy/View Cell; database combo + USE tracking (sources
  of truth ladder §11.4, bracket-escaped USE); transaction guard (document
  session); LSP bridge (executeCompletionItemProvider etc. + shadow v1
  connection per model; definition nav addendum §3.9); full keyboard map +
  keybindingProfile; OE "New Query Studio query" command.
- Gate: M3 parity checklist vs Appendix B (deferred items documented).

### B5 — MD-0..MD-3 (+MD-5 lite): MetadataService
- qs: `src/metadata/**` — keys/fingerprints (§4), handles + readiness +
  status events (MD-0); ServerCatalog S0–S1; DB hydration H1–H5 (+H6–H7)
  streaming SoA builder + string interning; dedicated-session ownership per
  addendum §3.2 (source union, USE-guard serialized queue, reopen-once);
  drift: DDL sniffer (shared lexer), digest polls (tiered), delta refresh
  (§9.4 30% rule); disk cache + validation (§11); large-catalog lite mode.
- Query Studio integration: DB combo from ServerCatalog, notifyExecutedBatch,
  nonblocking status (M4 gate: connect unaffected by hydration).
- Perf: metadata-hydrate-cold/warm, drift-ddl, context-build scenarios.

### B6 — MD-4 + M5: completions port + general replay wizard
- qs: port engine + LM providers + feature gates + settings guard from
  dev/karlb/completions (fixup: new repo layout, lint, contracts).
- MetadataService.buildSchemaContext absorbs compaction (golden parity suite
  Tight/Balanced/Generous/Unlimited vs old compactor fixtures; deviations
  recorded); engine consumes projection; events gain editorSurface.
- Debug console integration: port inlineCompletionDebug controller + pages
  onto the NEW Debug Console (left-rail pages or dedicated view per UX
  parity with completions branch — keep the strong UX: Sessions, EventGrid,
  DetailPane, Toolbar, settings overrides); **standardize the replay wizard**
  (ReplayTraceBuilder → shared replay wizard: completions traces + Query
  Studio QsRunRecords; matrix runs; standard descriptor formats; historical
  trace files load).
- Monaco inline bridge (QsInlineRequest/Accepted; ≤10ms overhead target).
- Gate: M5 (golden parity; latency/acceptance comparable on replay matrix;
  old traces load).

### B7 — M6: observability completion + preview readiness
- Replay recorder/runner for Query Studio runs (QsRunRecord; elevated-capture
  SQL text policy); privacy canary suite (all §18 stores incl. spill
  exclusion + LM prompt default-off); perftest scenarios promoted
  (maturity ladder); self-test entries (mssql.perf.queryStudioState PERF_MODE
  only); head-to-head classic vs Query Studio report; docs + release notes;
  STS2 worksheet rows closed or gate-excepted.

## Standing verification chain (every batch)
1. `npx tsgo -p tsconfig.extension.json --noEmit` + webviews (from
   extensions/mssql; never from repo root).
2. `npm run build` (repo root) — 0 errors.
3. `npx tsc -p tsconfig.extension.json --noCheck && npx vscode-test`
   (known flake: copilotChatEntry, suppresses 3 suite-mates).
4. perftest: workspaces tests; gate `query-10k-results` 4/4 official;
   `debug-console-smoke` green.
5. STS2 `verify.sh --quick` when sqltoolsservice touched.
6. obs-contracts: registry changes ⇒ regenerate + re-vendor (vendor-sync
   test enforces).

## Journal
Progress entries: `coding-docs/ssms-query-docs/PROGRESS.md`.
