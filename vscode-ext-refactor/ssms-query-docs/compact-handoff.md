# Compact Handoff — Query Studio build (written 2026-07-05, pre-compaction)

**Purpose:** full state transfer for the post-compaction session. Read this,
then resume Batch 6 (completions port) exactly where PROGRESS.md Entry 7 says.

**UPDATE 2026-07-05 (4th compaction point): B7 NEARLY COMPLETE.** B7 became
the "common observability + replay generalization" batch per Karl's directive
(rich completions-style capture/replay/settings-override lifted into a CORE
framework, features instantiate it). Landed (vscode-mssql dev/query):
core: a742401(perftest registry)+1a450183a re-vendor, 25a54eba2+cc44c9391
feature-capture framework (store/codec/traceFiles/replayEngine/settings-
snapshot, 18 tests), 3238f5d4c override-optional; qs: 62d41a7ee completions
onto framework + completions.request diag bridge + settings snapshots,
1d91ae5e2 instrumentation completion (cancel/windowFetch/sync.applyEdit/
inlineCompletion.bridge/sqlDataPlane.execute/metadata.contextBuild+drift/
mssql.perf.queryStudioState), 8f8f0d5fd QsRunRecord recorder + Replay Lab
panel, canary commit (featureCapturePrivacyCanary 4 tests), 0f4032d90
PERF_MODE seams (single-profile auto-pick + queryStudioConnect/Execute).
Full suite 3390 passing/12 pending/1 known copilotChatEntry flake.
REMAINING at write time: perftest agent (querystudio-query-10k + head-to-
head report), npm run build + gates, PROGRESS Entry 9. Read PROGRESS
Entry 9 when it exists — it supersedes this note.

**UPDATE 2026-07-04 (3rd compaction point): B1-B6 COMPLETE.** B6 landed in 6
commits (core: 4b978a8c5 logger2; qs: 9d1afc1bd foundation, eda5a9039 MD-4
bridge+provider, 6114ebe9d sdkLanguageModels, 26dc2af9e debug panel+replay,
0e1364da7 QS Monaco ghost text). Read PROGRESS.md Entry 8 for the full
inventory, lessons (structured-context-not-text; JS default-param sentinel;
rest-omission lint; FakeBackend first-match ordering) and recorded
deviations. Remaining: B7 (M6) — observability polish, replay
generalization to QS runs, dogfood gates, preview readiness (doc 04 §18).
Residuals from earlier batches unchanged (B5 disk cache, plan TAB rendering,
live-SQL scenario provisioning, B1 untitled/Save-As + resync gate).

**UPDATE 2026-07-05 (2nd compaction point): B1-B5 COMPLETE + B6 started.**
New commits since the list below: c0034d4d9 (B3 close: execution host,
results UI, LOCAL Monaco via monacoSetup.ts loader.config({monaco}) +
editorWorker entry, updateConnectionWebview fix for custom-editor RPC,
qsBootError relay, late registration, mssql.perf.setConfig), perftest
a012a11 (querystudio-open scenario — GREEN ~1.5s, queryStudio.open metric
pair-derived), 9a92d9d74 (B4: SET wrapper modes + finally restore, showplan
detection, listDatabases/setDatabase + USE, db dropdown, plan buttons, grid
cell copy), edbd8ccde (B5: catalogModel SoA + buildSchemaContext
deterministic projection + metadataService hydration/drift/dedicated
session; NOTE race lesson: helper sinks MUST await handle.completion, not
sink onComplete), a031489e9 (B6 start: metadata wired into QS binding/host/
state). Suite 3358 passing 0 failing at B5 close. Scenario list in
examples/config.phase3.local.jsonc now includes querystudio-open.
Task ledger: #40-44 done, #45 B6 in progress, #46 B7 pending.
B6 remaining = PROGRESS Entry 7 list (completions port, debug views to
Debug Console, replay wizard standardization, MD-4 golden parity).

## 1. Read in this order

1. THIS file.
2. `coding-docs/ssms-query-docs/EXECUTION_PLAN.md` — batches B1–B7, binding-decision
   digest, commit-isolation rule, verification chain, completions-port inventory.
3. `coding-docs/ssms-query-docs/PROGRESS.md` — journal Entries 1–3; Entry 3 has the
   EXACT remaining B3 work list.
4. `coding-docs/ssms-query-docs/query-studio-design-addendum.md` — BINDING, wins over docs.
5. Docs 01–04 (same dir) — consult per-section as needed (don't re-read fully;
   the plan digests the binding decisions). Design mock: `Query Studio.dc.html`, mockup1/2.png.
6. `coding-docs/observability-docs/07-phase2-query-studio-branch-guide.md` — frozen vs
   additive rules from Phase 1.
7. Memory: `query-studio-build.md` + `perftest-harness-build.md` (auto-loaded index).

## 2. Where things stand (all committed, working trees CLEAN)

Branches: `dev/query` in vscode-mssql, sqltoolsservice, perftest.
Task ledger: #40 B1 ✅ · #41 B2 ✅ · #42 B3 IN PROGRESS · #43 B4 · #44 B5 · #45 B6 · #46 B7.

Commits this phase (vscode-mssql unless noted):
- perftest `13975cb` core: queryStudio.* marker family + sqlDataPlane./rpc.v2. span
  families registered in observability-contracts (regenerated + re-vendored).
- `ff75d72db` qs: sqlDataPlane/api.ts + fakeBackend.ts + conformance core (14 tests).
- `117278d2d` qs: Qs contracts + textSync engine + document registry (14 tests).
- `fe096bfc8` qs: M0 shell — provider/model/controller + Monaco webview + package.json
  (customEditors mssql.queryStudio, commands, settings queryStudio.*/sqlDataPlane.*).
- `a800f40ab` qs: STS2 binding + M1 connect (wire/v2.ts, sts2Backend.ts,
  sqlDataPlaneService.ts, documentSessionBinding.ts, --enable-sts2 flag; 13 tests).
- `d2541cbc6` qs: batchSplitter + RowStore w/ spill (13 tests).
- `be893ea58` qs: ExecutionOrchestrator (6 e2e tests over fake; fixed fake's
  completion-ordering race; added pageDelayMs pacing knob).

Verification state: extension suite was 3321 passing at B2 close (+~19 B3 tests since,
suites run via --grep; FULL chain not yet run for B3 — run at B3 close). Gate
query-10k-results 4/4 official + debug-console-smoke green at B2 close. Known flake:
copilotChatEntry hook timeout (Copilot-owned; suppresses 3 suite-mates when it fires).

## 3. Resume point: B3 remaining (from PROGRESS Entry 3)

1. **Controller wiring** (`src/queryStudio/queryStudioController.ts`): replace execute
   stub — on QsExecute: get `this.model.sessionBinding.activeSession` (refuse honestly
   if none), create RowStore per execution under
   `<globalStorage>/querystudio-spill/<runId>/` (context.globalStorageUri), new
   ExecutionOrchestrator with RunEvents → forward as Qs notifications
   (QsResultSetStarted/QsRowsAppended counts-only/QsResultSetEnded/QsMessagesAppended),
   track execution state + elapsed in QsState (sessionBinding.setExecuting), buffer
   QsMessageRow[] for QsGetMessages{afterIndex}, QsGetRows → rowStore.getRows,
   QsCancel → orchestrator.requestCancel, QsNavigateToLine → QsRevealPosition
   notification. Dispose previous run's RowStore on new execution + on model dispose
   (wire into queryStudioDocumentModel dispose — it already disposes sessionBinding).
2. **Webview results region** (`src/webviews/pages/QueryStudio/app.tsx` + css):
   results tab strip (Results|Messages, 30px) appears only after first execution;
   virtualized grid (24px rows, render window over QsGetRows, follow-tail when at
   bottom, "rows added" chip when not, NULL styling italic warning-tint via
   nullBitmap); Messages tab (monospace, clickable error blocks → QsNavigateToLine);
   splitter (drag + dbl-click reset 55/45 + Ctrl+R collapse); status bar rows/elapsed
   segments; **resultsRendered webview mark + PERF_MODE bridge** — reuse
   `perfMarkAfterNextPaint` from `src/webviews/pages/QueryResult/queryResultsGridView.tsx`
   (import its utility; addendum §5.2).
3. **Scenarios**: `querystudio-open` (+ maybe `querystudio-query-10k` exploratory) in
   perftest CLI registry + inproc catalog (maturity "exploratory"); keep the standing
   pair green. Registry conformance: any new marker names must already be registered
   (they are — B1 core commit covered the family).
4. **Full verification chain + qs: commit + PROGRESS Entry 4.**

Then B4 (parity band), B5 (MetadataService), B6 (completions port from
`C:\repos\test\completions\vscode-mssql` dev/karlb/completions @ 065208582 + replay
wizard standardization), B7 (preview readiness) per EXECUTION_PLAN.md.

## 4. Hard-won session facts (not in any spec — read carefully)

**Repo mechanics:**
- ALWAYS `cd /c/repos/test/vscode-mssql/extensions/mssql` before npx/tsc/tsgo — from a
  wrong cwd, npx tries to install `tsgo` from npm (E404). Same for perftest package dirs.
- Typecheck: `npx tsgo -p tsconfig.extension.json --noEmit` + `npx tsgo -p
  tsconfig.webviews.json`. Test: `npx tsc -p tsconfig.extension.json --noCheck &&
  npx vscode-test [--grep "..."]`. Full build from repo root: `npm run build`
  (grep -cE " error " should be 0).
- Files are CRLF: the Edit tool needs exact text; for scripted edits use node scripts
  with EOL detection (`s.includes('\r\n')?'\r\n':'\n'`) or write to scratchpad .js and
  run (shell-escaping inline node -e breaks on quotes/template literals).
- Pre-commit hooks run localization extraction + lint-staged. Lint rules hit before:
  `no-duplicate-imports` (one import per module path). Commit from the REPO ROOT
  (`cd /c/repos/test/vscode-mssql`) with paths `extensions/mssql/...`.
- Commit isolation (OWNER RULE): `core:` prefix for observability-contracts/registry,
  Debug Console core, classic QueryResult extraction, legacy seams, STS2 service-side;
  `qs:` for queryStudio/sqlDataPlane/sts2-binding/metadata/completions. Never mix.
- Shared contracts import `vscode-jsonrpc` (NOT `vscode-jsonrpc/browser` — breaks
  extension esbuild bundle). Pattern per debugConsole.ts.
- Webview pages: add entry in `scripts/bundle-webviews.js` entryPoints; boot pattern =
  `VscodeWebviewProvider` + `useVscodeWebview<State,Reducers>()` (gives extensionRpc +
  themeKind; onNotification returns void, lives for webview lifetime).
- Monaco: use shared `src/webviews/common/vscodeMonaco.tsx` `VscodeEditor`
  (requires themeKind prop; theme bridge built-in). monaco-editor 0.53 +
  @monaco-editor/react already deps.
- Custom editor controllers: subclass `WebviewBaseController<State,Reducers>` and
  implement `_getWebview()` returning the PROVIDED panel's webview; set panel.webview
  options+html manually, then `initializeBase()`. (WebviewPanelController creates its
  own panel — not usable for custom editors.)
- Contracts registry workflow: edit `perftest/packages/observability-contracts/
  src/registry/event-types.json` → `npx tsc -p tsconfig.json && npx vitest run &&
  node dist/generate.js` → copy `generated/typescript/observabilityContract.generated.ts`
  to `vscode-mssql/extensions/mssql/src/sharedInterfaces/` → vendor-sync test enforces.
- Promise pattern: clear "active query" slots via reactions on the COMPLETION promise
  registered at execute time (reaction order), never on run().finally().

**STS2 wire facts (pinned in src/services/sts2/wire/v2.ts — trust that file):**
- Same stdio as legacy; `--enable-sts2` flag (added in serviceclient.ts when
  mssql.sqlDataPlane.enabled). Transport = SqlToolsServiceClient send/onNotification
  with v2/* methods (free rpc.* spans).
- Secrets: send RAW in profile.auth ({kind: sqlLogin|accessToken|integrated, user,
  password/accessToken}); service SecretRedactor tokenizes pre-journal. NEVER log.
- rows notification: {queryId, resultSetId:number, pageSeq, rowOffset, rows[][], last};
  columns: {name, engineType, nullable} (parse tolerant of casing);
  complete: {queryId, status: succeeded|canceled|error|disposed, rowsAffected:
  number|number[]|null, error?{code,message,server}}; ack: notification {queryId,
  throughPageSeq}. Errors: error.data.code = Sts2.* strings.
- Capture = v2/diagnostics.setCapture (design docs say session.setCapture — WRONG).

**Recorded deviations:** M1 profile selection = quick-pick over
connectionStore.readAllConnections (via mssql.getControllerForTests seam, same as
self-test); full selectConnectionProfile factoring deferred to B4/M3. Design §17.1
"query.execute begin/end" frozen as query.submit→complete (registry note). B1
residuals carried: untitled/Save-As exploratory test, 30-min dogfood resync gate.

**Settings landed:** mssql.queryStudio.enabled (false), mssql.sqlDataPlane.enabled
(false), mssql.sqlDataPlane.backend (sts2-jsonrpc|fake). NO mssql.sts2.* settings ever.

## 5. Phase-1 foundation (context, do not rebuild)

Observability foundation is COMPLETE and checkpointed on the previous branches
(dev/karlb/perftest lineage): contracts registry + eligibility + vendor-sync guard,
evidence durability (manifests/gaps/backfill/import safety/canaries), Trace Identity
V1 + lint, designer CLI parity, quick compare + rep Compare tab, diagnostic recipes,
STS2 verify green (11 gates, sanctioned-seam allowlist D-0013). Debug Console patterns
(WebviewBaseController, classify(), Perf facade) are the house style — reuse, don't
reinvent. perftest journal: perftest/PROGRESS.md Entries 1–36.
