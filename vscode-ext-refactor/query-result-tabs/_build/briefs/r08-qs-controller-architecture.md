# R08 — Query Studio Extension-Side Controller Architecture

Reader brief for the result-tab panes build (vector debugger + spatial visualizer). All paths
relative to `C:/repos/test/vscode-mssql/extensions/mssql/src/` unless noted. Line refs verified
2026-07-11 on branch `dev/query`.

---

## 1. Big picture: object graph and ownership

```
QueryStudioEditorProvider (1 per extension)           queryStudioEditorProvider.ts:76
  └─ QueryStudioDocumentModel (1 per document URI)    queryStudioDocumentModel.ts:41
       ├─ DocumentSessionBinding (data-plane session) documentSessionBinding.ts:70
       ├─ ExecutionHost (run state, shared)           executionHost.ts:44
       │    ├─ RowStore (per RUN, fresh each run)     rowStore.ts:120
       │    ├─ RetainedRowStore (lease wrapper, C2D)  queryResults/resultStoreLease.ts:54
       │    └─ ExecutionOrchestrator (per run)        executionOrchestrator.ts:141
       ├─ QueryStudioLiveResultSource (C2D adapter)   queryStudioLiveResultSource.ts:28
       └─ N × QueryStudioController (1 per PANEL)     queryStudioController.ts:117
            └─ WebviewBaseController<QsState, void>   controllers/webviewBaseController.ts:119
```

- **Model is shared per URI; controller is per webview panel.** Multiple panels of the same
  document attach to one model and share connection/results (`supportsMultipleEditorsPerDocument:
  true`, queryStudioEditorProvider.ts:373). Per-panel UI state (viewMode, actualPlan toggle) lives
  on the controller (queryStudioController.ts:138-139); per-document state (sqlcmdEnabled,
  openScanCompleted) lives on the host/model.
- **New pane state placement rule**: anything that must survive a panel split or be consistent
  across panels goes on `QueryStudioDocumentModel`/`ExecutionHost`; anything view-local (which tab
  is open, pane scroll position) stays webview-side or on the controller.

---

## 2. Lifecycle of a QS document + webview

### Registration (feature gate)
- `registerQueryStudio(context)` — queryStudioEditorProvider.ts:341. Gated on config key
  **`mssql.queryStudio.enabled`** (default false); a config watcher registers late without reload
  (lines 348-354).
- `registerQueryStudioFeatures` (line 360) registers: perf probes, active-editor redirect, Save As
  continuity, query-results lifecycle (C2D), `.mssql` file association, definition provider, and
  the custom editor:
  ```ts
  vscode.window.registerCustomEditorProvider(QUERY_STUDIO_VIEW_TYPE, provider, {
      webviewOptions: { retainContextWhenHidden: true },
      supportsMultipleEditorsPerDocument: true,
  })
  ```
  `QUERY_STUDIO_VIEW_TYPE = "mssql.queryStudio"` (queryStudioEditorProvider.ts:40).
  **`retainContextWhenHidden: true`** — the webview is never torn down while hidden; panes keep
  their DOM. Lazy-load cost is therefore paid at most once per panel.

### Resolve (per panel open)
`QueryStudioEditorProvider.resolveCustomTextEditor` (queryStudioEditorProvider.ts:85-174):
1. `Perf.marker("mssql.queryStudio.open.begin", "begin")` (line 90) — the open marker starts here.
2. Hot-exit backup restore; `diag.emit` event `queryStudio.open.resolve` (line 95).
3. Model lookup by `uriKey = document.uri.toString()`: reuse / Save-As transplant
   (`pendingModelTransplants`, line 60) / create new. Spill root:
   `globalStorage/querystudio-spill/<base64url(uriKey).slice(0,32)>` (lines 128-132).
4. `model.panelCount++`; `new QueryStudioController(context, panel, model)` (line 145); track in
   module-level `liveControllers` set and `liveModels` map (lines 44-47 — the lookup seams).
5. `panel.onDidDispose` (line 159): dispose controller, decrement `panelCount`, and when it hits 0
   dispose the model (session close, RowStore/spill cleanup).

### Controller construction (queryStudioController.ts:150-310)
1. `super(context, "queryStudio", initialState, "queryStudio")` — the `_sourceFile` string
   `"queryStudio"` selects the webview bundle `dist/views/queryStudio.js` + `.css` in
   `_getHtmlTemplate` (webviewBaseController.ts:241-280) and prefixes every auto diag span.
2. Sets `panel.webview.options` + `panel.webview.html = this._getHtmlTemplate()` — QS overrides
   `_getHtmlTemplate` (queryStudioController.ts:361-375) to inject a **boot-error relay** script
   (posts `{type: "qsBootError"}` messages before the bundle loads; handled at line 168).
3. **`this.updateConnectionWebview(this.panel.webview)`** (line 166) — CRITICAL: a custom text
   editor receives its panel from VS Code, so it must bind the vscode-jsonrpc reader/writer to
   the provided webview explicitly; otherwise every message drops with "webview is not set"
   (webviewBaseController.ts:221-226 / 93-110).
4. `initializeBase()` (webviewBaseController.ts:228) — registers default handlers
   (`GetStateRequest`, `GetThemeRequest`, `GetLocalizationRequest`, `ExecuteCommandRequest`,
   `ReducerRequest`, `GetEOLRequest`, theming, keybindings) and the perf-mark bridge.
5. `registerHandlers()` (queryStudioController.ts:639) — all `qs/*` request handlers (§3).
6. Attaches: model text-sync listener (line 232), sessionBinding change → `queueStatePush`
   (line 242), and `executionHost.attach({...})` (lines 244-305) for run fan-out.
7. Sends `QsSyncInitNotification` + first state push (lines 308-309).

### Webview-ready signal / open marker end
The webview's first `QsGetDiagnosticsSummaryRequest` ends the open marker
(queryStudioController.ts:658-670):
```ts
Perf.marker("mssql.queryStudio.open.end", "end", { fromCache: false });
this.scheduleOpenScan();   // idle scan 1500ms later (OPEN_SCAN_DELAY_MS, line 115)
```
This is the pattern for "document open" performance measurement — **new panes must not add work
before this point** (zero-impact-when-unused requirement).

### Dispose
`QueryStudioController.dispose` (line 1153): clears statePush/rows/messages timers, cancels
inline-completion CTS, disposes language service + listeners, then `super.dispose()`.
Model dispose (queryStudioDocumentModel.ts:465): live-source deregistration, context clear,
`executionHost.dispose()` (releases live lease → RowStore + spill delete unless snapshots hold
leases), `sessionBinding.dispose()`.

---

## 3. Message protocol and handler registration (exact names)

### Contract module
All webview↔host contracts live in **`sharedInterfaces/queryStudio.ts`** as `vscode-jsonrpc`
`RequestType`/`NotificationType` namespaces. `QS_SCHEMA_VERSION = 1` (line 16). Design rule
(header, lines 6-11): **coarse state pushes + hot-path RPCs; row data NEVER rides notifications**
— `QsRowsAppendedNotification` carries counts only; rows cross only via `QsGetRows`.

### Registration pattern (host side)
```ts
this.onRequest(QsGetRowsRequest.type, async (params) => this.model.executionHost.getRows(...));
void this.sendNotification(QsStateChangedNotification.type, next);
```
`onRequest` (webviewBaseController.ts:492-573) wraps every handler with: a debug log, a telemetry
activity (`TelemetryViews.WebviewController` / `OnRequest`), and — when any diagnostics sink is
active — a diag span `webview.queryStudio.<method>` (line 521). **Every new pane RPC is therefore
automatically timed in the Debug Console / session-diag with zero extra code**; add domain-level
`Perf.marker` / `diag.startSpan` inside the handler for detail beyond method-level spans.

### Requests (webview → host), method strings verbatim
| Namespace | method | shape |
|---|---|---|
| `QsSyncEditsRequest` | `qs/syncEdits` | `QsSyncEdits → QsSyncEditsResult` |
| `QsShowCommandPaletteRequest` | `qs/showCommandPalette` | void |
| `QsSyncAdoptRequest` | `qs/syncAdopt` | `{text, editGroupId}` |
| `QsSyncResyncRequest` | `qs/syncResyncRequest` | `{webviewVersion, textHash} → QsSyncResync` |
| `QsSyncUndoRequest` | `qs/syncUndo` | `{redo}` |
| `QsSyncSaveRequest` | `qs/syncSave` | void |
| `QsExecuteRequest` | `qs/execute` | `QsExecuteParams → {started, reason?}` |
| `QsCancelRequest` | `qs/cancel` | `→ {acknowledged}` |
| `QsConnectRequest` | `qs/connect` | `→ {connected}` |
| `QsDisconnectRequest` | `qs/disconnect` | `→ {disconnected}` |
| `QsReconnectRequest` | `qs/reconnect` | `→ {connected}` |
| `QsSetDatabaseRequest` | `qs/setDatabase` | `{database} → {changed, reason?}` |
| `QsListDatabasesRequest` | `qs/listDatabases` | `→ {databases}` |
| `QsGetRowsRequest` | `qs/getRows` | `QsGetRowsParams → QsCellWindow` |
| `QsSaveResultRequest` | `qs/saveResult` | `{resultSetId, format, selection?}` |
| `QsOpenCellDocumentRequest` | `qs/openCellDocument` | `{resultSetId, row, column, format: "xml"\|"json"\|"text"} → {opened}` |
| `QsOpenPlanRequest` | `qs/openPlan` | `{resultSetId} → {opened}` |
| `QsGetPlanStateRequest` | `qs/getPlanState` | `{resultSetIds} → {executionPlanState?, error?}` |
| `QsSaveExecutionPlanRequest` | `qs/saveExecutionPlan` | `{sqlPlanContent}` |
| `QsShowPlanXmlRequest` | `qs/showPlanXml` | `{sqlPlanContent}` |
| `QsShowPlanQueryRequest` | `qs/showPlanQuery` | `{query}` |
| `QsGetMessagesRequest` | `qs/getMessages` | `{afterIndex?} → {messages}` |
| `QsGetMessagesTextRequest` | `qs/getMessagesText` | `→ {text}` (host joins; QO-7) |
| `QsNavigateToLineRequest` | `qs/navigateToLine` | `{line, column?}` |
| `QsSetViewModeRequest` | `qs/setViewMode` | `{viewMode: "grid"\|"text"}` |
| `QsSetActualPlanRequest` | `qs/setActualPlan` | `{enabled}` |
| `QsSetSqlcmdModeRequest` | `qs/setSqlcmdMode` | `{enabled}` |
| `QsInlineCompletionRequest` | `qs/inlineCompletion` | params/result at queryStudio.ts:430-451 |
| `QsInlineCompletionAcceptedRequest` | `qs/inlineCompletionAccepted` | `{eventId?}` |
| `QsPinResultSetRequest` | `qs/pinResultSet` | `{resultSetId} → {opened, snapshotId?, error?}` |
| `QsPinAllResultsRequest` | `qs/pinAllResults` | same result |
| `QsUpdateGridSelectionRequest` | `qs/updateGridSelection` | `QsGridSelectionUpdate` (shape only, never values) |
| `QsGetDiagnosticsSummaryRequest` | `qs/getDiagnosticsSummary` | `→ {rowsStreamed, traceMode, replayArmed, syncResyncCount}` |

Language-service requests (`QsLang*`) live in `sharedInterfaces/queryStudioLanguage.ts` and are
registered at queryStudioController.ts:1073-1132 — same pattern, separate module (a precedent for
putting pane contracts in their own `sharedInterfaces/queryStudio<Pane>.ts` module).

### Notifications (host → webview)
| Namespace | method |
|---|---|
| `QsStateChangedNotification` | `qs/stateChanged` (`QsState`) |
| `QsRunStartedNotification` | `qs/runStarted` (`{startedEpochMs}`) |
| `QsSyncInitNotification` / `QsSyncRemoteNotification` / `QsSyncResyncNotification` | `qs/syncInit` / `qs/syncRemote` / `qs/syncResync` |
| `QsRevealPositionNotification` | `qs/revealPosition` |
| `QsRestoreEditorFocusNotification` | `qs/restoreEditorFocus` |
| `QsRowsAppendedNotification` | `qs/rowsAppended` (`{resultSetId, newRowCount, complete}` — **counts only**) |
| `QsResultSetStartedNotification` | `qs/resultSetStarted` (`QsResultSetSummary`) |
| `QsResultSetEndedNotification` | `qs/resultSetEnded` (`{resultSetId, rowCount, truncatedReason?}`) |
| `QsMessagesAppendedNotification` | `qs/messagesAppended` (`{startIndex, messages}` — position-addressed, QO-7) |
| `QsToastNotification` | `qs/toast` (defined, not currently sent by the controller) |

Note: `sendNotification` (webviewBaseController.ts:597-620) fires a telemetry action event per
call — do not design chatty per-row notifications for panes; pull via requests instead (this is
also the addendum §3.6 rule).

### State push throttle
`queueStatePush` (queryStudioController.ts:620-637): coalesced, `STATE_PUSH_MIN_INTERVAL_MS = 100`
(line 113) — ≤10 pushes/s per document. `currentState()` (line 516) rebuilds `QsState` from model:
connection, execution (with live `elapsedMs`), `executionHost.resultsState()`, metadata readiness,
toggles, and `gridStyle` merged with the run's QueryTuning windowing knobs (lines 543-554:
`gridWindowMode`, `gridWindowRows`, `gridPrefetchFactor`, `gridMaxWindowRows`, `textViewMaxRows`,
`textViewSampleRows`, `autosizeSampleRows`, `gridMaxColumnWidthPx`).

`QsState` shape (sharedInterfaces/queryStudio.ts:189-204): `schemaVersion, connection, execution,
results, editor, metadata, completions, toggles, gridStyle, statusMessage, capabilities`.
**`capabilities: Record<string, boolean>`** is currently `{}` — the natural place to advertise
pane availability flags (e.g. `vectorPane: true`) without schema churn.

### Run-event fan-out → notifications (coalescing, QO-7)
Controller's `executionHost.attach` listener (queryStudioController.ts:244-305):
- `onRunStarted`: snapshot per-run pacing from `executionHost.currentTuning`
  (`rowsNotifyIntervalMs`, `messagesNotifyIntervalMs`); reset buffers; send `qs/runStarted`.
- `onRowsAppended`: buffered per resultSetId in `pendingRows`, flushed immediately when interval
  ≤ 0 or on completion; else on a timer (`flushPendingRows`, line 585).
- `onMessages`: buffered in `pendingMessages`, flushed with absolute `startIndex`
  (`messagesSentCount`, line 133; `flushPendingMessages`, line 604).
- `onExecutionStateChanged`: terminal edges flush everything + state push.

---

## 4. Execution → result sets → row storage

### Execute path
`qs/execute` handler (queryStudioController.ts:673-713): slices selection from the backing
`vscode.TextDocument`, resolves mode (`normal | parseOnly | estimatedPlan | actualPlan`), timeout
from `mssql.query.executionTimeout` via `sessionOptions.executionTimeoutMs`, awaits
`sessionBinding.waitForUserSessionReady()`, then `executionHost.execute(text, options)` —
returns `{started, reason?}` synchronously; all progress flows through events.

`ExecutionHost.execute` (executionHost.ts:133-363):
1. Refusals: no session → "Not connected"; mid-run execute cancels + queues rerun (lines 151-161);
   production guard modal (lines 168-184).
2. **Resolves the QueryTuning snapshot ONCE per run** (`resolveQueryTuning`, line 189, QO-1) — it
   drives RowStore limits, wire paging, notification pacing, and is stamped on run records.
3. Releases the previous run's live lease (`retained.releaseLiveOwner("rerun")`) — previous
   RowStore+spill dispose immediately unless snapshots hold leases (C2D-1).
4. **Fresh `RowStore` per run** (line 204): spill dir `spillRoot/run-<n>` (`runSpillDirName`),
   limits from `rowStoreLimitsFrom(tuning)` (line 560: `storeMemoryBytes`, `spillEnabled`,
   `storeSpillBytes`, `maxRowsPerResultSet`), tuning from `rowStoreTuningFrom` (line 570:
   `maxPendingSpillBytes`, `protectedCacheRatio`, `windowCacheEntries`).
5. Wraps in `RetainedRowStore` (line 210) with `runId: qsrun_<rand>` and
   `retainedMemoryBytes` from `resolveQueryResultsParams()`.
6. Creates `ExecutionOrchestrator(session, rowStore, events)` (line 250) whose callbacks maintain
   `host.summaries: Map<string, QsResultSetSummary>` + `summaryOrder` and fan out to panels.
7. `orchestrator.run(text, {..., wire: {pageRows, pageBytes, maxCellBytes}, sqlcmd?})`.

### Orchestrator (executionOrchestrator.ts)
- Batch split (`splitBatches`), optional SQLCMD preprocess, SET wrappers for plan/parse modes
  (`MODE_WRAPPERS`, line 134: `SET SHOWPLAN_XML ON/OFF`, `SET STATISTICS XML ON/OFF`,
  `SET PARSEONLY ON/OFF`), always-restored in `finally`.
- **Store resultSetId format**: `` `b${batchIndex}r${batch.repeatOrdinal}s${wireResultSetId}` ``
  (line 598 etc.) — globally unique across batches within one run.
- Sink `onResultSetStarted` (line 596): calls `rowStore.beginResultSet(storeId, columns)` with
  columns mapped `{name, displayName, sqlType?, isXml?, isJson?}` and emits
  `events.onResultSetStarted({resultSetId, batchOrdinal, columnNames, columns, isPlanResult})`.
- **Plan detection**: `isPlanResultSet(columnNames)` (line 120) — exactly one column matching
  `SHOWPLAN_COLUMN = /^Microsoft SQL Server .*XML Showplan$/i` (line 118). Result sets flagged
  `isPlanResult: true`. *This heuristic is the direct precedent for pane-relevant column
  detection ('vector'/'geometry' columns) — but prefer `columns[].sqlType`, which is exact.*
- Sink `onRowsPage` (line 626): `await rowStore.appendPage(...)` — **this await is the
  backpressure point holding the STS2 ack** (QO-6). Rejection (row cap / storage limit) ends the
  set with `truncatedReason` and cancels the run with an honest warning message (lines 645-679).
- Perf markers: `mssql.queryStudio.query.submit` (begin, line 254),
  `mssql.queryStudio.query.firstResult` (instant, line 323),
  `mssql.queryStudio.query.complete` (end, line 370 — includes RowStore aggregates: `pages`,
  `spillWrites/Reads`, `appendMsTotal`, `spillWriteMsTotal`, `spillReadMsTotal`,
  `materializeMsTotal`), `mssql.queryStudio.cancel` (line 388).

### RowStore internals (rowStore.ts) — the data layout that panes will read
- **Unit of storage: `CompactPage`** (services/sqlDataPlane/api.ts:349-357):
  ```ts
  interface CompactPage {
      values: unknown[][];      // row-major display/raw values; nulls = undefined
      nullBitmap?: string;      // base64 packed bits, row-major (1 = NULL)
      typeHints?: string[];     // per-column decode hints
  }
  ```
  Cell values may be raw scalars, typed wire wrappers `{$t: "datetime2"|"binary"|"decimal"|..., v:
  string}`, or byte-capped markers `TruncatedCellEncoding {$t: "truncated", of: "string"|"binary",
  bytes?, digest?, v}` (api.ts:324-342). Values are **immutable once appended** — safe to cache.
- `ResultSetStore` (rowStore.ts:101): `pages: StoredPage[]`, `rowCount`, `complete`,
  `truncatedReason`, `corrupt`, `typeHints`, `columns: QsResultColumn[]`.
- `StoredPage` (line 84): `{rowOffset, rowCount, approxBytes, compact?, spillPending?, protected?,
  spillOffset?, spillLength?}` — in-memory when `compact` present, else read from spill.
- **Memory strategy (QO-6)**: segmented LRU — PROBATIONARY (appended/scanned) + PROTECTED
  (viewport-fetched, bounded to `protectedCacheRatio` × cap; `promoteToProtected`, line 559).
  Eviction (`evictIfNeeded`, line 590) spills probationary victims first via a **serialized async
  write queue** (`spillChain`); pages stay resident until the write confirms; saturation
  (`pendingSpillBytes > maxPendingSpillBytes`) back-pressures `appendPage`.
- **Spill format**: single file `resultsets.pages` in the run's spill dir; length-prefixed
  (4-byte LE header) JSON frames of `CompactPage` (writeSpillJob, line 641). Spill dirs are
  deleted on dispose; a 15s-delayed startup sweep reclaims orphans
  (queryStudioEditorProvider.ts:268, `sweepOrphanSpillDirs`).
- **`getRows(resultSetId, start, count, reason, columns?)`** (line 349) returns `QsCellWindow`:
  binary-search to the first overlapping page (`firstOverlappingPageIndex`, line 833),
  materialize from memory or spill, project columns horizontally (QO-7b), rebuild the
  window's `nullBitmap`, attach `typeHints`.
  - **`RowReadReason` drives cache admission** (line 72):
    `"grid" | "copy" | "export" | "text" | "cellDocument" | "diagnostic" | "sample" | "profile" |
    "transform" | "aiTool"`. Only `grid|copy|cellDocument|diagnostic` re-admit spilled pages to
    memory (line 447); `grid` additionally promotes to protected. Scan reasons stream without
    admission **so background reads never evict the viewport** — a new pane's bulk column scan
    must use a non-admitting reason (add e.g. `"pane"` to this union, or reuse `"sample"`).
  - **Served-window cache**: complete `grid`-reason windows cache in `windowCache` keyed
    `` `${resultSetId}:${start}:${count}:${columnStart}:${columnSpan}` `` (line 401), LRU-capped
    at `windowCacheEntries`.
  - Perf markers per fetch: `mssql.queryStudio.rows.windowFetch.begin` / `.end` (lines 357, 500)
    with `reason`, `fromSpill`, `cacheHit`, `pagesVisited`, `materializedPages`, `ms` — the
    existing timing template for any new read endpoint. Verbose diagnostics level adds
    `mssql.queryStudio.rows.append` / `rows.spill.write` / `rows.spill.read` markers.
- `stats` getter (line 300) feeds `mssql.perf.queryStudioState` and query.complete aggregates.

### ExecutionHost read surface
- `getRows(resultSetId, start, count, reason = "grid", columns?)` (executionHost.ts:414) —
  delegates to the CURRENT run's RowStore; empty window when none. **This is the single seam
  every extension-side reader goes through** (grid, export, cell docs, plan XML).
- `getMessages(afterIndex?)` (line 433); `resultsState()` (line 446) builds `QsResultsState`
  (`present, resultSets, totalRows, streaming, messageCount, errorCount, planCount`).
- `retainedStore` (line 538) exposes the `RetainedRowStore` for lease-based consumers.
- `currentTuning` (line 87) — the active/last run's `QueryTuningSnapshot`.

### RetainedRowStore (queryResults/resultStoreLease.ts) — lease + streaming idiom
- `retain(owner) → QueryResultStoreLease | undefined` (line 108) keeps the store (and spill)
  alive past reruns; final release disposes. Live-owner release demotes memory cap
  (`shrinkMemoryCap`) with marker `mssql.queryResults.store.demote` (line 136).
- **`streamRows(req)` async generator (line 193)** — the canonical chunked scan idiom
  (`getWindow` in a loop, stops on short window). A pane needing "all values of column X" should
  either use this with `columnStart/columnCount` projection or copy the chunked-loop pattern in
  `resultExport.ts` `readExportRows` (line 341), whose chunk size comes from tuning param
  `exportChunkRows` (line 350).

---

## 5. Row/cell access from the webview (existing precedents)

### Grid windows
`qs/getRows` handler (queryStudioController.ts:775-785) — passes `params.columnStart/columnCount`
projection through, reason `"grid"`. `QsGetRowsParams`/`QsCellWindow` at
sharedInterfaces/queryStudio.ts:217-256. `QsCellWindow.values` is `unknown[][]` — **never tagged
CellValue unions across postMessage** (Appendix A rule); the webview renders via
`cellDisplayText` (sharedInterfaces/queryStudioGridOps.ts:153 — webview-safe, import-free module;
handles typed wrappers, truncated markers, bit→0/1, binary hex display capped at 256 bytes).

### Large values / cell documents
- Wire-level cap: `ExecuteOptions.maxCellBytes` (tuning param) — oversized cells arrive as
  `TruncatedCellEncoding` markers with digest + prefix.
- Display clamp: `QS_CELL_DISPLAY_CLAMP = 2048` chars (queryStudioGridOps.ts:32); larger cells
  link out.
- `qs/openCellDocument` (queryStudioController.ts:802-846): fetches ONE cell via
  `getRows(resultSetId, row, 1, "cellDocument")`, stringifies with `cellDocumentText`
  (cellDocument.ts:24 — delegates to `cellDisplayText`), pretty-prints XML/JSON only under the
  tuning bound `cellDocumentFormatLimit` (raw-first above it, QO-8), opens Beside.
  Returns `{opened: false}` on any failure — the honest-refusal pattern.

### Messages
Pull model with catch-up: `qs/getMessages {afterIndex}` + position-addressed
`qs/messagesAppended {startIndex, messages}` lets the webview reconcile coalesced pushes with
fetches without duplication.

---

## 6. Column metadata: where 'vector' / 'geometry' type names live

- STS2 wire → domain: `ColumnMetadata.sqlType` is set from `wireColumnType(column)` =
  `column.engineType ?? column.EngineType` **verbatim from the service**
  (services/sts2/sts2Backend.ts:764; services/sts2/wire/v2.ts:268-270). A `vector(1536)` or
  `geometry` column arrives with its engine type name in `sqlType` (exact casing per service).
- Domain → QS: `toQsResultColumn` (executionOrchestrator.ts:124) copies
  `{name, displayName, sqlType?, isXml?, isJson?}` into `QsResultColumn`
  (sharedInterfaces/queryStudio.ts:238-244).
- Extension-side availability:
  - `ExecutionHost` summaries: `QsResultSetSummary.columns?: QsResultColumn[]`
    (set at executionHost.ts:252-259) — via `resultsState().resultSets[i].columns`.
  - `RowStore` per set: `summary(resultSetId).columns` (rowStore.ts:278).
- Webview availability: `qs/resultSetStarted` notification payload and `QsState.results`
  both carry `columns` — **the pane can decide "this result set has a vector/geometry column"
  purely from state it already receives; no extra RPC needed for detection.**
- `typeHints` caveat: `typeHintFor(engineType)` (sts2Backend.ts:155-165) maps only
  bit/int/decimal/date/binary/xml families; **vector, geometry, geography, json fall through to
  `"string"`** — so cell payloads for these types arrive as plain strings (vector: JSON-array
  text; geometry/geography: whatever the service emits, typically WKT or hex). Pane parsing
  must key off `QsResultColumn.sqlType`, not `typeHints`.
- `ColumnMetadata` also has `providerType, precision, scale, maxLength, isKey, allowNull`
  (api.ts:265-278) but only the five QsResultColumn fields cross into QS today — extend
  `toQsResultColumn` if a pane needs more (e.g. vector dimension might require precision or
  parsing the type name).

---

## 7. Plan tab — THE precedent for a lazy, host-computed pane payload

The execution-plan tab is exactly the pattern the new panes should copy:

1. **Detection**: orchestrator flags `isPlanResult` on the summary; `resultsState().planCount`
   rides coarse state → the webview shows/hides the tab with zero extra fetches.
2. **Lazy fetch on tab open**: webview sends `qs/getPlanState {resultSetIds}` only when the plan
   tab is actually opened.
3. **Host-side raw-data fetch**: `planXmlForResultSet` (queryStudioController.ts:349-359) —
   verifies the summary flag, then `executionHost.getRows(resultSetId, 0, 1, "cellDocument")` and
   `cellDocumentText(window.values[0]?.[0])`.
4. **Host-side parse + content-keyed cache (QO-8)**: `qs/getPlanState` handler (lines 870-922)
   builds a cache key from ids + total XML length + first-256-chars, checks
   `this.planStateCache` (line 135), else parses via `createExecutionPlanGraphs(...)` from
   `controllers/sharedExecutionPlanUtils` into `ExecutionPlanWebviewState["executionPlanState"]`,
   caches one entry (plans belong to the current run), and emits the timing marker either way:
   ```ts
   Perf.marker("mssql.queryStudio.plan.parse", "instant", { plans, cacheHit, ms });
   ```
5. **Error channel**: returns `{error: string}` instead of throwing — webview renders the message.
6. **Escape hatch**: `qs/openPlan` reuses the classic full plan viewer webview via the
   `executionPlanSeam()` (line 324 — `mssql.getControllerForTests` command seam).

For a vector/spatial pane: replace steps 3-4 with a column scan + pane-specific transform
(host-side, cached, measured), same request/response + error-string shape.

---

## 8. Where new pane-specific endpoints should be added

1. **Contracts**: new `RequestType` namespaces — either appended to
   `sharedInterfaces/queryStudio.ts` or (better, following `queryStudioLanguage.ts`) a new
   `sharedInterfaces/queryStudioPanes.ts` (or per-pane) module. Method naming: keep the `qs/`
   prefix, e.g. `qs/getColumnValues`, `qs/getVectorPaneState`, `qs/getSpatialPaneState`.
2. **Handlers**: register in `QueryStudioController.registerHandlers()`
   (queryStudioController.ts:639) — group under a new `// --- result panes ---` section next to
   the plan handlers (after line 949). Handlers delegate to `this.model.executionHost` only;
   never touch `RowStore` directly from the controller (the host owns run/lifecycle races —
   `getRows` on a disposed/absent store already returns an empty window safely).
3. **Bulk column read** ("all values of vector column X"): chunked loop over
   `executionHost.getRows(resultSetId, start, chunk, <scanReason>, {start: colIdx, count: 1})` —
   column projection (QO-7b) moves ONLY that column; chunk size from a tuning param (add one to
   the QueryTuning registry like `exportChunkRows`; see resultExport.ts:350 for the resolve
   pattern). Use a **non-admitting `RowReadReason`** (extend the union at rowStore.ts:72-83 and
   deliberately leave it out of the `admit` list at rowStore.ts:447-451) so a pane scan cannot
   evict the grid viewport. If the pane must survive a rerun while open, take a lease via
   `executionHost.retainedStore.retain({kind: ..., label: ...})` and use `streamRows`.
4. **Caching**: content/run-keyed cache on the controller, exactly like `planStateCache`
   (line 135) — invalidate implicitly by keying on `resultSetId`s + run identity
   (`executionHost.retainedStore?.runId`), since each run replaces summaries and store IDs.
5. **Capability/visibility**: pane tab visibility should derive from
   `QsState.results.resultSets[].columns[].sqlType` (already pushed); optional flags can ride
   `QsState.capabilities` (currently `{}`, queryStudioController.ts:401).
6. **Timing/metrics** (mandatory per build requirements):
   - Method-level spans are free (webviewBaseController onRequest wrapper →
     `webview.queryStudio.qs/<method>` in Debug Console/session-diag).
   - Add domain markers named `mssql.queryStudio.pane.<pane>.<event>` following
     `mssql.queryStudio.plan.parse` / `rows.windowFetch.begin|end` conventions, with `ms`,
     `rows`, `cacheHit`, `fromSpill`-style fields.
   - Structured diagnostics: `diag.emit({feature: "queryStudio", type: "queryStudio.<x>",
     fields: {k: {raw, cls: "diagnostic.metadata"}}})` (see dbSwitch, line 743) or
     `diag.startSpan` (see inlineCompletion.bridge, line 981). **Never put cell values or SQL
     text in diagnostics** (privacy invariant, api.ts:15-18).
7. **Perf-mode probes**: if the panes need harness hooks, follow
   `registerQueryStudioPerfProbe` (queryStudioEditorProvider.ts:192-253) —
   `mssql.perf.queryStudio*` commands registered only when `Perf.enabled`.

---

## 9. Config keys, constants, and misc identifiers (verbatim)

- Gates/settings: `mssql.queryStudio.enabled`, `mssql.queryStudio.scan.enabled`,
  `mssql.queryStudio.scan.autoEnableSqlcmd`, `mssql.queryStudio.warnWhenModifyingProduction`,
  `mssql.queryStudio.statusBarGroupColor`, `mssql.queryStudio.resultsPaneHeightPercent`,
  `mssql.queryStudio.maxRowsPerResultSet` (referenced in the truncation message,
  executionOrchestrator.ts:672), `mssql.query.executionTimeout`, `mssql.sqlDataPlane.enabled`,
  `mssql.resultsFontFamily`, `mssql.resultsFontSize`, `mssql.resultsGrid.showGridLines`,
  `mssql.resultsGrid.rowPadding`, `mssql.resultsGrid.alternatingRowColors`,
  `mssql.resultsGrid.inMemoryDataProcessingThreshold` (gridStyle.ts:31-64 — the pure-reader
  pattern; grid style config changes trigger a state push, queryStudioController.ts:222-228).
- Grid style flows as data (`QsGridStyle` on `QsState`); the webview maps it to CSS custom
  properties — new pane styling should ride the same snapshot rather than reading config in the
  webview.
- View type: `mssql.queryStudio`. Webview bundle id: `queryStudio` (→ `dist/views/queryStudio.js`).
- Commands: `mssql.queryStudio.new`, `mssql.queryStudio.newQueryFromContext`,
  `mssql.queryStudio.openActive`, `mssql.queryStudio.openInClassicEditor`,
  `mssql.queryStudio.duplicateAsNewQuery`, `mssql.queryStudio.languageServiceStatus`,
  `mssql.queryStudio.openReplayLab`, `mssql.queryStudio.pinAllResults`,
  `mssql.queryResults.showStatus`, `mssql.queryResults.benchmarkTransform`.
- Key perf markers already emitted: `mssql.queryStudio.open.begin/end`,
  `mssql.queryStudio.connect.begin/ready`, `mssql.queryStudio.query.submit/firstResult/complete`,
  `mssql.queryStudio.rows.windowFetch.begin/end`, `mssql.queryStudio.rows.append`,
  `mssql.queryStudio.rows.spill.write/read`, `mssql.queryStudio.rows.maxRowsPerResultSet`,
  `mssql.queryStudio.plan.parse`, `mssql.queryStudio.export.begin/end`,
  `mssql.queryStudio.cancel`, `mssql.queryStudio.sqlcmd.run`, `mssql.queryStudio.scan.run`,
  `mssql.queryResults.store.demote`.
- Execution modes / SET wrappers: `SET PARSEONLY`, `SET SHOWPLAN_XML`, `SET STATISTICS XML`
  (executionOrchestrator.ts:134-139).
- Session execute tags in use: `queryStudio:catalog`, `queryStudio:use`,
  `queryStudio:setWrapper`, `queryStudio:sessionOptions`, `queryStudio:tranProbe`,
  `queryStudio:spidProbe`, `queryStudio:dbListMaster` — background host-side SQL uses
  `priority: "background", commandKind: "metadata"` and MUST await `handle.completion`
  (not sink callbacks) to avoid racing the one-active-query slot (executionHost.ts:466-488,
  documentSessionBinding.ts:656-660). Bounded busy retry exists for the user path
  (`executeWhenFree`, executionOrchestrator.ts:528-549, error code `SqlDataPlane.Busy`).

## 10. Performance invariants the panes must not break

1. Nothing new on the open path before the `qs/getDiagnosticsSummary`-triggered
   `mssql.queryStudio.open.end` marker; pane data work starts only on first tab activation.
2. Rows never ride notifications; counts only. Panes pull.
3. `appendPage` await is the wire backpressure point — never insert synchronous work into the
   sink path (executionOrchestrator.ts:626-644).
4. Bulk reads use non-admitting `RowReadReason`s; only viewport reads may promote to protected.
5. One QueryTuning snapshot per run; new knobs go into the tuning registry, not constants.
6. State pushes stay coalesced (≤10/s); pane progress should ride existing state or its own
   coalesced notification with intervals from tuning.
7. Diagnostics carry metadata/digests only — no cell values, no SQL text.
