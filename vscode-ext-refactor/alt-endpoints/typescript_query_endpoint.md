# TypeScript Query Endpoint: Native In-Process SQL Backend Design and Implementation Plan

**Status:** Draft for review
**Date:** 2026-07-13
**Code basis:** `vscode-mssql` `dev/query` at `6b9015d8dc`, `sqltoolsservice` `dev/query` at `88c6149bce`, `perftest` `dev/query` at `8c15aaca98`
**Companion documents:** `coding-docs/querystudio_web_backend.md` (the remote/WSS backend), `coding-docs/sts2_entra_auth.md`, `coding-docs/settings.md`, `sqltoolsservice/docs/sts2/{SPEC,CONTRACT,INVARIANTS}.md`
**Primary audience:** Query Studio, SQL Data Plane, STS v2, Metadata Service, OE v2, perftest, and observability owners
**Task prefix:** `TSQ-n`; commit prefix `tsq:`

## 1. Executive recommendation

Build a fully native TypeScript implementation of the SQL Data Plane domain API
(`ISqlConnectionService` / `ISqlSession`) that runs inside the extension host on
the `tedious` v20 pure-JavaScript TDS driver, registered as a new backend kind
**`ts-native`** alongside the existing local STS v2 JSON-RPC binding
(`sts2-local`), the test `fake` binding, and the future remote `sts2-remote`
binding from the web-backend design. Do not clone the STS v2 wire protocol; the
reusable boundary is the domain API, not `v2/*` JSON-RPC.

At the same time, promote capability negotiation from an STS2-binding-internal
concern to a first-class, product-visible contract:

- every backend declares an honest, structured capability set (static provider
  facts plus per-session negotiated facts);
- features ask "does this session's provider support X?" and get a typed answer
  with a reason and alternatives, instead of sniffing whether a typed cell
  happened to arrive;
- the registry can answer "does *any* registered provider support X?" so the UI
  can say "Native TypeScript cannot render spatial results on this connection —
  switch this document to SQL Tools Service to enable the Spatial pane";
- sessions bind to a provider at open time, so different documents can run on
  different providers concurrently and a settings change applies to future
  sessions without a reload.

The native backend must reach STS v2 parity on the semantics that the domain
API and its conformance suites already pin (ordering, exactly-one-terminal,
backpressure, typed cells, truncation, cancellation, error identities), must be
a first-class citizen of the Debug Console / diagnostics / capture-replay
infrastructure, and must be benchmarked A/B against `sts2-local` in perftest on
identical scenarios before any default changes. Known driver gaps (Always
Encrypted, Windows integrated auth, LocalDB, decimal fidelity, large-value
streaming, native VECTOR/JSON wire types) are not disqualifying: they are the
first real consumers of the capability contract, which is itself a prerequisite
for the `sts2-remote` backend.

Why this is worth building, in one paragraph: the STS lane costs a process
spawn, a stdio multiplexer, and a JSON-RPC serialize/deserialize round trip on
every page of every result. Most users run simple queries against servers that
need none of the advanced driver surface. An in-process TypeScript endpoint
starts in milliseconds, moves pages from the TDS parser to the RowStore as
plain JS objects with zero serialization, is observable with the same substrate
as every other front-end component, and gives the project a second independent
implementation of the domain contract — which is the strongest possible test of
the "features import only the domain API" architecture that Query Studio,
Metadata, and OE v2 are built on.

## 2. Proposed decisions

| Area | Recommendation |
| --- | --- |
| Backend kind | New `SqlBackendKind` value `ts-native`, registered in the backend factory/registry; unknown kinds keep failing loudly (no silent fallback). |
| Driver | `tedious` v20 (pure JS, Node ≥ 22, `@azure/identity` integrated). `mssql`/tarn wrapper not used (we need direct Request/pause/resume control, and we pool nothing in v1). `msnodesqlv8` rejected for core (native module, Electron ABI churn); may be reconsidered later as an optional Windows-only integrated-auth provider. |
| Protocol reuse | None. The native backend implements `ISqlConnectionService`/`ISqlSession` directly; no `v2/*` DTOs, no orphan buffer, no wire credit protocol. Semantics parity is enforced by conformance suites, not by protocol reuse. |
| Session model | One physical `tedious.Connection` per `ISqlSession`, one active query per session (same as STS v2). No connection pooling in v1; `connection.reset()` unused. |
| Capability contract | New `SqlBackendCapabilityId` taxonomy + capability oracle on the data-plane registry (`sessionSupports` / `providerSupports` / `anyProviderSupports`), layered under the existing `SqlBackendCapabilities` struct. `OpenSessionParams.requestedCapabilities` replaced by `requiredCapabilities: readonly SqlBackendCapabilityId[]` (aligned with web-backend §13.2). |
| Provider selection | `mssql.sqlDataPlane.backend` selects the default provider for **future sessions**; live-applied, no reload. Per-document override via command/status UI. Both models coexist: a session is bound to one provider for its lifetime. |
| Capability fallback | When a profile requires a capability the selected provider lacks (e.g. integrated auth on `ts-native`), `canOpen` fails typed; a routing policy setting (`prompt`/`auto`/`off`) offers the capable provider. Never silently reinterpret auth. |
| Typed cells | Byte-compatible with the STS v2 compact encoding as consumed by `decodeCell()`/RowStore/webview; enforced by golden-cell parity fixtures run against a live server through both backends, not by prose. |
| Vector | Advertise `vectorBinaryV1` by transcoding the engine's JSON-array text into f32le binary typed cells (lossless: SQL emits shortest-round-trip float32 text). Native TDS VECTOR type is absent from tedious; track upstream. |
| Spatial | Advertise `spatialWkbV1` only after a SQLCLR-UDT→WKB transcoder passes the parity fixtures (parser lifted from node-mssql's MIT `udt.js` + WKB writer with Z/M). Ships in a later task; until then the capability is honestly `false` and the Spatial pane is gated with an explanation. |
| Auth | Reuse `prepareConnection` + `vscodeSqlTokenSource` unchanged. `sql` → tedious `default`; `aad`/`bearer` → `azure-active-directory-access-token` with a fresh token per open (60-second freshness rule preserved); `integrated` → typed unsupported (capability `auth.integrated=false`). |
| Observability | Full integration: `sqlDataPlane.tsNative.*` span family in the observability contract, `TsNativeStatus` snapshot, a Debug Console hosted page, `FeatureCaptureStore`/`FeatureReplayHost` with a **provider dimension** in matrix replay, and a debug-override object setting that includes capability masks and fault/latency injection. |
| Testing | Register as the third binding of `sqlDataPlaneConformance.test.ts`; port the STS2 YAML scenario corpus (fake-adapter subset) with a TS scenario runner + scripted fake TDS driver; live type-matrix parity against `STS2_SQLSERVER_CONNSTRING` / `STS2_AZURESQLSERVER_CONNSTRING` lanes. |
| Perf eval | Two-phase perftest plan: (A) paired scenario variants + existing `head-to-head` report immediately; (B) first-class backend dimension (run-level settings override, backend provenance tag, first-page/rows-per-sec spans, total-resource roll-up). Non-gating until baselines exist. |
| Namespace | Settings stay under `mssql.sqlDataPlane.*` (no competing namespace); code under `extensions/mssql/src/services/tsNative/`. |

## 3. Goals and non-goals

### 3.1 Goals

1. A drop-in third implementation of the SQL Data Plane domain API that any
   current consumer (Query Studio execution, SQLCMD `:connect`, auxiliary
   sessions, Metadata Service hydration, OE v2 browse, central upload) can use
   without code changes beyond capability-awareness work that benefits all
   backends.
2. Semantics parity with the STS v2 binding on everything the domain API pins:
   ordering, exactly-one-terminal liveness, sink backpressure/ack behavior,
   one-active-query, busy/cancel/dispose lifecycles, typed cells, truncation
   with digests, structured server messages, database-context truth, stable
   error identities.
3. A first-class capability negotiation contract usable by all backends
   (`sts2-local`, `ts-native`, `fake`, later `sts2-remote`), with per-session
   answers, cross-provider discovery, and honest "unsupported because X, but
   provider Y can" UX.
4. Per-session provider binding: global default by setting, per-document
   override, live application to future sessions, no extension reload.
5. Startup and steady-state performance that materially beats the STS lane for
   the common path (connect latency, first result, rows/sec on 10k–100k row
   grids), with equal or lower total memory/CPU, proven by perftest A/B on
   identical scenarios.
6. Deep observability: state visibility in the Debug Console, structured spans
   registered in the observability contract, capture/replay with provider
   matrix support, adjustable debug overrides including fault injection and
   capability masks — at or above the bar set by inline completions.
7. Reliability: bounded deadlines everywhere, honest synthesized terminals on
   loss, no unbounded buffers, privacy canaries green (no SQL text, rows,
   passwords, or tokens in diagnostics/journals/exports).
8. Full documentation of Tedious-vs-SqlClient gaps with per-gap mitigation or
   an honest capability answer, so the gap list is a capability catalog rather
   than a surprise list.
9. Host portability within Node: no `vscode` import inside the engine; the
   backend must be constructible in any Node process (perf harness, tests,
   future server-side reuse). VS Code specifics (settings, token source,
   Debug Console) stay in a thin composition layer.

### 3.2 Non-goals for the first milestone

- Replacing the STS v2 backend or changing the default backend setting.
- Browser/web-worker portability. `tedious` needs raw sockets; the browser
  story remains the `sts2-remote` WebSocket backend. (Node remote extension
  hosts — Codespaces server side — work fine and are in scope.)
- Always Encrypted, Windows integrated auth (Kerberos/SSPI), LocalDB/named
  pipes, MARS, distributed transactions, query notifications. These are
  documented capability gaps, not work items.
- Connection pooling, connection resiliency/session recovery, automatic
  failover-partner reconnect. One session = one physical connection in v1.
- Reimplementing STS v2's journal/replay machinery bit-for-bit. The native
  backend gets domain-level capture/replay through the existing
  `FeatureCaptureStore`/`FeatureReplayEngine` framework instead; `v2`-style
  digest-identical journal replay stays an STS2 feature and the corresponding
  capabilities are advertised honestly.
- Migrating classic Query Runner, classic OE, chat-to-data's STS v1
  `query/simpleexecute` path, Table Designer, Schema Compare, or Profiler.
- Writing to the server through new surfaces (bulk load, TVP-based editing).
  The engine executes batches and streams results; edit/bulk features remain
  out of scope.

## 4. Terminology

| Term | Meaning |
| --- | --- |
| Domain API | `extensions/mssql/src/services/sqlDataPlane/api.ts` — the only contract features may import. |
| Backend / provider | An implementation of `ISqlConnectionService`. "Provider" is used when talking about UX-facing capability answers; "backend" when talking about composition. Same object. |
| Backend kind | The registry identity: `sts2-local` (alias `sts2-jsonrpc`), `ts-native`, `fake`, reserved `sts2-remote`. |
| Session | One `ISqlSession`: for `ts-native`, one `tedious.Connection`; for `sts2-local`, one STS2 `connectionId`/`SqlConnection`. |
| Engine | The transport-free core of the native backend: page builder, ordered lane, credit gate, cell encoder, lifecycle state machines. |
| Driver port (`ITdsDriver`) | The narrow seam between the engine and tedious, mirrored by a scripted fake for tests. |
| Capability ID | A stable dotted string (`auth.integrated`, `types.spatialWkbV1`, …) describing one provider/session fact. |
| Capability oracle | The registry-level query surface answering session/provider/any-provider capability questions. |
| T1/T2/T3 capability tiers | T1 = static provider facts (no connection needed); T2 = per-session negotiated facts; T3 = live engine probes (e.g. `vectorCapabilityService` DMV probes). Config gates are orthogonal to all three. |
| Golden-cell parity | A fixture suite that runs identical SQL through two backends on the same server and diffs the resulting `CompactPage` values cell-by-cell. |

## 5. Code and document basis

This design was made against the three `dev/query` heads named at the top and
the following inventory sources:

- Domain API and STS2 binding: `services/sqlDataPlane/api.ts`,
  `services/sqlDataPlane/sqlDataPlaneService.ts`,
  `services/sqlDataPlane/fakeBackend.ts`, `services/sts2/sts2Backend.ts`,
  `services/sts2/wire/v2.ts` (all under `vscode-mssql/extensions/mssql/src/`).
- Consumers: `queryStudio/documentSessionBinding.ts`,
  `queryStudio/executionOrchestrator.ts`, `queryStudio/executionHost.ts`,
  `queryStudio/rowStore.ts`, `services/metadata/metadataService.ts`,
  `objectExplorer/v2/sessions/oeV2SessionRegistry.ts`.
- STS v2 semantics: `sqltoolsservice/docs/sts2/{SPEC,CONTRACT,COMPONENTS,STATE-MACHINE,INVARIANTS,TRACE-SCHEMA,SCENARIO-MATRIX}.md`,
  `Sts2Defaults.cs`, `WireValueEncoder.cs`, `SqlLargeValueReader.cs`,
  `DriverEffectRunner.cs`, `InvariantChecker.cs`, `test/sts2/scenarios/*.yaml`.
- Observability/debug patterns: `src/diagnostics/diagnosticsCore.ts`,
  `redaction.ts`, `featureCapture/{captureStore,replayEngine}.ts`,
  `completionsDebugConsoleHost.ts`, `controllers/debugConsoleWebviewController.ts`,
  `coding-docs/observability-docs/*.md`.
- Perf harness: `perftest/packages/perftest-cli/src/run/runPipeline.ts`,
  `scenarios/registry.ts`, `regression/{headToHead,compareRuns,statistics}.ts`,
  `docs/{ARCHITECTURE,SQL_PROVISIONING,STS_INSTRUMENTATION}.md`.
- Prior decisions this design aligns with: `querystudio_web_backend.md`
  §13 (backend factory, per-backend settings, `requiredCapabilities`),
  §21 (conformance/perf suites), §25 (open questions); `sts2_entra_auth.md`
  (token source, freshness, secret containment); `settings.md` conventions.
- Driver research: tedious v20.0.0 (2026-06-21) source and issue tracker;
  Microsoft.Data.SqlClient 7.0 release notes. Detailed citations are inline in
  section 11.

## 6. Current architecture inventory

### 6.1 The domain seam is ready; composition is not

`api.ts` is a clean, VS Code-free contract: `SqlConnectionProfileRef` with
deferred `AuthProviderBundle` secrets (`api.ts:46-67`), negotiated
`SqlBackendCapabilities` (`api.ts:78-106`), `ISqlConnectionService.openSession/canOpen`
(`api.ts:124-141`), `ISqlSession.execute/close` with state/database events
(`api.ts:160-193`), an ordered `IQueryEventSink` whose `onRowsPage` promise
resolution *is* the durable-acceptance/ack point (`api.ts:268-277`), a
`QueryHandle.completion` that always settles (`api.ts:255-262`), compact pages
with null bitmaps and per-column type hints plus lazy `decodeCell()`
(`api.ts:283-419,499-606`), typed truncation markers with sha256 digests
(`api.ts:350-380`), and stable `SqlDataPlane.*` error identities
(`api.ts:425-475`).

Composition, however, is a process-wide singleton that caches **one** backend
forever (`sqlDataPlaneService.ts:65-98`), recognizes only `sts2-jsonrpc` and
`fake`, has no single-flight startup, no reconfigure/dispose path, and no
per-session provider choice. The web-backend design (§13.1–13.2) already
specifies the replacement: a `SqlBackendFactory` registry keyed by
`SqlBackendKind`, an owning `SqlDataPlaneService` with single-flight startup,
configuration fingerprints, drain-before-replace, and rejection of unknown
kinds. This design adopts that machinery and extends it to hold **multiple
concurrently active backends** (section 8).

### 6.2 The STS2 binding carries semantics worth porting, not code worth wrapping

`Sts2Backend` (`services/sts2/sts2Backend.ts`, 1297 lines) spends most of its
code on problems the native backend does not have: wire-notification demux and
the orphan buffer for execute/notification races (`:280-342`), the ack credit
ledger with per-query cumulative ordinals (D-0015, `:1010-1030`), protocol
violation detection on wire streams (`:933-949,1199-1260`), and DTO mapping.
What it also encodes — and what the native engine must reproduce at the domain
level — is the behavioral contract: metadata-before-rows, gapless page
sequence, exactly-one-terminal with synthesized terminals on loss/timeout
(`:1163-1197`), a single ordered sink lane with `SinkError` containment
(`:1263-1291`), bounded deadlines (`:556-581`), busy semantics for the second
concurrent query (`:636-642`), honest capability negotiation from `initialize`
(`:239-278`), and database-context truth from the backend (`:1082-1088`).

### 6.3 STS v2 parity targets, in numbers

From `Sts2Defaults.cs` and the SPEC: 1000 rows/page, 256 KiB/page, 4-page
credit window, 1 MiB max cell, 64 KiB truncated prefix (`min(maxCellBytes,
65536)`), sha256 truncation digests, connect timeout 15 s, close timeout 5 s,
one active query per connection (not configurable). Client caps are lower-only
(a client can never raise service protection limits). The typed-cell model
wraps decimal/datetime2/datetimeoffset/time/guid/binary/non-finite floats in
`{$t,v}` wrappers with invariant formatting; vector cells use `data` (never
`v`) with f32le base64 and never truncate (per-cell `unavailable` statuses
instead); spatial cells carry OGC WKB with Z/M preserved and per-cell
`unrenderable` reasons. Compact pages carry row-major `values`, base64
LSB-first row-major `nullBitmap`, and per-column `typeHints`
(`boolean|number|number:approx|binary|xml|datetime|vector:f32le:v1|spatial:wkb:v1|string`).
Error identities are the stable `Sts2.*` strings; the domain maps them to
`SqlDataPlane.*` codes. The perf floor on the C# side is ≥ 50 000 rows/s
(1M×10 digest-mode gate); no spawn-to-ready startup number is published — the
native backend's A/B must measure both sides.

### 6.4 Three disjoint capability concepts exist today

1. **Negotiated `SqlBackendCapabilities`** — consumed only *inside* the STS2
   binding to gate wire encodings (`sts2Backend.ts:826-839`); never read by UI.
2. **`QsState.capabilities`** (`sharedInterfaces/queryStudio.ts:203`) — config
   flags (`vectorWorkbench`, `spatialResults`) seeded from settings gates
   (`queryStudioController.ts:521-525,666-668`), orthogonal to what the backend
   can actually do.
3. **Live engine probes** — `queryResults/vector/vectorCapabilityService.ts`
   runs DMV/syntax probes on an auxiliary session and caches per
   (connection, database); the only place that truly interrogates a target for
   feature support.

The UI learns "is this a vector/spatial column" by sniffing whether a typed
cell arrived (`app.tsx:1758-1832`); if the provider cannot emit typed cells the
column looks like a string and the tab silently never appears. Plans are
un-gated assumptions: the actual-plan toggle sets state unconditionally
(`queryStudioController.ts:1353-1356`), plan results are detected by a
column-name heuristic (`executionOrchestrator.ts:125-130`), and plan-graph
parsing still calls classic STS v1 (`services/executionPlanService.ts:13-27`).
`canOpen`/`CapabilityCheck` already model `{ok, missing?, reason?}`
(`api.ts:114-118`) but the STS2 implementation ignores requested capabilities.
`metadataEndpoints?` is declared and never read (`api.ts:105`). Chat-to-data's
`RunQueryTool` bypasses the data plane entirely (classic `query/simpleexecute`,
`copilot/tools/runQueryTool.ts:77-87`).

Section 9 unifies these into one contract; the native backend is its first
demanding consumer.

### 6.5 Test and harness baseline

- `test/unit/sqlDataPlaneConformance.test.ts` — transcript conformance against
  `FakeBackend` (ordering, backpressure serialization, sink-throw containment,
  one-terminal, busy, idempotent close, chaos cases).
- `test/unit/sts2Backend.test.ts` — scripted-wire binding conformance including
  the D-0015 credit regression, truncation cells, option wiring, and
  vector/spatial negotiation suites.
- STS2 C# side: 54 declarative YAML scenarios (50 fake-adapter), a seeded
  connection simulator (10 000-seed full gate), an `InvariantChecker` over
  journals, and live engine tests gated on `STS2_SQLSERVER_CONNSTRING`.
- perftest: per-scenario `userSettings` are written into the profile's
  `settings.json` **before VS Code launches** (`runPipeline.ts:722-747`) — the
  exact seam needed to select a backend per run. Query Studio scenarios exist
  for 10k/100k rows, wide 1000×300, large cells, 10k messages, 100 result
  sets, scroll interaction, and SQLCMD runs. `head-to-head` compares two
  scenario IDs with median/p95 and signed delta bars; `compare` is the gating
  Welch-t path. `environmentHash` excludes `userSettings`, so same-scenario
  backend A/B comparisons are not refused. STS-side pipeline metrics
  (`sts.query.pipeline.*`) exist only when STS spawns — a fairness caveat for
  A/B reporting (section 13).
- There is **no Query Studio e2e suite** driving the data plane today
  (Playwright e2e exercises the classic path only) — a pre-existing gap this
  plan partially covers via perftest scenarios and flags for ownership.
- `tedious` is not currently a dependency anywhere in the monorepo;
  `@azure/msal-node` is already in-tree.

## 7. Scenarios and requirements

### 7.1 Scenarios

**S1 — Fast path for the majority.** A user with SQL login or Entra auth
against SQL Server / Azure SQL opens Query Studio and runs queries. With
`backend: ts-native` there is no STS spawn, no .NET runtime, no stdio
multiplexer: the first connection is driver-speed, results stream in-process
into the RowStore. Everything they see (grids, messages, rowcounts, USE
tracking, cancel) behaves identically to `sts2-local`.

**S2 — Advanced feature discovery.** The same user later clicks the Spatial
pane on a geometry result. If the native provider cannot emit WKB for this
session, the pane is disabled with: "Spatial rendering is not supported by the
Native TypeScript backend. Switch this document to SQL Tools Service to enable
it." — with a one-click switch that rebinds the document's next session. The
UI got that answer from the capability oracle, not from a missing cell.

**S3 — Mixed composition.** One window has a Query Studio document on
`ts-native` (fast iteration), another document bound to `sts2-local` because
its profile uses Windows integrated auth, and OE v2 browsing on the default
provider. Each session carries its provider identity in status UI and
diagnostics; metadata caches are partitioned safely.

**S4 — Capability-routed open.** A profile with `authKind: integrated` is
opened while the default backend is `ts-native`. `canOpen` fails typed with
`missing: ["auth.integrated"]`; per the fallback policy the user is prompted
(or auto-routed) to `sts2-local` for that session. No silent auth
reinterpretation, ever.

**S5 — A/B evaluation.** An engineer runs the perftest backend matrix over the
10k/100k/wide/large-cell/messages/result-set scenarios and gets a head-to-head
report: connect/first-page/complete/render spans, rows/sec, exthost+STS total
CPU and memory, cancellation latency — same fixtures, same tuning digest, same
machine session.

**S6 — Debug and replay.** A user reports a hung query on `ts-native`. The
Debug Console's SQL Data Plane page shows the live session state (phase, pages
delivered/acked, credit stalls, driver state), the diag timeline shows the
span waterfall, and the captured run can be replayed — including as a matrix
across `ts-native` and `sts2-local` with overridden page sizes — to isolate
whether the fault is engine-, driver-, or server-side. Fault injection
(latency, dropped connection after N pages, forced open failure) reproduces
the failure deterministically in tests.

### 7.2 Requirements

Numbered for review traceability. "Backend" below = the `ts-native`
implementation unless stated otherwise.

**Contract and semantics**
- **R1.** Implement `ISqlConnectionService` and `ISqlSession` exactly as
  declared in `api.ts`; no new methods required for basic operation, no wire
  DTO imports, no `vscode` import in the engine.
- **R2.** Uphold the domain invariants: result-set metadata before rows;
  gapless per-set `pageSeq`; monotonic `rowOffset`; exactly one terminal per
  query, always settled (synthesized on loss/timeout with `synthesized: true`);
  no events after terminal; one sink callback in flight; ack-after-durable
  acceptance (next page delivery gated on the prior `onRowsPage` promise);
  one active query per session with `SqlDataPlane.Busy` on violation;
  idempotent close/dispose.
- **R3.** Match STS v2 result shaping: default 1000 rows / 256 KiB pages,
  4-page in-flight window, 1 MiB `maxCellBytes` with 64 KiB truncated prefix +
  `sha256:` digest, lower-only clamping of client options, compact pages with
  byte-identical `nullBitmap` packing and the same `typeHints` taxonomy.
- **R4.** Produce `CompactPage.values` cell encodings that `decodeCell()`,
  RowStore, export, and the webview consume identically to the STS2 path
  (golden-cell parity fixtures are the acceptance mechanism).
- **R5.** Map errors to stable identities: `SqlDataPlane.Auth`, `.Busy`,
  `.Unavailable`, `.Client.Timeout`, `.Client.SinkError`, plus a new
  `.CapabilityUnsupported`; carry structured `server {number,severity,state,
  line,procedure}` details; never make raw driver exception strings contract.
- **R6.** Structured server messages with number/severity/state/line/procedure
  in stream order relative to result sets; database-context changes surfaced
  through `onDidChangeDatabase` from the driver's ENVCHANGE event.
- **R7.** Cancellation via TDS attention with a bounded ack
  (`CancelAck.uncertain` when the deadline passes); dispose drains bounded and
  emits exactly one `disposed` terminal; close cancels the active query first.

**Capability contract (all backends)**
- **R8.** A `SqlBackendCapabilityId` taxonomy with T1 (provider-static) and T2
  (session-negotiated) answers; `ISqlSession.capabilities` stays the negotiated
  struct; a derived ID set is exposed for oracle queries.
- **R9.** `canOpen` honors `requiredCapabilities` and fails typed **before any
  credential provider is invoked**.
- **R10.** A registry-level capability oracle: `sessionSupports`,
  `providerSupports(kind)`, `anyProviderSupports` → `{supported, reason?,
  alternatives?}`; answers are pure/side-effect-free (no auth prompts, no
  connections opened).
- **R11.** UI integration: Query Studio derives feature enablement from
  config-gate AND capability answer (AND engine probe where applicable), and
  renders disabled states with reason + "switch provider" affordance. Column
  metadata gains `providerTypeName` so UDT columns are identifiable even when
  typed cells are unavailable.
- **R12.** Honesty rule (inherited from web-backend §13.4/§19.3): a backend
  never advertises a capability without an implemented, tested path; capture/
  replay/plan flags reflect reality per backend.

**Composition and selection**
- **R13.** Multi-backend registry: lazy single-flight construction per kind,
  per-kind config fingerprint, retry/reconfigure/dispose, drain-before-replace,
  unknown kind = typed failure. Passive status never triggers auth/connections.
- **R14.** Session-scoped binding: `openSession` resolves a provider at call
  time (explicit override > per-document override > setting default); existing
  sessions are never migrated. Setting changes apply to future sessions
  without reload; an optional "close and reconnect" prompt covers open
  documents.
- **R15.** Capability fallback policy setting (`prompt`/`auto`/`off`) governing
  S4; every fallback is visible (status + diag event), never silent.

**Auth and privacy**
- **R16.** Reuse `prepareConnection`/`ProfileTokenSource`; per-open token
  acquisition with the 60-second freshness rejection, account/tenant drift
  rejection, and one bounded end-to-end open deadline; no token/password ever
  stored beyond the driver call, logged, journaled, or exported (canary-tested).
- **R17.** `integrated` profiles are a typed capability failure on `ts-native`
  (R15 routing applies); `ActiveDirectoryDefault`/service-principal remain
  explicitly unsupported through the shared adapter until designed for all
  backends.

**Observability, debug, replay**
- **R18.** Register a `sqlDataPlane.tsNative.*` event/span family in the
  observability contract (conformance test enforces registration); spans for
  open/execute/first-page/complete/cancel/close with safe fields only
  (durations, counts, bytes, stable codes — never SQL text/rows/identifiers in
  plain form).
- **R19.** `TsNativeStatus` snapshot (sessions, active queries, pages/bytes
  delivered, credit stalls, driver versions, capability set) surfaced through
  the existing `mssql.sqlDataPlane.showStatus` command and a Debug Console
  hosted page with reducer-dispatched actions.
- **R20.** `FeatureCaptureStore`/`FeatureReplayHost` integration for query
  runs, with snapshot/override/live config modes and matrix replay including a
  **backend dimension** (replay the same captured run on `ts-native` and
  `sts2-local`).
- **R21.** A `mssql.sqlDataPlane.tsNative.overrides` object setting for debug:
  paging/timeout knobs, `capabilityMask` (force capabilities off to exercise
  gating UX), and `faults` (open failure rate, page delay, drop-after-N-pages,
  token-expiry simulation). Overrides are session-visible in diagnostics and
  ignored keys are tolerated (matching `queryStudio.tuning.overrides`
  conventions).

**Performance and consumption**
- **R22.** Perftest A/B on identical scenarios with backend provenance stamped
  on runs/markers, first-page and rows/sec metrics, and a total-resource
  roll-up (exthost + STS for `sts2-local` vs exthost-only for `ts-native`).
- **R23.** Event-loop discipline: the engine yields between page deliveries and
  never blocks the extension host beyond a budgeted slice; interaction
  scenarios (scroll during streaming) must not regress vs `sts2-local`.
- **R24.** Bounded memory: at most window×pageBytes of undelivered pages per
  query plus one in-flight row; the PLP large-value limitation (section 11) is
  documented and guarded (post-buffer truncation still enforces `maxCellBytes`
  on delivery; the transient driver-side buffering cost is called out in docs
  and status).

**Testing**
- **R25.** Conformance: third binding of `sqlDataPlaneConformance.test.ts`;
  scripted fake-driver suite mirroring `sts2Backend.test.ts` coverage; ported
  YAML scenario corpus with a TS invariant checker; golden-cell parity; live
  lanes on `STS2_SQLSERVER_CONNSTRING` (SQL 2025 local),
  `STS2_AZURESQLSERVER_CONNSTRING`, `STS2_AZURESQLSERVER_ENTRAID_CONNSTRING`;
  soak (repeated open/execute/cancel/dispose cycles) with leak assertions.

## 8. Provider model: registry, selection, lifecycle

### 8.1 Registry (extends web-backend §13.1)

Adopt the `backendFactory.ts` registry from the web-backend design with one
extension: the owning service holds a **map of active backends**, not a single
composition.

```typescript
export type SqlBackendKind = "sts2-local" | "ts-native" | "fake" | "sts2-remote";
// "sts2-jsonrpc" remains a deprecated read alias for "sts2-local".

export interface SqlBackendFactory {
    readonly kind: SqlBackendKind;
    readonly displayName: string;
    /** T1 facts — answerable with zero side effects, before create(). */
    readonly staticCapabilities: ProviderCapabilityStatement;
    create(context: SqlBackendFactoryContext): Promise<ISqlConnectionService>;
}

interface BackendEntry {
    factory: SqlBackendFactory;
    /** Single-flight startup; cleared on terminal failure so retry works. */
    startup?: Promise<ISqlConnectionService>;
    service?: ISqlConnectionService;
    configFingerprint: string;
    sessions: Set<WeakRef<ISqlSession>>; // drain accounting
    lastError?: SqlDataPlaneErrorInfo;
}
```

Rules (unchanged from the web-backend design where they overlap):

- unknown kinds are a typed failure, never a silent local-STS fallback;
- single-flight startup per kind; failed startup is retryable and never leaves
  a poisoned cache entry;
- per-kind configuration fingerprint; a config change drains and recomposes
  **that kind only** (sessions on other kinds are untouched);
- disposal stops timers, rejects pending opens, marks sessions lost, settles
  active handles, and clears secrets;
- passive status (`statusSummary`) reads entries without constructing backends,
  minting tokens, or resolving credentials.

Deviation from web-backend §13.2 ("one composition at a time, atomically
swapped"), stated explicitly for review: that rule exists because remote
backends change the *security realm* (operator, tenancy, cache identity).
`ts-native` and `sts2-local` share the local realm — same process user, same
targets, same credential sources — so concurrent composition is safe provided
cache identity is handled (below). When `sts2-remote` lands, realm-changing
backends keep the atomic-swap rule; local kinds may coexist. The registry
therefore tags each factory `realm: "local" | "remote:<deploymentId>"`.

Metadata cache identity: fingerprint v2 (web-backend §13.6) includes backend
kind. For v1 we follow it verbatim — `ts-native` sessions get their own
MetadataStore partition. This is safe and slightly wasteful (duplicate
hydration when one server is browsed through both kinds). Whether the two
local kinds may share one metadata realm is Open Question Q3.

### 8.2 Selection: setting default + per-document override

- `mssql.sqlDataPlane.backend` (scope `application`, enum
  `sts2-local | ts-native | fake`, default `sts2-local`, `sts2-jsonrpc`
  accepted as deprecated alias, `sts2-remote` reserved) selects the **default
  provider for future sessions**. Live-applied: a configuration change updates
  the default; open sessions keep their provider. No reload required
  (consistent with the settings.md late-enable norm; the engine-toggle
  precedent is `mssql.queryStudio.languageService.engine`).
- Per-document override: command `MS SQL: Select Query Backend for This
  Document` (`mssql.sqlDataPlane.pickDocumentBackend`) + a Query Studio status
  segment showing the bound provider. The override is held on the document
  binding (in-memory, not persisted); it applies at the next connect for that
  document. `DocumentSessionBinding` passes it to `openSession`.
- Resolution order inside `SqlDataPlaneService.openSession(params, opts?)`:
  `opts.backendKind` (explicit caller) → document override (threaded by the
  caller) → setting default. The resolved kind is stamped on
  `SessionInfo.backendKind` (field already exists) and on all diagnostics.
- Consumers do not change: `DocumentSessionBinding`, Metadata, OE v2, central
  upload keep calling the same service; Metadata and OE v2 use the default
  provider unless a future task gives them pinned kinds.

### 8.3 Capability-routed fallback

`mssql.sqlDataPlane.capabilityFallback`: `"prompt" | "auto" | "off"`, default
`"prompt"`. Flow: `canOpen` with the profile-derived `requiredCapabilities`
(e.g. `auth.integrated` for integrated profiles) fails typed → the service
consults the oracle for an alternative kind whose T1 set satisfies the
requirements → `prompt` shows a one-line action ("Open with SQL Tools
Service"), `auto` routes silently but emits a status/diag event and a one-time
notification, `off` surfaces the typed error. The fallback decision is made
before any credential resolution (R9/R16). Sessions opened by fallback carry
their real kind in status; nothing pretends.

## 9. Capability negotiation design

### 9.1 Capability IDs and tiers

```typescript
export type SqlBackendCapabilityId =
    // auth
    | "auth.sqlLogin" | "auth.entraToken" | "auth.integrated"
    | "auth.servicePrincipal"
    // connectivity
    | "connect.tcp" | "connect.namedPipes" | "connect.localdb"
    | "connect.tds8Strict" | "connect.multiSubnetFailover"
    | "connect.readOnlyIntent"
    // security
    | "security.alwaysEncrypted" | "security.alwaysEncryptedEnclaves"
    // execution
    | "exec.streamingRows" | "exec.creditBackpressure" | "exec.cancel"
    | "exec.dispose" | "exec.multipleResultSets" | "exec.compactRows"
    | "exec.queryTimeout" | "exec.pageLimits" | "exec.maxCellBytes"
    // types / rendering fidelity
    | "types.typedCells" | "types.vectorBinaryV1" | "types.spatialWkbV1"
    | "types.jsonNative" | "types.preciseDecimals"
    | "types.datetimeOffsetPreserved" | "types.subMsTime"
    | "types.largeValueStreaming"
    // plans
    | "plan.estimated" | "plan.actual" | "plan.xmlResult"
    // messages / metadata
    | "messages.verbatim" | "messages.rowsAffectedStructured"
    | "metadata.catalogSql" | "metadata.endpoints"
    // diagnostics
    | "diag.captureControl" | "diag.replayDescriptors"
    | "diag.resumeAfterDisconnect";
```

- **T1 (provider-static)** — answerable with zero side effects from
  `SqlBackendFactory.staticCapabilities`, before any backend is constructed.
  Values: `true`, `false`, or `"perSession"` (depends on negotiation/target).
  Example: `ts-native` reports `auth.integrated: false`,
  `security.alwaysEncrypted: false`, `types.vectorBinaryV1: "perSession"`.
- **T2 (session-negotiated)** — the existing `SqlBackendCapabilities` struct on
  `ISqlSession.capabilities`, extended with the handful of new fields implied
  above (`preciseDecimals`, `datetimeOffsetPreserved`, `subMsTime`,
  `largeValueStreaming`, `jsonNative`, `tds8Strict`); a derived
  `capabilityIds(session)` view maps struct → ID set so oracle answers and the
  struct never disagree. Struct fields remain the binding-internal fast path.
- **T3 (engine probes)** — unchanged, feature-owned (vector DMV probes, future
  spatial engine checks). The oracle does not subsume T3; it composes with it.

The boolean struct stays authoritative for T2 to avoid churning every
consumer; the ID taxonomy is the query/reporting surface. A single source
table in `api.ts` maps struct field ↔ ID so they cannot drift (unit-tested).

### 9.2 The oracle

Exposed by `SqlDataPlaneService` (not per-backend), because "any provider"
questions are registry questions:

```typescript
export interface CapabilityAnswer {
    supported: boolean | "unknown";   // "unknown" only for T1 "perSession" asked without a session
    /** Stable, user-presentable reason id + safe text when not supported. */
    reason?: { code: string; message: string };
    /** Other registered kinds whose T1 answer is true/perSession. */
    alternatives?: SqlBackendKind[];
    /** True when support additionally requires per-execute opt-in (vector/spatial). */
    requiresOptIn?: boolean;
}

export interface ISqlDataPlaneCapabilities {
    sessionSupports(session: ISqlSession, cap: SqlBackendCapabilityId): CapabilityAnswer;
    providerSupports(kind: SqlBackendKind, cap: SqlBackendCapabilityId): CapabilityAnswer;
    anyProviderSupports(cap: SqlBackendCapabilityId): CapabilityAnswer;
}
```

Properties: pure, synchronous, side-effect-free (T1 from factory statements,
T2 from an already-open session's negotiated struct); `anyProviderSupports`
consults T1 statements only — it never constructs backends. Answers carry
`alternatives` so the "switch to C# to get this feature" UX is one lookup.

`canOpen(params)` becomes the enforcement point:
`OpenSessionParams.requestedCapabilities?: Partial<SqlBackendCapabilities>` is
replaced by `requiredCapabilities?: readonly SqlBackendCapabilityId[]`
(web-backend §13.2 decision, applied here for all backends). Each consumer
declares its floor once: Query Studio execution
(`exec.streamingRows`, `exec.cancel`, `exec.multipleResultSets`,
`messages.verbatim`), Metadata hydration (`metadata.catalogSql`), OE v2 browse
(same), profile-derived additions (`auth.integrated` when the profile says so).
Failures produce `SqlDataPlane.CapabilityUnsupported` with `missing[]` — the
input to the fallback flow (§8.3).

### 9.3 UX integration

- **QsState**: `capabilities` becomes derived — for each gated feature,
  `enabled = configGate && oracle(session, capId).supported && (T3 where
  applicable)`; a parallel `capabilityHints` map carries
  `{reason, alternatives}` for disabled affordances. Controller refresh points
  already exist (`queryStudioController.ts:521-525,666-668`).
- **Column metadata**: add `providerTypeName?: string` to `ColumnMetadata` and
  `QsResultColumn` (populated from driver metadata: `geometry`, `geography`,
  `hierarchyid`, `vector`, `json`, …). The webview can then render "geometry
  column — spatial rendering unavailable on this backend (switch to SQL Tools
  Service)" instead of the current silent string column.
- **Plan toggles**: gate estimated/actual plan buttons on
  `plan.estimated`/`plan.actual`; both current backends answer true, so this is
  a no-op today but makes `sts2-remote`/future providers honest, and fixes the
  currently un-gated toggle (`queryStudioController.ts:1353-1356`).
- **Grid fidelity hints**: when a session lacks `types.preciseDecimals` or
  `types.datetimeOffsetPreserved`, affected cells render with the existing
  `exact:false` affordance plus a column-header tooltip sourced from the
  capability reason (section 11.3 policies).
- **Cross-provider suggestion**: a small shared helper
  `suggestProviderFor(cap, session)` produces the standard notification body
  ("X isn't supported by <current>. <Alternative> supports it — switch this
  document?") used by Spatial pane, Vector workbench, and future features.

### 9.4 Unsupported-at-runtime signaling

Capabilities gate *features*; cells still need per-value honesty. The typed
cell model already carries it: vector `status:"unavailable"` and spatial
`status:"unrenderable"` with reason enums, truncation markers, and
`unsupported` CellValue kind. The native backend reuses these verbatim (e.g. a
SQLCLR blob its transcoder cannot parse → spatial cell
`status:"unrenderable", reason:"unsupportedNativeValue"` — same enum the C#
driver uses). No new per-cell shapes.

## 10. The `ts-native` backend design

### 10.1 Module layout

```text
extensions/mssql/src/services/tsNative/
  tsNativeBackend.ts        ISqlConnectionService impl; capability statements;
                            availability; canOpen enforcement
  tsNativeSession.ts        ISqlSession impl; state machine; SET-options and
                            database-context tracking
  queryEngine.ts            per-query pump: ordered lane, page window/credit,
                            terminals, deadlines, invariant assertions
  pageBuilder.ts            row → CompactPage: rows/bytes thresholds, STS2-
                            compatible byte estimation, nullBitmap packing
  cellEncoder.ts            tedious value+metadata → cell values + typeHints;
                            truncation with sha256 digests; fidelity policies
  vectorTranscoder.ts       JSON-array text → f32le typed vector cells (D-0019 shape)
  spatialTranscoder.ts      SQLCLR UDT bytes → OGC WKB typed spatial cells (D-0020 shape)
  driver/
    tdsDriver.ts            ITdsDriver port (engine-facing; no tedious types)
    tediousDriver.ts        tedious adapter: Connection/Request wiring,
                            pause/resume, cancel, events
    fakeTdsDriver.ts        scripted driver for tests (mirrors STS2 FakeDriver
                            step vocabulary: resultSet/rows/message/done/error/
                            sever/hang/crash + fault knobs)
  observability.ts          span emission, TsNativeStatus snapshot, counters
  debugHost.ts              Debug Console hosted page state/actions
  capture.ts                FeatureCaptureStore/FeatureReplayHost wiring
  overrides.ts              tsNative.overrides parsing: tuning, capabilityMask, faults
```

The engine (`queryEngine`, `pageBuilder`, `cellEncoder`, transcoders, driver
port) imports neither `vscode` nor the diagnostics singletons — observability
is injected as a narrow sink interface — so the whole engine runs in plain
Node for tests, the perf harness, and any future non-VS-Code host (R1/R9 of
goals). `tsNativeBackend.ts` is the composition edge that binds VS Code
settings, the token source, and diag.

### 10.2 Driver choice

`tedious` v20.0.0 (June 2026; Node ≥ 22 — matches the extension host), the
Microsoft-documented production path for Node. Direct dependency, no `mssql`
wrapper: the wrapper adds pooling and API sugar we do not use, and hides the
Request-level pause/resume and event ordering the engine needs. Rejected
alternatives: `msnodesqlv8` (native ODBC binding — Electron ABI coupling,
ODBC driver install requirement, single maintainer; revisit only as an
optional Windows integrated-auth add-on), and a from-scratch TDS
implementation (months of protocol work for marginal control; tedious's parser
is the part of the stack least worth rewriting). Maintenance posture: tedious
is community-maintained with effectively one primary maintainer (~30
commits/yr); we budget for pinning + upstream contributions (section 11.4)
rather than assuming fast upstream fixes.

### 10.3 Session lifecycle

- **Open** (`openSession`): resolve provider (§8.2) → `canOpen` with
  `requiredCapabilities` (before credentials, R9) → resolve secrets via
  `AuthProviderBundle` inside the bounded open deadline
  (default `timeouts.openMs` 30 000, shared with token acquisition per
  sts2_entra_auth §8.1) → construct `tedious.Connection` with:
  `server`/`options.database`, `options.appName = applicationName`,
  `options.encrypt` mapped `strict → 'strict'`, `true/mandatory → true`,
  `false/optional → false`, `options.trustServerCertificate`,
  `options.connectTimeout = openTimeoutMs`, `options.requestTimeout = 0`
  (per-request timeouts are explicit), `options.useColumnNames = false`,
  `options.rowCollectionOnRequestCompletion = false`, keep-alive default.
  Auth mapping per R16/§10.6. On `connect` event: run the server-info probe
  (same statement STS2 uses: `select serverproperty('ProductVersion'),
  serverproperty('Edition'), cast(serverproperty('EngineEdition') as int)`)
  and `SELECT @@SPID` (tedious exposes no SPID) → populate `SessionInfo`
  (`backendKind: "ts-native"`). Subscribe `databaseChange` → 
  `onDidChangeDatabase {source:"backend"}`; `error`/`end` → loss handling.
  Any pre-ownership failure closes the socket and maps to
  `SqlDataPlane.Auth`/`.Unavailable` with the same SqlError-number
  classification STS2 uses (18456/18452/4060 → Auth; timeout/network classes
  → retryable Unavailable).
- **State machine**: `open → closing → closed`, `open → lost` on socket
  error/unexpected end. `markLost` synthesizes a `connectionLost` terminal on
  the active query (the domain liveness floor) and fires `onDidChangeState`.
- **Close**: cancel active query (bounded), then `connection.close()` awaited
  against `timeouts.closeMs` (default 15 000); idempotent; always transitions
  even if the socket refuses to die (socket destroy on deadline).
- **One active query**: `execute` while a query is live throws
  `SqlDataPlane.Busy` (retryable) — the orchestrator's existing ≤5 s Busy
  retry loop handles the race exactly as with STS2.

### 10.4 Query engine

**Submission.** `execute(text, opts, sink)` builds a `tedious.Request` and
submits via **`execSqlBatch`** — raw adhoc batch, no `sp_executesql` wrapper —
so session-scoped `SET` statements (Query Studio session options, SHOWPLAN,
STATISTICS XML) behave exactly as they do through `SqlDataReader` on the C#
side, and `done` (not `doneInProc`) semantics apply. Query Studio already
splits `GO` batches and runs SQLCMD preprocessing above this layer; the engine
receives one batch per execute. When `opts.timeoutMs > 0`,
`request.setTimeout(timeoutMs)` (driver maps to cancel + `ETIMEOUT`).

**Streaming and paging.** Driver events map to the domain stream:

| tedious event | Engine action |
| --- | --- |
| `columnMetadata(cols)` | close any open page; emit `onResultSetStarted` with `ResultSetMetadata` (ordinal/name/`sqlType` from type name, precision/scale/maxLength, `isXml`/`isJson`, `providerTypeName`, vector/spatial column facts when transcoders engaged); compute per-column `typeHints` once (STS2 `SerializeTypeHints` parity). |
| `row(columns)` | encode cells (§10.5) into the open page; close page on `pageRows` OR `pageBytes` threshold (single row over `pageBytes` becomes its own one-row page — STS2 rule). |
| `infoMessage` / `errorMessage` | enqueue `ServerMessage` in stream position (kind `error` when `class > 10`; severity=class, state, line, `procedure`=procName). Errors are recorded for terminal status. |
| `done`/`doneInProc`/`doneProc(rowCount, more)` | close page (`complete: true` on last), emit `onResultSetEnded {rowCount}` when a set is open; accumulate structured rowsAffected when `rowCount` is valid (NOCOUNT ⇒ absent). |
| `returnValue` | ignored in v1 (no proc-parameter surface in the domain API). |
| request callback | terminal (below). |

**Ordered lane and backpressure.** One async lane per query delivers sink
callbacks strictly in order, one in flight. Completed pages enter a bounded
queue; when `undeliveredPages ≥ windowPages` (default 4 — STS2 parity) the
engine calls `request.pause()`; `resume()` at low-water 1. Because
`pause()` lets already-parsed rows trickle in, the queue tolerates a bounded
overrun (mirroring STS2's one-page overrun note) and the bound is asserted in
tests. The sink's `onRowsPage` promise resolution is the durable-acceptance
point (RowStore spill backpressure propagates through it, exactly as today).
A sink throw fails the query locally with `SqlDataPlane.Client.SinkError`,
stops delivery, and cancels the driver request — matching the STS2 binding's
containment. Between page deliveries the lane yields (`setImmediate`) so grid
interaction and other extension work never starve (R23).

**Terminals.** Exactly one, always: request callback with no recorded errors →
`succeeded`; with recorded server errors but a completed request →
`completedWithErrors`; `ECANCEL` → `canceled`; `ETIMEOUT` → `failed` with the
timeout identity; socket loss → `connectionLost` (synthesized if the driver
callback never fires, on the session-loss path); dispose → exactly one
`disposed` after the pump is confirmed stopped (D-0011 parity). Terminal
summary carries resultSetCount/totalRows/rowsAffected/errorCount/durationMs.
`terminalGuard` drops (and diag-counts) any driver event arriving after the
terminal.

**Cancel.** `handle.cancel()` → `request.cancel()` (TDS attention). Ack
resolves when the driver surfaces `ECANCEL`/completion; if
`timeouts.cancelAckMs` (10 000) expires first, resolve
`{acknowledged:false, uncertain:true}` and arm the
`completeAfterCancelMs` synthesized-terminal deadline — same shape as the STS2
binding. tedious's own `cancelTimeout` (5 000 default) tears the socket down
if the server never acknowledges, which surfaces as loss → `connectionLost`
terminal; both paths settle `completion`.

**Dispose.** Cancel + stop delivery + drain bounded
(`timeouts.disposeDrainMs`, 10 000) + one `disposed` terminal + release page
queue. Idempotent.

**Option clamping.** `pageRows`/`pageBytes`/`maxCellBytes` are lower-only
against the pinned defaults (1000 / 262 144 / 1 048 576); absent/invalid ⇒
default; larger ⇒ clamped (D-0014 parity). All four honor flags
(`pageRowsHonored`, `pageBytesHonored`, `maxCellBytesHonored`,
`queryTimeoutHonored`) are advertised `true`.

### 10.5 Cell encoding and typed-cell parity

`cellEncoder` maps (tedious value, column metadata) → the compact `values`
entry + column `typeHints`, matching what `decodeCell()` and the webview
expect from the STS2 path:

- JSON natives pass through: bool, int/smallint/tinyint, finite float/real,
  strings. NULL → `undefined` in `values` + nullBitmap bit (bitmap packing
  byte-identical to `packBitmap`: row-major, LSB-first).
- `number:approx` columns (bigint/decimal/numeric/money): value delivered as
  the invariant **string** carrier. bigint: tedious already yields a lossless
  string. decimal/numeric/money: tedious yields a JS number — fidelity policy
  in §11.3 governs when the carrier is marked inexact.
- `datetime` hint (date/time/datetime/datetime2/datetimeoffset): invariant
  display string. datetime2 sub-ms recovered from tedious's
  `nanosecondsDelta`; datetimeoffset policy in §11.3.
- `binary` hint: bounded values as base64/hex per the compact conventions;
  over-cap values become `TruncatedCellEncoding {$t:"truncated", of, bytes,
  digest:"sha256:<hex>", v:<prefix>}` with the 64 KiB prefix rule. Digests are
  computed streaming (`crypto.createHash` over the full buffered value).
- `xml`/`json` hints: string value; truncation as above (UTF-8 prefix never
  splits a code point).
- `guid`: lowercased string (set `lowerCaseGuids` to match invariant "D"
  casing policy — parity fixture pins the case).
- vector columns: engine JSON-array text by default (typeHint `string` →
  matches STS2 text mode D-0018); with per-execute `vectorEncoding:"binary-v1"`
  and the capability negotiated, `vectorTranscoder` parses the text and emits
  the typed cell `{$t:"vector", version:1, status:"ok", dimensions, baseType:
  "float32", encoding:"f32le", byteLength, data:<base64>}` — field `data`,
  never `v` (the classic misparse trap). Unparseable/mismatched cells emit
  `status:"unavailable"` with the same reason enum as the C# driver. Vector
  cells never truncate.
- spatial columns (when the transcoder task has landed and negotiated):
  `spatialTranscoder` parses the SQLCLR serialization from the raw UDT
  `Buffer` and emits `{$t:"spatial", version:1, status:"ok", kind, encoding:
  "wkb", srid, wkbBytes, wkb:<base64>}` with Z/M preserved; failures emit
  `status:"unrenderable"` with the standard reasons. hierarchyid is never
  spatial (binary as usual).
- `sql_variant`: underlying value encoded by its runtime type (read-only —
  fine, we never send variants).
- Anything unmappable: invariant-string fallback (the `provider` wrapper
  equivalent) — never a thrown query.

Opt-in literalness (STS2 parity): `compactRows` participation is the engine's
native shape (there is no legacy shape to fall back to — the binding always
produces compact pages, which the domain API prefers); `vectorEncoding` must be
the literal `"binary-v1"` and `spatialEncoding` the literal `"wkb-v1"` to
engage transcoders.

Acceptance for all of the above is the golden-cell parity suite (§15.3), which
runs the STS2 engine-test type matrix (decimal/datetimeoffset/date/varbinary/
guid/null/wide/huge cells, vector text+binary, spatial WKB SRID/ZM, CLR UDT
binary transport) through both backends against a live server and diffs
decoded `CellValue`s and raw `CompactPage` entries.

### 10.6 Auth

Reuses the shared machinery end-to-end: `prepareConnection` (exact-switch auth
mapping, no substring matching, unsupported never coerced) supplies
`SqlConnectionProfileRef` + deferred `AuthProviderBundle`; the backend resolves
secrets only after `canOpen` passes, inside the open deadline.

| Profile `authKind` | tedious `authentication` | Notes |
| --- | --- | --- |
| `sql` | `{type:"default", options:{userName, password}}` | password from `passwordProvider()` at open; empty allowed (distinct from unresolved). |
| `aad` / `bearer` | `{type:"azure-active-directory-access-token", options:{token}}` | token from `tokenProvider()` **per open** — every session open re-invokes the source (VS Code auth owns caching/refresh); tokens with < 60 s lifetime rejected pre-open (`SqlDataPlane.Auth`); account/tenant drift rules inherited from the shared source. No mid-session refresh: TDS authenticates at login only, so expiry affects only future opens — same model as STS2's static-token slice, minus its pooling concern (we do not pool). |
| `integrated` | — | **Unsupported**: typed `canOpen` failure `missing:["auth.integrated"]` → fallback flow (§8.3). tedious has NTLM-with-explicit-credentials only; no SSPI/Kerberos. |

Secret containment is simpler than the STS2 path (no JSON-RPC hop, no gateway
tokenization): the secret exists in (1) the VS Code auth provider / credential
store, (2) the resolution local inside open, (3) the tedious config object
until the connection settles. The same guarantees still hold and are
canary-tested: never in diag events, capture stores, status snapshots, or
exports; the tedious config object is not retained after connect; open
failures scrub before rethrow.

`ActiveDirectoryDefault` / service-principal: the shared adapter maps these to
"explicitly unsupported" today for all backends; when that changes (per
sts2_entra_auth §14), tedious's `token-credential` type accepts any
`@azure/identity` credential, so `ts-native` can adopt them in the same change.

### 10.7 Availability and initialization

`availability` starts `unknown`; the first successful construction (a
dependency sanity check, not a server connection) flips to
`{state:"available", backend:"ts-native", capabilities}`; unrecoverable
composition errors flip to `unavailable` with `retryable` set appropriately.
There is no process to spawn, so `notEnabledOnService`-class failures do not
exist; availability is effectively static and cheap, which the status UI may
say honestly ("in-process; no service handshake").

## 11. Driver gap analysis: tedious v20 vs Microsoft.Data.SqlClient 7.0

Repo facts: no tedious/mssql/msnodesqlv8 dependency exists anywhere in the
monorepo today; MSAL (`@azure/msal-node` ^5.2.5) is already in-tree. MDS
baseline: 7.0 GA (2026) — `Encrypt=Strict` since 5.1, `AccessTokenCallBack`
since 5.2, `SqlJson` since 6.0, `SqlVector` since 6.1, pluggable SSPI in 7.0.
tedious baseline: v20.0.0 (2026-06-21, Node ≥ 22, bundles `@azure/identity`
^4.13.1).

### 11.1 Summary matrix

Legend: **cap** column = the `SqlBackendCapabilityId` that carries the answer;
UX = what the user sees when it matters.

| Feature | MDS | tedious v20 | `ts-native` position | cap |
| --- | --- | --- | --- | --- |
| SQL login | ✅ | ✅ `default` | Supported | `auth.sqlLogin` ✅ |
| Entra access-token pass-in | ✅ (+ callback 5.2) | ✅ `azure-active-directory-access-token`; also `token-credential` (v18.3) for `@azure/identity` objects | Supported; fresh token per open | `auth.entraToken` ✅ |
| Entra interactive/device-code | ✅ built-in | ❌ built-in; ✅ via extension-owned MSAL/VS Code auth → token pass-in | Supported (arguably better: one consent UX, shared token cache) | `auth.entraToken` ✅ |
| Windows integrated (SSPI/Kerberos) | ✅ (pluggable in 7.0) | ❌ (NTLM needs explicit user/pass/domain; no Kerberos; tediousjs#415/#660) | **Unsupported** — typed canOpen failure + fallback routing | `auth.integrated` ❌ |
| Service principal / managed identity / default credential | ✅ | ✅ (`-service-principal-secret`, `-msi-*`, `-default`) | Blocked by the shared adapter policy (unsupported for all backends today); driver-ready when policy lands | `auth.servicePrincipal` (policy-gated) |
| TLS encrypt / TrustServerCertificate | ✅ | ✅ (Node TLS; custom CA via `cryptoCredentialsDetails`) | Supported; never add a cert-ignore setting | — |
| TDS 8.0 `encrypt=strict` | ✅ (5.1+) | ✅ since v16.3.0; open field report tediousjs#1725 vs Force Strict Encryption | Supported, flagged for explicit conformance testing in our envs before advertising | `connect.tds8Strict` ✅ (validate) |
| Always Encrypted (+ enclaves) | ✅ | ❌ (PR #1020 open since 2019; scaffolding only) | **Hard gap** — capability false; AE columns read as ciphertext varbinary; UX explains + suggests `sts2-local` | `security.alwaysEncrypted` ❌ |
| Named pipes / shared memory / **LocalDB** | ✅ | ❌ TCP only (#348); SQL Browser UDP instance resolution works | **Hard gap** — `(localdb)\...` profiles fail typed → fallback routing | `connect.localdb` ❌ |
| MARS | ✅ | ❌ (one request per connection; wishlist #512) | Irrelevant to our model (one active query per session; aux sessions cover concurrency) | informational |
| Connection resiliency / session recovery | ✅ (`ConnectRetryCount`) | ❌ (connect-time transient retry only) | Session loss = honest `connectionLost` (same as STS2 socket death); no resume claimed | `diag.resumeAfterDisconnect` ❌ (both) |
| multiSubnetFailover / readOnly intent / Azure+Fabric redirect routing | ✅ | ✅ (`multiSubnetFailover`, `readOnlyIntent`, ENVCHANGE routing; Fabric since v19.1) | Supported when profile options are threaded | `connect.*` ✅ |
| Failover partner (mirroring) | ✅ auto | ⚠️ partner surfaced (v19.2 event), no auto-failover | Not implemented in v1; loss + reconnect covers the UX | — |
| decimal/numeric > 15–17 digits | ✅ exact (`SqlDecimal`) | ⚠️ parsed to JS `number` — silent precision loss; no string mode (issues #163/#678) | **Fidelity gap** — policy §11.3; capability false; `exact:false` cells | `types.preciseDecimals` ❌ |
| money | ✅ | ⚠️ JS number (÷10 000) | Same policy as decimal | (same) |
| bigint | ✅ | ✅ lossless string | Supported (string carrier is exactly what `number:approx` wants) | — |
| datetime2/time sub-ms | ✅ 100 ns | ⚠️ JS Date + non-enumerable `nanosecondsDelta` | **Recovered** by cellEncoder (reads the delta; formats full precision) | `types.subMsTime` ✅ |
| datetimeoffset | ✅ offset preserved | ❌ offset bytes read and discarded (UTC instant only) | **Fidelity gap** — policy §11.3; capability false | `types.datetimeOffsetPreserved` ❌ |
| varchar/nvarchar/varbinary(max)/XML/UDT per-value streaming | ✅ `SequentialAccess` | ❌ PLP values fully buffered per value (historic OOM #837) | **Consumption gap**: `maxCellBytes` truncation still enforced on delivery, but the transient buffer is the full value. Documented; guarded by status warnings; upstream candidate | `types.largeValueStreaming` ❌ |
| UTF-8 collations | ✅ | ✅ (v12.2) | Supported | — |
| XML | ✅ | ✅ string | Supported | — |
| JSON native type (SQL 2025) | ✅ (`SqlJson`, 6.0) | ❌ (PR #1683 open); server down-converts to nvarchar on TDS 7.4 | Reads work today as nvarchar (isJson via provider metadata); native wire type absent | `types.jsonNative` ❌ (reads fine) |
| VECTOR type (SQL 2025) | ✅ binary (`SqlVector`, 6.1) | ❌ native type; arrives as JSON-array varchar on older TDS | **Mitigated**: text mode = STS2 default anyway; `vectorBinaryV1` synthesized by text→f32le transcode (lossless — engine emits shortest-round-trip float32 text) | `types.vectorBinaryV1` ✅ via transcode |
| geometry/geography/hierarchyid (CLR UDT) | ✅ (`Microsoft.SqlServer.Types` → WKB with Z/M) | ⚠️ raw SQLCLR `Buffer`, no parsing, read-only | Binary transport (STS2 default) works day one; `spatialWkbV1` via SQLCLR→WKB transcoder (node-mssql `udt.js` lineage parser + WKB writer, Z/M) in a scoped task; curves/edge shapes fall back per-cell `unrenderable` | `types.spatialWkbV1` staged |
| sql_variant | ✅ | ⚠️ read yes / param no | Read-only is all we need | — |
| TVP / output params / bulk load / transactions+savepoints | ✅ | ✅ | Out of scope for the query surface (no domain API for them) | — |
| Distributed transactions / query notifications | ✅ | ❌ | Non-goals | — |
| Multiple result sets / rowcounts / PRINT+RAISERROR with line numbers, in stream order | ✅ | ✅ (`done*` rowCount; `infoMessage`/`errorMessage` with number/state/class/procName/lineNumber; single serialized token stream preserves order) | Supported — the query-tool core is solid | `messages.*` ✅ |
| Attention-based cancel | ✅ | ✅ `request.cancel()` → `ECANCEL`; `cancelTimeout` 5 s default | Supported (§10.4) | `exec.cancel` ✅ |
| SHOWPLAN / STATISTICS XML | ✅ | ✅ via raw batch (`execSqlBatch`) | Supported (engine always uses execSqlBatch) | `plan.estimated`/`plan.actual` ✅ |
| Connection pooling / sp_reset | ✅ built-in | ❌ built-in (by design; `connection.reset()` provided for pools) | Not needed in v1 (one connection per session) | — |
| SPID | ✅ (`ServerProcessId`, 7.0) | ❌ | `SELECT @@SPID` at open (already how the binding probes) | — |

### 11.2 Hard gaps vs mitigable gaps

**Hard (no JS workaround; capability = false, UX routes to `sts2-local`):**
Always Encrypted (+ enclaves); Windows integrated auth; LocalDB/named pipes;
MARS (moot); per-value LOB streaming (transient memory only — output is still
truncated correctly); session resiliency; native JSON/VECTOR wire types
(functional fallbacks exist; type-fidelity parity pending upstream).

**Mitigated in `ts-native` (this design):** vector binary cells (text
transcode); spatial WKB (UDT transcode, staged); datetime2 sub-ms
(`nanosecondsDelta`); bigint (string); SPID (probe); GO/SET semantics
(execSqlBatch + existing batch splitting); interactive Entra (extension-owned
MSAL/VS Code auth is already the product's model); pooling/reset (not needed);
plan retrieval (T-SQL level, no driver dependency).

**Fidelity policies required (§11.3):** decimal/numeric/money precision;
datetimeoffset offset loss.

### 11.3 Type-fidelity policies (review decision required)

A query tool must not display silently wrong values. Two tedious behaviors
lose information *before the engine sees the value*:

1. **decimal/numeric/money beyond ~15–17 significant digits** — parsed to a JS
   double inside the driver.
   **Policy P1 (recommended):** cellEncoder marks affected cells' string
   carrier `exact:false` whenever `precision > 15` on the column (conservative
   per-column rule; per-value exactness is undecidable post-parse). The grid
   already renders the `exact:false` affordance; the column tooltip explains
   and offers the provider switch. Capability `types.preciseDecimals=false`
   lets fidelity-sensitive features (export pipelines, chat-to-data numeric
   answers) detect it. In parallel: upstream a `returnDecimalAsString`-style
   option to tedious (RFC #678 has been open since 2014; scoped patch, strong
   contribution candidate) — landing it flips the capability to true.
   **Alternative P1b:** block-ship the backend until the upstream option
   exists. Rejected as default: it holds the entire lane hostage to one
   fidelity case most workloads never hit, and the capability contract exists
   precisely to make the limitation honest.
2. **datetimeoffset offset discard** — the driver keeps the UTC instant,
   drops the original offset.
   **Policy P2 (recommended):** display the UTC instant with explicit
   `+00:00` suffix and mark the column via capability
   `types.datetimeOffsetPreserved=false` (tooltip: "offset normalized to UTC
   by this backend"). Same upstream-contribution note (the offset byte is read
   and discarded — a small patch exposes it).

Both policies are pinned by golden-cell fixtures (asserting the *documented*
divergence, so an upstream fix shows up as a deliberate fixture update).

### 11.4 Upstream contribution budget

Ordered by leverage: (1) decimal/numeric-as-string option (#678); (2)
datetimeoffset offset preservation; (3) native VECTOR type (parallel to PR
#1683's JSON approach); (4) JSON type review help (#1683); (5) per-value PLP
streaming (largest; unblocks `types.largeValueStreaming`). Track as `TSQ-U*`
side tasks; none block v1.

## 12. Observability, Debug Console, and debug overrides

### 12.1 Structured events and spans

Register the `sqlDataPlane.tsNative.*` family in
`perftest/packages/observability-contracts` (the conformance test fails on
unregistered names) and emit through `diag`:

| Span/event | Fields (all classified; safe only) |
| --- | --- |
| `sqlDataPlane.tsNative.connection.open` (span) | authKind, encrypt mode, engineEditionId, outcome class, durationMs; server name digested |
| `sqlDataPlane.tsNative.query.execute` (span, submit→terminal) | commandKind, tag, status, resultSets, rows, pages, encodedBytes, durationMs, cancel/dispose flags; **never SQL text** (digest only, matching `RequestDescriptor.textDigest`) |
| `sqlDataPlane.tsNative.query.firstPage` (event) | ms from submit — the A/B headline metric (also a perftest marker, §13.2) |
| `sqlDataPlane.tsNative.query.page` (metric, sampled) | rowCount, approxBytes, encodeMs, sinkWaitMs, pauseState — the TS analog of STS2's `sts2.query.stats` (readMs/creditWaitMs/encodeMs), so pipeline A/B is apples-to-apples |
| `sqlDataPlane.tsNative.query.cancel` (span) | ackMs, uncertain |
| `sqlDataPlane.tsNative.session.lost` (event) | reason class, activeQuery present |
| `sqlDataPlane.auth.token.*` | reused as-is from the shared token source (already registered) |

Correlation: bind the session entity (`bindEntityTrace(sessionId, traceId)`)
so query spans stitch under the user action; `timingClass:
officialSameProcess` throughout (a genuine advantage — the STS lane's
cross-process spans are epoch-aligned diagnostics).

### 12.2 Status and Debug Console page

- `TsNativeStatus` snapshot (modeled on `LanguageServiceStatus`): backend
  availability, capability set (with masked entries flagged), per-session
  rows (state, database, spid, activeQuery phase, pagesDelivered,
  undeliveredPages high-water, credit stalls, bytes), driver version, override
  summary, recent error classes. Exposed through `statusSummary()` (the
  existing `mssql.sqlDataPlane.showStatus` JSON doc grows a per-backend
  section) and a `Dc*` RPC.
- Debug Console hosted page ("SQL Data Plane" page, `ts-native` section first;
  `sts2-local` status can join later): live session/query table, capability
  matrix with reasons, override editor (live-editable session-only overrides,
  the completions pattern), actions (`closeSession`, `cancelQuery`,
  `simulateLoss` — gated to when fault injection is enabled, `copyStatus`,
  `exportDiagnostics`). Implemented as a console-hosted debug host
  (`getState()` / `dispatchAction()` / throttled `onDidChange`), lazily
  constructed and honest-empty when the data plane is disabled.

### 12.3 Capture and replay with a provider dimension

- Query Studio run capture already exists (`mssql.queryStudio.replay.enabled`,
  digests-only by default). The backend contributes: run records gain
  `backendKind` + capability snapshot + resolved tuning, and the Replay Lab's
  matrix axes gain **backend** (`ts-native` × `sts2-local`) alongside page/
  tuning dimensions — replaying one captured run across providers is the
  primary triage tool for parity bugs and the qualitative half of A/B.
- Replays stamp the standard `FeatureReplayTags` so provider-comparison runs
  sit side-by-side on the diag timeline.
- Deeper engine capture (per-event driver traces) rides a
  `FeatureCaptureStore` in `capture.ts`, off by default, bounded ring,
  persisted only via the existing trace codec with redaction; SQL text only
  under time-bounded elevated capture (Session Diag policy, never a setting).
- Advertised capabilities stay honest: `diag.replayDescriptors=true`
  (`RequestDescriptor` is domain-level and cheap), `diag.captureControl=true`
  (session-diag capture modes apply), `diag.resumeAfterDisconnect=false`.

### 12.4 Debug overrides and fault injection

`mssql.sqlDataPlane.tsNative.overrides` (object, scope `application`, unknown
keys ignored, all session-visible in status/diag):

```jsonc
{
  "pageRows": 1000,            // lower-only vs defaults, same clamp rules
  "pageBytes": 262144,
  "maxCellBytes": 1048576,
  "windowPages": 4,
  "capabilityMask": {          // force capabilities OFF (never on) to test gating UX
    "types.spatialWkbV1": false
  },
  "faults": {                  // only honored when debugConsole enabled; never in perftest official runs
    "openFailRate": 0.0,       // inject typed open failures
    "openDelayMs": 0,
    "pageDelayMs": 0,          // latency per page delivery
    "dropAfterPages": 0,       // sever the socket after N pages (connectionLost path)
    "tokenNearExpiry": false   // simulate <60s token to exercise rejection
  }
}
```

Fault injection lives in the driver port boundary (`fakeTdsDriver` implements
it natively; `tediousDriver` wraps with the fault decorator), so the identical
knobs work in unit tests, live debugging, and replay matrix cells. This fills
the acknowledged gap that no shared fault-injection facility exists today, in
the place the replay framework expects it (a config dimension). perftest
official passes assert overrides are absent (honesty guard).

### 12.5 Logging and redaction

One `logger2.withPrefix("TsNativeBackend")` for developer text; all structured
state through `diag`. Hard rules inherited: secrets/connection material are
`NEVER_PLAIN`; server/database names digest-only in redacted mode; error
identities via `diagnosticErrorClass` (closed set — tedious error `code`s like
`ECANCEL`/`ETIMEOUT`/`ESOCKET` map into the allow-list); canary literals
(`CANARY-pw-…`, token canary) asserted absent from every artifact in tests.

## 13. Performance design and the A/B methodology

### 13.1 Why `ts-native` should win the common path — and where it may not

Expected wins (to be proven, not assumed):

1. **Cold start / first connection.** No STS spawn, no .NET startup, no
   multiplexer handshake, no `v2/initialize` round trip. The lane cost is one
   TCP+TLS+login sequence. perftest's `extension.stsSpawn` marker simply
   disappears from the trace.
2. **Per-page overhead.** STS lane: driver → C# page build → UTF-8 JSON encode
   → stdio frame → multiplexer → JSON parse → DTO mapping → RowStore. Native
   lane: TDS parse → JS cells → RowStore, zero serialization; pages transfer
   by reference. The `sts.query.pipeline.*` numbers (encode/serialize/UTF-8
   measurement costs) are the exact costs that vanish.
3. **Memory.** One runtime (no dedicated .NET process with its own GC heap and
   journal); the total-resource roll-up is the honest comparator.
4. **Cancellation latency.** Attention issued directly on the socket; no
   cross-process hop.

Expected risks (the A/B must watch these, not just the wins):

1. **Extension-host CPU contention.** TDS parsing + cell encoding now runs on
   the exthost event loop. STS moves that work off-process; a 100k-row stream
   that costs 300 ms of parse CPU is 300 ms of exthost time `ts-native` spends
   and `sts2-local` doesn't. Mitigations: yield discipline (R23), and the
   interaction scenarios (scroll during streaming) as first-class A/B gates.
   If they regress, the follow-up is a worker_thread engine host with
   transferable page buffers (Open Question Q4) — the engine's no-vscode
   design keeps that door open.
2. **JS parse throughput** on wide/many-column shapes (single-threaded,
   allocation-heavy). The C# floor is 50k rows/s on 1M×10; the native engine
   must be measured on the same order of workload (`querystudio-query-100k-narrow`
   and a new 1M-row scenario if needed).
3. **Large single values** (PLP buffering, §11.1) — a pathological
   `SELECT hugeBlob` costs a transient full-value buffer.

### 13.2 perftest integration — Path A now, Path B build-out

**Path A (no harness changes; first numbers in days).** Backend is an
activation-time setting and per-scenario `userSettings` land in
`settings.json` pre-launch — so:

- add paired variants via a `registerBackendPair()` helper in the scenario
  registry: same fixture/SQL/markers, `userSettings` differing only in
  `mssql.sqlDataPlane.backend` → `querystudio-query-10k-sts2` /
  `querystudio-query-10k-tsnative`, etc.;
- initial matrix (all existing fixtures): `querystudio-open`,
  `querystudio-query-10k`, `-100k-narrow`, `-wide-1000x300`, `-large-cells`,
  `-10k-messages`, `-100-resultsets`, the scroll-interaction scenario, and
  `querystudio-sqlcmd-run`; plus metadata cold/warm hydration once a metadata
  scenario exists on the pair;
- run both variants in one config (same machine session), compare with
  `head-to-head --baseline-scenario …-sts2 --candidate-scenario …-tsnative`
  (median/p95, signed delta bars, honesty notes). Both variants share the QS
  marker family, so the phase map lines up without translation.

**Path B (first-class backend dimension; the durable setup).** Per
web-backend §21.6/§23.3, which this plan extends to the local pair:

1. run-level `userSettings` override in `PerfConfig` + merge in
   `runPipeline.ts` (scenario defaults → matrix cell → run override) so one
   scenarioId runs under N backends;
2. backend provenance: **excluded from `environmentHash`** (so `compare` will
   pair the runs) but stamped as a run tag and on `query.submit` markers
   (exactly like `tuningDigest`), and recorded in `environment.json`;
3. new metric spans, emitted by the product behind `PERF_MODE` for **both**
   backends: `mssql.queryStudio.query.firstPage` (submit→first `onRowsPage`
   durable acceptance) and derived rows/sec + bytes/sec; credit-stall time
   (sink-wait accumulated) as the backpressure comparator;
4. **total-resource fairness rule:** the report compares
   exthost+STS-process CPU/working-set for `sts2-local` against exthost-only
   for `ts-native` (processSampler already samples children); STS-lane
   pipeline metrics get an explicit "not applicable to ts-native" honesty note
   rather than an empty column;
5. a `backend-bench` report grouping by (scenario, backend) with span split:
   connect / open / submit→accept / first page / complete / render / cancel;
6. gating posture: non-gating until baselines are captured and reviewed; then
   per-metric budgets via the existing `compare` Welch-t machinery (mirroring
   the web-backend rule "performance owners turn the matrix into budgets after
   a prototype supplies baselines").

**Fairness invariants:** identical fixtures and SQL; identical
`tuning.overrides` (both backends honor the same clamp rules); same warmup
policy; `capabilityMask`/faults asserted absent; token spans remain
`measurementEligible=false` (Entra smoke lanes stay diagnostic per
sts2_entra_auth §12); report every dropped/inapplicable lane explicitly.

### 13.3 Success criteria (initial, to be ratified after baselines)

- Connect-to-ready (fresh profile, local SQL): `ts-native` ≥ 40% faster
  end-to-end than the `sts2-local` path including spawn amortization on first
  connect; no worse than parity on warm reconnect.
- `querystudio-query-10k` submit→complete and submit→render: ≥ parity, target
  ≥ 20% improvement.
- 100k-narrow rows/sec: ≥ parity with `sts2-local` end-to-end; exthost-only
  CPU cost documented.
- Scroll-interaction p95 during streaming: no regression beyond noise.
- Total working set during 100k stream: ≤ `sts2-local`'s exthost+STS sum.
- Cancel ack p95: ≤ `sts2-local`.

## 14. What TypeScript can do better than C# here

Beyond raw perf (§13.1), captured so the doc review can push back explicitly:

1. **Zero serialization boundary.** The single biggest structural win: pages
   are built once, in the process that consumes them. Every STS2 page pays
   UTF-8 encode + frame + parse + DTO map; `ts-native` pays none of it.
2. **Uniform observability.** The engine's spans are same-process
   monotonic (`officialSameProcess`), live in the same diag substrate as the
   UI, and correlate without loopback listeners or epoch alignment. The Debug
   Console shows engine state with no cross-process diagnostics protocol.
3. **Debuggability.** One debugger attaches to the whole path
   (webview → controller → orchestrator → engine → driver). Capture/replay,
   fault injection, and capability masks are config dimensions in the existing
   replay framework rather than separate C# tooling.
4. **Deployment weight.** No platform-specific service download, no .NET
   runtime; pure-JS dependency (~ single npm package) that works unchanged on
   Node remote hosts (Codespaces server side). Install size and cold-start
   both benefit.
5. **Iteration speed.** Backend changes ship with the extension (one repo,
   one CI, one test run); no cross-repo protocol/version negotiation for
   domain-level features.
6. **Direct backpressure.** RowStore spill pressure propagates through one
   awaited promise into `request.pause()` — no credit protocol, no ack
   ordinal bookkeeping, no orphan buffer, and none of the D-0015 class of
   cross-implementation credit bugs.
7. **Second implementation as architecture proof.** A genuinely independent
   implementation of the domain contract keeps the seam honest (the
   web-backend's anti-drift argument — "one STS runtime" — does not cover a
   TS engine, so the conformance corpus becomes the drift gate; that
   discipline benefits `sts2-remote` too).

Where C# stays ahead, honestly: driver completeness (§11 — AE, integrated
auth, LocalDB, exact decimals, LOB streaming, native VECTOR/JSON), off-process
CPU isolation, the journaled digest-identical replay machinery, and a
decade of SqlClient hardening. That is exactly what the capability contract
and provider switching are for.

## 15. Testing strategy

### 15.1 Layers

| Layer | What | Gate |
| --- | --- | --- |
| L1 Engine unit | `queryEngine`/`pageBuilder`/`cellEncoder`/transcoders against `fakeTdsDriver` scripted steps (resultSet/rows/message/done/error/sever/hang/crash + faults) | PR |
| L2 Domain conformance | `sqlDataPlaneConformance.test.ts` runs against **FakeBackend, Sts2Backend (scripted wire), and TsNativeBackend (fakeTdsDriver)** — third binding; all existing cases (ordering, backpressure serialization, sink-throw, one-terminal, busy, idempotent close, chaos) plus new capability cases | PR |
| L3 Scenario corpus | TS scenario runner interpreting the STS2 YAML corpus (fake-adapter subset, ~50 files) against the engine + a TS invariant checker (I1, I2, I3, I5, I8, I9-equivalents at the domain level) | PR (quick) / nightly (full) |
| L4 Live engine parity | Golden-cell + behavior parity vs `sts2-local` on `STS2_SQLSERVER_CONNSTRING` (SQL 2025: vector/spatial/json/UDT fixtures) and `STS2_AZURESQLSERVER_CONNSTRING`; Entra lane via `STS2_AZURESQLSERVER_ENTRAID_CONNSTRING`; skip-not-fail when unset (STS2 `EngineGate` convention) | nightly / pre-merge on lane machines |
| L5 Product e2e | Query Studio smoke through `ts-native` (open→connect→run→grid→cancel→messages) — new, since no QS e2e exists; minimal Playwright spec + the perftest scenarios as the de facto e2e | nightly |
| L6 Perf | §13.2 Path A/B | scheduled |
| L7 Soak/reliability | Repeated open/execute/cancel/dispose/close cycles (1k+), loss injection at every phase, heap/handle leak assertions, event-loop stall budget | nightly |
| L8 Privacy | Canary literals through every path (open failure, capture, status, export, replay) | PR |

### 15.2 Capability and routing tests

- Oracle unit tests: T1/T2 precedence, `perSession` semantics, alternatives
  computation, struct↔ID mapping completeness (compile-time exhaustiveness +
  runtime table check).
- `canOpen` fails before credential resolution (spy on providers — the
  sts2_entra_auth tripwire pattern).
- Fallback flow: integrated profile + `prompt`/`auto`/`off` matrix; fallback
  visibility events asserted.
- UX gating: `capabilityMask` overrides drive Spatial/Vector disabled states
  with reasons and switch affordances (webview state assertions).
- Mixed composition: two documents on different kinds; per-kind config change
  drains only its kind; metadata partitioning respected.

### 15.3 Golden-cell parity harness

A standalone runner (usable from mocha and the perf harness) that executes a
pinned fixture set through two `ISqlConnectionService` instances against the
same server and diffs: decoded `CellValue` per cell, raw `CompactPage.values`
entries, `typeHints`, `nullBitmap`, truncation markers (prefix + digest),
`ResultSetMetadata`, `ServerMessage` sequences (number/severity/state/line),
rowsAffected, and terminal summaries. Divergences must be either fixed or
pinned as documented policy divergences (P1/P2 fidelity cells assert
`exact:false` + capability, not value equality). Fixture set = the STS2
`SqlClientEngineTests` type matrix + vector (text and binary) + spatial
(SRID/Z/M, curves) + wide/huge/many-sets/many-messages shapes.

### 15.4 Determinism note

The native backend does not claim STS2's digest-identical journal replay
(capability `diag.resumeAfterDisconnect=false`, journal replay not
advertised). Its determinism bar is: L1–L3 are fully deterministic (scripted
driver, no wall clock in assertions); flaky = P0, never retried (STS2
simulator convention adopted).

## 16. Implementation plan

Tasks are sized for the existing build cadence (journal/PROGRESS discipline;
`tsq:` commits). Gates named per task; L-numbers refer to §15.1.

| Task | Scope | Exit gate |
| --- | --- | --- |
| **TSQ-0** | Doc review + decisions: enum value (`ts-native`), capability ID set, fidelity policies P1/P2, metadata realm (Q3), fallback default | Reviewed doc; decisions recorded here |
| **TSQ-1** | Registry/composition v2 in `sqlDataPlane`: `backendFactory.ts` (multi-entry, single-flight, fingerprints, drain, typed unknown-kind), settings migration (`sts2-local` + alias), passive status; `sts2-local` + `fake` on the new registry; no behavior change | Existing L2 suites green on new composition; factory unit tests |
| **TSQ-2** | Capability contract: ID taxonomy, struct extensions + derived IDs, oracle, `requiredCapabilities` in `canOpen` (all backends), `SqlDataPlane.CapabilityUnsupported`, consumer requirement sets | Oracle/routing tests (§15.2, minus UX) |
| **TSQ-3** | Backend skeleton: tedious dep, `ITdsDriver` port + `tediousDriver` + `fakeTdsDriver`, session open/close/info/messages/db-change, SQL login only, `SELECT 1` end-to-end behind `backend: ts-native` | L1 basics; manual smoke |
| **TSQ-4** | Query engine complete: paging, window/pause-resume, ordered lane, terminals incl. synthesized, cancel/dispose/busy, deadlines, option clamps | **L2 third binding green**; L1 chaos suite |
| **TSQ-5** | Cell encoding parity: typeHints, wrappers, truncation+digests, fidelity policies P1/P2, guid/datetime formats | Golden-cell harness built; L4 type matrix green on local lane |
| **TSQ-6** | Auth completion: Entra token path (shared source, freshness/drift/deadline), integrated → typed failure, secret containment + canaries | L4 Entra lane; L8 |
| **TSQ-7** | Vector transcoder (`vectorBinaryV1`) + per-cell fallbacks; column vector facts | Vector fixtures in L4; Vector Workbench works on ts-native |
| **TSQ-8** | Observability: span family + contract registration, `TsNativeStatus`, showStatus integration, Debug Console hosted page | Contract conformance test green; page functional |
| **TSQ-9** | Overrides + fault injection + capture/replay host with backend matrix dimension | Fault-driven L1/L7 cases; replay matrix demo |
| **TSQ-10** | Scenario corpus port: YAML runner + TS invariant checker | L3 quick gate in PR CI |
| **TSQ-11** | perftest Path A: `registerBackendPair`, paired variants for the §13.2 matrix, head-to-head baseline report | First A/B report reviewed; risks (§13.1) assessed |
| **TSQ-12** | Selection UX: per-document override command/status segment, capability fallback flow (prompt/auto/off), QsState capability derivation + hints + `providerTypeName`, plan-toggle gating, suggest-switch helper | §15.2 UX tests; S2/S3/S4 scenario walkthroughs |
| **TSQ-13** | Spatial transcoder (`spatialWkbV1`): SQLCLR parser + WKB writer (Z/M), per-cell unrenderable fallbacks, curve policy | Spatial fixtures in L4; Spatial pane works on ts-native |
| **TSQ-14** | perftest Path B: run-level userSettings, backend provenance tag/markers, firstPage + rows/sec spans, total-resource roll-up, `backend-bench` report | Same-scenarioId gated `compare` demo; budgets proposed |
| **TSQ-15** | Consumer hardening: Metadata + OE v2 validated on ts-native (watchdog/recycle paths), SQLCMD `:connect`, aux sessions; L5 e2e smoke; L7 soak; settings.md + memory docs updated | Nightly lanes green one week |

Dependencies: TSQ-1/2 unblock everything and benefit `sts2-remote`
independently; TSQ-7 and TSQ-13 are parallel to TSQ-8..12; TSQ-11 lands as
soon as TSQ-4..6 make the scenarios run.

## 17. Constraints and risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| tedious bus factor (one primary maintainer) | Slow upstream fixes | Pin exact version; vendor patches if forced; upstream budget §11.4; the driver port isolates a future driver swap |
| Exthost event-loop pressure on huge streams | UI jank | R23 yield discipline; interaction scenarios as A/B gates; worker_thread fallback design (Q4) |
| Silent numeric infidelity | Wrong data shown | P1 policy + `exact:false` affordance + capability + fixtures pinning the divergence |
| TDS 8.0 strict regressions (tediousjs#1725) | Connection failures on hardened servers | Explicit strict-mode conformance tests on our lanes before advertising `connect.tds8Strict` |
| Parity drift between two implementations | Divergent behavior per backend | L2 shared conformance + L3 corpus + L4 golden-cell as permanent gates (the drift budget is zero; this replaces the "one runtime" argument) |
| PLP full-value buffering | Transient memory spikes | Documented capability; status warning surface; upstream streaming contribution (long-term) |
| Mixed composition confusion (which backend am I on?) | Support burden | Provider identity in status segment, session info, diagnostics, and every error's `backend.kind`; fallback always visible |
| Capability API over-generalization | Design churn | IDs are add-only strings; struct remains the binding contract; oracle is read-only — extension is cheap, removal is the thing to avoid |
| A/B unfairness (STS lanes missing on ts-native) | Wrong conclusions | Total-resource roll-up rule + explicit honesty notes in reports (§13.2 item 4) |

## 18. Open questions

1. **Q1 — Enum naming:** `ts-native` (this doc) vs `native-ts` vs `nativeTypeScript`
   (the language-service toggle uses `nativeTypeScript`). Pick one before TSQ-1;
   the doc recommends `ts-native` for symmetry with `sts2-local`/`sts2-remote`.
2. **Q2 — Fidelity policy ratification:** accept P1/P2 (ship with honest
   `exact:false`/UTC normalization + capabilities) or block spatial-grade
   fidelity features until upstream options land?
3. **Q3 — Metadata cache realm:** may `ts-native` and `sts2-local` share one
   MetadataStore partition (same local realm, same identity), or does
   fingerprint v2's backend-kind key stand for v1? (Doc default: keyed
   separately; revisit with data on hydration cost.)
4. **Q4 — Worker-thread engine host:** pre-build the worker offload in TSQ-4
   (cost: page transfer serialization returns) or wait for interaction-scenario
   evidence? (Doc default: wait for evidence; keep the engine host-agnostic.)
5. **Q5 — Default flip criteria:** what must be true (parity gates, A/B
   deltas, soak duration, dogfood time) before `ts-native` becomes the default
   for profiles it fully supports? Propose criteria after TSQ-11 baselines.
6. **Q6 — Chat-to-data:** should `RunQueryTool` move from STS v1
   `query/simpleexecute` onto the data plane (gaining capability awareness and
   the ts-native fast path) in this effort's tail, or stay a separate work item?
7. **Q7 — QS e2e ownership:** this plan adds a minimal smoke (L5); who owns a
   real Query Studio e2e suite, independent of backends?
8. **Q8 — Spatial curve scope:** must the SQLCLR transcoder handle arc
   segments (CircularString et al.) in TSQ-13, or is per-cell `unrenderable`
   acceptable for curves at first ship?
9. **Q9 — Per-document override persistence:** in-memory only (doc default) or
   persisted per-document (workspace state) across window reloads?
10. **Q10 — `metadata.endpoints`:** wire the declared-but-unused capability to
    a real typed metadata surface (relevant to `sts2-remote` §25-Q31) or drop
    it from the struct during TSQ-2?

## 19. References

- Domain API and binding: `vscode-mssql/extensions/mssql/src/services/sqlDataPlane/api.ts`,
  `sqlDataPlaneService.ts`, `fakeBackend.ts`; `services/sts2/sts2Backend.ts`, `wire/v2.ts`
- Consumers: `queryStudio/{documentSessionBinding,executionOrchestrator,executionHost,rowStore,queryStudioController}.ts`,
  `services/metadata/metadataService.ts`, `objectExplorer/v2/sessions/oeV2SessionRegistry.ts`
- STS v2: `sqltoolsservice/docs/sts2/{SPEC,CONTRACT,COMPONENTS,STATE-MACHINE,INVARIANTS,TRACE-SCHEMA,SCENARIO-MATRIX}.md`;
  `src/sts2/**/{Sts2Defaults,WireValueEncoder,SqlLargeValueReader,DriverEffectRunner,SqlClientDriver,SqlClientSession,InvariantChecker}.cs`;
  `test/sts2/scenarios/*.yaml`
- Observability: `src/diagnostics/{diagnosticsCore,redaction,diagnosticsManager}.ts`,
  `src/diagnostics/featureCapture/{captureStore,replayEngine}.ts`,
  `src/sharedInterfaces/{debugConsole,featureReplay}.ts`,
  `coding-docs/observability-docs/{01-architecture,02-debug-console,03-instrumentation-reference}.md`
- perftest: `packages/perftest-cli/src/run/runPipeline.ts`, `scenarios/registry.ts`,
  `regression/{headToHead,compareRuns,statistics}.ts`, `docs/{ARCHITECTURE,SQL_PROVISIONING,STS_INSTRUMENTATION}.md`
- Prior designs: `coding-docs/querystudio_web_backend.md` (§13, §21.6, §23.3, §25),
  `coding-docs/sts2_entra_auth.md`, `coding-docs/settings.md`,
  `coding-docs/query-result-tabs/geospatial_pane.md`,
  `coding-docs/query-optimization/EXECUTION_PLAN.md`
- Driver: tedious v20 — github.com/tediousjs/tedious (releases; `src/connection.ts`,
  `src/value-parser.ts`, `src/data-type.ts`; issues #163, #348, #415, #512, #660,
  #678, #837, #1020, #1522, #1682, #1683, #1709, #1725); node-mssql `lib/udt.js`
  (spatial UDT parser lineage); Microsoft.Data.SqlClient release notes
  (learn.microsoft.com — 5.1 Strict, 5.2 AccessTokenCallBack, 6.0 SqlJson,
  6.1 SqlVector, 7.0); Microsoft Node.js driver guidance
  (learn.microsoft.com/sql/connect/node-js)
