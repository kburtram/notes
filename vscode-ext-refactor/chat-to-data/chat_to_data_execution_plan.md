# Chat to Data Execution Plan
## Query Studio result snapshot leases, pinned result custom documents, and bounded AI/data access

**Status:** reviewed design and coding-agent execution plan, 2026-07-09.  
**Primary repo:** `microsoft/vscode-mssql`, branch `dev/query`.  
**Related repo:** `microsoft/sqltoolsservice`, branch `dev/query`, only for future STS2 result-artifact evolution.  
**Primary modules:** `src/queryStudio/**`, `src/queryResults/**` or `src/queryStudio/results/**`, `src/sharedInterfaces/**`, `src/webviews/pages/QueryStudio/**`, `src/controllers/mainController.ts`, `extension.ts`, `package.json`.  
**Design basis:** current Query Studio results execution path, the query optimization plan, the metadata/result privacy model, the central observability classification discipline, and the draft `chat_to_data.md` proposal.

---

## 0. Executive summary

The draft is directionally right: Query Studio already streams query rows into an extension-host `RowStore`, renders bounded windows through `qs/getRows`, and keeps row values out of coarse state. The missing platform piece is not an AI handler. It is a stable, product-wide **query result access layer** that can detach result data from the live editor run, keep it alive safely, and expose it to pinned documents, commands, exports, chat tools, and future consumers through one bounded contract.

This replacement plan makes that platform explicit:

1. Add a product-wide `QueryResultAccessService` that owns live result-source registration, immutable result snapshots, leases, retention, row-window reads, sampling, export, and diagnostics.
2. Wrap the current `RowStore` in a retainable `ResultStoreLease` model so rerunning a query or closing a Query Studio document releases the live owner without deleting snapshots still in use.
3. Add a readonly **pinned results custom document** backed by an in-memory snapshot URI, not a scratch file. It reuses the Query Studio result pane and grid, but its data source is a snapshot rather than the live `ExecutionHost`.
4. Extract the result pane into a shared component that can render `live`, `snapshot`, and future `remote artifact` result sources without forking the grid.
5. Implement result context tracking through the currently no-op `QsUpdateGridSelectionRequest`, plus a host-side `QueryResultContextService` that knows the active result set, selected cell/range, active pinned document, and live source.
6. Add a bounded `mssql_query_results` language model tool after the snapshot/pin substrate is proven. The tool returns schema and summaries freely, but raw rows, message text, SQL text, and cell values require explicit user confirmation.
7. Add a separate `@query` participant later as a thin orchestrator over the same service. Do not merge this into `mssql.agent` and do not tie it to AI completions.
8. Keep STS2 result-handle support as a future tier. The first useful feature should be extension-host snapshots over the existing Query Studio row store.

The architectural center of gravity is a little storage goblin with a ledger: every consumer gets a lease, every row fetch is bounded, and no result values sneak into state, telemetry, or a model response without a visible gate.

---

## 1. Technical review of the draft

### 1.1 What the draft gets right

Keep these choices:

- The feature should be built as a Query Studio result snapshot platform first and an AI feature second.
- Snapshots should be immutable, lease-owned views over completed result sets.
- Snapshot creation should avoid copying all rows.
- Rerunning a query should create a new live store while leased prior stores remain available.
- Pinned results should reuse the current result grid experience.
- AI access should be bounded, explicit, auditable, and separate from `mssql.agent`.
- `QsUpdateGridSelectionRequest` is the right seam for active result context, but it needs a real payload and implementation.
- STS2 should not be changed before the first useful feature. Query Studio already has a local random-access row store.

### 1.2 Improvements made in this replacement

#### 1.2.1 Elevate the service from `QueryResultSnapshotService` to `QueryResultAccessService`

The draft's snapshot service is the correct core, but the user's goal is broader: result data should become separate from the query and available across the product. Use a product-wide service name and contract:

```text
QueryResultAccessService
  live result-source registry
  snapshot and lease registry
  row-window access
  sampling and profiling
  export/open-cell helpers
  pinned custom-document opener
  chat/tool access checks
  diagnostics and retention
```

The service can live under `src/queryResults/**`. Query Studio integration code stays under `src/queryStudio/**`. This avoids an AI-shaped architecture and avoids making future consumers import Query Studio controller internals.

#### 1.2.2 Build the pinned result as a custom readonly document, not only a WebviewPanel

The draft allowed a `WebviewPanel` as the first implementation. The requested feature is a popout results pane custom document, so the target should be:

```ts
vscode.window.registerCustomEditorProvider(
  "mssql.queryResultsSnapshot",
  new PinnedQueryResultsDocumentProvider(...),
  {
    webviewOptions: { retainContextWhenHidden: true },
    supportsMultipleEditorsPerDocument: true,
  },
);
```

Open it with a readonly virtual URI such as:

```text
mssql-query-results-snapshot:/Pinned%20Results%20-%2012-45-03.mssqlresults?sid=<snapshotId>
```

A spike should validate that VS Code opens this scheme cleanly through `vscode.openWith`. If VS Code insists on URI backing, add a tiny readonly `FileSystemProvider` for the scheme that exposes metadata only and throws on writes. Do not create a scratch file.

#### 1.2.3 Freeze result-set metadata and row counts at snapshot creation

Even if the underlying `RowStore` remains live for a later result set in the same run, the snapshot should freeze:

- included result-set ids;
- row counts at snapshot time;
- column metadata;
- completion/truncation/corruption flags;
- plan flags;
- message summary;
- source title/database/server digests.

`getRows` for a snapshot must clamp to the frozen row count. This prevents ghost rows if a future streaming snapshot mode lands.

#### 1.2.4 Treat raw message text and SQL text as data too

The draft correctly protects row values. It should also protect:

- server messages, because they can contain object names, parameter values, or SQL fragments;
- query text, because it can contain literals, temp data, comments, and secrets;
- XML/JSON cell text, because it is often application data;
- plan XML, because it can include query text and object names.

Pinned documents can show these locally. AI/tool outputs must classify and confirm before transmitting them to a language model.

#### 1.2.5 Add a result-context service

The snapshot service should not guess what the user means by "these results." Add a separate context owner:

```text
QueryResultContextService
  active Query Studio model
  active result set
  active selected cell/range
  active pinned snapshot document
  last focused result source
  command/chat resolution policy
```

This service is what commands, `@query`, and tools should consult before asking the user to pick.

#### 1.2.6 Keep the row-store abstraction ready for ResultStoreV2 and non-STS backends

The query optimization plan proposes a future `ResultStoreV2` with better page indexes, async spill, compact frame storage, and lower UI memory. This feature should not bake `RowStore` into chat or pinned documents. Define an `IQueryResultStore` facade now, backed by current `RowStore` first and swappable for:

- `RowStoreV1Retained`, current extension-host store;
- `ResultStoreV2`, optimized local store;
- `Sts2ResultArtifactStore`, future server-side retained handle;
- `RemoteResultStore`, future web-hosted backend.

This is the hinge that keeps the design portable.

---

## 2. Current implementation truth to preserve

### 2.1 Query Studio result ownership today

Current `ExecutionHost` owns one `RowStore` per live run. Starting a new run disposes the previous store immediately, then creates a new `RowStore` under a per-run spill directory. That is correct for a single live editor result pane, but it is the exact lifecycle that prevents pinned documents and chat access from surviving reruns.

Current state shape:

```text
QueryStudioDocumentModel
  ExecutionHost
    rowStore?: RowStore
    summaries: Map<resultSetId, QsResultSetSummary>
    summaryOrder: string[]
    messages: QsMessageRow[]
    executionState: QsExecutionState
```

The current `resultsState()` pushes only result summaries, totals, streaming state, message count, error count, and plan count. That rule must remain: row values never ride coarse state.

### 2.2 RowStore today

`RowStore` is already close to a snapshot backing store:

- rows are stored as compact pages;
- pages are append-only during query execution;
- completed result sets are read-only;
- memory is bounded by an LRU;
- evicted pages spill to a length-prefixed JSON frame file;
- `getRows(resultSetId, start, count)` returns the same `QsCellWindow` the grid already consumes;
- `dispose()` clears maps, closes the spill fd, removes the spill file, and removes the spill directory.

The important change is ownership, not a row-store rewrite. The first slice should wrap `RowStore`. The query optimization plan can later replace the store implementation underneath the same facade.

### 2.3 Query Studio RPC today

Current controller handlers already provide the required operations for a pinned document data source:

- `QsGetRowsRequest` calls `executionHost.getRows`.
- `QsSaveResultRequest` calls `saveQueryStudioResult` with a `getRows` callback.
- `QsOpenCellDocumentRequest` fetches one row window, pretty-prints JSON/XML where appropriate, and opens a side document.
- `QsOpenPlanRequest` opens plan XML in the existing execution-plan viewer.
- `QsUpdateGridSelectionRequest` exists, but the controller currently returns `undefined` and stores nothing.

This should become a neutral result-pane contract: live Query Studio and pinned results should both answer the same basic row, export, cell, and plan requests, even if the request names remain `Qs*` during the first refactor.

### 2.4 Result grid today

`QsResultGridSurface` already uses a `windowed` data source over `QsGetRowsRequest`. Copy commands fetch in chunks, XML/JSON links use source row ids, and sort/filter only engage for complete result sets at or below `mssql.resultsGrid.inMemoryDataProcessingThreshold`.

That is exactly the model pinned documents need. Extract, do not fork.

### 2.5 AI surfaces today

The extension already registers language model tools in `MainController.registerLanguageModelTools()`. The extension also contributes and registers one chat participant, `mssql.agent`, from `extension.ts` and `package.json`.

The new result-data tool should be registered alongside existing language model tools, but it should not be implemented inside the existing SQL agent handler. Add a separate tool first, then a separate `mssql.query` chat participant later.

---

## 3. Goals and non-goals

### 3.1 Goals

| ID | Goal |
|---|---|
| C2D-G1 | Let users pin one result set, selected complete result sets, or all complete result sets into a readonly popout results document. |
| C2D-G2 | Let pinned results survive query rerun and source Query Studio document close until the pinned document closes or its lease expires. |
| C2D-G3 | Keep snapshot creation O(result set count), not O(row count). |
| C2D-G4 | Expose one product-wide result access service for pinned documents, commands, chat tools, reports, and future features. |
| C2D-G5 | Preserve the current bounded row-window rendering model. |
| C2D-G6 | Make AI access explicit, owner-scoped, bounded, and confirmation-backed for raw values. |
| C2D-G7 | Track active result context so commands and chat can resolve "this result" without guessing. |
| C2D-G8 | Make row data available for local operations such as export, copy, profile, and reports without pushing full data into the renderer or model. |
| C2D-G9 | Keep the storage abstraction compatible with future `ResultStoreV2`, STS2 retained result handles, and remote/webhost result stores. |
| C2D-G10 | Add deep tests and diagnostics for lifetime, cleanup, row-window equivalence, privacy, and performance. |

### 3.2 Non-goals for the first release slice

- Do not persist snapshots across VS Code restarts.
- Do not invent a saved `.mssqlresults` file format yet.
- Do not send full result sets to a language model.
- Do not rewrite STS2 query execution.
- Do not require ResultStoreV2 before pinned results work.
- Do not merge this with AI completions.
- Do not make snapshots mutable.
- Do not make the `mssql.agent` participant own Query Studio result data.
- Do not expose raw row values, query text, message text, plan XML, or cell contents in diagnostics.

---

## 4. Target architecture

```text
Query Studio live editor
  ExecutionHost
    RetainedQueryResultStore over RowStore
    summaries/messages/current run
      |
      | registers as live source
      v
QueryResultAccessService
  live source registry
  snapshot registry
  lease registry
  retention manager
  row window / cell / export / sample / profile operations
  diagnostics and privacy gates
      |
      +------------------------+-------------------------+-------------------+
      |                        |                         |                   |
      v                        v                         v                   v
Pinned Results custom doc   Query Result commands     LM tool            @query participant
readonly custom editor      pin/popout/export         bounded access      thin orchestrator
      |                        |                         |                   |
      v                        v                         v                   v
Shared Query Results Pane / FluentResultGrid windowed data source
      |
      v
getRows(start,count) only; no full result set in renderer
```

Storage tiers, from first slice to future:

```text
Tier 0, now:
  RetainedQueryResultStore wraps current RowStore.

Tier 1, optimization:
  ResultStoreV2 implements the same IQueryResultStore interface.

Tier 2, STS2/server:
  STS2 may return stable retained result handles and server-side sampling.

Tier 3, web/remote:
  A remote ResultStore service implements the same window/sample/profile contract.
```

---

## 5. Module layout

Recommended new product-wide result modules:

```text
src/queryResults/
  queryResultAccessService.ts
  queryResultTypes.ts
  queryResultSourceRegistry.ts
  queryResultContextService.ts
  queryResultRetention.ts
  resultStoreLease.ts
  resultStoreFacade.ts
  resultSnapshotStore.ts
  resultSampler.ts
  resultProfiler.ts
  resultPrivacy.ts
  resultDiagnostics.ts
  pinnedResultsDocumentProvider.ts
  pinnedResultsController.ts
  queryResultsTool.ts
  queryParticipant.ts
```

Query Studio integration modules:

```text
src/queryStudio/executionHost.ts              // create retained stores; expose live source
src/queryStudio/queryStudioController.ts      // pin/popout/context RPC handlers
src/queryStudio/queryStudioDocumentModel.ts   // register/unregister live source
src/queryStudio/queryStudioProvider.ts        // pass services into models/controllers
```

Shared webview modules:

```text
src/webviews/pages/QueryStudio/results.tsx       // extract reusable pane pieces
src/webviews/pages/QueryStudio/resultsGrid.tsx   // make data source injectable
src/webviews/pages/QueryResultsSnapshot/app.tsx  // thin host for pinned custom doc, or reuse QS app shell subset
src/sharedInterfaces/queryResults.ts             // neutral snapshot/pinned RPCs, or shared aliases over Qs* in first slice
```

Package contributions:

```text
package.json
  commands:
    mssql.queryStudio.pinResultSet
    mssql.queryStudio.pinAllResults
    mssql.queryStudio.popOutResults
    mssql.queryResults.askAboutSelection
    mssql.queryResults.releaseExpiredSnapshots
    mssql.queryResults.showStatus
  customEditors:
    mssql.queryResultsSnapshot
  chatParticipants:
    mssql.query, later phase
  language model tool contribution:
    mssql_query_results, if tool manifest contribution is required by current VS Code version
```

Dependency rules:

| Layer | May import | Must not import |
|---|---|---|
| `queryResults/**` core | shared interfaces, `vscode` only at provider/tool edges | Query Studio React internals, STS2 wire DTOs, row values in diagnostics |
| `queryStudio/**` | `QueryResultAccessService` and source interfaces | chat participant implementation |
| webview shared results | result state and RPC abstractions | `vscode`, extension-host services |
| tool/chat | `QueryResultAccessService`, `QueryResultContextService`, privacy gate | `ExecutionHost`, `RowStore` directly |
| result store facade | `RowStore` for V1 adapter | chat/tool/UI code |

---

## 6. Core concepts

### 6.1 Live result source

A live result source is the current result-producing owner, normally a Query Studio document model.

```ts
export interface LiveQueryResultSource {
    readonly sourceId: string;
    readonly sourceUri: vscode.Uri;
    readonly sourceTitle: string;
    readonly sourceKind: "queryStudio";

    state(): QueryResultSourceState;
    describeLive(): LiveQueryResultDescription;
    createSnapshot(request: CreateQueryResultSnapshotRequest): Promise<QueryResultSnapshotLease>;
    getRows(resultSetId: string, start: number, count: number): QsCellWindow;

    onDidChange(listener: () => void): vscode.Disposable;
    onDidDispose(listener: () => void): vscode.Disposable;
}
```

`ExecutionHost` should implement this through a small adapter, not by exposing itself to tools.

### 6.2 Result store

The result store is the physical row backing for one run. In phase 1 it wraps `RowStore`.

```ts
export interface IQueryResultStore {
    readonly storeId: string;
    readonly runId: string;
    readonly createdEpochMs: number;

    retain(owner: QueryResultLeaseOwner): QueryResultStoreLease;
    getRows(resultSetId: string, start: number, count: number): QsCellWindow;
    getCell(resultSetId: string, row: number, column: number): unknown | undefined;
    summary(resultSetId: string): QueryResultSetFrozenSummary | undefined;
    stats(): QueryResultStoreStats;
}

export interface QueryResultStoreLease extends vscode.Disposable {
    readonly leaseId: string;
    readonly owner: QueryResultLeaseOwner;
    readonly store: IQueryResultStore;
}
```

The wrapper owns the real `RowStore.dispose()`. Consumers dispose leases, never the raw store.

### 6.3 Snapshot

A snapshot is a logical immutable view over one or more frozen result sets.

```ts
export interface QueryResultSnapshot {
    readonly snapshotId: string;
    readonly createdEpochMs: number;
    readonly source: QueryResultSourceIdentity;
    readonly runId: string;
    readonly storeLease: QueryResultStoreLease;
    readonly resultSets: readonly QueryResultSetFrozenSummary[];
    readonly messages: QueryResultMessageCapture;
    readonly query: QueryResultQueryCapture;
    readonly database?: QueryResultDatabaseIdentity;
    readonly limits: QueryResultSnapshotLimits;
    readonly purpose: QueryResultSnapshotPurpose;
    readonly disposed: boolean;
}
```

A snapshot is immutable. A later feature that filters, sorts, annotates, or derives rows should create a **derived snapshot** with a parent snapshot id and a small delta.

### 6.4 Lease owner

```ts
export type QueryResultLeaseOwnerKind =
    | "liveRun"
    | "pinnedDocument"
    | "aiTool"
    | "chatParticipant"
    | "export"
    | "command"
    | "debug";

export interface QueryResultLeaseOwner {
    readonly kind: QueryResultLeaseOwnerKind;
    readonly label?: string;
    readonly conversationId?: string;
    readonly documentUri?: string;
    readonly createdByCommand?: string;
}
```

Lease owners are not a security boundary by themselves, but they prevent accidental cross-feature access and make retention explainable.

### 6.5 Snapshot handle

A handle is what UI, commands, and chat tools exchange.

```ts
export interface QueryResultSnapshotHandle {
    readonly snapshotId: string;
    readonly leaseId: string;
    readonly ownerKind: QueryResultLeaseOwnerKind;
    readonly resultSetIds?: readonly string[];
    readonly expiresEpochMs?: number;
}
```

Snapshot ids and lease ids should use crypto-grade randomness. Do not derive them from document URI, query text, database, or timestamps.

---

## 7. QueryResultAccessService

### 7.1 Public surface

```ts
export interface QueryResultAccessService extends vscode.Disposable {
    registerLiveSource(source: LiveQueryResultSource): vscode.Disposable;

    listLiveSources(filter?: QueryResultSourceFilter): readonly LiveQueryResultSummary[];
    listSnapshots(filter?: QueryResultSnapshotFilter): readonly QueryResultSnapshotSummary[];

    createSnapshot(request: CreateQueryResultSnapshotRequest): Promise<QueryResultSnapshotLease>;
    acquireSnapshot(snapshotId: string, owner: QueryResultLeaseOwner): QueryResultSnapshotLease | undefined;
    releaseLease(leaseId: string, reason?: string): void;

    describeSnapshot(snapshotId: string, options?: DescribeSnapshotOptions): QueryResultSnapshotDescription | undefined;
    getRows(params: QueryResultGetRowsParams): QsCellWindow;
    getCell(params: QueryResultGetCellParams): QueryResultCellValue;
    sampleRows(params: QueryResultSampleRowsParams): Promise<QueryResultSample>;
    profileResultSet(params: QueryResultProfileParams): Promise<QueryResultProfile>;
    exportSnapshot(params: QueryResultExportParams): Promise<QueryResultExportResult>;

    openPinnedDocument(request: OpenPinnedResultsRequest): Promise<vscode.Uri>;

    status(): QueryResultAccessStatus;
    onDidChangeSnapshots(listener: () => void): vscode.Disposable;
}
```

### 7.2 Snapshot creation request

```ts
export interface CreateQueryResultSnapshotRequest {
    readonly owner: QueryResultLeaseOwner;
    readonly reason: string;

    readonly sourceUri?: vscode.Uri;
    readonly sourceId?: string;
    readonly activeContext?: boolean;

    readonly scope:
        | { kind: "resultSet"; resultSetId: string }
        | { kind: "resultSets"; resultSetIds: readonly string[] }
        | { kind: "allCompleteResultSets" }
        | { kind: "selection"; selection: QueryResultSelectionRef };

    readonly includeMessages?: "none" | "summary" | "allLocal";
    readonly includeQueryText?: "none" | "digest" | "localOnly";
    readonly waitForCompletion?: "never" | "resultSet" | "run";
    readonly maxRows?: number;
    readonly maxApproxBytes?: number;
}
```

Recommended initial policy:

| Request | Initial behavior |
|---|---|
| pin result set | require the result set to be `complete` |
| pin all results | require run not streaming; include all complete result sets |
| AI create snapshot | allow handle creation without raw rows; no values in response |
| snapshot selection | create a snapshot over the owning result set plus a selection ref, not a physical row copy |
| wait for completion | `never` in phase 1; `resultSet`/`run` added only after cancellation and timeout behavior is designed |

### 7.3 Snapshot description

```ts
export interface QueryResultSnapshotDescription {
    snapshotId: string;
    source: QueryResultSourceIdentity;
    runId: string;
    createdEpochMs: number;
    leaseCount: number;
    purpose: QueryResultSnapshotPurpose;
    resultSets: QueryResultSetFrozenSummary[];
    totalRows: number;
    totalColumns: number;
    totalApproxBytes?: number;
    complete: boolean;
    hasErrors: boolean;
    messages: QueryResultMessageSummary;
    query: QueryResultQuerySummary;
    database?: QueryResultDatabaseIdentity;
    store: QueryResultStoreStats;
    retention: QueryResultRetentionState;
    truncation: QueryResultTruncationSummary;
}
```

`describeSnapshot` should not return raw row values. It may return column names and SQL types because the current schema/AI work already treats schema context as permissible under Copilot settings. Message text and query text require explicit options and confirmation when used for AI.

---

## 8. Retainable store integration

### 8.1 Recommended wrapper

Do not overload `RowStore.dispose()` to mean both "release live owner" and "delete everything." Wrap it.

```ts
export class RetainedRowStore implements IQueryResultStore, vscode.Disposable {
    private readonly rowStore: RowStore;
    private readonly leases = new Map<string, QueryResultLeaseOwner>();
    private disposed = false;
    private liveLeaseId: string | undefined;

    constructor(rowStore: RowStore, metadata: RetainedRowStoreMetadata) {
        this.rowStore = rowStore;
        this.liveLeaseId = this.createLease({ kind: "liveRun", label: "Query Studio live run" });
    }

    retain(owner: QueryResultLeaseOwner): QueryResultStoreLease {
        const leaseId = this.createLease(owner);
        return {
            leaseId,
            owner,
            store: this,
            dispose: () => this.release(leaseId, "leaseDisposed"),
        };
    }

    releaseLiveOwner(reason: "rerun" | "documentClosed" | "disconnect" | "extensionDeactivate"): void {
        if (this.liveLeaseId) {
            this.release(this.liveLeaseId, reason);
            this.liveLeaseId = undefined;
        }
    }

    private release(leaseId: string, reason: string): void {
        this.leases.delete(leaseId);
        this.disposeIfUnreferenced(reason);
    }

    private disposeIfUnreferenced(reason: string): void {
        if (!this.disposed && this.leases.size === 0) {
            this.disposed = true;
            this.rowStore.dispose();
        }
    }
}
```

### 8.2 ExecutionHost changes

Current run start:

```ts
this.rowStore?.dispose();
this.rowStore = new RowStore(...);
```

Target run start:

```ts
this.currentStore?.releaseLiveOwner("rerun");
this.runCounter++;
const rowStore = new RowStore(path.join(this.spillRoot, `run${this.runCounter}`), limits);
this.currentStore = new RetainedRowStore(rowStore, { runId, sourceUri, createdEpochMs });
this.rowWriter = this.currentStore.asLiveWriter();
```

Recommended execution-host fields:

```ts
private currentStore: RetainedRowStore | undefined;
private currentLiveLease: QueryResultStoreLease | undefined;
private rowWriter: RowStore | undefined; // or IAppendableQueryResultStore in the cleaner refactor
private runId: string | undefined;
```

Generate a globally unique `runId`, not just the current `runCounter`:

```text
qsrun_<shortUriDigest>_<runCounter>_<random8>
```

Diagnostics can use the digest/random id. UI can show friendly run time.

### 8.3 Close and rerun semantics

| Event | Behavior |
|---|---|
| query rerun | release live lease on previous store; create new store |
| source Query Studio document close, idle run | release live lease; snapshots remain |
| source Query Studio document close, executing run | request cancel, release UI bindings, release live lease only after terminal or bounded cleanup |
| disconnect | release live lease, preserve snapshots |
| extension deactivation | dispose all snapshots, release all stores, sweep spill roots |
| retained store corrupt | snapshot reads return short/corrupt windows and surface status, never throw through UI |

### 8.4 Completed-only rule

Phase 1 should snapshot only complete result sets. `Pin all results` should require the run not to be streaming. `Pin result set` may allow a complete result set from an active multi-result query only if the included result set's summary is complete and its frozen row count is clamped.

Simpler preview rule, acceptable for first PR:

```text
pin buttons are enabled only after the run is no longer streaming.
```

Then add per-result-set completed pinning in a follow-up.

---

## 9. Query Studio integration

### 9.1 Register live sources

`QueryStudioDocumentModel` should register a live source with `QueryResultAccessService` when the model is created and dispose it when the model is disposed.

```ts
this.resultSourceRegistration = queryResultAccess.registerLiveSource(
    new QueryStudioLiveResultSource(this.backingDocument.uri, this.executionHost, ...),
);
```

The service should not scan `QueryStudioProvider.liveModels` directly. Registration is easier to test and avoids tool/chat code depending on provider internals.

### 9.2 Add Query Studio webview RPCs

Add requests:

```ts
export namespace QsPinResultSetRequest {
    export const type = new RequestType<
        { resultSetId: string },
        { opened: boolean; snapshotId?: string; error?: string },
        void
    >("qs/pinResultSet");
}

export namespace QsPinAllResultsRequest {
    export const type = new RequestType<
        { includeMessages?: boolean },
        { opened: boolean; snapshotId?: string; skipped?: number; error?: string },
        void
    >("qs/pinAllResults");
}

export namespace QsPopOutResultsRequest {
    export const type = new RequestType<
        { scope: "all" | "active" },
        { opened: boolean; snapshotId?: string; error?: string },
        void
    >("qs/popOutResults");
}
```

Implementation in `QueryStudioController`:

```ts
this.onRequest(QsPinResultSetRequest.type, async ({ resultSetId }) => {
    const lease = await this.queryResultAccess.createSnapshot({
        owner: { kind: "pinnedDocument", label: "Pinned result set" },
        sourceUri: this.model.backingDocument.uri,
        reason: "User pinned result set from Query Studio",
        scope: { kind: "resultSet", resultSetId },
        includeMessages: "summary",
        includeQueryText: "digest",
    });
    await this.queryResultAccess.openPinnedDocument({ snapshotId: lease.snapshotId });
    return { opened: true, snapshotId: lease.snapshotId };
});
```

### 9.3 Add UI actions

Add three visible entry points:

- pin button in `GridCaption` for each complete result set;
- `Pin All Results` or `Pop Out Results` in the result-pane header or overflow menu;
- command palette commands for active Query Studio results.

`GridCaption` should accept an `actions` or `children` slot so the button does not fork the caption. It already accepts `children`; use that seam.

Button policy:

| State | Pin button |
|---|---|
| no rows yet | hidden or disabled |
| streaming and set incomplete | disabled, tooltip "Available after this result set completes" |
| set complete | enabled |
| corrupt/truncated | enabled with tooltip note; snapshot carries truncation/corrupt state |
| plan result set | enabled, but label says "Pin plan result" only if UX has room |

### 9.4 Active result context

Replace the no-op `QsUpdateGridSelectionRequest` handler with a real handler.

Current payload is too small:

```ts
{ row?: number; column?: number; rangeRows?: number; rangeCols?: number }
```

Recommended replacement:

```ts
export interface QsGridSelectionUpdate {
    resultSetId: string;
    active?: { sourceRow: number; column: number };
    ranges?: readonly QsGridSelectionRange[];
    sourceRowIds?: readonly number[];       // capped, for sorted/filtered non-contiguous selections
    displayedRowCount?: number;
    selectedCellCount?: number;
    selectedRowCount?: number;
    reason: "focus" | "selection" | "keyboard" | "mouse" | "contextMenu";
}
```

Rules:

- Send source row ids, not display row indexes, when the grid is sorted/filtered.
- Cap row ids in the selection update, for example 1000 ids. Larger selections send shape only.
- Throttle updates to avoid flooding on drag-select.
- Host stores shape and active result only, not cell values.

---

## 10. Pinned results custom document

### 10.1 Provider design

```ts
export class PinnedQueryResultsDocumentProvider
    implements vscode.CustomReadonlyEditorProvider<PinnedQueryResultsDocument> {

    async openCustomDocument(uri: vscode.Uri, openContext: vscode.CustomDocumentOpenContext): Promise<PinnedQueryResultsDocument> {
        const snapshotId = parseSnapshotUri(uri).snapshotId;
        const lease = this.resultAccess.acquireSnapshot(snapshotId, {
            kind: "pinnedDocument",
            documentUri: uri.toString(),
            label: "Pinned Results document",
        });
        if (!lease) {
            return PinnedQueryResultsDocument.expired(uri, snapshotId);
        }
        return new PinnedQueryResultsDocument(uri, lease);
    }

    async resolveCustomEditor(document: PinnedQueryResultsDocument, panel: vscode.WebviewPanel): Promise<void> {
        const controller = new PinnedResultsController(document, panel, this.resultAccess, this.context);
        panel.onDidDispose(() => controller.dispose());
        await controller.initialize();
    }
}
```

Document lifecycle:

- `openCustomDocument` acquires a document lease.
- Each webview panel attaches to the document but does not create another physical data lease unless needed for per-panel telemetry.
- `document.dispose()` releases the lease.
- If the snapshot is missing or expired, render an expired document with a clear message and no row access.

### 10.2 URI and title

Use a friendly URI path ending in `.mssqlresults`:

```text
mssql-query-results-snapshot:/Pinned%20Results%20-%2012-45-03.mssqlresults?sid=<snapshotId>
```

The query contains the real snapshot id. The path controls tab title. Do not include raw server names, full file paths, SQL text, or database names in the URI unless user-facing product policy permits it.

### 10.3 Pinned document state

A pinned results document should show:

- result set captions and grids;
- source title and creation time;
- snapshot retention status;
- truncation/corruption badges;
- database/server display only when allowed by current classification policy;
- plan links for plan result sets;
- optional message summary.

It should not show:

- query editor;
- connection toolbar;
- execute/cancel buttons;
- unsaved/dirty state;
- reconnect UI.

### 10.4 Pinned document RPC

The pinned document can reuse a subset of Query Studio RPC names during the first slice:

| Existing request | Pinned behavior |
|---|---|
| `qs/getRows` | calls `resultAccess.getRows(snapshotId, ...)` |
| `qs/saveResult` | exports from snapshot |
| `qs/openCellDocument` | opens from snapshot |
| `qs/openPlan` | opens plan XML from snapshot |
| `qs/getPlanState` | builds plan state from snapshot plan result sets |
| `qs/setViewMode` | local view-state only |
| `qs/updateGridSelection` | updates pinned document result context |

Longer term, move these to neutral names under `queryResults/*` after the shared pane extraction settles. Do not make the first phase churn the RPC namespace if reusing `Qs*` keeps the diff smaller.

### 10.5 Messages and plans

Recommended first behavior:

- Capture message summary in every snapshot.
- Capture full messages locally for pinned docs only if count is under a threshold, or after the MessagesView virtualization work from the query optimization plan lands.
- Do not send message text to AI without confirmation.
- Include plan result sets in `Pin all results` by default because they are part of the run output, but render them as plan links, not giant XML grids.
- If plan XML is truncated or missing, show a plan-unavailable note.

---

## 11. Shared result pane extraction

### 11.1 Component target

Extract the current results pane into a reusable view:

```tsx
<QueryResultsPane
    mode="live" | "snapshot"
    state={resultsState}
    messages={messageState}
    gridStyle={gridStyle}
    capabilities={capabilities}
    dataSource={resultDataSource}
    actions={actions}
/>
```

`ResultGridBlock`, `GridCaption`, `MessagesView`, plan link rendering, text-view rendering, and `QsResultGridSurface` should move toward neutral names. The first PR can be conservative:

- export `GridCaption` and action slots;
- make `QsResultGridSurface` accept a `getRows` function or `ResultGridDataSource` instead of always calling `QsGetRowsRequest` directly;
- keep Query Studio-specific imports in a thin adapter.

### 11.2 Data source abstraction

```ts
export interface QueryResultsPaneDataSource {
    getRows(resultSetId: string, start: number, count: number): Promise<QsCellWindow>;
    saveResult(request: QueryResultSaveRequest): Promise<QueryResultSaveResponse>;
    openCellDocument(request: QueryResultOpenCellRequest): Promise<QueryResultOpenCellResponse>;
    openPlan?(resultSetId: string): Promise<{ opened: boolean }>;
    getMessages?(afterIndex?: number): Promise<{ messages: QsMessageRow[] }>;
}
```

Live Query Studio data source sends current `Qs*` requests to `QueryStudioController`.

Pinned results data source sends the same logical requests to `PinnedResultsController`.

### 11.3 Avoid UI memory regressions

The pinned pane must obey the same rules as live Query Studio:

- coarse state contains no row values;
- grid gets windows only;
- large results lazy-mount grids;
- copy/export fetch in chunks;
- sort/filter stay threshold-gated;
- text view remains capped or streaming, not unbounded.

---

## 12. QueryResultContextService

### 12.1 Purpose

Commands and chat need to know what "the current result" means. The context service owns that answer.

```ts
export interface QueryResultContextService {
    updateFromQueryStudio(sourceUri: vscode.Uri, update: QsGridSelectionUpdate): void;
    updateFromPinnedDocument(snapshotId: string, update: QsGridSelectionUpdate): void;
    setActiveSource(source: QueryResultActiveSource): void;
    clearSource(sourceId: string): void;

    current(): QueryResultResolvedContext | undefined;
    resolve(request: QueryResultContextResolveRequest): Promise<QueryResultResolvedContext | QueryResultContextNeedsPick>;
}
```

### 12.2 Resolution policy

When a command or chat prompt asks for "current results", resolve in this order:

1. focused pinned results document;
2. focused Query Studio grid selection;
3. active Query Studio editor with complete results;
4. most recent live source in the workspace;
5. explicit snapshot handle in the prompt or command args;
6. picker.

If two plausible sources exist and neither is focused, ask. Silent guesses are where UX goblins breed.

### 12.3 Context values for commands

Set VS Code contexts so menu items can appear only when useful:

```text
mssql.queryResults.hasActiveSource
mssql.queryResults.hasActiveSelection
mssql.queryResults.canPin
mssql.queryResults.canAskChat
mssql.queryResults.activeSourceKind = queryStudio | pinnedSnapshot
```

These contexts are booleans and enums only. Do not put ids, names, SQL, or object labels in context keys.

---

## 13. AI and external access

### 13.1 Tool first, participant second

Add one language model tool first:

```text
name: mssql_query_results
toolReferenceName: query_results
```

Operations:

```ts
export type QueryResultsToolOperation =
    | "list_live"
    | "list_snapshots"
    | "create_snapshot"
    | "describe_snapshot"
    | "sample_rows"
    | "get_rows"
    | "profile_result_set"
    | "export_snapshot"
    | "release_snapshot";
```

The tool should be implemented in `src/queryResults/queryResultsTool.ts` and registered from `MainController.registerLanguageModelTools()`.

### 13.2 Tool output classes

| Operation | Returns row values? | Confirmation |
|---|---:|---|
| `list_live` | no | no |
| `list_snapshots` | no | no |
| `create_snapshot` | no | no, unless query/message text is requested |
| `describe_snapshot` | no row values | no for schema/counts; yes for SQL/message text |
| `sample_rows` | yes | yes |
| `get_rows` | yes | yes |
| `profile_result_set` | maybe | no for counts/null ratios/types; yes for sample values/top values |
| `export_snapshot` | writes local/export data | yes |
| `release_snapshot` | no | no |

### 13.3 Confirmation text

Confirmation should show:

- source title;
- snapshot age;
- database/server display when allowed;
- result set count;
- row and column counts;
- requested row/sample bounds;
- approximate bytes to send;
- whether message text, query text, XML, JSON, or plan XML is included;
- requesting participant/tool;
- purpose/reason string.

Initial confirmation should allow three choices:

```text
Allow once
Cancel
Show details
```

Avoid "always allow" until enterprise and workspace policy is designed.

### 13.4 Bounds

Initial defaults:

```ts
const DEFAULT_AI_ROW_LIMIT = 100;
const DEFAULT_AI_CELL_LIMIT = 10_000;
const DEFAULT_AI_RESPONSE_BYTES = 1 * 1024 * 1024;
const DEFAULT_AI_SINGLE_CELL_BYTES = 16 * 1024;
const DEFAULT_AI_SNAPSHOT_TTL_MS = 30 * 60 * 1000;
```

Tool requests may ask for less. Requests above configured maximums are rejected or clipped with explicit `truncated: true` metadata. Never stream millions of rows into a tool response.

### 13.5 `@query` participant

Add later, after tool tests pass.

Package contribution:

```jsonc
{
  "id": "mssql.query",
  "name": "query",
  "description": "Analyze Query Studio result snapshots and pinned SQL results.",
  "isSticky": false,
  "commands": [
    { "name": "list", "description": "List active Query Studio results and snapshots." },
    { "name": "summarize", "description": "Summarize the active or selected result set." },
    { "name": "profile", "description": "Profile columns, nulls, row counts, and approved sample values." },
    { "name": "report", "description": "Create a Markdown report from approved snapshot data." },
    { "name": "pin", "description": "Pin active results to a snapshot document." }
  ]
}
```

The participant handler should be thin:

```text
prompt/context parsing
  -> QueryResultContextService.resolve(...)
  -> QueryResultAccessService operations
  -> LM tool-style confirmation for raw values
  -> response
```

Do not duplicate row fetching, sampling, or permission logic in the chat handler.

### 13.6 Inline completion integration

Inline completions should remain separate from non-AI result analysis.

Allowed:

- Include result metadata such as "2 result sets, first has 50 rows and 4 columns" in prompt context when already allowed by Copilot settings.
- Suggest command-shaped comments or snippets such as `-- Use @query /summarize on the current results`.

Not allowed:

- Send row values automatically.
- Summarize results inside inline completions.
- Create hidden snapshots for a completion request.

---

## 14. Sampling, profiling, and reports

### 14.1 Sampling strategies

```ts
export type QueryResultSampleStrategy =
    | "head"
    | "head_tail"
    | "uniform_windows"
    | "selection"
    | "visible_window";
```

Rules:

- `head` is cheapest and deterministic.
- `head_tail` catches footer/summary rows.
- `uniform_windows` fetches several small windows by row offset, not random cell scans.
- `selection` uses source row ids when available.
- `visible_window` lets chat ask about exactly what the user sees without copying the entire grid.

### 14.2 Profiling tiers

Profiling should happen locally and return bounded summaries.

| Tier | Data included | Confirmation |
|---|---|---|
| shape | row count, column count, sql types, truncation flags | no |
| safe counts | null counts, non-empty counts, approximate bytes, min/max length | no for local display; for model output, no values only |
| value sample | sample values, top values, min/max values | yes |
| full scan stats | computed over all rows, but returns aggregates only | ask if expensive; confirm if values included |

Add cancellation tokens and progress for full-scan profiling. Do not run a full scan on the extension host UI path without slicing/yielding.

### 14.3 Reports

`@query /report` should not shovel all data into the model. Recommended flow:

1. Describe snapshot.
2. Confirm and fetch bounded samples.
3. Optionally compute local aggregates.
4. Ask the model to write a report using summaries and samples.
5. Offer export if the user wants a full-data artifact.

For very large datasets, the local profiler does the counting; the model does prose.

---

## 15. Security and privacy

### 15.1 Classification

Treat fields as:

| Data | Classification |
|---|---|
| row values | `row.data` |
| XML/JSON/blob/text cell content | `row.data` |
| query text | `sql.text` |
| server message text | `provider.text` or `sql.text` depending source |
| plan XML | `sql.text` plus `identifier` |
| column names/types | schema/identifier metadata |
| row counts, column counts, durations | safe structural metadata |
| snapshot ids | internal opaque ids |

Use the existing classification vocabulary rather than inventing another one.

### 15.2 Hard requirements

- Snapshot ids are unguessable and in-memory only.
- Tool access is owner-scoped by conversation/tool invocation.
- Raw values require confirmation.
- Query text and message text require confirmation before model output.
- No raw row values, SQL text, message text, plan XML, or cell content in diagnostics.
- Pinned documents are local UI and do not persist beyond existing spill mechanics.
- Spill files remain under extension-owned storage and are removed when the final lease releases.
- Workspace trust and Copilot/enterprise disable settings must be respected.
- If a privacy gate cannot decide, deny row access and explain.

### 15.3 Settings

Keep settings minimal but real:

```jsonc
"mssql.queryResults.pinnedDocuments.enabled": true,
"mssql.queryResults.ai.enabled": true,
"mssql.queryResults.ai.maxRowsPerResponse": 100,
"mssql.queryResults.ai.maxBytesPerResponse": 1048576,
"mssql.queryResults.snapshot.ttlMinutes": 30,
"mssql.queryResults.snapshot.maxUnpinned": 10,
"mssql.queryResults.snapshot.maxRetainedBytesMb": 2048
```

During internal preview these can be hidden or experimental, but the retention and AI knobs should not be hardcoded forever.

---

## 16. Performance and scale design

### 16.1 Budgets

| Operation | Target |
|---|---:|
| create snapshot over completed result set | O(result set metadata), under 10 ms for normal runs |
| create snapshot over 50 result sets | under 50 ms, no row scan |
| pinned doc open, first paint | comparable to live results pane first paint |
| snapshot row-window fetch | live `RowStore.getRows` plus under 15 percent overhead |
| AI `describe_snapshot` | under 25 ms after snapshot exists |
| AI `sample_rows` 100 rows | bounded by row-window fetches and byte cap |
| dispose final lease | best-effort cleanup under 100 ms, async spill sweep allowed |

### 16.2 Avoid full copies

Snapshot creation copies:

- summaries;
- column metadata;
- message summary and optionally message rows;
- query digest/preview based on policy;
- result set id list;
- store lease.

Snapshot creation must not copy row pages.

### 16.3 Retention policy

Initial policy:

- pinned documents retain until close;
- AI/tool snapshots retain for TTL, default 30 minutes;
- unpinned expired snapshots are disposed first;
- least-recently-used unpinned snapshots are disposed when over budget;
- active leased snapshots are never silently deleted;
- if all snapshots are active and a new snapshot would exceed budget, return a clear error and offer export/pin cleanup.

### 16.4 Large cells

Large cells should follow the query optimization plan's truncation and large-cell path. Until STS2/full-cell retrieval improves:

- row windows contain the same values the grid can see;
- if values are truncated, snapshot/tool output must report truncation;
- opening a truncated XML/JSON/blob cell should say it is a prefix, not full content;
- AI tools should default to excluding huge cell values unless explicitly requested and confirmed.

---

## 17. STS2 and future result artifacts

### 17.1 Do not block phase 1 on STS2

The first implementation should retain extension-host result stores. STS2 already streams forward, and Query Studio already owns random access. This feature sits naturally on that boundary.

### 17.2 Future STS2/data-plane enhancements

Add later only if perf evidence shows local storage is insufficient:

- STS2 query returns a `resultArtifactId`.
- STS2 owns server-side retention leases.
- Data plane exposes `openResultArtifact`, `getResultRows`, `sampleResultArtifact`, `profileResultArtifact`, `disposeResultArtifact`.
- Large cell retrieval uses artifact and cell coordinates.
- Remote/webhost deployments implement the same artifact interface.

### 17.3 Interface now, storage later

The current implementation should define:

```ts
export interface QueryResultArtifact {
    readonly artifactId: string;
    readonly kind: "rowStoreV1" | "resultStoreV2" | "sts2" | "remote";
    getRows(resultSetId: string, start: number, count: number): Promise<QsCellWindow> | QsCellWindow;
    sample(params: QueryResultSampleRowsParams): Promise<QueryResultSample>;
    stats(): QueryResultStoreStats;
    retain(owner: QueryResultLeaseOwner): QueryResultStoreLease;
}
```

Then phase 1 can use `kind: "rowStoreV1"` while keeping consumers storage-agnostic.

---

## 18. Observability

### 18.1 Event families

Register names through the observability contracts process before emission if the branch requires registry-first discipline.

Minimum product markers/events:

```text
mssql.queryResults.snapshot.create.begin/end
mssql.queryResults.snapshot.acquire
mssql.queryResults.snapshot.release
mssql.queryResults.snapshot.dispose
mssql.queryResults.snapshot.retentionSweep
mssql.queryResults.rows.windowFetch.begin/end
mssql.queryResults.pin.open.begin/end
mssql.queryResults.pin.close
mssql.queryResults.context.update
mssql.queryResults.aiTool.invoke.begin/end
mssql.queryResults.aiTool.confirmation
mssql.queryResults.aiTool.denied
mssql.queryResults.profile.begin/end
mssql.queryResults.sample.begin/end
```

### 18.2 Allowed fields

Allowed in diagnostics:

- snapshot id short digest;
- lease id short digest;
- owner kind;
- source kind;
- source URI digest;
- result-set count;
- rows requested/returned;
- columns count;
- approximate bytes;
- cache/spill hit counts;
- duration;
- error/failure code;
- confirmation outcome;
- retention action.

Never emit:

- row values;
- cell text;
- XML/JSON/blob content;
- SQL text;
- server message text;
- plan XML;
- full source URI;
- raw server/database/user names unless the active diagnostics policy explicitly allows them.

### 18.3 Debug/status command

Add `mssql.queryResults.showStatus` with:

- live sources;
- snapshot count;
- lease counts by owner kind;
- retained bytes;
- spill bytes;
- expired snapshot count;
- last cleanup result;
- AI tool enablement and limits;
- recent denied operations.

No row values. No SQL.

---

## 19. Testing plan

### 19.1 Unit tests

Add tests under `extensions/mssql/test/unit/queryResults*.test.ts` or equivalent:

- snapshot survives query rerun;
- snapshot survives source document close;
- final lease release deletes spill files;
- multiple snapshots share one physical store;
- releasing one lease does not break another;
- live release without snapshots deletes store;
- completed-only rule rejects incomplete result sets;
- `getRows` from snapshot matches live `RowStore.getRows` byte-for-byte for compact windows;
- snapshot clamps to frozen row count;
- corrupted store surfaces short/corrupt window, not throw;
- TTL cleanup touches only unleased snapshots;
- retention budget refuses or sweeps in correct order;
- message/query capture policy is honored;
- no row values in diagnostics payloads.

### 19.2 Controller tests

- `qs/pinResultSet` creates snapshot and opens custom document;
- `qs/pinAllResults` includes correct result sets and reports skipped incomplete sets;
- invalid result set id returns clear error;
- source rerun does not affect pinned rows;
- source document close does not affect pinned rows;
- `QsUpdateGridSelectionRequest` updates host context;
- open cell from pinned document reads snapshot, not live source;
- export from pinned document reads snapshot, not live source;
- plan open from pinned document reads snapshot plan result.

### 19.3 Webview/component tests

- pin button enablement by result state;
- pinned document renders same grid rows as source snapshot;
- result pane works with live and snapshot data sources;
- copy commands still fetch chunks;
- sort/filter thresholds remain enforced;
- large result sets lazy-mount grids;
- expired snapshot document shows recovery message.

### 19.4 AI tool tests

- `list_live`, `list_snapshots`, `describe_snapshot` return no row values;
- row access prompts for confirmation;
- denied confirmation returns a safe tool result;
- row/cell/byte bounds are enforced;
- tool cannot read another conversation's owner-scoped lease;
- released handle cannot fetch rows;
- tool output truncation metadata is accurate;
- seeded secret/row canaries do not appear in diagnostics.

### 19.5 Perf tests

Add scenarios when the harness has Query Studio result probes:

- 10k rows, pin one result set, first paint pinned document;
- 1M rows with spill, snapshot create no row scan;
- many result sets, pin all, lazy grid mounting;
- sample 100 rows from large snapshot;
- rerun source while pinned doc visible;
- close source while pinned doc visible;
- retention sweep with many expired snapshots.

---

## 20. Execution plan

### C2D-0: Spike and freeze seams

**Goal:** Prove the two riskiest host seams before broad code changes.

Tasks:

1. Verify `CustomReadonlyEditorProvider` can open a `mssql-query-results-snapshot:` virtual URI with `vscode.openWith`.
2. If needed, implement a minimal readonly `FileSystemProvider` for the virtual scheme.
3. Add a tiny fake pinned document that renders static HTML and closes cleanly.
4. Add a small `QueryResultsPaneDataSource` experiment that lets `QsResultGridSurface` accept an injected `getRows` function.
5. Decide whether phase 1 will reuse `Qs*` RPC names in the pinned webview or introduce neutral `queryResults/*` names immediately.

Exit gate:

- A custom results tab can open, split, close, and dispose without a real file.
- A fake row window can render in the existing grid without forking `FluentResultGrid`.

### C2D-1: Result access service and retainable store

**Goal:** Land lifetime-correct snapshots without UI.

Tasks:

1. Add `src/queryResults/queryResultTypes.ts`.
2. Add `RetainedRowStore` wrapper around current `RowStore`.
3. Change `ExecutionHost` to create retained stores and release live owner on rerun/dispose.
4. Add `QueryStudioLiveResultSource` adapter.
5. Add `QueryResultAccessService` with live-source registration, snapshot creation, acquire/release, row windows, and retention.
6. Add diagnostics for create/acquire/release/dispose.
7. Add deep unit tests.

Exit gate:

- All lifetime tests pass.
- Snapshot creation performs no row scan.
- Rerun no longer deletes leased prior results.
- Final lease release deletes spill.

### C2D-2: Query Studio pin commands

**Goal:** Let Query Studio create snapshots from live results.

Tasks:

1. Add `QsPinResultSetRequest`, `QsPinAllResultsRequest`, and `QsPopOutResultsRequest`.
2. Wire controller handlers to `QueryResultAccessService`.
3. Add pin button via `GridCaption.children` or an explicit action slot.
4. Add result-pane header action for `Pin All Results` or `Pop Out Results`.
5. Add command palette commands that target active Query Studio.
6. Add user notices for incomplete/streaming results.

Exit gate:

- Pin result set creates snapshot with correct summary.
- Pin all creates snapshot with all complete sets.
- Streaming or incomplete sets are handled honestly.

### C2D-3: Pinned results custom document

**Goal:** Open and render snapshot-backed result tabs.

Tasks:

1. Add package contribution for `mssql.queryResultsSnapshot` custom editor.
2. Add `PinnedQueryResultsDocumentProvider`.
3. Add `PinnedResultsController` with row/export/open-cell/plan handlers.
4. Extract shared result pane pieces enough to avoid grid fork.
5. Open pinned doc from Query Studio pin commands.
6. Release document lease on close.
7. Add tests for source rerun and source close stability.

Exit gate:

- Pinned document displays original rows after source rerun changes live results.
- Pinned document displays rows after source Query Studio closes.
- Copy/export/open-cell work from pinned doc.
- Closing pinned doc releases final lease.

### C2D-4: Result context tracking

**Goal:** Make "current result" a real product concept.

Tasks:

1. Expand `QsUpdateGridSelectionRequest` payload.
2. Add selection/focus event wiring in result grid, with throttling.
3. Add `QueryResultContextService`.
4. Update Query Studio and pinned controllers to feed context.
5. Add VS Code context keys for result commands.
6. Add `mssql.queryResults.showStatus`.

Exit gate:

- Commands can resolve active source/result set/selection.
- Sorted/filtered selection uses source row ids or shape-only fallback.
- No row values are stored in context.

### C2D-5: Language model tool

**Goal:** Expose bounded result access to models through one audited tool.

Tasks:

1. Add `QueryResultsTool` class.
2. Add tool constants and package contribution if required.
3. Register from `MainController.registerLanguageModelTools()`.
4. Implement list/create/describe/sample/get/profile/export/release.
5. Add confirmation service for raw values and sensitive text.
6. Add byte/row/cell caps.
7. Add tool tests and privacy canaries.

Exit gate:

- Metadata-only operations work without row access.
- Raw rows cannot be returned without confirmation.
- Tool output is bounded and has accurate truncation metadata.

### C2D-6: `@query` participant

**Goal:** Add a friendly chat surface over the same service.

Tasks:

1. Add package `chatParticipants` entry for `mssql.query`.
2. Register participant from `extension.ts` or a query-results activation module.
3. Implement `/list`, `/summarize`, `/profile`, `/report`, `/pin`.
4. Use `QueryResultContextService.resolve` for context.
5. Reuse tool privacy and bounds.
6. Add follow-ups such as "Pin these results" and "Profile columns".

Exit gate:

- `@query` never reads ambiguous results silently.
- `@query /summarize` uses confirmed samples and summaries, not full data.
- Existing `mssql.agent` remains unchanged.

### C2D-7: Sampling, profiling, and reporting polish

**Goal:** Make chat useful for large data without large transfers.

Tasks:

1. Add `resultSampler.ts`.
2. Add local shape/null/count profiler.
3. Add optional value/top-value profiling behind confirmation.
4. Add Markdown report generation over summaries/samples.
5. Add progress/cancellation for full scans.

Exit gate:

- Large snapshots produce useful summaries with bounded model output.
- Full scans are cancelable and do not block the extension host.

### C2D-8: Perf, retention, and cleanup hardening

**Goal:** Make the feature safe under dogfood load.

Tasks:

1. Add perf markers and central observability vocabulary entries.
2. Add retention settings and status UI.
3. Add startup/deactivation spill sweep for abandoned retained stores.
4. Add perf scenarios.
5. Add memory pressure behavior.
6. Add stress tests for many snapshots and large spills.

Exit gate:

- Retention is predictable.
- Deactivation cleans up.
- Large pinned snapshots keep renderer memory bounded.

### C2D-9: Future storage tiers

**Goal:** Prepare for deeper optimization and remote/web modes.

Tasks:

1. Implement `ResultStoreV2` behind `IQueryResultStore` after query optimization work lands.
2. Add optional STS2 result artifact capability detection.
3. Add artifact-backed snapshots only when STS2 can guarantee retained result leases.
4. Add persistent `.mssqlresults` design if users want saved result bundles.

Exit gate:

- Consumers do not change when storage changes.
- Result windows remain bounded across all backends.

---

## 21. Acceptance gates

### Preview gate

- Pin one result set and pin all complete results from Query Studio.
- Open pinned result custom document.
- Rerun source query and prove pinned rows unchanged.
- Close source Query Studio and prove pinned rows still available.
- Close pinned document and prove spill cleanup after final lease.
- No row values in coarse state or diagnostics.
- Snapshot creation does not scan rows.
- All unit/controller tests pass.

### AI tool gate

- Tool is registered and discoverable.
- Metadata-only operations return bounded summaries.
- Raw rows require confirmation.
- Bounds are enforced.
- Denied access is safe and clear.
- Owner-scoped leases prevent accidental cross-chat access.
- Privacy canary passes.

### Dogfood gate

- Large result snapshots do not regress Query Studio scrolling.
- Many snapshots do not leak spill files after close/expiry.
- Status command shows retained bytes and leases accurately.
- Central observability captures durations/counts only.
- `@query` asks for context when ambiguous.

---

## 22. Recommended answers to open questions

| Question | Recommendation |
|---|---|
| WebviewPanel or custom document? | Use `CustomReadonlyEditorProvider` as the target. Spike first. Fall back only if VS Code rejects virtual snapshot URIs. |
| Should snapshots include messages? | Always include message summary. Full message text stays local and is rendered only after message virtualization or below a threshold. AI needs confirmation. |
| Should pin all include plans? | Yes, include plan result sets by default, but render as plan links and mark truncated plans honestly. |
| What AI TTL? | 30 minutes for unpinned AI snapshots. Pinned docs retain until close. |
| Can AI use inactive Query Studio documents? | Yes only when explicitly selected or unambiguous in a picker. Active focused result is the default. |
| Should snapshot ids be visible? | Hide by default. Add copy-handle command under diagnostics/dev setting. |
| Should `@query /python` export temp CSV/JSON? | Generate a local script scaffold first. Export temp data only after explicit user confirmation. Do not silently rerun SQL. |
| Should `create_snapshot` require confirmation? | Not for handle creation and schema/counts. Require confirmation for row values, SQL text, message text, and plan XML. |
| Should we wait for ResultStoreV2? | No. Build against `IQueryResultStore` and wrap current `RowStore`. Swap in ResultStoreV2 later. |

---

## 23. First coding-agent handoff

Start with **C2D-0 and C2D-1 only**. Do not start chat or AI work until snapshot lifetime is mechanically correct.

### Files to inspect first

```text
extensions/mssql/src/queryStudio/rowStore.ts
extensions/mssql/src/queryStudio/executionHost.ts
extensions/mssql/src/queryStudio/queryStudioController.ts
extensions/mssql/src/queryStudio/queryStudioDocumentModel.ts
extensions/mssql/src/queryStudio/queryStudioProvider.ts
extensions/mssql/src/sharedInterfaces/queryStudio.ts
extensions/mssql/src/queryStudio/resultExport.ts
extensions/mssql/src/webviews/pages/QueryStudio/results.tsx
extensions/mssql/src/webviews/pages/QueryStudio/resultsGrid.tsx
extensions/mssql/src/controllers/mainController.ts
extensions/mssql/src/extension.ts
extensions/mssql/package.json
```

### First PR target

1. Add `src/queryResults/queryResultTypes.ts`.
2. Add `src/queryResults/resultStoreLease.ts` with `RetainedRowStore`.
3. Update `ExecutionHost` to use retained store on rerun/dispose.
4. Add `src/queryResults/queryResultAccessService.ts` with create/acquire/release/list/describe/getRows.
5. Add a fake `LiveQueryResultSource` test harness.
6. Add unit tests for lease lifetime and row-window equivalence.
7. Add diagnostics with safe fields only.

### Do not do in first PR

- Do not add AI tool.
- Do not add `@query` participant.
- Do not add persistent result files.
- Do not rewrite `RowStore` spill format.
- Do not fork the result grid.
- Do not send row data to any diagnostic or model path.

---

## 24. Design checklist

Before coding each phase, verify:

- Does this operation copy rows? If yes, is it bounded, confirmed, or export-only?
- Does this operation keep a lease? If yes, who releases it?
- What happens on source rerun?
- What happens on source document close?
- What happens on pinned document close?
- What happens on extension deactivation?
- Can this path leak row values into state, logs, diagnostics, telemetry, or model output?
- Is the storage backend hidden behind `IQueryResultStore`?
- Is the UI fetching windows only?
- Is the active context explicit, or are we guessing?

If the answer smells like wet cardboard, pause and add the missing seam.
