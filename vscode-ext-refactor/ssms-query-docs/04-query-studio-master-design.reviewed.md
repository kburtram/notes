# Query Studio — Master Technical Design, reviewed v2
## An SSMS-parity composite query editor for vscode-mssql, built on STS2 and deep observability

**Status:** proposed umbrella design, reviewed and tightened for implementation planning.  
**Codename:** Query Studio. Freeze or rename before M1 to avoid identifier churn.  
**Primary implementation target:** vscode-mssql extension host + custom webview document editor.  
**Data plane:** `03-sts2-client-adapter-design.reviewed.md`.  
**Metadata:** `02-metadata-service-design.reviewed.md`.  
**UX contract:** `01-query-studio-ux-brief-claude-design.reviewed.md`.

---

## 0. Review upgrades folded into this v2 master design

The first master design was strong and unusually implementation-ready. The reviewed version keeps the architecture and changes several decisions that would otherwise cause pain during coding:

1. **One backing SQL document URI cannot safely own multiple divergent language-service connections.** v1 now uses a document-scoped `QueryStudioDocumentModel` and shared session binding per URI. Multiple visible panels for the same URI attach to the same connection/results unless the user explicitly duplicates the document.
2. **The data-plane abstraction is broadened.** Query Studio imports the SQL Data Plane domain API, not STS2-specific types. STS2 JSON-RPC is the first binding, not the product-facing contract.
3. **Text synchronization is treated as a performance-critical subsystem.** Workspace edits per keystroke are allowed only through a coalesced, versioned, hash-checked protocol with IME/multicursor tests and a resync safety valve.
4. **Metadata hydration is nonblocking by default.** Query Studio opens a dedicated background metadata session when possible, and never lets a digest poll sit between the user and F5.
5. **Plan handling is made safer.** Plan result-set heuristics are acceptable only as fallback until the backend provides plan metadata.
6. **RowStore privacy and durability are explicit.** Spill files contain user data. Their lifecycle, location, deletion, limits, and export exclusion are binding design constraints.
7. **Execution and status states distinguish complete, partial, corrupt, canceled, failed, and connection-lost results.** No partial grid is allowed to masquerade as a successful result.
8. **Observability is not decorative.** Query Studio is the feature that demonstrates end-to-end markers, replay descriptors, debug-console waterfalls, and perftest scenarios across editor, adapter, metadata, STS2, and grid.
9. **Completions port is integrated but not tangled.** One extension-host engine serves native and Query Studio editors; schema context comes from MetadataService; the Monaco bridge is a surface adapter.
10. **Agent-facing sequencing is stricter.** Grid extraction, adapter conformance, text sync, RowStore, and privacy canaries each have gates before feature layering continues.

---

## 1. What we are building

Query Studio is a VS Code **custom text editor** for `.sql` documents that gives users an SSMS-parity query workflow inside a single editor tab:

- embedded Monaco SQL editor;
- embedded toolbar;
- connection and database controls;
- execution/cancel/parse/plan commands;
- embedded Results / Messages / Execution Plan tabs;
- reused and modernized result grid;
- per-document connection-tinted status bar;
- AI inline completions through the ported completions engine;
- metadata-backed schema context;
- observability, capture, replay, and perftest hooks from the first slice.

The purpose is not to build a shiny webview around the old query runner. The purpose is to make Query Studio the first serious production consumer of the STS2-based data plane and the deep observability stack.

---

## 2. SSMS parity scope

| Capability | v1 target | Notes |
|---|---:|---|
| Connect / disconnect / change connection | ✅ | Existing connection UI profile selection, STS2 data plane open. |
| Per-document connection title/status | ✅ | Filename + login/SPID; status bar connection tint. |
| Database dropdown and script-internal `USE` tracking | ✅ | ServerCatalog + Messages/db context signals. |
| Execute selection/document, F5/Ctrl+E | ✅ | Selection offset used for error line mapping. |
| `GO` / `GO n` batch splitting | ✅ | Shared lexer, comment/string aware by default. |
| Cancel with partial result truth | ✅ | Partial rows retained but marked incomplete. |
| Results grid, multiple result sets, NULL styling, copy, selection summary | ✅ | Shared grid extraction over Query Studio data source. |
| Results-to-text | ✅ | Same RowStore data, no re-execute. |
| Messages with rows affected, PRINT/RAISERROR, clickable errors | ✅ | Requires STS2 verbatim client message contract. |
| Estimated and actual execution plans | ✅ | SET orchestration + shared plan component; heuristics until structured plan metadata. |
| Save results as CSV/JSON/Markdown | ✅ | Stream from RowStore. |
| IntelliSense via existing STS v1 LSP | ✅ | Shadow language-service connection per document model. |
| AI inline completions | ✅ | Ported engine, MetadataService schema context, Monaco bridge. |
| Uncommitted transaction warning | ✅ v1.5 cheap | `@@TRANCOUNT` guard on close/disconnect. |
| Observability markers, replay descriptors, perftest scenarios | ✅ | Design showcase. |
| SQLCMD mode | ❌ deferred | Disabled toolbar item with tooltip. |
| Debugger, Client Statistics, Spatial Results, multi-server query | ❌ deferred | Leave extensible tab model. |
| Results to file during execution | ❌ deferred | Save-after-execution v1. |
| VS Code web mode | ❌ architecture-ready | No v1 release commitment. |

---

## 3. Architecture overview

```text
VS Code editor group
┌───────────────────────────────────────────────────────────────────────┐
│ Query Studio custom text editor webview                                │
│ React shell · Monaco · toolbar · splitter · results tabs · status bar   │
│ shared results grid · shared execution plan view · completion bridge    │
└───────────────▲────────────────────────────▲──────────────────────────┘
        QsSync text protocol          Qs RPC/state/hot paths
┌───────────────┴────────────────────────────┴──────────────────────────┐
│ QueryStudioEditorProvider                                              │
│ QueryStudioDocumentRegistry                                            │
│  one QueryStudioDocumentModel per TextDocument URI                      │
│  N panels attach to one model unless user duplicates                    │
│ QueryStudioController per panel: webview RPC/view state                 │
│ DocumentSessionBinding · ExecutionOrchestrator · RowStore · MessageLog │
│ PlanCollector · ResultSerializer · ReplayRecorder                      │
└──────▲──────────────┬────────────────────────────┬────────────────────┘
       │              │                            │
       │       MetadataService              CompletionsEngine
       │       server/db catalogs           native + Query Studio surfaces
       │
┌──────┴────────────────────────────────────────────────────────────────┐
│ SQL Data Plane Adapter                                                  │
│ domain API: ISqlSession.execute + event sink + capabilities             │
│ STS2 JSON-RPC binding today, HTTP/hosted bindings later                 │
└──────────────────────────────▲────────────────────────────────────────┘
                               │
                     sqltoolsservice STS2 lane
                     legacy STS v1 lane remains for LSP/OE/designers
```

Diag substrate instruments every layer. A single user execution should produce a waterfall that connects:

- toolbar/webview command;
- controller RPC;
- execution orchestrator;
- SQL data-plane adapter;
- STS2 wire/request spans;
- metadata generation used;
- row streaming and grid rendering;
- resultsRendered marker.

---

## 4. Core design decisions

### 4.1 Use `CustomTextEditorProvider`

Rationale:

- The backing document is a real VS Code `TextDocument`.
- Save, dirty, hot-exit, backup, and file associations remain VS Code-owned.
- Existing language providers can observe the document.
- Users can reopen with the classic editor.

Caveat: a webview's Monaco model and VS Code's TextDocument are separate. The sync protocol is a first-class subsystem, not glue code.

### 4.2 One document model per URI in v1

The first design allowed independent sessions/results for multiple Query Studio panels showing the same URI. That conflicts with:

- v1 LanguageClient connection keyed by document URI;
- existing URI-keyed status hooks;
- diagnostics keyed by owner URI digest;
- user confusion when two views of one file point to different databases.

Revised policy:

- `QueryStudioDocumentRegistry` owns one `QueryStudioDocumentModel` per `TextDocument.uri`.
- Multiple Query Studio webview panels for the same URI attach to the same document model and therefore share connection/session/results.
- Panel-specific state remains local: split ratio, active tab, scroll positions, selected grid cell.
- If user wants the same SQL text connected to another server/database, command `MSSQL: Query Studio: Duplicate as New Query` creates an untitled copy with a new URI/model.

This is less magical and far less likely to summon the URI goblin.

### 4.3 STS2 data plane only for execution

Query Studio never silently falls back to v1 execution. If the SQL Data Plane adapter is unavailable:

- show error with actions `Retry` and `Open in classic editor`;
- leave existing results intact;
- do not route Query Studio execution through the old query runner.

The classic editor remains the fallback product experience.

### 4.4 v1 LSP bridge is a temporary dual-plane design

Query Studio v1 uses:

- STS2/SQL Data Plane for connection/query execution;
- STS v1 LanguageClient for IntelliSense and diagnostics via a shadow language-service connection.

The shadow connection is per document model, not per panel. It is removed when the metadata-native LSP ships.

### 4.5 Query Studio owns result rows

STS2 streams results and does not provide random-access result caching. Therefore Query Studio owns RowStore, memory/spill limits, save/export, and grid window fetch.

### 4.6 Metadata is nonblocking

Metadata hydration starts after connection, but Connect is ready as soon as the data-plane session is open. Metadata readiness improves database list/completions/OE fast paths progressively. User execution does not wait for full metadata unless a specific command needs it.

---

## 5. Module inventory

Paths are relative to `extensions/mssql/`.

| Path | Responsibility |
|---|---|
| `src/queryStudio/queryStudioEditorProvider.ts` | `CustomTextEditorProvider` registration and webview panel lifecycle. |
| `src/queryStudio/queryStudioDocumentRegistry.ts` | URI → shared `QueryStudioDocumentModel`, refcounts, multi-panel policy. |
| `src/queryStudio/queryStudioDocumentModel.ts` | Shared text/session/results state for one TextDocument URI. |
| `src/queryStudio/queryStudioController.ts` | Per-panel RPC handlers, view state, webview messaging. |
| `src/queryStudio/documentSessionBinding.ts` | SQL data-plane session lifecycle, shadow v1 connection, status interop, db tracking. |
| `src/queryStudio/textSync.ts` | Host ⇄ Monaco sync state machine, versions, hashes, undo forwarding. |
| `src/queryStudio/executionOrchestrator.ts` | Selection resolution, batch loop, SET wrappers, cancel, terminal aggregation. |
| `src/sql/lexerLite.ts` | Shared lexer for GO splitter and metadata DDL sniffer. |
| `src/sql/batchSplitter.ts` | SQL batch splitting, GO n, source offsets. |
| `src/queryStudio/rowStore.ts` | Result storage, page index, memory LRU, window serving. |
| `src/queryStudio/rowStoreSpill.ts` | Spill file writer/reader, cleanup, limits. |
| `src/queryStudio/messageLog.ts` | Execution messages and error navigation metadata. |
| `src/queryStudio/planCollector.ts` | Plan result detection/storage. |
| `src/queryStudio/resultSerializer.ts` | CSV/JSON/Markdown/text export from RowStore. |
| `src/queryStudio/replayRecorder.ts` / `replayRunner.ts` | Query run descriptors and replay. |
| `src/sharedInterfaces/queryStudio.ts` | Versioned `Qs*` RPC contracts. |
| `src/webviews/pages/QueryStudio/` | React app: shell, toolbar, Monaco host, results host, status bar, state. |
| `src/webviews/shared/resultsGrid/` | Extracted shared grid components and data-source interface. |
| `src/webviews/shared/executionPlan/` | Extracted shared plan renderer. |
| `src/services/sqlDataPlane/**` | Reviewed domain API and adapter. |
| `src/services/sts2/**` | STS2 binding implementation. |
| `src/metadata/**` | MetadataService. |
| `src/completions/**` | Ported completions engine and providers. |

---

## 6. Custom editor registration and commands

`package.json`:

```jsonc
{
  "contributes": {
    "customEditors": [
      {
        "viewType": "mssql.queryStudio",
        "displayName": "Query Studio",
        "selector": [{ "filenamePattern": "*.sql" }],
        "priority": "option"
      }
    ]
  }
}
```

Commands:

- `mssql.queryStudio.new` — create untitled SQL document and open with Query Studio.
- `mssql.queryStudio.openActive` — reopen active `.sql` document in Query Studio.
- `mssql.queryStudio.openInClassicEditor` — reopen with default editor.
- `mssql.queryStudio.duplicateAsNewQuery` — copy current text to a new untitled Query Studio document.
- `mssql.queryStudio.reconnect` — reconnect current document model with last-used profile.
- `mssql.queryStudio.showStatus` — safe status dump.

Settings:

- `mssql.queryStudio.enabled`: false preview master gate.
- `mssql.queryStudio.defaultForSql`: false.

Webview options:

- `enableScripts: true`;
- `retainContextWhenHidden: true` for v1, with memory telemetry;
- local resource roots per existing webview conventions;
- CSP strict, no remote scripts except allowed local bundles.

---

## 7. Document and panel lifecycle

### 7.1 Resolve flow

1. `resolveCustomTextEditor(document, panel)`.
2. Registry `getOrCreateModel(document)`.
3. Create per-panel controller.
4. Controller attaches to model events.
5. Webview HTML loads Query Studio app.
6. Host sends `QsSyncInit` and `QsState`.
7. Restore panel-local UI preferences.
8. If model has active results/session, panel renders them; otherwise editor-only.

No automatic reconnect on reopen in v1. Last-used profile fingerprint may preselect Connect quick pick, but secrets are not stored in Query Studio state.

### 7.2 Untitled and Save As

- `mssql.queryStudio.new` opens untitled SQL document with our view type.
- On Save As, VS Code may re-resolve the custom editor. The model must be rebind-safe.
- Registry listens for document URI changes if available; otherwise dispose old model and create new model on re-resolve.
- Any shadow v1 ownerUri/status interop is re-keyed.

M0 must include a small exploratory test documenting actual VS Code behavior for untitled custom text editors.

### 7.3 Disposal

When last panel detaches from a model:

- cancel active query if running, bounded and non-blocking;
- ask transaction guard on explicit close/disconnect path, not extension shutdown;
- close data-plane session;
- release metadata handles;
- tear down shadow v1 connection;
- dispose RowStore and spill files;
- unregister status interop;
- flush pending diagnostics/replay descriptors.

Extension deactivate sweeps all models and orphan spill directories.

---

## 8. Text synchronization protocol

The backing `TextDocument` owns persistence and undo. Monaco owns interactive editing. The two converge through a versioned sync protocol.

### 8.1 Message types

Host → webview:

- `QsSyncInit { text, hostVersion, textHash }`;
- `QsSyncRemote { fromHostVersion, toHostVersion, edits, textHash, reason }`;
- `QsSyncResync { text, hostVersion, textHash, reason }`;
- `QsRevealPosition { line, column, flash }`.

Webview → host:

- `QsSyncEdits { baseHostVersion, editGroupId, edits, selectionBefore, selectionAfter, textHashAfter }`;
- `QsSyncUndoRequest { redo }`;
- `QsSyncSaveRequest`;
- `QsSyncResyncRequest { webviewVersion, textHash }`.

### 8.2 Coalescing

Do not send one host workspace edit for every low-level Monaco delta if Monaco coalesces a user operation into multiple deltas.

Policy:

- group deltas within the same Monaco `onDidChangeModelContent` event;
- coalesce microtask/animation-frame bursts up to 16 ms unless it would hurt LSP freshness;
- flush immediately before execute, completion request, save, or focus loss;
- IME composition should not emit broken intermediate edits to the host if avoidable.

Latency target: webview keystroke to host TextDocument update p95 < 20 ms local for normal typing.

### 8.3 Echo suppression and divergence

- Host increments `hostVersion` on every TextDocument change.
- Webview edit carries `baseHostVersion` and `editGroupId`.
- Host records expected echo mapping.
- Host → webview remote changes matching expected echo are acknowledged and not re-applied.
- Both sides keep rolling xxhash per version.
- Hash mismatch triggers full resync and `queryStudio.sync.resync` diagnostic.

Resync counter should be zero in dogfood. It exists because “never diverges” is a spell, not a test.

### 8.4 Undo/redo

Monaco Ctrl+Z/Ctrl+Y are overridden to call host undo/redo commands. The resulting TextDocument changes flow back via sync. Monaco's internal undo stack should not be used for document edits.

Tests must cover:

- single cursor typing;
- multi-cursor edit;
- paste large text;
- comment/uncomment;
- format-on-save/external change;
- undo after host edit;
- IME composition;
- CRLF/LF preservation;
- save/revert.

---

## 9. Webview app and RPC surface

Use the Debug Console webview pattern: versioned shared interfaces, controller instrumentation, coarse state pushes plus hot-path RPCs.

### 9.1 Coarse state

`QsState`, pushed at max 10/s:

```ts
interface QsState {
  schemaVersion: number;
  connection: QsConnectionState;
  execution: QsExecutionState;
  results: QsResultsState;
  editor: { hostVersion: number; language: "sql"; issues: number };
  metadata: { readiness: string; generation?: number; mode?: string };
  completions: { enabled: boolean; degraded?: string };
  toggles: { actualPlan: boolean; viewMode: "grid" | "text" };
  statusMessage: { kind: "ready" | "info" | "success" | "warning" | "error"; text: string };
  capabilities: Record<string, boolean>;
}
```

### 9.2 Hot-path RPC

Webview → host:

- `QsExecute`;
- `QsCancel`;
- `QsConnect`, `QsDisconnect`, `QsChangeConnection`, `QsReconnect`;
- `QsSetDatabase`;
- `QsGetRows`;
- `QsGetMessages`;
- `QsSaveResults`;
- `QsGetPlanXml`;
- `QsNavigateToLine`;
- `QsSetViewMode`;
- `QsUpdateGridSelection`;
- `QsInlineRequest`, `QsInlineCancel`, `QsInlineAccepted`;
- `QsLspCompletion`, `QsLspHover`, `QsLspSignatureHelp`, `QsLspDefinition`, `QsLspResolveCompletion`;
- `QsGetDiagnosticsSummary`.

Host → webview notifications:

- `QsStateChanged`;
- `QsResultSetStarted`, `QsRowsAppended`, `QsResultSetEnded`, `QsRowsInvalidated`;
- `QsMessagesAppended`;
- `QsExecutionPhaseChanged`;
- `QsPlanAvailable`;
- `QsDiagnosticsChanged`;
- `QsRevealPosition`;
- `QsToast`.

Row data is never part of coarse state. It flows through `QsGetRows` windows.

---

## 10. Monaco integration

### 10.1 Bundling and theme

- Bundle `monaco-editor` into Query Studio webview chunk; include SQL contribution only.
- Target chunk size tracked; if too large, split lazy loaded editor chunk.
- Theme bridge reads `--vscode-*` variables and calls `monaco.editor.defineTheme`.
- Exact user TextMate token fidelity is post-v1; coherent VS Code theme is v1.
- Font settings follow `editor.fontFamily`, `editor.fontSize`, `editor.lineHeight` where possible.

### 10.2 Keybindings

Inside webview:

| Keys | Action |
|---|---|
| F5, Ctrl+E | Execute |
| Alt+B, Alt+Break where capturable | Cancel |
| Ctrl+R | Toggle results |
| Ctrl+L | Estimated plan |
| Ctrl+M | Toggle actual plan |
| Ctrl+S | Save |
| Ctrl+Z/Y | Host undo/redo |
| Ctrl+K Ctrl+C/U | Monaco comment/uncomment |
| F6 | Focus cycle |

Also register package-level keybindings with `when: activeCustomEditorId == 'mssql.queryStudio'` so commands work when focus is in grid/toolbar.

### 10.3 LSP bridge

Because the backing TextDocument is real, host can call VS Code provider commands:

- `vscode.executeCompletionItemProvider`;
- `vscode.executeHoverProvider`;
- `vscode.executeSignatureHelpProvider`;
- `vscode.executeDefinitionProvider`.

The bridge serializes results to Monaco provider shapes. Diagnostics flow from `vscode.languages.onDidChangeDiagnostics` filtered to the document URI.

Latency budget: bridge overhead ≤ 15 ms over native provider call.

### 10.4 Shadow v1 connection

Policy:

- One shadow v1 connection per `QueryStudioDocumentModel` URI when STS2 session opens.
- It uses the same profile/database and exists only for language service schema awareness.
- It is lazy and nonblocking; failure downgrades IntelliSense but not Query Studio execution.
- It retargets on database change.
- It closes with the model.

If two panels attach to the same URI, they share the same shadow connection. Divergent sessions require duplicate document.

---

## 11. Connection lifecycle

### 11.1 Profile selection

Reuse existing connection UI, but factor a seam:

```ts
selectConnectionProfile(opts): Promise<IConnectionProfile | undefined>
```

This should select and return a profile without opening a v1 query connection. Classic paths keep their combined select+connect behavior.

### 11.2 Open

1. User selects profile.
2. Map to `SqlConnectionProfileRef` with secret/token providers.
3. `sqlDataPlane.openSession({ applicationName: "vscode-mssql-querystudio" })`.
4. On success:
   - update status/title;
   - start shadow v1 connection;
   - acquire MetadataService ServerCatalog and DatabaseCatalog;
   - run SPID probe only if open response lacked SPID;
   - emit `mssql.queryStudio.connect.ready`.

Connect is ready when the data-plane session is open. Metadata may still be loading.

### 11.3 States

```text
disconnected
  -> connecting
  -> connected
  -> executing
  -> connected
  -> disconnecting
  -> disconnected
  -> lost
```

`lost` is not `disconnected`: results remain visible, reconnect is offered, active query completes as connectionLost.

### 11.4 Database tracking

Sources of truth, in order:

1. Structured `onDidChangeDatabase` from backend if available.
2. SQL Server context-change messages from the executing session.
3. Query Studio-controlled `USE [db]` combo command success.
4. Background `SELECT DB_NAME()` probe only when a lexed `USE` occurred but no structured/message signal arrived.

Database change fans out to:

- status bar;
- database combo;
- MetadataService catalog reacquire;
- shadow v1 retarget;
- replay descriptor config;
- messages log.

Database names must be bracket-escaped for combo-driven `USE`.

### 11.5 Disconnect and transaction guard

Explicit Disconnect or close with live session:

1. If executing, confirm cancel/disconnect.
2. Background `SELECT @@TRANCOUNT` if session still usable.
3. If >0, modal: Commit / Rollback / Cancel.
4. Execute chosen `COMMIT` or `ROLLBACK` safely.
5. Close session.
6. Release metadata, shadow LSP, RowStore.

If transaction probe fails, warn and let user choose forced disconnect.

### 11.6 STS2 unavailable/lost

At connect time:

- show error with `Retry` and `Open in classic editor`.

Mid-session:

- state `lost`;
- active query terminal `connectionLost`;
- completed results remain visible;
- partial result sets get banner;
- status and toolbar show Reconnect.

No silent v1 execution fallback.

---

## 12. Execution pipeline

### 12.1 Entry

`QsExecute` resolves:

- scope: selection or whole document;
- text and source start line/column;
- current database;
- actual/estimated plan toggles;
- stop-on-error setting;
- current catalog generation if any.

Then `ExecutionOrchestrator.run()` owns the lifecycle.

### 12.2 Run shape

```text
submit marker
open root action
flush pending text sync
split batches
prepare plan/parse SET wrapper if needed
for each batch/repeat:
  execute through ISqlSession with interactive priority
  sink streams to RowStore, MessageLog, PlanCollector
  await terminal
  continue or stop based on policy
finally:
  restore SET state wrappers
  finalize RowStore/messages/status
  notify MetadataService of executed batches
  record replay descriptor if capture armed
  emit execute.end
webview emits resultsRendered after final grid paint
```

### 12.3 Batch splitter

Rules:

- Separator is a line containing only `GO`, case-insensitive, optional integer count, optional trailing `--` comment.
- `GO 5` repeats previous batch five times.
- `GO` inside comments/strings/bracketed identifiers does not split by default.
- Setting `mssql.queryStudio.strictSqlcmdGo` can emulate stricter line-based behavior later.
- Empty batches skipped.
- Output includes `startLine`, `startColumn`, `lineCount`, `repeatOrdinal`.

The lexer is shared with MetadataService DDL sniffing.

### 12.4 Error and batch policy

Default: continue on error, matching SSMS batch behavior. Run summary can be `completedWithErrors`.

Stop conditions:

- user cancel;
- connection lost;
- severity/terminal error indicating session death;
- `mssql.queryStudio.stopOnError` true.

Error line mapping:

```text
documentLine = selectionStartLine + batch.startLine + serverLine - 1
```

Guard against line missing/zero; navigate to batch start when uncertain.

### 12.5 Parse command

Prototype/product v1 can use `SET PARSEONLY ON` or a backend parse capability if STS2 adds one.

Rules:

- Always restore in finally.
- Do not leave session in parse-only state.
- Render messages, no grids.
- If backend/service provides a safer parse endpoint later, replace SET wrapper.

### 12.6 Execution plans

Actual plan:

- Prefer backend plan event or result metadata when available.
- Fallback: wrap execution with `SET STATISTICS XML ON`, detect canonical showplan XML result set, route to PlanCollector, then `OFF` in finally.
- False-positive risk exists if user query returns similar XML. Diagnostics should mark `planDetection: heuristic`.

Estimated plan:

- Use `SET SHOWPLAN_XML ON` wrapper.
- Execute user batches, which return plans and no data modifications.
- Restore `OFF` in finally even on error.
- Results tab may be absent; Plan tab active.

### 12.7 Cancel

- `QsCancel` calls `QueryHandle.cancel()` on active handle.
- UI enters `cancelRequested` until query terminal arrives.
- Partial result sets remain but are marked `truncatedReason: "cancelled"`.
- If cancel ack times out but terminal later arrives, status should say cancellation uncertain/connection lost based on adapter outcome.

---

## 13. Results subsystem

### 13.1 RowStore

Per execution, per result set:

- append pages from sink;
- build rowOffset index;
- serve random windows to grid;
- track completion/truncation/corruption;
- expose row count growth events.

### 13.2 Memory and spill

Settings:

- `mssql.queryStudio.results.maxMemoryMB`: 64;
- `mssql.queryStudio.results.spillEnabled`: true;
- `mssql.queryStudio.results.maxSpillMB`: 2048;
- `mssql.queryStudio.results.maxRowsPerResultSet`: 5,000,000.

Spill files:

```text
<globalStorage>/querystudio-spill/<runId>/<resultSetId>.pages
```

They contain result data. Binding rules:

- create with restrictive permissions where platform supports it;
- delete on new execution, editor close, extension deactivate sweep;
- exclude from session-diag/perftest export bundles by default;
- status command reports spill bytes;
- user setting can disable spill, causing honest backpressure/paused state.

Consider binary or compact columnar frames after v1. JSON frames are simpler but may be costly for very large results; track bytes/row and decode p95.

### 13.3 Window serving

`QsGetRows { resultSetId, start, count }`:

- locate pages by rowOffset;
- read/decode from memory LRU or spill;
- return cell window with metadata and null bitmap/typed values;
- target p95 < 8 ms for 100-row window from warm spill.

### 13.4 Shared grid extraction

Three-step extraction:

1. Introduce `IGridDataSource` inside existing QueryResult page, backed by v1 GetRows. Existing tests and `query-10k-results` perftest remain green.
2. Move decoupled components to `src/webviews/shared/resultsGrid/` and re-export for classic page.
3. Query Studio implements `IGridDataSource` over `QsGetRows` and streaming row-count events.

Data source:

```ts
export interface IGridDataSource {
  columns: GridColumn[];
  rowCount: number;
  complete: boolean;
  truncatedReason?: string;
  corrupt?: boolean;
  getRows(start: number, count: number): Promise<CellWindow>;
  onDidChange: Event<{ rowCount: number; complete: boolean; reason?: string }>;
}
```

Regression rule: any grid extraction PR that moves `query-10k-results` official timing materially is a stop-ship until understood.

### 13.5 Messages

`MessageLog` stores:

```ts
interface QueryMessageEntry {
  batchIndex: number;
  repeatOrdinal?: number;
  kind: "info" | "warning" | "error";
  text: string;
  server?: { number?: number; severity?: number; state?: number; line?: number; procedure?: string };
  epochMs: number;
  navigable?: { line: number; column: number };
}
```

Rows affected:

- prefer structured `rowsAffected`;
- render server messages verbatim when provided;
- synthesize only if no message exists, and tag diagnostics `rowsAffectedSource: summary`.

### 13.6 Execution plan component

Extract existing plan renderer into `shared/executionPlan/` behind `{ planXml: string }` input. Query Studio adds:

- multiple plans rail when >1;
- statement/batch labels;
- heuristic badge if plan detection not structured.

### 13.7 Save and text output

`ResultSerializer` streams from RowStore:

| Format | Rules |
|---|---|
| CSV | RFC 4180, UTF-8, optional BOM. NULL empty or configurable. |
| JSON | Array of objects, typed nulls; huge export streams incrementally. |
| Markdown | Cap at 10k rows with notice. |
| Text | Fixed-width SSMS-style display in UI. |

No re-query for save/export. Completed and truncated sets can be saved with warning metadata.

---

## 14. Metadata integration

On connect:

1. Acquire `ServerCatalogHandle` for database list.
2. Acquire `CatalogHandle` for current DB.
3. Query Studio status shows metadata readiness, but does not block execution.
4. Completion engine uses catalog when columns ready; degrades before that.
5. DDL executed by Query Studio calls `notifyExecutedBatch` after each batch.
6. Database changes reacquire DB catalog.

Query Studio should show subtle metadata status in a tooltip/status popover, not a noisy banner, unless metadata failure affects visible features like completions.

---

## 15. Completions port

### 15.1 Scope

Port from `dev/karlb/completions`:

- engine core;
- intent/continuation trigger logic;
- LM providers/config;
- debug Sessions and Replay tools;
- event schema/analytics;
- VS Code native inline provider.

Replace schema fetch/compaction with `MetadataService.buildSchemaContext`.

### 15.2 Engine placement

Engine stays extension-host-side:

- secrets and LM SDK calls stay out of webview;
- one event stream and debug UI for both surfaces;
- events gain `editorSurface: "classic" | "queryStudio"`.

### 15.3 Query Studio Monaco bridge

Webview registers Monaco inline completion provider and calls host:

```ts
QsInlineRequest {
  requestId,
  docVersion,
  position,
  contextWindow,
  triggerKind
}
```

Host:

- flushes/validates text version;
- cancels stale request;
- runs engine;
- returns inline items + `eventId`;
- records acceptance/partial acceptance via `QsInlineAccepted`.

Bridge overhead target: ≤ 10 ms over native path.

### 15.4 Privacy

Schema context to remote LM is governed by completions settings/policy. Events log catalog generation, cache key, budget, object counts, and degraded state; not prompt text by default unless completions debug capture policy explicitly allows it.

---

## 16. Toolbar and status bar

The visual/interaction contract is owned by doc 01. Product implementation adds:

- connection accent from profile group/color metadata, adding `accentColor` to saved profile schema if needed;
- status segments driven by `QueryStudioDocumentModel`, not per-panel duplicate state;
- grid cell status from active panel selection;
- editor cursor status from active panel editor;
- model-level connection/execution/results status shared across panels;
- SQLCMD toggle disabled with tooltip.

Status bar must distinguish:

- `Query executed successfully.`;
- `Query completed with errors.`;
- `Query was cancelled by user.`;
- `Results incomplete — query cancelled.`;
- `Connection lost.`;
- `Metadata loading/degraded` in tooltip rather than primary segment unless relevant.

---

## 17. Observability, capture, replay, perftest

### 17.1 Marker family

| Marker | Phase | Attrs |
|---|---|---|
| `mssql.queryStudio.open` | begin/end | fromCache, monacoMs |
| `mssql.queryStudio.connect` | begin/ready/end | backend, authKind, encrypted, metadataSession, error |
| `mssql.queryStudio.query.submit` | instant | scope, batchCount, selection |
| `mssql.queryStudio.query.execute` | begin/end | batches, resultSets, rows, errors, canceled, partial, bytes |
| `mssql.queryStudio.query.firstResult` | instant | msFromSubmit |
| `mssql.queryStudio.resultsRendered` | instant | rows, resultSets, partial, fromSpill |
| `mssql.queryStudio.rows.windowFetch` | begin/end | resultSetId, start, count, fromSpill |
| `mssql.queryStudio.cancel` | instant | msToAck, msToTerminal |
| `mssql.queryStudio.sync.applyEdit` | span | chars, editCount, latency |
| `mssql.queryStudio.lsp.bridge` | span | provider, itemCount, latency |
| `mssql.queryStudio.inlineCompletion` | span | surface, accepted, catalogGeneration |

Official user-perceived query metric: submit/execute start to `resultsRendered`, same-process/product timer where possible.

### 17.2 Replay recorder

When capture is armed, record `QsRunRecord`:

- run ID;
- document URI digest;
- profile fingerprint;
- database;
- SET toggles;
- splitter version;
- catalog generation;
- per-batch `RequestDescriptor`s;
- outcomes and row counts;
- adapter correlation IDs;
- grid/render timings.

Default capture stores SQL text digest only. Replayable SQL text requires Debug Console elevated capture, time-bound and local-only.

### 17.3 Replay runner

- Replays descriptors through SQL Data Plane normal API.
- Allows config overrides: connection/database/page hints/plan toggles.
- Tags events with `replayTraceId`, `replayRunId`, `replaySourceEventId`.
- Can generate matrix runs like completions replay.

### 17.4 perftest and self-test scenarios

Add gradually:

| Scenario | Purpose |
|---|---|
| `querystudio-open` | Custom editor open + Monaco ready. |
| `querystudio-open-connect` | Open, connect, status ready. |
| `querystudio-query-10k` | Head-to-head with classic `query-10k-results`. |
| `querystudio-cancel-midstream` | Partial results and terminal state. |
| `querystudio-multi-result` | Stacked result sets. |
| `querystudio-plan-actual` | Plan tab path. |
| `querystudio-lsp-completion-probe` | Monaco LSP bridge. |
| `querystudio-inline-completion-probe` | AI completion bridge. |
| `querystudio-sync-typing` | Text sync latency/resync count. |
| `querystudio-rowstore-spill` | Spill path and window fetch p95. |

Self-test exposes `mssql.perf.queryStudioState` only in PERF_MODE with rowCounts, phase, spill stats, metadata generation, and sync resync count.

---

## 18. Privacy and security

Binding invariants:

- SQL text not in diag by default.
- Result cells not in diag by default.
- Connection strings/secrets/tokens never in diag, replay descriptors, errors, or status.
- Spill files contain result data; treat as sensitive local artifacts.
- Replayable traces with SQL text require elevated capture.
- Schema context to LM is governed by completions privacy policy.
- Database names/object names are metadata; classify consistently.
- Save/export results is an explicit user action.
- Webview CSP prevents remote script injection.
- `USE [db]` and generated SET wrappers escape identifiers and use controlled text.
- No raw stdout or direct STS writes; all service communication through adapter.

Privacy canaries must cover all default stores:

- session diag;
- perf markers;
- replay records;
- RowStore spill exclusion from debug export;
- metadata cache;
- completions debug traces default mode.

---

## 19. Settings inventory

| Setting | Default | Notes |
|---|---:|---|
| `mssql.queryStudio.enabled` | false | Preview gate. |
| `mssql.queryStudio.defaultForSql` | false | Open With default later. |
| `mssql.queryStudio.languageService.shadowConnection` | true | v1 LSP bridge. |
| `mssql.queryStudio.stopOnError` | false | SSMS parity default continue. |
| `mssql.queryStudio.strictSqlcmdGo` | false | Default safer lexer splitter. |
| `mssql.queryStudio.autoSwitchToMessagesOnError` | true | |
| `mssql.queryStudio.results.maxMemoryMB` | 64 | Per document. |
| `mssql.queryStudio.results.spillEnabled` | true | Web mode may force false. |
| `mssql.queryStudio.results.maxSpillMB` | 2048 | Per execution. |
| `mssql.queryStudio.results.maxRowsPerResultSet` | 5000000 | Hard cap. |
| `mssql.queryStudio.results.csv.includeBom` | true | Save CSV. |
| `mssql.queryStudio.replay.enabled` | follows debug capture | No SQL text unless elevated. |

Plus `mssql.sqlDataPlane.*`, `mssql.metadata.*`, and completions settings.

---

## 20. Testing and verification

### 20.1 Unit tests

- Document registry: one model per URI, multi-panel attach/detach.
- Text sync: edits, echo suppression, resync, undo, IME, CRLF, external changes.
- Batch splitter/lexer corpus.
- Execution orchestrator: batch loop, errors, cancel, stopOnError, SET finally.
- PlanCollector heuristics and structured plan path.
- Database tracking from messages and probes.
- RowStore memory/spill/caps/window math/corrupt state.
- ResultSerializer golden outputs.
- MessageLog error line mapping.
- Privacy canaries.

### 20.2 Webview tests

- Toolbar state matrix.
- Status bar segments.
- Grid data source streaming growth.
- Selection/copy/summary.
- Results-to-text.
- Messages navigation.
- Plan tab.
- Keyboard focus map.
- Theme token snapshots.

### 20.3 Integration tests

- Fake backend end-to-end execute to grid.
- STS2 FakeDriver/SQLite live lanes.
- SQL Server engine lane for messages, rows affected, cancel, plans, database context.
- Shadow v1 connection with LSP completions.
- Metadata nonblocking connect.

### 20.4 Perftest gates

Standing non-regression throughout:

- classic `query-10k-results` remains green;
- `debug-console-smoke` remains green.

New Query Studio scenarios start exploratory, graduate after stability.

### 20.5 Standard verification chain

From `extensions/mssql`:

1. typecheck extension and webviews;
2. build;
3. unit suite, known flake documented only;
4. in-proc vitest;
5. harness non-regression pair;
6. STS build/tests when STS or STS2 contract touched.

---

## 21. Milestones

### M0 — Editor shell and sync

Scope:

- provider/registry/model/controller;
- webview shell;
- Monaco embed;
- text sync with undo/resync;
- theme bridge;
- keybindings;
- feature flag;
- open/new/reopen/duplicate commands.

Gate:

- sync suite green;
- 30-minute dogfood resync count zero;
- `queryStudio-open` marker pair emitted;
- multiple panels same URI share model correctly.

### M1 — Data plane connection

Scope:

- SQL Data Plane AD-0..AD-2;
- profile selection seam;
- connect/disconnect;
- status bar and title;
- lost/unavailable handling;
- shadow v1 connection skeleton.

Gate:

- adapter conformance core green;
- connect to Sts2TestDb through STS2;
- no v1 execution fallback path.

### M2 — Execute and results core

Scope:

- splitter;
- orchestrator;
- RowStore memory/spill;
- grid extraction steps 1–3;
- Messages;
- cancel;
- timer;
- multi-result stacking;
- rows affected.

Gate:

- UX scripts 2–6 real;
- classic `query-10k-results` still green;
- exploratory `querystudio-query-10k` runs.

### M3 — SSMS parity band

Scope:

- plans;
- results-to-text;
- save-as;
- selection summary/copy;
- database combo and USE tracking;
- transaction guard;
- LSP bridge;
- keyboard map complete;
- OE “new Query Studio query” command.

Gate:

- parity checklist v1 complete on SQL Server engine lane except documented deferred items.

### M4 — Metadata integration

Scope:

- ServerCatalog for DB combo;
- DatabaseCatalog hydrate/cache/drift;
- status/debug events;
- nonblocking metadata session;
- DDL notify.

Gate:

- metadata cold/warm perf scenarios;
- Query Studio connect unaffected by full hydration.

### M5 — Completions port

Scope:

- completions engine/providers/debug view ported;
- MetadataService projection;
- native-editor parity;
- Monaco bridge;
- replay Sessions surface filter.

Gate:

- golden compaction parity;
- latency/acceptance comparable across classic and Query Studio on replay matrix;
- historical trace files still load.

### M6 — Observability and preview readiness

Scope:

- marker vocabulary registered;
- replay recorder/runner;
- perftest scenarios promoted;
- self-test entries;
- privacy canary suite;
- docs and release notes;
- insiders preview gate.

Gate:

- full verification chain;
- head-to-head report classic vs Query Studio;
- STS2 required contract items closed or explicitly preview-gated.

---

## 22. Risks and open decisions

| Risk / decision | Recommendation |
|---|---|
| STS2 verbatim messages not ready | Treat as parity blocker for preview. Messages tab cannot be fake in product. |
| Dispose/complete contract unsettled | Adapter synthesizer can protect liveness, but preview should wait for server contract decision. |
| Grid extraction regresses classic editor | Extract in steps with classic gate green after each PR. |
| Text sync too slow or unstable | Instrument from M0; coalesce edits; if p95 fails, pause feature layering. |
| Shadow v1 connection doubles connections | Accept for v1, document setting, retire with metadata-native LSP. |
| Multiple panels same URI expectations | Share model in v1; provide duplicate command for divergent sessions. |
| RowStore spill privacy | Make local-data nature explicit; delete aggressively; exclude from bundles. |
| Plan heuristic false positives | Prefer backend plan metadata; show heuristic diagnostic until then. |
| Metadata dedicated sessions in managed environments | Setting fallback; collect connection-count feedback. |
| Web mode | Keep adapter core and serializers web-aware, but do not ship until HTTP backend and metadata LSP are real. |
| Naming | Freeze “Query Studio” or rename before M1. |

---

## 23. Agent operating notes

- Work in vertical slices matching milestones.
- Do not import STS2 wire DTOs outside adapter/binding modules.
- Do not edit legacy STS paths except explicit profile selection/shadow LSP seams.
- No raw SQL text, row data, secrets, or tokens in diag by default.
- PERF_MODE-only commands must not exist outside perf mode.
- Every new marker goes through classification.
- Every visible UI state must have a model state behind it, not hardcoded webview illusion.
- Tests before layering: sync, adapter conformance, grid extraction, RowStore, privacy canaries.
- If repo behavior conflicts with this document, repo wins for the slice; record the deviation and update the doc.

---

## Appendix A — Query Studio RPC sketch

Use `QS_SCHEMA_VERSION` and Debug Console-style request/notification types.

Hot-path row windows should avoid per-cell object bloat when crossing webview boundary. Candidate shape:

```ts
interface CellWindow {
  resultSetId: string;
  start: number;
  rowCount: number;
  columns: GridColumn[];
  values: unknown[][];          // display or typed compact values
  nullBitmap?: string;          // packed bits/base64 for nulls
  typeHints?: string[];
  truncatedBitmap?: string;
}
```

The internal RowStore keeps richer `CellValue`s. The webview payload can be compacted after measuring clone cost.

## Appendix B — SSMS parity checklist

- Execute selection/document.
- F5/Ctrl+E and cancel keybindings.
- GO/GO n.
- Continue-on-error batches.
- Grid NULL styling.
- Multi-result sets.
- Copy/copy headers.
- Save-as.
- Text mode.
- Selection aggregates.
- Cell viewer.
- Messages rows affected.
- PRINT/RAISERROR verbatim.
- Error click-to-line.
- Completion time.
- Estimated plan.
- Actual plan.
- Per-statement plans.
- Status bar: message, server/version, login/SPID, db, elapsed, editor cursor, grid cell, rows, connection color.
- DB dropdown and script-internal USE tracking.
- Dirty/save/save-as.
- Uncommitted transaction prompt.
- Reconnect after loss.
- IntelliSense completion/hover/signature/diagnostics.
- AI inline completions with debug/replay.
- Observability waterfall and perftest scenario.

## Appendix C — Minimum STS2 evidence for Query Studio preview

- Open/close/execute/cancel conformance against FakeDriver and SQL Server.
- Exactly-one query completion or documented adapter synthesizer path with server fix tracked.
- Verbatim query messages to client.
- Rows affected source pinned.
- Ack/credit ledger validated.
- Page options behavior known.
- SPID/server info available or probe path tested.
- Fatal/unavailable behavior tested.
- Privacy canaries clean.
