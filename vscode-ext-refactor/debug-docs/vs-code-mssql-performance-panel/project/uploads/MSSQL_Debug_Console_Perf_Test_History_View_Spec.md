# MSSQL Debug Console — Perf Test History View UX Spec

**Artifact role:** Prototype-generation spec for a dedicated performance test history view inside the MSSQL Debug Console.

**Primary audience:** UX prototype generator, codegen agent, performance engineers, and extension engineers building the `vscode-mssql` diagnostics UI.

**Last updated:** 2026-07-03

---

## 1. Product intent

The **Perf Test History** view is the historical investigation cockpit for the MSSQL performance harness and Session Diag ecosystem. It lets a developer open a run-history source, inspect recent performance runs, select a run, drill into the scenarios inside that run, then inspect per-scenario charts, submetrics, waterfalls, raw data, and optional diagnostic artifacts such as SQL activity, renderer traces, GC dumps, CPU traces, or memory snapshots.

This is a page inside the existing **MSSQL Debug Console** shell, not a separate app. It should feel like a sibling of **Perf & Sessions**, **Waterfall**, and **Consolidated Trace**, but optimized around a different workflow:

- **Perf & Sessions:** live/current-session and cross-session triage.
- **Perf Test History:** durable harness/test-run history, run selection, scenario matrix, scenario-specific deep inspection, and source switching across directory/SQLite-backed histories.

Think of it as the little black-box flight recorder room inside the DevTools hangar. Dense tables first, charts second, evidence always traceable.

---

## 2. Design goals

1. **Select a history source quickly.** A developer can use the configured default history source, open a run directory, connect to a SQLite store, or import a report/bundle.
2. **Scan runs at the top level.** The top table answers: what ran, when, on what commit/env, what passed, what regressed, and what artifacts are available?
3. **Drill into scenarios.** Selecting a run populates a scenario table with all scenarios, variants, repetitions, official metrics, diagnostic metrics, pass/invalid/regression verdicts, and artifact availability.
4. **Use filters without losing context.** Filters live in a persistent left panel for run, scenario, metric, verdict, tag, environment, and artifact facets.
5. **Charts follow the current selection.** The right chart rail updates based on selected scenario, selected metric, and optional compare/baseline selection.
6. **Deep details are tabbed.** The bottom panel exposes Submetrics, Waterfall, SQL Activity, Renderer, Memory/GC, CPU Trace, Artifacts, Validation, and All Data Dump tabs, with optional tabs appearing only when data exists.
7. **Preserve metric honesty.** Official vs diagnostic, invalid reps, missing markers, low-n confidence, environment mismatch, capture redaction, and source gaps are first-class UI states.
8. **Prototype-ready.** The layout, labels, sample columns, empty states, and interactions should be concrete enough for a generator to produce a high-fidelity mockup without inventing the information architecture.

---

## 3. Placement in the Debug Console shell

### 3.1 Navigation

Add this as either:

- **Common → Perf Test History**, placed immediately after **Perf & Sessions**, or
- a top-level tab inside **Perf & Sessions** named **History**, if the shell should remain compact.

For prototyping, prefer a dedicated left-rail item:

```text
COMMON
  Overview
  Consolidated Trace
  Waterfall
  Perf & Sessions
  Perf Test History   ← new view
  Completions
  Replay Lab
```

The page inherits the existing top bar:

- session/source selector area
- Live / History toggle, with **History** selected by default for this page
- global search
- redaction chip
- export button
- provenance drawer entry point

### 3.2 Page title and command bar

Page header:

```text
Perf Test History
Run history, scenario trends, regression evidence, and per-run diagnostic artifacts.
```

Command bar actions, left to right:

1. **Source selector** dropdown: `Default local history · 142 runs`
2. **Open directory…** button
3. **Connect SQLite DB…** button
4. **Import report/bundle…** button
5. **Refresh / rescan** button
6. **Pin baseline** button, disabled until a run/scenario is selected
7. **Compare selected** button, visible when 2 runs or scenarios are selected
8. **Export selection…** button

The source selector should feel like a VS Code combobox, not a consumer cloud-account picker.

---

## 4. Source selection model

### 4.1 Supported source types

The UI should model multiple source types from day one, even if SQLite support lands later.

| Source type | Description | Primary use | Status in prototype |
|---|---|---|---|
| `configuredDefault` | Path or SQLite DB configured in Debug Console settings | normal daily usage | fully mocked |
| `openDirectory` | User selects a folder containing `perf-runs`, `benchmark_reports`, or exported report folders | ad hoc local investigation | fully mocked |
| `sqliteDb` | User connects to a local performance store DB | future retention/history source | mocked with “preview” badge |
| `importedBundle` | User imports a zip/report bundle from CI, colleague, or support issue | isolated investigation | fully mocked |
| `currentWorkspace` | Auto-discovered run history under the current VS Code workspace | convenience path | optional |

### 4.2 Source selector dropdown content

When opened, the selector shows:

```text
Current source
  ✓ Default local history
    C:\repos\test\perftest\perf-runs
    142 runs · 31 scenarios · indexed 2m ago

Recent sources
  benchmark_reports\01_31b_sharding_ablation_16k
  C:\repos\test\perftest\perf-history.sqlite
  support-bundle-2026-07-01.zip

Actions
  Open directory…
  Connect SQLite DB…
  Import report bundle…
  Manage history settings…
```

### 4.3 Source status chip

Next to the source selector, show a compact status chip:

- `indexed` green
- `scanning…` blue / spinner
- `partial` amber
- `stale` amber
- `error` red
- `read-only` gray
- `sqlite preview` gray/blue

Hover/click opens a small popover:

```text
History source health
Path: C:\repos\test\perftest\perf-runs
Runs indexed: 142
Artifacts indexed: 1,284
Last scan: 14:05:22
Missing indexes: 3 runs
Schema: perf-store v3
Privacy: redacted/digest
```

### 4.4 Settings integration

Settings page should expose:

```text
Perf Test History
  Default source type: Directory | SQLite DB | Workspace auto-discovery
  Default run directory: [path] [Browse]
  Default SQLite DB: [path] [Browse]
  Auto-scan on open: on/off
  Watch directory for changes: on/off
  Max indexed runs: 500
  Include diagnostic artifacts: on/off
  Include raw data dump tab: on/off
  Redacted preview only: on/off
```

This page should not block ad hoc source overrides. A developer can always use **Open directory…** or **Connect SQLite DB…** from the Perf Test History command bar.

---

## 5. Overall layout

Use a four-zone layout inside the page content area.

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ Page header + source command bar                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ Run History Table                                                            │
│ top: all runs from selected source, sticky header, sortable, multi-select    │
├──────────────┬───────────────────────────────────────────┬──────────────────┤
│ Filter rail  │ Scenario table / matrix                    │ Charts rail      │
│ left         │ middle                                     │ right            │
│ facets       │ all scenarios for selected run(s)          │ selected scenario│
├──────────────┴───────────────────────────────────────────┴──────────────────┤
│ Details panel tabs: Submetrics | Waterfall | SQL Activity | Renderer | ...   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.1 Proportions

At 1920px wide:

- left rail shell: existing 210px
- page content width: remaining
- run table: full width, 220–280px height
- lower analysis region:
  - filter rail: 260px
  - scenario table: flexible, minimum 650px
  - chart rail: 420px
- bottom details panel: 320–520px, resizable vertically

At narrower widths:

- chart rail collapses below the scenario table
- filter rail becomes a collapsible drawer
- bottom details remain full width

### 5.2 Scrolling

Use nested scroll regions intentionally:

- run table scrolls independently if many runs
- scenario table scrolls independently
- bottom details panel scrolls inside each tab
- page-level scroll should be avoided where possible so the command bar and selected run context remain visible

Sticky headers are required for run and scenario tables.

---

## 6. Top run history table

### 6.1 Purpose

The run table answers: **which run should I inspect?** It is a run-level catalog, not a per-scenario detail surface.

### 6.2 Columns

Default columns:

| Column | Example | Notes |
|---|---:|---|
| Status | `ok`, `regressed`, `invalid`, `needs attention` | pill with color |
| Created | `2026-07-03 14:05` | local time, sortable |
| Run | `run_20260703_140512` | monospace, shortened with hover full ID |
| Label | `PR 1042 candidate` | editable tag/label in future |
| Source | `local dir`, `sqlite`, `bundle` | badge |
| Commit | `7f3c2b1-dirty` | dirty state visible |
| Branch | `dev/karlb/perftest` | optional hidden if narrow |
| Env | `9d0412a` | environment hash; mismatch warning if compared |
| Scenarios | `12 / 14 valid` | valid/total |
| Reps | `84` | total reps |
| Regressions | `2` | official regressions count |
| Invalid | `3` | invalid reps/scenarios count |
| Wall p50 | `2.84s` | run-wide or selected suite aggregate |
| Wall p95 | `8.22s` | run-wide or selected suite aggregate |
| SQL reads | `296k` | aggregate diagnostic if available |
| Artifacts | `sql · cdp · soak · gc` | compact badges |
| Size | `38 MB` | source storage footprint |

### 6.3 Row behavior

Single click selects a run and populates the scenario table. Multi-select with Ctrl/Cmd enables compare mode. Shift-click selects a contiguous range for trend/aggregate inspection.

Row states:

- selected: VS Code active-row background and left accent strip
- baseline pinned: thin green or blue vertical marker plus `baseline` badge
- candidate pinned: thin accent marker plus `candidate` badge
- environment mismatch: amber env badge with tooltip
- partial source: amber `partial` badge in source/artifacts column
- imported bundle: blue dot or `bundle` source pill

### 6.4 Run table toolbar

Above table, include compact filters/controls:

```text
Runs 142   [Search runs, labels, commit, scenario…]   Date: last 14 days ▼   Suite: all ▼   Verdict: any ▼   Group by: none ▼
```

When a row is selected, show a small selection summary on the right:

```text
Selected: run_20260703_140512 · 12 scenarios · 2 regressions · env 9d0412a
```

---

## 7. Left filter panel

### 7.1 Purpose

The filter panel controls the selected source and selected run(s) without requiring table header gymnastics. It should feel like the completion multi-session analysis filters, generalized for perf history.

### 7.2 Filter groups

Use collapsible groups with counts.

```text
FILTERS
Search
  [scenario, metric, artifact, tag…]

Run scope
  ○ Selected run only
  ○ Selected runs
  ○ All runs in source

Time range
  Last 24h
  Last 7 days
  Last 30 days
  Custom…

Scenario suite
  Query & Results (8)
  Object Explorer (5)
  Connection (4)
  Completions (3)
  Soak (2)

Verdict
  ok (103)
  regressed (8)
  invalid (11)
  inconclusive (5)
  warning (15)

Metric family
  Wall-clock
  SQL activity
  Renderer
  Memory / soak
  Reliability
  CPU / GC

Artifacts available
  SQL activity jsonl
  Cross-process waterfall
  Renderer trace
  CPU profile
  GC dump
  Heap snapshot
  Raw result.json

Environment
  env:9d0412a (88)
  env:a1f9c03 (54)

Tags
  baseline
  candidate
  PR
  nightly
  local
```

### 7.3 Filter badges

Active filters appear as removable chips above the scenario table:

```text
query-* ×   regressed ×   has:sql-activity ×   last 7 days ×   Clear all
```

### 7.4 Filter honesty

If a filter depends on data not available from the source, disable it with a tooltip:

```text
Renderer trace unavailable: selected source indexes result.json only.
```

---

## 8. Middle scenario table / matrix

### 8.1 Purpose

This is the main work surface after selecting a run. It answers: **which scenario changed, why does it matter, and what evidence exists?**

### 8.2 Modes

The table has three display modes:

1. **Scenario summary** default: one row per scenario in the selected run.
2. **Variant matrix:** one row per scenario × variant, useful for ablations.
3. **Rep detail:** one row per repetition, useful for invalid/noisy data.

Mode switcher:

```text
View: Scenario summary ▼   Metric: wall-clock ▼   Baseline: auto ▼   Group by: suite ▼
```

### 8.3 Default columns

| Column | Example | Notes |
|---|---:|---|
| Scenario | `query-10k-results` | monospace; primary link |
| Suite | `Query & Results` | feature/suite |
| Tags | `smoke`, `sql`, `renderer` | compact |
| Status | `regressed` | official verdict |
| Confidence | `high`, `low-n`, `inconclusive` | visible if not high |
| Valid reps | `8/8` | invalid reps excluded from official aggregate |
| Wall p50 | `2.84s` | official if from markers |
| Wall p95 | `8.22s` | official if available |
| Δ vs baseline | `+310ms · +12.3%` | red/green/amber |
| SQL reads | `296,120` | diagnostic unless official source exists |
| SQL Δ | `+87,720 · +42%` | investigation context |
| Render p95 | `1.20s` | diagnostic, CDP/webview marks |
| Memory slope | `+28KB/iter` | soak only; confidence required |
| Failures | `0` | reliability count |
| Artifacts | `waterfall · sql · cdp` | clickable badges |

### 8.4 Row expansion

Clicking a row selects it and updates the chart rail and bottom details. A small chevron expands inline summary:

```text
query-10k-results
  Official: wall-clock REGRESSED +12.3% over baseline
  Investigation: candidate added 3 SQL commands and +87,720 logical reads
  Evidence: 8 valid reps, SQL activity captured, renderer trace captured, no missing markers
```

### 8.5 Compare mode

When two runs are selected in the top table, scenario rows show baseline/candidate columns:

| Scenario | Verdict | Candidate | Baseline | Δ | % | Evidence |
|---|---|---:|---:|---:|---:|---|
| `query-10k-results` | regressed | `2.84s` | `2.53s` | `+310ms` | `+12.3%` | `+3 SQL round trips` |

When more than two runs are selected, the table pivots to trend mode:

| Scenario | Runs | Latest | Rolling baseline | Trend | Step change | Verdict |
|---|---:|---:|---:|---|---|---|
| `expand-tables-node-10k` | 31 | `9.83s` | `8.20–8.55s` | sparkline | `7f3c2b1` | investigate |

---

## 9. Right charts rail

### 9.1 Purpose

Charts are contextual, selection-driven evidence. They should never compete with the tables; they explain the selected scenario.

### 9.2 Top KPI strip

For the selected scenario, show small cards:

```text
Wall p50       2.84s     +12.3% regressed
Valid reps     8/8       official
SQL reads      296k      +42% investigate
Render p95     1.20s     diag
Memory slope   +28KB/it  low confidence
```

### 9.3 Chart stack

Default chart order:

1. **Trend over runs**
   - x-axis: run time or commit
   - y-axis: selected metric
   - baseline band
   - step-change marker at introducing run/commit
   - hover: run ID, commit, metric, verdict

2. **Distribution for selected run**
   - histogram + box plot
   - show all reps, invalid reps as hollow/gray points
   - median/p95 labels

3. **A/B metric delta**
   - baseline vs candidate bars for official metrics
   - diagnostic deltas below or in an “investigation” section

4. **Time split / component stack**
   - extension, STS, SQL, wire, renderer
   - solid for official measured intervals
   - hatched for aligned diagnostic intervals

5. **SQL activity top-N**
   - duration, CPU, logical reads, rows
   - only if SQL activity artifact exists

6. **Soak / memory trend**
   - RSS vs iteration scatter
   - fitted slope line
   - confidence band
   - R² and sample count
   - verdict: stable / growing / inconclusive

### 9.4 Chart controls

Compact controls at the top of the rail:

```text
Metric: wall-clock ▼   X: commit ▼   Scale: linear ▼   Show: official + diagnostic ▼
```

### 9.5 Chart states

- **No scenario selected:** show “Select a scenario to see charts.”
- **No historical comparison:** show distribution + current run only, hide trend/A-B.
- **Low-n:** show amber callout: `Only 2 valid reps; trend confidence low.`
- **Environment mismatch:** chart baseline band is amber and notes `Different env hash; comparison is advisory.`
- **Missing artifacts:** chart card says `Renderer trace not captured for this run.`

---

## 10. Bottom details panel

### 10.1 Purpose

The bottom panel is the evidence drawer for the selected scenario, variant, rep, or metric cell. It is tabbed and extensible. Tabs can be built-in or contributed by features/collectors.

### 10.2 Tab list

Default tabs:

```text
Submetrics | Waterfall | SQL Activity | Renderer | Memory / GC | CPU Trace | Artifacts | Validation | All Data Dump
```

Tabs are visible only when relevant, with two exceptions:

- **Submetrics** is always visible.
- **All Data Dump** is always visible when raw `result.json` or equivalent source data is available.

Unavailable optional tabs should not clutter the tab list. If the user expects a tab due to a filter, show a disabled tab with tooltip only while that filter is active.

### 10.3 Tab availability badges

Examples:

```text
SQL Activity  12
Renderer      diag
Memory / GC   3 artifacts
CPU Trace     unavailable
```

### 10.4 Submetrics tab

Shows a metric table for the selected scenario.

Columns:

| Metric | Value | Baseline | Δ | % | Official | Confidence | Source | Notes |
|---|---:|---:|---:|---:|---|---|---|---|
| `scenario.wallclock.p50` | `2.84s` | `2.53s` | `+310ms` | `+12.3%` | yes | high | markers | gated |
| `sqlserver.logicalReads` | `296,120` | `208,400` | `+87,720` | `+42%` | no | high | XEvents | investigation |
| `renderer.longestTask` | `390ms` | `380ms` | `+10ms` | `+2.6%` | no | medium | CDP | diagnostic |
| `soak.memory.rssSlope` | `+28KB/iter` | `+5KB/iter` | `+23KB` | — | eligible | low | process samples | low R² |

Add a callout beneath the table when the official verdict is driven by one or more metrics:

```text
Gating verdict: REGRESSED because scenario.wallclock.p50 exceeded baseline by +12.3%, above the 10% threshold and 100ms absolute floor.
```

### 10.5 Waterfall tab

Reuses the cross-process waterfall component, scoped to the selected scenario/rep.

Must show:

- user/driver action lane
- extension host lane
- webview/renderer lane
- STS lane
- driver/network lane
- SQL Server lane
- optional diagnostics lanes
- solid vs hatched timing legend
- calibration jitter
- critical path list
- selected bar inspector

Include a rep selector:

```text
Rep: #4 · valid · 2.84s ▼   Show: critical path on · diag lanes on
```

### 10.6 SQL Activity tab

Visible when `sql-activity.jsonl` or SQLite equivalent is available.

Top summary cards:

```text
Commands 12   Total SQL time 84.2s   CPU 41.6s   Logical reads 296k   Rows 1.28M   Round-trips +3
```

Table columns:

| Time | Event type | Duration | CPU | Logical reads | Physical reads | Writes | Rows | Session | Request | Correlation | Status |
|---|---|---:|---:|---:|---:|---:|---:|---|---|---|---|

Right detail pane:

- redacted SQL text digest
- command statistics
- query plan link/artifact if present
- correlation chain
- source confidence

### 10.7 Renderer tab

Visible when CDP/webview render traces or product render markers exist.

Sections:

- Render breakdown: scripting, layout, paint, longest task.
- Timeline alignment to data receive and render complete.
- Top long tasks table.
- Trace artifact link: `renderer.trace.json`.
- Warning if target discovery was partial.

### 10.8 Memory / GC tab

Visible for soak scenarios or when memory/GC artifacts exist.

Sections:

- RSS/working-set over iteration.
- Heap used over iteration.
- Slope + confidence + R² + sample count.
- Reliability summary: failures, first failure, taxonomy.
- GC dump / heap snapshot artifact list.
- Top growth table if diagnostic root-cause collectors ran.

The verdict must be one of: `stable`, `growing`, `inconclusive`. Never show “no leak” without sample count, slope, confidence, and R².

### 10.9 CPU Trace tab

Visible when CPU profiles, dotnet-counters, ETW/WPR, or process samples exist.

Sections:

- CPU time by process role.
- Process sample timeline.
- Threadpool counters if STS counters exist.
- Profile artifacts.
- Known limitations and capture cost.

### 10.10 Artifacts tab

Artifact browser table:

| Artifact | Type | Size | Source | Captured | Privacy | Open | Export |
|---|---|---:|---|---|---|---|---|
| `result.json` | contract | 42 KB | official | always | redacted | open | include |
| `markers.jsonl` | markers | 180 KB | official plane | measurement | redacted | open | include |
| `sql-activity.jsonl` | diagnostic | 98 KB | XEvents | diagnostic | SQL redacted | open | include |
| `renderer.trace.json` | diagnostic | 4.8 MB | CDP | diagnostic | no SQL | open | include |

### 10.11 Validation tab

Shows why the run/scenario is valid or invalid.

Sections:

- required markers present/missing
- semantic proof: e.g. `rowCount == 10000`
- environment consistency
- artifact schema validation
- missing collector warnings
- invalid reps and reasons

### 10.12 All Data Dump tab

A structured JSON/tree/table viewer for raw data.

Requirements:

- default collapsed tree
- search within data
- copy path / copy value
- redacted field treatment
- source selector: `result.json`, `comparison.json`, `investigation.json`, `soak-iterations.jsonl`, `sql-activity.jsonl`
- never render huge blobs unvirtualized

This tab is for engineers and coding agents. It can be dense and unapologetically nerdy.

---

## 11. Key workflows to prototype

### 11.1 Open default history and inspect latest regression

1. User opens **Perf Test History**.
2. Source automatically loads `Default local history`.
3. Run table shows recent runs sorted newest first.
4. Latest run has `regressed` status and `2` regressions.
5. User selects the run.
6. Scenario table shows `query-10k-results` as regressed.
7. Chart rail shows trend with step-change marker at commit `7f3c2b1`.
8. Bottom Submetrics tab shows wall-clock as official regression and SQL reads as diagnostic investigation.

### 11.2 Open a benchmark report directory

1. User clicks **Open directory…**.
2. File picker returns `benchmark_reports\01_31b_sharding_ablation_16k`.
3. Source status becomes `scanning…` then `indexed`.
4. Run table shows one imported benchmark group with variant rows or child runs.
5. Scenario table can switch to **Variant matrix** and reproduce the “same x-axis” comparison style from the existing benchmark report.

### 11.3 Connect SQLite DB

1. User clicks **Connect SQLite DB…**.
2. Modal asks for local `.sqlite` path, read-only toggle, and scan/index options.
3. After connecting, source selector shows `perf-history.sqlite · 1,204 runs`.
4. Run table supports server-like paging/virtualization.
5. If schema is old, show `schema upgrade available` callout without blocking read-only browsing.

### 11.4 Compare baseline vs candidate

1. User selects baseline run and clicks **Pin baseline**.
2. User selects candidate run.
3. Scenario table switches to compare columns.
4. Right chart rail shows A/B delta bars and trend context.
5. Bottom tabs show diagnostic diffs, especially SQL activity deltas.

### 11.5 Investigate a soak memory warning

1. User filters scenario suite to `Soak`.
2. Selects `connect-query-disconnect-soak`.
3. Chart rail shows RSS vs iteration with confidence band.
4. Bottom Memory / GC tab shows `inconclusive` or `growing` with slope, CI, R², and sample count.
5. If heap snapshots exist, tab shows top growth retainers.

### 11.6 Open optional artifact tab

1. User selects `query-large-scroll-virtual-window`.
2. Renderer tab appears because CDP trace exists.
3. User selects Renderer.
4. Breakdown shows scripting/layout/paint and longest task.
5. Warning appears if CDP target matching had medium confidence.

### 11.7 Source has partial data

1. User opens a directory with `result.json` files but no artifact subfolders.
2. Source status shows `partial`.
3. Run/scenario tables still load official metrics.
4. SQL Activity, Renderer, Memory, CPU tabs are absent or disabled with explanation.
5. Validation tab lists missing optional artifacts.

---

## 12. Data model for prototype and codegen

### 12.1 PerfHistorySource

```ts
type PerfHistorySourceType =
  | 'configuredDefault'
  | 'openDirectory'
  | 'sqliteDb'
  | 'importedBundle'
  | 'currentWorkspace';

interface PerfHistorySource {
  id: string;
  type: PerfHistorySourceType;
  label: string;
  path?: string;
  sqlitePath?: string;
  status: 'indexed' | 'scanning' | 'partial' | 'stale' | 'error' | 'empty';
  readOnly: boolean;
  runCount: number;
  scenarioCount: number;
  artifactCount: number;
  lastIndexedAt?: string;
  schemaVersion?: string;
  statusMessage?: string;
}
```

### 12.2 PerfRunSummary

```ts
interface PerfRunSummary {
  id: string;
  label?: string;
  createdAt: string;
  sourceId: string;
  sourceType: PerfHistorySourceType;
  status: 'ok' | 'warning' | 'regressed' | 'invalid' | 'inconclusive' | 'error';
  commitSha?: string;
  branch?: string;
  dirty?: boolean;
  environmentHash: string;
  scenarioTotal: number;
  scenarioValid: number;
  repTotal: number;
  regressionCount: number;
  invalidCount: number;
  wallP50Ms?: number;
  wallP95Ms?: number;
  sqlLogicalReads?: number;
  artifactKinds: ArtifactKind[];
  storageBytes?: number;
  tags: string[];
  provenance?: RunProvenance;
}
```

### 12.3 PerfScenarioSummary

```ts
interface PerfScenarioSummary {
  runId: string;
  scenarioId: string;
  suite: string;
  displayName: string;
  tags: string[];
  status: 'ok' | 'warning' | 'regressed' | 'invalid' | 'inconclusive' | 'error';
  confidence: 'high' | 'medium' | 'low' | 'low-n' | 'inconclusive';
  validReps: number;
  totalReps: number;
  metrics: MetricCell[];
  artifacts: ArtifactAvailability[];
  validation: ValidationSummary;
}
```

### 12.4 MetricCell

```ts
interface MetricCell {
  name: string;
  family: 'wallclock' | 'sql' | 'renderer' | 'memory' | 'reliability' | 'cpu' | 'custom';
  value: number | string;
  unit?: 'ms' | 's' | 'bytes' | 'count' | 'percent' | 'rows' | 'reads' | 'kbPerIteration';
  baselineValue?: number | string;
  delta?: number | string;
  deltaPercent?: number;
  verdict?: 'ok' | 'warning' | 'regressed' | 'improved' | 'invalid' | 'inconclusive';
  official: boolean;
  confidence: 'high' | 'medium' | 'low' | 'inconclusive';
  source: 'markers' | 'productTimer' | 'xevents' | 'cdp' | 'processSampler' | 'dotnetCounters' | 'resultJson' | 'sqlite' | 'derived';
  derivation?: string;
  notes?: string;
}
```

### 12.5 ArtifactAvailability

```ts
type ArtifactKind =
  | 'resultJson'
  | 'markersJsonl'
  | 'comparisonJson'
  | 'investigationJson'
  | 'waterfall'
  | 'sqlActivity'
  | 'rendererTrace'
  | 'cpuProfile'
  | 'processSamples'
  | 'soakIterations'
  | 'heapSnapshot'
  | 'gcDump'
  | 'logs'
  | 'rawData';

interface ArtifactAvailability {
  kind: ArtifactKind;
  label: string;
  available: boolean;
  path?: string;
  sizeBytes?: number;
  captureCost?: 'low' | 'diagnostic' | 'heavy';
  privacy: 'redacted' | 'digest' | 'full' | 'none';
  status?: 'ok' | 'missing' | 'partial' | 'corrupt' | 'blockedByPolicy';
  reason?: string;
}
```

---

## 13. Visual design notes

### 13.1 Use the existing Debug Console grammar

Reuse the current console visual system:

- 44px top bar
- left rail navigation
- compact KPI cards
- status pills
- monospace data cells
- VS Code theme tokens
- list-plus-detail and table-plus-chart density
- redacted lock treatment
- amber warning callouts
- blue active selection

### 13.2 Table density

Rows should be 30–36px tall. Use 11px uppercase headers, 12px row text, monospace for IDs and metric values. Avoid giant cards. The run table and scenario table are the soul of the view.

### 13.3 Color semantics

Use existing semantic roles:

- green: ok / improved / valid
- red: error / regressed / invalid when severe
- amber: warning / investigate / partial / low confidence
- blue: selected / link / active source / info
- gray: unavailable / diagnostic-only / read-only

Do not invent a rainbow for every metric. Charts should be readable under light and dark VS Code themes.

### 13.4 Metric honesty markers

Use small inline markers:

- `official` check badge
- `diag` badge
- `low-n` badge
- hatched chart bars for aligned diagnostic timing
- hollow points for invalid reps
- lock icon for redacted fields
- environment mismatch amber triangle

---

## 14. Empty, loading, error, and partial states

### 14.1 No source configured

```text
No performance history source configured
Choose a local perf-runs directory, connect a SQLite history DB, or import a report bundle.

[Open directory…] [Connect SQLite DB…] [Manage settings]
```

### 14.2 Source scanning

Show skeleton rows and progress:

```text
Indexing run history…
Scanning 42 of 142 runs · found 318 artifacts · 3 schema warnings
```

### 14.3 Empty source

```text
No performance runs found in this source
Expected result.json, comparison.json, benchmark report folders, or a perf-store SQLite DB.
```

### 14.4 Partial source

Amber callout:

```text
Partial history source
Official metrics are available, but 11 diagnostic artifacts are missing. SQL Activity, Renderer, and Memory tabs may be incomplete.
```

### 14.5 Invalid/corrupt run

The run row remains visible with red/amber state. Details show validation errors. Never hide corrupt runs by default; hiding the goblin only makes it chew wires in the wall.

### 14.6 Environment mismatch

When comparing runs with different `environmentHash`, show:

```text
Environment mismatch
These runs were captured on different environment hashes. Official gating should not treat this as a clean regression comparison unless explicitly allowed.
```

---

## 15. Privacy and redaction requirements

This view may load real product Session Diag data or user-provided bundles, not just synthetic perf harness data. Therefore:

- SQL text is redacted by default.
- Connection strings, tokens, secrets, row values, and sensitive paths are never displayed unless policy allows.
- SQL text cells show digest and classification by default:

```text
🔒 SQL text redacted
sql:sha256:8fd2c91a12e9…
classification: sql.text · handling: digest
```

- Raw data dump must respect redaction, even for JSON.
- Export selection must include privacy summary and redaction scan result.
- Optional full-data tabs should be blocked by policy unless explicitly elevated.

---

## 16. Prototype screen set

Ask the prototype generator for these screens/states:

1. **Perf Test History — default loaded source**
   - run table at top
   - selected latest run
   - filter rail
   - scenario table
   - chart rail
   - bottom Submetrics tab

2. **Source selector open**
   - default source, recent sources, actions
   - source health details

3. **Open directory / source scanning state**
   - scanning progress
   - partial artifacts warning

4. **Scenario selected with compare mode**
   - baseline and candidate pinned
   - scenario table with candidate/baseline columns
   - right rail A/B chart

5. **Waterfall tab**
   - selected scenario/rep
   - cross-process waterfall with official vs diagnostic legend
   - critical path panel

6. **SQL Activity tab**
   - SQL command table
   - redacted SQL detail pane
   - logical reads delta callout

7. **Memory / GC tab**
   - soak trend chart with confidence band
   - slope/R²/sample count
   - stable/growing/inconclusive verdict

8. **All Data Dump tab**
   - JSON tree, source selector, redacted field treatment

9. **SQLite connection modal**
   - path selection, read-only toggle, schema preview

10. **Partial source / missing artifacts state**
   - official metrics available
   - optional tabs hidden/disabled
   - validation warnings visible

---

## 17. Sample data for prototype

Use these sample runs and scenarios for visual realism.

### 17.1 Runs

| Status | Created | Run | Label | Commit | Env | Scenarios | Regressions | Wall p50 | Artifacts |
|---|---|---|---|---|---|---:|---:|---:|---|
| regressed | 2026-07-03 14:05 | `run_20260703_140512` | PR 1042 candidate | `7f3c2b1-dirty` | `9d0412a` | 12/14 | 2 | 2.84s | sql · cdp · soak |
| ok | 2026-07-03 10:22 | `run_20260703_102211` | local baseline | `7a3d09c` | `9d0412a` | 14/14 | 0 | 2.53s | sql · cdp |
| warning | 2026-07-02 22:11 | `run_20260702_221109` | nightly | `ff91a20` | `9d0412a` | 13/14 | 0 | 2.61s | sql |
| partial | 2026-07-02 09:14 | `benchmark_31b_shard` | imported ablation | `b25fe0a` | `tpu16` | 17/17 | 5 | 109.8s | report |

### 17.2 Scenarios

| Scenario | Suite | Status | Valid reps | Wall p50 | Δ | SQL reads | Render p95 | Memory slope | Artifacts |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| `query-10k-results` | Query & Results | regressed | 8/8 | 2.84s | +12.3% | 296,120 | 1.20s | — | waterfall · sql · cdp |
| `expand-tables-node-10k` | Object Explorer | investigate | 6/6 | 9.83s | +8.1% | 1,284,900 | 1.80s | — | waterfall · sql · cdp |
| `connect-local-container` | Connections | ok | 10/10 | 1.21s | +1.5% | 2,140 | — | — | waterfall |
| `connect-query-disconnect-soak` | Soak | warning | 1000/1000 | 2.91s | +3.2% | 296,120 | 1.15s | +28KB/iter | soak · samples · gc |
| `query-large-scroll-virtual-window` | Query & Results | ok | 5/5 | 4.18s | -2.5% | 512,300 | 1.60s | — | cdp · sql |
| `query-error-path` | Query & Results | ok | 4/4 | 820ms | +0.7% | 0 | 80ms | — | validation |

### 17.3 Metric names

Use realistic metric IDs:

- `scenario.wallclock.p50`
- `scenario.wallclock.p95`
- `extension.command.duration`
- `sts.rpc.query.execute.duration`
- `sqlserver.duration`
- `sqlserver.logicalReads`
- `sqlserver.roundTrips`
- `renderer.dataReceiveToPaint`
- `renderer.longestTask`
- `soak.memory.rssSlope`
- `soak.reliability.failureRate`
- `process.extensionHost.peakWorkingSet`

---

## 18. Implementation notes for codegen

Although this is a UX spec, the prototype should avoid implying impossible implementation details.

### 18.1 Data loading

The UI should be data-source agnostic. Build a provider interface mentally around:

```ts
interface PerfHistoryProvider {
  listSources(): Promise<PerfHistorySource[]>;
  openDirectory(path: string): Promise<PerfHistorySource>;
  connectSqlite(path: string, options: SqliteOpenOptions): Promise<PerfHistorySource>;
  listRuns(sourceId: string, query: RunQuery): Promise<PagedResult<PerfRunSummary>>;
  listScenarios(runSelection: RunSelection, query: ScenarioQuery): Promise<PagedResult<PerfScenarioSummary>>;
  getScenarioDetails(selection: ScenarioSelection): Promise<ScenarioDetails>;
  getArtifact(selection: ArtifactSelection): Promise<ArtifactPayload>;
}
```

### 18.2 Virtualization

Run and scenario tables can be large. Prototype can fake it, but codegen should plan for virtualization, sticky columns, and stable row selection by ID.

### 18.3 Local-only file access

A VS Code webview cannot read arbitrary local files directly. The extension host must load/index sources and send safe, redacted, typed data into the webview.

### 18.4 SQLite is a provider, not a separate UX

Do not fork the page for SQLite. The same tables/charts/tabs consume the same provider model.

### 18.5 Optional artifacts

Optional tabs should be data-driven. A scenario with no CDP trace should not render an empty Renderer tab unless the user explicitly wants to know why it is missing.

---

## 19. Acceptance criteria

The prototype is successful if a reviewer can answer these questions in under 30 seconds:

1. Where does the run history come from?
2. Which run is selected?
3. Which scenarios regressed or need attention?
4. Which metrics are official vs diagnostic?
5. What changed vs baseline?
6. Which artifacts exist for the selected scenario?
7. Can I open the waterfall for one scenario/rep?
8. Can I inspect SQL activity, renderer traces, memory/GC data, or raw data when available?
9. What is missing, partial, invalid, or low confidence?
10. How do I switch from directory history to SQLite history?

The implementation is successful when the view can load real local run history, virtualize large histories, preserve privacy/redaction, and navigate from run → scenario → metric/artifact without losing provenance.

---

## 20. Open design questions

These can remain unresolved in the prototype, but should be visible for product/design review.

1. Should **Perf Test History** be a dedicated page or a sub-view of **Perf & Sessions**?
2. Is SQLite retention the default future store, or only an optional index over directory artifacts?
3. How much editing should be allowed on run labels/tags from this view?
4. Should source indexing happen synchronously on open, lazily on demand, or in a background extension-host worker?
5. Should comparison defaults use the last pinned baseline, named baseline, rolling baseline, or nearest green run?
6. Which artifact kinds are safe to preview inline vs only open as external files?
7. Should imported bundles be persisted into local history or treated as temporary sources?
8. How much of this page should be available to end users vs internal/dev-only builds?

---

## 21. One-paragraph prompt for a prototype generator

Create a high-fidelity VS Code webview mockup for a new **Perf Test History** page inside the existing **MSSQL Debug Console**. The page has a source command bar for `Default local history`, **Open directory…**, **Connect SQLite DB…**, and **Import bundle…`; a top run-history table; a persistent left filter rail; a middle scenario table for the selected run; a right chart rail that updates for the selected scenario; and a bottom tabbed details panel with Submetrics, Waterfall, SQL Activity, Renderer, Memory/GC, CPU Trace, Artifacts, Validation, and All Data Dump. Use dense DevTools-style tables, VS Code theme tokens, monospace IDs/metrics, redacted lock treatment, official-vs-diagnostic badges, low-confidence and environment-mismatch warnings, optional artifact tabs, trend charts with baseline bands, A/B delta bars, histograms/box plots, soak memory charts with confidence bands, and a cross-process waterfall tab. Show the default loaded state, source selector, compare mode, SQL Activity tab, Waterfall tab, Memory/GC tab, and partial-source state.
