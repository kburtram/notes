# Vector/UDT provider behavior — evidence matrix (DA PR 3a / r02 P0-3)

Records live provider behavior for the STS2 read pattern (`SequentialAccess` + the exact
read calls used by `SqlClientSession.PumpResultSetAsync`). Dimension-metadata rules and the
D-0018/D-0019 transport were frozen against the VERIFIED rows only; unverified cells are
CI follow-ups, not assumed.

## Environment matrix

| RID / OS | SQL Server | Provider | Status |
|---|---|---|---|
| win-x64 (Windows 11 Enterprise 10.0.26200) | SQL Server 2025 17.0.1000.7 (local, shared memory) | Microsoft.Data.SqlClient 6.1.5 (Packages.props:86) | **VERIFIED 2026-07-11** |
| linux-x64 | SQL Server 2025 (container) | Microsoft.Data.SqlClient 6.1.5 | UNVERIFIED — CI/nightly follow-up (engine tests are RID-agnostic; run `SqlClientEngineTests` with `STS2_SQLSERVER_CONNSTRING` on the Linux lane) |
| osx-arm64 | n/a | Microsoft.Data.SqlClient 6.1.5 | UNVERIFIED — same follow-up |
| win-x64 vs Azure SQL Database | Azure SQL Database (SQL Azure 12.0.2000.8, EngineEdition 5, GP_S_Gen5_1 serverless, db `ninjadb`, compat 150 raised to 170) | Microsoft.Data.SqlClient 6.1.5 | **VERIFIED 2026-07-11** — all 5 `SqlClientEngineTests` pass live against Azure, incl. D-0018 `VectorReadsAsJsonTextByDefaultAndTypedWhenNegotiated` (277ms) and D-0019 `ClrUdtColumnsTransportAsBinaryInsteadOfFailingTheQuery` (1s); VectorLab rebuilt in schema `vectorlab` (`_build/sql/vectorlab_setup_azure.sql`), all 18 ground-truth checks PASS; surface deltas in the Azure section below |

## Verified behaviors (win-x64, SQL 2025, M.D.S 6.1.5)

| Behavior | Evidence |
|---|---|
| `vector(n)` + `GetValue` under SequentialAccess → boxed `Microsoft.Data.SqlTypes.SqlVector<float>` | r09 probe (scratchpad/typeprobe, 2026-07-11) + `VectorReadsAsJsonTextByDefaultAndTypedWhenNegotiated` (44ms live) |
| `vector(n)` + `GetChars` → JSON array text, float32 shortest-round-trip precision | r09 probe: `[0.1,0.3,1.1754944E-38,3.4028235E+38,-0.00012345679]`; live test parses text back to exact floats |
| `SqlVector<float>` `.Length`/`.Memory` consistent; LE byte conversion via `BinaryPrimitives` round-trips exactly | live test decodes `[1.5,-2.5,3.25]` byte-exact |
| Vector `ColumnSize` (→ wire `length`) = 8 + 4×dims (vector(3) → 20) | r09 probe + live test asserts `Length == 20` |
| `DataTypeName` for vector = `vector` (bare) | classify switch keys on exact `"vector"`; live test passes through `ClassifyColumns` |
| UDT `DataTypeName` is db-qualified 3-part (`master.sys.geometry`) | r09 probe; suffix match in `SqlLargeValueReader.IsClrUdt` |
| UDT `GetValue` throws `FileNotFoundException` (Microsoft.SqlServer.Types) failing the whole query | r09 probe [VERIFIED-LIVE]; motivates D-0018 binary classify |
| UDT chunked `GetBytes` under SequentialAccess works; geometry Point = 22 bytes, `SRID int32 LE + 0x01 + ...` (geography Point SRID 4326 → `E6 10 00 00`) | r09 probe + `ClrUdtColumnsTransportAsBinaryInsteadOfFailingTheQuery` (250ms live) |
| NULL vector → ordinary `IsDBNull` null both modes | live test |
| float16 vector base type | UNVERIFIED — preview feature not provisioned locally; v1 policy: text fallback when the provider yields a string, else `unsupportedBaseType` sentinel (fails honest, never wrong) |

## ANN / index surface — SQL Server 2025 RTM 17.0.1000.7 (VERIFIED LIVE 2026-07-11)

| Behavior | Result |
|---|---|
| `ALTER DATABASE SCOPED CONFIGURATION SET PREVIEW_FEATURES = ON` | Works (VectorLab now ON) |
| `CREATE VECTOR INDEX … WITH (METRIC='cosine', TYPE='diskann')` | Works — but requires `QUOTED_IDENTIFIER ON` (sqlcmd needs `-I`; error 1934 otherwise). Built on 4,959-row corpus. |
| `sys.vector_indexes` columns | `vector_index_type` ("DiskANN"), `distance_metric` ("COSINE"), `build_parameters` = `{"StartId","L","M","R"}` — **NO `$.Version` key** (guide's `JSON_VALUE(build_parameters,'$.Version')` version detection finds nothing on RTM) |
| `VECTOR_SEARCH(TABLE=…, COLUMN=…, SIMILAR_TO=…, METRIC=…, TOP_N=n)` TVF | **WORKS** (returns neighbors + `distance`) — the guide called this the "earlier/deprecated" form |
| `SELECT TOP (n) WITH APPROXIMATE …` | **REJECTED** — Msg 102 syntax error — the guide called this the "current" form; RTM does not accept it |
| `OPTION (USE HINT('FORCE_ANN_ONLY'))` | **REJECTED** — Msg 10715 "not a valid hint" — the spec's forced-ANN proof mechanism is unavailable on RTM; on this build the Search evidence ladder must fall back to plan inspection or the honest "Approximate requested, strategy unverified" label |

Consequence for VEC-7/VEC-8: syntax probes (DA A8) are NOT optional — the guide's
assumed current/legacy split is inverted on RTM. The `VectorSqlBuilder` must key
templates off probe results per connection, and the evidence taxonomy's
"strategy unverified" state is the RTM reality until a provable forcing
mechanism exists.

## Azure SQL vs SQL25 RTM surface differences (VERIFIED LIVE 2026-07-11)

Environment: Azure SQL Database `ninjadb`, GP_S_Gen5_1 (General Purpose serverless,
1 vCore), SQL Azure 12.0.2000.8, EngineEdition 5, ProductLevel RTM. Database compat
level was 150 at first contact; `vectorlab_setup_azure.sql` raised it to 170 (see the
compat/batch quirk below). VectorLab corpus rebuilt byte-faithfully under schema
`vectorlab`; **all 18 ground-truth checks PASS with the same expected counts as RTM**
(12 null / 4 zero / 8 near-zero / 17 high-norm / 12 groups 37 rows / 0 unequal groups /
50 stale / 50 provenance / 20 same-text / 100 boilerplate / 1000 docs / 5000 rows /
4988 non-null / 4959 corpus / 64/64 dims / 5 queries), and the informational full-scan
duplicate census is identical (14 groups / 49 rows).

| Surface | SQL Server 2025 RTM 17.0.1000.7 (local) | Azure SQL Database (2026-07-11) |
|---|---|---|
| Engine identity | ProductVersion 17.0.1000.7, EngineEdition 3 | ProductVersion **12.0.2000.8**, EngineEdition **5**, Edition `SQL Azure` |
| VECTOR type + `VECTORPROPERTY`/`VECTOR_NORM`/`VECTOR_NORMALIZE`/`VECTOR_DISTANCE` | Work at compat 170 | Work — **even at compat 150** (all four probed OK before the raise); `VECTORPROPERTY` returns `Dimensions=3 BaseType=float32` for `CAST('[1,2,3]' AS VECTOR(3))` |
| `sys.columns.vector_dimensions` / `vector_base_type` / `vector_base_type_desc` | Present | Present (same) |
| `sys.vector_indexes` shape | `vector_index_type` + `distance_metric`, NOT `distance_metric_desc` | Same — full 23-column list recorded: 20 `sys.indexes`-style columns (`object_id`…`auto_created`) + `vector_index_type`, `distance_metric`, `build_parameters` |
| `sys.vector_indexes.build_parameters` | `{"StartId","L","M","R"}` — **no `$.Version` key** | `{"StartId":"0", "L":"48", "R":"48", "Version":"3"}` — **has `Version` (= 3), no `M`** — the guide's `JSON_VALUE(build_parameters,'$.Version')` works on Azure only |
| `sys.dm_db_vector_indexes` | **Absent** | **Present**, 10 columns — and the guide's assumed names differ: `graph_catchup_pending_percent` (not `approximate_staleness_percent`), `last_background_task_execution_time` (not `last_background_task_time`); the guide's health query would fail Msg 207 on Azure too |
| `ALLOW_STALE_VECTOR_INDEX` db-scoped config | **Absent** from `sys.database_scoped_configurations` | **Present** (value 0, default) |
| `PREVIEW_FEATURES` db-scoped config | Present, 0 default | Present, 0 default (same) |
| `sys.external_models` | Exists | Exists — 12-column shape recorded; `parameters` column is native **`json`** type |
| `sys.configurations` `external rest endpoint enabled` / `external AI runtimes enabled` | 0 / 0 | **1** / 0 (`sp_invoke_external_rest_endpoint` surface enabled by default on Azure) |
| `CREATE VECTOR INDEX … WITH (METRIC=…, TYPE='diskann')` | Works (preview ON, 4,959-row corpus) | Statement accepted **without** `PREVIEW_FEATURES` (also with it); DiskANN `TYPE`, cosine/euclidean `METRIC`, and `MAXDOP` syntax all accepted — but the build **fails reproducibly** with Msg **42234** "DiskANN vector index build failed with an internal error 200" (3 attempts, both metrics, preview ON and OFF) on this GP_S_Gen5_1 tier. Likely tier/resource-related; treat vector-index availability as per-database, not per-engine |
| Failed CREATE VECTOR INDEX residue | n/a (create succeeds) | Failed build leaves a **transient phantom row in `sys.vector_indexes`** (with build_parameters) that is absent from `sys.indexes` and `sys.dm_db_vector_indexes`, unusable by `VECTOR_SEARCH` (42227), not droppable (`DROP INDEX` → 3701), blocks re-`CREATE` in the same window (42230 "already has an existing vector index"), and disappears asynchronously (~a minute) |
| `VECTOR_SEARCH(TABLE=…, COLUMN=…, SIMILAR_TO=…, METRIC=…, TOP_N=n)` | Works with preview ON | **Parse-gated by `PREVIEW_FEATURES`**: preview OFF → Msg 102 syntax error at compat 170 (and at 150); preview ON → parses and binds, then Msg 42227 "Cannot find a vector index with metric …" because no index can be built on this tier. End-to-end ANN **not verifiable** here |
| `SELECT TOP (n) … WITH APPROXIMATE` | REJECTED (Msg 102) | REJECTED (Msg 156/319 — parse error) at compat 150 and 170, preview ON and OFF (same conclusion as RTM) |
| `OPTION (USE HINT('FORCE_ANN_ONLY'))` | REJECTED (Msg 10715) | REJECTED (Msg 10715, identical) |
| `AI_GENERATE_CHUNKS(source=…, chunk_type=FIXED, chunk_size=…)` | not recorded on RTM | Parse-rejected at compat 150 (Msg 102); **works at compat 170 with preview OFF** (returned 4 chunks) |
| `geometry::Point` / `geography::Point` | Standard | Work (`POINT (1 2)` / `POINT (-122.3 47.6)`) — standard, as expected |
| `VECTOR_NORM` low-order bits | setup summary max_norm2 = 4.9223264451224198 | 4.9223265647888184 — differs in the 8th significant digit (within one float32 ulp; a different summation path). Thresholded ground-truth checks unaffected |

Azure-run quirks (harness/script, not engine deltas):

- **Same-batch compat raise does not rescue `GENERATE_SERIES`.** The guide's verbatim
  setup raises compat inside the main batch; on a compat-150 database the batch still
  fails Msg 208 `Invalid object name 'GENERATE_SERIES'` (the ALTER executes, the batch
  was already compiled). `vectorlab_setup_azure.sql` hoists the raise into its own
  earlier batch. Invisible on RTM only because the local VectorLab db was born at 170.
- ODBC sqlcmd defaults `QUOTED_IDENTIFIER OFF`; `CREATE VECTOR INDEX` then fails
  Msg 1934 — pass `-I` (same requirement as the RTM row above).

Consequence: identical conclusion to RTM for VEC-7/VEC-8 — per-connection syntax +
capability probes are mandatory. On Azure additionally: (a) gate ANN on a successful
`sys.vector_indexes`+`sys.dm_db_vector_indexes` join, not on `sys.vector_indexes`
alone (phantom rows); (b) `PREVIEW_FEATURES` gates `VECTOR_SEARCH` parse acceptance;
(c) vector-index availability varies by service tier even when the whole scalar vector
surface works.

## Regeneration recipe

The standalone probe lives at `_build/typeprobe/` (net10.0 console + M.D.S 6.1.5,
`Server=localhost;Integrated Security=true;TrustServerCertificate=true`). `dotnet run`
prints the CLR type, JSON text, byte layouts, and ColumnSize for vector/geometry/
geography/hierarchyid cells. The durable equivalents are the gated live tests in
`test/sts2/.../SqlClientEngineTests.cs` (`VectorReads...`, `ClrUdtColumns...`) — run with
`STS2_SQLSERVER_CONNSTRING` set.
