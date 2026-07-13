# Object Explorer Metadata Backend: Technical Review and Implementation Plan
## Incremental metadata backend for classic Object Explorer, now aligned with OE v2 and MetadataStore

**Status:** drop-in replacement spec, updated 2026-07-05 after the OE v2 design review.

**Primary target branch:** `dev/query` in `metadata/vscode-mssql`.

**Compatibility reference:** current `main` branch Object Explorer in `microsoft/vscode-mssql`, plus current Object Explorer request handling in `microsoft/sqltoolsservice`.

**Related design:** `oe_view_design.md` defines the preferred long-term OE v2 view. This document defines the incremental backend seam for the existing classic Object Explorer view. Use it for migration scaffolding, fixture capture, and compatibility learning. Do not mistake it for the final no-STS-v1 Object Explorer architecture.

**Recommended preview setting:**

```jsonc
"mssql.objectExplorer.backend": "sqlToolsService" | "metadataService"
```

Initial default: `sqlToolsService`.

**Core distinction:** Classic OE with a metadata backend may still need owner-URI compatibility with existing commands. OE v2 must not. If the primary product goal is to remove STS v1 from the UI as much as possible, prioritize the OE v2 plan and the MetadataStore upgrades.

---

## 0. Executive summary

This document remains useful, but its role is narrower now.

The incremental metadata backend lets the existing Object Explorer tree route expansion through TypeScript metadata instead of SQL Tools Service Object Explorer RPCs. It preserves the old UI, `TreeNodeInfo`, `NodeInfo`, connection groups, loading behavior, refresh queue, filter UI, and context-menu compatibility. That makes it valuable for dogfood, fixture capture, and learning which commands depend on classic node shapes.

It is not the clean end state. The existing Object Explorer model still assumes classic `sessionId` semantics, `ConnectionManager.connect(...)` owner URIs, package.json context regexes, and downstream command paths that may expect STS v1/SMO identity. For a true no-v1 browse experience, use `oe_view_design.md`.

The largest technical prerequisite remains the metadata substrate. Current `MetadataService` can key entries by server/database, but its session source is not key-aware. Classic metadata backend and OE v2 both need a shared MetadataStore that can safely acquire server and database catalogs across multiple databases. The store work is specified in `metadata_service_oe_v2_design.md`.

Recommended implementation strategy:

1. Capture live classic `NodeInfo` fixtures before changing anything.
2. Extract the current SQL Tools Service Object Explorer path behind `IObjectExplorerBackend` with no behavior change.
3. Build or consume the shared MetadataStore.
4. Add `MetadataObjectExplorerBackend` only for folders backed by ready metadata.
5. Guard or reroute commands that cannot consume metadata-generated nodes.
6. Keep this backend side-by-side until OE v2 or parity evidence makes it unnecessary.

---

## 1. What this document is and is not

### 1.1 This document is

- A plan to add a metadata route under the existing classic Object Explorer view.
- A compatibility harness for matching SQL Tools Service `NodeInfo` shapes.
- A stepping stone for command audits, context-menu audits, and fixture generation.
- A way to reduce SQL Tools Service Object Explorer expansion usage in the existing tree while OE v2 is built.

### 1.2 This document is not

- The final OE v2 architecture.
- A no-v1 guarantee for the entire Object Explorer UI.
- A replacement for classic command services such as Backup/Restore, Profiler, DacFx, Table Designer, or Schema Designer.
- A reason to make MetadataService depend on classic Object Explorer shapes.

### 1.3 Priority guidance

If engineering capacity is limited:

1. Build MetadataStore v2 first.
2. Build OE v2 second.
3. Do the classic backend extraction only if needed to stabilize legacy behavior or capture fixtures.
4. Avoid investing in advanced classic metadata backend parity once OE v2 is viable.

---

## 2. Current behavior to preserve in the classic view

Classic `ObjectExplorerService` owns:

- root connection groups and saved connection nodes;
- connection-node mutation;
- connection profile preparation and error handling;
- local container startup;
- Missing Entra account recovery;
- serverless wake/resume label updates;
- child cache in `_treeNodeToChildrenMap`;
- in-flight child fetch dedupe;
- refresh-after-in-flight queue;
- loading node UI;
- SQL Tools Service Object Explorer session creation;
- expand/refresh/close RPCs;
- connection-manager connect/disconnect;
- password storage after connect.

The backend seam must sit below those behaviors. Do not move all of that UX and command state into a backend class.

---

## 3. Backend route architecture

```text
Classic VS Code Object Explorer view
  |
  v
ObjectExplorerProvider
  |
  v
ObjectExplorerService
  - root nodes and groups
  - cache and loading UI
  - refresh queue
  - connection manager compatibility
  - command-visible TreeNodeInfo
  |
  v
ObjectExplorerBackendRouter
  |
  |-----------------------------------------------|
  v                                               v
LegacyStsObjectExplorerBackend                   MetadataObjectExplorerBackend
- current STS OE RPCs                            - NodeInfo factory over metadata
- exact behavior compatibility                   - structured metadata paths
                                                  |
                                                  v
                                      IMetadataStore / Provider leases
                                                  |
                                                  v
                                      SQL Data Plane domain API
```

### 3.1 Dependency rules

| Layer | May import | Must not import |
|---|---|---|
| `objectExplorerService.ts` | backend router, classic node types, connection manager | raw metadata SQL, STS2 DTOs |
| `legacyStsObjectExplorerBackend.ts` | existing classic OE contracts | metadata provider types |
| `metadataObjectExplorerBackend.ts` | MetadataStore leases, node factory, `NodeInfo` | classic OE request contracts, STS2 wire DTOs |
| `objectExplorerNodeFactory.ts` | `NodeInfo`, neutral metadata types | `vscode`, connection manager, MetadataService concrete classes |
| `services/metadata/**` | SQL Data Plane domain API, catalog model, provider adapters | classic `TreeNodeInfo` |

---

## 4. Settings

```jsonc
"mssql.objectExplorer.backend": {
  "type": "string",
  "enum": ["sqlToolsService", "metadataService"],
  "default": "sqlToolsService",
  "markdownDescription": "Choose whether classic Object Explorer reads database metadata from SQL Tools Service Object Explorer or the extension's TypeScript MetadataService preview."
}
```

Route policy:

- The setting applies to new classic OE sessions.
- Existing sessions keep their backend until disconnect.
- `metadataService` mode must not silently delegate unsupported folders to SQL Tools Service Object Explorer.
- A hidden dogfood route `metadataWithExplicitLegacyFallback` may exist only if every fallback emits diagnostics and status.

Do not overload this setting for OE v2. OE v2 uses `mssql.objectExplorer.viewMode`.

---

## 5. Backend interface

```ts
export type ObjectExplorerBackendKind = "sqlToolsService" | "metadataService";

export interface ObjectExplorerSessionRecord {
    readonly treeSessionId: string;
    readonly ownerUri: string;
    readonly backendKind: ObjectExplorerBackendKind;
    readonly connectionProfileId: string;
    readonly serverFingerprint: string;
    readonly defaultDatabase?: string;
    readonly createdAtUtc: string;
}

export interface ObjectExplorerPreparedConnection {
    readonly connectionProfile: IConnectionProfile;
    readonly connectionInfo: IConnectionInfo;
    readonly profileRef: SqlConnectionProfileRef;
    readonly auth: AuthProviderBundle;
}

export interface ObjectExplorerCreateSessionInput {
    readonly preparedConnection: ObjectExplorerPreparedConnection;
    readonly requestedOwnerUri?: string;
}

export interface ObjectExplorerCreateSessionResult {
    readonly success: boolean;
    readonly backendKind: ObjectExplorerBackendKind;
    readonly treeSessionId: string;
    readonly ownerUri: string;
    readonly rootNode?: NodeInfo;
    readonly errorNumber?: number;
    readonly errorMessage?: string;
    readonly errorCode?: string;
    readonly shouldRetryOnFailure?: boolean;
    readonly retryHint?: "serverlessWake" | "auth" | "transient";
}

export interface ObjectExplorerExpandInput {
    readonly treeSessionId: string;
    readonly ownerUri: string;
    readonly nodePath: string;
    readonly filters?: vscodeMssql.NodeFilter[];
    readonly forceRefresh: boolean;
}

export interface ObjectExplorerExpandResult {
    readonly treeSessionId: string;
    readonly ownerUri: string;
    readonly nodePath: string;
    readonly nodes?: NodeInfo[];
    readonly errorMessage?: string;
    readonly errorCode?: string;
    readonly incompleteReason?:
        | "metadataNotReady"
        | "metadataFailed"
        | "unsupportedNode"
        | "staleNode"
        | "permissionDenied";
    readonly catalogGeneration?: number;
}

export interface IObjectExplorerBackend extends DisposableLike {
    readonly kind: ObjectExplorerBackendKind;
    createSession(input: ObjectExplorerCreateSessionInput): Promise<ObjectExplorerCreateSessionResult>;
    expandNode(input: ObjectExplorerExpandInput): Promise<ObjectExplorerExpandResult>;
    refresh?(input: { treeSessionId: string; ownerUri: string; nodePath?: string }): Promise<void>;
    closeSession(treeSessionId: string): Promise<void>;
}
```

Compatibility rule:

- Legacy: `treeSessionId === ownerUri === stsObjectExplorerSessionId`.
- Metadata backend: `treeSessionId === ownerUri === generatedMetadataOwnerUri` at first, because downstream classic commands still read `TreeNodeInfo.sessionId`.
- Follow-up cleanup: add `TreeNodeInfo.ownerUri`, then make `sessionId` backend-only.

---

## 6. Classic service integration

`ObjectExplorerService` should remain the owner of:

- profile preparation;
- connection-node creation/mutation;
- loading/error/no-items UX;
- serverless wake label;
- child cache;
- refresh queue;
- `ConnectionManager.connect(...)` compatibility path;
- disconnect and password storage.

Backend-specific work moves behind `ObjectExplorerBackendRouter`.

### 6.1 Create flow

```ts
const prepared = await metadataConnectionAdapter.prepare(connectionProfile);
const backend = backendRouter.selectForCreate(connectionProfile);
const result = await backend.createSession({ preparedConnection: prepared });

if (result.success) {
    recordSession(result);
    connectionNode.updateToConnectedState({
        nodeInfo: result.rootNode,
        sessionId: result.treeSessionId,
        connectionProfile,
        parentNode,
    });
    await connectionManager.connect(result.ownerUri, connectionProfile);
}
```

This is classic-view compatibility. OE v2 must not do this during browse.

### 6.2 Expand flow

1. Look up `ObjectExplorerSessionRecord` by `node.sessionId`.
2. Route to that backend.
3. Convert returned `NodeInfo[]` through `TreeNodeInfo.fromNodeInfo(...)`.
4. Preserve existing cache/loading/error behavior.

### 6.3 Close flow

1. Route to backend close.
2. Disconnect owner URI through connection manager.
3. Clear child cache.
4. Mutate connection node to disconnected state.

---

## 7. Metadata backend session model

```ts
interface MetadataObjectExplorerSession extends DisposableLike {
    readonly treeSessionId: string;
    readonly ownerUri: string;
    readonly serverFingerprint: string;
    readonly profileRef: SqlConnectionProfileRef;
    readonly connectionProfile: IConnectionProfile;
    readonly serverLease: ServerCatalogLease;
    readonly defaultDatabase?: string;

    acquireDatabase(database: string): Promise<DatabaseCatalogLease>;
    getDatabaseLease(database: string): DatabaseCatalogLease | undefined;
    refreshPath(path: OeMetadataPath): Promise<void>;
}
```

Session creation:

1. Validate data-plane and MetadataStore availability.
2. Generate a secret-free owner URI, such as `objectexplorer://metadata/<fingerprint>/<uuid>`.
3. Acquire server catalog lease.
4. Start server catalog hydration.
5. Return a root `NodeInfo` equivalent to a connected server node.
6. Do not hydrate every database.

---

## 8. Metadata path model

Use structured paths internally and encode into `NodeInfo.nodePath` only at the boundary.

```ts
export type OeMetadataPath =
    | { kind: "server" }
    | { kind: "serverFolder"; folder: "databases" | "security" | "serverObjects" }
    | { kind: "database"; database: string }
    | { kind: "databaseFolder"; database: string; folder: OeDatabaseFolder }
    | { kind: "schema"; database: string; schema: string; usage: "folder" | "object" }
    | { kind: "schemaFolder"; database: string; schema: string; folder: OeDatabaseFolder }
    | { kind: "object"; database: string; objectId: number; objectKind: LangObjectKind }
    | { kind: "objectFolder"; database: string; objectId: number; folder: OeObjectFolder }
    | { kind: "column"; database: string; objectId: number; column: string }
    | { kind: "parameter"; database: string; objectId: number; parameter: string; ordinal: number }
    | { kind: "primaryKey"; database: string; objectId: number; name: string }
    | { kind: "foreignKey"; database: string; objectId: number; foreignKey: string };
```

Encoding examples:

```text
metadata-v1:/server
metadata-v1:/server/folder/databases
metadata-v1:/database/<db>
metadata-v1:/database/<db>/folder/tables
metadata-v1:/database/<db>/object/<objectId>/<kind>
metadata-v1:/database/<db>/object/<objectId>/folder/columns
```

Rules:

- All parsing goes through helpers.
- All path segments are percent-encoded.
- Stale object ids are stale-path errors, not empty folders.

---

## 9. NodeInfo construction

Classic metadata backend returns `NodeInfo[]` for compatibility.

Every factory must set:

```text
nodePath
parentNodePath
nodeType
label
nodeSubType
nodeStatus
isLeaf
metadata
filterableProperties
objectType
```

Important context fact: `TreeNodeInfo.fromNodeInfo(...)` uses `NodeInfo.objectType` as menu `subType`. Set `nodeSubType` for icons and `objectType` for menus intentionally.

Before finalizing strings, capture live SQL Tools Service fixtures. Do not infer the full contract from package.json.

Synthetic metadata URN format:

```text
metadata://<serverFingerprint>/<database>/<schema>/<kind>/<objectId>
```

Synthetic URNs are identity hints and future TypeScript scripting inputs. They are not proof that legacy SMO scripting can consume the node.

---

## 10. Expand rules

### 10.1 Server root

Return Databases folder. Add advanced server folders only when backed by shared server metadata.

### 10.2 Databases folder

Use `ServerCatalogLease.pin().listDatabases()`.

Only return `NoItemsNode` when the server catalog is ready and the visible database list is empty.

### 10.3 Database node

Acquire database lease lazily. Return stable folders:

- Tables;
- Views;
- Stored Procedures;
- Functions;
- Synonyms;
- Schemas.

Do not show object folders as authoritative if the objects section is not ready.

### 10.4 Object folders

Use pinned metadata view `searchObjects(...)` or `listObjects(...)` facade. Apply filters after listing and before node construction.

### 10.5 Object children

Initial:

- Table: Columns, Keys, Foreign Keys.
- View: Columns.
- Procedure/function: Parameters.

Failed sections show error/status children, not empty folders.

---

## 11. Command compatibility

Audit at least:

```text
mssql.objectExplorerNewQuery
mssql.refreshObjectExplorerNode
mssql.disconnectObjectExplorerNode
mssql.filterNode
mssql.filterNodeWithExistingFilters
mssql.clearFilters
mssql.copyObjectName
mssql.copyConnectionString
mssql.scriptSelect
mssql.scriptCreate
mssql.scriptDelete
mssql.scriptExecute
mssql.scriptAlter
mssql.newTable
mssql.editTable
mssql.tableExplorer
mssql.schemaCompare
mssql.profiler.launchFromObjectExplorer
mssql.profiler.launchFromDatabase
mssql.schemaDesigner
mssql.buildDataApi
mssql.searchDatabase
mssql.dacpacDialog.launch
mssql.createDatabase
mssql.renameDatabase
mssql.dropDatabase
mssql.backupDatabase
mssql.restoreDatabase
mssql.flatFileImport
mssql.notebooks.createNotebook
```

Policy:

| Metadata node command state | Action |
|---|---|
| Command works with owner URI and metadata fields | expose. |
| TypeScript scripting route exists | route there. |
| Legacy route proven with metadata node | expose with tests. |
| Legacy route needs real STS/SMO identity | hide, friendly message, or explicit legacy fallback only if route is instrumented. |
| Unknown | hide in metadata preview. |

Do not expose a command just because the classic context string matches.

---

## 12. Observability and privacy

Events:

```text
objectExplorer.backend.route
objectExplorer.backend.createSession
objectExplorer.backend.expand
objectExplorer.backend.refresh
objectExplorer.backend.closeSession
objectExplorer.metadata.nodeBuild
objectExplorer.metadata.filter
objectExplorer.metadata.unsupported
objectExplorer.metadata.commandCompatibility
```

Allowed fields:

- backend kind;
- node type;
- node subtype;
- path kind, not full path by default;
- readiness state;
- generation;
- object count;
- filter count;
- duration;
- result status;
- unsupported reason;
- short profile fingerprint.

Disallowed fields:

- SQL text;
- rows;
- raw connection strings;
- passwords;
- tokens;
- raw server endpoints;
- full object names unless classified and allowed.

---

## 13. Implementation plan

### OE-0: Fixture capture

Work:

1. Capture current SQL Tools Service `NodeInfo` fixtures for server, database, folders, tables, views, procedures, functions, columns, keys, FKs, parameters, and filters.
2. Snapshot `TreeNodeInfo.fromNodeInfo(...)` context values.
3. Use fixtures as compatibility oracle for node strings and metadata fields.

Exit criteria:

- Fixtures are committed.
- No product behavior changes.

### OE-1: No-behavior-change backend seam

Work:

1. Extract current STS OE RPC/notification logic into `LegacyStsObjectExplorerBackend`.
2. Add `ObjectExplorerBackendRouter`.
3. Keep default route `sqlToolsService`.
4. Preserve all current tests and UX.

Exit criteria:

- Classic OE behavior unchanged.
- Legacy requests and notifications still match current behavior.

### OE-2: MetadataStore integration

Work:

1. Consume `IMetadataStore` server/database leases.
2. Use shared profile/auth helpers.
3. Require key-correct multi-database acquisition.
4. Add status command.

Exit criteria:

- Metadata backend can acquire a server catalog and database catalog leases.
- Two-database isolation tests pass.

### OE-3: Minimal metadata tree

Work:

1. Metadata session creation.
2. Server root and Databases folder.
3. Database nodes and structural folders.
4. Honest readiness states.

Exit criteria:

- Metadata mode connects and expands to database folders.
- No classic OE create/expand/refresh RPCs during metadata route.

### OE-4: Object folders and filters

Work:

1. Tables/views/procedures/functions/synonyms/schemas.
2. Group-by-schema.
3. TypeScript filters.
4. Object metadata fields and synthetic URNs.

Exit criteria:

- Command utilities work for copy name and new query.
- Unsupported commands are hidden or guarded.

### OE-5: Child details

Work:

1. Columns.
2. Keys and foreign keys.
3. Parameters.
4. Failed-section handling.

Exit criteria:

- Object details render deterministically.
- Failed details are not empty.

### OE-6: Refresh and drift

Work:

1. Refresh maps to server/database lease refresh.
2. DDL-producing commands notify metadata store where possible.
3. Stale object ids recover on refresh.

Exit criteria:

- Refresh after DDL updates the tree.
- Stale paths do not show ghost objects.

### OE-7: Command audit and routing

Work:

1. Audit all visible commands.
2. Route TypeScript scripting where available.
3. Hide/guard unsupported classic commands.
4. Add command compatibility matrix.

Exit criteria:

- Metadata nodes expose no known-broken commands.

### OE-8: Decide future role

At this point decide:

- Continue classic metadata backend toward parity; or
- Freeze it as compatibility/scaffolding and focus on OE v2.

Default flip for `mssql.objectExplorer.backend` should not be considered unless command compatibility and perf gates are green.

---

## 14. Tests

- Fixture tests for classic `NodeInfo` and context strings.
- Backend router tests.
- Metadata path encode/decode tests.
- Node factory tests.
- Filter tests.
- Readiness mapping tests.
- Multi-database metadata tests.
- No silent fallback tests.
- Command compatibility tests.
- Privacy canaries.
- Large-catalog perf tests.

---

## 15. Acceptance matrix

Minimum metadata backend preview:

- Legacy default unchanged.
- Metadata route can connect in classic view.
- Databases folder comes from MetadataStore server catalog.
- Database folders and common object folders come from database metadata.
- Filters work on supported object folders.
- Table columns, PKs, FKs, and routine parameters render where metadata is ready.
- Ready-empty and failed are distinct.
- Unsupported folders are omitted or explicit.
- Metadata mode does not silently fall back to SQL Tools Service Object Explorer.
- Commands are audited and broken routes are hidden/guarded.

---

## 16. Final instruction for the coding agent

Treat this backend as compatibility scaffolding for the classic view. First capture fixtures. Then extract the legacy backend without behavior change. Then consume the shared MetadataStore, not a per-document metadata helper. Return classic `NodeInfo` only at the boundary, set `objectType` and `nodeSubType` deliberately, pin metadata once per expand, and never report failed or unavailable metadata as empty.

If the goal is a true no-v1 browsing UI, do not overbuild this path. Build OE v2.
