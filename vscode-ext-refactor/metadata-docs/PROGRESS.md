# Metadata cache/drift build journal

## 2026-07-06 — Entry 1: CACHE-PRE COMPLETE (core determinism fixes)

SHIPPED — perftest d18f6b5 (metadataCache. vocabulary registered with App C
allowlist; contentHash prefix excluded from events pending Q2); vscode-mssql
26ce65e73 (core: vendored contract), 55ea1adbd (qs: C-1 ordinal ordering in
catalogModel + AI payload, C-11 _BIN/_BIN2 collation fix, H-1/H-5 digest v2
with DB_NAME() identity rider, T-A1..3), c61e76f67 (ls: completion-label
ordinal tiebreak), b4a9861a0 (oe: fixture), 0d59ecd9d (core:
no-locale-compare lint rule).

FINDINGS beyond the addendum:
1. The AI payload module (copilot/catalogSchemaContextPayload.ts) had SIX
   case-folded localeCompare sorts on the replay-critical path — outside the
   addendum's lint scope; fixed + scoped into the rule.
2. The new lint rule immediately caught a fourth-file site the survey grep
   missed (sqlLanguage/features/completion.ts §10.5 tiebreak — commented
   "deterministic order", using ICU). Structural-duplicate ordinalCompare
   added to the pure core (purity boundary forbids the catalogModel import).
3. LATENT dead fixtures: metadataCatalog + metadataStore tests ordered the
   digest matcher AFTER H2, whose substring CHEAP_DIGEST contains — digest
   queries silently received H2 object rows since B5. Reordered + 3-column.
4. MD-4 goldens did NOT move under the comparator change (fixture names have
   no underscore/digit/non-ASCII ordering shapes) — the "one-time break"
   turned out to be a no-op for existing pins; T-A1 pins the new order.

Verified: tsgo/eslint/emit clean; full suite 4029 passing/12 pending/0
failing (second run; single fail in first run = known copilotChatEntry
flake); contracts vitest 27/27; rule proof by transient violation.

## 2026-07-06 — Entry 2: CACHE-0 COMPLETE (freshness policy API)

SHIPPED — vscode-mssql b5a428f53 (qs:) + 26ce65e73/d18f6b5 contracts (Entry 1).
metadataFreshness.ts (C-3/C-6/C-8/C-9/C-12 wording verbatim in headers);
ensureFresh on database handles + both lease scopes implementing §4.2
EXACTLY (memory TTL → coalesced T1 → chained refresh → C-7 rows → section
gate); H-2 lane watchdog (raced-lane continuation, opEpoch abandonment
guards, session recycle on next lane item, refresh() never rejects, module
reads map timeout→notLoaded); §4.3 coalescing via validationInFlight;
server catalog §4.4 (validation ≡ re-hydration + TTL). checkDigest is now
a wrapper over the shared validation (poll/EXEC semantics preserved —
T-A3 from Entry 1 still green).

Tests: 8/8 first run (T-A4/5/6/13 + C-7 row + offline no-network + section
gate + server §4.4). Suite 4037/12/known-flake (CopilotChatEntry named).
Build clean. Gates deferred to the CACHE-1/2 landing (agents are using the
machine's test lanes; official-metric wallclocks stay uncontended).

DELEGATED (in flight): CACHE-1+2 agent (codec/contentHash/manifest/disk
coordinator + T-A7/8/9/10/17); CACHE-5 diagnostics-slice agent
(metadataNotValidated/metadataStale suppression reasons + host-side
ensureFresh(diagnosticsBinder) gating).

## 2026-07-06 — Entry 3: CACHE-1 through CACHE-4 COMPLETE (+ CACHE-5 diagnostics slice)

SHIPPED — vscode-mssql 0420fd6ae (qs: CACHE-1/2 codec+contentHash+disk
coordinator, agent-built: frozen cm1 canonical tuple, adopt-verbatim
rehydration, §6.5 round-trip proof on CI+BIN2 fixtures, H-4 torn-write
matrix + EPERM retry + two-writer raceLost, C-5 intersection both
directions, C-10 recipes with NUL-separated salted databaseHash, 48
tests), 204791cb3 (ls: 18-reason ladder — metadataNotValidated/
metadataStale as DATA on DiagnosticsRequest, purity intact) + 51b6bffce
(qs: publisher gates T2 on ensureFresh(diagnosticsBinder) with host
backstop; 17 tests), 59e78a296 (qs: CACHE-3/4 — see commit message;
built by orchestrator).

KEY MOVES beyond the specs:
1. The classic AI resolver previously built a PRIVATE MetadataService —
   the substrate doc's "store-backed" claim was aspirational. Now true:
   classic editors share warm catalogs with QS, get the disk cache, the
   watchdog, and ensureFresh(aiContext) with the old 120s ceiling.
2. Guarded activation for storage-less mocked contexts after a real
   break: the configureCache joinPath crash silently killed
   ConnectionDialog's 58 tests — surfaced as a COUNT DROP (4108→4053),
   not a named failure. Lesson journaled: watch pass-counts, not just
   failure lines.
3. Manifest objectDigest recording is deliberately deferred until a
   validation-notify seam exists (engine-side C-4.2 compare is built +
   tested with hand-built manifests; production manifests carry no
   digest yet — the mandatory C-4.1 background refresh owns correctness).

Verified: suite 4111/12/0 FULLY GREEN; standing gates 28/28 at the
CACHE-1/2 point (run c8c1b8d0). Settings surface: the public four only,
enabled:false default. Karl flags live in EXECUTION_PLAN §Decisions.

REMAINING: CACHE-5 rest (OE browse block-with-loading, H-3 poll
governance, H-5 driftRename, H-6), CACHE-6 (scripting provenance +
offline UX), perf scenarios (§9), server-catalog disk cache (deferred
follow-up — C-7 two-case rule waits for that provenance).

## 2026-07-06 — Entry 4: CACHE-5 + CACHE-6 COMPLETE

SHIPPED — vscode-mssql 5bfae6d81 (qs: H-3 poll governance with focus
suspension/backoff/jitter/serverless-floor/semaphore + H-5 driftRename
identity episodes + H-6 permission/access drift routing; agent-built),
47bb5f0c8 (oe: browse requireValidated + block-with-loading §7.2/Q6 —
first-expand-validates, TTL reuse with zero SQL, status-child honesty on
timeout; agent-built), 3663ab056 (ls: CACHE-6 scripting provenance
data-in + engine-rendered offline banner with exact anchor shifting +
strict refusal flow + definition offline honesty; agent-built),
5da22c5e0 (qs: host wiring — focus fact, clearForConnection over disk
listEntries, pollSeconds setting).

DEVIATIONS RECORDED: serverless cap is a FLOOR (Q4 conservative side);
H-6(a) permission classification is a message heuristic (no error
numbers travel the H-pass catches); provenance NESTED on ScriptResult
(field-name collisions with existing members — §7.5 field set intact
inside); refresh() clears the identity latch by reopening BY NAME
(never auto-rekey); Script-As has no production caller yet — the
strict host seam + tests are the deliverable; OE offline status child
covered by the CACHE-5 staleness status child wording.

Verified: combined-tree full suite 4154/0 (agent run) + static chain
clean + build clean; gates 27/28 with one INVALID rep (query-10k rep 1
render-timeout during visible machine-wide slowness — neighboring OE
rep ran 6x its band, run 50% slower overall; reps 0/2/3 in-band
443/585/611ms) — rerun in flight to confirm; treated as environmental
pending that result.

REMAINING for wrap (#82): §9 perf markers + seam + warm-acquire
scenario; gates rerun confirmation; memory + final summary.

## 2026-07-06 — Entry 5: WRAP — perf probe live, all gates sealed. EFFORT COMPLETE.

SHIPPED — perftest a01dc2c (warmAcquire marker pair registered
contracts-first + metadatacache-warm-acquire scenario, exploratory);
vscode-mssql 4245c2407 (core: vendored contract) + 091b6712b (qs:
PERF_MODE probe — clear key → cold live acquire + deterministic saveNow
flush → SECOND fresh store MUST serve from disk, honesty-throwing).

HEADLINE NUMBER: the disk warm-acquire (load + publish + freshness
decision) measured **~9 ms** live against real STS2 + SQL Server
(metadata.cache.warmAcquire pair metric, run 4e7cf820 4/4) — versus a
full live hydration round-trip. The §7.6 promise held.

HARNESS LESSON (pinned in-registry): a scenario whose markers are its
proof must END on waitForMarker — afterLastAction closes the rep before
the perf sink flushes (first wiring failed 4/4 'marker not observed'
with the probe itself succeeding).

FINAL EVIDENCE: standing gates 32/32 (b0990fa9; the earlier single
'invalid' rep confirmed environmental — clean 28/28 rerun 7c2992f9);
closing full suite 4151 passing/known CopilotChatEntry flake only.

EFFORT CLOSED. Follow-ups on record: server-catalog disk cache (+ C-7
two-case rule), manifest digest recording (validation-notify seam),
Script-As production caller, §9 restart-flow scenarios, CACHE-7 T2/T3
digests (evidence-gated), central observability C0–C7 (deferred per
Karl). Karl review flags: EXECUTION_PLAN §Decisions Q1–Q6.
