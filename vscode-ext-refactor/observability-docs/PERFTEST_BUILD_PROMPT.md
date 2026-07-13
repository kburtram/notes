# Claude Code build prompt — MSSQL VS Code performance harness

> Paste everything below the line into Claude Code, running from the root folder that
> contains `vscode-mssql/`, `sqltoolsservice/`, `perftest-docs/`, and an empty `perftest/`.
> It is written to run autonomously for as long as needed, self-checkpointing across
> milestones. You do not need to babysit it between stages.

---

## Role and mission

You are building a **local-first, deterministic, end-to-end performance harness** for the
MSSQL for VS Code extension, from a blank repo, following an existing design.

The full design already exists in `./perftest-docs/`. **Treat that design as the source of
truth.** Your job is not to redesign it — it is to implement it, incrementally, one component
at a time, verifying each piece before moving to the next, until the whole *local* system
works end to end.

We build the entire local test box. Central/fleet data aggregation is deferred, and deep
diagnostic profiling is deferred — but we preserve every seam so those drop in later without
a redesign.

## What is in the working directory

- `./vscode-mssql/` — the product extension (TypeScript). You will instrument this **later and
  minimally**, only when a scenario needs a marker, always behind a `PERF_MODE` guard.
- `./sqltoolsservice/` — SQL Tools Service (C#/.NET). **Do not touch this in this pass.** Its
  instrumentation (ActivitySource, JSON-RPC trace context) is deferred; only preserve the seam.
- `./perftest-docs/` — the authoritative design: the V2 design document
  (`MSSQL_VSCODE_PERF_SYSTEM_DESIGN*.md`), the JSON schemas (marker / perf-config / perf-result),
  the SQLite schema (`perf-store*.sql`), the example configs (`config.measurement.local`,
  `config.diagnostic.local`) and example result, and the architecture diagrams / PDF.
- `./perftest/` — **empty. Build the entire system here** as a small monorepo.

## First actions (do these before writing any code)

1. **Read all of `./perftest-docs/`.** Every markdown file, every JSON schema, the SQL schema,
   the example configs and result, and the diagrams/PDF. The V2 design document is long and is
   the master plan — read it fully. Pay special attention to:
   - §3 design principles and §A3 non-negotiable design rules,
   - §7 scenario model and §8 baseline scenario catalog,
   - §9 control plane (env vars, message types, lifecycle, failure policy),
   - §10 marker contract and §11 time/identity model,
   - §12 measurement / diagnostic / calibration passes and official-metric rules,
   - §13 launch and environment design,
   - §14 collector framework interface,
   - §20 result contract, §22 output layout, §23 local store, §24 aggregation/regression,
   - §26 CLI design and exit codes,
   - §32 build plan (Milestones 0–6) and §33 AI coding task packets.
2. **Lightly skim the two product repos** to locate the seams you'll need later — do not deep-read yet:
   - In `./vscode-mssql/`: the activation entry point, command registration, where STS is spawned
     as a child process, and how webviews send/receive messages (`postMessage` bridge).
   - In `./sqltoolsservice/`: just note where JSON-RPC is hosted and where the process starts.
     You are not modifying it now.
3. **Write two tracking files in `./perftest/` and keep them current:**
   - `IMPLEMENTATION_PLAN.md` — the full milestone → task breakdown with acceptance criteria and
     checkboxes, derived from the plan below and the design's §32/§33. This is your working
     backlog; update checkboxes as you complete tasks.
   - `PROGRESS.md` — an append-only running log: what you did, what you verified, any blockers and
     the fallback you chose, and where you are. Update it after every task so you can recover
     context after any compaction and never lose the thread.
4. Then begin **Milestone 0** and proceed through the milestones **in order, without stopping
   between them**.

## Non-negotiable guardrails (these define whether the system is trustworthy)

These come from the design's §A3 and §12. Violating any of them makes the harness lie about
performance, which is worse than useless. Hold all of them at all times.

1. **Never fork VS Code.** Instrument only through launch flags, a controlled automation
   extension, product-extension markers behind `PERF_MODE`, and (later) CDP. You measure the
   product as it ships.
2. **Official metrics come only from markers and explicit product timers, in a measurement
   pass.** An official number must never depend on ETW/WPR, CPU profiling, heap/GC dumps,
   renderer CDP tracing, `dotnet-trace`, or SQL text capture. Missing a heavy collector may
   reduce diagnostic depth; it must never corrupt an official metric.
3. **Zero behavior change with the flag off.** Every change you make to `vscode-mssql` (and any
   future change to STS) is gated on `PERF_MODE=1`. With the flag absent, the extension builds
   and behaves exactly as before. Marker writes use a bounded queue with best-effort flush and
   must never block the product critical path.
4. **Every run is reproducible.** Each run captures its full config snapshot and an
   `environmentHash` (hardware, OS, VS Code version, extension versions, STS version, SQL image
   digest, SQL seed, config knobs, pass type). Never compare official metrics across different
   environment hashes unless explicitly configured to.
5. **Success must be proven, or the rep is `invalid`.** A scenario that cannot semantically prove
   it did the right thing (e.g. 10,000 rows actually rendered) is marked `invalid` — not fast,
   not slow. Invalid reps never feed regression.
6. **Never fabricate a metric to make a milestone pass.** This is the single most important rule
   for you as an autonomous agent. If a value cannot be measured yet, emit **no** metric, or a
   clearly `official: false` one — never a plausible-looking fake number, never a hardcoded
   duration, never synthetic timing. A milestone that "passes" on fabricated data is a failure.
   If you are blocked, record it in `PROGRESS.md` and choose the safest real fallback.
7. **Determinism over convenience.** No `sleep`/fixed delays in an official scenario action path;
   use semantic waits (`waitForMarker`, command completion, webview probe). Pin the SQL Server
   image by **digest**, not a floating tag. Use fresh `--user-data-dir` and `--extensions-dir`
   per the profile mode.
8. **No sensitive data by default.** SQL text, result data, connection strings, and tokens are
   not captured by default. Perf databases use non-sensitive seed data only.

## Working discipline (how to run for a long time without drifting)

- **One task at a time.** Implement the smallest coherent unit, then verify it, then check the
  box, then move on. Do not batch many half-finished things.
- **Verify every task before moving on:**
  - TypeScript compiles clean under `strict: true`.
  - Relevant unit tests pass (contracts validate the provided example config/result/marker;
    normalizer and regression math have tests).
  - The task's own acceptance check (from the plan / design) actually runs and passes on real
    output — not a mock, for anything end-to-end.
- **Checkpoint at logical boundaries.** Keep the tree clean per milestone. If a git repo is
  present or you can init one in `./perftest/`, commit at the end of each task/milestone with a
  clear message; otherwise snapshot state in `PROGRESS.md`.
- **Contracts are copied, not reinvented.** Copy the JSON schemas and the SQL schema from
  `./perftest-docs/` into the repo verbatim (adjusting only file locations), mirror them as
  TypeScript types, and use the provided example config/result/marker as fixtures that must
  validate. If you find a genuine mismatch between the docs and reality, note it in `PROGRESS.md`
  and prefer the docs unless following them is impossible.
- **When you finally instrument `vscode-mssql`:** deep-read the relevant code first, find the
  exact seam, make the smallest possible change behind `PERF_MODE`, then confirm the extension
  still builds and runs normally with the flag off before continuing.
- **Prefer real E2E verification** for the launch/control/marker loop; use unit tests for pure
  logic. When Docker or a real SQL Server is unavailable in the environment, use the config's
  `provider: "external"` path so connect/query scenarios can still be developed against a
  reachable SQL instance — but do not fake the timing.
- **Keep going.** Do not stop to ask between milestones. Only pause for input if a decision would
  violate a guardrail, materially change scope, or requires a secret/credential you cannot obtain.
  Otherwise pick the safest design-consistent option, log it, and continue.

## Technology (follow the design's §6; use well-maintained libraries)

TypeScript on Node LTS, monorepo via npm/pnpm workspaces inside `./perftest/`. Use
`@vscode/test-electron` to acquire/resolve a pinned VS Code build, then **spawn the executable
directly** so the orchestrator owns the PID, stdio, env, and shutdown. Control channel is a
localhost (`127.0.0.1`) WebSocket JSON-RPC protected by a random token. SQLite for the local
store. JSON Schema validation at runtime. Docker Compose (image pinned by digest) for SQL Server,
with an `external` provider fallback. Reports as Markdown + static HTML. Pick sensible libraries
(e.g. schema validation, an embedded SQLite driver, a WebSocket lib, a robust process-spawner)
unless the docs specify otherwise.

Target the repository layout in design §5 and the file-level breakdown in the §33 task packets
(`packages/perftest-cli`, `packages/perf-contracts`, `extensions/mssql-perf-driver`, `sql/`,
`scripts/`, `examples/`, `perf-runs/`), adapting names as needed.

---

## The incremental build plan

Milestone numbering is **aligned to design §32**; the scope notes below reflect our priorities:
**harness first, connect + query, timing first, defer deep diagnostics and central aggregation.**
Build strictly in this order.

### Milestone 0 — Contracts and CLI skeleton  *(pure harness; touches no product repo)*
Implement `perf-contracts` (TS types mirroring the schemas) and copy the JSON schemas + SQLite
schema into the repo. Build the CLI skeleton with the §26 commands wired as no-ops/plumbing:
`doctor`, `run`, `report`, `compare`, `baseline set`, `scenarios list`, `collectors list`,
`schema validate`, plus the §26 exit-code contract. Initialize the SQLite DB from the schema.
**Acceptance:** the provided example config, result, and marker all validate against the schemas;
`tsc --strict` is clean; the SQLite DB initializes; `perftest schema validate <file>` works.

### Milestone 1 — Smallest end-to-end loop  *(the seed crystal)*
Build the local control server (WebSocket + token + the §9 message types and lifecycle), the
marker sink writing `markers.jsonl`, the VS Code launcher (fresh dirs, base launch args from
§13.1), and the `mssql-perf-driver` automation extension that connects, authenticates, sends
`hello` then `ready`, and runs a **`noop`** scenario emitting `scenario.start`/`scenario.end`.
Then: normalize into `result.json` (§20), insert rows into SQLite (§23), and generate a minimal
Markdown report. Include the clock-calibration ping/pong (§11.3) and store its offset/round-trip.
**Acceptance:** `perftest run --scenario noop` produces a schema-valid `result.json` containing an
official `scenario.wallclock`, writes `markers.jsonl`, inserts SQLite rows, and renders a report —
with VS Code launched unforked and shut down cleanly. The driver connects only when `PERF_MODE=1`.

### Milestone 2 — Product command scenarios  *(first, minimal `vscode-mssql` instrumentation)*
Now make the first minimal change to `vscode-mssql`, behind `PERF_MODE`: activation
begin/end markers and a command wrapper that emits begin/end markers, plus the product-private
perf API surface from §16.3 (guarded, not shipped publicly) at least far enough to report state
and child-process PIDs. Implement the `ext-normal-activation` scenario and a generic command
scenario in the driver. Add baseline compare plumbing.
**Acceptance:** the activation scenario produces an official `scenario.wallclock` plus an
`extension.activate` metric from real markers; with `PERF_MODE` unset, `vscode-mssql` builds and
behaves identically (verify this explicitly).

### Milestone 4′ — Timing-focused SQL scenarios: **connect + query**  *(the priority payload)*
> This is the scoped, timing-only slice of design §Milestone 4. Server-side XEvents timing
> decomposition is **deferred** (see below); build only what's needed for honest wall-clock plus
> whatever coarse component markers are cheap.

- **SQL provisioning:** Docker Compose with the image pinned by **digest**, a deterministic seed
  DB, a 10k-row query fixture, and a small Object-Explorer shape — all non-sensitive data. Support
  the `external` provider as a fallback when Docker isn't available.
- **`connect-local-container` scenario:** measured start before the connect command; measured end
  at a semantic "connection ready" signal. Add the minimal `vscode-mssql` `PERF_MODE` marker
  (`mssql.connection.ready`) if a clean seam exists; otherwise have the driver detect readiness via
  the perf-only API / OE-root probe. Emit the STS-spawn PID marker via the product perf API.
  **Official metric:** `scenario.wallclock`. Add coarse component markers (command begin/end, STS
  spawn) where cheaply available.
- **`query-10k-results` scenario:** measured start before run-query; measured end at
  `mssql.resultsGrid.renderComplete`, bridged from the webview through `postMessage` using
  `performance.timeOrigin + performance.now()` for the epoch timestamp. **Success proof:** the
  results-grid probe verifies `rowCount == 10000` — otherwise the rep is `invalid`.
  **Official metric:** `scenario.wallclock`, plus available component marks (query submit/return,
  webview data-receive, grid render) as `official: false`.
- Keep the `derived`-metric and `confidence` fields in `result.json` present but **do not** require
  any server-side timing this pass.
**Acceptance:** both scenarios run end to end and produce schema-valid results; the query scenario
proves 10,000 rows rendered and yields an official wall-clock; all product changes are behind
`PERF_MODE` with no behavior change when it's off.

### Milestone 6′ — Local baselines, comparison, and regression gate  *(local only; no central push)*
Implement baseline management, the comparison JSON, the §24 aggregation + invalid-run rules +
regression classification (compare distributions across reps — medians/variance, absolute floor
**and** % threshold, worst-metric-wins), the console/Markdown/HTML report sections from §27, and
basic artifact retention cleanup. Wire the CLI exit codes (§26) so a gated regression exits 1.
**Acceptance:** re-running a scenario against a stored local baseline reports deltas and verdicts;
a **synthetic injected delay** produces a `REGRESSED` verdict and a non-zero exit code; a
deliberately **missing required marker** yields an `invalid` run rather than a bogus fast run.

---

## Definition of done for this build

The local perf box is complete for this pass when, on a real machine:

- `perftest doctor` runs the §13.3 preflight and reports environment/idle status.
- The SQL container provisions from a digest-pinned image (or an `external` instance is used).
- VS Code launches **unforked** with fresh dirs, loading only `vscode-mssql` + `mssql-perf-driver`.
- The driver executes `noop`, `ext-normal-activation`, `connect-local-container`, and
  `query-10k-results`, each proving success semantically.
- Each rep produces a schema-valid `result.json` with an official `scenario.wallclock` (plus
  coarse component markers where available), stored in SQLite with the run's `environmentHash`.
- A run compares against a local baseline, renders a report with per-scenario deltas and artifact
  links, and **fails with exit code 1 on a synthetic regression**.
- Every `vscode-mssql` change is `PERF_MODE`-gated with verified zero behavior change when off.
- `IMPLEMENTATION_PLAN.md` boxes are checked and `PROGRESS.md` tells the full story.

## Explicitly deferred — do NOT build now, but preserve the seams

Leave the plumbing in place so these slot in later without redesign; do not rip out the
trace-context or collector interfaces to "simplify."

- **STS instrumentation (design §18):** ActivitySource/EventSource in `sqltoolsservice`, JSON-RPC
  W3C trace-context propagation, StreamJsonRpc trace strategy, SqlClient OTel. Keep the
  `PERF_TRACEPARENT`/`PERF_OTLP_ENDPOINT` env vars and the traceparent-injection seam in the
  product extension ready, but do not implement the server side.
- **Server-side SQL timing (design §19, rest of §Milestone 4):** the Extended Events collector and
  the `T_wire`/`T_exec`/`T_driver_overhead` subtraction. Keep the `derived`/`confidence` result
  fields; don't compute server timing yet.
- **Deep diagnostic collectors (design §Milestone 5):** CDP ext-host profile, CDP renderer trace,
  `dotnet-counters`, `dotnet-trace`, WPR/ETW. Keep the §14 `Collector` interface and the
  measurement/diagnostic pass split so these register later as `official: false`, diagnostic-only.
- **Central / fleet (design §Milestone 6 central, §30):** Bencher/central push and shared
  dashboards. The canonical `result.json` + SQLite schema already make this a later add-on with no
  producer changes.

Optional-but-cheap this pass: a lightweight, non-blocking `processSampler` (CPU/mem of the owned
processes) is measurement-approved and may be included, provided the harness runs fine without it.

## Reference index (design section → milestone)

- Contracts/CLI skeleton → §5, §6, §20, §23, §26, §33 task packet 1.
- E2E loop → §9, §10, §11, §13.1, §16, §33 task packets 2–4.
- Product command scenarios → §16.3, §17, §33 task packet 5.
- Connect + query (timing) → §7, §8, §13.4, §17 (webview mark bridge), §33 task packets 5, 7 (seam only).
- Baselines/regression/reports → §22, §24, §27, §31, §32 Milestone 6.
- Guardrails throughout → §A3, §12.

Begin now: read `./perftest-docs/` in full, write `IMPLEMENTATION_PLAN.md` and `PROGRESS.md` in
`./perftest/`, then start Milestone 0 and work straight through.
