# Claude Design brief — in-product diagnostics & performance analysis viewer (VS Code)

> Paste below the line into Claude Design. This is a design brief for high-fidelity mockups of an
> in-product developer-diagnostics surface. It is for planning a real feature — favor information
> architecture and clarity over decorative flourish.

---

## What we're designing

An **in-product, extensible analysis surface inside VS Code** for the MSSQL for VS Code extension —
a "first-party viewer" over a deeply instrumented SQL tooling stack. The product emits a rich,
unified diagnostics stream at runtime (semantic events, spans, SQL server activity, renderer traces,
resource/memory samples), and this surface makes all of it observable: **live as you use the
product, and historically across sessions**.

It is one **extensible host** with pluggable **pages** (think VS Code's own multi-view panels). One
page already exists as a proven pattern (the Copilot **Completions Debug** view — see "reference
pattern" below); we are generalizing that pattern into a host and adding the net-new pages.

**Users:** developers building/testing the product; AI coding agents consuming the same data as
evidence; and end users capturing "Session diag data" to attach to bug reports. Design for the
developer first.

## Design language

- **VS Code webview native.** Match VS Code's visual language and use its theme tokens; deliver both
  **dark and light** themes. It should feel like part of the editor, not a bolted-on web app.
- **Developer-tool density.** Information-dense, calm, and scannable — like Chrome DevTools /
  a profiler, not a consumer dashboard. Tables and timelines are the primary surfaces.
- **Monospace for data:** ids, timestamps, seq numbers, SQL, durations. Sans for chrome/labels.
- **The list-plus-detail pattern** (from the completions view) is the workhorse: a stream/table on
  top or left, a multi-tab **detail pane** for the selected item.
- **Restraint.** No gradients-for-drama, no oversized hero elements. This is a precision instrument.
  (Apply a strong, intentional type scale and spacing system so density still reads clearly.)

## The reference pattern to generalize (Completions Debug view)

The existing completions view — treat it as one page of the host and the model for the others:
- **Live trace table** of events as the user types: columns for time, document, trigger, mode,
  model, latency, tokens (in/out), result (accepted/cancelled/skipped), with a running header
  showing counts and averages.
- **Detail pane tabs** for a selected event: Summary, System Prompt, User Prompt, Raw Response,
  Sanitized, Schema Context, Locals (service state), Telemetry.
- **Multi-session analysis:** aggregate events across sessions, **group by** (model / profile /
  schema budget), **filter** rails, and charts — by-group latency bars, an acceptance funnel, token
  cost in/out, and a latency time-series.
- **Replay:** a replay-trace builder (ordered event list, per-event config with original-vs-override
  and snapshot/override modes) and a config matrix (profiles × schema budgets × events, showing cell
  count, est. time, execution order); replayed events are tagged in the live view.

## The host + pages to mock

### 0. Host shell
A page navigation (left rail or top tabs): **Consolidated Tracing · Cross-Process Waterfall · Perf &
Sessions · Completions · Replay**. A persistent top bar with: a **session/run selector**, a
**live ⇄ historical** toggle, a **capture-mode / privacy chip** (see cross-cutting), and a global
filter. Design the shell so adding a new page later is obvious.

### 1. Consolidated Event Tracing  *(net-new — prioritize)*
The generalized event stream across **all features and all processes** (extension host, webview, SQL
Tools Service, SQL Server), live or historical.
- **Table columns:** time, seq, process, feature, kind, type, correlation id, duration, status.
- **Detail pane:** the event envelope — kind/type/correlation/cause/entity refs/classification — plus
  its payload, with **sensitive fields shown redacted/as digests behind a lock icon** (data is
  classified; secrets/SQL/rows are not shown in the default view).
- **Cause tree:** expand an event to follow its correlation/cause chain (what caused it, what it
  caused) as an indented tree.
- **Filter/group** by process, feature, correlation id, status.
- **Live-tail gap affordance (important, and real):** the data substrate reports exactly when the
  live stream dropped events. Show an inline marker like "▸ 214 events dropped — backfill from
  journal" that the user can expand to load the exact missed range. This honesty affordance is a
  first-class part of the UX, not an error state.

### 2. Cross-Process Waterfall  *(net-new — the headline view; prioritize)*
One user action decomposed across all four tiers on a single time axis — the thing that makes the
whole system worth building.
- **Rows grouped by process:** Extension Host · Webview / Renderer · SQL Tools Service · SQL Server.
  Bars are activities: semantic markers, spans, RPC handler latencies, SQL commands, render phases
  (scripting/layout/paint).
- **Two visually distinct bar styles with a legend:** **official / measured** intervals
  (same-process monotonic, exact) rendered solid; **aligned / diagnostic** intervals (cross-process,
  aligned via clock calibration) rendered hatched/lighter — the viewer must never imply cross-process
  timing is more precise than it is.
- **Correlation lines** linking a VS Code action → its STS RPC handler → the SQL command it caused
  (using the shared correlation id).
- **Interactions:** hover for detail, zoom/scrub the time axis, and a **critical-path highlight**.
- Include a compact **summary strip** above the timeline: total wall-clock and the per-tier
  breakdown (UI / extension / STS / wire / server) as a mini stacked bar.

### 3. Perf & Sessions  *(net-new — prioritize)*
Performance analysis across runs and sessions.
- **Distributions:** latency histograms / box plots for a chosen scenario+metric.
- **Soak / trend plots:** RSS-vs-iteration with a fitted slope line **and a confidence band** (leak
  analysis), latency-vs-iteration drift.
- **A/B deltas:** before/after bars per metric, with the SQL-activity delta called out (e.g. "+3
  round-trips, +296k logical reads").
- **Cross-session trend:** a metric over time (by run / by commit) with a **baseline band** and
  **step-change markers** pointing at the run/commit where it moved.
- **SQL activity table:** every command a scenario caused — duration, CPU, logical reads, rows —
  sortable, with the SQL text redacted unless capture policy allows.

### 4. Completions  *(existing pattern, shown as a host page for continuity)*
The completions view above, re-housed in the shell.

### 5. Replay  *(net-new; generalizes the completions replay)*
- **Replay-trace builder:** select events from history → ordered sequence → per-event config with
  original-vs-override and snapshot/override modes.
- **Config matrix:** profiles/params × schema-budgets/capture-modes × events, with cell count, est.
  time, and execution order.
- **Provenance:** replayed runs/events are tagged (source run, matrix cell, overrides) and filterable
  in the trace/analysis views.

## Cross-cutting UI elements (design these once, reuse across pages)

- **Capture-mode / privacy chip:** always-visible indicator of the current data-capture level
  (redacted / digest / full) and a **explicit, visible, time-bounded "elevate capture" action** —
  capture is never silently elevated; the chip shows when elevation is active and when it reverts.
- **Classification lock:** the redacted/digest treatment for sensitive cells (SQL text, row data,
  secrets), consistent everywhere they appear.
- **Run / session provenance panel:** commit SHA(s) + dirty state, environment fingerprint, capture
  policy — so a developer knows exactly what they're looking at.
- **Export evidence bundle** action: produce a coherent, redacted session bundle for a bug report or
  an AI-agent handoff.
- **States:** design empty, loading, **gap/backfill**, and error states for the trace table and the
  waterfall specifically (these are the views most affected by live streaming and dropped data).

## Deliverable

A cohesive **design system** (type scale, spacing, color roles mapped to VS Code tokens, the table +
detail-pane + timeline components, the chips/locks/state patterns) and **high-fidelity mockups** of
the host shell and the five pages, in **both light and dark**, at developer-tool density. Prioritize
the three net-new pages — **Consolidated Tracing, Cross-Process Waterfall, and Perf & Sessions** —
and fully work out the **detail-pane** and **cross-process timeline** patterns, since everything else
composes from them. These mockups guide a build, so make the information architecture unambiguous.
