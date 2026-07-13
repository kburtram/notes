-- vectorlab_setup_azure.sql
-- Azure SQL Database adaptation of vectorlab_setup.sql (Track A deterministic
-- synthetic vector lab corpus; guide source: vector_workbench_test_and_demo_guide.md
-- section 6.2, lines 374-797).
--
-- Differences from vectorlab_setup.sql, and nothing else:
--   1. The CREATE DATABASE / USE header is removed (Azure SQL Database is
--      single-database scope; run this connected to the target database).
--   2. Objects live in schema [vectorlab] instead of a dedicated VectorLab
--      database: every dbo.VectorLab* reference is renamed to
--      vectorlab.VectorLab* (CREATE/DROP/INSERT/UPDATE/FK REFERENCES/joins).
--      The schema is created if missing.
--   3. The guide's compatibility-level raise is ALSO run here in the header,
--      in its own batch. The guide's verbatim SQL raises the level inside the
--      main batch, which only works when the database already meets the
--      requirement at batch-compile time: verified live on Azure SQL
--      (2026-07-11, database at compat 150) that the same-batch raise does not
--      rescue GENERATE_SERIES — the batch fails with Msg 208 "Invalid object
--      name 'GENERATE_SERIES'" even though the ALTER executes. Raising the
--      level in a separate earlier batch fixes compilation; the verbatim
--      in-batch block below is kept and becomes a no-op.
--   4. This header.
-- The data generation SQL is otherwise byte-faithful to the guide
-- (GENERATE_SERIES needs compat >= 160; VECTOR features are surfaced fully
-- at 170).
--
-- Run: sqlcmd -S tcp:<server>,1433 -d <db> -U <user> -P <pw> -C -l 30 -i vectorlab_setup_azure.sql

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'vectorlab')
BEGIN
    EXEC (N'CREATE SCHEMA vectorlab;');
END;
GO

-- Header batch: raise compatibility level BEFORE the main batch compiles
-- (see header note 3).
IF (SELECT compatibility_level FROM sys.databases WHERE database_id = DB_ID()) < 170
BEGIN
    DECLARE @compat_sql_header nvarchar(max) =
        N'ALTER DATABASE ' + QUOTENAME(DB_NAME()) + N' SET COMPATIBILITY_LEVEL = 170;';
    EXEC sys.sp_executesql @compat_sql_header;
END;
GO

-- ============================================================================
-- Everything below this line is the guide's section 6.2 SQL, verbatim except
-- for the dbo.VectorLab* -> vectorlab.VectorLab* renames described above.
-- ============================================================================
SET NOCOUNT ON;
SET XACT_ABORT ON;

IF (SELECT compatibility_level FROM sys.databases WHERE database_id = DB_ID()) < 170
BEGIN
    DECLARE @compat_sql nvarchar(max) =
        N'ALTER DATABASE ' + QUOTENAME(DB_NAME()) + N' SET COMPATIBILITY_LEVEL = 170;';
    EXEC sys.sp_executesql @compat_sql;
END;

DROP TABLE IF EXISTS vectorlab.VectorLabExpectedRelevant;
DROP TABLE IF EXISTS vectorlab.VectorLabSearchQueries;
DROP TABLE IF EXISTS vectorlab.VectorLabSearchCorpus;
DROP TABLE IF EXISTS vectorlab.VectorLabChunks;
DROP TABLE IF EXISTS vectorlab.VectorLabDocuments;

CREATE TABLE vectorlab.VectorLabDocuments
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

CREATE TABLE vectorlab.VectorLabChunks
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
        REFERENCES vectorlab.VectorLabDocuments(document_id)
);

INSERT vectorlab.VectorLabDocuments
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

INSERT vectorlab.VectorLabChunks
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
FROM vectorlab.VectorLabDocuments AS d
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
    FROM vectorlab.VectorLabChunks AS c
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
FROM vectorlab.VectorLabChunks AS c
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
UPDATE vectorlab.VectorLabChunks
SET embedding = NULL,
    embedded_at = NULL
WHERE chunk_id BETWEEN 1 AND 12;

-- Exact zero vectors: 4 rows.
UPDATE vectorlab.VectorLabChunks
SET embedding = CAST(@zero_vector AS VECTOR(64))
WHERE chunk_id BETWEEN 13 AND 16;

-- Near-zero vectors: 8 rows.
UPDATE vectorlab.VectorLabChunks
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
    FROM vectorlab.VectorLabChunks AS c
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
FROM vectorlab.VectorLabChunks AS c
JOIN VectorJson AS v
    ON v.chunk_id = c.chunk_id;

-- Twelve duplicate groups covering 37 rows in total:
-- 12 leaders plus 25 copied members.
UPDATE vectorlab.VectorLabChunks
SET duplicate_group = chunk_id - 99
WHERE chunk_id BETWEEN 100 AND 111;

;WITH Targets AS
(
    SELECT
        c.chunk_id,
        1 + ((c.chunk_id - 200) % 12) AS duplicate_group
    FROM vectorlab.VectorLabChunks AS c
    WHERE c.chunk_id BETWEEN 200 AND 224
)
UPDATE target
SET target.embedding = leader.embedding,
    target.duplicate_group = t.duplicate_group
FROM vectorlab.VectorLabChunks AS target
JOIN Targets AS t
    ON t.chunk_id = target.chunk_id
JOIN vectorlab.VectorLabChunks AS leader
    ON leader.chunk_id = 99 + t.duplicate_group;

-- Source text changed after embedding: 50 stale rows.
UPDATE vectorlab.VectorLabChunks
SET chunk_text = CONCAT(chunk_text, N' UPDATED AFTER THE STORED EMBEDDING WAS CREATED.'),
    source_modified_at = DATEADD(day, 30, embedded_at)
WHERE chunk_id BETWEEN 300 AND 349;

-- Same dimensions, different declared provenance: 50 rows.
UPDATE vectorlab.VectorLabChunks
SET embedding_model = N'LegacyModelV1',
    embedding_profile = N'legacy-query-prefix|not-verified',
    embedding_batch_id = 0
WHERE chunk_id BETWEEN 400 AND 449;

-- Same source text, deliberately different vectors: 20 rows.
UPDATE vectorlab.VectorLabChunks
SET chunk_text = N'This standard confidentiality notice is repeated verbatim across unrelated documents.'
WHERE chunk_id BETWEEN 500 AND 519;

-- Shared boilerplate prefix: 100 rows.
UPDATE vectorlab.VectorLabChunks
SET chunk_text = CONCAT
(
    N'Copyright and confidentiality notice. Internal use only. ',
    chunk_text
)
WHERE chunk_id BETWEEN 600 AND 699;

-- A clean, indexable search target. The structural anomaly rows 1 through 41
-- stay in VectorLabChunks for Profile, but are excluded from cosine/ANN demos.
CREATE TABLE vectorlab.VectorLabSearchCorpus
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

INSERT vectorlab.VectorLabSearchCorpus
(
    chunk_id, document_id, tenant_id, category, language_code, chunk_order,
    label, chunk_text, source_modified_at, embedded_at,
    embedding_model, embedding_profile, embedding_batch_id, embedding
)
SELECT
    chunk_id, document_id, tenant_id, category, language_code, chunk_order,
    label, chunk_text, source_modified_at, embedded_at,
    embedding_model, embedding_profile, embedding_batch_id, embedding
FROM vectorlab.VectorLabChunks
WHERE chunk_id >= 42
  AND embedding IS NOT NULL;

CREATE TABLE vectorlab.VectorLabSearchQueries
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
        REFERENCES vectorlab.VectorLabChunks(chunk_id)
);

INSERT vectorlab.VectorLabSearchQueries
(query_id, query_name, source_chunk_id, expected_category, default_filter)
VALUES
(1, N'Technical selected-row query', 1001, N'Technical', N'category = Technical'),
(2, N'Billing selected-row query',   1006, N'Billing',   N'category = Billing'),
(3, N'Legal selected-row query',     1011, N'Legal',     N'category = Legal'),
(4, N'Support selected-row query',   1016, N'Support',   N'category = Support'),
(5, N'Other selected-row query',     1021, N'Other',     N'category = Other');

CREATE TABLE vectorlab.VectorLabExpectedRelevant
(
    query_id int NOT NULL,
    chunk_id int NOT NULL,
    relevance_grade tinyint NOT NULL,
    relevance_reason nvarchar(100) NOT NULL,
    CONSTRAINT PK_VectorLabExpectedRelevant
        PRIMARY KEY CLUSTERED (query_id, chunk_id),
    CONSTRAINT FK_VectorLabExpectedRelevant_Query
        FOREIGN KEY (query_id)
        REFERENCES vectorlab.VectorLabSearchQueries(query_id),
    CONSTRAINT FK_VectorLabExpectedRelevant_Chunk
        FOREIGN KEY (chunk_id)
        REFERENCES vectorlab.VectorLabChunks(chunk_id)
);

INSERT vectorlab.VectorLabExpectedRelevant
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
FROM vectorlab.VectorLabSearchQueries AS q
JOIN vectorlab.VectorLabChunks AS source
    ON source.chunk_id = q.source_chunk_id
JOIN vectorlab.VectorLabSearchCorpus AS c
    ON c.document_id = source.document_id OR c.category = q.expected_category;

SELECT
    COUNT(*) AS total_rows,
    SUM(CASE WHEN embedding IS NOT NULL THEN 1 ELSE 0 END) AS non_null_vectors,
    MIN(VECTORPROPERTY(embedding, 'Dimensions')) AS min_dimensions,
    MAX(VECTORPROPERTY(embedding, 'Dimensions')) AS max_dimensions,
    MIN(VECTOR_NORM(embedding, 'norm2')) AS min_norm2,
    MAX(VECTOR_NORM(embedding, 'norm2')) AS max_norm2
FROM vectorlab.VectorLabChunks;
