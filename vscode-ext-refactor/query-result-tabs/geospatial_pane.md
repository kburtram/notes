# Query Studio Geospatial Results Pane - Initial Design

**Status:** Draft for detailed code and design review  
**Date:** 2026-07-09  
**Target branches:** `sqltoolsservice/dev/query`, `vscode-mssql/dev/query`, `perftest/dev/query`  
**Primary surface:** Query Studio result pane  
**Reference image:** `screens/spatial.png`

This document inventories the current result path, evaluates implementation options, and recommends an initial architecture for a modern spatial result viewer. It is intentionally a design input, not an implementation-ready specification. Items marked **research gate** or **open question** need evidence before code is committed.

## 1. Executive recommendation

Build an **offline-first Spatial tab** as a sibling of Results, Messages, and Query Plan. It should render the explicitly supported native SQL Server `geometry` and `geography` shape matrix without changing the query, preserve a source-row identity for every feature, and remain a bounded secondary consumer of the existing query result store.

The recommended direction is:

1. Fix the existing STS2 compact-row capture leak before adding richer result payloads.
2. Extend STS2's ordinary row stream with a negotiated, provider-neutral spatial cell encoded as bounded OGC WKB plus `geometry`/`geography`, SRID, and fidelity metadata. Do not add a separate spatial query protocol.
3. Extend the SQL Data Plane and `IQueryResultStore` path. Add a `spatial` read reason and a cancellable, budgeted spatial preparation service. React code must not implement a bespoke scan over `qs/getRows`.
4. Use [OpenLayers](https://openlayers.org/) as the first renderer candidate. It is a mature BSD-licensed mapping library, supports a map with no tile layer, handles planar/custom projections, and includes WKB/WKT/GeoJSON readers. Validate bundle cost, worker strategy, SQL Server edge cases, and canvas/WebGL performance in a spike before final approval.
5. Ship with **zero network requests by default**. Use a theme-aware coordinate canvas and, if package review approves it, a small bundled physical world outline for geographic data. Online streets or satellite imagery should be a separate opt-in milestone with a provider, credentials, attribution, caching, CSP, legal, and location-privacy design.
6. Treat the map as one representation of the result, not the only way to access it. Provide a synchronized, virtualized feature list and a selected-feature detail view so keyboard and screen-reader users can perform the same core workflow.
7. Start with completed or terminal partial result sets. Add progressive rendering during execution only after the complete-result path is stable and measured.

The difficult part is not drawing points. The current result contract does not preserve a canonical spatial value or SRID, and a provider spatial object can bypass `maxCellBytes` and honest page-byte accounting. That cross-repository contract must be solved first.

## 2. Proposed decisions at a glance

| Area             | Initial decision                                                                                                                 | Confidence                      |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------- | ------------------------------- |
| Product label    | `Spatial` tab; use `Spatial results` in accessible name/empty states                                                             | High                            |
| UI placement     | Sibling of Results, Messages, and Query Plan; conditional on eligible columns                                                    | High                            |
| Default behavior | Do not auto-open; do no spatial row work until the user opens the tab                                                            | High                            |
| First data types | Metadata-confirmed native SQL Server `geometry`; `geography` points plus only line/polygon forms whose geodesic policy is proven | Medium; fidelity spike required |
| Service payload  | Bounded OGC WKB with separate kind, SRID, and fidelity/status fields                                                             | Medium; RID/type spike required |
| Result ownership | Existing extension-host `IQueryResultStore` and leases                                                                           | High                            |
| Initial loading  | Completed result sets and terminal partial sets; cancellable bounded scan                                                        | Medium                          |
| Renderer         | OpenLayers, lazy loaded and locally bundled                                                                                      | Medium; spike required          |
| Projection       | Auto: native Cartesian for arbitrary geometry; geographic/projected only when known                                              | High                            |
| Basemap          | Offline canvas always; optional bundled physical orientation layer                                                               | Medium; asset review required   |
| Online imagery   | Default off; later allowlisted provider feature, not MVP                                                                         | High                            |
| Accessibility    | DOM toolbar plus synchronized feature list/details; canvas is not the sole interface                                             | High                            |
| Pinned results   | Design against the neutral result source now; live Query Studio may ship first                                                   | High                            |
| Export           | Existing result export must not regress; map image/GeoJSON export is deferred                                                    | Medium                          |

## 3. Branch and document context

All three implementation repositories are on `dev/query`. Relative to `main`, each branch has a large, mostly additive change set. Exact counts are intentionally omitted because these active branches move while this document is reviewed.

| Repository        | Relevant branch-new areas                                                                                 |
| ----------------- | --------------------------------------------------------------------------------------------------------- |
| `sqltoolsservice` | STS2 contracts/core/runtime/drivers/tests/docs                                                            |
| `vscode-mssql`    | Query Studio, SQL Data Plane, RowStore, query result leases/snapshots/transforms, per-feature diagnostics |
| `perftest`        | Query Studio scenarios, result-shape fixtures, central observability integration                          |

`main` is useful as a boundary check, but it does not contain the Query Studio architecture being extended. The `dev/query` implementation and the newest progress documents are therefore the source of truth.

Important documentation precedence:

- The current result grid is `FluentResultGrid`; older custom-grid decisions are historical.
- The chat-to-data result ownership work is implemented locally, not only proposed. `IQueryResultStore`, retained leases, pinned result documents, `streamRows`, read reasons, and the budgeted transform engine are available.
- Several reviewed design documents say Query Studio uses a strict CSP, but the current shared webview HTML does not emit a CSP meta tag. This is an implementation gap, not an available guarantee.

Primary local design sources:

- `coding-docs/ssms-query-docs/04-query-studio-master-design.reviewed.md`
- `coding-docs/ssms-query-docs/03-sts2-client-adapter-design.reviewed.md`
- `coding-docs/query-optimization/query_editor_results_execution.md`
- `coding-docs/query-optimization/EXECUTION_PLAN.md`
- `coding-docs/chat-to-data/chat_to_data_addendum.md`
- `coding-docs/chat-to-data/PROGRESS.md`
- `coding-docs/ssms-query-docs/chat_to_data.md`
- `coding-docs/how_to_use_perftest.md`

## 4. SSMS reference: preserve the workflow, replace the presentation

`screens/spatial.png` shows the old SSMS Spatial Results surface.

Useful behaviors to retain:

- Spatial results appear only when a result includes a spatial column.
- The user can choose the spatial column.
- An optional label column can be selected.
- Projection, zoom, and coordinate-grid context are visible concepts.
- The viewer works without an internet basemap.
- Spatial output is adjacent to the normal grid and messages, not a separate application.

Problems not to copy:

- The initial world extent leaves the actual data as tiny marks. The new viewer should fit the data once.
- Every feature is an undifferentiated black mark.
- A permanent form panel consumes substantial width.
- There is no feature hover, selection, details, source-row link, legend, or useful density handling.
- Loading, invalid geometry, partial result, and budget states are absent.
- The projection dropdown exposes implementation detail without explaining data compatibility.
- Keyboard focus, screen-reader output, high contrast, and reduced motion are not evident.

Modern translation:

- A full-width spatial canvas inside the result pane.
- A compact toolbar with result set, spatial column, optional label, Fit, Layers, and More controls.
- Automatic fit with padding and a sensible maximum zoom for a single point.
- A contextual inspector only after selection, not a permanent settings sidebar.
- Clear status such as `12,450 features shown | 8 skipped | SRID 4326 | Offline`.
- Source row identity and an action to reveal the row in Results.
- A synchronized feature list for keyboard navigation and nonvisual access.

## 5. Goals and non-goals

### 5.1 Goals

| ID      | Goal                                                                                                                                 |
| ------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| GEO-G1  | Render native SQL Server `geometry` and `geography` result cells without requiring users to rewrite the query.                       |
| GEO-G2  | Work fully offline with no failed or attempted network calls.                                                                        |
| GEO-G3  | Keep query execution, STS2 credit/backpressure, RowStore limits, and grid scrolling behavior unchanged when Spatial is never opened. |
| GEO-G4  | Keep all preparation bounded by feature, vertex, encoded-byte, decoded-byte, time, and cancellation budgets.                         |
| GEO-G5  | Be honest about null, empty, invalid, unsupported, truncated, corrupt, canceled, and budget-limited data.                            |
| GEO-G6  | Support both geodetic data and arbitrary planar coordinates without pretending unknown geometry belongs on a world map.              |
| GEO-G7  | Use VS Code theme, localization, keyboard, high-contrast, reduced-motion, and focus conventions.                                     |
| GEO-G8  | Preserve source result set, row ordinal, spatial column, and optional label for every rendered feature.                              |
| GEO-G9  | Fit the existing live and pinned result ownership model rather than creating a second result cache.                                  |
| GEO-G10 | Add registry-first, value-free diagnostics and perftest coverage across service, extension host, RPC, and first paint.               |

### 5.2 Non-goals for the first product slice

- Editing geometries or writing changes back to SQL Server.
- A general-purpose GIS workbench.
- Satellite imagery, streets, geocoding, routing, address search, or location services.
- 3D terrain, globe, point cloud, heatmap, extrusion, or animation features.
- Arbitrary workspace-provided script/style execution.
- Automatic query rewriting to call `STAsText()`, `STAsBinary()`, or `STSrid`.
- Silent geometry repair, `MakeValid()`, simplification, reprojection, or sampling that changes the apparent data without disclosure.
- Image, GeoJSON, KML, or shapefile export in the first slice.
- Inferring spatial semantics from arbitrary string/binary columns in the first slice.

## 6. Current result architecture inventory

### 6.1 End-to-end flow

```text
SQL Server
  -> Microsoft.Data.SqlClient SqlDataReader
  -> STS2 SqlClient driver
  -> driver.queryEvent / v2/query.rows (forward-only, credited pages)
  -> vscode-mssql Sts2Backend / SQL Data Plane
  -> ExecutionOrchestrator sink
  -> extension-host RowStore / IQueryResultStore lease
  -> bounded result-source reads
  -> Query Studio or pinned-results controller RPC
  -> Query Studio webview
  -> FluentResultGrid / text / plan / proposed Spatial view
```

Binding ownership rules already established by the branch:

- STS2 owns connection state, execution ordering, result metadata/pages, messages, credit, cancel, and terminal state.
- STS2 is forward-only and is not a random-access result cache.
- Query Studio's extension host owns RowStore memory, spill, random access, result snapshots, exports, and secondary result consumers.
- Rows never belong in coarse `QsState`; the webview pulls bounded windows.
- A secondary scan must not promote its pages into the viewport-protected cache.
- UI, plots, notebooks, transforms, and AI access should consume the shared query result layer rather than author separate row loops.

### 6.2 `sqltoolsservice` inventory

| Area                            | Current behavior                                                                                                      | Spatial implication                                                                                          |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `SqlClientSession.cs:121-215`   | Uses `SequentialAccess`, reads metadata, streams pages, and preserves `DataTypeName` in `ColumnInfo.EngineType`.      | `geometry`/`geography` eligibility is discoverable, but the value path is not specialized.                   |
| `SqlLargeValueReader.cs:35+`    | Special handling is limited to large text/binary columns.                                                             | Spatial UDT values fall through to ordinary `GetValue`.                                                      |
| `WireValueEncoder.cs:24-116`    | Bounds only `string` and `byte[]`; common types get tagged wrappers; unknown provider objects use `Convert.ToString`. | Spatial values have no guaranteed format/SRID and provider objects can bypass `maxCellBytes`.                |
| `SqlRowsPageBuilder.cs:65+`     | Estimates known scalar/string/binary sizes; unknown objects receive a small fixed estimate.                           | Complex spatial objects can defeat `pageBytes` accounting.                                                   |
| `DriverEffectRunner.cs:401-590` | Encodes credited pages and can emit compact rows with `compact.values` and type hints.                                | Spatial gets generic `string` hints today.                                                                   |
| `CaptureElision.cs:49-77`       | Digest capture replaces top-level `rows`.                                                                             | It does not replace `compact` or `compact.values`; Query Studio compact row values can be journaled in full. |
| `Sts2Defaults.cs:9+`            | Defaults include 1,000 page rows, 256 KiB page bytes, 1 MiB cell bytes, and four unacked pages.                       | Spatial encoding must honor the same bounded model and actual byte accounting.                               |

Legacy STS evidence is relevant but should not define the new public contract:

- Legacy query execution deliberately treats spatial UDTs as bytes instead of loading arbitrary UDT assemblies.
- `DataTypeTests.GeometryTypeTest` expects SQL Server native serialized geometry bytes as hex.
- Those proprietary bytes can be converted to OGC WKB using `Microsoft.SqlServer.Types`, but the conversion must be tested on every supported runtime identifier.

### 6.3 `vscode-mssql` inventory

| Area                                                            | Current behavior                                                                                                                                                                        | Recommended spatial insertion                                                                                                                            |
| --------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `queryStudioEditorProvider.ts:72-169`                           | One shared document model per URI; one controller per panel; split panels supported.                                                                                                    | Keep camera/tool state panel-local and result data model-shared.                                                                                         |
| `queryStudioController.ts:112-135, 499-550`                     | Coarse state is throttled and row-free; row notifications are count-only.                                                                                                               | Keep geometry values out; expose a run-lifetime generation while model, live-store, and pinned-snapshot identities remain distinct and controller-owned. |
| `sharedInterfaces/queryStudio.ts:125-145, 234-250`              | Result columns carry name, display name, SQL type, XML/JSON flags.                                                                                                                      | Add stable spatial kind/encoding metadata and a run-lifetime generation distinct from model source ID and pinned snapshot ID.                            |
| `services/sts2/sts2Backend.ts:154-164, 742-845`                 | Engine type maps to SQL type; spatial currently maps to generic string hint; sink acceptance gates ack.                                                                                 | Decode the negotiated spatial wire tag into a backend-neutral compact tag without breaking ack behavior.                                                 |
| `queryStudio/rowStore.ts:6-24, 37-82, 342-554`                  | Bounded memory/spill, async spill queue, protected/probationary caches, window projection.                                                                                              | Store the compact spatial tag unchanged; add `spatial` read reason and sparse projection if justified.                                                   |
| `queryResults/queryResultTypes.ts:48-120`                       | `IQueryResultStore` supports windows, streams, leases, summaries, and explicit read reasons.                                                                                            | This is the spatial preparation source.                                                                                                                  |
| `queryResults/queryResultAccessService.ts:419-554`              | Public `getWindow` access is snapshot-oriented; live-store ownership remains behind the model/controller, while shared transform readers already establish secondary-consumer patterns. | Put a controller-bound live/pinned adapter and budgeted preparation in `queryResults/spatial/**`, not `ExecutionHost` or React.                          |
| `QueryStudio/app.tsx:101, 1317-1379, 1639-1813`                 | Local sibling tabs for Results, Messages, and Query Plan.                                                                                                                               | Add a conditional `spatial` sibling tab and include it in fill/resize logic.                                                                             |
| `QueryStudio/results.tsx` / `resultsGrid.tsx`                   | Shared Fluent grid with lazy mounting and bounded reads.                                                                                                                                | Add a grid-caption action that opens Spatial for the selected set/column.                                                                                |
| `QueryResultsSnapshot/app.tsx` and `pinnedResultsController.ts` | Pinned results reuse Query Studio result components over frozen result sources.                                                                                                         | Use a small shared spatial data-source adapter so pinned support does not fork the viewer.                                                               |
| `scripts/bundle-webviews.js:14-73`                              | ESM esbuild with splitting; explicit Monaco worker entry exists.                                                                                                                        | Lazy import the viewer and add an explicit worker entry only if the spike proves it useful.                                                              |
| `webviewBaseController.ts:239-270`                              | Local module bundle gets a nonce; no CSP meta is emitted.                                                                                                                               | Add a real CSP prerequisite. Do not make remote tile access depend on today's open policy.                                                               |

The extension currently has no direct MapLibre, OpenLayers, Leaflet, deck.gl, Turf, Proj4, WKT, or WKB dependency.

### 6.4 `perftest` inventory

The `dev/query` branch already has a reusable Query Studio scenario family and deterministic result shapes:

- 10k normal rows.
- 100k narrow rows.
- 1,000 x 300 wide results.
- Large cells.
- 10k messages.
- 100 result sets.
- Registered service/extension/window/RPC/render markers.
- Independent extension-host and webview proofs.

There are no spatial SQL fixtures or spatial renderer probes today. New scenarios can follow the existing shape-family conventions: exploratory first, registered markers only, no sleeps, row/feature guarded completion, and no result values in markers.

## 7. Blocking gaps and prerequisite fixes

### 7.1 P0: compact row capture leaks result values

Product composition sets row capture to digest, but `CaptureElision` currently elides only the top-level `rows` property. Query Studio opts into compact rows, whose values are under `compact.values`. Those values can therefore enter STS2 journals in full.

This is a prerequisite independent of the spatial feature:

1. Elide the complete `compact` payload before journaling/digest computation, including `values`, `nullBitmap`, and type hints. Null patterns are result data too.
2. Restore it only at the existing wire/effect edge.
3. Add canaries for normal compact rows and spatial compact rows.
4. Verify journal, replay export, diagnostic export, and failure paths.
5. Ensure digest/replay identity remains correct.

Do not add WKB coordinates to compact rows until this is fixed and tested.

### 7.2 P0: no canonical bounded spatial cell

Today a spatial value may become a generic provider string such as WKT, or provider/native bytes depending on provider/runtime behavior. The contract does not state:

- `geometry` versus `geography` at the cell level.
- SRID.
- WKT, WKB, SQL native binary, or another encoding.
- Z/M dimensionality.
- curved-shape approximation.
- validity, empty, or `FullGlobe` status.
- honest byte length and truncation.

A renderer cannot safely infer these fields from `String(value)`.

### 7.3 P0: spatial values can defeat cell, page, and frame bounds

- Unknown provider objects bypass the string/byte `maxCellBytes` branches.
- Page accounting can estimate a large provider object as a few bytes.
- A truncated WKT or WKB prefix is not a valid geometry and must not be passed to a parser.
- The current page builder permits one row larger than `pageBytes`.
- Multiple individually valid cells can produce a row/message larger than the 64 MiB transport frame ceiling.

Oversized spatial values need a complete non-renderable sentinel with a known source byte count and source digest when those can be computed. Never send a partial WKB value and pretend it is a feature. The row/page pipeline also needs a final UTF-8 JSON-RPC frame measurement before send. If a complete row cannot fit, fail with a stable typed row-too-large outcome before transport rather than dropping cells/rows or relying on a framing failure.

Byte terms used by this design:

| Term             | Required meaning                                                                                         |
| ---------------- | -------------------------------------------------------------------------------------------------------- |
| `sourceBytes`    | Exact proprietary SQL native UDT bytes read from the provider, when the provider supports a byte stream. |
| `sourceDigest`   | SHA-256 of those exact native bytes. It is not a digest of normalized WKB.                               |
| `wkbBytes`       | Raw normalized WKB byte length before base64.                                                            |
| `wireValueBytes` | UTF-8 byte length of the complete tagged cell JSON, including field names, base64 expansion, and quotes. |
| `pageBytes`      | Exact UTF-8 byte length of the encoded row values and wrappers in a page.                                |
| `frameBytes`     | UTF-8 byte length of the complete JSON-RPC message/envelope checked against `MaxFrameBytes`.             |

For MVP, require both native source bytes (when known) and raw WKB to fit the existing effective `maxCellBytes`. Page and frame accounting use the complete wire representation and exact UTF-8 byte counts. This likely requires encoding a cell before page construction or sharing a single encoded representation between the page builder and writer; the current build-then-wire layering cannot promise exact wrapper bytes.

The current `maxCellBytes` request is lower-only. Query Studio cannot raise the service's 1 MiB ceiling. Treat spatial cells above that ceiling as unsupported in MVP even when the aggregate viewer budget is larger. A separate higher spatial ceiling is a later protocol/config decision that requires memory and frame evidence.

### 7.4 P0: exact provider recognition

Do not recognize arbitrary CLR UDTs by suffix or `Convert.ToString`. The SqlClient driver needs a supported, case-insensitive identity check for SQL Server's two system spatial types and must explicitly exclude aliases/custom CLR UDTs. `EngineType` alone may be insufficient; Phase 0 must determine whether `DbColumn.DataType`, `UdtAssemblyQualifiedName`, or another SqlClient metadata field is needed, then keep that provider identity internal to the SqlClient driver.

### 7.5 P0 research: actual provider/RID behavior

Before the wire shape is frozen, run an engine matrix on supported Windows, Linux, and macOS RIDs and SQL Server/Azure SQL versions:

- `SqlDataReader.GetValue` and `GetSqlValue` CLR types.
- `GetBytes` behavior for `geometry` and `geography` under `SequentialAccess`.
- Null and empty values.
- Points, lines, polygons, multis, and collections.
- Invalid geometries.
- Z, M, and ZM values.
- CircularString, CompoundCurve, and CurvePolygon.
- `FullGlobe`, larger-than-hemisphere geography, poles, and antimeridian crossing.
- Very large cells and cancellation while reading/draining them.
- Conversion latency for bounded but complex values.
- Cancellation/timeout behavior during synchronous `Microsoft.SqlServer.Types` deserialization and `STAsBinary()` conversion, not only during `GetBytes` chunks.

`Microsoft.SqlServer.Types` is already present elsewhere through DacFx, but a direct STS2 SqlClient-driver dependency needs explicit dependency-matrix and cross-RID approval.

### 7.6 P0: all tagged-value consumers need an approved display contract

A new `$t: "spatial"` value is not isolated to the map. Audit and test:

- Grid display, copy, sort, and filter.
- Text view.
- CSV/JSON/INSERT result export.
- Cell document open.
- RowStore spill and restore.
- Retained snapshots and pinned documents.
- Transform engine comparison/projection.
- Query-result AI/tool serialization and budgets.
- Debug capture, replay, diagnostics, and privacy canaries.

The spatial feature must not silently change ordinary result display/export semantics. This is a contract blocker, not a cleanup task: the current generic wrapper path would show base64 WKB, and the unrenderable sentinel would degrade to raw JSON or `[object Object]`. Define a discriminated renderable/unrenderable union plus spatial-aware display, copy, text, cell-document, export, transform, and tool behavior before the tag ships. If the wire carries a human display preview, it must be independently bounded and included in wire/page/frame byte accounting.

## 8. Spatial representation options

| Option                                                      | Advantages                                                                         | Problems                                                                                                | Decision                             |
| ----------------------------------------------------------- | ---------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- | ------------------------------------ |
| Provider `ToString()` / current wrapper                     | No new contract                                                                    | Format and type are not guaranteed; loses SRID; can bypass bounds; parsing extended SQL WKT is fragile  | Reject                               |
| Rewrite the user's query with `.STAsBinary()` and `.STSrid` | Server performs conversion                                                         | Unsafe/complex for arbitrary batches, aliases, expressions, multiple sets, permissions, and semantics   | Reject                               |
| SQL Server native serialized bytes                          | Lossless, includes SQL-specific forms                                              | Proprietary; requires SQL Server parser in every client; not a provider-neutral Data Plane contract     | Keep only as driver input            |
| WKT plus SRID                                               | Human readable; OpenLayers can parse it                                            | Larger, slower to parse, expensive to duplicate for display, invalid if truncated, extended curves vary | Accept only as fallback/debug format |
| GeoJSON                                                     | Browser-ready and common                                                           | Verbose; weak SRID/Z/M semantics; conversion policy moves into service; not a canonical database value  | Derived UI format only               |
| OGC WKB plus metadata                                       | Compact, standard, library-neutral, binary-friendly, separates projection metadata | Curves/ZM/full-globe compatibility needs research; still needs SQL native conversion                    | **Recommended**                      |

SQL Server documents WKT and WKB as interchange forms for spatial values, and exposes SRID separately. See [SQL Server spatial data](https://learn.microsoft.com/en-us/sql/relational-databases/spatial/spatial-data-sql-server?view=sql-server-ver17), [geography construction and interchange](https://learn.microsoft.com/en-us/sql/relational-databases/spatial/create-construct-and-query-geography-instances?view=sql-server-ver17), and [`STAsBinary`](https://learn.microsoft.com/en-us/sql/t-sql/spatial-geography/stasbinary-geography-data-type?view=sql-server-ver17).

### 8.1 Proposed STS2 value

Names are provisional and must follow the STS2 contract/versioning process.

```json
{
  "$t": "spatial",
  "kind": "geography",
  "format": "wkb",
  "srid": 4326,
  "hasZ": false,
  "hasM": false,
  "v": "<base64 OGC WKB>"
}
```

Optional fidelity fields:

```json
{
  "empty": false,
  "approximated": false,
  "approximation": null,
  "sourceBytes": 143,
  "sourceDigest": "sha256:<native-byte-digest>",
  "wkbBytes": 121,
  "display": "POINT (-96.7 40.84)",
  "displayTruncated": false
}
```

Oversized/unrenderable value:

```json
{
  "$t": "spatial",
  "kind": "geometry",
  "status": "unrenderable",
  "reason": "maxCellBytes",
  "sourceBytes": 12345678,
  "sourceDigest": "sha256:<native-byte-digest>"
}
```

Rules:

- No partial WKB in an unrenderable sentinel.
- `srid` is per value because one SQL column can contain mixed SRIDs. `kind` is repeated for self-description even though a native result column cannot alternate between `geometry` and `geography`.
- `srid` is optional on an oversized sentinel. If conversion is intentionally skipped, do not parse an undocumented native prefix merely to recover it.
- `sourceDigest` identifies the exact native UDT byte stream. If a normalized-WKB digest is needed, give it a distinct name.
- The SqlClient driver may depend on `Microsoft.SqlServer.Types`; the provider-neutral abstraction and runtime may not expose `SqlGeometry`/`SqlGeography` types.
- Recognize only the exact SQL Server system spatial types using a supported SqlClient metadata identity.
- Read native UDT bytes incrementally under `SequentialAccess`, check cancellation between chunks, hash while draining, and convert only bounded values. Phase 0 must also bound/measure the non-cancelable synchronous conversion step.
- Recheck the converted WKB size before emitting it.
- Measure the complete tagged UTF-8 wire value, page, and final frame as defined in section 7.3.
- Advertise a boolean service capability such as `spatialWkbV1`. Because STS2 does not retain client initialize capabilities to gate later values, add an explicit per-execute `spatialEncoding: "wkb-v1"` option and propagate it through command validation, reducer normalization, journaled effect arguments, and the driver/runtime path. Alternatively make an unconditional preview-spec revision, but do not call initialize advertisement alone negotiation.
- Old clients that do not opt in retain safe prior behavior. Query Studio enables the option only after the service capability is observed.
- Standard WKB is initially 2D display data. Preserve Z/M flags and do not imply that elevation or measure is rendered.
- A bounded `display` value is optional. Spatial-aware consumers must never fall through to generic object/base64 display; its exact ordinary-grid/export policy is part of the Phase 1 contract.

### 8.2 Curves and SQL-specific geography

OpenLayers WKB support does not by itself guarantee SQL Server extended spatial fidelity. SQL Server exposes `CurveToLineWithTolerance` for a declared polygonal approximation, but silently applying it would change the displayed geometry.

There is a second, more fundamental geography issue: ordinary SQL Server `geography` LineString and Polygon edges are short great-elliptic arcs, while a normal OpenLayers vector geometry connects projected WKB vertices with straight segments. A two-vertex geography line can therefore render incorrectly even when it contains no CircularString. SQL Server documents this difference in its [spatial data types overview](https://learn.microsoft.com/en-us/sql/relational-databases/spatial/spatial-data-types-overview?view=sql-server-ver17).

Initial policy recommendation:

- Standard OGC geometry point/line/polygon/multi/collection shapes are required.
- Geography Point/MultiPoint can use their coordinates directly. Geography lines/polygons/collections require one of: an exact compatible renderer, geodesic densification with a declared ellipsoid/tolerance and vertex budget, or an explicit MVP restriction to points. Phase 0 must choose; straight projected chords are not acceptable.
- Curves, `FullGlobe`, and parser-incompatible extended forms are a research gate.
- If curves are approximated, the payload must carry `approximated: true`, the tolerance/mode, and the UI must disclose the count.
- If geography edges are densified, carry distinct geodesic approximation metadata and count the generated vertices against the viewer budget.
- If a bounded, predictable approximation is not available, return an honest unsupported cell rather than a wrong shape.
- Never call `MakeValid()` or otherwise repair a value silently.

## 9. Renderer and library options

| Option              | Strengths                                                                                                                                                               | Weaknesses for this feature                                                                                                                                       | Recommendation                                         |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| OpenLayers          | Offline/no-layer maps; planar and custom projections; WKB/WKT/GeoJSON readers; Canvas and WebGL options; picking and keyboard map navigation; modular ESM; BSD-2-Clause | Styling is lower-level than a hosted map SDK; SQL geography edges are not automatically preserved; very large mixed geometry and worker strategy need measurement | **Preferred first spike and likely MVP**               |
| MapLibre GL JS      | Modern GPU rendering, excellent vector/raster basemap ecosystem, styling, clustering, terrain                                                                           | Primarily cartographic longitude/latitude workflow; strict-CSP worker setup; less natural for arbitrary `geometry` SRID 0; spatial parsing still needed           | Strong option if online/basemap-first scope wins later |
| deck.gl             | Excellent GPU layers, picking, binary/large-data paths, 3D extensions                                                                                                   | It is a visualization layer rather than the complete projection/map/data parser; likely needs another map/parser dependency                                       | Future high-scale overlay, not MVP                     |
| Leaflet             | Very popular, small mental model, accessible DOM controls, broad plugin ecosystem                                                                                       | SVG/Canvas performance ceiling; projection and WKB support often need plugins; less suitable for complex/high-volume native SQL spatial data                      | Acceptable simple fallback, not preferred              |
| Custom Canvas/WebGL | Full control and potentially small narrow bundle                                                                                                                        | Reimplements projection, topology, hit testing, zoom/pan, styling, labels, accessibility, high-DPI, and browser fallbacks                                         | Reject                                                 |

Why OpenLayers currently fits best:

- A map may have no layers, so offline result rendering does not require a tile provider.
- Its [WKB reader](https://openlayers.org/en/latest/apidoc/module-ol_format_WKB-WKB.html) reads WKB/EWKB and supports projection options.
- Its projection API supports built-ins, custom projection objects, and optional Proj4 registration. See the [Projection API](https://openlayers.org/en/latest/apidoc/module-ol_proj_Projection-Projection.html) and [Proj4 integration](https://openlayers.org/en/latest/apidoc/module-ol_proj_proj4.html).
- The [Map API](https://openlayers.org/en/latest/apidoc/module-ol_Map-Map.html) documents focus/keyboard requirements and allows a map with no tile source.
- It offers Canvas vector rendering plus WebGL examples for large point/vector layers.
- The project is BSD-2-Clause and supports module-level imports. See the [OpenLayers repository](https://github.com/openlayers/openlayers).

MapLibre remains a credible alternate if the product becomes a hosted-map experience. Its official docs describe WebGL vector/raster maps, GeoJSON sources, and the separate strict-CSP worker bundle: [MapLibre GL JS docs](https://maplibre.org/maplibre-gl-js/docs/) and [source specification](https://maplibre.org/maplibre-style-spec/sources/).

Dependency policy:

1. Add only `ol` for the first spike/MVP.
2. Import exact modules, not a broad convenience bundle.
3. Lazy-load the Spatial component and renderer chunk only on first tab activation.
4. Bundle all code, CSS, fonts, workers, and default assets locally. No CDN.
5. Use an explicit worker entry only if a benchmark proves off-main-thread parsing is worth the transfer/complexity cost.
6. Do not add Turf, Proj4, deck.gl, MapLibre, or a SQL-spatial JavaScript parser without a measured requirement.
7. Record production minified/compressed chunk size and update third-party notices before approval.

## 10. Recommended architecture

### 10.1 Data flow

```text
SqlDataReader geometry/geography cell
  -> SqlClientSpatialValueReader
       bounded native-byte read, cancellation, source digest
       Microsoft.SqlServer.Types conversion to WKB + SRID
  -> provider-neutral DriverSpatialValue
  -> WireValueEncoder spatial tag
  -> ordinary credited STS2 row/compact page
  -> Sts2Backend SpatialCellEncoding + spatial type hint
  -> RowStore / ResultStoreLease (unchanged storage ownership)
  -> controller-bound SpatialReadSource + retained store lease
  -> SpatialResultService projected getWindow loop
       cancellation, row/wire-byte/time budgets
  -> pull/acknowledged bounded SpatialFeatureChunk RPC
  -> optional decoder worker / incremental scheduler
       WKB/geodesic decode, vertex/decoded-memory budgets
  -> shared SpatialResultsPane
  -> OpenLayers source/layers + synchronized DOM feature list
```

There is no new database/service request method for spatial results and no second authoritative raw-row cache. Bounded, lifecycle-scoped derived preparation/render state is allowed.

### 10.2 Ownership boundaries

| Component                 | Owns                                                                                                                                             | Must not own                                                                    |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------- |
| STS2 SqlClient driver     | Exact SQL system-type recognition, bounded reading, canonical WKB conversion, source fidelity/byte fields                                        | UI styles, map projections, basemaps, feature limits                            |
| STS2 runtime/wire         | Tagged encoding, byte accounting, capability/version, privacy-safe capture                                                                       | SQL provider types in public abstractions                                       |
| SQL Data Plane            | Backend-neutral spatial tag and column capability                                                                                                | Map library types or STS2 DTO leakage                                           |
| RowStore / result store   | Immutable compact values, spill, leases, random access                                                                                           | Parsed OpenLayers features or GPU data                                          |
| SpatialResultService      | Controller-bound lease, projected result scan, cancellation, source-row/total-wire-byte/time/per-response budgets, chunks, observed host summary | React state, map camera, tile provider credentials, claims about unscanned rows |
| Decoder/adapter           | WKB/geodesic parse, geometry/vertex validation, decoded-memory/render-time budgets, render feature conversion, observed decoder summary          | Full result rows or persistent authoritative cache                              |
| SpatialResultsPane        | Selection, camera, layers, theme, accessible list/details, source-row reveal                                                                     | Authoritative result storage or unbounded scans                                 |
| Online map provider layer | Explicit tile/style fetch, attribution, cache/credentials policy                                                                                 | Automatic enablement or raw query-result telemetry                              |

### 10.3 Query result service integration

Add `"spatial"` to `RowReadReason`. It follows the existing scan behavior:

- no protected-cache promotion;
- cooperative chunking/yield;
- cancellation between windows;
- frozen row-count clamp for snapshots;
- diagnostics contain only aggregate counts and timings.

Prefer a reusable service under `extensions/mssql/src/queryResults/spatial/**`. The webview must not supply a `sourceId`, `storeId`, or snapshot ID as lookup authority. Each controller opens an internal source bound to the Query Studio model or pinned document it already owns:

```ts
interface SpatialReadSource {
  openSpatialSession(request: SpatialOpenRequest): Promise<SpatialOpenResult>;
}

interface SpatialOpenRequest {
  resultSetId: string;
  spatialColumn: number;
  labelColumn?: number;
  hostBudget: SpatialHostBudget;
}

interface SpatialOpenResult {
  handle: string;
  generation: string;
  frozenSummary: SpatialResultSetSummary;
}

interface SpatialFeatureChunk {
  handle: string;
  generation: string;
  sequence: number;
  rowStart: number;
  features: SpatialSourceFeature[];
  progress: SpatialPrepareProgress;
  encodedBytes: number;
  done: boolean;
}

interface SpatialSourceFeature {
  sourceRow: number;
  spatial: SpatialCellEncoding;
  label?: string;
}
```

MVP uses pull-based `open` -> `next` -> `cancel` RPC:

- The controller resolves its current live store or pinned snapshot internally and acquires a `QueryResultStoreLease` for a new `spatialView` owner (or a precisely equivalent transient owner).
- `open` returns only an opaque handle, generation, and frozen summary.
- At most one `next` request is in flight per handle. Receipt of the next request is the backpressure/consumption boundary; host notifications are not used for feature data.
- Every chunk has a monotonically increasing sequence and adaptive per-response UTF-8 encoded-byte cap, including WKB base64, labels, wrapper metadata, and JSON-RPC overhead.
- `cancel` is idempotent. Handles have an expiry, per-controller/global concurrency cap, and bounded maximum count.
- Generation mismatch, rerun, hide, dispose, or lease loss closes the handle and rejects stale chunks.
- Live rerun cannot dispose a store mid-scan because the spatial session owns its lease; cancellation releases it promptly.
- The host final summary reports every reason observed in the scanned prefix, not facts about unscanned rows.
- The decoder returns its vertex/decoded-memory/invalid/approximation summary; the webview merges host and decoder summaries for display without treating either as knowledge of unscanned rows.

The label is the only nonspatial field in preparation. Clamp it per cell and include it in both per-response and total RPC-byte budgets. Fetch all other result fields on demand after selection.

`IQueryResultStore.streamRows()` is not projected today; it always reads all columns. The existing `getWindow` path supports one contiguous column range. Spatial plus a distant label column should not force hundreds of unrelated cells across RPC. Options, in preference order:

1. Extend `RowStreamRequest`/`CellWindowRequest` with a general sparse projection (`columnOrdinals`) and implement it through RowStore, retained stores, derived snapshots, and tests.
2. For MVP, use a budgeted `getWindow` loop with two aligned one-column reads and join by source row in `SpatialResultService`.
3. Pull one contiguous span only for narrow results below a measured threshold.

Do not add a spatial-only raw page loop in `QueryStudioController`.

### 10.4 Complete-result-first lifecycle

Recommended first-slice behavior:

1. Spatial eligibility is derived in the webview from stable `QsResultColumn` spatial metadata; no duplicate eligibility list is added to coarse state.
2. While that result set is executing, the tab may be visible but does not scan rows.
3. Preparation is enabled only after an authoritative terminal `execution.kind` and a stable `store.summary(resultSetId)`/frozen high-water state. Do not use `results.streaming`; it is false during `cancelRequested` before terminal state.
4. Test the cancel-request-to-terminal gap, connection loss, terminal error, row cap, and corrupt/short store explicitly.
5. Terminal partial sets render available complete cells with a visible partial banner and counts.
6. Opening starts a bounded preparation session and acquires its store lease.
7. Chunks are parsed and committed incrementally so first paint does not wait for the full cap.
8. Auto-fit occurs once after an initial meaningful chunk. Later chunks do not move a user-controlled viewport.
9. Rerun, source disposal, result-column change, tab close, panel hide, or handle expiry cancels preparation and invalidates stale chunks.

This avoids adding map work to query execution and greatly simplifies stale/partial semantics. Progressive viewing while a query is still streaming is a later milestone.

## 11. UX design

### 11.1 Result tab model

Current:

```text
Results | Messages | Query Plan
```

Proposed when eligible:

```text
Results | Spatial | Messages | Query Plan
```

Rules:

- Hide Spatial if there are no eligible non-plan result sets.
- Spatial never auto-opens. Preserve the current switches to Messages for terminal errors/no-data and to Query Plan for plan runs.
- A per-result-grid map action opens Spatial with that result set and column selected.
- If one result set has one spatial column, preselect it.
- If there are multiple sets/columns, preserve the panel-local prior selection when still valid; otherwise select the first eligible pair deterministically.
- Keep grid/text as the existing Results view toggle. Spatial is not a third grid/text mode.
- Spatial fills the result pane and participates in splitter/maximize/resize behavior.

### 11.2 Layout

```text
+-----------------------------------------------------------------------+
| Results | Spatial | Messages | Query Plan                       [max]  |
+-----------------------------------------------------------------------+
| [Result 1] [SpatialLocation] [Label: None]  [Fit] [Layers] [More]     |
+-----------------------------------------------------------------------+
|                                                                       |
|                     full-width spatial canvas                         |
|                                                                       |
|                                      +------------------------------+ |
|                                      | selected feature details     | |
|                                      | Row 418 | Polygon | SRID ... | |
|                                      | [Reveal in Results]          | |
|                                      +------------------------------+ |
+-----------------------------------------------------------------------+
| 12,450 shown | 8 skipped | 250,311 vertices | SRID 4326 | Offline    |
+-----------------------------------------------------------------------+
```

The selected-feature detail region is a collapsible drawer or unframed pane, not a permanent card. The accessible feature list can share this region behind `Features` and `Details` tabs or use a resizable lower pane.

### 11.3 MVP controls

| Control                 | Behavior                                                                                            |
| ----------------------- | --------------------------------------------------------------------------------------------------- |
| Result set selector     | Lists only eligible result sets with stable ordinal/row count.                                      |
| Spatial column selector | Lists metadata-confirmed `geometry`/`geography` columns.                                            |
| Label column selector   | Optional; default None; label is used in selection/details and selectively on the map.              |
| Fit                     | Fits all currently prepared features with padding; never silently changes selection.                |
| Layers                  | Offline context/grid switches; online providers appear only if explicitly configured and consented. |
| More                    | Coordinate mode/SRID info, show feature list, copy selected summary, diagnostics-safe status.       |
| Zoom controls           | Familiar icon buttons with tooltips and keyboard equivalents.                                       |

Do not expose color-by, arbitrary tooltips, measure, edit, heatmap, or extrusion controls until the base interaction is complete.

### 11.4 Feature styling and interaction

- Points use stable screen-space radii with a selected outline.
- Lines have a minimum pixel width and selected halo.
- Polygons use translucent fill plus opaque boundary, preserving holes.
- Collections keep one source-row identity; components may be styled by geometry type.
- Null/empty/unrenderable cells are not drawn and are counted separately.
- Hover may show row, label, type, and SRID. It must not be the only way to inspect a feature.
- Click/Enter selects and opens persistent details.
- Details fetch additional source-row fields on demand; do not attach an entire result row to every feature.
- Spatial maps the complete bounded source result in source-row order. MVP does not silently inherit the grid's webview-local sort/filter as a map transform.
- Add an async grid handle such as `revealSourceRow`/`selectCell`: switch to Results, mount the lazy grid, map source ordinal to current display row, scroll, select, and focus. If a filter excludes the row, preserve the filter and offer `Clear filter and reveal`; do not silently clear it.
- Spatial selection updates `QueryResultContextService` with a source-row identity/spatial selection kind. It must not report a display row/cell until the grid mapping succeeds.
- Labels are off by default for dense data. Show the selected label and optionally collision-managed labels at suitable zoom.
- Initial auto-fit has a maximum zoom for one/few points.
- Mouse-wheel zoom activates only while the map is focused so it does not unexpectedly trap results-pane scrolling.

### 11.5 Loading and truth states

The UI must distinguish:

| State                           | Required behavior                                                                                                               |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Preparing                       | Progress count; prior map cleared or explicitly marked stale.                                                                   |
| Complete full scan              | Exact shown/null/empty/invalid/unsupported counts available for all source rows.                                                |
| Terminal partial query          | Persistent warning with query truncation/cancel/error reason.                                                                   |
| Feature/row budget reached      | `Showing N features from the first R of T rows; remaining feature count unknown`; skip counts are explicitly `in scanned rows`. |
| Vertex/byte/time budget reached | Keep valid prepared features and show the reason.                                                                               |
| Mixed SRIDs                     | Do not overlay incompatible groups silently; require group selection or show separate layers only when transforms are known.    |
| Unsupported shape               | Count and expose row-level reason in feature list.                                                                              |
| Renderer unavailable            | Keep feature list/details usable; offer Results rather than a blank canvas.                                                     |
| Offline                         | No error banner; Offline is the normal baseline mode.                                                                           |
| Online provider failure         | Result geometry remains; basemap failure is nonfatal and clearly separate.                                                      |

## 12. Geometry, geography, SRID, and projection policy

SQL Server distinguishes Euclidean `geometry` from round-earth `geography`. The viewer must preserve this distinction. See [SQL Server spatial type overview](https://learn.microsoft.com/en-us/sql/relational-databases/spatial/spatial-data-sql-server?view=sql-server-ver17).

Projection is not enough to preserve geography semantics. SQL Server connects ordinary geography vertices with short great-elliptic arcs, while an ordinary vector renderer connects projected vertices with straight segments. Until Phase 0 proves an exact/densified path, MVP must either support geography points only or label geography line/polygon output unsupported. If densification is selected, it must use the declared SRID/ellipsoid, a documented error tolerance, antimeridian/pole handling, cancellation, and the same decoded-vertex budget as other render geometry.

| Input                                          | Initial display policy                                                                                                        | Basemap policy                                       |
| ---------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| `geometry`, SRID 0/unknown                     | Native Cartesian coordinates; fit extent; coordinate grid with unknown/native units                                           | Disabled                                             |
| `geometry`, known EPSG 4326                    | Treat coordinates as declared WGS84 for optional geographic view; retain geometry semantics in details                        | Allowed only after explicit mode/provider enablement |
| `geometry`, known EPSG 3857                    | Native projected view; optional transform where supported                                                                     | Allowed after explicit enablement                    |
| Other `geometry` SRID                          | For supported linearized shapes, use native Cartesian coordinates; show SRID and any approximation; do not invent a transform | Disabled until transform is known                    |
| `geography`, SRID 4326 Point/MultiPoint        | Geographic coordinates; offline graticule/orientation layer; antimeridian-aware fit                                           | Optional online layer after consent                  |
| `geography`, SRID 4326 line/polygon/collection | Only after an approved geodesic render/densification path; otherwise unsupported in MVP                                       | Optional only after compatible render path           |
| Other `geography` SRID                         | Show SRID and use a conservative coordinate view until its reference definition is known                                      | Disabled by default                                  |
| Mixed SRIDs in one column                      | Group and disclose; do not combine in one coordinate space without proven transforms                                          | Disabled unless one selected group is compatible     |

SQL Server allows mixed SRIDs in a column, and `sys.spatial_reference_systems` exposes authority, reference WKT, units, and conversion information. See [`sys.spatial_reference_systems`](https://learn.microsoft.com/en-us/sql/relational-databases/system-catalog-views/sys-spatial-reference-systems-transact-sql?view=sql-server-ver17).

Initial projection support should stay small:

- Native Cartesian identity.
- EPSG:4326.
- EPSG:3857.
- Built-in transforms that OpenLayers already supports and that tests cover.

Do not add automatic internet lookup for projection definitions. Add Proj4 only after customer scenarios demonstrate a need, and source projection definitions through a reviewed offline/metadata path.

Coordinate-order tests are mandatory. SQL spatial X/Y and geographic longitude/latitude must map correctly through WKB, the renderer, pointer readout, and fit calculations.

## 13. Offline and online map strategy

### 13.1 Required offline baseline

Offline means zero network requests.

Every compatible result gets:

- Theme-aware background.
- Data extent and coordinate readout.
- Cartesian axes/grid for planar geometry.
- Graticule and scale context for geography.
- Fit, zoom, pan, selection, details, and feature list.
- Geometry layers rendered entirely from local query data.

Recommended optional bundled orientation asset:

- A generalized physical land/coastline layer at small scale, loaded only for compatible geographic views.
- Prefer physical outlines over political borders to avoid disputed-boundary product decisions.
- Natural Earth provides 1:110m vector data and states that its data is public domain: [downloads](https://www.naturalearthdata.com/downloads/) and [terms](https://www.naturalearthdata.com/about/terms-of-use/).
- Preconvert the approved source to a minimal local format at build time; do not add a runtime shapefile/TopoJSON dependency solely for this asset.
- Record source/version/transformation and update third-party notices even if attribution is not legally required.

The bundled orientation layer is desirable for a polished offline geography experience, but it must not block the first renderer/protocol vertical slice.

### 13.2 Online streets/satellite as a separate milestone

Online tiles reveal the viewed geographic area to a third party. Auto-fitting query results and then requesting tiles can reveal the approximate location contained in the result, even if no coordinates appear in extension telemetry.

Requirements before enabling any online provider:

1. Default off and no request before explicit user action/disclosure.
2. Provider allowlist and HTTPS only.
3. Required attribution visible and accessible.
4. Credentials in `SecretStorage`, never settings, RPC logs, URLs, telemetry, or diagnostics.
5. Decide direct webview requests versus an extension-host authenticated/caching proxy.
6. Provider terms, rate limits, cost, user agent, referer, caching, retention, and offline policies reviewed.
7. CSP `img-src`/`connect-src` restricted to approved hosts; no broad arbitrary workspace URL.
8. Workspace settings alone cannot silently enable data-derived network requests.
9. Basemap failure never removes or blocks result geometry.
10. Provider name/mode may be logged; tile URL, viewport, extent, and coordinates may not.

Do not hardcode the public `tile.openstreetmap.org` service as a product backend. Its [tile usage policy](https://operations.osmfoundation.org/policies/tiles/) requires attribution/caching and explicitly disallows bulk/offline use; it is not a commercial product SLA.

Satellite imagery should remain deferred until a supported provider and authentication model are selected. Azure Maps is one possible provider, but its map control/services require authentication and carry a separate SDK/service design; see [Azure Maps map control](https://learn.microsoft.com/en-us/azure/azure-maps/how-to-use-map-control) and [Web SDK practices](https://learn.microsoft.com/en-us/azure/azure-maps/web-sdk-best-practices).

## 14. Performance, bounds, and lifecycle

### 14.1 Non-negotiable invariants

- Zero spatial row reads and no renderer module evaluation if the tab is never opened.
- No regression to STS2 credit/ack, query completion, grid first paint, or viewport cache behavior.
- No whole-result copy into coarse webview state.
- Every scan is cancellable and tagged `reason: "spatial"`.
- Every host and webview payload is bounded.
- No invalid partial WKB.
- A background scan never promotes pages into the grid's protected cache.
- Hidden/disposed panels release preparation handles; inactive maps do not accumulate workers/GPU buffers indefinitely.
- Two panels over one model must not create unbounded duplicate host scans.

### 14.2 Seed budgets for the spike

These are starting values for measurement, not final product commitments. Register every knob in the existing query-results parameter registry rather than scattering constants.

| Budget                                               |                                     Spike seed | Behavior when reached                                                                         |
| ---------------------------------------------------- | ---------------------------------------------: | --------------------------------------------------------------------------------------------- |
| Host source rows                                     |                                         25,000 | Stop before next row; report scanned rows, not unknown remaining features                     |
| Host total serialized RPC bytes                      |                                         32 MiB | Stop pull; includes geometry, label, metadata, base64, and JSON overhead                      |
| Host per-response serialized bytes                   |                           2 MiB initial target | End the chunk before the next feature; still bounded by final frame safety                    |
| Label UTF-8 bytes per cell                           |                                          4 KiB | Send bounded preview plus truncation flag; full value remains available on selected-row fetch |
| Decoder vertices, including geodesic/curve expansion |                                        250,000 | Keep completed features; cancel further pulls and mark vertex budget                          |
| Decoder derived memory                               |                          64 MiB initial target | Stop before committing the next feature/batch; release on lifecycle transition                |
| Chunk rows                                           |                                      500-1,000 | Tune against spill and RPC measurements                                                       |
| Main-thread work slice                               |                                 <= 8 ms target | Yield between parse/commit batches                                                            |
| Prepared-result memory                               | Derive from encoded/decoded limits and measure | Dispose/rebuild, do not spill a second parsed cache in MVP                                    |

Host and decoder enforce different budgets. The host is authoritative for scanned source rows, serialized bytes, handle lifetime, and observed wire statuses. The decoder is authoritative for parsed geometry type, generated/render vertices, derived memory, invalid/approximation statuses, and render work. The UI merges them and labels all counts with their observed scope.

The 32 MiB total viewer budget does not raise STS2's current lower-only 1 MiB per-cell ceiling. Do not silently reservoir-sample or simplify in MVP. A deterministic prefix is imperfect but honest and source-row addressable. If sampling is later added, the method, seed, and shown/total semantics must be explicit.

### 14.3 Parsing and worker strategy

Two implementation candidates need a spike:

**A. Incremental main-thread parsing**

- Lazy import OpenLayers WKB reader.
- Parse small chunks.
- Yield with the existing scheduler/performance conventions.
- Avoid structured-clone/transfer duplication.
- Simpler integration; may be sufficient under the MVP cap.

**B. Dedicated browser worker**

- Add explicit `spatialWorker` esbuild entry using the proven Monaco worker pattern.
- Version messages by store ID, result set, selected column, and generation.
- Parse to cloneable/transferable plain geometry data, not OpenLayers class instances.
- Terminate or cancel on rerun/disposal.
- Requires CSP `worker-src` and careful transfer-size measurement.
- Add a worker-specific TypeScript configuration/lib strategy; the current webview config has DOM types but not WebWorker types.

Select a provisional A/B strategy in Phase 0 and implement it in Phase 3. Phase 4 revalidates and tunes it. Do not add a worker because maps conventionally have one.

For either strategy, inspect the esbuild metafile and packaged VSIX. Confirm dynamic JS chunks are not evaluated/loaded before activation and determine whether importing OpenLayers CSS from a lazy module merges it into eagerly loaded `queryStudio.css`; lazy JavaScript alone is not proof of zero unopened bundle cost.

### 14.4 Rendering tiers

Initial stable path:

- OpenLayers Canvas vector layer for bounded mixed geometries.
- Renderer fallback preserves the feature list/details when canvas/WebGL creation fails.
- No animation required for correctness.

Later measured tiers:

- OpenLayers WebGL point/vector layer for larger point sets.
- Point clustering with accessible cluster expansion semantics.
- View-dependent simplification that preserves an unsimplified source identity and discloses approximation.
- deck.gl only if a proven scale/3D requirement exceeds OpenLayers without adding unacceptable complexity.

### 14.5 Panel and result lifetime

- Camera, selected columns, open inspector, and layer choices are panel-local UI state.
- Distinguish model-lifetime source identity, run-lifetime generation/store identity, and pinned snapshot identity. Only the controller-bound source resolves them.
- A rerun invalidates prior work even when result-set IDs repeat. The spatial session lease keeps the old store alive only until cancellation/cleanup.
- Pinned sessions acquire their own spatial-view store lease through the pinned controller.
- Switching away from the Spatial tab cancels an in-flight host pull. A completed bounded parsed source may remain panel-local for fast return while the panel stays visible; the OpenLayers target is detached while inactive.
- Whole-panel hide is stronger: `panel.onDidChangeViewState` synchronously cancels/releases host handles even if the webview does not respond. The webview then terminates its worker, calls the selected OpenLayers detach/dispose path, and releases parsed/GPU state. Disposal and rerun follow the same idempotent cleanup.
- MVP has no shared host prepared cache or multicast. Enforce a small per-controller/global active-handle cap. Reconsider deduplication only with an explicit bounded cache, backpressure, reference-count, and lifetime design.

## 15. Accessibility and localization

A canvas/WebGL map cannot be the only interface to the result. W3C treats maps as complex images that need an equivalent textual/structured representation: [WAI complex images guidance](https://www.w3.org/WAI/tutorials/images/complex/).

### 15.1 Required accessible workflow

- All toolbar actions are native/Fluent DOM controls with accessible names and visible focus.
- The map target is focusable and has an accessible name/description.
- Arrow keys pan; `+`/`-` zoom; Fit and reset are reachable buttons/commands.
- Feature navigation is available through a virtualized DOM list/table keyed by source row.
- Each list item exposes label (if selected), geometry type, source row, SRID, and selected state.
- Virtualization retains logical focus/selection when items unmount, ensures the active item is mounted before focus, and exposes either correct `aria-setsize`/`aria-posinset` or paged table semantics. Provide keyboard next/previous, Home/End within the loaded set, and text search over bounded labels.
- Activating a list item selects/highlights/fits the feature.
- Map selection moves/announces the corresponding list selection without stealing focus unexpectedly.
- A polite live region announces preparation, first paint, skipped/partial counts, and selection summary.
- The normal Results grid remains the complete tabular alternative.
- `Reveal in Results` provides a direct path from spatial selection to the source row.
- Hover-only information is duplicated in persistent details.

### 15.2 Visual accessibility

- Use shape, outline, width, dash/pattern, and selection halo in addition to color.
- Derive colors from VS Code theme/chart tokens and verify light, dark, high-contrast, and high-contrast-light modes.
- Support forced colors.
- Respect `vscode-reduce-motion`, `prefers-reduced-motion`, and the VS Code screen-reader body class. No animated fly-to in reduced-motion mode.
- Keep controls usable at 200% zoom and narrow result-pane heights.
- Ensure labels, attribution, status, and controls never overlap.
- Use minimum target sizes and stable control dimensions.

VS Code's webview guide exposes screen-reader and reduced-motion classes and recommends a restrictive CSP: [Webview API guide](https://code.visualstudio.com/api/extension-guides/webview).

### 15.3 Tab semantics and localization

The current Query Studio tabs already use `tablist`, `tab`, and `aria-selected`, but their semantics and keyboard behavior are incomplete. When adding Spatial:

- Preserve the existing roles and add stable tab/panel IDs, `aria-controls`, `aria-labelledby`, and `role="tabpanel"` relationships.
- Add roving focus/arrow-key behavior.
- Design and integrate the F6/focus-region sequence; Query Studio does not currently have a complete F6 region model to preserve.
- Route every new string through the existing localization bundle from the first patch.
- Do not embed English geometry errors or provider messages directly in JSX.

Consider `@axe-core/playwright` as a test-only dependency if it passes repository dependency review; there is no current automated axe coverage.

## 16. Security and privacy

### 16.1 Result data

Spatial bytes, coordinates, labels, properties, extents, and source rows are result data.

- Never place them in diagnostics, telemetry, replay descriptors, perf marker attributes, status dumps, or error logs.
- RowStore spill remains the sole persistent result representation and follows its existing sensitive-data cleanup policy.
- The parsed/rendered map cache is memory-only and tied to the result/panel lifetime.
- Do not persist map screenshots, GeoJSON, or online tiles as part of debug export.
- Do not attach whole result rows as feature properties.
- Render labels/properties as text; never use untrusted HTML.
- Error messages expose type/status/counts, not raw WKT/WKB.

### 16.2 CSP hardening prerequisite

Current `WebviewBaseController` has no CSP meta despite the reviewed design requiring one. Before spatial ships, Query Studio and pinned-results surfaces need a tested policy. Global hardening of every extension webview should be tracked separately rather than made an implicit Spatial blocker.

1. Add a base CSP builder with per-surface directive hooks rather than one globally widened string.
2. Use `default-src 'none'`; allow ESM entry and dynamic chunks with `script-src ${webview.cspSource}`, and explicitly allow only the local style/image/font resources the surface needs.
3. Move or nonce the inline style and Query Studio boot-relay script correctly.
4. Add `${webview.cspSource}` to the minimal worker policy only if the worker design is selected.
5. Keep remote `connect-src`/`img-src` absent in offline mode.
6. Add provider hosts only to the Query Studio/pinned surface policy. CSP cannot be widened dynamically without recreating/reloading the document, so provider changes need an explicit reload flow.
7. Validate all style/tile configuration, schemes, and attribution text.
8. Test every existing webview entry if shared HTML/CSP code changes, plus Query Studio dynamic imports and optional worker.

The recommended implementation is a standalone CSP foundation patch plus surface-specific adoption, with Query Studio and pinned results required before the offline viewer ships.

### 16.3 Compact capture canaries

Add canary coordinates/labels that must not appear in:

- STS2 journal.
- Replay/export bundle.
- Extension diagnostics.
- Query Studio replay records.
- Perf markers.
- Webview perf mark payloads.

Test legacy `rows` and the entire `compact` payload, including values and null bitmap, across success/failure and normal/spatial tagged values.

## 17. Observability and perftest

### 17.1 Registry-first markers

Names are provisional; register them in the shared query-results observability contract before emitting them. Each name has one process/role. Do not emit a nominally identical marker from both host and webview.

| Marker                                         | Fixed role              | Safe persisted attributes                                                                         |
| ---------------------------------------------- | ----------------------- | ------------------------------------------------------------------------------------------------- |
| `mssql.queryResults.spatial.prepare.begin`     | Extension host start    | result-set-count bucket, source mode (`live`/`pinned`)                                            |
| `mssql.queryResults.spatial.prepare.end`       | Extension host end      | scanned-row/serialized-byte/feature buckets, terminal status, budget-reason enum, duration bucket |
| `mssql.queryResults.spatial.prepare.cancel`    | Extension host terminal | reason enum, scanned-row bucket                                                                   |
| `mssql.queryResults.spatial.render.begin`      | Webview start           | renderer mode, offline/allowlisted-provider ID                                                    |
| `mssql.queryResults.spatial.render.firstPaint` | Webview milestone       | rendered-feature/vertex buckets, partial boolean, duration bucket                                 |
| `mssql.queryResults.spatial.render.settled`    | Webview end             | rendered/skipped buckets, fallback mode, duration bucket                                          |
| `mssql.queryResults.spatial.render.cancel`     | Webview terminal        | reason enum only                                                                                  |

Persist only registered buckets/enums. Exact counts, durations, handle/generation IDs, and assertion state belong only in a `PERF_MODE` test probe that is unavailable in production and never feeds diagnostics or telemetry.

Never include:

- coordinates or bounds;
- WKT/WKB/GeoJSON;
- labels or selected property values;
- column, table, database, server, or query names;
- raw SRID combined with location data;
- tile URLs or credentials.

### 17.2 Measurements

Measure the pipeline separately:

```text
tab open
  -> first result-store chunk
  -> WKB parse
  -> first feature committed
  -> first accepted feature followed by OpenLayers `rendercomplete`
  -> bounded preparation complete
  -> render settled
```

Define first paint as an OpenLayers `rendercomplete` event after at least one accepted feature has been committed to the active generation. A requestAnimationFrame or component mount is not sufficient. Canvas-pixel/screenshot assertions are a separate end-to-end correctness proof.

The in-memory `PERF_MODE` probe may expose exact spill reads, cache behavior, encoded/decoded bytes, feature/vertex counts, skipped reasons, long tasks, renderer state, and generation-scoped assertions. Production markers remain bucketed and value-free. Existing query completion and grid render markers are the unopened non-regression baseline.

### 17.3 New deterministic fixtures/scenarios

Suggested SQL fixtures:

- 10k geography points at deterministic global/local coordinates.
- 100k geography points for capped/high-scale experiments.
- Mixed point/line/polygon/collection result.
- A few complex polygons with holes and a controlled vertex count.
- Geometry SRID 0 Cartesian data.
- 4326 and 3857 data.
- Mixed SRIDs.
- Null, empty, invalid, curves, Z/M, `FullGlobe`, and oversized cells.
- Multiple result sets and multiple spatial columns.

Suggested exploratory scenarios:

| Scenario                               | Measured end                            | Independent proofs                                                                        |
| -------------------------------------- | --------------------------------------- | ----------------------------------------------------------------------------------------- |
| `querystudio-spatial-10k-offline`      | First accepted-feature `rendercomplete` | Host probe scanned expected rows; webview probe accepted expected features and generation |
| `querystudio-spatial-complex-polygons` | Render settled                          | Expected vertex/feature counts; no invalid-budget lie                                     |
| `querystudio-spatial-budget`           | Honest partial state                    | Host budget reason and webview partial status agree                                       |
| `querystudio-spatial-rerun-cancel`     | New-run first paint                     | Old handle canceled; no stale feature appears                                             |
| `querystudio-spatial-pinned`           | Pinned first paint                      | Source editor can close while snapshot remains valid                                      |
| `querystudio-spatial-pan-select`       | Semantic probe end                      | Real pan/zoom/select seam and source-row selection proof                                  |

The current harness does not inject real renderer scrolling for its grid scenario and does not prove absence of webview network requests. Spatial interaction therefore needs a test-only semantic command/probe; zero-network offline proof stays in Playwright unless perftest gains a real request interceptor. Do not use sleeps.

### 17.4 Performance acceptance approach

Do not declare arbitrary official latency gates before collecting stable samples. Initial acceptance is:

- Existing Query Studio query/result scenarios show no material regression when Spatial is unopened.
- Spatial scenarios are exploratory and have independent correctness proofs.
- No unbounded allocation, long synchronous scan, or viewport-cache pollution.
- First paint is progressive and occurs before full bounded preparation for large inputs.
- Pan/zoom/select remains responsive at the supported feature/vertex cap.
- Scenario eligibility graduates only after environment-stable baselines exist.

## 18. Test plan

### 18.1 `sqltoolsservice`

- `WireValueEncoderTests`: exact SQL `geometry`/`geography` recognition, exclusion of aliases/custom CLR UDTs, per-cell kind/SRID, null/empty, deterministic WKB, unrenderable sentinel, no partial WKB.
- New spatial reader unit tests: native serialization fixtures, chunk boundaries, synchronous conversion timing/failure policy, exact/over `sourceBytes`, `wkbBytes`, and `wireValueBytes`, `sourceDigest`, and cancellation between cells.
- `SqlClientEngineTests`: real SQL Server type matrix across supported RIDs.
- `QueryFlowTests`: normal and compact row shapes, ordering, credit, cancel/dispose, advertised `spatialWkbV1`, per-execute `spatialEncoding`, downgrade, and replay/journal propagation.
- `DigestCaptureTests`: normal and spatial canaries absent from journaled legacy `rows` and the entire compact object, including values and null bitmap, while the intended values still reach the outbound wire path.
- `SqlRowsPageBuilderTests`: exact `pageBytes`, final UTF-8 `frameBytes` guard, and typed oversized-single-row outcome without an over-limit frame.
- Geography fidelity fixtures: point pass-through plus great-elliptic line/polygon cases proving either approved densification error bounds/antimeridian handling or honest MVP rejection.
- `DependencyMatrixTests`: explicit SqlClient-driver-only approval for `Microsoft.SqlServer.Types`.
- YAML scenarios: spatial happy path, truncation, compact privacy, cancel while draining, mixed result sets.

### 18.2 `vscode-mssql` extension host/shared logic

- STS2 wire decode, advertised capability/per-execute negotiation, and downgrade.
- Backend-neutral tagged value round trip.
- RowStore append/spill/read with spatial values.
- `spatial` read reason does not promote viewport pages.
- Sparse/two-read projection alignment.
- Host row/total-byte/per-response-byte/time/label limits, including the oversized-next-feature outcome.
- Opaque handle sequence, one-in-flight pull, expiry, idempotent cancel, controller/global cap, and stale-generation rejection.
- Store lease survives a live rerun until spatial cancel and is released on completion, hide, expiry, and disposal.
- Terminal gating covers the `cancelRequested` interval where `results.streaming` is already false.
- Live and pinned controller-bound adapters return identical spatial chunks without accepting webview-supplied store IDs.
- Result export/copy/text/tool handling does not stringify raw tag objects or regress current display.
- Privacy canaries and value-free errors/telemetry.

### 18.3 Webview/component

- Eligibility and deterministic default selection.
- Result/column/label selector changes cancel stale work.
- Null/empty/invalid/unsupported/mixed-SRID/partial states.
- Fit once, explicit refit, no viewport jump after interaction.
- Theme changes and resize/maximize/split behavior.
- Worker or scheduler cancellation.
- Renderer fallback retains feature list/details.
- Source-row reveal maps through current grid sort; filtered rows preserve the filter and offer an explicit clear-and-reveal action.
- Query-result context never labels a source ordinal as a display row before mapping succeeds.
- Partial status distinguishes scanned-prefix facts from unknown remaining feature counts.
- Closing/inactivating the Spatial tab cancels active pulls; whole-panel hide also releases the host handle and worker/map resources.
- When Spatial remains unopened, no spatial row read, parser/renderer import, worker creation, or derived preparation occurs.
- Localization key coverage.
- Complete tab/panel relationships, roving focus, keyboard map controls, virtual-list focus/position semantics, live announcements, forced colors, reduced motion, and the new focus-region sequence.

### 18.4 End-to-end visual/accessibility

Use Query Studio, not the classic editor:

- Execute real geometry/geography SQL.
- Assert the conditional Spatial tab.
- Assert first paint only after an accepted feature and OpenLayers `rendercomplete`.
- Assert canvas/WebGL is nonblank using screenshot and pixel checks independent of timing markers.
- Verify correct fit and no toolbar/status overlap at desktop and narrow/mobile-like pane widths.
- Verify no network requests in offline mode.
- Test keyboard-only select/fit/reveal.
- Test light, dark, high contrast, high contrast light, 200% zoom, and reduced motion.
- Test two split panels on one document and disposal/rerun during preparation.
- Run an accessibility scanner plus manual screen-reader workflow.

## 19. Phased implementation plan

### Phase 0 - Evidence and decisions

Deliverables:

1. Fix and test compact-row capture elision.
2. Capture real SqlClient spatial values across supported RIDs and SQL targets.
3. Convert known SQL native fixtures with `Microsoft.SqlServer.Types`; validate standard WKB, SRID, curves, Z/M, and `FullGlobe` behavior.
4. Specify and test `sourceBytes`, `sourceDigest`, `wkbBytes`, `wireValueBytes`, `pageBytes`, and final UTF-8 `frameBytes`, including the typed row-too-large outcome.
5. Decide geography line/polygon policy: measured geodesic densification with declared ellipsoid/tolerance, an exact renderer, or points-only MVP.
6. OpenLayers spike with offline point/line/polygon/collection, supported native Cartesian/geographic views, theme switching, selection, resize, and a DOM feature list.
7. Benchmark incremental main-thread parse versus worker for 10k points and complex polygons; select the provisional Phase 3 strategy.
8. Measure production bundle/VSIX impact and prove lazy JS/CSS/worker behavior from the metafile and packaged extension.
9. Register marker vocabulary, deterministic fixture shape, and the exact test-only `PERF_MODE` probe before the first UI vertical slice.
10. Decide MVP curve/`FullGlobe` policy, seed budgets, and whether the bundled physical world outline is in MVP.

Exit criteria:

- No result-value journal leak.
- A supported canonical spatial payload is proven on the runtime matrix.
- Byte/frame bounds and the display/downgrade representation are reviewable contracts, not implementation assumptions.
- Renderer and provisional parser/worker choices are evidence-backed.
- Geography edges, unsupported cases, and every approximation policy are explicit.

### Phase 1 - STS2 and SQL Data Plane contract

Deliverables:

1. Add provider-neutral `DriverSpatialValue`.
2. Add bounded `SqlClientSpatialValueReader`.
3. Add WKB tagged wire value/unrenderable sentinel with the approved byte semantics and a final frame-size guard.
4. Advertise `spatialWkbV1` and require the per-execute `spatialEncoding: "wkb-v1"` option; journal/replay the decision and define downgrade behavior.
5. Extend STS2 docs/spec/generated public API and test corpus.
6. Add SQL Data Plane `SpatialCellEncoding`, spatial type hints, and column metadata.
7. Add the ordinary display/copy/export union so tagged values never become base64, raw JSON, or `[object Object]` accidentally.

Exit criteria:

- Native supported shapes round-trip through normal and compact pages.
- Per-cell, page, and final-frame limits remain bounded and honest.
- Existing clients fail safely or negotiate old behavior.
- Every existing result consumer has a specified spatial display/downgrade behavior.
- No UI dependency in STS2/Data Plane.

### Phase 2 - Shared spatial preparation service

Deliverables:

1. Add `spatial` read reason.
2. Add the minimal run generation to result state while keeping model, live store, and pinned snapshot identities distinct.
3. Add sparse projection or the aligned dual-`getWindow` strategy.
4. Implement controller-bound live/pinned `SpatialReadSource` adapters that acquire and release result-store leases internally.
5. Implement pull-based `open`/`next`/`cancel` sessions with opaque handles, sequence/backpressure rules, expiry, concurrency caps, and per-response/aggregate budgets.
6. Implement cancellable `SpatialResultService` preparation over projected `IQueryResultStore` reads.
7. Add metadata-only markers, test-only exact probes, and privacy canaries.

Exit criteria:

- React performs no raw result scan.
- Spatial scans do not evict grid viewport pages.
- Stale/rerun/cancel/hide/expiry paths are deterministic and leases are proven released.
- Live/pinned contract tests share fixtures.
- No webview-controlled store or snapshot identifier crosses the authority boundary.

### Phase 3 - Offline Spatial tab MVP

Deliverables:

1. Add preview gate `mssql.queryStudio.spatial.enabled`, conditional sibling tab, and grid action.
2. Add locally bundled, lazy OpenLayers modules using the provisional Phase 0 parse/worker strategy and surface-specific CSP.
3. Add result/spatial/label selectors, Fit, offline layers, status, selection/details, and source-row reveal.
4. Add native Cartesian and only the supported geographic/projection modes from the fidelity decision.
5. Add synchronized virtualized feature list, tab/focus-region semantics, and accessible announcements.
6. Add optional local physical orientation layer if approved.
7. Add renderer fallback and full localization.
8. Add one deterministic offline vertical perftest scenario/probe plus Playwright zero-network and nonblank-pixel coverage.

Exit criteria:

- The explicitly supported point/line/polygon/multi/collection matrix works offline; unsupported geography shapes are not rendered approximately by accident.
- Geometry SRID 0 never appears on a world basemap.
- Partial/invalid/budget states are honest.
- Keyboard/screen-reader/high-contrast flows pass.
- Before activation there are no spatial row reads, derived preparation, parser/renderer dynamic imports, or worker creation. Lightweight eligibility metadata and the gated tab itself are allowed.

### Phase 4 - Performance and release hardening

Deliverables:

1. Expand spatial perftest fixtures/scenarios and semantic probes beyond the Phase 3 vertical case.
2. Tune registered budgets/chunking from evidence.
3. Revalidate and tune the selected main-thread/worker strategy; change it only if evidence requires it.
4. Add WebGL/cluster tier only if the Canvas cap is insufficient.
5. Validate multi-panel/hidden GPU and memory lifecycle.
6. Run complete STS2, extension, webview, Playwright, and perftest verification chains.
7. Document supported/unsupported types, offline guarantee, and privacy behavior.

Exit criteria:

- Existing Query Studio perf scenarios do not regress.
- Spatial correctness proofs and privacy canaries are stable.
- Preview feature gate and rollback path are documented.

### Phase 5 - Optional online basemap/satellite

This is a separate product/security/legal project:

1. Select provider(s) and authentication.
2. Define consent and settings scope.
3. Add host allowlist/CSP and attribution.
4. Define caching/offline/failure/cost behavior.
5. Add location-privacy review and network tests.
6. Add streets/satellite only for compatible coordinate systems.

Do not hold the offline viewer for this phase.

### Expected code change map

This is a planning map, not a promise that every path changes:

| Repository area                                                                                   | Expected responsibility                                                                         |
| ------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `sqltoolsservice/src/sts2/Microsoft.SqlTools.Sts2.Runtime/Coordination/CaptureElision.cs`         | P0 compact capture elision and canary-safe replay behavior                                      |
| `sqltoolsservice/src/sts2/Microsoft.SqlTools.Sts2.Drivers.SqlClient/**`                           | Exact SQL spatial recognition, bounded native read/conversion, cell/page limits                 |
| `sqltoolsservice/src/sts2/Microsoft.SqlTools.Sts2.Runtime/Effects/WireValueEncoder.cs`            | Versioned tagged value and precise wire-size accounting                                         |
| STS2 contracts/hosting/public API/docs/tests under `sqltoolsservice/src/sts2` and `test/sts2`     | Capability plus execute option, final-frame behavior, scenarios and matrix tests                |
| `vscode-mssql/extensions/mssql/src/sharedInterfaces/queryStudio.ts` and SQL Data Plane interfaces | Spatial metadata/value union, run generation, display/downgrade contract                        |
| `vscode-mssql/extensions/mssql/src/queryResults/**`                                               | Controller-bound spatial source, lease, pull protocol, projected preparation, budgets           |
| `vscode-mssql/extensions/mssql/src/queryStudio/rowStore.ts`                                       | `spatial` read reason and sparse projection only if the shared API chooses it                   |
| Query Studio and pinned controllers                                                               | Bind the owned live/pinned store to opaque spatial sessions; release on lifecycle transitions   |
| `vscode-mssql/extensions/mssql/src/webviews/pages/QueryStudio/**` plus a shared results pane      | Conditional UI, lazy renderer/worker, accessible feature list, selection/reveal, offline layers |
| Webview base/CSP and mssql esbuild configuration                                                  | Surface-specific CSP, dynamic chunks/worker entry, WebWorker typing, CSS/bundle verification    |
| `perftest/packages/observability-contracts/**`, scenario registries, and mssql perf driver        | Fixed-role markers, deterministic fixture, exact test probe, exploratory scenarios              |

## 20. Risks and mitigations

| Risk                                                            | Impact                                                  | Mitigation                                                                                                                               |
| --------------------------------------------------------------- | ------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| Spatial provider values differ by RID/runtime                   | Wrong or failed decode                                  | Phase 0 engine matrix; native-byte fixtures; service advertisement plus per-execute opt-in/downgrade                                     |
| Compact values remain in journals                               | Severe result-data disclosure                           | P0 capture fix and canaries before spatial payload                                                                                       |
| Large geometry bypasses cell/page/frame limits                  | Service/extension OOM, huge frame, or transport failure | Separate source/WKB/wire/page/frame accounting, lower-only cell cap, final UTF-8 frame guard, typed row-too-large result, no partial WKB |
| Geography edges are rendered as straight projected chords       | Misleading line/polygon placement                       | Points-only MVP unless exact rendering or declared ellipsoid/tolerance densification is proven and budgeted                              |
| Curves/full globe render incorrectly                            | Misleading data                                         | Explicit support matrix; approximation metadata or honest unsupported state                                                              |
| Unknown/mixed SRID placed on basemap                            | Semantically wrong map                                  | Native Cartesian fallback; group mixed SRIDs; basemap only for proven transforms                                                         |
| Map bundle slows every editor open                              | Query Studio regression                                 | Dynamic import, modular imports, bundle budget, no CDN                                                                                   |
| Parsing freezes webview                                         | Poor editor input/interaction                           | Phase 0 parser/worker benchmark; hard vertex/memory/work-slice limits; revalidate after the vertical slice                               |
| Secondary scan evicts grid cache                                | Scroll regression                                       | `spatial` no-readmission reason and queryResults service ownership                                                                       |
| Live rerun or panel hide invalidates a store during preparation | Stale data, failed reads, or retained spill files       | Controller-owned lease, opaque generation-scoped pull handle, idempotent cancel/expiry, host-side hide/dispose release                   |
| Host sends faster/larger chunks than the webview can consume    | RPC queue and memory growth                             | Pull protocol, one in-flight request, sequence validation, total and per-response encoded-byte caps                                      |
| Hidden/split panels duplicate GPU memory                        | Process instability                                     | Visibility/disposal hooks and per-controller/global caps; no shared prepared cache in MVP                                                |
| Partial status implies facts about unscanned rows               | User makes decisions from false counts                  | Prefix-scoped host/decoder summaries and explicit unknown-remaining-feature wording                                                      |
| Canvas inaccessible                                             | Blocks keyboard/screen-reader users                     | Synchronized DOM feature list/details and complete Results grid alternative                                                              |
| Online tiles leak location                                      | Privacy incident                                        | Default off, explicit disclosure, allowlist, no arbitrary workspace URL                                                                  |
| Provider/license changes                                        | Broken/costly product                                   | Provider abstraction, attribution, no public free tile hardcode, separate milestone                                                      |
| Tagged value breaks export/AI/transforms                        | Cross-feature regression                                | Consumer audit and compatibility test matrix in Phase 1                                                                                  |
| App component grows further                                     | Maintenance burden                                      | New modules/shared pane; keep `app.tsx` to orchestration only                                                                            |

## 21. Open questions for detailed review

### 21.1 Product and UX

1. Is the visible label `Spatial`, `Map`, or `Spatial results`? `Spatial` is recommended because arbitrary planar geometry is not always a map.
2. Must both types ship together, or may preview start with `geometry` plus geography points while geography lines/polygons remain behind the fidelity gate?
3. Is completed-result-only acceptable for MVP?
4. Is pinned-result Spatial parity required in the first milestone or immediately after live Query Studio?
5. Is bidirectional grid/map selection required, or is map-to-grid reveal sufficient initially?
6. Should users be able to select WKT/WKB/GeoJSON string columns explicitly in a later advanced mode?
7. Are label and selected-row details sufficient, or is color-by a first-release requirement?
8. Is a bundled physical world outline desirable, and what VSIX size budget is acceptable?
9. Is any spatial export required for preview, or can all new export stay deferred?

### 21.2 Spatial fidelity

10. What exactly does `Microsoft.Data.SqlClient` return for spatial values on every supported RID?
11. Does standard `STAsBinary`/`Microsoft.SqlServer.Types` output cover the required shape matrix?
12. Is 2D display acceptable while preserving/disclosing Z/M flags?
13. For geography lines/polygons, is MVP points-only, exact geodesic rendering, or densification? If densified, which SRID/ellipsoid, pixel or ground-distance tolerance, antimeridian/pole rules, and disclosure are required?
14. How should curved types be handled: exact parser, declared tessellation, or unsupported in MVP?
15. What is the required `FullGlobe` and larger-than-hemisphere behavior?
16. Should invalid shapes fail one cell only, and what validity signal can be obtained without expensive work?
17. What bounded ordinary grid/copy/export representation should renderable and unrenderable spatial values use?
18. Which SRIDs/projections beyond 0, 4326, and 3857 are release requirements?

### 21.3 Performance and architecture

19. What supported host row/serialized-byte/per-response/time/label and decoder vertex/memory/work-slice caps are realistic after benchmarking?
20. Is deterministic-prefix partial display acceptable, or is representative sampling required?
21. Does parsing need a browser worker under the chosen caps?
22. Is Canvas sufficient for MVP, or is a point WebGL tier required?
23. Should host preparation ever be cached/shared across split panels after MVP?
24. Should the general result-store API gain sparse projection, or should Spatial join two projected reads?
25. What is the supported remote/Codespaces/web-extension story and RPC bandwidth budget?

### 21.4 Security, network, and release

26. Should the CSP foundation be shared while Query Studio/pinned results adopt it first, or must every webview migrate in the same release?
27. Which online provider, if any, may Microsoft ship and support?
28. Can an enterprise/self-hosted tile URL be configured without allowing a workspace to trigger exfiltrating requests?
29. Should provider auth use an existing Azure identity, a subscription key in SecretStorage, or a separate provider extension point?
30. What tile caching is permitted and where would sensitive viewed-area history live?
31. What preview-gate default, telemetry opt-out behavior, rollback criteria, and eventual gate-removal evidence are required?

## 22. Definition of ready for implementation

The feature is ready for an implementation plan only when:

- [ ] Compact-row capture is value-safe and canary-tested.
- [ ] The SqlClient spatial RID/type matrix is recorded.
- [ ] A versioned spatial cell contract, `spatialWkbV1` advertisement, and per-execute opt-in/downgrade flow are approved by STS2 and SQL Data Plane owners.
- [ ] `sourceBytes`, `sourceDigest`, `wkbBytes`, `wireValueBytes`, `pageBytes`, `frameBytes`, and the typed row-too-large outcome have exact definitions and tests.
- [ ] Geography edges, curves, Z/M, invalid values, mixed SRIDs, and `FullGlobe` have explicit support/approximation policies.
- [ ] OpenLayers (or an alternate) passes the offline, Cartesian, projection, accessibility, CSP, bundle, and performance spike.
- [ ] The provisional incremental-main-thread or worker strategy is selected, including WebWorker typing and packaged lazy-chunk/CSS evidence.
- [ ] Separate host and decoder budgets are agreed and registered, including a per-response RPC limit.
- [ ] The controller-bound live/pinned result-source boundary, lease lifecycle, opaque pull handle, backpressure, and generation contract are approved.
- [ ] Existing grid/copy/export/transform/AI behavior for spatial tagged values is specified.
- [ ] The accessible feature-list workflow is accepted as a release requirement.
- [ ] Online basemap scope is explicitly included or deferred; no ambiguous network behavior remains.
- [ ] Perftest fixtures, fixed-role bucketed markers, exact test-only probe, and non-regression scenarios are designed; Playwright owns zero-network proof unless interception is added.
- [ ] The preview gate and rollback policy are approved.
- [ ] Third-party code/data notices and security review requirements are known.

## 23. External references reviewed

- [SQL Server spatial data types](https://learn.microsoft.com/en-us/sql/relational-databases/spatial/spatial-data-sql-server?view=sql-server-ver17)
- [SQL Server geometry and geography behavior overview](https://learn.microsoft.com/en-us/sql/relational-databases/spatial/spatial-data-types-overview?view=sql-server-ver17)
- [Create, construct, and query geography instances](https://learn.microsoft.com/en-us/sql/relational-databases/spatial/create-construct-and-query-geography-instances?view=sql-server-ver17)
- [SQL Server spatial reference systems](https://learn.microsoft.com/en-us/sql/relational-databases/system-catalog-views/sys-spatial-reference-systems-transact-sql?view=sql-server-ver17)
- [`SqlGeometry` API](https://learn.microsoft.com/en-us/dotnet/api/microsoft.sqlserver.types.sqlgeometry?view=sql-dacfx-161)
- [`Microsoft.SqlServer.Types` package](https://www.nuget.org/packages/microsoft.sqlserver.types/)
- [OpenLayers WKB API](https://openlayers.org/en/latest/apidoc/module-ol_format_WKB-WKB.html)
- [OpenLayers Map API](https://openlayers.org/en/latest/apidoc/module-ol_Map-Map.html)
- [OpenLayers projection API](https://openlayers.org/en/latest/apidoc/module-ol_proj_Projection-Projection.html)
- [OpenLayers repository/license](https://github.com/openlayers/openlayers)
- [MapLibre GL JS documentation](https://maplibre.org/maplibre-gl-js/docs/)
- [deck.gl GeoJsonLayer](https://deck.gl/docs/api-reference/layers/geojson-layer)
- [Leaflet reference](https://leafletjs.com/reference)
- [VS Code webview security/accessibility guide](https://code.visualstudio.com/api/extension-guides/webview)
- [W3C guidance for maps and other complex images](https://www.w3.org/WAI/tutorials/images/complex/)
- [Natural Earth terms of use](https://www.naturalearthdata.com/about/terms-of-use/)
- [OpenStreetMap tile usage policy](https://operations.osmfoundation.org/policies/tiles/)

## 24. Recommended next review sequence

1. STS2 protocol/driver review: spatial native read, WKB contract, bounds, capture fix, RID matrix.
2. Query results platform review: read reason, run identity, sparse projection, live/pinned preparation service.
3. UX/accessibility review: tab model, feature list, source-row reveal, partial/mixed-SRID states.
4. Renderer spike review: OpenLayers fit, projection, bundle, main-thread/worker, Canvas/WebGL evidence.
5. Security/privacy review: CSP, compact capture, online provider deferral, canaries.
6. Perftest review: deterministic fixtures, marker vocabulary, correctness probes, graduation criteria.
7. Convert approved decisions into repository-specific execution plans with batch-sized tests and rollback points.
