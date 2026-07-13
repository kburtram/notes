# VectorLab synthetic SQL corpus

Extracted from `coding-docs/query-result-tabs/vector_workbench_test_and_demo_guide.md`
(the guide is the source of truth; the brief `_build/briefs/r04-vector-test-guide.md`
summarizes it). Verified live on **2026-07-11** against **Microsoft SQL Server 2025
(RTM) 17.0.1000.7 (X64), Enterprise Developer Edition**, database `VectorLab`,
compatibility level 170.

## Files

| File | What it is | Guide source |
| --- | --- | --- |
| `vectorlab_setup.sql` | Track A deterministic synthetic lab: `dbo.VectorLabDocuments` (1,000 docs), `dbo.VectorLabChunks` (5,000 rows, `VECTOR(64)`, deterministic cluster vectors + planted anomalies), `dbo.VectorLabSearchCorpus` (clean indexable copy, 4,959 rows), `dbo.VectorLabSearchQueries` (5 queries), `dbo.VectorLabExpectedRelevant` (graded relevance). Verbatim guide section 6.2 (lines 374-797) plus an added idempotent header (create `VectorLab` database if missing, `USE VectorLab`). The guide's own `DROP TABLE IF EXISTS` statements make the whole file rerunnable; a second run was verified clean. | §6.2, lines 374-797 |
| `vectorlab_probe.sql` | Capability probe: engine/compat facts, preview and external-endpoint gates, native vector columns, external models, vector indexes, health DMV. Verbatim guide section 5 plus a header and `GO` batch separators between the guide's top-level statements (so one incompatible statement cannot abort the whole probe — see discrepancy 1). | §5, lines 213-333 |
| `vectorlab_groundtruth.sql` | Acceptance queries written from the guide's stated ground truth (§6.3, lines 800-814). Result set 1: one row per anomaly class with expected vs observed and PASS/FAIL. Result set 2: informational full-table census of byte-equal vector groups. | §6.3 (counts); queries authored here |
| `vectorlab_setup_azure.sql` | Azure SQL Database adaptation of `vectorlab_setup.sql`: no CREATE DATABASE/USE header (single-database scope), objects in schema `vectorlab` instead of a VectorLab database (`vectorlab.VectorLab*`, schema-qualified everywhere incl. FKs and generation joins), and the guide's compat-level raise duplicated into its own header batch (a same-batch raise cannot rescue `GENERATE_SERIES` on a compat-150 database — verified live, Msg 208). Data generation is byte-faithful to the guide. | §6.2 via `vectorlab_setup.sql` |
| `vectorlab_groundtruth_azure.sql` | Azure adaptation of `vectorlab_groundtruth.sql`: no `USE`, `vectorlab.*` object names; expected counts unchanged. | §6.3 via `vectorlab_groundtruth.sql` |

## How to run

```
sqlcmd -S localhost -E -C -i vectorlab_setup.sql
sqlcmd -S localhost -E -C -d VectorLab -i vectorlab_probe.sql
sqlcmd -S localhost -E -C -i vectorlab_groundtruth.sql
```

- `-E` integrated auth, `-C` trust server certificate. Add `-W -s"|"` for compact output.
- `vectorlab_setup.sql` and `vectorlab_groundtruth.sql` select the `VectorLab` database
  themselves; the probe is database-agnostic by design, so pass `-d VectorLab`.
- Requires SQL Server 2025 (VECTOR type needs compatibility level >= 170; the setup
  script raises the level itself if the database is below 170).
- Use a disposable server/database. The lab deliberately plants anomalies.

### Azure SQL Database

```
sqlcmd -S tcp:<server>.database.windows.net,1433 -d <db> -U <user> -P <pw> -C -I -l 30 -i vectorlab_setup_azure.sql
sqlcmd -S tcp:<server>.database.windows.net,1433 -d <db> -U <user> -P <pw> -C -I -l 30 -i vectorlab_groundtruth_azure.sql
```

Verified live 2026-07-11 against Azure SQL Database (SQL Azure 12.0.2000.8,
EngineEdition 5, GP_S_Gen5_1 serverless, compat level raised 150 -> 170 by the
setup script): **all 18 ground-truth checks PASS with the same expected counts**,
and the informational duplicate census matches (14 groups / 49 rows). Setup summary:
total_rows 5000, non_null_vectors 4988, dims 64/64, min_norm2 0.0, max_norm2
4.9223265647888184 (differs from the local RTM value 4.9223264451224198 in the 8th
significant digit — a float summation-path difference, within one float32 ulp;
thresholded checks are unaffected). Full Azure-vs-RTM surface deltas (catalog shapes,
DMV presence, `VECTOR_SEARCH`/`WITH APPROXIMATE` gating, DiskANN index build failure
on this tier) live in `../evidence/vector-provider-matrix.md`.

## Verified ground truth (expected vs observed)

All checks passed on first run and after an idempotency rerun (2026-07-11,
17.0.1000.7 RTM).

| # | Check | Expected | Observed | Status |
| --- | --- | --- | --- | --- |
| 01 | Total chunk rows | 5000 | 5000 | PASS |
| 02 | Null vectors (chunk 1-12) | 12 | 12 | PASS |
| 03 | Exact zero vectors (chunk 13-16) | 4 | 4 | PASS |
| 04 | Near-zero vectors (chunk 17-24) | 8 | 8 | PASS |
| 05 | High-norm outliers, norm2 > 2 (chunk 25-41) | 17 | 17 | PASS |
| 06 | Duplicate groups (planted, `duplicate_group`) | 12 | 12 | PASS |
| 07 | Duplicate rows covered (planted) | 37 | 37 | PASS |
| 08 | Planted dup groups with unequal vectors | 0 | 0 | PASS |
| 09 | Stale source text (`source_modified_at > embedded_at`, chunk 300-349) | 50 | 50 | PASS |
| 10 | Provenance mismatch (`LegacyModelV1`, chunk 400-449) | 50 | 50 | PASS |
| 11 | Same text, different vectors (chunk 500-519) | 20 | 20 | PASS |
| 12 | Boilerplate prefix rows (chunk 600-699) | 100 | 100 | PASS |
| 13 | Documents | 1000 | 1000 | PASS |
| 14 | Non-null vectors | 4988 | 4988 | PASS |
| 15 | Search corpus rows (`chunk_id >= 42 AND embedding IS NOT NULL`) | 4959 | 4959 | PASS |
| 16 | Vector dimensions (min) | 64 | 64 | PASS |
| 17 | Vector dimensions (max) | 64 | 64 | PASS |
| 18 | Search queries | 5 | 5 | PASS |

Setup summary result (guide §6.2 final SELECT): total_rows 5000,
non_null_vectors 4988, min/max dimensions 64/64, min_norm2 0.0,
max_norm2 4.9223264451224198 (chunk 41, the largest planted outlier).

### Duplicate-count nuance (not a discrepancy)

The guide's "12 groups / 37 rows" refers to the **planted** duplicate groups
(leaders chunk 100-111 + 25 copies at 200-224, tracked by `duplicate_group`).
A naive whole-table scan for byte-equal vectors additionally finds the zero-vector
class (1 group / 4 rows) and the near-zero class (1 group / 8 rows), i.e.
**14 groups / 49 rows** — confirmed live by result set 2 of
`vectorlab_groundtruth.sql`. A Profile implementation that reports zero/near-zero
rows under their own findings will report 12/37 for the duplicate finding.

## Discrepancies against the live server

1. **`sys.vector_indexes.distance_metric_desc` does not exist on 17.0.1000.7 RTM.**
   The guide's probe (§5) and index-version query (§8.3) select
   `vi.distance_metric_desc`; this build exposes `distance_metric` (varchar) and
   `vector_index_type` instead. The verbatim statement fails with
   `Msg 207 ... Invalid column name 'distance_metric_desc'`. The guide's SQL was
   kept as written per its own rule that runtime probes are the source of truth;
   the probe file isolates the statement in its own batch so the other six probe
   sections still run.
2. **`sys.dm_db_vector_indexes` is absent on 17.0.1000.7 RTM.** The probe's
   `IF OBJECT_ID(...) IS NOT NULL` guard correctly skips the health-DMV block
   (no error, no result set).
3. **`ALLOW_STALE_VECTOR_INDEX` is not present in `sys.database_scoped_configurations`
   on this build** — the probe's filtered query returned only `PREVIEW_FEATURES`
   (value 0, default). Informational; the query itself runs fine.

No data-generation counts differed from the guide; nothing was tweaked to force a
match.

## Probe facts observed on this server (2026-07-11)

- ProductVersion 17.0.1000.7, ProductLevel RTM, Enterprise Developer Edition (64-bit),
  EngineEdition 3, database VectorLab, compatibility_level 170.
- `PREVIEW_FEATURES` = 0 (default). `external rest endpoint enabled` = 0,
  `external AI runtimes enabled` = 0.
- Native vector columns: `dbo.VectorLabChunks.embedding` VECTOR(64) float32 NULL;
  `dbo.VectorLabSearchCorpus.embedding` VECTOR(64) float32 NOT NULL.
- `sys.external_models` exists; zero models defined.
