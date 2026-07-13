# Central Observability — Design of Related Systems and Build Plan
## One shared SQL Server store, two ingestion paths: ad-hoc team uploads (Debug Console) and official CI/CD perf & stress results (perftest push)

**Status:** design + build plan for deep review, 2026-07-06.
**Supersedes/extends:** `options_for_central_tracing.md` (the options analysis — its Option A recommendation is taken as given here; this document turns it into an explicit system design and plan). Sequencing IDs C0–C7 keep the meaning they have in `central_remaining_docs_review_pack/remaining_tasks.md` §5.9.
**Code truth:** vscode-mssql `dev/query` @ `091b6712b`; perftest `dev/query` @ `a01dc2c`. Every "exists today" claim below is against those heads.
**Companion:** `CENTRAL_OBSERVABILITY_VISUALS.tex` (pages P1–P5, same visual language as the metadata/STS2 review packs).

---

## 0. Executive summary

Build **one central SQL Server store** with **two writers against one shared, vendored contract**:

1. **Ad-hoc central observability** — engineers and internal dogfooders upload *diagnostic sessions* (normal-usage journals) and *locally-imported perf runs* from the Debug Console's export surface, over the extension's own SQL data plane, with an exact "what leaves the machine" preview. This is the "everyone on the team can share evidence" path.
2. **Official CI/CD results** — `perftest push` publishes perf/stress *runs* (and later their marker/SQL-activity detail) from the CLI, wired into CI after the local gate passes. This is the "fleet history, baselines, regressions" path.

They are **the same store and the same schema** because the analysis questions span both ("did the fleet regress?" next to "what are dogfooders actually hitting?"), and because the store's spine — an **ingest ledger** with `kind = perfRun | diagSession | featureTrace` over kind-specific detail tables — makes "runs vs. sessions" a first-class dimension rather than two databases to reconcile. They are **two writer implementations** because the CLI and the extension host have different, already-proven SQL access paths (tedious in Node; the product's own data plane in the extension) — but both implement one contract (DDL, DTOs, idempotency rules, upload-policy vocabulary) that lives in `perf-contracts` and is vendored into vscode-mssql exactly like `observabilityContract.generated.ts` is today, with conformance fixtures run in both repos so the implementations cannot drift.

Files remain ground truth; the store is a queryable projection with append-only provenance. Uploads are idempotent by natural key (`runId` / `sessionId`), classified at the boundary (the same "classification decides, settings request" rule as capture), and recorded in a ledger that supports purge.

---

## 1. The two scenarios, stated precisely

### 1.1 Ad-hoc central observability (team/dogfood)

> An engineer or dogfooder has local evidence — a usage session where something felt wrong, a perf run they made on their machine — and wants it queryable by the team without zipping files around.

- Entry point: the **Debug Console**. Today it already exports redacted `mssql-diag-<ISO>.jsonl` and imports perf runs (`perfRunImport.ts`) into the session store. The new action is **"Upload to shared server"** on (a) a diag session, (b) an imported perf run.
- The upload previews *exactly* what leaves the machine: row counts per table, the effective upload policy id, and every field dropped or digested by classification. Nothing uploads without that preview being accepted (or a `--yes`-style setting for repeat dogfood use).
- Dedup and identity are automatic: `sessionId`/`runId` are the natural keys; re-uploading is an upsert no-op recorded in the ledger; two people uploading the same run collide onto one row.
- "Runs vs. sessions" is explicit: a dogfooder's normal-usage **session** and a perftest **run** land as different ingest kinds over shared dimensions (uploader, machine label, environment hash, product SHAs), so aggregation can slice either kind alone or join them (e.g. error-rate in sessions on builds that also regressed a gate metric).

### 1.2 CI/CD official perf & stress results

> Scheduled and PR-triggered perftest runs on pinned agents publish results centrally; gates ride the existing exit-code contract; trends and baselines live in the store, not in artifact zips.

- Entry point: **`perftest push`** (CLI), invoked by the CI workflow after the local gate step. The gate never depends on the push (C1′ acceptance: "gate not dependent on central upload") — a central outage cannot block CI.
- Official/diagnostic separation survives centrally: gate and trend queries read the central `official_metric_samples` equivalent (measurement passes, official metrics, controlled environments only); exploratory scenarios (like `metadatacache-warm-acquire`) are present but visibly second-class.
- Baselines are **role-gated**: the CI principal can write fleet baselines; developer pushes are runs only. A dev machine must never silently move the fleet baseline.
- Stress/soak runs are ordinary runs with their own scenario ids and `passType`; nothing new is needed in the model beyond retention headroom for their larger rep counts.

**Answer to the "same or different?" question:** same store, same contract, same ledger; different writer processes reusing their platform's proven SQL path. The one shared *implementation* artifact beyond the contract is the fixture corpus: golden run/session fixtures that both writers must project into byte-identical rows (modulo uploader/timestamps), tested in both repos.

---

## 2. Related systems today (what each contributes)

| System (exists today) | Location | What it contributes to central |
|---|---|---|
| Per-rep `result.json` v2 + `markers.jsonl` + `environment.json` (env hash) + `summary.json` + reports | `perftest/perf-runs/<runId>/...` | Ground truth for run ingestion; `runId` embeds a hash → global natural key |
| SQLite `perf.db` + canonical DDL `perf-store.schema.sql` (runs, run_repositories, environments, scenarios, repetitions, metrics, artifacts, validations, baselines, comparisons, comparison_metrics, `official_metric_samples` view) | `perftest/packages/perf-contracts/sql/`, written by `sqliteStore.ts` | The central schema is a dialect translation of this, plus multi-user tables; `StoreConfig.type` already reserves a non-sqlite store kind |
| DiagEvent v1 + SessionDiagSink session store (`manifest.json` + `events/segment-*.jsonl`), classification `{v, cls, handling, digest}` per field, policy ids, gap accounting, ProvenanceSummary | vscode-mssql `src/diagnostics/` | Session ingestion shape; the classification taxonomy IS the upload filter |
| Debug Console: session browser, redacted `mssql-diag-*.jsonl` export, perf-run import, Perf History with provider abstraction (`PerfSourceKind = "directory" \| "sqlite" \| "bundle"`) | vscode-mssql | The upload UX host and, later, the central *read* provider (`"central"` joins the union) |
| SQL data plane (`ISqlConnectionService`/`ISqlSession`, passwordProvider closures, background command kinds) | vscode-mssql `src/services/sqlDataPlane/` | The product-side writer's transport — no new driver, dogfoods the plane |
| Contracts registry + vendoring workflow (`observability-contracts` → generate → vendored TS in vscode-mssql; conformance vitest both sides) | perftest | The pattern the central-store contract reuses verbatim |
| Exit-code contract (0/1/2/3/4/5/6), regression engine, baselines — **unwired in CI** | perftest | C1′ wires it; push adds code 7 |
| perftest SQL Server container tooling + `STS2_SQLSERVER_CONNSTRING` env pattern | perftest | Live integration tests for the store run against the same container |

Two structural facts carry the whole design: **idempotency keys already exist** (`runId`, `sessionId`, `environment_hash`, per-event `seq`), and **privacy is already field-granular at emit time** — the upload boundary filters by classification + policy, it does not invent a second redaction system.

---

## 3. Data model: the ingest spine and the two kinds

### 3.1 Ledger and dimensions (new tables)

```sql
CREATE TABLE uploaders (
    uploader_id    BIGINT IDENTITY PRIMARY KEY,
    principal      NVARCHAR(200) NOT NULL,   -- domain identity or stable self-chosen alias
    display_name   NVARCHAR(200) NULL,
    is_ci          BIT NOT NULL DEFAULT 0,
    first_seen_utc DATETIME2 NOT NULL,
    UNIQUE (principal)
);

CREATE TABLE upload_ledger (                 -- append-only; the audit trail
    upload_id        BIGINT IDENTITY PRIMARY KEY,
    uploader_id      BIGINT NOT NULL REFERENCES uploaders,
    kind             NVARCHAR(20) NOT NULL,  -- 'perfRun' | 'diagSession' | 'featureTrace'
    natural_key      NVARCHAR(200) NOT NULL, -- runId / sessionId / trace file id
    content_digest   NVARCHAR(80) NOT NULL,  -- sha256 of the canonical projected payload
    upload_policy_id NVARCHAR(100) NOT NULL,
    tool             NVARCHAR(40) NOT NULL,  -- 'perftest-push' | 'debug-console'
    tool_version     NVARCHAR(40) NOT NULL,
    outcome          NVARCHAR(20) NOT NULL,  -- 'inserted' | 'alreadyPresent' | 'reprojected'
    row_counts_json  NVARCHAR(MAX) NOT NULL, -- what landed, per table
    uploaded_at_utc  DATETIME2 NOT NULL
);
```

Rules:
- **Global uniqueness by natural key, not per uploader**: `runs.run_id` and `diag_sessions.session_id` are globally UNIQUE (both already embed enough entropy). A second uploader of the same run gets `alreadyPresent` in the ledger — provenance without duplication.
- **`content_digest` is the drift detector**: re-push with identical digest ⇒ no-op; with a different digest and a *newer projector schema version* ⇒ `reprojected` (rows replaced transactionally); with a different digest and the same schema version ⇒ refused loudly (ground-truth files should never change under a runId — that is a red flag, not a merge).
- **"Runs vs. sessions" is `kind`**, joined through shared dimensions: `uploaders`, `environments` (env hash), machine label, product git SHAs. That is what makes "aggregate normal usage AND perftest runs" a `GROUP BY kind` rather than a federation project.

### 3.2 Run kind (dialect translation of the existing schema)

`perf-store.schema.sql` translates mechanically (IDENTITY, NVARCHAR, `ISJSON` checks); the proven relational shape — runs → scenarios → repetitions → metrics/validations/artifact-refs, environments keyed by hash, baselines/comparisons — is kept **identical in meaning** so `official_metric_samples` central parity with local fixtures is a testable acceptance gate (C0). Additions: `runs.uploader_id`, `runs.upload_id`, and role-gating on `baselines` (CI principal only).

### 3.3 Session kind (new, mirrors the session store)

```sql
CREATE TABLE diag_sessions (
    session_id NVARCHAR(100) PRIMARY KEY,
    uploader_id BIGINT NOT NULL, upload_id BIGINT NOT NULL,
    source NVARCHAR(20) NOT NULL,            -- 'live' | 'perfRun' | 'bundle'
    capture_mode NVARCHAR(40), capture_policy_id NVARCHAR(100),
    created_utc DATETIME2, event_count INT, gap_count INT,
    provenance_json NVARCHAR(MAX),           -- version/commit/dirty/env-hash/machine label
    environment_hash NVARCHAR(80) NULL       -- when derivable; joins to environments
);
CREATE TABLE diag_events (
    session_id NVARCHAR(100) NOT NULL, seq BIGINT NOT NULL,
    event_id NVARCHAR(60), epoch_ms BIGINT, monotonic_ns BIGINT,
    process NVARCHAR(30), pid INT, feature NVARCHAR(40),
    kind NVARCHAR(20), type NVARCHAR(120), status NVARCHAR(20),
    trace_id NVARCHAR(40), cause_event_id NVARCHAR(60),
    duration_ms FLOAT NULL, timing_class NVARCHAR(40),
    cls_max NVARCHAR(40) NOT NULL,           -- highest classification present post-filter
    payload_json NVARCHAR(MAX) NOT NULL,     -- classification-FILTERED at upload
    PRIMARY KEY (session_id, seq)
);
```

Promoted columns (`feature/type/status/duration_ms/trace_id`) make the common queries index-friendly; everything else stays in filtered JSON. `diag_events` is the growth center — see retention (§6.4).

### 3.4 Detail tiers (later, C5)

`markers` (per-rep waterfall rows) and `sql_activity` rows are Tier 2/3: valuable for central waterfalls, big, and policy-sensitive (SQL text only from synthetic-DB diagnostic passes). They ship after the spine proves itself, behind the same ledger.

---

## 4. The shared contract (C0) — how two writers cannot drift

The contract lives in `perftest/packages/perf-contracts` (beside the schema it already owns) and consists of:

1. **DDL, both dialects**: `perf-store.schema.sql` (SQLite, existing) + `central-store.schema.mssql.sql` (new) + `schema_info` version row + forward-only migration scripts. Acceptance: fresh DB creates from scratch; migrations replay on fixtures.
2. **Projection DTOs + rules** (generated TypeScript, vendored into vscode-mssql like `observabilityContract.generated.ts`): the canonical row shapes for each table, the natural-key/idempotency rules of §3.1, the canonical-JSON recipe for `content_digest`, and the batching contract (max rows per statement, `OPENJSON` bulk-insert shapes).
3. **Upload-policy vocabulary**: named, versioned policies over the existing `DataClassification` taxonomy — `team-default` (allows diagnostic/safe-enum/structural values; digests identifier-sensitive; drops user SQL/result data/provider text; refuses `secret` always), `elevated-support` (explicit gesture, adds feature-trace payloads), `ci-official` (runs only, no sessions). Policy id lands on every ledger row and session row.
4. **The preview contract**: `UploadPreview { tables: {name, rows}[], policyId, dropped: {field, cls, count}[], digested: {...}[], bytes }` — computed identically by both writers from the same projection code path that produces the rows (the preview *is* the projection, dry-run).
5. **Fixture corpus + conformance tests**: golden run + golden session; both repos' test suites project them and compare against golden row sets; privacy canaries scan projected rows for seeded secrets/SQL/prompt markers. This is the mechanism that keeps two writers honest — same discipline as the event-vocabulary conformance tests that already run in both repos.

---

## 5. Writers

### 5.1 `perftest push` (C1) — CLI, runs

`perftest push [runId | --all-new] --target <env|connstring>`:
- Reads **`result.json` ground truth** (not `perf.db`) so a fresh clone can push history; projects via the contract; upserts by natural key; ledger row per push.
- Tier 1 payload: runs/environments/scenarios/repetitions/metrics/validations/artifact *refs*. `--with-markers` / `--with-sql-activity` arrive with C5.
- Connection: `MSSQL_PERFTEST_CENTRAL_CONNSTRING` env var or arg; never persisted; tedious driver (no native-ABI issue in the CLI).
- New exit code `7 pushFailed` (extends the existing contract; never overloads gate codes).
- Emits its own observability: `centralStore.push` span family (registered contracts-first) with row counts/duration/outcome — the uploader is itself observable in the Debug Console.

### 5.2 CI publish (C1′) — the workflow

GitHub Actions on a pinned self-hosted agent (env-hash stability): run gates → fail job on exit 1/4/5 → upload run directory as build artifact → `perftest push` (continue-on-error; a red push never blocks the gate) → job summary from `report.md`. Nightly scheduled runs push trend data; PR runs push with a `context` tag (branch/PR number) so fleet views can exclude or slice them. Baselines: only the CI principal's role may execute `baseline set` against central.

### 5.3 Debug Console "Upload to shared server" (C2) — product, sessions + imported runs

- Action on a session or imported run in the Debug Console; target picked from saved connection profiles (or a dedicated `mssql.centralStore.profile` setting for the team server).
- Transport: **the extension's own data plane** (`applicationName: "vscode-mssql-central-upload"`, background priority) — passwordProvider secrecy, no new driver, and the uploader dogfoods the same plane the metadata/OE work hardened this session (watchdogs, one-active-query lane discipline all apply).
- Batched parameterized inserts via `OPENJSON` bulk shapes from the contract; bounded memory for 100k-event journals (segment-by-segment streaming, ledger row written last = the upload's "manifest-last").
- UX: preview (from §4.4) → upload with progress → ledger receipt (upload id + row counts). Cancellation is clean at segment boundaries; a re-run resumes idempotently (events PK dedups).
- The same action on an **imported perf run** projects it as `kind='perfRun'` using the identical contract rows the CLI would produce — the fixture corpus pins this equivalence.

---

## 6. Cross-cutting: privacy, identity, retention, operations

### 6.1 Privacy
The upload boundary re-applies classification with the chosen policy — fields whose class the policy disallows are dropped or digested *again* even though capture already classified them (defense in depth; capture policy and upload policy can differ). Secrets never upload under any policy. Feature traces default excluded. Privacy canaries run in CI over projected fixtures, and the product-side preview shows drops per field class. The store itself is an internal-team, opt-in engineering system — explicitly **not** product telemetry (decision recorded in remaining-tasks "decisions to freeze").

### 6.2 Identity
No anonymous uploads: `uploaders.principal` is a domain identity or a stable self-chosen alias (dogfooders outside the immediate team may choose the alias + pseudonymized machine label; the upload policy's pseudonymize toggle covers `machineId`). The ledger is the audit trail; `sp_purge_upload(kind, natural_key)` deletes rows + ledger-marks the purge ("delete my upload" honored mechanically).

### 6.3 Auth & roles
Three database roles: `central_reader` (team, Grafana), `central_writer` (dev pushes + Debug Console uploads: INSERT/upsert on data tables + ledger, no baseline writes), `central_ci` (adds baseline writes + retention jobs). CI authenticates via managed identity/stored secret; humans via their normal SQL auth through saved profiles.

### 6.4 Retention
Metrics/validations/manifests: keep years (small). `diag_events`: 90-day default TTL via a scheduled cleanup job (manifest rows survive so the ledger stays coherent); `markers`/`sql_activity` (C5): 30 days. All TTLs are table-driven config, not hardcoded.

### 6.5 Operations
Schema versioning via `schema_info` + forward-only migrations shipped in perf-contracts; a `perftest central init` admin command creates/migrates the DB from the shipped DDL; store health view (`central_health`: row counts, last upload per kind, oldest event). Hosting: any internal SQL Server or Azure SQL DB — first deployment can be the existing team server; nothing in the design assumes more than one database.

---

## 7. Readers and analysis (C3/C4)

- **SQL first** — the team's habitat; Query Studio browsing the central store is the pleasant dogfood loop. Canned views ship with the schema: `official_metric_samples` (central twin of the local view), `latest_run_per_scenario_env`, `trend(scenario, metric, env_hash)` iTVF, `regressions_last_30d`, `sessions_by_feature_error_rate`, `fleet_by_build` (the cross-kind join: session error rates × run verdicts per product SHA).
- **In-product Perf History central provider** — `PerfSourceKind` gains `"central"`; the provider implements the existing abstraction with data-plane queries (paged; distinct empty/error/permission states per the C3 acceptance gate). This finally answers the "SQLite driver can't load in the extension host" problem with a real database the extension already knows how to query.
- **Grafana (C4)** — MSSQL data source pointed at the canned views; dashboard JSON checked into perftest. Zero ingestion pipeline. Alerts on `regressions_last_30d`.
- **Bencher / OTLP (C7)** — projections of the same ground truth (PR-comment UX; live tracing) if ever wanted; never systems of record.

---

## 8. Scenarios supported (explicit walkthroughs)

| # | Scenario | Flow | Components |
|---|---|---|---|
| S1 | Dogfooder shares a bad session | Debug Console → session → Upload → preview (team-default policy) → data-plane insert → ledger receipt; engineer queries `diag_events` by feature/type | C2, C0 store |
| S2 | Engineer shares local perf runs | Debug Console imported run → Upload (same action, `kind='perfRun'`) — or `perftest push` from the repo | C2 or C1 |
| S3 | Nightly CI trend | Scheduled workflow: gates → artifacts → push → `trend` view moves; Grafana panel updates | C1′, C1, C4 |
| S4 | PR perf gate with central history | PR workflow: gates (exit codes decide) → push tagged with PR context → reviewer opens trend link | C1′, C3/C4 |
| S5 | Stress/soak results | Same as S3 with stress scenario ids + bigger rep counts; retention absorbs volume | C1, §6.4 |
| S6 | "Did dogfooders hit what CI missed?" | `fleet_by_build` join: session error rates × run verdicts per SHA | C0 views |
| S7 | Support bundle handoff | Session uploaded under `elevated-support` policy after explicit gesture; artifact refs point at a fileshare/blob (heavy files never in rows) | C2, C6 |
| S8 | Delete my upload | `sp_purge_upload('diagSession', id)` — rows gone, ledger marks purge | §6.2 |
| S9 | Fresh-clone history backfill | `perftest push --all-new` re-projects every local run dir; idempotent against whatever already landed | C1 |
| S10 | Central store outage | CI gate unaffected (push is continue-on-error); Debug Console upload fails with a clean error + retry; local files remain ground truth | §1.2, §5.3 |

---

## 9. Build plan (keeps the C0–C7 ids from remaining_tasks §5.9)

| Batch | Deliverable | Files (primary) | Acceptance gate | Size |
|---|---|---|---|---|
| **C0** | Contract + schema freeze: mssql DDL + migrations + `schema_info`; projection DTOs/rules generated + vendored; upload-policy vocabulary; preview contract; fixture corpus + conformance/canary tests in BOTH repos; `centralStore.*` event family registered | perftest `packages/perf-contracts/sql/**`, `packages/observability-contracts` registry; vscode-mssql vendored TS | Fresh DB creates; fixtures project to golden rows in both repos; official-view parity vs local sqlite; canaries green | M |
| **C1** | `perftest push` Tier 1 + `central init` + exit code 7 + push observability | `packages/perftest-cli/src/central/**`, `commands/push.ts` | Push a fixture run to a container DB; re-push idempotent (`alreadyPresent`); digest-drift refusal; privacy canaries | M |
| **C1′** | CI workflow: gates → artifacts → push (non-blocking) → job summary; role-gated baselines | `.github/workflows/perf.yml` (perftest) | Green run on pinned agent; gate independent of push (kill the DB, gate still gates) | S |
| **C2** | Debug Console upload: preview UX + data-plane writer (sessions + imported runs) + ledger receipts + `mssql.centralStore.*` settings | vscode-mssql `src/diagnostics/centralUpload/**`, Debug Console webview | Bounded 100k-event upload; preview row-counts exactly match landed rows; policy drops visible; resume-after-cancel idempotent | M–L |
| **C3** | Central Perf History provider (`PerfSourceKind: "central"`), paged reads, distinct empty/error/permission states | vscode-mssql `src/diagnostics/perfHistory/centralProvider.ts` | Provider states honest (the §18-style ladder); trend parity vs CLI query on same data | M |
| **C4** | Grafana dashboards over canned views (dashboard JSON in-repo) + `central_health` | perftest `dashboards/**` | Useful panels with zero custom ingestion | S |
| **C5** | Tier 2/3 detail: markers + SQL-activity rows, retention jobs | contracts + both writers | Detail tables policy-safe (synthetic-DB rule enforced at projection); TTL job proven | M |
| **C6** | Support bundles + artifact refs + purge procedure ratified | contracts, C2 surface | Support workflow walkthrough (S7/S8) signed off | S–M |
| **C7** | Bencher/OTLP projections (optional) | perftest projections | Central store stable first | S each |

Sequencing: **C0 → C1 → C1′** can start immediately and independently of product work; **C2** follows C0 (it consumes the vendored contract) and is the first product-side batch; **C3/C4** once data exists. Standing rules as always: contracts-first vocabulary, full verify chain per batch, standing perf gates untouched, live integration tests against the same SQL Server container the harness already manages. Commit trains: perftest work unprefixed/`core:` as appropriate; vscode-mssql C2/C3 ride `core:` (vendored contract) + a new `dc:` train for Debug Console surfaces (or `qs:` if we prefer no new train — flagged below).

Test framework integration mirrors this session's pattern: unit suites over fixture projections in both repos; a PERF_MODE probe (`mssql.perf.centralUploadRoundTrip`) that uploads a fixture session to the container and reads it back through the central provider — the executable form of the C2+C3 acceptance gates; a perftest scenario wrapping it once the seam exists.

---

## 10. Decisions to ratify (review asks)

1. **One store, two writers, one vendored contract** (§0/§4) — confirm, or argue for CLI-only writing with the Debug Console shelling out to perftest (rejected here: dogfooders won't have the perftest repo; the data plane path is already proven and observable).
2. **Global natural-key uniqueness with ledger-recorded duplicate attempts** (§3.1) — confirm the "second uploader gets alreadyPresent" semantic.
3. **Digest-drift refusal** (§3.1): same runId + same schema version + different content ⇒ refuse loudly. Confirm (alternative: last-writer-wins, rejected as evidence-tampering-shaped).
4. **Identity policy** (§6.2): no anonymous uploads; alias + pseudonymized machine label allowed for dogfooders. Confirm.
5. **Retention defaults** (§6.4): 90d events / 30d markers / years for metrics. Numbers are placeholders to ratify.
6. **Roles** (§6.3): baseline writes CI-only from day one. Confirm.
7. **Train label for Debug Console central work**: new `dc:` train vs reuse. Preference?
8. **Hosting**: which server/DB the team store starts on (existing team SQL Server vs a new Azure SQL DB) — needed before C1′ secrets are wired.
9. Carried from the options doc: store = SQL Server owned by perf-contracts (both dialects); engineering-data-not-telemetry boundary; heavy artifacts stay file/blob refs. Re-confirm in this fuller context.

## 11. Risks / open questions

- **`diag_events` volume**: 100k-event sessions × enthusiastic dogfooders. Mitigations already in-design: TTL, promoted-column indexes, segment-streamed uploads, per-upload row caps in policy. Watch: whether `payload_json` needs compression (SQL 2025 JSON type / COMPRESS()).
- **Two-writer drift** is the design's main structural risk — the fixture corpus + conformance tests are the whole defense; they must be C0 acceptance, not an afterthought.
- **Auth friction for dogfooders** (SQL auth vs AAD on the team server) may shape how "one-click" C2 can be; resolve with decision 8.
- **Clock skew across machines**: fleet views should trust `uploaded_at_utc` + monotonic in-run/in-session times, never cross-machine epoch comparisons (the timing-class discipline already encodes this — carry it into view definitions).
- **Schema evolution while data exists**: forward-only migrations + `reprojected` re-push path (§3.1) is the recovery story; test a migration in C0's fixtures from day one.
