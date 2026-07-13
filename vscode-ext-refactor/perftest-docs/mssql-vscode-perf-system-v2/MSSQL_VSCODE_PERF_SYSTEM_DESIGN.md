# MSSQL for VS Code Scenario Performance System - Review and Implementation Design v2

Status: implementation-ready design draft  
Scope: local-first performance harness for the MSSQL for VS Code extension, SQL Tools Service, SQL Server container, complex webviews, and spawned helper processes such as MCP servers  
Base input: `PERF_SYSTEM_DESIGN.md`  
Last updated: 2026-06-29

## 0. Executive summary

The initial design is strong. The most important choices are right: do not fork VS Code, run real end-to-end scenarios, separate cheap measurement from heavy diagnostics, use a canonical per-repetition result contract, propagate W3C trace context through the extension to STS boundary, and collect server-side SQL execution data so client, driver, wire, and server time can be separated where the data supports it.

This v2 keeps those decisions and turns the design into a buildable system. The main additions are:

1. A precise control protocol between the orchestrator and the VS Code automation extension.
2. A formal scenario model with setup, action, readiness, success, cleanup, and metric definitions.
3. A strict distinction between official metrics and diagnostic metrics.
4. Formal contracts for markers, result records, config, artifacts, and regression comparisons.
5. A concrete local SQLite schema and filesystem layout.
6. Implementation-ready collector interfaces and lifecycle rules.
7. Concrete instrumentation plans for `vscode-mssql`, STS, webviews, SQL Server, and arbitrary child processes such as MCP servers.
8. Setup-script requirements for off-the-shelf Windows and Linux machines.
9. Validation and acceptance tests that prove the harness is measuring what it claims.

The recommended first milestone is deliberately small: launch VS Code with a fresh profile, load only `vscode-mssql` and the automation extension, execute one command-only scenario, write `markers.jsonl`, write `result.json`, persist into SQLite, and render a tiny report. That is the seed crystal. Everything else grows around it.

---

# Part A - Review of the initial design

## A1. What to keep

The original document has the right spine. Keep these decisions unchanged unless a later validation test disproves them.

| Decision | Why it is good | Keep as |
|---|---|---|
| Local-first, central-ready | Developers need investigation artifacts on their perf box, while central infra can come later. | Local filesystem plus SQLite now, optional Postgres or Bencher later. |
| VS Code is not forked | It keeps the perf system maintainable and close to the product shipping reality. | Instrument only through launch flags, CDP, the product extension, and the automation extension. |
| Two controlled extensions | A product extension should expose product timing, while a driver extension owns scenario execution. | `vscode-mssql` plus `mssql-perf-driver`. |
| Measurement vs diagnostic passes | Heavy profiling perturbs wall-clock numbers. | Official regression metrics come from a cheap pass. Heavy collectors run in diagnostic passes. |
| `result.json` contract | A single per-rep contract keeps reports, stores, dashboards, and regression logic swappable. | Keep it, but formalize it as JSON Schema and store unified metrics. |
| W3C trace context over JSON-RPC | This is the seam that turns disconnected process traces into a component waterfall. | Make it a first-class acceptance test. |
| SQL Server side timing | SqlClient spans alone cannot separate server execution from client, driver, and wire time. | Use Extended Events first, `STATISTICS TIME, IO` only as a fallback or special scenario collector. |
| Collector state machine | Diagnostics have different attach and teardown points. | Use an explicit plugin interface and run-state transitions. |
| Artifact retention policy | ETL, traces, heap snapshots, and profiles can become enormous. | Keep raw artifacts by policy: `always`, `on-regression`, `on-failure`, or `never`. |

## A2. What needed clarification or correction

| Area | Initial design gap | v2 fix |
|---|---|---|
| Control plane | The orchestrator-to-extension protocol was implicit. | Define a localhost WebSocket or JSON-RPC control channel with auth token, message schemas, lifecycle, and failure behavior. |
| Official metrics | The document says spans are cheap, but full tracing can still perturb measurements. | Mark each metric with `official: true/false`; official scenario metrics are derived from markers and explicit product timers only. OTel spans can be minimal in measurement mode and full in diagnostic mode. |
| Scenario definitions | Scenario names existed, but not actions, success criteria, or measured intervals. | Add a scenario DSL with deterministic setup, action, success, cleanup, and metric definitions. |
| VS Code launch | The doc listed useful flags, but not a reproducible launch strategy. | Use fresh `--user-data-dir` and `--extensions-dir`, install only test extensions, pin VS Code version, and hard-fail if another Code instance contaminates the run. |
| CDP details | CDP flags differ by VS Code/Electron version and target type. | Treat CDP as a diagnostic capability that is probed at runtime. The launcher validates extension-host and renderer targets before running CDP collectors. |
| Webview timing | It mentioned User Timing marks, but not how to align them or define paint. | Use `performance.timeOrigin + performance.now()`, `PerformanceObserver` where available, double `requestAnimationFrame` for visual completion, and bridge all marks through `postMessage`. |
| SQL timing subtraction | The formula was right, but matching and limitations were underspecified. | Match SQL events by `runId`, `scenarioId`, `repId`, `connectionId`, `client_app_name`, `session_context`, SQL hash, and time window. Store provenance and confidence. |
| Store | SQLite was suggested, but no schema existed. | Add `perf-store.schema.sql` with runs, reps, metrics, artifacts, environments, baselines, and comparisons. |
| Setup scripts | The design asked for scripts, but did not define what they should install or validate. | Add setup-script contract, preflight checks, and acceptance output. |
| Security and PII | SQL text capture was noted but not governed. | SQL text and result data capture are off by default. Perf DBs use non-sensitive seed data. All captures get a data classification. |
| Regression method | Welch tests and thresholds were mentioned, but sample-size and invalid-run policy were not explicit. | Require minimum sample sizes, effect-size thresholds, CV checks, idle checks, and environment hash matching. |
| Child processes beyond STS | MCP server was not generalized. | Add a child-process registry and role-based instrumentation for STS, MCP, and future helper processes. |

## A3. Non-negotiable design rules

1. The official number must not depend on ETW, CPU profiling, heap snapshots, renderer tracing, or `dotnet-trace`.
2. Every per-component metric must declare its source and derivation.
3. Every run must be reproducible from its config snapshot and environment fingerprint.
4. Every diagnostic artifact must be reachable from the report and tied to `runId`, `repId`, `scenarioId`, and `traceId`.
5. Every regression comparison must say which baseline, environment hash, sample count, aggregation method, and threshold model it used.
6. A missing collector must degrade the diagnostic depth, not corrupt the official metric.
7. A scenario that cannot prove success must be marked invalid, not slow or fast.
8. SQL text, result data, connection strings, tokens, and customer-like data must never be collected by default.

---

# Part B - Improved implementation design

## 1. Goals

The system measures realistic end-to-end product scenarios for the MSSQL for VS Code extension and decomposes performance by component whenever visibility exists.

Primary goals:

- Run repeatable scenario performance tests locally on a dedicated perf machine.
- Support future central execution without redesign.
- Measure all-up wall-clock scenario time.
- Attribute time to extension host, renderer/webview, STS, JSON-RPC, SMO, DacFX, SqlClient, SQL Server, and child processes where possible.
- Store local history and compare to local or central baselines.
- Collect rich diagnostics only when requested or when a regression needs investigation.
- Generate human reports and machine-readable files that an AI coding agent can consume.

## 2. Non-goals

- Do not fork VS Code.
- Do not build a replacement for Playwright, PerfView, Perfetto, OpenTelemetry, or Bencher.
- Do not make diagnostic-pass timings the official regression signal.
- Do not guarantee true cold OS file cache behavior on ordinary developer boxes.
- Do not depend on pixel-based UI automation for primary scenarios when VS Code commands and extension APIs can execute the action deterministically.
- Do not collect production or customer data.

## 3. Design principles

- Prefer semantic markers over screen scraping.
- Prefer stable component contracts over fragile log parsing.
- Prefer process-local monotonic durations for exact intervals, plus epoch timestamps for cross-process alignment.
- Prefer one orchestration spine with pluggable collectors.
- Prefer local artifact-first storage, then optional central push.
- Prefer repeatability over maximal realism when the two conflict.
- Always record enough metadata to explain a number later.

## 4. System architecture

```text
perftest CLI
  config loader
  environment preflight
  scenario planner
  SQL provisioner
  VS Code launcher
  local control server
  marker sink
  OTLP sink or collector bridge
  collector manager
  normalizer
  SQLite writer
  regression engine
  report generator
        |
        | launch flags, env vars, fresh dirs, local control token
        v
VS Code Desktop, unforked
  main process
  renderer and webviews
  extension host
    vscode-mssql extension
    mssql-perf-driver automation extension
        |
        | JSON-RPC with W3C traceparent and perf metadata
        v
SQL Tools Service process
  JSON-RPC dispatcher
  connection/query/object explorer services
  SMO wrappers
  DacFX wrappers
  SqlClient instrumentation
        |
        | TDS
        v
SQL Server container
  restored perf database
  Extended Events session
  optional STATISTICS TIME/IO fallback

Other child processes
  Copilot MCP server
  future helpers
  process-role registry
  optional OTel/marker integration
```

## 5. Recommended repository layout

```text
perf-system/
  README.md
  docs/
    MSSQL_VSCODE_PERF_SYSTEM_DESIGN_V2.md
    SCENARIO_AUTHORING.md
    DIAGNOSTIC_COLLECTORS.md
    MACHINE_SETUP.md
  packages/
    perftest-cli/
      src/
        cli.ts
        config/
        control/
        launch/
        scenarios/
        collectors/
        normalize/
        store/
        regression/
        report/
      test/
      package.json
      tsconfig.json
    perf-contracts/
      src/
        marker.ts
        result.ts
        config.ts
        controlMessages.ts
      schemas/
        perf-result.schema.json
        perf-config.schema.json
        marker.schema.json
  extensions/
    mssql-perf-driver/
      package.json
      src/
        extension.ts
        controlClient.ts
        scenarios/
        probes/
        webviewProbe.ts
        objectExplorerProbe.ts
        resultGridProbe.ts
  sts-instrumentation/
    README.md
    examples/
      ActivitySources.cs
      JsonRpcTraceContext.cs
      SqlClientOtel.cs
  sql/
    docker-compose.sqlserver.yml
    seed/
      create-perf-db.sql
      query-10k.sql
      object-explorer-shape.sql
    xevents/
      create-perf-session.sql
      read-perf-session.sql
  scripts/
    setup-windows.ps1
    setup-linux.sh
    verify-machine.ps1
    verify-machine.sh
  examples/
    config.measurement.local.jsonc
    config.diagnostic.local.jsonc
    scenarios.local.jsonc
  perf-runs/
    .gitignore
```

## 6. Technology choices

| Component | Recommended implementation | Reason |
|---|---|---|
| Orchestrator | TypeScript on Node.js LTS | Same ecosystem as VS Code extension tests; easy CDP and JSON handling. |
| VS Code launch/acquire | `@vscode/test-electron` for download/resolve, direct spawn for full PID and argument control | Keeps official test tooling while preserving perf harness control. |
| Control channel | Local WebSocket JSON-RPC, bound to `127.0.0.1`, protected by random token | Full-duplex, simple, debuggable, works across extension host and orchestrator. |
| Marker transport | Same control channel plus append-only local sink | Low overhead, no external service required. |
| Contracts | TypeScript types plus JSON Schema | Allows shared compile-time types and runtime validation. |
| Local store | SQLite | Zero service dependency, simple local queries, easy central migration. |
| Artifacts | Filesystem under `perf-runs/<runId>` | Large traces stay out of the DB. |
| Tracing | OpenTelemetry in JS and .NET, OTLP export when enabled | Standard cross-process spans. |
| .NET diagnostics | `dotnet-counters`, `dotnet-trace`, `dotnet-gcdump` | Standard EventPipe tooling. |
| Windows system diagnostics | WPR/WPA and PerfView | Standard ETW capture and analysis. |
| Renderer diagnostics | CDP tracing and CPU profiles, viewed in Perfetto or Chrome trace tooling | Standard Chromium diagnostics. |
| Regression backend | Local SQLite first, optional Bencher push | Local velocity now, central trend later. |
| Reports | Markdown plus static HTML | Good for humans and agents. |

## 7. Scenario model

A scenario is not just a script. It is a complete reproducible experiment.

Each scenario defines:

- Identity: stable `scenarioId`, display name, owner, tags.
- Profile mode: fresh profile, warmed profile, or reused profile.
- Workspace mode: empty, seeded SQL workspace, or scenario-specific workspace.
- SQL state: database snapshot, container image digest, cache mode.
- Launch requirements: flags, environment variables, extension set.
- Setup steps: preconditions run before the measured interval.
- Start marker: exact moment the measured interval begins.
- Action steps: commands, extension calls, or controlled UI interactions.
- Success criteria: semantic checks that prove the scenario completed correctly.
- End marker: exact moment the measured interval ends.
- Cleanup steps: close panels, reset DB state, clear caches if configured.
- Metrics: official metrics, diagnostic metrics, resource metrics, derived metrics.
- Timeouts: readiness, action, teardown, collector flush.
- Invalid conditions: any state that makes the result unusable.

Example scenario definition:

```jsonc
{
  "scenarioId": "query-10k-results",
  "displayName": "Run query with 10000 result rows",
  "tags": ["query", "results-grid", "webview", "sqlclient"],
  "profileMode": "warmed",
  "workspace": "workspaces/query-basic",
  "sql": {
    "database": "PerfHarness",
    "snapshot": "seed-v4",
    "cacheMode": "warm",
    "connectionProfile": "local-container"
  },
  "setup": [
    { "type": "command", "command": "mssql.connect", "args": ["local-container"] },
    { "type": "waitForMarker", "name": "mssql.connection.ready", "timeoutMs": 30000 },
    { "type": "openDocument", "path": "queries/select-10000.sql" }
  ],
  "measure": {
    "start": { "type": "beforeCommand", "command": "mssql.runQuery" },
    "action": [
      { "type": "command", "command": "mssql.runQuery" }
    ],
    "end": { "type": "waitForMarker", "name": "mssql.resultsGrid.renderComplete" },
    "timeoutMs": 120000
  },
  "success": [
    { "type": "markerSeen", "name": "mssql.query.rowsRendered", "attrs": { "rowCount": 10000 } },
    { "type": "webviewProbe", "probe": "resultsGrid", "assert": "rowCount == 10000" },
    { "type": "noErrors", "sources": ["automation", "vscode-mssql", "sts"] }
  ],
  "metrics": [
    { "name": "scenario.wallclock", "source": "marker", "official": true, "lowerIsBetter": true },
    { "name": "webview.resultsGrid.render", "source": "webviewMark", "official": false },
    { "name": "sts.query.execute", "source": "otelSpan", "official": false },
    { "name": "sql.server.duration", "source": "xevent", "official": false }
  ]
}
```

## 8. Baseline scenario catalog

| Scenario | Profile | Measured start | Measured end | Official metric | Required success proof | Key breakdowns |
|---|---|---|---|---|---|---|
| `ext-first-launch` | Fresh user data dir and fresh extensions dir | Orchestrator process spawn timestamp | Automation extension `ready` plus product extension activation complete if applicable | `scenario.wallclock` | VS Code launched, automation extension connected, product extension loaded or remained lazy as expected | VS Code startup marks, product activation, extension host CPU, renderer startup. |
| `ext-normal-activation` | Warmed profile | Command or activation trigger begins | `vscode-mssql.activate.end` | `scenario.wallclock`, `extension.activate` | Activation event, no activation error, STS not started unless expected | Code loading, activation handler, contribution processing, STS spawn if triggered. |
| `connect-local-container` | Warmed profile | Before connection command | Object Explorer root connected marker | `scenario.wallclock` | Connected profile exists, server version read, OE root shown | Extension command, STS spawn, JSON-RPC transit, connection open, login, SQL Server response. |
| `query-10k-results` | Warmed profile, connected | Before run query command | Results grid render complete and row count verified | `scenario.wallclock` | 10000 rows fetched and rendered, no grid error, UI responsive probe passes | STS query, SqlClient, server duration, row transfer, webview data receive, grid build, paint. |
| `expand-tables-node` | Warmed profile, connected, OE visible | Before expand Tables node action | Tables child count rendered in OE | `scenario.wallclock` | Expected table count and labels visible in tree model | STS Object Explorer, SMO enumeration, SqlClient calls, extension tree update, renderer tree paint. |
| `mcp-server-first-request` | Warmed profile with MCP enabled | Before command that starts MCP operation | First MCP response consumed by extension | `scenario.wallclock` | MCP PID reported, request succeeded, output accepted | MCP process startup, RPC/stdio/http, extension request handling, downstream STS if any. |

## 9. Control plane

The orchestrator starts a local control server before launching VS Code.

Launch environment variables:

```text
PERF_MODE=1
PERF_RUN_ID=<runId>
PERF_REP_ID=<repId>
PERF_SCENARIO_ID=<scenarioId>
PERF_CONTROL_URL=ws://127.0.0.1:<port>/control
PERF_CONTROL_TOKEN=<random-128-bit-token>
PERF_MARKER_URL=http://127.0.0.1:<port>/v1/markers
PERF_OTLP_ENDPOINT=http://127.0.0.1:<otlpPort>
PERF_TRACEPARENT=<root-traceparent>
PERF_TRACESTATE=<optional>
PERF_ARTIFACT_DIR=<absolute-rep-dir>
```

The automation extension connects to `PERF_CONTROL_URL` during activation. It must send `hello` and then `ready`. Product extension and STS may either send markers directly to `PERF_MARKER_URL` or hand them to the automation extension, but direct send is preferred because it avoids losing markers if the automation extension crashes.

### 9.1 Control message types

```ts
type ControlMessage =
  | HelloMessage
  | ReadyMessage
  | StartScenarioMessage
  | ScenarioStartedMessage
  | MarkerMessage
  | ProcessDiscoveredMessage
  | ScenarioCompletedMessage
  | ScenarioFailedMessage
  | ArtifactHintMessage
  | ShutdownMessage
  | HeartbeatMessage;
```

Minimum fields for every control message:

```jsonc
{
  "schemaVersion": 1,
  "kind": "marker",
  "runId": "2026-06-29T22-00-00Z_abcd1234",
  "repId": 1,
  "scenarioId": "query-10k-results",
  "timestampUnixNs": "1782770400123456789",
  "sender": {
    "role": "automationExtension",
    "pid": 12345,
    "name": "mssql-perf-driver"
  },
  "payload": {}
}
```

### 9.2 Lifecycle

1. Orchestrator starts control server and marker sink.
2. Orchestrator launches VS Code with environment variables and configured args.
3. Automation extension connects and sends `hello`.
4. Automation extension runs basic environment checks and sends `ready`.
5. Product extension sends `mssql.extension.loaded` if active.
6. Orchestrator waits for readiness criteria for the scenario.
7. Orchestrator sends `startScenario`.
8. Automation extension emits `scenario.start`, executes steps, and emits `scenario.end`.
9. Automation extension sends `scenarioCompleted` or `scenarioFailed`.
10. Orchestrator sends `shutdown` and asks VS Code to close gracefully.
11. Orchestrator closes collectors, normalizes artifacts, writes result and store rows.

### 9.3 Control-plane failure policy

| Failure | Result status | Action |
|---|---|---|
| Automation extension never connects | `invalid` | Stop VS Code, retain logs, do not compare. |
| Product extension activation fails | `failed` | Retain logs, compare only failure rate, not timing. |
| Scenario timeout | `failed` | Retain diagnostic artifacts if configured. |
| Collector attach failure in measurement pass | `valid` if official markers exist | Record validation warning. |
| Official start or end marker missing | `invalid` | Do not compare. |
| Success probe mismatch | `failed` | Timing exists but not eligible for regression. |

## 10. Marker contract

Markers are append-only semantic events. They are the lowest-overhead and most durable measurement signal.

Marker schema summary:

```jsonc
{
  "schemaVersion": 1,
  "runId": "...",
  "repId": 1,
  "scenarioId": "query-10k-results",
  "name": "mssql.query.submit",
  "phase": "instant",                  // instant | begin | end | counter
  "timestampUnixNs": "1782770400123456789",
  "monotonicNs": "123456789",
  "traceId": "0af7651916cd43dd8448eb211c80319c",
  "spanId": "b7ad6b7169203331",
  "process": {
    "role": "extensionHost",           // orchestrator | vscodeMain | renderer | extensionHost | webview | sts | sqlserver | mcp | child
    "pid": 1111,
    "name": "vscode-mssql"
  },
  "thread": { "id": "main", "name": "main" },
  "attrs": {
    "command": "mssql.runQuery",
    "rowCount": 10000
  }
}
```

Rules:

- `scenario.start` and `scenario.end` are required for every valid rep.
- Markers must be line-delimited JSON in `markers.jsonl`.
- Marker writes must never block the product critical path. Use bounded queue plus best-effort flush.
- In measurement mode, markers are mandatory and heavy collectors are not.
- A marker can represent a duration using `phase=begin/end` with the same `name` and `correlationId`.
- A marker can represent a counter using `phase=counter` and `attrs.value`.
- Every marker should carry `traceId` when available.
- Webview marks use epoch timestamp computed from `performance.timeOrigin + performance.now()`.
- .NET durations should use `Stopwatch.GetTimestamp()` internally, with epoch timestamp only for correlation.

## 11. Time and identity model

### 11.1 Run identity

- `runId`: globally unique, human-sortable, generated once per invocation.
- `repId`: integer repetition index within a run and scenario.
- `scenarioId`: stable scenario key.
- `attemptId`: optional ID for retry attempts. Retries should not overwrite original failed attempts.
- `traceId`: W3C trace ID used to correlate spans and markers for one rep.
- `environmentHash`: stable hash of hardware, OS, VS Code version, extension versions, STS version, SQL image digest, SQL seed, config knobs, and pass type.

### 11.2 Timestamp strategy

Use two timing planes:

1. Official wall-clock plane: orchestrator timestamps and required markers. This is used for official scenario timing.
2. Diagnostic trace plane: OTel spans, CDP traces, ETW, EventPipe, XEvents, and profiles. This is used for explanation.

Use epoch nanoseconds for cross-process event ordering, but compute process-local durations from monotonic clocks or span durations. Do not subtract arbitrary monotonic timestamps from different processes.

### 11.3 Clock calibration

At connection time, the control server performs a ping/pong calibration with the automation extension:

```text
orchestrator send t0
extension receive e1 and send e2
orchestrator receive t3
estimated offset = ((t0 + t3) / 2) - e2
round trip = t3 - t0
```

Store the offset and round-trip in `environment.json` and `result.json.validations`. Do not attempt sub-millisecond cross-process claims if calibration jitter is high.

## 12. Measurement, diagnostic, and calibration passes

### 12.1 Pass types

| Pass type | Purpose | Allowed official metrics | Default collectors |
|---|---|---|---|
| `measurement` | Regression-tracking numbers | Markers, explicit product timers, minimal resource sampler | markers, processSampler, optional minimal OTel, SQL XEvents if low overhead validated. |
| `diagnostic` | Investigation and explanation | None by default, unless explicitly labeled non-official | markers, full OTel, CDP tracing/profiles, dotnet-counters, dotnet-trace, ETW, SQL XEvents, logs. |
| `calibration` | Measure collector overhead and machine noise | Calibration metrics only | Runs A/B with collectors on and off. |

### 12.2 Official metric rules

A metric is official only if:

- It comes from a measurement pass.
- Its source is listed in the scenario definition as official.
- The rep status is `valid` or `passed`.
- All required success criteria passed.
- All required environment validations passed or were explicitly waived.
- The metric source declared its overhead class as `low`.

A metric is not official if it came from:

- ETW/WPR.
- CPU profiles.
- Renderer CDP tracing.
- `dotnet-trace`.
- Heap snapshots.
- GC dumps.
- SQL text capture that modifies query execution behavior.

### 12.3 Collector overhead calibration

Every collector must have an overhead entry:

```jsonc
{
  "collector": "sqlServerXEvents",
  "scenarioId": "query-10k-results",
  "samples": 20,
  "overheadPctP50": 0.8,
  "overheadPctP95": 1.6,
  "approvedForMeasurement": true,
  "approvedBy": "perf-owner",
  "date": "2026-06-29"
}
```

If a collector has not been calibrated, it is diagnostic-only.

## 13. Launch and environment design

### 13.1 VS Code launch strategy

Use `@vscode/test-electron` to acquire and resolve a pinned VS Code build, then spawn the executable directly so the orchestrator owns the PID, stdout/stderr, environment, and shutdown.

Base launch args:

```text
--user-data-dir <repDir>/vscode-user-data
--extensions-dir <repDir>/vscode-extensions
--new-window
--wait
--skip-welcome
--disable-workspace-trust
--disable-updates
--crash-reporter-directory <repDir>/artifacts/vscode-crashes
<workspacePath>
```

Notes:

- Use a fresh `--extensions-dir` containing only `vscode-mssql` and `mssql-perf-driver`, or use extension development paths if that is how the product build is tested.
- Do not use `--disable-extensions` unless the launcher explicitly re-enables the product and driver extensions through a supported route. A fresh extensions dir is safer.
- Capture `code --status` after launch when possible, but treat it as diagnostic text, not official measurement data.
- Use `--prof-startup` only when the startup profile collector is enabled.
- Add CDP/inspector flags only in diagnostic passes unless a calibration says they are safe.
- Probe each launch flag on the target VS Code version. Some debug flags are not part of the stable public CLI surface.

### 13.2 VS Code profile modes

| Mode | User data dir | Extensions dir | Use cases |
|---|---|---|---|
| `fresh` | New per rep | New per rep | First launch, install/first activation tests. |
| `warmed` | Created once during scenario setup, then copied or reused | Stable minimal extensions | Normal activation, query, OE tests. |
| `reuse` | Same across reps | Same across reps | Only for exploratory diagnostics, not official regression. |

### 13.3 Machine isolation

Preflight checks:

- CPU model, core count, logical processor count.
- Power mode and frequency policy.
- Thermal throttling if available.
- Battery vs AC.
- Free memory and disk space.
- Background CPU over idle window.
- Docker availability and SQL container health.
- Admin/elevated status for ETW if requested.
- Required global tools installed.
- VS Code version resolved and matches config.
- Git repo SHA and dirty state.

A strict run fails preflight if `environment.requireIdle=true` and the machine is not idle.

### 13.4 SQL container strategy

Use Docker Compose or Testcontainers. Pin SQL Server image by digest, not floating tag.

Each measurement rep should start from a known database state. Recommended options, in order:

1. Restore a `.bak` snapshot before each rep.
2. Recreate database from deterministic SQL scripts.
3. Recreate the entire container for highly stateful scenarios.
4. Reuse database only for exploratory diagnostics.

Record cache mode:

- `warm`: run warmup queries before measured scenario.
- `coldDb`: restart SQL Server container or clear SQL buffers when supported and acceptable.
- `coldOs`: only on dedicated machines where OS cache control is possible.
- `unknown`: invalid for official cold-start comparisons.

## 14. Collector framework

### 14.1 Collector interface

```ts
export interface Collector {
  readonly name: string;
  readonly cost: "low" | "medium" | "high";
  readonly platforms: Array<"win32" | "linux" | "darwin" | "all">;
  readonly allowedPassTypes: Array<"measurement" | "diagnostic" | "calibration">;

  validate?(ctx: CollectorContext): Promise<ValidationResult[]>;
  preProvision?(ctx: CollectorContext): Promise<void>;
  preLaunch?(ctx: CollectorContext, launch: MutableLaunchSpec): Promise<void>;
  postLaunch?(ctx: CollectorContext, processes: ProcessRegistry): Promise<void>;
  onProcessDiscovered?(ctx: CollectorContext, process: PerfProcess): Promise<void>;
  onScenarioStart?(ctx: CollectorContext, marker: Marker): Promise<void>;
  onScenarioEnd?(ctx: CollectorContext, marker: Marker): Promise<void>;
  preShutdown?(ctx: CollectorContext): Promise<void>;
  postExit?(ctx: CollectorContext): Promise<Artifact[]>;
  normalize?(ctx: CollectorContext): Promise<NormalizedMetric[]>;
  teardown?(ctx: CollectorContext): Promise<void>;
}
```

### 14.2 Collector lifecycle

```text
preProvision
  create rep dir
  start marker sink
  start optional OTLP receiver
preLaunch
  amend env and launch args
  start pre-target collectors such as WPR
launch
postLaunch
  discover process tree
  attach CDP and EventPipe collectors
scenarioStart
  start scenario-window collectors
scenarioEnd
  stop scenario-window collectors
preShutdown
  flush in-process telemetry
postExit
  stop process-lifetime collectors
  collect artifacts
normalize
  parse artifacts into metrics
teardown
  cleanup temp state
```

### 14.3 Collector catalog

| Collector | Pass | Cost | Platform | Start | Output | Official? | Notes |
|---|---|---|---|---|---|---|---|
| `markers` | measurement, diagnostic | low | all | prelaunch | `markers.jsonl` | yes | Required. |
| `processSampler` | measurement, diagnostic | low | all | postlaunch | `process-samples.jsonl` | resource only | Samples CPU, RSS, child pids. |
| `otelMinimal` | measurement | low after calibration | all | prelaunch | `spans-minimal.otlp.json` | optional | Only root and component spans. No high-cardinality tags. |
| `otelFull` | diagnostic | medium | all | prelaunch | `spans.otlp.json` | no | Full span attributes and child spans. |
| `startupProfile` | diagnostic | low-medium | all | launch flag | `startup/*.cpuprofile` | no | Use for first-launch explanation. |
| `cdpExtHostProfile` | diagnostic | medium | all | postlaunch | `exthost.cpuprofile` | no | V8 CPU profile. |
| `cdpRendererTrace` | diagnostic | medium | all | scenario window | `renderer-trace.json` | no | Paint, layout, scripting, webview iframe. |
| `cdpRendererProfile` | diagnostic | medium | all | scenario window | `renderer.cpuprofile` | no | Renderer JavaScript CPU profile. |
| `dotnetCounters` | measurement after calibration, diagnostic | low-medium | all | STS pid discovered | `sts-counters.csv` | resource only | GC, threadpool, SqlClient counters. |
| `dotnetTrace` | diagnostic | medium-high | all | STS pid discovered | `sts.nettrace` or `sts.speedscope.json` | no | EventPipe trace. |
| `gcDump` | diagnostic | high | all | on demand | `sts.gcdump` | no | Heap investigation. |
| `heapSnapshot` | diagnostic | high | all | CDP attach | `*.heapsnapshot` | no | JS heap. |
| `sqlServerXEvents` | measurement after calibration, diagnostic | low | all | scenario window | `sql-xevents.json` | derived only | Server duration, reads, row count. |
| `sqlStatistics` | diagnostic | low-medium | all | query-specific | `sql-statistics.json` | no | Fallback for selected query scenarios. |
| `vscodeDiag` | diagnostic | low | all | launch/post | `vscode-logs/`, `status.txt` | no | Logs and status. |
| `wprEtw` | diagnostic | high | Windows admin | prelaunch | `trace.etl` | no | System CPU, disk, network, CLR, SqlClient. |
| `linuxPerf` | diagnostic | high | Linux | prelaunch | `perf.data` | no | Future Linux system profiling. |
| `childProcessRegistry` | measurement, diagnostic | low | all | postlaunch | `process-registry.json` | metadata | STS, MCP, helper processes. |

## 15. Process registry

Every process that matters gets a stable role.

```jsonc
{
  "role": "sts",
  "pid": 23456,
  "ppid": 12345,
  "name": "MicrosoftSqlToolsServiceLayer",
  "commandLine": "...",
  "startTimeUnixNs": "...",
  "reportedBy": "vscode-mssql",
  "discoveryMethods": ["marker", "processTree"],
  "version": "5.0.0-dev",
  "otelServiceName": "sqltoolsservice"
}
```

Roles:

- `orchestrator`
- `vscodeMain`
- `renderer`
- `extensionHost`
- `webview`
- `sts`
- `sqlserver`
- `mcp`
- `languageServer`
- `debugAdapter`
- `child`

Discovery order:

1. Self-report marker from product extension or child process.
2. Process tree walk from VS Code main PID.
3. Command-line classification.
4. Port or pipe ownership.
5. Fallback user-supplied mapping.

Self-reporting beats process-tree heuristics.

## 16. Automation extension design

The automation extension is the test driver's hand inside VS Code. It owns scenario execution, semantic probes, and communication with the orchestrator.

### 16.1 Responsibilities

- Connect to the control server and authenticate.
- Emit `automation.ready` when it can receive scenario commands.
- Execute scenario steps using VS Code APIs and product commands.
- Avoid pixel clicking where command/API execution is sufficient.
- Drive webview probes by message passing.
- Validate success criteria.
- Report child process PIDs received from `vscode-mssql`.
- Request graceful VS Code shutdown when the orchestrator asks.

### 16.2 Scenario step library

| Step type | Implementation |
|---|---|
| `command` | `vscode.commands.executeCommand(command, ...args)` with timing markers. |
| `openDocument` | `vscode.workspace.openTextDocument` and `vscode.window.showTextDocument`. |
| `waitForMarker` | Resolved by control server marker stream. |
| `waitForCommandCompletion` | Wrap command promise or product callback. |
| `webviewProbe` | Send probe message to webview and wait for response. |
| `objectExplorerProbe` | Ask product extension for OE model state through perf-only API. |
| `statusBarProbe` | Query VS Code-visible state if stable. |
| `uiClick` | Diagnostic fallback only, via VS Code test tooling or Playwright when no semantic hook exists. |
| `sleep` | Forbidden in official scenario action except with waiver. Use semantic waits. |

### 16.3 Product-private perf API

Expose a perf-only API from `vscode-mssql` when `PERF_MODE=1`:

```ts
export interface MssqlPerfApi {
  getActivationState(): Promise<ActivationState>;
  getStsProcessInfo(): Promise<ChildProcessInfo | undefined>;
  getMcpProcessInfo(): Promise<ChildProcessInfo | undefined>;
  getObjectExplorerSnapshot(): Promise<ObjectExplorerSnapshot>;
  getConnectionState(profileId: string): Promise<ConnectionState>;
  getResultsGridState(panelId?: string): Promise<ResultsGridState>;
  subscribePerfEvents(listener: (event: PerfEvent) => void): Disposable;
}
```

This API is not shipped as a public extension API. It is guarded by `PERF_MODE` and internal typings.

## 17. `vscode-mssql` instrumentation design

### 17.1 Gating

Instrumentation is guarded by environment and config:

```text
PERF_MODE=1
PERF_MARKERS_ENABLED=1
PERF_OTEL_MODE=off|minimal|full
PERF_CAPTURE_SQL_TEXT=0|1
PERF_CAPTURE_RESULT_DATA=0|1
```

Default outside perf mode: no exporter, no control connection, no SQL text capture, no extra product API.

### 17.2 Marker points

Required product markers:

| Marker | When |
|---|---|
| `mssql.extension.load.begin` | Top of extension module load if possible. |
| `mssql.activate.begin` | First line of `activate()`. |
| `mssql.activate.end` | Last awaited line of `activate()`. |
| `mssql.command.begin` | Around each tested command. |
| `mssql.command.end` | Command promise resolved. |
| `mssql.sts.spawn.begin` | Before STS process start. |
| `mssql.sts.spawn.end` | STS process created, pid known. |
| `mssql.sts.ready` | STS ready to accept RPC. |
| `mssql.mcp.spawn.begin` | Before MCP process start. |
| `mssql.mcp.spawn.end` | MCP process created, pid known. |
| `mssql.connection.begin` | Connection flow starts. |
| `mssql.connection.ready` | Product considers connection ready. |
| `mssql.query.submit` | Query request sent. |
| `mssql.query.firstRow` | First row available to extension if observable. |
| `mssql.query.allRows` | All rows fetched. |
| `mssql.resultsGrid.dataPosted` | Data posted to webview. |
| `mssql.resultsGrid.renderComplete` | Webview reports render complete. |
| `mssql.oe.expand.begin` | Object Explorer expand action begins. |
| `mssql.oe.expand.end` | Tree model updated and rendered. |

### 17.3 OpenTelemetry spans

Activity/span naming convention:

```text
mssql.activate
mssql.command.<commandId>
mssql.connection.open
mssql.query.execute
mssql.query.fetchRows
mssql.resultsGrid.render
mssql.objectExplorer.expand
mssql.rpc.request.<method>
mssql.mcp.request.<method>
```

Required span attributes:

```text
perf.run_id
perf.rep_id
perf.scenario_id
perf.pass_type
vscode.version
extension.version
rpc.method
rpc.request_id
process.role
process.pid
component
```

Avoid high-cardinality or sensitive attributes in measurement mode. SQL text is off unless the perf config explicitly enables it for a synthetic perf database.

### 17.4 JSON-RPC trace propagation to STS

Preferred strategy:

- The TypeScript side creates or reads the current W3C trace context.
- For every outgoing JSON-RPC request or notification to STS, stamp `traceparent` and optional `tracestate` on the JSON-RPC request object if the RPC library permits extra properties.
- STS uses StreamJsonRpc `ActivityTracingStrategy` or equivalent to extract trace context and create server-side activities.

Fallback strategy:

- If the TypeScript JSON-RPC library strips extra properties, wrap perf metadata in a method-specific metadata envelope for perf mode only, or send a `$ /perfTraceContext` notification immediately before the request with the same RPC request ID.
- Store `rpc.request_id` on both client and server spans so the normalizer can correlate even if parent-child trace context fails.

Validation test:

1. Start a scenario with known `traceId`.
2. Product extension sends a test JSON-RPC request to STS.
3. STS emits `sts.rpc.request.begin` with the same `traceId` and parent ID matching the client span.
4. Normalizer fails validation if the waterfall is disconnected.

### 17.5 Webview timing

Inside results-grid and other perf-sensitive webviews:

```ts
function mark(name: string, attrs: Record<string, unknown> = {}) {
  const now = performance.now();
  const timestampUnixNs = BigInt(Math.round((performance.timeOrigin + now) * 1_000_000));
  performance.mark(name);
  vscode.postMessage({
    kind: "perf.webviewMark",
    name,
    timestampUnixNs: timestampUnixNs.toString(),
    monotonicNs: BigInt(Math.round(now * 1_000_000)).toString(),
    attrs
  });
}

async function afterNextPaint() {
  await new Promise(requestAnimationFrame);
  await new Promise(requestAnimationFrame);
}
```

Recommended webview marks:

| Mark | Meaning |
|---|---|
| `webview.init` | Script initialized. |
| `webview.data.received` | Data message received from extension. |
| `webview.grid.modelBuilt` | Data transformed into grid model. |
| `webview.grid.domCommitted` | DOM update committed. |
| `webview.grid.firstPaintAfterData` | Two animation frames after DOM commit. |
| `webview.grid.renderComplete` | Product-defined render completion. |
| `webview.longTask` | PerformanceObserver long task, if available. |

## 18. STS instrumentation design

### 18.1 Activity sources

Use one root source plus subsystem sources:

```csharp
internal static class PerfActivitySources
{
    public static readonly ActivitySource Rpc = new("Microsoft.SqlToolsService.Rpc");
    public static readonly ActivitySource Connection = new("Microsoft.SqlToolsService.Connection");
    public static readonly ActivitySource Query = new("Microsoft.SqlToolsService.Query");
    public static readonly ActivitySource ObjectExplorer = new("Microsoft.SqlToolsService.ObjectExplorer");
    public static readonly ActivitySource Smo = new("Microsoft.SqlToolsService.Smo");
    public static readonly ActivitySource DacFx = new("Microsoft.SqlToolsService.DacFx");
    public static readonly ActivitySource Scripting = new("Microsoft.SqlToolsService.Scripting");
    public static readonly ActivitySource Mcp = new("Microsoft.SqlToolsService.Mcp");
}
```

### 18.2 JSON-RPC handler wrapper

Every request handler should create a root handler span:

```csharp
using var activity = PerfActivitySources.Rpc.StartActivity(
    $"sts.rpc.{methodName}",
    ActivityKind.Server);

activity?.SetTag("rpc.system", "jsonrpc");
activity?.SetTag("rpc.method", methodName);
activity?.SetTag("rpc.request_id", requestId);
activity?.SetTag("perf.run_id", perfContext.RunId);
activity?.SetTag("perf.rep_id", perfContext.RepId);
activity?.SetTag("perf.scenario_id", perfContext.ScenarioId);
```

### 18.3 StreamJsonRpc trace context

Set the JSON-RPC activity tracing strategy at construction time. The exact class name must be confirmed against the STS StreamJsonRpc package version during implementation.

```csharp
var jsonRpc = new JsonRpc(messageHandler, target);
jsonRpc.ActivityTracingStrategy = new ActivityTracingStrategy();
jsonRpc.StartListening();
```

Acceptance test: an inbound request with `traceparent` must produce a server Activity with that parent.

### 18.4 SqlClient spans and counters

- Enable OpenTelemetry SqlClient instrumentation for spans in perf mode.
- Enable Microsoft.Data.SqlClient EventSource counters in diagnostic or calibrated measurement mode.
- Include connection pool counters from `dotnet-counters` where useful.
- Do not include raw connection strings in span tags.
- Redact server, user, and database names unless the perf config classifies them as synthetic.

### 18.5 SMO and DacFX wrappers

SMO and DacFX can hide many SQL operations behind one product action. Wrap the product calls explicitly.

Recommended spans:

```text
sts.smo.server.refresh
sts.smo.database.refresh
sts.smo.objectExplorer.enumerate
sts.smo.scripter.script
sts.dacfx.deploy
sts.dacfx.extract
sts.dacfx.export
sts.dacfx.import
```

Recommended tags:

```text
smo.object_type
smo.object_count
dacfx.operation
dacfx.package_size_bytes
sql.database.synthetic_name
perf.query_shape
```

### 18.6 STS EventSource

Create an STS EventSource for low-level diagnostic events:

```text
STS-Perf/RpcRequestStart
STS-Perf/RpcRequestStop
STS-Perf/QueueDepth
STS-Perf/ConnectionPoolAcquireStart
STS-Perf/ConnectionPoolAcquireStop
STS-Perf/BindingQueueEnqueue
STS-Perf/BindingQueueDequeue
STS-Perf/ObjectExplorerEnumerationStart
STS-Perf/ObjectExplorerEnumerationStop
```

This gives ETW/EventPipe diagnostic phase information without requiring those events to be official metrics.

### 18.7 STS process self-report

STS should emit a startup marker to the marker sink if `PERF_MARKER_URL` exists:

```jsonc
{
  "name": "sts.process.ready",
  "phase": "instant",
  "process": { "role": "sts", "pid": 23456, "name": "MicrosoftSqlToolsServiceLayer" },
  "attrs": {
    "version": "5.0.0-dev",
    "dotnetRuntime": ".NET 8.0.12",
    "architecture": "x64"
  }
}
```

## 19. SQL Server collector design

### 19.1 Primary approach: Extended Events

Create an Extended Events session scoped to perf runs. Use an event file target mounted out of the container.

Events to consider:

```sql
sqlserver.rpc_completed
sqlserver.sql_batch_completed
sqlserver.sql_statement_completed
sqlserver.attention
sqlserver.error_reported
```

Actions:

```sql
sqlserver.client_app_name
sqlserver.client_hostname
sqlserver.database_name
sqlserver.session_id
sqlserver.sql_text               -- only when configured
sqlserver.query_hash
sqlserver.plan_handle            -- diagnostic only
```

Recommended connection string additions for perf runs:

```text
Application Name=vscode-mssql-perf;<runId>;<scenarioId>;<repId>
```

Recommended session context after opening a connection:

```sql
EXEC sys.sp_set_session_context @key = N'perf_run_id', @value = @RunId;
EXEC sys.sp_set_session_context @key = N'perf_rep_id', @value = @RepId;
EXEC sys.sp_set_session_context @key = N'perf_scenario_id', @value = @ScenarioId;
```

If session context is not easy to retrieve from the selected XEvent, use `client_app_name` and a narrow scenario time window.

### 19.2 Matching SQL events to client spans

Match in this order:

1. `runId`, `repId`, `scenarioId` in client app name or session context.
2. SQL connection/session ID if available from SqlClient or STS.
3. RPC method or query operation correlation ID if passed as SQL comment in synthetic perf DBs.
4. Query hash or normalized SQL hash.
5. Time-window overlap with the SqlClient span.

Store match confidence:

```jsonc
{
  "metric": "sql.server.duration",
  "source": "sqlServerXEvents",
  "matchConfidence": "high",
  "matchedEvents": 3,
  "limitations": []
}
```

### 19.3 Derived network and driver time

For matched commands:

```text
sql.networkDriver.duration.ms = max(0, sqlclient.command.duration.ms - sqlserver.duration.ms)
```

Limitations:

- The value includes client-side SqlClient work, driver overhead, serialization, deserialization, loopback networking, and any measurement mismatch.
- Multiple statements inside one command require summing matched SQL events.
- Parallel queries and async result streaming can make server duration overlap with client processing.
- Store the metric as `derived` with confidence, not as a hard physical truth.

### 19.4 Fallback: STATISTICS TIME and IO

Use `SET STATISTICS TIME, IO ON` for targeted query diagnostics or when XEvents are unavailable. Parse informational messages from SqlClient.

Do not enable it globally in official measurement until overhead and behavior changes have been calibrated.

## 20. Result contract

The v2 result contract uses one unified `metrics` array instead of separate primary, component, and resource arrays. This avoids schema drift and makes regression logic simpler.

Minimal shape:

```jsonc
{
  "schemaVersion": 2,
  "runId": "2026-06-29T22-00-00Z_abcd1234",
  "repId": 1,
  "scenarioId": "query-10k-results",
  "attemptId": 0,
  "passType": "measurement",
  "status": "passed",
  "trace": {
    "traceId": "0af7651916cd43dd8448eb211c80319c",
    "rootTraceparent": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
  },
  "git": [
    { "repo": "vscode-mssql", "sha": "abc123", "dirty": false },
    { "repo": "sqltoolsservice", "sha": "def456", "dirty": false }
  ],
  "environment": {
    "environmentHash": "sha256:...",
    "machineId": "perfbox-01",
    "os": { "platform": "win32", "version": "Windows 11 26100" },
    "cpu": { "model": "...", "logicalCores": 16, "affinity": [0,1,2,3], "turboDisabled": true },
    "vscode": { "version": "1.xx.x", "quality": "stable" },
    "sql": { "imageDigest": "sha256:...", "snapshot": "seed-v4", "cacheMode": "warm" }
  },
  "metrics": [
    {
      "name": "scenario.wallclock",
      "value": 412.7,
      "unit": "ms",
      "component": "scenario",
      "processRole": "boundary",
      "source": "marker",
      "official": true,
      "lowerIsBetter": true,
      "aggregation": "trimmedMean",
      "tags": { "scenarioGroup": "query" }
    },
    {
      "name": "sql.networkDriver.duration",
      "value": 70.0,
      "unit": "ms",
      "component": "driver",
      "processRole": "boundary",
      "source": "derived",
      "official": false,
      "lowerIsBetter": true,
      "derivation": {
        "formula": "max(0, sqlclient.command.duration - sqlserver.duration)",
        "inputs": ["sqlclient.command.duration", "sqlserver.duration"],
        "confidence": "medium"
      }
    }
  ],
  "artifacts": [
    { "kind": "markers", "path": "markers.jsonl", "retention": "always", "sizeBytes": 1234 },
    { "kind": "sqlXEvents", "path": "artifacts/sql/sql-xevents.json", "retention": "on-regression" }
  ],
  "validations": [
    { "name": "requiredMarkersPresent", "status": "passed" },
    { "name": "traceContextConnected", "status": "passed" },
    { "name": "machineIdle", "status": "passed" }
  ],
  "errors": []
}
```

See `schemas/perf-result.schema.json` for a standalone draft schema.

## 21. Metric naming conventions

Use dot-separated lower camel case names.

Pattern:

```text
<domain>.<area>.<operation>[.<phase>]
```

Examples:

```text
scenario.wallclock
vscode.startup.ready
extension.activate.duration
extension.command.duration
rpc.request.duration
rpc.transit.duration
sts.rpc.handler.duration
sts.objectExplorer.enumerate.duration
sts.smo.duration
sts.dacfx.duration
sqlclient.command.duration
sqlserver.duration
sqlserver.logicalReads
sql.networkDriver.duration
webview.resultsGrid.dataToRender.duration
webview.resultsGrid.firstPaint.duration
process.cpuTime
process.peakWorkingSet
```

Required fields for every metric:

- `name`
- `value`
- `unit`
- `component`
- `processRole`
- `source`
- `official`
- `lowerIsBetter`

Recommended fields:

- `spanId`
- `traceId`
- `startUnixNs`
- `endUnixNs`
- `tags`
- `derivation`
- `confidence`

## 22. Output layout

```text
perf-runs/
  <runId>/
    run-config.snapshot.json
    environment.json
    summary.json
    comparison.json
    report.md
    report.html
    artifacts-index.json
    scenarios/
      <scenarioId>/
        scenario-summary.json
        reps/
          rep-00/
            result.json
            markers.jsonl
            process-registry.json
            process-samples.jsonl
            spans-minimal.otlp.json
            artifacts/
              vscode-logs/
              startup/
              cdp/
              dotnet-counters/
              dotnet-trace/
              sql/
              etw/
              heap/
          rep-01/
          rep-02/
```

Artifact paths in `result.json` are relative to the rep directory. Reports use relative links so the entire run folder can be zipped or copied.

## 23. Local store design

SQLite is the default local store. Raw artifacts remain on disk.

Core tables:

- `runs`
- `run_repositories`
- `environments`
- `scenarios`
- `repetitions`
- `metrics`
- `artifacts`
- `validations`
- `baselines`
- `comparisons`
- `comparison_metrics`

See `sql/perf-store.schema.sql` for a complete starter schema.

### 23.1 Environment hash

The environment hash should include:

- OS platform/version/build.
- CPU model, core count, affinity, turbo/frequency settings.
- Memory size.
- VS Code version and quality.
- Electron/Chromium version when available.
- Node version used by extension host when available.
- Product extension version and SHA.
- STS version and SHA.
- SQL Server image digest.
- SQL snapshot ID.
- Scenario config hash.
- Pass type.

Do not compare official metrics across different environment hashes unless config explicitly allows cross-environment comparison.

## 24. Aggregation and regression design

### 24.1 Aggregation

Default:

- `warmupRepetitions`: 1.
- `measurementRepetitions`: 10 for local perf boxes, 5 minimum for smoke runs.
- Aggregation: 20 percent trimmed mean when samples >= 10, otherwise median.
- Always report all samples, mean, median, min, max, standard deviation, coefficient of variation, p90, p95, and 95 percent confidence interval.

### 24.2 Invalid-run rules

Mark a rep invalid if:

- Required markers are missing.
- Success criteria fail.
- Scenario times out.
- VS Code or STS crashes.
- Machine idle validation fails in strict mode.
- SQL snapshot restore fails.
- Environment fingerprint is incomplete.
- Trace context validation is required and fails.

Invalid reps are shown in reports but excluded from regression metrics.

### 24.3 Regression comparison

For each metric key:

```text
metricKey = scenarioId + metric.name + component + processRole + unit + tags subset
```

Comparison algorithm:

1. Resolve baseline by explicit run ID, named baseline, or latest green run on branch.
2. Require matching environment hash unless cross-environment comparison is allowed.
3. Drop warmups and invalid reps.
4. Require minimum sample size.
5. Compute current and baseline aggregate.
6. Compute percent delta and absolute delta.
7. Apply thresholds: percent, absolute floor, and optional statistical test.
8. Mark `regressed`, `improved`, `unchanged`, or `inconclusive`.
9. Fail process exit if any gated official metric regresses.

Threshold example:

```jsonc
{
  "default": {
    "pct": 10,
    "absMs": 5,
    "minSamples": 5,
    "maxCv": 0.20,
    "test": "welchT",
    "pValue": 0.05
  },
  "metrics": {
    "scenario.wallclock": { "pct": 8, "absMs": 20 },
    "webview.resultsGrid.firstPaint.duration": { "pct": 15, "absMs": 10 },
    "sts.objectExplorer.enumerate.duration": { "pct": 10, "absMs": 10 }
  }
}
```

### 24.4 Bencher and central trend

Local SQLite is sufficient for phase 1. For central infrastructure, export each official metric as a benchmark measure. Use dimensions equivalent to branch, testbed, scenario, metric name, and environment hash.

## 25. Config contract

Example measurement config:

```jsonc
{
  "schemaVersion": 2,
  "runId": "auto",
  "passType": "measurement",
  "repetitions": 10,
  "warmupRepetitions": 1,
  "scenarios": [
    "ext-normal-activation",
    "connect-local-container",
    "query-10k-results",
    "expand-tables-node"
  ],
  "vscode": {
    "version": "stable",
    "quality": "stable",
    "launchMode": "directSpawn",
    "profileMode": "scenarioDefault",
    "workspaceRoot": "./workspaces/perf",
    "extensions": [
      { "id": "ms-mssql.mssql", "source": "vsix", "path": "./artifacts/vscode-mssql.vsix" },
      { "id": "mssql-perf-driver", "source": "developmentPath", "path": "./extensions/mssql-perf-driver" }
    ],
    "extraArgs": ["--disable-workspace-trust"],
    "env": {}
  },
  "sql": {
    "provider": "dockerCompose",
    "composeFile": "./sql/docker-compose.sqlserver.yml",
    "service": "sqlserver",
    "imageDigest": "sha256:REPLACE_WITH_PINNED_DIGEST",
    "snapshot": "seed-v4",
    "cacheMode": "warm",
    "connectionProfile": "local-container"
  },
  "environment": {
    "requireIdle": true,
    "idleCpuPctMax": 5,
    "pinCpuAffinity": [0, 1, 2, 3],
    "requireAcPower": true,
    "fixCpuFrequency": "warn"
  },
  "diagnostics": {
    "markers": true,
    "processSampler": true,
    "otel": "minimal",
    "sqlServerXEvents": true,
    "startupProfile": false,
    "cdp": { "extHostProfile": false, "rendererTrace": false, "rendererProfile": false },
    "dotnetCounters": true,
    "dotnetTrace": false,
    "wprEtw": false,
    "vscodeDiag": { "logs": true, "status": true }
  },
  "store": {
    "type": "sqlite",
    "path": "./perf.db"
  },
  "regression": {
    "baseline": "main-latest-matching-env",
    "failOnRegression": true,
    "thresholds": {
      "default": { "pct": 10, "absMs": 5, "test": "welchT", "minSamples": 5 }
    }
  },
  "output": {
    "dir": "./perf-runs",
    "keepArtifacts": "on-regression"
  }
}
```

See `schemas/perf-config.schema.json` for a standalone draft schema.

## 26. CLI design

```text
perftest doctor --config <config>
perftest setup verify --config <config>
perftest run --config <config> [--scenario <id>] [--pass measurement|diagnostic]
perftest compare --current <runId> --baseline <runId|tag>
perftest baseline set <name> <runId>
perftest report <runId> [--open]
perftest serve [--db ./perf.db] [--runs ./perf-runs]
perftest collectors list
perftest scenarios list
perftest schema validate <file>
perftest cleanup --older-than 30d --keep-regressions
```

Exit codes:

| Code | Meaning |
|---|---|
| 0 | Run completed, no gated regression. |
| 1 | Gated regression found. |
| 2 | Config or schema validation failed. |
| 3 | Environment preflight failed. |
| 4 | Scenario failed. |
| 5 | Infrastructure or collector failure. |
| 6 | Insufficient valid samples. |

## 27. Reports

### 27.1 Console summary

```text
Run: 2026-06-29T22-00-00Z_abcd1234
Pass: measurement
Environment: perfbox-01 sha256:...

Scenario                 Metric                 Current      Baseline     Delta       Verdict
query-10k-results        scenario.wallclock     412.7 ms     389.1 ms     +6.1%       ok
expand-tables-node       scenario.wallclock     820.4 ms     712.0 ms     +15.2%      REGRESSED
  sts.oe.enumerate       diagnostic only        501.0 ms     390.0 ms     +28.5%      suspect

Artifacts: perf-runs/2026-06-29T22-00-00Z_abcd1234/report.html
```

### 27.2 Markdown and HTML report sections

- Run metadata.
- Environment fingerprint.
- Scenario summary table.
- Regression verdicts.
- Per-scenario charts.
- Per-rep samples.
- Component breakdown waterfall links.
- Artifact index.
- Validation warnings.
- Setup and config snapshots.
- Recommended next diagnostic command if a regression is found.

Example recommendation:

```text
Suggested follow-up:
perftest run --config examples/config.diagnostic.local.jsonc --scenario expand-tables-node --baseline 2026-06-20T10-00-00Z_main --diagnostics cdpRendererTrace,dotnetTrace,sqlServerXEvents,wprEtw
```

## 28. Setup scripts

Setup scripts should be boring and conservative. They install dependencies, validate machine settings, and print exact remediation steps when they cannot safely make changes.

### 28.1 Windows setup script responsibilities

`scripts/setup-windows.ps1` should:

- Check Windows version.
- Check PowerShell version.
- Install or validate Git.
- Install or validate Node.js LTS.
- Install or validate .NET SDK matching STS.
- Install or validate Docker Desktop or Docker Engine.
- Install `dotnet-trace`, `dotnet-counters`, and `dotnet-gcdump` as global tools.
- Validate SQL Server container can start.
- Optionally install Windows Performance Toolkit for WPR/WPA.
- Validate WPR availability if ETW diagnostics are enabled.
- Set or warn about high-performance power profile.
- Validate AC power.
- Optionally configure Defender exclusions for run/artifact directories, only with explicit user approval.
- Create `perf-runs` and local tool cache directories.
- Run `perftest doctor` and save `setup-report.json`.

It should not silently change global security settings.

### 28.2 Linux setup script responsibilities

`scripts/setup-linux.sh` should:

- Validate distro and kernel.
- Install or validate Node.js LTS.
- Install or validate .NET SDK.
- Install or validate Docker.
- Install or validate `perf` tools when Linux diagnostics are enabled.
- Check `perf_event_paranoid` and print remediation.
- Install `dotnet-trace`, `dotnet-counters`, and `dotnet-gcdump`.
- Install Xvfb or validate display if headless VS Code runs are required.
- Set CPU governor to performance only with explicit sudo action.
- Run SQL container smoke test.
- Run `perftest doctor`.

### 28.3 Setup-script acceptance output

```jsonc
{
  "status": "passed",
  "machineId": "perfbox-01",
  "checks": [
    { "name": "node", "status": "passed", "version": "22.x" },
    { "name": "dotnet", "status": "passed", "version": "8.x" },
    { "name": "docker", "status": "passed", "version": "..." },
    { "name": "sqlContainerSmoke", "status": "passed" },
    { "name": "wpr", "status": "warning", "message": "Windows Performance Toolkit not installed" }
  ]
}
```

## 29. Security and data classification

Default data classification: `synthetic-perf-data`.

Rules:

- Perf SQL databases must be synthetic and reproducible.
- SQL text capture is off by default.
- Result-set capture is off by default.
- Connection strings must be redacted before writing markers, spans, logs, result files, or SQLite rows.
- Access tokens and passwords must never be written.
- Reports should include a redaction validation result.
- Central push should reject runs marked with unknown or sensitive data classification.

Redaction fields:

```text
password
pwd
token
access_token
refresh_token
connectionString
user id
uid
serverCertificate
```

## 30. Central infrastructure path

Phase 1 is local-only. Later central infra can reuse the same contracts.

Recommended central path:

1. Use the same `result.json` and artifact layout.
2. Upload `summary.json`, `comparison.json`, and selected artifacts to object storage.
3. Push official metrics to Bencher or a Postgres metrics store.
4. Push full traces to Tempo or Jaeger only for diagnostic runs.
5. Push continuous profiles to Pyroscope only for diagnostic or long-running scenarios.
6. Render trend dashboards in Grafana.
7. Gate PRs using the same regression result JSON, not a separate algorithm.

## 31. Validation tests

### 31.1 Harness unit tests

- Config schema validation accepts examples and rejects malformed configs.
- Result schema validation accepts generated results.
- Metric aggregation handles warmups, invalid reps, and small sample counts.
- Regression engine respects percent and absolute thresholds.
- Artifact retention policy deletes only eligible artifacts.
- Redaction catches known sensitive keys.

### 31.2 Integration tests

- Launches VS Code with automation extension and receives `ready`.
- Runs a no-op scenario and produces `result.json`.
- Product extension emits activation markers in perf mode.
- STS self-reports PID.
- SQL container smoke query succeeds.
- Trace context is connected across extension to STS.
- Webview emits render marks and the extension receives them.
- Process registry finds STS and MCP child processes.

### 31.3 Calibration tests

- Run scenario with markers only.
- Run scenario with minimal OTel.
- Run scenario with SQL XEvents.
- Run scenario with dotnet-counters.
- Compute overhead relative to markers-only.
- Approve low-overhead collectors for measurement only after calibration.

## 32. Build plan

### Milestone 0 - Contracts and skeleton

Deliverables:

- `perf-contracts` TypeScript types.
- JSON schemas for config, result, marker.
- SQLite schema.
- Empty CLI with `doctor`, `run`, `report`, `schema validate`.

Acceptance:

- Example config validates.
- Example result validates.
- SQLite DB initializes.

### Milestone 1 - Smallest end-to-end loop

Deliverables:

- Orchestrator launches VS Code with fresh dirs.
- Automation extension connects and sends `ready`.
- No-op scenario executes.
- Markers written.
- `result.json` written.
- SQLite rows inserted.
- Markdown report generated.

Acceptance:

- `perftest run --scenario noop` produces a valid result with `scenario.wallclock`.

### Milestone 2 - Product command scenarios

Deliverables:

- `ext-normal-activation` scenario.
- Product activation markers.
- Command wrapper markers.
- Baseline compare.

Acceptance:

- Activation scenario produces official wall-clock and activation metrics.

### Milestone 3 - STS and trace context

Deliverables:

- STS ActivitySources.
- JSON-RPC trace context propagation.
- STS PID self-report.
- Minimal OTel collector.

Acceptance:

- A trace waterfall shows product command span parented to STS handler span.

### Milestone 4 - SQL scenarios

Deliverables:

- SQL container provisioning.
- Connection scenario.
- Query 10000 scenario.
- Object Explorer expand scenario.
- SQL XEvents collector.

Acceptance:

- Query scenario verifies 10000 rows and produces server duration and logical reads.

### Milestone 5 - Diagnostic collectors

Deliverables:

- CDP extension host profile.
- CDP renderer trace.
- dotnet-counters.
- dotnet-trace.
- WPR/ETW collector on Windows.
- Artifact links in HTML report.

Acceptance:

- Diagnostic run produces artifacts and keeps official metric labels false for heavy data.

### Milestone 6 - Regression and central-ready output

Deliverables:

- Robust baseline management.
- Comparison JSON.
- Optional Bencher export.
- Artifact retention cleanup.

Acceptance:

- A synthetic regression fails the CLI with exit code 1 and report links to artifacts.

## 33. AI coding task packets

Use these as implementation prompts for coding agents.

### Task packet 1 - Contracts

Goal: Create shared perf contracts.

Files:

- `packages/perf-contracts/src/marker.ts`
- `packages/perf-contracts/src/result.ts`
- `packages/perf-contracts/src/config.ts`
- `packages/perf-contracts/src/controlMessages.ts`
- `packages/perf-contracts/schemas/*.json`

Acceptance:

- `npm test` validates example config/result/marker.
- TypeScript exports compile with `strict: true`.
- No runtime dependency on VS Code APIs.

### Task packet 2 - Orchestrator launch and control server

Goal: Launch VS Code and control automation extension.

Files:

- `packages/perftest-cli/src/launch/resolveVscode.ts`
- `packages/perftest-cli/src/launch/spawnVscode.ts`
- `packages/perftest-cli/src/control/controlServer.ts`
- `packages/perftest-cli/src/run/runScenario.ts`

Acceptance:

- Starts local WebSocket control server with token.
- Spawns VS Code with fresh user-data and extensions dirs.
- Receives `hello` and `ready` from automation extension.
- Shuts down cleanly.

### Task packet 3 - Automation extension

Goal: Build driver extension.

Files:

- `extensions/mssql-perf-driver/src/extension.ts`
- `extensions/mssql-perf-driver/src/controlClient.ts`
- `extensions/mssql-perf-driver/src/scenarios/noop.ts`
- `extensions/mssql-perf-driver/src/scenarios/commandScenario.ts`

Acceptance:

- Connects only when `PERF_MODE=1`.
- Sends `ready`.
- Executes `noop` and command scenarios.
- Emits required markers.

### Task packet 4 - SQLite store and reports

Goal: Persist and display results.

Files:

- `packages/perftest-cli/src/store/sqliteStore.ts`
- `packages/perftest-cli/src/report/markdownReport.ts`
- `packages/perftest-cli/src/report/htmlReport.ts`
- `sql/perf-store.schema.sql`

Acceptance:

- Stores runs, reps, metrics, artifacts, validations.
- Generates report with sample table and artifact links.

### Task packet 5 - Product extension instrumentation

Goal: Add perf-mode markers and spans to `vscode-mssql`.

Files:

- product extension perf telemetry module.
- activation wrapper.
- command wrapper.
- STS/MCP child process PID report.
- JSON-RPC traceparent injection.
- webview mark bridge.

Acceptance:

- No behavior change when `PERF_MODE` is absent.
- Activation scenario emits begin/end markers.
- STS PID marker appears after spawn.
- Trace context validation passes for a test RPC.

### Task packet 6 - STS instrumentation

Goal: Add ActivitySource, EventSource, and trace context.

Files:

- STS perf context reader.
- Activity source definitions.
- JSON-RPC dispatcher wrapper.
- StreamJsonRpc trace strategy setup.
- SMO/DacFX wrappers.
- SqlClient OTel setup.

Acceptance:

- STS emits process ready marker.
- STS handler spans are parented to extension spans.
- SQL client spans appear under STS query spans.

### Task packet 7 - SQL collector

Goal: Collect server-side SQL timing.

Files:

- `sql/xevents/create-perf-session.sql`
- `sql/xevents/read-perf-session.sql`
- `packages/perftest-cli/src/collectors/sqlServerXEvents.ts`
- `packages/perftest-cli/src/normalize/sqlXEventsNormalizer.ts`

Acceptance:

- Starts and stops XEvent session for a scenario.
- Parses event file or ring buffer.
- Emits `sqlserver.duration`, `sqlserver.cpu`, `sqlserver.logicalReads`, and derived `sql.networkDriver.duration` with confidence.

### Task packet 8 - Diagnostic collectors

Goal: Add optional rich diagnostics.

Files:

- `collectors/cdpExtHostProfile.ts`
- `collectors/cdpRendererTrace.ts`
- `collectors/dotnetCounters.ts`
- `collectors/dotnetTrace.ts`
- `collectors/wprEtw.ts`

Acceptance:

- Each collector validates availability.
- Each writes artifacts under the rep directory.
- Each marks metrics as non-official.
- Missing tools produce validation warnings, not corrupt results.

## 34. Done criteria for v1 system

The system is v1-ready when:

- A clean machine can run setup and pass doctor checks.
- The no-op scenario is stable.
- The five baseline scenarios execute locally.
- Measurement pass writes valid `result.json` for each rep.
- SQLite history stores at least two runs and compares them.
- The report clearly shows current vs baseline and artifact links.
- Trace context validation passes for extension to STS.
- SQL XEvents match query scenario commands with high confidence.
- Heavy diagnostics can be enabled without changing official metric classification.
- A known injected delay produces a regression failure.
- A known missing marker produces an invalid run, not a bogus fast run.

---

# Appendix A - External references checked

These references informed the design and should be rechecked when upgrading major tool versions.

- VS Code CLI docs: `--user-data-dir`, `--extensions-dir`, `--status`, `--performance`, `--prof-startup`.
- VS Code Testing Extensions docs: integration tests run inside Extension Development Host and can use `@vscode/test-electron`.
- VS Code Webview API docs: webviews are iframe-like surfaces controlled by extensions and communicate by message passing.
- VS Code performance wiki: Startup Performance editor, performance marks, and startup profiling.
- StreamJsonRpc trace context docs: W3C trace context over JSON-RPC requests/notifications through `ActivityTracingStrategy`.
- W3C Trace Context specification: `traceparent` and `tracestate` fields.
- OpenTelemetry SqlClient instrumentation docs.
- .NET `dotnet-trace`, `dotnet-counters`, and EventPipe docs.
- Microsoft.Data.SqlClient EventSource and EventCounters docs.
- SQL Server Extended Events docs.
- SQL Server `SET STATISTICS IO` and `SET STATISTICS TIME` docs.
- Windows Performance Recorder and PerfView docs.
- Bencher threshold docs.
- Perfetto UI docs.
- Grafana Pyroscope docs.

