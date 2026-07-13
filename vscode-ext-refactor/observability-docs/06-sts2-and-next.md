# 06 — STS2, the Retrofit Status, and the Next Round

**Updated: 2026-07-04.** STATUS: the hardening asks in §2 landed as STS2 review waves R001–R047 (lifetime/fatal containment, pump barriers, strict/partial replay split, observer mailboxes, capture policy, bounded cancel, run isolation) — see sqltoolsservice git log 'STS2 review'. Chunks 1–6 of the rock-solid plan are complete; see 07 for the Phase-2 branch guide. Where the sqltoolsservice rebuild fits into the
observability picture, what is already integrated, and the seams for what
comes next. STS2's own docs (`sqltoolsservice/docs/sts2/`) are authoritative
for its internals; this doc covers the *relationship*.

## 1. STS2 in one paragraph

STS2 is an in-place rebuild of the SqlToolsService core: a
**StdioMultiplexer** splits the legacy dispatcher so v2 traffic runs beside
legacy (single stdout writer, crash containment), a **versioned wire
contract** with journaled **envelopes** (canonical payload digests, capture
modes, secret handling, export bundles), a **deterministic core**
(runtime pump + core reducer + effect runner, replay/time-travel with
divergence detection), a **pluggable driver port** (SqlClient, Sqlite,
FakeDriver adapters + engine-truth corpus), and a heavy **testing strategy**
(scenario corpus, invariants, simulator, engine matrix, mutation/Stryker).
See `SPEC.md` §3–§14, `OBSERVABILITY.md`, `TRACE-SCHEMA.md`.

## 2. The observability seam alignment

STS2's `IEnvelopeSink` (every envelope journaled then handed to observers in
`seq` order) is the same architectural shape as the extension's diag-core
sink registry. The two vocabularies meet in the Debug Console:

| Today (legacy STS) | Future (STS2) |
|---|---|
| `StsDiag` spans (protocol metadata only) over the `STS_DIAG_URL` loopback → console lanes | Envelope stream per `TRACE-SCHEMA.md` → the console's "diagnostic event viewer" integration named in `OBSERVABILITY.md` |
| Coarse: dispatcher + hot seams (sql/smo/dacfx) | Complete: every inbound RPC, core output, effect, control, config change — with digests and replayability |

Console features intentionally **gated on STS2 hardening** (kept as gated
pages in the console shell): Replay Lab (STS2 replay/time-travel §13) and
full STS capture/export. The gating principle: the console never grows
capabilities the legacy service can't honestly back; STS2 lands them with
determinism guarantees.

Rule that protects the rebuild: legacy-side instrumentation (everything in
`03-instrumentation-reference.md` §2) touches only the sanctioned seams and
never legacy code outside SPEC §5; STS diag stays metadata-only and inert
without the env gate.

## 3. Retrofit status: what is DONE

- **Substrate**: classified event core + sinks + stores + redaction choke
  point; startup-to-shutdown capture; self-noise exclusion. (01, 02)
- **Instrumentation**: extension marker families incl. designers/compare;
  STS dispatcher + sql/smo/dacfx + designer DesignServices spans; rich
  collection; harness span forwarding with the official gate proven green.
  (03)
- **Surfaces**: Debug Console with Overview/Trace (live controls + filter
  language)/Waterfall (native-scroll zoom, event details)/Perf Test History
  (scalable index, group drill-down, diagnostics tab, run hygiene)/Session
  History/self-test dialog. (02)
- **Harness integration**: in-proc engine + catalog, run-directory contract
  shared by CLI and self-test, history browsing both directions. (04)
- **Test coverage**: suites + reliability playbook. (05)

## 4. Known deferred items (recorded, intentional)

- ~~CLI designerOpen port~~ DONE (Chunk 4, 8/8 reps live-proven).
- ~~Session-diag size cap~~ DONE (Chunk 2, mssql.sessionDiag.maxTotalMB).
- SQL Database Projects extension instrumentation (separate extension).
- Console SQLite source (read-only preview stub; driver strategy open).
- Zip bundle import for run sharing (directory bundles work).
- XEvents collector MVP wiring for the sql recipe; heap snapshots for soak.

## 5. Seams for the next round

Where the architecture is deliberately open:

1. **STS2 envelope ingestion** — an `IEnvelopeSink` observer that speaks the
   loopback channel (or reads journals) would light up the gated console
   pages; `TRACE-SCHEMA.md` is the contract to import against
   (`importPerfRep` is the pattern to follow).
2. **Provider abstraction in Perf Test History** — sources are pluggable;
   a real SQLite provider (or an STS2-journal provider) slots in beside the
   directory provider.
3. **Scenario catalogs** — both engines take new scenarios cheaply; the
   designers/DacFx family is the next natural expansion (publish flows,
   schema compare end-to-end, project build/publish once sql-projects is
   instrumented).
4. **Filter language** — `traceFilter.ts` is a pure shared module; new
   predicates (corr:, tag:, has:perf) are additive.
5. **Waterfall** — the zoom viewport is self-contained in
   `waterfallView.tsx`; minimap/overview strip and flame-graph modes are
   natural extensions without new controls.
6. **Cross-run analysis** — the metric series RPC + trend charts are the
   base for regression annotations in-product (mirroring the harness gate
   verdicts in the UI).
