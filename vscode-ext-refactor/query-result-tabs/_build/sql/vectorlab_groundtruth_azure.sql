-- vectorlab_groundtruth_azure.sql
-- Azure SQL Database adaptation of vectorlab_groundtruth.sql: acceptance
-- queries for the corpus created by vectorlab_setup_azure.sql.
-- Expected values come from the guide's stated ground truth
-- (vector_workbench_test_and_demo_guide.md, section 6.3, lines 800-814).
--
-- Differences from vectorlab_groundtruth.sql, and nothing else:
--   1. The USE VectorLab statement is removed (Azure SQL Database is
--      single-database scope; run this connected to the target database).
--   2. Every dbo.VectorLab* reference is renamed to vectorlab.VectorLab*.
--
-- Run: sqlcmd -S tcp:<server>,1433 -d <db> -U <user> -P <pw> -C -l 30 -i vectorlab_groundtruth_azure.sql
--
-- Result set 1: one row per anomaly class, expected vs observed, PASS/FAIL.
--   Detection is semantic where the anomaly is observable from the data
--   (null / zero / near-zero / high-norm / stale / provenance / same-text /
--   boilerplate); the duplicate-group rows use the planted duplicate_group
--   marker because the guide's 12-groups/37-rows figure refers to the
--   deliberately planted groups (chunk_id 100-111 leaders + 200-224 copies),
--   not to every byte-equal vector in the table (the 4 zero and 8 near-zero
--   rows are also byte-equal within their class; see result set 2).
-- Result set 2: informational full-scan exact-duplicate census (no PASS/FAIL).

SET NOCOUNT ON;

SELECT
    metric,
    expected,
    observed,
    CASE WHEN expected = observed THEN 'PASS' ELSE 'FAIL' END AS status
FROM
(
    SELECT N'01 total chunk rows' AS metric, 5000 AS expected,
           (SELECT COUNT(*) FROM vectorlab.VectorLabChunks) AS observed
    UNION ALL
    SELECT N'02 null vectors', 12,
           (SELECT COUNT(*) FROM vectorlab.VectorLabChunks
            WHERE embedding IS NULL)
    UNION ALL
    SELECT N'03 exact zero vectors', 4,
           (SELECT COUNT(*) FROM vectorlab.VectorLabChunks
            WHERE embedding IS NOT NULL
              AND VECTOR_NORM(embedding, 'norm2') = 0)
    UNION ALL
    SELECT N'04 near-zero vectors', 8,
           (SELECT COUNT(*) FROM vectorlab.VectorLabChunks
            WHERE VECTOR_NORM(embedding, 'norm2') > 0
              AND VECTOR_NORM(embedding, 'norm2') < 0.001)
    UNION ALL
    SELECT N'05 high-norm outliers', 17,
           (SELECT COUNT(*) FROM vectorlab.VectorLabChunks
            WHERE VECTOR_NORM(embedding, 'norm2') > 2)
    UNION ALL
    SELECT N'06 duplicate groups (planted)', 12,
           (SELECT COUNT(DISTINCT duplicate_group) FROM vectorlab.VectorLabChunks
            WHERE duplicate_group IS NOT NULL)
    UNION ALL
    SELECT N'07 duplicate rows covered (planted)', 37,
           (SELECT COUNT(*) FROM vectorlab.VectorLabChunks
            WHERE duplicate_group IS NOT NULL)
    UNION ALL
    -- Every planted group must be internally vector-equal; expect 0 mismatched groups.
    SELECT N'08 planted dup groups with unequal vectors', 0,
           (SELECT COUNT(*) FROM
               (SELECT duplicate_group
                FROM vectorlab.VectorLabChunks
                WHERE duplicate_group IS NOT NULL
                GROUP BY duplicate_group
                HAVING COUNT(DISTINCT HASHBYTES('SHA2_256',
                           CONVERT(nvarchar(max), embedding))) > 1) AS bad)
    UNION ALL
    SELECT N'09 stale source text (modified after embed)', 50,
           (SELECT COUNT(*) FROM vectorlab.VectorLabChunks
            WHERE source_modified_at > embedded_at)
    UNION ALL
    SELECT N'10 provenance mismatch (LegacyModelV1)', 50,
           (SELECT COUNT(*) FROM vectorlab.VectorLabChunks
            WHERE embedding_model = N'LegacyModelV1')
    UNION ALL
    SELECT N'11 same text, different vectors', 20,
           (SELECT COUNT(*)
            FROM
            (
                SELECT
                    HASHBYTES('SHA2_256', chunk_text) AS text_hash,
                    HASHBYTES('SHA2_256', CONVERT(nvarchar(max), embedding)) AS vector_hash
                FROM vectorlab.VectorLabChunks
                WHERE embedding IS NOT NULL
            ) AS h
            WHERE h.text_hash IN
            (
                SELECT text_hash
                FROM
                (
                    SELECT
                        HASHBYTES('SHA2_256', chunk_text) AS text_hash,
                        HASHBYTES('SHA2_256', CONVERT(nvarchar(max), embedding)) AS vector_hash
                    FROM vectorlab.VectorLabChunks
                    WHERE embedding IS NOT NULL
                ) AS g
                GROUP BY text_hash
                HAVING COUNT(*) > 1
                   AND COUNT(DISTINCT vector_hash) > 1
            ))
    UNION ALL
    SELECT N'12 boilerplate prefix rows', 100,
           (SELECT COUNT(*) FROM vectorlab.VectorLabChunks
            WHERE chunk_text LIKE N'Copyright and confidentiality notice. Internal use only. %')
    UNION ALL
    SELECT N'13 documents', 1000,
           (SELECT COUNT(*) FROM vectorlab.VectorLabDocuments)
    UNION ALL
    -- 5,000 chunks minus 12 null vectors.
    SELECT N'14 non-null vectors', 4988,
           (SELECT COUNT(*) FROM vectorlab.VectorLabChunks WHERE embedding IS NOT NULL)
    UNION ALL
    -- Clean corpus = chunk_id >= 42 AND embedding IS NOT NULL = 5000 - 41.
    SELECT N'15 search corpus rows', 4959,
           (SELECT COUNT(*) FROM vectorlab.VectorLabSearchCorpus)
    UNION ALL
    SELECT N'16 vector dimensions (min)', 64,
           (SELECT MIN(CAST(VECTORPROPERTY(embedding, 'Dimensions') AS int))
            FROM vectorlab.VectorLabChunks WHERE embedding IS NOT NULL)
    UNION ALL
    SELECT N'17 vector dimensions (max)', 64,
           (SELECT MAX(CAST(VECTORPROPERTY(embedding, 'Dimensions') AS int))
            FROM vectorlab.VectorLabChunks WHERE embedding IS NOT NULL)
    UNION ALL
    SELECT N'18 search queries', 5,
           (SELECT COUNT(*) FROM vectorlab.VectorLabSearchQueries)
) AS checks
ORDER BY metric;

-- Informational: full-scan census of byte-equal vector groups (groups of size > 1).
-- The planted 12 groups / 37 rows are expected to appear here alongside the
-- zero-vector class (1 group / 4 rows) and the near-zero class (1 group / 8 rows),
-- i.e. 14 groups covering 49 rows in a naive whole-table scan.
SELECT
    COUNT(*) AS exact_duplicate_vector_groups_full_scan,
    SUM(rows_in_group) AS rows_covered_full_scan
FROM
(
    SELECT HASHBYTES('SHA2_256', CONVERT(nvarchar(max), embedding)) AS vector_hash,
           COUNT(*) AS rows_in_group
    FROM vectorlab.VectorLabChunks
    WHERE embedding IS NOT NULL
    GROUP BY HASHBYTES('SHA2_256', CONVERT(nvarchar(max), embedding))
    HAVING COUNT(*) > 1
) AS g;
