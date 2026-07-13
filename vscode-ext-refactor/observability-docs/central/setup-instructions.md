# Central Observability — Setup Instructions (Karl)

What I could not do from an unelevated shell / without external accounts, plus how the local pieces are wired today. Everything else (schema, writers, tests, dashboards-as-code) is built and committed.

## 1. Local central store — what exists NOW (no action needed)

- **The store lives in the perftest SQL container** `perftest-sqlserver` (SQL 2022, pinned digest, port **14333**): `docker compose -f sql/docker-compose.sqlserver.yml up -d --wait` (already running). DBs: `PerfCentral` (dogfood store — initialized, check-green, **131 local runs backfilled**), `PerfCentralTest` (integration tests).
- User env vars (set via setx; new shells only): `MSSQL_PERFTEST_CENTRAL_CONNSTRING` (PerfCentral), `MSSQL_PERFTEST_CENTRAL_TEST_CONNSTRING`, `MSSQL_PERFTEST_CENTRAL_TEST_WRITER_CONNSTRING` (least-priv negative tests). SA password is the repo's synthetic default from the compose file.
- CLI: `perftest central init|check|health|cleanup`, `perftest push [runId|--all-new] [--dry-run]`.

## 2. Host SQL Server 2025 TCP (elevated, one time) — OPTIONAL

Your host instance allows only shared memory, which sqlcmd/STS can use but the Node TDS driver (perftest push) cannot. To make `localhost` (not the container) a central target, run **elevated**:

```powershell
Set-ItemProperty 'HKLM:\Software\Microsoft\Microsoft SQL Server\MSSQL17.MSSQLSERVER\MSSQLServer\SuperSocketNetLib\Tcp' -Name Enabled -Value 1
Restart-Service MSSQLSERVER -Force
```

Then re-run `perftest central init` against it. Logins `perftest_central` / `perftest_central_writer` already exist on the host (passwords only in your user env vars from provisioning; rotate freely — nothing on disk).

## 3. Debug Console upload target (dogfood, 2 minutes)

1. Save a connection profile pointing at the central store, **database pinned**: server `localhost,14333`, database `PerfCentral`, SQL auth `sa` + the compose password (or a least-priv login you add to role `central_writer`). Give it a profile name, e.g. `central-store`.
2. Settings:
   ```jsonc
   "mssql.centralObservability.enabled": true,
   "mssql.centralObservability.targetProfileId": "central-store"
   ```
3. Debug Console → Exports → **Upload to shared server**: Preview shows the exact projection (tables/digested/dropped/refused); Upload streams it. Duplicates land as `alreadyPresent`; canceled uploads resume.

## 4. Team hosting decision (Q-4 — blocks CI publish activation)

Decide: Azure SQL DB vs. team-hosted SQL Server; SQL auth vs. Entra managed identity. Then:
- create the DB, run `perftest central init --target <connstring>`;
- create a `central_ci`-role login for CI; add repository secret `MSSQL_PERFTEST_CENTRAL_CONNSTRING`;
- label a pinned self-hosted runner `perf-pinned` and enable `.github/workflows/perf-nightly.yml` (template committed; gate stays local-authoritative, push is continue-on-error).

## 5. Grafana (reader; support code will land with CENT-4)

1. Install Grafana OSS (https://grafana.com/grafana/download — Windows installer or `docker run -d -p 3000:3000 grafana/grafana-oss`).
2. Add a *Microsoft SQL Server* data source: host `localhost:14333`, database `PerfCentral`, a `central_grafana`-role login (create one: `CREATE LOGIN grafana_reader WITH PASSWORD='...'; CREATE USER grafana_reader; ALTER ROLE central_grafana ADD MEMBER grafana_reader;`).
3. Import the dashboard JSON from `perftest/grafana/` once CENT-4 lands (panels read only the canned `central.*` views).

## 6. What stays deferred (by design, journaled)

- CENT-5: markers/SQL-activity detail tiers, `extended` growing-session outcome. CENT-6: support bundles + purge UX beyond `usp_purge_entity`. C7: Bencher/OTLP projections.
- In-product upload of imported perf RUNS (sessions upload today; runs ride `perftest push` — same store, same dedup, shared projection guarantees parity).
