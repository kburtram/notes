# Query Studio Vector Workbench — Design Review Addendum

**Status:** Independent review of the implementation plan, UX specification, and v1 mockup
**Date:** 2026-07-10
**Reviewed inputs:**
- `query_studio_vector_workbench_implementation_plan.md` (2026-07-10, 2,797 lines)
- `query_studio_vector_workbench_ux_spec.md` (2026-07-10, 1,339 lines)
- `Query_Studio_Vector_Workbench.html` (v1 design-agent mockup, decoded and inspected at markup/CSS/JS level)
- `microsoft/vscode-mssql@dev/query` at commit `205bbb98f4e21d551fbb4d9724301ca77cce7bd0` (shallow clone, 2026-07-10)
- `microsoft/sqltoolsservice@dev/query` at commit `d9aca04ec8293e36e19861f781ac609dde4f0fe2` (shallow clone, 2026-07-10)
- Microsoft Learn vector documentation and Azure SQL Dev Corner posts current as of 2026-07-10

**Companion output:** `ux_revisions.md` — the actionable brief for the design agent's v2 pass. This addendum explains *why*; that document says *do this*.

---

## 0. Scope and verdict

Three separate verdicts, because the three artifacts are at three different quality levels:

1. **Implementation plan: approve with amendments.** The branch inventory is accurate (every claim I spot-checked against live `dev/query` code held — see §2). The architecture is the right one: ordinary STS2 result path, store-lease reads, host-authoritative budgets, controller-bound opaque sessions, evidence-gated ANN claims. The amendments in §4.2 are refinements and one genuine semantic gap (legacy-index filtered comparisons), not structural changes.

2. **UX specification: approve with amendments.** The truth taxonomy (result facts / catalog facts / new execution / local computation / interpretation), the evidence-first Search design, and the honest-partial language are the strongest parts of the whole package and are exactly what distinguishes this from every generic embedding projector. The amendments in §5.2 are about *visual idiom*, where the spec under-specifies and the mock filled the vacuum with dashboard patterns.

3. **v1 mockup: right materials, wrong composition.** The mock is more faithful than it looks at first glance — it uses VS Code theme tokens across three themes, codicons, a real 24 px status bar, and zero gradients. The "PowerBI" feeling you're reacting to is compositional, not chromatic: KPI card rows, chip-badged panel cards, a centered max-width scrolling page, and marketing-register microcopy. §6 has the diagnosis; `ux_revisions.md` has the fix list. The information architecture underneath should *not* churn — the six workspaces, the header selectors, the capability popover, and the confirmation dialog are correct and should survive into v2.

---

## 1. What was verified and how

The plan asserts specific symbols and behaviors in both repos "verified against the public `dev/query` branches on 2026-07-10." I independently re-verified a sample of those claims today against the same branches at the commits listed above, and separately verified the SQL surface claims against current Microsoft Learn documentation (which has moved since some of the plan's referenced pages were snapshotted — see §3, notably the March 2026 DiskANN format changes and the May 2026 Azure SQL GA of the embeddings functions).

Anything below labeled **Verified** means I read the code or documentation myself today. Anything labeled **Not re-verified** means I did not independently check it and am relying on the plan; those items are listed so the boundary of this review is explicit.

---

## 2. Branch verification ledger

### 2.1 `microsoft/sqltoolsservice@dev/query` (`d9aca04`)

| Plan claim | What I found | Status |
| --- | --- | --- |
| `Packages.props` pins Microsoft.Data.SqlClient 6.1.5 | `<PackageReference Update="Microsoft.Data.SqlClient" Version="6.1.5" />` at line 86 | **Verified** |
| `SqlClientSession.PumpResultSetAsync` uses `SequentialAccess`; non-specialized values fall through to `reader.GetValue(i)` | `ExecuteReaderAsync(CommandBehavior.SequentialAccess, …)` with QO-4 comments; generic `_ => reader.GetValue(i)` arm in the cell switch | **Verified** |
| `WireValueEncoder.Encode`: unknown objects use invariant `Convert.ToString` | `_ => Wrapper("provider", Convert.ToString(cell, CultureInfo.InvariantCulture) ?? string.Empty)`; known byte[] path base64-wraps; oversized strings/binaries go through the truncated path | **Verified.** A native `SqlVector<float>` today lands in the `provider` wrapper — lossy and text-inflated, exactly as the plan warns. |
| `CaptureElision.ElideInput` wraps only top-level `rows`, not `compact` | Elision predicate checks `et.GetString() == "rows"`; wrap/restore logic operates on `obj["rows"]` only; no `compact` handling anywhere in the file | **Verified.** The P0 privacy blocker is real. Compact `values`/`nullBitmap` can reach journals today. |
| `Sts2Defaults`: 1,000-row pages, 64 MiB frame ceiling | `PageRows = 1000`, `MaxFrameBytes = 67108864` | **Verified** (I did not chase the 256 KiB page target and 1 MiB cell bound constants specifically; the two I checked matched, and the page/frame arithmetic in §4.2-A2 uses the two verified values). |
| `SqlRowsPageBuilder` groups rows by approximate provider-object estimates | File exists at the stated path; estimator behavior not line-verified | Present; behavior **not re-verified** |

### 2.2 `microsoft/vscode-mssql@dev/query` (`205bbb9`)

| Plan claim | What I found | Status |
| --- | --- | --- |
| `services/sqlDataPlane/api.ts`: no vector variant in `ColumnMetadata` or `CellValue` | `ColumnMetadata` carries `isXml`/`isJson` markers, precision/scale/maxLength; `CellValue` union is null/string/number/boolean/datetime/binary/xml\|json/unsupported. No vector kind. | **Verified** |
| Tagged-cell precedent uses `$t` with a `v` payload field | `TruncatedCellEncoding { $t: "truncated"; …; v: string }` in `api.ts` | **Verified** — and this is the concrete proof behind the plan's rule that the vector tag must use `data`, not `v`. A vector tag with `v` would be one structural typo away from the generic truncated-cell display path. Keep that rule non-negotiable. |
| `IQueryResultStore` exposes leases, windows, streams, frozen summaries, stats | `retain(owner) → QueryResultStoreLease`, `getWindow`, `streamRows`, `summary`, `stats`, `demote`; store kinds `rowStoreV1 \| resultStoreV2 \| sts2 \| remote` | **Verified** |
| Only contiguous column projection exists | `CellWindowRequest` has `columnStart?/columnCount?` ("QO-7b"), no ordinal-list projection; `RowStreamRequest` has none | **Verified.** Sparse projection (plan §10) is genuinely new work, PR 5 is correctly scoped. |
| `RowReadReason` lacks a vector reason; lease owners lack `vectorWorkbench` | `RowReadReason = grid \| copy \| export \| text \| cellDocument \| diagnostic \| sample \| profile \| transform \| aiTool`; `QueryResultLeaseOwnerKind = liveRun \| pinnedDocument \| aiTool \| chatParticipant \| export \| command \| debug` | **Verified** |
| `webviewBaseController.ts` shared HTML has no CSP | Grep for `Content-Security-Policy`/`csp` in the file returns nothing | **Verified.** P0 CSP prerequisite stands. |
| `documentSessionBinding.ts` exposes only the user session; metadata uses separate acquisition; no auxiliary seam | Metadata catalog lease via `MetadataStoreService` with `commandKind: "metadata"`, `metadataSession: false` markers; no `acquireAuxiliarySession` or equivalent | **Verified** |
| Recharts already present; no new chart dependency needed | `recharts ^3.8.1` in `extensions/mssql/package.json`, alongside `@fluentui/react-components ^9.72.3`, `@tanstack/react-virtual`, SlickGrid (ADS fork) + `slickgrid-react` | **Verified** |
| Query Studio owns sibling Results/Messages/Query Plan tabs, splitter, maximize, fill-mode layout | `app.tsx` (~2,056 lines) owns tab state, `resultsPaneMaximized`, `maximizedGridId`, sizing-v2 fill mode; `queryStudio.css` implements the shell | **Verified** |

### 2.3 The house style, from the branch itself

`webviews/pages/QueryStudio/queryStudio.css` opens with a design contract worth quoting because it settles the mockup argument by fiat:

> Query Studio — M0 shell densities (doc 01 §3/§7): toolbar 35px, status 24px, 2px radii max, VS Code tokens only, no ornamental chrome.

Measured constants from the same file: results tab strip 30 px with 24 px text-only tabs (active = 2 px bottom border in `--vscode-focusBorder`), 4 px splitters that light up as `focusBorder` on hover, 26 px toolbar buttons at radius 2, 24 px status bar with segmented items, and a fill-mode rule that the grid's virtualized scrollbar is *the* scrollbar ("issue A" — the pane itself never scrolls when one grid fills it). The grid surface is FluentResultGrid over SlickGrid.

This is the yardstick for §6 and for `ux_revisions.md`: the Vector pane is a *sibling* of these surfaces and must read as one.

---

## 3. External API verification ledger (state of the SQL surface, July 2026)

The plan's capability model anticipated a moving target and it has indeed moved. Everything below is from current Microsoft Learn pages and Azure SQL Dev Corner posts; the plan's architecture absorbs all of it through the existing `VectorDatabaseCapabilities` probe — no structural change needed, but several probes and findings should be added (§4.2).

| Area | Current state | Plan alignment |
| --- | --- | --- |
| GA vs preview split | SQL Server 2025 GA'd 2025-11-18 (CU1 2026-01-15). GA everywhere: `vector` type (float32), `VECTOR_DISTANCE`, `VECTORPROPERTY`. Still preview on box behind `PREVIEW_FEATURES = ON`: float16 base type, `VECTOR_SEARCH`, `CREATE VECTOR INDEX`, `AI_GENERATE_EMBEDDINGS`. | Matches the plan's "preview features … vary" stance and the `previewFeaturesEnabled` probe. |
| Latest DiskANN format | Announced 2026-03-18 for Azure SQL Database and Fabric SQL database (regional rollout): full DML support (no read-only tables, no `ALLOW_STALE_VECTOR_INDEX` needed), iterative filtering (WHERE applied during graph traversal), optimizer-driven ANN-vs-kNN choice, transparent quantization improvements. Box SQL Server 2025 retains earlier semantics as of this review. | The plan's `vectorSearch: unavailable \| legacy \| latest \| mixed` and index-version gating anticipated exactly this divergence. **Gap:** legacy filtered-comparison semantics (A1). |
| Latest syntax | `SELECT TOP (N) WITH APPROXIMATE … FROM VECTOR_SEARCH(TABLE=…, COLUMN=…, SIMILAR_TO=…, METRIC=…) [AS alias] [WHERE predicate] ORDER BY distance` — required for latest-version indexes. Legacy `TOP_N` parameter only for earlier-version indexes. | Plan's §20.3/§20.5 templates match, including the WHERE placement after the TVF alias (which is the iterative-filter position on latest indexes). |
| Forced ANN | `FORCE_ANN_ONLY` documented as a table hint that forces the ANN index path; otherwise the optimizer chooses ANN vs kNN. | Plan's evidence taxonomy is correct: forced-ANN success is proof; approximate syntax alone is not, because the optimizer may legitimately pick kNN. Exact hint placement should be a Phase 0 probe row (A8). |
| Index version detection | Documented pattern: `JSON_VALUE(v.build_parameters, '$.Version') >= '3'` ⇒ latest; below ⇒ migration recommended. Earlier indexes cannot upgrade in place; drop + recreate, and dropping immediately disables approximate search on the table until recreation. | Plan's "parsed version below 3 ⇒ earlier format, offer migration script" is exactly the documented rule. Add the service-impact wording to the generated migration script comments (A3). |
| Index health DMV | `sys.dm_db_vector_indexes` exposes `approximate_staleness_percent` and `last_background_task_succeeded`. Documented interpretation: 0–5% normal steady-state; 20–30% during batch loads is expected and self-draining; sustained >10–15% during regular operations warrants investigation; rebuild on recall degradation, not on staleness alone. Rows remain queryable while stale; ranking quality degrades. The DMV's *existence* is itself a probe for the new format (`SELECT OBJECT_ID('sys.dm_db_vector_indexes')`). | The plan/spec's staleness wording ("Review sustained staleness … never unconditional rebuild") mirrors the docs almost verbatim. Fold the numeric bands into the finding tooltip, clearly attributed to documentation guidance (A3). |
| Index prerequisites/constraints | Primary key clustered index required (preview-era guidance: single-column integer PK); ≥100 non-null rows required for latest-version index creation; no partitioning; not replicated to subscribers; `TRUNCATE TABLE` blocked while a vector index exists (drop → truncate → repopulate ≥100 rows → recreate); DiskANN gated to Standard/Enterprise editions per current docs. | Plan's §23.3 already has the clustered-PK and <100-row findings. Add TRUNCATE/replication/partitioning/edition rows (A3). |
| Embedding functions | `AI_GENERATE_EMBEDDINGS` + `CREATE EXTERNAL MODEL` announced **GA in Azure SQL** (May 2026); preview on box. `API_FORMAT ∈ {Azure OpenAI, OpenAI, Ollama, ONNX Runtime}`; `MODEL_TYPE` currently `EMBEDDINGS` only; `LOCAL_RUNTIME_PATH` for ONNX; built-in retry; `PARAMETERS` JSON with per-call override. Box/MI prerequisites: `sp_configure 'external rest endpoint enabled', 1` for REST formats; `'external AI runtimes enabled', 1` for ONNX. Not needed on Azure SQL DB. | Plan's Pipeline design holds. **Gaps:** egress classification per API_FORMAT (A4) and config-gate probes/scripts (A3, F8). |
| float16 | Preview; 16-bit base type supports up to ~3,998 dimensions per current docs. Driver transport remains JSON-text fallback. | Plan's float16 text-fallback policy remains correct and appropriately conservative. |

---

## 4. Implementation plan review

### 4.1 Strengths (kept short deliberately)

The plan does five hard things right that most feature plans get wrong: it fixes the capture-privacy hole *before* adding richer payloads; it refuses a second raw-result cache and a feature-private query protocol; it makes budgets host-authoritative and webview-unraisable; it separates requested mode from proven strategy in ANN evidence; and it sequences PRs so a non-UI test client can exercise the whole analysis stack (PR 6 exit) before any pixel ships. The prohibited-shortcuts list (§37.2) reads like it was written by someone who has watched an agent take every one of those shortcuts. Keep all of it.

The initial budgets are also internally coherent, which I checked rather than assumed: 8,000,000 components ÷ 1,536 dims = 5,208 rows ≥ the 5,000-row sample cap, so the component budget binds only above ~1,600 dims (at 1,998 dims the effective sample is 4,004 rows — correctly surfaced by the "minimum implied by every limit" rule). The 64 MiB packed-input budget (10,922 rows at 1,536 dims) is not the binding constraint. These numbers hang together.

### 4.2 Required and recommended amendments

**A1 (P0, correctness of the flagship). Legacy-index filtered comparisons must model post-filter semantics.**
On earlier-version indexes, predicates are applied *after* the approximate search, and documentation explicitly describes manual `TOP_N` oversizing to compensate. The plan's legacy template (§20.5) has no filter, and §20.6 structured predicates compose into a single WHERE that means different things on latest (iterative, during traversal) vs legacy (post-filter over an already-truncated candidate set). Consequences on legacy: a selective filter can return far fewer than K rows, and "recall@K vs exact" silently becomes "recall of a post-filtered truncated set," which is precisely the kind of untruth the plan elsewhere goes to war against. Required behavior: (a) when index version < 3 and structured filters are present, either disable the approximate variant in automated comparison with an explanation, or run it with an explicit, disclosed `TOP_N = K × M` oversample (M host-configured, shown in the generated SQL and the evidence panel); (b) add an evidence row for filter semantics — `Iterative filtering (during traversal)` vs `Post-filtered after approximate retrieval (TOP_N oversampled ×M)`; (c) add SQL-builder and comparison tests for the legacy+filter matrix. This also becomes a first-class UX element (U8/F4).

**A2 (P0, already planned — quantifying it). Page/frame math endorsement with an interim clamp.**
Concrete numbers against verified `Sts2Defaults`: one 1,536-dim float32 cell is 6,144 raw bytes → 8,192 base64 chars; a 1,000-row page of one such column is ~8.2 MB against a 256 KiB page target (~32×); at the 1,998-dim maximum it's ~10.7 MB (~42×). The 64 MiB frame ceiling is reachable with multi-vector-column selects at default page rows. So the plan's frame guard is not paranoia, it's arithmetic. Endorse the exact-encoded repacker as the platform fix; as the pragmatic interim inside PR 3, clamp rows-per-page when the vector type hint is present (`rowsPerPage = clamp(pageTargetBytes / conservativeEncodedRowBytes, 1, PageRows)`) so typed vectors never rely on the generic provider-object estimator even before the repacker lands.

**A3 (P1). Extend the capability probe and Index findings with the 2026 surface.**
Add to `VectorDatabaseCapabilities` / catalog service: `externalRestEndpointEnabled` (box/MI), `externalAiRuntimesEnabled` (ONNX), latest-format signal via `OBJECT_ID('sys.dm_db_vector_indexes')` presence in addition to index-version parsing, and edition gating where detectable. Add Index-workspace findings: TRUNCATE blocked while index exists (with the documented drop→truncate→repopulate→recreate sequence in the generated script), not replicated to subscribers, no partitioning, and the migration script's service-impact comment ("dropping immediately disables approximate search until recreation — plan a maintenance window"). Fold the documented staleness bands (0–5% steady state; 20–30% during loads normal; sustained >10–15% investigate) into the staleness finding's method tooltip, attributed to documentation rather than presented as the tool's own judgment — consistent with the spec's "no universal threshold claim" rule because the bands are cited guidance, not an unconditional verdict.

**A4 (P1). Egress classification per model API format.**
`API_FORMAT` now spans a real egress spectrum: `ONNX Runtime` executes in-process on the SQL Server host (no network egress); `Ollama` is typically a host-local endpoint (loopback egress, but still leaves the database engine process); `OpenAI`/`Azure OpenAI` are external egress. The confirmation dialog (§21.2 of the UX spec) currently has one register. It should have three, driven by catalog facts: the "Execution" line reads `Local ONNX runtime on the SQL Server host — no network egress`, `Host-local endpoint (localhost) — text leaves the database engine`, or `SQL Server calls the external endpoint <host> — text leaves your environment`. Same friction level, different truthful copy. The capability popover should show `API format` per model. No architectural change; this is copy plus one metadata field already visible in `sys.external_models`.

**A5 (P1). Stamp search evidence with index staleness at measurement time.**
Recall is a function of the graph state. A comparison run during a batch load (25% staleness) will report worse recall than the same index an hour later, and a DBA will chase a ghost. In the same diagnostic session, immediately before the variant runs, read `approximate_staleness_percent` for the bound index (when the DMV and permissions allow) and attach it to `VectorSearchComparisonResult` evidence: `Recall@20 90% — measured at 12.3% index staleness`. Cost: one DMV query per comparison. This single line connects the Index and Search workspaces and preempts the most likely "the index is broken" misdiagnosis. Degrades gracefully to absent when the DMV is unavailable.

**A6 (P2). Make the scan-side byte cost explicit, not just the packed-sample cost.**
Budgets bound packed input (64 MiB) and rows scanned (25,000), but the scan itself decodes base64 pages: 25,000 rows × 1,536 dims is ~154 MB raw / ~205 MB base64 traversed in the worst case, with spill rereads bounded by sparse projection. Add a disclosed scan-bytes budget (or derive and display it) so the Profile scope popover can say what the scan cost, and so perftest can assert it. This is a small contract addition to `VectorSampleDescriptor`/probe counters, not a behavior change.

**A7 (P2). Expose the third eigenvalue you're already computing.**
The covariance-free PCA runs with a 3-component working subspace and eigendecomposes a 3×3 B. PC3's explained variance is therefore free. Report it in `VectorProjectionSummary` and render it in the truth banner as a truncation signal: `PC1 18.4%, PC2 9.7%, next component 8.9% (not shown)`. When PC3 ≈ PC2, the 2-D layout is known-lossy in a way users should see; when PC3 ≪ PC2, the projection earned more trust. One number, real epistemic value, zero added compute.

**A8 (P2). Add hint-placement and syntax rows to the Phase 0 probe matrix.**
The plan gates everything on runtime probes (correct), but the matrix should explicitly include: `FORCE_ANN_ONLY` placement/grammar on the target, `WITH APPROXIMATE` acceptance, and legacy `TOP_N` rejection on version-3 indexes, so the SQL builder's template selection is evidence-backed per target rather than doc-backed. The plan's spirit already says this ("syntax probe"); make the rows explicit so an agent can't skip them.

**A9 (P2). Guard Pipeline copy against `MODEL_TYPE` expansion.**
`MODEL_TYPE` currently permits only `EMBEDDINGS`, and the required-single-value shape strongly suggests future types. The model selector and confirmation copy should filter on `MODEL_TYPE = EMBEDDINGS` explicitly rather than assuming all external models are embedders, so a future `COMPLETIONS`-style object appearing in `sys.external_models` degrades to "unsupported model type" instead of a wrong offer.

**A10 (endorsements, recorded so nobody relitigates them).**
Uniform-window sampling over silent reservoir sampling: right call for spill-bounded I/O and disclosed method. Covariance-free subspace iteration with deterministic sign normalization: right call at 1,998 dims (an explicit d×d covariance would be ~16 MB and pointless; the ban in §37.2 is correct). `data` not `v` in the wire tag: verified collision risk with `TruncatedCellEncoding` (§2.2). No new chart/math dependency in MVP: Recharts + a small audited numeric module is the right supply-chain posture; revisit only via the §13.4 spike gates. Isolated auxiliary session with isolation disclosure rather than borrowing the user session: right call, and the pre-run disclosure of an open user transaction (§12.5 of the spec) is a genuinely thoughtful touch.

### 4.3 PR plan notes

Sequencing is correct and the exit criteria are testable. Two small suggestions: (1) split the PR 3 provider/RID matrix into an evidence-only PR 3a (fixtures + recorded matrix, no product change) so the metadata rules freeze on committed evidence rather than a PR description; (2) A1's legacy-filter semantics belongs in PR 10's test matrix explicitly — add it to the §31.8 list now so it can't be discovered post-preview.

---

## 5. UX specification review

### 5.1 Strengths

The five-truths framing (§1), the capability ladder with a facts-not-marketing popover (§6.3), evidence labels that refuse the green check for unproven ANN (§12.10), honest-partial wording with denominators (§18.2), the preferred/avoid terminology table (§23.2), and a complete nonvisual workflow (§19.1) — this is the best-specified diagnostic-truthfulness UX I've reviewed in this codebase's orbit. The binding wizard's "the tool must not pretend it can reconstruct a base-table search from a cell" stance (§10.1) is the correct answer to a temptation every competitor yields to.

### 5.2 Amendments

**U1. Retire the "summary cards" idiom; specify a facts strip.** §11.2/§11.3 asks for four summary cards, and the mock dutifully produced a KPI dashboard row. The same facts belong in one dense line of `label value` segments under the header (or as status-bar segments), monospace values, no containers. Cards should not exist anywhere in this pane. (Full component rules in `ux_revisions.md`.)

**U2. Tables are grids, not styled divs.** Rank comparison (§12.7), findings rows (§11.5), the accessible point list (§14.8), and Index/DMV values should be specified as real data grids with the FluentResultGrid look: ~24 px rows, resizable/sortable columns where meaningful, right-aligned monospace numerics, virtualization, keyboard model, and the same selection/copy semantics users already have in Results. Reusing (or visually cloning) the existing grid is both a vibe fix and a functionality fix — a DBA will immediately try to sort the rank table by Δ and copy a range; give them the grid they already know. DMV/catalog facts in Index use a two-column properties grid, not cards.

**U3. Extend the "issue A" single-scrollbar rule to Vector.** Workspaces should be specified as fixed layouts whose *inner regions* scroll (grids, lists, SQL view), matching `qs-results-body-fill`. A page-level vertical scroll is acceptable only for Profile's stacked narrow mode. No max-width; the pane fills the results body like every sibling tab.

**U4. Make §20.1 numeric.** "Compact, information-dense" invited interpretation; the branch already defines the numbers. Adopt as normative: base 13 px / controls 12 px, radius ≤ 2 px, 26 px buttons, 30 px tab strip with 24 px text-only tabs, 24 px status bar, 4 px splitters, grid rows ~24 px, `--vscode-editor-font-family` for all numerics, VS Code tokens only, shadows only on menus/dialogs.

**U5. Kill decorative interrogatives in chrome.** The workspace-purpose questions ("Do the stored vectors look structurally healthy?") are excellent *specification* prose and good *empty-state* copy; they should not render as permanent subtitles next to headings. Chrome states facts; empty states teach.

**U6. Rail items are one line.** Icon + label at 22–24 px; no sub-captions; the lock glyph for gated workspaces stays. The evidence legend does not live in navigation — it moves into the evidence panel or a status-bar popover where it has context.

**U7. Scope/method live once.** The spec puts scope in both the header badge and the footer; keep the header badge as the *interactive* owner (opens details) and make the footer the passive summary, and delete per-panel scope chips — the mock stamped "Sampled" chips on every panel header, which is repetition noise. One authoritative badge, one status segment.

**U8. Add the filter-semantics evidence row** (from A1) to §12.10's table: iterative vs post-filtered, with the oversample multiplier when applicable.

**U9. Reserve a Search slot for the self-recall harness** (F1) so its later arrival doesn't force a composer redesign: a third run mode alongside single-comparison — `Query set: this vector / N sampled rows`.

**U10. Add a density gate to the mockup package (§24):** every screen also rendered at 1280×720, and the v2 acceptance check in `ux_revisions.md` §9 applies.

---

## 6. v1 mockup review — the diagnosis

What v1 got right, and should be carried forward without relitigating: correct VS Code token usage in dark/light/HC with a theme switcher; codicons throughout; a real status bar with the no-network assertion; the capability popover rendered as a facts table ("Facts probed from the connection, not marketing labels" — keep that sentence forever); the model-call confirmation dialog content; honest microcopy nearly everywhere; zero gradients and only four shadows in the whole document. This mock is *not* the neon-glow embedding-projector failure mode. Credit where due.

Why it still reads as PowerBI-in-a-VS-Code-costume — seven compositional tells, all measured from the decoded markup:

1. **KPI card row.** Four cards with 20 px display numerals opening Profile. That is the signature move of a BI dashboard; no VS Code or SSMS surface leads with hero numbers.
2. **Panel-cards with chrome.** Every section is a bordered card at radius 6 with a tinted header bar, and nearly every header carries 1–2 pill chips. The house rule is radius ≤ 2 and hierarchy from rules/labels, not containers.
3. **Pill chips as a primary vocabulary.** 9–10 px text inside 9 px-radius pills, dozens of instances. Chips are marketing-site texture; the native vocabulary is codicon + plain text in a severity foreground color.
4. **Centered page composition.** `max-width: 1180px` content column that scrolls vertically per workspace — a web page, not a tool pane. Siblings fill the pane and scroll internally.
5. **Marketing-register microcopy in chrome.** Question subtitles under every h2, "the target you search against," "exactly what executed" as a header garnish.
6. **Website-sidebar navigation.** Two-line rail items with 10 px sub-captions, plus a legend block living in the nav.
7. **Bespoke div-tables.** The rank comparison — the flagship's flagship — is a styled grid with uppercase letter-spaced headers rather than a sortable, resizable, selectable data grid.

None of these are token errors, which is why the mock survives a color-picker inspection while failing the squint test. The fix is a composition pass, fully specified in `ux_revisions.md`. The information architecture (workspaces, header, popovers, dialogs, states) transfers as-is.

---

## 7. High-value additions — what would make this exceptional for professionals

Ordered by leverage per unit of new machinery. F4 is really A1 wearing its UX hat; it's listed here because it's also the single highest-value *visible* feature. None of these violate the plan's boundaries (no DDL execution, no unconfirmed model calls, no webview network, budgets host-owned).

**F1 (P1, fast-follow after PR 10). Self-recall harness — the "is my index any good" number.**
Leave-one-out evaluation using only data already in the table: sample N bound rows (reusing the deterministic sampler), use each row's own vector as the query, run exact and approximate top-K per query on the diagnostic session, and report the recall@K *distribution* (median, p5, worst offenders with keys) instead of a single anecdote. Cost model is explicit and confirmable up front: 2N bounded queries (N default 20–50, hard-capped), sequential, cancellable between commands — the same friction shape as the drift sample. This turns the Search debugger from "debug this one query" into "characterize this index," which is the question a DBA actually gets asked. It also composes with A5: recall distribution stamped with staleness. No new architecture — it's a loop over the existing `VectorSearchComparisonSpec` with an aggregate result contract.

**F2 (P1, cheap). K-sweep recall curve.**
Run exact once at K_max; approximate at K ∈ {10, 20, 50, 100} (bounded set); compute recall@K against prefixes of the single exact result; plot recall and wall time vs K with the existing Recharts budget. Answers "what K do I need for the recall I want and what does it cost" in one run. Exact cost: one exact query + |K set| approximate queries. Pairs naturally with F1 (sweep over the query set median).

**F3 (P1). Staleness-stamped evidence** — specified as A5; listed here because it should appear in the Search results UI as one evidence line, not buried in Index.

**F4 (P0-with-PR10). Filter-semantics evidence row** — specified as A1(b). The production incident this prevents ("my filtered vector search returns 3 rows") is common enough that this line alone will justify the pane to a support engineer.

**F5 (P2, promote from deferred). Local float16 quantization impact lab.**
Currently on the deferred list, but note it needs *zero* server support: round-trip the sampled float32 matrix through IEEE 754 half precision in the worker, recompute the top-K neighbor lists for a set of probe rows in both precisions, and report rank churn and distance deltas. Answers "can I halve my storage" with the user's own vectors before they touch the preview float16 type. Pure worker math on data already in budget; the honest label writes itself (`Simulated float16 round-trip; server behavior may differ`). Recommend pulling it forward once PR 8's worker infrastructure exists.

**F6 (P2). Per-dimension contribution explainer.**
For a selected query/result pair under dot or cosine, show the top contributing dimensions (largest aᵢ·bᵢ terms, signed) next to the existing top-|Δ| view in Compare. Local math on two vectors already in panel memory. This is the "why did this row rank here" affordance that makes the tool feel like a debugger rather than a report, and it slots into the existing result-details inspector.

**F7 (P1, tiny). Bundled repro script.**
One action on a completed comparison: emit a single commented `.sql` containing the capability check, the exact/approximate/forced variants exactly as executed, the index-version verification query, and the health query, with a header stating target, assumptions, and generation provenance — opened in an editor, never persisted. The per-variant SQL drawer already exists; this is concatenation plus comments, and it's how a finding travels from the pane into a ticket, a PR description, or a colleague's SSMS session. Very high pro-user affinity per line of code.

**F8 (P1, small). Configuration-gate scripts, generated never executed.**
When probes report a gate closed, the explanation should end with `View generated check` (already specced) *and* `Generate enablement script for review`: `PREVIEW_FEATURES` database-scoped config, `external rest endpoint enabled`, `external AI runtimes enabled` — each with permission requirements and scope-of-effect comments. Same never-execute discipline as index DDL. This converts every dead-end state on box SQL Server into a forward path.

**F9 (research gate, keep deferred). Index footprint and memory.**
Vector index storage/memory characterization (allocation units, any future DMV columns) is worth a gate entry alongside the existing #9 (historical health), but the surface isn't stable enough to spec today.

Explicitly *not* recommended for MVP+1, despite temptation: UMAP/t-SNE (the deferred-list reasoning stands; PCA + original-space neighbors covers the diagnostic need), any automatic index or rebuild action (would burn the trust the evidence model builds), and a chat/NL layer in this pane (Query Studio has other surfaces for that; this pane's brand is determinism).

---

## 8. Direct answers to your questions

**"Is the plan right?"** Yes, with §4.2 folded in. I tried to break its branch inventory and could not — every claim I checked was true at today's commits, including the two uncomfortable ones (compact capture leaks; no CSP). The one substantive semantic gap is A1; everything else is extension, not correction.

**"Is what I have already the best UX possible?"** The *architecture* of the UX — workspaces, capability ladder, evidence model, truth labels, binding wizard, confirmation flow — is genuinely strong and I would not churn it. The *visual execution* is not there yet, and the gap is diagnosable and mechanical: v1 composed a dashboard out of correct materials. The house style is already written down in your own CSS ("2px radii max … no ornamental chrome"); v2 needs to obey it. Hand the design agent `ux_revisions.md` with the v1 mock and the UX spec; the revision list is specific enough that a competent pass should land within one iteration, two at most. The acceptance checklist at the end of that file is the arbiter — particularly the 1280×720 density test and the "would this component look at home in PowerBI" veto.

**"What would really be amazing?"** F1 + F2 + F4 + F7. A tool that can say "this index delivers median recall@20 of 0.94 at 11 ms, measured across 50 sampled queries at 3% staleness, iterative filtering confirmed — here's the repro script" is a tool no other SQL surface offers today, and every piece of that sentence is already within this plan's architecture.

---

## 9. Sources

Branch code: `microsoft/vscode-mssql@205bbb98f4e21d551fbb4d9724301ca77cce7bd0`, `microsoft/sqltoolsservice@d9aca04ec8293e36e19861f781ac609dde4f0fe2` (both `dev/query`, cloned 2026-07-10).

Documentation and posts consulted 2026-07-10: Microsoft Learn — CREATE VECTOR INDEX, VECTOR_SEARCH, Vector search and vector indexes, sys.dm_db_vector_indexes, CREATE EXTERNAL MODEL, AI_GENERATE_EMBEDDINGS (all `view=sql-server-ver17`); Azure SQL Dev Corner — "DiskANN Vector Index Improvements" (2026-03-18), "Generate Embeddings Function and External Model Object Support Are Now Generally Available in Azure SQL" (2026-05), "SQL Server 2025 Embraces Vectors" (2025-11-18); plus practitioner state-of-the-release coverage (SQLServerCentral, sqlfingers, dbi-services, Simple Talk) for GA/preview boundaries and box-vs-cloud divergence.
