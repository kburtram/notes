# R03 Brief — Vector Workbench Addenda (deltas that WIN over the base spec/plan)

**Sources (read completely):**
- `C:/repos/test/coding-docs/query-result-tabs/vector_design_addendum.md` (2026-07-10; design review of impl plan + UX spec + v1 mockup) — cited below as **DA:line**
- `C:/repos/test/coding-docs/query-result-tabs/vector_workbench_readiness_review_addendum.md` (2026-07-11; final pre-implementation readiness review of v2 mockups) — cited below as **RR:line**

**Project rule: addenda win over base docs.** Within the addenda, RR (2026-07-11) is later than DA (2026-07-10).

---

## 1. Precedence model (RR:26–36)

RR overrides a prior document **only** where it explicitly states `Required correction`, `P0`, `P1`, `P2`, `Do not`, or `Readiness gate`. Otherwise:
2. DA remains the code/platform architecture review.
3. `ux_revisions.md` remains the visual-language contract.
4. The implementation plan remains the repo/PR execution plan.
5. The UX spec remains normative for states/behavior/accessibility/interaction where no later doc changes it.

## 2. Verdicts

- **DA (DA:17–25):** Impl plan — *approve with amendments* (branch inventory accurate; architecture right; A1 is the one genuine semantic gap). UX spec — *approve with amendments* (visual-idiom under-specification). v1 mockup — *right materials, wrong composition* (PowerBI feel is compositional, not chromatic); IA (six workspaces, header selectors, capability popover, confirmation dialog) must survive into v2.
- **RR (RR:51–68):** "The architecture is ready. The revised visual system is ready. The feature is **not yet ready for a single unsupervised end-to-end generation pass**." Ready for staged implementation only after P0-1..P0-10 are folded into the normative specs and mockup annotations. Remaining blockers are semantic (labels mixing sources, non-fact claims, an internally contradictory Index mock, ambiguous counts, undisclosed self-match/read-consistency, wrong external-model naming, misleading global network claim).

## 3. Do-not-change foundations (RR:71–85; DA:131–132)

Do not churn: Vector sibling tab placement; the six workspaces **Profile, Search, Compare, Projection, Index, Pipeline**; the evidence taxonomy; exact search as the recall denominator; forced ANN as stronger evidence than approximate syntax alone; detached result mode vs explicitly table-bound mode; isolated diagnostic sessions; generated T-SQL visible and **never silently executed** for DDL/config; host-authoritative budgets and opaque result-store sessions; local PCA as the first projection; the external model-call confirmation dialog; the revised VS Code-native density/vocabulary.

DA A10 endorsements, recorded so nobody relitigates (DA:131–132): uniform-window sampling over silent reservoir sampling; covariance-free subspace iteration with deterministic sign normalization (explicit d×d covariance ≈16 MB at 1,998 dims — banned per plan §37.2); wire tag uses **`data` not `v`**; no new chart/math dependency in MVP (Recharts + small audited numeric module; revisit only via plan §13.4 spike gates); isolated auxiliary session with isolation disclosure (incl. pre-run disclosure of an open user transaction, UX spec §12.5).

## 4. Verified branch facts (ledger — DA §2; commits `vscode-mssql@205bbb98f4e21d551fbb4d9724301ca77cce7bd0`, `sqltoolsservice@d9aca04ec8293e36e19861f781ac609dde4f0fe2`, both `dev/query`)

sqltoolsservice (DA:41–48):
- `Packages.props` pins `Microsoft.Data.SqlClient` **6.1.5** (line 86 of that file).
- `SqlClientSession.PumpResultSetAsync` uses `CommandBehavior.SequentialAccess` (QO-4 comments); generic `_ => reader.GetValue(i)` arm.
- `WireValueEncoder.Encode`: unknown objects → `Wrapper("provider", Convert.ToString(cell, CultureInfo.InvariantCulture) ?? string.Empty)`. **A native `SqlVector<float>` today lands in the `provider` wrapper — lossy and text-inflated** (DA:45).
- **P0 privacy blocker is real (DA:46):** `CaptureElision.ElideInput` wraps only top-level `"rows"` (`obj["rows"]`), no `compact` handling — compact `values`/`nullBitmap` can reach journals today.
- `Sts2Defaults`: `PageRows = 1000`, `MaxFrameBytes = 67108864` (64 MiB). 256 KiB page target / 1 MiB cell bound not line-verified.
- `SqlRowsPageBuilder` exists at stated path; estimator behavior not re-verified.

vscode-mssql (DA:50–62):
- `services/sqlDataPlane/api.ts`: `ColumnMetadata` has `isXml`/`isJson`, precision/scale/maxLength; `CellValue` union = null/string/number/boolean/datetime/binary/xml|json/unsupported — **no vector kind**.
- Tagged-cell precedent: `TruncatedCellEncoding { $t: "truncated"; …; v: string }` — concrete proof the vector tag must use **`data`, not `v`** (one structural typo away from the truncated-cell display path). Non-negotiable (DA:55).
- `IQueryResultStore`: `retain(owner) → QueryResultStoreLease`, `getWindow`, `streamRows`, `summary`, `stats`, `demote`; store kinds `rowStoreV1 | resultStoreV2 | sts2 | remote`.
- Only contiguous column projection exists: `CellWindowRequest` has `columnStart?/columnCount?` ("QO-7b"); `RowStreamRequest` has none. **Sparse projection (plan §10) is genuinely new work; PR 5 correctly scoped** (DA:57).
- `RowReadReason = grid | copy | export | text | cellDocument | diagnostic | sample | profile | transform | aiTool` — no vector reason; `QueryResultLeaseOwnerKind = liveRun | pinnedDocument | aiTool | chatParticipant | export | command | debug` — no `vectorWorkbench` (DA:58).
- `webviewBaseController.ts` shared HTML has **no CSP** — P0 CSP prerequisite stands (DA:59).
- `documentSessionBinding.ts` exposes only the user session; metadata catalog lease via `MetadataStoreService` with `commandKind: "metadata"`, `metadataSession: false`; **no `acquireAuxiliarySession` seam exists** (DA:60).
- Deps already present: `recharts ^3.8.1`, `@fluentui/react-components ^9.72.3`, `@tanstack/react-virtual`, SlickGrid (ADS fork) + `slickgrid-react` — no new chart dependency (DA:61).
- `app.tsx` (~2,056 lines) owns tab state, `resultsPaneMaximized`, `maximizedGridId`, sizing-v2 fill mode; `queryStudio.css` implements the shell (DA:62).

House style, quoted from `webviews/pages/QueryStudio/queryStudio.css` (DA:66–72): "Query Studio — M0 shell densities (doc 01 §3/§7): toolbar 35px, status 24px, 2px radii max, VS Code tokens only, no ornamental chrome." Measured: results tab strip 30 px, 24 px text-only tabs (active = 2 px bottom border `--vscode-focusBorder`), 4 px splitters (hover = focusBorder), 26 px toolbar buttons radius 2, 24 px status bar segmented, fill-mode "issue A" — the grid's virtualized scrollbar is THE scrollbar (`qs-results-body-fill`). Grid = FluentResultGrid over SlickGrid.

## 5. External SQL surface, July 2026 (DA §3 — plan absorbs all via `VectorDatabaseCapabilities` probe; no structural change)

- **GA/preview split (DA:82):** SQL Server 2025 GA 2025-11-18 (CU1 2026-01-15). GA everywhere: `vector` type (float32), `VECTOR_DISTANCE`, `VECTORPROPERTY`. Preview on box behind `PREVIEW_FEATURES = ON`: float16 base type, `VECTOR_SEARCH`, `CREATE VECTOR INDEX`, `AI_GENERATE_EMBEDDINGS`. Matches plan's `previewFeaturesEnabled` probe.
- **Latest DiskANN format (2026-03-18, Azure SQL DB + Fabric SQL, regional rollout) (DA:83):** full DML (no read-only tables, no `ALLOW_STALE_VECTOR_INDEX`), iterative filtering (WHERE during graph traversal), optimizer-driven ANN-vs-kNN, transparent quantization. Box SQL 2025 retains earlier semantics. Plan's `vectorSearch: unavailable | legacy | latest | mixed` anticipated this. **Gap = A1** (legacy filtered comparisons).
- **Latest syntax (DA:84):** `SELECT TOP (N) WITH APPROXIMATE … FROM VECTOR_SEARCH(TABLE=…, COLUMN=…, SIMILAR_TO=…, METRIC=…) [AS alias] [WHERE predicate] ORDER BY distance` — required for latest-version indexes; legacy `TOP_N` parameter only for earlier indexes. Plan §20.3/§20.5 templates match (WHERE after TVF alias = iterative-filter position on latest).
- **Forced ANN (DA:85):** `FORCE_ANN_ONLY` documented table hint. Evidence taxonomy correct: forced-ANN success is proof; approximate syntax alone is not (optimizer may pick kNN). Hint placement → Phase 0 probe row (A8).
- **Index version detection (DA:86):** `JSON_VALUE(v.build_parameters, '$.Version') >= '3'` ⇒ latest; below ⇒ migration recommended. No in-place upgrade; drop + recreate; **dropping immediately disables approximate search until recreation**.
- **Health DMV (DA:87):** `sys.dm_db_vector_indexes` exposes `approximate_staleness_percent`, `last_background_task_succeeded`. Documented bands: 0–5% normal steady state; 20–30% during batch loads expected/self-draining; sustained >10–15% investigate; rebuild on recall degradation, not staleness alone. Rows stay queryable while stale; ranking quality degrades. **DMV existence itself is a latest-format probe:** `SELECT OBJECT_ID('sys.dm_db_vector_indexes')`.
- **Index prerequisites (DA:88):** clustered PK required (preview guidance: single-column integer PK); ≥100 non-null rows for latest-format creation; no partitioning; not replicated to subscribers; `TRUNCATE TABLE` blocked while index exists (drop → truncate → repopulate ≥100 → recreate); DiskANN gated to Standard/Enterprise editions.
- **Embedding functions (DA:89):** `AI_GENERATE_EMBEDDINGS` + `CREATE EXTERNAL MODEL` **GA in Azure SQL (May 2026)**; preview on box. `API_FORMAT ∈ {Azure OpenAI, OpenAI, Ollama, ONNX Runtime}`; `MODEL_TYPE` currently `EMBEDDINGS` only; `LOCAL_RUNTIME_PATH` for ONNX; built-in retry; `PARAMETERS` JSON with per-call override. Box/MI gates: `sp_configure 'external rest endpoint enabled', 1` (REST) and `'external AI runtimes enabled', 1` (ONNX); not needed on Azure SQL DB.
- **float16 (DA:90):** preview; up to ~3,998 dims; driver transport remains JSON-text fallback — plan's conservative policy stands.

## 6. Implementation-plan amendments A1–A10 (DA §4.2) — apply to base plan

**A1 (P0 — correctness of the flagship; DA:104–105). Legacy-index filtered comparisons must model post-filter semantics.** On earlier-version indexes predicates apply *after* approximate search (docs describe manual `TOP_N` oversizing). Plan's legacy template (§20.5) has no filter; §20.6 structured predicates mean different things on latest (iterative) vs legacy (post-filter over truncated candidates). Required: (a) when index version < 3 AND structured filters present → either disable the approximate variant in automated comparison with explanation, or run with explicit disclosed `TOP_N = K × M` oversample (M host-configured, shown in generated SQL and evidence panel); (b) new evidence row for filter semantics — `Iterative filtering (during traversal)` vs `Post-filtered after approximate retrieval (TOP_N oversampled ×M)`; (c) SQL-builder + comparison tests for the legacy+filter matrix. Also a first-class UX element (U8/F4).

**A2 (P0 — quantified; DA:107–108). Page/frame math + interim clamp.** One 1,536-dim float32 cell = 6,144 raw bytes → 8,192 base64 chars; a 1,000-row single-vector-column page ≈ 8.2 MB vs 256 KiB page target (~32×); at 1,998 dims ≈ 10.7 MB (~42×); 64 MiB frame ceiling reachable with multi-vector-column selects at default page rows. Endorse exact-encoded repacker as platform fix; **interim inside PR 3:** clamp rows-per-page when vector type hint present — `rowsPerPage = clamp(pageTargetBytes / conservativeEncodedRowBytes, 1, PageRows)` — so typed vectors never rely on the generic provider-object estimator.

**A3 (P1; DA:110–111). Extend capability probe + Index findings with 2026 surface.** Add to `VectorDatabaseCapabilities`/catalog service: `externalRestEndpointEnabled` (box/MI), `externalAiRuntimesEnabled` (ONNX), latest-format signal via `OBJECT_ID('sys.dm_db_vector_indexes')` in addition to index-version parsing, edition gating where detectable. Add Index findings: TRUNCATE blocked (with documented drop→truncate→repopulate→recreate sequence in generated script), not replicated, no partitioning, migration script service-impact comment ("dropping immediately disables approximate search until recreation — plan a maintenance window"). Fold documented staleness bands into finding tooltip, **attributed to documentation** (consistent with the spec's "no universal threshold claim" rule).

**A4 (P1; DA:113–114). Egress classification per `API_FORMAT`.** Three registers in the confirmation dialog "Execution" line: `Local ONNX runtime on the SQL Server host — no network egress` / `Host-local endpoint (localhost) — text leaves the database engine` / `SQL Server calls the external endpoint <host> — text leaves your environment`. Same friction, different truthful copy. Capability popover shows `API format` per model. Copy + one metadata field from `sys.external_models`.

**A5 (P1; DA:116–117). Stamp search evidence with index staleness at measurement time.** In the same diagnostic session, immediately before the variant runs, read `approximate_staleness_percent` for the bound index (when DMV+permissions allow); attach to `VectorSearchComparisonResult` evidence: `Recall@20 90% — measured at 12.3% index staleness`. One DMV query per comparison; degrades gracefully to absent.

**A6 (P2; DA:119–120). Explicit scan-side byte cost.** 25,000 rows × 1,536 dims ≈ 154 MB raw / 205 MB base64 traversed worst case. Add a disclosed scan-bytes budget (or derive+display) so the Profile scope popover reports what the scan cost and perftest can assert it. Small contract addition to `VectorSampleDescriptor`/probe counters, not a behavior change.

**A7 (P2; DA:122–123). Expose PC3's explained variance (free — 3-component working subspace, 3×3 B eigendecomposition).** Report in `VectorProjectionSummary`, render in truth banner: `PC1 18.4%, PC2 9.7%, next component 8.9% (not shown)`. PC3 ≈ PC2 ⇒ known-lossy 2-D; PC3 ≪ PC2 ⇒ earned trust.

**A8 (P2; DA:125–126). Explicit Phase 0 probe rows:** `FORCE_ANN_ONLY` placement/grammar on target, `WITH APPROXIMATE` acceptance, legacy `TOP_N` rejection on version-3 indexes — so template selection is evidence-backed per target, and an agent can't skip them.

**A9 (P2; DA:128–129). Guard against `MODEL_TYPE` expansion.** Model selector + confirmation copy must filter on `MODEL_TYPE = EMBEDDINGS` explicitly; future non-embedding types degrade to "unsupported model type", not a wrong offer.

**A10.** Endorsements — see §3 above.

### PR-plan notes (DA:134–136)
1. Split PR 3's provider/RID matrix into an **evidence-only PR 3a** (fixtures + recorded matrix, no product change) so metadata rules freeze on committed evidence.
2. Add A1's legacy-filter semantics to **PR 10's test matrix (plan §31.8) now**, so it can't be discovered post-preview.

## 7. UX-spec amendments U1–U10 (DA §5.2) — apply to base UX spec

- **U1 (DA:148).** Retire "summary cards" (spec §11.2/§11.3). Replace with one dense facts strip: `label value` segments under header (or status-bar segments), monospace values, no containers. **Cards must not exist anywhere in this pane.**
- **U2 (DA:150).** Tables are grids, not styled divs: rank comparison (§12.7), findings rows (§11.5), accessible point list (§14.8), Index/DMV values → real data grids with FluentResultGrid look (~24 px rows, resizable/sortable, right-aligned monospace numerics, virtualization, keyboard model, Results-style selection/copy). Index DMV/catalog facts = two-column properties grid.
- **U3 (DA:152).** Extend "issue A" single-scrollbar rule: workspaces are fixed layouts whose inner regions scroll (match `qs-results-body-fill`). Page-level vertical scroll only for Profile's stacked narrow mode. **No max-width**; pane fills results body.
- **U4 (DA:154).** Make spec §20.1 numeric/normative: base 13 px / controls 12 px, radius ≤ 2 px, 26 px buttons, 30 px tab strip with 24 px text-only tabs, 24 px status bar, 4 px splitters, grid rows ~24 px, `--vscode-editor-font-family` for all numerics, VS Code tokens only, shadows only on menus/dialogs.
- **U5 (DA:156).** Workspace-purpose questions are empty-state copy only — never permanent subtitles. Chrome states facts; empty states teach.
- **U6 (DA:158).** Rail items one line: icon + label at 22–24 px, no sub-captions; lock glyph for gated workspaces stays; evidence legend moves out of nav (into evidence panel or status-bar popover).
- **U7 (DA:160).** Scope/method live once: header badge = interactive owner (opens details); footer = passive summary; **delete per-panel scope chips** ("Sampled" chips on every panel header = repetition noise).
- **U8 (DA:162).** Add the filter-semantics evidence row (from A1) to §12.10's table: iterative vs post-filtered, with oversample multiplier.
- **U9 (DA:164).** Reserve a Search slot for the self-recall harness (F1): third run mode — `Query set: this vector / N sampled rows`.
- **U10 (DA:166).** Density gate in the mockup package (§24): every screen also rendered at 1280×720; `ux_revisions.md` §9 acceptance check applies.

### v1 mockup diagnosis (DA §6) — the seven compositional tells to avoid in implementation
Keep: VS Code tokens across 3 themes, codicons, real 24 px status bar, capability popover as facts table ("Facts probed from the connection, not marketing labels" — keep that sentence forever), model-call confirmation content, zero gradients. Avoid: (1) KPI card rows with 20 px display numerals; (2) bordered panel-cards radius 6 with tinted headers; (3) pill chips as vocabulary (native = codicon + plain text in severity foreground color); (4) centered `max-width: 1180px` scrolling page; (5) marketing-register microcopy in chrome; (6) two-line rail items + legend in nav; (7) bespoke div-tables for the rank comparison. IA transfers as-is.

## 8. RR P0 corrections (RR §2) — MUST land in normative specs/mockup annotations before coding begins

**P0-1 (RR:89–118). Source mode explicit everywhere.** Header currently shows current result (`Chunk search (top 50)`), selected vector column, bound table (`dbo.DocumentChunks`), and sample (`5,000 of 2,412,883`) at once — user can't tell where a number came from. Add a source-mode fact to header/facts strip and carry it in **every analysis result contract**. Recommended type (verbatim):

```ts
export type VectorEvidenceSource =
    | { kind: "capturedResult"; resultSetId: string; frozenRows: number }
    | { kind: "boundTableSample"; objectId: number; eligibleRows?: number; sampledRows: number; samplingMethod: string }
    | { kind: "catalog"; objectId?: number }
    | { kind: "diagnosticQuery"; sessionId: string; statementCount: number }
    | { kind: "localComputation"; inputRows: number }
    | { kind: "interpretation"; basedOnEvidenceIds: readonly string[] };
```

Visible examples: `Source: captured result, 50 rows` / `Source: bound table sample, 5,000 of 2,412,883 eligible rows` / `Source: catalog and health DMV` / `Source: 3 new statements on isolated session` / `Source: local computation over selected vectors`. Never infer source from color/position/workspace.

**P0-2 (RR:132–168). Typed subject on every finding.** Profile shows count `23` but drawer says `Affected rows` even for `Near-constant dimensions`. Verbatim contracts:

```ts
export type VectorFindingSubject = "row" | "dimension" | "duplicateGroup" | "pair" | "category" | "document" | "index" | "model" | "chunk";
export interface VectorFindingSummary {
    readonly findingId: string;
    readonly subject: VectorFindingSubject;
    readonly affectedCount: number;
    readonly sampledScope: boolean;
    readonly title: string;
    readonly method: string;
    readonly severity: "error" | "warning" | "info" | "success";
}
```

Drawer title/actions derive from `subject` (`Affected dimensions: 23`, `Duplicate groups: 12, covering 37 rows`, `Affected rows: 8`, `Categories with unusual geometry: 1`). Row actions (Reveal in Results, Add to Compare, Use as Query Vector) must not appear for dimension-only findings unless a deliberate representative-row subview exists.

**P0-3 (RR:171–194). Fix Index healthy-state contradiction.** `vec_index.png` shows `Version v3 (latest format)` + success finding + a selected `Generate migration script (v2 -> v3)` that drops/recreates the healthy v3 index. Split Index into ≥2 explicit states: (1) **healthy current-format** — hide/disable migration; offer health snapshot, create/recreate script for review, workload support-index review, config checks; explain no migration required. (2) **earlier-format** — version < 3 / unknown; offer migration script with service-impact warning ABOVE the script (dropping disables approximate search until recreation); show post-filter semantics and DML limitations as version-specific findings. Never generate a destructive migration recommendation from a generic command list when catalog says the index is current.

**P0-4 (RR:196–220). External model naming/ownership.** External model objects are **database-scoped names with an owner principal, not schema-scoped objects**. `dbo.TextEmbedding3Small` is wrong everywhere — generated T-SQL, selectors, provenance records, telemetry-safe metadata. Display: `Model TextEmbedding3Small / Owner dbo / Provider model text-embedding-3-small`. Reproducibility identity must include: object name; owner principal; API format; provider model string; endpoint host or local-runtime classification; `parameters` digest; create+modify time; dimensions requested/observed; model type explicitly `EMBEDDINGS`.

**P0-5 (RR:222–256). Layered network claim.** `No network requests` in the status bar is wrong after the engine calls a remote model. Layered copy: before any call — `Webview network: none` / `Server-side model calls: none in this session`; after a confirmed remote call — `Server-side external calls: 1`; ONNX — `Model execution: local SQL Server runtime`; host-local Ollama — `Model execution: host-local endpoint`. Footer must not contradict the confirmation dialog.

**P0-6 (RR:258–279). Search self-match/duplicate-exclusion semantics.** Verbatim contract:

```ts
export interface VectorSearchExclusionPolicy {
    readonly excludeSourceRow: boolean;
    readonly excludeExactVectorDuplicates: boolean;
    readonly excludeSameDocument?: boolean;
    readonly keyPredicateSql?: string;
}
```

Visible evidence: `Source row excluded by key: chunk_id <> 100042`, `Exact vector duplicates included`, `Same-document chunks included`. **Exact and approximate variants must use the same exclusion predicate.**

**P0-7 (RR:281–291). State comparison read consistency.** Search run contract + evidence panel must state one of: `Read consistency: one read-only snapshot transaction` / `Read consistency: database snapshot isolation` / `Read consistency: read committed; concurrent changes may affect comparison`. Prefer a single isolated diagnostic session with a stable read view where supported **without changing database settings; never enable snapshot isolation automatically**; disclose when a stable read view can't be guaranteed.

**P0-8 (RR:293–307). Projection analyzed-vs-rendered counts.** `vec_projection.png` says PCA used 5,000 rows but the point list says `1,200 sampled`. Report separately: `Analyzed: 5,000 vectors / Rendered: 1,200 points / Point selection: deterministic display subsample`. If all analyzed are rendered, counts must match. Point list must never say `sampled` for a display cap.

**P0-9 (RR:309–329). Statistically honest Search timing.** `Exact 842 ms` vs `Approx 17 ms (50x)` from single cold-vs-warm observations is theatrical. MVP may show one observation but must say `single observation`. Product-ready mode: optional warmup; 3–10 measured repeats (policy-bounded); median + p95 wall time; logical reads + CPU where available; plan-capture flag; identical parameters and query vector across variants. **Hide the speedup ratio when observations aren't comparable.**

**P0-10 (RR:331–341). Freeze the query vector once per comparison.** Text-with-model mode must not call the model separately per variant. Generate/obtain once, validate dimensions + base type once, record a digest locally, reuse for every statement. UI: `Query vector generated once and reused across 3 search variants`.

## 9. RR P1 additions (RR §3) — contract/roadmap now, UI may ship later

- **P1-1 (RR:346–361). Query-set recall harness** (labeled `Query set` in Search, not hidden in Profile): sample N rows, each row as query, exclude source row by key, run exact+approx; report median/p5/min recall@K, median+p95 latency, worst query keys, recall grouped by category/language/tenant/document type, staleness at run time, cancellation + statement count. (= DA F1, P1 fast-follow after PR 10: 2N bounded queries, N default 20–50 hard-capped, sequential, cancellable between commands; loop over existing `VectorSearchComparisonSpec` with an aggregate result contract; composes with A5.)
- **P1-2 (RR:363–368). K-sweep** seeded `{10, 20, 50, 100}`: exact once at max K, compare prefixes; show recall, overlap, latency by K. (= DA F2.)
- **P1-3 (RR:370–389). RAG crowding/diversity diagnostics:** unique documents in top K; max chunks from one document; adjacent-chunk share; repeated boilerplate neighbor frequency; hubness (how often each row appears in sampled neighbor lists); same-tenant vs cross-tenant neighbor counts. Descriptive by default, not universal thresholds.
- **P1-4 (RR:391–417). Provenance/freshness auditing:** columns/declared metadata for source text column/expression, document+chunk keys, external model object, provider model string, model/deployment version marker, preprocessing template, query/passage prefixes, normalization policy, chunk size+overlap, source modified time, embedded time, embedding batch ID. Findings: source modified after embedding; missing embedding timestamp; mixed model populations; mixed preprocessing; same dims but incompatible provenance; declared vs stored dimension disagreement.
- **P1-5 (RR:419–438). Endpoint/call diagnostics:** configured retry count, status-code class, endpoint host, model modify time, request count, payload bytes, call duration, cancellation outcome, dimension returned, XEvent refs (permission-gated), principal's execute permission, REST/AI-runtime gate state. **No secrets, full URLs with query strings, source text, or returned vectors in diagnostics.**
- **P1-6 (RR:440–450). Hybrid-search evaluation fast-follow** (vector-only / full-text-only / hybrid union / reciprocal rank fusion / optional rerank). Saved experiment format must permit multiple retrieval stages and graded expected rows now.
- **P1-7 (RR:452–470). ACL/tenant-filter validation:** preserve RLS, user permissions, tenant predicates, soft-delete/visibility, temporal/status filters; **never open a privileged diagnostic connection or bypass RLS**. Report eligible rows under current principal, filter selectivity, cross-tenant neighbors within authorized result, exact vs approx filter semantics, fewer-than-K caused by eligibility rather than recall.

## 10. DA high-value additions F1–F9 (DA §7) and explicit non-goals

- **F1** self-recall harness (P1) and **F2** K-sweep (P1) — superseded/confirmed by RR P1-1/P1-2 above.
- **F3 (P1)** = A5 staleness-stamped evidence, surfaced as one evidence line in Search results UI, not buried in Index.
- **F4 (P0-with-PR10)** = A1(b) filter-semantics evidence row (prevents "my filtered vector search returns 3 rows" incidents).
- **F5 (P2, promote from deferred).** Local float16 quantization lab: round-trip sampled float32 matrix through IEEE 754 half in the worker; recompute top-K neighbor lists in both precisions; report rank churn + distance deltas. Zero server support; label `Simulated float16 round-trip; server behavior may differ`. Pull forward once PR 8 worker infra exists. (RR:783 keeps it P2 in Compare.)
- **F6 (P2).** Per-dimension contribution explainer: top signed aᵢ·bᵢ terms for a selected pair under dot/cosine, beside the top-|Δ| view in Compare; local math on in-memory vectors.
- **F7 (P1, tiny).** Bundled repro script: one action on a completed comparison emits a single commented `.sql` — capability check, exact/approx/forced variants exactly as executed, index-version verification query, health query, header with target/assumptions/provenance — opened in an editor, never persisted.
- **F8 (P1, small).** Config-gate scripts, generated never executed: on closed gates add `Generate enablement script for review` for `PREVIEW_FEATURES` (database-scoped config), `external rest endpoint enabled`, `external AI runtimes enabled` — each with permission requirements and scope-of-effect comments.
- **F9 (research gate, keep deferred).** Index footprint/memory characterization — surface not stable enough to spec.
- **Explicitly NOT recommended for MVP+1 (DA:217):** UMAP/t-SNE (PCA + original-space neighbors covers the diagnostic need); any automatic index/rebuild action; chat/NL layer in this pane ("this pane's brand is determinism").
- DA:227 north star: "median recall@20 of 0.94 at 11 ms, measured across 50 sampled queries at 3% staleness, iterative filtering confirmed — here's the repro script" = F1+F2+F4+F7.

## 11. Shell/header tightening (RR §4, RR:482–503)

1. Source mode from P0-1. 2. Rename `Model enabled` → `Embedding model configured` / `Embedding model available` / `Model call verified` (last only after a successful confirmed call). 3. No green success merely because a catalog row exists (configured ≠ reachable). 4. Capability popover permission states: catalog metadata visible; health DMV permission; external model executable by current principal; table binding key readable. 5. Engine/platform facts: SQL Server 2025 / Azure SQL DB / MI / Fabric SQL; engine edition; compatibility level; preview-feature state; vector index version + regional rollout state. 6. Sample button describes analysis scope, not only sample size. 7. Layered network claim (P0-5). 8. Header must not imply all workspaces share one source (Search/Index often table-bound + server-executed; Compare can be local; Profile can be detached).

## 12. Screen-by-screen corrections (RR §5) — condensed delta list

**5.1 Capability popover (`vec_model.png`, RR:507–543):** replace `dbo.TextEmbedding3Small` with name+owner as separate facts; distinguish configured / authorized-and-callable / successfully-invoked-this-session; show `Model type: EMBEDDINGS` explicitly and filter unsupported types; add `Model modified` + short parameters digest; add engine/platform + compat level; add metadata visibility + `VIEW DATABASE STATE` availability; add egress class (external remote / host-local / local ONNX); add index metric compatibility separate from index existence; add a fact for vector metadata exposed only as string (driver/first-result path did not preserve native type); never expose credential name, secret, or URL query string. Acceptance tests RR:536–543 (catalog visible but exec denied; model absent; multiple models; returned dim ≠ bound column; DMV hidden; 2025 preview off; Azure region with earlier format; ONNX on supported Windows).

**5.2 Analysis scope popover (`vec_sample.png`, RR:545–579):** rename `Uniform windows` → `Evenly spaced row windows over captured result order` / `Deterministic window sample; not random`; state ordering can bias the sample; explain seed scope (stable only for same frozen row order + sampling spec); report rows scanned / rows accepted / null-unavailable skipped / bytes read from result store / packed bytes / elapsed / partial reason; later add table-bound deterministic key-hash sample when a stable key exists; full scan must show raised budget, expected work, cancellation, source mode before start; never call the sample "representative" without justification. Acceptance tests RR:573–579 (category-ordered bias disclosure; result smaller than sample; scan cap hit; component budget reduces rows; null-heavy column; spill read path; mid-preparation cancellation).

**5.3 Profile (`vec_profile.png`, RR:581–657):** implement P0-2 subjects; label every distribution with metric+scope; `Sampled pair distances` is descriptive, explanatory copy in details not chrome; centroid-distance outliers can overflag valid minority clusters — state method, offer local-density/kNN outlier later; `Near-constant dimensions` → `Low-variance dimensions in this sample`; duplicate equality must say byte-equal float payload vs component-equal vs normalized-equal within tolerance; near-zero thresholds disclosed and metric-specific; **non-finite components = provider/harness test only until the server ingestion matrix proves storability through supported SQL paths**; group comparison shows per-group sample size + instability warning for small groups; add P1-4 and P1-3 findings; add profiling by language/tenant/source system/document type/embedding batch. Findings taxonomy verbatim at RR:615–645 (Transport and shape / Distribution / Duplication and crowding / Provenance and freshness / Group behavior). Acceptance tests RR:649–657.

**5.4 Finding drawer (`vec_profile_findings.png`, RR:659–679):** title/columns depend on subject; duplicate finding shows groups, leaders, sizes, representative members; dimension finding shows dimension/variance/range/optional representative rows; group finding shows compared stats + sample sizes; disable/replace row actions for non-row findings; keep selection + keyboard focus stable across drawer open/close; expandable `Method and threshold` section; `Reveal in Results` maps ordinals through local grid sort/filter and preserves filters; `Use as query` names which vector when multiple selected; export finding keys or generated validation SQL, not raw vectors by default. Drawer pattern reusable for Search, Projection, Pipeline.

**5.5 Search composer (`vec_search.png`, RR:681–718):** add P0-6/P0-7/P0-10; **exact mandatory whenever recall is requested**; approximate and forced ANN capability-gated separately; **filters from a structured builder + parameterized SQL — never concatenate free-form predicates into automated comparison queries**; show eligible-row count / filter selectivity when cheap; block dimension mismatch pre-run; warn on provenance mismatch even with matching dims; text-with-model uses the same confirmation pattern as Pipeline; paste-vector validates JSON size, dimension count, finiteness, base type without evaluating code; expression mode stays local and visibly loses/synthesizes provenance; add disabled query-set placeholder now. Acceptance tests RR:706–718 (incl. selective filter on latest iterative vs earlier post-filter index; no compatible index; metric mismatch; exact-only connection).

**5.6 Search results (`vec_search_results.png`, RR:720–759):** add read consistency + self-exclusion evidence; query-vector source + digest summary; eligible-row count + selectivity; plan-capture state + whether ANN proof came from forced syntax, approved plan pattern, or neither; single-observation vs repeated timing (P0-9); **grid = full union of exact and approximate results, showing exact-only and approx-only rows**; preserve exact and approximate distances separately; explain ties + deterministic secondary ordering; when exact returns < K eligible rows, use actual exact count as denominator and say why; earlier-index: show `TOP_N` oversample multiplier + post-filter semantics; staleness stamped at run time (not last-opened Index value); unique-document + same-document concentration metrics; forced-ANN failure stays a diagnostic result, never a generic error toast; repro scripts contain exact parameters/filters, redact secrets, no remote source text unless explicitly requested. Acceptance tests RR:747–759.

**5.7 Compare (`vec_compare.png`, RR:761–795):** state 0- vs 1-based dimension numbering; `Top contributions` formula metric-aware + visible in details; cosine: explain normalization and how contributions sum; **`Nearest bound rows` is a new server query — label its evidence source separately, not local computation**; `Compatible` must not mean dims+base type only — use `dimension-compatible` / `provenance-compatible` / `provenance unknown` / `incompatible model or preprocessing`; pairwise matrix metric selectable or explicitly inherits workspace metric; arithmetic output shows norm, normalization, dimension, provenance status; **expression parsing = small audited grammar, never `eval`**; float16 round-trip experiment = P2; top signed contributions with "latent dimensions usually lack human labels" caveat. Acceptance tests RR:786–795.

**5.8 Projection (`vec_projection.png`, RR:797–830):** resolve P0-8; label axes `PC1`/`PC2` even with hidden ticks; report centering, normalization, seed, PCA method in details popover; keep third explained-variance component in banner (A7); add lasso selection, keyboard selection via point grid, Reveal in Results; legend filtering without silent recomputation; original-space nearest-neighbor lines for selected points; neighborhood-preservation score as advanced fact, not universal grade; explain category separation can reflect source text/metadata leakage/language/preprocessing, not retrieval quality; display subsampling deterministic + disclosed; canvas selection ↔ virtualized point grid synchronized and accessible. Acceptance tests RR:821–830 (incl. 5,000 analyzed / 1,200 rendered; same-seed stable sign/orientation; HC + screen-reader point navigation).

**5.9 Index (`vec_index.png`, RR:832–882):** implement P0-3 state machine; add engine/platform (v3 availability differs by target); **`Rows indexed` and `0 pending` are NOT direct documented health-DMV fields** — label as eligible non-null vector rows / estimated pending changes / direct DMV values per actual query; add all current health fields: last background task duration, processed inserts, processed deletes, last task error message; staleness guidance attributed, not a rebuild threshold; limitations + review scripts for clustered-PK requirement, ≥100 non-null vectors, no partitioning, no replication, TRUNCATE blocked, DacPac/BACPAC import+deployment constraints, earlier-index read-only/stale behavior, full DML on current format where supported; **`Edition gate` probed, never hardcoded from mock data**; support-index suggestion tied to observed filter columns or user-declared workload, never universal; health history says `Current snapshot only` until persisted history exists; migration SQL prominently states service impact, never default on a healthy index. Acceptance tests RR:869–882 (12 states).

**5.10 Pipeline (`vec_pipeline.png`, RR:884–934):** implement P0-4; label provenance source (catalog fact / workspace profile / SQL extended property / inferred binding / user-entered declaration); `Cosine (stored -> fresh)` must say `Cosine distance` or `Cosine similarity`; state retrieval mode used for neighbor overlap + rank movement; validate fresh embedding dims before comparison/storage; record model modify time + parameters digest with the run; **never send a truncated result-cell prefix to a model — fetch full source by verified key with disclosure, or block**; chunk ribbon shows source length, chunk order, start offset, chunk length, overlap chars, tail chunk, chunk-set ID, coverage gaps/repeated spans; `Generate embeddings for chunks` confirms chunk count + expected model calls; token-limit/model-side truncation caution (SQL chunks are character-based; endpoints enforce token limits); batch drift sampling as visible subflow or fast-follow; preprocessing templates incl. query/passage prefixes; source-freshness + model-provenance findings. Acceptance tests RR:923–934.

**5.11 Re-embed confirmation (`vec_pipeline_regen.png`, RR:936–955):** replace schema-qualified model display; add model modify time + parameters digest; retry count + max attempts; egress class with remote/host-local/ONNX-specific copy; source sensitivity/classification when available (without claiming completeness); whether full source was fetched from the table and by which verified key; cancellation semantics (a remote call may already be in flight); output dimension expectation; for N chunks show N calls or actual provider batching plan; primary action explicit: `Generate embedding` / `Generate N embeddings`.

## 13. Cross-workspace contracts (RR §6) — must be explicit before implementation

**6.1 Evidence identity (RR:961–984).** Every displayed fact carries an evidence record; footer `Evidence` control opens the list for the current workspace. Verbatim:

```ts
export interface VectorEvidenceRecord {
    readonly evidenceId: string;
    readonly kind: "capturedResult" | "catalog" | "healthDmv" | "diagnosticQuery" | "modelCall" | "localComputation" | "interpretation";
    readonly createdEpochMs: number;
    readonly sourceDescription: string;
    readonly sampled?: boolean;
    readonly partial?: boolean;
    readonly partialReason?: string;
    readonly statementDigest?: string;
    readonly inputDigest?: string;
}
```

**6.2 Provenance compatibility (RR:986–1000).** Verbatim:

```ts
export type VectorCompatibility =
    | "incompatibleDimensions"
    | "incompatibleBaseType"
    | "dimensionCompatibleProvenanceUnknown"
    | "provenanceMismatch"
    | "compatibleByDeclaredProfile"
    | "compatibleByVerifiedRegeneration";
```

Never show a green `provenance match` merely because two vectors have 1,536 components.

**6.3 Partial/approximate language (RR:1002–1019).** Every partial result states: what was scanned / accepted / skipped / remains unknown / why work stopped. Every approximate result states: algorithm or execution mode requested; execution strategy proven, unproven, or exact fallback; recall denominator; index version; filter semantics; staleness at run time when available.

**6.4 Security/permission inheritance (RR:1021–1025).** Diagnostic queries + model calls execute under the current user's effective database permissions — no privileged metadata/service connection that sees rows the user cannot. Auxiliary session may share the saved connection profile and auth material but must not elevate principal, bypass RLS, ignore session context, or omit user-required session setup. Disclose the isolation boundary when the user session has meaningful `SESSION_CONTEXT`, temp tables, or uncommitted data invisible to the isolated session.

**6.5 Reproducibility bundle (RR:1027–1042).** A completed experiment generates a local reviewable repro script: capability + version checks; table + vector-column identity; exact query; approximate query; forced ANN query where supported; structured filters; exclusion predicate; index metadata query; health query; model metadata query when relevant; comments with sample method, staleness, read consistency; **no secrets or raw remote source text by default**.

## 14. Minimum product demo/test matrix before preview (RR §7, VTEST-01..VTEST-22, RR:1048–1073)

| ID | Scenario | Workspace | Proof |
| --- | --- | --- | --- |
| VTEST-01 | Native vector detection/transport | Profile | dims + float32 preserved, no JSON inflation in supported path |
| VTEST-02 | Clean normalized clustered corpus | Profile, Projection | no false universal error; honest clusters/norms |
| VTEST-03 | Null/zero/near-zero vectors | Profile | counts + row drawer correct |
| VTEST-04 | Exact duplicate groups | Profile | group count vs covered-row count differ correctly |
| VTEST-05 | Low-variance dimensions | Profile | subject = dimension, not row |
| VTEST-06 | Group distribution shift | Profile | group sizes + within-group distances shown |
| VTEST-07 | Compare three vectors | Compare | metrics, matrix, medoid, closest pair, expression work |
| VTEST-08 | PCA analysis vs display cap | Projection | analyzed and rendered counts separate |
| VTEST-09 | Exact selected-row search | Search | self-exclusion explicit; exact top K reproducible |
| VTEST-10 | Current-format ANN comparison | Search, Index | forced ANN evidence, recall, staleness, iterative filtering shown |
| VTEST-11 | Earlier-index post-filter | Search, Index | TOP_N oversampling + fewer-than-K disclosed |
| VTEST-12 | No index / metric mismatch | Search, Index | exact fallback or warning honest |
| VTEST-13 | Healthy index state | Index | migration command absent |
| VTEST-14 | Legacy migration state | Index | service-impact warning + generated script |
| VTEST-15 | Re-embed selected source | Pipeline | one confirmed model call, egress disclosure, dim validation |
| VTEST-16 | Source changed after embedding | Pipeline, Profile | drift + freshness finding visible |
| VTEST-17 | Character chunking with overlap | Pipeline | offsets, lengths, overlap, tail, call count visible |
| VTEST-18 | Permission-degraded metadata | All | catalog/DMV-unavailable states remain useful |
| VTEST-19 | Cancellation and rerun | All | sessions, leases, workers, results clean up |
| VTEST-20 | Pinned results | Profile, Compare, Projection | detached mode survives source rerun / editor close |
| VTEST-21 | Query-set recall harness | Search | distribution, worst queries, statement budget reported |
| VTEST-22 | Tenant/ACL filter | Search | current principal + filter semantics preserved |

Companion doc with execution detail: `vector_workbench_test_and_demo_guide.md` (RR:24).

## 15. Readiness gates (RR §8) — staged go/no-go criteria

**8.1 Ready for coding-agent PR 1 when (RR:1077–1084):** prior platform prerequisites still accepted; P0-1..P0-10 incorporated into normative specs or the issue list; Index mockups split into healthy-current + earlier-format states; external model naming corrected; finding subjects typed; Search exclusion + read-consistency policies specified; Projection analysis/render counts separated; footer network copy layered.

**8.2 Ready for UI vertical slice when (RR:1088–1093):** typed vector transport + ordinary result-cell safety complete; **compact capture privacy fixed and canary-tested**; **Query Studio CSP in place**; host analysis sessions, sparse projection, cancellation, budgets pass tests; UX renders all error/partial/permission/unsupported states without inventing data; synthetic demo corpus produces stable Profile/Compare/Projection/exact-Search results.

**8.3 Ready for table-bound Search preview when (RR:1097–1102):** exact + approximate use the same frozen query vector, metric, filter, exclusion, read view; version-specific syntax + filter semantics probed; forced-ANN evidence correctly classified; staleness stamped at run time; rank-union + recall-denominator tests pass; repro script output matches executed SQL.

**8.4 Ready for Pipeline preview when (RR:1106–1112):** model execution permission + type checked; remote/host-local/ONNX egress copy correct; full source-text handling honest; model output dims validated; every model call explicitly confirmed; **no model secret, source text, or returned vector enters logs or telemetry**; cancellation + retry tested.

## 16. Implementation ordering adjustments (RR §9, RR:1116–1124) — keep the prior PR plan, plus

1. Finding subject types + source-mode evidence contracts **before Profile UI**.
2. External-model identity + egress classification in the capability probe **before Pipeline UI**.
3. Search exclusion policy + read-consistency result fields **before the SQL builder is implemented**.
4. Separate Index state machine **before script commands are wired**.
5. Analysis-count vs render-count fields **before Projection first paint**.
6. Query-set + K-sweep shapes in the saved experiment schema even if UI ships later.
7. Synthetic corpus + deterministic expected results **before a coding agent implements chart and finding logic**.

Plus DA's two: PR 3a evidence-only split; A1 legacy-filter matrix into PR 10 / plan §31.8 now (DA:134–136).

## 17. Budget sanity numbers worth keeping (DA:100)

8,000,000 components ÷ 1,536 dims = 5,208 rows ≥ the 5,000-row sample cap ⇒ component budget binds only above ~1,600 dims (at 1,998 dims effective sample = 4,004 rows, surfaced by the "minimum implied by every limit" rule). 64 MiB packed-input budget = 10,922 rows at 1,536 dims — not the binding constraint. Numbers hang together; do not change without rechecking this arithmetic.
