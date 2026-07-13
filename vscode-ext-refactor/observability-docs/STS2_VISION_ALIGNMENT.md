# Claude Code — STS2 vision alignment (substrate for the first-party viewer, harness, and replay)

> Paste below the line into Claude Code, running in `C:\repos\test\sqltoolsservice` (the STS2
> branch). This extends the **reviewed target design** and the **recalibrated plan** — it does not
> replace them. Read those first (they're in the review package you have:
> `00_EXECUTIVE_SUMMARY.md`, `01_TECHNICAL_REVIEW.md`, `03_TARGET_DESIGN.md`, and the tiered
> `REVIEW_ASSESSMENT_AND_PLAN.md`), plus the perftest docs and the Phase-4 in-product prompt so you
> understand what will consume STS2.

---

## Why this doc exists

STS2's reviewed target design is already, deliberately, "a database service whose externally
relevant decisions are deterministic, inspectable, privacy-safe, and recoverable." That is the
substrate for the whole vision: the perftest harness, the in-product **Session Diag** capture, the
**consolidated cross-process debug viewer**, and **replay**. The recalibrated assessment already
tiers the review and names the *viewer substrate* items. Your job here is to (A) land that
recalibrated plan as the correctness/substrate floor, and (B) add the small set of **additive
extensions** the vision needs that the target design doesn't yet cover — because they're new
product directions, not review findings.

**Preserve the target design's principles** (03 §2): one decider; journal-before-acted-upon; pure
authority + live overlays (`runtimeOnly`, excluded from replay identity); explicit ownership;
bounded by construction; privacy policy precedes capture mode; strict-verify ≠ time-travel. Every
extension below is consistent with these — nothing here is a domain decision in the reducer.

## Working discipline

Use `IMPLEMENTATION_PLAN.md` + `PROGRESS.md` in this repo as anchors (create them if absent).
**ADR-first for the one-way doors** (below) — draft the ADR with a recommendation before the code
it gates. Tests-first for correctness items. Never fake replay fidelity, classification, or gap
metadata to make something pass — an honest `Incomplete`/`Diverged`/`dropped-range` is the correct
output. Commit per task; keep `sts2/main` moving by *merging* `main` in, not rebasing (per the
assessment's R039 note).

---

## Part A — Land the recalibrated correctness/substrate floor (reference, don't re-derive)

Follow `REVIEW_ASSESSMENT_AND_PLAN.md`'s ordered plan. In priority:

1. **Tier-1 correctness sweep** (PR 1): R026, R011, R006, R010, R034, R020, R036, R040, R047, R030,
   R035, R016, R012 — each with a failing test first. These earn back "deterministic / bounded /
   terminal."
2. **Viewer substrate** (PR 2): R001 composite session completion → mux fatal containment; **R003
   observer mailboxes + `TryWrite` (never await observer code)** — this is the single most important
   item for the vision, because every consumer you attach (harness collector, Session Diag sink,
   live viewer) is an observer, and a blocking observer must never stall the pump; R007 one
   directory per run + run-keyed reader; R013/R014 runner ownership/disposal.
3. **Replay/durability truth** (PR 3): strict `verify` vs partial `until` (R006 deepened, target
   §14.1/§14.2); `query.complete`+lifecycle as durability checkpoints (R020); lifecycle pump barrier
   (R002).
4. **Privacy cheap wins** (PR 4): R032 opaque tokens, R004/R005 turn-scoped cleanup, R033 allowlist.
5. **ADRs before the code they gate:** dispose/I2 terminality (R008), **host capture policy**
   (R018/R031), durability classes, **observer data-access/isolation** (target §15.4/§16). The
   capture-policy and observer-data-access ADRs are the ones the vision most depends on — write them
   with the viewer + Session Diag use cases explicitly in scope (see Part B4).

This floor makes the target design's §16 observer framework and §15 capture model real. Build it
before the viewer hardens against it — but **prototype consumers against the live tail now** (Part
B3) to discover what the checkpoint/gap/correlation contract actually needs before R003/R007 freeze.

## Part B — Vision-alignment extensions (additive; consistent with target §2.3/§15/§16)

### B1 — Cross-tier correlation (enables the consolidated waterfall)

Target §7.3 correlates *inside* STS (corr = JSON-RPC id; cause chains; entityRefs). The vision needs
STS envelopes to join the **VS Code extension trace** and the **SQL command**, so one user action
renders as one waterfall across exthost → webview → STS → SQL Server.

- At the gateway, capture an **inbound external correlation** per request — the W3C `traceparent`
  (already flowed to STS as `PERF_TRACEPARENT`, currently unused) and/or a client-supplied
  correlation id — and stamp it onto the request-root envelope as a **`runtimeOnly` overlay field**
  (e.g. `externalTrace`), propagated as context down the cause chain. It is a live overlay, **not** a
  domain input, so it is excluded from replay identity (target §2.3) — additive, no reducer change.
- Propagate the same correlation into the **SQL path** so server-side XEvents join: set the
  connection **Application Name** (and/or `SESSION_CONTEXT`) to the correlation key. Coordinate with
  the harness, which already sets `Application Name = mssql-perf/<run>/<rep>/<scenario>` for exactly
  this — make STS the component that stamps it in product/Session-Diag mode too.
- Result: `externalTrace` (VS Code) ↔ `corr`/`cause`/`entityRefs` (STS) ↔ Application Name (SQL)
  gives real causal links, not time-alignment guesses.

### B2 — Publish the envelope/overlay/classification schema as a shared cross-repo contract

Three consumers parse envelopes (harness `stsEnvelopeJournal` normalizer, Session Diag store,
in-product viewer). Make the contract explicit and versioned (target §9 already specifies
`sts2.envelope/2`; the assessment defers *full external wire schemas* but this is the internal
envelope, which is cheap and high-leverage):

- Publish `sts2.envelope/2` + overlay fields + the **classification enum** (target §3.2) + the
  health/metric schemas (§16.3/§17.1) as versioned schema artifacts.
- Apply the perftest CONTRACTS pattern: consumers copy the schema verbatim, pin the version, and
  keep fixtures that must validate — a schema change that breaks a fixture fails the build.
- **Align the extension marker/event model and the Session Diag event model to the envelope shape**
  (kind/type/corr/cause/entityRefs/classification), so cross-tier correlation and the consolidated
  waterfall are native rather than adapter-glued. The STS2 envelope is the richest, most principled
  event shape in the system — make it the template the other tiers conform toward.

### B3 — One consumption API: the live-tail checkpoint protocol (target §16.2)

Make the harness collector, the Session Diag persistent sink, and the in-product live view consume
the **same** subscription surface:

- Expose per subscription: run id, first-available seq, last-delivered seq, **dropped count +
  dropped-from/dropped-through seq**, current journal checkpoint (target §16.2). On a gap, the
  consumer reads the exact range from the journal and resumes — no guesswork, no fabrication.
- This *is* the honesty contract the whole vision runs on: every consumer is told exactly what it
  missed. It maps directly to the harness rule "never fabricate; surface gaps."
- **Prototype all three consumers against the live tail now** (per the assessment) to learn what the
  checkpoint/gap/cause-tree contract needs before R003/R007 freeze it. Fold findings back into the
  observer-data-access ADR.

### B4 — Capture policy + classification as the Session-Diag privacy foundation (target §15/§3.2)

Session Diag = the user's real data. The target design already has the exact machinery; wire it to
the product:

- The **VS Code extension is the host** that supplies `CapturePolicy` (target §15.1). Product
  default is **digest/digest, no runtime elevation** — which is precisely the Phase-4 privacy
  requirement (opt-in, local, redacted).
- "**Enable Session Diag**" is a **user-authorized policy elevation**, applied at a journaled
  sequence boundary with auto-reversion (target §15.2) — never a silent client `setCapture`. A
  client cannot elevate beyond host policy (§2.6).
- Observers (including the viewer) register a **declared data view** (§15.4/§16): default
  redacted-authoritative; full wire view is governed and off by default; custom observers never
  auto-receive restored SQL/rows/secrets. Every field carries a classification (§3.2), so the
  Session Diag sink and the viewer redact per policy, mechanically.
- This makes Phase-4 privacy *mechanical, not conventional* — the reason to do the capture-policy +
  observer-data-access ADRs with the viewer/Session-Diag use cases explicitly named.

### B5 — Parameterized replay-drive + provenance (distinct from deterministic verify)

The vision's in-product replay + config-matrix (the completions pattern, generalized) is **not**
`sts2-replay verify` (pure, no DB, target §14). It is re-submitting a recorded run's client inputs
to a **live** STS2 with optional overrides, producing a new run. Keep them clearly separate:

- Add a **replay-drive** capability: take a recorded run's external inputs, optionally transform them
  (capture mode, feature/config params, connection target), re-submit to a live STS2, and journal a
  **new** run tagged with **replay-provenance** (source runId, matrix cell, overrides) in
  `session.start`. Honor overridden config deterministically; classify the new capture per policy.
- This respects the target's non-goal (no database-effect replay, §1.2): replay-drive re-executes
  against a live DB by design; `verify` remains the pure authoritative-output gate. Do not conflate
  the two result types.
- Feature-by-feature: STS-backed query/connection where the operation is deterministic and safely
  re-drivable; be honest where it isn't yet.

### B6 — Export bundle as agent + bug-report evidence (target §18)

The coherent, export-check-validated bundle (manifest/privacy-report/provenance/journals/schemas/
status) is already designed. Point the three evidence consumers at it: the harness reports, the
**AI-coding-agent** evidence path (structured runtime evidence for coding loops — the completions
PDF's agentic-traces scenario), and the in-product "export session for bug report." Additive; just
ensure the bundle carries the `externalTrace`/classification so downstream tools can correlate and
redact.

## Sequencing — which extension gates which Phase-4 stage

Layer these on the assessment's PRs:

- **Consolidated waterfall (Phase-4 4b)** ← B1 (correlation) + B2 (shared schema) + B3 (live-tail) +
  observer isolation (R003).
- **Session Diag capture (4a)** ← B4 (capture policy/classification) + observer isolation (R003) +
  run isolation (R007).
- **In-product replay (4c)** ← B5 (replay-drive/provenance) + strict-vs-partial replay (R006) +
  capture policy (R018).
- **Agent / bug-report evidence** ← B6 (export) + export coherence (R017).

## Decisions to surface (reinforce the assessment's two)

The assessment already asks the owner for (1) the target bar and (2) the dispose/I2 + capture-policy
ADRs. The vision *raises the stakes* on the **capture-policy** and **observer-data-access** ADRs
specifically, because Session Diag is real user data and the viewer/harness/agent are real observer
consumers. Draft both ADRs with those consumers named, recommend product-default deny-sensitive +
redacted-authoritative observer views, and get sign-off before coding B4.

Start: read the review package + assessment + target design + the perftest docs + Phase-4 prompt;
write/append `IMPLEMENTATION_PLAN.md` + `PROGRESS.md`; land Part A's PR 1–2 floor; draft the
capture-policy + observer ADRs; then build B1/B2/B3 as the consolidated-waterfall substrate while
prototyping the live-tail consumers.
