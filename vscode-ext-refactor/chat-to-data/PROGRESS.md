# Chat to Data — Build Journal (PROGRESS)

**Spec:** `chat_to_data_execution_plan.md` (base) + `chat_to_data_addendum.md` (wins over base). **This journal wins over both.**
**Restart protocol:** read this journal → base plan → addendum → continue from the first unfinished batch.
**Repos/branches:** `vscode-mssql` `dev/query` (primary), `perftest` `dev/query` (contracts + scenarios), `sqltoolsservice` untouched in v1.
**Commit prefix:** `c2d:` (vscode-mssql), perftest commits follow its existing conventions.
**Verification chain per batch:** build:extension + build:webviews + lint + unit suite (vscode-mssql); perftest build + tests + conformance on any registry change (regenerate + re-vendor both repos). Known pre-existing suite failures (NOT ours): sqlScripting strict-host CACHE-6 `drop` capability, sqlLanguage static `sys.all_*` catalog, CopilotChatEntry before-each flake.

**Branch law (Karl, 2026-07-09):** `dev/query` must stay **zero-impact / net-new additive** vs `main`. All C2D surfaces live behind `mssql.queryResults.*` and the existing `mssql.queryStudio.enabled` posture; no change to a main-branch feature's behavior when the new feature area is disabled.

---

## Entry 0 — Plan established + §12.1 current-state verification (2026-07-09)

### Verification results (addendum §12.1, run against local `dev/query` @ `04dbe8fbf`)

All addendum claims verified, with one large favorable drift: **the QO plan completed through QO-9 after the addendum was written** (addendum assumed QO-1..3 + QO-9a only).

1. **QO-6 already landed.** `RowStore.getRows` is `async`, takes `reason: RowReadReason` (`"grid" | "copy" | "export" | "text" | "cellDocument" | "diagnostic"`) and optional column projection (`{start, count}`, QO-7b). Protected/probationary cache segments, served-window cache, bounded async spill queue with append backpressure all exist (`rowStore.ts` header). Admission policy: `admit = reason !== "export" && reason !== "text"` (`rowStore.ts:412`).
2. **ExecutionHost.getRows already async + reason + columns** (`executionHost.ts:296`). Run start resolves one QueryTuning snapshot (QO-1), passes diagnosticsLevel + RowStoreTuning to the store, calls `beginRunRecord` (`:144`), sends wire params per batch. Rerun still hard-disposes the store (`:121`) and `dispose()` force-disposes (`:412`) — **exactly the C2D-1 seam**.
3. **Messages are still a plain `QsMessageRow[]`** on the host (no MessageStore landed). §5.6 capture-as-interface stands.
4. **`QsUpdateGridSelectionRequest` still a no-op** (`queryStudioController.ts:886`, payload `sharedInterfaces/queryStudio.ts:449`).
5. **`liveModels` module-level map confirmed** (`queryStudioEditorProvider.ts:32`); registration-based live sources rule stands.
6. **`runQueryTool.ts` still returns every row unbounded** (`rows: result.rows`, `:94`) via legacy `query/simpleexecute`. §4.1 P0 cap confirmed necessary.
7. **`QsCellWindow` carries `nullBitmap`/`typeHints`/`truncatedBitmap`** (`queryStudio.ts:243`). CellReader (§1.5) plan stands.
8. **Custom editor contributions to copy:** `mssql.executionPlanView`, `mssql.queryStudio` (`package.json:364+`). Registry: `perftest/packages/observability-contracts/src/registry/event-types.json`, now **95 events** (was 81) — registry-first mechanics unchanged.

### Sequencing decisions (binding)

- **C2D-D-01 resolved by events:** QO-6 landed first. The §5.5 "inverted order" path applies — the `IQueryResultStore` facade **wraps the async store natively**; no sync-inside/async-outside shim needed. `getWindow(req)` maps ~1:1 onto `RowStore.getRows(id, start, count, reason, columns)`.
- **`RowReadReason` is extended additively** with `"sample" | "profile" | "transform" | "aiTool"` and those reasons join the no-admit list (scan reads must not evict the viewport). This is the only `rowStore.ts` internal edit C2D makes; QO is complete so there is no file-ownership conflict.
- **Qs\* RPC reuse: YES for slice 1** (addendum C2D-0 decision). The pinned document webview speaks the existing `qs/*` request names to its own controller; neutral names deferred to post-extraction cleanup.
- **C2D-D-11 (new, zero-impact law):** the `mssql_run_query` P0 cap (§4.1) applies **only when `mssql.queryResults.ai.enabled` resolves true AND the queryResults feature area is active**; with the feature off, the tool behaves byte-for-byte as on `main`.
- Commit prefix `c2d:`; journal entries per batch, same rules as QO's journal.

### Batch order

C2D-0 (this entry + spike) → C2D-1 → C2D-2 → C2D-3 → C2D-4 → C2D-T → C2D-5 → C2D-6 → C2D-7/8 → C2D-9 (future tiers). Tasks #17–#25 in the session tracker mirror these.

### Residuals / open

- C2D-0 spike results recorded in Entry 1.
- `runId` vs run-record id join (§1.6): decide during C2D-1, record here.

---

## Entry 1 — C2D-1 complete: result access layer (2026-07-09)

**Commits:** vscode-mssql `ef501c539` (c2d:), perftest `f55cc30` (contracts).

**Plan deviation (recorded per C2D-0):** the custom-editor URI spike moved into C2D-3, where a vscode-test integration test will prove `vscode.openWith` on the virtual snapshot URI mechanically — C2D-1 has no dependency on that seam, so nothing was de-risked by doing it first.

### What landed

- `src/queryResults/queryResultTypes.ts` — full contract vocabulary: `IQueryResultStore` (async `getWindow` + `reason` + `streamRows`, per addendum §1.2), leases/owners, frozen summaries, snapshot/provenance/status types, typed `QueryResultAccessError`.
- `src/queryResults/resultStoreLease.ts` — `RetainedRowStore`: live lease minted at construction, `retain()` returns `undefined` unless `active` (race-clean), final release drives `active → draining → disposed` and disposes the RowStore (spill deleted), `releaseLiveOwner` demotes the memory cap lazily (addendum §5.1) via new `RowStore.shrinkMemoryCap` (override field — never mutates shared DEFAULT_LIMITS), `streamRows` chunk generator, `windowReads` counter = the scan-free proof source.
- `src/queryResults/queryResultAccessService.ts` — live-source registry (models self-register; nothing scans `liveModels`), scan-free snapshot creation (frozen summaries from the store, completed-only rule, message/query capture policies: summary-always, `allLocal` under `maxLocalMessages`, query digest default/localOnly optional), snapshot leases (pinned purpose disposes on last release; AI/chat idle under TTL), retention sweep (TTL first, then LRU while over `maxUnpinnedStores`; budget deduped by storeId; leased snapshots never victims), `status()`, singleton accessor.
- `src/queryResults/queryResultsParams.ts` — registered knob module (`mssql.queryResults.*` + `overrides` carrier, clamps, sha256[0:12] digest). Settings declared in package.json.
- `src/queryResults/spillHygiene.ts` — session nonce (`run<n>_<nonce>` dirs via ExecutionHost), `session-<nonce>.lock` heartbeat (60s, unref'd), startup orphan sweep (15s delayed) that only removes nonce-stamped dirs with stale/absent locks; legacy `run<n>` dirs untouched (old-code sibling windows).
- `ExecutionHost`: rerun/dispose release the live lease instead of force-dispose (identical behavior when no leases exist); `RetainedRowStore` carries runId `qsrun_<random8>` + tuningDigest/profile + runRecordId (stamped after `beginRunRecord` — **§1.6 decision: separate opaque runId, joined to the run record by stamping, recorded here**). `RowReadReason` extended additively (`sample|profile|transform|aiTool`), all non-interactive reasons now stream without cache re-admission.
- `QueryStudioDocumentModel` registers a `QueryStudioLiveResultSource`; deregistration on dispose. Deactivation disposes the access service + stops the spill lock (wired into `registerQueryStudioFeatures`).
- Registry: 8 `queryResults` events + 1 metric, regenerated + re-vendored, contracts suite 27/27.

### Verification

- 28 new unit tests green (leases/state machine/interleavings, window byte-equivalence, streamRows ≡ windows, demotion drain, spill delete on final release, scan-free creation over 20 sets, TTL/budget sweeps, capture policies, params clamps/digest, orphan sweep incl. live-sibling + legacy safety, privacy canary over describe/status/list).
- Full unit suite: only the 3 known pre-existing failures (sqlScripting CACHE-6, sqlLanguage `sys.all_*`, CopilotChatEntry flake). build:extension + lint clean. No webview changes.

### Residuals

- `extensionDeactivate` release reason currently reported as `documentClosed` via model dispose; cosmetic, revisit in C2D-8 if status wants the distinction.
- Retained-store re-promotion on sustained pinned scrolling: C2D-8 polish (C2D-D-09 unchanged).

---

## Entry 2 — C2D-2 + C2D-3 complete: pin commands + pinned document (2026-07-09)

**Commits:** vscode-mssql `df51db2f5`, perftest `a1c77d5`. **Batches merged deliberately** — pin commands are only meaningful with the document they open; exit gates of both batches verified together.

### What landed

- RPCs `qs/pinResultSet` + `qs/pinAllResults` (no separate popOut request — "Pop Out/Pin All" is one action; base-plan §9.2's third RPC dropped). Controller `pinResults` gates on `pinnedDocumentsEnabled`, snapshots via the access service (`includeMessages: "allLocal"`, `includeQueryText: "digest"`), opens the pinned doc, then releases the creator lease — a failed open therefore disposes the snapshot instead of leaking it.
- UI: per-set pin button in `GridCaption` (via new `captionExtras` prop; complete sets only, hover-quiet) and a pin-all button in the results tab strip (hidden while streaming). Refusals surface via the existing `actionHint` status-line pattern. Palette commands deferred to C2D-4 (need context-key/active-editor resolution to be non-guessy).
- `mssql.queryResultsSnapshot` readonly custom editor (`*.mssqlresults`, priority default) + `mssql-query-results-snapshot:` scheme with a minimal readonly FileSystemProvider (stat/readFile empty, writes throw NoPermissions). URI: `/<Pinned Results HH.MM.SS xxxx>.mssqlresults?sid=<snapshotId>`; `pinnedResultsUriParts` accepts strictly `[A-Za-z0-9_-]` ids.
- `PinnedQueryResultsDocument` holds the snapshot lease from `openCustomDocument`; document dispose releases it → pinned-purpose snapshot disposes → store lease releases. Unknown/expired sid → expired document, no lease, no throw.
- `PinnedResultsController` (WebviewBaseController, bundle `queryResultsSnapshot`): answers `qs/getRows` (reason `grid`, clamped by the service), `qs/saveResult` (reason `export`), `qs/openCellDocument` (reason `cellDocument`, same raw-first format-limit policy), `qs/openPlan` (plan XML from snapshot cell 0), `qs/getMessages`/`qs/getMessagesText` (frozen local capture); navigate/viewMode/selection are honest no-ops.
- Webview page `src/webviews/pages/QueryResultsSnapshot/` reusing `ResultGridBlock`/`MessagesView`/`QsResultsGridProvider` — no grid fork; header (source title, rows, pinned time, read-only), Results/Messages tabs, maximize/restore, lazy mounting, `computeResultsLayout` sizing. Expired state renders a recovery explanation.
- Registry: `pin.open.begin/end`, `pin.close` + `pin.open` metric (the conformance suite caught the unregistered emissions exactly as designed — registered, regenerated, re-vendored).

### Verification

- 31 queryResults tests green (URI contract, contribution/activation-event static checks, guard). Full suite 4404 passing / 2 failing — both documented pre-existing (sqlScripting CACHE-6, sqlLanguage `sys.all_*`; CopilotChatEntry flake dormant this run). build:extension + build:webviews (typecheck + esbuild bundle incl. new page) + lint clean.
- **Deviation:** the repo's unit host never opens real custom editors, so the `vscode.openWith`-on-virtual-URI proof is NOT automated (repo idiom = static contribution tests). First manual dogfood pass must exercise: pin one set, pin all, rerun source, close source, close pinned tab, window reload → expired document.

### Dogfood checklist for Karl

1. Run a query → hover a grid caption → pin icon → pinned tab opens beside with frozen rows.
2. Rerun with different WHERE → pinned rows unchanged; close the .sql editor → pinned still scrolls/copies/exports.
3. Pin-all on a multi-set run (plan sets show as plan links).
4. Close pinned tab → `mssql.queryResults.*` status (C2D-4 command, or Debug Console) shows store released; spill dir gone.
5. Reload window → restored pinned tab shows the "no longer available" message (in-memory by design).

---

## Entry 3 — C2D-4 complete: active-result context (2026-07-09)

**Commits:** vscode-mssql `45cfa64f4`, perftest `859fbef`.

- `QsGridSelectionUpdate` payload (resultSetId, active cell, ranges capped at 64, cell/row counts, displayedRowCount, reason, host-stamped `snapshotView`) replaces the tiny no-op shape; grids send it throttled (200 ms trailing) through the pre-existing `FluentResultGrid.onSelectionSummaryChange` seam — no grid internals touched.
- `QueryResultContextService` (`src/queryResults/queryResultContextService.ts`): most-recent-wins across live grids and pinned docs (full §12.2 focus ladder deferred to the chat surfaces that need it — journaled deviation); context keys `hasActiveSource` / `hasActiveSelection` / `activeSourceKind`; `clearForSource`/`clearForSnapshot` wired into model dispose and pinned-document dispose; injectable key-setter keeps the core vscode-free.
- `mssql.queryResults.showStatus` (palette, gated on queryStudio.enabled): pure `renderQueryResultsStatus` builder → JSON side doc; snapshot ids truncated to 12 chars; canary-tested.
- **Deviation/residual:** selection ranges are DISPLAY row space; source-row-id mapping for sorted/filtered grids deferred (sort/filter only engages in-memory ≤ threshold; the AI selection scope in C2D-T/5 uses visible-window/sample strategies instead). `context.update` marker registered + vendored.
- 36 queryResults tests green; full suite at the known pre-existing failures only.

**Next: C2D-T** (CellReader, transform spec v1, fused budgeted engine, derived snapshots, sampler/profiler as canned specs) — the core of the "apply algorithms to result sets" platform Karl asked for — then C2D-5 (gate + `mssql_query_results` tool + run_query cap), then C2D-6 (`@query`).

---

## Entry 4 — C2D-T complete: transform platform (2026-07-09)

**Commits:** vscode-mssql `7cf0b3e93`, perftest `bdf4da0`.

### What landed

- `cellReader.ts` — `windowCellReader` (bound per window, not per cell), `cellEqualityKey` (type-prefixed; truncated → digest key or explicit incomparable marker), `cellNumeric`.
- `transformSpec.ts` — spec v1 exactly per addendum §3.4 (filter pred tree ≤200 nodes, project, slice; terminals rows/aggregate/groupBy/topK/histogram/distinctCount/sample incl. `reservoir`), strict path-reporting validation, canonical digest, `transformOutputClass` (§1.4 function — groupBy keys/min/max/auto-histogram are values-class; the C2D-5 gate consumes this).
- `transformEngine.ts` — fused single-pass scan (ops keep per-stage column mappings; slices count post-filter), Welford sum/avg/stddev, groupBy `__other__` overflow bucket with counted keys, topK value/frequency (frequency approximate-flagged past `maxDistinctExact`), histogram (caller boundaries or auto via budget-charged min/max pre-pass), head/head_tail/uniform_windows/seeded-reservoir sampling, cooperative `setImmediate` yields + cancellation checks, budgets → `EvalStats { partial, partialReason }`. Deterministic per (snapshot, spec, budget).
- Access service: `snapshotReader` (frozen-clamped, reason-tagged), `evaluateSnapshotTransform` (params-derived budgets; digest+stats markers, never literals/values), `deriveSnapshot` (id-collection rides the scan under a count terminal — zero output materialization; over-cap and partial → typed errors; derive-from-derived composes to physical ids), derived `getWindow` via contiguous-run stitching; lineage in `describeSnapshot.derived`.
- Params: 9 transform/derive knobs appended to the registry (settings sections defined; **package.json declarations deliberately omitted** — `mssql.queryResults.overrides` is the documented carrier, C2D-D-10 posture; journaled deviation).
- Registry: transform.evaluate.begin/end (+metric), derive.begin/end. **No separate `transform.canceled` event** — cancellation is `partialReason: "canceled"` on evaluate.end (deviation from addendum §7 list, journaled).
- Sampler/profiler as canned specs: sampling IS a spec terminal; the shape/safe-counts/values profiler tiers land with the C2D-5 tool that needs their gating (deferral journaled — no bespoke profiler was built to be rewritten later, which was §3.8's actual point).

### Verification

22 new tests (golden vs naive reference for every op/terminal, seeded 25-round property test across odd chunk seams, per-cap budget honesty, cancellation at yield, NULL/truncated semantics, overflow accounting sums to rowsMatched, derived stitching + middle windows + parent-close survival + compose + lineage + typed errors). Full suite 4431 passing / 2 known pre-existing. Contracts 27/27.

---

## Entry 5 — C2D-5 complete: gate + mssql_query_results + run_query cap (2026-07-09)

**Commits:** vscode-mssql `2bcaf0d82`, perftest `c7b04aa`.

- `resultAccessGate.ts` — `ResultAccessGate` (crypto-random single-use grants, 2-min TTL constant, owner/snapshot/class scope, mint/denial markers) + `GatedQueryResultAccess`, the ONLY surface AI consumers get: value-class enforcement computed from the spec via `transformOutputClass` (§1.4 — never caller-asserted), per-owner snapshot cap, single concurrent transform, `release_snapshot` → new `disposeUnleasedSnapshot` service method.
- `queryResultsTool.ts` — `mssql_query_results` (toolReferenceName `query_results`), 9 operations; `prepareInvocation` shows Continue/Cancel (details folded into markdown per §4.3) ONLY for values-class requests (`operationNeedsConfirmation` mirrors the classification function; unit-matrixed); `call` mints the grant post-consent and the facade enforces it; values payloads ride a random-fenced treat-as-data block (§4.4), control chars stripped, per-cell/per-response caps; feature-off → clean decline (zero-impact). Registered in `MainController.registerLanguageModelTools` + package.json `languageModelTools` (description teaches the run=execute+head / query_results=analyze division of labor). AI params (`ai.maxRowsPerResponse/maxBytesPerResponse/maxCellBytes/maxSnapshotsPerConversation`) in the registry.
- `runQueryTool.ts` P0 cap per §4.1, gated on `mssql.queryStudio.enabled` + `ai.enabled` (C2D-D-11): truncated/totalRowCount/returnedRowCount metadata + guidance text; byte-identical to main when off.
- **C2D-D-02 held:** no remembered grants — single-use per invocation. **Deviation:** grant TTL is a constant (2 min), not a registered param — security posture, not a perf knob; revisit only with policy work. Owner key = per-window nonce (§1.8 best-effort; documented in code).
- 7 gate tests green; full suite 4438 / 2 known. grant/aiTool vocabulary registered, conformance green.

---

## Entry 6 — C2D-6 complete: @query participant (2026-07-09)

**Commit:** vscode-mssql `27ecc19a1`.

- `queryParticipant.ts` — `mssql.query` (`@query`), registered unconditionally in extension.ts beside `mssql.agent` (static contribution must not dangle); the handler explains itself when `mssql.queryStudio.enabled`/`ai.enabled` are off. Resolution ladder subset: active pinned snapshot → active grid source (snapshotted on demand under the chat owner key) → single unambiguous live source → list candidates and ask (never guess).
- `/list`, `/summarize` (one aggregate spec per set: count + per-column nullCount, ≤8 columns, ≤5 sets; partial-scan honesty rendered), `/profile` (adds min/max → values class → one Allow-once modal via the gate path; decline falls back to the value-free summary), `/pin` (pinned-purpose snapshot + document, creator lease released after open).
- **Deviations journaled:** `/report` deferred to C2D-7 (report = prose over engine outputs; the deterministic summary covers dogfood value now). Summaries are deterministic markdown, not model-generated prose — the participant makes no LM calls in v1; prose lands with /report. Followups (plan §C2D-6 task 6) deferred with it.
- Full suite at the known pre-existing failures only.

**Remaining backlog (C2D-7/8/9):** /report + value-tier profiling polish, derived-snapshot pinning UI, progress UI for long scans, `queryresults-*` perftest scenarios over QO-9a fixtures (incl. pin-multiset-100 per §5.7 and scan-throughput budgets), retention/status Debug-Console page hook, pinned-tab soft cap + `getState` rehydrate spike, webview memory data, arrow-export decision (C2D-D-04), headless-run P1 (§4.1).

---

## Entry 7 — C2D-7/8 complete: report, pin surface, hardening, perf scenarios (2026-07-10)

**Commits:** vscode-mssql `9c09004a2`, perftest `12a112c`.

### What landed

- `@query /report` (plan §14.3 shape): local aggregate specs compute per-set row/null statistics; a head/tail 10-row sample crosses only after an Allow-once modal; the chat model (`request.model`) writes Markdown prose from summaries + the injection-delimited sample. `stream.progress` notes ride every local scan. `/summarize` also gained progress.
- Pin surface unified in `pinCommands.ts` (`pinSourceResults` / `pinExistingSnapshot`), now behind: webview buttons, **`mssql.queryStudio.pinAllResults` palette command** (the C2D-2 deferral; gated on `hasActiveSource` context key; optional `{uri}` arg for harness/scripting), `@query /pin`, and the tool's new **`pin_snapshot`** operation — completing the "AI derives a filtered view, user pins it" flow (the pinned document's lease takes an aiTool snapshot out of TTL reach naturally).
- Hardening: pinned-tab soft cap warns once past 8 pinned-document leases (C2D-D-09 soft-warn; rehydrate still deferred pending dogfood memory data); gate keeps a 32-entry mint/denial ring surfaced in `showStatus` as `recentGrantActivity` (class+outcome only); `release_snapshot` now disposes the unleased snapshot immediately via `disposeUnleasedSnapshot`.
- Perf instrumentation: `mssql.queryResults.pin.rendered` webview first-paint mark (double-rAF) + `pin.toRender` boundary metric; hidden `mssql.queryResults.benchmarkTransform` command (groupBy(count) over the newest snapshot's largest set) as the harness probe.
- **perftest scenarios** (exploratory, wallclock unofficial): `queryresults-pin-after-100k` (pin command → first pinned paint; pin.open + pin.toRender metrics; snapshot.create.end as scan-free proof), `queryresults-pin-survives-rerun` (rerun with a live pinned lease; `store.demote` seen proves the lease path; toRender parity metric), `queryresults-transform-groupby-100k` (probe → transform.evaluate metric; §8.6 ≥200k rows/s target checked against baselines before hardening).

### Deviations / residuals

- `pin-multiset-100` (§5.7 shape) and `sample-100-from-spilled` deferred: multi-set pinning needs per-set pin drivability from the harness (webview button only today) — next scenario round, after baseline runs of the three above.
- Baseline runs NOT executed this round (need the harness + SQL container session); scenarios build clean and are registered. First runs happen alongside Karl's dogfood.
- Debug-Console queryResults page: still possible-not-built (all data behind `showStatus`/one service call), per §7 posture.
- C2D-9 unchanged (arrow export C2D-D-04, headless-run P1).

### Verification

vscode-mssql: build:extension + webviews typecheck + bundle + lint clean; full suite 4435 passing / 3 known pre-existing. perftest: workspace build clean, tests pass except the central-store integration suite (needs the live SQL container at localhost:14333 — environmental, pre-existing). Contracts 27/27, conformance green.

## 2026-07-10 — Entry 8: dogfood fixes (Karl round 1)

SHIPPED — vscode-mssql qs: 85710f0a7 + c2d: 5f15664ea:
1. Grid header labels non-selectable (FluentResultGrid.css user-select:
   none — all fluent-result-grid surfaces).
2. Pinned results converted CustomReadonlyEditor → WebviewPanel: the
   virtual-file custom editor made VS Code render a breadcrumbs row that
   only repeated the tab title. FS provider + customEditors contribution
   + onCustomEditor activation DELETED; scheme URI survives as lease-
   owner/context identity; Perf marks + soft cap unchanged. BEHAVIOR
   CHANGE (recorded): pinned tabs close on window reload (previously
   restored as expired husks — data never survived reload anyway).
   Contract test now pins the contribution's ABSENCE.
3. Stale status-bar SPID after KILL: the per-run @@TRANCOUNT probe reads
   @@SPID in the same batch; a transparently re-established session
   updates the status bar on the next execution (SSMS behavior, zero
   extra round trips). DBA rationale: the shown SPID must be referable.

VERIFIED: tsgo (extension + webviews) clean; extension + webview bundles
rebuilt (dist refreshed — dogfood picks these up); eslint 0 errors; full
suite 4481/12/2 known pre-existing; queryResults+QS targeted 237 green.
