# Claude Code — perftest harness, Phase 2 (richer diagnostics + stress/soak + change tracking)

> Paste below the line into Claude Code, running from `C:\repos\test\perftest`. This continues
> the existing autonomous build; it keys off `IMPLEMENTATION_PLAN.md` + `PROGRESS.md` exactly
> like before. It is multi-session-sized — the restart protocol covers it. Do not stop between
> milestones.

---

## Reload context first (do this before anything else)

You built the core local perf box plus full diagnostics in a prior session (7 commits in
`perftest`, product instrumentation on `dev/karlb/perftest` in `vscode-mssql` and
`sqltoolsservice`). Resume, don't restart:

1. Read `PROGRESS.md` end-to-end (newest entries at the bottom) to recover state, seam maps, and
   verified results.
2. Read `IMPLEMENTATION_PLAN.md` — note every unchecked box and the "Deferred (seams preserved)"
   section.
3. Skim `docs/` (the 12 implementation docs) so you reuse the real contracts, collector
   framework, scenario model, regression engine, and harness telemetry rather than re-deriving them.
4. Re-read the referenced design sections in
   `../../perftest-docs/mssql-vscode-perf-system-v2/MSSQL_VSCODE_PERF_SYSTEM_DESIGN.md` as each
   milestone calls for them (§14 collectors, §17/§18 instrumentation, §19 SQL collector, §20/§24
   contracts/regression).

Then **amend `IMPLEMENTATION_PLAN.md`** with the milestones below (as checkbox tasks, same format),
open a new `PROGRESS.md` entry announcing "Phase 2," and begin **M7**, working straight through
M7 → M8 → M9 → M10 → M11 in order.

## This phase in one sentence

Make the results *richer and more varied*: capture every SQL command a scenario runs with full
detail, trace webview rendering deeply, add stress/load/soak scenarios with real memory-leak and
reliability analysis, and turn before/after comparison into a proper investigation diff — all
without weakening a single guardrail from Phase 1.

## Guardrails carry over unchanged — plus new-area honesty rules

Everything from `PERFTEST_BUILD_PROMPT.md` still holds (no VS Code fork; official metrics from
markers/product-timers in a measurement pass only; `PERF_MODE` gates every product change with
verified zero behavior when off; success proven or the rep is `invalid`; determinism, no `sleep`;
§29 redaction; **never fabricate a metric**). The new areas add specific traps — hold these
explicitly:

- **Leak & reliability results are the #1 fabrication risk.** Never report "no leak" or "100%
  reliable" from thin or noisy data. Every leak verdict carries slope + confidence interval + R²
  + sample count and must resolve to `stable | growing | inconclusive`, with `inconclusive`
  whenever the data can't support a conclusion (mirror the regression engine's CV/inconclusive
  discipline). Every reliability number is a real count of real outcomes — never suppress, retry-
  hide, or round away a failure in a reliability scenario.
- **XEvents correlation must be honest.** If captured events can't be matched to the scenario
  window and this run's connection, emit a validation warning and a `confidence` flag — not a
  guessed `sqlserver.duration`. Derived metrics that need client-side SqlClient timing (still
  deferred in STS) stay low/medium confidence and say so; do not invent the client side.
- **CDP metrics only when the target was really found.** Webviews are iframes; if the results-grid
  target can't be located, warn and emit no render metric — never a plausible number.
- **Contract changes are additive and documented.** New fields/artifacts must not break existing
  `result.json`/`comparison.json` consumers or the design fixtures (they must still validate). Bump
  `schemaVersion` only additively and document it in `docs/CONTRACTS.md`.
- **Measurement vs diagnostic split still governs soak.** A soak's latency-trend, failure-rate, and
  low-cost RSS slope may be official (measurement pass). Heap snapshots, gcdump, CDP tracing, and
  full XEvents are diagnostic-only and never official — even inside a soak.
- **SQL text capture is diagnostic-pass-only, synthetic-DB-only.** It is allowed against the
  `PerfHarness` synthetic seed for investigation, never in a measurement pass, never official, never
  in harness logs. Keep it off by default.

## Working discipline (unchanged)

One task at a time; verify before moving on (`tsc --strict` clean, unit tests for pure logic, real
E2E for anything touching launch/markers/SQL/CDP); `PROGRESS.md` entry after every task; check the
box; commit per task/milestone in `perftest` and on the product branches; grow `docs/` in the
milestone that ships each feature. If blocked, log the blocker and the safest real fallback and
continue — don't fabricate to make a milestone "pass."

Owner priority order (highest first), reflected in the sequencing below: full SQL activity capture →
CDP webview rendering → stress/load/soak → richer change tracking → scenario variety.

---

## M7 — Resource & memory sampling substrate  *(unblocks soak/leak; finishes open 4.4)*

**Goal:** a low-cost, always-available per-role resource + memory timeline that soak analysis and
change tracking can consume.

Deliverables:
- Finish `processSampler` (plan 4.4): periodic per-role CPU + working set / RSS for `vscodeMain`,
  `extensionHost`, `sts` → `process-samples.jsonl`; summaries `process.peakWorkingSet` /
  `process.cpuTime` per role. Measurement-approved (declare `cost: "low"`; add a §12.3 overhead entry).
- Low-cost memory *marker* timeline on the official plane: the driver polls `process.memoryUsage()`
  (exthost heapUsed/rss) on a timer during scenarios and emits `phase: "counter"` markers; when STS
  self-report is active, add STS managed-memory counters if cheap (else defer to diagnostic).
- Wire both into the run dir + report as a memory/CPU timeline; keep everything non-blocking.

**Acceptance:** a multi-rep run produces per-role RSS/CPU series + peak summaries and an exthost
memory timeline on the marker plane; a calibration shows the sampler is genuinely low overhead.

## M8 — Rich server-side SQL activity capture (XEvents)  *(owner priority #1; expands deferred 4.7/§19)*

**Goal:** for any scenario, capture **every SQL command it caused, with full per-command detail**,
correlated to the scenario — not just an aggregate server duration.

Deliverables:
- XEvents session (`sql/xevents/create-perf-session.sql` + `read-perf-session.sql`) capturing at
  least `rpc_completed`, `sql_batch_completed`, `sql_statement_completed`, `module_end`, and — in
  diagnostic depth — `query_post_execution_showplan`. Fields: statement text (synthetic DB only),
  duration, cpu_time, logical_reads, physical_reads, writes, row_count, client_app_name, session_id,
  request_id, timestamps. Event-file or ring-buffer target; started/stopped around the scenario window.
- **Correlation seam:** set the connection's **Application Name** to `mssql-perf/<runId>/<repId>/
  <scenarioId>` via the `ConnectionProfileSpec` the orchestrator already ships (SQL_PROVISIONING.md).
  That app name + the scenario time window is the correlation key (session_id secondary). Filter in
  the session where feasible and always re-filter at parse time.
- `sqlServerXEvents` collector + normalizer: write `artifacts/sql/sql-activity.jsonl` (every captured
  command, full detail) plus a per-scenario rollup; emit `official: false` metrics
  `sqlserver.duration` (sum), per-rpc/statement rollups, `sqlserver.logicalReads`, and derived
  `sql.networkDriver.duration` with a `derivation` block + `confidence` (limited until STS SqlClient
  timing lands — say so, don't fabricate the client side).
- Reconcile with §29 in `docs/DIAGNOSTIC_COLLECTORS.md`: SQL-text capture is diagnostic-only,
  synthetic-DB-only, never official/logged.

**Acceptance:** a diagnostic run of `connect` + `query-10k` produces `sql-activity.jsonl` listing
every command the scenario caused, each with duration/reads/row_count, correlated by app-name +
window; totals reconcile with the fixture (the 10k select shows row_count ≈ 10000). Ambiguous
correlation → warning + confidence flag, never a fabricated number.

## M9 — CDP renderer / webview tracing  *(owner priority #2; finishes open 5.2)*

**Goal:** deep rendering detail for the webviews (results grid, OE tree), correlated to the webview
marks that already exist on the official plane.

Deliverables:
- Diagnostic-only `--remote-debugging-port=<port>`; enumerate CDP targets (`/json`), locate the
  renderer target **and the specific webview target(s)** by title/URL (results-grid webview), with
  robust degrade-if-not-found.
- `cdpRendererTrace` (+ optional `cdpRendererProfile`): attach, enable Tracing with rendering
  categories (`devtools.timeline`, `blink`, `cc`, `gpu`, `loading`, `v8`) and/or Runtime/Profiler CPU
  profile over the scenario window (start on `scenario.start`, stop on `scenario.end`). Artifacts:
  `artifacts/renderer.trace.json` (Perfetto/Chrome), optional `webview.cpuprofile`.
- Diagnostic metrics from the trace (`official: false`): paint/layout/scripting time, longest task,
  time-from-data-receive-to-paint — correlated to `mssql.resultsGrid.renderComplete`.

**Acceptance:** a diagnostic run of `query-10k` yields a renderer trace with identifiable results-grid
render work and a render-time breakdown that lines up with the webview marks; missing target →
validation warning, no fake metric.

## M10 — Stress / load / soak scenarios  *(the big new capability)*

**Goal:** run an action in a long loop, measure perf drift, reliability, and memory leaks over many
iterations; and stress large catalogs. This is a distinct measurement shape from the single measured
interval — design it as a first-class extension, not a hack.

- **M10.1 Scenario-model extension (contract work).** Add an optional `loop` block to `ScenarioSpec`:
  `iterations`, `warmupIterations`, inner `steps`, per-iteration `success` criteria, `onFailure:
  continue | abort` (reliability scenarios run to completion capturing all failures), and an optional
  `settle`/`forceGc` step between iterations. Emit `iteration.start`/`iteration.end` markers with
  `attrs.index`. **Contract extension:** per-iteration records → `soak-iterations.jsonl` artifact;
  `result.json` carries *summary* metrics only (additive, backward-compatible; document in
  `docs/CONTRACTS.md`). Reuse the existing step engine and marker plane — no new imperative test code.
- **M10.2 Soak analysis module** (pure logic, unit-tested like the regression engine). From the
  iteration series + the M7 memory timeline compute:
  - **Latency:** p50/p95 + per-iteration trend (slope; is there drift?).
  - **Reliability:** failure count/rate, first-failure index, error taxonomy (connect / query /
    timeout / crash), and a correctness check (iteration N returns the same 10000 rows as iteration 1
    — no drift under load).
  - **Memory leak:** exclude warmup; linear fit of RSS vs iteration over the steady-state window →
    slope (bytes/iter) + CI + R²; retained growth after a final forced-GC/settle; classify
    plateau (healthy) vs monotonic (leak); verdict `stable | growing | inconclusive` + confidence.
  - Metrics: `soak.latency.p50/p95`, `soak.latency.slope`, `soak.reliability.failureRate`,
    `soak.memory.rssSlope`, `soak.memory.retainedGrowthMb`. Latency/reliability/low-cost-RSS are
    official-eligible in a measurement pass; heap-derived ones are diagnostic.
- **M10.3 connect→query→disconnect soak scenario** (default 1000 iterations, configurable). Needs a
  `disconnect` step (product test seam) + connection-ready/disconnect markers. Per-iteration success =
  connected + 10k rows verified + clean disconnect. Emit the memory timeline. **Acceptance:** a
  1000-iteration run completes and produces latency-trend + failure-rate + RSS-slope with CI; an
  injected leak (a `PERF_SYNTHETIC_LEAK`-style deliberately leaky path, recorded transparently) is
  detected as `growing` with confidence; a clean run reports `stable`/`inconclusive` honestly.
- **M10.4 Large-catalog fixture + OE-at-scale scenario.** New seed generating **10,000 deterministic
  synthetic tables** (scripted loop, idempotent, verified `COUNT = 10000`); `expand-tables-node-10k`
  scenario expanding the Tables node and verifying **all 10k render** (exact count, no truncation, no
  error), measuring time-to-render, with timeouts scaled for the size. Ties into M8 (SMO enumeration
  SQL) and M9 (tree paint). **Acceptance:** expand completes, tree shows exactly 10k tables verified,
  wallclock recorded; a diagnostic pass shows the enumeration SQL (XEvents) and the tree-paint (CDP).
- **M10.5 (diagnostic) leak root-cause collectors.** Exthost V8 heap snapshots at start/mid/end via
  CDP HeapProfiler (+ forced GC), diff top retainers; STS `dotnet-gcdump` at start/end, diff managed
  heap. Artifacts + a "top growth" summary; diagnostic-only; degrade gracefully if a tool is missing.

## M11 — Rich A/B change tracking (investigation diff)  *(owner priority; extends §24 comparison)*

**Goal:** turn before/after into a proper "what changed" investigation, spanning official **and**
diagnostic signals and artifacts — while gating stays official-only.

Deliverables:
- `perftest diff --baseline <run> --candidate <run>` (or `compare --investigate`) producing a full
  breakdown: official metric deltas (the existing gate) **plus** an investigation section that is
  explicitly non-gating.
- Diagnostic diffs: **SQL-activity delta** from `sql-activity.jsonl` (commands added/removed, extra
  round-trips, per-command duration/reads/row_count deltas — this is the headline "what changed"),
  component-waterfall delta, memory/soak-trend delta, render-time delta. Surface git context (SHAs /
  branch / dirty from `run_repositories`) so perf deltas correlate to code deltas. (`environmentHash`
  already excludes product SHA, so cross-code comparison is valid — keep it that way.)
- Reports: an A/B investigation report (Markdown + HTML) with "what changed" sections; extend
  `comparison.json` additively with an `investigation` block. Reuse the variance/inconclusive
  discipline; a diagnostic-only difference must never silently gate or be hidden.

**Acceptance:** run a baseline, apply a change that adds an extra SQL round-trip (or extra logical
reads), run a candidate; the diff report shows the added SQL activity and metric deltas, with the
gating verdict driven only by official metrics and the SQL-activity difference shown as investigation
context.

## Scenario variety (fold in opportunistically as data-only additions)

As milestones land, extend the scenario registry (data only, per SCENARIO_AUTHORING.md) with:
`disconnect`, `cancel-running-query`, `large-result-100k`, `reconnect-after-drop`, `multi-connection`,
and `query-error-path` (verify graceful failure, not a crash). Each with semantic success proofs and
a `docs/` note. Add any product markers these need behind `PERF_MODE`.

## Still deferred (seams preserved, do NOT build this phase)

- Central / fleet aggregation, Bencher push, shared dashboards (§30) — still the "decide together"
  item; the contracts already make it a pure add-on.
- W3C traceparent/OTLP export in STS and the envelope→OTel adapter sink (keep the documented seam).
- `mcp-server-first-request` (until the MCP surface stabilizes).

Resume now: reload context, amend `IMPLEMENTATION_PLAN.md` with M7–M11, open the Phase 2 entry in
`PROGRESS.md`, and start M7.
