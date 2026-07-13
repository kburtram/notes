-- Small deterministic WKB/SQL-MM fixtures for browser decoder tests.
SELECT Fixture = N'geometry-point', WkbHex = CONVERT(VARCHAR(MAX), geometry::STGeomFromText('POINT (1 2)', 0).AsBinaryZM(), 2)
UNION ALL
SELECT N'geometry-point-zm', CONVERT(VARCHAR(MAX), geometry::STGeomFromText('POINT (1 2 3 4)', 0).AsBinaryZM(), 2)
UNION ALL
SELECT N'geometry-circularstring', CONVERT(VARCHAR(MAX), geometry::STGeomFromText('CIRCULARSTRING (0 0,1 1,2 0)', 0).AsBinaryZM(), 2)
UNION ALL
SELECT N'geography-fullglobe', CONVERT(VARCHAR(MAX), geography::STGeomFromText('FULLGLOBE', 4326).AsBinaryZM(), 2);
