# Query Studio Web Backend: Production Engineering Addendum

**Status:** Normative implementation addendum; conditional approval to build  
**Date:** 2026-07-13  
**Applies to:** `querystudio_web_backend.md` dated 2026-07-10  
**Companion addendum:** `typescript_query_endpoint_addendum.md`  
**Primary repositories:** `microsoft/vscode-mssql`, `microsoft/sqltoolsservice`, `kburtram/perftest` on `dev/query`  
**Suggested task prefix:** `WEB2-n`; commit prefix `web2:`

## 0. How to use this addendum

The base design remains the architectural source of truth except where this addendum explicitly corrects, narrows, or strengthens it. This document is written for a coding agent. Normative words have their usual engineering meaning:

- **MUST** is a correctness, security, privacy, or release-blocking requirement.
- **SHOULD** is the default implementation unless a reviewed deviation is recorded.
- **MAY** is optional and must not weaken a MUST.

Every work package in section 13 has a bounded scope, required tests, required artifacts, and a stop condition. An agent must not silently resolve a listed open decision by inventing a protocol or security rule. Record the decision in the base design or this addendum first.

## 1. Review outcome

Proceed with the recommended architecture: a separate ASP.NET Core WebHost that reuses the STS v2 Core, Runtime, and SqlClient driver and exposes STS v2 JSON-RPC over one authenticated WebSocket per isolated runtime. The architecture is sound, but production coding must not begin as one large vertical feature branch. Three prerequisite layers are mandatory:

1. **A shared multi-provider SQL Data Plane contract.** `sts2-local`, `sts2-remote`, and `ts-native` must share provider identity, lifecycle, capability, error, query-acceptance, observability, and conformance semantics. Building separate registries or instrumentation dialects would create a permanent fault line.
2. **STS v2 network-readiness hardening.** Several process-local assumptions still allow unbounded state, unbounded teardown, ambiguous query acceptance, and invisible outbound failures. A network listener must not be added before these are closed.
3. **Provider-neutral measurement and support diagnostics.** The performance harness and support capsule must exist early enough to guide implementation, not as decorative telemetry added after behavior has fossilized.

The provider should be described precisely in code and reports:

- semantic implementation: `sts2`
- deployment: `local-process`, `webhost-loopback`, or `webhost-remote`
- transport: `stdio-jsonrpc` or `wss-jsonrpc`
- database driver: `sqlclient`

Calling the hosted cell merely "STS v2 with HTTP" is ambiguous. HTTPS is used for discovery and ticket bootstrap; the query stream in this design is JSON-RPC over WSS. A future HTTP/2 streaming or REST binding is a separate transport and needs separate conformance tests.

## 2. Verified delta from the base design

This review re-read the current branch code rather than treating every finding in the base document as still open. The following table is normative for task planning.

| Area | Current branch finding | Implementation consequence |
| --- | --- | --- |
| Compact row capture | `CaptureElision` now elides the complete `compact` node, including values and null bitmap, before journaling. | Mark the original compact-value privacy bug **verified fixed**. Retain privacy canaries and stress the side-table lifetime; do not reimplement the fix. |
| Frame accounting | `DriverEffectRunner` now measures UTF-8 bytes and applies a final frame guard. | Retain as a regression gate. WebHost still needs its own final serialized WebSocket message bound because the HTTP edge may impose a lower limit. |
| STS v2 pipeline metrics | The runner already records rows, pages, encoded bytes, read, credit wait, encoding, serialization, UTF-8 measurement, page/event construction, posting, and allocation totals. | Preserve these fields. Add transport, queue, runtime, and host-resource spans instead of creating a competing query metric family. |
| Driver handle identity | The effect runner still stores live sessions under `h-<openId>`, while Core removes the successful `openId` mapping. | **P0 remains:** use a runtime-owned identity derived from `connectionId`, never a reusable client ID. |
| Query state lifetime | Completed and disposed query records are still retained in Core state. | **P0 remains:** separate live state from bounded idempotency tombstones. |
| Query disposal | Active dispose still awaits the pump task without a hard timeout. | **P0 remains:** define bounded stop, forced physical-session abort, one terminal, and observable cleanup. |
| Teardown | Leak cleanup cancels pump/open work but does not await all of it before disposing sessions. | **P0 remains:** track every provider task and await it under nested deadlines. |
| Outbound delivery | `Sts2Session.HandleOutbound` still fire-and-forgets JSON-RPC notifications. | **P0 remains:** one bounded, observed, single-writer outbound path. A send failure terminates only that runtime. |
| Hosting boundary | `Sts2Session` still constructs `HeaderDelimitedMessageHandler` internally from streams. | Extract or parameterize the message handler and keep stdio as one binding. |
| Query acceptance | STS v2 still has no client `executeId`, pre-accept cancel, or duplicate-execute contract. | Add the protocol amendment before remote transport code. |
| Client transport | `Sts2Rpc` still has no connect, close, error, abort, or promise-backed notification lifecycle. | Replace it before adding WSS. |
| Client composition | `SqlDataPlaneService` still caches one backend, silently maps unknown values to local STS, and status inspection can start it. | Replace with an owned multi-provider registry and passive status. |
| Profile preparation | Authentication mapping is now an exact switch for SQL Login, Integrated, and Entra interactive, but the portable profile remains narrow. | Keep the exact-switch rule; expand supported options deliberately and reject all unsupported semantics. |
| SqlClient baseline | The reviewed repository currently pins Microsoft.Data.SqlClient 6.1.5. | Test and document against the pinned version. Do not base a ship claim on unreconciled 7.x behavior. |

### 2.1 Reviewed code anchors

The implementation agent should revalidate these blobs at task start because `dev/query` is moving:

- `vscode-mssql/extensions/mssql/src/services/sqlDataPlane/api.ts`
- `vscode-mssql/extensions/mssql/src/services/sqlDataPlane/sqlDataPlaneService.ts`
- `vscode-mssql/extensions/mssql/src/services/sts2/sts2Backend.ts`
- `vscode-mssql/extensions/mssql/src/services/metadata/profileAuthAdapter.ts`
- `vscode-mssql/extensions/mssql/src/services/metadata/profileFingerprint.ts`
- `vscode-mssql/extensions/mssql/src/queryStudio/executionOrchestrator.ts`
- `vscode-mssql/extensions/mssql/src/diagnostics/diagnosticsCore.ts`
- `sqltoolsservice/src/sts2/Microsoft.SqlTools.Sts2.Hosting/Sts2Session.cs`
- `sqltoolsservice/src/sts2/Microsoft.SqlTools.Sts2.Runtime/Effects/DriverEffectRunner.cs`
- `sqltoolsservice/src/sts2/Microsoft.SqlTools.Sts2.Runtime/Coordination/CaptureElision.cs`
- `sqltoolsservice/src/sts2/Microsoft.SqlTools.Sts2.Core/{CoreState,Sts2CoreReducer}.cs`
- `perftest/packages/perf-contracts/src/{config,controlMessages,result}.ts`
- `perftest/packages/perftest-cli/src/run/{runPipeline,environment}.ts`
- `perftest/packages/perftest-cli/src/scenarios/registry.ts`

## 3. Shared provider contract that must land first

This section is intentionally mirrored in the native TypeScript addendum. Keep the definitions in one source file and generate or import projections. Do not allow the two implementations to fork them.

### 3.1 Provider identity is a tuple, not one enum string

`backendKind` remains the product selector, but diagnostics, caching, policy, and performance need the complete composition:

```ts
export type SqlBackendKind =
    | "sts2-local"
    | "sts2-remote"
    | "ts-native"
    | "fake";

export type SqlProviderImplementation = "sts2" | "ts-native" | "fake";
export type SqlProviderTransport = "stdio-jsonrpc" | "wss-jsonrpc" | "inprocess";
export type SqlProviderDriver = "sqlclient" | "tedious" | "fake";
export type SqlProviderDeployment =
    | "extension-local"
    | "webhost-loopback"
    | "webhost-remote"
    | "test";

export interface SqlBackendIdentity {
    readonly kind: SqlBackendKind;
    readonly implementation: SqlProviderImplementation;
    readonly transport: SqlProviderTransport;
    readonly driver: SqlProviderDriver;
    readonly deployment: SqlProviderDeployment;
    readonly realmId: string;          // non-secret stable partition id
    readonly providerVersion: string;
    readonly protocolVersion?: string;
    readonly driverVersion?: string;
}
```

Rules:

1. Every session snapshots the identity at open and never mutates it.
2. Every terminal, status snapshot, support capsule, and perf treatment records it.
3. `realmId` partitions credentials, consent, metadata, and diagnostics. A remote deployment ID must not be inferred from a URL string alone.
4. Alias `sts2-jsonrpc` may be accepted only at settings migration. It is never emitted as a new identity.

### 3.2 One owned registry, multiple local providers, remote realm isolation

Replace the static singleton with an activation-owned `SqlDataPlaneService`. It owns lazy factories, sessions, retries, configuration fingerprints, and disposal.

```ts
export interface SqlBackendFactory {
    readonly kind: SqlBackendKind;
    readonly displayName: string;
    readonly realmClass: "local" | "remote" | "test";
    readonly staticCapabilities: SqlCapabilitySet;
    create(context: SqlBackendFactoryContext): Promise<ISqlConnectionService>;
}

interface BackendEntry {
    readonly factory: SqlBackendFactory;
    startup?: Promise<ISqlConnectionService>; // single flight
    service?: ISqlConnectionService;
    configFingerprint: string;
    activeSessionCount: number;
    lastError?: SqlDataPlaneErrorInfo;
}
```

Required behavior:

- Unknown backend kind is `SqlDataPlane.InvalidRequest`, never a local fallback.
- Passive status and capability queries never construct a backend, prompt for auth, mint a ticket, or resolve a database credential.
- A failed startup clears the single-flight promise and is explicitly retryable.
- A configuration change drains only the affected entry when local providers coexist.
- A remote realm change atomically invalidates its consent, auth cache, metadata partition, and sessions.
- Extension deactivation awaits bounded disposal of every provider.
- Use explicit session registration and finalization. `WeakRef` alone is not lifecycle ownership.

### 3.3 Canonical capability model

Do not grow an unstructured boolean object and a separate string-ID oracle by hand. Define one versioned registry and derive compatibility projections.

```ts
export type SqlCapabilitySupport =
    | "supported"
    | "unsupported"
    | "conditional"
    | "degraded";

export type SqlCapabilityFidelity =
    | "exact"
    | "normalized"
    | "lossy"
    | "notApplicable";

export interface SqlCapabilityValue {
    readonly support: SqlCapabilitySupport;
    readonly fidelity?: SqlCapabilityFidelity;
    readonly limit?: number;
    readonly unit?: "bytes" | "rows" | "pages" | "milliseconds" | "count";
    readonly reasonCode?: string;
    readonly source: "static" | "handshake" | "route" | "session" | "probe";
}

export interface SqlCapabilitySet {
    readonly schemaVersion: 1;
    readonly values: Readonly<Record<SqlCapabilityId, SqlCapabilityValue | undefined>>;
}

export type SqlCapabilityRequirement =
    | { readonly id: SqlCapabilityId; readonly require: "supported" }
    | { readonly id: SqlCapabilityId; readonly fidelityAtLeast: "exact" | "normalized" }
    | { readonly id: SqlCapabilityId; readonly minimum: number };
```

Minimum initial IDs:

```text
auth.sqlLogin
auth.entraToken
auth.integrated
auth.hostDelegated
connect.tcp
connect.routeAlias
exec.streamingRows
exec.multipleResultSets
exec.cancel
exec.dispose
exec.queryTimeout
exec.compactRows
exec.maxCellBytes
exec.pageRows
exec.pageBytes
exec.windowPages
types.typedCells
types.vectorBinaryV1
types.spatialWkbV1
types.decimalExact
types.datetimeOffsetOriginal
metadata.catalogSql
metadata.endpoints
diag.supportCapsule
diag.captureControl
diag.replayDescriptor
diag.resumeAfterDisconnect
```

Plan parsing, result export, browser spill storage, webview rendering, and inline-completion availability are Query Studio host capabilities, not database-provider capabilities. Keep them in a separate `QueryStudioHostCapabilities` aggregate.

`canOpen` MUST evaluate capability and route policy before invoking a password or token provider. It returns all missing requirements, safe reasons, and alternative providers. It must not open a network connection to answer a static question.

### 3.4 Operation context and always-settled query acceptance

The current `backendQueryId` promise can remain unsettled when execute fails before acceptance. Replace it with an explicit acceptance result. Keep a compatibility getter only during migration.

```ts
export interface DataPlaneOperationContext {
    readonly operationId: string;      // random, client-owned
    readonly traceparent?: string;
    readonly deadlineEpochMs?: number;
    readonly signal?: AbortSignal;
    readonly perf?: {
        readonly runId: string;
        readonly repId: number;
        readonly scenarioId: string;
        readonly treatmentId: string;
    };
}

export type QueryAcceptance =
    | { status: "accepted"; clientQueryId: string; backendQueryId?: string; acceptedEpochMs: number }
    | { status: "rejected"; clientQueryId: string; error: SqlDataPlaneErrorInfo }
    | { status: "aborted"; clientQueryId: string; reason: "caller" | "deadline" | "transport" };

export interface QueryHandle {
    readonly clientQueryId: string;
    readonly accepted: Promise<QueryAcceptance>; // always settles
    readonly completion: Promise<QueryCompleteSummary>; // always settles
    cancel(): Promise<CancelAck>;
    dispose(): Promise<void>;
}
```

`ISqlSession.execute` may remain synchronous in returning the handle, but the handle enters this state machine:

```text
created -> submitting -> accepted -> streaming -> terminal
                |             |          |
                +-> rejected  +-> cancelRequested
                +-> aborted   +-> disposeRequested
```

Normative invariants:

1. Acceptance settles once.
2. An accepted query has exactly one terminal.
3. A rejected or pre-submit-aborted query emits no stream events.
4. `completion` settles independently of a stuck or throwing sink callback.
5. Cancel before acceptance is meaningful and provider-specific machinery must preserve it.
6. User SQL is never automatically replayed after an ambiguous disconnect.

Add an additive terminal field:

```ts
interface QueryCompleteSummary {
    // existing fields
    readonly outcomeCertainty?: "known" | "unknown";
    readonly outcomeReason?: "transportLost" | "cancelUncertain" | "providerAborted";
}
```

Any accepted query that loses its provider/transport before a trustworthy terminal is `unknown`. The UI and support capsule must say that database side effects may have occurred and must not offer an automatic retry. User cancellation can also have partial committed effects; `cancelAck.uncertain` is propagated into outcome certainty.

### 3.5 Error taxonomy

Add these stable domain identities and register them in the diagnostics safe-code set:

```text
SqlDataPlane.CapabilityUnsupported
SqlDataPlane.PolicyDenied
SqlDataPlane.ResourceLimit
SqlDataPlane.Client.Aborted
SqlDataPlane.Client.Timeout
SqlDataPlane.Client.ProtocolViolation
SqlDataPlane.Client.SinkError
SqlDataPlane.Transport.Closed
SqlDataPlane.Transport.Backpressure
SqlDataPlane.Provider.Internal
```

Provider exception text is not a contract. An error object contains stable code, retryability, safe message, backend identity, correlation ID, optional structured server fields, and an operator-only detail reference. Never forward raw remote paths, stack traces, SQL text, tokens, or connection strings.

### 3.6 Cache and consent identity

Version the connection fingerprint and include, without secrets:

- fingerprint schema version
- backend kind and realm ID
- authorized route alias or normalized direct-target digest
- database, login/account identity digest, tenant, auth strategy
- encryption, certificate, application intent, and every supported connection-affecting option
- provider implementation/driver when fidelity can differ

The same cache partition must never span two principals whose metadata visibility may differ. Remote credential disclosure consent is user/global state keyed by authenticated realm ID, route policy identity, auth strategy, and profile fingerprint. Workspace data cannot pre-seed it.

## 4. Normative WebHost runtime boundary

### 4.1 Required component split

The ASP.NET project owns only edge concerns. It does not become a second query engine.

```text
Kestrel/auth/tickets/policy/quotas
        |
        v
WebSocket JSON-RPC binding
        |
        v
transport-neutral Sts2RuntimeSession
        |
        +-> Gateway and DTO validation
        +-> Coordinator/Core/effects
        +-> journal/capture policy
        +-> SqlClient driver
```

The following dependency edges are forbidden:

- WebHost -> legacy ServiceLayer
- WebHost -> STS v1 controllers
- WebHost controller -> Coordinator directly
- vscode-mssql feature -> WebSocket/JSON-RPC DTOs
- Core -> ASP.NET, WebSocket, identity, clock, or filesystem

### 4.2 Runtime API

Refactor `Sts2Session` into an explicit lifetime owner. The exact names may vary, but the ownership must not.

```csharp
public sealed record Sts2RuntimeSessionOptions
{
    public required string RuntimeId { get; init; }
    public required Sts2EffectivePolicy Policy { get; init; }
    public required IReadOnlyDictionary<string, IDbDriver> Drivers { get; init; }
    public required ISts2JournalFactory JournalFactory { get; init; }
    public required ISts2Telemetry Telemetry { get; init; }
    public required TimeProvider TimeProvider { get; init; }
}

public interface ISts2RuntimeSession : IAsyncDisposable
{
    string RuntimeId { get; }
    Task Completion { get; }
    Sts2RuntimeSnapshot Snapshot();
    ValueTask StartAsync(IJsonRpcMessageHandler handler, CancellationToken cancellationToken);
    ValueTask StopAsync(Sts2StopReason reason, CancellationToken cancellationToken);
}
```

Rules:

1. The runtime constructs and owns `JsonRpc`, gateway, coordinator, effects, secrets, and journal.
2. The caller supplies the message handler. Stdio supplies `HeaderDelimitedMessageHandler`; WebHost supplies the WebSocket handler.
3. The ASP.NET endpoint owns the WebSocket and always disposes it in `finally` after runtime stop.
4. `StartAsync` is single-use. `StopAsync` and `DisposeAsync` are idempotent.
5. Clean transport completion, fault, server drain, ticket expiry, and application shutdown all enter the same stop state machine.
6. Stop first rejects new work, then fails pending RPCs, clears request secrets, cancels and awaits provider work, drains coordinator output, flushes bounded diagnostics, and closes transport.

### 4.3 Runtime stop hierarchy

Use nested deadlines with one monotonic clock:

```text
query stop deadline
    < SQL session close deadline
    < runtime drain deadline
    < platform shutdown deadline
```

A suggested initial policy, subject to measured tuning:

| Deadline | Default | Result on expiry |
| --- | ---: | --- |
| sink callback | 30 s | fail query locally, cancel provider, settle completion |
| query cancel acknowledgement | 10 s | uncertain ack; continue terminal deadline |
| query dispose/pump stop | 10 s | force physical SQL session abort |
| SQL session close | 15 s | force dispose and mark session lost |
| runtime graceful drain | 30 s | abort remaining provider work/socket |
| process shutdown | 45 s | final hard abort |

All expiries emit stable reason codes and duration metrics. No `Task` may be left unobserved after runtime disposal.

### 4.4 WebSocket message handler

The custom handler for the pinned StreamJsonRpc version MUST:

- map one JSON-RPC value to one text WebSocket message
- reassemble fragments only up to the uncompressed inbound limit
- reject binary and JSON-RPC batch messages in v1
- validate UTF-8, JSON depth, token count, collection count, and DTO shape
- use exactly one reader and one writer
- expose observed completion and send failures
- enforce a final outbound UTF-8 byte limit after JSON-RPC serialization
- own no socket lifetime beyond the endpoint contract
- disable compression initially
- emit byte, latency, queue, and close-category metrics

Do not pass `Content-Length` framing over the socket.

### 4.5 Bounded outbound scheduling

Correctness first requires one FIFO writer. Performance and multi-session fairness then require a scheduler that cannot let a large interactive query starve metadata, cancellation, or terminals.

Implement these invariants before the remote perf gate:

1. Per-query event order is immutable.
2. The execute response is committed before events that lack a client-visible binding. The protocol amendment in section 5 makes events independently bindable by `executeId`, which is still required as a defensive mechanism.
3. Control responses, cancel/dispose/close results, and terminals have a priority class but cannot overtake earlier events in the same query lane.
4. Row pages are scheduled by encoded byte cost, not just message count.
5. Each runtime has hard caps for queued messages and bytes.
6. A queue overflow terminates that runtime. It never drops a page or terminal and continues.
7. Queue metrics report current depth, byte depth, per-class high water, oldest age, enqueue wait, send duration, and overflow reason.

A weighted deficit round-robin scheduler over per-query lanes is the recommended production implementation. A single bounded FIFO is acceptable only for the first loopback conformance slice and must be labeled as such.

## 5. Required STS v2 protocol addendum

Write and review this protocol text before implementation. These are additive contract changes, not private WebHost conventions.

### 5.1 Client execute identity

`v2/query.execute` gains a required random `executeId` for clients that negotiate `queryExecuteIdentityV1`.

```json
{
  "executeId": "e_128bitRandom",
  "connectionId": "c-17",
  "sql": "<redacted here only for illustration>",
  "options": { "compactRows": true }
}
```

Core records a mapping from execute ID to accepted query ID. Every query notification includes both `executeId` and `queryId`, plus an optional monotonic `eventSeq`:

```json
{
  "executeId": "e_128bitRandom",
  "queryId": "q-42",
  "eventSeq": 3,
  "resultSetId": 0
}
```

Semantics:

- duplicate execute in the same runtime never starts SQL twice
- a duplicate returns the original acceptance outcome while its bounded tombstone exists
- `v2/query.cancelExecute` cancels by execute ID before or after query acceptance
- cancel ordered before acceptance causes a stable canceled acceptance and no stream
- cancel ordered after acceptance routes to normal query cancel
- transport retry middleware never resends execute automatically
- execute tombstones are count-bounded by a policy seeded through `session.start`, not wall-clock decisions hidden from replay

### 5.2 Open identity and driver handle identity

`openId` remains a client operation ID, not a provider handle. The effect runner MUST use `connectionId` or another runtime-generated unique ID for its live-session table. Recommended:

```csharp
string handleId = "h-" + connectionId;
```

Retain only the bounded state needed for duplicate-open semantics. Reusing an ID must never alias a live physical connection.

### 5.3 Request metadata

Allow an optional `_meta` object at the gateway boundary:

```json
{
  "_meta": {
    "operationId": "op_...",
    "traceparent": "00-...",
    "deadlineEpochMs": 1783970000000,
    "attempt": 0
  }
}
```

The gateway validates and strips `_meta` before Core journaling unless a field is protocol-semantic. Trace and deadline metadata must not perturb deterministic Core replay. The server creates a child Activity but never trusts caller trace fields for authorization or tenant attribution.

### 5.4 Effective capabilities and limits

Effective limits and method policy enter Core through the journaled `session.start` envelope so live and replay agree. Add at least:

- max live connections
- max live queries and tombstones
- page rows, page bytes, max cell bytes
- window pages and maximum outstanding page bytes
- maximum SQL bytes
- maximum messages/result sets/columns per query
- capture policy
- allowed drivers
- allowed database-auth strategies
- allowed diagnostics methods
- execute-ID support

Initialization reports the effective values. A gateway also enforces the method allowlist so an untrusted client cannot invoke an unadvertised diagnostic method.

### 5.5 Initialization gate

Before successful compatible initialize, permit only:

- `v2/initialize`
- optionally `v2/diagnostics.ping`, if explicitly approved

All connection, query, state, capture, and export methods fail with a stable initialization-required error. Repeated compatible initialize is idempotent. Incompatible version or required capability fails before any SQL credential can be resolved.

### 5.6 Close and fatal categories

Define an application close-category enum and map it to sanitized WebSocket close codes/reasons. Examples:

```text
normal
clientShutdown
idleTimeout
absoluteLifetime
serverDrain
protocolViolation
messageTooLarge
authExpired
policyDenied
quotaExceeded
outboundBackpressure
internalFailure
```

WebSocket reason strings are short and safe. Full operator details stay in correlated diagnostics.

## 6. STS v2 correctness work required before network exposure

### 6.1 Live state and tombstones

Split live resources from idempotency history.

```csharp
public sealed record CoreState
{
    public required ImmutableSortedDictionary<string, ConnectionInfo> Connections { get; init; }
    public required ImmutableSortedDictionary<string, QueryInfo> LiveQueries { get; init; }
    public required ImmutableSortedDictionary<string, ExecuteTombstone> ExecuteTombstones { get; init; }
    public required ImmutableQueue<string> ExecuteTombstoneOrder { get; init; }
}
```

Requirements:

- A terminal query may remain live only while provider cleanup or an explicit client dispose is outstanding.
- After provider resources are released, remove the full query record.
- Preserve only the minimum duplicate-execute outcome in a bounded tombstone.
- Bounds are deterministic inputs in `session.start`.
- Eviction is deterministic by journal sequence/order.
- Diagnostics state reports live counts and tombstone counts separately.
- Unknown late cancel/dispose remains idempotent and does not require a full retained record.

Add million-operation state-size tests. A long-lived socket must approach a stable memory plateau.

### 6.2 Bounded query stop and forced abort

`driver.queryDispose` must not await a pump forever. Implement:

1. mark pump suppressed
2. cancel its token
3. invoke driver cancel/dispose
4. await pump under `queryDisposeTimeout`
5. on expiry, close/abort the owning physical session
6. post exactly one dispose result to Core with `forcedSessionAbort=true`
7. transition the SQL session to lost/closed and reject subsequent execute
8. observe and classify any late pump exception

The caller gets one query terminal. The session state change is a separate event and must not create another query terminal.

### 6.3 Complete teardown accounting

Track every long-running operation in one runtime task registry:

```csharp
public interface IRuntimeTaskRegistry
{
    RuntimeTaskLease Track(string category, string operationId, Task task);
    RuntimeTaskSnapshot Snapshot();
    ValueTask CancelAndDrainAsync(TimeSpan timeout, CancellationToken cancellationToken);
}
```

At minimum track opens, query pumps, token acquisition, SQL close, outbound writer, journal flush, and diagnostics export. The runtime completion task is successful only when all tracked work has completed or has been explicitly force-aborted and accounted for.

### 6.4 Pending request settlement and secret lifetime

On any runtime stop:

- atomically stop intake
- reject every pending request completion source with `Sts2.Unavailable` or the classified stop reason
- remove pending request bodies and correlation IDs
- clear the secret side table before journal/export finalization
- cancel provider operations
- complete the outbound queue with the original failure

A deadline implemented only as `Promise.race` or `Task.WhenAny` without aborting/removing the underlying request is not accepted.

### 6.5 Boundary validation

Add total validators before reducer/effect access. Validation MUST cover:

- object kind and required fields
- string UTF-8 byte lengths
- ID format/length
- integer conversion ranges
- enum allowlists
- unknown-field count and total depth
- SQL bytes
- profile option count and size
- result-set/column/message collection limits
- mutually exclusive page shapes
- route/direct-target grammar
- auth strategy and credential presence

Malformed requests produce stable errors and cannot fault the coordinator. Run a seeded malformed corpus and a property-based/fuzz lane against both stdio and WebSocket bindings.

### 6.6 Journal and capture policy

The current compact elision fix remains mandatory, but production hosting needs additional bounds:

- `off` journal implementation with no file creation
- total bytes per runtime, not only per-segment rotation
- maximum segment count and retention deadline
- bounded in-memory capture side table by entries and bytes
- opaque random runtime directories
- server message and SQL exception classification
- no filesystem path returned to ordinary clients
- explicit export authorization and expiring stream

Remote default is `off`. Redacted/digest support capture is opt-in and still treated as customer data. Full capture requires time-bounded elevated consent and encryption.

### 6.7 Provider allowlist

The remote composition registers only `sqlclient`. Missing or unknown driver names fail closed. Never default to `fake` or expose SQLite, because the latter turns target input into a filesystem path.

## 7. Web edge, security, and tenancy details

The base design already covers Entra, tickets, target policy, and deployment options. This section adds code-level constraints that prevent common implementation shortcuts.

### 7.1 Ticket state machine

```text
issued -> redeemed
   |         |
   +-> expired
   +-> revoked
```

Required ticket record:

```csharp
public sealed record WebSocketTicketRecord
{
    public required byte[] TicketHash { get; init; }
    public required string PrincipalKey { get; init; }
    public required string TenantKey { get; init; }
    public required string AuthorizationGrantId { get; init; }
    public required string ExpectedClientClass { get; init; }
    public string? ExpectedOrigin { get; init; }
    public required string Subprotocol { get; init; }
    public required DateTimeOffset ExpiresAt { get; init; }
    public string? OboSecurityContextKey { get; init; }
}
```

- Generate at least 256 random bits.
- Store only a hash when server-side storage is used.
- Redeem with one atomic operation, such as a transaction or atomic get-delete.
- Acquire the long-lived socket quota lease during redemption, not issuance.
- Scrub the query string from every access log, proxy log, exception, and metric.
- An in-memory store is valid only for loopback/single-replica development.
- A self-contained ticket still needs replay prevention; it is not the recommended first implementation.

### 7.2 Principal, authorization grant, and runtime isolation

Create an immutable `BackendGrant` during ticket issuance. It contains only authorized facts:

```csharp
public sealed record BackendGrant
{
    public required string GrantId { get; init; }
    public required string PrincipalKey { get; init; }
    public required string TenantKey { get; init; }
    public required ImmutableHashSet<string> RouteIds { get; init; }
    public required ImmutableHashSet<string> DatabaseAuthStrategies { get; init; }
    public required ResourceClass ResourceClass { get; init; }
    public required DiagnosticsPermission Diagnostics { get; init; }
    public required DateTimeOffset AbsoluteExpiresAt { get; init; }
}
```

The runtime receives the grant once and cannot change principal. IDs supplied by the client are never authorization objects. A connection open reauthorizes route, database, and auth strategy against the grant and current server policy.

### 7.3 Target policy pipeline

Normalize and authorize in this order:

1. reject connection strings and unsupported transports
2. resolve route alias, or parse direct host/port only when direct mode is allowed
3. normalize DNS name, port, database, and options
4. enforce route/database/auth/TLS option policy
5. resolve DNS under a rebinding-aware policy
6. compare resolved addresses with allowed network ranges
7. connect through controlled egress
8. record only route/target digests in standard telemetry

Authorization occurs on every open. A ticket does not reserve or authorize a specific SQL credential.

### 7.4 OBO and managed identity provider seam

Do not serialize server-acquired SQL tokens through JSON-RPC. Add an opaque host credential provider reference that is valid only inside one runtime:

```csharp
public interface IHostDatabaseCredentialProvider
{
    string Strategy { get; }
    string SecurityContextKey { get; }
    ValueTask<AccessToken> GetTokenAsync(
        AuthorizedSqlTarget target,
        TokenRequestContext context,
        CancellationToken cancellationToken);
}
```

The driver receives a callback/provider, not a raw long-lived token where the pinned SqlClient API permits. Partition pools by security context, route, and callback identity. If pool isolation cannot be proven in the pinned driver, disable pooling for delegated identities in the preview and record that fact in capabilities and performance treatments.

### 7.5 Global admission

Use leases, not check-then-increment counters:

```csharp
public interface IGlobalAdmissionController
{
    ValueTask<IAsyncDisposable> AcquireSocketAsync(AdmissionKey key, CancellationToken ct);
    ValueTask<IAsyncDisposable> AcquireSqlSessionAsync(AdmissionKey key, CancellationToken ct);
    ValueTask<IAsyncDisposable> AcquireQueryAsync(AdmissionKey key, CancellationToken ct);
    AdmissionSnapshot Snapshot();
}
```

Every lease has one owner and is released after actual cleanup, not merely after the client disconnects. For multi-replica deployment, use distributed leases or conservative per-replica ceilings tied to maximum scale. Emit quota denial by resource and scope.

## 8. vscode-mssql remote provider implementation

### 8.1 Transport interface

Use one transport port for local and remote STS2 bindings:

```ts
export interface Sts2RpcTransport extends AsyncDisposable {
    readonly state: Sts2TransportState;
    readonly onDidChangeState: DataPlaneEvent<Sts2TransportState>;
    readonly onDidClose: DataPlaneEvent<TransportCloseInfo>;

    connect(context: DataPlaneOperationContext): Promise<void>;
    request<R>(
        method: string,
        params: unknown,
        context: DataPlaneOperationContext,
    ): Promise<R>;
    notify(
        method: string,
        params: unknown,
        context?: DataPlaneOperationContext,
    ): Promise<void>;
    onNotification(method: string, handler: (params: unknown) => void): DataPlaneDisposable;
    close(info?: { code?: number; reason?: string }): Promise<void>;
}
```

Required implementation details:

- pending requests are held in a bounded map with body-byte accounting
- abort removes the pending entry and any queued serialized body
- close rejects every pending request once
- notification send is promise-backed
- one writer preserves message order
- the client enforces inbound bytes, JSON depth, and DTO validation
- reconnect backoff has jitter and a stop signal
- reconnect reauthenticates/reinitializes only; it never recreates SQL sessions or reruns SQL

### 8.2 `Sts2Backend` hardening

Refactor the adapter rather than cloning it. Mandatory changes:

1. Inject `SqlBackendIdentity` instead of hard-coded `sts2-jsonrpc` strings.
2. Add initialize, open, and execute-accept absolute deadlines with `AbortSignal` propagation.
3. Resolve database secrets only after transport authentication, initialization, target-safe `canOpen`, and consent. Missing credentials are a typed error; never coerce `undefined` to an empty password/token. An explicitly stored empty SQL password remains distinguishable from failure to resolve one.
4. Validate every initialize result, error, and notification with runtime validators.
5. Replace the unbounded query-ID orphan buffer with an execute-ID registry bounded by count, bytes, and age. A limit violation is a protocol failure.
6. Make `accepted` settle on success, rejection, abort, and transport loss.
7. Await ack delivery. Ack failure terminates the query/session path rather than silently reducing credit forever.
8. Bound all sink callbacks and settle `completion` independently.
9. On transport close, mark every session lost and synthesize one `connectionLost` terminal for each accepted unresolved query.
10. Strip remote paths and untrusted detail strings before status/UI.
11. Advertise only negotiated capabilities. Do not infer capture, replay, plans, or resume.

### 8.3 Side-effect-free status

`mssql.sqlDataPlane.showStatus` reads registry/factory snapshots only. It must not:

- call `service()` in a way that creates the backend
- invoke VS Code authentication
- fetch `/info`
- mint a ticket
- open a WebSocket
- resolve SQL credentials

Provide explicit `Connect`, `Retry`, and `Disconnect Backend` commands for those effects.

### 8.4 Strict portability tripwires

In strict/remote composition:

- Query Studio, Metadata, native language, and OE v2 receive only the injected SQL Data Plane service.
- Construct no STS v1 bridge for scoped language requests.
- Register no OE legacy handoff commands.
- Plan parsing is injected and capability-gated.
- Tests fail if a scoped operation reaches `SqlToolsServiceClient`, local STS spawn, or classic connection handoff.

## 9. Observability and reproducibility contract

### 9.1 Two layers: provider-neutral and provider-specific

Provider-neutral events drive comparison and support tooling. Provider-specific events explain where time and resources went.

Common lifecycle vocabulary:

```text
sqlDataPlane.provider.create
sqlDataPlane.provider.state
sqlDataPlane.capability.check
sqlDataPlane.auth.resolve
sqlDataPlane.session.open
sqlDataPlane.session.state
sqlDataPlane.query.submit
sqlDataPlane.query.accept
sqlDataPlane.query.firstMetadata
sqlDataPlane.query.firstPageProduced
sqlDataPlane.query.firstPageAccepted
sqlDataPlane.query.terminal
sqlDataPlane.query.cancel
sqlDataPlane.query.dispose
sqlDataPlane.session.close
sqlDataPlane.supportCapsule.created
```

Web/STSv2 diagnostics:

```text
sts2.web.ticket.issue
sts2.web.ticket.redeem
sts2.web.socket.open
sts2.web.socket.close
sts2.web.rpc.request
sts2.web.rpc.response
sts2.web.outbound.enqueue
sts2.web.outbound.send
sts2.web.outbound.overflow
sts2.web.runtime.snapshot
sts2.web.quota.acquire
sts2.web.quota.deny
sts2.web.auth.api
sts2.web.auth.databaseToken
sts2.web.target.authorize
sts2.web.runtime.stop
```

Retain `sts2.query.stats` as the authoritative Core/driver pipeline aggregate. Add provider identity and correlation fields through the bridge rather than renaming it.

### 9.2 Required ordering fields

Trace IDs alone do not reproduce event order. Add:

- `providerSeq`: monotonic per provider runtime/session
- `queryEventSeq`: monotonic per accepted query
- `operationId`: client-owned ID
- `executeId` and safe local `queryId`
- `causeEventId` where one event triggered another

Counters must be exact even when detailed events are sampled. Every support artifact reports dropped event count, dropped bytes, queue overflows, and sampling decisions.

### 9.3 Trace propagation and clocks

- The extension creates the root trace and operation ID.
- Ticket/bootstrap, WebSocket connect, initialize, open, and query operations create child spans.
- The WebHost validates `traceparent` syntax and starts a child `Activity`; principal attribution comes only from authentication.
- Core journal correlation and envelope sequence are attached as safe fields.
- Durations use local monotonic clocks.
- Cross-process ordering uses epoch timestamps plus a calibrated offset and uncertainty from ping/pong exchange.
- The support capsule records clock source, offset, round-trip, and uncertainty.

### 9.4 Runtime snapshots

Capture transition snapshots always when a diagnostic sink is active, and periodic snapshots during active work in rich/perf mode.

WebHost snapshot fields:

- socket state, age, last receive/send, heartbeat RTT
- pending RPC count/bytes and oldest age
- outbound queue count/bytes by class and high water
- live connections, opens, queries, tombstones
- query credit ledger and credit-stall duration
- pump/task registry by category and age
- journal/capture bytes and side-table bytes
- process CPU, working set, managed heap, allocation rate, GC counts/pause, thread-pool queue/threads
- SqlClient active physical sessions and pool/security-context counts where safely measurable
- global/principal quota usage
- telemetry sink health and dropped events

Do not access unstable private runtime fields for a ship requirement. When a metric is unavailable, emit `available:false` rather than zero.

### 9.5 Support capsule

A default support capsule is a privacy-safe reproduction manifest, not a claim that arbitrary database semantics can be reconstructed without SQL/schema/data.

```json
{
  "schemaVersion": 1,
  "privacyMode": "redacted",
  "builds": {},
  "environment": {},
  "backendIdentity": {},
  "realmAndRouteDigests": {},
  "serverFacts": {},
  "capabilities": {},
  "effectiveLimits": {},
  "featureFlagsAndTuning": {},
  "timeline": [],
  "runtimeSnapshots": [],
  "aggregates": {},
  "stableErrors": [],
  "telemetryHealth": {},
  "replayRecipe": {}
}
```

The capsule MUST include:

- exact repository/product/provider/driver/protocol versions or SHAs
- OS, architecture, CPU class, memory class, VS Code, Node, and .NET versions
- provider identity and effective capability/limit snapshot
- auth strategy, never token or credential
- server product/version/engine edition and database compatibility level when safe
- sanitized settings/tuning/fault-injection snapshot and random seeds
- state-transition timeline with relative monotonic timing
- query shape facts: bytes, result sets, columns, rows, pages, messages, cell-size histogram, type categories, but no values
- queue/credit/task/runtime snapshots
- stable errors and cleanup outcomes
- all telemetry loss/sampling facts

For transport, backpressure, race, and lifecycle bugs, generate a deterministic fake-provider script from the shape/timing transcript. For SQL-semantic or value-encoding bugs, full reproduction requires a separately consented encrypted capture containing the SQL and any necessary schema/value fixture. The UI and documentation must state this boundary honestly.

### 9.6 Capture cost controls

- No active sinks: one cheap listener check, no payload construction.
- Default redacted mode: exact aggregate counters plus transition events.
- Rich mode: periodic runtime snapshots and bounded per-page detail.
- Perf mode: complete synthetic timeline where the harness contract permits it.
- Elevated full capture: explicit user action, reason, expiry, encryption, size cap, and visible status.

Instrumentation must never block the query path. A sink may drop, but it must report the drop.

## 10. Debug Console additions

Add a provider-neutral SQL Data Plane page with WebHost panels:

- provider registry and realm state
- remote auth/ticket/socket lifecycle
- sessions and active queries
- outbound queue and credit ledger
- effective capabilities and limits
- quotas and denials
- recent stable errors
- runtime resource charts
- support capsule export

Actions are reducer-dispatched and capability/policy gated:

```text
connectBackend
retryBackend
disconnectBackend
cancelQuery
closeSession
copySafeStatus
exportSupportCapsule
enableTimeBoundRichCapture
```

No Debug Console action may reveal a token, ticket, password, raw route, SQL text, or remote journal path in default mode.

## 11. Three-provider performance laboratory

The harness must compare treatments, not encode the backend into a pile of unrelated scenario IDs. A scenario describes user work. A treatment describes how it is served.

### 11.1 Canonical treatment model

Add to `@mssqlperf/contracts`:

```ts
export interface ProviderTreatment {
    readonly treatmentId: string;
    readonly backendKind: "sts2-local" | "sts2-remote" | "ts-native";
    readonly implementation: "sts2" | "ts-native";
    readonly transport: "stdio-jsonrpc" | "wss-jsonrpc" | "inprocess";
    readonly driver: "sqlclient" | "tedious";
    readonly deployment:
        | "extension-local"
        | "webhost-loopback"
        | "webhost-remote";
    readonly providerLifecycle: "perRep" | "perBlock" | "external";
    readonly auth: "sqlLogin" | "directToken" | "obo" | "managedIdentity";
    readonly settings: Readonly<Record<string, unknown>>;
    readonly network?: NetworkTreatment;
}

export interface NetworkTreatment {
    readonly leg: "clientToBackend" | "backendToSql";
    readonly latencyMs: number;
    readonly jitterMs?: number;
    readonly bandwidthMbps?: number;
    readonly lossPct?: number;
}

export interface PerfMatrixSpec {
    readonly treatments: readonly ProviderTreatment[];
    readonly order: {
        readonly strategy: "latinSquare" | "randomizedBlocks" | "fixed";
        readonly seed: number;
        readonly blockBy: "repetition" | "scenario";
    };
}
```

The same `scenarioId` runs under all treatments. Tactical suffixed scenarios may bootstrap the first prototype, but they must not become the durable result schema. Settings merge in this fixed order: scenario defaults -> treatment settings -> run/diagnostic override. Persist the fully resolved settings and a digest in every rep. Treatment settings that affect activation are written before VS Code starts, using the existing `ScenarioSpec.userSettings` seam.

Success criteria and process discovery are treatment-aware. Add `webHost` to sender/process roles. A native treatment must not fail because no `sts` process exists; a WebHost treatment must require the expected `webHost` role. Generate `noErrors.sources` and required process roles from the treatment instead of hard-coding `sts`.

### 11.2 Environment versus treatment fingerprint

Keep two digests:

- `environmentHash`: hardware, OS, VS Code, extension build, SQL fixture/image, cache mode, pass type, and other comparability controls
- `treatmentFingerprint`: backend, transport, deployment, driver, auth, settings, limits, network shaping, and provider versions

Backend choice must not accidentally make two otherwise comparable runs incomparable. It must also never be omitted from result provenance.

Add to `PerfResult`:

```ts
interface PerfResult {
    // existing fields
    treatment: ProviderTreatment;
    treatmentFingerprint: string;
    correctnessTranscriptHash?: string;
}
```

### 11.3 Randomized paired execution

Run A/B/C in interleaved blocks on the same machine session:

```text
rep block 0: local STS2 -> WebHost STS2 -> TS native
rep block 1: WebHost STS2 -> TS native -> local STS2
rep block 2: TS native -> local STS2 -> WebHost STS2
```

Use a recorded Latin-square/random seed. This reduces thermal, cache, antivirus, and background drift. Warmups are treatment-specific and excluded from statistics.

### 11.4 Process and remote-resource accounting

Add process roles:

```text
vscodeMain
extensionHost
webview
sts
webHost
sqlServer
```

For the loopback tri-provider lane, report:

- client process resources
- provider process resources
- total client+provider CPU and working set

For a genuinely remote WebHost, do not sum unrelated machines into one pretend total. Report client cost and server cost separately, plus throughput/latency and server cost per million rows or GiB. The remote host exports run-scoped metrics through authenticated OTLP or a bounded test-only collector channel keyed by run/rep/treatment. Never expose a general unauthenticated metrics dump.

### 11.5 Provider-neutral phase markers

Emit the same markers for every provider:

```text
mssql.sqlDataPlane.provider.ready
mssql.sqlDataPlane.session.open.begin/end
mssql.sqlDataPlane.query.submit
mssql.sqlDataPlane.query.accepted
mssql.sqlDataPlane.query.firstMetadata
mssql.sqlDataPlane.query.firstPageProduced
mssql.sqlDataPlane.query.firstPageAccepted
mssql.sqlDataPlane.query.complete
mssql.sqlDataPlane.query.cancel.requested/ack/terminal
mssql.sqlDataPlane.session.close.begin/end
```

Existing Query Studio submit, firstResult, complete, and render markers remain. The current `firstResult` is row-driven, so an empty result set or message-only query may never produce it. The new first-metadata and first-page markers are the provider-neutral truth and explain the gap between user action, provider work, RowStore acceptance, and paint.

### 11.6 Required metrics

**Latency**

- provider cold ready
- API authentication and ticket issuance
- WebSocket connect and initialize
- SQL physical open
- submit to acceptance
- acceptance to first metadata
- first page produced, transmitted, received, durably accepted, and visibly painted
- query terminal and final render
- cancel request to provider ack and terminal
- session/runtime cleanup

**Throughput and work**

- rows/s and logical encoded MiB/s
- client-to-host and host-to-SQL bytes
- JSON serialize/deserialize CPU and allocations
- WebSocket send/receive time and heartbeat RTT
- STS2 read/encode/credit/post fields already emitted
- RowStore append/spill/materialization fields already emitted
- CPU per million cells and allocations per row/page

**Runtime dynamics**

- outbound queue and pending-RPC high water
- credit-stall duration and outstanding page bytes
- extension event-loop lag
- .NET GC pause/allocation/thread-pool queue
- process working set/heap/external memory
- telemetry drops
- forced cleanup count

### 11.7 Correctness precedes measurement

Every measured query emits a normalized transcript artifact. It includes metadata, decoded cell values or value digests, messages, row counts, page boundaries, database change, and terminal. A provider comparison is measurement-eligible only when:

- all transcript invariants pass
- expected provider-specific fidelity differences are explicitly declared
- no privacy canary leaked
- no instrumentation/collector overflow occurred
- no fault override was active unless the scenario is diagnostic

A transcript mismatch marks the rep invalid, not merely slower.

### 11.8 Scenario matrix

Minimum matrix:

| Family | Scenarios |
| --- | --- |
| Startup/connect | extension activation, provider ready, empty connect, warm reconnect, auth refresh |
| Small query | `SELECT 1`, empty result set, DML row count, one server error |
| Throughput | 10k, 100k, and 1M narrow rows; wide 1000x300; mixed types |
| Payload stress | 1 MiB cells, truncation edge values, binary/XML/JSON, many nulls |
| Event stress | 10k messages, 100 result sets, 1000 columns, rows-affected flood |
| Interaction | vertical/horizontal scroll during streaming, tab switches, cancellation during paint |
| Lifecycle | cancel before acceptance, cancel during rows, dispose, close, transport loss, server drain |
| Concurrency | Query Studio + metadata + OE sessions, many sockets/principals, slow consumer |
| Metadata/OE | cold/warm hydration, broad catalog, database switch, reconnect |
| Network | 0/20/80/200 ms RTT, jitter, constrained bandwidth, connection reset |
| Security/quotas | denied target, quota saturation, token expiry, ticket replay |

Shape the client-to-backend and backend-to-SQL legs independently. A loopback proxy such as a test-controlled TCP/WebSocket proxy is preferable to platform-specific privileged network commands.

### 11.9 Statistics and gates

- Record every raw rep and order position.
- Use current Welch/bootstrap machinery where valid, but add randomized-block analysis and confidence intervals for paired deltas.
- Establish variance before setting release thresholds.
- Use non-inferiority gates for interaction responsiveness and correctness-sensitive metrics.
- Report median, p90/p95, confidence interval, coefficient of variation, and outlier policy.
- Never hide an inapplicable metric. Mark it `notApplicable` with a reason.
- Separate cold-start and steady-state claims.

Initial performance hypotheses are not ship gates. Turn them into budgets only after the prototype produces stable baselines.

## 12. Test strategy additions

### 12.1 Shared semantic conformance

Run one provider-neutral suite against:

1. FakeBackend
2. scripted STS2 adapter
3. local spawned stdio STS2
4. loopback WebHost STS2
5. native TS fake-driver engine
6. live native TS/Tedious

Required invariants:

```text
C1 acceptance always settles
C2 accepted query has exactly one terminal
C3 no event after terminal
C4 metadata precedes pages
C5 page sequence and row offsets are gapless
C6 sink callbacks are serial
C7 sink failure is contained
C8 cancel/dispose/close are bounded
C9 transport loss settles all operations
C10 provider resources/tasks return to baseline
C11 capability claims match implemented behavior
C12 default diagnostics contain no secret, SQL text, or result value
```

### 12.2 WebHost-specific gates

- real Kestrel, real WebSocket, not controller mocks only
- ticket expiry/replay/concurrent redemption
- exact browser Origin and Node no-Origin policies
- wrong subprotocol, malformed JSON, JSON batch, fragmentation, oversize
- initialize gate and method authorization
- two principals with identical client IDs and no cross-control/data
- queue overflow/slow consumer
- disconnect during open, token acquisition, query read, credit wait, cancel, dispose, and close
- query execute response/event race and cancel-before-accept
- runtime drain under active work
- distributed ticket/quota tests for scaled staging
- proxy logging canaries
- target normalization/DNS rebinding/driver allowlist

### 12.3 Model and property testing

Use a deterministic virtual clock and seeded event generator to explore races among:

```text
open result | open cancel | socket close | query accept | first event |
ack | cancel | dispose | session close | runtime drain | provider hang
```

Every failing seed becomes a permanent scenario. Do not add retry-on-flake.

## 13. Implementation work packages

### WEB2-0: Decision ledger and protocol text

**Depends on:** none  
**Scope:** resolve section 15 questions 1-8, write the STS2 execute identity/method policy/effective-limit contract, define stable errors and close categories.  
**Required artifacts:** reviewed protocol Markdown, threat-model delta, compatibility table, wire examples.  
**Exit:** Core, client, security, and WebHost owners approve.  
**Stop condition:** no runtime or client protocol code before this approval.

### WEB2-1: Shared provider registry and identity

**Depends on:** WEB2-0 only for final names  
**Repositories:** `vscode-mssql`  
**Scope:** section 3.1-3.2, lifecycle ownership, passive status, settings migration, per-realm cache invalidation.  
**Tests:** single flight, retry, unknown kind, config change, multi-local coexistence, remote realm swap, deactivation drain, zero side effects from status.  
**Exit:** existing local/fake behavior passes on the new registry.

### WEB2-2: Shared capability/error/acceptance contracts

**Depends on:** WEB2-1  
**Repositories:** `vscode-mssql`, observability contracts  
**Scope:** section 3.3-3.5, compatibility projection, safe error registration, always-settled acceptance.  
**Tests:** compile-time exhaustive capability table, credential-provider tripwire, all acceptance terminal paths.  
**Exit:** Fake and current STS2 adapter pass the expanded conformance suite.

### WEB2-3: STS2 live-state and lifecycle hardening

**Depends on:** WEB2-0  
**Repositories:** `sqltoolsservice`  
**Scope:** handle identity, live query removal/tombstones, bounded pump disposal, awaited teardown registry, pending request settlement.  
**Tests:** million-query plateau, open-ID reuse, forced query abort, shutdown at every phase, task/connection leak assertions.  
**Exit:** all existing scenarios/replay tests remain green and new P0 gates pass.

### WEB2-4: STS2 boundary validation and host policy

**Depends on:** WEB2-0, WEB2-3  
**Scope:** request validators, initialization gate, method allowlist, effective policy through `session.start`, SqlClient-only remote composition, journal off/bounds.  
**Tests:** malformed/fuzz corpus, privileged diagnostics denial, replay parity.  
**Exit:** one malformed peer cannot fault the runtime or process.

### WEB2-5: Transport-neutral runtime extraction

**Depends on:** WEB2-3, WEB2-4  
**Scope:** handler-injected runtime, stdio adapter, unified stop state machine, runtime snapshots.  
**Tests:** in-memory and header-delimited binding parity, clean/fault completion, stop idempotency.  
**Exit:** current spawned stdio E2E is byte/semantics compatible.

### WEB2-6: WebSocket binding

**Depends on:** WEB2-5  
**Scope:** pinned-version handler, framing, final byte guard, one reader/writer, bounded FIFO, execute-ID routing.  
**Tests:** Kestrel loopback fragmentation, oversize, malformed, send failure, response/event race.  
**Exit:** full STS2 scenario corpus passes over WSS.

### WEB2-7: Loopback WebHost edge

**Depends on:** WEB2-6  
**Scope:** info/ticket/WSS/health endpoints, development auth, target policy, admission leases, idle/absolute lifetime, graceful drain.  
**Tests:** ticket state machine, route deny, quotas, cleanup, log canaries.  
**Exit:** standalone WebHost queries local/container SQL without ServiceLayer.

### WEB2-8: Remote vscode-mssql transport and adapter

**Depends on:** WEB2-1, WEB2-2, WEB2-7  
**Scope:** remote auth/bootstrap, WSS transport, hardened adapter, consent, fingerprints, strict portability.  
**Tests:** close/abort/deadline, bounded buffers, failed ack, reconnect without SQL replay, config/trust/account change.  
**Exit:** Query Studio executes through loopback WebHost and no scoped local STS path is touched.

### WEB2-9: Metadata, OE v2, and native language integration

**Depends on:** WEB2-8  
**Scope:** injected composition, metadata query caps/watchdog cancel, cache realm, OE consent/loss, no bridge/handoff.  
**Tests:** concurrent scoped consumers, transport loss, stale cache prevention, strict tripwires.  
**Exit:** the scoped portable feature set runs process-free in the portable Node composition.

### WEB2-10: Observability and support capsule

**Depends on:** WEB2-2, WEB2-5; may proceed in parallel with WEB2-7  
**Scope:** sections 9-10, OTel/diagnostics bridge, sequence fields, runtime snapshots, capsule/replay recipe, Debug Console.  
**Tests:** schema contract, overhead-off path, dropped-event accounting, privacy canaries, deterministic capsule snapshot.  
**Exit:** a forced race can be diagnosed from the capsule and replayed with a fake provider.

### WEB2-11: Perftest treatment matrix

**Depends on:** WEB2-1, WEB2-2  
**Repositories:** `perftest`, `vscode-mssql`, `sqltoolsservice`  
**Scope:** treatment/result schemas, randomized blocks, provider-neutral markers, process roles, correctness transcript gate, loopback WebHost orchestration.  
**Tests:** schema migration, deterministic order, same-scenario three-treatment run, invalidation on transcript mismatch.  
**Exit:** one report compares local STS2, loopback WebHost STS2, and TS native with honest total-resource accounting.

### WEB2-12: Outbound fairness and remote network optimization

**Depends on:** WEB2-6, WEB2-10, first WEB2-11 baselines  
**Scope:** byte-aware fair scheduler, configurable negotiated credit/window, slow-client policy, network-shaped profiles.  
**Tests:** metadata/cancel latency under large query, 0-200 ms RTT, bounded memory, no reorder.  
**Exit:** reviewed latency/throughput budgets pass without semantic drift.

### WEB2-13: Production Entra and Azure deployment

**Depends on:** WEB2-7 through WEB2-12  
**Scope:** protected API, distributed tickets/quotas, OBO or managed identity, token cache/pool isolation, Azure hosting, drain/alerts/runbook.  
**Exit:** security, privacy, chaos, scale, and token-expiry reviews pass in staging.

### WEB2-14: Browser composition

**Depends on:** WEB2-8 through WEB2-10  
**Scope:** browser entry, browser-safe auth/crypto/storage/diagnostics, bounded RowStore, native language only, portable OE set.  
**Exit:** claimed browser hosts pass `@vscode/test-web` without Node/local STS imports.

## 14. Coding-agent delivery rules

Every task PR must include:

1. the code change
2. unit/conformance tests
3. fault-path tests
4. instrumentation contract updates
5. privacy canary coverage
6. a short design-decision entry for any deviation
7. before/after runtime or perf evidence when the hot path changes
8. updated support/status snapshots where state changes

Forbidden shortcuts:

- no silent provider fallback
- no generic retry of open/execute
- no unbounded queue, map, tombstone, capture, or task
- no fire-and-forget async operation on a lifecycle path
- no raw provider exception or remote path in user telemetry
- no credential resolution during status/capability inspection
- no capability advertised from intention alone
- no perf result accepted before transcript correctness
- no production auth mode that relies on a loopback development secret
- no controller logic that bypasses the STS2 gateway/Core path

## 15. Open questions with recommended defaults

| # | Decision | Recommended default | Blocks |
| --- | --- | --- | --- |
| 1 | Product/operator model | Start as single-tenant enterprise/self-host preview; design isolation so multi-tenant is possible, but do not claim it yet. | WEB2-0 security model |
| 2 | Execute identity | Required for remote clients; additive negotiated support for local clients; every event carries execute ID. | WEB2-0/3/6/8 |
| 3 | Event sequence | Add monotonic per-query `eventSeq` as an optional negotiated field for diagnostics and validation. | WEB2-0 |
| 4 | Remote credit window | Parameterize through journaled policy; keep 4 initially, test 8/16 under RTT with byte cap before changing default. | WEB2-12 |
| 5 | Ticket proof of possession | Short-lived single-use bearer for preview; add DPoP/PKCE-style proof only if threat review requires it. | WEB2-7/13 |
| 6 | Initial database auth | SQL Login + direct SQL token for loopback proof; managed identity for first service-identity production lane; OBO when per-user SQL identity is required. | WEB2-7/13 |
| 7 | Remote journal | Off by default. Redacted capsule is the ordinary support mechanism. | WEB2-4/10 |
| 8 | Diagnostics RPCs | Ordinary users get ping and safe capsule/status only; capture mutation/export/state require operator policy or are omitted. | WEB2-0/4 |
| 9 | Socket session count | Allow multiple SQL sessions per runtime with strict caps; start with one active streaming query per socket if fairness is not yet implemented. | WEB2-7/12 |
| 10 | StreamJsonRpc package upgrade | Keep 2.25.28 and implement the small handler first; upgrade only in a separate dependency review with parity/load evidence. | WEB2-6 |
| 11 | App Service vs Container Apps | App Service for the first on-prem Hybrid Connections proof; either is viable for Azure SQL after operational review. | WEB2-13 |
| 12 | Actual HTTP streaming binding | Out of scope until a concrete consumer requires it. WSS is the named v1 transport. | None |
| 13 | Browser result persistence | Bounded memory-only first, clearly surfaced; persistent IndexedDB/OPFS only after quota/privacy design. | WEB2-14 |
| 14 | Plan parsing | Keep separate from the SQL provider. Ship JS/WASM parser, explicit remote plan service, or honest unavailable state. | WEB2-9/14 |

Unresolved questions must be assigned an owner and decision milestone in the project tracker. A coding agent must not convert a recommendation into an undocumented permanent protocol.

## 16. Release gates

### 16.1 Loopback engineering preview

- all P0 runtime issues in section 6 closed
- stdio and WSS semantic parity green
- no secret/SQL/result canary in standard logs, journals, status, URLs, or capsules
- bounded memory under million-query lifecycle and slow consumer
- Query Studio, Metadata, native language, and OE v2 scoped paths use remote provider only
- transport loss settles every operation exactly once and never reruns SQL
- tri-provider correctness/perf report generated

### 16.2 Hosted preview

- Entra API authorization and target policy reviewed
- distributed replay-safe tickets and quota leases tested
- managed identity/OBO pool isolation proven or pooling disabled
- graceful drain and absolute socket lifetime tested through real ingress
- support capsule, alerts, retention, and runbook operational
- Azure SQL plus declared private/on-prem topology pass chaos and load tests

### 16.3 Browser preview

- real `browser` entry and WebWorker bundle
- no Node/local STS/classic service import graph
- bounded results/storage behavior visible to users
- strict native language and OE command set
- exact CORS/Origin/ticket behavior on every claimed host

## 17. Suggested file map

### sqltoolsservice

```text
src/sts2/Microsoft.SqlTools.Sts2.Hosting/
  Sts2RuntimeSession.cs
  Sts2RuntimeSessionOptions.cs
  StdioSts2RpcHost.cs
  WebSocketJsonRpcMessageHandler.cs
  OutboundScheduler.cs
  RuntimeTaskRegistry.cs

src/sts2/Microsoft.SqlTools.Sts2.Runtime/
  Validation/
  Journaling/NullJournalWriter.cs
  Coordination/RuntimeSnapshot.cs
  Effects/HostDatabaseCredentialProvider.cs

src/sts2/Microsoft.SqlTools.Sts2.WebHost/
  Program.cs
  Authentication/
  Endpoints/
  Hosting/
  Policy/
  Admission/
  Observability/
```

### vscode-mssql

```text
extensions/mssql/src/services/sqlDataPlane/
  api.ts
  capabilityRegistry.ts
  backendFactory.ts
  sqlDataPlaneService.ts
  supportCapsule.ts

extensions/mssql/src/services/sts2/
  sts2Backend.ts
  validation/
  transports/serviceClientRpc.node.ts
  transports/webSocketRpc.ts
  remoteAuth.ts
```

### perftest

```text
packages/perf-contracts/src/treatment.ts
packages/perftest-cli/src/matrix/
packages/perftest-cli/src/providers/webHostOrchestrator.ts
packages/perftest-cli/src/collectors/remoteProviderMetrics.ts
packages/perftest-cli/src/regression/providerMatrix.ts
```

## 18. Definition of done

The WebHost provider is done only when it is another faithful binding of the SQL Data Plane contract, not a special mode with private exceptions. A user can choose local STS2, hosted STS2, or native TypeScript per session; capability and error behavior is explicit; every operation settles; memory and task ownership is bounded; default diagnostics are private; a support capsule explains runtime behavior; and the same perftest scenario can compare all three treatments without renaming the user workload or hiding provider cost.

## 19. Reference set

Internal references are the base design and the reviewed paths in section 2.1. Recheck these official references during implementation:

- StreamJsonRpc connection and extensibility: <https://microsoft.github.io/vs-streamjsonrpc/>
- StreamJsonRpc WebSocket handler API in newer releases: <https://microsoft.github.io/vs-streamjsonrpc/api/StreamJsonRpc.WebSocketMessageHandler.html>
- ASP.NET Core WebSockets: <https://learn.microsoft.com/aspnet/core/fundamentals/websockets>
- ASP.NET Core authentication, authorization, and rate limiting: <https://learn.microsoft.com/aspnet/core/security/>
- .NET OpenTelemetry observability: <https://learn.microsoft.com/dotnet/core/diagnostics/observability-with-otel>
- Microsoft identity platform OBO: <https://learn.microsoft.com/entra/identity-platform/v2-oauth2-on-behalf-of-flow>
- Microsoft.Data.SqlClient access-token guidance: <https://learn.microsoft.com/dotnet/api/microsoft.data.sqlclient.sqlconnection.accesstoken>
