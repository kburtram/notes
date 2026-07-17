# Inline Completions Observability Unification — Final Execution Plan

**Updated: 2026-07-16.** This is the **authoritative, merged execution plan**, reconciling:

- `inline_comp_observability.md` (the companion plan: current-state survey, comparison,
  original phased proposal — still the primary survey document), and
- `inline_comp_observability_addendum.md` (the approved review: architectural amendments
  A–H, refined contracts, safety/analysis corrections, revised sequence).

**Precedence:** this document > addendum > companion plan. Where this document is silent,
the addendum's text (contracts in its §3–§9 and Appendices A–E, tests in §13, budgets in
§14, parity matrix in §12) applies verbatim. The companion plan remains the survey and
rationale. The branch is the final source of truth; Gate A records the heads.

**Scope of "done" for this effort:** Phases 0–1 are the committed minimum (full inline
UX in the Debug Console, de-forked, on typed thin RPC). Phases 2–4 are the target
(journal + bundle, Replay Lab v2, analysis corrections). Phase 5 + horizon are seams.

---

## 1. What the merge decided (delta log)

The addendum was accepted essentially in full. Decisions where this plan picks a side or
tightens the merge:

1. **Adopt all ten addendum corrections** (§0.1) — bundle catalog over shared manifest;
   typed durable identity before persistence; capture policy split into
   arming/fidelity/persistence/export/upload/trust; typed lifecycle records; de-fork via
   domain services + thin paged RPC; durable replay-run artifacts; QS replay treated as
   potentially mutating; cohort-separated analysis; untrusted imports; STS2 stays
   authoritative.
2. **Companion-plan items that survive unchanged:** the two-plane privacy doctrine, the
   three-replay-semantics taxonomy and the Replay-Lab-vs-perftest settings boundary,
   per-feature analysis specialization, Perf Test History separation, the
   "don't lose anything" checklist (now superseded in detail by the addendum §12 parity
   matrix, which is the release gate).
3. **Sequence = addendum §11** (Gate A → Phases 0–5 → horizon), with the companion
   plan's deep-link work folded into WI-1.6 and its `analysisKit` extraction deferred to
   WI-4.3 ("after a second real provider").
4. **All addendum §16 recommendations are frozen as-is**, notably: schema IDs
   (`mssql.observability.bundle/1`, `mssql.featureCapture.stream/1`,
   `mssql.featureCapture.record/1`, `mssql.featureTrace/2`, `mssql.replay.run/1`,
   `mssql.configGroup/1`, `mssql.observabilityLink/1`, `mssql.richCapturePolicy/1`);
   durable IDs via `crypto.randomUUID()` with timestamps as separate sort fields;
   session terminology (host/capture/replay/perf/STS2); capture defaults unchanged
   during migration + a developer "Observability Lab" preset; journal becomes source of
   truth only after shadow reconciliation; legacy trace files stay a first-class
   import/export library; `mssql.openInlineCompletionDebug` becomes a permanent alias
   into the Debug Console; standalone implementation deletion is evidence-gated;
   live replay config frozen at run start; completion replay fallback is explicit
   policy; QS replay starts parse-only/estimated-plan with exact target binding;
   interactive replay is never official; STS2 never converted; analysis extraction
   waits for a second tenant; no local encryption requirement now.
5. **New in this plan:** §3, the **Debug Console UX quality brief** — the merge must
   land looking like a designed product surface, not a transplanted panel. This is a
   first-class acceptance dimension for WI-1.4/1.5/3.5, with concrete rules drawn from
   the console's existing design system.
6. **Naming:** the UI keeps the user-facing term **"Replay cart"** (existing shipped
   copy) even where the addendum says "basket"; contracts use neutral names
   (`sources[]`, `sourceBasketDigest` stays as specced to match Appendix A–E).

## 2. Non-negotiables carried forward

The addendum §2 invariants apply to every work item verbatim (privacy/payload, honesty,
product isolation, compatibility). Three are repeated here because they shape daily
implementation decisions:

- Prompt/response/SQL/row/schema-context text **never** rides `DiagEvent`; Plane-A may
  carry IDs pointing at rich artifacts, never content.
- The webview transport never ships full rich state wholesale: thin rows, cursors,
  section-lazy detail, revision-stamped notifications (addendum §6.2–§6.3).
- Nothing on the §12 parity matrix regresses; the matrix is a release gate, not
  documentation.

---

## 3. Debug Console UX quality brief (REVISED 2026-07-16 per review feedback)

**Design North Star: the Inline Completion Debug design language, not the console's
dashboard idiom.** The owner's direction: the Inline Debug UX is the better model for
these tools — its event-streaming table beats the Consolidated Trace grid, its tightly
packed controls with resize splitters and collapsible panels beat the dashboard-style
pages, and its buttons/layouts/scrolling are generally better. These surfaces should
feel like **advanced development troubleshooting tools (Wireshark), not BI dashboards
(Power BI)**. Long-run the rest of the console may converge *toward* this language —
that is explicitly out of scope here; do not move the other direction.

Operationally, for the Completions page, Replay Lab, and any surface built in this
effort:

**Keep (and polish) the Inline Debug idiom**
- The Inline Debug components move into the console **as they are designed**: the
  dense EventGrid streaming table, the packed one-row toolbar with compact controls,
  the resizable splitter between grid and DetailPane, collapsible panels, the
  ReplayTraceBuilder drawer, the Sessions facet-rail/pivot layout. Do not restyle them
  into the console's KPI-tile/dashboard patterns.
- Density is a feature: small paddings, information-dense rows, monospace where ids/
  code appear, maximal use of vertical space for the event stream. No decorative
  chrome, no oversized cards.
- Polish means: consistent spacing rhythm within the Inline Debug system itself, crisp
  splitter/drag behavior, stable scroll positions (auto-scroll with pause-on-hover
  semantics preserved), no layout shift when detail sections load, clean overflow
  behavior on narrow widths (scroll inside panes, never page-level horizontal scroll).

**Fit into the console shell without dashboard-izing the content**
- The console shell (left-rail navigation, top bar, page routing) hosts the page; the
  page *content* is the Inline Debug system. The seam is the page boundary — inside it,
  Inline Debug rules.
- Shell-level fit only: the page fills the content area (no double scrollbars), uses
  VS Code theme tokens (light/dark/high-contrast all checked), respects the console's
  routing/deep-link mechanics, and its nav entry/badges match the rail's conventions.
  The Completions page keeps its `✦` identity.

**State & feedback (tool-grade, not dashboard-grade)**
- Every async surface has four designed states: loading (skeleton rows in the grid, not
  spinners in empty space), empty (one-line explanation + primary action), error
  (honest message + retry), partial (inline gap/truncation notices in the stream).
- Capture status is a compact, always-visible indicator in the Inline Debug toolbar
  (armed / recording / viewer-only / off + the sensitive-capture badge required by
  addendum §9.4) — informative and small, not a dashboard chip row.
- Replay runs show progress in-place (run row with n/m cells + cancel); long runs also
  surface in the VS Code status bar (self-test precedent, priority −1000).

**Interaction**
- Keyboard: arrow-key row navigation in grids, Enter opens detail, Esc closes drawers;
  the replay drawer traps focus; all actions reachable without a mouse.
- Deep links: every entity (capture session, event, replay run, matrix cell) has a
  stable route so Session History chips, analysis drilldowns, and replay results
  cross-navigate with one click.
- Copy actions are explicit buttons with success feedback, never auto-copy.

**Performance as UX**
- First paint of the Completions page ≤ the console's other pages (no synchronous
  hydration of event bodies); Sessions and Replay chunks lazy-load; 100k-row datasets
  scroll smoothly in virtualized views (addendum §14 budgets).

Acceptance for every UX work item includes a **manual design pass** against this brief,
recorded in the parity/evidence artifact (screenshots per state, per theme). The parity
matrix rows about look/feel are judged against the *standalone panel* as the reference:
if the console-hosted version feels worse than the panel did, it fails.

---

## 4. Execution sequence (merged)

The authoritative work-item detail (files, acceptance) is addendum §11 + Appendix E;
this section is the operating summary with merge notes. IDs match the addendum.

### Gate A — decisions and baseline
- **WI-A.1** record branch heads (all three repos), run the standard verification chain,
  capture UX evidence of the standalone panel + console page, save representative v1
  trace fixtures (redacted, truncated, replay-matrix, legacy-profile).
- **WI-A.2/A.3/A.4** identity/terminology, artifact-ownership, capture+replay policy
  ADRs — satisfied by §1.4 of this plan (frozen); record any deviation discovered
  during implementation back into this doc.

### Phase 0 — identity, compatibility, leases (contract-only; no storage change)
- **WI-0.1** durable identity: `featureCapture/identity.ts`; globally unique
  `captureSessionId`/`captureEventId` (UUID); preallocation + eviction-safe logical
  identity in `FeatureCaptureStore`; legacy display ordinals retained for UI.
- **WI-0.2** `ObservabilityLinkV1` on rich events; reverse IDs
  (`captureFeatureId/captureSessionId/captureEventId`, replay run/item/cell) on Plane-A
  completions + QS events; register attrs in the contracts registry → regenerate →
  re-vendor.
- **WI-0.3** completion provider emission ordering: allocate the ID before the pending
  record and thread it to the terminal Plane-A result (all result paths covered:
  success/skip/noModel/noPermission/error/cancelled).
- **WI-0.4** viewer leases (`acquireViewer(owner)` → `FeatureCaptureLease`), replacing
  `setPanelOpen`; health reports active leases; `recordWhenClosed` unchanged.
- **WI-0.5** strict `mssql.featureTrace/2` envelope + parser (separate event/overrides
  schema IDs, caps, unknown-major rejection); v1 fixtures keep loading.

### Phase 1 — full Debug Console parity on current stores (the committed minimum)
- **WI-1.1** de-fork into domain services (addendum §6.1): `InlineCompletionCaptureService`,
  `InlineCompletionTraceRepository`, `InlineCompletionReplayService`,
  `InlineCompletionDebugStateProjector`, `InlineCompletionDebugCommandHandler`; the
  standalone controller and the console host become thin adapters; delete every forked
  body.
- **WI-1.2** typed, versioned RPC: discriminated command union, protocol capabilities,
  state revisions, operation IDs, progress + cancellation, bounded errors. Replaces the
  full-state pull.
- **WI-1.3** thin rows + lazy detail: `CompletionLiveRowV1`, section-lazy
  `DcCompletionEventDetailRequest`; no prompt/response bodies in pushes or initial page.
- **WI-1.4** mount full Live + Sessions in the Completions page via **direct component
  reuse** (no copies), lazy chunks; §3 UX brief applies.
- **WI-1.5** mount full replay (cart/queue/matrix/config modes/cancel/progress) from the
  console with the standalone panel closed, on the current replay service.
- **WI-1.6** deep-link + parity gate: `mssql.openInlineCompletionDebug` routes to the
  console behind a feature flag (rollback available); §12 parity matrix green;
  bundle/first-paint budgets met; then (later, evidence-gated) standalone deletion.

### Phase 2 — rich journal + session bundle (the ideal outcome)
- **WI-2.1** journal + child-manifest schemas (`stream/1`, `record/1`, lifecycle reducer
  with revision/immutability validation and v1-compatible projection).
- **WI-2.2** bounded non-blocking journal writer (batched appends, segment roll by
  count+bytes, atomic child manifests, closed-segment digests, flush barriers, honest
  durability labels per addendum §3.7, health, fault isolation).
- **WI-2.3** `ObservabilityBundleManager`: lazy `bundle.json` (Appendix A), serialized
  atomic updates, startup reconciliation/repair, retention across child artifacts,
  clear-sensitive-captures.
- **WI-2.4** completion lifecycle records wired (created/finalized/acceptance/annotation;
  acceptance survives restart and ring eviction; no redaction resurrection).
- **WI-2.5** repository + indexed queries (manifest-only session index, paged rows,
  detail by ID, replay-capability flags, legacy external-trace provider).
- **WI-2.6** shadow dual-write + reconciliation report (blocks cutover on any mismatch).
- **WI-2.7** source-of-truth cutover (journal-backed history + v2 export; legacy files
  remain importable; no implicit deletion).
- **WI-2.8** import/export/retention hardening (adversarial corpus, content-redacted
  policy, default export excludes rich, canaries).

### Phase 3 — Replay Lab v2
- **WI-3.1** `ConfigGroupV1` + resolved-config digests + setting mutability.
- **WI-3.2** replay engine v2 context (IDs injected, cancellation token, preflight,
  estimate, safety assessment, durable-state callback; sequential kernel preserved).
- **WI-3.3** durable replay-run repository under the bundle (`mssql.replay.run/1`).
- **WI-3.4** explicit completion replay modes (frozenPrompt / rebuildCapturedContext /
  rebuildCurrentSchema / liveDocumentScenario; no implicit fallback; provenance per
  Appendix D; cancellation reaches the model request).
- **WI-3.5** Replay Lab page replaces the placeholder for completions (shared cart /
  config-group / matrix / run chrome; §3 UX brief; semantics + safety badges).
- **WI-3.6** Query Studio safe adapter (parse-only + estimated-plan; exact target
  binding; no first-document fallback; mutating modes stay gated behind **WI-3.7**).

### Phase 4 — analysis convergence
- **WI-4.1** provenance cohorts + corrected denominators (addendum §8.2 metric table).
- **WI-4.2** paired matrix analysis (per-source pairing, deltas, missingness,
  exploratory labels).
- **WI-4.3** extract shared analysis primitives only once a second provider needs them.
- **WI-4.4** Session History artifact chips (`Diag n`, `Completions n`, `QS runs n`,
  `Replay runs n`, `STS2 linked`) with deep links and honest absent/refused states.

### Phase 5 + horizon — controlled experiments, STS2, central
- **WI-5.1–5.5** `ExperimentDefinitionV1` in perf-contracts; mutability-aware scenario
  generation; deterministic (fake/recorded model) completions pipeline scenario;
  separate live-model exploratory scenario; central preview refuses rich artifacts from
  manifest classification.
- **Horizon**: STS2 verification adapter (authoritative formats, gated on its
  milestone); curated central trace policy (explicit versioned policy only).

---

## 5. Delivery slices & verification

PR-sized slices = addendum Appendix E (19 slices), each independently buildable and
rollback-capable. Per-slice verification = addendum §13.7 chain (typecheck → build →
focused tests → suite → smoke → parity script where UI changed → privacy canaries when
any serializer/export path changed). The §12 parity matrix runs at WI-1.6 and re-runs
after Phase 2 cutover and after Replay Lab lands.

Performance budgets: addendum §14 (notably: no file I/O on the capture hot path, ≤4
coalesced rich notifications/sec/page, initial page payload without bodies, 100–200-row
live pages, manifest-only session indexing, lazy webview chunks).

Risk register: addendum §15. Rejected alternatives: addendum §17 (binding).

## 6. Status ledger

Keep this table current as slices land (branch heads recorded at Gate A).

| Stage | Status |
|---|---|
| Gate A baseline | **done 2026-07-16** — heads: vscode-mssql `f37efaf2b2fa`, sqltoolsservice `b2660f2eb35c`, perftest `8cc093b9a682` (all `dev/query`, clean); extension + webview typechecks green; unit suite = vscode-test (`out/test/unit`), featureCapture + privacy-canary suites present |
| Phase 0 (identity/leases/envelope) | **done 2026-07-16** — identity.ts + ObservabilityLinkV1 + link-preserving eviction; reverse-link IDs on `completions.result`/`completions.request`-end/`queryStudio.runRecord.captured` (registered, regenerated, re-vendored); viewer leases across all 3 surfaces; strict v1/v2 envelope parser + v2 serializer + untrusted-import limits. 25 focused vscode-test units + 27 contracts tests green; both typechecks green |
| Phase 1 (console parity) | **code-complete 2026-07-16** — WI-1.1 de-fork (`657a3b9b4`), WI-1.2/1.3 typed RPC + thin rows (`9d24e0696`), WI-1.4/1.5/1.6 full console mount + deep link + rollback flag (`4e4bf7e6d`); 60 focused tests green, console preload −31.9%. **Open gate:** the manual parity pass — `inline_comp_parity_checklist.md` has 13 automated-green, 35 needs-manual-run rows (incl. the §3 UX design pass vs the standalone panel). Standalone panel deletion stays evidence-gated behind `mssql.copilot.inlineCompletions.debug.standalonePanel` |
| Phase 2 (journal/bundle) | **code-complete 2026-07-16** — WI-2.1/2.2 journal module (`4c91baff3`), WI-2.3 bundle catalog (`6e82e1837`), WI-2.4/2.5/2.6 dual-write + reconciliation + stored-session datasets (`997d0c291`), WI-2.7/2.8 flag-gated cutover mechanics + hardening (`07cfa3f17`); 179 focused tests green. **Open gates:** (a) enable the dark journal in dogfood (`trace.captureEnabled`) and run `mssql.copilot.completions.journal.reconcile` over a representative window — clean reports unlock (b) flipping `mssql.copilot.inlineCompletions.trace.journalPrimary`; M5 dual-write removal follows a stabilization window |
| Phase 3 (Replay Lab v2) | **code-complete 2026-07-16** — WI-3.1/3.2/3.3 config groups + engine v2 + durable runs (`771eafa19`), WI-3.4/3.5 explicit replay modes + Replay Lab page (`78c5f1c1b`), WI-3.6/3.7 QS safe adapter + closed mutating gate + config-group disk sanitization (`9ef018be9`). 313 focused tests green. Mutating QS replay stays code-gated pending product/security review (`QS_MUTATING_REPLAY_GATE`) |
| Phase 4 (analysis) | **code-complete 2026-07-16** (`c0beccade`) — provenance cohorts + §8.2 corrected metrics (Live default view, replay excluded by construction), paired matrix analysis in the Replay Lab (thin `dc/replayRunAnalysis`, n=1/missingness honesty), Session History artifact chips with deep links; extraction restraint recorded (no analysisKit — no second feature provider yet). 35 new tests |
| Phase 5 / horizon | pending by design — `ExperimentDefinitionV1` in perf-contracts, deterministic + live-model completions harness scenarios, STS2 verification adapter (gated on its M7 milestone), central curated-trace policy. No horizon item blocks local convergence |

## 7. Human gates open at code-complete (2026-07-16)

1. **Phase 1 manual parity pass** — `inline_comp_parity_checklist.md`: 35 needs-manual-run rows incl. the §3 UX design pass (reference = the standalone panel). Standalone panel deletion stays behind `mssql.copilot.inlineCompletions.debug.standalonePanel` until green.
2. **Journal cutover** — enable `mssql.copilot.inlineCompletions.trace.captureEnabled` in dogfood; run `mssql.copilot.completions.journal.reconcile` over a representative window; clean reports unlock `mssql.copilot.inlineCompletions.trace.journalPrimary`; M5 dual-write removal after a stabilization window.
3. **QS mutating replay** — `QS_MUTATING_REPLAY_GATE` stays false pending product/security review (target-group curation rides that review).
