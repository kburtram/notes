-- SpatialLab deterministic Query Studio Spatial corpus.
-- Azure-safe: creates only a schema and tables in the connected database.
-- Idempotent and synthetic; no user data or external calls.

SET NOCOUNT ON;
SET XACT_ABORT ON;
GO

IF SCHEMA_ID(N'spatiallab') IS NULL
    EXEC(N'CREATE SCHEMA spatiallab AUTHORIZATION dbo');
GO

DROP TABLE IF EXISTS spatiallab.GeographyShapes;
DROP TABLE IF EXISTS spatiallab.GeometryShapes;
DROP TABLE IF EXISTS spatiallab.Points100k;
GO

CREATE TABLE spatiallab.Points100k
(
    Id INT NOT NULL CONSTRAINT PK_SpatialLab_Points100k PRIMARY KEY,
    Label NVARCHAR(64) NOT NULL,
    Category NVARCHAR(16) NOT NULL,
    Reading FLOAT NOT NULL,
    Location GEOGRAPHY NULL
);
GO

;WITH N AS
(
    SELECT TOP (100000)
        ROW_NUMBER() OVER (ORDER BY a.object_id, b.object_id) AS n
    FROM sys.all_objects AS a
    CROSS JOIN sys.all_objects AS b
)
INSERT spatiallab.Points100k (Id, Label, Category, Reading, Location)
SELECT
    n,
    N'sensor-' + RIGHT(REPLICATE(N'0', 6) + CONVERT(NVARCHAR(12), n), 6),
    N'category-' + CONVERT(NVARCHAR(2), n % 8),
    CONVERT(FLOAT, (n * 7919) % 100000) / 100.0,
    CASE
        WHEN n % 1000 = 0 THEN NULL
        WHEN n % 1000 = 1 THEN geography::STGeomFromText('POINT EMPTY', 4326)
        WHEN n BETWEEN 99902 AND 100000 AND n % 2 = 0
            THEN geography::Point(10.0 + (n % 17) / 100.0, 179.0 + (n % 83) / 100.0, 4326)
        WHEN n BETWEEN 99902 AND 100000
            THEN geography::Point(10.0 + (n % 17) / 100.0, -179.0 - (n % 83) / 100.0, 4326)
        ELSE geography::Point(
            -80.0 + CONVERT(FLOAT, (n * 37) % 16000) / 100.0,
            -179.0 + CONVERT(FLOAT, (n * 53) % 35800) / 100.0,
            4326)
    END
FROM N;
GO

CREATE TABLE spatiallab.GeometryShapes
(
    Id INT NOT NULL CONSTRAINT PK_SpatialLab_GeometryShapes PRIMARY KEY,
    Label NVARCHAR(64) NOT NULL,
    Category NVARCHAR(16) NOT NULL,
    Shape GEOMETRY NULL
);
GO

INSERT spatiallab.GeometryShapes (Id, Label, Category, Shape)
VALUES
    (1, N'Point SRID 0', N'point', geometry::STGeomFromText('POINT (1 2)', 0)),
    (2, N'Point SRID 3857', N'point', geometry::STGeomFromText('POINT (-13621000 6024000)', 3857)),
    (3, N'LineString', N'line', geometry::STGeomFromText('LINESTRING (0 0, 10 5, 20 0)', 0)),
    (4, N'Polygon', N'polygon', geometry::STGeomFromText('POLYGON ((0 0, 12 0, 12 8, 0 8, 0 0))', 0)),
    (5, N'Polygon with hole', N'polygon', geometry::STGeomFromText('POLYGON ((0 0, 20 0, 20 20, 0 20, 0 0),(5 5,5 10,10 10,10 5,5 5))', 0)),
    (6, N'MultiPoint', N'multi', geometry::STGeomFromText('MULTIPOINT ((1 1), (2 3), (5 8))', 0)),
    (7, N'MultiLineString', N'multi', geometry::STGeomFromText('MULTILINESTRING ((0 0,3 3),(1 5,8 5))', 0)),
    (8, N'MultiPolygon', N'multi', geometry::STGeomFromText('MULTIPOLYGON (((0 0,2 0,2 2,0 2,0 0)),((4 4,7 4,7 7,4 7,4 4)))', 0)),
    (9, N'GeometryCollection', N'collection', geometry::STGeomFromText('GEOMETRYCOLLECTION (POINT (1 2), LINESTRING (0 0,2 2))', 0)),
    (10, N'CircularString unsupported', N'curve', geometry::STGeomFromText('CIRCULARSTRING (0 0,1 1,2 0)', 0)),
    (11, N'Point ZM', N'zm', geometry::STGeomFromText('POINT (1 2 3 4)', 0)),
    (12, N'Empty point', N'empty', geometry::STGeomFromText('POINT EMPTY', 0)),
    (13, N'Invalid bow-tie polygon', N'invalid', geometry::STGeomFromText('POLYGON ((0 0,4 4,0 4,4 0,0 0))', 0)),
    (14, N'Null shape', N'null', NULL);
GO

CREATE TABLE spatiallab.GeographyShapes
(
    Id INT NOT NULL CONSTRAINT PK_SpatialLab_GeographyShapes PRIMARY KEY,
    Label NVARCHAR(64) NOT NULL,
    Category NVARCHAR(16) NOT NULL,
    Shape GEOGRAPHY NULL
);
GO

INSERT spatiallab.GeographyShapes (Id, Label, Category, Shape)
VALUES
    (1, N'Seattle', N'point', geography::Point(47.6062, -122.3321, 4326)),
    (2, N'London', N'point', geography::Point(51.5074, -0.1278, 4326)),
    (3, N'Tokyo', N'point', geography::Point(35.6762, 139.6503, 4326)),
    (4, N'Antimeridian east', N'point', geography::Point(10, 179.8, 4326)),
    (5, N'Antimeridian west', N'point', geography::Point(10, -179.8, 4326)),
    (6, N'Geodesic line unsupported', N'line', geography::STGeomFromText('LINESTRING (179 10,-179 10)', 4326)),
    (7, N'Geodesic polygon unsupported', N'polygon', geography::STGeomFromText('POLYGON ((-1 0,0 1,1 0,-1 0))', 4326)),
    (8, N'FullGlobe unsupported', N'fullglobe', geography::STGeomFromText('FULLGLOBE', 4326)),
    (9, N'Point ZM', N'zm', geography::STGeomFromText('POINT (1 2 3 4)', 4326)),
    (10, N'Empty point', N'empty', geography::STGeomFromText('POINT EMPTY', 4326)),
    (11, N'Null shape', N'null', NULL);
GO

SELECT
    PointsRows = COUNT_BIG(*),
    NullPoints = SUM(CASE WHEN Location IS NULL THEN 1 ELSE 0 END),
    EmptyPoints = SUM(CASE WHEN Location IS NOT NULL AND Location.STIsEmpty() = 1 THEN 1 ELSE 0 END),
    NonEmptyPoints = SUM(CASE WHEN Location IS NOT NULL AND Location.STIsEmpty() = 0 THEN 1 ELSE 0 END)
FROM spatiallab.Points100k;
GO

