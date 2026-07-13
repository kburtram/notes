# Metadata Substrate Deep Review
## MetadataStore, MetadataService, CatalogModel, and the Query Studio / language service / AI completions / Object Explorer v2 consumers

**Status:** detailed review and improvement notes, 2026-07-06.  
**Review basis:** uploaded `metadata-substrate-design.md`, `METADATA_DESIGN_VISUALS.tex` / PDF, current `dev/query` code excerpts for `metadataStore.ts`, `metadataService.ts`, `serverMetadataService.ts`, `catalogModel.ts`, `sqlLanguage/provider/types.ts`, and the related language service and Object Explorer v2 design documents.

---

## 0. Executive verdict

The metadata substrate design is strong. It has the right center of gravity: a pure immutable catalog snapshot, a per-database hydration engine, and a process-wide store that hands consumers leases instead of handing them transport details. The important invariants are unusually crisp:

1. **Pin once per response.** A completion request, diagnostic pass slice, hover, AI schema-context build, or OE expand reads one consistent generation.
2. **Failure is never emptiness.** Empty lists only mean empty when the relevant section is ready. Failed, absent, stale, partial, unsupported, and permission-limited sections stay visible as state.
3. **Key correctness is structural.** A database catalog key must correspond to a session opened in that database, or the store must trip loudly.
4. **The snapshot is pure.** `CatalogSnapshot` never performs I/O. Hydration, drift, lazy module reads, and cache work remain outside it.
5. **Consumers are narrow.** Language and AI consumers go through `ISqlLanguageMetadataProvider` / `IPinnedMetadataView`; OE v2 and scripting use leases only where they need wider catalog surfaces.

The largest missing piece is not basic metadata browsing anymore. It is **freshness policy**: deciding which consumers may use stale cached data, which consumers need a recent validation, which consumers need a live refresh, and how that decision is represented in the API, UI, cache, tests, and diagnostics. The next design layer should be a first-class `FreshnessPolicy` plus a persistent cache. The persistent cache should be a projection of published snapshots, not a second metadata model hiding in the attic.

The rest of this review is a practical hardening plan: what to preserve, what to improve before persistent caching, what to test, and what to keep on the risk board.

---

## 1. What is already very good

### 1.1 The three-layer architecture is the right cut

The current split is the keeper:

```text
CatalogSnapshot / CatalogBuilder       pure immutable metadata model
MetadataService                        per-database hydration, generations, drift, lazy detail reads
MetadataStore                          process singleton, server/database leases, identity, refcount, TTL/LRU
```

This cut makes the system reviewable. `CatalogSnapshot` can be tested with fixtures. `MetadataService` can be stress-tested for session-lane and hydration races. `MetadataStore` can be tested for key correctness, lease lifecycle, and session pressure. Consumers can be tested against fixture providers without standing up a server.

Do not blur this boundary when adding cache. Persistent cache should load a `CatalogSnapshot` projection into the store. It should not become a hidden alternate metadata service.

### 1.2 Structure-of-arrays and interning are justified

The `CatalogModel` choice is not premature optimization. For metadata, SoA is also a correctness tool:

- deterministic ordering makes byte-identical AI schema-context render possible;
- string interning shrinks common repeated facts such as schemas, type names, and constraint names;
- contiguous ranges make `getColumns`, `getParameters`, and FK detail reads cheap enough for hot paths;
- folded name indexes make prefix search and completions cheap without live I/O.

The main caution is that append order is now a contract. New sections should be appended after existing arrays, and each read path that depends on grouping order should keep a test that fails under reordering.

### 1.3 Section readiness is the honesty backbone

The explicit `CatalogSection` plus `SectionState` model is exactly right. It lets each consumer choose correctly:

- completions can return partial lists and mark them incomplete;
- diagnostics can suppress instead of false-positive;
- hover can omit untrusted facts;
- OE can show an error child instead of `No items`;
- scripting can emit fidelity notes instead of fabricating DDL.

This should be extended, not replaced, for cache. Cache freshness should be layered as an additional dimension, not squashed into `ready` / `stale` only.

Recommended addition:

```ts
export type MetadataSourceKind = "live" | "memory" | "disk" | "offline";

export interface SectionFreshness {
    readonly section: CatalogSection;
    readonly state: SectionState;
    readonly source: MetadataSourceKind;
    readonly capturedAtUtc?: string;
    readonly validatedAtUtc?: string;
    readonly staleReason?: "ttlExpired" | "digestMismatch" | "ddlSniff" | "permissionChanged" | "unknown";
}
```

This keeps readiness and freshness separate. A section can be ready but old, failed but with a prior cached fallback, or absent from cache but available live.

### 1.4 Dedicated metadata sessions are the correct preview default

The per-database dedicated session strategy is the boring, provable thing, which is exactly what metadata needs. It avoids user F5 contention, turns database key correctness into a construction rule, and keeps the one-active-query STS2 session model simple.

The serialized `USE` server lane is a reasonable future optimization, but only after session-pressure evidence exists. It should not block OE v2 or the persistent cache. The current design already preserves the acquisition surface that would allow swapping it in later.

### 1.5 The completion-reaction discipline should stay loud

The note about awaiting `handle.completion`, not the sink callback, is not trivia. It is a bug repellent. Put the same warning in any new cache warmup, validation, object-scoped refresh, or lazy detail read code that executes metadata queries.

Recommended test pattern:

```ts
it("does not start validation query B until query A handle.completion resolves", async () => {
    // Fake session exposes a Busy failure if execute is called before completion resolves.
});
```

### 1.6 The store identity model is a major upgrade

The non-reversible server/profile fingerprints, exact database spelling, and post-open key-correctness tripwire are all release-worthy decisions. They address three common metadata bugs:

- secrets or endpoints leaking through IDs;
- case-sensitive database names getting merged;
- a session in database A accidentally hydrating a catalog for database B.

Cache must reuse the same keys. Do not invent a second cache fingerprint recipe. That way Query Studio, native LS, AI completions, OE v2, and offline snapshots all agree on identity.

### 1.7 Server catalog state is correctly modeled

`ServerMetadataService` listing inaccessible databases with `accessState` rather than filtering them out is the right UX and correctness call. A failed server catalog returning `undefined`, not `[]`, preserves the same failure-is-not-empty invariant at server scope.

The persistent cache should mirror this behavior. If server catalog load from disk fails, it should be failed/absent, not an empty server. If a cached server list exists but validation fails, consumers should see a prior snapshot plus freshness state, not a magically clean server.

### 1.8 The language-provider seam is small and valuable

The language seam is not just for language features. It is the seam that makes cached/offline metadata possible without infecting the engine with transport decisions. `IPinnedMetadataView` already has the most important property: all reads are synchronous over a pinned generation except the one sanctioned lazy definition read.

That is also the correct shape for cached metadata. A disk-loaded snapshot can implement the seam without a connection. A live snapshot can implement the same seam. A fixture can implement the seam. The consumer should choose based on a freshness policy, not know the source.

### 1.9 AI completions have the right determinism and privacy contract

The byte-identical schema-context guarantee is important enough to keep as a cache gate. Persisted cache should not perturb schema-context ordering or text. Cache-loaded snapshots must produce the same `buildSchemaContext` output as live snapshots with equivalent data.

The `MS_Description` exclusion from remote model projections should remain the default. Descriptions are user-authored content, not just structural metadata.

### 1.10 OE v2 is correctly stricter than the classic metadata backend

The OE metadata backend design is a compatibility path for the current tree. OE v2 is the long-term architecture path. OE v2 should keep its core rule: browse, refresh, filter, search, and basic query actions use STS2/Data Plane plus MetadataService; STS v1 exists only for explicit command handoff.

Persistent cache should be designed for OE v2 first, then classic metadata backend second.

---

## 2. Primary recommendations

### R1. Add a first-class freshness policy API before adding disk cache

Do this before writing cache files. Without this API, stale cache semantics will leak into every consumer as ad hoc booleans.

Recommended core types:

```ts
export type MetadataFreshnessMode =
    | "allowStale"          // return best known snapshot immediately, refresh in background
    | "requireValidated"    // return only if recent validation says it is current enough
    | "requireLive"         // refresh or targeted live read before answering
    | "offlineSnapshot";    // explicitly use known snapshot without live validation

export interface MetadataFreshnessPolicy {
    readonly mode: MetadataFreshnessMode;
    readonly maxStalenessMs?: number;
    readonly validationTtlMs?: number;
    readonly sections?: readonly CatalogSection[];
    readonly objects?: readonly { objectId?: number; schema?: string; name?: string; kind?: ObjectKind }[];
    readonly allowPartial?: boolean;
    readonly allowDiskLoad?: boolean;
    readonly backgroundRefresh?: boolean;
    readonly reason: "completion" | "hover" | "diagnostics" | "aiContext" | "oeBrowse" | "scripting" | "manualRefresh";
}

export interface FreshCatalogResult {
    readonly snapshot: CatalogSnapshot | undefined;
    readonly generation: number;
    readonly source: "memory" | "disk" | "live" | "offline";
    readonly freshness: "fresh" | "validated" | "stale" | "refreshing" | "unavailable";
    readonly validation?: MetadataValidationSummary;
}
```

Keep `lease.current()` and `provider.pin()` fast and synchronous. Add `lease.ensureFresh(policy)` for consumers that need it.

### R2. Define a consumer freshness matrix

A single freshness rule will make either the editor slow or scripting unsafe. The substrate should expose policy, and each consumer should pick intentionally.

| Consumer / feature | Default freshness policy | Notes |
|---|---|---|
| Non-AI completions | `allowStale`, background refresh | Worst case is a bad suggestion and SQL Server rejects it. Keep typing instant. |
| AI schema context | `allowStale`, privacy-gated, deterministic | Do not include descriptions/module definitions by default. Record generation and cache source. |
| Hover | `allowStale` for basic structure, `requireValidated` for module definition links if needed | Stale hover is tolerable if labeled in status, but do not show untrusted descriptions to remote models. |
| Diagnostics | `requireValidated` or suppress binder diagnostics | False squiggles are costly. Stale metadata should suppress 207/208/209-like claims. |
| OE browse | `requireValidated` with short TTL; within TTL use memory instantly | First expand validates/refreshes. Follow-up expands within the TTL should reuse. Explicit refresh forces validation. |
| OE search/filter | same as browse once folder/catalog validated | In-memory filter over pinned view. |
| Scripting `CREATE` / `ALTER` | `requireLive` or targeted object refresh | Scripts are user-visible output. If offline, emit a snapshot banner and fidelity notes. |
| Go-to/peek definition | module text: lazy live read unless cached by explicit policy | Module text persistence should be off by default. |
| Offline mode | `offlineSnapshot` | UI/status must say snapshot time and validation state. |

### R3. Persist published snapshots, not raw query rows

Cache should serialize the same facts consumers see from a published `CatalogSnapshot`, plus manifest metadata, freshness, digests, and privacy policy. Do not persist raw `sys.*` rows. Raw rows are harder to version, harder to privacy-review, and invite consumers to bypass the snapshot model.

### R4. Treat cache as a source, not a truth override

Disk cache should accelerate startup and offline use. It should not hide live validation failure from strict consumers.

A good mental model:

```text
Disk cache loads a previous generation quickly.
Live hydration publishes a newer generation when available.
Validation decides whether a cached generation is fresh enough for the caller.
Strict callers can block, refresh, or refuse.
Safe callers can continue on stale data while refresh runs.
```

### R5. Use a validation TTL layer in addition to digest polling

The existing digest poll catches drift while a lease is alive. Persistent cache needs one more idea: validation recency.

For example:

- OE expand policy: validate if last validation is older than 2 minutes.
- Completion policy: use immediately, refresh if older than 1 hour or if no validation since load.
- Scripting policy: refresh object sections every time unless explicitly offline.

This gives the exact behavior requested: first OE expand checks or fetches; the next ten expands in two minutes use the same validated generation.

### R6. Add section and object-scoped validation over time

The existing cheap database digest is a good start, but it is too broad and too narrow at the same time:

- too broad because a change in any object can invalidate a whole database;
- too narrow because it only tracks object count/modify date style drift and does not prove columns, keys, FKs, permissions, or descriptions stayed unchanged.

Recommended tiers:

| Tier | Purpose | Candidate query |
|---|---|---|
| T0 memory TTL | Avoid repeated checks in short windows | no SQL |
| T1 cheap object digest | Detect broad DDL drift | count + checksum over `sys.objects` modify dates |
| T2 section digest | Validate objects/columns/keys/FKs independently | per-section count/checksum over key columns |
| T3 object scoped digest | Validate one object before strict scripting | object id/name/kind plus columns/keys/FKs modify signatures |
| T4 full refresh | Recover after mismatch, permission change, cache mismatch, or explicit refresh | current H0-H7 ladder |

Use T1 now, design T2/T3 as extension points. Do not make correctness claims stronger than the validation tier supports.

### R7. Make offline mode explicit

Offline cache is useful, but it must not masquerade as live metadata. Add an explicit offline status and a visible banner or status detail when strict operations use it.

Suggested script header in offline mode:

```sql
-- Script generated from offline metadata snapshot.
-- Snapshot captured: 2026-07-06T15:12:03Z
-- Last validation: 2026-07-06T15:14:11Z
-- The live database was not checked for drift before this script was generated.
```

### R8. Keep module definitions and descriptions out of default cache

Columns, object names, types, keys, and FK relationships are structural metadata. Descriptions and module definitions can contain user-authored prose, SQL text, business logic, URLs, credentials accidentally placed in comments, or proprietary rules.

Default cache policy should be:

| Data class | Persist by default |
|---|---:|
| schemas, objects, columns, types, keys, FKs, params | yes |
| row counts | no until product decision |
| `MS_Description` | no initially, opt-in after privacy review |
| `sys.sql_modules.definition` | no by default |
| AI schema-context text | no, regenerate from snapshot |
| raw query rows | no |

### R9. Add cache observability now, even before the cache exists

Extend the metadata vocabulary with the cache fields now so later tests know where to look:

```text
metadataCache.load
metadataCache.save
metadataCache.validate
metadataCache.hit
metadataCache.miss
metadataCache.evict
metadataCache.corrupt
metadataCache.policyDecision
metadataCache.backgroundRefresh
```

Allowed fields:

- server fingerprint prefix;
- database hash or short fingerprint, not name by default;
- generation;
- readiness counts;
- cache source;
- stale age bucket;
- policy reason;
- duration;
- payload bytes;
- error class.

Never log object names, SQL text, rows, tokens, passwords, connection strings, raw server endpoints, prompt text, or module definitions.

### R10. Add persistent-cache performance gates before defaulting on

Disk cache sounds fast. Measure it before blessing it.

Suggested gates:

| Scenario | Target |
|---|---:|
| Load cached 10k-object catalog from disk | p95 < 50 ms after file read starts |
| Publish cache-loaded snapshot into store | p95 < 20 ms |
| First completion after extension restart with cache | p95 < 10 ms metadata wait |
| OE v2 first database folder from cache | p95 < 100 ms after connection/profile prepared |
| Background validation does not block F5 | 0 Busy errors in fake session stress |
| Corrupt cache recovery | no crash, live hydration starts, event emitted |

---

## 3. Potential problem areas needing extra attention

### 3.1 Stale metadata diagnostics

Completions can be stale. Diagnostics should be much stricter. A stale cached snapshot can easily report a missing column that actually exists after an external migration. The native diagnostic ladder should treat stale or unvalidated metadata as a suppression reason for binder diagnostics.

Recommended rule: only T1 lexical/structural diagnostics run offline or stale. T2 binder diagnostics require validated metadata for the touched object sections.

### 3.2 CHECKSUM-style digests are drift hints, not proofs

`CHECKSUM_AGG(CHECKSUM(...))` is useful and cheap, but it is not a cryptographic proof. It can collide, and it can ignore metadata not included in the expression. That is fine for background refresh triggers. It is not enough for strict scripting if fetching the object details is nearly as cheap as validating them.

Recommended wording in docs: cheap digest says "likely unchanged". Strict operations may still refresh relevant facts.

### 3.3 Permission changes can look like object drift

A user can lose permission to `sys.columns`, a database can become inaccessible, or a server can show a different database list after auth changes. Cache validation should record permission/access changes separately from schema changes where possible.

Suggested state:

```ts
staleReason: "permissionChanged" | "accessChanged" | "digestMismatch" | "ttlExpired" | "policyChanged" | "unknown"
```

### 3.4 Object IDs are not durable identifiers across generations

The current doc already notes object IDs are stable only within a generation. Persistent cache makes this even more important. Disk cache should store both object ID and natural identity `{database, schema, name, kind}`. When a strict consumer references an object from an older generation, re-resolve by natural identity before using the old object ID.

### 3.5 Database names and case sensitivity

The store correctly does not case-fold database names. The cache must preserve exact spelling in the logical model, but should hash path names for filesystem safety. Do not use raw database names as directory names unless escaped and privacy-reviewed.

### 3.6 Multiple extension hosts or windows

Two VS Code windows can connect to the same server/database and attempt to write the same cache. Use atomic file replace plus either a lightweight lock file or write-to-unique-temp then manifest-compare strategy. The simplest safe approach: readers never trust partially written payloads, and writers can overwrite only by manifest generation/captured time rules.

### 3.7 Cache invalidation after connection profile changes

Server, user, auth method, encryption/trust, tenant/account, and database identity affect what metadata is visible. Cache keys must include the connection-affecting fingerprint already used by the store. Do not share cache across users unless deliberately designed and privacy-reviewed.

### 3.8 Local privacy and workspace trust

A local cache can still be sensitive. It should live under extension global storage, respect a size/age limit, and be clearable. Consider disabling persistent cache in untrusted workspaces only if the cache is workspace-local. If the cache is global-storage-only and keyed by connection profile, workspace trust is less central, but still worth documenting.

### 3.9 AI completions and prompt replay

AI schema context should be regenerated from the snapshot to preserve byte identity and redaction rules. Do not persist rendered prompt fragments as the metadata cache. Prompt capture belongs to the feature-capture subsystem, not metadata cache.

### 3.10 Cache schema migrations

A cache that cannot migrate must fail closed and hydrate live. Use a manifest format version and codec version. A new code version should be able to ignore old cache safely.

### 3.11 Large catalog memory pressure

Current warm TTL/LRU handles live sessions, not disk payload memory. Cache-loaded snapshots can still be large. The store should support memory eviction independent of disk retention. Idle TTL governs sessions and memory entries; disk cache max size governs persisted files.

### 3.12 Strict OE v2 expand semantics

OE v2 can use cache to render quickly, but it should not show stale folders as current when its policy requires validation. The UX can show stale cached children with a spinner/status child while validating, or block the first expand briefly. Pick one policy and test it.

---

## 4. Suggested design/documentation updates

### 4.1 Add a freshness policy section to the metadata substrate doc

Proposed new section:

```text
11. Freshness policies: safe stale, validated, live, offline
```

Include the consumer matrix, policy types, and examples.

### 4.2 Add a persistent cache section

Proposed new section:

```text
12. Persistent cache: manifest, payload, privacy, atomic writes, migrations
```

Make clear that disk cache is a projection of published snapshots and that cache freshness is separate from section readiness.

### 4.3 Split "drift" into triggers and validation

Current drift is mostly triggers:

- DDL sniff;
- digest poll;
- explicit refresh.

Add validation language:

- validation TTL;
- section digests;
- object-scoped validation;
- strict refresh.

### 4.4 Add cache-aware diagrams

The updated TeX companion now includes proposed pages for consumer freshness policy and persistent cache architecture. Keep those diagrams next to the design so coding agents see cache as part of the substrate, not a loose bolt-on.

### 4.5 Add cache status to `MetadataStoreStatus`

Suggested extension:

```ts
export interface MetadataStoreStatus {
    readonly servers: readonly ServerStatus[];
    readonly databases: readonly DatabaseStatus[];
    readonly keyCorrectnessViolations: number;
    readonly cache?: {
        readonly enabled: boolean;
        readonly loadedEntries: number;
        readonly diskBytes?: number;
        readonly lastLoadError?: string;
        readonly lastSaveError?: string;
    };
}
```

### 4.6 Add a cache clearing command and status UI

Recommended commands:

```text
mssql.metadataCache.showStatus
mssql.metadataCache.clearAll
mssql.metadataCache.clearForConnection
```

Keep user-facing surface minimal at first. Internal status should be rich enough for dogfood.

---

## 5. Test plan improvements

### 5.1 Invariant tests

- Empty-vs-failed still holds after loading from disk.
- A cache-loaded snapshot and a live snapshot with identical content produce byte-identical schema context.
- One response never mixes memory generation N with live generation N+1.
- Object IDs from stale paths re-resolve by name/kind or fail explicitly.

### 5.2 Cache correctness tests

- Cache load publishes a snapshot with correct readiness and freshness metadata.
- Corrupt payload is ignored, event emitted, live hydration starts.
- Unsupported manifest version is ignored safely.
- Two writer race leaves either old valid cache or new valid cache, never partial cache.
- Cache max bytes evicts least-recently-used entries.
- Cache max age deletes old entries.

### 5.3 Freshness policy tests

- Completion returns stale cache immediately and schedules background refresh.
- Diagnostics suppress binder errors on stale metadata.
- OE expand validates on first expand and reuses within TTL.
- OE explicit refresh bypasses TTL.
- Scripting requires live refresh unless offline mode is explicitly set.
- Offline scripting emits snapshot banner and fidelity notes.

### 5.4 Drift tests

- DDL sniff marks affected database stale and queues refresh.
- Digest mismatch triggers refresh.
- Digest failure does not tight-loop.
- External table add/drop is detected by next validation.
- Permission loss changes access/readiness state and does not show old ready data as live.

### 5.5 Privacy tests

- Cache manifest contains no passwords, tokens, raw connection strings, prompts, SQL rows, or full endpoints.
- Module definitions are not persisted by default.
- Descriptions are not persisted by default.
- Telemetry events include only classified counts, durations, fingerprints, readiness, policy, and stale-age buckets.

### 5.6 Performance tests

- Large fixture load/save.
- Cold restart with cache.
- Background validation under user query load.
- Large-catalog OE folder expand with cache and without cache.

---

## 6. Recommended implementation sequence

### CACHE-0: Freshness policy API, no disk yet

Add `ensureFresh(policy)`, `FreshCatalogResult`, and policy constants. Implement against memory/live store only.

Exit gate: all consumers can state their policy without changing behavior.

### CACHE-1: Cache manifest and codec prototype

Implement serialization/deserialization for a snapshot envelope using JSON plus gzip first. Keep binary as a measured future option.

Exit gate: fixture snapshot round trips exactly enough to produce byte-identical schema context.

### CACHE-2: Disk cache coordinator

Add load/save, atomic writes, corruption handling, size/age eviction, and cache status.

Exit gate: cache can be loaded on acquire, ignored on corrupt, and cleared by command.

### CACHE-3: Safe stale consumers

Wire completions and AI schema context to use cached snapshots immediately. Keep diagnostics strict.

Exit gate: cold restart completions are instant from cache, background refresh updates generation.

### CACHE-4: Validated consumers

Wire OE v2 browse and hover to `requireValidated` with TTL. Add UI/status for validating/stale/offline.

Exit gate: first OE expand validates, subsequent short-window expands do not refetch, explicit refresh does.

### CACHE-5: Strict consumers

Wire scripting and definition to `requireLive` or targeted refresh. Offline mode explicitly downgrades.

Exit gate: strict script output always records whether it was live or offline snapshot.

### CACHE-6: Section/object digests

Add T2/T3 validation as evidence demands.

Exit gate: object-scoped strict operations refresh less than full database where safe.

---

## 7. Open decisions

| Decision | Recommendation |
|---|---|
| Cache codec | Start with JSON plus gzip. Move to binary only after measured need. |
| Persist descriptions | Off by default. Revisit after privacy review. |
| Persist module definitions | Off by default. Possibly allow explicit local-only opt-in later. |
| Default user setting | Keep persistent cache off until perf gates prove value, or enable internally only. |
| OE first-expand UX | Prefer short validation wait with loading node, then reuse TTL. Avoid showing stale as current. |
| Digest strictness | Cheap digest is a trigger, not proof. Strict operations refresh facts. |
| Serialized USE lane | Defer until session pressure evidence. |
| Cache encryption | Use OS/global-storage protections initially; consider optional encryption only if product requirements demand it. |
| Cache sharing | Per-profile/user fingerprint. No cross-user sharing. |

---

## 8. Bottom line

The metadata substrate is ready to grow a persistent cache, but only if freshness policy lands first. The design already has the right bones: immutable generations, pin-once reads, section readiness, key-correct sessions, refcounted leases, and privacy-conscious provider seams. The cache should be a speed layer over those bones, not a parallel skeleton.

Build freshness policy, then persistent snapshot cache, then safe stale consumers, then validated browse, then strict scripting. That sequence keeps the editor fast without letting stale metadata quietly pretend to be live truth.
