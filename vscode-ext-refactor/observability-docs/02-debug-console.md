# 02 — MSSQL Debug Console: Implementation Reference

**Updated: 2026-07-03.** All paths relative to
`vscode-mssql/extensions/mssql/`. This is the implementation doc for the
in-product diagnostics viewer; design/UX specs live in `debug-docs/`.

## 1. Module map (extension host)

`src/diagnostics/`:

| Module | Responsibility |
|---|---|
| `diagnosticsCore.ts` | The `diag` singleton: emit spans/events/metrics, seq/session identity, root-action correlation, dynamic sink registry, flushAll. Emission is a no-op with no sinks. |
| `redaction.ts` | `classify()` — the single classification/redaction choke point. Policy table by capture mode (`off`/`digest`/`redacted`/`full`); stamps `cls` on every event. |
| `sinks.ts` | `LiveTailSink` (batched pushes to the webview, gap records on overflow, viewer-internal excluded), `SessionDiagSink` (JSONL segments per session), `PerfModeSink` (harness wire: legacy perfMarker contract + additive forwarding of `rpc.*`/`webview.*`/`sts.*` diagnostic spans, tagged `diag`, viewer-internal excluded). |
| `sessionStore.ts` | Store + query engine: filters (process/feature/status/type/text/min-maxDurationMs/includeViewerInternal), pagination, session manifests, retention. Serves `store:<sessionId>` sources. |
| `analysis.ts` | Derived views: overview KPIs, user-action summaries, anomaly heuristics, `buildWaterfall` (lanes, timing classes, critical path), SQL activity rows, cause tree. |
| `perfRunImport.ts` | `importPerfRep` — converts a perf run rep (`markers.jsonl`) into DiagEvents; lifts forwarded `durationMs` attrs into span bars (`epochAlignedDiagnostic` + `stsDiag` tag). |
| `richCollection.ts` | Rich stats collector: `monitorEventLoopDelay`, `cpuUsage` deltas, heap/RSS snapshots @2s cadence, per-span heap deltas. Gated by `mssql.debugConsole.richCollection` setting / `MSSQL_COLLECT_ALL_THE_DATA=1` env / self-test dialog toggle. Diagnostic-only, never official. |
| `stsDiagListener.ts` | Loopback HTTP listener; sets `STS_DIAG_URL`/`STS_DIAG_TOKEN` for the STS child process **before spawn**; re-emits received STS span batches into the diag core. Discards when console closed. |
| `diagnosticsManager.ts` | Lifecycle: applies settings (enabled/captureMode/storePath), owns the store + sinks, registers `mssql.sessionDiag.*` commands, status bar indicator, elevated-capture timer. Constructed as the **first act of activation** so startup events are captured. |
| `perfHistory/directoryProvider.ts` | Scalable run-directory indexer: metadata-first `.dc-history-index.json` cache (fingerprint = dir mtime + summary mtime/size), chunked scans (25 dirs/tick, setImmediate yields), shared in-flight scanPromise, `rescanIfStale(5000)`, suite grouping rules, `deleteRun` (path-safe, index-evicting). Measured: 1000 runs cold 3.6s / warm 24ms. |
| `perfHistory/perfHistoryService.ts` | Source registry (default root + opened directories + read-only bundles + SQLite preview stub), provider dispatch, lazy artifact/dump loading (512KB cap), `richDiagnostics` (parses rep markers for `system.rich.snapshot` + `perf_*` span attrs), `deleteRun` guard (writable directory sources only). |
| `selfTest/selfTestService.ts` | In-product self-test: loads the in-proc engine, connection modes (active/saved/env-var/none), diag→MarkerBus tap (viewer-internal excluded; preserves `perf.metrics` as `perf_*` attrs), run persistence to the perf runs root, status-bar run indicator (right-most), progress notifications to the dialog, cancel. |
| `selfTest/connectionString.ts` | In-host parsing of `STS2_SQLSERVER_CONNSTRING` → profile (value never displayed/logged/persisted). |
| `selfTest/inprocLoader.ts` | Runtime walk-up resolution of `@mssqlperf/inproc` (works from `dist/`/`out/`, degrades gracefully to "self-test unavailable"). |

Controller: `src/controllers/debugConsoleWebviewController.ts` — one webview
panel; owns the live archive (seeded from the current session's persisted
store on open, seq-deduped), registers all RPC handlers, applies the
1/sec dataVersion throttle on live pushes.

## 2. RPC surface (shared contracts)

`src/sharedInterfaces/debugConsole.ts` (`Dc*`) and `perfHistory.ts` (`Ph*`):

- **Sources/live**: `DcListSources`, `DcSubscribeLive`/`DcUnsubscribeLive`,
  `DcLivePush` (events + gap records), `DcSetCaptureMode`,
  `DcCaptureChanged`.
- **Queries**: `DcQueryEvents` (EventQuery: process/feature/status/type/
  text/min-maxDurationMs/includeViewerInternal + paging), `DcGetOverview`,
  `DcGetWaterfall`, `DcGetCauseTree`, `DcGetSqlActivity`, `DcListTraces`,
  `DcExport`, `DcImportPerfRun`.
- **Self-test**: `DcRunSelfTest` (scenario list, reps, connection mode, rich
  toggle) → `SelfTestRunStarted`; `DcSelfTestProgress` notifications
  (per-hop/per-rep/summary); `DcCancelSelfTest`.
- **Perf history**: `PhListSources`, `PhAddSource`, `PhRescan`,
  `PhQueryRuns` (paged, filters), `PhQueryScenarios` (view modes/grouping,
  incl. `memberScenarioIds` for group drill-down), `PhScenarioDetails`
  (reps, submetrics, failure reasons), `PhGetWaterfall`, `PhGetSqlActivity`,
  `PhGetMetricSeries` (trends), `PhGetDump`, `PhGetRichDiagnostics`,
  `PhDeleteRun` (modal-confirmed), `PhIndexProgress` notifications.
- **Filter language**: `sharedInterfaces/traceFilter.ts` —
  `parseTraceFilter`/`applyTraceFilter`; expressions `dur>1000`, `dur<2s`,
  `proc:sts|extension|webview|sql`, `feat:<x>`, `status:<s>`, `type:<t>`,
  free text; unknown tokens surfaced in `invalid[]`, never dropped.

## 3. Webview (React, `src/webviews/pages/DebugConsole/`)

| File | Contents |
|---|---|
| `state.tsx` | `DcProvider` context: source selection (`isLive` **derived** — Current session = live), routing, live event buffer (20k cap), dataVersion throttle (1/sec), self-test state. |
| `shell.tsx` | 44px top bar (icon-only title, source picker + live dot, search, capture chip + popover, export, Run self-test), 210px collapsible grouped left rail. |
| `pagesCore.tsx` | Overview (KPI strip + recent actions + anomalies), Consolidated Trace (live controls: pause/resume, clear + show-all, auto-scroll, filter expressions — gated to the live source), Waterfall page (trace picker + full layout). |
| `waterfallView.tsx` | Reusable waterfall: native-scroll zoom (content grows to zoom×100%, scrollbar expands; wheel-at-cursor via post-render scrollLeft restore; W/S/A/D; drag-pan with click suppression; Esc/dbl-click reset), fixed label column outside the h-scroller, clipped tracks, visible-window axis, row-packed lanes, pixel-based label visibility, wall-clock decomposition strip, inspector + critical path, Event Details master/detail table. Layouts: `full` (splitter grid, fills page) / `embedded` (history tab). |
| `pagesPerfHistory.tsx` | Perf Test History: Runs Summary tab (KPIs, needs-attention, cross-run trend → drill-in) + Run Analysis tab (collapsible source/runs region, filter rail, scenario table with view modes + group drill-down, charts rail, collapsible bottom tabs: Submetrics/Waterfall/SQL Activity/Diagnostics/Artifacts/Validation/All Data Dump). Virtualized fixed-layout tables, shift-click ranges, per-run Delete. |
| `pagesPerf.tsx` | Session History (stored sessions list → open as source). |
| `pagesMore.tsx` | SQL Activity, Connections, Query & Results, Object Explorer feature pages, Exports, Settings; gating for not-yet-available pages. |
| `selftestDialog.tsx` | Run dialog: scenario picker, reps, connection mode (active/saved/env/none), rich diagnostics toggle, live status console, summary + "open attached" flow. |
| `charts.tsx`, `common.tsx` | TrendChart/sparklines; KPI/pills/formatters/status components. |
| `debugConsole.css` | Layout system: `.dc-page` flex column, split panes fill (`flex:1 1 auto`), one-row toolbars/KPI strips (min/max widths + h-scroll), fixed-layout tables (`.ph-table-fixed`), waterfall v2 chart styles. |

## 4. Settings, commands, env vars

Settings (`package.json`): `mssql.debugConsole.enabled` (gates everything),
`mssql.debugConsole.perfRunsRoot`, `mssql.debugConsole.richCollection`,
`mssql.sessionDiag.enabled` (always-on startup→shutdown capture),
`mssql.sessionDiag.captureMode` (`digest`/`redacted`), `mssql.sessionDiag.storePath`,
`mssql.sessionDiag.maxSessions` (10), `mssql.sessionDiag.maxAgeDays` (14).

Commands: `mssql.sessionDiag.enable`/`disable`/`clear`/`elevateCapture`
(reason + 15-min auto-revert)/`openStorageFolder`; the console itself opens
via the MSSQL Debug Console command / status bar.

Env: `MSSQL_COLLECT_ALL_THE_DATA=1` (rich collection),
`STS_DIAG_URL`/`STS_DIAG_TOKEN` (set by the extension for the STS child;
never set these manually), `STS2_SQLSERVER_CONNSTRING` (self-test env
connection mode), `PERF_MODE`/control-server vars (harness-owned, see 04).

## 5. Behavioral details worth knowing

- **Activation order**: DiagnosticsManager + console registration run before
  the first `Perf` marker so `sessionDiag.enabled` captures activation. The
  STS diag listener starts **before** the STS spawn so the child inherits
  the loopback env.
- **Live source semantics**: "Current VS Code Session" is the only live
  source; selecting any other source disables live-only controls
  (pause/clear/auto-scroll) with explanatory tooltips.
- **Designer prompt suppression**: designers opened from self-test OE
  sessions (connection `applicationName` prefix `vscode-mssql-selftest`)
  skip the "restore?" modal — scoped so real users are unaffected.
- **Self-test status bar**: `$(record) MSSQL Self-Test n/m`, priority
  -1000 (right-most, stationary while other items churn).
- **Scale numbers**: history index 1000 runs cold 3.6s / warm 24ms; live
  view cap 20k events; dataVersion ≤1/sec; artifact dumps capped 512KB.

## 6. Evidence durability (Chunk 2, 2026-07-04)

- **Store integrity**: session manifests now record `sizeBytes` + exact
  `droppedRanges`; `SessionStore.validateStore()` checks segment existence,
  line counts vs manifest, partial trailing lines, and boundary seqs.
  Size-based retention via `mssql.sessionDiag.maxTotalMB` (default 512) —
  oldest closed sessions evicted first.
- **Exact gaps + backfill**: live-tail gap records carry
  `firstAvailableSeq`; the TopBar "Backfill" button recovers dropped ranges
  from the session store journal (`dc/backfillGap`) and merges them back
  into the live view with honest partial/failed outcomes.
- **Sink health**: every sink self-reports (`health()`); `dc/getHealth`
  returns sink rows + store validation; the Settings page renders a
  Diagnostics health card. A sink may degrade — never silently.
- **Untrusted imports**: `repDir`/dump paths are containment-checked
  (webview-supplied ids cannot escape the source root); markers.jsonl
  import refuses oversized/malformed lines and records a synthetic
  `import.linesSkipped` warning event.
- **Provenance**: scenario details carry `runProvenance` (source kind,
  read-only, pass type, environment hash, run status, import warnings),
  rendered at the top of the Validation tab.
- **Privacy canaries**: `debugConsolePrivacyCanary.test.ts` pushes sentinel
  secrets/SQL/rows/provider text through classification, the on-disk
  journal, and the harness wire queue — plaintext leaks fail the suite;
  secrets never plaintext even under full capture.
