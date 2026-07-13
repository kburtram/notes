# 03 — Instrumentation Reference

**Updated: 2026-07-03.** The complete catalog of what is instrumented, the
naming vocabulary, gating, and recipes for adding more. Per-repo deep dives:
`perftest/docs/PRODUCT_INSTRUMENTATION.md` and
`perftest/docs/STS_INSTRUMENTATION.md`.

## 1. Extension: semantic Perf markers (`Perf` facade)

`src/perf/perfTelemetry.ts`. Markers are the **official timing vocabulary** —
begin/end pairs and instants with attrs; both the harness and the console
consume them. Non-exhaustive inventory of active families:

| Family | Markers (begin/end unless noted) | Notes |
|---|---|---|
| Activation | `mssql.activate` | plus `Perf.setActivationState` |
| Connection | `mssql.connection.connect`, `.disconnect`, `.failed` (instant, reason attr) | |
| Query | `mssql.query.submit` (instant), `mssql.query.execute`, `mssql.query.resultsRendered`, grid window fetches | resultsRendered closes the user-perceived loop |
| Object Explorer | `mssql.oe.expand`, `.refresh`, session create/close | |
| Table Designer | `mssql.tableDesigner.init` (isEdit attr; error+reason on failure), `mssql.tableDesigner.publish` | added in the designer iteration |
| Schema Designer | `mssql.schemaDesigner.init` (tableCount attr) | |
| Schema Compare | `mssql.schemaCompare.compare` (differences count) | |
| Webview lifecycle | `webview.<controller>.*` spans via controller instrumentation | reveal/init/request round-trips |
| RPC | `rpc.<method>` client-side spans (request → response) | correlated by JSON-RPC id |

Rules: attrs are metadata only (counts, booleans, reasons) — never SQL text,
names of user objects where avoidable, never secrets. Failure paths emit the
end marker with `error` + `reason` so waterfalls show *why*, not just *slow*.

## 2. STS: `StsDiag` spans (driver/service lane)

`src/Microsoft.SqlTools.Hosting/Utility/StsDiag.cs` — `SpanScope` struct
(no-op when disabled; call sites use fully-qualified
`Microsoft.SqlTools.Hosting.Utility.StsDiag.StartSpan(type, feature)` and
direct `.Complete("ok"|"error")`; it is a struct — no `?.`). Enabled only
when `STS_DIAG_URL`/`STS_DIAG_TOKEN` are inherited from the extension.
Protocol metadata ONLY.

| Span | Site | Covers |
|---|---|---|
| `sts.dispatch.<method>` | `Hosting/Protocol/MessageDispatcher.cs` | every JSON-RPC request/notification handler execution |
| `sts.sql.executeReader` | `QueryExecution/Batch.cs` | actual SqlClient reader execution per batch |
| `sts.sql.connectionOpen` | `Connection/ConnectionService.cs` | physical `SqlConnection.Open` |
| `sts.smo.expand` / `sts.smo.refresh` | `ObjectExplorer/ObjectExplorerService.cs` | SMO tree work |
| `sts.dacfx.<OperationType>` | `DacFx/DacFxService.cs` `ExecuteOperation` | export/import/extract/deploy/generate-script/plan (bacpac/dacpac family) |
| `sts.dacfx.tableDesigner.initialize/.processEdit/.publish/.generateScript/.previewReport` | `TableDesigner/TableDesignerService.cs` | DacFx DesignServices work inside the designer (initialize = the expensive model build) |
| `sts.dacfx.schemaDesigner.createSession/.generateScript/.publish` | `SchemaDesigner/SchemaDesignerService.cs` | schema model build/script/publish |

Lesson encoded here: **DacFxService ≠ all DacFx** — the designers use their
own services wrapping DacFx DesignServices, so they are instrumented at
their own seams. When adding coverage for a feature, find where the work
*actually* happens, not the service that shares its name.

## 3. Rich collection (diagnostic-only depth)

`src/diagnostics/richCollection.ts`. When enabled (setting / env
`MSSQL_COLLECT_ALL_THE_DATA=1` / self-test toggle):

- `system.rich.snapshot` metrics @2s: heapUsedMB, rssMB, event-loop delay
  histogram (incl. p95), CPU user/system deltas.
- Per-span `perf` blocks (e.g. `heapDeltaKB`) attached to DiagEvents; the
  self-test tap persists them into rep markers as `perf_*` attrs; the
  Diagnostics bottom tab renders KPIs, trends, and spans-ranked-by-heap-delta.
- Never official: reps recorded with rich collection are flagged and the
  harness/report treat them as diagnostic.

## 4. Forwarding into the harness wire

`PerfModeSink` (`src/diagnostics/sinks.ts`), active only in PERF_MODE runs:

- Legacy contract: all `perfMarker`-tagged events forward (unchanged).
- Additive: non-viewer-internal **span** events matching
  `/^(rpc\.|webview\.|sts\.)/` forward with `attrs.diag=true` +
  `durationMs`, role-mapped (`sqlToolsService`→`sts`), phase derived from
  `.begin`/`.end` suffix. This is what gives CLI waterfalls cross-process
  sublane detail instead of one "doing scenario" block.
- Import path: `importPerfRep` lifts `durationMs` attrs on forwarded instant
  markers back into real span bars (timingClass `epochAlignedDiagnostic`,
  tag `stsDiag`).
- Verified non-regressive: the official gate stayed green with forwarding
  active (harness 4/4 official).

## 5. Self-test tap

`selfTestService.ts` bridges diag → in-proc MarkerBus so scenarios can
`waitForMarker`. Exclusions/preservation: viewer-internal events never enter
the bus; `event.perf.metrics` are preserved as `perf_<k>` attrs +
`durationMs` so the persisted rep keeps rich data.

## 6. Recipes

**New extension feature instrumentation**
1. Add begin/end markers via `Perf` at the user-meaningful boundaries
   (init, publish, compare…), attrs = counts/flags/failure reason.
2. Failure path: end marker with `error` + `reason` (never swallow).
3. If a webview is involved, the controller's rpc/webview spans come free —
   check they correlate (root action open when the command fires).
4. Add/extend a scenario (see 04) that exercises it and asserts on the end
   marker; wire a metric from the begin/end pair.

**New STS coverage**
1. Find the real work site (service handler or engine seam, per the DacFx
   lesson).
2. `var diagSpan = Microsoft.SqlTools.Hosting.Utility.StsDiag.StartSpan("sts.<area>.<op>", "<feature>");`
   wrap with try/catch → `.Complete("ok")` / `.Complete("error"); throw;`.
   Struct semantics: no null-conditional, house pattern per `Batch.cs`.
3. Metadata only. Never log SQL text, row payloads, connection strings, or
   write unframed stdout (CLAUDE.md hard rules; PERF_MODE gates any harness
   product changes; stay inside the SPEC §5 seam for sts2-adjacent code).
4. Name it `sts.<family>.<operation>` — the console lanes and the forwarding
   regex key off the `sts.` prefix.

**New rich metric**: extend `richCollection.ts` snapshot or per-span block;
surface automatically via `perf_*` attr persistence + `PhGetRichDiagnostics`.

## 7. The Shared Observability Contract (Chunk 1, 2026-07-04)

The vocabulary above is now GOVERNED, not just documented:

- **Registry**: `perftest/packages/observability-contracts` — event types
  (exact + prefix families), explicit marker pairing (`connection.begin` ↔
  `connection.ready`, `query.submit` ↔ `query.complete` — suffixes are never
  guessed), field classifications, timing classes, derived metric names.
  Generated docs: `generated/markdown/EVENTS.md` (replaces hand lists).
- **Conformance**: extension test `observabilityContract.test.ts` greps the
  actually-emitted `Perf.*`/webview-mark literals and fails on unregistered
  names; the contracts package test does the same for the marker names
  CLI/in-proc scenarios wait on. Add an event ⇒ register it, regenerate,
  re-vendor the snapshot (`src/sharedInterfaces/observabilityContract.generated.ts`).
- **Eligibility**: every perftest result metric now carries a structured
  `eligibility` object (measurementEligible / ciGatingEligible / exploratory
  / diagnosticOnly + reason) computed by ONE shared function. Self-test runs
  are `interactiveHost` ⇒ exploratory, never gating. Epoch-plane and
  collector metrics are diagnostic-only by rule. Legacy `official` remains
  the gate flag; disagreements surface as validation warnings. The console's
  Submetrics tab renders the labels (gate-eligible / exploratory /
  diagnostic) with the reason on hover.

## 8. Trace Identity V1 + correlation lint (Chunk 3, 2026-07-04)

- **Identity contract**: `TraceIdentityV1` in the contracts package — the
  meaning and propagation rules for runId/repId/scenarioId, rootActionId,
  traceId/spanId, jsonRpcId (a HINT, reused per connection — never globally
  unique), webviewRpcId, ownerUri/connectionId digests, and STS2 corr/cause
  (cause is a graph EDGE on import, never a fake span parent). Root actions
  close on `ROOT_ACTION_TTL_MS` (120s) or explicit end.
- **Correlation linter**: `lintCorrelation(events)` — registry-driven pair
  balancing (explicit pairsWith: begin/ready, submit/complete), span-family
  `.begin/.end` balancing, orphan accounting (lifecycle types exempt),
  leaked-root detection past the TTL, epoch-aligned counting, scenario-window
  noise. Output includes an honest `good|fair|poor` score and human notes.
- **Surfaces**: `dc/getTraceQuality {sourceId, traceId?}` → Overview "Trace
  quality" card (score pill, orphans, unbalanced pairs, leaked roots, notes)
  and a per-trace "stitching: fair/poor" pill on the Waterfall toolbar with
  notes on hover. Fog is reported, never painted over.
