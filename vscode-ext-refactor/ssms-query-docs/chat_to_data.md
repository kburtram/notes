# Chat To Data: Query Studio Result Snapshots, Pinning, and AI Access

Status: draft proposal for review
Date: 2026-07-09
Scope: `vscode-mssql` Query Studio, Query Studio result storage, extension AI/chat/tool seams, and STS2 query-result integration points.

## Executive Summary

Query Studio already has the most important prerequisite for "chat to data": query results are streamed into an extension-owned `RowStore`, rendered through bounded `qs/getRows` windows, and shared by every split editor for the same backing document. The missing piece is a stable result ownership model. Today `ExecutionHost` owns exactly one live `RowStore`; rerunning the query or closing the last editor panel disposes that store and its spill files. That is correct for a live editor, but it is not enough for AI analysis, external consumers, or "Pin these results to a new document."

The recommended design is to add a Query Studio result snapshot service in the extension host:

- A snapshot is an immutable, reference-counted view of one or more result sets from a completed Query Studio run.
- A snapshot has leases. Query Studio, AI tools, chat participants, pinned result documents, and future consumers acquire and release leases by owner.
- Rerunning a query creates a new live `RowStore`; any leased previous store remains available until the last lease is released.
- Pinned result documents reuse the existing Query Studio result grid components, but their data source is a snapshot instead of the live `ExecutionHost`.
- AI access goes through bounded, explicit, diagnosable tools. The model gets metadata and samples by default, and it must request bounded row windows from a snapshot when raw data is needed.

This keeps the feature separate from the existing `mssql.agent` chat handler while still integrating with the extension's existing language model tool registration, Query Studio inline completions, result export commands, and diagnostics.

## Goals

1. Let AI services inspect and process Query Studio result data that is already available to the result grid.
2. Let users pin one result set or all result sets into a new read-only result-grid document that is disconnected from the live query.
3. Preserve result data for external consumers without blocking query reruns or editor close.
4. Avoid copying large result sets unless a consumer asks for a transformed/exported representation.
5. Make all AI data access explicit, bounded, auditable, and safe for large results, blobs, XML, and JSON.
6. Keep this feature separate from the current `mssql.agent` participant name and handler.
7. Build a reusable result access contract that can support chat, inline intent flows, tools, and future non-AI features.

## Non-Goals

- Do not invent a persistent new result file format in this phase.
- Do not make pinned result documents hot-exit/restorable across VS Code restarts in this phase.
- Do not send full result sets to an LLM automatically.
- Do not rewrite STS2 query execution as a prerequisite. The extension-host snapshot service should work with the current Query Studio path first.
- Do not merge this with the current `mssql.agent` chat participant. A separate `@query` participant can be added later.
- Do not make snapshots mutable. If a future feature edits or annotates result data, it should create a derived snapshot.

## Current Implementation Review

### Query Studio Editor and Model Lifetime

Query Studio is registered as a custom text editor with:

- `QUERY_STUDIO_VIEW_TYPE = "mssql.queryStudio"`
- `supportsMultipleEditorsPerDocument: true`
- `retainContextWhenHidden: true`

The provider keeps a `liveModels` map keyed by backing document URI and exposes `findQueryStudioModel(uri)`. This is already a cross-feature seam: inline completions use it to find Query Studio metadata and session context.

`QueryStudioDocumentModel` is the shared state for every Query Studio panel over the same document. It owns:

- the backing VS Code `TextDocument`
- `DocumentSessionBinding`
- `ExecutionHost`
- text sync and hot-exit backup plumbing

When the last panel for a document is disposed, `QueryStudioDocumentModel.dispose()` disposes the `ExecutionHost`, the session binding, and the text listeners. This means result data has the same lifetime as the live Query Studio document today.

### ExecutionHost and Current Result Ownership

`ExecutionHost` owns the live run:

- `private rowStore: RowStore | undefined`
- `private orchestrator: ExecutionOrchestrator | undefined`
- message rows
- result-set summaries
- execution state
- fanout listeners for every attached panel

On every normal run, `ExecutionHost.execute()` does this:

```ts
// Fresh run: previous results (and spill) are released NOW.
this.rowStore?.dispose();
this.runCounter++;
this.rowStore = new RowStore(path.join(this.spillRoot, `run${this.runCounter}`), ...);
this.messages = [];
this.summaries.clear();
this.summaryOrder = [];
```

That behavior is exactly why snapshots are needed. The current design makes the latest run cheap and easy to reason about, but it gives no way for a consumer to keep stable access to the previous run while the editor moves on.

### RowStore

`RowStore` stores result data as compact pages:

- in-memory page cache with LRU eviction
- optional spill file under the Query Studio spill root
- per-result-set summaries and columns
- bounded `getRows(resultSetId, start, count)` materialization
- diagnostics for append, spill write, spill read, and row window fetches

`RowStore.dispose()` clears the in-memory state, closes the spill file, deletes the spill file, and removes the spill directory. This is the correct cleanup primitive for an unleased live run, but it must become lease-aware before AI or pinned documents can retain old result data.

The existing store is already close to a good snapshot backing store because query result pages are append-only and row windows are read-only. Once a result set is complete, its pages are naturally immutable. That means the "copy-on-write" requirement can be met mostly by ownership and immutability rather than by copying pages.

### Result RPC and UI

The current Query Studio webview gets rows through bounded RPC:

- `QsGetRowsRequest` returns `QsCellWindow`
- `QsSaveResultRequest` exports a result set as CSV, JSON, or INSERT
- `QsOpenCellDocumentRequest` opens XML/JSON/text cells in side documents
- `QsOpenPlanRequest` and `QsGetPlanStateRequest` handle showplan XML
- `QsUpdateGridSelectionRequest` exists but is currently a no-op

The result pane uses `results.tsx` and `resultsGrid.tsx`:

- `GridCaption` renders the per-result-set caption, row count, plan link, and maximize button.
- `ResultGridBlock` lazy-mounts grids for many-result-set runs.
- `QsResultGridSurface` adapts Query Studio results into the shared `FluentResultGrid`.
- Grid commands are centralized in `handleCommand`, including copy, copy with headers, export CSV/JSON/INSERT, switch-to-text, and open-cell.

These are good integration points:

- `GridCaption` is the right place for "Pin this result set."
- A result-pane header command is the right place for "Pin all results."
- `QsUpdateGridSelectionRequest` should become the live selection/current-result tracking seam for AI and context commands.
- The grid data source should be factored so it can point at either live `ExecutionHost` data or snapshot data.

### Existing AI Surfaces

The extension currently has three relevant AI seams:

1. A chat participant:
   - id: `mssql.agent`
   - handler: `createSqlAgentRequestHandler(...)`
   - registered in `extension.ts`

2. Language model tools:
   - registered in `MainController.registerLanguageModelTools()`
   - existing tools include `mssql_run_query`, schema/object listing, connect/disconnect, DAB, and schema designer

3. Query Studio inline completions:
   - Query Studio webview calls `QsInlineCompletionRequest`
   - `QueryStudioController` forwards to the shared SQL inline completion provider
   - accepted completions call `mssql.copilot.inlineCompletion.accepted`

`mssql_run_query` currently uses STS v1 `query/simpleexecute` and returns rows directly in a JSON tool result. It is useful, but it is not a Query Studio result access feature. It executes a query through a different path and does not operate on the result grid's in-memory data.

## Required New Concepts

### Live Run

A live run is the current execution owned by `ExecutionHost`. It may be executing, complete, canceled, failed, or replaced by a later run.

### Result Store

A result store is the physical backing data for one run. Today this is `RowStore`. In the proposed design it becomes lease-aware and can be retained after the live run stops referencing it.

### Snapshot

A snapshot is a logical, immutable view over one or more result sets from a result store. It has:

- stable `snapshotId`
- source document URI and display name
- source run id
- result set ids included in the snapshot
- result summaries at snapshot time
- optional query text digest and selected query text
- optional messages captured at snapshot time
- creation time
- owner leases
- row and byte limits
- diagnostics counters

### Lease

A lease is an owner reference that keeps a snapshot alive. Example owners:

- `queryStudio.pinDocument`
- `queryStudio.aiTool`
- `queryStudio.chatParticipant`
- `queryStudio.export`
- `queryStudio.debug`

When the last lease is released, the snapshot can dispose its retained store reference and delete spill files if no other snapshot uses them.

### Pinned Result Document

A pinned result document is a read-only editor tab/webview that renders one snapshot. It is not backed by a user file and does not participate in save/hot-exit in the first phase. It releases its lease when closed.

### AI Result Handle

An AI result handle is a snapshot id plus optional result-set scope and access limits. Tools and chat participants should exchange handles and metadata first, then fetch bounded data windows only when needed.

## Core Proposal

### Add QueryResultSnapshotService

Add a service in the extension host, owned by the Query Studio feature registration or main controller:

```ts
export interface QueryResultSnapshotService extends vscode.Disposable {
    createSnapshot(request: CreateResultSnapshotRequest): Promise<ResultSnapshotLease>;
    acquire(snapshotId: string, owner: SnapshotOwner): ResultSnapshotLease | undefined;
    release(leaseId: string): void;
    list(filter?: SnapshotListFilter): ResultSnapshotSummary[];
    describe(snapshotId: string): ResultSnapshotDescription | undefined;
    getRows(params: SnapshotGetRowsParams): QsCellWindow;
    exportResult(params: SnapshotExportParams): Promise<SnapshotExportResult>;
}
```

The service should be the only extension-host component that knows all retained snapshots. `ExecutionHost` should not own snapshots directly; it should only offer the current run store and summaries to the service.

Recommended file placement:

- `src/queryStudio/results/queryResultSnapshotService.ts`
- `src/queryStudio/results/resultSnapshotTypes.ts`
- `src/queryStudio/results/pinnedResultDocumentProvider.ts`

The exact folder is flexible, but this should stay under `queryStudio` rather than under `copilot`, because snapshots are not an AI-only feature.

### Make RowStore Retainable

The smallest viable implementation is to add retain/release semantics around the existing `RowStore`:

```ts
export class RowStore {
    private refCount = 1;
    private disposed = false;
    private pendingDispose = false;

    retain(owner: string): RowStoreLease;
    release(leaseId: string): void;
    dispose(): void; // releases the live owner
}
```

However, that may overload `dispose()` and make lifetime bugs harder to spot. A clearer design is:

```ts
export class ResultStore {
    readonly runId: string;
    readonly spillRoot: string;

    retain(owner: SnapshotOwner): ResultStoreLease;
    release(leaseId: string): void;
    markLiveOwnerReleased(): void;
    getRows(resultSetId: string, start: number, count: number): QsCellWindow;
    getStats(): ResultStoreStats;
}
```

Then either rename `RowStore` to `ResultStore`, or wrap the current `RowStore` behind `ResultStoreLease`. The wrapper option is safer for an incremental branch because existing query execution code can keep using `RowStore` while the snapshot service manages retained references.

### Change ExecutionHost Replacement Semantics

Today rerun does:

```ts
this.rowStore?.dispose();
this.rowStore = new RowStore(...);
```

With snapshots, rerun should do:

```ts
this.currentRunStore?.releaseLiveOwner("rerun");
this.currentRunStore = createRunStore(...);
```

If no snapshots exist, release deletes the store immediately. If snapshots exist, the live editor detaches while snapshot leases keep the store alive.

Closing the last Query Studio editor should follow the same rule:

- dispose live session and model
- release the live owner on the current result store
- do not break snapshots or pinned documents
- let snapshot leases decide when the store is deleted

### Prefer Completed Snapshots First

The first version should snapshot only completed result sets. This avoids ambiguous behavior while rows are still streaming.

Rules:

- "Pin result set" is enabled only when that result set is complete.
- "Pin all results" pins complete result sets and warns if incomplete sets are skipped.
- AI tools can list live incomplete result sets, but `snapshot` should either wait for completion, fail with a clear message, or snapshot only completed result sets based on a requested mode.

Future work can add streaming snapshots, but that requires more complicated semantics:

- Does the snapshot continue to grow?
- Does it freeze at the click time?
- If it freezes while the live query continues, do later appends copy pages to a new store?

The completed-only rule is the right first step because it matches the user's mental model for "analyze these results" and keeps copy-on-write simple.

### Copy-On-Write Interpretation

For completed result sets, no physical copy is needed. The old store is immutable after the run completes, and rerun creates a new store. Logical disconnection is achieved by:

- snapshot refers to old store and fixed result-set ids
- live Query Studio switches to a new store on rerun
- both stores can share implementation code, not mutable state

If a future feature creates derived data, such as filtered/sorted/annotated snapshot rows, it should create a derived snapshot that references the base snapshot and stores only the delta. That is where true copy-on-write becomes useful.

### Snapshot Metadata

Each snapshot should include enough metadata for UX, diagnostics, and AI grounding:

```ts
export interface ResultSnapshotSummary {
    snapshotId: string;
    sourceUri: string;
    sourceTitle: string;
    runId: string;
    createdEpochMs: number;
    ownerCount: number;
    resultSetCount: number;
    totalRows: number;
    totalBytesApprox?: number;
    complete: boolean;
    hasErrors: boolean;
    purpose: "pin" | "ai" | "export" | "debug" | "external";
}

export interface ResultSnapshotDescription extends ResultSnapshotSummary {
    queryTextPreview?: string;
    queryTextDigest?: string;
    database?: string;
    server?: string;
    resultSets: QsResultSetSummary[];
    messages?: SnapshotMessageSummary;
    storeStats: ResultStoreStats;
}
```

Do not store raw SQL text in diagnostics by default. For the snapshot object itself, storing selected query text is useful for a pinned document title and AI grounding, but diagnostics should use digests and small previews only when explicitly enabled.

## Pin Results UX

### Commands

Add Query Studio commands:

- `mssql.queryStudio.pinResultSet`
- `mssql.queryStudio.pinAllResults`
- optionally `mssql.queryStudio.copySnapshotHandle` for diagnostics/testing

The visible UI should be:

- A pin button in each result-set caption next to maximize.
- A "Pin All Results" command in the result pane header overflow menu.
- Optional result-grid context menu entry for "Pin Result Set."

The current grid caption already has children and a maximize button; adding a pin button there is low-risk. The result grid command surface already maps `FluentResultGridCommand` values to host commands, but the pin command may need a Query Studio-local command if the shared component does not have an existing command id. Keep the shared grid component unchanged unless a generic "custom command" extension point already exists.

### Pinned Document Behavior

The pinned document should:

- open as a normal editor tab
- have a clear title, such as `Pinned Results - Untitled-1 - 12:45:03 PM`
- show the same result grid experience as Query Studio
- support copy, copy with headers, open XML/JSON cell, export CSV/JSON/INSERT, switch to text view, sort/filter where supported
- not show query editor chrome
- not be dirty
- not prompt to save on close
- release its snapshot lease on close

The first implementation can use a `WebviewPanel` instead of a full custom editor provider because the document is temporary and not file-backed. If editor-tab integration requires a custom editor, use a readonly virtual URI such as:

```txt
mssql-query-results-snapshot:/<snapshotId>
```

Do not use a scratch file. The user already rejected scratch-file UX for untitled Query Studio, and pinned results are explicitly temporary.

### Reusing the Existing Result Components

The pinned result UI should not fork the grid. Instead, extract a narrow data-source adapter:

```ts
export interface QueryResultDataSource {
    getState(): QsResultsState;
    getRows(resultSetId: string, start: number, count: number): Promise<QsCellWindow>;
    saveResult(request: SaveResultRequest): Promise<SaveResultResponse>;
    openCellDocument(request: OpenCellRequest): Promise<OpenCellResponse>;
}
```

Live Query Studio uses RPC to `ExecutionHost`.

Pinned results use RPC to `QueryResultSnapshotService`.

The React component tree should not care whether the data is live or pinned after the initial state is loaded.

### Messages and Plans in Pinned Documents

Result snapshots should capture enough message metadata for AI and diagnostics, but the first pinned result document can focus on result grids. Execution plans need special handling because Query Studio already treats showplan XML as a plan tab, not a normal grid.

Recommended behavior:

- If the snapshot includes a plan result set, preserve the existing "Open execution plan" behavior.
- Do not add a full Messages tab to pinned results in the first phase unless it falls out naturally from the reusable results pane.
- Add message capture to the snapshot object so `@query summarize` can explain failures and row-count messages even when the pinned UI does not render them yet.

## AI and External Access Proposal

### Keep AI Access Separate From `mssql.agent`

Add a separate result-data surface instead of extending `mssql.agent` directly:

- Chat participant id: `mssql.query`
- User-facing participant name: `query`
- Tool reference name: `query_results`
- Tool contribution name: `mssql_query_results`

The existing `mssql.agent` can later call the same service if desired, but the first implementation should not mix handlers.

### Add a Query Results Language Model Tool

Register one bounded tool first:

```ts
export interface QueryResultsToolInput {
    operation:
        | "list_live"
        | "list_snapshots"
        | "create_snapshot"
        | "describe_snapshot"
        | "sample_rows"
        | "get_rows"
        | "release_snapshot";
    snapshotId?: string;
    sourceUri?: string;
    resultSetIds?: string[];
    resultSetId?: string;
    start?: number;
    count?: number;
    sample?: {
        maxRowsPerResultSet: number;
        strategy: "head" | "head_tail" | "uniform";
    };
    reason?: string;
}
```

Tool output should be JSON and should remain bounded:

- `list_live` returns metadata only.
- `create_snapshot` returns a snapshot handle and summaries.
- `describe_snapshot` returns schema, row counts, result-set metadata, truncation flags, and message summary.
- `sample_rows` returns limited sample rows with byte limits.
- `get_rows` returns a requested bounded window and should reject huge requests.
- `release_snapshot` releases the tool lease.

The tool should not return all rows by default. If the model wants to build a report over large data, it should first inspect metadata and samples, then request windows or ask the user to export data.

### Confirmation and Consent

Result data is user data. AI tools must ask for confirmation before raw rows leave the extension host for a language model. The confirmation should say:

- source document/title
- database/server when available
- result-set count
- row count and approximate byte count
- requested row/sample bounds
- consumer purpose/reason

Metadata-only operations can be allowed without confirmation if they do not include row values. Recommended split:

- No confirmation: list active result sets, list snapshot ids owned by the conversation, describe columns and row counts.
- Confirmation required: create snapshot for AI, sample rows, get rows, export snapshot to a temp file for AI workflow.

This mirrors the existing `mssql_run_query` confirmation model, but with clearer data-sharing semantics because the query has already run.

### Data Bounds

Default bounds should be conservative:

- max rows per tool response: 100
- max cells per tool response: 10,000
- max bytes per tool response: 1 MB
- max single cell bytes: honor Query Studio's existing `maxCellBytes` and truncation markers
- max snapshot retention for AI without pinned document: configurable TTL, default 30 minutes

All limits should be settings-backed or query-tuning-backed later, but the first implementation can use constants plus diagnostics.

### Chat Participant `@query`

The chat participant can be built after the tool works. It should be a thin orchestrator over the same snapshot service and tool operations.

Suggested commands:

- `@query /list` - list active Query Studio results and snapshots
- `@query /summarize` - summarize active or selected result set
- `@query /profile` - describe columns, nulls if known, row counts, and sample values
- `@query /python` - build a Python script for the selected snapshot
- `@query /report` - create a Markdown report from selected snapshot data
- `@query /pin` - pin active result set or all result sets

The participant should resolve context in this order:

1. current Query Studio grid selection from `QsUpdateGridSelectionRequest`
2. active Query Studio editor result state
3. explicit snapshot handle in the prompt
4. explicit result-set reference from a chat variable or slash command

If no result context is clear, it should ask the user to pick a result set instead of guessing.

### Inline Completion Intent Integration

Inline completions should not become a hidden data exfiltration path. They can help with intent prompts, but they should not send row data to the model automatically.

Recommended behavior:

- The inline-completion prompt may include result metadata only: "active Query Studio has 2 result sets; result 1 has 50 rows and columns A, B, C."
- For comments like `-- summarize the results from this query`, inline completion should suggest a command-shaped SQL comment or a generated query/report scaffold, not silently summarize rows.
- If the desired result requires data access, the completion can insert a clear instruction or command hint, such as "Use @query /summarize on the current results."
- Full row access remains behind the `mssql_query_results` tool confirmation flow.

This keeps the automatic completion path fast, low-risk, and predictable.

### Agent "Run Query and Report" Flow

There are two distinct flows:

1. Query has already been run in Query Studio.
   - Agent lists live results.
   - Agent creates a snapshot.
   - Agent reads metadata/sample/windows.
   - Agent builds report/script.

2. Agent needs to run a query first.
   - Existing `mssql_run_query` can run small direct queries today.
   - A future `query_run_to_snapshot` operation could run through Query Studio/STSv2 and create a snapshot as the result.

The first phase should focus on already-rendered Query Studio results. Running queries from AI has higher safety and confirmation requirements and overlaps with existing `mssql_run_query`.

## API Sketches

### Snapshot Creation From Live Query Studio

```ts
export interface CreateResultSnapshotRequest {
    sourceUri: vscode.Uri;
    owner: SnapshotOwner;
    scope: "resultSet" | "allResultSets";
    resultSetIds?: string[];
    includeMessages?: boolean;
    reason: string;
    waitForCompletion?: "never" | "prompt" | "always";
}

export interface ResultSnapshotLease {
    snapshotId: string;
    leaseId: string;
    owner: SnapshotOwner;
    description: ResultSnapshotDescription;
    dispose(): void;
}
```

`QueryStudioController` can handle webview pin requests by calling:

```ts
snapshotService.createSnapshot({
    sourceUri: this.model.backingDocument.uri,
    owner: { kind: "pinDocument", label: "Pinned Results" },
    scope: "resultSet",
    resultSetIds: [resultSetId],
    includeMessages: true,
    reason: "User pinned result set from Query Studio",
});
```

### ExecutionHost Snapshot Hook

`ExecutionHost` should expose a narrow method for snapshot creation:

```ts
export interface LiveResultSnapshotSource {
    sourceUri: string;
    runId: string;
    title: string;
    store: RetainableRowStore;
    resultSets: QsResultSetSummary[];
    messages: QsMessageRow[];
    queryText?: string;
    database?: string;
    server?: string;
}

getSnapshotSource(): LiveResultSnapshotSource | undefined;
```

The snapshot service validates result-set ids, completion state, and size limits before acquiring a store lease.

### Snapshot Row Fetch

```ts
export interface SnapshotGetRowsParams {
    snapshotId: string;
    resultSetId: string;
    start: number;
    count: number;
    owner?: string;
}
```

This should return the same `QsCellWindow` shape as live `qs/getRows` so the UI can reuse existing code.

## Diagnostics and Journal Requirements

The feature should add rich diagnostics without logging cell values.

Minimum span/event types:

- `queryStudio.snapshot.create.begin`
- `queryStudio.snapshot.create.end`
- `queryStudio.snapshot.acquire`
- `queryStudio.snapshot.release`
- `queryStudio.snapshot.dispose`
- `queryStudio.snapshot.rows.windowFetch.begin`
- `queryStudio.snapshot.rows.windowFetch.end`
- `queryStudio.pin.open`
- `queryStudio.pin.close`
- `queryStudio.aiResultsTool.invoke.begin`
- `queryStudio.aiResultsTool.invoke.end`
- `queryStudio.aiResultsTool.confirmation`

Fields:

- snapshot id
- lease id
- owner kind
- source uri hash, not full path in low verbosity
- source title
- result-set count
- requested row count
- returned row count
- approximate bytes returned
- spill/cache hit info when available
- duration
- failure reason

Never log:

- row values
- full cell text
- raw XML/JSON/blob content
- full SQL text unless explicit full diagnostics mode already allows it

At full diagnostic verbosity, it is acceptable to log query text digests, short SQL previews, column names, type names, and result shape.

## Performance Design

### Avoid Full Copies

Snapshot creation should be O(number of result sets) plus metadata copying. It should not iterate every row. The retained store reference points at the existing pages and spill file.

### Keep Window Fetch Bounded

Pinned documents and AI tools should use the same windowing pattern as the live grid:

- fetch small visible windows
- materialize spilled pages only when needed
- keep sort/filter thresholds consistent with the live grid
- avoid building all rows in memory for AI

### Large Result Sets

For large result sets, AI should usually operate on:

- schema
- row counts
- sample rows
- optional summary statistics computed by extension/STSv2
- explicit user-approved exports

Do not let a chat request accidentally materialize millions of rows into a tool response.

### Memory Pressure and TTL

The snapshot service needs retention policy:

- Pinned documents keep snapshots until closed.
- AI snapshots have a TTL unless pinned.
- A max retained snapshot byte budget should be enforced.
- If memory pressure occurs, unpinned expired snapshots should be disposed first.
- If all snapshots are leased, show a clear error instead of deleting active data.

Initial defaults:

- AI TTL: 30 minutes
- Max unpinned snapshots: 10
- Max retained bytes: use a conservative extension setting or current Query Studio spill budget

## STS2 and Data Plane Considerations

The first implementation should keep snapshots in the extension host because that is where Query Studio results already live. STS2 changes are not required for the core feature.

Possible future STS2 improvements:

- stable result handle returned by STS2 query execution
- server-side result retention leases
- server-side sampling/statistics over retained results
- cancellation behavior when a max row limit is hit
- binary/blob streaming APIs for huge cells
- explicit "query result snapshot" protocol messages

Do not block the UI/AI feature on these. Start with extension-host snapshots, then move retention deeper only if perf evidence shows extension-host spill/cache is the bottleneck.

## Security and Privacy

This feature crosses an important boundary: data visible in the grid becomes available to AI. Treat raw result rows as sensitive user data.

Requirements:

- Raw row access requires explicit user confirmation.
- The confirmation must identify the source and bounds.
- Tool responses must be bounded and truncated.
- Diagnostics must not record row values.
- Snapshot ids should be unguessable.
- Snapshot handles should not grant access outside the current extension host session.
- Pinned documents should not persist data to disk beyond existing RowStore spill mechanics.
- Spill cleanup must be reliable when the final lease is released.
- Data access should respect workspace trust and any future enterprise AI disable settings.

## Testing Plan

### Unit Tests

Add deep unit tests for snapshot lifetime:

- snapshot survives query rerun
- snapshot survives live Query Studio document close
- store is deleted after final lease release
- multiple snapshots over same store share physical data
- releasing one lease does not break another lease
- completed-only snapshot rejects incomplete result sets
- row windows from snapshot match live `RowStore.getRows`
- snapshot metadata preserves result summaries and column metadata
- snapshots do not copy all rows at creation time
- TTL cleanup only deletes unleased snapshots

### Controller Tests

- `qs/pinResultSet` creates a snapshot and opens pinned document
- invalid result-set id returns clear error
- pin-all skips or rejects incomplete result sets based on selected policy
- `QsUpdateGridSelectionRequest` updates current result context
- export from pinned result uses snapshot rows, not live rows
- open XML/JSON cell from pinned result uses snapshot rows

### AI Tool Tests

- metadata operations do not require row access
- row access requires confirmation
- `get_rows` enforces row/cell/byte bounds
- tool cannot read a snapshot without a valid lease or owned handle
- released snapshot handle cannot fetch rows
- diagnostics include counts and durations but no row values

### UI Tests

E2E is useful but not first priority. Targeted webview/component tests should verify:

- pin buttons appear only when results exist
- pinned document renders the same rows after the source query reruns
- pinned document closes and releases its lease
- copy/export commands work in pinned documents
- large results continue to lazy-mount grids

## Implementation Plan

### Phase 1: Snapshot Foundation

- Add snapshot types and `QueryResultSnapshotService`.
- Add a retainable wrapper around `RowStore`.
- Change `ExecutionHost` rerun/dispose to release the live owner instead of always deleting the store.
- Add `ExecutionHost.getSnapshotSource()`.
- Add diagnostics for create/acquire/release/dispose.
- Add unit tests for lifetime and row-window equivalence.

### Phase 2: Pin Result Documents

- Add webview request types for pin result set and pin all results.
- Add pin UI to `GridCaption` and result-pane header overflow.
- Add pinned result document/panel provider.
- Reuse the existing result grid components with a snapshot-backed data source.
- Support copy, open-cell, export, and switch-to-text.
- Add tests for rerun/close stability.

### Phase 3: Result Context Tracking

- Implement `QsUpdateGridSelectionRequest`.
- Track active result set, row, column, and selection shape in `QueryStudioController`.
- Expose active result context to snapshot service and `@query`.
- Add diagnostics for context changes at verbose/full levels only.

### Phase 4: Language Model Tool

- Add `mssql_query_results` contribution with `toolReferenceName: "query_results"`.
- Implement list/describe/snapshot/sample/get-rows/release operations.
- Add confirmation for raw row access.
- Add strict bounds and tests.
- Register the tool in `MainController.registerLanguageModelTools()`.

### Phase 5: `@query` Participant

- Add `mssql.query` chat participant with user-facing name `query`.
- Implement `/list`, `/summarize`, `/profile`, `/python`, `/report`, and `/pin`.
- Keep the handler independent of `mssql.agent`.
- Use the same snapshot service and tool semantics.

### Phase 6: Inline Intent Integration

- Extend Query Studio inline completion context with result metadata only.
- Add intent prompts that steer users toward `@query` or result commands when row data is required.
- Do not send raw rows through automatic inline completion.

### Phase 7: Perf and STS2 Expansion

- Measure large snapshots, spill behavior, row-window fetch latency, and AI sample cost.
- Add result statistics/sampling helpers if needed.
- Decide whether STS2 should own server-side retained result handles for very large data.

## Open Questions

1. Should the pinned result document show captured Messages, or stay result-grid only for the first phase?
2. Should "Pin all results" include execution plan result sets by default, or should plans remain separate tabs/actions?
3. What should the default AI snapshot TTL and retained byte budget be?
4. Should AI tools be allowed to create snapshots from inactive Query Studio documents, or only the active editor?
5. Should `@query /python` export a temp CSV/JSON file for local script execution, or generate a script that connects back to SQL and reruns the query?
6. Should snapshot ids be visible/copyable for debugging, or only internal?
7. Do enterprise settings need a separate "allow AI access to result rows" gate?

## Recommendation

Build this as a Query Studio result snapshot feature first, not as an AI feature first.

The critical architecture is lease-based, immutable snapshots over the current `RowStore` data. Once that exists, "Pin these results," `@query`, and language model tools all become different consumers of the same stable result contract. This also keeps query rerun behavior clean: the live editor always gets fresh results, while retained snapshots stay available until their owners release them.

The first shippable slice should be:

1. lease-aware result stores
2. snapshot service
3. pin result set/all results to a temporary pinned result document
4. deep unit tests and diagnostics

After that, add `mssql_query_results` as a bounded, confirmation-backed tool. Then layer `@query` and inline intent support on top.
