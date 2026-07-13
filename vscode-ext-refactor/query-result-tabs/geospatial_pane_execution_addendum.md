# Query Studio Geospatial Results Pane - Execution Addendum and Code Review

**Status:** Attach to the initial design before implementation  
**Date:** 2026-07-10  
**Baseline:** `geospatial_pane.md`, dated 2026-07-09  
**Reviewed branches:** `microsoft/vscode-mssql@dev/query`, `microsoft/sqltoolsservice@dev/query`  
**Primary audience:** Engineers and AI code agents implementing the Query Studio Spatial results feature  
**Code-review scope:** The two requested public `dev/query` repositories were inspected directly. Perftest guidance in this addendum is design-level and was not code-verified against a separate repository.

## 0. Purpose and precedence

The initial design is strong and should remain the primary architecture document. It is unusually careful about data ownership, bounded work, spatial fidelity, privacy, accessibility, offline behavior, and performance. Replacing it wholesale would create churn without improving the core direction.

This addendum does four things:

1. Records code-level findings from the current `dev/query` branches.
2. Corrects a few assumptions that do not match the implementation as it exists today.
3. Locks a smaller, executable MVP so an implementation agent does not accidentally turn the feature into a broad platform rewrite.
4. Gives a dependency-ordered pull request plan, concrete contracts, acceptance tests, and stop conditions.

Where this addendum explicitly says **Amendment**, **Required**, **Do not**, or **MVP decision**, it overrides the corresponding baseline wording. Everything else in the baseline remains in force.

## 1. Verdict

Proceed with the baseline architecture, with the amendments in this document.

The central recommendation remains correct:

- Native SQL Server spatial values should be canonicalized in the STS2 SqlClient driver and transported through the ordinary credited row stream.
- The extension host result store should remain the sole authoritative row store.
- Spatial preparation should be a bounded secondary consumer with a distinct read reason and store lease.
- React should receive bounded feature chunks through an opaque pull session, not scan ordinary row RPCs.
- OpenLayers is the best first renderer candidate for an offline, planar-or-geographic viewer.
- Geography line and polygon fidelity must not be faked with projected straight chords.
- The canvas must have an equivalent feature-list and details workflow.
- Online maps should remain a separate product, security, legal, and privacy milestone.

The plan needs tightening in seven places before an agent starts coding:

1. The proposed `{"$t":"spatial","v":"<base64>"}` shape collides with the grid's existing generic typed-wrapper decoder and would expose base64 WKB as ordinary cell text.
2. Canonical WKB conversion cannot be delayed until the Spatial tab opens. STS2 is forward-only, so spatial ingestion work happens during execution whenever the execute option is enabled.
3. The webview must not supply host budgets, store identifiers, snapshot identifiers, or other lookup authority when opening a spatial session.
4. The existing result APIs support one contiguous column span, not sparse projection. Two one-column reads can deserialize the same spilled page twice.
5. `IQueryResultStore.runId` already provides the authoritative run identity. `startedEpochMs` is a UI lifecycle key, not a data-authority token, and another run identity should not be added to coarse state.
6. Spatial source-row identity must mean the row ordinal in the bound live or pinned result view. It must not be mislabeled as a current grid display row after local sort or filter.
7. Exact transport safety and exact `pageBytes` conformance are related but separable. A final frame guard is a hard safety prerequisite. A complete encode-once page repacker is the preferred protocol fix, but it should not be smuggled into the map UI pull request.

## 2. Required amendments at a glance

| ID | Amendment | Why it matters | Required disposition |
| --- | --- | --- | --- |
| EXE-A1 | Rewrite the unopened-cost invariant | WKB must be produced while the forward-only row stream is being consumed | Promise zero secondary scan/render work before tab activation, not zero spatial ingestion work |
| EXE-A2 | Replace spatial `v` with a dedicated `wkb` field | Current generic wrapper logic treats any non-truncated `{$t, v}` as display text | Add a discriminated spatial guard before enabling service negotiation |
| EXE-A3 | Introduce one shared result-cell codec | Compact and noncompact STS2 paths normalize tagged cells differently, while grid/export/cell-document share formatting behavior | Centralize validation and purpose-specific formatting |
| EXE-A4 | Keep budgets host-authoritative | The webview is not the authority for memory, row, time, or RPC limits | Resolve budgets from the extension-host registry; return effective limits as information only |
| EXE-A5 | Make sparse projection required for labels | Dual reads can repeat spill materialization and double scan traffic | Add general `columnOrdinals`, or omit the label selector from the first slice |
| EXE-A6 | Reuse `store.runId` internally | A second run generation creates identity drift and coarse-state leakage | Return an opaque spatial-session generation only; never expose store IDs as lookup authority |
| EXE-A7 | Release leases on normal completion | Cancel/hide cleanup alone leaves completed sessions holding stores | Delete the host session and release its lease when the final chunk is returned |
| EXE-A8 | Rename `sourceRow` | Pinned and future derived views may not map one-to-one to an original physical source row | Use `resultRowOrdinal`; add `originRowOrdinal` only when explicitly known |
| EXE-A9 | Separate transport status from render policy | A valid WKB value can still be unsupported by the MVP renderer, especially geography lines | Keep STS2 encoding generic; classify renderability in the spatial decoder |
| EXE-A10 | Do not claim topology validity without evidence | Successful WKB parsing is not the same as `STIsValid()` | Report `decodeFailed`, `unsupportedSemantics`, or `validityUnknown`; do not say `invalid` by inference |
| EXE-A11 | Stabilize mixed-SRID behavior incrementally | Later chunks can discover new SRIDs after first paint | Pick one active group deterministically and never silently merge or change it |
| EXE-A12 | Default to incremental main-thread decode | A worker creates a second geometry representation and transfer protocol before evidence requires it | Add a worker only after measured long-task or interaction failures |
| EXE-A13 | Adopt CSP per surface | The shared HTML currently has inline style and no CSP | Add a reusable hook, then migrate Query Studio and pinned results without globally breaking every webview |
| EXE-A14 | Elide the whole compact object | `compact.values` and `compact.nullBitmap` are result data | Wrap and restore the complete compact payload before any spatial bytes are journaled |
| EXE-A15 | Split platform prerequisites from the UI slice | Otherwise the map becomes a many-month umbrella change | Land small, independently testable foundations behind a default-off gate |

## 3. Locked MVP decisions

These decisions turn the baseline into an executable first release. Revisit them only with measured evidence or a product requirement.

### 3.1 Product scope

- The label is **Spatial**. Accessible names and empty states use **Spatial results**.
- The tab appears only for a run that has metadata-confirmed native `geometry` or `geography` columns **and** whose execution negotiated `spatialWkbV1`.
- The tab never auto-opens.
- Completed result sets and terminal partial result sets are supported. Progressive viewing while execution is active is deferred.
- Live Query Studio is the first vertical slice. The service and component boundaries must be pinned-compatible from the start. Pinned parity may land in the immediately following pull request, but the preview must document whether it is present.
- No online tile, style, geocoding, imagery, or provider configuration exists in MVP.
- Do not bundle a world-outline asset in the first vertical slice. Add it later if package-size and product review approve it.
- No spatial export command is added. Existing grid, copy, text, cell-document, CSV, JSON, and INSERT paths must handle the tagged value deliberately and must never expose internal JSON or base64 by accident.

### 3.2 Supported render matrix

| SQL value | MVP transport | MVP rendering |
| --- | --- | --- |
| `geometry` Point, LineString, Polygon | Required | Required in native Cartesian coordinates |
| `geometry` MultiPoint, MultiLineString, MultiPolygon, GeometryCollection | Required | Required for standard linear OGC forms |
| `geometry` SRID 4326 | Required | Straight geometry semantics; optional 4326 view, not geography semantics |
| `geometry` SRID 3857 | Required | Native projected view; tested built-in transform where used |
| Other `geometry` SRIDs | Required when WKB conversion succeeds | Native Cartesian only; no invented transform |
| `geography` Point and MultiPoint | Required | Required, with longitude/latitude tests and antimeridian-aware fit |
| `geography` LineString, Polygon, multis, collections | Transport when canonical conversion is safe | Explicitly unsupported in the first renderer unless Phase 0 proves exact or bounded geodesic rendering |
| Curved SQL spatial types | Research-gated | Unsupported unless conversion and approximation semantics are explicit |
| `FullGlobe` and larger-than-hemisphere cases | Research-gated | Unsupported unless a correct representation is proven |
| Z, M, or ZM | Preserve only what the approved interchange actually preserves | 2D display only; never imply elevation or measure visualization |
| Null | Existing null bitmap | Counted, not rendered |
| Empty geometry | Canonical WKB when supported | Counted as empty, not rendered |
| Oversized or conversion-failed value | Complete spatial sentinel | Counted with an explicit transport reason, never partially parsed |

A valid geography line or polygon is not a rendering error. It is a valid transported value with `unsupportedSemantics` under the MVP renderer policy.

### 3.3 Renderer and decode

- Use OpenLayers Canvas vector rendering.
- Use no tile layer and no default hosted-map controls.
- Use extension-owned DOM toolbar controls so theming, localization, keyboard support, and CSP are predictable.
- Lazy-load the spatial component and exact OpenLayers modules when the user first activates Spatial.
- Parse incrementally on the main thread with cooperative yields.
- Do not add a browser worker in the first implementation unless the Phase 0 benchmark shows unacceptable long tasks under the approved caps.
- Auto-fit once after the first meaningful accepted batch. Do not move the camera when later chunks arrive after user interaction.
- Render only one incompatible `(kind, SRID)` group at a time. Never overlay mixed groups without a proven transform.

### 3.4 Initial preparation budgets

The baseline seed budgets are reasonable. The extension host, not the webview, owns them. Register all values in the existing query-results parameter registry.

Recommended first implementation defaults:

| Budget | Initial value | Authority |
| --- | ---: | --- |
| Rows scanned | 25,000 | Extension host |
| Total spatial-session response payload bytes | 32 MiB | Extension host |
| Per-response soft target | 1 MiB | Extension host |
| Per-response hard maximum | 2 MiB | Extension host |
| Label preview bytes per cell | 4 KiB | Extension host |
| Decoded/render vertices | 250,000 | Webview decoder |
| Derived decode/render memory estimate | 64 MiB | Webview decoder |
| Rows read per store window | 500 to 1,000 | Extension host |
| Main-thread work slice | 8 ms target | Webview scheduler |

Use a conservative per-response payload target well below the JSON-RPC frame ceiling. The controller can measure the serialized response body exactly, but it should not depend on knowing every byte of the outer RPC envelope to remain safe.

## 4. Normative execution amendments

### 4.1 Amend the unopened-cost invariant

The baseline says Spatial should not change query execution when the tab is never opened. That is achievable for nonspatial results, but not for a spatial result once the client has requested canonical WKB.

The SqlClient result reader is forward-only. A provider spatial object cannot be revisited after the row has passed. Therefore, one of these must happen during ingestion:

1. Canonicalize the value to a provider-neutral representation.
2. Retain provider-specific state or native bytes and defer interpretation.
3. Rewrite and rerun the query later.

The baseline correctly rejects provider-specific storage and query rewriting. Canonicalization during ingestion is therefore the intended cost.

Replace the invariant with this wording:

> When the feature gate is disabled, Query Studio does not request spatial encoding and existing execution behavior is unchanged. When the feature gate is enabled and a result contains native spatial columns, STS2 may perform bounded spatial recognition, native-byte reading, and canonicalization during the ordinary forward-only row stream, whether or not the user later opens Spatial. Until the tab opens, the extension performs no secondary result-store scan, WKB browser decode, OpenLayers import, worker creation, map construction, feature-list creation, or GPU/canvas preparation.

Add two separate performance baselines:

- A nonspatial query with the feature gate enabled, proving negligible capability-check overhead.
- A spatial query whose Spatial tab is never opened, measuring the unavoidable STS2 canonicalization cost and proving zero extension-host secondary reads and zero renderer load.

The execute option should be enabled only when all of these are true:

- the Query Studio preview gate is enabled;
- STS2 advertised `spatialWkbV1`;
- the SQL Data Plane binding supports the spatial tagged value and all ordinary-cell consumers are safe.

A run made without this option is not retroactively spatial-viewable. Do not attempt to infer WKT or parse provider fallback strings after execution.

### 4.2 Replace the provisional wire shape and add a shared cell codec

#### 4.2.1 Why the current provisional shape is unsafe

The current grid helper treats any object with a string `$t` and string `v`, except `$t: "truncated"`, as a generic typed scalar wrapper. Its default display is `wrapper.v`. A spatial tag using `v` for base64 WKB would therefore display the base64 payload in the grid, copy, text, cell-document, and export paths.

The spatial payload must not match the generic scalar wrapper shape.

#### 4.2.2 Recommended v1 wire shape

Use a dedicated `wkb` field and an explicit version.

```json
{
  "$t": "spatial",
  "version": 1,
  "status": "ok",
  "kind": "geometry",
  "encoding": "wkb",
  "srid": 0,
  "wkbBytes": 21,
  "wkb": "<base64 OGC WKB>"
}
```

Use a complete sentinel for a value that cannot be transported canonically:

```json
{
  "$t": "spatial",
  "version": 1,
  "status": "unrenderable",
  "kind": "geometry",
  "reason": "maxCellBytes",
  "sourceBytes": 12345678,
  "sourceDigest": "sha256:<digest>"
}
```

Recommended TypeScript contract:

```ts
export type SpatialKind = "geometry" | "geography";

export interface SpatialCellOkV1 {
    readonly $t: "spatial";
    readonly version: 1;
    readonly status: "ok";
    readonly kind: SpatialKind;
    readonly encoding: "wkb";
    readonly srid: number;
    readonly wkbBytes: number;
    readonly wkb: string;
}

export type SpatialTransportReason =
    | "maxCellBytes"
    | "conversionFailed"
    | "unsupportedNativeValue"
    | "unsupportedInterchange";

export interface SpatialCellUnavailableV1 {
    readonly $t: "spatial";
    readonly version: 1;
    readonly status: "unrenderable";
    readonly kind: SpatialKind;
    readonly reason: SpatialTransportReason;
    readonly srid?: number;
    readonly sourceBytes?: number;
    readonly sourceDigest?: string;
}

export type SpatialCellEncodingV1 = SpatialCellOkV1 | SpatialCellUnavailableV1;
```

Keep v1 minimal:

- Do not add `hasZ`, `hasM`, `empty`, `approximated`, or normalized digests until the provider matrix proves their semantics and a consumer needs them.
- Derive empty and decoded geometry type in the decoder when possible.
- Include `sourceDigest` only for a value that is not otherwise represented and only when the full native stream was already read and hashed. Do not hash every successfully renderable cell without a consumer.
- Do not use a render-policy reason such as `geographyLineUnsupported` in the STS2 sentinel. The value may be valid and useful to a future renderer.
- If a bounded human preview is later added, call it `display`, give it a separate byte cap and truncation flag, and include it in all byte accounting. It is not required for the initial wire contract.

Repeating `kind` per cell is acceptable for v1 because it makes retained cell values self-describing. If payload evidence later justifies moving it exclusively to column metadata, make that a deliberate contract revision rather than an ad hoc optimization.

#### 4.2.3 One shared tagged-cell codec

Create an isomorphic, dependency-light module, for example:

```text
extensions/mssql/src/sharedInterfaces/queryResultCellCodec.ts
```

It should contain:

- tagged-value interfaces;
- strict structural guards;
- wire normalization helpers used by both compact and noncompact STS2 paths;
- purpose-specific formatting helpers that do not import VS Code or DOM APIs.

Do not keep one broad `cellDisplayText()` as the accidental policy for every surface. Add explicit purposes:

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

export function cellTextForPurpose(
    value: unknown,
    metadata: QueryResultCellMetadata | undefined,
    purpose: CellTextPurpose,
): string;
```

Recommended ordinary-surface policy for `status: "ok"`:

| Surface | Initial behavior |
| --- | --- |
| Grid preview | Localized summary such as `GEOMETRY, SRID 0, 21 WKB bytes`; optionally include a separately approved bounded preview |
| Tooltip/details | Type, SRID, WKB bytes, and transport status; no base64 |
| Cell document | Exact WKB as SQL-style `0x` hexadecimal plaintext, under existing open-cell limits |
| Copy | Exact WKB hex when within the copy budget; otherwise existing honest large-cell behavior |
| Text view | WKB hex or the approved bounded text representation, consistently documented |
| CSV/JSON export | Exact WKB hex string, not internal JSON and not base64 |
| INSERT export | Prefer a tested `geometry::STGeomFromWKB` or `geography::STGeomFromWKB` expression using hex and SRID; until implemented, use an explicit, tested fallback rather than generic object stringification |
| AI/tool serialization | Metadata summary only unless an existing explicit result-data grant permits the value; never silently forward coordinates |

For `status: "unrenderable"`, every ordinary surface must produce an honest localized description that includes the reason and known byte count, without raw object JSON.

The exact ordinary display choice can be adjusted by product review, but these invariants cannot:

- no base64 in ordinary UI;
- no `[object Object]`;
- no raw tagged JSON;
- no generic `$t` fallback consuming the spatial tag;
- no export silently dropping the value;
- compact and noncompact row paths normalize the same way.

Do not enable `spatialEncoding: "wkb-v1"` until these tests pass.

### 4.3 Put exact wire safety in the correct layer

The current SqlClient driver groups provider objects into approximate pages. The runtime later encodes cells and currently records `rowsJson.Length`, which is a UTF-16 character count, as encoded bytes. Unknown provider values are estimated as a small fixed size by the driver page builder. A spatial value makes the mismatch more visible, but it is not a spatial-only problem.

Keep these responsibilities separate:

| Layer | Responsibility |
| --- | --- |
| SqlClient driver | Exact spatial-type recognition, bounded native read, canonical value creation, source-byte facts |
| Provider-neutral driver abstraction | Carries a bounded spatial value or sentinel, not JSON text |
| STS2 runtime encoder | Produces the tagged JSON value and knows exact UTF-8 encoded size |
| Page packer | Packs already encoded rows under row and byte targets |
| Transport writer | Measures the complete JSON-RPC frame and enforces `MaxFrameBytes` |

#### 4.3.1 Preferred implementation

Refactor the row pipeline so a cell and row are encoded once in the runtime, then page-packed from that encoded representation. The runtime, not the SqlClient driver, owns wire page sequence and row offset after repacking.

A practical shape is:

```text
Driver row batch
  -> runtime EncodeCell once
  -> EncodedRow { node/json, utf8Bytes }
  -> exact page packer
  -> compact/legacy page body
  -> final JSON-RPC frame measurement
```

Avoid making the SqlClient driver depend on runtime JSON types merely to calculate page bytes.

#### 4.3.2 Minimum safe preview path

If the complete encode-once page repacker is too large to land before the first preview, the minimum acceptable path is:

1. Bound native spatial input and normalized WKB under the effective per-cell ceiling.
2. Give the driver page estimator an honest conservative spatial estimate, including base64 expansion and wrapper overhead.
3. Stop claiming exact `pageBytes` conformance while the implementation is approximate. If a capability says it is exact, correct the implementation or advertise it as unsupported.
4. Add a final complete-frame UTF-8 guard before the transport writes.
5. Return a stable typed row-too-large failure if one complete encoded row cannot fit a frame.
6. Never drop a row, drop a cell, or emit partial WKB to recover from the failure.

The final frame guard is non-negotiable. Exact page packing is strongly preferred and should be a separate protocol-foundation change if it cannot be completed in the same service patch.

### 4.4 Make sparse projection a shared result-store capability

The existing result store supports one contiguous column span. A spatial column and a distant label column would either pull all columns between them or issue two aligned reads. On spilled pages, two reads can deserialize and parse the same spill frame twice because non-grid scans are intentionally not readmitted to the viewport cache.

If the MVP includes a label-column selector, add general sparse projection before the spatial service.

Recommended API:

```ts
export interface CellWindowRequest {
    readonly resultSetId: string;
    readonly rowStart: number;
    readonly rowCount: number;
    readonly reason: RowReadReason;
    readonly columnStart?: number;
    readonly columnCount?: number;
    readonly columnOrdinals?: readonly number[];
}

export interface RowStreamRequest {
    readonly resultSetId: string;
    readonly rowStart: number;
    readonly rowCount: number;
    readonly chunkRows: number;
    readonly reason: RowReadReason;
    readonly columnOrdinals?: readonly number[];
}
```

Rules:

- `columnOrdinals` and the contiguous span are mutually exclusive.
- Validate ordinals once, deduplicate them, and preserve requested order.
- Project `columns`, `typeHints`, values, and null bitmap into that same order.
- Include the ordered projection in the served-window cache key.
- Implement it through `RowStore`, `RetainedRowStore`, snapshot reads, and derived-window stitching.
- Correct the derived-window path so it honors projection instead of fetching complete parent rows.
- Add tests for adjacent, distant, reversed, duplicate, invalid, empty, spilled, retained, and derived projections.

The spatial service then requests `[spatialColumn]` or `[spatialColumn, labelColumn]` in one materialization pass.

If this platform change is deferred, remove the label selector from the first UI slice. Fetch a selected row's label and details on demand after selection. Do not quietly use a repeated two-read scan as the production architecture.

### 4.5 Use existing run identity and define a complete session lifecycle

`IQueryResultStore` already has a random `runId` and `storeId`. The controller already owns the live `RetainedRowStore`, while the pinned controller owns a snapshot ID. Keep those identities inside the extension host.

Do not add a webview-supplied source ID, store ID, snapshot ID, or run ID to the spatial RPC. Do not use `execution.startedEpochMs` as data authority. It is suitable for UI reset and elapsed-time display only.

The controller opens a session against the source it already owns. The session captures the store's internal `runId`, acquires a lease, and returns only opaque session identity.

#### 4.5.1 Session state machine

```text
open
  -> reading
  -> completed
  -> cancelled
  -> expired
```

Required behavior:

- `open` resolves the current controller-bound live store or pinned snapshot internally.
- `open` freezes the selected result summary and effective host budgets.
- At most one `next` request is active per handle.
- Each response has a monotonically increasing sequence.
- A random session generation prevents stale responses from a recycled handle.
- `cancel` is idempotent.
- Rerun, source disposal, result-column change, panel disposal, and whole-panel hide cancel active sessions.
- Use `webviewPanel.visible`, not merely `active`, for host-side hide cleanup. A split panel can remain visible while inactive.
- When the final `done: true` response is returned, remove the session and release its lease immediately.
- Expiry also releases the lease and any buffered response state.
- Session limits are resolved by the host registry. The webview cannot request a larger budget.

Add a lease owner kind such as `spatialView` and a row read reason `spatial`.

### 4.6 Define row identity precisely and keep reveal mapping local

Rename `sourceRow` in the proposed feature shape to `resultRowOrdinal`.

```ts
interface SpatialSourceFeature {
    readonly resultRowOrdinal: number;
    readonly spatial: SpatialCellEncodingV1;
    readonly label?: string;
    readonly labelTruncated?: boolean;
    readonly originRowOrdinal?: number;
}
```

Meaning:

- `resultRowOrdinal` is zero-based within the live or pinned result view bound to the session.
- For a normal live or frozen result, this is the ordinary result row ordinal.
- For a future derived snapshot, it is the derived view's row ordinal unless the source explicitly provides origin lineage.
- `originRowOrdinal` is optional and must never be invented.

The grid's sort and filter are currently webview-local. Therefore, map-to-grid reveal should also be mapped in the webview:

1. Spatial selection identifies `resultRowOrdinal`.
2. Switch to Results.
3. Ask the mounted grid registry to map the result ordinal into its current display order.
4. If present, scroll, select, and focus.
5. If filtered out, preserve the filter and offer **Clear filter and reveal**.
6. Only after mapping succeeds should the Query Result Context service claim an active display row and cell.

Before mapping, context may carry a distinct spatial selection kind with `resultRowOrdinal`, but it must not reuse the existing display-row `active: { row, column }` shape as though the mapping had succeeded.

Do not add a host round trip to map a sort/filter state that the host does not own.

### 4.7 Separate transport, decode, semantic support, and topology validity

Use a four-stage status model:

| Stage | Example status | Owner |
| --- | --- | --- |
| Transport | `ok`, `maxCellBytes`, `conversionFailed` | STS2 and SQL Data Plane |
| Decode | `decoded`, `decodeFailed`, `vertexBudget` | Webview decoder |
| Semantic support | `renderable`, `unsupportedGeographyEdge`, `unsupportedCurve`, `unsupportedSridTransform` | Spatial adapter/render policy |
| Topology validity | `unknown`, or an explicit provider-derived fact | Never inferred from parsing alone |

Do not label a geometry `invalid` merely because OpenLayers rejects it. That is a decode failure. Do not label a successfully decoded geometry valid unless SQL Server or an approved validator supplied that fact.

Do not issue `STIsValid()` or other hidden database calls per cell in MVP. The viewer should display query results, not run a second validation workload without the user's query expressing it.

The status bar and feature list can still distinguish:

- null;
- empty;
- transport unavailable;
- corrupt or unsupported WKB;
- unsupported geography semantics;
- unsupported SRID transform;
- decoder budget;
- rendered.

### 4.8 Decode and render incrementally without precommitting to a worker

OpenLayers' WKB reader constructs geometry objects while it parses. A worker cannot transfer those class instances directly as a stable public protocol. A worker design therefore requires a second plain-geometry representation, a transfer format, and a second set of memory budgets.

Start with the simpler path:

1. Lazy-import the WKB reader and map modules after Spatial activation.
2. Decode one bounded host chunk at a time.
3. Validate base64 length against `wkbBytes` before parsing.
4. Catch WKB parser exceptions per cell.
5. Count coordinates immediately after parsing and discard a feature before commit if it would exceed the vertex budget.
6. Estimate derived memory consistently and stop before committing the next feature that would cross the limit.
7. Commit features in small batches.
8. Yield when the work-slice deadline is reached.
9. Cancel the host pull when the decoder reaches a terminal local budget.

Because each WKB cell is already capped, one pathological cell has a bounded input size. If fuzzing shows that parser count fields can still produce unacceptable work or allocation behavior, add a lightweight WKB structural preflight scanner before OpenLayers construction. Do not write a second full geometry renderer.

A worker becomes justified only when repeatable traces under the supported budgets show one or more of these:

- unacceptable long tasks;
- delayed keyboard or pointer interaction;
- first paint missing its exploratory target;
- complex polygons causing visible stalls despite cooperative chunking.

If a worker is added later, version its messages, transfer `ArrayBuffer` where beneficial, and return plain geometry data rather than OpenLayers instances.

### 4.9 Lock mixed-SRID behavior for progressive chunks

The decoder discovers SRIDs as chunks arrive. A later chunk may introduce a new incompatible group after first paint.

MVP policy:

- Group features by `(kind, SRID)`.
- Select the first renderable group encountered in source-row order as the active group.
- Keep that group active for the session unless the user explicitly changes it.
- Never move already accepted features into a newly discovered coordinate space.
- Never overlay an incompatible group automatically.
- Show discovered group counts as facts about the scanned prefix until the scan completes.
- Fit only the active group.
- If the active group has no renderable feature, advance deterministically to the next renderable group.
- For an unknown or unsupported transform, use native coordinates and disable basemap modes.

For geography points around the antimeridian, test fit using an unwrap strategy based on the largest longitude gap. A naive `minX/maxX` extent can zoom to almost the entire world for points near `179` and `-179` degrees.

### 4.10 Keep CSP adoption narrow and testable

The current shared webview HTML emits no CSP meta tag and contains inline style. Do not convert every extension webview to a strict policy inside the Spatial UI patch.

Recommended foundation:

```ts
interface WebviewCspOptions {
    readonly enabled: boolean;
    readonly allowWorker?: boolean;
    readonly extraImgSources?: readonly string[];
    readonly extraConnectSources?: readonly string[];
}
```

Add a protected per-surface hook to `WebviewBaseController`, then:

1. Move the shared inline style into a local stylesheet, or nonce it correctly.
2. Emit `default-src 'none'` for opted-in surfaces.
3. Allow local scripts, dynamic chunks, styles, images, and fonts through `webview.cspSource` as required.
4. Add `worker-src` only if the worker path is selected.
5. Keep remote `img-src` and `connect-src` absent.
6. Adopt and test the policy for Query Studio and pinned results first.
7. Track other webview migrations separately.

Offline mode must make zero network requests, not merely tolerate network failure.

### 4.11 Fix compact capture before introducing coordinate payloads

Current digest capture wraps only the top-level `rows` field. Compact rows place result values and null patterns under `compact`.

Fix this as an independent prerequisite:

- When a `driver.queryEvent` has `eventType: "rows"`, wrap whichever complete row payload is present: `rows`, `compact`, or both if a malformed test intentionally supplies both.
- For compact mode, elide the complete object, including `values`, `nullBitmap`, `typeHints`, and future result-derived fields.
- Treat the null bitmap as result data.
- Restore the object only at the existing effect or wire edge.
- Preserve digest/replay identity.
- Remove side-table entries on every success, suppression, error, cancel, and disposal path.
- Add canaries to journal, replay export, diagnostic export, and failure tests.

Do not add spatial WKB to compact rows until these canaries pass.

## 5. Concrete contracts for implementation

The following contracts are intended to prevent an agent from improvising incompatible seams. Exact names may follow repository conventions, but the authority boundaries should remain.

### 5.1 Column metadata

Add a backend-neutral spatial marker to SQL Data Plane metadata and Query Studio summaries.

```ts
export interface SpatialColumnMetadata {
    readonly kind: SpatialKind;
    readonly encoding: "wkb-v1";
}

export interface ColumnMetadata {
    // existing fields...
    readonly spatial?: SpatialColumnMetadata;
}

export interface QsResultColumn {
    // existing fields...
    readonly spatial?: SpatialColumnMetadata;
}
```

Eligibility uses metadata, not a scan of row values and not suffix matching against arbitrary UDT names.

The SqlClient driver may use provider-specific metadata internally to prove that the type is exactly SQL Server's system `geometry` or `geography`. Provider identity must not leak into SQL Data Plane contracts.

### 5.2 STS2 negotiation

Service initialize result:

```json
{
  "capabilities": {
    "spatialWkbV1": true
  }
}
```

Per-execute option:

```json
{
  "options": {
    "spatialEncoding": "wkb-v1"
  }
}
```

Rules:

- Initialize advertisement states support but does not by itself enable the changed value shape.
- The client opts in per execute.
- The normalized option appears in effect arguments and replay identity.
- A client that does not opt in receives the prior safe behavior.
- The option is rejected or ignored according to an explicit compatibility rule when unsupported. Do not silently emit a new tagged value to an old client.

### 5.3 Driver abstraction

Illustrative provider-neutral shape:

```csharp
public sealed class DriverSpatialValue
{
    public required string Kind { get; init; }       // geometry | geography
    public required int Srid { get; init; }
    public required byte[] Wkb { get; init; }
    public long? SourceBytes { get; init; }
    public string? SourceDigestHex { get; init; }
}

public sealed class DriverSpatialUnavailableValue
{
    public required string Kind { get; init; }
    public required string Reason { get; init; }
    public int? Srid { get; init; }
    public long? SourceBytes { get; init; }
    public string? SourceDigestHex { get; init; }
}
```

The exact implementation may avoid retaining `SourceDigestHex` for successful values. The important rule is that provider CLR types stop at the SqlClient driver boundary.

Spatial reading should be a new classified cell-read mode rather than a special case hidden in generic `GetValue()` fallback.

### 5.4 Spatial RPC

The webview request contains selection only. It does not contain host budgets or result-source identity.

```ts
export interface QsSpatialOpenParams {
    readonly resultSetId: string;
    readonly spatialColumn: number;
    readonly labelColumn?: number;
}

export interface QsSpatialFrozenSummary {
    readonly resultSetId: string;
    readonly rowCount: number;
    readonly complete: boolean;
    readonly truncatedReason?: string;
    readonly corrupt: boolean;
    readonly spatialColumn: number;
    readonly labelColumn?: number;
    readonly effectiveBudget: {
        readonly maxRows: number;
        readonly maxPayloadBytes: number;
        readonly maxLabelBytes: number;
        readonly targetResponseBytes: number;
        readonly maxResponseBytes: number;
    };
}

export interface QsSpatialOpenResult {
    readonly handle: string;
    readonly generation: string;
    readonly summary: QsSpatialFrozenSummary;
}

export interface QsSpatialNextParams {
    readonly handle: string;
    readonly generation: string;
    readonly sequence: number;
}

export interface QsSpatialSourceFeature {
    readonly resultRowOrdinal: number;
    readonly spatial: SpatialCellEncodingV1;
    readonly label?: string;
    readonly labelTruncated?: boolean;
}

export interface QsSpatialHostProgress {
    readonly sourceRowsScanned: number;
    readonly sourceRowsTotal: number;
    readonly candidateCells: number;
    readonly nullCells: number;
    readonly transportUnavailableCells: number;
    readonly payloadBytes: number;
    readonly partial: boolean;
    readonly partialReason?:
        | "rowBudget"
        | "payloadBudget"
        | "timeBudget"
        | "cancelled"
        | "storeShortRead"
        | "storeCorrupt";
}

export interface QsSpatialFeatureChunk {
    readonly handle: string;
    readonly generation: string;
    readonly sequence: number;
    readonly scannedRowStart: number;
    readonly scannedRowEndExclusive: number;
    readonly features: readonly QsSpatialSourceFeature[];
    readonly progress: QsSpatialHostProgress;
    readonly payloadBytes: number;
    readonly done: boolean;
}

export interface QsSpatialCancelParams {
    readonly handle: string;
    readonly generation: string;
}
```

Use request/response RPC for `open`, `next`, and `cancel`. Do not stream feature data through notifications.

#### 5.4.1 Chunk construction rules

- Scan result rows in ascending `resultRowOrdinal`.
- Include an entry only when the spatial cell is non-null. Empty and unavailable cells may be represented as entries if the feature list needs row-level reasons; otherwise count them and fetch details on demand. Choose one policy and test it.
- Clamp labels by UTF-8 bytes, not JavaScript string length.
- End a normal response before adding the next feature that would exceed the soft response target.
- One feature may exceed the soft target only when it still fits the hard response maximum. With the current 1 MiB raw-WKB cell ceiling, the initial 2 MiB hard maximum leaves room for base64 expansion and wrappers.
- If one feature cannot fit the hard maximum, return a typed session partial reason and advance or terminate deterministically. Do not loop forever on the same row.
- Measure `Buffer.byteLength(JSON.stringify(response), "utf8")` in the host before returning the response. Use a conservative cap below the transport maximum.
- Counts describe only the scanned prefix until `done` follows a complete scan.

### 5.5 Host service placement

Recommended modules:

```text
extensions/mssql/src/queryResults/spatial/
  spatialTypes.ts
  spatialSessionManager.ts
  spatialResultReader.ts
  spatialBudget.ts
  spatialDiagnostics.ts
  liveSpatialReadSource.ts
  pinnedSpatialReadSource.ts
```

Controller responsibilities:

- bind the service to its owned live store or pinned snapshot;
- register RPC handlers;
- cancel sessions on rerun, hidden panel, and disposal;
- never scan rows itself.

`SpatialSessionManager` responsibilities:

- create opaque handles and generations;
- resolve host budgets;
- acquire and release leases;
- enforce one in-flight `next`;
- enforce sequence, expiry, and concurrency caps;
- invoke the projected reader;
- produce value-free diagnostics.

`SpatialResultReader` responsibilities:

- read sparse projected windows with `reason: "spatial"`;
- preserve result-row ordinals;
- clamp labels;
- maintain source-prefix counts;
- stop on host budgets and cancellation;
- never parse WKB or import renderer code.

### 5.6 Webview module placement

Recommended modules:

```text
extensions/mssql/src/webviews/pages/QueryStudio/spatial/
  SpatialResultsPane.tsx
  SpatialToolbar.tsx
  SpatialStatus.tsx
  SpatialFeatureList.tsx
  spatialDecode.ts
  spatialProjection.ts
  spatialOlAdapter.ts
  spatialSelection.ts
  spatialTypes.ts
```

Keep `app.tsx` responsible for orchestration only:

- eligibility;
- active tab;
- chosen result and column;
- lazy component boundary;
- pane visibility and cancellation trigger.

Do not put WKB parsing, feature grouping, map construction, or host pull loops directly in `app.tsx`.

## 6. Dependency-ordered pull request plan

The safest path is a stack of narrow changes. Keep the feature gate default off until the full vertical slice passes.

### PR 1 - Compact capture privacy fix

**Repository:** `sqltoolsservice`  
**Feature behavior:** none

Deliver:

- Elide and restore the complete compact row payload.
- Add normal and spatial-shaped canaries, even before real spatial encoding exists.
- Cover journal, replay, diagnostic export, error, cancel, and suppression paths.

Exit:

- No compact values or null patterns appear in persisted capture artifacts.

### PR 2 - Tagged-cell codec and ordinary consumer safety

**Repository:** `vscode-mssql`  
**Feature behavior:** none

Deliver:

- Shared spatial interfaces and strict guard using `wkb`, not `v`.
- Central tagged-cell normalization for compact and noncompact STS2 rows.
- Purpose-specific grid, copy, text, cell-document, export, transform, and tool behavior.
- Synthetic tagged-value tests through RowStore spill and every consumer.

Exit:

- A synthetic spatial tag never displays as base64, raw JSON, or `[object Object]`.
- No service capability is enabled yet.

### PR 3 - STS2 spatial provider and wire contract

**Repository:** `sqltoolsservice`  
**Feature behavior:** protocol available only when opted in

Deliver:

- Provider/RID evidence tests.
- Exact native system-type recognition.
- Bounded spatial reader and provider-neutral driver value.
- WKB v1 tag and sentinel.
- Initialize capability and per-execute option.
- Final frame guard and row-too-large behavior.
- Preferred exact page packing, or the documented minimum safe preview path with honest capability advertisement.

Exit:

- Supported fixtures round-trip through normal and compact rows across the approved RID matrix.
- No partial WKB and no over-limit frame is written.

### PR 4 - SQL Data Plane and Query Studio metadata integration

**Repository:** `vscode-mssql`  
**Feature behavior:** still gated off in UI

Deliver:

- Capability and execute-option plumbing.
- Spatial column metadata.
- Spatial tagged-cell validation in both row paths.
- Round trip through RowStore, retained stores, and pinned snapshots.
- Downgrade and old-service tests.

Exit:

- An opted-in run stores safe backend-neutral values and all ordinary consumers remain correct.

### PR 5 - General sparse projection

**Repository:** `vscode-mssql`  
**Feature behavior:** reusable platform capability

Deliver:

- `columnOrdinals` across store, stream, retained, snapshot, and derived paths.
- Projection cache keys, null bitmaps, metadata, and spill tests.

Exit:

- One materialization pass can return a spatial column and distant label column in requested order.

If this PR is deferred, explicitly remove label-column selection from PR 7.

### PR 6 - Spatial host session service

**Repository:** `vscode-mssql`  
**Feature behavior:** RPC available behind gate, no map required

Deliver:

- `spatialView` lease owner and `spatial` read reason.
- Controller-bound live and pinned adapters.
- Opaque open/next/cancel sessions.
- Host budgets, exact response-body measurement, expiry, concurrency, cancellation, and completion release.
- Fake/synthetic spatial fixtures and a test consumer.

Exit:

- No React row scan.
- No webview-controlled source identity or budget.
- Store leases and spill files release on every terminal path.

### PR 7 - Offline Query Studio UI vertical slice

**Repository:** `vscode-mssql`  
**Feature behavior:** default-off preview

Deliver:

- Conditional Spatial tab and grid action.
- Lazy OpenLayers Canvas viewer.
- Geometry standard linear shapes and geography points.
- Native Cartesian, 4326, and 3857 policies.
- Incremental decode, budgets, mixed-SRID grouping, fit, select, details, and feature list.
- Honest terminal partial and unsupported states.
- Localization, high contrast, reduced motion, keyboard, and screen-reader flow.
- Query Studio surface CSP and zero-network tests.

Exit:

- The supported matrix renders correctly offline.
- Unsupported geography edges are never drawn as straight projected chords.
- Spatial unopened causes no host scan or renderer import.

### PR 8 - Reveal, context, and pinned parity

**Repository:** `vscode-mssql`

Deliver:

- Grid registry mapping from `resultRowOrdinal` to display order.
- Filter-preserving reveal flow.
- Spatial-aware Query Result Context semantics.
- Shared Spatial pane in pinned results.
- Pinned surface CSP and lifecycle tests.

Exit:

- Live and pinned use the same preparation and rendering contracts.
- Selection never confuses source/result ordinals with display rows.

### PR 9 - Performance, perftest, and release hardening

**Repositories:** `vscode-mssql`, `sqltoolsservice`, and the applicable perftest repository

Deliver:

- Deterministic spatial fixtures and registered marker vocabulary.
- Unopened nonspatial and unopened spatial baselines.
- First-paint, budget, rerun, hide, split-panel, pinned, accessibility, and zero-network proofs.
- Bundle and VSIX measurement.
- Budget tuning from evidence.
- Worker or WebGL only if the measurements justify them.

Exit:

- Preview documentation, rollback, supported matrix, and privacy behavior are complete.

## 7. Test and acceptance additions

The baseline test plan is comprehensive. Add the following tests because they are tied directly to current code behavior.

### 7.1 Contract collision tests

- A spatial tag with `wkb` must fail `isTypedCellWrapper` and pass only the spatial guard.
- A malformed spatial tag with `v` but no `wkb` must be rejected, not treated as a generic scalar.
- Compact and noncompact STS2 pages must produce byte-for-byte equivalent backend-neutral cell objects.
- Unknown `$t` values must have a safe, explicit fallback policy.

### 7.2 Ordinary consumer matrix

For renderable and unrenderable spatial values, test:

- grid text and tooltip;
- sort and filter behavior;
- copy cell, row, and range;
- text view;
- cell document;
- CSV;
- JSON;
- INSERT;
- transform comparison/projection;
- AI/tool serialization under allowed and denied data grants;
- RowStore spill/restore;
- pinned snapshots.

Assertions should prove the absence of raw base64, raw tag JSON, and `[object Object]` where those are not the selected exact export representation.

### 7.3 Unopened-cost tests

With a spatial result and the feature gate enabled but the tab unopened, prove:

- STS2 spatial conversion occurred only for spatial cells as expected;
- `RowReadReason: "spatial"` count is zero;
- no spatial session exists;
- no `ol` dynamic chunk was requested or evaluated;
- no decoder scheduler or worker was created;
- no canvas/map instance exists;
- ordinary grid first paint and scrolling remain within the exploratory baseline.

With a nonspatial result, additionally prove no spatial reader/conversion branch is entered.

### 7.4 Sparse projection tests

- Two distant columns from an in-memory page.
- Two distant columns from a spilled page with one materialization per page.
- Reversed requested order.
- Duplicate ordinals.
- Invalid ordinals.
- Empty projection.
- Retained store after live-owner release.
- Frozen snapshot clamp.
- Derived snapshot mapping with projection.
- Null bitmap and type-hint alignment.

### 7.5 Session lifecycle tests

For every case, assert lease count and spill cleanup:

- normal final chunk;
- user cancel;
- tab switch during pull;
- result-column change;
- rerun before first chunk;
- rerun after partial chunks;
- panel hidden but not disposed;
- split panel inactive but visible;
- panel disposal;
- session expiry;
- duplicate cancel;
- concurrent `next`;
- stale generation;
- wrong sequence;
- controller concurrency cap;
- global concurrency cap;
- store short read or corruption.

### 7.6 Spatial fidelity tests

- X/Y and longitude/latitude orientation.
- Little- and big-endian WKB if the approved producer can emit both.
- Empty values.
- Polygon holes and ring orientation independence.
- Nested GeometryCollection source-row identity.
- Mixed SRIDs discovered in later chunks.
- Geometry 4326 straight-line semantics.
- Geography points around `179/-179` longitude.
- Poles.
- Geography line and polygon rejection with no canvas geometry created.
- Curves and `FullGlobe` according to the final matrix.
- Z/M flags according to the final interchange evidence.
- Corrupt length/count fields and parser exceptions.
- One cell at, below, and above every source/WKB/wire/frame threshold.

### 7.7 Accessibility acceptance

The feature is not complete when the canvas looks correct. It is complete when a keyboard or screen-reader user can:

1. Activate Spatial through the tab list.
2. Choose result and spatial column.
3. Read preparation and partial status.
4. Navigate loaded features in a virtualized DOM list.
5. Select a feature and hear its row, type, SRID, and label summary.
6. Fit or focus the selected feature.
7. Reveal it in Results.
8. Understand when it is filtered out.
9. Return to the map without losing logical selection.

Verify roving tab focus, tab/panel relationships, F6-region behavior, 200 percent zoom, forced colors, high contrast, reduced motion, and narrow pane heights.

### 7.8 Privacy acceptance

Use unique coordinate and label canaries. They must not occur in:

- STS2 journals;
- replay bundles;
- diagnostic exports;
- extension logs;
- error messages;
- production marker attributes;
- webview performance marks;
- online requests, because none are permitted.

Inspect both successful and failed runs, compact and legacy row modes, and hidden/disposed sessions.

## 8. Tradeoffs and alternate approaches

### 8.1 Canonicalize during ingestion versus defer work

**Recommended:** canonicalize during the opted-in STS2 row stream.

This costs CPU even when the tab remains unopened, but it preserves a provider-neutral, replayable result and does not rewrite the query. Deferring conversion would require retaining provider-specific bytes or rerunning SQL, both of which violate stronger architecture goals.

Mitigation is measurement, a preview gate, exact type classification, bounded cells, and zero secondary work until activation.

### 8.2 Exact page repacker versus conservative preview safety

**Preferred:** encode once and exact-pack pages in the runtime.

**Acceptable preview compromise:** conservative spatial estimates, honest page-byte capability, and a hard final-frame guard.

The compromise can unblock the viewer without pretending the existing approximate page builder became exact. It should be documented as protocol debt with a separate owner.

### 8.3 Sparse projection versus aligned dual reads

**Recommended:** general sparse projection.

Dual reads are smaller in code but can duplicate spill I/O and JSON materialization. They also establish a spatial-only access pattern that other secondary consumers cannot reuse. Sparse projection is the cleaner platform improvement.

The simplest alternative is to defer label scanning, not to hide a repeated dual-read loop inside the controller.

### 8.4 Main thread versus worker

**Recommended:** incremental main-thread parsing first.

A worker can improve responsiveness at higher scale, but it also creates a transfer protocol, separate cancellation semantics, duplicated geometry representation, CSP changes, and bundle/test cost. Under a 25,000-row and 250,000-vertex cap, cooperative main-thread work may be sufficient.

Measure before adding the extra machine room.

### 8.5 OpenLayers versus MapLibre

**Recommended:** OpenLayers.

The core product problem is native SQL spatial data, including arbitrary Cartesian coordinates, not a hosted slippy map. OpenLayers fits a no-tile map and native projection view naturally. MapLibre becomes more attractive only if the product goal changes toward styled online cartography.

Do not abstract a generic map-provider framework in MVP. A renderer adapter boundary is enough.

### 8.6 Geography points-only versus early densification

**Recommended:** points and multipoints only in MVP.

Correct geodesic densification requires an ellipsoid policy, tolerance definition, antimeridian and pole handling, cancellation, generated-vertex accounting, and visible approximation disclosure. That is a real feature, not a minor parser option. Shipping lines as straight projected chords would be simpler but wrong.

### 8.7 Live-first versus simultaneous pinned support

**Recommended:** implement one controller-bound source interface, deliver live first, then pinned in the next narrow change.

Trying to land both UI surfaces in the first renderer PR increases test breadth. Designing only for live results creates an avoidable fork. The shared service boundary lets the work be sequenced without compromising architecture.

### 8.8 World outline in MVP

**Recommended:** defer.

A local physical outline is useful polish for geography, but it adds asset provenance, package size, projection behavior, and visual-composition testing. The first vertical slice should prove result fidelity, lifecycle, accessibility, and offline behavior with a graticule and coordinate context.

## 9. Thoughts on the plan

### 9.1 What is especially strong

The baseline correctly recognizes that drawing shapes is the easy sliver. The real feature is a cross-repository result contract that preserves type, SRID, row identity, bounds, and honesty without creating a second result cache. That framing is exactly right.

Its best decisions are:

- treating Spatial as a sibling representation of the same result;
- keeping STS2 forward-only and the extension host as the random-access owner;
- refusing query rewriting;
- making offline the normal state instead of a degraded state;
- separating planar geometry from geography;
- refusing to fake geography edges;
- requiring source-row reveal and an accessible feature list;
- budgeting rows, bytes, vertices, memory, time, and cancellation separately;
- treating online tiles as location disclosure;
- planning observability without result values.

Those choices give the feature a sturdy skeleton rather than a pretty but brittle map-shaped shell.

### 9.2 The main execution risk

The design contains several legitimate platform fixes that are larger than the visual feature:

- compact capture privacy;
- exact frame and page accounting;
- a shared tagged-cell codec;
- sparse projection;
- per-surface CSP;
- result-context row identity;
- a generalized session/lease pattern.

Each is worthwhile. Together they can swallow the feature if they are implemented as one umbrella change. The PR sequence above is intended to keep the blast radius visible. Every foundation should be independently testable and useful even if the map is temporarily disabled.

### 9.3 The most important product tradeoff

The only unavoidable unopened cost is spatial canonicalization during ingestion. The plan should say this plainly. Otherwise performance tests may chase an impossible goal or an implementation agent may attempt a late query rewrite to preserve the original wording.

The right promise is not “free until the tab opens.” It is “bounded canonical result capture during the opted-in query, then zero secondary work until the tab opens.”

### 9.4 The most important code-level hazard

The existing generic `{$t, v}` display path makes the provisional spatial tag unsafe. This is exactly the kind of small-looking shape collision that spreads through grid, copy, export, text, cell documents, transforms, and tools. Solve the shared cell codec before the service emits the first real coordinate.

### 9.5 The best scope reduction

Start with standard linear `geometry` and `geography` points. That still delivers a useful SQL Server spatial viewer while keeping every rendered shape truthful. Curves, geodesic edges, `FullGlobe`, WebGL, workers, online basemaps, world assets, and spatial export can then be added from evidence rather than anticipation.

### 9.6 Architectural opportunity

A well-factored spatial session becomes a reference implementation for future bounded secondary result consumers. It exercises leases, sparse projection, cancellation, pull backpressure, partial truth, pinned parity, and panel lifecycle without weakening the result-store ownership model. That is valuable beyond maps, but the spatial implementation should remain concrete and should not attempt to invent a universal visualization framework.

## 10. Instructions and guardrails for an AI code agent

An implementation agent should follow these rules without improvising around them.

### 10.1 Required behavior

- Read the baseline and this addendum before editing code.
- Inspect current `dev/query` code before relying on path or type names.
- Keep every change behind the preview gate until the vertical slice passes.
- Add tests in the same patch as each contract change.
- Keep feature data out of coarse state, diagnostics, telemetry, and capture.
- Use the existing result store and leases.
- Use opaque controller-bound spatial sessions.
- Localize user-visible strings from the first UI patch.
- Preserve offline zero-network behavior.
- Report partial facts with their scanned scope.

### 10.2 Prohibited shortcuts

Do not:

- rewrite the user's SQL to call spatial methods;
- parse arbitrary string or binary columns as spatial in MVP;
- call `String()` or `JSON.stringify()` as the spatial display policy;
- use `v` for base64 WKB;
- emit provider CLR objects beyond the SqlClient driver;
- add a React loop over `qs/getRows`;
- accept store, snapshot, source, budget, or lease authority from the webview;
- add a second authoritative raw-row or parsed-result cache;
- render unknown SRIDs on a world basemap;
- render geography edges as projected straight chords;
- call topology validity known when it was not measured;
- silently repair, simplify, sample, densify, or reproject;
- add a worker, WebGL tier, online map, world asset, or generic provider abstraction without evidence;
- broaden CSP to remote hosts;
- modify every webview's CSP as part of the map UI patch;
- claim exact page bytes while using character counts or approximate provider sizes;
- retain a spatial lease after a normal final chunk;
- call a result ordinal a display row before local grid mapping succeeds.

### 10.3 Stop conditions

Stop the feature patch and fix the prerequisite when any of these is true:

- compact capture canaries appear in a journal or export;
- the provider/RID matrix cannot reliably identify exact system `geometry` and `geography`;
- a successful spatial tag reaches a generic typed-wrapper branch;
- any ordinary consumer shows base64, raw JSON, or `[object Object]` unintentionally;
- one complete row can reach the writer above the frame ceiling without a typed pre-transport failure;
- label projection requires an unbounded span or repeated spill reads and sparse projection has not been approved;
- a rerun, hide, disposal, expiry, or final chunk leaves a store lease held;
- mixed SRIDs are overlaid without a proven transform;
- geography line or polygon coordinates reach the renderer without the approved geodesic policy;
- a hidden surface keeps pulling rows, parsing WKB, or retaining map resources;
- a production marker contains a coordinate, extent, label, raw SRID-plus-location context, WKB, tile URL, or result identifier.

## 11. Code anchors reviewed

These paths were inspected on the requested `dev/query` branches and explain the amendments above. Line numbers will move as the branch evolves, so use the symbols and behavior as the durable anchors.

### `microsoft/sqltoolsservice`

| Path / symbol | Observed behavior relevant to Spatial |
| --- | --- |
| `src/sts2/Microsoft.SqlTools.Sts2.Runtime/Coordination/CaptureElision.cs` / `ElideInput` | Digest capture recognizes row events but wraps only top-level `rows`; compact values and null bitmap remain present |
| `src/sts2/Microsoft.SqlTools.Sts2.Runtime/Effects/WireValueEncoder.cs` / `Encode` | `maxCellBytes` special-cases only string and byte array; unknown provider objects fall back to invariant `Convert.ToString` |
| `src/sts2/Microsoft.SqlTools.Sts2.Drivers.SqlClient/SqlClientSession.cs` / `PumpResultSetAsync` | Spatial currently falls through column classification to synchronous `reader.GetValue`; column metadata retains `DataTypeName` only |
| `src/sts2/Microsoft.SqlTools.Sts2.Drivers.SqlClient/SqlLargeValueReader.cs` | Bounded stream readers exist only for large text and binary and currently perform synchronous loops without token checks inside each chunk |
| `src/sts2/Microsoft.SqlTools.Sts2.Drivers.SqlClient/SqlRowsPageBuilder.cs` | Page bytes are approximate; unknown objects receive a small fixed estimate; one oversized row becomes its own page |
| `src/sts2/Microsoft.SqlTools.Sts2.Runtime/Effects/DriverEffectRunner.cs` | Rows are encoded after the driver's page grouping; compact `encodedBytes` currently uses `rowsJson.Length`; unknown engine types get a string hint |
| `src/sts2/Microsoft.SqlTools.Sts2.Contracts/Sts2Defaults.cs` | Current defaults are 1,000 rows, 256 KiB page target, 1 MiB cell, four unacked pages, and 64 MiB frame |

### `microsoft/vscode-mssql`

| Path / symbol | Observed behavior relevant to Spatial |
| --- | --- |
| `extensions/mssql/src/services/sts2/sts2Backend.ts` | Noncompact rows normalize only truncated tags; compact rows pass tagged objects through; spatial engine types currently get string hints |
| `extensions/mssql/src/sharedInterfaces/queryStudioGridOps.ts` / `isTypedCellWrapper`, `cellDisplayText` | Any non-truncated `{$t: string, v: string}` is a generic wrapper whose default display is `v` |
| `extensions/mssql/src/queryStudio/cellDocument.ts` | Cell documents delegate to the same shared display text used by the grid |
| `extensions/mssql/src/queryStudio/resultExport.ts` | CSV, JSON, and INSERT paths all flow through cell-document text, making a central codec high leverage |
| `extensions/mssql/src/queryStudio/rowStore.ts` | Read reasons do not yet include spatial; only contiguous projection exists; non-grid scans avoid protected-cache admission |
| `extensions/mssql/src/queryResults/queryResultTypes.ts` | `IQueryResultStore` already exposes `runId`, leases, windows, streams, and frozen summaries; lease owners do not yet include spatial |
| `extensions/mssql/src/queryResults/resultStoreLease.ts` | `RetainedRowStore` owns random run/store IDs and disposes the physical store on final lease release |
| `extensions/mssql/src/queryResults/queryResultAccessService.ts` | Snapshot windows forward contiguous projection; derived-window parent fetches currently do not honor projection |
| `extensions/mssql/src/queryStudio/executionHost.ts` | Each run creates a retained store with a random run ID; `results.streaming` is true only for `executing`, not `cancelRequested` |
| `extensions/mssql/src/queryStudio/queryStudioController.ts` | Ordinary row RPC goes directly to `ExecutionHost`; panel view-state handling currently restores focus but has no spatial-session cleanup |
| `extensions/mssql/src/queryResults/pinnedResultsController.ts` | Pinned reads are already controller-bound to its snapshot, which is the correct authority pattern for Spatial |
| `extensions/mssql/src/queryResults/queryResultContextService.ts` | Current active selection stores display-like `{row, column}` without a distinct spatial result-ordinal form |
| `extensions/mssql/src/webviews/pages/QueryStudio/app.tsx` | Tabs are locally owned; `startedEpochMs` is used as a webview run reset key; sort/filter and grid display state remain in the webview |
| `extensions/mssql/src/controllers/webviewBaseController.ts` | Shared HTML has no CSP meta and includes inline style |
| `extensions/mssql/scripts/bundle-webviews.js` | ESM splitting and an explicit Monaco worker entry already exist; lazy chunks and optional worker entries fit the build system |

## 12. Definition of ready for the UI vertical slice

The UI renderer work may start when all items below are true:

- [ ] Compact row capture elides the complete compact payload and passes canaries.
- [ ] Exact SQL Server system spatial types are recognized on the supported RID matrix.
- [ ] `spatialWkbV1` and the per-execute option are approved.
- [ ] The spatial tag uses `wkb`, not generic `v`.
- [ ] Compact and noncompact row paths share strict spatial normalization.
- [ ] Grid, copy, text, cell-document, export, transform, and tool behavior are specified and tested.
- [ ] Per-cell bounds and the final complete-frame guard are implemented.
- [ ] The service either exact-packs pages or advertises page-byte behavior honestly.
- [ ] `spatial` read reason and `spatialView` lease ownership exist.
- [ ] Sparse projection exists, or the label selector has been explicitly removed from the first slice.
- [ ] Host-authoritative open/next/cancel sessions pass lifecycle and lease tests.
- [ ] Geography lines and polygons have an explicit unsupported renderer policy.
- [ ] Query Studio's offline CSP loads dynamic local chunks and makes zero network requests.
- [ ] The preview gate is default off.

## 13. Definition of done for the preview

- [ ] Standard linear `geometry` shapes render in native Cartesian space with correct X/Y and source-row identity.
- [ ] Geography Point and MultiPoint render with correct longitude/latitude and antimeridian-aware fit.
- [ ] Unsupported geography edges, curves, and globe cases are disclosed rather than approximated accidentally.
- [ ] Mixed SRIDs never overlay silently.
- [ ] Opening Spatial starts one bounded controller-owned session; final completion releases its lease.
- [ ] Rerun, hide, disposal, tab change, expiry, and decoder budget cancel and clean up deterministically.
- [ ] The tab unopened performs no secondary row read and loads no renderer code.
- [ ] Grid, text, copy, cell document, CSV, JSON, INSERT, spill, and pinned values remain safe.
- [ ] A keyboard and screen-reader user can navigate features, inspect one, and reveal it in Results.
- [ ] Light, dark, high contrast, high contrast light, forced colors, reduced motion, 200 percent zoom, and narrow panes pass.
- [ ] Offline mode produces zero requests.
- [ ] Production diagnostics and markers contain no result values or location data.
- [ ] Existing Query Studio execution, grid first paint, scrolling, spill, and query-completion scenarios show no material unopened regression.
- [ ] Supported and unsupported behavior, preview gate, rollback path, and privacy model are documented.

