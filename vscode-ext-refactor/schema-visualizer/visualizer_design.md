# Schema Visualizer — Design

Read-only Schema Designer on the metadata substrate (STS v2 data plane), with commit handoff to the legacy v1 DacFx path.

- Status: PROPOSED (design for review — no code yet)
- Date: 2026-07-13
- Repos/branches: `vscode-mssql`, `sqltoolsservice`, `perftest` — all `dev/query`; notes on `main`
- Commit prefixes (proposed): `sv:` feature code · `qs:` metadata-substrate extensions (precedent: CACHE build) · `core:` shared/legacy touches (instrumentation in the existing designer, contracts, shared component extraction)
- Normative refs (precedence order; later docs win only where explicitly noted):
  1. This doc
  2. `oe-docs/metadata_service_oe_v2_design.md` (§5 store API, §9 object-details roadmap, §12 provider adapters) — the consumption pattern this design copies
  3. `metadata-docs/metadata-substrate-design.md` (as-built catalog truth @ `59e78a296`)
  4. `sts_refactor_docs/sts2/SPEC.md` (STS2 contract — schema tools are explicitly out of scope for STS2, §1.2)
  5. `alt-endpoints/_build/PROGRESS.md` entries 10–11 (data-plane state, Debug Console page pattern, live-lane env vars)

---

## 1. Problem

The Schema Designer is one of the last major surfaces still bound end-to-end to legacy STS v1. Opening it triggers a full DacFx `TSqlModel` load of the database (`sts.dacfx.schemaDesigner.createSession` — flagged in `SchemaDesignerService.cs:51-55` as "the expensive part"), holds a server-side session for the lifetime of the editor, and every read (model, definition script) round-trips v1.

Meanwhile the `dev/query` refactor has built a schema-truth substrate that already contains nearly everything the designer's read paths need:

- **MetadataStore** (`vscode-mssql/extensions/mssql/src/services/metadata/`) — per-database immutable `CatalogSnapshot`s hydrated from `sys.*` over the SQL Data Plane (`v2/query.execute`), with drift detection, freshness policies, and an optional disk cache (`mssql.metadataCache.enabled`). Full hydration of a 10k-object catalog measures **148 ms** (unit lane); warm disk acquire ~9 ms.
- Query Studio, OE v2, completions, and the AI context builder already consume it. `ssms-query-docs/02-metadata-service-design.reviewed.md:5` names "Table Designer / Schema Visualizer bootstrap" as an intended future consumer.

**Goal:** a schema visualizer whose *read* paths (diagram, table properties, definition scripts) run entirely on the metadata substrate — no v1 traffic, no DacFx model load, instant-open on warm cache — while *applying* changes stays on the proven v1 DacFx pipeline (`schemaDesigner/getReport` → `publishSession`). Edits are allowed in the new surface; commit is a deliberate, command-scoped handoff to v1.

**Non-goals (this effort):**
- Replacing the DacFx publish pipeline. `02-metadata-service-design.reviewed.md` §1.1 is explicit: "MetadataService may bootstrap designers, not publish from its snapshot." DacFx remains authoritative for diff/report/apply.
- A server-side STS2 metadata endpoint. STS2 v2.0 is connectivity + query + diagnostics only (SPEC §1.2); all schema reads derive from catalog SQL through `v2/query.execute`. This design does **not** add C# endpoints.
- Regressing or restructuring the existing Schema Designer. It keeps working unchanged on v1 (additive instrumentation only, §6.4).
- DAB (Data API Builder) in the first prototype (§5.6 — it is already isolated and can ride along later).

---

## 2. Existing code survey

### 2.1 Extension side (vscode-mssql, `extensions/mssql/`)

| Piece | Where | Notes |
|---|---|---|
| Commands | `src/controllers/mainController.ts` ~2305/~2324/~2346 | `mssql.schemaDesigner` (editable), `cmdDesignSchemaForTable` (**read-only already exists** — Table Explorer "View Table Diagram" passes `isReadOnly=true`), `mssql.buildDataApi` (DAB view) |
| Session manager | `src/schemaDesigner/schemaDesignerWebviewManager.ts` | Cache key `${connString}-${db}-${ro|rw}`; builds classic connection string via `ConnectionManager`; disposes v1 session on close |
| Controller | `src/schemaDesigner/schemaDesignerWebviewController.ts` | `WebviewPanelController<SchemaDesignerWebviewState, SchemaDesignerReducers>`, view id `"schemaDesigner"`; `initializeSchemaDesignerSession()` → v1 `createSession`; publish/report/definition handlers; DAB handlers ~472–626 |
| Webview page | `src/webviews/pages/SchemaDesigner/` | React Flow v12 (`@xyflow/react`); `graph/SchemaDiagramFlow.tsx`, `graph/schemaDesignerTableNode.tsx` (PK/FK icons, type text, collapse >10 cols, diff highlighting, **read-only gating via `state.isReadOnly`**); toolbar (publish, export image, definitions, filter, auto-arrange, undo/redo); editor drawer (RW only) |
| Model adapters | `src/webviews/pages/SchemaDesigner/model/` | **The only coupling point to the v1 contract**: `schemaToFlowState.ts` (`buildFlowComponentsFromSchema`) and `schemaFromFlowState.ts` (`buildSchemaFromFlowState`) convert `SchemaDesigner.Schema` ⇄ React Flow nodes/edges. Plus mutations, layout (`flowLayout.ts`), utils |
| Webview↔host RPC | `src/sharedInterfaces/schemaDesigner.ts` | `initializeSchemaDesigner`, `getDefinition`, `getReport`, `publishSession`, `getSchemaState`, `applyEdits`, notifications (`schemaDesigner/progress`, `/message`), types `Schema/Table/Column/ForeignKey` |
| STS client | `src/services/schemaDesignerService.ts` + `src/models/contracts/schemaDesigner.ts` | v1 JSON-RPC: `schemaDesigner/createSession`, `/disposeSession`, `/generateScript`, `/getDefinition`, `/getReport`, `/publishSession` |
| DAB | `src/webviews/pages/SchemaDesigner/dab/` + `src/services/dabService.ts` + `src/dab/` | Config-file builder + Docker deploy. **Zero STS calls** — consumes the in-webview `Schema` only. Cleanly separable |

Key coupling fact: the webview holds authoritative state in the React Flow graph; the v1 `Schema` shape appears only at the two adapter files and the RPC boundary. Feed it a `Schema` from any source and the entire diagram/toolbar/definitions UI works.

### 2.2 STS side (sqltoolsservice, v1)

- `src/Microsoft.SqlTools.ServiceLayer/SchemaDesigner/SchemaDesignerService.cs` — handlers; server-side session dictionary.
- `SchemaDesignerSession.cs` — wraps DacFx DesignServices `SchemaDesigner`; `createInitialSchema()` = full in-memory model load; column projection carries the full detail set (`DataType, MaxLength, Precision, Scale, IsNullable, IsPrimaryKey, IsIdentity, IdentitySeed, IdentityIncrement, DefaultValue, IsComputed, ComputedFormula, ComputedPersisted`); FK projection carries `OnDeleteAction/OnUpdateAction`.
- `SchemaDesignerUpdater.cs` — DacFx diff: `GenerateUpdateScripts(_initialSchema, updatedSchema, schemaDesigner)` → report + scripts. **Correlates tables/columns by the ids assigned at `createSession`** — load-bearing for the commit handoff design (§5.4).
- `SchemaDesignerScriptGenerator.cs` (`SchemaCreationScriptGenerator`) — **pure string-builder** CREATE TABLE + ALTER TABLE ADD CONSTRAINT generation, no DacFx. Used by `getDefinition`. Trivially portable to TS (§5.5).
- On the legacy seam allowlist (`sts_refactor_docs/sts2/LEGACY-SEAM-ALLOWLIST.txt:33`); STS2 explicitly excludes schema tools.

### 2.3 Metadata substrate (what the read paths run on)

Consumer API: `MetadataStoreService.get().store().acquireDatabase(prepared, database, onStatus)` → `DatabaseCatalogLease` → `.ensureFresh(policy)` / `.current(): CatalogSnapshot` / `.onDidChange` / `.dispose()`. OE v2's `OeV2MetadataCoordinator` (`src/objectExplorer/v2/metadata/oeV2MetadataCoordinator.ts`) is the template.

Coverage vs what the visualizer needs (hydration passes H0–H7, `metadataService.ts`):

| Need | Catalog today | Source |
|---|---|---|
| Tables/views + schema | ✅ `listObjects`, `getObject` | H2 `sys.objects` |
| Columns: name, nullable, identity/computed flags | ✅ `getColumns` → `ColumnInfo` | H3 `sys.columns ⋈ sys.types` |
| Column type display (`nvarchar(50)`, `decimal(18,2)`) | ✅ `typeDisplay` string | H3 |
| Column **raw** maxLength/precision/scale (discrete fields) | ❌ folded into `typeDisplay`, not retained | gap → SV-1 |
| PK membership + PK/UNIQUE constraint names | ✅ `getPrimaryKeyColumns`, `getKeyConstraints` | H4 |
| FK edges + ordered column pairs, both directions | ✅ `getForeignKeyDetailsFrom/To` | H5 + H5B |
| FK **on-delete / on-update actions** | ❌ not queried | gap → SV-1 |
| Column DEFAULT values | ❌ | gap → SV-1 |
| Identity **seed/increment** | ❌ flag only | gap → SV-1 |
| Computed column **formula/persisted** | ❌ flag only | gap → SV-1 |
| MS_Description tooltips (object + column) | ✅ `getDescription` | H7 — a bonus v1's designer doesn't surface |
| Data types list / schema names (edit dropdowns) | ⚠️ `listSchemas` ✅; distinct type list needs a small aux query | gap → SV-1 (edit only) |
| Indexes, check constraints, row counts | ❌ declared-but-not-hydrated sections | **not needed for v1 parity** (the v1 SD contract doesn't model indexes/checks either); optional later |

These gaps are exactly the `oe-docs/metadata_service_oe_v2_design.md` **§9.1 roadmap items** — this effort funds them.

Diagram + basic properties are fully serviceable **today**; only the full properties/edit drawer parity needs SV-1.

### 2.4 Program patterns this design must follow

- **Net-new, config-gated coexistence** (OE v2, Query Studio): separate registration, default-off flag, classic surface byte-untouched, banned-imports lint + **no-v1 tripwire** (sinon spies on `SqlToolsServiceClient.prototype.sendRequest` asserted `notCalled` during browse).
- **Command-scoped legacy handoff** (`oe-docs/oe_view_design.md` §34): v1 state may be created only on explicit user command — never as a browse fallback. Schema Designer is already listed there as an H2/H3 handoff target.
- **Contracts-first observability**: markers registered in `perftest/packages/observability-contracts/src/registry/event-types.json` + re-vendored before first emission (parity/vendorSync tests enforce).
- **Diag observer on the activation side** if any lazy chunk is involved (entry 11 lesson: lazy bundles get their own dead `diag` singleton).
- Unopened cost ≈ 0; bundle-budget denylist test guards heavy libs out of eagerly-loaded chunks.

---

## 3. Recommendation

**Build a net-new Schema Visualizer surface (new command, new controller, new webview entry point) that *imports* the existing SchemaDesigner webview's pure graph/model components, reads from MetadataStore leases, and hands off to v1 only inside the explicit Publish flow. Leave the existing Schema Designer untouched except additive diag instrumentation. Ship without DAB in P0.**

Why this and not the two alternatives:

1. **Rejected: retrofit the shared editor with a backend toggle.** The existing page's data flow (session init → `CreateSessionResponse` → flow state) would need branching at init, definition, report, and publish. Every branch is regression risk to a shipping feature, and mixed `core:`+feature commits violate the owner rule. The user constraint — "keep existing features pretty much unimpacted" — is best met by not touching the shipping code paths at all.
2. **Rejected: fully net-new UI from scratch (Query-Studio-style clean room).** Unnecessary duplication here: unlike the query editor (where the legacy grid was unsalvageable), the SchemaDesigner webview is modern (React Flow v12) and its STS coupling is confined to two adapter files. The graph node renderer, layout engine, filter, export-to-image, and definitions panel are directly reusable as imports. A clean-room rebuild would re-implement ~15 components to avoid touching zero of them.
3. **Chosen: net-new page, shared pure components.** `src/webviews/pages/SchemaVisualizer/index.tsx` imports `../SchemaDesigner/graph/*`, `../SchemaDesigner/model/schemaToFlowState.ts`, `flowLayout.ts`, etc. esbuild (`splitting: true`, ESM) automatically hoists shared modules into shared chunks — no duplication in `dist/views`, no edits to the SchemaDesigner page. If a shared component later *needs* a change, extract it to `src/webviews/shared/schemaGraph/` in a standalone `core:` commit first (the exact precedent of the B3 grid extraction: move shared pieces behind an interface, gate on the standing perf pair, then build on it).

The interface contract that makes reuse cheap: the visualizer's host side produces a **`SchemaDesigner.Schema`** (the existing shared-interface type) from a `CatalogSnapshot`. Everything downstream of that type — flow building, node rendering, layout — is already written.

---

## 4. Target architecture

```
                    ┌───────────────────────────── vscode-mssql (extension host) ─────────────────────────────┐
                    │                                                                                          │
 OE v2 node ──┐     │  SchemaVisualizerController (new)                                                        │
 cmd palette ─┼──►  │   ├─ read path:  MetadataStoreService.get().store().acquireDatabase(...)                 │
 Table Expl. ─┘     │   │      lease.ensureFresh(oeBrowse-like policy) → CatalogSnapshot                       │
                    │   │      catalogToSchema(snapshot) → SchemaDesigner.Schema  ──────────► webview          │
                    │   │                                                                                      │
                    │   ├─ definition:  TS port of SchemaCreationScriptGenerator (pure, client-side)           │
                    │   │                                                                                      │
                    │   └─ COMMIT (explicit user action only — command-scoped handoff):                        │
                    │        classic connection string (handoff service, OE v2 precedent)                      │
                    │        → v1 schemaDesigner/createSession  (DacFx model load, ids minted here)            │
                    │        → replay semantic edit ops onto v1 baseline (name-correlated)                     │
                    │        → v1 getReport (DacFx diff/report UI reused) → v1 publishSession                  │
                    │        → dispose v1 session; lease.refresh()                                             │
                    └──────────────────────────────────────────────────────────────────────────────────────────┘
                          │ MetadataService hydration (H0–H7 catalog SQL)
                          ▼
                SQL Data Plane (mssql.sqlDataPlane.backend: sts2-local | ts-native)
                          │ v2/query.execute on dedicated background session
                          ▼                                   ▲ only during Publish
                       SQL Server                    STS v1 (SchemaDesignerService → DacFx)
```

Central architectural fact (from the STS2 SPEC, deliberate): **there is no v2 metadata endpoint**. "Porting to STS v2" for schema reads means consuming the client-side MetadataStore, which hydrates over `v2/query.execute` on its own dedicated background session (`applicationName: "vscode-mssql-metadata"`). The visualizer must **never** run its own catalog SQL on the user's interactive session (one-active-query-per-connection rule) and must **not** invent a second truth source (`metadata_service_oe_v2_design.md` §12.2) — leases only.

---

## 5. Detailed design

### 5.1 Entry points, flags, registration

- Setting: **`mssql.schemaVisualizer.enabled`** (default `false`), requires `mssql.sqlDataPlane.enabled` (same gating chain as OE v2). No `mssql.sts2.*` settings — hard program rule.
- Command: `mssql.schemaVisualizer.open` ("Visualize Schema (Preview)"). Surfaced from: command palette; OE v2 database-node context menu (native v2 command via `oeV2CommandRegistry`); optionally Table Explorer later (parity with `cmdDesignSchemaForTable`, with initial table filter).
- New webview: entry `schemaVisualizer: "src/webviews/pages/SchemaVisualizer/index.tsx"` in `scripts/bundle-webviews.js`; controller `src/schemaVisualizer/schemaVisualizerController.ts` (new folder, mirrors `objectExplorer/v2` isolation), view id `"schemaVisualizer"`.
- Register/unregister on config flip without reload (OE v2 / QS precedent).
- Connection identity comes from the data-plane prepared profile (`profileAuthAdapter.prepareConnection` / `stableProfileId`) — not `ConnectionManager` — except inside the commit handoff (§5.4).

### 5.2 Read path: `catalogToSchema` adapter

New pure module `src/schemaVisualizer/catalogToSchema.ts` (vscode-free, unit-testable against catalog fixtures):

| `SchemaDesigner.Schema` field | Catalog source |
|---|---|
| `Table {id, name, schema}` | `listObjects(schema?, ["table"])` (+ views behind a toggle later); `id` = deterministic `sv:<generation>:<objectId>` |
| `Column {name, dataType, isNullable, isPrimaryKey, isIdentity, isComputed, maxLength/precision/scale, defaultValue, identitySeed/Increment, computedFormula/Persisted}` | `getColumns` + `getPrimaryKeyColumns`; discrete fields from SV-1 substrate extensions (until then: `typeDisplay` renders, discrete fields empty) |
| `ForeignKey {name, columnsIds, referencedTableId, referencedColumnsIds, onDeleteAction, onUpdateAction}` | `getForeignKeyDetailsFrom` (name + ordered column pairs); actions from SV-1 extension (until then default `NO_ACTION` display with an "unknown" affordance) |
| extras (not in v1) | `getDescription` → node/column tooltips; `getKeyConstraints` names in properties pane |

Honesty rules (non-negotiable, substrate invariants):
- **Empty ≠ failed.** A `failed` catalog section renders an error state in the diagram/panel — never an empty diagram. Snapshot `mode: partial` shows a degraded-banner (same pattern as OE v2 status-child honesty).
- **Pin once per render.** One `lease.current()` snapshot per webview push; generation rides the payload; `onDidChange` triggers an explicit "schema changed — refresh" toast rather than silently mutating the graph (drift episodes surface, not vanish).
- Freshness: open uses a `requireValidated`-class policy (OE v2's `oeBrowse` preset: 120s TTL, bounded wait, block-with-loading); manual refresh button → `lease.refresh()`.

### 5.3 Table properties pane (read-only)

Reuse the definitions-panel chrome; add a properties tab fed purely from the snapshot: columns grid (type, nullable, identity(seed, incr), default, computed), key constraints with real names (H4), FK list with column pairs and actions, MS_Description. Row counts and indexes stay out of scope (not in the v1 designer either); if ever wanted, they are new hydration sections gated honestly on `absent`.

### 5.4 Edits + commit handoff to v1 (the load-bearing design decision)

Edits happen locally against the flow state exactly as today (reusing `model/*Mutation.ts` + the editor drawer). The new part is **how a locally edited model becomes a v1 `getReport`/`publishSession` call**, given that `SchemaDesignerUpdater` correlates by the **ids minted at v1 `createSession`** — ids our metadata-built model does not have.

**Decision: keep a semantic edit-op log; replay it onto the v1 baseline at commit time.**

1. While editing, record semantic ops (`addTable`, `renameColumn`, `setType`, `addForeignKey`, …) — this also powers undo/redo (the existing designer already keeps an undo stack; ops formalize it).
2. On Publish: resolve a classic connection string via a handoff service (clone of `oeV2ClassicHandoffService` — profile→classic mapping is solved there) → v1 `createSession` (this is when the DacFx model loads; show progress via the existing `schemaDesigner/progress` events).
3. Correlate our baseline objects to the v1 baseline **by (schema, name)** — renames are unambiguous because they're explicit ops, applied against pre-rename names.
4. Replay ops onto the v1 baseline schema to produce `updatedSchema` carrying v1 ids (fresh ids for created objects) → `getReport` → show the existing DacFx report/diff UI (`DacReport`: `possibleDataLoss`, `requireTableRecreation`) → `publishSession` → dispose session → `lease.refresh()`.
5. **Drift guard:** before step 2, `ensureFresh(requireValidated)`; if the catalog generation moved since editing began, or step 3 fails to correlate (object vanished/renamed under us), stop and show the drift diff — the user re-bases. The DacFx report remains the authoritative last-line safety gate either way, because the v1 session reads the *actual* current DB.

Why not diff-final-vs-baseline instead of an op log: name-based diffing is ambiguous under rename (rename ≡ drop+add ⇒ data loss in the report). Ops make renames first-class. P0 is read-only, so none of this blocks the first milestone.

### 5.5 Definition scripts without v1

v1 `getDefinition` requires a server-side session. For the read-only definitions panel, port `SchemaCreationScriptGenerator` (pure string builder, no DacFx) to TS: `src/schemaVisualizer/schemaScriptGenerator.ts`, golden-tested against v1 output for a fixture schema (byte-parity suite, same style as the MD-4 goldens). Views/procs/functions can additionally use the lease's lazy `getModuleDefinition(objectId)` (`sys.sql_modules`) — something v1's designer can't show at all.

### 5.6 DAB

Finding: DAB never calls STS — `dabService.ts` + `src/dab/dabConfigFileBuilder.ts` build config files locally and drive Docker. Its only input is the in-webview `Schema`. Since the visualizer produces the same `Schema` type, DAB could ride along essentially free later. **P0 decision: exclude it** (keeps scope and the bundle lean); revisit as `SV-7` once read-only ships. No isolation work is needed to "keep v1 calls contained" because there are none.

### 5.7 What changes in the metadata substrate (SV-1, `qs:` commits)

All additive, per the SoA "existing array order is load-bearing" rule; cache codec (`metadataCacheCodec.ts`) + manifest schema version bump; fixture matcher-order care (`largeCatalogFixture.ts` substring matchers):

- H3 extension: retain raw `max_length/precision/scale`; join `sys.default_constraints` (default definitions), `sys.identity_columns` (seed/increment), `sys.computed_columns` (definition, is_persisted).
- H5 extension: `delete_referential_action`/`update_referential_action` → `FkEdge`/`FkDetail`.
- Small auxiliary: distinct data-type list (`sys.types`) + `listSchemas` for edit dropdowns (edit phase only; consider `auxiliaryCatalog.ts` as home).
- `catalogModel.ts`: extend `ColumnInfo`/`FkDetail` + builder + codec view; `metadataDeterminism`/codec round-trip tests updated.

These directly discharge `metadata_service_oe_v2_design.md` §9.1 — OE v2's object-details roadmap benefits for free.

---

## 6. Diagnostics, telemetry, Debug Console

### 6.1 Diag events (Debug Console) — contracts first

Register in `perftest/packages/observability-contracts/src/registry/event-types.json` **before first emission** (parity + vendorSync tests enforce), then re-vendor the generated TS. Family `mssql.schemaVisualizer.*`, `feature: "schemaVisualizer"`:

- `mssql.schemaVisualizer.open` (begin/end; attrs: `tableCount`, `fkCount`, `generation`, `cacheState: warm|cold|offline`) — the headline metric, deliberately parallel to the registered `mssql.schemaDesigner.init` so head-to-head phase mapping is trivial.
- `mssql.schemaVisualizer.ready` (instant; the perftest end-marker)
- `mssql.schemaVisualizer.layout` (begin/end), `.refresh`, `.drift.detected`
- `mssql.schemaVisualizer.commit.handoff` (begin/end; wraps createSession→report→publish; attrs: `opCount`, `correlated`, `reportDataLoss`) — spans the v1 leg
- Webview→host RPCs named `sv/<op>` (`sv/getModel`, `sv/refresh`, `sv/getDefinition`, `sv/publish`) get begin/end spans **for free** via `webviewBaseController.onRequest` auto-spanning.

Wiring notes: metadata hydration spans (`feature:"metadata"`) and STS-side `sts.dacfx.schemaDesigner.*` spans (via `stsDiagListener`) already exist — the visualizer's trace waterfall composes from them plus the new family; use `diag.bindEntityTrace` per visualizer session so the Consolidated Trace groups a whole open→render→publish episode. If any part of the page loads as a lazy chunk, build observers on the **activation side** and inject (entry 11 dead-singleton lesson).

### 6.2 Classic telemetry

New `TelemetryViews.SchemaVisualizer` + `sendActionEvent`/`startActivity` for Open, Refresh, Export, PublishHandoff (mirroring the existing SchemaDesigner actions) — the product-telemetry channel stays populated alongside diag.

### 6.3 Debug Console page

P0: nothing bespoke — emitted events appear in Consolidated Trace/waterfall automatically. P2 (optional): a "Schema Visualizer" section following the SQL Data Plane page pattern (`b476153b5`): `DcGetSchemaVisualizerStatusRequest` → pure vscode-free projection (`debugConsoleStatus.ts` style; unit-tested that no schema content/identifiers ride — only counts, states, safe codes), showing open sessions, lease/generation state, cache warmth, last drift episode, last handoff outcome.

### 6.4 Instrumenting the existing v1 designer (additive, `core:` commit)

Independent of the new surface (and useful for the A/B): add extension-side diag spans in `schemaDesignerWebviewController.ts` around `createSession`/`getDefinition`/`getReport`/`publishSession` (`feature:"schemaDesigner"`, types `mssql.schemaDesigner.createSession` etc. — register first). STS-side spans already exist; this closes the client half so both editors are comparable in the same waterfall. Zero behavior change; the shared editor keeps working on v1 untouched.

---

## 7. Testing

### 7.1 Unit (vscode-test, offline-first)

- `catalogToSchema` goldens: catalog fixture (reuse `largeCatalogFixture.ts` shapes) → `Schema` snapshot pins; determinism (two builds byte-identical); honesty matrix (failed `columns` section → error state, `mode: partial` → banner; **never** empty-diagram).
- Script generator byte-parity: TS `schemaScriptGenerator` vs recorded v1 `getDefinition` output for the fixture DB.
- Edit-op replay: ops × baseline → expected v1-id-bearing `updatedSchema`; rename correlation; conflict cases (target vanished → typed correlation failure, no publish).
- **No-v1 tripwire** (the OE v2 pattern verbatim): sinon spies on `SqlToolsServiceClient.prototype.sendRequest` + `ConnectionManager.prototype.connect` asserted `notCalled` across open/render/properties/definition/refresh; a companion test asserts the publish flow **does** call exactly `schemaDesigner/createSession→getReport→publishSession→disposeSession`.
- Bundle budget: extend the denylist test so `@xyflow/react` stays out of eagerly-loaded chunks; metafile assertion that the SchemaDesigner page's chunk graph is unchanged (proof of "existing feature unimpacted").
- Privacy: no table/column names in diag fields beyond counts (canary schema name scanned out of journals/exports).
- Suite hygiene: watch pass-*counts*, not just failure lines (CACHE Entry 3 lesson); 4 known pre-existing dev/query failures (sqlScripting strict-host, sqlLanguage sys catalog, OE v2 stableProfileId, CopilotChatEntry flake) — anything else is ours.

### 7.2 Live lanes (skip-not-fail when env unset)

- `STS2_SQLSERVER_SQLLOGIN_CONNSTRING` (local SQL 2025 — full harness): open visualizer against a seeded DB, assert model counts vs `INFORMATION_SCHEMA`, FK pairs vs `sys.foreign_key_columns`; publish handoff round-trip (add table → report → publish → catalog refresh shows it → drop).
- `STS2_AZURESQLSERVER_CONNSTRING` (Azure SQL auth): open + render lane (engineEdition 5 path).
- Manual smoke recipe: `mssql.sqlDataPlane.enabled=true`, backend `sts2-local` (then `ts-native` — reads must be backend-agnostic), `mssql.schemaVisualizer.enabled=true` → OE v2 → database → "Visualize Schema (Preview)".

### 7.3 Perftest (repo `perftest`, remember: **rebuild dist** before any run picks up scenario changes)

- New scenario `schema-visualizer-open` — clone of `schema-designer-open` (`packages/perftest-cli/src/scenarios/registry.ts:2502`), measure `scenario.start` → `waitForMarker mssql.schemaVisualizer.ready`, success = marker + `noErrors`; driver step: `command` + `waitForMarker` (no new step type needed initially; `designerOpen` exists if OE-tree-driven open is wanted). Config: clone `examples/config.designers.local.jsonc` (standard `PerfHarness` seed suffices — no new fixture).
- **Head-to-head v1 vs v2 (the headline):** `perftest head-to-head --baseline-scenario schema-designer-open --candidate-scenario schema-visualizer-open` with a phase map pairing `mssql.schemaDesigner.init` ↔ `mssql.schemaVisualizer.open`. This is the designer analog of the query engine's −24% result — expected to be dramatic on warm metadata cache (DacFx full model load vs ~9 ms warm acquire).
- Variants: `schema-visualizer-open-warm` (with `mssql.metadataCache.enabled=true`, pairs with the `metadatacache-warm-acquire` precedent); backend twin pair (sts2-local vs ts-native) via the `registerQueryStudio10kBackendVariant` factory pattern if read-path backend-sensitivity is ever in question.
- Maturity: start `exploratory`/`diagnostic`, `official:false`; promote after baseline history accrues. Standing gates (`query-10k-results` 4/4 etc.) must stay green — this build is additive; movement = regression.

---

## 8. Phased plan (proposed batch IDs — an EXECUTION_PLAN.md follows on ratification)

| ID | Scope | Gate |
|---|---|---|
| SV-0 | Ratify design; seed decision log; register `mssql.schemaVisualizer.*` + `mssql.schemaDesigner.*` client markers in observability-contracts + re-vendor; §6.4 instrumentation in existing designer (`core:`) | contracts/vendorSync/parity green; existing suites green |
| SV-1 | Metadata substrate extensions §5.7 (`qs:`) | codec round-trip + determinism + fixture suites; standing perf pairs unmoved |
| SV-2 | Read-only core: `catalogToSchema`, controller, webview page (imported graph components), command + OE v2 context entry, properties pane, flag (`sv:`) | no-v1 tripwire green; bundle budget green; honesty matrix green; live open lane |
| SV-3 | Diagnostics polish: entity-trace binding, privacy canaries, classic telemetry; Debug Console visibility verified in Consolidated Trace | privacy tests green |
| SV-4 | Definition panel: TS script generator + module definitions | byte-parity goldens |
| SV-5 | Edits + commit handoff: op log, handoff service, replay/correlation, report/publish reuse, drift guard | replay suite + live publish round-trip |
| SV-6 | Perftest: `schema-visualizer-open` (+warm variant), head-to-head vs `schema-designer-open` | scenario green, first A/B report archived |
| SV-7 | Decide DAB / Table-Explorer entry / Dc page follow-ups | — |

P0 (first demo) = SV-0..SV-2: read-only diagram + properties, zero v1 traffic, markers flowing.

## 9. Risks & open questions (decision-log seeds)

1. **Shared-component drift**: importing from `../SchemaDesigner` couples us to files owned by the legacy page. Mitigation: imports are pure/presentational only; first time a shared file needs modification, extract to `webviews/shared/schemaGraph/` in a `core:` commit (grid-extraction precedent). *Decision needed: pre-extract now vs extract-on-first-change (recommend the latter).*
2. **Replay correlation edge cases** (schema-qualified renames, FK-to-renamed-table ordering): bounded by making correlation failure a hard stop with a clear message; DacFx report remains the safety net.
3. **v1 ids in `Schema.id`**: some webview components may assume GUID-shaped ids — verify `sv:<gen>:<objectId>` ids flow through `schemaToFlowState`/node keys cleanly (SV-2 spike item).
4. **Views in the diagram**: v1 designer is tables-only; catalog has views cheaply. *Decision: tables-only for parity in P0, views behind a toggle later (recommend).*
5. **Commit prefix**: `sv:` proposed (new build family). *Confirm with Karl.*
6. **Where the visualizer opens from in classic OE** (not just OE v2): classic OE context menu addition would touch classic surface — defer; command palette covers it.

## 10. Reference index

- Existing designer: `extensions/mssql/src/schemaDesigner/*`, `src/webviews/pages/SchemaDesigner/*`, `src/sharedInterfaces/schemaDesigner.ts`, `src/services/schemaDesignerService.ts`, `src/models/contracts/schemaDesigner.ts`; STS `src/Microsoft.SqlTools.ServiceLayer/SchemaDesigner/*` (service, session, updater, script generator, contracts).
- Substrate: `extensions/mssql/src/services/metadata/*` (metadataService H0–H7, catalogModel, metadataStore/Service, cache/*); consumer template `src/objectExplorer/v2/*` (activation, metadata coordinator, legacy handoff, no-v1 tripwires).
- Data plane: `src/services/sqlDataPlane/*`, `src/services/sts2/wire/v2.ts` (`STS2_METHODS`); STS2 spec `notes/vscode-ext-refactor/sts_refactor_docs/sts2/SPEC.md`.
- Diag/Debug Console: `src/diagnostics/diagnosticsCore.ts` (+sinks), `src/controllers/debugConsoleWebviewController.ts`, `src/webviews/pages/DebugConsole/pagesSqlDataPlane.tsx` (page pattern), `perftest/packages/observability-contracts/src/registry/event-types.json`.
- Perftest: `packages/perftest-cli/src/scenarios/registry.ts` (`schema-designer-open` @2502, backend-variant factory @1031), `examples/config.designers.local.jsonc`, `src/regression/headToHead.ts`, docs `SCENARIO_AUTHORING.md`/`SQL_PROVISIONING.md`/`REGRESSION_MODEL.md`.
- Program docs: `oe-docs/metadata_service_oe_v2_design.md` (§9.1 gaps), `oe-docs/oe_view_design.md` §34 (handoff policy), `metadata-docs/metadata-substrate-design.md`, `ssms-query-docs/02-metadata-service-design.reviewed.md` (§1.1 non-goal, visualizer named as consumer), `alt-endpoints/_build/PROGRESS.md` entries 10–11.
