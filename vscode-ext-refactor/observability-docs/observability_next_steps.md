# Recommended Next Steps: Building the MSSQL Observability System into a Daily Workhorse

## Goal

The system should become the default way to answer three questions:

1. **Did we regress?** perftest answers this with controlled runs, official metrics, baselines, and gates.
2. **Why did it regress?** the Debug Console, diagnostic collectors, and STS signals explain which product, UI, service, SQL, or environment phase changed.
3. **Can we prove and share the answer safely?** STS2 journals, validated run bundles, redaction policy, replay, and provenance make the evidence trustworthy.

The steps below are ordered to reduce rework. They favor contracts and hardening first, then scenario expansion, then richer UI and automation.

## Priority map

| Priority | Workstream | Outcome |
|---|---|---|
| P0 | Shared contracts | One vocabulary for markers, DiagEvents, STS2 envelopes, classification, timing, correlation, and provenance. |
| P0 | Debug Console durability | Safe stores, exact gaps, import validation, size caps, schema migration, and trustworthy Perf Test History. |
| P0 | perftest/self-test parity | Scenarios can graduate from in-product self-test to CLI and CI without semantic rewrites. |
| P0 | STS2 hardening | Lifetime, barriers, exact-run replay/export, observer mailboxes, capture policy, and fatal containment before deep viewer work. |
| P1 | Cross-run analysis | Perf History shows baseline comparisons, trends, regression badges, and investigation diffs in-product. |
| P1 | Diagnostic depth | Add targeted recipes for UI, service, SQL, memory, and full diagnostics. |
| P1 | Scenario coverage | Designers, schema compare, SQL projects, cancellation, large data, memory, soak, and failure workflows. |
| P1 | UI explainability | Cause tree, compare waterfalls, anomaly explanation, correlation health, and provenance panels. |
| P2 | STS2 replay lab | Envelope import, state-at-seq, state diff, strict replay result, fatal summary, and safe bundle workflow. |
| P2 | CI and fleet evidence | Nightly baselines, rolling trends, dashboards, flake/noise ledger, and signed evidence manifests. |

## P0: Establish the shared Observability Contract

### 1. Create an event vocabulary registry

Build a small generated contract that all three repos consume. It should not force every event to share one physical record shape. It should define the semantic truth behind each event.

Recommended files:

```text
observability-contracts/
  event-types.json
  classifications.json
  timing-classes.json
  correlation-v1.schema.json
  metric-eligibility.json
  render-hints.json
  generated/
    typescript/
    csharp/
    markdown/
```

Each event type should include:

- canonical type name;
- owning feature;
- allowed process roles;
- kind: marker, span, event, metric, envelope, derived metric;
- begin/end pairing rules if relevant;
- allowed attributes with field classifications;
- official or measurement eligibility rules;
- timing class rules;
- correlation fields required or optional;
- render lane and display hints;
- deprecation status.

Exit criteria:

- vscode-mssql marker/span types validate against the registry.
- perftest marker/result schemas reference registry names.
- STS2 envelope import has a namespaced mapping plan.
- Generated docs replace hand-maintained event lists where practical.

### 2. Define Trace Identity V1

Create one correlation contract that maps product, harness, webview, STS, and STS2 identities.

Minimum fields:

- `runId`, `repId`, `scenarioId`;
- `rootActionId`, `traceId`, `spanId`;
- `jsonRpcId`, `webviewRpcId`;
- `ownerUriDigest`, `connectionIdDigest`, `queryIdDigest`;
- `sts2Corr`, `sts2CauseSeq`;
- source schema/version.

Add rules for:

- root action TTLs;
- nested actions;
- orphan events;
- begin/end pairing;
- JSON-RPC id reuse boundaries;
- how imported STS2 cause links appear in Debug Console cause graphs;
- how missing correlation is surfaced.

Build a **correlation linter** used by tests and the Debug Console:

- orphan count;
- unmatched begin/end pairs;
- long-lived roots;
- missing RPC response joins;
- events outside scenario windows;
- clock-alignment uncertainty.

### 3. Make official eligibility explicit everywhere

Replace the single overloaded concept of `official` with a richer decision object:

```jsonc
{
  "measurementEligible": true,
  "ciGatingEligible": false,
  "diagnosticOnly": false,
  "reason": "markerPairSameProcessMonotonic; local self-test environment",
  "timingClass": "officialSameProcess",
  "source": "productMarker",
  "passType": "measurement"
}
```

Implementation steps:

- Extend perftest result metrics with a structured eligibility reason.
- Preserve this object when importing runs into the Debug Console.
- Show it in Perf Test History and waterfall tooltips.
- Add tests proving epoch-aligned spans, collectors, rich collection, and diagnostic passes cannot become CI-gating metrics.

## P0: Harden Debug Console storage, import, and live capture

### 4. Add session store manifests, size caps, and integrity checks

Add a manifest per session:

```jsonc
{
  "schemaVersion": "diag-session/1",
  "sessionId": "...",
  "startedAt": "...",
  "endedAt": "...",
  "seqRange": [1, 104293],
  "eventCountsByKind": {},
  "capturePolicyIds": [],
  "droppedRanges": [],
  "segments": [{ "path": "0001.jsonl", "firstSeq": 1, "lastSeq": 5000, "sha256": "..." }],
  "retention": { "maxAgeDays": 14, "maxSessions": 10, "maxBytes": 1073741824 }
}
```

Add commands:

- validate store;
- compact/compress old segments;
- clear elevated captures only;
- show store health;
- export safe bundle.

Tests:

- corrupt segment;
- missing segment;
- partial last line;
- size retention;
- schema migration from an older fixture;
- classification failure fallback.

### 5. Make live gaps exact and recoverable

LiveTailSink and future STS2 live viewers should use exact gap metadata:

```jsonc
{
  "kind": "gap",
  "source": "liveTail",
  "droppedFromSeq": 1234,
  "droppedThroughSeq": 1450,
  "firstAvailableSeq": 1451,
  "lastDeliveredSeq": 1900,
  "reason": "mailboxOverflow"
}
```

UI behavior:

- show a visible trace gap marker;
- offer “load missing range from store” when possible;
- degrade analysis confidence when the gap cannot be filled;
- never silently compute a critical path across unknown data.

### 6. Treat perf run directories and bundles as untrusted imports

Build a `RunImportValidator` used by Perf Test History, bundle import, and report regeneration.

Validation corpus:

- invalid JSONL lines;
- huge marker attrs;
- path traversal in artifacts;
- zip bomb shapes;
- HTML artifacts with scripts;
- malformed timestamps;
- mismatched `runId`/`repId`/`scenarioId`;
- missing `scenario.start`/`scenario.end`;
- forwarded diagnostic spans marked official;
- old schema versions;
- unknown collector artifacts.

Exit criteria:

- malicious or malformed imports fail with actionable diagnostics;
- valid old runs still open;
- artifacts are capped, sanitized, and lazy-loaded;
- all import warnings appear in the run provenance panel.

## P0: Unify CLI perftest and in-product self-test semantics

### 7. Create a shared scenario core

The CLI and in-proc packages already share concepts. The next step is a more explicit common scenario model:

- one scenario schema;
- shared step definitions where possible;
- host adapters for CLI driver vs in-product engine;
- shared success criteria;
- shared metric declarations;
- shared cleanup semantics;
- shared cancellation behavior;
- shared marker freshness rules.

Keep host-specific steps, but require them to declare whether they have CLI, self-test, or both implementations.

### 8. Port `designerOpen` to the CLI driver engine

This is already identified as deferred and should be early because designers are performance-critical and rich in cross-process behavior.

Deliverables:

- CLI `designerOpen` implementation;
- designers run config;
- Table Designer open scenario;
- Schema Designer open scenario;
- designer restore prompt suppression verified only for self-test application names;
- official marker pair for user-perceived designer init;
- diagnostic STS/DacFx spans surfaced in waterfalls.

### 9. Define scenario graduation gates

Add scenario maturity metadata:

```jsonc
{
  "maturity": "exploratory | diagnostic | measurementCandidate | ciGating | releaseGate",
  "owners": ["query", "objectExplorer"],
  "requiredSuccessProofs": 2,
  "knownFlakes": [],
  "varianceBudget": { "maxCv": 0.2 },
  "minimumSamples": 5
}
```

The dashboard should show why a scenario is not yet gate-worthy.

## P0: Finish STS2 hardening before deep viewer coupling

The STS2 review package already defines the right waves. For integration, these are the minimum gates before building the full STS2 Debug Console pages.

### 10. Stabilize session lifetime and fatal containment

Required:

- composite `Sts2Session.Completion`;
- coordinator, outbound writer, effect runner, observers, and RPC listener all owned;
- pending v2 requests terminate on fatal;
- legacy v1 continues when STS2 dies;
- safe fatal descriptor available after pump death.

### 11. Implement pump barriers for lifecycle, checkpoint, and export

Required:

- lifecycle shutdown is processed by the pump before flush acknowledgement;
- export receives an immutable exact-run inventory;
- query terminal and fatal points follow a central durability policy;
- active segment/checkpoint semantics are strict.

### 12. Make exact-run replay/export strict

Required:

- one run per directory or exact manifest-bound reader;
- strict verification rejects truncation, mixed runs, missing outputs, bad digests, bad cause links, and corr/config mutations;
- partial replay cannot call itself identical;
- export-check runs strict replay and privacy checks.

### 13. Stabilize observer mailbox and checkpoint protocol

Required before live STS2 console ingestion:

- bounded observer mailboxes;
- nonblocking coordinator publish;
- exact dropped seq ranges;
- redacted observer view declaration;
- sink health;
- resync from journal checkpoint.

### 14. Lock host capture policy

Required:

- client cannot enable full SQL/row capture beyond host policy;
- reason, duration, audit, and automatic reversion for elevated capture;
- provider/server text classification;
- secret leases and opaque tokens;
- canary tests across journals, logs, state, exports, and reports.

## P1: Build richer cross-run analysis in the Debug Console

### 15. Bring perftest comparison results into Perf Test History

For each scenario:

- current vs baseline median/trimmed mean;
- percent and absolute delta;
- p-value and inconclusive reasons;
- sample counts;
- CV/noise warning;
- environment hash match;
- official eligibility summary;
- comparison verdict badge.

Allow users to choose:

- named baseline;
- prior green run;
- rolling N baseline;
- before/after tagged runs.

### 16. Add compare waterfalls

A compare waterfall view should show two reps aligned by semantic phases:

- baseline bars above candidate bars;
- official bars solid, diagnostics hatched;
- added/removed spans;
- duration deltas per phase;
- clock/jitter caveats;
- “focus on changed critical path” toggle.

This would make the console feel less like a log viewer and more like a perf debugger.

### 17. Integrate investigation diff

Bring the `perftest diff` concepts into the in-product history UI:

- official gate summary;
- SQL activity delta when XEvents exist;
- metric deltas including diagnostic metrics;
- git context;
- added/removed RPC calls;
- changed STS methods;
- memory/CPU trend deltas;
- “what changed most?” ranked list.

## P1: Expand diagnostic collectors and recipes

### 18. Add named diagnostic recipes

Implement recipes as config presets:

| Recipe | Collectors | Question answered |
|---|---|---|
| `light` | markers, process sampler | Did it regress and which process grew? |
| `ui-rendering` | CDP extension host, renderer trace/profile, webview marks | Was this UI/rendering/event-loop bound? |
| `service` | STS journal, dotnet-trace, dotnet-counters | Was this STS, DacFx, SMO, SqlClient, or dispatcher bound? |
| `sql` | SQL XEvents, SQL activity normalization | Did SQL round-trips, reads, or waits change? |
| `memory` | process sampler, heap snapshots, allocation summaries | What retained memory grew? |
| `full` | all available safe collectors | Give me the big lantern. |

### 19. Add SQL XEvents collector and SQL activity normalization

This unlocks the most useful investigation headline: “we added three SQL round trips” or “logical reads grew 10x.”

Requirements:

- synthetic/test-data safe defaults;
- no raw SQL text by default unless explicitly governed;
- normalization with literal parameterization;
- per-command duration, reads, writes, CPU, row count where available;
- one-sided capture warnings;
- integration into `perftest diff` and Debug Console SQL Activity.

### 20. Add heap snapshots to soak memory investigations

The soak doc already found extension-host RSS growth. Add a follow-up path:

- capture heap snapshot at start, midpoint, end for diagnostic pass;
- compute retained type/object growth;
- link growth to marker phases if possible;
- show “top retained constructors” in Diagnostics tab;
- keep official leak verdict based on measured slopes, not heap snapshot heuristics.

## P1: Expand scenario catalog

Recommended scenario groups:

### Query and results grid

- 10k, 100k, and larger virtualized result sets;
- large cell/blob/xml data;
- scroll window fetch correctness;
- query cancellation;
- query error with safe provider message;
- multiple result sets;
- cold DB vs warm DB;
- connection reuse vs fresh connection.

### Object Explorer

- server-level expand;
- database-level expand;
- 10k tables catalog;
- refresh;
- search/filter if supported;
- disconnect cleanup;
- slow SMO or error path.

### Designers and DacFx

- Table Designer open existing table;
- Table Designer new table;
- publish no-op/minor edit;
- generate script;
- Schema Designer open with N tables;
- Schema Compare compare and publish;
- DacFx export/import/extract where safe.

### SQL Database Projects

- project load;
- build;
- publish to local container;
- schema compare from project;
- integration once sql-projects instrumentation exists.

### Reliability and soak

- connect-query-disconnect loop;
- repeated designer open/close;
- repeated OE expand/refresh;
- cancellation loop;
- memory growth and failure taxonomy;
- long-running live tail with gaps.

### Failure and privacy

- bad credentials;
- SQL syntax error;
- provider message with canaries;
- connection timeout;
- missing STS;
- diagnostics sink failure;
- import corrupted run;
- redaction/elevated capture expiration.

## P1: Improve Debug Console UI for “why slow?”

### 21. Add an Investigation Workbench page

This should combine the most useful slices:

- selected run/rep/trace;
- top changed phases;
- critical path;
- slowest spans;
- added/removed RPC calls;
- SQL activity delta;
- memory/CPU deltas;
- validation warnings;
- suggested next diagnostic recipe.

The goal is not to guess the answer. The goal is to shorten the path from data swamp to next useful action.

### 22. Add correlation health and trace quality panels

Show:

- missing begin/end pairs;
- orphan spans;
- root action leaks;
- unmatched RPCs;
- clock alignment jitter;
- gap ranges;
- viewer-internal exclusions;
- capture mode changes;
- schema compatibility warnings.

### 23. Add provenance panels everywhere

Each run, trace, metric, and artifact should answer:

- where did this come from?
- which schema version?
- which product/STS/perftest commit?
- which environment hash?
- which capture mode?
- which collectors?
- which validation warnings?
- can this metric gate a regression?

## P2: Build STS2 Replay Lab after contracts stabilize

### 24. STS2 envelope import

First version can be offline:

- open journal/export bundle;
- validate schema and strict replay result;
- show sequence list;
- show cause graph;
- map connection/query entity refs;
- show fatal descriptor;
- show state at selected seq;
- show runtime overlay separately.

### 25. State diff and explain

Add:

- state before/after selected envelope;
- reducer output explanation;
- effect requested;
- driver observation returned;
- why terminal status happened;
- privacy/capture policy at that seq.

### 26. Link STS2 journal evidence to perftest runs

When a perftest diagnostic pass collects STS2 journals:

- expose them as nested sources under the rep;
- link waterfall spans to envelope seq ranges;
- allow “open STS2 evidence at this RPC”;
- run strict replay and show result in Validation tab.

## P2: CI, dashboards, and operating model

### 27. Establish a perf CI ladder

| Tier | Purpose | Frequency |
|---|---|---|
| Smoke | no-op, activation, simple query, console smoke | every PR where relevant |
| Feature gate | query/OE/designer selected scenarios | PR opt-in or protected branches |
| Nightly baseline | full measurement catalog on pinned machines | nightly |
| Diagnostic nightly | rotating diagnostic recipes | nightly/weekly |
| Soak | long reliability/memory loops | scheduled weekly |
| Release gate | release-critical scenario set | release branches |

### 28. Build a flake/noise dashboard

Track:

- invalid reps by reason;
- failed reps by success criterion;
- scenario CV over time;
- timeout rate;
- marker missing rate;
- collector warnings;
- machine idle/preflight failures;
- scenario maturity movement;
- known flakes with owners.

### 29. Publish evidence manifests

Every CI run should produce a machine-readable manifest:

- commit SHAs and dirty state;
- VS Code build;
- STS build;
- SQL image digest and seed version;
- perftest version;
- scenario list;
- collector list;
- environment hash;
- pass type;
- schema versions;
- artifact hashes;
- validation warnings;
- comparison verdicts.

## First 15 pull requests I would sequence

1. **Shared Observability Contract skeleton**: event registry, classifications, timing classes, generated docs.
2. **Trace Identity V1**: schema, correlation linter, Debug Console trace quality summary.
3. **Metric eligibility object**: perftest result extension, console display, tests preventing diagnostic promotion.
4. **Session store manifest and size cap**: schema, retention, validation command, migration fixture.
5. **Exact live gap ranges**: LiveTailSink protocol, UI markers, resync from session store.
6. **Run import validator**: adversarial corpus, artifact caps, bundle safety groundwork.
7. **Scenario core unification**: shared scenario schema and host adapter capability matrix.
8. **CLI designerOpen port**: designers run config and first Table/Schema Designer CLI scenarios.
9. **Perf History comparison badges**: consume comparison.json/store data, show baseline verdicts and provenance.
10. **Named diagnostic recipes**: light/ui/service/sql/memory/full presets.
11. **SQL XEvents collector MVP**: normalized activity and diff integration.
12. **Soak heap snapshot diagnostic pass**: memory attribution tab.
13. **STS2 lifetime/barrier hardening**: from STS2 Wave 1.
14. **STS2 exact-run replay/export hardening**: from STS2 Wave 2.
15. **STS2 observer mailbox/checkpoint protocol**: prerequisite for live console integration.

## Tests to add next

### Contract tests

- generated event registry matches emitted marker/span names;
- every registered event has classifications;
- every official metric has a valid source rule;
- unknown event type behavior is stable;
- schema migration fixtures.

### Timing honesty tests

- same-process marker pair becomes official/solid;
- epoch-aligned STS span remains diagnostic/hatched;
- rich collection makes the rep diagnostic-only;
- diagnostic pass cannot produce CI-gating metric;
- missing end marker produces invalid/no fake metric.

### Privacy tests

Canary data in:

- SQL text;
- row cells;
- connection strings;
- saved profile password;
- provider message;
- exception text;
- artifact path;
- STS2 journal payload;
- report and export bundle.

Assert no plaintext in default stores, reports, histories, exports, logs, or UI dumps.

### Import safety tests

- malicious zip paths;
- oversized artifacts;
- invalid JSONL;
- old schema;
- mixed run ids;
- script-bearing HTML;
- symlinks;
- path tricks in delete run;
- partial/corrupt markers.

### Cross-repo integration tests

- CLI run imported into console preserves official eligibility;
- self-test run appears in Perf History with local/exploratory provenance;
- forwarded `rpc.*`, `webview.*`, and `sts.*` spans render diagnostic;
- STS2 journal collected by perftest maps to rep evidence;
- scenario parity between CLI and in-proc for one query scenario.

### UI scale tests

- 20k live events;
- 100k imported events;
- 1000 run history source;
- large artifacts;
- waterfall zoom/pan performance;
- virtualized table row stability;
- no viewer-internal pollution.

## Decisions to freeze soon

1. **Schema ownership**: where does the shared observability contract live?
2. **Metric terminology**: official vs measurement-eligible vs CI-gating.
3. **Self-test status**: can local self-test ever gate, or is it always exploratory?
4. **Bundle format**: directory bundle, zip bundle, manifest, signatures/hashes, artifact rules.
5. **Capture policy**: exact elevated capture UX, duration, reason, local-only guarantee, STS2 limits.
6. **STS2 viewer timing**: when is the observer contract stable enough for live integration?
7. **SQLite in extension**: native driver, worker process, WASM, or keep directory provider as primary?
8. **Scenario maturity**: who owns promotion to CI gate?
9. **Telemetry boundary**: local-only stores now, but what aggregate non-sensitive telemetry is allowed in CI dashboards?
10. **Support workflow**: what is the approved safe bundle for issue sharing?

## Definition of done for the next phase

The next phase is successful when:

- a regression found in CI can be opened in the Debug Console with full provenance;
- official and diagnostic evidence cannot be confused in reports or UI;
- a local self-test can reproduce the same scenario shape as the CLI;
- run imports are safe, validated, and schema-versioned;
- redaction canaries stay out of all default artifacts;
- Debug Console analysis clearly labels gaps, missing correlation, and timing class;
- STS2 journals can be attached as diagnostic evidence without weakening privacy or replay truth;
- the scenario catalog shows maturity, owners, flake/noise health, and gate status;
- developers have named diagnostic recipes for common “why slow?” questions.

At that point, the system stops being a collection of excellent tools and becomes a daily performance engineering loop: measure, explain, reproduce, fix, prove, and archive.
