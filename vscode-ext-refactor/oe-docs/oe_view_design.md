# Object Explorer v2 View Design
## STS2/Data Plane-native Object Explorer with MetadataStore-backed catalog browsing and explicit STS v1 handoff

**Status:** drop-in replacement spec, reviewed 2026-07-05 against the current `main` Object Explorer and the current `dev/query` SQL Data Plane, MetadataService, Query Studio, and native language-provider seams.

**Primary target branch:** `dev/query` in `metadata/vscode-mssql`.

**Related documents:**

- `oe_metadata_design.md` covers the incremental metadata backend for the existing classic Object Explorer tree. That path is useful as migration scaffolding, fixture capture, and compatibility work, but it is not the final OE v2 architecture.
- `metadata_service_oe_v2_design.md` covers the required MetadataService/MetadataStore upgrades. OE v2 should not be built on the current per-document Query Studio metadata shape without those upgrades.
- `05-tsql-language-service-design.md` covers the native TypeScript T-SQL language service and TypeScript scripting engine that OE v2 should share for definitions and future Script As commands.

**Core rule:** OE v2's own connect, browse, expand, refresh, filter, search, table preview, and basic query operations must use the SQL Data Plane and MetadataStore. SQL Tools Service v1 connections are allowed only after an explicit user command that requires a legacy feature handoff. OE v2 must never use SQL Tools Service Object Explorer RPCs to populate its own tree.

**Recommended setting:**

```jsonc
"mssql.objectExplorer.viewMode": "classic" | "v2Preview"
```

Initial default: `classic`.

---

## 0. Executive summary

The draft had the right north star: a new Object Explorer view that uses the STS2/Data Plane connection and query path, with catalog data supplied by the new metadata integration. This replacement sharpens that plan into a coding-agent-ready design.

The key design decision is that **OE v2 is a new view and a new model, not a classic Object Explorer backend wearing a fresh coat of paint**. Classic Object Explorer can gain a metadata backend behind `mssql.objectExplorer.backend`, but it still carries classic assumptions: `TreeNodeInfo`, `NodeInfo`, `sessionId` as owner URI, package.json menu regexes, SQL Tools Service scripting expectations, and many commands that assume STS v1 state. OE v2 should instead have its own tree nodes, connection sessions, metadata coordinator, command router, and handoff service.

The second key decision is that the current metadata service must grow up from a Query Studio helper into a shared **MetadataStore**. Current code can key entries by `{ serverFingerprint, database }`, but the session source opens a single data-plane metadata session without receiving the catalog key. That makes multi-database Object Explorer browsing unsafe unless the registry fixes key-correct acquisition. OE v2 expands many databases under one server; it needs a server catalog, database-specific catalog leases, refresh/drift handling, and a neutral store used by Query Studio, the native language service, scripting, and Object Explorer.

The third key decision is strict handoff discipline. OE v2 may create STS v1 state for commands such as Backup/Restore, Profiler, DacFx, Table Designer, Schema Designer, or legacy scripting only after the user invokes that command. Handoff is command-scoped and observable. It is never a browse fallback, never created on view activation, and never used to refresh the v2 tree.

Build order:

1. Land the metadata substrate upgrades from `metadata_service_oe_v2_design.md`.
2. Add the OE v2 activation shell and setting.
3. Add data-plane connection sessions with no v1 creation.
4. Add server catalog and database catalog browsing.
5. Add native commands: refresh, filters, search, copy names, new Query Studio query, table preview.
6. Add explicit legacy handoff for selected commands.
7. Migrate scripting and object-management actions to native implementations as metadata coverage expands.
8. Flip default only after no-v1-browse tests, perf tests, command compatibility, and privacy gates are green.

---

## 1. Design review of the draft

### 1.1 What the draft already got right

- It treats OE v2 as an STS2/Data Plane-native view rather than a new set of STS v1 Object Explorer RPC calls.
- It separates OE v2 from the incremental metadata backend in `oe_metadata_design.md`.
- It states the important handoff rule: STS v1 is allowed for legacy features but not for OE v2 metadata browsing.
- It keeps STS2 wire DTOs out of feature code by requiring the SQL Data Plane domain API.
- It uses the same metadata-provider seam as the native language service.
- It calls out multi-database metadata as a required fix before OE v2 can be correct.
- It plans deterministic tests with the fake data-plane backend.

### 1.2 Improvements made in this replacement

#### 1.2.1 Make OE v2 a new tree model

The original plan still had several classic Object Explorer gravitational fields. This replacement makes the separation explicit:

- OE v2 uses `OeV2Node`, not `TreeNodeInfo`, as its internal model.
- OE v2 uses structured `OeV2Path`, not SQL Tools Service `nodePath` strings.
- OE v2 uses capability-driven menu contexts, not classic `type=Table,subType=...` regex compatibility as the primary contract.
- OE v2 opens data-plane sessions, not `ConnectionManager.connect(...)`, during normal browse.
- OE v2 converts to classic `TreeNodeInfo` only inside the legacy handoff service, and only for commands that still need it.

#### 1.2.2 Promote MetadataService to MetadataStore before relying on it

The draft said the metadata service needs to be multi-database. This replacement turns that into a hard precondition. OE v2 should consume a shared `IMetadataStore` with server and database leases. The current `MetadataService` can be a database-catalog engine inside that store, but it should not remain a per-document Query Studio helper.

#### 1.2.3 Split server catalog from database catalog

A server expansion begins with visible databases and server facts. That is not the same as a database object catalog. OE v2 needs:

- `ServerCatalogLease` for visible databases, server capabilities, engine facts, and permission-shaped partiality;
- `DatabaseCatalogLease` for schemas, objects, columns, keys, foreign keys, parameters, and object details.

#### 1.2.4 Define a handoff ladder

Some legacy commands only need a connected owner URI. Others need a `TreeNodeInfo`. The most tightly coupled commands may need an actual classic OE session or SMO URN. This design defines three levels:

1. **Connection handoff:** lazily call `ConnectionManager.connect(ownerUri, profile)`.
2. **Node adapter handoff:** create a best-effort `TreeNodeInfo` from an `OeV2Node`.
3. **Classic OE session handoff:** create a short-lived SQL Tools Service Object Explorer session only for a proven command that requires real classic OE/SMO node identity.

Every handoff is explicit, measured, and disposable.

#### 1.2.5 Add no-v1 tests as first-class gates

OE v2 should have tests that spy on classic APIs and fail if connect, expand, refresh, filter, or search creates STS v1 state. This is the guardrail that keeps the architecture honest when future changes enter the garden with muddy boots.

---

## 2. Current code truth this design depends on

### 2.1 Classic Object Explorer facts to avoid inheriting

Current classic Object Explorer does much more than tree rendering. `ObjectExplorerService` owns root connection groups, saved connections, child caching, loading nodes, in-flight dedupe, queued refresh-after-in-flight, serverless wake labels, SQL Tools Service Object Explorer session creation, expand/refresh requests, close-session requests, and connection-manager connect/disconnect calls.

Important behavior to know:

- Classic expand sends `ExpandRequest` or `RefreshRequest` and resolves `ExpandCompleteNotification` through pending expand maps keyed by session id plus node path.
- Classic create session sends `GetSessionIdRequest` and `CreateSessionRequest`, waits for `CreateSessionCompleteNotification`, then calls `ConnectionNode.updateToConnectedState(...)`.
- Classic success calls `ConnectionManager.connect(nodeUri, connectionProfile)`, where the node URI is usually the same value as `node.sessionId`.
- Classic close sends `CloseSessionRequest` and then disconnects the owner URI.
- Classic `getChildren` returns cached children, loading nodes, `NoItemsNode`, or `ExpandErrorNode` according to that service state.

OE v2 should copy useful UX patterns such as loading nodes and refresh queuing, but it should not reuse this session model as its own metadata path.

### 2.2 Classic node context facts

`TreeNodeInfo.fromNodeInfo(...)` creates menu context from `NodeInfo` values. The classic context `subType` comes from `NodeInfo.objectType`, while `nodeSubType` primarily drives icon lookup. That matters for the incremental metadata backend and for any legacy handoff adapter, but OE v2 should not base its native menu model on those classic strings.

### 2.3 SQL Data Plane facts

The SQL Data Plane domain API is the right OE v2 connection/query surface. It exposes:

- `SqlConnectionProfileRef` with stable profile fingerprint and safe display facts;
- `AuthProviderBundle` for password/token providers, keeping secrets out of stored state;
- `ISqlConnectionService.openSession(...)` with requested capabilities and application name;
- `ISqlSession.execute(...)` with `commandKind`, `priority`, `tag`, `expectedDatabase`, and query event sink;
- availability/capability reporting, session state changes, database-context change events, and close/dispose semantics.

OE v2 should import this domain API, not STS2 JSON-RPC transport types.

### 2.4 MetadataService facts

Current `MetadataService` hydrates schemas, objects, columns, identity/computed flags, primary-key columns, foreign keys, FK column pairs, and routine parameters. It tracks section readiness, immutable generations, refcounts, digest polling, DDL sniffing, and failure states.

The important correctness gap is multi-database acquisition. The service stores entries keyed by `{ serverFingerprint, database }`, but `DataPlaneMetadataSessionSource.open()` opens and caches one session based on its constructor `OpenSessionParams`. `MetadataService.acquire(key)` does not pass the requested key to the session source, and hydration queries do not issue a key-scoped database switch. A store/registry must fix this before OE v2 expands multiple databases.

### 2.5 Language-provider seam facts

The native language-service metadata seam already has most of the shape OE v2 needs for database object browsing:

- `ISqlLanguageMetadataProvider.generation`, `env()`, `readiness()`, `pin()`, `databases()`, `requestHydration(...)`, and `onDidChange(...)`.
- `IPinnedMetadataView.resolveObject(...)`, `getObject(...)`, `getColumns(...)`, `getParameters(...)`, `fkFrom(...)`, `fkTo(...)`, `searchObjects(...)`, and `listSchemas()`.

OE v2 should reuse the provider seam for object metadata but should not force all server-level metadata into that interface. Server catalog belongs beside it in the shared MetadataStore.

---

## 3. Goals and non-goals

### 3.1 Goals

| ID | Goal |
|---|---|
| V2-G1 | Add a new OE v2 view that can be enabled by setting while classic OE remains available. |
| V2-G2 | Connect, browse, expand, refresh, filter, and search through STS2/Data Plane plus MetadataStore only. |
| V2-G3 | Never create STS v1 connection state during OE v2 activation, connect, expand, refresh, filter, search, or table preview. |
| V2-G4 | Create STS v1 state only through explicit legacy handoff commands. |
| V2-G5 | Use shared saved connection profiles and credential providers without calling classic connection creation as a side effect. |
| V2-G6 | Use shared `IMetadataStore` server/database leases for catalog data. |
| V2-G7 | Keep STS2 wire DTOs out of `src/objectExplorer/v2/**`. |
| V2-G8 | Provide native v2 operations for refresh, filters, search, copy names, Query Studio new query, select top, and table preview. |
| V2-G9 | Use capability-driven command exposure, not classic context regex compatibility. |
| V2-G10 | Surface metadata readiness honestly: loading, ready-empty, stale, partial, failed, permission denied, and unsupported are distinct. |
| V2-G11 | Use fake data-plane and fixture metadata providers for deterministic tests. |
| V2-G12 | Make v1 handoff visible in status and telemetry, with an idle TTL and cleanup on disconnect. |

### 3.2 Non-goals

- Do not replace every classic Object Explorer feature in the first preview.
- Do not create a hidden STS v1 browse fallback.
- Do not call SQL Tools Service `objectExplorer/*` RPCs from OE v2 tree expansion.
- Do not call `ConnectionManager.connect(...)` merely to browse metadata.
- Do not import `TreeNodeInfo` or classic `NodeInfo` into pure OE v2 tree code.
- Do not import STS2 wire DTOs into OE v2 feature code.
- Do not make unsupported metadata appear as empty folders.
- Do not promise full SMO parity before the metadata sections exist.
- Do not make the incremental metadata backend a prerequisite for OE v2 unless a specific compatibility fixture or handoff adapter needs it.

---

## 4. Relationship to the incremental metadata backend

There are now two Object Explorer paths:

| Path | Setting | Purpose | STS v1 role |
|---|---|---|---|
| Classic OE with backend router | `mssql.objectExplorer.backend` | Incremental migration, fixture parity, compatibility testing in the existing view. | Normal classic path when backend is `sqlToolsService`; compatibility owner URI may still use v1-oriented command surfaces. |
| OE v2 | `mssql.objectExplorer.viewMode` | New Data Plane-native view and future default. | Explicit handoff only, never browse source. |

Recommended priority if the product goal is to remove STS v1 from the UI as much as possible:

1. Build the MetadataStore upgrades.
2. Build OE v2.
3. Use the classic metadata backend only for fixture capture, command-compatibility learning, or transitional dogfood if needed.
4. Do not pour advanced feature work into the classic metadata backend once OE v2 is viable. Classic OE can be a bridge, not a second castle.

---

## 5. Settings and activation

### 5.1 View mode setting

```jsonc
"mssql.objectExplorer.viewMode": {
  "type": "string",
  "enum": ["classic", "v2Preview"],
  "default": "classic",
  "markdownDescription": "Choose which Object Explorer view is active. Classic uses the established SQL Tools Service Object Explorer path. v2 Preview uses the SQL Data Plane and MetadataStore for its own browsing operations, with STS v1 only for explicit legacy feature handoff."
}
```

Setting rules:

- `classic` keeps current behavior.
- `v2Preview` shows and activates OE v2.
- Changing the setting does not migrate active connections automatically. Existing sessions remain in their original view until disconnected.
- OE v2 never silently falls back to classic when the data plane is unavailable.

### 5.2 Data-plane gate

OE v2 requires:

```jsonc
"mssql.sqlDataPlane.enabled": true
"mssql.sqlDataPlane.backend": "sts2-jsonrpc" | "fake"
```

If the data plane is disabled or unavailable, OE v2 shows a top-level unavailable node with:

- effective data-plane setting;
- backend availability state;
- command to open OE v2 status;
- command to open classic Object Explorer.

It must not create classic connections or classic Object Explorer sessions as a workaround.

### 5.3 Optional v2-specific settings

```jsonc
"mssql.objectExplorer.v2.confirmLegacyHandoff": true,
"mssql.objectExplorer.v2.tablePreviewRowLimit": 1000,
"mssql.objectExplorer.v2.groupBySchema": false,
"mssql.objectExplorer.v2.showSystemDatabases": true,
"mssql.objectExplorer.v2.enableNativeTablePreview": true
```

Notes:

- Reuse existing group-by-schema setting if the product already has one and the behavior should match classic.
- Keep handoff confirmation configurable. Dogfood may want it off; public preview should probably show a first-use disclosure so users understand why a legacy connection is being created.

### 5.4 View contribution recommendation

Contribute a separate preview tree view during development:

```text
view id: mssql.objectExplorerV2
view title: Object Explorer v2
container: same MSSQL activity-bar container as classic OE, or a preview container if preferred
```

Registration policy:

- Activate the v2 provider only when `viewMode == "v2Preview"` or when a command explicitly opens the preview view.
- Keep classic OE accessible during preview.
- After acceptance gates pass, v2 can replace the provider behind the existing public view id in a separate product decision.

---

## 6. Architecture

```text
VS Code Tree View: Object Explorer v2
  |
  v
OeV2TreeDataProvider
  |
  v
OeV2TreeController
  - view activation state
  - refresh batching
  - loading/status/error nodes
  - command context publication
  |
  v
OeV2TreeStore
  - OeV2Node records
  - structured OeV2Path ids
  - readiness and filters per node
  - stable view snapshots
  |
  +-------------------------------+
  |                               |
  v                               v
OeV2SessionRegistry          OeV2MetadataCoordinator
  - data-plane sessions          - server catalog leases
  - prepared profiles            - database catalog leases
  - connection lifecycle         - pinned metadata views
  - lost/reconnect state         - refresh/drift hooks
  |                               |
  v                               v
SQL Data Plane domain API     IMetadataStore
  |                               |
  v                               v
STS2 backend or fake backend  ServerCatalog + DatabaseCatalog
                                  |
                                  v
                          MetadataService engines

Explicit legacy command only:

OeV2CommandRouter
  -> OeV2ClassicHandoffService
      -> ConnectionManager.connect(...)
      -> optional classic OE session adapter
      -> legacy feature command
```

### 6.1 Module layout

Add new code under `src/objectExplorer/v2/**`:

```text
src/objectExplorer/v2/activation.ts
src/objectExplorer/v2/settings.ts
src/objectExplorer/v2/objectExplorerV2Provider.ts
src/objectExplorer/v2/tree/oeV2TreeController.ts
src/objectExplorer/v2/tree/oeV2TreeStore.ts
src/objectExplorer/v2/tree/oeV2Node.ts
src/objectExplorer/v2/tree/oeV2NodeFactory.ts
src/objectExplorer/v2/tree/oeV2Path.ts
src/objectExplorer/v2/tree/oeV2Readiness.ts
src/objectExplorer/v2/tree/oeV2Filters.ts
src/objectExplorer/v2/tree/oeV2Icons.ts
src/objectExplorer/v2/sessions/oeV2SessionRegistry.ts
src/objectExplorer/v2/sessions/oeV2ProfileAdapter.ts
src/objectExplorer/v2/sessions/oeV2ConnectionState.ts
src/objectExplorer/v2/metadata/oeV2MetadataCoordinator.ts
src/objectExplorer/v2/commands/oeV2CommandRouter.ts
src/objectExplorer/v2/commands/oeV2NativeCommands.ts
src/objectExplorer/v2/commands/oeV2QueryStudioCommands.ts
src/objectExplorer/v2/commands/oeV2TablePreview.ts
src/objectExplorer/v2/legacy/oeV2ClassicHandoffService.ts
src/objectExplorer/v2/legacy/oeV2LegacyNodeAdapter.ts
src/objectExplorer/v2/status/oeV2StatusModel.ts
src/objectExplorer/v2/telemetry/oeV2Telemetry.ts
```

Shared metadata code belongs under `src/services/metadata/**` and is specified in `metadata_service_oe_v2_design.md`:

```text
src/services/metadata/metadataStore.ts
src/services/metadata/serverMetadataService.ts
src/services/metadata/databaseMetadataService.ts
src/services/metadata/metadataProviderRegistry.ts
src/services/metadata/profileFingerprint.ts
src/services/metadata/profileAuthAdapter.ts
src/services/metadata/metadataSessionPool.ts
src/services/metadata/catalogProviderLease.ts
```

### 6.2 Dependency rules

| Layer | May import | Must not import |
|---|---|---|
| `objectExplorer/v2/objectExplorerV2Provider.ts` | `vscode`, controller, public node view model | STS2 DTOs, raw metadata SQL, classic OE RPC contracts |
| `objectExplorer/v2/tree/**` | pure v2 types and helpers | `vscode`, `TreeNodeInfo`, classic `NodeInfo`, SQL Data Plane singleton, MetadataService |
| `objectExplorer/v2/sessions/**` | SQL Data Plane domain API, profile/auth helpers, connection store seams | classic OE contracts, STS2 wire DTOs |
| `objectExplorer/v2/metadata/**` | `IMetadataStore` leases, language-provider seam types | concrete STS2 DTOs, classic OE contracts, raw SQL strings unless temporary adapter |
| `objectExplorer/v2/commands/**` | v2 node model, native command helpers, handoff service | direct `ConnectionManager.connect` except through handoff |
| `objectExplorer/v2/legacy/**` | `ConnectionManager`, classic node adapter, legacy command ids | metadata hydration logic, server/database browse logic |
| `services/metadata/**` | SQL Data Plane domain API, MetadataService engines, catalog model | OE v2 tree item classes, `vscode.TreeItem` |

Add lint/import-boundary tests before the second implementation slice.

---

## 7. Connection model

### 7.1 Prepared profile seam

OE v2 should reuse saved connection profiles and credential stores but split profile preparation from classic v1 connection creation.

```ts
export interface OeV2PreparedProfile {
    readonly originalProfile: IConnectionProfile;
    readonly profileRef: SqlConnectionProfileRef;
    readonly auth: AuthProviderBundle;
    readonly displayName: string;
    readonly defaultDatabase?: string;
    readonly groupId?: string;
    readonly profileId: string;
    readonly serverFingerprint: string;
}

export interface OeV2ProfileAdapter {
    listSavedProfiles(): Promise<readonly IConnectionProfile[]>;
    prepare(profile: IConnectionProfile): Promise<OeV2PreparedProfile>;
}
```

Implementation guidance:

- Extract profile fingerprint and auth-provider helpers from Query Studio into `src/services/metadata/profileFingerprint.ts` and `profileAuthAdapter.ts`.
- Passwords and tokens must be providers, not stored strings.
- Audit existing `ConnectionManager.prepareConnectionInfo(...)`. If it performs useful authentication/credential refresh without opening v1 state, wrap it. If it connects or mutates v1 state, split a pure helper first.
- Preserve local container startup behavior by extracting a `LocalContainerConnectionPreflight` helper that can be called before data-plane open.
- Preserve Entra account recovery by using the same account/token provider path, not by calling classic connect.

### 7.2 Native v2 connection session

OE v2 connection means opening an `ISqlSession` through the data plane:

```ts
const session = await connectionService.openSession({
    profile: prepared.profileRef,
    database: requestedDatabase ?? prepared.defaultDatabase,
    applicationName: "vscode-mssql-oe-v2",
    auth: prepared.auth,
    requestedCapabilities: {
        streamingRows: true,
        dispose: true,
        cancel: true,
    },
});
```

That session is used for:

- proving the profile opens;
- server info and engine facts;
- native query actions such as table preview;
- session/lost/reconnect state;
- lightweight server catalog probes if the shared server catalog uses this lane temporarily.

Metadata hydration should use dedicated metadata sessions through the shared MetadataStore, not the user's interactive tree/query session.

### 7.3 Session registry shape

```ts
export type OeV2ConnectionState =
    | "connecting"
    | "connected"
    | "lost"
    | "reconnecting"
    | "disconnecting"
    | "disconnected"
    | "failed";

export interface OeV2ConnectionSession {
    readonly id: string;
    readonly prepared: OeV2PreparedProfile;
    readonly state: OeV2ConnectionState;
    readonly primarySession?: ISqlSession;
    readonly serverFingerprint: string;
    readonly defaultDatabase?: string;
    readonly serverVersion?: string;
    readonly engineEdition?: string;
    readonly metadata: OeV2MetadataCoordinator;
    readonly handoff?: OeV2ClassicHandoffState;
}
```

Registry responsibilities:

- open and close data-plane sessions;
- expose connection state to the tree store;
- acquire/dispose metadata coordinator leases;
- maintain lost/reconnect state;
- close legacy handoff state on disconnect;
- never call classic OE RPCs;
- never call `ConnectionManager.connect(...)` except via `OeV2ClassicHandoffService`.

### 7.4 Serverless and transient connection behavior

Classic OE has special Azure serverless wake behavior. OE v2 should keep equivalent UX, but through v2 seams:

- show a `Resuming database` readiness state if the data-plane open or metadata query fails with a serverless pause/resume timeout and Azure status probing confirms a waking database;
- retry only through data-plane open/metadata refresh;
- do not create a classic OE session to wake the database;
- keep the retry count and timeout policy in a shared helper if classic and v2 use the same Azure status check.

### 7.5 No v1-on-connect rule

For OE v2, these are disallowed during activation, connect, expand, refresh, filter, and search:

```text
ConnectionManager.connect(...)
objectExplorer/createsession
objectExplorer/getsessionid
objectexplorer/expand
objectexplorer/refresh
objectexplorer/closesession
```

Add tests that spy on those surfaces. This rule is the tripwire. If it breaks, the tree starts growing secret tunnels.

---

## 8. Metadata coordination

OE v2 consumes the shared store defined in `metadata_service_oe_v2_design.md`.

### 8.1 Required store API

```ts
export interface IMetadataStore extends DisposableLike {
    prepareProfile(profile: IConnectionProfile): Promise<PreparedMetadataProfile>;
    acquireServer(input: AcquireServerInput): Promise<ServerCatalogLease>;
    acquireDatabase(input: AcquireDatabaseInput): Promise<DatabaseCatalogLease>;
    refresh(input: MetadataRefreshRequest): Promise<void>;
    notifyExecutedBatch(input: MetadataDriftNotification): void;
    status(): MetadataStoreStatus;
}
```

### 8.2 OE v2 metadata coordinator

```ts
export interface OeV2MetadataCoordinator extends DisposableLike {
    readonly connectionId: string;
    readonly serverLease: ServerCatalogLease;

    serverView(): IPinnedServerCatalogView;
    acquireDatabase(database: string): Promise<DatabaseCatalogLease>;
    databaseView(database: string): IPinnedMetadataView | undefined;
    refreshPath(path: OeV2Path): Promise<void>;
    notifyExecutedBatch(input: MetadataDriftNotification): void;
    status(): OeV2MetadataStatus;
}
```

Coordinator rules:

- Pin once per tree expand.
- Do not mix generations within a response.
- Never show `No items` unless the relevant section is `ready` and the result set is truly empty.
- If the server catalog says a database is inaccessible, render that explicitly rather than trying to acquire a database catalog and then guessing.
- Use store readiness events to refresh only affected nodes.

### 8.3 Server catalog

Server expansion needs:

- visible databases;
- database state/read-only/accessibility;
- engine edition/version/capabilities;
- partial/failure states;
- user/system database classification if available;
- database-scoped connection behavior.

Minimum first-pass query, subject to engine compatibility:

```sql
SELECT
    d.database_id,
    d.name,
    d.state_desc,
    d.is_read_only,
    d.user_access_desc,
    d.compatibility_level,
    HAS_DBACCESS(d.name) AS has_dbaccess
FROM sys.databases AS d
WHERE HAS_DBACCESS(d.name) = 1
ORDER BY d.name;
```

Important edge cases:

- Azure SQL Database may only expose the connected database depending on permissions.
- Fabric/Synapse/SQL Warehouse may have different catalog surfaces.
- `HAS_DBACCESS` can return `NULL`.
- A database can be visible but offline, restoring, suspect, paused, or permission-limited.
- Server catalog query failure is not an empty database list.

### 8.4 Database catalog

Database object browsing uses `ISqlLanguageMetadataProvider` and `IPinnedMetadataView` through a database catalog lease.

Required initial sections:

- environment facts: current database, default schema, collation/case sensitivity, engine edition, server version/capabilities;
- schemas;
- objects: tables, views, procedures, scalar functions, table-valued functions, synonyms;
- columns with type display, nullable, identity, computed, PK column flag;
- foreign keys with ordered column pairs;
- routine parameters.

Strongly recommended before broader OE parity:

- PK/unique constraint names;
- indexes with key order, included columns, uniqueness, filter definitions;
- default and check constraints;
- triggers;
- module definitions and encrypted/permission states;
- extended properties/descriptions;
- synonym targets;
- temporal/history table relationships;
- object/database modify dates;
- approximate row counts if the UI displays them.

### 8.5 Multi-database correctness

OE v2 must not show database B's objects under database A. Acceptable implementations:

1. **Preview-safe:** one dedicated metadata session/service per database with `OpenSessionParams.database` set explicitly.
2. **Optimized target:** one server-scoped metadata lane with a private serialized queue and `USE [db]` guards before each database-scoped hydration group.
3. **API cleanup:** make the metadata session source key-aware, such as `open(key: CatalogKey)`.

The store hides this strategy from OE v2. OE v2 asks for a database lease and receives a key-correct pinned view.

Required test:

- create database A and database B with distinct table names and overlapping object ids where possible;
- acquire both through one OE v2 connection;
- prove A's tree cannot show B's objects and B's tree cannot show A's objects.

---

## 9. Tree model

### 9.1 Node shape

```ts
export interface OeV2Node {
    readonly id: string;
    readonly path: OeV2Path;
    readonly kind: OeV2NodeKind;
    readonly label: string;
    readonly description?: string;
    readonly tooltip?: string;
    readonly collapsible: boolean;
    readonly connectionId?: string;
    readonly database?: string;
    readonly schema?: string;
    readonly objectName?: string;
    readonly objectKind?: OeV2ObjectKind;
    readonly readiness: OeV2Readiness;
    readonly capabilities: OeV2NodeCapabilities;
    readonly metadata?: OeV2ObjectMetadata;
}
```

`OeV2Node` is pure data. The VS Code provider converts it to `vscode.TreeItem` at the edge.

### 9.2 Node kinds

```ts
export type OeV2NodeKind =
    | "root"
    | "connectionGroup"
    | "disconnectedConnection"
    | "connectingConnection"
    | "connectedServer"
    | "lostConnection"
    | "serverFolder"
    | "database"
    | "databaseFolder"
    | "schema"
    | "object"
    | "objectFolder"
    | "column"
    | "parameter"
    | "key"
    | "foreignKey"
    | "index"
    | "constraint"
    | "trigger"
    | "loading"
    | "status"
    | "error"
    | "unsupported"
    | "noItems";
```

### 9.3 Structured paths

```ts
export type OeV2Path =
    | { kind: "root" }
    | { kind: "connectionGroup"; groupId: string }
    | { kind: "connection"; connectionId: string }
    | { kind: "server"; connectionId: string }
    | { kind: "serverFolder"; connectionId: string; folder: OeV2ServerFolder }
    | { kind: "database"; connectionId: string; database: string }
    | { kind: "databaseFolder"; connectionId: string; database: string; folder: OeV2DatabaseFolder }
    | { kind: "schema"; connectionId: string; database: string; schema: string }
    | { kind: "schemaFolder"; connectionId: string; database: string; schema: string; folder: OeV2DatabaseFolder }
    | { kind: "object"; connectionId: string; database: string; schema: string; name: string; objectKind: OeV2ObjectKind; objectId?: number }
    | { kind: "objectFolder"; connectionId: string; database: string; schema: string; name: string; objectKind: OeV2ObjectKind; objectId?: number; folder: OeV2ObjectFolder }
    | { kind: "column"; connectionId: string; database: string; schema: string; objectName: string; column: string; objectId?: number }
    | { kind: "parameter"; connectionId: string; database: string; schema: string; objectName: string; parameter: string; ordinal: number; objectId?: number }
    | { kind: "status"; connectionId?: string; scope: string }
    | { kind: "error"; connectionId?: string; scope: string; code?: string };
```

Path rules:

- Encode all paths deterministically with a version prefix.
- Use percent-encoding for path segments.
- Do not log full path strings by default.
- Do not use object names as globally stable identities when object ids are available.
- Treat stale object ids after refresh as stale-path errors that recover on parent refresh.

### 9.4 Readiness

```ts
export type OeV2ReadinessKind =
    | "notApplicable"
    | "loading"
    | "ready"
    | "readyEmpty"
    | "stale"
    | "partial"
    | "failed"
    | "permissionDenied"
    | "unsupported"
    | "dataPlaneUnavailable"
    | "legacyHandoffOnly";

export interface OeV2Readiness {
    readonly kind: OeV2ReadinessKind;
    readonly message?: string;
    readonly generation?: number;
    readonly retryable?: boolean;
}
```

Display rule: only `readyEmpty` produces a no-items child. Failed, absent, stale, unsupported, and permission-denied states get their own status/error nodes.

### 9.5 Capabilities

```ts
export interface OeV2NodeCapabilities {
    readonly canConnect?: boolean;
    readonly canDisconnect?: boolean;
    readonly canRefresh?: boolean;
    readonly canFilter?: boolean;
    readonly canSearch?: boolean;
    readonly canCopyName?: boolean;
    readonly canCopyQualifiedName?: boolean;
    readonly canOpenQuery?: boolean;
    readonly canSelectTop?: boolean;
    readonly canPreviewTable?: boolean;
    readonly canScriptCreateNative?: boolean;
    readonly canScriptAlterNative?: boolean;
    readonly canScriptDropNative?: boolean;
    readonly legacyHandoff: readonly OeV2LegacyFeature[];
}
```

Menus should be capability-driven. A command appears because a tested route exists, not because the node looks like a classic `Table` string.

---

## 10. Tree expansion rules

### 10.1 Root

Top-level content:

```text
Connections
  <connection group>
    <disconnected profile>
    <connected server>
```

Implementation choices:

- Reuse existing connection store for saved profiles and groups.
- Do not reuse `ObjectExplorerService` session state.
- If group storage is too coupled to classic OE, extract a read-only `ConnectionProfileTreeSource` first.

### 10.2 Disconnected connection node

Shows saved profile display name and connect capability. On expand, either:

- show a status child with connect action; or
- connect on explicit command only.

Avoid auto-connect-on-expand in first preview unless classic behavior requires it for user expectations. Explicit connect gives clearer no-v1 tests.

### 10.3 Connected server node

Children:

- Databases folder.
- Later: Security, Server Objects, Management, SQL Agent, Linked Servers, where native metadata exists.

Do not show advanced server folders until the store can back them honestly.

### 10.4 Databases folder

Use server catalog pinned view.

States:

| Server catalog state | Tree behavior |
|---|---|
| loading | loading child |
| ready with databases | database nodes |
| ready with zero visible databases | no-items child |
| failed | error child with refresh capability |
| partial | visible databases plus status child |
| permission-denied | permission/status child |

Sorting:

- Match classic if fixture capture shows a strong product expectation.
- Otherwise use stable case-insensitive display ordering unless the server collation says case-sensitive and duplicates differ by case.

### 10.5 Database node

Initial folders:

- Tables;
- Views;
- Stored Procedures;
- Functions;
- Synonyms;
- Schemas.

Acquire the database catalog lease lazily when the database node expands. Do not hydrate every database at server connect time.

### 10.6 Object folders

Use `IPinnedMetadataView.searchObjects(...)` or a store-level `listObjects(...)` facade.

Folder mapping:

| Folder | Object kinds |
|---|---|
| Tables | `table` |
| Views | `view` |
| Stored Procedures | `procedure` |
| Functions | `scalarFunction`, `tableFunction` |
| Synonyms | `synonym` |
| Schemas | `listSchemas()` |

Group-by-schema:

- If disabled, list object nodes directly.
- If enabled, list schema group nodes first, then objects below each schema.

### 10.7 Object children

Initial child folders:

| Parent | Children |
|---|---|
| table | Columns, Primary Key, Foreign Keys |
| view | Columns |
| stored procedure | Parameters |
| scalar function | Parameters |
| table function | Columns, Parameters |
| synonym | target placeholder only if target metadata exists |

Future folders:

- Indexes;
- Constraints;
- Triggers;
- Statistics;
- Dependencies;
- Permissions;
- Extended Properties.

### 10.8 Filters

Implement native v2 filters in memory over pinned metadata views.

Initial filterable folders:

- Tables;
- Views;
- Stored Procedures;
- Functions;
- Synonyms;
- Schemas.

Initial filter properties:

```ts
[
    { name: "Name", type: "string" },
    { name: "Schema", type: "string" }
]
```

Operators:

- equals;
- contains;
- startsWith;
- endsWith if UI exposes it;
- notEquals if UI exposes it.

Filter semantics must respect catalog case sensitivity.

---

## 11. Native v2 commands

### 11.1 Command ids

Use v2 command ids during preview:

```text
mssql.objectExplorerV2.connect
mssql.objectExplorerV2.disconnect
mssql.objectExplorerV2.refresh
mssql.objectExplorerV2.filter
mssql.objectExplorerV2.clearFilters
mssql.objectExplorerV2.search
mssql.objectExplorerV2.copyName
mssql.objectExplorerV2.copyQualifiedName
mssql.objectExplorerV2.newQuery
mssql.objectExplorerV2.selectTop
mssql.objectExplorerV2.tablePreview
mssql.objectExplorerV2.showStatus
mssql.objectExplorerV2.openClassicObjectExplorer
mssql.objectExplorerV2.handoffToClassic
```

Do not wire classic command ids directly to v2 nodes until compatibility is proven.

### 11.2 Native command matrix

| Operation | Native v2 implementation |
|---|---|
| Connect | `ISqlConnectionService.openSession` plus MetadataStore server lease. |
| Disconnect | close data-plane session, dispose metadata leases, close handoff state. |
| Refresh server | server catalog refresh. |
| Refresh database | database catalog lease refresh. |
| Refresh folder | refresh relevant lease or section. |
| Filter folder | in-memory filter over pinned metadata. |
| Clear filters | tree-store state update. |
| Search object names | metadata provider/store search. |
| Copy name | local identifier formatter. |
| Copy qualified name | local formatter with bracket escaping. |
| New query | open Query Studio with profile/database context. |
| Select top rows | data-plane query or Query Studio with generated SQL. |
| Table preview | data-plane query with row/page/cell limits. |
| Show status | local v2 status model. |

### 11.3 Query Studio open seam

Add or extend a Query Studio command contract:

```ts
export interface QueryStudioOpenFromContextRequest {
    readonly profile: SqlConnectionProfileRef;
    readonly auth: AuthProviderBundle;
    readonly database?: string;
    readonly initialSql?: string;
    readonly source: "objectExplorerV2";
}
```

OE v2 should default to Query Studio for new query actions. If the user explicitly chooses the classic editor and that editor still requires v1, route through handoff.

### 11.4 Table preview and SELECT TOP

Initial generated SQL:

```sql
SELECT TOP (1000) *
FROM [schema].[table];
```

Rules:

- bracket-escape identifiers;
- execute in the selected database through `OpenSessionParams.database` or `ExecuteOptions.expectedDatabase`;
- avoid concatenated `USE` in the user-visible query path;
- cap row count, page bytes, and cell bytes;
- do not log generated SQL by default;
- prefer Query Studio result grid if available.

### 11.5 Native scripting path

Once `SqlScriptingService` from the language-service plan is available, OE v2 routes supported script operations there.

Policy:

| Case | Action |
|---|---|
| Native TS scripting supports node kind | run native scripting. |
| Native scripting does not support node kind but legacy scripting is proven | use explicit handoff. |
| Neither is true | hide command or show preview limitation. |

Do not assume synthetic metadata identity works with legacy SMO scripting.

---

## 12. Legacy handoff

### 12.1 Principle

Handoff is a user-command boundary, not a metadata source.

OE v2 may create STS v1 state only after the user invokes a legacy command that requires it. Handoff should be visible in status, measured, and disposed when idle or when the v2 connection disconnects.

### 12.2 Handoff service

```ts
export interface OeV2ClassicHandoffService {
    ensureClassicOwnerUri(input: OeV2HandoffInput): Promise<OeV2ClassicOwnerUri>;
    toLegacyTreeNode(node: OeV2Node, ownerUri: string): TreeNodeInfo | undefined;
    ensureClassicObjectExplorerSession?(input: OeV2HandoffInput): Promise<OeV2ClassicOeSession>;
    run<T>(input: OeV2HandoffInput, action: (ctx: OeV2ClassicHandoffContext) => Promise<T>): Promise<T>;
    close(connectionId: string): Promise<void>;
}
```

### 12.3 Handoff levels

| Level | What it creates | Use when |
|---|---|---|
| H1 connection owner | `ConnectionManager.connect(ownerUri, profile)` | command only needs a connected URI. |
| H2 adapted node | `TreeNodeInfo` built from `OeV2Node` plus H1 owner URI | command expects classic node shape but not real SMO/OE path. |
| H3 classic OE session | SQL Tools Service Object Explorer session and optionally real node path | command requires real classic OE/SMO identity. |

H3 is the dragon door. It is allowed, but every use must be named in the policy table and tested.

### 12.4 Initial handoff policy table

| Feature | Initial OE v2 policy |
|---|---|
| Browse/expand tree | native only, no handoff. |
| Refresh tree | native only, no handoff. |
| Filter/search tree | native only, no handoff. |
| Copy name/qualified name | native only. |
| New Query | Query Studio native by default. |
| Select top/table preview | native data-plane query. |
| Classic editor | H1 handoff if no data-plane editor route exists. |
| Script Create/Alter/Drop/Select/Execute | native TS scripting if available, otherwise guarded H2/H3 handoff or hidden. |
| Table Designer/Edit Table | H2/H3 handoff initially. |
| Schema Designer | H2/H3 handoff initially. |
| Backup/Restore | H1/H2 handoff initially. |
| DacFx import/export | H1/H2 handoff initially. |
| Profiler | H1 handoff initially. |
| Schema Compare | H1/H2 handoff initially. |
| Create/Rename/Drop database | hidden or guarded handoff until a tested native route exists. |

### 12.5 Handoff guardrails

- No handoff from `getChildren`.
- No handoff during view activation.
- No handoff during connect.
- No handoff during refresh.
- No handoff during filter/search.
- No silent handoff after a native command fails.
- No legacy handoff metadata can update the v2 tree.
- Every handoff command has a capability check, status entry, telemetry event, and test.
- Handoff state has an idle TTL and is disposed on v2 disconnect.

---

## 13. Error and readiness UX

### 13.1 Data plane unavailable

Top-level unavailable node:

```text
Object Explorer v2 unavailable
  SQL Data Plane is disabled or unavailable
  [Show status]
  [Open Classic Object Explorer]
```

No classic fallback.

### 13.2 Metadata loading

Use loading nodes for sections that are actively hydrating. Prefer targeted refreshes when store events arrive rather than refreshing the whole tree.

### 13.3 Metadata failed

Show sanitized error nodes with refresh capability. Never show `No items` for failed metadata.

### 13.4 Partial catalog

Render ready sections and show a status child for missing/failed sections. Example:

```text
Tables
Views
Stored Procedures
Metadata status: columns unavailable, foreign keys failed. Refresh available.
```

### 13.5 Permission denied

If a database or object is visible but inaccessible, show permission state explicitly. Do not treat it as absent.

### 13.6 Lost connection

When the primary session is lost:

- mark the connection node lost;
- disable native query actions;
- mark metadata leases stale or dispose according to store policy;
- close handoff state unless the legacy feature owns its own lifetime;
- show reconnect.

---

## 14. Observability and privacy

### 14.1 Events and spans

```text
objectExplorerV2.view.activate
objectExplorerV2.connection.open
objectExplorerV2.connection.close
objectExplorerV2.connection.lost
objectExplorerV2.serverCatalog.acquire
objectExplorerV2.serverCatalog.refresh
objectExplorerV2.databaseCatalog.acquire
objectExplorerV2.databaseCatalog.refresh
objectExplorerV2.tree.expand
objectExplorerV2.tree.filter
objectExplorerV2.tree.search
objectExplorerV2.command.route
objectExplorerV2.command.native
objectExplorerV2.command.handoff
objectExplorerV2.legacyConnection.created
objectExplorerV2.unsupported
objectExplorerV2.noV1Browse.violation
```

### 14.2 Allowed fields

- view mode;
- data-plane backend kind;
- node kind;
- folder kind;
- readiness state;
- generation number;
- object count;
- filter count;
- duration;
- result status;
- command route: native, handoff, hidden, unavailable;
- handoff level;
- unsupported reason;
- short non-reversible profile fingerprint.

### 14.3 Disallowed by default

- SQL text;
- result rows;
- raw connection strings;
- passwords;
- tokens;
- raw server endpoints;
- full object names unless classified and explicitly allowed;
- full node paths.

### 14.4 Privacy canaries

Add tests that create fake profiles and object names containing:

```text
Password=
Pwd=
AccessToken
Bearer
server.example.internal
user@example.com
```

Then assert diagnostics, telemetry fields, status dumps, and path encodings do not leak them except through explicitly classified UI labels.

---

## 15. Performance targets

| Operation | Target |
|---|---:|
| Activate v2 view with no connection | p95 < 50 ms extension-host work |
| Open saved profile quick pick/list | same as classic or better |
| Connect to data-plane session | bounded by backend, no extra v1 connection |
| Expand server to loading/Databases | immediate UI response |
| Warm Databases folder expand | p95 < 50 ms host work |
| Warm database structural folder expand | p95 < 30 ms host work |
| Warm Tables folder, 10k objects | p95 < 150 ms host work |
| Filter 10k objects | p95 < 50 ms host work |
| Expand table with 1k columns | p95 < 50 ms host work |
| Table preview first page | backend-bound, UI stays responsive |
| Handoff command overhead | measured separately, never on browse path |

Rules:

- No network call in pure node factory code.
- No classic connection in performance measurements for native browse.
- Pin once per expand.
- Do not hydrate every database on server connect.
- Avoid locale-heavy sorting in hot paths unless measured.
- Add large catalog fixtures before dogfood.

---

## 16. Tests

### 16.1 Unit tests

```text
test/unit/objectExplorerV2/oeV2Path.test.ts
test/unit/objectExplorerV2/oeV2NodeFactory.test.ts
test/unit/objectExplorerV2/oeV2Readiness.test.ts
test/unit/objectExplorerV2/oeV2Filters.test.ts
test/unit/objectExplorerV2/oeV2Capabilities.test.ts
test/unit/objectExplorerV2/oeV2CommandRouter.test.ts
test/unit/objectExplorerV2/oeV2ClassicHandoffService.test.ts
```

Required assertions:

- structured paths encode/decode safely;
- pure tree modules import no `vscode`, classic OE contracts, or STS2 DTOs;
- readiness maps to loading/error/no-items correctly;
- capability model controls command exposure;
- filters respect case sensitivity;
- handoff is not reachable from browse operations.

### 16.2 Metadata tests

```text
test/unit/services/metadata/metadataStore.test.ts
test/unit/services/metadata/serverMetadataService.test.ts
test/unit/services/metadata/databaseCatalogIsolation.test.ts
test/unit/objectExplorerV2/oeV2MetadataCoordinator.test.ts
```

Required assertions:

- database A and database B catalogs stay isolated;
- server catalog failure is not empty database list;
- database catalog section failure is not empty folder;
- store refresh increments generations correctly;
- store leases dispose sessions and listeners.

### 16.3 Fake data-plane integration tests

- v2 activates without v1 state.
- saved profile connects through fake data plane.
- server expands to databases without classic OE RPCs.
- database expands to folders without classic OE RPCs.
- object folders render from fixture metadata.
- refresh uses metadata leases.
- table preview uses data-plane execute.
- lost connection state appears.
- disconnect closes data-plane sessions, metadata leases, and handoff state.

### 16.4 No-v1-browse tests

Spy on:

```text
ConnectionManager.connect
GetSessionIdRequest
CreateSessionRequest
ExpandRequest
RefreshRequest
CloseSessionRequest
```

These must not be called during:

- view activation;
- connect;
- expand server;
- expand databases;
- expand database folders;
- refresh;
- filter;
- search;
- table preview.

### 16.5 Handoff tests

- Handoff command creates v1 state exactly once per TTL.
- Handoff failure does not mutate v2 metadata tree.
- Disconnect closes handoff.
- Handoff status is visible.
- H3 classic OE session handoff is used only by commands explicitly marked as requiring it.

### 16.6 Perf tests

```text
objectExplorerV2.activate
objectExplorerV2.connectToDatabasesReady
objectExplorerV2.expandDatabases.warm
objectExplorerV2.expandTables.10k
objectExplorerV2.filterTables.10k
objectExplorerV2.expandColumns.1k
objectExplorerV2.tablePreview.firstPage
objectExplorerV2.handoffLatency
```

---

## 17. Implementation plan

### V2-0: Settings, activation shell, and no-v1 tripwires

Files:

```text
src/objectExplorer/v2/activation.ts
src/objectExplorer/v2/settings.ts
src/objectExplorer/v2/objectExplorerV2Provider.ts
src/objectExplorer/v2/status/oeV2StatusModel.ts
package.json
```

Work:

1. Add `mssql.objectExplorer.viewMode`.
2. Contribute/register the preview view.
3. Render disconnected/unavailable/status nodes.
4. Add `mssql.objectExplorerV2.showStatus`.
5. Add no-v1-browse test harness spies.

Exit criteria:

- Classic OE remains default.
- OE v2 can be enabled and shown without connecting.
- Activation creates no v1 state.
- Data-plane disabled state is explicit.

### V2-1: Shared profile/auth helpers and MetadataStore foundation

Files:

```text
src/services/metadata/profileFingerprint.ts
src/services/metadata/profileAuthAdapter.ts
src/services/metadata/metadataStore.ts
src/services/metadata/metadataSessionPool.ts
src/objectExplorer/v2/sessions/oeV2ProfileAdapter.ts
```

Work:

1. Extract stable profile fingerprinting from Query Studio.
2. Extract auth provider creation from Query Studio and connection store seams.
3. Add profile preparation helper that does not create v1 connections.
4. Start MetadataStore implementation per `metadata_service_oe_v2_design.md`.

Exit criteria:

- Query Studio still connects and acquires metadata.
- OE v2 can list saved profiles.
- Fingerprints are stable and secret-free.
- No v1 state is created by preparation.

### V2-2: Data-plane connection registry

Files:

```text
src/objectExplorer/v2/sessions/oeV2SessionRegistry.ts
src/objectExplorer/v2/sessions/oeV2ConnectionState.ts
src/objectExplorer/v2/tree/oeV2NodeFactory.ts
```

Work:

1. Open `ISqlSession` through `SqlDataPlaneService`.
2. Render connected, failed, lost, reconnecting, and disconnected nodes.
3. Close session on disconnect.
4. Wire session state changes to tree refresh.

Exit criteria:

- Saved profile connects through data plane.
- No `ConnectionManager.connect(...)` during connect.
- Lost session state is visible.

### V2-3: Server catalog

Files:

```text
src/services/metadata/serverMetadataService.ts
src/objectExplorer/v2/metadata/oeV2MetadataCoordinator.ts
src/objectExplorer/v2/tree/oeV2TreeStore.ts
```

Work:

1. Acquire server catalog lease through MetadataStore.
2. Render server node and Databases folder.
3. Render database nodes with readiness/accessibility state.
4. Add refresh for server catalog.

Exit criteria:

- Server expands to visible databases with no classic OE RPCs.
- Server catalog failure is explicit.
- Database-scoped connections are represented honestly.

### V2-4: Database metadata tree

Files:

```text
src/objectExplorer/v2/metadata/oeV2MetadataCoordinator.ts
src/objectExplorer/v2/tree/oeV2Path.ts
src/objectExplorer/v2/tree/oeV2Filters.ts
src/services/metadata/metadataProviderRegistry.ts
```

Work:

1. Implement key-correct database catalog acquisition.
2. Render database structural folders.
3. Render tables, views, procedures, functions, synonyms, and schemas.
4. Render columns, parameters, PKs, and FKs where metadata is ready.
5. Implement group-by-schema.

Exit criteria:

- Multiple databases under one server show distinct correct objects.
- Object folders render from metadata without v1 calls.
- Ready-empty and failed sections are distinct.

### V2-5: Native basic commands

Files:

```text
src/objectExplorer/v2/commands/oeV2CommandRouter.ts
src/objectExplorer/v2/commands/oeV2NativeCommands.ts
src/objectExplorer/v2/commands/oeV2QueryStudioCommands.ts
```

Work:

1. Implement refresh, filter, clear filters, search.
2. Implement copy name and copy qualified name.
3. Add Query Studio open-from-context command.
4. Add capability-driven menus.

Exit criteria:

- Basic OE workflows are usable without v1.
- Query actions default to Query Studio/data-plane route.
- Unsupported commands are hidden or clearly unavailable.

### V2-6: Table preview and SELECT TOP

Files:

```text
src/objectExplorer/v2/commands/oeV2TablePreview.ts
src/objectExplorer/v2/commands/sqlIdentifierFormatter.ts
```

Work:

1. Generate safe SELECT TOP SQL.
2. Execute through data plane with row/page/cell limits.
3. Show results in Query Studio or a minimal v2 preview surface.
4. Add expected-database tests.

Exit criteria:

- Table preview creates no v1 state.
- Generated identifiers are escaped correctly.
- Query does not log SQL text by default.

### V2-7: Explicit legacy handoff

Files:

```text
src/objectExplorer/v2/legacy/oeV2ClassicHandoffService.ts
src/objectExplorer/v2/legacy/oeV2LegacyNodeAdapter.ts
src/objectExplorer/v2/commands/oeV2LegacyCommandPolicy.ts
```

Work:

1. Implement H1 connection-owner handoff.
2. Implement H2 `TreeNodeInfo` adapter for proven commands.
3. Implement H3 classic OE session handoff only if required by selected commands.
4. Add first-use confirmation/status/telemetry.
5. Add policy table in code.

Exit criteria:

- Browse path still creates no v1 state.
- Handoff works for selected legacy commands.
- Handoff failure does not mutate v2 tree metadata.

### V2-8: Native scripting and command migration

Work:

1. Route native script operations to `SqlScriptingService`.
2. Add metadata sections needed for scripting parity.
3. Migrate high-value handoff commands to native implementations.
4. Add command parity report.

Exit criteria:

- Handoff count trends down.
- Native scripting is available for supported object kinds.
- Unsupported script operations are honest.

### V2-9: Default flip readiness

Exit criteria:

- No-v1-browse tests mandatory in CI.
- MetadataStore multi-database tests green.
- Native command matrix meets preview bar.
- Handoff is explicit and measured.
- Large-catalog perf targets met.
- Privacy review complete.
- Classic OE remains accessible for rollback.

---

## 18. Acceptance gates

Minimum OE v2 preview:

- `mssql.objectExplorer.viewMode = "v2Preview"` shows the v2 view.
- With data plane enabled, a saved profile connects through `ISqlConnectionService.openSession`.
- Activation, connect, expand, refresh, filter, search, and table preview create no STS v1 connection and send no classic OE RPCs.
- Databases folder lists visible databases through server catalog.
- Multiple databases have key-correct metadata.
- Tables, views, procedures, functions, synonyms, and schemas render from metadata.
- Columns, parameters, PKs, and FKs render where metadata is ready.
- Refresh, filters, search, copy name, copy qualified name, new Query Studio query, and table preview work natively.
- Unsupported features are hidden, disabled with explanation, or routed through explicit handoff.
- Handoff creates v1 state only after a handoff command is invoked.
- Status shows data-plane state, metadata readiness, catalog generations, and handoff state.

Must not regress:

- Classic Object Explorer default behavior.
- Saved profile and connection group storage.
- Query Studio data-plane connection behavior.
- Native language-service metadata-provider behavior.
- Password/token secrecy.

---

## 19. Open questions

1. Should the v2 preview view appear side-by-side with classic, or should `viewMode` hide one and show the other?
2. Which Query Studio command should accept an external profile/database/initial SQL request?
3. Which legacy commands only need H1 connection handoff, which need H2 node adapter, and which truly require H3 classic OE session?
4. Should table preview always open Query Studio, or should OE v2 have a small preview grid?
5. What is the first native scripting target for OE v2: `SELECT`, `CREATE`, `ALTER`, or `DROP`?
6. How should database-scoped Azure SQL connections represent a server if the user can only see the current database?
7. Should connection groups be shared read-only at first, or should v2 introduce a new connection grouping model that later replaces classic?
8. Should the preview confirm first legacy handoff by default?

---

## 20. Final instruction for the coding agent

Build OE v2 as a new STS2/Data Plane-native tree. Do not skin classic Object Explorer. Reuse saved profiles, icons, metadata providers, Query Studio commands, and scripting services where they are cleanly separable, but keep OE v2's own connection and metadata browsing independent of STS v1.

Start with settings, activation, and no-v1-browse tests. Then build data-plane connection sessions, server catalog browsing, database catalog browsing, native commands, table preview, and only then explicit legacy handoff. If OE v2 needs a catalog fact that the current MetadataService does not expose, add it to the shared MetadataStore first. Pin metadata once per expand. Treat failure as failure, not emptiness. Treat STS v1 as a handoff tool, not as a secret basement under the new tree.
