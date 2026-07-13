-- Query Studio manual/automation probes over SpatialLab.

-- 10k progressive geography point target.
SELECT TOP (10000) Id, Label, Category, Reading, Location
FROM spatiallab.Points100k
ORDER BY Id;

-- 100k GPU-point qualification target.
SELECT Id, Label, Category, Reading, Location
FROM spatiallab.Points100k
ORDER BY Id;

-- Linear geometry fidelity + mixed SRID + curve/ZM/null/empty/invalid states.
SELECT Id, Label, Category, Shape
FROM spatiallab.GeometryShapes
ORDER BY Id;

-- Geography semantic-support states including antimeridian, geodesic edges and FullGlobe.
SELECT Id, Label, Category, Shape
FROM spatiallab.GeographyShapes
ORDER BY Id;
