# Query Studio — Build Journal

## 2026-07-04 — Entry 1: Plan + B1 first slices (contracts, AD-0, M0 core)

Read the full reviewed doc set 01–04 + addendum (BINDING) + mockups +
completions-branch inventory (~31.7k lines; see EXECUTION_PLAN.md digest).
Branches confirmed `dev/query` ×3. EXECUTION_PLAN.md written (batches B1–B7,
commit isolation core:/qs:, binding-decision digest, STS2 worksheet).

SHIPPED (perftest `core:` 13975cb):
- observability-contracts: `mssql.queryStudio.*` family registered (open,
  connect begin→READY pairing per addendum §3.5, query.submit→complete —
  design's "execute begin/end" frozen as submit/complete to mirror classic,
  recorded in registry note; firstResult, resultsRendered webview mark
  epoch-aligned, rows.windowFetch, cancel), span families queryStudio.sync./
  queryStudio.lsp./sqlDataPlane./rpc.v2., derived metrics incl.
  query.toComplete/toRender. Regenerated + re-vendored; 27/27.

SHIPPED (vscode-mssql `qs:` ff75d72db — AD-0):
- src/services/sqlDataPlane/api.ts: full domain contract (doc 03 §4–6,
  §11–12) + compact page encoding w/ lazy CellValue + null bitmaps
  (addendum §3.3) + pack/decode/display helpers.
- fakeBackend.ts: transcript scripts + chaos knobs (duplicate/gap pages,
  rows-before-metadata, event-after-complete, noTerminal, fatal), sink
  contract enforced (serialized, awaited pages, one terminal, Busy, 
  idempotent close).
- test sqlDataPlaneConformance: 14/14 (ordering, terminality, cancel
  partial truth, backpressure non-overlap, sink-error isolation, fatal,
  dispose terminal D-0011 mirror, noTerminal documented as adapter-owned).

SHIPPED (vscode-mssql `qs:` 117278d2d — M0 core):
- sharedInterfaces/queryStudio.ts: QS_SCHEMA_VERSION, QsSync* protocol,
  QsState, hot-path RPCs + notifications (QsRowsAppended counts-only).
- queryStudio/textSync.ts: pure sync engine — shared FNV-1a textHash,
  applyEdits (desc order), echo suppression, stale-base rejection,
  resync valve w/ counter.
- queryStudio/queryStudioDocumentRegistry.ts: pure one-model-per-URI
  registry (refcount, dispose-on-last-detach, Save-As rekey, sweep).
- test queryStudioSync: 14/14.

B1 REMAINING (next stretch):
1. queryStudioDocumentModel.ts (adapts VS Code TextDocument ⇄ TextSyncEngine;
   owns future session binding/RowStore; rebind-safe for Save As).
2. queryStudioEditorProvider.ts + queryStudioController.ts
   (CustomTextEditorProvider, per-panel RPC via the Debug Console webview
   pattern — see debugConsoleWebviewController for the RPC host pattern;
   webview HTML + CSP w/ worker-src carve-out).
3. Webview app src/webviews/pages/QueryStudio/: check how pages are bundled
   (esbuild? scripts/build — find the pages entry list); Monaco ESM +
   editor.worker local; MonacoEnvironment.getWorker explicit; theme bridge;
   layout per doc 01 §4–5 (results ABSENT before first run); keybindings
   addendum §4; open.begin/end markers + monacoMs attr.
4. package.json: customEditors viewType mssql.queryStudio (priority option,
   *.sql), commands (new/openActive/openInClassicEditor/duplicateAsNewQuery/
   reconnect/showStatus), settings queryStudio.* + sqlDataPlane.* (enabled
   false previews), F5 package keybinding w/ activeCustomEditorId when.
5. Exploratory test: untitled custom-editor Save-As behavior (doc 04 §7.2).
6. Full verification chain + PROGRESS entry + commits.

VERIFY (B1 close): builds clean (extension bundle initially broke on a
vscode-jsonrpc/browser import in queryStudio.ts - fixed to vscode-jsonrpc,
matching debugConsole.ts); extension suite 3308 passing (+28 B1) / 1 known
copilot flake; gate query-10k-results 4/4 official; debug-console-smoke
green; contracts 27/27.

SHIPPED (vscode-mssql qs: fe096bfc8 - M0 shell): document model (WorkspaceEdit
application, echo suppression, Save-As rebind, resync diagnostics), editor
provider (viewType mssql.queryStudio, commands, preview gate), controller
(provided-panel WebviewBaseController host, QsSync bridge, <=10/s state
pushes, open markers, honest M0 stubs), Monaco webview shell (VscodeEditor
theme bridge, doc-01 densities, results region absent pre-execution,
coalesced edit groups, host-owned undo/redo/save, F5/Ctrl+E), package.json
contributions + queryStudio bundle entry.

B1 STATUS: COMPLETE except two live-host residuals -> carried to B2:
(1) exploratory untitled/Save-As custom-editor behavior test (doc 04 s7.2),
(2) 30-min dogfood resync-count-zero gate (needs interactive use).

## 2026-07-05 - Entry 2: B2 COMPLETE (AD-1/AD-2 + M1)

SHIPPED (vscode-mssql qs: a800f40ab):
- wire/v2.ts: STS2 wire pinned from CONTRACT.md/CLIENT.md/Core reducer
  (2.0.0-preview.1). Worksheet answers INLINE: #2 ack=client notification
  high-water throughPageSeq; #3 dispose=D-0011 single terminal; #4
  rowsAffected structured (number|number[]|null); #5 serverInfo in open
  result + SPID probe; capture=v2/diagnostics.setCapture; #1 verbatim
  messages arrive as data via v2/query.message.
- sts2Backend.ts: protocol engine - Sts2Rpc transport port (real transport
  wraps SqlToolsServiceClient => shared stdio v2 lane + free rpc.* spans),
  ordered per-query lanes, orphan buffer (execute-response race), ack
  ledger (high-water strictly AFTER sink acceptance), invariants (metadata
  before rows, gapless pageSeq, monotonic rowOffset, one terminal, silence
  after) => ProtocolViolation + backend cancel, deadline SYNTHESIS (cancel
  drain 30s, dispose drain, fatal => connectionLost; synthesized flagged +
  diagnosed), Sts2.* => SqlDataPlane.* error mapping.
- sqlDataPlaneService.ts: composition root (backend by setting; fake for
  tests), --enable-sts2 launch flag in serviceclient when
  sqlDataPlane.enabled, mssql.sqlDataPlane.showStatus command.
- documentSessionBinding.ts (M1): saved-profile quick pick via connection
  store (password from credential store inside the open closure only),
  connect.begin->ready markers (failure=ready+error+reason per addendum
  3.5), lost/close fan-out, SPID probe, Retry/Open-in-classic, NO v1
  fallback. Controller connect/disconnect/reconnect real; execute = honest
  M2 stub. DEVIATION RECORDED: full selectConnectionProfile seam factoring
  of the classic connection UI deferred to B4/M3 (quick-pick over saved
  profiles is the M1 path, same seam as self-test).
- 13 new conformance tests (scripted wire) - 13/13 first run.

VERIFY: build clean; suite 3321 passing (+13) / 1 known copilot flake;
gate 4/4 official; smoke green.

M1 GATE NOTE: live connect to Sts2TestDb through a real STS2 process needs
the data plane enabled in a running VS Code (interactive or a perftest
scenario) - carried into B3 where querystudio-open-connect becomes a
scenario; the binding itself is conformance-proven against the pinned wire.

NEXT (B3 per EXECUTION_PLAN): lexer/splitter, ExecutionOrchestrator,
RowStore+spill, MessageLog+error mapping, QsGetRows windows, grid
extraction steps 1-3 (classic gate green per step), Messages tab,
multi-result, cancel, webview mark bridge, querystudio scenarios.

## 2026-07-05 - Entry 3: B3 host pipeline (foundations + orchestrator)

SHIPPED (qs: d2541cbc6): batchSplitter (GO/GO n corpus-tested, nested
comments, escaped quotes/brackets; leadingKeyword char-walk for the future
DDL sniffer; mapServerLineToDocument w/ addendum 3.4 vector) + RowStore
(compact pages, LRU, spill v1 length-prefixed JSON frames, caps, windows w/
null bitmaps, spill deleted on dispose; spill-disabled = honest in-memory).
13 tests.

SHIPPED (qs: next commit): ExecutionOrchestrator - full M2 host pipeline
(markers, batch loop, sink->RowStore/messages fan-in, continue-on-error
SSMS default, stopOnError, cancel partial truth, connectionLost,
rowsAffected aggregation). FIXED a real fake-backend completion-ordering
race (active slot now clears via completion promise reaction order).
6 e2e tests; 18/18 with conformance.

B3 REMAINING (next stretch):
1. Controller: real QsExecute (model.sessionBinding.activeSession +
   orchestrator + RowStore per execution under globalStorage/querystudio-
   spill/<runId>), QsGetRows from RowStore, QsCancel, QsGetMessages buffer,
   notifications (QsResultSetStarted/RowsAppended counts-only/Ended,
   QsMessagesAppended), execution state in QsState + elapsed.
2. Webview: results region (tabs strip Results/Messages; virtualized grid
   24px rows over QsGetRows windows w/ follow-tail + rows-added chip; NULL
   styling; Messages tab w/ clickable error blocks -> QsNavigateToLine +
   flash), splitter + Ctrl+R collapse, status bar rows/elapsed segments,
   resultsRendered webview mark + PERF_MODE bridge (addendum 5.2 - reuse
   QueryResult page perfMarkAfterNextPaint utility).
3. Scenarios: querystudio-open + querystudio-query-10k (exploratory, both
   catalogs where feasible); standing pair green.
4. Full chain + commits + journal.

## 2026-07-05 - Entry 4: B3 COMPLETE (M2 results core)

SHIPPED (vscode-mssql qs: c0034d4d9; perftest core: a012a11):
- executionHost.ts: shared per-doc execution state; fresh RowStore+spill per
  run; honest refusals. Controller: real execute/cancel/getRows/getMessages/
  navigate; counts-only notifications; QsState execution+results live.
- Webview results region: Results|Messages tabs, stacked virtualized grids
  (window fetch, follow-tail + new-rows chip, NULL bitmap styling), Messages
  w/ clickable error nav, splitter + Ctrl+R, rows/elapsed status segments,
  resultsRendered double-rAF mark.
- querystudio-open scenario PASSED live: wallclock 1435ms, queryStudio.open
  1167.6ms (pair-derived, measurement-eligible).

THREE REAL BUGS the scenario caught (fix knowledge):
1. Monaco CDN: @monaco-editor/react loader defaults to jsdelivr — webview
   never booted in the harness. Fix: monacoSetup.ts binds BUNDLED monaco via
   loader.config({monaco}) + editorWorker bundle entry + .ttf loader
   (queryStudio.js now ~9.6MB). Import monacoSetup FIRST in index.tsx.
2. Custom-editor RPC: provided panels MUST call updateConnectionWebview(
   panel.webview) before initializeBase — else every message drops with
   "webview is not set" (panel-owning base does it in createWebviewPanel).
3. Late registration: queryStudio.enabled flip now registers without reload
   (config watcher); mssql.perf.setConfig (PERF_MODE-only) added so
   scenarios can enable preview gates.
DIAGNOSTIC INFRA ADDED: inline qsBootError relay (window error/rejection ->
postMessage -> host logger) + __vscodeApiPreAcquired guard in the shared
acquireVsCodeApi fetcher. Boot failures are now visible host-side.

VERIFY: suite 3340 passing (+19 B3) / copilot flake; build clean; gate 4/4
official; smoke green; querystudio-open green. Lint note: do NOT use
eslint-disable for react-hooks/exhaustive-deps (rule not defined here).

B3 residuals -> B4: live SQL execute-through-grid scenario
(querystudio-query-10k needs a real STS2 connect in the harness: saved
profile provisioning TBD); grid extraction steps (classic-grid reuse)
deferred - QS-native grid proved the data source first.

NEXT: B4 (M3 parity band - SET wrappers, plans, per-cell nav/copy, database
dropdown, estimated plan, parse) per EXECUTION_PLAN.

## 2026-07-05 - Entry 5: B4 COMPLETE (M3 parity band core)

SHIPPED (qs: 9a92d9d74): orchestrator SET-wrapper modes (parseOnly/
estimatedPlan/actualPlan; ON before user loop, OFF in FINALLY even on
cancel/failure, skipped when session dead); canonical showplan-XML column
detection -> isPlanResult flags; ISqlSession.signalDatabaseChanged added to
domain contract; ExecutionHost.listDatabases (sys.databases) + setDatabase
(USE [db] escaped, signal on success only, refuse while executing);
controller mode mapping + real list/set database; webview db dropdown +
Parse/EstimatedPlan buttons + ActualPlan toggle + grid cell select w/
Ctrl+C copy (Ctrl+Shift+C row+headers). 5 tests.

VERIFY: suite 3348 passing (0 failing!); build clean; gate 4/4; smoke
green; querystudio-open 1542ms green.

B4 residuals -> later: plan TAB rendering (plan sets currently flagged +
listed as grids; the executionPlan webview page exists for reuse), per-cell
context menu, Ctrl+R conflict check vs VS Code default, dedicated
querystudio-query scenario w/ live SQL connect.

NEXT: B5 (MD-0..3 MetadataService): catalog contracts + SoA DatabaseCatalog
snapshots, dedicated metadata session (one per ServerKey, applicationName
vscode-mssql-metadata, background priority), sys.* batched loaders, drift
detection tiers, disk cache, buildSchemaContext projection (absorbs the
completions branch schemaJsonService compaction, MD-4 golden parity later
in B6).

## 2026-07-05 - Entry 6: B5 COMPLETE (MetadataService core)

SHIPPED (qs: edbd8ccde): catalogModel.ts (SoA + interning + folded name
index + collation-aware resolveName + per-section readiness + generation
snapshots; buildSchemaContext deterministic projection w/ FK one-hop,
fidelity tiers, budget degradation, remoteLm privacy gate);
metadataService.ts (H1-H3+H5 hydration over background data-plane queries,
section-failure honesty, DDL sniff + CHECKSUM_AGG digest poll + explicit
refresh, DataPlaneMetadataSessionSource dedicated session per §8.2).
10 tests. FIXED latent race: helper sinks must await handle.completion
(session frees active slot in completion reaction order) - fixed in
metadata rows / listDatabases / USE / SPID probe.

VERIFY: suite 3358 passing (0 failing); build clean; gate 4/4;
querystudio-open 1742ms green.

B5 residuals (recorded, not blockers): disk cache (manifest+catalog.mdc,
design §11) NOT built yet; keys/indexes/params/descriptions sections
declared but absent (H4/H6/H7); ServerCatalog (databases combo currently
served by executionHost.listDatabases); wire into Query Studio
controller/QsState metadata block + status-bar readiness (B6 alongside
completions port, which is the first real consumer).

NEXT: B6 (MD-4 + M5): port completions from completions branch onto
buildSchemaContext (golden parity vs schemaJsonService), replay wizard
standardization, debug/replay views onto Debug Console.

## 2026-07-05 - Entry 7: B6 STARTED (metadata wired into QS)

SHIPPED (qs: a031489e9): DocumentSessionBinding acquires a metadata catalog
after connect (dedicated data-plane session per design §8.2; failures never
degrade connect; released on disconnect/dispose); ExecutionHost feeds run
text to the DDL sniffer after every run; QsState.metadata carries live
readiness/generation/mode. Suite 3355 (flake only); scenario green.

B6 REMAINING (the port — needs a fresh context, ~15k lines to read):
1. PORT sqlInlineCompletionProvider.ts (3235 lines) from
   C:/repos/test/completions/vscode-mssql (dev/karlb/completions @
   065208582) extensions/mssql/src/copilot/: LM prompt building, model
   selection, streaming, acceptance tracking. REBASE its schema context
   calls onto sessionBinding.metadataHandleForConsumers.buildSchemaContext
   (replaces sqlInlineCompletionSchemaContextService.ts 3740 lines — that
   service is NOT ported; MD-4 golden parity test compares outputs on the
   same fixture catalog first).
2. inlineCompletionDebug views (+ webviews/pages/InlineCompletionDebug)
   -> adapt to Debug Console patterns (webview panel base, versioned
   contracts, classify()).
3. Replay wizard standardization: adapt the completions ReplayTraceBuilder
   as the general-purpose one (completions traces + Query Studio runs,
   standard formats).
4. Wire provider registration behind copilot feature gate + QS completions
   state (QsState.completions).
5. Verification chain + core:/qs: commits + PROGRESS Entry 8.

THEN B7 (M6): observability polish, spans for sync/exec paths in Debug
Console timeline, dogfood gates, preview-readiness checklist (doc 04 §18).

## 2026-07-04 - Entry 8: B6 COMPLETE (completions port, both editors)

SHIPPED (6 commits):
- core: 4b978a8c5 — logger2 vendored from upstream (dependency only).
- qs: 9d1afc1bd — foundation: inlineCompletionDebug contracts + latency
  buckets, languageModels/shared, languageModelSelection, feature gate,
  copilotEnableSettingsGuard, debug profiles/store, trace
  serializer/persistence/loader, constants/telemetry/loc additions.
- qs: eda5a9039 — MD-4: selection pipeline extracted VERBATIM into
  completionSchemaContextCore.ts (budgets, relevance terms, ranking,
  degradation, normalize); catalogSchemaContextPayload.ts synthesizes the
  RawSchemaContextPayload from CatalogSnapshot (replaces the mega query);
  MetadataService hydration gained H0 env (engineEdition/defaultSchema/
  collation→caseSensitive), H4 PK columns, H5B FK column pairs, H6 routine
  parameters (typeDisplay'd; ordinal 0 = scalar return); curated system-DMV
  surface lifted into static completionSystemObjectCatalog.ts (scope gating
  by engine edition; masterSymbols always [] — matches the query's WHERE 1=0
  branch). CompletionSchemaContextService: resolver chain = Query Studio
  binding metadata → classic connection over the data plane (first-hydration
  wait 120s, LRU 8 acquisitions); normalized-context cache per
  fingerprint|generation|fetchCacheKey; selection per call.
  sqlInlineCompletionProvider.ts ported with ONLY the schema-context import
  rebased; registered for language 'sql' in mainController. MD-4 golden
  parity test (8 tests) asserts exact prompt lines + determinism.
- qs: 6114ebe9d — sdkLanguageModels verbatim (proposed
  registerLanguageModelChatProvider, graceful absent), @anthropic-ai/sdk +
  openai deps (xAI reuses openai client), api-key commands, settings.
- qs: 26dc2af9e — InlineCompletionDebug panel + FULL replay system (cart,
  sequential + matrix runs, trace sessions browser) — controller adapted to
  target WebviewPanelController (no vscodeWrapper param) + new schema
  service; webview ported whole (+recharts); bundle entry; open command
  feature+palette gated; traces save on deactivate.
- qs: 0e1364da7 — Query Studio Monaco ghost text: qs/inlineCompletion RPC →
  shared provider over the custom editor's REAL backing TextDocument;
  acceptance relayed to the standard accepted command (markAccepted +
  telemetry identical to classic); QsState.completions.enabled live;
  inlineSuggest enabled.

LESSONS: (1) the old schema service returns a STRUCTURED context — the
prompt TEXT renderer lives in the provider; parity work = payload synthesis,
not text matching. (2) fixtureSnapshot(undefined) triggers JS default params
— use a sentinel for "unknown". (3) This repo's lint flags rest-omission
destructuring as unused vars — use copy+delete. (4) FakeBackend scripts
match FIRST predicate: H4/H5B contain "sys.columns", so their fixtures must
precede the H3 matcher.

DEVIATIONS RECORDED: no fetch-wait for QS docs (hydrating catalog ⇒ that
request runs without schema context; provider reports
fallbackWithoutMetadata honestly); sys.all_objects existence probe dropped
from the static DMV catalog; unknown engine edition ⇒ scope=all only;
fluentSlickGrid.css theme delta NOT ported (touches classic grid styling —
separate decision); classic-resolver acquisitions evicted LRU(8), no
onConnectionsChanged eviction yet; replay generalization to Query Studio
runs (beyond completions traces) moved to B7.

VERIFIED (2026-07-05): full `npm run build` clean (0 error lines); full
`npx vscode-test` green except the known Copilot-owned copilotChatEntry
hook-timeout flake (prior full run: 3363 passing / 12 pending; the one real
failure it exposed — duplicate refresh-command registration when a second
CompletionSchemaContextService instantiates — fixed in 58364148c and the
targeted suite re-verified 8/8). Gates: query-10k-results 4/4 official
(warm ~1.1s), debug-console-smoke passed, querystudio-open passed 1550.8ms.
Both working trees clean. BONUS: recovered perftest journal Entries 34–35
(lost to a wrong-cwd write in a prior session; found as a stray
extensions/mssql/PROGRESS.md, spliced back before Entry 36, perftest
b922964).

NEXT: B7 (M6) — observability polish (sync/exec spans in Debug Console
timeline), replay generalization for QS runs, dogfood gates,
preview-readiness checklist (doc 04 §18).

## 2026-07-05 - Entry 9: B7 COMPLETE (common observability + replay generalization + preview readiness)

SCOPE (Karl's directive expanded M6): modernize end-to-end diag/logging for
completions + Query Studio + MetadataService with FIRST-CLASS shared
observability; keep the completions branch's rich event capture, settings
capture, and settings-override replay — generalized into the CORE framework
where possible, feature-specific where needed.

SHIPPED — vscode-mssql (dev/query):
- core: 1a450183a — re-vendored contract (B7 vocabulary; see perftest
  a742401): metadata.* / completions.* / queryStudio.inlineCompletion.* /
  replay.* span families + settings.snapshot/changed + queryStudio.
  runRecord.captured. Fixed a live conformance gap: metadata.hydrate had
  been emitting UNREGISTERED since B5.
- core: 25a54eba2 + cc44c9391 + 3238f5d4c — feature-capture framework in
  src/diagnostics/featureCapture/: FeatureCaptureStore<TEvent,TOverrides>
  (ring, pending→final, mutateEvent, panel-open/record-when-closed gating,
  import w/ id-counter recovery), trace codec (versioned envelope, key-set
  redaction walker + structural hook, oldest-first size cap), trace files
  (naming/folder/~-expansion/watcher/index+facet hooks), FeatureReplayEngine
  (cart w/ per-item labels, snapshot/override/live config modes, single +
  matrix runs, sequential single-flight drain, cancel keeps running row,
  throwing executors contained, replay.run/replay.item diag spans, Trace
  Identity tags), settings-snapshot capture (classified kind:state events;
  secret-pattern keys ALWAYS tokenized, spec cannot loosen). 18 unit tests.
- qs: 62d41a7ee — completions = instantiation #1 (behavior-identical, net
  -437 lines): store extends FeatureCaptureStore; serializer/persistence/
  loader delegate to the codec/files generics (redaction surface is now a
  declarative FeatureTraceRedaction); controller hosts FeatureReplayEngine
  (prompt rebuild/model selection/schema-context strategy stay feature-side
  as host callbacks). Diag bridge: completions.request span per request +
  correlated completions.stage/completions.result instants, emitted
  REGARDLESS of rich-capture gating (protocol metadata only — prompts never
  ride DiagEvents); settings.snapshot on panel open + settings.changed
  deltas. Golden parity stayed 8/8.
- qs: 1d91ae5e2 — instrumentation completion: queryStudio.cancel
  (msToAck/msToTerminal), rows.windowFetch begin/end (honest fromSpill),
  queryStudio.sync.applyEdit span, queryStudio.inlineCompletion.bridge span
  (surface/trigger/returned; measurable against completions.request for the
  <=10ms bridge target), sqlDataPlane.execute span (STS2 query lane,
  construct→terminal), metadata.contextBuild span + metadata.drift instant,
  mssql.perf.queryStudioState PERF_MODE probe (phase/rowCounts/spill/
  metadata generation/sync resync count).
- qs: 8f8f0d5fd — QsRunRecord recorder + Replay Lab (instantiation #2):
  armed via panel-open OR mssql.queryStudio.replay.enabled; records carry
  salted digests ALWAYS (uri/profile/batch text), SQL text ONLY under Debug
  Console elevated capture with the effective policy id recorded on the
  record (worksheet row 9 honesty); replay re-drives the live document's
  ExecutionHost through the normal data-plane API with database/mode
  overrides, sequential + matrix; digest-only records and disconnected
  targets REFUSED with reason. Replay Lab = dedicated panel
  (mssql.queryStudio.openReplayLab) + webview page. 4 capture tests.
- qs: privacy canaries (featureCapturePrivacyCanary, 4 tests): run-record
  traces clean by default; elevation carries SQL by design but server/path
  stay digests; completions redaction surface strips prompts/responses/
  schema text incl. nested; model.prompt/response never plaintext in
  redacted/digest. Full canary corpus 9/9.
- qs: 0f4032d90 — PERF_MODE harness seams: single-profile auto-pick in QS
  connect (perf mode only) + mssql.perf.queryStudioConnect/Execute.

SHIPPED — perftest (dev/query):
- core: a742401 — registry vocabulary (above), regenerate + re-vendor,
  contracts 27/27.
- f36d409 — querystudio-query-10k scenario (exploratory; same 10k fixture +
  provisioned server as the classic gate; profile written as the ONLY saved
  connection so the auto-pick engages; unmeasured SELECT 1 preflight after
  connect — the post-connect SPID probe raced the single sts2 query slot;
  ScenarioSpec.userSettings merge-written pre-launch because post-activation
  setConfig is too late for --enable-sts2; opt-in withinMeasuredWindow
  scopes pair derivation to scenario.start..end). `perftest head-to-head`
  command (default classic vs QS; latest official-passing runs; medians/p95/
  delta bars/phase rows; non-gating; exit 6 honestly when a side is empty;
  benchmark.html design system). perftest workspaces 110/110 (13 new).

LESSONS: (1) diag.withTrace is synchronous-scope — thread traceId explicitly
through async pipelines. (2) DiagStatus is a closed union — map replay
outcomes to ok/warning + an outcome field. (3) Emit substrate events INSIDE
feature record-helpers but BEFORE their capture gate: substrate visibility
must not depend on rich-capture arming. (4) Structural typing let the
completions webview keep its exact contract types while the engine's
generic state assigns into them (required→optional direction) — zero
webview churn in the migration. (5) Post-activation setConfig cannot add
service spawn flags; provision user settings before launch.

DEVIATIONS RECORDED: queryStudio.lsp.* spans deferred (no LSP-bridge RPC in
the repo yet — shadow-LSP deferral; family stays registered). Replay Lab is
a dedicated panel, DC 'replay'/'completions' left-rail pages stay gated
(embedding = follow-up UX, same deviation shape as B6's panel decision).
Metadata perf scenarios (hydrate-cold/warm, context-build) deferred:
metadata.hydrate/contextBuild spans are live in captured runs, but dedicated
scenarios need realistic catalog fixtures to be honest (FakeBackend's empty
catalog would measure overhead only). QS replay matrix v1 axes =
database x mode (profile-style axes when QS grows config profiles).
querystudio-query-10k stays exploratory pending multi-rep baseline history;
SqlLogin credential-seeding path untested live (box provisions Integrated).
Head-to-head interpretation caveat: QS toComplete (5.6ms) is the product's
own sts2-plane marker and completes before render work — flagged in the
report, not adjusted.

STS2 WORKSHEET at B7 exit: row 9 (capture effective-mode) CLIENT-SIDE
ANSWERED via QsRunRecord policy recording; service-side setCapture echo
still desirable pre-GA — explicit gate exception. Row 1 (verbatim messages)
remains the open preview blocker to verify against sts2 src. Rows 3/10
answered; 2 answered in B2; 4/5/7 fallback-covered; 6/8 milestone-gated.

VERIFIED (2026-07-05): typechecks (extension + webviews) clean at every
commit; full `npm run build` 0 error lines; full `npx vscode-test` 3390
passing / 12 pending / 1 failing = the known Copilot-owned copilotChatEntry
hook-timeout flake only (+27 tests over B6: framework 18, capture 4, canary
4, +1). perftest workspaces 110/110 (obs-contracts 27, perf-contracts 14,
cli 57 incl. 13 new, inproc 12). Gates: query-10k-results 4/4 official
(steady 1133–1169ms, re-run WITH the normalizer window change active),
debug-console-smoke passed (13.9ms), querystudio-open passed (1523.4ms —
B6 baseline 1550.8ms), querystudio-query-10k LIVE pass exit 0 (wallclock
550.9ms official; toComplete 5.6ms monotonic; toRender 167.0ms epoch; both
10k-row proofs green). Head-to-head sample rendered from the real store
(QS wallclock -52.8% vs classic; env-hash mismatch honestly noted, n=1 vs
3). Both working trees committed clean.

NEXT: preview-readiness residuals — verify worksheet row 1 against the
service; B5 disk cache; plan TAB rendering; B1 residuals (untitled/Save-As,
30-min dogfood resync gate); DC embedding of the two feature panels;
multi-rep QS baseline history then maturity review.

## 2026-07-05 - Entry 10: Post-B7 full evaluation + worksheet row 1 CLOSED

Full evaluation re-run (details: language-service-docs/PROGRESS.md Entry 1):
build/typechecks clean, suite 3390/12/1-known-flake, perftest 110/110,
gates 16/16 passed (debug-console-smoke, querystudio-open,
querystudio-query-10k ×3 official — multi-rep baseline residual now
accruing — and query-10k-results).

Worksheet row 1 ANSWERED + service FIXED (sqltoolsservice dev/query):
verbatim by construction; SqlClient driver now delivers InfoMessage
(PRINT/RAISERROR≤10) as v2/query.message with `line`; new QueryFlowTests
passthrough case. The M2-exit/preview blocker is CLEARED. Row 4's
client-side "(N rows affected)" rendering confirmed correct.

Residual dispositions recorded in language-service-docs/PROGRESS.md Entry 1
(B5 disk cache / plan tab / DC embedding → backlog; dogfood + SqlLogin →
need human/live env). Next big effort: T-SQL language service
(language-service-docs/EXECUTION_PLAN.md, batches B8..B14).

## 2026-07-05 - Entry 11: QS-P1 SSMS-parity QoL batch (Karl's 11 asks) [COMPLETE]

SCOPE (verbatim intent): (1) live running timer in status bar (2) SPID in
status bar w/ refresh (3) USE db updates SPID?/dropdown/state (4) cross-
execution transactions (5) session/query options parity (6) large-query/
wide/blob grid perf (7) JSON/XML cell links → document (8) many-grids UX
(9) NULL styling (10) default grid styling settings (11) filter/sort widget
like v1.

SURVEY FINDINGS (two agent maps, 2026-07-05): SPID already complete (probe
+ status bar); NULL styling present but not theme-token parity; timer field
crosses but never ticks; editor-typed USE untracked (no ENVCHANGE on wire);
transactions already persist across executions (same session, nothing
injected in normal mode) but no indicator/guard; mssql.query.* settings are
DECLARED-ONLY even in classic (STS v1 read them via LSP config sync — QS
must apply them itself); classic grid = slickgrid w/ headerFilter plugin,
in-memory sort/filter under mssql.resultsGrid.inMemoryDataProcessingThreshold
(5000), hyperLinkFormatter for isXml/isJson + content sniffing
(webviews/common/xmlUtils+jsonUtils), openFileThroughLink host reducer,
grid settings read in queryResultWebViewController; QS grid = custom
row-virtualized HTML table (no column virtualization, no truncation wiring,
maxCellBytesHonored:false).

SHIPPED SO FAR:
- (1) webview-local 500ms elapsed ticker derived from startedEpochMs
  (app.tsx) — counts during silent long queries; terminal shows host value.
- (2) SPID: no change needed (probe at connect incl. reconnect path).
- (3) USE tracking: service 7a99455f (sqltoolsservice) — ExecCompleted
  gains Database (SqlClient connection.Database = driver ENVCHANGE truth)
  → v2/query.complete "database"; client sts2Backend.onWireComplete fires
  signalDatabaseChanged(db, "backend") when differing (no-op when same);
  binding re-keys the metadata catalog on database change (fresh dedicated
  session, new CatalogKey); dropdown/status bar update via existing state
  push. Wire test in sts2Backend.test.ts (change + no-spurious-event).
  NOTE: USE does NOT change SPID (same session) — expected behavior.
- (4) transactions: cross-execution already worked (same connection);
  added @@TRANCOUNT post-run probe on the SAME session (binding.
  probeTransactionState, called from executionHost.finishRun),
  QsConnectionState.openTransactions, warning-styled TRAN (n) status-bar
  badge, and a modal disconnect guard ("Disconnect (roll back)").
- (5) options: NEW src/queryStudio/sessionOptions.ts — validated/whitelisted
  snapshot of all mssql.query.* settings, deterministic SET batch (ANSI
  family or ANSI_DEFAULTS, ARITHABORT, XACT_ABORT, NOCOUNT, STATISTICS
  TIME/IO, ROWCOUNT, TEXTSIZE, LOCK_TIMEOUT, QUERY_GOVERNOR_COST_LIMIT
  when >=0, DEADLOCK_PRIORITY, ISOLATION LEVEL whitelist, NOEXEC last),
  applied on the user session at connect/reconnect (session serializes, so
  user queries queue behind it); per-QUERY executionTimeout →
  ExecuteOptions.timeoutMs (controller reads, orchestrator passes).
  6 unit tests incl. injection-safety.
- (7)(9)(10) LANDED (G1): XML/JSON cell links — detection via wire
  typeHints[col]==="xml" || sqlType==="xml" + isXmlCell/isJson content
  sniffing (shared webviews/common utils) → <a class="qs-cell-link"> →
  qs/openCellDocument {resultSetId,row,column,format} → controller fetches
  the single cell via executionHost.getRows, pretty-prints (new
  cellDocument.ts indentXml/prettyPrint — xml-formatter default-import is
  esbuild-only, so a minimal indenter; JSON via parse+stringify), opens
  Beside as preview. NULL cells: classic theme tokens
  mssql.resultsGridNullBackground/Foreground + italic. QsState.gridStyle
  (REQUIRED) {fontFamily?, fontSize? (editor.fontSize fallback),
  alternatingRowColors, showGridLines both|horizontal|vertical|none,
  rowPadding?} from mssql.resultsFontFamily/Size + mssql.resultsGrid.*,
  live via the config watcher; dynamic rowHeight=24+rowPadding used in ALL
  virtualization math + CSS var; alt-rows via absolute-index qs-row-alt
  (spacer row breaks nth-child parity). New pure modules gridStyle.ts +
  cellDocument.ts w/ 16 tests.
- (11)(8)(6) IN FLIGHT (G2): materialized-mode in-memory sort/filter under
  gridStyle.inMemoryDataProcessingThreshold (classic 5000 default; chunked
  full fetch when complete+under threshold; SQL NULLs-first asc; original
  row numbers kept; over-threshold/streaming → honest disable note), header
  sort toggle + filter popup (contains + distinct values capped 200),
  lazy-mount grid bodies via IntersectionObserver (captions always),
  display clamp 2048/tooltip 512 + "text" format on qs/openCellDocument
  for clamped cells.

- (11)(8)(6) LANDED (G2): sharedInterfaces/queryStudioGridOps.ts pure ops
  (compareCells w/ SQL NULLs-first + numeric typeHints, applyFilterSort,
  distinctValues cap 200, clampDisplay) — 20 tests; header sort toggle
  asc→desc→none + filter popup (contains + distinct checklist + Select
  All); materialized mode = chunked 512-row QsGetRows full fetch when
  complete && rowCount <= gridStyle.inMemoryDataProcessingThreshold
  (classic default 5000; over-threshold/streaming shows the honest
  disable note; original row numbers via source indices; "N of M shown");
  ResultGridBlock lazy-mount (IntersectionObserver rootMargin 150%,
  captions always, never unmounts); display clamp 2048 + tooltip 512 with
  clamped cells linking out via qs/openCellDocument format "text".

DEVIATIONS: classic slickgrid/FluentResultGrid NOT adopted (custom table
extended; Fluent convergence = future option); autoSizeColumnsMode not
implemented (CSS max-width ellipsis); wire maxCellBytes still unhonored by
the service (client display clamp instead); QS wide/blob perf scenarios
(classic query-wide-columns/query-blob-xml equivalents) deferred; USE does
not change SPID by design (same session — item 3's SPID mention was a
conflation; the DATABASE updates everywhere). Same disable-note text for
over-threshold and still-streaming.

VERIFIED (2026-07-06): tsgo extension+webviews clean; repo build 0 error
lines; full suite 3529 passing / 12 pending / 1 failing = the known
copilotChatEntry flake only (+45 tests: sessionOptions 6, sts2 wire 1,
cellDocument 8, gridStyle 10, gridOps 20); gates 16/16 (run a9447d30:
querystudio-query-10k 453.2–562.8ms official — no regression from the
connect-time SET batch or post-run tran probe; querystudio-open,
query-10k-results, debug-console-smoke passed) against the REBUILT service
(sqltoolsservice 7a99455f: database on v2/query.complete; verify.sh
--quick green). Commits: vscode-mssql 611ce7d55 (qs:), sqltoolsservice
7a99455f. Trees clean.

RESIDUAL MANUAL VALIDATION (needs a human + live server): typed-USE
dropdown follow-through, TRAN badge + disconnect guard UX, filter/sort
feel on real data, grid styling settings visual check, XML/JSON link
documents — all wired and unit-tested but not yet dogfooded.

## 2026-07-06 — Entry 12: QS-1 plan viewer integration [COMPLETE] (remaining-tasks pass)

Context: OE v2 B15–B21 complete + validated live (oe-docs PROGRESS Entries
2–8); now working the revised remaining-tasks doc
(central_remaining_docs_review_pack/remaining_tasks.md) high-pri queue.

SHIPPED — vscode-mssql qs: b2e5625a7: execution plans open in the classic
execution-plan VIEWER instead of stranding as flagged grids (B4 residual
closed). Host: qs/openPlan RPC → single-cell showplan XML from RowStore →
openExecutionPlanWebview (viewer reuse; plan parsing rides the same STS v1
service classic uses — recorded as viewer reuse, not a data-plane
dependency). Webview: 'Open execution plan' link on plan-flagged blocks
(live + lazy captions); auto-open once per plan set when a run armed by
Estimated Plan or the Actual Plan toggle ends succeeded OR
completedWithErrors (SSMS multi-statement behavior); per-resultSet dedup;
failed/canceled/connectionLost never auto-open.

VERIFIED: build 0 errors; suite 3567/12/1 (known flake); gates 20/20
(run 2026-07-06T05-14-31Z_274fd463 — incl. objectexplorerv2-browse).
MV-10 plan-viewer live UX stays on the manual ledger.

NEXT (remaining-tasks queue): LS-10 native diagnostics (language-service
EXECUTION_PLAN B10) → LS-11 hover/signature → LS-12 scripting/definition
→ STS2-1 M7 verify+evidence → STS2-3 maxCellBytes + QS-3 wide/blob →
QS-2 grid convergence decision record.

## 2026-07-06 — Entry 13: STS2-3 + QS-3 COMPLETE — remaining-tasks P0/P1 queue DONE

SHIPPED — sqltoolsservice 7532d145 (maxCellBytes honored on the wire:
lower-only bound on v2/query.execute options, per-cell truncation
wrappers {$t:'truncated', of, bytes, digest:sha256, v:prefix≤64KB never
splitting a code point}, capability maxCellBytesHonored:true, journaled
effective bound for replay determinism; SPEC §7.3/7.5/7.7 +
SPEC-CHANGE-0001 in DECISIONS.md — flagged for Karl's review; scenario
matrix 46→47; verify --quick green + report entry). ALSO sqltoolsservice
328b47b6: P0 LATENT determinism fix (seed 7496: query.cancel during
Disposing stomped the dispose ack → lost terminal + leaked session;
found by the M7 10k sweep; 10k green ×2 post-fix) — the FULL M7 ladder
is now green in ONE run at 328b47b6 incl. mutation 84.3% (verify-latest
.md artifact). TAG sts2-v2.0.0-preview = Karl's human gate.

SHIPPED — vscode-mssql qs: 99a44957c (capability derived from
v2/initialize; ExecuteOptions.maxCellBytes rides the wire; truncated
cells → CellValue.truncated with prefix rendering + link-out, spill-safe;
+4 wire tests). perftest: querystudio-query-wide + querystudio-query-blob
(exploratory, classic-fixture reuse, rows-guarded proofs) — first live
pass 8/8; standing gates now 28 reps (run 2026-07-06T10-35-34Z_61d46160).
DEVIATIONS: QS wide scenario proves rows not columns (no QS column-count
marker/probe); no per-cell "truncated" badge yet (domain model carries
digest/originalBytes; QsCellWindow.truncatedBitmap dormant for future UI).

REMAINING-TASKS QUEUE CLOSED: QS-1 ✅ QS-2 ✅ LS-10 ✅ LS-11 ✅ LS-12 ✅
STS2-1 ✅ (tag = human gate) STS2-3+QS-3 ✅. Deferred per directive:
central observability C0–C4, DC-1..8 decisions, LS B13/B14, P2 items —
see central_remaining_docs_review_pack/remaining_tasks.md tiers.
Suite 4023/12/known-flake; gates 28/28.

KARL REVIEW ITEMS: (1) sts2-v2.0.0-preview tag (M7 evidence:
sqltoolsservice artifacts/verify-latest.md at 328b47b6 + verification-
report entries); (2) SPEC-CHANGE-0001 (maxCellBytes wire shape);
(3) grid-convergence-decision.md ratification; (4) MV ledger dogfood
pass (MV-1..12 incl. new MV-10 plan viewer + MV-11 OE v2 no-v1 smoke).

## 2026-07-10 — Entry 14: dogfood fixes — F5 restart + SPID + grid/pinned polish

SHIPPED — vscode-mssql qs: 85710f0a7 (grid header labels user-select:
none; @@SPID rides the per-run @@TRANCOUNT probe → status bar corrects
itself on the next execution after a KILL — DBA-referable SPID, zero
extra round trips) + c2d: 5f15664ea (pinned results → WebviewPanel; the
custom-editor breadcrumbs row that echoed the tab title is gone; tabs
close on reload instead of expired husks; contribution absence pinned by
test) + qs: 205bbb98f (F5 restart: mid-run execute cancels + QUEUES the
request, latest wins; queued run starts at the canceled run's terminal
BEFORE the post-run probe; orchestrator waits out briefly-busy sessions
— 'one active query per STS2 session' can no longer reach the user from
held F5). +3 restart tests. Suite 4488/12/known trio; dist rebundled.

## 2026-07-10 — Entry 15: QS bootstrap perf (BOOT-1/2 SHIPPED; BOOT-3/4 in flight)

Karl P0: open-window scenario, zero waste, full visibility, tests that
fail on new critical-path deps; spatial/vector tabs (query-result-tabs)
must be 0-cost unless used. Plan: QS_BOOTSTRAP_PERF_PLAN.md.

MEASURED: init closure was 14.3MB code/78MB fetched (dev inline maps) —
monaco 7.2MB legit + azdataGraph 2.0MB AT INIT (waste) + slickgrid stack
1.6MB + shell. querystudio-open gates: 110ms warm / 1963-4800ms cold.

SHIPPED: perftest core 22e1988-successor (boot vocabulary; see git) +
vscode-mssql core 1754c32f4 (vendored) + qs ced94e2c5 (staged loading:
grid dynamic + idle prefetch post-editorInteractive, plan chunk on-use
only, resultsGridShared light module, CSS hoisted; dev maps
inline→linked = entry fetch 10.2→2.3MB; boot marks scriptStart/
reactMount/monacoReady/editorInteractive/gridChunk*/planChunkLoaded +
open.toEditorInteractive/toResultsRendered metrics; per-bundle metafiles
+ dist/views/preload-manifest.json + modulepreload injection in the
shared webview HTML — all entries benefit). Init closure now 10.4MB.

REMAINING (BOOT-3/4): queryStudioBundleBudget.test.ts (metafile static-
closure DENYLIST azdataGraph/@slickgrid-universal/slickgrid-react/
sortablejs/multiple-select-vanilla/vanilla-calendar-pro + forward names
maplibre/leaflet/deck.gl/plotly/chart.js/echarts/three/cesium/@arcgis/d3;
code-byte ceiling ~11.5MB; chunk-count ceiling) + perftest scenario
querystudio-open-autorun (newQueryFromContext initialSql SELECT 100
autoRun → resultsRendered; metrics open.toEditorInteractive/
toResultsRendered) + full-suite/webview verify + before/after harness
runs + boot.autoRunStart deliberately NOT emitted (query.submit covers
run start; registered for future). autoRun arg name check on
newQueryFromContext before scenario.

## 2026-07-10 — Entry 16: BOOT-3/4 COMPLETE — bootstrap workstream shipped

SHIPPED — vscode-mssql qs: (budget guard commit + honesty commit),
perftest da84f92 (+driver serverScoped type fix):
- queryStudioBundleBudget.test.ts: init-closure DENYLIST (azdataGraph,
  slickgrid stack, forward heavy-tab libs maplibre/leaflet/deck.gl/
  plotly/chart.js/echarts/three/cesium/@arcgis/d3) fails BY NAME;
  11.5MB code ceiling; chunk-count ceiling; preload-manifest presence;
  metafile REQUIRED (guard cannot pass by absence).
- querystudio-open-autorun scenario in the gates: newQueryFromContext
  (SELECT 100, autoRun) → resultsRendered; success REQUIRES
  boot.editorInteractive + boot.gridChunkLoaded (staged-loading contract
  live-proven every run).
- Honesty found+fixed BY the first run: resultsRendered fired on the
  Suspense placeholder (120ms early) → now gated on whenGridStackLoaded;
  perfMarkAfterNextPaint 500ms fallback for rAF-throttled hidden
  webviews (rafThrottled attr) — warmup reps had lost editorInteractive.

LIVE (run d796deba, 8/8): open warm 87-88ms (cold outlier 5.3s = window
spawn variance, known); open+SQL+autorun→REAL grid 876-990ms incl.
~325ms session connect. Phase table (rep-01): open.begin 0 →
scriptStart 325 → monacoReady 472 → editorInteractive 497 →
gridChunkRequested 547 → gridChunkLoaded 743 → resultsRendered 776.
Suite 4491/12/known trio.

RESIDUALS: derived open.toEditorInteractive/toResultsRendered metrics
registered but the CLI did not surface them per-rep (phase table comes
from markers.jsonl meanwhile) — wire the CLI derivation next harness
pass; entry CSS split (1.5MB) + Monaco feature trim = follow-up spikes;
spatial/vector tabs MUST use the lazyResults P2 pattern (plan §P2 +
denylist enforces).

## 2026-07-10 — Entry 17: grid-row regression fixed + production-safety feature STARTED

REGRESSION (Karl, screens/grid-row-size.png): BOOT-2 css hoist left the
slickgrid THEME css entering the entry stylesheet AFTER our
FluentResultGrid overrides (position 102 vs 99-101) — lib theme stomped
row metrics → clipped rows. FIX (qs commit "slickgrid theme cascade
order"): theme statically hoisted FIRST; cascade = theme → base →
vscode overrides → table.css, verified in emitted css input order for
queryStudio AND queryResultsSnapshot. Budget denylist refined to scan
JS inputs only (it correctly flagged the css-only theme hoist — guard
proven on its own author). NOTE fix knowledge: dev css also went
inline→linked maps (1.5MB→483KB + .css.map) — css SIZE deltas are maps,
check content via metafile inputs.

NEXT — production safety (Karl directive, recon done, NOT implemented):
1. Settings (both default false): mssql.queryStudio.statusBarGroupColor
   (statusbar takes server-group color) + mssql.queryStudio.
   warnWhenModifyingProduction. Group JSON gains OPTIONAL
   "production": true (settings-JSON only, no UI, v1 code ignores —
   read structurally, do NOT edit IConnectionGroup).
2. Binding resolves group facts at open() via its ConnectionStore param
   (groupId → {color, production}); QsConnectionState already HAS
   accentColor field (line ~101 sharedInterfaces/queryStudio.ts) —
   populate it + add production flag; controller computes textColor
   extension-side via new sharedInterfaces/colorContrast.ts (WCAG
   luminance → #ffffff/#1e1e1e). Webview app styles .qs-statusbar
   background+color when accent present. Production w/o color →
   default #B71C1C. Color shows if statusBarGroupColor OR
   (production && warn setting).
3. Guard: new src/sql/sqlSafetyClassifier.ts isModifyingSql (strip
   comments/strings/brackets; word-boundary INSERT|UPDATE|DELETE|MERGE|
   DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|DENY|EXEC|EXECUTE|BACKUP|
   RESTORE|KILL|BULK|DBCC|INTO). ExecutionHost gains injected
   productionGuard {shouldConfirm(text), confirm(): yes|yesSession|no,
   suppressForSession} — vscode-free host; model
   (queryStudioDocumentModel:92 constructs host) wires modal
   showWarningMessage {modal} buttons Run Query / Run and Don't Ask
   Again This Session; suppression per binding session, reset on
   reconnect. execute() when guard fires → async confirm → re-execute
   via one-shot allow; return {started:false, reason:"Awaiting
   production confirmation…"}.
4. OE v2 group folder color bug (screens/colors.png): v2 provider
   renders ThemeIcon(folder) always — replicate classic tinted-SVG
   data-URI (connectionGroupNode.ts getIcon pattern; classic import
   BANNED in v2 — copy the ~15-line svg fn into objectExplorerV2Provider
   using node.color).
5. Tests: classifier matrix, contrast, host guard (fake confirm),
   + suite/bundles/dist rebundle.

## 2026-07-10 — Entry 18: production safety SHIPPED (qs 3b50add81)

Full Entry-17 spec implemented end to end: colorContrast + sqlSafety
Classifier pure modules (+11 tests), binding resolves group facts
(structural "production": true via store seam — classic untouched),
QsConnectionState carries accentColor/accentTextColor/production,
ExecutionHost injected guard (vscode-free) pauses modifying SQL on
production connections, model owns the modal (Run Query / Run and Don't
Ask Again This Session; suppression keyed to session object — reconnect
re-arms), webview statusbar takes the accent w/ inherit-!important child
rule, two default-false settings, OE v2 tinted group folder icon
(colors.png fix). Accent matrix: color shows when statusBarGroupColor OR
(production && warn); production w/o group color → #B71C1C. Guard
composes with F5-restart queueing (queued reruns re-enter the gate).
Suite 4502/12/known trio; webview+extension bundles rebuilt (dogfood
current). Later (Karl): fancy color selection (regex/groups) — v1 is
group-color only.

## 2026-07-10 — Entry 19: grid focus-follows-click fix (dogfood)

Single cell click left focus in Monaco (ctrl-a/ctrl-c/arrows hit the
editor) while drag-select worked: the CellRangeSelector's mousedown
preventDefault suppresses the browser's default focus transfer; drags
focused via the selection model. FIX: fluentResultGridCommandController
handleClick calls grid.focus() (slick sink) for every cell click, hoisted
above the modifier-click early return (focus doesn't touch the selection
anchor). No unit harness exists for webview DOM focus — verify by
dogfood: click cell → arrows move active cell, ctrl-c copies cell,
ctrl-a selects grid; click editor → keys return to editor. Webview
bundle rebuilt.

## 2026-07-10 — Entry 20: status-bar accent text readable (dogfood fix)

Root cause was OUR css: 'color: inherit !important' on the accent
container beat the inline computed color (stylesheet !important >
inline), re-inheriting the theme's dark foreground → dark-on-dark-red.
Fixed with --qs-accent-bg/fg CSS variables set inline + !important
consumers (cannot self-clobber); muted dimming dropped under accents.
Text pick upgraded to curated candidates scored by WCAG contrast ratio
(#1f1f1f when AA on light, white when AA on dark, strongest pure
black/white on mid-tones); rgb()/rgba() parsing added. FIX KNOWLEDGE:
never put '!important inherit' on the element that carries the inline
style it is meant to protect. Suite green; webview bundle rebuilt.

## 2026-07-10 — Entry 21: PRODUCTION warning label + Azure SQL DB database semantics

Three dogfood asks (Karl):
- Status bar now leads with a bold "WARNING: PRODUCTION" span (first
  element, far left) whenever the connected group carries the production
  flag (app.tsx + .qs-status-prod-warning css). Rides the same accent
  facts as the color, so it needs no new state.
- Azure SQL DB database SWITCH: USE does not work there (engine edition
  5). The controller's QsSetDatabase now routes through
  binding.switchDatabaseByReconnect() — close session, release metadata
  lease, reopen with the new database — the exact STS v1
  ChangeConnectionDatabaseContext IsCloud semantic (close + rebuild).
  Non-Azure keeps the in-session USE.
- Azure SQL DB database LIST: sys.databases from a user database lists
  only master + itself. executionHost.listDatabases() is now
  master-first (STS v1 ListDatabaseRequestHandler parity):
  binding.listDatabasesViaMaster() opens a transient master-scoped
  session (applicationName vscode-mssql-querystudio-dblist, 15s cache,
  closed in finally) and runs the same catalog query; no master access
  (Azure 18456/40532 case) → undefined → fall back to the current
  session's list, so the selector is never emptier than before.

Tests: queryStudioAzureDatabase.test.ts (4) — master list wins with no
current-session query, undefined/empty/rejecting master probe all fall
back. Suite green modulo the known trio. tsgo both configs, eslint 0
errors, both bundles rebuilt (dogfood runs dist/).

## 2026-07-11 — Entry 22: SQLCMD mode + scan-and-detect framework (SC-1..SC-5)

Design + plan: SQLCMD_MODE_PLAN.md (research digest: STS ManagedBatchParser
is the SQLCMD implementation — six functional commands, everything else
recognized-then-rejected; v1 sends options.isSqlCmdMode via
query/setexecutionoptions and lets STS parse; QS splits batches client-side
so SQLCMD is a client-side preprocessor here).

SHIPPED (perftest core: 87446c6 + scenario commit):
- Registry: sqlcmd.toggle / sqlcmd.run / scan.run markers (counts + safe
  enums only). Contracts 27/27; re-vendored.
- Scenario querystudio-sqlcmd-run (setvar/$(var)/GO 2, sqlcmd open-context
  seam, autorun; success requires the sqlcmd.run marker) + 
  examples/config.sqlcmd.local.jsonc.

SHIPPED (vscode-mssql qs: — SC-2 2e5506337-successor train):
- src/sql/sqlcmdPreprocessor.ts: pure STS-parity preprocessor —
  :setvar/$(var) (env fallback, undefined FATAL, case-insensitive,
  substitution everywhere incl. strings: sqlcmd quirk), :r include seam
  (resolved-path circularity, depth 16), :on error exit|ignore, :connect
  (-U/-P quoted args), rejected-command set errors honestly, directives
  never recognized inside strings/comments (scanLine reuse). String-kind
  discriminant ("script"/"parseError") — REPO KNOWLEDGE: strict:false
  kills truthiness narrowing on boolean-literal discriminants; use string
  kinds + === (tsc AND tsgo agree).
- executionOrchestrator: buildWorkPlan compiles text → work items (batch
  steps GO-split, startLine shifted to document coords so Started-at and
  Msg-line mapping stay correct); :on error flips run-local stopOnError;
  :connect swaps currentSession run-scoped (transients closed in finally,
  binding session restored before mode-wrapper OFF); parse error = one
  honest message, status failed, ZERO executes. sqlcmd OFF byte-identical.
- Toggle: QsSetSqlcmdModeRequest + toggles.sqlcmd; toolbar SQLCMD text
  button (SSMS parity); status bar shows SQLCMD badge ONLY when on. Mode
  owned by ExecutionHost (per-document, v1 per-ownerUri parity).
- :connect sessions: binding.openSqlcmdConnectSession — synthesized
  profile, SQL auth iff -U/-P (password only in the auth closure),
  encrypt/trust inherited from the document's profile.
- Scan-and-detect framework (scanDetect.ts, pure): per-rule SamplingPolicy
  (headLines default / fullText+maxChars), samples shared per policy,
  throwing rules isolated. Controller schedules ONE scan per document
  1.5s after webview ready (mssql.queryStudio.scan.enabled). Rules
  (scanDetectRules.ts): sqlcmd (directive heads, string/comment-aware,
  :: casts and :unknown are NOT signals) → 3-option prompt Enable /
  Don't Enable / Don't show again auto-enable
  (mssql.queryStudio.scan.autoEnableSqlcmd) or silent auto; psql
  (backslash meta-commands / 2 strong syntax signals) → per-document
  native diagnostics suppression (new suppressDocumentDiagnostics seam).
- Tests: sqlcmdPreprocessor (21), orchestrator SQLCMD (6), scanDetect
  (11). Suite 4548 passing; failures = known set.

Perftest gate: querystudio-sqlcmd-run run recorded in this entry's
follow-up (run id in summary.json); rebundled dist before gating.

## 2026-07-11 — Entry 23: Azure DB switch root-caused + fixed (dogfood)

Karl: selector still not switching on Azure SQL DB. Session journal
(sess_20260711091353, seq 201-206) showed qs/setDatabase completing "ok"
in ~60ms with an inner sqlDataPlane.execute ERROR — the classic USE path
ran, meaning isAzureSqlDb was false. ROOT CAUSE: STS2's SqlClient driver
fills serverInfo.engineEdition from serverproperty('Edition') — the
DISPLAY NAME ("SQL Azure") — so Number(...)===5 was NaN, forever false.
(OE v2 already knew: its serverScopeFacts sniffs /azure/i on the name.)

Fixes:
- sqltoolsservice sts2 (D-0017, additive optional wire field + SPEC §7.4
  text): driver open probe also selects serverproperty('EngineEdition')
  numeric → ServerInfo.EngineEditionId → serverInfo.engineEditionId.
  PublicAPI.Unshipped updated; Core untouched (opaque passthrough).
- vscode: isAzureSqlDb = engineEditionId===5 when present (exact — MI=8
  keeps USE), else name sniff /azure/i (older services; MI then takes
  reconnect, which works). connectionState prefers the numeric id.
- Honesty: qs/setDatabase now returns {changed, reason}; webview surfaces
  failures via actionHint (same rule as refused runs — a selector pick
  never no-ops silently). New journal event queryStudio.dbSwitch
  {method: use|reconnect, changed, engineEditionKnown, ms}.
- Tests: 4 detection cases incl. the NaN repro and MI-vs-SQLDB. 4552
  passing. STS ServiceLayer + sts2 rebuilt (dogfood bin refreshed).
