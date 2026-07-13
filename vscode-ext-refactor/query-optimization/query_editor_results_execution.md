# Query Editor Results Execution: End-to-End Perf Review

Status: draft for review  
Date: 2026-07-09  
Scope: Query Studio query execution, result streaming, result storage, grid rendering, messages, plan/XML/JSON handling, diagnostics, and perf-test coverage across `vscode-mssql`, `sqltoolsservice`, and `perftest`.

## Executive summary

Query Studio already has the right high-level architecture for large results:

- STS2 is a forward-only query stream. It does not own random-access result caches.
- The extension host owns per-run result storage through `RowStore`.
- The webview grid pulls bounded windows by RPC instead of receiving row data in coarse state.
- The shared `FluentResultGrid` uses a windowed SlickGrid data source.
- Backpressure exists between extension acceptance and STS2 page credit.

The primary perf risk is not one broken architectural decision. It is duplicated work and missing hard bounds at several seams:

- `SqlClientSession` reads full cell values with `SqlDataReader.GetValue` before STS2 truncates them. Large XML, JSON, and BLOB values can already be fully materialized in STS memory before the `maxCellBytes` guard helps.
- `PageBytes` exists in STS2 defaults and request contracts, but the current SQL Client page pump is row-count based. A 1000-row page can be tiny or enormous depending on cell shape.
- STS2 serializes pages to JSON, the extension parses them, the binding computes `approxBytes` with `JSON.stringify(params.rows).length`, and the `RowStore` may later `JSON.stringify` the compact page again for spill.
- `RowStore` spill/read is synchronous filesystem + JSON work on the extension host.
- `RowStore.getRows` scans cells to build diagnostics on every window fetch, even when detailed row diagnostics are not needed.
- `MessagesView` prepares and renders every message row. A script that prints 10,000 messages keeps making normal editor typing slow when the pane is visible.
- Text view and result export fetch in chunks but still build complete output strings in memory.
- The current perf scenarios cover important shapes, but the instrumentation does not yet attribute time and bytes across every row-pipeline stage.

Recommendation:

1. Keep the ownership split: STS2 streams forward-only; Query Studio owns random access.
2. First make limits and diagnostics honest end to end: page rows, page bytes, max cell bytes, row cap, spill stats, queue depth, render window stats.
3. Then remove hot-path duplicate serialization and synchronous spill work.
4. Finally add targeted perf scenarios and unit tests for wide, deep, large-cell, high-message, cancellation, and scroll-window behavior.

## Current architecture map

```text
Query Studio webview
  Monaco editor, toolbar, results tabs
  QsResultGridSurface / MessagesView / QueryStudioResultsTextView
        |
        | WebviewBaseController RPC
        v
QueryStudioController
  QsExecute, QsCancel, QsGetRows, QsGetMessages, QsSaveResult,
  QsOpenCellDocument, QsGetPlanState, QsOpenPlan
        |
        v
QueryStudioDocumentModel
  shared text, shared session binding, shared ExecutionHost
        |
        v
ExecutionHost
  per-document run state, messages, result summaries, RowStore
        |
        v
ExecutionOrchestrator
  GO splitting, query modes, message synthesis, row cap cancellation
        |
        v
SQL Data Plane ISqlSession.execute
        |
        v
Sts2Backend / Sts2Query
  v2/query.execute, ordered notification lane, page ack after sink acceptance
        |
        v
STS2 Core + Runtime
  reducer state, credit accounting, DriverEffectRunner query pump
        |
        v
SqlClientSession
  SqlCommand, SqlDataReader, schema, rows, messages, cancel
        |
        v
SQL Server
```

Important ownership boundary:

- STS2 is authoritative for connection/session execution order, query lifecycle, server messages, rows pages, and cancellation requests.
- Query Studio is authoritative for result-set random access, spill storage, grid state, view-mode transforms, message display, export, and plan/XML/JSON UI handling.

## Classic query editor reference path

Relevant files:

- `vscode-mssql/extensions/mssql/src/controllers/queryRunner.ts`
- `vscode-mssql/extensions/mssql/src/models/sqlOutputContentProvider.ts`
- `vscode-mssql/extensions/mssql/src/queryResult/utils.ts`
- `vscode-mssql/extensions/mssql/src/webviews/pages/QueryResult/*`

The classic query editor remains the main parity and perf control for Query Studio. Its path is materially different:

```text
Text editor command
        |
        v
QueryRunner
  QueryExecuteRequest, query notifications, batch/result/message state
        |
        v
SQL Tools Service v1 query service
  owns result data and serves subsets
        |
        v
SqlOutputContentProvider.rowRequestHandler
        |
        v
QueryExecuteSubsetRequest
  QueryRunner chunks subset requests in 500-row pages
        |
        v
Classic QueryResult webview
  shared FluentResultGrid or classic result surfaces
```

Classic execution markers include:

- `mssql.query.submit`
- `mssql.query.complete`
- `mssql.resultsGrid.windowFetch.begin`
- `mssql.resultsGrid.windowFetch.end`
- `mssql.resultsGrid.dataReceived`
- `mssql.resultsGrid.renderComplete`

Important contrasts:

- Classic STS v1 owns result storage and serves random-access subsets.
- Query Studio STS2 streams forward-only and the extension `RowStore` owns random access.
- Classic `QueryRunner.getRows` chunks every subset request into `QueryExecuteSubsetRequest` calls of 500 rows.
- Query Studio `QsGetRows` asks the extension `RowStore` directly; STS2 is not involved after rows have streamed into the store.
- Classic XML/JSON open-link formatting happens through the established query-result controller path. Query Studio does similar work through `QsOpenCellDocumentRequest`.
- Classic render-complete markers are grid-level; Query Studio has `mssql.queryStudio.resultsRendered` plus row-window markers but needs deeper grid-window attribution.

Perf implication:

- Query Studio should not copy classic server-side result-cache ownership unless STS2 intentionally grows a durable result artifact. The better optimization path is to make Query Studio's extension-owned store and STS2 forward stream faster, more bounded, and better instrumented.

## Current execution path

### 1. Webview command to extension host

Relevant files:

- `vscode-mssql/extensions/mssql/src/webviews/pages/QueryStudio/app.tsx`
- `vscode-mssql/extensions/mssql/src/queryStudio/queryStudioController.ts`
- `vscode-mssql/extensions/mssql/src/queryStudio/queryStudioDocumentModel.ts`

The webview sends `QsExecuteRequest` to `QueryStudioController`. The controller resolves:

- current editor text or selected text
- execution mode: normal, parse-only, estimated plan, or actual plan
- query session options such as `mssql.query.executionTimeout`
- current grid style and result view state

Rows are deliberately excluded from coarse `QsState`. Result-set metadata, row counts, message counts, and execution state are pushed to the webview. Actual row values are fetched later through `QsGetRowsRequest`.

State push throttling:

- `STATE_PUSH_MIN_INTERVAL_MS = 100`, so coarse state is pushed at most about 10 times per second per document.
- `QsRowsAppendedNotification` is count-only and currently sent on every accepted page.
- `QsMessagesAppendedNotification` sends message rows and then queues a coarse state push.

Perf note:

- Keeping row data out of `QsState` is essential and should remain a hard rule.
- Per-page row-count notifications can still become noisy at high page rates. They should be frame-batched or time-batched after deeper instrumentation proves the cost.

### 2. ExecutionHost

Relevant file:

- `vscode-mssql/extensions/mssql/src/queryStudio/executionHost.ts`

`ExecutionHost` is the per-document shared execution owner. Multiple split editors attach to the same host. It owns:

- the active `ExecutionOrchestrator`
- the current `RowStore`
- message rows
- result-set summaries
- run capture records
- execution state

Starting a run:

1. Rejects if no active session.
2. If an execution is already active, requests cancel and returns "Canceling the running query."
3. Rejects empty SQL.
4. Disposes the previous `RowStore`.
5. Creates a new `RowStore` under a per-run spill folder.
6. Clears messages and summaries.
7. Creates `ExecutionOrchestrator`.
8. Fans out `onRunStarted` before `orchestrator.run()` because the orchestrator emits the first "Started executing..." message synchronously.

Important settings:

- `mssql.queryStudio.maxRowsPerResultSet`, default `5_000_000`.
- `RowStore.DEFAULT_LIMITS.maxMemoryBytes = 64 MiB`.
- `RowStore.DEFAULT_LIMITS.maxSpillBytes = 2048 MiB`.
- `RowStore.DEFAULT_LIMITS.spillEnabled = true`.

Only the row cap is currently exposed through a Query Studio setting. Memory and spill limits are constants.

### 3. ExecutionOrchestrator

Relevant file:

- `vscode-mssql/extensions/mssql/src/queryStudio/executionOrchestrator.ts`

Responsibilities:

- split scripts by `GO` and `GO n`
- run batches sequentially
- implement modes:
  - normal
  - parse-only through `SET PARSEONLY ON/OFF`
  - estimated plan through `SET SHOWPLAN_XML ON/OFF`
  - actual plan through `SET STATISTICS XML ON/OFF`
- synthesize classic-style messages:
  - `Started executing query at Line N`
  - `(N rows affected)`
  - `Total execution time: HH:MM:SS.mmm`
- map server error lines back to document lines
- write row pages to `RowStore`
- cancel when `RowStore` rejects a page because the per-result-set row cap is reached
- detect plan result sets from the SHOWPLAN XML column shape

Run status behavior:

- Continue-on-error is the Query Studio default, matching SSMS-style multi-batch behavior.
- A failed batch can be followed by later successful batches.
- Canceled and row-capped result sets are marked partial/truncated and do not print misleading row-affected messages.

Perf markers already present:

- `mssql.queryStudio.query.submit`
- `mssql.queryStudio.query.firstResult`
- `mssql.queryStudio.query.complete`
- `mssql.queryStudio.cancel`
- `mssql.queryStudio.rows.maxRowsPerResultSet`

### 4. SQL Data Plane API

Relevant files:

- `vscode-mssql/extensions/mssql/src/services/sqlDataPlane/api.ts`
- `vscode-mssql/extensions/mssql/src/services/sqlDataPlane/sqlDataPlaneService.ts`

The extension-side contract already has the right shape:

```ts
interface ExecuteOptions {
    pageRows?: number;
    pageBytes?: number;
    maxCellBytes?: number;
    priority?: "interactive" | "background";
    commandKind?: "user" | "metadata" | "system";
    timeoutMs?: number;
    expectedDatabase?: string;
    catalogGeneration?: number;
    tag?: string;
}
```

`IQueryEventSink.onRowsPage` is intentionally awaited by bindings. Its resolution means durable acceptance by the consumer. STS2 acks pages only after this sink completes.

Rows delivered to Query Studio use `CompactPage`:

```ts
interface CompactPage {
    values: unknown[][];
    nullBitmap?: string;
    typeHints?: string[];
}
```

This is more compact than per-cell object rows and is the right direction for the extension/webview boundary. It is not yet the STS2 wire shape.

### 5. STS2 backend binding

Relevant files:

- `vscode-mssql/extensions/mssql/src/services/sts2/sts2Backend.ts`
- `vscode-mssql/extensions/mssql/src/services/sts2/wire/v2.ts`

`Sts2Backend` is the extension-host binding over the STS2 JSON-RPC lane. It enforces local protocol invariants:

- metadata must arrive before rows
- `pageSeq` must be gapless
- `rowOffset` must be monotonic
- only one terminal notification is accepted
- page ack is high-water and happens only after `sink.onRowsPage` resolves
- cancel has a terminal deadline
- protocol violation triggers diagnostics and best-effort cancellation

Current row handling:

1. Receive `v2/query.rows`.
2. Validate sequencing.
3. Convert `params.rows` to `CompactPage` and build null bitmap/type hints.
4. Compute `approxBytes` with `JSON.stringify(params.rows).length`.
5. Await `sink.onRowsPage(page)`.
6. Send `v2/query.ack` with the new high-water page sequence.

Perf risks:

- `JSON.stringify(params.rows).length` is an avoidable full-page serialization on the extension host.
- The binding creates a second compact page after STS2 already serialized a full rows array.
- `pageBytes` and `timeoutMs` exist in extension contracts, but the current STS2 binding sends only `pageRows` and `options.maxCellBytes`.
- Startup capability flags currently only advertise `maxCellBytesHonored` when STS2 reports it. Page-byte capability is not honored today.

### 6. STS2 Core query state machine

Relevant files:

- `sqltoolsservice/src/sts2/Microsoft.SqlTools.Sts2.Core/Sts2CoreReducer.cs`
- `sqltoolsservice/src/sts2/Microsoft.SqlTools.Sts2.Core/CoreState.cs`
- `sqltoolsservice/src/sts2/Microsoft.SqlTools.Sts2.Contracts/Sts2Defaults.cs`

Default limits:

```csharp
PageRows = 1000
PageBytes = 262144
WindowPages = 4
MaxCellBytes = 1048576
TruncatedPrefixBytes = 65536
MaxFrameBytes = 67108864
QueryDefaultTimeoutMs = 0
```

Core state tracks query lifecycle and credit, not row cells:

- query id
- connection id
- phase
- pages sent
- pages acked
- credit outstanding
- terminal status

Credit flow:

1. Query starts with `WindowPages` credits.
2. Runtime sends rows pages while credit exists.
3. Client acks high-water accepted page.
4. Core computes credit to restore back to the window size.
5. Runtime gets `driver.queryAdvance` effects.

This is the right place for lifecycle and flow control. It should not become a grid cache.

Current gaps:

- `pageRows` and `pageBytes` in client requests are not fully plumbed through the reducer/effect arguments.
- `EffectiveMaxCellBytes` is implemented as lower-only clamping, which is good, but capability reporting should be made explicit and covered by tests.
- `PageBytes` is defined but not enforced by `SqlClientSession`.

### 7. STS2 runtime driver pump

Relevant file:

- `sqltoolsservice/src/sts2/Microsoft.SqlTools.Sts2.Runtime/Effects/DriverEffectRunner.cs`

`DriverEffectRunner` turns driver events into STS2 query notifications.

For row pages:

- waits for query credit
- serializes rows using `SerializeRows`
- encodes cells with `WireValueEncoder.Encode`
- posts `driver.queryEvent` back through the reducer

Current behavior note from code comments:

- Backpressure gates page posting, but the async enumerator can materialize one extra driver page before the credit wait. This creates a bounded one-page overrun.
- Eliminating the overrun would require a credit-gated page-pull driver port rather than the current `await foreach` stream shape.

Perf risks:

- `SerializeRows` creates `JsonArray` objects and calls `ToJsonString`.
- The page is later parsed by the extension and often re-serialized for approximate size or spill.
- `approxBytes` should be computed once near serialization, then sent as metadata.
- STS2 should eventually be able to emit compact rows directly, including null bitmap and type hints, so the extension binding does not rebuild them.

### 8. SqlClientSession and SqlDataReader

Relevant file:

- `sqltoolsservice/src/sts2/Microsoft.SqlTools.Sts2.Drivers.SqlClient/SqlClientSession.cs`

Current query execution:

1. Create `SqlCommand` on the session `SqlConnection`.
2. Apply command timeout if requested.
3. Hook `SqlConnection.InfoMessage`.
4. Execute `ExecuteReaderAsync`.
5. For each result set, call `GetColumnSchemaAsync`.
6. Yield `ResultSetStarted`.
7. Read rows with `ReadAsync`.
8. For every cell, call `IsDBNull` or `GetValue`.
9. Build pages by row count.
10. Yield `RowsPage`.
11. Drain pending messages at page/result boundaries.
12. Yield `ExecCompleted` with affected row counts and current database.

Cancellation:

- active command is stored
- `CancelAsync` calls `SqlCommand.Cancel()`
- the streaming loop observes cancellation tokens

Current high-risk behavior:

- `GetValue` materializes the whole provider value before `WireValueEncoder` can truncate it.
- Large XML, JSON, and BLOB columns can allocate large strings/byte arrays in STS memory.
- `PageBytes` is not enforced, so a page with 1000 rows can exceed intended bounds.
- The reader does not appear to use `CommandBehavior.SequentialAccess`, which would be needed for true streaming/truncating of large values.

Primary STS2-side optimization:

- Use `SequentialAccess` and type-specific readers for large values:
  - `GetChars` or `GetTextReader` for large string/XML values
  - `GetBytes` or `GetStream` for binary values
  - bounded prefix read plus optional digest computation
- Enforce page byte limits while building pages, not only while serializing them.
- Emit per-page byte estimates and truncation counts.

### 9. Wire value encoding

Relevant file:

- `sqltoolsservice/src/sts2/Microsoft.SqlTools.Sts2.Runtime/Effects/WireValueEncoder.cs`

Current behavior:

- scalar JSON-safe values pass through
- decimals, date/time, GUID, binary, and provider-specific values get wrappers when needed
- strings and binary values above `maxCellBytes` become:

```json
{
  "$t": "truncated",
  "of": "string",
  "bytes": 123456,
  "digest": "sha256:...",
  "v": "prefix"
}
```

Strengths:

- The payload is honest about truncation.
- The retained prefix is bounded.
- Existing tests cover exact-bound and one-over-bound behavior.

Perf concern:

- The digest is computed over the full value after the full value has already been materialized. For huge values this adds CPU on top of the memory hit. If full digests remain required, digesting should happen while streaming the reader rather than after materialization.

### 10. RowStore

Relevant file:

- `vscode-mssql/extensions/mssql/src/queryStudio/rowStore.ts`

`RowStore` stores per-run pages and serves random windows to the webview.

Current design:

- pages indexed per result set by `rowOffset`
- binary search finds the first overlapping page
- memory LRU keeps hot pages
- spill uses a single length-prefixed JSON frame file
- spill artifacts are removed on dispose
- `getRows` returns `QsCellWindow`

Current default limits:

- memory cap: 64 MiB
- spill cap: 2 GiB
- row cap: 5 million rows per result set

Important implementation facts:

- `appendPage` rejects an entire page if accepting it would exceed the row cap. The orchestrator then cancels the query and warns the user.
- `getRows` rebuilds a window null bitmap and counts null/non-null/non-empty cells for diagnostics.
- spill uses `fs.writeSync`, `fs.readSync`, `JSON.stringify`, and `JSON.parse` in the extension host process.

Perf risks:

- Synchronous spill can block the extension host during heavy ingestion or high-offset scrolling.
- JSON spill duplicates the page payload and parse cost.
- Re-admitting a spilled page can immediately evict another page, causing churn during scroll.
- Detailed per-window cell counting is useful in full diagnostics but expensive for wide grids.

Recommended direction:

- Preserve `RowStore` ownership in the extension.
- Make spill asynchronous or worker-backed.
- Prefer storing the already compact serialized frame bytes instead of re-stringifying the page.
- Add explicit page/window cache hit/miss and spill read/write timings.
- Gate expensive per-cell diagnostic counts behind a verbose diagnostic level.
- Expose memory/spill limits as settings or experiment knobs, but keep defaults conservative.

### 11. Query Studio webview result grid

Relevant files:

- `vscode-mssql/extensions/mssql/src/webviews/pages/QueryStudio/results.tsx`
- `vscode-mssql/extensions/mssql/src/webviews/pages/QueryStudio/resultsGrid.tsx`
- `vscode-mssql/extensions/mssql/src/webviews/common/FluentResultGrid/*`

Current grid behavior:

- Query Studio uses the shared `FluentResultGrid`, backed by SlickGrid through the shared grid component.
- Query Studio passes a `windowed` data source.
- `QsResultGridSurface` maps `QsCellWindow` to `DbCellValue[][]`.
- Display text is clamped to `QS_CELL_DISPLAY_CLAMP = 2048`.
- XML/JSON document links are identified from metadata or content shape.
- Copy uses chunked `QsGetRows` fetches with `COPY_CHUNK = 512`.
- Copy refuses selections above `COPY_MAX_ROWS = 100_000`.
- Sort/filter are enabled only when the result set is complete and row count is at or below `mssql.resultsGrid.inMemoryDataProcessingThreshold`, default `5000`.
- Column reorder is disabled locally for Query Studio.

Shared windowed grid internals:

- `FLUENT_RESULT_GRID_WINDOW_SIZE = 50`.
- Three windows are kept: before, current, after.
- The before window starts about 1.5 windows before the current target.
- The grid invalidates rows and schedules render when windows load.

Strengths:

- The DOM only contains visible SlickGrid rows.
- Row values are fetched by viewport windows.
- Heavy cells are display-clamped before DOM insertion.
- Sorting/filtering large result sets is explicitly gated.

Perf risks:

- Window size 50 may be too small for high-latency extension-host RPC or fast wheel scrolls.
- There is no visible adaptive prefetch based on viewport size or scroll velocity.
- There is limited tracing around webview request start/end, grid cache hits/misses, placeholder time, and paint time per loaded window.
- Column auto-size samples can still be expensive on very wide columns if repeated often.

Recommended direction:

- Make the window size adaptive or Query Studio-specific, for example 2 to 4 visible viewports instead of a fixed 50 rows.
- Add cache hit/miss markers in the webview data view.
- Emit `QsGetRows` RPC duration and row/column counts in both host and webview lanes.
- Add a lightweight "first visible rows painted" marker separate from full `resultsRendered`.
- Keep sort/filter threshold-based unless a server/worker-backed transform is designed later.

### 12. Messages tab

Relevant file:

- `vscode-mssql/extensions/mssql/src/webviews/pages/QueryStudio/results.tsx`

Current behavior:

- Messages are stored in extension-host memory as `QsMessageRow[]`.
- The webview appends new messages into React state.
- `MessagesView` maps every message to a prepared display row on render.
- It renders every prepared row into the DOM.
- `Copy All` builds a full text string including timestamps.
- Line numbers in error messages can be rendered as document-navigation links.

Perf risk:

- With 10,000 PRINT messages visible, editor typing becomes slow because React can reprocess and keep a large messages DOM live. This matches the observed user repro.

Recommended direction:

- Virtualize messages just like grid rows.
- Keep the timestamp/text formatting function pure and test-covered, but apply it only for visible rows.
- Keep `Copy All`, but have it call a host-side `QsCopyAllMessages` or `QsGetMessagesText` request that builds text once on demand.
- Add markers:
  - messages appended count
  - visible message rows rendered
  - total message rows
  - prepare duration
  - paint duration
  - copy-all duration and bytes

### 13. Text view

Relevant file:

- `vscode-mssql/extensions/mssql/src/webviews/pages/QueryStudio/resultsTextView.tsx`

Current behavior:

- Fetches all rows in chunks of `TEXT_VIEW_CHUNK = 5000`.
- Computes column widths across all rows.
- Builds a complete text string.
- Renders the full string in Monaco plaintext.

Strength:

- Chunked fetch avoids a single unbounded `QsGetRows`.

Perf risk:

- The final output is still all rows x all columns in memory.
- Width computation requires all rows.
- Large result sets can freeze the webview or extension host while fetching and formatting.

Recommended direction:

- Treat result-to-text as a large export-like operation, not a cheap view toggle.
- Provide a progressive/virtual text viewer or cap with explicit user confirmation.
- For full text output, stream to a temp document/file instead of building a single webview string.
- Add cancellation/progress for text generation.

### 14. Save/export

Relevant file:

- `vscode-mssql/extensions/mssql/src/queryStudio/resultExport.ts`

Current behavior:

- CSV/JSON/INSERT export reads rows in `EXPORT_CHUNK_SIZE = 2048`.
- CSV, JSON, and INSERT content is assembled into arrays/strings in memory.
- The final string is written via `vscode.workspace.fs.writeFile`.

Strength:

- Source row fetching is bounded.

Perf risk:

- Output construction is not streaming. Exporting a large result can create a very large string and duplicate it as a `Buffer`.

Recommended direction:

- Stream export output directly to a file with backpressure.
- Add progress and cancellation.
- For JSON, use streaming array emission with first-row comma handling.
- For INSERT, stream batches directly.
- Keep current small-result path for simplicity, but switch to streaming above a byte/row threshold.

### 15. XML, JSON, and BLOB links

Relevant files:

- `vscode-mssql/extensions/mssql/src/sharedInterfaces/queryStudioGridOps.ts`
- `vscode-mssql/extensions/mssql/src/queryStudio/cellDocument.ts`
- `vscode-mssql/extensions/mssql/src/queryStudio/queryStudioController.ts`

Current behavior:

- Grid display clamps cell text.
- Document language detection uses metadata where possible.
- Content sniffing parses JSON only below `QS_CELL_DOCUMENT_PARSE_LIMIT = 256 KiB`.
- Larger JSON-shaped text can still be considered JSON by shape.
- `QsOpenCellDocumentRequest` fetches a single cell and opens a text document with pretty JSON/XML when possible.

Perf risks:

- Pretty-printing very large JSON/XML can be CPU-heavy.
- Current STS2 truncation means Query Studio may only have a prefix of very large values. That is honest for display, but it is not equivalent to a full-value open unless a separate full-cell retrieval design exists.

Recommended direction:

- Make full-cell behavior explicit:
  - Either Query Studio only offers "open prefix" for truncated cells.
  - Or STS2/Query Studio gets a separate large-cell retrieval channel tied to server cursor/result storage.
- Avoid pretty-printing huge values synchronously.
- Add markers for open-cell request duration, value bytes, pretty-print duration, and document-open duration.

### 16. Estimated and actual query plans

Relevant files:

- `vscode-mssql/extensions/mssql/src/queryStudio/executionOrchestrator.ts`
- `vscode-mssql/extensions/mssql/src/queryStudio/queryStudioController.ts`
- `vscode-mssql/extensions/mssql/src/controllers/sharedExecutionPlanUtils.ts`

Current behavior:

- Estimated plan mode wraps execution with `SET SHOWPLAN_XML ON/OFF`.
- Actual plan mode wraps execution with `SET STATISTICS XML ON/OFF`.
- Plan result sets are detected by SHOWPLAN XML column shape.
- Query Studio exposes an embedded Query Plan tab and an "Open in New Tab" path through existing execution-plan utilities.
- Plan XML is read from the first cell of the plan result set.

Perf risks:

- Plan XML can be large.
- Plan graph creation can be CPU-heavy and should not be repeated unnecessarily.
- Selection-execution behavior should match normal Execute.

Recommended direction:

- Cache parsed plan graphs by result set id and plan XML digest.
- Add progress/error states for plan parse.
- Add markers around SHOWPLAN run, plan XML fetch, graph parse, first paint, and "open in new tab."

## Current diagnostics and instrumentation

### Extension markers

Relevant files:

- `vscode-mssql/extensions/mssql/src/perf/perfTelemetry.ts`
- `coding-docs/observability-docs/03-instrumentation-reference.md`

The `Perf` facade routes marker events into the unified diagnostics core. When no sink is active, marker emission is effectively no-op. When perf/session diagnostics are active, markers can flow to:

- perf harness marker sink
- Debug Console live tail
- session diagnostics store

Query Studio/result markers observed in code and registry:

- `mssql.queryStudio.open.begin`
- `mssql.queryStudio.open.end`
- `mssql.queryStudio.connect.begin`
- `mssql.queryStudio.connect.ready`
- `mssql.queryStudio.query.submit`
- `mssql.queryStudio.query.firstResult`
- `mssql.queryStudio.query.complete`
- `mssql.queryStudio.resultsRendered`
- `mssql.queryStudio.rows.windowFetch.begin`
- `mssql.queryStudio.rows.windowFetch.end`
- `mssql.queryStudio.cancel`
- `mssql.queryStudio.rows.maxRowsPerResultSet`
- `mssql.queryStudio.messagesPrepared`
- `mssql.queryStudio.messagesRendered`

Current good coverage:

- user-perceived query to render
- query to complete
- row-window fetches in the extension host
- cancellation timing
- row cap
- message preparation/render markers

Current gaps:

- STS2 SQL reader timing per result set and per page
- STS2 encode/serialize time per page
- wire payload bytes sent to extension
- extension binding decode/compact time
- exact page bytes without extension-side re-stringify
- RowStore append/spill/write/read/materialize time
- webview `QsGetRows` request duration and cache hit/miss
- SlickGrid window placeholder duration and render duration
- message virtualization metrics
- export/text-view progress and memory use

### STS2 observability

Relevant docs:

- `sqltoolsservice/docs/sts2/OBSERVABILITY.md`
- `sqltoolsservice/docs/sts2/SPEC.md`

STS2 has a central envelope sink, journal capture, live tail, metrics, and diagnostic RPCs:

- `v2/diagnostics.health`
- `v2/diagnostics.state`
- `v2/diagnostics.setCapture`
- `v2/diagnostics.exportLog`

This is a strong base. For query result perf, the missing piece is a structured row-pipeline vocabulary that can explain where time and bytes went without logging row contents.

Recommended STS2 event fields:

- `queryId`
- `connectionId` or digest
- `resultSetOrdinal`
- `pageSeq`
- `rowOffset`
- `rowCount`
- `columnCount`
- `rawApproxBytes`
- `wireBytes`
- `encodedBytes`
- `truncatedCellCount`
- `maxCellBytes`
- `pageRowsLimit`
- `pageBytesLimit`
- `readerMs`
- `encodeMs`
- `creditWaitMs`
- `postMs`
- `cancelRequested`
- `cancelAckMs`
- `terminalMs`

Privacy rule:

- No SQL text in normal logs.
- No cell values.
- No object names unless already classified and redacted by the diagnostics policy.
- Sizes, counts, ordinals, durations, and digests are acceptable diagnostic metadata.

### Perf harness

Relevant files/docs:

- `perftest/packages/perftest-cli/src/scenarios/registry.ts`
- `perftest/packages/perftest-cli/test/queryStudioScenario.test.ts`
- `perftest/docs/DIAGNOSTIC_COLLECTORS.md`
- `perftest/docs/PRODUCT_INSTRUMENTATION.md`

Current Query Studio scenarios:

- `querystudio-open`
- `querystudio-query-10k`
- `querystudio-query-wide` - 300-column result, 100 rows
- `querystudio-query-blob` - VARBINARY(MAX), XML, NVARCHAR(MAX) cells

Current measurement shape:

- `querystudio-query-10k` is the exploratory twin of classic `query-10k-results`.
- It measures through `mssql.queryStudio.resultsRendered`.
- It derives:
  - `mssql.queryStudio.query.toComplete`
  - `mssql.queryStudio.query.toRender`
- `scenario.wallclock` is official for the 10k scenario. Query Studio product metrics are diagnostic/exploratory until baselines mature.

Collectors already available in code include process sampling, extension-host profile, renderer trace, heap snapshot, and STS2 journal copy support. The docs may lag some collector implementation details, so the review plan should verify current collector availability before locking the perf-test matrix.

## Current tests

### STS2 tests

Relevant files:

- `sqltoolsservice/test/sts2/Microsoft.SqlTools.Sts2.UnitTests/Runtime/QueryFlowTests.cs`
- `sqltoolsservice/test/sts2/Microsoft.SqlTools.Sts2.UnitTests/Drivers/WireValueEncoderTests.cs`
- `sqltoolsservice/test/sts2/Microsoft.SqlTools.Sts2.UnitTests/Perf/PerfSmokeTests.cs`
- `sqltoolsservice/docs/sts2/ENGINE-TESTS.md`

Covered:

- happy-path query streaming
- server message passthrough with line
- current database on complete
- max-cell truncation honesty
- exact-bound and one-over-bound truncation
- oversized client max-cell clamp
- ordering and exactly-one-complete invariants
- gapless `pageSeq` and monotonic `rowOffset`
- backpressure window
- cancellation mid-stream
- server error mid-stream
- close while query active
- replay identity
- fake-driver perf smoke: 1 million rows x 10 columns, digest mode, >= 50k rows/sec

Gaps:

- real `SqlClientSession` tests for page-byte enforcement
- sequential large-value read without full materialization
- cancel at max-row cap with real server still producing rows
- large XML/JSON/BLOB query behavior through the real driver
- per-page diagnostic event assertions

### Query Studio tests

Relevant files:

- `vscode-mssql/extensions/mssql/test/unit/queryStudioOrchestrator.test.ts`
- `vscode-mssql/extensions/mssql/test/unit/queryStudioResultsCore.test.ts`
- `vscode-mssql/extensions/mssql/test/unit/queryStudioResultsLayout.test.ts`
- `vscode-mssql/extensions/mssql/test/unit/queryStudioGridOps.test.ts`
- `vscode-mssql/extensions/mssql/test/unit/queryStudioCellDocument.test.ts`
- `vscode-mssql/extensions/mssql/test/unit/queryStudio/rowStore.test.ts`
- `vscode-mssql/extensions/mssql/test/unit/sts2Backend.test.ts`
- `vscode-mssql/extensions/mssql/test/unit/sqlDataPlaneConformance.test.ts`
- `vscode-mssql/extensions/mssql/test/unit/fluentResultGrid.test.ts`

Covered:

- GO splitting, `GO n`, line mapping
- multi-batch execution
- continue-on-error and stop-on-error
- error message synthesis
- parse-only sequencing
- classic message text parity
- cancel mid-stream
- row cap cancellation
- result layout sizing
- cell document detection/formatting
- basic RowStore append/window/spill/cap behavior
- grid transform helpers and keyboard command mapping

Gaps:

- RowStore large-page async/spill perf behavior
- RowStore wide-window diagnostics gating
- message flood rendering and virtualization
- grid window cache hit/miss behavior
- scroll velocity and high-offset window fetches under spill
- export/text-view large-output cancellation and streaming
- BLOB/XML/JSON link behavior for truncated and very large cells

## Current bottleneck hypotheses

These should be validated with the instrumentation plan before broad rewrites.

1. Large cell materialization in STS

`SqlClientSession` calls `GetValue` for every cell. Truncation happens later. Large values can dominate memory, GC, and CPU before any UI code sees them.

2. Page sizing is row-count only

`PageRows = 1000` is acceptable for narrow rows but unsafe for wide cells and many columns. `PageBytes` must become a real bound.

3. Duplicate JSON work

STS2 builds JSON pages. The extension parses them. The extension binding calls `JSON.stringify` for approximate bytes. RowStore spill can call `JSON.stringify` again. This is a major candidate for CPU and allocation reduction.

4. Synchronous spill on extension host

When RowStore spills or materializes pages, synchronous filesystem and JSON parse/stringify can block extension-host responsiveness.

5. Webview message DOM

10,000 messages are fully mapped and rendered. This can slow unrelated typing while the panel is visible.

6. Fixed grid window size

A 50-row window may cause frequent host RPC and placeholder churn for large grids, especially on high-latency or fast-scroll paths.

7. Whole-output secondary views

Text view and export fetch in chunks but build full strings. They should be treated as heavy operations with streaming/progress.

## Recommended optimization plan

### Phase 0: Baseline and attribution

Goal: make every slow query explainable before changing algorithms heavily.

Add diagnostics:

- STS2:
  - SQL command execute-reader start/end
  - first row time
  - result-set schema time
  - page read time
  - page encode time
  - page row count, column count, raw/wire bytes
  - truncated cells per page
  - credit wait time
  - cancel requested, command cancel sent, terminal received
- Extension binding:
  - notification receive time
  - rows compact conversion time
  - approx bytes source
  - sink wait time
  - ack send time
- RowStore:
  - append time
  - spill write/read time and bytes
  - materialize time
  - cache hit/miss
  - getRows total time
  - diagnostics scanning enabled/disabled
- Webview:
  - QsGetRows request begin/end
  - grid window load begin/end
  - placeholder row count
  - visible rows painted
  - messages visible row count and paint time
- Heavy features:
  - text view fetch/format/render
  - export fetch/format/write
  - open XML/JSON cell fetch/format/open
  - plan XML fetch/parse/render

Add diagnostic levels:

- `minimal`: default user-safe lifecycle markers.
- `diagnostic`: timings, counts, byte sizes.
- `verbose`: per-page and per-window details.
- `full`: bounded deep capture for perf tests and active bug investigation.

Do not log cell values or raw SQL text. Use row counts, byte counts, ordinals, durations, status, and digests only.

### Phase 1: Honor limits end to end

Goal: every configured/built-in limit actually constrains memory and wire size.

STS2:

- Plumb `pageRows`, `pageBytes`, `timeoutMs`, and `maxCellBytes` from Query Studio through `ExecuteOptions`, `Sts2Backend`, `Sts2CoreReducer`, `DriverEffectRunner`, and `SqlClientSession`.
- Enforce `PageBytes` during page construction.
- Emit capability flags:
  - `pageRowsHonored`
  - `pageBytesHonored`
  - `maxCellBytesHonored`
  - `queryTimeoutHonored`
- Add tests proving the capabilities are honest.

Query Studio:

- Keep `mssql.queryStudio.maxRowsPerResultSet` as a local UI/cache cap.
- Consider settings for:
  - page row target
  - page byte target
  - max display cell bytes
  - RowStore memory cap
  - RowStore spill cap
- Keep advanced settings hidden or preview-only until stable.

### Phase 2: Large-cell streaming

Goal: large strings/BLOBs should not be fully allocated just to discover they exceed display limits.

STS2 driver:

- Use `CommandBehavior.SequentialAccess`.
- Detect large types from schema when possible.
- For string/XML:
  - stream a prefix up to `maxCellBytes` or `TruncatedPrefixBytes`
  - count UTF-8 bytes honestly
  - compute digest while reading only if digest remains required
- For binary:
  - stream prefix bytes
  - compute digest while reading if required
- For normal scalar types, keep simple `GetValue` path.

Design decision:

- Decide whether truncated cells are display-only or can be opened fully later.
- If full open is required, design a separate cell-value retrieval mechanism. Do not push full BLOBs through the normal grid page path.

### Phase 3: Compact rows on the STS2 wire

Goal: stop rebuilding compact rows in the extension and reduce JSON overhead.

Candidate wire shape:

```json
{
  "queryId": "q-1",
  "resultSetId": 0,
  "pageSeq": 12,
  "rowOffset": 12000,
  "rowCount": 1000,
  "columns": 37,
  "approxBytes": 240000,
  "compact": {
    "values": [[1, "a"], [2, "b"]],
    "nullBitmap": "base64...",
    "typeHints": ["int", "nvarchar"]
  },
  "stats": {
    "truncatedCells": 0,
    "encodeMs": 3
  }
}
```

Benefits:

- no extension-side rows-to-compact conversion
- no extension-side `JSON.stringify(params.rows).length`
- more accurate bytes
- type hints and null bitmap computed once

Compatibility:

- Add as a capability-gated STS2 protocol extension.
- Keep existing rows shape until both sides negotiate the compact shape.

### Phase 4: RowStore spill and cache improvements

Goal: make random access responsive under large result sets.

Changes:

- Replace synchronous spill with async or worker-backed spill.
- Store compact serialized bytes directly when possible.
- Track pages by result-set id and page sequence with explicit indexes.
- Add a window cache on top of page cache for repeated grid requests.
- Reduce getRows work in normal diagnostics mode:
  - build null bitmap because UI needs it
  - skip null/non-empty counting unless verbose diagnostics are active
- Add spill churn protection:
  - avoid materialize-then-immediately-evict loops
  - use a two-queue or protected LRU policy for pages fetched by scrolling
- Consider per-result-set memory partitions so one huge result set does not evict all other visible result sets.

### Phase 5: Webview render improvements

Goal: make the UI remain instant while results stream, while scrolling, and while messages are huge.

Grid:

- Increase or adapt window size based on viewport height and scroll velocity.
- Prefetch next/previous viewport more aggressively for fast wheel scroll.
- Add explicit webview markers for window request, receive, row conversion, and paint.
- Ensure auto-size runs once per result-set identity and sample only bounded rows.

Messages:

- Virtualize messages.
- Render only visible rows.
- Keep `Copy All` as a host-generated string on demand.
- Batch message appends to React on animation frames or short intervals.

Tabs:

- Keep Results hidden when no result sets exist.
- Keep Messages always available for runs.
- Activate Messages on error.
- Make plan tabs lazy-rendered.

### Phase 6: Heavy secondary features

Text view:

- Convert to a streaming/generated document or virtual text viewer.
- Add progress and cancel.
- Cap or confirm large conversions.

Export:

- Stream directly to disk.
- Add progress and cancel.
- Keep small-result in-memory fast path if it stays simpler and faster.

XML/JSON:

- Avoid sync pretty-print for large documents.
- Show raw first, format on demand, or format asynchronously.

Plans:

- Cache plan parse results.
- Parse heavy plans asynchronously.
- Add dedicated plan-perf markers.

## Proposed perf-test matrix

Baseline scenarios to keep:

- Query Studio open
- Query Studio 10k rows
- Query Studio 300 columns x 100 rows
- Query Studio BLOB/XML/NVARCHAR(MAX)

Add result-shape scenarios:

1. Narrow large row count

- 100k rows x 5 columns
- 1M rows x 5 columns
- validate first render, scrolling to middle/end, memory, row cap behavior

2. Wide rows

- 100 rows x 300 columns
- 1000 rows x 300 columns
- validate first render, horizontal scroll, copy small selection

3. Large text cells

- 100 rows x JSON 64 KiB
- 100 rows x XML 64 KiB
- 20 rows x JSON/XML 1 MiB+
- validate display clamp, links, open-cell behavior, truncation honesty

4. Binary/BLOB cells

- 20 rows x varbinary(max) 1 MiB+
- validate no DOM payload explosion and no full-value materialization after driver fix

5. Many messages

- 10k PRINT messages, no result sets
- visible messages pane while typing in editor
- hidden pane while typing
- copy-all messages

6. Long-running query

- delayed first row
- slow rows after first page
- cancel before first row
- cancel mid-stream
- cancel at row cap

7. Multiple result sets

- 10 result sets x small rows
- 100 result sets x small rows
- mixed result/message/plan sets
- validate lazy grid mounting and tab stability

8. Export/text view

- CSV export 100k rows
- JSON export 100k rows
- text view 100k rows
- cancel/progress once streaming implementation exists

Collectors to use for full diagnostics:

- product markers/session journal
- STS2 envelope journal
- extension-host CPU profile
- renderer trace
- process sampler
- heap snapshot on regression or explicit diagnostic pass
- SQL Server timing/XEvents where configured

Success metrics:

- time to submit
- time to first result-set metadata
- time to first row page
- time to query complete
- time to first visible rows painted
- time to results rendered
- extension host peak working set
- STS peak working set
- renderer main-thread long tasks
- row-window cache hit rate
- spill bytes and spill read/write duration
- cancel acknowledgement and terminal time
- row cap terminal time

## Test plan additions

STS2 unit/integration tests:

- page bytes split pages even when row count is below `PageRows`
- page rows and page bytes both honored, with bytes taking precedence
- `timeoutMs` reaches `SqlCommand.CommandTimeout`
- compact rows capability emits null bitmap/type hints and approx bytes
- sequential large string truncation does not allocate full value in a fake/controlled reader test, if practical
- cancel while credit wait is active
- credit window remains bounded with page-byte split

Query Studio unit tests:

- `RowStore.getRows` normal mode skips expensive verbose counts
- spill read/write markers and stats update
- spill corruption marks result set corrupt and returns short windows
- message virtualization renders bounded rows for 10k messages
- copy-all messages includes timestamps without requiring all rows in DOM
- text view refuses/confirms large sets or streams once implemented
- export streams in chunks and does not build a full string above threshold
- grid window size is adaptive/configured for Query Studio
- `QsRowsAppendedNotification` batching preserves final row counts

Perftest scenario tests:

- registry assertions for every new Query Studio scenario
- marker registration/conformance for every new marker
- head-to-head classic/Query Studio comparisons stay diagnostic until baselines mature

## API design guidance

Keep the API simple. Avoid a large grid-cache protocol in STS2 unless future requirements force server-side random access.

Recommended minimal execution options:

```ts
interface ExecuteOptions {
    pageRows?: number;
    pageBytes?: number;
    maxCellBytes?: number;
    timeoutMs?: number;
    priority?: "interactive" | "background";
    commandKind?: "user" | "metadata" | "system";
    tag?: string;
}
```

Recommended capabilities:

```ts
interface QueryCapabilities {
    pageRowsHonored: boolean;
    pageBytesHonored: boolean;
    maxCellBytesHonored: boolean;
    queryTimeoutHonored: boolean;
    compactRows: boolean;
    estimatedPlan: boolean;
    actualPlan: boolean;
}
```

Recommended row page metadata:

```ts
interface RowsPageStats {
    approxBytes: number;
    wireBytes?: number;
    rowCount: number;
    columnCount: number;
    truncatedCellCount?: number;
    buildMs?: number;
    encodeMs?: number;
}
```

Do not add random-access `getRows` to STS2 unless the driver/runtime owns a durable result cache or server cursor lifecycle. Today Query Studio already needs independent split-view grid state, webview windowing, export state, and spill cleanup, so extension ownership remains the pragmatic place.

## Open design questions

1. Should Query Studio ever offer full open/download for cells truncated by STS2?

If yes, normal result pages are not enough. We need a separate full-cell or result-artifact retrieval design with clear lifecycle and memory bounds.

2. Should row cap cancel the server query or keep the query running while the client discards rows?

Current behavior cancels on cap. That is probably the best default because it protects the user and the client, but the message should be explicit: no more rows will be displayed and the query was canceled because the configured cap was reached.

3. Should page byte defaults differ for interactive and export workloads?

Interactive rendering wants smaller pages for fast first paint and cancellation. Export may want larger pages for throughput. This can be solved with `commandKind`/`priority` presets without complicating the public API too much.

4. Do we need a worker for RowStore?

Async fs may be enough for spill, but JSON parse/stringify CPU remains on the extension host. If compact serialized frames still require heavy parsing, a worker thread can isolate it.

5. Should message history stay in webview state?

For huge message streams, the host should remain the source of truth and the webview should request visible windows plus copy-all text on demand.

## Recommended first implementation slice

The first slice should be small but highly diagnostic:

1. Add missing row-pipeline markers and diagnostics:
   - STS page build/encode/credit wait
   - extension compact conversion/sink wait/ack
   - RowStore append/spill/materialize/getRows cache stats
   - webview QsGetRows/window paint
2. Stop extension-side `JSON.stringify(params.rows).length` by sending page byte estimates from STS2.
3. Gate `RowStore.getRows` expensive cell counts behind verbose diagnostics.
4. Virtualize `MessagesView`.
5. Add perf scenarios for 10k messages and 100k narrow rows.
6. Add unit tests for the above behavior.

The second slice should address true large-cell safety:

1. Plumb and honor `pageRows`, `pageBytes`, `timeoutMs`, and `maxCellBytes` end to end.
2. Enforce page bytes in `SqlClientSession`.
3. Add sequential large-value read/truncate for strings/XML/binary.
4. Add tests and perf scenarios proving STS memory stays bounded for BLOB/XML/JSON workloads.

The third slice should reduce serialization cost:

1. Add capability-gated compact row pages on the STS2 wire.
2. Store compact serialized page frames directly in RowStore spill.
3. Tune grid window sizing and cache policy using the new markers.
