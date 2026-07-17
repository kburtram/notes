# Inline Completions — WI-1.6 Parity Checklist (addendum §12 matrix)

**Generated:** 2026-07-16, branch `dev/query`, working tree on top of `9d24e0696`
(WI-1.4/1.5/1.6 changes, uncommitted at time of writing).
**Statuses:** `[automated-green]` — verified by tests run this session;
`[needs-manual-run]` — behavior is wired (direct component reuse + full command
surface) but requires the scripted manual/webview pass; `[n/a-until-phase-N]` —
the *unified-target* upgrade for that row lands in a later phase (current
behavior preserved).

**Automated evidence base (all green, this session):**
`npx vscode-test --grep "completions debug rpc|command handler|Feature capture|completions page|completions debug deep link"`
→ 55 passing; `npx vscode-test --grep "privacy canary|Privacy canary"` → 13
passing; extension + webview typechecks green; full webview bundle build green.

| # | Capability | Status | Evidence / why |
|---|---|---|---|
| 1 | Pending request row | [automated-green] | store pending semantics ("pending event finalizes in place") + thin-row projection tests green; pending rows ride `CompletionLiveRowV1` with lazy detail |
| 2 | Terminal in-place update | [automated-green] | same ring id survives finalization (featureCapture suite); live-rows cursor tests prove stable ids across pages |
| 3 | Acceptance update | [needs-manual-run] | store flip mechanics unit-green; no automated assertion yet that an accepted flip re-renders the console row (acceptedState is projected, rendering unverified) |
| 4 | Live auto-scroll and selection | [needs-manual-run] | EventGrid reused byte-for-byte (no fork); auto-scroll/pause + selection need the scripted webview pass in the console shell |
| 5 | Full prompt tabs (system/user) | [automated-green] | detail RPC fixture: prompt section carries exactly the prompt sentinels, absent unless requested; DetailPane fetches `prompt` lazily via the shared accessor |
| 6 | Raw / sanitized / final response | [automated-green] | detail RPC fixture: rawResponse + sanitizedResponse(+finalCompletionText) sections carry their sentinels only |
| 7 | Schema context | [automated-green] | detail RPC fixture: schemaContext section carries the schema sentinel; DetailPane schema tab fetches it lazily |
| 8 | Locals dump | [automated-green] | detail RPC fixture: locals section carries locals sentinel only. Classification/omission notes are Phase-2 (§5.2/§9.1) — current behavior preserved |
| 9 | Telemetry summary | [automated-green] | summary+telemetry detail slices proven content-free by sentinel canary |
| 10 | Copy actions | [needs-manual-run] | host-side `copyEventPayload` clipboard unit green (content never round-trips the webview); button/context-menu click-through needs the webview pass |
| 11 | Profile picker | [needs-manual-run] | Toolbar reused unchanged; `selectProfile` dispatch unit green; console rendering pass pending |
| 12 | Model + continuation model | [needs-manual-run] | Toolbar reused; model catalog rides the base-state pull; needs manual pass with a real model catalog |
| 13 | Schema budget overrides | [needs-manual-run] | `updateOverrides` shape-validation + materialize-to-custom units green; live effect needs manual run. Effective-config recording is Phase-3 (WI-3.1) |
| 14 | Other live overrides | [needs-manual-run] | same as 13; mutability labels are Phase-3 |
| 15 | Custom system prompt (edit/reset/save) | [needs-manual-run] | save/reset persistence units green (memento fakes); dialog round-trip in the console (dialogOpen rides host viewState) needs manual pass |
| 16 | Record when closed | [automated-green] | "shouldCapture honors viewer leases OR record-when-closed" + config write-through unit green |
| 17 | Manual save | [needs-manual-run] | `saveTraceNow` dispatches through the shared repository; no automated end-to-end file assertion in the console context |
| 18 | Save on deactivate | [needs-manual-run] | path untouched by this WI; needs the usual deactivate check |
| 19 | Redacted trace | [automated-green] | privacy-canary suite green ("completions trace redaction surface strips prompts, responses, schema text") |
| 20 | Max file size truncation | [automated-green] | "size cap drops oldest events first and flags truncation" (featureCapture suite) green |
| 21 | External trace folder (watch/scan) | [needs-manual-run] | repository add-file/load units green; folder watcher + rescan behavior in the console needs manual run |
| 22 | Add arbitrary trace file | [needs-manual-run] | workflow automated-green (loaded-trace repository test); *hardened/untrusted* import limits are Phase-2 (WI-2.8) |
| 23 | Change folder | [needs-manual-run] | `sessionsChangeFolder` dispatches to the shared service (host-side dialog); manual pass pending |
| 24 | Import/export dialog | [needs-manual-run] | commands dispatch host-side via injected host services; manual pass pending |
| 25 | Trace include toggles | [needs-manual-run] | `sessionsToggleTrace`/`sessionsSetAllTraces` validated + dispatched; SessionsTab reused unchanged |
| 26 | Multi-session load | [needs-manual-run] | `sessionsLoadIncluded` via shared repository; loaded traces ride the sessions slice AFTER user load (documented interim until Phase-2 host-side aggregation) |
| 27 | Facets | [needs-manual-run] | SessionsTab + analysis code reused verbatim (no fork); provenance/mode facet additions are Phase-4 |
| 28 | Pivot and secondary pivot | [needs-manual-run] | component reuse; no new unit added this WI |
| 29 | Summary metrics | [needs-manual-run] | reused as-is; corrected cohorts/denominators are Phase-4 (WI-4.1) |
| 30 | Latency histogram | [needs-manual-run] | reused as-is; webview pass pending |
| 31 | Drilldown | [needs-manual-run] | drilldown DetailPane consumes full local session events (no lazy dependency); webview pass pending |
| 32 | Send historical event to basket | [needs-manual-run] | SessionsTab passes full local events (allowed — user-loaded); command validated + cart mutation unit green for the handler |
| 33 | Replay one event | [needs-manual-run] | `replayEvent` (live, by id) and `replaySessionEvent` (full body) dispatch through the shared replay service; execution needs a model — manual |
| 34 | Replay session | [needs-manual-run] | `replaySessionNow`/`addSessionToReplayCart` resolve loaded traces host-side; manual run needed |
| 35 | Basket add/remove/reorder/reverse | [needs-manual-run] | host units green for add-by-liveEventId (new, resolves full body host-side), add-full-event, clear; reorder/reverse are dispatch-validated only; drawer UI pass pending |
| 36 | Snapshot mode | [needs-manual-run] | configMode enum validated end-to-end; behavior unchanged (shared service) |
| 37 | Override mode | [needs-manual-run] | same as 36 |
| 38 | Live mode | [needs-manual-run] | same label/behavior; freeze-at-run-start is Phase-3 (WI-3.1) |
| 39 | Queue | [needs-manual-run] | queue rows ride the replay slice (full snapshots, post-user-action); durable run artifact is Phase-3 (WI-3.3) |
| 40 | Matrix | [needs-manual-run] | `runReplayMatrix` validated + dispatched; run progress strip renders from replay slice via state refresh; generic axes/repetitions are Phase-3 |
| 41 | Matrix warning | [needs-manual-run] | current cell-threshold warning reused; calls/tokens/safety estimate is Phase-3 (WI-3.2) |
| 42 | Cancel | [needs-manual-run] | queued cancellation via `cancelReplayRun` (shared service, standalone panel closed); ACTIVE cancellation is Phase-3 (WI-3.2) |
| 43 | Replay tags (run/cell/source) | [needs-manual-run] | thin row carries replayRunId + matrix cell id (tag id, not the locals label — label hydrates with locals on selection); no explicit automated assertion |
| 44 | Replay result analysis | [needs-manual-run] | dimensions reused; paired analysis is Phase-4 (WI-4.2) |
| 45 | Gate-off page (metadata only) | [automated-green] | gate-off Plane-A view untouched this WI; privacy-canary suite green; gate-off RPC helpers still return honest empties at revision 0 |
| 46 | Multiple viewers | [automated-green] | "viewer leases are independent and idempotent in every disposal order" green; console + standalone hold separate named leases |
| 47 | Standalone command deep-links Debug Console | [automated-green] | `resolveCompletionsDebugLaunchTarget` unit-tested (flag off → console@completions regardless of gate; flag on → legacy panel, still gated); in-VS Code click-through belongs to the manual pass |
| 48 | Old v1 trace loads | [automated-green] | detail-lookup test writes a v1 trace file, indexes it via `addSessionTraceFile`, loads and resolves events by id |

## Transport/privacy invariants re-proven this session

- Live rows carry **no** prompt/response/schema/locals/error/URI content
  (sentinel canary + compile-time `CompletionLiveRowContentLeakGuard`, intact).
- The console's initial page payload now carries **no live event bodies**:
  `DcIcDebugStateRequest { omitEvents: true }` strips `events` (new unit:
  "omitEvents strips live event bodies and nothing else"); legacy callers get
  the unmodified state ("legacy callers … get the unmodified state").
- Cart adds from the console live grid send `{ liveEventId }` references; the
  shared command handler resolves full bodies from the ring host-side (units:
  resolve + honest drop of evicted references).
- ≤4 coalesced change notifications/sec (revision/throttle unit re-run green).

## Known intentional console-vs-panel differences (record for the manual pass)

1. **Info column previews hydrate lazily** — the newest 150 terminal rows fetch
   their sanitized-completion preview eagerly through the detail channel
   (cached once, content-free rows stay content-free); older rows show
   metadata until selected. The standalone panel has all previews immediately.
2. **Pending-row stage text** ("In flight: waiting for model response…") comes
   from a lazy locals fetch and may lag one refresh behind the panel.
3. **Trigger column before hydration** maps `invoke → explicit`;
   `explicitFromUser` is refined when the summary section hydrates (selection).
4. **documentUri** is not present in console live view models (source-path
   privacy); grids/details show the file name, which is what both hosts render.
5. **New in both hosts:** a compact truncation strip above the live grid when
   the ring has evicted events (`liveEvictedCount`, addendum §2.2 honesty).
6. The enablement card's "Open Inline Completion Debug viewer" button executes
   the (now flag-routed) command: with the flag off it re-reveals the console's
   Completions page; with the flag on it opens the legacy panel.

## Manual design pass (final plan §3 UX brief) — REQUIRED, not yet run

[needs-manual-run] Screenshot evidence per state (loading/empty/error/partial)
per theme (light/dark/high-contrast) for: Live grid + splitter + DetailPane,
Sessions facet-rail/pivot, ReplayTraceBuilder drawer, run-progress strip,
custom prompt dialog — judged against the standalone panel as the reference.
Also verify: no double scrollbars (page fills the console content area),
overflow scrolls inside panes, no layout shift while detail sections load,
first paint of the Completions page ≤ other console pages (app chunk is lazy).

## Bundle budget evidence (dev, unminified, esbuild `splitting: true`)

| Measure | Before (HEAD `9d24e0696`) | After (this WI) | Delta |
|---|---|---|---|
| debugConsole preload closure | 5,199.8 KiB (12 files) | 3,540.1 KiB (10 files) | **−1,659.7 KiB (−31.9%)** |
| completions app lazy chunk | — (forked subset was static) | 1,156.8 KiB (loads on gate-on Completions page) | deferred off first paint |
| inlineCompletionDebug (standalone) closure | 5,939.2 KiB | 5,943.5 KiB | +4.3 KiB (+0.07%) |
| all webview JS (clean build) | ≈24,003 KiB | 23,909 KiB | ≈−94 KiB |

The full shared app (Live+Sessions+Replay drawer) ships as ONE lazy chunk via
`React.lazy` in `completionsPage.tsx`; per-tab (Sessions/Replay) sub-chunks
were not split further because the shared `App` mounts both tabs (hidden
inactive) by design — documented here instead of inventing infrastructure.

## Rollback

`mssql.copilot.inlineCompletions.debug.standalonePanel` (default `false`).
`true` restores the legacy standalone panel behind the same command; the panel
runs on the identical shared services + shared components (no forks remain),
so the rollback path is exercised by the same unit surface.
