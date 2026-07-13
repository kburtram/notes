# TypeScript Query Endpoint: Production Engineering Addendum

**Status:** Normative implementation addendum; conditional approval to prototype  
**Date:** 2026-07-13  
**Applies to:** `typescript_query_endpoint.md` dated 2026-07-13  
**Companion addendum:** `querystudio_web_backend_addendum.md`  
**Primary repositories:** `microsoft/vscode-mssql`, `microsoft/sqltoolsservice`, `kburtram/perftest` on `dev/query`  
**Suggested task prefix:** `TSQ2-n`; commit prefix `tsq2:`

## 0. How to use this addendum

The base design is approved as a direction: implement the SQL Data Plane domain API directly in TypeScript over Tedious, without cloning STS v2 JSON-RPC. This addendum tightens the parts that affect correctness, package viability, event semantics, type fidelity, memory safety, diagnostics, and three-provider benchmarking.

Normative terms:

- **MUST:** release-blocking correctness, privacy, security, or lifecycle rule.
- **SHOULD:** default design unless a reviewed deviation is recorded.
- **MAY:** optional and cannot weaken a MUST.

An agent must not turn a known fidelity gap into a cosmetic warning while still returning altered data as if it were exact. It also must not advertise a capability based on a driver README, old issue, or planned transcoder. Capabilities come from implemented tests against the exact pinned package.

## 1. Review outcome

Proceed in stages, with two distinct milestones:

1. **Engineering/dogfood provider:** proves the domain seam, lifecycle, paging, cancellation, observability, and performance on a declared supported subset.
2. **General provider:** requires exact scalar fidelity or explicit fail-closed behavior for types that Tedious cannot preserve, bounded large-value behavior, packaged-extension validation, and sustained conformance/soak/performance evidence.

The native path has compelling structural advantages for common queries: no service spawn, no stdio multiplexer, no JSON serialization boundary, direct RowStore backpressure, and same-process instrumentation. It also moves TDS parsing and cell conversion onto the extension-host event loop and inherits driver behaviors that differ from SqlClient. The design must optimize the whole product, not win rows/second while freezing completions, inline suggestions, metadata, or the Debug Console.

The provider identity used in code and reports is:

- backend kind: `ts-native`
- semantic implementation: `ts-native`
- deployment: `extension-local`
- transport: `inprocess`
- driver: `tedious`

## 2. Corrections and missing constraints found in review

### 2.1 Current SqlClient comparison baseline

The reviewed `sqltoolsservice` branch pins Microsoft.Data.SqlClient **6.1.5**. The base design discusses 7.0 capabilities. Benchmark and parity claims MUST compare against the actual pinned STS2 provider first. A future SqlClient upgrade is a separate treatment/version change and may alter both capabilities and performance.

### 2.2 Exact Tedious package, not a floating idea of Tedious

The `v20.0.0` source tag declares Node `>=22` and includes `@azure/identity`, Key Vault, and Always Encrypted-related code. The source tree also uses release automation, so its checked-in `package.json` version is not a sufficient runtime provenance value. The implementation MUST record:

- resolved npm package version
- lockfile integrity
- source commit/tag used for any patch
- Node runtime version
- package/bundle mode
- optional maintained patch revision

Pin an exact version for the first implementation. Do not use a caret range for a database driver on the hot path.

### 2.3 Always Encrypted and other driver claims need live proof

The base design labels Always Encrypted a hard gap based on historic issues, but the reviewed source contains column-encryption options and implementation scaffolding. That is not proof of product-ready support, and it is also not proof of absence. Default `security.alwaysEncrypted` to unsupported until a live fixture matrix proves read behavior, key-provider behavior, parameter behavior, error handling, and secret containment for the exact package. Use the same evidence rule for TDS 8 strict, native JSON/vector behavior, routing, and authentication variants.

### 2.4 Tedious request timeout is not a whole-query deadline

Tedious documents that its request timeout can be cleared after a response begins. A query that produces an early response and then stalls may exceed it. Therefore:

- set the domain's **absolute query deadline** with an extension-owned monotonic timer
- on expiry, issue cancel and classify the terminal as timeout
- use Tedious's request timeout only as a secondary guard, or set it to zero and rely on the domain timer plus `cancelTimeout`
- test a query that emits one row/message and then waits beyond the deadline

A `request.setTimeout(timeoutMs)` call by itself does not satisfy the SQL Data Plane timeout contract.

### 2.5 DONE tokens are statement boundaries, not the query terminal

Tedious emits `done`, `doneInProc`, and `doneProc` for statement/procedure completion. A batch can emit many of them. The request completion callback is the terminal fence. The engine MUST:

- open a result set only on `columnMetadata`
- close only the currently active result set on the first applicable DONE token or before the next metadata set
- never create a result set from a DONE token
- never double-close on `doneProc` after `doneInProc`
- aggregate rows-affected under a tested policy separate from result-set row counts
- wait for the request callback before choosing the query terminal

### 2.6 Connection-level messages need query-generation ownership

`infoMessage`, `errorMessage`, database changes, socket errors, and end events originate at connection scope. The adapter must not attach ad hoc listeners per query that leak or misattribute late events. Use one connection event router and an explicit active-query generation lease. Events are stamped with a monotonic driver sequence and routed only to the generation active when the token is observed. Late events after the terminal are diagnostics, not callbacks into the completed sink.

### 2.7 PLP large values prevent a strict memory claim

The reviewed value parser accumulates PLP chunks before returning a value. `maxCellBytes` truncation in the engine happens after that allocation. Therefore the v1 provider cannot truthfully claim that memory is bounded to `windowPages * pageBytes` for arbitrary MAX/XML/UDT values.

Required policy:

- advertise `types.largeValueStreaming=unsupported`
- expose an explicit provider read-limit behavior
- monitor external/array-buffer memory and memory-pressure aborts
- do not claim a full-value truncation digest if the provider limits the value before the full payload is read
- make PLP streaming or a maintained bounded parser patch a general-availability gate for untrusted large-value workloads

### 2.8 Approximate scalar values are not merely a tooltip problem

The reviewed parser converts decimal/numeric/money to JavaScript numbers and discards the original datetimeoffset offset. Once information is lost, displaying a warning does not make export, copy, AI analysis, or equality behavior correct.

Recommended policy:

- **Exact mode is the default.** On metadata for a type the provider cannot preserve, terminate before emitting its first data page with `SqlDataPlane.CapabilityUnsupported` and a provider-switch recommendation.
- **Lossy preview is an explicit dogfood/debug option**, never silent and never used for export, chat-to-data, automated tools, or official parity/perf correctness lanes.
- Upstream or maintain a narrow Tedious patch that returns decimal/numeric/money as exact strings and preserves datetimeoffset offset. Once live golden fixtures pass, advertise exact capabilities.

This is stricter than the base design's default P1/P2 recommendation because the stated project goal is functional correctness, not approximate browsing.

### 2.9 Package cost can erase the startup win

Tedious pulls a nontrivial dependency graph. A top-level import can increase extension parse/evaluation time even when `sts2-local` is selected. The provider MUST be lazy-loaded and packaged in a way that does not regress normal activation. Measure:

- VSIX size delta
- `dist` bundle size and source-map size
- extension activation parse/evaluation
- first dynamic import
- first connection
- memory after import but before connection

### 2.10 Current shared infrastructure is not ready for a third provider

The current `SqlDataPlaneService` still owns one cached backend and silently maps unknown settings to local STS. `Sts2Rpc` lacks close/abort lifecycle. `OpenSessionParams` still uses a partial boolean capability object. The native provider must depend on the shared registry/capability/query-acceptance work in the companion addendum rather than creating private substitutes.

## 3. Shared provider contract

This is the same normative contract as the WebHost addendum. Implement it once in `services/sqlDataPlane`.

### 3.1 Identity

```ts
export interface SqlBackendIdentity {
    readonly kind: "sts2-local" | "sts2-remote" | "ts-native" | "fake";
    readonly implementation: "sts2" | "ts-native" | "fake";
    readonly transport: "stdio-jsonrpc" | "wss-jsonrpc" | "inprocess";
    readonly driver: "sqlclient" | "tedious" | "fake";
    readonly deployment: "extension-local" | "webhost-loopback" | "webhost-remote" | "test";
    readonly realmId: string;
    readonly providerVersion: string;
    readonly driverVersion?: string;
    readonly protocolVersion?: string;
}
```

Every session snapshots this identity. It partitions status, diagnostics, cache, capability answers, and perf treatments.

### 3.2 Capability set with fidelity and limits

Use one versioned capability registry and derive the old boolean projection. A capability has support, fidelity, source, optional limit, and a stable reason code.

```ts
export interface SqlCapabilityValue {
    support: "supported" | "unsupported" | "conditional" | "degraded";
    fidelity?: "exact" | "normalized" | "lossy" | "notApplicable";
    source: "static" | "handshake" | "route" | "session" | "probe";
    limit?: number;
    unit?: "bytes" | "rows" | "pages" | "milliseconds" | "count";
    reasonCode?: string;
}
```

`canOpen` evaluates `SqlCapabilityRequirement[]` before credential resolution. Query-time metadata may still discover a type-fidelity requirement that was unknowable at open; that path fails explicitly before rows are delivered.

### 3.3 Query acceptance and lifecycle

Use the shared always-settled handle:

```ts
export interface QueryHandle {
    readonly clientQueryId: string;
    readonly accepted: Promise<QueryAcceptance>;
    readonly completion: Promise<QueryCompleteSummary>;
    cancel(): Promise<CancelAck>;
    dispose(): Promise<void>;
}
```

Native acceptance occurs after the driver accepts ownership of the Request, not merely after the JavaScript object is constructed. Cancellation before that point marks the local operation canceled and prevents submission. Add `outcomeCertainty: "known" | "unknown"` to terminal summaries. Socket loss, forced abort without a trustworthy provider terminal, and uncertain cancel are `unknown`; the UI must warn that database side effects may have occurred and never auto-retry the SQL.

### 3.4 Stable errors

At minimum add:

```text
SqlDataPlane.CapabilityUnsupported
SqlDataPlane.PolicyDenied
SqlDataPlane.ResourceLimit
SqlDataPlane.Client.Aborted
SqlDataPlane.Client.Timeout
SqlDataPlane.Transport.Closed
SqlDataPlane.Transport.Backpressure
SqlDataPlane.Provider.Internal
```

Tedious error strings and stacks are diagnostics, not product contracts. Whitelist and map driver codes such as login, socket, timeout, and cancel categories. Unknown driver codes map to a safe provider-internal category with a correlation ID.

### 3.5 Multi-provider registry

The activation-owned registry supports concurrent local providers, per-document choice, live default changes for future sessions, and explicit fallback. The TypeScript agent MUST consume this shared implementation. It must not add a second singleton, alternate setting namespace, or provider-selection cache.

## 4. Dependency, packaging, and supply-chain gate

Complete this gate before query-engine work, because a provider that cannot be safely packaged is not a viable architecture.

### 4.1 Dependency policy

- Add Tedious as an exact production dependency.
- Commit the lockfile and integrity metadata.
- Generate/update third-party notices and SBOM.
- Run license and vulnerability scans in CI.
- Record the exact driver version in `SqlBackendIdentity` and support capsules.
- Disable Tedious payload/token debug logging in all product modes.
- Do not use Tedious's Azure identity flows for the initial provider; reuse the extension's token source and pass only the resulting access token.

### 4.2 Lazy load

No module reachable from normal extension activation may statically import `tedious` or its Azure/Key Vault graph.

```ts
let tediousModulePromise: Promise<typeof import("tedious")> | undefined;

export function loadTedious(): Promise<typeof import("tedious")> {
    return (tediousModulePromise ??= import("tedious"));
}
```

The factory performs a runtime Node compatibility check before import. A mismatch reports an unavailable provider without breaking extension activation or other providers.

### 4.3 Packaging options spike

Evaluate and record:

1. bundle Tedious into a lazy chunk
2. externalize Tedious and ship its production dependency tree
3. a dedicated provider bundle loaded only when selected

Choose using measured VSIX size, activation parse time, dynamic-import time, source-map quality, and platform packaging reliability. Test packaged VSIX, not only the repository development host, on Windows, Linux, macOS, x64, and arm64 where supported.

### 4.4 Maintained driver patch policy

If exact numeric, datetimeoffset, or PLP streaming changes are required before upstream release:

- keep the patch narrow and covered by upstream-style unit/integration tests
- record upstream issue/PR and source commit
- use a reproducible package build with provenance/integrity
- isolate all assumptions behind `ITdsDriver`
- never edit generated `node_modules` as a build step

## 5. Native provider architecture

### 5.1 Module boundaries

```text
services/tsNative/
  tsNativeBackend.ts          provider factory/service, capabilities, availability
  tsNativeSession.ts          session state and active-query ownership
  queryEngine.ts              query lifecycle and event ledger
  resultSetLedger.ts          metadata/page/end/row-count rules
  pageBuilder.ts              compact page and byte accounting
  cellEncoder.ts              exact typed-cell mapping
  boundedEventLane.ts         sink serialization and deadlines
  memoryBudget.ts             logical/provider memory accounting
  driver/
    tdsDriver.ts              public engine port, no Tedious types
    tediousDriver.ts          all Tedious imports and event wiring
    fakeTdsDriver.ts          deterministic scripted implementation
  observability.ts
  status.ts
  supportCapture.ts
  overrides.ts
```

Only `tediousDriver.ts` imports Tedious. The engine imports neither `vscode` nor diagnostics singletons. Clock, ID source, scheduler, telemetry, hash, and fault injector are constructor dependencies.

### 5.2 Driver port

Normalize the driver into a small event model. Do not leak `Connection`, `Request`, or Tedious metadata objects into the engine.

```ts
export interface ITdsDriver {
    readonly name: "tedious" | "fake";
    readonly version: string;
    open(request: TdsOpenRequest, observer: TdsConnectionObserver, context: DataPlaneOperationContext):
        Promise<ITdsConnection>;
}

export interface ITdsConnection extends AsyncDisposable {
    readonly id: string;
    readonly state: "open" | "closing" | "closed" | "lost";
    execute(request: TdsExecuteRequest, observer: TdsQueryObserver, context: DataPlaneOperationContext):
        ITdsQueryLease;
    close(context: DataPlaneOperationContext): Promise<void>;
}

export interface ITdsQueryLease extends AsyncDisposable {
    readonly generation: number;
    readonly accepted: Promise<void>;
    readonly completed: Promise<TdsCompletion>;
    pause(reason: TdsPauseReason): void;
    resume(reason: TdsPauseReason): void;
    cancel(reason: "user" | "timeout" | "dispose" | "sessionClose"): Promise<TdsCancelResult>;
}

export type TdsQueryEvent =
    | { kind: "metadata"; driverSeq: number; columns: TdsColumn[] }
    | { kind: "row"; driverSeq: number; cells: readonly TdsCell[] }
    | { kind: "done"; driverSeq: number; token: "done" | "doneInProc" | "doneProc"; rowCount?: number; more: boolean }
    | { kind: "message"; driverSeq: number; message: TdsServerMessage }
    | { kind: "databaseChanged"; driverSeq: number; database: string };
```

The driver adapter owns listener installation/removal and guarantees that `completed` resolves once after all events already emitted for the generation.

### 5.3 Connection event router

Install connection listeners once. Maintain:

```ts
interface ActiveQueryLease {
    generation: number;
    clientQueryId: string;
    observer: TdsQueryObserver;
    terminal: boolean;
}
```

Rules:

- one active lease per connection
- increment generation for every submitted request
- stamp connection-level message/database events with the current generation at observation time
- ignore or route late events to diagnostics after terminal
- remove the active lease only after request callback and engine terminal handoff
- `end` or fatal socket failure marks the session lost and completes the active lease once
- login errors before open never create an `ISqlSession`

### 5.4 Session state machine

```text
creating -> opening -> open -> closing -> closed
                     |       |
                     +-> lost
```

- `openSession` owns one physical connection.
- `execute` while active throws `SqlDataPlane.Busy` synchronously.
- Close is idempotent and rejects new execute immediately.
- Closing an active query follows the shared conformance rule: the query terminal is `connectionLost` with `synthesized:true`, unless it had already reached another terminal.
- No connection pooling in v1.
- All provider listeners, timers, queues, and task promises are removed/settled by close or loss.

### 5.5 Open sequence

1. resolve backend and static requirements
2. check provider/package availability
3. validate profile/options without secrets
4. resolve password/token inside one absolute open deadline
5. construct the driver config with an option allowlist
6. connect
7. run server facts and `@@SPID` probes through the same one-request rule
8. install session event router
9. publish open session and negotiated capabilities

If any step fails after a socket exists, close/destroy it under a bounded cleanup deadline. Clear references to the credential-bearing config after connect settles. A missing password/token is a typed resolution failure and is never converted to an empty credential. An explicitly supplied empty SQL password remains a distinct value.

Recommended baseline driver options, all pinned by tests:

```text
rowCollectionOnDone=false
rowCollectionOnRequestCompletion=false
useColumnNames=false
requestTimeout=0                 # domain absolute timer is authoritative
cancelTimeout=<reviewed bound>
lowerCaseGuids=<golden parity choice>
appName=<safe product/provider/build label>
```

Use `execSqlBatch` for Query Studio batches. The product already performs GO and SQLCMD preprocessing above this layer, while raw batch execution preserves SET, SHOWPLAN, STATISTICS XML, transaction, and session semantics. Do not switch to `execSql` or parameterized wrappers without a separate semantic transcript review.

### 5.6 Query result-set ledger

The ledger, not ad hoc event callbacks, owns domain ordering.

```ts
interface ResultSetState {
    id: string;
    ordinal: number;
    columns: readonly ColumnMetadata[];
    nextPageSeq: number;
    nextRowOffset: number;
    rowCount: number;
    open: boolean;
}
```

Behavior:

- `metadata` closes any still-open previous result set defensively, then opens one new set and emits `onResultSetStarted` before rows.
- `row` requires an open set; otherwise it is a driver protocol violation.
- a DONE token closes an open set once and records its row count evidence
- DONE with no open set contributes only to rows-affected accounting
- next metadata cannot arrive until the previous set has been closed in the sink lane
- request completion closes a final open set, drains pages/events, then emits the one terminal
- `more` is diagnostic evidence, not a query terminal

Rows affected require live parity fixtures for DML, triggers, stored procedures, `SET NOCOUNT`, multiple statements, and errors. Do not assume summing every DONE rowCount matches SqlClient.

### 5.7 Page pipeline and backpressure

```text
Tedious token events
    -> cell encoding/page builder
    -> bounded page/event queue
    -> one serial sink lane
    -> RowStore durable acceptance
```

Memory accounting includes:

- one building page
- at most one blocked completed page
- queued pages under page and byte budgets
- one sink-in-flight page
- queued metadata/messages/terminal
- driver/parser buffering, reported separately as unknown or sampled provider memory

When a page is ready:

1. reserve queue byte/page budget
2. if unavailable, pause the Request and retain at most one blocked page
3. enqueue in query order
4. the lane invokes the sink
5. when `onRowsPage` resolves, release budget
6. resume at the configured low water

The default four-page concept is a maximum queue window, not a license to retain four pages plus arbitrary additional pages. Use both count and logical-byte caps.

Messages and metadata also use the bounded event lane. The provider must not build an unbounded 10,000-message promise chain. If the driver cannot be paused for a message flood and the hard event budget is exceeded, cancel with `SqlDataPlane.ResourceLimit` and one terminal rather than dropping messages.

### 5.8 Comparable byte definitions

Use two distinct metrics:

- `logicalEncodedBytes`: provider-neutral estimated bytes of the canonical compact representation
- `residentBytesEstimate`: provider-specific retained JavaScript memory estimate

`RowsPage.approxBytes` should use the shared logical estimator so RowStore policy and provider comparisons remain coherent. Do not call `JSON.stringify` on every native page merely to measure it. Implement an incremental estimator in the shared cell/page encoder and golden-test it against canonical serialization.

### 5.9 Sink containment

All sink methods, including synchronous ones, are wrapped. The lane enforces one callback in flight.

- A sink throw maps to `SqlDataPlane.Client.SinkError`.
- A sink callback deadline maps to `SqlDataPlane.Client.Timeout` or a dedicated safe sink-timeout reason.
- The driver request is canceled and queues are cleared.
- `QueryHandle.completion` settles independently, even when the sink promise never settles.
- `onComplete` is best effort after settlement and never blocks resource cleanup.
- No callback occurs after the terminal guard closes.

### 5.10 Absolute query deadline

Use a domain timer started at submission:

```ts
const deadline = clock.deadline(options.timeoutMs);
deadline.onExpire(() => query.requestCancel("timeout"));
```

The engine records cancellation cause. If timeout initiated cancellation, the terminal is `failed` with `SqlDataPlane.Client.Timeout`, not `canceled`. If the user initiated it first, the terminal is `canceled`. Races are resolved by one atomic terminal decision.

### 5.11 Cancel, dispose, and close

**Cancel**

- call `Request.cancel()` once
- acknowledgement is the request completion/cancel result attributable to the generation
- if the cancel-ack deadline expires, return `{acknowledged:false, uncertain:true}`
- continue to the terminal deadline
- Tedious `cancelTimeout` or socket loss may make the session lost

**Dispose**

- stop future sink delivery
- cancel the request
- wait under the dispose deadline
- if it stops, emit exactly one `disposed` terminal
- if it cannot stop, destroy/close the physical session, emit `disposed` once, and mark session lost with a forced-abort diagnostic

**Session close**

- reject new execute
- cause active accepted query to settle `connectionLost` if not already terminal
- close/destroy the connection under deadline
- remove listeners/timers and settle all internal promises

### 5.12 Event-loop discipline

Yielding only between 1000-row pages can still freeze the extension on wide or expensive cells. Add a CPU-slice governor:

```ts
interface EngineSlicePolicy {
    maxRowsBeforeYield: number;
    maxSynchronousMs: number;
}
```

Measure work since the last yield. When either limit is reached:

- pause the Request
- schedule continuation with `setImmediate`
- resume only when queue budgets permit

Record pause reason separately for sink backpressure, CPU yield, memory pressure, and user/debug fault. Do not adapt page/tuning values invisibly in official performance runs. Every effective value is stamped in diagnostics and the treatment fingerprint.

### 5.13 Memory-pressure circuit breaker

Sample `process.memoryUsage()` and event-loop health at bounded intervals while a native query is active. A configurable provider budget may terminate a query/session before the extension host reaches catastrophic OOM. The terminal is `SqlDataPlane.ResourceLimit`, and the support capsule records heap/external/array-buffer snapshots and the exact limit. This is a last-resort guard, not a substitute for PLP streaming.

## 6. Type fidelity and cell encoding

### 6.1 Golden parity is the contract

The native provider emits the same domain `CompactPage` and `CellValue` shapes consumed by `decodeCell`, RowStore, export, and webviews. Prose descriptions are secondary. The acceptance mechanism is a golden fixture runner that executes the same SQL through `sts2-local` and `ts-native` against the same server and compares:

- result-set and column metadata
- raw compact values
- type hints
- null bitmap bytes
- decoded cells
- truncation status/prefix/digest
- messages and structured server fields
- result-set row counts and total rows affected
- terminal status/error identity

Expected divergence must be encoded as a reviewed fidelity policy, not ignored by a broad snapshot update.

### 6.2 Exactness matrix

Start with this default capability position until live tests and any driver patch change it:

| Type/family | Native policy | Capability |
| --- | --- | --- |
| bit, tinyint, smallint, int | exact | supported/exact |
| bigint | exact string carrier | supported/exact |
| real/float | IEEE behavior, non-finite typed wrapper | supported/exact to source type |
| decimal/numeric | fail closed in exact mode until raw exact string path exists | unsupported exact |
| money/smallmoney | fail closed in exact mode until exact scaled integer/string path exists | unsupported exact |
| uniqueidentifier | exact normalized casing | supported/exact |
| binary/varbinary | exact within provider read policy | supported/conditional |
| varchar/nvarchar/char/nchar | exact decoded text within provider read policy | supported/conditional |
| XML/JSON text | exact within provider read policy; native SQL JSON wire type separately probed | conditional |
| date/datetime/smalldatetime | exact to SQL precision | supported/exact |
| time/datetime2 | use `nanosecondsDelta`, prove scales 0-7 | supported after fixtures |
| datetimeoffset | fail closed in exact mode until original offset is preserved | unsupported exact |
| sql_variant | only claim exact for every underlying tested supported type | conditional |
| CLR UDT | binary exact; semantic transcoding separately negotiated | conditional |
| vector | text exact only when the engine representation is proven; binary transcode staged | conditional |
| spatial | binary transport first; WKB transcode staged | conditional |
| PLP/MAX | value may be exact but transient memory is unbounded without patch | degraded/conditional |

### 6.3 Exact-mode failure timing

When `columnMetadata` reveals a column whose value cannot be preserved under the query's required fidelity:

1. emit no result-set start or rows to the feature sink
2. cancel the driver request
3. settle acceptance as accepted, because SQL was submitted
4. settle query completion as failed with `SqlDataPlane.CapabilityUnsupported`
5. include missing capability IDs and alternative providers
6. mark the session reusable only if cancel completed cleanly; otherwise mark it lost

This avoids a partially rendered result that looks authoritative.

### 6.4 Lossy preview

Lossy preview is allowed only behind an explicit development setting/Debug Console override and must:

- be visible in session and result-set status
- mark affected columns/cells as inexact/normalized
- disable export, copy-as-exact, chat-to-data, automated analysis, and parity correctness eligibility
- stamp the override in the support capsule and perf treatment
- never be the default or an automatic fallback

### 6.5 Numeric driver patch target

The preferred driver improvement returns exact decimal/numeric/money carriers before JavaScript-number conversion. The adapter then formats invariant strings and reuses existing typed decimal wrappers. Tests cover precision 1-38, scale 0-38, signs, min/max values, trailing zeros, scientific-looking values, and sql_variant.

### 6.6 datetimeoffset driver patch target

Preserve the signed offset minutes in the returned value or metadata. The cell encoder produces the same invariant representation as STS2, including scale and original offset. Tests cover extreme offsets, daylight-saving boundaries, scale 0-7, and values crossing UTC dates.

### 6.7 Large value policy

Until chunk streaming exists, expose two limits:

- `maxCellBytes`: retained/display prefix policy
- `maxProviderReadBytes`: maximum provider value the native path is willing to materialize

If a server-side/provider read limit prevents reading the full value, emit a distinct status such as `providerReadLimit` and do not fabricate a full-value SHA-256 digest. Any new typed cell status is added to the shared domain contract and supported by STS2/fake conformance projections.

### 6.8 Vector transcode gate

Do not advertise `types.vectorBinaryV1` until all are true:

- the exact server/TDS combination exposes a reliable vector column identity
- text parsing handles whitespace, dimensions, malformed values, NaN policy, and limits
- float32 round-trip equivalence is proven against SqlClient vector results
- binary layout, endianness, byte length, and base64 match the existing typed cell fixture
- large dimensions are bounded
- query and per-cell failure behavior is defined

If the driver exposes only an ordinary varchar with no reliable type identity, do not guess from a string that looks like `[1,2,3]`.

### 6.9 Spatial transcode gate

Ship spatial WKB only after a dedicated parser/writer review:

- preserve SRID, Z, and M
- define curve/compound/collection behavior
- validate malformed and adversarial UDT buffers
- bound points, rings, parts, and output bytes
- include attribution for any MIT-derived parser
- compare against SqlClient/Microsoft.SqlServer.Types fixtures

Before that, keep raw UDT binary and advertise spatial rendering unsupported.

## 7. Authentication and profile mapping

### 7.1 Shared preparation

Reuse `prepareConnection` and the extension's SQL token source. The provider does not create a second account store, token cache, or auth-type parser.

### 7.2 Credential timing

Credentials are resolved only after:

- provider availability
- static capability check
- profile/option validation
- provider choice/fallback decision
- user consent where applicable

Resolution, driver construction, and connect share one absolute open deadline. On failure, references to password/token-bearing config are cleared before the error leaves the factory.

### 7.3 Supported first modes

| Auth kind | Native action |
| --- | --- |
| SQL Login | Tedious `default`; exact user/password from deferred provider |
| Entra/bearer | Tedious access-token auth; acquire a fresh SQL-resource token per physical open |
| Integrated | typed unsupported, suggest `sts2-local` |
| Service principal/default/managed identity | remain unsupported until the shared profile policy supports them; do not reinterpret |

The backend must not use Tedious's own interactive identity UI. VS Code remains the user-consent and account-selection authority.

### 7.4 Token checks

Before driver construction validate safe token metadata already available from the shared source:

- expected account/tenant binding
- SQL audience/resource through the shared acquisition path
- expiry with the existing freshness margin

Never log the token, claims body, or token hash. A session does not refresh mid-login because TDS authentication occurs at physical open. Reopen is explicit after auth expiry or account change.

## 8. Capability policy and provider switching

### 8.1 Static capability statement

The factory can answer without loading Tedious. A conservative initial statement:

```text
auth.sqlLogin                 supported
auth.entraToken               supported
auth.integrated               unsupported
connect.tcp                   supported
connect.localdb               unsupported
exec.streamingRows            supported
exec.multipleResultSets       supported
exec.cancel                   supported
exec.dispose                  supported
exec.compactRows              supported
types.typedCells              conditional
types.decimalExact            unsupported until patch
types.datetimeOffsetOriginal  unsupported until patch
types.largeValueStreaming     unsupported
types.vectorBinaryV1          conditional
types.spatialWkbV1            conditional
metadata.catalogSql           supported
diag.resumeAfterDisconnect    unsupported
```

Capabilities that depend on the loaded driver version or live server become session/route/probe values. Static answers must not optimistically say supported.

### 8.2 Provider fallback

When the native provider cannot open a profile, return all missing capabilities before secrets. The shared policy decides prompt/auto/off. Auto fallback is visible through status and diagnostics, and a one-time user notification identifies the actual provider. No feature assumes a native session because the setting requested one; it uses `session.backendInfo`.

### 8.3 Runtime type fallback

A result type discovered after query submission cannot be rerun automatically on STS2. The query may have side effects. Fail the current query explicitly and offer to reconnect/switch for a future run. Never execute the same SQL again as a hidden fidelity fallback.

### 8.4 Provider and host capabilities remain separate

`plan.estimated` and `plan.actual` may indicate the provider can execute the required SET/batch semantics. Plan XML parsing/rendering is a Query Studio host capability. The native provider must not claim plan graph support merely because it can return SHOWPLAN XML.

## 9. Observability contract

### 9.1 Provider-neutral events

Emit the shared lifecycle vocabulary used by all providers:

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
```

Every event includes backend identity, operation ID, trace, provider/session sequence, safe status/reason, and treatment ID in PERF_MODE.

### 9.2 Native diagnostic family

Register a single family in the observability contract:

```text
sqlDataPlane.tsNative.driver.load
sqlDataPlane.tsNative.connection.open
sqlDataPlane.tsNative.connection.event
sqlDataPlane.tsNative.query.driverEvent
sqlDataPlane.tsNative.query.pageBuild
sqlDataPlane.tsNative.query.queue
sqlDataPlane.tsNative.query.pause
sqlDataPlane.tsNative.query.sink
sqlDataPlane.tsNative.query.cancel
sqlDataPlane.tsNative.query.terminal
sqlDataPlane.tsNative.runtime.snapshot
sqlDataPlane.tsNative.memoryPressure
sqlDataPlane.tsNative.invariantViolation
```

Do not emit one rich event per cell. Exact aggregate counters are maintained in memory and emitted at terminal. Per-page detail is rich/perf mode only and bounded.

### 9.3 Query aggregate

At terminal emit:

- driver event counts by kind
- result sets, columns, rows, cells, nulls
- logical encoded bytes and resident estimate
- bytes by type family
- page count, row/page and byte/page histograms
- page-build/cell-encode/hash time
- queue wait, sink wait, pause time by reason
- event-loop yields and max synchronous slice
- first metadata/page/accept timing
- cancel ack and terminal timing
- error/message counts
- driver completion lag after last token
- cleanup duration and forced-abort flag

### 9.4 Runtime dynamics

During an active native query, capture transition snapshots and periodic rich/perf samples:

- session/query state and generation
- event queue pages/items/bytes and high water
- building/blocked/in-flight page sizes
- driver paused state and pause reasons
- timers/deadlines remaining
- heap used/total, external memory, array buffers, RSS
- event-loop utilization and delay histogram
- process CPU delta
- active resource categories through supported Node APIs
- telemetry sink health/drops
- memory budget and pressure state

Avoid undocumented Node internals as a required metric. If an exact parser/socket buffer size is not available through a supported driver port, report `available:false` and rely on process/external-memory evidence.

### 9.5 Trace and sequence

- `providerSeq`: monotonic per provider service
- `sessionSeq`: monotonic per native session
- `queryEventSeq`: monotonic per query domain event
- `driverSeq`: monotonic per normalized driver event
- `clientQueryId`: random local query identity

The support timeline can reconstruct driver -> page -> queue -> sink -> terminal order without relying on timestamps alone.

### 9.6 Privacy classification

Standard diagnostics contain:

- SQL text: never plain; HMAC/ephemeral digest only when correlation is needed
- server/database/user: protected digest or omitted
- result values: never
- password/token: never, including hashes
- error text: mapped stable code; raw detail only in explicitly elevated encrypted capture
- column names/type names: classified metadata, redacted/digested according to policy

A raw SHA of common SQL is not automatically safe. Use keyed correlation where appropriate.

## 10. Support capsule and Debug Console

### 10.1 Native support capsule

Use the shared capsule schema from the WebHost addendum. Native additions:

- resolved Tedious version/integrity/patch revision
- Node runtime and packaged bundle mode
- effective driver config with secrets and raw target removed
- connection/query generation timeline
- safe transaction/session facts, current-database change sequence, and digest of effective session options
- type-fidelity capability snapshot and any lossy override
- driver token/event shape counts
- queue/pause/yield timeline
- event-loop and memory snapshots
- exact fault-injection seed/knobs
- listener/timer/resource counts before and after

A deterministic fake-driver script can be generated from shape and timing events to reproduce ordering, cancellation, sink, and memory-pressure behavior without SQL/result values.

### 10.2 Debug Console page

Add a provider-neutral SQL Data Plane page with a Native section:

- provider load/package/version state
- capability matrix and reasons
- sessions, SPID, database, generation, active query
- queue/page/sink state
- event-loop/memory charts
- recent stable errors/invariants
- effective debug overrides
- support capsule export

Debug actions:

```text
selectDefaultProvider
selectDocumentProvider
cancelQuery
closeSession
simulateConnectionLoss
applyCapabilityMask
applyFaultProfile
exportSupportCapsule
```

Fault actions are available only when the existing debug/session-diagnostics policy permits them. They are forbidden in official measurement passes.

## 11. Fault injection

Implement fault injection at the `ITdsDriver` boundary so fake and live decorated drivers use the same vocabulary:

```ts
export interface TsNativeFaultProfile {
    seed: number;
    openDelayMs?: number;
    openFailure?: "auth" | "network" | "timeout";
    delayEveryRows?: { rows: number; ms: number };
    delayEveryPageMs?: number;
    dropAfterDriverEvents?: number;
    dropAfterPages?: number;
    hangOnCancel?: boolean;
    hangOnClose?: boolean;
    malformedEventAt?: number;
    memoryPressureAfterBytes?: number;
    sinkDelayMs?: number;
}
```

Rules:

- deterministic from seed
- visible in status/capsule
- unknown keys ignored with a diagnostic
- capability masks can turn support off, never fabricate support on
- official perftest validates no fault or lossy override is active
- fault/override settings are application/debug controlled, never workspace-authoritative in an untrusted workspace
- setting changes apply to future sessions; a live Debug Console action may affect only the explicitly selected diagnostic session and records the change

## 12. Three-provider performance laboratory

The canonical framework is shared with the WebHost addendum. One Query Studio scenario runs under treatments:

```text
sts2-local   = STS2 + stdio-jsonrpc + SqlClient + local process
sts2-remote  = STS2 + wss-jsonrpc + SqlClient + loopback/remote WebHost
ts-native    = native domain engine + inprocess + Tedious
```

### 12.1 Treatment and environment identity

Add first-class treatment data to `PerfResult`. Keep `environmentHash` for controlled comparability and a separate `treatmentFingerprint` for backend/transport/driver/auth/tuning/network/version facts. The same `scenarioId` must be comparable across treatments. Settings merge in this fixed order: scenario defaults -> treatment settings -> run/diagnostic override. Activation-time treatment settings use the existing pre-launch `ScenarioSpec.userSettings` path. Persist the fully resolved setting snapshot and digest. Generate required process roles and `noErrors.sources` from the treatment, so `ts-native` does not require an STS process and WebHost treatments do require their provider process/collector.

### 12.2 Randomized blocks

Run treatments in recorded Latin-square/randomized-block order per repetition to reduce thermal/cache drift. Warm up each provider separately. The report includes order position and warmup policy.

### 12.3 Native-specific cold phases

Separate:

- extension activation without native import
- dynamic provider import
- provider construction
- credential resolution
- TCP/TLS/login open
- server-facts probe
- first query acceptance

This proves that lazy packaging preserves normal activation and shows the real first-use cost.

### 12.4 Total-resource fairness

For loopback comparison:

- `sts2-local`: extension host + STS process
- `sts2-remote`: extension host + WebHost process
- `ts-native`: extension host only

Report both component and total CPU/working set. Also report extension-host event-loop delay separately because moving work into-process can improve total cost while degrading interactivity.

For remote WebHost, report client and server costs separately. Do not add memory from different machines into one synthetic number.

### 12.5 Provider-neutral markers

Use the same markers as section 9.1 plus existing Query Studio markers. Add provider identity and treatment ID to connect/query submit markers. `mssql.queryStudio.query.firstResult` remains, but it is row-driven and does not cover empty or message-only results. Add provider-level first metadata/first page produced/first page accepted so a slow render is not blamed on TDS and a slow TDS page is not blamed on React.

### 12.6 Native metrics

- dynamic import duration and allocated memory
- connection/login and server probe duration
- driver events/s, rows/s, cells/s, logical MiB/s
- page build, cell encode, hash, queue, and sink wait
- pause duration by backpressure/CPU/memory
- event-loop delay p50/p95/p99 and max
- event-loop utilization during measured window
- heap/external/array-buffer allocation deltas
- CPU per million rows/cells
- maximum synchronous slice
- cancellation ack/terminal and forced socket close
- memory-pressure/resource-limit events
- listener/timer/resource baseline delta after cleanup

### 12.7 Correctness eligibility

Before a rep is measurement-eligible:

- transcript invariants pass
- raw/decoded cells match the golden expectation
- no exact-mode unsupported type appeared
- no lossy preview/fault/capability mask is active
- no telemetry/collector overflow occurred
- provider reports the expected identity/version

Expected capability differences are not silently normalized away. A scenario requiring exact decimal is either run only on capable treatments or records a capability-denied result as a functional comparison, not a throughput result.

### 12.8 Core scenario matrix

Use existing Query Studio shapes and add missing lanes:

| Family | Required scenarios |
| --- | --- |
| Import/startup | normal activation with native unselected; first native selection; warm native reuse |
| Connect | SQL Login, Entra token, bad auth, bad TLS, unreachable host, cancel during open |
| Small | `SELECT 1`, no rows, DML rowcount, one error, PRINT |
| Throughput | 10k/100k/1M narrow; 1000x300 wide; mixed null/type matrix |
| Payload | large binary/XML/JSON/MAX; provider read limit; truncation thresholds |
| Event pressure | 10k messages; 100 result sets; many DML DONE tokens; stored procedure events |
| Fidelity | decimal 1-38, money, datetimeoffset, time/datetime2 scale 0-7, bigint, GUID, variant |
| Typed features | vector text/binary, spatial binary/WKB, JSON, UDT failures |
| Interaction | scroll/tab/completion/metadata activity while 100k rows stream |
| Lifecycle | cancel before submit, cancel after first row, timeout after first response, dispose, close, loss |
| Concurrency | multiple sessions, Query Studio + Metadata + OE, repeated SQLCMD `:connect` |
| Soak | 1k+ open/execute/cancel/dispose/close cycles, heap/resource plateau |

### 12.9 Statistical posture

- First reports are exploratory, not default-flip evidence.
- Establish variance with randomized paired blocks.
- Use existing Welch/bootstrap tools plus paired delta confidence intervals.
- Gate interaction and event-loop metrics by non-inferiority.
- Separate cold-start and steady-state conclusions.
- Report inapplicable metrics explicitly.
- Keep raw reps and treatment order in artifacts.

### 12.10 Default-flip evidence

Do not propose making `ts-native` default until:

- all shared conformance and supported-type golden fixtures pass
- exact numeric and datetimeoffset policy is resolved
- large-value policy is accepted and protected
- package/activation budgets pass
- no leak in the nightly soak for at least the reviewed stability window
- interaction/event-loop non-inferiority passes
- total-resource and latency baselines show a meaningful benefit
- dogfood has provider-attributed support data and rollback capability

## 13. Testing strategy

### 13.1 Layered gates

| Layer | Scope | Gate |
| --- | --- | --- |
| N1 | page builder, encoder, ledger, queue, deadlines with fake clock | PR |
| N2 | `ITdsDriver` scripted fake and fault profiles | PR |
| N3 | shared SQL Data Plane conformance as third provider | PR |
| N4 | seeded lifecycle/model-race generator and invariant checker | PR quick, nightly full |
| N5 | live SQL behavior and golden cell parity against current STS2/SqlClient | nightly/pre-merge lane |
| N6 | packaged VSIX/platform smoke | nightly/release |
| N7 | Query Studio/Metadata/OE product E2E | nightly |
| N8 | perf matrix | scheduled |
| N9 | soak/leak/memory/event-loop | nightly |
| N10 | privacy canaries/support-capsule snapshot | PR |

### 13.2 Required shared invariants

```text
N-I1 acceptance always settles
N-I2 accepted query has exactly one terminal
N-I3 no sink event after terminal
N-I4 result metadata precedes rows
N-I5 page sequence/offset are gapless
N-I6 sink callbacks never overlap
N-I7 sink throw/hang is contained
N-I8 cancel/dispose/close finish or force-abort under deadline
N-I9 connection messages are attributed to the correct generation
N-I10 listeners/timers/tasks/resources return to baseline
N-I11 default diagnostics contain no SQL, result value, password, or token
N-I12 every advertised capability has a green implementation fixture
```

### 13.3 Tedious event-semantic fixtures

Test at least:

- multiple SELECTs in one batch
- SELECT + DML + SELECT
- stored procedure with nested statements and row counts
- triggers producing additional DONE/message tokens
- `SET NOCOUNT ON/OFF`
- RAISERROR/THROW severities and line/procedure fields
- PRINT interleaving
- database `USE` change
- error followed by continued batch output
- cancel during rows and during server wait
- timeout after an early result/message
- connection end before request callback
- late message/error after terminal fence

### 13.4 Type matrix

Live fixtures compare exact raw and decoded values. Include boundary values, not friendly examples:

- numeric/decimal precision 1, 15, 16, 18, 28, 38 and all relevant scales
- money min/max and values not exactly representable as binary float
- bigint min/max
- time/datetime2 scale 0-7
- datetimeoffset offsets -14:00 through +14:00 and date-crossing cases
- GUID case/order
- UTF-8 and supplementary Unicode
- binary sizes around every truncation/page/read boundary
- XML/JSON/MAX null/empty/large
- sql_variant of supported/unsupported underlying types
- vector dimensions and malformed representations
- spatial SRID/Z/M/curve/collection/malformed buffers

### 13.5 Property/model testing

Generate deterministic sequences of:

```text
metadata | row | done | message | databaseChange | callback |
cancel | timeout | dispose | close | socketLoss | sinkResolve | sinkReject
```

Run them through a simple reference state machine and the engine. Persist every failing seed as a named regression. Flakiness is a P0 bug and is not hidden by retries.

### 13.6 Leak and soak tests

Record before/after:

- heap/external/array-buffer memory after forced GC in test hosts
- active sessions/queries
- driver listener counts
- timers and supported active resource categories
- registry entries
- support-capture ring bytes

Run repeated normal, error, cancel, timeout, loss, and forced-abort cycles. The expected steady state is a bounded plateau, not necessarily byte-identical memory after each iteration.

### 13.7 Package/runtime tests

- selected provider works from packaged VSIX
- unselected provider does not import Tedious
- unsupported Node runtime leaves other providers healthy
- source maps identify native engine/driver frames
- all supported OS/arch packages install without optional native build steps
- SBOM/license/integrity artifacts are present

## 14. Implementation work packages

The registry/capability/acceptance foundation is shared with `WEB2-1` and `WEB2-2` in the companion addendum. Implement it once. The TypeScript provider depends on it.

### TSQ2-0: Decision and dependency spike

**Depends on:** none  
**Scope:** pin exact Tedious package, choose packaging mode, ratify exact-mode policy, large-value preview/GA policy, and initial capability statement.  
**Artifacts:** dependency report, VSIX/bundle measurements, runtime/platform matrix, decision log, driver gap fixture plan.  
**Exit:** provider can be loaded lazily from a packaged extension.  
**Stop condition:** no full engine implementation until package viability and fidelity policy are reviewed.

### TSQ2-1: Consume shared provider foundation

**Depends on:** companion `WEB2-1/2` or equivalent shared PRs  
**Scope:** register `ts-native` factory/identity/static capabilities, per-document selection, passive status, fallback integration.  
**Tests:** no import on passive status/unselected activation, provider choice/fallback, multi-local sessions.  
**Exit:** skeleton provider can report available/unavailable without connecting.

### TSQ2-2: Driver port and fake driver

**Depends on:** TSQ2-0  
**Scope:** `ITdsDriver`, event union, connection/query leases, fake driver, virtual clock/scheduler, deterministic faults.  
**Tests:** listener ownership, generation routing, all completion/error races.  
**Exit:** engine tests require no Tedious or VS Code.

### TSQ2-3: Tedious connection adapter

**Depends on:** TSQ2-0, TSQ2-2  
**Scope:** lazy import, option allowlist, SQL Login, open/close, server facts, connection event router, error mapping.  
**Tests:** local live `SELECT 1`, bad auth/network/TLS, open cancel/timeout, listener cleanup.  
**Exit:** one session can open/close reliably from packaged extension.

### TSQ2-4: Query lifecycle and result-set ledger

**Depends on:** TSQ2-2, TSQ2-3  
**Scope:** acceptance, one-active-query, metadata/row/DONE/callback rules, terminals, server messages, database changes.  
**Tests:** section 13.3 and shared conformance ordering.  
**Exit:** N3 passes for non-paged scalar fixtures.

### TSQ2-5: Bounded paging and sink lane

**Depends on:** TSQ2-4  
**Scope:** page builder, logical bytes, queue budgets, pause/resume, sink deadlines, CPU yields, cancel/dispose/close.  
**Tests:** slow/hung/throwing sink, 10k messages, wide rows, memory high water, timeout after first response.  
**Exit:** full N3 lifecycle/backpressure suite passes.

### TSQ2-6: Exact cell encoder and driver fidelity patch

**Depends on:** TSQ2-5  
**Scope:** all scalar/binary/text/date typed cells, exact numeric/money and datetimeoffset path or fail-closed behavior, truncation/read-limit statuses.  
**Tests:** golden matrix section 13.4.  
**Exit:** supported exact-type transcript parity is green; unsupported types fail before rows.

### TSQ2-7: Entra token auth and secret containment

**Depends on:** TSQ2-3, shared auth preparation  
**Scope:** fresh token per open, freshness/account/tenant checks, credential object lifetime, integrated typed failure.  
**Tests:** Entra live lane, near-expiry, account drift, token/password canaries.  
**Exit:** SQL Login and one Entra lane supported.

### TSQ2-8: Native observability and support capsule

**Depends on:** TSQ2-2 through TSQ2-5  
**Scope:** sections 9-10, provider-neutral markers, aggregate/runtime snapshots, Debug Console, deterministic fake replay recipe.  
**Tests:** observability schema, zero-sink overhead, drop accounting, capsule snapshot/privacy.  
**Exit:** injected lifecycle race is diagnosable and replayable from capsule.

### TSQ2-9: Capability UX and exact-mode routing

**Depends on:** TSQ2-1, TSQ2-6  
**Scope:** result-type fail-closed UX, provider switch suggestion, per-document status, host-vs-provider capability split, export/AI exactness gates.  
**Tests:** integrated profile fallback, decimal/datetimeoffset runtime denial, no automatic SQL rerun.  
**Exit:** unsupported fidelity is visible and safe.

### TSQ2-10: Vector transcode

**Depends on:** TSQ2-6 and proven type identity  
**Scope:** section 6.8 with dimension/size limits and typed cell parity.  
**Exit:** all vector fixtures pass; otherwise capability stays conditional/unsupported.

### TSQ2-11: Spatial transcode

**Depends on:** TSQ2-6  
**Scope:** section 6.9, parser/writer review, licensing, adversarial bounds.  
**Exit:** spatial fixtures pass including declared curve policy; otherwise capability stays unsupported.

### TSQ2-12: Perftest treatment matrix and native collectors

**Depends on:** shared matrix work and TSQ2-5/7/8  
**Scope:** section 12, dynamic-import phase, event-loop/memory metrics, total-resource rollup, transcript eligibility.  
**Exit:** one same-scenario report contains all three providers with randomized order.

### TSQ2-13: Consumer integration

**Depends on:** TSQ2-6 through TSQ2-9  
**Scope:** Query Studio, SQLCMD `:connect`, Metadata, OE v2, auxiliary sessions, plan execution capability.  
**Tests:** product E2E, concurrent sessions, watchdog/recycle, strict no-classic bypass for scoped features.  
**Exit:** supported scoped consumers run through native provider.

### TSQ2-14: Soak, packaging, and preview gate

**Depends on:** TSQ2-0 through TSQ2-13  
**Scope:** N6-N10, nightly stability, package/platform matrix, performance baseline, support docs, rollback.  
**Exit:** engineering preview criteria in section 17.1 pass.

### TSQ2-15: Large-value/general-provider gate

**Depends on:** measured preview data  
**Scope:** PLP streaming/maintained bounded parser or an approved fail-closed server/provider read policy, adversarial memory tests, final capability.  
**Exit:** general-provider criteria in section 17.2 pass.

## 15. Coding-agent delivery rules

Every task must include:

1. code and focused tests
2. lifecycle/fault tests
3. instrumentation contract changes
4. privacy canaries
5. package/build evidence when dependencies change
6. a decision-log entry for divergences
7. before/after perf evidence for hot-path changes
8. status/support-capsule updates for new state

Forbidden shortcuts:

- no top-level Tedious import in normal activation graph
- no silent numeric or temporal precision loss
- no automatic query rerun on provider switch
- no unbounded event/page/message queue
- no request timeout used as the sole absolute deadline
- no listener/timer left owned by a completed query
- no raw Tedious error as a stable user contract
- no capability enabled because a module or option merely exists
- no private driver field as a mandatory production metric
- no fault/lossy override in official performance results
- no performance claim without transcript correctness
- no Node/runtime/package support claim from development-host tests alone

## 16. Open questions with recommended defaults

| # | Decision | Recommended default | Blocks |
| --- | --- | --- | --- |
| 1 | Backend name | `ts-native` | TSQ2-1 |
| 2 | Exact scalar policy | Fail closed by default; patch driver for exact decimal/money/datetimeoffset before broad preview. | TSQ2-6/9 |
| 3 | Lossy preview | Debug/dogfood explicit opt-in only; disable export/AI/official perf. | TSQ2-6/9 |
| 4 | Tedious package | Exact reviewed release, lazy-loaded, with lock/integrity; no caret. | TSQ2-0 |
| 5 | Driver patch ownership | Maintain narrow patch only when upstream timing blocks correctness; track source and upstream PR. | TSQ2-6/15 |
| 6 | PLP policy | Preview with explicit read/memory limits and capability warning; GA requires streaming or approved fail-closed bounds. | TSQ2-15 |
| 7 | Worker thread | Wait for interaction/event-loop evidence; keep engine host-agnostic. A worker reintroduces serialization and needs its own treatment. | after TSQ2-12 |
| 8 | Metadata cache realm | Keep backend kind in fingerprint initially. Share only after parity/security evidence. | TSQ2-13 |
| 9 | Provider override persistence | In-memory per document initially. Persist only after workspace-trust/privacy review. | TSQ2-9 |
| 10 | Always Encrypted | Unsupported until live exact-package fixture proves the required read/query surface. | capability only |
| 11 | TDS strict | Conditional until target fixture matrix passes. | capability only |
| 12 | Vector type identity | Do not infer from text shape. Require reliable metadata/probe evidence. | TSQ2-10 |
| 13 | Spatial curves | Per-cell unrenderable is acceptable for first typed-spatial preview only if clearly declared; no false supported claim. | TSQ2-11 |
| 14 | Chat-to-data migration | Separate tail task; it must require exact capabilities and should not be bundled into engine MVP. | none |
| 15 | Default flip | Decide only after section 12.10 evidence and dogfood review. | post-preview |

Assign an owner and decision milestone for every unresolved item. Do not encode a temporary dogfood choice as an undocumented permanent contract.

## 17. Release gates

### 17.1 Engineering preview

- lazy package works from packaged VSIX on supported platforms
- normal activation is not measurably regressed when native is unselected
- shared conformance passes
- SQL Login and one Entra lane pass
- supported scalar/type fixtures are exact
- unsupported exact types fail before rows with a clear provider alternative
- timeout-after-first-response, cancel, dispose, close, and socket loss settle exactly once
- queues/tasks/listeners/resources are bounded and soak reaches a plateau
- privacy canaries pass
- support capsule can explain/replay a lifecycle fault
- tri-provider perf report exists and interaction is not materially worse

### 17.2 General provider

In addition to preview:

- exact decimal/numeric/money and datetimeoffset are solved or a reviewed product scope excludes them before query execution
- large-value behavior cannot catastrophically exhaust extension-host memory under the declared limits
- package/supply-chain/rollback ownership is established
- nightly soak and parity have passed for the reviewed stability window
- no critical capability is advertised from unproven driver scaffolding
- default/fallback UX is reviewed with support telemetry

### 17.3 Default-provider consideration

- all general-provider gates
- stable A/B/C baselines across representative hardware and SQL targets
- clear total-resource or latency benefit on supported profiles
- event-loop/interaction non-inferiority
- dogfood defect rate and rollback plan accepted
- per-profile capability routing prevents unsupported auth/fidelity surprises

## 18. Suggested file map

```text
extensions/mssql/src/services/sqlDataPlane/
  capabilityRegistry.ts
  backendFactory.ts
  sqlDataPlaneService.ts
  queryLifecycle.ts
  boundedAsyncLane.ts
  supportCapsule.ts

extensions/mssql/src/services/tsNative/
  tsNativeBackend.ts
  tsNativeSession.ts
  queryEngine.ts
  resultSetLedger.ts
  pageBuilder.ts
  cellEncoder.ts
  memoryBudget.ts
  observability.ts
  status.ts
  supportCapture.ts
  overrides.ts
  driver/tdsDriver.ts
  driver/tediousDriver.ts
  driver/fakeTdsDriver.ts
```

Tests:

```text
extensions/mssql/test/unit/tsNative/
extensions/mssql/test/integration/tsNative/
extensions/mssql/test/e2e/queryStudioNative/
```

Perftest:

```text
packages/perf-contracts/src/treatment.ts
packages/perftest-cli/src/matrix/
packages/perftest-cli/src/collectors/nodeRuntime.ts
packages/perftest-cli/src/regression/providerMatrix.ts
```

## 19. Definition of done

The native provider is done when it behaves as a first-class SQL Data Plane implementation rather than a fast-path exception. It owns every timer, listener, queue, task, and connection; preserves or explicitly refuses data it cannot represent exactly; never silently reruns SQL; reports honest capabilities; supplies enough ordered runtime evidence to reproduce lifecycle/performance defects; and participates in the same correctness and performance matrix as local and hosted STS2.

## 20. Reference set

Internal references are the base design and current branch paths reviewed above. Recheck these source/official references during implementation:

- Tedious Request API: <https://tediousjs.github.io/tedious/api-request.html>
- Tedious Connection API: <https://tediousjs.github.io/tedious/api-connection.html>
- Tedious source: <https://github.com/tediousjs/tedious>
- Node performance hooks: <https://nodejs.org/api/perf_hooks.html>
- Node process memory/resource APIs: <https://nodejs.org/api/process.html>
- VS Code extension bundling: <https://code.visualstudio.com/api/working-with-extensions/bundling-extension>
- VS Code extension host model: <https://code.visualstudio.com/api/advanced-topics/extension-host>
