# Integrated Technical Overview: A Unified Observability Vision for vscode-mssql, perftest, and STS2

## The vision in one sentence

When these efforts are complete, the MSSQL VS Code stack will have a single evidence pipeline that can **measure user-visible performance, explain the cross-process cause, reproduce the scenario, gate regressions, and export safe forensic proof** without confusing diagnostic noise for official timing.

## Why these three efforts belong together

The three components solve different parts of the same problem.

| Component | Role in the observability system | What it contributes |
|---|---|---|
| **vscode-mssql Debug Console** | In-product microscope | Live traces, session history, waterfalls, Perf Test History, self-test, redaction, rich local diagnostics. |
| **perftest** | Deterministic measurement lab | Controlled VS Code runs, semantic scenarios, official marker-derived metrics, regression gates, reports, diagnostic collectors, history. |
| **STS2** | Future service truth engine | Journaled service envelopes, deterministic reducer, replay, strict causality, exportable evidence, robust service diagnostics. |

Individually, each is useful. Together, they form a loop:

```text
Developer or CI runs scenario
        |
        v
Product emits markers and diagnostic spans
        |
        +--> perftest derives official metrics and gates regressions
        |
        +--> Debug Console renders live/session/run waterfalls and history
        |
        +--> STS today emits diagnostic spans, STS2 tomorrow journals causal envelopes
        |
        v
A safe evidence bundle can explain, reproduce, compare, and support the fix
```

The important word is **same**: the same scenario shape, same event vocabulary, same timing rules, same redaction policy, and same provenance should travel across local debugging, CI measurement, and service replay.

## The layered model

### Layer 1: Semantic product markers

Markers are the official timing vocabulary. They name user-meaningful milestones:

- activation started and completed;
- connection began and became ready;
- query submitted, executed, and rendered;
- Object Explorer expanded;
- designer initialized or published;
- webview/result grid finished visible work.

These markers are intentionally not generic logs. They define the performance contract users feel. perftest uses them to derive official metrics. The Debug Console uses them to anchor traces and waterfalls.

Design principle: **a metric without the right marker pair should not exist.** Missing evidence should produce invalid or inconclusive output, not a fabricated number.

### Layer 2: Diagnostic spans and events

The vscode-mssql diagnostics substrate adds rich spans/events/metrics around the official markers:

- extension host spans;
- RPC client spans;
- webview spans;
- legacy STS `StsDiag` spans;
- rich collection snapshots;
- session stores;
- live tail;
- perf forwarding.

These explain shape and cause. They are not automatically official timing. A diagnostic bar can show where time likely went, while the official metric remains derived from product-timer or marker sources.

Design principle: **diagnostics explain official metrics; they do not silently become official metrics.**

### Layer 3: perftest scenario execution and regression gate

perftest provides the controlled lab:

- launches a pinned VS Code build with fresh profiles;
- loads only the product and driver extensions;
- provisions deterministic SQL data;
- drives scenarios through commands and semantic waits;
- records markers and artifacts per repetition;
- normalizes results;
- persists samples in SQLite;
- compares against baselines using eligibility rules, thresholds, variance checks, and statistical tests.

This answers: “Did the product get slower in a controlled environment?”

Design principle: **a gate should be boring, strict, and explainable.** A noisy environment should be inconclusive, not falsely green or falsely red.

### Layer 4: Diagnostic collectors

Diagnostic collectors turn a regression into an investigation:

- process sampling;
- extension-host CPU profiles;
- STS dotnet traces;
- STS2 envelope journals;
- future renderer traces;
- future SQL XEvents;
- future counters and memory snapshots.

Collectors are valuable because they attach deeper evidence to the same scenario window. They are dangerous if they change the measured behavior. The system handles this by marking collector metrics diagnostic-only unless overhead is calibrated and explicitly approved.

Design principle: **turn on heavier lights only after the official measurement tells you where to look.**

### Layer 5: STS2 deterministic service journal

STS2 moves service observability from “what did we log?” to “what did the service decide?”

Its intended future contribution:

- every service-relevant input/output is journaled;
- envelopes have sequence, correlation, cause, digest, and config version;
- the reducer can be replayed without a database;
- strict replay can prove whether the recorded journal is complete and deterministic;
- exports can be safe, exact-run, and privacy-governed;
- service fatal states can be explained after failure.

This answers questions that spans alone cannot:

- Which request caused this output?
- What state transition happened?
- Did replay reproduce the same service decision?
- Did the service lose, reorder, or corrupt any evidence?
- Which capture policy applied at that moment?

Design principle: **STS2 should enter the Debug Console as causal evidence, not as flattened logs.**

## How the data flows today

### Live product session

```text
vscode-mssql extension code
  -> Perf markers and diag spans
  -> classify/redact
  -> sinks
      -> LiveTailSink -> Debug Console live trace
      -> SessionDiagSink -> local session history
      -> console archive -> current-session queries
      -> self-test tap -> in-proc MarkerBus
```

If the STS diag listener is active, legacy STS spans enter through the loopback listener and are re-emitted into the same diagnostic core. The Debug Console can then show extension, webview, and service lanes in one waterfall.

### CLI perftest run

```text
perftest orchestrator
  -> launches VS Code with PERF_MODE
  -> driver executes scenario
  -> product emits markers
  -> PerfModeSink forwards official markers and selected diagnostic spans
  -> control server writes markers.jsonl
  -> normalizer writes result.json
  -> reports, SQLite store, regression comparison
  -> Debug Console can open the run directory
```

The same run can appear in a static HTML report, SQLite history, and the in-product Perf Test History view.

### In-product self-test

```text
Debug Console self-test dialog
  -> in-proc scenario engine
  -> real product commands and test seams
  -> diag tap feeds MarkerBus
  -> run directory written under self-test runs root
  -> Perf Test History opens the result immediately
```

This is the local reproduction loop. It should share scenario semantics with CLI perftest while clearly labeling its provenance as local/exploratory unless run under controlled conditions.

### Future STS2 diagnostic run

```text
perftest diagnostic pass or Debug Console STS2 integration
  -> STS2 journals envelopes during service work
  -> collector/importer validates exact run
  -> Debug Console maps envelopes to cause graph, state diff, and service lane
  -> strict replay/export result appears in Validation tab
```

This gives perftest reports and Debug Console traces service-layer evidence with replay teeth.

## How the proposed next steps make the system great

The next-steps plan turns the current architecture into an integrated product by filling the seams.

### Shared Observability Contract: the common language

Without a shared contract, each repo can be correct locally but confusing globally. With it:

- marker names do not drift;
- attributes have known classifications;
- timing rules are machine-checkable;
- new features know how to instrument themselves;
- reports and UI render events consistently;
- docs can be generated instead of hand-synchronized.

This is the difference between a bag of events and a language.

### Trace Identity V1: the thread through the maze

A real trace crosses boundaries:

- user command;
- extension host;
- webview;
- JSON-RPC;
- STS dispatcher;
- SqlClient;
- DacFx or SMO;
- SQL Server;
- back to UI rendering.

Trace Identity V1 lets the system stitch that journey without guessing. It also lets the UI say when stitching is incomplete.

This matters because partial traces are not useless, but they must be honest. A waterfall with missing correlation should look like a map with fog, not a map with invented roads.

### Metric eligibility: trust labels for numbers

Performance systems live or die by trust. The user should be able to answer:

- Is this number official?
- Can it gate CI?
- Was rich collection on?
- Is this diagnostic-only?
- Was the environment comparable?
- How many samples exist?
- Was the variance acceptable?

By carrying eligibility and provenance with every metric, the system prevents beautiful but untrustworthy graphs from driving decisions.

### Store and import hardening: evidence that survives time and sharing

A local session store, run directory, or STS2 bundle is useful only if it can be opened later and trusted. Manifests, schema versions, exact seq ranges, hashes, size caps, and import validation make this possible.

This is especially important for support workflows. A safe bundle should answer what happened without leaking secrets or requiring the recipient to trust mutable prose.

### Scenario parity: local reproduction to CI gate

The ideal path for a new perf issue:

1. Developer reproduces locally using in-product self-test.
2. The scenario is cleaned up and promoted to CLI perftest.
3. It runs in diagnostic mode to identify likely cause.
4. It graduates to measurement candidate.
5. It becomes a CI gate when stable.

This path works only if self-test and CLI share scenario semantics. Otherwise every promotion becomes a rewrite, and rewrites introduce tiny gremlins with clipboards.

### STS2 hardening: service evidence with replay truth

STS2 should not be rushed into the console just because it can emit interesting data. The hardening plan is what makes it trustworthy:

- session lifetime and fatal containment;
- pump barriers;
- exact-run replay;
- observer mailboxes;
- capture policy;
- strict export;
- bounded query/cancel/close behavior.

After those contracts stabilize, the Debug Console can safely grow Replay Lab features: state at seq, cause tree, state diff, strict replay validation, and fatal summaries.

## Example end-to-end workflows

### Workflow 1: CI regression to root cause

A nightly perftest run reports `query-10k-results` regressed.

1. The report shows the official metric regressed with enough samples and matching environment hash.
2. Developer opens the run directory in the Debug Console Perf Test History view.
3. The run provenance panel shows measurement pass, rich collection off, process sampler approved, no missing markers.
4. The compare waterfall shows scenario wallclock grew mostly after `mssql.query.execute` and before `mssql.resultsGrid.renderComplete`.
5. Diagnostic spans show an extra webview RPC and a longer results-grid render phase.
6. The investigation diff shows no SQL activity change, but extension-host CPU profile points to grid virtualization work.
7. Developer fixes the grid path and reruns the scenario.
8. New run compares green against the baseline. The evidence remains attached for the PR.

Outcome: the system not only catches the regression, it guides the developer away from STS/SQL and toward UI rendering.

### Workflow 2: Local self-test to CI scenario

A developer notices Table Designer feels slow.

1. They open the Debug Console and run the in-product Table Designer self-test using an active connection.
2. The self-test run appears in Perf Test History as local/exploratory.
3. Waterfall shows Table Designer init marker, webview initialization, RPCs, and legacy STS DacFx DesignServices spans.
4. Rich diagnostics show heap growth during initialization.
5. The scenario is promoted to CLI with the `designerOpen` driver port.
6. A diagnostic perftest recipe collects extension-host CPU and STS trace.
7. Once stable, it becomes a measurement candidate or CI gate.

Outcome: local hunch becomes repeatable evidence without rewriting the workflow from scratch.

### Workflow 3: STS2 failure support bundle

A user hits an STS2 query cancellation hang during preview.

1. Debug Console shows the service fatal summary and last committed seq.
2. User exports a safe STS2 diagnostic bundle.
3. Export-check validates hashes, privacy policy, exact run, and strict replay.
4. Support opens the bundle in Replay Lab.
5. Cause graph shows `query.cancel` led to a provider cancel timeout and forced cleanup.
6. State diff shows connection remained `ClosePendingQuery` until the journaled timer fired.
7. No secrets, SQL text, or row data appear in the bundle.

Outcome: support can diagnose an async service failure without raw credentials, guesswork, or a repro database.

### Workflow 4: SQL activity regression

A schema compare change appears to regress.

1. perftest gate shows official wallclock regression.
2. Diagnostic recipe `sql` captures XEvents.
3. Investigation diff shows candidate added 42 `rpc_completed` events and increased logical reads.
4. Debug Console correlates those SQL events to a specific extension command and STS/DacFx span.
5. The team fixes duplicate metadata fetching.
6. Follow-up run shows official metric green and SQL activity back to baseline.

Outcome: the system catches “same UI, more SQL work” regressions that pure wallclock cannot explain alone.

## What “great” looks like when this is done

### For feature developers

They can add instrumentation by choosing from a known event vocabulary, running contract tests, and seeing their feature appear in waterfalls, perf runs, and history without one-off plumbing.

### For performance owners

They can rely on gates because official metrics are structurally protected from diagnostic contamination, noisy runs are inconclusive, and provenance is visible.

### For service owners

They can inspect STS2 cause chains and replay journals instead of reverse-engineering from logs. Fatal states become explainable artifacts.

### For UI owners

They can see webview, RPC, render, and extension-host work in one trace, with viewer self-noise excluded from product analysis.

### For support

They can ask for safe bundles that validate privacy and replay before analysis. The bundle says what capture policy applied and which evidence is missing.

### For CI

It can store run histories, trend performance, detect step changes, compare baselines, and reject regressions with machine-readable reasons.

## The north-star architecture

```text
                 Shared Observability Contract
       event vocabulary | classification | timing | correlation
                                  |
                                  v
┌─────────────────────────────────────────────────────────────────┐
│ vscode-mssql product                                             │
│ Perf markers | diag spans | redaction | stores | Debug Console   │
└───────────────┬───────────────────────────────────────┬─────────┘
                │                                       │
                │ live/session/self-test                │ PERF_MODE
                v                                       v
     Debug Console live/history                perftest control server
     waterfalls, cause tree,                   markers.jsonl, result.json,
     Perf Test History                         SQLite, reports, regression
                │                                       │
                └────────────────┬──────────────────────┘
                                 v
                         Run and evidence bundle
                provenance | metrics | artifacts | validation
                                 │
                                 v
┌─────────────────────────────────────────────────────────────────┐
│ sqltoolsservice                                                  │
│ Legacy StsDiag today | STS2 envelopes, journals, replay tomorrow │
└─────────────────────────────────────────────────────────────────┘
```

## Operating principles

1. **Markers define the user-visible contract.** They are the roots of official performance numbers.
2. **Diagnostics explain, they do not smuggle themselves into gates.** Collector and epoch-aligned evidence remain labeled.
3. **Redaction is a contract, not a kindness.** Every field needs classification and policy.
4. **Correlation can be partial, but partial must be visible.** Fog is acceptable. Fake certainty is not.
5. **Runs are evidence.** They deserve manifests, hashes, schema versions, provenance, and safe import.
6. **Scenarios should graduate.** Local self-test, CLI diagnostic, measurement candidate, and CI gate should be stages of one lifecycle.
7. **STS2 should preserve causality.** Import sequence, cause, digest, and replay identity, not only duration bars.
8. **The UI should answer the next question.** When it shows a regression, it should suggest what evidence would most likely explain it.

## Final picture

The completed system becomes a performance evidence flywheel:

1. perftest detects a regression with controlled, official metrics;
2. Debug Console opens the same evidence and makes it explorable;
3. diagnostic collectors add targeted depth without contaminating the gate;
4. STS2 journals explain service decisions with replayable causality;
5. self-test reproduces the scenario locally;
6. comparisons prove the fix;
7. safe bundles preserve the story for review and support.

That is a strong destination. The magic is not any single chart or collector. The magic is that the whole stack tells one coherent truth, from the first marker to the last replayed envelope.
