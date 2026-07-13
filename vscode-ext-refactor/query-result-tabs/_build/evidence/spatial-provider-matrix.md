# Spatial provider/WKB behavior — evidence matrix (SPA-0)

## Environment

| Date | OS/RID | Engine | Driver/runtime | Spatial package | Result |
| --- | --- | --- | --- | --- | --- |
| 2026-07-12 | Windows x64 | Azure SQL Database | .NET 10, Microsoft.Data.SqlClient 6.1.5, SequentialAccess | Microsoft.SqlServer.Types 170.1000.7 | PASS for native-byte read, exact identity, SRID, OGC/ISO WKB conversion |
| pending | Windows x64 | local SQL Server 2025 | same | same | local connection env unavailable in this session |
| pending CI | Linux x64 | SQL Server/Azure SQL | same | same | required before release gate |
| pending CI | macOS arm64/x64 | Azure SQL | same | same | required before release gate |

Probe source: `../typeprobe/Program.cs`. The probe prints no connection string or credential.

## Exact provider identity

Azure SQL returned:

- `DataTypeName`: `<database>.sys.geometry` / `<database>.sys.geography`
- `DataType`: `Microsoft.SqlServer.Types.SqlGeometry` / `SqlGeography`
- `UdtAssemblyQualifiedName`: the exact corresponding `Microsoft.SqlServer.Types` CLR type, assembly version 11.0.0.0, public-key token `89845dcd8080cc91`

Typed spatial transport should require both the supported engine-type suffix and the exact supported assembly-qualified CLR type. Suffix-only recognition remains appropriate only for the existing safe binary fallback.

## Native serialization → WKB facts

| Case | Native bytes | `STAsBinary` | `AsBinaryZM` | SRID | Type | Finding |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| geometry Point XY | 22 | 21 | 21 | 0 | Point | standard WKB type 1 |
| geometry LineString | 38 | 41 | 41 | 4326 | LineString | standard WKB type 2 |
| geometry Polygon with hole | 197 | 177 | 177 | 0 | Polygon | standard WKB type 3, two rings |
| geometry GeometryCollection | 103 | 71 | 71 | 0 | GeometryCollection | standard WKB type 7 |
| geometry CircularString | 80 | 57 | 57 | 0 | CircularString | SQL/MM WKB type 8; renderer must classify unsupported unless explicitly implemented |
| geometry Point ZM | 38 | **21** | **37** | 0 | Point | `STAsBinary` drops Z/M; `AsBinaryZM` preserves ISO type 3001 |
| geography Point XY | 22 | 21 | 21 | 4326 | Point | coordinate order in WKB is X/Y = longitude/latitude |
| geography Point ZM | 38 | **21** | **37** | 4326 | Point | same Z/M loss/preservation behavior |
| geography antimeridian line | 38 | 41 | 41 | 4326 | LineString | transported; MVP renderer rejects geodesic edge semantics |
| geography Polygon | 96 | 77 | 77 | 4326 | Polygon | transported; MVP renderer rejects geodesic edge semantics |
| geography FullGlobe | 27 | 5 | 5 | 4326 | FullGlobe | SQL Server extended WKB type 126; inspectable/unsupported in MVP renderer |

## Locked consequence

The production driver must call `AsBinaryZM()`, not `STAsBinary()`, so Z/M values are not silently lost. The v1 `encoding: "wkb"` contract admits the ISO/SQL-MM dimensional type codes returned by `AsBinaryZM`; the decoder derives layout from WKB and renders XY while details disclose Z/M. Curves and FullGlobe remain transport-success values with semantic-support status determined in the decoder/renderer, not transport sentinels.

OpenLayers 10.9.0 browser-decoder probe on the exact Azure bytes:

- standard XY Point: PASS (`Point`, `XY`, coordinates `[1,2]`);
- ISO type 3001 ZM Point from `AsBinaryZM()`: PASS (`Point`, `XYZM`, coordinates `[1,2,3,4]`);
- SQL/MM CircularString type 8: typed parser rejection (`Unsupported WKB geometry type 8`);
- SQL Server FullGlobe type 126: typed parser rejection (`Unsupported WKB geometry type 126`).

This is the desired boundary: the transport preserves curves/FullGlobe as complete WKB, the decoder catches a specific unsupported-type condition per cell, and the feature list/details remain available without treating the value as transport failure or invalid topology.

## Conversion timing observation

The first conversion for each CLR type paid a cold-start/JIT cost (approximately 13 ms for geometry and geography in the second probe run; an earlier geometry cold run observed 31.8 ms). Warm small conversions were generally below 3 ms and mostly below 1 ms. SPA-3 must add a one-time warm-up or account honestly for cold conversion in STS diagnostics, and the large-cell corpus must bound worst-case synchronous `Deserialize` + `AsBinaryZM()` time before capability advertisement is enabled by default.

## Still required

- near/over-1 MiB native and WKB cells;
- cancellation while draining many native chunks;
- invalid stored instances;
- CompoundCurve/CurvePolygon and nested curve collections;
- little/big-endian decoder corpus (SQL Server emitted little-endian in these probes);
- Windows local SQL Server plus Linux/macOS package/RID evidence.

## SpatialLab fixture evidence

`spatiallab_setup.sql` provisioned the Azure-safe schema on 2026-07-12. All ground-truth checks passed: 100,000 points, 100 NULL, 100 empty, 99,800 non-empty, 14 geometry shapes, two geometry SRIDs, one invalid geometry, 11 geography shapes, one FullGlobe, and Z/M-preserving WKB larger than OGC XY WKB.
