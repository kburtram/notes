# Query Optimization (QO) — Progress Journal

Companion to `EXECUTION_PLAN.md` (this folder). One entry per batch/sub-batch. **The journal wins over the plan on conflicts.** Restart recipe: read this file top-to-bottom, then the plan, then continue from the first unfinished batch.

Repos: vscode-mssql / sqltoolsservice / perftest, all `dev/query`.

---

## Entry 0 — Plan established (2026-07-09)

- Explored all three repos (4 parallel agents) and corrected the design docs' current-state assumptions; corrections recorded in EXECUTION_PLAN.md §0.
- Key verified facts: maxCellBytes done end-to-end; pageRows/pageBytes/timeoutMs dropped in the STS2 middle (reducer/runner) and never sent by the orchestrator; approxBytes JSON.stringify at sts2Backend.ts:761; RowStore sync + double-encoding spill, ungated getRows cell counting, hardcoded caps; MessagesView memoized but NOT virtualized; no notification coalescing; no diagnostics-level concept; zero sts2.query.* events; perftest has no matrix mechanism; featureCapture/replay substrate + QS replay scaffold exist to build QO-1 on.
- Batch order: QO-1 → QO-2 → QO-3 → QO-9a → QO-6 → QO-7 → QO-5 → QO-4 → QO-8 → QO-9b.

Status: QO-1 starting.

---

## Entry 1 — QO-1 COMPLETE: QueryTuning parameter system (2026-07-09)

**Commits:** vscode-mssql `e70bd4dd4` (Add Query Studio QueryTuning parameter system), perftest `74f94cb` (core: register Query Studio row-pipeline + tuning marker vocabulary).

**Built:**
- `src/sharedInterfaces/queryTuning.ts` — 31-knob typed registry (`QUERY_TUNING_SPEC` canonical key order = digest order), behavior-preserving defaults, profiles interactive/throughput/lowMemory + custom sentinel, pure normalize helpers.
- `src/queryStudio/tuning/queryTuningResolver.ts` — precedence `run ?? store ?? tuning.overrides setting ?? profile ?? dedicated setting ?? default`; salt-free sha256[0:12] digest (cross-session comparable, deliberately NOT the salted privacy digest); dedicated-setting back-compat for `maxRowsPerResultSet` + `inMemorySortFilterThreshold`.
- `src/queryStudio/tuning/queryTuningStore.ts` — live override singleton (the future Debug Console tuning page writes here; UI explicitly next round).
- ExecutionHost resolves ONE snapshot per run → RowStore limits (hardcoded DEFAULT_LIMITS caps replaced), orchestrator `wire` params (pageRows/pageBytes/maxCellBytes now sent on every user batch — pageBytes ignored by STS2 until QO-3), `beginRunRecord` tuning stamp, submit-marker `tuningDigest`/`tuningProfile` attrs.
- Replay: `QsReplayConfig.tuning` + matrix-cell `tuning` axis; snapshot-mode replay uses the record's CAPTURED params (`queryTuningParamsToOverrides`); `executionHost.execute({tuningOverrides})` is the run-level injection point.
- Settings: `mssql.queryStudio.tuning.profile` (public enum) + `mssql.queryStudio.tuning.overrides` (object; the perftest per-combo carrier via scenario userSettings).
- Tests: 12 new queryTuning tests (precedence/clamp/digest/privacy canary) + orchestrator wire-params test. Registry: also retro-registered `rows.maxRowsPerResultSet` + `messagesPrepared/Rendered` (fixed a PRE-EXISTING conformance failure on dev/query HEAD) and pre-registered the QO-2 vocabulary; regenerated + vendored (vendor-sync green).

**Verification:** build:extension + build:webviews + lint green; suite 4334 passing / 3 failing — ALL PRE-EXISTING on clean HEAD (verified by stash-run): (1) sqlScripting strict host CACHE-6 `drop` capability list, (2) sqlLanguage static system catalog `sys.all_*` scoping, (3) observability conformance (FIXED by this batch's registry+vendor). CopilotChatEntry before-each timeout flake appeared in one of two runs (known alternating flake). perftest workspace tests: observability-contracts 27/27 + vendor-sync green; ONE pre-existing env failure `centralStore.integration.test.ts` T-B6 (live central SQL; fails identically on stashed clean tree; 14 siblings skip).

**Deviations:** timeout stays owned by `mssql.query.executionTimeout` (not a tuning knob — behavior setting, already plumbed). Per-batch binding markers deferred in favor of aggregates on the existing `sqlDataPlane.execute` span (avoids queryStudio→services layering leak). `rowsNotifyIntervalMs`/`messagesNotifyIntervalMs` default 0 = current per-page behavior until QO-7 re-tunes with data.

**Residuals for later batches:** pre-existing failures (1)/(2) belong to ls/scripting workstreams — NOT fixed here, flag to Karl; grid.window.painted mark intentionally not registered (request/received + firstVisibleRowsPainted suffice for now).

Status: QO-2 next — emissions (RowStore stats + verbose gating, binding aggregates, webview grid marks) then STS2-side sts2.query.* events.

---

## Entry 2 — QO-2 COMPLETE: row-pipeline instrumentation (2026-07-09)

**Commits:** perftest `74f94cb` (registry, from Entry 1), vscode-mssql `a60b40879` (Instrument the Query Studio row pipeline end to end), sqltoolsservice `ab640e6a` (STS2: journal-side query row-pipeline stats + sts2.query.stats diagnostic).

**Extension side:**
- RowStore: append/spill-write/spill-read/materialize accumulators surfaced via `stats` and stamped as aggregates on `query.complete` (pages/spillWrites/spillReads/appendMsTotal/spillWriteMsTotal/spillReadMsTotal/materializeMsTotal); per-page `rows.append`/`rows.spill.write`/`rows.spill.read` markers ONLY at verbose; **getRows per-cell null/non-empty scanning now verbose-only** (R1 quick win pulled forward from QO-6.4 — null bitmap still always built for the UI); `windowFetch.end` gains `cacheHit`/`materializedPages`/`ms`. RowStore constructor takes the run's `diagnosticsLevel` from the tuning snapshot.
- Binding: `Sts2Backend` accumulates pages/wireApproxBytes/convertMsTotal/sinkWaitMsTotal per query and reports them on the existing `sqlDataPlane.execute` span end (deliberate: no queryStudio-named marker from the services layer, no per-page emission).
- Webview: `grid.window.request/received` marks around every windowed fetch + once-per-grid `grid.firstVisibleRowsPainted` after the first non-empty window paints. `grid.window.painted` deliberately NOT added (received + firstVisible suffice).
- Tests: rowStore.test.ts 1→4 (spill round-trip/eviction, cap-reject, diagnostics-level equivalence).

**Service side (verify.sh --quick green 17:31Z; report entry prepended to artifacts/verification-report.md):**
- Runner stamps per-page `stats` (readMs≈driver gap, creditWaitMs, encodeMs, encodedBytes) on the JOURNALED rows event + per-query totals on completed; reducer emits ONE `sts2.query.stats` diagnostic per query. v2 wire unchanged; Core clock-free; replay byte-identical (stats replay from journal). Per-page envelope flood deliberately avoided — per-page detail is queryable from the journal (perftest StsEnvelopeJournalCollector copies it).
- QueryPipelineStatsTests +3 (journal stats present / wire unchanged, single aggregate diagnostic + privacy canary, replay identity). GeneratedDocs diag-kind description + TRACE-SCHEMA.md regenerated via scripts/update-sts2-docs.ps1.

**Verification:** vscode-mssql suite 4335 passing / 3 failing = the SAME pre-existing set (sqlScripting strict-host, sqlLanguage system catalog, CopilotChatEntry flake) — Entry 1's conformance failure now fixed. STS2 verify.sh --quick green (one transient MSB4018 legacy-exe file-lock failure when run in parallel with the vscode suite; clean rerun green — do not run both gates concurrently).

**Housekeeping:** removed two STALE (July 7) .git/index.lock files in perftest and sqltoolsservice.

**Attribution now available per run:** SQL reader (journal readMs) → encode (encodeMs) → credit wait → wire bytes → binding convert/sink-wait (execute span) → store append/spill (query.complete attrs) → window serve (windowFetch) → grid RPC (window.request/received) → paint (firstVisibleRowsPainted/resultsRendered).

Status: QO-3 next — honor pageRows/pageBytes/timeoutMs end to end + SqlRowsPageBuilder.

---

## Entry 3 — QO-3 COMPLETE: limits honored end to end (2026-07-09)

**Commits:** sqltoolsservice `700562eb` (STS2: honor pageRows/pageBytes/queryTimeoutMs end to end, D-0014), vscode-mssql `df75251a1` (Send Query Studio page/timeout options on the STS2 wire).

**Service:** Core normalizes `options.pageRows/pageBytes` (lower-only, shared `EffectiveLoweredOption` generalizing the STS2-3 maxCellBytes pattern) + `options.queryTimeoutMs` (passthrough-or-0) into the journaled `driver.queryStart` args; runner hardcodes DELETED (older journals fall back); `QueryTimeoutMs` now reaches `SqlCommand.CommandTimeout` (was dead plumbing). New `SqlRowsPageBuilder`: rows AND bytes bound page construction, whichever first; oversized single row = own one-row page (cells still maxCellBytes-bounded); byte accounting = cheap construction-time approximation (exact bytes via QO-2 stats). Capabilities `pageRowsHonored/pageBytesHonored/queryTimeoutHonored` advertised + pinned in initialize-idempotent scenario; SPEC §7.3/§7.5 updated; DECISIONS **D-0014** (two-way: options were already contractual; raising page maxima stays a SPEC-CHANGE, not done). FakeDriver records `LastExecuteRequest`. +9 tests; verify.sh --quick green; report entry prepended.

**Extension:** execute options now ride `options.*` per SPEC — **fixes a real bug: pageRows was previously sent top-level where the service ignored it**. `SqlBackendCapabilities` + fake backend gain the two new flags; negotiation honest (false unless service says true). +2 tests; full suite 4337 passing / 3 failing (same pre-existing set).

**Effect:** the QueryTuning wire knobs (`pageRows`, `pageBytes`, `maxCellBytes`) are now real end to end — a perftest spread over them changes actual service behavior. Interactive default stays 1000 rows/256 KiB; `lowMemory` profile (512/128 KiB/256 KiB cells) now does what it says.

**Residuals:** Engine-category (real SQL) byte-split test deferred to QO-9 live scenarios; note that tuning values ABOVE the pinned service maxima clamp server-side (throughput profile's pageRows 4096 clamps to 1000 on STS2 — recorded for QO-9b analysis honesty; raising maxima = SPEC-CHANGE decision fed by data).

Status: QO-9a next (seed fixtures + scenarios + baselines) — then QO-6 (async spill), QO-7 (webview), QO-5 (compact rows), QO-4 (large-cell streaming), QO-8, QO-9b.

---

## Entry 4 (interim) — QO-9a scenarios + REAL DEADLOCK FOUND (2026-07-09)

**Built so far (uncommitted in perftest until baseline green):** 4 new query fixtures (`wide-columns-1000.sql`, `hundred-result-sets.sql`, `large-cells-1mb.sql` — 1 MiB cells computed server-side, no seed change — and `many-messages.sql` 10k PRINTs); `registerQueryStudioShape` factory (the QO-9b spread seed) + 5 scenarios (100k-narrow / wide-1000x300 / large-cells / 10k-messages / 100-resultsets); family-wide conformance tests (every querystudio-* scenario: registered markers, registry metric pairs, attrs-guarded ends, wallclock-only officials) which also caught + fixed a pre-existing metric-name drift (`queryStudio.open` → canonical `mssql.queryStudio.open`).

**First baseline result:** querystudio-query-100k-narrow 4/4 reps green, wallclock ~1.3–1.6 s (run `2026-07-09T18-19-12Z_a03bee8a`) — the streaming path is already strong at this shape.

**REAL BUG FOUND by querystudio-query-100-resultsets (all reps timed out at 300 s):** multi-result-set queries through the STS2 lane DEADLOCK after exactly the 4-page credit window. Root cause: wire `pageSeq` restarts at 0 per result set, but Core's credit ledger counts pages PER QUERY (`throughPageSeq` = per-query cumulative ordinal; `DecideQueryAck` ignores `resultSetId`) — the binding acked the per-set seq, so its `> highestAckedPageSeq` guard suppressed every ack after the first set; credit drained; pump parked forever. Single-set queries (10k/wide/blob) never hit it. **Fixes:** vscode-mssql `sts2Backend` now acks per-QUERY ordinals (assigned in wire order, acked after durable acceptance) + multi-set regression test (acks [0..5] across 6 sets); sqltoolsservice SPEC §7.8 clarified to the as-built per-query semantics + DECISIONS **D-0015** (two-way: documents implemented behavior; no service code change) + QueryFlowTests `MultiResultSetStreamCompletesWithPerQueryOrdinalAcks` (window exhausts at 4 pages of pageSeq-0 pages; per-query ordinal ack releases). This is precisely the class of bug the QO-9a shape matrix exists to catch.

Also observed working in the wild: QO-2 aggregates on query.complete (pages/appendMsTotal/spill*) and QO-2 windowFetch cacheHit attrs in the failed rep's marker stream.

**CLI gotcha:** repeated `--scenario` flags run only the LAST one — use the config's scenario list (or one flag per run) until the CLI grows multi-flag support.

Full 6-scenario baseline running; final Entry 4 lands with run IDs + per-shape numbers + commits.

### Entry 4 FINAL — QO-9a COMPLETE (2026-07-09)

**Commits:** perftest `7555df3` (core: QO-9a scenarios + baselines), vscode-mssql `1becc4c96` (Fix multi-result-set credit deadlock in the STS2 binding), sqltoolsservice `13bf8ec7` (STS2: document per-query ack ordinal semantics + multi-set backpressure test, D-0015).

**Pre-optimization baselines (runs `2026-07-09T18-54-11Z_48d1d309` + `2026-07-09T19-21-26Z_ad3bbf9c`, 4 reps each, deadlock fix included):**

| Shape | wallclock (min–max) | Notes |
|---|---|---|
| 10k rows (anchor, official) | 0.55–2.0 s | matches existing gate behavior |
| 100k rows × 4 cols | 1.16–1.97 s | streaming path already strong |
| 1000 × 300 wide | 3.11–4.61 s | QO-6/QO-7 column-projection target |
| 20 × ~1 MiB JSON/XML cells | 3.98–4.32 s | truncation-honesty path; QO-4 target |
| 10000 PRINT messages | 4.90–6.42 s | SLOWEST shape — QO-7 virtualization target |
| 100 result sets | 0.58–0.66 s | was a 300 s DEADLOCK before the D-0015 fix |

Messages end-marker guard pinned at the observed deterministic 10003 host rows (10000 PRINTs + synthesized Started/Total + one server info row).

**Residuals:** cancel-before-first-row/mid-stream scenarios need a driver cancel step (harness work, defer); export/text scenarios wait on QO-8 streaming; 1M-row fixture decision deferred (100k covers the spill path for now); CLI runs only the LAST of repeated --scenario flags (use the config list).

Status: QO-6 next (RowStore async spill + cache policy).

---

## Entry 5 — QO-6 COMPLETE: async spill + viewport-safe caching (2026-07-09)

**Commit:** vscode-mssql `c29db1a1c` (Make Query Studio result spill asynchronous with viewport-safe caching).

**Built:**
- Spill writes: serialized ASYNC queue off the hot path; pages stay resident until write confirms; queue saturation (`maxPendingSpillBytes`) back-pressures `appendPage` — the awaited sink now genuinely holds the STS2 ack under storage pressure (invariant 5 made real). JSON stringify happens in the writer, off the append stack (QO-5 will hand pre-encoded frames and delete it).
- Churn protection: re-admitted pages that already have a spill frame DROP their decoded copy on eviction instead of rewriting.
- Cache split: protected (grid-fetched, capped by `protectedCacheRatio`) vs probationary segments; export/text-reason reads materialize WITHOUT re-admission — **a background export can no longer evict the active viewport** (proven by test: full export scan leaves memoryBytes untouched and the viewport re-fetch hits the window cache with zero spill reads).
- Served-window cache (`windowCacheEntries`, grid-reason, complete windows only — cell immutability makes them valid for the run); hits/misses in stats.
- Honest storage truncation: `spillLimit`/`memoryLimit` rejections cancel the query with the §14 storage-limit message (was: silent per-page discard for non-rowcap rejections).
- `getRows`/`appendPage` async end to end (controller/export/planXml callers); `RowReadReason` threaded (`grid`/`copy`/`export`/`text`/`cellDocument`); all knobs from the tuning snapshot.
- Tests: RowStore suite 4→6 (export-no-evict + spillLimit truncation); results-core + orchestrator suites converted to the async API.

**Verification:** build/lint green; full suite **4340 passing / 3 failing** (same pre-existing set). Perf re-check vs baseline: wide-1000x300 **3.12–3.20 s vs 3.11–4.61 s** (no regression, tighter); 100k-narrow 1.76–1.98 s vs 1.16–1.97 s (overlapping ranges — neither shape spills at defaults so QO-6 is neutral there; flagged for QO-9b distribution analysis). Runs `2026-07-09T19-41-44Z_1d44a9a6`, `2026-07-09T19-43-48Z_e1d8f7c2`.

**Deviations:** frame format v2 (magic/hash header) deferred to QO-5 (pre-encoded frames change the body anyway — one format change instead of two); per-result-set memory partitioning deferred (protected/probationary + no-admit streaming covers the observed eviction pathology; partitions only if QO-9b shows cross-set eviction pain).

Status: QO-7 next (webview: notification coalescing, message store + virtualization, adaptive grid windows, column projection).

---

## Entry 6 — QO-7 messages slice COMPLETE: ~4× on the message-flood shape (2026-07-09)

**Commit:** vscode-mssql `1417c5f6d` (Virtualize Query Studio messages and coalesce streaming notifications).

**Measured (querystudio-query-10k-messages, 4 reps):** baseline **4.90–6.42 s** → virtualization only **3.95–5.11 s** → + 50 ms coalescing **1.29–1.58 s**. Runs `2026-07-09T20-01-13Z_177fb08e` (mid), `2026-07-09T20-28-10Z_541ec556` (final).

**Built:**
- Virtualized MessagesView: only visible rows (+overscan) mount and format; heights line-count exact via prefix sums (rebuilt O(n) per append, binary-searched per scroll). CSS: `.qs-message-row` `pre-wrap` → `pre` (SSMS messages-pane behavior — long lines scroll horizontally; wrap would break exact heights). `messagesPrepared` mark now carries `visibleRows`; `messagesRendered` keeps total-count semantics (scenario guard unchanged).
- Copy All → host-built (`QsGetMessagesText`) from the new shared pure formatter module (`sharedInterfaces/queryStudioMessages.ts`) — clipboard byte-identical to the pane, no 10k-row webview join.
- Notification coalescing driven by the run's tuning snapshot (`ExecutionHost.currentTuning`): messages batches flushed per `messagesNotifyIntervalMs`, rows-appended per `rowsNotifyIntervalMs` (accumulated per result set), completion/terminal edges always flush.
- **Default re-tuned from measurement: `messagesNotifyIntervalMs` 0 → 50** (rows stays 0 — page-granular already). First data-driven default change of the effort.
- **Race found by the harness and fixed:** coalesced batches duplicated rows against the webview's catch-up fetch (first coalesced run rendered 10515/10003 and failed the exact-count guard — the guard caught a real correctness bug). Message batches are now position-addressed (`startIndex` = host absolute index) and the webview handler dedupes by position; gaps defer to the catch-up effect.

**Verification:** build + lint green; full suite **4340 passing / 3 failing** (same pre-existing set); scenario 4/4 green at the exact 10003 count.

**QO-7 remaining (next slice):** adaptive grid window sizing + prefetch, column projection for wide grids, host-computed display flags, bounded autosize.

Status: QO-7 grid slice next.

---

## Entry 7 — QO-7 grid-windowing slice COMPLETE (2026-07-09)

**Commit:** vscode-mssql `aca7b1c93` (Make the Query Studio grid fetch window a tuning parameter).

**Built:** `FluentResultGrid` gains an optional `windowSize` prop (threaded prop → controller → data controller → data view; default preserves the fixed 50). Query Studio computes the effective size from the run's tuning snapshot, which now rides `QsGridStyle` in `QsState` (the already-threaded channel): `fixed` = `gridWindowRows`; `adaptive` = surface-height-derived viewport rows × (1 + `gridPrefetchFactor`), clamped to [`gridWindowRows`, `gridMaxWindowRows`], sampled once per result-set identity. Defaults unchanged (fixed/50) — the knob exists for QO-9b sweeps and dogfood, not a behavior flip.

**Verification:** both typechecks + lint green; full suite **4343 passing / 2 failing** (pre-existing pair; the CopilotChatEntry flake didn't fire this run).

**QO-7 remaining, moved to a follow-up batch (QO-7b):** column projection for wide grids (QsGetRows columnStart/columnCount + RowStore projection + windowed-source column awareness), host-computed display flags (null/truncated/xml/json bitsets), bounded autosize sampling knob wiring, velocity-aware prefetch. Rationale: each needs grid-internals surgery best done against QO-9b spread data for the wide shape (baseline 3.1–4.6 s is the target evidence).

Status: remaining batches — QO-4 (large-cell streaming), QO-5 (compact rows wire), QO-7b (column projection et al.), QO-8 (export/text/cell-docs/plans), QO-9b (spread matrix + defaults).

---

## Entry 8 — QO-4 COMPLETE: large-cell streaming, ~2.5× on the huge-cell shape (2026-07-09)

**Commit:** sqltoolsservice `56665ea4` (STS2: stream large cells in the SqlClient driver). Report entry prepended.

**Built:** `CommandBehavior.SequentialAccess`; new `SqlLargeValueReader` streams MAX-typed columns (xml, text/ntext, image, (n)varchar/varbinary/json at MAX) in fixed chunks — stateful UTF-8 encoder so surrogate pairs split across chunks hash/count correctly; within-bound values arrive as ordinary CLR values, oversized as new `DriverTruncatedValue` (bounded prefix + full bytes + streaming sha256; peak per-cell memory = prefix + one chunk). `QueryExecuteRequest.MaxCellBytes` (additive, PublicAPI updated, journaled args). `WireValueEncoder` emits the §7.7 wrapper verbatim from driver facts (bytes long-safe) and re-caps only the prefix. **Digest semantics unchanged — no SPEC-CHANGE; digestPolicy stays a future knob gated on QO-9b data.**

**Measured live:** `querystudio-query-large-cells` **3.98–4.32 s → 1.53–1.79 s (~2.5×)** (run `2026-07-09T21-01-40Z_9c41f3c9`); `querystudio-query-blob` (within-bound path, complete values) 4/4 green ~0.55 s (run `2026-07-09T21-04-09Z_8496c2cc`). verify.sh --quick green; 293/293 quick unit; encoder test covers wrapper-verbatim/multi-byte re-cap/binary cap.

**Cumulative shape scoreboard (baseline → now):** 10k messages 4.9–6.4 s → **1.29–1.58 s (~4×)**; ~1 MiB cells 3.98–4.32 s → **1.53–1.79 s (~2.5×)**; 100 result sets **300 s deadlock → 0.6 s** (D-0015); 100k narrow ~1.2–2.0 s (neutral); wide 1000×300 3.1–4.6 s → 3.1–3.2 s (tightened; QO-7b/QO-9b target).

Status: remaining — QO-5 (compact rows wire), QO-7b (column projection), QO-8 (secondary features), QO-9b (spread matrix + defaults report).

---

## Entry 9 — QO-5 COMPLETE: compact rows on the wire (2026-07-09)

**Commits:** sqltoolsservice `d9aca04e` (STS2: compact row pages on the wire, opt-in per query, D-0016), vscode-mssql `514307730` (Consume compact STS2 row pages and drop the client-side page rebuild).

**Built:** `options.compactRows=true` (journaled queryStart arg) → runner emits `compact:{values,nullBitmap,typeHints}` + `approxBytes`/`encodedBytes` (bitmap byte-identical to the client's LSB-first layout; type hints ONCE per result set with the client's exact taxonomy — parity documented on both sides); reducer routes by payload shape (no Core state; legacy byte-for-byte). Extension opts in when negotiated, consumes wire facts with an in-place null-normalization pass, and **deletes the per-page rebuild + `JSON.stringify(rows).length`** from the hot path (legacy fallback retained + tested). Capability `compactRows`; SPEC §7.3/§7.5 + D-0016.

**Verification:** verify.sh --quick green ×2; STS2 quick 294/294 (new CompactRowsOptInSwitchesTheWireShape pins both shapes); binding conformance 23/23 (compact consume + opt-in gating); full suite 4342/3-pre-existing. Live 100k-narrow on the compact wire green (run `2026-07-09T21-37-04Z_8125d6af`); **wallclock neutral at 4 reps — honestly recorded**: the binding CPU/allocation reduction needs QO-9b distributions/ext-host profiles, not 4-rep wallclock. Mid-batch slip caught by the suite: a 4-quote raw-string delimiter ate `"compact"`'s leading quote (35 failures) — multi-line raw strings fix; lesson recorded.

Status: QO-9b next (spread factory + matrix + tuning report) — QO-8 and QO-7b remain after.

---

## Entry 10 — QO-9b spread matrix run + defaults validated (2026-07-09)

**Commit:** perftest `9e7b495` (core: QO-9b QueryTuning spread matrix). Matrix run `2026-07-09T21-41-37Z_e940dd33`, 28/28 reps green.

**Analysis (wallclock ranges, 4 reps/point, vs default-knob runs on the same tree):**

| Shape | Axis point | Result | Verdict vs default |
|---|---|---|---|
| 100k narrow (def 1.64–2.21 s) | pageRows 128 | 1.75–2.41 s | worse — page/ack overhead |
| | pageRows 512 | 1.53–2.12 s | ≈ default (noise) |
| | pageBytes 64 KiB | 1.72–2.33 s | ≈/slightly worse — byte-split page count |
| wide 1000×300 (def 3.12–3.20 s) | pageRows 128 | 3.15–4.46 s | worse/noisy — overhead × 300 cols |
| | gridWindowRows 200 | 3.12–3.28 s | neutral (first-render fetches one window regardless) |
| | adaptive windows | 3.13–4.68 s | neutral + one outlier |
| large cells (def 1.53–1.79 s) | maxCellBytes 64 KiB | 1.51–1.79 s | equal — QO-4 streaming already pays the drain; smaller display bound buys nothing at 20 rows |

**Defaults decision (quantitative):** keep `pageRows` 1000 / `pageBytes` 256 KiB / `maxCellBytes` 1 MiB / fixed 50-row grid window — smaller pages measurably hurt or wash out; the one data-justified default change of the effort remains `messagesNotifyIntervalMs` 0→50 (Entry 6, ~4× shape win). All knobs stay sweepable for future hardware/scenario profiles.

**Honest residuals:** wallclock-to-first-render doesn't exercise the SCROLL path where window sizing matters — a scroll step in the driver is the follow-up that makes w200/adaptive measurable; binding CPU deltas (QO-5) need ext-host profile collectors on a diagnostic pass; cell64k equality suggests the next large-cell win is skipping the digest drain (`digestPolicy`, deferred D-question).

**REMAINING BATCHES (next session start here):** QO-8 (streaming export + text-view thresholds + cell-doc/plan safety — no scenario coverage yet, add with it), QO-7b (column projection + host display flags + scroll-step scenario), then promotion/defaults review (plan §R8): baseline accrual, official-metric decisions, public-vs-internal settings.

---

## Entry 11 — QO-8 COMPLETE: secondary features large-result-safe (2026-07-09)

**Commits:** perftest `9ec7241` (core: register export/textView/plan markers), vscode-mssql `8d4771a28` (Make Query Studio secondary features large-result-safe).

**Built:**
- **Export streams to disk** (QO-8 §1): format generators (csv/json/insert) yield bounded pieces → incremental `fs.WriteStream` writes (~256 KB buffers) with a cancellable progress notification; cancel deletes the partial file; non-file targets keep bounded in-memory assembly through the same generators. `export.begin/end` markers (rows/bytes/canceled/streamed); chunk size from `exportChunkRows` tuning. Output byte-format preserved (headers/quoting/batching identical to the old builders).
- **Text view capped honestly**: materialization stops at `textViewMaxRows` (tuning, ridden on gridStyle) with a VISIBLE "…display truncated at N of M rows" line + `textView.capped` mark; column widths from `textViewSampleRows` sample instead of every row.
- **Cell documents raw-first** above `cellDocumentFormatLimit` — no synchronous pretty-print of multi-megabyte XML/JSON (language highlighting kept; Format Document available on demand).
- **Plan parse cache** keyed by plan-XML identity — tab switches/state pushes stop reparsing; `plan.parse` marker with cacheHit/ms.
- New unit tests: 4 export-piece tests (bounded streaming, JSON validity across chunks, INSERT termination, selection bounds).

**Verification:** contracts 27/27 + vendor-sync green; full suite **4346 passing / 3 failing** (same pre-existing set); perftest workspace green except the known central-store env failure.

**Residuals:** export/text live scenarios still blocked on Save-dialog automation (journaled since QO-9a); the export progress notification's cancel path is unit-covered at the generator level and needs one manual dogfood pass.

Status: QO-7b is the LAST batch (column projection, host display flags, bounded autosize wiring, scroll-step scenario) — then plan §R8 promotion review.

---

## Entry 12 — QO-7b COMPLETE (protocol layer): ALL PLANNED BATCHES LANDED (2026-07-09)

**Commit:** vscode-mssql `ebf163cbc` (Add Query Studio column projection and bounded autosize sampling).

**Built:** `QsGetRows` accepts `columnStart`/`columnCount`; RowStore serves horizontally projected windows (values/columns/typeHints/null bitmap all projected; window cache keyed by span; clamping honest; full-width unchanged — new projection unit test covers span metadata, projected bitmap bits, clamping, and cache identity). **Wide-grid copy uses projection immediately**: a 3-column selection from a 300-column grid no longer serializes the other 297 columns per chunk. FluentResultGrid autosize data sample = `autosizeSampleRows` prop from the tuning snapshot (rides gridStyle like the window knobs). Also fixed NUL-byte separators that had crept into rowStore's cache keys (file read as binary by tools; keys now `:`-separated).

**Verification:** both typechecks + lint green; full suite **4350 passing / 2 failing** (pre-existing pair). 

**Deliberately deferred (recorded, not forgotten):** grid-internal VIEWPORT column projection + velocity prefetch + host display-flag bitsets need the shared data view re-keyed by row+column windows (touches classic-editor-shared internals) and a driver scroll step so the win is measurable — that trio is one coherent follow-up work order with the scroll scenario as its acceptance gate.

## Entry 13 — Untitled Save-As continuity + .mssql extension (2026-07-09, dogfood-driven)

**Commits:** vscode-mssql `7f143b55c`, perftest `d747d6c` (saveAs.adopted event registration). Karl's testing found: saving an untitled QS document demoted to the plain text editor (VS Code opens the saved file in the DEFAULT editor; QS is deliberately priority "option" for .sql).

**Built:** (1) `.mssql` = QS-first extension — sql language association + QS selector + a `workbench.editorAssociations` `*.mssql → mssql.queryStudio` default written once on QS activation (never overwrites a user choice; the Configure-Default-Editor mechanism). Untitled → save as `.mssql` stays QS natively; `.mssql` files open straight into QS; flipping `.sql` later is a one-line association. (2) Save-As continuity watcher: untitled QS custom tab closes → `.sql`/`.mssql` file tab opens in the SAME tab group within 1.5 s → adopted back into QS via openWith, with the session's profile/database handed to the adopted document through the open-context path (work continues on the same connection). Narrow same-group window prevents hijacking unrelated opens after a discard. `queryStudio.saveAs.adopted` diag registered (extension/reopened/withConnection).

**Verification:** contracts 27/27 + vendor-sync green; full suite 4347/3-pre-existing. **Manual validation checklist for Karl:** untitled→save `.mssql` (stays QS + connected), untitled→save `.sql` (brief flash, adopted back + connected), discard untitled then open unrelated `.sql` (must NOT hijack), double-click `.mssql` (opens QS directly).

## Entry 14 — Wire-wrapper display fix + SSMS-density UX pass (2026-07-09, dogfood-driven)

**Commit:** vscode-mssql (see git). Karl's side-by-side vs SSMS (screens/ssms-databases.png vs vscode-databases.png) found two classes of problems: (1) **correctness** — typed wire wrappers (`{"$t":"datetime2","v":...}`, binary, decimal…) rendered as raw JSON, got sniffed as JSON links, and blew every column to the 400px autosize cap (~4 columns visible vs ~15 in SSMS); (2) **density** — 14px inherited editor font, 12px base row chrome, 400px width cap.

**Built:** (1) shared `$t`-wrapper decoder in `queryStudioGridOps.cellDisplayText` — datetime2/datetimeoffset → `2003-04-08 09:13:36.390` (T→space, fraction trimmed to a 3-digit floor, offset kept for dtoffset), binary → `0x…` uppercase hex from base64 (pure JS, 256-byte display cap + ellipsis), time/decimal/guid/double/provider → invariant `v`. `cellDocumentText` (exports/cell docs/copy) delegates to it; `cellDocumentLanguage` stops false-JSON automatically. Sorting: numeric compare goes through display text (decimal wrappers were `[object Object]` → NaN) and the numeric hint now accepts `number:approx` (bigint/decimal/money). (2) Density: grid default font 12px (no longer inherits editor.fontSize; `mssql.resultsFontSize` still wins), BASE_ROW_PADDING 12→6 (24→18px rows at defaults; `mssql.resultsGrid.rowPadding` raises it), new `gridMaxColumnWidthPx` tuning param (default 260, range 80–4000, grid group tail — digest changes) threaded QUERY_TUNING_SPEC → QsGridStyle → controller stamp → `autosizeMaxColumnWidth` FluentResultGrid prop (classic grid keeps its 400 default). Cell ellipsis CSS already present (`grid-cell-value-container`).

**Verification:** both tsgo typechecks clean; gridOps/cellDocument/gridStyle/tuning suites green (33+9+10+12); full unit suite = only the 3 known pre-existing failures. **Manual validation for Karl:** AdventureWorks-style wide table — dates/GUIDs/binary render as values (no JSON links), ~2× more columns/rows on screen, long text ellipsizes at 260px, `tuning.overrides {"gridMaxColumnWidthPx": 600}` widens live.

## Entry 15 — Split/font density round 2 + Save As transplant (2026-07-09, dogfood-driven)

**Commit:** vscode-mssql `e8ecf79c3`. Karl round-2 feedback (screens/ssms2.png, vscode2.png, sidebyside.png + save repro): (1) editor/results split off vs SSMS's ~50/50; (2) columns still wide — sidebyside proved the grid inherits the MONOSPACE editor font while SSMS uses the proportional UI font (~2× width for identical text); (3) Save As broken two ways: untitled QS tab ORPHANED on save (VS Code never closes custom-editor tabs during untitled Save As → session-diag showed ZERO tab-close events → Entry-13's tab-watcher can never fire; dead editor + stranded grid), and titled Save As (file.mssql → file2.mssql) lost connection+results (fresh model under the new URI).

**Built:** (1) split default 50/50 via `mssql.queryStudio.resultsPaneHeightPercent` (15–80, default 50) riding QsGridStyle; splitter drag wins per session (splitAdjustedRef); reset-split restores the configured value. (2) grid fontFamily fallback `--vscode-editor-font-family` → `--vscode-font-family` (resultsGrid only; text view stays monospace for column alignment; `mssql.resultsFontFamily` still overrides). (3) Save As continuity v2 — **document-save keyed, model transplant**: `onDidSaveTextDocument(file .sql/.mssql)` that is NOT an open QS doc but content-matches a live model (EOL/trailing-normalized) ⇒ register `pendingModelTransplants[targetUri] = model` (5 s expiry) + fallback `pendingOpenContexts`; 200 ms later ensure target open in QS (`openWith` unless a QS tab appeared natively) and close orphaned source tabs. `resolveCustomTextEditor` consumes the transplant: `model.adoptSavedDocument(doc)` re-keys uriKey (now mutable behind getter) + rebind, registries re-keyed, panel-dispose closure now decrements by model identity at its CURRENT key (zombie panel of a transplanted model decrements correctly; no leak, no double-dispose). Transplanted models skip applyOpenContext (never reconnect over the live session).

**Verification:** both typechecks clean, full unit suite = 3 known pre-existing only. **Manual validation for Karl:** untitled → Save As `.sql` and `.mssql` (tab becomes the file in QS, connection + results intact, no zombie tab), `file.mssql` → Save As `file2.mssql` (same), plain Save of open QS file (no adoption), save a COPY of an open doc's content from another editor (should not steal the session unless content matches — known heuristic edge for identical-content docs).

## Entry 16 — Modifier-click selection + union copy + bit 0/1 + header ellipsis (2026-07-09, dogfood round 3)

**Commit:** vscode-mssql `16981858a`. Karl round-3 (sidebyside2.png): shift/ctrl-click cell selection missing; bit shows true/false vs SSMS 0/1; clipped headers don't ellipsize.

**Built:** (1) `FluentResultGridSelectionModel` cell-mode modifier clicks (base SlickHybridSelectionModel only has them for ROW mode): plain click collapses to the clicked cell; shift-click = box from active anchor (activation suppressed → anchor survives repeated shift-clicks); ctrl-click = toggle cell into irregular multi-range (preserveRangesOnActiveCellChange flag defeats the base reset — onActiveCellChanged fires UNCONDITIONALLY per SlickGrid #329); ctrl+shift = add box. CRITICAL companion: commandController.handleClick (slickgrid-react onClick, runs BEFORE the model's grid.onClick subscription) now returns early on modifier clicks — it was setActiveCell+selectRange(single), destroying the anchor/ranges before the model saw the click. (2) copySelectionAsTsv multi-range = SSMS union semantics: union rows × union cols, unselected intersections emit "", headers = union columns, fetched per contiguous row-run over the union col-span; single-range fast path unchanged; copyHeaders unions too. (3) `typeof value === "boolean"` → "1"/"0" in cellDisplayText (bit rides the wire as JSON bool per WireValueEncoder line 93) — flows to grid/text/copy/export/cell docs. (4) header ellipsis: `.slick-header-with-filter .slick-column-name` was display:flex — text-overflow CANNOT ellipsize text inside a flex container (anonymous box), so headers hard-clipped; display:block restores "…", parent flex still centers. Pure CSS, zero measurement cost.

**Verification:** typechecks clean; gridOps 34/cellDocument 9 green (new: bit 0/1 both files); full suite = 3 known pre-existing. **Manual for Karl:** shift-click box, ctrl-click scatter → copy → paste in Excel/editor (coherent table, blanks at gaps, right headers), plain click collapses, shift-arrows still extend, select-column/row commands still work, headers show "…".

### PLAN COMPLETE — R8 promotion review is the remaining standing item
All QO batches (1–9) have landed with green gates. R8 checklist for the review pass: (1) baseline accrual on the new shapes → promote `querystudio-query-*` maturity + consider official metrics beyond wallclock (toRender candidates); (2) decide public vs internal for `mssql.queryStudio.tuning.*` (currently profile public, overrides preview); (3) manual dogfood ledger: export cancel path, text-view cap UX, plan-tab cache behavior, adaptive-window feel on big monitors; (4) the deferred trio above; (5) digestPolicy wire option if large-cell profiling justifies it; (6) Debug Console tuning page (params/store/replay are ready).

## Entry 17 — Dogfood round 4: editor menu, Disconnect, selection round follow-ups (2026-07-09)

**Commits:** `9a2dd8acf` (this entry), plus `e168c7697` (ls: structural
diagnostics — journaled in language-service-docs Entry 8) and `04dbe8fbf`
(oe: Script as Execute — journaled in oe-docs Entry 9), all from Karl's
round-4 feedback. QS bits here: (1) Monaco "Go to Symbol" filtered from
the Query Studio editor context menu via the contextmenu contribution's
_getMenuActions seam (no public API exists for removing built-in items).
(2) Change button is now a split button — chevron opens a compact
connection menu with Disconnect (qs/disconnect handler already existed);
same qs-db-wrap/menu pattern + outside-click close as the database picker.
