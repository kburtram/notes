# 04 — Perftest ↔ Debug Console Integration

**Updated: 2026-07-03.** How the harness and the console share one data
model. Harness internals: `perftest/docs/` (ARCHITECTURE, CONTRACTS, CLI,
SCENARIO_AUTHORING, RUNNING_TESTS).

## 1. Two execution paths, one contract

| | CLI harness (`perftest`) | In-product self-test |
|---|---|---|
| Entry | `node packages/perftest-cli/dist/cli.js run --config … --scenario …` | Console "Run self-test" dialog / `DcRunSelfTest` |
| Host | Fresh VS Code launched by the CLI, driver extension + control server | The user's running VS Code, in-proc engine |
| Scenario source | CLI registry (`packages/perftest-cli` scenarios) | `@mssqlperf/inproc` catalog (`scenarios.ts`) |
| Markers | Product → PerfModeSink → control server → `markers.jsonl` | Product → diag tap → MarkerBus + persisted `markers.jsonl` |
| Official numbers | Yes (gate, baselines, SQLite store) | Yes for wallclock/metrics unless rich collection is on |
| Consumed by | Reports (`benchmark.html`-bar), `perftest history`, Perf Test History (open directory) | Perf Test History (default source), "open attached" after run |

Both write the **same run-directory layout**, which is the integration
contract (`perftest/docs/CONTRACTS.md` is authoritative):

```
<runsRoot>/<runId>/                      runId = <ISO-stamp>_<suffix>
  summary.json                           run verdicts, env, scenario totals
  <scenarioId>/rep-<n>/
    result.json                          status, wallclock, metrics, official flag
    markers.jsonl                        every forwarded event for the rep
    artifacts/…                          optional (screenshots, dumps, rich data)
```

## 2. The in-proc package (`perftest/packages/perftest-inproc`)

Self-contained (only `vscode` external); loaded by the extension at runtime
via `inprocLoader.ts` walk-up resolution (works from `dist/` and `out/`;
degrades gracefully when absent).

- `scenarioEngine.ts` — drives the real product via commands +
  `mssql.getControllerForTests`: steps (command / oeExpand with
  `oeServerLevel` / `designerOpen` / waitForMarker / sleep …),
  `createOeSession` (server-level sessions for Databases-folder access),
  `findDatabaseNode` (descends into System Databases for master/msdb/…),
  `deferCleanup` (cleanup runs even on failure/cancel).
- `markerBus.ts` — `wait(name, timeout, …, isCancelled)` with 200ms cancel
  polling and timeout diagnostics (last-5 marker tail, stale-marker note).
- `runner.ts` — rep loop; **first-rep any-failure abort** (skip remaining
  reps of a failing scenario); cancellation via `ScenarioCancelledError`.
- `scenarios.ts` — the self-test catalog: connect/query/OE-expand
  (server-level), Table Designer open, Schema Designer open, soak variants,
  console smoke, etc.
- `metrics.ts` — metric extraction from marker pairs.

~~Known deferred item~~ RESOLVED (Chunk 4, §6 below): `designerOpen` now
exists in BOTH engines with identical semantics, enforced by parity tests.

## 3. Connection modes (self-test)

`DcRunSelfTest.connectionMode`: `active` (current OE connection), `saved`
(pick a saved profile; password via credential store only), `env`
(`STS2_SQLSERVER_CONNSTRING`, parsed in-host, never shown/persisted),
`none` (connectionless scenarios only). Self-test OE sessions use
`applicationName` prefix `vscode-mssql-selftest` — this is also the hook
that suppresses designer restore prompts during runs.

## 4. History browsing (both directions)

- The console's Perf Test History default source is the self-test runs root;
  **CLI run directories can be opened as additional sources** (Open
  directory… / read-only bundles). The directory provider indexes both
  identically.
- `importPerfRun` can pull a single rep into the trace/waterfall views for
  deep-dive (forwarded spans become hatched diagnostic bars).
- The harness keeps its own SQLite store for baselines/compare; the console
  SQLite source is a read-only preview stub for now (driver not loadable in
  the extension host) — use `perftest history` or directory sources.

## 5. Verification loop used throughout the build

Non-regression: `query-10k-results` (official gate must stay green) +
`debug-console-smoke` (console-specific scenario, unofficial). Both ran
green with span forwarding active — the proof that diagnostics stay out of
official numbers while enriching the same runs.

## 6. Parity, graduation, compare, recipes (Chunks 4-6, 2026-07-04)

- **CLI designerOpen** (the long-deferred port): the driver engine gained the
  in-proc semantics — server-level OE session, Databases walk (System
  Databases descended), designer command against the real database node,
  deferred session cleanup even on failure. New CLI scenarios
  `table-designer-open` / `schema-designer-open` + `config.designers.local.jsonc`.
  Proven live: 8/8 reps passed; the rep carries the gate-eligible
  `mssql.tableDesigner.init` metric AND the `sts.dacfx.tableDesigner.*` +
  rpc.* diagnostic spans — the vision doc's Workflow 2 end-to-end.
- **Maturity**: both catalogs declare `maturity` (exploratory | diagnostic |
  measurementCandidate | ciGating | releaseGate); `query-10k-results` is the
  explicit ciGating scenario; designers start diagnostic. Defaults derive
  from `implemented`.
- **Parity conformance** (contracts package): shared metric families must
  declare identical begin/end marker pairs in BOTH hosts and agree with the
  registry's derivedFrom — a scenario graduates from self-test to CLI without
  a semantic rewrite, enforced by test.
- **In-product quick compare**: scenario rows show a verdict chip
  (regression/improved/ok/inconclusive) vs the pinned baseline — 10% AND 50ms
  floors, n≥3 both sides, IQR noise check; the tooltip states the CLI gate is
  authoritative. `ph/compareReps` + the Compare bottom tab show marker-pair
  phase deltas, per-type "what changed most" ranking, and added/removed event
  types between a current rep and a baseline rep.
- **Diagnostic recipes**: `diagnostics.recipe` in perftest configs — light /
  ui-rendering / service / sql / memory / full — expanded at config load
  (explicit flags override); heavy recipes warn when run in a measurement
  pass. Collector metrics remain diagnostic-only structurally (eligibility).
