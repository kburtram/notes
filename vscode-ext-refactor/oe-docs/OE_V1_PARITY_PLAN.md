# Object Explorer v2 — v1/SSMS Parity Plan (B22–B27)

**Authored:** 2026-07-10, from Karl's six-point directive plus three code surveys (classic OE
implementation, STS SmoTreeNodesDefinition hierarchy, OE v2 current seams).
**Relationship to prior docs:** extends `EXECUTION_PLAN.md` (B15–B21 COMPLETE, PROGRESS Entries 1–9).
House rules (§1 of EXECUTION_PLAN) carry over unchanged and BINDING: commit trains `oe:`/`qs:`/`core:`,
contracts-first, privacy classification, no-v1-browse tripwires, readiness honesty, verification chain
per batch, journal per batch in `PROGRESS.md`.
**Journal wins over this plan.** Karl will deliver detailed specs (exact SSMS folder layout, full
command matrix) later — the framework must absorb those as DATA changes, not architecture changes.

---

## 0. Mission (Karl, 2026-07-10, paraphrased with traceability)

Make OE v2 a UX drop-in replacement for OE v1 — same content and commands, but faster and more
reliable on STS v2 connections + MetadataStore + caching. Six requirement areas:

| # | Requirement | Batch |
|---|---|---|
| K1 | Server-level metadata objects (logins, server roles, credentials, encryption/crypto, service broker, users, "all the objects") when connected to a SERVER; suppressed when connected to a DATABASE. Organization must be configurable through metadata in code (future spec will say e.g. "Security/Logins"). Must stay super quick. | B23 (server scope), B24 (database scope) |
| K2 | System-data display: system database context → system objects shown; user database, non-ms_shipped → no system objects. | B24 |
| K3 | Ledger + temporal/history tables organized like SSMS; subfolders (e.g. Dropped Ledger Tables) ONLY when non-empty — no empty folders. | B24 |
| K4 | Extensible command registration with full when-context support. First commands: Backup (database nodes only, incl. DB-scoped top-level connections) + Restore (server or database nodes). Commands get an STS v1 connection via a redirect seam: v2 node → lookup → legacy handler unchanged; OE v2 never touches the v1 connection directly. NEW registrations file — v1 registrations untouched, reuse only without change. | B25 |
| K5 | Server groups like v1: same dialog/buttons, arbitrary nested folders, connections moveable into folders. | B26 |
| K6 | Top-level node label = v1 recipe `server, database (auth)` (e.g. `localhost, <default> (Integrated)`); when two nodes tie on those, tooltip surfaces the differing properties. Copy the v1 label/tooltip builders. | B22 |
| K-cross | Framework/API quality: hierarchy customizable per connection type; commands attached by precise context; node → full metadata extraction for command handlers; connection-in-progress UX (spinners, cached-metadata indicators); mindful of timeouts; testable, diagnosable, fast. | all; UX close-out B27 |

Zero-impact law still applies: everything additive on `dev/query`, classic OE byte-identical,
`viewMode: "classic"` default untouched.

## 1. Code truth this plan builds on (verified 2026-07-10)

### Classic OE (reuse targets — never modify)
- Label: `models/connectionInfo.ts` `getConnectionDisplayName()` (:275) — profileName wins, else
  `` `${server}, ${database} (${userOrAuthType})` ``; SqlLogin→user, AzureMFA→email, Integrated→"Integrated"
  (raw authType); `<default>` = `LocalizedConstants.defaultDatabaseLabel` (locConstants.ts:316).
- Tooltip: `objectExplorer/nodes/connectionNode.ts` `getConnectionTooltip()` (:107-255) — emits only
  non-default properties (profileName bare; then Server/Database/Auth/Port/container/version/
  applicationIntent/timeouts/alwaysEncrypted/replication), joined with os.EOL.
- Groups: `IConnectionGroup {id,name,parentId?,color?,description?}` (models/interfaces.ts:77);
  storage `mssql.connectionGroups` via `ConnectionConfig` (ROOT_GROUP_ID="ROOT", addGroup/updateGroup/
  removeGroup(id,"delete"|"move")); dialog `controllers/connectionGroupWebviewController.ts`
  (standalone, callable with optional group-to-edit); DnD `objectExplorerDragAndDropController.ts`
  (MIME `application/vnd.code.tree.objectExplorer`; drop sets `conn.groupId`/`group.parentId`).
- Backup/Restore handlers (mainController.ts:2429/2449): consume `node.connectionProfile`,
  `node.sessionId`, `ObjectExplorerUtils.getDatabaseName(node)` → webview controllers. Classic menus
  gate Backup on `(type|subType)=(Database|DockerContainerDatabase)`, Restore on Server + Database.
- Classic context value grammar: comma-separated `type=…,subType=…,filterable=…,hasFilters=…`.

### STS SMO hierarchy (the SSMS layout authority — sqltoolsservice/…/ObjectExplorer/SmoModel/SmoTreeNodesDefinition.xml)
- Server: Databases (+System Databases), Security (Logins, Server Roles, Credentials, Cryptographic
  Providers, Server Audits, Server Audit Specifications), Server Objects (Endpoints, Linked Servers,
  Server Triggers, Error Messages).
- Database: Tables (+System/External/Dropped Ledger), Views (+System/Dropped Ledger), Synonyms,
  Programmability (Stored Procedures+System, Functions [System/TVF/Scalar/Aggregate], Database
  Triggers, Assemblies, Types [System Data Types + UDDT/UDTT/UDT/XML Schema Collections], Sequences),
  External Resources, Service Broker (Message Types, Contracts, Queues, Services, Event Notifications,
  Remote Service Bindings, Broker Priorities — each with System* subfolder), Storage (Filegroups,
  Full Text Catalogs/Stop Lists, Log Files, Partition Functions/Schemes, Search Property Lists),
  Security (Users, Roles [Database/Application], Schemas, Asymmetric Keys, Certificates, Symmetric
  Keys, Database Scoped Credentials, Database Encryption Keys, Master Keys, Database Audit
  Specifications, Security Policies, Always Encrypted Keys [CMK/CEK]).
- System mechanics: collections filter `IsSystemObject=0`; sibling `System*` folder at `=1` marked
  `IsSystemObject`; runtime gate strips system folders unless connected DB is a system database
  (`TreeNode.cs:351`, `SmoChildFactoryBase.cs:65`). `IsMsShippedOwned` marks system folders.
- Ledger/temporal: Tables list excludes `TemporalType=HistoryTable`, `LedgerType=HistoryTable`,
  `IsDroppedLedgerTable=1`; history table nests UNDER its parent table (match `HistoryTableID`);
  Dropped Ledger Tables/Views/Columns folders sort last (`SortPriority=Int32.MaxValue`); labels
  `(System-Versioned)`, `(Updatable Ledger)`, `(Append-Only Ledger)`, `(External)`, `(FileTable)`;
  subtypes drive icons (Temporal/LedgerUpdatable/LedgerAppendOnly/LedgerDropped/GraphNode/GraphEdge).
- Version gating: `ValidFor` flags per node/filter/property (Sql2016OrHigher, Sql2022OrHigher,
  AzureV12, AllOnPrem…); invalid folders stripped.

### OE v2 seams (insertion points)
- `tree/oeV2Browse.ts` `serverChildren()` renders ONLY Databases; `OeV2ServerFolder` already types
  `"security"|"serverObjects"`. `FOLDER_LABELS`/`FOLDER_KINDS`/`FOLDER_SECTION` are the hard-coded
  tables the hierarchy registry replaces.
- `serverMetadataService.ts` hydrates sys.databases only; extension point = new section queries +
  pinned-view accessors. `metadataService.ts` H0–H7 covers schemas/objects/columns/keys/FKs/params/
  descriptions; NO temporal/ledger facets, no security/broker/storage objects.
- Handoff: `legacy/oeV2ClassicHandoffService.ts` (H1 ownerUri via injected ConnectionManager seam,
  confirm gate, TTL) + `oeV2LegacyNodeAdapter.toLegacyTreeNode()` (server/database/object) +
  `commands/oeV2LegacyCommandPolicy.ts` policy table (backup=h2 database-scoped; restore=h2
  server+database; today surfaced ONLY via the `Legacy Actions…` quick pick).
- Groups: `oeV2ProfileAdapter.readProfileTree()` read-only, nesting renders; NO CRUD/move/DnD.
- Labels: `connectionNode` label = `profile.displayName` (profileName||server) — NOT the v1 recipe.
- Context values: `oe2:kind=…` + `oe2:can…` flags; menus regex-gated on them.

## 2. Architecture additions

### 2.1 Declarative hierarchy registry (K1 organization, K2/K3 rules as data) — `tree/oeV2Hierarchy.ts`
One in-code table describing every folder, modeled on SmoTreeNodesDefinition.xml:

```ts
export interface OeV2FolderDef {
    readonly id: string;              // stable slug: "security", "security/logins", "tables/systemTables"
    readonly label: string;           // display name (SSMS wording)
    readonly scope: "server" | "database" | "objectFolderChild";
    readonly parentId?: string;       // nesting: undefined = direct child of scope root
    readonly order: number;           // SSMS ordering
    readonly section: string;         // catalog section that backs it (drives lazy hydration + readiness)
    readonly content?: OeV2FolderContentSpec;  // objectKinds / auxiliary item kind / special ("schemas")
    readonly isSystemFolder?: boolean;         // stripped in user-database context (K2)
    readonly presence?: "always" | "nonEmpty"; // "nonEmpty" = hide when zero items (K3)
    readonly sortLast?: boolean;               // Dropped Ledger* pattern
    readonly validFor?: (facts: OeV2ScopeFacts) => boolean; // version/edition/connection-shape gate
}
```

`OeV2ScopeFacts` = { serverMajorVersion, engineEdition, isAzure, databaseScopedConnection,
isSystemDatabase, groupBySchema }. Pure resolver `resolveFolders(scope, facts, counts)` returns the
ordered, gated folder list; `oeV2Browse` iterates it instead of `FOLDER_LABELS`. Existing six
database folders + Databases become registry entries FIRST (no behavior change), then new entries
are data. Future Karl-spec layout changes = edits to this one table. `oeV2Path` gains generic
`folderId` segments (versioned codec bump with backward decode).

### 2.2 Auxiliary catalog sections (K1 speed) — `services/metadata/auxiliaryCatalog.ts` (qs:)
Server- and database-scoped LAZY sections, one cheap query each, hydrated ON FIRST EXPAND of the
owning folder (never at connect), single-flight, cached in the store lease with the existing
generation/TTL discipline, refreshable per folder. Uniform item shape:

```ts
export interface AuxCatalogItem {
    readonly name: string; readonly schema?: string;
    readonly kind: string;            // "login" | "serverRole" | "user" | "certificate" | …
    readonly subType?: string;        // icon/status modifier ("disabled", "windowsLogin", …)
    readonly isSystem: boolean;       // is_ms_shipped / principal_id ranges / IsSystemObject analog
    readonly sortName: string;
}
```

Section specs declare: key, scope, SQL (version-gated variants), row mapper, privacy class of names
(object-name classification, same rules as existing metadata). Server sections (B23): logins
(sys.server_principals S/U/G/C/K + is_disabled), serverRoles (type R), credentials (sys.credentials),
cryptographicProviders, serverAudits, serverAuditSpecifications, endpoints (sys.endpoints),
linkedServers (sys.servers is_linked=1), serverTriggers (sys.server_triggers), errorMessages
(sys.messages message_id>50000). Database sections (B24): users, databaseRoles, applicationRoles,
asymmetricKeys, certificates, symmetricKeys, databaseScopedCredentials, databaseEncryptionKeys,
masterKeys, databaseAuditSpecifications, securityPolicies, columnMasterKeys, columnEncryptionKeys,
serviceBroker.{messageTypes,contracts,queues,services,remoteServiceBindings,brokerPriorities},
storage.{filegroups,fullTextCatalogs,fullTextStopLists,logFiles,partitionFunctions,partitionSchemes,
searchPropertyLists}, databaseTriggers, assemblies, sequences, userDefinedTypes(+table types, XML
schema collections). Counts surface to `presence: "nonEmpty"` resolution WITHOUT hydrating children
where the section query already returns rows (hydration IS the count source — expand of parent
folder triggers the section fetch of `nonEmpty` children only when cheap: one COUNT-per-section
probe batched per parent expand; measure in B27, tune).

### 2.3 Table facets (K3) — H8 phase, additive (qs:)
New version-gated hydration section `tableFacets`: `temporal_type, history_table_id, ledger_type,
is_dropped_ledger_table(2022+), is_external, is_node/is_edge(2017+), is_filetable` from sys.tables
LEFT JOINs, only columns the server version supports (assembled from H0 facts). Feeds: Tables-list
exclusion of history/dropped rows, nested history-table child under parent, name suffixes
`(System-Versioned)` etc., subtype icons, Dropped Ledger Tables/Views folders (nonEmpty). MUST NOT
perturb `buildSchemaContext` goldens (separate section, not folded into H2/H3).

### 2.4 Command registry (K4) — `commands/oeV2CommandRegistry.ts`
New registrations file; declarative entries:

```ts
export interface OeV2CommandDef {
    readonly id: string;                       // "mssql.objectExplorerV2.backupDatabase"
    readonly title: string;
    readonly route: { kind: "native"; run(target: OeV2CommandTarget): Promise<void> }
                  | { kind: "legacyRedirect"; feature: OeV2LegacyFeature };  // → redirect library
    readonly targets: OeV2TargetRule[];        // node kinds + predicates (databaseScoped, capability flags)
    readonly menuGroup?: string;               // package.json when-clause generated from targets → new oe2:cmd flags
}
```

`OeV2CommandTarget` = the node-extraction contract (K-cross): full node metadata (path, kind,
connectionId, database, schema, object identity, facts) + resolved profile/fingerprint — one
function `commandTargetFor(node, controller)` so every handler gets identical rich context.
Targeting emits per-command context flags (`oe2:cmd=backup`) into the capability serializer so
package.json `when` stays precise; menu contributions generated from the same table (checked-in
output, conformance-tested against the registry — no drift).

### 2.5 STS v1 redirect library (K4) — `legacy/oeV2LegacyRedirect.ts`
Formalizes the proven handoff pattern as THE way legacy commands launch: resolve target →
`ensureOwnerUri` (confirm gate + TTL as today) → `toLegacyTreeNode` (kind-scoped, database-scoped
when rule says) → `vscode.commands.executeCommand(classicCommand, adaptedNode)`. Legacy handlers
stay byte-identical; v2 never touches the v1 connection object. Backup targets database nodes AND
DB-scoped top-level connections; Restore targets connected servers + databases. Existing
`Legacy Actions…` quick pick reroutes through the same library (one code path).

### 2.6 Groups CRUD/move (K5) — reuse classic pieces on new v2 command ids
`mssql.objectExplorerV2.connectionGroups.{create,edit,delete}` → invoke the SAME
`ConnectionGroupWebviewController` + `ConnectionConfig` CRUD (delete offers Delete/Move contents like
classic); `moveToGroup` command (quick-pick of group tree) sets `conn.groupId`/`group.parentId`; v2
DnD controller (own MIME `application/vnd.code.tree.mssql.objectExplorerV2`) mirroring classic drop
semantics. v2 re-renders via existing config watcher. Classic files untouched.

### 2.7 Labels/tooltips (K6) — reuse v1 builders
`oeV2ProfileAdapter` computes displayName via `getConnectionDisplayName` (import from models —
adapter layer is impure-ok; tree stays pure receiving strings). Tooltip: extract classic
`getConnectionTooltip` body into a shared pure helper (new file, classic node DELEGATES ONLY IF
zero-risk — otherwise duplicate into v2 with a source comment; decide at code time, prefer
no-classic-edit). Disambiguation (Karl's addition over v1): after tree build, nodes with identical
labels get differing non-default properties appended to tooltip + `description` hint.

### 2.8 Observability + perf
New contracts vocabulary (core:, perftest registry first): `objectExplorerV2.auxCatalog.hydrate`
(section, scope, rowCount, elapsed), `objectExplorerV2.command.invoke` (route, commandId, nodeKind),
`objectExplorerV2.group.mutate` (op), `objectExplorerV2.hierarchy.resolve` (folderCount, gated
counts). Perftest scenarios (B27): server-folder expand (security), aux-section hydration timing,
regression guard on existing objectexplorerv2-browse. Debug Console: sections flow through existing
span timeline; showStatus gains aux-section table (hydrated/rows/age per section).

## 3. Batches

### B22 / OE-F: hierarchy registry + label/tooltip parity
1. `oe:` — `tree/oeV2Hierarchy.ts` registry + resolver; migrate existing Databases + 6 database
   folders onto it (byte-identical rendering, tests prove); path codec `folderId` support.
2. `oe:` — K6 labels: v1 display-name recipe + rich tooltip + tie disambiguation; connected/
   connecting descriptions preserved.
3. Tests: registry resolution (scope/validFor/presence/system gating as pure table tests),
   label parity vs classic recipe fixtures (incl. `<default>`, SqlLogin/AzureMFA/Integrated),
   tie-disambiguation, codec round-trip, no-v1 spies stay green.
Exit: rendering unchanged for today's content; labels match v1; registry is the single layout source.

### B23 / OE-G: server-level metadata objects
1. `core:` — contracts vocabulary (auxCatalog + hierarchy events), regenerate/re-vendor.
2. `qs:` — auxiliaryCatalog server sections + store lease surfacing + lazy single-flight hydration
   + refresh + status; privacy classification on names.
3. `oe:` — Security + Server Objects folders (registry entries) rendered from sections; icons
   (reuse media/objectTypes where present, ThemeIcon fallback); databaseScopedConnection gate (K1:
   profile with explicit database → NO server-level folders); login disabled badge; System Databases
   folder (registry + existing isSystem flag).
4. Tests: fake-data-plane aux sections, lazy-hydration (expand-triggered, no connect-time fetch),
   DB-scoped gating, failure honesty per section, no-v1 spies, privacy canaries.
Exit: server connections browse Security/Server Objects live-fast; DB-scoped connections don't.

### B24 / OE-H: database-level parity + system rules + ledger/temporal
1. `qs:` — database aux sections (Security/Service Broker/Storage/Programmability additions) +
   H8 tableFacets (goldens untouched); is_ms_shipped/isSystem on H2 objects if absent.
2. `oe:` — registry entries for the full SSMS database layout (§1 STS survey is the layout
   authority until Karl's spec lands); K2 system gate (system-database context → System* folders +
   system objects; user database → stripped); K3: history tables nested under parents, excluded from
   main list; Dropped Ledger Tables/Views as `presence:"nonEmpty"` + sortLast; name suffixes + subtype
   icons; Programmability (triggers/assemblies/types/sequences), Service Broker, Storage, Security.
3. Tests: system-context matrix (master vs user db), temporal/ledger fixture catalog (history
   nesting, exclusion, empty-folder suppression), version gating (2016/2017/2022/Azure), goldens
   10/10, no-v1 spies.
Exit: database subtree matches SSMS organization on fixtures; no empty ledger folders; system rules per K2.

### B25 / OE-I: command registry + Backup/Restore + redirect library
1. `oe:` — oeV2CommandRegistry + commandTargetFor + generated menu contributions (conformance test);
   oeV2LegacyRedirect; Backup (database nodes + DB-scoped connections) + Restore (servers +
   databases) as first registrations; Legacy Actions quick pick reroutes through the library;
   policy table stays the truth for feature→classicCommand mapping.
2. Tests: targeting matrix (backup absent on server-scoped connection node, present on nested db +
   DB-scoped top-level), redirect flow with spied executeCommand + fake handoff, confirm-gate
   inheritance, failure isolation, no-v1-from-browse unchanged.
Exit: right-click Backup/Restore works on the right nodes through classic dialogs; adding a command = one registry entry.

### B26 / OE-J: server groups CRUD + move + DnD
1. `oe:` — group create/edit/delete commands on v2 nodes (shared dialog + ConnectionConfig),
   moveToGroup quick-pick, v2 DnD controller (connection→group, group→group, root drop, self-drop
   guard), inline icons parity, group color/description rendering (tinted icon reuse decision at
   code time).
2. Tests: CRUD delegation (stubbed config), move semantics, DnD handler unit tests (drop targets,
   guards), re-render on config change, classic untouched.
Exit: full group management from v2 without opening classic.

### B27 / OE-K: connect-UX polish + perf + close-out
1. `oe:` — connection-in-progress polish: spinner states audit (connecting/reconnecting/aux-section
   loading), cached-metadata indicator (description shows "(cached)" + refresh affordance when
   serving stale-but-warm), timeout surfacing (slow-connect status child with elapsed), K-cross UX
   pass with Karl's dogfood notes.
2. `core:`+perftest — scenarios: server-security expand, aux hydration, browse regression; baseline
   runs where harness available.
3. Docs/journal: acceptance checklist vs K1–K6, residuals dispositioned, memory updated.
Exit: Karl-visible UX complete; perf evidenced; journal current.

## 4. Decisions taken at plan time

| # | Decision |
|---|---|
| P1 | Hierarchy = in-code declarative registry (SmoTreeNodesDefinition analog), NOT config-file; Karl's future spec lands as registry edits. |
| P2 | Aux sections hydrate lazily per folder expand; never at connect. Counts for `nonEmpty` folders ride the parent's section fetch (measured in B27 before any eager probing). |
| P3 | Table facets = separate H8 section; QS `buildSchemaContext` goldens must stay byte-identical. |
| P4 | Backup/Restore route = H2 redirect via existing handoff service (proven adapter); no new v1 surface. Classic registrations/handlers untouched. |
| P5 | Group CRUD reuses classic dialog + ConnectionConfig under NEW v2 command ids (worksheet #4 of the old plan now ANSWERED: shared-storage reuse, v2-native entry points). |
| P6 | Label recipe imported from `models/connectionInfo.ts` at the adapter layer (tree stays pure); tooltip logic shared or duplicated — whichever keeps classic file diff at zero. |
| P7 | System-context rule follows STS: system folders + system objects appear when connected database is a system database; plus explicit System Databases folder at server scope always. Per-folder isSystemFolder flag in registry. |
| P8 | SSMS layout per STS XML survey is authoritative until Karl's written spec supersedes it. |

## 5. Worksheet (open — answer during build/dogfood)

| # | Question |
|---|---|
| 1 | Exact folder layout spec from Karl (SSMS walk-through) — registry edits when it lands. |
| 2 | `nonEmpty` probing cost on high-latency links: batched COUNT probe vs hydrate-on-parent-expand — measure B27. |
| 3 | Which additional legacy commands after Backup/Restore (Karl's command spec). |
| 4 | Error Messages folder: include user messages only (message_id>50000) or skip until asked? (Start: include, user-only.) |
| 5 | Aggregate Functions folder: catalog query support (sys.objects type AF) — include in Functions if trivially cheap. |
| 6 | DnD between v1 and v2 views (shared MIME?) — start v2-internal only. |
