# Docker (Local Containers) in OE v2 — review + integration design

Status: **IMPLEMENTED** (2026-07-16, DOCK-0..6). Shipped as vscode-mssql
f37efaf2b + perftest 8cc093b; both container perftest scenarios pass live
(deploy 16.3s, reconnect 6.99s). See oe-docs/PROGRESS.md Entry 19 for the
build, the three live-found fixes (esp. the running≠ready pre-login open
retry), and the stale-bundle process note. Original design below.

Status (original): **DESIGN FOR REVIEW** (2026-07-16). Requested by Karl: "fully review how
the OE v1 docker container node type works, design how to integrate the same
functionality in OE v2 in the best way — fully reliable, testable, observable,
performant, using all the new connection support, but with the same UX. Either
rebuild if needed, or integrate if it's solid."

## 0. Verdict up front

**Reuse the docker orchestration core as-is behind three narrow seams. Do not
rebuild it.** The engine layer is genuinely connection-agnostic, has ~1,750 LOC
of unit tests, and already serves a second consumer (the DAB container feature)
— the best evidence it isn't entangled with v1 connections. What v1-couples the
feature is concentrated in three places (connect step, ensure-started hook,
loading-label leak), each of which wants a small interface, not a rewrite.
What the subsystem genuinely lacks — and what we add regardless — is
observability: it has telemetry events but **zero diag spans, no Debug Console
presence, and no perftest scenarios**.

## 1. What exists today (v1 map)

### Engine core (connection-agnostic — REUSE)
- `src/docker/dockerodeClient.ts` (20 LOC) — lazy `Dockerode` singleton.
- `src/docker/dockerUtils.ts` (877 LOC) — hybrid CLI/dockerode layer:
  environment probes (`docker --version`, `docker info`, engine switch,
  Docker Desktop launch + 2s×30 poll) via `child_process.spawn`
  (`execDockerCommand`, `fixPath()` for macOS/Linux GUI PATH); container
  lifecycle (create/start/stop/remove/inspect/logs/pull, `findAvailablePort`,
  `startContainerLogMonitor`) via dockerode. Failures return
  `DockerCommandParams { success, error?, fullErrorText? }`, error text
  scrubbed of `SA_PASSWORD` (`sanitizeErrorText`).
- `src/deployment/sqlServerContainer.ts` (392 LOC) — SQL-specific steps:
  MCR tag list → year versions, `startSqlServerDockerContainer` (ACCEPT_EULA +
  SA_PASSWORD env, port binding → 1433/tcp), readiness = log-stream
  `waitForMatch("SQL Server is now ready for client connections", 300s)`,
  `restartSqlServerContainer`, `validateSqlServerPassword` (8-128, 3/4 classes).
- Tests: `dockerUtilities.test.ts` (958), `sqlContainer.test.ts` (456),
  `localContainersHelpers.test.ts` (332).

### Wizard + wiring (v1-coupled at the edges)
- Entry: OE v1 toolbar `mssql.deployNewDatabase` (`view/title`, view ==
  objectExplorer) → `DeploymentWebviewController(context, MainController,
  group?)`; deployment type `LocalContainers` = the docker wizard.
- Step engine: `DockerStepOrder` 0-6 (checkInstall → startDocker →
  checkEngine → pullImage → createContainer → readiness → connect), reducers
  in `localContainersHelpers.ts` (433 LOC), React pages under
  `webviews/pages/Deployment/LocalContainers/` (~970 LOC). The step engine is
  a plain state machine; only the LAST step and the group options touch v1.
- The connect seam: `addContainerConnection` (~25 lines) —
  `connectionUI.saveProfile(profile)` (settings.json + SecretStorage) then
  `mainController.createObjectExplorerSession(profile)` (v1 OE session).
- Profile marking: saved profile carries `containerName` + `version`; plus
  `connectionManager.checkForDockerConnection` back-fills `containerName` on
  any connect whose `serverInfo.machineName` matches a container id (auto-
  upgrades hand-written localhost profiles into docker nodes).
- v1 rendering: `ConnectionNode.subType` docker variants (red/green docker
  icons), context menu group `9_MSSQL_container` (Start/Stop/Delete
  Container), `loadingLabel` spinner text via `objectExplorerService.
  setLoadingUiForNode`, and the expand-while-stopped hook:
  `prepareConnectionProfile` → `restartSqlServerContainer` (starts Docker
  Desktop + container + readiness before the session opens; offers node
  removal if the container vanished).

### The three v1 couplings (and only these)
| # | Coupling | Seam to cut |
|---|----------|-------------|
| 1 | `addContainerConnection` → `connectionUI.saveProfile` + `createObjectExplorerSession` | `ContainerConnectAdapter { saveProfile(profile): Promise<connectionId>; connect(connectionId): Promise<boolean> }` — v1 impl wraps today's calls; v2 impl writes the same settings.json shape then `OeV2TreeController.connectProfile` |
| 2 | Expand-while-stopped + docker detection live inside v1 `objectExplorerService` / `connectionManager` | v2 pre-connect hook (see §3.2) calling the SAME pure helpers |
| 3 | `startDocker` / `prepareForDockerContainerCommand` / `restartSqlServerContainer` take `ConnectionNode` + `ObjectExplorerService` ONLY to set spinner text | `ContainerProgressReporter { setStatus(text?): void }` — v1 adapts `setLoadingUiForNode`, v2 adapts its tree description/busy state |

## 2. Design decision

**Integrate, don't rebuild.** One shared docker/deployment core, two thin
front-ends (v1 stays untouched; v2 gets adapters). The wizard webview is kept
(same UX, same pages) and parameterized by a connect adapter — NOT forked.
Rebuilding the wizard or engine would re-earn ~2,600 LOC of behavior (engine
quirks: PATH repair, engine-type switch, Rosetta check, socket permissions,
port scanning) that is already tested and battle-hardened, for zero UX gain.

## 3. v2 integration plan (checkpoints DOCK-0..6)

### DOCK-0 — seams in the shared core (no behavior change)
- Add `ContainerProgressReporter` and thread it through `startDocker`,
  `prepareForDockerContainerCommand`, `restartSqlServerContainer`; delete the
  `ConnectionNode`/`ObjectExplorerService` imports from `dockerUtils` /
  `sqlServerContainer`. v1 call sites pass an adapter over
  `setLoadingUiForNode` (byte-identical UX).
- Add `ContainerConnectAdapter`; `DeploymentWebviewController` takes it (plus
  a `ConnectionGroupOptionsSource`) instead of reaching into
  `MainController` for the final step. v1 impl = today's two calls.
- Exit gate: existing docker suites green untouched; no v1 UX change.

### DOCK-1 — v2 entry point
- `mssql.objectExplorerV2.deployNewDatabase` on the v2 view/title menu (same
  icon as v1's), opening the SAME `DeploymentWebviewController` with the
  **v2 connect adapter**: persist profile via `ConnectionConfig` (identical
  settings.json shape — `containerName`/`version` props; password via the
  same credential store the v2 profile adapter already reads), then
  `controller.connectProfile(stableProfileId(profile))`. The wizard is
  unchanged pixel-for-pixel.

### DOCK-2 — v2 node identity + commands
- `OeV2StoredProfile` already carries `containerName`/`port`/`version` and
  the tooltip already renders them. Add:
  - node facts: `isContainer` (containerName present) → icons
    `DockerContainer_green/red` (same assets), `oe2:cmd=` flags
    `startContainer` / `stopContainer` / `deleteContainer` via the command
    registry (v1 wording: "Start Container", "Stop Container", "Delete
    Container"; same node-state targeting as v1's subType gates: start on
    disconnected, stop on connected, delete on both).
  - handlers in the registry loop (route "native"): call the shared helpers
    (`prepareForDockerContainerCommand`, `stopContainer`, `deleteContainer`)
    with a v2 progress reporter (tree `description` + busy spinner via the
    existing connecting ticker), then `connectProfile`/`disconnect` and a
    profile-tree refresh. Delete confirms modally (v1 parity) and offers
    profile removal.
- Container state polling: NONE (v1 has none either) — state is derived at
  command time and from connect outcomes. Cheap `isDockerContainerRunning`
  check piggy-backs on node expand only.

### DOCK-3 — ensure-started pre-flight (the v1 magic moment)
- In `OeV2TreeController.connectProfile`, BEFORE `prepareConnection`:
  if the profile has `containerName` and the data plane can't reach the
  server, run `restartSqlServerContainer(containerName, reporter)` (Docker
  Desktop launch → container start → readiness log wait), then proceed to
  the normal v2 open. Bound the whole pre-flight with its own deadline
  (default 90s, well inside the 300s readiness cap) and surface honest
  failure text on the node (`failureReason`) — never an infinite spinner
  (the OE v2 connect-hang fix set that precedent).
- Post-connect: v2 equivalent of `checkForDockerConnection` — when
  `session.info` machineName matches a container id, back-fill
  `containerName` into the stored profile (same auto-upgrade as v1).

### DOCK-4 — observability (new, both stacks benefit)
- Diag spans in the SHARED core (feature `deployment`):
  `docker.step` (step name + outcome + ms — mirrors the existing
  RunDockerStep telemetry), `docker.engine.start`, `docker.container.start|
  stop|delete|create`, `docker.image.pull` (bytes/duration),
  `docker.readiness.wait` (ms, outcome), `objectExplorerV2.container.preflight`
  (DOCK-3 wrapper). Value-free: names/ports only, never passwords (the
  sanitize layer already guarantees this).
- Debug Console: the spans surface in the existing session journal + a
  "Containers" row in the OE v2 status dump (`showStatus`): per-container
  profile → last known state/outcome.
- perftest: two scenarios — `container-deploy` (wizard steps end-to-end
  against local Docker, gated on docker availability like live-SQL gates) and
  `container-reconnect` (stopped container → expand → preflight → ready).
  Report wallclock + per-step breakdown; A/B v1 vs v2 entry once DOCK-3 lands.

### DOCK-5 — tests
- Unit: adapter seams (fake docker layer — the existing test doubles pattern
  in `dockerUtilities.test.ts` transfers); v2 command targeting matrix
  (registry conformance already pins package.json); preflight state machine
  (stopped→starting→ready→open; docker-missing → honest failure; container
  deleted → offer removal path).
- The no-v1 tripwires stay green: the v2 path never touches
  `ConnectionManager.connect` / classic OE RPCs (the connect adapter uses the
  data plane; only the WIZARD's profile-save writes shared settings).

### DOCK-6 — exit gate / parity checklist
- Same UX end-to-end: toolbar button → wizard → auto-connected green docker
  node in the v2 tree; stop/start/delete with v1 wording; expand-while-
  stopped transparently restarts; VS Code restart re-materializes a red
  docker node; stale container offers cleanup.
- v1 remains fully functional off the same shared core.

## 4. Risks / open questions for review
1. **Wizard group options** come from `connectionUI.getConnectionGroupOptions`
   — v2 adapter can read the same `ConnectionConfig`; low risk.
2. **Entra/localhost auth**: container connections are SQL-login only (sa) —
   no capability-fallback interaction expected; the v2 opener handles
   sqlLogin natively.
3. **`checkForDockerConnection` parity** needs `machineName` from the v2
   session info — verify sts2/ts-native expose it; if not, defer the
   auto-upgrade (DOCK-3 note) and keep explicit `containerName` marking only.
4. **Shared wizard regression risk** on v1: DOCK-0 is deliberately
   refactor-only with the existing suites as the gate.

## 5. Estimate
DOCK-0 ~1 day; DOCK-1/2 ~1-1.5 days; DOCK-3 ~1 day; DOCK-4 ~0.5-1 day;
DOCK-5/6 ~1 day. Total ≈ a focused week, dominated by seam refactors and the
preflight state machine — no new docker engine code.
