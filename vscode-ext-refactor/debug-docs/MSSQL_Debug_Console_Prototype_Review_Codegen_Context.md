# MSSQL Debug Console Prototype Review and Codegen Handoff Context

**Artifact role:** Supplemental review/context document for the coding agent that will implement the MSSQL Debug Console after reading the UX spec, technical design, mockups, prototype output, and offline prototype HTML.

**Primary job:** Call out what the mockups clarify, what the HTML prototype implies, and what is still ambiguous or easy to get wrong. This file should travel with:

- `MSSQL_Debug_Console_UX_Spec.md`
- `MSSQL_Debug_Console_Technical_Design.md`
- `MSSQL Debug Console - offline.html`
- `Pasted text(70).txt`
- the provided screenshots `screen1.png` through `screen11.png`
- the original Claude Design brief, completions instrumentation PDF, perf prompts, STS2 alignment docs, and north-star docs

**Read this after the two main specs.** The main UX spec and technical design remain the source of truth for product behavior, privacy, architecture, and staged implementation. This document is the little brass plaque next to the prototype that says: “Looks like this, but here be dragons.”

---

## 1. High-level verdict

The mockups are strong and unusually useful as a codegen reference. They turn the abstract concept into a real VS Code-native tool with dense tables, a stable global shell, clear privacy affordances, and the right “profiler / DevTools” grammar. The prototype’s strongest contributions are:

1. **It proves the host shape.** The left rail, 44px top bar, page-specific content area, bottom provenance card, and grouped navigation make the console feel like a first-party VS Code webview rather than a random dashboard.
2. **It proves the visual language.** Compact KPI cards, small status pills, process-colored rows, list-plus-detail panes, and restrained SVG charts all fit the feature.
3. **It proves the three key surfaces can coexist.** Consolidated Trace, Waterfall, and Perf & Sessions all use the same shell but feel purpose-built.
4. **It makes privacy visible.** The redacted chip, lock treatment, export modal, redaction counts, and “blocked by policy” affordance are not decorative. They are part of the product contract.
5. **It makes uncertainty visible.** Gap markers, hatched timing, confidence labels, diagnostic flags, and official-vs-diagnostic distinctions are visible in the UI rather than hidden in footnotes.

The prototype should not be treated as implementation-ready HTML. It is a high-fidelity storyboard built with a Design Component runtime, static sample data, inline styles, inline event handlers, and presentational filters. The codegen agent should mine it for layout, density, token names, state names, and visual grammar, then reimplement it in the actual VS Code webview stack with typed data models, a strict CSP, real query/filter/backfill APIs, virtualization, accessibility, and the diagnostic substrate described in the technical design.

---

## 2. Source-of-truth priority for codegen

When sources disagree, use this precedence:

1. **Technical design:** data model, event schema, store, privacy, capture policy, live-tail, STS2 gates, webview message protocol, CSP, testing, and implementation order.
2. **UX spec:** page purposes, component behavior, global shell, workflows, states, copy, and acceptance criteria.
3. **This review/context file:** gaps and implementation caveats discovered from the mockups and HTML.
4. **Screenshots:** exact visual density, layout proportions, hierarchy, and examples of what should be visible above the fold.
5. **Offline HTML:** component inventory, token approximations, sample data, and interaction hints only. Do not copy its runtime, inline handlers, or static data architecture.
6. **Prototype output transcript:** confirms what the prototype generator intended and what was merely presentational.

The prototype output explicitly says the interactions are real for navigation/theme/live-history/selection/tabs/bar selection/toggles/gap-backfill, but the data is illustrative and filter/selector chips are presentational. That is important enough to staple to the codegen prompt.

---

## 3. What the mockups clarify beyond the main specs

### 3.1 The console should open to a triage cockpit, not directly to raw trace

`screen1.png` makes the Overview page valuable, not optional. It does three things at once:

- summarizes the current session health with KPI cards;
- shows recent user actions with enough fields to decide where to click next;
- surfaces anomalies as direct entry points into Trace, Perf, Waterfall, or Replay.

The codegen agent should preserve this as the default landing page. Do not make the first screen a raw event table. The Overview is the air-traffic-control pane.

### 3.2 The left rail grouping is now clear

The mockups use three groups:

- **Common:** Overview, Consolidated Trace, Waterfall, Perf & Sessions, Completions, Replay Lab
- **Feature Pages:** SQL Activity, Connections, Query & Results, Object Explorer
- **Session:** Exports, Settings

This is better than a flat list. It also implies dynamic feature-page contributions should be visually grouped into the `Feature Pages` section by default unless a feature declares a different group.

### 3.3 The bottom provenance card should be persistent

Every screenshot keeps the small provenance card in the lower-left rail, for example:

```text
PROVENANCE
mssql 7f3c2b1-dirty
env:9d0412a
```

This should stay visible whenever the left rail has enough height. It is not only decorative. It anchors all diagnostic interpretation to commit, dirty state, and environment fingerprint. It should open the full provenance drawer when clicked.

### 3.4 Feature pages are examples of an extensibility model

Connections, Query & Results, Object Explorer, SQL Activity, Exports, and Settings are shown with representative content. They should not be implemented as one-off static pages. They should prove the page registry and shared component system:

- a feature contributes navigation metadata;
- a feature consumes the common session/event/query APIs;
- a feature can add custom detail panes without creating a separate webview;
- a feature can deep-link into Trace or Waterfall by correlation ID.

### 3.5 The Debug Console is both a live tool and a session browser

The top bar has both a session selector and a `Live / History` segmented control. In the screenshots, the selected source can be:

- current VS Code session;
- local persisted session;
- imported perf run;
- imported support bundle.

This should become a first-class `SessionSource` or `DataSource` model, not a string in UI state.

---

## 4. Global shell review

### 4.1 Keep these shell dimensions and density as visual targets

The offline HTML implies these useful density targets:

| Element | Prototype value | Implementation note |
|---|---:|---|
| Top bar height | `44px` | Works well. Keep close to this. |
| Left rail width | `210px` | Good at full width; add collapse/compact behavior later. |
| Base UI font size | `12px` | Good for DevTools density. Use VS Code typography tokens where possible. |
| Page title | about `13-15px`, semibold | Avoid hero text. |
| Nav row height | `30px` | Works well with icons. |
| Toolbar/button height | `28px` | Good for VS Code webview density. |
| Radius | `5-8px` | Keep quiet, not card-bubble flamboyance. |
| Table row height | roughly `28-32px` | Must support virtualization. |

The implementation should not hard-code every style inline. Extract these into design tokens/classes.

### 4.2 Top bar controls need exact semantics

The mockup top bar has:

1. product name;
2. session/run selector;
3. `Live / History` toggle;
4. global search;
5. capture/privacy chip;
6. gap/backfill button;
7. export button;
8. refresh/theme/prototype-only icon.

Codegen should not leave these as dead buttons. At minimum, implement stubs with typed command handlers and visible disabled/pending states.

Suggested semantics:

| Control | Required behavior |
|---|---|
| Session selector | Opens a session/source picker. Lists current session, local sessions, perf runs, imported bundles. Shows source kind and capability flags. |
| Live | Subscribes to current live-tail stream. Shows current seq and connection health. |
| History | Suspends live subscription and queries persisted store. Does not mutate the live capture state. |
| Search | Searches visible source only by default. Must not reveal redacted content. Must support event type, process, feature, correlation ID, status, digest, and session name. |
| Capture chip | Opens capture popover. Shows current policy and any time-bounded elevation countdown. |
| Backfill | Opens the Trace page and focuses unresolved gaps. If one gap exists, can trigger backfill directly after confirmation. |
| Export | Opens export modal with source/scope preselected based on current context. |

### 4.3 Top bar overflow is a real risk

The screenshots are wide. In a normal VS Code split editor, the webview may be much narrower. The top bar will crowd quickly. Define responsive priority now:

1. Always keep title or icon, session source, capture chip, and overflow menu visible.
2. Collapse global search to icon below a threshold.
3. Collapse `Backfill` and `Export` into icon buttons or overflow menu below a threshold.
4. Let the left rail collapse only in narrow modes, not before.

### 4.4 Theme toggle in the prototype is not product behavior

The offline prototype has its own light/dark toggle. The real webview should follow VS Code theme tokens. A theme toggle may remain in mock data/dev mode, but production code should not maintain an independent theme state that conflicts with VS Code.

---

## 5. Visual system and CSS implementation notes

### 5.1 Preserve the process color language

The prototype establishes a useful process palette:

| Process/component | Visual role |
|---|---|
| Extension Host | teal/green-blue |
| Webview / Renderer | blue |
| SQL Tools Service | purple |
| SQL Server | green |
| Driver / Wire | orange |
| Harness / Process counters | slate/gray |
| System/User action | gray |

These should become semantic process tokens, not arbitrary chart colors. Pages should reuse the same process colors for row stripes, waterfall lanes, cause trees, mini timelines, badges, and legends.

### 5.2 Preserve status semantics

The prototype uses quiet status pills:

- `ok`: green
- `warning`: amber
- `error`: red
- `skipped`: neutral
- `blocked`: amber/locked
- `partial` / `invalid`: should be added explicitly even if not prominent in screenshots

Do not use bright banner-level severity unless the issue blocks the entire page. Most diagnostic issues belong in rows, chips, and cards.

### 5.3 Extract tokens from inline styles

The offline HTML uses extensive inline styles. The implementation should translate them into a small design system:

```text
.debug-console-shell
.dc-topbar
.dc-leftnav
.dc-page
.dc-toolbar
.dc-card
.dc-kpi
.dc-table
.dc-detail-pane
.dc-pill
.dc-redacted-field
.dc-waterfall
.dc-chart
```

Use CSS variables backed by VS Code theme variables. The prototype’s token names are good scaffolding, but final code should map to actual `--vscode-*` variables wherever available.

### 5.4 Do not rely on CSS background hatching alone for meaning

The Waterfall uses hatched bars to mean aligned/diagnostic/inferred timing. Keep the hatching, but also include:

- a visible legend;
- accessible text in the selected detail inspector;
- `aria-label` or equivalent for timeline bars;
- an exported textual summary.

Hatching is a great visual cue. It is not enough for accessibility or exported evidence.

---

## 6. Page-by-page review and implementation notes

## 6.1 Overview page

### What works

The Overview page in `screen1.png` is the right default landing experience. It balances:

- session KPIs;
- recent actions;
- anomaly cards;
- sessions/imported runs.

The layout also gives the product a good “control room” feeling without becoming a glittery dashboard.

### Clarify before implementation

#### KPI formulas need definitions

The mockup shows:

- Events: `18,421`
- Errors: `11`
- Warnings: `34`
- Live-tail gaps: `2`
- Slowest action: `9.83s`
- SQL commands: `312`
- Renderer: `412ms`
- Memory peak: `684MB`
- Capture mode: `Redacted`
- Replay runs: `3`
- Exports: `2`

Codegen should not hard-code these or compute them ad hoc in the UI. Define metric queries:

| KPI | Suggested source |
|---|---|
| Events | Count of events in selected source after current time/session filters. |
| Errors | Count where `severity=error` or `status=error`, excluding redaction-policy expected locks. |
| Warnings | Count where `severity=warning` or `status=warning`. |
| Live-tail gaps | Count unresolved gap records for selected live/history source. |
| Slowest action | Longest user-action/root-correlation span, not any child event. |
| SQL commands | Count of `sqlActivity` events. |
| Renderer | P95 or last selected render metric must be labeled. Do not show ambiguous “Renderer 412ms” without metric name. |
| Memory peak | Peak RSS/working set for selected process role. |
| Replay runs | Count of replay runs attached to selected source or current session. |
| Exports | Count of generated/imported bundles in local store. |

#### Recent actions should be correlation roots

The Recent user actions table should use root user actions or scenario/action spans. Each row should have a root correlation ID and a deep link:

- click row -> Waterfall for that action;
- click feature -> feature page filtered to correlation;
- click warning/error -> Trace detail at the most relevant event.

#### Anomaly cards should be generated, not curated

The prototype anomaly cards are excellent examples. Implement them as a derived `AnomalySummary[]`, not static strings. Each anomaly should include:

```ts
interface AnomalySummary {
  id: string;
  severity: 'info' | 'warning' | 'error';
  title: string;
  detail: string;
  sourceEventIds: string[];
  sourceCorrelationId?: string;
  confidence: 'high' | 'medium' | 'low';
  cta: { label: string; route: DebugRoute };
}
```

### Important empty/loading states

The Overview is the page most likely to be opened before capture is enabled. It needs explicit states:

- Capture off: explain Session Diag and offer enable action if allowed.
- No events yet: “Use MSSQL features, then events will appear here.”
- Store unavailable/corrupt: show diagnostic message and recovery/export options.
- Imported bundle: show read-only mode and privacy report status.

---

## 6.2 Consolidated Trace page

### What works

`screen3.png` nails the Trace page pattern:

- dense table on the left;
- selected-row highlight;
- process pills;
- kind glyphs;
- correlation IDs visible;
- inline amber gap marker;
- detail pane with tabs;
- Cause tab rendered as a tree.

This page is the backbone of the console. Implement it early and thoroughly.

### Required implementation details

#### Use a virtualized table

The mockup shows `15 of 18,421 shown`. The real page must handle tens or hundreds of thousands of events. Implement virtualization from day one. Avoid rendering every event as a DOM row.

Minimum features:

- keyboard row navigation;
- preserve selected row when data streams;
- support pinned gap markers and group headers;
- stable scroll while live-tail appends, with “jump to latest” control.

#### Filters must be real

The prototype’s filter chips are presentational. Codegen must implement actual query filters:

- process;
- feature;
- kind;
- status/severity;
- correlation ID;
- text search over non-redacted fields and digests;
- time range;
- replay/source tags.

Filters should update the table query, count, and detail context. If a selected event disappears due to filters, preserve a “selected event outside current filter” notice or clear selection intentionally.

#### Gap rows must be data records

The gap marker is not a row decoration. It should be a `GapRecord` with:

```ts
interface GapRecord {
  id: string;
  sessionId: string;
  subscriptionId?: string;
  fromSeq: number;
  throughSeq: number;
  droppedCount: number;
  reason: 'subscriberOverflow' | 'storeUnavailable' | 'journalMissing' | 'transportDisconnect' | string;
  backfillStatus: 'notStarted' | 'running' | 'succeeded' | 'partial' | 'failed';
  checkpoint?: string;
  error?: string;
}
```

Backfill should be honest:

- not started: show `Backfill from journal`;
- running: show progress/spinner;
- succeeded: replace or expand with recovered rows;
- partial: show recovered count and remaining missing range;
- failed: keep the gap visible and exportable.

#### Detail tabs need stable contracts

The right-side detail pane has tabs:

- Summary
- Payload
- Cause
- Timeline
- Privacy
- Raw
- Actions

Each tab should be backed by typed data. Avoid letting feature pages inject arbitrary HTML into these tabs. Use renderers for fields, trees, timelines, privacy tables, and JSON.

#### Payload handling must be classification-first

The prototype shows `sql.text` redacted with digest and lock treatment. The implementation should render all payload fields through a `RedactedField` or `ClassifiedValue` component:

```ts
interface ClassifiedValue<T = unknown> {
  value?: T;
  display?: string;
  classification: Classification;
  handling: 'plain' | 'redacted' | 'digest' | 'sanitized' | 'blocked';
  digest?: string;
  policyId: string;
  reason?: string;
}
```

Never special-case SQL text only. Connection strings, server names, database names, schema names, prompts, row samples, paths, and provider messages all need the same machinery.

### Ambiguity to resolve

The mockup shows `SQL Server` event correlation as `app:mssql-vscode` in one place and `trace_8d3f…0007` in others. The implementation should keep both concepts:

- **external trace/correlation ID:** joins extension, webview, STS;
- **SQL correlation key:** Application Name / session context / SQL session ID used by XEvents;
- **normalized correlation chain:** UI-friendly cause tree that bridges both.

Do not collapse SQL `applicationName` into `traceId` unless the actual substrate guarantees it.

---

## 6.3 Cross-Process Waterfall page

### What works

`screen2.png` is the headline experience. It demonstrates why this feature exists: one action, one time axis, cross-tier decomposition.

The strongest parts to preserve:

- wall-clock decomposition strip at top;
- process lanes;
- solid vs hatched timing legend;
- correlation lines;
- selected bar detail inspector;
- critical path panel;
- calibration/jitter note.

### Required implementation details

#### Timing classes must be explicit data

Do not infer hatched vs solid from process name. Each activity should carry timing classification:

```ts
interface WaterfallActivity {
  id: string;
  laneId: string;
  label: string;
  startEpochMs?: number;
  endEpochMs?: number;
  startMonotonicMs?: number;
  endMonotonicMs?: number;
  durationMs: number;
  timingClass: 'officialSameProcess' | 'productTimer' | 'epochAlignedDiagnostic' | 'collectorDiagnostic' | 'inferred';
  confidence: 'high' | 'medium' | 'low';
  correlationId?: string;
  causeEventId?: string;
  sourceEventIds: string[];
  classification?: Classification;
}
```

The renderer should decide visual style from `timingClass`, not from label text.

#### Keep calibration visible

The screenshot shows alignment notes such as `exthost ±1.4ms · STS ±3.2ms · webview ±2.0ms`. Keep this. It is the UI’s credibility anchor. Put it near the timeline axis and in the selected bar inspector.

#### Critical path should be computed, not static

The right-side critical path panel lists steps and durations. Codegen should implement a minimal critical-path calculator over the selected correlation’s activity graph. If full graph semantics are not available yet, show `critical path unavailable` rather than inventing it.

#### Zoom/scrub is specified but not implemented in the prototype

The design brief calls for hover, zoom/scrub, and critical-path highlight. The prototype demonstrates toggles and selection but not true zoom/scrub. Codegen should at least design the API and state:

```ts
interface TimelineViewport {
  startMs: number;
  endMs: number;
  scale: number;
  selectedActivityId?: string;
  hoveredActivityId?: string;
}
```

First implementation can support horizontal scroll and fit-to-width. Do not paint yourself into a chart corner.

#### Correlation lines need hit testing and fallbacks

SVG overlay correlation lines look good. Implementation details:

- lines should not intercept clicks meant for bars;
- line endpoints must update on resize and horizontal scroll;
- hidden lanes should hide related lines;
- inferred or low-confidence links should be dashed and explained;
- if a link target is outside viewport, show arrow/continuation or omit with count.

### Ambiguity to resolve

The decomposition strip totals `2.84s`, but segments may overlap. Decide whether the strip shows:

- exclusive critical path contribution;
- wall-clock phase decomposition;
- raw summed time per tier;
- selected action elapsed with overlapping tier bars.

The label in the screenshot says wall-clock decomposition. Therefore do not sum overlapping child durations into a value greater than wall-clock unless the strip clearly says “sum.”

---

## 6.4 Perf & Sessions page

### What works

`screen5.png` and `screen6.png` make Perf & Sessions feel like the harness report, but native to the product. The page correctly emphasizes:

- distribution and variance, not only a single value;
- cross-session trend with baseline band and step-change marker;
- A/B deltas;
- SQL logical reads investigation;
- memory soak with slope, confidence band, R², and sample count;
- small-multiple variant time split;
- metric comparison table with verdict and confidence.

### Required implementation details

#### Separate gating verdicts from investigation context

The screenshot mixes official metrics and diagnostic explanations. The UI must preserve the distinction:

- official metrics may gate regressions;
- diagnostic metrics explain what changed;
- investigation callouts must not imply gating unless the metric is official.

Use explicit labels:

- `official` / `diagnostic` / `derived`;
- `gating: yes/no`;
- `confidence: high/medium/low`;
- `sample count` and `small-n` warning.

#### Define what each chart is scoped to

The toolbar shows controls like source runs/sessions, scenario, metric, group by commit, and baseline. These controls must be real. Each chart needs a query object:

```ts
interface PerfQuery {
  sourceIds: string[];
  scenarioId?: string;
  metricName: string;
  groupBy: 'time' | 'commit' | 'session' | 'variant' | 'environment';
  baselineId?: string;
  includeDiagnostic: boolean;
}
```

#### Do not smooth away variance

The trend line should show actual points. The baseline band and step-change marker are excellent. Keep dots visible, and surface low sample count. Memory trend should show slope, R², sample count, and verdict.

#### Watch wording consistency in A/B deltas

The screenshots use strong investigation text such as “Candidate added 3 SQL commands and +87,720 logical reads.” Make sure signs and percentages are consistent across:

- KPI cards;
- A/B delta bars;
- investigation callout;
- metric table;
- SQL activity table.

This page will be where people argue about performance. Tiny inconsistencies will become gremlins with tiny clipboards.

### Minimum useful implementation

A first implementation can support:

- imported perf run data;
- one scenario selector;
- metric table;
- one distribution chart;
- one trend chart;
- one A/B comparison panel.

Then add soak/memory and SQL delta once artifacts exist.

---

## 6.5 SQL Activity page

### What works

`screen7.png` gives SQL Activity its own page rather than burying SQL rows inside Perf. It shows:

- SQL activity KPIs;
- command table;
- selected command details;
- redacted SQL text with digest;
- statistics cards;
- query plan link;
- correlation chain.

### Required implementation details

#### SQL text must go through capture policy

Default view should show:

```text
SQL text redacted
digest: sql:sha256:...
classification: sql.text · handling: digest · policy: redacted_default
```

Do not accidentally store or render SQL text in hidden DOM, tooltips, data attributes, logs, or search indexes.

#### Query plan links need artifact semantics

The mockup has `query-plan.sqlplan · open in estimated plan viewer`. Implementation needs to define:

- artifact ID;
- artifact path or URI;
- capture classification;
- whether it is included in export;
- whether it is safe under current policy.

#### Correlation chain should deep-link

Each node in the correlation chain should be clickable:

- command event -> Trace detail;
- STS RPC -> Waterfall bar;
- SQL activity -> selected SQL Activity row;
- webview render -> Query & Results / Waterfall.

### Ambiguity to resolve

The `SQL Activity` page and the `SQL activity table` inside `Perf & Sessions` overlap. Suggested split:

- `SQL Activity`: session/source-level command explorer, sorted/filterable.
- `Perf & Sessions` SQL section: scoped to selected scenario/A/B comparison, with deltas and top-N.

---

## 6.6 Connections page

### What works

`screen8.png` shows a simple but useful connection lifecycle page:

- active connection count;
- STS PID;
- readiness average;
- failure count;
- STS lifecycle card;
- active connections table with digested server/database and auth kind.

### Required implementation details

#### Connection identity is sensitive

Server and database names are digest-rendered in the mockup. Keep that. Also classify:

- auth type;
- user name;
- connection string;
- server name;
- database name;
- tenant/account data.

#### Distinguish STS process health from connection health

The page has an STS card and connection rows. Keep those separate in data and UI. A failed connection does not necessarily mean STS is unhealthy.

#### Add lifecycle detail tabs later

The current page is a shell. The eventual version should have selected-connection details:

- Summary;
- Timeline;
- Payload/parameters redacted;
- STS/process;
- Errors;
- Privacy.

---

## 6.7 Query & Results page

### What works

`screen9.png` is a compact feature page focused on result rendering:

- wall-clock;
- rows rendered;
- render time;
- window fetches;
- result sets table;
- render breakdown;
- row-count proof.

### Required implementation details

#### Row-count proof is a product invariant

The green proof card is not decoration. It is the UX expression of “success must be proven or the rep is invalid.” Store this as structured evidence:

```ts
interface QueryResultProof {
  expectedRows?: number;
  renderedRows?: number;
  resultSetCount?: number;
  windowingTriggered?: boolean;
  proofStatus: 'passed' | 'failed' | 'notAvailable';
  evidenceEventIds: string[];
}
```

#### Virtual windowing needs a specific state

The mockup shows `Window fetches: 8`. For large-result scenarios, the UI should prove windowing was actually triggered, not merely infer from row count. Include markers such as:

- `resultsGrid.windowFetch.begin`;
- `resultsGrid.windowFetch.end`;
- rows rendered for each window;
- scroll offset / range if safe.

#### Render breakdown is diagnostic-only

Scripting/layout/paint/longest task comes from renderer diagnostics. Label it as CDP/diagnostic and hide or warn when the CDP target is missing.

---

## 6.8 Object Explorer page

### What works

The Object Explorer page is not in the shown screenshots here, but the prototype output says it includes object-count proof and real representative content. In the Overview and Trace, Object Explorer expansion is a first-class anomaly with a live-tail gap and slow STS metadata enumeration.

### Required implementation details

Object Explorer needs special care because it is where “everything is a tree” can become “everything is slow.” The feature page should show:

- selected OE action/correlation;
- object count proof;
- STS metadata calls;
- SQL/SMO activity;
- renderer tree render phases;
- truncation/lazy-load/windowing state;
- errors and partial results.

### Ambiguity to resolve

The UI should distinguish:

- **Object count proof:** did the product render expected objects?
- **Enumeration SQL activity:** how much SQL/SMO did we trigger?
- **Tree rendering:** how long did DOM/tree painting take?
- **Live-tail gaps:** did we miss trace data while expanding?

Those are different questions and should not be collapsed into one warning.

---

## 6.9 Exports page and Export Evidence Bundle modal

### What works

`screen4.png` and `screen10.png` make export feel coherent and safe:

- explicit scope choice;
- privacy choices;
- policy-blocked full SQL text;
- validation checklist;
- bundle preview with event/redaction/artifact counts;
- recent exports list;
- bundle validation panel.

### Required implementation details

#### Export is a transaction, not just a zip button

Export should take a stable snapshot. It must not race against live writes and produce a half-true bundle. Implement export via the store/session snapshot API described in the technical design.

#### Scope choices need exact semantics

The modal shows:

- Entire session;
- Selected correlation;
- Selected time range / current replay result.

Define scope data:

```ts
interface ExportScope {
  kind: 'session' | 'correlation' | 'timeRange' | 'eventSelection' | 'replayRun';
  sessionId: string;
  correlationId?: string;
  fromSeq?: number;
  throughSeq?: number;
  fromTimeUtc?: string;
  throughTimeUtc?: string;
  eventIds?: string[];
  replayRunId?: string;
}
```

#### Validation must block unsafe export

The validation panel should not be decorative. Required checks:

- snapshot consistency;
- unresolved gaps;
- redaction scan;
- manifest hashes;
- privacy report included;
- artifact presence/hash;
- schema version included;
- no disallowed plaintext secrets.

If validation fails, do not silently export. Offer “export with unresolved gaps” only if product policy allows and bundle manifest marks it.

#### Import bundle path is not shown enough

The Exports page has `Import bundle...`, but the UX does not define import states. Add:

- validate before import;
- show source and privacy policy;
- show read-only imported source;
- do not merge imported bundle into live local store without a source boundary;
- handle schema version mismatch.

---

## 6.10 Settings page

### What works

`screen11.png` captures the right settings groups:

- Session Diag capture;
- retention and storage;
- experimental features.

### Required implementation details

#### Defaults are product decisions, not UI decisions

The mockup shows `Enable Session Diag` on and default capture mode `redacted`. The Phase 4 prompt explicitly says shipping privacy defaults should not be decided unilaterally. For implementation, make settings support this, but gate defaults by product configuration/build channel:

```ts
interface DebugConsoleFeatureFlags {
  debugConsoleEnabled: boolean;
  sessionDiagDefaultEnabled: boolean;
  sessionDiagAllowedCaptureModes: CaptureMode[];
  elevatedCaptureAllowed: boolean;
  replayLabEnabled: boolean;
  sts2SourceEnabled: boolean;
}
```

#### Clear-all requires confirmation

`Clear all local diagnostics` should require a confirmation modal with counts:

- sessions;
- events;
- artifacts;
- exports;
- approximate disk usage.

After clearing, the UI should navigate to a safe empty state.

#### Elevated capture needs reason and countdown

The settings page has `Allow elevated capture`, while the top bar has a capture chip. The actual elevation flow should require:

- user action;
- reason string;
- duration;
- max policy check;
- clear top-bar countdown;
- auto-revert event;
- audit event in Session Diag store, redacted if needed.

---

## 6.11 Completions page

### What works

The prototype output says the Completions page has:

- live trace strip;
- event table;
- 10 detail tabs;
- multi-session analysis;
- replay tags.

The original completions PDF remains the stronger visual reference for this page. The Debug Console should preserve the existing completion workflow but re-house it in the shared shell.

### Required implementation details

#### Do not regress the existing completions debug UX

The existing completions view already has persisted sessions, live tracing, multi-session analysis, replay trace builder, matrix runs, and replay tagging. When migrating into the host, keep feature-specific detail tabs intact:

- Summary;
- System Prompt;
- User Prompt;
- Raw Response;
- Sanitized;
- Schema Context;
- Locals;
- Telemetry;
- Replay;
- Privacy.

#### Header crowding was already noted

The prototype output mentions minor crowding around token/result headers. In implementation, use column resize, responsive column priorities, or compact labels (`Tok in/out`) to avoid clipping.

#### Prompt/response privacy is its own classification family

Do not classify completions prompts as generic text. Use explicit classifications such as:

- `model.prompt`;
- `model.response`;
- `user.text`;
- `schema.name`;
- `sql.text` if SQL appears inside prompt or response;
- `diagnostic.metadata`.

---

## 6.12 Replay Lab

### What works

Replay Lab generalizes the completions replay pattern into a shared feature. The mockups and prior docs make it clear that replay is central, but also gated.

### Required implementation details

#### Replay types must not be conflated

The UI needs to distinguish:

- **deterministic journal verify:** forensic check, no live DB re-execution;
- **replay-drive:** resubmit recorded inputs to a live system with provenance;
- **feature adapter replay:** completions, query, connection, etc., each with eligibility and limitations.

Do not label everything “replay” without showing which class it is.

#### Adapter eligibility is visible UX

A replay row or event should show one of:

- replayable now;
- replayable with degraded fidelity;
- blocked by capture policy;
- blocked by missing data;
- blocked by STS2 hardening gate;
- not supported by feature adapter.

#### Matrix runs need provenance

Every generated replay event must carry:

- source session/run ID;
- source event IDs;
- replay trace ID;
- replay run ID;
- matrix cell ID;
- overrides;
- capture policy used;
- adapter version.

---

## 7. HTML prototype review

### 7.1 What the HTML is

`MSSQL Debug Console - offline.html` is a bundled Design Component prototype. It contains:

- a bundler shell and thumbnail;
- a compressed runtime asset;
- a large `x-dc` template;
- inline CSS token approximations;
- one component class extending `DCLogic`;
- `vals_*` methods that return static sample data for each page;
- inline event handlers through template bindings;
- custom tags such as `sc-if` and `sc-for`.

This is excellent for visual handoff. It is not the implementation substrate.

### 7.2 Useful implementation clues in the HTML

The HTML names the major conceptual functions:

```text
shellVals()
vals_overview()
vals_trace()
buildTraceDetail()
vals_waterfall()
buildWfDetail()
vals_perf()
vals_sql()
vals_replay()
vals_completions()
vals_connections()
vals_query()
vals_oe()
vals_exports()
vals_settings()
```

Treat these as a rough component/data inventory. They map naturally to React page components and selectors.

### 7.3 Do not copy these HTML implementation patterns

#### Inline styles everywhere

The prototype uses inline style attributes. Convert to CSS classes and tokens.

#### Inline event handlers

The prototype uses `onclick` bindings. A VS Code webview with strict CSP should not depend on inline JS handlers. Use bundled scripts with nonce/hash-based CSP and a framework event system.

#### Static sample data inside view methods

The prototype stores all rows and chart points in component methods. Move sample data to fixtures for Storybook/dev mode, and real data to the store/live query layer.

#### Presentational filters

The transcript confirms filters and selector chips are presentational. Implement actual query/filter behavior.

#### Prototype-only theme switching

Do not keep independent theme state in production. Use VS Code CSS variables and theme change events.

#### No virtualization

The prototype renders small samples. Real trace and SQL tables need virtualization.

#### No accessibility semantics

The prototype is visually strong, but implementation needs ARIA labels, keyboard navigation, focus management, modal trapping, table semantics, and chart text alternatives.

#### No strict CSP model

The real webview must enforce strict CSP and avoid raw HTML rendering. Any JSON/payload viewer should escape content.

### 7.4 Sample data should become fixtures

The prototype sample world is useful and should be preserved as fixtures for tests/stories:

- session: `sess_20260702_140213_devbox`
- trace: `trace_8d3f…0007`
- commit: `7f3c2b1-dirty`
- gap: `seq 10432–10645`, `214 events dropped`, reason `subscriberOverflow`
- query wall-clock: `2.84s`
- SQL logical reads: `296,120`
- rows: `10,000`
- render complete: `412ms`
- object explorer expand: `9.83s`
- memory peak: `684MB`

Use these values to build deterministic visual fixtures and tests. Do not use them as defaults in production.

### 7.5 Prototype HTML has good renderer hints

The hand-authored SVG-style chart approach is useful because it avoids external dependencies and can work offline. For product implementation:

- factor chart math into shared renderer modules;
- use deterministic SVG for reports and webview;
- include text alternatives;
- support resize/viewport changes;
- avoid heavyweight chart libraries unless already approved.

This lines up with the prior design requirement that harness reports and the in-product viewer reuse waterfall/plot/trend renderers.

---

## 8. Ambiguities and decisions to resolve before or during implementation

### 8.1 Session source model

The UX mixes live sessions, historical local sessions, perf runs, and support bundles. Define a single source model:

```ts
interface DebugSource {
  id: string;
  kind: 'liveSession' | 'localSession' | 'perfRun' | 'supportBundle' | 'replayRun';
  label: string;
  readonly: boolean;
  captureMode?: CaptureMode;
  createdAt?: string;
  eventCount?: number;
  unresolvedGapCount?: number;
  capabilities: DebugSourceCapability[];
  provenance: ProvenanceSummary;
}
```

Each page should render based on `capabilities`, not just page availability.

### 8.2 Capability gating

Not every source has every artifact. A support bundle may have no live-tail. A digest-only session may not support replay. A perf run may have SQL/CDP artifacts but no completions prompts. Add capability checks and missing-collector states.

Suggested capability examples:

```text
liveTail
historyQuery
traceEvents
waterfallActivities
sqlActivity
rendererTrace
processSamples
completionsEvents
replayDrive
exportable
backfillableGaps
privacyReport
```

### 8.3 Global search scope

Clarify whether search applies to:

- current page only;
- current source across all pages;
- all stored sources;
- current table only.

Recommended default: current source across major indexed fields, with page-local filters applied on each page. Add a clear label like `Search current source` or `Search all sessions` when scope changes.

### 8.4 Routing and deep links

The prototype uses page state only. Implementation should support deep links such as:

```text
/debug-console/trace?source=sess_...&event=evt_...
/debug-console/waterfall?source=sess_...&corr=trace_...
/debug-console/sql?source=sess_...&sqlEvent=...
/debug-console/perf?scenario=query-10k&metric=scenario.wallclock
```

VS Code webviews do not need browser URL routing, but internal route state should be serializable so actions, reloads, and test fixtures can restore it.

### 8.5 Capture defaults and shipping surface

The Settings mockup shows Session Diag enabled. The Phase 4 docs require privacy defaults to be owner decisions. Codegen should build flags/settings without deciding shipping defaults.

### 8.6 STS2-backed features are gated

The UI should be able to show STS/SQL lanes from imported perf data or extension-side events now, but STS2 live Session Diag capture and STS-backed replay must stay gated until hardening requirements are met.

### 8.7 Export and backfill from live source need snapshot semantics

Export and backfill both need consistent reads from an active store. Do not implement them as plain “read current array” operations. They should use snapshot/checkpoint APIs.

### 8.8 What is a “user action”?

Overview and Waterfall depend on root actions. Define root action/event types early:

- command invocation;
- connection open/close;
- query run/cancel;
- OE expand/refresh;
- completion request;
- result-grid render;
- replay run/cell;
- export/import.

Root actions should create or reference a correlation ID and have begin/end semantics where possible.

### 8.9 Error taxonomy

Rows use `status=warning/error`, but errors can mean many things:

- product error;
- diagnostic collector warning;
- privacy policy block;
- live-tail gap;
- replay adapter failure;
- validation failure;
- regression verdict.

Create a taxonomy rather than overloading one `status` field everywhere.

---

## 9. Implementation architecture suggestions for codegen

### 9.1 Recommended webview module structure

The technical design already suggests a module layout. Extend it with fixture/dev data and renderer boundaries:

```text
webview/debugConsole/
  app/
    DebugConsoleApp.tsx
    routes.ts
    state.ts
    useDebugSource.ts
    useLiveTail.ts
  api/
    DebugConsoleClient.ts
    messages.ts
    types.ts
  components/
    shell/
      AppShell.tsx
      TopBar.tsx
      LeftNav.tsx
      ProvenanceCard.tsx
    common/
      KpiCard.tsx
      StatusPill.tsx
      ProcessPill.tsx
      ToolbarSelect.tsx
      EmptyState.tsx
      ErrorState.tsx
      RedactedField.tsx
      GapMarker.tsx
      DetailTabs.tsx
      JsonViewer.tsx
    trace/
      EventTable.tsx
      EventDetailPane.tsx
      CauseTree.tsx
      MiniTimeline.tsx
    waterfall/
      WaterfallTimeline.tsx
      WaterfallLegend.tsx
      CriticalPathPanel.tsx
      ActivityInspector.tsx
    charts/
      Histogram.tsx
      BoxPlot.tsx
      TrendChart.tsx
      DeltaBars.tsx
      SoakScatter.tsx
  pages/
    OverviewPage.tsx
    TracePage.tsx
    WaterfallPage.tsx
    PerfSessionsPage.tsx
    CompletionsPage.tsx
    ReplayLabPage.tsx
    SqlActivityPage.tsx
    ConnectionsPage.tsx
    QueryResultsPage.tsx
    ObjectExplorerPage.tsx
    ExportsPage.tsx
    SettingsPage.tsx
  renderers/
    timelineModel.ts
    waterfallLayout.ts
    chartScales.ts
    svgPrimitives.ts
  fixtures/
    sampleSession.ts
    sampleTrace.ts
    samplePerf.ts
```

### 9.2 Data model minimum set

Build these types early:

```ts
type CaptureMode = 'off' | 'redacted' | 'digest' | 'full';
type ProcessKind = 'extensionHost' | 'webview' | 'renderer' | 'sqlToolsService' | 'sqlServer' | 'driver' | 'harness' | 'system';
type EventKind = 'event' | 'span' | 'metric' | 'request' | 'response' | 'sqlActivity' | 'renderPhase' | 'state' | 'artifact' | 'gap';
type Severity = 'ok' | 'info' | 'warning' | 'error' | 'blocked' | 'skipped' | 'partial' | 'invalid';

interface DiagEvent {
  id: string;
  sessionId: string;
  seq: number;
  timestampUtc: string;
  process: ProcessKind;
  feature: string;
  kind: EventKind;
  type: string;
  status?: Severity;
  severity?: Severity;
  correlationId?: string;
  parentId?: string;
  causeId?: string;
  entityRefs?: EntityRef[];
  durationMs?: number;
  classification: ClassificationSummary;
  payload: Record<string, ClassifiedValue>;
  tags?: string[];
}
```

### 9.3 Store/query API minimum set

A codegen build can start with mocked data, but keep API shape real:

```ts
interface DebugConsoleStoreClient {
  listSources(): Promise<DebugSource[]>;
  getSource(id: string): Promise<DebugSourceDetail>;
  queryEvents(query: EventQuery): Promise<PagedResult<DiagEvent | GapRecord>>;
  getEvent(sessionId: string, eventId: string): Promise<DiagEventDetail>;
  getCauseTree(sessionId: string, eventId: string): Promise<CauseTree>;
  getWaterfall(query: WaterfallQuery): Promise<WaterfallModel>;
  getPerfSummary(query: PerfQuery): Promise<PerfSummary>;
  getSqlActivity(query: SqlActivityQuery): Promise<PagedResult<SqlActivityEvent>>;
  backfillGap(request: BackfillGapRequest): Promise<BackfillGapResult>;
  exportBundle(request: ExportBundleRequest): Promise<ExportBundleResult>;
}
```

### 9.4 Use fixture mode as a first-class development mode

Because substrate work may lag UI work, support fixture-backed rendering:

```ts
const client = isFixtureMode ? new FixtureDebugConsoleClient() : new VsCodeDebugConsoleClient(vscodeApi);
```

This lets codegen match the mockups while keeping the final API shape intact.

---

## 10. Accessibility and keyboard requirements to add to codegen prompt

The specs mention accessibility, but the mockups/HTML do not prove it. Add these explicit requirements:

### 10.1 Global keyboard

| Key | Behavior |
|---|---|
| `Ctrl/Cmd+F` | Focus global search when Debug Console has focus. |
| `Esc` | Close popover/modal/detail transient state. |
| Arrow up/down | Move table selection when table focused. |
| Enter | Open/select highlighted row. |
| `[` / `]` or Ctrl+Page | Switch detail tabs if tablist focused. |
| `g` then `t` | Optional: go to Trace in dev builds only if shortcuts are desired. |

### 10.2 Modals/popovers

- Export modal must trap focus.
- Capture popover should close on outside click and `Esc`.
- Confirmation modals should return focus to the originating control.

### 10.3 Charts and timelines

- Every SVG chart needs an accessible name and a textual data summary.
- Bars/points should be keyboard-focusable when interactive.
- Hatching must not be the only indicator of timing class.

### 10.4 Tables

- Use semantic tables or ARIA grid patterns consistently.
- Support screen-reader labels for process/status pills.
- Provide visible focus states.

---

## 11. Privacy, security, and CSP gotchas

### 11.1 Never render payloads as HTML

Payloads may contain SQL comments, provider messages, user prompts, file paths, or server strings. They must be treated as data and escaped. Avoid `dangerouslySetInnerHTML`.

### 11.2 Do not put secrets in attributes

Do not store raw or redacted-sensitive values in:

- `title` attributes;
- `data-*` attributes;
- hidden spans;
- chart tooltips;
- logs;
- search caches.

If a value is redacted, the raw value should not be in the webview DOM at all.

### 11.3 Strict CSP should shape the implementation

The prototype uses inline styles/handlers because it is a standalone design artifact. The real webview should use:

- bundled JS/CSS;
- nonce-based script loading;
- no remote sources;
- no eval;
- no inline script handlers;
- local extension resources only;
- sanitized text rendering.

### 11.4 Privacy reports should be visible, not buried

Export modal and Exports page show privacy validation. Keep a `Privacy` tab/panel for:

- current source capture mode;
- policy ID;
- redaction counts;
- classifications encountered;
- blocked fields;
- export scan result.

---

## 12. Performance and scalability notes

### 12.1 Live trace throughput

The UI must not re-render the whole app per event. Use batching/throttling:

- append live events to a buffer;
- update visible rows at a capped cadence;
- coalesce KPI updates;
- keep selection stable;
- show paused/live-tail state.

### 12.2 Tables

Virtualize:

- Trace events;
- SQL Activity;
- completions live trace;
- result sets if many;
- sessions/imports if large.

### 12.3 Charts

SVG is appropriate for deterministic local/offline rendering. Avoid heavy canvas/WebGL unless necessary. Reuse the same scale/layout code for:

- harness standalone reports;
- in-product webview;
- export summaries where possible.

### 12.4 Store query performance

Global search and filters must hit indexed fields, not scan JSON blobs. Index at least:

- session ID;
- seq;
- timestamp;
- process;
- feature;
- kind/type;
- status/severity;
- correlation ID;
- digest values;
- tags/replay IDs.

---

## 13. Visual regression targets from the screenshots

Use these as approximate screenshot tests or story fixtures:

1. **Overview:** top bar, KPI grid, recent actions, anomalies, session/import list.
2. **Waterfall:** decomposition strip, lanes, legend, correlation lines, selected activity inspector, critical path panel.
3. **Trace:** filter toolbar, event table, inline gap marker, right detail pane Cause tab.
4. **Export modal:** dimmed background, scope/privacy/validation sections, green bundle preview.
5. **Perf & Sessions top:** KPI row, latency distribution, trend chart, A/B and memory panels.
6. **Perf & Sessions lower:** variant time split, metric comparison table, SQL activity table.
7. **SQL Activity:** KPI cards, command table, redacted detail pane, query plan link, correlation chain.
8. **Connections:** STS lifecycle card, active connections table.
9. **Query & Results:** result sets table, render breakdown, row-count proof.
10. **Exports:** recent exports table, validation panel.
11. **Settings:** capture settings, retention/storage, experimental toggles.

For early implementation, fixture-backed visual tests can be more useful than brittle unit tests. Use the sample data from the prototype to avoid inventing a second little universe.

---

## 14. Build-order recommendation for codegen

### Slice 0: fixture-backed shell

- Implement webview shell, top bar, left nav, routing, theme tokens.
- Implement fixture client using prototype sample data.
- Implement Overview, Trace, and Waterfall in fixture mode.
- Add screenshot/visual tests.

### Slice 1: data contracts and store client

- Add typed webview message protocol.
- Add `DebugConsoleStoreClient` abstraction.
- Add `ClassifiedValue`, `GapRecord`, `WaterfallModel`, `DebugSource`.
- Wire mock/fixture client and VS Code bridge client behind same interface.

### Slice 2: Consolidated Trace for real data

- Query persisted events.
- Subscribe to live-tail.
- Implement real filters/search.
- Implement gap backfill.
- Implement event detail tabs.

### Slice 3: Waterfall renderer

- Normalize events into activities.
- Render timeline with timing classes and calibration display.
- Add selected bar inspector and critical path skeleton.
- Support imported perf run/harness waterfall data first if live STS data is not ready.

### Slice 4: Privacy/capture/export controls

- Implement capture chip and settings against policy model.
- Implement export modal with validation states.
- Implement privacy report display.

### Slice 5: Perf, SQL, and feature pages

- Add Perf & Sessions from imported/stored metric data.
- Add SQL Activity command explorer.
- Add Connections, Query & Results, OE feature pages with real data as available.

### Slice 6: Completions migration and Replay Lab

- Re-house existing completions UI into shell.
- Implement replay UI for completions first.
- Gate STS-backed replay behind capability checks.

---

## 15. Codegen-specific warnings

1. **Do not create a second diagnostics system for the UI.** Use the unified diagnostics event model and store. The UI is a consumer, not a separate logger.
2. **Do not silently decide privacy defaults.** Implement flags/settings/policy, but leave shipping defaults explicit and configurable.
3. **Do not fake STS2-backed replay.** Show blocked/gated states until hardening gates are satisfied.
4. **Do not treat diagnostic metrics as official.** Make official/diagnostic visible in data and UI.
5. **Do not hide live-tail gaps.** Gap rows are product honesty, not errors to suppress.
6. **Do not copy the offline HTML runtime.** Rebuild as a proper VS Code webview with strict CSP.
7. **Do not put raw sensitive values in DOM/tooltips/search.** Redaction must happen before render.
8. **Do not implement filters as local string filters only.** They must map to real store queries for large data.
9. **Do not over-specialize to the query sample.** The whole point is feature extensibility.
10. **Do not make charts beautiful at the expense of truth.** Show variance, low confidence, gaps, and small sample counts.

---

## 16. Open issues that should become backlog items

### UX/functionality

- Define session/source picker UI in detail.
- Define global search scope and result display.
- Define import bundle validation flow.
- Define capture elevation modal/popover in full.
- Define clear-all confirmation modal.
- Define narrow-width behavior for top bar and left rail.
- Define detail pane resize behavior.
- Define grouped trace view behavior.
- Define waterfall zoom/scrub and keyboard interactions.
- Define replay adapter eligibility copy.

### Technical

- Choose chart rendering package or shared internal SVG renderer.
- Choose table virtualization package/pattern consistent with extension bundle constraints.
- Add fixture data extracted from prototype.
- Add route serialization for deep links.
- Add capability model for sources and pages.
- Add CSP test harness.
- Add visual regression tests for light/dark themes.
- Add store query indexes for search/filter.

### Privacy/security

- Finalize capture defaults by build channel.
- Finalize classification enum and field handling matrix.
- Decide digest/HMAC strategy for sensitive digests.
- Define policy for SQL plan artifacts.
- Define export with unresolved gaps policy.
- Define imported bundle trust and schema migration policy.

---

## 17. Suggested acceptance checks for the first codegen pass

A useful first implementation should pass these checks:

1. Debug Console opens in a VS Code webview and uses VS Code theme variables.
2. Fixture mode renders screens matching the provided mockups for Overview, Trace, Waterfall, Perf, SQL Activity, Connections, Query & Results, Exports, and Settings.
3. Navigation, row selection, detail tabs, capture popover, export modal, live/history toggle, and waterfall bar selection work with fixture data.
4. Trace table is virtualized or has a virtualization-ready abstraction.
5. Filters/search have real state and at least fixture-backed filtering behavior; not just inert chips.
6. Redacted fields render through a shared component and raw values are not present in DOM fixtures.
7. Waterfall bars carry timing classes and display official/diagnostic/inferred differences in both visual style and text.
8. Export modal shows validation states and blocks unsafe sample export if configured to fail.
9. Settings controls are wired to state/actions, but shipping defaults come from configuration.
10. The app runs under strict CSP-compatible patterns: no inline event handlers in production bundle.

---

## 18. Final implementation posture

Build the UI like a microscope, not like a mural. The prototype’s charm is that it shows complicated evidence without theatrics: exact gaps, honest timing, redaction locks, confidence bands, and provenance quietly doing their jobs. Keep that tone.

The console will earn trust through tiny acts of honesty:

- “I missed exactly seq 10432–10645, and I can backfill it.”
- “This interval is aligned diagnostic timing, not exact monotonic timing.”
- “This SQL text is redacted by policy; here is the digest and the reason.”
- “This metric explains the regression but does not gate it.”
- “This replay path is blocked until the substrate is safe.”

Those are the important pixels. The rest is chrome.
