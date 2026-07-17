# Inline Completions Observability — Current Design, Comparison, and Unification Plan

**Updated: 2026-07-16.** Code basis: `vscode-mssql`, `perftest`, `sqltoolsservice` on their
`dev/query` branches. All extension paths are relative to `vscode-mssql/extensions/mssql/`.
When this doc and the branch disagree, the branch wins and this doc should be updated.

This doc answers three questions:

1. **What did we build for inline AI completions observability** (data collection, UX,
   history tracking, replay) and why is it shaped the way it is?
2. **How does it compare** to the other observability mechanisms in the stack — the diag
   substrate + Debug Console, the STS2 envelope journal + deterministic replay, and the
   perftest harness (including settings-group A/B and the Perf Test History page)?
3. **How do we unify them into one clean, scalable story** — minimally merging the full
   inline UX into the Debug Console, ideally consolidating journals — without losing
   anything the inline system does today? §5 is an execution plan detailed enough to hand
   to a coding agent.

---

## 0. Executive summary

The stack has **four observability mechanisms** that grew for different reasons:

| # | Mechanism | One-liner |
|---|---|---|
| 1 | **Diag substrate + Debug Console** | Classified, redacted protocol-metadata events (`DiagEvent`), journaled to a session store, rendered live in the console. The "everything" plane. |
| 2 | **Inline completions capture/replay** (on the generic `featureCapture/` framework) | Rich, payload-carrying events (full prompts, raw model replies, schema context), gated capture, its own trace files, its own viewer, replay with settings overrides and experiment matrices, pivot-table session analysis. |
| 3 | **STS2 envelope journal + `sts2-replay`** | Write-ahead journaled service envelopes with `corr`/`cause` causality; deterministic *verification* replay through a pure reducer. |
| 4 | **perftest harness** | Marker-derived official metrics, run directories + SQLite history, regression gates, settings-group A/B scenarios, reports; surfaced in-product via the Perf Test History page. |

**The central finding:** the inline-completions split is not an accident to erase — it is a
**two-plane architecture** that the whole system should adopt deliberately:

- **Plane A — the classified metadata plane** (`DiagEvent`). Always-on capable, redaction
  at a single choke point, safe to journal, forward to the harness, and upload centrally.
  Prompts, model replies, SQL text and row data must **never** ride this plane — this
  invariant is load-bearing for the entire privacy story
  (`src/diagnostics/featureCapture/captureStore.ts:11` states it verbatim).
- **Plane B — the rich feature-capture plane** (`FeatureCaptureStore` + trace files).
  Payload-carrying, consent-gated, feature-scoped. This is where debugging fidelity lives
  (full prompts/replies) and where *experimental replay* is possible, because the events
  carry everything needed to re-drive the feature.

What *should* be unified is not the two record formats but everything around them:
**one storage lifecycle** (the session-diag store's manifests/retention/integrity),
**one UX surface** (the Debug Console), **one correlation identity** (dual-stamped IDs so
the planes cross-reference), **one replay pattern** (the generic replay engine +
per-feature hosts, surfaced in a single Replay Lab), and **one analysis chrome**
(shared pivot/facet components, per-feature dimensions/metrics — per-feature analysis
stays specialized on purpose).

The plan (§5) delivers, in order:

- **Phase 0** — correlation stitching + trace-envelope metadata (small, unblocks everything).
- **Phase 1** — *the minimal ask*: the full inline UX (Live + Sessions + Replay
  builder/matrix) merged into the Debug Console by **de-forking**, then retiring the
  standalone panel.
- **Phase 2** — *the ideal ask*: rich capture becomes a **second stream inside the
  session-diag store** (one journal directory, one manifest, one retention/validation
  story; crash-durable JSONL instead of save-on-deactivate) without losing any current
  capability.
- **Phase 3** — Replay Lab as the umbrella replay surface: a `ReplayableFeature`
  registration contract, generalized settings-group matrices, Query Studio as the second
  live tenant, and a graduation seam to perftest `userSettings` A/B scenarios.
- **Phase 4** — analysis chrome convergence (shared components, per-feature providers).
- **Phase 5** — horizon: STS2 Replay Lab tab (verification semantics, offline import),
  central upload of curated traces under policy, perftest completions scenarios.

---

## 1. The inline completions observability system today

Ported from the `completions/vscode-mssql` project (branch `dev/karlb/completions`; see
`src/constants/constants.ts:457`). Historically it **predates** the Debug Console — the
console's UX bar was explicitly modeled on it (`01-architecture.md` §8 "Design lineage").
When ported onto `dev/query`, the diag substrate already existed with its
payloads-never-ride-DiagEvents invariant, so the rich system stayed parallel **by
design**, and was partially generalized into a reusable framework.

### 1.1 The layering: generic framework + completions tenant

- **Generic framework** — `src/diagnostics/featureCapture/`:
  - `captureStore.ts` — `FeatureCaptureStore<TEvent, TOverrides>`: bounded in-memory ring
    (default capacity 500), `addEvent/updateEvent/mutateEvent/clearEvents`, an override
    surface, `onDidChange`, and capture gating `shouldCapture = panelOpen || recordWhenClosed`.
  - `replayEngine.ts` — `FeatureReplayEngine`: cart → queue → sequential single-flight
    drain with cancellation; matrix runs; emits `replay.run` / `replay.item` spans into
    the diag substrate (the narration seam).
  - `traceCodec.ts` — versioned JSON envelope (`FeatureTraceEnvelope`, `version: 1`),
    redaction walker, oldest-first size-cap truncation (`_truncated: true`).
  - `traceFiles.ts` — file naming, folder resolution, disk write, folder watcher, index scan.
  - `settingsSnapshot.ts` — emits classified `settings.snapshot` / `settings.changed`
    state events onto the diag substrate (the ambient-config baseline for captured sessions).
- **Completions tenant** — `src/copilot/inlineCompletionDebug/` (controller, store
  singleton, profiles, trace persistence/serializer/loader) + the live emitter
  `src/copilot/sqlInlineCompletionProvider.ts`.
- **Second tenant already exists**: Query Studio run capture/replay
  (`src/queryStudio/replay/qsRunCapture.ts`, `queryStudioReplayController.ts`,
  `src/sharedInterfaces/queryStudioReplay.ts`) uses the same framework. So "inline
  completions observability" is really "the first tenant of the feature-capture plane."

### 1.2 Data collection — the event and reply format

`InlineCompletionDebugEvent` (`src/sharedInterfaces/inlineCompletionDebug.ts:117`) is a
rich record, nothing like a `DiagEvent`: trigger/category/intent flags, model identity
(family/id/vendor), latency, token counts, schema-context stats, the applied overrides,
and — the part the substrate can never carry — `promptMessages[]` (role + full content),
`rawResponse`, `sanitizedResponse`, `finalCompletionText`, `schemaContextFormatted`, plus
a free-form `locals` diagnostic bag (prefix/suffix text, budget profile, degradation
steps, …). Result vocabulary: `success | accepted | skipped | emptyFromModel |
emptyFromSanitizer | noModel | noPermission | error` (+ debug-only `cancelled | pending |
queued`).

Collection mechanics (`sqlInlineCompletionProvider.ts`):

- A **pending event** is added at model-request start and **updated in place** to its
  terminal result (`recordPendingDebugEvent`/`recordDebugEvent`, lines 436–480).
- Acceptance is a **post-hoc mutation**: `markAccepted(eventId)` flips
  `success → accepted` when VS Code reports the completion was taken (line 150). This
  matters for the storage plan (§5 Phase 2): the record is not append-once.
- The provider **dual-emits**: each request also opens a `completions.request` diag span
  and emits `completions.stage` / `completions.result` DiagEvents (protocol metadata
  only — trigger, stage, result, latency), correlated by the span's `requestTraceId`.
  **Gap:** that substrate `traceId` is *not* stored on the rich event — today the two
  planes correlate only loosely (fixed in Phase 0).

### 1.3 Trace files (history persistence)

- **Format**: one pretty-printed JSON file per session — `FeatureTraceEnvelope` =
  `{ version: 1, exportedAt, _savedAt, _extensionVersion, _truncated?, overrides,
  recordWhenClosed, customPromptLastSavedAt?, events[] }`. **Not JSONL, no manifest, no
  integrity checks** — a deliberate contrast to the session-diag store.
- **Naming/location**: `mssql-copilot-trace-<timestamp>.json` under
  `mssql.copilot.inlineCompletions.trace.folder` (with `~` expansion) or the default
  `<globalStorage>/copilot-completion-traces`.
- **When written**: on extension **deactivate** if `trace.captureEnabled`, or on-demand
  (`saveTraceNow` reducer). A crash loses the in-memory ring — another Phase 2 fix.
- **Size policy**: no rotation; oldest-first truncation to `trace.maxFileSizeMB`
  (default 50).
- **Redaction**: opt-in `trace.redactPrompts` — replaces prompt/response/schema-context
  text with `[REDACTED]` at write time (`traceSerializer.ts:38`). Default is **not**
  redacted: this plane is consent-gated, local-only, and exists precisely to keep full
  fidelity.
- Arbitrary export/import via save/open dialogs also exists (`exportSession`/`importSession`).

### 1.4 UX — two surfaces, one of them a fork

- **Standalone panel** — "Copilot Completion Debug"
  (`mssql.openInlineCompletionDebug` → `InlineCompletionDebugController`, 2,501 lines;
  webview `src/webviews/pages/InlineCompletionDebug/`). Tabs:
  - **Live** — toolbar (profile picker: focused/balanced/broad/custom; model + continuation
    model; schema budget; per-session overrides; record-when-closed; custom system prompt;
    replay-cart button), the live **EventGrid**, and the **DetailPane** with per-reply tabs:
    Summary / System Prompt / User Prompt / Raw Response / Sanitized / Schema Context /
    Locals Dump / Telemetry, plus computed sanitization-steps notes and copy actions.
  - **Sessions** — see §1.6.
  - **ReplayTraceBuilder** — overlay drawer with *builder* and *matrix* views (§1.5).
- **Debug Console "Completions" page** — `webviews/pages/DebugConsole/completionsPage.tsx`:
  an enablement card plus, when the feature gate is on, a **forked** copy of the Live tab
  served by `src/diagnostics/completionsDebugConsoleHost.ts` over pull-based RPCs
  (`DcIcDebugStateRequest`/`DcIcDebugActionRequest` + throttled
  `DcIcDebugChangedNotification`). The fork's own header says it: *"the standalone panel
  remains the reference implementation until replay parity is confirmed, then this and
  the panel converge."* Replay and sessions reducers are stubbed with an info message.
  When the gate is **off**, the page honestly renders only the substrate's classified
  `completions.*` DiagEvents — a good pattern to keep.
- **Known wart** (documented in the fork, lines 168–171): capture gating rides a single
  non-refcounted `setPanelOpen` flag; the console host snapshots/restores it so it
  doesn't stop a concurrently open panel from recording.

### 1.5 Replay — experimental re-execution with settings overrides

Built on the generic `FeatureReplayEngine` with a completions `FeatureReplayHost`
(`inlineCompletionDebugController.ts:218`).

- **Entry points**: replay one event; replay a whole session trace; build a **cart** of
  event snapshots; **queue** the cart; or run a **matrix**.
- **What re-executes** (`replaySourceEvent`, controller lines 1428–1841): the *full live
  pipeline* under the chosen config — re-selects the model, re-fetches **fresh** schema
  context (falling back to the captured `schemaContextFormatted`; the source is tracked
  as `current|captured|unavailable|disabled`), rebuilds prompts through the shared
  builder, calls `model.sendRequest`, re-sanitizes, and records a **new** event into the
  same store, stamped with replay tags.
- **Settings-override mechanism**: the replay config *is* the session-override surface
  (`InlineCompletionDebugOverrides`: profile, model selectors, schema context on/off +
  budget, debounce, maxTokens, categories, forceIntentMode, custom system prompt…). Per
  cart row a **config mode** — `snapshot` (config as captured when added) | `override`
  (snapshot + row-specific partial) | `live` (current toolbar config).
- **Replay experiments (matrix)**: `runReplayMatrix(profileIds, schemaBudgetProfileIds)`
  runs the cart across the **cartesian product** of preset profiles × schema-budget
  profiles (warning threshold at 100 cells). This is the in-session cousin of perftest's
  settings-group A/B (§2.4).
- **Correlation of results**: replayed events carry
  `replayTraceId / replayRunId / replayMatrixCellId / replaySourceEventId` tags, so the
  Sessions analysis can pivot originals vs. replays vs. matrix cells. The engine also
  narrates `replay.run` / `replay.item` spans onto the diag substrate, so replays are
  visible on the console timeline.

### 1.6 Session history analysis

- **Dataset**: the trace-file index (folder scan + watcher + per-file include toggles +
  add-file/change-folder), lazily loaded, with a 100k-event warning.
- **Engine**: pure functions in `src/sharedInterfaces/inlineCompletionAnalysis.ts` —
  filter/group/pivot (primary + secondary dimension), facet counts, and metrics: count,
  latency mean/median/p50/p95/p99/min/max, token sums/means, and
  accept/cancel/reject/skip/error rates.
- **14 dimensions**: model, profile, schemaMode, schemaSizeKind, intentMode, result,
  trigger, language, inferredSystemQuery, completionCategory, and the four replay
  dimensions (replayTrace/replayRun/replayMatrixCell/replaySourceEvent).
- **UX** (`sessions/SessionsTab.tsx`): summary tiles, facet filter rail, pivot table
  with drilldown to the same DetailPane, latency histogram, and "send to replay cart."

This is exactly the "specialized per-feature analysis" the unified story should keep —
acceptance rate by model × schema budget is meaningless for any other feature.

---

## 2. The other mechanisms (what the inline system must coexist with)

Condensed; authoritative docs are linked. Read §3 for the direct comparison.

### 2.1 Diag substrate + Debug Console (the classified metadata plane)

See `01-architecture.md` / `02-debug-console.md`. Essentials:

- `diag` singleton (`src/diagnostics/diagnosticsCore.ts`) → `classify()` redaction choke
  point (`redaction.ts`; capture modes off/redacted/digest/time-bounded-full; secrets
  never plaintext) → dynamic sinks: **LiveTailSink** (ring 5,000, exact gap records),
  **SessionDiagSink** (JSONL segments of 5,000 events under
  `<storeRoot>/sessions/<sessionId>/` with a `SessionManifest` — seq ranges, dropped
  ranges, sizeBytes, integrity validation, retention by count/age/size), **PerfModeSink**
  (harness wire + forwarded `rpc.*`/`webview.*`/`sts.*` spans), console archive, self-test tap.
- `DiagEvent` (`mssql.diag.event/1`): seq/session identity, process/feature/kind/type,
  status, correlation (`traceId`, `causeEventId`, entity bindings, root-action window),
  `timingClass` honesty labels, and a mandatory classification stamp `cls`.
- Debug Console pages: Overview, Consolidated Trace (filter language), Waterfall,
  Perf Test History, Session History, Completions (the fork), SQL Activity / SQL Data
  Plane / feature pages, Exports, Settings — plus a **gated Replay Lab placeholder**
  explicitly waiting for "the completions replay adapter to migrate into the host and
  STS2 replay hardening."
- Vocabulary is governed by `perftest/packages/observability-contracts` (registry +
  `deriveEligibility()` + Trace Identity V1 + correlation lint), vendored into the
  extension as `sharedInterfaces/observabilityContract.generated.ts`. The registry
  already documents the `completions.*` and generic `replay.*` families, including the
  rule that prompt text never rides them.
- **No replay of any kind** in this plane — it observes; it cannot re-drive.

### 2.2 STS2 envelope journal + deterministic replay

See `sqltoolsservice/docs/sts2/{OBSERVABILITY,TRACE-SCHEMA}.md`. Essentials:

- Every service input/output becomes an `Sts2Envelope` (`sts2.envelope/1`: runId, gapless
  `seq`, kind, `corr`, `cause` = seq of producing envelope, configVersion, canonical
  payload `digest`), journaled **write-ahead** to JSONL segments (64 MiB, sha256-chained
  manifest) before the core dispatches it; observers hang off one seam (`IEnvelopeSink`).
- Capture modes (`full|digest` rows, `text|digest` SQL; product default digest/digest)
  are the verbosity knob; changes journal `config.changed` and bump `configVersion`.
- `tools/sts2-replay` re-runs recorded inputs through the **pure reducer**
  (`run|verify|until|diff|explain|export-check`), injecting recorded `effect.res` instead
  of touching a database. Outcome is `Verified | Diverged | Incomplete` — this is
  **verification replay** (did the recorded run reproduce exactly?), not experimentation.
- Reaches the client only by **pull** (`v2/diagnostics.health/state/setCapture/exportLog`)
  or by reading journal files; nothing streams to the extension. The legacy `StsDiag`
  loopback bridge is a separate, metadata-only channel feeding the substrate's console lanes.

### 2.3 perftest harness + Perf Test History

See `perftest/docs/` and `04-perftest-integration.md`. Essentials:

- Markers (localhost HTTP sink → `markers.jsonl`) are the only source of official
  metrics; the normalizer writes `result.json`; runs live in self-describing directories
  and a SQLite store whose `official_metric_samples` view structurally enforces the
  official-metric rules; Welch-t regression gates against environment-hash-matched baselines.
- **Settings-group A/B exists today** as paired scenarios differing only in
  `ScenarioSpec.userSettings` (seeded into `User/settings.json` **before launch** — the
  mechanism for activation-time settings like `mssql.sqlDataPlane.backend`), e.g.
  `registerQueryStudio10kBackendVariant()` and the 20-scenario
  `config.backend-shapes.local.jsonc` matrix, compared via `perftest head-to-head`.
- The Debug Console's **Perf Test History** page reads the run-directory contract
  directly (index + lazy artifacts); in-product **self-test** (`@mssqlperf/inproc`)
  writes the same layout, so local runs appear with no import step. Eligibility metadata
  distinguishes `controlledHarness` from `interactiveHost` (exploratory) provenance.
- Central observability: `perftest push` + Debug Console upload project runs/sessions
  into a shared SQL Server store under upload policies; the `DataClassification`
  taxonomy already includes `model.prompt` / `model.response` (refused by default policy).

### 2.4 Query Studio — one foot in each plane (the proof of the pattern)

Query Studio is instrumented on the substrate (the `mssql.queryStudio.*` marker family;
`sts2.query.stats` pipeline diagnostics arriving via the STS bridge) **and** uses the
feature-capture plane for run capture/replay (`qsRunCapture.ts` keeps SQL text in the
rich store, emits only a `queryStudio.runRecord.captured` state event onto the
substrate). It is the template for how every payload-bearing feature should split.

---

## 3. Comparison — same problems, different answers

| Concern | Diag substrate | Inline completions (feature capture) | STS2 journal | perftest |
|---|---|---|---|---|
| Record format | `DiagEvent` (classified metadata, closed schema) | Rich typed event, full payloads, `locals` bag | `Sts2Envelope` (canonical digest, closed kinds) | `Marker` + normalized `Metric` |
| Correlation | traceId/causeEventId/entity + Trace Identity V1 + lint | own event ids + replay tags; **substrate traceId not stored** (gap) | `corr` + `cause` seq chain | runId/repId/scenarioId + marker correlationId |
| Storage | JSONL segments + manifest + retention + validation + backfill | single JSON file, save-on-deactivate, size-cap truncation, no manifest/integrity | JSONL segments, sha256-chained manifest, write-ahead | run directories + SQLite + central SQL |
| Privacy | classification choke point; secrets never plaintext; capture modes | consent-gated capture; opt-in redaction; full fidelity is the point | digest-elision capture modes; secret side-table | classification-governed attrs; upload policies |
| Capture gating | settings + sink registration | viewer-open ∥ recordWhenClosed | always-on when STS2 enabled | PERF_MODE only |
| UX | Debug Console (9+ pages) | standalone panel + partial console fork | none in-product (CLI + pull RPCs) | HTML reports + Perf Test History page |
| History/analysis | Session History, waterfalls, KPIs, anomalies | trace index + 14-dimension pivot analysis | journal files; `until`/`explain`/`diff` | SQLite trends, regression verdicts, head-to-head, investigation diff |
| Replay | none (gated placeholder) | **experimental re-execution** + settings overrides + matrix | **deterministic verification** | **scenario re-execution across settings groups** |
| Reuse across features | universal by design | generic framework; 2 tenants (completions, QS) | service-only | any scenario |

### 3.1 The three kinds of "replay" (do not blur them)

1. **Verification replay** (STS2): re-run *recorded inputs* through *pure logic*; success
   = byte-identical outputs. Answers "is this journal complete and was the behavior
   deterministic?" Requires event-sourcing discipline; impossible for a feature that
   calls a live LLM.
2. **Experimental re-execution** (inline completions, QS runs): re-drive a captured
   scenario against *live systems* under a *different config*; outputs are expected to
   differ — that's the point. Answers "would this config do better?"
3. **Harness scenario replay across settings groups** (perftest): re-run a *scenario
   spec* (not captured events) in a controlled environment across `userSettings`
   variants; answers "which config is faster/regressed, with gate-grade rigor?"

The unified story needs all three, clearly labeled, sharing UX chrome where it helps
(cart/matrix/run-list) but never pretending to be one semantics. The boundary between
(2) and (3) is precise: **in-session-flippable settings belong to Replay Lab matrices;
activation-time settings belong to perftest `userSettings` variants** — with a
graduation seam from one to the other (§5 WI-3.5).

### 3.2 Why the inline system is the way it is

- It **came first** and was built as a self-contained lab; the console later borrowed its
  UX density patterns (per `01-architecture.md` §8).
- Its events **must** carry prompts/replies to be useful — which the substrate
  constitutionally forbids — so parallel capture was correct, not lazy.
- Its replay needs the **full feature config surface** as the override type, which no
  generic mechanism offered.
- The port already paid down the biggest debt: the generic `featureCapture/` framework
  exists, has a second tenant, and its replay engine already narrates onto the substrate.

### 3.3 What each side does better (the merge inherits both)

**Inline system, worth generalizing:** experimental replay with config modes and
matrices; reply-centric detail UX (raw vs sanitized vs final, sanitization-step notes);
pivot/facet analysis with replay dimensions; profile presets as first-class experiment
axes; send-to-cart curation from history.

**Main system, inline should inherit:** durable JSONL journaling with manifests,
integrity validation, retention, and crash safety; a single store lifecycle with
provenance; the correlation identity + lint; one UX shell instead of a standalone panel
plus a drifting fork; central-upload policy machinery; scale patterns (virtualized
tables, lazy artifacts, index caching).

---

## 4. Target architecture — one story that scales

**Principle: two planes, one everything-else.**

```text
                    ┌───────────────────────────────────────────────┐
                    │            MSSQL Debug Console                │
                    │  Overview · Trace · Waterfall · Perf History  │
                    │  Session History · Feature pages · Settings   │
                    │  ┌─────────────────────────────────────────┐  │
                    │  │ Completions page (full: Live+Sessions)  │  │
                    │  │ Replay Lab (features + [STS2 gated])    │  │
                    │  └─────────────────────────────────────────┘  │
                    └───────▲───────────────────────▲───────────────┘
                            │                       │
              Plane A: DiagEvents          Plane B: rich feature events
              (classified metadata)        (payloads, consent-gated)
                            │                       │
        ┌───────────────────┴───────┐   ┌───────────┴──────────────────┐
        │ diag core → classify →    │   │ FeatureCaptureStore ring     │
        │ sinks (live/store/perf)   │   │ + FeatureCaptureJournal      │
        └───────────────────┬───────┘   └───────────┬──────────────────┘
                            │      one store dir     │
              <storeRoot>/sessions/<sessionId>/      │
                ├── manifest.json  (covers BOTH planes: segments,
                │                   richStreams[], retention, integrity)
                ├── events/segment-NNNNNN.jsonl      (Plane A)
                └── rich/<featureId>/segment-NNNNNN.jsonl  (Plane B)

   Cross-plane identity: rich events carry {sessionId, substrate traceId};
   substrate completions.result / *.runRecord.captured events carry richEventId.

   Replay: ReplayableFeature registry → shared cart/queue/matrix UX in Replay Lab
   → per-feature replay hosts re-execute → results land in the feature's store,
   tagged, narrated as replay.* spans on Plane A.
   Graduation: Replay Lab matrix cell → perftest scenario userSettings variant.
```

**The Feature Observability Pattern** — what any new payload-bearing feature does
(completions and Query Studio both already fit; this makes it a checklist):

1. Register its `feature.*` event/marker names in the observability-contracts registry
   (classified attrs; prompt/SQL payload rule stated).
2. Emit Plane-A protocol-metadata events/spans for every request (works even when rich
   capture is off — the Completions page's gate-off view proves the value).
3. If it needs fidelity: instantiate a `FeatureCaptureStore` tenant with a typed event +
   overrides surface; declare its settings-snapshot spec.
4. If it wants replay: implement a `FeatureReplayHost` and register as a
   `ReplayableFeature` (config surface, matrix axes, analysis dimensions).
5. Get for free: console hosting, journaled storage with manifests/retention/validation,
   Replay Lab UX, analysis chrome, export, and (policy permitting) central upload.

**What deliberately stays separate:**

- The two record formats. A prompt never becomes a `DiagEvent`; a `DiagEvent` never grows
  a payload escape hatch.
- STS2 verification replay semantics (its Replay Lab tab renders journals; it never
  pretends to be an experiment runner).
- Perf Test History (official-metric provenance) vs. feature session analysis
  (experimental fidelity). They may share chart/table components, never data semantics.
- Per-feature analysis dimensions/metrics — specialized is better here.

---

## 5. Execution plan

Ordered to reduce rework: de-fork before merging UX; correlation before storage; storage
before Replay Lab surfacing (the Lab reads stores). Each work item lists concrete files
and acceptance criteria. Phases 0–1 are independent of Phase 2 and can ship alone —
Phase 1 *is* the minimal outcome.

### The "don't lose anything" checklist (regression gate for every phase)

Full prompt/response/locals fidelity · record-when-closed · trace redaction option ·
size caps · export/import session JSON · profile presets + custom system prompt · model
& continuation-model selection UX · replay single/session/cart/queue/matrix + the three
config modes · replay tags + pivot dimensions · facet/pivot/drilldown/histogram analysis ·
external trace folder (watcher, add-file, change-folder) · acceptance marking
(post-hoc `success → accepted`) · gate-off page shows classified events only · a
concurrently open second viewer never stops capture.

### Phase 0 — Correlation stitching + envelope metadata (small; do first)

**WI-0.1 Dual-stamp cross-plane identity.**
- Add to the generic event path an optional link block; for completions, populate it in
  `createDebugEvent` (`sqlInlineCompletionProvider.ts:325`) from the already-threaded
  `requestTraceId` plus `diag`'s current `sessionId`:
  `link?: { sessionId: string; traceId?: string }` on `InlineCompletionDebugEvent`
  (additive, optional — old traces still load).
- Stamp the rich event id back onto Plane A: add `richEventId` to the
  `completions.result` emission (`sqlInlineCompletionProvider.ts:451`) and to the
  `completions.request` span end. Register the attr (classification
  `diagnostic.metadata`) in `perftest/packages/observability-contracts/src/registry/event-types.json`,
  run the generate step, re-vendor `sharedInterfaces/observabilityContract.generated.ts`
  (the conformance + vendor-sync tests enforce this loop).
- Do the same for Query Studio run capture (`qsRunCapture.ts` already emits
  `queryStudio.runRecord.captured`; add the reverse link on the rich record).
- **Accept:** unit test walks `completions.result` → rich event and rich event →
  substrate trace; correlation lint has no new orphans; conformance suites green in both repos.

**WI-0.2 Trace envelope v2 (prep for Phase 2).**
- `traceCodec.ts`: bump `FeatureTraceEnvelope` to `version: 2` adding `featureId`,
  `sessionId?`, `schemaName: "mssql.featureTrace/2"`. Loader (`traceLoader.ts
  normalizeTraceFile`) accepts v1 and v2 (v1 infers `featureId: "completions"`).
- **Accept:** round-trip tests for v1 fixture + v2; Sessions tab loads both.

### Phase 1 — Inline UX fully merged into the Debug Console (the minimal outcome)

**WI-1.1 De-fork by extraction (prerequisite for everything).**
- Create `src/copilot/inlineCompletionDebug/inlineCompletionDebugHostCore.ts`: move the
  reducer bodies + `createState` assembly out of `InlineCompletionDebugController` into a
  host-agnostic core parameterized by
  `{ extensionContext, schemaContextService, showDialogs, getConfigurationTarget }`.
  The standalone controller and `completionsDebugConsoleHost.ts` become thin adapters;
  **delete every forked body** in the console host (the fork header itself declares this
  convergence as the plan). Include the replay host creation (`createReplayHost`) and
  sessions logic (folder scan/watch/load) in the core.
- **Accept:** the console host file shrinks to adapter-only; a reducer-parity test
  dispatches every `InlineCompletionDebugReducers` key through both adapters against the
  same store and asserts identical state effects; no `FORKED` markers remain.

**WI-1.2 Full reducer surface over the console RPC.**
- `DcIcDebugActionRequest` is already `{name, payload}` — extend the console host
  dispatch to the full surface (sessions\*, replay\*, import/export, saveTraceNow,
  matrix). Long-running replay runs already publish progress through store state
  (`replay.runs/queueRows`) + the throttled `DcIcDebugChangedNotification`; verify
  cancellation (`cancelReplayRun`) round-trips.
- Host-side dialogs (export/import save dialogs, change-folder picker) already run in the
  extension host — no webview change needed.
- **Accept:** every reducer callable from the console page; replay matrix run started,
  observed, and cancelled from the console with the standalone panel closed.

**WI-1.3 Mount the full experience in the Completions page.**
- Generalize the standalone webview's state provider so components are host-agnostic:
  extract the context contract used by `InlineCompletionDebug/` components; implement it
  in `DebugConsole/completionsDebug/consoleStateProvider.tsx` (replacing the forked
  component subset with direct imports of `TabBar`, Live page, `SessionsTab`,
  `ReplayTraceBuilder`, `DetailPane`, …).
- `completionsPage.tsx`: keep the enablement card + gate-off classified view; when the
  gate is on, render the full tabbed app (Live / Sessions, replay drawer).
- Bundle size: check `scripts/esbuild-utils.js` for page-level code-splitting; the
  Sessions/Replay chunks should lazy-load within the DebugConsole bundle.
- **Accept:** manual parity checklist (every §1.4–§1.6 capability) passes inside the
  console; webview scale tests still pass; gate-off privacy behavior unchanged.

**WI-1.4 Refcounted capture gating.**
- Replace `FeatureCaptureStore.setPanelOpen(boolean)` with
  `acquireViewer(): vscode.Disposable` (internal refcount; `isPanelOpen()` ≡ refcount>0).
  Update both hosts + tests; remove the snapshot/restore workaround in
  `completionsDebugConsoleHost.ts:168-171`.
- **Accept:** console open + panel open, dispose either → capture continues; dispose both
  → capture stops (unless recordWhenClosed).

**WI-1.5 Retire the standalone panel.**
- Re-route `mssql.openInlineCompletionDebug` to open the Debug Console **deep-linked** to
  the Completions page (add a route param to the console open command). Keep the
  standalone controller behind `mssql.copilot.inlineCompletions.debug.standalonePanel`
  (default `false`) for one milestone as an escape hatch, then delete the controller +
  `webviews/pages/InlineCompletionDebug` entry point (components live on, imported by the
  console).
- **Accept:** command opens the console at Completions; with the escape-hatch setting on,
  the old panel still works off the shared core (not a fork).

**WI-1.6 Tests.**
- Reducer parity (WI-1.1), capture refcount (WI-1.4), console-page privacy canary
  (prompts render only when gate on; never appear in Plane-A queries), replay-tag
  integrity after a console-initiated matrix run, deep-link routing.

### Phase 2 — One journal: rich streams inside the session-diag store (the ideal outcome)

Goal: `<storeRoot>/sessions/<sessionId>/` holds **both planes**; one manifest, one
retention/validation/lifecycle; rich capture becomes crash-durable. The trace-file
format remains supported for import/export and external folders.

**WI-2.1 `FeatureCaptureJournal` (new, in `featureCapture/`).**
- Append-only JSONL under `rich/<featureId>/segment-NNNNNN.jsonl` with three line types:
  `{"t":"hdr", ...envelope-v2-metadata}` (first line per segment),
  `{"t":"evt", event}` and `{"t":"amend", id, patch}` — amendments cover
  `updateEvent`/`mutateEvent`/`markAccepted` (merge on load, last-wins per field).
  Write-behind batching mirroring `SessionDiagSink` (500 ms flush, bounded buffer,
  drop accounting); segment roll at 5,000 lines.
- Wire into `FeatureCaptureStore`: when persistence is enabled
  (`trace.captureEnabled`) and capture is active, `addEvent/updateEvent/mutateEvent`
  write through. **Redaction at append time** honoring `trace.redactPrompts`
  (amendments must be redacted with the same walker so merges can't resurrect text).
- **Accept:** kill -9 mid-session loses ≤ one flush interval of rich events; load merges
  amendments correctly (acceptance flips survive reload); redacted stream contains no
  prompt text (canary).

**WI-2.2 Manifest + retention extension.**
- `SessionManifest` v2 (`mssql.diag.sessionManifest/2`, v1 still readable): add
  `richStreams: [{ featureId, segments[], events, sizeBytes, redaction:
  "full"|"redactPrompts", truncatedRanges[] }]`. `SessionDiagSink`/`sessionStore.ts` own
  the manifest writes; the capture journal reports its segment stats through a small
  registration API rather than writing the manifest itself.
- Retention: session-level eviction (count/age/`maxTotalMB`) now includes rich-stream
  bytes; per-stream cap honors `trace.maxFileSizeMB` semantics via oldest-segment
  eviction recorded in `truncatedRanges`.
- **Accept:** `validateStore()` covers rich segments (existence, torn lines, header
  presence); retention test evicts oldest sessions including their rich streams;
  Settings-page health card reports rich-stream totals.

**WI-2.3 Sessions dataset selector reads the store.**
- `traceLoader.ts` gains a store-backed provider: enumerate stored sessions' rich streams
  (from manifests) alongside (a) the legacy/external trace-file folder (watcher and
  add-file preserved — external files remain a first-class import path) and (b) the
  current live ring. Facet inference unchanged.
- `exportSession` still writes a single self-contained v2 JSON file (now assembled from
  ring + journal); `importSession` unchanged.
- Optional: `mssql.copilot.completions.trace.migrateToStore` one-shot command; and make
  the dead `trace.syncToDatabase` stub either do the central-upload preview path or remove it.
- **Accept:** a session recorded yesterday appears in the Sessions dataset list without
  any file dialog; legacy `mssql-copilot-trace-*.json` files still load; export/import
  round-trips.

**WI-2.4 Privacy boundaries for the consolidated store.**
- `DcExportRequest` (Plane-A JSONL export) must **not** include rich streams unless the
  user explicitly checks a new "include rich feature streams" option (default off).
- Central upload: `projectDiagSession` refuses `rich/` streams under the default policy
  (the taxonomy already classifies `model.prompt`/`model.response`); the preview shows
  them as refused-with-counts. Add a policy fixture test in
  `perf-contracts/src/central/policies` fixtures.
- Extend `debugConsolePrivacyCanary.test.ts`: sentinel prompt text placed via rich
  capture never appears in Plane-A segments, exports, harness wire, or central preview.
- **Accept:** all canaries green.

### Phase 3 — Replay Lab: one consistent replay pattern

**WI-3.1 `ReplayableFeature` registry** (`featureCapture/replayRegistry.ts`):
`{ featureId, label, store, createReplayHost(), configSurface: { profiles,
overridesSchema, describeConfig }, matrixAxes: MatrixAxis[], analysisRef }` where
`MatrixAxis = { id, label, options: {id,label}[] }` and the host resolves a cell config
from selected axis options (generalizing today's hard-coded profile × schema-budget
pair). Register completions (axes: profile, schemaBudgetProfile) and Query Studio
(axes: e.g. in-session tuning profile; backend is activation-time → explicitly *not* an
axis, see WI-3.5).

**WI-3.2 Replay Lab page (replace the `GatedPage`).**
- Feature picker (registered features) + the shared cart/builder/matrix UX: move
  `ReplayTraceBuilder` internals to `webviews/pages/DebugConsole/replayLab/` as generic
  components parameterized by the feature's config surface; the Completions page keeps
  its embedded entry points (send-to-cart etc.) but the drawer is the same component.
- Runs list with status/cancel; per-run link "open results in <feature> analysis"
  (deep-link to Sessions tab filtered to `replayRunId`).
- Keep an "STS2 journals" section on the page **still gated** (Phase 5), with the gating
  note explaining verification vs. experiment semantics.
- **Accept:** a QS run and a completions cart both replayed from the same page; results
  land in each feature's store with tags; `replay.run`/`replay.item` spans appear on the
  console timeline; the Lab is no longer a stub.

**WI-3.3 Config groups (settings-group experiments, consistent pattern).**
- Name the concept once: a **config group** = named preset (profile) + partial overrides,
  the unit both matrix axes and cart config modes consume. Add
  `describeConfig(config) → string` for run labeling so analysis pivots are readable.
- **Accept:** matrix cell labels and analysis `replayMatrixCell` dimension values are
  human-readable and stable.

**WI-3.4 Graduation seam to perftest.**
- "Export as perftest A/B" action on a matrix definition: emits a config JSONC snippet
  with paired scenario variants using `ScenarioSpec.userSettings`
  (perftest `packages/perf-contracts/src/controlMessages.ts:454`), following the
  `registerQueryStudio10kBackendVariant` pattern, plus a doc pointer for the
  `head-to-head` comparison. This is scaffolding + docs, not automation — it encodes the
  boundary: in-session-flippable settings → Replay Lab; activation-time settings →
  harness variants.
- **Accept:** exported snippet validates against the perftest config schema.

### Phase 4 — Analysis chrome convergence (keep specialization, share the shell)

- Extract `DatasetSelector`, `FacetRail`, `PivotTable`, `SummaryTiles`,
  `LatencyHistogram` from `SessionsTab.tsx` into
  `webviews/pages/DebugConsole/analysisKit/`, parameterized by a
  `FeatureAnalysisProvider { dimensions, getDimensionValue, computeMetrics, facets }` —
  the completions provider is a thin wrapper over `inlineCompletionAnalysis.ts` (already
  pure). Query Studio adds a provider when its analysis matures.
- Session History page: sessions with rich streams get a per-feature chip
  ("Completions: 214 events") deep-linking to the feature's Sessions view filtered to
  that session.
- **Perf Test History stays separate** (official-metric provenance vs. experimental
  fidelity); it may adopt `analysisKit` components opportunistically, nothing more.
- **Accept:** completions Sessions tab renders on analysisKit with zero feature loss;
  Session History chips navigate correctly.

### Phase 5 — Horizon (explicitly not now)

1. **STS2 Replay Lab tab**: offline journal/export-bundle import (follow the
   `importPerfRep` pattern per `06-sts2-and-next.md` §5.1), sequence list, cause graph,
   state-at-seq, state diff, strict-replay verdict in a Validation panel. Labeled
   "deterministic verification" throughout. Gated on the STS2 M7 human gate per its runbook.
2. **Central upload of curated traces**: an explicit policy id that admits redacted or
   even full prompt/response streams for team dogfood analysis, with the standard
   preview/refuse machinery; central tables for completion events (the classifications
   already exist in the taxonomy).
3. **perftest completions scenarios**: drive a curated prompt corpus through the replay
   engine headlessly (self-test first, CLI later) to benchmark latency/acceptance across
   config groups with harness rigor — eligibility `exploratory` until model
   nondeterminism handling is decided.

### Sequencing & dependencies

```text
Phase 0  ──► Phase 1 (WI-1.1 → 1.2 → 1.3 → 1.4 → 1.5/1.6)   ← minimal outcome ships here
   │
   └─────► Phase 2 (2.1 → 2.2 → 2.3 → 2.4)                    ← ideal outcome
                 │
                 └─► Phase 3 (3.1 → 3.2 → 3.3 → 3.4) ─► Phase 4 ─► Phase 5
```
Phase 1 does not depend on Phase 2 (the console UX works against today's trace files).
Phase 3 reads stores, so it lands best after Phase 2, but WI-3.1/3.2 can start against
the in-memory store + legacy files if priorities demand.

### Risk register

| Risk | Mitigation |
|---|---|
| Console webview bundle growth from importing the full IC component set | Lazy chunks per page (verify `scripts/esbuild-utils.js` splitting); measure against the existing UI scale tests |
| Amendment semantics (acceptance flips) in append-only JSONL | Explicit `amend` line type + merge-on-load, covered by round-trip tests (WI-2.1) |
| Rich payloads leaking through consolidated-store tooling (export, upload, validation dumps) | Rich streams are structurally separate files; every reader opts in; privacy canaries extended (WI-2.4) |
| Fork drift during the transition window | WI-1.1 (de-fork) lands **first**; the escape-hatch panel runs on the shared core |
| Capture-gating regressions with two viewers | Refcount API + tests (WI-1.4) |
| Write-through journaling overhead in hot completion paths | Same batched write-behind pattern as `SessionDiagSink` (proven at 5k-event segments); persistence still gated behind `trace.captureEnabled` |
| Replay semantics confusion (experiment vs verification vs harness) | §3.1 labels enforced in UX copy; STS2 section stays gated until Phase 5 |

### Decisions to freeze before coding

1. `featureId` keys: `"completions"`, `"queryStudio"` (used in store paths, manifests, registry).
2. Envelope/manifest version strings: `mssql.featureTrace/2`, `mssql.diag.sessionManifest/2`.
3. Standalone panel fate: escape-hatch setting for one milestone, then delete (recommended above).
4. Whether `trace.captureEnabled` default flips to `true` once storage is consolidated,
   retention-bounded, and crash-safe (recommendation: yes for dev builds via the existing
   settings UX, keep `false` for release until the central-upload policy story is decided).
5. Rich-stream inclusion rules for `DcExport` (default off) and central upload (refused
   under default policy) — proposed in WI-2.4, needs sign-off.

### Definition of done

- One viewer: everything the standalone panel does is in the Debug Console; the command
  deep-links there; no forked reducer/state code remains.
- One store: a session directory contains both planes under one manifest; validation,
  retention, health, and backfill cover both; crash-durability for rich capture.
- One identity: any completions request can be walked substrate-span ↔ rich-event in
  both directions; correlation lint stays clean.
- One replay pattern: Replay Lab hosts completions + Query Studio with shared
  cart/queue/matrix chrome, feature-declared config groups, tagged results, and a
  documented graduation path to perftest settings-group A/B.
- Nothing on the "don't lose anything" checklist regressed; all privacy canaries green.
