# MSSQL Debug Console Technical Design

**Artifact role:** Engineering design document for implementing the in-product diagnostics substrate and extensible debug UI in `vscode-mssql`, with STS2 and perf harness integration points.

**Related UX spec:** `MSSQL_Debug_Console_UX_Spec.md`

**Last updated:** 2026-07-02

---

## 1. Executive summary

MSSQL Debug Console is a local-first diagnostics system and VS Code webview host for `vscode-mssql`. It unifies existing and planned signals from the extension host, webviews, completions logs, SQL Tools Service, SQL Server, renderer traces, process sampling, and perf harness artifacts into one structured event model.

The same instrumentation points feed multiple sinks:

1. **Perf harness sink:** `PERF_MODE` capture for automated scenarios and regression analysis.
2. **Live-tail sink:** in-memory bounded stream for the in-product debug UI.
3. **Session Diag store:** user-enabled, classified, redacted, local, retained across VS Code sessions.
4. **Export bundle:** coherent, redacted evidence for support or AI coding agents.

The webview UI is an extensible host with page plugins. Built-in pages include Consolidated Trace, Cross-Process Waterfall, Perf & Sessions, Completions, Replay Lab, SQL Activity, Connections, Query & Results, Object Explorer, Exports, and Settings.

The design intentionally separates extension-side work that can proceed now from STS-side capture and replay-drive work that is gated on STS2 hardening around observer isolation, run isolation, capture policy, export coherence, and strict replay semantics.

---

## 2. Goals

### 2.1 Product goals

- Provide a first-party, developer-grade diagnostics console inside VS Code.
- Make end-to-end behavior visible live and historically across sessions.
- Generalize the completions debug pattern across all MSSQL features.
- Support bug-report capture through local, classified, redacted Session Diag data.
- Support performance investigation using shared waterfall, plot, and trend renderers.
- Enable structured evidence handoff to coding agents.
- Enable feature-by-feature replay and matrix experimentation where replay contracts are trustworthy.

### 2.2 Engineering goals

- One instrumentation model with pluggable sinks, not duplicated logging paths.
- Bounded, non-blocking emission on product critical paths.
- Explicit classification and redaction for every potentially sensitive field.
- Durable local store that supports fast historical queries.
- Live-tail protocol with exact gap metadata and backfill from journal/store.
- Cross-tier correlation across VS Code, STS, and SQL Server.
- Clear official vs diagnostic metric separation.
- Shared renderer modules reusable by perf harness reports and in-product webviews.

### 2.3 Non-goals for the first implementation

- No automatic upload of Session Diag data.
- No full-data capture by default.
- No STS-side Session Diag capture until STS2 capture policy and observer isolation are hardened.
- No STS replay-drive until strict replay, run isolation, export coherence, and capture policy are hardened.
- No central/fleet dashboard in this phase.
- No claim of official metric precision from diagnostic collectors.

---

## 3. System architecture

### 3.1 Conceptual architecture

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ vscode-mssql instrumentation points                                           │
│ extension host markers | webview markers | completions events | feature state │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │ DiagnosticEventEnvelope
                                ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ Diagnostics Core                                                             │
│ classification | redaction | correlation | bounded queue | sink routing       │
└──────────────┬───────────────┬────────────────┬──────────────────────────────┘
               │               │                │
               ▼               ▼                ▼
     PERF_MODE sink      Live-tail sink   Session Diag store
     markers.jsonl       bounded ring     JSONL segments + SQLite index
               │               │                │
               │               └──────┬─────────┘
               │                      ▼
               │        MSSQL Debug Console webview host
               │        pages + shared renderers + query API
               │
               ▼
       Perf harness reports
       standalone waterfall + plots

Optional and staged sources:
  STS2 envelope journal → classified events and live-tail checkpoint API
  SQL XEvents → SQL activity artifacts and rollups
  CDP renderer traces → render phases and longest tasks
  process sampler → CPU/memory time series
```

### 3.2 Runtime process map

| Process | Current role | Future role |
|---|---|---|
| VS Code extension host | Primary emission point, diagnostics core, store writer, webview provider | Capture policy host for STS2, replay coordinator |
| Webview renderer | Emits UI and render markers through `postMessage` | Page host for debug UI, reusable renderers |
| SQL Tools Service | External process, currently observed through extension and perf harness | STS2 envelope source, live-tail source, replay-drive target |
| SQL Server | Observed through XEvents in diagnostics runs | Correlated SQL activity source via Application Name or session context |
| Perf harness driver | Automation and official measurement | Producer of importable runs and shared renderer artifacts |

---

## 4. Staging and decision gates

### 4.1 Stage A: extension-side substrate and gated Session Diag

Can proceed without STS2 hardening:

- Diagnostics core in `vscode-mssql`.
- Unified event envelope for extension, webview, and completions events.
- Live-tail sink and local Session Diag store.
- Redaction/classification and storage caps.
- View, clear, and export controls.
- Debug UI host with at least Consolidated Trace, Waterfall, and Completions pages.

### 4.2 Stage B: shared renderers and in-product host

Can proceed using existing perf harness renderer code:

- Page registry.
- Store query API.
- Live and historical views.
- Waterfall over extension/webview events and imported harness artifacts.
- Perf & Sessions over local store and imported perf runs.

### 4.3 Stage C: STS-side Session Diag integration

Requires STS2 hardening:

- Observer isolation using bounded mailboxes and non-blocking `TryWrite` publication.
- Run isolation with one run per directory or run-keyed readers.
- Host capture policy and observer data views.
- Exact live-tail gap metadata and journal checkpoint protocol.
- Export snapshot coherence.

### 4.4 Stage D: feature replay and replay-drive

Requires STS2 and feature adapter hardening:

- Strict replay vs partial replay separation.
- Replay-drive produces new live run with provenance, not pure verify.
- Capture policy applied to source and replay run.
- Feature-specific determinism contracts.
- Replay matrix results tagged and analyzable.

### 4.5 Decisions to keep explicit

- Privacy defaults and allowed capture modes.
- Whether the debug view is internal, experimental, or support-facing.
- Storage format, caps, and retention defaults.
- Feature replay rollout order.
- STS2 sequencing and hardening gates.

---

## 5. Unified diagnostics event model

### 5.1 Design requirements

The event model must:

- Represent instantaneous events, spans, metrics, request/response pairs, SQL activities, renderer phases, and replay provenance.
- Carry stable IDs and correlation across tiers.
- Carry field-level classification.
- Support redacted and digest-only payloads.
- Preserve enough detail for offline analysis and export.
- Be append-friendly and index-friendly.
- Be versioned.

### 5.2 Envelope shape

TypeScript draft:

```ts
export type DiagnosticSchemaVersion = 'mssql.diag.event/1';

export type DiagnosticProcess =
  | 'extensionHost'
  | 'webview'
  | 'renderer'
  | 'sqlToolsService'
  | 'sqlServer'
  | 'harness'
  | 'diagnosticCollector';

export type DiagnosticFeature =
  | 'connection'
  | 'query'
  | 'resultsGrid'
  | 'objectExplorer'
  | 'completions'
  | 'replay'
  | 'sessionDiag'
  | 'perfHarness'
  | 'system';

export type DiagnosticKind =
  | 'event'
  | 'span'
  | 'metric'
  | 'request'
  | 'response'
  | 'sqlActivity'
  | 'renderPhase'
  | 'gap'
  | 'artifact'
  | 'state';

export type DiagnosticStatus =
  | 'ok'
  | 'info'
  | 'warning'
  | 'error'
  | 'blocked'
  | 'partial'
  | 'invalid'
  | 'unknown';

export interface DiagnosticEventEnvelope<TPayload = unknown> {
  schemaVersion: DiagnosticSchemaVersion;
  eventId: string;
  sessionId: string;
  runId?: string;
  seq: number;

  timestampUtc: string;
  time: DiagnosticTime;

  process: DiagnosticProcess;
  processId?: number;
  threadId?: string;
  feature: DiagnosticFeature;
  category: string;
  kind: DiagnosticKind;
  type: string;
  name?: string;
  status: DiagnosticStatus;

  correlation: DiagnosticCorrelation;
  entityRefs?: DiagnosticEntityRef[];
  classification: DiagnosticClassificationSummary;

  durationMs?: number;
  timingClass?: DiagnosticTimingClass;
  confidence?: DiagnosticConfidence;

  payload: ClassifiedPayload<TPayload>;
  metrics?: Record<string, DiagnosticMetricValue>;
  artifacts?: DiagnosticArtifactRef[];
  provenance?: DiagnosticProvenance;
  replay?: DiagnosticReplayProvenance;

  source: DiagnosticSource;
  flags?: string[];
}
```

### 5.3 Time model

```ts
export interface DiagnosticTime {
  epochMs: number;
  monotonicNs?: string;
  timeOriginEpochMs?: number;
  clockId: string;
  calibration?: ClockCalibrationRef;
}

export type DiagnosticTimingClass =
  | 'official.sameProcessMonotonic'
  | 'productTimer'
  | 'diagnostic.epochAligned'
  | 'diagnostic.collector'
  | 'inferred';

export interface ClockCalibrationRef {
  calibrationId: string;
  offsetMs: number;
  roundTripMs: number;
  jitterMs: number;
  sourceClockId: string;
  targetClockId: string;
}
```

Rules:

- Same-process intervals should use monotonic clocks and can be official if other conditions are met.
- Cross-process intervals use epoch alignment and must carry calibration metadata.
- Webview events use `performance.timeOrigin + performance.now()` for epoch alignment.
- Diagnostic collector intervals are never official by default.

### 5.4 Correlation model

```ts
export interface DiagnosticCorrelation {
  traceId: string;
  spanId?: string;
  parentSpanId?: string;
  causeEventId?: string;
  externalTrace?: string;
  stsCorr?: string;
  stsCause?: string;
  sqlApplicationName?: string;
  replayTraceId?: string;
  replayRunId?: string;
  scenarioId?: string;
}
```

Correlation rules:

- Extension creates `traceId` for user actions and feature operations.
- Webviews receive and echo `traceId` through `postMessage` payloads.
- STS requests receive W3C `traceparent` or explicit external correlation where supported.
- SQL Server correlation uses Application Name or session context.
- Replay events carry source and replay IDs.

### 5.5 Entity references

```ts
export interface DiagnosticEntityRef {
  kind:
    | 'connection'
    | 'query'
    | 'resultSet'
    | 'document'
    | 'completionRequest'
    | 'objectExplorerNode'
    | 'sqlCommand'
    | 'session'
    | 'replayRun';
  id: string;
  label?: string;
  classification?: DataClassification;
}
```

### 5.6 Classification model

```ts
export type DataClassification =
  | 'public'
  | 'system.metadata'
  | 'diagnostic.metadata'
  | 'source.path'
  | 'server.name'
  | 'database.name'
  | 'schema.name'
  | 'object.name'
  | 'sql.text'
  | 'sql.digest'
  | 'row.data'
  | 'result.shape'
  | 'secret'
  | 'connection.string'
  | 'token'
  | 'user.text'
  | 'model.prompt'
  | 'model.response'
  | 'unknown';

export interface DiagnosticClassificationSummary {
  maxClassification: DataClassification;
  fields: Record<string, FieldClassification>;
  redactionApplied: boolean;
  policyId: string;
}

export interface FieldClassification {
  classification: DataClassification;
  handling: 'plain' | 'redacted' | 'digest' | 'tokenized' | 'truncated' | 'omitted';
  digest?: string;
  reason?: string;
}
```

### 5.7 Payload model

```ts
export type ClassifiedPayload<T = unknown> = {
  value: T;
  redactions?: RedactionRecord[];
};

export interface RedactionRecord {
  jsonPath: string;
  classification: DataClassification;
  handling: 'redacted' | 'digest' | 'tokenized' | 'truncated' | 'omitted';
  digest?: string;
  originalLength?: number;
  reason: string;
}
```

### 5.8 Example event

```json
{
  "schemaVersion": "mssql.diag.event/1",
  "eventId": "evt_00010430",
  "sessionId": "sess_20260702_140213_devbox",
  "seq": 10430,
  "timestampUtc": "2026-07-02T14:02:41.118Z",
  "time": {
    "epochMs": 1783000961118,
    "monotonicNs": "128391283912839",
    "clockId": "extensionHost:pid=18422"
  },
  "process": "extensionHost",
  "processId": 18422,
  "feature": "query",
  "category": "command",
  "kind": "event",
  "type": "command.mssql.runQuery.begin",
  "status": "ok",
  "correlation": {
    "traceId": "trace_8d3f1a9c_0007",
    "spanId": "span_query_submit"
  },
  "classification": {
    "maxClassification": "diagnostic.metadata",
    "fields": {},
    "redactionApplied": false,
    "policyId": "policy_redacted_default"
  },
  "payload": {
    "value": {
      "documentUriDigest": "uri:sha256:df02...",
      "selectionLine": 42
    }
  },
  "source": {
    "component": "vscode-mssql",
    "version": "dev",
    "commit": "7f3c2b1"
  }
}
```

---

## 6. Instrumentation sources

### 6.1 Extension host markers

Emit from command boundaries, service operations, connection lifecycle, query execution, OE actions, and feature-level state changes.

Initial required markers:

| Feature | Marker |
|---|---|
| extension | `mssql.extension.activate.begin/end` |
| command | `mssql.command.begin/end` |
| connection | `mssql.connection.open.begin`, `mssql.connection.ready`, `mssql.connection.close.begin/end` |
| query | `mssql.query.submit`, `mssql.query.resultReceived`, `mssql.query.complete`, `mssql.query.cancel.begin/end` |
| results grid | `mssql.resultsGrid.dataReceived`, `mssql.resultsGrid.renderComplete`, `mssql.resultsGrid.windowFetch.begin/end` |
| object explorer | `mssql.oe.expand.begin/end`, `mssql.oe.refresh.begin/end`, `mssql.oe.nodeCount` |
| completions | existing completion request/result/telemetry events mapped to unified envelope |
| session diag | `mssql.sessionDiag.enabled`, `mssql.sessionDiag.elevated`, `mssql.sessionDiag.disabled`, `mssql.sessionDiag.export.begin/end` |

### 6.2 Webview markers

Webviews emit events via `postMessage` to the extension host. Each message must include trace context and webview time:

```ts
interface WebviewDiagnosticMessage {
  kind: 'mssql.diagnosticEvent';
  traceId: string;
  eventId?: string;
  type: string;
  feature: DiagnosticFeature;
  timeOriginEpochMs: number;
  nowMs: number;
  payload: unknown;
  classification?: Partial<DiagnosticClassificationSummary>;
}
```

The extension host validates, classifies, redacts, assigns seq, and routes to sinks. Webviews do not write Session Diag directly.

### 6.3 Completions session logs

The existing completions instrumentation captures request parameters, local service state, model responses, telemetry, token usage, latency, result status, and persisted session logs. The migration should add an adapter layer:

```ts
interface CompletionEventAdapter {
  toDiagnosticEnvelope(event: ExistingCompletionEvent): DiagnosticEventEnvelope;
  fromDiagnosticEnvelope?(event: DiagnosticEventEnvelope): ExistingCompletionEvent;
}
```

Requirements:

- Preserve existing completions views during migration.
- Tag migrated events with `source.component = completionsDebug`.
- Keep replay trace IDs and matrix cell IDs in unified provenance.
- Do not regress existing prompt, raw response, sanitized response, schema context, locals, or telemetry tabs.

### 6.4 STS2 envelope journal

STS2 envelopes are the target shape for rich service-side events. Initial in-product implementation should treat STS-side Session Diag as experimental until hardening lands. Imported harness or STS artifacts can be normalized for the UI without enabling normal-use STS capture.

Expected STS integration later:

- `externalTrace` runtime overlay from inbound request.
- `corr`, `cause`, `entityRefs`, and classification carried into the envelope.
- Live-tail subscription with gap metadata.
- Capture policy supplied by VS Code extension host.
- Observer views governed by policy.

### 6.5 SQL Server activity

The perf harness diagnostic collector already models XEvents with command details. In product Session Diag, full SQL text capture is not default. SQL activity can be represented by digests and stats when available.

Fields for SQL activity events:

- event type: rpc completed, batch completed, statement completed, module end.
- duration.
- CPU.
- logical reads.
- physical reads.
- writes.
- row count.
- client app name.
- session ID.
- request ID.
- timestamp.
- SQL digest or text depending on policy.

### 6.6 Renderer traces

CDP renderer traces are diagnostic-only and should not be enabled for normal Session Diag by default. Imported perf runs and diagnostic sessions can include:

- scripting time.
- layout time.
- paint time.
- longest task.
- time from data receive to paint.
- trace artifact references.

### 6.7 Process and memory sampling

Low-cost samples can be captured in measurement contexts and optionally Session Diag if approved by policy:

- extension host heap used/RSS.
- STS working set/RSS if available.
- VS Code main process working set.
- CPU time by role.
- peak summaries.

---

## 7. Diagnostics core in `vscode-mssql`

### 7.1 Responsibilities

The diagnostics core owns:

- Event construction helper APIs.
- Trace context propagation.
- Sequence assignment.
- Classification and redaction.
- Capture policy enforcement.
- Sink registration and routing.
- Bounded queue and drop/gap accounting.
- Store writes.
- Query API for webview.
- Export bundle preparation.

### 7.2 Proposed module layout

```text
src/diagnostics/
  core/
    DiagnosticEventEnvelope.ts
    DiagnosticTypes.ts
    DiagnosticsService.ts
    TraceContext.ts
    Clock.ts
    Sequence.ts
    BoundedEventQueue.ts
  classification/
    Classification.ts
    Redaction.ts
    CapturePolicy.ts
    FieldClassifiers.ts
  sinks/
    DiagnosticSink.ts
    PerfModeSink.ts
    LiveTailSink.ts
    SessionDiagSink.ts
    NullSink.ts
  store/
    SessionDiagStore.ts
    JsonlSegmentWriter.ts
    SqliteIndex.ts
    RetentionManager.ts
    StoreQueryService.ts
  export/
    EvidenceBundleBuilder.ts
    PrivacyReport.ts
    BundleValidator.ts
  webview/
    DebugConsoleWebviewProvider.ts
    DebugConsoleProtocol.ts
  adapters/
    CompletionsAdapter.ts
    PerfHarnessImportAdapter.ts
    StsEnvelopeAdapter.ts
    SqlActivityAdapter.ts
```

### 7.3 Emission APIs

```ts
export interface DiagnosticsService {
  isEnabled(): boolean;
  startSpan(input: StartSpanInput): DiagnosticSpan;
  emitEvent(input: EmitEventInput): void;
  emitMetric(input: EmitMetricInput): void;
  withTrace<T>(trace: TraceContext, fn: () => T): T;
  getCurrentTrace(): TraceContext | undefined;
}

export interface DiagnosticSpan {
  trace: TraceContext;
  end(status?: DiagnosticStatus, payload?: unknown): void;
  fail(error: unknown, payload?: unknown): void;
}
```

Emission must be safe when diagnostics are disabled. With capture off, the service should be a near-zero overhead no-op except for lightweight trace propagation needed by `PERF_MODE`, if active.

### 7.4 Sink interface

```ts
export interface DiagnosticSink {
  readonly id: string;
  readonly accepts: DiagnosticSinkMode[];
  tryWrite(event: DiagnosticEventEnvelope): DiagnosticSinkWriteResult;
  flush?(reason: 'shutdown' | 'export' | 'manual'): Promise<void>;
  dispose?(): Promise<void>;
  health(): DiagnosticSinkHealth;
}

export interface DiagnosticSinkWriteResult {
  accepted: boolean;
  dropped?: boolean;
  reason?: string;
}
```

Rules:

- Product instrumentation never awaits arbitrary sink code on critical paths.
- Sinks that need I/O write through bounded queues.
- Drops are recorded as gap metadata, not silently swallowed.
- Fatal sink failures disable that sink and emit a health event to surviving sinks where safe.

---

## 8. Session Diag store

### 8.1 Recommended storage design

Use a hybrid store:

1. **Append-only JSONL segment journal** as the source of truth.
2. **SQLite index** for fast filtering, grouping, and aggregate queries.
3. **Artifact directory** for large traces, SQL activity files, screenshots, and exports.

This combines durable, stream-friendly writes with fast historical UI queries.

### 8.2 Directory layout

```text
<globalStorageUri>/session-diag/
  store.json
  sessions/
    sess_20260702_140213_devbox/
      manifest.json
      events/
        segment-000001.jsonl
        segment-000002.jsonl
      artifacts/
        renderer.trace.json
        sql-activity.jsonl
        process-samples.jsonl
      privacy-report.json
      index.sqlite
  index.sqlite
  exports/
    mssql-session-20260702-140213.zip
```

### 8.3 Manifest shape

```ts
export interface SessionDiagManifest {
  schemaVersion: 'mssql.diag.sessionManifest/1';
  sessionId: string;
  createdUtc: string;
  updatedUtc: string;
  source: 'live' | 'importedBundle' | 'perfRun' | 'replay';
  capturePolicy: CapturePolicySnapshot;
  retentionPolicy: RetentionPolicySnapshot;
  segments: SegmentManifest[];
  artifacts: DiagnosticArtifactRef[];
  provenance: SessionProvenance;
  privacyReport?: string;
  status: 'active' | 'closed' | 'exported' | 'corrupt' | 'partial';
}
```

### 8.4 SQLite index tables

Keep the JSONL segments authoritative. SQLite is an index and aggregate cache.

```sql
CREATE TABLE sessions (
  session_id TEXT PRIMARY KEY,
  created_utc TEXT NOT NULL,
  updated_utc TEXT NOT NULL,
  source TEXT NOT NULL,
  status TEXT NOT NULL,
  capture_policy_id TEXT NOT NULL,
  provenance_json TEXT NOT NULL
);

CREATE TABLE events (
  session_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  event_id TEXT NOT NULL,
  timestamp_utc TEXT NOT NULL,
  process TEXT NOT NULL,
  feature TEXT NOT NULL,
  kind TEXT NOT NULL,
  type TEXT NOT NULL,
  status TEXT NOT NULL,
  trace_id TEXT,
  corr TEXT,
  cause_event_id TEXT,
  duration_ms REAL,
  timing_class TEXT,
  max_classification TEXT,
  redaction_applied INTEGER NOT NULL,
  segment_path TEXT NOT NULL,
  segment_offset INTEGER,
  PRIMARY KEY (session_id, seq)
);

CREATE INDEX idx_events_trace ON events(session_id, trace_id, seq);
CREATE INDEX idx_events_feature ON events(session_id, feature, timestamp_utc);
CREATE INDEX idx_events_type ON events(session_id, type);
CREATE INDEX idx_events_status ON events(session_id, status);

CREATE TABLE gaps (
  session_id TEXT NOT NULL,
  gap_id TEXT NOT NULL,
  dropped_from_seq INTEGER NOT NULL,
  dropped_through_seq INTEGER NOT NULL,
  recovered INTEGER NOT NULL DEFAULT 0,
  reason TEXT,
  PRIMARY KEY (session_id, gap_id)
);

CREATE TABLE metrics (
  session_id TEXT NOT NULL,
  event_id TEXT NOT NULL,
  metric_name TEXT NOT NULL,
  metric_value REAL NOT NULL,
  unit TEXT NOT NULL,
  official INTEGER NOT NULL,
  confidence TEXT,
  PRIMARY KEY (session_id, event_id, metric_name)
);
```

### 8.5 Retention

Default retention should be conservative and user-visible. Suggested knobs:

- Capture off by default.
- Maximum sessions: configurable, default 10.
- Maximum age: configurable, default 7 or 14 days for internal builds, TBD for shipping.
- Maximum size: configurable, default 250 MB.
- Full capture elevation auto-reverts.
- Clear all action must delete segments, indexes, artifacts, and exports if selected.

### 8.6 Store query API

```ts
export interface StoreQueryService {
  listSessions(filter?: SessionFilter): Promise<SessionSummary[]>;
  queryEvents(query: EventQuery): Promise<EventQueryResult>;
  getEvent(sessionId: string, seqOrEventId: number | string): Promise<DiagnosticEventEnvelope>;
  getCauseTree(sessionId: string, eventId: string): Promise<CauseTree>;
  queryMetrics(query: MetricQuery): Promise<MetricSeriesResult>;
  getArtifacts(sessionId: string, filter?: ArtifactFilter): Promise<DiagnosticArtifactRef[]>;
  backfillGap(sessionId: string, gapId: string): Promise<BackfillResult>;
}
```

---

## 9. Capture policy and redaction

### 9.1 Capture modes

```ts
export type CaptureMode = 'off' | 'redacted' | 'digest' | 'full';

export interface CapturePolicy {
  policyId: string;
  mode: CaptureMode;
  allowSqlText: boolean;
  allowRowData: boolean;
  allowPrompts: boolean;
  allowConnectionDetails: boolean;
  allowSecrets: false;
  maxDurationMs?: number;
  expiresUtc?: string;
  reason?: string;
  actor?: 'user' | 'developer' | 'testHarness';
  scope?: CaptureScope;
}
```

Rules:

- Secrets, tokens, and connection strings are never persisted as plaintext.
- SQL text, row data, schema names, object names, prompts, and responses require explicit classification.
- Full capture is never silently enabled.
- Elevation is time-bounded and session-scoped.
- A client cannot elevate beyond host policy.

### 9.2 Redaction behavior

| Classification | Off | Redacted | Digest | Full |
|---|---|---|---|---|
| Public/system metadata | omitted unless needed | plain | plain | plain |
| Diagnostic metadata | omitted unless needed | plain | plain | plain |
| Server/database/object names | omitted or digest | digest | digest | plain if allowed |
| SQL text | omitted | redacted | digest | plain if allowed |
| Row data | omitted | redacted | digest or shape | plain if allowed |
| Secret/token/connection string | omitted | tokenized or omitted | tokenized or omitted | tokenized or omitted |
| Model prompts/responses | omitted | redacted or sanitized | digest/sanitized | plain if allowed |

### 9.3 Redaction primitives

- **Omitted:** field not stored.
- **Redacted:** placeholder with classification and reason.
- **Digest:** stable digest for equality and grouping, not reversible.
- **Tokenized:** opaque per-run token, not raw hash prefix.
- **Truncated:** capped with original length recorded.

### 9.4 Privacy report

Every export and session should be able to produce a privacy report:

- Capture policy history.
- Count of fields by classification.
- Count of redactions by handling.
- Elevated capture periods and reasons.
- Gaps and unrecovered ranges.
- Artifacts included.
- Warnings.

---

## 10. Live-tail and gap protocol

### 10.1 Requirements

The live view must know exactly when it missed events. Gaps are first-class data.

### 10.2 Live subscription messages

```ts
export type LiveTailMessage =
  | LiveTailHello
  | LiveTailEvent
  | LiveTailGap
  | LiveTailBackfillStarted
  | LiveTailBackfillCompleted
  | LiveTailError
  | LiveTailHeartbeat;

export interface LiveTailHello {
  type: 'hello';
  sessionId: string;
  firstAvailableSeq: number;
  lastDeliveredSeq: number;
  currentCheckpoint?: JournalCheckpoint;
}

export interface LiveTailEvent {
  type: 'event';
  event: DiagnosticEventEnvelope;
}

export interface LiveTailGap {
  type: 'gap';
  gapId: string;
  sessionId: string;
  droppedFromSeq: number;
  droppedThroughSeq: number;
  droppedCount: number;
  reason: 'subscriberOverflow' | 'sinkOverflow' | 'journalUnavailable' | 'sourceGap';
  currentCheckpoint?: JournalCheckpoint;
}
```

### 10.3 Backfill flow

1. UI receives `LiveTailGap`.
2. UI renders gap marker row.
3. User clicks backfill or global backfill runs.
4. Store reads JSONL range by seq.
5. UI inserts recovered events at original positions.
6. Store marks gap recovered.
7. If range is unavailable, UI leaves gap marker with failure reason.

### 10.4 Ring buffer behavior

- Live tail uses a bounded ring buffer.
- Overflow drops oldest events and emits a gap marker.
- If even the gap marker cannot be delivered, next heartbeat reports missed count and range where possible.
- Dropping a diagnostic live event does not delete it from Session Diag store if store write succeeded.

---

## 11. Cross-process waterfall design

### 11.1 Input data

Waterfall renderer consumes normalized activities:

```ts
export interface TimelineActivity {
  id: string;
  sessionId: string;
  traceId: string;
  lane: TimelineLane;
  label: string;
  startEpochMs: number;
  endEpochMs?: number;
  durationMs?: number;
  timingClass: DiagnosticTimingClass;
  confidence?: DiagnosticConfidence;
  status: DiagnosticStatus;
  sourceEventIds: string[];
  causeEventId?: string;
  childEventIds?: string[];
  metrics?: Record<string, DiagnosticMetricValue>;
  classification?: DiagnosticClassificationSummary;
}
```

### 11.2 Lane grouping

Default lanes:

- User action.
- Extension Host.
- Webview / Renderer.
- SQL Tools Service.
- Driver / network.
- SQL Server.
- Process samples.
- Diagnostic collectors.

### 11.3 Activity extraction

The renderer receives activities from:

- Paired span start/end events.
- Single events with duration.
- SQL activity events.
- Renderer trace phases.
- Process sample ranges.
- Harness run artifacts.
- Derived intervals.

### 11.4 Timing honesty

Waterfall renderer must show:

- solid bars for same-process monotonic intervals.
- hatched bars for cross-process aligned intervals.
- dotted outline for inferred intervals.
- calibration jitter in legend.
- confidence labels on derived metrics.

### 11.5 Critical path computation

Initial critical path can be simple:

- Group by trace ID.
- Build DAG from cause relationships.
- Sort by start/end time.
- Select longest chain from root action to terminal user-visible completion.
- Mark overlaps as concurrent, not serial.

Critical path must degrade gracefully when cause relationships are missing.

---

## 12. Webview host architecture

### 12.1 Extension side

`DebugConsoleWebviewProvider` responsibilities:

- Register command `mssql.openDebugConsole`.
- Create webview with strict CSP.
- Serve static assets from extension bundle.
- Provide typed message protocol to webview.
- Bridge StoreQueryService.
- Bridge live-tail subscription.
- Bridge export and capture policy actions.

### 12.2 Webview side

Use the existing extension frontend stack if available. Required modules:

```text
webview/debugConsole/
  app/
    DebugConsoleApp.tsx
    routes.ts
    state.ts
  components/
    AppShell.tsx
    CaptureChip.tsx
    EventTable.tsx
    DetailPane.tsx
    Waterfall.tsx
    MetricCharts.tsx
    RedactedField.tsx
    ExportModal.tsx
  pages/
    OverviewPage.tsx
    TracePage.tsx
    WaterfallPage.tsx
    PerfSessionsPage.tsx
    CompletionsPage.tsx
    ReplayLabPage.tsx
    SqlActivityPage.tsx
    ConnectionsPage.tsx
    QueryResultsPage.tsx
    ObjectExplorerPage.tsx
    ExportsPage.tsx
    SettingsPage.tsx
  protocol/
    messages.ts
```

### 12.3 Webview message protocol

```ts
export type DebugConsoleRequest =
  | { type: 'listSessions'; filter?: SessionFilter }
  | { type: 'queryEvents'; query: EventQuery }
  | { type: 'getEvent'; sessionId: string; eventId: string }
  | { type: 'getCauseTree'; sessionId: string; eventId: string }
  | { type: 'subscribeLive'; sessionId?: string }
  | { type: 'unsubscribeLive'; subscriptionId: string }
  | { type: 'backfillGap'; sessionId: string; gapId: string }
  | { type: 'setCaptureMode'; request: CaptureModeChangeRequest }
  | { type: 'exportBundle'; request: ExportBundleRequest }
  | { type: 'startReplay'; request: ReplayRunRequest };
```

### 12.4 Page registry

```ts
export interface DebugConsolePageContribution {
  id: string;
  title: string;
  icon: string;
  order: number;
  requiredCapabilities?: string[];
  route: string;
  component: React.ComponentType<DebugConsolePageProps>;
}

export interface DebugConsolePageProps {
  session: SessionSummary | undefined;
  query: StoreQueryClient;
  live: LiveTailClient;
  actions: DebugConsoleActions;
}
```

Feature pages register with the host rather than each building a standalone webview.

---

## 13. Shared renderer modules

### 13.1 Goal

Use one renderer implementation for:

- perf harness standalone HTML reports.
- in-product Waterfall page.
- in-product Perf & Sessions charts.
- export bundle offline HTML.

### 13.2 Package shape

If code is shared across repos, make it framework-light and data-driven:

```text
packages/mssql-diagnostics-renderers/
  src/
    timeline/
      TimelineTypes.ts
      normalizeActivities.ts
      renderSvgTimeline.ts
      interactions.ts
    charts/
      histogram.ts
      boxPlot.ts
      trend.ts
      deltaBars.ts
      stackedTimeSplit.ts
      gantt.ts
    tables/
      virtualizedRows.ts
      columns.ts
    index.ts
```

### 13.3 Renderer constraints

- No external network assets.
- Deterministic SVG output for reports.
- Themeable using tokens.
- Accessible labels.
- Can render without React for static reports.
- Can render interactively inside React webview.

---

## 14. Replay design

### 14.1 Replay types

There are two distinct concepts:

1. **Strict replay/verify:** forensic validation of a journal. No live DB effects.
2. **Replay-drive:** re-submit captured external inputs to live product/STS with optional overrides, producing a new run with provenance.

The UI Replay Lab is replay-drive. It must not claim strict verify semantics.

### 14.2 Replay adapter interface

```ts
export interface FeatureReplayAdapter {
  readonly feature: DiagnosticFeature;
  canReplay(event: DiagnosticEventEnvelope): ReplayEligibility;
  buildReplayInput(event: DiagnosticEventEnvelope, options: ReplayBuildOptions): Promise<ReplayInput>;
  runReplay(input: ReplayInput, context: ReplayRunContext): Promise<ReplayResult>;
  estimateCost(inputs: ReplayInput[], matrix: ReplayMatrix): ReplayEstimate;
}

export interface ReplayEligibility {
  eligible: boolean;
  reason?: string;
  requiredCapture?: DataClassification[];
  safety: 'safe' | 'needsUserApproval' | 'blocked';
}
```

### 14.3 Replay provenance

Every replay event must carry:

- source session ID.
- source event IDs.
- replay trace ID.
- replay run ID.
- matrix cell ID.
- overrides.
- adapter version.
- capture policy snapshot.

### 14.4 Initial adapters

| Feature | Stage | Notes |
|---|---|---|
| Completions | first | Existing replay model already established |
| Query | gated | Requires deterministic fixture or STS replay-drive hardening |
| Connection | gated | Requires safe target and deterministic profile handling |
| Object Explorer | future | Depends on deterministic catalog fixture or replay-drive |
| Results Grid rendering | future | Can replay UI data snapshots if captured safely |

---

## 15. Commands and settings

### 15.1 Commands

| Command | Purpose |
|---|---|
| `mssql.openDebugConsole` | Open console |
| `mssql.sessionDiag.enable` | Enable default redacted capture |
| `mssql.sessionDiag.disable` | Disable capture |
| `mssql.sessionDiag.elevateCapture` | Start time-bounded elevation |
| `mssql.sessionDiag.clear` | Clear local store |
| `mssql.sessionDiag.export` | Export evidence bundle |
| `mssql.sessionDiag.openStorageFolder` | Open local store folder |
| `mssql.debugConsole.importBundle` | Import evidence bundle |
| `mssql.debugConsole.startReplay` | Start replay from selection |

### 15.2 Settings

```json
{
  "mssql.sessionDiag.enabled": false,
  "mssql.sessionDiag.captureMode": "redacted",
  "mssql.sessionDiag.maxSessions": 10,
  "mssql.sessionDiag.maxAgeDays": 14,
  "mssql.sessionDiag.maxSizeMb": 250,
  "mssql.sessionDiag.allowElevatedCapture": false,
  "mssql.debugConsole.enabled": true,
  "mssql.debugConsole.experimental.sts2Source": false,
  "mssql.debugConsole.experimental.replayLab": false
}
```

Privacy-sensitive defaults are product decisions and should be finalized with owner sign-off.

---

## 16. Evidence bundle design

### 16.1 Bundle contents

```text
mssql-session-bundle.zip
  manifest.json
  privacy-report.json
  sessions/
    <sessionId>/events/*.jsonl
    <sessionId>/artifacts/*
  index.sqlite
  schemas/*.schema.json
  provenance.json
  validation.json
  README.md
```

### 16.2 Manifest requirements

- Exact session IDs included.
- Capture policy snapshots.
- Redaction policy.
- Gap report.
- Artifact inventory.
- Hashes for all files.
- Export tool version.
- VS Code and extension versions.

### 16.3 Validation checks

- Schema validation.
- Segment sequence continuity or explicit gaps.
- Redaction scan for known sensitive classes.
- Manifest hash verification.
- Policy compliance.
- Artifact existence.
- No external fetch needed for offline HTML.

---

## 17. Integration with perf harness

### 17.1 Import perf runs

The debug console should be able to import or open perf harness run directories and map artifacts into the same store/query model.

Supported artifacts:

- `result.json`.
- `markers.jsonl`.
- `sql-activity.jsonl`.
- `renderer.trace.json`.
- `process-samples.jsonl`.
- `soak-iterations.jsonl`.
- static reports.

### 17.2 Official vs diagnostic metric display

UI should show official status explicitly:

```ts
interface DiagnosticMetricValue {
  value: number;
  unit: string;
  official: boolean;
  source: 'productTimer' | 'marker' | 'sqlXEvents' | 'cdp' | 'processSampler' | 'derived';
  confidence?: DiagnosticConfidence;
  derivation?: string;
}
```

### 17.3 Harness visual patterns to reuse

- KPI grid.
- Filterable errors table.
- Time split stacked bars.
- Small multiples.
- Trace waterfall with phase totals side panel.
- Tool/step explorer.
- Slowest steps table.
- Latency strip.
- Wall-clock Gantt.
- Aggregate pivot.
- Tool cost and behavior table.
- Expected outcome misses.
- Server detail and artifact links.

---

## 18. STS2 integration requirements

### 18.1 Hardening gates

Do not enable STS-side normal-use capture or STS-backed replay until these areas are implemented or explicitly accepted:

- Observer isolation with bounded mailboxes.
- Exact live-tail gap ranges and checkpoints.
- One run per directory or run-keyed reader.
- Host capture policy.
- Observer data views.
- Strict replay vs partial replay separation.
- Coherent export snapshots.
- Sensitive lifetime cleanup.
- Exact-run export and validation.

### 18.2 Cross-tier correlation

STS should accept external correlation from the extension and stamp it as runtime-only overlay. It should propagate into SQL path using Application Name or session context where safe. Result:

```text
extension traceId ↔ STS externalTrace/corr/cause ↔ SQL Application Name
```

### 18.3 Shared schema

STS envelope schema and classification enum should be versioned and copied or packaged as a shared contract. The extension-side DiagnosticEventEnvelope should align with STS envelope concepts:

- kind.
- type.
- corr/cause.
- entityRefs.
- classification.
- runtimeOnly overlays.
- payload digests.

---

## 19. Performance and reliability constraints

### 19.1 Emission budget

- Disabled diagnostics: near no-op, no allocations beyond guarded fast path where possible.
- Redacted Session Diag: bounded queue, non-blocking writes.
- Full capture: explicit elevation, time-bounded, visible, still bounded.
- Webview live rendering: virtualized tables and throttled updates.

### 19.2 Batching

Store writes should batch events:

- flush on lifecycle boundaries.
- flush before export snapshots.
- flush on session close.
- periodic flush while active.
- bounded memory queue.

### 19.3 Failure handling

If a sink fails:

- disable failing sink.
- emit health event to surviving sinks if safe.
- surface status in Debug Console.
- do not block product operations.

If store corrupts:

- mark session partial/corrupt.
- preserve raw segments.
- allow export of corruption evidence.
- do not silently delete.

---

## 20. Security and privacy threat model

### 20.1 Sensitive data classes

- Passwords and tokens.
- Connection strings.
- SQL text.
- Result row values.
- Server, database, schema, and object names.
- User prompts and model responses.
- File paths.

### 20.2 Threats

| Threat | Mitigation |
|---|---|
| Accidental capture of secrets | classifiers, redaction, no plaintext secret persistence |
| Silent full capture | explicit user action, time bound, top-bar visibility |
| Export includes unsafe data | privacy report, redaction scan, manifest validation |
| Custom observer stalls product | non-blocking sink queues and health isolation |
| Replay uses digest-only data unsafely | adapter eligibility and policy checks |
| Webview XSS through payload data | strict CSP, escaping, no raw HTML rendering |
| Store grows unbounded | retention manager and storage cap |
| Low-entropy secret digest attack | opaque tokens or keyed HMAC, no raw hash prefix |

### 20.3 CSP requirements

Webview must use strict CSP:

- no inline scripts unless nonce.
- no remote sources.
- no eval.
- local extension resources only.
- sanitize all payloads before display.

---

## 21. Implementation plan

### Phase 0: design and owner decisions

- Finalize privacy defaults.
- Finalize internal vs shipped behavior.
- Choose store caps and location.
- Confirm feature replay order.
- Record STS2 gating decisions.

### Phase 1: diagnostics core

- Add DiagnosticEventEnvelope types.
- Add DiagnosticsService with no-op and enabled modes.
- Add trace context propagation.
- Add classifiers and redactors.
- Add PerfModeSink adapter if existing harness sink exists.
- Add LiveTailSink.
- Unit tests for classification and redaction.

### Phase 2: Session Diag store

- JSONL segment writer.
- SQLite index.
- retention manager.
- store query service.
- capture settings.
- view/clear/export commands.
- tests for capture off, capture on, redaction, retention.

### Phase 3: webview host and first pages

- Add DebugConsoleWebviewProvider.
- Add app shell, capture chip, session selector.
- Add Consolidated Trace page.
- Add detail pane.
- Add gap/backfill UI.

### Phase 4: waterfall and shared renderers

- Port or package timeline renderer.
- Normalize events to timeline activities.
- Add Waterfall page.
- Add official vs diagnostic styling.
- Add calibration display.

### Phase 5: completions migration

- Add adapter for existing completions events.
- Re-house live trace and multi-session analysis in host.
- Preserve existing tabs and replay tags.
- Add compatibility tests.

### Phase 6: Perf & Sessions and SQL Activity

- Add metrics query service.
- Add distributions, trends, deltas.
- Add SQL activity import/normalization.
- Add process and renderer artifact import.

### Phase 7: Replay Lab

- Add replay trace builder.
- Add completions replay adapter first.
- Add matrix UI.
- Add provenance tags and analysis filters.
- Gate STS-backed replay adapters.

### Phase 8: export and evidence bundles

- Add bundle builder.
- Add privacy report.
- Add validation.
- Add import bundle path.
- Add offline report renderer.

### Phase 9: STS2 integration

- After gates: consume STS2 live-tail checkpoint API.
- Apply host capture policy.
- Normalize STS envelopes into Session Diag store.
- Add STS-backed replay-drive where allowed.

---

## 22. Testing strategy

### 22.1 Unit tests

- Event envelope validation.
- Classification and redaction.
- Capture policy transitions.
- Trace context propagation.
- Sink routing.
- Store indexing.
- Gap detection.
- Renderer normalization.
- Replay eligibility.

### 22.2 Integration tests

- With capture off, use extension and assert no Session Diag files are created.
- With redacted capture on, connect/query and assert events persisted with redactions.
- Webview marker postMessage to store path.
- Live-tail overflow emits exact gap.
- Backfill recovers from JSONL segments.
- Export bundle validates.
- Completions event adapter preserves details.

### 22.3 End-to-end tests

- Open Debug Console, enable redacted capture, run query, view trace.
- Run query and open Waterfall with extension and webview lanes.
- Import perf run and display SQL activity and renderer trace.
- Create completion replay matrix and verify replay tags appear.
- Clear local diagnostics and verify files/index removed.

### 22.4 Security tests

- Secret canaries in connection strings, SQL comments, row values, server messages, prompts.
- Export scan rejects unsafe bundle.
- CSP test for payload with HTML/script.
- No full capture without explicit policy.
- Opaque token tests for secrets.

### 22.5 Performance tests

- Emission overhead microbenchmarks.
- Store write throughput with 100k events.
- Webview table virtualization with 100k rows.
- Backfill large gap.
- Export large session.

---

## 23. Acceptance criteria

### 23.1 Substrate acceptance

- Diagnostics disabled by default produces no Session Diag store and minimal overhead.
- Redacted Session Diag persists extension, webview, query, connection, OE, and completions events across sessions.
- Every payload field with potential sensitivity is classified and redacted/digested according to policy.
- Live-tail gaps are exact and backfillable.
- Store retention enforces configured caps.

### 23.2 UI acceptance

- Debug Console opens from VS Code command.
- Global top bar shows session selector, live/history, capture chip, search, gap count, export.
- Consolidated Trace renders live and historical events with detail pane.
- Waterfall renders one user action across at least extension host and webview, and supports imported STS/SQL lanes.
- Perf & Sessions renders at least one trend and one distribution from imported or stored metrics.
- Completions page is available in the host.
- Replay Lab supports completions replay trace builder and matrix UI.

### 23.3 Privacy acceptance

- Capture is off by default unless owner decides otherwise.
- Full capture requires explicit time-bounded elevation.
- Export includes privacy report.
- Clear action removes local store.
- Secrets and connection strings never persist as plaintext.

### 23.4 Engineering acceptance

- TypeScript strict compile passes.
- Unit and E2E tests cover capture off/on/redaction/export.
- Renderers are shared or designed to be shared with harness reports.
- STS-backed features remain gated until hardening criteria are met.
- Documentation includes known limitations and open decisions.

---

## 24. Open questions

1. Should default Session Diag be off or redacted-on for internal builds only?
2. Should SQLite be one global index plus per-session index, or only global?
3. What are the exact retention defaults for preview, internal, and shipping builds?
4. Which fields from completions prompts/responses are classified as `model.prompt`, `user.text`, or `sql.text`?
5. Which feature owns Query replay first, if any?
6. Will STS2 export bundle format become the canonical support bundle format?
7. Should perf harness run directories be imported in place or copied into Session Diag store?
8. Which pages are hidden behind experimental flags for first release?
9. What is the naming: MSSQL Debug Console, MSSQL Diagnostics, Session Diagnostics, or another name?

---

## 25. Appendix: mapping UX pages to data sources

| Page | Extension events | Webview events | STS events | SQL activity | Renderer trace | Process samples | Replay provenance |
|---|---|---|---|---|---|---|---|
| Overview | yes | yes | imported/gated | imported/gated | imported/gated | yes | yes |
| Consolidated Trace | yes | yes | imported/gated | yes | yes | yes | yes |
| Waterfall | yes | yes | imported/gated | yes | yes | yes | yes |
| Perf & Sessions | yes | yes | imported/gated | yes | yes | yes | yes |
| Completions | yes | optional | no | no | no | optional | yes |
| Replay Lab | yes | optional | gated | optional | optional | no | yes |
| SQL Activity | optional | no | optional | yes | no | no | yes |
| Connections | yes | no | gated | optional | no | yes | future |
| Query & Results | yes | yes | gated | yes | yes | yes | future |
| Object Explorer | yes | yes | gated | yes | yes | yes | future |
| Exports | yes | yes | yes if present | yes if present | yes if present | yes if present | yes |

