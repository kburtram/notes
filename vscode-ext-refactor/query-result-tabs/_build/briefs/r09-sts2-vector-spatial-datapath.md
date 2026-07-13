# R09 — STS2 data path for VECTOR and geometry/geography (sqltoolsservice, branch `dev/query`)

Reader brief for the vector-debugger / spatial-visualizer result tabs. Repo: `C:/repos/test/sqltoolsservice`,
branch `dev/query` (HEAD `559d2596` "STS2: serverInfo.engineEditionId ... (D-0017)"). All paths below are
relative to the repo root unless absolute. **Facts marked [VERIFIED-LIVE] were empirically confirmed on
2026-07-11 against host SQL Server 2025 (17.0.1000.7, Enterprise Developer) using Microsoft.Data.SqlClient
6.1.5 — the exact package version the STS2 driver builds against (`Packages.props:86`) — with the exact STS2
read pattern (`CommandBehavior.SequentialAccess` + `GetValue`).**

---

## 1. Headline findings (read this first)

1. **VECTOR columns are BROKEN on STS2 today.** The driver's `reader.GetValue(i)` returns a boxed
   `Microsoft.Data.SqlTypes.SqlVector<float>` [VERIFIED-LIVE]; `WireValueEncoder.Encode` has no case for it,
   so it falls into the provider fallback (`src/sts2/Microsoft.SqlTools.Sts2.Runtime/Effects/WireValueEncoder.cs:116`)
   which emits `Convert.ToString(cell)` — and `SqlVector<float>.ToString()` is NOT overridden, so every vector
   cell arrives on the wire as ``{"$t":"provider","v":"Microsoft.Data.SqlTypes.SqlVector`1[System.Single]"}``
   — **the data is lost** [VERIFIED-LIVE for the ToString behavior]. Any vector tab needs a service-side fix first.
2. **geometry/geography/hierarchyid columns FAIL the whole query on STS2 today.** `GetValue` on a UDT column
   throws `System.IO.FileNotFoundException: Could not load ... 'Microsoft.SqlServer.Types'` on .NET
   [VERIFIED-LIVE]. The pump's catch-all (`DriverEffectRunner.cs:530-537`) turns that into
   `v2/query.complete` `status:"error"` with `code:"Sts2.Internal"`, message
   `"Driver threw an unclassified exception: FileNotFoundException"`. The legacy ServiceLayer avoids this by
   treating UDTs as bytes (`DbColumnWrapper.cs:330-340`); STS2's `SqlLargeValueReader.ClassifyColumns` has no
   UDT case yet.
3. **Both fixes are small and localized** in `SqlLargeValueReader.ClassifyColumns`
   (`src/sts2/Microsoft.SqlTools.Sts2.Drivers.SqlClient/SqlLargeValueReader.cs:36-54`):
   - `vector` → `CellRead.Text`: `reader.GetChars` on a vector column works under SequentialAccess and yields
     the JSON array string with full float32 shortest-round-trip precision, e.g.
     `[0.1,0.3,1.1754944E-38,3.4028235E+38,-0.00012345679]` [VERIFIED-LIVE].
   - UDTs (`EngineType` ends with `.sys.geometry` / `.sys.geography` / `.sys.hierarchyid`) → `CellRead.Binary`:
     chunked `reader.GetBytes` streaming works on UDT columns under SequentialAccess [VERIFIED-LIVE] and the
     existing binary path then emits a standard `{"$t":"binary","v":"<base64>"}` cell containing SQL Server's
     CLR serialization bytes (SRID-bearing; same bytes the legacy grid shows as `0xE610...`).
4. **Column metadata on the STS2 wire is minimal**: `v2/query.resultSet` sends only
   `{"name","type","nullable"}` per column (`DriverEffectRunner.SerializeColumns`, lines 596-609). The driver
   *captures* `Precision/Scale/Length/Collation` in `ColumnInfo` (`SqlClientSession.ReadColumnsAsync`,
   lines 198-218) but they are **not serialized**. SPEC §7.7 already promises "precision, scale, nullable,
   length, collation" — adding them to `SerializeColumns` is spec-aligned and additive (precedent: `database`
   on `v2/query.complete`, `engineEditionId` D-0017). For vector, `ColumnSize` = wire bytes = `8 + 4*dims`
   (vector(3) → 20, vector(4) → 24 [VERIFIED-LIVE]) — so shipping `length` lets the client know the dimension
   count from metadata alone.
5. **No new endpoint is needed for whole-column full-precision fetch** in the common case, but two real
   constraints exist: one-active-query-per-connection (`Sts2.Busy`) and the lower-only `maxCellBytes` ceiling
   of 1 MiB (cells above it always arrive as `truncated` wrappers). See §8.

---

## 2. STS2 endpoint surface (the wire contract)

Method registry: `src/sts2/Microsoft.SqlTools.Sts2.Contracts/Sts2Methods.cs:33-53`. Spec:
`docs/sts2/SPEC.md` §7 (wire contract at lines 303-592). Transport = JSON-RPC 2.0, Content-Length framing,
same stdio pair as legacy; methods prefixed `v2/` route to STS2 (enable with `--enable-sts2` or
`STS_ENABLE_STS2=1`; `docs/sts2/CLIENT.md:1-7`). `specVersion` = `2.0.0-preview.1`
(`Sts2WireConstants.cs:12`).

Query-relevant methods:

| Method | Kind |
|---|---|
| `v2/query.execute` | request → `{ "queryId": "q-<seq>" }` |
| `v2/query.resultSet` | server notification (result-set metadata) |
| `v2/query.rows` | server notification (forward-only row page) |
| `v2/query.message` | server notification |
| `v2/query.complete` | server notification (exactly one terminal) |
| `v2/query.ack` | client notification (backpressure credit) |
| `v2/query.cancel`, `v2/query.dispose` | requests, idempotent |

`v2/query.execute` params (SPEC §7.5, lines 453-481; normalization in
`src/sts2/Microsoft.SqlTools.Sts2.Core/Sts2CoreReducer.cs:428-489`):

```json
{ "connectionId": "c-1", "sql": "...",
  "options": { "queryTimeoutMs": 0, "pageRows": 1000, "pageBytes": 262144,
               "maxCellBytes": 65536, "compactRows": true } }
```

- `pageRows`/`pageBytes`/`maxCellBytes` are **lower-only**: positive lowers the pinned default, larger clamps
  to it, absent/0/negative/non-integer = default (`EffectiveLoweredOption`, `Sts2CoreReducer.cs:508+`).
- `compactRows` must be literal `true` (`OptionIsTrue`, read at `Sts2CoreReducer.cs:464`).
- Core journals all normalized options into the `driver.queryStart` effect args
  (`Sts2CoreReducer.cs:465-467`): `{queryId, connectionId, handleId, sql, credit, maxCellBytes, pageRows,
  pageBytes, queryTimeoutMs, compactRows}`.

Pinned defaults (`src/sts2/Microsoft.SqlTools.Sts2.Contracts/Sts2Defaults.cs`): `PageRows=1000` (:12),
`PageBytes=262144` (:15), `WindowPages=4` (:18), `MaxCellBytes=1048576` (:21), `TruncatedPrefixBytes=65536`
(:24), `MaxFrameBytes=67108864` (:27). Config-key names in the doc comments: `sts2.results.pageRows`,
`sts2.results.pageBytes`, `sts2.results.windowPages`, `sts2.results.maxCellBytes`,
`sts2.results.truncatedPrefixBytes`, `sts2.transport.maxFrameBytes`.

Capabilities advertised by `v2/initialize` (`Sts2CoreReducer.cs:104-123`): `forwardOnlyStreaming`,
`oneActiveQueryPerConnection`, `redactedReplay`, `exportLog`, `setCapture`, `maxCellBytesHonored`,
`pageRowsHonored`, `pageBytesHonored`, `queryTimeoutHonored`, `compactRows` — all `true`. `limits` mirror the
pinned defaults plus `maxConnections`.

Ordering guarantees (SPEC lines 483-489): `query.resultSet` precedes its rows; `pageSeq` gapless per result
set; `rowOffset` monotonic per result set; exactly one `query.complete`; nothing after complete.

Backpressure (SPEC §7.8, lines 561-582; D-0015 in `docs/sts2/DECISIONS.md`): window = 4 unacked pages **per
query**. Ack forms: `{queryId, resultSetId, pageSeq}` (per page) or `{queryId, throughPageSeq}` (high-water).
**`throughPageSeq` is the per-QUERY cumulative page ordinal, NOT the per-result-set `pageSeq`** (which
restarts at 0 each result set) — acking per-set seq deadlocks multi-result-set queries after 4 pages
(found live in vscode-mssql, fixed there; pinned by `QueryFlowTests.MultiResultSetStreamCompletesWithPerQueryOrdinalAcks`).
`resultSetId` in the ack is diagnostic only. Busy rule: second active query on a connection →
`Sts2.Busy` (`Sts2CoreReducer.cs:448-451`).

Error identity: numeric JSON-RPC `error.code` + stable string in `error.data.code` (`Sts2.QueryFailed.Server`
= -32050, `Sts2.Busy` = -32061, `Sts2.Internal` = -32603, etc. — `Sts2Defaults.cs:55-72`).

---

## 3. `v2/query.rows` wire shapes (legacy and QO-5 compact)

Reducer assembles the notification (`Sts2CoreReducer.cs:751-771`); it routes **by payload shape** — a
`compact` property on the journaled driver event forwards compact, else legacy, byte-for-byte:

Legacy (default) shape:
```json
{ "queryId":"q-3", "resultSetId":0, "pageSeq":12, "rowOffset":12000,
  "rows":[[1,"abc",null,{"$t":"decimal","v":"12.50"}]], "last":false }
```

Compact shape (only when `options.compactRows === true`; D-0016, SPEC §7.5 line 481):
```json
{ "queryId":"q-3", "resultSetId":0, "pageSeq":12, "rowOffset":12000,
  "compact": { "values":[[...cells...]], "nullBitmap":"<base64>", "typeHints":["number","string",...] },
  "approxBytes":12345, "encodedBytes":12345, "last":false }
```

- `compact.values` carries **the same wire-encoded cells** as the legacy `rows` (built by
  `DriverEffectRunner.SerializeRows`, lines 611-627 — one `WireValueEncoder.Encode(cell, maxCellBytes)` per cell).
- `nullBitmap`: base64, **row-major LSB-first** over the page's cells — `byte[i>>3] |= 1 << (i&7)` for
  null/DBNull cells; byte-identical to the client's `packBitmap` layout in `sts2Backend.ts`
  (`DriverEffectRunner.PackNullBitmap`, lines 549-566).
- `typeHints`: computed **once per result set** from driver column metadata
  (`DriverEffectRunner.SerializeTypeHints`, lines 573-594) — same taxonomy as the client's `typeHintFor` in
  `sts2Backend.ts`; the comment demands the two mappings stay identical. Taxonomy (engineType lowercased):
  `bit`→`boolean`; `int|smallint|tinyint|float|real`→`number`;
  `bigint|decimal|numeric|money|smallmoney`→`number:approx`;
  `varbinary|binary|image|timestamp|rowversion`→`binary`; `xml`→`xml`;
  `date*|time*|smalldatetime`→`datetime`; everything else→`string`. **`vector` and
  `master.sys.geometry` therefore hint as `string` today** — if the panes want a dedicated hint (`vector`,
  `spatial`), both the runner switch AND the client `typeHintFor` must change in lockstep.
- `approxBytes`/`encodedBytes` are currently both `rowsJson.Length` (service-measured at encode,
  `DriverEffectRunner.cs:471-473`).
- `last` is **hardcoded `false`** in both shapes (`Sts2CoreReducer.cs:765,768`) — clients learn completion
  from `v2/query.complete` (`{queryId, status:"succeeded"|"canceled"|"error"|"disposed", rowsAffected,
  database, error?}`, reducer lines 784-808). `resultSetDone` driver events are swallowed
  (`Sts2CoreReducer.cs:781-782`).

### Cell encoding rules (`WireValueEncoder`, `src/sts2/Microsoft.SqlTools.Sts2.Runtime/Effects/WireValueEncoder.cs`)

`Encode(object? cell)` switch (lines 88-117):
- `null`/`DBNull` → JSON `null`.
- JSON natives: `bool`, `long`, `int`, `short`, `byte`, `string`; finite `double`/`float` as JSON numbers.
- Typed wrappers `{"$t":"<t>","v":"<invariant string>"}`: `decimal`; `DateTime`→`datetime2` ("O" format);
  `DateTimeOffset`→`datetimeoffset`; `TimeSpan`→`time` ("c"); `Guid`→`guid`; `byte[]`→`binary` (base64);
  non-finite floats→`double` with `"NaN"|"Infinity"|"-Infinity"`.
- Pre-built `JsonNode` passes through (FakeDriver edge values).
- **Fallback** (line 116): `_ => Wrapper("provider", Convert.ToString(cell, CultureInfo.InvariantCulture))` —
  this is where `SqlVector<float>` lands today (see §5).
- Oversized cells (`Encode(cell, maxCellBytes)`, lines 34-55): string/binary above the bound become
  `{"$t":"truncated","of":"string"|"binary","bytes":<fullByteCount>,"digest":"sha256:<hex>","v":"<prefix>"}`;
  prefix capped by `min(maxCellBytes, 65536)`, UTF-8 code-point safe; base64 for binary prefixes. Driver-side
  streamed truncations (`DriverTruncatedValue`, QO-4) emit the same wrapper verbatim (lines 40-43, 57-85).
- SPEC statement of these rules: `docs/sts2/SPEC.md:536-559`.

---

## 4. `v2/query.resultSet` and column metadata

Wire shape (reducer `Sts2CoreReducer.cs:743-749`, runner `SerializeColumns` lines 596-609):

```json
{ "queryId":"q-3", "resultSetId":0,
  "columns":[ { "name":"vec", "type":"vector", "nullable":true }, ... ] }
```

- `type` = `ColumnInfo.EngineType` **verbatim** = `DbColumn.DataTypeName ?? reader.GetDataTypeName(i)`
  (`SqlClientSession.ReadColumnsAsync`, `src/sts2/Microsoft.SqlTools.Sts2.Drivers.SqlClient/SqlClientSession.cs:198-218`).
- `ColumnInfo` (`src/sts2/Microsoft.SqlTools.Sts2.Abstractions/ExecEvents.cs:63-85`) also captures
  `Nullable`, `Precision` (`NumericPrecision`), `Scale`, `Length` (`ColumnSize`), `Collation` (always null
  today) — **only `name`/`type`/`nullable` reach the wire.** `UdtAssemblyQualifiedName` is not captured at all.

[VERIFIED-LIVE] metadata for the interesting types (via `GetColumnSchema()` on SqlClient 6.1.5):

| column | `DataTypeName` | `ColumnSize` | `NumericPrecision/Scale` | `IsLong` | `DataType` (CLR) | `UdtAssemblyQualifiedName` |
|---|---|---|---|---|---|---|
| `vector(3)` | `vector` | **20** (= 8 + 4×3) | 255 / 0 | false | `Microsoft.Data.SqlTypes.SqlVector'1[System.Single]` | (empty) |
| `vector(4)` | `vector` | **24** | 255 / 0 | false | same | (empty) |
| geometry | **`master.sys.geometry`** (3-part, db-qualified!) | 2147483647 | 255 / 255 | true | null | `Microsoft.SqlServer.Types.SqlGeometry, Microsoft.SqlServer.Types, Version=11.0.0.0, ...` |
| geography | **`master.sys.geography`** | 2147483647 | 255 / 255 | true | null | `...SqlGeography...` |
| hierarchyid | **`master.sys.hierarchyid`** | 892 | 255 / 255 | false | null | `...SqlHierarchyId...` |

Consequences:
- The client detects vector columns by `columns[i].type === "vector"` (exact). Spatial columns must be
  detected by **suffix** (`.endsWith(".sys.geometry")` / `".sys.geography"`) because the db-name prefix varies
  — the legacy code uses exactly this trick (`DbColumnWrapper.cs:257` — `DataTypeName.EndsWith(".sys.hierarchyid")`).
- Vector dimension count is NOT on the STS2 wire today (no `length`). Options: derive from the first non-null
  cell, or (better) extend `SerializeColumns` with `length`/`precision`/`scale` — additive per SPEC §7.7
  sentence "Column metadata carries engine type names verbatim plus normalized fields where known: precision,
  scale, nullable, length, collation" (`docs/sts2/SPEC.md:556`).

---

## 5. VECTOR: exact behavior, wire options, fix points

### Server/driver facts [VERIFIED-LIVE, SQL 2025 + M.D.S 6.1.5]

- `GetValue(i)` (SequentialAccess or not) → boxed `Microsoft.Data.SqlTypes.SqlVector<float>`.
  `GetSqlValue(i)` → same. `GetFieldType(i)`/`GetProviderSpecificFieldType(i)` → `SqlVector<float>`.
- `SqlVector<float>` public surface (6.1.5): `.Length` (dims), `.Memory` (`ReadOnlyMemory<float>`),
  `.IsNull`, `SqlVector<T>.CreateNull(int length)`, ctor `(ReadOnlyMemory<T>)`. **`.ToString()` is not
  overridden** → returns the CLR type name.
- `GetString(i)` / `GetFieldValue<string>(i)` / chunked `GetChars(i, offset, ...)` (SequentialAccess-safe) →
  the JSON array string, shortest-round-trip float32 formatting, uppercase exponent, no spaces:
  `[0.1,0.3,1.1754944E-38,3.4028235E+38,-0.00012345679]` — bit-identical round-trip vs `.Memory` floats
  formatted with "R".
- Chunked `GetBytes(i, ...)` also works → raw TDS payload, e.g. vector(2) `[9.25,-1.5]` =
  `0xA901020000000000000014410000C0BF`: **8-byte header** (`A9` magic, `01` version, dims as UInt16 LE at
  offset 2, element-type/reserved bytes 4-7) then float32 LE values. The in-repo authority for this layout is
  the legacy parser `ServiceBufferFileStreamWriter.VectorBytesToJsonString`
  (`src/Microsoft.SqlTools.ServiceLayer/QueryExecution/DataStorage/ServiceBufferFileStreamWriter.cs:556-592`) —
  it reads `dimensions = BitConverter.ToUInt16(bytes, 2)` and checks `dimensions*4 + 8 == length`.
- `IsDBNull(i)` on a null vector works normally (→ JSON `null` on the wire; nullBitmap bit set).
- Server-side `cast(vector as varchar(max))` yields scientific notation (`1.0000000e-001,...`) — full
  precision but ugly; client-side `GetChars` conversion is strictly nicer.
- SQL Server 2025 vector: element type float32 only; max 1998 dimensions → max wire size 8+7992=8000 bytes;
  as JSON text ≤ ~25 KB — far below the 1 MiB `maxCellBytes`, so **vectors never truncate** at defaults.

### Current STS2 behavior (BROKEN)

`SqlLargeValueReader.ClassifyColumns` (`SqlLargeValueReader.cs:36-54`) has no `vector` case and vector's
`Length` (20/24/...) is bounded, so it classifies as `CellRead.Value` → `reader.GetValue(i)`
(`SqlClientSession.cs:167-179`) → `SqlVector<float>` → `WireValueEncoder` provider fallback →
``{"$t":"provider","v":"Microsoft.Data.SqlTypes.SqlVector`1[System.Single]"}``. Compiles, runs, "succeeds" —
and ships the type name instead of the data. No STS2 test covers vector (only
`test/Microsoft.SqlTools.ServiceLayer.UnitTests/QueryExecution/DataStorage/VectorDisplayTests.cs` covers the
legacy converter).

### Legacy ServiceLayer contrast (works)

- `DbColumnWrapper` knows `vector` (`AllServerDataTypes` entry at
  `src/Microsoft.SqlTools.ServiceLayer/QueryExecution/Contracts/DbColumnWrapper.cs:61`; `IsVector` property
  :182; `case "vector": IsVector = true;` :309-311; `DetermineSqlDbType` maps vector→`SqlDbType.NVarChar`
  :253-255).
- `StorageDataReader.GetValue` uses `sqlDataReader.GetSqlValue(i)` (provider-specific;
  `DataStorage/StorageDataReader.cs:110-113`), and `ServiceBufferFileStreamWriter.WriteRow` special-cases
  `ci.IsVector` → `WriteString(ConvertVectorToDisplayString(values[i]))` (:188-197), handling
  `SqlVector<float>` → `FloatSpanToJsonString(floatVector.Memory.Span)`, `SqlBinary`/`byte[]` →
  `VectorBytesToJsonString` (:521-534).

### Fix options for STS2 (service side, smallest first)

A. **Classify `vector` as `CellRead.Text`** — one line in `ClassifyColumns` (`"vector" => CellRead.Text`,
   note: must not be gated on `unbounded` since vector Length is small). `ReadText` (lines 57-109) then
   streams `GetChars` → plain JSON-array **string** cell on the wire (`"[0.1,0.3,...]"`), full float32
   precision [VERIFIED-LIVE]. Zero encoder/reducer/Core changes; legacy+compact shapes both benefit;
   `typeHints` still says `string` (client keys off `columns[i].type === "vector"` instead).
B. First-class: in `SqlClientSession.PumpResultSetAsync` read `reader.GetSqlVector<float>(i)` and emit a new
   ExecEvent value type, plus a `WireValueEncoder` case emitting e.g. `{"$t":"vector","v":"[...]"}` or a raw
   JSON number array. Richer typing, but touches Abstractions + Runtime + encoder tests, and a new `$t` value
   is a wire-contract addition (additive → two-way door, but needs the D-xxxx decision-log entry per repo
   rules in `sqltoolsservice/CLAUDE.md`).
C. Defensive belt (cheap, worth doing regardless): a `SqlVector` case in `WireValueEncoder`/`EstimateCellBytes`
   so an unclassified vector can never ship a type name again. Note `SqlRowsPageBuilder.EstimateCellBytes`
   (`SqlRowsPageBuilder.cs:80-92`) currently estimates any unknown object at 24 bytes — with option A the
   string case (`s.Length + 2`) is used and page byte accounting stays honest.

---

## 6. GEOMETRY / GEOGRAPHY (and hierarchyid): exact behavior, wire options, fix points

### Current STS2 behavior (query fails)

UDT columns classify as `CellRead.Value` → `reader.GetValue(i)` throws
`FileNotFoundException: Could not load file or assembly 'Microsoft.SqlServer.Types, Version=10.0.0.0, ...'`
[VERIFIED-LIVE on .NET 10; Microsoft.SqlServer.Types is a .NET Framework assembly and is not shipped].
The exception unwinds the pump enumerator → `DriverEffectRunner.StreamQueryPumpAsync` generic catch
(`DriverEffectRunner.cs:530-537`) → `v2/query.complete` `{status:"error", error:{code:"Sts2.Internal",
message:"Driver threw an unclassified exception: FileNotFoundException"}}`. **The entire query dies, not just
the cell.** (Legacy integration test proves the legacy path returns `0xE6100000010C...` instead:
`test/Microsoft.SqlTools.ServiceLayer.IntegrationTests/QueryExecution/DataTypeTests.cs:198-201` GeometryTypeTest,
:210-213 HierarchyIdTypeTest.)

### What works instead [VERIFIED-LIVE]

- Chunked `reader.GetBytes(i, offset, buf, 0, len)` under SequentialAccess streams the UDT's raw bytes:
  - geometry `POINT(-96.70 40.84)` SRID 4326 → 22 bytes `0xE6100000010CCDCCCCCCCC2C58C0EC51B81E856B4440`
  - geography `LINESTRING(-122.360 47.656, -122.343 47.656)` → 38 bytes `0xE610000001148716D9CE...`
  - hierarchyid `0x58` → 1 byte.
  Format = SQL Server CLR serialization ("SqlGeometry serialization format"): SRID Int32 LE first
  (0x000010E6 = 4326), then version byte `01`, flags, coords as float64 LE. (Not WKB — WKB has no SRID.)
  NetTopologySuite's `NetTopologySuite.IO.SqlServerBytes` reads this format directly if client-side decode is
  wanted.
- Server-side conversions for re-query projections: `.STAsText()` → WKT `nvarchar` (`POINT (-96.7 40.84)`),
  `.AsTextZM()` (WKT with Z/M), `.STAsBinary()` → WKB `varbinary` (`0x0101000000CDCC...`, SRID dropped),
  `.STSrid` → `int`. All verified live.

### Fix for STS2

Extend `ClassifyColumns` (`SqlLargeValueReader.cs:36-54`) so UDTs go to `CellRead.Binary`, e.g. match
lowercased `EngineType` by suffix: `.sys.geometry`, `.sys.geography`, `.sys.hierarchyid` (names are
db-qualified 3-part, so exact match is wrong). A generic "unknown type ⇒ binary" rule (the legacy
`AllServerDataTypes` whitelist approach, `DbColumnWrapper.cs:29-62,330-340`) is safer against other UDTs
(user CLR types) — anything not whitelisted reads as bytes and never loads assemblies. `ReadBinary`
(lines 112-155) then produces `byte[]` → `{"$t":"binary","v":"<base64>"}` wire cells, and values above
`maxCellBytes` become honest `truncated` wrappers automatically. geometry/geography metadata says
`IsLong=true`/`ColumnSize=int.MaxValue`, so the existing `unbounded` check pattern also fires if the suffix
rule sets it up like `varbinary`. Optionally capture `column.UdtAssemblyQualifiedName` into a new
`ColumnInfo` field if the client should distinguish UDT kinds without name-sniffing.

---

## 7. End-to-end data path (with timing hooks)

```
SqlClientDriver.OpenAsync (SqlClientDriver.cs:27-59; serverInfo probe :61-93 incl. engineEditionId)
  → SqlClientSession.ExecuteAsync (SqlClientSession.cs:32-119)
      ExecuteReaderAsync(CommandBehavior.SequentialAccess)   ← QO-4, SqlClientSession.cs:128
      PumpResultSetAsync (:149-196)
        ReadColumnsAsync → ColumnInfo[] (:198-218)
        SqlLargeValueReader.ClassifyColumns → CellRead[] (:155)
        per row: IsDBNull / ReadText / ReadBinary / GetValue (:167-179)
        SqlRowsPageBuilder.Add — pages close on pageRows OR approx pageBytes (SqlRowsPageBuilder.cs:39-52)
      yields ExecEvents: ResultSetStarted / RowsPage / ServerMessage / ResultSetCompleted / ExecCompleted
  → DriverEffectRunner.StreamQueryPumpAsync (DriverEffectRunner.cs:401-542)
      backpressure gate: pump.Credits.WaitAsync per RowsPage (:460) — at most ONE page read beyond window (R012 note :429-435)
      SerializeRows → WireValueEncoder per cell (:611-627)
      compact extras: PackNullBitmap (:549-566), SerializeTypeHints once per set (:428,450,573-594)
      per-page stats measured here: readMs / creditWaitMs / encodeMs / encodedBytes (:458-486)
      posts driver.queryEvent effect payloads (journaled)
  → Sts2CoreReducer.DecideQueryEvent (Sts2CoreReducer.cs:738-845)
      "resultSet" → v2/query.resultSet (:743-749)
      "rows" → v2/query.rows, legacy|compact by payload shape (:751-771); stats NOT forwarded to the wire
      "completed|error|canceled" → v2/query.complete (:784-808) + sts2.query.stats diagnostic (:815-822)
```

### Timing/metric surfaces relevant to the perf requirements

- **Per-page pipeline stats** ride the *journaled* `driver.queryEvent` payloads only:
  `"stats":{"rowCount","encodedBytes","readMs","creditWaitMs","encodeMs"}` (`DriverEffectRunner.cs:486`).
  `readMs` approximates driver/enumerator time as gap-since-last-event; credit wait and encode are exact
  (comment :421-424).
- **Per-query aggregate** on the completed event: `{"pages","rows","encodedBytes","readMsTotal",
  "creditWaitMsTotal","encodeMsTotal"}` (`DriverEffectRunner.cs:502`) → surfaced by Core as ONE diagnostic
  envelope `kind:"diag"`, `type:"sts2.query.stats"`, data `{queryId, connectionId, status, pagesSent, stats}`
  (`Sts2CoreReducer.cs:815-822`; QO-2). Journal + live tail only — **not** on the v2 wire.
- **Observation seams** (`docs/sts2/OBSERVABILITY.md`): `IEnvelopeSink` (every envelope in seq order, journal
  is write-ahead first sink); `Sts2Session.LiveTail` (`BroadcastEnvelopeSink`, bounded 4096, drops-oldest with
  drop counters); `Coordinator.Metrics` (`MetricsEnvelopeSink`); EventSource `Microsoft-SqlTools-Sts2`
  (`envelopes-total`, `rpc-errors-total`, `sink-faults-total`); `v2/diagnostics.health` (queueDepth,
  activeQueryPumps, droppedDiagnostics, errorsByCodeTotal); `v2/diagnostics.state`. The vscode-mssql
  session-diag viewer tails these — new pane fetches will show up as ordinary v2 traffic + `sts2.query.stats`.
- Privacy: default capture is `digest` — journals hold **no row cells or SQL text** in product mode
  (`docs/sts2/SPEC.md:699`, D-0012); never log row payloads from the client side either
  (`sqltoolsservice/CLAUDE.md` rules).

---

## 8. Whole-column / full-precision fetch: existing endpoints vs new endpoint

**STS2 is strictly forward-only push**: there is no subset/re-read endpoint (`forwardOnlyStreaming`
capability; method table has nothing like the legacy `query/subset` —
`src/Microsoft.SqlTools.ServiceLayer/QueryExecution/Contracts/SubsetRequest.cs:61` exists only on the legacy
path, which keeps a disk-backed buffer). On STS2 the client's own page cache is the only store; a "fetch
column" operation is either (a) served from cached pages, or (b) a **new `v2/query.execute` projection
re-query** (e.g. `SELECT [vec] FROM (...)`, `SELECT col.STAsBinary(), col.STSrid FROM ...`).

Constraints that shape the design:
1. **`oneActiveQueryPerConnection`**: a re-query while the main grid query still streams gets `Sts2.Busy`
   (`Sts2CoreReducer.cs:448-451`). Lazy tabs must either wait for `v2/query.complete` or open a dedicated
   side `v2/connection.open` (cheap; `maxConnections` default 64).
2. **`maxCellBytes` is lower-only, pinned at 1,048,576**: a client can never raise it (STS2-3 / SPEC-CHANGE-0001).
   Cells >1 MiB always arrive as `{"$t":"truncated","of","bytes","digest","v"}` with the retained prefix
   further capped at 65,536 bytes. Vectors never hit this (≤ ~25 KB). Large geometries (multi-MB polygons)
   WILL truncate — full-fidelity fetch of those needs server-side chunking via re-query
   (`SUBSTRING(CAST(col AS varbinary(max)), @off, @len)`), server-side simplification (`.Reduce(@tol)`), or a
   SPEC-CHANGE (raising the pinned bound or adding a raw-fetch endpoint requires the human-gated
   `SPEC-CHANGE` process per `sqltoolsservice/CLAUDE.md` / `docs/sts2/DECISIONS.md`).
3. **Full precision is a non-issue once the driver fix lands**: vector cells carry shortest-round-trip float32
   text; spatial cells carry exact raw bytes (base64 ≈ +33% size). No second "high-precision" fetch channel is
   required for correctness — only for *bulk columnar efficiency*, where a compact-rows projection re-query
   (1000-row/256 KiB pages, null bitmap included) is already a decent columnar transport.
4. If a dedicated bulk shape is ever wanted (e.g. base64 packed float32 column blocks), the additive-field
   pattern is well-precedented (compact rows D-0016, engineEditionId D-0017): new opt-in execute option + new
   capability flag + scenario pin, two-way door if additive.

**Recommendation embedded in the findings**: for the vector tab, cached compact pages (or a projection
re-query on a side connection) + the §5A driver fix are sufficient; for the spatial tab, same plus a
truncation-aware path (detect `$t:"truncated"` → re-query that row's geometry chunked or as WKT).

---

## 9. Test & verification landscape

- STS2 tests: `test/sts2/Microsoft.SqlTools.Sts2.UnitTests` (xunit; `Drivers/WireValueEncoderTests.cs` pins
  the encode matrix — no provider-fallback/vector/geometry cases today), `Runtime/QueryFlowTests.cs`
  (`CompactRowsOptInSwitchesTheWireShape`, `MultiResultSetStreamCompletesWithPerQueryOrdinalAcks`),
  `Runtime/QueryPipelineStatsTests.cs` (one `sts2.query.stats` per query), scenario YAMLs under
  `test/sts2/scenarios/` (e.g. `cell-truncation-max-cell-bytes.yaml`) run by the Testing project's
  ScenarioRunner against FakeDriver. **No scenario or test covers vector or spatial types on STS2.** New
  driver classification behavior should get: WireValueEncoderTests additions, a live-SQL integration test
  (legacy repo pattern: `DataTypeTests.cs`), and a scenario pin if the wire shape changes.
- Definition of done on this repo: `./verify.sh --quick` green + report entry; never weaken tests; SPEC §7.7
  changes to encoding are SPEC-CHANGE; additive fields are two-way doors logged as D-xxxx in
  `docs/sts2/DECISIONS.md` (`sqltoolsservice/CLAUDE.md`).
- The SPEC's M-milestone exit criteria include a type-encoding matrix line: "decimal, datetime, datetime2,
  datetimeoffset, date, time, money, binary, guid, xml/json text, null/DBNull, provider-specific passthrough"
  (`docs/sts2/SPEC.md:1342`) — vector/spatial were simply never in the matrix.

## 10. Empirical probe (reproducible)

Probe project: `C:/Users/karlb/AppData/Local/Temp/claude/C--repos-test/9a332f8d-c84b-4237-bc2b-c91f94a68e56/scratchpad/typeprobe/`
(net10.0 console, `Microsoft.Data.SqlClient 6.1.5`, `Server=localhost;Integrated Security=true;
TrustServerCertificate=true` — host SQL 2025 via shared memory; TCP is disabled on the host instance).
Ran three passes: (1) SequentialAccess + GetColumnSchema + IsDBNull/GetValue per ordinal (the exact
`SqlClientSession` pattern), (2) alternate accessors (`GetSqlVector<float>`, `GetString`, `GetSqlBytes`,
`GetFieldValue`), (3) chunked `GetBytes`/`GetChars` streaming (the exact `SqlLargeValueReader` pattern) and
server-side conversion projections. All results quoted in §4-§6 came from these runs on 2026-07-11.
