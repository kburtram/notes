# Client-side Metadata Cache and Drift Detection Design
## Persistent snapshot cache, scenario-aware freshness policies, and strict/live validation for MetadataStore consumers

**Status:** proposed design, 2026-07-06.  
**Target area:** `extensions/mssql/src/services/metadata/**`, with consumer integration in Query Studio, native language service, AI completions, Object Explorer v2, and TypeScript scripting.  
**Core idea:** load useful metadata instantly from a local persistent snapshot, serve consumers that tolerate stale data immediately, and validate or refresh before serving consumers that need correctness.

---

## 0. Executive summary

The existing metadata substrate already has the right runtime model: key-correct server/database leases, immutable generations, section readiness, cheap drift triggers, explicit refresh, and pin-once consumers. This design adds a persistent client-side cache and a formal freshness policy layer.

The cache must serve different consumers differently:

- **Completions** can use stale metadata immediately. A wrong suggestion is annoying, but SQL Server will reject invalid SQL at execution time.
- **AI schema context** can use cached structural metadata, as long as privacy gates and deterministic rendering stay intact.
- **Diagnostics** should not use stale metadata to assert binder errors. Stale data should suppress or downgrade metadata-backed diagnostics.
- **Object Explorer** should validate on the first expand, then reuse the validated generation for a short TTL so repeated expands are instant.
- **Scripting and create/alter generation** should use live or freshly validated metadata unless the user is explicitly in offline snapshot mode.

This design treats cache as a **published snapshot projection**, not as a second catalog model. A cache-loaded snapshot enters the same `MetadataStore` path as a live snapshot. Consumers still pin once, still respect readiness, and still never treat failure as empty.

---

## 1. Goals

| ID | Goal |
|---|---|
| C-G1 | Persist metadata snapshots locally so cold extension restarts can serve safe metadata requests quickly. |
| C-G2 | Add a scenario-aware freshness policy API: safe stale, require validated, require live, offline snapshot. |
| C-G3 | Preserve existing metadata invariants: pin once, immutable generations, key correctness, readiness honesty, failure not empty. |
| C-G4 | Keep cache keyed by the existing non-reversible server/profile/database identity model. |
| C-G5 | Make safe stale consumers instant without making strict consumers unsafe. |
| C-G6 | Add validation TTLs so repeated OE expands after one validation are instant. |
| C-G7 | Support explicit offline mode with visible snapshot age and fidelity notes. |
| C-G8 | Add cache privacy controls for descriptions and module definitions. |
| C-G9 | Add observability for cache decisions without logging object names, SQL text, rows, endpoints, prompts, secrets, tokens, or module text. |
| C-G10 | Make cache corruption, migration mismatch, permission changes, and drift detectable and recoverable. |

---

## 2. Non-goals

- Do not make persistent cache a hidden fallback for strict operations.
- Do not persist raw `sys.*` query rows.
- Do not persist SQL result rows, connection strings, passwords, tokens, prompts, or rendered AI schema-context text.
- Do not persist `sys.sql_modules.definition` by default.
- Do not persist `MS_Description` by default until privacy review explicitly approves it.
- Do not introduce STS2 wire DTO imports outside the SQL Data Plane boundary.
- Do not change the `CatalogSnapshot` read API into an I/O API.
- Do not block cache work on a binary codec. Start simple and measure.

---

## 3. Key principles

### 3.1 Cache accelerates, freshness decides

A cache hit means "we have known metadata." It does not mean "this metadata is current enough for every feature."

Consumers must declare a freshness policy. The store then decides whether to return the cached generation, validate it, refresh it, or refuse.

### 3.2 Readiness and freshness are separate dimensions

Readiness answers: "Do we have a trustworthy section in this snapshot?"

Freshness answers: "Is this snapshot recent or validated enough for this caller?"

A section can be:

- ready but stale;
- failed but with an older cached generation available;
- absent in the cached snapshot;
- ready from disk but not yet validated live;
- ready and recently validated.

Keep those states distinct. Do not collapse them into one overloaded `stale` bit.

### 3.3 The snapshot remains pure

`CatalogSnapshot` should not load files, validate drift, open sessions, or schedule refresh. The cache coordinator and store own those jobs. `CatalogSnapshot` can carry metadata such as captured time, readiness, and generation, but it must stay a pure read model.

### 3.4 Strict consumers must be able to block or refuse

Scripting, destructive OE actions, and strict definition scenarios must have a way to require live or freshly validated metadata. If the database is unavailable and offline mode is not explicit, the right answer is a clear refusal, not an optimistic script.

### 3.5 Offline mode is a mode, not an accident

Offline snapshot mode is useful and should be supported. It must be explicit in status, command output, and generated scripts. The UI should never imply that offline data was checked live.

---

## 4. Architecture

```text
Consumers
  - completions, hover, diagnostics, AI, OE v2, scripting
        |
        v
DatabaseCatalogLease / ServerCatalogLease
  - current(), pin(), ensureFresh(policy), refresh(), status()
        |
        v
MetadataStore
  - key-correct leases
  - memory entries and TTL/LRU
  - policy routing
  - drift notifications
        |
        +-------------------------------+
        |                               |
        v                               v
MetadataCacheCoordinator             MetadataService / ServerMetadataService
  - manifest load/save                  - live hydration H0-H7
  - cache validation state              - digest poll
  - eviction                            - DDL sniff
  - atomic writes                       - lazy module reads
        |                               |
        v                               v
Persistent cache files              SQL Data Plane / STS2 / SQL Server
```

### 4.1 New components

Recommended files:

```text
src/services/metadata/cache/metadataFreshness.ts
src/services/metadata/cache/metadataCacheCoordinator.ts
src/services/metadata/cache/metadataCacheManifest.ts
src/services/metadata/cache/metadataCacheCodec.ts
src/services/metadata/cache/metadataCacheStore.ts
src/services/metadata/cache/metadataCacheSettings.ts
src/services/metadata/cache/metadataCacheStatus.ts
src/services/metadata/cache/metadataCachePrivacy.ts
src/services/metadata/cache/metadataValidation.ts
```

Add light integration in:

```text
src/services/metadata/metadataStore.ts
src/services/metadata/metadataStoreService.ts
src/services/metadata/metadataService.ts
src/services/metadata/serverMetadataService.ts
src/sqlLanguage/provider/catalogProvider.ts
src/objectExplorer/v2/metadata/oeV2MetadataCoordinator.ts
src/sqlScripting/**
```

### 4.2 Consumer rule

Consumers should not import cache modules directly. They talk to leases:

```ts
const result = await databaseLease.ensureFresh(policy);
const snapshot = result.snapshot;
const view = provider.pin(); // or pin result-specific provider, depending on adapter shape
```

The cache is a store concern, not a feature concern.

---

## 5. Freshness policy API

### 5.1 Core types

```ts
export type MetadataFreshnessMode =
    | "allowStale"
    | "requireValidated"
    | "requireLive"
    | "offlineSnapshot";

export type MetadataFreshnessReason =
    | "completion"
    | "aiContext"
    | "hover"
    | "diagnostics"
    | "definition"
    | "oeBrowse"
    | "oeRefresh"
    | "oeSearch"
    | "scripting"
    | "manualRefresh"
    | "startupWarm";

export interface MetadataFreshnessPolicy {
    readonly mode: MetadataFreshnessMode;
    readonly reason: MetadataFreshnessReason;
    readonly sections?: readonly CatalogSection[];
    readonly objects?: readonly MetadataObjectIdentity[];
    readonly maxStalenessMs?: number;
    readonly validationTtlMs?: number;
    readonly allowPartial?: boolean;
    readonly allowDiskLoad?: boolean;
    readonly backgroundRefresh?: boolean;
    readonly timeoutMs?: number;
}

export interface MetadataObjectIdentity {
    readonly objectId?: number;
    readonly database?: string;
    readonly schema?: string;
    readonly name?: string;
    readonly kind?: ObjectKind;
}

export interface FreshCatalogResult {
    readonly snapshot: CatalogSnapshot | undefined;
    readonly generation: number;
    readonly source: "memory" | "disk" | "live" | "offline" | "none";
    readonly freshness: "fresh" | "validated" | "stale" | "refreshing" | "unavailable";
    readonly validation?: MetadataValidationSummary;
    readonly backgroundRefreshStarted?: boolean;
}
```

### 5.2 Lease additions

Add to `DatabaseCatalogLease`:

```ts
ensureFresh(policy: MetadataFreshnessPolicy): Promise<FreshCatalogResult>;
```

Add to `ServerCatalogLease`:

```ts
ensureFresh(policy: ServerMetadataFreshnessPolicy): Promise<FreshServerCatalogResult>;
```

Existing methods remain:

```ts
current(): CatalogSnapshot | undefined;
pin(): IPinnedServerCatalogView;
refresh(): Promise<void>;
status(): MetadataStatus;
```

### 5.3 Policy constants

Create common policy presets so consumers do not invent new knobs:

```ts
export const MetadataPolicies = {
    completion: {
        mode: "allowStale",
        reason: "completion",
        allowDiskLoad: true,
        backgroundRefresh: true,
        maxStalenessMs: 30 * 24 * 60 * 60_000,
    },
    aiContext: {
        mode: "allowStale",
        reason: "aiContext",
        allowDiskLoad: true,
        backgroundRefresh: true,
        maxStalenessMs: 7 * 24 * 60 * 60_000,
    },
    diagnosticsBinder: {
        mode: "requireValidated",
        reason: "diagnostics",
        sections: ["objects", "columns"],
        validationTtlMs: 60_000,
        timeoutMs: 250,
        allowPartial: false,
    },
    oeBrowse: {
        mode: "requireValidated",
        reason: "oeBrowse",
        validationTtlMs: 120_000,
        timeoutMs: 5_000,
    },
    scriptingStrict: {
        mode: "requireLive",
        reason: "scripting",
        timeoutMs: 15_000,
        allowPartial: false,
    },
} as const;
```

Values above are proposed defaults for dogfood. They should become options only after measurement and UX validation.

---

## 6. Consumer policy matrix

| Consumer | Policy | Behavior |
|---|---|---|
| Completion table/object suggestions | `allowStale` | Return cache immediately. If stale beyond max, schedule background refresh. |
| Completion column suggestions | `allowStale`, require `columns` section ready in snapshot | If columns absent/failed, return incomplete result rather than query live on the hot path. |
| FK join completions | `allowStale`, require `foreignKeys` ready | If FK section absent, omit join suggestions and keep basic completions. |
| AI schema context | `allowStale` | Build deterministic text from cached/pinned snapshot. Do not include descriptions/module definitions. |
| Hover | `allowStale` for column/table facts; optional `requireValidated` for module link | Show only facts from ready sections. |
| Diagnostics binder | `requireValidated` | If validation cannot complete within budget, suppress metadata-backed diagnostics. |
| Semantic tokens | `allowStale` for resolved color, or degrade unresolved modifiers | Do not show unresolved/error semantic meaning from stale metadata. |
| OE v2 server/database folder | `requireValidated` | First expand validates or refreshes. Within TTL, reuse memory generation. |
| OE explicit refresh | `requireLive` or forced `refresh()` | Bypass validation TTL. |
| OE search/filter | `requireValidated` if initial catalog not validated, else memory | Filter/search over pinned generation. |
| TypeScript scripting | `requireLive` | Refresh target facts. Offline mode explicitly downgrades and emits banner. |
| Go-to-definition synthesized table script | `requireLive` if online, `offlineSnapshot` only when user opts in | Anchors must map to the generation used. |
| Module definition read | live lazy read by default | Persist only under explicit policy. |

---

## 7. Persistent cache model

### 7.1 File layout

Recommended initial layout:

```text
<globalStorage>/metadata-cache/v1/
  index.json
  servers/
    <serverFingerprint>/
      manifest.json
      serverCatalog.json.gz
  databases/
    <serverFingerprint>/
      <databaseHash>/
        manifest.json
        catalog.json.gz
        previous/
          <capturedAt>.manifest.json
```

Rules:

- Use `serverFingerprint` from the store.
- Use a hash of the exact database name for path privacy and filesystem safety.
- Store exact database spelling inside the manifest payload, classified as local metadata.
- Do not use raw server names, user names, or database names as path segments.
- `previous/` is optional and should be capped or omitted initially.

### 7.2 Manifest

```ts
export interface CatalogCacheManifest {
    readonly formatVersion: 1;
    readonly producer: {
        readonly extensionVersion?: string;
        readonly gitCommit?: string;
        readonly catalogModelVersion: string;
        readonly cacheCodec: "json-gzip-v1";
    };
    readonly key: {
        readonly serverFingerprint: string;
        readonly databaseHash: string;
        readonly databaseExact?: string;
    };
    readonly capture: {
        readonly capturedAtUtc: string;
        readonly publishedGeneration: number;
        readonly source: "live" | "offlineImport";
    };
    readonly validation: {
        readonly lastValidatedAtUtc?: string;
        readonly validationTier?: MetadataValidationTier;
        readonly serverDigest?: string;
        readonly objectDigest?: string;
        readonly sectionDigests?: Partial<Record<CatalogSection, string>>;
    };
    readonly readiness: Record<CatalogSection, SectionState>;
    readonly mode: "full" | "lite" | "partial";
    readonly stats: {
        readonly schemas: number;
        readonly objects: number;
        readonly columns: number;
        readonly foreignKeys: number;
        readonly payloadBytes: number;
        readonly uncompressedBytes?: number;
    };
    readonly privacy: {
        readonly includesDescriptions: boolean;
        readonly includesModuleDefinitions: boolean;
        readonly includesRowCounts: boolean;
        readonly policyId: string;
    };
    readonly payload: {
        readonly file: "catalog.json.gz";
        readonly sha256: string;
    };
}
```

### 7.3 Payload

Initial payload can be JSON plus gzip:

```ts
export interface CatalogCachePayloadV1 {
    readonly environment: CatalogEnvironment;
    readonly strings: readonly string[];
    readonly schemas: SerializedSchemaTable;
    readonly objects: SerializedObjectTable;
    readonly columns: SerializedColumnTable;
    readonly foreignKeys: SerializedForeignKeyTable;
    readonly keys: SerializedKeyTable;
    readonly parameters: SerializedParameterTable;
    readonly descriptions?: SerializedDescriptionTable;
}
```

The serializer should live next to `catalogModel.ts` but not inside `CatalogSnapshot`. A codec can be a friend class/function that knows how to rehydrate `CatalogBuilder` safely.

### 7.4 Why JSON plus gzip first

JSON plus gzip is easy to inspect, easy to diff, easy to version, and likely fast enough for metadata volumes. A binary codec can come later if measured load time or file size justifies it.

Do not spend the first implementation slice inventing a binary XML goblin when JSON can carry the lantern.

---

## 8. Privacy model

### 8.1 Default persistence policy

| Data | Persist by default | Rationale |
|---|---:|---|
| schemas | yes | structural metadata |
| objects and kinds | yes | structural metadata |
| columns and type display | yes | needed for completions/OE |
| identity/computed flags | yes | structural metadata, needed for scripting notes |
| PK/UQ/FK names and columns | yes | structural metadata |
| routine parameter names/types | yes | structural metadata |
| `MS_Description` | no | user-authored prose |
| module definitions | no | SQL text and business logic |
| row counts | no | can disclose data scale; product decision needed |
| AI schema-context text | no | regenerate deterministically |
| query results/raw rows | never | not metadata cache |
| connection string/password/token | never | secrets |

### 8.2 Optional sensitive local metadata

If later enabled, descriptions and module definitions should have separate settings and separate cache sections:

```jsonc
"mssql.metadataCache.persistDescriptions": false,
"mssql.metadataCache.persistModuleDefinitions": false
```

Even if enabled, they should never appear in diagnostic events or remote model schema context unless separately approved.

### 8.3 Cache status redaction

Allowed in diagnostics:

- short fingerprint prefix;
- payload byte count;
- object/column/FK counts;
- readiness states;
- stale age bucket;
- validation tier;
- policy reason;
- error class.

Not allowed:

- object names;
- database names by default;
- SQL text;
- row values;
- connection strings;
- passwords/tokens;
- raw endpoints;
- prompt text;
- module text;
- descriptions.

---

## 9. Atomic writes and corruption recovery

### 9.1 Write protocol

Use a manifest-last protocol:

1. Build `CatalogCachePayloadV1` from a published snapshot.
2. Serialize to temp file `catalog.json.gz.<pid>.<nonce>.tmp`.
3. Flush and close temp payload.
4. Compute SHA-256 over temp payload.
5. Rename temp payload to content-addressed or stable payload path.
6. Write manifest to temp file.
7. Flush and close manifest temp.
8. Rename manifest temp to `manifest.json`.
9. Emit `metadataCache.save`.

A reader trusts only a manifest whose referenced payload exists and whose digest matches.

### 9.2 Read protocol

1. Read manifest.
2. Validate format version, codec, key, privacy policy, and payload digest.
3. Read/decompress payload.
4. Validate payload shape and section counts.
5. Rehydrate `CatalogBuilder` and publish `CatalogSnapshot` with source `disk` and cache metadata.
6. Emit `metadataCache.load`.

On any failure:

- emit `metadataCache.corrupt` or `metadataCache.miss` with safe fields;
- delete or quarantine invalid files when safe;
- continue to live hydration if online;
- do not crash activation.

### 9.3 Concurrent writers

Minimum safe strategy:

- temp filenames include process ID and random nonce;
- manifest replace is atomic;
- a writer can overwrite only after reading current manifest and deciding new capture is newer or better;
- readers never trust partial files.

Optional later:

- lock file with stale lock timeout;
- content-addressed payloads and manifest CAS.

---

## 10. Load and startup flow

### 10.1 Database lease acquire

```text
acquireDatabase(prepared, database)
  -> create or reuse store entry
  -> if no memory snapshot:
        ask cache coordinator for disk snapshot
        if valid: publish as generation N, source=disk, freshness=stale/unknown
  -> start live hydration according to policy/settings
  -> return lease immediately
```

### 10.2 Safe consumer flow

```text
completion request
  -> lease.ensureFresh(MetadataPolicies.completion)
  -> if disk/memory snapshot exists: return immediately
  -> if no snapshot: return keyword-only / incomplete and request hydration
  -> background refresh continues
```

### 10.3 Strict consumer flow

```text
script create request
  -> lease.ensureFresh(MetadataPolicies.scriptingStrict)
  -> if online and refresh succeeds: script generation N
  -> if online and refresh fails: refuse with actionable error
  -> if offline mode: script snapshot N with offline banner and fidelity notes
```

### 10.4 OE v2 flow

```text
first table folder expand
  -> requireValidated(validationTtlMs = 120000)
  -> if not recently validated: run cheap validation or refresh
  -> render generation N

next table folder expand 30 seconds later
  -> validation still within TTL
  -> render generation N immediately

explicit Refresh
  -> bypass TTL
  -> refresh server/database lease
  -> render generation N+1 or error child
```

---

## 11. Drift and validation design

### 11.1 Existing drift triggers

The design keeps existing triggers:

- DDL sniff from executed batches: `CREATE`, `ALTER`, `DROP`, `SP_RENAME` force refresh; `EXEC` can trigger digest check.
- Cheap digest poll while handles are live.
- Explicit refresh from consumer commands.

### 11.2 New validation state

Add validation metadata to store entries:

```ts
export interface MetadataValidationSummary {
    readonly validatedAtUtc?: string;
    readonly tier: MetadataValidationTier;
    readonly result: "notChecked" | "unchanged" | "changed" | "failed" | "unsupported";
    readonly staleReason?: MetadataStaleReason;
    readonly durationMs?: number;
}

export type MetadataValidationTier =
    | "none"
    | "memoryTtl"
    | "cheapDatabaseDigest"
    | "sectionDigest"
    | "objectDigest"
    | "fullRefresh";

export type MetadataStaleReason =
    | "ttlExpired"
    | "ddlSniff"
    | "digestMismatch"
    | "sectionMismatch"
    | "objectMismatch"
    | "permissionChanged"
    | "accessChanged"
    | "cachePolicyChanged"
    | "unknown";
```

### 11.3 Tier T0: memory TTL

If an entry was validated recently enough for the policy, return it without SQL.

This is the key to the "10 expands in 2 minutes" scenario.

### 11.4 Tier T1: cheap database digest

Use the existing object count/hash as a broad drift signal.

Best for:

- completion background refresh;
- OE browse validation when broad accuracy is enough;
- detecting external migrations cheaply.

Limitations:

- collisions possible;
- not all metadata sections covered;
- permission changes can alter visibility;
- strict scripts may need targeted refresh anyway.

### 11.5 Tier T2: section digests

Add optional digest queries per section:

| Section | Digest source idea |
|---|---|
| objects | object id, schema id, name, type, modify date |
| columns | object id, column id, name, user type id, max length, precision, scale, nullable, identity, computed |
| keys | object id, index id, key ordinal, key flags, column id |
| foreignKeys | FK id, parent/ref object ids, column ids, constraint column id |
| parameters | object id, parameter id, name, type, output |
| descriptions | extended property major/minor id, value hash only if descriptions persist/used |

Section digests let OE refresh the right state without full database hydration every time.

### 11.6 Tier T3: object-scoped digest

For strict scripting, validate the target object directly:

- re-resolve object by natural identity `{database, schema, name, kind}`;
- compare object ID when available;
- validate sections needed by requested script operation;
- refresh target object or full catalog if mismatch.

If fetching object details is as cheap as checking, fetch. Do not over-design validation when live read is cheaper.

### 11.7 Tier T4: full refresh

Full refresh remains the recovery path after mismatch, explicit refresh, unsupported digest, cache schema mismatch, or strict policy.

Forced refresh must keep the current chaining rule: never overlap an in-flight hydration on the one-active-query session lane.

---

## 12. Status model

Extend status without breaking current consumers:

```ts
export interface MetadataStatus {
    readonly readiness: "absent" | "loading" | "ready" | "failed" | "stale";
    readonly generation: number;
    readonly mode: "full" | "lite" | "partial" | "offline";
    readonly stats?: { schemas: number; objects: number; columns: number; foreignKeys: number };
    readonly cache?: MetadataCacheEntryStatus;
    readonly validation?: MetadataValidationSummary;
}

export interface MetadataCacheEntryStatus {
    readonly source: "none" | "memory" | "disk" | "offline" | "live";
    readonly capturedAtUtc?: string;
    readonly loadedAtUtc?: string;
    readonly lastSavedAtUtc?: string;
    readonly payloadBytes?: number;
    readonly privacyPolicyId?: string;
    readonly staleAgeMs?: number;
    readonly hasDiskSnapshot: boolean;
    readonly includesDescriptions: boolean;
    readonly includesModuleDefinitions: boolean;
}
```

OE and status commands can present this as:

```text
Metadata: ready, generation 42, loaded from disk, validated 43 seconds ago
```

or:

```text
Metadata: offline snapshot, captured 2 days ago, live validation unavailable
```

---

## 13. Settings and knobs

### 13.1 Initial settings

Keep the initial public surface small:

```jsonc
"mssql.metadataCache.enabled": false,
"mssql.metadataCache.maxAgeDays": 14,
"mssql.metadataCache.maxBytes": 268435456,
"mssql.metadataCache.offlineMode": false
```

### 13.2 Internal/dogfood settings

```jsonc
"mssql.metadataCache.persistDescriptions": false,
"mssql.metadataCache.persistModuleDefinitions": false,
"mssql.metadataCache.validationTtlMs": 120000,
"mssql.metadataCache.writeDelayMs": 5000,
"mssql.metadataCache.codec": "json-gzip-v1"
```

Do not expose all of these to normal users until there is evidence that users need them.

### 13.3 Commands

```text
mssql.metadataCache.showStatus
mssql.metadataCache.clearAll
mssql.metadataCache.clearForConnection
mssql.metadataCache.enableOfflineMode
mssql.metadataCache.disableOfflineMode
```

Commands should use classified output and avoid raw endpoints/secrets.

---

## 14. Write scheduling

Do not save every generation immediately. Use debounce and section filters:

- Save after a successful full or useful partial hydration.
- Debounce writes by `writeDelayMs`.
- Coalesce multiple refreshes.
- Do not save snapshots whose mandatory sections failed unless there is no better cache and the manifest records partial mode.
- Do not write while the entry is being disposed unless the snapshot is already built.

Recommended first rule:

```text
save if objects=ready and schemas=ready, and at least one of columns/keys/foreignKeys/parameters is ready.
```

Later, save per-section payloads if large catalogs make full writes expensive.

---

## 15. Cache eviction

### 15.1 Memory eviction

Existing idle TTL/LRU handles live metadata entries. Cache-loaded memory snapshots should follow the same database entry lifecycle. When a database entry is evicted from memory, the disk cache remains.

### 15.2 Disk eviction

Evict by:

1. max age;
2. max total bytes;
3. least recently used;
4. corrupt/unsupported entries first.

Maintain `index.json` for quick status. If index is corrupt, rebuild by scanning manifests.

---

## 16. Offline mode

### 16.1 Offline acquisition

When offline mode is true:

- do not open live metadata sessions for cache-backed requests;
- load cache if available;
- mark status mode `offline`;
- strict policies become `offlineSnapshot` only if the caller allows it;
- if no snapshot exists, return unavailable with a clear status.

### 16.2 Consumer behavior in offline mode

| Consumer | Behavior |
|---|---|
| completions | use cache if available, incomplete otherwise |
| AI schema context | use cache, privacy-gated, include snapshot metadata in feature-capture metadata but not prompt text by default |
| diagnostics | lexical/structural only; suppress metadata-backed binder diagnostics unless user opts into stale diagnostics |
| OE | browse snapshot with offline status child/banner |
| scripting | generate only with explicit offline banner and fidelity notes |

### 16.3 Offline banner examples

OE status node:

```text
Using offline metadata snapshot from 2026-07-06 15:12. Live database was not checked.
```

Scripting header:

```sql
-- Generated from offline metadata snapshot.
-- Snapshot captured at 2026-07-06T15:12:03Z.
-- Live drift validation was not performed.
```

---

## 17. Integration points

### 17.1 MetadataStore

Responsibilities:

- call cache load during database/server entry creation;
- publish disk snapshot if valid;
- route `ensureFresh(policy)`;
- schedule background refresh;
- call cache save after useful live generations;
- expose cache status;
- maintain key correctness and refcount semantics.

### 17.2 MetadataService

Responsibilities:

- expose enough metadata for cache serialization;
- expose validation helpers or digest queries;
- keep hydration and forced refresh chained;
- never know about disk paths.

### 17.3 CatalogModel

Responsibilities:

- provide stable serialization helpers or builder rehydration helpers;
- preserve deterministic ordering;
- keep snapshot pure.

### 17.4 Query Studio

Responsibilities:

- safe stale completions and AI context can use cache;
- DDL execution continues to notify store drift;
- status bar can show metadata source/freshness when useful.

### 17.5 Native language service

Responsibilities:

- pass freshness policy for features that require it;
- suppress binder diagnostics when policy cannot validate;
- keep hot path sync after `ensureFresh` decisions.

### 17.6 Object Explorer v2

Responsibilities:

- use `requireValidated` for browse;
- use memory TTL for follow-up expands;
- explicit refresh bypasses TTL;
- offline mode renders snapshot honestly.

### 17.7 AI completions

Responsibilities:

- build schema context from pinned snapshot;
- do not persist rendered schema context;
- keep remote LM privacy gates.

### 17.8 TypeScript scripting

Responsibilities:

- require live or targeted refresh;
- record snapshot generation and freshness in `ScriptResult`;
- emit offline banner/fidelity notes in offline mode.

---

## 18. Observability

### 18.1 Event vocabulary

Register these events/spans before emitting:

```text
metadataCache.load
metadataCache.save
metadataCache.hit
metadataCache.miss
metadataCache.validate
metadataCache.policyDecision
metadataCache.backgroundRefresh
metadataCache.evict
metadataCache.corrupt
metadataCache.clear
metadataCache.offlineMode
```

### 18.2 Suggested fields

| Field | Class |
|---|---|
| server fingerprint prefix | diagnostic.metadata |
| database hash prefix | diagnostic.metadata |
| policy reason | safe enum |
| policy mode | safe enum |
| source | safe enum |
| generation | diagnostic.metadata |
| readiness summary | diagnostic.metadata |
| validation tier | safe enum |
| validation result | safe enum |
| stale age bucket | diagnostic.metadata |
| payload bytes | diagnostic.metric |
| duration ms | diagnostic.metric |
| error class | safe enum |

### 18.3 Forbidden fields

- object names;
- raw database names by default;
- SQL text;
- result rows;
- full server endpoints;
- connection strings;
- passwords/tokens;
- prompt text;
- module definitions;
- descriptions.

---

## 19. Testing plan

### 19.1 Unit tests

```text
test/unit/metadataCache/manifest.test.ts
test/unit/metadataCache/codec.test.ts
test/unit/metadataCache/atomicWrite.test.ts
test/unit/metadataCache/freshnessPolicy.test.ts
test/unit/metadataCache/privacy.test.ts
test/unit/metadataCache/eviction.test.ts
```

Required cases:

- manifest version mismatch;
- payload digest mismatch;
- corrupt gzip;
- database path with Unicode/slash/bracket/dot in name;
- privacy settings exclude descriptions/modules;
- cache source does not alter `buildSchemaContext` output.

### 19.2 Store integration tests

```text
test/unit/metadataStoreCache.test.ts
```

Cases:

- acquire database loads disk snapshot before live hydration completes;
- safe stale policy returns disk snapshot immediately;
- strict policy waits for validation;
- validation TTL prevents repeated SQL checks;
- explicit refresh bypasses TTL;
- dispose/TTL/LRU still works;
- key-correctness tripwire still works.

### 19.3 Consumer tests

- completion uses stale cache without network on hot path;
- diagnostics suppress binder diagnostics on stale/unvalidated cache;
- OE first expand validates and next expand uses TTL;
- scripting refuses stale metadata unless offline mode is explicit;
- AI schema context remains byte-identical.

### 19.4 Fault tests

- cache file deleted while loading;
- manifest updated during read;
- two writers race;
- live validation fails;
- permissions change after cache load;
- database no longer exists;
- object ID reused after drop/recreate.

### 19.5 Perf tests

Suggested scenarios:

```text
metadata-cache.load.10k
metadata-cache.save.10k
metadata-cache.completion-after-restart
metadata-cache.oe-first-expand
metadata-cache.oe-repeat-expand-ttl
metadata-cache.validation-under-query-load
```

---

## 20. Performance budgets

Initial budgets, to be calibrated with real large catalog fixtures:

| Operation | Target |
|---|---:|
| cache manifest read | p95 < 5 ms |
| cache payload load/decompress 10k objects | p95 < 50 ms |
| rehydrate `CatalogSnapshot` from payload | p95 < 30 ms |
| safe completion metadata wait after restart | p95 < 10 ms |
| OE first validated expand from cache | p95 < 250 ms including validation if server responsive |
| OE repeat expand within validation TTL | p95 < 30 ms |
| cache save after hydration | background, no user-visible stall |
| corrupt cache recovery | p95 < 20 ms before live hydration starts |

---

## 21. Implementation plan

### CACHE-0: Freshness policy API

Files:

```text
src/services/metadata/cache/metadataFreshness.ts
src/services/metadata/metadataStore.ts
```

Work:

1. Add policy types and presets.
2. Add `ensureFresh(policy)` to database/server leases.
3. Implement memory/live behavior only.
4. Add telemetry for policy decisions.

Exit criteria:

- Existing consumers unchanged.
- New tests prove completion/diagnostics/OE/scripting policies make different decisions.

### CACHE-1: Snapshot serialization codec

Files:

```text
src/services/metadata/cache/metadataCacheCodec.ts
src/services/metadata/cache/metadataCacheManifest.ts
src/services/metadata/catalogModel.ts
```

Work:

1. Serialize a published snapshot to JSON payload.
2. Rehydrate into a builder/snapshot.
3. Preserve readiness, mode, generation metadata, and environment.
4. Round-trip large fixture.

Exit criteria:

- Round-trip schema context is byte-identical.
- Descriptions/modules excluded by default.

### CACHE-2: Disk coordinator

Files:

```text
src/services/metadata/cache/metadataCacheCoordinator.ts
src/services/metadata/cache/metadataCacheStore.ts
src/services/metadata/cache/metadataCacheSettings.ts
```

Work:

1. Implement file layout.
2. Implement atomic writes.
3. Implement load, save, clear, and status.
4. Implement max age and max bytes cleanup.

Exit criteria:

- Corruption safe.
- Concurrent writer safe enough for dogfood.
- Status command can report cache state.

### CACHE-3: Store integration

Work:

1. Load disk snapshot on acquire.
2. Publish cache-loaded generation.
3. Save after successful hydration.
4. Mark source/freshness in status.
5. Preserve TTL/LRU behavior.

Exit criteria:

- Cold restart can serve cached metadata before live hydration.
- Live hydration replaces cached generation when complete.

### CACHE-4: Safe stale consumers

Work:

1. Wire native completions.
2. Wire AI schema-context build.
3. Add status/debug UI.
4. Add perf gates.

Exit criteria:

- Completion hot path never opens a network query because cache is stale.
- Background refresh occurs and is observable.

### CACHE-5: Validated consumers

Work:

1. Wire diagnostics binder policy.
2. Wire OE v2 browse policy.
3. Add validation TTL behavior.
4. Add explicit refresh bypass.

Exit criteria:

- Diagnostics do not false-positive from stale cache.
- OE first expand validates, repeat expands within TTL are instant.

### CACHE-6: Strict consumers and offline mode

Work:

1. Wire TypeScript scripting.
2. Wire go-to/peek definition where applicable.
3. Add offline banner/fidelity notes.
4. Add offline status UI.

Exit criteria:

- Strict online operations refresh or refuse.
- Offline operations clearly declare snapshot use.

### CACHE-7: Section/object validation tiers

Work:

1. Add section digests for objects/columns/keys/FKs/parameters.
2. Add object-scoped validation for scripting.
3. Add policy routing to select cheapest sufficient tier.

Exit criteria:

- Strict operations can avoid full database refresh where safe.
- Mismatch correctly recovers with refresh.

---

## 22. Acceptance gates

Persistent metadata cache should not be enabled broadly until these are true:

- Cache-loaded and live snapshots produce identical schema-context text for equivalent data.
- Cache contains no secrets, raw endpoints, connection strings, SQL rows, prompts, module definitions, or descriptions by default.
- Corrupt/old cache never crashes activation.
- Completion and AI paths are faster after restart with cache.
- Diagnostics suppress or validate, never assert binder errors from stale cache.
- OE v2 validates first browse and uses TTL for repeated expands.
- Scripting requires live or emits offline banner.
- Key correctness tests still pass with cache.
- Large-catalog cache load/save has measured budgets.
- Cache can be cleared from command/status UI.

---

## 23. Open decisions

| Decision | Suggested answer for first implementation |
|---|---|
| Public default | Off, or internal dogfood only, until perf/privacy gates pass. |
| Codec | JSON + gzip v1. |
| Persist descriptions | Off. |
| Persist module definitions | Off. |
| Offline mode | User-visible explicit mode, not automatic. |
| Validation TTL for OE | 120 seconds dogfood default. |
| Validation for diagnostics | Require validated; suppress if unavailable. |
| Strict scripting fallback | Refuse unless offline snapshot explicitly allowed. |
| Encryption at rest | Use VS Code global storage and OS protections initially; revisit if product policy requires more. |
| Section digests | Phase 2 after broad cache proves useful. |
| Serialized USE lane | Separate performance optimization after session-pressure evidence. |

---

## 24. Coding-agent handoff summary

Start by adding `MetadataFreshnessPolicy` and `ensureFresh(policy)` with no disk implementation. Then build a JSON+gzip snapshot codec and prove byte-identical schema-context round-trip. Only then wire disk load/save. Consumers should integrate in this order:

1. completions and AI schema context;
2. diagnostics suppression/validation;
3. OE v2 browse validation TTL;
4. scripting strict/live and offline mode;
5. section/object digest optimization.

The design succeeds when cache is a transparent speed layer for safe consumers and a visible, policy-governed snapshot source for strict consumers. It fails if stale data becomes invisible truth.
