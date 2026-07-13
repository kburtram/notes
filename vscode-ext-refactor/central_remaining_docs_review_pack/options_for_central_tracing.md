# Central Observability Store and Upload Pipeline
## Centralizing perf runs, diagnostic sessions, CI trends, and support bundles without turning local evidence into product telemetry

**Status:** reviewed replacement, 2026-07-06.
**Target repos/branches:** `dev/query` across `vscode-mssql`, `sqltoolsservice`, and `perftest`.
**Primary decision:** build a SQL Server-backed central store first, with files remaining the source of truth and with all upload paths guarded by explicit upload policies.
**Companion inventory:** `remaining_tasks.md` tracks where this work sits in the larger Query Studio, STS2, MetadataStore, language service, Debug Console, Object Explorer v2, and perftest backlog.

---

## 0. Technical review of the draft

The draft is already pointed at the right target. It correctly identifies that the current system produces high-quality local evidence, not centralized telemetry; that upload should be opt-in engineering data, not a product telemetry channel; and that SQL Server is the most natural first central store because the local perftest projection is already relational and the extension already has a modern SQL Data Plane.

This replacement tightens the design in the places where future maintenance pressure will land.

1. **Rename the concept from central tracing to central observability.** The artifacts are not only traces. They include perf result contracts, local history indexes, diagnostic session journals, SQL activity, feature-capture traces, validation rows, baselines, comparisons, and support bundles. Traces are one useful shape, not the whole cauldron.
2. **Keep files as the authority, but make upload batches first-class.** The original schema used a simple `upload_ledger` with a uniqueness constraint by `(kind, natural_key, uploader_id)`. That is not enough for re-projection, partial upload, failed upload retry, schema migration, purge, or multiple upload attempts of the same run by CI and a developer. This document uses upload batches and upload items, while the canonical entities remain unique by natural key such as `run_id` or `session_id`.
3. **Do not use `MERGE` as the default ingestion primitive.** The first draft used `MERGE` as shorthand for idempotent upsert. A coding agent should instead build stored procedures with explicit transaction boundaries, staging tables, unique keys, and `UPDATE ... WITH (UPDLOCK, HOLDLOCK)` plus insert-if-missing, or use `MERGE` only behind tests that prove concurrency behavior. The goal is idempotence, not a particular SQL verb.
4. **Align upload policy names to the current diagnostic contracts.** The current product boundary has concrete `DataClassification` values such as `sql.text`, `row.data`, `secret`, `connection.string`, `token`, `model.prompt`, and metadata classes. Upload policy must consume those contract values directly, not invent a second vocabulary.
5. **Make in-product upload streaming, not in-memory.** The current `SessionStore` can query sessions by loading segments, which is fine for local viewing. Uploading large sessions should use a public streaming segment reader, validate the manifest first, and batch rows to SQL Server without loading a 100k event journal into one object graph.
6. **Add a central Perf History provider deliberately.** The current Perf History source model is file-oriented: directory, bundle, and an unsupported SQLite preview. A central provider is not just another path. It needs source contracts, paging, query semantics, and permission-aware errors.
7. **Separate central dashboards from CI gates.** Grafana and Bencher are useful presentation layers. The canonical CI gate remains the perftest regression engine and its official-metric rules. Dashboards should observe and explain; they should not become a second source of release truth.
8. **Close more of the “decisions to freeze.”** This design directly freezes schema ownership, the telemetry boundary, upload policy semantics, baseline ownership, support-bundle shape, retention, and heavy-artifact handling.

The recommendation remains: SQL Server first, CI artifact wiring in parallel, Grafana on top, Bencher and OTLP as projections later.

---

## 1. Existing local evidence, summarized

The central system projects these local artifact families. The local files remain authoritative and re-uploadable.

| Family | Current local source | Central role |
|---|---|---|
| Perf results | Per-rep `result.json`, `summary.json`, `environment.json`, `run-config.snapshot.jsonc`, `markers.jsonl`, `harness-log.jsonl`, run reports | Canonical perf run projection, trends, CI history, baseline comparison, artifacts index |
| Local perf store | `perf.db` with `runs`, `environments`, `scenarios`, `repetitions`, `metrics`, `validations`, `baselines`, `comparisons`, `official_metric_samples` | Starting point for SQL Server DDL and query views, not the upload source of truth |
| Diagnostic sessions | `sessions/<sessionId>/manifest.json` plus `events/segment-*.jsonl` | Session journal projection, support investigations, session error-rate dashboards |
| Debug Console exports | Redacted JSONL export | Manual support upload or bundle attachment, not the preferred structured ingestion path |
| Feature-capture traces | `mssql-copilot-trace-*.json`, `mssql-querystudio-run-*.json` | Excluded by default; explicit elevated policy only |
| SQL activity | `sql-activity.jsonl` plus rollup, diagnostic-only | Optional central SQL Activity detail and aggregate diagnostic metrics |
| Rich diagnostics | Heap, RSS, event-loop, CPU, traces, dumps | Mostly artifact refs, selected aggregate rows |
| CI outputs | Exit codes, `comparison.json`, run directories, job artifacts | CI ingestion and gate provenance |

Important facts the implementation should preserve:

- `runId`, `sessionId`, `environmentHash`, `eventId`, `seq`, `traceId`, git SHAs, and artifact hashes already give stable identity.
- Metric trust labels and timing classes ride with the data. Central views must preserve official versus diagnostic separation structurally.
- Diagnostic payload fields are classified before they reach sinks. Upload policy should filter those fields, not re-classify from raw values.
- The in-product Perf History abstraction currently indexes file sources. A central provider is a new provider kind with SQL-backed paging, not a magic local path.
- There is no upload or network sync code today. Centralization is greenfield, which is a luxury: do not smuggle it through an existing export command with unclear policy semantics.

---

## 2. Goals and non-goals

### 2.1 Goals

| ID | Goal |
|---|---|
| C-G1 | Centralize perftest run projections, diagnostic session journals, SQL activity summaries, validation rows, baselines, and comparisons in a SQL Server or Azure SQL database. |
| C-G2 | Keep local run/session files as the ground truth. Central rows are projections and may be rebuilt. |
| C-G3 | Provide two upload writers: CLI `perftest push` and in-product Debug Console upload. |
| C-G4 | Wire CI runs to publish results centrally after local gate evaluation. |
| C-G5 | Add a `central` Perf History source provider so the Debug Console can query shared history through the SQL Data Plane. |
| C-G6 | Enforce upload policy mechanically from data classifications and record the effective policy on every uploaded entity. |
| C-G7 | Preserve official-only CI gate semantics in central views. |
| C-G8 | Make uploads idempotent, replayable, partial-failure-safe, and auditable. |
| C-G9 | Provide SQL views and dashboard-ready projections for Grafana or similar tools. |
| C-G10 | Leave hooks for Bencher and OTLP projection without making either the system of record. |

### 2.2 Non-goals

- Do not build product telemetry.
- Do not stream live user data to a service.
- Do not upload SQL text, row data, prompts, model responses, connection strings, tokens, passwords, or raw server endpoints under the default policy.
- Do not replace local `result.json`, `markers.jsonl`, session manifests, or journal segments.
- Do not make Grafana, Bencher, Azure Monitor, or OTLP the canonical comparison engine.
- Do not require a native SQLite driver in the extension host.
- Do not support cross-company multi-tenancy in the first design. This is an internal engineering store with explicit upload.

---

## 3. Design principles

1. **Files remain ground truth.** Central rows are a projection. Any central entity should point back to the local file identity or content hash that produced it.
2. **Upload policy is a hard boundary.** The policy decides what may leave the machine. The writer cannot “helpfully” include a field because it looks useful.
3. **Trust labels are structural.** Official metrics must be queryable through official-only views. Diagnostic rows may exist, but they must not feed release gates by accident.
4. **Environment hash is the comparability wall.** Cross-environment trends are marked as exploratory unless a query explicitly opts into that comparison.
5. **Upload attempts are append-only.** The entity projection may be upserted, but every attempt is recorded in an upload batch ledger with status, row counts, policy, uploader, tool version, and errors.
6. **Heavy artifacts stay out of relational rows.** Large files are kept local or moved later to blob/file storage. The central store records hashes, sizes, classifications, and references.
7. **Central queryability starts small and honest.** The first schema should answer trends, regressions, session error rates, and run provenance. It should not pretend to be a full distributed tracing backend.
8. **Data-plane dogfood is a feature.** In-product upload and central readback should use the SQL Data Plane. The CLI may use the Node SQL Server driver because native ABI is not a VS Code extension-host problem there.

---

## 4. Recommendation

Build the **SQL Server central observability store** first.

| Option | Verdict | Why |
|---|---|---|
| SQL Server central store | **Primary** | Best match for normalized perf data, diagnostic sessions, team SQL workflows, Query Studio dogfood, and Grafana queryability. |
| CI artifacts only | **Do in parallel, not instead** | Fast path to PR and nightly evidence, but history remains trapped in zips without shared queryability. |
| Grafana over SQL Server | **Recommended layer** | Gives dashboards and alerts without a second ingestion pipeline. |
| Bencher | **Optional projection** | Useful PR-comment UX for official scalar metrics, but incomplete for sessions, markers, SQL activity, and support evidence. |
| OTLP/OTel | **Later adapter** | Good for live distributed tracing after STS2 observer contracts settle, but not a benchmark/run-comparison store. |

Implementation order:

1. Contracts and SQL Server DDL.
2. CLI `perftest push` Tier 1.
3. CI workflow that runs, gates, uploads artifacts, then pushes Tier 1 centrally.
4. In-product upload for diagnostic sessions and imported perf runs.
5. Central Perf History provider and Grafana dashboards.
6. Optional Bencher and OTLP projections.

---

## 5. Target architecture

```text
Local producers
  perftest CLI runs
  Debug Console session store
  in-product self-test runs
  feature-capture traces
  SQL activity collectors
        |
        | local files stay authoritative
        v
Upload writers
  perftest push
  Debug Console Upload to SQL Server
  CI publish step
        |
        | policy filter + manifest validation + batch ingestion
        v
Central SQL Server database
  contracts-owned schema
  upload batches and items
  perf projections
  diagnostic session projections
  artifacts and support-bundle refs
  official-only views
        |
        +---------------------------+
        |                           |
        v                           v
Readers                      Projections
  Query Studio SQL            Grafana dashboards
  Debug Console central source Bencher JSON
  direct SQL reports          OTLP adapter later
```

### 5.1 Module ownership

| Repo | Ownership |
|---|---|
| `perftest/packages/perf-contracts` | SQL Server schema, migrations, central views, schema version, generated contract metadata |
| `perftest/packages/perftest-cli` | `perftest push`, central-store validation, CI writer, optional Bencher projection |
| `vscode-mssql/extensions/mssql/src/diagnostics` | Upload policy preview, session segment reader, Debug Console upload command |
| `vscode-mssql/extensions/mssql/src/diagnostics/perfHistory` | Central Perf History provider and central source contracts |
| `vscode-mssql/extensions/mssql/src/services/sqlDataPlane` | In-product SQL connection/query path for central upload/readback |
| `sqltoolsservice/docs/sts2` | Future STS2 envelope export and OTLP adapter only after observer contracts settle |

### 5.2 Commit train guidance

Use small trains:

- `core:` observability contracts, schema, generated registry, diagnostics vocabulary.
- `perf:` perftest CLI push, CI workflow, Bencher projection.
- `dc:` Debug Console upload, Perf History central provider.
- `dp:` SQL Data Plane helper only if needed for batched inserts or central source connection.

---

## 6. Central database design

### 6.1 Schema ownership and versioning

The central DDL lives beside the local SQLite DDL:

```text
packages/perf-contracts/sql/perf-store.schema.sql
packages/perf-contracts/sql/perf-store.sqlserver.schema.sql
packages/perf-contracts/sql/migrations/sqlserver/V001__initial.sql
packages/perf-contracts/sql/migrations/sqlserver/V002__diag_sessions.sql
```

Every database has:

```sql
CREATE TABLE dbo.schema_info (
    schema_name NVARCHAR(128) NOT NULL PRIMARY KEY,
    schema_version INT NOT NULL,
    contracts_package_version NVARCHAR(64) NOT NULL,
    applied_utc DATETIME2(7) NOT NULL,
    applied_by NVARCHAR(256) NULL,
    source_commit NVARCHAR(64) NULL
);
```

Rules:

- Schema upgrades are forward-only migrations.
- Every writer checks `schema_info` before upload.
- An older writer refuses to write to a newer incompatible schema.
- A newer writer may re-project older local artifacts if artifact schema supports it.
- Views are versioned only when their contract changes. Dashboard-only view changes can be additive.

### 6.2 Upload ledger

Use two tables: one batch per upload attempt, many items per entity within that batch.

```sql
CREATE TABLE dbo.uploaders (
    uploader_id BIGINT IDENTITY PRIMARY KEY,
    uploader_key NVARCHAR(256) NOT NULL UNIQUE,
    display_name NVARCHAR(256) NULL,
    machine_label NVARCHAR(256) NULL,
    first_seen_utc DATETIME2(7) NOT NULL DEFAULT SYSUTCDATETIME(),
    last_seen_utc DATETIME2(7) NOT NULL DEFAULT SYSUTCDATETIME()
);

CREATE TABLE dbo.upload_batches (
    upload_batch_id BIGINT IDENTITY PRIMARY KEY,
    uploader_id BIGINT NOT NULL REFERENCES dbo.uploaders(uploader_id),
    uploaded_at_utc DATETIME2(7) NOT NULL DEFAULT SYSUTCDATETIME(),
    tool_name NVARCHAR(80) NOT NULL,
    tool_version NVARCHAR(80) NOT NULL,
    source_kind NVARCHAR(40) NOT NULL,      -- perftestCli | debugConsole | ci
    upload_policy_id NVARCHAR(128) NOT NULL,
    upload_policy_hash NVARCHAR(96) NOT NULL,
    status NVARCHAR(20) NOT NULL,           -- started | succeeded | partial | failed
    preview_hash NVARCHAR(96) NULL,
    row_counts_json NVARCHAR(MAX) NULL CHECK (row_counts_json IS NULL OR ISJSON(row_counts_json) = 1),
    errors_json NVARCHAR(MAX) NULL CHECK (errors_json IS NULL OR ISJSON(errors_json) = 1)
);

CREATE TABLE dbo.upload_items (
    upload_item_id BIGINT IDENTITY PRIMARY KEY,
    upload_batch_id BIGINT NOT NULL REFERENCES dbo.upload_batches(upload_batch_id),
    entity_kind NVARCHAR(40) NOT NULL,       -- perfRun | diagSession | featureTrace | supportBundle
    natural_key NVARCHAR(256) NOT NULL,
    local_schema_version NVARCHAR(80) NULL,
    content_hash NVARCHAR(96) NULL,
    projected_hash NVARCHAR(96) NULL,
    status NVARCHAR(20) NOT NULL,            -- inserted | updated | skipped | failed
    message NVARCHAR(1024) NULL,
    UNIQUE (upload_batch_id, entity_kind, natural_key)
);
```

Canonical entities are unique separately:

- `perf_runs.run_id` is unique.
- `diag_sessions.session_id` is unique.
- Feature traces use a trace file id or content hash.
- Support bundles use a bundle id and manifest hash.

The ledger records attempts. The entity tables record the latest accepted projection plus the projection hash that made it.

### 6.3 Perf projection

Port the local SQLite model to SQL Server with additive central columns:

```text
perf_runs
perf_run_repositories
perf_environments
perf_scenarios
perf_repetitions
perf_metrics
perf_artifacts
perf_validations
perf_baselines
perf_comparisons
perf_comparison_metrics
```

Required central additions:

| Table | Additions |
|---|---|
| `perf_runs` | `first_upload_batch_id`, `last_upload_batch_id`, `uploader_id`, `source_kind`, `run_config_hash`, `summary_hash`, `run_dir_hash`, `upload_policy_id` |
| `perf_environments` | stable `environment_hash`, pseudonymized machine fields, raw allowed fields by policy only |
| `perf_metrics` | eligibility flags, `timing_class`, source, derivation JSON, official gate flags |
| `perf_artifacts` | local relative path, kind, size, hash, classification, central ref nullable |
| `perf_baselines` | owner kind `ci | manual`, role-gated write marker, environment hash binding |
| `perf_comparisons` | comparison engine version, threshold JSON, result status, source run hashes |

Do not upload run directories wholesale into the database. The first central slice stores artifact references and selected hashes.

### 6.4 Diagnostic session projection

Mirror the current manifest and event contracts, with exact gap and policy data:

```sql
CREATE TABLE dbo.diag_sessions (
    session_id NVARCHAR(128) NOT NULL PRIMARY KEY,
    first_upload_batch_id BIGINT NOT NULL REFERENCES dbo.upload_batches(upload_batch_id),
    last_upload_batch_id BIGINT NOT NULL REFERENCES dbo.upload_batches(upload_batch_id),
    source NVARCHAR(40) NOT NULL,             -- live | perfRun | bundle
    capture_mode NVARCHAR(20) NOT NULL,
    policy_id NVARCHAR(128) NOT NULL,
    created_utc DATETIME2(7) NOT NULL,
    updated_utc DATETIME2(7) NULL,
    event_count INT NOT NULL,
    gap_count INT NOT NULL,
    size_bytes BIGINT NULL,
    status NVARCHAR(20) NOT NULL,
    provenance_json NVARCHAR(MAX) NOT NULL CHECK (ISJSON(provenance_json) = 1),
    dropped_ranges_json NVARCHAR(MAX) NULL CHECK (dropped_ranges_json IS NULL OR ISJSON(dropped_ranges_json) = 1),
    manifest_hash NVARCHAR(96) NOT NULL
);

CREATE TABLE dbo.diag_events (
    session_id NVARCHAR(128) NOT NULL REFERENCES dbo.diag_sessions(session_id),
    seq INT NOT NULL,
    event_id NVARCHAR(128) NOT NULL,
    epoch_ms BIGINT NOT NULL,
    monotonic_ns NVARCHAR(40) NULL,
    process NVARCHAR(40) NOT NULL,
    pid INT NULL,
    feature NVARCHAR(80) NOT NULL,
    kind NVARCHAR(40) NOT NULL,
    type NVARCHAR(160) NOT NULL,
    status NVARCHAR(40) NOT NULL,
    trace_id NVARCHAR(64) NULL,
    cause_event_id NVARCHAR(128) NULL,
    entity_kind NVARCHAR(80) NULL,
    entity_id_digest NVARCHAR(96) NULL,
    duration_ms FLOAT NULL,
    timing_class NVARCHAR(60) NULL,
    cls_max NVARCHAR(80) NOT NULL,
    policy_id NVARCHAR(128) NOT NULL,
    payload_json NVARCHAR(MAX) NULL CHECK (payload_json IS NULL OR ISJSON(payload_json) = 1),
    tags_json NVARCHAR(MAX) NULL CHECK (tags_json IS NULL OR ISJSON(tags_json) = 1),
    PRIMARY KEY (session_id, seq)
);
```

Notes:

- The current diagnostic event uses `eventId`, `traceId`, and `causeEventId`. Do not assume a separate `spanId` unless the contract adds it.
- `payload_json` contains only the post-policy classified fields that are allowed to leave the machine.
- `entity_id` should be omitted or digested by default. Use path and object-name classes only under a policy that permits them.
- Store exact dropped ranges from the manifest, not just a count.

### 6.5 Optional detail tables

These are Tier 2+ tables, not required for C1:

| Table | Purpose | Default upload |
|---|---|---|
| `perf_markers` | Central waterfall/detail over `markers.jsonl` | Off unless `--with-markers` |
| `perf_sql_activity` | SQL duration, CPU, reads, command count, no raw SQL text by default | Off unless diagnostic/calibration pass and policy allows |
| `feature_traces` | Feature capture manifests and redacted summaries | Off by default |
| `feature_trace_events` | Detailed feature capture payload rows | Explicit elevated policy only |
| `support_bundles` | Bundle manifest, hashes, and artifact refs | Manual upload only |
| `central_artifacts` | Blob/file refs for heavy artifacts | Later decision |

### 6.6 Canned views and table-valued functions

Ship views in the contracts package:

```text
v_official_metric_samples
v_latest_run_per_scenario_env
v_recent_regressions
v_run_health
v_session_error_rate_by_feature
v_session_slow_actions
v_ci_gate_inputs
v_upload_batch_summary
v_artifact_refs
```

`v_official_metric_samples` must be the central equivalent of the local official sample view. It should require:

- metric official or CI-gating eligible;
- pass type `measurement`;
- non-warmup repetition;
- passed repetition;
- matching environment hash when paired with a baseline;
- no diagnostic-only timing class.

Optional TVFs:

```sql
fn_metric_trend(@scenario_id NVARCHAR(160), @metric_name NVARCHAR(160), @environment_hash NVARCHAR(96), @last_n INT)
fn_recent_regressions(@since_utc DATETIME2(7))
fn_session_trace(@session_id NVARCHAR(128), @trace_id NVARCHAR(64))
fn_upload_preview(@upload_batch_id BIGINT)
```

---

## 7. Upload policy and privacy design

### 7.1 Policy object

Upload policy is a named, versioned object. It is not a UI-only setting.

```ts
export interface UploadPolicy {
    policyId: string;
    version: number;
    description: string;
    allowClassifications: readonly DataClassification[];
    digestOnlyClassifications: readonly DataClassification[];
    omitClassifications: readonly DataClassification[];
    allowFeatureTraceUpload: boolean;
    allowSqlActivityDetail: boolean;
    allowObjectNames: boolean;
    allowServerNames: boolean;
    allowSourcePaths: boolean;
    pseudonymizeMachine: boolean;
    maxDiagEventsPerSession?: number;
    maxPayloadBytesPerEvent?: number;
}
```

Default `team-default` policy:

| Classification | Handling |
|---|---|
| `public`, `system.metadata`, `diagnostic.metadata`, `result.shape` | Plain if already classified plain |
| `source.path`, `server.name`, `database.name`, `schema.name`, `object.name` | Digest by default, plain only under team-internal object-name policy |
| `sql.digest` | Plain digest value allowed |
| `sql.text`, `row.data`, `connection.string`, `token`, `secret` | Omit always under default policy; `secret` is never allowed under any policy |
| `user.text`, `model.prompt`, `model.response` | Omit by default; explicit elevated policy only |
| `unknown` | Omit |

### 7.2 Preview before upload

Every upload path first computes an `UploadPreview`:

```ts
export interface UploadPreview {
    kind: "perfRun" | "diagSession" | "featureTrace" | "supportBundle";
    naturalKey: string;
    policyId: string;
    policyHash: string;
    localSchemaVersion: string;
    rowCounts: Record<string, number>;
    omittedCountsByClassification: Record<string, number>;
    digestCountsByClassification: Record<string, number>;
    artifactRefs: Array<{ kind: string; sizeBytes?: number; classification: string; uploaded: boolean }>;
    warnings: string[];
    previewHash: string;
}
```

CLI prints the preview in JSON or a readable table. In-product upload shows it in the Debug Console and requires an explicit action.

### 7.3 Purge and retention

- Metrics and validations may be retained for years.
- Diagnostic events should default to a shorter TTL such as 90 days, while session manifests remain longer.
- Feature traces are short-retention by default.
- `purge_upload(entity_kind, natural_key)` marks or deletes rows according to store policy and records the purge in an audit table.
- Pseudonymization must be policy-driven, not an afterthought.

---

## 8. Writers

### 8.1 CLI: `perftest push`

Command shape:

```powershell
perftest push <runId|path|--all-new> `
  --target <profile|connstring|env:MSSQL_PERFTEST_CENTRAL_CONNSTRING> `
  [--policy team-default] `
  [--with-markers] `
  [--with-sql-activity] `
  [--dry-run] `
  [--json]
```

Rules:

- Read `result.json`, `summary.json`, and related artifacts from the run directory, not `perf.db`.
- Validate artifact schemas before upload.
- Compute content hashes and projection hashes.
- Start an `upload_batch` with status `started`.
- Stage rows into temporary tables or table-valued parameters.
- Execute stored procedures that upsert canonical entities in one transaction per run.
- Mark upload items inserted, updated, skipped, or failed.
- Mark the batch succeeded, partial, or failed.
- Exit code `7` means push failed. Do not overload infrastructure failure `5`.
- `--dry-run` computes preview and validates target schema without writing rows.

Upsert guidance:

- Prefer stored procedures over ad hoc SQL in the CLI.
- Use unique constraints and explicit transaction isolation.
- Avoid broad `MERGE` unless the implementation includes concurrency tests, duplicate-source tests, and stable row-count reporting.

### 8.2 In-product upload

Command surfaces:

```text
mssql.debugConsole.uploadSessionToSqlServer
mssql.debugConsole.uploadPerfRunToSqlServer
mssql.debugConsole.showUploadPreview
mssql.debugConsole.manageUploadPolicies
```

Implementation requirements:

- Use saved connection profiles and the SQL Data Plane, not a new extension-host SQL driver.
- Do not persist raw connection strings.
- Add a public streaming reader over diagnostic session segments so upload does not need to materialize all events at once.
- Run `SessionStore.validateStore()` or equivalent manifest validation before upload.
- Batch rows with JSON `OPENJSON`, TVPs if available through the data plane, or bounded parameter batches.
- Show exactly what leaves the machine.
- Upload under `applicationName: "vscode-mssql-observability-upload"` or equivalent.
- Never upload an active session without first freezing a safe manifest snapshot or marking it as partial with exact seq range.

### 8.3 CI writer

CI sequence:

1. Run `perftest doctor`.
2. Run configured measurement scenarios on a pinned self-hosted agent when stability matters.
3. Compute official gate locally.
4. Upload the run directory as a CI artifact regardless of central push result.
5. Run `perftest push` Tier 1.
6. Publish `comparison.json` and central upload URL or run id in the job summary.
7. Fail the job according to perftest exit codes, not according to dashboard ingestion.

CI baseline ownership:

- CI may write fleet baselines.
- Developer uploads may write runs and comparisons, but not silently move fleet baselines.
- Baseline writes require a role or token separate from ordinary upload.

---

## 9. Readers

### 9.1 Direct SQL and Query Studio

The central store should be pleasant to query directly. That is a feature, not a loophole. Provide a `docs/central-store/QUERY_COOKBOOK.md` with examples:

- latest regressions by scenario;
- trend for one official metric and environment hash;
- sessions with highest error rates by feature;
- runs where SQL activity got slower but official wallclock did not regress;
- upload failures by policy and tool version;
- comparisons by product commit.

### 9.2 Debug Console central Perf History provider

Extend source contracts:

```ts
export type PerfSourceKind = "directory" | "sqlite" | "bundle" | "central";

export interface CentralPerfHistorySource extends PerfHistorySource {
    kind: "central";
    connectionProfileId: string;
    database?: string;
    status: "indexed" | "scanning" | "partial" | "stale" | "error" | "empty" | "unsupported";
}
```

Provider behavior:

- `PhListSources` includes configured central sources without opening them unless status requires it.
- `PhQueryRuns`, `PhQueryScenarios`, `PhMetricSeries`, `PhScenarioDetails`, and `PhGetWaterfall` map to SQL views/TVFs.
- Heavy artifact tabs show refs and fetch only when a central artifact store exists.
- Permission errors are explicit. Empty is not permission denied.
- Central source can be read-only.
- Central provider should never download full sessions unless the user drills into a session trace.

### 9.3 Grafana

Use the Microsoft SQL Server data source pointed at views, not raw tables. Suggested dashboards:

- Suite health overview.
- Official metric trends by scenario and environment hash.
- Recent regressions.
- CI baseline drift.
- Session error rate by feature.
- Upload batch health.
- Top slow user actions or traces.

Grafana should not be the only way to inspect data. Every panel query should be checked into source as SQL.

### 9.4 Bencher and OTLP projections

- `perftest push --bencher` can project official scalar metrics after Tier 1 is stable.
- OTLP export can map markers and diag events to spans/metrics later, preferably from the same central rows or from STS2 envelope adapters.
- Neither projection becomes the canonical store.

---

## 10. Implementation plan

### C0: Contract and schema design freeze

Files:

```text
packages/perf-contracts/sql/perf-store.sqlserver.schema.sql
packages/perf-contracts/sql/migrations/sqlserver/**
packages/perf-contracts/src/centralStore.ts
packages/perf-contracts/schemas/upload-preview.schema.json
```

Work:

1. Add SQL Server schema and migration folder.
2. Add upload preview and upload manifest contracts.
3. Add central classification policy helpers.
4. Add canned views and minimal seed/test data.
5. Add schema validation tests.

Exit:

- Schema creates cleanly on SQL Server and Azure SQL target versions chosen by the team.
- Local fixtures validate.
- Official-only view matches local `official_metric_samples` semantics on sample data.

### C1: `perftest push` Tier 1

Files:

```text
packages/perftest-cli/src/central/**
packages/perftest-cli/src/commands/push.ts
packages/perftest-cli/src/exitCodes.ts
```

Work:

1. Add central connection config through env var and CLI argument.
2. Add dry-run preview.
3. Upload runs, environments, scenarios, repetitions, metrics, validations, artifact refs.
4. Record upload batches/items.
5. Add idempotency and partial failure tests.

Exit:

- Re-pushing the same run is safe and reports `skipped` or `updated` deterministically.
- Push failure does not corrupt canonical rows.
- Exit code `7` is documented and tested.

### C1-prime: CI artifact and central publish

Work:

1. Add GitHub Actions workflow for a pinned agent path.
2. Run gates and publish artifacts.
3. Push Tier 1 centrally when credentials are available.
4. Write job summary with local verdict and central run id.

Exit:

- CI gate remains authoritative if central upload fails.
- Central upload failure is visible and actionable.

### C2: In-product upload preview and writer

Files:

```text
extensions/mssql/src/diagnostics/upload/**
extensions/mssql/src/diagnostics/sessionStore.ts
extensions/mssql/src/controllers/debugConsoleWebviewController.ts
extensions/mssql/src/webviews/pages/DebugConsole/**
```

Work:

1. Add streaming segment reader and manifest validator.
2. Add upload policy preview.
3. Add Debug Console commands and UI.
4. Upload diagnostic sessions and imported perf runs through the SQL Data Plane.
5. Add privacy canary tests.

Exit:

- User sees row counts and omitted classification counts before upload.
- Default policy uploads no SQL text, row data, secrets, connection strings, tokens, prompts, or model responses.
- 100k event journal upload stays bounded in memory.

### C3: Central Perf History source

Work:

1. Add `PerfSourceKind: "central"`.
2. Add central provider with SQL-backed queries.
3. Add source management UI.
4. Support runs, scenarios, trends, details, and limited waterfalls from central rows.

Exit:

- Debug Console can browse central history without SQLite driver support.
- Empty, error, unsupported, and permission-denied states are distinct.

### C4: Grafana dashboards and SQL cookbook

Work:

1. Check in panel SQL.
2. Provide dashboard JSON or deployment notes.
3. Add queries for regressions, trends, upload health, and session errors.

Exit:

- A developer can point Grafana at the store and see useful dashboards without custom ingestion.

### C5: Tier 2 details

Work:

1. Add optional marker upload.
2. Add SQL activity detail upload.
3. Add central waterfall query support.
4. Add retention jobs for high-volume tables.

Exit:

- Diagnostic data remains visibly diagnostic.
- Retention can be configured and tested.

### C6: Support bundles and artifact refs

Work:

1. Define support bundle manifest and signature/hash rules.
2. Add central refs for blob/file storage if chosen.
3. Add purge workflow.

Exit:

- A support engineer can answer what evidence exists, where it is, what policy produced it, and what was intentionally omitted.

### C7: Bencher and OTLP projections

Work:

1. Add `--bencher` projection from official samples.
2. Add OTLP adapter only after STS2 observer/export contracts settle.

Exit:

- Projection failures do not affect canonical central store rows.

---

## 11. Testing and acceptance gates

| Area | Required tests |
|---|---|
| Schema | create/drop, migrations, view correctness, official-only parity with SQLite fixtures |
| Upload preview | classification omission/digest counts, policy hash stability, no raw secrets |
| CLI push | idempotency, partial failure, retry, invalid schema, old writer/new schema, dry-run |
| In-product upload | streaming memory bound, manifest validation, active-session partial snapshot, data-plane failure |
| Central provider | paging, filters, permission-denied, empty source, missing artifacts, trend parity |
| CI | local gate wins over central upload status, artifact upload always happens, exit codes preserved |
| Privacy | canaries for password, token, connection string, SQL text, row data, prompt, response, server/user names |
| Retention | TTL cleanup, protected baselines, purge audit |

Definition of done for C1:

- A perftest run can be pushed to a fresh central database.
- `v_official_metric_samples` has the same samples as local official views for fixture runs.
- Re-push is idempotent.
- Upload ledger shows the attempt and row counts.
- No default-policy canary value appears in central rows.

Definition of done for C3:

- The Debug Console can add a central source and query runs/scenarios/trends from it.
- It does not require a local SQLite driver.
- Permission errors and empty data are distinct.
- All queries are bounded and paged.

---

## 12. Open decisions to ratify

This design asks Karl or the team to ratify these decisions:

1. Central store is SQL Server or Azure SQL.
2. Central data is opt-in engineering/support data, not product telemetry.
3. `perf-contracts` owns SQL Server schema and migrations.
4. Upload policies are named, versioned, recorded on every upload, and enforce the current classification vocabulary.
5. CI writes fleet baselines. Developer uploads do not move fleet baselines unless explicitly authorized.
6. Heavy artifacts stay out of relational tables in the first slice.
7. Diagnostic events have default TTL; manifests and perf metrics have longer retention.
8. Feature-capture traces are excluded by default.
9. Central provider uses the SQL Data Plane in-product; CLI may use the Node SQL Server driver.
10. Bencher and OTLP are projections, not the store of record.

---

## 13. Coding-agent starting point

A coding agent can start with C0 and C1 without touching product UI.

1. Add SQL Server schema and contract types under `perf-contracts`.
2. Add a central-store fixture and tests that prove official-only parity.
3. Implement `perftest push --dry-run`.
4. Implement Tier 1 upload through stored procedures.
5. Add idempotency and privacy canary tests.
6. Add C1-prime CI workflow after push works locally.

Do not start with Grafana. Do not start with in-product upload. The store contract and CLI writer are the foundation stones; dashboard glitter belongs after the floor stops moving.
