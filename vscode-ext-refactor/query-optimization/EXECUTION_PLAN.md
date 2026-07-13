# Query Optimization Execution Plan (QO)

**Status:** ACTIVE — build plan for the Query Studio query-execution/results perf effort on `dev/query`.
**Date started:** 2026-07-09
**Companion docs:** `query_editor_results_execution.md` (current-state review), `query_optimization_plan.md` (design, phases R0–R8). This plan turns those into concrete, restartable batches (QO-1..QO-9) with verified current-state corrections from source inspection (2026-07-09).
**Journal:** `PROGRESS.md` in this folder. One entry per batch/sub-batch with commits, deviations, and residuals. **On restart: read PROGRESS.md first, then this plan; the journal wins on conflicts.**

**Repos/branches:** `vscode-mssql` (`dev/query`, commits `qs:` / `core:` per repo convention), `sqltoolsservice` (`dev/query`, commits `STS2:`), `perftest` (`dev/query`, commits `core:` / `central:`).

---

## 0. Verified current-state corrections (source inspection 2026-07-09)

The design docs are accurate except where noted. These corrections are BINDING on the batches below:

1. **`maxCellBytes` is DONE end to end** (STS2 commit `7532d145`): reducer clamps lower-only via `EffectiveMaxCellBytes`, journaled effect arg, `WireValueEncoder` honors it, `maxCellBytesHonored` negotiated by `Sts2Backend`. Copy this plumbing pattern for pageRows/pageBytes/timeoutMs.
2. **The pageRows/pageBytes/timeoutMs plumbing is 80% built at both ends; the middle drops it.** `QueryExecuteRequest` (Abstractions/DriverPort.cs:105) already has `PageRows`/`PageBytes`/`QueryTimeoutMs` and `SqlClientSession` honors `PageRows` + `CommandTimeout`. But `Sts2CoreReducer.DecideQueryExecute` never reads them from options, and `DriverEffectRunner.cs:392-398` hardcodes `Sts2Defaults.PageRows/PageBytes` and leaves timeout 0. Extension side: `sts2Backend.start()` sends only `pageRows`+`maxCellBytes`; the **orchestrator passes only `priority` and optional `timeoutMs`** for user queries — no page options at all.
3. **`approxBytes = JSON.stringify(params.rows).length` is live at `sts2Backend.ts:761`.** No byte measurement exists anywhere in STS2 (not runner, not core).
4. **RowStore spill is synchronous AND double-encoding**: `spillPage` re-runs `JSON.stringify(page.compact)` per eviction, `materialize` re-admits read pages into the LRU (export scans thrash the viewport), plain LRU with no protected/probationary split. `getRows` cell null/non-empty counting is UNGATED (rowStore.ts:244-259). Memory (64 MiB) / spill (2 GiB) caps are hardcoded constants.
5. **`MessagesView` is NOT virtualized.** Commit `7d0aecd90` added memoization + `messagesPrepared/messagesRendered` marks only. Full `preparedMessages.map(...)` DOM; `Copy All` is webview-side over the full array; `QsGetMessagesWindow` does not exist; `QsMessagesAppendedNotification` carries full message rows per host batch.
6. **Notifications are per-page, unbatched** (`QsRowsAppended` per accepted page). Only coarse `QsState` is throttled (100 ms).
7. **No diagnostic-level concept exists** (minimal/diagnostic/verbose/full) — only rich-enrichment boolean + per-field `DataClassification`. Must be built before "gate behind verbose" tasks.
8. **STS2 has zero `sts2.query.*` events.** Only `core.unexpectedInput` exists as `DiagnosticOutput` precedent. **Core is pure (no clock)** — timings must be measured in `DriverEffectRunner` and ride the journaled `driver.queryEvent` effect payload into the reducer, which re-emits them as `DiagnosticOutput` (keeps replay byte-identical). Every new execute option must ride journaled `driver.queryStart` args (the maxCellBytes precedent).
9. **Grid**: shared `FluentResultGrid`, fixed `FLUENT_RESULT_GRID_WINDOW_SIZE = 50`, no adaptive sizing, no column projection (all columns fetched per window), autosize samples 50 rows, webview re-infers XML/JSON/truncated per cell.
10. **Export/text view fully materialize output** (fetch is chunked; accumulation unbounded; no progress/cancel).
11. **perftest has NO parameter matrix mechanism.** Scenarios are pure-data `ScenarioSpec`s in `packages/perftest-cli/src/scenarios/registry.ts`; per-scenario `userSettings` merge into `User/settings.json` pre-launch (the reliable per-combo carrier); `mssql.perf.setConfig` step exists for runtime flips. Build a **registration factory** expanding base spec × param list into distinct `scenarioId`s. New markers/metrics must land in `packages/observability-contracts/src/registry/event-types.json` + regenerate into BOTH repos' `.generated.ts`, or conformance tests fail. QS end markers must stay rows-guarded (`attrs:{rows:N}`) because the connect preflight emits the same family. New scenarios register `maturity:"exploratory"`, wallclock `official:false`.
12. **The parameter/override/replay substrate already exists** (`src/diagnostics/featureCapture/*`: `FeatureCaptureStore`, `FeatureReplayEngine`, `settingsSnapshot`) **plus a QS replay scaffold** (`src/queryStudio/replay/qsRunCapture.ts`, `queryStudioReplayController.ts`, `sharedInterfaces/queryStudioReplay.ts` with thin 3-knob `QsReplayConfig`). QO-1 extends these; do not build a parallel system. Model files: `sharedInterfaces/inlineCompletionDebug.ts:58-204` (overrides/defaults), `copilot/inlineCompletionDebug/inlineCompletionDebugProfiles.ts` (presets + custom sentinel + sticky-custom), `copilot/sqlInlineCompletionProvider.ts:259-296` (precedence `override ?? profile ?? setting ?? constant`), `copilot/completionSchemaContextCore.ts:456-507` (resolved runtime settings + cache key from resolved snapshot), `sharedInterfaces/inlineCompletionAnalysis.ts` (metrics + pivot by dimension).
13. **`rowStore.test.ts` has ONE test.** Spill/eviction/cap/corruption uncovered — build the safety net before refactoring RowStore.
14. **SQL targets:** perftest container SQL at `localhost,14333` (`sql/docker-compose.sqlserver.yml`, DB `PerfHarness` with `PerfRows` 10k / `PerfRows100k` / `PerfBlobs` seeds). STS2 Engine tests use `STS2_SQLSERVER_CONNSTRING` (skip-not-fail when unset).

---

## 1. Design invariants (from the plan doc, binding)

1. Rows never enter coarse `QsState`.
2. The renderer never owns the dataset; extension host is source of truth.
3. Window fetches are indexed — never scan a result set to serve a viewport.
4. Every limit is honest end to end: honored or reported unsupported via capabilities.
5. STS2 ack = real bounded acceptance (memory-admitted under cap or queued behind bounded spill with backpressure).
6. Large values are never fully read just to be truncated.
7. Secondary views (export/text/cell-doc/plan) are heavy operations: thresholds, progress, cancel, streaming.
8. Diagnostics carry counts/timings/bytes/ordinals/statuses/digests only — never SQL text, cell values, or raw object names. Privacy canaries are part of done.
9. Contracts discipline: new marker/metric vocabulary lands in the perftest observability-contracts registry FIRST, regenerate + re-vendor, then emit.
10. Core purity: STS2 reducer stays clock-free; timings originate in the runner and ride journaled payloads.
11. **Every perf-sensitive knob is a QueryTuning parameter**: declared once, resolved with explicit precedence, snapshotted per run, stamped on events, sweepable by perftest. No new hardcoded perf constant may be introduced by ANY QO batch unless registered as a parameter with a rationale.

## 2. Parameter-first architecture (the spine of this effort)

Everything hangs off **QueryTuningParams** — one typed, versioned parameter block in `vscode-mssql` mirroring the completions pattern:

```
QueryTuningOverrides (all-nullable)         — live override channel (store singleton)
  ?? QueryTuningProfile (named presets)     — interactive / throughput / lowMemory / custom
  ?? VS Code settings (mssql.queryStudio.tuning.*)
  ?? DEFAULT_QUERY_TUNING (constants)
  => ResolvedQueryTuningParams (frozen snapshot, paramsDigest)
```

- Resolved **once per run** in `ExecutionHost.startRun`; the snapshot (and its digest) is stamped into the run record (`QsRunRecord`), attached to `query.submit` marker attrs, and drives: STS2 `ExecuteOptions`, RowStore limits, notification coalescing intervals, grid window policy (sent to webview via `QsState.tuning`), export/text thresholds, diagnostics level.
- Parameter groups (initial registry — extend, never fork):
  - **wire:** `pageRows`, `pageBytes`, `maxCellBytes`, `timeoutMs`, `digestPolicy`
  - **store:** `maxRowsPerResultSet`, `storeMemoryBytes`, `storeSpillBytes`, `spillEnabled`, `maxPendingSpillBytes`, `protectedCacheRatio`, `windowCacheEntries`
  - **notify:** `rowsNotifyIntervalMs`, `messagesNotifyIntervalMs`, `statePushMinIntervalMs`
  - **grid:** `gridWindowMode` (fixed|adaptive), `gridWindowRows`, `gridPrefetchFactor`, `gridMaxWindowRows`, `columnProjection` (off|wide|all), `columnProjectionBuffer`, `autosizeSampleRows`, `displayCellClamp`
  - **messages:** `messagesVirtualization` (on|off), `messagesWindowRows`
  - **secondary:** `exportChunkRows`, `exportStreamingThresholdBytes`, `textViewMaxRows`, `textViewSampleRows`, `cellDocumentFormatLimit`
  - **diag:** `diagnosticsLevel` (minimal|diagnostic|verbose|full)
- Settings surface: `mssql.queryStudio.tuning.profile` (public) + `mssql.queryStudio.tuning.overrides` (object, internal/preview) so perftest can inject ANY combination via scenario `userSettings` without one setting key per knob. Existing `mssql.queryStudio.maxRowsPerResultSet` stays and feeds the resolver (back-compat).
- Replay/experiments: enrich `QsReplayConfig`/`QsReplayMatrixCell` with `tuningProfileId` + `tuningOverrides` axes so the existing `FeatureReplayEngine` can sweep parameters in-product later (debug UI itself is a follow-on round, NOT in scope — but the parameter isolation that makes it possible IS).

## 3. Batches

Build order: QO-1 → QO-2 → QO-3 → QO-9a (baseline scenarios early) → QO-6 → QO-7 → QO-5 → QO-4 → QO-8 → QO-9b (spread matrix + tuning report). Each batch = verify green + journal entry + commit(s) before moving on.

### QO-1 — QueryTuning parameter system (vscode-mssql)
Files: `src/queryStudio/tuning/queryTuning.ts` (types, defaults, profiles), `queryTuningResolver.ts` (precedence + digest), `queryTuningStore.ts` (FeatureCaptureStore-based override singleton, normalize helpers), `sharedInterfaces/queryTuning.ts` (webview-visible subset), package.json settings, `executionHost.ts` (resolve per run, stamp run record), `executionOrchestrator.ts` (consume wire params), `replay/qsRunCapture.ts` (snapshot in `QsRunRecord`), `queryStudioReplay.ts` (matrix axes). Tests: resolver precedence, digest stability, profile materialization, settings round-trip, snapshot-in-run-record, privacy canary (no user text in snapshot).
Acceptance: every existing hardcoded perf constant listed in §2 groups is resolvable through the registry (consumers may still read defaults until their batch wires them); `query.submit` carries `tuningDigest` + `tuningProfile`; perftest can set any knob via `mssql.queryStudio.tuning.overrides` in `userSettings`.

### QO-2 — Row-pipeline instrumentation + diagnostics levels (all three repos)
1. Contracts first: add vocabulary to `observability-contracts` registry + regenerate/vendor both repos: `mssql.queryStudio.rows.append.begin/end`, `rows.spill.write/read.begin/end`, `rows.materialize.begin/end`, `grid.window.request/received/painted`, `grid.firstVisibleRowsPainted`, `messages.window.request/painted`, `binding.rowsPage` (receive/convert/sinkWait/ack timings as attrs), and STS2 `sts2.query.reader.open/schema`, `sts2.query.page.build/encode/creditWait/post`, `sts2.query.cancel.request/ack`.
2. `diagnosticsLevel` param (minimal|diagnostic|verbose|full) gating emission granularity: minimal = lifecycle only (today's set), diagnostic = per-run aggregates, verbose = per-page/per-window, full = bounded deep capture (perftest).
3. STS2: measure in `DriverEffectRunner` (TimeProvider), attach stats to the journaled `driver.queryEvent` payload, reducer re-emits `DiagnosticOutput` (replay-deterministic — option (1) from exploration). Aggregate rows/pages/bytes/timings per result set emitted at `query.complete`.
4. Extension binding: receive→validate→convert→sinkWait→ack timings; queue depth.
5. RowStore: append/spill write/read/materialize timings + cache hit/miss counters (aggregate at diagnostic, per-event at verbose).
6. Webview: `QsGetRows` RPC duration, window received→painted, `firstVisibleRowsPainted`, messages window metrics.
7. Privacy canary tests both repos.
Acceptance: one perf run attributes wall time across reader/encode/wire/sink/store/RPC/paint; conformance tests green in both repos; no marker carries SQL text/cell values.

### QO-3 — Honor limits end to end (sqltoolsservice + vscode-mssql)
1. STS2: `DecideQueryExecute` reads `options.pageRows/pageBytes/timeoutMs` (clamp: pageRows ≤ default? NO — pageRows/pageBytes clamp to [1, default*4] bounded by `MaxFrameBytes`; timeout passthrough with 0=provider default), journaled into `driver.queryStart` args; `DriverEffectRunner` passes them into `QueryExecuteRequest` (delete hardcodes at :392-398).
2. `SqlRowsPageBuilder` (new, Drivers.SqlClient): PageRows AND PageBytes both bound page construction (bytes measured as encoded-size upper bound per cell — cheap estimator, exact encoded bytes come in QO-5); single oversized row → one-row page if < MaxFrameBytes else bounded-result error.
3. Capabilities: `pageRowsHonored`, `pageBytesHonored`, `queryTimeoutHonored` in initialize payload; `Sts2Backend` reads them into `SqlBackendCapabilities`.
4. Extension: orchestrator passes resolved wire params (from QO-1) into `ISqlSession.execute` for user queries; `sts2Backend.start()` sends `pageBytes`/`timeoutMs` (wire `V2QueryExecuteParams` extension).
5. Tests: STS2 fake-driver byte-split tests (rows-below-PageRows page splits on bytes), timeout reaches `CommandTimeout`, capability honesty tests, extension conformance tests both capability states, YAML scenario for byte-split.
Acceptance: wide-row query splits pages by bytes before row count; capabilities false unless honored; `verify.sh --quick` green; vscode-mssql suite green.

### QO-4 — Large-cell streaming (sqltoolsservice)
1. `CommandBehavior.SequentialAccess` for the query path; ordinal-order cell reads (page builder already reads in order).
2. Type-aware readers via `ColumnInfo.EngineType/Length`: `GetChars`/`GetTextReader` prefix reads for (n)varchar(max)/xml/text; `GetBytes` prefix for varbinary(max)/image; scalars keep `GetValue`.
3. `digestPolicy` (none|prefix|full) execute option: full digest computed streaming (incremental hash while reading), never post-materialization; default `prefix`. Truncation metadata keeps `of`/`bytes`(when known)/`digest`(per policy)/`v`.
4. Reconcile with `WireValueEncoder`: driver emits pre-bounded `TruncatedCellValue` sentinels the encoder passes through; encoder keeps handling small values.
5. Tests: fake reader proving no full materialization (allocation assertion via bounded reader), Engine tests for real large values (env-gated), truncation honesty preserved, PerfSmoke extension for large-cell mode.
Acceptance: 1 MiB+ cells never fully allocated on the grid path; STS memory bounded in the blob perf scenario.

### QO-5 — Compact rows on the wire (sqltoolsservice + vscode-mssql)
1. STS2: capability `compactRows`; when client opts in (`v2/query.execute` param), rows notifications carry `{compact:{values,nullBitmap,typeHints}, approxBytes, encodedBytes, stats:{truncatedCellCount,buildMs,encodeMs,creditWaitMs}}`. Bytes measured at serialization (single pass).
2. Extension: `Sts2Backend` negotiates; compact path skips rebuild + skips `JSON.stringify(params.rows).length` (line 761); legacy adapter stays for non-compact backends; fake backend supports both.
3. RowStore stores the already-compact page; spill can persist the encoded frame (ties into QO-6).
4. Tests: conformance both shapes, null bitmap/type hints parity vs legacy, exact-numeric preservation, replay determinism.
Acceptance: no extension-side re-stringify on compact-capable STS2; measured CPU reduction recorded in PROGRESS from perf scenarios.

### QO-6 — ResultStore async spill + cache policy (vscode-mssql)
0. FIRST: expand `rowStore.test.ts` to cover current behavior (spill round-trip, eviction, cap-reject, corruption, high-offset windows) as the refactor safety net.
1. Async spill: bounded queue (`maxPendingSpillBytes`), `appendPage` becomes async and awaits queue capacity when saturated (this is the STS2 ack backpressure point per invariant 5); page stays in memory until spill write confirmed; spill failure → truncatedReason + orchestrator cancel + clear message.
2. Frame v2: spill the encoded frame bytes (no re-stringify when source is compact/QO-5); magic/version/length/hash header; corruption → markCorrupt honesty.
3. Cache policy: protected (viewport-fetched) vs probationary (append/scan) segments sized by `protectedCacheRatio`; export/text `reason:"export"` reads stream WITHOUT LRU re-admission (fixes export-evicts-viewport); small window cache (`windowCacheEntries`) keyed by (resultSet,start,count,columns,generation).
4. `getRows(id, start, count, opts?: {reason, diagnostics})` — cell null/non-empty counting only at verbose; null bitmap always (UI needs it).
5. Limits from resolved tuning params (QO-1) instead of DEFAULT_LIMITS constants.
Acceptance: extension host hot path never blocks on spill I/O; export scan does not evict viewport pages; store metrics visible at diagnostic level; expanded tests green.

### QO-7 — Webview render + notification optimizations (vscode-mssql)
1. Notification coalescing: `QsRowsChanged` batched per `rowsNotifyIntervalMs` (flush on set end/complete/cancel/error); messages become count-notifications (`QsMessagesChanged{messageCount,appendedCount,hasErrors,firstErrorIndex}`).
2. Host-owned message store + `QsGetMessagesWindow{start,count}` + `QsGetMessagesText{includeTimestamps,range?}` (Copy All host-side); webview `MessagesView` → virtual list (bounded DOM rows, visible-only formatting, near-bottom autoscroll).
3. Adaptive grid windows: `gridWindowMode=adaptive` computes request size from viewport rows × prefetch factor clamped to [gridWindowRows, gridMaxWindowRows]; velocity-aware (fast scroll → landing window first, cancel stale in-flight); fixed mode preserves today's 50 for fallback/comparison.
4. Column projection: `QsGetRows` gains optional `columnStart/columnCount/includeColumns`; windowed source requests visible columns + buffer when `columnProjection` active and grid is wide; RowStore projects cells + bitmaps.
5. Host-computed display flags (null/truncated/xml/json/linkable bitsets per window) so the webview stops sniffing cell content per render.
6. Bounded autosize (`autosizeSampleRows`, once per result-set generation); `grid.firstVisibleRowsPainted` marker; renderer window-cache hit/miss markers.
Acceptance: 10k-message run types clean (perf scenario proof); wide-grid vertical scroll transfers only projected columns; window fetch markers show adaptive sizing; all tuning-param driven.

### QO-8 — Heavy secondary features (vscode-mssql)
1. Streaming export: chunked fetch → incremental file writes (progress + cancel); in-memory fast path below `exportStreamingThresholdBytes`; CSV/JSON/INSERT writers.
2. Text view: `textViewMaxRows` threshold → prompt/stream to temp doc; widths from `textViewSampleRows` sample; no full-string build above threshold.
3. Cell documents: raw-first + async format above `cellDocumentFormatLimit`; truncated cells open as explicit prefix.
4. Plans: parse cache by (runId,resultSetId,planDigest); async parse; markers.
Acceptance: 100k-row export/text run bounded memory + cancellable; unit tests for no-full-string-above-threshold.

### QO-9 — Perf scenarios + parameter spread + quantitative tuning
**QO-9a (early, after QO-2/QO-3):**
1. Seed fixtures in `sql/seed/create-perf-db.sql`: `PerfRowsWide1000` (1000×300), `PerfLargeCells` (JSON/XML 64 KiB ×100 + 1 MiB ×20), `PerfBlobs1M` (varbinary 1 MiB ×20), messages script (10k PRINT), 100-result-set script, `PerfRows1M` (1M×5 — CHECK seed cost; may gate behind a flag), cancel scripts (WAITFOR variants). Deterministic COUNT verifies.
2. Scenarios (registry + conformance tests, `maturity:"exploratory"`, wallclock unofficial, rows-guarded ends): `querystudio-query-100k-narrow`, `querystudio-query-1m-narrow`, `querystudio-query-wide-1000x300`, `querystudio-query-large-json`, `-large-xml`, `-large-binary`, `querystudio-query-10k-messages`, `querystudio-query-100-resultsets`, `querystudio-cancel-before-first-row`, `querystudio-cancel-midstream`, `querystudio-export-100k-csv`, `querystudio-text-100k`. New metrics (e.g. over `rows.windowFetch`, `grid.firstVisibleRowsPainted`) registered in contracts first.
3. Baseline runs recorded (pre-optimization) for before/after.
**QO-9b (final):**
4. Spread factory in `registry.ts`: `registerSpread(baseSpec, paramAxes)` → distinct `scenarioId` per combo (`-p{digest}` suffix + spread metadata in tags), params injected via `mssql.queryStudio.tuning.overrides` in `userSettings`, combo params recorded in run metadata for the report.
5. Spread matrix across critical axes: `pageRows` × `pageBytes` × `maxCellBytes` × `gridWindowMode/rows` × `storeMemoryBytes` on the key shapes (narrow-100k, wide, large-cell).
6. Run matrix + collectors (processSampler always; extHost profile + renderer trace on diagnostic passes), analyze distributions, produce tuning report (central store or local HTML), and **tune shipped defaults from data** — record decisions in PROGRESS.
Acceptance: tradeoffs validated quantitatively with linked run IDs; defaults chosen with evidence; scenarios green in conformance tests.

## 4. Verification chain (per batch)

- **vscode-mssql** (`extensions/mssql`): `npm run build:extension` (tsgo typecheck both configs + emit) → `npm run lint` → `npm test` (vscode-test unit suite; baseline ~4184; known pre-existing CopilotChatEntry-adjacent alternating flake) → repo build. Webview code: the webview tsconfig typecheck is part of build.
- **sqltoolsservice**: `dotnet build sqltoolsservice-sts2.slnf -v q --nologo` → targeted `dotnet test ... --filter 'FullyQualifiedName~QueryFlowTests'` while iterating → `./verify.sh --quick` before commit (build + unit + scenarios + contract + replay + 200-seed simulator + E2E). Engine tests when `STS2_SQLSERVER_CONNSTRING` set (container `localhost,14333` via perftest compose).
- **perftest**: `npm run build` → `npm test` (workspace vitest incl. conformance) → `perftest doctor` → scenario runs via `perftest run --config examples/config.eval.local.jsonc --scenario <id>`.
- Cross-repo contract changes: regenerate observability contracts, re-vendor into vscode-mssql, keep `observabilityContract.test.ts` green in both.
- Perf evidence: record run IDs + key metric deltas in PROGRESS per batch that claims a perf win.

## 5. Open decisions (decide during build, record in PROGRESS)

| Decision | Default position |
|---|---|
| pageRows/pageBytes clamp ceiling | clamp to [1, 4× default], bounded by MaxFrameBytes; revisit with data |
| 1M-row seed cost | seed if < ~60 s and < ~200 MB, else flag-gated |
| Worker thread for RowStore decode | async fs first; worker only if JSON parse remains hot after QO-5/QO-6 (measure) |
| Compact binary wire | NOT in scope; only if QO-5 measurements demand |
| Full-cell artifact channel | NOT in scope; prefix-open honesty only |
| Debug Console tuning UI | NEXT ROUND; QO-1 must make it possible (params isolated, store-based, replayable) |
| Public vs internal settings | `tuning.profile` public; `tuning.overrides` internal/preview until QO-9b data tunes defaults |
