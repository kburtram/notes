# Claude Code — perftest harness, Phase 3 (finish & sharpen)

> Paste below the line into Claude Code from `C:\repos\test\perftest`. Continues the autonomous
> build; keys off `IMPLEMENTATION_PLAN.md` + `PROGRESS.md` as before. Multi-session-sized; the
> restart protocol covers it. Don't stop between milestones.

---

## Reload context first

You completed Phase 2 core (M7 substrate, M8 SQL activity, M9 renderer trace, M10.1–10.3 soak
loop + analysis + connect→query→disconnect, leak-detection proof, M11 gate + `investigation.json`).
Open items are queued in the plan. Resume, don't restart:

1. Read `PROGRESS.md` end-to-end (newest at bottom); read `IMPLEMENTATION_PLAN.md` (all unchecked
   boxes + the "Deferred" section); skim `docs/` (now 14 docs) to reuse the real contracts,
   collector framework, scenario model, soak analysis, investigation diff, and report code.
2. Re-read the original design's **build plan (§32)** and **done criteria (§34)** in
   `../../perftest-docs/mssql-vscode-perf-system-v2/MSSQL_VSCODE_PERF_SYSTEM_DESIGN.md`, plus §27
   (report sections — the waterfall/charts this phase finishes were always in scope).

Then amend `IMPLEMENTATION_PLAN.md` with M12–M15 below, open a "Phase 3" `PROGRESS.md` entry, and
work M12 → M13 → M14 → M15 in order.

## This phase in one sentence

Get the harness to *actually done and genuinely sharp*: close every original-scope gap, add
advanced realistic scenarios, make a run's results directory a powerful standalone investigation
surface (waterfall + plots), and make cross-run tracking first-class.

## Guardrails carry over — plus this phase's honesty rules

All Phase 1–2 guardrails hold (no fork; official metrics from markers/product-timers in a
measurement pass only; `PERF_MODE` gates every product change, zero behavior when off; success
proven or `invalid`; determinism, no `sleep`; §29 redaction/synthetic-data; **never fabricate a
metric**; contract changes additive + documented + fixtures still validate). New-area traps:

- **Cross-process timeline alignment must be honest.** The waterfall aligns events from different
  processes using the epoch plane + the per-process clock-calibration offset already captured.
  Visually and in data, distinguish **official monotonic intervals** (exact, same-process) from
  **epoch-aligned diagnostic intervals**, label the plane, and surface the calibration jitter.
  Never render cross-process ordering as more precise than calibration supports.
- **Plots show real variance, not smoothed stories.** Distributions show the real spread; soak
  trends show the fitted slope *with* CI band and R² and sample count; small-n is flagged. No
  curve-fitting that hides noise; no implied precision.
- **Advanced scenarios prove what they claim.** Every new interaction (scroll → windowed fetch,
  cancel, expand-at-scale, completion) is proven semantically from product data — e.g.
  virtual-windowing must be proven *triggered* by product markers, never assumed. Add the markers
  behind `PERF_MODE`.
- **Reports stay self-contained.** No external asset fetch — inline SVG/JS only (opened as
  `file://`); everything regenerable from `result.json` + artifacts via `perftest report <runId>`.

## Working discipline (unchanged)

One task at a time; verify before moving on; `PROGRESS.md` entry after each; check the box; commit
per task/milestone across the three repos; grow `docs/` in the milestone that ships each feature.
Blocked ⇒ log it + safest real fallback, continue. Owner priority: finish gaps → advanced tests →
analysis → cross-run tracking.

---

## M12 — Complete original scope + Phase-2 tail  *(audit, then close gaps)*

**Goal:** the *original* harness is truly done — nothing important from the design left implicit.

- **M12.0 Gap audit (first task).** Reconcile built features against design §32 + §34 + every open
  box in the plan. Write the gap list into `IMPLEMENTATION_PLAN.md` with a box each. Anything that
  stays open must be explicitly "blocked because …", not silently dropped.
- **M10.5 leak root-cause collectors** (attribute the ~30KB/iter exthost growth from the
  connection-cycling soak). Exthost V8 heap snapshots at start/mid/end via CDP HeapProfiler +
  forced GC, diff top retainers/constructors; STS `dotnet-gcdump` at start/end, managed-heap diff;
  "top growth" summary; diagnostic-only, degrade gracefully. **Acceptance:** the soak diagnostic
  pass names the top retainers behind the growth.
- **M10.4 10k-table catalog + `expand-tables-node-10k`.** Deterministic 10,000 synthetic tables
  seed (scripted, idempotent, verified `COUNT=10000`); scenario expands the Tables node, verifies
  all 10k render (exact count, no truncation, no error), timeouts scaled; ties into M8 (SMO
  enumeration SQL) and M9 (tree paint).
- **11.3 investigation report (md/html) + acceptance.** Render the investigation diff (currently
  JSON-only) as self-contained md/html with the SQL-activity delta as the headline. **Acceptance:**
  a baseline-vs-candidate run where the candidate adds an SQL round-trip shows the added activity;
  the gate verdict stays official-only.
- **dotnet-counters live attach.** Solve the Windows graceful-stop for `dotnet-counters collect`
  (stop-file / CTRL-break / `--duration`, whatever is reliable); live time-series of the
  `Microsoft-SqlTools-Sts2` counters + GC/working-set/threadpool; diagnostic-only.
- **Scope-gap closures needed downstream:** implement the reserved **`objectExplorerProbe`** and
  **`webviewProbe`** step types (M13 needs them); implement **`coldDb`** cache mode (container
  restart / `DBCC DROPCLEANBUFFERS`) for cold-start fidelity; document the STS-waterfall limitation
  (legacy path journals lifecycle only — full parenting lands as v2 traffic grows) and keep
  `sql.networkDriver.duration` confidence-tagged pending STS SqlClient client-side timing.
- **Scenario variety basics:** `cancel-running-query`, `query-error-path`, `large-result-100k`
  (data-only, using the new probe steps).

**Acceptance:** §34 done-criteria all met or residuals documented as blocked-with-reason; queued
Phase-2 boxes closed; the exthost-growth finding has a named root-cause candidate.

## M13 — Advanced, realistic scenarios

**Goal:** exercise the product like a heavy real user. Each scenario = seed/fixture + interaction
steps + semantic success proofs + any `PERF_MODE` markers it needs.

- **`query-large-scroll-virtual-window`** — 100k+ row result; drive the grid to scroll and force
  virtualized windowed fetch/render; product markers for window-fetch begin/end + rows-rendered
  per window; success = correct rows at multiple scroll offsets **and** windowing proven triggered
  (not full materialization).
- **`query-blob-xml`** — large `VARBINARY(MAX)`/`XML`/`NVARCHAR(MAX)` cells; success = correct
  sizes/content rendered; measure transfer + cell render.
- **`query-many-result-sets`** — 25–50 result sets in one batch; success = all grids present with
  correct shapes.
- **`query-wide-columns`** — hundreds of columns; success = full column set rendered.
- **`oe-expand-mixed-schema` / `oe-expand-deep` / `oe-refresh`** — mixed object types
  (tables/views/procs/functions/columns/indexes/keys), deep nesting, refresh; success = tree
  correctness via `objectExplorerProbe`.
- **`intellisense-completion-latency`** — trigger completions in a large schema (foreshadows
  Phase 4's completions instrumentation); measure completion latency; success = expected
  suggestions returned.
- **`query-cancel-midflight`, `reconnect-after-drop`, `large-script-execution`** — realistic
  reliability/perf paths. Add heavy ones as soak variants where useful (e.g. scroll-heavy soak).

**Acceptance:** each runs E2E with real semantic proofs; the virtual-windowing scenario
demonstrably triggers windowed fetch (proven from product markers); OE advanced scenarios verify
tree correctness at scale.

## M14 — Analysis & viewer: cross-process waterfall + plots + standalone results

**Goal:** finish the design's §27 report intent so a run's results dir is a standalone
investigation surface.

- **Cross-process activity waterfall (per rep):** align all events — driver/product/webview
  markers, STS envelope-journal RPC latencies/spans, SQL commands (XEvents), CDP render phases —
  on one time axis via the epoch plane + per-process calibration offset; rows per process/
  component; bars per activity; hover detail; inline SVG+JS, self-contained. Distinguish official
  monotonic intervals from epoch-aligned diagnostic ones; label planes; show jitter.
- **Metric plots (run summary):** latency distributions (histogram/box), soak trends (RSS-vs-
  iteration with fitted slope + CI band; latency-vs-iteration), per-metric A/B delta bars,
  SQL-activity top-N by duration/reads. Inline SVG, deterministic, self-contained.
- **Standalone run `index.html`:** ties waterfall + plots + SQL-activity table + soak analysis +
  validations + environment fingerprint + artifact links; zip-and-share; regenerable via
  `perftest report <runId>`.
- **Factor the timeline/plot renderers into a reusable module** — Phase 4's in-product views will
  render session data with the same code.

**Acceptance:** a run's `index.html` opens offline (no external fetch) and shows the cross-process
waterfall intermixing VS Code + STS + SQL on one timeline (planes labeled) plus the metric plots;
`perftest report` regenerates it from stored artifacts.

## M15 — Cross-run tracking, trends, baselines, local history

**Goal:** make investigating behavior across many runs first-class (beyond 2-run A/B).

- **Many-run trend:** `perftest trend --scenario <id> --metric <name> [--last N] [--by time|sha]`
  → time-series with baseline band, rendered via the M14 plot module.
- **Local history dashboard:** implement `perftest serve [--db][--runs]` (or generate
  `history.html`) reading the SQLite store — per-scenario trends, recent runs, recent regressions,
  environment changes; self-contained/local.
- **Richer baselines:** named baselines `list`/`show`/promote; **rolling/auto-baseline** (median of
  last N green runs on the same `environmentHash`) to cut single-baseline noise; config wiring.
- **Run tagging/labels** (`before-fix`/`after-fix`/PR#) via the `runs` table; filterable in
  trend/history/diff.
- **Step-change attribution:** in a trend, flag the run where a metric stepped and surface its git
  SHA (bisect-style pointer) so a perf change maps to a code change.

**Acceptance:** after several runs, `trend`/history shows a metric's trajectory with baseline band;
a rolling baseline reduces noise vs a single-run baseline; a deliberate step-change is flagged with
the introducing run/SHA.

## Deferred (unchanged; seams preserved)

Central/fleet aggregation & Bencher push (still the "decide together" item); STS W3C
traceparent/OTLP export (seam preserved); `mcp-server-first-request`.

Resume now: reload, run the M12.0 audit, amend the plan with M12–M15, and work through.
