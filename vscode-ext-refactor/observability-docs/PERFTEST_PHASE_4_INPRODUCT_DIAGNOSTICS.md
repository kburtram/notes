# Claude Code — In-product diagnostics & consolidated debug UI (Phase 4)

> Paste below the line into Claude Code from `C:\repos\test`. This is the major scope expansion:
> runtime "Session diag data" in the shipping product, an extensible in-product analysis view,
> consolidated cross-process/-feature tracing, and replay. It **starts with a design doc and
> decision-flagging**, then builds in stages — see "How this phase differs" below.
>
> **Prerequisite:** Phase 3 should be substantially done — this phase reuses the harness
> instrumentation and the Phase-3 waterfall/plot/trend renderers.

---

## The thesis (why this is one system, not four)

The harness markers/events, the STS2 envelope journal, and the Completions session log are **the
same telemetry viewed three ways**. Unify them into one diagnostics substrate with three
consumption modes:

1. **Automation / harness** — the perftest harness (`PERF_MODE` sink). Already built.
2. **AI-coding-agent** — the same trace data as structured evidence for coding agents (the PDF's
   "richer runtime traces for agentic development").
3. **Normal use — "Session diag data"** — the product, when the user enables it, persists the same
   rich diag locally across sessions (exactly what the Completions feature already does).

On top of that substrate sits **one extensible in-product analysis view** (the Completions debug UI
in `MSSQL_for_VS_Code_Completions_Event_Instrumentation.pdf`, generalized into a host with
pluggable pages: consolidated event tracing, cross-process waterfall, perf-across-sessions, and
replay). That view is the payoff: run the product in automation, in AI-coding loops, or as a normal
user; collect all the data; see the bugs; experiment with changes.

**Reuse, don't rebuild.** The product's runtime diag and the harness's `PERF_MODE` markers must
share emission points — the difference is *sink + gate*, not duplicated instrumentation. The
in-product views must reuse the Phase-3 waterfall/plot/trend renderers over Session Diag data.

## How this phase differs from Phases 1–3

Phases 1–3 ran autonomously to completion. Phase 4 touches **shipping product UX**, **real user-data
privacy**, and **STS2 sequencing** — decisions the owner must make. So:

- **Start by producing `IN_PRODUCT_DIAGNOSTICS_DESIGN.md`** (thesis, diagnostics event model,
  sink/store design, UI-host architecture, privacy model, STS2 sequencing, staged milestones), and
  **flag the decisions listed below** in `PROGRESS.md` before building any shipping-surface behavior.
- Then build the internal/experimental scaffolding autonomously (substrate + UI host + one reference
  page). **Do NOT unilaterally set privacy defaults or shipping behavior** — build it gated and
  experimental, surface the choices.
- Keep the same DNA: guardrails, honesty rules, `IMPLEMENTATION_PLAN.md` + `PROGRESS.md` discipline,
  docs-per-milestone, commit-per-task across repos.

## Decisions to flag for the owner (do not decide these unilaterally)

- **Privacy defaults:** Session diag off by default; opt-in; local-only; never auto-upload. What is
  captured by default vs opt-in? (SQL text, schema, result data are now the *user's real data*, not
  synthetic.)
- **Ship vs internal:** Is the debug view dev-only / behind an experimental flag / shipped for
  support & bug-reports? What surface is user-facing?
- **STS2 sequencing:** The replay pillar depends on STS2 hardening (see below) — when does that land?
- **Which features get replay** (feature-by-feature): completions first (already has it), then
  query/connection where deterministic.
- **Storage & retention:** Session Diag store format (reuse the STS2 JSONL-segment journal pattern
  vs SQLite), size caps, retention, user controls.

## Guardrails carry over — plus privacy-first (this phase's central constraint)

All prior guardrails hold. The new one dominates: **normal-use capture is real user data**, so the
harness's synthetic-only assumption no longer applies. Every capture path is **opt-in, local-only,
never auto-uploaded, classified, redacted (secrets/connection strings/tokens never persisted), and
retention-capped, with user-visible view/clear/export controls**. This extends design §29 to real
data and directly implements the STS2 review's capture-policy findings (R004/R005/R017/R018:
sensitive lifetime + capture bounded by an immutable host policy). Off ⇒ zero capture, zero cost.

---

## Stage 4a — Unify the diagnostics substrate + Session Diag capture

**Goal:** one event model, pluggable sinks; product-side capture to a local cross-session store,
user-gated.

- **Common diagnostics event model:** generalize harness markers/events + Completions session events
  + STS2 envelopes into one schema with `feature` / `process` / `category`, correlation ids
  (harness `traceId` + STS2 `corr`/`cause`), and a data `classification`.
- **Pluggable sinks:** the existing harness sink (`PERF_MODE`) **plus** a new **Session Diag store**
  (user-enabled, local, cross-session). Same emission points, different sink/gate.
- **Extension side:** a diagnostics core routing events; a user setting enables persisting a
  classified, redacted Session Diag log across VS Code sessions (the Completions logs are the
  template). Classification + redaction + retention + user controls from day one.
- **STS side:** promote the STS2 envelope journal to a user-enablable session-diagnostics source,
  bounded by an immutable host capture policy (R017/R018). **Gated on STS2 hardening** for
  correctness/privacy — until then treat STS-side session capture as experimental/internal.

**Acceptance:** with the setting on, normal use (connect, query, completions, OE) persists a
classified/redacted Session Diag log across sessions; with it off, zero capture; the user can
view/clear/export.

## Stage 4b — In-product extensible analysis UI (the debug view)

**Goal:** the extensible webview *host* the Completions debug view is one instance of.

- **Host/shell:** a page registry, shared live-event stream + multi-session store access, shared
  filters/grouping, and shared renderers (**reuse the Phase-3 waterfall + plot modules**).
- **Reference pages:**
  - **Completions** — generalize the existing Completions debug view onto the host (live trace,
    multi-session analysis, config grouping). The PDF is the spec.
  - **Consolidated Event Tracing** — all features' events, live + historical, filter/group.
  - **Cross-process waterfall** — VS Code (exthost/webview) + STS events intermixed on one timeline
    with causal links, reusing the Phase-3 renderer over Session Diag data.
  - **Perf-across-sessions** — perf metrics/trends across sessions (reuse the Phase-3 trend module).
- **Live + multi-session parity** with the Completions UX (inspect request/response/state; group by
  config; compare latency/error/etc.).
- **AI-coding-agent path:** expose Session Diag + waterfall as structured evidence a coding agent can
  consume (the PDF's agentic-traces scenario; your AI-coding loops).

**Acceptance:** an in-product debug view with ≥3 pages (completions, consolidated tracing,
cross-process waterfall) renders real Session Diag data; live + multi-session views work; renderers
are shared with the harness reports.

## Stage 4c — Replay infra in the UI (feature-by-feature, on STS2)

**Goal:** generalize the Completions replay pattern (PDF) across features, with STS-side determinism
from STS2 replay.

- **Replay-trace builder:** select interesting/historical events → sequence → resubmit with original
  or overridden config → expand into config-matrix runs → replay events tagged + persisted so they
  can be isolated in analysis. The Completions replay/matrix UX is the template.
- **STS-side determinism via STS2 replay** (byte-identical journal replay). **GATED** on STS2
  hardening — the review's R006/R007 (replay can accept a truncated tail; readers can combine runs)
  and R017/R018 (export not a coherent snapshot; capture unbounded) must be closed first, or replay
  is untrustworthy. See sequencing below.
- **Feature-by-feature adapters:** completions first (exists), then query/connection where the
  operation is deterministic and safely replayable. Be honest where a feature isn't replayable yet —
  don't fake replay fidelity.

**Acceptance:** a feature's historical event sequence replays with original/overridden config and
matrix expansion, results tagged and analyzable; STS-side replay used only where STS2 guarantees it.

## STS2 dependency & sequencing

The replay vision leans on the STS2 refactor, which the review
(`00_EXECUTIVE_SUMMARY.md`) says should **not be tagged preview yet** — the blockers are at the
live-runtime edges, and several are exactly what in-product replay/capture depends on:

- **4a (STS-side session capture)** needs the capture-policy work (Wave 4 / R017/R018) to be safe on
  real data.
- **4c (STS-side replay)** needs journal/replay strictness + run isolation (Wave 2 / R006/R007) and
  the capture policy (Wave 4).

Therefore: **4a extension-side capture and 4b (UI host + pages + consolidated tracing) can proceed
now** — they don't require STS2 replay. **STS-side capture and 4c replay wait** on the corresponding
STS2 waves and the owner's call. Surface this in the design doc and don't build STS-side replay on an
unhardened journal.

## Start here

1. Produce `IN_PRODUCT_DIAGNOSTICS_DESIGN.md` (thesis, event model, sink/store, UI-host
   architecture, privacy model, STS2 sequencing, staged milestones for 4a/4b/4c).
2. Flag the "decisions to flag for the owner" list in `PROGRESS.md` and pause on shipping-surface
   privacy/UX defaults.
3. Build autonomously: 4a extension-side substrate + Session Diag capture (gated, experimental,
   privacy-first) → 4b UI host + one reference page (start with the generalized Completions page,
   then the cross-process waterfall page reusing the Phase-3 renderer).
4. Hold STS-side capture and 4c replay pending STS2 hardening + the owner's decisions; keep the
   seams ready.

Deferred (unchanged): central/fleet aggregation & Bencher push.
