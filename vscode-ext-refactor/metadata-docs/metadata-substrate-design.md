# The Metadata Substrate — Deep Design Notes
## CatalogModel → MetadataService → MetadataStore, and its four consumers (Query Studio, native language service, AI completions, Object Explorer v2)

**Status:** as-built design record, written 2026-07-06 for deep review.
**Code truth:** vscode-mssql `dev/query` @ `59e78a296` (cache/drift CACHE-PRE..4 landed 2026-07-06); sqltoolsservice `dev/query` @ `7532d145`. Everything described here is implemented and tested unless explicitly marked *gap* or *future*.
**Companion:** `METADATA_DESIGN_VISUALS.tex` in this folder (TikZ diagrams, same visual language as the STS2 review pack).
**Lineage:** built across the Query Studio effort (B5/B6), the OE v2 effort (B15/B16), and the language-service effort (B9/B11/B12). Original specs: `ssms-query-docs/02-metadata-service-design.reviewed.md`, `oe-docs/metadata_service_oe_v2_design.md`. Where this document and those specs disagree, **this document describes what was actually built and why**.

---

## 0. One-paragraph summary

The metadata substrate is a three-layer stack. At the bottom, **`CatalogModel`** is a pure, immutable, structure-of-arrays snapshot of one database's schema with interned strings and per-section readiness. In the middle, **`MetadataService`** is a per-database *engine*: it hydrates snapshots from `sys.*` catalog queries over a dedicated data-plane session, bumps monotonic generations, detects drift, and never lies about failure. At the top, **`MetadataStore`** is the process-wide *registry*: it hands out refcounted **leases** to server catalogs and database catalogs, guarantees key-correctness (database A's catalog can never contain database B's objects), and bounds session pressure with idle TTL + LRU. Four consumers sit on top through two narrow seams — the language-provider seam (`ISqlLanguageMetadataProvider`/`IPinnedMetadataView`) and the lease surface itself — and every consumer obeys the same two disciplines: **pin once per response** (never mix generations) and **failure is never emptiness**.

---

## 1. Layer 1 — CatalogModel (the pure snapshot)

`src/services/metadata/catalogModel.ts`. No `vscode`, no I/O, no timers. Two classes: `CatalogBuilder` (streaming appends during hydration) and `CatalogSnapshot` (immutable reads).

### 1.1 Storage: structure-of-arrays + string interning

The builder keeps parallel arrays per entity family rather than object graphs:

| Family | Arrays (appended in hydration order) |
|---|---|
| schemas | `schemaIds`, `schemaNameSyms` |
| objects | `objectIds`, `objectSchemaIds`, `objectNameSyms`, `objectKinds`, `objectModifyDates` |
| columns | `columnOwner` (object *index*, not id), `columnNameSyms`, `columnTypeSyms`, `columnNullable`, `columnIdentity`, `columnComputed` |
| FK edges | `fkFrom`, `fkTo`, `fkNameSyms`, `fkConstraintIds` |
| FK column pairs | `fkColumnConstraintIds`, `fkColumnFromSyms`, `fkColumnToSyms` |
| PK columns | `pkOwner`, `pkColumnNameSyms` (key-ordinal order) |
| key constraints | `keyConstraintOwner`, `keyConstraintNameSyms`, `keyConstraintKinds`, `keyConstraintColumnSyms` (consecutive rows per constraint — ordering is load-bearing, see §2.2/H4) |
| parameters | `paramOwner`, `paramOrdinals`, `paramNameSyms`, `paramTypeSyms`, `paramOutput` |
| descriptions (H7) | `descriptionOwner`, `descriptionColumnSyms` (−1 = object-level), `descriptionValueSyms` |

All strings pass through one intern table (`strings[]` + `stringIndex` map). Rationale:

- **Memory**: a 10k-object catalog holds tens of thousands of repeated type names (`int`, `nvarchar(100)`) and schema names; interning collapses them to symbol integers.
- **Comparison speed**: name-equality during binding/search is integer comparison after one fold.
- **Determinism**: the same hydration input produces byte-identical internal state — a prerequisite for the AI schema-context byte-identity guarantee (§6.3).

**Review note — array-order invariant:** several read paths (`getColumns`, `getKeyConstraints` run-grouping, parameter ordering) depend on hydration append order. This is documented at each site, and additions are required to be *append-only after existing arrays* (H7 followed this rule). A reviewer should treat any reordering of builder arrays as a red flag.

### 1.2 Read surface

`CatalogSnapshot` (constructed by `builder.build(generation, readiness, mode)`) exposes: `listSchemas()`, `getObject(objectId)`, `listObjects(schema?, kinds?)` (sorted schema-then-name — the OE folder enumeration path, deliberately *not* an empty-prefix search hack), `getColumns`, `getPrimaryKeyColumns`, `getKeyConstraints` (PK + UNIQUE with names, key-ordinal column order), `getForeignKeysFrom/To`, `getForeignKeyDetailsFrom/To` (edges + ordered column pairs, both directions), `getParameters`, `getDescription(objectId, column?)`, `search(prefix, limit)` (folded-name index), `resolveName(parts)` and `buildSchemaContext(req)` (§6).

`resolveName` is **collation-aware**: case-sensitive catalogs never accept a folded-only match; ambiguity returns `{kind:"ambiguous", candidates}` — *reported, not guessed*. This one decision propagates all the way up: the language binder refuses instead of guessing, diagnostics suppress instead of false-positive, hover declines instead of overclaiming.

### 1.3 Sections and readiness (the honesty backbone)

```ts
type CatalogSection = "schemas" | "objects" | "synonyms" | "columns" | "types" | "keys"
                    | "foreignKeys" | "indexes" | "constraints" | "parameters"
                    | "descriptions" | "rowCounts";
type SectionState  = "absent" | "loading" | "ready" | "failed" | "stale" | "lite";
```

Every snapshot carries a complete `readiness: Record<CatalogSection, SectionState>` (unset sections are `"absent"`, never silently `"ready"`). The **empty-vs-failed rule** is the substrate's most important behavioral invariant:

> An empty array means "ready and truly empty" **only** when the section state is `ready`. A failed hydration section is published as `failed` and the snapshot's mode drops to `partial`. Consumers must render failure as failure (error node, suppressed diagnostic, declined hover) — never as an empty folder or empty completion list.

`indexes`, `constraints`, and `rowCounts` are declared-but-not-hydrated today (*gap*, §9) — they exist in the type so consumers can already gate on `"absent"` honestly.

---

## 2. Layer 2 — MetadataService (the per-database engine)

`src/services/metadata/metadataService.ts`. One engine instance owns one `CatalogKey = { serverFingerprint, database }` entry map, one `MetadataSessionSource`, hydration, drift, and generation bumping.

### 2.1 The dedicated-session rule

Hydration and polling run on a **dedicated data-plane session** (`applicationName: "vscode-mssql-metadata"`, `commandKind: "metadata"`, `priority: "background"`), never on the user's interactive session. Rationale: STS2 sessions allow **one active query**; a hydration burst on the user's session would make F5 race into `Busy`. The dedicated session costs one extra connection per (server, database) but buys total isolation of user latency from metadata work. (Bound by the store's TTL/LRU — §3.4.)

**The session lane (`runExclusive`, added B12):** hydration passes, digest polls, and lazy module-definition reads all share that one-active-query session, so the engine serializes them through a per-entry promise lane. Before this, a lazy read racing a digest poll could hit `Busy`; now everything queues. A cold go-to-definition can therefore wait behind an in-flight hydration — a recorded, acceptable trade (B14's head-to-head must account for it).

**The completion-reaction discipline:** every internal query awaits `handle.completion` — *not* the sink callback — because the data-plane session frees its active-query slot in the completion promise's reaction order. Synchronizing on the sink races the next execute into `Busy`. This bug was found twice independently (B5 hydration, B4 helpers) before the discipline was written down; it is now a comment at every call site and a paragraph here because a reviewer *will* be tempted to "simplify" it.

### 2.2 Hydration ladder (H0–H7)

Sequential `sys.*` queries, each parsed with bit-tolerance (`row[n] === true || row[n] === 1` — the wire delivers both forms):

| Pass | Source | Yields | Failure policy |
|---|---|---|---|
| H0 | `SERVERPROPERTY` / `SCHEMA_NAME()` / `DATABASEPROPERTYEX` | engine edition, default schema, collation → `caseSensitive` | best-effort: defaults survive a failed probe |
| H1 | `sys.schemas` (`schema_id < 16384`) | schemas | hard: hydration fails |
| H2 | `sys.objects` (`U,V,P,FN,IF,TF,SN`, not ms-shipped) | objects + synonyms + `modify_date` | hard |
| H3 | `sys.columns` ⋈ `sys.types` | columns, `typeDisplay` (`nvarchar(max)` etc.), nullability, identity, computed | **section-failed** → `columns: failed`, mode `partial` |
| H4 | `sys.indexes` ⋈ `sys.index_columns` (`is_primary_key OR is_unique_constraint`) | PK column *marks* (PK rows only) + named key constraints (PK + UQ, key-ordinal order) | section-failed |
| H5/H5B | `sys.foreign_keys`, `sys.foreign_key_columns` | FK edges + ordered column pairs (both directions readable) | section-failed |
| H6 | `sys.parameters` ⋈ `sys.types` | routine parameters (ordinal 0 = scalar return) | section-failed |
| H7 | `sys.extended_properties` (class 1, `MS_Description`; columns via `COL_NAME()`) | object + column descriptions | section-failed (`descriptions`) |

Design notes worth reviewing:

- **H4 was extended, not forked**, when OE v2 needed constraint *names* (B16): the same query now feeds both the legacy PK-column marks (behavior-identical) and the named-constraint arrays. Unique-constraint columns are *never* PK-marked.
- **H7 deliberately avoids a `sys.columns` join** (uses `COL_NAME()`), because test fixtures match hydration queries by substring and H3's matcher claims `sys.columns`. This "matcher-collision" hazard is real enough that it is documented in three fixture files; the discipline is: *new hydration SQL must not substring-collide with earlier matchers* (see also `CHEAP_DIGEST` containing H2's `FROM sys.objects o WHERE` — digest fixtures must precede H2 fixtures).
- **H7 values are `CAST(... AS nvarchar(4000))`** — longer descriptions truncate silently. Fine for hover; recorded as a fidelity note for scripting (§6.4).
- **Descriptions never enter AI projections** (§6.3 privacy gate).

### 2.3 Generations

Each successful hydration bumps `generation` and publishes a **new immutable snapshot**; the old one remains valid for anyone still holding it. Generations are monotonic per entry and *scoped to that entry* (server-catalog generations are independent). Two rules follow:

1. **Pin once per response.** A consumer answering one request (a completion, one tree expand, one hover) reads exactly one snapshot. It may be one generation behind — that is fine; mixing two generations in one answer is not.
2. **Object ids are stable within a generation, not across.** After refresh, stale object ids are stale-path *errors* that recover by re-resolving name/kind (OE renders an explicit "object not found in this catalog generation" node; definition re-resolves).

### 2.4 Drift: sniff, digest, refresh

Three triggers, cheapest-first:

- **A — DDL sniff**: consumers report executed batches (`notifyExecutedBatch`); the shared lexer's `leadingKeyword` classifies `CREATE/ALTER/DROP/SP_RENAME` → immediate forced re-hydrate; `EXEC/EXECUTE` → digest check (dynamic SQL *might* have DDL'd).
- **B — digest poll**: every 60s while any handle is alive, `CHECKSUM_AGG(CHECKSUM(object_id, modify_date))` + count. Change → forced re-hydrate. Poll failures are silently skipped (never queued, never retried in a tight loop).
- **C — explicit refresh**: `lease.refresh()` / OE refresh commands.

**Hydration serialization (a real bug fixed in B15):** forced refreshes originally *overlapped* the in-flight hydration; on a one-active-query session the two runs raced into `Busy` and could both fail. It passed B5-era tests only through lucky promise-reaction interleaving; the store's concurrent A/B isolation test shifted the phase and exposed it. The fix: a forced refresh **chains after** the in-flight run (`hydrating.catch(()=>{}).then(() => hydrateCore())`), with identity-guarded clears. *Reviewer takeaway:* every await point in this engine has been a race at least once; the tests that guard them are load-bearing.

### 2.5 Lazy detail reads (B12)

Module definitions (`sys.sql_modules`) are **not** an H-pass: they are per-object, on-demand (`getModuleDefinition(objectId)`), cached per generation (cleared on hydrate), in-flight-deduped, and run through the session lane. `OBJECTPROPERTY(..., 'IsEncrypted')` disambiguates *encrypted* from *permission-denied* from *not-loaded*; failures are never cached. This is the template for future lazy sections (index DDL, computed-column expressions): **bulk-hydrate what browse/bind needs; lazy-read what scripting needs.**

---

## 3. Layer 3 — MetadataStore (the shared registry)

`src/services/metadata/metadataStore.ts` + `metadataStoreService.ts` (process-lifetime singleton, mirroring `SqlDataPlaneService`). This layer exists because OE v2 made the old shape untenable: one `MetadataService` per Query Studio document, with a session source that ignored the requested database, cannot serve a tree that expands many databases under many servers.

### 3.1 Identity and keys

```ts
ServerKey   = { serverFingerprint }                 // sfp_<22 b64url of sha256> — EXCLUDES database
DatabaseKey = { serverFingerprint, database }       // exact spelling, NOT case-folded
```

`profileFingerprint.ts` produces two scopes from connection-affecting facts (server, user, authKind, encrypt, trust — plus database for the profile scope `pfp_`). Both are sha256-derived and **non-reversible**; this replaced the original `qsfp_` recipe, which was a truncated base64 of the raw parts and *decoded to plaintext server/database/user* — a violation of the `SqlConnectionProfileRef` contract ("never reversible") that had gone unnoticed because nothing ever decoded it. In-memory keys only, so the recipe change invalidated nothing persistent.

Database names are deliberately **not case-folded for keying**: name case-sensitivity is a server-collation fact, and backends report canonical spelling on context changes (ENVCHANGE). Folding would merge catalogs that a case-sensitive server considers distinct.

`stableProfileId()` (profileAuthAdapter) is the one shared recipe for *profile identity* (saved id, else deterministic derivation) — OE v2 tree nodes and Query Studio's open-from-context path must agree on it, and a test pins that agreement.

### 3.2 Key-correctness (the load-bearing fix)

**The original defect:** `MetadataSessionSource.open()` took no key; `DataPlaneMetadataSessionSource` cached one session at whatever database it was constructed for. `acquire({database:"A"})` and `acquire({database:"B"})` could both hydrate against the same physical database. Harmless with one document/one database; disqualifying for a multi-database tree.

**The built solution (preview-safe strategy):** each `DatabaseKey` gets its **own** dedicated session, opened with `OpenSessionParams.database = key.database` — key-correct *by construction*. A wrapper source additionally verifies `session.info.database === key.database` after open and, on mismatch, increments a counter in `store.status()` and emits `metadataStore.keyCorrectness.violation` — a **tripwire, not a correction**: the store does not silently retry, because a backend that ignores the requested database is a bug to surface, not paper over. (Empty `database` key = "profile default"; the check is skipped since there is no expectation to verify.)

**The alternative not built (yet):** one server-scoped session with a serialized `USE [db]` lane. Cheaper in sessions for many-database servers, but harder to prove correct (every query group must be fenced by a context switch; cancel/timeout in the middle of a group leaves the lane's context suspect). The key-aware acquisition surface was designed so this can be swapped in later without touching any consumer. Worksheet trigger: session pressure evidence from large-server dogfood.

**Proof obligations (all in the suite):** concurrent A/B acquisition with distinct fixture objects never cross-contaminates; refresh of A during B's hydration stays isolated; the tripwire fires against a database-ignoring backend.

### 3.3 Leases

```ts
ServerCatalogLease   { key, status(), pin(): IPinnedServerCatalogView, refresh(), onDidChange, dispose }
DatabaseCatalogLease { key, status(), current(): CatalogSnapshot|undefined, buildSchemaContext(),
                       notifyExecutedBatch(), getModuleDefinition(), refresh(), onDidChange, dispose }
```

Design choices:

- `DatabaseCatalogLease` is **structurally assignable** to the pre-store `MetadataCatalogHandle` (`ReturnType<MetadataService["acquire"]>`). This is why migrating Query Studio and the language provider onto the store (B16) required *zero changes in consumers* — the lease simply superset the handle. Deliberate: structural typing as a migration tool.
- Leases are refcounted per key; the *entry* (engine + session) is shared. Double-dispose is inert. Listener callbacks are isolation-wrapped (one consumer's throw cannot break another's notifications).
- `pin()` on the server lease returns an immutable view (list + name map captured at pin time) — the same pin-once discipline as snapshots.

### 3.4 Lifecycle: warm reuse, TTL, LRU

When a key's refcount reaches zero the entry **stays warm** for `idleTtlMs` (default 120 s) — a re-acquire within the window is a cache hit with the catalog instantly available (proven: warm re-acquire performs no second hydration, generation unchanged, no new session). Zero-ref entries beyond `maxIdleDatabases` (default 4) are evicted oldest-released-first. Timers are `unref()`'d.

**Recorded behavior change:** after Query Studio disconnect, its metadata session now lingers warm ≤ TTL rather than closing immediately. This is the intended store semantic (reconnect/database-switch is instant); noted because a user watching server sessions will see it.

### 3.5 ServerMetadataService

The server-scoped catalog (visible databases + server facts) — previously a Query Studio host seam (`executionHost.listDatabases`), now first-class:

- Query: `sys.databases` with `HAS_DBACCESS(name)` — **no WHERE filter**. Inaccessible databases are *listed* with `accessState: "inaccessible"` (SSMS shows them; hiding them misrepresents the server). `NULL` → `"unknown"`. `database_id <= 4` → `isSystem`.
- Readiness `absent | loading | ready | failed`; on failure the previous list is **dropped from state** (a failed catalog must not masquerade as a stale-ready one) and `listDatabases()` returns `undefined` — *not* `[]`.
- Server facts (version, edition, login) captured from the session at hydrate.

---

## 4. The two consumer seams

### 4.1 Language-provider seam (`ISqlLanguageMetadataProvider` / `IPinnedMetadataView`)

`src/sqlLanguage/provider/types.ts` (pure) + `provider/catalogProvider.ts` (the adapter). This seam exists so the language engine is **rehostable**: the engine never sees `MetadataService`, the store, or the data plane — only `generation`, `env()`, `readiness()`, `pin()`, `databases()`, `requestHydration()`, `onDidChange()`, and a pinned view of resolve/columns/keys/FKs/params/search/schemas/descriptions/definitions. `NullProvider` and `FixtureProvider` implement it for offline honesty and fourslash tests; a future host (different editor, different metadata origin) implements it once.

Adapter honesty rules (each one test-pinned): `getDescription` only when `descriptions === "ready"`; `getKeyConstraints` only when `keys === "ready"`; `definitions` readiness reported as `"lazy"` with `getDefinition` delegating to the lease's lazy read; `fkTo` serves reverse edges *with column pairs* (closed in B12 — the pinned view originally returned empty pairs on the reverse side, a B11 finding).

### 4.2 Lease surface (OE v2, scripting)

OE v2 and scripting consume leases directly (they need `listObjects`, constraint names, server catalogs, module text — wider than the language seam). The rule keeping this sane: **the lease/pinned surfaces are the only truth sources.** OE v2's coordinator is a convenience wrapper over leases, not a second metadata implementation.

---

## 5. Consumers, one by one

### 5.1 Query Studio

`DocumentSessionBinding` prepares the profile (shared `prepareConnection`: fingerprints + passwordProvider closure — passwords exist only inside the closure, resolved from the credential store at open time), then acquires one `DatabaseCatalogLease` for the connection's current database. On `onDidChangeDatabase` (typed `USE` lands via the service's ENVCHANGE-truth `database` field on `v2/query.complete`), the binding **swaps leases** — release old key, acquire new key. Warm TTL makes A→B→A switches instant. Executed batches feed the DDL sniffer (`notifyExecutedBatch`). QS state surfaces `MetadataStatus` (readiness/generation/mode) to the status bar.

### 5.2 Native language service

The engine's analysis cache keys work on `(document version, provider generation)`; the B10 diagnostics scheduler additionally **cancels in-flight passes when the generation changes** — metadata movement invalidates conclusions mid-pass. Consumption pattern per feature:

- **Completions (B9):** pinned view per request; FK join predicates and FK-adjacency ranking come straight from `getForeignKeyDetailsFrom/To`; star expansion refuses when `columns !== "ready"` (`isIncomplete + incompleteReason` — honest partial results).
- **Diagnostics (B10):** the **suppression ladder** is the metadata-honesty contract at its most explicit — 16 counted reasons (`providerNotReady`, `columnsNotReady`, `databaseNotHydrated`, `crossDatabaseUnhydrated`, `linkedServer`, `opaqueSource`, `dynamicSql`, `tempTableUnknown`, …). Suppress-never-guess: a 62-case corpus asserts *zero* unexpected diagnostics across every metadata-degradation shape. Suppression counts (never identifier text) ride diagnostics telemetry.
- **Hover/signature (B11):** claims are gated per-section (`columns==="ready"` strictly for column counts); overlay shapes only when trustworthy (`alteredNames`, SELECT-INTO caveats).
- **Definition/scripting (B12):** lazy module reads; synthesized `CREATE TABLE` from columns+keys+FKs with **fidelity notes** enumerating what was *not* included (indexes/defaults/checks — sections that don't exist yet). Scripts never fabricate: encrypted/permission-denied module text is an honest refusal.

### 5.3 AI completions (the schema-context projection)

Three stages, the privacy- and determinism-critical path:

1. **`catalogSchemaContextPayload.ts`** synthesizes the raw payload from a `CatalogSnapshot` — this *replaced* a 3.7k-line service-side mega-query when the completions branch was ported (B6). A curated static system-DMV catalog (engine-edition-scoped) substitutes for live DMV probing.
2. **`completionSchemaContextCore.ts`** — the selection pipeline extracted *verbatim* from the legacy implementation: relevance terms, ranking, char budgets, degradation tiers, normalization.
3. **`buildSchemaContext` (snapshot)** — deterministic rendering. **Byte-identical** output for the same (generation, request) is a hard guarantee: the MD-4 golden-parity suite (10 tests) pins exact prompt lines, and *every* substrate change since B5 has had to keep it green (H4 names, H7, reverse pairs — all additive around it). Replay comparisons and prompt caching depend on this.

Resolver chain for the *classic* editor: QS binding lease first, else a store-backed acquisition over the classic connection's facts (first-hydration wait 120 s, LRU 8). **Privacy gates:** `remoteLm` requests exclude `MS_Description` content (addendum §9 — user-authored text does not ride to remote models until that question is settled; a test pins descriptions out of schema context entirely), and schema-context *text* never enters DiagEvents (prompts are feature-capture territory with its own redaction envelope).

### 5.4 Object Explorer v2

`OeV2MetadataCoordinator` (one per connected v2 connection) holds the server lease and lazily-acquired database leases; store change events drive *targeted* tree refresh. Browse rules map substrate states to UI honestly (the §13 table of oe_view_design, implemented in `oeV2Browse.ts`):

| Substrate state | Tree rendering |
|---|---|
| catalog loading / absent | loading child |
| section `ready`, zero rows | "No items" |
| section `failed` | error child with refresh (never empty) |
| database `accessState: inaccessible` | non-expandable node, permission-denied readiness |
| stale object id after refresh | explicit "not found in this catalog generation" error child |
| mode `partial` | ready sections render; status child names the failed ones |

Pin-once-per-expand; database leases acquire on database-node expand (never bulk on connect); folder enumeration via `listObjects`; keys/FKs/params from the B16 named-constraint and reverse-pair surfaces. The no-v1 tripwires (lint boundaries + sinon spies + live scenario) guarantee none of this ever touches classic OE RPCs.

---

## 6. Cross-cutting: privacy and observability

- **Classification discipline:** every diag field is `{raw, cls}`-classified. Database names ride as `source.path`/`database.name` class; object names, SQL text, rows, endpoints, secrets **never** enter metadata diagnostics. Fingerprints in events are the short (12-char) non-reversible prefix.
- **Registered vocabulary:** `metadata.*` (hydrate span, drift instant, contextBuild span) and `metadataStore.*` (acquire/dispose/session/hydrate.server/keyCorrectness.violation, cache hit/miss) — all in the contracts registry with attr classification notes; unregistered emissions are conformance-test failures (a real one was caught in B7).
- **Privacy canaries:** fingerprint outputs and `store.status()` dumps are asserted to leak no server names/users/passwords; the AI path has its own canaries (prompts/schema text never plaintext in redacted traces).

---

## 7. Performance (measured, not estimated)

| Operation | Measured | Context |
|---|---|---|
| Full hydration through the store, 10k objects / 81k columns / 2k FKs | **148 ms** wall | unit lane, FakeBackend |
| `listObjects()` over 10,201 objects (sorted) | **10 ms** | 〃 |
| `search("T0099", 50)` over 10k names | ~0 ms | folded-name index |
| `getColumns` on a 1000-column table | ~0 ms | SoA slice |
| Warm re-acquire (same key, within TTL) | instant, no re-hydration | generation unchanged |
| OE v2 live: connect → server catalog → Databases rendered | **338–416 ms** | real STS2 + SQL Server (scenario, 4/4) |
| Warm native completion over the pinned view (2k-line doc) | median 0.05 ms / p95 0.15 ms | B9 bench |
| QS 10k-row query gates with metadata acquisition on the connect path | 389–1100 ms band, unchanged across all substrate batches | 28-rep standing gates |

The oe_view_design §15 host-work targets (warm folder expand < 30–150 ms) are met with an order of magnitude to spare in the unit lane; the live wallclock is backend-bound.

---

## 8. Decision log (with alternatives)

| # | Decision | Alternatives considered | Why this one |
|---|---|---|---|
| D1 | SoA + interning snapshot | object-graph model; keep server-side (STS v1) metadata | memory + determinism + pure/rehostable; server-side was the thing being removed |
| D2 | Dedicated metadata session per database key | share the user session; server lane + serialized `USE` | user-latency isolation is non-negotiable; per-db is provable today, lane can swap in behind the key-aware source later |
| D3 | Sections fail independently; mode `partial` | all-or-nothing hydration | a permission-denied `sys.columns` shouldn't take down object browse |
| D4 | Generations immutable + pin-once | mutable catalog with change events per entity | consumer correctness is trivially auditable; replay/parity need it |
| D5 | Store leases with structural handle-compat | migrate every consumer to a new interface in one go | zero-churn migration (B16 proved it: QS/LS unchanged) |
| D6 | Hash fingerprints, server-scope excludes database | keep `qsfp_` (reversible); include database in ServerKey | contract compliance; a server key that varies by default database fragments the server catalog |
| D7 | Key-correctness tripwire (count + event, no auto-retry) | silent retry with corrected database | a lying backend is a bug to surface; retries mask it |
| D8 | TTL+LRU warm cache, default 120 s / 4 idle | close on zero-ref; unlimited warm cache | instant reconnects vs bounded session pressure; defaults are settings-free until evidence demands tuning |
| D9 | `HAS_DBACCESS` as state, not filter | `WHERE HAS_DBACCESS = 1` (the spec's first draft) | SSMS parity; hiding inaccessible databases misdescribes the server |
| D10 | Lazy per-object module reads through the session lane | bulk H-pass for `sys.sql_modules` | module text is big and rarely needed; the lane keeps one-active-query safe |
| D11 | Byte-identical schema context as a hard test | "close enough" prompt equivalence | replay comparisons, prompt caches, and regression detection all break under drift |
| D12 | Descriptions excluded from remoteLm projections | include with a setting | user-authored text to remote models is a one-way privacy door; deferred until explicitly decided |

---

## 9. Known gaps and future work (honest list)

| Item | State | Trigger to act |
|---|---|---|
| `indexes` / `constraints` (defaults, checks) sections | declared, not hydrated; scripting emits fidelity notes | scripting F2+ fidelity demand, OE index/constraint folders |
| `rowCounts` (H8) | declared, not hydrated | product decision to display counts |
| Disk cache (manifest + `catalog.mdc`) | not built | LS/OE cold-start measurements say warm-start matters |
| Deep digest tiers / scoped delta refresh / 30% rule / metadata-lite | cheap sniff+digest only | drift-scale or large-catalog evidence |
| Serialized-`USE` server lane | interface ready, not built | session-pressure evidence (50-db expand-all dogfood) |
| `metadataPermission` suppression reason | not derivable from the provider today | provider surfacing of per-section permission causes |
| Live 10k-object catalog scenario | unit-lane fixtures only | seeded large catalog on the harness server |
| H7 4000-char truncation | accepted for hover | scripting fidelity demand |
| OE H2/H3 handoff-node fixture capture | constructor-based adapter, runtime-guarded | MV-ledger dogfood pass |

---

## 10. Suggested review path

1. **Invariants first:** §1.3 (empty-vs-failed), §2.3 (generations), §3.2 (key-correctness). These three carry everything else.
2. **Race discipline:** §2.1 (completion-reaction), §2.4 (hydration chaining), §2.5/§2.1 (session lane). Read the tests: `metadataStore.test.ts` (A/B isolation, tripwire), `metadataCatalog.test.ts` (B12 lazy-read suite).
3. **The seams:** §4 — is the language seam narrow enough to rehost, and is the lease surface wide enough for OE/scripting without leaking store internals?
4. **The projection:** §6.3 byte-identity + privacy gates — the highest-consequence consumer contract.
5. **Decision log** (§8) against your own priors; **gaps** (§9) against the release plan tiers.

Companion diagrams: `METADATA_DESIGN_VISUALS.tex` — layering, key/lease lifecycle, hydration/drift machine, consumer flows, and the honesty map.

---

## 11. Freshness policies: safe stale, validated, live, offline (as built, CACHE-0)

Readiness and freshness are **separate dimensions**: readiness answers "is this section trustworthy in this snapshot", freshness answers "is this snapshot recent/validated enough for this caller". The as-built readiness vocabulary is untouched — its `stale` still means *re-hydration in flight over an existing snapshot*; age-based staleness only ever appears in `FreshCatalogResult.freshness`.

Consumers declare a `MetadataFreshnessPolicy` (`allowStale | requireValidated | requireLive | offlineSnapshot` + reason, sections gate, TTLs, wait budget) against `lease.ensureFresh(policy)` on both scopes. The decision procedure (addendum §4.2, implemented exactly in `metadataService.ts`): memory-TTL tier first, then a **coalesced** T1 digest validation (all concurrent `requireValidated` callers share one digest query), `changed` awaits the chained refresh before resolving, failure rows follow C-7 (the retained snapshot stays readable; strict callers refuse on *freshness*, never on a missing snapshot). **Timeouts are races, never cancellations** — a timed-out caller stops waiting while the shared lane work completes for everyone else. Preset policies (`MetadataPolicies`): completion/aiContext (allowStale + background-refresh triggers), diagnosticsBinder (requireValidated, 250 ms wait budget — on miss diagnostics *suppress*, they never block), oeBrowse (requireValidated, 120 s TTL, 5 s budget), scriptingStrict (requireLive, 15 s).

The lane watchdog (H-2) bounds every session operation (hydration 60 s, digest/lazy 15 s): a completion that never arrives fails the one operation (error class `laneTimeout`), an `opEpoch` guard bars the abandoned run from ever mutating the entry, and the wedged session recycles on the next lane item. `refresh()` still never rejects.

## 12. Persistent cache: manifest, payload, privacy, atomic writes (as built, CACHE-1..4)

The disk cache is a **projection of published snapshots** (never raw `sys.*` rows, never a second model): `CatalogCachePayloadV1` serializes the SoA arrays in a frozen canonical order (`cm1` — a model change is a clean miss, never a migration), rehydration **adopts arrays verbatim** (symbol ids preserved), and `contentHash` (`csh_` + sha256 of the canonical payload) makes live-vs-rehydrated identity trivially provable — the §6.5 round-trip proof pins byte-identical schema context, folded search, and environment (including BIN2 case sensitivity) on every codec change. Privacy: descriptions and module definitions are **never persisted in v1**; loads intersect the manifest against the *current* policy in both directions (excluded/absent sections come back `absent` — never ready-and-empty); bytes-on-disk canaries assert no names/prose/secrets.

Write protocol (H-4): same-directory temp files, fsync-then-rename with Windows EPERM retry, manifest-last — every readable state is old-valid or new-valid (torn-write matrix pinned); two writers converge with a `raceLost` event for the loser. Store integration (CACHE-3): a fresh acquire loads disk **before** live hydration and publishes at the manifest generation; a background refresh is **mandatory** (C-4.1); the first live digest compares against the manifest's recorded digest (C-4.2 — the baseline is never seeded from it); failed refreshes over a retained snapshot re-arm with backoff (C-4.3). Consumers: the classic AI resolver now goes through the shared store (a disk hit answers a cold restart instantly; the old private-engine + raw 120 s wait is gone), QS completions fire the policy without awaiting it, and binder diagnostics suppress on unvalidated metadata via two new counted reasons (`metadataNotValidated`, `metadataStale`). Everything ships behind `mssql.metadataCache.enabled` (default **false**) until the acceptance gates pass.

Still open at this layer: server-catalog disk cache (and with it the C-7 two-case failure rule), manifest digest recording (waits on a validation-notify seam), T2/T3 section/object digests (CACHE-7, evidence-gated), and the §9 perf scenario family.
