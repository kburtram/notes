# MetadataStore v2 for Object Explorer v2
## Multi-connection, multi-server, multi-database metadata substrate for Query Studio, native language service, scripting, classic metadata backend, and OE v2

**Status:** new design spec, created 2026-07-05 as a required substrate plan for OE v2.

**Primary target branch:** `dev/query` in `metadata/vscode-mssql`.

**Consumers:** Query Studio, native TypeScript language service, TypeScript scripting service, classic Object Explorer metadata backend, and Object Explorer v2.

**Core premise:** The current `MetadataService` is a strong database-catalog hydrator, but OE v2 needs a shared MetadataStore: a generic, key-correct, multi-connection, multi-server, multi-database metadata service with server catalog, database catalog, object detail, refresh, drift, caching, and provider adapters.

---

## 0. Executive summary

Object Explorer v2 cannot be correct if metadata remains tied to a single Query Studio document session. OE v2 expands servers, many databases, and many object folders. It needs catalog data to be instant when warm, honest when loading or failed, and safe across multiple databases under the same server.

Current code has useful pieces:

- SQL Data Plane domain API with safe profile refs, auth providers, sessions, query execution, and backend capabilities.
- `MetadataService` with H0-H6 database catalog hydration, immutable generation snapshots, readiness states, DDL sniffing, and digest polling.
- `CatalogLanguageMetadataProvider` that adapts catalog snapshots into a narrow language-provider seam.

But the current shape is not enough:

- `MetadataService` entries are keyed by `{ serverFingerprint, database }`, but the session source is not key-aware.
- Query Studio creates metadata service instances per document connection.
- Server catalog/database list is still a host seam rather than a first-class shared service.
- Object Explorer needs richer object details than completions need.
- Multiple consumers need shared leases, not copied metadata hydraters.

This document defines `IMetadataStore`: a shared service that owns profile/auth preparation, server catalog leases, key-correct database catalog leases, object detail hydration, refresh/drift coordination, cache policy, provider adapters, and diagnostics.

Recommended build path:

1. Extract profile fingerprint and auth-provider helpers.
2. Add `IMetadataStore` and a registry around the existing `MetadataService`.
3. Fix key-correct database acquisition, preview-safe via one metadata session per database or optimized via server lane plus serialized `USE`.
4. Add `ServerMetadataService` for visible databases and server facts.
5. Extend database catalog sections for OE details.
6. Move Query Studio and language service onto the store.
7. Let OE v2 consume store leases only.

---

## 1. Current code truth

### 1.1 SQL Data Plane

The SQL Data Plane domain API already has the right feature boundary. It provides `SqlConnectionProfileRef`, `AuthProviderBundle`, `ISqlConnectionService.openSession(...)`, session state, database-change events, query execution, command kind, priority, tags, expected database, and capability reporting. It explicitly keeps STS2 wire DTOs out of feature code.

### 1.2 Current MetadataService

Current `MetadataService`:

- stores catalog entries keyed by `serverFingerprint|database`;
- hydrates schemas, objects/synonyms, columns, identity/computed flags, primary-key columns, foreign keys, FK column pairs, and routine parameters;
- builds immutable `CatalogSnapshot` generations;
- publishes readiness and mode;
- marks failed sections as failed rather than empty;
- supports explicit refresh, DDL sniffing, and cheap digest polling;
- uses a `MetadataSessionSource` whose `open()` returns an `ISqlSession`.

The critical gap: `MetadataSessionSource.open()` receives no `CatalogKey`. `DataPlaneMetadataSessionSource` caches one session. Therefore `MetadataService.acquire({ database: "A" })` and `.acquire({ database: "B" })` can both run queries on whatever database that one session is actually using unless the source was constructed per database or a higher-level registry serializes database context changes. OE v2 must not build on that ambiguity.

### 1.3 Current Query Studio metadata shape

`DocumentSessionBinding` opens the user's data-plane session, then creates a dedicated `DataPlaneMetadataSessionSource` and a `MetadataService` for that document. It acquires one catalog for the current connection database and exposes a metadata handle for consumers.

This is fine for one document. It is not a generic metadata store.

### 1.4 Current language provider

`CatalogLanguageMetadataProvider` maps a metadata handle into `ISqlLanguageMetadataProvider` and `IPinnedMetadataView`. That adapter should remain, but the host should move from per-document Query Studio handles to store-backed database catalog leases.

---

## 2. Requirements

### 2.1 Functional requirements

| ID | Requirement |
|---|---|
| MD-G1 | Provide a shared metadata service for all features in the extension host. |
| MD-G2 | Support multiple saved profiles, servers, and databases concurrently. |
| MD-G3 | Provide a server catalog with visible databases and server facts. |
| MD-G4 | Provide key-correct database catalogs. |
| MD-G5 | Expose immutable pinned views with monotonic generations. |
| MD-G6 | Distinguish ready, loading, stale, partial, failed, permission denied, unsupported, and ready-empty. |
| MD-G7 | Support explicit refresh at server, database, object, and section scopes. |
| MD-G8 | Support DDL drift notifications from Query Studio, classic editor, OE v2, and scripting. |
| MD-G9 | Provide provider adapters for native language service and OE v2. |
| MD-G10 | Keep SQL Data Plane domain API as the only connection/query dependency. |
| MD-G11 | Avoid STS2 wire DTOs and classic Object Explorer types in metadata services. |
| MD-G12 | Preserve privacy: no SQL text, rows, passwords, tokens, or raw connection strings in diagnostics. |

### 2.2 Non-goals for the first slice

- Full SMO parity.
- Full disk cache.
- Cross-server distributed metadata.
- Server Agent, Linked Server, and Management folder parity unless metadata sections are added.
- Background hydration of every database on connect.
- Using classic Object Explorer RPCs as a metadata source.

---

## 3. Target architecture

```text
Feature consumers
  - Query Studio
  - Native SQL language service
  - SqlScriptingService
  - Classic OE metadata backend
  - OE v2
        |
        v
IMetadataStore
  |
  +-- Profile/Auth/Fingerprint helpers
  |
  +-- ServerMetadataService
  |     - visible databases
  |     - server facts
  |     - readiness/failure states
  |
  +-- DatabaseMetadataService / MetadataService engines
  |     - schemas/objects/columns/keys/FKs/params
  |     - object details
  |     - pinned CatalogSnapshots
  |
  +-- MetadataSessionPool
  |     - data-plane sessions
  |     - per-server or per-database lanes
  |     - serialized database-context switching where needed
  |
  +-- SnapshotCache
  |     - memory LRU
  |     - future disk cache
  |
  +-- DriftCoordinator
  |     - notifyExecutedBatch
  |     - digest polling
  |     - explicit refresh
  |
  +-- Provider adapters
        - CatalogLanguageMetadataProvider
        - OeMetadata facade
        - Scripting detail reader
```

---

## 4. Identity and keys

### 4.1 Profile fingerprint

```ts
export interface StableProfileIdentity {
    readonly profileFingerprint: string;
    readonly displayName?: string;
    readonly serverDisplayName?: string;
    readonly authKind: "sql" | "integrated" | "aad" | "bearer";
}
```

Rules:

- Deterministic for the same logical connection.
- Non-reversible.
- Excludes password, token, raw connection string, and unredacted diagnostic secrets.
- Includes enough connection-affecting facts to avoid unsafe sharing: server identity, auth kind, user identity where appropriate, encryption/trust semantics, tenant/account identity where appropriate.

### 4.2 Store keys

```ts
export interface ServerKey {
    readonly profileFingerprint: string;
}

export interface DatabaseKey extends ServerKey {
    readonly database: string;
}

export interface ObjectKey extends DatabaseKey {
    readonly objectId?: number;
    readonly schema?: string;
    readonly name?: string;
    readonly kind?: LangObjectKind;
}
```

Rules:

- `DatabaseKey.database` is normalized for keying but preserves display spelling.
- Object ids are stable within a database generation, not forever.
- After refresh, stale object keys must re-resolve by schema/name/kind when possible.

---

## 5. Public API

### 5.1 Store interface

```ts
export interface IMetadataStore extends DisposableLike {
    prepareProfile(profile: IConnectionProfile): Promise<PreparedMetadataProfile>;

    acquireServer(input: AcquireServerInput): Promise<ServerCatalogLease>;
    acquireDatabase(input: AcquireDatabaseInput): Promise<DatabaseCatalogLease>;
    acquireObjectDetails(input: AcquireObjectDetailsInput): Promise<ObjectDetailsLease>;

    refresh(input: MetadataRefreshRequest): Promise<void>;
    notifyExecutedBatch(input: MetadataDriftNotification): void;

    status(): MetadataStoreStatus;
    onDidChange(listener: (event: MetadataStoreChangeEvent) => void): DisposableLike;
}
```

### 5.2 Prepared profile

```ts
export interface PreparedMetadataProfile {
    readonly profileRef: SqlConnectionProfileRef;
    readonly auth: AuthProviderBundle;
    readonly serverKey: ServerKey;
    readonly defaultDatabase?: string;
    readonly displayName?: string;
}
```

### 5.3 Server catalog lease

```ts
export interface ServerCatalogLease extends DisposableLike {
    readonly key: ServerKey;
    readonly generation: number;
    status(): ServerCatalogStatus;
    pin(): IPinnedServerCatalogView;
    refresh(reason?: MetadataRefreshReason): Promise<void>;
    onDidChange(listener: () => void): DisposableLike;
}

export interface IPinnedServerCatalogView {
    readonly generation: number;
    readonly readiness: ServerCatalogReadiness;
    readonly serverInfo?: ServerInfoSummary;
    listDatabases(): readonly ServerDatabaseInfo[] | undefined;
    getDatabase(name: string): ServerDatabaseInfo | undefined;
}
```

### 5.4 Database catalog lease

```ts
export interface DatabaseCatalogLease extends DisposableLike {
    readonly key: DatabaseKey;
    readonly provider: ISqlLanguageMetadataProvider;
    readonly generation: number;
    status(): DatabaseCatalogStatus;
    pin(): IPinnedMetadataView;
    refresh(reason?: MetadataRefreshReason): Promise<void>;
    requestHydration?(request: HydrationRequest): void;
    onDidChange(listener: () => void): DisposableLike;
}
```

### 5.5 Object details lease

```ts
export type ObjectDetailSection =
    | "definition"
    | "indexes"
    | "constraints"
    | "triggers"
    | "extendedProperties"
    | "permissions"
    | "rowCount"
    | "temporal"
    | "synonymTarget";

export interface ObjectDetailsLease extends DisposableLike {
    readonly key: ObjectKey;
    readonly sections: readonly ObjectDetailSection[];
    status(): ObjectDetailsStatus;
    current(): ObjectDetailsSnapshot | undefined;
    refresh(reason?: MetadataRefreshReason): Promise<void>;
}
```

---

## 6. Session strategy

### 6.1 Preview-safe strategy: one metadata session per database

This is easiest to prove correct with current code.

```text
ServerKey(profile fp)
  -> ServerMetadataService session
DatabaseKey(profile fp, db A)
  -> DataPlaneMetadataSessionSource(OpenSessionParams.database = A)
  -> MetadataService for db A
DatabaseKey(profile fp, db B)
  -> DataPlaneMetadataSessionSource(OpenSessionParams.database = B)
  -> MetadataService for db B
```

Pros:

- key-correct by construction;
- small changes to current `MetadataService`;
- easy tests.

Cons:

- more backend sessions;
- may be heavy for many databases;
- needs eviction/refcount discipline.

### 6.2 Optimized target: one server metadata lane with serialized USE

```text
ServerKey(profile fp)
  -> MetadataSessionLane
      queue:
        USE [db A]; H0-H6 queries
        USE [db B]; H0-H6 queries
        USE [db A]; digest query
```

Rules:

- Lane is private to metadata.
- All database-context changes are serialized.
- Every query group runs after an explicit database switch or database-bound session open.
- The session's `signalDatabaseChanged` state is kept truthful.
- No user query runs on this lane.

Pros:

- fewer backend sessions;
- better for many databases.

Cons:

- more complex;
- requires careful timeout/cancel/error handling;
- all query groups must be serialized to avoid cross-db races.

### 6.3 API cleanup: key-aware session source

Preferred long-term type:

```ts
export interface KeyAwareMetadataSessionSource {
    open(key: DatabaseKey): Promise<ISqlSession>;
}
```

Then `MetadataService` cannot accidentally hydrate the wrong database because it asks for a session with the key it is hydrating.

### 6.4 Recommendation

Use one session per database for the first OE v2 preview unless session pressure is already unacceptable. Add the key-aware API now, even if its first implementation opens per-database sessions. Later optimize behind that interface.

---

## 7. ServerMetadataService

### 7.1 Responsibilities

- Open/acquire server-level metadata session.
- Read visible database list.
- Read server version/edition/capabilities.
- Track readiness/failure/partial state.
- Refresh on demand.
- Publish generation changes.
- Avoid treating failure as empty.

### 7.2 Minimum query

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

### 7.3 Database info shape

```ts
export interface ServerDatabaseInfo {
    readonly databaseId?: number;
    readonly name: string;
    readonly state?: string;
    readonly isReadOnly?: boolean;
    readonly userAccess?: string;
    readonly compatibilityLevel?: number;
    readonly hasDbAccess?: boolean;
    readonly isSystem?: boolean;
    readonly accessState: "accessible" | "inaccessible" | "unknown" | "permissionDenied";
}
```

### 7.4 Edge cases

- Azure SQL database-scoped logins may see only the current database.
- Managed Instance and SQL Server expose broader `sys.databases` behavior.
- Fabric/Synapse may require alternate queries or reduced metadata.
- Paused serverless databases can look like transient failures.
- Permission limitations must be modeled as partial/permission states.

---

## 8. Database catalog service

### 8.1 Keep current H0-H6 but make it key-correct

Existing sections:

| Section | Current purpose |
|---|---|
| H0 | engine edition, default schema, collation/case sensitivity |
| H1 | schemas |
| H2 | objects and synonyms |
| H3 | columns, type display, identity, computed |
| H4 | primary-key columns |
| H5/H5B | foreign keys and column pairs |
| H6 | routine parameters |

Required changes:

- Ensure each hydration runs in the database from `DatabaseKey`.
- Expose section readiness through store status.
- Add an object listing method that is safe for OE folder enumeration.
- Add schema list and case-sensitivity-aware filtering.

### 8.2 Object listing API

The language provider has `searchObjects(query)`. For OE, add a store-level or pinned-view method that is semantically a list, not an empty-prefix search hack:

```ts
export interface ObjectListQuery {
    readonly schema?: string;
    readonly kinds?: readonly LangObjectKind[];
    readonly prefix?: string;
    readonly limit?: number;
    readonly includeSystem?: boolean;
}

listObjects(query: ObjectListQuery): readonly LangObjectInfo[];
```

If implemented by `searchObjects`, tests must prove empty-prefix listing is fast and complete for large catalogs.

### 8.3 Section readiness

```ts
export type MetadataSectionState =
    | "absent"
    | "loading"
    | "ready"
    | "stale"
    | "partial"
    | "failed"
    | "permissionDenied"
    | "unsupported"
    | "lite";
```

Empty arrays mean ready-empty only when the section state is `ready`.

---

## 9. Object details roadmap

OE v2 and scripting need more than completion metadata.

### 9.1 Required for useful OE v2

| Detail | Consumer | Notes |
|---|---|---|
| PK/unique constraint names | OE key nodes, scripting | H4 currently marks PK columns, but names are needed. |
| FK names and column pairs both directions | OE FK nodes, join suggestions | Reverse edges should include column pairs too. |
| Identity seed/increment | scripting | H3 has identity flag only. |
| Computed column definition | scripting | lazy read acceptable. |
| Default/check constraints | OE and scripting | include names and definitions. |
| Indexes | OE and scripting | key order, included columns, filter, uniqueness, clustering. |
| Module definitions | scripting and definition | include encrypted/permission unavailable states. |
| Extended properties/descriptions | hover/OE properties | H7 planned in language doc. |

### 9.2 Later parity

- Triggers;
- statistics;
- permissions;
- database principals and roles;
- server logins and server roles;
- synonyms target metadata;
- temporal, ledger, graph, memory-optimized, external tables;
- row counts;
- dependencies;
- SQL Agent/jobs if product wants native server folders.

Each section must have readiness/failure states.

---

## 10. Refresh and drift

### 10.1 Refresh scopes

```ts
export type MetadataRefreshRequest =
    | { kind: "server"; key: ServerKey; reason?: MetadataRefreshReason }
    | { kind: "database"; key: DatabaseKey; reason?: MetadataRefreshReason }
    | { kind: "object"; key: ObjectKey; sections?: readonly ObjectDetailSection[]; reason?: MetadataRefreshReason }
    | { kind: "allForProfile"; profileFingerprint: string; reason?: MetadataRefreshReason };
```

### 10.2 Drift notifications

```ts
export interface MetadataDriftNotification {
    readonly profileFingerprint: string;
    readonly database?: string;
    readonly text?: string;
    readonly succeeded: boolean;
    readonly source: "queryStudio" | "classicEditor" | "objectExplorerV2" | "scripting" | "unknown";
}
```

Rules:

- DDL sniffing accelerates refresh.
- Digest polling is the backstop.
- Classic editor and legacy commands should notify the store once easy hooks exist.
- Failed drift checks are skipped, not retried in tight loops.

### 10.3 Generations

- Server catalog generation is separate from database catalog generation.
- Database catalog generation is separate from object detail generation if details are lazy.
- Pinned views must never mix generations inside a single feature response.

---

## 11. Cache policy

### 11.1 Memory cache

- Refcount leases by server/database/object key.
- Keep warm snapshots for recently used databases with LRU eviction.
- Do not keep unlimited catalogs for every database on large servers.
- Release sessions when refcounts drop and idle TTL expires.

### 11.2 Disk cache, later

Disk cache is useful but not required for first OE v2 preview.

If implemented:

- store only classified metadata;
- encrypt or respect extension storage policy if needed;
- include server/profile fingerprint, database, generation timestamp, engine version, schema version;
- invalidate on digest mismatch and explicit refresh;
- never cache secrets or SQL text.

---

## 12. Provider adapters

### 12.1 Language provider adapter

`CatalogLanguageMetadataProvider` should move from a Query Studio host handle to a `DatabaseCatalogLease` host.

```ts
new CatalogLanguageMetadataProvider({
    handle: () => databaseLease.currentHandle(),
    serverVersion: () => serverLease.pin().serverInfo?.serverVersion,
    currentDatabase: () => databaseKey.database,
    databases: () => serverLease.pin().listDatabases()?.map(d => d.name),
    subscribeStatus: listener => databaseLease.onDidChange(listener),
});
```

### 12.2 OE v2 facade

OE v2 can have a convenience facade over store leases, but it should not invent a separate metadata truth source.

### 12.3 Scripting detail reader

`SqlScriptingService` can consume object detail leases directly when it needs richer information than the language-provider seam exposes.

---

## 13. Observability and privacy

Events/spans:

```text
metadataStore.prepareProfile
metadataStore.acquireServer
metadataStore.acquireDatabase
metadataStore.acquireObjectDetails
metadataStore.refresh
metadataStore.disposeLease
metadataStore.session.open
metadataStore.session.close
metadataStore.hydrate.server
metadataStore.hydrate.database
metadataStore.hydrate.objectDetails
metadataStore.drift.detected
metadataStore.cache.hit
metadataStore.cache.miss
metadataStore.keyCorrectness.violation
```

Allowed fields:

- key kind;
- short profile fingerprint;
- database classification, not raw name by default unless allowed;
- section names;
- readiness state;
- generation;
- counts;
- duration;
- backend kind;
- error code/class.

Disallowed fields:

- SQL text;
- rows;
- raw connection strings;
- passwords;
- tokens;
- raw server endpoints;
- unclassified object names.

Privacy canaries must assert that diagnostics do not leak secrets.

---

## 14. Tests

### 14.1 Unit tests

- profile fingerprint stability and secrecy;
- key normalization;
- server catalog readiness mapping;
- database catalog readiness mapping;
- section failed versus ready-empty;
- lease refcounting;
- memory cache eviction;
- generation monotonicity;
- provider adapter behavior;
- import-boundary rules.

### 14.2 Key-correctness tests

- fake database A and B with distinct objects;
- acquire A and B concurrently;
- force refresh A while B is hydrating;
- ensure no cross-contamination;
- run digest polling for both.

### 14.3 Fake data-plane tests

- server catalog query success/failure;
- database catalog hydrate success/partial/failure;
- one-active-query-per-session backend behavior;
- lost session handling;
- session disposal on lease release.

### 14.4 Integration tests

- Query Studio consumes store-backed metadata.
- Native language service consumes store-backed provider.
- OE v2 expands using store leases.
- Classic metadata backend consumes store leases.
- Scripting reads object details.

### 14.5 Perf tests

```text
metadataStore.acquireServer.warm
metadataStore.acquireDatabase.warm
metadataStore.hydrateDatabase.cold
metadataStore.listObjects.10k
metadataStore.getColumns.150k
metadataStore.refreshAfterDdl
metadataStore.disposeIdle
```

---

## 15. Implementation plan

### MD-0: Profile/auth/fingerprint helpers

Work:

1. Extract stable profile fingerprint helper from Query Studio.
2. Extract auth provider helper from Query Studio/connection store seam.
3. Add privacy tests.
4. Make Query Studio use the helper without behavior change.

Exit criteria:

- No secrets in fingerprints.
- Query Studio still connects.

### MD-1: Store shell and lease model

Work:

1. Add `IMetadataStore` interface.
2. Add server/database/object lease interfaces.
3. Add refcount/dispose mechanics.
4. Add status model and diagnostics.

Exit criteria:

- Store can return fake leases in tests.
- No feature behavior changes yet.

### MD-2: Key-correct database acquisition

Work:

1. Implement preview-safe per-database metadata session source or key-aware source.
2. Adapt current `MetadataService` behind `DatabaseCatalogLease`.
3. Add two-database isolation tests.

Exit criteria:

- Database A and B never cross-contaminate.
- Existing metadata hydrations still work.

### MD-3: ServerMetadataService

Work:

1. Add server catalog queries through data plane.
2. Model visible database list and readiness.
3. Add failure/partial/permission states.
4. Add store server leases.

Exit criteria:

- OE v2 can list databases without Query Studio host seam.
- Query Studio `databases()` can move to server catalog.

### MD-4: Move Query Studio and language provider to store

Work:

1. Make `DocumentSessionBinding` acquire metadata through `IMetadataStore`.
2. Make `CatalogLanguageMetadataProvider` consume database leases.
3. Preserve current language-service behavior.

Exit criteria:

- Query Studio metadata behavior unchanged or better.
- Provider generation/readiness tests green.

### MD-5: OE v2 required object metadata

Work:

1. Add PK names and reverse FK column pairs.
2. Add object list API.
3. Add section state API for OE.
4. Validate large-catalog object listing.

Exit criteria:

- OE v2 can render database folders and child details.

### MD-6: Object details for scripting and parity

Work:

1. Add indexes.
2. Add constraints.
3. Add module definitions.
4. Add computed/default/check definitions.
5. Add extended properties/descriptions.

Exit criteria:

- TypeScript scripting can produce useful CREATE/ALTER scripts.

### MD-7: Cache and scaling

Work:

1. Add memory LRU.
2. Add idle session TTL.
3. Add optional disk cache design/implementation.
4. Add perf probes.

Exit criteria:

- Large-server dogfood is responsive.
- Session pressure is bounded.

---

## 16. Acceptance gates for OE v2 dependency

OE v2 should not claim metadata-native correctness until:

- server catalog exists;
- database acquisition is key-correct;
- database A/B isolation test is green;
- provider adapter returns pinned consistent generations;
- failed sections are never represented as empty;
- refresh works at server and database scopes;
- leases dispose sessions/listeners;
- privacy canaries pass;
- Query Studio still works through the same store.

---

## 17. Final instruction for the coding agent

Do not bolt OE v2 onto the current per-document metadata helper. Build a shared MetadataStore. Keep SQL Data Plane as the only connection/query layer. Make database acquisition key-correct before rendering any multi-database tree. Add server catalog as a first-class service. Keep `MetadataService` as the database-catalog engine if useful, but put it behind leases and a store that can serve all features. Pin once per response, publish honest readiness, and never let a failed catalog become an empty folder.
