# SQL Connection/Query Adapter — Technical Design, reviewed v2
## STS2-first data-plane abstraction with swappable backend bindings

**Component:** `src/services/sqlDataPlane/` plus `src/services/sts2/` binding modules in vscode-mssql.  
**Serves:** Query Studio, MetadataService, query replay/perftest, future v2-native features.  
**Backends:** STS2 JSON-RPC/stdio first; STS2 HTTP/WebSocket later; hosted REST-style query backends where STS2 semantics are fronted by another service.  
**Status:** proposed design, reviewed and made stricter around backend abstraction, result value semantics, liveness, and conformance.

---

## 0. Why this document changed

The original adapter design did a good job shielding features from STS2 JSON-RPC and modeling streaming/backpressure. The main review correction is terminology and layering:

- A **transport** is bytes: stdio JSON-RPC, HTTP, WebSocket.
- A **backend binding** is semantics: open session, execute, stream rows, cancel, close, messages, plans, capture, capabilities.
- A **domain adapter** is what product features import.

The user's architecture goal is broader than “STS2 over two transports.” Query Studio and MetadataService need to talk to **connection/query semantics** that can be backed by STS2 stdio today, STS2 HTTP later, and possibly Azure Portal or VS Code web-hosted REST adapters that expose equivalent semantics. This design therefore defines a domain API plus conformance requirements that every backend binding must satisfy or explicitly mark unsupported.

The one rule remains: **features program against SQL session/query semantics, never against a wire method.**

---

## 1. Goals and non-goals

### 1.1 Goals

- Open, close, and monitor SQL sessions.
- Execute a batch and stream results/messages/plans to a consumer with clear terminal semantics.
- Preserve ordering, backpressure, cancellation, and liveness across backend implementations.
- Normalize errors and server messages.
- Provide capabilities so features can degrade honestly.
- Keep SQL text, result data, secrets, and tokens out of diagnostics by default.
- Expose precise hooks for Query Studio markers, replay descriptors, perftest, and Debug Console waterfalls.
- Keep core domain code isomorphic enough for web-hosted clients when possible.
- Reuse one conformance suite across STS2 stdio, STS2 HTTP, fake bindings, and any future REST bridge.

### 1.2 Non-goals

- Not a UI connection dialog. Existing connection UI produces profiles; this adapter opens them.
- Not a result-grid cache. Query Studio RowStore owns random access and spill.
- Not a language service transport. STS v1 LSP remains separate until a metadata-native LSP exists.
- Not an automatic v1 execution fallback. Features decide fallback before starting v2 work.
- Not an auth UX. Token and credential providers are injected.
- Not a service-side replay engine. It records descriptors and correlation; STS2 owns server journal replay.

---

## 2. Layering

```text
Feature code
 Query Studio · MetadataService · replay runner · future features
        │
        │ imports only src/services/sqlDataPlane/api.ts
        ▼
┌───────────────────────────────────────────────────────────────────────┐
│ SQL Data Plane Adapter                                                 │
│  ISqlConnectionService · ISqlSession · execute() · QueryHandle         │
│  capabilities · errors · event sinks · priority queue · instrumentation │
└───────────────────────────────▲───────────────────────────────────────┘
                                │ backend-binding port
┌───────────────────────────────┴───────────────────────────────────────┐
│ Backend bindings                                                        │
│  Sts2JsonRpcBackend · Sts2HttpBackend · HostedRestBackend · FakeBackend │
└───────────────▲─────────────────────────────▲─────────────────────────┘
                │ transport                    │ transport/protocol
┌───────────────┴───────────────┐   ┌─────────┴────────────────────────┐
│ JSON-RPC over StdioMultiplexer │   │ fetch + WebSocket / HTTPS REST    │
└───────────────────────────────┘   └──────────────────────────────────┘
```

Import rule:

- Product features import `sqlDataPlane/api.ts` only.
- STS2-specific DTOs live under `sts2/wire/` and never leak into Query Studio or MetadataService types.
- Bindings translate backend semantics into the domain contract.

---

## 3. Semantic contract every backend must honor

A backend binding must either provide these semantics or return capabilities that let a feature opt out.

| Semantic | Requirement |
|---|---|
| Session identity | Stable adapter-local `sessionId`, server/backend `connectionId`, `SessionInfo` with database/version/encryption/SPID when available. |
| One active query | At most one active query per session unless capability says otherwise. Adapter queue enforces one-active for STS2. |
| Ordered events | Result-set metadata precedes rows; rows are gapless and ordered per result set; messages are delivered in backend order. |
| Terminality | Every accepted query produces exactly one completion outcome to the feature, even if the backend fails and the adapter must synthesize it. |
| Backpressure | A row page is acknowledged or requested only after the sink durably accepts it, when backend supports streaming credit. If backend cannot backpressure, capability must say so and the binding must bound memory locally. |
| Cancellation | `cancel()` has a bounded request acknowledgment; query terminal completion is still separate. |
| Close | `close()` is idempotent and bounded from the feature's perspective. |
| Data classification | Diagnostics contain metadata only by default. SQL text/result rows/secrets never enter adapter events. |
| Error normalization | Infrastructure failures throw/complete as `SqlDataPlaneError`; server batch errors are query results/messages, not transport exceptions. |
| Capability honesty | Unsupported plan/capture/backpressure/typed-values/resume behaviors are explicit. |

If a binding cannot guarantee ordered push, it must reconstruct order before invoking the sink. If it cannot reconstruct order, it must fail the query rather than show wrong data.

---

## 4. Domain API

### 4.1 Service and session factory

```ts
export interface ISqlConnectionService {
  readonly availability: DataPlaneAvailability;
  readonly onDidChangeAvailability: Event<DataPlaneAvailability>;
  readonly backendInfo?: BackendInfo;

  openSession(params: OpenSessionParams): Promise<ISqlSession>;
  canOpen(params: OpenSessionParams): Promise<CapabilityCheck>;
}

export type DataPlaneAvailability =
  | { state: "unknown" }
  | { state: "available"; backend: string; capabilities: SqlBackendCapabilities }
  | { state: "unavailable"; backend: string; reason: string; retryable: boolean };

export interface OpenSessionParams {
  profile: SqlConnectionProfileRef;
  database?: string;
  applicationName: string;
  openTimeoutMs?: number;
  requestedCapabilities?: Partial<SqlBackendCapabilities>;
  auth?: AuthProviderBundle;
}
```

`SqlConnectionProfileRef` contains sanitized connection metadata and references to secrets/token providers. It must not store raw passwords or tokens.

### 4.2 Session

```ts
export interface ISqlSession extends Disposable {
  readonly sessionId: string;          // adapter-local
  readonly connectionId: string;       // backend-assigned when available
  readonly info: SessionInfo;
  readonly capabilities: SqlBackendCapabilities;
  readonly state: "open" | "closing" | "closed" | "lost";

  readonly onDidChangeState: Event<SessionStateChange>;
  readonly onDidChangeDatabase: Event<DatabaseContextChange>;
  readonly onServerInfoMessage: Event<ServerMessage>;

  execute(text: string, opts: ExecuteOptions, sink: IQueryEventSink): QueryHandle;
  close(opts?: CloseOptions): Promise<void>;
}

export interface SessionInfo {
  serverDisplayName?: string;
  serverVersion?: string;
  engineEdition?: string;
  database?: string;
  loginName?: string;
  spid?: number;
  encrypted?: boolean;
  trustServerCertificate?: boolean;
  backendKind: string;
}
```

### 4.3 Execute and query handle

```ts
export interface ExecuteOptions {
  pageRows?: number;
  pageBytes?: number;
  maxCellBytes?: number;
  priority?: "interactive" | "background";
  tag?: string;                       // diag/replay label, metadata only
  commandKind?: "user" | "metadata" | "plan" | "parse" | "replay";
  timeoutMs?: number;
  expectedDatabase?: string;
  catalogGeneration?: number;
}

export interface QueryHandle {
  readonly clientQueryId: string;
  readonly backendQueryId?: Promise<string>;
  readonly completion: Promise<QueryCompleteSummary>;

  cancel(): Promise<CancelAck>;
  dispose(): Promise<void>;
}
```

`completion` always settles. This is the feature-level liveness floor. A synthesized terminal must be marked as synthesized and produce diagnostics.

### 4.4 Event sink

```ts
export interface IQueryEventSink {
  onAccepted?(info: QueryAccepted): void | Promise<void>;
  onResultSetStarted(meta: ResultSetMetadata): void | Promise<void>;
  onRowsPage(page: RowsPage): void | Promise<void>;
  onMessage(msg: ServerMessage): void | Promise<void>;
  onResultSetEnded?(info: ResultSetEnded): void | Promise<void>;
  onPlan?(plan: PlanPayload): void | Promise<void>;
  onComplete(summary: QueryCompleteSummary): void | Promise<void>;
}
```

Sink contract:

- Sink callbacks for one query are serialized.
- `onRowsPage` promise resolution means the consumer has durably accepted the page. STS2 acks only after that.
- If the sink throws, the adapter cancels/fails the query locally with `SqlDataPlane.Client.SinkError` and marks any partial result as not trustworthy.
- The adapter must not keep calling a failed sink.

---

## 5. Result and value model

The first design used `unknown[][]`. That is convenient but too vague for a query tool. Query Studio needs typed display, copy, save, NULL styling, truncation, binary/XML handling, and future plan detection.

### 5.1 Result metadata

```ts
export interface ResultSetMetadata {
  resultSetId: string;
  batchOrdinal: number;
  statementOrdinal?: number;
  columns: readonly ColumnMetadata[];
  isPlanResult?: boolean;
}

export interface ColumnMetadata {
  ordinal: number;
  name: string;
  displayName: string;
  sqlType?: string;
  providerType?: string;
  allowNull?: boolean;
  precision?: number;
  scale?: number;
  maxLength?: number;
  isKey?: boolean;
  isXml?: boolean;
  isJson?: boolean;
}
```

### 5.2 Cell values

```ts
export type CellValue =
  | { kind: "null" }
  | { kind: "string"; value: string; truncated?: TruncationInfo }
  | { kind: "number"; value: number | string; exact?: boolean }
  | { kind: "boolean"; value: boolean }
  | { kind: "datetime"; iso?: string; display: string }
  | { kind: "binary"; base64?: string; hexPrefix?: string; byteLength?: number; truncated?: TruncationInfo }
  | { kind: "xml" | "json"; value: string; truncated?: TruncationInfo }
  | { kind: "unsupported"; display: string; typeName?: string };

export interface TruncationInfo {
  originalBytes?: number;
  digest?: string;
  reason: "maxCellBytes" | "backendLimit" | "displayLimit";
}
```

The binding should preserve enough type information for display and export without putting raw data into diagnostics. `RowsPage.approxBytes` is metadata and may be logged.

### 5.3 Rows page

```ts
export interface RowsPage {
  resultSetId: string;
  pageSeq: number;
  rowOffset: number;
  rows: readonly (readonly CellValue[])[];
  approxBytes: number;
  complete?: boolean;
}
```

---

## 6. Capabilities

```ts
export interface SqlBackendCapabilities {
  protocolVersion?: string;
  streamingRows: boolean;
  creditBackpressure: boolean;
  cancel: boolean;
  dispose: boolean;
  oneActiveQueryPerSession: boolean;
  multipleResultSets: boolean;
  serverMessagesVerbatim: boolean;
  rowsAffectedStructured: boolean;
  executionPlanXml: boolean;
  estimatedPlan: boolean;
  actualPlan: boolean;
  typedCells: boolean;
  maxCellBytesHonored: boolean;
  pageBytesHonored: boolean;
  captureControl: boolean;
  replayDescriptors: boolean;
  resumeAfterDisconnect: boolean;
  metadataEndpoints?: boolean;
}
```

Query Studio v1 requires:

- streaming rows or bounded local buffering;
- cancel;
- multiple result sets;
- server messages verbatim enough for Messages parity;
- typed cells at least for NULL/string/number/datetime/binary;
- either structured rows affected or messages that include row counts;
- plan XML support for estimated/actual plans, or plan controls disabled with tooltip.

---

## 7. Backend-binding port

```ts
export interface ISqlBackendBinding extends Disposable {
  readonly kind: string;
  readonly onAvailabilityChanged: Event<DataPlaneAvailability>;

  start(): Promise<BackendHello>;
  openSession(params: OpenSessionParams): Promise<BackendSession>;
  getCapabilities(): SqlBackendCapabilities;
}

export interface BackendSession extends Disposable {
  readonly connectionId: string;
  readonly info: SessionInfo;
  readonly onEvent: Event<BackendSessionEvent>;

  execute(req: BackendExecuteRequest, sink: IQueryEventSink): BackendQueryHandle;
  close(): Promise<void>;
}
```

The domain adapter wraps `BackendSession` to enforce queueing, deadlines, instrumentation, and synthesized terminals consistently across bindings.

### 7.1 Lower-level transport for STS2 bindings

```ts
export interface ISts2Transport {
  readonly kind: "jsonrpc-stdio" | "http-ws";
  start(): Promise<TransportHello>;
  request<TRes>(method: string, params: unknown, opts?: RequestOpts): Promise<TRes>;
  notify(method: string, params: unknown): void;
  readonly onServerNotification: Event<{ method: string; params: unknown }>;
  readonly onTransportDown: Event<TransportDownInfo>;
  dispose(): Promise<void>;
}
```

`Sts2ProtocolEngine` sits above `ISts2Transport` and below `Sts2BackendBinding`.

---

## 8. STS2 protocol engine

### 8.1 Contract source of truth

`sqltoolsservice/docs/sts2/CONTRACT.md` or generated schemas on `sts2/main` are authoritative. Implementation task AD-1 reconciles exact method names/shapes into `src/services/sts2/wire/v2.ts`.

Until then, every concrete method name below carries `verify CONTRACT` status.

### 8.2 Wire mapping sketch

| Domain | STS2 wire, verify exact name/schema |
|---|---|
| initialize | `v2/initialize` |
| open session | `v2/connection.open` |
| close session | `v2/connection.close` |
| execute | `v2/query.execute` |
| result set metadata | notification `v2/query.resultSet` |
| rows | notification `v2/query.rows` |
| message | notification `v2/query.message` |
| terminal | notification `v2/query.complete` |
| ack | `v2/query.ack` request or notification |
| cancel | `v2/query.cancel` |
| dispose | `v2/query.dispose` |
| capture | `v2/session.setCapture` |
| fatal | notification `v2/fatal` |

### 8.3 Correlation and pending requests

- Every outbound request receives adapter correlation.
- Exactly one terminal per request.
- Duplicate terminals: diag + drop.
- Transport fatal: fail all pendings with `SqlDataPlane.Unavailable`.
- JSON-RPC IDs are not used as product-facing query/session IDs.

### 8.4 Event demux and ordering

Demux by `entityRefs.connectionId` and `entityRefs.queryId`. Each query has an ordered lane:

- one sink callback in flight;
- ack only after callback resolves;
- queue length bounded;
- invariant checks before delivering to sink.

### 8.5 Ack/credit ledger

Per `(queryId, resultSetId)`:

- track `highestSeen`, `highestAcked`, and acknowledged set/high-water;
- never ack unseen pages;
- never ack same page twice;
- coalesce high-water acks when possible;
- stop acking after terminal/corrupt/fail;
- on cancel/dispose, send final high-water for landed pages if protocol allows.

Metric: `sqlDataPlane.creditStallMs` = time sink/backpressure held backend credit.

### 8.6 Invariant checks

Always on:

- result-set metadata before rows;
- pageSeq gapless per result set;
- rowOffset monotonic and consistent;
- no rows/messages/result sets after complete;
- exactly one complete;
- complete status compatible with messages/errors;
- no page beyond memory/size bounds if backend claims honors.

Violation:

- mark query failed with `SqlDataPlane.Client.ProtocolViolation`;
- cancel/dispose backend query if possible;
- emit diagnostic with expectation/observation;
- do not present partial grid as complete truth.

### 8.7 Deadlines and synthesized terminals

Defaults, configurable:

| Deadline | Default |
|---|---:|
| open | 30 s |
| cancel ack | 10 s |
| close | 15 s |
| dispose drain | 10 s |
| complete after cancel | 30 s |
| first response after execute accept | 30 s warning, not terminal by default |

Expiry produces a synthesized completion or session lost state. Synthesized outcomes are visible in diagnostics and Query Studio messages when user-facing.

### 8.8 Fatal and availability

`v2/fatal`, transport close, or protocol engine fatal:

- availability becomes unavailable/lost;
- open sessions transition `lost`;
- active query sinks receive completion `connectionLost`;
- pending API calls settle;
- no automatic v1 fallback.

---

## 9. Queueing and priorities

STS2 allows one active query per connection. Adapter enforces:

- interactive lane: user executions, cancel-sensitive operations;
- background lane: metadata hydration, digest polls, definition reads;
- interactive always dequeues before background;
- background currently running is not preempted unless `preemptBackground` is true.

Recommended for Query Studio:

- `mssql.sqlDataPlane.preemptBackground`: true;
- digest polls skip instead of queueing behind user work;
- metadata hydration on dedicated session where possible.

Metrics:

- `sqlDataPlane.queueWait`;
- queue depth by priority;
- preemptions;
- skipped background polls.

---

## 10. Database context handling

Backend may provide structured database context changes. If not, features can parse server messages such as SQL Server context-change messages.

Adapter responsibilities:

- maintain `session.info.database` best-effort;
- expose `onDidChangeDatabase` when backend provides reliable signal or feature calls `sessionDatabaseChanged` hook;
- never parse user SQL text in the adapter for `USE` unless explicitly delegated from Query Studio;
- preserve server messages verbatim to query sink if capability says so.

Query Studio owns final `USE` tracking because it knows batch boundaries and Messages UX.

---

## 11. Error model

```ts
export class SqlDataPlaneError extends Error {
  code!: string;
  retryable!: boolean;
  corr?: string;
  backend?: { kind: string; code?: string; diagnosticRef?: string };
  server?: { number?: number; severity?: number; state?: number; line?: number; procedure?: string };
  synthesized?: boolean;
}
```

Error classes:

| Code family | Meaning |
|---|---|
| `SqlDataPlane.InvalidRequest` | Client/domain request invalid. |
| `SqlDataPlane.Busy` | Backend cannot accept due active operation and queue policy. |
| `SqlDataPlane.Unavailable` | Backend unavailable/fatal. |
| `SqlDataPlane.Auth` | Authentication/authorization to open failed. |
| `SqlDataPlane.Client.Timeout` | Adapter deadline expired. |
| `SqlDataPlane.Client.ProtocolViolation` | Backend event stream violated invariants. |
| `SqlDataPlane.Client.SinkError` | Consumer failed to accept a page/event. |
| `SqlDataPlane.Server.*` | Stable backend/server errors when structured. |

Batch execution errors are query results:

- delivered as `ServerMessage` and `QueryCompleteSummary.status = "failed"`;
- not thrown from `execute()` after the query was accepted;
- Query Studio renders them in Messages.

---

## 12. Messages

```ts
export interface ServerMessage {
  kind: "info" | "warning" | "error";
  text: string;
  number?: number;
  severity?: number;
  state?: number;
  line?: number;
  procedure?: string;
  batchOrdinal?: number;
  statementOrdinal?: number;
  rowsAffected?: number;
  isDatabaseContextChange?: boolean;
  databaseName?: string;
}
```

Important contract question with STS2:

- Query editors need verbatim `PRINT`, `RAISERROR`, and rows-affected messages in the client stream.
- Service/provider diagnostic messages in journals may be classified/redacted.
- The contract must distinguish user/server result-stream messages from provider exception diagnostics.

If STS2 cannot provide rows affected as structured data, Query Studio may parse message text as a fallback, but that fallback should be marked in diagnostics.

---

## 13. Plans

Capabilities distinguish:

- estimated plan via `SET SHOWPLAN_XML` orchestration by Query Studio;
- actual plan via `SET STATISTICS XML` or backend-native plan stream;
- plan result-set classification.

Adapter should not hard-code SSMS plan heuristics unless backend supplies metadata. It can pass plan-like result sets through with metadata; Query Studio's `PlanCollector` owns heuristics until STS2 has a structured plan event.

Future preferred event:

```ts
onPlan({ planId, batchOrdinal, statementOrdinal, format: "showplanXml", xml })
```

---

## 14. Secrets and auth

Profiles provide secrets by reference:

- credential-store lookup closure;
- AAD token provider;
- Azure Portal bearer provider;
- integrated auth marker.

Rules:

- Raw secret exists only inside the open request closure.
- Never attach secrets to session objects, errors, tags, descriptors, diagnostics, or replay records.
- Token refresh callbacks belong to binding/auth provider; domain adapter sees only success/failure.
- Canary password/token tests assert zero appearances in logs/diag/errors.

HTTP/WebSocket binding:

- Inject `TokenProvider` at composition root.
- Authorization header only in binding.
- Refresh on 401 once if provider supports it.
- Do not store bearer tokens in replay descriptors.

---

## 15. Instrumentation, capture, and replay hooks

### 15.1 Diag events

| Event | Kind | Attrs |
|---|---|---|
| `sqlDataPlane.openSession` | span | backend, authKind, database, success/error |
| `sqlDataPlane.closeSession` | span | backend, reason, success/error |
| `sqlDataPlane.execute` | begin/end marker or span | tag, commandKind, resultSets, rows, status, synthesized |
| `rpc.v2.<method>` | span | corr, backend, status |
| `sqlDataPlane.page` | metric/event | rows, bytes, resultSet, pageSeq |
| `sqlDataPlane.queueWait` | metric | priority, ms |
| `sqlDataPlane.creditStallMs` | metric | query tag, ms |
| `sqlDataPlane.protocolViolation` | event | expectation, observation, backend |
| `sqlDataPlane.deadline` | event | operation, ms, synthesized |

No SQL text, row values, connection strings, or tokens in attrs.

### 15.2 Request descriptors

```ts
export interface RequestDescriptor {
  descriptorVersion: 1;
  backendKind: string;
  sessionProfileFingerprint: string;
  database?: string;
  textDigest: string;
  textRef?: string;                  // only under elevated capture policy
  options: ExecuteOptions;
  tag?: string;
  corr?: string;
  catalogGeneration?: number;
}
```

Query Studio replay records descriptors. Default capture stores text digest only. Replayable SQL text requires elevated local capture.

### 15.3 Capture requests

`requestCapture(mode, reason, durationMs)` maps to backend capability. Host policy may deny. Adapter returns effective mode and never retries elevation.

---

## 16. Backend bindings

### 16.1 `Sts2JsonRpcBackend`

- Reuses existing STS child process and StdioMultiplexer v2 lane.
- No second stdout writer. No unframed bytes.
- `v2/initialize` on start.
- MethodNotFound or service flag off → unavailable with reason.
- Spawn environment registered before STS process starts.
- JSON-RPC notification order is trusted but still invariant-checked.

### 16.2 `Sts2HttpBackend`

Future browser-safe binding:

| Domain | Sketch |
|---|---|
| initialize | `GET /v2/server` |
| open | `POST /v2/sessions` with idempotency key |
| close | `DELETE /v2/sessions/{id}` |
| execute | `POST /v2/sessions/{id}/queries` |
| cancel | `POST /v2/queries/{id}/cancel` |
| dispose | `DELETE /v2/queries/{id}` |
| events | WebSocket per session with ordered event stream and acks |
| auth | injected bearer provider |

Resume is future. Until backend supports journaled resume, WebSocket death means session lost.

### 16.3 `HostedRestBackend`

For Azure Portal or environments that do not expose STS2 directly:

- Must implement domain semantics through its own backend contract.
- If streaming is HTTP chunked or paged pull, binding reconstructs `RowsPage` events.
- If backpressure is unsupported, binding bounds local buffering and marks `creditBackpressure=false`.
- If server messages are sanitized or omitted, Query Studio disables Messages parity features or shows limitation.

Do not pretend a REST backend is STS2 if it cannot satisfy STS2 terminal/ordering semantics. Capability honesty is the contract.

### 16.4 `FakeBackend`

For unit/perftest/self-test:

- deterministic scripts;
- chaos knobs: delay, drop, duplicate, reorder, fatal, busy, timeout;
- transcript-driven event streams;
- strict invariant tests.

---

## 17. Configuration and commands

Settings:

| Setting | Default | Notes |
|---|---:|---|
| `mssql.sqlDataPlane.enabled` | false preview | Master gate for v2 consumers. |
| `mssql.sqlDataPlane.backend` | `sts2-jsonrpc` | `sts2-http`, `hosted-rest`, `fake` reserved. |
| `mssql.sqlDataPlane.preemptBackground` | true | User query beats background. |
| `mssql.sqlDataPlane.timeouts.openMs` | 30000 | |
| `mssql.sqlDataPlane.timeouts.cancelAckMs` | 10000 | |
| `mssql.sqlDataPlane.timeouts.closeMs` | 15000 | |
| `mssql.sqlDataPlane.timeouts.disposeDrainMs` | 10000 | |
| `mssql.sts2.enabled` | false preview | Service-specific flag, may coexist during transition. |
| `mssql.sts2.transport` | `jsonrpc-stdio` | Legacy alias to backend setting if needed. |

Commands:

- `MSSQL: Show SQL data-plane status`;
- `MSSQL: Show STS2 status` optional binding-specific detail;
- `MSSQL: Copy data-plane diagnostics summary` with safe fields only.

Status command should show:

- availability;
- backend kind;
- protocol/capabilities;
- open sessions;
- queue depths;
- ledger stats;
- last fatal/unavailable reason;
- whether service-side STS2 flag appears enabled.

---

## 18. Testing and conformance

### 18.1 Conformance suite

One suite runs against every binding using transcript scenarios:

- happy single result set;
- multiple result sets;
- empty result set;
- messages interleaved with rows;
- server error after partial messages;
- cancel before accept, after accept, during rows, after complete;
- dispose races;
- connection close during query;
- backend unavailable mid-stream;
- fatal notification;
- rows before metadata;
- duplicate/gapped/out-of-order pages;
- sink slow/backpressure;
- sink throws;
- oversized/truncated cells;
- rows affected structured and message fallback;
- database context message;
- plan result.

Each transcript asserts:

- sink callback sequence;
- completion settlement;
- ack behavior where supported;
- diagnostics emitted;
- no secret/text/data leakage in diagnostics.

### 18.2 Property tests

- Ack ledger random permutations never over-ack.
- Deadlines always settle promises.
- Queueing preserves priority ordering and one-active invariant.
- Duplicate terminal events never double-complete.

### 18.3 Live matrix

- FakeBackend in unit tests.
- STS2 FakeDriver / SQLite live lanes.
- SQL Server engine subset for actual query behavior, messages, rows affected, plans, cancel.
- HTTP binding tests when service exists.

### 18.4 Privacy canaries

Place canary values in:

- password;
- access token;
- SQL text;
- result cell;
- server PRINT message;
- provider error.

Assert expected policy:

- password/token never appear anywhere;
- SQL/result not in adapter diag by default;
- server PRINT appears only in Query Studio Messages/result stream, not diag store unless elevated capture policy permits;
- provider error safe message only.

---

## 19. Milestones

| Milestone | Scope | Exit gate |
|---|---|---|
| AD-0 | Domain API, capability model, fake backend | Features compile against domain API only. |
| AD-1 | STS2 contract pinning and wire types | Generated/verified `wire/v2.ts`, first conformance transcripts. |
| AD-2 | STS2 JSON-RPC binding core | Open/execute/rows/complete/cancel against FakeDriver. |
| AD-3 | Hardening | Ledger, invariants, deadlines, priority queue, privacy canaries, status command. |
| AD-4 | Query Studio integration | Real execute to RowStore; 10k/query cancel scenarios pass. |
| AD-5 | MetadataService integration | Dedicated/background sessions and hydrate scenarios pass. |
| AD-6 | HTTP/backend readiness | Isomorphic bundle check, HTTP binding skeleton, hosted backend requirements validated. |

---

## 20. Contract questions to resolve with STS2 before Query Studio preview

1. **Verbatim messages:** `PRINT`, `RAISERROR`, errors, rows affected, and database-context changes must reach the requesting client as result-stream content. Journaling can still redact by policy.
2. **Ack shape:** request vs notification, page vs high-water, exact method name and terminal behavior after cancel/dispose.
3. **Dispose terminality:** every accepted query should produce exactly one complete. Pin ordering of dispose response relative to query complete.
4. **Rows affected:** structured field preferred; message fallback accepted only as compatibility.
5. **SPID and server info:** open response should include SPID/version/encryption/database; otherwise adapter or Query Studio must run background probes.
6. **Query options:** pageRows/pageBytes/maxCellBytes honored or explicitly hints.
7. **Plan result metadata:** structured plan event or result-set classification to avoid heuristic false positives.
8. **Fatal semantics:** exact notification/error behavior for pending and future requests.
9. **Capture policy:** client request vs host permission and effective-mode reporting.
10. **HTTP/WebSocket ordering:** if service team designs HTTP later, domain semantics in this doc are the requirements.

---

## 21. Agent implementation notes

- Do not import JSON-RPC types into Query Studio, MetadataService, or completions.
- Do not log SQL text from `execute`, even under error paths.
- Do not invent plan/message parsing inside the adapter unless the binding explicitly owns a documented compatibility shim.
- Treat protocol violations as data-integrity failures, not cosmetic warnings.
- Keep fake backend transcripts small, deterministic, and reusable by perftest/self-test.
- Prefer visible synthesized terminals over hanging promises. A scary-but-settled error is better than a polite eternity.
