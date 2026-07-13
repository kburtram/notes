-- SpatialLab ground-truth checks. Every row returned must say PASS.
SET NOCOUNT ON;

SELECT TestName = N'Points row count', Expected = CONVERT(BIGINT, 100000), Actual = COUNT_BIG(*),
       Result = IIF(COUNT_BIG(*) = 100000, N'PASS', N'FAIL')
FROM spatiallab.Points100k;

SELECT TestName = N'Points NULL count', Expected = CONVERT(BIGINT, 100),
       Actual = SUM(CONVERT(BIGINT, IIF(Location IS NULL, 1, 0))),
       Result = IIF(SUM(CONVERT(BIGINT, IIF(Location IS NULL, 1, 0))) = 100, N'PASS', N'FAIL')
FROM spatiallab.Points100k;

SELECT TestName = N'Points empty count', Expected = CONVERT(BIGINT, 100),
       Actual = SUM(CONVERT(BIGINT, IIF(Location IS NOT NULL AND Location.STIsEmpty() = 1, 1, 0))),
       Result = IIF(SUM(CONVERT(BIGINT, IIF(Location IS NOT NULL AND Location.STIsEmpty() = 1, 1, 0))) = 100, N'PASS', N'FAIL')
FROM spatiallab.Points100k;

SELECT TestName = N'Geometry shape rows', Expected = CONVERT(BIGINT, 14), Actual = COUNT_BIG(*),
       Result = IIF(COUNT_BIG(*) = 14, N'PASS', N'FAIL')
FROM spatiallab.GeometryShapes;

SELECT TestName = N'Geometry mixed SRIDs', Expected = CONVERT(BIGINT, 2), Actual = COUNT_BIG(DISTINCT Shape.STSrid),
       Result = IIF(COUNT_BIG(DISTINCT Shape.STSrid) = 2, N'PASS', N'FAIL')
FROM spatiallab.GeometryShapes
WHERE Shape IS NOT NULL;

SELECT TestName = N'Geometry invalid rows', Expected = CONVERT(BIGINT, 1),
       Actual = SUM(CONVERT(BIGINT, IIF(Shape IS NOT NULL AND Shape.STIsValid() = 0, 1, 0))),
       Result = IIF(SUM(CONVERT(BIGINT, IIF(Shape IS NOT NULL AND Shape.STIsValid() = 0, 1, 0))) = 1, N'PASS', N'FAIL')
FROM spatiallab.GeometryShapes;

SELECT TestName = N'Geography shape rows', Expected = CONVERT(BIGINT, 11), Actual = COUNT_BIG(*),
       Result = IIF(COUNT_BIG(*) = 11, N'PASS', N'FAIL')
FROM spatiallab.GeographyShapes;

SELECT TestName = N'Geography FullGlobe rows', Expected = CONVERT(BIGINT, 1),
       Actual = SUM(CONVERT(BIGINT, IIF(Shape IS NOT NULL AND Shape.InstanceOf('FullGlobe') = 1, 1, 0))),
       Result = IIF(SUM(CONVERT(BIGINT, IIF(Shape IS NOT NULL AND Shape.InstanceOf('FullGlobe') = 1, 1, 0))) = 1, N'PASS', N'FAIL')
FROM spatiallab.GeographyShapes;

SELECT TestName = N'ZM differs from OGC XY WKB', Expected = CONVERT(BIGINT, 1),
       Actual = SUM(CONVERT(BIGINT, IIF(DATALENGTH(Shape.AsBinaryZM()) > DATALENGTH(Shape.STAsBinary()), 1, 0))),
       Result = IIF(SUM(CONVERT(BIGINT, IIF(DATALENGTH(Shape.AsBinaryZM()) > DATALENGTH(Shape.STAsBinary()), 1, 0))) = 1, N'PASS', N'FAIL')
FROM spatiallab.GeometryShapes
WHERE Id = 11;
