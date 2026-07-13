# Object Explorer v2 — Execution Plan

**Authored:** 2026-07-05, from the reviewed design pack (`oe_view_design.md` = the OE v2 view, **primary**; `metadata_service_oe_v2_design.md` = MetadataStore substrate, **hard precondition**; `oe_metadata_design.md` = classic-backend scaffolding, **deprioritized to fixture capture only**, per its own §1.3) + a full map of the classic OE implementation on `dev/query`.
**Branches:** `dev/query` in vscode-mssql, sqltoolsservice, perftest.
**Batch numbering** continues the global sequence (Query Studio B1–B7, language service B8–B14): **B15–B21**.
**Journal:** `oe-docs/PROGRESS.md` (one entry per batch, house format: SHIPPED / DEVIATIONS / VERIFIED / NEXT).

---

## 0. Mission

A new, optional Object Explorer view (`mssql.objectExplorer.viewMode: "v2Preview"`) whose connect, browse, expand, refresh, filter, search, and table preview run **entirely on the SQL Data Plane + a shared MetadataStore** — STS v1 only via explicit, measured legacy handoff. Classic OE stays the default and is untouched in behavior. Server/connection-group management is preserved (shared storage). Full unit + fake-data-plane + no-v1-spy tests, perftest scenarios, and Debug Console visibility.

## 1. House rules (carried from prior efforts — BINDING)

- **Commit isolation:** `core:` = contracts registry vocabulary + re-vendor + lint infra. `qs:` = `src/services/metadata/**`, `src/services/sqlDataPlane/**`, `src/queryStudio/**` (the store work rides the existing qs: train — metadata already lives there). **`oe:` (new)** = `src/objectExplorer/v2/**` + its tests + package.json OE-v2 contributions. Never mix trains in one commit.
- **Privacy:** no SQL text / rows / secrets / raw connection strings / raw endpoints / unclassified object names in diagnostics, ever, by default; passwords only inside `passwordProvider` closures; classification decides, settings request; privacy canaries per batch. Full-path strings never logged (path *kind* only).
- **Contracts-first:** register `objectExplorerV2.*` + `metadataStore.*` vocabulary in the perftest contracts registry, regenerate + re-vendor, BEFORE emitting (metadata.hydrate's B5 lesson).
- **No `mssql.sts2.*` settings.** Data-plane gates are `mssql.sqlDataPlane.enabled`/`.backend`.
- **Verification chain per batch:** tsgo (extension + webviews where touched) → `npm run build` (repo root, 0 error lines) → full `npx vscode-test` (known copilotChatEntry flake tolerated) → perftest gates `node packages/perftest-cli/dist/cli.js run --config examples/config.eval.local.jsonc` (16/16) → commits from repo root (pre-commit prettier/CRLF) → PROGRESS entry.
- **Readiness honesty:** failed/loading/permission-denied ≠ empty. Only `readyEmpty` renders a no-items child.
- **Import boundaries lint-enforced** (extend `eslint/custom-rules/banned-imports.js`): `objectExplorer/v2/tree/**` pure (no `vscode`, no `TreeNodeInfo`/`NodeInfo`, no data-plane singletons, no MetadataService concrete classes); `objectExplorer/v2/**` never imports STS2 wire DTOs or classic OE RPC contracts; `services/metadata/**` never imports `vscode.TreeItem`/OE tree classes; handoff imports (`ConnectionManager`) allowed ONLY in `objectExplorer/v2/legacy/**`.

## 2. Current-code anchors (verified 2026-07-05)

- Classic OE: `src/objectExplorer/objectExplorerService.ts` (session/expand RPCs, `_treeNodeToChildrenMap` cache, `_inFlightChildrenFetches` dedupe, loading-node trick), `objectExplorerProvider.ts`, nodes under `src/objectExplorer/nodes/`, filter dialog `objectExplorerFilter.ts`, DnD `objectExplorerDragAndDropController.ts`. Root nodes rebuilt each `getRootNodes()` from `ConnectionStore.readAllConnectionGroups()/readAllConnections()`; groups stored in VS Code settings via `ConnectionConfig` (`ROOT_GROUP_ID = "ROOT"`, full CRUD).
- View: `views.objectExplorer` id `objectExplorer` in container `objectExplorer` ("SQL Server"); menus keyed on `viewItem =~ /\btype=(...)\b/` regexes.
- Data plane: `src/services/sqlDataPlane/api.ts` — `OpenSessionParams { profile, database?, applicationName, auth?, requestedCapabilities? }`; `ExecuteOptions { commandKind, priority, tag, expectedDatabase, timeoutMs, maxCellBytes… }`; `ISqlSession.onDidChangeState/onDidChangeDatabase`; composition root `SqlDataPlaneService.get()`; test double `fakeBackend.ts`.
- Metadata: `src/services/metadata/metadataService.ts` — `CatalogKey { serverFingerprint, database }`, H0–H6 hydration, generations, DDL sniff + digest poll; **`MetadataSessionSource.open()` is key-blind** (the gap this plan fixes); `DataPlaneMetadataSessionSource` caches one session. Profile ref + `qsfp_` fingerprint + passwordProvider pattern live in `src/queryStudio/documentSessionBinding.ts` `open()`.
- Icons: `media/objectTypes/*.svg` via `ObjectExplorerUtils.iconPath()` / `IconUtils.getIcon()`. Group tinted-SVG generator in `connectionGroupNode.ts`.
- No serverless-wake logic exists in classic OE (design's "preserve wake behavior" is aspirational — record as such). No `objectExplorerV2`/`viewMode` code exists anywhere yet.
- Tests to pattern-match: `test/unit/objectExplorerService.test.ts` (sinon stubs), `queryStudioOrchestrator.test.ts` (FakeBackend e2e seam).

## 3. Decisions taken at plan time (design §19 open questions)

| # | Question | Decision |
|---|---|---|
| 1 | Side-by-side vs switch | **Side-by-side during preview**: v2 view contributes with `when: config.mssql.objectExplorer.viewMode == v2Preview`; classic stays visible. Replacing the public view id = separate product decision at flip time. |
| 2 | Query Studio open seam | New `qs:` command `mssql.queryStudio.newQueryFromContext` accepting `{ profileId, database?, initialSql?, source }`, resolved via the existing binding/profile path (no credentials in args — profileId only, store resolves). |
| 3 | Handoff levels per command | Audited in B20 policy table; start H1-only, add H2 for proven commands, H3 only with a named justification per command. |
| 4 | Table preview surface | **Query Studio** with generated SQL + auto-run (capability-gated); no bespoke v2 grid in preview. |
| 5 | First native scripting target | `SELECT` (identifier-formatter only, no metadata gaps). CREATE/ALTER/DROP wait for LS B12 `SqlScriptingService` (cross-plan dependency, recorded). |
| 6 | DB-scoped Azure connections | Server node renders with `accessState`-aware single-database representation from ServerCatalog (`HAS_DBACCESS` may be NULL; failure ≠ empty). |
| 7 | Connection groups | **Shared read-only reuse** of `ConnectionConfig`/`ConnectionStore` for tree structure; group CRUD/drag-drop remain classic commands operating on the same shared storage (v2 re-renders on config change). No new grouping model. |
| 8 | Confirm first handoff | Yes — `mssql.objectExplorer.v2.confirmLegacyHandoff` default `true`, "don't ask again" persists. |

Also decided: **preview-safe session strategy** (one metadata session per database, per design §6.4) with the key-aware `open(key)` API added NOW so the serialized-USE lane can come later behind the same interface. Store-level LRU + idle TTL from day one (bounded session pressure). The classic-backend router (`mssql.objectExplorer.backend`) is **NOT built**; classic `NodeInfo` fixtures are captured opportunistically in B20 for the H2 adapter only.

## 4. Batches

### B15 / MD-A: MetadataStore foundation (store, keys, key-correct acquisition, server catalog) — **COMPLETE (Entry 2)**
*Design: metadata_service_oe_v2_design MD-0..MD-3. Commits: perftest ec5b4f6 (core:), vscode-mssql 4dc939f42 (core:) + b82af5713 (qs:).*

1. `core:` (perftest) — register vocabulary: `metadataStore.*` (prepareProfile/acquireServer/acquireDatabase/refresh/disposeLease/session.open/close/hydrate.server/hydrate.database/drift.detected/cache.hit|miss/keyCorrectness.violation) + `objectExplorerV2.*` span/event families (view.activate, connection.open/close/lost, serverCatalog.acquire/refresh, databaseCatalog.acquire/refresh, tree.expand/filter/search, command.route/native/handoff, legacyConnection.created, unsupported, noV1Browse.violation). Regenerate + re-vendor.
2. `qs:` — extract `src/services/metadata/profileFingerprint.ts` + `profileAuthAdapter.ts` from `documentSessionBinding.open()` (fingerprint recipe unchanged ⇒ existing catalog keys stay stable; passwordProvider closure pattern preserved); binding consumes the helpers, zero behavior change.
3. `qs:` — `src/services/metadata/metadataStore.ts`: `IMetadataStore` + `ServerKey/DatabaseKey/ObjectKey`, refcounted `ServerCatalogLease`/`DatabaseCatalogLease`, status model, `onDidChange`, LRU + idle-TTL session release. `KeyAwareMetadataSessionSource.open(key)` interface; first impl = per-database `DataPlaneMetadataSessionSource` with `OpenSessionParams.database = key.database` (key-correct by construction). Existing `MetadataService` becomes the database-catalog engine behind the lease.
4. `qs:` — `src/services/metadata/serverMetadataService.ts`: sys.databases catalog (design §7.2 query), `ServerDatabaseInfo` incl. `accessState`, readiness/partial/permission states, generations, refresh.
5. Tests: fingerprint stability/secrecy, A/B database isolation (distinct fixture objects, concurrent acquire, refresh-during-hydrate), lease refcount/dispose, server catalog failure ≠ empty, privacy canaries (metadataStore events), fake-data-plane suite.

Exit: store returns key-correct leases under tests; Query Studio untouched and green; contracts conformance green.

### B16 / MD-B: Store adoption + OE-grade metadata — **COMPLETE (Entry 3)**
*Design: MD-4, MD-5 (+H7 descriptions if cheap). Commit: vscode-mssql 1f4a597e5 (qs:). H7 descriptions NOT taken (rides B11/LS-3 as planned).*

1. `qs:` — `DocumentSessionBinding` acquires metadata through `IMetadataStore.acquireDatabase` (replaces its own per-doc `MetadataService`); database-change re-key becomes lease swap; `CatalogLanguageMetadataProvider` hosts a `DatabaseCatalogLease`. **MD-4 golden parity 8/8 must stay byte-identical; full gates re-run (metadata is on the QS hot path).**
2. `qs:` — OE-required sections: PK/unique constraint NAMES (H4 extension), reverse FK column pairs, `listObjects(ObjectListQuery)` as a real listing (not empty-prefix search) on the pinned view + store facade, section-readiness surfaced via store status; schema list + case-sensitivity-aware filtering helpers.
3. `qs:` — large-catalog fixture provider (10k objects / 1k columns) for tests + future perf scenarios.

Exit: QS + native language service run on store leases with unchanged behavior (suite + gates green); OE folder enumeration APIs proven on large fixtures.

### B17 / OE-A: OE v2 shell, tree model, no-v1 tripwires — **COMPLETE (Entry 4)**
*Design: oe_view V2-0 + profile adapter half of V2-1. Commits: vscode-mssql 9d5096ab8 (core: lint) + 6ca6d805f (oe: shell).*

1. `oe:` — `src/objectExplorer/v2/`: `settings.ts`, `activation.ts` (registered from mainController behind `viewMode == "v2Preview"`, config-watched — late enable without reload, the B3 lesson), `objectExplorerV2Provider.ts` (thin TreeDataProvider edge), `tree/` pure modules: `oeV2Node.ts`, `oeV2Path.ts` (versioned, percent-encoded encode/decode), `oeV2Readiness.ts`, `oeV2Capabilities.ts`, `oeV2NodeFactory.ts`, `oeV2TreeStore.ts`, `oeV2TreeController.ts` (loading nodes, refresh batching — copy classic's loading-node trick, not its session model).
2. `oe:` — root content: read-only `ConnectionProfileTreeSource` over `ConnectionStore.readAllConnectionGroups()/readAllConnections()` (ROOT group hierarchy, groups-first ordering — same shape as classic `getRootNodes`), config-change re-render; disconnected profile nodes with `canConnect`; data-plane-unavailable top node (effective settings + [Show status] + [Open Classic]); `mssql.objectExplorerV2.showStatus` (OutputChannel lantern, same style as the LS status command).
3. `oe:` — package.json: setting, view (id `mssql.objectExplorerV2`, container `objectExplorer`, `when` gate), v2 command ids, `viewItem` contexts built from the capability model (context value = serialized capability flags, NOT classic type strings).
4. Tests: path codec, node factory, readiness mapping, capability→menu-context, **no-v1 spy harness** (spies on `ConnectionManager.connect`, `GetSessionIdRequest`, `CreateSessionRequest`, `Expand/Refresh/CloseSessionRequest`; asserts activation + root render create no v1 state). Lint: banned-imports clauses for `objectExplorer/v2/**`.

Exit: v2 view enables/disables by setting without reload; renders groups + saved profiles + honest unavailable states; zero v1 calls proven; classic OE untouched.

### B18 / OE-B: data-plane connect + full catalog browse — **COMPLETE (Entry 5)**
*Design: V2-2..V2-4. Commit: vscode-mssql 0640c3f35 (oe:).*

1. `oe:` — `sessions/oeV2ProfileAdapter.ts` (shared profileFingerprint/profileAuthAdapter helpers; Entra token path via the same account provider used by the data plane elsewhere; NO `ConnectionManager.connect`), `sessions/oeV2SessionRegistry.ts` (openSession `applicationName: "vscode-mssql-oe-v2"`, states connecting/connected/lost/reconnecting/disconnected/failed, close discipline), `metadata/oeV2MetadataCoordinator.ts` (server lease + lazy per-database leases via the store; pin once per expand; targeted node refresh on store change events).
2. `oe:` — expansion rules: server → Databases folder (server-catalog states table from design §10.4); database → Tables/Views/Stored Procedures/Functions/Synonyms/Schemas (lease acquired lazily on database expand); object folders via `listObjects` (+ `groupBySchema` setting); object children: table → Columns/Keys/Foreign Keys, view → Columns, proc/scalar fn → Parameters, TVF → Columns+Parameters; failed sections → status/error children.
3. `oe:` — icons via `ObjectExplorerUtils.iconPath` name mapping; connect/disconnect commands (explicit connect, no auto-connect-on-expand); lost-session UX + reconnect.
4. Tests: fake-data-plane integration (connect → databases → folders → objects → children, all spied no-v1), multi-database A/B isolation through the coordinator, readiness/error rendering, lost/reconnect, dispose closes sessions + leases.

Exit: full browse of a fake multi-database server with key-correct catalogs and zero v1 state; honest states everywhere.

### B19 / OE-C: native commands + table preview — **COMPLETE (Entry 6)**
*Design: V2-5, V2-6. Commits: vscode-mssql 8cb0c3402 (qs: open-from-context seam) + c7c181558 (oe: commands).*

1. `oe:` — `commands/oeV2CommandRouter.ts` + `oeV2NativeCommands.ts`: refresh (server/database/folder → lease refresh), in-memory filter (Name/Schema; equals/contains/startsWith; collation-aware) + clear, search over store `searchObjects`, copy name / qualified name (bracket-escaping formatter `sqlIdentifierFormatter.ts` — shared with preview SQL gen).
2. `qs:` — `mssql.queryStudio.newQueryFromContext` (decision #2): opens a Query Studio doc bound to the given profile/database; `oe:` wires New Query + `initialSql` for SELECT TOP.
3. `oe:` — `commands/oeV2TablePreview.ts`: `SELECT TOP (N) * FROM [schema].[table]` (limit setting, default 1000), routed into Query Studio with auto-run; expectedDatabase enforced; no SQL text in diagnostics.
4. Tests: command router capability gating, filter semantics incl. case sensitivity, identifier escaping (adversarial names: `]`, unicode, keywords), preview SQL generation, no-v1 spies across every native command.

Exit: usable daily-driver browse workflows with zero v1; menus capability-driven.

### B20 / OE-D: explicit legacy handoff + command audit — **COMPLETE (Entry 7)**
*Design: V2-7 + the §12.4 policy table. Commit: vscode-mssql 6087f103a (oe:). Fixture capture folded into the MV-ledger dogfood pass.*

1. `oe:` — `legacy/oeV2ClassicHandoffService.ts`: H1 (lazy `ConnectionManager.connect(ownerUri, profile)` with generated secret-free owner URI, idle TTL, dispose-on-disconnect), H2 (`oeV2LegacyNodeAdapter.ts` → best-effort `TreeNodeInfo`; validated against captured classic NodeInfo fixtures), H3 only if a selected command proves to need it (named + tested individually). First-use confirmation (decision #8), status entries, `objectExplorerV2.command.handoff` + `legacyConnection.created` events.
2. `oe:` — `commands/oeV2LegacyCommandPolicy.ts`: the policy table IN CODE (design §12.4 starting values); unsupported commands hidden; guarded commands show the explanation; handoff unreachable from getChildren/activation/connect/refresh/filter/search (tests).
3. Fixture capture (OE-0, harness-assisted where a live server is available): classic `NodeInfo` snapshots for server/database/table/columns/keys to pin the H2 adapter; committed as test fixtures.
4. Tests: handoff-once-per-TTL, failure isolation (handoff failure never mutates v2 tree), disconnect closes handoff, per-command route tests, guardrail spies.

Exit: selected legacy features (classic editor, Table Designer, Backup/Restore, Profiler, Schema Compare per policy table) reachable from v2 nodes via explicit handoff; browse path still provably v1-free.

### B21 / OE-E: perf scenarios, Debug Console visibility, preview readiness — **COMPLETE (Entry 8)**
*Design: V2 perf targets §15/§16.6 + acceptance gates §18. Commits: perftest 6f83c0e-era scenario commit + vscode-mssql ccb5c5ba2 (oe:). Live browse 338–416ms.*

1. `core:` (perftest) — scenarios: `objectexplorerv2-activate`, `objectexplorerv2-connect-databases` (connect → Databases ready), `objectexplorerv2-expand-tables-10k`, `objectexplorerv2-filter-10k` (fixture catalogs from B16; real-server variants where the harness DB allows); PERF_MODE seams (`mssql.perf.objectExplorerV2State` probe if needed). Wire into `config.eval.local.jsonc` as exploratory first (standing-gate promotion after baseline history accrues — the QS lesson).
2. `oe:` — instrumentation completion pass: every §14.1 event emitting with classified fields; `noV1Browse.violation` tripwire event wired to the spy assertions in dev builds; status model dump command redaction-checked.
3. Debug Console: OE v2 spans/events flow through the existing substrate (timeline/waterfall) — verify with a captured session; add an OE section to the perf-history scenario labels where relevant. (A dedicated DC page = backlog, same shape as the completions/replay panel deviation.)
4. Preview-readiness checklist vs design §18 + performance-targets table measured (host-work timings from spans); dogfood pass with a live server; PROGRESS entry with the flip-readiness assessment (the flip itself is NOT this plan).

Exit: gates green incl. new scenarios; acceptance-gate checklist answered honestly; residuals dispositioned.

## 5. Cross-plan dependencies

- **LS B12 `SqlScriptingService`** → native Script As (V2-8). Until then: Script SELECT native; CREATE/ALTER/DROP hidden or handoff per policy table.
- **H7 descriptions** (LS B11 + store MD-6) → object tooltips/properties polish; not preview-blocking.
- **STS2 M7 preview tag** → unrelated to OE browse (data plane already shipping); noted only for DC live-source work.

## 6. Worksheet (open items to answer during the build)

| # | Question | Answer when |
|---|---|---|
| 1 | ~~HAS_DBACCESS filtering~~ **ANSWERED (B15):** no WHERE filter — all sys.databases rows listed with `accessState` (1→accessible, 0→inaccessible, NULL→unknown); SSMS-style show-but-mark. | ✅ B15 |
| 2 | Session pressure: per-database metadata sessions under a 50-db expand-all — is LRU+TTL enough (B15 shipped idleTtlMs 120s + maxIdleDatabases 4), or do we need the serialized-USE lane sooner? | B18 (measure), B21 (perf) |
| 3 | Which classic commands do dogfooders actually invoke from v2 nodes (drives H2/H3 investment)? | B20 telemetry + dogfood |
| 4 | Do group CRUD/drag-drop need v2-native implementations, or is shared-storage reuse (classic commands) acceptable for preview? | B19 dogfood |
| 5 | Table preview auto-run: always, or only ≤ row-limit tables (avoid surprise full scans on views)? Preview = TOP N so bounded — but views with expensive plans? | B19 |
| 6 | ~~ServerKey fingerprint~~ **ANSWERED (B15):** new hash-based `sfp_` server fingerprint excludes database; profile-scoped `pfp_` replaces the reversible `qsfp_` recipe (it leaked the server name, violating the profileRef contract). In-memory keys only — nothing persisted invalidates. | ✅ B15 |

## 7. Definition of done (whole effort)

Design §18 acceptance gates, plus house bars: suite green (flake-only), gates 16/16 incl. new OE scenarios at exploratory+, lint boundaries enforced, privacy canaries green, no-v1-browse spies mandatory in the suite, classic OE behavior byte-identical when `viewMode == "classic"`, journals current, all trees committed clean on the right trains.
