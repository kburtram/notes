# Object Explorer v2 — Build Journal

Restart protocol: read `EXECUTION_PLAN.md` (batches B15–B21 + decisions + worksheet), then the design pack (`oe_view_design.md` PRIMARY, `metadata_service_oe_v2_design.md` substrate, `oe_metadata_design.md` scaffolding-only). House rules carry over from the Query Studio / language-service efforts (`ssms-query-docs/EXECUTION_PLAN.md`): commit isolation `core:`/`qs:`/`ls:`/**`oe:` (new)**, CRLF, commit from repo root, cd to extensions/mssql before npx, contracts regenerate+re-vendor before emitting, privacy rules, never `mssql.sts2.*`, verification chain per batch.

## 2026-07-05 — Entry 1: Plan authored

CONTEXT: QS B1–B7 + QoL batch complete (ssms-query-docs Entry 11); language
service through B9; two planning docs written this session
(`coding-docs/remaining_tasks.md`, `observability-docs/options_for_central_tracing.md`).
Karl's directive: upgrade OE onto STS v2 endpoints + metadata service as an
OPTIONAL new feature (old OE untouched), keep core features incl. server
group management, improve UX, full tests + perftest + debug console
integration; design docs are a starting point, not a straitjacket.

DONE:
- Read all three oe-docs designs + mapped the classic OE implementation
  (service internals, groups storage in ConnectionConfig, view/menu
  contributions, ConnectionManager flow, icons, filter plumbing, test
  layout) and the current data-plane/metadata seams.
- EXECUTION_PLAN.md written: batches B15 (MetadataStore foundation),
  B16 (store adoption + OE-grade metadata), B17 (v2 shell + no-v1
  tripwires), B18 (connect + browse), B19 (native commands + table
  preview), B20 (legacy handoff + command audit), B21 (perf scenarios +
  DC visibility + preview readiness).
- Decisions recorded (plan §3): side-by-side preview view; QS
  open-from-context command; preview-safe per-database metadata sessions
  behind a key-aware source API; table preview = Query Studio auto-run;
  Script SELECT native first (rest waits for LS B12); shared read-only
  connection groups; handoff confirmation default on; classic-backend
  router NOT built (fixtures only, B20).
- Worksheet opened (plan §6): HAS_DBACCESS filtering vs grayed nodes,
  session pressure under many-db expansion, H2/H3 command demand,
  group-CRUD reuse sufficiency, preview auto-run policy, ServerKey
  fingerprint excluding database (without invalidating QS catalog keys).

NEXT: B15 — contracts vocabulary (core:, perftest), profile/auth helper
extraction (qs:), IMetadataStore + key-correct acquisition + server
catalog (qs:), isolation/privacy/lease tests.

## 2026-07-05 — Entry 2: B15 / MD-A COMPLETE (MetadataStore foundation)

SHIPPED — perftest (dev/query):
- core: ec5b4f6 — registry: `metadataStore.` + `objectExplorerV2.` span
  families (member names + attr rules + privacy in notes; the
  noV1Browse.violation tripwire documented as any-emission-is-a-test-
  failure). Regenerated + re-vendored; contracts 27/27.

SHIPPED — vscode-mssql (dev/query):
- core: 4dc939f42 — vendored contract snapshot.
- qs: b82af5713 —
  - services/metadata/profileFingerprint.ts: hash-based NON-REVERSIBLE
    fingerprints — `pfp_` profile-scoped, `sfp_` server-scoped (excludes
    database; the store ServerKey). Replaces the `qsfp_` truncated-base64
    recipe, which DECODED to plaintext server|database|user (violated the
    profileRef "never reversible" contract). identityDigest() for the
    completions classic resolver (`iccfp` now hashed too). In-memory keys
    only — nothing persisted invalidates.
  - services/metadata/profileAuthAdapter.ts: buildProfileRef /
    buildAuthBundle / prepareConnection extracted from
    DocumentSessionBinding.open() — the shared seam OE v2 + the store use;
    binding rewired with zero behavior change (passwords stay inside
    passwordProvider closures).
  - services/metadata/metadataStore.ts: refcounted server/database
    catalog leases over per-key engines. KEY-CORRECT by construction:
    each database catalog opens its own dedicated session with
    OpenSessionParams.database = key.database (preview-safe strategy,
    design §6.1) behind a source wrapper that emits
    metadataStore.keyCorrectness.violation (+ counts in status()) on
    mismatch. Idle TTL (120s default) + LRU cap (4) bound session
    pressure; warm re-acquire = cache hit. Drift routing
    (notifyExecutedBatch by fingerprint+database).
  - services/metadata/serverMetadataService.ts: sys.databases server
    catalog — ALL rows listed with accessState
    accessible/inaccessible/unknown (worksheet #1 ANSWERED: show-but-mark
    like SSMS, no HAS_DBACCESS WHERE filter), isSystem (id<=4),
    state/read-only/compat; pinned generation views; failure ≠ empty.
  - 8 tests (metadataStore.test.ts): fingerprint stability/scoping/
    non-reversibility, prepared-connection auth closure (integrated never
    touches the credential store), concurrent A/B database isolation over
    a routing fake service, refcount/warm-reuse, TTL + LRU eviction,
    server catalog honesty (incl. NULL HAS_DBACCESS), key-correctness
    tripwire (database-ignoring backend), privacy canary over status
    dumps.

REAL BUG FOUND (fix knowledge): MetadataService.hydrate(force=true)
OVERLAPPED a second hydrateCore with the in-flight one on the same
one-active-query metadata session. B5-era tests passed only because
promise-reaction order happened to interleave the two runs' executes at
cleared-slot boundaries; the store's concurrent A/B test shifted the
phase (extra await in the key-check wrapper) and BOTH runs died on Busy.
Fix: forced refresh now CHAINS after the in-flight hydration; the
finally-clear is identity-guarded. Digest-poll refreshes inherit the
serialization.

DECISIONS: worksheet #1 + #6 answered in EXECUTION_PLAN (accessState
show-but-mark; sfp_/pfp_ fingerprint split).

VERIFIED (2026-07-06): tsgo extension clean; repo `npm run build` 0 error
lines; eslint clean; full `npx vscode-test` 3540 passing / 12 pending /
0 failing (+8; even the known copilotChatEntry flake passed this run);
gates 16/16 (run 2026-07-06T02-24-17Z_89c930b0: querystudio-query-10k
433.1–1036.3ms official — within the 389–1060ms historical band, no
regression from the fingerprint/serialization/binding changes;
querystudio-open, query-10k-results, debug-console-smoke passed).
Trees clean: perftest ec5b4f6; vscode-mssql b82af5713.

NEXT: B16 / MD-B — move DocumentSessionBinding + CatalogLanguageMetadata
Provider onto store leases (MD-4 golden parity 8/8 must stay
byte-identical), OE-grade sections (PK/unique constraint NAMES, reverse
FK pairs, listObjects facade), large-catalog fixtures.

## 2026-07-06 — Entry 3: B16 / MD-B COMPLETE (store adoption + OE-grade metadata)

SHIPPED — vscode-mssql qs: 1f4a597e5:
- metadataStoreService.ts: extension-host singleton composition root (same
  process-lifetime pattern as SqlDataPlaneService; setForTests seam).
- DocumentSessionBinding on store leases (MD-4): acquireMetadata =
  prepareConnection + store.acquireDatabase(prepared, db, onStatus);
  database-change re-key = lease swap; releaseMetadata = lease.dispose().
  BEHAVIOR CHANGE (recorded): after QS disconnect the catalog engine stays
  warm ≤ idle TTL (120s, LRU-capped 4) — deliberate store semantics; warm
  reconnect is instant. metadataHandleForConsumers is now the lease —
  language provider/completions resolver/QS state unchanged (structural).
- Store: empty database key = profile default; correctness check skipped.
- OE-grade sections (agent-built, additive): H4 now hydrates PK + UNIQUE
  key constraints with NAMES + key-ordinal column order —
  snapshot.getKeyConstraints(objectId) → KeyConstraintInfo{name, kind:
  primaryKey|uniqueConstraint, columns}; PK column MARKING unchanged
  (unique-constraint columns never PK-marked);
  getForeignKeyDetailsTo(objectId) mirrors ...From with column pairs
  (reuses per-constraint pair storage, no new query). "keys" section
  covers both. buildSchemaContext BYTE-IDENTICAL — golden parity 10/10.
- Large-catalog fixtures (agent-built): test/unit/support/
  largeCatalogFixture.ts — deterministic FakeScript generator
  (spec: schemas/tables/columnsPerTable/wideTable/procedures/FKs;
  default 10k tables + 1000-col WideTable + 200 procs + 2000 FKs) +
  metadataStoreScale suite: hydration-through-store 148ms wall,
  listObjects(10201) 10ms, search/getColumns ~0ms, warm re-acquire = no
  second hydration. All far inside oe_view_design §15 targets.
- FIXTURE HAZARD documented: CHEAP_DIGEST SQL contains
  "FROM sys.objects o WHERE" — digest scripts must precede H2 in
  FakeScript lists (same class as the H4/H5B-before-H3 rule).

VERIFIED (2026-07-06): tsgo clean; repo build 0 errors; eslint clean;
full suite 3549 passing / 12 pending / 0 failing (+9: 4 key-constraint,
5 scale); gates 16/16 (run 2026-07-06T02-48-35Z_40a10c46:
querystudio-query-10k 530.1–1101.2ms official — in band). Tree clean at
1f4a597e5.

NEXT: B17 / OE-A — OE v2 shell: settings (viewMode), activation +
provider, pure tree modules (node/path/readiness/capabilities/factory/
store/controller), read-only ConnectionProfileTreeSource over the
connection store, data-plane-unavailable node, showStatus lantern,
package.json contributions, NO-V1 SPY HARNESS, banned-imports clauses.

## 2026-07-06 — Entry 4: B17 / OE-A COMPLETE (OE v2 shell + no-v1 tripwires)

SHIPPED — vscode-mssql core: 9d5096ab8 (banned-imports: OE v2 clauses —
tree/sessions pure [no vscode/classic OE/data-plane singletons]; all of
v2 outside legacy/** banned from classic OE modules + ConnectionManager).

SHIPPED — vscode-mssql oe: 6ca6d805f:
- src/objectExplorer/v2/tree/: oeV2Path (versioned `oe2:` codec, percent-
  encoded segments, foreign/corrupt ids → undefined; FULL path union incl.
  B18+ kinds), oeV2Node (pure record + readiness + capabilities types),
  oeV2Capabilities (context value = `oe2:kind=…,oe2:canX,…` flag
  serialization — capability-driven menus, NO classic type regexes),
  oeV2Readiness (synthesizeChildren policy: only readyEmpty/ready-zero →
  no-items; failed → error child; permission/unsupported/dataPlane →
  status child; partial renders + container status; + status/error/
  loading/noItems node builders), oeV2NodeFactory (group/connection nodes,
  groups-first alpha ordering — classic getRootNodes shape),
  oeV2TreeController (injected ConnectionProfileSource + DataPlaneProbe;
  root = unavailable status | profile tree | no-profiles guidance;
  connection expand = explicit connect hint until B18; refresh
  invalidates + notifies).
- sessions/oeV2ProfileAdapter: read-only profile/group tree over the
  ConnectionStore structural seam (decision #7) — no credentials ride;
  store-read failures → empty tree, never a throw.
- Edge: objectExplorerV2Provider (TreeItem conversion; ThemeIcons for
  status/error/loading/group; media/objectTypes reuse via
  ObjectExplorerUtils for server icons), activation (register on
  viewMode==v2Preview, config-flip WITHOUT reload, refresh on
  connections/groups/data-plane config changes, showStatus lantern,
  openClassicObjectExplorer, view.activate diag event), settings
  (validated readers incl. tablePreviewRowLimit clamp).
- package.json: mssql.objectExplorer.viewMode (classic default) +
  mssql.objectExplorer.v2.{confirmLegacyHandoff, tablePreviewRowLimit,
  groupBySchema, showSystemDatabases}; when-gated view
  mssql.objectExplorerV2 in the SQL Server container; 3 commands +
  view/title refresh. mainController: activateObjectExplorerV2 after
  classic OE init (classic untouched).
- TESTS (5, objectExplorerV2Shell.test.ts): codec round-trips w/ hostile
  identifiers + foreign-id rejection; factory hierarchy/ordering;
  readiness-synthesis honesty; capability context values; and the NO-V1
  TRIPWIRE — sinon spies on SqlToolsServiceClient.prototype.sendRequest +
  ConnectionManager.prototype.connect across every browse op, notCalled.

VERIFIED (2026-07-06): tsgo clean; repo build 0 errors; eslint clean (new
boundary clauses active); full suite 3554 passing / 12 pending / 0
failing (the intermittent copilotChatEntry flake absent this run — three
fully-green full runs today); gates 16/16 (run 2026-07-06T03-07-51Z_
610246b5: querystudio-query-10k 532.0–558.1ms official). Tree clean at
6ca6d805f.

NEXT: B18 / OE-B — data-plane connect + full catalog browse: session
registry (openSession "vscode-mssql-oe-v2", state machine incl. lost/
reconnect), metadata coordinator (server lease + lazy database leases;
pin once per expand; targeted refresh on store events), expansion rules
(Databases folder states table, database structural folders, object
folders via listObjects + groupBySchema, columns/keys/FKs/params
children), icons, explicit connect command, multi-db isolation +
no-v1 + readiness-UX tests over the fake data plane.

## 2026-07-06 — Entry 5: B18 / OE-B COMPLETE (connect + full catalog browse)

SHIPPED — vscode-mssql oe: 0640c3f35: OeV2SessionRegistry (explicit
data-plane connect, state machine, session-lost wiring, diag spans);
OeV2MetadataCoordinator (server + lazy per-database leases from the
SHARED store; pin-once; change-event-driven refresh); tree/oeV2Browse
(pure expansion rules: Databases states table w/ accessState + system
filter, structural folders, listObjects object folders + groupBySchema,
columns/keys/FKs/params children with badges + Key_PrimaryKey/UniqueKey/
ForeignKey + parameter direction icons; kind-exact object resolution;
stale paths = explicit errors); controller browse orchestration +
connect/disconnect/refreshNode lease routing + state-aware root nodes;
activation composition + connect/disconnect commands + capability-flag
context menus. 7 tests under standing no-v1 spies (setup/teardown
notCalled): catalog states, server-catalog failure honesty, folder/
object/schema browse, object children, MULTI-DATABASE ISOLATION, stale
object, disconnect lease release. 49 OE/metadata tests green targeted.

VERIFIED (2026-07-06): build 0 errors; suite 3558/12/1 (known
copilotChatEntry flake only); gates 16/16 (run 2026-07-06T03-59-29Z_
4a55b827). Tree clean at 0640c3f35.

DIRECTIVE UPDATE (Karl, mid-B18): after OE is fully validated end-to-end
+ metadata core solid, work through the REVISED remaining-tasks doc at
coding-docs/central_remaining_docs_review_pack/remaining_tasks.md
(stable task IDs, slices A–F) — implement all important high-pri items
autonomously one-by-one; defer big design changes, non-key items, and
central observability. Post-OE queue planned: QS-1 plan tabs → LS-10/11/
12 (→ OE2-6 script-as) → STS2-1 M7 verification+evidence (tag = human
gate) → STS2-3 maxCellBytes + QS-3 wide/blob → QS-2 grid decision record.

NEXT: B19 / OE-C — native commands + table preview: command router,
refresh/filter/clearFilters/search, copy name/qualified
(sqlIdentifierFormatter), mssql.queryStudio.newQueryFromContext (qs:) +
New Query wiring, SELECT TOP table preview into Query Studio (row-limit
setting, expectedDatabase, no SQL text in diagnostics), capability
menus, adversarial identifier tests, no-v1 spies.

## 2026-07-06 — Entry 6: B19 / OE-C COMPLETE (native commands + table preview)

SHIPPED — vscode-mssql qs: 8cb0c3402: mssql.queryStudio.newQueryFromContext
(doc created w/ initialSql; context queued by uri; on resolve the model
connects via NEW DocumentSessionBinding.connectToProfile — direct saved-
profile connect, no quick pick, optional database override — then
optionally auto-runs). stableProfileId() in profileAuthAdapter = the ONE
profile-id recipe (saved id, else deterministic derivation) shared by OE
nodes and QS.

SHIPPED — vscode-mssql oe: c7c181558: sqlIdentifierFormatter (bracketQuote
]-doubling, qualifiedName, selectTopSql clamp 1..100000 — the only SQL
composition point, adversarial-tested); oeV2NativeCommands (copyName/
copyQualifiedName via clipboard; per-folder in-memory name filter w/
honest "Filter: 'x' (N of M shown)" + no-matches notes + clearFilters;
database prefix search → quick pick → copy qualified name; New Query /
Script SELECT TOP / Preview Table Data (autoRun) via the qs: seam with
profile+database from the node; QS-disabled → honest guidance; command
events carry route+nodeKind, never SQL); controller folderFilters +
searchObjects; databaseNode gains canSearch; package.json 10 commands +
capability-flag menus. Tests: +4 (adversarial identifiers, clamping,
shared id recipe parity, filter/search flow) — 16 OE tests green under
standing no-v1 spies.

DEVIATIONS: search result action = copy qualified name (tree reveal
deferred); Select Top opens with SQL ready (no auto-run) while Preview
auto-runs (plan decision #4); filter is name-contains case-insensitive
(collation-aware filter = follow-up if dogfood asks).

VERIFIED (2026-07-06): build 0 errors; suite 3562/12/1 (known flake; 16
OE tests green targeted); gates 16/16 (run 2026-07-06T04-17-28Z_4f0b0e9e).
Trees clean at c7c181558.

NEXT: B20 / OE-D — explicit legacy handoff: oeV2ClassicHandoffService
(H1 lazy ConnectionManager.connect w/ generated owner URI + idle TTL +
first-use confirmation; H2 TreeNodeInfo adapter only for proven
commands), oeV2LegacyCommandPolicy table IN CODE, hide/guard unsupported,
handoff events, guardrail tests (handoff unreachable from browse;
failure isolation; disconnect closes handoff); fixture capture
opportunistic.

## 2026-07-06 — Entry 7: B20 / OE-D COMPLETE (explicit legacy handoff)

SHIPPED — vscode-mssql oe: 6087f103a: handoff service (H1 lazy classic
connect via injected seam, secret-free owner URIs, first-use confirmation
setting-gated, ONE handoff per v2 connection reused across features,
idle TTL 10min, close-on-disconnect, failure isolation, handoff +
legacyConnection.created events); H2 TreeNodeInfo adapter (server/
database/table only — identity hints, consumers guarded); policy table
IN CODE (backup/restore/profiler/schemaCompare/editTable; H1/H2 only,
NO H3 — invariant-tested); 'Legacy Actions…' quick pick command with
honest classic-route failure messages; disconnect closes handoff first;
mainController injects ConnectionManager as the seam (marked: handoff
door ONLY). 4 tests; 20 OE tests green; browse stays provably v1-free.

DEVIATIONS: classic NodeInfo fixture capture NOT taken (H2 adapter is
constructor-based, validated by tests + guarded at runtime; live-server
fixture capture folded into the MV ledger dogfood pass). H3 absent by
design until a command proves the need.

VERIFIED (2026-07-06): build 0 errors; suite 3566/12/1 (known flake);
gates 16/16 (run 2026-07-06T04-33-32Z_5a7226f9). Tree clean 6087f103a.

NEXT: B21 / OE-E — perf seam mssql.perf.objectExplorerV2Browse (oe:),
exploratory objectexplorerv2-browse scenario + eval config (perftest),
instrumentation/readiness close-out vs design §18, residuals → MV
ledger; then task #73 (revised remaining_tasks slices).

## 2026-07-06 — Entry 8: B21 / OE-E COMPLETE — OE v2 VALIDATED LIVE END-TO-END

SHIPPED — perftest (scenario commit) + vscode-mssql oe: ccb5c5ba2:
- mssql.perf.objectExplorerV2Browse (PERF_MODE only): connect provisioned
  profile → server catalog → RENDERED Databases; throws on every honesty
  failure so scenario noErrors is a real proof.
- perftest: provisionConnectionProfile driver step (provisioning half of
  queryStudioConnect extracted — saved profile + credential seed, no QS);
  objectexplorerv2-browse exploratory scenario in the eval config
  (standing gates now 20 reps). CLI 57/57.
- REAL BUG caught by the FIRST live run: group-less saved profiles
  (harness- and hand-written settings) were invisible at the v2 root —
  root level now includes them (classic parity). +1 regression test.

LIVE VALIDATION (run 2026-07-06T04-55-59Z_c0e19a30, 20/20 reps): 4/4
objectexplorerv2-browse passed — real STS2 service + real SQL Server:
data-plane connect + server-catalog hydration + Databases render =
338.0–415.8ms wallclock. Standing gates unaffected.

ACCEPTANCE GATES (design §18) at close-out:
✅ viewMode=v2Preview shows the v2 view (config-flip without reload)
✅ saved profile connects through ISqlConnectionService.openSession (live)
✅ activation/connect/expand/refresh/filter/search/table preview create
   no STS v1 state (lint boundaries + sinon spy suites + live noErrors)
✅ Databases folder from server catalog (live, accessState-aware)
✅ multi-database key-correct metadata (isolation tests)
✅ tables/views/procs/functions/synonyms/schemas render from metadata
✅ columns/params/PKs/FKs render where ready (badges, key kinds, pairs)
✅ refresh/filters/search/copy names/new QS query/table preview native
✅ unsupported = hidden or explicit; handoff only via 'Legacy Actions…'
   (policy table, confirmation, TTL, close-on-disconnect)
✅ status command shows data plane, registration, store status
✅ must-not-regress: classic OE untouched (suite green), QS data-plane
   behavior unchanged (gates in band all batches), provider behavior
   unchanged (golden parity 10/10), secrecy (canaries + hashed
   fingerprints)
Host-work perf targets (§15): unit-lane scale suite — 10k-object
hydration 148ms, listObjects(10201) 10ms, columns(1000) ~0ms; live
browse wallclock 338–416ms (backend-bound). 10k-object LIVE catalog
scenario deferred (needs a seeded large catalog — same disposition as
the metadata perf scenarios residual).

RESIDUALS → MV ledger + backlog: MV-11 human no-v1 browse smoke (spies
+ live scenario cover the automated bar); OE2-6 native Script-As (waits
LS-12); OE2-8 advanced SMO parity (demand-driven backlog); DC dedicated
OE page (spans flow to timeline already); default-flip decision
(D-freeze-10, Karl).

**OE v2 B15–B21 COMPLETE.** NEXT: task #73 — revised remaining_tasks
slices (QS-1 plan tabs → LS-10/11/12 → STS2-1 M7 verify+evidence →
STS2-3+QS-3 → QS-2 decision record).

## 2026-07-09 — Entry 9: Script as Execute for procedures (dogfood ask)

`emitExecute` reshaped to the classic SSMS block (DECLARE @RC int + one
DECLARE per parameter, `-- TODO: Set parameter values here.`, then
`EXECUTE @RC = schema.proc` with NAMED arguments + OUTPUT markers — named
args deliberately, they survive parameter reordering). OE v2 procedure
nodes get a `canScriptExecute` capability (oeV2Browse objectNode →
FLAG_ORDER → context value) surfacing "Script as Execute" in the Generate
Script submenu, gated `viewItem =~ /\boe2:canScriptExecute\b/`; command
`mssql.objectExplorerV2.scriptExecute` reuses scriptObjectFromContext
(controller.scriptObject widened to "execute" — the engine already
implemented the operation) and opens in Query Studio on the node's
connection. Golden updated in sqlScripting.test.ts. Commit 04dbe8fbf.

## 2026-07-10 — Entry 10: v1/SSMS parity phase planned (B22–B27)

CONTEXT: Karl directive (while dogfooding C2D): make OE v2 a UX drop-in
replacement for OE v1 — six areas: (K1) server-level metadata objects on
server-scoped connections only, org configurable via in-code metadata;
(K2) system-object display by database context (is_ms_shipped/system db);
(K3) SSMS-style ledger/temporal history organization, no empty folders;
(K4) extensible command registration + when-contexts, Backup/Restore first,
STS v1 connection-redirect seam (new registrations file, v1 untouched);
(K5) server groups: same dialog, arbitrary nesting, moveable connections;
(K6) v1 label recipe `server, database (auth)` + disambiguating tooltips.

DONE: three code surveys (classic OE label/groups/commands/TreeNodeInfo;
STS SmoTreeNodesDefinition.xml full hierarchy incl. system/ledger/ValidFor
mechanics; OE v2 seams). `OE_V1_PARITY_PLAN.md` authored — batches B22
(hierarchy registry + label parity), B23 (server-level aux catalog
sections), B24 (database-level parity + system rules + ledger/temporal
H8 facets), B25 (command registry + Backup/Restore redirect), B26 (groups
CRUD/move/DnD), B27 (connect-UX polish + perf + close-out). Decisions
P1–P8 recorded there; journal wins; Karl's future layout/command specs
land as registry data edits.

NEXT: B22 — tree/oeV2Hierarchy.ts registry + resolver, migrate existing
folders (byte-identical), v1 label/tooltip parity + tie disambiguation.

## 2026-07-10 — Entry 11: B22 / OE-F COMPLETE (hierarchy registry + label parity)

SHIPPED — vscode-mssql oe: f62d5a09b:
- tree/oeV2Hierarchy.ts: declarative layout registry (SmoTreeNodesDefinition
  analog) — OeV2FolderDef {id, label, scope, parentId, order, section,
  objectKinds/special, isSystemFolder, presence always|nonEmpty, sortLast,
  canFilter, validFor(facts)}; resolveFolders = the ONE visibility decision
  point (scope+parent, validFor, system-context strip, nonEmpty, sortLast
  tail); folderDef lookup; isSystemDatabaseName (STS rule). Existing
  Databases + six database folders migrated BYTE-IDENTICAL (tests prove
  order/labels/caps). Karl's future SSMS-layout spec = data edits here.
- tree/oeV2ConnectionLabel.ts (K6): pure copies of the classic recipes —
  connectionDisplayLabel (profileName wins, else `server, database (auth)`
  w/ <default>, SqlLogin→user, AzureMFA→email) + connectionTooltipLines
  (non-default props, classic order/wording, user dropped for MFA/
  Integrated) + disambiguationLines (Karl's addition: tied labels list
  differing props, defaults included, "(not set)" for absent).
- oeV2Path: OeV2ServerFolder/OeV2DatabaseFolder widened to open registry
  ids; folder segments percent-encoded so nested ids ("security/logins")
  round-trip; legacy encoded ids still decode (enc is identity on old ids).
- oeV2Browse: FOLDER_LABELS/KINDS/SECTION deleted — registry-driven;
  unknown folder id → explicit stale-folder error node; serverChildren/
  databaseChildren accept OeV2ScopeFacts (default {} = today's behavior).
- oeV2ProfileAdapter: displayName = v1 recipe (sort order follows);
  OeV2StoredProfile widened (email/port/version/applicationIntent/
  timeouts/alwaysEncrypted/replication) for tooltip facts.
- oeV2NodeFactory: connectionNode tooltip = v1 lines (+ additive live
  "Server Version:" when connected; + "Differs from same-named
  connections:" block for sibling ties computed in childrenOfGroup);
  description now carries STATE only (db/auth live in the label).
- Tests: +10 in objectExplorerV2Hierarchy.test.ts — registry order,
  synthetic-registry gate matrix (validFor/system/nonEmpty/sortLast/
  nesting), system-db names, nested-folder codec round-trip, LABEL PARITY
  PINNED against classic getConnectionDisplayName (5-case matrix),
  tooltip wording, disambiguation incl. factory-level sibling scoping.
  Shell test label expectation updated to the v1 recipe.

DEVIATIONS (deliberate, recorded):
- connectTimeout tooltip compares against the REAL default (30) — classic
  compared against a misspelled defaults key and always printed the line.
- Missing user under SqlLogin falls back to the auth type — classic
  printed "undefined" in the label.
- Missing authenticationType defaults to Integrated for the label.
- Disambiguation is SIBLING-scoped (same group level); cross-group ties
  unhandled until dogfood demands otherwise.
- Perftest live gates NOT run this batch: Karl is dogfooding on this
  machine and the batch is pure tree-layer (no data-plane/metadata/QS
  behavior change; unit suite at parity). Gates re-run at B23 (metadata
  touched) or next free window — same disposition as C2D Entry 7.

VERIFIED (2026-07-10): tsgo clean; repo build 0 error lines; eslint clean
(new files); full suite 4448 passing / 12 pending / 2 failing — BOTH the
documented pre-existing failures (sqlScripting CACHE-6 'drop',
sqlLanguage static sys.all_*); copilotChatEntry flake absent. Tree clean
at f62d5a09b.

NEXT: B23 / OE-G — perftest contracts vocabulary (auxCatalog.hydrate,
hierarchy.resolve, command.invoke, group.mutate), auxiliaryCatalog server
sections (qs:), Security/Server Objects folders + DB-scoped gate (oe:).

## 2026-07-10 — Entry 12: B23 / OE-G COMPLETE (server-level metadata objects)

SHIPPED — perftest core: 22e1988 (registry: metadataStore.auxCatalog
.hydrate/.refresh + objectExplorerV2.hierarchy.resolve/.command.invoke/
.group.mutate vocabulary in the family notes; contracts 27/27).
SHIPPED — vscode-mssql core: (vendored snapshot commit after 22e1988).
SHIPPED — vscode-mssql qs: 5adfdc8de:
- services/metadata/auxiliaryCatalog.ts: per-section lazy engine (ONE
  query per section, fetch on FIRST expand — never at connect, single-
  flight, per-section failure honesty failed≠empty, statusDump) +
  SERVER_AUX_SECTIONS (10): logins (S/U/G/C/K, ##% excluded, disabled
  badge), serverRoles (fixed=system), credentials, cryptoProviders,
  serverAudits + auditSpecifications (disabled when not enabled),
  endpoints (id<65536=system), linkedServers, serverTriggers, user
  errorMessages (ids only — message TEXT stays out; worksheet #4 answer).
- ServerMetadataService owns the aux engine (same session source, one
  change stream); ServerCatalogLease.auxiliary surfaces it.
- 6 tests: lazy-by-construction (server hydration runs ZERO aux queries),
  demand fetch + warm cache, single-flight, failure honesty, unknown-key
  rejection, change stream + statusDump.
SHIPPED — vscode-mssql oe: 7e3544b4c (see commit message; registry
entries in STS order, K1 database-scoped gate, Azure ValidFor mirror,
serverObject leaf nodes w/ classic icons + _Disabled variants,
serverObjectItem codec kind, coordinator ensureAuxSection, controller
lazy-hydrate + per-section refresh, serverScopeFacts). +7 pure tests.

DEVIATIONS:
- isAzure detection = engineEdition "5" or /azure/i on the live server
  facts (post-connect); pre-connect the folders render optimistically for
  server-scoped profiles and correct on facts arrival.
- Error Messages = user messages (id>50000), id-only labels (privacy).
- Perftest live gates again deferred (Karl dogfooding; aux catalog is
  lazy + off the QS hot path — DocumentSessionBinding/database-catalog
  paths untouched). Run at next free harness window with B22's.

VERIFIED (2026-07-10): tsgo clean; repo build 0 error lines; eslint 0
errors; full suite 4458 passing / 12 pending / 2 known pre-existing
failures (+ flake variance). OE+aux targeted: 51 green under standing
no-v1 spies. Trees clean: perftest 22e1988, vscode-mssql 7e3544b4c.

NEXT: B24 / OE-H — database aux sections (Security/Service Broker/
Storage/Programmability), H8 tableFacets (goldens untouched),
is_ms_shipped on H2, K2 system gate, K3 ledger/temporal organization
(history nested under parent, Dropped Ledger nonEmpty+sortLast).

## 2026-07-10 — Entry 13: B24 / OE-H COMPLETE (database parity + system rules + ledger/temporal)

SHIPPED — vscode-mssql qs: 20c33d407: auxiliaryCatalogDatabaseSections.ts
(30 lazy sections: Security users/roles/keys/certs/credentials/audit/
policies/CMK+CEK, Service Broker x6 w/ system flags, Storage x7,
Programmability triggers/assemblies/sequences/types x3; systemObjects
is_ms_shipped=1 kept OUT of H2 — K2 without touching completions/goldens;
tableFacets/viewFacets via COL_LENGTH-probed sp_executesql — one query
2016→2022+, older servers fail the section and browse renders flat).
AuxCatalogItem widened (schema/kind/objectId/facts). Store: per-database
AuxiliaryCatalog on a DEDICATED key-correct session (one-active-query
collision rule — server aux moved to dedicated session too);
DatabaseCatalogLease.auxiliary; aux ticks ride entry status listeners.

SHIPPED — vscode-mssql oe: eaa7c4bbf: full SSMS database layout in the
registry (Tables/Views w/ System* [K2] + Dropped Ledger* [K3 nonEmpty,
sortLast], Synonyms, Programmability [SPs +System, Functions, Database
Triggers, Assemblies, Types, Sequences], Service Broker [Azure-hidden],
Storage, Security [Users, Roles, Schemas MOVED under Security per SSMS,
keys/certs/credentials/audit/policies/Always Encrypted]). Browse: mixed
folder content (subfolders-before-items, sortLast after — STS
SortPriority parity); facet exclusions (temporal/ledger history +
dropped rows never in main list), SSMS suffixes + subtype icons, history
table NESTED under parent (before child folders, HistoryTable icon);
dropped-ledger folders only when rows exist; aux leaves w/ honesty +
disabled badges + K2 hideSystemItems; databaseObjectItem codec kind.
Controller: per-folder lazy aux ensure, database facts, history lookup,
per-section refresh.

DEVIATIONS (recorded): External Resources folder deferred (needs version
facts plumbing; not in Karl's list). Master Keys / Database Encryption
Keys folders folded into Symmetric Keys listing (## keys; DEK needs VIEW
SERVER STATE) until asked. Functions subfolders (TVF/Scalar/Aggregate/
System) deferred — flat merged list as before. System Functions folder
deferred with them. Ledger-view "(Ledger View)" suffix deferred. System
objects render browse-shallow (no column expansion — metadata not
hydrated for MS-shipped objects; SSMS-deep on demand later). Facets are
progressive: first Tables expand may render flat, re-renders when facets
land (journaled honesty trade).

VERIFIED (2026-07-10): tsgo clean; eslint 0 errors; repo build 0 error
lines; full suite 4464 passing / 12 pending / 2 known pre-existing
failures (+flake variance); 57 OE+aux tests green under standing no-v1
spies. Tree clean at eaa7c4bbf.

NEXT: B25 / OE-I — oeV2CommandRegistry + commandTargetFor + generated
menu contributions + oeV2LegacyRedirect; Backup (database nodes +
DB-scoped connections) + Restore (servers + databases); Legacy Actions
reroutes through the library.

## 2026-07-10 — Entry 14: B25 / OE-I COMPLETE (command registry + Backup/Restore redirect)

SHIPPED — vscode-mssql oe: (see commit "command registry + Backup/Restore
via the v1 redirect library (B25)"): oeV2CommandRegistry (declarative
defs, oe2:cmd context flags, generated+conformance-tested package.json
menus, commandTargetFor extraction contract), oeV2LegacyRedirect (the ONE
legacy launch path over the handoff service; DB-scoped connections adapt
AS their database; defense-in-depth refusals; command.invoke events),
Backup on database nodes + DB-scoped top-level connections, Restore on
servers + databases, Legacy Actions quick pick rerouted. +11 tests.

DEVIATIONS: none beyond plan. K4 satisfied: v1 registrations untouched;
handlers unchanged; adding a command = one registry entry + one policy
row + generated manifest entries.

VERIFIED (2026-07-10): tsgo clean; eslint 0 errors; suite 4478/12/2
(known pre-existing only); 62 OE tests green under no-v1 spies.

NEXT: B26 / OE-J — groups CRUD/move/DnD + view-title New Connection
button (Karl 2026-07-10: shared classic connection dialog, no new UI;
button on both views; v2 re-renders via config watcher).

## 2026-07-10 — Entry 15: B26 / OE-J COMPLETE (groups CRUD/move/DnD + title buttons)

SHIPPED — vscode-mssql oe: (commit "group CRUD/move/drag-drop + New
Connection title button (B26)"). K5 satisfied via classic-dialog +
shared-ConnectionConfig reuse (plan decision P5); v2 DnD with cycle
guard; Move to Group quick pick; view-title Add Connection + New Group
buttons; the connect-them-both rule = single-new-profile auto-connect on
mssql.connections changes (Karl 2026-07-10: one dialog, both views,
connect in both when v2 enabled — bulk-edit imports excluded, journaled
heuristic). Group-node context create currently opens the dialog at root
(nesting via DnD/move) — dialog has no parent picker; deviation noted.
+6 tests. Suite 4484/12/2 (known pre-existing only).

NEXT: B27 / OE-K — connect-UX polish (cached-metadata indicator, slow-
connect surfacing), perftest scenarios (server-security expand, aux
hydration) + the DEFERRED B22–B26 gate regression runs (machine now
free), acceptance checklist vs K1–K6, memory close-out.

## 2026-07-10 — Entry 16: B27 / OE-K COMPLETE — v1/SSMS PARITY PHASE (B22–B27) DONE

SHIPPED — vscode-mssql oe: "connect-UX polish + security-expand perf
probe (B27)": slow-connect elapsed ("connecting… (Ns)" past 5s, 2s live
tick while opening/closing), connecting nodes spin (loading~spin),
mssql.perf.objectExplorerV2SecurityExpand honesty probe.
SHIPPED — perftest 94ea2e8 + 0a6a594 (+ config commit):
objectexplorerv2-security-expand scenario in the eval gates;
provisionConnectionProfile gains serverScoped (a DB-scoped profile
correctly hides Security per K1 — the FIRST live run caught exactly that
gate working); examples/config.oe.local.jsonc for OE-focused runs.

LIVE VALIDATION (2026-07-10):
- Full gates run 2026-07-10T18-55-04Z_4b5dee0b: 32/32 valid reps passed —
  standing QS gates in band (querystudio-query-10k 837–1424ms official,
  wide/blob/open/cache/query-10k all passed), objectexplorerv2-browse
  328–400ms (historical band 338–416ms) — the DEFERRED B22–B24 gate
  regression proof. (security-expand invalid that run: harness loaded the
  18:16 dist bundle predating B25–B27 — found via 'command not found',
  fixed by rebundling; fix knowledge: gates exercise dist/extension.js,
  NOT out/ — rebundle before gating new commands.)
- OE-focused run 2026-07-10T19-06-35Z_bbf1e29d: security-expand 3/3
  official reps 406.1–416.0ms (connect + Security expand + lazy logins
  hydration); browse 335–398ms. Warmup rep-0 on both: cold-start
  "data-plane connect failed" flake (official reps unaffected; known
  disposition — first window after teardown).

ACCEPTANCE vs Karl's six points (2026-07-10 directive):
✅ K1 server-level objects: Security (6 leaves) + Server Objects (4)
   lazy aux sections, server-scoped connections only (live-proven both
   ways: DB-scoped profile hides them; server-scoped hydrates logins in
   ~410ms end-to-end incl. connect). Organization = one in-code registry.
✅ K2 system data: system db → System Databases/Tables/Views/SPs folders
   + system objects (aux systemObjects section, is_ms_shipped kept OUT of
   H2 — completions/goldens untouched); user db → none.
✅ K3 ledger/temporal: history tables nested under parents, main lists
   exclude history/dropped rows, SSMS suffixes + subtype icons, Dropped
   Ledger folders ONLY when rows exist (fixture-tested matrix).
✅ K4 commands: oeV2CommandRegistry (declarative, conformance-tested
   manifest) + oeV2LegacyRedirect over the handoff service; Backup on
   database nodes + DB-scoped connections, Restore on servers+databases;
   v1 registrations byte-untouched.
✅ K5 groups: classic dialog reuse, delete w/ contents modal, Move to
   Group, v2 DnD w/ cycle guard, arbitrary nesting (storage supports it
   natively); Add Connection + New Group title buttons; connect-them-both
   single-new-profile rule.
✅ K6 labels: v1 recipe pinned against the classic function; rich
   tooltip; tie disambiguation.
✅ K-cross: fast (lazy everything, dedicated aux sessions), no-v1 spies
   standing, spinner/elapsed connect UX, showStatus lantern, node→handler
   extraction contract (commandTargetFor).

RESIDUALS/BACKLOG (dispositioned): Karl's SSMS-walkthrough layout spec →
registry data edits when it lands; External Resources folder + Functions
subfolders (TVF/Scalar/Aggregate/System) + Master/DEK folders deferred;
system objects browse-shallow; group-create-from-group opens at root
(dialog lacks parent picker); scenario promotion exploratory→standing
after baseline history accrues; cross-view DnD (worksheet #6).

VERIFIED FINAL: vscode-mssql suite 4484/12/2 (documented pre-existing
only); perftest CLI 93 passing (+central-store env suite needs the
localhost,14333 container); contracts 27/27; all trees committed clean.

**OE v1/SSMS PARITY PHASE B22–B27 COMPLETE.** Commits: vscode-mssql
f62d5a09b, 5adfdc8de, 7e3544b4c, 20c33d407, eaa7c4bbf, 33f2d0380,
7bb92711a, B27-oe; perftest 22e1988, 94ea2e8, 0a6a594 (+config).

## 2026-07-10 — Entry 17: async expansion hardening (Karl dogfood round 2)

CONTEXT: screens/oe-async.png — a sleeping serverless Azure connection
stalled ANOTHER connection's Tables expand indefinitely; VS Code renders
a hung getChildren as expanded-NOTHING (no spinner, no error).

SHIPPED — vscode-mssql qs: f0acfd0ee (per-server validation limiter —
the store-wide 2-slot digest semaphore let one sleeping server starve
every other server's requireValidated waits; now scoped per fingerprint)
+ oe: 55d887bc8 (children() hardened: thrown expansions → explicit error
child; expandable-with-zero-children → "(No items)" tripwire, silent
empty impossible; ALL awaited expansion dependencies bounded — freshness/
lease 6s, first-expand connect kick 400ms w/ spinner + change-stream
re-render; bounds injectable via deps.waits). +4 tests (stalled-folder
loading within bound, cross-connection independence, sleeping-connect
spinner, silent-empty tripwire). Karl's contract satisfied: parallel
across connections, serialized-per-connection at the session layer,
spin-or-fail-never-empty.

NOTE: exact lower-layer stall (suspected: lease/session work queued
behind the serverless resume below the 5s policy race) is now bounded
away at the tree edge regardless of culprit; if the spinner-forever case
shows up in dogfood, the next probe is STS2-side connectionOpen dispatch.
