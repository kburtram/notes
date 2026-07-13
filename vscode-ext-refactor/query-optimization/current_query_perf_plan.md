# Query Studio current performance plan

**Status:** Active execution plan  
**Last updated:** 2026-07-13  
**Scope:** `vscode-mssql` (`dev`), `sqltoolsservice` (`query`), and `perftest` (`dev`)  
**Primary objective:** Make Query Studio predictably fast and memory-efficient from query submission through rendering and interaction, without weakening correctness, cancellation, backpressure, or diagnostic quality.

This document is the current source of truth for the next optimization cycle. It records the architecture and evidence found in the July 12 investigation, reconciles the earlier optimization and bootstrap plans, defines the missing measurements and workload matrix, and sequences implementation so each optimization is justified by comparable measurements.

## Executive assessment

The current implementation already has a strong foundation:

- STS v2 streams sequentially with credits instead of materializing the complete result.
- The extension uses compact row pages, an asynchronous spill store, page/window caches, capped text documents, and streaming export.
- Query Studio lazy-loads the grid and custom result panes, defers offscreen result grids, virtualizes visible messages, and exposes tuning profiles.
- The performance harness covers the main process boundaries and has reusable workload generation, process sampling, an exact Query Studio webview CPU profiler, an honestly scoped workbench renderer trace, .NET traces/counters, heap captures, and scenario spread support.
- Earlier work measured substantial gains for messages, large cells, compact rows, spill/cache behavior, and bootstrap.

The largest remaining risk is no longer one obviously synchronous operation. It is cumulative amplification across boundaries: the driver creates boxed row arrays; STS builds JSON DOM values and strings; the extension parses and projects them, tracks repeated aggregate state, and materializes rich cells; the webview retains grids and custom panes; and the UI performs several unbounded interaction operations. Current terminal/render timings do not exercise enough interaction or retain enough memory evidence to attribute that amplification.

The next cycle therefore starts by making page, state, cache, render, tab, and interaction costs observable and by making the scenario runner drive the real result surface. Optimizations will then proceed in measured waves, with correctness and resource gates at every checkpoint.

## User-visible correctness regression found during the audit

### PERF-CORRECTNESS-001: a fast result could leave an empty Messages tab selected

Observed with a one-result query in the supplied session diagnostic trace. The run completed in 78 ms, before the webview's first row-window request:

| Event | Relative time |
| --- | ---: |
| query submitted | 0 ms |
| first result | 75 ms |
| query complete, 1 result set / 11 rows / 0 errors | 78 ms |
| webview reported results rendered | 192 ms |
| first row-window request | 259 ms |

There were two adjacent races. First, the view reset depended on observing transient `executing`; a debounced push could skip directly to terminal and preserve the prior Messages selection. `fc41565f7` keyed reset to a genuinely new run generation. Second, the lower-latency `QsRunStarted` notification could reset Results before coarse state caught up; eligibility then evaluated the stale idle/terminal state and immediately moved back to Messages. `8524c6572` treats that notification-to-state interval as executing for eligibility.

- Fixes: `vscode-mssql` `fc41565f7` (`qs: keep fast query results focused`) and `8524c6572` (`fix: keep first query results focused`)
- Coverage: terminal-only generation changes, same-generation renderer recreation, and notification-before-state eligibility
- Direct post-paint observability: `resultsRendered.activeTab` is a registered safe enum sampled after the actual paint
- E2E regression: `perftest` `730fbf3` runs both the first readiness `SELECT 1` and measured `SELECT 100`; each must render one row / one result set with `activeTab=results`
- Live validation: `2026-07-13T19-15-16Z_0bea9db9` passed 4/4; all eight renders reported Results and no run-time eligibility transition targeted Messages

## Current architecture and cost centers

| Stage | Current design | Strength | Current performance risk |
| --- | --- | --- | --- |
| SQL driver read | `SequentialAccess`, paged `object[]` rows, MAX-value streaming | Bounded forward read and correct large-value handling | Boxing and per-row arrays; limited type/size attribution; estimated page bytes are approximate |
| STS page encode | `SqlRowsPageBuilder` plus `JsonArray`/`JsonNode`, JSON strings, full event construction | Compact protocol and measured encoded bytes | Multiple object graphs, UTF-16/UTF-8 conversions, null rescan, event parse/serialize copies |
| STS transport | credit-based query stream through coordinator/journal/RPC | Backpressure and replayability | Queue/journal/write stages and complete frame bytes are not separately measured |
| Extension ingest | protocol projection, compact page append, notifications | Low-latency streaming, backend abstraction | A per-cell null-to-`undefined` pass remains; repeated page/value projection is not yet fully attributed |
| Row store | async spill, page cache, decoded-window cache, projection support | Bounded page retention and fast repeat reads | Spill JSON re-encoding, synchronous one-time filesystem calls, untracked window-cache bytes, approximate heap accounting, allocation-heavy materialization |
| State delivery | coarse state plus row/message notifications; incremental row/column/error/plan counters and a stable ordered summary index | Separates metadata from row payloads and makes aggregate maintenance O(delta) | result metadata is still serialized repeatedly; notification/catch-up cadence and payload application need deeper attribution |
| Grid window fetch | viewport-adaptive row windows plus opt-in horizontal projection for schemas with at least 64 columns; stable data-source identity, independent length updates, and stale-response suppression | Browsing scales with visible + overscan columns while transforms/explicit autosize retain full-row reads | no velocity-aware prefetch/cancellation; distant frozen/active dependencies can correctly force a wider contiguous span; rich cell objects are created eagerly |
| Grid render | SlickGrid with lazy chunk and deferred offscreen result grids | Mature virtualization, actual render/paint markers, linear header initialization, viewport-only header controls, and sparse source-ordinal rows | mounted grids accumulate after scrolling; all header cells still exist; rapid horizontal jumps now pay a small projected RPC latency instead of retaining every column |
| Tab/custom panes | result pane registry, lazy Vector/Spatial/plan chunks, preserve mounted tabs | Responsive first activation and pane state retention | app rendering remains pane-specific; all opened panes and their data stay mounted; tab eligibility scans repeat on row updates |
| Messages | coalesced positioned notifications, bounded count/character catch-up windows, incremental height offsets, and virtualized visible DOM | Restore/catch-up and display indexing are bounded or O(delta) | copy-all remains one large string; sustained 100k-message/reverse-scroll/filter coverage is incomplete |
| Interaction | grid selection/copy/export/text document flows | Selection and copy use interval plans, projected bounded windows, cell/character guards, and real 100k-row regression scenarios | admitted grid copies are not yet cancellable; export/text/large-value interaction coverage is still incomplete |
| Bootstrap | staged editor/grid/custom chunks and module preload | Warm open and editor readiness improved substantially | static closure is close to chunk/CSS budgets; Monaco dominates; optional pane CSS is in the startup closure; cold spawn variance lacks attribution |

## Evidence captured before new changes

### Bootstrap/bundle snapshot

The current Query Studio static closure contains 19 chunks and approximately 10.20 MiB of JavaScript source in the esbuild metadata. The current ceilings are fewer than 20 chunks and 11.5 MiB, leaving only one chunk of structural headroom. The entry JavaScript is approximately 2.36 MB and entry CSS approximately 528 KB; the CSS ceiling is 560 KiB.

The dominant package is `monaco-editor` at approximately 7.41 MB of the static closure. Optional Vector, Spatial, pipeline, and search CSS are currently imported through the Query Studio entry, so feature-lazy JavaScript does not imply feature-lazy CSS.

Earlier measured bootstrap results remain the comparison baseline until refreshed:

- static closure reduced from roughly 14.3 MB to roughly 10.4 MB in the earlier bootstrap pass;
- warm open was roughly 87 ms in the documented run;
- real-grid autorun was roughly 876–990 ms in representative warm runs;
- a cold process-spawn outlier was roughly 5.3 s.

### Coverage snapshot

The current perftest suite has generated scenarios for open/autorun, 10k rows, 100k narrow rows, 1,000 × 300 wide rows, large cells, 10k messages, 100 result sets, Vector, Spatial, and tuning-profile spreads. Semantic scenarios now exercise middle/end scrolling, horizontal scrolling, result-stack traversal, tab activation, a host-settled 100k-row select-all, and a real 100k-row copy through the Clipboard API. They still do not systematically cover tab reopen, retained pane memory, sparse/large-value copy, result-set revisit/accumulation, resize/autosize, filter/sort, forced spill, cancel, export, or generated text/cell documents.

The diagnostic infrastructure can capture extension-host CPU profiles, exact Query Studio webview CPU profiles, workbench renderer-process traces, .NET trace/counters, process samples, heap snapshots, and gcdumps. The profiler discovers only MSSQL-owned iframe targets and proves Query Studio identity with a product DOM sentinel. A two-phase control handshake arms collectors before `scenario.start` and flushes them at `scenario.end` before editor cleanup. Renderer heap capture and renderer identity in normal process sampling remain incomplete.

## Detailed findings register

Priority meanings: **P0** blocks trustworthy optimization or can freeze/corrupt normal work; **P1** is a likely high-value hotspot or major coverage gap; **P2** is useful after measured higher-priority work.

| ID | Pri | Finding | Evidence / consequence | Planned disposition |
| --- | --- | --- | --- | --- |
| QPF-001 | P0 | Scenario terminal timings omit realistic result interaction | Existing query scenarios finish without scrolling or tab/copy flows | Add typed Query Studio actions and settled markers |
| QPF-002 | P0 | Grid render-complete measurement could detach when a live SlickGrid swapped data views | Resolved by existing `grid.render.complete` / next-paint markers plus `c2b177254`: live grid observers survive data-view swaps and the replacement view reattaches to the retained grid | Keep all-rep render/paint presence as a scenario oracle and add explicit data-applied/settled attribution |
| QPF-003 | P0 | Renderer/webview heap and long-task ownership are incomplete | Exact webview CPU and post-paint heap/long-task health now exist; process sampler still excludes renderer and heap is coarse | Register renderer identity; add renderer heap capture and tighter marker/profile correlation |
| QPF-004 | P0 | Large selection summary traversed every selected row | Resolved by `61a442d5a`: inclusive ranges are merged in O(R log R), with warmed-state select-all coverage | Keep the 100k scenario and interval-unit boundary cases as regression gates |
| QPF-005 | P0 | Multi-range copy was bounded by rows, not cells/bytes | Resolved by `37396c3c4` + `83e017b`: interval planning rejects before expansion, sparse projections/chunking bound decoded work, cell/character/range budgets show existing feedback, and a real 100k copy is a regression gate | Keep cardinality/payload/long-task oracles; cancellation is tracked separately in QPF-031 |
| QPF-006 | P1 | Grid requested all columns even though the row store supported projection | Resolved by `c2b177254` + `7223a79`: wide viewport reads use a reusable contiguous band with frozen/always-rendered/active dependencies; full-row operations omit projection | Keep the 300-column no-automatic-full-read oracle; extend to 1,000 columns, resize/reorder/freeze, rapid sweep, and explicit autosize/sort/filter |
| QPF-007 | P1 | Grid data source identity could have followed live row count | Resolved by audit: the windowed source lives in a ref, the data-view memo excludes it, result identity excludes `rowCount`, and `setLength` updates independently | Keep this design invariant in controller coverage; no product change was needed |
| QPF-008 | P1 | Rich cell values and content sniffing are eager | Every fetched visible-window cell gets a `DbCellValue` and display/language work | Delay large/special-value decoration and cache immutable formatting metadata |
| QPF-009 | P1 | Every result grid remains mounted once intersected | Deferred blocks never unmount after a long scroll | Virtualize result-set blocks and cap/warm-recycle grid instances |
| QPF-010 | P1 | Custom panes remain mounted after first activation | `mountedTabs` retains Vector/Spatial/plan state and caches | Define keep-warm budgets and dispose/recreate policies per pane |
| QPF-011 | P1 | Eligibility and metadata scans repeat with row notifications | derived result-set arrays are unstable; spatial eligibility depends on live row counts | Normalize immutable schema indexes and isolate row-count state |
| QPF-012 | P1 | Coarse state rebuild repeated aggregate scans and metadata arrays | Resolved by `d0eb49d63`: rows/columns/errors/plans are maintained incrementally and the ordered summary index grows O(1); tuning already governs the push interval | Keep state-build/payload markers and add a many-result-set state-stress scenario |
| QPF-013 | P1 | Message restore/catch-up protocol was cumulative | Resolved by `d0eb49d63` + `41541b1`: windows are capped at 2,048 rows / 1,000,000 text characters with absolute continuation/backlog metadata and registered timing | Extend the live matrix to force multi-window 100k-message catch-up |
| QPF-014 | P1 | Message height offsets were rebuilt for every coalesced update | Resolved by `d0eb49d63`: append-only updates extend the exact variable-height prefix index in O(delta); replacements rebuild once | Keep append/reset/multiline unit coverage and add reverse-scroll stress |
| QPF-015 | P1 | Row-store window cache is entry-bounded but not byte-bounded | Full cell windows duplicate decoded data; bytes are not part of memory caps | Track actual cache cost and evict by bytes plus entries |
| QPF-016 | P1 | Spill path serializes compact pages to JSON and parses them back | `JSON.stringify`/`JSON.parse` and UTF-8 conversion occur on the extension event loop | Store a pre-encoded frame or binary-safe owned payload after measuring compatibility |
| QPF-017 | P1 | Row-store memory estimates are wire-size estimates | Wire bytes can badly understate JS object/string overhead | Add retained-cost estimates, heap evidence, and safety margins by type |
| QPF-018 | P1 | STS encoding creates multiple representations of every page | JSON DOM, page string, event string, and parsed event coexist | Measure allocations and stage bytes, then move to direct UTF-8 writing/owned payloads |
| QPF-019 | P1 | Extension protocol projection still walks every cell | Null values are mutated to `undefined` in place | Remove or fuse the pass if contract tests prove null preservation is safe |
| QPF-020 | P1 | STS stage metrics end before coordinator/journal/RPC write | Current stats aggregate read/credit/encode and encoded bytes only | Add page-build, frame, enqueue/journal/write, queue, and allocation metrics |
| QPF-021 | P1 | Tons-of-results flows lack lifecycle and memory tests | 100-result scenario does not scroll through/mount/revisit results | Add mount sweep, return-to-first, memory plateau, and rerun tests |
| QPF-022 | P1 | Large-type coverage conflates materially different shapes | JSON/XML/binary/blob/vector and mixed nullable data have different encode/render paths | Add separate and mixed fixtures with compressible/incompressible values |
| QPF-023 | P1 | Query Studio has short timer-based interaction work | selection throttle and focus restore use short `setTimeout` calls | Replace with animation-frame/microtask scheduling and test hidden/revealed panels |
| QPF-024 | P2 | Adaptive row window samples pane height only during mount | resize/zoom and scroll velocity do not retune fetches | Feed resize/velocity signals into bounded prefetch policy |
| QPF-025 | P2 | Wide-schema keys stringify all column metadata during render | `JSON.stringify` is used as a column identity key | Use stable schema versions/digests produced once by the host |
| QPF-026 | P2 | Protected-cache byte accounting performs repeated reductions | promotion cost can grow with cache size | Maintain counters incrementally and cover invariants with stress tests |
| QPF-027 | P2 | One-time spill setup/cleanup uses synchronous filesystem calls | Small but visible extension-event-loop stalls under contention | Move lifecycle work async where disposal guarantees permit |
| QPF-028 | P2 | Optional pane CSS consumes startup budget | feature CSS is statically imported from Query Studio entry | Isolate feature CSS without flashes or theme regressions |
| QPF-029 | P2 | Monaco remains the dominant startup payload | namespace editor import retains a broad feature set | Spike a supported minimal editor API/features build and compare capabilities |
| QPF-030 | P2 | Result pane registry does not own rendering/lifecycle end to end | app still contains pane-specific eligibility and render blocks | Extend descriptors with loader, eligibility index, retention, and telemetry policy |
| QPF-031 | P1 | An admitted grid copy cannot be cancelled | Bounded copies no longer freeze or exhaust memory, but a user cannot abort projected fetch/TSV work after invoking copy | Thread an abort generation through projected requests/formatting and settle with a safe cancelled outcome |
| QPF-032 | P1 | Messages Copy All still creates one unbounded extension string | `buildMessagesText(getMessages().messages)` copies/formats the entire retained log before the clipboard request | Add character/count guards or a streamed/file-backed path, cancellation, and 100k variable-width coverage |
| QPF-033 | P0 | Live SlickGrid observers were torn down when React swapped a custom data view without recreating the grid | A timing-dependent wide run missed render/paint telemetry and could also lose keyboard/selection listeners after a schema-changing rerun | Resolved by `c2b177254`: lifecycle teardown now follows the grid lifetime and replacement data views reattach independently |

## Required observability contract

All new events must use aggregate, privacy-safe attributes only. SQL text, cell values, object names, connection identifiers, and filenames must never enter performance markers. Event names and schemas are registered before producers and consumers are added.

### Webview/bootstrap

- HTML created, provider start/end, preload emitted, navigation start, script fetch/evaluate, React commit.
- Monaco chunk requested/loaded, model created, editor ready, first input-ready.
- Grid chunk requested/loaded, grid instance created/disposed, data applied, render-complete, next paint, settled.
- Feature CSS/chunk requested/loaded and first feature render for plan, Vector, Spatial, and future custom tabs.
- Long-task count/total/maximum, event-loop/input delay where available, used JS heap where supported, React/grid/pane instance counts.

### Query/run lifecycle

- run generation observed, execution state transition, automatic tab decision, user tab activation, pane mount/reuse/dispose.
- submit-to-first metadata/page/terminal, terminal-to-first fetch, first fetch-to-data apply/render/paint/settled.
- result-set count, column count and safe shape buckets; never schema names.

### State and transport

- coarse-state build/send/receive/apply duration and approximate aggregate size/counts.
- row/message notification cadence, coalescing counts, queue depth, dropped/superseded updates.
- row-window request projection width, requested/returned rows and cells, payload bytes, cache outcome, spill outcome, materialization and RPC time.

### Caches and memory

- encoded page bytes, estimated retained bytes, resident/spilled page counts.
- page/window cache bytes, entries, hits, misses by aggregate reason, promotions, evictions, peak values.
- custom-pane retained row/feature/cache counts and disposal outcome.
- heap/process samples at post-terminal, post-interaction, post-return, post-rerun, and post-close checkpoints.

### STS/driver

- driver read, page build, credit wait, cell encode, null bitmap, page serialize, frame build, coordinator enqueue, journal, RPC/write durations.
- rows/cells, nulls, safe type-family counts, large-value counts/bytes, estimated and exact UTF-8 bytes.
- managed allocation delta when profiling is enabled; payload/frame sizes; queue/credit minima and peaks.
- totals plus count/min/max/percentiles or histograms for page stages, rather than averages alone.

### User interactions

- vertical/horizontal scroll action begin, target reached, data settled, long tasks and peak memory.
- tab activation begin/end/settled and mount/reuse outcome.
- selection summary, copy/export/text document, sort/filter/resize/autosize begin/end/cancel/failure with rows/cells/bytes only.

## Scenario matrix

Every canonical scenario has a correctness oracle, duration markers, process/heap samples, and a repeatable interaction script. Quick PR smoke uses reduced sizes; scheduled/local deep runs use the full sizes.

| Family | Shapes | Required interactions and assertions |
| --- | --- | --- |
| Bootstrap | cold/warm blank editor; cached/uncached grid; restored editor | editor input-ready, first execution, reveal/hide, reopen, bundle/long-task gates |
| Narrow rows | 10k, 100k, 1m+; nullable and mixed primitive | top/middle/end scroll, rapid reverse scroll, select ranges, rerun, bounded memory plateau |
| Wide rows | 100, 300, 1,000 columns with short and mixed cells | horizontal sweep, pinned/selected column fetch, autosize/resize, copy bounded region |
| Large values | JSON, XML, Unicode text, binary/blob, vector; 64 KiB through multi-MiB | visible preview, cell document, copy/export, cap behavior, cancel, incompressible and repeated values |
| Messages | 10k, 100k, mixed info/error and variable height | stream while executing, top/end/reverse scroll, filter, copy bounded/all, memory plateau |
| Result sets | 10, 100, 1,000 sets; mixed empty/result/message/plan | sweep all sets, return to first, grid instance cap, tab state, rerun cleanup |
| Many batches | sequential batches, errors between results, cancellation | stable ordering/status, partial results, cleanup and no stale updates |
| Custom tabs | plan, Vector, Spatial individually and together | first activation, pan/zoom/filter for Spatial, vector analysis, tab cycle, reopen, dispose/reclaim |
| Spill/cache | forced low thresholds, sequential/random/repeat access | checksum, hit/miss expectations, queue saturation, concurrent reads, cleanup/corruption behavior |
| Network/backpressure | localhost/Azure profiles, latency/throughput variation, slow consumer | credit bounds, no deadlock, one-page read-ahead bound, cancel responsiveness |
| Export/copy | visible, selection, full result, huge-cell cases | correct bytes/rows, bounded UI work, cancellation, output equality |
| Reliability soak | repeated execute/cancel/close, connection loss, renderer recreation | no leaked files/listeners/grids, stable memory, correct active tab and run isolation |

Initial size points are intentionally spread rather than only maximal: small enough to expose fixed overhead, around each threshold, and large enough to force steady-state/spill behavior. Scenario metadata records tuning digest, product commits, machine/load context, connection class, warm/cold state, repetitions, and raw artifact locations.

## Performance and reliability gates

Exact numeric budgets will be promoted from clean repeated baselines, but implementation uses these provisional rules immediately:

- No UI task over 50 ms at p95 during scroll/tab/copy interaction; investigate any single task over 200 ms.
- Query Studio input remains responsive while rows/messages stream; cancellation is acknowledged promptly and no producer exceeds the documented credit/read-ahead bound.
- Resident memory reaches a plateau determined by configured page, window, grid, and custom-pane budgets; it must not scale linearly with total rows or every result set visited.
- First visible results must not regress by more than 5% median or 10% p95 in a changed path without an explicit, documented tradeoff.
- Deep scenarios use at least five measured repetitions after warm-up; promotion requires stable distributions and retained raw artifacts.
- Bundle closure remains below 20 static chunks, 11.5 MiB source bytes, and 560 KiB entry CSS until a smaller measured budget is established.
- All performance changes preserve row order/value fidelity, null semantics, error/message ordering, cancellation, replay, export equality, accessibility, localization, theme behavior, and renderer recreation.

## Execution plan

Each wave follows the same loop: add the missing marker/oracle, run a clean baseline, implement one coherent optimization, repeat the same workload, inspect raw traces/heaps, run correctness tests, document the result, and commit the checkpoint. A change is kept only when the measured benefit or reliability simplification is clear.

### QP-0 — Establish truth and close known correctness regressions

**Status:** Complete — live user revalidation of the fast-query tab fix remains desirable

- Reconcile earlier optimization/bootstrap plans with current code and scenarios.
- Record bundle closure and test/collector capability.
- Preserve the supplied fast-query trace as numeric evidence only.
- Fix run-generation tab reset and add regression coverage (`fc41565f7`).
- Run a clean canonical baseline on current branch heads before hot-path changes.

**Exit:** this document is current; repos are clean at a checkpoint; fast terminal-only results select Results; baseline artifacts and run metadata are recorded.

### QP-1 — Instrument the complete path

**Status:** In progress — renderer/grid/tab, state/cache, STS page-stage attribution, and exact webview CPU profiling landed

- Register the event contract above in `perftest`.
- Add Query Studio run/tab/grid render/instance/health and state-push markers.
- Extend row-store statistics with byte-bounded cache/peak/outcome counters.
- Extend STS page statistics through frame enqueue/journal/write with opt-in allocation details.
- Normalize STS diagnostics into perftest reports and wire the unused renderer profiling option.
- Add contract tests for event schema, privacy classification, correlation, and balanced begin/end spans.

**Exit:** one report attributes submit-to-settled time and peak resources across driver, STS, extension, RPC, webview data apply, render, and paint.

### QP-2 — Make scenarios drive the real UI

**Status:** In progress — semantic tab, controller-driven grid/result-stack scroll, host-settled select-all/copy-all, and real baselines landed

- Add typed, performance-mode-only Query Studio actions for scroll, tab activation, result-set navigation, selection, copy, resize/autosize, filter/sort where supported, cancel, export, and reopen.
- Actions return only after a correlated product-level settled marker and correctness oracle.
- Add the scenario families above, quick/deep size profiles, deterministic fixtures, and failure diagnostics.
- Register and sample renderer identity; add renderer/webview heap checkpoints.

**Exit:** the harness reproduces interactive workloads without fragile screen coordinates and produces comparable artifacts for each data shape.

### QP-3 — Remove low-risk repeated work and unbounded interactions

**Status:** In progress — wide-grid repeated work, unbounded selection summaries, and unbounded grid copy landed

- Stabilize derived schema/result indexes and grid data-source identity.
- Incrementally maintain state/message/plan aggregates and honor the tuning state-push interval.
- Replace full selection enumeration with interval algebra; enforce copy cell/byte budgets (complete); add copy cancellation (QPF-031).
- Replace short timer scheduling with animation-frame/microtask mechanisms.
- Measure and remove/fuse the extension per-cell null projection pass if contract-safe.

**Exit:** large selection and wide/many-result streaming have no long synchronous tasks; output and selection semantics are unchanged.

### QP-4 — Optimize viewport fetching and rendering

**Status:** In progress — header controls and wide row transport are viewport-bounded; rich-cell reuse, adaptive prefetch, and superseded-request cancellation remain

- Send visible/frozen/always-rendered/active column projections to the row store (complete for contiguous windows).
- Add correctness-preserving fallback for operations needing full rows (complete for sort/filter, explicit autosize, and commands).
- Reuse decoded immutable cell/display data; defer large/special-value decoration.
- Tune row window and velocity-aware prefetch with superseded-request cancellation.
- Attribute actual SlickGrid data apply/render/paint and reduce layout/autosize churn.

**Exit:** wide-result transfer/materialization scales with visible columns during browsing; rapid scrolling remains smooth and bounded.

### QP-5 — Bound result-set and custom-pane lifecycle

- Virtualize long result-set lists and enforce a small grid keep-warm/recycle budget.
- Extend pane descriptors to own lazy loader, eligibility, retention, suspension, disposal, and telemetry.
- Give Vector/Spatial/plan caches explicit byte/feature budgets and active/inactive behavior.
- Verify state preservation where valuable and deterministic reconstruction elsewhere.

**Exit:** visiting 100/1,000 result sets or cycling custom tabs reaches a memory plateau and returns to prior locations correctly.

### QP-6 — Complete the message pipeline

- Replace cumulative message slices with bounded windows/deltas and backlog/version metadata.
- Grow height/offset indexes incrementally.
- Make filter/copy operations cancellable and byte-bounded; stream copy-all where the platform allows.
- Add message streaming/reverse-scroll/filter/copy scenarios through 100k messages.

**Exit:** sustained messages show near-linear total work, smooth scrolling, and bounded memory.

### QP-7 — Tighten row-store spill and cache memory

- Track page and window cache retained bytes and evict by byte plus entry budget.
- Replace JSON re-encode/parse spill with a measured pre-encoded representation.
- Cache decoded null/projection metadata where it wins; maintain cache counters incrementally.
- Add corruption, queue saturation, disposal-during-write, concurrent-read, fairness, and cleanup tests.

**Exit:** forced-spill workloads preserve checksums and responsiveness, keep the event loop clear, and stay within measured budgets.

### QP-8 — Reduce STS/transport allocation and copying

- Use new stage/allocation evidence to prioritize the dominant copies.
- Replace JSON DOM construction with direct `Utf8JsonWriter`/owned-buffer writing where compatible.
- Avoid page/event string and parse round-trips through coordinator/journal/RPC.
- Fuse null bitmap/type accounting into encoding and improve exact byte estimation.
- Preserve replay, diagnostics, credit semantics, cancellation, and wire compatibility with focused fault tests.

**Exit:** large/wide/large-value scenarios show lower allocated bytes and CPU per encoded byte with identical protocol behavior.

### QP-9 — Revisit bootstrap after steady-state wins

- Split truly optional feature CSS from the startup closure without flashes.
- Attribute cold provider/navigation/fetch/evaluate stages.
- Spike a supported minimal Monaco feature/API import and execute editor capability tests.
- Tighten bundle budgets only after repeated cold/warm validation.

**Exit:** lower cold/warm input-ready and first-grid cost with language/editor functionality intact.

### QP-10 — Promote defaults and lock reliability

- Run the full localhost and Azure matrix across tuning-profile spreads.
- Promote stable baselines/budgets and compare dashboards.
- Run repeated execute/cancel/close/renderer-recreate and failure-injection soaks.
- Reconcile docs, tuning digest policy, debug-console controls, and deferred work.

**Exit:** recommended defaults are evidence-based, CI/scheduled gates are actionable, soak memory is stable, and no open P0/P1 correctness issue remains.

## Test strategy by layer

### `vscode-mssql`

- Pure tests for run/tab decisions, schema indexes, interval selection, cache budgets, and tuning.
- Row-store randomized/property-style equivalence against an in-memory oracle, plus spill/fault/concurrency tests.
- Controller tests for notification coalescing, incremental aggregates, correlation, cancellation, and disposal.
- Webview component tests for grid lifecycle, actual render-settled markers, result-set virtualization, tab retention, message deltas, hidden/revealed scheduling, accessibility, localization, and themes.
- Extension integration tests that run Query Studio through real RPC and verify row/message/export/text results.

### `sqltoolsservice`

- Page-builder/encoder value fidelity for every SQL type family, null patterns, Unicode, JSON/XML/binary/vector, and large values.
- Allocation/copy and byte-accounting benchmarks separated from correctness tests.
- Credit, slow-consumer, cancellation, queue, journal/replay, connection-loss, and partial-result tests.
- Multi-batch/multi-result ordering and MAX-value streaming fault coverage.

### `perftest`

- Event registry/schema and collector lifecycle tests.
- Typed action correlation/timeout/settled contracts and deterministic fixture checksums.
- Process identity, renderer targeting, artifact retention, spread/repetition, baseline comparison, and regression explanation tests.
- Fast PR subset plus scheduled/local deep and soak profiles.

## Iteration and checkpoint policy

- Commit at coherent checkpoints, normally one instrumentation/scenario/optimization wave per repository.
- Never combine unexplained baseline movement with multiple independent hot-path changes.
- Keep raw diagnostic artifacts out of source control; record commands, scenario IDs, commits, machine context, and summarized numbers here or in `PROGRESS.md`.
- Revert or redesign optimizations that merely shift time/memory to an unmeasured process or weaken cancellation/backpressure.
- Correctness defects discovered during profiling are fixed with focused regression tests, then the same performance comparison is repeated.

## Investigation log

### 2026-07-12 — architecture, coverage, and observability audit

- Read and reconciled `query_optimization_plan.md`, `EXECUTION_PLAN.md`, `PROGRESS.md`, `QS_BOOTSTRAP_PERF_PLAN.md`, and bootstrap progress entries.
- Inspected Query Studio initialization, app/tab lifecycle, grid data source/materialization, messages renderer/host API, controller state delivery, row-store spill/cache, STS driver/page/encode/coordinator flow, central event registry, collectors, and generated scenarios.
- Calculated the current Query Studio static closure and package contributors from the esbuild metafile.
- Found the missing fast-terminal generation reset, confirmed it with the supplied 78 ms run trace, fixed it, and added focused tests.
- Established the findings register, observability contract, interaction workload matrix, gates, and QP-0 through QP-10 sequence above.

### 2026-07-12 — QP-1 renderer/extension/STS instrumentation checkpoint

- `vscode-mssql` `956d37fb8`: added distinct run observation, automatic/user tab activation through paint, live SlickGrid create/dispose counts, actual grid post-render completion, and moved first-visible-row paint behind the real grid render boundary.
- The same checkpoint measures coarse-state build/shape/perf-only payload size, honors `statePushMinIntervalMs`, and reports row-store resident/pending/window-cache bytes, peaks, entries, hits/misses, and evictions. Decoded-window retained-byte accounting has focused cache/eviction/corruption coverage.
- `perftest` `526d827`: registered/generated/vendored the privacy-safe contracts. Contract, correlation, parity, and vendor-sync suites passed.
- `sqltoolsservice` `88c6149b`: STS v2 now attributes row serialization, UTF-8 byte measurement, null bitmap, page body, event build, coordinator post build/wait, full event payload bytes/maximum, cell/null counts, and synchronous managed allocation deltas. All 331 STS2 unit tests passed.
- `perftest` `d6788ea`: `stsEnvelopeJournal` now normalizes `sts2.query.stats` into `sts2.query.pipeline.*` report metrics without correlation identifiers or content.

### 2026-07-12 — QP-2 semantic interaction checkpoint

- `vscode-mssql` `43e4883b6`: added a PERF_MODE-only closed interaction contract. It accepts result-set ordinals and semantic start/middle/end targets only; arbitrary selectors, pixels, SQL, identifiers, and values are unrepresentable and rejected by tests.
- Correlated tab actions wait through paint. Grid vertical actions wait for a real fresh grid render; horizontal actions wait through the following paint; result-stack sweeps wait for a newly created grid instance.
- Added exploratory scenarios for a 100k-row middle/end vertical sweep, a 1,000 × 300 horizontal sweep, and scrolling a 100-result-set stack to its end. Scenario conformance plus observability and STS-normalization tests passed (107 tests); focused product interaction tests passed (7 tests).
- Validation note: an unrestricted MSBuild test attempt triggered pathological worker fan-out and reached the environment timeout without compiler output. Re-running with `--disable-build-servers -m:1 -nodeReuse:false` compiled cleanly and completed the focused and full STS2 suites. Use the constrained form for repeatable local validation on this machine.

### 2026-07-12 — first real Query Studio baselines and interaction-seam correction

- Localhost runs used the provisioned `PerfHarness` database with integrated authentication, SQL Tools Service `net10.0` Debug bits, VS Code 1.128.0, warm SQL cache, one warm-up plus three measured repetitions, and raw artifacts under `perftest/perf-runs`. No credentials were written to source or artifacts.
- Query/render baseline `2026-07-13T00-57-24Z_4848ce6e` (`querystudio-query-100k-narrow`) passed 4/4. Wallclock values were 1402.5, 1554.6, 1528.8, and 1556.0 ms (median 1541.7 ms). Query completion in the first three normalized reps was approximately 1116.0, 1269.8, and 1235.6 ms; actual grid-render completion was approximately 1159, 1316, and 1282 ms. Webview heap peaked around 36–38 MB, the longest observed webview tasks were 69–127 ms, extension-host RSS was 375–383 MB, and STS RSS was 153–167 MB.
- The fourth query rep contained the required markers but initially lost its derived phase metrics. Root cause was asynchronous cross-process delivery: a preflight completion appeared after `scenario.start` in JSONL file order despite carrying an earlier event timestamp. `perftest` `8c15aac` now scopes and sorts measured markers by `timestampUnixNs`; the regression fixture reproduces that exact delivery order and all 9 focused normalizer tests pass.
- The first 100k interaction attempt (`2026-07-13T01-02-11Z_10b98259`) correctly failed 4/4: DOM `scrollTop` mutation reported `applied` but did not drive SlickGrid virtual paging, so the required fresh render marker timed out. This was an automation-seam defect, not accepted noise.
- `vscode-mssql` `a8333f6d6` adds bounded row/column navigation to `FluentResultGrid` and routes semantic PERF actions through the mounted product controller. The registry has replacement-safe disposal, retains the selector/coordinate-free external contract, and reports `applied` only when SlickGrid accepts the operation. Webview builds, lint, production bundles, and 8 focused PERF_MODE tests pass.
- Repaired 100k vertical sweep `2026-07-13T01-14-44Z_54119c86` passed 4/4. Wallclock values were 4499.6 ms for the warm-up and 863.6, 834.6, 811.6 ms measured (measured median 834.6 ms). Each middle/end jump caused a fresh 50-row/40-row window and actual render. Measured webview heap peaks were 34.2–39.1 MB; grid count stayed at one; extension-host RSS peaks were 383–387 MB; window fetches at the end were cache hits with one-page materialization and 0–1 ms host time.
- Wide horizontal sweep `2026-07-13T01-16-23Z_e918d5d3` passed 4/4 at 795.4–811.0 ms (all-rep median about 802.7 ms). It exposed the strongest immediate UI target: 2,600 DOM nodes and a 5.49–5.57 second longest-task peak while building the 300-column result surface, despite horizontal interactions themselves completing promptly. Webview heap peaked at 37.8–44.5 MB and extension-host RSS at 353–381 MB.
- 100-result-set end sweep `2026-07-13T01-17-42Z_d703ee76` passed 4/4 at 603.1–626.2 ms (median about 609.8 ms). Lazy mounting capped live grids at 10 rather than 100, but the view still reached 2,597 DOM nodes and 138–179 ms long tasks; webview heap peaked at 40.7–48.0 MB and extension-host RSS at 379–386 MB. This validates the lifecycle design direction while quantifying the remaining grid/DOM budget work.
- These baselines promote wide-column initialization/layout as the first measured QP-3/QP-4 optimization target. The 100-result-set lifecycle is the next retention/virtualization target; the 100k vertical data/window path is currently bounded and serves as a regression control.

### 2026-07-13 — wide-grid initialization optimization

- The original 1,000 × 300 trace showed an accidental O(C²) header path: each of 300 header-render callbacks scanned all columns and queried both action buttons. `vscode-mssql` `9f4290310` changed initial header-state application to O(1) per header while retaining the full scan only for real filter/sort changes. Identical live reps dropped the longest task from 5,487–5,569 ms to 299–315 ms, approximately a 94% reduction.
- The follow-up profile showed redundant frozen-option/layout application, full `setColumns` header reconstruction after width-only autosize, and per-button listeners. `vscode-mssql` `6b9015d` skips already-applied frozen options, mutates column widths through SlickGrid's supported `reRenderColumns` path without replacing column identity, skips inactive restore-state scans, delegates header actions once per grid, and materializes sort/filter buttons only for headers intersecting the horizontal viewport. Offscreen controls are removed and recreated with current active state when panned back into view; environments without `IntersectionObserver` retain the full-control fallback.
- Identical four-rep interaction run `2026-07-13T16-01-36Z_f03f9667` passed every semantic horizontal/selection/scroll oracle. Longest tasks were 143, 122, 226, and 244 ms (183.8 ms average), versus 252 ms immediately before viewport materialization and about 5,549 ms before the two wide-grid checkpoints. Final DOM counts were 2,258, 2,258, 2,002, and 2,012 (2,132.5 average), down from a stable 2,600; wallclock remained 798–815 ms and webview heap remained 41.2–44.8 MB. This is roughly a 96.7% reduction in the original long-task average with unchanged query/grid semantics.
- Validation: webview and extension builds, lint, production bundle, 11 focused Fluent Result Grid tests, and the real 4/4 VS Code/SQL interaction run all passed. The remaining >200 ms outliers keep the wide path open for further QP-4 work rather than being treated as complete.

### 2026-07-13 — exact webview profiling and collector-boundary checkpoint

- `perftest` `f14fb91` wires the previously dormant `rendererProfile` configuration to a CPU-sampling collector for the actual Query Studio iframe target. Target inventory logs only privacy-safe type/kind/debuggable fields; candidates must belong to `ms-mssql.mssql` and contain the product-owned `qs-results-panel-results` sentinel. The raw `.cpuprofile` and normalized duration, sampled CPU, and sample-count metrics are retained as diagnostic-only evidence.
- Chromium's Tracing domain is unavailable on the iframe target, so `cdpRendererTrace` now explicitly selects and labels the workbench page as `workbenchRendererProcessWindow`; its paint/layout/script totals are no longer presented as grid-only evidence. Trace and profile collectors reuse one remote-debugging port.
- A fast query could otherwise complete while CDP attachment was still in flight, or editor cleanup could remove the iframe before `Profiler.stop`. The driver now emits `scenario.collectors.prepare`, waits for every start hook, then timestamps `scenario.start`; at `scenario.end` it waits for every stop/flush hook before success checks and cleanup. Start attachment cost stays outside the measured interval, while the profile intentionally includes the short boundary-ack envelope around it. Both waits are bounded and collector failures degrade through the existing validation channel rather than hanging the run.
- End-to-end proof run `2026-07-13T16-38-44Z_a46aca4c` passed. Both collectors started before the phase-`start` acknowledgement, the query window then completed in 702.9 ms, and both stopped before phase-`end` acknowledgement and shutdown. The exact webview profile contains 1,086 samples / 1,031.7 ms sampled CPU; the workbench trace contains 5,206 events and is separately scoped. Both collector validations passed and both raw artifacts were linked from the report.
- Validation: contracts/CLI/driver builds passed; 47 contract tests and 145 non-central-store CLI tests passed. The full CLI invocation additionally passed those same 145 tests but could not run the independently provisioned central-store integration case because nothing was listening on localhost:14333; that environmental failure is unrelated to the query profiler.

### 2026-07-13 — bounded large-selection summary and real select-all coverage

- Query Studio's active-result context counted selected rows by inserting every row ordinal into a JavaScript `Set` after the 200 ms drag-selection coalescer. A single 100k/million-row rectangle therefore performed O(selected rows) synchronous work and allocated one entry per row even though the input was already an interval.
- `vscode-mssql` `61a442d5a` replaces expansion with sorted inclusive-interval merging: O(R log R) time and O(R) memory for R selection ranges, independent of row cardinality. Unit coverage includes a 100,000,006-row overlapping/adjacent union and invalid ranges. The imperative grid seam now supports selector-free select-all and waits until the same throttled host selection-context RPC used by normal UI interactions has completed.
- The first warmed-state run passed 3/4 and exposed a correctness edge rather than hiding it: SlickGrid suppresses its range-changed event when a full selection is restored unchanged. The grid now recognizes that exact full-range state and synthesizes the normal summary callback only for the suppressed-event case. The repeated run `2026-07-13T17-17-09Z_fa8c2cbe` then passed 4/4, including the warmed/restored rep.
- Full scenario wallclocks (results-tab paint plus select-all) were 799.5, 805.9, 811.4, and 810.8 ms. The isolated select-all interaction—from semantic begin through the 200 ms coalescer, interval summary, host RPC, and next paint—was 270, 271, 303, and 318 ms. Longest webview tasks were 63–102 ms, DOM stayed at 517–546 nodes, and all outcomes were `applied`. The scenario is deliberately end-to-end; the remaining 200 ms coalescer is visible in the number rather than timed outside it.
- `perftest` `a17c304` adds the closed `selectGrid/all` action, 100k scenario, contract notes, warmed repetitions, and scenario conformance coverage. Validation passed: product builds/lint/bundles, 18 focused product tests, 27 observability tests, 47 contracts tests, and 148 non-central-store CLI tests.

### 2026-07-13 — bounded/projected grid copy and real 100k clipboard coverage

- The old copy path guarded only row count. Multi-range copy expanded every selected row/column into `Set`s, fetched the full span between distant columns, retained every decoded `DbCellValue`, built a second TSV line matrix, and finally joined another full clipboard string. A 100k × 300 selection passed the row guard even though it implied 30 million output cells; sparse columns 0 and 299 transported the other 298 columns.
- `vscode-mssql` `37396c3c4` introduces a pure interval planner. It normalizes/clamps ranges, merges inclusive row/column runs, computes SSMS-style sparse row bands, and rejects more than 1,024 rectangles, 100,000 union rows, or 1,000,000 union-output cells before enumerating an index. Runtime output is additionally capped at 8,000,000 UTF-16 characters (about 16 MiB); oversize selections reuse the localized copy-too-large notice and issue no further clipboard write.
- Copy execution now requests each contiguous selected column run rather than its bounding span, processes only one adaptive row window at a time, retains no result-wide decoded matrix/map, and keeps only the unavoidable final clipboard text. A copy-specific decoder preserves full `cellTextForPurpose(..., "copy")` fidelity and NULL semantics without constructing render-only grid-cell objects or classifying XML/JSON links. Headers use the same non-expanding column-run plan.
- The privacy-safe `mssql.queryStudio.grid.copy.begin/end` pair reports only aggregate shape/outcome: ranges, rows, columns, output cells, characters, projected RPC count, adaptive window rows, and planning/fetch-decode/format/Clipboard API durations. `perftest` `83e017b` adds the closed selector-free `copyGrid/all` action, a real 100k-row copy scenario, registry generation/vendor parity, and an oracle requiring `copied`, 100,000 rows, and four columns.
- Fixed-512-window baseline `2026-07-13T17-43-34Z_e808df14` passed 4/4 with the exact 400,000-cell / 3,215,607-character output. It needed 196 projected RPCs and 1,200.6 ms average copy time; full semantic-action wallclock averaged 1,720.8 ms.
- Final 8,192-cell work-quantum run `2026-07-13T17-57-57Z_db9ce71c` also passed 4/4 with identical output, but needed 49 RPCs (75% fewer) and averaged 828.4 ms copy time (31% lower) / 1,317.9 ms full action wallclock (23% lower). Average phase attribution was 0.55 ms planning, 777.1 ms projected fetch + exact decode, 33.4 ms TSV formatting, and 16.7 ms Clipboard API. Interaction longest tasks were 80, 0, 0, and 79 ms; DOM stayed at 517 nodes and used heap was 66.6–73.9 MB.
- A deliberate 16,384-cell experiment `2026-07-13T18-00-18Z_3ee1071e` reduced RPCs to 25 and copy time to 716.9 ms average, but produced a 154 ms main-thread task. It was rejected and the 8,192-cell setting retained: the extra ~112 ms total latency buys the materially tighter responsiveness envelope requested for interactive Query Studio work.
- Validation passed on the committed setting: complete product/perftest builds, product lint, online VSIX packaging, 194 Query Studio tests, 27 observability-contract tests, 47 perf-contract tests, 85 Query Studio scenario tests, vendor parity, and repeated live SQL/VS Code/Clipboard runs. Remaining copy work is cancellation plus sparse/large-value fixture expansion (QPF-031/QPF-022), not unbounded allocation.

### 2026-07-13 — bounded Messages catch-up and incremental state/index checkpoint

- The user-supplied session capture `sess_20260712235836_34424` sharpened the fast-result focus diagnosis. For the submitted run, `qs/getMessages` began/ended at events 262/263 before `query.firstResult` at 264; the query then completed with one result set, 11 rows, and zero errors, and the grid rendered/fetched normally. The capture was created at 16:58:36 local time, 26 seconds before `fc41565f7` was committed at 16:59:02. It proved the ordering class and motivated the post-paint tab oracle; that stronger oracle subsequently exposed the second notification-to-state race fixed below.
- `vscode-mssql` `d0eb49d63` replaces repeated state scans with incrementally maintained total rows, columns, error messages, and plan results. Its ordered result-summary index appends in O(1) and resets per run; it is not rebuilt on every coarse state push. A host/data-plane regression test covers two result sets, a plan set, errors, row/column totals, and reset correctness across a second execution.
- Messages restore/catch-up now uses absolute-positioned windows capped at 2,048 messages and 1,000,000 text characters. Responses expose `startIndex`, `nextIndex`, `totalCount`, `textCharacters`, and `hasMore`; merge logic deduplicates overlaps, refuses gaps, clamps hostile positions, and always makes forward progress for a single oversized message. Live positioned notifications and catch-up windows share the same index space.
- The virtual Messages pane now extends its exact multiline height-prefix index only for appended rows, O(delta), and rebuilds once when a new run replaces the array. The tiny eager transport/window helper is separate from lazy formatting/rendering code: the first broad test caught an extra startup chunk, the split removed it, and all five Query Studio bundle-budget guards passed without raising a ceiling.
- `perftest` `41541b1` registers `mssql.queryStudio.messages.window` and the missing `visibleRows` display-preparation attribute, regenerates the reference contract, and preserves product/vendor parity. The new marker prices every host window using aggregate-only indices/counts/characters/backlog/duration—never message text.
- Fresh before run `2026-07-13T18-17-08Z_9392ccaa` and after run `2026-07-13T18-44-43Z_a49f8965` each passed 4/4 on localhost integrated SQL, VS Code 1.128.0, one warm-up plus three measured reps, and the same 10,003-message oracle. Wallclock mean moved from 2,284.9 to 2,111.1 ms (-7.6%), while the median was effectively flat (2,104.9 vs 2,116.6 ms); treat this as responsiveness/non-regression evidence, not a promoted latency win. Total state-build time moved from 41.1–49.5 ms (44.4 ms mean, 43.6 median) to 32.6–40.6 ms (36.4 ms mean, 36.1 median), about 18%/17% lower. Display preparation remained 2.9–4.5 ms before and 3.0–4.0 ms after.
- The live after run served 9–15 catch-up windows per repetition, each returning at most 800 messages in this streaming race, for only 0.68–1.05 ms total host window work. DOM remained bounded at 264 nodes (263 before); used webview heap was 36.2–41.4 MB (37.7–42.9 MB before). Three reps had no long task and one recorded 59 ms; the before run recorded none, so this single small outlier is retained rather than claimed as an improvement. A forced-backlog 100k-message scenario is still required to exercise `hasMore` repeatedly.
- Validation: full extension/webview builds and bundles, typechecks, lint, 201 Query Studio tests, five explicit bundle-budget tests, 27 observability tests, 47 perf-contract tests, 85 Query Studio scenario tests, generated/vendor parity, and the live 4/4 run passed. The broad CLI run passed 151 tests plus 14 intentional skips; its one independent central-store integration test could not connect to stopped `localhost:14333`, unrelated to this checkpoint.
- A separate audit closed QPF-007 without code: the current grid controller already keeps its windowed source in a ref, excludes the source and `rowCount` from result/data-view identity, and calls `setLength` independently. Recreating the data source on every row-count update is therefore not a current defect.

### 2026-07-13 — first-query / `SELECT 100` Results-focus closure

- `resultsRendered` now reports `activeTab` as a registered privacy-safe enum computed at the actual post-paint boundary. This distinguishes “result data exists” from “the user is actually looking at Results” and makes the screenshot regression machine-verifiable.
- Initial live oracle run `2026-07-13T19-06-08Z_0ce3d1f3` appeared to pass the measured `SELECT 100` 4/4, but marker inspection found that the unmeasured first readiness `SELECT 1` painted `activeTab=messages` in all four fresh processes. `QsRunStarted` had reset Results before the debounced coarse state arrived; the eligibility render still saw idle/previous state, selected Messages, and then treated that explicit selection as sticky.
- `vscode-mssql` `8524c6572` records the notified run id and treats only the notification-to-matching-state gap as execution-in-progress for tab eligibility. Once coarse state observes the same run, normal executing/terminal/result/error rules resume. Unit coverage pins undefined/previous/matching generation transitions; the full Query Studio suite passed 202 tests and all startup bundle ceilings remain intact.
- `perftest` `730fbf3` adds the exact `SELECT 100;` fixture and `querystudio-query-scalar-results-focus` scenario. It refuses to begin measurement unless the connect readiness `SELECT 1` already painted one row / one result set on Results, then applies the same oracle to the measured `SELECT 100`. Scenario/contract coverage passed 88 + 27 tests.
- Final live run `2026-07-13T19-15-16Z_0bea9db9` passed 4/4. Every process emitted two one-row renders, all eight had `activeTab=results`, and there were zero run-time eligibility transitions to Messages. Measured wallclocks were 213.4, 356.1, 1,186.4, and 231.5 ms; the outlying third process is retained as startup/environment variance because the correctness oracle and all milestones passed.

### 2026-07-13 — wide-grid horizontal viewport projection

- `vscode-mssql` `c2b177254` makes horizontal projection an opt-in FluentResultGrid source contract. Schemas below 64 columns keep the existing full-row path. Wide grids derive a contiguous source-ordinal band from SlickGrid's pixel viewport and retain eight overscan columns on each side; frozen, always-rendered, and active data columns are mandatory dependencies. The resident band is reused until the required span leaves it, avoiding a request per scroll event. If dependencies span the schema, the resolver deliberately falls back to a full row.
- Projected wire rows are expanded into sparse arrays in the original full source-ordinal space. This preserves field keys, source row ids, NULL semantics, rich-cell language metadata, selection/navigation, and later band replacement. Sort/filter and explicit async operations call the source without a column window and therefore retain authoritative full rows. Automatic autosize samples only already-loaded projected rows so a timing-dependent retry cannot defeat viewport bounds; explicit user autosize retains full-row behavior.
- Column-band changes invalidate the three row windows as one request generation; existing request ids suppress late responses. Initial/result-identity refresh now resolves the live horizontal band before resetting row windows. This ordering fix was necessary: the first implementation could issue one full generation and immediately replace it with a projected generation when grid creation and identity refresh interleaved.
- The same investigation found a lifecycle correctness defect: changing a custom data view tore down SlickGrid render, keyboard, and selection observers even when SlickGrid retained the live instance. The lifecycle now follows the grid instance rather than the data-view identity, and a replacement view reattaches independently. All four final live repetitions emitted the real 300-column first-visible-rows paint marker.
- Window observability now reports row start/count, projected start/count, total columns, requested/returned rows/columns/cells, projection mode, and RPC duration. Render and first-paint markers report both logical and fetched columns. `perftest` `7223a79` governs those attributes and makes the 300-column horizontal scenario require a completed projected window.
- Clean before run `2026-07-13T19-33-11Z_fec0e81b` and final run `2026-07-13T20-08-13Z_aecd56b5` each passed 4/4 with localhost integrated SQL, VS Code 1.128.0, one warm-up plus three measured repetitions, and the same end/back horizontal sweep. Before projection, automatic viewport reads decoded an estimated 73,800–90,000 cells per process (six full-width windows). The final run decoded exactly 4,376 cells in eight windows per process—including both horizontal jumps—with zero automatic full-width 300-column reads: a 94.1–95.1% reduction. First paint fetched 9 of 300 columns in every process.
- The transfer reduction has an honest interaction tradeoff: the old full-width cache made end/back jumps local, while the bounded design performs two small row-window RPCs for each new band. Full scenario wallclock mean/median moved from 800.6/797.6 ms to 832.9/834.2 ms (about +4.0%/+4.6%); post-action projected RPCs ranged from 4.9 to 50.1 ms. The horizontal interactions added zero long tasks in every final repetition. Terminal used heap averaged 44.5 MB versus 46.4 MB before (about 4% lower); post-interaction used heap was effectively flat, and DOM remained SlickGrid-bounded. Treat heap/long-task movement as bounded non-regression evidence, not a promoted latency win.
- Validation: complete product build, webview typecheck/bundle, lint, 202 Query Studio tests plus the direct projection/refresh/full-row fallback test, 27 observability-contract tests, 47 perf-contract tests, 88 Query Studio scenario tests, generated/vendor parity, and the final live 4/4 oracle passed. The broader perftest run passed all non-central-store coverage; its independent live central-store case could not connect to stopped `localhost:14333`.

### Baseline/results template

Use one block per promoted run set:

```text
Date / machine / load:
vscode-mssql commit:
sqltoolsservice commit:
perftest commit:
STS/runtime build:
Scenario + tuning digest:
Connection class / warm state / repetitions:
Correctness oracle:
Median / p95 milestones:
CPU / allocations / peak working set / heap:
Cache / spill / queue / long-task evidence:
Raw artifact location:
Conclusion and next change:
```
