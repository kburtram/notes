# Deep Observability Retrofit — Documentation Hub

**Updated: 2026-07-04 — PHASE 1 WRAPPED (see 07 for the branch guide).** This folder is the map for the three workstreams that
together retrofit deep observability onto the MSSQL VS Code stack. It is the
place to (re)build context before the next round of improvements.

## The three workstreams and how they fit

```
                 ┌──────────────────────────────────────────────────┐
                 │              What the user experiences            │
                 │   MSSQL Debug Console (in-product, webview)       │
                 │   Perf Test History · Waterfalls · Live Trace     │
                 └───────────────▲──────────────────▲───────────────┘
                                 │                  │
     (1) vscode-mssql            │                  │   (2) perftest
     diagnostics substrate       │                  │   CLI harness
 ┌───────────────────────────┐   │   ┌──────────────┴──────────────┐
 │ diag core + sinks         │───┘   │ scenario runner, collectors, │
 │ Perf markers, rpc/webview │◄──────┤ SQLite history, reports,     │
 │ spans, redaction, stores  │ spans │ regression gate, self-test   │
 └────────────▲──────────────┘ fwd   └──────────────▲───────────────┘
              │ STS_DIAG_URL loopback               │ markers (control server)
 ┌────────────┴───────────────────────────────────── ┴──────────────┐
 │ (3) sqltoolsservice: StsDiag spans today; STS2 rebuild            │
 │ (dispatcher split, journaled v2 envelopes, pluggable driver,      │
 │  mutation/Stryker tests) as the future high-fidelity source       │
 └───────────────────────────────────────────────────────────────────┘
```

One idea unifies them: **a single classified event vocabulary** (markers +
spans with correlation ids) emitted by the product and the service, consumed
by two surfaces — the in-product Debug Console (live, interactive) and the
perftest harness (deterministic, gated, historical). The same event can appear
in a live trace, a self-test rep, a CLI waterfall, and a regression gate.

## Documents in this folder

| Doc | What it covers |
|---|---|
| [01-architecture.md](01-architecture.md) | The unified event pipeline end to end: emit → classify → sink → store → analyze → render. Correlation, timing honesty, privacy invariants. |
| [02-debug-console.md](02-debug-console.md) | vscode-mssql Debug Console implementation: every module, RPC surface, webview page, setting, and command. |
| [03-instrumentation-reference.md](03-instrumentation-reference.md) | The complete instrumentation catalog: extension markers/spans, STS spans, rich collection, forwarding rules, and recipes for adding more. |
| [04-perftest-integration.md](04-perftest-integration.md) | How the console and the harness interlock: in-proc self-test engine, run directory contract, history providers, span forwarding into CLI runs. |
| [05-testing.md](05-testing.md) | Test inventory across all three repos, verification workflows, known flakes, and the reliability playbook. |
| [06-sts2-and-next.md](06-sts2-and-next.md) | Where STS2 fits, what is gated on it, current retrofit status, and the seams for the next round of improvements. |
| [07-phase2-query-studio-branch-guide.md](07-phase2-query-studio-branch-guide.md) | Phase-1 wrap: what Query Studio consumes, frozen vs additive, pre-branch verification, deferred backlog. |
| [inline_comp_observability.md](inline_comp_observability.md) | Inline completions observability (feature capture, replay, sessions analysis): current design, comparison with the substrate/STS2/perftest mechanisms, and the phased unification plan (console UX merge, journal consolidation, Replay Lab). |
| [inline_comp_observability_addendum.md](inline_comp_observability_addendum.md) | Approved review of the unification plan: architectural amendments (bundle catalog, durable identity, capture-policy dimensions, lifecycle records, service de-fork, replay safety), revised sequence, parity matrix, test plan. |
| [inline_comp_observability_final_plan.md](inline_comp_observability_final_plan.md) | **The authoritative merged execution plan** (companion + addendum reconciled): frozen decisions, UX quality brief, merged Gate A → Phase 0–5 sequence, delivery slices, status ledger. |

## Where the per-repo docs live (source of truth for their internals)

- **perftest** — `perftest/docs/` (15 docs: ARCHITECTURE, CONTRACTS, CLI,
  SCENARIO_AUTHORING, PRODUCT_INSTRUMENTATION, STS_INSTRUMENTATION,
  DIAGNOSTIC_COLLECTORS, REGRESSION_MODEL, REPORTS, RUNNING_TESTS, …), plus
  `IMPLEMENTATION_PLAN.md` and `PROGRESS.md` (the build journal — entries 1–30
  narrate every iteration). Design source:
  `perftest-docs/mssql-vscode-perf-system-v2/MSSQL_VSCODE_PERF_SYSTEM_DESIGN.md`.
- **sts2** — `sqltoolsservice/docs/sts2/` (SPEC, CONTRACT, STATE-MACHINE,
  TRACE-SCHEMA, OBSERVABILITY, SCENARIO-MATRIX, ENGINE-TESTS, INVARIANTS,
  DECISIONS, PLAN-M0…M7, AGENT-RUNBOOK).
- **Debug Console design/UX specs** — `debug-docs/` (Technical design, UX
  spec, Perf Test History spec + mocks). The *implementation* documentation
  is [02-debug-console.md](02-debug-console.md) in this folder.

## Reading order for a fresh context

1. This README (the map).
2. `01-architecture.md` (the pipeline).
3. The doc for whichever workstream you're touching.
4. `perftest/PROGRESS.md` latest entries for the current build state.
