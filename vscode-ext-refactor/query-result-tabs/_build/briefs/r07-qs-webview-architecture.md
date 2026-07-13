# R07 — Query Studio webview architecture (results tabs, lazy loading, data plane, styling)

Sources read completely (all paths relative to `C:/repos/test/vscode-mssql/extensions/mssql/src` unless noted):
`webviews/pages/QueryStudio/{index.tsx, app.tsx, results.tsx, lazyResults.tsx, queryPlanTab.tsx, resultsGrid.tsx, resultsGridShared.ts, resultsTextView.tsx, executionRequests.ts, monacoSetup.ts, keybindings.ts, queryStudio.css}`, `sharedInterfaces/{queryStudio.ts, queryStudioResultsLayout.ts, queryStudioMessages.ts, queryStudioGridOps.ts}`, `webviews/common/{perfMarks.ts, vscodeWebviewProvider.tsx}`, `controllers/webviewBaseController.ts` (HTML/preload portions), `scripts/bundle-webviews.js`, `scripts/esbuild-utils.js` (manifest portion), `test/unit/queryStudioBundleBudget.test.ts`, plus targeted reads of `queryStudio/queryStudioController.ts`.

---

## 1. Boot path and bundle composition

### 1.1 Entry and HTML

- Bundler: **esbuild**, config in `scripts/bundle-webviews.js`. QS entry: `queryStudio: "src/webviews/pages/QueryStudio/index.tsx"` (bundle-webviews.js:32). Key options (bundle-webviews.js:53–75): `format: "esm"`, **`splitting: true`** (this is what makes `import()` produce separate chunks), `outdir: "dist/views"`, `metafile: true` always (the budget test reads it), `sourcemap: "linked"` in dev (inline maps made the webview fetch ~6x bytes — comment at :68), tsconfig `./tsconfig.webviews.json`. The Monaco editor worker is its own entry: `editorWorker: "monaco-editor/esm/vs/editor/editor.worker.js"` (:36).
- HTML template: `controllers/webviewBaseController.ts:241–280` (`_getHtmlTemplate`). `<base href>` points at `dist/views/`; loads `${this._sourceFile}.css` then `<script type="module" src="${this._sourceFile}.js">`. For QS, `_sourceFile` is `"queryStudio"` (4th arg of `super(context, "queryStudio", initialState, "queryStudio")` at `queryStudio/queryStudioController.ts:155`).
- **Modulepreload wave (BOOT-2)**: `preloadChunksFor()` (webviewBaseController.ts:754–768) reads `dist/views/preload-manifest.json` (emitted per-entry by `scripts/esbuild-utils.js:87–104` — walks the metafile's `import-statement` edges from each entry) and injects `<link rel="modulepreload" nonce=... href=chunk>` per static-closure chunk (webviewBaseController.ts:248–253). This turns the ESM static-import waterfall into one parallel fetch. Missing manifest degrades to no preloads, never a throw.
- `index.tsx` (24 lines): imports `"./monacoSetup"` **first** (binds bundled Monaco via `loader.config({ monaco })` before any editor mounts — monacoSetup.ts:55; worker instantiated as `new Worker(new URL("editorWorker.js", document.baseURI), { type: "module" })`, monacoSetup.ts:33). Then `perfMark("mssql.queryStudio.boot.scriptStart")` (index.tsx:17), `ReactDOM.createRoot(...).render(<VscodeWebviewProvider><QueryStudioApp/></VscodeWebviewProvider>)` (index.tsx:19–23), `perfMark("mssql.queryStudio.boot.reactMount")` (index.tsx:24).
- `retainContextWhenHidden: true` for the QS custom editor (`queryStudio/queryStudioEditorProvider.ts:372`).

### 1.2 Staged loading tiers (this is the contract new panes must follow)

Documented in the `lazyResults.tsx` header comment (lazyResults.tsx:6–23):
- **Entry chunk**: Monaco + the app shell ONLY.
- **P1 (known-need)**: grid stack (`results.tsx`/`resultsGrid.tsx` → slickgrid) loads via dynamic import, **prefetched on first idle after the editor is interactive** — by the time a query returns the chunk is usually resident.
- **P2 (on-use)**: execution-plan surface (azdataGraph, ~2 MB) loads ONLY when the plan tab is activated. Verbatim from the comment (lazyResults.tsx:16–19): *"Future heavy tabs (spatial, vector — see coding-docs/query-result-tabs) follow this exact pattern: cheap `appliesTo` sniffing in the shell, `loader: () => import(...)` on first activation."*

### 1.3 The bundle-budget tripwire (BOOT-3)

`test/unit/queryStudioBundleBudget.test.ts` — fails the suite if a heavy package re-enters the entry's static closure:
- `ENTRY = "dist/views/queryStudio.js"` (:26). Walks the metafile static closure (`kind === "import-statement"`, :70–85).
- `DENYLIST` (:34–53) already contains **forward-looking entries for our feature**: `"maplibre-gl"`, `"leaflet"`, `"deck.gl"`, `"@deck.gl"`, `"plotly"`, `"chart.js"`, `"echarts"`, `"three"`, `"cesium"`, `"@arcgis"`, `"d3"` — plus existing `"azdataGraph"`, `"@slickgrid-universal"`, `"slickgrid-react"`, `"sortablejs"`, `"multiple-select-vanilla"`, `"vanilla-calendar-pro"`. Comment: *"grow this list, never shrink it"*.
- Ceilings: `CLOSURE_CODE_BYTES_CEILING = 11.5 MB` (:56), `CLOSURE_CHUNK_CEILING = 20` chunks (:58).
- CSS-only inputs are exempt (:105–111) because lib CSS is deliberately hoisted statically (see §7).
- Requires `npm run build:webviews-bundle` first (reads `webviews-metafile.json` at repo-extension root).

**Consequence for the new panes**: any spatial/vector rendering library MUST come in via `() => import(...)` inside a lazy module analogous to `lazyResults.tsx`, or the suite fails by name.

---

## 2. lazyResults.tsx — the lazy-loading mechanism in detail

File: `webviews/pages/QueryStudio/lazyResults.tsx` (110 lines). Mechanism = **`React.lazy` over esbuild code-split dynamic imports**, plus a hand-rolled idle prefetch and honesty flags:

- Module thunks (:28–30): `const resultsModule = () => import("./results"); const gridModule = () => import("./resultsGrid"); const planModule = () => import("./queryPlanTab");`
- State flags (:32–34): `gridPrefetchStarted`, `gridLoaded`, `renderWaitedForChunk` (module-scoped booleans).
- `prefetchGridStack()` (:37–61): one-shot; kicks via `requestIdleCallback(kick, { timeout: 1_000 })` with a `setTimeout(kick, 50)` fallback. Emits `perfMark("mssql.queryStudio.boot.gridChunkRequested")`, then `Promise.all([resultsModule(), gridModule()])`, then `perfMark("mssql.queryStudio.boot.gridChunkLoaded", { waitedForByRender: renderWaitedForChunk })`.
- `gridStackLoaded(): boolean` (:64–66) — true once resident (render never suspends then).
- `whenGridStackLoaded(): Promise<void>` (:73–79) — resolves when resident, starting the load if needed. Used to keep the `resultsRendered` perf mark honest (must wait for the REAL grid paint, never the Suspense placeholder — see §6).
- Lazy components (:81–97):
  - `export const LazyResultGridBlock = React.lazy(async () => ({ default: (await resultsModule()).ResultGridBlock }));`
  - `export const LazyMessagesView = React.lazy(async () => ({ default: (await resultsModule()).MessagesView }));`
  - `export const LazyQsResultsGridProvider = React.lazy(async () => ({ default: (await gridModule()).QsResultsGridProvider }));`
  - `export const LazyExecutionPlanView = React.lazy(async () => { const module = await planModule(); perfMark("mssql.queryStudio.boot.planChunkLoaded", {}); return { default: module.QueryStudioExecutionPlanView }; });` ← **the P2 precedent: perf mark fires inside the lazy factory on first chunk load.**
- `ResultsSurfaceLoading()` (:100–110): the shared Suspense fallback. Renders `<div className="qs-muted qs-results-surface-loading">Loading results view…</div>`; side effects: sets `renderWaitedForChunk = true` and kicks `prefetchGridStack()` if not already in flight (render can precede the idle-prefetch kick when autoRun results land fast).

**CSS stranding rule**: lazy chunks never carry their own lib CSS. All grid CSS is hoisted statically in `app.tsx:89–92` (see §7) so dynamic chunks can't strand styles or scramble cascade order.

---

## 3. Tab model in the shell (app.tsx) — the precedent for contributed panes

### 3.1 State

- `type QueryStudioTab = "results" | "messages" | "queryPlan";` (app.tsx:122) — a plain string union; **there is no registry/array of tab descriptors today**. New panes extend this union or replace it with a registered-pane model.
- `const [activeTab, setActiveTab] = useState<QueryStudioTab>("results");` (app.tsx:192).
- Plan tab has its own fetched state: `interface QueryPlanTabState { readonly key: string; readonly executionPlanState: ExecutionPlanState; }` (app.tsx:124–127), held in `queryPlanTabState` (app.tsx:193–195).

### 3.2 How the Query Plan tab is conditionally added (copy this pattern)

1. **Cheap sniffing from coarse state** (app.tsx:1374–1405): `allResultSetSummaries = results?.resultSets ?? []`; split into `resultSetSummaries` (`summary.isPlanResult !== true`) and `planResultSetSummaries` (`isPlanResult === true`). `hasPlanResults = planResultSetSummaries.length > 0`. This is the `appliesTo` sniff — a boolean per-summary flag on `QsResultSetSummary` (`isPlanResult?: boolean`, sharedInterfaces/queryStudio.ts:138). A vector/spatial pane needs an equivalent cheap flag or column-metadata sniff (e.g. over `QsResultColumn.sqlType`) — never a data fetch.
2. **Fallback routing** (`visibleActiveTab`, app.tsx:1386–1393): if `activeTab === "queryPlan"` but `!hasPlanResults`, fall back to `"results"` or `"messages"`. Also a guard effect (app.tsx:1502–1506) resets `activeTab` when plan sets disappear.
3. **Tab button rendered conditionally** (app.tsx:1715–1726): inside `<div className="qs-results-tabs" role="tablist">` (:1694), `{hasPlanResults ? <button role="tab" aria-selected={...} className={`qs-tab ${active ? "active" : ""}`} onClick={() => setActiveTab("queryPlan")}>Query Plan{count > 1 ? ` (${n})` : ""}</button> : null}`.
4. **Body rendered lazily on activation** (app.tsx:1868–1876): `visibleActiveTab === "queryPlan" ? <React.Suspense fallback={<ResultsSurfaceLoading />}><LazyExecutionPlanView rpc={rpc} executionPlanState={queryPlanTabState?.executionPlanState} /></React.Suspense> : ...` — comment: *"BOOT-2/P2: azdataGraph loads on FIRST plan-tab activation only — never at init."* Note: the tab body is **unmounted** when another tab is active (unlike maximized-grid hiding which keeps grids mounted with `.qs-grid-hidden`).
5. **Pane data fetched by effect keyed on the run + set ids** (app.tsx:1439–1501): keyed by `planResultSetKey = `${runId ?? "idle"}:${planResultSetIdsKey}`` (:1398–1401); waits for `planRowsAvailable` (every plan set has rows or is complete, :1402–1406); posts `QsGetPlanStateRequest` with `{ resultSetIds }`, sets Loading/Error `ApiStatus` states; cancels via a `canceled` closure flag on cleanup. Empty plan sets clear the tab state (:1440–1443).
6. **Auto-focus once per run** (app.tsx:665–674): plan-mode runs (armed via `planRunArmedRef`, set in `execute`/`estimatedPlan` at :832/:930) focus the tab exactly once when `executionKind === "succeeded"` and `state.results.planCount > 0`, tracked by `planTabFocusRef` (:242).
7. **Per-run reset** (`resetRunViewForStart`, app.tsx:275–297): sets `setActiveTab("results")`, clears `liveRowCounts`, `messages`, `queryPlanTabState`, `maximizedGridId`, un-collapses results. A new contributed pane's per-run state must be reset here too.
8. **Tabbar contextual actions** (app.tsx:1727–1793): buttons shown per active tab — pin-all + grid/text toggle for `"results"`, "Open in New Tab" (`QsOpenPlanRequest`) for `"queryPlan"`, plus the always-present maximize/restore pane button. Class `qs-tabbar-btn`.

### 3.3 Results region structure

Rendered only when `showResults` (`results?.present && !resultsCollapsed`, app.tsx:1365): splitter (`.qs-splitter`, drag handler :1336–1355) → `.qs-results` (flexBasis `${resultsHeightPct}%`) → `.qs-results-tabs` (role=tablist, 30px) → `.qs-results-body` (`ref={resultsBodyRef}`, measured by ResizeObserver :1427–1438; gets `.qs-results-body-fill` when one surface fills the pane — `resultsFillActive` includes `visibleActiveTab === "queryPlan"` at :1411–1415 — a full-pane vector/spatial pane should join this condition). Layout metrics constants: `GRID_HEADER_PX = 34`, `GRID_CHROME_PX = 20`, `GRID_CAPTION_PX = 30` (app.tsx:150–152).

### 3.4 Stacked grid sizing (results tab)

`computeResultsLayout(rowCounts, paneHeight - 8, { rowHeight: qsGridRowHeight(state?.gridStyle), headerHeight, chromePx, captionPx })` (app.tsx:1416–1426) from `sharedInterfaces/queryStudioResultsLayout.ts` (pure, webview-safe, unit-tested). Exports: `QS_MIN_GRID_ROWS = 12`, `QS_MIN_VISIBLE_GRID_ROWS = 1`, `QS_FALLBACK_GRID_ROWS = 14`, `QsResultsLayoutMetrics`, `type QsGridSizing = { kind: "fill" } | { kind: "height"; bodyPx: number }`, `QsResultsLayout { sizing; paneScrolls }`, `qsGridContentHeight()`. Rules (:6–22): 1 grid → fill (grid scrollbar IS the scrollbar); all fit → exact content heights; else fair-share with 12-row minimum; pane scrolls only when minimums overflow. `qsGridRowHeight(gridStyle) = (fontSize ?? 12) + 6 + 2*rowPadding` (resultsGridShared.ts:27–30).

---

## 4. State management pattern

- **No redux/zustand.** Two layers:
  1. `VscodeWebviewProvider` (`webviews/common/vscodeWebviewProvider.tsx`) — context with `{ vscodeApi, extensionRpc, getSnapshot, subscribe, themeKind, keyBindings, localization, EOL }` (:38–70). State lives in a `stateRef` + listener set; consumed via `useSyncExternalStore(subscribe, getSnapshot)` (app.tsx:182). Bootstrap (:120–211): registers `initPerfMarks`, `ColorThemeChangeNotification`, `StateChangeNotification`, `KeyBindingsChangeNotification` handlers FIRST, then awaits `GetStateRequest` (first-paint gate), then keybindings + EOL, sets `isBootstrapComplete`; theme/localization load non-blocking; children render only after bootstrap (:231–234). Wraps children in Fluent UI `FluentProvider` with `webviewTheme(theme)`.
  2. **QS coarse state** `QsState` — pushed both through the base `StateChangeNotification` (webviewBaseController.ts:665–667, `set state`) and `QsStateChangedNotification` ("qs/stateChanged"). Host debounces via `queueStatePush()` (queryStudioController.ts:620–637, min interval → ≤10/s). App resolution (app.tsx:183–185): `providerState = isQueryStudioState(snapshot) ? snapshot : undefined; state = providerState ?? pushedState` where `pushedState` is set by the `QsStateChangedNotification` handler (app.tsx:544–546). `isQueryStudioState` checks `schemaVersion`/`connection`/`results` keys (app.tsx:2047–2055).
- Everything else is local `useState`/`useRef` in `QueryStudioApp` (activeTab, liveRowCounts, messages, split %, maximizedGridId, actionHint, etc.).
- **Cardinal data rule** (sharedInterfaces/queryStudio.ts:6–11 header): *"row data NEVER rides coarse state (QsRowsAppended carries counts only — addendum §3.6; rows cross only via QsGetRows in the compact window shape, Appendix A)."* `QsRowsAppendedNotification` ("qs/rowsAppended") carries `{ resultSetId, newRowCount, complete }`; the webview accumulates `liveRowCounts` (app.tsx:547–555) and uses `effectiveRowCount = max(summary.rowCount, liveRowCounts[id])` (app.tsx:1375–1376) so grids grow smoothly between debounced state pushes.

---

## 5. Data plane: how rows/columns reach a pane

### 5.1 Types (sharedInterfaces/queryStudio.ts — verbatim)

- `QsResultSetSummary` (:129–139): `{ resultSetId: string; batchOrdinal: number; columnNames: string[]; columns?: QsResultColumn[]; rowCount: number; complete: boolean; truncatedReason?: string; corrupt?: boolean; isPlanResult?: boolean }`. `resultSetId` is shaped `"b0r0s0"`; ordinal parsed via `resultSetId.split("s").pop()` (resultsGrid.tsx:178–181).
- `QsResultColumn` (:238–244): `{ name: string; displayName: string; sqlType?: string; isXml?: boolean; isJson?: boolean }` — **this is ALL the column metadata the webview has today.** A vector/spatial `appliesTo` sniff has `sqlType` (e.g. detect `vector`, `geometry`, `geography`) plus `columnNames`. If more is needed (dimensions, SRID), extend `QsResultColumn` or add typeHints.
- `QsCellWindow` (:247–256): `{ resultSetId; start; rowCount; columns: QsResultColumn[]; values: unknown[][]; nullBitmap?: string; typeHints?: string[]; truncatedBitmap?: string }` — "Compact window (Appendix A): values + null bitmap, never tagged unions." `nullBitmap` is base64; decode pattern `windowNullFlags()` at resultsGrid.tsx:101–116 (bit index = `row * colCount + col`, tested `(bytes.charCodeAt(index>>3) & (1 << (index & 7))) !== 0`); duplicated in resultsTextView.tsx:183–198.
- `QsGetRowsParams` (:217–227): `{ resultSetId; start; count; columnStart?; columnCount? }` — column projection (QO-7b) so a pane reading only 1–2 columns (e.g. the vector column) can avoid dragging the other columns across the RPC.
- Cell value decoding lives in `sharedInterfaces/queryStudioGridOps.ts` (pure, webview-safe): `cellDisplayText(value)` (:153–174; NULL→"NULL", bit→"0"/"1", typed wire wrappers `{ $t, v }` via `isTypedCellWrapper` :61–69 — datetime2/datetimeoffset/time/decimal/guid/binary/double/provider; truncation markers `{ $t: "truncated", of?, bytes?, v }` via `isTruncatedCellMarker` :44–53), `cellDocumentLanguage()` (:236–252, metadata wins, then shape+parse sniff capped at `QS_CELL_DOCUMENT_PARSE_LIMIT = 256*1024`), `clampDisplay(text, QS_CELL_DISPLAY_CLAMP /* 2048 */)`, `compareCells`, `applyFilterSort` (returns ORIGINAL row indices, stable), `distinctValues` (cap `QS_DISTINCT_VALUES_CAP = 200`). **Important for vector data**: raw wire values for float arrays likely arrive as strings/JSON — check the actual `sqlType`/typeHint of vector columns; typeHints are `"number"` / `"number:approx"` for numeric ordering (queryStudioGridOps.ts:320–323).

### 5.2 Fetch pattern (grid precedent, resultsGrid.tsx)

- `dataSource` (:601–643): `{ kind: "windowed", rowCount, getRows: async (offset, count) => rpc.sendRequest(QsGetRowsRequest.type, { resultSetId, start, count }) → windowToGridRows(window, columnCount) }`. Every window fetch is bracketed with perf marks (see §6).
- Host side: `QsGetRowsRequest` handler (queryStudioController.ts:775–785) → `this.model.executionHost.getRows(resultSetId, start, count, "grid", columnProjection?)` → backed by `queryStudio/rowStore.ts` (host-side row storage; the webview never sees it directly — **all row access is via `qs/getRows` windows**).
- Copy path: chunked fetches `COPY_CHUNK = 512`, guard `COPY_MAX_ROWS = 100_000` (resultsGrid.tsx:84–86), column-projected (:196–216), TSV with SSMS union semantics for multi-range (:235–330).
- Text view: chunked `TEXT_VIEW_CHUNK = 5000`, display cap `textViewMaxRows` (default 100_000) with a visible truncation line, width sample `textViewSampleRows` (default 1000) (resultsTextView.tsx:21–24, 96–148).
- Windowing knobs ride `QsGridStyle` (see §7): `gridWindowMode: "fixed" | "adaptive"`, `gridWindowRows` (default 50), `gridPrefetchFactor` (default 2), `gridMaxWindowRows` (default 1000); adaptive window = `min(maxRows, max(baseRows, visibleRows * (1 + prefetch)))`, computed once per mount (resultsGrid.tsx:781–797).

### 5.3 Lazy mounting inside the results tab (second-tier laziness)

`ResultGridBlock` (results.tsx:196–257): caption always renders; grid body mounts only when the block comes within ~1.5 viewports of `.qs-results-body` (IntersectionObserver, `rootMargin: "150% 0px"`, root = `el.closest(".qs-results-body")`) — and **never unmounts**. Placeholder `.qs-grid-placeholder` reserves `sizing.bodyPx` height so scroll geometry stays stable. Fill-mode grids always mount (:207–234). Hidden-not-unmounted while another grid is maximized: `.qs-grid-hidden { display: none }` (queryStudio.css:355–357).

---

## 6. Messaging + timing/metric instrumentation

### 6.1 RPC surface

- Webview side: `useVscodeWebview<QsState, void>()` → `extensionRpc` (`WebviewRpc`, `webviews/common/rpc.ts`): `sendRequest(type, params, token?)`, `sendNotification(type, params)`, `onNotification(type, handler)` over `vscode-jsonrpc` types. Panes receive a minimal structural `Rpc` prop instead of the full context: `export interface Rpc { sendRequest<P, R>(type: { method: string }, params: P): Promise<R> }` (resultsGridShared.ts:17–19) — **light**, importable by the entry chunk (resultsGridShared is the BOOT-2 seam: *"nothing in this file may import slickgrid/FluentResultGrid, ever"*, :6–13).
- Message contracts are `namespace X { export const type = new RequestType<P, R, void>("qs/...") }` in `sharedInterfaces/queryStudio.ts`. Full request list relevant to panes: `QsGetRowsRequest` "qs/getRows", `QsGetPlanStateRequest` "qs/getPlanState", `QsOpenPlanRequest` "qs/openPlan", `QsOpenCellDocumentRequest` "qs/openCellDocument", `QsSaveResultRequest` "qs/saveResult", `QsUpdateGridSelectionRequest` "qs/updateGridSelection", `QsGetMessagesRequest` "qs/getMessages", `QsGetMessagesTextRequest` "qs/getMessagesText", `QsNavigateToLineRequest` "qs/navigateToLine", `QsSetViewModeRequest` "qs/setViewMode", `QsPinResultSetRequest` "qs/pinResultSet", `QsPinAllResultsRequest` "qs/pinAllResults", `QsExecuteRequest` "qs/execute", `QsGetDiagnosticsSummaryRequest` "qs/getDiagnosticsSummary". Notifications (host→webview): `QsStateChangedNotification` "qs/stateChanged", `QsRunStartedNotification` "qs/runStarted", `QsRowsAppendedNotification` "qs/rowsAppended", `QsResultSetStartedNotification` "qs/resultSetStarted", `QsResultSetEndedNotification` "qs/resultSetEnded", `QsMessagesAppendedNotification` "qs/messagesAppended" (position-addressed `{ startIndex, messages }`), `QsToastNotification` "qs/toast", plus the QsSync* text-sync family.
- Response conventions: guarded actions return `{ started: boolean; reason?: string }` / `{ opened: boolean; error?: string }` — **refusals must surface** (the `actionHint` status-line pattern, app.tsx:210–213, 820–822, 958–971: "a guard reason must never look like a dead button").

### 6.2 Perf marks (Debug Console / harness timing)

`webviews/common/perfMarks.ts`: `perfMark(name, attrs?)`, `perfMarkAfterNextPaint(name, attrs?)` (double-rAF, 500ms fallback adds `rafThrottled: true` for hidden webviews), `perfMarksEnabled()`. Disabled by default; enabled when the controller sends `PerfEnableNotification` (under PERF_MODE=1 **or when any diag sink is active** — webviewBaseController.ts:193–213 checks `Perf.enabled || diag.anySinkActive`, with retries at 500/2000/5000/15000/30000ms + 20s poll). Pre-enable marks queue (bounded 50) with original timestamps. Marks travel as `PerfWebviewMarkNotification`.

Existing QS mark names (the naming convention to extend):
- Boot: `mssql.queryStudio.boot.scriptStart`, `.boot.reactMount` (index.tsx:17,24); `.boot.monacoReady`, `.boot.editorInteractive` (paint) (app.tsx:705–706); `.boot.gridChunkRequested`, `.boot.gridChunkLoaded {waitedForByRender}` (lazyResults.tsx:43–48); `.boot.planChunkLoaded` (lazyResults.tsx:95).
- Run: `mssql.queryStudio.resultsRendered {status, rows, resultSets}` after terminal paint — **gated on `whenGridStackLoaded()` when result sets exist and the chunk isn't resident** so the mark never fires on the Suspense placeholder (app.tsx:632–648; "the first live run proved the mark drifted 120ms early without this gate").
- Grid data: `mssql.queryStudio.grid.window.request {resultSetId,start,count}`, `.grid.window.received {…,ms}`, `.grid.firstVisibleRowsPainted {resultSetId,rows,columns}` (resultsGrid.tsx:607–637); `mssql.queryStudio.messagesPrepared {messages,visibleRows,durationMs}`, `.messagesRendered` (results.tsx:371–387); `mssql.queryStudio.textView.capped` (resultsTextView.tsx:118).
- Pattern for guarding cost: `const perfEnabled = perfMarksEnabled(); const startedAt = perfEnabled ? performance.now() : 0;` — every call is an inert boolean check outside perf mode.

A new pane should mint: `mssql.queryStudio.boot.<pane>ChunkLoaded` (inside the React.lazy factory), `mssql.queryStudio.<pane>.window.request/received`, `mssql.queryStudio.<pane>.firstPainted` (via `perfMarkAfterNextPaint`).

### 6.3 session-diag (host side)

Host controller uses `import { diag } from "../diagnostics/diagnosticsCore"` (queryStudioController.ts:16): `diag.emit({ feature: "queryStudio", type: "queryStudio.dbSwitch", status, fields: { ms: { raw, cls: "diagnostic.metadata" }, ... } })` (:743–756) and `diag.startSpan({ feature, kind: "span", type: "queryStudio.inlineCompletion.bridge", fields })` → `span.end("ok", fields)` (:981–996). New pane host handlers (e.g. a `qs/getVectorData` request) should wrap in the same span/emit pattern. (Detailed observability contract is another reader's brief.)

---

## 7. Styling system

- **Plain CSS with VS Code theme tokens only** — no CSS-in-JS for QS chrome. `queryStudio.css` header (:1–2): *"toolbar 35px, status 24px, 2px radii max, VS Code tokens only, no ornamental chrome."* Tokens in use: `--vscode-editor-background`, `--vscode-foreground`, `--vscode-editorWidget-background/-border`, `--vscode-descriptionForeground`, `--vscode-focusBorder`, `--vscode-toolbar-hoverBackground`, `--vscode-button-background/-foreground`, `--vscode-statusBar-*`, `--vscode-statusBarItem-error/warningBackground`, `--vscode-list-hover/activeSelection*`, `--vscode-inputOption-active*`, `--vscode-textLink-foreground/-activeForeground`, `--vscode-errorForeground`, `--vscode-editorWarning-foreground`, `--vscode-panel-border`, `--vscode-editor-font-family/-size`, `--vscode-font-family`, `--vscode-disabledForeground`. Grid-specific vars: `--fluent-result-grid-row-even/odd-background`, `--fluent-result-grid-foreground`, `--fluent-result-grid-null-cell-*`, `--fluent-result-grid-table-header-foreground`.
- Class naming: `qs-` prefix. Key hooks for a new pane: `.qs-results-tabs`, `.qs-tab` / `.qs-tab.active` (active = `border-bottom: 2px solid var(--vscode-focusBorder)`), `.qs-tab.has-errors`, `.qs-tabbar-btn`, `.qs-results-body` / `.qs-results-body-fill`, `.qs-query-plan-view` (the plan pane's full-height wrapper, css:232–236 — model for `.qs-vector-view`/`.qs-spatial-view`), `.qs-muted`, `.qs-grid-notice`, `.qs-grid-placeholder`, `.qs-results-surface-loading` (Suspense fallback).
- Theme kind reaches components via `themeKind: ColorThemeKind` from `useVscodeWebview()`; grid maps it to `FluentResultGridTheme["kind"]`: `"dark" | "highContrast" | "highContrastLight" | "light"` (`toFluentThemeKind`, resultsGrid.tsx:518–529). Fluent UI provider theme via `webviewTheme(theme)` (vscodeWebviewProvider.tsx:230).
- **CSS hoist + cascade-order rule** (app.tsx:82–92, verbatim comment): grid/plan CSS is imported STATICALLY in app.tsx even though the JS is lazy — *"Their CSS is hoisted here statically so lazy chunks never strand styles. ORDER IS THE CASCADE … the slickgrid THEME must load BEFORE our FluentResultGrid overrides … Keep lib css first, ours after."* Imports in order: `@slickgrid-universal/common/dist/styles/css/slickgrid-theme-fluent.css`, `../../common/FluentResultGrid/FluentResultGrid.css`, `FluentResultGrid.vscode.css`, `../../media/table.css`. **A new pane's heavy-lib CSS must be hoisted the same way (statically in app.tsx, lib css before overrides); CSS is exempt from the bundle-budget denylist.**
- Icons: codicons via `<span className="codicon codicon-<name>" />`.
- Grid font/config snapshot: `QsGridStyle` on `QsState.gridStyle` (sharedInterfaces/queryStudio.ts:158–187) — `fontFamily`, `fontSize`, `alternatingRowColors`, `showGridLines: QsGridLinesMode ("both"|"horizontal"|"vertical"|"none")`, `rowPadding`, `inMemoryDataProcessingThreshold` (classic `mssql.resultsGrid.inMemoryDataProcessingThreshold`), `gridWindowMode/Rows/PrefetchFactor/MaxWindowRows`, `textViewMaxRows/SampleRows`, `autosizeSampleRows`, `gridMaxColumnWidthPx`, `resultsPaneHeightPct` (config `mssql.queryStudio.resultsPaneHeightPercent`, app.tsx:198–201). Host builder: `queryStudio/gridStyle.ts`.

---

## 8. Exactly where and how a new lazily-contributed pane plugs in

Minimal-change recipe (mirrors queryPlan end to end):

1. **New pane module** `webviews/pages/QueryStudio/vectorTab.tsx` (analog: `queryPlanTab.tsx`, 58 lines) — exports one component taking `{ rpc: Rpc, ... }` with `Rpc` imported **from `./resultsGridShared`** (type-only, light). Heavy viz lib is imported only inside this module (or deeper), so it lands in the dynamic chunk.
2. **lazyResults.tsx**: add `const vectorModule = () => import("./vectorTab");` and `export const LazyVectorView = React.lazy(async () => { const m = await vectorModule(); perfMark("mssql.queryStudio.boot.vectorChunkLoaded", {}); return { default: m.QueryStudioVectorView }; });` — P2, no prefetch (or an idle prefetch gated on `appliesTo` if warm-load is wanted).
3. **app.tsx**:
   - extend `type QueryStudioTab` (app.tsx:122);
   - compute the sniff from `state.results.resultSets[i].columns` (`QsResultColumn.sqlType`) — cheap, synchronous, per state push (mirror `planResultSetSummaries` at :1380–1382);
   - add fallback routing to `visibleActiveTab` (:1386–1393) and the disappearing-sets guard (:1502–1506);
   - add the `<button role="tab" className="qs-tab">` in the tablist (:1715–1726 pattern);
   - add the body branch under `.qs-results-body` wrapped in `<React.Suspense fallback={<ResultsSurfaceLoading />}>` (:1868–1876 pattern); include the tab in `resultsFillActive` (:1411–1415) if full-pane;
   - reset any per-run pane state in `resetRunViewForStart` (:275–297);
   - if the pane needs host-prepared data, mirror the `QsGetPlanStateRequest` effect (:1439–1501): keyed on `${runId}:${setIdsKey}`, gated on rows-available, cancelable.
   - hoist the pane's lib CSS statically next to app.tsx:89–92 (lib css first).
4. **sharedInterfaces/queryStudio.ts**: add `QsGetXxxRequest` namespaces ("qs/..." method names); if sniffing needs richer column metadata, extend `QsResultColumn` (additive, `schemaVersion` gate available via `QS_SCHEMA_VERSION = 1`).
5. **Host**: register `this.onRequest(...)` in `queryStudioController.registerHandlers()` (queryStudioController.ts:639+), delegate to `executionHost.getRows(...)`/rowStore, wrap in `diag.startSpan`/`diag.emit` with `feature: "queryStudio"`.
6. **Budget test**: the new lib is already (or must be added) in `DENYLIST` (queryStudioBundleBudget.test.ts:34–53) — maplibre-gl/leaflet/deck.gl/plotly/chart.js/echarts/three/cesium/@arcgis/d3 are pre-listed; add anything else you pull in. Rebuild `npm run build:webviews-bundle` before running the suite.

Perf invariants to preserve: zero new bytes in the entry static closure (test-enforced); tab button + sniff cost only when unused; `resultsRendered` honesty (if the new pane can be the terminal focus target, gate the mark on its chunk like `whenGridStackLoaded()` at app.tsx:642–648); data via bounded `qs/getRows` windows with column projection — never rows over notifications, never unbounded fetches.
