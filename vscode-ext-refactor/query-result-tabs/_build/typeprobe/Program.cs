using System.Data;
using System.Data.Common;
using System.Data.SqlTypes;
using Microsoft.Data.SqlClient;
using Microsoft.SqlServer.Types;

string connStr = Environment.GetEnvironmentVariable("STS2_SQLSERVER_CONNSTRING")
    ?? Environment.GetEnvironmentVariable("STS2_AZURESQLSERVER_CONNSTRING");
if (string.IsNullOrWhiteSpace(connStr))
{
    Console.Error.WriteLine("Set STS2_SQLSERVER_CONNSTRING or STS2_AZURESQLSERVER_CONNSTRING.");
    return 2;
}

await using var conn = new SqlConnection(connStr);
await conn.OpenAsync();
Console.WriteLine($"Server={conn.DataSource}; Database={conn.Database}; SqlClient=6.1.5; SqlServer.Types=170.1000.7");

if (args.Length == 2 && args[0] == "--script")
{
    await RunScriptAsync(conn, args[1]);
    return 0;
}

var cases = new (string Name, string Kind, string Expression)[]
{
    ("geometry-point", "geometry", "geometry::STGeomFromText('POINT (1 2)', 0)"),
    ("geometry-line-4326", "geometry", "geometry::STGeomFromText('LINESTRING (-122.36 47.656, -122.343 47.656)', 4326)"),
    ("geometry-polygon-hole", "geometry", "geometry::STGeomFromText('POLYGON ((0 0,10 0,10 10,0 10,0 0),(2 2,2 4,4 4,4 2,2 2))', 0)"),
    ("geometry-collection", "geometry", "geometry::STGeomFromText('GEOMETRYCOLLECTION (POINT (1 2), LINESTRING (0 0, 2 2))', 0)"),
    ("geometry-circularstring", "geometry", "geometry::STGeomFromText('CIRCULARSTRING (0 0, 1 1, 2 0)', 0)"),
    ("geometry-point-zm", "geometry", "geometry::STGeomFromText('POINT (1 2 3 4)', 0)"),
    ("geography-point", "geography", "geography::Point(47.656, -122.36, 4326)"),
    ("geography-point-zm", "geography", "geography::STGeomFromText('POINT (1 2 3 4)', 4326)"),
    ("geography-antimeridian-line", "geography", "geography::STGeomFromText('LINESTRING (179 10, -179 10)', 4326)"),
    ("geography-polygon", "geography", "geography::STGeomFromText('POLYGON ((-1 0, 0 1, 1 0, -1 0))', 4326)"),
    ("geography-fullglobe", "geography", "geography::STGeomFromText('FULLGLOBE', 4326)"),
};

foreach ((string name, string kind, string expression) in cases)
{
    try
    {
        await ProbeAsync(conn, name, kind, expression);
    }
    catch (Exception ex)
    {
        Console.WriteLine($"{name}: ERROR {ex.GetType().Name} {SingleLine(ex.Message)}");
    }
}

return 0;

static async Task ProbeAsync(SqlConnection conn, string name, string kind, string expression)
{
    await using var cmd = new SqlCommand($"SELECT {expression} AS spatial_value", conn);
    await using SqlDataReader reader = await cmd.ExecuteReaderAsync(CommandBehavior.SequentialAccess);
    DbColumn schema = (await reader.GetColumnSchemaAsync())[0];
    await reader.ReadAsync();
    byte[] native = ReadAllBytes(reader, 0);
    var started = System.Diagnostics.Stopwatch.StartNew();
    byte[] wkb;
    byte[] wkbZm;
    int srid;
    string geometryType;
    if (kind == "geometry")
    {
        SqlGeometry value = SqlGeometry.Deserialize(new SqlBytes(native));
        srid = value.STSrid.Value;
        geometryType = value.STGeometryType().Value;
        wkb = value.STAsBinary().Value;
        wkbZm = value.AsBinaryZM().Value;
    }
    else
    {
        SqlGeography value = SqlGeography.Deserialize(new SqlBytes(native));
        srid = value.STSrid.Value;
        geometryType = value.STGeometryType().Value;
        wkb = value.STAsBinary().Value;
        wkbZm = value.AsBinaryZM().Value;
    }
    started.Stop();
    Console.WriteLine(
        $"{name}: type={schema.DataTypeName}; clr={schema.DataType?.FullName ?? "(null)"}; " +
        $"udt={schema.UdtAssemblyQualifiedName ?? "(null)"}; native={native.Length}; wkb={wkb.Length}; wkbZm={wkbZm.Length}; " +
        $"srid={srid}; geometryType={geometryType}; convertMs={started.Elapsed.TotalMilliseconds:F3}; " +
        $"wkbPrefix={Convert.ToHexString(wkb.AsSpan(0, Math.Min(wkb.Length, 16)))}; " +
        $"wkbZmPrefix={Convert.ToHexString(wkbZm.AsSpan(0, Math.Min(wkbZm.Length, 16)))}");
}

static byte[] ReadAllBytes(SqlDataReader reader, int ordinal)
{
    byte[] chunk = new byte[32 * 1024];
    using var output = new MemoryStream();
    long offset = 0;
    while (true)
    {
        long read = reader.GetBytes(ordinal, offset, chunk, 0, chunk.Length);
        if (read <= 0)
        {
            break;
        }
        output.Write(chunk, 0, checked((int)read));
        offset += read;
        if (read < chunk.Length)
        {
            break;
        }
    }
    return output.ToArray();
}

static string SingleLine(string value) => value.Replace('\r', ' ').Replace('\n', ' ');

static async Task RunScriptAsync(SqlConnection conn, string path)
{
    string sql = await File.ReadAllTextAsync(path);
    string[] batches = System.Text.RegularExpressions.Regex.Split(
        sql,
        @"^\s*GO\s*(?:--.*)?$",
        System.Text.RegularExpressions.RegexOptions.Multiline | System.Text.RegularExpressions.RegexOptions.IgnoreCase);
    int batchOrdinal = 0;
    foreach (string batch in batches)
    {
        if (string.IsNullOrWhiteSpace(batch))
        {
            continue;
        }
        batchOrdinal++;
        await using var command = new SqlCommand(batch, conn) { CommandTimeout = 180 };
        await using SqlDataReader reader = await command.ExecuteReaderAsync();
        do
        {
            while (await reader.ReadAsync())
            {
                var cells = new string[reader.FieldCount];
                for (int i = 0; i < reader.FieldCount; i++)
                {
                    cells[i] = $"{reader.GetName(i)}={SingleLine(Convert.ToString(reader.GetValue(i), System.Globalization.CultureInfo.InvariantCulture) ?? "NULL")}";
                }
                Console.WriteLine(string.Join("; ", cells));
            }
        }
        while (await reader.NextResultAsync());
        Console.WriteLine($"batch={batchOrdinal}; status=ok");
    }
}
