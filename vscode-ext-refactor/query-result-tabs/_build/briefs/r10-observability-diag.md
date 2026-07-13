# R10 — Observability, Diagnostics, Perf Marks & Session-Diag (Query Studio)

Reader brief for the vector-debugger / spatial-visualizer result-tab build. Sources: `C:/repos/test/vscode-mssql/extensions/mssql/src` (branch `dev/query`), `C:/repos/test/perftest/packages/observability-contracts`, and live session logs under `C:/Users/karlb/AppData/Roaming/Code/User/globalStorage/ms-mssql.mssql/session-diag/sessions`. All paths below are relative to `vscode-mssql/extensions/mssql/` unless noted.

"Debug Console" throughout means the **MSSQL Debug Console webview** (command `mssql.openDebugConsole`), not VS Code's debug console.

---

## 1. Architecture: one emission path, pluggable sinks, different gates

`src/diagnostics/diagnosticsCore.ts` is the single emission path for ALL product instrumentation (file header, lines 6–16). A singleton `export const diag = new DiagnosticsCore()` at diagnosticsCore.ts:497. Sinks implement `DiagnosticSink` (diagnosticsCore.ts:59–67: `id`, `tryWrite(event)` non-blocking, optional `flush()`, `dispose()`, `health()`).

Active sinks (src/diagnostics/sinks.ts):

| Sink | id | Gate | Behavior |
|---|---|---|---|
| `PerfModeSink` (sinks.ts:66) | `perfMode` | `PERF_MODE=1` + `PERF_MARKER_URL`/`PERF_CONTROL_TOKEN` env | Forwards `perfMarker`-tagged events in the **exact legacy harness wire format** (`LegacyPerfMarker`, sinks.ts:35–47) via HTTP NDJSON POST; also forwards diag spans matching `FORWARDED_SPAN_TYPES = /^(rpc\.|webview\.|sts\.)/` (sinks.ts:57) with `attrs.diag=true` so CLI waterfalls get sublane detail. Queue 1000 / flush 250 ms / POST timeout 2 s. |
| `LiveTailSink` (sinks.ts:226) | `liveTail` | Debug Console open | Ring of 5000 events, batch delivery every 120 ms; drops accounted as exact `GapRecord`s (reason `subscriberOverflow`). Skips `viewerInternal`-tagged events entirely (feedback-loop guard, sinks.ts:255–262). |
| `SessionDiagSink` (sinks.ts:348) | `sessionDiag` | `mssql.sessionDiag.enabled` | JSONL segment journal + manifest; flush every 500 ms, buffer 2000, segment rollover at 5000 events (`SEGMENT_MAX_EVENTS`, sinks.ts:344). |
| consoleArchive (inline, debugConsoleWebviewController.ts:173–184) | `consoleArchive` | Debug Console open | In-memory array capped at `LIVE_ARCHIVE_CAP = 100_000` (line 117); backs history queries for the live source. |

**Zero-cost guarantee** (the property the new panes must preserve): `diag.emit()` returns immediately when `this.sinks.length === 0` (diagnosticsCore.ts:302–304 — "one array-length check"); `Perf.marker`/`Perf.webviewMark` early-return on `!diag.anySinkActive` (perfTelemetry.ts:116, 158); every sink write is wrapped in try/catch — "Instrumentation must never throw into the product" (diagnosticsCore.ts:15, 377–383).

Wiring order (src/extension.ts): `DiagnosticsManager` is created **first** in activation (extension.ts:69–74, gated on `mssql.debugConsole.enabled` default true) so startup markers are captured, then `registerDebugConsole(context, diagnosticsManager)`; `startStsDiagListener()` runs before STS spawn (extension.ts:108–110); `registerPerfApi(context, {getController})` at the end (extension.ts:152).

---

## 2. The event envelope (`DiagEvent`) and on-disk format

Contract: `src/sharedInterfaces/debugConsole.ts` (must stay JSON-serializable, no runtime imports). Key types, verbatim:

- `DIAG_SCHEMA_VERSION = "mssql.diag.event/1"` (debugConsole.ts:13)
- `DiagProcess = "extensionHost" | "webview" | "renderer" | "sqlToolsService" | "sqlServer" | "harness" | "system"` (:15)
- `DiagKind = "event" | "span" | "metric" | "request" | "response" | "sqlActivity" | "renderPhase" | "gap" | "state"` (:24)
- `DiagStatus = "ok" | "info" | "warning" | "error" | "blocked" | "partial"` (:35)
- `DiagTimingClass = "officialSameProcess" | "productTimer" | "epochAlignedDiagnostic" | "collectorDiagnostic" | "inferred"` (:37)
- `DiagEvent` (:95–131): `eventId` (`evt_<base36 seq>`), `sessionId`, `seq`, `epochMs`, `monotonicNs?` (string, hrtime ns), `process`, `pid?`, `feature`, `kind`, `type`, `status`, `traceId?`, `causeEventId?`, `entity?` (`{kind,id}`), `durationMs?`, `timingClass?`, `payload?` (`Record<string, ClassifiedValue>`), `cls` (`{max, redactedFields, policyId}`), `tags?`, `perf?` (rich-mode enrichment block, never official-eligible).
- `GapRecord` (:133–145), `SessionManifest` schemaVersion `"mssql.diag.sessionManifest/1"` (:204–221).

Session id format: `sess_<YYYYMMDDHHMMSS>_<pid>` (diagnosticsCore.ts:117–120).

**On-disk store** (verified live): `<globalStorage>/ms-mssql.mssql/session-diag/sessions/<sessionId>/manifest.json` + `events/segment-000001.jsonl`. Real line (redacted-mode session, extension-host marker):

```json
{"schemaVersion":"mssql.diag.event/1","eventId":"evt_000004","sessionId":"sess_20260711094516_44868","seq":4,"epochMs":1783763117089,"process":"extensionHost","pid":44868,"feature":"query","kind":"event","type":"mssql.queryStudio.open.begin","status":"ok","cls":{"max":"public","redactedFields":0,"policyId":"policy_redacted_default"},"monotonicNs":"233752722002800","tags":["perfMarker","phase:begin"]}
```

Webview mark as stored (note `process:"webview"`, `pid:0`, webview-local `monotonicNs`, tag `webview:queryStudio`):

```json
{"eventId":"evt_00001j","seq":55,"process":"webview","pid":0,"feature":"query","kind":"event","type":"mssql.queryStudio.boot.scriptStart","monotonicNs":"388500000","tags":["perfMarker","phase:instant","webview:queryStudio"], ...}
```

Payload fields are stored **post-redaction** as `ClassifiedValue` `{v?, cls, handling, digest?, len?}` — e.g. `"scope":{"v":"document","cls":"diagnostic.metadata","handling":"plain"}`.

---

## 3. Extension-side instrumentation APIs

### 3.1 `diag` core (src/diagnostics/diagnosticsCore.ts)

- `diag.emit(input: EmitInput): string | undefined` (:301) — returns eventId. `EmitInput` (:37–57): `feature`, `type`, optional `kind/status/traceId/causeEventId/entity/durationMs/timingClass/tags/process/pid/epochMs/monotonicNs`, and `fields?: Record<string, RawField>` where `RawField = { raw: unknown; cls: DataClassification }` — **redaction happens at this boundary** via `classifyPayload` (redaction.ts:165).
- `diag.startSpan(input): DiagSpan` (:411) — emits `<type>.begin` now; `span.end(status?, fields?)` emits `<type>.end` with `durationMs` from `process.hrtime.bigint()` delta, `timingClass:"officialSameProcess"`, `causeEventId` = begin's eventId; `span.fail(error)` emits `.end` with `status:"error"` and an `error` field (message only, `cls:"diagnostic.metadata"`). Under rich mode the end carries a `perf` block with `heapDeltaKB` + collector metrics.
- `newTraceId(hint?)` (:78) → `trace_<hint12>_<base36 time>_<counter>`.
- `diag.withTrace(traceId, fn)` (:270) — ambient trace for sync scopes; `diag.currentTrace` (:280).
- `diag.bindEntityTrace(entityId, traceId)` / `diag.traceForEntity(entityId)` (:285–297) — entity-keyed correlation (e.g. document URI digest), LRU-capped at 500. **Currently unused by Query Studio code** — available for the panes.
- `withRootAction(label, feature, fn)` (src/diagnostics/diagnosticsManager.ts:323–332) — emits `userAction.<label>` with tag `"rootAction"`, runs `fn` under a fresh trace.
- `diag.setRichMode/setRichProvider`, `diag.flushAll()`, `diag.sinkHealthSnapshot()`.

### 3.2 Trace correlation rules (critical)

`emit()` trace resolution (diagnosticsCore.ts:311–329): explicit `input.traceId` → ambient (`withTrace`) → entity binding → **root-action auto-correlation**: if the type matches `ROOT_BEGINNERS`, a new root trace opens and subsequent traceless events inherit it for `ROOT_WINDOW_MS = 120_000` (:106). Verbatim list (:107–115):

```
/^mssql\.command\.invoked$/, /^mssql\.query\.submit$/, /^mssql\.connection\.begin$/,
/^mssql\.oe\.expand\.begin$/, /^mssql\.oe\.session\.create\.begin$/,
/^command\..+\.begin$/, /^userAction\./
```

**Gotcha (verified in the live log):** `mssql.queryStudio.query.submit` does NOT match `^mssql\.query\.submit$` — QS query markers are currently emitted **without a traceId** (orphans), while the enclosing `webview.queryStudio.qs/execute` request span mints its own trace (`trace_webviewquery_…`). They co-exist but do not join. New pane instrumentation that wants a stitched waterfall must pass `traceId` explicitly (from a span or `withTrace`) rather than relying on root inheritance.

`startSpan` trace resolution (`resolveSpanTrace`, :394–408): explicit → ambient → active root (within window) → fresh `newTraceId(feature)`.

Trace Identity V1 contract lives in the generated file (`TraceIdentityV1`, observabilityContract.generated.ts:2170–2190; `ROOT_ACTION_TTL_MS = 120_000` :2193). `lintCorrelation()` (:2242) scores stitching quality; correlation-exempt types: `/^(sessionDiag\.|system\.|selfTest\.|scenario\.|import\.|mssql\.sts\.pid|mssql\.activate)/` (:2234).

### 3.3 `Perf` facade (src/perf/perfTelemetry.ts)

Thin facade over `diag` since Phase 4 (header :6–18). API (`IPerfTelemetry`, :35–56):

- `Perf.marker(name, phase = "instant" | "begin" | "end" | "counter", attrs?, correlationId?)` (:110) → `diag.emit` with tags `["perfMarker", "phase:<phase>"]` (+ `"perfCorrelation"` and `traceId` when correlationId passed), `kind:"metric"` for counters else `"event"`, `status:"error"` iff `attrs.error === true`.
- `Perf.webviewMark(mark, webviewName)` (:149) — ingests a `WebviewPerfMark` (validates numeric ns strings), emits with `process:"webview"`, `pid:0`, `epochMs` from the mark's `timestampUnixNs`, mark's own `monotonicNs`, tags `["perfMarker","phase:instant","webview:<name>"]`.
- `Perf.enabled` = `process.env.PERF_MODE === "1"` (:93). PERF_MODE env inputs: `PERF_MARKER_URL`, `PERF_CONTROL_TOKEN`, `PERF_RUN_ID`, `PERF_REP_ID`, `PERF_SCENARIO_ID` (:95–104).
- **Feature bucketing** `featureFor(name)` (:59–68): `mssql.connection|mssql.sts`→`connection`, `mssql.query*`→`query`, `mssql.resultsGrid`→`resultsGrid`, `mssql.oe`→`objectExplorer`, `mssql.activate|mssql.extension`→`system`, `mssql.command`→`command`, `driver.`→`harness`, else `system`. **Because `"mssql.queryStudio.…".startsWith("mssql.query")`, ALL QS markers land in feature bucket `query`** (confirmed in logs). Direct `diag.emit` calls in QS code set `feature:"queryStudio"` explicitly. Keep this in mind when filtering Debug Console pages (see §7).
- Attr classification in normal use: `ATTR_CLASSIFICATION` map (:76–84) — `nodePath`/`objectName`→`object.name`, `documentUri`/`uri`→`source.path`, `messages`→`user.text`, everything else defaults `diagnostic.metadata`. Under PERF_MODE everything is `diagnostic.metadata` (synthetic data by harness contract).

### 3.4 Other extension-side channels

- `this.logger: ILogger` on every webview controller (webviewBaseController.ts:148, 162 — `logger.withPrefix(viewId)`), levels via `LoggerMethod` (sharedInterfaces/logger.ts). This is VS Code Output-channel logging (human debugging), NOT the diag substrate.
- Telemetry (`startActivity`/`sendActionEvent`, TelemetryViews.WebviewController) rides alongside in `webviewBaseController.onRequest` — separate concern, do not conflate.
- Rich collection (src/diagnostics/richCollection.ts): `richStats.enable(reason)/disable(reason)` singleton; samples heap/RSS/CPU/event-loop every `SAMPLE_INTERVAL_MS = 2000` (:27) and provides per-span deltas. Gates: setting `mssql.debugConsole.richCollection`, env `MSSQL_COLLECT_ALL_THE_DATA=1` (diagnosticsManager.ts:25–26, 85–96). `system.rich.snapshot` heartbeat additionally gated on `mssql.debugConsole.richSnapshotHeartbeat` (default off; richCollection.ts:29–45). Off ⇒ zero cost.
- Settings capture (src/diagnostics/featureCapture/settingsSnapshot.ts): `emitSettingsSnapshot(spec, reason)` (:47) and `watchFeatureSettings(spec)` (:59) emit `settings.snapshot` / `settings.changed` (kind `state`, feature `diagnostics`, `settingsFeature` attr). Secret-pattern keys (`/apikey|api-key|token|secret|password|credential/i`) always classified `secret`. A new pane with its own config surface should register a `FeatureSettingsSpec`.
- STS-side spans (src/diagnostics/stsDiagListener.ts): loopback HTTP listener started pre-spawn; passes `STS_DIAG_URL`/`STS_DIAG_TOKEN` env (:82–83). Ingest (:95–127) stamps `process:"sqlToolsService"`, `timingClass:"epochAlignedDiagnostic"`, tags `["stsDiag"]`, anchored at span start (`epochMs = startEpochMs`). Families: `sts.dispatch.<method>`, `sts.sql.*`, `sts.smo.*`, `sts.dacfx.*`, `sts.event.*`.

---

## 4. Webview-side instrumentation APIs

### 4.1 `perfMarks` (src/webviews/common/perfMarks.ts) — the ONLY webview→diag channel for timings

- `perfMark(name, attrs?)` (:62) — captures `timestampUnixNs` (epoch, from `performance.timeOrigin + performance.now()`) and `monotonicNs` (µs-precision `performance.now()`), sends `PerfWebviewMarkNotification` when enabled, else queues up to `MAX_PENDING = 50` (:28) **with original timestamps** (late enablement never distorts timing).
- `perfMarkAfterNextPaint(name, attrs?)` (:94) — double-`requestAnimationFrame` "visually complete" mark with a **500 ms fallback that adds `rafThrottled: true`** when the webview is hidden/throttled (BOOT-4 lesson, :98–111). Use for every "rendered/painted" mark.
- `perfMarksEnabled()` (:44) — gate ANY non-trivial attr computation on this in hot paths (pattern: results.tsx:366, resultsGrid.tsx:606).
- `initPerfMarks(rpc)` (:32) — wired once by the shared webview provider (`vscodeWebviewProvider.tsx`); pane code never calls it.

### 4.2 Enablement handshake (why marks flow outside PERF_MODE too)

Wire contract (src/sharedInterfaces/perf.ts): `PerfEnableNotification` = method `"perf/enable"` (:24), `PerfWebviewMarkNotification` = `"perf/webviewMark"` (:28), payload `WebviewPerfMark {name, timestampUnixNs, monotonicNs, attrs?}` (:14–22).

Host bridge in `webviewBaseController` constructor (src/controllers/webviewBaseController.ts:178–213): forwards incoming marks via `Perf.webviewMark(mark, this._sourceFile)` (:185–187); sends `perf/enable` whenever `Perf.enabled || diag.anySinkActive` — i.e. **PERF_MODE, Debug Console open, or session-diag capture on** — retried at 500/2000/5000/15000/30000 ms plus a 20 s poll for late-opened consoles (:193–213). So webview marks are inert booleans by default and light up automatically when anyone listens.

### 4.3 Automatic per-request spans (free coverage for new RPCs)

`webviewBaseController.onRequest` wraps EVERY webview→host request in a diag span (webviewBaseController.ts:502–573): `feature: "webview.<sourceFile>"`, `kind: "request"`, `type: "webview.<sourceFile>.<method>"` (:516–526) — e.g. `webview.queryStudio.qs/getRows.begin` / `.end` (verified in logs). Success → `end("ok")`, failure → `fail(error)`. Debug Console's own traffic (`_sourceFile === "debugConsole"`) is tagged `viewerInternal` with `traceId: "viewer_<sessionId>"` and excluded from live tail + analysis (sinks.ts:255, analysis.ts:70, EventQuery.includeViewerInternal debugConsole.ts:240–246).

**Consequence:** any `qs/<pane>.<op>` request the panes add gets begin/end spans + durations in Debug Console and session-diag with zero extra code. Name RPC methods self-describingly (`qs/vector.sample`, `qs/spatial.getFeatures`) — the method string IS the span name.

Webview bundle note: `_getHtmlTemplate` (webviewBaseController.ts:241–279) injects `modulepreload` links from a bundle-time manifest (BOOT-2) — lazy chunks stay OUT of that closure.

---

## 5. Naming conventions (with real examples)

All lowercase dot-separated, camelCase segments; **no invented suffix rules — pairing is explicit** in the registry via `pairsWith` (conventions blurb, perftest event-types.json "conventions").

| Kind | Convention | Examples |
|---|---|---|
| Extension-host markers (measurement-grade) | `mssql.<feature>.<op>[.begin/.end]`, pairs explicit (`begin/ready`, `submit/complete` also exist) | `mssql.queryStudio.open.begin/.end`, `mssql.queryStudio.connect.begin/.ready`, `mssql.queryStudio.query.submit/.complete`, `mssql.queryStudio.rows.windowFetch.begin/.end`, `mssql.queryStudio.export.begin/.end` |
| Instant markers | `mssql.<feature>.<noun>` | `mssql.queryStudio.query.firstResult`, `mssql.queryStudio.cancel`, `mssql.queryStudio.scan.run`, `mssql.queryStudio.plan.parse`, `mssql.queryStudio.rows.maxRowsPerResultSet` |
| Webview marks (`kind:"webviewMark"`, epochAligned) | `mssql.queryStudio.<noun>` past-tense / `boot.*` | `mssql.queryStudio.resultsRendered`, `mssql.queryStudio.boot.scriptStart/.reactMount/.monacoReady/.editorInteractive/.gridChunkRequested/.gridChunkLoaded/.planChunkLoaded/.autoRunStart`, `mssql.queryStudio.grid.window.request/.received`, `mssql.queryStudio.grid.firstVisibleRowsPainted`, `mssql.queryStudio.messagesPrepared/.messagesRendered`, `mssql.queryStudio.textView.capped` |
| Diag spans (diagnostic-only, no `mssql.` prefix) | `<feature>.<op>` span families registered by **prefix** | `queryStudio.sync.applyEdit`, `queryStudio.inlineCompletion.bridge`, `queryStudio.languageService.route`, `rpc.<method>`, `webview.<controller>.<method>`, `sts.dispatch.<method>`, `metadata.*`, `sqlDataPlane.*` |
| Plain events | `<feature>.<noun>` | `queryStudio.open.resolve`, `queryStudio.dbSwitch`, `queryStudio.sync.resync`, `queryStudio.saveAs.adopted`, `queryStudio.runRecord.captured`, `settings.snapshot` |
| Derived metrics | `mssql.<feature>.<name>` with `derivedFrom: [begin, end]` | `mssql.queryStudio.open`, `mssql.queryStudio.connect`, `mssql.queryStudio.query.toComplete`, `mssql.queryStudio.query.toRender`, `mssql.queryStudio.open.toEditorInteractive`, `mssql.queryStudio.open.toResultsRendered` (generated.ts:1880–1937) |

Attr classification vocabulary in the registry (generated.ts:1939–1975): `structuralMetadata` (counts/durations/statuses — stored normally), `diagnosticMetric` (heap bytes, queue depth), `safeEnum` (**must be a closed enum, never free text**), plus `secret`/`userSql`/`resultData`/`providerText`/`identifierSensitive` rules. Timing classes (:1976–1993): `sameProcessMonotonic` (solid bar, measurement-eligible), `epochAligned` (hatched, diagnostic-only always), `derived`.

Attrs on the flagship QS pair, verbatim from the registry: `mssql.queryStudio.query.submit` attrs `scope, batchCount, selection, tuningDigest, tuningProfile` (generated.ts:675–692); `…query.complete` attrs `batches, resultSets, rows, errors, canceled, partial, bytes, pages, spillWrites, spillReads, appendMsTotal, spillWriteMsTotal, spillReadMsTotal, materializeMsTotal, windowCacheHits, windowCacheMisses` (:694–722). `resultsRendered` attrs `rows, resultSets, partial, fromSpill` — "measurement-eligible via the harness calibrated plane only" (:737–752).

---

## 6. How QS emits today — exact call sites

Extension host (all via `Perf.marker` unless noted):

- `mssql.queryStudio.open.begin` — queryStudioEditorProvider.ts:90 (top of `resolveCustomTextEditor`); `queryStudio.open.resolve` diag.emit with `uriScheme/languageId/isUntitled/isDirty/chars/backupRestore` — :95–108.
- `mssql.queryStudio.open.end` `{fromCache:false}` — queryStudioController.ts:661, fired **once** inside the `qs/getDiagnosticsSummary` handler (webview-ready signal, :658–663).
- Connect pair — documentSessionBinding.ts:436 (`connect.begin`), :476/:497 (`connect.ready`, success and failure-with-reason paths).
- Query lifecycle — executionOrchestrator.ts:254 (`query.submit`), :323 (`query.firstResult` `{msFromSubmit}`), :370 (`query.complete` with rowStore stats aggregates), :388 (`cancel` `{msToAck,msToTerminal}`), :429/:463 (`sqlcmd.run`).
- Row pipeline — rowStore.ts:217 (`rows.append`, verbose-only), :357/:373/:410/:500 (`rows.windowFetch.begin/.end` with `resultSetId,start,count,fromSpill,ms,cacheHit,materializedPages`), :674/:761 (`rows.spill.write/.read`).
- Export — resultExport.ts:74/:81/:98. Scan/SQLCMD — queryStudioController.ts:461/:496/:512.
- Spans — queryStudioDocumentModel.ts:275 (`queryStudio.sync.applyEdit` with graded end status ok/warning/info), queryStudioController.ts:981 (`queryStudio.inlineCompletion.bridge` with `surface`/`trigger` fields and `returned` end field); `queryStudio.dbSwitch` event — queryStudioController.ts:743.

Webview (`perfMark`/`perfMarkAfterNextPaint`):

- Boot: index.tsx:17 `boot.scriptStart` (first statement of entry module), index.tsx:24 `boot.reactMount`; app.tsx:705 `boot.monacoReady`, app.tsx:706 `boot.editorInteractive` (afterNextPaint) then `prefetchGridStack()` (app.tsx:707).
- Lazy chunks (src/webviews/pages/QueryStudio/lazyResults.tsx — **the explicit template for new tabs**, header comment :16–19 names spatial/vector): `boot.gridChunkRequested` (:43) on idle prefetch kick; `boot.gridChunkLoaded {waitedForByRender}` (:46) — the honesty attr is set by the Suspense fallback (`ResultsSurfaceLoading` :100–110); `boot.planChunkLoaded` (:95) inside the `React.lazy` loader — fires only on first plan-tab activation.
- Render: app.tsx:637–648 `resultsRendered` — attrs `{status, rows, resultSets}`, gated so it waits for `whenGridStackLoaded()` when results beat the chunk (never marks the placeholder paint, comment :634–636).
- Grid windows: resultsGrid.tsx:609 `grid.window.request`, :624 `grid.window.received {…, ms}` (round trip measured with `performance.now()`), :632 `grid.firstVisibleRowsPainted` (afterNextPaint, once per grid via `firstRowsPaintedRef`).
- Messages: results.tsx:373 `messagesPrepared {messages, visibleRows, durationMs}` (compute measured only when `perfMarksEnabled()`), :383 `messagesRendered` (afterNextPaint). Text view cap: resultsTextView.tsx:118.

---

## 7. Debug Console: where events surface and how to add a panel

Host controller: `src/controllers/debugConsoleWebviewController.ts` (class :119; registered via `registerDebugConsole` :917–931, command `mssql.openDebugConsole`; singleton reveal). The webview is a pure renderer — every query/aggregation runs host-side (header :9).

RPC surface (namespace types in sharedInterfaces/debugConsole.ts:506–819, all `dc/*`): `dc/listSources`, `dc/queryEvents` (`EventQuery` filters: `processes, features, kinds, statuses, traceId, text, fromSeq, limit, beforeSeq, includeViewerInternal, minDurationMs, maxDurationMs` — :227–250), `dc/getOverview`, `dc/getCauseTree`, `dc/getWaterfall`, `dc/listTraces`, `dc/getSqlActivity`, `dc/subscribeLive`, `dc/unsubscribeLive`, `dc/setCaptureMode`, `dc/importPerfRun`, `dc/getPerfSummary`, `dc/backfillGap`, `dc/getHealth`, `dc/getTraceQuality`, `dc/export`, `dc/getHistory`, self-test (`dc/listSelfTestScenarios`, `dc/runSelfTest`, `dc/cancelSelfTest`), central upload, perf-history (`ph*` in sharedInterfaces/perfHistory.ts). Push notifications: `dc/livePush` (batches every ~120 ms), `dc/captureChanged`, `dc/selfTestProgress`.

Webview app: `src/webviews/pages/DebugConsole/`. Routing: `DcPage` union (state.tsx:54–67: `"overview" | "trace" | "waterfall" | "perf" | "history" | "completions" | "replay" | "sql" | "connections" | "query" | "oe" | "exports" | "settings"`), left-rail `NAV` groups (shell.tsx:25–54), page switch in `DebugConsoleApp` (shell.tsx:325–375). Client state provider (`DcProvider`, state.tsx:113) handles live subscription (`LIVE_VIEW_CAP = 20_000` :111), a 1/sec `dataVersion` throttle (:175–194), gap backfill.

**Feature-page pattern** (src/webviews/pages/DebugConsole/pagesMore.tsx): `useFeatureEvents(features: string[])` (:47) issues `dc/queryEvents {features, limit: 2000}` keyed on `dataVersion`; `pairOccurrences(events, beginType, endType)` (:75) pairs chronologically per-trace with monotonic-preferred durations; `OccurrenceTable` (:122) + `occurrenceKpis` (:181, median/p95/errors) render it. Example: `QueryResultsPage` (:365) uses `useFeatureEvents(["query", "resultsGrid"])` and pairs `mssql.query.submit`/`mssql.query.complete`.

**To surface a new pane's events**: nothing is needed for the generic views — Consolidated Trace shows everything; QS markers already land on the "Query & Results" page because the Perf facade buckets `mssql.queryStudio.*` into feature `query` (§3.3). For a dedicated panel: (1) add the id to `DcPage` (state.tsx:54), (2) add a NAV item (shell.tsx:25), (3) add the `case` in `DebugConsoleApp` (shell.tsx:328), (4) write the page with `useFeatureEvents([...])`/`pairOccurrences`. Filter by the exact feature strings your events carry (`query` for Perf-facade markers, `queryStudio` for direct `diag.emit`, `webview.queryStudio` for auto RPC spans).

Overview "Recent user actions" only lists traces containing a `ROOT_LABELS` match (src/diagnostics/analysis.ts:26–58 — `mssql.query.submit`, `mssql.connection.begin`, `mssql.oe.expand.begin`, `command.<id>.begin`, `mssql.command.invoked`, cancel). Waterfall building (analysis.ts:261–406): `.begin`/`.end` pairs keyed `stem@process` with monotonic-ns durations when same-process, `IRREGULAR_END` map for begin/ready & submit/complete (:408–414), `rpc.*` round-trips laned under `sqlToolsService`, own-duration events (STS spans) drawn as bars, `sts.sql.*`/`sts.smo.*` on a `driver` lane, top-6 critical path.

Health: every sink self-reports (`dc/getHealth` → `diag.sinkHealthSnapshot()` + store validation, controller :456–462) — degradation is visible, never silent.

---

## 8. Redaction & capture policy (what your attrs may contain)

`src/diagnostics/redaction.ts` — `classify(raw, cls, policy)` (:97) is the single choke point; redaction happens **before** the envelope exists. Policies (`CAPTURE_POLICIES` :218–255): `policy_off`, `policy_redacted_default` (default), `policy_digest`, `policy_full_elevated` (time-bounded, `allowSqlText`+`allowConnectionDetails` true, `allowRowData` **still false**, secrets never). `NEVER_PLAIN` = secret/connection.string/token (tokenized only); `ALWAYS_PLAIN` = public/system.metadata/diagnostic.metadata/sql.digest/result.shape; name-like classes (`server.name`, `database.name`, `schema.name`, `object.name`, `source.path`) get salted digests under redacted mode (`digestValue`, per-process salt :26–31); free text (`user.text`, `sql.text`, `row.data`, `model.*`) is redacted/omitted. `MAX_PLAIN_LENGTH = 4096`. `RANK_ORDER` (:191) defines classification severity.

**Rule for the panes:** vector/spatial attrs must be counts, dimensions, byte sizes, durations, cache hit/miss, and closed enums — never cell values, geometry coordinates from user data, embedding contents, column names (those are `object.name` → digest), or SQL text. Model the row-pipeline events (`rows.windowFetch.end`, `query.complete`) which carry shape/timing only.

Capture lifecycle (src/diagnostics/diagnosticsManager.ts): settings `mssql.sessionDiag.enabled` (default false), `mssql.sessionDiag.captureMode` (`redacted`|`digest`), `.storePath`, `.maxSessions` 10, `.maxAgeDays` 14, `.maxTotalMB` 512 (package.json:2426–2465). Full capture ONLY via the elevation command `mssql.sessionDiag.elevateCapture` or the console chip — time-bounded (max 60 min), auto-reverts, reason recorded (`sessionDiag.elevated`). Commands: `mssql.sessionDiag.enable/disable/clear/openStorageFolder/elevateCapture` (:194–248). Status-bar item shows capture mode.

---

## 9. The generated observability contract & regeneration workflow

`src/sharedInterfaces/observabilityContract.generated.ts` — header (:6–10): "GENERATED — do not edit. Source of truth: perftest/packages/observability-contracts (npm run generate, then vendor). Registry obs-contract/1."

Source of truth: `C:/repos/test/perftest/packages/observability-contracts/src/registry/event-types.json` (+ `classifications.json`, `timing-classes.json`). Entry shape = `EventTypeEntry` (generated.ts:17–31): `name` XOR `prefix` (prefix = dynamic span family), `kind` (`marker|webviewMark|event|metric|richMetric|spanFamily`), `phase`, **explicit `pairsWith`**, `feature`, `processRoles`, `timingClass`, `measurementEligible`, `attrs` (name→classification), `attrsComplete` (false = known-partial list is tolerated), `notes`, `deprecated`.

**Regeneration workflow** (perftest package README, verbatim steps):
1. Edit the registry JSON in `perftest/packages/observability-contracts/src/registry/`.
2. `npm run build && npm test && npm run generate` in that package (generate = `node dist/generate.js`, emits `generated/markdown/EVENTS.md` + `generated/typescript/observabilityContract.generated.ts`).
3. Copy `generated/typescript/observabilityContract.generated.ts` over `vscode-mssql/extensions/mssql/src/sharedInterfaces/observabilityContract.generated.ts`.
4. Both repos' conformance suites must pass.

Enforcement:
- vscode-mssql: `test/unit/observabilityContract.test.ts` — walks `src/`, extracts every literal in `Perf.marker("…")` and `perfMarkAfterNextPaint("…")`, fails on names `explainEventName()` doesn't know (:39–59). **Note the extraction gap: bare `perfMark("…")` literals are NOT scanned** — register webview mark names anyway (perftest's own conformance and the EVENTS.md doc depend on it, and future regex tightening will catch you).
- perftest: `test/vendorSync.test.ts` regenerates and diffs (whitespace/prettier-normalized) against the vendored copy — registry edits without re-vendor fail CI ("vendored snapshot is STALE…").

Helper APIs in the vendored file: `explainEventName(name)` (exact then longest-prefix match; span family members may carry `.begin/.end` suffixes — :2013–2031), `isKnownMetricName`, `deriveEligibility(input): MetricEligibility` (:2097 — the honesty rules: only marker/productTimer/derived-with-provenance sources, monotonic plane, measurement pass, passed rep, no rich collection, no collector; `ciGatingEligible` additionally requires `environment:"controlledHarness"`; interactive host ⇒ `exploratory`), `lintCorrelation(events)` (:2242).

New pane names to register will include (registry conventions): exact `mssql.queryStudio.<pane>.*` markers/webviewMarks with `pairsWith`, a `queryStudio.<pane>.` **prefix family** for diag spans, and derived metrics with `derivedFrom` pairs.

---

## 10. Recommended instrumentation recipe for a new lazy result pane

Follow the grid/plan precedent exactly (lazyResults.tsx header comment :16–19 explicitly says spatial/vector "follow this exact pattern: cheap `appliesTo` sniffing in the shell, `loader: () => import(...)` on first activation").

1. **Register the vocabulary first** (perftest registry → regen → vendor, §9). Suggested set per pane `<p>` ∈ {`vector`, `spatial`}:
   - webviewMarks: `mssql.queryStudio.boot.<p>ChunkRequested`, `mssql.queryStudio.boot.<p>ChunkLoaded` (attr `waitedForByRender: structuralMetadata`), `mssql.queryStudio.<p>.paneRendered` (attrs: counts/dims only; the user-perceived end — afterNextPaint, double-rAF like `resultsRendered`).
   - extension markers: `mssql.queryStudio.<p>.data.begin/.end` (pairsWith explicit; attrs `resultSetId, rows, bytes, ms, fromSpill, cacheHit` as structuralMetadata) for host-side data preparation.
   - span family prefix: `queryStudio.<p>.` for internal ops (`queryStudio.vector.project`, `queryStudio.spatial.tile` …), `timingClass sameProcessMonotonic`, `measurementEligible false`.
   - derived metrics: `mssql.queryStudio.<p>.activateToRender` from tab-activation begin → paneRendered (epoch plane ⇒ diagnostic outside the harness — that's fine and honest).
2. **Webview side**: dynamic-import module + `React.lazy`; `perfMark` at chunk request and inside the lazy loader on resolution (copy lazyResults.tsx:37–61 & 93–97 including the `waitedForByRender`/Suspense-fallback honesty wiring); `perfMarkAfterNextPaint` for the first real paint, gated to the REAL component paint, never the placeholder (app.tsx:642–648 pattern); wrap per-frame/per-window costs in `if (perfMarksEnabled())` and compute `ms` with `performance.now()` (resultsGrid.tsx:606–638 pattern). Emit a `…capped`-style instant when you refuse work for size (resultsTextView.tsx:118 precedent) — caps must be visible, never silent.
3. **Extension host**: name the pane RPCs `qs/<p>.<op>` — the base controller auto-spans them as `webview.queryStudio.qs/<p>.<op>.begin/.end` (§4.3). Inside heavy handlers use `diag.startSpan({feature:"queryStudio", type:"queryStudio.<p>.<op>", fields:{…, cls:"diagnostic.metadata"}})` with `span.end(status, extraFields)` / `span.fail(error)`. Emit `Perf.marker` pairs only for measurement-grade endpoints you intend the harness to gate on.
4. **Correlation**: markers do NOT auto-join traces (§3.2). Either pass the enclosing span's `traceId` (4th arg of `Perf.marker` — adds tag `perfCorrelation`), or wrap the activation flow in `withRootAction("openVectorPane", "queryStudio", fn)`, or `diag.bindEntityTrace(uriDigest, traceId)` per document. Keep `.begin`/`.end` counts balanced — `dc/getTraceQuality` (lintCorrelation) flags unmatched pairs and orphan ratios.
5. **Privacy**: attrs = counts/bytes/durations/dims/safe enums only; anything name-like goes through `fields` with an honest `cls` so redaction owns it (§8). No embedding values, no coordinates, no cell text, no column names in plain.
6. **Debug Console + session-diag land automatically** once names emit through `diag` — verify by opening the console (live tail + Query & Results page) and by reading `session-diag/sessions/<latest>/events/segment-*.jsonl`. For a dedicated console panel follow §7 (DcPage + NAV + page component with `useFeatureEvents`).
7. **Perf-harness visibility**: `perfMarker`-tagged events and `webview.*`/`rpc.*` spans are forwarded to the harness under PERF_MODE automatically (§1 PerfModeSink); registered names appear in imported waterfalls (importPerfRep pairs `.begin/.end`). The bundle-budget test (`queryStudioBundleBudget.test.ts`, referenced in lazyResults.tsx:21–23) fails the suite if the pane modules re-enter the entry chunk's static closure — keep imports dynamic.
8. **Zero-cost check**: every new call site must be `diag.anySinkActive`/`perfMarksEnabled()`-shaped — no string building, no `performance.now()`, no object allocation on the cold path when nothing listens.

---

## 11. Key identifiers quick-reference

- Settings: `mssql.sessionDiag.enabled|storePath|captureMode|maxSessions|maxAgeDays|maxTotalMB`, `mssql.debugConsole.enabled|perfRunsRoot|richCollection|richSnapshotHeartbeat`, `mssql.centralObservability.enabled` (package.json:2426–2483, 4036).
- Commands: `mssql.openDebugConsole`, `mssql.sessionDiag.enable|disable|elevateCapture|clear|openStorageFolder`; PERF_MODE-only: `mssql.perf.getState|setConfig|gridState|gridFetchWindow|oeSnapshot` (src/perf/perfApi.ts).
- Env: `PERF_MODE`, `PERF_MARKER_URL`, `PERF_CONTROL_TOKEN`, `PERF_RUN_ID`, `PERF_REP_ID`, `PERF_SCENARIO_ID`, `MSSQL_COLLECT_ALL_THE_DATA`, `STS_DIAG_URL`, `STS_DIAG_TOKEN`.
- Wire methods: `perf/enable`, `perf/webviewMark`, `dc/*`, `ph/*`, `qs/*`.
- Schema versions: `mssql.diag.event/1`, `mssql.diag.sessionManifest/1`, `obs-contract/1`.
- Policy ids: `policy_off`, `policy_redacted_default`, `policy_digest`, `policy_full_elevated`.
- Trace/gap/event id shapes: `trace_<hint>_<t36>_<n36>`, `viewer_<sessionId>`, `evt_<seq36 padded 6>`, `gap_live_<n>`, `sess_<stamp>_<pid>`.
