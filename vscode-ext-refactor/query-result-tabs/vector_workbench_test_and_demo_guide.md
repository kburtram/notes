# Query Studio Vector Workbench - Use, Setup, Test, and Demo Guide

**Status:** Build, evaluation, and demonstration guide  
**Date:** 2026-07-11  
**Audience:** Query Studio developers, SQL Tools Service developers, UX evaluators, test engineers, support engineers, DBAs, retrieval engineers, and coding agents  
**Target products:** SQL Server 2025, Azure SQL Database, Azure SQL Managed Instance where supported, and SQL database in Microsoft Fabric where supported  
**Companion documents:**

- `query_studio_vector_workbench_ux_spec.md`
- `query_studio_vector_workbench_implementation_plan.md`
- `vector_design_addendum.md`
- `vector_ux_revisions.md`
- `vector_workbench_readiness_review_addendum.md`

## 0. What this document delivers

This guide explains:

1. What the Vector Workbench is for.
2. How the SQL vector type, vector functions, vector search, vector indexes, external models, embedding generation, and chunk generation fit together.
3. How to create a deterministic local lab without any AI endpoint.
4. How to configure an optional remote or local embedding model.
5. How to populate tables with synthetic or real embeddings.
6. How to exercise every visible Vector Workbench workspace.
7. Which scenarios are suitable for live database demonstrations and which require a test harness or mocked capability fixture.
8. What each test proves and why a DBA, developer, or retrieval engineer would care.
9. How to evaluate correctness, privacy, cancellation, performance, accessibility, and degraded-permission behavior.

The scripts are intentionally split into tracks. The fast synthetic track exercises Profile, Compare, Projection, exact Search, binding, sampling, and most error states without sending data anywhere. The endpoint track exercises Pipeline, text-to-vector Search, re-embedding, model-call confirmation, chunk embedding, and model drift. The index track exercises approximate search and Index diagnostics only on targets that advertise the required capabilities.

## 1. What the feature is used for

The Vector Workbench is a result-pane debugger for vector-bearing SQL results. It is not merely a scatterplot and it is not a replacement for the normal Results grid.

It helps answer six families of questions.

### 1.1 Are the stored vectors structurally healthy?

Profile helps find:

- null, unavailable, zero, and near-zero vectors;
- unexpected norm distributions;
- exact duplicates and near duplicates;
- low-variance dimensions;
- outliers;
- mixed provenance;
- stale embeddings;
- group-specific distribution changes;
- duplicated boilerplate or chunk crowding.

### 1.2 Why did this vector rank near or far from another?

Compare helps examine:

- cosine, Euclidean, and negative dot distances;
- vector norms;
- top component differences;
- top metric contributions;
- pairwise matrices;
- centroids and medoids;
- local vector arithmetic;
- nearest bound rows to a local expression result.

### 1.3 Is approximate retrieval returning the same useful neighbors as exact retrieval?

Search helps compare:

- exact ground truth;
- optimizer-selected approximate search;
- forced ANN where supported;
- recall at K;
- overlap and rank movement;
- exact-only and approximate-only rows;
- filter semantics;
- index-version behavior;
- index staleness at run time;
- generated SQL and execution evidence.

### 1.4 What broad structure exists in the embedding space?

Projection helps explore:

- category or tenant clusters;
- outliers;
- overlap between groups;
- selected rows and neighborhoods;
- a deterministic PCA representation with explained variance;
- the difference between projected coordinates and original-space distance.

### 1.5 Is the vector index present, compatible, current, and maintainable?

Index helps inspect:

- DiskANN index presence;
- metric compatibility;
- index version;
- current versus earlier format behavior;
- health DMV facts;
- approximate staleness;
- background maintenance;
- creation prerequisites and limitations;
- generated create, migration, health, and configuration scripts.

### 1.6 Was the embedding pipeline configured and executed correctly?

Pipeline helps investigate:

- source text provenance;
- external model configuration;
- egress path;
- model output dimensions;
- stored-versus-fresh embedding drift;
- changed preprocessing;
- chunk size and overlap;
- source text changed after embedding;
- repeated generation across chunks;
- remote-call failures, retry, and cancellation.

## 2. SQL feature map

### 2.1 Native vector type

A column can be declared as:

```sql
embedding VECTOR(1536)
```

The default base type is float32. SQL Server stores it in an optimized binary representation and exposes JSON conversion for compatibility. The maximum dimension count for the documented native type is 1,998. Half-precision float16 exists as a preview feature and currently has different driver-transport behavior, so this guide uses float32 unless a specific float16 test says otherwise.

### 2.2 Core vector functions

The most relevant functions are:

```sql
VECTORPROPERTY(embedding, 'Dimensions')
VECTORPROPERTY(embedding, 'BaseType')
VECTOR_NORM(embedding, 'norm1')
VECTOR_NORM(embedding, 'norm2')
VECTOR_NORM(embedding, 'norminf')
VECTOR_NORMALIZE(embedding, 'norm2')
VECTOR_DISTANCE('cosine', embedding, @query_vector)
VECTOR_DISTANCE('euclidean', embedding, @query_vector)
VECTOR_DISTANCE('dot', embedding, @query_vector)
```

`VECTOR_DISTANCE` is exact and does not use a vector index. It is the natural ground truth for an approximate-recall experiment.

### 2.3 Approximate search and vector indexes

Approximate retrieval is performed with `VECTOR_SEARCH`. Syntax and semantics vary by index version and target. Current-format indexes use `SELECT TOP (N) WITH APPROXIMATE`; earlier indexes retain the deprecated `TOP_N` argument and use post-filter behavior. `FORCE_ANN_ONLY` can prove that an ANN index path was used when the target supports the hint and all requirements are met.

Do not paste one approximate-search template into every target. The Workbench must probe the actual connection and index version.

### 2.4 External models and embedding generation

An external model object stores:

- endpoint or local runtime location;
- API format;
- model type;
- provider model name;
- credential reference;
- optional parameters such as dimensions and retry count.

The object is named at database scope. It is not schema-qualified.

`AI_GENERATE_EMBEDDINGS` generates an embedding from character input by using a precreated external model object.

### 2.5 Chunk generation

`AI_GENERATE_CHUNKS` is a table-valued function. In the current documented surface, fixed chunking uses character counts, not tokenizer counts. `OVERLAP` is a percentage from 0 through 50. The function returns chunk text, order, offset, length, and optionally a chunk-set ID.

## 3. Capability and safety rules before running the lab

### 3.1 Use a disposable database

Run this guide in a development or test database. Several optional scenarios deliberately create duplicates, stale embeddings, RLS policies, vector indexes, and model calls. Do not point the scripts at production tables.

### 3.2 Keep endpoint calls opt-in

The synthetic lab makes no model calls. The endpoint track is separate and clearly marked. Read the generated T-SQL and the model-call confirmation before executing any endpoint-backed statement.

### 3.3 Preview and platform variability

The native float32 vector type and exact vector functions are broadly available on the documented SQL Server 2025 family. Approximate search, vector indexes, float16, and AI features can be preview-gated or vary by platform, region, edition, and index version.

Treat runtime probes as the source of truth.

### 3.4 Minimum row requirement for an index

The current documented vector-index surface requires at least 100 rows with non-null vector values before index creation. The synthetic lab creates 5,000 rows, with more than enough non-null values.

### 3.5 Security context

Run diagnostic queries with the same effective principal that owns the user workflow. Do not grant the Workbench a privileged connection that bypasses row-level security or sees metadata the user cannot see.

## 4. Track overview

| Track | Network or model calls | Main workspaces exercised | Expected duration |
| --- | --- | --- | --- |
| A. Synthetic local corpus | None | Profile, Compare, Projection, exact Search, detached mode | A few minutes |
| B. Vector index and ANN | None, but target capability required | Search, Index | Depends on index build |
| C. External embedding model | Remote, host-local, or ONNX depending configuration | Pipeline, text Search, drift | Depends on endpoint and row count |
| D. Security and lifecycle | None by default | Permission states, RLS, cancel, pinned results | A few minutes |
| E. Harness-only edge fixtures | None in product; test transport may be synthetic | Non-finite, truncation, legacy index, protocol errors | Automated test suite |

## 5. Capability probe script

Run this first. It produces factual rows that should correspond to the capability popover and Index workspace.

```sql
SET NOCOUNT ON;

SELECT
    SERVERPROPERTY('ProductVersion') AS product_version,
    SERVERPROPERTY('ProductLevel') AS product_level,
    SERVERPROPERTY('Edition') AS edition,
    SERVERPROPERTY('EngineEdition') AS engine_edition,
    DB_NAME() AS database_name,
    d.compatibility_level
FROM sys.databases AS d
WHERE d.database_id = DB_ID();

SELECT
    name,
    value,
    value_for_secondary,
    is_value_default
FROM sys.database_scoped_configurations
WHERE name IN (N'PREVIEW_FEATURES', N'ALLOW_STALE_VECTOR_INDEX')
ORDER BY name;

SELECT
    name,
    value,
    value_in_use
FROM sys.configurations
WHERE name IN
(
    N'external rest endpoint enabled',
    N'external AI runtimes enabled'
)
ORDER BY name;

SELECT
    s.name AS schema_name,
    o.name AS object_name,
    c.column_id,
    c.name AS column_name,
    t.name AS type_name,
    c.vector_dimensions,
    c.vector_base_type,
    c.vector_base_type_desc,
    c.is_nullable
FROM sys.columns AS c
JOIN sys.objects AS o
    ON o.object_id = c.object_id
JOIN sys.schemas AS s
    ON s.schema_id = o.schema_id
JOIN sys.types AS t
    ON t.user_type_id = c.user_type_id
WHERE c.vector_dimensions IS NOT NULL
ORDER BY s.name, o.name, c.column_id;

IF OBJECT_ID(N'sys.external_models') IS NOT NULL
BEGIN
    SELECT
        em.name AS external_model_name,
        USER_NAME(em.principal_id) AS owner_name,
        em.api_format,
        em.model_type_desc,
        em.model AS provider_model,
        em.location,
        em.parameters,
        em.create_time,
        em.modify_time
    FROM sys.external_models AS em
    ORDER BY em.name;
END;

-- CORRECTED to live server symbols (verified 2026-07-11 on SQL Server 2025
-- RTM 17.0.1000.7 AND Azure SQL DB; see _build/evidence/vector-provider-matrix.md):
-- sys.vector_indexes exposes `distance_metric` + `vector_index_type` — there
-- is NO `distance_metric_desc` on either environment (Msg 207). The
-- `$.Version` key in build_parameters exists on Azure only (RTM emits
-- {StartId,L,M,R} with no Version). Probes must tolerate both shapes.
IF OBJECT_ID(N'sys.vector_indexes') IS NOT NULL
BEGIN
    SELECT
        s.name AS schema_name,
        t.name AS table_name,
        i.name AS index_name,
        vi.vector_index_type,
        vi.distance_metric,
        JSON_VALUE(vi.build_parameters, '$.Version') AS index_version, -- NULL on RTM
        vi.build_parameters
    FROM sys.vector_indexes AS vi
    JOIN sys.indexes AS i
        ON i.object_id = vi.object_id
        AND i.index_id = vi.index_id
    JOIN sys.tables AS t
        ON t.object_id = vi.object_id
    JOIN sys.schemas AS s
        ON s.schema_id = t.schema_id
    ORDER BY s.name, t.name, i.name;
END;

-- CORRECTED: the health DMV is ABSENT on SQL 2025 RTM (the OBJECT_ID guard
-- skips it, honestly = "current snapshot only" health state) and on Azure its
-- REAL columns differ from earlier drafts of this guide — verified names
-- include `graph_catchup_pending_percent` (not approximate_staleness_percent)
-- and `last_background_task_execution_time` (not last_background_task_time).
-- The tolerant projection below works on any shape; the Workbench product
-- code resolves exact column names per connection via sys.all_columns.
IF OBJECT_ID(N'sys.dm_db_vector_indexes') IS NOT NULL
BEGIN
    BEGIN TRY
        SELECT
            s.name AS schema_name,
            t.name AS table_name,
            i.name AS index_name,
            dvi.*
        FROM sys.dm_db_vector_indexes AS dvi
        JOIN sys.indexes AS i
            ON i.object_id = dvi.object_id
            AND i.index_id = dvi.index_id
        JOIN sys.tables AS t
            ON t.object_id = dvi.object_id
        JOIN sys.schemas AS s
            ON s.schema_id = t.schema_id
        ORDER BY s.name, t.name, i.name;
    END TRY
    BEGIN CATCH
        SELECT
            ERROR_NUMBER() AS health_dmv_error_number,
            ERROR_MESSAGE() AS health_dmv_error_message;
    END CATCH;
END;
```

### What this proves

- Which engine and compatibility level the Workbench is attached to.
- Whether preview gates are visible and enabled.
- Whether remote REST and local AI runtime server gates are enabled.
- Which native vector columns exist and their dimensions/base type.
- Which external models are visible to the current principal.
- Which vector indexes exist and which format version they report.
- Whether the health DMV is present and readable.

## 6. Track A - deterministic synthetic corpus

### 6.1 Why a synthetic corpus is necessary

A real embedding endpoint is excellent for Pipeline tests, but it is a poor foundation for deterministic UI acceptance. Model output can change, endpoint availability can vary, calls cost money, and exact numeric findings are difficult to freeze.

The synthetic corpus below deliberately creates:

- five visible category clusters;
- unit-normalized baseline vectors;
- a wider Legal cluster;
- low-variance trailing dimensions;
- null, zero, and near-zero vectors;
- high-norm outliers;
- exact duplicate groups;
- duplicated source text with different vectors;
- shared boilerplate;
- stale source text after embedding;
- mixed provenance labels with the same dimensions;
- tenant, language, category, document, and chunk keys.

The vectors are not claimed to be meaningful language embeddings. They are a stable numerical fixture designed to exercise the Workbench honestly.

### 6.2 Create the lab schema and data

Run in a disposable SQL Server 2025 or Azure SQL database.

```sql
SET NOCOUNT ON;
SET XACT_ABORT ON;

IF (SELECT compatibility_level FROM sys.databases WHERE database_id = DB_ID()) < 170
BEGIN
    DECLARE @compat_sql nvarchar(max) =
        N'ALTER DATABASE ' + QUOTENAME(DB_NAME()) + N' SET COMPATIBILITY_LEVEL = 170;';
    EXEC sys.sp_executesql @compat_sql;
END;

DROP TABLE IF EXISTS dbo.VectorLabExpectedRelevant;
DROP TABLE IF EXISTS dbo.VectorLabSearchQueries;
DROP TABLE IF EXISTS dbo.VectorLabSearchCorpus;
DROP TABLE IF EXISTS dbo.VectorLabChunks;
DROP TABLE IF EXISTS dbo.VectorLabDocuments;

CREATE TABLE dbo.VectorLabDocuments
(
    document_id int NOT NULL,
    tenant_id int NOT NULL,
    category_code tinyint NOT NULL,
    category nvarchar(32) NOT NULL,
    language_code char(2) NOT NULL,
    title nvarchar(200) NOT NULL,
    body nvarchar(max) NOT NULL,
    source_modified_at datetime2(3) NOT NULL,
    CONSTRAINT PK_VectorLabDocuments
        PRIMARY KEY CLUSTERED (document_id)
);

CREATE TABLE dbo.VectorLabChunks
(
    chunk_id int NOT NULL,
    document_id int NOT NULL,
    tenant_id int NOT NULL,
    category_code tinyint NOT NULL,
    category nvarchar(32) NOT NULL,
    language_code char(2) NOT NULL,
    chunk_order int NOT NULL,
    label nvarchar(200) NOT NULL,
    chunk_text nvarchar(max) NOT NULL,
    source_modified_at datetime2(3) NOT NULL,
    embedded_at datetime2(3) NULL,
    embedding_model nvarchar(128) NULL,
    embedding_profile nvarchar(128) NULL,
    embedding_batch_id int NULL,
    duplicate_group int NULL,
    embedding VECTOR(64) NULL,
    CONSTRAINT PK_VectorLabChunks
        PRIMARY KEY CLUSTERED (chunk_id),
    CONSTRAINT FK_VectorLabChunks_Document
        FOREIGN KEY (document_id)
        REFERENCES dbo.VectorLabDocuments(document_id)
);

INSERT dbo.VectorLabDocuments
(
    document_id,
    tenant_id,
    category_code,
    category,
    language_code,
    title,
    body,
    source_modified_at
)
SELECT
    n.value AS document_id,
    1 + ((n.value - 1) % 4) AS tenant_id,
    1 + ((n.value - 1) % 5) AS category_code,
    CASE 1 + ((n.value - 1) % 5)
        WHEN 1 THEN N'Technical'
        WHEN 2 THEN N'Billing'
        WHEN 3 THEN N'Legal'
        WHEN 4 THEN N'Support'
        ELSE N'Other'
    END AS category,
    CASE WHEN n.value % 7 = 0 THEN 'fr' ELSE 'en' END AS language_code,
    CONCAT(
        CASE 1 + ((n.value - 1) % 5)
            WHEN 1 THEN N'Technical operations guide '
            WHEN 2 THEN N'Billing and refund policy '
            WHEN 3 THEN N'Legal and compliance memo '
            WHEN 4 THEN N'Support troubleshooting article '
            ELSE N'General company reference '
        END,
        n.value
    ) AS title,
    CONCAT(
        N'Document ', n.value, N'. ',
        CASE 1 + ((n.value - 1) % 5)
            WHEN 1 THEN N'This document covers authentication, failover, API reliability, monitoring, and deployment practices. '
            WHEN 2 THEN N'This document covers invoices, refunds, annual plans, proration, credits, and payment processing. '
            WHEN 3 THEN N'This document covers data residency, retention, privacy, contracts, audit, and compliance obligations. '
            WHEN 4 THEN N'This document covers incidents, troubleshooting, escalation, service recovery, and customer support. '
            ELSE N'This document covers people, facilities, product terminology, and general operational references. '
        END,
        REPLICATE(N'Additional deterministic reference text for chunking and retrieval evaluation. ', 20)
    ) AS body,
    DATEADD(minute, n.value, CONVERT(datetime2(3), '2026-01-01T00:00:00'))
FROM GENERATE_SERIES(1, 1000) AS n;

INSERT dbo.VectorLabChunks
(
    chunk_id,
    document_id,
    tenant_id,
    category_code,
    category,
    language_code,
    chunk_order,
    label,
    chunk_text,
    source_modified_at,
    embedded_at,
    embedding_model,
    embedding_profile,
    embedding_batch_id
)
SELECT
    ((d.document_id - 1) * 5) + s.value AS chunk_id,
    d.document_id,
    d.tenant_id,
    d.category_code,
    d.category,
    d.language_code,
    s.value AS chunk_order,
    CONCAT(d.title, N' - chunk ', s.value) AS label,
    CONCAT(
        d.title, N'. Chunk ', s.value, N'. ',
        CASE d.category_code
            WHEN 1 THEN N'Reset MFA devices, rotate API keys, investigate latency, configure SSO, and verify regional failover. '
            WHEN 2 THEN N'Refund annual plans, issue credits, validate invoices, calculate proration, and reconcile payment disputes. '
            WHEN 3 THEN N'Apply retention rules, verify GDPR deletion, preserve audit records, and enforce regional data residency. '
            WHEN 4 THEN N'Run incident response, gather logs, retry webhooks, escalate severity, and restore customer service. '
            ELSE N'Maintain reference data, update product terminology, coordinate facilities, and publish internal guidance. '
        END,
        N'Document key ', d.document_id, N'; tenant ', d.tenant_id, N'; language ', d.language_code, N'. ',
        SUBSTRING(d.body, 1 + ((s.value - 1) * 240), 520)
    ) AS chunk_text,
    d.source_modified_at,
    DATEADD(second, 30, d.source_modified_at) AS embedded_at,
    N'SyntheticClusterModel64' AS embedding_model,
    N'passage-prefix-v1|unit-norm' AS embedding_profile,
    1 AS embedding_batch_id
FROM dbo.VectorLabDocuments AS d
CROSS JOIN GENERATE_SERIES(1, 5) AS s;

;WITH Dims AS
(
    SELECT value AS dim
    FROM GENERATE_SERIES(1, 64)
),
Components AS
(
    SELECT
        c.chunk_id,
        d.dim,
        CAST
        (
              CASE WHEN d.dim = c.category_code THEN 2.00 ELSE 0.00 END
            + CASE WHEN d.dim = 5 + c.category_code THEN 0.80 ELSE 0.00 END
            + CASE WHEN d.dim = 10 + c.tenant_id THEN 0.35 ELSE 0.00 END
            + CASE WHEN d.dim = 15 + c.chunk_order THEN 0.20 ELSE 0.00 END
            + CASE
                WHEN d.dim BETWEEN 21 AND 28
                 AND d.dim = 21 + (c.document_id % 8)
                    THEN 0.25
                ELSE 0.00
              END
            + CASE
                WHEN d.dim BETWEEN 61 AND 64
                    THEN d.dim * 0.0000001
                ELSE 0.00
              END
            +
              (
                  ((ABS(CHECKSUM(CONCAT(c.chunk_id, N':', d.dim))) % 2001) - 1000)
                  * CASE WHEN c.category = N'Legal' THEN 0.00005 ELSE 0.00002 END
              )
            AS float
        ) AS component
    FROM dbo.VectorLabChunks AS c
    CROSS JOIN Dims AS d
),
VectorJson AS
(
    SELECT
        chunk_id,
        '[' + STRING_AGG(CONVERT(varchar(64), component, 3), ',')
            WITHIN GROUP (ORDER BY dim) + ']' AS vector_json
    FROM Components
    GROUP BY chunk_id
)
UPDATE c
SET c.embedding = VECTOR_NORMALIZE(CAST(v.vector_json AS VECTOR(64)), 'norm2')
FROM dbo.VectorLabChunks AS c
JOIN VectorJson AS v
    ON v.chunk_id = c.chunk_id;

DECLARE @zero_vector varchar(max);
DECLARE @near_zero_vector varchar(max);

SELECT @zero_vector =
    '[' + STRING_AGG('0', ',') WITHIN GROUP (ORDER BY value) + ']'
FROM GENERATE_SERIES(1, 64);

SELECT @near_zero_vector =
    '[' + STRING_AGG
    (
        CASE WHEN value = 1 THEN '0.0000001' ELSE '0' END,
        ','
    ) WITHIN GROUP (ORDER BY value) + ']'
FROM GENERATE_SERIES(1, 64);

-- Null vectors: 12 rows.
UPDATE dbo.VectorLabChunks
SET embedding = NULL,
    embedded_at = NULL
WHERE chunk_id BETWEEN 1 AND 12;

-- Exact zero vectors: 4 rows.
UPDATE dbo.VectorLabChunks
SET embedding = CAST(@zero_vector AS VECTOR(64))
WHERE chunk_id BETWEEN 13 AND 16;

-- Near-zero vectors: 8 rows.
UPDATE dbo.VectorLabChunks
SET embedding = CAST(@near_zero_vector AS VECTOR(64))
WHERE chunk_id BETWEEN 17 AND 24;

-- High-norm outliers: 17 rows. These are intentionally not normalized.
;WITH Dims AS
(
    SELECT value AS dim
    FROM GENERATE_SERIES(1, 64)
),
Components AS
(
    SELECT
        c.chunk_id,
        d.dim,
        CAST
        (
            CASE
                WHEN d.dim = 1 THEN 4.5 + (c.chunk_id * 0.01)
                WHEN d.dim = 2 THEN 0.25
                ELSE ((ABS(CHECKSUM(CONCAT(N'outlier:', c.chunk_id, N':', d.dim))) % 101) - 50) * 0.001
            END
            AS float
        ) AS component
    FROM dbo.VectorLabChunks AS c
    CROSS JOIN Dims AS d
    WHERE c.chunk_id BETWEEN 25 AND 41
),
VectorJson AS
(
    SELECT
        chunk_id,
        '[' + STRING_AGG(CONVERT(varchar(64), component, 3), ',')
            WITHIN GROUP (ORDER BY dim) + ']' AS vector_json
    FROM Components
    GROUP BY chunk_id
)
UPDATE c
SET c.embedding = CAST(v.vector_json AS VECTOR(64))
FROM dbo.VectorLabChunks AS c
JOIN VectorJson AS v
    ON v.chunk_id = c.chunk_id;

-- Twelve duplicate groups covering 37 rows in total:
-- 12 leaders plus 25 copied members.
UPDATE dbo.VectorLabChunks
SET duplicate_group = chunk_id - 99
WHERE chunk_id BETWEEN 100 AND 111;

;WITH Targets AS
(
    SELECT
        c.chunk_id,
        1 + ((c.chunk_id - 200) % 12) AS duplicate_group
    FROM dbo.VectorLabChunks AS c
    WHERE c.chunk_id BETWEEN 200 AND 224
)
UPDATE target
SET target.embedding = leader.embedding,
    target.duplicate_group = t.duplicate_group
FROM dbo.VectorLabChunks AS target
JOIN Targets AS t
    ON t.chunk_id = target.chunk_id
JOIN dbo.VectorLabChunks AS leader
    ON leader.chunk_id = 99 + t.duplicate_group;

-- Source text changed after embedding: 50 stale rows.
UPDATE dbo.VectorLabChunks
SET chunk_text = CONCAT(chunk_text, N' UPDATED AFTER THE STORED EMBEDDING WAS CREATED.'),
    source_modified_at = DATEADD(day, 30, embedded_at)
WHERE chunk_id BETWEEN 300 AND 349;

-- Same dimensions, different declared provenance: 50 rows.
UPDATE dbo.VectorLabChunks
SET embedding_model = N'LegacyModelV1',
    embedding_profile = N'legacy-query-prefix|not-verified',
    embedding_batch_id = 0
WHERE chunk_id BETWEEN 400 AND 449;

-- Same source text, deliberately different vectors: 20 rows.
UPDATE dbo.VectorLabChunks
SET chunk_text = N'This standard confidentiality notice is repeated verbatim across unrelated documents.'
WHERE chunk_id BETWEEN 500 AND 519;

-- Shared boilerplate prefix: 100 rows.
UPDATE dbo.VectorLabChunks
SET chunk_text = CONCAT
(
    N'Copyright and confidentiality notice. Internal use only. ',
    chunk_text
)
WHERE chunk_id BETWEEN 600 AND 699;

-- A clean, indexable search target. The structural anomaly rows 1 through 41
-- stay in VectorLabChunks for Profile, but are excluded from cosine/ANN demos.
CREATE TABLE dbo.VectorLabSearchCorpus
(
    chunk_id int NOT NULL,
    document_id int NOT NULL,
    tenant_id int NOT NULL,
    category nvarchar(32) NOT NULL,
    language_code char(2) NOT NULL,
    chunk_order int NOT NULL,
    label nvarchar(200) NOT NULL,
    chunk_text nvarchar(max) NOT NULL,
    source_modified_at datetime2(3) NOT NULL,
    embedded_at datetime2(3) NULL,
    embedding_model nvarchar(128) NULL,
    embedding_profile nvarchar(128) NULL,
    embedding_batch_id int NULL,
    embedding VECTOR(64) NOT NULL,
    CONSTRAINT PK_VectorLabSearchCorpus
        PRIMARY KEY CLUSTERED (chunk_id)
);

INSERT dbo.VectorLabSearchCorpus
(
    chunk_id, document_id, tenant_id, category, language_code, chunk_order,
    label, chunk_text, source_modified_at, embedded_at,
    embedding_model, embedding_profile, embedding_batch_id, embedding
)
SELECT
    chunk_id, document_id, tenant_id, category, language_code, chunk_order,
    label, chunk_text, source_modified_at, embedded_at,
    embedding_model, embedding_profile, embedding_batch_id, embedding
FROM dbo.VectorLabChunks
WHERE chunk_id >= 42
  AND embedding IS NOT NULL;

CREATE TABLE dbo.VectorLabSearchQueries
(
    query_id int NOT NULL,
    query_name nvarchar(100) NOT NULL,
    source_chunk_id int NOT NULL,
    expected_category nvarchar(32) NOT NULL,
    default_filter nvarchar(200) NULL,
    CONSTRAINT PK_VectorLabSearchQueries
        PRIMARY KEY CLUSTERED (query_id),
    CONSTRAINT FK_VectorLabSearchQueries_Chunk
        FOREIGN KEY (source_chunk_id)
        REFERENCES dbo.VectorLabChunks(chunk_id)
);

INSERT dbo.VectorLabSearchQueries
(query_id, query_name, source_chunk_id, expected_category, default_filter)
VALUES
(1, N'Technical selected-row query', 1001, N'Technical', N'category = Technical'),
(2, N'Billing selected-row query',   1006, N'Billing',   N'category = Billing'),
(3, N'Legal selected-row query',     1011, N'Legal',     N'category = Legal'),
(4, N'Support selected-row query',   1016, N'Support',   N'category = Support'),
(5, N'Other selected-row query',     1021, N'Other',     N'category = Other');

CREATE TABLE dbo.VectorLabExpectedRelevant
(
    query_id int NOT NULL,
    chunk_id int NOT NULL,
    relevance_grade tinyint NOT NULL,
    relevance_reason nvarchar(100) NOT NULL,
    CONSTRAINT PK_VectorLabExpectedRelevant
        PRIMARY KEY CLUSTERED (query_id, chunk_id),
    CONSTRAINT FK_VectorLabExpectedRelevant_Query
        FOREIGN KEY (query_id)
        REFERENCES dbo.VectorLabSearchQueries(query_id),
    CONSTRAINT FK_VectorLabExpectedRelevant_Chunk
        FOREIGN KEY (chunk_id)
        REFERENCES dbo.VectorLabChunks(chunk_id)
);

INSERT dbo.VectorLabExpectedRelevant
(query_id, chunk_id, relevance_grade, relevance_reason)
SELECT
    q.query_id,
    c.chunk_id,
    CASE
        WHEN c.document_id = source.document_id THEN 3
        WHEN c.category = q.expected_category THEN 1
        ELSE 0
    END AS relevance_grade,
    CASE
        WHEN c.document_id = source.document_id THEN N'same document'
        WHEN c.category = q.expected_category THEN N'same category'
        ELSE N'not expected'
    END AS relevance_reason
FROM dbo.VectorLabSearchQueries AS q
JOIN dbo.VectorLabChunks AS source
    ON source.chunk_id = q.source_chunk_id
JOIN dbo.VectorLabSearchCorpus AS c
    ON c.document_id = source.document_id OR c.category = q.expected_category;

SELECT
    COUNT(*) AS total_rows,
    SUM(CASE WHEN embedding IS NOT NULL THEN 1 ELSE 0 END) AS non_null_vectors,
    MIN(VECTORPROPERTY(embedding, 'Dimensions')) AS min_dimensions,
    MAX(VECTORPROPERTY(embedding, 'Dimensions')) AS max_dimensions,
    MIN(VECTOR_NORM(embedding, 'norm2')) AS min_norm2,
    MAX(VECTOR_NORM(embedding, 'norm2')) AS max_norm2
FROM dbo.VectorLabChunks;
```

### 6.3 Expected broad facts

The exact floating-point summaries depend on engine formatting, but the setup deliberately produces these stable row-count facts:

- 5,000 rows.
- 12 null vectors.
- 4 exact zero vectors.
- 8 near-zero vectors.
- 17 high-norm outliers.
- 12 exact duplicate groups covering 37 rows.
- 50 rows whose source text is newer than the stored embedding.
- 50 rows with a different declared model/profile.
- 20 rows with identical source text but different vectors.
- 100 rows with a repeated boilerplate prefix.
- 64-dimensional float32 vectors.

### 6.4 Recommended Workbench binding

Use this table profile:

```text
Profile table          dbo.VectorLabChunks
Search/index table     dbo.VectorLabSearchCorpus
Key column             chunk_id
Display column         label
Vector column          embedding
Source text column     chunk_text
Document key           document_id
Chunk order            chunk_order
Group/color column     category
Tenant column          tenant_id
Language column        language_code
Model column           embedding_model
Profile column         embedding_profile
Embedding batch        embedding_batch_id
Embedded timestamp     embedded_at
Source modified time   source_modified_at
Expected metric        cosine
Expected normalization unit norm for baseline rows
```

The Workbench should mark the profile as user-declared or workspace-local unless it is stored through an approved database metadata convention.

### 6.5 Open a result that exercises detached mode

```sql
SELECT
    chunk_id,
    document_id,
    tenant_id,
    category,
    language_code,
    chunk_order,
    label,
    chunk_text,
    source_modified_at,
    embedded_at,
    embedding_model,
    embedding_profile,
    duplicate_group,
    embedding
FROM dbo.VectorLabChunks
ORDER BY chunk_id;
```

Open Vector. Profile, Compare, and Projection should be usable from the captured result without any new SQL.

## 7. Demo scenarios by workspace

## 7.1 Profile demo P-01 - healthy baseline versus injected anomalies

### Steps

1. Run the full 5,000-row query from section 6.5.
2. Open Vector, then Profile.
3. Confirm the source says `captured result` or `bound table sample` accurately.
4. Use a 5,000-row sample.
5. Open the findings for null, zero, near-zero, duplicate, norm-outlier, low-variance, and freshness cases.

### Expected observations

- Most baseline rows have L2 norm near 1.
- High-norm rows appear as a separate tail or outliers.
- Null, zero, and near-zero counts match the setup.
- Duplicate groups show 12 groups and 37 covered rows.
- The finding drawer says `Affected dimensions` for low-variance dimensions, not `Affected rows`.
- Legal has a wider within-group distance distribution than the other groups.
- Source freshness identifies rows 300 through 349.
- Provenance identifies rows 400 through 449 as dimension-compatible but not provenance-confirmed.

### Why this helps

This is the common first diagnosis when a retrieval system suddenly returns nonsense. It separates transport and pipeline defects from legitimate semantic variation before a developer starts changing index parameters or model prompts.

## 7.2 Profile demo P-02 - duplicate text versus duplicate vectors

### Steps

1. Filter or inspect chunk IDs 100 through 111 and 200 through 224.
2. Open the exact duplicate-vector finding.
3. Inspect chunk IDs 500 through 519 for duplicate source text.

### Expected observations

- The vector duplicate groups contain genuinely byte- or component-equal vectors.
- The repeated source-text rows do not necessarily have equal vectors because their vectors were generated before the text was overwritten.

### Why this helps

A duplicate text finding and a duplicate vector finding imply different failures. Duplicate vectors can indicate copied payloads, a broken embedding batch, or placeholder values. Duplicate text with different vectors can indicate preprocessing, model, or timing differences.

## 7.3 Profile demo P-03 - boilerplate and RAG crowding

### Steps

1. Inspect rows 600 through 699.
2. Run a sampled neighbor-frequency or near-duplicate analysis when available.
3. Compare top-K document diversity with and without these rows.

### Expected observations

- The identical boilerplate prefix increases similarity across unrelated documents.
- Some rows may appear unusually often in neighborhoods.
- Top-K can contain multiple low-value chunks dominated by the notice text.

### Why this helps

Production RAG often fails because repeated headers, navigation, confidentiality notices, or templates dominate embeddings. A global PCA view may not reveal the retrieval crowding clearly.

## 7.4 Compare demo C-01 - three category vectors

Use these rows:

```sql
SELECT
    chunk_id,
    label,
    category,
    embedding
FROM dbo.VectorLabChunks
WHERE chunk_id IN (1001, 1006, 1011)
ORDER BY chunk_id;
```

### Steps

1. Add all three rows to Compare as A, B, and C.
2. Review cosine, Euclidean, negative dot, norms, pairwise matrix, centroid, medoid, and closest pair.
3. Enter `normalize(A + B - C)` in the arithmetic lab.
4. Use the result as a query vector against the bound table.

### Expected observations

- The rows are dimension-compatible.
- Provenance is declared compatible because all three use the same synthetic model/profile.
- Category centroids make distances visibly different.
- Arithmetic output has a new local provenance state rather than inheriting the original model profile blindly.
- Nearest bound rows are labeled as a new server query, not local computation.

### Why this helps

This demonstrates why a vector debugger needs both local math and table-bound retrieval. The expression itself is local; its meaning is tested only when it is searched against real stored rows.

## 7.5 Compare demo C-02 - provenance mismatch with same dimensions

```sql
SELECT
    chunk_id,
    label,
    embedding_model,
    embedding_profile,
    embedding
FROM dbo.VectorLabChunks
WHERE chunk_id IN (451, 401)
ORDER BY chunk_id;
```

### Expected observations

- Both vectors are 64-dimensional float32.
- The tool reports dimension compatibility.
- It does not report verified provenance compatibility.

### Why this helps

One of the most common migration errors is assuming that equal dimensions mean equal embedding spaces. They do not.

## 7.6 Projection demo R-01 - five clusters

### Steps

1. Open the full result.
2. Open Projection.
3. Use PCA 2D, center only.
4. Color by `category`.
5. Display 1,200 points while analyzing 5,000, if the render cap is configured that way.
6. Select and reveal a point from each cluster.

### Expected observations

- Five broad category clusters are visible.
- Legal has more spread.
- The truth banner reports PC1, PC2, and the next component.
- The banner distinguishes analyzed and rendered counts.
- Original-space ranking is not derived from the plotted coordinates.

### Why this helps

Projection is useful for finding broad batch, language, or category structure, but it can manufacture visually persuasive separation. The banner and original-space actions keep the screen from becoming a constellation oracle.

## 7.7 Projection demo R-02 - lasso and outliers

### Steps

1. Lasso the isolated high-norm/outlier region if visible.
2. Add selected points to Compare.
3. Reveal their source rows.
4. Filter the legend to one category without recomputing PCA.

### Expected observations

- Selection is synchronized with the accessible point list.
- Legend filtering hides points but does not silently change the projection coordinates.
- The outliers can be traced back to chunk IDs 25 through 41.

### Why this helps

A projection is only useful in a database tool when a user can travel from shape to row, query, source text, and numerical evidence.

## 7.8 Exact Search demo S-01 - selected-row query

```sql
DECLARE @query_chunk_id int = 1001;
DECLARE @q VECTOR(64) =
(
    SELECT embedding
    FROM dbo.VectorLabSearchCorpus
    WHERE chunk_id = @query_chunk_id
);

SELECT TOP (20)
    c.chunk_id,
    c.document_id,
    c.category,
    c.label,
    VECTOR_DISTANCE('cosine', c.embedding, @q) AS distance
FROM dbo.VectorLabSearchCorpus AS c
WHERE c.chunk_id <> @query_chunk_id
ORDER BY
    VECTOR_DISTANCE('cosine', c.embedding, @q),
    c.chunk_id;
```

### Workbench steps

1. Select row 1001 as the query vector.
2. Set metric Cosine and K 20.
3. Enable exact only.
4. Confirm `Source row excluded by key` appears.
5. Run.

### Expected observations

- The source row does not appear at distance zero.
- Technical rows dominate because of the synthetic category centroid.
- Exact search is labeled ground truth.
- The generated SQL matches the exclusion and metric.

### Why this helps

The test proves basic SQL generation, self-match handling, stable tie-breaking, and exact distance correctness before ANN is introduced.

## 7.9 Exact filtered Search demo S-02 - selective eligibility

```sql
DECLARE @query_chunk_id int = 1001;
DECLARE @q VECTOR(64) =
(
    SELECT embedding
    FROM dbo.VectorLabSearchCorpus
    WHERE chunk_id = @query_chunk_id
);

SELECT TOP (20)
    c.chunk_id,
    c.tenant_id,
    c.category,
    c.label,
    VECTOR_DISTANCE('cosine', c.embedding, @q) AS distance
FROM dbo.VectorLabSearchCorpus AS c
WHERE c.chunk_id <> @query_chunk_id
  AND c.category = N'Technical'
  AND c.tenant_id = 1
ORDER BY
    VECTOR_DISTANCE('cosine', c.embedding, @q),
    c.chunk_id;
```

### Expected observations

- The Workbench reports the structured filter.
- Eligible-row count or filter selectivity is shown when measured.
- If fewer than K rows are eligible, the exact denominator uses the actual row count.

### Why this helps

Many apparent vector-search failures are ordinary eligibility failures. A debugger must distinguish them.

## 8. Track B - vector index and approximate search

### 8.1 Enable preview features only where required

On SQL Server 2025 box, preview features may be required for vector search and vector indexes. On Azure SQL Database or Fabric SQL, use the target's documented capability state.

Review before running:

```sql
ALTER DATABASE SCOPED CONFIGURATION
SET PREVIEW_FEATURES = ON;
```

Do not enable preview features automatically from the Workbench.

### 8.2 Create a vector index

Run only after the capability probe indicates `CREATE VECTOR INDEX` is accepted on the target.

```sql
CREATE VECTOR INDEX IX_VectorLabSearchCorpus_Embedding
ON dbo.VectorLabSearchCorpus(embedding)
WITH
(
    METRIC = 'cosine',
    TYPE = 'diskann'
);
```

### 8.3 Inspect index version

```sql
-- CORRECTED to live server symbols (verified 2026-07-11; see
-- _build/evidence/vector-provider-matrix.md): `distance_metric` (there is no
-- `distance_metric_desc` on RTM or Azure). NOTE version detection reality:
-- Azure build_parameters carries Version ("3"); SQL 2025 RTM has NO Version
-- key ({StartId,L,M,R}) — an absent Version on an RTM-built DiskANN index is
-- the CURRENT format there, so "unknown format" below must NOT be read as
-- legacy. The Workbench classifies via probes, never this literal CASE.
SELECT
    s.name AS schema_name,
    t.name AS table_name,
    i.name AS index_name,
    vi.vector_index_type,
    vi.distance_metric,
    JSON_VALUE(vi.build_parameters, '$.Version') AS index_version,
    CASE
        WHEN TRY_CONVERT(int, JSON_VALUE(vi.build_parameters, '$.Version')) >= 3
            THEN N'latest format'
        WHEN TRY_CONVERT(int, JSON_VALUE(vi.build_parameters, '$.Version')) < 3
            THEN N'earlier format'
        ELSE N'version key absent (RTM current format) — probe, do not assume'
    END AS format_class
FROM sys.vector_indexes AS vi
JOIN sys.indexes AS i
    ON i.object_id = vi.object_id
    AND i.index_id = vi.index_id
JOIN sys.tables AS t
    ON t.object_id = vi.object_id
JOIN sys.schemas AS s
    ON s.schema_id = t.schema_id
WHERE t.object_id = OBJECT_ID(N'dbo.VectorLabSearchCorpus');
```

### 8.4 Current-format approximate query

Run only when the syntax probe and index version support it.

```sql
DECLARE @query_chunk_id int = 1001;
DECLARE @q VECTOR(64) =
(
    SELECT embedding
    FROM dbo.VectorLabSearchCorpus
    WHERE chunk_id = @query_chunk_id
);

SELECT TOP (20) WITH APPROXIMATE
    c.chunk_id,
    c.document_id,
    c.category,
    c.label,
    r.distance
FROM VECTOR_SEARCH
(
    TABLE = dbo.VectorLabSearchCorpus AS c,
    COLUMN = embedding,
    SIMILAR_TO = @q,
    METRIC = 'cosine'
) AS r
WHERE c.chunk_id <> @query_chunk_id
  AND c.category = N'Technical'
ORDER BY r.distance;
```

### 8.5 Force ANN where supported

```sql
DECLARE @query_chunk_id int = 1001;
DECLARE @q VECTOR(64) =
(
    SELECT embedding
    FROM dbo.VectorLabSearchCorpus
    WHERE chunk_id = @query_chunk_id
);

SELECT TOP (20) WITH APPROXIMATE
    c.chunk_id,
    c.document_id,
    c.category,
    c.label,
    r.distance
FROM VECTOR_SEARCH
(
    TABLE = dbo.VectorLabSearchCorpus AS c,
    COLUMN = embedding,
    SIMILAR_TO = @q,
    METRIC = 'cosine'
) AS r WITH (FORCE_ANN_ONLY)
WHERE c.chunk_id <> @query_chunk_id
  AND c.category = N'Technical'
ORDER BY r.distance;
```

### 8.6 Earlier-format query

Use only when the catalog and syntax probe identify an earlier index format.

```sql
DECLARE @query_chunk_id int = 1001;
DECLARE @q VECTOR(64) =
(
    SELECT embedding
    FROM dbo.VectorLabSearchCorpus
    WHERE chunk_id = @query_chunk_id
);

DECLARE @requested_k int = 20;
DECLARE @oversample_multiplier int = 5;

SELECT TOP (@requested_k)
    c.chunk_id,
    c.document_id,
    c.category,
    c.label,
    r.distance
FROM VECTOR_SEARCH
(
    TABLE = dbo.VectorLabSearchCorpus AS c,
    COLUMN = embedding,
    SIMILAR_TO = @q,
    METRIC = 'cosine',
    TOP_N = 100
) AS r
WHERE c.chunk_id <> @query_chunk_id
  AND c.category = N'Technical'
ORDER BY r.distance;
```

The literal `TOP_N` must be generated safely for the probed target. The UI should disclose the oversample multiplier and post-filter semantics. The example uses 100 because K is 20 and the demonstration multiplier is 5.

### 8.7 Search comparison demo S-03 - exact versus ANN

### Steps

1. Bind `dbo.VectorLabSearchCorpus` as the Search/Index target.
2. Select chunk 1001.
3. Choose K 20, Cosine, Technical filter.
4. Enable exact, approximate, and forced ANN where supported.
5. Run the comparison.
6. Open the evidence panel and repro script.

### Required observations

- Exact and approximate use the same frozen query vector.
- Self-exclusion is visible.
- Read consistency is visible.
- Index version and filter semantics are visible.
- Forced ANN is claimed only when the forced statement succeeds.
- Recall denominator is 20 exact neighbors or the actual eligible count.
- The rank grid contains the union of both result sets.
- Timing says single observation or reports repeated-run statistics.
- Index staleness is stamped at run time when the DMV is available.

### Why this helps

This is the flagship scenario. It separates poor recall caused by ANN from poor results caused by the embedding model, filter, source corpus, or stale graph.

### 8.8 Index health query

```sql
SELECT
    i.name AS index_name,
    dvi.approximate_staleness_percent,
    dvi.quantized_keys_used_percent,
    dvi.last_background_task_time,
    dvi.last_background_task_succeeded,
    dvi.last_background_task_duration_seconds,
    dvi.last_background_task_processed_inserts,
    dvi.last_background_task_processed_deletes,
    dvi.last_background_task_error_message
FROM sys.dm_db_vector_indexes AS dvi
JOIN sys.indexes AS i
    ON i.object_id = dvi.object_id
    AND i.index_id = dvi.index_id
WHERE dvi.object_id = OBJECT_ID(N'dbo.VectorLabSearchCorpus');
```

### 8.9 Staleness demonstration

This scenario is timing-dependent and is most useful on a current-format index with DML support.

```sql
-- Review the current index version first.
-- This intentionally creates many vector changes by copying embeddings.
-- Rerun the full synthetic setup to restore the original corpus afterward.

UPDATE target
SET target.embedding = source.embedding,
    target.embedding_batch_id = 99
FROM dbo.VectorLabSearchCorpus AS target
JOIN dbo.VectorLabSearchCorpus AS source
    ON source.chunk_id = 1000 + ((target.chunk_id - 3000) % 200)
WHERE target.chunk_id BETWEEN 3000 AND 3499;

SELECT
    approximate_staleness_percent,
    quantized_keys_used_percent,
    last_background_task_time,
    last_background_task_succeeded,
    last_background_task_duration_seconds,
    last_background_task_processed_inserts,
    last_background_task_processed_deletes,
    last_background_task_error_message
FROM sys.dm_db_vector_indexes
WHERE object_id = OBJECT_ID(N'dbo.VectorLabSearchCorpus');
```

Run the Search comparison immediately, then again after maintenance reduces staleness.

### What this demonstrates

- Staleness is a run-time condition, not a static index property.
- Search results remain available while maintenance catches up.
- Ranking quality can change while the graph incorporates updates.
- The Workbench should not recommend a rebuild from one staleness value alone.

### 8.10 Index screen state tests

**Healthy current format**

- Version 3 or newer.
- Metric matches.
- Migration command absent.
- Health and maintenance facts visible.

**Earlier format**

- Version below 3.
- Migration command visible.
- Service-impact warning visible.
- Post-filter behavior and DML limitations visible.

**No index**

- Explain that exact search still works.
- Offer a generated create-index script for review.

**Permission degraded**

- Catalog index visible but DMV unavailable.
- UI says health unavailable rather than healthy.

## 9. Track C - external embedding model and real embeddings

## 9.1 Choose an endpoint mode

| Mode | Egress | Typical use |
| --- | --- | --- |
| Azure OpenAI | SQL Server calls a remote Azure endpoint | Managed development or production-like lab |
| OpenAI | SQL Server calls a remote OpenAI endpoint | Interoperability lab |
| Ollama | SQL Server calls a host-local HTTPS endpoint | Local development where configured |
| ONNX Runtime | Model executes through local SQL Server runtime | Windows-only local-runtime lab with prerequisites |

The Workbench confirmation text must vary by mode.

## 9.2 Enable the REST endpoint gate where required

On SQL Server or Managed Instance where the configuration is not already enabled:

```sql
EXECUTE sys.sp_configure 'external rest endpoint enabled', 1;
RECONFIGURE WITH OVERRIDE;
```

Azure SQL Database and SQL database in Fabric document this as enabled by default.

## 9.3 Azure OpenAI template

Edit every placeholder before running. Do not commit the secret to source control or save it in a shared query file.

```sql
-- Replace:
--   <endpoint-host>
--   <deployment-name>
--   <api-key>
-- Review the API version for the endpoint you deployed.

CREATE DATABASE SCOPED CREDENTIAL
    [https://<endpoint-host>/]
WITH
    IDENTITY = 'HTTPEndpointHeaders',
    SECRET = '{"api-key":"<api-key>"}';
GO

CREATE EXTERNAL MODEL VectorLabEmbeddingModel
AUTHORIZATION dbo
WITH
(
    LOCATION = 'https://<endpoint-host>/openai/deployments/<deployment-name>/embeddings?api-version=2024-02-01',
    API_FORMAT = 'Azure OpenAI',
    MODEL_TYPE = EMBEDDINGS,
    MODEL = 'text-embedding-3-small',
    CREDENTIAL = [https://<endpoint-host>/],
    PARAMETERS =
        '{"dimensions":1536,"sql_rest_options":{"retry_count":3}}'
);
GO

GRANT EXECUTE ON EXTERNAL MODEL::VectorLabEmbeddingModel
TO [<database-principal>];
GO
```

### Important identity note

The external model is `VectorLabEmbeddingModel`, not `dbo.VectorLabEmbeddingModel`. `dbo` is the owner in this example.

## 9.4 Verify model catalog facts

```sql
SELECT
    em.name AS external_model_name,
    USER_NAME(em.principal_id) AS owner_name,
    em.api_format,
    em.model_type_desc,
    em.model AS provider_model,
    em.location,
    em.parameters,
    em.create_time,
    em.modify_time
FROM sys.external_models AS em
WHERE em.name = N'VectorLabEmbeddingModel';
```

## 9.5 One-call smoke test

This sends the source text to the configured model path.

```sql
SELECT
    AI_GENERATE_EMBEDDINGS
    (
        N'Reset a multi-factor authentication device for an employee account.'
        USE MODEL VectorLabEmbeddingModel
    ) AS generated_embedding;
```

The Workbench should present a confirmation before it generates this query from the UI.

## 9.6 Create a real-embedding table

```sql
DROP TABLE IF EXISTS dbo.VectorLabRealChunks;

CREATE TABLE dbo.VectorLabRealChunks
(
    chunk_id int NOT NULL,
    document_id int NOT NULL,
    category nvarchar(32) NOT NULL,
    label nvarchar(200) NOT NULL,
    chunk_text nvarchar(max) NOT NULL,
    source_modified_at datetime2(3) NOT NULL,
    embedded_at datetime2(3) NULL,
    embedding_model nvarchar(128) NULL,
    embedding_profile nvarchar(128) NULL,
    embedding VECTOR(1536) NULL,
    CONSTRAINT PK_VectorLabRealChunks
        PRIMARY KEY CLUSTERED (chunk_id)
);

INSERT dbo.VectorLabRealChunks
(
    chunk_id,
    document_id,
    category,
    label,
    chunk_text,
    source_modified_at
)
SELECT TOP (120)
    c.chunk_id,
    c.document_id,
    c.category,
    c.label,
    c.chunk_text,
    c.source_modified_at
FROM dbo.VectorLabChunks AS c
WHERE c.chunk_id >= 1000
ORDER BY c.chunk_id;
```

## 9.7 Generate a small smoke batch first

This can make one endpoint request per row, depending on the engine/provider path. Start with 5 rows.

```sql
UPDATE dbo.VectorLabRealChunks
SET embedding = AI_GENERATE_EMBEDDINGS
    (
        chunk_text USE MODEL VectorLabEmbeddingModel
    ),
    embedded_at = SYSUTCDATETIME(),
    embedding_model = N'VectorLabEmbeddingModel',
    embedding_profile = N'passage-prefix-v1|provider-output'
WHERE chunk_id IN
(
    SELECT TOP (5) chunk_id
    FROM dbo.VectorLabRealChunks
    WHERE embedding IS NULL
    ORDER BY chunk_id
);

SELECT
    chunk_id,
    VECTORPROPERTY(embedding, 'Dimensions') AS dimensions,
    VECTORPROPERTY(embedding, 'BaseType') AS base_type,
    VECTOR_NORM(embedding, 'norm2') AS norm2
FROM dbo.VectorLabRealChunks
WHERE embedding IS NOT NULL
ORDER BY chunk_id;
```

Confirm dimensions before generating the remaining rows.

## 9.8 Populate enough rows for an index, deliberately and visibly

Review endpoint cost, rate limit, and data sensitivity first.

```sql
DECLARE @batch_size int = 10;
DECLARE @rows_remaining int = 1;

WHILE @rows_remaining > 0
BEGIN
    ;WITH NextBatch AS
    (
        SELECT TOP (@batch_size) chunk_id
        FROM dbo.VectorLabRealChunks
        WHERE embedding IS NULL
        ORDER BY chunk_id
    )
    UPDATE target
    SET embedding = AI_GENERATE_EMBEDDINGS
        (
            target.chunk_text USE MODEL VectorLabEmbeddingModel
        ),
        embedded_at = SYSUTCDATETIME(),
        embedding_model = N'VectorLabEmbeddingModel',
        embedding_profile = N'passage-prefix-v1|provider-output'
    FROM dbo.VectorLabRealChunks AS target
    JOIN NextBatch AS b
        ON b.chunk_id = target.chunk_id;

    SET @rows_remaining = @@ROWCOUNT;
END;

SELECT
    COUNT(*) AS rows_total,
    SUM(CASE WHEN embedding IS NOT NULL THEN 1 ELSE 0 END) AS vectors_generated,
    MIN(VECTORPROPERTY(embedding, 'Dimensions')) AS min_dimensions,
    MAX(VECTORPROPERTY(embedding, 'Dimensions')) AS max_dimensions
FROM dbo.VectorLabRealChunks;
```

Cancellation should be tested. The user should understand that a remote request might already be in flight when cancellation is requested.

## 9.9 Pipeline demo L-01 - re-embed selected row

### Steps

1. Query `dbo.VectorLabRealChunks` including source text and embedding.
2. Bind key, source text, timestamps, model, and profile.
3. Select one row in Pipeline.
4. Choose Re-embed and compare.
5. Read the confirmation dialog.
6. View generated T-SQL.
7. Confirm the call.

### Required observations

- Model name and owner are separate.
- API format and endpoint host are shown.
- Egress copy is correct for the endpoint mode.
- Source row, text character count, approximate payload, call count, and retry count are shown.
- Fresh vector dimensions are validated.
- The result stays in the panel and is not written to the table.
- Stored-versus-fresh cosine distance, Euclidean distance, negative dot, norm, neighbor overlap, and rank movement are labeled with their search mode.
- Footer says `Webview network: none` and records the server-side model call separately.

### Why this helps

This detects stale embeddings, wrong source columns, changed preprocessing, model migrations, and pipeline drift without overwriting production data.

## 9.10 Pipeline demo L-02 - create deliberate drift

```sql
UPDATE dbo.VectorLabRealChunks
SET chunk_text = CONCAT
(
    chunk_text,
    N' The source content changed substantially after the stored embedding was created.'
),
    source_modified_at = DATEADD(day, 10, COALESCE(embedded_at, SYSUTCDATETIME()))
WHERE chunk_id IN
(
    SELECT TOP (10) chunk_id
    FROM dbo.VectorLabRealChunks
    WHERE embedding IS NOT NULL
    ORDER BY chunk_id
);
```

Re-embed one of the changed rows.

### Expected observations

- Freshness finding says source modified after embedding.
- Stored-versus-fresh distance is larger than an unchanged row.
- Neighbor overlap and rank movement may change.

### Why this helps

A stale vector can be perfectly well-formed and still be wrong for the current source. Norm and PCA checks alone cannot detect this.

## 9.11 Pipeline demo L-03 - provenance mismatch

Change only the provenance declaration on a few rows:

```sql
UPDATE dbo.VectorLabRealChunks
SET embedding_model = N'PreviousEmbeddingDeployment',
    embedding_profile = N'legacy-prefix-v0'
WHERE chunk_id IN
(
    SELECT TOP (10) chunk_id
    FROM dbo.VectorLabRealChunks
    WHERE embedding IS NOT NULL
    ORDER BY chunk_id DESC
);
```

### Expected observations

- Dimensions still match.
- The Workbench says provenance mismatch or unknown rather than green compatibility.

## 10. Chunking demos

## 10.1 Preview fixed-character chunks

```sql
SELECT
    d.document_id,
    c.chunk_set_id,
    c.chunk_order,
    c.chunk_offset,
    c.chunk_length,
    c.chunk
FROM dbo.VectorLabDocuments AS d
CROSS APPLY AI_GENERATE_CHUNKS
(
    SOURCE = d.body,
    CHUNK_TYPE = FIXED,
    CHUNK_SIZE = 800,
    OVERLAP = 15,
    ENABLE_CHUNK_SET_ID = 1
) AS c
WHERE d.document_id = 203
ORDER BY c.chunk_order;
```

### Workbench steps

1. Bind `body` as the source text.
2. Set size 800 and overlap 15 percent.
3. Compare the ribbon to `chunk_offset` and `chunk_length`.
4. Inspect the tail chunk.
5. Change overlap to 0 and 30.

### Required observations

- UI says characters, not tokens.
- Overlap regions are visibly marked.
- Chunk order, offset, length, and tail are shown.
- The UI does not imply that the endpoint tokenizer will accept every character chunk without truncation.

## 10.2 Generate embeddings for chunks

This can make multiple model calls. Preview and confirm the chunk count first.

```sql
SELECT
    d.document_id,
    c.chunk_order,
    c.chunk_offset,
    c.chunk_length,
    AI_GENERATE_EMBEDDINGS
    (
        c.chunk USE MODEL VectorLabEmbeddingModel
    ) AS embedding
FROM dbo.VectorLabDocuments AS d
CROSS APPLY AI_GENERATE_CHUNKS
(
    SOURCE = d.body,
    CHUNK_TYPE = FIXED,
    CHUNK_SIZE = 800,
    OVERLAP = 15,
    ENABLE_CHUNK_SET_ID = 1
) AS c
WHERE d.document_id = 203
ORDER BY c.chunk_order;
```

### Why this helps

Chunking policy can change retrieval more than index tuning. The ribbon, call count, and neighbor comparison let a developer see the pipeline decision rather than treating chunks as invisible preprocessing.

## 11. Query-set evaluation demo

The synthetic relevance table provides a simple graded benchmark. It is deliberately artificial but deterministic.

### 11.1 One-query exact evaluation

```sql
DECLARE @query_id int = 1;
DECLARE @source_chunk_id int =
(
    SELECT source_chunk_id
    FROM dbo.VectorLabSearchQueries
    WHERE query_id = @query_id
);
DECLARE @q VECTOR(64) =
(
    SELECT embedding
    FROM dbo.VectorLabSearchCorpus
    WHERE chunk_id = @source_chunk_id
);

;WITH Retrieved AS
(
    SELECT TOP (20)
        c.chunk_id,
        VECTOR_DISTANCE('cosine', c.embedding, @q) AS distance
    FROM dbo.VectorLabSearchCorpus AS c
    WHERE c.chunk_id <> @source_chunk_id
    ORDER BY
        VECTOR_DISTANCE('cosine', c.embedding, @q),
        c.chunk_id
),
Ranked AS
(
    SELECT
        r.chunk_id,
        r.distance,
        ROW_NUMBER() OVER (ORDER BY r.distance, r.chunk_id) AS retrieval_rank
    FROM Retrieved AS r
)
SELECT
    r.retrieval_rank,
    r.chunk_id,
    r.distance,
    COALESCE(e.relevance_grade, 0) AS relevance_grade,
    COALESCE(e.relevance_reason, N'not expected') AS relevance_reason
FROM Ranked AS r
LEFT JOIN dbo.VectorLabExpectedRelevant AS e
    ON e.query_id = @query_id
    AND e.chunk_id = r.chunk_id
ORDER BY r.retrieval_rank;
```

### 11.2 Workbench query-set mode

When implemented, select all five `VectorLabSearchQueries` rows and run a bounded query-set evaluation.

Report:

- recall@20 per query;
- median and p5 recall;
- unique documents in top 20;
- same-document chunk count;
- median and p95 exact/approximate latency;
- worst query IDs;
- staleness at run time;
- total statement count and cancellation state.

### Why this helps

A single selected-row comparison finds a local bug. A query set characterizes the index and corpus.

## 12. Security and tenant-filter demo

This optional scenario verifies that diagnostics respect the current principal and session context.

```sql
DROP SECURITY POLICY IF EXISTS dbo.VectorLabTenantPolicy;
DROP FUNCTION IF EXISTS dbo.fn_VectorLabTenantPredicate;
DROP TABLE IF EXISTS dbo.VectorLabTenantChunks;

CREATE TABLE dbo.VectorLabTenantChunks
(
    chunk_id int NOT NULL,
    tenant_id int NOT NULL,
    category nvarchar(32) NOT NULL,
    label nvarchar(200) NOT NULL,
    embedding VECTOR(64) NULL,
    CONSTRAINT PK_VectorLabTenantChunks
        PRIMARY KEY CLUSTERED (chunk_id)
);

INSERT dbo.VectorLabTenantChunks
(chunk_id, tenant_id, category, label, embedding)
SELECT TOP (1000)
    chunk_id,
    tenant_id,
    category,
    label,
    embedding
FROM dbo.VectorLabSearchCorpus
ORDER BY chunk_id;
GO

CREATE FUNCTION dbo.fn_VectorLabTenantPredicate(@tenant_id int)
RETURNS TABLE
WITH SCHEMABINDING
AS
RETURN
(
    SELECT 1 AS allowed
    WHERE @tenant_id = TRY_CONVERT(int, SESSION_CONTEXT(N'vector_lab_tenant_id'))
);
GO

CREATE SECURITY POLICY dbo.VectorLabTenantPolicy
ADD FILTER PREDICATE dbo.fn_VectorLabTenantPredicate(tenant_id)
ON dbo.VectorLabTenantChunks
WITH (STATE = ON);
GO

EXEC sys.sp_set_session_context
    @key = N'vector_lab_tenant_id',
    @value = 1;

SELECT COUNT(*) AS visible_rows
FROM dbo.VectorLabTenantChunks;
```

### Workbench expectations

- A table-bound diagnostic session must reproduce required session context or disclose that it cannot.
- It must not see tenants hidden from the principal/session.
- Exact and approximate comparisons use the same tenant filter and security context.
- Eligible-row count reflects the authorized view.

### Why this helps

A faster ANN query is useless if it crosses an authorization boundary. Security filters are part of retrieval semantics.

## 13. Permission-degraded demos

### 13.1 Health DMV unavailable

The easiest deterministic automation is to execute the health query as a principal without `VIEW DATABASE STATE` and assert the Workbench shows `Health unavailable` rather than `Healthy`.

```sql
CREATE USER VectorLabLimited WITHOUT LOGIN;
GRANT SELECT ON dbo.VectorLabChunks TO VectorLabLimited;

EXECUTE AS USER = 'VectorLabLimited';

SELECT TOP (1)
    chunk_id,
    embedding
FROM dbo.VectorLabChunks;

BEGIN TRY
    SELECT *
    FROM sys.dm_db_vector_indexes;
END TRY
BEGIN CATCH
    SELECT
        ERROR_NUMBER() AS error_number,
        ERROR_MESSAGE() AS error_message;
END CATCH;

REVERT;
```

For an end-to-end Query Studio connection, use a real least-privilege test login or contained user appropriate to the test environment.

### 13.2 External model visible but not executable

Create or use a principal that can read the table but lacks:

```sql
GRANT EXECUTE ON EXTERNAL MODEL::VectorLabEmbeddingModel
```

The Pipeline should remain useful for local profiling and show a clear model-execution permission state.

## 14. Lifecycle, result-store, and UI tests

## 14.1 Rerun while Profile preparation is active

1. Run the 5,000-row result.
2. Open Profile and start analysis with a deliberately low work-slice budget.
3. Rerun the query.
4. Confirm the old analysis cancels and no stale findings appear in the new run.
5. Confirm the old result-store lease is released.

## 14.2 Switch workspaces during analysis

- Switching away should cancel work that is not intentionally retained.
- Completed bounded local data may remain session-local only under the approved lifetime policy.
- No hidden worker or server query should continue without a visible task state.

## 14.3 Pin results

1. Run the 5,000-row result.
2. Pin it.
3. Rerun or close the original editor.
4. Open the pinned Vector pane.
5. Confirm Profile, Compare, and Projection use the frozen snapshot.
6. Confirm table-bound Search or Pipeline requires an explicit current connection and binding rather than pretending the pinned rows are a live table.

## 14.4 Cancel Search comparison

Cancel during exact, approximate, and repeated-query-set runs. The UI must report which statements completed, which results are partial, and whether the cancel acknowledgement was certain.

## 15. Harness-only edge cases

Some important states are not reliable or responsible to manufacture with ordinary T-SQL on every target. They belong in unit, integration, or protocol-fixture tests.

| Scenario | Why harness-only or environment-specific | Required UI result |
| --- | --- | --- |
| Non-finite components | Server/provider acceptance of NaN and infinity must be validated; JSON paths commonly reject them | Finding appears only when real typed input proves it exists |
| Native vector transport truncation | Requires controlled STS2 cell/frame limits | Honest unavailable/truncated state, never partial vector math |
| Malformed tagged vector payload | Protocol fault, not ordinary SQL | Query fails or cell is unavailable; no crash |
| Earlier v2 index | New deployments may create only current format | Preserved test DB, captured fixture, or mocked catalog/SQL responses |
| Regional syntax rollout mismatch | Cloud rollout varies | Capability probe and syntax-test fixture |
| Health DMV background failure | Difficult to force safely | Mocked DMV row or controlled service fault |
| Quantized-key saturation | Not predictably generated by small lab | DMV fixture |
| Metadata hidden but data readable | Needs tailored principal and metadata visibility setup | Degraded capability state |
| Model returns wrong dimension | Requires controllable endpoint | Fake endpoint or test model |
| Endpoint 429/500/retry | Requires controllable endpoint | Fake HTTPS endpoint or provider test double |
| Cancellation during in-flight REST call | Timing-sensitive | Fake endpoint with deterministic delay |
| Exact and approximate concurrent-change race | Requires coordinated transactions | Integration harness with barriers |
| Compact capture privacy canary | Protocol/journal concern | Service unit/integration test, no canary in persisted artifact |

## 16. Automated acceptance matrix

Acceptance scenarios use the namespace `VTEST-01..VTEST-22`, defined in `vector_workbench_readiness_review_addendum.md` section 7. `VEC-0..VEC-12` is reserved for implementation checkpoints in `_build/EXECUTION_PLAN.md`; do not use a checkpoint ID as proof that the similarly numbered acceptance scenario passed. The workspace-specific lists below define the assertions each `VTEST` scenario composes.

### 16.1 SQL Tools Service

- Native float32 `SqlVector<float>` recognized and encoded losslessly.
- Vector cells have honest byte accounting.
- Compact and noncompact rows normalize identically.
- Oversized vector yields a complete unavailable marker, not a prefix.
- Capture elides complete compact payloads.
- Journal and diagnostic exports contain no vector canaries.
- Query cancel and frame guard remain deterministic.

### 16.2 SQL Data Plane and result store

- Vector metadata reaches `QsResultColumn`.
- Typed vector cells spill and restore.
- Sparse projection returns vector plus distant label in one materialization.
- Vector-analysis read reason does not evict grid viewport pages.
- Host sessions release leases on completion, cancellation, expiry, rerun, hide, and disposal.
- Webview cannot raise row, component, byte, or time budgets.

### 16.3 Profile

- Stable counts for every injected anomaly.
- Finding subject units are correct.
- Sample method and bias disclosure are present.
- Cancellation returns partial scope.
- Group sizes and statistics align.
- Duplicate groups and covered rows are distinct values.

### 16.4 Search

- Query vector frozen once.
- Self-exclusion identical across variants.
- Structured filters parameterized.
- Read consistency recorded.
- Exact denominator correct.
- Rank union complete.
- Forced ANN proof classified correctly.
- Earlier post-filter behavior disclosed.
- Staleness stamped at measurement time.
- Repro script matches executed SQL.

### 16.5 Compare

- Metric formulas and component indexing documented.
- Zero-vector cosine state handled.
- Dimension and provenance compatibility separated.
- Arithmetic parser never evaluates JavaScript.
- Local versus server evidence source is distinct.

### 16.6 Projection

- Deterministic PCA and sign normalization.
- Analyzed versus rendered counts separate.
- Original-space neighbors remain original-space.
- Point list and canvas selection synchronize.
- High contrast and keyboard navigation pass.

### 16.7 Index

- Healthy current format hides migration.
- Earlier format shows migration and service-impact warning.
- Every DMV field is mapped correctly.
- Missing permission is not reported as health.
- Generated scripts never execute automatically.
- Limitations and prerequisites are accurate for the probed target.

### 16.8 Pipeline

- No automatic model call on open.
- Confirmation content varies by egress class.
- Full source text is never silently replaced with a truncated prefix.
- Model dimension validated.
- Model object identity is not schema-qualified.
- Retry and cancellation state represented.
- Remote source text and vectors absent from telemetry and logs.

## 17. UX evaluation script

Use this sequence for a 20-to-30-minute product demonstration.

1. Run the capability probe.
2. Run the synthetic setup.
3. Open the full 5,000-row result.
4. Profile the corpus and open the duplicate and low-variance drawers.
5. Add three rows to Compare and run one arithmetic expression.
6. Open Projection, color by category, lasso an outlier, and reveal it.
7. Run exact selected-row Search with self-exclusion.
8. If an index is supported, create it and run exact/approximate/forced comparison.
9. Open Index and show current-format health or the appropriate legacy state.
10. Configure or select an existing external model.
11. Open Pipeline, re-embed one unchanged row, then one deliberately stale row.
12. Preview fixed-character chunks and display the expected model-call count.
13. Cancel one long operation.
14. Pin results and prove detached Profile/Compare/Projection survive a rerun.
15. Switch to a least-privilege connection and show degraded metadata honestly.

The demonstration should spend more time on evidence rows and row-to-SQL traceability than on the PCA picture. That is the product distinction.

## 18. Cleanup

Run only after reviewing object names. Drop the vector index first because a vector-indexed table cannot be truncated and may have target-specific DML behavior.

```sql
IF EXISTS
(
    SELECT 1
    FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.VectorLabSearchCorpus')
      AND name = N'IX_VectorLabSearchCorpus_Embedding'
)
BEGIN
    DROP INDEX IX_VectorLabSearchCorpus_Embedding
    ON dbo.VectorLabSearchCorpus;
END;
GO

DROP SECURITY POLICY IF EXISTS dbo.VectorLabTenantPolicy;
DROP FUNCTION IF EXISTS dbo.fn_VectorLabTenantPredicate;
DROP TABLE IF EXISTS dbo.VectorLabTenantChunks;
DROP TABLE IF EXISTS dbo.VectorLabRealChunks;
DROP TABLE IF EXISTS dbo.VectorLabExpectedRelevant;
DROP TABLE IF EXISTS dbo.VectorLabSearchQueries;
DROP TABLE IF EXISTS dbo.VectorLabSearchCorpus;
DROP TABLE IF EXISTS dbo.VectorLabChunks;
DROP TABLE IF EXISTS dbo.VectorLabDocuments;
DROP USER IF EXISTS VectorLabLimited;
GO

-- Optional model cleanup. Review dependencies and principal use first.
-- DROP EXTERNAL MODEL VectorLabEmbeddingModel;
-- DROP DATABASE SCOPED CREDENTIAL [https://<endpoint-host>/];
```

## 19. Troubleshooting checklist

### Vector tab does not appear

- Confirm `mssql.queryStudio.vectorWorkbench.enabled` was enabled **before** the query began. Opening Vector never enables transport for a run.
- Confirm STS2 initialize advertised `vectorBinaryV1` and the execute request negotiated `vectorEncoding: "binary-v1"`.
- Confirm a terminal, non-plan result set contains a metadata-confirmed native `float32` vector column whose transport is `binary-v1`.
- Confirm the retained result store is still available for analysis.
- A metadata-confirmed text-fallback vector is intentionally ineligible for the initial preview; inspect it in Results. Do not infer eligibility from a JSON-looking string.
- If the setting was changed after execution, that existing result cannot be re-encoded. Run the query again once under the new setting; opening the tab must never create a run-twice workflow.

### Profile sample is smaller than requested

- Check row count.
- Check null/unavailable rows.
- Check component budget: dimensions multiplied by rows.
- Check packed-byte budget.
- Check row-scan cap and elapsed-time budget.
- Read the partial reason.

### Search has fewer than K rows

- Check eligible-row count.
- Check self and same-document exclusion.
- Check RLS and tenant filters.
- Check earlier-index post-filter behavior.
- Check null vectors.
- Check exact denominator before blaming ANN.

### Approximate search is not proven

- Check index existence, column, and metric.
- Check current versus earlier syntax.
- Check `WITH APPROXIMATE`.
- Check `FORCE_ANN_ONLY` capability and placement.
- Check whether the optimizer chose exact kNN.
- Open generated SQL and evidence.

### Pipeline model call fails

- Check model object name, type, owner, and grants.
- Check endpoint or local-runtime configuration gate.
- Check credential URL matching rules.
- Check HTTPS and allowlist requirements.
- Check retry count and endpoint status.
- Check XEvents when permissions allow.
- Check output dimensions before storing.

### Projection looks impressive but retrieval is poor

- Remember projection is lossy.
- Inspect explained variance.
- Compare original-space neighbors.
- Run exact Search and a query-set benchmark.
- Check boilerplate, duplicates, chunk crowding, and provenance.

## 20. Primary documentation

All links were checked against Microsoft documentation current on 2026-07-11.

- [Vector data type](https://learn.microsoft.com/en-us/sql/t-sql/data-types/vector-data-type?view=sql-server-ver17)
- [VECTORPROPERTY](https://learn.microsoft.com/en-us/sql/t-sql/functions/vectorproperty-transact-sql?view=sql-server-ver17)
- [VECTOR_NORM](https://learn.microsoft.com/en-us/sql/t-sql/functions/vector-norm-transact-sql?view=sql-server-ver17)
- [VECTOR_NORMALIZE](https://learn.microsoft.com/en-us/sql/t-sql/functions/vector-normalize-transact-sql?view=sql-server-ver17)
- [VECTOR_DISTANCE](https://learn.microsoft.com/en-us/sql/t-sql/functions/vector-distance-transact-sql?view=sql-server-ver17)
- [VECTOR_SEARCH](https://learn.microsoft.com/en-us/sql/t-sql/functions/vector-search-transact-sql?view=sql-server-ver17)
- [CREATE VECTOR INDEX](https://learn.microsoft.com/en-us/sql/t-sql/statements/create-vector-index-transact-sql?view=sql-server-ver17)
- [sys.vector_indexes](https://learn.microsoft.com/en-us/sql/relational-databases/system-catalog-views/sys-vector-indexes-transact-sql?view=sql-server-ver17)
- [sys.dm_db_vector_indexes](https://learn.microsoft.com/en-us/sql/relational-databases/system-dynamic-management-objects/sys-dm-db-vector-indexes-transact-sql?view=sql-server-ver17)
- [CREATE EXTERNAL MODEL](https://learn.microsoft.com/en-us/sql/t-sql/statements/create-external-model-transact-sql?view=sql-server-ver17)
- [sys.external_models](https://learn.microsoft.com/en-us/sql/relational-databases/system-catalog-views/sys-external-models-transact-sql?view=sql-server-ver17)
- [AI_GENERATE_EMBEDDINGS](https://learn.microsoft.com/en-us/sql/t-sql/functions/ai-generate-embeddings-transact-sql?view=sql-server-ver17)
- [AI_GENERATE_CHUNKS](https://learn.microsoft.com/en-us/sql/t-sql/functions/ai-generate-chunks-transact-sql?view=sql-server-ver17)
