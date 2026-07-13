# Peer Review: VS Code MSSQL Observability, perftest, and STS2

## Review posture

This review treats the uploaded documentation as the current design/build state for three related efforts:

1. **vscode-mssql Debug Console and diagnostics substrate**: in-product event capture, redaction, live views, session history, Perf Test History, self-test, STS span ingestion, and harness forwarding.
2. **perftest**: deterministic external performance harness, marker contracts, scenario runner, regression model, diagnostic collectors, reports, soak/stress, and investigation diff.
3. **sqltoolsservice STS2**: service refactor centered on deterministic core, journaled envelopes, replay, side-by-side v1/v2 transport, hardening plan, and future service observability.

The strongest pattern is already clear: **one family of classified events flowing into two complementary surfaces**. The Debug Console gives developers a microscope inside a running product. perftest gives CI-grade repeatability, regression gates, history, and reproducible artifacts. STS2 is the future deep source of truth for the service layer, with replayable journals and causal envelopes rather than loose logging.

The main critique is not that the system lacks ambition. It has several beautiful bones. The risk is that the three efforts could each grow a slightly different observability dialect. If that happens, the system will still be useful, but the grander promise, “one trace can move from live product to CI report to STS replay without semantic translation fog,” will erode.

## Executive assessment

The architecture is directionally excellent. It separates official metrics from diagnostic evidence, makes privacy a first-class constraint, uses semantic waits instead of sleeps, and recognizes that service-layer introspection needs a deterministic journal rather than one more logging stream.

The highest-leverage improvements are cross-cutting:

| Theme | Peer-review concern | Suggested direction |
|---|---|---|
| Contract ownership | DiagEvent, perf marker, and STS2 envelope schemas overlap but are not yet one governed vocabulary. | Create an Observability Contract package with event type registry, classification, timing class, official eligibility, and correlation rules. |
| Correlation | `runId`, `repId`, `traceId`, root action id, JSON-RPC id, owner URI digest, session id, STS2 `corr`, and `cause` all exist, but need one identity map. | Define Trace Identity V1: exact fields, propagation rules, TTLs, missing-correlation diagnostics, and import mappings. |
| Timing honesty | The official/diagnostic distinction is strong, but every UI/import/report path must preserve it without human interpretation. | Make timing class part of every derived metric and every visual bar. Add contract tests that prevent diagnostic durations from becoming official. |
| Privacy | Each subsystem has redaction rules, but field classifications and capture policy need to align across stores, exports, imports, and observers. | Create a shared classification taxonomy and canary corpus that runs across VS Code, perftest, STS2, reports, and bundles. |
| Data lifecycle | Session stores, run directories, SQLite history, STS2 journals, and bundles have different retention and integrity models. | Add manifests, schema versions, size caps, migrations, exact-run validation, and adversarial import tests. |
| Viewer contracts | The Debug Console is ahead of some STS2 observer contracts. | Keep STS2 gated pages gated until observer checkpoints, exact gaps, and safe envelope views are stable. |
| Scenario parity | CLI and in-product self-test share concepts but not fully one scenario implementation yet. | Converge the scenario catalog/DSL so a workflow can graduate from local self-test to CI gate with minimal rewriting. |
| Evidence provenance | perftest is strong here, STS2 is planning it, Debug Console history can benefit from more explicit provenance. | Every run/session/rep should carry source repo SHAs, schema versions, capture modes, official eligibility, environment hash, and collection cost. |

## What is notably strong

### The official metric boundary is a load-bearing idea

The docs consistently separate **measurement** from **diagnosis**. perftest derives official metrics from semantic markers, filters through passed measurement reps, and excludes diagnostics by structure. The Debug Console marks cross-process STS spans as epoch-aligned diagnostic bars. Rich collection is diagnostic-only. This is exactly the right discipline. It prevents the classic performance-tool failure mode where a heavy profiler “finds” a slowdown it caused itself.

The next improvement is to make this boundary **unmistakable and schema-enforced everywhere**, not just documented. A bar, metric, trend, export row, comparison, and UI annotation should all carry an explicit `timingClass` and `officialEligibility` decision with a reason.

### Semantic waits are the right antidote to flaky automation

The scenario model’s refusal to use arbitrary sleeps is a major quality advantage. Waiting for `mssql.resultsGrid.renderComplete`, OE expansion markers, webview probes, or success criteria creates repeatability and forces product instrumentation to name meaningful milestones. That is the right feedback loop: when a scenario needs a sleep, the product is missing an honest event.

The next layer should be a **scenario health score**: how many success proofs exist, whether they come from independent processes, whether they depend on fragile labels, and whether cleanup restores the exact state for the next rep.

### The Debug Console has the right “dual surface” shape

The console is not just a log viewer. It is a live trace surface, a history browser, a waterfall renderer, a self-test launcher, and an importer for perf runs. This is the right shape because performance work is usually a loop:

1. notice a regression;
2. open the run;
3. identify the slow lane;
4. reproduce locally;
5. instrument deeper;
6. compare again.

The console is positioned to become the cockpit for that loop.

### STS2’s journal/replay model is the correct future service observability substrate

The legacy `StsDiag` spans are useful, but STS2’s envelope model is more powerful: gapless sequence, causality, canonical digest, replay, export, and deterministic state. If hardened as planned, STS2 can answer “what happened?” and “would the reducer make the same decision again?” That is far beyond tracing.

The caution is that a viewer built too early against unstable observer semantics would calcify the wrong API. The STS2 next-steps guidance to stabilize lifetime, barriers, exact-run replay/export, observer checkpointing, and capture policy before full viewer integration is sound.

## Cross-system review

### 1. You need one Observability Contract, not just compatible shapes

Right now there are at least three semantically related but distinct units:

- **Perf markers**: official timing vocabulary for perftest and product performance metrics.
- **DiagEvents**: rich spans/events/metrics for the Debug Console, stores, live tail, and perf forwarding.
- **STS2 envelopes**: authoritative service journal entries with replay identity and cause links.

They do not need to become identical records. They serve different layers. But they need one governed semantic registry.

A registry entry should answer:

| Question | Example answer |
|---|---|
| What is the canonical event type? | `mssql.query.resultsRendered` |
| Is it a marker, span, envelope, metric, or derived event? | marker end, maps to DiagEvent span end |
| What feature owns it? | query/results-grid |
| Which attributes are allowed? | rowCount, resultSetCount, hasError, reason |
| What classification applies to each field? | rowCount: structural metadata, reason: safe enum |
| Can it be official? | yes, when paired with `mssql.query.execute` in same process |
| Which timing plane is valid? | product monotonic only |
| Which scenario metrics use it? | `query.resultsRendered.duration`, `scenario.wallclock` endpoint |
| How does it render? | solid bar in extensionHost or webview lane |
| What are its failure semantics? | error end marker must include stable reason |

This registry could live in a small shared package or generated artifact consumed by all three repos. It would reduce drift and make docs less hand-maintained.

### 2. Clarify “official” vs “measurement-eligible” vs “CI-gating”

The word **official** is doing a lot of work. In perftest, official means regression-eligible under strict conditions. In the in-product self-test, docs say wallclock/metrics can be official unless rich collection is enabled, but a user’s live VS Code session is not a controlled environment. That can create a trust mismatch.

Consider splitting the terms:

| Term | Meaning |
|---|---|
| `measurementEligible` | The metric was derived from approved marker/product-timer sources and passed timing rules. |
| `diagnosticOnly` | The metric came from collectors, epoch alignment, rich collection, or non-measurement pass. |
| `ciGatingEligible` | The metric was produced in a controlled perftest measurement run with environment hash, passed reps, no disallowed collectors, and enough samples. |
| `exploratoryMeasurement` | The metric was locally measured and useful for investigation, but not a regression gate. |

This keeps self-test valuable without implying a developer’s interactive machine is equivalent to a pinned CI runner. Tiny semantics, big trust dividend.

### 3. Define Trace Identity V1

The system has many useful identifiers, but correlation is where observability systems often turn into a drawer of tangled headphones. I would define a small cross-repo identity contract:

```jsonc
{
  "runId": "perftest or self-test run id, optional for normal product sessions",
  "repId": "perftest repetition id, optional",
  "scenarioId": "scenario id, optional",
  "rootActionId": "user action or scenario action root",
  "traceId": "cross-process trace id when available",
  "spanId": "local span id when available",
  "jsonRpcId": "request id when crossing extension to STS",
  "webviewRpcId": "request id when crossing webview boundary",
  "connectionIdDigest": "stable safe connection/session grouping id",
  "ownerUriDigest": "safe document/editor grouping id",
  "sts2Corr": "STS2 corr when imported",
  "causeSeq": "STS2 cause seq when imported from envelopes"
}
```

Then add rules:

- root actions have a TTL and explicit close semantics;
- nested root actions are either forbidden or represented as parent/child;
- orphan events are allowed but counted;
- every imported perf run maps `runId/repId/scenarioId` into the console source identity;
- STS2 envelope `cause` becomes an edge in the cause graph, not a fake span parent;
- JSON-RPC ids are correlation hints, not globally unique trace ids.

The Debug Console could then include a **Correlation Health** panel: orphan count, missing RPC joins, clock alignment quality, root-action leaks, long-running roots, and unmatched begin/end pairs.

### 4. Treat schema evolution as a product feature

These stores will outlive individual implementation waves. People will open old run folders and session stores months later. That means schema versioning, migration, and import validation are not polish, they are product features.

Suggested additions:

- `schemaVersion` in every persisted store manifest, run summary, marker file, imported bundle, and session store segment.
- A `compatibility` block saying which console/perftest versions can read it.
- Forward-compatible readers that preserve unknown fields but refuse unknown dangerous shapes.
- Migration tests with golden old stores.
- An import validator that treats run directories as untrusted input: path traversal, huge JSON lines, malformed timestamps, invalid attrs, scriptable HTML artifacts, and zip bombs should all be in the corpus.

The console will eventually become a forensic viewer. Forensic tools cannot be casual about input.

### 5. Unify privacy classification, not only redaction behavior

The docs are privacy-aware, which is excellent. The next step is field-level data classification across all schemas:

| Classification | Examples | Default behavior |
|---|---|---|
| `secret` | passwords, tokens, connection strings | never stored, never displayed, never exported |
| `userSql` | SQL text, batch fragments | digest by default, governed elevated capture only |
| `resultData` | row cells, grid contents | never captured by default, digest/governed only |
| `providerText` | SQL Server messages, exception text | sanitized safe code/message by default |
| `identifierSensitive` | server/db/object names, file paths | digest or redacted unless explicitly safe |
| `structuralMetadata` | row counts, durations, method names, statuses | stored normally |
| `diagnosticMetric` | heap, CPU, queue depth | stored normally, bounded labels |

Important nuance: provider/server messages can contain SQL text, object names, values, and credentials. They deserve the same suspicion as SQL text, not a separate “error string” loophole.

### 6. Add a cross-repo “observability contract test” suite

The pieces already have unit tests. The missing layer is tests that prove the shared story.

Examples:

1. Emit a product query marker pair, forward it into a perftest run, import the rep into the Debug Console, and assert the same metric remains official/solid.
2. Emit an STS span over legacy `StsDiag`, forward it into perftest, import it into the console, and assert it renders diagnostic/hatched and cannot appear in official samples.
3. Generate a redaction canary in SQL text, provider message, connection string, row value, and artifact. Assert no default store/report/export contains plaintext.
4. Create a live-tail overflow. Assert exact gap ranges and resync behavior.
5. Import a malicious bundle. Assert the console rejects or sanitizes it without executing anything or reading outside the bundle.
6. Run one scenario in CLI and in-product self-test. Assert markers, metrics, cleanup, and status semantics match within expected environment differences.

This suite should be small but sacred. It protects the promise that the three workstreams are one system.

## vscode-mssql Debug Console review

### Strengths

The Debug Console architecture has several strong choices:

- a single classification/redaction choke point before sinks;
- dynamic sink fan-out with self-noise exclusion;
- startup-to-shutdown session capture when enabled;
- a live archive seeded from persisted store, which avoids “open too late, lose context” pain;
- Perf Test History that reads both self-test and CLI run directories;
- watermarks around timing honesty: official same-process bars vs epoch-aligned diagnostic bars;
- a self-test engine that uses the real product paths instead of faked UI clicks;
- rich collection explicitly marked diagnostic-only.

### Have you considered: sink backpressure as a first-class contract?

The docs say sink failures should never break the product, and LiveTailSink has batching/gap records. I would make the sink contract more explicit:

- every sink has a bounded mailbox;
- emission is `tryWrite`, never arbitrary sink code on the hot path;
- overflow records include `droppedFromSeq`, `droppedThroughSeq`, `source`, and `reason`;
- sink health is queryable in the console;
- SessionDiagSink failures degrade capture and surface a status indicator, but do not silently pretend capture is healthy;
- PerfModeSink forwarding failures become validation warnings in the rep, not hidden loss.

Without this, the system can have “observability uncertainty”: you may not know whether nothing happened or capture dropped it.

### Have you considered: a store manifest and size budget?

The docs note count/age retention but no size cap for session diag. A session store can become a little JSONL dragon under a developer’s desk.

Add:

- total size cap;
- per-segment max size;
- compression option for closed segments;
- store manifest with schema version, policy id, session start/end, event counts, seq range, dropped ranges, capture mode changes, and redaction policy version;
- integrity check command;
- “clear sensitive captures” command separate from full delete;
- import/export bundle format with validation.

### Have you considered: analysis explainability?

The Overview, anomalies, critical path, SQL activity, and cause tree will be trusted only if the console explains how it derived them. For every derived view, include a “why this appears here” detail:

- which source events were used;
- what filters applied;
- whether viewer-internal events were excluded;
- whether any gaps exist;
- whether timing is same-process or epoch-aligned;
- whether missing correlation weakened the conclusion.

This turns heuristics from “magic panel” into a reliable debugging assistant.

### Have you considered: webview performance as a measured product feature?

The console itself is a UI with large traces, virtualized tables, charts, and waterfalls. It already excludes viewer-internal events from product traces, but its own performance still matters. Add a separate self-observation mode for the viewer:

- render latency for large trace imports;
- table virtualization health;
- memory for 20k, 100k, and 1M-event synthetic traces;
- waterfall zoom/pan frame time;
- RPC latency for history queries;
- artifact loading time and truncation reasons.

Keep these out of product traces by default, but make them visible in a console self-diagnostics page.

### Have you considered: perf history provenance as a first-class UI row?

Perf Test History should show not only “this run regressed,” but also “can this run be trusted?” Suggested columns or badges:

- source type: CLI, self-test, imported bundle, read-only directory, SQLite;
- measurement eligibility: CI-gating, local/exploratory, diagnostic-only;
- environment hash match/mismatch;
- product SHA, STS SHA, VS Code build, SQL seed;
- schema compatibility;
- capture mode and rich collection on/off;
- collector cost class;
- validation warnings;
- missing markers or dropped event ranges.

A run with a dazzling chart but bad provenance should look visibly suspect.

## perftest review

### Strengths

perftest has the right instincts for a serious perf harness:

- JSON schemas and runtime validation for configs, markers, and results;
- fresh VS Code profiles and controlled extension sets;
- semantic waits, no sleeps;
- official metric eligibility encoded in result shape and SQLite view;
- environment hashes to avoid nonsense comparisons;
- regression model using samples, variance checks, percent plus absolute thresholds, and statistical significance;
- diagnostic collectors structurally prevented from producing official metrics;
- harness self-telemetry;
- soak/stress with honest inconclusive leak verdicts;
- investigation diff as a non-gating explainer.

### Have you considered: scenario maturity levels?

Not every scenario should immediately be a gate. Define levels:

| Level | Meaning |
|---|---|
| `exploratory` | useful locally, still flaky or missing independent success proof |
| `diagnostic` | gathers evidence, not measurement-gating |
| `measurementCandidate` | stable enough for repeated measurement, not yet baseline-backed |
| `ciGating` | baseline-backed, enough samples, stable environment, known variance |
| `releaseGate` | blocks release or merge, owned by a feature team |

This helps the catalog grow without either blocking everything or pretending every new scenario is battle-hardened.

### Have you considered: a flake and noise ledger?

The regression model handles high variance as inconclusive. A next step is to persist noise over time:

- per-scenario coefficient of variation history;
- common failure reasons;
- machine/environment fingerprints correlated with noise;
- marker timeout rates;
- collector warning rates;
- rep invalidation reasons;
- cleanup failures.

Then the dashboard can say “this scenario is not gate-worthy yet because 18% of reps invalidate on missing `resultsRendered`,” which is much better than folklore.

### Have you considered: richer metric provenance for derived diagnostics?

The result contract requires derivation blocks for derived metrics. Extend that idea into reports and UI:

- source files and line counts used;
- collector version;
- capture window start/end marker names;
- clock calibration jitter;
- missing or partial collection notes;
- transformation formula;
- confidence level.

This is especially important for SQL activity diffs and STS envelope-derived medians.

### Have you considered: diagnostic pass recipes instead of toggles?

The collector list is growing: process sampler, STS journal, CDP, dotnet-trace, WPR/ETW, future XEvents, counters, renderer traces. A raw toggle matrix can overwhelm users.

Add named recipes:

- `light`: markers plus process sampler;
- `ui-rendering`: extension host profile, renderer trace, webview marks;
- `service`: STS journal, dotnet-trace, counters;
- `sql`: XEvents, SQL activity, query plans if safe/synthetic;
- `memory`: process sampler, heap snapshots, leak slope analysis;
- `full`: everything available, diagnostic-only.

Each recipe declares expected overhead, platform requirements, and what questions it answers.

### Have you considered: scenario artifact hygiene?

Artifacts are powerful and dangerous. Treat them as untrusted even when locally produced:

- define retention class and privacy class per artifact;
- cap file sizes;
- sanitize paths;
- make HTML reports static and script-free by default;
- include artifact manifest hashes;
- do not inline large artifacts into reports;
- ensure imported artifacts cannot escape the run directory.

This matters once run folders are zipped, shared, and opened inside the Debug Console.

## STS2 review

### Strengths

The STS2 direction is unusually strong for a service refactor:

- a deterministic reducer instead of async domain decisions scattered everywhere;
- journal-before-dispatch as a durable truth source;
- explicit effect runner boundary;
- side-by-side v1/v2 transport migration;
- replay and export as built-in design goals;
- privacy, capture, and redaction treated as architectural concerns;
- tests and invariants planned at the system level.

The existing STS2 review package already identifies the key hardening work. I agree with its bias: preserve the architecture, but convert the promises into mechanically enforced contracts before preview.

### Integration-specific concern: do not let STS2 and DiagEvent become parallel universes

The future Debug Console can ingest STS2 envelopes directly, but the mapping should be explicit:

| STS2 concept | Debug Console concept | Mapping note |
|---|---|---|
| `seq` | event order | preserve as service-local order and expose original sequence |
| `corr` | correlation id | map into `corr.sts2Corr`, not generic span id |
| `cause` | cause graph edge | preserve as cause edge, not necessarily parent span |
| envelope kind/type | event kind/type | maintain STS2 namespace, avoid flattening too early |
| payload digest | redaction proof/integrity | show in details, use for replay/export verification |
| runtime overlay | diagnostic metric/state | label runtime-only and exclude from replay identity |
| journal checkpoint | source provenance | needed for support bundles and gap recovery |

A thin importer that turns everything into generic spans would lose the best part of STS2: causality and replay identity.

### Integration-specific concern: observer checkpointing must precede rich viewer features

Live STS2 viewer integration should require:

- `runId` and schema version;
- last delivered seq;
- exact dropped seq ranges;
- first available seq for resync;
- journal checkpoint reference;
- redacted view declaration;
- capture policy visible to the viewer;
- sink health and overflow counters.

Until then, STS2 envelopes are safer as offline journal imports in diagnostic runs than as a live, always-on viewer feed.

### Integration-specific concern: capture policy should align with VS Code capture modes

VS Code has `digest`/`redacted` and elevated capture. STS2 has row/SQL capture modes and host policy in the target design. These should be one conceptual policy from the user's point of view:

- product default: local, redacted/digest, no secrets;
- elevation requires reason, duration, local-only warning, and visible timer;
- STS2 cannot exceed extension host policy;
- support bundles show exactly which policy applied;
- perftest diagnostic passes record capture mode in result/provenance;
- UI displays “this run had rich/full capture” with appropriate caution.

## Specific design questions worth answering soon

### Ownership and governance

1. Who owns the canonical event vocabulary across repositories?
2. Is the event registry generated from code, code generated from registry, or both from schemas?
3. What is the compatibility promise for old markers, DiagEvents, and STS2 envelopes?
4. Which repo owns the shared contracts package and release cadence?
5. What is the rule for deprecating or renaming an event type?

### Timing and metrics

1. Can in-product self-test ever produce CI-gating metrics, or only measurement-eligible exploratory metrics?
2. How is clock calibration quality surfaced when importing CLI runs into the console?
3. Are epoch-aligned STS/SQL bars always diagnostic, even if derived from STS2 journal timestamps?
4. Can a collector ever become measurement-approved, and what calibration evidence is required?
5. How do reports show when a metric is missing because a marker was missing rather than fast?

### Correlation

1. What happens when a root action leaks or remains open across unrelated work?
2. How are nested user actions represented?
3. How are webview RPC ids joined to extension RPC ids and STS JSON-RPC ids?
4. What is the orphan-event budget for a high-quality trace?
5. Can the console show correlation confidence rather than binary joined/not joined?

### Privacy and import safety

1. Are imported run directories treated as untrusted input?
2. Can the console open a zip bundle without extracting unsafe paths?
3. Which artifacts may contain sensitive data, and how are they labeled?
4. Does “full capture” still exclude secrets everywhere, including provider messages and artifacts?
5. What is the emergency behavior if classification fails: drop event, redact entire payload, or disable capture?

### Product behavior and overhead

1. What is the overhead budget for always-on session diagnostics in normal use?
2. Are sinks benchmarked under worst-case burst conditions?
3. Does rich collection perturb event-loop latency enough to change user behavior?
4. How is Debug Console self-noise measured without contaminating product traces?
5. Can a stuck history scan, artifact load, or webview render ever block product work?

### STS2 integration

1. What exact STS2 observer contract is stable enough for the console?
2. Will perftest consume STS2 journals offline, live envelopes, or both?
3. How are STS2 fatal descriptors surfaced in the Debug Console and perftest reports?
4. What subset of STS2 replay should be available inside VS Code vs command-line tooling?
5. Will STS2 envelope ingestion replace legacy `StsDiag` spans, or coexist for a transition period?

## Recommended principles for the next design pass

1. **Every number should carry its citizenship papers.** Source, timing plane, official eligibility, pass type, collector cost, schema version, and environment hash should travel with the metric.
2. **Every viewer claim should be explainable.** If the UI says “critical path,” “anomaly,” or “regression,” it should show the evidence and caveats.
3. **Every imported file is hostile until proven boring.** Run directories and bundles deserve schema, path, size, and privacy validation.
4. **No hidden translation layers.** Markers, DiagEvents, and envelopes can differ structurally, but semantic mappings must be explicit and tested.
5. **Diagnostics must fail visibly but harmlessly.** A sink, collector, indexer, or viewer may degrade. It should not break the product or pretend nothing was lost.
6. **Prefer graduation paths over duplicate engines.** Local self-test, CLI perftest, and CI gates should share scenario language and differ mainly in host environment and eligibility.
7. **Make privacy policy stronger than capture settings.** Settings request capture. Policy decides what is permitted.
8. **Let STS2 be causal, not just visual.** Preserve journal sequence, cause, replay identity, and checkpoints when bringing STS2 into the console.

## Bottom line

This system is close to a genuinely powerful observability loop: product markers establish honest timings, diagnostics explain the shape of the work, perftest gates regressions, and STS2 can eventually replay the service truth behind a trace.

The next phase should focus less on adding isolated features and more on making the seams crystalline: shared contracts, correlation, provenance, privacy policy, import safety, scenario parity, and STS2 observer stability. Do that, and the three workstreams become more than a set of useful tools. They become a coherent performance evidence machine.
