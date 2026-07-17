# Inline Completions Observability Unification Plan Addendum

**Reviewed:** 2026-07-16  
**Companion plan:** `inline_comp_observability.md`  
**Primary implementation branches:** `microsoft/vscode-mssql:dev/query`, `microsoft/sqltoolsservice:dev/query`, `kburtram/perftest:dev/query`  
**Design-note source:** `kburtram/notes`  
**Status:** Approved with required architectural amendments before broad implementation

## How to use this addendum

The companion plan remains the primary current-state survey and the source of the original phased proposal. This addendum does four things:

1. validates the plan against the current `dev/query` implementations and design notes;
2. identifies implementation risks that are not obvious from the current plan;
3. tightens the contracts, storage ownership, replay semantics, analysis rules, and rollout gates;
4. replaces portions of the execution sequence where a coding agent could otherwise build itself into a corner.

Where this addendum explicitly conflicts with the companion plan, this addendum takes precedence. Everything else in the companion plan remains in force, especially the two-plane privacy boundary and the "do not lose anything" requirement.

The branch is the final source of truth. Before starting each phase, the coding agent must record the current branch head SHA for all repositories it will touch and revalidate the paths named here.

---

## 0. Executive review

### 0.1 Verdict

The companion plan is directionally excellent. Its central conclusion is correct:

- rich completion payloads must remain outside `DiagEvent`;
- the Debug Console should become the primary UX;
- correlation, lifecycle, retention, replay patterns, and common UI primitives should converge;
- STS2 verification replay, interactive feature re-execution, and perftest scenario execution must remain semantically distinct;
- feature-specific analysis is not a failure of unification;
- inline completions should be the minimum capability bar for any feature that claims equivalent replay and experimentation support.

Proceed with the plan, but do not implement Phase 2 or generalize Replay Lab exactly as currently written. The most important corrections are:

1. use one **session bundle catalog** with independently owned child manifests, not one mutable manifest shared by multiple writers;
2. introduce globally unique, typed identity before persistence;
3. separate capture arming, content fidelity, persistence, export, and upload policy;
4. journal typed lifecycle records instead of generic merge patches;
5. de-fork through domain services and thin, paged RPCs, not a new monolithic host core that returns every prompt on every state change;
6. make replay runs durable artifacts with explicit provenance, cancellation, cost, target, and side-effect policy;
7. treat Query Studio replay as potentially mutating until proven otherwise;
8. separate live-user acceptance analysis from replay experiment analysis;
9. treat imported rich traces as untrusted content;
10. preserve STS2 as an authoritative external journal rather than translating it into the feature-capture format.

### 0.2 The refined north star

The best unified system is:

> One Debug Console, one identity vocabulary, one local evidence catalog and lifecycle, one feature registration pattern, one replay shell, one config-group concept, and one set of trust labels over multiple authoritative stream formats.

That is stronger than forcing every mechanism into one event shape. A universal format would either leak payloads into the safe metadata plane or strip the fidelity that makes inline completions useful. Neither trade is acceptable.

### 0.3 What "one system" should and should not mean

| Concern | Unify? | Target |
|---|---:|---|
| Main UX shell and navigation | Yes | Debug Console |
| Session and artifact discovery | Yes | Session bundle catalog |
| Cross-plane identity | Yes | Typed, globally unique links |
| Capture status, health, retention, repair | Yes | Common lifecycle services |
| Feature registration and capabilities | Yes | Feature observability descriptor |
| Replay cart, queue, matrix, progress chrome | Yes | Replay Lab primitives |
| Config group naming and provenance | Yes | Versioned config-group contract |
| Record format | No | Plane-specific authoritative schemas |
| Privacy policy | Common framework, feature rules | Structural separation plus feature serializers |
| Replay semantics | No | Experiment, verification, and harness remain labeled |
| Analysis metrics | No | Shared components, feature-owned semantics |
| Official performance history | No merge | Perf Test History remains provenance-specific |
| STS2 journal | No conversion | Imported or live-linked authoritative artifact |

### 0.4 Inline completions remains the minimum bar

No common abstraction may reduce the current completions experience. The target must retain:

- real-time pending and terminal events;
- full prompt, response, schema context, locals, and error detail when rich capture is allowed;
- real-time session-only overrides;
- profiles and model selection;
- custom system prompt;
- record-when-closed;
- local session persistence;
- external trace folder workflows;
- import and export;
- session indexing and inclusion controls;
- facets, pivots, histograms, drilldown, and detail tabs;
- single-event, session, basket, queue, and matrix replay;
- snapshot, override, and live config modes;
- cancellation and progress;
- replay tags and analysis dimensions;
- send-to-basket from live and history views;
- the safe metadata-only view when rich completions debug is disabled.

The target adds durability, provenance, safety, scalability, and shared UX. It does not exchange existing capability for uniformity.

---

## 1. Review scope and evidence

### 1.1 Current implementations reviewed

The following current branch areas materially informed this addendum.

#### `vscode-mssql`

- `extensions/mssql/src/diagnostics/featureCapture/captureStore.ts`
- `extensions/mssql/src/diagnostics/featureCapture/replayEngine.ts`
- `extensions/mssql/src/diagnostics/featureCapture/traceCodec.ts`
- `extensions/mssql/src/diagnostics/featureCapture/traceFiles.ts`
- `extensions/mssql/src/copilot/sqlInlineCompletionProvider.ts`
- `extensions/mssql/src/copilot/inlineCompletionDebug/*`
- `extensions/mssql/src/sharedInterfaces/inlineCompletionDebug.ts`
- `extensions/mssql/src/sharedInterfaces/inlineCompletionAnalysis.ts`
- `extensions/mssql/src/sharedInterfaces/featureReplay.ts`
- `extensions/mssql/src/diagnostics/completionsDebugConsoleHost.ts`
- `extensions/mssql/src/webviews/pages/DebugConsole/completionsPage.tsx`
- `extensions/mssql/src/webviews/pages/DebugConsole/completionsDebug/*`
- `extensions/mssql/src/diagnostics/sinks.ts`
- `extensions/mssql/src/diagnostics/sessionStore.ts`
- `extensions/mssql/src/diagnostics/diagnosticsManager.ts`
- `extensions/mssql/src/sharedInterfaces/debugConsole.ts`
- `extensions/mssql/src/queryStudio/replay/qsRunCapture.ts`
- `extensions/mssql/src/queryStudio/replay/queryStudioReplayController.ts`

#### `perftest`

- `packages/observability-contracts/src/registry/event-types.json`
- `packages/perf-contracts/src/controlMessages.ts`
- settings-group and Query Studio scenario patterns on `dev/query`
- central projection, policy, and conformance work on `dev/query`

#### `sqltoolsservice`

- `docs/sts2/OBSERVABILITY.md`
- `docs/sts2/TRACE-SCHEMA.md`
- STS2 runtime journaling, durability, export, and replay components on `dev/query`

#### Design notes

- unified observability architecture and Debug Console documents;
- Debug Console technical and UX specifications;
- Query Studio reviewed design and execution notes;
- STS2 integration and gating notes;
- perftest integration notes;
- central observability design and privacy policy;
- peer review and remaining-task inventories.

### 1.2 Material current-code facts

| Observed fact | Implication |
|---|---|
| `FeatureCaptureStore` uses process-local counter IDs such as `E-1` and a single `_panelOpen` boolean. | Identity and capture gating must change before multi-viewer or durable unification. |
| Pending records are replaced in place and acceptance is a later mutation. | The rich journal needs lifecycle records and amendments, not append-once event snapshots. |
| The completion provider emits Plane-A result metadata before or independently of rich-store mutation. | Cross-plane IDs must be allocated before emission and propagated intentionally. |
| The Debug Console host pulls a full `InlineCompletionDebugWebviewState`, including all rich event payloads, whenever the host announces a change. | Full parity must not preserve this transport shape. Use thin rows, cursors, and lazy detail. |
| The console host explicitly contains forked reducers and empty Sessions/Replay state. | De-forking is a prerequisite, not cleanup after feature work. |
| The existing `SessionDiagSink` owns and rewrites `manifest.json`. | A new rich writer cannot safely co-edit that file without a single coordinator. |
| Session journal flush uses buffered synchronous append and a 500 ms timer, but no explicit disk flush contract. | Do not promise a hard kill or power-loss bound without defining durability levels. |
| Trace normalization accepts almost any object with `events[]` and coerces unknown versions to v1. | Import needs strict versioning, schema validation, resource limits, and trust labeling. |
| Current redaction is mostly key-driven and does not comprehensively classify `locals`, paths, SQL diagnostics, or error stacks. | Rich redaction must become feature-semantic and schema-driven. |
| Replay engine cancellation removes queued work but does not provide a cancellation token to the active host execution. | Active model and SQL work is not honestly cancellable through the generic contract yet. |
| Completion replay refreshes schema context when possible, then falls back to captured context. | Replay mode and fallback must be explicit provenance, not an incidental behavior. |
| Query Studio replay executes SQL through a live connected document and can change database. | Generic Replay Lab needs a side-effect and target-binding policy before Query Studio is enabled broadly. |
| Current completion acceptance rate uses all events in the group as the denominator. | Live quality metrics and replay experiment metrics need corrected cohorts and denominators. |
| STS2 journals first, has canonical payload digests, gapless sequence, and deterministic verification. | STS2 should stay authoritative and be adapted into the console, not recoded as a feature trace. |

---

## 2. Non-negotiable invariants

The coding agent should encode these as tests and comments at the relevant choke points.

### 2.1 Privacy and payload invariants

1. Prompt text, model replies, SQL text, row data, schema-context text, document text, and arbitrary locals never ride `DiagEvent`.
2. Plane-A identifiers may point to rich artifacts, but never contain rich content.
3. Rich streams are opt-in or explicitly armed, local by default, and structurally separate from Plane-A segments.
4. Secret material is never persisted, even in rich streams.
5. Default Debug Console export and default central upload exclude rich streams.
6. A redacted capture can never be silently treated as replayable.
7. Imported files are untrusted and never automatically executed or replayed.

### 2.2 Honesty invariants

1. Gaps, truncation, dropped records, failed persistence, incomplete replay, target substitutions, schema fallbacks, and missing payloads are visible states.
2. Interactive replay results are never labeled as official perftest metrics.
3. STS2 verification replay is never presented as an experiment matrix.
4. A "live" replay config is frozen and recorded at a defined boundary.
5. Query Studio replay never falls back to an arbitrary first live connection without explicit user selection.
6. A replay output is not counted as user acceptance unless a user explicitly evaluates it.

### 2.3 Product isolation invariants

1. Observability failure does not fail the product operation.
2. Hot feature paths perform no synchronous file I/O.
3. Viewer-internal activity remains excluded from default traces, stores, forwarding, and official metrics.
4. Opening or closing one viewer never disables capture needed by another viewer.
5. No standalone implementation is deleted until parity, privacy, performance, and rollback gates pass.

### 2.4 Compatibility invariants

1. Existing v1 completion trace files continue to load.
2. Existing external trace folder, add-file, change-folder, import, and export workflows remain available.
3. Existing completion profile and override behavior remains available.
4. Existing analysis dimensions and detail tabs remain available.
5. Existing command IDs continue to work, even when they route to the Debug Console.
6. Existing Plane-A event vocabulary remains additive and contract-governed.

---

## 3. Required architectural amendments

### 3.1 Amendment A: one bundle catalog, not one shared mutable manifest

The companion plan proposes a `SessionManifest` v2 with a `richStreams[]` field and asks the existing diagnostic sink and new capture journal to participate in one manifest. The goal is correct, but the ownership model is unsafe.

Today `SessionDiagSink` holds an in-memory manifest and rewrites `manifest.json` after each flush. If a rich writer also updates the same file, either writer can overwrite the other's changes. Adding a registration callback helps only if a single component becomes the sole writer.

#### Required design

Introduce a parent **Observability Bundle** that is the single session-level catalog. Each child artifact owns its own manifest.

```text
<storeRoot>/sessions/<hostSessionId>/
  bundle.json
  diag/
    manifest.json
    segment-000001.jsonl
    ...
  rich/
    completions/
      <captureSessionId>/
        manifest.json
        segment-000001.jsonl
        ...
    queryStudio/
      <captureSessionId>/
        manifest.json
        segment-000001.jsonl
        ...
  replay/
    <replayRunId>/
      manifest.json
      items.jsonl
  refs/
    sts2-<runId>.json
    perf-<runId>.json
```

`bundle.json` contains safe metadata only:

- bundle and host session identity;
- created, updated, and closed timestamps;
- artifact descriptors;
- schema IDs;
- relative child-manifest paths;
- feature ID and artifact kind;
- record/event counts;
- bytes;
- status;
- gap/truncation counts;
- classification summary;
- provenance;
- content or manifest digest where available.

The parent does not duplicate child segment lists or rich payload metadata.

#### Ownership rules

- `SessionDiagSink` owns only `diag/manifest.json` and `diag/segment-*`.
- each `FeatureCaptureJournal` owns only its feature capture directory;
- `ReplayRunRepository` owns only its replay directory;
- `ObservabilityBundleManager` is the only writer of `bundle.json`;
- bundle updates are serialized and written by temporary-file plus atomic rename;
- bundle state can be rebuilt by scanning child manifests;
- retention operates on the bundle, with optional explicit per-artifact purge;
- central preview can refuse a whole artifact from its classification summary without opening payload segments.

This still gives one store, one lifecycle, one session row, one retention unit, and one health surface. It avoids making unrelated writers share mutable state.

### 3.2 Amendment B: define identity before persistence

Current IDs are appropriate for an in-memory panel, not durable cross-session evidence. `E-1`, `R-1`, timestamp counters, and `cell-1` collide after restart and import.

Define these identities explicitly:

| Identity | Meaning | Scope |
|---|---|---|
| `hostSessionId` | one extension-host activation | globally unique |
| `captureSessionId` | one continuous rich-capture epoch for a feature | globally unique |
| `captureEventId` | one logical rich feature event across pending, final, and acceptance records | globally unique |
| `traceId` | Plane-A causal trace | existing Trace Identity contract |
| `replayRunId` | one queued replay or matrix run | globally unique |
| `replayItemId` | one source item execution in a run and cell | globally unique |
| `matrixCellId` | one config combination within a run | stable within run; include config digest |
| `perfRunId` | one perftest run | perftest contract |
| `sts2RunId` | one STS2 process run | STS2 contract |

Use `crypto.randomUUID()` or the repository's approved equivalent for durable IDs. Timestamp remains a separate sort field. Do not encode uniqueness assumptions into labels.

Add a versioned link block to rich events:

```ts
export interface ObservabilityLinkV1 {
    schema: "mssql.observabilityLink/1";
    featureId: string;
    hostSessionId: string;
    captureSessionId: string;
    captureEventId: string;
    traceId?: string;
    causeEventId?: string;
    editorSurface?: "classic" | "queryStudio" | "other";
}
```

Plane-A events may carry the safe reverse fields:

- `captureFeatureId`
- `captureSessionId`
- `captureEventId`
- `replayRunId`
- `replayItemId`
- `matrixCellId`

All are `diagnostic.metadata`.

#### Completion emission ordering

The completion provider must reserve `captureEventId` before it emits the pending rich event or the Plane-A result link. The same ID survives:

```text
request start
  allocate captureEventId
  add pending read model, if rich capture armed
  emit Plane-A request/span with optional link
model settles
  append event.finalized for same captureEventId
  emit Plane-A result with same optional link
acceptance arrives
  append acceptance.changed for same captureEventId
```

When the live ring has evicted the pending read model, finalization must reinsert a projection with the same `captureEventId`, not allocate a second logical event.

### 3.3 Amendment C: separate capture arming from persistence and policy

The current settings have different meanings:

- viewer-open or `recordWhenClosed` decides whether rich events are recorded;
- `trace.captureEnabled` decides whether the in-memory ring is saved on deactivate;
- `trace.redactPrompts` changes export content;
- Session Diag capture policy controls Plane A.

Do not reuse `trace.captureEnabled` to mean continuous journaling without an explicit migration.

Model rich capture with independent dimensions:

| Dimension | Example values | Purpose |
|---|---|---|
| Arming | `off`, viewer lease, `recordWhenClosed` | Should the feature create rich records? |
| Fidelity | `fullLocal`, `contentRedacted`, `digestOnly` | What content may be recorded? |
| Persistence | `memoryOnly`, `localJournal` | Is the stream durable? |
| Export policy | `metadataOnly`, `contentRedacted`, `fullLocal` | What leaves the store in a file? |
| Upload policy | policy ID, default refuse | What may leave the machine? |
| Trust | `localProduct`, `externalImport`, `generatedFixture` | May records be replayed without an extra trust step? |

Suggested compatibility behavior:

- preserve existing settings and UI labels for the first migration;
- map `trace.captureEnabled=true` to `persistence=localJournal`;
- map `trace.redactPrompts=true` to at least `contentRedacted`;
- do not flip defaults in release builds during the migration;
- provide a developer-only "Enable Observability Lab" preset rather than silently changing several existing setting meanings;
- capture and persist the effective policy on every segment and replay run.

### 3.4 Amendment D: replace `setPanelOpen` with viewer leases

Replace the single boolean with a lease registry:

```ts
interface FeatureCaptureLease {
    id: string;
    owner: string;
    acquiredAt: number;
    dispose(): void;
}

acquireViewer(owner: string): FeatureCaptureLease;
getActiveViewerCount(): number;
getActiveViewerOwners(): readonly string[];
```

Requirements:

- disposal is idempotent;
- one viewer closing cannot affect another;
- a leaked lease appears in health diagnostics;
- standalone panel, Debug Console Completions page, and Replay Lab acquire separate named leases;
- capture behavior when the user navigates away from the page is explicit;
- tests cover webview reload, panel disposal order, and command rerouting.

### 3.5 Amendment E: use typed lifecycle records, not generic merge patches

A generic `{ t: "amend", id, patch }` makes it too easy to mutate immutable fields, resurrect redacted content, apply out-of-order patches, or create a read model that no version of the product actually emitted.

Use a versioned append-only record stream:

```ts
type FeatureCaptureJournalRecordV1<TCreated, TFinal, TAcceptance> =
    | {
          schema: "mssql.featureCapture.record/1";
          kind: "stream.header";
          recordSeq: 0;
          featureId: string;
          hostSessionId: string;
          captureSessionId: string;
          eventSchema: string;
          overridesSchema: string;
          capturePolicy: RichCapturePolicySnapshot;
          createdUtc: string;
      }
    | {
          schema: "mssql.featureCapture.record/1";
          kind: "event.created";
          recordSeq: number;
          eventRevision: 1;
          captureEventId: string;
          at: number;
          value: TCreated;
      }
    | {
          schema: "mssql.featureCapture.record/1";
          kind: "event.finalized";
          recordSeq: number;
          eventRevision: number;
          captureEventId: string;
          at: number;
          value: TFinal;
      }
    | {
          schema: "mssql.featureCapture.record/1";
          kind: "acceptance.changed";
          recordSeq: number;
          eventRevision: number;
          captureEventId: string;
          at: number;
          value: TAcceptance;
      }
    | {
          schema: "mssql.featureCapture.record/1";
          kind: "annotation.added";
          recordSeq: number;
          eventRevision: number;
          captureEventId: string;
          at: number;
          value: Record<string, unknown>;
      };
```

The reducer validates:

- created appears once;
- revisions increase;
- finalized cannot alter immutable request identity;
- acceptance applies only to a finalized, presented suggestion;
- duplicate records are idempotent;
- out-of-order or illegal transitions are surfaced as validation issues;
- redacted streams cannot gain full content from later records;
- unknown future record kinds are handled according to schema compatibility rules.

For completions, preserve a compatibility projection to the current `InlineCompletionDebugEvent` so the existing UI can move before the event model is fully redesigned.

### 3.6 Amendment F: separate stream, event, config, and export versions

Do not use one `version` number for every compatibility question.

A v2 exported trace should carry at least:

```ts
interface FeatureTraceEnvelopeV2<TEvent, TOverrides> {
    schema: "mssql.featureTrace/2";
    featureId: string;
    hostSessionId?: string;
    captureSessionId: string;
    eventSchema: string;
    overridesSchema: string;
    exportedAt: number;
    savedAt: string;
    extensionVersion: string;
    events: TEvent[];
    overrides: TOverrides;
    capturePolicy: RichCapturePolicySnapshot;
    truncation?: {
        occurred: boolean;
        omittedEvents: number;
        firstRetainedAt?: number;
    };
    provenance: FeatureTraceProvenance;
}
```

Compatibility rules:

- load known v1 and v2 formats;
- migrate v1 to a normalized in-memory representation;
- reject unsupported future major versions with an actionable error;
- preserve unknown additive fields when safe;
- validate feature ID and event schema;
- cap file bytes, event count, string length, nesting depth, and aggregate decoded bytes;
- do not coerce an unknown version to v1;
- expose truncation and missing replay payload as explicit capability flags.

### 3.7 Amendment G: define durability honestly

A 500 ms write-behind timer does not prove that `kill -9` or power loss loses at most 500 ms. A write may be in the runtime buffer, OS page cache, or filesystem journal.

Use explicit durability labels:

| Level | Meaning |
|---|---|
| `memory` | only in the live ring or writer queue |
| `appended` | append call completed and data is visible to normal reads |
| `checkpointed` | segment and child manifest agree |
| `durable` | an explicit file and directory flush contract completed, where supported |

The initial implementation may choose `appended` or `checkpointed` for performance. It must not claim `durable` unless it performs and tests the required flush operations.

Required writer behavior:

- no file I/O on the feature hot path;
- bounded record and byte queue;
- exact dropped record ranges;
- segment roll by both record count and bytes;
- temporary-file plus rename for child manifests;
- closed-segment digest;
- flush barriers for explicit save/export, replay-run terminal state, extension deactivation, and test hooks;
- startup repair marks stale active streams `partial`;
- health reports queue depth, queued bytes, drops, last append, last checkpoint, current durability level, and failure detail;
- product behavior continues when the writer fails.

### 3.8 Amendment H: journal is source of truth, ring is a cache

After cutover:

- the journal or imported trace is the historical source of truth;
- the ring is a bounded live read model;
- UI state must show when earlier live records have fallen out of the ring;
- finalization and acceptance may update journal state even after ring eviction;
- export is assembled from a consistent repository snapshot after a flush barrier;
- the product does not indefinitely write both a legacy session JSON file and the journal;
- external trace files remain a first-class import/export library, not a second hidden live source of truth.

---

## 4. Refined target architecture

### 4.1 System diagram

```text
                              MSSQL Debug Console
  -------------------------------------------------------------------------------
  Overview | Trace | Waterfall | Session History | Perf History | Feature pages
                 Completions: Live + Sessions + embedded replay entry points
                 Replay Lab: common run/cart/matrix shell by capability
  -------------------------------------------------------------------------------
                 | metadata queries          | rich queries and commands
                 v                           v
       Plane A diagnostics              Feature observability adapters
       classified DiagEvents            completions | Query Studio | future
                 |                           |
      LiveTail / PerfMode / diag journal     +-- live read-model ring
                 |                           +-- feature capture repository
                 |                           +-- analysis provider
                 |                           +-- replay adapter, when supported
                 v                           v
  <storeRoot>/sessions/<hostSessionId>/bundle.json
       |-- diag/manifest.json + segments
       |-- rich/<feature>/<captureSession>/manifest + segments
       |-- replay/<run>/manifest + items
       |-- refs/STS2 and perf artifact descriptors
                 |
                 +-- retention, health, repair, export preview, deep links
```

### 4.2 The feature observability descriptor

A single registry may describe a feature without pretending every feature supports every capability.

```ts
interface FeatureObservabilityDescriptor {
    featureId: string;
    label: string;
    schemas: {
        event?: string;
        overrides?: string;
        analysis?: string;
    };
    capabilities: {
        planeAMetadata: true;
        richLive?: boolean;
        richHistory?: boolean;
        analysis?: boolean;
        replayExperiment?: boolean;
        replayVerification?: boolean;
        harnessGraduation?: boolean;
    };
    privacy: {
        payloadClasses: string[];
        defaultRichCapture: "off" | "redacted" | "fullLocal";
        replayRequiresPayload: boolean;
    };
    createLiveProvider?: () => FeatureLiveProvider;
    createHistoryProvider?: () => FeatureHistoryProvider;
    createAnalysisProvider?: () => FeatureAnalysisProvider;
    createReplayAdapter?: () => ReplayableFeatureV2;
}
```

The Debug Console consumes capabilities. It does not render fake empty controls for unsupported features.

### 4.3 Capability levels

Use capability levels in docs and acceptance tests:

| Level | Name | Required capability |
|---|---|---|
| F0 | Instrumented | Plane-A metadata and correlation |
| F1 | Rich live | gated full-detail event view |
| F2 | Durable history | indexed, retained local capture |
| F3 | Interactive replay | basket, config groups, run artifact, progress, cancellation |
| F4 | Specialized analysis | feature-specific dimensions and metrics |
| F5 | Harness graduation | exportable controlled experiment definition |

Every meaningful feature should reach F0. Payload-bearing features add F1 and F2 only when useful. A feature that claims F3 must meet the completions minimum bar and safety contract. A feature should not implement fake replay merely to look uniform.

### 4.4 Session semantics

Avoid using the word "session" for five different things.

- **Host session:** one extension-host activation and Plane-A `sessionId`.
- **Capture session:** one continuous feature-capture epoch with one fixed capture policy.
- **Replay run:** one basket or matrix execution.
- **Perf run:** one controlled harness run directory.
- **STS2 run:** one STS2 process journal.
- **Dataset:** a user-selected union of capture sessions or imports for analysis.

The Session History page should show one host-session row with child artifact chips. A completions analysis dataset may span many capture sessions across host sessions.

---

## 5. Completion event model hardening

### 5.1 Preserve the current read model while improving the stored model

The current `InlineCompletionDebugEvent` is a productive UI read model. Replacing it in the first UI migration creates unnecessary risk. Keep it as a compatibility projection while introducing a normalized stored event model.

A normalized completion event should group fields by meaning:

| Group | Stable fields |
|---|---|
| Identity | link block, event schema, capture timestamps, editor surface |
| Source | document digest, optional full URI under rich policy, language, version, cursor position, trigger |
| Request | category, intent mode, inferred-system-query flag, source context digests and optional text |
| Effective config | config group, profile version, effective config digest, resolved layered config |
| Model | requested selector, resolved vendor/family/id, model capability snapshot |
| Prompt | prompt messages, prompt digest, prompt-builder version |
| Schema context | source mode, digest, counts, budget, selection metadata, optional formatted text |
| Outcome | pending/final state, latency, tokens, raw/sanitized/final output, sanitizer version, error classification |
| Acceptance | state, timestamp, optional accepted length or fraction when available |
| Replay | source event, run, item, cell, execution mode, config digest |
| Provenance | extension version and commit, VS Code version, relevant component versions |
| Diagnostics | typed and classified diagnostic fields |

### 5.2 Promote stable fields out of `locals`

`locals` is useful for rapid debugging but unsafe as the long-term contract. It currently can contain document text, SQL diagnostics, schema decisions, replay labels, and arbitrary future values.

Rules:

- keep `locals` for legacy imports and explicitly experimental diagnostics;
- add a per-field classification map for any new `locals` value;
- promote fields used by filtering, analysis, replay, or compatibility into typed properties;
- do not use key-name redaction as the only protection for `locals`;
- cap total locals bytes per event;
- omit or digest stack traces, paths, and provider messages under redacted policy;
- surface omitted diagnostics in the detail pane.

Candidates to promote immediately:

- editor surface;
- profile ID and profile definition version;
- schema budget profile;
- schema size kind;
- schema source;
- degradation steps;
- prompt builder version;
- sanitizer version;
- replay schema-context mode;
- effective token limit;
- config digest;
- source document digest and version.

### 5.3 Acceptance lifecycle

The current success-to-accepted flip should become an explicit acceptance object:

```ts
interface CompletionAcceptanceV1 {
    state: "unknown" | "notAccepted" | "accepted" | "partiallyAccepted";
    changedAt?: number;
    acceptedCharacters?: number;
    acceptedLines?: number;
    source: "vscodeInlineApi" | "queryStudioBridge" | "manualReplayRating" | "unknown";
}
```

Requirements:

- live completion acceptance remains separate from replay evaluation;
- pending and queued records are excluded from terminal analysis;
- acceptance after ring eviction still reaches the journal;
- duplicate acceptance notifications are idempotent;
- accepted text is not persisted unless already permitted by the capture policy;
- partial acceptance remains optional until both editor surfaces can report it honestly.

### 5.4 Effective config and settings layering

Every captured request and replay item should store the fully resolved effective config, not only an override object.

Record the layers:

```text
product defaults
  -> user/workspace settings
  -> named feature profile
  -> session debug overrides
  -> replay config group
  -> per-item override
  = effective config + canonical digest
```

The UI may continue to show concise overrides, but replay and analysis use the effective snapshot and digest.

A profile ID alone is insufficient because profile definitions can change. Capture:

- profile ID;
- profile schema version;
- profile definition digest;
- resolved effective config;
- setting mutability metadata;
- human-readable description frozen into the replay run.

### 5.5 Cross-surface completions

The Query Studio design expects one completion engine for classic and Query Studio editors. Add `editorSurface` as a first-class field and analysis dimension. The same capture, replay, and history system should work across both surfaces, while preserving surface-specific source and acceptance adapters.

Do not create a second completions journal for Query Studio.

---

## 6. Debug Console convergence without transport regression

### 6.1 De-fork through services, not a giant controller clone

The proposed `InlineCompletionDebugHostCore` is useful as a façade, but moving a 2,500-line controller into one host-agnostic file would merely relocate the monolith.

Extract these responsibilities:

1. `InlineCompletionCaptureService`
   - viewer leases;
   - live read model;
   - effective config;
   - event selection hooks.

2. `InlineCompletionTraceRepository`
   - live and historical queries;
   - import/export;
   - external folder provider;
   - journal provider;
   - migration and repair.

3. `InlineCompletionReplayService`
   - basket;
   - run creation;
   - adapter execution;
   - durable progress;
   - cancellation.

4. `InlineCompletionDebugStateProjector`
   - thin summaries;
   - detail projections;
   - capability and health state.

5. `InlineCompletionDebugCommandHandler`
   - typed command dispatch;
   - validation;
   - operation IDs;
   - dialogs through injected host services.

6. Existing pure analysis functions
   - retain feature ownership;
   - later wrap with a common analysis provider.

The standalone panel adapter and Debug Console adapter call the same services. No business reducer is copied.

### 6.2 Replace full-state pull with paged and lazy APIs

The current console integration can re-send hundreds of full prompts and replies after every event. Full parity should not preserve that behavior.

Use APIs shaped around user tasks:

```ts
DcFeatureCapabilitiesRequest
DcCompletionLiveRowsRequest
DcCompletionEventDetailRequest
DcCompletionSessionIndexRequest
DcCompletionSessionEventsRequest
DcCompletionAnalysisRequest
DcReplayRunListRequest
DcReplayRunDetailRequest
DcReplayCommandRequest
```

Suggested characteristics:

- live rows are compact and paged by cursor;
- event detail is fetched by ID and requested section;
- prompt, raw response, schema text, locals, and stack are lazy;
- session index reads manifests, not complete trace files;
- analysis may run in the extension host or a worker and returns aggregates plus drilldown cursors;
- notifications carry `revision`, changed resource IDs, and progress, not an instruction to pull the entire state;
- long operations return an `operationId`;
- cancellation targets the operation or replay run;
- commands are a discriminated union, not `{ name: string; payload?: unknown }`;
- stale command revisions are rejected or reconciled explicitly;
- all responses are size bounded.

### 6.3 Suggested thin live row

```ts
interface CompletionLiveRowV1 {
    captureEventId: string;
    captureSessionId: string;
    timestamp: number;
    result: string;
    trigger: string;
    completionCategory?: string;
    modelLabel?: string;
    profileLabel?: string;
    latencyMs?: number;
    inputTokens?: number;
    outputTokens?: number;
    acceptedState?: string;
    replayRunId?: string;
    matrixCellLabel?: string;
    detailAvailable: {
        prompt: boolean;
        response: boolean;
        schema: boolean;
        locals: boolean;
        error: boolean;
    };
}
```

### 6.4 UX placement

Recommended Debug Console behavior:

- **Completions page**
  - enablement and capture status;
  - Live tab;
  - Sessions tab;
  - full detail pane;
  - embedded "send to replay" and "open basket" entry points;
  - safe Plane-A activity when rich debug is disabled.

- **Replay Lab**
  - cross-feature feature picker;
  - shared basket, config group, matrix, run, progress, and result-navigation chrome;
  - feature-specific editor panels where needed;
  - explicit semantics and safety badges.

- **Session History**
  - host session rows;
  - child chips such as `Diag 8,142`, `Completions 214`, `QS runs 9`, `Replay runs 3`, `STS2 linked`;
  - deep links to feature analysis.

- **Perf Test History**
  - remains separate because official provenance and statistical semantics differ;
  - may link to related replay definitions or artifacts.

### 6.5 Standalone panel retirement

Keep the command ID permanently for compatibility, but route it to the Debug Console once parity is complete.

Delete the standalone implementation only after:

- the full parity matrix passes;
- imported and external-folder workflows pass;
- prompt and response detail is lazy and complete;
- replay matrix and cancellation work with the standalone panel closed;
- console bundle and first-paint budgets pass;
- privacy canaries pass;
- a feature flag can return users to the old implementation for one stabilization window;
- no forked state, reducer, or component copy remains.

Retirement is evidence-gated, not calendar-gated.

---

## 7. Unified replay architecture

### 7.1 Preserve three replay semantics

| Semantics | Input | Execution | Expected result | Trust label |
|---|---|---|---|---|
| Interactive experiment | captured feature scenario | live model, product, service, or database | outputs may differ | exploratory |
| Deterministic verification | STS2 journal | pure reducer with recorded effects | exact match or divergence | verification |
| Harness scenario execution | scenario definition and environment | controlled VS Code run | measured distribution and verdict | controlled or exploratory |

Shared UI can display all three, but the run contract, labels, and result panels must preserve the distinction.

### 7.2 Replay adapter v2

Extend the current generic host around its good sequential kernel:

```ts
interface ReplayableFeatureV2<TSource, TConfig, TResultRef> {
    featureId: string;
    label: string;
    semantics: "interactiveExperiment";
    capabilities: {
        supportsMatrix: boolean;
        supportsRepetitions: boolean;
        supportsActiveCancellation: boolean;
        supportsResume: boolean;
    };

    describeSource(source: TSource): ReplaySourceSummary;
    captureSourceSnapshot(source: TSource): ReplaySourceSnapshot;
    resolveEffectiveConfig(
        source: ReplaySourceSnapshot,
        group: ConfigGroupV1,
        itemOverride?: unknown,
    ): ResolvedReplayConfig<TConfig>;

    estimate(
        sources: ReplaySourceSnapshot[],
        groups: ConfigGroupV1[],
        repetitions: number,
    ): ReplayEstimate;

    preflight(context: ReplayPreflightContext<TConfig>): Promise<ReplayPreflightResult>;
    classifySafety(context: ReplayPreflightContext<TConfig>): ReplaySafetyAssessment;

    execute(
        context: ReplayExecutionContext<TSource, TConfig>,
        cancellation: vscode.CancellationToken,
    ): Promise<TResultRef>;

    evaluateResult?(context: ReplayEvaluationContext<TResultRef>): Promise<ReplayMetrics>;
}
```

### 7.3 Durable replay run artifact

A replay run is evidence, not only transient UI state.

```ts
interface ReplayRunManifestV1 {
    schema: "mssql.replay.run/1";
    replayRunId: string;
    featureId: string;
    semantics: "interactiveExperiment" | "verification" | "harness";
    createdAt: number;
    startedAt?: number;
    endedAt?: number;
    status:
        | "queued"
        | "running"
        | "cancelling"
        | "cancelled"
        | "completed"
        | "partial"
        | "failed";

    sourceBasketDigest: string;
    sources: Array<{
        captureSessionId: string;
        captureEventId: string;
        snapshotDigest: string;
        label: string;
    }>;

    configGroups: Array<{
        configGroupId: string;
        version: number;
        label: string;
        effectiveConfigDigest: string;
    }>;

    cells: Array<{
        matrixCellId: string;
        configGroupId: string;
        label: string;
        ordinal: number;
    }>;

    repetitions: number;
    expectedItems: number;
    completedItems: number;
    failedItems: number;
    cancelledItems: number;

    estimate?: ReplayEstimate;
    actual?: ReplayActualCost;
    safety: ReplaySafetyAssessment;
    provenance: ReplayProvenance;
}
```

Per-item records include:

- replay item ID;
- source capture event ID;
- matrix cell;
- repetition number;
- queue, start, and end timestamps;
- resolved config digest;
- target identity;
- status;
- result capture event ID or artifact reference;
- error code and redacted detail;
- cancellation outcome;
- attempt number.

### 7.4 Cancellation semantics

Current queued cancellation is useful but incomplete. Define:

- `cancelRequestedAt`;
- queued items removed immediately;
- active item receives a cancellation token;
- adapter reports whether cancellation reached the underlying operation;
- run status becomes `cancelling` until active work settles;
- result distinguishes `cancelledBeforeStart`, `cancelledInFlight`, and `cancelRequestedButCompleted`;
- completion model requests use the run token;
- Query Studio uses the execution host's real cancellation path;
- disposal of a UI does not automatically cancel a durable run unless the user chose that behavior.

### 7.5 Cost, cardinality, and rate limits

Before queueing, show:

- source count;
- matrix cell count;
- repetitions;
- expected item count;
- estimated model calls or SQL executions;
- estimated input tokens where available;
- configured maximum;
- side-effect class;
- target summary.

Default execution remains sequential. Add adapter-declared concurrency only after rate and resource tests.

Suggested guardrails:

- warning threshold for large item count;
- hard configurable item cap;
- hard queued-byte cap;
- model-call and token budget;
- per-provider rate limit;
- user confirmation above cost or side-effect thresholds;
- no hidden automatic retry for non-idempotent operations.

### 7.6 Config groups

A config group is the common experiment unit:

```ts
interface ConfigGroupV1 {
    schema: "mssql.configGroup/1";
    configGroupId: string;
    featureId: string;
    version: number;
    label: string;
    description?: string;
    baseProfileId?: string;
    baseProfileVersion?: number;
    partialOverrides: Record<string, unknown>;
    effectiveConfig?: Record<string, unknown>;
    effectiveConfigDigest?: string;
    settingMutability: Record<
        string,
        "hot" | "nextRequest" | "featureRestart" | "extensionReload" | "hostRelaunch"
    >;
}
```

Rules:

- Replay Lab applies only `hot` and `nextRequest` settings.
- `featureRestart`, `extensionReload`, and `hostRelaunch` settings graduate to perftest or a controlled relaunch runner.
- the "live" cart mode resolves and freezes config at run start;
- profile labels and definitions are frozen into the run;
- unknown fields are validated by the feature adapter;
- sensitive values never enter a shared config group.

### 7.7 Completion replay modes

Current completion replay can silently mix current and captured inputs. Make the mode explicit.

| Mode | Prompt | Editor context | Schema context | Primary use |
|---|---|---|---|---|
| `frozenPrompt` | captured exact messages | captured | already embedded | compare models or response handling |
| `rebuildCapturedContext` | rebuilt with current builder | captured | captured | compare profile, prompt builder, sanitizer |
| `rebuildCurrentSchema` | rebuilt with current builder | captured | current required | evaluate schema/config changes |
| `liveDocumentScenario` | rebuilt | current document state | current | live scenario re-execution, not strict pairing |

Rules:

- no implicit mode switch;
- if required current schema is unavailable, the item is `blocked` unless the user selected a fallback policy;
- fallback is a recorded dimension;
- matrix axes declare which modes they affect;
- `frozenPrompt` disables axes that only change prompt construction;
- capture prompt-builder and sanitizer versions;
- capture actual resolved model identity and capability snapshot;
- show nondeterminism and sample count.

### 7.8 Query Studio replay safety

Query Studio is a valid second tenant only after a safety contract lands.

Current replay can execute SQL through a live connection, switch database, and fall back to the first live document. That is too permissive for a generic Replay Lab.

Required policy:

1. classify execution:
   - `noExecution`: parse-only;
   - `readOnlyExpected`: estimated plan or parser-proven read-only;
   - `potentiallyMutating`: normal, actual plan, unknown, DDL, DML, procedure call, dynamic SQL.

2. bind target:
   - capture server and database fingerprint;
   - require exact match or explicit target selection;
   - never silently choose the first connected document;
   - record target fingerprint and database on each item.

3. gate modes:
   - enable parse-only and estimated-plan replay first;
   - keep potentially mutating execution behind an explicit warning and developer feature gate;
   - require a user confirmation that names target and item count;
   - prefer a configured sandbox or test connection;
   - do not claim that wrapping in a transaction makes arbitrary SQL safe.

4. cancellation:
   - wire the active replay token to Query Studio cancellation;
   - report cancellation acknowledgement and terminal state.

5. matrix axes:
   - do not offer arbitrary database cartesian products by default;
   - only expose adapter-approved target groups;
   - activation-time backend changes belong in perftest.

### 7.9 STS2 integration

STS2 remains authoritative for its own journal and verification.

The Replay Lab STS2 adapter should:

- import or link an STS2 export bundle;
- preserve run ID, sequence, cause, config version, canonical digests, and hash-chain evidence;
- render sequence, cause graph, state-at-sequence, diff, explain, and verdict;
- call STS2 verification tooling or a supported library boundary;
- never translate STS2 envelopes into completion or generic rich-event records;
- label runs `verification`;
- remain gated until the STS2 hardening and human milestone are complete;
- use live-tail plus journal backfill when a supported live adapter lands.

### 7.10 Perftest graduation

The companion plan's JSONC snippet export is useful scaffolding, but it should not be the long-term contract.

Target a payload-free experiment definition in `perf-contracts`:

```ts
interface ExperimentDefinitionV1 {
    schema: "mssql.experiment.definition/1";
    featureId: string;
    adapterId: string;
    adapterVersion: string;
    sourceCorpus: {
        kind: string;
        digest: string;
        artifactRef?: string;
    };
    configGroups: ConfigGroupV1[];
    repetitions: number;
    requestedMetrics: string[];
    eligibility: "exploratory" | "calibration" | "officialCandidate";
    environmentRequirements: Record<string, unknown>;
    safety: ReplaySafetyAssessment;
}
```

The perftest adapter turns this into:

- `ScenarioSpec.userSettings` for activation-time values;
- runtime `setConfig` steps for mutable values;
- a deterministic source corpus or controlled fixture;
- repetitions and metric definitions;
- explicit eligibility.

For completions, create two distinct harness paths:

1. deterministic fake or recorded model response for gate-grade pipeline latency and correctness;
2. live model evaluation for exploratory latency, token, and quality analysis.

Live network model behavior should not become an official regression gate without a separate nondeterminism and provider-stability design.

---

## 8. Analysis model corrections and extensions

### 8.1 Separate cohorts by provenance

Every feature event and result should identify provenance:

- `liveUser`;
- `interactiveReplay`;
- `controlledHarness`;
- `externalImport`;
- `generatedFixture`.

Default user-quality views exclude replay and fixtures. Replay analysis starts from a replay run or explicit replay filter.

### 8.2 Correct completion denominators

Do not use every event as the denominator for every rate.

Recommended metrics:

| Metric | Numerator | Denominator |
|---|---:|---:|
| Request error rate | error terminals | all terminal requests |
| Skip rate | skipped terminals | all terminal requests |
| Model-call rate | requests that called a model | eligible terminal requests |
| Suggestion yield rate | nonempty suggestions shown | model calls or eligible requests, label which |
| Acceptance rate | accepted suggestions | accepted plus shown-not-accepted suggestions |
| Cancellation rate | cancelled requests | started requests |
| Sanitizer-empty rate | empty after sanitizer | nonempty raw model responses |
| Permission/model-unavailable rate | matching outcomes | all terminal requests |
| Replay production rate | replay items producing output | completed replay items |
| Replay manual preference | preferred replay outputs | explicitly evaluated replay pairs |

Pending and queued records never enter terminal denominators.

### 8.3 Replay comparison is paired analysis

Matrix analysis should pair outputs by source event:

```text
source event A
  cell profile-1 x schema-small, rep 1..N
  cell profile-2 x schema-small, rep 1..N
source event B
  ...
```

Provide:

- per-cell distributions;
- paired latency and token deltas;
- output-presence deltas;
- normalized text diff or feature-specific similarity where appropriate;
- schema-source and fallback stratification;
- sample count and missing item count;
- optional manual rating;
- confidence intervals only when statistically justified;
- explicit exploratory label for stochastic model output.

A single call per cell is useful debugging evidence, not a stable quality conclusion.

### 8.4 Specialized analysis remains feature-owned

Share:

- dataset selector;
- filter chips;
- facet rail;
- virtualized pivot table;
- histogram or distribution primitives;
- drilldown drawer;
- run/cell/source deep-link format;
- empty/error/gap states.

Keep feature-owned:

- dimensions;
- metric definitions;
- eligibility;
- result evaluator;
- detail panels;
- comparison semantics.

Extract a common `analysisKit` only after completions is stable in the Debug Console and a second real provider needs the same primitive. Do not build a speculative generic schema around one tenant.

### 8.5 Perf Test History remains separate

Perf Test History represents controlled run directories, environment hashes, official eligibility, statistical gates, and baselines. It may link to the experiment definition and source artifact, but it should not merge its rows with interactive completion sessions.

---

## 9. Privacy, security, and untrusted imports

### 9.1 Rich classification must be semantic

The current key-driven redaction is not sufficient for a long-lived rich format. A completion serializer must classify at least:

| Field family | Classification |
|---|---|
| prompt messages, custom prompt | `model.prompt` and `user.text` |
| raw, sanitized, final response | `model.response` |
| schema-context formatted text | `sql.text` or feature-specific sensitive content |
| line prefix, statement prefix, suffix, SQL diagnostics | `sql.text` or `user.text` |
| document URI and file name | `source.path` |
| server, database, schema, object names | matching name classes |
| error message and stack | `user.text`, `source.path`, or `unknown` until sanitized |
| token counts, latency, booleans, enums | diagnostic metadata or metric |
| IDs and digests | diagnostic metadata |

Replace the narrow meaning of "redact prompts" with a defined **content-redacted** policy that covers all source, model, schema, path, diagnostic, and error content.

### 9.2 Capture-time and export-time policy

- capture-time policy sets the maximum fidelity ever stored;
- a segment rolls when policy changes;
- export can further reduce fidelity;
- export can never restore omitted content;
- a redacted stream advertises `replayPayloadAvailable=false` where appropriate;
- the UI explains why replay is disabled.

### 9.3 Import hardening

Before parsing an external trace:

- stat the file and enforce a configurable maximum;
- reject directory traversal and unsupported file types;
- parse in a worker or bounded streaming path for large files;
- enforce maximum event count, record count, string size, object depth, and aggregate decoded bytes;
- validate envelope, feature, event, and config schema versions;
- mark origin `externalImport` and trust `untrusted`;
- never auto-open a URI, run SQL, call a model, or execute a replay;
- render text through escaped React content;
- avoid raw HTML from imported diagnostics;
- show validation warnings and omitted fields;
- copy actions remain explicit user gestures;
- maintain a canonical content digest for deduplication;
- preserve the original file as an external reference unless the user explicitly imports a copy into the managed store.

### 9.4 Local storage protection

At minimum:

- use the extension's user-scoped storage root;
- create restrictive file and directory permissions where the platform supports them;
- show a persistent sensitive-capture badge for full local payload capture;
- provide "Clear sensitive captures" separately from "Clear all diagnostics";
- ensure retention and deletion cover child streams, replay artifacts, temporary exports, and abandoned active segments;
- do not include rich segments in crash dumps or logs.

Optional local encryption at rest is a future enhancement, not a prerequisite for the first unified store.

### 9.5 Export and central upload

- default `DcExport` remains Plane A only;
- "include rich feature data" is an explicit unchecked option;
- export preview lists classifications, redactions, omissions, bytes, and replay capability;
- default central policy refuses rich artifacts without opening their segments when the bundle summary is sufficient;
- any future policy that admits redacted or full model content must have a distinct versioned policy ID, exact preview, explicit confirmation, and canary fixtures;
- central upload success or failure never controls local gate or local evidence retention.

---

## 10. Migration and source-of-truth cutover

### 10.1 Migration principles

1. Do not rewrite or delete user trace files automatically.
2. Do not change setting meanings silently.
3. Do not make the new journal authoritative before reconciliation is proven.
4. Do not keep dual-write forever.
5. Make rollback a feature flag until the source-of-truth cutover stabilizes.
6. Preserve v1 import and export compatibility.

### 10.2 Recommended rollout

#### Stage M0: contract-only

- add global IDs and link fields;
- add strict v1/v2 trace parser;
- add viewer leases;
- no storage behavior change.

#### Stage M1: Debug Console parity on current stores

- de-fork services;
- move full UX into Debug Console;
- keep current in-memory and trace-file persistence;
- prove parity before storage work.

#### Stage M2: dark journal

- write the new rich journal behind an internal flag;
- current UI and exports continue reading the old path;
- compare event counts, IDs, terminal states, acceptance states, and digests;
- expose reconciliation health.

#### Stage M3: journal-backed history

- history provider reads journal and legacy files side by side;
- live ring remains current;
- exported v2 trace is assembled from repository snapshot;
- no automatic legacy file migration.

#### Stage M4: source-of-truth cutover

- journal becomes primary for new captures;
- save-on-deactivate legacy file becomes optional explicit compatibility export;
- external trace folder remains import/export library;
- enable bundle retention and repair;
- keep rollback flag for one stabilization window.

#### Stage M5: cleanup

- remove dual-write;
- remove old save-on-deactivate dependency from normal persistence;
- retain v1 loader and explicit v1-compatible export only as long as required;
- document migration and storage locations.

### 10.3 Reconciliation report

For each capture session during shadow mode, compare:

- created events;
- terminal events;
- unique capture event IDs;
- pending events at shutdown;
- accepted events;
- replay-tagged events;
- redaction mode;
- first and last timestamp;
- event digest after compatibility projection;
- dropped and truncated ranges.

Any mismatch blocks cutover.

---


### 10.4 Disposition of the companion plan work items

This table is the direct review map for the original execution plan.

| Original item | Disposition | Addendum direction |
|---|---|---|
| WI-0.1 dual-stamp identity | Keep, materially strengthen | use globally unique capture session/event IDs, a versioned link block, and deliberate emission ordering |
| WI-0.2 trace envelope v2 | Keep, materially strengthen | separate export, event, overrides, journal, and policy schema versions; reject unknown major versions |
| WI-1.1 de-fork by extraction | Keep, change shape | extract domain services plus a small façade, not one new monolithic host core |
| WI-1.2 full reducer surface over console RPC | Replace transport design | use typed commands, capabilities, revisions, operation IDs, progress, paging, and lazy detail |
| WI-1.3 mount full experience | Keep | direct component reuse, full Live and Sessions parity, lazy chunks |
| WI-1.4 refcount capture gating | Keep, generalize | named viewer leases with health and idempotent disposal |
| WI-1.5 retire standalone panel | Keep, gate by evidence | command alias remains; implementation deletion waits for parity, privacy, performance, and rollback gates |
| WI-1.6 tests | Keep, expand | add transport size, import security, multi-viewer, parity, and active cancellation tests |
| WI-2.1 feature capture journal | Replace record model | typed lifecycle records, event revisions, exact gaps, policy-per-segment, no generic merge patch |
| WI-2.2 manifest and retention extension | Replace ownership model | parent bundle plus independently owned child manifests; never two writers on one mutable manifest |
| WI-2.3 Sessions dataset reads store | Keep, clarify source of truth | journal becomes primary after shadow reconciliation; external trace files remain an import/export provider |
| WI-2.4 privacy boundaries | Keep, expand | semantic rich classification, broader content redaction, untrusted import limits, whole-artifact central refusal |
| WI-3.1 ReplayableFeature registry | Keep, strengthen | add semantics, safety, target, preflight, cancellation, estimate, result reference, repetitions, and durable run contract |
| WI-3.2 Replay Lab page | Keep, resequence | completions first; Query Studio only after safe adapter; STS2 remains separately gated |
| WI-3.3 config groups | Keep, strengthen | version, digest, effective config, layered provenance, and setting mutability |
| WI-3.4 export as perftest A/B | Keep as MVP scaffolding, replace long-term seam | introduce payload-free `ExperimentDefinitionV1`; generate `userSettings` or runtime steps based on mutability |
| Phase 4 analysis chrome | Keep, delay extraction | correct cohorts first; extract shared primitives only after a second real provider |
| Phase 5 STS2 tab | Keep as horizon | authoritative adapter, no format conversion, verification-only labels |
| Phase 5 central curated traces | Keep as explicit future policy | default remains refuse; require versioned policy, exact preview, and canaries |
| Phase 5 perftest completions | Keep, split | deterministic fake/recorded-model path and separate live-model exploratory path |
| "trace capture enabled by default" decision | Do not freeze yet | separate arming, fidelity, persistence, export, and upload semantics before revisiting defaults |
| "one manifest" definition of done | Replace wording | one bundle/catalog and lifecycle, with child-manifest ownership |
| Query Studio as immediate second replay tenant | Defer unsafe modes | parse-only and estimated plan first; exact target binding and active cancellation required |


## 11. Revised execution sequence

The sequence below replaces the original phase order where noted.

### Gate A: decisions and baseline

#### WI-A.1 Record branch and test baseline

**Repos:** all touched repositories

- record current branch heads;
- record generated-contract versions;
- run the existing standard verification chain;
- capture Debug Console and standalone completion screenshots or scripted UX evidence;
- save representative v1 traces, including redacted, truncated, replay matrix, and legacy-profile fixtures.

**Accept:**

- baseline results and known flakes are documented;
- no implementation work starts from an unknown branch state.

#### WI-A.2 Freeze identity and terminology ADR

**Files:** new observability ADR in `notes` and implementation docs

Freeze:

- host session, capture session, capture event, replay run, replay item, matrix cell;
- globally unique ID generation;
- Plane-A reverse-link attribute names;
- artifact and bundle vocabulary.

**Accept:**

- contract examples exist;
- no use of bare `sessionId` where the kind is ambiguous.

#### WI-A.3 Freeze artifact ownership ADR

Freeze:

- parent bundle manager owns `bundle.json`;
- child writers own child manifests;
- atomic update and repair behavior;
- retention and deletion ownership;
- behavior when Plane-A capture is off but rich capture is on.

**Recommendation:** create a bundle lazily whenever any child artifact is activated. `hostSessionId` remains available even when no Plane-A journal exists.

#### WI-A.4 Freeze capture and replay policy ADR

Freeze:

- capture arming, fidelity, persistence, export, upload, and trust dimensions;
- settings compatibility mapping;
- replay semantics labels;
- side-effect classes;
- config setting mutability;
- Query Studio initial safe modes.

---

### Phase 0: identity, compatibility, and capture leases

#### WI-0.1 Add durable capture identity

**Primary files:**

- `src/diagnostics/featureCapture/captureStore.ts`
- new `src/diagnostics/featureCapture/identity.ts`
- `src/sharedInterfaces/inlineCompletionDebug.ts`
- `src/sharedInterfaces/queryStudioReplay.ts`

Changes:

- accept or allocate globally unique `captureSessionId` and `captureEventId`;
- allow a preallocated ID to be inserted into the ring;
- preserve logical ID across ring eviction and reinsertion;
- maintain legacy display ordinals separately if useful.

**Accept:**

- IDs do not collide across restart, import, or multiple feature stores;
- pending finalization after eviction preserves one logical event.

#### WI-0.2 Add `ObservabilityLinkV1`

**Primary files:**

- new shared feature-capture contract;
- completion provider;
- Query Studio capture;
- event contract registry in `perftest`;
- generated vendored contract in `vscode-mssql`.

Changes:

- capture Plane-A trace and host session on rich records;
- emit optional reverse IDs on completion and Query Studio metadata events;
- register all attributes as diagnostic metadata;
- do not emit a capture event ID when no rich record exists.

**Accept:**

- test walks Plane A to rich event and rich event to Plane-A trace;
- correlation lint remains clean;
- default Plane-A export contains IDs but no rich payload.

#### WI-0.3 Correct completion result ordering

Allocate the optional rich ID before request capture. Return or otherwise propagate the ID so the terminal Plane-A result can include it without reading mutable global state.

**Accept:**

- one request produces one stable cross-plane link;
- skipped, no-model, permission, error, and success paths are covered;
- span-end behavior is documented if it cannot carry late fields.

#### WI-0.4 Replace viewer boolean with leases

Update standalone completion panel, Debug Console page, Replay Lab, and Query Studio replay surfaces.

**Accept:**

- all disposal order combinations pass;
- webview reload does not leak or prematurely release;
- health reports active leases;
- `recordWhenClosed` remains unchanged.

#### WI-0.5 Add strict export-envelope v2

Add `mssql.featureTrace/2` with separate event and overrides schema IDs. Keep v1 fixtures.

**Accept:**

- v1 and v2 round trips;
- unknown major version is rejected;
- malformed and oversized fixture tests pass;
- old trace folder still indexes.

---

### Phase 1: full Debug Console parity, without storage change

#### WI-1.1 Extract domain services

Move business behavior out of both controller and console host into the services described in Section 6.1.

**Accept:**

- no reducer business body is duplicated;
- service tests use fake dialogs, model catalog, schema service, repository, and clock;
- standalone and console adapters are thin.

#### WI-1.2 Introduce typed, versioned RPC

Replace stringly action dispatch with a discriminated command union and protocol capability response.

Include:

- protocol version;
- state revision;
- operation ID;
- typed validation result;
- progress notification;
- cancellation command;
- bounded error result.

**Accept:**

- invalid payload never reaches a service;
- stale revision behavior is tested;
- long operations do not return the full application state.

#### WI-1.3 Add thin rows and lazy detail

**Primary files:**

- `src/sharedInterfaces/debugConsole.ts`
- completion console host;
- completion Debug Console state provider;
- live grid and detail pane adapters.

**Accept:**

- initial page does not include prompt or response bodies;
- selecting an event fetches only requested detail;
- notification frequency and response sizes meet provisional budgets;
- detail parity is exact.

#### WI-1.4 Mount full Live and Sessions experience

Use direct shared component imports, not copied files.

**Accept:**

- all current Live detail tabs work;
- Sessions index, include toggles, add file, change folder, load, facets, pivot, histogram, drilldown, and send-to-basket work;
- gate-off page remains Plane A only.

#### WI-1.5 Mount full replay experience

Use the current replay service first. Storage and durable-run improvements come later.

**Accept:**

- single, session, basket, queue, matrix, reorder, reverse, all config modes, progress, and cancel work with standalone panel closed;
- result tags and analysis links remain present;
- no prompt leaks into Plane A.

#### WI-1.6 Deep link and parity gate

Route the existing command to the Completions page behind a feature flag. Keep the old implementation as rollback.

**Accept:**

- automated parity matrix is green;
- manual scripted parity evidence is attached;
- console bundle and first paint remain within budget;
- no fork markers remain.

---

### Phase 2: rich journal and session bundle

#### WI-2.1 Define journal and child manifest schemas

Add:

- `mssql.featureCapture.stream/1`;
- `mssql.featureCapture.record/1`;
- feature child manifest;
- segment descriptor with record range, event count, bytes, digest, policy;
- validation and repair result types.

**Accept:**

- schemas have golden fixtures;
- illegal lifecycle transitions are rejected;
- event projection is deterministic.

#### WI-2.2 Implement bounded journal writer

**Primary area:** `src/diagnostics/featureCapture/journal/`

Requirements:

- nonblocking `tryWrite`;
- record and byte caps;
- exact dropped ranges;
- batched append;
- segment roll by records and bytes;
- manifest atomic rename;
- closed-segment digest;
- flush barriers;
- health;
- failure isolation;
- test clock and filesystem abstraction.

**Accept:**

- fault-injection suite passes;
- no synchronous I/O occurs in capture call sites;
- product operation succeeds when writer fails.

#### WI-2.3 Implement bundle manager

**Primary area:** `src/diagnostics/sessionBundle/`

Responsibilities:

- lazy bundle creation;
- serialized artifact registration and summary updates;
- atomic `bundle.json`;
- startup reconciliation;
- stale active artifact repair;
- aggregate bytes and classification summary;
- session-level retention;
- health and clear-sensitive-captures.

**Accept:**

- diagnostic and rich writers never co-edit one file;
- bundle rebuild from child manifests works;
- partial child failure does not corrupt other artifacts.

#### WI-2.4 Connect completion lifecycle records

Hook created, finalized, acceptance, and annotation records into the journal.

**Accept:**

- acceptance survives restart;
- finalization after ring eviction preserves identity;
- no redaction resurrection;
- full and redacted segments project correctly;
- current UI read model remains unchanged.

#### WI-2.5 Add repository and indexed queries

Provide:

- capture session list from manifests;
- paged event rows;
- detail by ID;
- replay-capability flags;
- analysis streaming or worker input;
- external legacy trace provider.

**Accept:**

- indexing does not parse every full trace;
- 100k-event datasets remain navigable;
- live ring and history queries do not duplicate events.

#### WI-2.6 Shadow dual-write and reconcile

Enable internal dual-write for representative dogfood.

**Accept:**

- reconciliation report is exact;
- no capture-path performance regression;
- dropped ranges are visible;
- rollback flag works.

#### WI-2.7 Cut over source of truth

Switch new sessions to journal-backed history and v2 export.

**Accept:**

- explicit save/export flushes first;
- legacy files still import;
- no implicit legacy file deletion;
- save-on-deactivate compatibility path is documented or removed from default flow.

#### WI-2.8 Harden import, export, retention, and repair

**Accept:**

- malicious and oversized import corpus passes;
- content-redacted export canaries pass;
- default export excludes rich;
- retention deletes whole bundles and temporary files;
- repair marks incomplete evidence honestly.

---

### Phase 3: Replay Lab v2

#### WI-3.1 Add config-group and resolved-config contracts

**Accept:**

- current completion profiles serialize with version and digest;
- "live" config is frozen at run start;
- setting mutability is visible;
- incompatible matrix axes are blocked.

#### WI-3.2 Extend replay engine with v2 context

Add injected IDs, cancellation token, preflight, estimate, safety, result reference, and durable state callback. Preserve the current sequential kernel and per-item containment.

**Accept:**

- active cancellation reaches a fake adapter;
- partial and failed run states are correct;
- disposal does not silently lose run evidence.

#### WI-3.3 Add replay run repository

Persist run manifest and item log under the bundle.

**Accept:**

- reopening the Debug Console shows prior run status and results;
- incomplete runs are marked partial after restart;
- source, cell, config, and result links resolve.

#### WI-3.4 Implement explicit completion replay modes

Refactor `replaySourceEvent` around frozen prompt, captured-context rebuild, current-schema rebuild, and live-document scenario.

**Accept:**

- no implicit fallback;
- provenance and versions are visible;
- mode-incompatible axes are disabled;
- model/token cost estimate is shown;
- cancellation token reaches model request and response collection.

#### WI-3.5 Replace Replay Lab placeholder for completions

**Accept:**

- common basket and run UI works;
- embedded Completions page entry points share the same basket;
- run results deep-link to analysis;
- Plane-A replay spans carry only safe IDs and metadata.

#### WI-3.6 Add Query Studio safe replay adapter

Land parse-only and estimated-plan support first, with exact target binding.

**Accept:**

- no first-document fallback;
- target mismatch blocks;
- potentially mutating modes remain gated;
- active cancellation reaches execution host;
- side-effect warning names target and item count.

#### WI-3.7 Add Query Studio mutating-mode decision gate

Do not enable broad normal or actual-plan matrix execution until product and security review approves the policy.

---

### Phase 4: analysis convergence

#### WI-4.1 Correct completion cohorts and metrics

Add explicit result populations and provenance defaults.

**Accept:**

- live acceptance rate excludes skips, errors, pending, queued, and replay;
- replay production metrics are separate;
- fixtures cover every terminal result.

#### WI-4.2 Add paired matrix analysis

Add repetitions, source pairing, deltas, missingness, and exploratory trust labels.

**Accept:**

- matrix cells compare the same source set;
- incomplete runs do not fabricate denominators;
- fallback and replay mode are dimensions.

#### WI-4.3 Extract proven analysis primitives

Extract only components required by a second provider.

**Accept:**

- completions loses no dimension or drilldown;
- Query Studio or another real tenant uses at least one shared primitive;
- feature metrics remain provider-owned.

#### WI-4.4 Add Session History artifact chips

**Accept:**

- one host session can deep-link to its Plane-A trace, completions dataset, Query Studio captures, replay runs, and linked STS2 artifact;
- absent or refused artifacts have honest states.

---

### Phase 5: controlled experiment graduation

#### WI-5.1 Add `ExperimentDefinitionV1` to `perf-contracts`

Keep the contract payload-free and adapter-versioned.

**Accept:**

- both repositories validate golden fixtures;
- generated or vendored contract stays in sync.

#### WI-5.2 Generate perftest scenarios from config mutability

**Accept:**

- activation-time settings use `userSettings`;
- runtime settings use controlled config steps;
- generated scenario validates and has stable labels.

#### WI-5.3 Add deterministic completions pipeline scenario

Use fake or recorded model response.

**Accept:**

- scenario is reproducible;
- official eligibility is reviewed separately;
- prompt payload remains local or fixture-governed.

#### WI-5.4 Add live-model exploratory scenario

**Accept:**

- clearly exploratory;
- provider, model, rate, cost, and failure provenance recorded;
- no official gate claim.

#### WI-5.5 Extend central preview for bundle artifacts

**Accept:**

- default policy refuses rich child artifacts from manifest classification;
- exact counts and reasons appear;
- no rich segment is opened unnecessarily.

---

### Horizon: STS2 adapter and curated central traces

Keep the original horizon, with these constraints:

- STS2 adapter preserves authoritative formats and verification semantics;
- live source waits for supported sink or export integration and milestone approval;
- curated full model traces require a separate explicit upload policy;
- no horizon item blocks local completions convergence.

---

## 12. No-take-backs parity matrix

The coding agent should turn this table into a checked artifact for WI-1.6 and rerun it after storage and Replay Lab changes.

| Capability | Current completion behavior | Unified target | Gate |
|---|---|---|---|
| Pending request row | appears at request start | same, thin row plus lazy detail | automated |
| Terminal in-place update | pending becomes result | same logical ID and projected update | automated |
| Acceptance update | success becomes accepted | explicit acceptance record and same UI | automated |
| Live auto-scroll and selection | current panel behavior | same in Debug Console | manual plus webview |
| Full prompt tabs | system and user prompt | lazy detail, no content loss | automated fixture |
| Raw, sanitized, final response | separate detail | same | automated fixture |
| Schema context | full formatted view | same when policy allows | automated fixture |
| Locals dump | arbitrary diagnostic details | same plus classification/omission notes | automated fixture |
| Telemetry summary | current detail | same | automated fixture |
| Copy actions | IDs and payload sections | same explicit actions | webview |
| Profile picker | focused/balanced/broad/custom | same | webview |
| Model and continuation model | selectable | same | webview |
| Schema budget overrides | live | same, effective config recorded | unit plus webview |
| Other live overrides | live | same, mutability labeled | unit plus webview |
| Custom system prompt | edit/reset/save | same | integration |
| Record when closed | supported | same through leases | unit |
| Manual save | supported | repository flush plus export | integration |
| Save on deactivate | supported when enabled | compatibility or journal replacement, no data loss | integration |
| Redacted trace | supported | broader content-redacted policy | canary |
| Max file size | oldest-first truncation | bounded streaming export with truncation report | unit |
| External trace folder | watch and scan | remains first-class import library | integration |
| Add arbitrary trace file | supported | remains, hardened and untrusted | security |
| Change folder | supported | remains | integration |
| Import/export dialog | supported | remains | integration |
| Trace include toggles | supported | remains | webview |
| Multi-session load | supported | journal plus external providers | integration |
| Facets | supported | same dimensions plus provenance/mode | unit plus webview |
| Pivot and secondary pivot | supported | same | unit |
| Summary metrics | supported | corrected cohorts, no feature loss | unit |
| Latency histogram | supported | same or improved distribution view | webview |
| Drilldown | supported | same with lazy detail | webview |
| Send historical event to basket | supported | same | integration |
| Replay one event | supported | same with explicit mode | integration |
| Replay session | supported | same | integration |
| Basket add/remove/reorder/reverse | supported | same | unit plus webview |
| Snapshot mode | supported | same, versioned | unit |
| Override mode | supported | same | unit |
| Live mode | supported | same label, frozen at run start | unit |
| Queue | supported | same plus durable run | integration |
| Matrix | profile x schema budget | same plus generic axes and repetitions | integration |
| Matrix warning | cell threshold | calls/items/tokens/safety estimate | webview |
| Cancel | queued cancellation | queued plus active cancellation when supported | integration |
| Replay tags | run/cell/source | same plus replay item and global IDs | unit |
| Replay result analysis | dimensions | same plus paired analysis | unit |
| Gate-off page | metadata only | unchanged | privacy canary |
| Multiple viewers | current boolean risk | lease-safe | unit |
| Standalone command | opens panel | deep-links Debug Console | integration |
| Old v1 trace | loads | continues to load | fixture |

No row may be deleted merely because the shared abstraction does not support it. Extend the abstraction or keep a feature-specific path.

---

## 13. Test and verification plan

### 13.1 Unit tests

#### Identity and lifecycle

- ID uniqueness across stores, restarts, and imports;
- reserved ID preserved from pending through final and acceptance;
- pending eviction followed by finalization;
- acceptance after live-ring eviction;
- duplicate and out-of-order lifecycle records;
- illegal immutable-field mutation;
- event revision monotonicity;
- v1 projection equivalence.

#### Capture leases and settings

- two and three viewers in every close order;
- idempotent disposal;
- webview reload;
- `recordWhenClosed` interaction;
- settings migration and rollback;
- policy change rolls segment;
- redacted segment never accepts full-content amendment.

#### Journal and bundle

- record and byte queue overflow with exact ranges;
- segment roll by count and bytes;
- torn final line;
- missing child manifest;
- stale active manifest;
- root bundle atomic replacement;
- child writer failure;
- root rebuild;
- retention includes every child artifact;
- clear-sensitive preserves safe diagnostics when requested;
- export flush barrier;
- manifest digest validation.

#### Replay

- global run/item/cell IDs;
- config frozen at run start;
- preflight block;
- estimate and hard cap;
- active cancellation;
- partial run;
- adapter failure containment;
- restart marks incomplete run;
- source and result links;
- repetitions and pairing;
- no implicit completion schema fallback;
- mode-axis compatibility;
- Query Studio target mismatch;
- Query Studio potentially mutating block.

#### Analysis

- terminal cohort definitions;
- acceptance denominator;
- replay exclusion by default;
- pending and queued exclusion;
- partial run missingness;
- source-paired deltas;
- fallback dimension;
- exact versus exploratory trust label.

### 13.2 Import and security tests

- file over byte cap;
- event count over cap;
- deeply nested object;
- giant string;
- unknown schema;
- malformed JSON;
- truncated JSON;
- duplicate IDs;
- malicious paths;
- HTML/script strings;
- arbitrary locals keys;
- prompt canary in every sensitive field;
- SQL, row, token, connection string, path, and stack canaries;
- imported Query Studio record never auto-executes;
- imported completion trace never auto-calls a model;
- copy remains user initiated.

### 13.3 Integration tests

- live completion request links Plane A and Plane B;
- Query Studio completion surface uses the same capture store and event schema;
- full Debug Console workflow with standalone closed;
- external folder watcher and journal provider coexist;
- replay matrix produces durable run and linked result events;
- active replay cancellation;
- restart and history reload;
- export/import round trip;
- central preview refuses rich by default;
- Session History chips deep-link correctly.

### 13.4 Webview tests

- thin-row rendering;
- lazy detail loading and cache;
- stale revision handling;
- virtualized 100k rows;
- Sessions filters and pivots;
- replay run progress;
- cancellation state;
- explicit completion replay mode;
- Query Studio safety confirmation;
- screen reader labels, focus order, keyboard navigation;
- theme and high contrast;
- no raw imported HTML.

### 13.5 Fault injection

Inject failure at:

- every append boundary;
- after segment append but before child manifest;
- after child manifest but before bundle update;
- during atomic rename;
- during retention;
- during export snapshot;
- during replay item result persistence;
- while the UI is closed;
- while a capture policy changes;
- while acceptance arrives;
- while the active replay is cancelled.

Tests should prove recoverability or an honest `partial` state, not perfect durability by assertion.

### 13.6 Cross-repo contract tests

- event registry conformance;
- generated contract vendor sync;
- Plane-A classification of new IDs;
- `ExperimentDefinitionV1` golden fixtures;
- perftest scenario schema validation;
- official eligibility remains unaffected by interactive replay;
- STS2 adapter fixtures preserve run ID, sequence, cause, and digest.

### 13.7 Standard verification chain

At every relevant work item:

1. extension and webview typecheck;
2. full build;
3. focused unit tests;
4. full unit suite with known flakes documented, not hidden;
5. in-proc tests;
6. Debug Console smoke;
7. completions parity script;
8. representative perftest non-regression pair;
9. STS2 build and tests only when STS2 contracts or adapter code change;
10. privacy canary suite.

---

## 14. Provisional performance and scale budgets

These are starting budgets. Record current baselines first and adjust only with evidence.

| Area | Provisional requirement |
|---|---|
| Capture hot path | no file I/O, no full-state serialization, bounded allocation |
| Journal enqueue | p95 under 1 ms excluding event construction |
| Writer queue | bounded by records and bytes; overflow visible |
| Debug Console rich notifications | at most 4 updates per second per active page, coalesced |
| Initial Completions page payload | compact rows and settings only; no prompt/response bodies |
| Live row page | default 100 to 200 rows, cursor-paged |
| Event detail | one selected event, section-lazy |
| Session index | manifest-only scan, no full event parse |
| Large dataset | 100k events navigable with virtualization and worker/host aggregation |
| Replay | sequential by default, explicit adapter concurrency |
| Export | streaming or chunked, no quadratic repeated whole-file serialization |
| Bundle update | serialized, atomic, off hot path |
| Disk retention | includes all child bytes and temporary artifacts |
| Webview bundle | Sessions and Replay chunks lazy-loaded |
| Self-noise | excluded from default traces and official paths |

Add perftest scenarios for:

- completion capture disabled versus enabled;
- Debug Console closed versus Completions page open;
- journal persistence on;
- 500 live rows and lazy detail;
- 100k-session analysis fixture;
- 100-cell matrix UI without executing real calls;
- bundle startup repair;
- external trace indexing.

---

## 15. Risk register

| Risk | Severity | Mitigation |
|---|---:|---|
| Shared root manifest lost updates | Critical | parent bundle plus child ownership |
| Rich payload leaks into Plane A | Critical | structural separation, registry, canaries |
| Query Studio replay mutates real data | Critical | side-effect classification, exact target, safe modes first |
| Imported trace triggers execution | Critical | untrusted origin, explicit replay consent |
| Full-state RPC overwhelms webview | High | thin rows, paging, lazy detail |
| Ring eviction breaks logical identity | High | preallocated global IDs and journal update by ID |
| Acceptance lost after eviction or restart | High | typed acceptance journal record |
| Redaction misses `locals` or stacks | High | semantic serializer and classification |
| Capture-setting semantic drift | High | separate policy dimensions and migration |
| Writer corrupts bundle after crash | High | atomic manifests and rebuild |
| Replay cancel does not cancel active work | High | token in adapter contract |
| Replay config changes mid-run | High | freeze and digest at run start |
| Matrix conclusions overstate one stochastic sample | High | repetitions, pairing, exploratory labels |
| Profile ID changes meaning over time | High | profile version, definition digest, effective config |
| Legacy file workflow disappears | High | first-class external provider and parity gate |
| Standalone panel removed too early | High | evidence-based retirement and rollback flag |
| Journal overhead slows completions | Medium | nonblocking queue, benchmarks, dark launch |
| Bundle grows without bound | Medium | total bytes, age, count, child-aware retention |
| Analysis abstraction becomes lowest common denominator | Medium | feature providers, extract after second tenant |
| STS2 semantics blurred | Medium | authoritative adapter and verification label |
| perftest export becomes brittle JSONC text | Medium | typed experiment definition |
| Central upload opens refused rich payload | Medium | manifest-level classification refusal |
| Full local capture surprises user | Medium | persistent sensitive-capture badge and clear command |
| Version migration becomes ambiguous | Medium | independent schema IDs and strict parser |

---

## 16. Decisions to freeze before coding

| Decision | Recommendation |
|---|---|
| Physical unification | one bundle root, multiple child manifests |
| Parent schema | `mssql.observability.bundle/1` |
| Rich stream schema | `mssql.featureCapture.stream/1` |
| Rich record schema | `mssql.featureCapture.record/1` |
| Export schema | `mssql.featureTrace/2` |
| Replay run schema | `mssql.replay.run/1` |
| Config group schema | `mssql.configGroup/1` |
| Durable IDs | random UUIDs plus separate timestamps |
| Session terminology | host, capture, replay, perf, STS2 explicitly named |
| Plane-A reverse IDs | capture feature/session/event and replay run/item/cell |
| Capture defaults | unchanged for release during migration |
| Developer preset | explicit Observability Lab command or setting preset |
| Rich writer source of truth | journal after shadow reconciliation |
| Legacy files | retained as import/export library |
| Standalone command | permanent alias to Debug Console |
| Standalone implementation deletion | parity and rollback gated |
| Live replay config | frozen at run start |
| Completion replay fallback | explicit user-selected policy only |
| Query Studio first modes | parse-only and estimated plan |
| Query Studio arbitrary target fallback | prohibited |
| Interactive replay official eligibility | false |
| Full model content central upload | future explicit policy only |
| STS2 storage | authoritative external artifact, no conversion |
| Analysis extraction | after a second real provider |
| Local encryption | future option; restrictive local handling now |

---

## 17. Rejected alternatives

Do not pursue these shortcuts:

1. Put prompts or SQL text into `DiagEvent` under a "full" mode.
2. Create one mega-event schema for completions, Query Studio, STS2, and perftest.
3. Let multiple writers patch the same root manifest.
4. Use local counters as durable IDs.
5. Preserve the full-state pull protocol for parity.
6. Treat a generic JSON patch as the event lifecycle.
7. Treat completion replay fallback as harmless implementation detail.
8. Count replay output as user acceptance.
9. Expose normal Query Studio execution matrices without target and side-effect policy.
10. Convert STS2 envelopes to feature capture events.
11. Generate only free-form JSONC and call that a cross-repo experiment contract.
12. Delete the standalone panel after a fixed milestone regardless of evidence.
13. Flip rich persistence on by default before capture policy and storage migration are clear.
14. Parse every full trace file to build a session index.
15. Auto-import or auto-replay external traces.

---

## 18. Final definition of done

### One primary UX

- the Debug Console contains the complete completion Live, Sessions, detail, and replay entry points;
- the existing command deep-links there;
- no forked reducer, state, or component copy remains;
- the old implementation is removed only after parity and rollback gates.

### One evidence catalog

- a host-session bundle catalogs Plane A, rich captures, replay runs, and external references;
- each writer owns its child manifest;
- retention, health, repair, export preview, and Session History understand all artifacts;
- the journal is the historical source of truth for new rich captures;
- legacy trace files remain loadable.

### One identity vocabulary

- every durable rich event has globally unique capture session and event IDs;
- Plane A and Plane B cross-link in both directions when rich capture exists;
- replay runs, items, and cells have stable IDs;
- correlation and contract tests are green.

### One safe replay pattern

- Replay Lab uses shared basket, config group, run, progress, cancellation, and result chrome;
- completions has explicit replay modes and full provenance;
- Query Studio enables only policy-approved modes and targets;
- run artifacts survive UI close and restart;
- STS2 remains verification-specific.

### One honest analysis story

- live-user and replay cohorts are separate by default;
- acceptance and error denominators are correct;
- matrix analysis is paired and reports missingness and sample count;
- feature metrics stay specialized;
- Perf Test History remains official-provenance specific.

### No takebacks

- every row in the parity matrix is green;
- v1 files load;
- external folder workflows work;
- all detail tabs and settings overrides remain;
- all current replay entry points and config modes remain;
- privacy, scale, and fault-injection suites pass.

### Cross-repo coherence

- Plane-A vocabulary is registered and vendored correctly;
- experiment contracts validate in both repos;
- perftest graduation respects setting mutability and eligibility;
- STS2 adapter work preserves its authoritative schema and milestone gates;
- design notes and implementation docs match the final code.

---

## 19. Instructions for the coding agent

1. Start from the current `dev/query` branch in each repository and record branch heads.
2. Do not combine de-forking, storage cutover, Replay Lab v2, and Query Studio unsafe replay into one change set.
3. Land additive contracts before consumers.
4. Keep each PR or commit batch independently buildable and rollback-capable.
5. Preserve the current completions read model until the Debug Console parity gate passes.
6. Add tests before deleting compatibility code.
7. Run privacy canaries whenever a field, serializer, export, or upload path changes.
8. Run capture-path performance checks whenever store or journal code changes.
9. Never infer that an imported file is trusted because it has a known filename.
10. Never execute Query Studio replay against a substituted target without a new explicit user action.
11. Update the companion plan and this addendum when branch reality changes.
12. Record every intentional semantic change in an ADR or migration note.
13. Do not mark interactive completion replay metrics official.
14. Do not touch STS2 internals merely to make them fit the feature-capture abstraction.
15. Treat the parity matrix as a release gate, not a documentation checklist.

---

## Appendix A: suggested bundle contract

```ts
interface ObservabilityBundleV1 {
    schema: "mssql.observability.bundle/1";
    bundleId: string;
    hostSessionId: string;
    createdUtc: string;
    updatedUtc: string;
    closedUtc?: string;
    status: "active" | "closed" | "partial";
    provenance: {
        extensionVersion?: string;
        extensionCommit?: string;
        vscodeVersion?: string;
        platform?: string;
    };
    artifacts: ObservabilityArtifactDescriptorV1[];
    totals: {
        artifacts: number;
        events?: number;
        records?: number;
        bytes: number;
        gaps: number;
        truncations: number;
    };
}

interface ObservabilityArtifactDescriptorV1 {
    artifactId: string;
    kind:
        | "diagStream"
        | "featureCapture"
        | "replayRun"
        | "perfRunRef"
        | "sts2RunRef"
        | "externalImportRef";
    featureId?: string;
    schema: string;
    relativeManifest?: string;
    externalRef?: string;
    createdUtc: string;
    updatedUtc: string;
    status: "active" | "closed" | "partial" | "invalid" | "missing";
    records?: number;
    events?: number;
    bytes: number;
    gaps: number;
    truncations: number;
    classification: {
        containsRichPayload: boolean;
        maximumClass: string;
        policyId: string;
        replayPayloadAvailable?: boolean;
    };
    manifestDigest?: string;
}
```

## Appendix B: suggested capture policy contract

```ts
interface RichCapturePolicySnapshot {
    schema: "mssql.richCapturePolicy/1";
    policyId: string;
    featureId: string;
    fidelity: "fullLocal" | "contentRedacted" | "digestOnly";
    persistence: "memoryOnly" | "localJournal";
    source: "viewerLease" | "recordWhenClosed" | "developerPreset" | "test";
    activatedAt: number;
    expiresAt?: number;
    replayPayloadAvailable: boolean;
}
```

## Appendix C: suggested replay safety contract

```ts
interface ReplaySafetyAssessment {
    sideEffectClass: "none" | "readOnlyExpected" | "potentiallyMutating" | "unknown";
    targetBinding: "none" | "exactRequired" | "userSelected";
    requiresConfirmation: boolean;
    requiresSandbox: boolean;
    reasons: string[];
    blockedReason?: string;
}

interface ReplayEstimate {
    sourceItems: number;
    matrixCells: number;
    repetitions: number;
    totalExecutions: number;
    estimatedInputTokens?: number;
    estimatedOutputTokens?: number;
    estimatedCost?: number;
    currency?: string;
    warnings: string[];
}

interface ReplayExecutionContext<TSource, TConfig> {
    replayRunId: string;
    replayItemId: string;
    matrixCellId?: string;
    repetition: number;
    source: TSource;
    config: TConfig;
    configDigest: string;
    target?: {
        kind: string;
        fingerprint: string;
        label: string;
    };
    provenance: ReplayProvenance;
}
```

## Appendix D: recommended completion replay provenance

```ts
interface CompletionReplayProvenanceV1 {
    schema: "mssql.completionsReplayProvenance/1";
    mode:
        | "frozenPrompt"
        | "rebuildCapturedContext"
        | "rebuildCurrentSchema"
        | "liveDocumentScenario";
    promptBuilderVersion?: string;
    sanitizerVersion?: string;
    sourceEventSchema: string;
    sourcePromptDigest?: string;
    sourceSchemaContextDigest?: string;
    replaySchemaContextDigest?: string;
    schemaContextSource:
        | "captured"
        | "current"
        | "disabled"
        | "unavailable"
        | "explicitFallback";
    extensionVersion: string;
    extensionCommit?: string;
    model: {
        requestedSelector?: string;
        resolvedVendor?: string;
        resolvedFamily?: string;
        resolvedId?: string;
    };
    effectiveConfigDigest: string;
}
```

## Appendix E: first implementation slices

A practical PR sequence is:

1. identity contracts and viewer leases;
2. completion and Query Studio dual links;
3. strict v2 export parser and fixtures;
4. domain-service de-fork;
5. typed thin RPC and lazy detail;
6. full Debug Console parity;
7. child journal schema and reducer;
8. writer, health, and fault tests;
9. bundle manager and Session History chips;
10. shadow dual-write and reconciliation;
11. journal source-of-truth cutover;
12. replay config groups and durable run artifact;
13. completion replay modes and active cancellation;
14. Replay Lab completions;
15. Query Studio safe adapter;
16. analysis cohort corrections and paired matrix analysis;
17. typed perftest experiment definition;
18. deterministic and exploratory completions harness scenarios;
19. STS2 verification adapter after its gate.

This sequence keeps the best current completions experience available throughout the migration and turns each abstraction into a proven shared component rather than a speculative rewrite.
