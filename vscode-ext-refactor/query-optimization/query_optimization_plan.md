# Query Studio Query Execution and Results Optimization Plan
## End-to-end design for massive results, fast rendering, bounded memory, and observable reliability

**Status:** proposed implementation plan for `dev/query`.

**Primary repos:**

- `microsoft/vscode-mssql`, branch `dev/query`
- `microsoft/sqltoolsservice`, branch `dev/query`
- `perftest`, branch `dev/query`

**Primary input:** `query_editor_results_execution.md`, which is the detailed current-state review. This plan intentionally does not restate every current implementation detail. It turns that review into a concrete build plan for a coding agent.

**Scope:** Query Studio execution, STS2 row streaming, extension-host result storage, webview grid rendering, messages, export/text/cell-document/plan handling, diagnostics, and perf-test coverage.

---

## 0. Executive decision

Keep the current ownership split and make it sharp:

```text
SQL Server / backend
  owns: execution, cancellation, TDS reading, forward-only result streaming,
        server messages, page-size enforcement, cell truncation honesty

STS2 / SQL Data Plane
  owns: session lifecycle, one-active-query discipline, credit/backpressure,
        ordered notifications, typed page contracts, protocol invariants

Query Studio extension host
  owns: random access, result-run lifetime, spill/cache policy, row caps,
        export/text/cell-document access, plan state, message history

Query Studio webview
  owns: visible viewport state, adaptive prefetch, rendering cache,
        DOM virtualization, keyboard/mouse UX, paint attribution
```

Do **not** move grid random access into STS2 unless STS2 intentionally grows a durable result artifact or cursor lifecycle. The best path is a high-throughput forward stream into a bounded, indexed, extension-owned result store. That keeps Query Studio portable: a web-hosted SQL Data Plane backend, a fake backend, or a future non-STS backend only needs to implement the streaming contract, while Query Studio keeps the same near-renderer optimizations and random-access store.

The dragon to slay is not one giant beast. It is a flock of tiny allocation crows: full-value materialization, row-count-only pages, duplicate JSON serialization, synchronous spill, unbounded message DOM, whole-output secondary views, and missing per-stage attribution.

---

## 1. Design principles

### 1.1 Hard invariants

1. **Rows never enter coarse state.** `QsState` may include counts, summaries, status, and metadata. It must never carry result cells.
2. **The renderer never owns the dataset.** The webview may cache viewport windows, but the extension host remains the source of truth for row data.
3. **The extension host never scans a result set to answer a viewport request.** Window fetch is indexed by result-set id, row range, and later column range.
4. **Every limit is honest end to end.** `pageRows`, `pageBytes`, `maxCellBytes`, row cap, memory cap, spill cap, and timeout must either be honored or clearly reported as unsupported.
5. **Backpressure means real acceptance.** STS2 acks only after Query Studio has accepted the page into a bounded store path. With async spill, “accepted” means either memory-admitted under cap or enqueued behind a bounded durable/spill queue that will apply backpressure when saturated.
6. **Large values are never read fully just to truncate them.** Any driver path for `nvarchar(max)`, `varchar(max)`, `xml`, `varbinary(max)`, `image`, or provider-specific huge values must stream or explicitly report that it cannot.
7. **Secondary views are heavy operations.** Export, text view, open-cell formatting, and plan parsing use progress, cancellation, thresholds, and streaming. They do not run as cheap tab toggles over arbitrarily large data.
8. **Diagnostics are counts, timings, byte sizes, ordinals, statuses, and digests.** No SQL text, cell values, row payloads, connection strings, tokens, or raw object names in normal diagnostics.

### 1.2 Performance shape goals

These are initial targets for dogfood and perf harness calibration, not permanent product promises:

| Area | Target |
|---|---|
| First visible rows after first row page accepted | p95 under 100 ms on local dev hardware |
| Warm viewport fetch from RowStore memory | p95 under 16 ms host-side |
| Spill-backed viewport fetch | p95 under 75 ms for ordinary pages, under 150 ms for wide pages |
| Renderer long task from grid window receive to paint | no task over 50 ms for default scenarios |
| Message pane with 10k messages | typing/editor latency indistinguishable from hidden pane |
| Extension-host row ingest | no unbounded memory growth, bounded by store limits plus at most in-flight windows/pages |
| STS2 large cell query | no full large-cell allocation on the hot path after streaming reader slice lands |
| Cancel after row cap | terminal status and user message within bounded deadline |

### 1.3 Tiered optimization model

The feature must work across STS2 desktop, fake backends, and future web-hosted backends. Build in tiers:

```text
Tier R0: Renderer-near cache
  small viewport cache, adaptive prefetch, virtualization, column projection
  works everywhere, no STS dependency

Tier R1: Extension-host ResultStore
  indexed row pages, bounded memory, spill provider, export/text/cell access
  works with any forward-streaming SQL Data Plane backend

Tier R2: SQL Data Plane / STS2 stream
  page bytes, max cell bytes, compact pages, credit/backpressure, typed values
  implemented by STS2 first, required from other backends over time

Tier R3: Driver/backend source
  SequentialAccess, type-specific large-value readers, page-byte construction,
  cancellation truth, optional large-cell artifact channel
```

If a future web-hosted backend cannot use Node `fs`, it still gets Tier R0 and R1 through a web store provider such as IndexedDB or Origin Private File System. If a backend cannot honor compact pages yet, the extension binding adapts legacy rows into the same `ResultStore` API.

---

## 2. Target architecture

```text
Query Studio webview
  QsResultGridSurface
  MessagesVirtualList
  QueryStudioResultsTextView / export / cell docs / plans
      |
      | QsGetRowsV2 / QsGetMessagesWindow / QsExport / QsOpenCellDocument
      v
QueryStudioController
      |
      v
ExecutionHost
  ExecutionOrchestrator
  ResultRunRegistry
  ResultStoreV2
      |
      | appendRowsPage / getCellWindow / streamRows / openCell / stats
      v
SQL Data Plane ISqlSession.execute
      |
      v
Sts2Backend
  capability negotiation
  compact or legacy rows adaptation
  ordered sink queue
  ack after bounded store acceptance
      |
      v
STS2 Core + Runtime
  reducer lifecycle and credit
  query options honored
  row-pipeline diagnostics
      |
      v
SqlClientSession
  SequentialAccess
  byte-aware page builder
  type-specific large value readers
      |
      v
SQL Server
```

The central seam is the new `ResultStoreV2`. It is not a giant database. It is a narrow, indexed, bounded cache for one Query Studio run.

---

## 3. ResultStoreV2 design

### 3.1 Goals

`RowStore` is already in the right ownership layer, but it needs to become a more explicit storage engine:

- indexed by result set, page sequence, row range, and eventually column projection;
- bounded by memory/spill limits;
- async-spill capable;
- observable at append, eviction, spill, materialization, and window-serving points;
- portable across Node desktop and web extension hosts;
- able to serve grid windows, export streams, text generation, cell documents, and plan XML without each feature inventing a row retrieval loop.

### 3.2 API

Add under:

```text
extensions/mssql/src/queryStudio/results/resultStore.ts
extensions/mssql/src/queryStudio/results/resultStoreTypes.ts
extensions/mssql/src/queryStudio/results/resultStoreStats.ts
extensions/mssql/src/queryStudio/results/pageStores/nodeFilePageStore.ts
extensions/mssql/src/queryStudio/results/pageStores/memoryPageStore.ts
extensions/mssql/src/queryStudio/results/pageStores/webIndexedDbPageStore.ts   // later / web host
```

Suggested interface:

```ts
export interface ResultStoreV2 extends DisposableLike {
    beginResultSet(meta: ResultSetMetadata): void;

    appendPage(page: ResultAppendPage): Promise<ResultAppendResult>;

    endResultSet(resultSetId: string, info: ResultSetEnded): void;

    getWindow(req: CellWindowRequest): Promise<CellWindowResult>;

    getCell(req: CellLookupRequest): Promise<CellLookupResult>;

    streamRows(req: RowStreamRequest): AsyncIterable<CellWindowResult>;

    getSummary(resultSetId: string): ResultSetSummary | undefined;

    getRunSummary(): ResultRunSummary;

    getStats(): ResultStoreStats;
}

export interface ResultAppendPage {
    readonly resultSetId: string;
    readonly pageSeq: number;
    readonly rowOffset: number;
    readonly rowCount: number;
    readonly columnCount: number;
    readonly compact: CompactPage;
    readonly stats: RowsPageStats;
    readonly sourceEncoding: "legacyRows" | "compactJson" | "compactBinary";
}

export interface ResultAppendResult {
    readonly accepted: boolean;
    readonly truncatedReason?: "maxRowsPerResultSet" | "memoryLimit" | "spillLimit";
    readonly backpressureMs?: number;
}

export interface CellWindowRequest {
    readonly resultSetId: string;
    readonly rowStart: number;
    readonly rowCount: number;
    /** Optional. Omitted means all columns for compatibility. */
    readonly columnStart?: number;
    readonly columnCount?: number;
    /** Optional sparse projection for pinned columns or copy selections. */
    readonly includeColumns?: readonly number[];
    readonly reason: "grid" | "copy" | "text" | "export" | "cellDocument" | "plan" | "diagnostic";
    readonly diagnostics?: "minimal" | "diagnostic" | "verbose";
}
```

Compatibility path: keep `RowStore` as an adapter over `ResultStoreV2` until the controller and tests move. Do not rewrite every caller at once. First slice can implement `ResultStoreV2` behind the existing `RowStore.getRows` API.

### 3.3 Page index

Per result set:

```ts
interface ResultSetPageIndex {
    readonly resultSetId: string;
    readonly columns: readonly QsResultColumn[];
    rowCount: number;
    complete: boolean;
    truncatedReason?: string;
    corrupt: boolean;
    pagesBySeq: StoredPageRef[];
    rowOffsets: number[];       // aligned with pagesBySeq for binary search
    pageSeqToIndex: Map<number, number>;
    typeHints?: string[];
    perColumnStats?: ColumnSampleStats[];
}

interface StoredPageRef {
    pageSeq: number;
    rowOffset: number;
    rowCount: number;
    approxBytes: number;
    encodedBytes?: number;
    columnCount: number;
    memory?: CompactPage;
    spill?: SpillFrameRef;
    /** Built once at append, not during every window fetch. */
    stats: PageLocalStats;
}

interface PageLocalStats {
    nullCellCount?: number;
    nonEmptyCellCount?: number;
    truncatedCellCount?: number;
    linkableCellCount?: number;      // xml/json/truncated/openable bitset count
    nullBitmap?: string;             // page-local passthrough or compacted copy
    truncatedBitmap?: string;        // optional, for cell badges without scanning values
    linkableBitmap?: string;         // optional, for XML/JSON/link styling
}
```

Rules:

- Use binary search over `rowOffsets` to find the first page. Never linearly scan from page 0.
- `getWindow` only materializes pages overlapping the requested row range.
- In normal diagnostics mode, `getWindow` does not count null/non-null/non-empty cells. Those stats are computed at append or only in verbose diagnostics.
- Store per-page bitsets for expensive UI decorations when needed. The grid should not parse every value in a viewport to decide whether a cell is XML, JSON, truncated, or null.
- Future column projection should avoid returning off-screen cells for wide grids. A 50-row x 300-column page fetch is a tiny spreadsheet avalanche when only 12 columns are visible.

### 3.4 Spill provider

Create a storage abstraction:

```ts
export interface ResultPageStore extends DisposableLike {
    readonly kind: "memory" | "nodeFile" | "indexedDb" | "opfs" | "backendArtifact";
    writePage(page: EncodedPageFrame): Promise<SpillFrameRef>;
    readPage(ref: SpillFrameRef): Promise<EncodedPageFrame>;
    deleteAll(): Promise<void>;
    stats(): PageStoreStats;
}
```

Initial implementations:

1. `NodeFilePageStore`: async file-backed store for desktop extension host.
2. `MemoryPageStore`: tests and small runs.
3. `WebIndexedDbPageStore`: later, for web extension host.
4. `BackendArtifactPageStore`: future, only if a backend owns durable artifacts.

Frame format v2:

```text
magic:       "QSRP2\0"
version:     uint16
flags:       uint16
headerLen:   uint32
bodyLen:     uint32
bodyHash:    uint128 or sha256 digest prefix
headerJson:  { resultSetId, pageSeq, rowOffset, rowCount, columnCount,
               encoding, approxBytes, stats }
body:        compact-json-utf8 initially; compact-binary later
```

Start with compact JSON body if fastest to implement, but do not keep re-stringifying object graphs on spill. The store should receive an encoded page frame when possible and spill that exact frame.

### 3.5 Async spill and backpressure

The current synchronous spill shape is simple but blocks the extension host. Replace it with a bounded queue:

```ts
class AsyncSpillManager {
    enqueue(pageRef: StoredPageRef, frame: EncodedPageFrame): Promise<SpillFrameRef>;
    readonly pendingBytes: number;
    readonly pendingPages: number;
    readonly saturated: boolean;
}
```

Append behavior:

1. Add page to memory if under cap.
2. If memory exceeds soft cap, select eviction candidates and enqueue spill.
3. Do not remove the in-memory page until the spill write succeeds.
4. If memory exceeds hard cap or spill queue exceeds `maxPendingSpillBytes`, `appendPage` awaits spill progress. This is the backpressure point that delays STS2 ack.
5. If spill fails or spill cap is exceeded, reject the append with `memoryLimit` or `spillLimit`. The orchestrator cancels the query and emits a clear user message.

This gives the query stream a pressure gauge instead of a trapdoor.

### 3.6 Cache policy

Use two layers:

1. **Page cache:** memory-resident decoded `CompactPage`s. Split into protected and probationary queues.
2. **Window cache:** renderer/request-shaped `CellWindowResult`s for repeated viewport requests and copy selections.

Recommended policy:

```text
append pages → probationary
visible window pages → protected
fast-scroll read-ahead pages → probationary
copy/export pages → non-protected streaming reads
plan/cell-open page → protected briefly
```

This avoids a large export evicting the active viewport. Little goblin rule: work done for a background export must not steal the chair from the cell the user is staring at.

### 3.7 Column projection

Add `columnStart`/`columnCount` to the webview row-window request. Keep old all-column behavior as fallback.

The grid should request:

```text
visible rows + vertical buffer
visible columns + horizontal buffer + pinned columns
```

Benefits:

- wide result sets do not pay all-column transfer costs for every vertical scroll;
- cell-value decoding happens only for visible columns;
- `nullBitmap` and display-class bitsets can be projected to the returned column range.

Implementation detail: RowStore may store row-major full pages, but `getWindow` returns only projected cells. Later compact-binary pages can be columnar or hybrid without changing the RPC.

---

## 4. STS2 and SQL Client optimizations

### 4.1 Query options contract

The current SQL Data Plane API already has the right shape. Make it fully honored and testable:

```ts
interface ExecuteOptions {
    pageRows?: number;
    pageBytes?: number;
    maxCellBytes?: number;
    timeoutMs?: number;
    priority?: "interactive" | "background";
    commandKind?: "user" | "metadata" | "plan" | "parse" | "replay" | "centralUpload";
    tag?: string;
}
```

Capabilities should distinguish configured, requested, and honored:

```ts
interface QueryCapabilities {
    pageRowsHonored: boolean;
    pageBytesHonored: boolean;
    maxCellBytesHonored: boolean;
    queryTimeoutHonored: boolean;
    compactRows: boolean;
    compactBinaryRows?: boolean;
    fullCellArtifacts?: boolean;
}
```

Recommended default presets:

| Workload | `pageRows` | `pageBytes` | `maxCellBytes` | Notes |
|---|---:|---:|---:|---|
| interactive grid | 512 to 1000 | 256 KiB | 1 MiB or lower | fast first paint, bounded frames |
| metadata query | 1000 | 256 KiB | 256 KiB | never huge values expected |
| export | 2048 to 8192 | 1 to 4 MiB | same as grid unless full export is designed | throughput over first paint |
| text view generation | 2048 | 1 MiB | display-focused | cancellable heavy operation |
| plan XML | 1 row/page | bounded by max cell or plan policy | plan policy | avoid mixing plan with ordinary grid flow |

Do not expose all knobs to normal users immediately. Put them behind internal/preview settings or perftest configuration first.

### 4.2 Page-byte enforcement

Add a byte-aware page builder in `SqlClientSession` or a small helper under the SQL Client driver:

```csharp
internal sealed class SqlRowsPageBuilder
{
    public bool TryAddRow(EncodedRow row, out RowsPage? completedPage);
    public RowsPage? Complete();
}
```

Rules:

- `PageRows` and `PageBytes` both apply. Whichever limit is reached first ends the page.
- A single row larger than `PageBytes` may be emitted as a one-row oversized page only if it remains below `MaxFrameBytes` after truncation wrappers.
- If a single row cannot fit below frame bounds even after truncation, fail the query with a clear bounded-result error. Do not send a frame that risks transport failure.
- Page byte calculation should measure the encoded wire body or a close upper bound, not `object.ToString()` or a raw provider-size guess.
- Emit `RowsPageStats` alongside the page: `rowCount`, `columnCount`, `encodedBytes`, `rawApproxBytes`, `truncatedCellCount`, `buildMs`.

### 4.3 SequentialAccess and large-value readers

Use `CommandBehavior.SequentialAccess` for interactive query execution once compatibility tests pass.

Large-value reader policy:

| SQL/provider family | Reader path | Stored grid value |
|---|---|---|
| `nvarchar(max)`, `varchar(max)`, `ntext`, `text`, large JSON-ish text | `GetChars` or `GetTextReader` | UTF-8-safe prefix + truncation metadata |
| `xml` | `GetTextReader` or `GetChars` | XML prefix + truncation metadata, type hint `xml` |
| `varbinary(max)`, `image` | `GetBytes` or `GetStream` | base64/hex prefix + truncation metadata |
| ordinary scalars | `GetValue` | typed scalar/wrapper |
| provider-specific CLR/UDT | safe string wrapper with byte cap | provider wrapper, not raw object graph |

Digest decision:

- If the full digest is kept, compute it while streaming and never after full materialization.
- If streaming digest is too costly for default mode, use `digestPolicy: "none" | "prefix" | "full"`. Default can be `prefix` for display, `full` only in diagnostic/perftest or when needed for full-cell artifact identity.
- Truncation must remain honest even without full digest: include `originalBytes` when known, `prefixBytes`, and `truncationReason`.

SequentialAccess caution:

- Sequential readers require cells to be read in ordinal order. The page builder naturally does this, but any future “skip hidden columns at source” optimization must not break this rule. Column projection belongs in `ResultStore.getWindow`, not in `SqlDataReader` for the first versions.

### 4.4 Compact row wire v2

Current STS2 emits `rows: unknown[][]`, the extension converts to `CompactPage`, and the extension recomputes `approxBytes`. Add capability-gated compact rows:

```jsonc
{
  "eventType": "rows",
  "resultSetId": 0,
  "pageSeq": 12,
  "rowOffset": 12000,
  "rowCount": 512,
  "columnCount": 37,
  "approxBytes": 240000,
  "encodedBytes": 218400,
  "encoding": "compact-json-v1",
  "compact": {
    "values": [[1, "a"], [2, "b"]],
    "nullBitmap": "base64...",
    "typeHints": ["number", "string"]
  },
  "stats": {
    "truncatedCellCount": 0,
    "buildMs": 2.1,
    "encodeMs": 3.4,
    "creditWaitMs": 0.6
  }
}
```

Benefits:

- one compacting step instead of two;
- no extension-host `JSON.stringify(params.rows).length`;
- type hints and null bitmap produced where column metadata is already known;
- better instrumentation and page-byte enforcement;
- a clean stepping stone to compact binary.

Compatibility:

- STS2 advertises `compactRows: true` and `pageBytesHonored: true` separately.
- `Sts2Backend` supports legacy and compact notifications until all supported STS2 builds negotiate compact.
- Fake backend and conformance tests must support both shapes.

### 4.5 Compact binary is optional, not first slice

A binary row-page encoding can reduce CPU and payload size, but it is not the first optimization. First remove duplicate JSON and synchronous spill. Then measure.

Future candidate:

```text
CompactBinaryPage v1
  header: resultSetId, pageSeq, rowOffset, rowCount, columnCount, offsets
  columns: type code, nullable, display type
  null bitmap
  value block: varints + UTF-8 + base64-free binary prefixes
```

Only build it if central observability shows JSON encode/decode remains a top contributor after compact JSON and spill fixes. Otherwise, binary becomes an ornate little sword nobody needed.

---

## 5. Extension binding and backpressure

### 5.1 Sts2Backend changes

Files:

```text
extensions/mssql/src/services/sts2/sts2Backend.ts
extensions/mssql/src/services/sts2/wire/v2.ts
extensions/mssql/src/services/sqlDataPlane/api.ts
extensions/mssql/test/unit/sts2Backend.test.ts
extensions/mssql/test/unit/sqlDataPlaneConformance.test.ts
```

Tasks:

1. Send all supported `ExecuteOptions`: `pageRows`, `pageBytes`, `maxCellBytes`, `timeoutMs`.
2. Read negotiated capabilities from `v2/initialize` and expose them in `SqlBackendCapabilities`.
3. Add legacy-row and compact-row adapters behind a single `RowsPage` output.
4. Remove extension-side approximate-byte `JSON.stringify` when STS2 sends `approxBytes`/`encodedBytes`. Fallback to measured compatibility estimate only when capability is absent.
5. Add timings:
   - notification received;
   - wire validation;
   - compact conversion;
   - sink wait;
   - ack sent;
   - queue depth;
   - orphan-buffer delay.
6. Preserve protocol-invariant enforcement: metadata before rows, gapless `pageSeq`, monotonic `rowOffset`, single terminal.

### 5.2 Sink semantics with async ResultStore

Current design acks after `sink.onRowsPage` resolves. Keep that rule. Change what the Query Studio sink does:

```ts
async onRowsPage(page: RowsPage): Promise<void> {
    const result = await resultStore.appendPage(convert(page));
    if (!result.accepted) {
        await handleRowStoreLimit(result);
        return;
    }
    notifyRowsAppendedBatched(page.resultSetId, page.rowCount);
}
```

If `ResultStore.appendPage` is waiting on spill queue capacity, STS2 credit is held. That is correct. The query stream should slow rather than turn the extension host into a memory bonfire.

### 5.3 Notification coalescing

Replace per-page webview notifications with coalesced batches:

```ts
interface QsRowsChangedNotification {
    runId: string;
    resultSets: Array<{
        resultSetId: string;
        rowCount: number;
        appendedRows: number;
        complete: boolean;
        truncatedReason?: string;
    }>;
}
```

Policy:

- send at most once per animation frame or `STATE_PUSH_MIN_INTERVAL_MS`, whichever is appropriate;
- always flush on result-set completion, query completion, cancel, and error;
- keep coarse `QsState` push independent but deduped.

Messages should use the same approach: store in host, notify counts/ranges, let webview request visible windows.

---

## 6. Webview grid design

### 6.1 Adaptive windowing

Current fixed row windows are too rigid for both tiny and huge grids. Use viewport-driven windows:

```ts
const visibleRows = Math.ceil(viewportHeight / rowHeight);
const rowBuffer = clamp(visibleRows * velocityFactor, visibleRows, visibleRows * 4);
const requestRows = clamp(visibleRows + rowBuffer * 2, 64, 1000);
```

Scroll velocity policy:

| Scroll state | Prefetch |
|---|---|
| idle / keyboard row movement | current viewport + one buffer |
| slow wheel | current + previous + next viewport |
| fast wheel / scrollbar drag | skip intermediate requests, fetch landing window first |
| page up/down | landing window + one direction buffer |
| jump to end | cancel stale windows, fetch target window immediately |

### 6.2 Column projection

For wide results, add a column-aware request:

```ts
interface QsGetRowsV2Request {
    resultSetId: string;
    rowStart: number;
    rowCount: number;
    columnStart?: number;
    columnCount?: number;
    includeColumns?: number[];
    reason: "grid" | "copy" | "export" | "text" | "cellDocument" | "plan";
}
```

The grid data source should know:

- visible row range;
- visible column range;
- pinned/frozen columns;
- selected copy range;
- active editor row/column focus.

Request visible columns plus a small horizontal buffer. When all-column mode is required for copy/export, use streaming, not viewport RPC.

### 6.3 Renderer cache

The renderer keeps a tiny cache:

```ts
interface GridWindowCacheKey {
    resultSetId: string;
    rowStart: number;
    rowCount: number;
    columnStart: number;
    columnCount: number;
    generation: number;
}
```

Rules:

- store only decoded display values for visible windows;
- cap by cells or bytes, not just window count;
- clear on result-set identity change;
- cancel stale in-flight requests on scroll jumps;
- render placeholders while waiting, but measure placeholder duration.

### 6.4 Cell rendering policy

Introduce a cheap, shared display-cell contract for webview windows:

```ts
interface GridDisplayCell {
    readonly text: string;
    readonly kind: "null" | "text" | "number" | "boolean" | "datetime" | "binary" | "xml" | "json" | "truncated" | "unsupported";
    readonly flags?: number; // null/truncated/openable/error/linkable
}
```

The webview should not repeatedly infer XML/JSON/truncated status from arbitrary values. The extension can send flags computed from page metadata or cheap structural checks. Keep raw compact values in the host for export/open-cell, not in the DOM.

### 6.5 Autosize and layout

Column autosize policy:

- sample metadata/header and only the first N rendered rows, not the whole result set;
- never inspect more than `autosize.maxCells` per autosize pass;
- run autosize once per result-set generation unless the user explicitly re-runs it;
- for very wide grids, autosize only visible columns plus pinned columns;
- measure autosize cost separately from row-window fetch.

### 6.6 First-visible-paint marker

Add a marker that closes the user-perceived loop more precisely than “results rendered”:

```text
mssql.queryStudio.grid.firstVisibleRowsPainted
  attrs: runIdDigest, resultSetOrdinal, rows, columnsVisible, fromCache, fromSpill, elapsedSinceSubmitMs
```

Do not make this marker official until the perf harness proves stability. It is the lantern in the tunnel, not the gate yet.

---

## 7. Messages design

### 7.1 Host-owned message store

Move large message history out of webview React state as the authoritative store.

```ts
interface MessageStore {
    append(rows: QsMessageRow[]): void;
    getWindow(start: number, count: number): QsMessageWindow;
    getText(req: MessageTextRequest): Promise<string | TempFileRef>;
    summary(): MessageSummary;
}
```

The webview receives:

```ts
interface QsMessagesChangedNotification {
    runId: string;
    messageCount: number;
    appendedCount: number;
    hasErrors: boolean;
    firstErrorIndex?: number;
}
```

Then it requests visible rows through `QsGetMessagesWindow`.

### 7.2 Virtualized rendering

Replace `preparedMessages.map(...)` DOM rendering with a virtual list:

- fixed row height for most rows;
- variable height only for multi-line server errors, measured lazily;
- timestamps formatted only for visible rows;
- navigation links created only for visible rows;
- auto-scroll to bottom only when the user is already near bottom.

### 7.3 Copy all

`Copy All` should not map every message in the DOM. It calls host-side text generation:

```ts
QsGetMessagesTextRequest {
    runId: string;
    includeTimestamps: boolean;
    range?: { start: number; count: number };
}
```

For very large outputs, host can write a temp file and then copy or open it depending on VS Code constraints.

---

## 8. Export, text view, cell documents, and plans

### 8.1 Export streaming

Replace large-result in-memory export with a streaming writer.

Files:

```text
extensions/mssql/src/queryStudio/resultExport.ts
extensions/mssql/src/queryStudio/results/exportWriters.ts
extensions/mssql/src/queryStudio/results/exportController.ts
```

Design:

```ts
interface ResultExportJob {
    id: string;
    runId: string;
    resultSetId: string;
    format: "csv" | "json" | "insert";
    status: "running" | "completed" | "canceled" | "failed";
    progress: { rowsWritten: number; bytesWritten: number; totalRows?: number };
    cancel(): void;
}
```

Rules:

- small exports can keep the current simple path under a byte threshold;
- large exports use Node streams or a `WritableResultArtifact` abstraction;
- JSON exports stream `[` then rows with comma handling, then `]`;
- CSV exports stream rows with RFC-compatible escaping and selected encoding;
- INSERT exports stream batches, with configurable rows per statement;
- cancellation is checked between RowStore chunks;
- progress updates are rate-limited.

### 8.2 Text view

A full text rendering of a large result is an export wearing a trench coat. Treat it as such.

Options:

1. **Small result:** current Monaco string path.
2. **Medium result:** generated temp text document with progress.
3. **Huge result:** virtual text viewer or prompt to export to file.

Implementation policy:

- do not compute widths across all rows synchronously;
- use a bounded sample for initial widths;
- refine widths only if the user requests full formatting;
- do not allocate one complete string for 100k+ rows in the webview.

### 8.3 Cell documents

Truncated cell behavior must be explicit:

| Cell state | UI label | Behavior |
|---|---|---|
| not truncated, under format threshold | Open | fetch cell from ResultStore, optional pretty format |
| not truncated, over format threshold | Open Raw / Format | raw first, async format on demand |
| truncated by backend | Open Prefix | shows retained prefix with banner and metadata |
| full-cell artifact available | Open Full Value | uses artifact channel, with progress and cancellation |
| binary | Open Binary Preview / Save Prefix | no accidental megabyte DOM insert |

Do not imply “Open” means full value when STS2 only retained a prefix.

### 8.4 Full-cell artifact channel, future

Only design this if required. Normal result pages are not a full-value transport.

Possible contract:

```ts
interface FullCellArtifactRequest {
    runId: string;
    resultSetId: string;
    rowOrdinal: number;
    columnOrdinal: number;
    expectedDigest?: string;
}
```

This requires backend support for durable result artifacts or server cursors. Until that exists, Query Studio offers prefix-open honestly.

### 8.5 Plans

Plan XML can be huge and parsing can be CPU-heavy.

Tasks:

- cache parsed plan graphs by `{runId, resultSetId, planCellDigest}`;
- parse plans asynchronously with progress/error state;
- lazy-render plan tabs only when activated;
- do not reparse when user switches tabs;
- instrument `plan.fetchXml`, `plan.parse`, `plan.firstPaint`, and `plan.openExternal`.

---

## 9. Data types and display correctness

### 9.1 Type preservation rules

Keep type information through the pipeline as long as practical:

| SQL type family | Wire/store representation | Display/export rule |
|---|---|---|
| `bigint`, `decimal`, `numeric`, `money` | string or typed wrapper, exact flag | display exact string, never lossy JS rounding for export |
| `float`, `real` | number or non-finite wrapper | display invariant, export with clear value |
| `datetime*`, `date`, `time`, `datetimeoffset` | ISO/invariant string wrapper | display with existing format policy, export invariant |
| `uniqueidentifier` | string wrapper | display raw GUID |
| `bit` | boolean | display `True`/`False` or configured casing |
| `xml` | string prefix/full value, type hint | XML link, optional formatter |
| JSON-ish text | string with JSON hint/sniff | JSON link only under threshold or shape hint |
| binary | base64/hex prefix + byte length | display hex prefix, open/save behavior explicit |
| geography/geometry/hierarchyid/UDT/provider-specific | provider wrapper string with type name | display safely, export string or unsupported marker |
| null | null bitmap | display `NULL` style, no per-cell value object needed |

### 9.2 Decode once per purpose

`decodeCell` should be called for a purpose:

- grid display;
- copy display;
- CSV export;
- JSON export;
- INSERT export;
- text view;
- cell document.

Do not decode into a generic rich object and then re-stringify for every feature. Use purpose-specific formatters over compact values and metadata. This avoids a small taxonomy zoo of objects grazing across the heap.

---

## 10. Observability plan

### 10.1 Row-pipeline vocabulary

Add registered events before emitting. Suggested families:

```text
mssql.queryStudio.rows.append.begin/end
mssql.queryStudio.rows.spill.write.begin/end
mssql.queryStudio.rows.spill.read.begin/end
mssql.queryStudio.rows.materialize.begin/end
mssql.queryStudio.rows.window.request
mssql.queryStudio.rows.window.served
mssql.queryStudio.grid.window.request
mssql.queryStudio.grid.window.received
mssql.queryStudio.grid.window.painted
mssql.queryStudio.grid.firstVisibleRowsPainted
mssql.queryStudio.messages.window.request
mssql.queryStudio.messages.window.painted
mssql.queryStudio.export.begin/progress/end
mssql.queryStudio.textView.generate.begin/progress/end
mssql.queryStudio.cellDocument.open.begin/end
mssql.queryStudio.plan.parse.begin/end
```

STS2 events:

```text
sts2.query.reader.open
sts2.query.reader.schema
sts2.query.page.build
sts2.query.page.encode
sts2.query.page.creditWait
sts2.query.page.post
sts2.query.cancel.request
sts2.query.cancel.ack
```

Fields:

- query id or digest;
- connection id digest;
- result-set ordinal;
- page sequence;
- row offset;
- row count;
- column count;
- encoded bytes;
- approximate bytes;
- truncation counts;
- source encoding;
- cache hit/miss;
- from spill;
- durations;
- status/reason.

No SQL text, cell values, object names, or raw connection details.

### 10.2 Diagnostic levels

| Level | Behavior |
|---|---|
| `minimal` | existing user-perceived lifecycle markers |
| `diagnostic` | aggregate rows/pages/windows, durations, bytes, cache hit rates |
| `verbose` | per-page/per-window events, spill frames, truncation counts |
| `full` | bounded deep capture for perftest and active investigations, still no raw row values |

### 10.3 Central observability tie-in

The central observability store should ingest aggregate row-pipeline facts, not row contents. Query/result performance can be analyzed by:

- result shape: rows, columns, page bytes, truncation counts;
- stage durations: SQL reader, encode, wire, sink, store, spill, host window, webview paint;
- outcome: success, cancel, row cap, spill limit, memory limit, protocol violation;
- environment: product SHA, STS2 SHA, backend kind, platform, renderer process.

This lets you answer “where did the run go slow?” without smuggling the user’s data into the observability attic.

---

## 11. Perf-test matrix

### 11.1 Scenario additions

Add or strengthen scenarios in `perftest`:

| Scenario | Shape | Required proof |
|---|---|---|
| `querystudio-query-100k-narrow` | 100k rows x 5 columns | first paint, scroll middle/end, memory, spill stats |
| `querystudio-query-1m-narrow` | 1M rows x 5 columns | row cap behavior, bounded memory, cancel if capped |
| `querystudio-query-wide-1000x300` | 1000 rows x 300 columns | horizontal/vertical scroll, column projection, no all-column churn |
| `querystudio-query-large-json` | 100 rows x 64 KiB and 20 rows x 1 MiB JSON | truncation honesty, no formatter freeze |
| `querystudio-query-large-xml` | same for XML | XML link/open-prefix behavior |
| `querystudio-query-large-binary` | 20 rows x 1 MiB varbinary(max) | no full DOM payload, bounded STS memory after streaming slice |
| `querystudio-query-10k-messages` | 10k PRINT/RAISERROR info messages | virtualized messages, typing unaffected |
| `querystudio-query-100-resultsets` | 100 small result sets | lazy tab/grid mounting, state stability |
| `querystudio-query-cancel-before-first-row` | WAITFOR before SELECT | cancel terminal timing |
| `querystudio-query-cancel-midstream` | slow row stream | cancel and credit cleanup |
| `querystudio-export-100k-csv` | 100k rows | streaming export progress/cancel |
| `querystudio-text-100k` | 100k rows | prompt/stream/virtual behavior |

### 11.2 Success metrics

For each scenario capture:

- submit to first metadata;
- submit to first row page;
- first row page to first visible rows painted;
- query complete;
- results rendered;
- extension host peak working set;
- STS peak working set;
- renderer long tasks;
- row-window cache hit rate;
- spill write/read bytes and duration;
- rows/sec from SQL reader;
- encode ms/page;
- sink wait ms/page;
- cancel ack and terminal time;
- row cap terminal time.

### 11.3 Gating policy

Keep new Query Studio result metrics diagnostic until:

1. instrumentation is stable;
2. scenarios have enough repeated runs on stable environment hashes;
3. central observability can compare distributions;
4. classic vs Query Studio head-to-head is understood.

Then promote a small set of official metrics. Do not make every shiny number official. A dashboard stuffed with unofficial truth-confetti is how regressions learn camouflage.

---

## 12. Implementation phases

### R0 — Baseline and row-pipeline attribution

**Goal:** every slow path has a stage name before major rewrites.

Files:

```text
vscode-mssql/extensions/mssql/src/queryStudio/**
vscode-mssql/extensions/mssql/src/services/sts2/sts2Backend.ts
vscode-mssql/extensions/mssql/src/sharedInterfaces/queryStudio*.ts
sqltoolsservice/src/sts2/**
perftest/packages/perftest-cli/src/scenarios/**
```

Tasks:

1. Register the row-pipeline event vocabulary.
2. Add STS2 timings for reader open, schema, page build, encode, credit wait, post, cancel.
3. Add extension timings for wire receive, validation, compact conversion, sink wait, ack.
4. Add RowStore timings for append, eviction, spill write/read, materialize, window serve.
5. Add webview timings for row-window request/receive/paint and first visible rows.
6. Add message prepare/render counters.
7. Add perf scenarios for 10k messages and 100k narrow rows.
8. Add privacy canary tests for diagnostics fields.

Acceptance:

- A single perf run can attribute wall time across SQL reader, STS encode, extension sink, RowStore, RPC, and paint.
- No new marker carries SQL text or cell values.
- Existing Query Studio tests stay green.

### R1 — Quick wins in extension and webview

**Goal:** remove obvious UI freezes without changing STS2 protocol.

Tasks:

1. Gate `RowStore.getRows` expensive null/non-empty counts behind verbose diagnostics.
2. Coalesce `QsRowsAppendedNotification` and message notifications.
3. Virtualize `MessagesView` and add `QsGetMessagesWindow`.
4. Move `Copy All Messages` to host-side generation.
5. Add adaptive grid row window sizing behind an internal setting.
6. Add renderer window cache hit/miss telemetry.

Acceptance:

- 10k messages visible does not degrade editor typing in the perf scenario.
- `getRows` normal mode does not scan cell values only for diagnostics.
- Fast scroll produces fewer stale/intermediate window requests.

### R2 — Honor execution limits end to end

**Goal:** options and capabilities become truthful.

Tasks:

1. Plumb `pageRows`, `pageBytes`, `timeoutMs`, and `maxCellBytes` through `Sts2Backend` to STS2.
2. Add STS2 reducer/effect state for page byte and timeout options.
3. Enforce `PageBytes` in the SQL Client page builder.
4. Add `pageRowsHonored`, `pageBytesHonored`, `queryTimeoutHonored` capability flags.
5. Add tests for row-count/byte split, timeout propagation, and capability negotiation.
6. Expose internal Query Studio settings or perftest knobs for page sizes.

Acceptance:

- A wide-row query splits pages by bytes before row count.
- Capability flags are false unless a build actually honors them.
- No page exceeds negotiated frame bounds except documented one-row oversize behavior.

### R3 — Large-cell streaming and truncation honesty

**Goal:** large values are bounded at the driver edge.

Tasks:

1. Use `CommandBehavior.SequentialAccess` in `SqlClientSession` after compatibility tests.
2. Add type-specific large string/XML/binary readers.
3. Stream prefix and optional digest without full allocation.
4. Extend truncation metadata for digest policy and original byte availability.
5. Add real-server or controlled-reader tests for large values.
6. Add BLOB/XML/JSON perf scenarios with STS memory measurements.

Acceptance:

- Large `nvarchar(max)`, `xml`, and `varbinary(max)` values do not allocate full cell values on the normal grid path.
- Truncated cells display as prefix/truncated with honest metadata.
- Open-cell behavior says “prefix” unless a full artifact is truly available.

### R4 — ResultStoreV2 async spill and cache

**Goal:** large result random access stays responsive under bounded memory.

Tasks:

1. Introduce `ResultStoreV2` behind `RowStore` compatibility.
2. Add `ResultPageStore` abstraction with `NodeFilePageStore` and `MemoryPageStore`.
3. Replace synchronous spill writes/reads with async queue and bounded backpressure.
4. Add frame format v2 and page index metadata.
5. Add protected/probationary page cache and window cache.
6. Add per-result-set memory partitioning or eviction weights.
7. Add corruption handling and cleanup tests.

Acceptance:

- Spill write/read does not block the extension host hot path.
- High-offset scrolling over spilled pages remains bounded and observable.
- A background export does not evict the active viewport aggressively.

### R5 — Compact row wire

**Goal:** remove duplicated row compaction and approximate-byte serialization.

Tasks:

1. Add STS2 compact row notification shape and negotiation.
2. Compute null bitmap, type hints, stats, and approx/encoded bytes once in STS2.
3. Keep legacy rows adapter in `Sts2Backend`.
4. Store encoded compact frames directly where possible.
5. Update fake backend/conformance tests.
6. Measure JSON compact vs old rows before considering binary.

Acceptance:

- Extension no longer calls `JSON.stringify(params.rows).length` on compact-capable STS2.
- Compact rows preserve nulls, type hints, truncated cells, and exact numerics.
- Protocol fallback remains tested.

### R6 — Grid column projection and wide-data UX

**Goal:** wide results only transfer and render visible cells.

Tasks:

1. Add `QsGetRowsV2` with row and column projection.
2. Teach FluentResultGrid windowed source to request visible columns plus buffer.
3. Add projected null/truncated/linkable bitsets.
4. Bound autosize sampling.
5. Add wide 1000x300 perf scenario and horizontal scroll checks.

Acceptance:

- Wide-grid vertical scroll does not return all 300 columns unless needed.
- Horizontal scroll does not force full result re-fetch.
- Autosize cost is bounded and measured.

### R7 — Heavy secondary features

**Goal:** export, text, cell documents, and plans become large-result-safe.

Tasks:

1. Streaming CSV/JSON/INSERT export with progress/cancel.
2. Text view threshold/prompt and temp-document streaming path.
3. Open-cell prefix/full behavior and async formatting.
4. Plan graph parse cache by digest and async parse/progress.
5. Unit tests for large output cancellation and no full-string allocation above threshold.

Acceptance:

- Export 100k rows does not build one giant string in memory.
- Text view does not freeze on 100k rows.
- Large JSON/XML formatting never runs synchronously on the UI path.
- Plan parse is cached and observable.

### R8 — Hardening, defaults, and review

**Goal:** decide which optimizations become defaults.

Tasks:

1. Run full perf matrix with central observability ingestion.
2. Compare classic query editor and Query Studio for shared scenarios.
3. Tune defaults: page bytes, page rows, grid windows, memory/spill caps.
4. Finalize settings that should be public vs internal.
5. Add support bundle summaries for result-store health.
6. Document known limits and user-visible messages.

Acceptance:

- No silent data loss.
- No known path can store unbounded result cells in renderer memory.
- Query Studio can run massive result scenarios with bounded memory and clear user feedback.

---

## 13. File-level coding-agent checklist

### vscode-mssql

```text
src/queryStudio/executionHost.ts
src/queryStudio/executionOrchestrator.ts
src/queryStudio/queryStudioController.ts
src/queryStudio/rowStore.ts                         // compatibility wrapper first
src/queryStudio/results/resultStore*.ts              // new
src/queryStudio/results/pageStores/*.ts              // new
src/queryStudio/resultExport.ts
src/queryStudio/cellDocument.ts
src/webviews/pages/QueryStudio/results.tsx
src/webviews/pages/QueryStudio/resultsGrid.tsx
src/webviews/pages/QueryStudio/resultsTextView.tsx
src/webviews/common/FluentResultGrid/**
src/services/sts2/sts2Backend.ts
src/services/sts2/wire/v2.ts
src/services/sqlDataPlane/api.ts
src/sharedInterfaces/queryStudio.ts
src/sharedInterfaces/queryStudioGridOps.ts
src/perf/perfTelemetry.ts
src/diagnostics/**
test/unit/queryStudio*.test.ts
test/unit/queryStudio/rowStore.test.ts
test/unit/sts2Backend.test.ts
test/unit/fluentResultGrid.test.ts
```

### sqltoolsservice

```text
src/sts2/Microsoft.SqlTools.Sts2.Contracts/**
src/sts2/Microsoft.SqlTools.Sts2.Core/Sts2CoreReducer.cs
src/sts2/Microsoft.SqlTools.Sts2.Core/CoreState.cs
src/sts2/Microsoft.SqlTools.Sts2.Runtime/Effects/DriverEffectRunner.cs
src/sts2/Microsoft.SqlTools.Sts2.Runtime/Effects/WireValueEncoder.cs
src/sts2/Microsoft.SqlTools.Sts2.Drivers.SqlClient/SqlClientSession.cs
src/sts2/Microsoft.SqlTools.Sts2.Drivers.SqlClient/SqlRowsPageBuilder.cs  // new
test/sts2/Microsoft.SqlTools.Sts2.UnitTests/**
test/sts2/scenarios/**
docs/sts2/CONTRACT.md
```

### perftest

```text
packages/perftest-cli/src/scenarios/registry.ts
packages/perftest-cli/test/queryStudioScenario.test.ts
packages/perf-contracts/src/observabilityContract*.ts
packages/perf-contracts/schemas/**
docs/PRODUCT_INSTRUMENTATION.md
docs/DIAGNOSTIC_COLLECTORS.md
```

---

## 14. User-facing behavior rules

1. If the row cap cancels the query, show: **“Stopped after N rows because Query Studio reached the configured row limit. The server query was canceled to protect the editor.”**
2. If spill cap is reached, show: **“Stopped because local result storage reached its configured limit.”** Include a link to settings/status, not a crash stack.
3. If a cell is truncated, display a visible badge and make the cell document say **prefix** unless full retrieval is supported.
4. If export/text generation is large, show progress and cancellation.
5. If a backend cannot honor page bytes or max cell bytes, show this in the diagnostics/status command and keep conservative local caps.

---

## 15. Open decisions

| Decision | Recommendation | When to decide |
|---|---|---|
| Full-cell retrieval | Defer. Ship honest prefix-open first. | After large-cell streaming and user feedback |
| Compact binary wire | Defer. Measure compact JSON first. | After R5 perf data |
| Public memory/spill settings | Keep internal until defaults stabilize. | R8 |
| Row cap behavior | Keep cancel-on-cap. | Confirm in R2/R8 |
| Worker thread for ResultStore | Use async fs first; worker if JSON parse/format remains hot. | R4/R5 data |
| Column projection default | Enable for wide results first, then all grids. | R6 |
| Official perf metrics | Keep diagnostic until stable central history. | R8 |

---

## 16. First coding-agent slice

Start with this small, high-leverage slice:

1. Add row-pipeline markers and conformance registration.
2. Add `diagnostics` option to `RowStore.getRows` and skip verbose cell counts by default.
3. Replace `MessagesView` with a virtual list and add `QsGetMessagesWindow`.
4. Batch `QsRowsAppendedNotification` and `QsMessagesAppendedNotification`.
5. Add 10k-message and 100k-narrow Query Studio perf scenarios.
6. Add tests proving:
   - normal `getRows` does not count every cell for diagnostics;
   - 10k messages render a bounded number of DOM rows;
   - copy-all messages is host-generated;
   - rows-appended batching preserves final counts;
   - no marker emits SQL text or cell values.

This slice gives immediate UX relief and better x-ray vision without entangling STS2 protocol changes. Then move to R2/R3, where the real memory-safety work begins.
