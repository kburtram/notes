# 01 — Unified Observability Architecture

**Updated: 2026-07-03.** How an event travels from product code to a chart,
and the invariants that hold at every hop.

## 1. The event pipeline

```
 EMIT                    CLASSIFY            FAN OUT (sinks)            CONSUME
 ─────                   ────────            ───────────────            ───────
 Perf.marker(...)   ┐
 diag.span(...)     ├──► diag core ──► classify()/redact ──► LiveTailSink ──► Debug Console live view
 rpc instrumentation┘    (diagnosticsCore.ts)            ├─► SessionDiagSink ─► JSONL store → Session History
                         seq, sessionId,                 ├─► consoleArchive ──► current-session queries
 STS process:            epochMs, corr ids               ├─► PerfModeSink ────► perftest control server
 StsDiag.StartSpan ──► loopback HTTP ──► stsDiagListener ┘                      (markers.jsonl in the run dir)
 (STS_DIAG_URL)         (re-emitted into diag core)      └─► self-test tap ───► in-proc MarkerBus (waits/metrics)
```

- **Emit.** The extension emits through two facades: `Perf`
  (`src/perf/perfTelemetry.ts` — semantic begin/end/instant *markers*, the
  official timing vocabulary) and `diag`
  (`src/diagnostics/diagnosticsCore.ts` — *spans/events/metrics* with
  features, correlation, attrs). STS emits `StsDiag` spans over a loopback
  HTTP batch channel that the extension re-ingests
  (`src/diagnostics/stsDiagListener.ts`).
- **Classify.** Every event passes one choke point (`redaction.ts
  classify()`) before any sink sees it. Classification stamps
  `cls: {max, redactedFields, policyId}`. There is no code path that writes an
  unclassified event.
- **Fan out.** Sinks are registered/removed dynamically on the diag core.
  Emission is a no-op when no sink is attached (near-zero overhead when
  nothing is listening). A sink failure never breaks the product (try/catch
  per sink).
- **Consume.** The Debug Console renders live + stored events; the perftest
  harness persists forwarded events per rep and analyzes/gates them; the
  self-test engine *waits* on markers via its MarkerBus.

## 2. The DiagEvent envelope

Defined in `src/sharedInterfaces/debugConsole.ts` (`DIAG_SCHEMA_VERSION`).
The essential fields:

| Field | Meaning |
|---|---|
| `eventId`, `sessionId`, `seq` | Identity + strict per-session ordering |
| `epochMs` | Wall-clock (cross-process alignment) |
| `process` | `extensionHost` \| `webview` \| `sqlToolsService` \| `harness` \| `system` |
| `feature` | Product feature bucket (`query`, `connection`, `objectExplorer`, …) |
| `kind` / `type` | `span`/`event`/`metric` + dotted type name (the vocabulary) |
| `status`, `durationMs` | Outcome + measured duration for spans |
| `corr` | Correlation ids: root action/trace id, rpc id, ownerUri digest, … |
| `tags` | e.g. `perfMarker`, `stsDiag`, `viewerInternal` |
| `cls` | Classification proof (never absent) |
| `perf` | Optional rich block (heap delta etc.) when rich collection is on |

## 3. Correlation model

- **Root actions.** User-initiated commands establish a root action id; spans
  emitted while it is open auto-attach (`diag` root-action auto-correlation).
  A "trace" in the console = one root action's event set (with a bounded time
  window), which is why browsing a results grid joins the `runQuery` trace —
  the waterfall Event Details table makes that composition explicit.
- **Cross-process stitching.** rpc.* client spans (extension) and
  `sts.dispatch.*` server spans (STS) share the JSON-RPC id; `webview.*`
  spans carry the webview controller's rpc correlation. Epoch timestamps
  align lanes; monotonic clocks stay authoritative within a process.

## 4. Timing honesty (the load-bearing invariant)

Two timing classes are never mixed silently:

- **`officialSameProcess` / `productTimer`** — same-process monotonic
  measurements. Only these can be *official* numbers in perf runs.
- **`epochAlignedDiagnostic`** — cross-process bars aligned by wall clock
  (STS spans in an extension-anchored waterfall). Rendered hatched in every
  waterfall, labeled "aligned diagnostic", excluded from official metrics.

The harness enforces the same rule independently (perftest
`REGRESSION_MODEL.md`): diagnostics never contaminate official numbers —
rich collection runs are marked and their reps are never official.

## 5. Privacy invariants (verbatim, enforced in code)

- SQL text, result data, connection strings, tokens, and secrets are **never
  captured by default and never as plaintext regardless of settings**.
  `classify()` is the single choke point; elevated ("full") capture is
  time-bounded, reason-logged, local-only, and still never captures secrets.
- STS diag emits **protocol metadata only** (method names, durations,
  outcomes — never SQL text, parameters, row payloads, or connection
  strings).
- Env-var connection strings (`STS2_SQLSERVER_CONNSTRING`) are parsed
  in-host and never displayed, logged, or persisted; saved-profile passwords
  come from the credential store only.
- Nothing is uploaded anywhere. All stores are local files under user
  control, with retention settings.

## 6. Self-noise exclusion

The console observing the product must not observe itself into a feedback
loop. Spans from the console's own webview are tagged `viewerInternal` and:

- excluded from LiveTailSink pushes (no self-triggering re-renders),
- excluded from store queries and analysis by default
  (`includeViewerInternal` opt-in on `EventQuery`),
- excluded from PerfModeSink forwarding (never enter a perf run),
- excluded from the self-test tap (never pollute rep markers).

## 7. Stores and their lifecycles

| Store | Contents | Location (default) | Retention |
|---|---|---|---|
| Session Diag store | Continuous per-session JSONL event journals | `<globalStorage>/ms-mssql.mssql/session-diag/` (override: `mssql.sessionDiag.storePath`) | `maxSessions` (10) / `maxAgeDays` (14) |
| Perf runs root | Discrete run directories (self-test + CLI): `summary.json`, per-rep `result.json` + `markers.jsonl` + artifacts | `<globalStorage>/self-test-runs` (override: `mssql.debugConsole.perfRunsRoot`) | user-managed (Delete action in Perf Test History) |
| perftest SQLite store | Harness history for baselines/compare/report | `perftest/perf-runs` + store per config | harness-managed |

Startup capture: `mssql.sessionDiag.enabled` initializes the store sink as
the **first act of extension activation** (before the `activate.begin`
marker), so startup/activation data is always captured when enabled; the
console seeds its live source from the session store on open.

## 8. Design lineage

- Debug Console UX bar: the completions debug view
  (`completions/vscode-mssql`, dev/karlb/completions) — packed layouts,
  one-row toolbars, splitter-filled panes, live capture controls.
- Report bar: cloud-deploy-agent `benchmark.html` (perftest phase 3);
  phase 4 = the in-product Perf Test History view (now shipped in the
  console).
- Specs: `debug-docs/` (technical design + UX + history-view spec with
  `pth-*.png` mocks).
