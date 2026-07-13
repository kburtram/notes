-- vectorlab_probe.sql
-- Capability probe for the Vector Workbench. Run FIRST, in the target database
-- (e.g. sqlcmd -S localhost -E -C -d VectorLab -i vectorlab_probe.sql).
-- Source of truth: coding-docs/query-result-tabs/vector_workbench_test_and_demo_guide.md,
-- section 5 (guide lines 213-333). The SQL text is verbatim; the only additions are
-- this header and GO batch separators between the guide's top-level statements, so
-- that a statement that does not compile on a given build cannot abort the whole probe.
--
-- KNOWN DISCREPANCY (verified 2026-07-11 against SQL Server 2025 RTM 17.0.1000.7):
--   The sys.vector_indexes batch fails with Msg 207 "Invalid column name
--   'distance_metric_desc'". On this build sys.vector_indexes exposes
--   'distance_metric' and 'vector_index_type' instead of a *_desc metric column.
--   The guide's SQL is kept as written; treat runtime probes as the source of truth
--   for the actual connection (guide section 3.3).
--
-- Result sets, in order:
--   1. Engine version, edition, database, compatibility level.
--   2. PREVIEW_FEATURES / ALLOW_STALE_VECTOR_INDEX database-scoped configurations.
--   3. 'external rest endpoint enabled' / 'external AI runtimes enabled' server configs.
--   4. Native vector columns visible in this database (dimensions, base type).
--   5. External models (only when sys.external_models exists).
--   6. Vector indexes and format version (only when sys.vector_indexes exists;
--      fails on 17.0.1000.7 RTM, see above).
--   7. Vector index health DMV facts (only when sys.dm_db_vector_indexes exists;
--      absent on 17.0.1000.7 RTM, so the batch is skipped).

SET NOCOUNT ON;
GO

SELECT
    SERVERPROPERTY('ProductVersion') AS product_version,
    SERVERPROPERTY('ProductLevel') AS product_level,
    SERVERPROPERTY('Edition') AS edition,
    SERVERPROPERTY('EngineEdition') AS engine_edition,
    DB_NAME() AS database_name,
    d.compatibility_level
FROM sys.databases AS d
WHERE d.database_id = DB_ID();
GO

SELECT
    name,
    value,
    value_for_secondary,
    is_value_default
FROM sys.database_scoped_configurations
WHERE name IN (N'PREVIEW_FEATURES', N'ALLOW_STALE_VECTOR_INDEX')
ORDER BY name;
GO

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
GO

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
GO

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
GO

-- CORRECTED 2026-07-11 (was distance_metric_desc — Msg 207 on RTM AND Azure;
-- Karl confirmed distance_metric fixes it locally; guide updated to match).
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
GO

-- CORRECTED 2026-07-11: the DMV is absent on RTM; on Azure its REAL columns
-- differ from the guide's earlier draft (`graph_catchup_pending_percent`,
-- `last_background_task_execution_time`). Tolerant projection works on any
-- shape; product code resolves exact names per connection (sys.all_columns).
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
GO
