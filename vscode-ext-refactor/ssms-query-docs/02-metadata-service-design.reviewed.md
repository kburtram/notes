# Metadata Service — Technical Design, reviewed v2

**Component:** `MetadataService` in the vscode-mssql extension host, with an isomorphic read-model core where practical.  
**Depends on:** the SQL data-plane adapter described in `03-sts2-client-adapter-design.reviewed.md`.  
**Consumed by:** Query Studio, AI inline completions, classic editor completions, Object Explorer fast paths, Table Designer / Schema Visualizer bootstrap, future metadata-native LSP.  
**Status:** proposed design, reviewed and tightened for implementation planning.

---

## 0. What changed in this reviewed version

The original design correctly centered the service on immutable catalog snapshots, synchronous reads, drift detection, disk cache, and a projection layer for completions. This version keeps that spine and strengthens several seams that would otherwise become reliability or privacy traps:

1. **Server-level metadata is explicit.** Query Studio needs database lists and server identity before a database catalog is hydrated. This design adds a `ServerCatalog` alongside `DatabaseCatalog`.
2. **Session strategy is no longer one-size-fits-all.** Borrowing the user's query session is correct for seeing the current context, but risky for background hydration and polling. Query Studio should prefer a dedicated background metadata session when available, while still supporting borrowed-session fallback.
3. **AI schema context is treated as outbound user data.** Object names and schema shape are not result rows, but sending them to a remote model is still a privacy boundary. The projection API now carries explicit policy and provenance.
4. **Drift detection is tiered.** The prior checksum query was intentionally cheap, but could miss column/parameter/constraint changes. This design introduces cheap and deep digests, scoped refresh, and explicit false-negative posture.
5. **Large catalog behavior is more concrete.** Metadata-lite mode, on-demand object details, and user-visible readiness states are specified so pathological catalogs degrade honestly.
6. **LSP overlay requirements are reserved earlier.** Temporary tables, CTEs, aliases, and in-script DDL overlays are not implemented in v1, but the snapshot API leaves room for them.
7. **Testing expands around real SQL Server edge cases:** permissions, Azure SQL, case-sensitive collations, synonyms, encrypted definitions, metadata visibility, and cache corruption.

One sentence remains the north star: **connect once, then every “what objects, columns, keys, and relationships exist?” question is answered from a stable local snapshot, with observable freshness and honest degradation.**

---

## 1. Purpose

`MetadataService` provides a shared, cache-backed, observable source of schema truth for vscode-mssql features. It replaces scattered per-feature catalog fetching with one pipeline that hydrates, indexes, projects, refreshes, and caches SQL Server metadata.

It should answer these questions fast and consistently:

- Which databases are visible on this server?
- Which schemas, objects, columns, types, keys, constraints, relationships, routines, parameters, and synonyms are visible in this database?
- Given a name near a cursor, what object does it resolve to?
- Given a table, what are its columns and key relationships?
- Given a token budget, what compact schema context should an AI completion request receive?
- Has the catalog changed since the last snapshot?
- Which generation of metadata did a feature use when it made a decision?

### 1.1 Non-goals

- Not an authoring model. DacFx/DesignServices remain authoritative for designer edit sessions and publish diffs. MetadataService may bootstrap designers, not publish from its snapshot.
- Not a permissions engine. It reflects catalog visibility for the connected principal. It does not decide authorization.
- Not a data cache. It never stores table rows.
- Not a module-definition bulk store. Definitions are lazy and governed.
- Not the language service itself. It is the substrate for a future metadata-native binder.
- Not a cross-server catalog federation service.
- Not a replacement for Object Explorer's full tree semantics. It provides fast-path structural facts; OE can still call specialized services for advanced nodes.

---

## 2. Position in the architecture

```text
                         Consumers
  Query Studio · AI completions · classic editor · OE fast paths · designers
                         │ sync reads / async projections / change events
                         ▼
┌───────────────────────────────────────────────────────────────────────┐
│ MetadataService                                                        │
│  ServerCatalogs · DatabaseCatalogs · immutable snapshots · indexes     │
│  drift detection · disk cache · schema-context projection · diag       │
└───────────────────────────────▲───────────────────────────────────────┘
                                │ catalog T-SQL through domain API
┌───────────────────────────────┴───────────────────────────────────────┐
│ SQL data-plane adapter                                                  │
│  STS2 JSON-RPC today · STS2 HTTP/WebSocket or hosted REST later         │
└───────────────────────────────────────────────────────────────────────┘
```

Rules:

1. **MetadataService never imports a transport binding.** It calls the adapter's domain API, not JSON-RPC or HTTP directly.
2. **Snapshots are immutable.** Refresh creates a new generation. Consumers can pin a generation for a document version, completion event, or LSP pass.
3. **Background work must not make F5 feel slow.** Hydration and polling use background priority and, for Query Studio, a dedicated session where possible.
4. **Every readiness state is explicit.** A consumer must distinguish absent, loading, ready, failed, partial, lite, and stale.
5. **Projection is a product feature boundary.** Building prompt context is not just formatting. It is a policy-controlled export of metadata.

---

## 3. Requirements

### 3.1 Functional requirements

| ID | Requirement |
|---|---|
| F1 | Hydrate visible server databases into a `ServerCatalogSnapshot`. |
| F2 | Hydrate database schemas, objects, synonyms, columns, types, keys, foreign keys, indexes, constraints, parameters, and optional descriptions into immutable `CatalogSnapshot`s. |
| F3 | Serve synchronous lookups by object ID, name, schema, prefix, kind, and relationship. |
| F4 | Support progressive readiness: object names can be ready before columns, columns before relationships. |
| F5 | Detect drift through DDL sniffing, database-context events, explicit refresh, and polling. |
| F6 | Refresh affected slices incrementally when practical; fall back to full rebuild when cheaper or safer. |
| F7 | Build deterministic, budgeted schema-context projections for AI completions and future LSP features. |
| F8 | Persist validated snapshots to local disk for warm start. |
| F9 | Provide observability events, perf markers, and provenance fields including `catalogGeneration`. |
| F10 | Degrade gracefully for huge catalogs without blocking the editor. |

### 3.2 Performance targets

These are gates for local SQL Server / STS2 stdio scenarios, not promises for every network:

| Target | Goal |
|---|---:|
| Cold hydrate, WideWorldImporters-class DB, names+columns ready | < 1.5 s |
| Cold hydrate, full structural catalog | < 3 s |
| Warm cache validate and ready | < 150 ms to serve cached snapshot, validation in flight |
| Sync snapshot read p99 | < 100 µs |
| Prefix search over 10k objects | < 2 ms |
| `buildSchemaContext(balanced)` p95 from warm snapshot | < 15 ms |
| Memory for 10k objects / 150k columns | < 30 MB resident |
| Poll query normal cost | single-row or small aggregate, skipped under user query pressure |

### 3.3 Privacy requirements

- Result rows never enter metadata snapshots.
- Module definitions are lazy and never included in diagnostics, disk manifests, or AI schema context by default.
- Object names and schema shape are stored locally and may appear in metadata diagnostics under the product's metadata classification policy.
- Sending schema context to a remote LM provider is controlled by the completions feature's user consent/configuration and is logged as metadata export provenance, not as default diagnostic capture.
- Disk cache is local, user-controlled, clearable, versioned, and excluded from debug/perf export bundles unless explicitly requested under policy.

---

## 4. Identity model

Metadata visibility depends on server, database, principal, and important connection options. Do not key snapshots only by hostname and database name.

```ts
export interface ServerKey {
  /** Digest of normalized server endpoint, instance/port, auth principal, tenant, and visibility-affecting options. */
  serverFingerprint: string;
}

export interface CatalogKey extends ServerKey {
  database: string;
  /** Optional when available. Helps survive rename/case collisions and cache validation. */
  databaseId?: number;
  /** Captured for resolution/search behavior and cache provenance. */
  collationName?: string;
}
```

Fingerprint inputs should include:

- normalized server/instance/port;
- auth kind and principal digest, never raw username/password/token;
- tenant/account digest for AAD;
- trust/encryption flags only if they can affect endpoint identity or visibility;
- service/adapter backend kind for compatibility if semantics differ.

Two Query Studio tabs connected to the same server/database/principal should share the same catalog state. Different principals do not share because metadata visibility can differ.

---

## 5. Public API

### 5.1 Service entry point

```ts
export interface MetadataService {
  acquireServer(session: ISqlSession, opts?: AcquireServerOptions): Promise<ServerCatalogHandle>;
  acquireDatabase(session: ISqlSession, opts?: AcquireDatabaseOptions): Promise<CatalogHandle>;

  peekServer(key: ServerKey): ServerCatalogSnapshot | undefined;
  peekDatabase(key: CatalogKey): CatalogSnapshot | undefined;

  clearCache(scope?: { server?: ServerKey; database?: CatalogKey }): Promise<void>;
}
```

### 5.2 Server catalog

```ts
export interface ServerCatalogHandle extends Disposable {
  readonly key: ServerKey;
  current(): ServerCatalogSnapshot;
  readonly onDidChange: Event<ServerCatalogChangeEvent>;
  readonly onStatus: Event<MetadataStatusEvent>;
  refresh(): Promise<ServerCatalogSnapshot>;
}

export interface ServerCatalogSnapshot {
  readonly key: ServerKey;
  readonly generation: number;
  readonly capturedAtUtc: string;
  readonly readiness: "absent" | "loading" | "ready" | "failed" | "stale";
  readonly serverInfo?: { version?: string; engineEdition?: string; defaultCollation?: string };

  listDatabases(opts?: { includeSystem?: boolean; onlyAccessible?: boolean }): readonly DatabaseInfo[];
  getDatabase(name: string): DatabaseInfo | undefined;
  searchDatabases(prefix: string, limit?: number): readonly DatabaseInfo[];
}

export interface DatabaseInfo {
  name: string;
  databaseId?: number;
  stateDesc?: string;
  isReadOnly?: boolean;
  collationName?: string;
  compatibilityLevel?: number;
  userAccessDesc?: string;
}
```

`ServerCatalog` powers the Query Studio database combo. It is intentionally smaller than a database catalog and can hydrate quickly after connect.

### 5.3 Database catalog handle

```ts
export type CatalogSection =
  | "schemas"
  | "objects"
  | "synonyms"
  | "columns"
  | "types"
  | "keys"
  | "foreignKeys"
  | "indexes"
  | "constraints"
  | "parameters"
  | "descriptions"
  | "rowCounts";

export interface CatalogHandle extends Disposable {
  readonly key: CatalogKey;
  current(): CatalogSnapshot;
  readonly onDidChange: Event<CatalogChangeEvent>;
  readonly onStatus: Event<MetadataStatusEvent>;

  refresh(scope?: RefreshScope): Promise<CatalogSnapshot>;
  notifyExecutedBatch(input: ExecutedBatchNotification): void;
  buildSchemaContext(req: SchemaContextRequest): SchemaContextResult;

  /** Optional v1.5 seam for future metadata-native LSP. */
  withOverlay?(overlay: CatalogOverlay): CatalogSnapshotView;
}

export interface ExecutedBatchNotification {
  textDigest: string;
  /** Full text only when caller already has it in memory; service must not log it. */
  text?: string;
  databaseAtStart: string;
  databaseAtEnd?: string;
  succeeded: boolean;
  hadErrors: boolean;
}
```

### 5.4 Snapshot read surface

```ts
export interface CatalogSnapshot {
  readonly key: CatalogKey;
  readonly generation: number;
  readonly capturedAtUtc: string;
  readonly digest: CatalogDigest;
  readonly readiness: Readonly<Record<CatalogSection, SectionState>>;
  readonly mode: "full" | "lite" | "partial";
  readonly stats: CatalogStats;

  getObject(ref: ObjectRef | number): ObjectInfo | undefined;
  resolveName(parts: NamePart[], ctx?: ResolveContext): Resolution;
  getColumns(objectId: number): readonly ColumnInfo[];
  getIndexes(objectId: number): readonly IndexInfo[];
  getPrimaryKey(objectId: number): KeyInfo | undefined;
  getUniqueKeys(objectId: number): readonly KeyInfo[];
  getForeignKeysFrom(objectId: number): readonly FkEdge[];
  getForeignKeysTo(objectId: number): readonly FkEdge[];
  getParameters(objectId: number): readonly ParameterInfo[];
  getSynonymTarget(objectId: number): SynonymTarget | undefined;
  search(prefix: string, opts?: SearchOptions): readonly ObjectRef[];
  listSchemas(): readonly SchemaInfo[];
  listObjects(schema?: string, kinds?: ObjectKind[]): readonly ObjectRef[];

  /** Lazy, policy-governed, never bulk-loaded. */
  getDefinition(objectId: number, opts?: DefinitionReadOptions): Promise<DefinitionResult>;
}

export type SectionState = "absent" | "loading" | "ready" | "failed" | "stale" | "lite";
```

`Resolution` must distinguish:

```ts
type Resolution =
  | { kind: "resolved"; objectId: number; confidence: "exact" | "synonym" | "defaultSchema" }
  | { kind: "ambiguous"; candidates: readonly ObjectRef[] }
  | { kind: "notFound" }
  | { kind: "sectionUnavailable"; section: CatalogSection }
  | { kind: "crossDatabaseUnhydrated"; database: string };
```

---

## 6. Data model and storage layout

### 6.1 Object coverage

Hydrate these in v1:

| Category | Types / sources | Notes |
|---|---|---|
| Schemas | `sys.schemas` | Include user schemas and useful built-ins. |
| Objects | tables, views, procedures, scalar functions, inline/table-valued functions | Core completion and LSP substrate. |
| Synonyms | `sys.synonyms` + object row | Store `base_object_name`; chase depth 1 by default. |
| Columns | `sys.columns` + `sys.types` | Tables, views, table-valued functions. |
| Types | `sys.types` | Include alias/user-defined types enough for display/completions. |
| Keys | PK/UQ constraints + index columns | Preserve column order. |
| FKs | `sys.foreign_keys` + `sys.foreign_key_columns` | Both adjacency directions. |
| Indexes | `sys.indexes` + `sys.index_columns` | Useful for designers/OE and future LSP ranking; can be lite. |
| Constraints | defaults/checks, basic names/parent columns | Definitions lazy or redacted. |
| Parameters | `sys.parameters` + types | Routines. |
| Descriptions | `sys.extended_properties` `MS_Description` | Optional, default on unless permissions/cost fail. |
| Row counts | `sys.dm_db_partition_stats` | Optional enrichment, off by default. |

Consider for v1.5 or v2:

- sequences;
- triggers;
- table types and TVP details;
- security policies;
- temporal/ledger metadata;
- computed-column definitions;
- graph/external table specifics;
- full-text indexes.

The service should not block v1 on every exotic object, but the data model should tolerate future kinds without breaking cache format.

### 6.2 Structure-of-arrays storage

Use flat arrays and symbol tables rather than nested object graphs.

- String table interns schema names, object names, column names, type names, descriptions.
- Object table: objectId, schemaId, nameSym, kind, modifyDate, createDate, flags.
- Column table grouped by object: objectId → `[start,len)`, with ordinal, nameSym, typeSym, length/precision/scale, flags.
- Relationship tables: keys, FK edges, FK column-pair arrays, indexes, index-column arrays.
- Name index: sorted case-folded keys plus raw symbols.
- Prefix index: binary search over folded keys.

Reason: p99 synchronous reads and predictable memory.

### 6.3 Collation and case sensitivity

Search can use invariant folding for speed, but exact resolution must not lie in case-sensitive databases.

Policy:

- Store database collation name.
- Exact `resolveName` first compares according to a simple collation capability flag: case-sensitive collations require raw comparison before accepting a folded match.
- If folded search returns multiple raw candidates that differ only by case, return `ambiguous` rather than guessing.
- A future collation-faithful comparator may improve this; do not over-engineer it for v1.

---

## 7. Hydration pipeline

Hydration is progressive. Each step emits status and readiness.

### 7.1 Server hydration

| Step | Section | Query intent |
|---|---|---|
| S0 | serverInfo | Version, edition, server collation when cheap. |
| S1 | databases | Visible databases from `sys.databases`, filtered by online/accessibility. |

S1 powers Query Studio's database combo. It should complete quickly and should not wait for full database metadata.

### 7.2 Database hydration

| Step | Sections | Intent |
|---|---|---|
| H1 | schemas | Schema table and defaults. |
| H2 | objects + synonyms | Objects, kinds, create/modify dates, synonym base names. Publish `objects` readiness. |
| H3 | types + columns | Column details for tables/views/TVFs. Publish `columns` readiness. |
| H4 | keys + indexes + constraints | PK/UQ/index/basic constraint membership. |
| H5 | foreignKeys | FK graph and column pairs. |
| H6 | parameters | Routine parameters. |
| H7 | descriptions | Extended properties, optional. |
| H8 | rowCounts | Optional enrichment for ranking/OE. Off by default. |

Hydration queries execute through `ISqlSession.execute` with `priority: "background"`, `tag: "metadata:Hn"`, and page-size hints tuned for catalog results.

### 7.3 Streaming build

The builder consumes adapter pages directly. It appends into growable typed arrays, interns strings, and publishes snapshots only at safe section boundaries. It should not materialize entire catalog query results into JS arrays first.

### 7.4 Cancellation and budgets

Defaults:

- per-step wall budget: 20 s;
- total hydration budget: 60 s;
- idle cancellation when all handles disposed;
- background work cancelled if the owning session is lost.

If a section fails, publish the snapshot with that section `failed` instead of pretending it is empty. Consumers must handle this explicitly.

### 7.5 Large-catalog modes

Thresholds, configurable:

- `mssql.metadata.limits.maxObjects`: 25,000;
- `mssql.metadata.limits.maxColumns`: 500,000.

Modes:

| Mode | Behavior |
|---|---|
| `full` | All core sections hydrated. |
| `lite` | Object names/kinds/schemas hydrated, columns on-demand for top schemas or focused objects. |
| `partial` | Some sections failed or timed out. Snapshot remains usable with readiness states. |

Expose lite/partial in status UI and events. AI completions should degrade to name-only or focused-object-only context rather than blocking.

---

## 8. Session strategy

The first design recommended borrowed sessions by default. That is attractive because it avoids extra connections, but it can contend with user execution and can run inside session state the user did not intend metadata machinery to touch.

### 8.1 Strategies

| Strategy | Pros | Cons | Recommended use |
|---|---|---|---|
| Borrowed document session | Same principal, same current DB, sees session-local context; no extra connection | Contends with F5; can be blocked by user query/transaction; metadata SET/query noise shares session; polling may surprise | Fallback, explicit refresh, transaction-local probes, web hosts with no second session |
| Dedicated metadata session | Does not block user query; safe for polling/hydration; can be lower priority; cleaner cancellation | Extra connection; may not see uncommitted session-local DDL; auth/token renewal complexity | Query Studio default when adapter can open same profile |
| Hybrid | Dedicated for hydrate/poll, borrowed for `DB_NAME()`/current context and explicit user-triggered refresh | More lifecycle complexity | Recommended product policy |

### 8.2 Recommended v1 policy

- Query Studio opens a dedicated metadata session after the main STS2 session succeeds, unless `mssql.metadata.dedicatedSession` is false or backend cannot support it.
- Hydration, polling, cache validation, and `getDefinition` use dedicated metadata session.
- Database context changes are signaled by Query Studio from the main session; MetadataService reacquires the relevant catalog.
- DDL sniff receives executed batch notification from Query Studio and schedules refresh on the metadata session.
- If dedicated session fails, fall back to borrowed background queue with clear status: `metadata: background shared with query session`.

This policy keeps editor responsiveness above connection-count purity. A single digest poll should never lurk between the user and F5 like a very small troll under a very expensive bridge.

---

## 9. Drift detection and refresh

Three triggers feed one refresh engine.

### 9.1 Trigger A — DDL sniff

`notifyExecutedBatch` receives a text digest and, when available, the batch text already in memory. The service must never log the full text.

Use a lightweight lexer shared with Query Studio's batch splitter:

- comments;
- nested block comments;
- strings;
- bracketed identifiers;
- quoted identifiers treated conservatively.

Detect leading statement patterns:

- `CREATE|ALTER|DROP TABLE|VIEW|PROC|PROCEDURE|FUNCTION|SYNONYM|SCHEMA|INDEX|TRIGGER|TYPE|SEQUENCE`;
- `sp_rename`;
- `ALTER AUTHORIZATION` / schema transfer if easy;
- unknown `EXEC` with possible dynamic SQL → schedule cheap digest check, not full refresh.

Sniffing accelerates refresh. It is not the correctness backstop.

### 9.2 Trigger B — digest poll

While handles are alive, poll at `mssql.metadata.pollSeconds` (default 60) only when the metadata session is idle. If using borrowed session, skip when user query is active. Skipped polls are not queued.

Digest tiers:

| Tier | Cost | Contents | Use |
|---|---|---|---|
| Cheap | one or a few aggregate rows | object count, object modify-date checksum/hash, column count, parameter count | frequent poll |
| Structural | aggregates over columns, FKs, params, indexes | detects more non-object-date changes | after sniff, manual refresh, cache validation mismatch |
| Full H2 diff | object rows | computes added/removed/modified ids | refresh planning |

Do not oversell `CHECKSUM_AGG` as perfect. It is a trigger heuristic. Manual refresh always exists. For stronger detection where supported, prefer stable `HASHBYTES` over deterministic concatenations, but be mindful of compatibility and cost.

### 9.3 Trigger C — explicit refresh

Commands:

- `MSSQL: Refresh metadata for current connection`;
- Query Studio status-bar refresh action;
- Object Explorer refresh can notify MetadataService;
- test/perftest refresh step.

Manual refresh may request full rebuild.

### 9.4 Delta computation

Refresh algorithm:

1. Run H2 object identity/modify-date rows.
2. Diff object IDs and names against current snapshot.
3. Classify added, removed, modified, maybe-renamed.
4. For affected IDs, rerun H3–H7 scoped by `WHERE object_id IN (...)`, chunked safely.
5. If affected set >30% of catalog, or a schema/type-level change makes scoping suspect, full rebuild.
6. Publish new snapshot generation with delta.

Deltas are advisory. Consumers may treat any generation bump as “re-read what you care about.”

### 9.5 Database context changes

When the document session changes database:

- Query Studio emits database change to MetadataService.
- Existing handle reacquires for the new `CatalogKey`.
- Old catalog remains warm under idle TTL.
- ServerCatalog remains shared.

### 9.6 Cross-database references

`resolveName(["OtherDb","dbo","T"])`:

- if a resident catalog for `OtherDb` exists, delegate;
- otherwise return `crossDatabaseUnhydrated`;
- do not silently hydrate other databases in completions v1.

---

## 10. Schema-context projection

The completions branch's compaction logic moves here and becomes a stable projection service.

### 10.1 Request/response

```ts
export interface SchemaContextRequest {
  budget: "tight" | "balanced" | "generous" | "unlimited" | { maxChars: number };
  focus?: { objectIds?: number[]; nameHints?: string[]; textDigest?: string; text?: string };
  format: "prompt-text" | "structured-json";
  include?: { fkTwoHop?: boolean; routines?: boolean; descriptions?: boolean; rowCounts?: boolean };
  privacy: { destination: "local" | "remoteLm"; policyId: string; allowObjectNames: boolean };
}

export interface SchemaContextResult {
  text: string;
  charCount: number;
  objectsIncluded: number;
  cacheKey: string;
  catalogGeneration: number;
  truncated: boolean;
  degraded?: "catalogNotReady" | "liteMode" | "privacyPolicy" | "sectionFailed";
  composition: { tables: number; views: number; routines: number; columnsElided: number };
}
```

If `privacy.allowObjectNames` is false for `remoteLm`, the result should either be empty/degraded or use a future anonymized representation. Do not invent silent pseudonymization in v1.

### 10.2 Deterministic selection

1. Seed from explicit object IDs, resolved name hints, and lexed names from focus text.
2. Expand FK one hop; two hops for Generous if budget allows.
3. Fill by importance: referenced-by-FK count, optional row count, kind priority, name asc.
4. Render at fidelity tiers: full columns/types/keys → column names only → object names only.
5. Degrade from the tail until budget fits.
6. Sort output deterministically: schema asc, object asc.

The same request against the same catalog generation must produce byte-identical output. Replay comparisons depend on this.

### 10.3 Caching

Memoize per `(catalogGeneration, normalizedRequestDigest, privacyPolicyId)` with a small LRU. Generation bump invalidates naturally. Log only cache keys, counts, and budget metadata, not prompt text.

---

## 11. Disk cache

Location:

```text
<globalStorage>/metadata-cache/<serverFingerprint>/<safe-database-key>/
  manifest.json
  catalog.mdc
```

Manifest:

```json
{
  "formatVersion": 2,
  "createdBy": "vscode-mssql",
  "serverFingerprint": "sha256:...",
  "database": "Sts2TestDb",
  "databaseId": 7,
  "collationName": "SQL_Latin1_General_CP1_CI_AS",
  "digest": {},
  "capturedAtUtc": "...",
  "sections": ["schemas", "objects", "columns", "keys", "foreignKeys"],
  "privacy": { "containsDefinitions": false, "containsRows": false }
}
```

Rules:

- Load cache optimistically to serve warm reads, but immediately validate digest.
- UI/status should say `metadata cache validating` until validation completes.
- If digest matches, emit `cacheValidated`.
- If digest mismatches, run delta refresh from cached snapshot.
- Corrupt cache: discard, emit status, hydrate cold.
- Format version bump discards.
- Retention LRU capped by `mssql.metadata.cacheMaxMB` default 200.
- `MSSQL: Clear metadata cache` deletes.

Privacy:

- Cache contains names and structural metadata.
- No definitions by default.
- No row data ever.
- Local file permissions rely on VS Code/globalStorage environment. Document this honestly; do not imply OS credential vault protection.

---

## 12. Future metadata-native LSP seam

Reserve these behaviors now:

- **Snapshot pinning:** bind a document version against one `CatalogSnapshot` generation.
- **Ephemeral overlays:** temp tables, table variables, CTEs, aliases, derived tables, and in-script DDL appear as overlay objects.
- **Default schema and database context:** binder supplies current database, default schema, and batch start context.
- **Allocation-light reads:** binder can call `resolveName`, `getColumns`, `getParameters`, `search` repeatedly without async waits.
- **Delta-driven invalidation:** bindings keyed by referenced object IDs can be selectively invalidated.

Sketch:

```ts
export interface CatalogOverlay {
  temporaryObjects?: EphemeralObject[];
  ctes?: EphemeralObject[];
  aliases?: AliasBinding[];
  scriptDdl?: EphemeralObject[];
}

export interface CatalogSnapshotView extends CatalogSnapshot {
  readonly baseGeneration: number;
  readonly overlayId: string;
}
```

Do not implement a parser in this service. The future LSP owns parsing and overlays.

---

## 13. Observability

Events flow through the unified diagnostics substrate and classification policy.

| Event | Kind | Important attrs |
|---|---|---|
| `mssql.metadata.serverHydrate` | begin/end marker | databaseCount, cacheHit, error/reason |
| `mssql.metadata.hydrate` | begin/end marker | objectCount, columnCount, bytesApprox, mode, cacheHit |
| `metadata.step.H1..H8` | span | rows, ms, section, failed |
| `metadata.digestPoll` | span | tier, changed, skippedReason |
| `metadata.refresh` | begin/end marker | reason, added, removed, modified, fullRebuild |
| `metadata.schemaContext.build` | span | budget, chars, objects, cacheHit, generation, degraded |
| `metadata.cache.load/save/validate` | span | bytes, valid, reason |
| `metadata.definition.read` | span | objectKind, allowed, cacheHit, resultKind |

Add `catalogGeneration` and `catalogKeyDigest` to trace identity optional fields so completions, LSP, Query Studio execution, and replay records can tie decisions back to schema truth.

### 13.1 Debug Console

V1 requires no bespoke metadata panel. Events appear in live trace/waterfall under feature bucket `metadata`. A later Catalog Inspector page can show:

- active catalogs;
- generation history;
- readiness;
- digest poll health;
- cache state;
- last deltas;
- large-catalog mode.

### 13.2 Perftest scenarios

- `metadata-server-hydrate` — connect, wait server catalog ready.
- `metadata-hydrate-cold` — clear cache, connect DB, wait columns/full ready.
- `metadata-hydrate-warm` — second run with cache.
- `metadata-drift-ddl` — create/alter/drop table, wait generation bump.
- `metadata-context-build` — repeated balanced projection p95.
- `querystudio-connect-with-metadata` — Query Studio connect, metadata nonblocking proof.

---

## 14. Failure and permission handling

| Failure | Behavior |
|---|---|
| Permission hides catalog rows | Snapshot reflects visible metadata. Correct by definition. |
| One section denied/errors | Mark section failed, continue. |
| Step timeout | Retry once with backoff; then failed section. |
| Dedicated metadata session fails | Fall back to borrowed session if configured; status warning. |
| Borrowed session busy | Skip background poll; do not queue behind user query unless explicit refresh. |
| Cache corrupt | Discard and hydrate cold. |
| Digest query denied | Disable polling for that catalog, rely on DDL sniff/manual refresh, status warning. |
| Azure SQL differences | Tolerate missing optional DMVs; do not treat optional row counts as failure. |
| Database offline/dropped | Mark catalog stale/unavailable, clear handle on next context update. |

Hydration messages go to diagnostics, not the user's Messages pane.

---

## 15. Settings and commands

| Setting | Default | Notes |
|---|---:|---|
| `mssql.metadata.enabled` | true for Query Studio/completions preview | Master gate. |
| `mssql.metadata.dedicatedSession` | true for Query Studio | Fallback to borrowed when unavailable. |
| `mssql.metadata.pollSeconds` | 60 | 0 disables polling. |
| `mssql.metadata.idleRetentionMinutes` | 10 | Time after last handle disposed. |
| `mssql.metadata.cacheEnabled` | true | Local structural cache. |
| `mssql.metadata.cacheMaxMB` | 200 | LRU cap. |
| `mssql.metadata.loadDescriptions` | true | H7 optional. |
| `mssql.metadata.loadRowCounts` | false | H8 optional. |
| `mssql.metadata.limits.maxObjects` | 25000 | Lite mode threshold. |
| `mssql.metadata.limits.maxColumns` | 500000 | Lite mode threshold. |
| `mssql.metadata.aiSchemaContext.enabled` | follows completions setting | Projection may still be local. |

Commands:

- `MSSQL: Refresh metadata for current connection`;
- `MSSQL: Clear metadata cache`;
- `MSSQL: Show metadata status`;
- `MSSQL: Open metadata cache folder` optional, behind advanced setting.

---

## 16. Testing plan

### 16.1 Unit tests

- Builder from fixture page streams.
- String interning and SoA indexes.
- Name resolution with default schema, quoted names, case-sensitive collisions.
- Prefix search and limits.
- Synonym target parsing and cycle/depth behavior.
- Delta computation for added/removed/modified/renamed objects.
- DDL sniffer corpus sharing Query Studio lexer.
- Projection determinism, budget monotonicity, elision accounting.
- Cache round-trip, corrupt/truncated files, version mismatch.
- Privacy canaries: definitions/rows absent from cache/diag/projection unless explicitly allowed.

### 16.2 SQL Server integration tests

- Permissions: low-privilege user sees only allowed rows.
- Azure SQL: optional DMV denial tolerated.
- Case-sensitive collation DB.
- Large catalog synthetic DB.
- Synonyms across schema/database.
- DDL drift: create/alter/drop table/view/proc/function/synonym/type/index.
- `sp_rename` object and column.
- Extended properties denied or absent.
- Dedicated session vs borrowed fallback.

### 16.3 Perf tests

- Cold/warm hydrate gates.
- Projection p95.
- Prefix search microbench.
- Large catalog lite mode memory.
- Query Studio connect not blocked by metadata.

### 16.4 Golden parity for completions

Before switching completions to this service, build a fixture catalog and compare old compactor output to `buildSchemaContext` output for Tight/Balanced/Generous/Unlimited. Any intentional difference must be recorded because it changes replay analysis.

---

## 17. Milestones

| Milestone | Scope | Exit gate |
|---|---|---|
| MD-0 | API skeleton, keys, status events, fake adapter fixtures | Unit tests for handles/readiness. |
| MD-1 | ServerCatalog + DB H1–H5 hydrate, dedicated/borrrowed session strategy | Query Studio db combo from ServerCatalog; cold hydrate works. |
| MD-2 | Drift detection: DDL sniff, digest poll, delta refresh | Engine tests for common DDL; generation deltas correct. |
| MD-3 | Disk cache and warm validation | Warm hydrate perf target met; corrupt cache tests. |
| MD-4 | Projection port from completions | Golden parity suite; completions consumes service. |
| MD-5 | Large catalog lite mode, optional indexes/descriptions/row counts, hardening | Memory targets and permission matrix green. |
| MD-6 | Perftest/debug integration | Scenarios registered and visible in Debug Console waterfalls. |

---

## 18. Open questions to decide before MD-1 exit

1. **Dedicated metadata session default:** this doc recommends true for Query Studio. Confirm connection-count impact with AAD and managed environments.
2. **Digest tier implementation:** choose exact SQL for cheap and structural digests based on SQL Server version support and cost.
3. **Descriptions default:** useful for AI/LSP, but metadata text may be longer and more sensitive than object names. Confirm default and projection policy.
4. **Synonym chase:** eager depth 1 recommended; deeper chase can cross database/server and should be explicit.
5. **Case-sensitive search:** invariant prefix search with ambiguity is recommended; do not claim collation-perfect search in v1.
6. **AI schema context privacy:** align wording and settings with the completions feature. Remote LM prompt composition should be user-visible and diagnosable.
7. **Definition reads:** decide whether any feature can request definitions in v1, and how that is classified.
8. **Cache storage:** confirm no encryption claim. Provide clear cache clear command.
9. **Metadata for Object Explorer:** decide which OE nodes can safely use snapshot fast paths and which must remain service-backed.
10. **Temp-table overlays:** reserve now, implement with future metadata-native LSP rather than bolting temp-table state into this service.

---

## Appendix A — Hydration query sketches

Exact query text should be pinned in implementation and tested against SQL Server versions. Sketches:

```sql
-- S1 databases
SELECT database_id, name, state_desc, is_read_only, collation_name,
       compatibility_level, user_access_desc
FROM sys.databases
WHERE state = 0
ORDER BY name;

-- H1 schemas
SELECT schema_id, name
FROM sys.schemas
WHERE name NOT IN ('INFORMATION_SCHEMA');

-- H2 objects and synonyms
SELECT o.object_id, o.schema_id, o.name, o.type, o.create_date, o.modify_date,
       s.base_object_name
FROM sys.objects o
LEFT JOIN sys.synonyms s ON s.object_id = o.object_id
WHERE o.is_ms_shipped = 0
  AND o.type IN ('U','V','P','FN','IF','TF','SN')
ORDER BY o.object_id;

-- H3 columns and types
SELECT c.object_id, c.column_id, c.name, t.name AS type_name,
       SCHEMA_NAME(t.schema_id) AS type_schema,
       c.max_length, c.precision, c.scale,
       c.is_nullable, c.is_identity, c.is_computed, c.is_rowguidcol
FROM sys.columns c
JOIN sys.types t ON t.user_type_id = c.user_type_id
JOIN sys.objects o ON o.object_id = c.object_id
WHERE o.is_ms_shipped = 0
  AND o.type IN ('U','V','TF','IF')
ORDER BY c.object_id, c.column_id;
```

Implementation should add H4–H8 with scoped variants for delta refresh.

## Appendix B — Digest posture

A cheap digest is a smoke alarm, not a courtroom transcript. The service should:

- use it to trigger deeper checks;
- expose `digestTier` in diagnostics;
- never claim impossible freshness;
- make manual refresh obvious;
- design perftest drift scenarios that prove real changes cause generation bumps.
