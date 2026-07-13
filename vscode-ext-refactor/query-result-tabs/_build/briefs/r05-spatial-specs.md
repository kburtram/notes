# R05 Brief — Spatial (Geospatial) Results Pane Specs

**Sources (read completely):**
- `coding-docs/query-result-tabs/geospatial_pane.md` (baseline design, 2026-07-09, 1292 lines)
- `coding-docs/query-result-tabs/geospatial_pane_execution_addendum.md` (execution addendum + code review, 2026-07-10, 1362 lines)

**Precedence:** the addendum wins wherever it says **Amendment**, **Required**, **Do not**, or **MVP decision** (addendum §0). Everything else in the baseline remains in force. The addendum's amendments are labeled `EXE-A1`..`EXE-A15` (addendum §2). This brief always states the post-addendum position.

**Build order context:** this pane is built SECOND. A shared extensible result-pane framework is built FIRST and must accommodate everything in §12 of this brief ("Framework capabilities spatial forces").

---

## 1. One-paragraph shape of the feature

An offline-first **Spatial** tab, sibling of Results | Messages | Query Plan in Query Studio, rendering native SQL Server `geometry`/`geography` cells. Values are canonicalized to **OGC WKB + SRID** in the STS2 SqlClient driver *during* the ordinary forward-only credited row stream (when the run opted in), stored unchanged in the extension-host RowStore, and later pulled by a controller-bound, budgeted, cancellable spatial session (`open`/`next`/`cancel` request-response RPC). The webview lazy-loads OpenLayers (BSD-2-Clause) Canvas modules on first tab activation, decodes WKB incrementally on the main thread, and renders one `(kind, SRID)` group at a time alongside a synchronized accessible DOM feature list. Zero network requests, ever, in MVP. The hard part is the cross-repo result contract (type/SRID/bounds/honesty), not drawing shapes (baseline §1; addendum §9.1).

## 2. Activation conditions (tab visibility + data enablement)

Two independent gates (addendum §3.1, §4.1):

1. **Execute-time data gate.** The `spatialEncoding: "wkb-v1"` per-execute option is sent only when ALL of:
   - preview gate `mssql.queryStudio.spatial.enabled` is on (default off; baseline Phase 3 §19),
   - STS2 initialize advertised capability `spatialWkbV1: true`,
   - the SQL Data Plane binding supports the spatial tagged value and **all ordinary-cell consumers are safe** (see §8).
   A run made without this option is **not retroactively spatial-viewable** — never infer WKT / parse provider fallback strings after execution (addendum §4.1).
2. **Tab visibility gate.** The Spatial tab appears only for a run that has **metadata-confirmed** native `geometry` or `geography` columns **and** whose execution negotiated `spatialWkbV1` (addendum §3.1).

Column detection rules:
- Eligibility comes from column **metadata**, never from scanning row values and never suffix-matching UDT names (addendum §5.1). Marker shape (verbatim):

```ts
export interface SpatialColumnMetadata {
    readonly kind: SpatialKind;            // "geometry" | "geography"
    readonly encoding: "wkb-v1";
}
// added as optional `spatial?: SpatialColumnMetadata` on SQL Data Plane ColumnMetadata AND on QsResultColumn
```

- The SqlClient driver needs a supported, case-insensitive, **exact** identity check for SQL Server's two system spatial types, explicitly excluding aliases/custom CLR UDTs. `EngineType` (`DataTypeName`) alone may be insufficient; Phase 0 must decide whether `DbColumn.DataType` or `UdtAssemblyQualifiedName` is needed. Provider identity stays inside the SqlClient driver — it must not leak into SQL Data Plane contracts (baseline §7.4; addendum §5.1).
- Webview derives eligibility from stable `QsResultColumn` spatial metadata; **no duplicate eligibility list in coarse `QsState`** (baseline §10.4 item 1).
- Tab **never auto-opens**; existing auto-switches to Messages (terminal error/no data) and Query Plan (plan runs) are preserved (baseline §11.1; addendum §3.1).
- Hide the tab if there are no eligible non-plan result sets. A per-result-grid map action opens Spatial with that set/column preselected. One set + one spatial column ⇒ preselect; multiple ⇒ keep panel-local prior selection if still valid, else first eligible pair deterministically (baseline §11.1).
- MVP loads only **completed result sets and terminal partial sets**. Preparation is gated on an authoritative terminal `execution.kind` and a stable `store.summary(resultSetId)`. **Do not use `results.streaming`** — it is false during `cancelRequested` before terminal state (baseline §10.4; code anchor: `executionHost.ts` — `results.streaming` true only for `executing`). Progressive viewing during execution is a later milestone.

## 3. Wire/value contract (addendum REPLACES the baseline shape)

**Critical collision (EXE-A2, addendum §4.2.1, §9.4):** the grid helper `isTypedCellWrapper` in `extensions/mssql/src/sharedInterfaces/queryStudioGridOps.ts` treats any non-`truncated` `{$t: string, v: string}` as a generic scalar wrapper whose default display is `wrapper.v`. The baseline's `{"$t":"spatial","v":"<base64>"}` shape would show raw base64 WKB in grid/copy/text/cell-document/export. **The spatial payload must use `wkb`, never `v`.**

Canonical v1 shapes (addendum §4.2.2, verbatim):

```json
{ "$t": "spatial", "version": 1, "status": "ok", "kind": "geometry",
  "encoding": "wkb", "srid": 0, "wkbBytes": 21, "wkb": "<base64 OGC WKB>" }
```

```json
{ "$t": "spatial", "version": 1, "status": "unrenderable", "kind": "geometry",
  "reason": "maxCellBytes", "sourceBytes": 12345678, "sourceDigest": "sha256:<digest>" }
```

TypeScript union (verbatim names): `SpatialKind = "geometry" | "geography"`; `SpatialCellOkV1`; `SpatialCellUnavailableV1` with `SpatialTransportReason = "maxCellBytes" | "conversionFailed" | "unsupportedNativeValue" | "unsupportedInterchange"`; union `SpatialCellEncodingV1`.

v1 minimalism rules (addendum §4.2.2):
- Do NOT add `hasZ`, `hasM`, `empty`, `approximated`, normalized digests, or `display` until the provider matrix proves semantics and a consumer needs them. Derive empty/geometry type in the decoder.
- `sourceDigest` (SHA-256 of the **exact native UDT bytes**, not normalized WKB) only for values not otherwise represented, only when the full native stream was already read+hashed.
- Do NOT put render-policy reasons (e.g. `geographyLineUnsupported`) in the STS2 sentinel — transport status ≠ render policy (EXE-A9).
- Repeating `kind` per cell is deliberate self-description; changing that is a contract revision.
- No partial WKB, ever, in any sentinel (baseline §7.3).
- `srid` is per value (one column can mix SRIDs); optional on oversized sentinels.

**Negotiation (addendum §5.2, verbatim):** initialize result `{"capabilities": {"spatialWkbV1": true}}`; per-execute `{"options": {"spatialEncoding": "wkb-v1"}}`. Advertisement alone does not change value shapes; client opts in per execute; normalized option appears in effect arguments and replay identity; non-opted-in clients get prior safe behavior; unsupported option is rejected/ignored by an explicit compatibility rule.

**Driver abstraction (addendum §5.3):** provider-neutral `DriverSpatialValue { Kind, Srid, Wkb, SourceBytes?, SourceDigestHex? }` and `DriverSpatialUnavailableValue { Kind, Reason, Srid?, SourceBytes?, SourceDigestHex? }`. Provider CLR types (`SqlGeometry`/`SqlGeography` via `Microsoft.SqlServer.Types`) stop at the SqlClient driver boundary; the dependency needs explicit dependency-matrix/cross-RID approval (baseline §7.5). Spatial reading is a new classified cell-read mode, not a `GetValue()` fallback special case. Read native UDT bytes incrementally under `SequentialAccess`, check cancellation between chunks, hash while draining, convert only bounded values, recheck WKB size after conversion; Phase 0 must bound/measure the non-cancelable synchronous conversion step (baseline §8.1).

## 4. Byte accounting and transport safety

Byte vocabulary (baseline §7.3, exact meanings): `sourceBytes` (exact native UDT bytes), `sourceDigest` (SHA-256 of those bytes), `wkbBytes` (raw WKB length pre-base64), `wireValueBytes` (UTF-8 length of complete tagged cell JSON incl. field names/base64/quotes), `pageBytes` (exact UTF-8 of encoded page rows+wrappers), `frameBytes` (UTF-8 of complete JSON-RPC message vs `MaxFrameBytes`).

Current service defaults (`Sts2Defaults.cs`): 1,000 page rows, 256 KiB page bytes, **1 MiB `maxCellBytes`**, 4 unacked pages, **64 MiB frame ceiling**. `maxCellBytes` is lower-only — Query Studio cannot raise the 1 MiB ceiling; spatial cells above it are unsupported sentinels in MVP (baseline §7.3).

Known holes spatial exposes (baseline §6.2/§7.3; addendum §4.3 + code anchors):
- `WireValueEncoder.cs` / `Encode`: bounds only `string`/`byte[]`; unknown provider objects fall to invariant `Convert.ToString` — bypasses `maxCellBytes`.
- `SqlRowsPageBuilder.cs`: unknown objects get a small fixed estimate; one oversized row becomes its own page — defeats `pageBytes`.
- `DriverEffectRunner.cs`: compact `encodedBytes` currently uses `rowsJson.Length` — a **UTF-16 char count**, not bytes.

Layering (EXE-A15-adjacent, addendum §4.3): driver = recognition/bounded read/canonical value/source-byte facts; runtime encoder = tagged JSON + exact UTF-8 size; page packer = packs already-encoded rows; transport writer = measures complete frame vs `MaxFrameBytes`. **Preferred:** encode-once → `EncodedRow { node/json, utf8Bytes }` → exact page packer → final frame measurement (a separate protocol-foundation change, not smuggled into the map PR). **Minimum acceptable preview path (addendum §4.3.2):** bound native+WKB under the per-cell ceiling; honest conservative driver estimate incl. base64+wrapper; STOP claiming exact `pageBytes` while approximate; **hard final complete-frame UTF-8 guard before transport (non-negotiable)**; stable typed row-too-large failure; never drop rows/cells or emit partial WKB.

## 5. P0 prerequisites (blockers before any spatial payload ships)

1. **Compact capture privacy leak (PR 1).** `CaptureElision.cs` / `ElideInput` elides only top-level `rows`; Query Studio uses compact rows, so `compact.values` + `compact.nullBitmap` are journaled in full. Fix: when `driver.queryEvent` has `eventType: "rows"`, wrap whichever complete payload is present (`rows`, `compact`, or both); elide the whole compact object incl. `values`, `nullBitmap`, `typeHints`; null bitmap is result data; restore only at the wire/effect edge; preserve digest/replay identity; clean side-table entries on success/suppression/error/cancel/disposal; canaries in journal/replay export/diagnostic export/failure paths (baseline §7.1; addendum §4.11, EXE-A14). No WKB in compact rows until canaries pass.
2. **Canonical bounded spatial cell** — §3 above (baseline §7.2).
3. **Cell/page/frame bounds** — §4 above (baseline §7.3).
4. **Exact provider recognition** — §2 above (baseline §7.4).
5. **Provider/RID evidence matrix** (baseline §7.5): Windows/Linux/macOS RIDs × SQL Server/Azure SQL: `GetValue`/`GetSqlValue` CLR types, `GetBytes` under `SequentialAccess`, null/empty, all shape classes, invalid geoms, Z/M/ZM, CircularString/CompoundCurve/CurvePolygon, `FullGlobe`/larger-than-hemisphere/poles/antimeridian, huge cells + cancellation while draining, conversion latency, cancellation during synchronous `Microsoft.SqlServer.Types` deserialization / `STAsBinary()`.
6. **All tagged-value consumer safety** — §8 below (baseline §7.6; contract blocker, not cleanup).

## 6. Host preparation service and RPC contract

### 6.1 Authority rules (EXE-A4, EXE-A6, addendum §4.5)
- Webview supplies **selection only** — never budgets, store IDs, snapshot IDs, source IDs, run IDs, or lease authority. Budgets resolve from the extension-host query-results parameter registry; effective limits are returned as information only.
- `IQueryResultStore.runId` is the authoritative run identity, used internally. `execution.startedEpochMs` is a webview UI reset key only, never data authority. Sessions return only an opaque `handle` + random `generation`.
- Controller binds the session to the live `RetainedRowStore` or pinned snapshot it already owns; acquires a `QueryResultStoreLease` with a new lease-owner kind **`spatialView`**; reads use new `RowReadReason` **`"spatial"`** (no protected-cache promotion, cooperative chunking, cancellation between windows, frozen row-count clamp, aggregate-only diagnostics — baseline §10.3).

### 6.2 RPC shapes (addendum §5.4, verbatim key names)
- `QsSpatialOpenParams { resultSetId, spatialColumn, labelColumn? }`
- `QsSpatialOpenResult { handle, generation, summary: QsSpatialFrozenSummary }` where the summary carries `resultSetId, rowCount, complete, truncatedReason?, corrupt, spatialColumn, labelColumn?, effectiveBudget: { maxRows, maxPayloadBytes, maxLabelBytes, targetResponseBytes, maxResponseBytes }`
- `QsSpatialNextParams { handle, generation, sequence }`
- `QsSpatialSourceFeature { resultRowOrdinal, spatial: SpatialCellEncodingV1, label?, labelTruncated? }` — **`resultRowOrdinal`, not `sourceRow`** (EXE-A8); zero-based within the bound live/pinned result view; optional `originRowOrdinal` only when explicitly known, never invented.
- `QsSpatialHostProgress { sourceRowsScanned, sourceRowsTotal, candidateCells, nullCells, transportUnavailableCells, payloadBytes, partial, partialReason? }` with `partialReason ∈ "rowBudget" | "payloadBudget" | "timeBudget" | "cancelled" | "storeShortRead" | "storeCorrupt"`
- `QsSpatialFeatureChunk { handle, generation, sequence, scannedRowStart, scannedRowEndExclusive, features, progress, payloadBytes, done }`
- `QsSpatialCancelParams { handle, generation }`

**Request/response RPC only for open/next/cancel; never stream feature data through notifications.** Receipt of `next` is the backpressure boundary.

### 6.3 Chunk construction rules (addendum §5.4.1)
- Scan in ascending `resultRowOrdinal`; include entries only for non-null spatial cells (pick and test ONE policy for empty/unavailable: entries with row-level reasons vs counted + on-demand detail).
- Clamp labels by **UTF-8 bytes**, not JS string length.
- End a response before the feature that would exceed the soft target; one feature may exceed soft only if it fits the hard max (1 MiB raw-WKB ceiling ⇒ 2 MiB hard max covers base64 + wrappers). A feature that cannot fit the hard max ⇒ typed session partial reason, advance/terminate deterministically — no infinite loop on one row.
- Measure `Buffer.byteLength(JSON.stringify(response), "utf8")` in the host before returning; conservative cap below transport max.
- Counts describe only the scanned prefix until `done` after a complete scan.

### 6.4 Session state machine and lifecycle (addendum §4.5.1)
`open -> reading -> completed | cancelled | expired`. Rules: open freezes selected result summary + effective budgets; at most one in-flight `next` per handle; monotonically increasing sequence; random generation rejects stale/recycled handles; `cancel` idempotent; rerun / source disposal / result-column change / panel disposal / whole-panel hide cancel active sessions; use **`webviewPanel.visible`, not `active`** for hide cleanup (split panels stay visible while inactive); **on final `done: true` remove the session and release the lease immediately (EXE-A7)** — completion, not just cancel/hide, releases; expiry releases lease + buffered state; per-controller and global concurrency caps; handles have bounded max count. Host-side `panel.onDidChangeViewState` synchronously cancels/releases handles even if the webview does not respond (baseline §14.5). No shared host prepared cache or multicast in MVP; two panels over one model must not create unbounded duplicate scans.

### 6.5 Sparse projection (EXE-A5, addendum §4.4)
Existing store APIs support one contiguous column span; two one-column reads can deserialize the same spill frame twice (non-grid scans are not readmitted to the viewport cache). **If the label selector ships in the first slice, general sparse projection must land first (PR 5); otherwise remove the label selector.** API: add `columnOrdinals?: readonly number[]` to `CellWindowRequest` and `RowStreamRequest`; mutually exclusive with the contiguous span; validate once/dedupe/preserve requested order; project `columns`, `typeHints`, values, null bitmap in that order; include ordered projection in the served-window cache key; implement through `RowStore`, `RetainedRowStore`, snapshot reads, and derived-window stitching (fix the derived path that currently fetches complete parent rows). Do not hide a repeated dual-read loop in the controller as production architecture.

### 6.6 Module placement (addendum §5.5, §5.6)
Host: `extensions/mssql/src/queryResults/spatial/` — `spatialTypes.ts`, `spatialSessionManager.ts`, `spatialResultReader.ts`, `spatialBudget.ts`, `spatialDiagnostics.ts`, `liveSpatialReadSource.ts`, `pinnedSpatialReadSource.ts`. Controller: bind service to owned store/snapshot, register RPC handlers, cancel on rerun/hide/disposal, never scan rows itself. `SpatialSessionManager`: handles/generations, budgets, leases, one-in-flight, sequence/expiry/concurrency, invoke reader, value-free diagnostics. `SpatialResultReader`: sparse projected windows `reason: "spatial"`, preserve ordinals, clamp labels, prefix counts, stop on budgets/cancel, **never parses WKB or imports renderer code**.
Webview: `extensions/mssql/src/webviews/pages/QueryStudio/spatial/` — `SpatialResultsPane.tsx`, `SpatialToolbar.tsx`, `SpatialStatus.tsx`, `SpatialFeatureList.tsx`, `spatialDecode.ts`, `spatialProjection.ts`, `spatialOlAdapter.ts`, `spatialSelection.ts`, `spatialTypes.ts`. `app.tsx` keeps orchestration only (eligibility, active tab, chosen result/column, lazy boundary, visibility/cancel trigger) — no WKB parsing, grouping, map construction, or pull loops in `app.tsx`.

## 7. Rendering approach

**Renderer: OpenLayers (`ol` package), BSD-2-Clause**, Canvas vector rendering, no tile layer, no hosted-map controls; extension-owned DOM toolbar (theming/l10n/keyboard/CSP predictability) (addendum §3.3). Why OL: map with zero layers works offline; `ol/format/WKB` reads WKB/EWKB with projection options; projection API supports built-ins/custom/optional Proj4; documented keyboard/focus behavior; Canvas + WebGL options; modular ESM (baseline §9). MapLibre only if product pivots to hosted cartography; deck.gl future overlay; Leaflet fallback-grade; custom Canvas/WebGL rejected. Dependency policy: add only `ol`; exact module imports; lazy-load component + renderer chunk on first activation; bundle everything locally (code/CSS/fonts/workers/assets), no CDN; no Turf/Proj4/deck.gl/MapLibre/SQL-spatial JS parser without measured requirement; record min+compressed chunk size and update third-party notices (baseline §9).

**Decode strategy (EXE-A12, addendum §4.8):** incremental **main-thread** parsing with cooperative yields — no worker in the first implementation. Steps: lazy-import WKB reader + map modules post-activation; decode one host chunk at a time; validate base64 length against `wkbBytes` before parsing; catch parser exceptions per cell; count coordinates immediately post-parse, discard pre-commit if over vertex budget; consistent derived-memory estimate, stop before the feature that crosses the limit; commit in small batches; yield at the work-slice deadline; cancel host pull on terminal local budget. If fuzzing shows parser count fields cause pathological work, add a lightweight WKB structural preflight scanner — not a second renderer. Worker justification requires repeatable traces (long tasks, delayed input, missed first paint, polygon stalls) under approved caps; if added later: versioned messages, `ArrayBuffer` transfer, plain geometry data (not OL instances), `worker-src` CSP, explicit esbuild entry (Monaco worker pattern exists in `scripts/bundle-webviews.js`), WebWorker TS lib config (baseline §14.3).

**Camera/grouping:** auto-fit once after the first meaningful accepted batch; never move a user-touched viewport on later chunks; max zoom for single/few points. Mixed SRIDs (EXE-A11, addendum §4.9): group by `(kind, SRID)`; activate the first renderable group in source-row order; keep it for the session unless the user changes it; never re-space accepted features, never overlay incompatible groups; show group counts as scanned-prefix facts; fit only the active group; advance deterministically if the active group has no renderable feature; unknown transform ⇒ native coordinates + basemap disabled. Antimeridian: fit geography points via unwrap on the largest longitude gap (naive minX/maxX near ±179° zooms to the whole world).

**Projection policy (baseline §12):** native Cartesian identity, EPSG:4326, EPSG:3857, plus only OL built-in transforms with test coverage. No internet projection lookup; Proj4 only after demonstrated need through a reviewed offline path. Coordinate-order (X/Y vs lon/lat) tests are mandatory through WKB → renderer → pointer readout → fit.

**Supported render matrix (addendum §3.2, locked):** `geometry` Point/LineString/Polygon + Multi*/GeometryCollection (standard linear OGC forms) — required, native Cartesian; `geometry` 4326 = straight geometry semantics (optional 4326 view, not geography semantics); 3857 = native projected with tested transforms; other SRIDs = native Cartesian, no invented transform; `geography` Point/MultiPoint — required, lon/lat + antimeridian-aware fit; `geography` lines/polygons/multis/collections — **transported but explicitly unsupported by the MVP renderer** (`unsupportedSemantics`) unless Phase 0 proves exact or bounded geodesic rendering — SQL Server geography edges are short great-elliptic arcs, and **straight projected chords are prohibited** (baseline §8.2, §12); curves + `FullGlobe` research-gated; Z/M: 2D display only, never imply elevation/measure; null/empty counted not rendered; sentinels counted with transport reason. Never `MakeValid()`/repair/simplify/sample/densify/reproject silently.

**Four-stage status model (EXE-A9/A10, addendum §4.7):** Transport (`ok`, `maxCellBytes`, `conversionFailed`) owned by STS2/Data Plane; Decode (`decoded`, `decodeFailed`, `vertexBudget`) owned by webview decoder; Semantic support (`renderable`, `unsupportedGeographyEdge`, `unsupportedCurve`, `unsupportedSridTransform`) owned by render policy; Topology validity = `unknown` unless a provider-derived fact — never inferred from parsing; parser rejection is `decodeFailed`, not `invalid`. No hidden per-cell `STIsValid()` database calls in MVP.

**Offline baseline (baseline §13.1):** offline = **zero network requests** (not tolerated failures). Every compatible result gets theme-aware background, extent + coordinate readout, Cartesian axes/grid for planar, graticule + scale for geography, fit/zoom/pan/selection/details/feature list. **World-outline asset: deferred out of the first slice (MVP decision, addendum §3.1)** — later candidate is Natural Earth 1:110m (public domain), preconverted at build time, notices updated. Online tiles/satellite = separate milestone (Phase 5) with its own consent/allowlist/HTTPS/attribution/SecretStorage/CSP/legal design; never hardcode `tile.openstreetmap.org`; tiles disclose viewed location — provider name may be logged, tile URL/viewport/extent/coordinates may not (baseline §13.2).

**CSP (EXE-A13, addendum §4.10; baseline §16.2):** current `webviewBaseController.ts` (~239-270) emits **no CSP meta** and has inline style — reviewed docs claiming strict CSP are wrong. Add a per-surface hook on `WebviewBaseController`: `WebviewCspOptions { enabled, allowWorker?, extraImgSources?, extraConnectSources? }`; `default-src 'none'`; local scripts/chunks/styles/images/fonts via `${webview.cspSource}`; nonce or relocate the inline style + Query Studio boot-relay script; `worker-src` only if worker chosen; remote `img-src`/`connect-src` absent. Migrate Query Studio + pinned results first; global webview migration tracked separately — do not convert every webview in the map patch. CSP cannot widen dynamically; provider changes need a reload flow.

## 8. Ordinary-consumer display contract (shared cell codec)

New isomorphic dependency-light module `extensions/mssql/src/sharedInterfaces/queryResultCellCodec.ts` (addendum §4.2.3): tagged-value interfaces, strict structural guards, wire normalization shared by compact and noncompact STS2 paths (today `sts2Backend.ts` normalizes only truncated tags on noncompact rows and passes compact tagged objects through), and purpose-specific formatting:

```ts
export type CellTextPurpose = "gridPreview" | "copy" | "textView" | "cellDocument"
    | "csvExport" | "jsonExport" | "insertExport" | "toolSummary";
export function cellTextForPurpose(value, metadata, purpose): string;
```

Policy for `status: "ok"`: grid preview = localized summary like `GEOMETRY, SRID 0, 21 WKB bytes`; tooltip/details = type/SRID/bytes/status, no base64; cell document = exact WKB as SQL-style `0x` hex; copy = WKB hex within budget else honest large-cell behavior; text view = WKB hex or approved bounded text; CSV/JSON = exact WKB hex string; INSERT = tested `geometry::STGeomFromWKB`/`geography::STGeomFromWKB` with hex + SRID (explicit tested fallback until then); AI/tool = metadata summary only unless an explicit result-data grant exists. `status: "unrenderable"` ⇒ honest localized description with reason + byte count. Hard invariants: **no base64 in ordinary UI; no `[object Object]`; no raw tagged JSON; no generic `$t` fallback consuming the spatial tag; no export silently dropping the value; compact and noncompact paths normalize identically.** Do not enable `spatialEncoding: "wkb-v1"` until these tests pass. High leverage: `cellDocument.ts` and `resultExport.ts` (CSV/JSON/INSERT) all flow through shared display text today (addendum §11 anchors).

## 9. UI structure, views, row identity

**Tabs:** `Results | Spatial | Messages | Query Plan` when eligible. Label **Spatial**; accessible name/empty states **Spatial results**. Spatial is not a third grid/text mode; it fills the pane and participates in splitter/maximize/resize (baseline §11.1).

**Layout (baseline §11.2):** toolbar row — result-set selector (eligible sets only), spatial-column selector (metadata-confirmed), label-column selector (default None — only if PR 5 lands), `Fit`, `Layers`, `More`, zoom buttons; full-width canvas; collapsible selected-feature detail drawer (never a permanent sidebar), optionally sharing a region with the feature list behind `Features`/`Details` tabs; status bar like `12,450 features shown | 8 skipped | SRID 4326 | Offline`. No color-by/tooltip-config/measure/edit/heatmap/extrusion in MVP.

**Interaction (baseline §11.4):** points = stable screen-space radii + selected outline; lines = min pixel width + halo; polygons = translucent fill + opaque boundary, holes preserved; collections keep one source-row identity; null/empty/unrenderable counted, not drawn; hover optional and never the only inspection path; click/Enter selects and opens persistent details; details fetch extra row fields on demand (never attach whole rows to features); map shows the bounded source result in source-row order — grid sort/filter is NOT inherited as a map transform; labels off by default for dense data; wheel zoom only when map focused.

**Row identity + reveal (EXE-A6/A8, addendum §4.6):** `resultRowOrdinal` = zero-based ordinal in the bound live/pinned result view. Grid sort/filter is webview-local, so reveal maps in the webview: select → switch to Results → grid registry maps ordinal → display order → scroll/select/focus; if filtered out, preserve the filter and offer **`Clear filter and reveal`**. `QueryResultContextService` gets a distinct spatial selection kind carrying `resultRowOrdinal`; it must NOT claim an `active: { row, column }` display cell until mapping succeeds. No host round trip for a sort/filter state the host does not own.

**Truth states (baseline §11.5):** distinguish preparing / complete full scan / terminal partial (persistent warning + reason) / feature-row budget (`Showing N features from the first R of T rows; remaining feature count unknown`; skips labeled `in scanned rows`) / vertex-byte-time budget (keep prepared features + reason) / mixed SRIDs (group, never silent overlay) / unsupported shape (counted, row-level reason in list) / renderer unavailable (feature list + details stay usable; offer Results, not a blank canvas) / offline (normal baseline, no error banner) / online provider failure (nonfatal, separate, geometry remains).

**Accessibility (baseline §15; addendum §7.7):** canvas must never be the sole interface. DOM toolbar; focusable named map target; arrows pan, `+`/`-` zoom; **virtualized DOM feature list** keyed by source row exposing label/geometry type/row/SRID/selected state, with correct `aria-setsize`/`aria-posinset` or paged table semantics, retained logical focus across unmount, Home/End, text search over bounded labels; activation selects/highlights/fits; map selection syncs list without stealing focus; polite live region announces preparation/first paint/partial counts/selection; `Reveal in Results`; hover info duplicated in details. Visual: shape/outline/width/dash in addition to color; VS Code theme/chart tokens; forced colors; `vscode-reduce-motion` + `prefers-reduced-motion` (no animated fly-to); 200% zoom + narrow panes. Tabs: keep `tablist`/`tab`/`aria-selected`, add stable IDs, `aria-controls`, `aria-labelledby`, `role="tabpanel"`, roving focus/arrow keys; design the F6 focus-region sequence (none exists today). All strings through the l10n bundle from the first patch. Acceptance = keyboard/screen-reader user can activate tab, choose result/column, read status, navigate features, select + hear row/type/SRID/label, fit, reveal in Results, understand filtered-out, return without losing selection.

**Panel vs model state (baseline §14.5):** camera, selected columns, inspector, layer choices are panel-local; result data is model-shared. Tab-switch away cancels in-flight pulls (parsed source may stay panel-local while visible; OL target detached when inactive); whole-panel hide synchronously cancels/releases host handles; disposal/rerun follow the same idempotent cleanup.

## 10. Performance requirements and budgets

**Amended unopened-cost invariant (EXE-A1, verbatim intent):** gate disabled ⇒ no spatial encoding requested, execution unchanged. Gate enabled + spatial columns ⇒ STS2 may perform bounded recognition/native-byte-read/canonicalization **during the ordinary forward-only row stream whether or not the tab is ever opened** (forward-only reader ⇒ unavoidable; the honest promise is "bounded canonical capture during the opted-in query, then zero secondary work until the tab opens", addendum §9.3). Until the tab opens: no secondary result-store scan, no WKB browser decode, no OpenLayers import, no worker, no map construction, no feature list, no GPU/canvas prep. Two mandatory baselines: (a) nonspatial query + gate on ⇒ negligible capability-check overhead; (b) spatial query + tab unopened ⇒ measured canonicalization cost, zero host secondary reads, zero renderer load.

**Non-negotiable invariants (baseline §14.1):** no regression to STS2 credit/ack, query completion, grid first paint, viewport cache; no whole-result copy into coarse webview state; every scan cancellable + `reason: "spatial"`; every payload bounded; no partial WKB; background scans never promote pages into the grid protected cache; hidden/disposed panels release handles and don't accumulate workers/GPU buffers; two panels over one model never cause unbounded duplicate scans.

**Budgets (addendum §3.4 — authoritative first-implementation defaults; all registered in the query-results parameter registry; host-authoritative, webview cannot raise):**

| Budget | Value | Authority |
| --- | ---: | --- |
| Rows scanned | 25,000 | Extension host |
| Total spatial-session response payload | 32 MiB | Extension host |
| Per-response soft target | 1 MiB | Extension host |
| Per-response hard maximum | 2 MiB | Extension host |
| Label preview bytes per cell | 4 KiB (UTF-8) | Extension host |
| Decoded/render vertices (incl. geodesic/curve expansion) | 250,000 | Webview decoder |
| Derived decode/render memory estimate | 64 MiB | Webview decoder |
| Rows per store window | 500–1,000 | Extension host |
| Main-thread work slice | 8 ms target | Webview scheduler |

Host is authoritative for scanned rows, serialized bytes, handle lifetime, observed wire statuses; decoder for parsed type, vertices, derived memory, invalid/approximation, render work; UI merges and labels every count with observed scope (baseline §14.2). The 32 MiB total does not raise the 1 MiB per-cell ceiling. No reservoir sampling/simplification in MVP — deterministic prefix, honest and row-addressable. Chunks parse/commit incrementally so **first paint precedes full bounded preparation**; pan/zoom/select stays responsive at cap. No formal latency gates before stable samples; existing Query Studio scenarios are the unopened non-regression bar (baseline §17.4). Bundle proof: inspect esbuild metafile + packaged VSIX; confirm dynamic chunks aren't pre-evaluated AND lazy-module CSS isn't merged into eager `queryStudio.css` (baseline §14.3).

## 11. Observability, diagnostics, test plan

**Markers (baseline §17.1, registry-first, one process/role each):** host — `mssql.queryResults.spatial.prepare.begin` (result-set-count bucket, source mode `live`/`pinned`), `.prepare.end` (scanned-row/byte/feature buckets, terminal status, budget-reason enum, duration bucket), `.prepare.cancel` (reason enum, scanned-row bucket); webview — `mssql.queryResults.spatial.render.begin` (renderer mode, offline/provider ID), `.render.firstPaint` (feature/vertex buckets, partial bool, duration bucket), `.render.settled` (rendered/skipped buckets, fallback mode, duration bucket), `.render.cancel` (reason enum only). Bucketed/enum values only in production; exact counts/durations/handles only in a test-only `PERF_MODE` probe never feeding diagnostics/telemetry. Never log coordinates/bounds, WKT/WKB/GeoJSON, labels/properties, column/table/db/server/query names, raw SRID + location, tile URLs, credentials. **First paint definition:** OpenLayers `rendercomplete` after ≥1 accepted feature committed to the active generation (rAF/mount insufficient). Pipeline stages measured separately: tab open → first store chunk → WKB parse → first feature committed → first `rendercomplete` → bounded prep complete → render settled (baseline §17.2).

**Perftest (baseline §6.4, §17.3):** existing `dev/query` Query Studio scenario family conventions apply (exploratory-first, registered markers only, no sleeps, guarded completion, no result values). New SQL fixtures: 10k geography points (deterministic coords), 100k points, mixed shapes, complex polygons with holes/controlled vertex counts, geometry SRID 0, 4326 + 3857, mixed SRIDs, null/empty/invalid/curves/Z-M/`FullGlobe`/oversized, multi-set/multi-column. Scenarios: `querystudio-spatial-10k-offline` (first accepted-feature `rendercomplete`; host scanned-rows proof + webview accepted-features/generation proof), `querystudio-spatial-complex-polygons`, `querystudio-spatial-budget` (host reason and webview partial agree), `querystudio-spatial-rerun-cancel` (old handle cancelled, no stale feature), `querystudio-spatial-pinned` (source editor closes, snapshot valid), `querystudio-spatial-pan-select` (test-only semantic probe). **Zero-network proof lives in Playwright** unless perftest gains request interception. Perftest guidance is design-level (addendum was not code-verified against perftest).

**Test plan highlights** (baseline §18; addendum §7 additions):
- Contract collisions (addendum §7.1): spatial tag with `wkb` fails `isTypedCellWrapper`, passes only the spatial guard; malformed `{$t:"spatial", v}` rejected, not generic; compact/noncompact pages byte-for-byte equivalent neutral cells; explicit unknown-`$t` fallback policy.
- Ordinary consumer matrix (addendum §7.2): renderable + unrenderable through grid/tooltip, sort/filter, copy cell-row-range, text view, cell document, CSV, JSON, INSERT, transform compare/project, AI/tool under allowed+denied grants, spill/restore, pinned — assert absence of base64 / raw tag JSON / `[object Object]`.
- Unopened-cost (addendum §7.3): gate on + tab unopened ⇒ conversion only for spatial cells; `RowReadReason: "spatial"` count zero; no session; no `ol` chunk requested/evaluated; no scheduler/worker; no canvas/map; grid baseline holds. Nonspatial ⇒ no spatial branch entered.
- Sparse projection (addendum §7.4): distant columns in-memory + spilled (one materialization per page), reversed/duplicate/invalid/empty ordinals, retained store, frozen clamp, derived mapping, null-bitmap/type-hint alignment.
- Session lifecycle (addendum §7.5, all assert lease count + spill cleanup): normal final chunk, user cancel, tab switch mid-pull, column change, rerun before/after chunks, hidden-not-disposed, split inactive-but-visible, disposal, expiry, duplicate cancel, concurrent `next`, stale generation, wrong sequence, controller cap, global cap, short read/corruption.
- Fidelity (addendum §7.6): X/Y + lon/lat orientation; both WKB endiannesses if producible; empties; polygon holes/ring orientation; nested GeometryCollection identity; late-chunk mixed SRIDs; geometry-4326 straight semantics; geography points at 179/−179 + poles; **geography line/polygon rejection with no canvas geometry created**; curves/`FullGlobe` per final matrix; Z/M per interchange evidence; corrupt count fields/parser exceptions; one cell at/below/above every source/WKB/wire/frame threshold.
- Service (baseline §18.1): `WireValueEncoderTests`, spatial-reader units (chunk boundaries, sync-conversion timing/failure, digest, cancellation), `SqlClientEngineTests` RID matrix, `QueryFlowTests` (negotiation/downgrade/replay), `DigestCaptureTests` (canaries), `SqlRowsPageBuilderTests` (exact pageBytes + frame guard + typed oversized-row), geography fidelity fixtures, `DependencyMatrixTests` (`Microsoft.SqlServer.Types` driver-only), YAML scenarios.
- Privacy (addendum §7.8): unique coordinate/label canaries absent from STS2 journals, replay bundles, diagnostic exports, extension logs, error messages, production markers, webview perf marks, online requests (none permitted); test success+failure, compact+legacy, hidden/disposed.
- E2E (baseline §18.4): real SQL, conditional tab, first-paint definition, nonblank pixel checks, fit + no overlap at narrow widths, zero network, keyboard-only select/fit/reveal, all theme/contrast/zoom/motion modes, two split panels, disposal/rerun mid-prep, axe scan (`@axe-core/playwright` if dependency review passes) + manual screen reader.

## 12. Framework capabilities SPATIAL forces (that vector alone would not)

The shared pane framework (built first) must provide these, at framework-shaping depth. Items marked (S) are spatial-specific pressures a numeric vector-debugger tab would likely not force on its own:

1. **(S) Large binary cell payloads end-to-end:** tagged binary-carrying cells (base64 in JSON) up to the 1 MiB `maxCellBytes` ceiling, with exact `wireValueBytes`/`pageBytes`/`frameBytes` UTF-8 accounting, a final pre-transport frame guard vs the 64 MiB ceiling, typed row-too-large outcomes, and complete non-renderable sentinels (never partial payloads).
2. **(S) Per-execute encoding negotiation:** initialize capability advertisement (`spatialWkbV1`) + per-execute option (`spatialEncoding: "wkb-v1"`) propagated through command validation, reducer normalization, journaled effect args, replay identity, and downgrade rules. The framework's tab-eligibility model must combine column metadata with per-run negotiated capabilities (a tab can be ineligible for a rerun of the same query).
3. **Opaque host-authoritative pull sessions:** `open`/`next`/`cancel` request-response RPC; handle + random generation + monotonic sequence; one in-flight `next` as backpressure; per-response soft/hard byte caps + total session cap measured via `Buffer.byteLength(JSON.stringify(...), "utf8")`; expiry; per-controller/global concurrency caps; lease release on `done: true` as well as cancel/hide/dispose/expiry. (Spatial's 32 MiB / 2 MiB numbers make this mandatory; a small vector pane could have gotten away with a single response.)
4. **Store lease + read-reason extension points:** new lease-owner kinds (`spatialView`) and `RowReadReason` values (`"spatial"`) with the no-viewport-cache-promotion scan contract, controller-bound live AND pinned read-source adapters, and webview-supplies-selection-only authority (no store/snapshot/budget identifiers cross the boundary).
5. **(S) Sparse column projection** (`columnOrdinals` on `CellWindowRequest`/`RowStreamRequest`) through RowStore, retained stores, snapshots, derived windows, cache keys, null bitmaps, and type hints — driven by spatial's spatial-column + distant-label-column pattern over spilled pages.
6. **(S) Progressive chunked rendering:** incremental chunk commit with first paint before full preparation, auto-fit-once camera policy, stable behavior when later chunks change the picture (mixed-`(kind,SRID)` group pinning), and scanned-prefix-vs-total honesty in every count the UI shows.
7. **(S) Heavy lazy third-party renderer loading:** dynamic import of a large external library (OpenLayers) on first activation with proof (metafile + VSIX) that neither JS nor CSS loads eagerly; optional worker-entry pattern reserved (Monaco precedent in `scripts/bundle-webviews.js`); third-party notice process.
8. **Per-surface CSP hook** on `WebviewBaseController` (`WebviewCspOptions`; `default-src 'none'`; optional `worker-src`; opt-in per surface) — spatial's zero-network guarantee and future tile allowlists make this a framework prerequisite, adopted by Query Studio + pinned first.
9. **(S) Coordinate/projection subsystem seam:** native Cartesian vs EPSG:4326 vs EPSG:3857 policies, coordinate-order correctness testing, antimeridian-aware fit, and the four-stage status split (transport / decode / semantic-support / topology-validity) so render policy never contaminates wire status.
10. **Shared tagged-cell codec** (`queryResultCellCodec.ts`, `cellTextForPurpose` with `CellTextPurpose`): any new `$t` tag must register purpose-specific display for grid/copy/text/cell-document/CSV/JSON/INSERT/tool before its encoding is negotiable — the generic `{$t, v}` wrapper trap applies to every future pane's payloads.
11. **Row-identity + reveal contract:** `resultRowOrdinal` semantics, webview-local grid-registry mapping to display rows, filter-preserving `Clear filter and reveal`, and a non-display `QueryResultContextService` selection kind until mapping succeeds.
12. **Panel lifecycle discipline:** panel-local vs model-shared state split; `webviewPanel.visible`-based (not `active`) synchronous host-side cleanup on `onDidChangeViewState`; split-panel duplicate-scan caps; idempotent cancel shared across rerun/hide/dispose/expiry.
13. **Accessible parallel representation pattern:** a canvas-based pane must ship a synchronized virtualized DOM list + details view, live-region announcements, and the tab/F6/roving-focus semantics — framework should make this a reusable structure, not a spatial one-off.
14. **Registry-first observability:** registered fixed-role bucketed markers per process (host `prepare.*`, webview `render.*`), test-only `PERF_MODE` exact probe, value-free diagnostics, privacy canary harness, and renderer-anchored first-paint definition (`rendercomplete` + accepted feature).
15. **Terminal-state gating helper:** authoritative `execution.kind` terminal + frozen `store.summary` (explicitly not `results.streaming`, which lies during `cancelRequested`) — any completed-result-first pane needs this exact gate.
16. **(S) Budget registry integration:** all knobs in the existing query-results parameter registry, host-authoritative, echoed to the webview as `effectiveBudget` information only.

Explicitly NOT framework scope (addendum §8.5, §9.6): no generic map-provider abstraction, no universal visualization framework — a renderer adapter boundary per pane is enough; spatial stays concrete.

## 13. Dependency-ordered PR plan (addendum §6) and gates

1. **PR 1** (`sqltoolsservice`) compact capture privacy fix + canaries — exit: no compact values/null patterns in persisted capture.
2. **PR 2** (`vscode-mssql`) tagged-cell codec + ordinary consumer safety — exit: synthetic spatial tag never base64/raw JSON/`[object Object]`; no capability enabled yet.
3. **PR 3** (`sqltoolsservice`) provider/RID evidence, exact recognition, bounded reader, WKB v1 tag + sentinel, capability + execute option, frame guard + row-too-large, exact packer or documented minimum path — exit: fixtures round-trip normal+compact across RID matrix; no partial WKB, no over-limit frame.
4. **PR 4** (`vscode-mssql`) Data Plane + Query Studio metadata, both-row-path validation, RowStore/retained/pinned round trip, downgrade tests — exit: opted-in run stores safe neutral values; consumers correct.
5. **PR 5** (`vscode-mssql`) general sparse projection — exit: one materialization pass returns spatial + distant label in requested order. If deferred: label selector removed from PR 7.
6. **PR 6** (`vscode-mssql`) spatial host session service (`spatialView` lease, `spatial` reason, live+pinned adapters, sessions, budgets, exact response measurement) — exit: no React row scan; no webview authority; leases/spill release on every terminal path.
7. **PR 7** (`vscode-mssql`) offline UI vertical slice (tab, grid action, lazy OL Canvas, geometry linear + geography points, Cartesian/4326/3857, incremental decode, budgets, SRID grouping, fit/select/details/list, honest states, a11y, l10n, surface CSP, zero-network tests) — exit: matrix renders offline; no straight-chord geography; unopened ⇒ no scan/import.
8. **PR 8** (`vscode-mssql`) reveal/context/pinned parity + pinned CSP — exit: live+pinned share contracts; ordinals never confused with display rows.
9. **PR 9** (all three repos) perf/perftest/release hardening (fixtures, markers, unopened baselines, bundle/VSIX measurement, budget tuning, worker/WebGL only with evidence) — exit: preview docs, rollback, matrix, privacy complete.

Phases (baseline §19): Phase 0 evidence (capture fix, RID matrix, `Microsoft.SqlServer.Types` conversion validation, byte-term specs, geography-edge decision, OL spike, main-thread-vs-worker benchmark, bundle proof, marker registration, budget seeds); Phase 1 STS2/Data Plane contract; Phase 2 preparation service; Phase 3 offline tab MVP behind `mssql.queryStudio.spatial.enabled`; Phase 4 perf hardening; Phase 5 optional online basemap (separate project — never blocks offline viewer).

**Stop conditions (addendum §10.3, enforce during build):** capture canaries leak; RID matrix can't identify exact system types; spatial tag reaches a generic wrapper branch; any consumer shows base64/raw JSON/`[object Object]`; a complete row can pass the writer above the frame ceiling untyped; label projection needs unbounded span/repeated spill reads without approved sparse projection; any lifecycle path leaves a lease held; mixed SRIDs overlay without proven transform; geography line/polygon coords reach the renderer without approved geodesic policy; a hidden surface keeps pulling/parsing/retaining; a production marker contains coordinates/extent/label/SRID+location/WKB/tile URL/result identifier.

**Prohibited shortcuts (addendum §10.2, condensed):** no SQL rewriting (`STAsText()`/`STAsBinary()`/`STSrid`); no string/binary column inference; no `String()`/`JSON.stringify()` display policy; no `v` for WKB; no provider CLR objects past the driver; no React loop over `qs/getRows`; no webview authority; no second authoritative row/parsed cache; no unknown SRIDs on a world basemap; no straight-chord geography edges; no unmeasured validity claims; no silent repair/simplify/sample/densify/reproject; no worker/WebGL/online map/world asset/generic provider abstraction without evidence; no remote CSP hosts; no all-webview CSP migration in the map patch; no exact-pageBytes claims while approximate; no lease retained past a normal final chunk; no result-ordinal-as-display-row before mapping.

## 14. Code anchors (dev/query; symbols are the durable reference — lines drift)

`sqltoolsservice`: `src/sts2/Microsoft.SqlTools.Sts2.Runtime/Coordination/CaptureElision.cs` (`ElideInput` wraps only top-level `rows`; baseline cites :49-77); `.../Effects/WireValueEncoder.cs` (`Encode`, string/byte[]-only bounds; :24-116); `.../Effects/DriverEffectRunner.cs` (`rowsJson.Length` UTF-16 count; string hints for unknown engine types; :401-590); `src/sts2/Microsoft.SqlTools.Sts2.Drivers.SqlClient/SqlClientSession.cs` (`PumpResultSetAsync`, spatial falls to sync `GetValue`, `DataTypeName` → `ColumnInfo.EngineType`; :121-215); `SqlLargeValueReader.cs` (text/binary only, sync loops without per-chunk token checks; :35+); `SqlRowsPageBuilder.cs` (approximate pages, small fixed unknown estimate; :65+); `Sts2Defaults.cs` (defaults; :9+).

`vscode-mssql` (`extensions/mssql/src/`): `services/sts2/sts2Backend.ts` (noncompact normalizes only truncated tags; compact passes tags through; spatial → string hints; :154-164, 742-845); `sharedInterfaces/queryStudioGridOps.ts` (`isTypedCellWrapper`, `cellDisplayText` — the `{$t, v}` trap); `sharedInterfaces/queryStudio.ts` (`QsResultColumn`; :125-145, 234-250); `queryStudio/rowStore.ts` (reasons lack spatial; contiguous projection only; :6-24, 37-82, 342-554); `queryStudio/cellDocument.ts` + `queryStudio/resultExport.ts` (shared display text ⇒ codec leverage); `queryResults/queryResultTypes.ts` (`IQueryResultStore`: `runId`, leases, windows, streams, summaries; :48-120); `queryResults/resultStoreLease.ts` (`RetainedRowStore` disposes store on final release); `queryResults/queryResultAccessService.ts` (snapshot windows contiguous; derived-window parent fetch ignores projection; :419-554); `queryStudio/executionHost.ts` (random run ID per run; `results.streaming` excludes `cancelRequested`); `queryStudio/queryStudioController.ts` (row RPC → ExecutionHost; no spatial view-state cleanup; :112-135, 499-550); `queryResults/pinnedResultsController.ts` (controller-bound snapshot = correct authority pattern); `queryResults/queryResultContextService.ts` (display-like `{row, column}` only today); `webviews/pages/QueryStudio/app.tsx` (local tabs; `startedEpochMs` reset key; webview-local sort/filter; :101, 1317-1379, 1639-1813); `controllers/webviewBaseController.ts` (no CSP meta, inline style; :239-270); `scripts/bundle-webviews.js` (ESM splitting + Monaco worker entry; :14-73).

`perftest`: existing Query Studio scenario family + result-shape fixtures on `dev/query`; no spatial fixtures/probes yet; expected changes in `perftest/packages/observability-contracts/**`, scenario registries, mssql perf driver (baseline §19 change map). Note: extension has **no existing** MapLibre/OpenLayers/Leaflet/deck.gl/Turf/Proj4/WKT/WKB dependency (baseline §6.3).

## 15. Open questions still requiring decisions (subset most likely to shape the framework)

Geography line/polygon policy (points-only vs exact vs densification with declared ellipsoid/tolerance — Phase 0 gate); curve/`FullGlobe` handling; exact grid/copy/export representation sign-off; SRIDs beyond 0/4326/3857; worker need under caps; Canvas vs WebGL point tier; pinned parity in first milestone vs immediately after; sparse projection vs deferred label; remote/Codespaces RPC bandwidth budget; CSP shared-foundation-first vs all-webview migration; preview-gate rollback criteria (baseline §21 full list, items 1-31).
