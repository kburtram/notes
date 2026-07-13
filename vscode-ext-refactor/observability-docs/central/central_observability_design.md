# Central Observability - Design of Related Systems and Build Plan
## One shared SQL Server store for ad-hoc Debug Console uploads and official `perftest push` results

**Status:** reviewed drop-in replacement, 2026-07-06.  
**Supersedes/extends:** `options_for_central_tracing.md`. The options document chose SQL Server as the foundation; this document turns that option into an executable system design and task plan.  
**Related artifacts:** `CENTRAL_OBSERVABILITY_VISUALS.tex` (updated companion diagrams).  
**Code basis:** `vscode-mssql` and `perftest` `dev/query` branches as described in the supplied design references. When the branch and this document disagree, the branch wins for code truth and this document should be updated.

---

## 0. Executive summary

Build **one central SQL Server observability store** with **two writer lanes** and **one shared contract**.

1. **Ad-hoc team and dogfood uploads**: the Debug Console uploads local diagnostic sessions and locally imported perf runs through the extension's own SQL Data Plane. The user sees an exact preview of what will leave the machine before upload.
2. **Official CI and perf fleet results**: `perftest push` publishes perf and stress runs from the CLI after the local gate runs. The central push must never decide whether CI passes; the existing exit-code gate remains local and authoritative.

The core choice from the options document is preserved: centralization is a queryable SQL Server projection, not a replacement for local files. Run directories and diagnostic session journals remain the source of truth. The central store provides shared analysis, trend history, dashboards, and investigation joins.

The main review correction is that the store should not be modeled as a single `upload_ledger` table that writers mutate directly. The safer design is an **ingest entity plus upload batch spine**:

```text
source artifact files
  -> contract projection and privacy policy
  -> upload batch + upload items
  -> idempotent stored-procedure ingestion
  -> current entity rows and kind-specific detail tables
  -> append-only ledger and health/read views
```

This gives us partial-failure accounting, retry/resume, exact projection hashes, policy evidence, and least-privilege database roles without turning every writer into a bespoke SQL mini-engine.

---

## 0.1 Technical review: what changed from the draft

The draft's direction is strong. It correctly chooses one SQL Server store, keeps local files as ground truth, splits CLI and product writers, uses the SQL Data Plane for product uploads, keeps Grafana/Bencher/OTLP as readers or projections rather than foundations, and makes fixture parity the anti-drift mechanism.

This replacement tightens the design in eight areas.

| Area | Review finding | Incorporated update |
|---|---|---|
| Ingest model | A single append-only ledger is not enough to represent started, partial, committed, duplicate, reprojected, refused, and purged uploads. | Added `upload_batches`, `upload_items`, `central_entities`, and append-only ledger events. |
| Writer permissions | Granting writers broad table INSERT/UPDATE is easy but brittle. | Writers execute versioned stored procedures. Tables stay write-protected. |
| Upsert semantics | `MERGE` is tempting but harder to reason about for concurrency, auditing, and idempotent refusal rules. | Default to stored-proc upserts using transactions, uniqueness constraints, `UPDLOCK`/`HOLDLOCK`, or `sp_getapplock` per entity key. `MERGE` is allowed only with a reviewed proof. |
| Privacy taxonomy | The draft used older shorthand classes such as `safeEnum` and `identifierSensitive`. Current product contracts use concrete `DataClassification` values. | Added an explicit upload-policy matrix over `public`, `system.metadata`, `diagnostic.metadata`, `source.path`, `server.name`, `database.name`, `schema.name`, `object.name`, `sql.text`, `row.data`, `secret`, `connection.string`, `token`, `model.prompt`, `model.response`, and `unknown`. |
| Preview contract | Preview row counts were described but not made a first-class dry-run projection artifact. | `UploadPreview` is now a signed dry-run of the exact projection that will be uploaded, including omitted/digested counts and source/artifact digests. |
| Schema evolution | Reprojection needs a durable projector version and a way to tell legitimate re-projection from evidence mutation. | Added `contract_version`, `projector_version`, `source_schema_version`, `content_digest`, and `projection_digest`. |
| Read performance | `diag_events` volume is the growth risk. | Added index, retention, partitioning/windowing, payload-size caps, and payload compression guidance. |
| Build plan | C0 was a large bundle. | Split C0 into concrete sub-deliverables that a coding agent can execute without spelunking through prose. |

The design also adds a clear rule of thumb: **central observability is engineering evidence, not product telemetry**. Uploads are explicit, previewed, policy-governed, auditable, and purgeable.

---

## 1. Goals and non-goals

### 1.1 Goals

| ID | Goal |
|---|---|
| G1 | Store perf runs, diagnostic sessions, and later feature traces in one SQL Server schema with shared provenance and upload policy evidence. |
| G2 | Support two writers: `perftest push` in the CLI and Debug Console upload in the product. |
| G3 | Keep a single contract package for DDL, migrations, projection DTOs, policy vocabulary, canonical digests, preview shape, and conformance fixtures. |
| G4 | Reuse the extension's SQL Data Plane for in-product upload and central readback. No native SQLite driver, no new product driver. |
| G5 | Preserve official versus diagnostic separation. CI gates and fleet baseline views read official measurement metrics only. |
| G6 | Make upload privacy mechanical: classification decides, upload policy chooses the allowed projection, and preview shows what leaves the machine. |
| G7 | Make ingestion idempotent, resumable, auditable, and safe under concurrent duplicate uploads. |
| G8 | Provide SQL-first analysis, an in-product Perf History central provider, Grafana dashboards, and optional projections such as Bencher/OTLP. |
| G9 | Provide test fixtures that prove both writers project the same source artifacts to the same rows. |
| G10 | Keep local files and session journals as ground truth. The store is a projection that can be rebuilt. |

### 1.2 Non-goals for the first implementation

- Public product telemetry or cross-company multi-tenant telemetry.
- Real-time streaming ingestion.
- Replacing local perf run directories or session journals.
- Uploading raw SQL text, row data, prompts, model responses, connection strings, tokens, or secrets under the default policy.
- Storing heavy artifacts such as full VS Code logs, crash dumps, heap snapshots, screenshots, profiles, or HTML reports directly in relational rows.
- Making Bencher, OTLP, Tempo, Azure Monitor, or Grafana the system of record.
- Moving fleet baselines from a developer machine. Baseline mutation is CI/admin-only.

---

## 2. Existing systems and what they contribute

| System | Existing contribution | Central use |
|---|---|---|
| perftest run directories | `result.json`, `markers.jsonl`, `environment.json`, `summary.json`, reports, config snapshots, artifact refs | Ground truth for CLI run ingestion and replay/reprojection. |
| Local perf SQLite store | Normalized run/scenario/repetition/metric/baseline/comparison schema plus `official_metric_samples` view | SQL Server central schema starts as a dialect twin plus central upload dimensions. |
| Diagnostic session store | `SessionManifest` plus segmented JSONL `DiagEvent` journals | Session ingestion source and Debug Console upload target. |
| Debug Console | Session browser, export, imported perf runs, Perf History provider abstraction | Product upload UX and central readback surface. |
| SQL Data Plane | Domain API for open session, execute, cancellation, data-plane privacy, capability checks | In-product writer and central provider transport. |
| Observability contracts registry | Classified event vocabulary, policy discipline, generated/vendored contracts | Pattern for central contract and event families. |
| perftest CLI exit-code contract | Gate semantics `0..6` today; push gets a new non-gating failure code | CI keeps gate local and non-blocking central publish. |
| SQL Server container/test tooling | Live integration target | Central schema integration tests and round-trip probes. |

Important code-shape facts to preserve:

- Debug Console contracts already have a field-level `DataClassification` model, and `secret`, `connection.string`, `token`, `sql.text`, `row.data`, `model.prompt`, and `model.response` are concrete classes.
- Session journals are JSONL segments with manifests. Upload should stream segments and should not require loading a 100k-event session into memory.
- Perf History already has provider-style source dispatch and a SQLite source that is explicitly unsupported in-product because native SQLite driver loading is not the desired extension-host path.
- The SQL Data Plane domain API exists specifically to keep feature code away from transport DTOs and to keep SQL text, rows, secrets, and tokens out of adapter diagnostics.

---

## 3. System architecture

```text
                         Shared contract package
     DDL + migrations + projection DTOs + upload policies + fixtures
                                      |
                    +-----------------+-----------------+
                    |                                   |
                    v                                   v
        perftest push writer                  Debug Console writer
        result.json ground truth              session JSONL / imported run
        tedious SQL client                    product SQL Data Plane
                    |                                   |
                    +-----------------+-----------------+
                                      |
                                      v
                         Central SQL Server store
       upload_batches / upload_items / entities / kind tables / views
                                      |
           +--------------------------+---------------------------+
           |                          |                           |
           v                          v                           v
     SQL / Query Studio       Perf History central provider       Grafana
                                      |
                                      v
                              optional projections
                            Bencher / OTLP / support
```

Design rules:

1. **Contract first.** Writers do not invent row shape, policy, or digest rules. They call generated projection code from the shared contract.
2. **Files first.** The central store is rebuildable from run directories and session journals.
3. **Ledger last.** A committed entity is visible only after the batch commit stored procedure finishes. Partial batches are visible as ingestion evidence, not as analysis rows.
4. **Policy at the boundary.** Upload re-applies classification even when capture already did. Capture policy and upload policy are different gates.
5. **Readers use views.** Dashboards and in-product providers read stable views/table-valued functions, not every detail table directly.
6. **No silent central dependency for gates.** CI gates run before central publish and do not depend on central availability.

---

## 4. Shared contract package, C0

### 4.1 Location and shape

Recommended package ownership:

```text
perftest/packages/perf-contracts/
  sql/
    perf-store.schema.sql                  # existing SQLite/local schema
    central-store.schema.mssql.sql          # new SQL Server schema
    central-store.migrations/               # forward-only migrations
    central-store.procedures.sql            # ingestion/read/admin procs
    central-store.views.sql                 # read views and iTVFs
  src/central/
    dto.ts                                  # generated row/input DTOs
    projection.ts                           # canonical projection and dry-run preview
    policies.ts                             # named upload policies
    digest.ts                               # canonical JSON and digest rules
    conformance.ts                          # fixture helpers
  fixtures/central/
    golden-run/**
    golden-session/**
    privacy-canaries/**
```

Vendored into `vscode-mssql` as generated TypeScript in the same spirit as existing generated observability contracts. The product must not hand-edit generated central contract files.

### 4.2 Contract contents

| Artifact | Required content |
|---|---|
| DDL | schema, tables, indexes, views, iTVFs, stored procedures, roles, constraints, and `schema_info`. |
| Migrations | Forward-only SQL migration files with from/to schema version, repeatability tests, and rollback notes where rollback is not possible. |
| Projection DTOs | Canonical row shapes for upload batches, upload items, runs, repetitions, metrics, validations, sessions, events, markers, SQL activity, and artifact refs. |
| Digest rules | Canonical JSON normalization, field ordering, omitted-field handling, binary encoding, `content_digest`, `projection_digest`, and privacy-canary digest rules. |
| Upload policies | Named, versioned allow/drop/digest behavior over the current `DataClassification` taxonomy. |
| Preview shape | `UploadPreview` generated by the same projection path as upload, not by a second estimator. |
| Conformance fixtures | Golden run, golden session, privacy canaries, schema migration fixture, and one duplicate/reprojection fixture. |

### 4.3 Contract versions

Every uploaded batch and entity records:

```ts
interface CentralProjectionIdentity {
    contractVersion: string;       // DDL and DTO contract
    projectorVersion: string;      // projection code version or package version
    sourceSchemaVersion: string;   // result.json / diag event / manifest schema
    uploadPolicyId: string;        // e.g. team-default.v1
}
```

A content mismatch under the same `kind + naturalKey + contractVersion + projectorVersion` is refused. A content mismatch under a newer projector version may be a legitimate reprojection, but only through the stored procedure that records `reprojected` and preserves the old digest in the ledger.

---

## 5. Central SQL Server schema

The exact SQL belongs in `central-store.schema.mssql.sql`. This section defines the intended model and invariants.

### 5.1 Schema metadata

```sql
CREATE TABLE central.schema_info (
    schema_name        sysname       NOT NULL PRIMARY KEY,
    schema_version     nvarchar(40)  NOT NULL,
    contract_version   nvarchar(40)  NOT NULL,
    created_at_utc     datetime2(7)  NOT NULL DEFAULT sysutcdatetime(),
    updated_at_utc     datetime2(7)  NOT NULL DEFAULT sysutcdatetime()
);
```

The admin command `perftest central init` creates the database objects. `perftest central migrate` applies forward-only migrations. `perftest central check` validates views, procedures, constraints, and fixture round-trip state.

### 5.2 Uploaders and principals

```sql
CREATE TABLE central.uploaders (
    uploader_id        bigint IDENTITY PRIMARY KEY,
    principal_kind     nvarchar(30)  NOT NULL, -- domainUser | alias | ci | servicePrincipal
    principal_digest   nvarchar(80)  NOT NULL, -- non-reversible stable digest
    display_name       nvarchar(200) NULL,     -- optional safe alias
    is_ci              bit           NOT NULL DEFAULT 0,
    first_seen_utc     datetime2(7)  NOT NULL DEFAULT sysutcdatetime(),
    last_seen_utc      datetime2(7)  NULL,
    CONSTRAINT uq_uploaders_principal UNIQUE (principal_kind, principal_digest)
);
```

Do not store raw email, account, host, or machine name by default. The UI may show a local display label in preview, but the store should prefer digests unless the upload policy explicitly permits a plain alias.

### 5.3 Upload batches

`upload_batches` represents an attempt. It can be committed, already present, refused, failed, or abandoned.

```sql
CREATE TABLE central.upload_batches (
    upload_batch_id       bigint IDENTITY PRIMARY KEY,
    uploader_id           bigint        NOT NULL REFERENCES central.uploaders(uploader_id),
    tool                  nvarchar(60)  NOT NULL, -- perftest-push | debug-console
    tool_version          nvarchar(60)  NOT NULL,
    contract_version      nvarchar(40)  NOT NULL,
    projector_version     nvarchar(80)  NOT NULL,
    upload_policy_id      nvarchar(120) NOT NULL,
    source_kind           nvarchar(30)  NOT NULL, -- perfRun | diagSession | featureTrace
    natural_key           nvarchar(200) NOT NULL,
    content_digest        nvarchar(100) NOT NULL,
    projection_digest     nvarchar(100) NOT NULL,
    status                nvarchar(30)  NOT NULL, -- started | committed | alreadyPresent | reprojected | refused | failed | abandoned | purged
    outcome_reason        nvarchar(200) NULL,
    row_counts_json       nvarchar(max) NOT NULL,
    dropped_counts_json   nvarchar(max) NOT NULL,
    digested_counts_json  nvarchar(max) NOT NULL,
    source_summary_json   nvarchar(max) NOT NULL,
    started_at_utc        datetime2(7)  NOT NULL DEFAULT sysutcdatetime(),
    committed_at_utc      datetime2(7)  NULL
);
```

Add `ISJSON` checks where compatible with the minimum supported SQL Server and database compatibility level.

### 5.4 Upload items

`upload_items` records the projected slices inside a batch. It makes partial upload, retry, and support triage boring, which is exactly what we want.

```sql
CREATE TABLE central.upload_items (
    upload_item_id     bigint IDENTITY PRIMARY KEY,
    upload_batch_id    bigint        NOT NULL REFERENCES central.upload_batches(upload_batch_id),
    item_kind          nvarchar(50)  NOT NULL, -- runs | metrics | diag_events | markers | sql_activity | artifact_refs | etc.
    item_ordinal       int           NOT NULL,
    row_count          int           NOT NULL,
    payload_digest     nvarchar(100) NOT NULL,
    status             nvarchar(30)  NOT NULL, -- staged | applied | skipped | failed
    error_code         nvarchar(80)  NULL,
    error_message      nvarchar(400) NULL,
    created_at_utc     datetime2(7)  NOT NULL DEFAULT sysutcdatetime(),
    CONSTRAINT uq_upload_items_batch_kind_ordinal UNIQUE (upload_batch_id, item_kind, item_ordinal)
);
```

### 5.5 Central entities

`central_entities` is the current projection state for one natural artifact. This is where duplicate upload and reprojection rules land.

```sql
CREATE TABLE central.central_entities (
    entity_id            bigint IDENTITY PRIMARY KEY,
    kind                 nvarchar(30)  NOT NULL, -- perfRun | diagSession | featureTrace
    natural_key          nvarchar(200) NOT NULL,
    current_batch_id     bigint        NOT NULL REFERENCES central.upload_batches(upload_batch_id),
    contract_version     nvarchar(40)  NOT NULL,
    projector_version    nvarchar(80)  NOT NULL,
    content_digest       nvarchar(100) NOT NULL,
    projection_digest    nvarchar(100) NOT NULL,
    upload_policy_id     nvarchar(120) NOT NULL,
    environment_hash     nvarchar(100) NULL,
    product_sha          nvarchar(80)  NULL,
    created_at_utc       datetime2(7)  NOT NULL DEFAULT sysutcdatetime(),
    updated_at_utc       datetime2(7)  NOT NULL DEFAULT sysutcdatetime(),
    purged_at_utc        datetime2(7)  NULL,
    CONSTRAINT uq_central_entities_kind_key UNIQUE (kind, natural_key)
);
```

Kind-specific tables reference `entity_id` or the natural key. Use one convention consistently in DDL. This document recommends `entity_id` for central joins and natural key columns for convenience and fixture parity.

### 5.6 Perf run tables

Start as a SQL Server dialect twin of the local perf schema, with central additions:

- `runs.entity_id`, `runs.upload_batch_id`, `runs.uploader_id`.
- `runs.run_id` globally unique.
- `run_repositories` for git SHAs, dirty flags, branch/PR context, and repo name.
- `environments.environment_hash` globally unique.
- `metrics` keep `official`, `eligibility`, `pass_type`, `source`, `component`, `process_role`, `unit`, `lower_is_better`, and derivation/config JSON.
- `baselines` are writeable only by `central_ci` or admin procedures.
- `official_metric_samples` central view must be semantically identical to the local SQLite view.

Minimum canned views:

```text
central.official_metric_samples
central.latest_run_per_scenario_env
central.regressions_last_30d
central.trend(scenario_id, metric_name, environment_hash)
central.fleet_by_build
```

### 5.7 Diagnostic session tables

```sql
CREATE TABLE central.diag_sessions (
    entity_id            bigint        NOT NULL REFERENCES central.central_entities(entity_id),
    session_id           nvarchar(100) NOT NULL PRIMARY KEY,
    upload_batch_id      bigint        NOT NULL REFERENCES central.upload_batches(upload_batch_id),
    source               nvarchar(30)  NOT NULL, -- live | perfRun | bundle
    capture_mode         nvarchar(40)  NOT NULL,
    capture_policy_id    nvarchar(120) NOT NULL,
    upload_policy_id     nvarchar(120) NOT NULL,
    created_utc          datetime2(7)  NOT NULL,
    event_count          int           NOT NULL,
    gap_count            int           NOT NULL,
    source_size_bytes    bigint        NULL,
    provenance_json      nvarchar(max) NOT NULL,
    environment_hash     nvarchar(100) NULL,
    status               nvarchar(30)  NOT NULL -- active | closed | partial | uploaded
);

CREATE TABLE central.diag_events (
    session_id           nvarchar(100) NOT NULL REFERENCES central.diag_sessions(session_id),
    seq                  bigint        NOT NULL,
    event_id             nvarchar(80)  NULL,
    epoch_ms             bigint        NOT NULL,
    monotonic_ns         nvarchar(40)  NULL,
    process              nvarchar(40)  NOT NULL,
    pid                  int           NULL,
    feature              nvarchar(80)  NOT NULL,
    kind                 nvarchar(40)  NOT NULL,
    type                 nvarchar(200) NOT NULL,
    status               nvarchar(40)  NOT NULL,
    trace_id             nvarchar(80)  NULL,
    cause_event_id       nvarchar(80)  NULL,
    duration_ms          float         NULL,
    timing_class         nvarchar(60)  NULL,
    cls_max              nvarchar(80)  NOT NULL,
    cls_rank             int           NOT NULL,
    payload_json         nvarchar(max) NOT NULL,
    payload_digest       nvarchar(100) NOT NULL,
    CONSTRAINT pk_diag_events PRIMARY KEY (session_id, seq)
);
```

Recommended indexes:

```sql
CREATE INDEX ix_diag_events_feature_type_time
ON central.diag_events(feature, type, epoch_ms DESC)
INCLUDE (status, duration_ms, trace_id, session_id, seq);

CREATE INDEX ix_diag_events_trace
ON central.diag_events(trace_id, epoch_ms, session_id, seq)
WHERE trace_id IS NOT NULL;

CREATE INDEX ix_diag_events_status_time
ON central.diag_events(status, epoch_ms DESC)
INCLUDE (feature, type, duration_ms);
```

Payload rules:

- `payload_json` is already filtered by upload policy.
- `cls_max` and `cls_rank` are computed using the contract's classification order, not lexicographic order.
- Default policy does not keep SQL text, row data, connection strings, tokens, prompts, model responses, or secrets.
- Consider SQL Server page compression or archiving before `payload_json` compression. Compressed payloads are harder to query, so compression is a C5/C6 decision, not a C0 default.

### 5.8 Detail tiers

| Tier | Tables | Default timing | Notes |
|---|---|---|---|
| Tier 1 | runs, repositories, environments, scenarios, repetitions, metrics, validations, artifact refs, diag sessions, promoted diag event rows | C1/C2 | Required for shared trends and session triage. |
| Tier 2 | markers, central waterfalls, richer event detail | C5 | Larger and useful, but not needed to prove the spine. |
| Tier 3 | SQL activity, feature traces, support-bundle refs | C5/C6 | Policy-sensitive. SQL text only under explicit synthetic/support policy. |
| Projection only | Bencher, OTLP | C7 | Not a system of record. |

### 5.9 Canned reader views

Minimum reader surface:

```text
central.official_metric_samples
central.latest_run_per_scenario_env
central.trend(scenario_id, metric_name, environment_hash)
central.regressions_last_30d
central.sessions_by_feature_error_rate
central.sessions_by_build
central.fleet_by_build
central.upload_history
central.central_health
central.policy_drop_summary
central.ingestion_failures
```

Views must distinguish:

- no data;
- data filtered out by official/diagnostic rules;
- data missing because upload failed;
- data missing because upload policy dropped it;
- permission denied.

That distinction matters because the Debug Console and Perf History UI should never render "empty" when the real state is "unavailable" or "filtered."

---

## 6. Idempotency and ingestion protocol

### 6.1 Entity key

```text
EntityKey = (kind, naturalKey)
kind = perfRun | diagSession | featureTrace
naturalKey = runId | sessionId | featureTraceId
```

Natural keys are globally unique by design and should remain the central uniqueness boundary. A second uploader of the same run or session records provenance but does not duplicate analysis rows.

### 6.2 Digests

| Digest | Meaning |
|---|---|
| `source_digest` | Digest of source artifact inventory: source files, manifests, schema versions, and source row counts. |
| `content_digest` | Digest of canonical policy-filtered source content before table projection. Used to detect mutation under the same natural key. |
| `projection_digest` | Digest of projected row set after contract projection. Used for row-level conformance and writer parity. |
| `payload_digest` | Digest per uploaded item or event payload. Used for canaries, retries, and support. |

The contract owns canonical JSON: sorted object keys, stable number formatting, stable missing/null handling, and stable string normalization.

### 6.3 Outcomes

| Existing entity state | Incoming state | Outcome |
|---|---|---|
| none | any valid projection | `inserted` |
| same `content_digest` and same or compatible projection | duplicate upload | `alreadyPresent` |
| same natural key, different `projection_digest`, newer `projector_version`, same source truth | reproject through stored proc | `reprojected` |
| same natural key, different `content_digest`, same projector/contract | refused | `refused` |
| policy would upload prohibited class | refused before transport | `refusedByPolicy` |
| upload canceled mid-stream | incomplete batch | `abandoned` or `failed`, entity unchanged |
| purge requested | rows removed or redacted per policy | `purged` |

### 6.4 Stored-procedure ingestion

Writers call procedures rather than writing tables directly:

```sql
central.usp_begin_upload
central.usp_stage_upload_item
central.usp_commit_upload
central.usp_abort_upload
central.usp_purge_entity
central.usp_set_baseline
central.usp_retention_cleanup
central.usp_store_health
```

Implementation guidance:

- Use explicit transactions in `usp_commit_upload`.
- Use uniqueness constraints as the last line of defense.
- Use `UPDLOCK, HOLDLOCK` on `central_entities` or `sp_getapplock` on a hash of `(kind, naturalKey)` while deciding insert/duplicate/reprojection/refusal.
- Do not default to `MERGE`. `MERGE` can be considered only if the generated SQL has a dedicated concurrency test, plan review, and exact refusal semantics.
- Write `upload_batches.status = committed` only after all kind-specific rows are applied and checks pass.
- Record every refusal and failure with a safe reason code. Failure evidence is valuable.

---

## 7. Privacy and upload policies

### 7.1 Policy principle

Capture policy controls what is collected locally. Upload policy controls what may leave the machine. The upload boundary must re-apply classification and must be able to drop or digest fields that local capture retained.

Default behavior:

- no raw SQL text;
- no row data;
- no connection strings;
- no tokens;
- no secrets;
- no prompts or model responses;
- object/server/database names digest by default for broad dogfood uploads unless the policy explicitly permits plaintext metadata names.

### 7.2 Policy matrix

Initial policies:

| Policy | Intended user | Keep | Digest | Drop/refuse |
|---|---|---|---|---|
| `team-default.v1` | internal engineering/dogfood | `public`, `system.metadata`, `diagnostic.metadata`, `result.shape`, `sql.digest` | `source.path`, `server.name`, `database.name`, `schema.name`, `object.name`, selected `user.text` when safe | drop `sql.text`, `row.data`, `connection.string`, `token`, `model.prompt`, `model.response`, `unknown`; refuse `secret` |
| `team-names.v1` | trusted internal investigation where object names are necessary | above plus selected metadata names as plaintext | source paths and machine labels | same prohibitions as default |
| `elevated-support.v1` | explicit support/investigation gesture | policy-specific feature traces and richer metadata | names depending on consent | secrets always refused; SQL/rows/prompts only if a separate, explicit support policy is ratified |
| `ci-official.v1` | official CI/perftest | perf run metrics, validations, environment hash, repo SHAs, scenario IDs, synthetic SQL activity where allowed | agent/machine labels as needed | diagnostic session journals, prompts, row data, connection strings, tokens, secrets |

The policy matrix must be generated into both repos and tested with canary source artifacts.

### 7.3 Preview contract

```ts
interface UploadPreview {
    contractVersion: string;
    projectorVersion: string;
    sourceKind: "perfRun" | "diagSession" | "featureTrace";
    naturalKey: string;
    uploadPolicyId: string;
    contentDigest: string;
    projectionDigest: string;
    sourceSummary: {
        files: number;
        bytes: number;
        events?: number;
        metrics?: number;
        gaps?: number;
    };
    tables: Array<{ name: string; rows: number; bytesEstimate?: number }>;
    dropped: Array<{ field: string; cls: string; count: number }>;
    digested: Array<{ field: string; cls: string; count: number }>;
    refused?: Array<{ field: string; cls: string; reason: string }>;
    warnings: string[];
}
```

The preview is the projection in dry-run mode. Upload uses the same projected row stream. If preview and upload counts diverge, the upload should fail before commit.

### 7.4 Privacy canaries

C0 fixtures must contain seeded canaries for:

- SQL text;
- row values;
- connection strings;
- passwords;
- bearer tokens;
- user free text;
- model prompts and responses;
- server/database/schema/object names;
- paths and machine labels.

Tests scan projected rows, preview JSON, logs, diagnostics, status output, and dashboard seed data.

---

## 8. Writer designs

### 8.1 `perftest push`, C1

Command surface:

```text
perftest central init --target <connstring|env>
perftest central check --target <connstring|env>
perftest push [runId | --all-new] --target <connstring|env> [--dry-run] [--with-markers] [--with-sql-activity]
```

Behavior:

- Read `result.json` and run directory artifacts, not `perf.db`, so a fresh clone can backfill history.
- Use contract projection code to produce `UploadPreview` and row stream.
- Default payload is Tier 1: runs, repositories, environments, scenarios, repetitions, metrics, validations, and artifact refs.
- C5 adds `--with-markers` and `--with-sql-activity`.
- Connection via `MSSQL_PERFTEST_CENTRAL_CONNSTRING` or CLI argument. Never persist the raw value.
- New exit code `7 pushFailed`. Do not overload infrastructure failure code `5` for central push failure.
- Emit `centralStore.push.*` or `centralObservability.push.*` diagnostics through the existing observability-contract path.

Push is idempotent. `--dry-run` prints the same preview and policy results that the product UI shows.

### 8.2 CI publish, C1-prime

Workflow:

```text
checkout
build
run perftest gates
write run artifacts
upload run directory as CI artifact
perftest push --target central (continue-on-error)
write job summary with local gate verdict and central push receipt/failure
```

Rules:

- Central outage never makes a passing local gate fail.
- Central push failure is visible in job summary and diagnostics.
- PR runs are tagged with branch/PR context and excluded from fleet baselines by default.
- Scheduled pinned-agent runs feed trend dashboards.
- Only the CI principal can set central baselines.

### 8.3 Debug Console upload, C2

Entry points:

- session history row: **Upload to shared server**;
- live session: **Upload current session snapshot** after the manifest is closed or checkpointed;
- imported perf run: **Upload run to shared server**.

Settings:

```jsonc
"mssql.centralObservability.targetProfileId": "",
"mssql.centralObservability.defaultUploadPolicy": "team-default.v1",
"mssql.centralObservability.quickUpload": false,
"mssql.centralObservability.maxEventsPerUpload": 100000,
"mssql.centralObservability.enabled": false
```

UX flow:

1. User chooses a session/run.
2. Extension builds `UploadPreview` from the vendored contract.
3. Preview shows target, policy, row counts, dropped classes, digested classes, refused fields, estimated bytes, and warnings.
4. User confirms.
5. Upload opens a SQL Data Plane session with `applicationName = vscode-mssql-central-upload`, background priority, and `commandKind = metadata` or a new central-upload kind if the data-plane API adds one.
6. Upload streams segments/items in bounded batches through stored procedures using `OPENJSON` or TVP-shaped parameters.
7. Commit returns a ledger receipt.
8. Debug Console records the receipt and offers copy query/open central history actions.

Cancellation stops at item or segment boundaries. A later upload resumes idempotently through the batch/entity protocol.

### 8.4 Product-side central readback, C3

Add a Perf History source kind:

```ts
type PerfSourceKind = "directory" | "sqlite" | "bundle" | "central";
```

Provider rules:

- Use SQL Data Plane queries against canned views/procs.
- Page every list.
- Show distinct states: unavailable, permission denied, empty, filtered, error, indexed.
- Never download unbounded event payloads into the webview.
- Do not require a native SQLite driver.
- Trend results must match equivalent CLI SQL queries on the same central DB.

---

## 9. Readers and dashboards

### 9.1 SQL and Query Studio

SQL is the primary investigation surface. The schema should be pleasant to query directly, with enough views to avoid memorizing table joins.

Example questions that should be one query away:

- Which scenarios regressed in the last 30 days on the same environment hash?
- Which product SHA has the highest dogfood error rate?
- Did normal usage sessions show errors around a build that also regressed official metrics?
- Which upload policies are dropping the most fields?
- Which uploads failed, refused, or reprojected this week?

### 9.2 Perf History central provider

The central provider should reuse the existing Perf History UI shape. It adds shared history rather than inventing a new view.

Initial capabilities:

- list central runs;
- filter by scenario, status, branch/PR context, environment hash, source kind;
- show run summary and scenario details;
- show trend chart from central `trend` view;
- open upload receipt and central query links;
- later: waterfall and SQL activity details from C5 tables.

### 9.3 Grafana

Grafana uses the Microsoft SQL Server data source pointed at views. Dashboard JSON lives in the repo.

Initial panels:

- latest official gate verdict by scenario;
- regressions last 30 days;
- trend by scenario/metric/environment;
- upload health by writer/tool version;
- sessions by feature error rate;
- fleet by build: dogfood sessions joined to CI run verdicts;
- policy drops/digests over time.

### 9.4 Optional projections

Bencher and OTLP are projections of the central store or of source artifacts. They are not systems of record. C7 begins only after the SQL store is stable.

---

## 10. Security, roles, operations, and retention

### 10.1 Roles

| Role | Permissions |
|---|---|
| `central_reader` | SELECT on approved views and execute approved read procs. |
| `central_writer` | Execute ingestion procs only. No direct table writes. No baseline mutation. |
| `central_ci` | Writer permissions plus baseline and CI tag procedures. |
| `central_admin` | Schema migration, retention cleanup, purge, grants. |
| `central_grafana` | SELECT on dashboard views only. |

Avoid granting humans direct write access to base tables. It will save future-us from audit goblins nesting in the schema walls.

### 10.2 Retention

Defaults to ratify:

| Data | Default retention | Notes |
|---|---|---|
| official metrics, validations, run manifests | years | Small and trend-critical. |
| upload batches and ledger summaries | years | Audit and provenance. |
| diagnostic sessions manifest rows | years or until purge | Small and useful for audit. |
| `diag_events` | 90 days | Growth center. Table-driven TTL. |
| markers | 30 days | Large detail data. |
| SQL activity | 30 days | Policy-sensitive. |
| heavy artifacts | external storage policy | Relational rows hold refs and digests only. |

Retention should be a stored proc runnable by SQL Agent, Azure Automation, a scheduled job, or `perftest central cleanup`. Do not require SQL Agent specifically.

### 10.3 Purge

`central.usp_purge_entity(kind, natural_key, reason)` must:

- delete or anonymize kind-specific rows;
- mark the entity as purged;
- leave a minimal audit record without sensitive payload;
- remove uploader display data if the purge is a privacy request;
- keep aggregate counts only when they cannot identify a person or artifact.

The Debug Console should expose "copy purge command" or an admin flow rather than hiding the fact that purge is a database operation.

### 10.4 Health

`central.central_health` should report:

- schema version;
- latest upload by kind;
- failed/refused batches by day;
- largest sessions;
- event rows by retention window;
- last retention cleanup;
- writer tool versions;
- canary projection version;
- orphaned staging rows;
- permission/procedure version mismatches.

---

## 11. Observability for the central feature

Register vocabulary through the observability contracts first. Suggested families:

```text
centralObservability.preview.begin/end
centralObservability.upload.begin/end
centralObservability.upload.item.begin/end
centralObservability.upload.commit.begin/end
centralObservability.upload.failed
centralObservability.upload.refused
centralObservability.push.begin/end
centralObservability.push.failed
centralObservability.provider.query.begin/end
centralObservability.provider.failed
centralObservability.schema.migrate.begin/end
```

Allowed fields:

- source kind;
- policy id;
- row counts;
- dropped/digested counts;
- duration;
- status/outcome;
- tool version;
- short non-reversible profile/server fingerprint;
- central schema version;
- query/view name.

Disallowed fields:

- SQL text;
- result rows;
- raw object names unless explicitly allowed by a metadata-name policy;
- raw server endpoints;
- connection strings;
- passwords;
- tokens;
- prompts;
- model responses.

---

## 12. Test strategy

### 12.1 Contract tests, C0

- Create fresh SQL Server database from DDL.
- Apply migrations from empty and from the previous fixture schema.
- Validate procedures and views exist.
- Project golden run in perftest and vscode-mssql. Compare row sets.
- Project golden session in perftest and vscode-mssql. Compare row sets.
- Run privacy canaries through every policy.
- Validate `official_metric_samples` central view against local SQLite fixture output.
- Validate duplicate upload, refused digest drift, and reprojected flow.

### 12.2 Writer tests

| Writer | Tests |
|---|---|
| `perftest push` | dry-run preview, container DB push, duplicate push, digest drift refusal, permission denied, central outage, bad schema version, CI non-blocking publish. |
| Debug Console upload | preview counts, segment streaming, cancellation/resume, 100k-event bounded memory, imported run parity with CLI, central outage, permission denied, policy refusal, receipt rendering. |

### 12.3 Reader tests

- Central provider list/query/scenario details/trend parity.
- Empty/error/permission/filtered states rendered distinctly.
- Pagination and max row caps.
- Grafana view smoke queries.
- Retention cleanup leaves health coherent.

### 12.4 Perf and soak tests

Add a PERF_MODE or self-test probe:

```text
mssql.perf.centralUploadRoundTrip
```

Flow:

1. create or load fixture session;
2. preview upload;
3. upload to SQL Server container through data plane;
4. read back through central provider;
5. assert row counts, digests, policy drops, and provider state.

This probe becomes a perftest scenario when stable.

---

## 13. Build plan

The C0-C7 names are preserved, but C0 is broken into smaller coding-agent batches.

### C0 - Contract and store foundation

| ID | Task | Primary files | Acceptance |
|---|---|---|---|
| C0.1 | Add central DDL, `schema_info`, roles, base tables, views, procedures | `perf-contracts/sql/central-store.*.sql` | Fresh SQL Server DB creates cleanly. |
| C0.2 | Add generated DTOs and projection/digest library | `perf-contracts/src/central/**` | Golden fixtures project deterministically. |
| C0.3 | Add upload policies and preview contract | `policies.ts`, `projection.ts` | Policy canaries pass. |
| C0.4 | Add conformance fixtures | `fixtures/central/**` | perftest and vscode-mssql compare identical projected rows. |
| C0.5 | Vendor generated central contract to vscode-mssql | generated shared interface path | Product build imports generated contract only. |
| C0.6 | Add central event vocabulary | observability registry | No unregistered central events. |
| C0.7 | Add migration and health checks | CLI/admin scripts | migrate/check green on empty and fixture DBs. |

### C1 - `perftest push`

| Task | Acceptance |
|---|---|
| `perftest central init/check` | Creates and validates a container DB. |
| `perftest push --dry-run` | Preview matches projection fixture. |
| `perftest push <runId>` Tier 1 | Inserts one fixture run and returns receipt. |
| Duplicate push | Returns `alreadyPresent`, no duplicate rows. |
| Digest drift fixture | Refuses loudly and leaves entity unchanged. |
| Exit code 7 | Central outage returns push failure without gate-code ambiguity. |
| Push observability | Emits registered central push events with safe fields only. |

### C1-prime - CI publish

| Task | Acceptance |
|---|---|
| Add workflow on pinned agent | Local gate outcome unchanged. |
| Upload run artifacts | Artifact available even if central push fails. |
| Push after local gate | Central outage does not fail a passing gate. |
| Tag PR/nightly context | Central views can include/exclude PR runs. |
| Protect baseline writes | Developer credentials cannot set fleet baselines. |

### C2 - Debug Console upload

| Task | Acceptance |
|---|---|
| Add settings and target profile resolution | No raw connection string persistence. |
| Add preview RPC/UI | Shows row counts, policy, dropped/digested/refused fields. |
| Add data-plane writer | Streams 100k events without unbounded memory. |
| Add receipt UI | Shows batch id, outcome, rows, policy id, digest. |
| Add cancel/resume | Canceled upload can re-run idempotently. |
| Upload imported perf run | Row parity with CLI projection. |
| Privacy canaries | Product upload path leaks none. |

### C3 - Central Perf History provider

| Task | Acceptance |
|---|---|
| Add `central` source kind | Source appears only when configured. |
| Implement paged queries | No unbounded central read into webview. |
| Implement state ladder | unavailable, permission, empty, filtered, error distinct. |
| Trend parity | Provider trend equals direct SQL view on fixture DB. |
| Receipt drill-in | Upload receipt can open related central runs/sessions. |

### C4 - Grafana dashboards

| Task | Acceptance |
|---|---|
| Add dashboard JSON | Panels load against fixture DB. |
| Add SQL views/iTVFs | Dashboard uses views, not hand-joined table soup. |
| Add central health panel | Shows upload health and freshness. |

### C5 - Detail tiers

| Task | Acceptance |
|---|---|
| Add marker rows | Waterfall query works on central data. |
| Add SQL activity rows | Synthetic/policy rule enforced. |
| Add retention cleanup | Detail TTL proven with fixture. |
| Add C5 canaries | SQL text/row data policy remains enforced. |

### C6 - Support bundles and purge

| Task | Acceptance |
|---|---|
| Add artifact refs | Heavy files stay external with digest/ref. |
| Add support policy workflow | Explicit gesture and preview required. |
| Add purge proc and admin UX | S7/S8 walkthrough signed off. |

### C7 - Optional projections

| Projection | Rule |
|---|---|
| Bencher | Projection from central/source truth. Not authoritative. |
| OTLP | Adapter for traces/spans where useful. Not authoritative. |

---

## 14. Decisions to ratify

1. **Store foundation:** SQL Server is the system of record for the central projection, with local files remaining source truth.
2. **Contract owner:** `perf-contracts` owns SQL Server DDL, migrations, DTOs, policy vocabulary, digests, and fixtures.
3. **Writer permissions:** writers execute stored procedures; no broad direct table writes.
4. **No default MERGE:** ingestion uses explicit stored-proc idempotency unless a reviewed `MERGE` proof is added.
5. **Natural key uniqueness:** `(kind, naturalKey)` is global; duplicate uploads become ledger evidence, not duplicate rows.
6. **Digest drift:** same key + same projector + changed content is refused, not last-writer-wins.
7. **Policies:** default upload policy digests or drops names/paths and drops SQL/rows/prompts; a metadata-name policy can be ratified separately.
8. **Identity:** no anonymous uploads. Alias plus pseudonymized machine label allowed for dogfooders.
9. **Baseline writes:** CI/admin only.
10. **Retention:** initial defaults 90 days for diag events, 30 days for marker/SQL-activity detail, years for official metrics and ledger summaries.
11. **Hosting:** choose initial SQL Server/Azure SQL DB, auth model, and CI secret/managed identity path before C1-prime.
12. **Commit train:** use a dedicated `dc:` train for Debug Console central work or explicitly choose `core:` plus `qs:`/existing labels.

---

## 15. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Two writers drift | Shared contract, generated DTOs, golden fixtures, both-repo conformance tests. |
| `diag_events` volume | Default TTL, promoted indexes, pagination, row caps, C5 retention jobs, no unbounded reads. |
| Privacy leak through preview/logs | Preview generated from policy-filtered projection, canaries scan preview/logs/status/store. |
| CI accidentally depends on central | Push is after local gate and continue-on-error. New exit code 7 never replaces gate exit codes. |
| Dogfooder auth friction | Use saved SQL profiles and explicit target setting; decide server/auth before C2 dogfood. |
| Schema migration with existing data | Forward-only migrations, fixture migration tests, reprojection path. |
| Baselines moved by developers | Role-gated central baseline procs and CI-only credentials. |
| Cross-machine timing misuse | Views use environment hash and same-process monotonic durations; no cross-machine epoch duration comparisons. |
| Heavy artifacts bloat SQL DB | Store refs and digests only. Blob/fileshare story remains C6. |
| Query readers join base tables incorrectly | Publish stable views/iTVFs and point Grafana/product readers at them. |

---

## 16. First coding-agent handoff

Start with **C0.1 + C0.2 only**. Do not start UI upload before the store contract exists.

Implementation boundaries:

1. Add `central-store.schema.mssql.sql`, `central-store.views.sql`, `central-store.procedures.sql`, and a minimal `schema_info` migration.
2. Add DTOs for `UploadPreview`, `UploadBatch`, `UploadItem`, `CentralEntity`, perf Tier 1 rows, session rows, and event rows.
3. Add a canonical digest helper with fixture tests.
4. Add one golden perf run fixture and one golden session fixture.
5. Add privacy canary fixture.
6. Add tests that project fixtures twice and get byte-identical row sets.
7. Add a SQL Server container integration test that creates the schema and runs `central.usp_store_health`.
8. Update this document's code-truth section and `CENTRAL_OBSERVABILITY_VISUALS.tex` if implementation decisions change.

Do not implement `perftest push` until the fixture projection and schema creation are green. The contract is the compass; without it, every writer walks into a different fog bank.
