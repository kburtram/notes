# Central Observability build — PROGRESS journal

Companion to `EXECUTION_PLAN.md` (same folder). One entry per completed batch; deviations from the base design / addendum are recorded here with rationale.

---

## Entry 0 — grounding + plan (2026-07-06)

- Read Karl's review pack in full: `central_observability_design.md` (reviewed drop-in replacement, 1017 lines) + `CENTRAL_OBSERVABILITY_REVIEW_ADDENDUM.md` (403 lines, NORMATIVE — wins over base; C-1..C-15, H-1..H-6 woven in, T-B1..18, Q-1..7 with defaults).
- Verified all F1–F17 code-truth facts against both branches (vscode-mssql `091b6712b`, perftest `a01dc2c`): RANK_ORDER at redaction.ts:189 (private — needs export), exit code 7 free, canonicalJson at environment.ts:60, attempt_id + official_metric_samples join semantics in perf-store.schema.sql, envelope unions debugConsole.ts:15-42.
- Localhost SQL Server 2025 (17.0.1000.7) verified: mixed mode, sysadmin via integrated auth, sqlcmd 170 tools present. `PerfCentral`/`PerfCentralTest` DB names reserved. npm registry reachable (mssql 12.7.0).
- Mapped both repos (2 explorer agents) — anchors folded into EXECUTION_PLAN §0.
- Wrote EXECUTION_PLAN.md (CENT-0a..CENT-6, Q-defaults flagged, verification chains).

## Entry 1 — CENT-0a contract core COMPLETE (2026-07-06, perftest `ddc6cda`)

Built the shared contract in `perf-contracts`: `src/central/` (digest/policies/envelope/dto/encode/projection + barrel), `sql/central-store.{schema.mssql,procedures,views,roles}.sql`, `fixtures/central/{golden-run,golden-session,privacy-canaries}` with locked `expected.json` digest anchors, tests 46/46. DDL applied clean to live `PerfCentralTest` and the disposition algebra smoke-tested end-to-end (proceed→stage→commit; duplicate→alreadyPresent; mutation→refused:sourceMutation; policy change→reprojection lane; abort→abandoned; official_metric_samples shows exactly the committed row). `canonicalJson` moved to the contract; environment.ts re-exports.

**Deviations/decisions journaled:**
- Digest prefixes: house 22-char b64url with kind tags `src_/cnt_/prj_/pay_/pvw_/prn_/fld_` (addendum only pinned `prn_`).
- Kind tables carry `upload_batch_id` ONLY (no denormalized entity_id/uploader_id from base §5.6) — C-3's current_batch join makes them derivable and un-stale-able; per-batch PKs (global uniqueness lives on central_entities).
- H-1 `UNIQUE(session_id)` relaxed to `UNIQUE(upload_batch_id, session_id)` — H-1 as written conflicts with C-3 stage-beside-current reprojection.
- `cls_max`/`cls_rank` are RECOMPUTED over the post-upload-policy payload (row describes stored content; capture-side count preserved in cls_redacted_fields).
- Secret-class fields: refusal only for plain/truncated values; redacted/omitted/tokenized/digested markers drop quietly (addendum §5 handling semantics — otherwise every session with a password field would refuse).
- `upload_policy_id` on diag_sessions rows is filled by the proc from the batch (single source of truth; not in the row DTO).
- created_at_unix_ns for directory-loaded runs derives from the runId prefix (second precision documented).
- SQL Server gotchas: filtered indexes need QUOTED_IDENTIFIER ON (`sqlcmd -I`; tedious defaults ON); OPENJSON `[key]` needs `COLLATE DATABASE_DEFAULT`; `AS JSON` requires nvarchar(max) in WITH clauses.
- Tooling trap: Write/Edit tool params JSON-decode `backslash-u0000`-style escapes into RAW bytes — build control chars via `String.fromCharCode` in source and single-escape sequences in fixtures via node scripts, never sed (GNU sed `\u`/`\0` replacement magic corrupts).

## Entry 2 — CENT-0b store bring-up + admin CLI COMPLETE (2026-07-06, perftest `66e5f3c`)

`mssql`(tedious) + `@types/mssql` deps; `src/central/centralClient.ts` (target resolution — SQL auth REQUIRED, integrated refused with actionable message; parameterized proc wrappers; `uploadProjection` = THE writer path: begin→stage(skip resume-applied)→commit, abort-on-failure), `centralAdmin.ts` (init = GO-split contract DDL apply + schema_info seed; check = compat/contract/rank/union skew + procs/views/trend + health), `runLoader.ts` (run dir → PerfRunSource; parity rules in header), CLI `central init|check|health|cleanup`. Integration suite `test/centralStore.integration.test.ts` gated on `MSSQL_PERFTEST_CENTRAL_TEST_CONNSTRING`: **T-B1/2/3/7/13/14/16/17/18 all pass live**.

**Environment decisions (IMPORTANT for restart):**
- Host SQL Server 2025 has **TCP DISABLED** (shared-memory only) and I am not elevated → tedious cannot reach it. **The perftest docker container is the canonical local central store**: `perftest-sqlserver` (compose file `sql/docker-compose.sqlserver.yml`), `localhost,14333`, sa/`PerfH@rness2026!` (the repo's synthetic default). DBs `PerfCentral` (dogfood, INITIALIZED + check-green) and `PerfCentralTest` (integration tests) + login `perftest_central_writer` (central_writer role only, pwd `WriterOnly#2026!x`) live IN THE CONTAINER.
- User env vars (setx, new shells only — export inline in this session): `MSSQL_PERFTEST_CENTRAL_CONNSTRING` → PerfCentral@14333; `MSSQL_PERFTEST_CENTRAL_TEST_CONNSTRING` → PerfCentralTest; `MSSQL_PERFTEST_CENTRAL_TEST_WRITER_CONNSTRING` → writer login. (Host-instance logins `perftest_central`/writer also created earlier — unused until Karl enables TCP, see setup-instructions.)
- Proc fixes from live testing: OPENJSON WITH must NOT use `AS JSON` for string-valued JSON columns (yields NULL); failed stage items re-ledger AFTER rollback; retries DELETE-supersede non-applied slots; cleanup windows parameterized.

## Entry 3 — CENT-1 push COMPLETE (2026-07-06, perftest `c295464`)

`push [runId] | --all-new [--dry-run] [--policy] [--ci] [--target]` + exit code 7 `pushFailed`. Proven live: real gates run b0990fa9 pushed (541 rows), duplicate → alreadyPresent, **full backfill of local history: 131 runs / 5685 metric rows / 0 failed** (8 `*_selftest` dirs skip cleanly — no environment.json by design; scans skip, targeted pushes fail loudly). Unit tests: preview output discipline (no labels/notes/paths), CI identity sniff, no-connstring-echo.

## Entry 4 — CENT-0c vocabulary + vendoring COMPLETE (2026-07-06, perftest `c00da76`+`9a75b90`, vscode-mssql `3fe09c9f6` core:)

- Registry: `centralObservability.` spanFamily + `mssql.central.{preview,upload,provider.list}` begin/end pairs; regenerated + vendored `observabilityContract.generated.ts`; obs-contracts 27/27.
- Central contract vendored **byte-identically** (modulo CRLF — the product pre-commit hook rewrites EOLs; vendor-sync normalizes) to `src/sharedInterfaces/centralContract/` (prettier-ignored via repo `.prettierignore`, eslint-ignored via `eslint.config.mjs` global ignores). Golden fixtures embedded as `test/unit/support/centralGoldenFixtures.ts`. `redaction.ts` now EXPORTS `RANK_ORDER`.
- `centralContractConformance.test.ts` 6/6 under vscode-test: **T-B5 cross-repo digest parity proven**, RANK_ORDER equality, union versions, canaries, policy invariants.
- CI template `.github/workflows/perf-nightly.yml` (CENT-1p authored-only; activation blocked on Q-4 hosting + runner + secret).

## Entry 5 — CENT-2pre + CENT-2 core COMPLETE (2026-07-06, vscode-mssql `501a55d5d` qs: + `62aa8f763` core:)

- commandKind union += "centralUpload" (only ONE code site — the union itself; adapters treat it opaquely).
- `src/diagnostics/centralUpload.ts`: CentralUploadService (begin/stage/commit as EXEC + sqlNString literals; RowCollectingSink over IQueryEventSink; per-execute {background, centralUpload, tag, expectedDatabase}; cancel-at-item-boundary leaves batch RESUMABLE — no abort on cancel; abort-as-failed otherwise; centralObservability.* diag emission) + `loadDiagSessionSource` (SessionStore dir → DiagSessionSource with sha256 inventory). `centralUpload.test.ts` 6/6 on FakeBackend (incl. wire-text literal assertions).

**Entry 5b — CENT-2 full surface built (2026-07-06, uncommitted at writing; commit follows full-suite green):** settings `mssql.centralObservability.{enabled,targetProfileId,defaultUploadPolicy,maxItemBytes}` (quickUpload/maxEventsPerUpload deliberately DEFERRED until consumed — no unwired settings); RPC `dc/centralPreview` + `dc/centralUpload` + `dc/centralUploadProgress` with self-contained serializable types (CentralTargetInfo/CentralPreviewInfo/CentralReceiptInfo — debugConsole.ts stays import-free of the contract); controller handlers + `resolveCentralUpload` (store: sources only in v1; active sessions refused with C-6 message; perf runs → "use perftest push" message); host seam `configureCentralUploadHost` wired in mainController (profile via mssql.connections match on id/profileName + prepareConnection; database REQUIRED on the profile); ExportsPage gains `CentralUploadCard` (preview tables/digested/dropped/refused/warnings, upload disabled until previewed and refusal-free, progress + receipt lines); PERF_MODE probe `mssql.perf.centralUploadRoundTrip` (2000-event fixture via `makeCentralProbeSession`, preview+upload marker pairs, readback honesty via `queryCentralRows` through the visibility join, unique sessionId per rep); `queryCentralRows` exported as the CENT-3 provider primitive. tsconfig.webviews EXCLUDES sharedInterfaces/centralContract (node:crypto — extension-host only).

## Entry 6 — CENT-2 COMPLETE + CENT-4 CLI half (2026-07-06/07, vscode-mssql `7268807a4` core:, perftest `4692f2e`)

Full vscode-test suite **4166 passing / 0 failing / 12 pending** (baseline 4151 + 15 central tests: 6 conformance + 6 upload + RANK_ORDER/etc.); repo build green. `perftest central report` renders live from PerfCentral (131 runs → 7 trend charts, regression board, ledger with alreadyPresent pills from the idempotent re-push, health KPIs). `setup-instructions.md` written (host TCP enable, dogfood profile walkthrough, Q-4 hosting worksheet, Grafana steps, deferred list). Deviations: quickUpload/maxEventsPerUpload settings deferred until consumed; product uploads SESSIONS only in v1 (runs ride `perftest push`; parity guaranteed by the shared projection); the C2 probe awaits a saved dogfood profile to run live (setup-instructions §3).

**Entry 6 addendum — final gates 32/32 (run `2026-07-07T01-28-36Z_5ff773ac`, status passed), then pushed centrally via `perftest push` → committed batch 396, 541 rows.** The verification run publishing itself through the pipeline it verified is the end-to-end proof for this window.

**Follow-up (small):** `central.regressions_last_30d` returned 0 rows against the backfilled history despite official samples existing — inspect the CTE window/percentile logic with real data next session (the report renders its empty-state gracefully; not load-bearing). Grafana dashboard committed as `perftest/grafana/central-observability-dashboard.json` (perftest `fa3b22d`); panel SQL smoke-verified live.

**REMAINING overall: CENT-3** (central Perf History provider: PerfSourceKind "central" + status unions + resultFlags + paged queries over queryCentralRows + T-B12 trend parity + receipt drill-in), **CENT-4 rest** (Debug Console central viz panels — upload history/health/fleet trend via provider RPC; `grafana/` dashboard JSON + provisioning), **CENT-5/6 deferred**. Final gates run for this window: see Entry 6 addendum below (32/32 expected; environmental invalids rerun to confirm).

**(historical) REMAINING for CENT-2 (next window):** (a) settings `mssql.centralObservability.{enabled,targetProfileId,defaultUploadPolicy,quickUpload,maxEventsPerUpload,maxItemBytes}` in package.json; (b) RPC: `dc/centralPreview` + `dc/centralUpload` (+ progress notification) in sharedInterfaces/debugConsole.ts mirroring DcExportRequest (:626); (c) controller handlers in debugConsoleWebviewController.ts near the export handler (:618) — resolve profile via connectionStore/profileAuthAdapter prepareConnection + build CentralUploadTargetConfig, sources: closed/partial sessions (close-then-upload for live per C-6) + imported perf runs (share vendored projection); (d) ExportsPage UI (upload button → preview panel → confirm → progress → receipt); (e) PERF_MODE probe `mssql.perf.centralUploadRoundTrip` in mainController (fixture session → preview → upload to PerfCentral@localhost,14333 container → readback → assert; marker pair mssql.central.upload.begin/end; scenario ends on waitForMarker!); (f) FULL verification chain incl. vscode-test full suite (baseline 4151+12 new) + repo build + gates 32/32.

**THEN CENT-3** (provider) + **CENT-4** (central report HTML + Debug Console viz + grafana/ + setup-instructions.md). Original roadmap below.

**NEXT (in order): CENT-2pre** (qs: commandKind union += "centralUpload" + adapter/fake passthrough), **CENT-2** (Debug Console upload: settings mssql.centralObservability.*, preview RPC/UI parallel to DcExportRequest seam at debugConsoleWebviewController.ts:618, data-plane writer per C-11 using vendored sqlNString + segment→item streaming, receipt UI, closed/partial-only precondition, canaries, fake-backend unit tests, PERF_MODE probe mssql.perf.centralUploadRoundTrip), **CENT-3** (central provider: PerfSourceKind "central", status unions += unavailable/permissionDenied, resultFlags, paged canned-view queries, T-B12 trend parity), **CENT-4** (perftest `central report` static HTML reusing report/htmlShell+charts; Debug Console central viz panels; grafana/ dashboards; setup-instructions.md covering: host TCP enable (elevated regedit Tcp Enabled=1 + service restart), Grafana install/provisioning, hosting/CI secrets Q-4, container store facts). Remaining vscode-mssql verification chain for CENT-2/3: tsgo both configs → prettier/eslint → tsc --noCheck → vscode-test FULL suite (baseline 4151+6 conformance) → repo build → perftest gates 32/32.
