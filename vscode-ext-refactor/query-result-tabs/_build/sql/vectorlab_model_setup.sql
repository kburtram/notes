/* ============================================================================
   VectorLab external embedding model setup (Track C / VEC-10 Pipeline testing)
   APPLY MANUALLY — replace every <PLACEHOLDER> before running. Never commit
   real endpoints or keys. Target: SQL Server 2025 (VectorLab DB) and/or
   Azure SQL DB (adjust schema per environment).

   Prereqs by environment:
   - Box SQL 2025: sysadmin must enable the external endpoint gate once:
        EXEC sp_configure 'external rest endpoint enabled', 1; RECONFIGURE;
     (instance-level; also verify 'external AI runtimes enabled' if using ONNX)
   - Azure SQL DB: no sp_configure; external REST is governed by the
     database's outbound firewall rules — allow the endpoint host.
   ========================================================================= */

-- 1. Database-scoped credential for the endpoint (key never in model DDL).
--    Endpoint host must match the model URL's host exactly.
IF NOT EXISTS (SELECT 1 FROM sys.database_scoped_credentials WHERE name = 'https://<ENDPOINT-HOST>/')
    CREATE DATABASE SCOPED CREDENTIAL [https://<ENDPOINT-HOST>/]
    WITH IDENTITY = 'HTTPEndpointHeaders',
         SECRET = '{"api-key":"<API-KEY>"}';
GO

-- 2. External model (DATABASE-SCOPED object — never schema-qualify when
--    referencing it from AI_GENERATE_EMBEDDINGS; readiness review P0-4).
--    Azure OpenAI URL shape:
--    https://<ENDPOINT-HOST>/openai/deployments/<DEPLOYMENT>/embeddings?api-version=2024-02-01
IF NOT EXISTS (SELECT 1 FROM sys.external_models WHERE name = 'VectorLabEmbeddingModel')
    CREATE EXTERNAL MODEL VectorLabEmbeddingModel
    WITH (
        LOCATION = 'https://<ENDPOINT-HOST>/openai/deployments/<DEPLOYMENT>/embeddings?api-version=2024-02-01',
        API_FORMAT = 'Azure OpenAI',
        MODEL_TYPE = EMBEDDINGS,
        MODEL = '<MODEL-NAME e.g. text-embedding-3-small>',
        CREDENTIAL = [https://<ENDPOINT-HOST>/],
        PARAMETERS = '{"dimensions":1536}'
    );
GO

-- 3. Grant for the test principal(s) that the extension connects as.
-- GRANT EXECUTE ON EXTERNAL MODEL::VectorLabEmbeddingModel TO [<principal>];

-- 4. Smoke test (ONE call; verify shape + cost before any batch work):
-- SELECT AI_GENERATE_EMBEDDINGS(N'hello vector workbench' USE MODEL VectorLabEmbeddingModel) AS embedding;

-- 5. Probe rows the Workbench capability ladder reads (verify after setup):
-- SELECT name, model_type_desc, api_format, location FROM sys.external_models;
-- SELECT name, value FROM sys.configurations WHERE name LIKE 'external%';  -- box SQL only
