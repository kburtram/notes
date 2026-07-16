# Query Studio Spatial Results - Optional Map Layers Addendum

**Status:** Proposed follow-on specification and execution plan  
**Date:** 2026-07-14  
**Applies after:** `geospatial_pane.md` and `geospatial_pane_execution_addendum.md`  
**Primary surface:** Query Studio Spatial tab  
**Owner boundary:** `vscode-mssql` extension host, Query Studio webview, and approved map-data providers

## 0. Purpose and precedence

The offline Spatial tab is intentionally correct for arbitrary SQL Server `geometry`: a coordinate plane must not imply that unknown Cartesian values are locations on Earth. It is nevertheless not sufficient for the common case of `geography` data or `geometry` with SRID 4326/3857, where users need coastlines, streets, or imagery to interpret a feature.

This addendum specifies an **optional, offline-by-default map-layer capability**. It provides a useful orientation layer without weakening the existing privacy, result-ownership, or bounded-work rules.

This document supplements the two existing geospatial documents. It overrides the prior Phase 5 outline with an implementation-ready plan, but it does not change these baseline decisions:

- Spatial remains usable with zero network requests.
- `geometry` with an unknown or arbitrary SRID is never placed on a world map by guesswork.
- The extension host remains the authority for secrets, network policy, disk cache, and provider selection.
- The webview receives no provider credential, endpoint URL, raw tile response header, or arbitrary fetch authority.
- Google Maps/Earth, OpenStreetMap Standard tiles, Azure Maps, and any other provider are not interchangeable technical details; their terms, attribution, authentication, privacy, and cache policy must be respected.

Normative wording in this document uses **MUST**, **MUST NOT**, **SHOULD**, and **MAY** in their usual requirements sense.

## 1. Decision summary

### 1.1 Product decision

Ship two layer classes in increasing order of capability:

| Layer class | Default | Network | Purpose | Initial disposition |
| --- | --- | --- | --- | --- |
| **None** | Selected by default | None | Existing coordinate-canvas behavior | Required |
| **World outline** | Available for compatible data; never auto-selected | None | Low-detail coastline and graticule orientation comparable to a simple SSMS world map | Required first follow-on slice |
| **Configured raster basemap** | Disabled until the user explicitly selects it and accepts the disclosure | Host-only, HTTPS | Streets, satellite, or organization-owned map tiles | Required online vertical slice |
| **Provider adapter** | Disabled until configured | Host-only, HTTPS | A reviewed provider such as Azure Maps, with its own authentication and terms implementation | Second online slice |

The initial online protocol is **host-proxied XYZ raster tiles in Web Mercator (EPSG:3857)**. It is intentionally narrower than “arbitrary maps”:

- It works with the existing OpenLayers dependency and does not require MapLibre or a vector-style runtime.
- It supports the common streets/satellite tile model used by commercial and self-hosted providers.
- It avoids granting the webview remote `connect-src` access.
- It avoids the nested style, glyph, sprite, worker, and subresource policy required by vector-tile style engines.
- It can add a provider adapter later without exposing a generic browser network surface.

`WMTS`, `WMS`, MapLibre style/vector tiles, local MBTiles/PMTiles, terrain, and a Google-specific integration are explicitly follow-on work. They must not be smuggled into the XYZ implementation through an unrestricted URL field or a browser `fetch` fallback.

### 1.2 User-visible behavior

The Spatial toolbar gets a `Layers` command that opens a Fluent menu or popover. The menu has:

1. `None`.
2. `World outline (offline)` when the active spatial group is compatible.
3. A separator and each valid, user-configured basemap source.
4. `Configure map layers...`, which opens the relevant user-level Settings page.

Selecting an online source requires an explicit first-use confirmation for that source and endpoint fingerprint. The confirmation states that tile requests disclose the approximate viewed area to the selected provider. The user can decline without changing the current map.

The status row reports one of the following localized states without exposing an endpoint:

- `Offline`
- `World outline`
- `Layer: <configured display name>`
- `Map layer unavailable for this coordinate system`
- `Online layer disabled in an untrusted workspace`
- `Map layer could not be loaded`

Selection persists only as a source ID in the panel view state. It never persists a URL, credential, raw provider response, tile coordinate, or full attribution HTML. On restore, the ID is revalidated against current user settings and the source must be consented again if its endpoint fingerprint changed.

### 1.3 Coordinate compatibility policy

Online and world-outline layers are available only when the active render group is one of:

| Active group | Vector handling over layer | Layer availability |
| --- | --- | --- |
| `geography`, SRID 4326, supported point semantics | Transform to EPSG:3857 for display | Available |
| `geometry`, SRID 4326 | Transform to EPSG:3857 for display | Available |
| `geometry`, SRID 3857 | Render directly | Available |
| `geometry`, any other SRID including 0 | Native Cartesian display | Not available |
| Any unsupported geography edge, curve, or `FullGlobe` | Existing honest unsupported state | Not available |
| Mixed `(kind, SRID)` groups | One active group at a time | Re-evaluate when group changes |

The existing geography-fidelity rules remain in force. A basemap is not permission to render a geography line or polygon with incorrect straight projected chords. The first online slice supports only the existing renderer’s approved spatial matrix.

No projection definition is fetched dynamically. Support for any SRID other than 4326 and 3857 requires a separately reviewed, locally bundled projection definition and fidelity tests.

## 2. Why this architecture

### 2.1 Recommended model: host-proxied raster tiles

The browser webview MUST NOT directly fetch a remote tile URL. Instead:

```text
SpatialMap / OpenLayers XYZ source
  -> bounded qs/spatial.basemap.tile request: opaque handle + z/x/y
  -> QueryStudioController
  -> SpatialBasemapSessionManager
  -> configured source registry + consent + compatibility validation
  -> tile cache
  -> host HTTPS fetch with provider-specific auth/headers
  -> cache file under dedicated basemap-cache root
  -> controller converts file URI with webview.asWebviewUri
  -> opaque local webview URI returned to OpenLayers
```

The webview’s CSP continues to use `connect-src 'none'` even when an online layer is selected. Its `img-src` remains local `webview.cspSource` plus `data:`. Remote map data crosses only the extension-host boundary, where policy and secrets are enforceable.

This is preferable to remote `ol/source/XYZ` URLs in the webview because it:

- does not disclose a provider key to DevTools or extension-page JavaScript;
- does not need a dynamic CSP origin allowlist;
- allows the host to enforce URL templates, redirects, concurrency, payload limits, cache behavior, and cancellation;
- makes provider attribution and user consent a first-class product decision;
- permits native-client headers where provider terms require application identification;
- gives deterministic tests a fake host fetcher instead of relying on a public internet service.

The cost is a small tile RPC and local-file handoff. It is acceptable because visible raster tiles are bounded, cached, and lower volume than spatial result payloads. The implementation MUST measure the cost before rollout and retain the existing offline renderer as a fallback.

### 2.2 Why not make Google Earth or Google Maps the default

Google Earth is a separate desktop/web product, not a generic tile service for this extension. Google Maps Platform usage is governed by provider-specific SDK, API-key, attribution, billing, cache, and terms requirements. A generic XYZ URL template is not an approved Google Maps integration.

This feature therefore MUST NOT:

- scrape Google Maps/Earth tiles;
- expose a `google` URL shortcut;
- embed a Google Maps SDK or iframe as an unreviewed fallback;
- export query geometry to a third-party map service automatically.

A dedicated Google Maps product integration could be proposed later only after legal, security, and provider-contract review. It is not needed to make the Spatial tab useful.

### 2.3 Why OpenStreetMap Standard tiles are not the default provider

OpenStreetMap data is broadly usable, but the public `tile.openstreetmap.org` service has a separate tile-usage policy. It requires visible attribution, identifiable application traffic, cache compliance, and forbids bulk download/offline prefetch. Availability is best effort and can be withdrawn.

Do not hard-code the OSM Standard endpoint as a product default. A future `osmStandard` adapter may be considered only after it demonstrates policy-compliant attribution, a stable application User-Agent, response-cache behavior, no prefetch, a privacy review, and a provider approval. Organization-owned or commercially contracted sources are the intended first configured sources.

## 3. Scope, non-goals, and provider choices

### 3.1 In scope

- A local, bundled low-detail world outline and graticule for compatible spatial data.
- User-level configuration for a finite list of reviewed XYZ raster source definitions.
- Host-mediated HTTPS tile requests for an explicitly selected source.
- Per-source consent, visible attribution, bounded memory/disk cache, cache clearing, and failure states.
- A provider adapter interface, with Azure Maps as the recommended first reviewed adapter after the generic enterprise source vertical slice.
- A projection/semantics eligibility gate that protects arbitrary planar data.
- Unit, integration, Playwright, accessibility, privacy, and performance coverage.

### 3.2 Explicitly out of scope for the first online slice

- A default internet provider or a silent network fallback.
- Direct remote requests from the webview.
- Arbitrary workspace-supplied tile URLs, styles, JavaScript, HTML, headers, or provider plugins.
- WMS `BBOX` requests, which transmit a more precise geographic extent and have a different request/response model.
- Vector tile styles, sprites, glyphs, 3D terrain, globe mode, geocoding, routing, address search, traffic, or location services.
- Downloading regions for offline use, tile prefetch, bulk tile capture, or tile export.
- Caching secrets, query text, labels, result values, GeoJSON/WKB, or source feature coordinates with tiles.
- Automatically enabling a layer for query results opened in an untrusted workspace.

### 3.3 Provider option assessment

| Option | Fit | Decision | Rationale |
| --- | --- | --- | --- |
| Bundled Natural Earth-style world outline | Excellent privacy/offline fit | First follow-on slice | Gives immediate global context with no provider account or network policy. Asset licensing, size, and notices still require review. |
| Configured organization XYZ raster endpoint | Best initial online fit | First online vertical slice | Common model, works with OpenLayers, keeps provider selection with the customer, and can use host proxy/cache controls. |
| Azure Maps raster adapter | Strong Microsoft/Azure fit | Recommended second online slice | Supports Azure identity and render-specific authorization, but needs an approved authentication and CORS-independent host path. |
| Commercial OSM-derived provider adapter | Potentially strong | Provider-by-provider | Requires contract, attribution, pricing, and cache-policy review. |
| OSM Standard public raster service | Useful but operationally constrained | Not a default | Requires a dedicated policy-compliant adapter; no generic hard-code. |
| WMTS raster | Useful for enterprises | Later | Tile matrix metadata, dimensions, and per-service capabilities add meaningful protocol surface. |
| WMS | Common enterprise protocol | Later | BBOX requests and service capabilities need separate privacy/security design. |
| MapLibre/vector tiles | Rich cartography | Later | Requires styles, sprites, glyphs, worker/CSP setup, and a much larger allowlist/subresource model. |
| MBTiles/PMTiles | Private/offline-friendly | Later | Needs a local archive reader, licensing policy, storage/bundle decisions, and a separate supported-file story. |
| Google Maps/Earth | Familiar | No generic integration | Requires a dedicated provider agreement and implementation, not an endpoint template. |

## 4. Product and UX specification

### 4.1 Layer selector

Add a `Layers` icon command to the existing Spatial toolbar. Use the established Fluent menu/popover pattern, keyboard focus behavior, localized labels, and an accessible menu name. The command is disabled only when no active group supports any locally available layer.

For an incompatible group, the menu still makes `None` available and shows a disabled explanation for map layers. Do not make the user infer why a basemap disappeared after selecting an SRID filter or group.

Each configured item displays:

- configured display name;
- `Online` indicator;
- provider type only where it helps distinguish multiple sources;
- a visible selection state;
- an accessible description that includes the attribution name, not a raw endpoint.

The selected layer’s attribution is always visible over the map, outside the feature canvas and above any opaque map control. It is not hidden in the menu, tooltip, or details panel. Attribution comprises sanitized text and an optional HTTPS terms link opened through a host-approved external-link command.

### 4.2 Consent and trust

The first attempt to select an online source presents a modal confirmation:

> Enable online map layer “{displayName}”? The provider will receive tile coordinates that reveal the approximate area you view. Query results, labels, SQL text, and credentials are not sent as map data.

Actions: `Enable`, `Cancel`, and `View provider terms` when configured. The dialog is localizable and includes the source’s visible attribution.

Consent is stored in extension `globalState` under a hash of the stable source ID, normalized endpoint template, provider type, and attribution identity. It is invalidated when any of those values changes. A setting or command clears all map-layer consent.

Online layers require `vscode.workspace.isTrusted`. In an untrusted workspace, the selector shows the source disabled with a localized explanation and offers no “enable anyway” path. This protects against a query result or workspace state steering a user toward remote requests, even though endpoint configuration itself is user-level.

### 4.3 Defaults and restore behavior

- Initial selection is `none`.
- `World outline` is never auto-selected merely because an SRID looks geographic. This preserves today’s exact zero-network and no-extra-layer default.
- The last selected valid layer may be restored for the same Query Studio panel only after its consent and compatibility checks pass.
- A provider failure never falls back to another online source and never changes the user’s selection silently.
- Switching to an incompatible group keeps the selection remembered but renders `None` and shows the compatibility status. Returning to a compatible group may restore the chosen layer without a second confirmation.
- Closing, hiding, rerunning, and disposing a panel releases active basemap sessions and cancels queued tile work. Cached files remain only under the configured cache policy.

### 4.4 World outline asset

The local orientation layer SHOULD contain a simplified, low-detail coast/land boundary plus optional graticule, not a full street map. It MUST:

- be bundled as a static, locally served asset;
- use an approved source and retain required third-party notices;
- be size-budgeted and loaded lazily only when selected;
- have no labels derived from the query result and no network dependency;
- render only for EPSG:4326/3857-compatible groups;
- use theme-aware styling and remain subordinate to result features;
- not claim geographic accuracy beyond its source/data resolution.

Use a locally converted, audited TopoJSON/GeoJSON asset or an equivalent compact representation. Do not put an unbounded or dynamically fetched world dataset into the VSIX.

## 5. Configuration and credential contract

### 5.1 Configuration scope

All basemap configuration is application/user scoped. It MUST NOT be read from workspace settings, a workspace file, SQL text, query result, or webview message. A workspace must not be able to add an endpoint, credential reference, request header, or provider ID.

Proposed settings:

```json
{
  "mssql.queryStudio.spatial.basemap.defaultLayer": "none",
  "mssql.queryStudio.spatial.basemap.sources": [
    {
      "id": "contoso-road",
      "displayName": "Contoso Road Map",
      "kind": "xyzRaster",
      "urlTemplate": "https://maps.contoso.example/tiles/road/{z}/{x}/{y}.png",
      "minZoom": 0,
      "maxZoom": 19,
      "attribution": {
        "text": "© Contoso Maps",
        "termsUrl": "https://maps.contoso.example/terms"
      },
      "credentialRef": "contoso-road-map",
      "allowPrivateNetwork": false
    }
  ],
  "mssql.queryStudio.spatial.basemap.cache.maxMb": 128,
  "mssql.queryStudio.spatial.basemap.cache.maxAgeDays": 30
}
```

`defaultLayer` remains `none` in the first release. It exists so a user can explicitly opt into an organization-approved layer after a later product decision; it does not cause automatic online activity before consent.

`sources` is a schema-validated array with an intentionally small model. The first implementation accepts only `xyzRaster`. It rejects unknown properties rather than treating them as transport options.

### 5.2 Source validation

The host validates every source at configuration load and again before each session:

- `id` is a stable ASCII identifier, unique after case normalization, and not a reserved built-in ID.
- `displayName` and attribution text are bounded plain text, not HTML.
- `urlTemplate` is HTTPS, has no fragment, contains exactly one each of `{z}`, `{x}`, and `{y}`, and contains no other placeholders.
- The normalized URL has no embedded credentials, username, password, `data:`, `file:`, `javascript:`, or unsupported scheme.
- `minZoom` and `maxZoom` are finite integers within supported bounds and `minZoom <= maxZoom`.
- `termsUrl`, when present, is HTTPS.
- `credentialRef`, when present, is a key name only. It is not a secret and must not be a URL query parameter.
- A source targeting loopback, link-local, or private network addresses is rejected unless the user has explicitly set `allowPrivateNetwork: true` and confirmed an additional warning. The implementation must account for DNS rebinding and redirects; it cannot validate only the original hostname string.
- Redirects are rejected by default. A provider adapter may enable a fixed, reviewed redirect policy later.

The validation result is a sanitized `BasemapDescriptor` sent to the webview. It contains source ID, display name, kind, attribution text/link, zoom bounds, and compatibility metadata only. It never contains the template, host name, credentials, cache key, headers, consent record, or internal error detail.

### 5.3 Credentials

Credentials live only in VS Code `SecretStorage`, under names owned by the extension such as `mssql.spatialBasemap.<sourceId>`. They are created, updated, and deleted by explicit extension commands/UI, not by a settings value.

For the initial configured XYZ source, allow exactly one reviewed authentication mode per source implementation:

- no authentication; or
- one provider-defined static secret injected by the host into an approved request location.

Do not accept arbitrary configured headers, query parameters, cookies, bearer-token templates, scripts, or auth callbacks. Such flexibility is an endpoint-proxy framework, not a map-layer feature.

Azure Maps is a provider adapter, not a generic secret template. The preferred design is Microsoft Entra authentication with a render-only role, acquired in the extension host through approved Azure identity plumbing. Shared keys or SAS tokens require separate security review and remain host-only. The webview never receives an Azure access token, SAS token, or subscription key.

## 6. Host module and contracts

### 6.1 Required module placement

Create a separate extension-host module rather than extending `SpatialSessionManager` with network, secrets, and cache concerns:

```text
extensions/mssql/src/queryResults/spatialBasemap/
  spatialBasemapTypes.ts
  spatialBasemapConfig.ts
  spatialBasemapSourceRegistry.ts
  spatialBasemapConsent.ts
  spatialBasemapSessionManager.ts
  spatialBasemapFetcher.ts
  spatialBasemapTileCache.ts
  spatialBasemapDiagnostics.ts
  providers/
    basemapProvider.ts
    xyzRasterProvider.ts
    azureMapsRasterProvider.ts             # later provider-specific PR

extensions/mssql/src/sharedInterfaces/
  spatialBasemap.ts

extensions/mssql/src/webviews/pages/QueryStudio/spatial/
  SpatialBasemapControl.tsx
  spatialBasemapOlAdapter.ts
  spatialBasemapTypes.ts
  worldOutlineLayer.ts
```

`SpatialSessionManager` continues to own bounded result-row preparation. `SpatialBasemapSessionManager` owns only provider-session and tile behavior. The two are joined in the Query Studio controller and webview pane, not by allowing either service to take responsibility for the other’s data.

### 6.2 Host responsibilities

`SpatialBasemapSourceRegistry`:

- loads and validates user-level source configuration;
- exposes sanitized descriptors;
- resolves a source ID to a trusted provider implementation;
- computes source fingerprints for consent/cache invalidation;
- does not expose raw configuration to the webview.

`SpatialBasemapSessionManager`:

- opens opaque, panel-bound sessions;
- enforces workspace trust, consent, source validity, source compatibility, and per-panel/global concurrency;
- validates request sequence, zoom range, tile coordinate range, and cancellation;
- releases sessions on selection change, panel hide/dispose, rerun, expiry, or configuration change;
- never accepts a URL, header, credential, or source configuration from the webview.

`SpatialBasemapFetcher`:

- issues HTTPS requests only through injected/testable host networking;
- enforces timeout, redirect, response-size, content-type, and concurrency rules;
- attaches provider-owned authentication and identity headers;
- records only value-free, bucketed diagnostics;
- returns typed failures rather than raw provider response text.

`SpatialBasemapTileCache`:

- keeps a bounded memory cache and a bounded persistent cache below a dedicated `globalStorageUri/spatial-basemap-cache` root;
- keys entries with a keyed hash of the source fingerprint and `z/x/y`, never a raw provider URL;
- honors provider cache policy where approved;
- evicts by byte budget and age without prefetching;
- writes restrictive file permissions where supported;
- implements `Clear Spatial Map Cache` and `Clear Spatial Map Consent` commands;
- treats cache metadata as sensitive viewed-area history and never sends it to telemetry.

### 6.3 RPC contract

Use separate opaque RPCs. Do not overload result-stream requests and do not send a remote tile URL to the webview.

```ts
export interface QsSpatialBasemapListResult {
    readonly layers: readonly QsSpatialBasemapDescriptor[];
}

export interface QsSpatialBasemapDescriptor {
    readonly id: string;
    readonly displayName: string;
    readonly kind: "none" | "worldOutline" | "xyzRaster";
    readonly minZoom?: number;
    readonly maxZoom?: number;
    readonly attribution: {
        readonly text: string;
        readonly termsUrl?: string;
    };
    readonly online: boolean;
}

export interface QsSpatialBasemapOpenParams {
    readonly layerId: string;
    readonly activeProjection: "EPSG:4326" | "EPSG:3857" | "planar";
}

export interface QsSpatialBasemapOpenResult {
    readonly handle: string;
    readonly generation: number;
    readonly tileProjection: "EPSG:3857";
    readonly minZoom?: number;
    readonly maxZoom?: number;
    readonly status: "ready" | "consentRequired" | "incompatible" | "untrusted" | "unavailable";
}

export interface QsSpatialBasemapTileParams {
    readonly handle: string;
    readonly generation: number;
    readonly sequence: number;
    readonly z: number;
    readonly x: number;
    readonly y: number;
}

export interface QsSpatialBasemapTileResult {
    readonly generation: number;
    readonly sequence: number;
    readonly status: "ready" | "notFound" | "cancelled" | "unavailable";
    readonly localUri?: string;
}
```

`localUri` is a `webview.asWebviewUri` value scoped to the current Query Studio webview and backed by a cache file. It is not a remote URL. A session can return at most one tile per request. The webview may request tiles only for the active viewport, and the host limits all request rate and total concurrency.

Consent is a host-owned action, not a Boolean supplied with `open`. The webview asks to select a source; the controller invokes the host confirmation UX where necessary, then opens a session only after confirmation succeeds.

### 6.4 Query Studio controller integration

`QueryStudioController` owns a lazily created `SpatialBasemapSessionManager`, analogous to but independent from the current spatial result service. It must:

- register `list`, `open`, `tile`, and `close/cancel` RPC handlers;
- cancel a basemap session when its matching Spatial tab becomes hidden, a new layer is selected, the result run changes, or the controller is disposed;
- recompute sanitized source descriptors when relevant application settings change;
- add only the dedicated basemap-cache directory, not all global storage, to this webview’s `localResourceRoots`;
- reissue `asWebviewUri` for a cached file on the owning webview only;
- leave `connect-src 'none'` intact in `WebviewBaseController`.

The current controller has extension-root-only local resource access. The implementation must extend its local roots narrowly to `globalStorageUri/spatial-basemap-cache`, after ensuring the directory exists. It MUST NOT grant the webview all of `globalStorageUri`.

### 6.5 OpenLayers adapter

`spatialBasemapOlAdapter.ts` creates an OpenLayers `XYZ` source with a custom `tileLoadFunction`. It converts a requested tile coordinate into one bounded host RPC and sets the returned opaque local URI on the image tile.

Rules:

- The adapter MUST NOT call `fetch`, construct a remote URL, or use an OpenLayers remote URL template.
- It limits its own pending tile requests and abandons stale image loads when the map generation changes.
- It clears the layer and revokes object URLs, if any, on source change/unmount.
- It cannot retry indefinitely. The host communicates a typed failure and the adapter uses a bounded retry/backoff policy only for transient provider failures.
- It never treats a tile failure as a feature-render failure.
- The vector-feature layer remains above the basemap layer.

The world outline uses a local vector layer and does not create a basemap session or any tile request.

## 7. Network, privacy, cache, and security rules

### 7.1 Data disclosure model

An online raster tile request reveals an approximate viewed area through `z/x/y`, source choice, timing, IP address, and normal HTTPS metadata. It MUST NOT intentionally contain:

- query text, database/server/table/column names, row labels, WKB/WKT/GeoJSON, or selected feature properties;
- raw map bounds, raw coordinate pairs, result counts, result-set IDs, source row ordinals, or SQL connection information;
- VS Code session tokens, extension telemetry identifiers, or credentials in logs/diagnostics;
- workspace-controlled query parameters or arbitrary headers.

The disclosure dialog and product documentation must say that tile coordinates reveal the approximate viewed area. Do not describe online maps as private merely because feature data is not serialized in the request.

### 7.2 Request limits

Initial seed limits, to be registered in a host-owned parameter registry and tuned by evidence:

| Limit | Initial value | Rule |
| --- | ---: | --- |
| Per-panel concurrent tile fetches | 4 | Additional visible tiles queue; stale requests cancel first. |
| Process-wide concurrent tile fetches | 12 | Prevent split panels from multiplying traffic. |
| Tile response body | 2 MiB | Reject before cache/write/decode when exceeded. |
| Fetch timeout | 10 seconds | Typed unavailable result; no infinite retry. |
| Retry attempts | 1 | Only transient network/5xx class; no retry on 4xx or policy rejection. |
| Persistent cache budget | 128 MiB | User configurable within a bounded range. |
| Cache max age | 30 days | Subject to stricter provider cache headers/terms. |
| Memory cache budget | 16 MiB | Per extension process. |
| Zoom range | Provider configuration bounded by 0 through 22 | Validate before fetching. |

Do not prefetch a ring of tiles, a region, another zoom level, or an anticipated pan path. A user-visible viewport is the only fetch trigger.

### 7.3 Cache rules

The cache is a privacy-sensitive optional performance mechanism, not an offline-map feature. It MUST:

- cache only successful, validated raster bytes and non-secret cache metadata;
- honor approved provider HTTP cache directives; use no persistent cache when provider policy prohibits it;
- avoid `Cache-Control: no-cache` unless a provider adapter specifically requires it;
- never serve a cached tile after its source fingerprint changes;
- have a clear command and surfaced cache size in Settings;
- avoid indexing cache entries by raw URL or storing credentials in file names, sidecars, or logs;
- remain unavailable to other webview resources outside the dedicated cache root.

The extension must not claim that cached online tiles make a provider’s online map available offline. That behavior requires explicit provider permission and is outside this scope.

### 7.4 CSP and local resources

The current per-surface CSP foundation is sufficient only if the online layer continues to use host-cached local URIs. Required policy invariants:

```text
default-src 'none'
script-src <nonce> <webview.cspSource> blob:
style-src <webview.cspSource> 'unsafe-inline'          # existing foundation; tighten separately
img-src <webview.cspSource> data:
font-src <webview.cspSource>
connect-src 'none'
worker-src <local/blob only when required>
```

Do not append `https:` to `img-src` or `connect-src` as a shortcut. Do not permit arbitrary image hosts because a setting happens to contain a URL.

## 8. Provider implementation model

### 8.1 Provider interface

```ts
export interface BasemapProvider {
    readonly kind: "xyzRaster" | "azureMapsRaster";
    validate(source: BasemapSourceConfig): BasemapValidationResult;
    fingerprint(source: BasemapSourceConfig): string;
    getTile(request: BasemapTileRequest, cancellation: vscode.CancellationToken): Promise<BasemapTile>;
    cachePolicy(source: BasemapSourceConfig, response: BasemapFetchResponse): BasemapCachePolicy;
}
```

The interface is internal to the extension host. Its request object contains a validated source configuration and tile coordinate; it does not contain webview objects or spatial result values. Its response contains bytes, validated media type, cache instructions, and typed status. It must not surface arbitrary headers or provider error bodies to the UI.

### 8.2 `xyzRasterProvider` v1

`xyzRasterProvider` is the first implementation. It:

- substitutes only validated `z`, `x`, and `y` placeholders;
- supports PNG, JPEG, and WebP response types after sniffing/validation;
- uses host HTTPS networking with a finite timeout and no default redirects;
- supports no auth or one reviewed host-injected secret mode;
- passes configured attribution through the sanitized descriptor;
- has no browser-side URL, key, or request-header surface.

The initial generic provider is for user/organization-owned or contracted endpoints. It is not a promise that every public URL template is legally or technically compatible.

### 8.3 Azure Maps adapter

Azure Maps is the recommended first built-in provider adapter because the extension already has Azure dependencies and identity surfaces. It should be a separate PR after the generic XYZ path is proven.

Requirements:

- use an Azure Maps render-only authorization model, preferably Microsoft Entra with least-privilege render access;
- acquire tokens in the extension host through approved existing Azure authentication plumbing;
- store no token in webview state, a tile filename, diagnostics, telemetry, or configuration;
- use Azure Maps’ documented render endpoint/model rather than pretending it is a generic anonymous XYZ service;
- make account/client configuration user-level and validate it before enabling;
- document required Azure Maps CORS only if a direct browser path is ever proposed; the host-proxy path should not depend on webview CORS;
- expose Azure Maps attribution and terms visibly;
- handle expired credentials and denied access as typed, recoverable layer errors.

Shared keys and SAS tokens are sensitive. They may be supported only through SecretStorage and an explicit security review. An Azure Maps implementation must not place a subscription key in `package.json`, a settings value, a tile URI, a webview RPC, or source control.

### 8.4 Future source kinds

Each source kind needs a provider implementation and a distinct privacy/terms review:

- `wmtsRaster`: fixed reviewed tile matrix set and dimensions; no raw capability document interpreted in the webview.
- `wmsRaster`: separate design due BBOX disclosure and render parameters.
- `mapLibreStyle`: a full subresource policy for style JSON, vector tiles, sprites, glyphs, images, worker behavior, and attribution; no generic style URL.
- `pmtiles`: local archive indexing, trusted-file selection, licensing, package-size/storage policy, and a local-only renderer path.

## 9. Implementation phases and pull-request plan

Keep `mssql.queryStudio.spatial.enabled` default-off throughout development. Add a separate default-off gate, `mssql.queryStudio.spatial.basemap.enabled`, so the offline spatial preview can remain usable if online-layer work is rolled back.

### Phase 0 - Approval and technical spike

**Deliverables**

1. Product/security/legal approval of the disclosure text, data-flow diagram, provider policy, cache policy, and world-outline asset license.
2. A local OpenLayers spike showing an EPSG:4326 feature over a bundled world outline and an EPSG:3857 feature over a mock XYZ source.
3. A controller/webview spike that writes a synthetic raster tile under a dedicated cache root, returns `asWebviewUri`, and renders it with `connect-src 'none'`.
4. A measurement of map first paint, tile RPC latency, cache hit behavior, memory, cache files, and panel-hide disposal.
5. A decision on the first reviewed online source: generic organization XYZ only, or generic XYZ plus Azure Maps adapter.

**Exit criteria**

- The webview makes no remote browser requests.
- A cached local URI renders in OpenLayers with the current CSP.
- No secret, endpoint, tile coordinate, or spatial value appears in persisted diagnostics.
- World-outline licensing and third-party notice requirements are approved.

### PR 1 - Offline world outline

**Repository:** `vscode-mssql`  
**Feature behavior:** optional local orientation layer; zero network

Deliver:

- audited bundled outline asset and notice update;
- `worldOutlineLayer.ts` with EPSG:4326/3857 eligibility;
- Layers selector with `None` and `World outline (offline)`;
- view-state persistence, selection, accessibility, localization, theme, high-contrast, and compatibility status;
- unit/component/Playwright proof of zero network and nonblank reference layer.

Exit:

- Common geography points and 4326/3857 geometry have a useful offline orientation option.
- Arbitrary planar geometry cannot select it.

### PR 2 - Basemap configuration and host policy foundation

**Repository:** `vscode-mssql`  
**Feature behavior:** no network provider enabled yet

Deliver:

- shared basemap interfaces and host module scaffolding;
- application-only settings schema and source validation;
- sanitized descriptor/list RPC;
- consent state, clear-consent command, cache configuration schema, and diagnostic vocabulary;
- dedicated cache-root lifecycle plus narrowly scoped Query Studio `localResourceRoots` support;
- tests proving a workspace cannot inject or override a source.

Exit:

- Configuration is host-validated, sanitized, localizable, and has no raw URL/credential path to the webview.

### PR 3 - Host-proxied XYZ raster vertical slice

**Repository:** `vscode-mssql`  
**Feature behavior:** explicit online layer from a configured mock/organization source

Deliver:

- `xyzRasterProvider`, host fetch abstraction, tile cache, opaque session/generation model, and tile RPC;
- timeout, size/type/redirect/concurrency/rate/cancellation enforcement;
- source-consent dialog and workspace-trust gate;
- OpenLayers custom tile loader using only local returned URIs;
- attribution overlay and typed unavailable states;
- test-only fake fetcher and deterministic tiles.

Exit:

- A user can choose a configured HTTPS XYZ layer for compatible data.
- The webview CSP remains `connect-src 'none'`.
- Secrets, URLs, and raw tile coordinates do not cross webview state/diagnostics boundaries.

### PR 4 - Cache, lifecycle, and resilience hardening

**Repository:** `vscode-mssql`  
**Feature behavior:** production-quality configured XYZ source

Deliver:

- persistent cache eviction, response cache-policy handling, clear-cache command, and cache-size reporting;
- robust source-change, consent-invalidation, rerun, split-panel, hide, dispose, and stale-generation cleanup;
- failure UX, bounded retry, and performance markers;
- security/privacy test canaries and an end-to-end controlled HTTP(S) fixture.

Exit:

- No unbounded files, stalled tile queue, stale tile flash, or cross-panel credential/session leakage.

### PR 5 - Azure Maps adapter, if approved

**Repository:** `vscode-mssql`  
**Feature behavior:** selected Azure Maps raster layer

Deliver:

- provider-specific configuration/validation and SecretStorage/identity commands;
- render-only Entra authentication integration with least privilege;
- Azure-specific attribution, response/cache/error policy, and tests with a fake token/fetch boundary;
- documentation of account setup and support limitations.

Exit:

- Azure Maps works without exposing an access token or subscription key to the webview.
- The provider meets product, security, legal, and billing review requirements.

### PR 6 - Release hardening and follow-on decision

**Repository:** `vscode-mssql` and any required test/perftest repositories

Deliver:

- cross-platform tests, bundle/VSIX analysis, accessibility review, telemetry review, docs, and support guidance;
- baseline performance comparison for offline Spatial, world outline, cache hit, cache miss, and unavailable provider;
- explicit decision whether to pursue WMTS, WMS, MapLibre/vector tiles, PMTiles, OSM Standard adapter, or a Google-specific proposal.

Exit:

- Online capability is independently feature-gated and can be rolled back without affecting offline Spatial.

## 10. Test and acceptance plan

### 10.1 Host/unit tests

- source validation: duplicate IDs, invalid placeholders, HTTP, embedded credentials, arbitrary placeholders, invalid zooms, invalid attribution/terms URLs, private-network opt-in, redirects, and endpoint fingerprint changes;
- configuration scope: workspace/folder settings cannot enable or override sources;
- SecretStorage: secret never appears in descriptor, RPC, URI, cache metadata, logs, diagnostics, or telemetry;
- consent: first use, decline, re-consent after endpoint change, clear command, untrusted-workspace refusal;
- provider fetch: timeout, cancellation, body limit, invalid media type, image sniff mismatch, 4xx/5xx, redirect refusal, concurrency, one retry maximum, and no prefetch;
- cache: hit/miss, expiration, source-fingerprint invalidation, budget eviction, clear cache, safe file path construction, cache root isolation, and no raw URL key;
- sessions: opaque handles, stale generation, invalid z/x/y, duplicate sequence, panel cancellation, source configuration change, and global/panel caps;
- projection eligibility: only approved 4326/3857 groups can open an online session.

### 10.2 Webview/component tests

- Layers selector keyboard and screen-reader behavior;
- compatible/incompatible group transitions;
- `None`, world outline, consent-required, untrusted, loading, ready, and failure states;
- local URI tile handoff without a browser `fetch` call;
- attribution visibility at narrow widths, zoom, high contrast, and reduced motion;
- selection persistence never includes raw source configuration or secrets;
- vector features remain readable and selectable above a high-contrast/light/dark basemap;
- a tile failure does not clear spatial features or turn a valid result into an error.

### 10.3 End-to-end and security tests

- execute real compatible spatial SQL, select World outline, and assert a nonblank visual layer with no network requests;
- select a controlled configured XYZ fixture, assert host fetches only visible tile coordinates and the webview makes no remote request;
- inspect request payloads/logs/markers to prove WKB, labels, query text, endpoints, credentials, and raw coordinates are absent;
- test first-use consent, decline, workspace trust, source endpoint change, expired credential, 404, timeout, and corrupted image;
- verify no fetch occurs when Spatial is unopened, Layers remains `None`, world outline is selected, or data has an incompatible SRID;
- run light/dark/high-contrast, 200% zoom, narrow pane, split panels, rerun during tile load, hide/dispose during tile load, and reload restore;
- run package/bundle checks proving MapLibre or other unapproved heavy dependencies did not enter the Query Studio static closure.

### 10.4 Performance and telemetry

Registered production markers may include only provider kind enum, online/offline state, cache hit/miss bucket, tile count bucket, error category, and duration bucket. They MUST NOT include a source ID if it can identify an organization, URL/host, tile coordinate, map bounds, SRID paired with place information, query metadata, or credential state.

Suggested marker roles:

| Marker | Role | Safe attributes |
| --- | --- | --- |
| `mssql.queryResults.spatial.basemap.open` | Host session start | layer class, compatibility outcome |
| `mssql.queryResults.spatial.basemap.tile` | Host aggregate completion | provider-kind enum, cache bucket, outcome, duration bucket |
| `mssql.queryResults.spatial.basemap.close` | Host session terminal | reason enum, tile-count bucket |
| `mssql.queryResults.spatial.render.firstPaint` | Existing webview marker extension | `offline`, `worldOutline`, or `hostedRaster` renderer-layer enum |

Exact coordinates and request information may exist only in a test-only in-memory probe that is unavailable in production.

## 11. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| User accidentally leaks a sensitive area to an online provider | Default `None`, explicit per-source disclosure, visible online state, workspace-trust gate, and no automatic fallback. |
| Arbitrary URL becomes a general SSRF or exfiltration mechanism | User/application-only configuration, strict source grammar, source registry, host-only fetcher, no workspace input, private-network warning, redirect policy, and no webview network access. |
| Provider key leaks through browser tools, settings, cache, or telemetry | SecretStorage only, host-only auth injection, opaque local tile URIs, and privacy canaries. |
| Public tile service policy is violated | No default public endpoint, provider-specific adapter review, visible attribution, cache/no-prefetch policy, and support only for approved sources. |
| Basemap falsely implies an arbitrary geometry is geographic | Strict 4326/3857 eligibility gate and native-planar fallback. |
| Map layer obscures user features | Layer order, theme-aware opacity/styling, feature styles above tile layer, and accessibility/test review. |
| Tile traffic or cache grows without bound | Per-panel/global concurrency, visible-viewport-only requests, response caps, bounded cache, eviction, and clear controls. |
| Host cache root exposes unrelated extension data | Dedicated subdirectory only in `localResourceRoots`; never add all global storage. |
| Map library expansion harms Query Studio startup | Keep OpenLayers; lazy-load world outline and tile adapter; no MapLibre dependency in the first online slice; validate metafile/VSIX budget. |
| Provider adapter scope grows into routing/geocoding/search | Explicitly isolate raster render capability and deny non-render APIs. |

## 12. Definition of ready and done

### Ready for implementation

- [ ] Product/security/privacy/legal owners approve the disclosure, cache policy, provider policy, and world-outline license.
- [ ] The host-to-local-webview tile handoff spike proves that `connect-src 'none'` remains viable.
- [ ] Application-only settings behavior is confirmed for the target VS Code version.
- [ ] The baseline spatial fidelity matrix and EPSG:4326/3857 eligibility are accepted.
- [ ] The cache root and `localResourceRoots` narrowing design is reviewed.
- [ ] First source type/provider support and attribution/terms requirements are selected.
- [ ] Test fixture strategy can prove absence of remote webview requests and absence of sensitive payloads.

### Done for the first online release

- [ ] `None` remains the default and produces no map-layer requests.
- [ ] World outline provides an offline reference option for compatible data.
- [ ] A user can explicitly configure and select a supported HTTPS XYZ source.
- [ ] Every online selection is consented, workspace-trusted, attributed, and compatibility-gated.
- [ ] The webview has no remote `connect-src` and never receives an endpoint or credential.
- [ ] Host fetch/cache limits, cancellation, disposal, and error states are tested.
- [ ] Planar/unknown-SRID geometry cannot use a world or hosted basemap.
- [ ] Security, accessibility, visual, package, and performance tests pass.
- [ ] The online capability has its own default-off feature gate and documented rollback path.

## 13. References to retain in implementation review

- Existing `geospatial_pane.md` and `geospatial_pane_execution_addendum.md` for spatial fidelity, offline renderer, result ownership, and existing Phase 5 boundary.
- VS Code Webview security guidance: strict CSP, local-resource roots, and host/webview message boundaries.
- OpenLayers XYZ source and custom tile loader APIs.
- Azure Maps authentication guidance for Microsoft Entra, shared keys/SAS, least-privilege render access, and CORS implications.
- OpenStreetMap Foundation Tile Usage Policy for attribution, identification, caching, no prefetch/offline behavior, and public-service limitations.
- The selected world-outline data source’s license/attribution requirements.

## 14. Recommended immediate next step

Approve the architecture through a small Phase 0 spike, then land the offline `World outline` slice first. It delivers the simple world context users expect without adding network, provider, credential, or privacy risk. The host-proxied XYZ vertical slice should follow only after its controlled tile handoff, disclosure, and cache behavior are demonstrated.