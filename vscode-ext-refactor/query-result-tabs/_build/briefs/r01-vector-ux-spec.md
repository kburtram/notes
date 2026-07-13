# R01 Brief — Vector Workbench UX Spec (base spec + v2 revisions)

**Sources (read completely):**
- Base spec: `C:/repos/test/coding-docs/query-result-tabs/query_studio_vector_workbench_ux_spec.md` (cited below as `spec:LINE`)
- Revisions: `C:/repos/test/coding-docs/query-result-tabs/vector_ux_revisions.md` (cited as `rev:LINE`)

**Precedence rules (verbatim intent):**
- Revisions override the base spec and the v1 mockup **only on visual language and composition**; the base spec "remains normative for behavior, states, copy rules, and accessibility" (rev:5). Where the revisions doc is silent, keep v1's choice (rev:5).
- The companion implementation doc `query_studio_vector_workbench_implementation_plan.md` is normative for data contracts, service ownership, **budgets**, SQL generation, security, and code sequencing; where a visual idea conflicts with a technical safety/truthfulness rule there, the implementation rule wins (spec:15). That doc was NOT among this brief's sources — numeric perf budgets beyond what is listed in §16 below must come from it.
- The pane must follow the result-pane architecture/quality bar of the existing geospatial docs: `geospatial_pane(1).md`, `geospatial_pane_execution_addendum(1).md` (spec:17-21).
- Target branches: `microsoft/vscode-mssql@dev/query`, `microsoft/sqltoolsservice@dev/query` (spec:5). Visible tab label: `Vector`; pane product name: `Vector Workbench` (spec:7-8).

Every place where the revisions doc overrides the base spec is flagged **[OVERRIDE Rn]** inline.

**2026-07-12 implementation reconciliation:** explicit user decisions in `_build/EXECUTION_PLAN.md` override this distilled brief where its original line references describe the old tab order, text-fallback eligibility, or incomplete state lifetime. The synchronized rules are recorded below.

---

## 1. Product shape — six workspaces (not ten)

The pane has exactly **six task-oriented workspaces** (spec:26-33), navigated by a left rail (wide layout):

1. **Profile** — is stored vector data structurally healthy? (default workspace, spec:35)
2. **Search** — exact vs optimizer-selected vs forced-approximate retrieval; the flagship workflow (spec:77-79).
3. **Compare** — selected vectors, pairwise distances, neighbors, experimental arithmetic.
4. **Projection** — deterministic PCA 2D only in MVP (spec:790).
5. **Index** — DiskANN metadata, version, maintenance, compatibility, generated repair scripts.
6. **Pipeline** — provenance, chunking, re-embedding, drift via explicit model calls.

There are **no** separate "sample", "model", "findings", or "regen" workspaces: sampling is a cross-cutting scope concept (§9 here), Findings is a panel inside Profile (spec:474-496), model calls are a confirmed operation used by Search/Pipeline (spec:1166-1187), and re-embed ("regen") is a Pipeline flow (spec:966-985).

Default workspace is **Profile, not Projection** (spec:35, spec:1276). Five kinds of truth must stay visually distinct: captured-result facts, catalog/DMV facts, newly executed diagnostic SQL, locally computed bounded-sample results, and inferred interpretations/warnings (spec:39-45).

Non-goals for v1 (spec:98-111): no in-place vector editing/write-back, no notebook/chat, no auto cluster labels, no automatic index DDL execution, no automatic model calls (on open, selection change, or profile load), no UMAP/t-SNE/3D/animation/GPU effects, no inferring JSON arrays are vectors without explicit action, no single "similarity %" badge, no claiming ANN without evidence, no silent normalize/sample/filter/quantize/repair/exclude, **no result data in telemetry/diagnostics/perf markers/web services** (spec:111, spec:1163).

## 2. Activation rules — when the Vector tab appears

For the initial preview, show the tab only when the feature setting was enabled before execution, STS2 negotiated the typed contract, and a terminal **non-plan result set** contains a native `binary-v1` `float32` vector column retained for analysis. Text fallback remains in Results until a real limited-mode/binding experience exists; never show a tab whose only action is a rerun warning.

Never show the tab just because a string contains a JSON array. Tab order when eligible: `Results | Messages | Vector | Query Plan`. Results is the only tab before Messages; all contributed tabs follow it. Rules:
- Vector **never auto-opens**; existing error→Messages and plan→Query Plan auto-switches unchanged.
- If the selected result disappears after rerun, fall back to first eligible result, else Results.
- Pinned result documents reuse the same tab/component with database-aware actions disabled until explicitly re-bound to a live connection+table.

**Entry points** (spec:235-246): cell context menu `Inspect in Vector Workbench`; multi-cell/row selection `Compare in Vector Workbench` (seeds Compare basket); column header `Open Vector Workbench`; result-grid caption vector icon button; Results tab overflow `Open Vector Workbench`; later milestone: Object Explorer table context `Open Vector Workbench for column`. Opening from a cell preselects result set + vector column + result-row ordinal; opening from the tab restores last valid panel-local workspace (spec:246).

**Sizing** (spec:248-252): fills the results body, participates in existing splitter/maximize; it is NOT a third Grid/Text display mode. Must remain usable at minimum content height **240 CSS px**; below that, secondary inspectors collapse into drawers and charts show a compact state.

## 3. Capability ladder

Badge near title + info popover (spec:185-216):

| Level | Badge | Experience |
| --- | --- | --- |
| A | `Typed result` | Full detached Profile/Compare/PCA for float32 cells |
| B | `Vector text fallback` | Future limited mode; initial preview keeps ordinary inspection in Results until verified binding/conversion UX exists |
| C | `Table bound` | Search, Index, server-side vector math per runtime probes + permissions |
| D | `Model enabled` | Explicit embedding, chunking, re-embedding, drift |
| E | `Limited permissions` | Show available metadata + precise permission explanation; NOT a whole-pane error |

Capability popover is a plain facts table (spec:200-216) listing: transport (`Native float32 binary`), dimensions (`1,536`), base type, binding (`dbo.DocumentChunks.embedding`), exact distance, approximate search (`Available, preview`), vector index (`vec_DocumentChunks_embedding, version 3`), index health DMV permission, embedding model (`dbo.TextEmbedding3Small`), chunk generation, diagnostic session (`Isolated connection`). Unavailable entries carry a concise reason + `View generated check` action (spec:216). Revisions keep-list preserves the popover as a plain facts table including the line "Facts probed from the connection, not marketing labels" (rev:18).

## 4. Layout and navigation

### Wide layout (≥ 960 CSS px), spec:256-278
ASCII frame at spec:258-273: results tab strip → workbench header (`Vector Workbench [Result 1] [embedding] [Table bound] [Sample: 5,000] [...]`) → left workspace rail + main content + optional right inspector → one-line footer status.
- Rail: base spec says 156–184 px, resizable only if pane conventions support it (spec:275). **[OVERRIDE R8]** rev:58: rail ~**160 px**, items **22–24 px**, single-line codicon + label, active = `list-active-selection` background, gated workspaces show a lock codicon at right; **no 10 px sub-captions, no "Evidence legend" block in the rail** (evidence explained where evidence appears or in a status-bar popover).
- Main content: fluid. Optional right inspector: 320–400 px, resizable, dismissible (spec:277).
- Footer status: one line with overflow into details popover (spec:278). Revisions: **24 px status bar**, segmented items separated by hairlines, carries scope summary + `No network requests` assertion (rev:19, rev:35).

### Medium layout (640–959 px), spec:280-286
Rail → top segmented nav or compact tab row; inspector → right overlay drawer; summary cards reflow 4→2 columns (**[OVERRIDE R1]** cards are gone; the facts strip replaces them — see §7); Search comparison → tabbed Exact/Approximate list + persistent comparison summary.

### Narrow layout (< 640 px), spec:288-294
Workspace choice becomes labeled dropdown `Workspace: Search`; global selectors stack in two rows; every chart immediately followed by its accessible data table; search variants stack as vertical cards; Projection canvas stays ≥ **240 px** high and never hides the feature list; **no horizontal page scrolling** — tables scroll within their own labeled regions.

### Global header controls (spec:296-306)
| Control | Default | Notes |
| --- | --- | --- |
| Result set | first eligible | ordinal, row count, complete/partial status |
| Vector column | first eligible | dimensions + base type when known |
| Binding badge | `Detached` | opens binding summary or wizard |
| Scope badge | `Sample` or `Full` | opens scope details; never labels a partial scan as full |
| Workspace overflow | hidden on wide | reset workspace, copy diagnostics summary, help |

Header contains no per-workspace analysis settings (spec:306). **[OVERRIDE R3 exception]** binding/scope badges are interactive buttons and may keep a 1 px border at radius 2, styled like `qs-btn`, not like tags (rev:48). **[OVERRIDE R9]** scope is stated **exactly twice**: header badge (interactive) + status bar (passive); all per-panel `Sampled`/`Local` chips are deleted (rev:60, rev:118).

**[OVERRIDE R4]** No `max-width` anywhere; each workspace is a fixed layout filling the results body; **inner regions scroll, the page does not** (grids/lists/SQL view own their scrollbars, mirroring Query Studio's fill-mode rule where one grid's virtualized scrollbar is *the* scrollbar). Sole exception: Profile may vertically stack-and-scroll in the narrow (<640 px) layout (rev:50).

## 5. State and persistence (spec:308-338)

Panel-local state is versioned, bounded, controller-memory-only, and restored across sibling-tab switches and renderer/webview recreation while the run remains valid. It covers shell and Results/Messages/Query Plan context plus active Vector workspace; selected result/column/ordinals; Compare basket and safe arithmetic state; Projection camera/color/lasso/list/inspector state; safe Search composition; and Index/Pipeline view preferences. It never stores selected text, pasted vectors, model source text, result keys/labels, query vectors, projection points, confirmation tokens, model results, or result-derived generated SQL in diagnostics, replay, telemetry, settings, or durable mementos.

A new run invalidates (spec:322-330): result-row selections, detached analysis results, projections, result-derived query vectors, result-bound binding verification. A saved provenance profile may be re-offered but must be reverified against current database + column metadata (spec:332).

Local provenance persistence (spec:334-338): binding + provenance profile can be saved locally; save dialog states that object/column names are stored locally; DB is not modified. **By default nothing else persists**: no source text, vector values, query vectors, model responses, projection points, or search-result keys.

## 6. Table binding (spec:340-422)

Detached tools always work on result data; **Search, Index, and most Pipeline actions require explicit table binding** (spec:346). The workbench never pretends it can reconstruct a base-table search from a vector cell alone (spec:344).

Entry points (spec:348-353): `Bind to table` button in the capability badge; locked Search/Index/Pipeline empty state; `Edit binding` in pane overflow; suggested-binding banner when result metadata has base-table lineage hints.

Wizard steps:
1. **Choose database object** (spec:357-369): connection (read-only), database, schema, base table, vector column. Only base tables are eligible for `VECTOR_SEARCH`; views selectable for detached metadata only, with that limitation shown. Lineage suggestions labeled `Suggested from result metadata`, must be confirmed; object verified in catalog before continuing.
2. **Identity & display** (spec:371-381): key column(s), label/display column, optional source-text column, optional group columns, optional embedding-generated timestamp column. PK columns preselected when visible. Nonunique identity → warning + reliable recall comparison disabled until corrected.
3. **Vector expectations** (spec:383-394): expected metric (cosine / euclidean / negative dot product), expected normalization (unknown / unit norm / not normalized), optional external model object, optional source expression description, optional chunk size+overlap, notes. Metric is a profile expectation, not a DB constraint — UI says so.
4. **Review & verify** (spec:396-411): FQ object + column, dims + base type from catalog, key uniqueness, compatible vector indexes + metrics, current permissions, model endpoint host or runtime type (no credentials), whether diagnostic session is isolated. Actions: `Save locally and bind`, `Bind for this panel only`, `Back`.

Binding badge states (spec:414-422): `Detached` (none) / `Binding available` (suggested, unverified) / `Table bound` (verified) / `Binding changed` (stale) / `Binding unavailable` (connection/permission/object failure).

## 7. Profile workspace (spec:424-535)

Answers "do vectors look structurally suspicious; where do I investigate first?" — must not claim semantic diagnosis from geometry (spec:428-430). **[OVERRIDE R7]** that question copy moves from chrome subtitle into the workspace **empty state** verbatim; heading is the bare word `Profile` (rev:56).

**Summary cards (spec:449-458) → [OVERRIDE R1] facts strip:** the four cards (Rows observed / Dimensions / Base type / Availability) are replaced by a single-line facts strip directly under the header: `Rows 5,000 sampled of 2,412,883 · Dimensions 1,536 · float32 native · Null/unavailable 214` — labels in `--vscode-descriptionForeground`, values in monospace foreground, hairline-separated, warnings as inline codicon + warning-foreground word (no chip), total height ≤ **24 px** (rev:44). Base-spec card content values (e.g. `5,000 sampled of 2,412,883`, `12,450 full result`, `float32 native`, `float16 text fallback`) carry into the strip. Spec's rule that cards are buttons only when they open a filtered list (spec:461) becomes moot for the strip; interactivity lives in the scope badge (R9).

**[OVERRIDE R2 + per-workspace directive rev:70] layout:** two-column dense layout — left: Norms (histogram + norm selector as 3 small text-toggle buttons + stats grid) above Component variance (two compact ranked bar lists, dimension ids in 10 px mono); right: Findings as a data grid/list (severity codicon, factual title, count right-aligned mono, method in 10 px mono description text, chevron) above Sampled pair distances. Group comparison = data grid spanning the bottom. Row inspector = right-side drawer (data grid + detail fields). This supersedes the base ASCII layout at spec:434-449.

**Norm panel** (spec:463-472): norm selector L2 default / L1 / infinity; histogram bin count in overflow only; near-zero threshold with visible current value; optional expected unit-norm reference line. Displays median, p5, p95, min, max, count-near-zero. Never labels non-unit vectors wrong unless the provenance profile expects unit norm.

**Findings panel** (spec:474-496) — severity/evidence order: (1) unreadable or dimension-mismatched cells; (2) non-finite values; (3) exact-zero or near-zero vectors; (4) exact duplicate groups; (5) source-content conflicts (needs binding-provided source text/key evidence); (6) centroid-distance outliers; (7) low-variance/constant dimensions; (8) group distribution differences. Each finding: factual title, observed scope, count, method/threshold, `Inspect rows` action, optional `Why this matters` disclosure. Wording: `Possible stale or reused embeddings`, never `Your model pipeline is stale` (spec:496).

**Component variance** (spec:498-505): ten highest + ten lowest variance dimensions; display labels one-based (`Dimension 418`) while internal ordinals stay zero-based; details show mean, std dev, min, max, missing/non-finite counts.

**Distance sample** (spec:507-515): metric = binding expectation else cosine; deterministic pair-sample count; optional within/between group compare; distribution + median/p5/p95 + sample method; chart title `Sampled pair distances`, never `All pair distances`.

**Group comparison** (spec:517-524): cap visible groups, fold remainder into `Other`; show vector count, median norm, median within-group sampled distance, outlier rate, NN label agreement when computed; disclose null-group rows; never claim semantic coherence from projection alone.

**Row inspector** (spec:526-535): resizable, virtualized row list — result-row ordinal or table key, bounded label, norm, reason, centroid distance when applicable; actions `Reveal in Results`, `Add to Compare`, `Use as query vector`, `Open source details`.

## 8. Search workspace (spec:537-707)

Requires verified base-table binding + stable key (spec:543). Composer has four query-vector source tabs (spec:547-588): **Selected row** (ordinal/key, label, dims, base type, provenance match; choose among Compare basket entries; warns on dimension/profile mismatch), **Text with model** (verified external model objects selector; multiline text; optional model-parameters JSON behind advanced disclosure; `Generate embedding` opens the §21 model-call confirmation; generated vector cached only for the current panel, shown as a query-vector chip), **Paste vector** (JSON numeric array only; validates syntax/dims/finiteness/base-type conversion; bounded preview + normalized byte estimate; never accepts objects or nested arrays), **Expression** (Compare-basket vectors in a constrained editor — `normalize(A + B - C)`, `0.7 * A + 0.3 * B`, `centroid(A, B, C)`; locally parsed, never JavaScript `eval`; dims + profile validated; marked `Experimental vector arithmetic`).

**Settings defaults** (spec:590-598): Metric = binding expected metric (dot labeled `Negative dot product`); **K = 20** (1..approved max); Filter = none (structured builder, not arbitrary SQL); Variants = Exact + Approximate, Forced ANN opt-in when supported; Actual plan = **on** for debugger runs, can be disabled for faster iteration; Repetitions = 1 (advanced, capped; first run treated as warmup only when explicitly selected).

**Filter builder** (spec:600-610): AND-combined predicates over verified scalar columns — `=`, `<>`, `<`, `<=`, `>`, `>=`, `IN` (capped list), `IS NULL`, `IS NOT NULL`. Shows generated predicate + typed variables. `Open custom SQL experiment` moves editable SQL to an editor tab but removes it from automated recall comparison until rerun through a supported binding.

**Run** (spec:612-629): primary `Run comparison`; split secondaries `Run exact only`, `Run approximate only`, `Run forced ANN`, `Open generated T-SQL`. Pre-run the UI states: separate diagnostic connection; temp tables/uncommitted changes not visible; target db+table; whether an open transaction exists on the query session; whether a model call is part of query-vector generation. **[OVERRIDE per rev:72]** this pre-run disclosure is **one info line above the button**, not a panel.

**Comparison summary** (spec:631-647): example block — `Recall@20 90% (18 of 20 exact neighbors returned)`, `Top-20 overlap 18`, `Exact wall time 842 ms`, `Approx wall time 17 ms`, `Forced ANN Confirmed`, `Index vec_chunks_embedding, cosine, version 3`, `Scope Filter: category = @p0`. Every metric gets a tooltip with exact denominator + method. `Recall@K` = set overlap vs exact result; if fewer than K exact qualifying rows exist, denominator = exact count and is shown (spec:647). **[OVERRIDE per rev:72]** summary renders as a facts strip: `Recall@20 90% (18/20) · Overlap 18 · Exact 842 ms · Approx 17 ms`.

**Rank comparison table** (spec:649-663): columns exact rank, approx rank, rank change, table key, label, exact distance, approx distance, status (matched / exact-only / approximate-only), actions. Groupable by status; `Distance tie` indicator within approved tolerance; don't overstate rank movement under ties. **[OVERRIDE R5]** rendered as the existing Fluent result grid (SlickGrid look): 24 px rows, normal-case sortable/resizable headers, row-number gutter where useful, right-aligned monospace numerics at 6 significant digits, status as codicon + word (`$(pass) matched`, `$(arrow-down) −4`) (rev:52).

**Rank-flow view** (spec:665-667): optional lines exact→approx rank, modest K, shape+line-style not color alone, rank table always the equivalent representation. Revisions: an optional narrow companion column beside the rank grid (rev:72).

**Result details inspector** (spec:669-679): key+label; source text only on permission + request; exact/approx ranks+distances; filtered-or-absent status; norm + provenance summary; `Reveal in Results` (captured rows), `Fetch bound row` (table-only rows), `Add to Compare`.

**Execution evidence** (spec:681-694) — requested mode vs proven strategy: `ANN confirmed by FORCE_ANN_ONLY`; `ANN confirmed by execution plan` (approved plan signature); `Approximate requested, strategy unverified`; `Exact fallback` (warning or plan shows kNN fallback); `No compatible vector index`. Never a green check merely because `WITH APPROXIMATE` was present (spec:694). **[ADDITION rev:72]** evidence panel is a compact label/value block with codicon states and must include a **filter-semantics line** (`Iterative filtering` vs `Post-filtered, TOP_N ×5`) and a **staleness stamp** when available — neither is in the base spec; both are required (rev:120 checklist).

**Generated SQL drawer** (spec:696-707): read-only per-variant SQL with copy, open-in-editor, line wrapping, parameter declarations, capability/version comments, no hidden predicates. Part of the **primary** experience (spec:707); revisions keep drawer behavior, flatten chrome (rev:72).

## 9. Compare workspace (spec:709-784)

**Basket** (spec:713-720): holds up to the supported selection cap; entries labeled A, B, C… then by row/key; each shows source, dims, base type, norm, provenance profile; incompatible dimensions allowed in basket but disabled for joint ops with explanation. **[OVERRIDE per rev:74]** basket entries = 24 px list rows (mono key, label, dims, norm) with A/B/C prefix letters in badge-free mono.

**Two-vector comparison** (spec:722-734): cosine distance, Euclidean distance, negative dot product; L1/L2/infinity norms; top component differences by absolute delta; component-difference histogram; shared nearest neighbors when bound; neighbor rank comparison. **Never a "97% similar" badge** (spec:734). **[ADDITION rev:74]** metrics as a label/value grid; top-|Δ| dimensions **and the new contribution view** as compact ranked bar lists (contribution view is new in revisions).

**Pairwise matrix** (spec:736-743, 3+ vectors): metric selector; heatmap-like matrix **plus accessible table**; cell click opens two-vector comparison; diagonal clearly labeled zero or metric identity; matrix limit + partial state explicit. **[OVERRIDE per rev:74]** flat heat cells with 1 px gaps, mono values on hover/selection, accessible table adjacent.

**Selection summary** (spec:745-756): centroid, medoid, most isolated vector, closest pair, average pair distance, compatible/incompatible count; each with a method tooltip.

**Arithmetic lab** (spec:758-784): supports add/subtract, scalar multiply, weighted mean, centroid, L1/L2/infinity normalization. Output: exact expression, dims, output norm, component preview, nearest bound rows under selected metric, `Use as query vector`, `Copy JSON array`, `Open search comparison`. Persistent warning verbatim: "Arithmetic is exploratory. Analogy behavior depends on the embedding model, version, preprocessing, and training objective." (spec:783). **[OVERRIDE per rev:74]** single mono input row + `$(beaker) Experimental vector arithmetic` as plain warning-colored text; output as label/value grid.

## 10. Projection workspace (spec:786-876)

MVP: deterministic **PCA 2D only** (spec:790). Toolbar defaults (spec:794-803): Method `PCA 2D`; Preprocessing `Center only`; original-space neighbor metric = binding metric or cosine; Color by None; Label by binding label or none; Sample = host-resolved bounded sample; Fit available; selection tools pointer + lasso. Optional `L2 normalize, then center` preprocessing is explicit, never silently inherited from a search metric (spec:805). **[OVERRIDE R6]** toolbar is a 28–30 px toolbar row of native-styled controls (rev:54, rev:76).

**Canvas** (spec:807-817): custom 2D canvas or equivalent, **fully local**; pan/zoom/fit/click/lasso/keyboard point navigation; stable screen-space point size; selected point uses shape + outline, not color alone; labels off by default except selected/focused; MVP must **not silently aggregate points** (alpha/bounded binning later); auto-fit once after first complete projection; recompute with changed preprocessing resets camera only after confirmation when a selection exists.

**Truth banner** (spec:819-826) verbatim shape: `PCA projection of 5,000 sampled rows. PC1 18.4%, PC2 9.7% of sampled variance. Distances and search ranking are calculated in the original 1,536-dimensional space.` **[OVERRIDE R11 + rev:76]** rendered as a single-line info bar ≤ **24 px** styled like a status-bar warning/info item (`--vscode-inputValidation-*` background, 3 px left accent acceptable, radius 0–2), and must now include the **third-component line**: `PC1 18.4% · PC2 9.7% · next 8.9% not shown` (rev:76, rev:121).

**Side inspector** (spec:828-839): ordinal/key, label + selected metadata, PC1/PC2 coords, norm, centroid distance, original-space nearest neighbors, projected nearest points **clearly separated**, actions reveal / compare / query vector / isolate selection.

**Color & legend** (spec:841-853): categorical — top categories get distinct theme-aware styles, rest folded into `Other`, null distinct, high-cardinality warning before applying; numeric — sequential legend with min/median/max, clipped outliers disclosed, no red/green-only meaning. **[OVERRIDE per rev:76]** legend overlay = flat 1 px-bordered panel, radius 2, no shadow, square 8 px swatches; zoom cluster likewise.

**Lasso** (spec:855-864): selected count; actions `Inspect list`, `Add to Compare` (within cap), `Profile selection`, `Clear`; selection list virtualized + keyboard accessible; **no entire vector payload attached to each rendered point** (spec:864 — a data-structure perf requirement).

**Accessible point list** (spec:866-876): always-available synchronized list/table — logical position, row/key, label, PC1/PC2, selected state, norm or color value. List selection highlights canvas without stealing focus; canvas selection updates list and announces via live region. **[OVERRIDE R5/rev:76]** rendered as a data grid in the inspector or bottom drawer.

## 11. Index workspace (spec:878-941)

Requires verified table binding (spec:885). Overview data (spec:887-896): index name + type, vector column + metric, index version, approximate staleness, quantized key-space use, last background task status + time; permission/platform gaps surface at the item level. **[OVERRIDE per rev:78]** the card grid becomes a **properties grid** (two-column label/value, hairline rows — VS Code settings register).

Compatibility findings (spec:898-912): no vector index on column; metric mismatch; earlier index version; latest syntax required; forced ANN unsupported; primary clustered key prerequisite unmet; fewer than required non-null rows for creation; background maintenance failure; sustained staleness observation (no universal threshold claim); missing supporting indexes on common filter columns labeled as a review suggestion, not a command. Rendered with the same list pattern as Profile findings (rev:78).

Health timeline (spec:914-918): MVP may show **current DMV snapshot only** — never draw a fake time series from one sample. Later `Sample health while pane is open` collects in-memory points at an explicit interval and must state history is local, temporary, and starts when sampling starts.

Script actions (spec:920-928): `Generate create vector index script`, `Generate migration script`, `Generate health query`, `Generate supporting-index review query`, `Open exact vs approximate comparison`. **All DDL opens in an editor; no DDL executes from the pane.** Revisions render these as a plain command list, e.g. `$(file-code) Generate create vector index script` (rev:78).

Staleness wording (spec:930-941): use `Approximate staleness: 7.2%`, `Background maintenance last succeeded 4 minutes ago`, `Review recommended because maintenance failed`; avoid `Index unhealthy` from a fixed threshold and `Rebuild now` without workload context.

## 12. Pipeline workspace (spec:943-1011)

**Provenance profile** (spec:949-964): vector column; source text column/expression description; external model object; endpoint host or local runtime type; expected dims + metric; expected normalization; chunk size + overlap; embedding timestamp column; model/batch identifier column; local notes. Unknown fields stay unknown; never infer a model from dimensions alone. **[OVERRIDE per rev:80]** rendered as a properties grid.

**Re-embed selected row** (spec:966-985): flow — select bound row + inspect source text → choose model + params → model-call confirmation → generate fresh embedding → compare stored vs fresh → compare exact NN lists. Result panel: source length + bounded preview; stored vs generated dimensions; cosine/Euclidean/negative-dot distances; norm comparison; neighbor overlap + rank movement; execution messages + elapsed time; **no automatic write-back**. Revisions: label/value grid + small before/after distance table (rev:80).

**Chunk debugger** (spec:987-999): source ribbon with character offsets; chunk blocks with overlap regions; chunk order/offset/length/set-ID; controls for fixed chunk size + overlap within supported ranges; tiny-tail and high-overlap warnings; optional explicit `Generate embeddings for chunks` after model-call confirmation; per-chunk NN result summary. Chunk size labeled **characters**, never tokens (spec:999). Revisions: flatten blocks to radius-2 1 px borders; overlap regions as hatched/tinted spans with a text key (rev:80).

**Drift sample** (spec:1001-1011): explicit bounded-sample operation — regenerate with selected model; compare stored vs generated distance distribution; group by insertion date / model-batch column / scalar column; flag likely transition boundaries as observations, not proof; show call count, failures, retries, sampled scope. Requires **higher-friction confirmation** than single-row re-embed because it is expensive and sends substantial data (spec:1011).

## 13. Selection identity and Results-grid sync (spec:1013-1037)

- Identity rule: all detached visual items use **`resultRowOrdinal`** (zero-based row identity in the bound live/pinned result view — spec:170); never call it a displayed row when the grid has local sort/filter. Table-bound results use the configured table key; a result may hold both identities (spec:1015-1019).
- `Reveal in Results` flow (spec:1021-1030): switch to Results → mount target grid if needed → map ordinal to current display order → scroll/select/focus the vector cell; if filtered out, preserve the filter and offer `Clear filter and reveal`; if no captured row exists, stay in Vector and offer `Fetch bound row` or `Open generated SELECT`.
- Bidirectional selection (spec:1032-1037): grid selection can seed Vector selection when the workbench is open; Vector selection updates query-result context as a **distinct vector selection kind**; must not overwrite a grid display-row context until reveal mapping succeeds; **selection changes throttled for context updates, never for visible highlight** (a perf/UX requirement).

## 14. Loading / partial / empty / error state taxonomy (spec:1039-1073)

Fifteen required states (spec:1043-1060), each with required UX:
| State | Required UX |
| --- | --- |
| Waiting for execution | initial preview keeps Vector hidden until a typed eligible result is terminal; Results shows execution progress |
| Preparing sample | progress count, cancel action, operation method; no stale data presented as current |
| Full result analyzed | exact full-result badge + row count |
| Sample analyzed | sample badge, method, seed, sampled count, total count |
| Scan budget reached | preserve completed output; state what was scanned and what remains unknown |
| Local compute budget reached | preserve complete derived items; explain the stopped operation |
| Terminal partial query | persistent banner: cancellation / connection loss / row cap / store corruption reason |
| No non-null vectors | empty state with counts + Results action |
| Text fallback | initial preview keeps it in Results; future limited mode must offer verified binding/conversion before eligibility |
| Dimension mismatch | isolate affected rows; never crash the whole analysis |
| Diagnostic connection unavailable | detached tools remain usable |
| Permission denied | name the unavailable workspace operation + permission category when known |
| Preview feature disabled | show generated verification/enablement SQL; never execute config changes |
| Model call partial | preserve successful rows; list failures, retries, cancellation status |
| Renderer unavailable | keep tables, findings, point list usable |

Honest partial wording (spec:1062-1073) — preferred verbatim examples: "Showing a deterministic sample of 3,842 rows from 2,412,883 because the 8,000,000-component analysis budget was reached." and "12 malformed vectors were observed in the 25,000 scanned rows. Remaining rows were not scanned." Avoid "12 malformed vectors in the table" unless a full scan occurred.

**[OVERRIDE R7]** question-style copy ("Do the stored vectors look structurally healthy?" etc.) lives in **empty states**, not chrome (rev:56). Checklist requires all §18 states remain representable in the new visual vocabulary (rev:124).

## 15. Accessibility (spec:1075-1119)

Complete nonvisual workflow (spec:1079-1091): activate Vector tab via results tablist; choose result set + column; understand transport/dims/sample/binding; run Profile without a chart; navigate findings + affected rows; compose + run Search comparison; read recall/rank/evidence in tables; navigate Projection points via synchronized list; select a point + reveal in Results; review generated SQL; cancel any operation.

Semantics (spec:1093-1098): results tabs use complete `tablist`/`tab`/`tabpanel`; workspace nav is vertical tabs **or** a navigation list with a single selected item — not nested tablists with ambiguous arrows; regions join the Query Studio **F6 focus sequence**: editor → results tab bar → Vector workspace navigation → main content → inspector → status; drawers return focus to the invoking control.

Charts/canvas (spec:1100-1107): every chart gets a concise text summary + data table/list; canvas has accessible name + instructions; canvas is **not flooded with one accessibility node per point** (perf-relevant); point navigation via the virtualized list; hover info duplicated in persistent details; selection changes via **polite live region**.

Visual (spec:1109-1119): shape/outline/dash/text in addition to color; support light, dark, high contrast, high contrast light, and **forced-colors** modes; respect VS Code reduced-motion and screen-reader classes; no required animation, camera transitions instant under reduced motion; controls usable at **200% zoom**; legends/status never overlay chart marks at narrow widths. Acceptance (spec:1293-1299): focus visible + stable across drawers/reruns/workspace changes; live announcements concise and not repeated per streamed chunk.

## 16. Visual design system — base rules + normative house-style constants

Base spec §20 (spec:1121-1146): first-party Query Studio feel, not an embedded analytics site; **Fluent controls and VS Code theme tokens**; compact information-dense layouts with generous chart whitespace; sparse borders (hierarchy from headings/alignment/elevation); no neon gradients/glowing points/pseudo-3D; locale-aware number formatting with stable precision. Status color semantics (spec:1130-1135): Error = decode/model/maintenance failure; Warning = partial scope, metric mismatch, unsupported strategy, stale binding; Information = preview feature, isolated session, sample method; Success = completed operation or confirmed evidence — never merely "looks healthy". Distance precision (spec:1137-1146): **6 significant digits in tables**, more in tooltip/copy, scientific notation for extreme values, exact raw value in details; ranks/recall as integer counts alongside percentages.

**[OVERRIDE — rev §3 house-style constants, "normative — from the shipping Query Studio code"]** (rev:24-40). Contract verbatim: "toolbar 35px, status 24px, 2px radii max, VS Code tokens only, no ornamental chrome."

| Token | Value |
| --- | --- |
| Base/control font | 13 px / 12 px, `--vscode-font-family` |
| Numeric + code font | `--vscode-editor-font-family` (Cascadia/Consolas) — always for numbers in tables |
| Border radius | ≤ **2 px everywhere**; no pills, no rounded cards |
| Results tab strip | 30 px strip, 24 px **text-only** tabs, active = 2 px bottom border `--vscode-focusBorder`, no icons in tabs |
| Toolbar rows | 35 px primary / 28–30 px secondary; buttons 26 px, radius 2, transparent bg, hover `--vscode-toolbar-hoverBackground`, primary `--vscode-button-background` |
| Status bar | 24 px, hairline-separated segments |
| Splitters | 4 px, `--vscode-editorWidget-border`, hover `--vscode-focusBorder` |
| Data-grid rows | ~24 px, alternating backgrounds per Fluent result-grid tokens, right-aligned mono numerics, resizable/sortable headers |
| Section separation | 1 px rules (`--vscode-panel-border`) + 11 px UPPERCASE labels in `--vscode-descriptionForeground` — the **only** sanctioned uppercase |
| Shadows | menus/popovers/dialogs only; never on in-pane content |
| Backgrounds | pane = `--vscode-panel-background` / editor background; no tinted section headers, no `surface2` card bodies |

Chart register **[OVERRIDE R10]** (rev:62): hairline baseline, bars in `--vscode-charts-*`, 10 px monospace axis extremes, stats as small label/value grid beneath (label description-foreground, value mono); median/p5/p95 as tick marks on the baseline, not a stat card; the section label is the chart title.

Numbers **[R12]** (rev:66): locale-aware thousands separators; 6 significant digits in tables (full precision in tooltip/copy per spec §20.3); monospace, right-aligned in any columnar context; bytes in KiB/MiB; **never center-align a number**. Largest numeral in any workspace ≤ **15 px** except dialogs (rev:86, rev:117).

Component vocabulary (rev:82-86) — **Allowed:** codicon+text inline statuses, facts strips, 11 px uppercase section labels with hairline rules, properties grids, Fluent result grids, toolbar rows of native-styled controls, status-bar segments, single-line severity info bars, flat legend/zoom overlays (1 px border, radius 2), monospace numerics, popovers/menus with standard shadow. **Banned:** KPI/stat cards, pill chips/tag badges, tinted section-header bars, card containers radius > 2, shadows on in-pane content, max-width centered columns, icons in results tabs, two-line nav items, decorative chrome subtitles, uppercase letter-spaced table headers, display-size numerals (> 15 px) outside dialogs, progress "hero" moments.

Keep-list (rev:13-22, do not regress): VS Code theme tokens; dark/light/HC parity; theme switcher affordance (preview); **codicons as the only icon system**; 24 px status bar with scope summary + `No network requests`; capability popover facts table; model-call dialog field set (radii/spacing tightened, content stays); six workspaces; header Result/Vector-column selectors; binding + scope badges; SQL drawer as primary experience; honest microcopy ("sampled vs full", denominators, evidence labels, "Experimental vector arithmetic", "parsed locally, never eval()"); no gradients/glow/3-D/emoji.

## 17. Keyboard model (spec:1194-1210)

Suggested commands, subject to Query Studio command review:
| Shortcut | Action |
| --- | --- |
| `Ctrl+Alt+V` | Open/focus Vector tab when eligible |
| `Ctrl+Enter` | Run the focused explicit operation when safe; never triggers a model call without confirmation |
| `Escape` | Cancel lasso, close drawer, return focus; a running operation requires the visible Cancel action or a confirmed command |
| `F6` / `Shift+F6` | Cycle Query Studio focus regions |
| Arrow keys | Navigate workspace rail or focused list |
| `Enter` | Activate selected workspace/finding/row/point |
| `Space` | Toggle selection in list/matrix contexts |
| `+` / `-` | Zoom Projection canvas while focused |
| `0` | Fit Projection while focused |
| `Ctrl+C` | Copy focused table cell or selected generated SQL per normal control semantics |

Do not overload editor shortcuts while focus remains in Monaco (spec:1210).

## 18. Privacy, egress, model-call confirmation (spec:1148-1192)

Classified as result data — banned from telemetry, diagnostics, replay descriptors, performance marks, and error logs (spec:1152-1163): vector components + binary payloads; source text + labels; table keys; distances/norms/centroids/duplicate hashes; **projection coordinates**; search results; model outputs; table/column bindings when combined with user data context. (Directly constrains the required timing/metric logging for this build: log timings and counts, never these values.)

Model-call confirmation dialog required fields (spec:1166-1183, verbatim shape): title `Generate embeddings with dbo.TextEmbedding3Small?`; rows for Model type (`Embeddings`), API format (`Azure OpenAI`), Endpoint host (`example.openai.azure.com`), Source (`Selected text cell`), Rows / calls (`1`), Text characters (`842`), Approximate payload (`1.7 KiB`), Execution (`SQL Server calls the configured endpoint`), Result handling (`Kept in this panel; not written to the table`); buttons `[Cancel] [View generated T-SQL] [Generate embedding]`. Batch/drift ops emphasize call count, sampled scope, estimated payload, retry behavior, cancellation limits (spec:1185). Never display credentials, credential names when policy forbids, bearer tokens, or full endpoint query strings (spec:1187).

**Webview network rule** (spec:1189-1191): the Vector webview performs **no network requests**; external model communication happens only through the database engine + configured external model. Opening the pane never invokes a model (spec:75). UX-G9: fully offline in the webview (spec:95).

## 19. Localization & microcopy (spec:1212-1233; rev:88-90)

Every visible string enters the existing localization bundle **from the first patch**; no sentence composition assuming English word order; locale-aware number/date/time/byte utilities; SQL identifiers exact and visually separated from prose. Preferred-terms table (spec:1223-1233): use `Vector Workbench` not "AI magic/semantic map"; `Negative dot product` not "Dot similarity"; `Approximate requested, strategy unverified` not "ANN used"; `Sampled rows` not "Dataset"; `Result-row ordinal` not "Row number" after local sort/filter; `Exact duplicate` not "Duplicate meaning"; `Possible provenance mismatch` not "Wrong model"; `Generate script` not "Fix automatically"; `Text may be sent to the configured model endpoint` not "Safe model call". Revisions add (rev:90): chrome is declarative and terse (`Profile`, `Sampled pair distances`, `Executed`); questions/explanations live in empty states and `Why this matters` disclosures; every sampled number says so **once, in its authoritative location** (R9).

## 20. Every stated numeric budget / requirement in these sources

Layout/interaction:
- Breakpoints: wide ≥ 960 CSS px; medium 640–959; narrow < 640 (spec:256, 280, 288).
- Minimum usable content height: **240 CSS px** (spec:252); Projection canvas ≥ 240 px in narrow layout (spec:293).
- Rail: 156–184 px (spec:275) → **[OVERRIDE R8]** ~160 px, 22–24 px items (rev:58). Inspector 320–400 px (spec:277).
- 200% zoom usability (spec:1117); no horizontal page scrolling in narrow layout (spec:294) and, per R4, no page scrolling at wide/medium at all (rev:50, rev:113).
- Facts strip ≤ 24 px (rev:44); truth banner ≤ 24 px (rev:64, rev:121); status bar 24 px; tab strip 30 px / tabs 24 px; toolbars 35 / 28–30 px; buttons 26 px; splitters 4 px; grid rows ~24 px; section labels 11 px; radius ≤ 2 px; fonts 13/12 px; 10 px mono for axis extremes/method text/dimension ids; numerals ≤ 15 px outside dialogs; 3 px left accent on info bars; 8 px legend swatches; 1 px matrix cell gaps (rev:24-86).

Data/precision:
- 6 significant digits in tables, full precision in tooltips/copy, scientific notation at extremes (spec:1139-1143, rev:66).
- K default 20; Repetitions default 1 (capped); Actual plan on by default (spec:594-598).
- Example scope numbers used across mockup copy: sample 5,000 of 2,412,883; 1,536 dims; PC1 18.4% / PC2 9.7% / next 8.9%; recall 18/20 = 90%; exact 842 ms vs approx 17 ms; staleness 7.2%; **8,000,000-component analysis budget** (the only explicit compute budget stated in these sources — actual budget values are owned by the implementation plan, spec:15).

Perf-relevant structural rules (bear on "highly optimized data structures"):
- Virtualized: Profile row-inspector list (spec:528), lasso selection list (spec:863), Projection point list; mockups must annotate which components are virtualized (spec:1267).
- No vector payload attached per rendered point (spec:864); canvas not flooded with per-point a11y nodes (spec:1103); selection-change context updates throttled, highlights not (spec:1037).
- Inner-region scrolling with one virtualized grid scrollbar as *the* scrollbar (rev:50).
- Live announcements must not repeat per streamed chunk (spec:1299).
- Result data (including projection coordinates and distances) is banned from perf markers and logs (spec:1152-1163) — timing/metric instrumentation must log durations/counts only.

Mockup deliverable acceptance (rev:92-124): every screen also captured at **1280×720**; at 1280×720 the Search-comparison screen must show **≥ 12 rank-grid rows** and **≥ 2×** the visible data rows of v1's equivalent with no horizontal page scroll (rev:122); squint test at 25% zoom must read as VS Code panels (rev:123); scope stated exactly twice (rev:118); zero radius > 2 px, zero chips, zero cards, no `max-width` (rev:110-113).

## 21. UX acceptance criteria (spec:1270-1305)

Core flow: open Vector from a result without changing the query; defaults to Profile and explains scope before findings; binding without guessed authority; generate + inspect exact and approximate SQL variants; recall/rank changes include counts + denominators; ANN evidence labeled by proof, not syntax; any projected point selectable via canvas **and** list and revealable in Results; DDL generated, never executed; model calls need explicit informative confirmation.
Truthfulness: no sampled op labeled full; no scanned-prefix count as table-wide; no projection distance as SQL distance; no auto-interpreting JSON text as vectors; no model/normalization inferred from dims; no unconditional rebuild advice from staleness alone.
Privacy: opening Vector sends no network request and performs no model call; confirmation accurately describes source/model/endpoint host/row count/egress path; no copy encourages public projector URLs.

## 22. Mockup/screen package (spec:1235-1268 baseline; rev:92-106 v2 minimum set)

Base spec §24 lists 18 annotated light/dark/high-contrast screens. Revisions §8 defines the v2 minimum re-render set: (1) Profile complete wide — the reference screen; (2) Profile row inspector open; (3) Search composer, Selected-row, pre-run; (4) Search comparison complete (facts strip, evidence incl. filter-semantics + staleness, rank grid, SQL drawer open); (5) evidence states strip: confirmed / unverified / exact fallback / no index; (6) Projection wide with selection, flat legend, truth banner with third component; (7) Index properties grid + findings + scripts (healthy v3 and legacy-migration); (8) Pipeline re-embed + chunk ribbon; (9) narrow Profile and Search; (10) all in dark; screens 1, 4, 6 also light + high-contrast; (11) everything at 1280×720. Carry v1 annotation duties from spec §24: focus order, keyboard behavior, aria role/name, breakpoints, exact copy for empty/partial/warning/confirmation states, full/sampled/scanned-prefix/newly-executed data provenance, which controls cause SQL execution or model egress, which components are virtualized, which values are result data and must not enter telemetry (spec:1258-1268, rev:106).

## 23. Consolidated override ledger (revisions vs base spec)

| # | Base spec | Revision override |
| --- | --- | --- |
| R1 | §11.3 four summary cards (spec:449-458) | Single-line facts strip ≤ 24 px (rev:44) |
| R2 | §11.2 boxed panels / §15.2 index cards | No bordered/radius-6/header-barred containers; flat regions + 11 px uppercase labels + 1 px rules (rev:46) |
| R3 | Badge/chip styling implied by v1 | Pill chips banned; inline codicon + word or popover row; header binding/scope badges only exception (1 px border, radius 2, button-styled) (rev:48) |
| R4 | (composition unspecified) | No `max-width`; pane fills; inner regions scroll, page never (narrow Profile exception) (rev:50) |
| R5 | Tables described generically (§12.7, §11.5, §14.8, §13.4, §15) | All rendered as Fluent result grid / SlickGrid look: 24 px rows, sortable/resizable, right-aligned mono 6-sig-digit numerics, codicon+word statuses (rev:52) |
| R6 | Workspace controls as forms/toolbars (§12.3, §14.2) | One idiom: 28–30 px toolbar rows, native VS Code-styled controls, 26 px buttons (rev:54) |
| R7 | Workspace "purpose" questions in headings (§11.1, §12.1, …) | Questions removed from chrome, moved verbatim into empty states; headings are bare words (rev:56) |
| R8 | Rail 156–184 px (spec:275) | ~160 px, single-line 22–24 px items, lock codicon for gated, no sub-captions, no evidence legend in rail (rev:58) |
| R9 | Scope surfaced in header + cards + panels | Scope exactly twice: header badge (interactive) + status bar (passive); per-panel scope chips deleted (rev:60) |
| R10 | §11.4/§11.7 chart panels | Utility register: hairline baseline, `--vscode-charts-*`, 10 px mono extremes, tick-mark stats, section label = title (rev:62) |
| R11 | §14.4 "persistent compact banner" | ≤ 24 px single-line info bar (`--vscode-inputValidation-*`, 3 px accent, radius 0–2) (rev:64) |
| R12 | §20.3 precision | + locale separators, KiB/MiB, right-aligned mono, never centered, ≤ 15 px numerals (rev:66) |
| Add | §12.10 evidence panel | + filter-semantics line (`Iterative filtering` vs `Post-filtered, TOP_N ×5`) + staleness stamp (rev:72, rev:120) |
| Add | §14.4 banner text | + third PCA component: `next 8.9% not shown` (rev:76, rev:121) |
| Add | §13.3 two-vector view | + "contribution view" ranked bar list (rev:74) |
| Add | §24 mockups | + 1280×720 capture, ≥ 12 rank rows, ≥ 2× data density, 25%-zoom squint test (rev:104, rev:122-123) |
