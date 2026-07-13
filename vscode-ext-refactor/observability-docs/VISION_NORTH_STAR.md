# Vision north-star — one observable, testable, replayable MSSQL tooling stack

> Orientation doc for any coding agent working on this system across repos and phases. It exists so
> that a local implementation choice can be checked against where the whole thing is going. Keep it
> alongside `IMPLEMENTATION_PLAN.md` and the phase prompts. It is the "why"; the phase prompts are
> the "what/when."

## The thesis (one paragraph)

The MSSQL for VS Code extension, the SQL Tools Service (STS2), and the perf harness are becoming one
**highly observable, testable, replayable framework**. The product is instrumented once, at the
source, to emit a **unified diagnostics stream** (semantic events/markers, spans, SQL server
activity, renderer traces, resource/memory samples). That one stream is consumed **three ways**: by
the **perftest harness** (automation/regression), by **AI coding agents** (structured runtime
evidence for coding loops), and by **normal-use "Session diag data"** (persisted locally when the
user opts in). On top of it sits **one extensible in-product analysis viewer** (consolidated
cross-process tracing, perf analysis, and replay), plus the harness's standalone reports — sharing
the same renderers. The result: run the product in automation, in AI-coding loops, or as a normal
user; collect all the data; see the bugs; experiment with changes.

## Architecture map

```text
        one instrumentation stream (unified event model)
   markers/events (ext host, webview)  +  STS2 envelopes (corr/cause/entityRefs/classification)
   +  SQL activity (XEvents)  +  renderer traces (CDP)  +  resource/memory samples
        correlated cross-tier:  externalTrace (VS Code) ↔ corr/cause (STS) ↔ Application Name (SQL)
                                   │
             ┌─────────────────────┼─────────────────────┐
        harness sink          live-tail sink         Session Diag sink
        (PERF_MODE)           (§16.2 checkpoint)     (user opt-in, classified, local)
             │                     │                     │
        harness reports      in-product viewer      agent evidence bundle (export)
        (waterfall + plots)  (same renderers)       (coherent, redacted)
                                   │
                         replay engine (STS2 replay-drive + provenance)
```

## Repo & phase map

- **perftest** (`C:\repos\test\perftest`) — the harness. Phases 1–3: contracts → E2E loop →
  product/STS instrumentation → SQL scenarios → regression → rich SQL activity → CDP → soak/stress →
  investigation diff → (Phase 3) finish gaps, advanced scenarios, cross-process waterfall + plots,
  cross-run tracking. Builds the **shared renderers** the in-product viewer reuses.
- **vscode-mssql** (`dev/karlb/perftest`) — `PERF_MODE` markers (Phase 2+), then **Session Diag**
  capture + the **in-product viewer** (Phase 4). The extension is the **host** that sets STS2 capture
  policy.
- **sqltoolsservice / STS2** — the envelope substrate: adopt the reviewed target design + recalibrated
  plan (correctness + viewer-substrate floor), then the vision-alignment extensions (cross-tier
  correlation, shared envelope schema, live-tail consumption, capture policy, replay-drive, export).
  See `STS2_VISION_ALIGNMENT.md`.

## The invariants (apply these to every local decision)

1. **Never fabricate; surface gaps.** No synthesized metrics, intervals, verdicts, or completions.
   When a value can't be measured/observed, emit nothing or a clearly non-official/`inconclusive`
   result — and surface exact gap metadata (dropped-from/through, missing markers, low-n) so a human
   or agent knows what's missing. This is the trait the whole system's credibility rests on.
2. **Official vs diagnostic separation.** Official metrics come only from markers/product timers in a
   measurement pass on a passed rep. Everything heavy (CDP, dotnet-trace, ETW, XEvents, heap dumps) is
   diagnostic and `official:false` — structurally, not by convention.
3. **Privacy-first for real data.** Normal-use capture is the user's real data: opt-in, local-only,
   never auto-uploaded, classified per field, redacted by default, bounded by an immutable host
   capture policy. A client can request but never silently elevate capture.
4. **One instrumentation, many sinks.** Reuse emission points; the difference between harness capture,
   live-tail, and Session Diag is the **sink + gate**, not duplicated instrumentation.
5. **Shared contracts + shared renderers.** The STS2 envelope schema + classification enum are a
   versioned cross-repo contract (copy verbatim, pin version, fixtures must validate). The
   waterfall/plot/trend renderers are one module reused by harness reports and the in-product viewer.
6. **Correlation is cross-tier.** Every identifier should help join VS Code ↔ STS ↔ SQL:
   `externalTrace`/traceId, STS `corr`/`cause`/`entityRefs`, and the SQL Application Name key all line
   up so one user action renders as one waterfall.
7. **No fork; measure shipping reality; determinism.** Instrument through launch flags, controlled
   extensions, product markers, CDP, and the STS2 journal — never a forked editor. No `sleep` in
   measured paths; semantic waits only. Every run reproducible from its config + environment
   fingerprint.

## How to use this doc

When making an implementation choice, prefer the option that: keeps official-metric integrity intact;
makes the piece **reusable across the three surfaces** (harness report, in-product viewer, agent
evidence); is **consumable by the correlation and replay model** (carries the right ids/classification);
and **surfaces rather than hides** uncertainty or gaps. If a choice would require faking data,
breaking a shared contract, or silently capturing sensitive data, it's the wrong choice — stop and
flag it.

## Pointers

- Phase prompts: `PERFTEST_PHASE_3_PROMPT.md` (finish & sharpen the harness),
  `PERFTEST_PHASE_4_INPRODUCT_DIAGNOSTICS.md` (in-product diagnostics).
- STS2: `STS2_VISION_ALIGNMENT.md` + the review package (`00`/`01`/`03` + `REVIEW_ASSESSMENT_AND_PLAN`).
- In-product UX: `CLAUDE_DESIGN_INPRODUCT_DIAGNOSTICS_BRIEF.md` (design mockups) and the Completions
  Debug view as the established pattern to generalize.
