# T-SQL Language Service — Execution Plan

Source spec: `05-tsql-language-service-design.md` (2026-07-05, replacement spec —
BINDING except where a deviation is recorded here or in PROGRESS.md).
Journal: `PROGRESS.md` (same folder). Batch numbering continues the Query Studio
plan: B8..B14 = LS-0..LS-6. Branches: `dev/query` in vscode-mssql + perftest
(+ sqltoolsservice only if a service-side need emerges; none is expected —
MetadataService reaches STS2 through raw SQL over the data plane).

## Commit isolation (owner rule, extends core:/qs:)

- `core:` — observability-contracts registry vocabulary + re-vendored
  generated contract; eslint custom-rule changes (`banned-imports.js`);
  Debug Console core; anything shared beyond the feature.
- `ls:` — NEW prefix: `src/sqlLanguage/**`, `src/sqlScripting/**`, their
  tests, fixtures, and data assets. Self-contained; must not depend on qs:
  commits landing in the same PR train.
- `qs:` — Query Studio integration surface (RPC contracts, controller/webview
  wiring, package.json settings/commands) and MetadataService hydration
  extensions (new H-sections).

## Local code reality (verified 2026-07-05; adapt spec accordingly)

1. **There is no LSP bridge in Query Studio today** (B4 deferral). The spec's
   "old-engine bridge" is therefore NEW work, not a wrapper: QS documents get
   ZERO deterministic language features right now. The backing document is a
   real `untitled:` TextDocument with languageId `sql`, so (a) the classic STS
   v1 `LanguageClient` (documentSelector `["sql"]`, diagnostics collection
   `mssql`) already matches it, and (b) `vscode.execute*Provider` commands
   work against `model.backingDocument.uri`. Bridge = provider-command
   aggregation + a lazy shadow v1 connection via `connectionManager` on the
   backing URI + `onDidChangeDiagnostics` forwarding to Monaco markers.
2. **Monaco webview surface**: only an inline-completion provider is
   registered today (`app.tsx` ~L387). Every deterministic feature needs a
   Monaco provider in the QS webview + a `qs/lang.*` RPC contract + a
   controller handler that calls the router. Contracts go in a new
   `src/sharedInterfaces/queryStudioLanguage.ts` (webview-safe, vscode-jsonrpc
   pattern per queryStudio.ts).
3. **MetadataService** (`src/services/metadata/`) provides: objects/columns/
   PK-columns/FK edges+ordered pairs/params/schemas, `resolveName`, folded
   prefix `search`, immutable generation-stamped `CatalogSnapshot` (pinning =
   hold the ref), per-section readiness, `defaultSchema`, `caseSensitive`.
   GAPS to fill in-batch (all `qs:` MetadataService commits):
   - B9: H3 gains `is_identity`/`is_computed` column flags (INSERT scaffolds).
   - B11: H7 descriptions (`sys.extended_properties` MS_Description).
   - B12: lazy module-definition reads (`sys.sql_modules`), unique
     constraints/indexes as needed for scripting F2.
   Server version/edition/capabilities come from `session.info` (wire
   serverInfo), NOT the snapshot — the catalog provider adapter unifies both
   into `SqlLanguageEnvironment`. Database list via the host seam
   (`executionHost.listDatabases()`), cached on the adapter.
4. **Lexer**: `src/sql/batchSplitter.ts` (scanLine/leadingKeyword/splitBatches)
   is shared with MetadataService's DDL sniffer. Do NOT destabilize it in
   LS-0. Build the full lexer in `src/sqlLanguage/core/lexer.ts`; segmenter
   parity tests assert agreement with `splitBatches` on the GO corpus;
   converging batchSplitter onto the full lexer is a recorded follow-up.
5. **Observability**: emit through `diag.startSpan`/`diag.emit` with
   `{raw, cls}` fields. Register `sqlLanguage.`, `sqlScripting.`, and
   `queryStudio.languageService.` span families in
   perftest/packages/observability-contracts (core: + re-vendor; vendor-sync
   test enforces). Language-service events carry NO document text and NO
   user identifiers — counts, kinds, durations, context kinds, readiness,
   suppression reasons, generation numbers only. Extend the privacy canary
   suite accordingly in each feature batch.
6. **Purity enforcement**: extend `eslint/custom-rules/banned-imports.js`
   (core: commit): `src/sqlLanguage/core/**` and `src/sqlLanguage/features/**`
   may not import `vscode`, `src/services/**`, `src/queryStudio/**`, or
   node-only APIs; `provider/catalogProvider.ts` and `host/**` are the only
   sanctioned integration points (spec §6.2). Add the long-documented STS2
   wire clause (`src/services/sts2/wire/v2.ts` importable only under
   `src/services/sts2/`) in the same commit.
7. **Tests**: mocha TDD + chai under `test/unit`, imports from `../../src/...`,
   run via `npx vscode-test`. The fourslash harness lives in
   `src/sqlLanguage/testSupport/` and runs in this lane (core is pure, so no
   VS Code dependency). Perf probes gate on `Perf.enabled` in
   `src/perf/perfApi.ts`; scenario work lands in perftest later (B14 or when
   promoted).
8. **Feature capture/replay**: reuse `src/diagnostics/featureCapture/*`
   generics (instantiation #3) in B13 for completion/diagnostics summaries.

## Settings (final names; no per-feature user toggles initially)

```jsonc
"mssql.queryStudio.languageService.engine": "sqlToolsService" | "nativeTypeScript"  // default sqlToolsService
"mssql.sqlLanguage.diagnostics.enabled": true,
"mssql.sqlLanguage.keywordCasing": "upper" | "asTyped",
"mssql.sqlLanguage.completions.snippets": true,
"mssql.sqlLanguage.definition.mode": "peek" | "open"
```

NEVER `mssql.sts2.*`. Per-feature maturity lives in the router capability
table (code), not user settings.

## Batches (large autonomous slices; each ends: verification chain green, commits, PROGRESS entry)

### B8 / LS-0 — Foundation: setting, router, bridge, lexer, segmenter, provider seam, harness  [STATUS: complete — PROGRESS Entry 2]
- core: register `sqlLanguage.` / `sqlScripting.` / `queryStudio.languageService.`
  span families (+ `queryStudio.lsp.` family already registered in B7 — the
  bridge finally emits it); regenerate; re-vendor. eslint purity boundaries.
- ls: `src/sqlLanguage/` skeleton per spec §6.1: `api.ts`,
  `core/text/{textSnapshot,position}.ts`, `core/lexer.ts` (full-fidelity:
  nested block comments, N'...', brackets, quoted idents, variables, temp
  names, `GO`-line rules, SQLCMD-directive lines opaque, keywordId metadata,
  line-start states for incremental lexing), `core/keywords.ts` +
  `data/keywords.generated.ts` (provenance header), `core/segmenter.ts`
  (batch + statement segmentation incl. module-body AS consumption),
  `provider/types.ts` (`ISqlLanguageMetadataProvider`, `IPinnedMetadataView`,
  `LanguageReadiness`, `SqlLanguageEnvironment` per spec §8),
  `provider/{nullProvider,fixtureProvider}.ts`, `provider/catalogProvider.ts`
  skeleton (env + readiness + resolve/list over CatalogSnapshot),
  `host/router.ts` (LanguageFeatureRouter + NativeCapabilityTable +
  circuit-break), `host/nativeEngine.ts` (returns honest empty results),
  `host/bridgeEngine.ts`, `testSupport/fourslash.ts` skeleton +
  `fixtureCatalog.ts`, lexer/segmenter corpus tests + splitBatches parity.
- qs: `sharedInterfaces/queryStudioLanguage.ts` contracts (completion,
  resolve, hover, signature, definition, diagnostics-publish, folding,
  symbols, highlights, semanticTokens — schema-versioned); controller
  handlers → router; webview Monaco providers (completion/hover/signature/
  definition/folding + marker application via `monaco.editor.setModelMarkers`);
  bridge shadow-connection lifecycle (lazy create on first bridge-routed
  request, retarget on database change, teardown on model dispose — the
  `queryStudioDocumentModel.ts` "tear down shadow LSP" TODO becomes real);
  `mssql.queryStudio.languageService.engine` setting; status command
  `MSSQL: Show Query Studio Language Service Status` (spec §18.2).
- Gate: toggle changes effective route live; bridge completions/hover/
  signature/definition/diagnostics work in QS against a connected doc;
  native lexer/segmenter corpus green + parity with splitBatches; no shadow
  v1 connection until a bridge-routed feature is requested (test); no native
  feature claims schema intelligence yet; standing verification chain green.

### B9 / LS-1 — Native non-AI completions  [STATUS: functional core complete — PROGRESS Entry 3; residuals: fourslash depth toward 150+, live dogfood, PERF probe]
- ls: sketch parser (`core/sketch/*`: select/dml/ddl/procedural/expressionScan/
  recovery — tolerant + total), `core/overlay.ts` (CTEs, #temp, @table vars,
  SELECT INTO, script-local DDL, DROP ends scope), `core/databaseContext.ts`
  (USE map per spec §4.4), `core/binder.ts` (scopes, alias-before-object,
  qualified/unqualified columns, inserted/deleted, suppression reasons),
  `core/context.ts` (caret classifier for every spec §10.2 context),
  `core/fuzzy.ts`, `core/quote.ts`, `features/completion.ts` (candidates,
  FK join suggestions incl. composite, JOIN-table FK-adjacency ranking, star
  expansion, INSERT scaffolds skip identity/computed, EXEC named params,
  deterministic ranking spec §10.5, item shaping §10.6, lazy resolve),
  `data/{builtinFunctions,snippets,statementKeywords}.json`,
  `provider/overlayView.ts`; fourslash suite 150+ cases (incl. case-sensitive
  collation + bracketed identifier fixtures); bench probes (lexer/sketch/bind/
  completion budgets spec §16.1) as unit-lane bench tests with generous CI
  thresholds + PERF_MODE probe `mssql.perf.sqlLanguage`.
- qs: H3 identity/computed flags; wire completion RPC to native when routed;
  router capability `completion=preview`; `mssql.sqlLanguage.completions.
  snippets` + `keywordCasing` settings.
- Gate: acceptance matrix Appendix A green; 150+ tests; warm p95 < 40ms on
  bench corpus; zero network I/O on completion path (test via fixture
  provider instrumentation); honest incomplete results under partial
  readiness; privacy canary extension green.

### B10 / LS-2 — Native diagnostics  [STATUS: COMPLETE — Entry 4; ls: 5358da450 + qs: 47176417e]
- ls: `features/diagnostics.ts` — T1 lexical/structural (errors) + T2 binder
  207/208/209-style (warnings) + suppression ladder (spec §11.2, every
  suppression counted by reason, no identifier text); debounce ~300ms +
  time-sliced whole-doc pass + stale-version cancel.
- qs: diagnostics publish RPC → Monaco markers, source `T-SQL (native)`,
  codes `mssql(207|208|209)`; mutual exclusion with bridge diagnostics;
  `mssql.sqlLanguage.diagnostics.enabled`; suppression counts in status
  command; capability `diagnostics=preview`.
- Gate: honesty suite (spec §17.4 full list) zero unexpected diagnostics;
  100+ cases; markers clear on close/route-switch; suppression telemetry
  visible in Debug Console.

### B11 / LS-3 — Hover/tooltips + signature help  [STATUS: COMPLETE — Entry 5; ls: 25b272149 + qs: 83b20f5f4]
- ls: `features/hover.ts` (objects/columns/aliases/variables/params/CTEs/
  temp tables/procs/functions/builtins; PK/FK badges; never overclaims),
  `features/signatureHelp.ts` (routines + curated builtins; active param by
  comma index or named arg); builtin signature data.
- qs: H7 descriptions hydration + `getDescription` on the adapter; hover/
  signature RPC wiring; capabilities `hover=preview`, `signatureHelp=preview`.
- Gate: 80+ hover / 60+ signature tests; missing metadata degrades cleanly;
  no network on hover path except explicit lazy resolve.

### B12 / LS-4 — Scripting engine + definition/peek  [STATUS: COMPLETE — Entry 6; core: f72652c4a + ls: 55a97f065 + qs: 2a94d6c5d]
- ls: `src/sqlScripting/**` (service, ModuleEmitter with token-level
  CREATE→ALTER / CREATE OR ALTER rewrite gated on server capability,
  CreateTableEmitter F1→F2, DmlTemplateEmitter, anchors, fidelity notes);
  `features/definition.ts` routing by bound symbol kind (spec §13.4 table).
- qs: MetadataService lazy detail reads (module definitions; unique
  constraints/indexes for F2); QS peek virtual Monaco model + `mssql-def:`
  TextDocumentContentProvider; `mssql.sqlLanguage.definition.mode`;
  capability `definition=preview`.
- Gate: golden scripts; column-anchor tests; ALTER rewrite property tests;
  encrypted/permission-hidden honesty; local-symbol navigation in-document.

### B13 / LS-5 — Semantic polish + capture  [STATUS: pending]
- ls: folding + document symbols (earlier if trivial post-B9), highlights,
  semantic tokens full+delta, code actions (expand star, qualify column,
  add alias, fill GROUP BY); optional lexer-driven Monaco tokenizer behind
  preview flag.
- qs: wiring; feature-capture instantiation #3 (completion/diagnostics
  summaries — counts and context kinds only, NO text) + Replay-Lab-style
  matrix support where meaningful.
- Gate: token tests; no completion/diagnostics perf regression; colorization
  independently disable-able.

### B14 / LS-6 — Audit + default-flip decision  [STATUS: pending]
- Parity matrix vs bridge; native-vs-bridge latency head-to-head (perftest
  scenario `querystudio-language-completion` + report); suppression counter
  review; dogfood false-positive review; decision memo in PROGRESS;
  default-flip or documented blockers; classic-editor preview decision;
  shadow-v1 deprecation plan for QS.

## Standing verification chain (every batch)
1. `npx tsgo -p tsconfig.extension.json --noEmit` + webviews (from
   extensions/mssql).
2. `npx eslint` on touched dirs (purity boundaries are lint-enforced).
3. `npm run build` (repo root) — 0 errors.
4. `npx tsc -p tsconfig.extension.json --noCheck && npx vscode-test`
   (known flake: copilotChatEntry).
5. perftest workspaces if registry touched; gates
   (query-10k-results, querystudio-open, querystudio-query-10k,
   debug-console-smoke) when the QS surface or service is touched.
6. Privacy canaries green (extended per batch).

## Worksheet (track answers in PROGRESS)

1. Bridge provider-command aggregation: do non-STS providers pollute QS
   results (Copilot, other SQL extensions)? If yes → direct STS v1 client
   adapter (spec §9.3 recommendation path).
2. Shadow v1 connection side effects on status bar / OE / connection UI
   (status interop drives from tab activation — verify a QS-focused tab
   never shows the shadow connection as the active one).
3. `connectionManager.onDidCloseTextDocument` disconnect vs custom-editor
   lifetime: does closing the QS tab dispose the backing doc and tear the
   shadow connection predictably?
4. Case-sensitive collation fixture: need a CS_AS test database seed for the
   live gates (unit fixtures cover the logic; live proof optional pre-GA).
5. `master`/system-db resolution: catalogSchemaContextPayload ships
   `masterSymbols: []` today — decide system-object catalog exposure via
   `systemObjects()` (curated list exists in copilot layer; move/share).
6. Monaco `sql` language id collision: classic Monarch tokenizer + our
   providers coexist; verify no double-completion when VS Code-level
   providers also fire inside the webview (they don't — webview Monaco is
   isolated; confirm once wired).
