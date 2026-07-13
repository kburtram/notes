# Options for Centralizing Perf & Diagnostic Results
## From per-machine artifacts to shared analysis: SQL Server upload, CI/CD aggregation, and off-the-shelf tooling

**Status:** options analysis, written 2026-07-05 against the current `dev/query` implementation (perftest + vscode-mssql diagnostics).
**Prompted by:** the "central/fleet aggregation, Bencher push, shared dashboards" seam that `perftest/IMPLEMENTATION_PLAN.md` deliberately deferred ("seams preserved, decide with user later"). This is that decision document.

---

## 0. Executive summary

Everything we produce today is **local files with excellent provenance**: schema-versioned JSON/JSONL artifacts, a normalized SQLite projection (`perf.db`), environment hashes, per-repo git SHAs, W3C trace ids, and a governed classification vocabulary that already decides what is allowed to leave a field unredacted. There is **no upload or network code anywhere** — centralization is greenfield, and the existing seams make it cheap.

**Recommendation (detailed in §9):** build the **SQL Server central store first** (Option A) — it is the lowest-friction path (the relational model already exists as `perf-store.schema.sql`; the extension already knows how to talk to SQL Server through its own data plane; the team already lives in SQL tools), it serves both perf runs *and* diagnostic session journals, and every other option can be layered on top of it later (Grafana reads SQL Server directly; a Bencher push is a projection of the same `result.json` ground truth). Ship it in three phases: CLI `perftest push` → in-product "Upload to SQL Server" → Grafana dashboards over the central DB. Treat OTLP export and Bencher as optional adjuncts, not foundations.

---

## 1. What exists today (the data being centralized)

Ground truth is per-rep `result.json` (schema v2) under `perf-runs/<runId>/scenarios/<id>/reps/rep-NN/`, plus these distinct artifact families (full inventory in the table at the end of this section):

- **Perf runs (harness):** `PerfResult` v2 (metrics with `MetricEligibility` — the official/diagnostic/exploratory trust labels — plus validations, errors, artifact refs, `TraceInfo` with W3C `traceId`/`traceparent`), `markers.jsonl` (`Marker` v1, epoch-ns + monotonic-ns), `environment.json` (`EnvironmentInfo` with canonical-JSON sha256 **environment hash**), `summary.json`, `run-config.snapshot.jsonc`, `harness-log.jsonl`, per-run static HTML reports (`index.html`), and cross-run reports (`history.html`, `trend-*.html`, `head-to-head-*.html`).
- **SQLite aggregate (`perftest/perf.db`):** already a clean relational model — `runs`, `run_repositories`, `environments`, `scenarios`, `repetitions`, `metrics`, `artifacts`, `validations`, `baselines`, `comparisons`, `comparison_metrics`, view `official_metric_samples`. Canonical DDL: `packages/perf-contracts/sql/perf-store.schema.sql`. Written by `packages/perftest-cli/src/store/sqliteStore.ts` (`PerfStore`). **`StoreConfig.type` already reserves `"postgres"` as a store kind with no implementation — this is the declared centralization seam.**
- **Diagnostic sessions (product):** `DiagEvent` v1 (`mssql.diag.event/1`, every payload field a `ClassifiedValue {v?, cls, handling, digest?}` with a policy id) persisted by `SessionDiagSink` as `sessions/<sessionId>/manifest.json` + `events/segment-*.jsonl` (5000 events/segment); `SessionManifest` v1 carries `source: "live"|"perfRun"|"bundle"`, capture mode, policy id, gap accounting, and a `ProvenanceSummary` (extension version/commit/dirty/env-hash/machine label). Debug Console can export a redacted `mssql-diag-<ISO>.jsonl`.
- **Feature-capture traces:** `FeatureTraceEnvelope` v1 (versioned, size-capped, key-driven redaction): `mssql-copilot-trace-*.json`, `mssql-querystudio-run-*.json`. These may carry elevated content (prompts, SQL under explicit policy) and are the most privacy-sensitive artifact family.
- **SQL activity:** XEvents ring-buffer shredded to `sql-activity.jsonl` + rollup per rep, normalized to `sqlserver.*` metrics (diagnostic-only today).
- **The registry:** `@mssqlperf/observability-contracts` — event vocabulary (~69 entries), classification taxonomy (`secret`…`safeEnum`), timing classes, and `deriveEligibility()`, the single shared official/diagnostic decision. **Classification decides what is permitted; settings only request.** This is the enforcement mechanism any upload boundary should reuse.
- **CI hooks that exist but are unwired:** documented exit-code contract (`exitCodes.ts`: 0 ok / 1 regression / 2 configInvalid / 3 preflight / 4 scenarioFailed / 5 infrastructure / 6 insufficientSamples). No GitHub Actions workflow invokes perftest today.
- **Two parallel history mechanisms to reconcile:** perftest's `perf.db` (authoritative, CLI-side) and the product's directory-scan `.dc-history-index.json` (`DirectoryHistoryProvider`), which exists because a native SQLite driver can't load in the extension host. The in-product Perf History already has a **provider abstraction** (`PerfHistoryProvider`-style: directory / sqlite-stub / bundle / session) — a central source slots in as one more provider kind.

Key structural facts that make centralization easy:
1. **Idempotency keys exist**: `runId` (timestamp+hash), `sessionId`, `environment_hash`, `eventId`/`seq` — safe upsert semantics for sync.
2. **Comparability keying exists**: metric × scenario × environment_hash × product SHA is exactly what `trendSeries()` uses locally; any central store keeps the same keys.
3. **Trust labels ride the data**: `MetricEligibility` and `DiagTimingClass` mean a central store can enforce "gates read official only" mechanically.
4. **Privacy is field-granular**: every diag field is classified at emit; upload can filter by classification + policy id rather than inventing a second redaction pass.

---

## 2. Use cases to serve

| ID | Use case | Data involved | Consumers |
|---|---|---|---|
| U1 | **Team/dogfood upload** — "everyone on the team or internal dogfooders can upload files for shared analysis"; sync local perf runs + usage-session diag journals to a shared DB | run summaries/metrics/validations/markers; session manifests + DiagEvents; optionally feature traces | engineers via SQL/Query Studio, shared dashboards |
| U2 | **CI/CD perf runs** — scheduled + PR-triggered perftest runs publish results centrally; gates ride exit codes; trends across machines/agents | full run projection + baselines/comparisons | CI gate, nightly trend review |
| U3 | **Off-the-shelf analysis** — Grafana (or similar) dashboards; possibly Bencher-style continuous benchmarking UI | official metric samples keyed by scenario × env × commit; optionally spans | dashboards, alerts, PR comments |
| U4 | **Support/incident sharing** — a user or dogfooder hands over a coherent, redacted evidence bundle | session journal + linked perf artifacts | engineer doing the investigation |

Non-goals for the first slice: public telemetry (this is an *opt-in engineering* store, not product telemetry — the telemetry boundary is one of the recorded "decisions to freeze"), cross-company multi-tenancy, and real-time streaming ingestion.

---

## 3. Design principles (apply to every option)

1. **Files remain ground truth.** The central store is a *projection* for querying and sharing; `result.json`/journal segments stay authoritative and re-uploadable. Never mutate centrally; re-push is idempotent upsert by natural key.
2. **The upload boundary enforces classification.** Only fields whose `DataClassification` is permitted by the *upload policy* leave the machine; the effective policy id is recorded on every uploaded row. Secrets never upload under any policy (same "settings request, classification decides" rule as capture). Feature traces (prompts/SQL) upload only under an explicit elevated policy, and default to excluded.
3. **Official/diagnostic separation survives centrally.** Gate queries and dashboards read `measurement`+`official` samples only (the central equivalent of the `official_metric_samples` view); diagnostic/exploratory data is present but visibly second-class.
4. **Environment hash is the comparability wall.** Central trend/gate queries group by `environment_hash`; cross-env comparison requires the same explicit override the CLI has.
5. **Provenance or it didn't happen.** Every uploaded run/session carries machine label, uploader identity, git SHAs + dirty flags, schema versions, capture/upload policy ids, and upload timestamp — in an append-only upload ledger.
6. **Heavy artifacts don't go in the relational store.** Metrics/markers/validations/events are rows; VS Code logs, profiles, crash dumps, HTML reports are files — keep them local or in blob storage with `artifacts` rows as refs.

---

## 4. Option A — SQL Server central store ("Upload to SQL Server")

The primary proposal, in three parts: schema, writers, readers.

### 4.1 Schema

Translate `perf-store.schema.sql` to SQL Server DDL — it is already normalized and proven by the local store. Mechanical changes: `INTEGER PRIMARY KEY AUTOINCREMENT` → `BIGINT IDENTITY`, `PRAGMA`/WAL removed, `TEXT` → `NVARCHAR(...)`/`NVARCHAR(MAX)`, JSON columns (`tags_json`, `derivation_json`, `config_fingerprint_json`) stay `NVARCHAR(MAX)` with `ISJSON` checks (or native `json` type on SQL 2025+). Additions for multi-user centrality:

```sql
-- new dimensions
CREATE TABLE uploaders (uploader_id, display_name, machine_label, first_seen_utc, ...);
CREATE TABLE upload_ledger (
    upload_id BIGINT IDENTITY PRIMARY KEY,
    uploader_id, uploaded_at_utc, tool_version,
    kind NVARCHAR(20) NOT NULL,           -- 'perfRun' | 'diagSession' | 'featureTrace'
    natural_key NVARCHAR(200) NOT NULL,   -- runId / sessionId / trace file id
    upload_policy_id NVARCHAR(100) NOT NULL,
    row_counts NVARCHAR(MAX),             -- JSON: what landed
    UNIQUE (kind, natural_key, uploader_id)  -- idempotent re-push = upsert
);
-- perf side: runs/environments/scenarios/repetitions/metrics/artifacts/validations/
-- baselines/comparisons/comparison_metrics as today, PLUS uploader_id on runs
-- and UNIQUE(run_id) so two people can't collide (runId already embeds a hash).

-- diag side (new; mirrors SessionManifest + DiagEvent):
CREATE TABLE diag_sessions (session_id PK, uploader_id, source, capture_mode, policy_id,
    created_utc, event_count, gap_count, provenance_json, status);
CREATE TABLE diag_events (session_id, seq, event_id, epoch_ms, monotonic_ns,
    process, pid, feature, kind, type, status, trace_id, cause_event_id,
    duration_ms, timing_class, cls_max, payload_json,   -- classification-filtered at upload
    PRIMARY KEY (session_id, seq));
-- markers (optional tier): per-rep marker rows for central waterfalls.
CREATE TABLE markers (run_id, rep_id, scenario_id, name, phase, correlation_id,
    timestamp_unix_ns, monotonic_ns, process_role, process_pid, attrs_json, ...);
```

Baselines/comparisons: central baselines become *named, env-hash-bound* rows exactly like local ones; CI owns writing them (a dev machine should not silently move the fleet baseline — make baseline writes role-gated).

### 4.2 Writers

**(a) `perftest push [runId|--all-new] --target <profile|connstring>`** (CLI, U2 + U1-perf):
- Reads `result.json` files (ground truth), not `perf.db`, so a fresh clone can push history.
- Tiered payload: Tier 1 (default) = runs/environments/scenarios/repetitions/metrics/validations/artifact *refs*; Tier 2 (`--with-markers`) = marker rows; Tier 3 (`--with-sql-activity`) = SQL activity rows (diagnostic passes only, and only when the run itself was allowed to capture SQL text — the synthetic-DB rule carries over).
- Connection via `MSSQL_PERFTEST_CENTRAL_CONNSTRING` env var or CLI arg; never persisted raw; mssql Node driver (tedious) — no native-ABI problem in the CLI.
- Idempotent: `MERGE`/upsert on natural keys; re-push after a schema-version bump re-projects.
- Exit codes extend the existing contract (a new `7 pushFailed` rather than overloading 5).

**(b) In-product "Upload to SQL Server"** (U1-sessions + U1-runs, Debug Console):
- Command + Debug Console action on a session (`Session Diag` store) or an imported perf run: pick a saved connection profile, preview *exactly what leaves the machine* (row counts per table + effective upload policy + any fields dropped by classification), then upload.
- **Uses the extension's own SQL data plane** (`ISqlConnectionService.openSession` with `applicationName: "vscode-mssql-diagupload"`, `commandKind: "metadata"`-class background priority). This is the elegant part: the product already has a first-class, tested SQL Server access path with passwordProvider-closure secrecy — no new driver, no native module, and it dogfoods the data plane. Batched parameterized inserts (TVPs or JSON `OPENJSON` bulk insert) keep it efficient for 100k-event journals.
- Reuses `perfRunImport.ts`'s reading of run dirs and the session store's segment reader; upload policy plugs into the existing `CAPTURE_POLICIES`/classification machinery — an `UploadPolicy` is just a capture policy applied at the exfiltration boundary plus an allowlist of classifications.

### 4.3 Readers

- **SQL directly** — the team's native habitat, and Query Studio itself browses the central DB (pleasant dogfood loop).
- **In-product Perf History central provider** — a new `PerfSourceKind: "central"` provider implementing the existing provider abstraction with data-plane queries. This *also* dissolves the long-standing "SQLite native driver can't load in the extension host" problem for shared history: the central store, not a local sqlite file, becomes the queryable multi-run source in-product.
- **Grafana on top** (see Option B′): Grafana's built-in Microsoft SQL Server data source pointed at `official_metric_samples`-equivalent views. Zero ingestion work — dashboards are `SELECT` statements.
- Canned views to ship with the schema: `official_metric_samples`, `latest_run_per_scenario_env`, `trend(scenario, metric, env)` TVF, `regressions_last_30d`, `sessions_by_feature_error_rate`.

### 4.4 Assessment

| | |
|---|---|
| **Strengths** | Serves all four use cases with one system; schema already exists; both writers reuse proven code paths (CLI store writer, product data plane); readable by every off-the-shelf SQL tool including Grafana; classification enforcement is a filter, not a new system; self-hostable on any internal SQL Server/Azure SQL DB. |
| **Weaknesses** | We own schema migrations and retention jobs; no out-of-the-box benchmark UI (we bring our own via existing HTML reports + Grafana); blob-artifact story (Tier 2+ heavy files) needs a later decision (fileshare/blob container + `artifacts.central_ref`). |
| **Cost** | Schema translation + `perftest push`: small (the store writer is ~1 file). In-product upload with policy preview: moderate (UX + policy). Central provider read side: moderate. |

---

## 5. Option B — OTel/OTLP export → Grafana stack (Tempo/Mimir/Loki) or Azure Monitor

Every rep already has W3C `traceId`/`traceparent` (injected into env as `PERF_TRACEPARENT`), DiagEvents carry `traceId`/`spanId`, and "Envelope→OTel adapter + OTLP export" is a preserved-but-unbuilt seam on the STS side (`STS_INSTRUMENTATION.md`). So a faithful OTLP emitter is feasible: markers/spans → OTel spans, official metrics → OTel metrics with `eligibility` attributes, DiagEvents → span events/logs.

| | |
|---|---|
| **Strengths** | Industry-standard; live fleet observability; Tempo/Jaeger waterfalls for free; language-agnostic (STS C# side can join later with the same traceparent); Azure Monitor variant needs no self-hosted infra. |
| **Weaknesses** | **Wrong shape for the core job.** Our center of gravity is *benchmark comparison with provenance and trust labels* (baselines, env-hash walls, Welch t-tests, official-only gates) — OTel backends are retention-limited time-series/trace stores, not run-comparison stores; baselines/verdicts would still need a database. Diag session journals (policy ids, gap accounting, classification) don't round-trip. Adds infra to run (collector + Tempo/Mimir) for less capability than SQL over Option A's store. |
| **Verdict** | Not the foundation. Worth doing *later* as an adapter (the seam is already reserved) if live distributed tracing across extension⇄STS⇄SQL becomes a priority — and it composes fine with Option A (same trace ids in both). |

**Option B′ (recommended sliver):** skip OTLP, keep Grafana — point Grafana's MSSQL data source at the Option A store. All the dashboard/alerting value, none of the pipeline.

---

## 6. Option C — Bencher (or similar continuous-benchmarking service)

Bencher's model — metric × branch × **testbed** × threshold with PR comments and self-hosted option — maps cleanly onto ours: testbed ≈ `environment_hash` (or a friendlier machine-class label derived from it), branch/commit come from `git[]`, and `bencher run` accepts custom-adapter JSON, which is a trivial projection of `result.json` official samples.

| | |
|---|---|
| **Strengths** | PR-gate UX (comments, thresholds, trend charts) without building any UI; statistical thresholds built in; self-hostable. |
| **Weaknesses** | Official scalar metrics only — no markers/waterfalls/SQL activity/diag sessions/validations; duplicate thresholding logic (ours in `regression.ts` is more tailored: eligibility, CV guards, env walls); another system of record to reconcile; team data would live outside SQL. |
| **Verdict** | Optional adjunct for U3/U2 *presentation*, driven from the same `result.json` ground truth (`perftest push --bencher` later). Do not make it the store. Our own gate (exit codes + `comparisons` table) remains authoritative. |

---

## 7. Option D — CI-artifact minimalism (no shared store)

Wire perftest into GitHub Actions now: run gates on a pinned self-hosted agent (env-hash stability demands self-hosted), upload the run directory as a build artifact, render `report.md` into the job summary, fail the job on exit codes 1/4/5, and keep a rolling baseline via `baseline set` on the agent's local `perf.db`.

| | |
|---|---|
| **Strengths** | Days, not weeks; zero new services; uses the documented exit-code contract that is currently unwired. |
| **Weaknesses** | No cross-run/cross-machine queryability, no team upload, no dogfood sessions; history trapped in artifact zips. |
| **Verdict** | Not an alternative — it's **step one of U2 regardless of store choice**, and it should happen alongside Option A phase C1. |

---

## 8. Cross-cutting design: privacy, identity, retention

- **Upload policy is a named, versioned object** (like capture policies): `uploadPolicy: "team-default"` allows `diagnosticMetric|safeEnum|structuralMetadata` values, digests for `identifierSensitive`, drops `userSql|resultData|providerText`, refuses `secret` always. Elevated policies exist but require the same explicit gesture as elevated capture, and the policy id lands on every row (`upload_ledger.upload_policy_id`, `diag_sessions.policy_id`).
- **Identity**: uploader = domain identity or a stable self-chosen label + machine label (already in `ProvenanceSummary`). No anonymous uploads to the team store; the ledger is the audit trail. A `purge(kind, natural_key)` admin procedure honors "delete my upload."
- **Server endpoints / machine names**: `EnvironmentInfo` includes hostname as `machineId` — acceptable for an internal team store, but make the pseudonymize toggle part of the upload policy for dogfooders outside the immediate team.
- **Retention**: metrics/validations rows are small — keep years. `diag_events` is the growth risk (100k+ rows/session): default TTL (e.g. 90 days) via a cleanup job, manifests kept forever.
- **Schema ownership + versioning**: the central DDL should live next to `perf-store.schema.sql` in `perf-contracts` and version with it (`schema_info` table + migration scripts). This resolves one of the ten "decisions to freeze" (schema ownership) concretely: contracts package owns both dialects.

---

## 9. Recommendation and phasing

**Primary: Option A (SQL Server central store), with Option D wired in parallel and Grafana as B′ on top.**

| Phase | Deliverable | Serves | Size |
|---|---|---|---|
| **C1** | `perf-contracts` SQL Server DDL + `perftest push` (Tier 1: runs/env/scenarios/reps/metrics/validations/artifact-refs; idempotent; env-var connstring) + canned views | U2, U1-perf | S–M |
| **C1′** (parallel) | GitHub Actions workflow on a pinned agent: run gates → exit-code gate → artifact upload → `perftest push` to central | U2 | S |
| **C2** | In-product **Upload to SQL Server**: Debug Console action for diag sessions + imported runs, over the extension's own data plane, with what-leaves-the-machine preview + upload policies; `upload_ledger` | U1, U4 | M |
| **C3** | Central read side: Perf History `central` source provider (data-plane queries) + Grafana MSSQL dashboards (trend, suite health, regressions, session error rates) | U1, U3 | M |
| **C4** (optional) | `--bencher` projection for PR-comment UX; OTLP adapter if live distributed tracing is wanted (seam already reserved) | U3 | S each |

Rationale in one line each:
- SQL Server first because the schema, the client code paths, and the team's query habits all already exist — it's the only option that serves perf runs *and* diagnostic sessions in one system.
- CI wiring is independent of store choice and overdue (contract exists, unwired) — do it immediately.
- Grafana over the SQL store gives U3 without an ingestion pipeline; Bencher/OTLP stay projections, never systems of record.
- The in-product upload doubles as a data-plane dogfood and finally gives the "SQLite can't load in the extension host" problem a better answer than a local driver: shared history lives in a real database the extension already knows how to query.

**Decisions this doc asks Karl to ratify** (they close 4 of the 10 open "decisions to freeze"):
1. Central store = SQL Server; schema owned/versioned by `perf-contracts` (both dialects).
2. Upload is opt-in engineering data, distinct from product telemetry; named upload policies with ledger + purge.
3. CI baselines are role-gated (CI writes fleet baselines; dev pushes are runs only).
4. Heavy artifacts stay file-based (local or blob ref) — rows for anything queryable, refs for everything else.
