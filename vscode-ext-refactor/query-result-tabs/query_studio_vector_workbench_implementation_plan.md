# Query Studio Vector Workbench - Feature Implementation and Execution Plan

**Status:** Implementation-ready cross-repository execution specification  
**Date:** 2026-07-10  
**Target branches:** `microsoft/sqltoolsservice@dev/query`, `microsoft/vscode-mssql@dev/query`  
**Primary surface:** Query Studio results pane  
**Feature gate:** `mssql.queryStudio.vectorWorkbench.enabled`, default off until the vertical slice passes  
**Primary audience:** Engineers, code-reviewers, performance engineers, security reviewers, and AI coding agents

## 0. Purpose, scope, and precedence

This document defines the end-to-end implementation plan for a SQL Server 2025 and Azure SQL Vector Workbench in Query Studio. It covers STS2 ingestion, SQL Data Plane contracts, result-store ownership, bounded local analysis, database-aware diagnostics, Query Studio RPC, rendering, accessibility, security, performance, testing, pull-request sequencing, and release criteria.

The companion UX document, `query_studio_vector_workbench_ux_spec.md`, is normative for visible behavior and interaction. This document is normative for architecture, authority boundaries, data contracts, budgets, SQL generation, and implementation order.

The geospatial design and execution addendum supplied with this task establish the result-pane architecture and quality bar. Their reusable principles remain in force:

- use the ordinary STS2 result path rather than a feature-specific query protocol;
- keep the extension-host result store authoritative;
- use leases and bounded secondary reads;
- never place rows in coarse state;
- use opaque controller-bound sessions;
- make host budgets authoritative;
- preserve result-row identity;
- release leases on every terminal path, including normal completion;
- fix compact capture before adding richer values;
- make canvas or WebGL an optional representation, not the only accessible interface;
- separate transport facts, decode facts, semantic support, and interpretations;
- keep diagnostics and telemetry value-free.

Where this document explicitly locks a decision, an implementation agent must not substitute a broader architecture without code-review approval.

## 1. Verdict and executive recommendation

Proceed with the feature as a **Vector Workbench**, not a vector-only viewer.

The implementation has two layers:

1. **Typed vector result foundation**
   - recognize native SQL Server float32 vectors in the STS2 SqlClient driver;
   - encode them as a bounded, provider-neutral binary tagged cell;
   - preserve them through compact pages, RowStore, spill, snapshots, copy, export, and pinned results;
   - add vector-aware result metadata and display behavior;
   - keep current float16 driver fallback honest.

2. **Bounded workbench**
   - analyze captured results through `IQueryResultStore` leases;
   - perform heavy numerical work in an extension-host worker;
   - send only derived summaries and projection coordinates to the webview;
   - run table-aware search, index, and pipeline experiments on an explicit isolated SQL Data Plane session;
   - display generated T-SQL and execution evidence for every server operation.

The flagship feature is exact versus approximate search debugging. PCA is included, but it is not the product thesis and does not become the default workspace.

## 2. Locked MVP decisions

### 2.1 Product and UI

- Add a conditional `Vector` sibling tab to Query Studio results.
- Do not auto-open it.
- Default workspace is `Profile`.
- Workspaces are Profile, Search, Compare, Projection, Index, and Pipeline.
- Detached result analysis is available without a table binding.
- Search, Index, and most Pipeline actions require a verified base-table binding.
- Completed and terminal partial result sets are supported. Live progressive analysis while the query is still streaming is deferred.
- Live Query Studio ships first. The service/component boundary must be pinned-compatible. Pinned parity follows in the next narrow change if it cannot fit safely in the first UI PR.
- The webview performs zero network requests.
- No database DDL executes from the pane.
- No model call occurs without explicit confirmation.

### 2.2 Typed result support

| Source | MVP result behavior |
| --- | --- |
| Native `VECTOR(n, float32)` returned through Microsoft.Data.SqlClient 6.1+ | Full typed result contract and detached numerical analysis. |
| `VECTOR(n, float16)` current driver/TDS fallback | Preserve as text fallback with vector metadata when provable. No automatic arbitrary-result numerical interpretation. Offer controlled table-bound analysis. |
| Older service or client without vector binary negotiation | Preserve prior JSON/text behavior. Vector tab can be limited or absent according to metadata confidence. |
| Arbitrary JSON array string | Not a vector automatically. Future explicit `Interpret as vector JSON` action only. |
| Mixed dimensions in one result expression | Transport each supported cell with its own dimensions. Analysis isolates compatible groups and reports mismatches. |

### 2.3 Local analysis

- Profile and PCA operate on a host-resolved bounded sample.
- Heavy numerical work runs in a Node `worker_threads` worker packaged as a separate extension entry point.
- PCA MVP is deterministic 2D, centered by default.
- Optional L2 normalization is explicit and precedes centering.
- UMAP, t-SNE, and 3D are deferred.
- Projection rendering uses a local custom Canvas 2D layer. Existing Recharts can be used for histograms and rank charts. Add no new charting dependency in MVP.
- Original-space distances remain authoritative.

### 2.4 Database experiments

- Use a new isolated auxiliary `ISqlSession` opened from the same verified connection profile and database.
- Run exact, approximate, and forced-ANN variants sequentially on the same diagnostic session.
- The session does not see local temporary tables or uncommitted changes from the Query Studio session. The UI states this.
- Use structured filters only in automated comparisons.
- Every query can be opened in an editor.
- A successful `FORCE_ANN_ONLY` query is direct ANN evidence. Approximate syntax alone is not.
- Plan operator recognition is an evidence-gated parser. Do not claim ANN from an unapproved Showplan heuristic.

### 2.5 Security and privacy

- Vector values, source text, labels, keys, distances, projection points, and model output are result data.
- They do not enter telemetry, diagnostics, replay descriptors, capture artifacts, or production performance marks.
- Fix full compact-row capture elision before vector binary payloads are enabled.
- Query Studio and pinned results adopt a tested per-surface CSP before the Vector preview ships.

## 3. Current branch inventory and verified code findings

The following findings were verified against the public `dev/query` branches on 2026-07-10. File line numbers will move; symbols and behavior are the durable anchors.

### 3.1 `microsoft/sqltoolsservice@dev/query`

| Path / symbol | Current behavior | Vector consequence |
| --- | --- | --- |
| `Packages.props` | Pins `Microsoft.Data.SqlClient` 6.1.5. | Native `SqlVector<float>` support is already present. No driver upgrade is required for float32 MVP. |
| `SqlClientSession.PumpResultSetAsync` | Uses `SequentialAccess`; specializes only large text/binary; all other values use `reader.GetValue(i)`. | A native vector currently falls into the generic provider-object path. |
| `SqlClientSession.ReadColumnsAsync` | Preserves `DbColumn.DataTypeName` as `ColumnInfo.EngineType`, plus precision, scale, and `ColumnSize`. | Vector type is discoverable, but dimension/base-type metadata behavior needs a live provider matrix. |
| `WireValueEncoder.Encode` | Bounds strings and byte arrays; known scalars get wrappers; unknown objects use invariant `Convert.ToString`. | A `SqlVector<float>` is not transported losslessly and may inflate into JSON text. |
| `SqlRowsPageBuilder` | Groups rows using approximate provider-object estimates. | Native vectors can defeat the intended page-byte target unless recognized. |
| `DriverEffectRunner` compact path | Unknown engine types fall back to string type hints; encoded byte accounting uses JSON string length. | Add a vector hint and stop treating UTF-16 character count as exact UTF-8 bytes. |
| `CaptureElision.ElideInput` | In digest mode, wraps only top-level `rows`. It does not wrap `compact`. | `compact.values`, `compact.nullBitmap`, and future vector bytes can enter journals. This is a P0 privacy blocker. |
| `Sts2Defaults` | Current defaults include 1,000 rows, 256 KiB page target, 1 MiB cell bound, and 64 MiB frame ceiling. | One vector cell is small, but a 1,000-row page of high-dimensional vectors can exceed the page target by an order of magnitude. |

### 3.2 `microsoft/vscode-mssql@dev/query`

| Path / symbol | Current behavior | Recommended insertion |
| --- | --- | --- |
| `services/sqlDataPlane/api.ts` | Domain API isolates features from STS2 wire DTOs; `ColumnMetadata` and `CellValue` have no vector variant. | Add backend-neutral vector metadata and tagged-cell support without leaking `SqlVector`. |
| `services/sts2/sts2Backend.ts` | Compact tagged objects largely pass through; noncompact normalization is narrower; unknown type hints become strings. | Add one shared vector codec used by compact and noncompact paths. |
| `sharedInterfaces/queryStudio.ts` | `QsResultColumn` has SQL type/XML/JSON markers; coarse state is row-free. | Add optional vector metadata only. Do not add vector values or samples to state. |
| `queryStudio/rowStore.ts` | Bounded memory/spill; grid reads promote protected cache; analysis reasons do not; only contiguous projection exists. | Add `vectorAnalysis` read reason and general sparse projection. |
| `queryResults/queryResultTypes.ts` | `IQueryResultStore` exposes run identity, leases, windows, streams, summaries, and bounded ownership. | This is the sole captured-result source for the workbench. Add `vectorWorkbench` lease owner. |
| `queryResults/queryResultAccessService.ts` | Shared snapshots and transform engine already establish bounded secondary-consumer patterns. | Reuse conventions, but keep vector operations controller-bound rather than accepting store IDs from the webview. |
| `queryResults/transformEngine.ts` | Fused bounded scans, deterministic seeded sampling, cooperative yield, honest partial results. | Reuse its budget and determinism patterns. Do not force vector math through its scalar cell semantics. |
| `queryStudio/executionHost.ts` | Owns the current `RetainedRowStore`, run ID, execution state, and result summaries. | The live Vector source binds here and retains the existing store. |
| `queryStudio/documentSessionBinding.ts` | Owns the verified profile/auth closure and one user session; metadata uses separate acquisition. | Add a narrow auxiliary-session acquisition method for explicit vector diagnostics. |
| `queryResults/queryResultContextService.ts` | Active selection assumes display-like row/column. | Add a distinct vector result-row selection kind. Do not mislabel a result ordinal as a displayed row. |
| `webviews/pages/QueryStudio/app.tsx` | Owns sibling Results/Messages/Query Plan tabs and panel-local grid state. | Add conditional Vector tab and lazy component boundary. Keep analysis logic out of `app.tsx`. |
| `package.json` | Recharts is already present. | Use it for bounded histograms/rank views; no extra chart dependency is necessary. |
| `scripts/bundle-extension.js` | Builds `extension` and `serviceInstallerUtil` Node entries. | Add a separate `vectorAnalysisWorker` entry. |
| `controllers/webviewBaseController.ts` | Shared HTML currently has no CSP and includes inline styling. | Add a per-surface CSP hook; migrate Query Studio and pinned results before preview release. |

### 3.3 Existing architecture that must not be bypassed

```text
SQL Server
  -> Microsoft.Data.SqlClient SqlDataReader
  -> STS2 SqlClient driver
  -> ordinary credited STS2 row pages
  -> SQL Data Plane binding
  -> ExecutionOrchestrator sink
  -> extension-host RowStore / RetainedRowStore
  -> IQueryResultStore lease and bounded reads
  -> Vector analysis or diagnostic services
  -> bounded derived RPC
  -> Query Studio Vector pane
```

Do not add:

- a second raw-result cache;
- a Vector-specific database result stream outside ordinary execution;
- a React loop over ordinary `qs/getRows`;
- provider CLR values in SQL Data Plane or webview contracts;
- a webview-supplied store, run, source, snapshot, budget, or lease identifier as authority.

## 4. SQL Server and Azure SQL capability matrix

The workbench must probe capabilities because preview rollout, database configuration, permissions, and index versions vary.

### 4.1 Surface matrix

| Capability | Detection | Workbench use |
| --- | --- | --- |
| Native vector type | result metadata, provider value, catalog | Eligibility and typed result transport. |
| Dimensions/base type | `sys.columns.vector_dimensions`, `vector_base_type_desc`; per-cell typed length | Validation and binding. |
| Exact distance | compile or runtime probe for `VECTOR_DISTANCE` | Exact search and pair validation. |
| Norms | probe `VECTOR_NORM` | Optional server-side verification and generated diagnostics. |
| Normalization | probe `VECTOR_NORMALIZE` | Optional server operation; local normalization remains available. |
| Approximate search | compile/runtime probe for `VECTOR_SEARCH` | Search debugger. |
| Latest approximate syntax | index version and syntax probe | Generate `TOP (N) WITH APPROXIMATE`. |
| Forced ANN | syntax probe plus compatible index | Confirm ANN path. |
| Vector indexes | `sys.vector_indexes` visibility | Index workspace. |
| Index health | `sys.dm_db_vector_indexes` visibility | Maintenance state. |
| External models | `sys.external_models` visibility | Pipeline model selector. |
| Embedding generation | probe `AI_GENERATE_EMBEDDINGS` | Query-vector generation and re-embed. |
| Chunk generation | compatibility level plus probe `AI_GENERATE_CHUNKS` | Chunk debugger. |
| Preview features | database configuration and operation errors | Explain unavailable behavior. |

### 4.2 Capability probe result

```ts
export interface VectorDatabaseCapabilities {
    readonly checkedAtEpochMs: number;
    readonly databaseName: string;
    readonly serverMajorVersion?: number;
    readonly engineEdition?: number;
    readonly compatibilityLevel?: number;
    readonly previewFeaturesEnabled?: boolean;
    readonly vectorType: boolean;
    readonly vectorFloat16Catalog: boolean;
    readonly vectorDistance: boolean;
    readonly vectorNorm: boolean;
    readonly vectorNormalize: boolean;
    readonly vectorSearch: "unavailable" | "legacy" | "latest" | "mixed";
    readonly forceAnnOnly: boolean;
    readonly vectorIndexesCatalog: boolean;
    readonly vectorIndexHealthDmv: boolean;
    readonly externalModelsCatalog: boolean;
    readonly generateEmbeddings: boolean;
    readonly generateChunks: boolean;
    readonly permissionLimitations: readonly VectorPermissionLimitation[];
}
```

Rules:

- Cache by connection profile fingerprint, database, and catalog generation for a short TTL.
- Invalidate on database change, reconnect, DDL sniff affecting relevant objects, or explicit refresh.
- Probe with metadata-only or compile-safe queries where possible.
- Treat error numbers as hints, not the only compatibility contract. Preserve safe error categories and avoid persisting server text.
- Never enable a UI action solely because the server version string appears new enough.

## 5. Recommended architecture

### 5.1 Data flow

```text
Typed query result
  -> SqlClientVectorValueReader
       recognize exact native vector
       copy float32 components to explicit little-endian bytes
       validate dimension and finite policy
  -> DriverVectorValue
  -> WireValueEncoder vector tag
  -> ordinary STS2 compact row page
  -> Sts2Backend strict vector normalization
  -> RowStore / retained snapshots
  -> VectorResultSource controller adapter
  -> sparse, bounded row scan with vectorAnalysis reason
  -> packed Float32Array sample in extension host
  -> Node vectorAnalysisWorker
       profile, compare, PCA, derived point chunks
  -> opaque pull RPC with derived data only
  -> Vector Workbench webview

Table-aware operation
  -> verified VectorTableBinding
  -> isolated auxiliary ISqlSession
  -> generated exact/approx/index/model SQL
  -> bounded VectorDiagnosticRunner
  -> result keys, distances, plans, messages, metrics
  -> comparison/evidence model
  -> opaque pull RPC
  -> Vector Workbench webview
```

### 5.2 Ownership boundaries

| Component | Owns | Must not own |
| --- | --- | --- |
| STS2 SqlClient driver | Provider recognition, native float32 extraction, dimension, binary component copy | UI summaries, PCA, SQL table binding |
| STS2 runtime | Tagged wire encoding, negotiation, page/frame safety, capture privacy | `SqlVector` public contracts, model semantics |
| SQL Data Plane | Backend-neutral vector tag and column metadata | Worker algorithms, UI state |
| RowStore / result store | Immutable tagged cells, spill, leases, bounded windows | Parsed whole-result matrices or projection cache |
| VectorResultReader | Sparse reads, sampling, validation, result-row identity, host scan budgets | Canvas state, database query generation |
| Vector analysis worker | Numeric arrays, deterministic algorithms, derived summaries | Result-store leases, VS Code APIs, SQL sessions |
| VectorDiagnosticRunner | Isolated SQL session, generated SQL, plans, result comparison | User-query session state, hidden DDL |
| Vector pane | Controls, selection, derived visualization, accessibility, generated SQL display | Authoritative rows, raw whole-result vector cache, network requests |

## 6. Blocking prerequisites and required amendments

### 6.1 P0 privacy: elide the complete compact row payload

Current digest capture wraps only `rows`. Query Studio uses compact pages whose result data is under `compact`.

Required independent fix:

1. On `driver.queryEvent` row events, wrap the complete `compact` object before journal/digest capture.
2. Include `values`, `nullBitmap`, `typeHints`, and future result-derived fields.
3. Treat null patterns as result data.
4. Restore only at the existing wire/effect edge.
5. Remove side-table entries on success, suppression, error, cancel, disposal, and coordinator shutdown.
6. Add canaries for scalar, binary, truncated, vector-shaped, and malformed both-rows-and-compact payloads.
7. Verify journal, replay export, diagnostics export, and failure bundles.

Do not enable vector binary negotiation until these tests pass.

### 6.2 P0 shared result-cell codec

A vector tag must not fall through generic `{$t, v}` display logic. Add one dependency-light isomorphic codec used by:

- STS2 compact and noncompact normalization;
- RowStore window serialization;
- grid preview and tooltip;
- copy;
- text view;
- cell document;
- CSV, JSON, and INSERT export;
- transforms and cell comparison;
- query-result AI/tool serialization;
- pinned results.

Do not create a vector-only display helper in the webview.

### 6.3 P0 provider and metadata matrix

Run live tests on every supported Windows, Linux, and macOS RID against SQL Server 2025 and representative Azure SQL targets:

- `GetValue`, `GetSqlValue`, and `GetSqlVector<float>` CLR types;
- null and typed-null behavior;
- `DbColumn.DataTypeName`, `DataType`, `ColumnSize`, and base lineage fields;
- float32 and float16;
- vector expressions, variables, stored-procedure outputs, CTEs, views, and direct table columns;
- minimum, maximum, and invalid dimensions;
- non-finite components if the engine permits them;
- cancellation and sequential access;
- old-server and old-client downgrade behavior;
- all-null result columns;
- multiple vector columns and result sets.

Record evidence before freezing dimension metadata rules.

### 6.4 P0 page and frame safety

A maximum float32 vector has only 7,992 raw bytes, but base64 and JSON wrappers expand it, and a page may contain hundreds of vectors. The current provider-object estimator is not sufficient.

Required minimum:

- recognize `DriverVectorValue` in byte estimation;
- include base64 expansion and wrapper overhead conservatively;
- add a final complete UTF-8 JSON-RPC frame measurement before transport write;
- fail with a stable typed row-too-large result when one complete row cannot fit;
- never drop a cell, drop a row, or truncate binary vector components to recover.

Preferred platform fix:

- encode each cell/row once in the runtime;
- pack pages from exact encoded UTF-8 sizes;
- keep one encoded representation through page construction and writer;
- advertise `pageBytesHonored` only when the implementation is truthful.

The preferred exact page repacker can be a separate foundation PR. The frame guard is non-negotiable.

### 6.5 P0 sparse projection

Vector analysis often needs a vector column plus distant key, label, group, source-text, or timestamp columns. Repeated single-column reads can deserialize a spilled page multiple times.

Add general sparse projection to `CellWindowRequest` and `RowStreamRequest` before shipping label/group analysis.

### 6.6 P0 auxiliary session seam

The current `DocumentSessionBinding` owns the profile and authentication closure but exposes only the user session. Add a narrow session lease for diagnostic operations. Do not borrow the metadata session or user session.

### 6.7 P0 Query Studio CSP

Add a reusable per-surface CSP hook and adopt it for Query Studio and pinned results. The Vector webview needs only local scripts, styles, images, fonts, and canvas. No remote hosts are permitted.

## 7. STS2 typed vector contract

### 7.1 Negotiation

Service capability:

```json
{
  "capabilities": {
    "vectorBinaryV1": true
  }
}
```

Per-execute option:

```json
{
  "options": {
    "vectorEncoding": "binary-v1"
  }
}
```

Rules:

- Initialize advertisement states support but does not enable the new cell shape.
- Query Studio opts in per execute only when the feature gate is enabled and its codec is ready.
- The normalized option is included in reducer/effect arguments and replay identity.
- Old clients that do not opt in retain the prior safe representation.
- Unsupported options are rejected or explicitly ignored according to the STS2 compatibility policy. Never emit a new tag to a client that did not opt in.

### 7.2 Provider-neutral driver value

Illustrative C# contract:

```csharp
public sealed class DriverVectorValue
{
    public required int Dimensions { get; init; }
    public required string BaseType { get; init; }      // "float32" in v1
    public required string Encoding { get; init; }      // "f32le"
    public required byte[] ComponentBytes { get; init; }
}

public sealed class DriverVectorUnavailableValue
{
    public int? Dimensions { get; init; }
    public string? BaseType { get; init; }
    public required string Reason { get; init; }
}
```

Provider CLR types stop at the SqlClient driver boundary.

### 7.3 Exact recognition

Recognize native float32 vectors by supported SqlClient type identity, not by arbitrary type-name suffix and not by JSON shape.

Recommended classification order:

1. `reader.IsDBNull(i)` remains normal null.
2. Metadata indicates candidate SQL vector type.
3. `reader.GetSqlVector<float>(i)` or `GetValue(i) is SqlVector<float>` according to matrix evidence.
4. Validate `IsNull`, `Length`, and component memory length.
5. Copy components into explicit little-endian IEEE 754 bytes.

Do not expose the internal TDS `SqlVector` header. The public v1 wire payload is component bytes only.

### 7.4 Little-endian encoding

Do not use `MemoryMarshal.AsBytes` without an endianness contract. Encode explicitly:

```csharp
byte[] bytes = new byte[vector.Length * sizeof(float)];
for (int i = 0; i < vector.Length; i++)
{
    int bits = BitConverter.SingleToInt32Bits(vector.Memory.Span[i]);
    BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(i * 4, 4), bits);
}
```

This makes replay and cross-platform decode deterministic.

### 7.5 Wire shape

Successful value:

```json
{
  "$t": "vector",
  "version": 1,
  "status": "ok",
  "dimensions": 1536,
  "baseType": "float32",
  "encoding": "f32le",
  "byteLength": 6144,
  "data": "<base64 component bytes>"
}
```

Unavailable value:

```json
{
  "$t": "vector",
  "version": 1,
  "status": "unavailable",
  "reason": "unsupportedBaseType",
  "dimensions": 1536,
  "baseType": "float16"
}
```

TypeScript contract:

```ts
export type VectorBaseType = "float32" | "float16";

export interface VectorCellOkV1 {
    readonly $t: "vector";
    readonly version: 1;
    readonly status: "ok";
    readonly dimensions: number;
    readonly baseType: "float32";
    readonly encoding: "f32le";
    readonly byteLength: number;
    readonly data: string;
}

export type VectorTransportReason =
    | "unsupportedBaseType"
    | "metadataMismatch"
    | "providerValueMismatch"
    | "decodeFailed"
    | "cellLimit";

export interface VectorCellUnavailableV1 {
    readonly $t: "vector";
    readonly version: 1;
    readonly status: "unavailable";
    readonly reason: VectorTransportReason;
    readonly dimensions?: number;
    readonly baseType?: VectorBaseType;
}

export type VectorCellEncodingV1 = VectorCellOkV1 | VectorCellUnavailableV1;
```

Rules:

- Use `data`, not `v`, so the tag cannot collide with the generic typed-scalar wrapper.
- `byteLength` must equal `dimensions * 4` for v1 success.
- Base64 decoded length must equal `byteLength`.
- Per-cell dimensions remain authoritative even when column metadata is present.
- Do not include a duplicate JSON display string in the wire payload.
- Do not truncate vector bytes. A vector is complete or unavailable.
- Normal null uses the existing null bitmap, not a vector status.
- An all-null typed vector column can still be eligible through metadata, but detached numerical actions explain that no analyzable value exists.

### 7.6 Float16 policy

Official driver support currently transmits float16 as JSON text rather than native binary. V1 does not pretend otherwise.

Result-path policy:

- preserve the original text cell through existing bounded text handling;
- attach column metadata only when the provider/catalog evidence proves that the source is vector float16;
- mark transport mode `textFallback`;
- ordinary grid and export keep the JSON representation;
- detached numeric analysis is disabled by default because arbitrary result lineage and exact dimensions can be ambiguous;
- offer table binding.

Table-bound float16 analysis:

- query catalog dimensions/base type;
- use an explicit bounded diagnostic `CAST(vector_column AS nvarchar(max))` or the provider fallback proven by Phase 0;
- parse a strict numeric JSON array;
- require exact dimension match;
- promote components to float32 only for local analysis;
- label every result `Source float16, analyzed as float32 after JSON conversion`;
- use the native server vector column for search experiments, not the promoted local copy.

### 7.7 Compact type hint

Add an explicit hint such as `vector:f32le:v1` aligned to the column. The tag itself remains self-describing. The hint permits fast cell routing and compatibility checks but is not trusted without structural validation.

## 8. Shared result-cell codec and ordinary result behavior

### 8.1 Module

Recommended path:

```text
extensions/mssql/src/sharedInterfaces/queryResultCellCodec.ts
```

Responsibilities:

- strict `isVectorCellEncodingV1` guard;
- base64 length and structural validation;
- decoding a bounded component prefix or full component array;
- purpose-specific formatting;
- safe equality/hash behavior;
- compact and noncompact normalization;
- no VS Code, React, DOM, Node-only, or provider imports.

### 8.2 Purpose-specific text

```ts
export type CellTextPurpose =
    | "gridPreview"
    | "copy"
    | "textView"
    | "cellDocument"
    | "csvExport"
    | "jsonExport"
    | "insertExport"
    | "toolSummary";
```

Recommended policy:

| Surface | `status: ok` behavior |
| --- | --- |
| Grid preview | Bounded JSON component preview plus `VECTOR(n, float32)`, for example `[0.0123, -0.44, ...]  VECTOR(1536)`. |
| Tooltip | Dimensions, base type, byte length, bounded component preview. |
| Copy cell | Exact JSON numeric array under existing copy budget; otherwise honest bounded behavior. |
| Cell document | Exact JSON array, one line or pretty-printed according to existing cell-document controls. |
| Text view | Exact JSON array subject to existing result text budget. |
| CSV | One escaped JSON-array field. |
| JSON export | A JSON array value when the exporter can preserve typed values; otherwise a documented string representation. Never internal tag JSON. |
| INSERT export | `CAST(N'[ ... ]' AS VECTOR(n))`, or `VECTOR(n, float16)` for verified table-bound fallback. |
| Tool summary | `VECTOR(1536, float32)` unless an explicit result-data grant permits components. |

For `status: unavailable`, every surface produces a localized honest description with reason and known metadata. No base64, raw tag JSON, or `[object Object]` appears.

### 8.3 Grid operations

- Disable scalar ordering on typed vector cells because SQL vector values have no comparison ordering.
- Grid filtering supports null/not-null and perhaps status filters, not lexical JSON comparison.
- Exact vector equality is available only inside Vector Workbench and uses byte equality for float32 typed cells.
- Generic transform predicates treat vector cells as opaque and incomparable unless a future vector-specific transform is added.
- RowStore spill preserves the tag unchanged.

### 8.4 Decode API

```ts
export interface DecodedFloat32Vector {
    readonly dimensions: number;
    readonly values: Float32Array;
}

export function decodeVectorFloat32(cell: VectorCellOkV1): DecodedFloat32Vector;
export function decodeVectorPrefix(cell: VectorCellOkV1, maxComponents: number): number[];
export function vectorCellSummary(cell: VectorCellEncodingV1): VectorCellSummary;
```

Validate before allocating:

- dimensions between 1 and the supported maximum;
- byteLength exactly dimensions times four;
- base64 decoded length exactly byteLength;
- no integer overflow;
- operation budget can accept the vector.

## 9. Column metadata and result lineage

### 9.1 SQL Data Plane metadata

```ts
export interface VectorColumnMetadata {
    readonly kind: "vector";
    readonly transport: "binary-v1" | "textFallback";
    readonly dimensions?: number;
    readonly baseType?: VectorBaseType;
}

export interface ResultColumnLineageHint {
    readonly baseCatalog?: string;
    readonly baseSchema?: string;
    readonly baseTable?: string;
    readonly baseColumn?: string;
    readonly isExpression?: boolean;
}

export interface ColumnMetadata {
    // existing fields
    readonly vector?: VectorColumnMetadata;
    readonly lineage?: ResultColumnLineageHint;
}
```

Mirror only safe vector metadata into `QsResultColumn`. Do not place full provider metadata or unverified object authority in coarse state.

### 9.2 Metadata authority

- Per-cell dimensions/base type are authoritative for a typed cell.
- Column metadata is a declaration or hint and can be unknown.
- Base-table lineage from `DbColumn` is a suggestion only.
- Table-bound catalog metadata is authoritative for generated table SQL.
- If result metadata and catalog disagree, mark the binding stale and require review.

### 9.3 Catalog query

Use `sys.columns.vector_dimensions`, `vector_base_type`, and `vector_base_type_desc`, joined to `sys.types`. Also retrieve:

- object and column IDs;
- nullability;
- table/view type;
- primary key and unique index columns;
- compatible vector indexes;
- ordinary indexes on selected filter columns;
- row-count estimate where permission allows.

Do not use `sp_describe_first_result_set` as the sole source because current documentation states that it does not correctly report vector type.

## 10. General sparse projection

### 10.1 Contract

```ts
export interface CellWindowRequest {
    readonly resultSetId: string;
    readonly rowStart: number;
    readonly rowCount: number;
    readonly columnStart?: number;
    readonly columnCount?: number;
    readonly columnOrdinals?: readonly number[];
    readonly reason: RowReadReason;
}

export interface RowStreamRequest {
    readonly resultSetId: string;
    readonly rowStart: number;
    readonly rowCount: number;
    readonly chunkRows: number;
    readonly columnOrdinals?: readonly number[];
    readonly reason: RowReadReason;
}
```

Rules:

- Sparse and contiguous projection are mutually exclusive.
- Validate once; deduplicate ordinals while preserving requested order.
- Empty projection is either rejected or returns zero columns consistently across every store implementation.
- Project column metadata, type hints, values, and null bitmap in exactly the requested order.
- Include ordered ordinals in the served-window cache key.
- Support RowStore, RetainedRowStore, snapshots, and derived snapshots.
- Derived snapshots must map row IDs and projection without fetching full parent rows.
- A spilled page is materialized once for one sparse request.

### 10.2 New reasons and lease owners

```ts
export type RowReadReason =
    | /* existing */
    | "vectorAnalysis";

export type QueryResultLeaseOwnerKind =
    | /* existing */
    | "vectorWorkbench";
```

`vectorAnalysis` follows scan semantics and never promotes pages to the grid-protected cache.

## 11. Controller-bound result source and analysis sessions

### 11.1 Authority rule

The webview sends result-set and column selections. It never sends a store ID, run ID, snapshot ID, source ID, lease owner, or budget as authority.

The Query Studio controller binds to its current `RetainedRowStore`. The pinned controller binds to its owned snapshot. Each opens a lease internally.

### 11.2 Session state

```text
open
  -> scanning
  -> computing
  -> streamingDerived
  -> completed
  -> cancelled
  -> expired
  -> failed
```

Normal final completion removes the session and releases the store lease immediately.

### 11.3 Operation kinds

```ts
export type VectorAnalysisOperation =
    | VectorProfileOperation
    | VectorProjectionOperation
    | VectorCompareOperation
    | VectorSelectionProfileOperation;
```

Do not build a universal visualization-operation framework. This union belongs to the Vector feature.

### 11.4 Open contract

```ts
export interface QsVectorAnalysisOpenParams {
    readonly resultSetId: string;
    readonly vectorColumn: number;
    readonly labelColumn?: number;
    readonly groupColumn?: number;
    readonly keyColumns?: readonly number[];
    readonly operation: VectorAnalysisOperation;
}

export interface QsVectorEffectiveBudget {
    readonly maxRowsScanned: number;
    readonly maxSampleRows: number;
    readonly maxComponents: number;
    readonly maxInputBytes: number;
    readonly maxDerivedBytes: number;
    readonly maxEvalMs: number;
    readonly targetResponseBytes: number;
    readonly maxResponseBytes: number;
}

export interface QsVectorAnalysisOpenResult {
    readonly handle: string;
    readonly generation: string;
    readonly frozen: {
        readonly resultSetId: string;
        readonly rowCount: number;
        readonly complete: boolean;
        readonly truncatedReason?: string;
        readonly corrupt: boolean;
        readonly vectorColumn: number;
        readonly dimensions?: number;
        readonly baseType?: VectorBaseType;
    };
    readonly effectiveBudget: QsVectorEffectiveBudget;
}
```

The host resolves budgets from the query-results parameter registry. Webview requests cannot raise them.

### 11.5 Pull protocol

```ts
export interface QsVectorAnalysisNextParams {
    readonly handle: string;
    readonly generation: string;
    readonly sequence: number;
}

export type QsVectorAnalysisEvent =
    | { readonly kind: "progress"; readonly progress: VectorAnalysisProgress }
    | { readonly kind: "profile"; readonly result: VectorProfileResult }
    | { readonly kind: "projectionPoints"; readonly points: readonly VectorProjectionPoint[] }
    | { readonly kind: "projectionSummary"; readonly result: VectorProjectionSummary }
    | { readonly kind: "compare"; readonly result: VectorCompareResult }
    | { readonly kind: "terminal"; readonly status: VectorOperationTerminal };

export interface QsVectorAnalysisChunk {
    readonly handle: string;
    readonly generation: string;
    readonly sequence: number;
    readonly events: readonly QsVectorAnalysisEvent[];
    readonly payloadBytes: number;
    readonly done: boolean;
}
```

Rules:

- At most one `next` request is in flight per handle.
- Sequences are strictly monotonic.
- The manager buffers at most one bounded derived chunk per operation.
- The next request is the consumption/backpressure boundary.
- `cancel` is idempotent.
- Expiry, rerun, panel hide, disposal, selection-column change, and final completion release the lease and worker resources.
- Use `webviewPanel.visible`, not only active status, for host-side hidden cleanup.
- Inactive but visible split panels can remain alive under global caps.
- Counts are scoped to scanned/sample rows until a complete full scan is proven.

### 11.6 Result row identity

Every detached item uses:

```ts
export interface VectorResultIdentity {
    readonly resultRowOrdinal: number;
    readonly originRowOrdinal?: number;
}
```

`originRowOrdinal` exists only when a derived source explicitly provides lineage. Do not invent it.

## 12. Sampling and host scan behavior

### 12.1 Default sample strategy

Use deterministic uniform-window sampling rather than a naive prefix for projection/profile defaults. The goals are reproducibility, bounded spill reads, and broad result coverage.

Recommended strategy:

1. Determine effective sample cap:
   - configured max sample rows;
   - `floor(maxComponents / dimensions)`;
   - `floor(maxInputBytes / (dimensions * 4))`;
   - total available rows.
2. Divide the result into at most 32 windows.
3. Allocate rows proportionally across windows.
4. Use a deterministic seed derived from store run ID, result set ID, vector column, operation spec digest, and a fixed algorithm version.
5. Read windows in source-row order through sparse projection.
6. Exclude null/unavailable/mismatched cells with reason counts.
7. Do not replace excluded rows with unbounded extra reads. A bounded oversample factor can be configured and disclosed.

For a full profile explicitly requested by the user, scan sequentially under the larger full-scan budget.

### 12.2 Why not silent reservoir sampling

Reservoir sampling would be statistically reasonable but can force a full scan of millions of rows and spill pages. Uniform windows provide a predictable I/O cap and a sample distributed across the result. The UI reports the method.

### 12.3 Sample descriptor

```ts
export interface VectorSampleDescriptor {
    readonly method: "full" | "uniformWindows" | "selection" | "prefix";
    readonly seed?: string;
    readonly sourceRows: number;
    readonly rowsScanned: number;
    readonly vectorsAccepted: number;
    readonly vectorsRejected: number;
    readonly completeSourceScan: boolean;
    readonly windows?: number;
}
```

## 13. Extension-host numerical worker

### 13.1 Packaging

Add an entry point to `extensions/mssql/scripts/bundle-extension.js`:

```js
entryPoints: {
  extension: "src/extension.ts",
  serviceInstallerUtil: "src/languageservice/serviceInstallerUtil.ts",
  vectorAnalysisWorker: "src/queryResults/vector/vectorAnalysisWorker.ts",
}
```

The manager starts the worker from the packaged `dist/vectorAnalysisWorker.js` path. The worker imports no `vscode` API.

### 13.2 Transfer contract

The host builds one packed `Float32Array` matrix in row-major order plus bounded metadata arrays. Transfer the underlying `ArrayBuffer` to the worker rather than cloning it.

```ts
export interface VectorWorkerInput {
    readonly operationId: string;
    readonly kind: "profile" | "projection" | "compare";
    readonly rows: number;
    readonly dimensions: number;
    readonly vectors: ArrayBuffer;
    readonly resultRowOrdinals: Int32Array;
    readonly labels?: readonly string[];
    readonly groups?: readonly string[];
    readonly options: VectorWorkerOptions;
}
```

The manager must retain only the minimum metadata needed to map derived results. It must not hold a second full matrix after transfer.

### 13.3 Worker lifecycle

- one worker per active heavy operation in MVP, under a small global cap;
- terminate on cancel, expiry, rerun, panel hide, or manager disposal;
- worker messages include operation ID and generation;
- progress cadence is bounded, for example no more than four messages per second;
- errors return a safe category and stack only to local debug logs when diagnostics policy permits, without vector values;
- unit tests can run algorithms directly without spawning a worker.

### 13.4 Dependency policy

MVP should not add a broad data-science runtime. Implement only the required vector operations in a small audited module, or adopt a narrowly scoped permissive dependency after a Phase 0 spike proves:

- numerical correctness against reference fixtures;
- no full `d x d` covariance allocation for high dimensions;
- cancellation or bounded runtime integration;
- acceptable extension bundle and supply-chain review;
- deterministic output.

The algorithmic contracts below apply regardless of implementation choice.

## 14. Numerical algorithms and exact definitions

### 14.1 Common validation

For every accepted vector:

- dimension equals the active compatible group;
- component count equals dimension;
- component values are decoded exactly from float32 bytes;
- non-finite components are counted and excluded from algorithms that cannot support them;
- no normalization occurs unless the operation says so;
- float64 accumulation is used for sums, means, variance, norms, dot products, and distances;
- output arrays can use float32 where precision is sufficient for rendering.

### 14.2 Norms

Definitions:

```text
L1       sum(abs(x_i))
L2       sqrt(sum(x_i * x_i))
L-infinity max(abs(x_i))
```

Use a scaled sum-of-squares algorithm for L2 when needed to reduce overflow/underflow risk. Compare local results to server `VECTOR_NORM` fixtures.

### 14.3 Distance metrics

Definitions must match SQL labeling:

```text
cosine distance        1 - dot(a,b) / (norm2(a) * norm2(b))
euclidean distance     sqrt(sum((a_i - b_i)^2))
negative dot product   -sum(a_i * b_i)
```

Policy for zero-norm cosine:

- mark distance undefined;
- do not coerce to zero or one;
- count and display the affected pair.

Use compensated or pairwise summation where benchmark evidence justifies it. Test tolerances against SQL Server outputs.

### 14.4 Online component statistics

Use Welford/Chan accumulation for each dimension:

- count;
- mean;
- M2 variance accumulator;
- min;
- max;
- non-finite count.

Arrays are O(dimensions), not O(rows x dimensions) beyond the sample matrix already required for projection.

### 14.5 Exact duplicate detection

For native float32 typed cells:

- hash the raw component bytes with SHA-256 or a faster noncryptographic hash plus byte verification;
- never log the hash;
- groups require a final byte comparison to avoid collision assumptions;
- report exact binary duplicates only.

For table-bound float16 JSON analysis:

- label the method `Exact after JSON conversion to float32` unless a native float16 binary contract exists later.

### 14.6 Near-zero definition

Report separately:

- exact zero: every component bit represents numeric zero, treating `+0` and `-0` according to numeric comparison;
- near zero: L2 norm at or below an explicit threshold, default `1e-6`.

The threshold is part of the result and adjustable in Profile. Do not call near-zero vectors invalid.

### 14.7 Centroid and outliers

Centroid is the component-wise arithmetic mean over accepted sample vectors.

Default outlier score:

- selected metric distance from sample centroid;
- for cosine, undefined zero-norm rows are separated;
- show top N scores, median, and robust percentile threshold;
- do not apply a universal “bad” label.

A later robust medoid or local-density method is deferred.

### 14.8 Pair-distance distribution

- draw deterministic random pairs without replacement when practical;
- cap pair count, default 10,000;
- use the operation seed;
- report pair count and metric;
- group comparison samples within-group and between-group pairs separately.

### 14.9 Pairwise matrix

- soft cap 100 selected vectors;
- hard cap 200;
- O(n squared times dimensions) cost shown before operation above the soft cap;
- compute upper triangle and mirror;
- stream rows of the derived matrix if the final payload approaches RPC limits.

### 14.10 PCA 2D contract

Input preprocessing:

1. Optional row L2 normalization, explicit.
2. Compute component means in float64.
3. Center rows by subtracting means.

Required output:

- PC1 and PC2 score per accepted row;
- component vectors or a digest/version, not necessarily exposed to the webview;
- eigenvalue/variance for PC1 and PC2;
- total sampled variance;
- explained-variance percentages;
- sample descriptor;
- algorithm version and iteration count;
- convergence status.

Recommended covariance-free orthogonal iteration:

1. Deterministically initialize a `dimensions x 3` random matrix.
2. Orthonormalize its columns with modified Gram-Schmidt and reorthogonalization.
3. Repeat a fixed bounded number of iterations, initially 6 to 10:
   - compute `Z = X * Q`;
   - compute `Y = X^T * Z`;
   - orthonormalize `Y` to produce new `Q`;
   - test subspace convergence under a documented tolerance.
4. Form the small projected covariance `B = (XQ)^T(XQ)/(n-1)`.
5. Eigendecompose the 3 x 3 symmetric matrix with a bounded Jacobi method.
6. Rotate Q, sort by descending eigenvalue, and keep the first two components.
7. Compute scores `X * Q2`.
8. Compute total variance from the centered sample and explained percentages.

Why three working components for a two-component output:

- improves separation when the second and third eigenvalues are close;
- provides a convergence check;
- remains bounded.

Correctness requirements:

- deterministic for the same sample, seed, options, and algorithm version;
- component sign normalized deterministically, for example largest absolute loading positive;
- compare scores up to sign/rotation tolerance against NumPy or another approved reference fixture;
- explained variance within agreed relative tolerance;
- no explicit `dimensions x dimensions` covariance matrix;
- cancellation checked between matrix passes;
- time budget stops with an honest partial/no-result terminal rather than a half-projection.

### 14.11 Projection point payload

```ts
export interface VectorProjectionPoint {
    readonly resultRowOrdinal: number;
    readonly x: number;
    readonly y: number;
    readonly label?: string;
    readonly group?: string;
    readonly numericColor?: number;
}
```

Do not include vector components in the webview point payload.

## 15. Profile result contract

```ts
export interface VectorProfileResult {
    readonly scope: VectorSampleDescriptor;
    readonly dimensions: number;
    readonly baseType: VectorBaseType;
    readonly accepted: number;
    readonly nullCells: number;
    readonly unavailableCells: number;
    readonly dimensionMismatches: number;
    readonly nonFiniteVectors: number;
    readonly exactZeroVectors: number;
    readonly nearZeroVectors: number;
    readonly duplicateGroups: readonly VectorDuplicateGroupSummary[];
    readonly normSummaries: Readonly<Record<"norm1" | "norm2" | "norminf", DistributionSummary>>;
    readonly componentVarianceHigh: readonly ComponentSummary[];
    readonly componentVarianceLow: readonly ComponentSummary[];
    readonly distanceSample?: DistanceSampleSummary;
    readonly outliers: readonly VectorOutlierSummary[];
    readonly groupSummaries?: readonly VectorGroupSummary[];
    readonly partial: boolean;
    readonly partialReason?: VectorAnalysisPartialReason;
}
```

Only bounded row identities and labels needed for findings return to the webview. Full vectors remain in the result store.

## 16. Compare and arithmetic implementation

### 16.1 Single-cell inspection

A single typed vector cell can be inspected through a direct controller-bound request rather than opening a full analysis session.

```ts
export interface QsVectorCellInspectParams {
    readonly resultSetId: string;
    readonly resultRowOrdinal: number;
    readonly vectorColumn: number;
    readonly previewComponents: number;
}

export interface QsVectorCellInspectResult {
    readonly identity: VectorResultIdentity;
    readonly dimensions?: number;
    readonly baseType?: VectorBaseType;
    readonly status: "ok" | "null" | "unavailable" | "mismatch";
    readonly preview: readonly number[];
    readonly previewTruncated: boolean;
    readonly norms?: { norm1: number; norm2: number; norminf: number };
}
```

The request acquires a short-lived controller-bound store lease or uses an existing pane lease. The response never contains base64.

### 16.2 Compare basket reads

For selected result rows:

- validate against the frozen result row count;
- request one sparse window per compact row span where possible;
- cap selected rows;
- decode in the extension host;
- transfer the packed selection to the worker;
- return only metrics, top differing dimensions, and bounded component previews.

### 16.3 Arithmetic parser

Implement a constrained expression grammar, not `eval`:

```text
expression   := sum
sum          := product (("+" | "-") product)*
product      := scalar "*" primary | primary
primary      := symbol | function | "(" expression ")"
function     := "normalize" "(" expression ["," norm] ")"
             | "centroid" "(" symbol ("," symbol)+ ")"
             | "mean" "(" weightedList ")"
scalar       := finite decimal literal
symbol       := basket identifier
norm         := "norm1" | "norm2" | "norminf"
```

Rules:

- finite scalar literals only;
- no property access, function injection, loops, or dynamic names;
- exact dimension compatibility;
- operation count cap;
- output component magnitude guard;
- non-finite output is an error with no partial vector;
- output exists only in panel memory unless copied or used in an explicit search operation;
- output is labeled experimental.

### 16.4 Serialization to SQL vector literal

When an arithmetic result becomes a table search query vector:

- serialize using round-trip-safe finite float formatting;
- use invariant culture;
- cap total literal bytes;
- declare the exact vector type and dimensions;
- never concatenate user labels or free text into the literal;
- store the generated SQL only in operation memory.

## 17. Verified table binding and provenance

### 17.1 Binding contract

```ts
export interface VectorTableBinding {
    readonly version: 1;
    readonly profileFingerprint: string;
    readonly database: string;
    readonly objectId: number;
    readonly schemaName: string;
    readonly tableName: string;
    readonly vectorColumnId: number;
    readonly vectorColumnName: string;
    readonly dimensions: number;
    readonly baseType: VectorBaseType;
    readonly keyColumns: readonly VectorBindingColumn[];
    readonly labelColumn?: VectorBindingColumn;
    readonly sourceTextColumn?: VectorBindingColumn;
    readonly groupColumns?: readonly VectorBindingColumn[];
    readonly generatedAtColumn?: VectorBindingColumn;
    readonly expectedMetric?: VectorDistanceMetric;
    readonly expectedNormalization?: "unknown" | "unitNorm" | "notNormalized";
    readonly externalModel?: VectorExternalModelBinding;
    readonly chunking?: { readonly type: "fixed"; readonly size: number; readonly overlapPercent: number };
    readonly notes?: string;
    readonly catalogSignature: string;
}

export interface VectorBindingColumn {
    readonly columnId: number;
    readonly name: string;
    readonly sqlType: string;
    readonly nullable: boolean;
}
```

### 17.2 Binding verification

Verification must query catalog by object ID and column ID, then confirm:

- object is a base table for Search;
- vector column still exists and is vector typed;
- dimensions/base type match;
- key columns exist and are scalar;
- primary/unique key status;
- label/source/group columns exist;
- model object exists when configured and visible;
- vector-index metadata and versions;
- permissions needed for requested workspaces.

Compute `catalogSignature` from stable metadata fields. A DDL notification or a different signature marks the binding stale.

### 17.3 Key identity

Search recall comparison requires a deterministic row identity.

Preferred:

1. primary key columns in index order;
2. a verified unique non-null index;
3. explicit user-selected columns with a uniqueness verification query.

If uniqueness cannot be proven:

- Search can still show raw results;
- recall/overlap metrics are disabled or use a user-approved surrogate expression opened in editable SQL;
- the UI explains why.

Represent keys as a typed tuple internally. Use canonical JSON only for in-memory comparison, not SQL injection.

### 17.4 Local persistence

Persist profiles in extension workspace state using a key derived from:

- hashed connection/profile identity;
- database;
- object ID;
- vector column ID.

Do not persist:

- credentials;
- vector values;
- source text;
- query literals;
- search result keys;
- model output.

Provide explicit remove and clear-all controls.

## 18. Auxiliary diagnostic session

### 18.1 Required seam

Add to `DocumentSessionBinding` or a focused collaborator:

```ts
export interface AuxiliarySqlSessionLease extends vscode.Disposable {
    readonly session: ISqlSession;
    readonly database: string;
}

acquireAuxiliarySession(
    purpose: "vectorDiagnostics" | "vectorModelCall",
    database?: string,
): Promise<AuxiliarySqlSessionLease>;
```

Implementation requirements:

- use the already verified profile reference and credential provider closure;
- open a new SQL Data Plane session with an application name such as `vscode-mssql-vector-workbench`;
- select the current or bound database explicitly;
- never expose credentials to the webview or operation spec;
- cap concurrent auxiliary sessions per controller and globally;
- close on operation terminal, cancellation, disconnect, panel disposal, or timeout;
- preserve one auxiliary session across variants in one Search comparison;
- do not reuse the MetadataStore session;
- do not reuse the user query session in MVP.

### 18.2 Isolation disclosure

Because the session is separate:

- local/global temporary table behavior must be tested and documented;
- uncommitted changes on the query session are not visible under normal isolation;
- session SET options can differ;
- user-session open transaction state is shown as a warning before running diagnostics;
- the diagnostic runner explicitly sets only the options it requires and restores them in `finally`.

### 18.3 Command kinds and priority

Use SQL Data Plane command kinds/tags that distinguish operations without carrying user data:

```text
priority: interactive
commandKind: metadata | plan | query
safe tag: vector:capability, vector:searchExact, vector:searchApprox,
          vector:searchForced, vector:indexHealth, vector:modelEmbed,
          vector:chunkPreview
```

Tags are fixed enums, never table names, model names, or query text.

## 19. Vector diagnostic runner

### 19.1 Service placement

Recommended extension-host modules:

```text
extensions/mssql/src/queryResults/vector/
  vectorTypes.ts
  vectorCellCodec.ts                // shared path may live under sharedInterfaces
  vectorParams.ts
  vectorResultSource.ts
  vectorResultReader.ts
  vectorSamplePlanner.ts
  vectorAnalysisSessionManager.ts
  vectorAnalysisWorker.ts
  vectorAlgorithms.ts
  vectorBindingStore.ts
  vectorCatalogService.ts
  vectorCapabilityService.ts
  vectorDiagnosticSession.ts
  vectorSqlBuilder.ts
  vectorSearchRunner.ts
  vectorIndexDiagnostics.ts
  vectorPipelineRunner.ts
  vectorDiagnostics.ts
```

Controllers register RPC and bind owned sources. They do not implement scan or SQL experiment loops.

### 19.2 Search operation state

```text
open diagnostic session
  -> verify binding and capabilities
  -> materialize or generate query vector
  -> run exact variant
  -> run approximate variant
  -> optionally run forced ANN variant
  -> optionally collect actual plan for each variant
  -> compare keys/ranks/distances
  -> classify evidence
  -> stream derived result
  -> close session
```

Every stage is cancellable between commands. Active `QueryHandle.cancel()` is used during a command. Closing the session is the final fallback.

### 19.3 Search request

```ts
export type VectorDistanceMetric = "cosine" | "euclidean" | "dot";

export interface VectorSearchComparisonSpec {
    readonly bindingId: string;
    readonly queryVector: VectorQuerySource;
    readonly metric: VectorDistanceMetric;
    readonly k: number;
    readonly filters: readonly VectorStructuredPredicate[];
    readonly variants: readonly ("exact" | "approximate" | "forcedAnn")[];
    readonly collectActualPlan: boolean;
    readonly repetitions: number;
    readonly warmupRuns: number;
}
```

The webview sends a binding ID owned by the controller-local binding store, not arbitrary schema/table text. The host resolves and revalidates the binding.

### 19.4 Query-vector sources

```ts
export type VectorQuerySource =
    | { readonly kind: "resultRow"; readonly resultSetId: string; readonly resultRowOrdinal: number; readonly vectorColumn: number }
    | { readonly kind: "pastedJson"; readonly json: string }
    | { readonly kind: "localExpression"; readonly expressionId: string }
    | { readonly kind: "modelText"; readonly modelBindingId: string; readonly text: string; readonly parametersJson?: string };
```

Security rules:

- `pastedJson` is validated as a flat finite numeric array before SQL generation;
- `localExpression` resolves from panel/session memory, not arbitrary host IDs;
- `modelText` requires explicit confirmation token minted after the user reviews egress details;
- source text is never logged or persisted;
- request sizes are bounded.

## 20. Safe SQL generation

### 20.1 General rules

`VectorSqlBuilder` is the only module that produces automated diagnostic SQL.

- All identifiers come from verified catalog bindings and are escaped with a tested `quoteIdentifier` equivalent to `QUOTENAME` semantics.
- Automated SQL does not accept raw identifier strings from the webview.
- Filter values are declared as typed variables.
- Free-form filter SQL is not accepted in the automated runner.
- K, dimensions, chunk size, overlap, and repetition values are host-validated integers and emitted as literals only after range checks.
- Vector JSON is generated by the host from validated finite components or validated model output.
- String literals use `N'...'` and doubled quotes.
- Date/time, GUID, numeric, and binary literals use type-aware converters.
- Generated SQL includes a header comment stating operation kind, capability assumptions, and that it was generated by Vector Workbench. The comment contains no vector data.
- The exact SQL shown to the user is the SQL executed, aside from plan wrapper batches managed by the runner.

### 20.2 Exact ground-truth query

Illustrative latest template:

```sql
DECLARE @q VECTOR(1536) = CAST(N'[0.1,0.2,...]' AS VECTOR(1536));
DECLARE @p0 nvarchar(100) = N'Technical';

SELECT TOP (20)
       t.[chunk_id],
       t.[chunk_label],
       VECTOR_DISTANCE('cosine', @q, t.[embedding]) AS [distance]
FROM [dbo].[DocumentChunks] AS t
WHERE t.[embedding] IS NOT NULL
  AND t.[category] = @p0
ORDER BY [distance] ASC;
```

Rules:

- exact query uses `VECTOR_DISTANCE` to make ground truth unambiguous;
- add a deterministic key tie-break only in an outer query when it does not change the exact top-K set semantics;
- capture all rows tied at the Kth distance only in a later tie-aware mode. MVP marks tie ambiguity from returned distances;
- do not add hidden filters.

### 20.3 Latest approximate query

```sql
DECLARE @q VECTOR(1536) = CAST(N'[0.1,0.2,...]' AS VECTOR(1536));
DECLARE @p0 nvarchar(100) = N'Technical';

SELECT TOP (20) WITH APPROXIMATE
       t.[chunk_id],
       t.[chunk_label],
       s.[distance]
FROM VECTOR_SEARCH(
       TABLE = [dbo].[DocumentChunks] AS t,
       COLUMN = [embedding],
       SIMILAR_TO = @q,
       METRIC = 'cosine'
     ) AS s
WHERE t.[category] = @p0
ORDER BY s.[distance] ASC;
```

`ORDER BY` for the inner approximate query contains distance only, as required. If the display needs a secondary sort, wrap the approximate query in an outer query after the top-K set is materialized.

### 20.4 Forced ANN query

```sql
DECLARE @q VECTOR(1536) = CAST(N'[0.1,0.2,...]' AS VECTOR(1536));

SELECT TOP (20) WITH APPROXIMATE
       t.[chunk_id],
       t.[chunk_label],
       s.[distance]
FROM VECTOR_SEARCH(
       TABLE = [dbo].[DocumentChunks] AS t,
       COLUMN = [embedding],
       SIMILAR_TO = @q,
       METRIC = 'cosine'
     ) AS s WITH (FORCE_ANN_ONLY)
ORDER BY s.[distance] ASC;
```

Run only when:

- latest approximate syntax is available;
- a compatible vector index is visible;
- the user selected the variant;
- permissions allow execution.

A successful command confirms that an ANN-only strategy was accepted. A failure is categorized and shown; it is not silently replaced by another query.

### 20.5 Legacy approximate query

For earlier index versions only:

```sql
DECLARE @q VECTOR(1536) = CAST(N'[0.1,0.2,...]' AS VECTOR(1536));

SELECT TOP (20)
       t.[chunk_id],
       t.[chunk_label],
       s.[distance]
FROM VECTOR_SEARCH(
       TABLE = [dbo].[DocumentChunks] AS t,
       COLUMN = [embedding],
       SIMILAR_TO = @q,
       METRIC = 'cosine',
       TOP_N = 20
     ) AS s
ORDER BY s.[distance] ASC;
```

Do not use deprecated `TOP_N` for version 3 indexes. Runtime binding/index evidence decides the template.

### 20.6 Structured predicate serialization

```ts
export type VectorStructuredPredicate =
    | { readonly columnId: number; readonly op: "eq" | "ne" | "lt" | "le" | "gt" | "ge"; readonly value: unknown }
    | { readonly columnId: number; readonly op: "in"; readonly values: readonly unknown[] }
    | { readonly columnId: number; readonly op: "isNull" | "notNull" };
```

- AND only in MVP.
- Resolve `columnId` against the verified binding/catalog.
- Permit scalar SQL types from an allowlist.
- Cap `IN` length and total generated SQL bytes.
- Reject vector, XML, image, text, CLR UDT, or unsupported large-value predicate types.
- Produce declarations and predicate fragments separately, then compose.
- Include unit tests for every allowed type, quoting edge, Unicode, dates, decimals, null, and injection strings.

### 20.7 Timing and repetition

Report separately:

- client wall time from command submit to terminal;
- time to first row when available;
- actual plan runtime metrics when safely parsed;
- result-row count;
- messages and warnings by safe category.

Repetitions:

- execute variants in rotating order when more than one measured repetition is selected, to reduce order bias;
- warmup count is explicit and excluded from summary;
- default one run;
- never claim benchmark-grade performance from one interactive run;
- no statistics IO/time parsing from localized message text in MVP.

## 21. Exact versus approximate comparison

### 21.1 Key canonicalization

Represent each returned table key as a typed tuple:

```ts
export interface VectorSearchKey {
    readonly values: readonly VectorScalarKeyValue[];
    readonly canonical: string;
}
```

Canonical form includes type tags and unambiguous separators. Do not use display label as identity.

### 21.2 Metrics

For exact set `E` and approximate set `A`:

```text
overlap          |E intersect A|
recall@K         overlap / min(K, |E|)
approx precision overlap / |A|, when |A| > 0
exact-only       E minus A
approx-only      A minus E
rank delta       approxRank - exactRank for matched keys
```

Show counts with percentages. If duplicate keys invalidate set semantics, disable the metric and explain the binding problem.

### 21.3 Tie handling

- Detect exact-distance values within a host-configured absolute/relative tolerance near each other.
- Mark rank delta as tie-sensitive when either rank lies in a tie group.
- MVP recall remains key-set based.
- A future tie-aware recall mode can retrieve all rows at the Kth boundary.

### 21.4 Result contract

```ts
export interface VectorSearchComparisonResult {
    readonly binding: VectorBindingSummary;
    readonly queryVectorSummary: VectorQueryVectorSummary;
    readonly metric: VectorDistanceMetric;
    readonly k: number;
    readonly exact?: VectorSearchVariantResult;
    readonly approximate?: VectorSearchVariantResult;
    readonly forcedAnn?: VectorSearchVariantResult;
    readonly comparison?: {
        readonly overlap: number;
        readonly denominator: number;
        readonly recall: number;
        readonly exactOnly: readonly string[];
        readonly approximateOnly: readonly string[];
        readonly rows: readonly VectorRankComparisonRow[];
    };
    readonly evidence: VectorExecutionEvidence;
    readonly generatedSql: readonly VectorGeneratedSqlVariant[];
    readonly partial: boolean;
    readonly partialReason?: string;
}
```

Generated SQL is local result data. It is returned to the requesting panel and not persisted in production diagnostics.

## 22. Execution-plan evidence

### 22.1 Plan collection

Reuse the existing `SET STATISTICS XML ON/OFF` discipline or factor a shared plan-wrapper utility. Restoration occurs in `finally` even after cancellation or failure.

The diagnostic runner captures plan result sets separately from search rows and does not append them to the user's main RowStore.

### 22.2 Evidence classification

```ts
export type VectorExecutionEvidence =
    | { readonly kind: "forcedAnnConfirmed"; readonly indexName?: string }
    | { readonly kind: "planConfirmedAnn"; readonly indexName?: string; readonly parserVersion: number }
    | { readonly kind: "exactFallback"; readonly reason: string }
    | { readonly kind: "approximateRequestedUnverified"; readonly reason: string }
    | { readonly kind: "exact" }
    | { readonly kind: "unavailable"; readonly reason: string };
```

### 22.3 Showplan research gate

Before shipping `planConfirmedAnn`:

1. collect Showplan XML fixtures for exact, approximate optimizer ANN, approximate kNN fallback, and forced ANN across supported targets and index versions;
2. identify stable schema/operator attributes;
3. version the parser;
4. test unknown future operators as unverified, not exact or ANN;
5. keep raw plan XML only in the requesting operation/pane under existing plan limits;
6. never place table names, predicates, or plan XML in telemetry.

Until the parser is approved, only forced-ANN success is a confirmed ANN label.

## 23. Vector index diagnostics

### 23.1 Catalog query

Retrieve from `sys.vector_indexes`, `sys.indexes`, `sys.tables`, `sys.schemas`, and `sys.columns`:

- object/index IDs and names;
- vector column;
- vector index type and distance metric;
- `build_parameters`;
- parsed index version;
- disabled/hypothetical state where applicable;
- row-count prerequisites and table key prerequisites;
- ordinary indexes relevant to selected structured filters.

### 23.2 Health DMV

When permitted, retrieve:

- approximate staleness percent;
- quantized keys used percent;
- last background task time;
- success status;
- duration;
- inserts/deletes processed;
- safe bounded error summary.

Do not persist `last_background_task_error_message` in telemetry. Display it only in the user-requested pane, bounded by existing cell/error limits.

### 23.3 Diagnostic rules

Rules are evidence-based and nonautomatic:

| Condition | Finding |
| --- | --- |
| No index on bound vector column | `No vector index found`; offer generated create script. |
| Index metric differs from selected metric | `Metric mismatch`; ANN cannot use this index for the selected metric. |
| Parsed version below 3 | `Earlier vector index format`; offer migration script. |
| Latest version | Show iterative filtering and DML capability according to runtime docs/probes. |
| Background task failed | High-severity maintenance finding. |
| Staleness above user-configured review level | `Review sustained staleness`; never unconditional rebuild. |
| Key-space usage near documented capacity | Review finding with exact DMV value and documentation link. |
| Missing clustered primary key | Explain create-index prerequisite. |
| Fewer than 100 non-null rows | Explain create-index prerequisite. |
| Common structured filter has no supporting ordinary index | Review suggestion, not a guaranteed recommendation. |

### 23.4 Generated scripts

All scripts open in a new editor:

- create vector index;
- drop/recreate migration to latest format;
- health query;
- index-version verification;
- forced-ANN test;
- ordinary-index review query.

Scripts include comments about service impact and preview/version assumptions. They do not execute from the pane.

## 24. Pipeline and external model operations

### 24.1 External model metadata

Use `sys.external_models` and catalog-visible fields to populate a binding-safe model summary. Expose:

- model object name;
- model type;
- API format;
- endpoint location/host or local runtime indicator;
- parameters that are safe and relevant;
- permission limitations.

Never retrieve or display secrets.

### 24.2 Confirmation token

A model operation requires a short-lived host-minted confirmation token tied to:

- panel/controller;
- operation digest;
- model binding;
- row/call count;
- source-text byte count bucket;
- expiration.

Flow:

1. webview asks for a confirmation summary;
2. host resolves binding and computes safe details;
3. webview displays the confirmation;
4. user confirms;
5. webview returns the token;
6. host verifies digest and expiration, then executes.

This prevents a stale or modified request from reusing confirmation for a broader call.

### 24.3 Single-row re-embed SQL

Illustrative:

```sql
DECLARE @source nvarchar(max) = @validated_source_literal;
SELECT AI_GENERATE_EMBEDDINGS(
           @source USE MODEL [dbo].[TextEmbedding3Small]
           PARAMETERS @validated_parameters_json
       ) AS [generated_embedding];
```

Because STS2 execute does not yet expose a general parameter-binding contract, the SQL builder must emit a bounded escaped Unicode literal or add a narrow parameterized execution foundation before this feature. A general parameter protocol is preferable long term, but is not silently invented inside the webview.

### 24.4 Model parameter JSON

- Parse as JSON object.
- Apply byte limit and depth limit.
- Permit only properties allowed by the runtime/model policy.
- Surface `retry_count` clearly.
- Store no parameters after panel disposal unless they are part of a saved provenance profile and contain no secret.

### 24.5 Re-embed comparison

After the model returns a vector:

- validate dimensions and finite values;
- compare locally to the stored vector;
- optionally run exact nearest-neighbor searches for stored and generated vectors;
- report overlap, rank movement, and distances;
- never update the table automatically.

### 24.6 Chunk preview

Generate chunk SQL only from a selected bound source text:

```sql
SELECT c.[chunk],
       c.[chunk_order],
       c.[chunk_offset],
       c.[chunk_length],
       c.[chunk_set_id]
FROM AI_GENERATE_CHUNKS(
       SOURCE = @source,
       CHUNK_TYPE = FIXED,
       CHUNK_SIZE = 800,
       OVERLAP = 15,
       ENABLE_CHUNK_SET_ID = 1
     ) AS c
ORDER BY c.[chunk_order];
```

Rules:

- chunk size is characters, not tokens;
- overlap is whole-number percent 0 through 50;
- source byte/character limits apply;
- chunk text remains result data;
- embeddings for chunks require a second explicit model confirmation;
- do not automatically multiply model calls when a slider changes.

### 24.7 Drift sample

A drift operation is explicitly expensive.

- bounded row sample and call cap;
- source text total-byte cap;
- explicit estimated call count;
- sequential or low-concurrency execution according to server guidance;
- cancellation between calls;
- preserve successful comparisons and failure count;
- no automatic retries beyond configured `retry_count`;
- group/time summaries are observations over the sample;
- never claim a model-version transition without provenance evidence.

## 25. Webview integration

### 25.1 Module placement

```text
extensions/mssql/src/webviews/pages/QueryStudio/vector/
  VectorWorkbenchPane.tsx
  VectorWorkbenchHeader.tsx
  VectorWorkspaceNav.tsx
  VectorProfileView.tsx
  VectorSearchView.tsx
  VectorCompareView.tsx
  VectorProjectionView.tsx
  VectorIndexView.tsx
  VectorPipelineView.tsx
  VectorBindingWizard.tsx
  VectorOperationStatus.tsx
  VectorGeneratedSqlDrawer.tsx
  VectorAccessiblePointList.tsx
  vectorCanvas.ts
  vectorSelection.ts
  vectorViewTypes.ts
```

`QueryStudio/app.tsx` owns only:

- eligibility;
- active sibling tab;
- chosen result/column at a high level;
- lazy import boundary;
- pane visibility and cancellation command;
- integration with splitter/maximize behavior.

Do not put worker messaging, search SQL, WKB-style base64 decode loops, PCA, or Canvas drawing directly in `app.tsx`.

### 25.2 Lazy loading

On first Vector activation:

- dynamically import Vector pane JS;
- load no heavy module before activation;
- do not create a Canvas, analysis session, worker, or database session until required;
- verify production metafile and packaged VSIX behavior;
- confirm lazy CSS is not merged into a large eager stylesheet without review.

The typed vector canonicalization in STS2 occurs during opted-in forward ingestion. The unopened guarantee applies to secondary host scans and UI/compute load, not ingestion.

### 25.3 Rendering dependencies

- Recharts for bounded histograms, bar charts, rank flow, and small heatmap/table companions if it meets accessibility needs.
- Custom Canvas 2D for up to the supported PCA point cap.
- Fluent UI controls and VS Code theme tokens.
- `react-virtual` for point/finding/result lists.
- No TensorFlow projector embedding, external iframe, CDN, or remote assets.
- No UMAP/t-SNE dependency in MVP.

### 25.4 Canvas adapter

The Canvas adapter receives only projection points and style metadata.

Requirements:

- device-pixel-ratio scaling;
- bounded hit-test index;
- pan/zoom/fit;
- click and lasso;
- no per-frame allocation proportional to all points;
- no animation required;
- dispose event listeners and buffers on hidden/disposal;
- high-contrast fallback styles;
- list-driven focus/selection;
- no raw vector data.

For 5,000 points, a simple screen-space bucket index is sufficient. A quadtree dependency is unnecessary unless measurement proves otherwise.

### 25.5 Result-grid integration

Add an async grid registry seam such as:

```ts
interface QueryStudioGridHandle {
    revealResultRow(resultSetId: string, resultRowOrdinal: number, columnOrdinal?: number): Promise<
        | { status: "revealed"; displayRow: number }
        | { status: "filteredOut" }
        | { status: "unavailable" }
    >;
}
```

The mapping stays in the webview because local sort/filter state lives there.

### 25.6 Query-result context

Add a distinct context variant:

```ts
export type QueryResultSelectionContext =
    | { readonly kind: "gridCell"; readonly resultSetId: string; readonly displayRow: number; readonly column: number }
    | { readonly kind: "vectorResultRow"; readonly resultSetId: string; readonly resultRowOrdinal: number; readonly vectorColumn: number }
    | { readonly kind: "vectorTableKey"; readonly bindingId: string; readonly keySummary: string };
```

Do not reuse grid display coordinates before reveal succeeds.

## 26. Lifecycle and cancellation

### 26.1 Result lifetime

- Each analysis session captures the internal store `runId` and frozen result summary.
- A rerun invalidates active sessions even if result-set IDs repeat.
- The session lease keeps the old store alive only until cancellation/terminal cleanup.
- Pinned sessions retain the snapshot-owned store through the pinned controller.

### 26.2 Panel visibility

- Switching away from the Vector sibling tab cancels active scans and heavy computations by default.
- Completed bounded derived results may remain panel-local while the panel stays visible, subject to a memory cap.
- Whole-panel hide triggers host-side cancellation and releases auxiliary SQL sessions.
- Split panels that remain visible but inactive are not treated as hidden.
- Panel disposal always terminates workers, SQL sessions, store leases, and Canvas resources.

### 26.3 Operation terminal behavior

Every terminal path is idempotent:

- success;
- user cancel;
- decoder/numeric budget;
- host scan budget;
- SQL error;
- connection loss;
- panel hide;
- rerun;
- binding change;
- expiry;
- worker crash;
- controller disposal.

On final `done: true`, remove the operation record and release its lease immediately. Do not wait for TTL cleanup.

### 26.4 Expiry and caps

Initial caps:

- one heavy local analysis per panel;
- one database diagnostic operation per panel;
- two heavy local workers globally;
- two auxiliary vector SQL sessions globally;
- small bounded handle count per controller;
- operation idle expiry, for example 60 seconds while awaiting pull;
- maximum wall duration according to operation type.

Values live in the registry and are tuned by evidence.

## 27. Initial budgets

These are seed values for implementation and measurement, not eternal product constants.

### 27.1 Result scan and sample

| Budget | Initial value | Owner |
| --- | ---: | --- |
| Rows scanned for default detached operation | 25,000 | Extension host |
| Accepted sample rows | 5,000 | Extension host |
| Accepted vector components | 8,000,000 | Extension host |
| Packed vector input bytes | 64 MiB | Extension host |
| Sparse window rows | 500 to 1,000 | Extension host |
| Label bytes per row | 4 KiB | Extension host |
| Key/display metadata bytes total | 8 MiB | Extension host |

Effective sample rows are the minimum implied by every limit.

### 27.2 Worker

| Budget | Initial value |
| --- | ---: |
| Profile interactive wall target | 5 seconds |
| Projection wall target | 10 seconds |
| Explicit full profile maximum | 30 seconds |
| Pair samples | 10,000 |
| Pairwise selected vectors soft/hard | 100 / 200 |
| Duplicate groups returned | 100 |
| Outlier rows returned | 200 |
| Component summaries returned | 50 high + 50 low maximum |

Time target and hard timeout are distinct. The UI can remain responsive beyond the target if progress continues, but the hard budget stops the worker.

### 27.3 Derived RPC

| Budget | Initial value |
| --- | ---: |
| Target response body | 1 MiB UTF-8 |
| Hard response body | 2 MiB UTF-8 |
| Total derived output per operation | 32 MiB |
| Projection point chunk | 500 to 1,000 points |
| Progress message rate | <= 4 per second |

Measure `Buffer.byteLength(JSON.stringify(response), "utf8")` before return. Leave conservative room for the outer RPC envelope.

### 27.4 Database operations

| Budget | Initial value |
| --- | ---: |
| Search K default/max | 20 / 1,000 |
| Search variants per run | 3 |
| Measured repetitions default/max | 1 / 10 |
| Structured predicates | 20 |
| `IN` values per predicate | 100 |
| Generated SQL bytes | 2 MiB |
| Single model source text | Existing cell limit or lower operation cap |
| Drift sample model calls | 100 default, host-configurable hard cap |
| Chunk preview returned chunks | 1,000 |

## 28. Security and privacy

### 28.1 Result-data boundaries

The following never enter production diagnostics or telemetry:

- base64 vector bytes or decoded components;
- vector JSON;
- labels, keys, source text, filter values, model parameters;
- generated SQL containing data literals;
- distances, norms, hashes, projection coordinates;
- selected rows;
- table, model, database, or server names when combined with result context;
- plan XML or server messages containing object/text details.

### 28.2 Capture canaries

Use unique component sequences and labels that must be absent from:

- STS2 journals;
- replay bundles;
- diagnostic exports;
- extension logs;
- failure bundles;
- perf markers;
- webview performance marks.

Cover compact/noncompact, success/failure, typed vector, text fallback, truncated neighbors, model operations, and generated SQL.

### 28.3 CSP

Recommended per-surface policy:

```text
default-src 'none';
script-src ${webview.cspSource};
style-src ${webview.cspSource};
img-src ${webview.cspSource} data:;
font-src ${webview.cspSource};
connect-src 'none';
```

Exact nonce/source details follow the Query Studio bundling implementation. No remote `connect-src`, `img-src`, worker host, or iframe source is added.

### 28.4 Model-call egress

- Confirmation displays model, API format, endpoint host/local runtime, rows/calls, source fields, character/byte count, and execution path.
- Credentials remain in database scoped credentials or host credential providers.
- The extension never receives a model API secret.
- The webview never calls the endpoint.
- Confirmation tokens are short-lived and operation-bound.
- Batch calls have higher-friction confirmation and an explicit cancel control.

### 28.5 SQL injection defense

The automated runner accepts structured values and binding IDs, not raw SQL.

Required tests:

- closing brackets in identifiers;
- quotes, semicolons, comments, Unicode escapes, and null characters in values;
- decimals and exponent notation;
- date/time offset formats;
- GUIDs;
- very long strings;
- invalid JSON and nested arrays;
- model parameters with dangerous-looking strings;
- unexpected catalog changes between confirmation and execution.

Revalidate binding immediately before execution.

## 29. Accessibility implementation

- Complete tab/panel ARIA relationships for the new sibling tab.
- Workspace navigation with roving focus.
- F6 focus-region integration.
- Virtualized finding, row, search-result, and projection-point lists retain logical focus.
- Correct `aria-setsize`/`aria-posinset` or paged table semantics.
- Canvas has an accessible description but not thousands of child nodes.
- Every chart has a text summary and accessible table.
- Live region announces operation start, meaningful progress milestones, completion, partial reason, and selection. It does not announce every chunk.
- High contrast and forced-colors styles avoid color-only encoding.
- Reduced motion disables camera animation.
- 200% zoom and narrow results heights are tested.
- Generated SQL uses an accessible read-only code region and can open in Monaco.

Consider a test-only `@axe-core/playwright` dependency after repository review, plus manual screen-reader verification.

## 30. Observability and perftest

### 30.1 Registry-first markers

Names are provisional and must be registered before emission. Each name has one process/role.

| Marker | Role | Safe attributes |
| --- | --- | --- |
| `mssql.queryResults.vector.ingest` | STS2/runtime aggregate | vector-cell count bucket, component-byte bucket, typed/fallback enum, duration bucket |
| `mssql.queryResults.vector.analysis.begin` | Extension host | operation kind, source mode, sample/full enum |
| `mssql.queryResults.vector.analysis.end` | Extension host | row/component/output buckets, terminal enum, duration bucket |
| `mssql.queryResults.vector.analysis.cancel` | Extension host | reason enum, stage enum |
| `mssql.queryResults.vector.worker.end` | Extension worker summary through host | operation kind, input-size buckets, convergence enum, duration bucket |
| `mssql.queryResults.vector.render.begin` | Webview | workspace and renderer kind |
| `mssql.queryResults.vector.render.firstPaint` | Webview | point/count bucket, partial boolean, duration bucket |
| `mssql.queryResults.vector.search.end` | Extension host | variants enum, K bucket, evidence enum, duration bucket |
| `mssql.queryResults.vector.model.end` | Extension host | operation enum, call-count bucket, terminal enum, duration bucket |

Do not include exact dimensions if policy treats them as fingerprinting data; use buckets. Never include names, values, coordinates, keys, text, query digests tied to data, or endpoint hosts.

### 30.2 Test-only probe

Under `PERF_MODE`, expose exact in-memory assertions unavailable in production:

- typed vector cells ingested;
- raw and encoded bytes;
- secondary window reads by reason;
- spill reads/materializations;
- sample windows and rows;
- components accepted/rejected;
- worker iterations and convergence;
- projection points committed;
- active leases, sessions, workers, and Canvas instances;
- no-network assertion state;
- stale-generation rejection;
- exact first-paint event.

The probe never feeds diagnostics or telemetry.

### 30.3 First-paint definitions

- Profile first paint: summary skeleton replaced by at least one complete factual card or distribution summary from the active generation.
- Projection first paint: at least one accepted point committed and the Canvas draw completed for the active generation.
- Search first meaningful result: one variant has terminal result rows or a terminal error, not component mount.

### 30.4 Deterministic fixtures

SQL fixtures:

- 10,000 float32 vectors, 64 dimensions, deterministic generated components.
- 100,000 float32 vectors for sampling/spill scenarios.
- 1,536-dimension embeddings at 5,000 and 25,000 rows.
- maximum 1,998 dimensions.
- null, all-null, exact zero, near-zero, duplicates, non-finite if supported, and dimension-error fixtures.
- multiple vector result sets and columns.
- float16 table and fallback result.
- table with compatible cosine index, metric-mismatched index, legacy index, version 3 index, and no index.
- index maintenance/permission variants where environment permits.
- external model tests through a fake/local approved endpoint only in secure integration environments.

### 30.5 Perftest scenarios

| Scenario | End condition | Independent proofs |
| --- | --- | --- |
| `querystudio-vector-unopened-f32` | ordinary Results first paint | typed ingestion occurred; zero vectorAnalysis reads; no worker or Vector chunk loaded |
| `querystudio-vector-profile-5k-1536` | Profile result committed | expected sample/components, no viewport cache promotion, worker terminal |
| `querystudio-vector-pca-5k-1536` | Canvas first draw | expected point count, deterministic digest, convergence status |
| `querystudio-vector-budget` | honest partial terminal | host/worker partial reasons agree with visible state |
| `querystudio-vector-rerun-cancel` | new-run Profile first paint | old lease/session/worker released; no stale point |
| `querystudio-vector-search-compare` | comparison result | exact/approx key sets and evidence probe match fixture |
| `querystudio-vector-pinned` | pinned Projection first paint | live editor can close while snapshot remains valid |
| `querystudio-vector-reveal` | selected grid cell focused | result ordinal mapped through current sort/filter semantics |

Do not use sleeps. Use registered markers and semantic probes.

## 31. Test plan

### 31.1 `sqltoolsservice` unit tests

- native `SqlVector<float>` exact recognition;
- typed null and normal null;
- component-byte little-endian fixtures;
- dimensions 1, common embedding sizes, and 1,998;
- byteLength and base64 round trip;
- unavailable sentinel;
- exclusion of arbitrary provider objects and JSON strings;
- float16 fallback matrix;
- compact and noncompact wire equivalence;
- type hint;
- execute capability/option negotiation and downgrade;
- conservative/exact page size behavior;
- final UTF-8 frame guard and typed row-too-large outcome;
- cancellation and provider exceptions;
- no partial vector payload.

### 31.2 `sqltoolsservice` integration matrix

Across supported RIDs and targets:

- direct table column;
- expression/variable/procedure result;
- null/all-null;
- multiple result sets;
- max dimensions and large pages;
- old client option omitted;
- feature option enabled;
- float16 with preview configuration;
- cancel mid-result;
- replay/journal capture canaries.

### 31.3 Shared codec tests

For success, unavailable, malformed, and unknown-version tags:

- strict guard behavior;
- generic typed wrapper does not match vector tag;
- compact/noncompact normalization equivalence;
- prefix/full decode;
- base64 mismatch rejection;
- grid preview;
- copy;
- cell document;
- text;
- CSV;
- JSON;
- INSERT;
- tool summary;
- spill/restore;
- pinned snapshot;
- absence of base64/raw tag/`[object Object]` in ordinary surfaces.

### 31.4 Sparse projection tests

- adjacent and distant ordinals;
- reversed order;
- duplicates;
- invalid/empty projection;
- null bitmap and type hints;
- in-memory and spilled pages;
- one materialization per page;
- retained store;
- frozen snapshot clamp;
- derived snapshot row mapping;
- cache key separation.

### 31.5 Analysis algorithms

Reference fixtures generated by NumPy or another approved implementation:

- norms and all distance metrics;
- zero-norm cosine;
- Welford component statistics;
- duplicates and signed zero;
- centroid/outliers;
- deterministic pair sampling;
- pairwise matrix;
- arithmetic parser and operations;
- PCA scores up to deterministic sign and tolerance;
- explained variance;
- convergence/no-convergence;
- cancellation between matrix passes;
- non-finite rejection;
- memory/component/time budgets.

### 31.6 Session lifecycle tests

Assert store lease, worker, auxiliary session, and buffer cleanup for:

- normal final chunk;
- user cancel;
- tab switch;
- panel hidden;
- split panel inactive but visible;
- result/column change;
- rerun before scan;
- rerun during worker computation;
- rerun during SQL command;
- panel disposal;
- expiry;
- duplicate cancel;
- stale generation;
- wrong sequence;
- concurrent `next`;
- worker crash;
- store short read/corruption;
- SQL connection loss;
- final response not pulled by webview.

The manager must have a bounded terminal cleanup timer for the last case.

### 31.7 SQL builder tests

- exact/latest/legacy/forced templates;
- version selection;
- metric mapping and label `dot` as negative dot product;
- schema/table/column quoting;
- composite keys;
- every structured predicate type;
- dangerous strings;
- Unicode;
- vector literal formatting and byte cap;
- model object quoting;
- chunk size/overlap validation;
- generated SQL displayed equals executed SQL;
- no hidden predicate or DDL.

### 31.8 Search comparison tests

- exact and approximate identical;
- one and many misses;
- fewer than K exact rows;
- duplicate-key binding rejection;
- tie-sensitive ranks;
- no index fallback;
- metric mismatch;
- forced ANN success/failure;
- latest and legacy index versions;
- partial/canceled variant;
- actual plan unavailable;
- approved plan parser and unknown plan operator.

### 31.9 Webview/component tests

- eligibility and deterministic defaults;
- no auto-open;
- workspace responsive layouts;
- Profile finding filters;
- Search composer validation;
- model confirmation token flow;
- generated SQL drawer;
- Compare basket and arithmetic errors;
- Projection pan/zoom/fit/lasso/select;
- synchronized point list;
- color/group caps;
- grid reveal and filtered-out flow;
- pinned limitations;
- terminal partial states;
- theme changes;
- localization keys;
- no network requests;
- lazy chunk not loaded unopened;
- renderer fallback.

### 31.10 Accessibility end-to-end

- tab and workspace keyboard navigation;
- F6 sequence;
- screen-reader Profile and Search workflow;
- point-list selection and reveal;
- focus restoration from drawers/dialogs;
- live announcements;
- 200% zoom;
- narrow pane;
- forced colors;
- light/dark/high-contrast/high-contrast-light;
- reduced motion;
- automated scanner plus manual verification.

### 31.11 Privacy tests

Unique vector/text/key canaries must not occur in:

- journals;
- replay bundles;
- diagnostics exports;
- extension logs;
- production markers;
- webview perf marks;
- CSP/network logs;
- worker error messages;
- stale operation records after disposal.

## 32. Dependency-ordered pull-request plan

### PR 1 - Compact capture privacy fix

**Repository:** `sqltoolsservice`  
**Visible feature:** none

- Elide the complete compact object.
- Add capture canaries and cleanup tests.
- Preserve digest/replay identity.

**Exit:** no compact value or null pattern persists.

### PR 2 - Shared vector cell codec and ordinary consumer safety

**Repository:** `vscode-mssql`  
**Visible feature:** none

- Add vector tag interfaces and strict guards.
- Add purpose-specific formatting.
- Cover grid, copy, text, cell document, export, transforms, tools, spill, and pins with synthetic cells.
- Ensure tag uses `data`, not `v`.

**Exit:** synthetic vector values are safe in every ordinary consumer.

### PR 3 - STS2 native float32 vector contract

**Repository:** `sqltoolsservice`

- Provider/RID matrix.
- `DriverVectorValue`.
- float32 little-endian encoding.
- wire tag and unavailable sentinel.
- capability plus per-execute opt-in.
- type hint.
- page estimate/exact pack work and final frame guard.
- compact/noncompact and downgrade tests.

**Exit:** native float32 round-trips losslessly and safely.

### PR 4 - SQL Data Plane and Query Studio metadata plumbing

**Repository:** `vscode-mssql`

- capability/execute-option negotiation;
- backend-neutral vector metadata/tag normalization;
- QsResultColumn vector marker;
- RowStore/spill/snapshot round trip;
- float16 text-fallback metadata behavior;
- old service/client downgrade tests.

**Exit:** opted-in results are typed and all ordinary UI remains correct.

### PR 5 - General sparse projection

**Repository:** `vscode-mssql`

- `columnOrdinals` across all store/read paths;
- cache keys and derived snapshots;
- materialization/performance tests.

**Exit:** vector plus distant metadata columns require one page materialization.

### PR 6 - Vector result analysis service and worker foundation

**Repository:** `vscode-mssql`

- `vectorAnalysis` reason and `vectorWorkbench` lease owner;
- controller-bound live source;
- open/next/cancel sessions;
- sample planner;
- worker entry and lifecycle;
- profile algorithms;
- derived pull protocol;
- test-only probe.

**Exit:** a non-UI test client can profile a retained result with bounded reads and no leaks.

### PR 7 - Profile and Compare UI vertical slice

**Repository:** `vscode-mssql`

- feature gate and conditional Vector tab;
- lazy pane shell;
- Profile cards/charts/findings/list;
- single-cell inspect and Compare basket;
- accessibility and localization;
- Query Studio CSP;
- unopened-cost tests.

**Exit:** typed results have a useful offline debugger before PCA or database calls.

### PR 8 - PCA Projection

**Repository:** `vscode-mssql`

- deterministic PCA algorithm and fixtures;
- projection point streaming;
- Canvas renderer;
- accessible point list;
- lasso, selection, reveal seam;
- responsive and performance tests.

**Exit:** bounded 2D PCA is deterministic, accessible, and responsive.

### PR 9 - Table binding, catalog, and auxiliary session

**Repository:** `vscode-mssql`

- binding wizard/service/store;
- catalog signature and verification;
- capability service;
- auxiliary SQL session lease;
- model metadata summary;
- no Search execution yet.

**Exit:** a binding can be created, saved locally, reverified, and invalidated safely.

### PR 10 - Search Debugger and Index workspace

**Repository:** `vscode-mssql`

- SQL builder;
- exact/latest/legacy/forced variants;
- actual plan capture;
- key comparison/recall/rank metrics;
- evidence labels;
- Index catalog/DMV diagnostics;
- generated scripts;
- no automatic DDL.

**Exit:** exact versus approximate comparison is truthful and reproducible.

### PR 11 - Pipeline workspace

**Repository:** `vscode-mssql`

- confirmation token flow;
- single-row embedding;
- re-embed comparison;
- chunk preview;
- bounded drift sample behind an additional gate if needed;
- egress/security tests.

**Exit:** no model call occurs without informed confirmation and no result is written back.

### PR 12 - Pinned parity, context, and release hardening

**Repositories:** `vscode-mssql`, applicable perftest repository, and `sqltoolsservice` fixes found by soak

- pinned source adapter and CSP;
- result-row context/reveal completion;
- deterministic fixtures and registered markers;
- performance tuning;
- privacy canaries;
- preview documentation and rollback.

**Exit:** preview definition of done is met.

## 33. Expected code change map

| Repository area | Responsibility |
| --- | --- |
| `sqltoolsservice/src/sts2/.../CaptureElision.cs` | Complete compact capture elision. |
| `sqltoolsservice/src/sts2/...Drivers.SqlClient/**` | Native vector classification and float32 extraction. |
| `sqltoolsservice/src/sts2/...Runtime/Effects/WireValueEncoder.cs` | Versioned vector tag, unavailable sentinel, exact/conservative size. |
| STS2 contracts/reducer/public API/docs/tests | Capability and execute option, replay identity, compatibility. |
| `vscode-mssql/extensions/mssql/src/sharedInterfaces/queryResultCellCodec.ts` | Strict tag and purpose-specific formatting. |
| `services/sqlDataPlane/api.ts` and backend bindings | Vector metadata and normalized cell union. |
| `queryStudio/rowStore.ts` and `queryResults/queryResultTypes.ts` | New reason/owner and sparse projection. |
| `queryResults/vector/**` | Analysis sessions, worker, catalog, binding, SQL runner. |
| Query Studio and pinned controllers | Controller-owned source and auxiliary-session authority. |
| `webviews/pages/QueryStudio/vector/**` | Full workbench UI. |
| `bundle-extension.js`, webview bundling, CSP base | Worker entry, lazy chunks, CSP. |
| observability contracts/perftest | markers, fixtures, exact probes, scenarios. |

## 34. Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Provider metadata differs by RID or expression shape | Missing or wrongly typed Vector tab | Live provider matrix; cell identity plus metadata; safe downgrade. |
| Compact vector values enter journals | Severe data disclosure | P0 complete compact elision and canaries. |
| Generic wrapper displays base64 | Cross-feature regression and disclosure | `data` field, strict codec, ordinary-consumer matrix before opt-in. |
| High-dimensional pages exceed intended byte target | Memory/RPC regression | vector-aware estimate, exact page packing, final frame guard. |
| Float16 is treated as equivalent to float32 native transport | False precision and broken decode | explicit text-fallback state and table-bound promotion label. |
| Secondary analysis evicts grid viewport | Scrolling regression | `vectorAnalysis` no-readmission reason and sparse reads. |
| Worker duplicates large matrices | Extension-host memory spike | transfer ArrayBuffer, release host reference, dynamic sample cap. |
| PCA produces unstable or misleading layouts | User distrust | deterministic seed, algorithm version, explained variance, original-space caveat, reference fixtures. |
| Search uses wrong syntax for index version | Query failure or fallback | verified index version and runtime capability service. |
| Approximate syntax is labeled ANN without proof | Misleading diagnosis | forced-ANN/approved-plan evidence taxonomy. |
| Separate diagnostic session misses temp/uncommitted state | Confusing results | explicit binding to base table, isolation disclosure, no silent current-session mode. |
| Structured filter builder expands into a SQL editor | Injection and scope creep | AND-only allowlist; open custom SQL in editor outside automated compare. |
| Model calls leak or surprise users | Privacy/cost incident | confirmation token, endpoint disclosure, call cap, no auto-run. |
| Hidden panel retains lease/worker/session | spill files and process growth | host visibility cleanup, caps, expiry, terminal release tests. |
| Canvas blocks accessibility | Core workflow unavailable | synchronized virtual list and tables. |
| Vector feature becomes a universal analytics framework | Delivery stall | concrete vector-only services and narrow PR stack. |

## 35. Definition of ready for UI implementation

The first Profile UI patch may begin only when:

- [ ] Complete compact capture elision passes canaries.
- [ ] Supported RID/provider behavior is recorded.
- [ ] `vectorBinaryV1` and per-execute opt-in are approved.
- [ ] Vector tag uses `data`, not `v`.
- [ ] Compact and noncompact paths share strict normalization.
- [ ] Every ordinary result consumer has tested vector behavior.
- [ ] Final frame guard exists.
- [ ] Page-byte behavior is exact or honestly advertised.
- [ ] `vectorAnalysis` reason and `vectorWorkbench` lease owner exist.
- [ ] Sparse projection is complete.
- [ ] Controller-bound analysis sessions release leases on every terminal path.
- [ ] Worker algorithm fixtures and cancellation pass.
- [ ] Query Studio CSP loads local lazy chunks and blocks network requests.
- [ ] Feature gate defaults off.

## 36. Definition of done for preview

- [ ] Native float32 vectors round-trip losslessly through STS2, SQL Data Plane, RowStore, spill, snapshots, and pins.
- [ ] Float16 fallback is explicit and never silently treated as native float32.
- [ ] Grid, copy, text, cell document, CSV, JSON, INSERT, transforms, and tools remain safe.
- [ ] Vector tab is conditional and never auto-opens.
- [ ] Profile, Compare, and PCA operate from bounded retained-result reads.
- [ ] PCA is deterministic, labeled, and has an accessible point list.
- [ ] Search compares exact, approximate, and forced ANN with correct versioned syntax.
- [ ] Recall denominators, ties, partial variants, and execution evidence are honest.
- [ ] Index workspace reads catalog/DMV state and generates, but never executes, DDL.
- [ ] Pipeline model calls require confirmed egress disclosure.
- [ ] Rerun, hide, tab change, disposal, expiry, worker crash, and SQL loss clean up all resources.
- [ ] Pinned results use the same workbench contracts.
- [ ] No Vector webview network request occurs.
- [ ] No result value appears in capture, diagnostics, telemetry, or production markers.
- [ ] Existing Query Studio execution, first paint, scrolling, spill, copy, export, and query-plan scenarios show no material unopened regression.
- [ ] Supported/unsupported matrix, preview gate, rollback, privacy, and isolation behavior are documented.

## 37. Instructions and guardrails for an AI coding agent

### 37.1 Required workflow

- Read this document, the UX specification, and both geospatial reference documents before editing.
- Inspect current `dev/query` symbols before relying on path or line numbers.
- Land foundation changes separately from UI.
- Add tests with every contract change.
- Keep feature gate default off until the full vertical slice passes.
- Preserve existing result ownership and credit/backpressure behavior.
- Use controller-bound opaque handles and host budgets.
- Keep every partial count scoped to what was observed.
- Localize strings in the first UI patch.
- Generate SQL through one reviewed builder.
- Treat model calls as explicit data egress.

### 37.2 Prohibited shortcuts

Do not:

- stringify `SqlVector` and call that typed support;
- use generic `$t, v` for binary vector data;
- infer arbitrary JSON arrays as vectors;
- send `SqlVector`, `Float32Array`, or raw base64 to coarse state;
- add a React scan over `qs/getRows`;
- accept store/run/snapshot IDs or budgets from the webview;
- create a second authoritative row cache;
- perform PCA in the React render thread;
- construct a full covariance matrix for 1,998 dimensions;
- silently normalize, sample, or exclude rows;
- label approximate syntax as ANN proof;
- use `TOP_N` against version 3 indexes;
- use `FORCE_ANN_ONLY` without required latest syntax and compatible index;
- parse localized statistics messages as performance truth;
- run diagnostics on the user session in MVP;
- execute DDL from the pane;
- invoke a model without a confirmation token;
- persist model source text, vector values, generated SQL literals, or search keys;
- add UMAP, t-SNE, 3D, GPU rendering, or a large math runtime without evidence;
- broaden CSP to remote hosts;
- retain a lease or worker after final completion;
- call a result-row ordinal a display row before webview mapping succeeds.

### 37.3 Stop conditions

Stop the current feature patch and fix the prerequisite when:

- a vector or null-pattern canary appears in capture or diagnostics;
- provider/RID behavior cannot distinguish a native float32 vector safely;
- a vector tag reaches generic typed-wrapper display;
- any ordinary consumer shows base64, raw tag JSON, or `[object Object]` unintentionally;
- a complete row can exceed the frame ceiling without typed pre-transport failure;
- sparse projection still causes repeated spill materialization;
- a worker or analysis session receives unbounded rows/components;
- a hidden or rerun panel keeps a lease, worker, SQL session, or Canvas alive;
- PCA output is nondeterministic for the same seed and sample;
- an approximate run is labeled ANN without forced or approved plan evidence;
- generated SQL contains a webview-supplied raw identifier or predicate;
- a model call can execute without current confirmation;
- a production marker contains vector data, source text, keys, coordinates, names, or endpoint details.

## 38. Open research gates that do not block the foundation

1. Exact SqlClient metadata for vector dimensions/base type across result shapes and RIDs.
2. Native float16 driver support timeline and future wire contract.
3. Stable Showplan XML signature for ANN versus kNN across index versions.
4. Whether a narrow audited numerical dependency is preferable to the specified internal PCA implementation.
5. Final sample/component/time budgets after real 1,536 and 1,998 dimension traces.
6. Whether Profile can offer a full scan by default for small completed results.
7. Tie-aware recall behavior at the Kth distance boundary.
8. A future parameterized SQL Data Plane execute contract to replace escaped data literals.
9. Whether historical vector-index health belongs in this pane or a broader monitoring surface.
10. Float16 quantization simulation accuracy and whether it ships as a later lab.
11. Hybrid full-text plus vector evaluation, RRF, and reranking scope.
12. UMAP/t-SNE dependency, worker, reproducibility, and accessibility strategy.

These gates must not be used to weaken MVP truthfulness. Unknown behavior remains unavailable or explicitly unverified.

## 39. External references reviewed

### SQL Server and Azure SQL

- [Vector data type](https://learn.microsoft.com/en-us/sql/t-sql/data-types/vector-data-type?view=sql-server-ver17)
- [Vector search and vector indexes](https://learn.microsoft.com/en-us/sql/sql-server/ai/vectors?view=sql-server-ver17)
- [VECTOR_DISTANCE](https://learn.microsoft.com/en-us/sql/t-sql/functions/vector-distance-transact-sql?view=sql-server-ver17)
- [VECTOR_SEARCH](https://learn.microsoft.com/en-us/sql/t-sql/functions/vector-search-transact-sql?view=sql-server-ver17)
- [CREATE VECTOR INDEX](https://learn.microsoft.com/en-us/sql/t-sql/statements/create-vector-index-transact-sql?view=sql-server-ver17)
- [sys.columns vector metadata](https://learn.microsoft.com/en-us/sql/relational-databases/system-catalog-views/sys-columns-transact-sql?view=sql-server-ver17)
- [sys.vector_indexes](https://learn.microsoft.com/en-us/sql/relational-databases/system-catalog-views/sys-vector-indexes-transact-sql?view=sql-server-ver17)
- [sys.dm_db_vector_indexes](https://learn.microsoft.com/en-us/sql/relational-databases/system-dynamic-management-objects/sys-dm-db-vector-indexes-transact-sql?view=sql-server-ver17)
- [VECTOR_NORM](https://learn.microsoft.com/en-us/sql/t-sql/functions/vector-norm-transact-sql?view=sql-server-ver17)
- [VECTOR_NORMALIZE](https://learn.microsoft.com/en-us/sql/t-sql/functions/vector-normalize-transact-sql?view=sql-server-ver17)
- [AI_GENERATE_EMBEDDINGS](https://learn.microsoft.com/en-us/sql/t-sql/functions/ai-generate-embeddings-transact-sql?view=sql-server-ver17)
- [AI_GENERATE_CHUNKS](https://learn.microsoft.com/en-us/sql/t-sql/functions/ai-generate-chunks-transact-sql?view=sql-server-ver17)
- [CREATE EXTERNAL MODEL](https://learn.microsoft.com/en-us/sql/t-sql/statements/create-external-model-transact-sql?view=sql-server-ver17)
- [sys.external_models](https://learn.microsoft.com/en-us/sql/relational-databases/system-catalog-views/sys-external-models-transact-sql?view=sql-server-ver17)

### Current source branches

- [microsoft/sqltoolsservice dev/query](https://github.com/microsoft/sqltoolsservice/tree/dev/query)
- [microsoft/vscode-mssql dev/query](https://github.com/microsoft/vscode-mssql/tree/dev/query)
- [Microsoft.Data.SqlClient SqlVector source](https://github.com/dotnet/SqlClient/blob/main/src/Microsoft.Data.SqlClient/src/Microsoft/Data/SqlTypes/SqlVector.cs)

### Visualization and accessibility references

- [TensorFlow Embedding Projector](https://projector.tensorflow.org/)
- [UMAP parameter guide](https://umap-learn.readthedocs.io/en/latest/parameters.html)
- [scikit-learn t-SNE reference](https://scikit-learn.org/stable/modules/generated/sklearn.manifold.TSNE.html)
- [VS Code webview guide](https://code.visualstudio.com/api/extension-guides/webview)
