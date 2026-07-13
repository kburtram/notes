# MSSQL Debug Console UX Specification

**Artifact role:** Prototype-generation spec for a VS Code webview debug UX.

**Product name used in this spec:** MSSQL Debug Console. The name is intentionally practical, not final branding. The console is also referred to as the in-product diagnostics viewer or debug view host.

**Primary audience:** UX prototype generator, product/design reviewers, feature engineers, performance engineers, and coding agents that need an unambiguous description of the desired UI.

**Last updated:** 2026-07-02

---

## 1. Product thesis

MSSQL Debug Console is a first-party, extensible diagnostics workspace inside VS Code for the `vscode-mssql` extension. It is Chrome DevTools for the SQL tooling stack: one place to observe a user action as it moves through the extension host, webviews, SQL Tools Service, driver, and SQL Server, then inspect, compare, replay, export, and hand off the evidence.

The console has three connected jobs:

1. **Live observability:** See what the extension is doing right now, with a unified event stream and a cross-process waterfall.
2. **Historical analysis:** Open past Session Diag data, perf harness runs, completions traces, or support bundles, then aggregate across sessions and commits.
3. **Experimentation and replay:** Select interesting events or scenarios, replay them with original or overridden config, run matrices, and compare outcomes.

The product should feel native to VS Code, dense but calm, like a precision instrument with its own little cockpit. Tables, timelines, and detail panes are the core surfaces. Charts are used when they clarify differences, not to decorate the room.

---

## 2. Source inputs folded into this spec

Use these attached artifacts as the conceptual and visual foundation:

- `CLAUDE_DESIGN_INPRODUCT_DIAGNOSTICS_BRIEF.md`, especially the host shell, page list, consolidated tracing, waterfall, perf sessions, completions, replay, capture chip, classification lock, provenance panel, export bundle, and gap/backfill states.
- `MSSQL for VS Code Completions Event Instrumentation(2).pdf`, especially live completion trace, multi-session analysis, replay trace builder, config matrix, replay tags, persisted sessions, prompt/response inspection, and parameter overrides.
- `VISION_NORTH_STAR.md`, especially the single instrumentation stream, many sinks, shared contracts, shared renderers, correlation across VS Code, STS, and SQL Server, and the “never fabricate, surface gaps” invariant.
- `PERFTEST_PHASE_2_PROMPT.md`, `PERFTEST_PHASE_3_PROMPT.md`, and `PERFTEST_PHASE_4_INPRODUCT_DIAGNOSTICS.md`, especially SQL activity capture, CDP renderer tracing, soak and memory trend analysis, cross-process waterfall reports, Session Diag, privacy, and staged implementation constraints.
- `STS2_VISION_ALIGNMENT.md`, especially live-tail checkpoint gaps, capture policy, classification, replay-drive, provenance, and export bundle alignment.
- STS2 review package, especially hardening needs around replay strictness, run isolation, observer isolation, export coherence, host capture policy, and exact gap metadata.
- `benchmark.html`, `diagnostics.html`, `bench1.png`, `bench2.png`, and `bench3.png`, especially KPI cards, filterable errors table, small-multiple comparisons, time-split stacked bars, trace waterfall, phase totals side panel, tool explorer, latency strip, Gantt, aggregate pivot, and per-run diagnostics.

---

## 3. Design principles

### 3.1 One console, many pages

The console is a host. Individual features contribute pages and panels. Common views such as Consolidated Tracing, Cross-Process Waterfall, Perf & Sessions, Completions, and Replay are built in. Feature pages such as Connection, Query, Results Grid, Object Explorer, and SQL Activity plug into the same shell.

### 3.2 Live and historical parity

Every primary view supports a live stream and historical sessions. A developer should be able to watch an event happen, close VS Code, reopen it later, and inspect the same evidence.

### 3.3 Data honesty is visible

The UI never hides uncertainty. If a live stream dropped events, the table shows the exact gap and offers backfill. If cross-process time is aligned by clocks rather than exact monotonic measurement, the timeline shows that as diagnostic alignment. If a metric is low confidence, the chart says so.

### 3.4 Capture is explicit

Normal-use diagnostics are real user data. Capture is opt-in, local, classified, redacted, retention-capped, and clearable. Capture elevation is explicit, time-bounded, and visible in the top bar.

### 3.5 Classification is mechanical

Sensitive values are rendered consistently everywhere: lock icon, redacted preview, digest where allowed, and explanation of the governing policy. SQL text, row values, connection strings, tokens, and secrets are not casually displayed.

### 3.6 Dense, not noisy

The console favors compact rows, narrow chrome, stable filters, and a strong visual hierarchy. KPI cards and charts are allowed, but the UX should never balloon into a consumer dashboard.

### 3.7 Reuse over reinvention

The completions debug view is the reference interaction model: live trace table, detail pane tabs, multi-session grouping, replay trace builder, matrix runs, and replay tags. The new console generalizes that pattern across the extension.

---

## 4. Users and jobs to be done

### 4.1 Extension engineer

**Goal:** Debug a feature implementation while actively using VS Code.

**Key needs:** Live event trace, payload inspection, correlation chains, feature state, perf timings, errors, gap handling, parameter overrides, replay.

### 4.2 Performance engineer

**Goal:** Investigate latency, memory growth, renderer costs, SQL activity, and regressions across runs.

**Key needs:** Waterfall, metrics, distributions, soak trends, A/B diffs, SQL activity deltas, process memory, render phases, baseline bands.

### 4.3 Support engineer

**Goal:** Open a user-provided evidence bundle and find a credible explanation without seeing unnecessary private data.

**Key needs:** Provenance, privacy report, redacted events, export manifest, errors, user-visible scenarios, bundle integrity.

### 4.4 AI coding agent

**Goal:** Consume structured runtime evidence to reproduce, localize, and fix issues.

**Key needs:** Exportable event model, correlation IDs, gap metadata, artifacts, replay provenance, cause trees, stable schemas.

### 4.5 End user capturing a bug

**Goal:** Turn on Session Diag, reproduce a bug, export a safe bundle, and clear local diagnostics.

**Key needs:** Simple capture controls, privacy explanation, export workflow, storage controls, no accidental upload.

---

## 5. Information architecture

### 5.1 Navigation model

Use a left rail for page families with pinned common pages first. A horizontal tab strip may be used inside each page for subviews.

Primary top-level pages:

1. **Overview**
2. **Consolidated Trace**
3. **Waterfall**
4. **Perf & Sessions**
5. **Completions**
6. **Replay Lab**
7. **SQL Activity**
8. **Connections**
9. **Query & Results**
10. **Object Explorer**
11. **Exports**
12. **Settings**

Prototype note: the original design brief names five core host pages: Consolidated Tracing, Cross-Process Waterfall, Perf & Sessions, Completions, Replay. The extra pages are extensibility examples and feature-specific pages that should still use the same shell.

### 5.2 Suggested left rail labels and icons

| Page | Label | Icon metaphor | Primary job |
|---|---|---|---|
| Overview | Overview | pulse or dashboard | session triage |
| Consolidated Trace | Trace | list-tree | search every event |
| Waterfall | Waterfall | timeline | explain one user action |
| Perf & Sessions | Perf | chart | compare sessions and runs |
| Completions | Completions | sparkle/inline-suggest | preserve existing debug workflow |
| Replay Lab | Replay | loop/experiment | rebuild, override, matrix-run |
| SQL Activity | SQL | database/log | command-level SQL details |
| Connections | Connections | plug | connection lifecycle |
| Query & Results | Query | play/table | query and grid rendering |
| Object Explorer | Object Explorer | tree | OE expansion and refresh |
| Exports | Exports | package | bundle and bug reports |
| Settings | Settings | gear | capture, storage, privacy |

---

## 6. Global shell

### 6.1 Shell frame

Use this visual structure in prototypes:

```text
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ MSSQL Debug Console   [Session: current ▾] [Live ●] [Capture: Redacted 🔒 ▾] [Search...]   │
│                       [Backfill 0 gaps] [Export] [Clear] [Settings]                       │
├──────────────┬─────────────────────────────────────────────────────────────────────────────┤
│ Overview     │ Page-specific toolbar                                                       │
│ Trace        ├─────────────────────────────────────────────────────────────────────────────┤
│ Waterfall    │ Page body                                                                    │
│ Perf         │                                                                              │
│ Completions  │                                                                              │
│ Replay       │                                                                              │
│ SQL Activity │                                                                              │
│ Connections  │                                                                              │
│ Query        │                                                                              │
│ OE           │                                                                              │
│ Exports      │                                                                              │
│ Settings     │                                                                              │
└──────────────┴─────────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Top bar required elements

**Product title:** `MSSQL Debug Console`.

**Session/run selector:** shows current session name, source, timestamp, and mode.

Examples:

- `Current VS Code Session`
- `Session 2026-07-02 14:02:13`
- `Bug bundle: support-2026-07-01.zip`
- `Perf run: query-10k / candidate 7f3c2b1`

**Live/historical toggle:** two-state segmented control.

- `Live` shows stream status and latest seq.
- `History` opens session selector and persisted stores.

**Capture-mode/privacy chip:** always visible.

States:

| State | Chip copy | Visual treatment |
|---|---|---|
| Off | `Capture off` | neutral gray outline |
| Redacted | `Capture: redacted` | lock icon, neutral |
| Digest | `Capture: digest` | lock icon, blue/neutral |
| Full, time bounded | `Full capture: 04:32 left` | warning accent, countdown |
| Policy blocked | `Full capture blocked` | warning accent with info icon |

**Global search:** query across event IDs, types, features, SQL digests, error codes, session names, and correlation IDs. Search never reveals redacted content.

**Export button:** opens Export Evidence Bundle modal.

**Gap indicator:** global count of known live-tail gaps in current session. Example: `Backfill 2 gaps`.

### 6.3 Page toolbar behavior

Each page can contribute toolbar controls after the global controls. Common page controls should appear in a predictable order:

1. Source scope selector
2. Scenario or feature selector
3. Time range selector
4. Group-by selector
5. Filter chips
6. View mode toggles
7. Refresh/backfill actions
8. Export or copy action

---

## 7. Visual design system

### 7.1 Theme integration

Use VS Code theme tokens rather than fixed colors. Prototype can approximate tokens, but component names should map to these roles:

| Role | Suggested VS Code token |
|---|---|
| App background | `--vscode-editor-background` |
| Panel background | `--vscode-sideBar-background` or `--vscode-editorWidget-background` |
| Raised panel | `--vscode-editorHoverWidget-background` |
| Border | `--vscode-panel-border` |
| Text primary | `--vscode-foreground` |
| Text muted | `--vscode-descriptionForeground` |
| Link / selected | `--vscode-textLink-foreground` |
| Focus outline | `--vscode-focusBorder` |
| Error | `--vscode-errorForeground` |
| Warning | `--vscode-editorWarning-foreground` |
| Success | use theme-safe green token fallback |
| Badge background | `--vscode-badge-background` |
| Badge foreground | `--vscode-badge-foreground` |
| Input background | `--vscode-input-background` |
| Input border | `--vscode-input-border` |

### 7.2 Typography

Use VS Code’s default UI font for labels and chrome. Use monospace for:

- event IDs
- sequence numbers
- timestamps
- durations
- SQL snippets and digests
- payload JSON
- correlation IDs
- commit hashes
- process IDs

Type scale:

| Token | Size | Use |
|---|---:|---|
| `title` | 20 px | page title in empty states only |
| `sectionTitle` | 13 px, semibold | panels, cards |
| `body` | 12 px | rows, details |
| `caption` | 11 px | muted secondary copy |
| `monoBody` | 12 px | data fields |
| `monoTiny` | 11 px | table metadata |
| `kpi` | 18 to 22 px | KPI values |

### 7.3 Density and spacing

- Table row height: 24 px compact, 30 px comfortable.
- KPI card: 112 px minimum width, 72 px height.
- Toolbar height: 36 px.
- Tabs height: 28 px.
- Left rail width: 152 px default, collapsible to icons.
- Detail pane min width: 360 px.
- Split pane default: 60 percent list, 40 percent detail.

### 7.4 Color semantics

Status colors are semantic and theme-safe.

| Semantic | Usage |
|---|---|
| Green | completed, ok, passed validation |
| Amber | warning, degraded, partial, human review, diagnostic-only timing |
| Red | failed, exception, blocked, missing required marker |
| Blue | info, selected, live, links |
| Purple | tool calls, replay, experiment |
| Teal | extension or agent step |
| Orange | queue or backpressure |
| Slate | neutral, agent bookkeeping, unknown |

Process colors should be consistent across pages:

| Process | Color role |
|---|---|
| Extension Host | teal |
| Webview / Renderer | blue |
| SQL Tools Service | purple |
| SQL Server | green |
| Harness / Driver | slate |
| Network / wire | orange |

### 7.5 Timeline interval styles

The waterfall MUST visually distinguish timing precision:

| Timing class | Meaning | Visual style |
|---|---|---|
| Official measured | Same-process monotonic interval, exact enough for official metric | solid bar |
| Product timer | Product marker pair, official if measurement pass and success proof passed | solid bar with fine outline |
| Epoch-aligned diagnostic | Cross-process alignment using clock calibration | hatched or translucent bar |
| Diagnostic collector | CDP, XEvents, process sampler, heap, or dotnet-counters | hatched/translucent with collector icon |
| Inferred | Derived relation with confidence | dotted outline, never solid |

---

## 8. Shared components

### 8.1 KPI card row

Use KPI cards for top-level triage, adapted from the benchmark report samples.

Card anatomy:

- Label, uppercase or muted small caps.
- Large value.
- Secondary note.
- Optional status color.
- Optional sparkline.

Example cards:

- `Events`, `18,421`, `2 gaps`
- `Errors`, `11`, `0 privacy leaks`
- `Wall-clock`, `2.84s`, `UI 430ms / STS 1.8s`
- `SQL reads`, `296k`, `+42% vs baseline`
- `Render`, `412ms`, `paint 84ms`
- `Memory slope`, `+28KB/iter`, `stable, R² .19`

### 8.2 Filter rail

A reusable compact filter row or side rail.

Controls:

- Search text.
- Process multi-select.
- Feature multi-select.
- Kind/type multi-select.
- Status severity.
- Correlation ID.
- Time range.
- Capture class.
- Source session/run.
- Replay provenance.

Filters appear as removable chips once set. Keyboard shortcut `Ctrl/Cmd+F` focuses search within the page, not the editor.

### 8.3 List plus detail split pane

The workhorse component.

List/table side:

- Virtualized rows.
- Sticky header.
- Columns can be resized and hidden.
- Selected row persists while filters change if still visible.
- Row count and filtered count appear in toolbar.

Detail side:

- Tabs with consistent ordering: `Summary`, `Payload`, `Cause`, `Timeline`, `Privacy`, `Raw`, `Actions`.
- Redaction controls appear only when policy allows.
- Copy actions copy redacted values by default.
- “Reveal sensitive” requires explicit per-session elevation and should not be available in normal redacted mode.

### 8.4 Event row

Columns for generalized event rows:

1. Time
2. Seq
3. Process
4. Feature
5. Kind
6. Type
7. Correlation
8. Duration
9. Status
10. Flags

Visual row details:

- Left process color stripe.
- Replay tag when `provenance.kind = replay`.
- Lock badge if selected payload contains redacted data.
- Gap markers are rows, not toast notifications.
- Diagnostic-only rows use a subtle hatched icon or `diag` pill.

### 8.5 Detail pane tabs

**Summary tab**

- Event name, status, duration, start/end.
- Process, feature, category.
- Correlation ID, parent cause ID, entity refs.
- Classification summary.
- Related artifacts.

**Payload tab**

- Structured key/value view first.
- JSON view second.
- Redacted fields rendered with lock + reason.

**Cause tab**

- Tree of ancestor and descendant events.
- Clicking a node selects it in the table and highlights it in the waterfall.

**Timeline tab**

- Mini waterfall around selected event with 250ms before/after default window.

**Privacy tab**

- Classification per field.
- Capture policy that applied.
- Redaction method: omitted, digest, tokenized, truncated.
- Elevation affordance if allowed.

**Raw tab**

- Raw envelope exactly as stored, with redactions applied.

**Actions tab**

- Add to Replay Trace.
- Copy event ID.
- Copy correlation ID.
- Filter by this correlation.
- Export selected slice.
- Open source artifact.

### 8.6 Capture-mode chip

The capture chip is both status and control.

Click opens a small popover:

- Current mode.
- What is captured.
- What is redacted.
- Storage location.
- Retention cap.
- Elevate capture button if allowed.
- Revert now button if capture is elevated.
- Open Settings link.

Elevation modal copy:

> Full capture may include SQL text, schema names, or row values. It remains local and time-bounded. Choose a duration and reason.

Fields:

- Capture mode: digest, full SQL text, full row values if allowed.
- Duration: 5 min, 15 min, 30 min, custom.
- Reason: required text.
- Scope: current session, current connection, current feature.
- Confirm button: `Start elevated capture`.

### 8.7 Classification lock

A redacted field renders like this:

```text
🔒 SQL text redacted  digest: sql:sha256:8fd2...  [why?]
```

Clicking `why?` opens a tooltip:

- Classification: `sql.text`
- Capture policy: `digest`
- Reason: `Session Diag redacted mode`
- To reveal: `Elevate capture for current session` if allowed, otherwise `Blocked by host policy`.

### 8.8 Gap/backfill marker

Gap marker row in tables:

```text
▸ 214 events dropped from seq 10432 to 10645  [Backfill from journal]
```

Expanded state:

```text
Backfilling 214 events from local journal...
[progress bar]
Recovered 214 events. Inserted at original sequence positions.
```

If backfill fails:

```text
Could not backfill seq 10432-10645. Journal segment is unavailable.
[Open diagnostics] [Export gap report]
```

This is not an error row unless recovery fails. The first-class marker is a little honesty lantern in the fog.

### 8.9 Provenance drawer

A right-side drawer available from top bar and all pages.

Sections:

- Session ID.
- Source: live, local store, perf run, bundle, replay.
- Started/ended.
- VS Code version.
- `vscode-mssql` commit, branch, dirty state.
- SQL Tools Service version and commit.
- Environment fingerprint.
- Capture policy.
- Store path.
- Retention.
- Export manifest.
- Replay source if applicable.

### 8.10 Export Evidence Bundle modal

Steps:

1. **Scope:** entire session, selected time range, selected correlation, selected events, or current replay result.
2. **Privacy:** redacted default, include digests, include full SQL only if policy allows, include row samples only if policy allows.
3. **Contents:** events, artifacts, renderer trace, SQL activity, process samples, screenshots, provenance, privacy report.
4. **Validation:** snapshot consistency, gap summary, redaction scan, manifest hashes.
5. **Save:** choose local path.

Confirmation state:

```text
Bundle ready: mssql-session-2026-07-02T14-02-13.zip
Contains 12,481 events, 0 unresolved gaps, 31 redactions, 4 artifacts.
```

---

## 9. Global states and microcopy

### 9.1 Capture off empty state

Title: `Session diagnostics are off`

Body: `Turn on local Session Diag to capture classified, redacted traces for this VS Code session. Nothing is uploaded.`

Actions: `Enable redacted capture`, `Open docs`, `Import bundle`.

### 9.2 No historical data

Title: `No saved sessions yet`

Body: `Run with Session Diag enabled or import an evidence bundle.`

### 9.3 Loading

Use skeleton table rows and subtle progress line. Avoid spinners for long journal loads. Show count as records load.

### 9.4 Gap exists

Banner text: `This live stream has 2 known gaps. Backfill is available from the local journal.`

Actions: `Backfill all`, `Show gaps`.

### 9.5 Policy blocked

Tooltip: `This field is classified as row data. Current host policy allows digest only. It cannot be revealed in this session.`

### 9.6 Missing collector

Example: `Renderer trace unavailable: webview target was not found. No render metric was emitted.`

### 9.7 Diagnostic-only metric

Example: `Diagnostic metric. It can explain behavior but does not gate regressions.`

### 9.8 Replay blocked

Example: `Replay is not available for this event type until the feature adapter declares a deterministic replay contract.`

---

## 10. Page specification: Overview

### 10.1 Purpose

A quick session triage surface. It answers: Is capture on? Are there errors? What is slow? What changed? What should I click first?

### 10.2 Layout

Top: KPI card grid.

Middle left: Recent user actions list.

Middle right: Anomaly cards.

Bottom: Recent sessions and exports.

### 10.3 KPI cards

Use 8 to 12 cards, responsive wrap:

- Events
- Errors
- Warnings
- Gaps
- Slowest action
- SQL commands
- Renderer time
- Memory peak
- Active capture mode
- Replay runs
- Exports

### 10.4 Recent user actions table

Columns:

- Start time
- Action
- Feature
- Duration
- Status
- SQL commands
- Render
- Gaps

Example rows:

| Start | Action | Feature | Duration | Status | SQL | Render | Gaps |
|---|---|---|---:|---|---:|---:|---:|
| 14:02:41.118 | Run query | Query | 2.84s | ok | 4 | 412ms | 0 |
| 14:03:10.445 | Expand Tables | OE | 9.83s | warning | 21 | 1.8s | 1 |
| 14:03:22.004 | Completion | Completions | 621ms | skipped | 0 | 0ms | 0 |

### 10.5 Anomaly cards

Examples:

- `1 live-tail gap in Object Explorer expansion`
- `SQL logical reads +42% vs baseline`
- `Renderer longest task 390ms in Results Grid`
- `Replay matrix cell failed: focused x generous x E-2`

Each card links to the relevant page and applies filters.

---

## 11. Page specification: Consolidated Trace

### 11.1 Purpose

A universal event stream across all features and processes, live or historical. This is the row-level truth table.

### 11.2 Layout

```text
Toolbar: [Search] [Process] [Feature] [Kind] [Status] [Correlation] [Group by] [Backfill]
┌─────────────────────────────────────────────────────────────┬───────────────────────────────┐
│ Event table                                                   │ Detail pane                    │
│ Time  Seq  Proc Feature Kind Type Corr Duration Status Flags  │ Summary | Payload | Cause ... │
│ ...                                                           │                               │
└─────────────────────────────────────────────────────────────┴───────────────────────────────┘
```

### 11.3 Default columns

| Column | Width | Behavior |
|---|---:|---|
| Time | 90 | local time or relative time toggle |
| Seq | 64 | monospace, sortable |
| Process | 110 | colored process pill |
| Feature | 110 | feature pill |
| Kind | 96 | event/span/metric/request/response/log |
| Type | 180 | main searchable label |
| Correlation | 140 | copyable, filterable |
| Duration | 80 | hidden for instantaneous events |
| Status | 80 | ok/warn/error/blocked |
| Flags | 120 | diag, replay, lock, gap, artifact |

### 11.4 Row kinds

| Kind | Example type | Visual treatment |
|---|---|---|
| Event | `mssql.connection.ready` | small dot |
| Span start/end | `mssql.query.execute` | linked duration |
| Metric | `process.memory.heapUsed` | chart glyph |
| Request | `sts.rpc.connection.open` | request arrow |
| Response | `sts.rpc.connection.open.result` | response arrow |
| SQL activity | `sql.rpc_completed` | database icon |
| Render phase | `renderer.paint` | renderer icon |
| Gap marker | `liveTail.gap` | full-width marker row |

### 11.5 Grouping modes

- None.
- By correlation.
- By feature.
- By process.
- By severity.
- By replay run.
- By scenario.

When grouped by correlation, show a collapsible top row:

```text
▾ corr a83f...  Run query  2.84s  18 events  Extension → STS → SQL → Webview
```

### 11.6 Detail pane

Tabs:

1. Summary
2. Payload
3. Cause
4. Timeline
5. Privacy
6. Raw
7. Actions

The Cause tab must support ancestors and descendants. Use arrows and indentation:

```text
User action: Run query
  causes extension command mssql.runQuery
    causes STS rpc query.execute
      causes SQL batch SELECT TOP 10000...
      causes webview resultDataReceived
        causes renderer layout
        causes resultsGrid.renderComplete
```

### 11.7 Required interactions

- Click row: select event.
- Double click row: open detail pane and focus Summary.
- Click correlation: filter by correlation.
- Hover redacted field: show classification tooltip.
- Click gap marker: expand gap and backfill.
- Press `F`: focus filter search.
- Press `C`: copy correlation ID.
- Press `R`: add selected event to Replay Lab if replayable.

### 11.8 Prototype sample data

Use rows like:

| Time | Seq | Process | Feature | Kind | Type | Duration | Status |
|---|---:|---|---|---|---|---:|---|
| 14:02:41.118 | 10430 | Extension | Query | event | `command.mssql.runQuery.begin` | | ok |
| 14:02:41.122 | 10431 | Extension | Query | span | `query.submit` | 12ms | ok |
| gap | 10432-10645 | Live tail | system | gap | `events dropped` | | warn |
| 14:02:41.246 | 10646 | STS | Query | rpc | `query.execute` | 1.92s | ok |
| 14:02:42.384 | 10651 | SQL Server | Query | sql | `sql_batch_completed` | 1.43s | ok |
| 14:02:43.002 | 10663 | Webview | Results | render | `resultsGrid.renderComplete` | 412ms | ok |

---

## 12. Page specification: Cross-Process Waterfall

### 12.1 Purpose

The headline view. One user action decomposed across extension host, webview, STS, SQL Server, renderer, and optionally harness. It answers: Where did the time go, what caused what, and how reliable is the timing?

### 12.2 Layout

```text
Toolbar: [Action/correlation selector] [Time range] [Show diag] [Critical path] [Export SVG]
Summary strip: total wall-clock | UI | extension | STS | wire | server | renderer
Legend: solid official | hatched diagnostic aligned | dotted inferred | lock redacted
┌─────────────────────────────────────────────────────────────────────────┐
│ Time axis with zoom / scrub                                             │
├────────────────────┬────────────────────────────────────────────────────┤
│ Extension Host     │ █ command.begin █████ query.submit █ command.end    │
│ Webview/Renderer   │              ▧ data recv ▧ layout ▧ paint █ render  │
│ SQL Tools Service  │        ▧ rpc handler █ driver execute █ serialize   │
│ SQL Server         │             ▧ batch completed ▧ reads/cpu           │
│ Process samples    │ memory/cpu counter overlay                          │
└────────────────────┴────────────────────────────────────────────────────┘
Detail inspector below or right.
```

### 12.3 Summary strip

A compact stacked bar above the timeline.

Segments:

- UI input to command dispatch.
- Extension host handling.
- STS RPC handling.
- Wire/driver wait if available.
- SQL Server execution.
- Result grid render.
- Agent or harness overhead when imported from perf runs.

Each segment is clickable and filters timeline bars.

### 12.4 Time axis

Controls:

- Zoom with mouse wheel or trackpad.
- Drag scrubber to pan.
- Double click to zoom to selected span.
- `Fit action` button.
- `Fit selected` button.

Time labels show both relative time and absolute timestamp on hover.

### 12.5 Lanes

Required lanes:

1. User action
2. Extension host
3. Webview / renderer
4. SQL Tools Service
5. Driver / network
6. SQL Server
7. Process counters
8. Diagnostics collectors

Lanes can be hidden. Hidden lanes show a pill in the legend.

### 12.6 Bars

Bar tooltip fields:

- Name.
- Start, end, duration.
- Timing class: official measured, aligned diagnostic, inferred.
- Process and thread if known.
- Correlation ID.
- Cause ID.
- Classification summary.
- Source artifact.
- Confidence and clock calibration jitter for aligned bars.

### 12.7 Bar styles

- Official same-process spans: solid fill.
- Cross-process aligned spans: hatched fill.
- Diagnostic collectors: translucent hatch with collector icon.
- Inferred spans: dotted outline.
- Selected correlation: bright outline and connection lines.
- Critical path: amplified outline or glow that respects VS Code theme.

### 12.8 Correlation lines

Lines connect cause/child relationships:

- VS Code command to STS RPC handler.
- STS RPC to SQL command.
- STS response to webview data receive.
- Webview data receive to renderer render complete.

If the relation is based on timing only, line is dotted and labeled `inferred`.

### 12.9 Critical path mode

When enabled:

- Highlight bars contributing to end-to-end latency.
- Dim unrelated background events.
- Show a side panel with ordered steps and durations.

Example critical path panel:

```text
Critical path, 2.84s total
1. command.mssql.runQuery.begin        8ms
2. STS query.execute                   1.92s
3. SQL batch completed                 1.43s, overlaps STS
4. Results webview data receive        44ms
5. Grid render complete                412ms
```

### 12.10 Calibration and confidence display

Display a subtle timing confidence line below the legend:

```text
Cross-process alignment: exthost ±1.4ms, STS ±3.2ms, webview ±2.0ms. Solid bars use same-process monotonic clocks. Hatched bars are epoch-aligned diagnostics.
```

### 12.11 Detail inspector

Tabs:

- Summary
- Related events
- Payload
- SQL activity
- Renderer detail
- Raw artifacts

When a SQL command is selected, show SQL metrics: duration, CPU, logical reads, physical reads, writes, row count, application name, session ID, request ID, SQL digest, text redaction state.

---

## 13. Page specification: Perf & Sessions

### 13.1 Purpose

Analyze performance across sessions, runs, scenarios, commits, and replay experiments.

### 13.2 Layout

```text
Toolbar: [Source: sessions/runs/bundles] [Scenario] [Metric] [Group by] [Baseline] [Compare]
KPI cards
┌───────────────────────────────┬───────────────────────────────┐
│ Latency distribution           │ Cross-session trend            │
├───────────────────────────────┼───────────────────────────────┤
│ A/B delta bars                 │ Soak memory trend              │
├───────────────────────────────┴───────────────────────────────┤
│ SQL activity table and diagnostic deltas                       │
└────────────────────────────────────────────────────────────────┘
```

### 13.3 Required chart panels

1. Latency histogram or box plot for selected scenario and metric.
2. Cross-session time series by run, commit, or timestamp with baseline band.
3. A/B delta bars per metric.
4. Soak RSS versus iteration with fitted slope, confidence band, R², sample count.
5. Latency versus iteration drift.
6. SQL activity top-N by duration, CPU, reads.
7. Render time breakdown: scripting, layout, paint, longest task.
8. Memory and CPU peak by process.

### 13.4 KPI cards

Example:

- `Runs`, `31`, `last 7 days`
- `Median latency`, `2.84s`, `+310ms vs baseline`
- `p95 latency`, `8.22s`, `small-n: 8 reps`
- `SQL reads`, `296k`, `+3 round trips`
- `Render p95`, `1.2s`, `renderer diag`
- `Memory slope`, `+28KB/iter`, `stable`
- `Regressions`, `2`, `official only`

### 13.5 Metric table

Columns:

- Metric
- Candidate median
- Baseline median
- Delta
- Percent
- Verdict
- Official
- Confidence
- Small-n
- Link to evidence

### 13.6 SQL activity table

Columns:

- Command index
- Source session/run
- Event type
- Duration
- CPU
- Logical reads
- Physical reads
- Writes
- Rows
- App name/correlation
- SQL digest/text
- Status

SQL text is redacted unless capture policy allows. Diagnostics from synthetic perf harness can show full SQL if explicitly marked synthetic.

### 13.7 A/B comparison view

Show two columns: baseline and candidate. Diagnostic deltas appear under an “Investigation” section and never gate by themselves.

Example investigation callout:

```text
Candidate added 3 SQL commands and +296k logical reads during Object Explorer refresh.
Official latency verdict: REGRESSED.
Diagnostic explanation: likely extra SMO enumeration query.
```

### 13.8 Trend details

Trend line interactions:

- Hover point: show run metadata and value.
- Click point: open run in Overview.
- Click step-change marker: open diff between previous green run and selected run.
- Baseline band toggle.
- Environment hash mismatch warning.

---

## 14. Page specification: Completions

### 14.1 Purpose

Re-house the existing completions debug experience inside the shared host and reuse it as the reference page.

### 14.2 Live trace subview

Top strip:

- Recording status.
- Current model.
- Profile.
- Schema budget.
- Events count.
- Average latency.
- Acceptance/skipped/canceled counts.
- Replay tags count.

Table columns:

- Time
- Document
- Line:Col
- Trigger
- Mode
- Model
- Latency
- Tokens in/out
- Result
- Info

Detail tabs:

1. Summary
2. System Prompt
3. User Prompt
4. Raw Response
5. Sanitized
6. Schema Context
7. Locals
8. Telemetry
9. Replay provenance
10. Privacy

### 14.3 Multi-session analysis subview

Use the attached completions PDF as the pattern.

Left filters:

- Model.
- Profile.
- Schema budget.
- Trigger mode.
- Result.
- Replay source.

Main table group-by:

- Model.
- Profile.
- Schema budget.
- Feature flags.
- Replay matrix cell.

Charts:

- Latency p95 by group.
- Acceptance funnel.
- Token cost in/out.
- Latency time series.
- Error rate.

### 14.4 Replay integration

Selected completion events can be added to Replay Lab. Replayed completions appear in live trace with tags:

- `replayTraceId`
- `replayRunId`
- `matrixCellId`
- `sourceEventId`
- overrides

Replay-generated rows should be filterable and visually tagged but not hidden from normal live stream.

---

## 15. Page specification: Replay Lab

### 15.1 Purpose

Generalize the completions replay builder for any feature that declares a replay adapter. The lab supports ordered traces, per-event config overrides, matrix expansion, run queueing, result tagging, and comparison.

### 15.2 Replay trace builder layout

```text
Header: Replay Trace Builder   3 events   est. 41s sequential
Toolbar: [Use live] [Reverse order] [Clear] [Run] [Matrix]
Table: # | Source | Feature | Event | Config | State | Preview | Actions
Bottom split: Edit config | Captured snapshot / payload
```

### 15.3 Event row states

- Snapshot: original captured config.
- Override: row-level overrides.
- Live: uses current settings.
- Blocked: replay adapter unavailable.
- Unsafe: capture policy or data class blocks replay.

### 15.4 Config matrix layout

Two or three selector panels:

- Profiles/params.
- Schema budgets/capture modes.
- Feature-specific dimensions, for example completion model or connection target.

Summary strip:

- Total events.
- Matrix cells.
- Estimated time.
- Replay mode.
- Required capture level.

Execution order preview:

```text
cell 1/4 Balanced x Balanced -> events 1..3
cell 2/4 Balanced x Generous -> events 1..3
cell 3/4 Focused x Balanced -> events 1..3
cell 4/4 Focused x Generous -> events 1..3
```

### 15.5 Replay results view

After running, show:

- Run queue with progress.
- Live events tagged in Consolidated Trace.
- Matrix result grid.
- Metrics by cell.
- Diff against source events.
- Failure reasons.
- Export selected results.

### 15.6 Replay gating UX

If STS-backed replay is not hardened:

```text
Replay unavailable for Query because STS replay-drive is not enabled for this feature. You can still export the event slice or add it to a manual reproduction bundle.
```

If capture policy blocks replay:

```text
This event depends on data captured as digest only. Replay requires either a deterministic fixture or a feature adapter that can operate from digests.
```

---

## 16. Page specification: SQL Activity

### 16.1 Purpose

Expose every SQL command caused by a scenario, connection, query, OE action, or session slice, with full performance stats and redaction.

### 16.2 Layout

Top: SQL activity KPI cards.

Main: sortable SQL command table.

Detail: selected command with metrics, redacted SQL text/digest, query plan artifact if available, and correlation chain.

### 16.3 KPI cards

- Commands.
- Total SQL duration.
- CPU.
- Logical reads.
- Physical reads.
- Writes.
- Rows.
- Extra round trips vs baseline.

### 16.4 Table columns

- Time.
- Correlation.
- Command type.
- Duration.
- CPU.
- Logical reads.
- Physical reads.
- Writes.
- Row count.
- App name.
- Session ID.
- Request ID.
- SQL digest/text.
- Confidence.

### 16.5 Detail tabs

- Summary.
- SQL text.
- Statistics.
- Plan.
- Cause.
- Raw event.
- Privacy.

### 16.6 Redaction behavior

Default SQL text presentation:

```text
🔒 SQL text redacted
Digest: sql:sha256:8fd2c91a...
Stats: duration 1.43s, CPU 920ms, logical reads 296,120, rows 10,000
```

---

## 17. Page specification: Connections

### 17.1 Purpose

Explain connection lifecycle, STS spawn/health, connection profile shape, authentication timings, pooling, disconnect, reconnect, and failures.

### 17.2 Panels

- Connection timeline.
- STS lifecycle card: PID, start time, version, health, fatal state.
- Active connections table.
- Recent failures.
- Environment/provenance.
- Replay eligibility.

### 17.3 Connection table columns

- Connection ID.
- Server, redacted or digest.
- Database, redacted or digest.
- Auth type, safe category only.
- Created.
- Ready duration.
- Status.
- STS session.
- Correlation.

### 17.4 Detail tabs

- Summary.
- Timeline.
- Profile classification.
- STS RPCs.
- SQL activity.
- Errors.
- Raw.

---

## 18. Page specification: Query & Results

### 18.1 Purpose

Debug query execution, result streaming, grid rendering, cancellation, row count validation, large results, virtualized scrolling, and webview performance.

### 18.2 Panels

- Query timeline.
- Results grid render breakdown.
- Result sets table.
- Row count proof.
- CDP renderer trace summary.
- SQL activity.
- Webview postMessage events.

### 18.3 Result sets table columns

- Result set index.
- Columns.
- Rows expected.
- Rows rendered.
- Render complete.
- Window fetches.
- Bytes.
- Status.

### 18.4 Large-result and virtual windowing states

If virtual windowing is triggered:

```text
Virtual windowing active: 8 windows fetched, offsets 0, 10k, 25k, 50k, 75k, 99k.
```

If not triggered but expected:

```text
Expected virtual windowing marker was not observed. Scenario marked invalid.
```

---

## 19. Page specification: Object Explorer

### 19.1 Purpose

Debug OE tree expansion, refresh, large catalogs, metadata queries, object counts, and renderer costs.

### 19.2 Panels

- Tree action timeline.
- Object count proofs.
- SMO/SQL activity table.
- Renderer tree paint breakdown.
- Cache state.
- Errors and partial loads.

### 19.3 Object count proof card

Example:

```text
Tables node expanded
Expected: 10,000 tables
Rendered: 10,000 tables
Truncation: none
Duration: 9.83s
SQL commands: 21
Renderer: 1.8s
```

---

## 20. Page specification: Exports

### 20.1 Purpose

Create and inspect evidence bundles. Show privacy report and manifest health.

### 20.2 Layout

- Recent exports table.
- Create export button.
- Import bundle button.
- Bundle detail inspector.
- Privacy report.
- Validation report.

### 20.3 Recent exports columns

- Created.
- Source session.
- Scope.
- Events.
- Redactions.
- Gaps.
- Size.
- Validation.
- Path.

### 20.4 Bundle detail

Tabs:

- Summary.
- Manifest.
- Privacy report.
- Redactions.
- Provenance.
- Artifacts.
- Validation.

---

## 21. Page specification: Settings

### 21.1 Purpose

Control Session Diag capture, retention, storage, feature pages, privacy, and export policy.

### 21.2 Settings sections

1. Session Diag capture.
2. Capture mode and policy.
3. Retention and storage caps.
4. Sensitive data handling.
5. Export defaults.
6. Page/plugin visibility.
7. Developer/experimental flags.
8. Diagnostics store location.

### 21.3 Required controls

- Enable Session Diag.
- Default capture mode: off, redacted, digest.
- Retention: count, days, disk cap.
- Clear all local diagnostics.
- Open diagnostics folder.
- Show privacy explanation.
- Enable experimental STS2 Session Diag source, disabled by default until hardening.
- Enable replay lab, with feature adapter list.

---

## 22. End-to-end workflows

### 22.1 Capture and export a bug report

1. User opens MSSQL Debug Console.
2. Top bar shows `Capture off`.
3. User clicks chip and selects `Enable redacted capture`.
4. User reproduces connection/query/OE bug.
5. Overview shows error anomaly.
6. User clicks anomaly to open Consolidated Trace filtered by correlation.
7. User clicks `Export`.
8. Export modal defaults to redacted bundle.
9. Validation confirms manifest, privacy, and gap status.
10. User saves bundle and optionally clears local data.

### 22.2 Investigate a slow query

1. Engineer opens Waterfall.
2. Selects latest `Run query` action.
3. Summary strip shows total 2.84s.
4. STS lane and SQL Server lane show overlapping long bars.
5. SQL Activity tab shows 296k logical reads.
6. Results lane shows render complete 412ms.
7. Engineer opens Perf & Sessions and compares against baseline.
8. A/B diff shows extra SQL commands or reads.

### 22.3 Diagnose dropped live events

1. Trace table shows `214 events dropped` marker.
2. User expands marker.
3. UI loads missing range from journal.
4. Rows are inserted in sequence.
5. Global gap indicator decreases.
6. If missing, export gap report records exact unavailable range.

### 22.4 Replay completions across configurations

1. Engineer filters Completions to high-latency skipped events.
2. Adds three events to Replay Lab.
3. Sets event 2 profile override to Focused.
4. Opens matrix and selects profiles Focused/Balanced and budgets Balanced/Generous.
5. UI estimates 12 completion requests and 41s.
6. Starts matrix run.
7. Live trace shows replay-tagged rows.
8. Multi-session analysis filters by replay matrix cell.

### 22.5 Hand off to a coding agent

1. Engineer selects a correlation or failed scenario.
2. Exports evidence bundle.
3. Bundle includes redacted events, artifacts, provenance, privacy report, and gap metadata.
4. Agent consumes the structured bundle to localize likely code path.

---

## 23. Prototype screens to generate

Generate at least these high-fidelity frames in light and dark themes:

| Screen ID | Name | Required state |
|---|---|---|
| UX-00 | Capture off overview | Empty/no capture state |
| UX-01 | Live overview | Active redacted capture, KPI cards, anomalies |
| UX-02 | Consolidated Trace | Live rows, selected event, detail pane |
| UX-03 | Consolidated Trace with gap | Gap marker expanded and backfill action |
| UX-04 | Waterfall | One query action across Extension, STS, SQL, Renderer |
| UX-05 | Waterfall selected SQL command | Detail inspector open, redacted SQL |
| UX-06 | Perf & Sessions | Trend, distribution, A/B delta, SQL activity |
| UX-07 | Completions live | Existing pattern in shared host |
| UX-08 | Completions analysis | Grouped by model/profile/schema budget |
| UX-09 | Replay trace builder | Three events, one override selected |
| UX-10 | Replay matrix | Profiles × budgets × events summary |
| UX-11 | SQL Activity | Command table, SQL redacted |
| UX-12 | Export bundle modal | Privacy and validation step |
| UX-13 | Settings privacy | Capture policy and retention controls |

---

## 24. Prototype sample data dictionary

Use consistent identifiers across frames.

| Field | Example |
|---|---|
| Session ID | `sess_20260702_140213_devbox` |
| Run ID | `run_query_10k_candidate_7f3c2b1` |
| Correlation ID | `trace_8d3f1a9c_0007` |
| STS corr | `sts.corr.142` |
| Source event ID | `evt_00010430` |
| Replay trace ID | `rtrace_completion_hotspots_001` |
| Replay run ID | `rrun_20260702_141055` |
| Matrix cell ID | `cell_focused_generous_02` |
| SQL digest | `sql:sha256:8fd2c91a12e9...` |
| Commit | `7f3c2b1-dirty` |
| Environment hash | `env:9d0412a` |

Sample action:

- Action name: `Run query`
- Total wall-clock: `2.84s`
- Extension: `120ms`
- STS: `1.92s`
- SQL Server: `1.43s`
- Renderer: `412ms`
- SQL logical reads: `296,120`
- Rows rendered: `10,000`

Sample completion:

- Document: `Untitled-1`
- Trigger: `automatic`
- Mode: `intent`
- Model: `Claude Sonnet 4.6`
- Latency: `3,892ms`
- Tokens: `3,667 / 129`
- Result: `accepted`
- Profile: `Balanced`
- Schema budget: `Balanced default`

---

## 25. Accessibility and keyboard requirements

- All interactive controls must be keyboard reachable.
- Table rows must expose selected state and status to screen readers.
- Color must not be the only indicator for status or process.
- Bars must have accessible text labels with duration and status.
- Redacted fields must announce classification and reason.
- Provide high-contrast theme compatibility.
- Respect VS Code font scaling.
- Virtualized tables must maintain focus as rows load/backfill.

Keyboard shortcuts within webview:

| Shortcut | Action |
|---|---|
| `Ctrl/Cmd+F` | Focus page search |
| `Esc` | Clear current transient popover or search focus |
| `Enter` | Open selected row details |
| `C` | Copy selected correlation ID |
| `R` | Add selected event to replay if allowed |
| `B` | Backfill selected gap |
| `[` / `]` | Previous/next event in same correlation |
| `Shift+W` | Open selected event in Waterfall |

---

## 26. Responsive behavior

At narrow widths:

- Left rail collapses to icons.
- Detail pane moves below table.
- KPI cards wrap.
- Waterfall lanes remain horizontally scrollable.
- Chart grid becomes one column.
- Export modal uses full width.

At very wide widths:

- Use three-column layouts only where helpful, such as Perf & Sessions.
- Keep reading line lengths constrained in detail panes.

---

## 27. Acceptance criteria for UX prototype

A prototype is acceptable when it demonstrates:

1. One native-feeling VS Code webview host with extensible navigation.
2. Global session selector, live/history toggle, capture chip, search, gap indicator, export action.
3. Consolidated Trace table with list-plus-detail, cause tree, payload privacy, and gap/backfill.
4. Cross-Process Waterfall with process lanes, official vs diagnostic bar styles, correlation lines, critical path, and calibration honesty.
5. Perf & Sessions with distributions, trends, A/B deltas, SQL activity, and memory/soak analysis.
6. Completions page re-housed in the shell with live trace, detail tabs, multi-session analysis, and replay tags.
7. Replay Lab with trace builder, row overrides, config matrix, provenance, and blocked states.
8. Consistent classification lock and capture elevation UX.
9. Export bundle flow with privacy and validation.
10. Light and dark themes using VS Code token-like colors.

