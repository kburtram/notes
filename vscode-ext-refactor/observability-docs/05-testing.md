# 05 — Testing & Verification

**Updated: 2026-07-03.** What is tested where, how to run it, and the
reliability lessons baked into the suites.

## 1. Test inventory

### vscode-mssql extension unit suite
Run: `cd vscode-mssql/extensions/mssql && npx tsc -p tsconfig.extension.json --noCheck && npx vscode-test`
(mocha TDD + sinon + chai, compiled to `out/`). Current: **3269 passing / 12
pending / 1 known flake** (see §3).

Debug-console-relevant files (`test/unit/`):

| File | Covers |
|---|---|
| `debugConsoleRedaction.test.ts` | classify() policies per capture mode, secret/SQL-text exclusion, redactedFields accounting |
| `debugConsoleAnalysis.test.ts` | store queries, overview/waterfall/critical-path derivations, viewer-internal exclusion, session store behavior |
| `debugConsoleTraceFilter.test.ts` | filter expression language (durations, aliases, invalid-token surfacing), store duration filters, PerfModeSink forwarding (legacy perfMarker + additive rpc/webview/sts, viewer-internal/unrelated exclusion) |
| `perfHistoryProvider.test.ts` | directory indexing (cold/warm, fingerprints, chunked scan), suite grouping, scenario details, `deleteRun` (directory removal, index eviction + persisted reload, path-trick rejection) |
| `selfTestConnectionString.test.ts` | env connstring parsing (never-log invariants) |

### perftest in-proc suite
Run: `cd perftest/packages/perftest-inproc && npx vitest run` (vscode alias
stub). Current: **12/12** — runner rep-loop semantics, first-rep
any-failure abort, cancellation interrupting a 60s wait in <3s, marker bus
timeout diagnostics, metric extraction.

### perftest harness suites
See `perftest/docs/RUNNING_TESTS.md` (authoritative): contracts/validator
tests, store tests, scenario smoke, doctor. Non-regression pair used
throughout this build:

```powershell
node packages/perftest-cli/dist/cli.js run --config examples/config.sql.local.jsonc --scenario query-10k-results
node packages/perftest-cli/dist/cli.js run --config examples/config.phase3.local.jsonc --scenario debug-console-smoke
```

### sqltoolsservice
Build gate: `dotnet build src/Microsoft.SqlTools.ServiceLayer/Microsoft.SqlTools.ServiceLayer.csproj`.
STS2 has its own engine/mutation test program (`docs/sts2/ENGINE-TESTS.md`,
Stryker) — owned by that workstream.

## 2. Reliability playbook (lessons already paid for)

- **OE**: use awaited `provider.expandNode(node, sessionId)` — never poll
  `getChildren` + "Loading…" (requires a visible tree). Server-level
  sessions (`database:""`) for Databases-folder access; system DBs live
  under the "System Databases" folder — search both levels.
- **Cancellation**: every wait polls `isCancelled` (200ms); sleeps are
  cancellable; first-rep failure aborts remaining reps (fail fast, same
  outcome expected).
- **Cleanup**: `deferCleanup` runs session/editor disposal even on
  failure/cancel; designer restore prompts suppressed for self-test
  sessions (applicationName prefix) so runs never block on modals.
- **Determinism in tests**: deterministic cancel points (not race-prone
  timings); virtualized-table tests assert fixed row heights/column widths.
- **Self-noise**: assertions exist that viewer-internal events stay out of
  live pushes, stores, forwarding, and rep markers.

## 3. Known issues

- **`copilotChatEntry.test.ts` hook timeout** — PRE-EXISTING flake
  (sync require hook timing out under host load; ~50% across runs,
  independent of diagnostics changes; Copilot-team-owned). Documented, not
  churned. Everything else green is the bar.

## 4. Standard verification chain (used before every commit batch)

1. Typecheck: `npx tsgo -p tsconfig.extension.json --noEmit` +
   `npx tsgo -p tsconfig.webviews.json` (run from `extensions/mssql` — npx
   from the wrong cwd hits the npm registry).
2. Full build: `npm run build` (repo root) — expect 0 errors.
3. Unit suite (above) — expect 3269+ passing, only the known flake.
4. In-proc vitest — 12/12.
5. Harness non-regression pair — official gate green + smoke passing.
6. STS build when STS changed.
