# Metadata cache/drift execution plan (CACHE-PRE … CACHE-7)

Plan of record: `metadata_design_review_pack/metadata_cache_drift_design.md`.
Normative overlay (WINS on conflict): `metadata_design_review_pack/METADATA_CACHE_DRIFT_REVIEW_ADDENDUM.md` (C-1..12, H-1..10, §4 decision procedure, §6 codec rules, §10 tests T-A1..18, §11 batch deltas).
As-built truth: `metadata-substrate-design.md`. Progress journal: `PROGRESS.md` (this folder).

| Batch | Content | Status |
|---|---|---|
| CACHE-PRE | C-1 ordinal comparator + golden regen + lint guard; C-11 _BIN/_BIN2 collation; H-1/H-5 digest v2 SQL + fixtures; T-A1..3 | **COMPLETE** — perftest d18f6b5; vscode-mssql 26ce65e73 (core: vendored contract), 55ea1adbd (qs:), c61e76f67 (ls:), b4a9861a0 (oe:), 0d59ecd9d (core: lint) |
| CACHE-0 | metadataFreshness.ts (C-3/6/8/9/12); ensureFresh on db+server leases (§4.2, memory/live); H-2 watchdog + session recycle + op-epoch guards; §4.3 coalescing; T-A4/5/6/13 | **COMPLETE** — b5a428f53 |
| CACHE-1 | JSON+gzip codec, manifest, contentHash (C-2, §6 rules), T-A7 | **COMPLETE** — 0420fd6ae |
| CACHE-2 | disk coordinator: atomic writes (H-4), eviction (H-10), policy intersection (C-5), recipes (C-10); T-A8/9/10/17 | **COMPLETE** — 0420fd6ae |
| CACHE-3 | store integration: disk load on acquire, C-4 background hydrate + baseline rule + backoff, C-7 db-side semantics, H-7 accounting; T-A11/12/18 (T-A14 waits on server-catalog disk cache) | **COMPLETE** — 59e78a296 |
| CACHE-4 | safe stale consumers: completions + AI resolver→SHARED-store migration (§7.6), commands/settings, H-9 deferred-until-measured | **COMPLETE** — 59e78a296 |
| CACHE-5 | validated consumers: diagnostics slice **COMPLETE** (204791cb3+51b6bffce); OE browse/H-3/H-5/H-6 slice in flight (agent) | in progress |
| CACHE-6 | strict consumers + offline mode: scripting provenance + banner, offline commands/status | in flight (agent) |
| CACHE-7 | T2/T3 section/object digests — DEFERRED until broad cache proves useful (base §23) | deferred |

## Decisions taken with Karl-review flags (addendum §12)
1. **Q1 goldens (C-1):** one-time ordering change taken in CACHE-PRE per "make all the core fixes now" — existing goldens did not actually move (fixture names carry no reordering shapes); new T-A1 pins the ordinal bytes. FLAGGED for confirmation.
2. **Q2 contentHash in telemetry:** conservative default — kept OUT of diag events (status()/feature-capture only); registry note records the pending decision. FLAGGED.
3. **Q3 server-catalog two-case rule (C-7):** will implement in CACHE-3 with the updated pin, journaled. FLAGGED.
4. **Q4 serverless polling:** 300 s starting interval per H-3.3 (not full suspension) — CACHE-5. FLAGGED.
5. **Q5 maxEntryBytes:** 32 MiB compressed default, re-pick after first large-fixture save measurement — CACHE-2/3. FLAGGED.
6. **Q6 OE first-expand UX:** block-with-loading per addendum §7.2 — CACHE-5. FLAGGED.

## Standing rules for every batch
Full verify chain per batch; standing QS gates (28 reps) must stay in-band — cache is additive, movement = regression; contracts registered before first emission; trains: `qs:` metadata/cache/consumers-in-qs, `ls:` sqlLanguage, `oe:` OE v2, `core:` contracts/lint.
