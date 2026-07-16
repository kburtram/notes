# Query Studio Result-Tab Panes — Progress Journal

This journal is authoritative for **current checkpoint status and recorded evidence only**. It does not override feature scope, safety rules, or exit criteria in `EXECUTION_PLAN.md` and its authority chain. A scope change requires an explicit dated decision; a historical entry cannot silently waive unfinished acceptance work. Reconciliation entries are appended at the bottom and supersede older status claims. Each checkpoint entry records: what landed (files/commits), validation evidence (build/test/perf/live), deviations from plan, and anything the next session must know.

## Status board

`DONE` means the entire checkpoint in `EXECUTION_PLAN.md` has exit evidence. `PARTIAL` means a committed, tested slice exists but required behavior remains. `READY` means the plan is complete and implementation is authorized but the checkpoint has not started. `IN PROGRESS` is not validation evidence and may include uncommitted work.

| Checkpoint | Status | Landed evidence | Remaining before `DONE` |
|---|---|---|---|
| Understand + plan | DONE | Docs and reader briefs; `coding-docs` is not a Git repository | — |
| VEC-0 STS capture privacy | DONE | sqltoolsservice `d20d8d7c` | — |
| VEC-1 STS2 vector transport | DONE | sqltoolsservice `5a6ab3cc` | — |
| VEC-2 Ext codec + metadata + negotiation | DONE | vscode-mssql `3f15907f4` | — |
| VEC-3 Sparse projection + read discipline | DONE | vscode-mssql `7466a481f` | — |
| VEC-4 Analysis service + worker + RPC | PARTIAL | vscode-mssql `52941530d`, `a514d6c2a`, `2dae20aa0`, `67eb22d7c`; perftest `0c64a3e`, `d72d1d4` | Freshness/provenance/group finding producers; progress protocol/UX; complete lifecycle/privacy evidence |
| VEC-5 Webview shell + Profile | PARTIAL | vscode-mssql `fb8708257`, `3d505a330`, `59b29ec0e`, `82eaa6207`, `67eb22d7c` | Group comparison; capability/binding popovers; grid entry points; complete taxonomy, localization, and full accessibility validation |
| VEC-6 Compare + Projection | PARTIAL | vscode-mssql `19ac1053b`, `67eb22d7c` | Arithmetic-lab/use-as-query-vector and nearest-bound-row flows; group color, lasso, inspector/reveal, and grid seeding |
| VEC-7 Binding + probes + aux sessions | PARTIAL | vscode-mssql `e59122504`, `67eb22d7c` | Shared verified binding object/wizard, persistence/reverification, capability ladder/popover, and badge states |
| VEC-8 Search | PARTIAL | vscode-mssql `bd28c69f4`, `67eb22d7c`; perftest `d72d1d4` | Shared read snapshot/evidence digests; full model reproducibility/permission facts; lineage-backed source exclusion; advanced filters/plan/forced/repeat/K-sweep/query-set evidence |
| VEC-9 Index | PARTIAL | vscode-mssql `f9117064a`, `67eb22d7c` | Shared binding wizard/persistence; full engine/version/permission matrix and pinned/live end-to-end validation |
| VEC-10 Pipeline | PARTIAL | vscode-mssql `1afcb42bc`, `abd1eb028`, `67eb22d7c`; perftest `84ce1ec` | Verified-key full-source fetch, drift workflow, batch embedding, persisted provenance, and full permission/retry matrix |
| VEC-11 Pinned parity + lifecycle | PARTIAL | vscode-mssql `fb32eaba5`, `83b6276dd`, `67eb22d7c` | Pinned Compare/Projection handler parity; Reveal-in-Results; complete rerun/hide/dispose/expiry matrix |
| VEC-12 Perf validation + matrix | PARTIAL | perftest `46bcf39`, `84ce1ec`, `d72d1d4`, `ec21555`; vscode-mssql `59b29ec0e`, `82eaa6207`, `67eb22d7c` | `VTEST-01..VTEST-22`; edge/privacy/a11y/localization sweeps; all-family session-diag proof; baselines and release docs |
| SPA-0..SPA-8 (spatial implementation) | DONE | vscode-mssql `720fd3fe5`..`b06cc650f`; sqltoolsservice `f1a6393b`; perftest `aa26fe8`..`2a77143`; Entry 18 | — |
| SPA-9 release evidence | PARTIAL | All affected builds/focused suites green; live unopened/10k/100k diagnostic runs green; privacy/localization/packaging/notices covered | Promote exploratory metrics only after multi-run/multi-machine stability; complete final manual visual/theme/keyboard screen-reader sweep and named official baseline |
| SPA-10 external cartographic services | NOT STARTED | Explicitly outside the approved offline-first scope | Requires separate product/privacy/legal approval |

## Entries

### 2026-07-11 — Entry 1: Understand phase complete; plan written

- 11 parallel reader briefs in `_build/briefs/` (r01–r11) covering all specs/addenda/mockups/QS architecture/STS2 datapath/observability/perf-build. All mockup PNGs reviewed directly.
- Baseline: all three repos on `dev/query`, clean; extensions/mssql `npm run build` green (ext 1.3s / webviews 4.0s); QS boot baseline run d796deba (r11) is the do-not-regress reference.
- Empirically verified (r09, live SQL 2025 17.0.1000.7 + M.D.S 6.1.5, STS2 read pattern): vector → useless `{$t:"provider"}` cell; geometry/geography → whole-query failure (FileNotFoundException). Classify fix + opt-in typed contracts required as planned.
- Key hazards logged: `{$t,v}` wrapper collision (use `data`/`wkb` fields); CaptureElision compact leak (VEC-0); no CSP on webviews today; QS markers are trace-orphans (pass traceId explicitly); type-hint taxonomy must change in lockstep both sides; conformance regex misses bare `perfMark(` — register names regardless; `last:false` hardcoded on wire (completion = v2/query.complete only); ack by per-query cumulative pageSeq (D-0015).
- Next: VEC-0.

### 2026-07-11 — Entry 2: Adversarial plan review applied; VEC-0 implemented, gate running

- Adversarial reviewer (vs briefs + repos) returned 11 findings. #1 ("compact elision fix already exists") was a FALSE POSITIVE — it read the working tree containing our own uncommitted VEC-0 edit and attributed it to commit 70b66034 (that commit only touched the file last; its version wrapped `rows`/`sql` only, verified by reading it pre-edit + `git status` showing our M flags). Findings #2–#11 applied to EXECUTION_PLAN.md:
  - VEC-1: + evidence-only provider/RID matrix (`_build/evidence/vector-provider-matrix.md`, Windows-local honest scope) + durable typeprobe copy.
  - VEC-4: + evidence contracts (P0-1 `VectorEvidenceSource`/`VectorEvidenceRecord`) and subjects (P0-2) BEFORE Profile UI; + freshness/provenance findings P1-3/P1-4; + VectorLab corpus fixtures move here (before finding logic); + `mssql.queryStudio.boot.vectorChunkRequested/Loaded` in registered vocabulary; + perf-mode tab-activation seam for VEC-12 scenarios.
  - VEC-6: C-01 server-side demo steps deferred to VEC-8.
  - VEC-7: + `api_format`/egress classification in the capability probe (DA A4).
  - Budgets: + disclosed scan-bytes budget (DA A6).
  - Spatial: codec-first reorder (SPA-0 = codec/consumer safety before any negotiation); `ol` added to DENYLIST at SPA-4.
- VEC-0 code complete: `CaptureElision` wraps `compact` node (kind "compact", digest wrapper, row-count parity); canary test `DigestModeElidesCompactPagesFromJournal` (wire real / journal wrapper-only / replay digest-identical). `./verify.sh --quick` running.

### 2026-07-11 — Entry 3: VEC-0 DONE

- verify.sh --quick green (all 11 gates ok, incl. replay verify, 200-seed simulator, secret canary). Committed sqltoolsservice `d20d8d7c` with verification-report entry. Working tree clean.
- Risk noted in report: digest-mode journals lose per-page typeHints visibility (whole compact node elided) — safe direction, stats field untouched.
- Next: VEC-1 (typed vector transport + UDT crash fix + additive column metadata + page clamp/frame guard + provider evidence matrix).

### 2026-07-11 — Entry 4: VEC-1 implemented; verify gate running

- D-0018 (classify fix): `SqlLargeValueReader.ClassifyColumns` routes `vector`→streamed Text (JSON, full precision), UDT suffix `*.sys.geometry|geography|hierarchyid` + bare names→streamed Binary (CLR bytes; was whole-query FileNotFoundException). `SerializeColumns` ships precision/scale/length/collation when known (vector length = 8+4*dims). Runner measures encoded pages in UTF-8 bytes (was UTF-16 chars) + last-line typed frame guard (`Sts2.QueryFailed.Transport`, MaxFrameBytes−1MiB).
- D-0019 (typed contract): capability `vectorBinaryV1`; option `vectorEncoding:"binary-v1"` (literal only) normalized to `vectorBinary` in journaled startArgs (compactRows pattern); `QueryExecuteRequest.VectorBinary`; `SqlClientVectorValueReader` (SqlVector<float> → explicit-LE `DriverVectorValue`, sentinels `unsupportedBaseType|providerValueMismatch|decodeFailed|cellLimit`, string passthrough for text fallback); encoder emits `{$t:"vector",...,data}` (never `v`), never truncates vectors; typeHints `vector:f32le:v1` only when negotiated; `SqlRowsPageBuilder.EstimateCellBytes` learns vector (~8.3KB/1536-dim) + truncated values. PublicAPI entries added; SPEC §7.3/§7.5/§7.7 updated; DECISIONS D-0018/D-0019.
- Tests: encoder vector cases (data-not-v, never-truncated, sentinel facts); ClassifyColumns matrix; page-estimate + byte-bound clamp tests; QueryFlow negotiation e2e on FakeDriver (opt-in reaches driver; typed cell on wire; wrong literal stays off); LIVE engine tests green against SQL 2025 (vector text/typed/nulls 44ms; geometry/geography/hierarchyid binary 250ms). FakeQueryStep.CellValue widened string→object.
- Evidence matrix at `_build/evidence/vector-provider-matrix.md` (win-x64 verified; linux/osx/Azure honestly UNVERIFIED, CI follow-ups); typeprobe copied durably to `_build/typeprobe/`.
- Client-side lockstep note: server emits `vector:f32le:v1` hints ONLY for opted-in queries; no client opts in yet, so vscode-mssql `typeHintFor` parity changes belong to VEC-2 behind the same negotiation.
- verify.sh --quick running; commit after green (single VEC-1 commit: transport is one coherent contract).

### 2026-07-11 — Entry 5: VEC-1 DONE

- verify.sh --quick green (11/11 gates incl. replay, 200-seed simulator, secret canary, legacy diff budget). Committed sqltoolsservice `5a6ab3cc` (18 files, +748/−24) with verification-report entry. Tree clean.
- Live-verified on SQL 2025: vector byte-exact both modes + NULLs (44ms); geometry/geography/hierarchyid transport as SRID-tagged CLR bytes instead of failing the query (250ms).
- Next: VEC-2 in vscode-mssql — queryResultCellCodec.ts (CellTextPurpose, strict vector guards, decode API), consumer adoption (grid/copy/text/cellDoc/CSV/JSON/INSERT/transforms/tools/pins), QsResultColumn vector metadata (dims from length), gate `mssql.queryStudio.vectorWorkbench.enabled`, sts2Backend negotiation + typeHintFor lockstep (`vector:f32le:v1`), scalar sort disabled on vector cells, consumer-matrix tests.

### 2026-07-11 — Entry 6: VEC-2 core contracts landed (typechecks green); consumers + tests delegated

- New `sharedInterfaces/queryResultCellCodec.ts`: strict structural guards (shape AND arithmetic — byteLength === dims*4, base64 length exact, dims ≤ 1998), pure base64/LE-float32 decode (DataView LE, platform-independent), `formatFloat32Shortest` (toPrecision 1..9 + fround round-trip = engine JSON parity), `vectorCellText` per `CellTextPurpose`, `typedCellTextForPurpose` chokepoint (spatial extends here later), `vectorDimensionsFromColumnLength`.
- gridOps: `cellDisplayText` bounded vector preview (`[…] · 1536D float32`); `cellTextForPurpose` export; sort no-op on `vector:f32le:v1` hint; vector cells open as JSON documents.
- **Found + fixed two pre-existing client bugs**: (1) `wireColumnType` read `engineType` but the service serializes `type` — sqlType was silently undefined for EVERY column on the live STS2 path (the appliesTo sniff would never have fired); (2) client `typeHintFor` hinted timestamp/rowversion as "datetime" vs server "binary" (JS if-order vs C# constant-pattern precedence) — client now matches the server taxonomy.
- Negotiation: `SqlBackendCapabilities.vectorBinaryV1` + initialize parse + `vectorBinaryNegotiated`; per-query `options.vectorEncoding="binary-v1"` only when caller opted AND negotiated; `vectorBinaryActive` drives typeHints + column `vector {transport, dimensions}` facts (dims from wire length; precision/scale/maxLength now populated). QsResultColumn mirrors `vector` (orchestrator passthrough). Gate `mssql.queryStudio.vectorWorkbench.enabled` (package.json, application scope) → documentModel seam → executionHost per-run thunk → RunOptions.vectorEncoding → ExecuteOptions.
- Both tsgo typechecks green (extension + webviews); fakeBackend capability updated.
- Delegated in parallel: consumer adoption (cellDocument/exports/copy/textView/tools/pins) and unit tests (codec matrix, gridOps, sts2Backend conformance incl. negotiation + metadata + taxonomy-fix assertions).

### 2026-07-11 — Entry 7: VEC-2 DONE (vscode-mssql 3f15907f4)

- Consumer agent adopted all chokepoints: cellDocument ("cellDocument"), resultExport CSV/JSON/INSERT (INSERT emits `CAST('[…]' AS VECTOR(n))`, raw-not-requoted), grid copy via `windowToGridRows(clamp=false)` ("copy" full fidelity; rendered windows stay bounded preview), resultsTextView ("textView"), queryResultsTool `boundCell` funnel + queryParticipant `/profile`/`/report` (`toolSummary`). Pinned snapshots inherit (no own formatter); legacy runQueryTool rides classic wire (D-0018 text) by design.
- Test agent: 132 targeted tests green (38 codec matrix incl. fround round-trip property + denormal/NaN/±0; gridOps vector display/sort-gate/doc-language; sts2Backend negotiation both-ways + column facts + `type` fallback + taxonomy pin; orchestrator passthrough). Runner: `npx vscode-test --label "Unit Tests" --run out/test/unit/<file>.js` after tsc emit.
- Post-agent refinements: decodeVectorPrefix(cell,0) → [] (was null); unavailable+insertExport → NULL (valid SQL); cellDocumentLanguage only for OK cells (sentinels have no document).
- Full unit suite: green minus 3 failures VERIFIED pre-existing via git stash + rerun on clean tree (sqlLanguageCompletion ×1 deterministic, copilotChatEntry ×2 hook-timeout flakes; matches QO-5 report's "3 pre-existing").
- Next: VEC-3 — sparse projection (`columnOrdinals` on CellWindowRequest/RowStreamRequest through RowStore/retained/spill, one spill materialization per request), RowReadReason `vectorAnalysis` (non-admitting), lease owner `vectorWorkbench`, cache-behavior tests. Key files: queryStudio/rowStore.ts, queryResults/resultStoreLease.ts, queryResults/queryResultTypes.ts, sharedInterfaces/queryStudio.ts (QsGetRowsParams already has columnStart/columnCount — sparse ordinals is the new bit).

### 2026-07-11 — Entry 8: VEC-3 DONE (vscode-mssql 7466a481f)

- rowStore.getRows: `{ordinals}` variant (caller order, invalid dropped, null bits track projection, one materialize per page, hoisted ordinal expansion, sparse-aware window-cache key + begin-marker attrs); reason `vectorAnalysis` non-admitting (positive admit list untouched); CellWindowRequest/RowStreamRequest `columnOrdinals` (wins over span), RetainedRowStore forwards per chunk; lease owner kind `vectorWorkbench`.
- Tests (3 new, all green): sparse matrix incl. [2,0] order + [99,1,-1] filtering; admission both-ways via stats.memoryBytes over spilled scan (vectorAnalysis flat, grid grows); lease+streamRows forwarding e2e.
- Next: VEC-4 — `queryResults/vector/` host service: VectorResultSource packed ingest (Float32Array via codec decode over sparse vectorAnalysis stream), budget registry in QueryTuning, vectorAnalysisWorker (worker_threads; norms L2/L1/L∞, per-dim variance, SHA-256 dup groups, sampled pair distances, freshness/provenance findings P1-3/P1-4, deterministic seeds), evidence contracts P0-1/P0-2 FIRST (VectorEvidenceSource/Record, VectorFindingSubject), opaque pull RPC `qs/vector.*`, cancellation + lease lifecycle, marker vocabulary registration in perftest observability-contracts (incl. `mssql.queryStudio.boot.vectorChunkRequested/Loaded` + perf-mode tab-activation seam) + vendored regen, VectorLab corpus fixtures to `_build/sql/`, worker tests + budget/cancel tests + value-free log assertions.

### 2026-07-11 — Entry 9: VEC-4 part 1 committed (budgets + contracts); corpus agent in flight

- QueryTuning: vector budget group appended at spec tail (vectorScanRowLimit 25k, vectorSampleRows 5k, vectorComponentBudget 8M, vectorPackedInputBytes 64MiB, vectorScanByteBudget 128MiB A6, vectorRpcSoft/Hard/Session 1/2/32MiB, vectorAnalysisTimeMsBudget 30s, vectorMaxWorkers 2, vectorProgressMaxPerSecond 4); lowMemory profile lowers packed/scan; 12/12 tuning tests green (digest evolves — sanctioned append path).
- New `sharedInterfaces/vectorWorkbench.ts`: VectorEvidenceSource/Record (P0-1), VectorSampleDescriptor w/ budget echo + VectorPartialReason (A6), VectorFindingSubject/Kind/Severity/Summary/Detail incl. staleSourceText + provenanceMismatch (P0-2, P1-3/4), VectorHistogram/NormsSummary/ProfileSummary (P0-8), VECTOR_RPC methods + open/profile/findingDetail/cancel/close params/results (opaque handle + generation).
- Background agent extracting VectorLab corpus from test guide → `_build/sql/` with LIVE ground-truth verification on SQL 2025.
- **Corpus DONE**: `_build/sql/{vectorlab_setup,vectorlab_probe,vectorlab_groundtruth}.sql` + README — guide SQL byte-identical + idempotent header; ALL 18 ground-truth checks PASS live (nulls 12, zero 4, near-zero 8, high-norm 17, dup 12/37 planted — naive full-scan census 14/49 incl. zero/near-zero classes, both confirmed; stale 50, provenance 50, same-text-diff-vector 20, boilerplate 100; 4988 non-null 64-D). Rerun clean.
- **Catalog discrepancies found live (RTM 17.0.1000.7) — VEC-7/VEC-9 must probe, never template**: `sys.vector_indexes` has `distance_metric`+`vector_index_type`, NOT `distance_metric_desc` (guide's query fails Msg 207); `sys.dm_db_vector_indexes` ABSENT (health = "current snapshot only" state); `ALLOW_STALE_VECTOR_INDEX` absent from database_scoped_configurations (only PREVIEW_FEATURES=0).

### 2026-07-11 — Entry 10: VEC-4 DONE (pt 3: service + handlers + markers + tests)

- VectorWorkbenchService (sessions/handles/generations/leases/worker gate/idle expiry/honest refusals; drill-in ordinal mapping across nulls proven); controller handlers for qs/vector.* (lazy service creation — unopened cost zero; run-tuning budgets); RequestType wrappers on contracts.
- Markers: 8 registry entries in perftest observability-contracts (`core: 0c64a3e`) — vector ingest/analysis.begin/end/cancel, boot.vectorChunkRequested/Loaded (gridChunk-classification copy), render.begin/firstPaint (reserved for VEC-5, paired begin/end); contract vendored; conformance 4/4 + vendorSync green. Note: partialTime classified safeEnum (boolean convention); firstPaint carries phase "end" per pairing-symmetry rule.
- Honesty fixes from tests: sample `method` describes the SCAN plan (full stays full under null-reduced yield); scan-row budget bounds the PLAN (no mid-flight abort). 11 new tests; affected suites 88 passing.
- **NOTE for VEC-12**: perf-mode tab-activation seam (mssql.perf.queryStudioActivateTab-style) NOT yet added — do it with VEC-5's tab so the seam drives the real activation path.
- Next: VEC-5 — webview shell + lazy Vector tab + Profile workspace: extend QueryStudioTab union + appliesTo sniff (QsResultColumn.vector on summaries), lazyResults P2 pattern (thunk + React.lazy + boot.vectorChunkRequested/Loaded marks + Suspense honesty), per-surface CSP for QS + pins, six-workspace shell (rail/facts strip/status bar/state taxonomy per r01 house rules + r06 mock recipes), Profile view (norms histograms L2/L1/L∞ + variance rows + findings list + affected-rows drawer + pair distances + group comparison LATER when grouping lands — v1 renders what VectorProfileSummary carries), render.begin/firstPaint marks, bundle-budget green, demos P-01-adjacent against VectorLab.

### 2026-07-11 — Entry 12 (out of order, environment): two SQL test environments + Track B live on SQL25

- Karl added USER env vars: `STS2_SQLSERVER_CONNSTRING` (SQL25 RTM local; may create DBs) and `STS2_AZURESQLSERVER_CONNSTRING` (Azure SQL DB; schemas/tables only, no DBs). Model connections for embeddings coming (Track C). Memory saved (test-sql-environments).
- Track B self-served on SQL25 VectorLab: PREVIEW_FEATURES=ON; DiskANN index `IX_VectorLabSearchCorpus_Embedding` (cosine) CREATED — requires QUOTED_IDENTIFIER ON (sqlcmd -I).
- **Search-surface reality on RTM (evidence matrix updated — INVERTS the guide's assumption)**: `VECTOR_SEARCH` TVF w/ TOP_N WORKS; `TOP (n) WITH APPROXIMATE` REJECTED (Msg 102); `USE HINT('FORCE_ANN_ONLY')` REJECTED (Msg 10715) — forced-ANN proof unavailable on RTM → VEC-8 must probe per connection and use the "Approximate requested, strategy unverified" honesty state; `build_parameters` has NO $.Version key ({StartId,L,M,R} only).
- **Azure surface VERIFIED (agent complete)**: all 5 STS2 engine tests PASS live against Azure SQL DB (D-0018 text 277ms, D-0019 UDT 1s — transport contracts hold on EngineEdition 5); VectorLab rebuilt in `vectorlab` schema, 18/18 ground truth PASS (compat 150→170 raise must be its OWN batch for GENERATE_SERIES). Matrix updated with full diff table. Deltas that shape VEC-7/8/9: Azure HAS `sys.dm_db_vector_indexes` but column names differ from the guide (`graph_catchup_pending_percent` NOT `approximate_staleness_percent`; `last_background_task_execution_time`) — the mock's staleness fact must read probed column names; Azure HAS `ALLOW_STALE_VECTOR_INDEX` (0) + `Version:"3"` in build_parameters (no M) — version detection works ONLY on Azure; `external rest endpoint enabled`=1 by default on Azure; CREATE VECTOR INDEX DDL parses without preview but build FAILS on GP_S serverless tier (Msg 42234) leaving a transient PHANTOM row in sys.vector_indexes (not in sys.indexes, undroppable, self-cleans ~1min, blocks re-create) → Index workspace must gate on sys.vector_indexes ⨝ sys.dm_db_vector_indexes and treat index availability as per-database/tier; VECTOR_SEARCH parse is PREVIEW_FEATURES-gated on Azure; WITH APPROXIMATE + FORCE_ANN_ONLY rejected on BOTH environments. Azure PREVIEW_FEATURES restored to OFF; no residue.
- `_build/sql/vectorlab_model_setup.sql` prepared for Karl (placeholders; box SQL needs sysadmin `sp_configure 'external rest endpoint enabled', 1` once).

### 2026-07-11 — Entry 14: CONTINUOUS PIPELINE running (Karl: no pausing until vector is done)

- Committed `3d505a330` (VEC-5 pt 2): Profile norm toggles L2/L1/L∞ + tab-activation seam (`mssql.perf.queryStudioActivateTab` → model.requestActivateTab → controller `qs/activateTab` notification → app.tsx setActiveTab).
- **UNCOMMITTED in vscode-mssql working tree (mine, hold until wave-1 agents land, then commit per checkpoint)**: VEC-11 pinned parity — queryResultAccessService.storeForSnapshot (derived flag), pinnedResultsController vector RPC handlers (derived → honest refusal "Transformed snapshots cannot be analyzed"; lazy VectorWorkbenchService), QueryResultsSnapshot app.tsx lazy Vector tab (sniff over frozen summaries; runKey pinned:createdEpochMs). Both typechecks green WITH VEC-6 agent's concurrent contract edits.
- **AGENTS IN FLIGHT** (integration order when they land): (1) VEC-6 Compare+Projection — worker PCA (orthogonal iteration), qs/vector.projection + qs/vector.compare contracts+service, NEW vectorCompareView.tsx/vectorProjectionView.tsx (they do NOT edit vectorTab.tsx/app/controller — I wire mounts+handlers after); (2) VEC-7 probes+aux — documentSessionBinding.acquireAuxiliarySession, NEW vectorCatalogProbes.ts + vectorCapabilityService.ts + sharedInterfaces/vectorCatalog.ts, live tests both envs (I wire controller handler + model thunk after); (3) VEC-12 perftest scenarios — markerAbsent success check + command args + queries/vectorlab-chunks.sql + querystudio-vector-unopened-f32 + querystudio-vector-profile-f32 + config.vector.local.jsonc, LIVE runs (this IS the in-product demo pass); (4) VEC-8 foundation — NEW vectorSqlBuilder.ts (verified syntax matrix baked in: TVF TOP_N works, WITH APPROXIMATE/FORCE_ANN_ONLY rejected both envs → evidence "approxStrategyUnverified"; P0-6 structured exclusions, P0-7 read-consistency declaration, P0-10 frozen @q, A1 oversample disclosure) + tests + live recall smoke.
- **WAVE 2 after integration**: VEC-8 Search UI (rank grid + evidence panel + SQL drawer + rank-flow SVG per mock, using builder + aux sessions + probes), VEC-9 Index workspace (probe-driven state machine: healthy / no-index / permission-degraded / phantom-row-aware; generated-never-executed scripts), VEC-10 Pipeline (provenance via sys.external_models probe; re-embed via AI_GENERATE_EMBEDDINGS + VectorLabEmbeddingModel — VERIFIED LIVE both envs; host-minted confirmation + egress copy per API_FORMAT; chunk debugger AI_GENERATE_CHUNKS), VEC-11 commit, VEC-12 finish (baselines, full matrix incl. track E fixtures, unopened regression sweep vs d796deba, CHANGELOG). THEN STOP (spatial gated on Karl).

### 2026-07-11 — Entry 13 (environment complete + SCOPE GATE): Track C live on BOTH environments; STOP before spatial

- **SCOPE (Karl)**: complete the vector feature end-to-end, then STOP before geospatial — he tests vector first. Task #5 on hold; EXECUTION_PLAN spatial section gated; memory updated. NO CU8 upgrade — feature targets RTM w/ backcompat (probe symbol variants); CU8 not needed for anything found so far.
- **Models verified live (one smoke call each)**: local VectorLab — `VectorLabEmbeddingModel` (OpenAI, text-embedding-3-small) via AI_GENERATE_EMBEDDINGS → 1536-D float32, L2 .999961; `dbo.AI_ClaudeSonnet5` sproc (Anthropic Messages, claude-sonnet-5, credential [https://api.anthropic.com/]) present. Azure — `VectorLabEmbeddingModel` (Azure OpenAI @ sqlninja.openai.azure.com) → identical embedding facts; `dbo.AI_AzureOpenAIResponse` sproc (gpt-5-mini responses API). Chat sprocs are sp_invoke_external_rest_endpoint wrappers, NOT external models (CREATE EXTERNAL MODEL = EMBEDDINGS only). VEC-10 Pipeline/re-embed + VEC-7 model probes fully unblocked; VectorLabRealChunks (120-row embedded corpus) deferred to VEC-10 (costs ~120 calls).
- **Guide + probe corrected to verified symbols** (Karl's distance_metric fix confirmed + extended): guide §5 + §8.3 and _build/sql/vectorlab_probe.sql now use `distance_metric`/`vector_index_type` (no `_desc` anywhere), tolerant `dvi.*` DMV projection with real Azure names noted, and §8.3's format CASE marked "version key absent = RTM current format — probe, don't assume legacy".
- Azure vector-index absence CONFIRMED expected: serverless GP tier build failure (Msg 42234); probe agent cleaned its residue.
- Env note: `VECTOR(1536)` + AI_GENERATE_EMBEDDINGS worked at compat 170 on both; same input string → same norm on both providers' text-embedding-3-small.

### 2026-07-11 — Entry 11: VEC-5 pt 1 committed — the pipeline is VISIBLE end-to-end

- Tab strip order `Results | Vector | Messages | Query Plan`; sniff = QsResultColumn.vector flatMap in app.tsx (memoized); visibleActiveTab fallback + resultsFillActive extended; runKey per run.
- vectorTab.tsx (own 18KB chunk, verified out of entry closure via metafile; bundle-budget 3/3 green): 6-workspace rail (Profile live; Search/Compare/Projection/Index/Pipeline honestly disabled "coming in a later build"), facts strip, status bar (scope + "Local computation · no SQL executed · no network requests"), column selector, Profile view (L2 histogram w/ p5/median/p95, variance top/bottom bars, findings list w/ severity colors + hints + drill-in drawer showing result-row/dimension ordinals + truncation note, pair-distance histogram, partialReason fact), render.begin/firstPaint marks. Styles appended to queryStudio.css (`qs-vec-*`).
- **VEC-5 REMAINING**: per-surface CSP hook (webviewBaseController — default-src 'none' for QS + pins); L1/L∞ norm toggles; group comparison (needs grouping/label column concept); mock-fidelity pass against vec_profile.png (top context bar w/ Model enabled + table + Sample popovers = VEC-7 probe territory; Evidence/Diagnostic-session footer chips); live demo pass against VectorLab (launch app w/ gates on: mssql.queryStudio.enabled + vectorWorkbench.enabled, run `SELECT chunk_id, chunk_text, embedding FROM VectorLab.dbo.VectorLabChunks`, verify tab + Profile + findings match ground truth incl. 12 null/4 zero/8 near-zero/dup groups, session-diag markers present); webview state-taxonomy strings; a11y pass (F6 cycle, tablist semantics — partial); THEN VEC-6.
- **VEC-4 REMAINING (restart here)**: (b) DONE — `src/queryResults/vector/vectorAnalysisWorker.ts` written + typechecked (pure exported core `analyzePackedVectors` for unit tests + worker_threads envelope; Welford per-dim variance, float64 norms, SHA-256 dup groups over row bytes, centroid p99 outliers, robust norm-outlier band, seeded xorshift pair sampling w/ monotonic deadline → partialTime; DETAIL_CAP 256; bundle entry `vectorAnalysisWorker` added to scripts/bundle-extension.js → dist/vectorAnalysisWorker.js). Still open:
  (a) DONE — `vectorResultSource.ts` committed (pt 2): planWindows (full vs evenly-spaced uniform windows, deterministic), ingestVectorColumn (streamRows vectorAnalysis + sparse ordinals, strict codec decode, null/unavailable counts, dims from metadata or first cell + replan, all budgets → honest VectorPartialReason, source-ordinal Int32Array, descriptor w/ budget echo), ingestBudgetFrom(QueryTuningParams).
  (c) `src/queryResults/vector/vectorWorkbenchService.ts` — session manager: open (validate gate + column.vector metadata + retain lease {kind:"vectorWorkbench"}) → handle (crypto random) + generation; profile → source ingest → spawn Worker(dist/vectorAnalysisWorker.js, workerData envelope + transferList [buffer]) → map VectorWorkerResult → VectorProfileSummary (stamp evidence localComputation + sample descriptor); findingDetail from cached worker findings (map rowIndices → resultRowOrdinals via sample plan!); cancel (worker.terminate + generation bump); close (release lease); caps: ≤2 workers global, ≤2 sessions/controller, session expiry ~5min idle; markers `mssql.queryResults.vector.{ingest,analysis.begin/end/cancel,worker.end}` via Perf.marker w/ explicit traceId + counts/bytes/ms only.
  (d) controller handlers: queryStudioController.registerHandlers — onRequest(VECTOR_RPC.*) delegating to service w/ model.executionHost.retainedStore; wire QsState.capabilities.vectorWorkbench = gate for the webview sniff.
  (e) markers registry-first in perftest/packages/observability-contracts/src/registry/event-types.json (incl. `mssql.queryStudio.boot.vectorChunkRequested/Loaded` + perf-mode tab-activation seam) → npm run build && npm test && npm run generate → copy generated TS to vscode-mssql sharedInterfaces/observabilityContract.generated.ts (vendorSync.test.ts guards drift).
  (f) tests: worker pure-core against synthetic fixtures MATCHING VectorLab ground-truth classes (zero/near-zero/non-finite/dup/near-constant counts); sampling determinism (same seed ⇒ same result); budget/partial reasons; service open/cancel/close lifecycle + lease release; value-free assertion (marker attrs contain no arrays/strings beyond enums).
  Commit prefix `qs: vector — …` (vscode-mssql), `core: …` (perftest). VectorLab corpus VERIFIED in `_build/sql/` (Entry 9).

### 2026-07-12 — Entry 15: post-83b implementation reconciliation

- Audit baseline: vscode-mssql `83b6276dd` (`Query Studio: preserve pane state and harden Vector lifecycle`). This entry inventories committed code at that point; it does not retroactively add validation to older slices.
- **User decisions override the earlier mock/spec defaults:** results-tab order is `Results | Messages | Vector | Query Plan`; the preview Vector tab requires the feature gate, a terminal non-plan result, and at least one negotiated `binary-v1` vector column; text-fallback results remain in Results until a real limited-mode experience exists; panel-local state must survive renderer recreation while its run remains valid.
- Entry 11's `Results | Vector | Messages | Query Plan` statement is historical and superseded. Opening Vector never enables transport. The feature setting must be active before execution; changing it cannot retrofit typed cells into an existing run.
- `83b6276dd` added controller-memory panel state for shell/Results/Messages/basic Vector/Query Plan state, kept sibling result tabs mounted, added pane error boundaries, reset Vector services on rerun, and tightened typed eligibility. It does **not** complete Vector nested-state persistence: Compare/Search/Projection/Index/Pipeline local state is not yet represented across renderer recreation.
- Pinned parity remains incomplete: the pinned controller advertises Profile/Compare/Projection parity but, at this baseline, registers only open/profile/finding/cancel/close Vector RPCs; Index is also exposed despite requiring a live verified binding. VEC-11 remains PARTIAL until the handlers/locks and lifecycle tests land.
- VEC-7 remains PARTIAL. Catalog probes and auxiliary sessions are implemented, but Search/Index/Pipeline do not yet share the normative verified binding object. They must not independently infer or accept a table identity from renderer input.
- **Search candidate is work in progress only:** `vectorSearchService.ts`, `vectorSearch.ts`, `vectorSearchView.tsx`, `vectorSearchView.css`, and `vectorSearchService.test.ts` were untracked in the vscode-mssql worktree during this audit. They are not committed, wired, build-validated, test-validated, or live-validated by this entry. The committed rail still disables Search. The candidate currently covers Selected row and Paste vector, not the four-source normative scope.
- Acceptance scenario IDs are now `VTEST-01..VTEST-22`; `VEC-0..VEC-12` is reserved for implementation checkpoints.
- Corrected status board above is authoritative. Next dependency order: VEC-11 pinned/state correctness → VEC-7 verified binding → VEC-8 integration/completion → remaining Profile/Compare/Projection/Index/Pipeline gaps → VEC-12 full exit matrix. Spatial remains gated.

### 2026-07-12 — Entry 16: Vector Search integration and lifecycle hardening landed

- **Landed:** vscode-mssql `67eb22d7c` (`Query Studio: integrate Vector Search and workspace lifecycle`); perftest scenario wave `d72d1d4`; Projection corpus-count correction `ec21555`.
- **Search slice:** the rail is enabled and all four sources are implemented (selected row, text with a catalog-verified model, pasted float32 vector, and bounded A-H expression grammar). Host-owned opaque target/model bindings, catalog allowlists, exact + version-probed ANN comparison, structured AND filters, same-session staleness measurement, recall/rank evidence, generated-SQL drawer, cancellation, terminal result restoration, and value-free `search.end` are covered. Automatic selected-row exclusion is deliberately refused until STS2 supplies verified result-column lineage.
- **Index/Pipeline slice:** Index state and generated-only scripts are target-scoped. Pipeline now re-verifies exact model identity and normalized endpoint immediately before egress; consent is single-use and revocable; source size/truncation is bounded before SQL retention; active SQL is cancelled on hide; two allowlisted terminal comparisons survive recreation; stable opaque model IDs survive reprobe through bounded keyed digests. Model-statement counts are host-authoritative, advance when the SQL handle is acquired, survive suspension, and rotate by query generation.
- **Pane lifecycle/accessibility:** nested Search/Compare/Projection/Index/Pipeline state is controller-memory-only and bounded; filter values/model text/vectors/SQL are not retained in panel state. Results, Messages, Query Plan, Profile drawer, Index script, rank-grid selection, and per-variant SQL scroll state restore across renderer recreation. Hidden live-only work is cancelled; pinned live-only panes lock honestly. Async errors use alert semantics and histogram data has a table equivalent.
- **Extension validation:** final mssql build/typechecks/bundles green; full lint green plus post-fix focused lint; focused Vector/QS suite 239 passing / 1 environment-gated Azure probe pending, then the issued-at-handle regression slice 101/101; bundle budget 4/4. Earlier full extension sweep: 4,847 passing / 13 pending with three unrelated existing failures (`sqlScripting` strict-host freshness assertion, `sqlLanguage` exact system-schema completion, OE v2 `stableProfileId`). Patch batch remained green against the isolated STS target; no STS files changed in this wave.
- **Live SQL evidence:** generated Pipeline SQL returned a 1,536-D embedding with L2 norm 0.999806 and `AI_GENERATE_CHUNKS` matched local character offsets. Search exact/ANN live smoke returned 64-D K=10 with recall@10=1.0.
- **Perf evidence:** run `2026-07-12T18-06-15Z_d6aa38b5` passed unopened, Profile, exact Search, and indexed ANN Search 4/4 each. Projection produced successful analysis/worker/paint markers but the scenario incorrectly expected 5,000 analyzed rows; VectorLabChunks intentionally has 12 NULL vectors. `ec21555` pins the correct 4,988 invariant, and corrected run `2026-07-12T18-14-14Z_48461388` passed Projection 4/4 (854.8–876.2 ms exploratory wallclock). Combined current scenario evidence is 4/4 for each of the five scenarios; no baselines exist, so all remain `official:false`.
- **Honest remaining scope:** VEC-4..VEC-12 remain `PARTIAL`. Still open are normative shared binding/wizard persistence, freshness/provenance/group findings, full Profile group comparison, Compare arithmetic/reveal flows, Projection grouping/lasso/inspector, Search shared-snapshot/digest/repro/plan/query-set work, full Index/Pipeline matrices, `VTEST-01..VTEST-22`, privacy/localization/a11y sweeps, and release documentation. This entry does not waive those exit criteria. Spatial remains blocked by the user gate.

### 2026-07-12 — Entry 17: Spatial redesign complete; implementation gate lifted

- User direction supersedes the 2026-07-11 Spatial stop gate: begin Spatial planning now while the remaining Vector work is finished separately.
- Re-read the spatial baseline/addendum, distilled briefs, mock/runtime, Query Studio webview/controller/data-path briefs, STS2 transport, observability/perftest material, recent Vector commits, and current branch code across all three repos. Rendered and visually inspected the Spatial HTML mock.
- Current branch reconciliation: compact capture privacy, UTF-8 encoded-row accounting/frame guard, safe UDT binary fallback, typed-cell codec foundation, sparse projection, leases, CSP, lazy chunks, controller-memory view state, and Vector perf activation already exist. Typed spatial WKB, exact provider identity, codec policy, pane/session/renderer, spatial diagnostics, and tests do not.
- Wrote `_build/SPATIAL_DESIGN_AND_EXECUTION_PLAN.md`. It locks the offline-first serious-analysis UX, minimal result-pane contribution framework, opt-in WKB/SRID contract, controller-bound pull session, worker-backed decode, isolated Canvas/GPU/list render tiers, query/grid selection integration, cross-process trace stitching, Debug Console Spatial drill-down, deterministic SpatialLab corpus, and dependency-ordered `SPA-0..SPA-10` execution.
- Intentional revision to the older execution addendum: worker-backed WKB decode is the production default (with measured cooperative fallback) because the explicit huge-data/no-responsiveness requirement cannot rely on per-cell main-thread slicing alone. The GPU point tier remains evidence-gated and isolated behind an adapter.
- No production code was changed and no Spatial implementation checkpoint was started in this planning entry.

### 2026-07-12 — Entry 18: Spatial implementation complete through SPA-8; live scale gates green

- **Cross-repo transport and safety:** sqltoolsservice `f1a6393b` adds opt-in `spatialWkbV1`/`wkb-v1` geometry and geography transport using exact provider identity, sequential bounded reads, canonical `AsBinaryZM()` WKB, SRID/layout metadata, cell-local unavailable states, diagnostics, ordinary-client fallback, and decision/spec coverage. Local, Azure, unit, scenario, replay, and fidelity validation passed, including Z/M preservation.
- **Extension implementation:** vscode-mssql `720fd3fe5`, `267530a4d`, `26f0d0cd9`, `e7e7a1c99`, and `dcda59cca` land the dependency/license/observability foundation, guarded tagged-cell codec, terminal eligibility, minimal lazy result-pane contribution framework, controller-bound sparse pull sessions, bounded lifecycle and leases, worker decode, offline OpenLayers Canvas map, synchronized list/details, grouping/filtering/color-by, query-grid reveal, controller-memory state, pinned parity, Debug Console diagnostics, localization, and the isolated WebGL point tier.
- **Lifecycle/build hardening:** vscode-mssql `90d084073` and `31f351d49` fetch the locally packaged decoder through the webview resource channel and launch it as a CSP-safe Blob worker; the worker is separately emitted without split imports and the bundle test enforces self-containment and size. `b06cc650f` shares a deterministic 50k automatic tier cutoff so 10k remains Canvas and 100k exercises WebGL. No external tile/service/network capability was introduced.
- **Results regression fixed:** vscode-mssql `790c63cc1` adds a pure visible-tab resolver. A running query with transiently empty result metadata now keeps Results selected; terminal no-result executions may select Messages. `SELECT 100` therefore opens the Results grid instead of the blank Messages surface shown in `screens/message-blank-selected.png`. The focused regression test is green.
- **Performance harness:** perftest `aa26fe8`, `3e6de89`, `224a037`, `4cdb826`, `26e990f`, `d7d03ba`, and `2a77143` add registered Spatial observability, unopened/10k/100k scenarios, connection profiles, read-only external-database operation, a one-repetition smoke config, and lifecycle-correct completion on `render.settled`. The scenario contract suite is 73/73 green and the workspace build is green.
- **Live end-to-end evidence against the configured Azure SQL database and development STS/extension:** diagnostic run `2026-07-12T23-09-30Z_4b16202c` passes unopened lazy-load absence; `2026-07-12T23-07-22Z_178fb0b3` passes 10,000 rows with `prepare.end outcome=ok`, Canvas settle, 10,000 features/vertices, zero skipped, and no long tasks; `2026-07-12T23-08-06Z_d6cc286e` passes 100,000 rows with `prepare.end outcome=ok`, progressive Canvas first paint, WebGL `gpuPoints` settle, 100,000 features/vertices, zero skipped, and no long tasks.
- **Final focused extension gate:** webview/extension builds and two-stage bundle are green; 19/19 Spatial geometry/session/resource-worker/view-state/results-focus/bundle-budget tests pass. The broader affected suite was 31/31 green earlier. Full extension sweep recorded 4,872 passing / 16 pending with four unrelated pre-existing failures; full perftest CLI recorded 130 passing / 14 skipped with one unrelated central-store integration failure because its localhost:14333 service was absent.
- **Release honesty:** SPA-0..SPA-8 are complete and committed. SPA-9 remains `PARTIAL` only for promotion evidence that cannot be manufactured by one implementation session: named official baselines after stable multi-run/multi-machine variance plus the final manual visual/theme/keyboard/screen-reader acceptance sweep. SPA-10 remains intentionally unstarted and requires separate approval.

### 2026-07-14 — Entry 19: SPA-10 map layers — MAP-0..3 landed (world outline + host-proxied XYZ)

Per ONLINE_MAPS_EXECUTION_PLAN.md (new; addendum wins; decisions D-0021..D-0034).
LANDED (vscode-mssql 4d4771000 MAP-1, d708d3f69 MAP-2/3, +defensive-init fix;
perftest core: basemap markers registered+vendored MAP-0):
- Contracts-first: basemap.open/tile.end/close (host) + layer.begin/ready pair
  with derived metric layerReady; render family gained layer attr, offline now
  honest. vendorSync + conformance green.
- MAP-1 offline World outline: Layers <select> gated on NEW default-off
  mssql.queryStudio.spatial.basemap.enabled (capabilities.spatialBasemap;
  pinned panes via PinnedResultsState.spatialBasemapEnabled); Natural Earth
  land-110m (55KB, ThirdPartyNotices) copied to dist/views, fetched lazily on
  selection only; EPSG:4326/3857 eligibility (planar never on Earth, D-0030);
  layerId view state (bounded id, rerun carry-forward D-0031); bundle-budget
  guard keeps the asset out of every JS chunk.
- MAP-2/3 online slice: spatialBasemap host module (validation grammar §5.2,
  fingerprints, sanitized descriptors, consent restore-never-prompts D-0027,
  HMAC-keyed bounded disk+memory cache D-0028 under the dedicated
  globalStorage root = the ONLY extra localResourceRoot, typed fetcher with
  https/redirect/size/timeout/sniff/retry + resolved-address private-network
  gate), session manager (trust/eligibility/consent/zxy/generation/
  concurrency, markers), qs/spatial.basemap.* RPCs, controller wiring with
  rerun/configChanged/disposed cleanup, OL adapter via injected requestTile
  (kept vscode-jsonrpc out of the chunk graph — budget test caught it),
  consent modal, attribution overlay, honest status states. CSP UNTOUCHED
  (connect-src as before; tiles ride asWebviewUri img-src).
- Commands: mssql.spatialBasemap.clearCache / clearConsent (palette-gated).
VERIFIED: tsgo both configs; spatial band 64 passing (15 new host tests incl.
privacy canaries: no URL/coordinate/secret in descriptors, cache paths, or
marker attrs); full suite 5114/12/5 = the 5 documented pre-existing (two extra
failures were my init leaking into mock contexts — fixed, suites re-green).
Mid-build tri-repo pull: one lockfile conflict (sql-database-projects, took
upstream — their repin now installs; feed caught up on lru-cache 11.5.2).
REMAINING (MAP-4, next stretch START HERE): perf action
mssql.perf.queryStudioSpatialSelectLayer + perftest scenarios
querystudio-spatial-basemap-worldoutline (A/B vs points-10k-offline, measure
layer.begin→layer.ready + settled{layer}) + negative proofs (gate off / None ⇒
basemap markers absent; extend unopened scenario) + scenario contract tests +
config.spatial.local.jsonc; live A/B evidence; cache-size surfacing polish;
Playwright sweep. DEFERRED (D-0032/D-0033): defaultLayer setting, Azure Maps
adapter (PR5), WMTS/WMS/vector/PMTiles, OSM-standard adapter, live-internet
perf scenario (no controlled endpoint in harness — online path is proven by
fake-fetcher tests).

### 2026-07-14 — Entry 20: Vector Workbench bug batch (Karl dogfood list) + QS shell fixes

LANDED (vscode-mssql, one commit per concern; see git log `qs:`/`grid:`/`oe:`):
- Search Target oscillation (Karl #5/#8): the authoritative-targetId prop is
  the view's OWN emission round-tripped one commit late; the sync effect
  treated the echo as an Index-initiated change, reverted local picks, and the
  persist effect re-emitted the reverted value — perpetual leapfrog, pane-wide
  flicker. Fix: `vectorSearchTargetSync.ts` pure seam
  (`resolveAuthoritativeVectorTargetIndex`) — a prop equal to the last
  emission carries no information; only a differing prop applies. Leapfrog
  convergence simulated in vectorSearchTargetSync.test.ts.
- "Vector could not be rendered." after Add filter → pick column (Karl #6):
  REAL stack recovered from MSSQL.log — `TypeError: Cannot read properties of
  null (reading 'value')` in VectorSearchView render. All three predicate-row
  handlers read `e.currentTarget.value` INSIDE setState updaters; React nulls
  currentTarget after dispatch and defers updaters to render when the queue
  isn't empty (hence intermittent). Reads hoisted; webview-wide multiline grep
  proves the anti-pattern is gone. + `target?.filterColumns?.length` guard.
- Text-with-model draft lost on tab switch (Karl #7): panelActive=false effect
  wiped modelText/modelParameters, and the webview-recreation snapshot had no
  field for them. Draft text/model id/parameters now ride
  QsVectorSearchViewState (bounded 32768/256/2048, validators + hasOnlyKeys),
  seeded on mount, emitted on change; hide no longer wipes drafts (in-flight
  prepare/generated vector still cancelled+cleared). NOTE: deliberate §9.1
  deviation — spec excluded "model-source text" from the snapshot; Karl
  explicitly requested restore (2026-07-14). Memory-only contract unchanged;
  new runs still clear it (reset not carried).
- Projection never frames points (Karl #10): fit clamped UP to SCALE_MIN=6 —
  wide PCA spreads (unnormalized embeddings) need scale « 1, so every fit
  landed over-zoomed. New pure `vectorProjectionMath.ts`: unclamped-below fit,
  fit-relative zoom-out floor (fit/8, capped at legacy 6), and
  projectionShowsAnyPoint guard — a RESTORED camera that frames none of the
  data (saved against another column) refits instead of showing empty space.
  Validator now admits sub-1 scales (rejecting them dropped the ENTIRE panel
  snapshot on round trip — silent state loss).
- Vector pane document-scroll + dead space (Karl #4): defense in depth —
  `body{overflow:hidden}` for QS/pinned pages (document NEVER scrolls; panes
  own scrollbars), `.qs-root` 100vh→100% (matches the #root clip chain; vh in
  iframes disagrees with the layout viewport under zoom/scrollbar-gutter),
  `.qs-vec-root` overflow:hidden, `.qs-vec-workspace` min-height:0 +
  max-height:100% (stretched flex item's min-height:auto let tall content
  grow the row past the pane instead of scrolling).
- Reembed dialog cropped (Karl #9): scrim was position:absolute scoped to the
  PANE while the body capped at 60vh of the VIEWPORT. Now position:fixed like
  the Search model dialog; dialog is a flex column capped calc(100vh-72px),
  only the body scrolls.
- QS status bar wrap (Karl #2): `.qs-status-message` base rule was missing —
  nowrap+ellipsis+min-width:0; segments and PRODUCTION warning flex-shrink:0.
- Grid cross-axis scroll reset (Karl #3): scrollbar grabs emit NO pointer
  events in Chromium — the 200ms pointer-focus guard never armed, container
  focus re-ran gotoCell and snapped BOTH axes to the active cell. Guard now
  also arms from onMouseDownCapture.
- OE v2 Edit Connection (Karl #1): `mssql.objectExplorerV2.editConnection` —
  profile via groupConfig+stableProfileId (moveToGroup pattern), delegates to
  v1 `mssql.editConnection` (accepts bare profile, opens Connection Dialog
  pre-filled); menu on all four connection kinds, palette-suppressed.
VERIFIED: tsgo both configs clean; eslint clean on changed files; new suites
31 passing (vectorSearchTargetSync, vectorProjectionMath, view-state
round-trip incl. model-draft bounds + sub-1 scale); vector/grid/QS band
533/1 failing = documented pre-existing RowStore VEC-3; full suite run
recorded in the commit-time note below.
REMAINING: Karl to re-verify #4's document scrollbar in his dogfood session
(root cause defended on all layers but the growing element was never observed
live); VTEST sweep + remaining Entry 16 scope unchanged.

### 2026-07-15 — Entry 21: scroll-yank root causes + stale-webview class fixed; checkouts synced

Karl's re-reports came from checkouts WITHOUT Entry 20 (he tests from
langsrv2 / repos/test/vscode-mssql; fixes lived only in langsrv). While
syncing, two REAL new root causes fell out of his fresh evidence:
- Chrome trace (Trace-20260715T124704): ALL mid-drag scrollTop writes come
  from SlickGrid's own _handleScroll→scrollTo(), and scrollbar grabs emit
  NO pointer/mouse events — both prior "arm the guard" fixes could not
  hold. Fixed twice over (commit b84e15276): (1) focus reveal now requires
  POSITIVE keyboard evidence (window-level Tab keydown ≤250ms) instead of
  absence-of-pointer; (2) streaming setLength→updateRowCount waits for a
  200ms scroll-quiet window — updateRowCount reaches scrollTo(), which
  teleports the thumb mid-drag whenever the page/offset mapping shifts
  (matches "jerky until the run finishes, then smooth").
- Pinned pane "missing maximize button": the on-disk bundle PROVABLY
  contained the wiring (dev-mode chunk inspection + entry references) yet
  the running pane lacked it → VS Code's webview service worker serves
  STALE cached ENTRY bundles (unhashed names; chunks are content-hashed
  and immune). Fixed with a per-host-session cache-buster on entry asset
  URLs (6eb482a00). This class likely contaminated other "still broken"
  reports.
- Document-scroll backstop (8fe0a25d0): html/body/#root pinned to 0 on any
  scroll event + violation logged with the focused element — the vector
  dead-space repro will now name its culprit in MSSQL.log if it survives
  the Entry 20 CSS containment.
- Tri-repo pull: origin perf commits merged both ways (perftest registry
  notes conflict resolved, contracts regenerated + re-vendored, 27/27;
  spatial SpatialMap/SpatialResultsPane conflicts resolved keeping
  basemap + upstream renderer/partialReason changes).
VERIFIED: full suite 5215/12/5 (the documented five); grid band green incl.
new defer + Tab-gate tests; both test checkouts fast-forwarded to 6eb482a00,
npm install + FULL build run, fix strings verified in their dist.
REMAINING: Karl re-tests #2/#3/#4 and pinned maximize on the synced builds
(fresh extension host needed); MAP-4 unchanged as the spatial restart point.

### 2026-07-15 — Entry 22: spatial dogfood batch — map context menu, panel splitters/collapse, OSM one-click setup

Karl's second spatial dogfood list (commit f20c64fbb, qs:). Vector item #1
(64-dim embeddings) withdrawn — he found the model-parameters override UI.

- **Map right-click (screens\spatial-copy.png)**: the default webview
  Cut/Copy/Paste menu appeared over the canvas and none of it could work.
  Suppressed on the map region (data-vscode-context preventDefault items +
  onContextMenu preventDefault) and replaced with a real menu: **Copy
  image** composites the OL layer canvases into one PNG on the clipboard
  (spatialMapExport.canvasCompositeMatrix handles CSS matrix transforms +
  style/pixel scale fallback, identity on malformed — unit-tested; WebGL
  buffer read is safe because export runs renderSync inside
  rendercomplete), plus **Fit**. Outcome toast bottom-left (loading toast
  owns bottom-right). SpatialMap is now forwardRef with an exportImage
  handle.
- **Side panels**: feature list and details get drag splitters against the
  map (qs-splitter idiom, widths clamped 150..50% live, 120..4000 in the
  validator, persisted as spatial.listWidth/detailsWidth, carried across
  reruns) and Perf-History-style collapse — section headers with chevrons,
  collapsed panels become 24px expand rails. listOpen/detailsOpen finally
  have UI. Body layout grid→flex; the <760px hide-details media query is
  gone (user-controlled now).
- **LATENT STATE-DROP BUG fixed**: isSpatialState's filters hasOnlyKeys
  omitted the optional geometryType/srid keys — setting either filter made
  the WHOLE panel snapshot fail validation and silently drop on restore.
  Regression-tested.
- **Basemap onboarding**: Karl had to ask Copilot for the sources JSON —
  "I don't think anyone will figure this out." First spatial view now
  offers one-click OpenStreetMap setup (spatialBasemapOnboarding, host
  seam-injected + 4 decision tests): writes enabled+sources to USER
  settings (application scope preserved, §5.1), records consent for
  exactly the fingerprint written (offer text carries the tile-coordinate
  disclosure — no double prompt), don't-ask-again in globalState
  (mssql.spatialBasemap.setupOffer.dismissed.v1), once per session, never
  when enabled+configured. Trigger: QsSpatialOpenRequest. Basemap config
  changes bump QsState.spatialBasemapEpoch (controller listener now
  watches mssql.queryStudio.spatial.basemap) so a mounted pane re-fetches
  the layer list live — covers the enabled-but-sources-empty accept path.
VERIFIED: tsgo both configs, eslint 0 errors, targeted vscode-test band 34
passing (onboarding 4, view-state widths/filters, export matrix 3), full
langsrv build green; both test checkouts fast-forwarded to f20c64fbb + full
builds green.
REMAINING: Karl re-tests in a fresh extension host; MAP-4 (perftest spatial
scenarios + live A/B) unchanged as the spatial restart point.

### 2026-07-16 — Entry 23 (pointer): QS-side dogfood fixes landed in the OE round-3 batch

qs: 19b513493 + core: cec2999a7 (details in oe-docs/PROGRESS.md Entry 18):
plan properties filter case-insensitive; Peek Definition renders the
scripted CREATE inside Monaco (virtualContent over qs/lang.definition +
editor-opener → mssql-def beside; ctrl-hover no longer pops tabs); pinned
documents with actual plans get the REAL Query Plan tab (qs/getPlanState
over the frozen snapshot; plan sets leave the Results grid stack — this
was the rendering-error/unbounded-height report).
