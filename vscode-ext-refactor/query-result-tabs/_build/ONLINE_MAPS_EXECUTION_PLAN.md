# Spatial Map Layers — Execution Plan (SPA-10 / online maps addendum)

**Status:** ACTIVE
**Date:** 2026-07-14
**Normative inputs:** `geospatial_pane_online_maps_addendum.md` (wins on conflict), then
`geospatial_pane_execution_addendum.md`, `geospatial_pane.md`, `SPATIAL_DESIGN_AND_EXECUTION_PLAN.md`.
**Base:** SPA-0..8 DONE (offline slice green), SPA-9 PARTIAL, SPA-10 = this plan.
**Commit prefix:** `qs: spatial — …` (vscode-mssql), `core:` (perftest). Decision IDs continue D-00NN.

## 1. Scope of this stretch

Implements the addendum's PR 1–PR 4 with the Azure Maps adapter (PR 5) explicitly
deferred, condensed into four checkpoints MAP-1..MAP-4 plus a contracts-first MAP-0.
"Earth map" ships two ways: the bundled offline **World outline** (no network, no host
session, works in pinned panes) and **configured host-proxied XYZ raster sources**
(consented, trusted; Query Studio panel only at first — extended to pinned documents
by D-0035).

## 2. Locked decisions (delta log)

| ID | Decision |
|---|---|
| D-0021 | Whole Layers capability behind NEW `mssql.queryStudio.spatial.basemap.enabled` (default false, application scope). `spatial.enabled` stays independent; rollback of layers never affects the offline pane. |
| D-0022 | Tile handoff: host cache file → `asWebviewUri` → OpenLayers XYZ `tileLoadFunction`. NO CSP change: `img-src <cspSource>` already admits cache URIs once the cache dir joins `localResourceRoots` (narrow add of `globalStorageUri/spatial-basemap-cache` ONLY). `connect-src` unchanged. |
| D-0023 | World outline asset = `world-atlas@2.0.2` `land-110m.json` (Natural Earth derivative, public domain), copied at bundle time to `dist/views/spatial-world-land-110m.json` (~108 KB), fetched lazily from the webview resource origin only when the layer is selected, decoded with `topojson-client` inside the lazy spatial chunk. ThirdPartyNotices updated. No graticule in v1. |
| D-0024 | World outline is webview-local: no host session, no RPC, no consent (offline). Available in pinned panes for free. Online layers are QS-panel-only in v1 (pinned controller registers no basemap RPCs; the pane degrades honestly). |
| D-0025 | Layers selector is a toolbar `<select>` matching the established spatial toolbar idiom (NOT a Fluent menu — deviation from addendum §4.1 widget choice; its semantics are honored: None always available, incompatible/untrusted explanations shown in the status row, attribution overlaid on the map). |
| D-0026 | v1 auth: none, or one reviewed mode — `credentialRef` names a SecretStorage key (`mssql.spatialBasemap.<sourceId>`) injected host-side as `Authorization: Bearer <secret>`. No query-param secrets, no configured headers. |
| D-0027 | Consent: modal on INTERACTIVE selection only (`open(interactive:true)`); restore (`interactive:false`) never prompts — returns `consentRequired` and the pane renders None with a status explanation. Consent recorded in globalState under sha256(sourceId + normalized template + kind + attribution); invalidated on fingerprint change; `MS SQL: Clear Spatial Map Layer Consent` clears all. |
| D-0028 | Cache: memory LRU 16 MiB + disk under `globalStorageUri/spatial-basemap-cache/<fingerprintHash>/z/x/y.bin`, keyed by HMAC-SHA256 (per-install random key in globalState) — never raw URLs. Budget `cache.maxMb` (default 128), age `cache.maxAgeDays` (default 30), eviction by bytes then age, `MS SQL: Clear Spatial Map Cache` command. |
| D-0029 | Limits registered in code as `SPATIAL_BASEMAP_LIMITS` const (per-panel 4 / global 12 in-flight, 2 MiB tile, 10 s timeout, 1 transient retry, zoom 0..22 clamped by source). No prefetch anywhere: OL requests only viewport tiles; adapter bounds its own in-flight set; host enforces. |
| D-0030 | Eligibility: basemap (outline or online) available only when every rendered feature's decoded projection ∈ {EPSG:4326, EPSG:3857}; any `planar` feature in the active set disables layers with status `Map layer unavailable for this coordinate system`. Selection is REMEMBERED across incompatible groups (renders None) per addendum §4.3. |
| D-0031 | View state: `layerId?: string` on the spatial slice ("none" default omitted; "worldOutline"; or a source id). Carried across rerun like renderer/groupBy. Restore of an online id revalidates source + consent + trust silently. |
| D-0032 | `defaultLayer` setting DEFERRED (addendum allows; fewer consent paths). Azure Maps adapter (PR 5), WMTS/WMS/vector/PMTiles, and an OSM-standard adapter remain out of scope. |
| D-0033 | Online perf scenario vs live internet is NOT added (no controlled tile endpoint in the harness). Online path is proven by unit/integration tests with a fake fetcher + deterministic tiles. Perf scenarios cover world outline A/B + negative proofs. |
| D-0034 | Markers (registered in perftest registry BEFORE emission): extensionHost `mssql.queryResults.spatial.basemap.open` / `.tile.end` / `.close`; webview pair `mssql.queryResults.spatial.basemap.layer.begin` / `.layer.ready` (+ derived metric `mssql.queryResults.spatial.basemap.layerReady`); `render.begin/.firstPaint/.settled` gain `layer` safeEnum (none|worldOutline|xyzRaster) and `offline` becomes honest ("false" iff online layer active). Attrs: enums/buckets only — never URLs, hosts, tile coords, source ids. |
| D-0035 | REVISES D-0024 (2026-07-16, dogfood): online layers gain pinned-document parity. `pinnedResultsController` registers the same four basemap RPCs as thin proxies over the shared extension-level host (consent, trust, cache, fetch policy, and limits all stay host-owned and are shared with live QS), adds the tile-cache dir to its `localResourceRoots` (D-0022 mechanics, derived from context so restore-before-activation holds), and bumps `spatialBasemapEpoch` on basemap config changes so mounted panes re-fetch the layer list. The strict pinned CSP is untouched: tiles are `img-src <cspSource>` loads of local cache URIs, same as D-0022. World-outline-only degradation remains the honest fallback when the host is absent or the gate is off. |

## 3. Checkpoints

### MAP-0 — contracts + scaffolding (perftest `core:`, vscode-mssql `qs: spatial —`)
- Register D-0034 markers + derived metric in `event-types.json`; regenerate; vendor into
  vscode-mssql; vendorSync + observabilityContract conformance green.
- Settings schema in package.json (+nls): `basemap.enabled`, `basemap.sources`,
  `basemap.cache.maxMb`, `basemap.cache.maxAgeDays`; commands `mssql.spatialBasemap.clearCache`,
  `mssql.spatialBasemap.clearConsent` (palette-visible when basemap.enabled).
- Deps: `world-atlas` (dev, data), `topojson-client` (runtime, webview chunk).
Exit: contracts land unused; typechecks + contract tests green.

### MAP-1 — offline World outline (addendum PR 1)
- bundle-webviews.js copies the land asset into dist/views; ThirdPartyNotices entry.
- `spatial/worldOutlineLayer.ts`: lazy fetch + topojson→GeoJSON → `VectorImageLayer`
  under the feature layers; theme-aware (editor-foreground stroke at low alpha, subordinate
  to features); load emits `basemap.layer.begin/.ready {layer:worldOutline}`.
- Layers `<select>` in the spatial toolbar (None / World outline (offline) / online sources
  / Configure…); status chip states; eligibility per D-0030; view-state `layerId` + allow-list
  + rerun carry-forward; `render.*` markers gain `layer`/honest `offline`.
- Tests: eligibility, view-state round-trip, outline decode unit (topojson fixture), bundle
  budget (asset excluded from js ceilings; ol stays lazy), marker conformance.
Exit: compatible data gets an offline earth outline; planar data cannot select it; zero network.

### MAP-2 — host policy foundation (addendum PR 2)
- `src/queryResults/spatialBasemap/`: types, config load+validation (full §5.2 grammar:
  https-only, exactly one {z}/{x}/{y}, no other placeholders/credentials/fragments, id
  grammar+uniqueness, zoom bounds, bounded text attribution, termsUrl https, private-network
  rejection unless `allowPrivateNetwork`), fingerprints, sanitized descriptors; consent store;
  cache-root lifecycle; clear commands wired.
- `qs/spatial.basemap.list` RPC (QS controller) returning sanitized descriptors (+ trust flag).
- Narrow `localResourceRoots` addition for the cache dir.
- Tests: validation matrix, workspace-cannot-inject (application scope read), descriptor
  sanitization canaries (no template/host/credentialRef in RPC results), consent lifecycle.
Exit: config host-validated; no URL/credential path to the webview exists.

### MAP-3 — host-proxied XYZ vertical slice (addendum PR 3)
- Fetcher (injectable; timeout/size/type/redirect/retry per D-0029), tile cache (D-0028),
  session manager (open with consent modal per D-0027 + trust gate + eligibility params,
  per-panel/global concurrency, z/x/y + generation + sequence validation, disposal on
  rerun/hide/layer-change/dispose via `resetSpatialServices`), `qs/spatial.basemap.open/.tile/.close`.
- Webview `spatialBasemapOlAdapter.ts`: XYZ source + `tileLoadFunction` → tile RPC → local
  URI; bounded in-flight; stale-generation abandonment; bounded backoff on transient failure;
  tile failure NEVER degrades feature rendering.
- Attribution overlay (sanitized text + optional terms link via host command); untrusted/
  consent-required/unavailable status states.
- Tests: session manager suite with fake fetcher/consent/trust (addendum §10.1 list),
  cache suite (hit/miss/eviction/fingerprint invalidation/path safety), adapter unit
  (no fetch, bounded retries), privacy canaries (markers/descriptors/errors carry no
  URL/coords/ids), pinned-pane degradation.
Exit: configured HTTPS XYZ layer renders for compatible data; CSP untouched; webview
never sees an endpoint or credential.

### MAP-4 — hardening + perf + release evidence (addendum PR 4 + PR 6 essentials)
- Disk eviction sweep + cache size surfaced in clearCache toast; rerun/hide/dispose/
  source-change cleanup proofs; failure UX polish.
- perftest: scenarios `querystudio-spatial-basemap-worldoutline` (A/B vs
  `querystudio-spatial-points-10k-offline`; measure layer.begin→layer.ready + settled with
  layer attr) and negative proofs (basemap markers absent when gate off / layer None;
  extend unopened scenario's markerAbsent). Perf action `mssql.perf.queryStudioSpatialSelectLayer`.
  Scenario contract tests extended; config.spatial.local.jsonc updated.
- Full gates: tsgo both configs, lint, full unit suite (only the 5 documented pre-existing
  failures), bundle budget, perf smoke run of the spatial config, live A/B vs offline base.
- PROGRESS entry + status board SPA-10 update; EXECUTION_PLAN cross-link.
Exit: addendum "Done for the first online release" list satisfied except deferred items
(D-0032/D-0033), each recorded.

## 4. Stop conditions (inherited + new)
- Any marker/diagnostic/persisted state carrying URL, host, tile coordinate, map bounds,
  credential, or source id in telemetry-visible form → stop, fix, add canary.
- Webview gains any remote fetch path or CSP widens → stop (design violation).
- Planar/unknown-SRID data appears over any world layer → stop.
- Feature rendering regresses when a tile fails → stop.
