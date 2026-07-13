# Metadata Cache & Drift — Review Addendum for Implementation
## Corrections, hardening, and contract clarifications layered on `metadata_cache_drift_design.md`

**Status:** review addendum, 2026-07-06. Written to be handed, together with the three base documents, to the code-gen agent.
**Applies to:** `metadata_cache_drift_design.md` (the plan of record), `metadata-substrate-design.md` (as-built truth), `metadata_design_review.md` (prior review — this addendum extends it, it does not repeat it).
**Code truth checked:** `microsoft/vscode-mssql` `dev/query` HEAD as fetched 2026-07-06 (`extensions/mssql/src/services/metadata/*.ts`, `sqlLanguage/provider/*.ts`); `microsoft/sqltoolsservice` `dev/query`; `kburtram/perftest` `dev/query`. Where this addendum quotes code, it quotes those files, not the design prose.
**Companion:** `METADATA_DESIGN_VISUALS_ADDENDUM.tex` / `.pdf` (pages A1–A6, same visual language as v2). Page references below use `A#`.

---

## 0. How to read this addendum (agent instructions)

- **Precedence.** Where this addendum conflicts with `metadata_cache_drift_design.md`, this addendum wins. Where it conflicts with `metadata-substrate-design.md`'s description of *already-built* behavior, the built behavior wins until a finding below explicitly changes it.
- **Normative keywords.** `MUST` = build it this way; a deviation needs Karl's sign-off recorded in the progress journal. `SHOULD` = do it unless there is a concrete, journaled reason not to. `CONSIDER` = optional, measure first.
- **Finding IDs.** `C-n` are corrections (the base design or current code is wrong or ambiguous enough to produce a bad implementation). `H-n` are hardening items (the design is right but incomplete for real-world conditions). Every C/H item ends with the batch it belongs to (mapped to CACHE-0…7 from the base design, plus a new **CACHE-PRE** batch defined in §11).
- **Do not renegotiate the base invariants.** Pin-once, failure-is-never-emptiness, key-correctness-by-construction, snapshot purity, and the byte-identity gate are all reaffirmed here. Several findings below exist precisely to keep those invariants true once a disk layer appears.

---

## 1. Verdict

The cache/drift design is ready to build. Its two best decisions — freshness policy lands *before* any disk I/O, and the disk cache is a projection of published snapshots rather than a second model — should be defended against every convenience shortcut during implementation. The implementation order in §21/§24 of the base design (CACHE-0 → CACHE-7) is correct and is kept, with one new preparatory batch (CACHE-PRE, §11) that fixes three latent defects in the as-built substrate which the cache would otherwise freeze into persisted artifacts.

The findings below are ordered by consequence, not by discovery.

---

## 2. Corrections (C-series)

### C-1. `buildSchemaContext` ordering is ICU-dependent; the byte-identity guarantee is currently machine/version-scoped — fix before the codec freezes it  **[CACHE-PRE]**

**What the code does today.** `catalogModel.ts` builds the folded search index with a code-unit comparator (deterministic), but every user-visible ordering — `listSchemas()`, `listObjects()` (schema-then-name), and the candidate/render tiebreaks inside `buildSchemaContext` — uses `String.prototype.localeCompare`:

```ts
// listObjects
(a, z) => a.schema.localeCompare(z.schema) || a.name.localeCompare(z.name)
// buildSchemaContext final tiebreak
return a.schema.localeCompare(z.schema) || a.name.localeCompare(z.name);
```

`localeCompare` delegates to the embedded ICU collator. Its output is deterministic *within one Node/Electron build* but is not stable across VS Code updates (Electron bumps ship new ICU), across platforms, or between the extension host and any future rehost. Names containing `_`, digits, or non-ASCII characters sort differently under ICU default collation than under ordinal comparison (`Order_Details` vs `OrderHeader` is the canonical SQL-world case: ICU typically ignores the underscore's weight; ordinal does not).

**Why the cache makes this urgent.** Today the MD-4 golden suite pins byte-identity on one machine, so the hazard is invisible. The cache design explicitly promises (§22, acceptance gate 1): *cache-loaded and live snapshots produce identical schema-context text for equivalent data* — including after an extension restart that may also be a VS Code upgrade. It also feeds prompt caching and replay comparison, both of which cross process boundaries by definition. An ICU bump would silently invalidate every cached prompt and produce replay "diffs" with zero semantic change.

**Required change.**
1. MUST replace `localeCompare` with an ordinal, locale-independent comparator in every path that feeds `buildSchemaContext` output or any persisted/replayed ordering. Recommended comparator (matches the existing folded-index discipline):
   ```ts
   const ord = (a: string, b: string): number => {
       const fa = a.toLowerCase(), fb = b.toLowerCase();
       if (fa < fb) return -1;
       if (fa > fb) return 1;
       return a < b ? -1 : a > b ? 1 : 0; // stable tiebreak on raw bytes
   };
   ```
   (`toLowerCase` without a locale argument is Unicode-default case mapping, not ICU collation, and is stable across the environments we care about. The raw tiebreak keeps `Foo`/`foo` deterministic on case-sensitive catalogs.)
2. MUST regenerate the MD-4 goldens in the same commit and record in the journal that this is an intentional one-time prompt-shape change (underscored names will move). This is the last cheap moment to take that break — after the cache ships, a comparator change also invalidates every persisted expectation users have built.
3. SHOULD apply the same comparator to `listObjects`/`listSchemas` for consistency (OE ordering will shift the same way; note it in the batch journal).
4. MUST add a regression test that asserts the schema-context bytes for a fixture containing `_`, digits, mixed case, and at least one non-ASCII identifier, and a lint/grep guard (`localeCompare` forbidden under `services/metadata/**` and `sqlLanguage/**` except in explicitly UI-labeled presentation code).

**Side benefit.** Ordinal comparison is markedly cheaper than ICU; `listObjects()` over 10k objects (currently 10 ms, sorted per call) will drop, which matters once OE re-renders from cache on every cold start. CONSIDER memoizing the sorted index per snapshot (it is immutable) — see H-9.

### C-2. Generations do not survive or coordinate across processes; add a snapshot content hash and make it the cross-process determinism key  **[CACHE-1]**

**The gap.** Generations are per-entry, per-process monotonic integers (`entry.generation++` in `hydrateCore`). The base design's load flow (§10.1) publishes a disk snapshot "as generation N" and live hydration then publishes N+1 — fine within one process. But two windows (or two restarts) that both load cached generation 42 and then live-hydrate will each publish a *different* generation 43. Anything that treats `(generation, request) → bytes` as a cross-process key — prompt caches, replay comparison, feature-capture correlation — will collide.

**Required change.**
1. MUST compute a canonical **content hash** at snapshot build/rehydrate time: SHA-256 over the serialized `CatalogCachePayloadV1` in its canonical field order (see §6), truncated to 16 bytes, rendered as `csh_<22 b64url>`. Because the payload is exactly the SoA arrays in hydration order, live-hydrated and cache-rehydrated snapshots with identical data hash identically by construction — this doubles as the round-trip proof.
2. MUST carry `contentHash` on `CatalogSnapshot` (a plain readonly string; it does not violate purity), in `FreshCatalogResult`, in the manifest (it can *be* `payload.sha256`'s logical twin — keep both: `payload.sha256` covers the compressed file bytes, `contentHash` covers the canonical uncompressed form and is codec-independent), and in `metadata.contextBuild` span fields (cls `diagnostic.metadata`).
3. MUST NOT put the hash (or the generation) into rendered prompt text — byte-identity of the prompt itself is sacred. The hash rides result metadata and feature capture only. The "deterministic generation marker" on visuals page 5 SHOULD be read as `{generation, contentHash}` in metadata, never as prompt bytes.
4. Disk-resume rule: on load, publish the disk snapshot with `generation = manifest.capture.publishedGeneration` and set the entry counter to that value, so the next live publish is strictly greater. Two windows may still mint colliding integers; the hash is the disambiguator, and that is now documented behavior rather than a latent surprise.

### C-3. `readiness: "stale"` is already taken — it means "re-hydration in flight over an existing snapshot", not "old data"  **[CACHE-0]**

`hydrateCore` sets `entry.status = entry.snapshot ? "stale" : "loading"` for the duration of a refresh and flips to `ready`/`failed` at the end. The base cache design reuses the word "stale" for age-based freshness in several places (status examples §12, matrix §6). If the agent maps cache staleness onto `MetadataStatus.readiness`, every consumer that today interprets `stale` as "a newer generation is seconds away" breaks, and the status bar will lie in both directions.

**Required change.**
1. MUST keep the readiness vocabulary exactly as-built: `absent | loading | ready | failed | stale(=refreshing)`. A cache-loaded snapshot publishes readiness `ready` (its sections carry their captured states), with `source: "disk"` and `validation.result: "notChecked"` carried in the new cache/validation blocks of `MetadataStatus` — never via readiness.
2. SHOULD rename the transient in code for clarity when convenient (`"refreshing"` alias with `"stale"` retained on the wire for structural compatibility is acceptable; do not break `MetadataStatus` consumers in CACHE-0).
3. MUST express age-based staleness only through `FreshCatalogResult.freshness` and `MetadataCacheEntryStatus.staleAgeMs`. The two-axis model (readiness × freshness) on visuals page A3 is the normative picture.

### C-4. Disk-publish suppresses the initial hydration kick — background refresh must become an explicit rule, or cached data becomes silent forever-truth  **[CACHE-3]**

As built, `MetadataService.acquire` kicks hydration only when `entry.status === "absent" || "failed"`. The moment the cache coordinator publishes a disk snapshot during acquire (base §10.1), status is `ready` and *nothing* schedules live hydration; the digest poll then runs against the disk baseline and will happily report "unchanged" for a database that changed before the snapshot was even taken (the baseline digest is recomputed live — see the interaction in C-5 note — but the point stands for every section the digest does not cover).

**Required change.**
1. MUST: whenever an acquire is satisfied from disk and `offlineMode` is false, the store schedules a background live hydration immediately (through the normal chained/`runExclusive` path), regardless of policy, unless a policy with `backgroundRefresh: false` *and* mode `offlineSnapshot` is in force. `FreshCatalogResult.backgroundRefreshStarted` reports it.
2. MUST: the digest poll's baseline (`entry.lastDigest`) is never seeded from the manifest. First poll after a disk load always executes `CHEAP_DIGEST` live and compares against manifest `validation.serverDigest`/`objectDigest` if present; mismatch ⇒ `staleReason: "digestMismatch"` and forced refresh; match ⇒ record `validatedAtUtc` at tier `cheapDatabaseDigest`. (This is the cheapest possible "was my cache already wrong?" check and should be the first network round-trip after a cold start.)
3. MUST: `entry.status === "failed"` with a retained snapshot (see C-7) also re-arms hydration attempts with backoff — today a failed refresh permanently disables the poll (`if (entry.status !== "ready" || entry.hydrating) return;`) until a new acquire. Backoff schedule: 5 s, 30 s, 2 min, then every poll tick; reset on success. Cap: never more than one in-flight attempt (the lane already guarantees this).

### C-5. Load-time privacy/policy intersection: excluded sections MUST come back `absent`, never ready-and-empty — in both directions  **[CACHE-2]**

The manifest records `privacy.includesDescriptions` / `includesModuleDefinitions`. Two hazards the base design leaves implicit:

- A payload written under an older, more permissive policy is loaded under a stricter one (or vice versa).
- A payload legitimately contains a `descriptions` section that was `ready` at capture, but the current settings say descriptions must not be *used* from cache.

If the loader simply drops the arrays and keeps the readiness map, `descriptions: "ready"` with zero rows renders as "this object has no description" — a textbook empty-vs-failed violation, now minted from disk.

**Required change.**
1. MUST: on load, readiness for any section excluded by *current* policy, or absent from the payload regardless of manifest readiness, is forced to `"absent"`. On save, sections excluded by policy are neither serialized nor marked `ready` in the manifest — write `"absent"`.
2. MUST: `policyId` mismatch between manifest and current settings is not a corruption; it is a normal load with intersection applied. Emit `metadataCache.load` with a `policyIntersected: true` field (safe enum/boolean).
3. MUST: module definitions are never in `CatalogCachePayloadV1` v1 at all (base §2 non-goal). The lazy read stays live-only; `readiness.definitions` on the provider seam remains `"lazy"` even when the snapshot came from disk (a disk snapshot cannot serve `getDefinition`; in offline mode the provider reports the lazy read as failed-with-reason, not empty).
4. Test (unit, CACHE-2 exit): write with descriptions on → load with descriptions off → `getDescription` path is gated by `descriptions === "ready"` in the adapter (already test-pinned) and must observe `absent`; hover must decline, not show blank.

### C-6. `mode: "offline"` is a status dimension, not a snapshot mode  **[CACHE-0]**

The base design's `MetadataStatus.mode` gains `"offline"` (§12). `CatalogSnapshot.mode` must stay `full | lite | partial` — a snapshot is what it is regardless of how it is being served; offline is a property of the *serving decision*. MUST keep `snapshot.mode` untouched, put `"offline"` only on `MetadataStatus.mode` (derived: offline mode active AND source is disk), and mirror it in `FreshCatalogResult.source: "offline"`. This keeps the codec and the purity rule clean.

### C-7. Live-refresh failure semantics with a retained snapshot — codify what the code already does, extend it to disk and to the server catalog  **[CACHE-0/3]**

As built (verified): a failed `hydrateCore` sets `entry.status = "failed"` but **retains** `entry.snapshot`; `current()` keeps serving the previous generation. That is the right semantic and the cache extends it: after a disk load, a failed live refresh leaves the disk generation in place, `readiness: "failed"`, `validation.result: "failed"`, `staleReason` from the error class. `ensureFresh` then resolves per mode:

| mode | outcome on refresh-failure-with-snapshot |
|---|---|
| `allowStale` | snapshot returned, `freshness: "stale"`, background retry scheduled per C-4.3 |
| `requireValidated` | snapshot returned, `freshness: "stale"`, `validation.result: "failed"` — caller (diagnostics) suppresses; NEVER claim validated |
| `requireLive` | `snapshot: undefined` in the result is wrong — return the snapshot **but** `freshness: "unavailable"`; strict callers refuse on freshness, and still have the snapshot if they want to offer the explicit offline path to the user |
| `offlineSnapshot` | snapshot returned, `freshness: "stale"`, `source: "offline"` |

**Server catalog reconciliation.** The as-built rule "on failure the previous list is dropped and `listDatabases()` returns `undefined`" was written for a live-only world where the previous list had no provenance. With a cache it becomes: failure never *creates* emptiness and never *promotes* freshness — but a previously *published* generation (including one loaded from disk) MAY remain readable with `validation.result: "failed"` attached. Concretely: keep the list, set server readiness `failed`, keep `listDatabases()` returning the retained list (not `undefined`) **only when** that list carries cache provenance the UI can display; with no retained generation, `undefined` stands. OE renders the failure state either way. This is a deliberate, journaled change to §3.5 semantics; the test that pins "failed drops list" is updated to pin the new two-case rule.

### C-8. `FreshCatalogResult` refinements  **[CACHE-0]**

MUST adopt these deltas to the base §5.1 types:

```ts
export interface FreshCatalogResult {
    readonly snapshot: CatalogSnapshot | undefined;
    readonly generation: number;
    readonly contentHash?: string;                    // C-2; absent only when snapshot is
    readonly source: "memory" | "disk" | "live" | "offline" | "none"; // "none" ⇔ snapshot undefined
    readonly freshness: "live" | "validated" | "stale" | "refreshing" | "unavailable";
    readonly capturedAtUtc?: string;
    readonly staleAgeMs?: number;
    readonly waitedMs: number;                        // how long ensureFresh blocked this caller
    readonly validation?: MetadataValidationSummary;
    readonly backgroundRefreshStarted?: boolean;
}
```

- Rename `"fresh"` → `"live"` (SHOULD): "fresh" vs "validated" reads as a judgment call; "live" states a fact — this result was produced by a refresh completed for this call. `"validated"` = TTL/digest-confirmed. `"refreshing"` = returned early while shared work continues (only `allowStale` may produce it). `"stale"` = known-unvalidated. `"unavailable"` = the policy's bar was not met (snapshot may still be present, see C-7).
- `waitedMs` is required for the perf gates (§9) and costs nothing.

### C-9. `timeoutMs` semantics: a race, never a cancellation; add `signal`  **[CACHE-0]**

Multiple consumers coalesce onto the same entry's validation/hydration (see §4.3). A policy timeout therefore MUST only stop *waiting*; it must never cancel the shared lane work (someone else is awaiting it, and per H-2 the lane must anyway never lose a completion). On timeout: `requireLive` resolves `freshness: "unavailable"`; `requireValidated` resolves with the best snapshot and `freshness: "stale"`, `validation.result: "notChecked"`. SHOULD add `signal?: AbortSignal` to the policy (adapted from `vscode.CancellationToken` at the call sites) with identical race-only semantics, so editor-cancelled requests stop waiting immediately.

### C-10. Pin the `databaseHash` recipe and the `index.json` shape  **[CACHE-2]**

The base design says "a hash of the exact database name" without a recipe. Two windows, or a future rehost, must derive the same path. MUST:

```ts
databaseHash = "dbh_" + b64url(sha256(serverFingerprint + "\u0000" + exactDatabaseName)).slice(0, 22)
```

Salting with the server fingerprint prevents cross-server correlation of identical database names on disk listings. Do **not** reuse `pfp_` (the profile scope hashes more than `{server facts, database}` and would fragment the cache across otherwise-identical profiles).

`index.json` (rebuildable from manifests, per base §15.2):

```jsonc
{
  "formatVersion": 1,
  "entries": [
    {
      "serverFingerprint": "sfp_…",
      "databaseHash": "dbh_…",           // absent for server-catalog entries
      "kind": "database",                 // "database" | "server"
      "capturedAtUtc": "…",
      "lastAccessUtc": "…",              // updated on load, write debounced ≥60s
      "payloadBytes": 123456,
      "contentHash": "csh_…"
    }
  ],
  "totalBytes": 1234567
}
```

Corrupt or missing index ⇒ rebuild by scanning manifests (never by trusting payload files without manifests).

### C-11. The H0 case-sensitivity probe misclassifies binary collations — fix before the environment is persisted  **[CACHE-PRE]**

Verified in `metadataService.ts`:

```ts
caseSensitive: collation ? /_CS(_|$)/i.test(collation) : undefined,
```

`Latin1_General_BIN` / `_BIN2` collations are case-sensitive (byte/codepoint comparison) but contain no `_CS` token, so this evaluates to `false`. Consequence today: `resolveName` on a BIN-collated database accepts folded-only matches the server would reject — the binder "guesses" in exactly the way the design forbids. Consequence under the cache: the wrong `caseSensitive` is serialized into `CatalogEnvironment` and outlives the session.

MUST fix to:

```ts
caseSensitive: collation ? /_CS(_|$)|_BIN2?(_|$)/i.test(collation) : undefined,
```

and add unit cases for `Latin1_General_CS_AS`, `..._CI_AS`, `..._BIN`, `..._BIN2`, `SQL_Latin1_General_CP1_CI_AS`, and a `_CS_..._KS_WS` variant. (Accent/kana/width sensitivity remain intentionally unmodeled — folding is case-only; note this as an accepted limit in the doc rather than silently.)

### C-12. `ensureFresh(sections)` in v1 is a readiness gate + validation scope — it is NOT per-section hydration  **[CACHE-0]**

The engine hydrates via the whole H-ladder; section-scoped hydration does not exist until CACHE-7 (T2/T3). To stop the agent from inventing it early: in CACHE-0…6, `policy.sections` means (a) the readiness check that decides whether the snapshot *can* satisfy the caller (`allowPartial` interplay), and (b) once T1 validation exists, which manifest section digests participate in the compare. Any refresh triggered by a v1 policy is a full-ladder refresh. Document this in `metadataFreshness.ts` header verbatim.

---

## 3. Hardening (H-series)

### H-1. Cheap digest v2: the rename/transfer blind spot  **[CACHE-5, SQL in CACHE-PRE]**

Verified digest:

```sql
SELECT COUNT(*) AS object_count,
       ISNULL(CHECKSUM_AGG(CHECKSUM(o.object_id, o.modify_date)), 0) AS object_hash
FROM sys.objects o WHERE o.type IN ('U','V','P','FN','IF','TF','SN') AND o.is_ms_shipped = 0;
```

`object_id` and `modify_date` both survive `sp_rename` and `ALTER SCHEMA … TRANSFER` (rename does not bump `modify_date`; transfer changes `schema_id` only). A rename performed *in this editor* is caught by the DDL sniff (`SP_RENAME` is in `DDL_KEYWORDS`); a rename performed by SSMS, a migration tool, or a teammate is invisible to the digest until some unrelated change lands. With a persistent cache, "invisible until unrelated change" can now mean *days*.

MUST upgrade to digest v2:

```sql
SELECT COUNT(*) AS object_count,
       ISNULL(CHECKSUM_AGG(CHECKSUM(o.object_id, o.schema_id,
              CAST(o.name AS varbinary(256)), o.modify_date)), 0) AS object_hash
FROM sys.objects o WHERE o.type IN ('U','V','P','FN','IF','TF','SN') AND o.is_ms_shipped = 0;
```

- `CAST(name AS varbinary)` makes the name contribution byte-exact (plain `CHECKSUM` over character data is collation-folded, so a pure-case rename on a CI server would still hide).
- Still one narrow scan of the same rows; cost is indistinguishable from v1.
- Keep the fixture-matcher discipline: the digest fixture must precede H2's (`FROM sys.objects o WHERE` substring collision is already documented in three fixture files — extend those notes for the new text).
- MUST NOT trust my `modify_date` claims from prose alone: add a **live drift-matrix scenario** to the harness (create/alter/drop/sp_rename/schema-transfer/permission-change × {sniff, digest v1, digest v2} → detected?) and let the matrix in the repo be the citation. Visuals page A4 is the target picture; fill its cells from the scenario run, not from this document.
- Coverage honesty stays: digest v2 still cannot see column/key/FK/parameter/description drift, permission changes, or `ALTER` that touches only sub-objects without bumping `modify_date` (rare but real for some index operations routed oddly). That is what T2 section digests are for; keep the "likely unchanged, never proof" wording.

### H-2. STS2 interlocks: the lane must survive a completion that never comes  **[CACHE-0]**

The substrate's completion-reaction discipline (await `handle.completion`, never the sink) assumes exactly-one `v2/query.complete` per accepted execute. The STS2 review (this package) found that assumption currently violable: **STS2-R008** (dispose suppresses `query.complete`), **R009** (dispose releases the connection before the pump stops), **R010** (duplicate close orphans the first waiter). Until those land on the service side, a metadata lane that waits forever is a metadata subsystem that dies quietly for one database.

MUST, on the extension side and independent of the service fixes:
1. Never call `query.dispose` on an in-flight lane query the engine intends to await. Cancellation for lane work is expressed only as "stop waiting" (C-9) plus, when the *engine itself* must give up (watchdog), session recycle.
2. Add a per-operation lane watchdog (default 60 s hydration, 15 s digest/lazy read; internal settings). On expiry: mark the pass/section failed with error class `laneTimeout`, emit `metadata.hydrate` span fail, **dispose the session source and reopen** on the next lane item (a fresh dedicated session is cheap; a wedged one is not), and re-baseline the digest. The watchdog MUST NOT reject the shared lane promise for other queued waiters mid-chain; it fails the operation, then lets the recycle path restore the lane.
3. Close-once: the session source guards against duplicate close (R010) — idempotent `dispose()` at the source level, mirroring the store's inert double-dispose leases.
4. `store.dispose()` / entry eviction while hydrating: bound the drain — await the lane with the same watchdog ceiling, then hard-dispose. Never leave `entry.hydrating` unsettled (identity-guarded clears already exist; extend them to the recycle path).
5. Add the fake-backend test the STS2 review prescribes, pointed at this lane: a backend that swallows one completion; assert the watchdog fires, the section is `failed` (not empty), the session recycles, and a subsequent `ensureFresh(requireLive)` succeeds.

### H-3. Poll governance: serverless auto-pause, jitter, and a global validation budget  **[CACHE-5]**

The 60 s digest poll per leased database is exactly the kind of tick that keeps Azure SQL serverless from auto-pausing (billable) and that turns a 30-database OE session into a background query herd.

1. MUST gate polling on VS Code window focus: `vscode.window.state.focused === false` for > 2 min ⇒ suspend polls (drift re-checked on next `ensureFresh(requireValidated)` anyway — the TTL model already covers the return path). Resume with an immediate tick on focus.
2. SHOULD back off per-entry when nothing changes: 60 s → 120 s → 300 s (cap), reset to 60 s on any drift trigger or user execution against that database.
3. SHOULD detect serverless/auto-pause-capable targets (`SERVERPROPERTY('EngineEdition')` = 5/8/11/12 family is already captured in H0) and start at the 300 s cap for them, with a one-line status detail ("reduced polling to allow auto-pause").
4. MUST cap concurrent validations store-wide (semaphore, default 2) — per-entry lanes serialize within a key, not across keys; a reconnect storm after laptop resume must not fan out 30 digest queries at once. Add ±10 % jitter to every interval.
5. Expose `mssql.metadata.pollSeconds` as an internal/dogfood setting (engine already accepts `pollSeconds`).

### H-4. Multi-window disk protocol: pin the loser-tolerant details  **[CACHE-2]**

The base §9 protocol (temp + fsync + rename payload, manifest-last, sha-verified) is right. Pin the platform realities:

1. Temp files MUST live in the *same directory* as their target (rename atomicity is same-volume only). Names: `<target>.<pid>.<nonce>.tmp`.
2. On Windows, `fs.rename` maps to `MoveFileExW(MOVEFILE_REPLACE_EXISTING)` — replace works, but antivirus/indexers cause transient `EPERM`/`EBUSY`/`EACCES`. MUST retry rename up to 3× with 50/150/400 ms jittered backoff before declaring the save failed (save failure is an event, never an error surfaced to the user).
3. `fsync` the payload file handle before rename; directory fsync is best-effort (`fs.open(dir)`+`fsync` on POSIX, skip on Windows). A torn state is already recoverable by construction — the sha check plus manifest-last means every readable state is either old-valid or new-valid (visuals page A2 carries the 2×2 torn-write matrix; implement to that table).
4. Writer conflict policy is last-writer-wins with a fairness guard: before overwriting, read the current manifest; if its `capture.capturedAtUtc` is newer than ours **and** its `publishedGeneration` ≥ ours, skip the save (`metadataCache.save` with `skipped: "newerExists"`). Include `writerId: "<pid>:<nonce>"` in the manifest for postmortems.
5. After a save, re-read the manifest once; if it is not ours, another window won — benign, emit `raceLost` (safe enum), do not retry.
6. Remote dev note (docs only): in SSH/WSL/containers the extension host — and therefore `globalStorage` and the cache — lives on the remote. Two *local* windows attached to the same remote share one cache directory (the above protocol covers it); a local window and a remote window do not share anything. No code change; one paragraph in the design doc so the agent does not "fix" it.

### H-5. Database rename/drop under a live lease: piggyback identity on the digest  **[CACHE-5]**

`DatabaseKey` binds the *name*; the physical database can be renamed or dropped underneath a warm lease and the dedicated session either follows the rename (its context is the DB, not the name) or starts failing. Today nothing distinguishes those from generic failure.

MUST extend the digest batch to also select identity, one round-trip, zero extra cost:

```sql
SELECT DB_NAME() AS current_db, COUNT(*) AS object_count, ISNULL(CHECKSUM_AGG(…)) AS object_hash FROM sys.objects o WHERE …;
```

If `current_db` ≠ `key.database` (byte-exact — same rule as the tripwire): count it with the existing key-correctness counter but a distinct event `metadataStore.keyCorrectness.driftRename` (fields `expected`/`actual` with cls `database.name`, matching the tripwire's sanctioned classes), mark the entry `staleReason: "accessChanged"`, fail `requireValidated`/`requireLive` with an actionable error, keep serving `allowStale` from the retained snapshot, and stop the poll for that entry (it is now lying by definition). Session-open failures with "database does not exist/offline" error classes map to the same state with `staleReason: "accessChanged"`. Never auto-rekey — the consumer owns reacquisition under the new name (QS already swaps leases on ENVCHANGE truth).

### H-6. Permission drift is not schema drift — route it into the vocabulary that already exists  **[CACHE-5]**

`MetadataStaleReason` already has `permissionChanged`/`accessChanged`; wire the producers: (a) a section that flips ready→failed across a refresh with a permission-class error sets `permissionChanged`; (b) server-catalog `accessState` transitions for a database with a live entry set `accessChanged` on that entry; (c) the (future) `metadataPermission` suppression reason in the diagnostics ladder keys off the same classification. Counted, never named — reuse the existing per-section error classes; do not add object identifiers to any of these events.

### H-7. Memory accounting for cache-loaded snapshots  **[CACHE-3]**

Entries hold exactly one current snapshot; older generations live only as long as pins — GC handles them, and the module-definition cache is already cleared per generation. Two additions: (a) MUST include `payloadBytes`/`uncompressedBytes` estimates in `MetadataCacheEntryStatus` and in `store.status()` totals so dogfood can see resident cost; (b) SHOULD skip disk save for snapshots whose serialized size exceeds a per-entry cap (`mssql.metadataCache.maxEntryBytes`, default 32 MiB compressed) — emit `metadataCache.save` with `skipped: "entryTooLarge"`, and let CACHE-7's lite/per-section payloads be the real answer for monster catalogs rather than inventing one now.

### H-8. Azure/edition notes to record, not to code around  **[docs]**

(a) Azure SQL Database has no cross-database `USE`; the per-database dedicated session strategy is not just preview-safe there, it is the *only* strategy — record an engine-edition gate on the future serialized-`USE` lane so nobody burns a week discovering this on dogfood. (b) Contained/AAD users may see `sys.databases` narrowly; server-catalog readiness semantics already handle it (list what is visible; `HAS_DBACCESS` NULL → `unknown`). (c) `sys.databases … ORDER BY d.name` sorts under server collation — fine for UI, but the server-catalog *cache* must not assume this order is stable across servers; the codec stores rows as fetched and any UI sort is presentation-side (same C-1 comparator if determinism is ever needed).

### H-9. Presentation-sort memoization  **[CONSIDER, CACHE-4]**

`listObjects()` re-sorts on every call over an immutable snapshot. After C-1's ordinal comparator lands, CONSIDER a lazily-built, per-snapshot sorted index (schema,name) reused by `listObjects` and `buildSchemaContext`'s render ordering. Expected: OE folder enumeration and repeated context builds drop well under the current 10 ms. Only do it with a perf scenario proving the win; it is not needed for correctness.

### H-10. Startup cleanup discipline  **[CACHE-2]**

Eviction (age → bytes → LRU → corrupt-first) runs at activation and after each save, but MUST be async, throttled (≤ 1 fs op burst per 25 ms), and started only after activation completes — cache hygiene must never appear in `mssql.activate` timings. `clearAll`/`clearForConnection` delete manifests first, payloads second (a payload without a manifest is by definition garbage and gets swept by the next cleanup).

---

## 4. Freshness policy — consolidated normative semantics

### 4.1 Types (final, superseding base §5.1 where they differ)

Base §5.1 stands with the C-8/C-9 deltas: `FreshCatalogResult` as in C-8; `MetadataFreshnessPolicy` gains `signal?: AbortSignal`; `MetadataFreshnessReason` keeps the base union (add `"offlineBrowse"` if OE needs to distinguish — optional). Policy presets (base §5.3) stand, with two adjustments: `completion.maxStalenessMs` is a *background-refresh trigger*, never a reason to withhold the snapshot (a 31-day-old snapshot still serves; it just also schedules refresh and reports `staleAgeMs`); `diagnosticsBinder.timeoutMs: 250` is a wait budget per C-9 — on miss, diagnostics suppress, they do not block the pass.

### 4.2 The decision procedure (implement exactly; visuals page A1 is this text as a flowchart)

```
ensureFresh(policy):
  e ← entry(key);  snap ← e.snapshot (memory, incl. earlier disk publish)
  if snap is undefined and policy.allowDiskLoad and diskAvailable:
      snap ← coordinator.load(key)          # publishes into entry per C-2/C-5
  offline ← settings.offlineMode or policy.mode == "offlineSnapshot"

  switch policy.mode:
    allowStale:
      if snap: schedule background per C-4 when due; return {snap, freshness: staleOrValidatedOrRefreshing}
      if offline: return {none/unavailable}
      else: join hydration wait up to timeout; on timeout → {none, "unavailable"}? NO —
            return {snapshot: undefined, source:"none", freshness:"unavailable"} only if still nothing;
            completions then answer keyword-only + isIncomplete (as today).
    requireValidated:
      if offline: return {snap?, freshness: snap ? "stale" : "unavailable", validation notChecked}
      if validatedWithin(policy.validationTtlMs, policy.sections): return {snap, "validated"}
      join/start T1 validation (coalesced, §4.3) with wait ≤ timeout:
        unchanged → record validation; return {snap, "validated"}
        changed   → join/start chained refresh, wait ≤ remaining timeout:
                      done → {newSnap, "live"};  timeout → {snap, "stale", refreshing}
        failed/timeout → {snap?, "stale"/"unavailable", validation failed|notChecked}   # C-7 table
    requireLive:
      if offline: {snap?, "unavailable"}   # strict never silently downgrades; caller may re-ask offlineSnapshot
      join/start forced refresh (chained), wait ≤ timeout:
        done → {newSnap, "live"};  fail/timeout → C-7 row
    offlineSnapshot:
      no network ever; {snap?, snap ? "stale" : "unavailable", source:"offline"}
```

Readiness gating happens *after* the freshness decision: if `policy.sections` are not all `ready` (or `lazy` where sanctioned) in the returned snapshot and `allowPartial !== true`, downgrade `freshness` to `"unavailable"` for `require*` modes; `allowStale` callers receive the snapshot plus per-section truth and do their own honest degradation (that is already their contract).

### 4.3 Coalescing and starvation

Per-entry: `validationInFlight?: Promise<MetadataValidationSummary>` alongside the existing `hydrating`. All concurrent `requireValidated` callers await the same T1; all `requireLive` callers await the same chained refresh (`hydrating` already provides this). Waits are races (C-9); the underlying work always runs to completion so `allowStale` background refreshes and other waiters are never robbed. Because the lane is FIFO, a long hydration ahead of a strict small read is a known, journaled trade (substrate §2.1) — the watchdog (H-2) bounds the worst case; do not add priorities in v1.

### 4.4 Server-catalog `ensureFresh`

No digest exists at server scope; validation ≡ re-hydrate. `ServerMetadataFreshnessPolicy` = `{mode, reason, validationTtlMs?, timeoutMs?, signal?}`; `requireValidated` re-hydrates when older than TTL (OE default 120 s), `requireLive` always re-hydrates, `allowStale` returns whatever generation exists (memory or disk) and schedules per C-4. Failure semantics per C-7's server paragraph.

---

## 5. Persistent cache — spec deltas

1. **Manifest additions** (to base §7.2): `payload.contentHash` (C-2), `writerId` (H-4.4), `environment: { engineEdition?, collationName?, caseSensitive?, defaultSchema? }` copied from the snapshot's `CatalogEnvironment` (also lives in the payload; duplicated in the manifest so status/eviction can reason without decompressing), `producer.appVersion` (VS Code version string) alongside `extensionVersion`.
2. **`databaseExact` at rest.** It is plaintext database name on disk inside the manifest. That matches the sanctioned local classification (cls `database.name` is already emitted by the tripwire), but say it out loud in the privacy section and keep it out of *events* per base §8.3. CONSIDER (not v1) a `persistDatabaseNames: false` mode that omits it and shows the hash in offline UI — only if enterprise feedback asks.
3. **Server-catalog payload** gets its own minimal codec (`serverCatalog.json.gz`): rows as fetched from `LIST_DATABASES` (name, state_desc, is_read_only, user_access_desc, compatibility_level, accessState, isSystem) plus server facts and capture time. Offline OE MUST render `accessState` with an "as of <capture>" qualifier — access is the most volatile fact in the file.
4. **`previous/`**: omit in v1 (base already allows this). One live manifest+payload per key.
5. **Write scheduling addition:** skip the save when `contentHash` equals the manifest's current `contentHash` (refresh confirmed no change) — bump only `validation.*` in the manifest via the same manifest-last protocol. This turns the steady state into a tiny manifest rewrite instead of a payload rewrite.
6. **Settings (final v1 set):** base §13.1/13.2 stand, plus `mssql.metadataCache.maxEntryBytes` (H-7), `mssql.metadata.pollSeconds` (H-3, internal). Defaults unchanged: `enabled: false` until §22 gates pass.

---

## 6. Codec rules (CACHE-1, normative)

1. **Adopt arrays verbatim.** Rehydration constructs the builder by assigning the deserialized arrays directly (`strings`, `*Syms`, ids, flags) — never by replaying `addObject`/`intern` (re-interning would work but forfeits the symbol-id identity that makes `contentHash` and byte-identity trivially provable, and is slower). Provide one `CatalogCodec.adopt(builder, payload)` friend function beside `catalogModel.ts` (base §7.3's "friend" note, made concrete).
2. **Canonical field order** is the serialization order and the hash order; freeze it in code as an exported tuple list and derive `catalogModelVersion` from a hand-bumped constant beside it (`"cm1"`). Any change to arrays or order bumps it; a mismatch is a clean miss (`metadataCache.miss`, reason `modelVersion`), never a migration in v1.
3. **Environment travels.** `CatalogEnvironment` (incl. the C-11-corrected `caseSensitive`) is part of the payload; `resolveName` offline must behave exactly as it did live. Round-trip test on a CS and a BIN2 fixture.
4. **Strictness.** Unknown top-level payload fields ⇒ reject (miss, reason `shape`); optional sections present only when their manifest flag says so (C-5). Numeric arrays reject non-finite values. Gzip via `zlib` default level; CONSIDER level 1 only if the save scenario misses its budget (it is background, so unlikely to matter).
5. **Round-trip proof (exit gate, unchanged from base):** fixture → serialize → rehydrate → (a) `buildSchemaContext` bytes identical, (b) folded-index search results identical, (c) `contentHash` identical, (d) readiness/mode/generation/environment identical.

---

## 7. Consumer wiring specifics

1. **Query Studio USE swap ordering.** MUST acquire the new database lease *before* disposing the old one (warm-TTL churn otherwise turns A→B→A into re-hydrations under load, and in-flight responses pinned to the old snapshot must stay valid — pin-once already guarantees the latter, the ordering guarantees the former). Verify current `DocumentSessionBinding` order and pin it with a test; if it already does this, the test is the deliverable.
2. **OE v2 first-expand UX (decides prior review §3.12).** Policy: block-with-loading. First expand beyond TTL shows the loading child while `requireValidated` runs (budget 5 s per preset); on validation timeout/failure with a snapshot present, render the snapshot *plus* a status child naming the staleness — never render stale silently as current. Stale-while-revalidate stays behind an internal flag for experiments.
3. **Diagnostics.** Two new counted suppression reasons: `metadataNotValidated` (policy returned stale/unvalidated) and `metadataStale` (drift trigger fired mid-pass; the generation-change cancel already exists). Counts only, as with the existing 16.
4. **Hover/signature.** Facts from ready sections ride `allowStale`; the "authoritative claims" set (module link presence, description text shown locally) MAY request `requireValidated` with a 250 ms budget and silently omit on miss.
5. **Scripting.** `ScriptResult` gains `{generation, contentHash, source, freshness, capturedAtUtc?}`; the offline banner (base §16.3 wording) is emitted from those fields, so banner and telemetry can never disagree.
6. **AI completions.** No behavior change beyond C-2's metadata fields; the classic-editor resolver keeps its 120 s first-hydration wait, but SHOULD switch that wait to `ensureFresh(MetadataPolicies.aiContext)` so a disk hit turns 120 s worst-case into instant-with-background-refresh — that is the headline user win of this whole effort; make it a named perf scenario (§9).

---

## 8. Observability & privacy deltas

1. Register the base §18.1 vocabulary in the contracts registry before first emission (conformance tests already enforce this — a B7-style failure here is cheap and early). Add `metadataCache.raceLost` and the `skipped` field values from H-4/H-7 to the registered attrs.
2. Every field `{raw, cls}`-classified per the debug-console discipline. Class assignments: fingerprint/db-hash prefixes, generation, readiness summaries, stale-age buckets → `diagnostic.metadata`; byte counts and durations → `diagnostic.metric`; policy/mode/source/tier/result/error-class/skip-reason → safe enums. Database names appear only where the tripwire precedent already sanctions them (`database.name` class: tripwire, H-5 rename event) — cache events use the hash prefix.
3. Extend the privacy canaries: manifest and payload files for a hydrated fixture are scanned to assert no server name, user name, token, connection-string fragment, prompt text, or module text appears; with `persistDescriptions: false` (default), no description value appears either. Run the canary against the *bytes on disk*, not the in-memory objects.
4. Stale-age buckets: `<1m, <10m, <1h, <1d, <7d, <30d, ≥30d` — fixed now so dashboards do not fork.

---

## 9. perftest integration (make the budgets executable)

Wire through the existing contracts: markers via the `Perf` facade only (frozen no-op outside PERF_MODE — every new call site through the gate), official metrics only from marker pairs, scenarios declared with `setup/measure/success` and `markerSeen` criteria, regression thresholds per the §24 model (percent + absolute floor). New marker family:

```
mssql.metadata.cache.load        begin/end   attrs: source, payloadBytes, objects (counts only)
mssql.metadata.cache.save        begin/end   attrs: skipped?, payloadBytes
mssql.metadata.ensureFresh       begin/end   attrs: mode, reason, freshness, waitedMs
mssql.metadata.validate          begin/end   attrs: tier, result
```

Scenario table (ids from base §19.5, now with metric + target + gate):

| Scenario id | Official metric (marker pair) | Target (p95) | Gate |
|---|---|---|---|
| `metadata-cache.load.10k` | `metadata.cache.load.duration` | < 50 ms | yes |
| `metadata-cache.save.10k` | `metadata.cache.save.duration` | < 200 ms bg | no (report-only) |
| `metadata-cache.completion-after-restart` | `metadata.ensureFresh.wait` (reason=completion) | < 10 ms | yes |
| `metadata-cache.ai-context-after-restart` | ensureFresh wait, reason=aiContext | < 25 ms | yes |
| `metadata-cache.oe-first-expand` | expand → rendered (existing `mssql.oe.expand`) | < 250 ms incl. validation | yes |
| `metadata-cache.oe-repeat-expand-ttl` | 〃 within TTL | < 30 ms | yes |
| `metadata-cache.validation-under-query-load` | 0 `Busy` on user session (validation `noErrors`) | 0 | yes |
| `metadata-drift.matrix.live` | n/a — success criteria = detection table matches H-1 expectations | — | yes (functional) |
| `metadata-cache.corrupt-recovery` | recovery-to-live-hydration-start | < 20 ms | yes |

Standing-gate rule: the QS 10k-row connect-path gates (389–1100 ms band, 28 reps) MUST remain unchanged across every CACHE-* batch — the cache is additive; any movement there is a regression by definition. Unit-lane micro-benches (codec round-trip, adopt(), ordinal sort) live beside the existing B9-style benches and are report-only.

---

## 10. Test additions (beyond base §19, each mapped to a batch)

| ID | Test | Batch |
|---|---|---|
| T-A1 | Ordinal-comparator schema-context bytes incl. `_`/digit/case/non-ASCII fixture; `localeCompare` lint guard | PRE |
| T-A2 | Collation probe truth table incl. `_BIN`/`_BIN2` (C-11) | PRE |
| T-A3 | Digest v2 detects fake-backend rename/schema-transfer; v1 documented-miss asserted (so the improvement is pinned) | PRE |
| T-A4 | Lane watchdog: swallowed completion ⇒ section failed, session recycled, next requireLive succeeds (H-2) | 0 |
| T-A5 | ensureFresh coalescing: N concurrent requireValidated ⇒ exactly one digest query (fake backend counts) | 0 |
| T-A6 | Timeout-is-a-race: strict caller times out; background waiter still receives the completed refresh | 0 |
| T-A7 | contentHash: live vs rehydrated equality; inequality on any array perturbation | 1 |
| T-A8 | Policy intersection both directions (C-5), incl. hover-declines-not-blank | 2 |
| T-A9 | Torn-write matrix: all four payload/manifest old-new states load old-valid or new-valid, never partial (drive via injected rename failure) | 2 |
| T-A10 | Windows rename EPERM retry path (mock fs) | 2 |
| T-A11 | Disk-publish schedules background hydrate; digest baseline never seeded from manifest (C-4) | 3 |
| T-A12 | failed-with-snapshot backoff re-arms; poll resumes after success (C-4.3) | 3 |
| T-A13 | readiness "stale" reserved for refreshing; cache staleness never appears in readiness (C-3) | 0 |
| T-A14 | Server-catalog failure two-case rule (C-7) | 3 |
| T-A15 | DB rename under lease: digest identity check fires `driftRename`, strict fails actionably, allowStale keeps serving (H-5) | 5 |
| T-A16 | Focus-loss suspends polls; resume ticks immediately (H-3) | 5 |
| T-A17 | Two-writer race sim: interleaved save protocols end with one valid winner; loser emits `raceLost` (H-4) | 2 |
| T-A18 | Key-correctness tripwire and A/B isolation re-run *with cache enabled* (base gate, restated because it is the one that must never move) | 3 |

---

## 11. Batch plan deltas (for the agent's journal)

**CACHE-PRE (new, first):** C-1 comparator + golden regen, C-11 collation fix, H-1 digest v2 SQL + fixtures, T-A1..3. Small, self-contained, ships value even if the cache slips. Definition of done: goldens regenerated intentionally (journal note), lint guard active, drift-matrix scenario checked in (may run live-lane only).

**CACHE-0:** as base, plus C-3/C-6/C-8/C-9/C-12 wording in `metadataFreshness.ts`, H-2 watchdog + recycle, §4.3 coalescing, T-A4..6, T-A13. Exit adds: fake-backend swallowed-completion test green.

**CACHE-1:** as base, plus C-2 contentHash end-to-end, §6 codec rules, T-A7.

**CACHE-2:** as base, plus C-5, C-10 recipes, H-4 protocol details, H-10 cleanup discipline, T-A8..10, T-A17.

**CACHE-3:** as base, plus C-4, C-7 (incl. server two-case), H-7 accounting, T-A11/12/14/18.

**CACHE-4:** as base, plus §7.6 AI resolver switch + `metadata-cache.ai-context-after-restart` scenario, H-9 only-if-measured.

**CACHE-5:** as base, plus H-1 wiring into T1 validation, H-3 governance, H-5/H-6, T-A15/16, drift-matrix live gate.

**CACHE-6/7:** as base; CACHE-7 additionally owns per-section payloads if H-7's cap ever bites.

Each batch: PRFCV loop as usual; journal records goldens/pins intentionally changed; the standing QS gates run in every batch's verify step.

---

## 12. Open questions for Karl (do not let the agent guess these)

1. **Goldens break in CACHE-PRE (C-1):** confirm you accept the one-time schema-context reordering for underscore/digit names now, before any prompt cache exists in the wild.
2. **`contentHash` in telemetry:** proposed cls `diagnostic.metadata` (it is derived from object names in aggregate but is non-reversible). Sign off, or keep it out of events and only in status/feature-capture.
3. **Server-catalog failure rule change (C-7):** the "failed drops list" pin becomes a two-case rule once provenance exists — confirm.
4. **Poll defaults for serverless (H-3.3):** 300 s starting interval acceptable, or should serverless suspend polling entirely and rely on TTL validation?
5. **`maxEntryBytes` default (H-7):** 32 MiB compressed is a guess; pick after the first large-fixture save measurement.
6. **OE first-expand block-with-loading (§7.2):** this decides prior-review §3.12 — confirm the UX pick before CACHE-5 wires it.

---

## Appendix A — revised policy/type set (verbatim for `metadataFreshness.ts`)

Base §5.1 types with: `FreshCatalogResult` per C-8; `MetadataFreshnessPolicy` + `signal?: AbortSignal`; header comment carrying C-12's scope note and C-9's race-not-cancel rule; `MetadataPolicies` presets unchanged except the completion `maxStalenessMs` comment per §4.1.

## Appendix B — SQL (verbatim)

```sql
-- CHEAP_DIGEST v2 (H-1 + H-5 identity piggyback)
SELECT DB_NAME() AS current_db,
       COUNT(*) AS object_count,
       ISNULL(CHECKSUM_AGG(CHECKSUM(o.object_id, o.schema_id,
              CAST(o.name AS varbinary(256)), o.modify_date)), 0) AS object_hash
FROM sys.objects o
WHERE o.type IN ('U','V','P','FN','IF','TF','SN') AND o.is_ms_shipped = 0;
```

Fixture-matcher note: register this text's fixture before H2's; `DB_NAME()` and `varbinary(256)` collide with no earlier matcher.

## Appendix C — event field allowlist (cache family)

`serverFpPrefix`, `dbHashPrefix` (diagnostic.metadata); `generation`, `contentHashPrefix?` (Q2 pending), `readinessSummary`, `staleAgeBucket` (diagnostic.metadata); `payloadBytes`, `durationMs`, `waitedMs` (diagnostic.metric); `mode`, `reason`, `source`, `freshness`, `tier`, `result`, `errorClass`, `skipped`, `policyIntersected`, `raceLost` (safe enums/bools). Forbidden list: base §18.3 verbatim.
