# Query Studio Spatial Results — Product Design and Execution Plan

**Status:** designed; implementation not started  
**Date:** 2026-07-12  
**Branches reviewed:** `vscode-mssql/dev/query`, `sqltoolsservice/dev/query`, `perftest/dev/query`  
**Authority:** this document supersedes the old “do not start spatial” gate and refines the spatial section of `EXECUTION_PLAN.md`. The safety and fidelity rules in `geospatial_pane.md`, `geospatial_pane_execution_addendum.md`, and brief `r05` remain authoritative unless this document explicitly records a newer decision.

## 1. Outcome

Build an offline-first **Spatial** result tab for Query Studio that turns native SQL Server `geometry` and `geography` result cells into a serious analysis and validation surface without changing the query, re-reading the database, or compromising Query Studio’s large-result behavior.

The experience must:

- stay responsive while data is streamed, decoded, filtered, selected, panned, and zoomed;
- remain honest when a result, transport, decoder, projection, or render budget is partial;
- preserve native row identity and round-trip safely through Results, copy, text, export, pin, and AI-tool consumers;
- cost almost nothing until an eligible Spatial tab is opened, except for the unavoidable bounded WKB canonicalization performed during an explicitly opted-in spatial query;
- work with no network access and no basemap, while leaving a separately consented online-map milestone possible;
- expose a value-free, cross-process diagnostic story in Session Diag, the MSSQL Debug Console, and perftest.

This is a data-analysis map, not a dashboard canvas. The center of gravity is row-level inspection, fidelity, status, comparison, filtering, and query-result integration.

## 2. Context reconciled against the current branches

Several prerequisites described as missing in the original spatial documents have now landed through the Vector work:

- STS2 compact row capture elision covers compact payloads.
- STS2 measures encoded rows in UTF-8 and has a final conservative frame guard.
- CLR UDT results no longer fail the query; spatial UDTs currently arrive as bounded SQL Server CLR-serialization bytes through the ordinary binary wrapper.
- Query Studio has a shared typed-cell codec for Vector, a complete sparse-column projection path, non-admitting analysis reads, retained-store leases, strict CSP for Query Studio, lazy result chunks, controller-memory panel state, and registry-governed observability.
- Vector has established a workable pattern for gate-controlled typed transport, metadata eligibility, lazy activation, lifecycle invalidation, pinned/live authority, and perftest tab activation.

The following are still spatial-specific gaps:

- no `spatialWkbV1` STS2 capability or per-execute opt-in;
- no exact system `geometry`/`geography` provider recognition for typed transport;
- no provider-neutral bounded WKB + SRID cell contract;
- no spatial codec/display/export policy;
- no spatial metadata on `QsResultColumn`;
- no spatial host pull session, decode pipeline, renderer, feature list, or row-selection context;
- no spatial observability vocabulary, perf fixtures, scenarios, or Debug Console analysis view;
- Query Studio’s result tabs are still hard-coded around Results/Messages/Vector/Query Plan rather than registered as lightweight pane contributions.

Vector remains partially incomplete. Spatial work must not rewrite or destabilize Vector’s live Search/Index/Pipeline paths. Shared framework changes must be narrow, compatibility-tested, and independently revertible.

## 3. Locked product decisions

### 3.1 Activation and truth

1. Add preview setting `mssql.queryStudio.spatial.enabled`, default `false`, application scope, “applies to the next execution.”
2. STS2 advertises `spatialWkbV1: true`, but changes cell shapes only when the execute request contains `spatialEncoding: "wkb-v1"`.
3. Query Studio sends that option only when the setting is enabled, the backend capability is present, and the extension’s spatial codec/consumer matrix is enabled.
4. The tab appears only for terminal non-plan result sets whose metadata confirms an opted-in WKB spatial column. It never appears by value sniffing and never retrofits an old run.
5. The tab never auto-opens. A result-grid **View Spatial** action may open it with the originating set/column selected.
6. Streaming-result viewing is not in the first slice. A canceled or limited result becomes eligible only after its terminal frozen summary exists.
7. Every count says what it counts: source rows, scanned rows, candidate cells, decoded features, renderable features, visible features, skipped values, and selected features are distinct.

### 3.2 Offline-first map

- MVP makes **zero network requests**. “Offline” is a normal mode, not an error state.
- The data-only view supplies a Cartesian grid or geographic graticule, coordinate readout, scale, extent, fit/home, smooth pan/zoom, selection, feature list, details, and truth/status bars.
- A small generalized world-outline layer is a follow-up offline-context feature, lazy bundled with attribution/notices. It is not required for the first vertical slice.
- Streets, satellite, geocoding, routing, and remote projection lookup are a separate product/security/legal milestone. No remote host is admitted to MVP CSP.

### 3.3 Renderer

Use **OpenLayers behind a repository-owned `SpatialRenderAdapter`**. Pin the exact reviewed package version; import exact ESM modules only; bundle all code and CSS locally; add `ol` to the Query Studio bootstrap denylist in the same change.

The adapter exposes three measured tiers:

1. **Canvas vector** — correctness baseline and default for polygons, lines, mixed shapes, and smaller point sets.
2. **GPU point** — point-only or point-dominant large sets after compatibility/perf qualification. Keep the upstream WebGL API isolated because OpenLayers documents parts of that surface as unstable. A failure falls back to Canvas with an honest status.
3. **List only** — decoder or renderer unavailable; inspection and Reveal in Results remain usable.

No renderer tier may silently simplify, sample, repair, reproject, or omit accepted geometry. An explicitly labeled density/cluster analysis mode may aggregate points in a later slice; it must never be presented as the full feature layer.

### 3.4 Decode and UI responsiveness

The old main-thread-only default is superseded for the production design. WKB validation and decode run in a **lazy Web Worker** by default, because one near-limit WKB cell can create an unacceptable main-thread long task even when work between cells is cooperatively sliced.

- The worker validates base64 length, WKB structure, byte order, geometry nesting, coordinate counts, and local budgets before committing a feature.
- It uses the same reviewed WKB semantics as the renderer path and returns versioned, transferable flat geometry buffers plus value-free facts.
- Raw WKB is discarded in the webview after decode; the RowStore remains the authoritative source.
- The main thread creates/render-commits features in small frame-budgeted batches. React does not receive coordinate arrays or per-frame pointer state.
- At most one host `next` request and two decoded-but-uncommitted chunks may exist per session. This is the backpressure boundary across host, worker, and renderer.
- If worker creation fails, a lower-budget cooperative main-thread fallback remains available and is visibly disclosed.
- Worker startup, decode, commit, and render tiers are tested separately. No “worker is faster” assumption substitutes for measurements.

### 3.5 Spatial fidelity

- `geometry`: render linear OGC Point/LineString/Polygon, Multi* and GeometryCollection in native Cartesian coordinates; support known 4326/3857 views only through tested transforms.
- Other geometry SRIDs: native Cartesian view, no invented transform or geographic basemap.
- `geography`: Point/MultiPoint are required. Lines/polygons remain transported and inspectable but are not drawn until an exact or bounded geodesic policy passes the provider/fidelity gate. Straight projected chords are forbidden.
- Mixed `(kind, SRID)` values are separate groups. Only one compatible group is active at a time unless a proven transform makes an overlay valid.
- Z/M values are displayed in 2D. The transport and details must not claim Z/M preservation until the provider matrix proves exactly what `STAsBinary()` preserves.
- Null, empty, oversized, conversion-failed, malformed, unsupported-semantic, and renderer-failed are different statuses.
- Decode failure is not topology invalidity. Topology is `unknown` unless the provider supplies a validity fact; no hidden `STIsValid()` calls are made.

## 4. UX design

### 4.1 Layout

Tab order becomes `Results | Messages | Vector | Spatial | Query Plan` when both contributed data panes apply. Spatial fills the complete results region and participates in collapse, maximize, resize, and renderer recreation.

The first production layout:

```
Spatial toolbar
  Result set | Spatial column | Label | Color by | SRID group
  Filter | Layers | Fit/Home | − / + | More

Truth/status banner (only when needed)

Map / analysis viewport
  legend                 zoom controls
  hover preview
  selection overlay
  coordinate readout     scale / projection

Optional right panel
  Features | Selection | Details
  virtualized, searchable, keyboard navigable

Status bar
  scanned / decoded / shown / skipped | vertices | group | render tier | Offline
```

Use Fluent controls, codicons, VS Code/Fluent tokens, localized strings, square/dense Query Studio styling, and no decorative cards/chips. Menus and popovers use shared accessible components.

### 4.2 Core workflows

**Open from a result**

- Spatial tab uses the only eligible set/column automatically, otherwise restores a valid panel-local choice or selects the first eligible pair deterministically.
- A grid action opens Spatial and preserves the originating result set/column.
- Opening never re-executes SQL and never changes transport.

**Inspect and validate**

- Click/tap/Enter on map or feature list selects one source row.
- Details show label, result-row ordinal, SQL spatial kind, OGC geometry type, SRID, layout, WKB bytes, vertices/parts/rings, envelope, and the four-stage status. No unverified validity/area/length claim is shown.
- Actions: Reveal in Results, zoom to feature, open exact cell value, copy bounded summary, copy exact WKB hex when allowed by existing copy budgets.

**Filter and compare**

- Local filters operate over the bounded prepared population: geometry type, status, SRID group, label text, and an optional bounded category/numeric style column.
- The UI states “filtered from N prepared features / first R scanned rows,” never implies a database predicate.
- Color-by supports none, geometry type, status, bounded categorical values, and numeric gradient. Categories beyond the budget collapse into Other with an exact disclosure.
- Box/lasso multi-select and selection statistics are a post-vertical-slice feature. They must preserve result-row ordinals and avoid putting large ordinal arrays in coarse React/controller state.

**Navigate**

- Cursor-centered wheel/pinch zoom; drag pan; double-click zoom; fit group; fit selection; reset/home.
- Auto-fit once after the first meaningful accepted batch. Later chunks never move a user-touched camera.
- Geography point fitting unwraps at the largest longitude gap so antimeridian clusters do not zoom to the whole world.
- Reduced motion disables fly/fit animation. Hidden panels do no animation, pull, decode, or render work.

**Reveal in Results**

- `resultRowOrdinal` is the only source identity.
- The webview maps it through current grid sort/filter state. If filtered out, preserve the filter and offer **Clear filter and reveal**.
- Spatial selection enters `QueryResultContextService` as a spatial-selection kind. It becomes an active grid cell only after display-row mapping succeeds.

### 4.3 Accessibility

- Canvas is never the only interface. The synchronized virtualized feature list exposes row, label, type, SRID, status, and selection.
- Map target has a named focus region and keyboard pan/zoom/fit/escape semantics.
- Feature list supports arrows, Page Up/Down, Home/End, search, Enter, retained logical focus, `aria-posinset`/`aria-setsize` or table equivalents.
- Selection synchronization never steals focus.
- Polite live regions announce preparation, first render, terminal partials, group changes, selection, and Reveal results.
- Status and selection use outline/width/dash/shape in addition to color; forced colors, high contrast, 200% zoom, narrow panes, and reduced motion are acceptance gates.
- Query Studio result tabs keep roving focus, stable IDs, `aria-controls`, `aria-labelledby`, and a documented F6 region order.

## 5. Cross-repository architecture

### 5.1 Data path

```
SqlDataReader (SequentialAccess)
  -> exact system spatial classification
  -> bounded native UDT byte stream + cancellation + digest
  -> Microsoft.SqlServer.Types conversion to OGC WKB + per-value SRID
  -> DriverSpatialValue / DriverSpatialUnavailableValue
  -> WireValueEncoder spatial tag
  -> existing compact result pages / STS2 credit+ack
  -> sts2Backend structural normalization
  -> RowStore / RetainedRowStore / pinned snapshot
  -> controller-bound SpatialSessionManager
  -> sparse projected, byte-capped open/next/cancel RPC
  -> lazy decode worker
  -> SpatialRenderAdapter + virtual feature list
```

There is no feature-specific result stream, SQL rewrite, automatic projection query, webview loop over `qs/getRows`, provider CLR type past the driver, or second authoritative raw cache.

### 5.2 STS2 contract

Canonical success cell:

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

Canonical unavailable cell:

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

Use `wkb`, never `v`. No partial WKB. Transport reasons remain `maxCellBytes | conversionFailed | unsupportedNativeValue | unsupportedInterchange`; renderer-policy reasons stay out of the wire contract.

Implementation rules:

- Add a new STS2 decision entry and SPEC/type-encoding matrix entries.
- Capture `DbColumn.UdtAssemblyQualifiedName` or an equivalent provider fact and require exact supported system-type identity. The existing suffix-based binary fallback remains for non-opted queries and unrecognized CLR UDTs.
- Add a classified `CellRead.Spatial` mode used only for opted-in, exactly recognized geometry/geography columns.
- Stream native bytes in fixed chunks, check cancellation between chunks, hash while draining, and never retain more than the native-cell budget.
- Convert bounded native bytes using the reviewed `Microsoft.SqlServer.Types` package at the driver boundary; obtain `STSrid` and `STAsBinary()` there; recheck WKB length and conversion time.
- Conversion is synchronous and potentially non-cancelable. The provider spike must establish a native-size ceiling and worst-case conversion bound before capability advertisement is enabled.
- Add `spatial:wkb:v1` compact type hints in service/client lockstep.
- Add `spatial` metadata to result-set columns only when typed transport is active.
- Keep the complete-frame UTF-8 guard. Add exact encoded-size estimates for spatial cells so page construction does not undercount base64/wrapper overhead.

Provider go/no-go matrix:

- Windows, Linux, macOS RIDs supported by the STS package;
- local SQL Server 2025 and Azure SQL;
- Point/Line/Polygon/Multi*/GeometryCollection, null, empty, invalid topology;
- both byte orders when producible; Z/M/ZM; curves; FullGlobe; antimeridian/poles;
- native and WKB sizes around every bound;
- cancellation during native drain and measured behavior during synchronous deserialize/`STAsBinary()`;
- exact proof of Z/M, curve, and FullGlobe interchange behavior.

### 5.3 Shared cell codec and ordinary consumers

Extend `queryResultCellCodec.ts` with strict spatial guards, metadata, exact base64/WKB validation helpers, and purpose-specific formatting.

- Grid: `GEOMETRY · SRID 0 · 21 WKB bytes`.
- Tooltip/details: kind, SRID, WKB bytes, transport status; never base64.
- Cell document/copy/text/CSV/JSON: exact SQL-style `0x` WKB hex within existing budgets.
- INSERT export: tested `geometry::STGeomFromWKB(0x..., srid)` / `geography::STGeomFromWKB(...)`.
- AI/tool summary: metadata only unless an existing explicit result-data grant permits the value.
- Unsupported cell: localized reason and byte facts; never raw tag JSON.

Before the execute option can be emitted, the consumer matrix must prove grid, tooltip, sort/filter, copy cell/row/range, text view, cell document, CSV, JSON, INSERT, transforms, pins, snapshots, spill/restore, and AI/tool grant paths never display base64, `[object Object]`, raw JSON, or silently dropped data.

### 5.4 Minimal result-pane extensibility framework

Refactor the Query Studio shell to a lightweight contribution registry without importing heavy implementations:

```ts
interface QueryResultPaneContribution {
    id: QueryStudioTabId;
    order: number;
    appliesTo(context: ResultPaneApplicabilityContext): boolean;
    fillsPane: boolean;
    keepMounted: boolean;
    load(): Promise<ResultPaneModule>;
    chunkMarks?: { requested: string; loaded: string };
}
```

The eager registry contains only metadata sniffs and loader thunks. Vector and Spatial become contributions; Query Plan may keep its specialized payload preparation but uses the same tab ordering/render shell. Results and Messages remain core surfaces.

Shared framework responsibilities:

- deterministic tab ordering and active-tab fallback;
- stable tab/tabpanel accessibility wiring;
- lazy requested/loaded marks and Suspense/error states;
- pane visibility and panel visibility lifecycle callbacks;
- `fillsPane` sizing and keep-mounted behavior;
- per-run invalidation and controller-memory state slot validation;
- PERF_MODE activation by pane ID;
- no renderer, chart, map, or generic visualization abstraction.

Version `QueryStudioPanelViewState` and add bounded Spatial state: chosen set/column/label/style ordinals, group key, panel/list/details visibility, filters without raw values, selected ordinal, and camera. Camera/result-derived state remains controller-memory-only and is invalidated by run generation.

### 5.5 Host spatial service

Add `src/queryResults/spatial/`:

- `spatialTypes.ts`
- `spatialBudget.ts`
- `spatialSessionManager.ts`
- `spatialResultReader.ts`
- `spatialDiagnostics.ts`
- `liveSpatialReadSource.ts`
- `pinnedSpatialReadSource.ts`

The controller supplies the owned store/snapshot; the renderer supplies only result-set and column selections.

RPC:

- `qs/spatial.open { resultSetId, spatialColumn, labelColumn?, styleColumn? }`
- `qs/spatial.next { handle, generation, sequence }`
- `qs/spatial.cancel { handle, generation }`

The open response freezes row count, completeness/corruption, selected columns, source mode, and effective budgets. Next responses preserve ascending `resultRowOrdinal`, carry byte-measured bounded chunks, prefix progress, and `done`. No feature-data notifications.

Lifecycle:

- new lease owner `spatialView`; new non-admitting read reason `spatial`;
- one in-flight `next` per handle, monotonic sequence, random generation, bounded handles and concurrency;
- cancellation on source change, column change, tab leave during active preparation, rerun, panel hide, panel disposal, source disposal, expiry, or local terminal budget;
- `webviewPanel.visible`, not active-editor state, controls whole-panel hide cleanup;
- final `done` releases the lease immediately even while derived map data remains visible;
- cancel is idempotent; stale generations and wrong sequences are typed refusals;
- no webview-provided budget, run ID, store ID, lease ID, or source authority.

Sparse reads request spatial + optional label/style ordinals in one store window. Labels and categorical values are UTF-8 clamped. The host measures the complete serialized response before return and always advances or terminates on an over-hard-limit feature.

### 5.6 Webview modules

Add `src/webviews/pages/QueryStudio/spatial/`:

- `SpatialResultsPane.tsx`
- `SpatialToolbar.tsx`
- `SpatialMap.tsx`
- `SpatialFeatureList.tsx`
- `SpatialDetails.tsx`
- `SpatialStatus.tsx`
- `spatialDecodeWorker.ts`
- `spatialWorkerProtocol.ts`
- `spatialWkbPreflight.ts`
- `spatialProjection.ts`
- `spatialRenderAdapter.ts`
- `spatialCanvasAdapter.ts`
- `spatialGpuPointAdapter.ts`
- `spatialSelection.ts`
- `spatialTypes.ts`
- `spatial.css`

`app.tsx` owns eligibility, selected tab, contribution mount, run generation, and shell view-state handoff only. It does not parse WKB, construct maps, pull chunks, or hold feature arrays.

## 6. Performance design and initial budgets

### 6.1 Honest unopened cost

Measure two separate promises:

1. Gate on + nonspatial query: negligible classification/capability overhead; no spatial conversion.
2. Gate on + spatial query + tab unopened: bounded native read/WKB canonicalization occurs during the forward-only result stream; no secondary RowStore read, spatial RPC, worker, OpenLayers chunk, map, canvas/GPU resource, feature list, or derived geometry cache.

### 6.2 Initial safe profile

Start with the previously reviewed conservative profile, then raise point-only caps only after evidence:

| Budget | Initial interactive value | Owner |
| --- | ---: | --- |
| Rows scanned | 25,000 | host |
| Session response payload | 32 MiB | host |
| Response soft / hard | 1 MiB / 2 MiB | host |
| Label/style preview | 4 KiB UTF-8 each | host |
| Rows per store window | 500–1,000 | host |
| Decoded/render vertices | 250,000 | worker/webview |
| Derived geometry memory estimate | 64 MiB | worker/webview |
| Main-thread commit slice | 4 ms target, 8 ms hard diagnostic threshold | webview |
| Pending decoded chunks | 2 | webview |

The large-point qualification target is 100,000 points with GPU buffers and a higher derived-memory profile. It does not ship merely because the GPU demo works; it ships when pan/zoom/select, fallback, memory reclamation, remote-webview bandwidth, and low-memory behavior pass.

### 6.3 Responsiveness acceptance

- first meaningful feature render occurs before full bounded preparation;
- pointer/keyboard interaction is available while later chunks decode;
- no React state update on pointer move, pan frame, zoom frame, coordinate readout, or scale update;
- renderer/worker/store queues are bounded and observable;
- no stale generation can commit after rerun, hide, or selection change;
- no long task above 50 ms in the 10k mixed-shape target; point-tier 100k interaction p95 frame time and input delay get baseline-relative gates after stable samples;
- all buffers, OL sources, event listeners, workers, and GPU contexts are released on lifecycle exit;
- a two-panel test proves bounded duplicate work and complete cleanup.

## 7. Observability and MSSQL Debug Console

### 7.1 Cross-process trace stitching

Before claiming end-to-end observability:

- bind the STS2 query ID/process identity to the owning Query Studio query trace when execute returns;
- have STS diagnostics containing that query identity resolve through the diagnostics entity-trace map;
- add a Query Studio controller hook that enriches Spatial webview marks with the current pane/session trace instead of leaving them as root-window orphans;
- start a fresh child correlation for each Spatial open generation and pass it explicitly to host markers;
- never emit handles, coordinates, bounds, WKB/WKT, labels, values, column/table/database/server/query names, raw SRID+location, or tile URLs.

### 7.2 Marker vocabulary

Register before emission:

- `mssql.queryStudio.boot.spatialChunkRequested/Loaded`
- `mssql.queryResults.spatial.prepare.begin/end/cancel`
- `mssql.queryResults.spatial.chunk.end`
- `mssql.queryResults.spatial.decode.begin/end/cancel`
- `mssql.queryResults.spatial.render.begin/firstPaint/settled/cancel`
- `mssql.queryResults.spatial.interaction.end` (PERF_MODE exact; production bucketed)
- `mssql.queryResults.spatial.resources.released`

STS aggregated diagnostics add spatial cell count, native/WKB byte buckets, conversion duration, maximum conversion bucket, and unavailable reason counts. They never include coordinate-bearing material or raw SRID.

Production attributes are enums/buckets/booleans and safe counts. Exact test counts/durations/memory/frame data remain PERF_MODE diagnostic metrics under the existing classification contract.

### 7.3 Debug Console design

Extend **Query & Results** with a Spatial subview instead of adding another top-level rail item.

- KPIs: sessions, median/p95 first paint, scanned/decoded/rendered counts, partial/cancel/error totals, render-tier distribution, long-task count, peak derived-memory bucket, unreleased-resource count.
- Occurrence table: open time, prepare/decode/render durations, source mode, render tier, terminal outcome/reason, trace link.
- Selected occurrence: compact stage waterfall from STS canonicalization through store read, worker decode, first render, settled, and cleanup.
- Health panel: active handles/workers, pending chunks, lease count, stale-generation drops, renderer fallbacks, network-request violations.
- Every row links to the cross-process Waterfall/Consolidated Trace.

Session Diag and exported bundles contain the same value-free events. Add privacy canaries that fail if coordinates, WKB/WKT, labels, result values, or configured sentinel strings appear anywhere.

## 8. Test strategy

### 8.1 SQL Tools Service

- exact provider classification and unrecognized-UDT fallback;
- opt-in/default wire compatibility;
- cell tags, unavailable sentinels, type hints, metadata, compact/noncompact equivalence;
- native drain cancellation, size/digest facts, post-conversion WKB bound;
- exact UTF-8 page estimate and final frame guard;
- malformed/provider conversion failures remain cell-local, never fail the result stream;
- decision/SPEC/PublicAPI tests and `verify --quick`;
- live local/Azure matrix and CI RID coverage.

### 8.2 Extension host/shared logic

- codec guard collision: spatial `wkb` is never a generic `{$t,v}` wrapper;
- full ordinary-consumer matrix, spill/restore, pin/snapshot/derived paths;
- metadata eligibility and gate/option negotiation;
- spatial source sparse projection and one spill materialization per window;
- byte-capped response construction and UTF-8 label/style truncation;
- every normal/cancel/hide/rerun/dispose/expiry/concurrency/stale-generation lifecycle releases its lease;
- panel view-state versioning, validation, sensitive-field exclusion, run reset;
- QueryResultContext mapping and filtered Reveal behavior.

### 8.3 Worker/renderer/webview

- fuzz/property corpus for malformed WKB length/count/nesting/endian cases;
- all supported OGC shapes, holes/ring orientation, nested collections, empties, both byte orders, X/Y and lon/lat orientation;
- mixed SRIDs arriving in late chunks never overlay or re-fit the user;
- geography lines/polygons never reach the straight-line renderer;
- worker/main fallback equivalence for accepted features/statuses;
- progressive first render, cancellation, stale-message drop, memory cleanup;
- Canvas/GPU tier visual and selection parity;
- keyboard, screen reader, forced colors, reduced motion, 200% zoom, narrow pane;
- CSP and Playwright request interception prove zero network;
- themes, high DPI, resize, split editors, hidden/revealed panels, renderer recreation.

### 8.4 Deterministic fixtures

Create a durable SpatialLab corpus for local SQL Server and Azure-safe schema variants:

- 10k and 100k deterministic geography points, including antimeridian/poles;
- planar points/lines/polygons/multis/collections;
- polygon holes and controlled vertex counts;
- SRID 0, 4326, 3857, unknown/mixed SRIDs;
- null, empty, malformed/unavailable transport fixtures;
- Z/M/ZM, curves, invalid topology, FullGlobe/larger-hemisphere evidence cases;
- near-cell-limit and over-cell-limit values;
- multiple result sets and multiple spatial/label/style columns.

Ground-truth scripts assert counts/types/SRIDs/byte ranges before UI/perf results are trusted.

### 8.5 Perftest scenarios

- `querystudio-spatial-nonspatial-unopened`
- `querystudio-spatial-unopened-points`
- `querystudio-spatial-points-10k-offline`
- `querystudio-spatial-points-100k-gpu`
- `querystudio-spatial-mixed-shapes`
- `querystudio-spatial-complex-polygons`
- `querystudio-spatial-budget-partial`
- `querystudio-spatial-rerun-cancel`
- `querystudio-spatial-pinned`
- `querystudio-spatial-pan-zoom-select`
- `querystudio-spatial-renderer-fallback`

Negative proofs require absent spatial reads/chunks/workers for unopened cases. Positive cases require independent host preparation and real renderer `rendercomplete`/semantic-probe evidence with matching generation/count facts. Start exploratory, collect variance, set named baselines, then promote only stable metrics.

## 9. Dependency-ordered execution plan

Every checkpoint ends with focused tests, full affected-repo typecheck/build/lint, privacy assertions, progress entry, and an intentional commit. Cross-repo contracts land disabled before consumers enable negotiation.

### SPA-0 — Evidence, budgets, and vocabulary

- Re-run the provider/RID/WKB fidelity matrix on current packages and both configured SQL environments.
- Benchmark conversion worst cases and decide the safe native/WKB cell ceiling.
- Build SpatialLab SQL corpus and ground truth.
- Prototype Canvas and GPU point tiers plus worker/main decode on 10k/100k/complex shapes.
- Register observability markers and derived metrics in perftest; regenerate/vendor contracts.
- Record exact OpenLayers/package/license/version and packaged lazy chunk sizes.

**Exit:** no unresolved contract question can silently lose coordinates/dimensions or block cancellation; initial budgets are evidence-backed; marker contracts are green.

### SPA-1 — Minimal pane framework

- Add result-pane contribution registry, deterministic ordering, lazy loaders, accessibility wiring, fill/keep-mounted/lifecycle semantics, and generic PERF_MODE activation by pane ID.
- Version controller-memory panel state and add validated Spatial slot.
- Keep Vector behavior byte-for-byte/functionally stable; bundle budget and Vector focused suite green.

**Exit:** a test contribution can appear/disappear/load lazily/reset by generation without feature code in `app.tsx`.

### SPA-2 — Spatial codec before negotiation

- Add tagged spatial contracts/guards/metadata and purpose-specific display/export behavior.
- Adopt through every ordinary consumer and complete the consumer matrix.
- Add unknown-tag and malformed-tag refusal behavior.

**Exit:** no base64/raw tag/object string can reach any ordinary surface; execute option remains off.

### SPA-3 — STS2 WKB transport

- Add exact system-type classification, provider-neutral values, bounded native read, WKB conversion, sentinels, metadata, type hints, size estimates, capability/option, SPEC decision, and aggregated diagnostics.
- Preserve current binary fallback for default/non-opting clients.
- Run unit/scenario/live/RID validation.

**Exit:** local and Azure round trips match SpatialLab ground truth; failures are cell-local and honest; capture/frame/privacy gates pass.

### SPA-4 — SQL Data Plane binding and eligibility

- Normalize compact/noncompact spatial tags identically.
- Map STS metadata to `QsResultColumn.spatial`; add gate-controlled execute option.
- Add setting, capability state, terminal eligibility, and View Spatial result-grid action.
- Bind STS query diagnostics and webview marks to the owning trace.

**Exit:** eligible runs show a dormant Spatial tab; unopened-cost scenarios prove no secondary work or renderer chunk.

### SPA-5 — Host pull session

- Implement source adapters, budgets, sparse reads, byte-measured chunks, handles/generations/sequences, expiry/concurrency, and lifecycle cleanup for live results.
- Add `spatialView` lease owner and `spatial` read reason.
- Implement label/style projection without duplicate spill reads.

**Exit:** lifecycle matrix and corrupt/short/oversize response tests pass with zero leaked leases.

### SPA-6 — Offline vertical slice

- Lazy-load Spatial pane, worker, OpenLayers adapter, Canvas tier, toolbar, map, feature list, details, truth/status model, selection, and Reveal in Results.
- Support required geometry shapes and geography points; enforce group/projection/geography policy.
- Emit real decode/render/cleanup markers and add Query & Results Spatial diagnostics view.

**Exit:** 10k points and mixed-shape corpus are fully usable by mouse and keyboard; first render is progressive; zero-network and accessibility core scenarios pass.

### SPA-7 — Large-data analysis and interaction

- Qualify/isolate GPU point tier and automatic tier selection.
- Add local type/status/label/category/numeric filters and color-by.
- Add fit selection and bounded multi-select/box selection if memory/ordinal representation passes.
- Tune worker/commit/backpressure and low-memory/remote profiles from traces.

**Exit:** 100k point target is smooth and bounded on qualified hardware, with reliable Canvas/list fallback and no bootstrap regression.

### SPA-8 — Pinned parity and lifecycle hardening

- Reuse Profile-like Spatial experience for pinned snapshots; lock any live-only action honestly.
- Complete renderer recreation, split-panel visibility, hide/reveal, rerun, source close, expiry, duplicate cancel, two-panel, and spill-cleanup families.
- Persist only bounded controller-memory view state.

**Exit:** live and pinned acceptance matrix passes; every exit produces `resources.released` evidence.

### SPA-9 — Performance, privacy, fidelity, and release gate

- Land all perftest scenarios/configs, baselines, reports, and Debug Console validation.
- Run complete SpatialLab matrix, fuzzing, visual regression, network interception, privacy canaries, localization, accessibility, themes, packaging, and third-party notices.
- Document limits, supported semantics, status taxonomy, gate behavior, and troubleshooting.

**Exit:** builds/suites green in all repos; official unopened non-regression gate green; stable activated metrics baselined; no open P0/P1 fidelity/privacy/lifecycle issue.

### SPA-10 — Optional cartographic services (separate approval)

Design provider configuration, explicit consent, HTTPS/allowlists, attribution, credentials, cache/retention, CSP reload, privacy disclosure, offline fallback, and legal review. Do not begin inside SPA-0..9.

## 10. Proposed change map

### `sqltoolsservice`

- `docs/sts2/DECISIONS.md`, `docs/sts2/SPEC.md`
- `src/sts2/Microsoft.SqlTools.Sts2.Abstractions/ExecEvents.cs`
- `src/sts2/Microsoft.SqlTools.Sts2.Core/Sts2CoreReducer.cs`
- `src/sts2/Microsoft.SqlTools.Sts2.Drivers.SqlClient/SqlClientSession.cs`
- new `SqlClientSpatialValueReader.cs`
- `SqlLargeValueReader.cs`, `SqlRowsPageBuilder.cs`
- `src/sts2/Microsoft.SqlTools.Sts2.Runtime/Effects/WireValueEncoder.cs`
- `DriverEffectRunner.cs`, public API baselines, unit/scenario/integration tests

### `vscode-mssql/extensions/mssql`

- `src/sharedInterfaces/queryResultCellCodec.ts`, `queryStudio.ts`, `queryStudioViewState.ts`, new spatial RPC contracts
- `src/services/sts2/sts2Backend.ts`
- `src/queryStudio/rowStore.ts`, `queryStudioController.ts`, `executionHost.ts`
- `src/queryResults/queryResultTypes.ts`, `resultStoreLease.ts`, `queryResultContextService.ts`
- new `src/queryResults/spatial/`
- `src/webviews/pages/QueryStudio/app.tsx`, `lazyResults.tsx`, new pane registry and `spatial/`
- `src/controllers/webviewBaseController.ts` trace-enrichment hook
- Debug Console contracts/controller/pages
- `scripts/bundle-webviews.js`, `test/unit/queryStudioBundleBudget.test.ts`
- package/settings/localization/notices and focused unit/Playwright tests

### `perftest`

- observability registry/generated/vendor artifacts
- SpatialLab/perf query fixtures and config
- Query Studio scenario registry + conformance tests
- perf driver semantic interaction probe if the generic activation command is insufficient
- baseline/report/Debug Console validation artifacts

## 11. Stop conditions

Stop the affected checkpoint and fix the foundation if any of these occurs:

- result values, labels, coordinates, extents, WKB/WKT, or raw SRID+location enter diagnostics, telemetry, logs, replay, or panel mementos;
- an ordinary consumer displays base64/raw JSON/`[object Object]` or silently drops a spatial value;
- a non-opting client receives the typed spatial tag;
- provider identity cannot exclude custom CLR UDTs;
- a complete response/frame can exceed its hard byte ceiling untyped;
- mixed SRIDs overlay without a proven transform;
- geography edges reach a straight-line renderer;
- a hidden/stale generation keeps pulling, decoding, rendering, or holding a lease/worker/GPU resource;
- first content requires full bounded preparation;
- large-point qualification produces long tasks, memory instability, or unreliable fallback;
- a UI or diagnostic count cannot state its observed scope.

## 12. Definition of done

Spatial is done when a developer can execute an eligible query, open Spatial without requerying, progressively inspect and filter a large bounded result, pan/zoom/select without UI stalls, understand every skipped/partial state, reveal the exact source row through current grid transforms, use the same experience from a pinned result, work entirely offline, and diagnose the complete STS-to-render lifecycle in the MSSQL Debug Console—while all ordinary consumers remain safe and no result-derived value escapes the approved result surfaces.
