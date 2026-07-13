# Central Observability — Review Addendum (Code-Verified)
## Normative corrections and hardening for `central_observability_design.md`, grounded in `vscode-mssql` and `perftest` `dev/query`

**Status:** review addendum, 2026-07-06. Apply on top of `central_observability_design.md` (the "base"). Where this addendum and the base disagree, this addendum wins; where the branch and this addendum disagree, the branch wins and this document should be updated.
**Code basis (fetched and read, not recalled):** `microsoft/vscode-mssql` `dev/query` — `sharedInterfaces/debugConsole.ts`, `sharedInterfaces/perfHistory.ts`, `sharedInterfaces/observabilityContract.generated.ts`, `diagnostics/redaction.ts`, `diagnostics/sessionStore.ts`, `diagnostics/perfHistory/perfHistoryService.ts`, `diagnostics/perfRunImport.ts`, `services/sqlDataPlane/api.ts`, `services/metadata/metadataService.ts`; `kburtram/perftest` `dev/query` — `packages/perftest-cli/src/exitCodes.ts`, `packages/perftest-cli/src/run/environment.ts`, `packages/perf-contracts/sql/perf-store.schema.sql`, package layout of `perf-contracts` and `observability-contracts`.
**Companions:** `CENTRAL_OBSERVABILITY_VISUALS_ADDENDUM.tex/.pdf` (pages B1–B6, same visual language as the base deck). Related prior work: `METADATA_CACHE_DRIFT_REVIEW_ADDENDUM.md` — the contentHash/canonical-JSON discipline there and the digest discipline here should stay siblings, not twins that drift.

Conventions: **MUST** = the coding agent implements it as written. **SHOULD** = implement unless a recorded reason exists. **CONSIDER** = design note, not a task. `C-x` = correction to the base design. `H-x` = hardening the base doesn't cover. `T-Bx` = test obligation. `Q-x` = decision Karl must make (§12) — the agent must not guess these.

---

## 0. Executive verdict

The base design is right where it matters most: one SQL Server projection with local files as truth, two writers through one generated contract, stored-procedure-only writes, an ingest spine (batches/items/entities/ledger) instead of a mutable ledger, policy re-applied at the upload boundary, preview as a dry-run of the real projection, and a non-gating CI publish with a fresh exit code. None of that changes.

What the code pull surfaced is a layer of load-bearing details the base leaves implicit or gets subtly wrong, in three clusters:

1. **The disposition algebra is under-determined.** The base defines `source_digest` but never stores it, which makes "refused" and "reprojected" indistinguishable the moment an upload policy changes (a policy change alters `content_digest` over the *same* source). And the stage-then-decide flow writes kind rows for duplicates before anyone notices they're duplicates. C-1/C-2/C-3 fix the algebra, move the decision to `usp_begin_upload` under an entity lock, and make reader visibility structural (`current_batch_id` join) rather than procedural.
2. **The projection sources are richer and leakier than the tables.** The real `DiagEvent` envelope has required `eventId`, an `entity` anchor, `tags`, and a sibling `GapRecord` stream the base flattens to a count; `cls_rank` has an exact, vendorable definition (`RANK_ORDER` in `redaction.ts`); `SessionManifest.provenance.machineLabel` and half a dozen SQLite-twin columns (`output_dir`, `config_path`, `result_path`, `machine_id`, `notes`, `artifacts.path`, `baselines.created_by`) are paths and labels that a naïve "dialect twin" would upload verbatim. C-4 through C-10 pin the mapping and the subtraction list, column by column.
3. **The product writer's transport doesn't exist as described.** `ISqlSession.execute(text, opts, sink)` takes **no parameters** — TVPs are impossible and `OPENJSON` inputs must ride as escaped literals; `commandKind`/`priority` live on per-execute `ExecuteOptions`, not the session; and the central provider's honest-state ladder needs an actual union extension in `perfHistory.ts`, not prose. C-11/C-12 turn §8.3/§8.4 into something an agent can build against the real API.

Everything lands in the existing C0–C7 batch names with concrete sub-deliverable deltas (§11), tests T-B1–T-B18 (§10), and perf probes wired to the marker/official-metric contracts (§9). Seven decisions are parked for you in §12.

---

## 1. Code-truth ledger

Facts the rest of this addendum builds on, with where they live. The agent should treat these as fixed points.

| # | Fact | Source |
|---|---|---|
| F1 | `DataClassification` is exactly the 19-value union the base's policy matrix names — `public`, `system.metadata`, `diagnostic.metadata`, `source.path`, `server.name`, `database.name`, `schema.name`, `object.name`, `sql.text`, `sql.digest`, `row.data`, `result.shape`, `secret`, `connection.string`, `token`, `user.text`, `model.prompt`, `model.response`, `unknown` | `sharedInterfaces/debugConsole.ts` (`DataClassification`) |
| F2 | The classification **order** exists in code: `RANK_ORDER` (19 entries, `public` → `secret`; `rank()` = array index; unknown values rank past the end). Verbatim copy in Appendix B | `diagnostics/redaction.ts` (~line 189) |
| F3 | `DiagEvent`: `schemaVersion:"mssql.diag.event/1"`, **required** `eventId`, `sessionId`, `seq:number`, `epochMs:number`, optional `monotonicNs?: string` (decimal-ns string), `process`, `pid?`, `feature`, `kind`, `type`, `status`, `traceId?`, `causeEventId?`, `entity?: {kind,id}`, `durationMs?`, `timingClass?`, `payload?: Record<string, ClassifiedValue>`, `cls: {max, redactedFields, policyId}`, `tags?: string[]`, `perf?` (rich, never official) | `sharedInterfaces/debugConsole.ts` (`DiagEvent`) |
| F4 | `ClassifiedValue = { v?, cls, handling, digest?, len? }`, `handling ∈ plain|redacted|digest|tokenized|truncated|omitted`; redaction happens **before** the envelope exists | same file (`ClassifiedValue`, header comment) |
| F5 | `GapRecord` is a first-class journal row: `gapId`, `sessionId`, `fromSeq`, `throughSeq`, `droppedCount`, `reason ∈ subscriberOverflow|sinkOverflow|journalUnavailable`, `firstAvailableSeq?`, `backfillStatus`, `epochMs`. Store queries return `Array<DiagEvent \| GapRecord>` | same file (`GapRecord`, `EventQueryResult`) |
| F6 | `SessionManifest`: `schemaVersion:"mssql.diag.sessionManifest/1"`, `sessionId`, `createdUtc`, **`updatedUtc`**, `source ∈ live|perfRun|bundle`, `captureMode`, `policyId`, `eventCount`, `gapCount`, `segments[{file,firstSeq,lastSeq,events}]`, `sizeBytes?`, `droppedRanges?`, `provenance`, `status ∈ active|closed|partial` — no `uploaded`, no `checkpointed` | same file (`SessionManifest`) |
| F7 | `ProvenanceSummary` includes **`machineLabel?`** alongside `extensionVersion/commit/dirty/environmentHash/vscodeVersion/stsVersion` | same file (`ProvenanceSummary`) |
| F8 | Session journals are JSONL segments under `<sessionDir>/events/<segment.file>`; the store verifies per-segment line counts and flags partial trailing lines — segment-at-a-time streaming is already the read grain | `diagnostics/sessionStore.ts` |
| F9 | `PerfSourceKind = "directory" \| "sqlite" \| "bundle"`; `PerfSourceStatus = indexed\|scanning\|partial\|stale\|error\|empty\|unsupported`; the sqlite source registers as `status:"unsupported"` in-product (native driver deliberately not loaded) | `sharedInterfaces/perfHistory.ts`, `diagnostics/perfHistory/perfHistoryService.ts` (~line 131) |
| F10 | `OpenSessionParams = { profile, database?, applicationName, openTimeoutMs?, requestedCapabilities?, auth? }` — **no** session-level priority or commandKind | `services/sqlDataPlane/api.ts` |
| F11 | `ISqlSession.execute(text: string, opts: ExecuteOptions, sink): QueryHandle` — **text only, no parameter binding**. `ExecuteOptions = { pageRows?, pageBytes?, maxCellBytes?, priority?: "interactive"\|"background", tag?, commandKind?: "user"\|"metadata"\|"plan"\|"parse"\|"replay", timeoutMs?, expectedDatabase?, catalogGeneration? }` | same file |
| F12 | The metadata engine already models the intended usage: per-execute `{ priority:"background", commandKind:"metadata", tag }` | `services/metadata/metadataService.ts` (~line 412) |
| F13 | The observability registry is generated in `perftest/packages/observability-contracts` and **vendored** as `sharedInterfaces/observabilityContract.generated.ts` ("GENERATED — do not edit… npm run generate, then vendor. Registry obs-contract/1"). Entries: `{name?|prefix?, kind, phase?, pairsWith?, feature, processRoles, timingClass, measurementEligible, attrs, attrsComplete, notes?}` | `sharedInterfaces/observabilityContract.generated.ts` |
| F14 | Exit codes 0–6 are taken and documented "never repurpose a code"; **7 is free**; no `central`/`push` code exists anywhere in the CLI yet (greenfield) | `packages/perftest-cli/src/exitCodes.ts`; repo grep |
| F15 | `environmentHash = "sha256:" + sha256(canonicalJson(fingerprint))` — a working `canonicalJson` already exists in the CLI | `packages/perftest-cli/src/run/environment.ts` (~line 95) |
| F16 | Local SQLite twin facts the base omits: `repetitions` and `metrics` carry **`attempt_id INTEGER NOT NULL DEFAULT 0`**, and `official_metric_samples` joins on `(run_id, scenario_id, rep_id, attempt_id)` with `WHERE m.official=1 AND r.pass_type='measurement' AND rep.status='passed'`; `runs` has `output_dir NOT NULL`, `config_path`, `machine_id`, `notes`; `repetitions.result_path NOT NULL`; `environments.machine_id`; `artifacts` has absolute `path` + `sha256` + `retention`; `baselines` PK is `(baseline_name, scenario_id, metric_name, environment_hash)` **with nullable members** (legal in SQLite, illegal in SQL Server); `comparisons`/`comparison_metrics` are local analysis outputs | `packages/perf-contracts/sql/perf-store.schema.sql` |
| F17 | Debug Console store roots and knobs (upload sources): session-diag journals under `<globalStorage>/ms-mssql.mssql/session-diag/`, perf runs under `<globalStorage>/self-test-runs` (`mssql.debugConsole.perfRunsRoot`); `perfRunImport.ts` maps a run directory (markers.jsonl, result.json…) — the "imported perf run" upload path reads the same ground truth as `perftest push` | `vscode-debug-COMBINED.md` §2; `diagnostics/perfRunImport.ts` |

---

## 2. Corrections (C-1 … C-15)

### C-1. Store `source_digest`; key the refusal/reprojection algebra on it [C0.1, C0.2] — MUST

Base §6.2 defines `source_digest` ("digest of source artifact inventory"); base §5.3/§5.5 then persist only `content_digest` + `projection_digest`. That breaks §6.3's own outcome table: `content_digest` is *policy-filtered* content, so uploading the same untouched session under `team-names.v1` after a `team-default.v1` upload produces a different `content_digest` under the same natural key and the same projector — which the base classifies as **refused** ("evidence mutation"). It isn't.

Normative changes:

- Add `source_digest nvarchar(100) NOT NULL` to `central.upload_batches` and `central.central_entities`.
- `source_digest` covers the **pre-policy** source inventory: for a `diagSession` — manifest schemaVersion, sessionId, eventCount, gapCount, segments (file, firstSeq, lastSeq, events), sizeBytes, droppedRanges; for a `perfRun` — result.json schema version, runId, per-rep result digests, markers/env file digests. It must be computable without reading payload bodies where the manifest already vouches for them, and identically by both writers.
- Replace the base §6.3 outcome table with:

| existing entity | incoming | outcome |
|---|---|---|
| none | valid projection | `inserted` |
| same `source_digest`, same `(contractVersion, projectorVersion, uploadPolicyId)`, same `projection_digest` | duplicate | `alreadyPresent` (ledger evidence, no rows) |
| same `source_digest`, same versions/policy, **different** `content_digest` or `projection_digest` | projector nondeterminism | `refused: projectionMismatch` — this is now unambiguously a bug signal |
| same `source_digest`, newer `projectorVersion` (or same projector, different `uploadPolicyId`) | legitimate re-projection | `reprojected` via the stored proc; old digests preserved in ledger; entity records new policy/projector |
| **different `source_digest`**, same natural key | source mutated under a supposedly-immutable key | `refused: sourceMutation` — entity unchanged, loud ledger row |
| same sessionId, prior committed, `source_digest` differs only by appended events (C-6 prefix rule) | growing session | `extended` (C-6; built in C5) |
| policy prohibits a class pre-transport | — | `refusedByPolicy` (client-side, still ledgered via a begin+abort pair) |
| cancel mid-stream | — | `abandoned`/`failed`, entity unchanged |
| purge | — | `purged` |

- `upload_batches.status` gains `extended`; §14 decision 6 is amended accordingly ("digest drift" now means *source* drift).

### C-2. Disposition is decided at `usp_begin_upload`, under the entity lock — not discovered at commit [C0.1] — MUST

The base's flow (stage items → commit decides) writes kind-table rows for uploads that turn out to be `alreadyPresent` or `refused`, then needs cleanup. Move the decision to the front:

- `central.usp_begin_upload(@kind, @natural_key, @source_digest, @content_digest, @projection_digest, @contract_version, @projector_version, @upload_policy_id, @preview_digest, @tool, @tool_version, @uploader…)` acquires `sp_getapplock` (`Exclusive`, resource = `'central:' + kind + ':' + lower-hex sha256(natural_key)`, session-scoped within the transaction), evaluates the C-1 table, and returns a **disposition row**: `proceed(new batch_id)` \| `alreadyPresent(existing entity)` \| `refused(reason)` \| `resume(batch_id, applied items…)` \| `extendCandidate(prior entity facts)` (C5).
- **Resume:** if a prior batch for the same key sits in `started` with identical digests and the same writer identity, `begin` returns that batch id plus the set of `(item_kind, item_ordinal, payload_digest)` already `applied`; the writer skips matching items. This is the whole cancel/resume story — no new machinery.
- `usp_commit_upload` re-acquires the same lock, re-checks the disposition (double-checked locking against a racing writer), verifies item accounting (H-3), flips `central_entities.current_batch_id` (insert or update) and stamps `committed_at_utc` — all in one transaction. Uniqueness constraints remain the last line of defense exactly as the base says.
- Writers therefore never stage a byte for a duplicate. `refusedByPolicy` still executes `begin` + `usp_abort_upload` so the refusal is ledgered with safe reason codes.

### C-3. Reader visibility is structural: kind rows join through `current_batch_id` [C0.1] — MUST

Base rule 3 ("ledger last… partial batches are ingestion evidence, not analysis rows") needs a mechanism, because staged rows land in the kind tables before commit:

- Every kind table (runs, repetitions, metrics, validations, artifact refs, diag_sessions, diag_events, diag_gaps, markers, sql_activity) carries `upload_batch_id bigint NOT NULL`.
- Every canned view and iTVF joins `central.central_entities e ON e.current_batch_id = k.upload_batch_id` (plus the natural-key/entity join as convenient). Rows from `started`/`failed`/`abandoned`/superseded batches are invisible **by construction**, not by remembering a `WHERE status='committed'`.
- Reprojection becomes clean: the new batch stages beside the old, the pointer flips, and the old batch's rows become sweepable garbage. `usp_retention_cleanup` gains an **orphan sweep**: delete kind rows whose batch is not any entity's `current_batch_id` and whose batch `started_at_utc` is older than 7 days; promote `started` batches older than 7 days to `abandoned` first.

### C-4. `diag_events` matches the real envelope [C0.1, C0.2] — MUST

Column-level deltas against base §5.7, from F3/F4:

- `event_id nvarchar(80) NOT NULL` — the envelope's `eventId` is required; the base's `NULL` invites writer divergence.
- Add `entity_kind nvarchar(40) NULL`, `entity_ref nvarchar(200) NULL` from `DiagEvent.entity` — the join anchor the base drops (e.g. `{kind:"document", id:"uri:sha256:…"}`). Projection rule: `entity.id` values already in digest form pass through; anything else is treated as `source.path`-class and digested under `team-default`.
- Add `tags_json nvarchar(400) NULL` (`diagnostic.metadata`; e.g. `viewerInternal` matters for honest error-rate views).
- Add `cls_redacted_fields int NOT NULL` from `cls.redactedFields` — this powers `policy_drop_summary` for capture-side redaction, distinct from upload-side drops.
- `cls_rank int NOT NULL` gets a concrete definition: **the index of `cls_max` in the vendored `RANK_ORDER`** (F2, Appendix B). The contract package vendors the array with a `rankTableVersion`; `schema_info` records the version; reprojection under a newer rank table recomputes `cls_rank` (that is a `reprojected`, not a mutation). Never `ORDER BY cls_max` lexicographically — `secret` would sort before `sql.text`.
- `monotonic_ns` **stays** `nvarchar(40)` — the envelope carries a decimal-ns string (marker-contract precedent, F3); do not cast at ingest. Views that need arithmetic use `TRY_CONVERT(bigint, …)`.
- Add `event_time_utc datetime2(3) NOT NULL`, **computed by the projector** from `epochMs` (not a SQL computed column — `DATEADD` can't take the bigint directly and we want writer parity anyway). Retention, the recommended time indexes, and human queries key off it; `epoch_ms` remains the exact value.
- Pin `kind`/`status`/`process`/`timing_class` with CHECK constraints generated from the vendored unions (F3); `schema_info` records the union version so `central check` can flag skew.
- `payload_json` stores the **post-upload-policy** `payload` map, preserving each field's `{cls, handling, digest?, len?}` shape — the upload boundary may re-digest a `plain` field whose class the policy demands digested (base §7.1), and `handling` is how a reader can tell.

### C-5. Gaps are rows, not just a count [C0.1, C0.2] — MUST

The journal interleaves `GapRecord`s (F5) and the manifest carries `droppedRanges` (F6); flattening to `diag_sessions.gap_count` throws away exactly the evidence a triage query wants ("was the error cluster inside a dropped range?").

```sql
CREATE TABLE central.diag_gaps (
    session_sk        int          NOT NULL,          -- H-1
    upload_batch_id   bigint       NOT NULL,
    gap_id            nvarchar(80) NOT NULL,
    from_seq          bigint       NOT NULL,
    through_seq       bigint       NOT NULL,
    dropped_count     int          NOT NULL,
    reason            nvarchar(40) NOT NULL,           -- subscriberOverflow | sinkOverflow | journalUnavailable
    backfill_status   nvarchar(20) NOT NULL,
    first_available_seq bigint     NULL,
    epoch_ms          bigint       NOT NULL,
    CONSTRAINT pk_diag_gaps PRIMARY KEY (session_sk, gap_id)
);
```

Projected from journal GapRecords, unioned with manifest `droppedRanges` (synthesized `gap_id = 'range:'+fromSeq`). `diag_sessions.gap_count` stays as the summary. Views computing `sessions_by_feature_error_rate` MUST note gap-awareness: an error rate over a gappy window is labeled `partialWindow` (reader honesty, base §5.9).

### C-6. Session status mirrors the manifest; live-session upload is deferred behind an explicit `extended` path [C0.1, C2, C5] — MUST

Two entangled fixes:

1. `central.diag_sessions.status` allows exactly `active | closed | partial` (F6). The base's `uploaded` value conflates source state with central state — upload state already lives on the entity/batch spine. Drop it.
2. Base §8.3's "upload current session snapshot after the manifest is closed or checkpointed" collides with C-1: the manifest has no `checkpointed` status, and a later upload of the now-longer session is a *different `source_digest` under the same natural key* → `refused: sourceMutation`. Resolve it in two steps:
   - **C2 (v1): only `closed` and `partial` sessions are uploadable.** The "upload current session snapshot" entry point performs the existing close/rotate, then uploads. Simple, honest, zero new protocol.
   - **C5: the `extended` outcome.** `usp_begin_upload` detects same sessionId + prior committed entity + incoming `eventCount > prior.eventCount` + **prefix rule**: the digest of the first `prior.eventCount` events (per-segment digests make this cheap) equals the prior content basis. Disposition `extendCandidate`; the writer stages only items covering `seq > prior.lastSeq`; commit appends, updates entity digests/counts, ledgers `extended`. Anything failing the prefix rule is `refused: sourceMutation` as before.
   - Q-2 asks whether you want `extended` pulled forward; default is as above.

### C-7. Provenance is policy-filtered like everything else; `machineLabel` is the canary [C0.2, C0.3] — MUST

`ProvenanceSummary.machineLabel` (F7) is a machine name riding inside `diag_sessions.provenance_json`; the base filters payloads but says nothing about provenance. Rules:

- `provenance_json` is produced by the same projection/policy path as payloads. Under `team-default.v1`: `machineLabel` → digest; `commit`, `dirty`, `extensionVersion`, `vscodeVersion`, `stsVersion`, `environmentHash` → keep (they're the join keys the whole feature exists for).
- Promote `product_sha` (from `commit`) and `environment_hash` onto `diag_sessions` columns for indexed joins (the entity already carries them; keep both in sync at projection).
- Privacy canaries (base §7.4) gain: `machineLabel`, plus the perf-twin label columns from C-8.

### C-8. The perf twin needs a subtraction list, not just additions [C0.1, C0.2, C0.3] — MUST

Base §5.6 says "dialect twin plus central additions." The local schema (F16) contains columns that must **not** cross the boundary verbatim. Appendix A is the full per-column classification map; the binding rules:

- **Drop centrally:** `runs.output_dir`, `runs.config_path`, `repetitions.result_path` (absolute local paths, `source.path`); `runs.notes`, `baselines.notes` (`user.text`) under `team-default`/`ci-official` (allowed under `team-names.v1`+).
- **Digest centrally:** `runs.machine_id`, `environments.machine_id` (label class); `baselines.created_by` becomes `uploader_id bigint FK` instead of free text.
- **Artifacts:** central `artifact_refs` stores `relative_path` only (projection verifies the path is relative to the run root; absolute → `refusedByPolicy`), plus `sha256`, `size_bytes`, `kind`, `content_type`, `retention`. The blob itself stays external (base non-goal, unchanged).
- **Keep:** every `environments.*` hardware/OS/version column (`system.metadata`), `config_fingerprint_json`, `sql_image_digest`, `sql_snapshot`, all metric/validation columns.
- **Local-only, never uploaded:** `comparisons`, `comparison_metrics` — they're derived analysis; the central store recomputes trends/regressions through views (Q-7 confirms).
- `runs.status` centrally includes `aborted` (present locally, missing from base prose).

### C-9. `attempt_id` and exact `official_metric_samples` parity [C0.1, C0.4] — MUST

`repetitions` and `metrics` carry `attempt_id` and the local view joins on it (F16). The central twin MUST carry `attempt_id` on `repetitions`, `metrics`, `validations`, `artifact_refs`, and the central `official_metric_samples` MUST reproduce, in T-SQL, exactly: the four-column join `(run_id, scenario_id, rep_id, attempt_id)` and `WHERE m.official = 1 AND r.pass_type = 'measurement' AND rep.status = 'passed'` — no re-derivation, no improvements. Conformance test T-B7 runs the fixture through both engines and byte-compares canonicalized row sets. Central additions to the view's SELECT list (e.g. `uploader_id`, branch context) go in a *separate* `official_metric_samples_ex` view so the parity surface stays frozen.

### C-10. `baselines` PK is illegal in T-SQL as twinned [C0.1] — MUST

SQLite permits NULLs inside the composite PK `(baseline_name, scenario_id, metric_name, environment_hash)`; SQL Server does not. Central shape:

```sql
CREATE TABLE central.baselines (
    baseline_id        bigint IDENTITY PRIMARY KEY,
    baseline_name      nvarchar(120) NOT NULL,
    scenario_id        nvarchar(200) NOT NULL DEFAULT N'',   -- '' = wildcard (maps NULL)
    metric_name        nvarchar(200) NOT NULL DEFAULT N'',
    environment_hash   nvarchar(100) NOT NULL DEFAULT N'',
    run_id             nvarchar(100) NOT NULL,
    uploader_id        bigint        NOT NULL REFERENCES central.uploaders(uploader_id),
    created_at_utc     datetime2(3)  NOT NULL DEFAULT sysutcdatetime(),
    CONSTRAINT uq_baselines UNIQUE (baseline_name, scenario_id, metric_name, environment_hash)
);
```

The codec documents the `NULL ↔ ''` mapping in both directions; fixtures include a wildcard baseline. Writes only via `usp_set_baseline`, which checks `IS_ROLEMEMBER('central_ci') = 1` (H-5).

### C-11. Product-writer transport, corrected to the real Data Plane [C2, plus one tiny product PR] — MUST

Base §8.3 vs F10/F11/F12:

- **Session:** `openSession({ profile, database: <central db>, applicationName: "vscode-mssql-central-upload", auth })`. There is no session priority/commandKind (F10).
- **Every execute:** `opts = { priority: "background", commandKind: "centralUpload", tag: "centralUpload", timeoutMs: 30_000 per item / 60_000 for commit, expectedDatabase: <central db> }`. `expectedDatabase` gives us the same tripwire discipline the metadata engine uses. **Product PR (pre-C2):** add `"centralUpload"` to the `ExecuteOptions.commandKind` union in `services/sqlDataPlane/api.ts` and thread it through the adapter/fake backend (additive string union; Q-1 offers reusing `"metadata"` if you'd rather not touch the union).
- **No parameter binding exists** (F11). TVPs are off the table for the product writer; `OPENJSON` inputs ride as N-string literals. Therefore the contract package owns a **SQL literal encoder**: `sqlNString(json: string): string` — doubles `'`, refuses U+0000 (projection strips it from payload values earlier and counts it as `truncated` handling), emits `N'…'`, and enforces a per-execute text budget. Item call shape: `EXEC central.usp_stage_upload_item @upload_batch_id=…, @item_kind=N'diag_events', @item_ordinal=…, @row_count=…, @payload_digest=N'…', @payload=N'<escaped JSON array>';` with the proc shredding via `OPENJSON … WITH (…)`.
- **Item sizing:** target ≤ 1.5 MB of batch text per execute → roughly 1,000–2,000 events per item at observed payload sizes; a 100k-event session is ~60–100 items. Memory stays bounded because F8's segment grain feeds the item grain — read segment, project, encode, execute, release.
- **Cancellation/resume:** cancel between items only (the base already says this); resume rides C-2's `begin` disposition.
- **Readback provider paging** uses the mechanism that already exists: `pageRows`/`pageBytes`/`maxCellBytes` on `ExecuteOptions` plus `ORDER BY`-stable keys with `OFFSET/FETCH` in the canned procs — "page every list" is now a named API, not an aspiration.
- CONSIDER (recorded, not v1): optional `params` on `ISqlSession.execute` would delete the encoder and its whole risk class; right investment window is C3+, alongside any other feature that wants it.

### C-12. Central Perf History states are a union extension, not prose [C3] — MUST

F9's `PerfSourceStatus` has no `unavailable` or `permission` value, and `filtered` isn't a source-level state at all. Concretely:

- `PerfSourceKind` += `"central"` (as the base says). `PerfSourceStatus` += `"unavailable" | "permissionDenied"`. Webview switch sites updated (small; the union is exhaustive-switched in the pages).
- "Filtered by official/diagnostic rules" and "dropped by upload policy" are **query-result** facts, not source states: central query responses gain `resultFlags?: Array<"officialOnly" | "policyDropped" | "partialWindow" | "rowCapped">` so a list can be simultaneously `indexed` and visibly filtered. This is how base §5.9's five-way distinction actually reaches the UI.
- The sqlite source's `unsupported` registration (F9) is the pattern to copy for "central configured but data plane can't open": register the source with `status:"unavailable"` + `statusMessage`, never hide it.

### C-13. Vocabulary lands in the existing generated registry; CLI events live in harness telemetry [C0.6, C1, C2] — MUST

F13 fixes the mechanism the base gestures at: central event vocabulary is authored in `perftest/packages/observability-contracts`, `npm run generate`, vendored into `sharedInterfaces/observabilityContract.generated.ts`. Product-side families (DiagEvents, `feature: "centralObservability"`):

```
centralObservability.preview            span   (begin/end; attrs: sourceKind, policyId, tables, droppedFields, digestedFields, bytesEstimate)
centralObservability.upload             span   (attrs: batchOutcome, items, rows, waitedMs)
centralObservability.upload.item        spanFamily prefix (attrs: itemKind, ordinal, rowCount)
centralObservability.upload.refused     event  (attrs: reasonCode)
centralObservability.provider.query     span   (attrs: viewName, rowCount, resultFlags)
centralObservability.provider.failed    event  (attrs: errorClass)
```

Allowed attr classes per base §11 (counts, durations, policy id, outcome, schema version, short fingerprint prefixes, view name); the registry entry `attrs` maps carry the classification notes, and the existing unregistered-emission conformance test extends to the new family for free. **CLI-side** `push`/`migrate` events are *harness self-telemetry* spans (`centralPush.begin/end`, `centralPush.item`, `centralMigrate.*`) in `harness-log.jsonl` conventions — the CLI does not emit DiagEvents. Perf markers for PERF_MODE scenarios are separate and listed in §9.

### C-14. Pin the uploader principal digest recipe [C0.2] — MUST

Base §5.2 says "non-reversible stable digest" without a recipe; two writers will invent two. Contract-owned:

```
principal_digest = "prn_" + b64url(sha256("central-principal\u0000" + principal_kind + "\u0000" + normalized)) [0..22)
normalized: domainUser/alias → trim + lowercase UPN/alias; ci → pipelineIdentity + "\u0000" + poolName; servicePrincipal → appId
```

Same house style as `sfp_`/`pfp_` (22-char b64url). Documented explicitly as **not a security boundary** (internal store, guessable inputs) — it exists for stable joins without storing labels. `display_name` populated only when the policy permits a plain alias (base rule preserved).

### C-15. "Signed" preview becomes `preview_digest` [C0.2, C0.1] — MUST

No signing infrastructure exists or is warranted. `preview_digest = sha256(canonicalJson(UploadPreview))`; the writer passes it to `usp_begin_upload`; `upload_batches` stores it; the receipt echoes it. Combined with H-3's count verification, the receipt is checkable evidence: this exact preview produced this exact commit. Amend base §0.1/§7.3 wording from "signed" to "digest-pinned."

---

## 3. Ingest protocol — normative shape

For the agent; supersedes base §6.4's prose where they differ.

```text
usp_begin_upload(kind, natural_key, source_digest, content_digest, projection_digest,
                 contract_version, projector_version, upload_policy_id, preview_digest,
                 tool, tool_version, principal…)
  BEGIN TRAN
    sp_getapplock 'central:'+kind+':'+sha256hex(natural_key)  (Exclusive, Transaction)
    e := SELECT … FROM central_entities WHERE kind=@kind AND natural_key=@natural_key
    r := SELECT … FROM upload_batches WHERE status='started' AND same key AND same digests AND same uploader
    disposition := C-1 table (e, incoming, r)
    IF proceed/resume: upsert 'started' batch row (resume returns existing batch + applied items)
  COMMIT  →  return disposition row(s)

usp_stage_upload_item(batch_id, item_kind, item_ordinal, row_count, payload_digest, payload NVARCHAR(MAX))
  validate batch status='started' and ordinal uniqueness (uq_upload_items)
  OPENJSON(@payload) WITH (…contract columns…)  →  INSERT kind table rows carrying upload_batch_id
  UPDATE upload_items SET status='applied', row_count, payload_digest
  (idempotent: same (batch,kind,ordinal,payload_digest) already applied → no-op 'applied')

usp_commit_upload(batch_id, expected_items, expected_rows_json)
  BEGIN TRAN
    re-acquire the same applock; re-run the disposition check (racing writer defense)
    verify: every expected item status='applied'; per-item COUNT(*) of inserted kind rows == staged row_count (H-3)
    upsert central_entities (current_batch_id=@batch_id, digests, versions, policy, env hash, product sha)
    UPDATE upload_batches SET status = committed|reprojected|extended, committed_at_utc
  COMMIT  →  receipt row (batch id, outcome, rows, policy, digests, preview_digest)

usp_abort_upload(batch_id, reason_code)         → status abandoned|failed|refusedByPolicy; entity untouched
usp_purge_entity(kind, natural_key, reason)      → H-4
usp_set_baseline(…)                              → IS_ROLEMEMBER('central_ci') gate (H-5)
usp_retention_cleanup(…)                         → H-4 lanes
usp_store_health()                               → H-6 row set
```

Lock discipline: applock on the entity key hash is the concurrency unit (base's own suggestion, now mandatory); `UPDLOCK, HOLDLOCK` on `central_entities` inside the same transaction as belt-and-braces; **no `MERGE`** (base decision 4 stands; nothing here needs it).

---

## 4. Schema deltas beyond §2

- **H-1 applied:** `diag_sessions` gains `session_sk int IDENTITY` with `UNIQUE(session_id)`; `diag_events` and `diag_gaps` key on `(session_sk, seq/gap_id)` and drop `session_id` from their rows and indexes entirely (join through `diag_sessions`). At 90-day volumes this halves nonclustered index width vs an `nvarchar(100)` key riding every row, and it makes retention a whole-session operation (H-4). The three base-recommended indexes are kept, re-based on `session_sk` + `event_time_utc`.
- `upload_batches` += `source_digest`, `preview_digest`, `extended` status (C-1/C-15); `central_entities` += `source_digest`.
- All kind tables += `upload_batch_id NOT NULL` (C-3); perf kind tables += `attempt_id` (C-9).
- Time columns: journal/marker decimal-ns strings persist as `nvarchar(30)` truth columns where they exist locally; every table adds a projector-computed `*_utc datetime2(3)` for indexing/retention (C-4 pattern generalized).
- `schema_info` += `rank_table_version`, `union_versions_json`, `min_compat_level` (H-2).
- `ISJSON` CHECKs on every `*_json` column (base note, now unconditional given H-2's floor).

---

## 5. Privacy additions

- Canary corpus (base §7.4) extends with: `machineLabel` (C-7), `machine_id`, `created_by`, absolute paths in `output_dir`/`config_path`/`result_path`/`artifacts.path` (C-8), an `entity.id` that is *not* digest-form (C-4), and **escaper bombs** for C-11: payload values containing `'`, `''`, `N'`, `];--`, U+0000, unpaired surrogates, and a 9 KB single field (exercises the `truncated` path). Canary scans cover: projected rows, preview JSON, DiagEvents, harness-log, CLI stdout, receipt UI text, and dashboard seed data (base list + the two new render surfaces).
- `RANK_ORDER` is vendored verbatim into `perf-contracts/src/central/policies.ts` with `rankTableVersion: "cls-rank/1"` (Appendix B); the policy matrix in base §7.2 is *generated from* a table keyed by these class strings so the two repos cannot drift (T-B4 pins generated output equality).
- Upload-policy application operates on `{cls, handling}` pairs (F4): a `plain` value whose class the policy digests is re-digested at the boundary with `handling:"digest"`; `omitted`/`redacted` values pass through untouched. The base's "re-apply classification" gets this as its concrete semantics.

---

## 6. Writer specifics

**CLI (`perftest push`, C1):**
- `exitCodes.ts` += `pushFailed: 7` — the file's "never repurpose" contract holds (F14).
- **Move `canonicalJson` from `perftest-cli/src/run/environment.ts` into `perf-contracts/src/central/digest.ts`** and re-export for the CLI; the environment-hash recipe (`"sha256:"+hex`, F15) is unchanged and becomes the shared canonicalization every central digest uses. One implementation, two writers, zero drift — this is the C0.2 keystone.
- SQL client: `mssql` (tedious) as a `perftest-cli` dependency only; parameterized calls to the same procs (the CLI is *not* forced through the literal encoder — but T-B6 projects one fixture through both call styles and compares stored rows, so the encoder can't diverge silently).
- Connection resolution: `--target` arg else `MSSQL_PERFTEST_CENTRAL_CONNSTRING`; never persisted, never echoed (canary-scanned in CLI output).
- `push` reads the run directory (base rule) — note `perfRunImport.ts` (F17) already demonstrates the directory→facts mapping the projection layer formalizes; the product's "upload imported perf run" path and `push` MUST share the generated projection, which is exactly what T-B5's parity fixture proves.

**Product (Debug Console, C2):** C-11 in full; entry-point precondition per C-6 (closed/partial only in v1); settings as base §8.3 with one addition — `mssql.centralObservability.maxItemBytes` (internal, default 1.5 MB) so the encoder budget is tunable in dogfood without a rebuild.

**CI (C1′):** unchanged from base except `pushFailed` is 7 and the job summary line is emitted even on success (receipt id + row counts) so central health has a CI heartbeat to cross-check.

---

## 7. Readback (C3)

C-12 in full, plus: trend parity (base §8.4 last rule) becomes T-B12 — the provider's trend series for a fixture scenario must equal the direct `central.trend(…)` iTVF rows on the same container DB, and the iTVF itself must match the CLI `perftest trend` math on the mirrored local fixture. Provider execute options always set `pageRows`/`pageBytes`; provider never selects from base tables (deny-by-role makes this structural, H-5).

---

## 8. Observability vocabulary

C-13's families registered in `observability-contracts` and vendored; product markers for PERF_MODE (Perf facade, `mssql.*` family, `sameProcessMonotonic`, `measurementEligible: true`):

```
mssql.central.preview        begin/end
mssql.central.upload         begin/end        (attrs: items, rows)
mssql.central.provider.list  begin/end        (attrs: page, rowCount)
```

CLI harness spans: `centralPush.begin/end`, `centralPush.item`, `centralPush.commit`, `centralMigrate.apply`, `centralCheck.run`. Nothing in either family may carry names, paths, endpoints, or SQL text — same allowlist enforcement as the metadata family.

---

## 9. Perf and soak scenarios

All scenario timings from marker pairs per the perftest contracts; official only where the environment is controlled. Standing QS 10k gates (389–1100 ms band) must not move — central code paths are inert outside explicit use.

| Scenario | Measures | Budget / gate |
|---|---|---|
| `central-upload.session.100k` | fixture 100k-event session: preview build; full upload wall; peak ext-host heap (rich pass) | preview p95 < 1.5 s; upload < 60 s to container; heap delta < 150 MB; **0 Busy** on any session |
| `central-upload.resume` | cancel at item ~50%, re-run | resumed items skipped == applied set; identical final digests |
| `central-push.run.tier1` | fixture run push via CLI | < 3 s to container; duplicate re-push `alreadyPresent` < 300 ms |
| `central-provider.list.paged` | central runs list, page 1 and page N | p95 < 200 ms/page on 1k-run fixture; `pageRows` honored |
| `central-provider.trend` | trend iTVF via provider | parity with direct SQL (T-B12); p95 < 300 ms |
| `central.retention.cleanup` | 30-day fixture; cleanup proc | whole-session deletes; health coherent after; < 30 s on fixture volume |
| `mssql.perf.centralUploadRoundTrip` (base §12.4) | end-to-end self-test probe | promoted to a perftest scenario once stable, exactly as base says |

Initial `central-push` timings are **non-gating** (container variance) — recorded, trended, gated only after variance evidence; the upload scenario's *Busy=0* and *resume-correctness* assertions gate from day one.

## 10. Test obligations

T-B1 disposition algebra: every C-1 row exercised against a container DB, including the policy-change→`reprojected` and source-mutation→`refused` lanes. T-B2 begin-lock race: two concurrent writers, same key — one `proceed`, one `alreadyPresent`/`resume`, zero duplicate kind rows. T-B3 resume: kill mid-stream, re-run, applied-item skip verified, commit counts exact. T-B4 policy matrix generation parity across repos; RANK_ORDER vendor equality. T-B5 golden run + golden session projected by CLI and by vendored product code → byte-identical canonical row streams (base §12.1, now with the C-8 subtraction map in the goldens). T-B6 encoder-vs-parameterized call parity (C-11/§6). T-B7 `official_metric_samples` parity incl. `attempt_id` (C-9). T-B8 canary corpus incl. §5 additions across all render surfaces. T-B9 gap projection: journal GapRecords + droppedRanges → `diag_gaps`; `partialWindow` flag surfaces. T-B10 C-6 preconditions: active session upload refused in v1 with actionable message; (C5) extend prefix rule pass/fail pair. T-B11 provider union: `unavailable`/`permissionDenied`/`empty`/`error`/`resultFlags` rendered distinctly (fixture data plane). T-B12 trend parity. T-B13 purge: kind rows gone, ledger audit row remains, uploader display cleared on privacy purge, health reflects. T-B14 orphan sweep + `started`→`abandoned` promotion. T-B15 migration fixture: v(N-1) dump → migrate → check green; reprojection over migrated data. T-B16 corrupt/oversized payload item: proc rejects with safe error_code, batch `failed`, entity unchanged. T-B17 baselines: role gate blocks non-CI principal; wildcard `''` mapping round-trips. T-B18 count-mismatch commit refusal (H-3) with a doctored fixture.

## 11. Batch deltas

- **C0.1** += C-1/C-2/C-3/C-4/C-5/C-6(status)/C-9/C-10 DDL + §3 procs + H-1/H-2. **C0.2** += `canonicalJson` move, `source_digest` recipe, RANK_ORDER vendor, principal recipe (C-14), `preview_digest` (C-15), encoder `sqlNString`. **C0.3** += generated policy matrix + C-7/C-8 rules. **C0.4** += goldens embodying the subtraction map + canary additions; T-B1–T-B9. **C0.6** = C-13 registry entries. **C0.7** += compat/union/rank checks in `central check`.
- **Pre-C2 product PR** (tiny, standalone): `commandKind` union + adapter passthrough (Q-1).
- **C1** += exit code 7, both-call-style parity (T-B6). **C2** += closed/partial precondition, encoder budget setting, resume UX. **C3** += C-12 unions + `resultFlags` + T-B11/12. **C5** += `extended` path (C-6), markers/sql_activity tiers as base. **C6** unchanged + T-B13.

## 12. Open questions (decide before the agent reaches the marked batch)

- **Q-1 [pre-C2]:** add `"centralUpload"` to `ExecuteOptions.commandKind`, or reuse `"metadata"`? (Union touch vs semantic mush; addendum assumes the union add.)
- **Q-2 [C2/C5]:** live-session uploads — accept v1 = closed/partial only with `extended` in C5, or pull `extended` into C2?
- **Q-3 [C0.3]:** `artifact_refs.relative_path` under `team-default` — plaintext relative paths (assumed) or digest them too?
- **Q-4 [before C1′]:** hosting + auth (base decision 11): SQL auth vs Entra managed identity changes tedious config, role grants, and dogfooder friction; C1′ is blocked on this.
- **Q-5 [C0.1]:** confirm `monotonic_ns` stays a decimal string column (assumed; fidelity + marker-contract precedent) rather than `bigint` at ingest.
- **Q-6 [C0.1]:** approve the projector-computed `event_time_utc` (and `*_utc` siblings) as the indexing/retention time axis.
- **Q-7 [C0.1]:** confirm `comparisons`/`comparison_metrics` stay local-only (assumed) — central recomputes via views.

---

## Appendix A — Perf-twin column classification map (binding for C0.2/C0.3 goldens)

| Local column | Class | team-default | ci-official | team-names |
|---|---|---|---|---|
| runs.run_id, pass_type, status, config_hash, created_at_unix_ns | diagnostic.metadata | keep | keep | keep |
| runs.output_dir, runs.config_path, repetitions.result_path | source.path | **drop** | **drop** | digest |
| runs.machine_id, environments.machine_id | source.path (label) | digest | digest | plain label allowed |
| runs.notes, baselines.notes | user.text | **drop** | **drop** | keep |
| run_repositories.repo/sha/branch/dirty/remote | system.metadata | keep | keep | keep |
| environments.* (os/cpu/mem/versions), config_fingerprint_json, sql_image_digest, sql_snapshot | system.metadata | keep | keep | keep |
| scenarios.*, repetitions.(ids, attempt_id, status, warmup, trace_id, *_unix_ns) | diagnostic.metadata | keep | keep | keep |
| metrics.* (all), validations.* | diagnostic.metadata | keep | keep | keep |
| artifacts.path | source.path | relative-only (Q-3) | relative-only | relative-only |
| artifacts.sha256/size/kind/content_type/retention | diagnostic.metadata | keep | keep | keep |
| baselines.created_by | user label | → uploader_id FK | → uploader_id FK | → uploader_id FK |
| comparisons.*, comparison_metrics.* | — | **local-only** | local-only | local-only |

## Appendix B — RANK_ORDER, verbatim (`diagnostics/redaction.ts`; vendor as `cls-rank/1`)

```ts
const RANK_ORDER: DataClassification[] = [
    "public", "system.metadata", "diagnostic.metadata", "result.shape",
    "sql.digest", "source.path", "object.name", "schema.name",
    "database.name", "server.name", "user.text", "sql.text", "row.data",
    "model.prompt", "model.response", "unknown", "token",
    "connection.string", "secret",
];
// rank(cls) = index; unrecognized → RANK_ORDER.length
```

Note the deliberate quirks worth preserving: `unknown` outranks `model.response` but sits below `token`/`connection.string`/`secret`; policies that "drop unknown" (base §7.2) are consistent with this ladder.

## Appendix C — Stored-procedure surface (final list)

`usp_begin_upload`, `usp_stage_upload_item`, `usp_commit_upload`, `usp_abort_upload`, `usp_extend_upload` (C5), `usp_purge_entity`, `usp_set_baseline`, `usp_retention_cleanup`, `usp_store_health` — signatures per §3; every writer-role grant is EXECUTE on exactly this list and nothing else.
