# Query Studio Vector Workbench - Readiness Review Addendum

**Status:** Final pre-implementation review of the scenario, revised UX direction, and v2 mockups  
**Date:** 2026-07-11  
**Primary audience:** Product engineering, SQL Tools Service engineering, Query Studio engineering, UX design, accessibility, performance, security, and coding agents  
**Reviewed inputs:**

- `query_studio_vector_workbench_implementation_plan.md`
- `query_studio_vector_workbench_ux_spec.md`
- `vector_design_addendum.md`
- `vector_ux_revisions.md`
- `vec_model.png`
- `vec_sample.png`
- `vec_profile.png`
- `vec_profile_findings.png`
- `vec_search.png`
- `vec_search_results.png`
- `vec_compare.png`
- `vec_projection.png`
- `vec_index.png`
- `vec_pipeline.png`
- `vec_pipeline_regen.png`

**Companion document:** `vector_workbench_test_and_demo_guide.md`

## 0. Purpose and precedence

This document is an additional review layer. It does not replace the implementation plan, UX specification, prior design review addendum, or UX revision brief.

Precedence is:

1. This addendum overrides a prior document only where it explicitly states **Required correction**, **P0**, **P1**, **P2**, **Do not**, or **Readiness gate**.
2. The previous design addendum remains the code and platform architecture review.
3. The UX revision brief remains the visual-language contract.
4. The implementation plan remains the repository and pull-request execution plan.
5. The UX specification remains normative for states, behavior, accessibility, and interaction where no later document changes it.

The purpose of this review is narrower and more operational:

- Decide whether the scenario is ready to hand to coding agents.
- Review every revised screen for technical truth and workflow completeness.
- Identify common RAG, embedding, and vector-search failure modes that are still missing.
- Convert ambiguous UI facts into explicit data contracts.
- Add acceptance criteria for the mockups themselves.
- Separate product demonstrations from synthetic or harness-only test cases.

## 1. Executive verdict

### 1.1 Overall verdict

**The architecture is ready. The revised visual system is ready. The feature is not yet ready for a single unsupervised end-to-end generation pass.**

It becomes ready for staged implementation after the P0 corrections in section 2 are incorporated into the source specifications and mockup annotations.

The revised screens are a large improvement over the first mockup. They now read as a Query Studio results-pane tool rather than a dashboard. The dense facts strips, flat sections, native grids, command lists, evidence rows, and status bar are all pointed in the right direction. The Search workspace in particular now has a credible professional identity: it asks what exact and approximate retrieval changed, then shows the evidence needed to prove the answer.

The remaining blockers are mostly semantic, not visual:

- Some labels still mix facts from the current result with facts from a bound table.
- A few displayed claims are not direct catalog or DMV facts.
- One Index mockup contradicts itself by showing a latest v3 index and offering a selected v2-to-v3 migration.
- The Profile finding count does not identify whether it counts rows, dimensions, groups, or pairs.
- The Projection screen reports two different sample counts without explaining the analysis-versus-render distinction.
- Search does not yet disclose self-match exclusion or comparison read consistency.
- Pipeline displays external model names as schema-qualified even though external model objects are database-scoped names, not schema-scoped objects.
- The global `No network requests` claim becomes misleading after the database engine makes a remote model call.

These are the kind of issues that look cosmetic in a mockup and become expensive cross-layer ambiguity in code. They should be corrected before implementation contracts are frozen.

### 1.2 What should not change

Do not churn the following foundations:

- The Vector sibling tab placement.
- The six workspaces: Profile, Search, Compare, Projection, Index, Pipeline.
- The evidence taxonomy.
- Exact search as the recall denominator.
- Forced ANN as stronger evidence than approximate syntax alone.
- Detached result mode versus explicitly table-bound mode.
- Isolated diagnostic sessions.
- Generated T-SQL that is visible and never silently executed for DDL or configuration changes.
- Host-authoritative budgets and opaque result-store sessions.
- Local PCA as the first projection.
- The external model call confirmation dialog.
- The revised VS Code-native density and visual vocabulary.

## 2. P0 corrections before coding begins

### P0-1. Make source mode explicit everywhere

The header currently shows all of these at once:

- A current result set such as `Chunk search (top 50)`.
- A selected vector column.
- A bound table such as `dbo.DocumentChunks`.
- A sample such as `5,000 of 2,412,883`.

A user cannot tell whether a number or finding came from the 50 returned rows, the 5,000-row analysis sample, the complete bound table, a catalog query, or a new diagnostic query.

**Required correction:** Add a source-mode fact to the header or workspace facts strip and carry it in every analysis result contract.

Recommended values:

```ts
export type VectorEvidenceSource =
    | { kind: "capturedResult"; resultSetId: string; frozenRows: number }
    | {
          kind: "boundTableSample";
          objectId: number;
          eligibleRows?: number;
          sampledRows: number;
          samplingMethod: string;
      }
    | { kind: "catalog"; objectId?: number }
    | { kind: "diagnosticQuery"; sessionId: string; statementCount: number }
    | { kind: "localComputation"; inputRows: number }
    | { kind: "interpretation"; basedOnEvidenceIds: readonly string[] };
```

Visible examples:

- `Source: captured result, 50 rows`
- `Source: bound table sample, 5,000 of 2,412,883 eligible rows`
- `Source: catalog and health DMV`
- `Source: 3 new statements on isolated session`
- `Source: local computation over selected vectors`

The user should never have to infer the source from color, position, or workspace.

### P0-2. Add a typed subject to every finding

The Profile finding list shows counts such as `23`, but the detail drawer calls them `Affected rows`, even when the finding is `Near-constant dimensions` and the count represents dimensions.

This is a contract bug waiting to hatch.

**Required correction:** Every finding must declare what its count measures.

```ts
export type VectorFindingSubject =
    | "row"
    | "dimension"
    | "duplicateGroup"
    | "pair"
    | "category"
    | "document"
    | "index"
    | "model"
    | "chunk";

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

The drawer title and actions must derive from `subject`:

- `Affected dimensions: 23`
- `Duplicate groups: 12, covering 37 rows`
- `Affected rows: 8`
- `Categories with unusual geometry: 1`

Row actions such as Reveal in Results, Add to Compare, and Use as Query Vector must not appear for a dimension-only finding unless the tool also presents a deliberate representative-row subview.

### P0-3. Fix the Index healthy-state contradiction

`vec_index.png` reports:

- `Version v3 (latest format)`
- `Latest index format (v3)` as a successful finding
- A selected action `Generate migration script (v2 -> v3)`
- A generated script that drops and recreates the same healthy v3 index

This is internally contradictory and dangerous. A user could infer that routine migration is appropriate even when no migration is required.

**Required correction:** Split the Index designs into at least two explicit states.

1. **Healthy current-format state**
   - Hide or disable the migration command.
   - Offer health snapshot, create/recreate script for review, workload support-index review, and configuration checks.
   - Explain that no migration is required.

2. **Earlier-format state**
   - Show version `< 3` or unknown older format.
   - Offer the migration script.
   - Put the service-impact warning above the script: dropping the index disables approximate vector search until recreation completes.
   - Show post-filter semantics and DML limitations as version-specific findings.

Do not generate a destructive migration recommendation from a generic command list when the catalog facts say the index is already current.

### P0-4. Correct external model naming and ownership

The mockups show `dbo.TextEmbedding3Small`. External model objects are named at database scope and have an owner principal, but they are not schema-qualified objects.

**Required correction:** Display the model as:

```text
Model            TextEmbedding3Small
Owner            dbo
Provider model   text-embedding-3-small
```

Do not use `dbo.TextEmbedding3Small` in generated T-SQL, selectors, provenance records, or telemetry-safe metadata.

The model identity used for reproducibility should include at least:

- external model object name;
- owner principal;
- API format;
- provider model string;
- endpoint host or local runtime classification;
- `parameters` digest;
- create time and modify time;
- dimensions requested or observed;
- model type, explicitly `EMBEDDINGS`.

### P0-5. Replace the global network claim with a layered claim

The status bar says `No network requests`. That is correct for a sealed webview, but it is not correct for the full operation after SQL Server calls Azure OpenAI, OpenAI, or another REST endpoint.

**Required correction:** Use layered language.

Before any model call:

```text
Webview network: none
Server-side model calls: none in this session
```

After a confirmed remote model call:

```text
Webview network: none
Server-side external calls: 1
```

For ONNX Runtime:

```text
Webview network: none
Model execution: local SQL Server runtime
```

For host-local Ollama:

```text
Webview network: none
Model execution: host-local endpoint
```

The confirmation dialog already explains egress well. The footer must not contradict it.

### P0-6. Explain Search self-match and duplicate-exclusion semantics

A selected row used as a query vector will normally retrieve itself at distance zero. The Search results mockup begins below the first ranks, but it does not state whether the source row, byte-identical duplicates, same-document chunks, or any other rows were excluded.

**Required correction:** Add explicit query-set rules to the composer and evidence result.

```ts
export interface VectorSearchExclusionPolicy {
    readonly excludeSourceRow: boolean;
    readonly excludeExactVectorDuplicates: boolean;
    readonly excludeSameDocument?: boolean;
    readonly keyPredicateSql?: string;
}
```

Visible evidence:

- `Source row excluded by key: chunk_id <> 100042`
- `Exact vector duplicates included`
- `Same-document chunks included`

The exact and approximate variants must use the same exclusion predicate.

### P0-7. State comparison read consistency

Exact and approximate queries can observe different committed data when concurrent DML occurs. A comparison that reports recall and rank movement without stating its read-consistency conditions can blame ANN for ordinary concurrent change.

**Required correction:** The Search run contract and evidence panel must state one of:

- `Read consistency: one read-only snapshot transaction`
- `Read consistency: database snapshot isolation`
- `Read consistency: read committed; concurrent changes may affect comparison`

The implementation should prefer a single isolated diagnostic session and a transaction that provides a stable read view where the target supports it and the feature can do so without changing database settings. Do not enable snapshot isolation automatically. When a stable read view cannot be guaranteed, disclose the limitation.

### P0-8. Resolve the Projection sample-count discrepancy

`vec_projection.png` says the PCA used 5,000 sampled rows, while the point list says `1,200 sampled`.

This can be valid if 5,000 rows were analyzed and 1,200 points were rendered, but it must be explicit.

**Required correction:** Report separate counts:

```text
Analyzed: 5,000 vectors
Rendered: 1,200 points
Point selection: deterministic display subsample
```

If all analyzed vectors are rendered, the counts must match. The point list count must never use the word `sampled` when it is actually a display cap over an already sampled analysis matrix.

### P0-9. Make Search timing statistically honest

The Search result shows `Exact 842 ms` and `Approx 17 ms (50x)`. A single cold exact query versus a warm approximate query, or vice versa, can make the multiplier theatrical rather than useful.

**Required correction:** MVP may show one observation, but it must say so:

```text
Exact 842 ms, single observation
Approx 17 ms, single observation
```

The product-ready comparison mode should support:

- optional warmup;
- 3 to 10 measured repeats, bounded by policy;
- median and p95 wall time;
- logical reads and CPU where available;
- whether plan capture was enabled;
- the same parameter values and query vector for every variant.

A speedup ratio should be hidden when the observations are not comparable.

### P0-10. Freeze the query vector once per comparison

Text-with-model mode must not call the model separately for exact and approximate variants. Model output can vary by model version, endpoint behavior, or preprocessing.

**Required correction:** Generate or obtain the query vector once, validate its dimensions and base type once, record a digest locally, then reuse that same value for every search statement in the comparison.

The UI should say:

```text
Query vector generated once and reused across 3 search variants
```

## 3. P1 additions that materially improve professional usefulness

These are not blockers for the first vertical slice, but they should be represented in the contracts and roadmap now so the MVP does not paint itself into a tiny corner.

### P1-1. Add a query-set recall harness

A single query can be an anecdote. DBAs and retrieval engineers need a distribution.

Add a bounded mode that samples N rows, uses each row as a query, excludes the source row by key, runs exact and approximate retrieval, and reports:

- median recall@K;
- p5 recall@K;
- minimum recall@K;
- median and p95 latency;
- worst query keys;
- recall grouped by category, language, tenant, or document type;
- index staleness at run time;
- cancellation and statement count.

This should be labeled `Query set` in Search, not hidden inside Profile.

### P1-2. Add a K-sweep

A bounded K-sweep answers a practical tuning question: how much recall and latency change as K grows.

Recommended values are configurable but seeded as `{10, 20, 50, 100}`. Run exact once at the maximum K, then compare prefixes. Show recall, overlap, and latency by K.

### P1-3. Add RAG crowding and diversity diagnostics

Common retrieval failures are not visible in global PCA or norm distributions:

- many adjacent chunks from one document crowding out other documents;
- boilerplate chunks appearing in every neighborhood;
- one document or tenant acting as a nearest-neighbor hub;
- duplicate or near-duplicate chunks consuming top-K slots;
- same-document overlap creating artificial recall.

Add diagnostics for:

- unique documents in top K;
- maximum chunks from one document;
- adjacent-chunk share;
- repeated boilerplate neighbor frequency;
- hubness, such as how often each row appears in sampled neighbor lists;
- same-tenant versus cross-tenant neighbor counts.

These should be descriptive by default, not universal error thresholds.

### P1-4. Add provenance and freshness auditing

Dimension compatibility does not prove embedding compatibility.

A useful profile should support columns or declared metadata for:

- source text column or expression;
- document and chunk keys;
- external model object;
- provider model string;
- model or deployment version marker;
- preprocessing template;
- query prefix and passage prefix;
- normalization policy;
- chunk size and overlap;
- source modified time;
- embedded time;
- embedding batch ID.

Findings should include:

- source text modified after embedding;
- embedding timestamp missing;
- mixed model populations;
- mixed preprocessing profiles;
- same dimensions but incompatible provenance;
- declared expected dimensions disagreeing with stored vector dimensions.

### P1-5. Add endpoint and call diagnostics

Pipeline troubleshooting should expose more than success or failure.

Useful facts include:

- configured retry count;
- observed status code class;
- endpoint host;
- model object modify time;
- request count;
- payload bytes;
- call duration;
- cancellation outcome;
- dimension returned;
- XEvent references where the user has permission;
- database principal permission to execute the external model;
- whether the external REST or local AI runtime configuration gate is enabled.

No secrets, full URLs with query strings, source text, or returned vectors enter diagnostics.

### P1-6. Add hybrid-search evaluation as a fast-follow

Production RAG commonly combines full-text or lexical search with vectors. A serious SQL workbench should eventually compare:

- vector-only;
- full-text-only;
- hybrid union;
- reciprocal rank fusion;
- optional reranked output.

This is not required for the first implementation, but the saved experiment format should permit multiple retrieval stages and graded expected rows.

### P1-7. Add ACL and tenant-filter validation

A vector debugger used in multi-tenant or security-filtered systems should help detect retrieval that is technically similar but operationally forbidden.

The tool must preserve:

- row-level security;
- user permissions;
- tenant predicates;
- soft-delete and visibility predicates;
- temporal or status filters.

It must never open a privileged diagnostic connection or bypass RLS. The UI should be able to report:

- eligible rows under the current principal;
- filter selectivity;
- cross-tenant neighbors visible within the authorized result;
- exact and approximate filter semantics;
- fewer-than-K results caused by eligibility rather than ANN recall.

## 4. Global shell and header review

### What works

- The Vector sibling tab reads naturally beside Results, Messages, and Query Plan.
- The top selectors are compact and discoverable.
- The model, binding, and sample controls look native after the revision pass.
- The status bar communicates evidence and diagnostic-session isolation.
- The capability and analysis-scope popovers are appropriately factual and dense.

### Tightening required

1. Add the explicit source mode from P0-1.
2. Rename `Model enabled` to one of:
   - `Embedding model configured`
   - `Embedding model available`
   - `Model call verified`, only after a successful confirmed call
3. Do not use a green success state merely because a catalog row exists. A model can be configured but unreachable.
4. Add permission state to the capability popover:
   - catalog metadata visible;
   - health DMV permission available or unavailable;
   - external model executable by the current principal;
   - table binding key readable;
5. Include engine and platform facts:
   - SQL Server 2025, Azure SQL Database, Managed Instance, or Fabric SQL;
   - engine edition;
   - compatibility level;
   - preview-feature state;
   - vector index version and regional rollout state where applicable.
6. Make the sample button describe analysis scope, not only the sample size.
7. Replace the global network claim per P0-5.
8. Do not let the header imply that every workspace uses the same source. Search and Index are often table-bound and server-executed; Compare can be local; Profile can be detached.

## 5. Screen-by-screen technical review

## 5.1 Vector capability popover (`vec_model.png`)

### What works

- `Facts probed from the connection, not marketing labels` is exactly the right framing.
- Native transport, dimensions, exact search, approximate search, index, health DMV, external model, API format, feature gates, and diagnostic-session isolation are the correct categories.
- The colored values convey status without relying only on cards or decoration.

### Corrections and additions

- Replace `dbo.TextEmbedding3Small` with the model name and owner as separate facts.
- Distinguish three states:
  - configured;
  - authorized and callable;
  - successfully invoked in this session.
- Show `Model type: EMBEDDINGS` explicitly and filter out future unsupported model types.
- Add `Model modified` and a short parameters digest.
- Add `Engine/platform` and compatibility level.
- Add metadata visibility and `VIEW DATABASE STATE` availability.
- Add egress classification:
  - external remote endpoint;
  - host-local endpoint;
  - local ONNX runtime.
- Add index metric compatibility separately from index existence.
- Add a result when vector metadata is exposed only as string because the driver or first-result metadata path did not preserve native vector type.
- Do not expose the full credential name, secret, or URL query string.

### Acceptance tests

- Catalog visible but model execution denied.
- External model absent.
- Multiple embedding models.
- Model with a returned dimension different from the bound vector column.
- Health DMV hidden by permission.
- SQL Server 2025 with preview features off.
- Azure SQL region with earlier index format.
- ONNX Runtime model on supported Windows environment.

## 5.2 Analysis scope popover (`vec_sample.png`)

### What works

- Sample rows, method, seed, packed input, scan cap, and full-scan option are useful and appropriately compact.
- The disclosure that local computations never see rows outside the sample is excellent.

### Corrections and additions

- `Uniform windows` can be read as a statistically uniform random sample. Use:
  - `Evenly spaced row windows over captured result order`
  - `Deterministic window sample; not random`
- State that ordering can bias the sample.
- Explain seed scope: the seed is stable only for the same frozen row order and sampling specification.
- Report:
  - rows scanned;
  - rows accepted;
  - null/unavailable rows skipped;
  - bytes read from the result store;
  - packed bytes;
  - elapsed time;
  - partial reason.
- Add a table-bound representative sampling option later, such as a deterministic key-hash sample, when a stable key is available.
- A full scan must show its raised budget, expected work, cancellation, and source mode before it starts.
- Do not call the sample representative unless its method and source distribution justify that claim.

### Acceptance tests

- Input ordered by category to prove visible sample bias disclosure.
- Result smaller than requested sample.
- Scan cap reached before sample fills.
- Component budget reduces effective rows below the requested sample.
- Null-heavy vector column.
- Result-store spill read path.
- Cancellation halfway through preparation.

## 5.3 Profile workspace (`vec_profile.png`)

### What works

- The revised screen is dense, legible, and task-oriented.
- Norms, component variance, findings, pair distances, and group comparison are sensible first-line views.
- The facts strip communicates sample and type efficiently.
- The findings list is much more useful than a generic scatterplot landing page.

### Corrections and additions

- Implement P0-2 finding subjects.
- Label every distribution with its metric and scope.
- `Sampled pair distances` is descriptive, not a quality score. Add explanatory copy in its details, not the main chrome.
- Centroid-distance outliers can overflag valid minority clusters. State the method and offer a local-density or k-nearest-neighbor outlier method as a later option.
- `Near-constant dimensions` should say `Low-variance dimensions in this sample`. Low variance is not universally a defect.
- Exact duplicate detection must say whether equality is:
  - byte-equal float payload;
  - component-equal numeric values;
  - normalized-equal within tolerance.
- Near-zero thresholds must be disclosed and metric-specific.
- Non-finite components should be supported as a provider or harness test only until the server ingestion matrix proves they can be stored through supported SQL paths.
- Group comparison must show sample size per group and indicate when a small group makes the result unstable.
- Add provenance and freshness findings from P1-4.
- Add RAG-specific findings from P1-3:
  - repeated boilerplate text;
  - adjacent chunk crowding;
  - same-document top-K concentration;
  - hub rows;
  - near-duplicate chunks.
- Add an option to profile by language, tenant, source system, document type, and embedding batch.

### Suggested findings taxonomy

```text
Transport and shape
  Null or unavailable vectors
  Wrong or mixed dimensions
  Non-finite components
  Zero and near-zero vectors

Distribution
  Norm outliers
  Low-variance dimensions
  Strong anisotropy
  Centroid or local-density outliers

Duplication and crowding
  Exact vector duplicates
  Near-duplicate vectors
  Duplicate source text
  Adjacent-chunk crowding
  Hub rows

Provenance and freshness
  Source newer than embedding
  Mixed model or preprocessing profiles
  Missing embedded timestamp
  Declared dimension mismatch

Group behavior
  Unusual within-group distances
  Weak label neighborhood agreement
  Cross-tenant or cross-security-boundary neighbors
```

### Acceptance tests

- Clean normalized corpus.
- Null, zero, and near-zero rows.
- Exact duplicate groups covering multiple rows.
- Low-variance dimensions.
- A valid minority cluster far from the global centroid.
- One category with higher internal spread.
- Boilerplate chunks shared by many documents.
- Stale source text after embedding.
- Mixed model provenance with equal dimensions.

## 5.4 Profile finding drawer (`vec_profile_findings.png`)

### What works

- The right-side drawer preserves the main analysis context.
- The row table and action bar make findings actionable.
- The drawer is a good pattern for Search, Projection, and Pipeline details too.

### Corrections and additions

- The drawer title and columns must depend on finding subject.
- A duplicate finding should show groups, group leaders, group size, and representative members, not one undifferentiated row list.
- A dimension finding should show dimension, variance, range, and optional representative rows.
- A group finding should show compared group statistics and sample sizes.
- Disable or replace row actions when the finding is not row-oriented.
- Keep selection and keyboard focus stable when the drawer opens and closes.
- Add an expandable `Method and threshold` section.
- `Reveal in Results` must map result ordinals through local grid sort/filter and preserve filters.
- `Use as query` should say which vector becomes the query when multiple rows are selected.
- Add export of finding keys or generated validation SQL, not raw vectors by default.

## 5.5 Search composer (`vec_search.png`)

### What works

- The source tabs are appropriate.
- Exact, approximate, and forced ANN are visible choices.
- Metric, K, filters, isolated-session disclosure, and statement-count estimate make the operation legible.
- The empty state teaches the purpose without permanent decorative chrome.

### Corrections and additions

- Add P0-6 self-match and exclusion policy.
- Add P0-7 read consistency.
- Add P0-10 query-vector reuse.
- Exact must be mandatory whenever recall is requested.
- Approximate and forced ANN must be capability-gated separately.
- Filters must come from a structured builder and parameterized SQL. Do not concatenate a free-form predicate into automated comparison queries.
- Show eligible-row count or estimated filter selectivity when obtainable at acceptable cost.
- Block dimension mismatch before running.
- Warn on provenance mismatch even when dimensions match.
- Text-with-model must use the same model-call confirmation pattern as Pipeline.
- Paste-vector mode must validate JSON size, dimension count, numeric finiteness, and base type without evaluating arbitrary code.
- Expression mode remains local and must visibly lose or synthesize provenance.
- Add a query-set mode placeholder now, even if disabled until P1.

### Acceptance tests

- Selected row, source row included and excluded.
- Exact duplicates included and excluded.
- Text query with successful model call.
- Text query with model permission denied.
- Pasted vector with wrong dimensions.
- Expression result normalized and unnormalized.
- Structured filter with quotes and parameters.
- Selective filter on latest iterative index.
- Selective filter on earlier post-filter index.
- No compatible index.
- Metric mismatch.
- Connection with only exact search available.

## 5.6 Search results (`vec_search_results.png`)

### What works

- The facts strip is excellent.
- The Evidence block is the defining product element.
- Execution path, filter semantics, staleness, syntax probes, and recall denominator are the right facts.
- The rank grid and rank-flow companion are practical.
- `Open repro script` is a high-value professional action.

### Corrections and additions

- Add read consistency and self-exclusion evidence.
- Add query-vector source and digest summary.
- Add eligible-row count and filter selectivity.
- Add plan-capture state and whether ANN proof came from forced syntax, an approved plan pattern, or neither.
- Add single-observation versus repeated timing mode per P0-9.
- The grid must be the full union of exact and approximate results. It must show both exact-only and approximate-only rows.
- Preserve exact distance and approximate distance separately.
- Explain ties and deterministic secondary ordering.
- When exact returns fewer than K eligible rows, use the actual exact count as denominator and say why.
- For earlier index versions, show the `TOP_N` oversampling multiplier and post-filter semantics.
- Stamp staleness at run time, not only the last opened Index workspace value.
- Add unique-document and same-document concentration metrics for RAG.
- A forced ANN failure should remain a diagnostic result, not collapse into a generic error toast.
- Repro scripts must contain the exact parameters and filters, but redact secrets and avoid embedding remote source text unless the user explicitly asks to include it.

### Acceptance tests

- Perfect recall.
- Exact-only and approximate-only rows.
- Rank movement with identical overlap.
- Fewer-than-K due to filter selectivity.
- Forced ANN confirmed.
- Forced ANN unavailable.
- Approximate syntax accepted but exact fallback selected by optimizer.
- Index staleness nonzero.
- Concurrent DML under read committed disclosure.
- Earlier-index post-filtering returning fewer rows.
- Ties at equal distances.

## 5.7 Compare workspace (`vec_compare.png`)

### What works

- The basket and A/B/C metaphor are clear.
- Pairwise distances, summary statistics, top component differences, contributions, arithmetic, and nearest rows make this a real laboratory.
- The warning around experimental arithmetic is appropriately restrained.

### Corrections and additions

- State whether dimensions are numbered from 0 or 1. SQL and array conventions differ.
- The `Top contributions` formula must be metric-aware and visible in details.
- For cosine, explain whether contributions use normalized vectors and how they sum to similarity or distance.
- `Nearest bound rows` is a new server query, not a local computation. Label its evidence source separately.
- `Compatible` must not mean only dimensions and base type. Use:
  - `dimension-compatible`;
  - `provenance-compatible`;
  - `provenance unknown`;
  - `incompatible model or preprocessing`.
- Allow the pairwise matrix metric to be selected or clearly state it inherits the workspace metric.
- Arithmetic output must show norm, normalization, dimension, and provenance status.
- Expression parsing must be a small audited grammar and never `eval`.
- Add a local simulated float16 round-trip experiment as a P2 feature.
- Add top signed component contributions for the selected pair, but warn that latent dimensions usually do not have human labels.

### Acceptance tests

- Two and three vectors.
- Different dimensions.
- Same dimensions, mixed provenance.
- Zero vector with cosine unavailable.
- Normalized and unnormalized pairs.
- Expression parse error.
- Arithmetic output used as Search query.
- Nearest-bound-rows query canceled.

## 5.8 Projection workspace (`vec_projection.png`)

### What works

- The truth banner is outstanding.
- The screen clearly separates projected coordinates from original-space distance and ranking.
- PCA, explained variance, category coloring, legend, point list, fit, and zoom are appropriate.
- The layout now fills the result pane rather than imitating a report page.

### Corrections and additions

- Resolve P0-8 analysis-versus-render count.
- Label axes `PC1` and `PC2` even when tick labels are hidden.
- Report centering, normalization, seed, and PCA method in a details popover.
- Keep the third explained-variance component in the banner as already proposed.
- Add lasso selection, keyboard selection through the point grid, and Reveal in Results.
- Add legend filtering without silently recomputing the projection.
- Offer original-space nearest-neighbor lines for selected points.
- Consider a neighborhood-preservation score as an advanced fact, not a universal quality grade.
- Explain that category separation can reflect source text, metadata leakage, language, or preprocessing and does not by itself prove retrieval quality.
- Display subsampling must remain deterministic and disclosed.
- Canvas selection and the virtualized point grid must remain synchronized and accessible.

### Acceptance tests

- Clean separated clusters.
- Overlapping categories.
- One outlier far from all points.
- 5,000 analyzed, 1,200 rendered.
- All points rendered.
- Category filter and lasso.
- Same seed stable projection sign/orientation.
- Cancellation and recompute.
- High contrast and screen-reader point navigation.

## 5.9 Index workspace (`vec_index.png`)

### What works

- Properties, findings, script commands, and generated SQL are the right architecture.
- `Generated - never executed by this pane` is essential.
- Metric compatibility, forced ANN support, staleness, and traditional support-index review are useful findings.
- The split layout suits a DBA workflow.

### Corrections and additions

- Implement P0-3 separate healthy and legacy states.
- Add engine/platform because latest v3 availability currently differs by target.
- `Rows indexed` and `0 pending` are not direct fields in the documented health DMV. Label values as:
  - eligible non-null vector rows;
  - estimated pending changes;
  - or direct DMV values, depending on the actual query.
- Add all current health fields:
  - last background task duration;
  - processed inserts;
  - processed deletes;
  - last task error message.
- Use documented staleness guidance as attributed context, not a universal rebuild threshold.
- Add limitations and review scripts for:
  - clustered primary key requirement;
  - at least 100 non-null vectors;
  - no partitioning;
  - no replication to subscribers;
  - `TRUNCATE TABLE` blocked while index exists;
  - DacPac/BACPAC import and deployment constraints;
  - earlier-index read-only or stale-index behavior;
  - full DML on current format where supported.
- `Edition gate` must be probed, not hardcoded from mock data.
- A supporting relational index suggestion must be tied to observed filter columns or user-declared workload, not generated as a universal recommendation.
- Health-history UI must say `Current snapshot only` until persisted history exists.
- Migration SQL must prominently state service impact and never be the default action on a healthy index.

### Acceptance tests

- No vector index.
- Healthy latest index.
- Earlier format index.
- Metric mismatch.
- Health DMV unavailable by target.
- Health DMV permission denied.
- Background task failure.
- High staleness during a batch load.
- Sustained staleness after load.
- Fewer than 100 non-null rows.
- Partitioned table.
- Missing clustered primary key.

## 5.10 Pipeline workspace (`vec_pipeline.png`)

### What works

- Provenance and re-embedding are correctly paired.
- The source text preview, explicit action, stored-versus-fresh metrics, neighbor overlap, rank movement, and chunk ribbon are genuinely useful.
- The fixed-character chunk copy is accurate and important.
- The lower ribbon makes overlap visible without pretending it is token-aware.

### Corrections and additions

- Implement P0-4 external model naming.
- Label provenance source:
  - catalog fact;
  - workspace profile;
  - SQL extended property;
  - inferred binding;
  - user-entered declaration.
- `Cosine (stored -> fresh)` must say `Cosine distance` or `Cosine similarity`, not simply `Cosine`.
- State the retrieval mode used for neighbor overlap and rank movement.
- Validate fresh embedding dimensions before comparison or storage.
- Record model modify time and parameters digest with the run.
- Do not send a truncated result-cell prefix to a model. Fetch the full source by verified key with disclosure, or block the action.
- The chunk ribbon should show:
  - source length;
  - chunk order;
  - start offset;
  - chunk length;
  - overlap characters;
  - tail chunk;
  - chunk-set ID where enabled;
  - coverage gaps or repeated spans.
- `Generate embeddings for chunks` must confirm the number of chunks and expected model calls.
- Add token-limit and model-side truncation caution. SQL fixed chunks are character-based, while embedding endpoints commonly enforce model-specific token limits.
- Add batch drift sampling as a visible Pipeline subflow or fast-follow.
- Add preprocessing templates, especially query/passsage prefixes for models that expect them.
- Add source freshness and model-provenance findings.

### Acceptance tests

- Stored and freshly generated embeddings nearly identical.
- Stale stored embedding with large drift.
- Wrong source column.
- Changed preprocessing template.
- Model output dimension mismatch.
- Truncated source cell.
- Chunk tail and overlap.
- Empty source text.
- Model permission denied.
- Endpoint timeout and retry.
- Cancellation during a multi-chunk run.

## 5.11 Re-embed confirmation dialog (`vec_pipeline_regen.png`)

### What works

- The dialog has the right friction level.
- It discloses model, API format, endpoint host, source, rows/calls, text characters, payload estimate, execution path, and result handling.
- `View generated T-SQL` is exactly the right secondary action.

### Corrections and additions

- Replace schema-qualified model display.
- Add model modify time and parameters digest.
- Add retry count and maximum possible attempts.
- Add egress class and use copy specific to remote, host-local, or ONNX execution.
- Add source sensitivity or classification when available, without pretending it is complete.
- Add whether full source text was fetched from the table and by which verified key.
- Add cancellation semantics: cancellation is requested, but a remote endpoint call may already be in flight.
- Add output dimension expectation.
- For N chunks, show N calls or the actual provider batching plan.
- Keep the primary action explicit: `Generate embedding` or `Generate N embeddings`.

## 6. Cross-workspace contracts that need to be explicit

### 6.1 Evidence identity

Every displayed fact should carry an internal evidence record.

```ts
export interface VectorEvidenceRecord {
    readonly evidenceId: string;
    readonly kind:
        | "capturedResult"
        | "catalog"
        | "healthDmv"
        | "diagnosticQuery"
        | "modelCall"
        | "localComputation"
        | "interpretation";
    readonly createdEpochMs: number;
    readonly sourceDescription: string;
    readonly sampled?: boolean;
    readonly partial?: boolean;
    readonly partialReason?: string;
    readonly statementDigest?: string;
    readonly inputDigest?: string;
}
```

The footer `Evidence` control should open a list of these records for the current workspace.

### 6.2 Provenance compatibility

Use separate states:

```ts
export type VectorCompatibility =
    | "incompatibleDimensions"
    | "incompatibleBaseType"
    | "dimensionCompatibleProvenanceUnknown"
    | "provenanceMismatch"
    | "compatibleByDeclaredProfile"
    | "compatibleByVerifiedRegeneration";
```

Do not show a green `provenance match` merely because two vectors have 1,536 components.

### 6.3 Partial and approximate language

Every partial result must state:

- what was scanned;
- what was accepted;
- what was skipped;
- what remains unknown;
- why work stopped.

Every approximate result must state:

- algorithm or execution mode requested;
- execution strategy proven, unproven, or exact fallback;
- recall denominator;
- index version;
- filter semantics;
- staleness at run time when available.

### 6.4 Security and permission inheritance

Diagnostic queries and model calls must execute under the current user's effective database permissions. Do not use a privileged metadata or service connection that can see rows the user cannot see.

A dedicated auxiliary session may share the same saved connection profile and authentication material, but it must not elevate principal, bypass row-level security, ignore session context, or omit user-required session setup. If the current user session has meaningful `SESSION_CONTEXT`, temporary tables, or uncommitted data that the isolated session cannot see, disclose the isolation boundary.

### 6.5 Reproducibility bundle

A completed experiment should be able to generate a local, reviewable repro script containing:

- capability and version checks;
- table and vector-column identity;
- exact query;
- approximate query;
- forced ANN query where supported;
- structured filters;
- exclusion predicate;
- index metadata query;
- health query;
- model metadata query when relevant;
- comments with sample method, staleness, and read consistency;
- no secrets or raw remote source text by default.

## 7. Demo and test cases that must exist before preview

The companion guide provides detailed execution. This section is the minimum product matrix.

`VTEST` identifies preview acceptance scenarios. `VEC-0..VEC-12` is reserved for implementation checkpoints; similarly numbered checkpoint and test IDs have no implied completion relationship.

| ID | Scenario | Primary workspace | Required proof |
| --- | --- | --- | --- |
| VTEST-01 | Native vector detection and transport | Profile | Dimensions and float32 are preserved without JSON inflation in supported path |
| VTEST-02 | Clean normalized clustered corpus | Profile, Projection | No false universal error; clusters and norms display honestly |
| VTEST-03 | Null, zero, and near-zero vectors | Profile | Counts and row drawer are correct |
| VTEST-04 | Exact duplicate vector groups | Profile | Group count and covered-row count differ correctly |
| VTEST-05 | Low-variance dimensions | Profile | Subject is dimension, not row |
| VTEST-06 | Group distribution shift | Profile | Group sizes and within-group distances are shown |
| VTEST-07 | Compare three vectors | Compare | Metrics, matrix, medoid, closest pair, and expression work |
| VTEST-08 | PCA analysis versus display cap | Projection | Analyzed and rendered counts are separate |
| VTEST-09 | Exact selected-row search | Search | Self-exclusion is explicit and exact top K is reproducible |
| VTEST-10 | Current-format ANN comparison | Search, Index | Forced ANN evidence, recall, staleness, and iterative filtering are shown |
| VTEST-11 | Earlier-index post-filter behavior | Search, Index | TOP_N oversampling and fewer-than-K behavior are disclosed |
| VTEST-12 | No index or metric mismatch | Search, Index | Exact fallback or warning is represented honestly |
| VTEST-13 | Healthy index state | Index | Migration command is absent |
| VTEST-14 | Legacy migration state | Index | Service-impact warning and generated script appear |
| VTEST-15 | Re-embed selected source | Pipeline | One confirmed model call, egress disclosure, dimension validation |
| VTEST-16 | Source text changed after embedding | Pipeline, Profile | Drift and freshness finding are visible |
| VTEST-17 | Character chunking with overlap | Pipeline | Offsets, lengths, overlap, tail, and call count are visible |
| VTEST-18 | Permission-degraded metadata | All | Catalog or DMV unavailable states remain useful |
| VTEST-19 | Cancellation and rerun | All | Sessions, leases, workers, and results clean up |
| VTEST-20 | Pinned results | Profile, Compare, Projection | Detached mode survives source rerun or editor close |
| VTEST-21 | Query-set recall harness | Search | Distribution, worst queries, and statement budget are reported |
| VTEST-22 | Tenant and ACL filter | Search | Current principal and filter semantics are preserved |

## 8. Readiness gates

### 8.1 Ready for coding-agent PR 1 when

- The previous platform prerequisites remain accepted.
- P0-1 through P0-10 are incorporated into the normative specs or issue list.
- The Index mockups are split into healthy-current and earlier-format states.
- External model naming is corrected.
- Finding subjects are typed.
- Search exclusion and read-consistency policies are specified.
- Projection analysis and render counts are separated.
- The footer network copy is layered.

### 8.2 Ready for UI vertical slice when

- Typed vector transport and ordinary result-cell safety are complete.
- Compact capture privacy is fixed and canary-tested.
- Query Studio CSP is in place.
- Host analysis sessions, sparse projection, cancellation, and budgets pass tests.
- The UX can render all error, partial, permission, and unsupported states without inventing data.
- The synthetic demo corpus produces stable Profile, Compare, Projection, and exact Search results.

### 8.3 Ready for table-bound Search preview when

- Exact and approximate statements use the same frozen query vector, metric, filter, exclusion, and read view.
- Version-specific syntax and filter semantics are probed.
- Forced ANN evidence is correctly classified.
- Staleness is stamped at run time.
- Rank union and recall denominator tests pass.
- Repro script output matches executed SQL.

### 8.4 Ready for Pipeline preview when

- Model execution permission and type are checked.
- Remote versus host-local versus ONNX egress copy is correct.
- Full source text handling is honest.
- Model output dimensions are validated.
- Every model call requires explicit confirmation.
- No model secret, source text, or returned vector enters logs or telemetry.
- Cancellation and retry behavior are tested.

## 9. Recommended implementation ordering adjustments

Keep the prior PR plan, with these additions:

1. Add finding subject types and source-mode evidence contracts before the Profile UI.
2. Add external-model identity and egress classification to the capability probe before Pipeline UI.
3. Add Search exclusion policy and read-consistency result fields before the SQL builder is implemented.
4. Add a separate Index state machine before script commands are wired.
5. Add analysis-count versus render-count fields before Projection first paint.
6. Add the query-set and K-sweep shapes to the saved experiment schema even if their UI ships later.
7. Add the synthetic corpus and deterministic expected results before a coding agent implements chart and finding logic.

## 10. Final assessment

This is now a compelling product, not a fashionable visualization panel.

The revised UX has the correct professional posture:

- It starts with evidence.
- It names exact ground truth.
- It refuses to claim ANN without proof.
- It exposes generated SQL.
- It separates local computation from server execution.
- It treats model calls as data-egress events.
- It preserves the normal Results grid as the authoritative tabular view.
- It uses projection as an exploration aid rather than a verdict machine.

The remaining work is to make the labels as rigorous as the architecture. Once the P0 semantic corrections are applied, the feature is ready for staged end-to-end implementation by coding and design agents, with human review at each protocol, SQL-generation, and security boundary.

## 11. Primary references reviewed

All links were checked against Microsoft documentation current on 2026-07-11.

- [Vector data type](https://learn.microsoft.com/en-us/sql/t-sql/data-types/vector-data-type?view=sql-server-ver17)
- [Vector functions](https://learn.microsoft.com/en-us/sql/t-sql/functions/vector-functions-transact-sql?view=sql-server-ver17)
- [VECTOR_DISTANCE](https://learn.microsoft.com/en-us/sql/t-sql/functions/vector-distance-transact-sql?view=sql-server-ver17)
- [VECTOR_SEARCH](https://learn.microsoft.com/en-us/sql/t-sql/functions/vector-search-transact-sql?view=sql-server-ver17)
- [CREATE VECTOR INDEX](https://learn.microsoft.com/en-us/sql/t-sql/statements/create-vector-index-transact-sql?view=sql-server-ver17)
- [sys.vector_indexes](https://learn.microsoft.com/en-us/sql/relational-databases/system-catalog-views/sys-vector-indexes-transact-sql?view=sql-server-ver17)
- [sys.dm_db_vector_indexes](https://learn.microsoft.com/en-us/sql/relational-databases/system-dynamic-management-objects/sys-dm-db-vector-indexes-transact-sql?view=sql-server-ver17)
- [CREATE EXTERNAL MODEL](https://learn.microsoft.com/en-us/sql/t-sql/statements/create-external-model-transact-sql?view=sql-server-ver17)
- [sys.external_models](https://learn.microsoft.com/en-us/sql/relational-databases/system-catalog-views/sys-external-models-transact-sql?view=sql-server-ver17)
- [AI_GENERATE_EMBEDDINGS](https://learn.microsoft.com/en-us/sql/t-sql/functions/ai-generate-embeddings-transact-sql?view=sql-server-ver17)
- [AI_GENERATE_CHUNKS](https://learn.microsoft.com/en-us/sql/t-sql/functions/ai-generate-chunks-transact-sql?view=sql-server-ver17)
