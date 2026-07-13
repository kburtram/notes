# Remaining Work Inventory — `dev/query` (vscode-mssql, sqltoolsservice, perftest)

**Date:** 2026-07-05 (written after QS-P1 QoL batch, Entry 11; language service through B9)
**Purpose:** one place that answers "what was proposed in the designs that we have not built yet, and what does it take to get these components ready for review and release." Sourced from the design docs, execution plans, and PROGRESS journals across `coding-docs/{observability,debug,perftest,ssms-query,language-service,oe}-docs`, `perftest/PROGRESS.md`, and `sqltoolsservice/docs/sts2`.
**How to read:** §1 is where each component stands today. §2 is the binding decisions that shape the remaining work. §3 is the inventory, grouped by component and tiered (P0 = needed for the preview/review bar of that component, P1 = pre-GA, P2 = backlog/decide-later). §4 is the recommended build-out sequence. §5 is the standing manual-validation ledger (things that need a human + live server, not more code).

> Journal-vs-plan drift warning: `perftest/IMPLEMENTATION_PLAN.md` has stale unchecked boxes (16.7–20.11) for work that PROGRESS Entries 25–37 record as BUILT. This inventory trusts the journals; the items below are the ones the journals themselves record as deferred.

---

## 1. Current state

| Component | State (verified 2026-07-05/06) |
|---|---|
| **STS2 service** (sqltoolsservice `src/sts2`, HEAD `7a99455f`) | v2 core complete through review waves R001–R047: connect/query/cancel/dispose, message verbatim + `line`, `database` on `v2/query.complete`, capture policy, SecretRedactor, journal/trace schema. `verify.sh --quick` green. **Preview tag `sts2-v2.0.0-preview` not yet applied** (M7 human gate). |
| **SQL Data Plane client** (vscode-mssql `src/services/{sqlDataPlane,sts2}`) | Domain API + STS2 backend conformance-proven (ordered lanes, ack ledger, invariants, deadline synthesis); wire DTO containment lint-enforced. Fake backend with chaos knobs. |
| **Query Studio** (B1–B7 + QoL batch, HEAD `611ce7d55`) | Custom editor, sync engine, execution pipeline, RowStore+spill, results/messages UI, plans (flagged, not rendered as tabs), db dropdown, metadata wired, completions (both editors), Replay Lab, run records, SSMS-parity QoL (timer, USE tracking, TRAN badge/guard, options engine, XML/JSON links, NULL/grid styling, filter/sort, lazy grids). Suite 3529 passing; gates 16/16. |
| **MetadataService** (`src/queryStudio/metadataService.ts` + catalogModel) | H0–H6 hydration (env, schemas, objects, columns+identity/computed, PK columns, FKs+pairs, params), immutable generation snapshots, readiness/failure honesty, DDL sniff + digest poll, `buildSchemaContext` with MD-4 golden parity. **Per-document, single-session; not key-correct for multi-database** (the OE v2 blocker). |
| **Language service** (B8–B9, `src/sqlLanguage`) | Full-fidelity lexer, segmenter, sketch parser, overlay, binder v1, context classifier, native completions (FK joins, star expansion, scaffolds, deterministic ranking), engine toggle `mssql.queryStudio.languageService.engine`, router with maturity gate + circuit breaker, STS v1 bridge with lazy shadow connection. 93 tests; warm completion p95 0.15 ms. |
| **Completions/AI** (ported B6) | Inline completions on `buildSchemaContext` in both editors, model selection, InlineCompletionDebug panel + replay matrix, acceptance telemetry. |
| **Debug Console** | Full shell + timeline/waterfall/perf-history pages; Perf Test History refactor (providers, Runs Summary/Run Analysis, virtualized tables, lazy tabs) landed per perftest Entries 25–37; feature-capture framework with 2 instantiations (completions, QS run records). `completions`/`replay` left-rail pages gated; STS2 live source gated. |
| **Perftest** | CLI + scenario harness, 4 standing gates green (16/16 reps, run `a9447d30`), store/history/head-to-head, XEvents *collector* built (recipe wiring deferred), self-test, contracts registry re-vendor workflow, 110/110 workspace tests. |
| **Object Explorer v2** | Design pack only (`oe-docs/`, reviewed 2026-07-05): MetadataStore substrate spec, OE v2 view spec, classic-backend scaffolding spec. **No code yet** — next big effort, plan in `oe-docs/EXECUTION_PLAN.md`. |

---

## 2. Key design decisions in force

These are the decisions that remaining work must respect (sources: design docs + journals; the addendum and registry notes are BINDING):

1. **Data plane is the only connection/query dependency for new features.** STS2 wire DTOs importable only under `src/services/sts2/` (lint-enforced). No `mssql.sts2.*` settings — switches are `mssql.sqlDataPlane.enabled`/`.backend`.
2. **STS v1 is a handoff tool, not a substrate.** Query Studio has no v1 fallback; the language service uses a lazy shadow v1 connection only via the bridge engine (retirement is a B14 deliverable); OE v2 allows v1 only through explicit, measured legacy handoff (H1/H2/H3 ladder).
3. **Privacy is mechanical, not editorial.** SQL text/rows/secrets never in diagnostics by default and never plaintext regardless of settings; every diag field classified; settings values never interpolated raw into SQL; privacy canaries are part of the definition of done.
4. **Official vs diagnostic separation.** Gates run only on official metrics; rich diagnostics (SQL activity, renderer traces, heap dumps) are investigation context. No fabricated metrics — absence is surfaced as absence.
5. **Readiness honesty.** Failed metadata/catalog sections are never rendered as empty; ready-empty is distinct from failed/loading/permission-denied everywhere (metadata sections, OE folders, perf history tabs).
6. **Commit isolation.** `core:` (contracts/registry, DC core, STS2 service-side, lint infra) / `qs:` (queryStudio, data plane binding, metadata, completions) / `ls:` (sqlLanguage, sqlScripting) — and OE v2 will need its own `oe:` train. Upstream PRs split along these lines.
7. **Contracts discipline.** New diag vocabulary lands in the perftest contracts registry first, regenerate + re-vendor, then emit. Unregistered emissions are conformance failures.
8. **Metadata generations are immutable and never mixed within a response.** Pin once per request/expand.

---

## 3. Inventory of remaining work

### 3.1 STS2 service layer (sqltoolsservice)

| Pri | Item | Detail | Source |
|---|---|---|---|
| **P0** | **M7 preview close-out** | `verify.sh --full`, Stryker mutation ratchet, 10,000-seed simulator run, final docs pass, human review → `sts2-v2.0.0-preview` tag. This tag is the trigger the Debug Console STS2 pages and Stage C are gated on. | SPEC §16, AGENT-RUNBOOK |
| **P1** | Capture effective-mode echo | Client never calls `v2/diagnostics.setCapture`; service should echo effective/host-bounded capture mode so run records don't rely on client-side policy recording alone. Recorded gate exception (worksheet row 9). | SPEC, DECISIONS D-0012, ssms-query worksheet #9 |
| **P1** | Honor `maxCellBytes` on the wire | Service still ships full cells; QS clamps client-side (2048 display / 512 tooltip). Service-side truncation with honesty flag is the real fix for blob rows. | ssms-query PROGRESS Entry 11 DEVIATIONS |
| **P2** | Envelope→OTel/OTLP sink, W3C traceparent, `v2/diagnostics.health` polling, envelope→marker `IEnvelopeSink` | Observability adapters; seams preserved, deliberately unbuilt "until v2 traffic makes it useful." The `IEnvelopeSink` loopback is what lights up the DC live STS2 source. | STS_INSTRUMENTATION.md, 06-sts2-and-next §5 |
| — | Reserved envelope kinds (`cmd`, `evt`, `state.snapshot`, `timer.due`) | Schema-declared, intentionally unproduced in v2.0. Not work — recorded so nobody "fixes" it. | TRACE-SCHEMA.md |

Out-of-scope-by-design (stays legacy or moves client-side): language service, IntelliSense, OE, edit data, scripting, plans, schema tools, notebooks, profiling, server-side batch splitting, random-access grid caching (SPEC §2). The client-side rehosts (language service, OE v2, scripting) are exactly the vscode-mssql efforts below.

### 3.2 Metadata service → MetadataStore

The OE v2 design pack (`oe-docs/metadata_service_oe_v2_design.md`) turns most of this section into the **next funded effort** (MD-0..MD-7). Items marked ⭢OE land inside that plan rather than as separate work.

| Pri | Item | Detail | Source |
|---|---|---|---|
| **P0 ⭢OE** | Key-correct multi-database acquisition | `MetadataSessionSource.open()` receives no `CatalogKey`; one cached session can hydrate the wrong database. Fix via key-aware source + per-database sessions (preview-safe) before any multi-db tree. | oe-docs MD-2; metadata design §6 |
| **P0 ⭢OE** | ServerCatalog / `ServerMetadataService` | Visible databases + server facts as a first-class service (S0–S1). Today `executionHost.listDatabases()` serves the combo. Declared in 02-design M4, never built. | ssms-query PROGRESS Entry 6; oe-docs MD-3 |
| **P0 ⭢OE** | Shared store + leases | `IMetadataStore` with refcounted server/database/object leases replacing per-document `MetadataService` instantiation; QS + language service migrate onto it (MD-4). | oe-docs MD-1/MD-4 |
| **P1 ⭢OE** | OE-grade object details | PK/unique constraint **names**, reverse FK pairs, indexes (key order/included/filter/uniqueness), default/check constraints, module definitions (+encrypted state), identity seed/increment, `listObjects()` that isn't an empty-prefix search hack. | oe-docs MD-5/MD-6 |
| **P1** | H7 descriptions (`MS_Description`) | Needed for hover (LS B11) and OE properties; also gated on the remoteLm privacy question (addendum §9). | 02-design §7.2; LS plan B11 |
| **P1** | Metadata perf scenarios | `hydrate-cold/warm`, `context-build`, plus the OE store probes (`acquireDatabase.warm`, `listObjects.10k`, `getColumns.150k`). Deferred because FakeBackend's empty catalog would measure overhead only — needs realistic large-catalog fixtures first. | ssms-query PROGRESS Entry 9; oe-docs §14.5 |
| **P2** | Disk cache (manifest + `catalog.mdc`) | Backlog until language-service cold-start metrics exist; warm completions benefit most. Not required for OE v2 preview. | Entry 6 residuals; 02-design §11 |
| **P2** | Deep digest tiers / scoped delta refresh / 30% rule / metadata-lite mode | Cheap DDL-sniff + CHECKSUM_AGG digest built; the scoped `object_id IN (...)` delta path and large-catalog lite mode are spec'd, unbuilt. | 02-design §7.5/§9.4 |
| **P2** | H8 row counts | Optional, off by default; only if OE UI displays them. | 02-design §7.2 |

### 3.3 Language service (B10–B14 — the plan's own remaining batches)

| Pri | Item | Detail | Source |
|---|---|---|---|
| **P0** | **B10 / LS-2 native diagnostics** | T1 lexical/structural + T2 binder (207/208/209) with suppression ladder, debounced sliced scheduler, honesty suite; batch-level GO-junk diagnostic; per-statement effective-db binding (`core/databaseContext.ts` split). | LS EXECUTION_PLAN; PROGRESS Entry 3 |
| **P0** | **B11 / LS-3 hover + signature help** | Tooltips over binder + H7 descriptions; builtin signatures already in data assets. | LS plan |
| **P0** | **B12 / LS-4 scripting engine + definition** | `src/sqlScripting/**` (ModuleEmitter CREATE→ALTER, CreateTable/DmlTemplate emitters), definition/peek routing; module-definition + index metadata sections land here. **OE v2 Script-As routes through this** — sequencing matters. | LS plan; oe-docs V2-8 |
| **P1** | **B13 / LS-5 semantic polish** | Document highlights, semantic tokens (full+delta), code actions (expand star, qualify column, add alias, fill GROUP BY), feature-capture instantiation #3. | LS plan |
| **P1** | **B14 / LS-6 audit + flip decision** | Fourslash corpus to 150+ (now ~60), native-vs-bridge head-to-head (PERF_MODE probe `mssql.perf.sqlLanguage` + `querystudio-language-completion` scenario), default-flip + classic-editor preview decision, **shadow-v1 deprecation plan**. | LS plan; Entry 3 residuals |
| **P2** | B9 small residuals | MRU accept-history boost, lazy documentation resolve, `sp_*` system-proc catalog via `systemObjects()` (worksheet #5), keywordCasing `asTyped`. | Entry 3 |
| **P2** | batchSplitter convergence onto the full lexer | Execution splitter and metadata DDL sniffer share the old splitter; converge once stable (don't destabilize). | Entry 2 deviations |
| **open** | Worksheet #1–#4 | Aggregation pollution, shadow status-bar side effects, backing-doc close vs panel lifetime, CS_AS live seed DB — all need live dogfood (see §5). | LS worksheet |

### 3.4 Query Studio

| Pri | Item | Detail | Source |
|---|---|---|---|
| **P0** | Plan TAB rendering | Plan result sets are detected + flagged but listed as grids; the classic `executionPlan` webview page exists for reuse. Biggest visible parity gap left. | Entry 5 residuals |
| **P1** | Per-cell context menu; Ctrl+R conflict check | Small UX parity items from B4. | Entry 5 |
| **P1** | Grid convergence decision | Custom virtualized table vs FluentResultGrid/slickgrid: decide before public preview (recorded deviation, twice). `autoSizeColumnsMode` and the `fluentSlickGrid.css` theme delta ride on this decision. | Entries 8/11 DEVIATIONS |
| **P1** | Wide/blob grid perf scenarios | QS equivalents of classic `query-wide-columns`/`query-blob-xml`; pairs with service `maxCellBytes` work (§3.1). | Entry 11 |
| **P1** | Untitled/Save-As exploratory test | Custom-editor Save-As behavior (doc 04 §7.2) still unproven. | Entry 1 residuals |
| **P2** | SQLCMD mode, results-to-file-during-execution, Excel export, multi-server query, web mode | Explicit v1 non-goals in the master design/addendum; keep the toolbar/tab model extensible, revisit post-preview. | 04-design §2; addendum §9 |
| **P2** | Spill frame format revisit | JSON v1 frames; binary/columnar only if measurement demands. | addendum §9 |
| **P2** | Classic-resolver LRU eviction on connections change | Completions schema-context resolver LRU(8) has no `onConnectionsChanged` eviction. | Entry 8 |
| **P2** | QS replay matrix profile axes | v1 axes = database × mode; profile-style axes when QS grows config profiles. | Entry 9 |

### 3.5 Debug Console

| Pri | Item | Detail | Source |
|---|---|---|---|
| **P0 (post-tag)** | Stage C: live STS2 source | `mssql.debugConsole.experimental.sts2Source` — envelope source into the console. Gated on the STS2 preview tag + `IEnvelopeSink` adapter (§3.1). | DC tech design §4.3 |
| **P1** | DC embedding of Completions + Replay Lab panels | Both shipped as dedicated panels; DC left-rail pages remain gated stubs. Follow-up UX, twice recorded. | Entry 9; perftest Entry 20 |
| **P1** | §24 shipping decisions | Which pages ship experimental/internal/support-facing; capture-policy UX; owner calls flagged not decided. Needed before any DC-visible release. | DC tech design §24 |
| **P1** | Stage D: replay-drive matrix growth | Feature replay for Query (gated), Connection (gated), OE + results-grid rendering (future). STS2 Replay Lab (C7: envelope import, state-at-seq diff, strict replay) intentionally not started. | DC design §4.4; next_steps §24–26 |
| **P2** | Investigation Workbench + dedicated compare-waterfall view | Compare bottom tab exists (marker-pair phase deltas); the baseline-above-candidate waterfall and workbench page do not. | next_steps §16/17/21 |
| **P2** | Perf-history SQLite source (real) + zip bundle import | SQLite is an honest "unsupported" stub (`better-sqlite3` ABI in extension host unresolved: worker/WASM/keep-directory). Zip import needs a zip dep; directory bundles work. | perftest Entry 25 |
| **P2** | Self-test polish | Config-file selection + custom test JS, in-dialog connection picker, soak built-ins exposure, run-label editing, export-selection, env-mismatch warnings on compare, dedicated Renderer/Memory/CPU chart tabs. | perftest Entries 24/25/37 |

### 3.6 Perftest / observability

| Pri | Item | Detail | Source |
|---|---|---|---|
| **P1** | **XEvents: recipe wiring + measurement calibration** | Correction to the docs' framing: XEvent capture is NOT unparsed — `sqlServerXEvents.ts` shreds the ring buffer to `sql-activity.jsonl` + rollup, correlates per-command rows by Application Name, and normalizes `sqlserver.duration/cpu/logicalReads/commandCount` metrics (waterfall + SQL Activity tab consume them). What remains: the one-flag `sql` diagnostic recipe wiring, and the §12.3 calibration pass that could promote the collector beyond `allowedPassTypes: ["diagnostic","calibration"]`. | 06-sts2-and-next §4; collectors/sqlServerXEvents.ts |
| **P1** | Central results aggregation | Upload/sync, CI trends, Grafana/Bencher — deliberately deferred "decide with user." Now specified: see `observability-docs/options_for_central_tracing.md` (companion doc). | IMPLEMENTATION_PLAN deferred; PHASE_4 final line |
| **P1** | CI/fleet ladder | Nightly baselines, rolling trends, per-tier CI gates, flake/invalid-rep ledger, signed run manifests. Operating-model work; pairs with central aggregation. | next_steps §27–29 |
| **P1** | Multi-rep QS baseline accrual → gate maturity review | `querystudio-query-10k` official but young history; standing gates review once history deepens. | Entry 9 |
| **P2** | Heap-snapshot soak attribution recipe | Collectors exist (`cdpHeapSnapshot`/`gcDump`); the recipe path + attribution flow is backlog. | next_steps §20 |
| **P2** | `mcp-server-first-request` scenario | Deferred until MCP surface stabilizes. | IMPLEMENTATION_PLAN |
| **P2** | SQL Database Projects instrumentation | Separate extension; not instrumented. | 06-sts2-and-next §4 |
| **P1** | "Decisions to freeze" (8 open of 10) | Schema ownership, bundle format/signatures, capture-policy UX, STS2 viewer-timing readiness, SQLite strategy, scenario-maturity ownership, telemetry boundary for CI dashboards, support-bundle workflow. Cheap to decide, expensive to leave open. | next_steps "Decisions to freeze soon" |

### 3.7 Object Explorer v2 (newly funded — for completeness)

The whole `oe-docs/` pack is remaining work by definition: MetadataStore substrate (MD-0..7), OE v2 view (V2-0..9: shell + no-v1 tripwires, data-plane sessions, server/database catalogs, tree, native commands, table preview, legacy handoff, scripting migration, default-flip readiness), and optionally the classic-backend scaffolding (OE-0..8, explicitly deprioritized to fixture capture). Tracked in its own `oe-docs/EXECUTION_PLAN.md`, not duplicated here.

---

## 4. Recommendation

**Ordering principle:** fund work that retires a *substrate risk* or unlocks a *gated consumer* before polish; let big items absorb their satellite items instead of scheduling satellites separately.

1. **OE v2 + MetadataStore now** (already directed). This one effort absorbs the largest metadata backlog cluster: key-correct acquisition, ServerCatalog, store/leases, object details, `listObjects`, large-catalog fixtures, and the metadata perf scenarios. Build MD-0..MD-4 first (store under Query Studio and the language service, behavior-preserved), then the OE view on top — per the design pack's own priority guidance. Skip the classic-backend track except fixture capture (OE-0), which is cheap and de-risks node/command compatibility.
2. **Language service B10–B12 next** (diagnostics → hover → scripting+definition). B12's scripting engine is what lets OE v2 route Script-As natively instead of growing more legacy handoff, and B11's hover consumes H7 descriptions added during store work. Then B13–B14, whose head-to-head + flip decision also produces the shadow-v1 deprecation plan.
3. **STS2 M7 preview tag** in parallel (it's a verification + human-review milestone, not feature work). It unblocks DC Stage C and settles the capture-echo question. Fold `maxCellBytes` honoring into the same service pass.
4. **Release-readiness pass** once OE v2 preview + LS flip candidate exist: burn down §5's manual-validation ledger in a structured dogfood week, settle the DC §24 shipping-surface decisions and the 8 open "decisions to freeze," and make the QS grid-convergence + plan-tab calls (plan tab is the one QS feature gap users will hit immediately in review).
5. **Observability round after that:** XEvent parsing → SQL Activity (single highest-value diagnostics item), then central aggregation per `options_for_central_tracing.md`, then the CI ladder. These multiply in value once more people (team upload/dogfood) and more machines (CI) are producing runs — which is exactly what the release push creates.

Items *not* worth scheduling as standalone work: disk cache (wait for LS cold-start data), digest deep tiers (wait for a real drift-scale complaint), SQLite provider (wait for the driver-strategy decision), reserved envelope kinds (by design), spill format (wait for measurement).

---

## 5. Manual validation ledger (human + live server; no code owed)

Accumulated across journals — a structured dogfood session can burn all of these down:

1. Typed-`USE` dropdown/status follow-through (QS Entry 11).
2. TRAN badge + disconnect-guard UX feel (Entry 11).
3. Filter/sort widget feel on real data; grid styling settings visual check; XML/JSON cell-link documents (Entry 11).
4. 30-minute dogfood resync-count-zero gate (B1 residual).
5. Native completions live dogfood with `mssql.queryStudio.languageService.engine=nativeTypeScript` (B9).
6. LS worksheet #1 aggregation pollution / #2 shadow status-bar side effects / #3 backing-doc close lifetime — observe with a connected QS document.
7. SqlLogin credential-seeding path in perftest (box provisions Integrated only).
8. CS_AS collation seed database for case-sensitivity gates (LS worksheet #4).
