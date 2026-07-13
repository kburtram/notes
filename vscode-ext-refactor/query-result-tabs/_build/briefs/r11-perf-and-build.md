# R11 Brief — Perf instrumentation, webview build system, and perftest harness

Reader brief for the vector-debugger / spatial-visualizer result tabs build.
Scope: (a) perf/bootstrap-perf code in `vscode-mssql/extensions/mssql`, (b) the webview
bundle system and lazy-chunk mechanics, (c) the `perftest` CLI harness (scenarios,
metrics, gates, commands). All paths absolute; line numbers verified 2026-07-11 on
branch `dev/query` (vscode-mssql) and perftest main.

---

## 1. The non-negotiable contract for the new tabs

From `C:/repos/test/coding-docs/ssms-query-docs/QS_BOOTSTRAP_PERF_PLAN.md` (authored
2026-07-10, Karl P0):

> Future spatial/vector result tabs (`coding-docs/query-result-tabs`) must be
> **0-cost for queries that don't use them**.

- **P2 on-use loading** (plan lines 34–38): a results tab contributes
  `{ id, label, appliesTo(resultSet), loader: () => import(...) }` — `appliesTo` is
  cheap metadata sniffing (column type names) in the entry chunk; the loader never
  runs unless the user opens the tab. This is the exact pattern already implemented
  by the query-plan tab (see §3).
- The bundle-budget test **already denylists the heavy viz libraries** the new tabs
  are likely to use (`maplibre-gl`, `leaflet`, `deck.gl`, `plotly`, `chart.js`,
  `echarts`, `three`, `cesium`, `@arcgis`, `d3` — see §4). Adding one of these as a
  static import of the QS entry fails the unit suite by name.
- `C:/repos/test/coding-docs/ssms-query-docs/PROGRESS.md:741` (Entry 16 residuals):
  "spatial/vector tabs MUST use the lazyResults P2 pattern (plan §P2 + denylist
  enforces)."

---

## 2. Perf instrumentation architecture (vscode-mssql)

### 2.1 Extension-host facade: `Perf`

`C:/repos/test/vscode-mssql/extensions/mssql/src/perf/perfTelemetry.ts`

- Singleton `Perf: IPerfTelemetry` (line 231). Since Phase 4 it is a **thin facade
  over the unified diagnostics core** (`src/diagnostics/diagnosticsCore.ts`): every
  `Perf.marker()` becomes a `diag.emit()` that fans out to whichever sinks are
  active — PERF_MODE harness sink, Debug Console live tail, user-enabled Session
  Diag store. "One emission path, several gates" (lines 6–18).
- `Perf.enabled` = `process.env.PERF_MODE === "1"` (line 93). When enabled AND
  `PERF_MARKER_URL` + `PERF_CONTROL_TOKEN` are present, a `PerfModeSink` is added
  with `PERF_RUN_ID`, `PERF_REP_ID`, `PERF_SCENARIO_ID` (lines 95–106).
- `Perf.marker(name, phase, attrs, correlationId)` (line 110): no-op unless
  `diag.anySinkActive` (a single array-length check — this is why per-entry-point
  logging is safe in the product). Emits with `kind: phase === "counter" ? "metric"
  : "event"`, tags `["perfMarker", "phase:<phase>"]`. Phases: `"instant" | "begin"
  | "end" | "counter"` (line 24).
- `featureFor(name)` (lines 59–68) maps marker-name prefixes to Debug Console
  feature buckets: `mssql.queryStudio.*` is NOT listed → falls to `"system"` unless
  it matches `mssql.query*` → `"query"`. (`mssql.queryStudio.…` starts with
  `mssql.query` so it buckets as `query`.)
- Attr classification (lines 76–84): under PERF_MODE everything is
  `diagnostic.metadata`; in normal use `ATTR_CLASSIFICATION` maps name-bearing keys
  (`nodePath`, `objectName` → `object.name`; `documentUri`, `uri` → `source.path`;
  `messages` → `user.text`) so redaction policy governs them. New pane attrs with
  user data must use these keys or extend the map.
- `Perf.webviewMark(mark, webviewName)` (line 149): validates ns-string timestamps
  with `/^[0-9]+$/`, emits with `process: "webview"`, `pid: 0`, tags
  `["perfMarker", "phase:instant", "webview:<name>"]`.

### 2.2 Diagnostics core (Debug Console + session-diag)

`C:/repos/test/vscode-mssql/extensions/mssql/src/diagnostics/diagnosticsCore.ts`

- `diag.emit(input: EmitInput)` (line 301): builds a `DiagEvent` (schema in
  `src/sharedInterfaces/debugConsole.ts`), classifies/redacts fields at this
  boundary (`classifyPayload`, line 308), stamps `monotonicNs` from
  `process.hrtime.bigint()` for extension-host events (line 351), fans out to all
  sinks; sink failures never propagate.
- **Spans**: `diag.startSpan(input)` (line 411) emits `<type>.begin` now and
  `<type>.end` with `durationMs` + `timingClass: "officialSameProcess"` on `end()`;
  `fail(error)` emits `.end` with `status:"error"`. Use this for pane host-side
  entry points (data fetch, transform) — duration comes free and correctly.
- **Trace correlation**: root-beginner regexes (lines 107–115) include
  `mssql.query.submit`, `mssql.command.invoked` etc.; traceless events within 120s
  inherit the root trace. Explicit `traceId` always wins.
- Sinks (`src/diagnostics/sinks.ts`): `PerfModeSink` (id `perfMode`) — bounded queue
  1000 drop-oldest, 250ms batched HTTP POST to `PERF_MARKER_URL`, 2s timeout
  (lines 31–33); forwards `perfMarker`-tagged events in the exact legacy wire
  format, PLUS diagnostic spans matching `/^(rpc\.|webview\.|sts\.)/`
  (`FORWARDED_SPAN_TYPES`, line 57) so CLI waterfalls get sublane detail.
  `LiveTailSink` = Debug Console; `SessionDiagSink` = user-enabled JSONL segment
  journal under a sessions dir (`src/diagnostics/sessionStore.ts`,
  `storeRoot/sessions/<name>/manifest.json` + segments).

### 2.3 Webview-side marks

`C:/repos/test/vscode-mssql/extensions/mssql/src/webviews/common/perfMarks.ts`

- `perfMark(name, attrs?)` (line 62): captures BOTH clocks at call time —
  `timestampUnixNs` = `BigInt(Math.round(performance.timeOrigin + now)) * 1e6`,
  `monotonicNs` = `BigInt(Math.round(now*1000)) * 1000n` (µs precision; ms×1e6
  overflows Number). Sent via `PerfWebviewMarkNotification` when enabled; else
  queued, bounded `MAX_PENDING = 50` (line 28). Timestamps captured at mark time so
  late enablement never distorts timing.
- Enablement: extension sends `PerfEnableNotification` (types in
  `src/sharedInterfaces/perf.ts:28` for the mark notification namespace); the
  webview provider calls `initPerfMarks(rpc)` once —
  `src/webviews/common/vscodeWebviewProvider.tsx:122`.
- `perfMarkAfterNextPaint(name, attrs?)` (line 94): double-rAF "visually complete"
  mark with a **500ms setTimeout fallback** that adds `rafThrottled: true` — hidden
  webviews have rAF throttled to a standstill; BOOT-4 warmup reps lost
  `editorInteractive` entirely before this fallback existed. Use this for every
  pane "rendered" mark.
- Bridge back to the host:
  `src/controllers/webviewBaseController.ts:185` —
  `connection.onNotification(PerfWebviewMarkNotification.type, (mark) =>
  Perf.webviewMark(mark, this._sourceFile))`. Enable-notification is re-sent on a
  schedule `[500, 2000, 5000, 15000, 30000]`ms + a 20s poll (lines 206–213), gated
  on `Perf.enabled || diag.anySinkActive` (line 197), because webview-ready can
  precede handler registration and consoles can open late.

### 2.4 Perf-only API seams (PERF_MODE only)

`C:/repos/test/vscode-mssql/extensions/mssql/src/perf/perfApi.ts`

- `registerPerfApi` (line 26) registers nothing unless `Perf.enabled`. Commands:
  - `mssql.perf.getState` (line 20/34) → `PerfState` (activation state, PIDs,
    markersQueued/Dropped).
  - `mssql.perf.setConfig(section, value)` (line 44) — harness-only global setting
    flip (used by `querystudio-open` to enable preview gates without a profile
    rebuild).
  - `mssql.perf.gridState(uri?)` (line 59) — result-set summaries probe.
  - `mssql.perf.gridFetchWindow` (line 121) — windowed row fetch through the REAL
    product row path.
  - `mssql.perf.oeSnapshot` (line 181).
- QS-specific seams live in
  `src/queryStudio/queryStudioEditorProvider.ts`: `mssql.perf.queryStudioConnect`
  (line 197), `mssql.perf.queryStudioExecute` (line 206),
  `mssql.queryStudio.newQueryFromContext` (line 388 — takes
  `{ profileId, initialSql, autoRun, sqlcmd?, source }`). A pane-activation perf
  seam for the new tabs (e.g. `mssql.perf.queryStudioActivateTab`) would follow this
  registration pattern.

### 2.5 QS boot marker call sites

- `src/webviews/pages/QueryStudio/index.tsx:17` — `mssql.queryStudio.boot.scriptStart`
  (first statement of the entry module body); `:24` — `boot.reactMount`.
- `src/webviews/pages/QueryStudio/app.tsx:705–707` — `boot.monacoReady`,
  `perfMarkAfterNextPaint("mssql.queryStudio.boot.editorInteractive")`, then
  `prefetchGridStack()` (P1 kick).
- `src/webviews/pages/QueryStudio/lazyResults.tsx:43,46` —
  `boot.gridChunkRequested` / `boot.gridChunkLoaded` (attr
  `waitedForByRender: boolean`); `:95` — `boot.planChunkLoaded`.
- Extension side: `src/queryStudio/queryStudioEditorProvider.ts:90` —
  `Perf.marker("mssql.queryStudio.open.begin", "begin")`;
  `src/queryStudio/queryStudioController.ts:661` — `mssql.queryStudio.open.end`
  (attrs `{ fromCache: false }`).
- **resultsRendered honesty** (`app.tsx:632–648`): when result sets exist and the
  grid chunk is not resident, the mark waits on `whenGridStackLoaded()` then
  `perfMarkAfterNextPaint("mssql.queryStudio.resultsRendered", { status, rows,
  resultSets })` — the first live run proved the mark drifted 120ms early firing on
  the Suspense placeholder. New pane "rendered" marks must be gated the same way
  (real content painted, never the placeholder).
- `boot.autoRunStart` is **registered but deliberately NOT emitted**
  (PROGRESS.md:708 — `query.submit` covers run start).
- Note: the plan's `queryStudio.boot.summary` per-open phase-table diag event
  (QS_BOOTSTRAP_PERF_PLAN.md:51–52) is **not implemented** — no `boot.summary`
  emitter exists in src; the phase table today comes from the harness's
  `markers.jsonl` (PROGRESS.md:738).

---

## 3. The lazy-chunk pattern (what the new tabs copy)

`C:/repos/test/vscode-mssql/extensions/mssql/src/webviews/pages/QueryStudio/lazyResults.tsx`

- Loaders are plain dynamic-import thunks (lines 28–30):
  `const planModule = () => import("./queryPlanTab");` etc.
- **P1 (known-need)**: `prefetchGridStack()` (line 37) — kicked once from
  `onEditorMount` via `requestIdleCallback(kick, { timeout: 1_000 })` with a
  `setTimeout(kick, 50)` fallback (lines 51–60).
- **P2 (on-use)**: `LazyExecutionPlanView = React.lazy(async () => { const module =
  await planModule(); perfMark("mssql.queryStudio.boot.planChunkLoaded", {}); return
  { default: module.QueryStudioExecutionPlanView }; })` (lines 93–97). azdataGraph
  (~2 MB) loads ONLY on first plan-tab activation. The header comment (lines
  16–19) explicitly names spatial/vector as followers of this exact pattern.
- `whenGridStackLoaded()` (line 73) — awaitable residency, starts the load if
  needed; `gridStackLoaded()` (line 64) — sync check.
- Suspense fallback `ResultsSurfaceLoading()` (lines 100–110): sets
  `renderWaitedForChunk = true` (honesty attr on `gridChunkLoaded`) and ensures the
  load is in flight; renders
  `<div className="qs-muted qs-results-surface-loading">Loading results view…</div>`.
- Mounting in the tab body (`app.tsx:1868–1881`): each surface is wrapped in
  `<React.Suspense fallback={<ResultsSurfaceLoading />}>`; the plan tab renders
  `<LazyExecutionPlanView rpc={...} executionPlanState={...} />` only when
  `visibleActiveTab === "queryPlan"`.
- **Light-shared-module rule**: anything the entry shell needs from a heavy module
  goes in a light sibling, e.g. `resultsGridShared.ts` (lines 6–13): "nothing in
  this file may import slickgrid/FluentResultGrid, ever". For the new tabs: the
  `appliesTo(resultSet)` column-type sniffing lives in a light module; everything
  else behind `import()`.
- **CSS caveat** (plan lines 39–41 + PROGRESS Entry 17): esbuild moves
  dynamic-chunk CSS out of the entry stylesheet, which strands lazy-chunk styles.
  CSS for lazy surfaces is statically hoisted into the entry (css-only
  side-imports). Cascade order matters: the slickgrid THEME css had to be hoisted
  FIRST (theme → base → vscode overrides → table.css) — a wrong order shipped a
  visible row-height regression. Verify emitted css input order via the metafile
  `inputs`. Also: dev css maps are `linked` — css SIZE deltas are usually maps,
  check content via metafile inputs.

### How to add a NEW lazy chunk — concrete steps

1. **No build-config change is required.** `scripts/bundle-webviews.js` already has
   `format: "esm", splitting: true` (lines 73–74) — any `import("...")` expression
   becomes a split chunk automatically under `dist/views/`.
2. Create the heavy pane module (e.g.
   `src/webviews/pages/QueryStudio/vectorTab.tsx`) importing its viz library.
3. In `lazyResults.tsx` (or a new `lazyPanes.tsx`), add
   `const vectorModule = () => import("./vectorTab");` and
   `export const LazyVectorView = React.lazy(async () => { const m = await
   vectorModule(); perfMark("mssql.queryStudio.boot.vectorChunkLoaded", {}); return
   { default: m.VectorDebuggerView }; });`
4. Mount behind `visibleActiveTab === "vector"` inside
   `<React.Suspense fallback={<ResultsSurfaceLoading />}>` in `app.tsx`.
5. Statically hoist the pane's CSS side-imports into the entry (watch cascade
   order), keep `appliesTo` sniffing in a light module.
6. Add the library to the `DENYLIST` in
   `test/unit/queryStudioBundleBudget.test.ts` if not already there (maplibre-gl /
   deck.gl / plotly / three / d3 etc. already are).
7. `npm run build:webviews-bundle` then run the unit suite — the budget test reads
   `webviews-metafile.json` and FAILS if the library re-enters the entry's static
   closure.
8. Register new marker names in the observability registry (§6) BEFORE emitting.

---

## 4. Exact perf budgets currently enforced for QS document load

### 4.1 Hard build-time budgets (unit-suite-failing)

`C:/repos/test/vscode-mssql/extensions/mssql/test/unit/queryStudioBundleBudget.test.ts`

- Entry under guard: `ENTRY = "dist/views/queryStudio.js"` (line 26).
- **Static-closure package DENYLIST** (lines 34–53), verbatim: `azdataGraph`,
  `@slickgrid-universal`, `slickgrid-react`, `sortablejs`,
  `multiple-select-vanilla`, `vanilla-calendar-pro`, `maplibre-gl`, `leaflet`,
  `deck.gl`, `@deck.gl`, `plotly`, `chart.js`, `echarts`, `three`, `cesium`,
  `@arcgis`, `d3`. Comment: "grow this list, never shrink it". CSS-only inputs are
  exempt (lines 105–110) — the denylist guards CODE on the init path.
- **Code-byte ceiling**: `CLOSURE_CODE_BYTES_CEILING = 11.5 * 1024 * 1024` (line
  56; 10.4 MB measured post-split + headroom). Failure message says raise the
  ceiling only "in the SAME review that justifies it".
- **Chunk-count ceiling**: `CLOSURE_CHUNK_CEILING = 20` (line 58).
- **Preload-manifest presence**: `dist/views/preload-manifest.json` must exist and
  have a non-empty `queryStudio` entry (lines 146–163).
- The metafile is REQUIRED (test fails if `webviews-metafile.json` is missing —
  "the bundle-budget guard cannot pass by absence", lines 60–68). Closure = walk of
  `imports` with `kind === "import-statement"` only (dynamic imports excluded), so
  lazy chunks are structurally outside the budget.

### 4.2 Runtime perf: baseline-relative, not absolute-ms

There is **no absolute millisecond budget** enforced for QS open today. The QS
scenarios are `maturity: "exploratory"` — their `scenario.wallclock` is
`official: false` (querystudio-open registry.ts:908; open-autorun :1610) and the
example configs run `"regression": { "baseline": "none", "failOnRegression":
false }` (`examples/config.boot.local.jsonc:52`). Gating is the generic regression
model (§7.4) once baselines mature. The only run-failing runtime contract today:
`querystudio-open-autorun` **success criteria REQUIRE**
`mssql.queryStudio.boot.editorInteractive` AND `boot.gridChunkLoaded` markers
(registry.ts:1604–1605) — the staged-loading contract is live-proven every run.

### 4.3 Current measured truth (the de-facto budgets to not regress)

`C:/repos/test/coding-docs/ssms-query-docs/PROGRESS.md:730–735` (Entry 16, run
d796deba, 8/8 passed):

- `querystudio-open` warm: **87–88ms** (cold outlier 5.3s = window-spawn variance,
  known). Earlier gate history: 110ms warm / 1963–4800ms cold (plan line 24).
- `querystudio-open-autorun` (open + SQL + autorun → REAL grid): **876–990ms**
  including ~325ms session connect.
- Phase table (rep-01, ms from open.begin): scriptStart 325 → monacoReady 472 →
  editorInteractive 497 → gridChunkRequested 547 → gridChunkLoaded 743 →
  resultsRendered 776.
- Init closure: 10.4 MB code (was 14.3 MB pre-BOOT-2); dev entry fetch 10.2 →
  2.3 MB after inline→linked sourcemaps.

---

## 5. Webview build system

### 5.1 Bundler config

`C:/repos/test/vscode-mssql/extensions/mssql/scripts/bundle-webviews.js`

- esbuild, one config: `entryPoints` map (lines 16–52) — QS entry is
  `queryStudio: "src/webviews/pages/QueryStudio/index.tsx"` (line 32); siblings
  include `queryResult`, `queryStudioReplay`, `queryResultsSnapshot`,
  `executionPlan`, `debugConsole`, plus
  `editorWorker: "monaco-editor/esm/vs/editor/editor.worker.js"` (line 36).
- Key options (lines 53–75): `bundle: true`, `outdir: "dist/views"`,
  `platform: "browser"`, `tsconfig: "./tsconfig.webviews.json"`,
  `sourcemap: isProd ? false : "linked"` (BOOT-2: inline maps made the webview
  fetch ~6x code bytes per open), `metafile: true` **always** (budget-test input),
  `minify: isProd`, `format: "esm"`, `splitting: true`. Loaders: tsx/ts/css plus
  `file` for svg/png/ttf/gif.
- Flags: `--prod|-p`, `--watch|-w`.

### 5.2 Metafile + preload manifest

`C:/repos/test/vscode-mssql/extensions/mssql/scripts/esbuild-utils.js`

- `build()` writes the metafile to `./webviews-metafile.json` when
  `config.outdir` contains "views", else `./extension-metafile.json` (lines
  75–82) — named per bundle so the extension build never clobbers the webviews
  graph the budget test reads.
- For webviews it also emits `./dist/views/preload-manifest.json` (lines 83–105):
  per-entry static-closure chunk basenames (walk of `import-statement` imports,
  entry excluded). Purpose: `<link rel="modulepreload">` turns the ESM import
  waterfall into one parallel fetch wave.

### 5.3 HTML injection

`C:/repos/test/vscode-mssql/extensions/mssql/src/controllers/webviewBaseController.ts`

- `_getHtmlTemplate()` (line 241): `<base href>` on `dist/views/`, then injects
  `preloadChunksFor(extensionPath, this._sourceFile)` as
  `<link rel="modulepreload" nonce=... href=...>` per chunk (lines 248–253,
  263), then `<link rel="stylesheet" href="${this._sourceFile}.css">` and
  `<script type="module" src="${this._sourceFile}.js">` (lines 274–276).
- `preloadChunksFor` (lines 754–768): reads
  `dist/views/preload-manifest.json` once, cached process-wide; missing manifest
  degrades to no preloads, never a throw.
- Because manifest entries are STATIC closure only, new lazy pane chunks are
  automatically excluded from preloading — correct for 0-cost-when-unused.

### 5.4 Build commands (extension repo)

Run in `C:/repos/test/vscode-mssql/extensions/mssql` (scripts from `package.json`):

- Full build: `npm run build` → `scripts/build.js` runs, in order:
  `build:prepare` (copy-assets + runtime localization) → `build:extension`
  (tsgo typecheck + tsc emit) → `build:extension-bundle` → `build:webviews`
  (tsgo typecheck) → `build:webviews-bundle` → `build:notebook-renderer-bundle`.
  `--prod` propagates to the bundlers.
- Webviews only: `npm run build:webviews-bundle` (needed before the bundle-budget
  test); watch: `npm run watch:webviews-bundle` or full `npm run watch`.
- Unit suite (includes `queryStudioBundleBudget.test.ts` and
  `observabilityContract.test.ts`): `npm test` (`vscode-test --coverage`).
- Bundles land in `dist/views/<entry>.js|.css` + shared `chunk-*.js` (esbuild
  splitting); monaco language chunks are the bulk of the ~555 chunk files.

---

## 6. Observability contract registry (marker vocabulary governance)

`C:/repos/test/perftest/packages/observability-contracts/`

- Registry: `src/registry/event-types.json` — exact names + prefix families +
  derived metric names. Boot events registered at lines 823–933 (all
  `kind: "webviewMark"`, `timingClass: "epochAligned"`,
  `measurementEligible: true`, `processRoles: ["webview"]`). Derived metrics at
  lines 2184–2198: `mssql.queryStudio.open.toEditorInteractive` (derivedFrom
  `mssql.queryStudio.open.begin` + `mssql.queryStudio.boot.editorInteractive`) and
  `mssql.queryStudio.open.toResultsRendered`.
- **Change workflow** (README lines 41–47): edit registry JSON → in
  `packages/observability-contracts`: `npm run build && npm test && npm run
  generate` → copy `generated/typescript/observabilityContract.generated.ts` over
  `vscode-mssql/extensions/mssql/src/sharedInterfaces/observabilityContract.generated.ts`
  → both repos' conformance suites must pass.
- `test/vendorSync.test.ts` regenerates and byte-compares (prettier-normalized)
  the vendored copy — registry edits without regenerate+re-vendor fail there.
- vscode-mssql conformance:
  `test/unit/observabilityContract.test.ts:39` greps src for
  `Perf.marker|begin|end|instant("...")` and `perfMarkAfterNextPaint("...")`
  literals and fails on unregistered names. NOTE: plain `perfMark("...")` webview
  literals are NOT matched by the extraction regex — register them anyway; the
  perftest side (below) catches them when a scenario waits on them.
- perftest conformance: `packages/perftest-cli/test/queryStudioScenario.test.ts`
  — EVERY `querystudio-*` scenario (family test, lines 74+) must (a) wait/assert
  only registered markers, (b) declare metric begin/end pairs that EXACTLY match
  the registry's `derivedFrom`, (c) keep `scenario.wallclock` as the only
  `official` metric while exploratory.

---

## 7. perftest harness

Repo: `C:/repos/test/perftest`. Workspaces: `packages/perftest-cli` (orchestrator),
`packages/observability-contracts`, `packages/perf-contracts`,
`packages/perftest-inproc`, `extensions/mssql-perf-driver` (the in-VS-Code driver).
Docs: `docs/CLI.md`, `docs/SCENARIO_AUTHORING.md`, `docs/RUNNING_TESTS.md`,
`docs/PRODUCT_INSTRUMENTATION.md`, `docs/REGRESSION_MODEL.md`.

### 7.1 How markers flow

Product `Perf.marker`/webview `perfMark` → `PerfModeSink` (batched POST to
`PERF_MARKER_URL` with `PERF_CONTROL_TOKEN`) → CLI marker sink
(`packages/perftest-cli/src/markers/markerSink.ts`) → per-rep
`perf-runs/<runId>/scenarios/<id>/reps/rep-NN/markers.jsonl` → normalizer
(`src/normalize/normalizer.ts`) → `result.json` metrics → SQLite `perf.db`
(`official_metric_samples` view is the regression-eligible dataset).
"session-diag" (the product's Session Diag store) is a separate, user-facing sink
of the SAME events; the harness plane is markers.jsonl.

### 7.2 Scenario definitions

`C:/repos/test/perftest/packages/perftest-cli/src/scenarios/registry.ts` —
scenarios are data (`ScenarioSpec`), registered with
`register({ implemented, plannedMilestone, maturity, spec })`. Maturity ladder
(lines 9–14): `exploratory → diagnostic → measurementCandidate → ciGating →
releaseGate`; "Promotion to ciGating requires baseline history + variance
evidence, not enthusiasm."

Key existing QS scenarios (all `maturity: "exploratory"`, wallclock
`official:false` except querystudio-query-10k which is official:true):

- `querystudio-open` (lines 868–921): flips preview gates via
  `mssql.perf.setConfig` steps; measures `mssql.queryStudio.new` →
  `waitForMarker mssql.queryStudio.open.end`; metric `mssql.queryStudio.open`
  (begin/end pair).
- `querystudio-query-10k` (lines 936–1012): preview gates PRE-SEEDED via
  `userSettings: { "mssql.sqlDataPlane.enabled": true, "mssql.queryStudio.enabled":
  true }` (must be true at ACTIVATION so STS spawns with `--enable-sts2`); setup
  `openDocument queries/select-10000.sql` → `mssql.queryStudio.openActive` →
  `queryStudioConnect`; measure `queryStudioExecute` → end
  `waitForMarker mssql.queryStudio.resultsRendered attrs { rows: 10000 }`
  (rows-guarded: the connect preflight renders its own 1-row results). Metrics
  `mssql.queryStudio.query.toComplete` / `.toRender` with
  `withinMeasuredWindow: true`.
- Shape family helper `registerQueryStudioShape` (lines 1196–1275) — the template
  to clone for pane scenarios; `tuningOverrides` ride
  `mssql.queryStudio.tuning.overrides` in userSettings.
- `querystudio-open-autorun` (BOOT-4, lines 1556–1625): setup
  `provisionConnectionProfile`; measured action =
  `mssql.queryStudio.newQueryFromContext` with args
  `[{ profileId: "perf-querystudio-default", initialSql: "SELECT 100 AS
  bootstrap_probe;", autoRun: true, source: "perftest" }]` →
  `waitForMarker mssql.queryStudio.resultsRendered`. Success REQUIRES
  `boot.editorInteractive` + `boot.gridChunkLoaded`. Declares name-only metrics
  `mssql.queryStudio.open.toEditorInteractive` / `.toResultsRendered`.
- `querystudio-sqlcmd-run` (lines 1627–1694).

Driver step vocabulary (docs/SCENARIO_AUTHORING.md lines 32–47): `command`,
`openDocument`, `waitForMarker`, `mssqlConnect/Disconnect`, `webviewProbe`,
`objectExplorerProbe`, `oeExpand`, `windowFetchCheck`, `completionProbe`,
`syntheticDelay`, `noop`; QS steps `queryStudioConnect` / `queryStudioExecute`
(driver impl `extensions/mssql-perf-driver/src/scenarioEngine.ts:452,487` — they
call `mssql.perf.queryStudioConnect` / `mssql.perf.queryStudioExecute`).
**There is deliberately no `sleep` step** — wait on a named marker; if none
exists, add an honest one behind PERF_MODE.

### 7.3 Metric extraction (normalizer)

`C:/repos/test/perftest/packages/perftest-cli/src/normalize/normalizer.ts`

- `scenario.wallclock` exists ONLY if both `scenario.start`/`scenario.end` markers
  observed (lines 105–116, 200–216); missing required markers ⇒ rep `invalid`, no
  official metrics ever. `official: true` only in a measurement pass on a passed
  rep (line 194).
- Declared marker-pair metrics (lines 246–287): pairs the LAST `beginMarker`
  before the FIRST `endMarker`; `withinMeasuredWindow` scopes the search to
  scenario.start…end (essential for QS — the connect preflight emits the same
  family). Missing markers ⇒ metric absent + a `metricMarkers:<name>` validation
  warning — never a fabricated value.
- Timing plane honesty (lines 83–98): same-pid + both monotonicNs ⇒ monotonic;
  else epoch diff, tagged `tags.timePlane`. Webview marks are epoch-plane by
  construction ⇒ boundary metrics like `.toRender` are diagnostic-only under
  `deriveEligibility` (stamped on every metric, lines 409–439; disagreement with
  the legacy `official` flag becomes a validation warning).
- **GAP (residual, PROGRESS ssms-query-docs:737–740)**: registry `derivedFrom`
  metrics with NO begin/end in the scenario spec (e.g.
  `open.toEditorInteractive`) are skipped by the normalizer (lines 247–249 skip
  specs without beginMarker/endMarker) — the CLI does not surface them per-rep
  yet; the phase table comes from markers.jsonl. Wiring CLI derivation is a named
  follow-up. For the new panes: either declare explicit begin/end pairs in the
  scenario metric (both markers must be registered and the pair must equal the
  registry's `derivedFrom`) or accept markers.jsonl-only until that pass lands.
- Counter markers (`phase: "counter"`, numeric `attrs.value`) get `.peak`/`.final`
  summaries automatically (lines 326–363) — use for pane memory/row-count
  telemetry.

### 7.4 Pass/fail gates

- Regression classification:
  `packages/perftest-cli/src/regression/regression.ts`. Defaults (lines 55–63):
  `pct: 10, absMs: 5, minSamples: 3, maxCv: 0.2, test: "welchT", pValue: 0.05`.
  A regression requires BOTH percent AND absolute floor exceeded, plus
  significance; high variance or thin samples ⇒ `inconclusive`, never gated.
  Worst metric wins the run verdict (lines 168–174). Only warmup-excluded,
  passed-rep, `official: true` samples participate.
- Expressed in run config, e.g. `examples/config.gate-proof.local.jsonc:41–47`:
  `"regression": { "baseline": "<name|runId|rolling:N>", "failOnRegression": true,
  "thresholds": { "default": {...}, "metrics": { "<metricName>": {...} } } }`.
  Exit codes (docs/CLI.md): 0 clean, 1 gated regression, 2 bad config, 3
  preflight, 4 scenario failed, 5 infrastructure, 6 insufficient samples.
- Success criteria inside a scenario (markerSeen with attrs subset + noErrors)
  are the per-rep pass/fail; prefer two independent proofs (extension-host marker
  AND webview render marker with the same counts).

### 7.5 Commands to run the perf suite locally

From the **perftest repo root** (`C:/repos/test/perftest`):

```powershell
npm install && npm run build        # builds all workspaces incl. CLI + driver
node packages/perftest-cli/dist/cli.js doctor
# QS bootstrap gates (querystudio-open + querystudio-open-autorun, 3 reps + 1 warmup):
node packages/perftest-cli/dist/cli.js run --config examples/config.boot.local.jsonc
# one scenario only:
node packages/perftest-cli/dist/cli.js run --config examples/config.boot.local.jsonc --scenario querystudio-open-autorun
# reports / baselines / comparisons:
node packages/perftest-cli/dist/cli.js report <runId> --open
node packages/perftest-cli/dist/cli.js baseline set <name> <runId>
node packages/perftest-cli/dist/cli.js compare --current <runId> --baseline <name|rolling:5>
node packages/perftest-cli/dist/cli.js trend --scenario querystudio-open-autorun
```

`config.boot.local.jsonc` points at the product dev tree
(`"path": "../vscode-mssql/extensions/mssql"`) and STS via env
`MSSQL_SQLTOOLSSERVICE=C:\repos\test\sqltoolsservice\src\Microsoft.SqlTools.ServiceLayer\bin\Debug\net10.0`;
SQL comes from `"provider": "external"` + `STS2_SQLSERVER_CONNSTRING` (the
container SQL is `localhost,14333` per central-observability setup). **Build the
extension first** (`npm run build` in `extensions/mssql`) — the pipeline checks
`main` exists but stale builds misbehave. Output lands in `perf-runs/<runId>/`
(`report.md`, `summary.json`, per-rep `result.json` + `markers.jsonl`,
`harness-log.jsonl`) and `perf.db`. Don't touch the VS Code windows during reps.

### 7.6 Recipe: perftest scenarios for the new panes

1. Register new markers in `event-types.json` (e.g.
   `mssql.queryStudio.boot.vectorChunkLoaded` as `webviewMark`/`epochAligned`;
   `mssql.queryStudio.vectorTab.open.begin/.end` pair;
   `mssql.queryStudio.vectorTab.rendered` webviewMark with `rows`/`dims` attrs) +
   regenerate + vendor (§6).
2. Emit: extension-side `Perf.marker` at the tab-activation entry point,
   webview-side `perfMark`/`perfMarkAfterNextPaint` at chunk-load and
   real-paint. Gate "rendered" on actual pane content (§2.5 honesty rule).
3. Add scenarios in `registry.ts` cloning `registerQueryStudioShape` discipline:
   `userSettings` activation gates, fixture SQL under `workspaces/perf/queries/`
   (vector/spatial-typed columns need a new seed fixture + provisioner support),
   attrs-guarded end marker, success = chunk-loaded marker + rendered marker +
   `noErrors`, `maturity: "exploratory"`, wallclock `official:false`.
   Two shapes minimum: (a) pane-unused guard — run a plain query, success asserts
   boot metrics unchanged and NO `vectorChunkLoaded` marker; (b) pane-activation —
   open tab, measure activation→rendered.
4. A driver step or PERF_MODE seam to activate the tab is required (there is no
   generic "click tab" step) — mirror `mssql.perf.queryStudioExecute`
   (`queryStudioEditorProvider.ts:206`) with e.g.
   `mssql.perf.queryStudioActivateTab { tabId }`, then drive it via a `command`
   step.
5. `packages/perftest-cli/test/queryStudioScenario.test.ts` will automatically
   conformance-check any new `querystudio-*` scenario id.

---

## 8. File index (quick jump)

| Concern | File |
|---|---|
| Perf facade | `vscode-mssql/extensions/mssql/src/perf/perfTelemetry.ts` |
| Perf-only commands/seams | `.../src/perf/perfApi.ts`; QS seams `.../src/queryStudio/queryStudioEditorProvider.ts:197,206,388` |
| Diagnostics core / spans | `.../src/diagnostics/diagnosticsCore.ts` (emit:301, startSpan:411) |
| Sinks (harness/console/session) | `.../src/diagnostics/sinks.ts`; store `.../src/diagnostics/sessionStore.ts` |
| Webview marks | `.../src/webviews/common/perfMarks.ts`; init `vscodeWebviewProvider.tsx:122` |
| Mark bridge + modulepreload HTML | `.../src/controllers/webviewBaseController.ts:185,241–279,754–768` |
| Lazy-chunk pattern | `.../src/webviews/pages/QueryStudio/lazyResults.tsx`; mounts `app.tsx:1798–1881` |
| Boot marks | `QueryStudio/index.tsx:17,24`; `app.tsx:705–707,632–648` |
| Light shared module rule | `QueryStudio/resultsGridShared.ts` |
| Bundle config | `.../scripts/bundle-webviews.js`; metafile/manifest `.../scripts/esbuild-utils.js:75–105`; orchestration `.../scripts/build.js` |
| Bundle budget test | `.../test/unit/queryStudioBundleBudget.test.ts` |
| Marker-name conformance | `.../test/unit/observabilityContract.test.ts` |
| Vocabulary registry | `perftest/packages/observability-contracts/src/registry/event-types.json` (boot:823–933, derived:2184–2198) |
| Vendor sync guard | `perftest/packages/observability-contracts/test/vendorSync.test.ts` |
| Scenario registry | `perftest/packages/perftest-cli/src/scenarios/registry.ts` (QS:868–1012, shapes:1196–1445, autorun:1556–1625) |
| Scenario conformance | `perftest/packages/perftest-cli/test/queryStudioScenario.test.ts` |
| Normalizer | `perftest/packages/perftest-cli/src/normalize/normalizer.ts` |
| Regression gate | `perftest/packages/perftest-cli/src/regression/regression.ts` |
| Run configs | `perftest/examples/config.boot.local.jsonc` (QS boot), `config.gate-proof.local.jsonc` (thresholds shape) |
| Driver steps | `perftest/extensions/mssql-perf-driver/src/scenarioEngine.ts:452,487,891` |
| Plan + measured baselines | `coding-docs/ssms-query-docs/QS_BOOTSTRAP_PERF_PLAN.md`; `coding-docs/ssms-query-docs/PROGRESS.md` Entries 15–17 |
