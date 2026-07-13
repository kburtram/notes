# How to use perftest (and all the logging/diag around it)

Task-oriented guide for the whole observability stack: the perftest CLI, the central store, the Debug Console, session diagnostics, and replay. Deep reference lives in `perftest/docs/` (CLI.md, SCENARIO_AUTHORING.md, REGRESSION_MODEL.md, REPORTS.md, SOAK_AND_STRESS.md…) — this doc is "what do I type to do X". Product-side settings: see `settings.md` next to this file.

Repo: `C:\repos\test\perftest` (branch `dev/query`). Build once per change: `npm run build`. CLI entry: `node packages/perftest-cli/dist/cli.js …` (below abbreviated as `perftest …`).

---

## 1. Everyday runs

```bash
perftest doctor                        # environment preflight (add --config to validate a config too)
perftest scenarios list                # what exists + implementation status
perftest run --config examples/config.eval.local.jsonc              # THE gates: 8 scenarios × 4 reps
perftest run --config examples/config.eval.local.jsonc --scenario query-10k-results   # one scenario
perftest run --config ... --pass diagnostic --tag before-fix        # diagnostic pass, tagged
```

- Each run writes `perf-runs/<runId>/`: `index.html` (open this), `report.md/html`, `summary.json`, `environment.json`, `harness-log.jsonl`, per-rep `scenarios/<id>/reps/rep-NN/{result.json, markers.jsonl, artifacts/}`, and inserts into the local SQLite store `perf.db`.
- **Exit codes are the contract**: 0 ok · 1 gated regression · 2 config invalid · 3 preflight failed · 4 scenario failed · 5 infrastructure · 6 insufficient samples · 7 central push failed (never gate-relevant).
- Contended machines sometimes produce an "invalid" rep (e.g. a 120 s render timeout) — rerun to confirm before believing a regression.
- SQL target comes from `STS2_SQLSERVER_CONNSTRING` (config `sql.provider: external`) or the pinned container (`sql/docker-compose.sqlserver.yml`, port 14333).

## 2. Reading results

```bash
perftest report <runId>                # re-render index.html/report.md from the run dir
perftest history                       # cross-run listing from perf.db
perftest trend --scenario query-10k-results --metric scenario.wallclock
```

`index.html` per run has the waterfall, per-rep metrics, validations, and artifacts. Only **official** metrics (marker-based, measurement pass, passed rep) feed gating; everything else is diagnostic.

## 3. Comparing and gating

```bash
perftest compare --current <runId> --baseline <runId|name|rolling:5>   # gate-style comparison
perftest diff --baseline <runA> --candidate <runB>    # investigation: what changed (non-gating)
perftest head-to-head --baseline-scenario query-10k-results --candidate-scenario querystudio-query-10k
perftest baseline list
perftest baseline set nightly <runId> [--scenario id] # named baseline (env-hash bound)
perftest tag <runId> before-fix
perftest cleanup --older-than 14d [--dry-run]         # prune old run dirs (regression evidence kept)
```

Baselines never compare across different `environmentHash`es. The regression model (thresholds, Welch t, verdicts) is `docs/REGRESSION_MODEL.md`.

## 4. Central store — shared SQL Server (runs + sessions)

One store, two writers, one contract. Local files stay ground truth; the store is a rebuildable projection with an append-only upload ledger.

**Where it lives today:** the perftest SQL container — `localhost,14333`, DBs `PerfCentral` (real) and `PerfCentralTest` (integration tests). Start it: `docker compose -f sql/docker-compose.sqlserver.yml up -d --wait`. Connection strings are in your user env vars `MSSQL_PERFTEST_CENTRAL_*` (set via setx; every `central`/`push` command also accepts `--target`). Host-instance option + team hosting: `observability-docs/central/setup-instructions.md`.

```bash
perftest central init        # create/upgrade schema, procs, views, roles (idempotent)
perftest central check       # contract/vocabulary skew, procs, views, health — must be OK
perftest central health      # one-row operational facts
perftest central cleanup     # retention TTLs, orphan sweep, abandoned promotion
perftest central report --out central-report.html    # local HTML: trends, regressions, ledger, sessions

perftest push <runId>        # publish one run (Tier 1: runs/reps/metrics/validations/artifact refs)
perftest push <runId> --dry-run   # print the EXACT upload preview (tables, digested/dropped/refused) offline
perftest push --all-new      # backfill every run dir; unchanged runs land as alreadyPresent
perftest push ... --ci       # record under the CI principal (baselines are CI/admin-gated)
```

Semantics worth trusting: re-push of an unchanged run = `alreadyPresent` (ledgered, no rows); changed source under the same runId = **refused** `sourceMutation`; a new policy/projector over the same source = `reprojected` (pointer flip, old rows swept later); canceled uploads resume. Upload policies (`ci-official.v1` default for push, `team-default.v1` for the product) digest machine labels and drop notes/SQL/rows — `--dry-run` shows exactly what leaves.

**Sessions from the product:** Debug Console → Exports → *Upload to shared server* (preview-first; needs `mssql.centralObservability.*` settings — `settings.md` snippet). Sessions and runs land in the same store, so "did dogfooders hit what CI missed" is one query (`central.fleet_by_build`).

**Dashboards:** `perftest/grafana/central-observability-dashboard.json` (import into Grafana with an MSSQL datasource; setup-instructions §5). Ad-hoc SQL: query the `central.*` views only — never base tables.

## 5. In-product diagnostics (Debug Console)

`MS SQL: Open Debug Console`. Pages: Overview · Consolidated Trace · Waterfall · Perf Test History · Session History · SQL Activity · Connections · Query & Results · Object Explorer · Completions · Exports · Settings.

- **Self-test**: run perftest scenarios in-process against your live window (status-bar on-air light, cancel, results attach as a console source). Uses `perftest-inproc` — build perftest first.
- **Perf Test History**: browses run directories (add sources; `mssql.debugConsole.perfRunsRoot`), trends, rep compare, waterfalls, rich diagnostics. A `central` source kind (reads the shared store through the data plane) is the next planned increment.
- **Session diagnostics**: `Session Diagnostics: Enable Capture` (or `mssql.sessionDiag.enabled`) journals redacted events across sessions. `Elevate Capture` = time-bounded full capture (needed for replayable SQL text). Export = redacted JSONL; Upload = central store.
- **Completions page**: enable/disable AI completions, watch live redacted activity, open the full Inline Completion Debug viewer.
- **Rich collection** (`mssql.debugConsole.richCollection`): CPU/mem/event-loop counters per span while capture is on.

## 6. Replay

Three replay surfaces, all built on the feature-capture framework (bounded ring of rich feature events, pending→final lifecycle, policy-gated):

1. **Query Studio Replay Lab** (`MS SQL: Query Studio: Open Replay Lab`, needs `mssql.queryStudio.replay.enabled`): captures QS runs (digests by default; elevated capture for full SQL), replays them with original or overridden config, matrix runs, replay Trace Identity tagging so replayed spans never pollute real traces.
2. **Inline Completion Debug viewer** (`MSSQL: Open Inline Completion Debug`): replay cart + matrix runner re-issues captured completion requests across profile × schema-budget combinations; Sessions tab loads persisted trace files (`mssql.copilot.inlineCompletions.trace.captureEnabled`, traces flush on window close).
3. **Debug Console Replay Lab page**: gated until the completions replay adapter migrates into the console host — use the two surfaces above.

## 7. PERF_MODE probes (harness-only honesty checks)

Registered only when the harness launches the extension in PERF_MODE; each throws on any honesty failure so a scenario records a real error: `mssql.perf.metadataCacheWarmAcquire` (cold hydrate + save, warm MUST serve from disk), `mssql.perf.centralUploadRoundTrip` (fixture session → preview → upload → readback through the visibility join), plus QS open/query and OE v2 browse probes. Scenarios end on `waitForMarker` of the probe's end marker — never on afterLastAction (sink flush timing).

## 8. When something is weird

- `central check` first — it catches contract/vocabulary skew between writers and store.
- `perftest push --dry-run` shows exactly what a run projects to, offline.
- Ledger truth: `central.upload_history` / `central.ingestion_failures` views, or the ledger section of `central report`.
- Gates flaky? Check pass-COUNTS per suite, not just failure names; rerun environmental "invalid" reps.
- Node TDS (push) needs TCP — the host instance is shared-memory-only until the elevated enable (setup-instructions §2); the container always works.
- Applying central DDL by hand: `sqlcmd -I` (QUOTED_IDENTIFIER) or filtered indexes fail.
