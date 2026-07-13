# R04 Brief — Vector Workbench Test & Demo Guide

**Source:** `C:/repos/test/coding-docs/query-result-tabs/vector_workbench_test_and_demo_guide.md` (2,175 lines, read completely; all line refs below are into that file)
**Doc status/date:** Build, evaluation, and demonstration guide, 2026-07-11 (lines 3–4)
**Targets:** SQL Server 2025, Azure SQL DB, Azure SQL MI (where supported), Fabric SQL (where supported) (line 6)
**Companion docs (line 7–13):** `query_studio_vector_workbench_ux_spec.md`, `query_studio_vector_workbench_implementation_plan.md`, `vector_design_addendum.md`, `vector_ux_revisions.md`, `vector_workbench_readiness_review_addendum.md`

---

## 1. What the feature is and the six question families (lines 31–117)

The Vector Workbench is a **result-pane debugger for vector-bearing SQL results** — not a scatterplot toy and not a replacement for the normal Results grid (line 33). Its six workspaces map to six diagnostic question families:

| Workspace | Question | Key capabilities (verbatim from source) |
|---|---|---|
| **Profile** (1.1, lines 37–49) | Are stored vectors structurally healthy? | null/unavailable/zero/near-zero vectors; norm distributions; exact & near duplicates; low-variance dimensions; outliers; mixed provenance; stale embeddings; group-specific distribution changes; boilerplate/chunk crowding |
| **Compare** (1.2, lines 51–62) | Why did this vector rank near/far from another? | cosine, Euclidean, negative dot distances; norms; top component differences; top metric contributions; pairwise matrices; centroids & medoids; local vector arithmetic; nearest bound rows to a local expression result |
| **Search** (1.3, lines 64–77) | Is ANN returning the same useful neighbors as exact? | exact ground truth; optimizer-selected approximate; forced ANN; recall at K; overlap & rank movement; exact-only/approximate-only rows; filter semantics; index-version behavior; index staleness at run time; generated SQL & execution evidence |
| **Projection** (1.4, lines 79–88) | What broad structure exists in the embedding space? | category/tenant clusters; outliers; overlap; selected rows & neighborhoods; deterministic PCA with explained variance; distinction between projected coords and original-space distance |
| **Index** (1.5, lines 90–102) | Is the vector index present, compatible, current, maintainable? | DiskANN presence; metric compatibility; index version; current-vs-earlier format; health DMV facts; approximate staleness; background maintenance; prerequisites/limitations; generated create/migration/health/config scripts |
| **Pipeline** (1.6, lines 104–117) | Was the embedding pipeline configured and executed correctly? | source text provenance; external model config; egress path; model output dimensions; stored-vs-fresh drift; changed preprocessing; chunk size/overlap; source text changed after embedding; repeated generation across chunks; remote-call failures/retry/cancellation |

## 2. SQL feature map — key facts an engineer must know (lines 119–172)

- Column type: `embedding VECTOR(1536)` (line 126). Default base type **float32**; optimized binary storage with JSON conversion for compat; **max dimensions for the native type = 1,998**; **float16 is preview with different driver-transport behavior** — this guide uses float32 unless a test says otherwise (line 129).
- Core functions (verbatim, lines 135–145): `VECTORPROPERTY(embedding, 'Dimensions')`, `VECTORPROPERTY(embedding, 'BaseType')`, `VECTOR_NORM(embedding, 'norm1'|'norm2'|'norminf')`, `VECTOR_NORMALIZE(embedding, 'norm2')`, `VECTOR_DISTANCE('cosine'|'euclidean'|'dot', embedding, @query_vector)`.
- `VECTOR_DISTANCE` is **exact and does not use a vector index** — it is the natural ground truth for approximate-recall experiments (line 147).
- Approximate search uses `VECTOR_SEARCH`. **Current-format indexes: `SELECT TOP (N) WITH APPROXIMATE`. Earlier indexes: deprecated `TOP_N` argument with post-filter behavior.** `FORCE_ANN_ONLY` proves an ANN index path was used, where supported (line 151). **Hard rule:** do not paste one approximate-search template into every target — the Workbench must probe the actual connection and index version (line 153).
- External model object: stores endpoint/local runtime location, API format, model type, provider model name, credential reference, optional parameters (dimensions, retry count). **Named at database scope, NOT schema-qualified** (lines 157–166).
- `AI_GENERATE_EMBEDDINGS` generates an embedding from character input using a precreated external model (line 168).
- `AI_GENERATE_CHUNKS` is a TVF: fixed chunking uses **character counts, not tokenizer counts**; `OVERLAP` is a **percentage 0–50**; returns chunk text, order, offset, length, optional chunk-set ID (line 172).

## 3. Safety rules before running the lab (lines 174–196)

1. **Disposable database only** — scenarios deliberately create duplicates, stale embeddings, RLS policies, vector indexes, model calls (3.1, line 178).
2. **Endpoint calls opt-in** — synthetic lab makes zero model calls; endpoint track separate and marked; read generated T-SQL and the model-call confirmation before executing (3.2, line 182).
3. **Preview/platform variability** — ANN, vector indexes, float16, AI features can be preview-gated or vary by platform/region/edition/index version. **Treat runtime probes as the source of truth** (3.3, lines 186–188).
4. **Index minimum: ≥100 rows with non-null vector values** before index creation; the lab creates 5,000 rows (3.4, line 192).
5. **Security context:** run diagnostics as the same effective principal as the user workflow; never a privileged connection bypassing RLS or metadata visibility (3.5, line 196).

## 4. Test tracks (table at lines 200–206)

| Track | Network/model calls | Workspaces exercised | Duration |
|---|---|---|---|
| A. Synthetic local corpus | None | Profile, Compare, Projection, exact Search, detached mode | Minutes |
| B. Vector index and ANN | None, but target capability required | Search, Index | Depends on index build |
| C. External embedding model | Remote, host-local, or ONNX | Pipeline, text Search, drift | Depends on endpoint/rows |
| D. Security and lifecycle | None by default | Permission states, RLS, cancel, pinned results | Minutes |
| E. Harness-only edge fixtures | None in product; test transport may be synthetic | Non-finite, truncation, legacy index, protocol errors | Automated test suite |

## 5. Capability probe script — run FIRST (lines 208–334)

Produces factual rows that must correspond to the capability popover and Index workspace. Verbatim:

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

IF OBJECT_ID(N'sys.vector_indexes') IS NOT NULL
BEGIN
    SELECT
        s.name AS schema_name,
        t.name AS table_name,
        i.name AS index_name,
        vi.type_desc,
        vi.distance_metric_desc,
        JSON_VALUE(vi.build_parameters, '$.Version') AS index_version,
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

IF OBJECT_ID(N'sys.dm_db_vector_indexes') IS NOT NULL
BEGIN
    BEGIN TRY
        SELECT
            s.name AS schema_name,
            t.name AS table_name,
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

**What it proves (lines 336–344):** engine + compat level; preview gate visibility/enabled state; remote REST and local AI runtime server gates; native vector columns with dimensions/base type; external models visible to the current principal; vector indexes and format version; whether the health DMV is present and readable.

## 6. Track A — deterministic synthetic corpus (lines 346–865)

### 6.1 Why synthetic (lines 348–367)
Real endpoints are nondeterministic, cost money, and can't freeze exact numeric findings. The synthetic corpus deliberately creates: five visible category clusters; unit-normalized baseline vectors; a wider Legal cluster; low-variance trailing dimensions; null/zero/near-zero vectors; high-norm outliers; exact duplicate groups; duplicated source text with different vectors; shared boilerplate; stale source text after embedding; mixed provenance labels with same dimensions; tenant/language/category/document/chunk keys. The vectors are "a stable numerical fixture designed to exercise the Workbench honestly" — not meaningful language embeddings (line 367).

### 6.2 Full lab setup T-SQL (lines 373–798) — VERBATIM

Run in a disposable SQL Server 2025 or Azure SQL database:

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

### 6.3 Expected stable facts — the acceptance ground truth (lines 800–814)

- **5,000 rows** total (1,000 documents × 5 chunks each).
- **12 null vectors** (chunk_id 1–12).
- **4 exact zero vectors** (chunk_id 13–16).
- **8 near-zero vectors** (chunk_id 17–24).
- **17 high-norm outliers** (chunk_id 25–41; not normalized; dim1 ≈ 4.5 + chunk_id×0.01).
- **12 exact duplicate groups covering 37 rows** (12 leaders at chunk_id 100–111 + 25 copies at 200–224).
- **50 rows with source text newer than stored embedding** (chunk_id 300–349).
- **50 rows with a different declared model/profile** (chunk_id 400–449; `LegacyModelV1` / `legacy-query-prefix|not-verified` / batch 0).
- **20 rows with identical source text but different vectors** (chunk_id 500–519).
- **100 rows with a repeated boilerplate prefix** (chunk_id 600–699; prefix `Copyright and confidentiality notice. Internal use only. `).
- **64-dimensional float32 vectors** (`VECTOR(64)`).
- Baseline provenance labels: `embedding_model = 'SyntheticClusterModel64'`, `embedding_profile = 'passage-prefix-v1|unit-norm'`, `embedding_batch_id = 1`.
- Vector construction: dim = category_code gets 2.00; dim = 5+category_code gets 0.80; dim = 10+tenant_id gets 0.35; dim = 15+chunk_order gets 0.20; dims 21–28 keyed by document_id%8 get 0.25; dims 61–64 nearly-zero (dim × 0.0000001 → low-variance trailing dims); deterministic CHECKSUM noise with **Legal cluster noise 0.00005 vs 0.00002 for others** (wider Legal spread). Baseline rows then `VECTOR_NORMALIZE(..., 'norm2')` (unit norm).
- `dbo.VectorLabSearchCorpus` = clean indexable copy: `chunk_id >= 42 AND embedding IS NOT NULL` (anomaly rows 1–41 excluded from cosine/ANN demos but kept in `VectorLabChunks` for Profile).

### 6.4 Recommended Workbench binding profile (lines 816–841) — verbatim

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

The Workbench should mark the profile as **user-declared or workspace-local** unless stored through an approved database metadata convention (line 841).

### 6.5 Detached-mode result query (lines 843–865)

```sql
SELECT
    chunk_id, document_id, tenant_id, category, language_code, chunk_order,
    label, chunk_text, source_modified_at, embedded_at,
    embedding_model, embedding_profile, duplicate_group, embedding
FROM dbo.VectorLabChunks
ORDER BY chunk_id;
```

Open Vector: **Profile, Compare, and Projection must be usable from the captured result without any new SQL** (line 865).

## 7. Manual demo scenarios by workspace (lines 867–1106)

### P-01 Profile — healthy baseline vs injected anomalies (lines 869–892)
Steps: run 5,000-row query (6.5) → open Vector → Profile → confirm source label says `captured result` or `bound table sample` accurately → 5,000-row sample → open findings for null/zero/near-zero/duplicate/norm-outlier/low-variance/freshness.
Expected: most baseline rows have L2 norm ≈ 1; high-norm rows a separate tail; null/zero/near-zero counts match setup; duplicate groups = 12 groups / 37 covered rows; **finding drawer says `Affected dimensions` for low-variance dims, not `Affected rows`**; Legal has wider within-group distance distribution; freshness identifies rows 300–349; provenance identifies rows 400–449 as dimension-compatible but not provenance-confirmed.

### P-02 Profile — duplicate text vs duplicate vectors (lines 894–909)
Inspect chunk 100–111 & 200–224 (vector duplicates) and 500–519 (duplicate text). Expected: vector duplicate groups are byte/component-equal; repeated-text rows do NOT necessarily have equal vectors (vectors generated before text overwrite). Different findings imply different failure classes.

### P-03 Profile — boilerplate / RAG crowding (lines 911–927)
Rows 600–699. Expected: identical boilerplate prefix raises similarity across unrelated documents; some rows appear unusually often in neighborhoods; top-K can contain multiple low-value chunks dominated by notice text. Rationale: global PCA may not reveal retrieval crowding.

### C-01 Compare — three category vectors (lines 929–961)
Rows `chunk_id IN (1001, 1006, 1011)`. Add as A, B, C; review cosine/Euclidean/negative dot/norms/pairwise matrix/centroid/medoid/closest pair; enter **`normalize(A + B - C)`** in the arithmetic lab; use result as a query vector against the bound table.
Expected: dimension-compatible; provenance declared compatible (same synthetic model/profile); **arithmetic output has a NEW local provenance state** (does not inherit original model profile); **nearest bound rows are labeled as a new server query, not local computation**.

### C-02 Compare — provenance mismatch, same dimensions (lines 963–985)
Rows `chunk_id IN (451, 401)` (`embedding_model`/`embedding_profile` differ). Expected: both 64-dim float32; tool reports dimension compatibility but does NOT report verified provenance compatibility. "Equal dimensions ≠ equal embedding spaces."

### R-01 Projection — five clusters (lines 987–1008)
PCA 2D, center only; color by `category`; **display 1,200 points while analyzing 5,000 if the render cap is configured that way**; select/reveal a point from each cluster.
Expected: five broad clusters; Legal more spread; **truth banner reports PC1, PC2, and the next component**; banner distinguishes analyzed vs rendered counts; **original-space ranking is not derived from plotted coordinates**.

### R-02 Projection — lasso and outliers (lines 1010–1027)
Lasso the outlier region → add selected points to Compare → reveal source rows → filter legend to one category **without recomputing PCA**.
Expected: selection synchronized with the accessible point list; legend filtering hides points without silently changing projection coordinates; outliers trace back to chunk 25–41.

### S-01 exact Search — selected-row query (lines 1029–1070)
Reference SQL (verbatim, lines 1031–1051):

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

Workbench steps: select row 1001 as query vector; metric Cosine, K 20; enable exact only; **confirm `Source row excluded by key` appears**; run.
Expected: source row not at distance zero; Technical rows dominate; exact search labeled **ground truth**; generated SQL matches exclusion and metric. Proves SQL generation, self-match handling, **stable tie-breaking** (secondary `ORDER BY c.chunk_id`), exact distance correctness.

### S-02 exact filtered Search — selective eligibility (lines 1072–1106)
Same query + `AND c.category = N'Technical' AND c.tenant_id = 1`. Expected: structured filter reported; eligible-row count / filter selectivity shown when measured; **if fewer than K rows eligible, exact denominator uses the actual row count**. Rationale: many "vector search failures" are ordinary eligibility failures.

## 8. Track B — vector index & ANN (lines 1108–1371)

### Enablement & creation
- Preview gate (review before running, don't auto-enable from the Workbench, lines 1116–1121):
  ```sql
  ALTER DATABASE SCOPED CONFIGURATION
  SET PREVIEW_FEATURES = ON;
  ```
- Create index (only after probe indicates `CREATE VECTOR INDEX` accepted, lines 1127–1135):
  ```sql
  CREATE VECTOR INDEX IX_VectorLabSearchCorpus_Embedding
  ON dbo.VectorLabSearchCorpus(embedding)
  WITH
  (
      METRIC = 'cosine',
      TYPE = 'diskann'
  );
  ```
- Index version check (lines 1139–1162): joins `sys.vector_indexes` → `sys.indexes` → `sys.tables` → `sys.schemas`; `JSON_VALUE(vi.build_parameters, '$.Version')`; classification: **`>= 3` = 'latest format', `< 3` = 'earlier format', else 'unknown format'**.

### Approximate query shapes (all three verbatim in source)
- **Current format (8.4, lines 1168–1193):** `SELECT TOP (20) WITH APPROXIMATE ... FROM VECTOR_SEARCH(TABLE = dbo.VectorLabSearchCorpus AS c, COLUMN = embedding, SIMILAR_TO = @q, METRIC = 'cosine') AS r WHERE c.chunk_id <> @query_chunk_id AND c.category = N'Technical' ORDER BY r.distance;`
- **Forced ANN (8.5, lines 1197–1222):** same shape with `) AS r WITH (FORCE_ANN_ONLY)`.
- **Earlier format (8.6, lines 1228–1259):** no `WITH APPROXIMATE`; instead `TOP_N = 100` inside `VECTOR_SEARCH(...)` with `SELECT TOP (@requested_k)`; example uses `@requested_k=20`, `@oversample_multiplier=5` → `TOP_N = 100`. **The literal `TOP_N` must be generated safely for the probed target; UI must disclose the oversample multiplier and post-filter semantics** (line 1259).

### S-03 Search comparison — flagship scenario (lines 1261–1286)
Steps: bind `dbo.VectorLabSearchCorpus` as Search/Index target; select chunk 1001; K 20, Cosine, Technical filter; enable exact + approximate + forced ANN where supported; run; open evidence panel and repro script.
**Required observations (acceptance, lines 1272–1282):**
- Exact and approximate use the **same frozen query vector**.
- Self-exclusion visible.
- Read consistency visible.
- Index version and filter semantics visible.
- **Forced ANN is claimed only when the forced statement succeeds.**
- **Recall denominator = 20 exact neighbors or the actual eligible count.**
- Rank grid contains the **union of both result sets**.
- **Timing says single observation or reports repeated-run statistics.**
- **Index staleness is stamped at run time when the DMV is available.**

### Index health & staleness (8.8–8.9, lines 1288–1346)
- Health query fields (verbatim column names): `approximate_staleness_percent`, `quantized_keys_used_percent`, `last_background_task_time`, `last_background_task_succeeded`, `last_background_task_duration_seconds`, `last_background_task_processed_inserts`, `last_background_task_processed_deletes`, `last_background_task_error_message` from `sys.dm_db_vector_indexes`.
- Staleness demo (8.9): UPDATE copies embeddings into chunk 3000–3499 (`embedding_batch_id = 99`, source = `1000 + ((target.chunk_id - 3000) % 200)`), then query the DMV; run Search comparison immediately and again after maintenance. Restore by re-running full synthetic setup. Demonstrates: staleness is a run-time condition; results stay available during maintenance; ranking quality can change; **the Workbench should not recommend a rebuild from one staleness value alone** (line 1345).

### Index screen state tests (8.10, lines 1347–1371)
- **Healthy current format:** version ≥3; metric matches; migration command absent; health/maintenance facts visible.
- **Earlier format:** version <3; migration command visible; **service-impact warning visible**; post-filter behavior and DML limitations visible.
- **No index:** explain exact search still works; offer generated create-index script **for review** (never auto-run).
- **Permission degraded:** catalog index visible but DMV unavailable → **UI says health unavailable rather than healthy**.

## 9. Track C — external embedding model (lines 1373–1665)

### Endpoint modes (table, lines 1377–1384)
| Mode | Egress | Use |
|---|---|---|
| Azure OpenAI | remote Azure endpoint | managed dev/prod-like lab |
| OpenAI | remote OpenAI endpoint | interoperability lab |
| Ollama | host-local HTTPS endpoint | local dev where configured |
| ONNX Runtime | local SQL Server runtime | Windows-only local-runtime lab |

**The Workbench confirmation text must vary by mode** (line 1386).

### Setup
- REST gate (SQL Server/MI; Azure SQL DB & Fabric enabled by default): `EXECUTE sys.sp_configure 'external rest endpoint enabled', 1; RECONFIGURE WITH OVERRIDE;` (lines 1391–1393).
- Azure OpenAI template (9.3, lines 1401–1432): `CREATE DATABASE SCOPED CREDENTIAL [https://<endpoint-host>/] WITH IDENTITY = 'HTTPEndpointHeaders', SECRET = '{"api-key":"<api-key>"}';` then `CREATE EXTERNAL MODEL VectorLabEmbeddingModel AUTHORIZATION dbo WITH (LOCATION = 'https://<endpoint-host>/openai/deployments/<deployment-name>/embeddings?api-version=2024-02-01', API_FORMAT = 'Azure OpenAI', MODEL_TYPE = EMBEDDINGS, MODEL = 'text-embedding-3-small', CREDENTIAL = [https://<endpoint-host>/], PARAMETERS = '{"dimensions":1536,"sql_rest_options":{"retry_count":3}}');` then `GRANT EXECUTE ON EXTERNAL MODEL::VectorLabEmbeddingModel TO [<database-principal>];`. Never commit the secret.
- **Identity note (line 1436): the model is `VectorLabEmbeddingModel`, not `dbo.VectorLabEmbeddingModel` — `dbo` is the owner.**
- Catalog verification (9.4): `sys.external_models` filtered `WHERE em.name = N'VectorLabEmbeddingModel'`.
- Smoke test (9.5, lines 1459–1466): `SELECT AI_GENERATE_EMBEDDINGS(N'Reset a multi-factor authentication device for an employee account.' USE MODEL VectorLabEmbeddingModel) AS generated_embedding;` — **the Workbench must present a confirmation before generating this from the UI** (line 1468).

### Real-embedding data (9.6–9.8, lines 1473–1585)
- `dbo.VectorLabRealChunks`: 120 rows copied from `VectorLabChunks WHERE chunk_id >= 1000` (TOP (120) ORDER BY chunk_id); columns chunk_id, document_id, category, label, chunk_text, source_modified_at, embedded_at, embedding_model, embedding_profile, `embedding VECTOR(1536) NULL`.
- **Smoke batch first — 5 rows** (9.7): `UPDATE ... SET embedding = AI_GENERATE_EMBEDDINGS(chunk_text USE MODEL VectorLabEmbeddingModel), embedded_at = SYSUTCDATETIME(), embedding_model = N'VectorLabEmbeddingModel', embedding_profile = N'passage-prefix-v1|provider-output' WHERE chunk_id IN (SELECT TOP (5) ... WHERE embedding IS NULL ...)`; verify dimensions/base type/norm2 before generating the rest.
- Full population (9.8): WHILE loop, `@batch_size = 10`, batches by `NextBatch` CTE until `@@ROWCOUNT = 0`. Review endpoint cost, rate limit, sensitivity first. **Cancellation should be tested; a remote request might already be in flight when cancellation is requested** (line 1585).

### Pipeline demos (9.9–9.11, lines 1587–1665)
- **L-01 re-embed selected row:** required observations (lines 1599–1608): model name and owner separate; API format and endpoint host shown; egress copy correct for mode; source row / text char count / approximate payload / call count / retry count shown; fresh vector dimensions validated; **result stays in the panel and is not written to the table**; stored-vs-fresh cosine/Euclidean/negative dot/norm/neighbor overlap/rank movement labeled with their search mode; **footer says `Webview network: none` and records the server-side model call separately**.
- **L-02 deliberate drift:** append `' The source content changed substantially after the stored embedding was created.'` and set `source_modified_at = DATEADD(day, 10, COALESCE(embedded_at, SYSUTCDATETIME()))` on TOP (10) embedded rows; re-embed one. Expected: freshness finding "source modified after embedding"; stored-vs-fresh distance larger than unchanged row; neighbor overlap / rank movement may change.
- **L-03 provenance mismatch:** set `embedding_model = N'PreviousEmbeddingDeployment'`, `embedding_profile = N'legacy-prefix-v0'` on TOP (10) DESC rows. Expected: dimensions still match; Workbench says **provenance mismatch or unknown rather than green compatibility**.

## 10. Chunking demos (lines 1667–1736)

- Preview (10.1): `CROSS APPLY AI_GENERATE_CHUNKS(SOURCE = d.body, CHUNK_TYPE = FIXED, CHUNK_SIZE = 800, OVERLAP = 15, ENABLE_CHUNK_SET_ID = 1) AS c` against `dbo.VectorLabDocuments WHERE d.document_id = 203`; output columns `chunk_set_id, chunk_order, chunk_offset, chunk_length, chunk`.
- Workbench steps: bind `body` as source text; size 800, overlap 15%; compare ribbon to `chunk_offset`/`chunk_length`; inspect tail chunk; change overlap to 0 and 30.
- **Required observations (lines 1700–1705):** UI says **characters, not tokens**; overlap regions visibly marked; chunk order/offset/length/tail shown; UI does not imply the endpoint tokenizer will accept every character chunk without truncation.
- 10.2 chunk-embedding query combines `AI_GENERATE_CHUNKS` + `AI_GENERATE_EMBEDDINGS(c.chunk USE MODEL VectorLabEmbeddingModel)` — can make multiple model calls; **preview and confirm the chunk count first** (line 1709).

## 11. Query-set evaluation (lines 1738–1808)

- One-query exact evaluation SQL (11.1, lines 1744–1789): TOP (20) cosine against `VectorLabSearchCorpus`, self-excluded, `ROW_NUMBER() OVER (ORDER BY r.distance, r.chunk_id) AS retrieval_rank`, LEFT JOIN `VectorLabExpectedRelevant` with `COALESCE(e.relevance_grade, 0)` / `COALESCE(e.relevance_reason, N'not expected')`.
- Relevance grading (from setup): grade 3 = same document, 1 = same category, 0 = not expected.
- **Workbench query-set mode report (11.2, lines 1795–1804), must include:** recall@20 per query; median and p5 recall; unique documents in top 20; same-document chunk count; **median and p95 exact/approximate latency**; worst query IDs; staleness at run time; **total statement count and cancellation state**.
- Rationale: "A single selected-row comparison finds a local bug. A query set characterizes the index and corpus" (line 1808).

## 12. Security / tenant-filter demo (lines 1810–1876)

Setup (verbatim key objects): `dbo.VectorLabTenantChunks` (1,000 rows from SearchCorpus); `dbo.fn_VectorLabTenantPredicate(@tenant_id int)` — SCHEMABINDING TVF returning `1 AS allowed WHERE @tenant_id = TRY_CONVERT(int, SESSION_CONTEXT(N'vector_lab_tenant_id'))`; `CREATE SECURITY POLICY dbo.VectorLabTenantPolicy ADD FILTER PREDICATE dbo.fn_VectorLabTenantPredicate(tenant_id) ON dbo.VectorLabTenantChunks WITH (STATE = ON);`; then `EXEC sys.sp_set_session_context @key = N'vector_lab_tenant_id', @value = 1;` and count visible rows.

**Workbench expectations (lines 1867–1872):** a table-bound diagnostic session must **reproduce required session context or disclose that it cannot**; must not see tenants hidden from the principal/session; exact and approximate comparisons use the same tenant filter and security context; eligible-row count reflects the authorized view. Rationale: "A faster ANN query is useless if it crosses an authorization boundary."

## 13. Permission-degraded demos (lines 1878–1918)

- **13.1 Health DMV unavailable:** `CREATE USER VectorLabLimited WITHOUT LOGIN; GRANT SELECT ON dbo.VectorLabChunks TO VectorLabLimited; EXECUTE AS USER = 'VectorLabLimited';` then TRY/CATCH select from `sys.dm_db_vector_indexes`; `REVERT;`. Assert Workbench shows **`Health unavailable` rather than `Healthy`** (principal lacks `VIEW DATABASE STATE`). For end-to-end Query Studio, use a real least-privilege login/contained user (line 1908).
- **13.2 Model visible but not executable:** principal reading table but lacking `GRANT EXECUTE ON EXTERNAL MODEL::VectorLabEmbeddingModel` → Pipeline stays useful for local profiling and shows a clear model-execution permission state.

## 14. Lifecycle, result-store, and UI tests (lines 1920–1947)

- **14.1 Rerun while Profile preparation active:** run 5,000-row result → start analysis with a **deliberately low work-slice budget** → rerun query → old analysis cancels, no stale findings in the new run → **old result-store lease is released**.
- **14.2 Switch workspaces during analysis:** switching away cancels work not intentionally retained; completed bounded local data may remain session-local only under the approved lifetime policy; **no hidden worker or server query continues without a visible task state**.
- **14.3 Pin results:** pin → rerun/close original editor → open pinned Vector pane → Profile/Compare/Projection use the **frozen snapshot**; **table-bound Search or Pipeline requires an explicit current connection and binding rather than pretending the pinned rows are a live table**.
- **14.4 Cancel Search comparison:** cancel during exact, approximate, and repeated-query-set runs → UI must report **which statements completed, which results are partial, and whether the cancel acknowledgement was certain**.

## 15. Harness-only edge cases (table, lines 1949–1967)

Not reliably/responsibly manufactured with T-SQL on every target — belong in unit/integration/protocol-fixture tests:

| Scenario | Required UI result |
|---|---|
| Non-finite components (NaN/inf) | Finding appears only when real typed input proves it exists |
| Native vector transport truncation (controlled STS2 cell/frame limits) | Honest unavailable/truncated state, **never partial vector math** |
| Malformed tagged vector payload | Query fails or cell unavailable; **no crash** |
| Earlier v2 index | Preserved test DB, captured fixture, or mocked catalog/SQL responses |
| Regional syntax rollout mismatch | Capability probe + syntax-test fixture |
| Health DMV background failure | Mocked DMV row or controlled service fault |
| Quantized-key saturation | DMV fixture |
| Metadata hidden but data readable | Degraded capability state |
| Model returns wrong dimension | Fake endpoint or test model |
| Endpoint 429/500/retry | Fake HTTPS endpoint or provider test double |
| Cancellation during in-flight REST call | Fake endpoint with deterministic delay |
| Exact/approximate concurrent-change race | Integration harness with barriers |
| Compact capture privacy canary | Service unit/integration test; **no canary in persisted artifact** |

## 16. Automated acceptance matrix — the "done" definition (lines 1969–2045)

### 16.1 SQL Tools Service
- Native float32 **`SqlVector<float>`** recognized and encoded losslessly.
- Vector cells have honest byte accounting.
- Compact and noncompact rows normalize identically.
- Oversized vector yields a **complete unavailable marker, not a prefix**.
- Capture elides complete compact payloads.
- **Journal and diagnostic exports contain no vector canaries.**
- Query cancel and frame guard remain deterministic.

### 16.2 SQL Data Plane and result store
- Vector metadata reaches **`QsResultColumn`**.
- Typed vector cells spill and restore.
- Sparse projection returns vector plus distant label **in one materialization**.
- **Vector-analysis read reason does not evict grid viewport pages.**
- Host sessions release leases on completion, cancellation, expiry, rerun, hide, and disposal.
- **Webview cannot raise row, component, byte, or time budgets.**

### 16.3 Profile
- Stable counts for every injected anomaly; finding subject units correct; sample method and bias disclosure present; **cancellation returns partial scope**; group sizes/statistics align; **duplicate groups and covered rows are distinct values**.

### 16.4 Search
- Query vector frozen once; self-exclusion identical across variants; **structured filters parameterized**; read consistency recorded; exact denominator correct; rank union complete; forced ANN proof classified correctly; earlier post-filter behavior disclosed; **staleness stamped at measurement time**; **repro script matches executed SQL**.

### 16.5 Compare
- Metric formulas and component indexing documented; zero-vector cosine state handled; dimension vs provenance compatibility separated; **arithmetic parser never evaluates JavaScript**; local vs server evidence source distinct.

### 16.6 Projection
- Deterministic PCA and sign normalization; analyzed vs rendered counts separate; original-space neighbors remain original-space; point list and canvas selection synchronize; **high contrast and keyboard navigation pass**.

### 16.7 Index
- Healthy current format hides migration; earlier format shows migration + service-impact warning; **every DMV field mapped correctly**; missing permission is not reported as health; **generated scripts never execute automatically**; limitations/prerequisites accurate for probed target.

### 16.8 Pipeline
- **No automatic model call on open**; confirmation content varies by egress class; full source text never silently replaced with a truncated prefix; model dimension validated; **model object identity is not schema-qualified**; retry and cancellation state represented; **remote source text and vectors absent from telemetry and logs**.

## 17. UX evaluation script — 20–30-minute demo sequence (lines 2047–2067)

1. Run the capability probe. 2. Run the synthetic setup. 3. Open the full 5,000-row result. 4. Profile the corpus; open duplicate and low-variance drawers. 5. Add three rows to Compare; run one arithmetic expression. 6. Projection: color by category, lasso an outlier, reveal it. 7. Exact selected-row Search with self-exclusion. 8. If index supported: create it and run exact/approximate/forced comparison. 9. Open Index; show current-format health or legacy state. 10. Configure/select an external model. 11. Pipeline: re-embed one unchanged row, then one deliberately stale row. 12. Preview fixed-character chunks and display expected model-call count. 13. Cancel one long operation. 14. Pin results and prove detached Profile/Compare/Projection survive a rerun. 15. Switch to least-privilege connection; show degraded metadata honestly.

**Emphasis:** "spend more time on evidence rows and row-to-SQL traceability than on the PCA picture. That is the product distinction." (line 2067)

## 18. Cleanup (lines 2069–2102)

**Drop the vector index FIRST** — a vector-indexed table cannot be truncated and may have target-specific DML behavior (line 2071). Conditional `DROP INDEX IX_VectorLabSearchCorpus_Embedding ON dbo.VectorLabSearchCorpus;` then, in order: `DROP SECURITY POLICY IF EXISTS dbo.VectorLabTenantPolicy; DROP FUNCTION IF EXISTS dbo.fn_VectorLabTenantPredicate; DROP TABLE IF EXISTS dbo.VectorLabTenantChunks; ...VectorLabRealChunks; ...VectorLabExpectedRelevant; ...VectorLabSearchQueries; ...VectorLabSearchCorpus; ...VectorLabChunks; ...VectorLabDocuments; DROP USER IF EXISTS VectorLabLimited;`. Optional (commented, review dependencies first): `DROP EXTERNAL MODEL VectorLabEmbeddingModel;` and `DROP DATABASE SCOPED CREDENTIAL [https://<endpoint-host>/];`.

## 19. Troubleshooting checklist (lines 2104–2156)

- **Vector tab does not appear:** result metadata identifies a native vector column; **feature gate and negotiated typed-vector capability**; result is not only a plan result; cell not downgraded to generic text by an older driver path.
- **Profile sample smaller than requested:** row count; null/unavailable rows; **component budget (dimensions × rows)**; **packed-byte budget**; **row-scan cap and elapsed-time budget**; read the partial reason.
- **Search has fewer than K rows:** eligible-row count; self/same-document exclusion; RLS/tenant filters; earlier-index post-filter behavior; null vectors; check exact denominator before blaming ANN.
- **Approximate search not proven:** index existence/column/metric; current vs earlier syntax; `WITH APPROXIMATE`; `FORCE_ANN_ONLY` capability and placement; whether the optimizer chose exact kNN; open generated SQL and evidence.
- **Pipeline model call fails:** model object name/type/owner/grants; endpoint or local-runtime configuration gate; **credential URL matching rules**; HTTPS and allowlist requirements; retry count and endpoint status; XEvents when permitted; output dimensions before storing.
- **Projection looks impressive but retrieval is poor:** projection is lossy; inspect explained variance; compare original-space neighbors; run exact Search + query-set benchmark; check boilerplate/duplicates/chunk crowding/provenance.

## 20. Primary documentation (lines 2158–2175)

Microsoft Learn (checked 2026-07-11, `view=sql-server-ver17`): Vector data type; `VECTORPROPERTY`; `VECTOR_NORM`; `VECTOR_NORMALIZE`; `VECTOR_DISTANCE`; `VECTOR_SEARCH`; `CREATE VECTOR INDEX`; `sys.vector_indexes`; `sys.dm_db_vector_indexes`; `CREATE EXTERNAL MODEL`; `sys.external_models`; `AI_GENERATE_EMBEDDINGS`; `AI_GENERATE_CHUNKS`.

## Perf-validation notes relevant to the build's performance goals

The guide's performance-relevant checks (dispersed; consolidated here):

1. **Budgets are enforced host-side:** the webview cannot raise row, component, byte, or time budgets (16.2). Profile sampling respects a component budget (dimensions × rows), a packed-byte budget, a row-scan cap, and an elapsed-time budget, and must disclose the partial reason (19).
2. **Latency reporting is a product feature:** Search timing must say "single observation" or report repeated-run statistics (8.7); query-set mode must report median and p95 exact/approximate latency plus total statement count (11.2).
3. **Result-store isolation:** vector-analysis reads must not evict grid viewport pages; typed vector cells spill/restore; leases released on completion/cancel/expiry/rerun/hide/disposal (16.2, 14.1).
4. **Render vs analyze split:** Projection can analyze 5,000 while rendering a capped 1,200; banner must separate the counts (7.6).
5. **Work-slice budgets and cancellation:** Profile runs with a configurable low work-slice budget for rerun-cancellation testing (14.1); cancellation must return partial scope (16.3) and report per-statement completion/partial/ack-certainty (14.4).
6. **The 5,000-row × 64-dim synthetic corpus is the standard perf/functional fixture**; Track A completes "in a few minutes" with zero network calls (section 4 table).
