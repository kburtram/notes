# Central Observability — Execution Plan (build phase)

**Status:** ACTIVE build plan, started 2026-07-06.
**Normative inputs (priority order):** (1) the branch (code truth), (2) `CENTRAL_OBSERVABILITY_REVIEW_ADDENDUM.md` (wins over base), (3) `central_observability_design.md` (Karl's reviewed drop-in replacement), (4) base-pack visuals. Karl's build directive: build perftool + Debug Console + support code end-to-end; local SQL Server on localhost is the test target; local visualizations in debug tools and local reports are in scope; Grafana/третьи-party systems get support code + `setup-instructions.md` for anything requiring installation; adjust the spec where implementation reveals better options (journal every deviation).
**Restart protocol:** read this file + `PROGRESS.md`, then the addendum §2/§3 (C-1..C-15) and §10 (T-B1..18). Code anchors verified 2026-07-06: vscode-mssql `dev/query` @ `091b6712b`, perftest `dev/query` @ `a01dc2c`, both trees clean.

---

## 0. Environment facts (verified, don't re-derive)

- Localhost SQL Server 2025 Enterprise Developer (17.0.1000.7), **mixed mode**, current user is sysadmin via integrated auth (`sqlcmd -S localhost -E -C`). Existing DBs incl. `PerfCatalog`, `PerfHarness`, `Sts2TestDb` — do not touch.
- Central DBs: **`PerfCentral`** (local stand-in for the shared store, dogfood target), **`PerfCentralTest`** (integration tests; created by `central init`, reset per test run).
- CLI SQL client: `mssql` npm pkg (tedious) — registry reachable (12.7.0). Tedious cannot do Windows SSPI ⇒ dedicated SQL login **`perftest_central`** for CLI push (created by setup, documented). Product upload path uses saved connection profiles ⇒ integrated auth works there.
- Connstring env: `MSSQL_PERFTEST_CENTRAL_CONNSTRING` (never persisted/echoed). Integration tests additionally require `MSSQL_PERFTEST_CENTRAL_TEST=1` else skip cleanly.
- perftest already shells host `sqlcmd` in `sqlProvisioner.ts`; `canonicalJson` lives at `packages/perftest-cli/src/run/environment.ts:60` (moves to contract per addendum §6).
- Exit codes 0–6 taken; **7 free** (`exitCodes.ts` verified). `RANK_ORDER` verified verbatim at `diagnostics/redaction.ts:189` (19 entries). Envelope unions verified (`debugConsole.ts:15-42`): DiagProcess(7), DiagKind(9), DiagStatus(6), DiagTimingClass(5).
- Run-dir ground truth: per-rep `scenarios/<id>/reps/rep-NN/result.json` (schemaVersion 2: runId/repId/scenarioId/attemptId/passType/status/trace/git[]/environment/metrics[]/artifacts[]/validations[]/errors[]), run-level `summary.json` {runId, passType, status, environmentHash, scenarios}, `environment.json`, `harness-log.jsonl`.

**Code anchors from repo mapping (2026-07-06):**
- perftest-cli: ALL commands registered inline in `src/cli.ts` (no commands/ folder; `notImplemented()` stub pattern at :32; exit via local `exit(code)` :28). Run-dir reader precedents: `report` action `cli.ts:327-343` + `report/runIndex.ts loadReps()` :71-97. Store = concrete `PerfStore` over better-sqlite3 (`store/sqliteStore.ts`), loads schema via `perf-contracts validation.ts sqliteSchemaPath()` :92 — mirror this pattern (`centralSchemaPath()` etc.). Report primitives to reuse for `central report`: `report/htmlShell.ts` (pageShell/section/dataTable/kpiRow/pill), `report/charts.ts` (trendChart/waterfall/histogram/horizontalBars/TOKENS). Harness telemetry: `telemetry/logger.ts` `HarnessLogger.span()` — JSONL sink only attached inside `run` (cli.ts:234); `push` attaches its own or stays console-only. `sql/sqlProvisioner.ts` = sqlcmd/redaction precedent (SQLCMDPASSWORD env, never argv; `redact()` :367).
- observability-contracts: generate = `npm run build && npm run generate` → `generated/typescript/observabilityContract.generated.ts`; vendor = MANUAL copy to `src/sharedInterfaces/` enforced by `test/vendorSync.test.ts` byte-compare.
- vscode-mssql: webview pages at `src/webviews/pages/DebugConsole/` (shell.tsx NAV :24-53, pagesMore.tsx has ExportsPage). Upload seam parallels `DcExportRequest` (debugConsole.ts :626, handler `controllers/debugConsoleWebviewController.ts` :618-657, `eventsFor(sourceId)` + `diag.flushAll()`). Data plane: `ISqlConnectionService`/`ISqlSession` (api.ts :119/:158), real impl `sqlDataPlaneService.ts`, fake `src/services/sqlDataPlane/fakeBackend.ts` (`new FakeBackend({scripts})` per `sqlDataPlaneConformance.test.ts` :27). Profile+secrets seam: `services/metadata/profileAuthAdapter.ts prepareConnection(stored, secrets)` :101. PerfHistory: no provider interface — `perfHistoryService.ts` dispatches concrete providers, sqlite handled inline in `sourceStatus()` :131-146 (`unsupported` pattern to copy for central-unavailable). `RANK_ORDER` is module-PRIVATE in redaction.ts — export it (additive) for the vendor-equality test.
- Projection API shape: perf-contracts central projectors are **pure functions over parsed inputs** (no fs in the contract): `projectPerfRun(input)` / `projectDiagSession(input)` where each side's thin loader assembles `{parsed JSON files + relative paths + per-file sha256}`. Keeps the vendored bundle dependency-free and fixture-testable.

## 1. Standing decisions for this build (addendum defaults, FLAGGED for Karl)

| # | Decision | Taken as |
|---|---|---|
| Q-1 | commandKind for product upload | **Add `"centralUpload"` to `ExecuteOptions.commandKind` union** (qs: train, tiny PR before C2) |
| Q-2 | live-session upload | v1 = closed/partial only; `extended` outcome deferred to CENT-5 |
| Q-3 | artifact relative paths under team-default | plaintext **relative** paths (absolute ⇒ refusedByPolicy) |
| Q-4 | hosting + auth | localhost `PerfCentral` for dev/dogfood now; real hosting + CI secrets = `setup-instructions.md` §hosting; C1′ workflow authored but not activated |
| Q-5 | monotonic_ns column type | decimal string `nvarchar(40)`, `TRY_CONVERT` in views |
| Q-6 | `event_time_utc` etc. | projector-computed `*_utc datetime2(3)` columns approved as index/retention axis |
| Q-7 | comparisons/comparison_metrics | local-only; central recomputes via views |
| D-12 | commit train | vscode-mssql: **`core:`** for diagnostics/central + vendored contract (matches existing Debug Console precedent), **`qs:`** for the sqlDataPlane union add. perftest: descriptive messages per repo style |

Also standing: all product-side central code behind **`mssql.centralObservability.enabled` (default false)**; secrets/SQL text/rows/prompts/tokens NEVER in diagnostics or uploads by default and never plaintext regardless of settings; new vocabulary lands contracts-first (registry → generate → vendor → emit); no `MERGE`; writers only ever EXECUTE the Appendix-C proc list.

## 2. Batches

### CENT-0a — Contract core in perf-contracts (C0.1–C0.4) — perftest repo
DDL: `sql/central-store.schema.mssql.sql` (+ `central-store.procedures.sql`, `central-store.views.sql`, `central-store.roles.sql`) per base §5 with addendum C-1..C-10 + H-1 (`session_sk`) + H-2 (`schema_info` gains `rank_table_version`, `union_versions_json`, `min_compat_level`), ISJSON checks, generated CHECK constraints from vendored unions.
TS: `src/central/digest.ts` (canonicalJson moved + sha256 digests: source/content/projection/payload/preview + `prn_` principal recipe C-14), `policies.ts` (RANK_ORDER `cls-rank/1` + generated policy matrix: team-default.v1 / team-names.v1 / elevated-support.v1 / ci-official.v1 + Appendix-A perf-twin column map), `dto.ts`, `projection.ts` (perfRun projector over run dir; diagSession projector over manifest+segments incl. gaps C-5, provenance filtering C-7, subtraction map C-8; `UploadPreview` = dry-run of same stream, C-15 `preview_digest`), `encode.ts` (`sqlNString` literal encoder with U+0000/surrogate/budget rules), `conformance.ts`.
Fixtures: `fixtures/central/golden-run/**` (trimmed real-shape run: 2 scenarios × 2 reps, attempt_id variance, wildcard baseline), `golden-session/**` (synthesized: 3 segments, GapRecords + droppedRanges, entity anchors, tags, machineLabel, all handling kinds), `privacy-canaries/**` (base §7.4 + addendum §5: machineLabel, machine_id, created_by, absolute paths, non-digest entity.id, escaper bombs `'`, `''`, `N'`, `];--`, U+0000, unpaired surrogates, 9KB field).
Vitest: projection determinism (project twice ⇒ byte-identical canonical row streams), digest goldens, policy matrix + rank parity (T-B4 perftest half), canary scans over projected rows + preview JSON (T-B8 subset), encoder unit tests.
**Acceptance:** perf-contracts vitest green; DDL parses (syntax-checked in CENT-0b against live server).

### CENT-0b — Store bring-up + admin CLI + integration tests (C0.7, part C1) — perftest repo
`mssql` dep in perftest-cli; `src/central/` client module (connstring resolution, proc-call wrappers, receipt types); commands `perftest central init|migrate|check|cleanup` (init creates DB objects idempotently; check validates schema_info versions, procs, views, fixture round-trip state, rank/union skew H-2; cleanup = retention + orphan sweep + started→abandoned promotion C-3).
Integration vitest suite (gated on `MSSQL_PERFTEST_CENTRAL_TEST=1`): full disposition algebra T-B1 (all C-1 rows), begin-lock race T-B2 (two concurrent writers), resume T-B3, orphan sweep T-B14, corrupt/oversized payload T-B16, baseline role gate + wildcard mapping T-B17, count-mismatch commit refusal T-B18, migration fixture T-B15 (v0→v1 skeleton), purge T-B13, health proc.
One-time local provisioning (scripted in `tools/` + documented): create `perftest_central` SQL login, `PerfCentral` DB, role grants; set user env var.
**Acceptance:** `central init && central check` green on a fresh `PerfCentralTest`; integration suite green locally.

### CENT-0c — Vocabulary + vendoring (C0.5/C0.6) — both repos
Registry: `centralObservability.` family (preview/upload/upload.item spans, upload.refused, provider.query, provider.failed per C-13 attrs) + `mssql.central.` marker pairs (preview/upload/provider.list, measurementEligible) ⇒ regenerate ⇒ vendor `observabilityContract.generated.ts`. CLI push/migrate spans are harness-log conventions (no registry).
Vendor central contract into vscode-mssql as generated files (dto/policies/digest/projection/encode — same "GENERATED — do not edit" header + vendor script parity test like vendorSync).
Product-side conformance: golden fixtures projected by vendored code ⇒ byte-identical to perf-contracts output (T-B5 product half); RANK_ORDER vendor equality vs `redaction.ts`.
**Acceptance:** contracts vitest green (rerun after cp — vendorSync races); vscode-mssql unit tests green.

### CENT-1 — `perftest push` (C1) — perftest repo
`exitCodes.ts` += `pushFailed: 7`; `perftest push [runId|--all-new] [--dry-run] [--target]` reading run directories (not perf.db); preview printing = product preview parity; Tier-1 payload; duplicate ⇒ alreadyPresent; digest-drift fixture ⇒ refused; central outage ⇒ exit 7 with gate codes untouched; harness spans (`centralPush.begin/end/item/commit`); T-B6 both-call-style parity (tedious parameterized vs sqlNString literal ⇒ identical stored rows); canary scan on CLI stdout.
**Acceptance:** push of a real local run lands in `PerfCentral`; re-push `alreadyPresent`; gates 32/32 unaffected.

### CENT-1p — CI publish (C1′) — perftest repo, authored-only
Workflow YAML (pinned agent): gates → artifacts → `perftest push --target env` continue-on-error → job summary line incl. receipt (success too, per addendum §6). Not activatable here (hosting/secrets = Q-4) ⇒ `setup-instructions.md` §CI.

### CENT-2pre — data-plane union (Q-1) — vscode-mssql, `qs:`
`ExecuteOptions.commandKind` += `"centralUpload"`; thread through adapter + fake backend. Tiny standalone commit.

### CENT-2 — Debug Console upload (C2) — vscode-mssql, `core:`
Settings (`mssql.centralObservability.{enabled,targetProfileId,defaultUploadPolicy,quickUpload,maxEventsPerUpload,maxItemBytes}`); upload service over SQL Data Plane per C-11 (openSession w/ applicationName `vscode-mssql-central-upload`, per-execute background/centralUpload/tag/timeout/expectedDatabase; segment→item streaming ≤1.5MB text per execute; cancel at item boundaries; resume via begin disposition); preview RPC + UI (exact dry-run, dropped/digested/refused, digest-pinned); receipt UI + ledger echo; upload entry points: closed/partial session (close-then-upload for live), imported perf run (shares generated projection with push); diag events under `centralObservability.` family; canaries over receipt/UI text (T-B8 render surfaces); unit tests on fake data plane (preview counts, streaming bounds, cancellation, refusal, escaper bombs end-to-end T-B10/T-B16-product).
PERF_MODE probe `mssql.perf.centralUploadRoundTrip` (fixture session → preview → upload to localhost → readback → assert counts/digests/policy drops) + perftest scenario when stable (base §12.4, addendum §9).
**Acceptance:** real upload from Debug Console to `PerfCentral` with receipt; vscode-test suite green; QS 10k gates unmoved.

### CENT-3 — Central Perf History provider (C3) — vscode-mssql, `core:`
`PerfSourceKind` += `"central"`; `PerfSourceStatus` += `"unavailable" | "permissionDenied"`; query responses += `resultFlags` (officialOnly/policyDropped/partialWindow/rowCapped); provider over canned views/iTVFs with pageRows/pageBytes + OFFSET/FETCH; states rendered distinctly (copy the sqlite-unsupported registration pattern); trend parity T-B12 (provider ≡ direct `central.trend` ≡ CLI trend math); receipt drill-in.
**Acceptance:** central runs/sessions/trends visible in Debug Console against `PerfCentral`; unit tests green.

### CENT-4 — Readers: local reports, Debug Console viz, Grafana (C4 + Karl's local-viz directive)
- `perftest central report [--out]`: static HTML (house report style) from central store — fleet trend by scenario/metric/env, regressions_last_30d, upload health, sessions_by_build, policy drops.
- Debug Console central visualizations: upload history + receipts view, central health panel, fleet trend panel (all via provider RPC; no new transport).
- Grafana: dashboard JSON in repo (`grafana/` + provisioning yaml) over the canned views; **not installed here** ⇒ `setup-instructions.md` (install, SQL datasource, provisioning, least-priv `central_grafana` login).
- `setup-instructions.md` also covers: hosting decision worksheet (Q-4), CI secret wiring, dogfood login provisioning, Bencher/OTLP C7 stubs-not-built.
**Acceptance:** report renders from `PerfCentral` with real pushed+uploaded data; dashboards load once Grafana installed (verified against JSON lint + view queries via sqlcmd).

### CENT-5 (C5) — detail tiers — deferred unless time allows
`--with-markers` / `--with-sql-activity` tiers, `extended` outcome + `usp_extend_upload`, retention proven on 30-day fixture (T-B10 extend pair, addendum §9 scenarios). Journal if deferred.

### CENT-6 (C6) — support bundles + purge UX — deferred
`usp_purge_entity` + T-B13 already land in CENT-0a/0b; the explicit support-policy workflow + artifact-ref UX deferred.

## 3. Verification chains (unchanged)
perftest: `npm run build` + vitest per package + gates `node packages/perftest-cli/dist/cli.js run --config examples/config.eval.local.jsonc` (8 scenarios/32 reps; contended runs may show environmental "invalid" reps — rerun to confirm; watch pass-counts).
vscode-mssql: `npx tsgo --noEmit -p tsconfig.extension.json` + webviews config → prettier + `npx eslint --quiet` → `npx tsc -p tsconfig.extension.json --noCheck` → `npx vscode-test` (CopilotChatEntry flake known; watch suite pass-COUNTS) → repo-root `npm run build` → perftest gates.

## 4. Batch status

| Batch | Status |
|---|---|
| CENT-0a | COMPLETE (perftest `ddc6cda`; PROGRESS Entry 1) |
| CENT-0b | COMPLETE (perftest `66e5f3c`; Entry 2 — container store is canonical local target) |
| CENT-0c | COMPLETE (perftest `c00da76`+`9a75b90`, vscode-mssql `3fe09c9f6`; Entry 4) |
| CENT-1 | COMPLETE (perftest `c295464`; Entry 3 — 131 runs backfilled live) |
| CENT-1p | AUTHORED (workflow template in `c00da76`; activation blocked on Q-4) |
| CENT-2pre | COMPLETE (vscode-mssql `501a55d5d` qs:) |
| CENT-2 | COMPLETE (vscode-mssql `62aa8f763` service + `7268807a4` settings/RPC/UI/probe; suite 4166 passing; PROGRESS Entry 5/5b/6) |
| CENT-3 | NOT STARTED (next: PerfSourceKind "central" provider over queryCentralRows; status unions += unavailable/permissionDenied; resultFlags; T-B12 trend parity) |
| CENT-4 | CLI HALF COMPLETE (perftest `4692f2e` central report, live-verified vs 131 runs; setup-instructions.md written). Remaining: Debug Console central viz panels + grafana/ dashboard JSON |
| CENT-5 | DEFERRED (build if time allows) |
| CENT-6 | DEFERRED |
