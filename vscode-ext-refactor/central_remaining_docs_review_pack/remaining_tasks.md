# Remaining Work Inventory and Release Scoping - `dev/query`
## vscode-mssql, sqltoolsservice, perftest, MetadataStore, Language Service, Object Explorer v2, Debug Console, and central observability

**Status:** reviewed replacement, 2026-07-06.
**Purpose:** one place that answers: what remains, what blocks review or preview, what can run in parallel, and which tasks should not be scheduled as standalone work yet.
**Source hierarchy:** current code and progress journals win over older execution-plan checkboxes; design docs define target direction; this inventory defines current sequencing and scope.
**Companion doc:** `options_for_central_tracing.md` now defines the central observability store and upload pipeline.

> Maintenance rule: update this document when a workstream crosses a phase boundary, when a setting/default changes, when a preview gate moves, or when a “decision to freeze” is ratified. Otherwise it becomes a museum label taped to a rocket.

---

## 0. Technical review of the draft

The draft is strong. It correctly trusts the journals over stale plan checkboxes, captures the main substrate decisions, and identifies OE v2 plus MetadataStore as the next large funded effort. It also makes a useful distinction between code owed and live-server/manual validation owed.

This replacement makes these improvements:

1. **Adds an evidence-confidence layer.** Several rows contain precise state claims. Those are useful, but a coding agent needs to know whether a claim is code-verified, journal-reported, design-only, or manual-validation-pending.
2. **Separates critical path from background rails.** OE v2 and MetadataStore are the main product substrate risk. STS2 M7, central observability C0/C1, and CI artifact wiring can run in parallel without waiting for OE v2.
3. **Aligns central observability with the new companion doc.** Central SQL store C0/C1 and CI artifact wiring should not be delayed until the very end. In-product upload and central Debug Console readback can wait until the foundation is stable.
4. **Corrects wording around XEvents.** XEvent collection and shredding are built; the remaining work is recipe wiring, calibration, and maturity promotion, not “parsing from scratch.”
5. **Makes task IDs more agent-friendly.** The inventory now has stable IDs, dependencies, acceptance gates, and suggested commit train labels.
6. **Distinguishes preview blockers from pre-GA work.** P0 means “needed for that component’s preview/review bar.” It does not mean every P0 across every component must finish before any work can merge.
7. **Promotes decision debt.** The “decisions to freeze” are now tracked with proposed owners and consequences.
8. **Adds a release-slice recommendation.** Rather than one long list, the document now proposes a sequence of slices that produce reviewable PRs without turning the repo into a single tangled scarf.

---

## 1. Priority definitions

| Priority | Meaning |
|---|---|
| P0 | Required for the preview or review bar of the named component, or required to remove a substrate correctness risk. |
| P1 | Required before broader preview, public review, default flip, or GA, but not a blocker for the next narrow slice. |
| P2 | Backlog, decide-later, or measurement-dependent work. Keep the seam, do not fund until evidence says it matters. |
| Open | Needs live dogfood, product decision, or external input before code should be written. |

Evidence confidence:

| Tag | Meaning |
|---|---|
| Code-verified | Checked in code, tests, or direct branch inspection. |
| Journal-reported | Recorded in progress journals or execution logs, not independently rebuilt here. |
| Design-only | Spec exists, no implementation yet. |
| Manual-pending | Requires a human with a real server or VS Code session. |
| Decision-pending | Needs an explicit product or engineering owner decision. |

---

## 2. Current state by component

| Component | State | Confidence |
|---|---|---|
| STS2 service | v2 core is reported complete through hardening/review waves, with connect/query/cancel/dispose, journal/trace schema, capture policy, message verbatim plus line, and database on query complete. `sts2-v2.0.0-preview` tag still pending M7 human gate. | Journal-reported |
| SQL Data Plane client | Domain API and STS2 backend are in place with DTO containment, ordered lanes, fake backend, chaos knobs, and conformance tests. | Journal-reported |
| Query Studio | Custom editor, sync, execution, RowStore and spill, results/messages UI, database dropdown and `USE` tracking, metadata, completions, Replay Lab, run records, and SSMS-parity QoL are reported built. Execution plans are detected but not rendered as plan tabs. | Journal-reported |
| MetadataService | H0-H6 hydration, immutable generations, readiness/failure honesty, DDL sniff and digest poll, schema context, and provider adapter exist. Current blocker: not yet a shared multi-connection, multi-server, key-correct MetadataStore for OE v2. | Code/design mix |
| Native language service | Lexer, segmenter, sketch parser, overlay, binder v1, context classifier, native completions, router, setting, and STS v1 bridge are reported through B9. Diagnostics, hover/signature, semantic polish, scripting/definition, and default-flip audit remain. | Journal-reported |
| Completions and AI | Inline completions are ported to schema context in both editors; debug panel and replay matrix exist. | Journal-reported |
| Debug Console | Core pages, live/session history, waterfalls, Perf Test History, self-test, feature-capture framework, and providers are present. STS2 live source and some embedded pages remain gated. | Code/journal mix |
| Perftest | CLI, scenario harness, store/history/head-to-head, XEvents collector, self-test, contracts registry, and 110 tests are reported built. CI wiring and central store remain. | Journal-reported |
| Object Explorer v2 | Design pack only. No OE v2 code yet. This is the next large product workstream. | Design-only |
| Central observability | Design now ratified by companion doc unless Karl changes it: SQL Server central store first, CLI push, CI artifact wiring, then in-product upload and central provider. | Design-only |

---

## 3. Binding design decisions

These decisions shape all remaining work:

1. **Data Plane is the connection/query substrate for new features.** Feature code imports domain APIs, not STS2 wire DTOs. No `mssql.sts2.*` feature settings.
2. **STS v1 is a handoff or bridge, not a new-feature substrate.** Query Studio has no v1 fallback. Language service uses a lazy shadow v1 connection only for the bridge path. OE v2 can create v1 state only for explicit, measured legacy command handoff.
3. **Privacy is mechanical.** SQL text, row data, secrets, connection strings, tokens, and prompts do not enter diagnostics or central upload under default policy. Classification and canary tests are gates.
4. **Official and diagnostic data stay separate.** CI gates read official metric samples only. Diagnostic data explains regressions; it does not quietly become a gate input.
5. **Readiness honesty is mandatory.** Empty, failed, loading, partial, stale, permission-denied, and unsupported states are distinct.
6. **Metadata generations are immutable.** Pin once per request, completion, diagnostic pass, or tree expand. Do not mix catalog generations in one response.
7. **Contracts registry first.** New diagnostics, perf markers, central upload contracts, and shared vocabulary land in contracts, regenerate, then emit.
8. **Commit isolation.** Prefer trains: `core:`, `dp:`, `qs:`, `ls:`, `oe:`, `dc:`, `perf:`, `sts2:`. Do not splice a settings change, metadata substrate change, UI behavior change, and scripting engine into one heroic octopus commit.
9. **Files remain ground truth for perf and diagnostics.** Central rows are projections.
10. **Preview defaults move only with evidence.** Default flips require head-to-head data, privacy review, rollback path, and manual dogfood sign-off.

---

## 4. Dependency map

```text
STS2 M7 tag
  -> Debug Console live STS2 source
  -> stronger Data Plane confidence

MetadataStore v2
  -> OE v2 server/database tree
  -> OE-grade object details
  -> LS hover descriptions and scripting metadata
  -> metadata perf scenarios

Language service B10-B12
  -> native diagnostics, hover, signature help
  -> TypeScript scripting and go-to-definition
  -> OE v2 native Script-As route

Central observability C0-C1
  -> CI trend history
  -> central dashboards
  -> release dogfood evidence

Query Studio plan/grid decisions
  -> review UX confidence
  -> wide/blob perf maturity
```

Parallelizable work:

- STS2 M7 verification and tag.
- Central observability C0/C1 and CI artifact-minimal workflow.
- MetadataStore MD-0 to MD-2 foundation.
- Query Studio plan-tab spike.

Sequential dependencies:

- OE v2 meaningful tree requires MetadataStore key-correct multi-database acquisition and ServerCatalog.
- OE v2 native Script-As requires TypeScript scripting from LS B12 or guarded handoff.
- Debug Console live STS2 source should wait for the STS2 observer/export contracts and preview tag.
- Central in-product upload should wait for upload policy contracts and a streaming session-segment reader.

---

## 5. Workstream inventory

### 5.1 STS2 service layer

| ID | Pri | Item | Detail | Acceptance gate |
|---|---:|---|---|---|
| STS2-1 | P0 | M7 preview close-out | Full verification, mutation ratchet, simulator run, docs pass, human review, preview tag. | `sts2-v2.0.0-preview` tag with evidence bundle. |
| STS2-2 | P1 | Effective capture-mode echo | Service reports host-bounded effective capture so client run records do not rely on local intent only. | Client can display requested versus effective capture mode. |
| STS2-3 | P1 | `maxCellBytes` honored on the wire | Service truncates or wraps oversized cells with honesty flags, rather than relying on QS display clamp. | Wide/blob query scenario shows bounded payload and correct truncation metadata. |
| STS2-4 | P2 | Envelope to OTLP adapter | Future adapter after observer contracts settle. | Not scheduled until central store and STS2 live source mature. |
| STS2-5 | P2 | Diagnostics health polling and envelope sink loopback | Needed for richer live source and health dashboards later. | Explicit consumer identified. |

Do not schedule reserved envelope kinds merely because they are reserved. Reserved means “do not break the shape,” not “emit now.”

### 5.2 SQL Data Plane client

| ID | Pri | Item | Detail | Acceptance gate |
|---|---:|---|---|---|
| DP-1 | P0-for-OE | Metadata session helper hardening | Data Plane sessions must support OE/MetadataStore acquisition patterns, background metadata query priority, cancel/dispose, and failure surfacing. | MetadataStore can open server and database sessions through a stable helper without feature code seeing wire DTOs. |
| DP-2 | P1 | Batched central upload helpers | In-product central upload may need bounded JSON or TVP-like insert helpers. | 100k event session upload remains bounded and policy-safe. |
| DP-3 | P1 | Central read source connection profile | Debug Console central provider uses saved profiles without storing raw strings. | Central source can connect/read through Data Plane. |

### 5.3 MetadataService to MetadataStore

This is the main substrate effort for OE v2 and a useful cleanup for Query Studio and language service.

| ID | Pri | Item | Detail | Acceptance gate |
|---|---:|---|---|---|
| MD-0 | P0 | Shared contracts and store shell | `IMetadataStore`, keys, leases, status model, invalidation bus, test fixtures. | Query Studio can still use existing metadata through compatibility adapter. |
| MD-1 | P0 | Key-correct multi-database acquisition | Fix current risk where one cached current-database session can hydrate the wrong database. | Database A and B with different schemas never cross-contaminate. |
| MD-2 | P0 | ServerCatalog or `ServerMetadataService` | Visible databases and server facts as first-class metadata, not a Query Studio combo-box helper. | OE v2 can list databases without classic OE. |
| MD-3 | P0 | Shared leases and migration | QS and LS acquire metadata from shared store without behavior change. | Existing QS and LS tests pass with store path. |
| MD-4 | P1 | OE-grade object details | PK/unique constraint names, reverse FK pairs, indexes, defaults/checks, module definition state, identity seed/increment, real `listObjects`. | OE v2 can render tables, columns, keys, FKs, procedures, functions without empty-prefix hacks. |
| MD-5 | P1 | H7 descriptions | `MS_Description` for hover/OE properties, policy-reviewed. | LS hover and OE properties can show descriptions under policy. |
| MD-6 | P1 | Metadata perf scenarios | `hydrate-cold/warm`, `context-build`, `listObjects.10k`, `getColumns.150k`. | Perf history can track metadata regressions. |
| MD-7 | P2 | Disk cache | Manifest plus catalog cache once LS/OE cold-start data justifies it. | Cold-start data shows it matters. |
| MD-8 | P2 | Deep digest and delta refresh | Scoped delta, 30 percent rule, metadata-lite mode. | Real drift-scale problem or large-catalog evidence. |
| MD-9 | P2 | H8 row counts | Only if OE or hover needs row counts. | Product decision to display row counts. |

### 5.4 Object Explorer v2

| ID | Pri | Item | Detail | Acceptance gate |
|---|---:|---|---|---|
| OE2-0 | P0 | Activation shell and setting | `mssql.objectExplorer.viewMode`, preview view, status node, no-v1 tripwire. | View opens with no v1 connection on activation. |
| OE2-1 | P0 | Data-plane connection registry | Connect/disconnect through SQL Data Plane, no `ConnectionManager.connect` for browse. | Saved profile connects, tree shows server, no classic OE RPCs. |
| OE2-2 | P0 | Server catalog | Databases folder and database nodes from ServerCatalog. | Server expands to databases without STS v1 OE. |
| OE2-3 | P0 | Database metadata tree | Tables/views/procs/functions/synonyms/schemas and first child details. | Multi-database catalog isolation test passes. |
| OE2-4 | P1 | Native basic commands | refresh, filter, search, copy names, Query Studio new query, select top/table preview. | Basic workflows need no v1. |
| OE2-5 | P1 | Explicit legacy handoff | Guarded handoff service for unmigrated commands. | Browse/refresh never triggers handoff; selected command does. |
| OE2-6 | P1 | Native scripting migration | Route Script-As through LS B12 where supported. | Hand-off count drops for table/view/proc/function scripting. |
| OE2-7 | P1 | Perf and privacy gates | perftest probes, no-v1-browse tests, canaries. | Preview readiness evidence. |
| OE2-8 | P2 | Advanced SMO parity | server security, SQL Agent, management nodes, advanced object properties. | Backlog, driven by user demand. |

Classic metadata-backend work is useful only as fixture capture and compatibility scaffolding unless the team decides to fund it separately. Do OE fixture capture because it de-risks node compatibility. Do not force the old `TreeNodeInfo` model to become OE v2 wearing a trench coat.

### 5.5 Native language service

| ID | Pri | Item | Detail | Acceptance gate |
|---|---:|---|---|---|
| LS-10 | P0 | Native diagnostics | T1 lexical/structural and T2 binder diagnostics with suppression ladder and sliced scheduler. | Honesty suite has zero false positives on covered suppressions. |
| LS-11 | P0 | Hover and signature help | Hovers over binder plus descriptions, builtin signatures, parameter help. | Fixture suite proves hover/signature coverage. |
| LS-12 | P0 | Scripting and definition | `src/sqlScripting/**`, CREATE/ALTER emitters, definition/peek routing. | Go-to-definition on object and column lands at correct anchor. |
| LS-13 | P1 | Semantic polish | semantic tokens, highlights, code actions, feature-capture instantiation. | Head-to-head UX and performance evidence. |
| LS-14 | P1 | Audit and default-flip decision | Larger fourslash corpus, bridge-vs-native comparison, classic-editor preview decision, shadow-v1 deprecation plan. | Default flip has rollback and evidence. |
| LS-15 | P2 | Completion residuals | MRU accept-history, lazy docs, system proc catalog, keyword casing. | Polish after diagnostics and scripting. |
| LS-16 | P2 | Splitter convergence | Execution splitter and metadata sniffer move to full lexer after stability. | Corpus differential green. |
| LS-open | Open | Dogfood worksheet | aggregation pollution, shadow status-bar side effects, backing-doc lifetime, CS_AS seed DB. | Live dogfood notes resolved. |

### 5.6 Query Studio

| ID | Pri | Item | Detail | Acceptance gate |
|---|---:|---|---|---|
| QS-1 | P0 | Plan tab rendering | Show execution plans as plan tabs, not flagged grid rows. | Classic visible parity gap closed. |
| QS-2 | P1 | Grid convergence decision | Decide custom virtualized table versus Fluent/slickgrid path before public preview. | Decision recorded with perf and maintenance rationale. |
| QS-3 | P1 | Wide/blob scenarios | Add wide columns and blob/XML perf tests, tied to STS2 `maxCellBytes`. | Perf gates produce useful data. |
| QS-4 | P1 | Per-cell context menu and Ctrl+R audit | Small parity and keybinding polish. | Manual UX check passed. |
| QS-5 | P1 | Untitled/Save-As test | Custom editor save behavior proven. | Manual or automated exploratory test recorded. |
| QS-6 | P2 | SQLCMD mode and results-to-file | Explicit v1 non-goals, keep toolbar extensible. | Product decision later. |
| QS-7 | P2 | Spill frame format revisit | JSON v1 until measurement demands binary/columnar. | Measurement-driven only. |
| QS-8 | P2 | Classic resolver LRU eviction | Evict schema-context resolver cache on connection changes. | Small cleanup, not substrate blocker. |

### 5.7 Debug Console

| ID | Pri | Item | Detail | Acceptance gate |
|---|---:|---|---|---|
| DC-1 | P0-post-STS2 | Live STS2 source | Envelope source in Debug Console after STS2 preview tag and observer contract stability. | Live source works without polluting viewer traces. |
| DC-2 | P1 | Central upload UI | Upload sessions and imported runs to central store after C0/C1. | Upload preview is policy-accurate and bounded. |
| DC-3 | P1 | Central Perf History source | SQL-backed central source provider after central schema exists. | Queries are paged, permission-aware, and policy-safe. |
| DC-4 | P1 | Shipping surface decisions | Decide internal/support/experimental pages, capture-policy UX, owner calls. | Release checklist closes §24 decisions. |
| DC-5 | P1 | Completions and Replay Lab embedding | Dedicated panels exist; left-rail pages remain gated. | UX decision and implementation. |
| DC-6 | P2 | Investigation workbench | Dedicated compare waterfall and workbench page. | Useful after central history and more runs exist. |
| DC-7 | P2 | SQLite source strategy | Native driver, worker, WASM, or keep-directory decision. | Defer because central source may make it less important. |
| DC-8 | P2 | Self-test polish | Config-file selection, connection picker, soak exposure, labels, export, charts. | Polish backlog. |

### 5.8 Perftest and observability

| ID | Pri | Item | Detail | Acceptance gate |
|---|---:|---|---|---|
| PERF-1 | P1 | XEvents recipe wiring and calibration | Collector exists. Wire one-flag SQL diagnostic recipe and calibrate before any promotion beyond diagnostic/calibration. | SQL Activity tab and metrics have calibrated trust labels. |
| PERF-2 | P1 | Central observability C0/C1 | SQL Server schema plus `perftest push` Tier 1. | Central official-only view matches local fixtures. |
| PERF-3 | P1 | CI artifact-minimal workflow | Run gates on pinned agent, upload artifacts, job summary, optional central push. | CI gate independent of central upload success. |
| PERF-4 | P1 | CI/fleet ladder | Nightlies, rolling trends, per-tier gates, invalid-rep ledger, signed run manifests. | Operating model documented and automated. |
| PERF-5 | P1 | QS baseline maturity | Accrue multi-rep history for `querystudio-query-10k` and review gate maturity. | Standing gate review completed. |
| PERF-6 | P2 | Heap snapshot soak attribution | Collectors exist, recipe and attribution later. | Needed by a real investigation. |
| PERF-7 | P2 | MCP first request scenario | Wait for MCP surface stability. | Surface stable. |
| PERF-8 | P2 | SQL Database Projects instrumentation | Separate extension. | Product owner asks and scope is defined. |

### 5.9 Central observability

Tracked in `options_for_central_tracing.md`; summarized here for sequencing.

| ID | Pri | Item | Detail | Acceptance gate |
|---|---:|---|---|---|
| C0 | P1 | Contract and schema freeze | SQL Server DDL, migrations, upload preview contracts, upload policy vocabulary. | Fresh DB creates, fixtures pass, official view parity. |
| C1 | P1 | CLI `perftest push` Tier 1 | Run/env/scenario/rep/metric/validation/artifact refs. | Idempotent re-push and privacy canaries. |
| C1-prime | P1 | CI publish | Artifact upload plus central push after local gate. | Gate not dependent on central upload. |
| C2 | P1 | In-product upload | Debug Console upload preview and writer through Data Plane. | Bounded 100k event upload, exact policy preview. |
| C3 | P1 | Central Perf History provider | SQL-backed source in Debug Console. | Paged queries and distinct empty/error/permission states. |
| C4 | P2 | Grafana dashboards | SQL views and dashboard JSON. | Useful panels without custom ingestion. |
| C5 | P2 | Marker and SQL activity detail | Tier 2 rows and retention jobs. | Diagnostic tables remain policy-safe. |
| C6 | P2 | Support bundles and artifact refs | Bundle manifests, central refs, purge. | Support workflow ratified. |
| C7 | P2 | Bencher and OTLP projections | Projection only, not canonical store. | Central store stable. |

---

## 6. Recommended build sequence

### Slice A: Foundations that can run now

1. **STS2 M7 preview tag**: verification and human gate. This is not feature work, but it unlocks Debug Console live STS2 work and builds confidence in Data Plane consumers.
2. **Central observability C0/C1**: schema plus CLI push. This can run alongside product feature work and immediately gives CI/fleet history a home.
3. **CI artifact-minimal workflow**: run perftest gates, upload artifacts, then central push when configured. Even without central credentials, this improves release evidence.

### Slice B: MetadataStore before OE v2

1. Build MD-0 through MD-3.
2. Migrate Query Studio and LS onto the shared store without visible behavior change.
3. Add ServerCatalog and multi-database isolation tests.
4. Add metadata perf scenarios once realistic fixtures exist.

### Slice C: OE v2 preview path

1. OE2-0 through OE2-3 for browse-only preview.
2. OE2-4 native basic commands.
3. OE2-5 handoff service for unmigrated commands.
4. Wire perftest probes and no-v1-browse tests.

### Slice D: Language service value tier

1. LS-10 diagnostics.
2. LS-11 hover/signature.
3. LS-12 scripting and definition.
4. Feed OE v2 native scripting from LS-12.

### Slice E: Review-readiness pass

1. QS plan tabs.
2. Grid convergence decision.
3. Debug Console shipping-surface decisions.
4. Manual validation ledger burn-down.
5. Ratify or close the remaining decisions to freeze.

### Slice F: Observability expansion

1. In-product central upload C2.
2. Central Perf History provider C3.
3. Grafana dashboards C4.
4. XEvents recipe/calibration PERF-1.
5. Bencher/OTLP only if the team still wants them after SQL dashboards exist.

---

## 7. Decisions to freeze

| ID | Decision | Recommendation | Owner signal needed | Cost of delay |
|---|---|---|---|---|
| D-freeze-1 | Central schema ownership | `perf-contracts` owns local SQLite and SQL Server schemas. | Ratify in central doc. | Schema drift and duplicate contracts. |
| D-freeze-2 | Telemetry boundary | Central upload is opt-in engineering/support data, not product telemetry. | Product/privacy owner. | Confusing policy and review risk. |
| D-freeze-3 | Upload policy UX | Named upload policies with preview and canaries. | Debug Console/product owner. | Unsafe or unusable upload flow. |
| D-freeze-4 | CI baseline ownership | CI owns fleet baselines; dev uploads cannot silently move them. | Engineering owner. | Noisy or untrusted gates. |
| D-freeze-5 | Bundle format and signatures | Support bundle manifest plus hashes, heavy artifacts by ref. | Support/privacy owner. | Support workflow reinvents exports. |
| D-freeze-6 | STS2 viewer-timing readiness | Wait for preview tag and observer checkpoint contract before live source. | STS2/DC owners. | Fossilized viewer interface. |
| D-freeze-7 | SQLite strategy | Keep directory provider and add central provider before fighting native SQLite. | Debug Console owner. | Time spent on ABI problem with lower payoff. |
| D-freeze-8 | Scenario maturity ownership | Define who promotes exploratory scenarios to official gates. | Perf owner. | Young gates become folklore. |
| D-freeze-9 | Support-bundle workflow | Decide local export versus central upload handoff. | Support owner. | Fragmented incident workflows. |
| D-freeze-10 | OE v2 default path | New view first, classic backend only as fixture/compat path unless funded. | Product owner. | Two half-modern Object Explorers. |

---

## 8. Work not worth scheduling standalone yet

| Item | Why not now |
|---|---|
| Metadata disk cache | Wait for LS/OE cold-start measurements. |
| Deep digest tiers and scoped deltas | Current cheap sniff/digest is enough until drift-scale data says otherwise. |
| SQLite Perf History provider | Central source may solve the useful queryability problem without native ABI work. |
| Spill frame binary format | JSON frames are acceptable until measurement says otherwise. |
| Reserved STS2 envelope kinds | Reserved by design. Do not emit them just to fill a table. |
| Full SMO OE parity | OE v2 should ship useful core browsing first, then expand by demand. |
| Bencher and OTLP | Projection layers after SQL central store is working. |

---

## 9. Manual validation ledger

These require a human with a live server or a realistic VS Code dogfood session.

| ID | Validation | Owner context | Exit |
|---|---|---|---|
| MV-1 | Typed `USE` dropdown/status follow-through | Query Studio | Status and editor context track typed `USE` correctly. |
| MV-2 | TRAN badge and disconnect guard feel | Query Studio | UX is understandable and not noisy. |
| MV-3 | Filter/sort widget on real data | Query Studio grid | Interactions feel stable on realistic result sets. |
| MV-4 | Grid styling, XML/JSON links, NULL display | Query Studio grid | Visual parity and navigation check. |
| MV-5 | 30-minute resync-count-zero dogfood | Query Studio sync | No backing-document drift. |
| MV-6 | Native completions live dogfood | Language service | Useful suggestions, no distracting regressions. |
| MV-7 | LS worksheet items | Language service bridge/native | Aggregation pollution, status-bar side effects, backing-doc close lifetime observed. |
| MV-8 | SqlLogin credential-seeding path in perftest | Perftest | Non-integrated auth works in test setup. |
| MV-9 | CS_AS collation seed database | Language service/metadata | Case-sensitive resolution gates possible. |
| MV-10 | Plan tab rendering UX | Query Studio | Plans render in the expected tab and do not disrupt grids. |
| MV-11 | OE v2 no-v1 browse smoke | OE v2 | Connect, expand, refresh, filter show no classic OE traffic. |
| MV-12 | Central upload preview | Debug Console | User can understand what leaves the machine before upload. |

A structured dogfood week after OE v2 browse preview and LS diagnostics exists can burn down most of these in one pass.

---

## 10. Release-readiness checklist

Before a broad preview announcement:

- STS2 preview tag exists with evidence.
- Query Studio plan tabs either work or are explicitly scoped out with a visible fallback.
- Grid convergence decision is recorded.
- MetadataStore supports key-correct multi-database catalogs.
- OE v2 browse preview has no-v1-browse tests.
- Native language service diagnostics/hover/scripting have honesty and performance gates.
- Central observability C0/C1 exists or CI artifact-minimal is wired as the interim evidence path.
- Debug Console shipping surface is decided.
- Privacy canaries run for diagnostics, central upload, feature capture, and OE v2 telemetry.
- Manual validation ledger has owner notes and dispositions.
- Default flips have rollback settings and support notes.

---

## 11. Coding-agent handoff format

When handing any item to a coding agent, include:

```text
Task ID:
Target branch:
Commit train label:
Files likely touched:
Design docs to read:
Current code truth:
Dependencies:
Non-goals:
Acceptance gates:
Tests to run:
Manual validation required:
Privacy canaries:
```

Example:

```text
Task ID: C1
Target branch: dev/query
Commit train label: perf:
Files likely touched:
  packages/perf-contracts/sql/**
  packages/perftest-cli/src/central/**
  packages/perftest-cli/src/commands/push.ts
Design docs to read:
  options_for_central_tracing.md
Dependencies:
  C0 schema
Non-goals:
  in-product upload, Grafana, Bencher, OTLP
Acceptance:
  push one fixture run, re-push idempotently, official view parity, privacy canaries
```

---

## 12. One-page recommendation

Fund these now:

1. STS2 M7 verification and preview tag.
2. Central observability C0/C1 plus CI artifact-minimal workflow.
3. MetadataStore MD-0 through MD-3.
4. OE v2 OE2-0 through OE2-3 after MetadataStore foundations.
5. Language service LS-10 through LS-12.
6. Query Studio plan tab rendering and grid convergence decision.

Defer these until evidence or product demand says otherwise:

- metadata disk cache;
- deep digest tiers;
- native SQLite Perf History provider;
- OTLP and Bencher;
- advanced OE SMO parity;
- binary spill frames.

The strategic spine is simple: stabilize the substrates first, then let the UI features perch on them. Anything else invites a hydra, and hydras make terrible release managers.
