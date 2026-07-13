# Claude Code Prompt: Refactor MSSQL Debug Console Perf Test History, Self-Test Connections, and Rich Diagnostics

> Paste this into Claude Code from `C:\repos\test` or from the root that contains the `vscode-mssql`, `perftest`, `sqltoolsservice`, and debug-docs folders. This is a multi-stage autonomous build. Make a detailed plan first, then implement task by task, verifying each task before moving to the next.

---

## Role and mission

You are improving the MSSQL Debug Console and the local perftest/debug diagnostics stack. The current Perf & Sessions page has started to slow down as history grows, and the product needs a sharper, scalable **Perf Test History** experience that fits the Debug Console host.

Your mission is to:

1. Refactor the existing **Perf & Sessions / Perf Test History** UI into a fast, scalable, drill-down history viewer using the supplied Claude Design prototype as the visual and interaction reference.
2. Make history loading snappy with large numbers of runs by introducing lazy loading, indexed summary metadata, virtualization, and provider abstractions for directory, SQLite, and imported-bundle sources.
3. Improve the self-test workflow so the user can choose which SQL connection the test run uses.
4. Investigate and fix the current self-run timeout waiting for `mssql.activate.end`.
5. Add a context-sensitive rich diagnostics collection mode, temporarily named `COLLECT_ALL_THE_DATA`, that augments telemetry events with low-cost CPU, memory, rendering, SQL, I/O, and available per-context metrics while preserving official-vs-diagnostic honesty and privacy/redaction rules.
6. Fix the current waterfall bug where a scenario span keeps running after scenario completion and the timeline fills with repeated viewer calls such as `getWaterfall` / `listTraces`.
7. Add richer instrumentation across the core scenarios so the new history UI has better timelines, breakdowns, drill-ins, and evidence.

This should be implemented as production-quality code, not a static demo. The supplied design component is a reference for behavior and layout, not a runtime dependency.

---

## Source material to read first

Before making code changes, read the relevant local docs and prototypes. Treat the existing implementation as truth for current APIs, and treat the prototype/spec files as the intended UX direction.

Primary prototype/reference:

- `C:\repos\test\debug-docs\VS Code MSSQL Performance Panel-handoff 2\vs-code-mssql-performance-panel\project\Perf Test History.dc.html`
- Any other perf-history files in that handoff folder.
- The new Perf Test History spec file, if present in the debug-docs handoff or repo.
- Existing Debug Console UX/technical specs from the previous handoff.

Related existing directions:

- Existing MSSQL Debug Console / in-product diagnostics docs.
- Perftest Phase 3 and Phase 4 docs, especially history/trend, waterfall/plot renderer reuse, SQL activity, CDP renderer traces, soak analysis, local history, and Session Diag source selection.
- Existing implementation of the current Perf & Sessions page.
- Existing self-test implementation and the current perftest runner/control flow.

Important UX reference from the prototype:

- The view has two top-level tabs: **Runs Summary** and **Run Analysis**.
- Runs Summary gives snappy all-up history triage: KPIs, latest regression callout, cross-run trend, suite health, needs-attention list, and history sources.
- Run Analysis has a source command bar, a top runs table, left filter rail, middle scenario/aggregate table, right charts panel, and bottom detail tabs.
- Run Analysis panes are resizable and dense. Tables and charts are linked: selecting runs changes scenario aggregates, selecting a scenario changes charts and bottom detail panes.
- Bottom tabs include Submetrics, Waterfall, SQL Activity, Renderer, Memory / GC, CPU Trace, Artifacts, Validation, and All Data Dump. Tabs should be optional or disabled when data is absent.

Do not copy the design component runtime or `support.js` into the product. Rebuild this as a proper VS Code webview using the existing project architecture, VS Code theme tokens, CSP-safe assets, and production data models.

---

## Non-negotiable guardrails

1. **Do not fabricate metrics.** If a metric, interval, artifact, or confidence value cannot be measured or read from artifacts, surface it as missing, unavailable, low-confidence, or diagnostic-only. Never invent plausible values to make UI or tests look good.
2. **Keep official and diagnostic data separate.** Official regression gating must remain driven only by official metrics. SQL activity, CDP renderer traces, heap dumps, CPU profiles, and other rich diagnostics are investigation context unless explicitly official-eligible under the existing contract.
3. **Keep privacy and redaction mechanical.** SQL text, row values, connection strings, tokens, secrets, and user data must remain redacted/digest-only by default. Rich collection must obey capture policy and must never silently elevate capture.
4. **No product behavior change with debug/perf flags off.** Product instrumentation changes must be behind the existing perf/debug/session-diagnostics gates. Low-cost markers must be nonblocking and bounded. Heavy collectors must be opt-in or diagnostic-mode only.
5. **Scale is a feature.** The history UI must not parse every artifact, load every run JSON, or render thousands of DOM rows on open. It should feel instant even with thousands of runs.
6. **Autonomous but disciplined.** Make a plan, implement in small verifiable steps, update progress notes, and keep going unless a decision would violate privacy, metric integrity, or product behavior constraints.

---

## Stage 0: Plan, inventory, and baseline verification

Start by writing or updating a local implementation plan and progress log in the appropriate repo or docs folder.

Plan must include:

- Current implementation map: where Perf & Sessions is implemented, where history data is loaded, where self-test lives, where waterfall data is produced, and where instrumentation is emitted.
- Data source map: local perf-runs directory, SQLite perf store, imported bundles, current Session Diag or Debug Console session if present.
- Performance risks: places that eagerly scan directories, parse full `result.json`, parse large artifacts, rerender giant tables, or calculate aggregates on the UI thread.
- A proposed history provider interface and indexing strategy.
- A task checklist with acceptance criteria.

Before changing behavior, capture the current state:

- Run unit tests and build checks that are normally required for this repo.
- Open the current Perf & Sessions page and note current loading behavior.
- Run the current self-test once, or inspect the latest failure logs if running it is too expensive.
- Reproduce or inspect the waterfall bug where scenario spans keep extending after scenario completion.

---

## Stage 1: Make history loading scalable and snappy

The Perf Test History page must support large histories without freezing the webview. Implement the data layer first, then wire the UI to it.

### Requirements

Create a provider abstraction, for example:

```ts
interface PerfHistoryProvider {
  readonly id: string;
  readonly kind: 'directory' | 'sqlite' | 'bundle' | 'session';
  readonly displayName: string;
  getStatus(): Promise<HistorySourceStatus>;
  queryRuns(query: RunHistoryQuery): Promise<PagedResult<RunSummaryRow>>;
  queryScenarioSummaries(query: ScenarioSummaryQuery): Promise<PagedResult<ScenarioSummaryRow>>;
  queryMetricSeries(query: MetricSeriesQuery): Promise<MetricSeriesResult>;
  loadScenarioDetails(query: ScenarioDetailsQuery): Promise<ScenarioDetails>;
  loadArtifact(ref: ArtifactRef): Promise<ArtifactPayload>;
  rescan?(): Promise<void>;
}
```

Use equivalent names if the codebase already has a better convention.

Implement a metadata-first indexing model:

- Run-level summary metadata should be available without reading every heavy artifact.
- Scenario-level aggregate rows should be precomputed, cached, or retrieved through SQLite summaries when available.
- Heavy artifacts such as `sql-activity.jsonl`, `renderer.trace.json`, heap snapshots, gcdumps, CPU profiles, raw dumps, and full waterfalls should load only when the user opens the relevant tab or chart.
- Directory sources should maintain a small index/cache file if appropriate, with clear invalidation on file timestamp/hash changes.
- SQLite sources should query with limits, filters, and aggregate SQL rather than loading everything into memory.
- Imported bundles should be read-only and lazy.
- UI tables must use virtualization or incremental paging for large run and scenario lists.
- Aggregation work that can be expensive should move off the UI thread or be chunked so the webview does not freeze.

### Performance acceptance targets

Use practical targets and record results in the progress log:

- Initial render of Runs Summary should show shell and cached/source status quickly without waiting for full artifact parsing.
- With a synthetic or real large history of at least 5,000 runs and many scenarios, the page should remain responsive while data loads.
- No top-level page open should synchronously parse full artifact files for every run.
- Top runs table and scenario table should scroll smoothly through large result sets.
- Switching selected run/scenario should request only the data needed for the selected view.
- Bottom tabs should lazy-load their artifacts and show loading, missing, stale, and error states.

---

## Stage 2: Refactor Perf & Sessions into the new Perf Test History UX

Refactor the UI around the supplied prototype and the spec.

### Top-level structure

Use two primary tabs:

1. **Runs Summary**
2. **Run Analysis**

Keep it inside the MSSQL Debug Console visual system, or register it as the Perf & Sessions page if that is the existing navigation name. It should still feel native to VS Code: same theme tokens, dense tables, monospace data, restrained colors, and no decorative dashboard fluff.

### Runs Summary tab

Implement the summary tab as a fast landing/triage page.

Include:

- History source status: source name, run count, indexing freshness, source kind.
- KPI strip: total runs, scenario count, latest verdict, current median/p95, SQL read deltas, memory/soak status, invalid reps, source count.
- Latest regression callout with direct drill-in to Run Analysis.
- Cross-run trend with baseline band and step-change marker.
- Suite health bars for latest selected run or latest indexed run.
- Needs-attention list with regression/investigation/warning rows.
- History sources panel listing default local history, SQLite preview/source, imported bundles, and source state.

Each tile/callout should be clickable where meaningful and should preserve selection context when moving to Run Analysis.

### Run Analysis tab

Implement the detailed workbench layout:

- Source command bar: current source selector, Open Directory, Connect SQLite DB, Import Bundle, Rescan, Pin Baseline, Compare selected runs, Export Selection.
- Top pane: virtualized runs table.
- Left pane: filter rail.
- Middle pane: scenario/aggregate table.
- Right pane: linked charts for the selected scenario or aggregate.
- Bottom pane: tabbed drill-in.
- Resizable splitters: top runs height, bottom details height, left filter width, right chart width.

#### Runs table

Columns should include at least:

- Selection checkbox
- Verdict/status
- Created
- Run id
- Label/tag
- Source
- Commit and dirty state
- Environment hash
- Scenario pass count
- Reps
- Regression count
- Invalid count
- p50
- p95
- SQL reads or key selected metric
- Artifact badges

Support:

- Single selected primary run.
- Optional selected comparison set.
- Baseline pinning.
- Sorting and filtering.
- Environment mismatch warning.
- Source badges: local directory, SQLite, bundle, current session.

#### Filter rail

Filters should include:

- Run scope: selected run only, selected runs, all runs in source.
- Time range: last 24h, last 7 days, last 30 days, custom.
- Scenario suite.
- Verdict.
- Metric family.
- Artifact availability.
- Environment hash.
- Tags/labels.
- Threshold filters, such as p50 delta > N%, p95 delta > N ms, SQL reads delta > N%, invalid reps > 0.

Filters should apply to both the scenario aggregate table and charts. The UI should make active filters visible as removable chips.

#### Scenario / aggregate table

This is the main middle table. It should support multiple modes:

- Scenario summary.
- Group by suite.
- Group by scenario name.
- Group by run label/tag.
- Group by commit.
- Group by setting/config dimension where present.
- Group by verdict.
- Group by metric family.

Columns should include:

- Scenario or group name.
- Suite.
- Status/verdict.
- Confidence.
- Valid reps / total reps.
- Candidate p50 / p95.
- Baseline p50 / p95.
- Delta absolute and percent.
- SQL reads and SQL delta when present.
- Renderer p95/longest task when present.
- Memory slope when present.
- Artifact badges.

Selecting a row updates the right charts and bottom details. Expanding a row should show an investigation summary and evidence line.

#### Right chart panel

Charts are linked to the selected scenario/group and current filters.

Include:

- KPI mini-cards for selected metric family.
- Trend over runs with baseline band and step-change marker.
- Distribution for selected run/reps.
- A/B delta bars for key metrics.
- Time split / component breakdown.
- Memory soak chart when applicable.
- Low-N and low-confidence warnings.

Charts should render from real data only. Missing or unavailable metrics should show clear empty states, not fake sample data.

#### Bottom detail tabs

Tabs should be lazy-loaded and conditionally enabled. Required tabs:

- **Submetrics**: metric table with value, baseline, delta, percent, official/diagnostic, confidence, source, notes, and gating explanation.
- **Waterfall**: per-rep cross-process waterfall using existing/shared renderer, with official vs aligned diagnostic styling and clock alignment metadata.
- **SQL Activity**: commands, duration, CPU, logical reads, physical reads, writes, rows, correlation, status, and redacted SQL digest/detail pane.
- **Renderer**: CDP breakdown, long tasks, data receive to render complete, trace artifact link.
- **Memory / GC**: RSS/working-set trends, soak slope, CI, R², samples, verdict, heap/gcdump artifacts when present.
- **CPU Trace**: CPU/profile artifacts and summary if present.
- **Artifacts**: all artifacts, type, size, source, privacy classification, open/include actions.
- **Validation**: required markers, semantic success proofs, artifact schemas, gap/missing marker state, invalid rep reasons.
- **All Data Dump**: redacted raw JSON for selected run/scenario/rep/artifact, with search.

Optional tabs should be visible but disabled, or hidden, based on the chosen UX pattern. Make absence obvious without clutter.

---

## Stage 3: History source selection and SQLite support

The view needs explicit control over where run history comes from.

### Required sources

- Default local history directory.
- Open Directory.
- Connect SQLite DB, initially read-only if schema support is partial.
- Import Bundle / support zip.
- Current Session / Session Diag source when available.

### Source UX requirements

- Current source selector should show name, kind, run count, and indexing status.
- Source dropdown should show current source, recent sources, actions, and warnings.
- SQLite connect modal should support read-only mode, index-on-connect, watch-for-changes where supported, schema version detection, and graceful behavior for old schemas.
- Imported bundles are read-only and should clearly display that state.
- Allow multiple sources to be listed in summary, but Run Analysis should have a clear active source or explicit multi-source mode.

### Data architecture requirements

- Do not couple the UI directly to filesystem scanning or SQLite details.
- Providers should return normalized rows.
- Preserve provenance: run id, source id, source kind, environment hash, commit, branch, dirty state, capture policy, schema version.
- Add robust missing/mismatch states: missing result, invalid schema, partial artifacts, stale index, unreadable directory, SQLite schema mismatch.

---

## Stage 4: Improve self-test connection selection

The self-test must let the user choose how SQL connectivity is provided. The current behavior is too implicit and too dependent on active editor focus.

### UX requirements

Add a self-test connection selector with these options:

1. **Use active connection**
   - Default when an active MSSQL connection can be resolved.
   - Must be more robust than "foreground editor only".
   - Should search the extension's active connection/session state, Object Explorer selection, query editor association, and recent/current connection context.
   - Show exactly which server/database/auth mode will be used, redacted as needed.

2. **Choose saved connection**
   - Dropdown/search over saved MSSQL connection profiles.
   - Redact secrets and sensitive fields.
   - Validate availability before starting test.

3. **Use connection string from environment variable**
   - User picks or types the env var name, such as `MSSQL_PERFTEST_CONNECTION_STRING`.
   - Do not persist the raw connection string.
   - Redact display. Show only safe digest/summary.

4. **Temporary connection profile from env/secret**
   - Create a temporary profile if the test machinery requires one.
   - Delete it after the run, even on failure, unless user explicitly opts to save it.

5. **No SQL connection needed**
   - For harness-only/no-op/activation scenarios.
   - UI should explain that SQL scenarios will be skipped or marked unavailable.

### Self-test execution requirements

- The selected connection mode must be captured in run provenance without leaking secrets.
- If a test uses a saved profile, use the product's existing connection profile model rather than inventing a parallel secret store.
- If a test uses an env var connection string, never log the raw value.
- Validate connection before starting scenarios that need SQL.
- Fail early with actionable errors if no connection can be resolved.
- The self-test runner should clearly show which scenarios are skipped due to missing connection versus failed after starting.

### Acceptance

- User can run harness-only tests with no SQL connection.
- User can run SQL scenarios using an active connection without relying on foreground editor focus.
- User can choose a saved connection profile.
- User can use an env var connection string without persisting it.
- Temporary profile cleanup is verified after success, failure, and cancellation.
- Logs and provenance redact sensitive connection data.

---

## Stage 5: Investigate and fix the self-run activation timeout

The current self-run gets stuck here:

```text
▸ run started · 7 scenario(s) · 28 rep(s)
▸ [1/7]
Harness loop (no-op)
rep 0 (warmup) …
✓ rep 0 (warmup)
1ms
rep 1 …
✓ rep 1
0ms
rep 2 …
✓ rep 2
0ms
rep 3 …
✓ rep 3
1ms
done: 4 passed
▸ [2/7]
Synthetic 250ms delay
rep 0 (warmup) …
✓ rep 0 (warmup)
326ms
rep 1 …
✓ rep 1
333ms
rep 2 …
✓ rep 2
329ms
rep 3 …
✓ rep 3
359ms
done: 4 passed
▸ [3/7]
Extension activation
rep 0 (warmup) …
✗ rep 0 (warmup)
— Timed out after 300000ms waiting for marker 'mssql.activate.end'
rep 1 …
```

### Investigation checklist

Determine which of these is true:

- The extension did not activate.
- The extension activated but marker emission did not run.
- `PERF_MODE` or the diagnostics gate was not set for the extension host.
- The marker name changed or is emitted under a different trace/session id.
- The marker sink is not connected or is dropping the activation marker.
- Activation failed before the end marker and the failure was not surfaced.
- The driver is waiting for the wrong run/session marker source.
- The timeout is masking a fast failure.

### Fix requirements

- Activation begin/end markers should always be balanced when activation starts, including failure paths. If activation fails, emit a failure marker with error classification and then fail the scenario clearly.
- The self-test should fail fast if the extension host is not connected to the marker sink.
- Waiting for markers should show last observed marker, current trace/run id, expected marker, and the marker source being watched.
- Add a diagnostic breadcrumb to the UI and logs for missing required markers.
- Do not increase the timeout as the primary fix.

### Acceptance

- Extension activation self-test passes or fails with a specific actionable reason within a reasonable time.
- A missing activation marker produces an invalid scenario or clear failure, not a silent hang.
- Unit/integration tests cover activation success and activation failure marker behavior where feasible.

---

## Stage 6: Add context-sensitive rich diagnostics collection

Add a bounded, policy-aware rich diagnostics mode. Use a better final name if the codebase has a naming convention, but the intent is equivalent to:

```text
COLLECT_ALL_THE_DATA=1
```

This is not a license to capture secrets or add overhead everywhere. It is a context-sensitive, opt-in diagnostics enrichment layer.

### Core idea

When a perf trace, Debug Console session, diagnostic self-test, or explicit rich collection flag is active, telemetry events should be enriched with context-specific metrics that are cheap and safe to collect at that point.

Examples:

- Extension host events: heap used, RSS/working set, CPU usage deltas, event-loop delay if available, queue depth, pending operations, lightweight I/O counters if available.
- Webview events: `performance.now`, `timeOrigin`, marks/measures, long task summary when available, layout/paint/render phase data when available without heavy tracing, virtualized row/window counters, data receive size, render batch counts.
- STS events: managed memory counters, GC generation counts, threadpool counters, queue depth, request counts, SQL client timing where already available, not by adding intrusive queries.
- SQL command events: rows, duration, CPU, logical reads, physical reads, writes, request/session ids from existing driver/server results or XEvents when enabled. Do not add extra SQL queries just to collect metrics unless in a diagnostic collector pass explicitly designed for that.
- Scenario/harness events: rep index, warmup flag, success proof state, environment hash, active collectors, artifact refs, validation gaps.

### Data model

Add a generic diagnostics enrichment field, for example:

```ts
interface DiagnosticEventEnvelope {
  // existing fields...
  perf?: {
    captureLevel: 'summary' | 'rich' | 'artifact';
    officialEligible: boolean;
    metrics: Record<string, MetricValue>;
    counters?: Record<string, CounterValue>;
    artifactRefs?: ArtifactRef[];
    confidence?: 'high' | 'medium' | 'low' | 'inconclusive';
    collectionCost?: 'free' | 'low' | 'medium' | 'heavy';
  };
}
```

Use existing event/envelope structures if present. The specific shape should integrate with the current contracts.

### Collection policy

- Default capture remains redacted/minimal.
- Rich collection can be enabled by diagnostic session state, Debug Console trace state, self-test run config, env var, or explicit user action.
- Heavy collectors require explicit diagnostic mode and should be called out in UI.
- Each collector declares cost, privacy class, official eligibility, and availability.
- If a collector is unavailable, emit a warning/availability state, not fake metrics.
- Preserve bounded queues and do not block product critical paths.

### UI integration

The refactored Perf Test History view should detect rich metrics and surface them in:

- Scenario aggregate columns.
- Right-side chart KPIs.
- Bottom Submetrics table.
- Renderer, Memory / GC, CPU Trace, SQL Activity, and Artifacts tabs.
- Validation tab, including collector availability and missing data reasons.

### Acceptance

- Rich mode can be toggled on for a debug/perf session and off again.
- Events contain additional context-specific metrics when available.
- Metrics appear in the Perf Test History details without custom one-off UI code per event type.
- With rich mode off, overhead and capture remain minimal.
- Redaction and capture policy are enforced.

---

## Stage 7: Fix waterfall span lifecycle and viewer self-noise

There is a current waterfall bug: after running a scenario such as Object Explorer expansion, the scenario span appears not to stop. Even after scenario completion, timing keeps extending and the trace fills with repeated viewer/internal calls such as `getWaterfall` and `listTraces`.

### Likely classes of bug

Investigate all of these:

- Scenario span end marker is missing or not paired with start marker.
- Waterfall query uses current wall-clock as the end time when a completed scenario end time exists.
- The selected trace is live-following instead of pinned to the completed scenario window.
- Debug Console viewer calls are emitted into the same trace/correlation as the scenario being viewed.
- Trace queries append diagnostic viewer events to the scenario event list.
- Polling/subscription events are not classified as viewer-internal and not filtered by default.
- `listTraces` / `getWaterfall` are recursively instrumented in a way that pollutes the viewed trace.

### Fix requirements

- Completed scenario windows must have a fixed start and end.
- Waterfall rendering for completed scenarios must use the fixed end time and must not extend with later unrelated events.
- Viewer/internal diagnostic calls must be classified with `feature: debugConsole` or equivalent and `category: viewerInternal` or equivalent.
- Viewer/internal calls must be excluded by default from scenario waterfalls and Perf Test History drill-ins.
- Offer an explicit option to include viewer-internal diagnostics for debugging the Debug Console itself.
- The timeline should distinguish current live traces from historical/completed traces.
- Add tests for completed scenario end time, correlation filtering, and exclusion of viewer self-noise.

### Acceptance

- Object Explorer expansion scenario waterfall stops at scenario completion.
- Repeated `getWaterfall` / `listTraces` calls no longer extend or pollute the scenario timeline by default.
- A completed trace remains stable when the user opens/refreshes its waterfall repeatedly.
- Live traces still update correctly while actually live.

---

## Stage 8: Add richer instrumentation across core scenarios

While fixing the waterfall and rich diagnostics path, add useful instrumentation hooks to make the main scenarios easy to diagnose.

### Priority scenarios

- Extension activation.
- Connect local container / saved connection / env var connection.
- Query 10k results.
- Large result / virtual scroll.
- Object Explorer expand Tables node, including 10k-table case.
- Query error path.
- Cancel-running-query / query-cancel-midflight.
- Connect-query-disconnect soak.
- Completions latency, where the integration exists.

### Instrumentation should capture

- Scenario start/end and rep start/end.
- Semantic success proof markers.
- Command begin/end.
- RPC begin/end where available.
- STS request/handler spans where available.
- SQL activity correlation keys.
- Webview data received, render begin, render complete, row/window counts.
- Object Explorer request/response/render counts.
- Connection lifecycle: begin, auth mode, STS PID, connection ready, disconnect begin/end, failure reason.
- Error/cancellation lifecycle: cancellation requested, acknowledged, final status.
- Collector/artifact availability markers.

### Output expectations

The new history UI should be able to show:

- Which part of a scenario got slower.
- Whether slowdown is official or diagnostic only.
- Which SQL commands or renderer phases contributed.
- Which required markers or proofs are missing.
- Which collectors were active.
- What artifacts are available for deep dive.

---

## Stage 9: Verification and deliverables

### Required verification

Run the appropriate checks for every repo touched:

- TypeScript build and tests.
- Lint or format if configured.
- Webview build/CSP checks.
- Unit tests for provider queries, indexer/cache, filters, grouping, and table state.
- Tests for self-test connection selection and secret redaction.
- Tests for activation marker success/failure.
- Tests for waterfall span closure and viewer self-noise filtering.
- A synthetic large-history performance test.
- At least one manual or automated run of the self-test with the new connection selection flow, if environment permits.

### UI acceptance checklist

- Runs Summary opens quickly and shows source/index state.
- Run Analysis opens quickly without parsing all artifacts.
- Top runs table is virtualized or paged.
- Scenario table is virtualized or paged.
- Filters, grouping, baseline pinning, selected run, selected scenario, charts, and bottom tabs stay synchronized.
- Optional tabs handle missing artifacts cleanly.
- SQLite source can connect read-only or display a graceful unsupported/schema warning.
- Open Directory and Import Bundle paths are wired through provider abstraction.
- Dark/light themes work through VS Code tokens.
- Keyboard navigation and accessible labels are reasonable for tables, tabs, filters, buttons, and splitters.

### Final deliverables

At the end, provide:

1. A concise summary of what changed.
2. A list of files/modules changed.
3. Any new settings/env vars and their defaults.
4. Known limitations and deferred work.
5. Verification commands run and results.
6. Screenshots or generated HTML/report artifacts if available.
7. Notes on performance before/after for large history loading.
8. Notes on the activation timeout root cause and fix.
9. Notes on waterfall stuck-span root cause and fix.

---

## Suggested implementation order

1. Inventory current code and write the plan.
2. Build the history provider abstraction and metadata/index cache.
3. Wire the new Perf Test History data loading path to the existing page without full UI refactor.
4. Implement Runs Summary.
5. Implement Run Analysis layout with virtualized runs/scenario tables and resizable panes.
6. Implement lazy bottom tabs and artifact loading.
7. Add source selector, Open Directory, SQLite, and Import Bundle flows.
8. Add self-test connection selector.
9. Fix the activation timeout.
10. Add rich diagnostics collection framework.
11. Fix waterfall span lifecycle and viewer self-noise.
12. Add richer instrumentation to priority scenarios.
13. Polish, accessibility, dark/light, performance tests, docs, and final verification.

Keep each step independently buildable. Do not leave the repository in a half-refactored state between steps.
