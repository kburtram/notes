# TypeScript Query Endpoint — Execution Plan

**Started:** 2026-07-13
**Working tree:** `C:\repos\test\langsrv` (vscode-mssql, sqltoolsservice, perftest on `dev/query`; separate from the `C:\repos\test` checkout — merge later)
**Normative specs (in precedence order):**
1. `../typescript_query_endpoint_addendum.md` (TSQ2 addendum — wins on conflict)
2. `../querystudio_web_backend_addendum.md` §3 (shared provider contract, WEB2-1/2)
3. `../typescript_query_endpoint.md` (base design)
4. `../querystudio_web_backend.md` (context for sts2-remote workability)

**Conventions:** commit prefix `tsq2:`; shared-foundation commits that also serve the web backend use `dp:` (data plane). Journal in `PROGRESS.md` — the journal wins over this plan when they disagree. Specs may be adapted during validation; every divergence gets a Decision-log entry here and a journal entry there.

## Code basis at start

| Repo | Branch | Head |
| --- | --- | --- |
| vscode-mssql | dev/query | `37396c3c44` |
| sqltoolsservice | dev/query | `88c6149bce` |
| perftest | dev/query | `83e017b95e` |

Confirmed at start: `services/sqlDataPlane/` still has only `api.ts`, `fakeBackend.ts`, `sqlDataPlaneService.ts`, `vscodeSqlTokenSource.ts` — the shared registry (WEB2-1/2) has NOT landed anywhere; this build implements it once, shared with the future `sts2-remote`.

## Environment / commands

- Node v24.17.0, npm 11.13 (tedious v20 requires Node ≥ 22 — satisfied).
- Install: `npm install` at `vscode-mssql/` root (bootstraps extension targets via postinstall).
- Build extension: `npm run build` in `extensions/mssql` (typecheck via tsgo + emit via tsc + bundles); watch variants exist.
- Unit tests: `npm test` in `extensions/mssql` runs `vscode-test --coverage` (whole suite in a VS Code host). Investigate a filtered/fast lane during FOUND-1 — engine tests (tsNative) must also run under plain mocha/node with no vscode import so the inner loop is fast.
- Live SQL lanes: `STS2_SQLSERVER_CONNSTRING` (local SQL 2025), `STS2_AZURESQLSERVER_CONNSTRING`, `STS2_AZURESQLSERVER_ENTRAID_CONNSTRING`. Skip-not-fail when unset.
- perftest: `perftest` CLI in `perftest/packages/perftest-cli`; scenario registry `src/scenarios/registry.ts`; per-scenario `userSettings` land pre-launch (the backend-selection seam).

## Work packages (tracked as session tasks #1–#17)

| # | Package | Spec anchor | Gate |
| --- | --- | --- | --- |
| 1 | TSQ2-0 dependency/packaging spike | §2.2, §2.9, §4 | lazy load proven; provenance recorded |
| 2 | FOUND-1 shared registry/identity | web §3.1–3.2 | existing suites green on new registry |
| 3 | FOUND-2 capability/error/acceptance | web §3.3–3.5 | fake + STS2 pass expanded conformance |
| 4 | TSQ2-2 driver port + fake | §5.2–5.3, §11 | engine tests run without tedious/vscode |
| 5 | TSQ2-3 tedious adapter | §5.3, §5.5 | live open/close + failure matrix |
| 6 | TSQ2-4 lifecycle + ledger | §2.4–2.5, §5.4/5.6/5.10 | N3 scalar fixtures + §13.3 events |
| 7 | TSQ2-5 paging/backpressure | §5.7–5.13 | full N3 lifecycle/backpressure |
| 8 | TSQ2-6 exact cells + fail-closed | §6 | golden parity green; unsupported fails pre-rows |
| 9 | TSQ2-7 Entra auth | §7 | Entra lane + canaries |
| 10 | TSQ2-8 observability/capsule/console | §9–10 | capsule replay of injected race |
| 11 | TSQ2-9 capability UX/routing | §8 | fallback + runtime denial flows |
| 12 | TSQ2-10 vector | §6.8 | fixtures or capability stays off |
| 13 | TSQ2-11 spatial | §6.9 | fixtures + curve policy or off |
| 14 | TSQ2-12 perf treatments | §12 | same-scenario multi-treatment report |
| 15 | TSQ2-13 consumers | §14 TSQ2-13 | scoped consumers on native |
| 16 | TSQ2-14 soak/VSIX/preview | §13, §17.1 | preview checklist |
| 17 | TSQ2-15 GA gate (future) | §17.2 | blocked on preview data |

Execution order: 1 → 2 → 3 → 4 → (5 ∥ continue engine on fake) → 6 → 7 → 8 → 9 → 10..13 as parallel tracks → 14 → 15 → 16. TSQ2-U* upstream tedious items are tracked in the journal when opened.

## Delivery rules (addendum §15, enforced per commit)

Every task: code + focused tests, lifecycle/fault tests, instrumentation contract updates, privacy canaries, packaging evidence when deps change, decision-log entry for divergences, before/after perf evidence for hot paths, status/capsule updates for new state.

Forbidden (release-blocking if found): top-level tedious import in activation graph; silent numeric/temporal precision loss; automatic SQL rerun on provider switch; unbounded queues; request timeout as sole deadline; leaked listeners/timers; raw tedious errors as contract; capability claims without green fixtures; fault/lossy overrides in official perf runs.

## Decision log

| # | Date | Decision | Rationale / spec ref |
| --- | --- | --- | --- |
| D1 | 2026-07-13 | Backend kind string is `ts-native`; identity tuple per web §3.1 (`implementation: ts-native`, `transport: inprocess`, `driver: tedious`, `deployment: extension-local`, `realmId: local`). | Addendum §16 Q1 default accepted. |
| D2 | 2026-07-13 | Exact mode fail-closed is the default for decimal/numeric/money/datetimeoffset; lossy preview only behind debug override. Base-design P1/P2 superseded. | Addendum §2.8/§6.3 (MUST-level). |
| D3 | 2026-07-13 | Shared foundation implemented once in `services/sqlDataPlane` under `dp:` commits so `sts2-remote` reuses it verbatim. | Web addendum §3 preamble; TSQ2 §2.10/§3.5. |
| D4 | 2026-07-13 | Comparison baseline is the pinned SqlClient in this sqltoolsservice tree (verify exact version during FOUND-1), not SqlClient 7.0. | Addendum §2.1. |

| D5 | 2026-07-13 | `mssql.sqlDataPlane.showStatus` becomes fully passive (no backend construction). Explicit start happens only via real feature use (openSession). | Web §3.2 "passive status never constructs"; supersedes current command behavior. |
| D6 | 2026-07-13 | Packaging: dedicated esbuild **minified** provider chunk `dist/tsNativeProvider.js` (own entry point, like vectorAnalysisWorker), loaded via computed-path require on first selection. Evidence: unbundled require('tedious') = 1627 ms / +15.1 MiB heap; minified bundle = 176 ms / +8.2 MiB; bundle size 1.5 MB. tedious pinned exactly `20.0.0` (lockfile committed; Node v24.17.0; engines node>=22 ok). | Addendum §2.2/§2.9/§4.3 option 3. |

(Add entries as decisions are made; never edit past entries.)
