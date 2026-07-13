# 07 — Phase 2 Branch Guide: Query Studio on the Observability Foundation

**Updated: 2026-07-04.** Phase 1 ("deep observability retrofit": Debug
Console + perftest + STS2 refactor + shared contracts) wraps at this point.
Phase 2 (Query Studio — the SSMS-parity editor, `ssms-query-docs/`) branches
from here. This doc records what Phase 2 consumes, what is frozen vs
additive, the pre-branch verification, and the deferred backlog.

## 1. What Query Studio builds on (per its own design docs)

| Foundation piece | How Query Studio uses it | Phase-1 status |
|---|---|---|
| **STS2 v2 wire contract** (`sqltoolsservice/docs/sts2/CONTRACT.md`) | The ONLY data plane for execution (adapter design §8: initialize, connection.open/close, query.execute + resultSet/rows/message/complete notifications, ack backpressure, cancel, dispose, capture, fatal) | ✅ Complete on `sts2/main`-derived branch; hardening review waves R001–R047 landed (lifetime/fatal containment, pump barriers, strict replay, observer mailboxes, capture policy, bounded cancel) |
| **Observability Contract registry** | Adds the `mssql.queryStudio.*` marker family (design §17.1); official metric = submit→resultsRendered | ✅ Additive by design — register + regenerate + re-vendor; conformance + vendor-sync tests enforce the loop |
| **Metric eligibility** | Query Studio perftest scenarios produce gate-eligible metrics; self-test runs stay exploratory | ✅ Structural (shared deriveEligibility) |
| **Trace Identity V1 + lint** | Editor→adapter→STS2 correlation; `replayTraceId`/`replayRunId` tagging (design §17.3) | ✅ Contract written; STS2 corr/cause mapping rules defined (edges, not fake parents) |
| **Debug Console patterns** | Webview pattern (versioned interfaces, coarse state + hot-path RPC), capture elevation for replayable SQL text, session diag | ✅ Stable; elevation is time-bound/local-only as the design requires |
| **perftest + self-test parity** | `queryStudio-*` scenarios in both hosts; `query-10k-results` must stay green through grid extraction (design M0) | ✅ Parity conformance tests enforce identical metric semantics across hosts; designerOpen port proved the graduation path works |
| **Diagnostic recipes** | "why slow?" investigations during development | ✅ light/ui-rendering/service/sql/memory/full |

## 2. Contract findings for the adapter's AD-1 task

AD-1 ("reconcile exact method names/shapes into wire/v2.ts") — checked
against `CONTRACT.md` on the branch-point commit:

- **All core methods exist**: `v2/initialize`, `v2/connection.open`,
  `v2/connection.close`, `v2/query.execute`, `v2/query.resultSet`,
  `v2/query.rows`, `v2/query.message`, `v2/query.complete`, `v2/query.ack`,
  `v2/query.cancel`, `v2/query.dispose`, `v2/fatal`.
- **One naming reconciliation**: the design's `v2/session.setCapture` is
  `v2/diagnostics.setCapture` in the contract.
- **Extras available**: `v2/connection.cancel`,
  `v2/diagnostics.{health,state,ping,exportLog}` — the health/state surface
  the design's status bar + diagnostics can use.

**No wire-contract changes are required for Query Studio v1.** Anything new
it needs (if discovered) is an STS2-side ADDITIVE method behind the
versioning rules (SPEC §7.1), not a mutation of existing shapes.

## 3. Frozen vs additive after the branch

**Frozen (change on the foundation branches only, merge forward):**
- STS2 wire contract shapes + envelope schema + journal format
  (`CONTRACT.md`, `TRACE-SCHEMA.md`).
- DiagEvent envelope + classification taxonomy + timing classes.
- perftest marker/result schemas (incl. `eligibility`), run-directory
  layout.
- The eligibility + correlation decision functions (shared semantics).

**Additive (feature branch does this freely, guarded by tests):**
- Registry entries for `mssql.queryStudio.*` (register → `npm run
  generate` → re-vendor; the extension conformance test fails on
  unregistered names, the vendor-sync test fails on stale copies).
- New scenarios in both catalogs (parity test enforces identical metric
  semantics; maturity starts `exploratory`/`diagnostic`).
- New Debug Console pages/tabs, new perftest configs and recipes.

## 4. Pre-branch verification (executed at wrap)

- STS2 `verify.sh --quick` — see PROGRESS Entry 36 for the recorded result.
- vscode-mssql extension suite (3280-class, one documented copilot-owned
  flake), full build.
- perftest workspaces: observability-contracts 27/27 (incl. NEW vendor-sync
  guard), perf-contracts 14/14, cli 44/44, inproc 12/12.
- Non-regression gate `query-10k-results` 4/4 official; console smoke green.
- Designer CLI scenarios 8/8 (the parity/graduation proof).
- All three repos committed clean on their current branches
  (`dev/karlb/perftest` lineage).

## 5. Deferred backlog (Phase 1 leftovers, safely post-branch)

None of these change contracts; they are additive depth/tooling:

1. **XEvents collector MVP** + SQL activity normalization (the `sql` recipe
   currently enables the flag; the collector wiring is the follow-up).
2. **Heap snapshots** for soak memory attribution.
3. **Zip bundle import** (directory bundles work today).
4. **Console SQLite source** (read-only preview stub until a loadable
   driver strategy is chosen: worker process / WASM / keep directories).
5. **STS2 Replay Lab in the console** (offline envelope import first) — the
   console pages stay gated; STS2's M7 preview-tag human gate is the
   trigger, per its runbook.
6. **CI ladder / flake ledger / evidence manifests** (next_steps P2) — an
   operating-model effort, orthogonal to feature code.
7. **CopilotChatEntry hook flake** — Copilot-team-owned; suppresses 3
   suite-mates when it fires (documented arithmetic).

## 6. How Phase 2 starts (mechanics)

1. Branch `vscode-mssql`, `perftest`, and (if touching STS2)
   `sqltoolsservice` from the current foundation branches.
2. First instrumentation PR on the feature branch: register the
   `mssql.queryStudio.*` family from design §17.1 in
   `perftest/packages/observability-contracts`, regenerate, re-vendor —
   the marker names are then contract-checked from day one.
3. Keep `query-10k-results` green through the M0 grid extraction (the
   design's own gate), using the standard verification chain
   (05-testing.md §4).
