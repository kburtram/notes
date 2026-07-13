# Query Studio Vector Workbench - UX and Interaction Specification

**Status:** Implementation-ready design specification  
**Date:** 2026-07-10  
**Target branches:** `microsoft/vscode-mssql@dev/query`, `microsoft/sqltoolsservice@dev/query`  
**Primary surface:** Query Studio results pane  
**Visible tab label:** `Vector`  
**Pane product name:** `Vector Workbench`  
**Primary audience:** UX designers, product designers, accessibility reviewers, engineers, and AI design agents producing production mockups

## 0. Purpose and precedence

This document defines the user experience for a native SQL Server and Azure SQL vector analysis and debugging surface inside Query Studio. It is intended to be detailed enough for a design agent to produce complete responsive mockups, interaction states, component specifications, and accessibility annotations without inventing core behavior.

The companion implementation document, `query_studio_vector_workbench_implementation_plan.md`, is normative for data contracts, service ownership, budgets, SQL generation, security, and code sequencing. Where a visual idea conflicts with a technical safety or truthfulness rule in that document, the implementation rule wins.

The implementation should follow the result-pane architecture and quality bar established by the existing Query Studio geospatial design documents:

- `geospatial_pane(1).md`
- `geospatial_pane_execution_addendum(1).md`

This is not a generic machine-learning dashboard. It is a SQL-aware diagnostic workbench for people who need to explain why vector data or vector search behaves the way it does.

## 1. Executive product recommendation

Build a conditional **Vector** tab as a sibling of Results, Messages, and Query Plan. The tab opens a full-width **Vector Workbench** with six task-oriented workspaces:

1. **Profile** - determine whether the stored vectors look structurally healthy.
2. **Search** - compare exact, optimizer-selected, and forced approximate retrieval.
3. **Compare** - inspect selected vectors, pairwise distances, neighbors, and experimental arithmetic.
4. **Projection** - explore a deterministic PCA projection while preserving original-space truth.
5. **Index** - inspect DiskANN metadata, version, maintenance state, compatibility, and generated repair scripts.
6. **Pipeline** - inspect provenance, chunking, re-embedding, and drift through explicit model calls.

The default workspace is **Profile**, not Projection. The product promise is:

> Select a vector result, understand its data quality, bind it to a table when database context is needed, compare exact and approximate retrieval, inspect the index and embedding pipeline, and retain a direct path back to the source rows and generated T-SQL.

The experience must make five kinds of truth visually distinct:

- facts from the captured query result;
- facts from catalog or DMV queries;
- results from newly executed diagnostic SQL;
- results computed locally from a bounded sample;
- interpretations or warnings inferred from those facts.

A colorful point cloud without those boundaries would be a constellation-shaped lie detector that forgot the detecting part.

## 2. Research conclusions that shape the UX

### 2.1 The SQL surface is broader than a viewer

The current SQL surface supports native vector columns, exact distance functions, approximate search, vector indexes, index health metadata, vector norms and normalization, external embedding models, embedding generation, and fixed-size chunk generation. Some capabilities remain preview features and can vary by platform, region, database configuration, and vector-index version.

The UX must therefore discover capabilities at runtime and explain unavailable actions. It must not assume that every SQL Server 2025 or Azure SQL database exposes the same vector feature set.

### 2.2 Generic embedding projectors solve only one slice

Generic tools commonly offer PCA, UMAP, t-SNE, color-by-metadata, selection, and original-space nearest neighbors. Those ideas are useful references for the Projection workspace. They do not understand SQL result ownership, relational filters, exact versus approximate recall, vector-index versions, query plans, external model objects, server permissions, transaction isolation, or generated T-SQL.

The Query Studio differentiator is not a prettier scatterplot. It is a coherent debugger that joins the relational, vector, index, model, and execution layers.

### 2.3 Projection is evidence, not ground truth

A 2D projection distorts a high-dimensional space. The Projection workspace must always show:

- projection method and preprocessing;
- sample method, sample count, and deterministic seed;
- explained variance for PCA;
- original-space metric used for neighbor calculations;
- a persistent statement that projection coordinates are not the distance used by SQL search.

### 2.4 Model calls are data egress operations

`AI_GENERATE_EMBEDDINGS` can invoke a configured endpoint from the database engine. The user must see which model object is used, what text or rows will be sent, how many calls are expected, and that source data may leave the database environment. Opening the pane must never invoke a model.

### 2.5 Exact versus approximate comparison is the flagship workflow

Exact `VECTOR_DISTANCE` results provide a practical ground truth for evaluating approximate retrieval. The Search workspace should make recall loss, rank movement, fallback, index compatibility, and plan evidence understandable without requiring a notebook export.

## 3. Goals and non-goals

### 3.1 Goals

| ID | Goal |
| --- | --- |
| UX-G1 | Make vector result columns discoverable without auto-opening or changing the user query. |
| UX-G2 | Provide useful detached analysis from the retained result snapshot. |
| UX-G3 | Add database-aware debugging only after an explicit table binding. |
| UX-G4 | Make exact versus approximate search quality and execution evidence the primary advanced workflow. |
| UX-G5 | Keep every computed result scoped as full, sampled, scanned-prefix, approximate, or partial. |
| UX-G6 | Link every visual point, comparison item, and search result to a stable result-row or table key identity. |
| UX-G7 | Show generated T-SQL for every server-side experiment and never execute DDL automatically. |
| UX-G8 | Make the core workflow complete with keyboard and screen-reader access; canvas is never the sole interface. |
| UX-G9 | Work fully offline in the webview. Only explicit database operations may cause server-side endpoint calls. |
| UX-G10 | Remain useful when vector indexes, model objects, preview features, permissions, or typed driver transport are unavailable. |

### 3.2 Non-goals for the first release

- Editing vector components in place or writing results back to a table.
- A general-purpose notebook, model playground, or chat interface.
- Automatic semantic labels for clusters.
- Automatic index creation, drop, rebuild, or migration.
- Automatic model calls when the pane opens, when selection changes, or when a profile loads.
- UMAP, t-SNE, 3D projection, animated embeddings, or GPU particle effects in MVP.
- Inferring that arbitrary JSON arrays are vectors without an explicit advanced action.
- Treating vector arithmetic as a supported SQL operator or a guaranteed semantic analogy.
- A single numeric “similarity percentage” that hides the selected metric.
- Claiming that a query used ANN when the evidence does not prove it.
- Silently normalizing, sampling, filtering, quantizing, repairing, or excluding rows.
- Sending result data to extension telemetry, diagnostics, performance markers, or web services.

## 4. Users and jobs to be done

### 4.1 Database administrator or performance engineer

Needs to answer:

- Does a compatible vector index exist?
- Which index version is present?
- Is background maintenance succeeding?
- Did approximate search actually use an ANN strategy?
- How much recall and rank quality is traded for latency?
- Are relational predicates or missing supporting indexes changing the result?
- What safe script should be reviewed to create or migrate an index?

### 4.2 Application or retrieval engineer

Needs to answer:

- Are these embeddings zero, duplicated, stale, or generated from the wrong text?
- Does the selected distance metric fit the model and stored data?
- Which exact neighbors are missing from approximate search?
- How do chunking, model choice, or preprocessing change retrieval?
- Which rows are outliers and what source text produced them?

### 4.3 Data engineer

Needs to answer:

- Are dimensions and base type consistent?
- Did a batch load produce a distribution shift?
- Which groups, tenants, languages, or sources behave differently?
- Would float16 storage materially change neighborhood results?
- Can a reproducible diagnostic query be handed to another engineer?

### 4.4 Query Studio user exploring an arbitrary result

Needs to answer:

- What is in this vector cell?
- How is it related to selected rows?
- What does a bounded PCA view reveal?
- Can the selected point be revealed in the current Results grid?
- What additional table binding is required for database-aware tools?

## 5. Terminology and mental model

| Term | UX meaning |
| --- | --- |
| Vector result | A query result set containing at least one metadata-confirmed vector column or a metadata-confirmed driver text fallback. |
| Detached mode | Analysis performed only on the retained live or pinned result data. No SQL is executed. |
| Table-bound mode | A verified mapping to a base table, vector column, key columns, and optional source/model metadata. Database-aware operations become available. |
| Query vector | The vector used as the search target. It can come from a selected row, pasted JSON, local arithmetic, a centroid, or an explicit embedding call. |
| Exact result | Retrieval ordered by exact `VECTOR_DISTANCE` computation. |
| Approximate result | Retrieval requested with `VECTOR_SEARCH` approximate syntax. The actual execution strategy can still require evidence. |
| Forced ANN | Approximate retrieval using `FORCE_ANN_ONLY`. A successful execution is strong evidence that an ANN path was used. |
| Original space | The full-dimensional vector space in which SQL distance functions operate. |
| Projection space | A derived 2D coordinate system used only for visualization. |
| Result row ordinal | Zero-based row identity in the bound live or pinned result view. It is not necessarily the currently displayed grid row after local sort or filter. |
| Table key | One or more base-table columns used to compare and reveal database search results. |
| Provenance profile | Local metadata connecting a vector column to source text, model, metric, chunk policy, and timestamps. |
| Observed scope | The rows actually scanned or sampled by an operation. |

## 6. Eligibility and capability ladder

### 6.1 When the Vector tab appears

For the initial preview, show the Vector tab only when all of these are true:

1. `mssql.queryStudio.vectorWorkbench.enabled` was enabled before the query began, so Query Studio requested the typed transport during execution.
2. STS2 advertised and negotiated the vector binary contract.
3. At least one terminal, non-plan result set contains a metadata-confirmed `float32` vector column delivered as `binary-v1`.
4. The retained result is available for bounded analysis.

Do not show the tab merely because a string contains a JSON array. Do not show it for a metadata-confirmed text-fallback result until the product has a real limited-mode experience that offers useful metadata, binding, and controlled conversion. A pane containing only "rerun with the feature enabled" is not that experience.

Opening Vector never enables typed transport. Changing the feature setting after a run cannot retrofit typed cells into that retained result; a later execution uses the new setting. This avoids an open-tab-then-rerun workflow.

### 6.2 Capability levels

The pane should present a capability badge near the title and expose details in an information popover.

| Level | Badge | Available experience |
| --- | --- | --- |
| A | `Typed result` | Full detached Profile, Compare, and PCA analysis for supported float32 cells. |
| B | `Vector text fallback` | **Future limited mode, not initial-preview eligibility.** Metadata and ordinary result inspection remain available in Results; when implemented, offer table binding for controlled JSON conversion. |
| C | `Table bound` | Search, Index, and server-side vector math are available according to runtime probes and permissions. |
| D | `Model enabled` | Explicit embedding, chunking, re-embedding, and drift operations are available. |
| E | `Limited permissions` | Show available metadata and a precise permission explanation. Do not turn the whole pane into an error state. |

### 6.3 Capability details popover

The popover lists facts, not marketing labels:

```text
Vector result transport     Native float32 binary
Dimensions                  1,536
Base type                   float32
Table binding               dbo.DocumentChunks.embedding
Exact distance              Available
Approximate search          Available, preview
Vector index                vec_DocumentChunks_embedding, version 3
Index health DMV            Permission available
Embedding model             dbo.TextEmbedding3Small
Chunk generation            Available
Diagnostic session          Isolated connection
```

Unavailable entries include a concise reason and a `View generated check` action when useful.

## 7. Results-pane integration

### 7.1 Tab order

When eligible:

```text
Results | Messages | Vector | Query Plan
```

Results is the only tab allowed before Messages. Vector and every other contributed result tab appear to the right of Messages. The older mockup tab strips are superseded by this rule.

Rules:

- Vector never auto-opens.
- Existing error-driven switches to Messages and plan-driven switches to Query Plan remain unchanged.
- If the currently selected result disappears after rerun, Vector falls back to the first eligible result or Results when none remain.
- A pinned result document uses the same Vector tab and component, with database-aware actions disabled until the user explicitly binds it to a live connection and table.

### 7.2 Entry points

| Surface | Action |
| --- | --- |
| Vector cell context menu | `Inspect in Vector Workbench` |
| Multiple selected vector cells or rows | `Compare in Vector Workbench` |
| Vector column header | `Open Vector Workbench` |
| Result-grid caption | Vector icon button when the result has eligible columns |
| Results tab overflow | `Open Vector Workbench` |
| Object Explorer table context, later milestone | `Open Vector Workbench for column` |

Opening from a cell preselects the result set, vector column, and result-row ordinal. Opening from a multi-selection seeds the Compare basket. Opening from the tab restores the last valid panel-local workspace.

### 7.3 Results-pane sizing

Vector fills the available results body and participates in the existing splitter and maximize behavior. It is not a third Grid/Text display mode. Grid/Text continues to belong to Results.

The pane must remain usable at a minimum content height of 240 CSS pixels. Below that height, secondary inspectors collapse into drawers and charts show a compact state rather than overlapping controls.

## 8. Pane shell and responsive layout

### 8.1 Wide layout, 960 CSS pixels or more

```text
+--------------------------------------------------------------------------------+
| Results | Messages | Vector | Query Plan                              [restore] |
+--------------------------------------------------------------------------------+
| Vector Workbench  [Result 1] [embedding] [Table bound] [Sample: 5,000] [...]   |
+------------------+-------------------------------------------------------------+
| Profile          |                                                             |
| Search           |                 active workspace                            |
| Compare          |                                                             |
| Projection       |                                                             |
| Index            |                                      optional inspector      |
| Pipeline         |                                                             |
+------------------+-------------------------------------------------------------+
| 5,000 sampled of 2.4M rows | 1,536 dimensions | float32 | No network requests |
+--------------------------------------------------------------------------------+
```

- Left workspace rail: 156 to 184 pixels, resizable only if existing pane conventions support it.
- Main content: fluid.
- Optional right inspector: 320 to 400 pixels, resizable and dismissible.
- Footer status: one line with overflow into a details popover.

### 8.2 Medium layout, 640 to 959 CSS pixels

- Workspace rail becomes a top segmented navigation or compact tab row.
- Inspector becomes an overlay drawer from the right.
- Summary cards reflow from four columns to two.
- Search comparison uses a tabbed Exact/Approximate result list plus a persistent comparison summary.

### 8.3 Narrow layout, under 640 CSS pixels

- Workspace choice becomes a labeled dropdown: `Workspace: Search`.
- Global selectors stack into two rows.
- Charts are followed immediately by their accessible data table.
- Search variants become vertically stacked cards.
- Projection canvas remains at least 240 pixels high and never hides the feature list.
- No horizontal page scrolling. Tables may scroll within their own labeled regions.

### 8.4 Global header controls

| Control | Default | Notes |
| --- | --- | --- |
| Result set | First eligible result | Shows ordinal, row count, complete/partial status. |
| Vector column | First eligible vector column | Shows dimensions and base type when known. |
| Binding badge | `Detached` | Opens binding summary or wizard. |
| Scope badge | `Sample` or `Full` | Opens scope details; never labels a partial scan as full. |
| Workspace overflow | Hidden on wide layouts | Includes reset workspace, copy diagnostics summary, help. |

The header does not contain analysis settings that belong to one workspace.

## 9. State and persistence

### 9.1 Panel-local state

Preserve user-modified view context per Query Studio panel while its run remains valid. This must survive Results/Messages/Vector/Query Plan switches and renderer or webview recreation. Split editors retain independent state over the same document and run.

The extension controller owns a versioned, bounded, memory-only snapshot. The renderer restores from it and coalesces updates back to it. This snapshot is never written to telemetry, diagnostics, replay, workspace settings, or durable mementos.

Preserve at least:

- shell: active result tab, results-pane height/collapse/maximize state, and maximized result grid;
- Results: per-grid selection, vertical and horizontal scroll, column widths, hidden/frozen columns, filters, sort, text-view selection and scroll, and the result-stack scroll position;
- Messages: vertical scroll and logical text-selection anchors expressed as message index plus character offset, never selected text;
- Vector shell: active workspace, selected result set and vector column, selected result-row ordinals, workspace scroll positions, and safe local chart preferences;
- Compare: basket, active pair/metric, and arithmetic editor state only when it contains no result-derived vector values;
- Projection: camera, color field, lasso/list selection, and open inspector; projection points themselves stay in the run-bound analysis result and are never durable state;
- Search: target binding identity, source-tab choice, metric, K, variants, plan/repetition options, structured-filter shape, inspector/drawer state, and other form values only when they contain no secret, pasted vector, model-source text, result label/key, or generated query vector;
- Index and Pipeline: selected inspector/script/view preferences and non-sensitive numeric controls; never generated SQL containing result values, source text, confirmation tokens, model results, or endpoint secrets;
- Query Plan: page and graph scroll, zoom, selected plan element, and properties-pane visibility and width.

Hiding a completed pane does not invalidate its completed local state. In-flight work may be canceled under the lifecycle policy, but returning to the pane restores the last honest completed state rather than silently presenting stale work as current or recomputing merely because a sibling tab was selected.

### 9.2 Run-bound invalidation

A new run invalidates:

- result-row selections;
- detached analysis results;
- projections;
- result-derived query vectors;
- result-bound table-binding verification.

It also clears run-bound grid/message/plan selections and nested Vector results. It may retain true panel preferences such as splitter size, preferred workspace, norm selector, or properties-pane width when those preferences contain no result data.

A saved provenance profile can be offered again, but it must be reverified against the current database and column metadata.

### 9.3 Local provenance persistence

A table binding and provenance profile can be saved locally for the workspace under a separate, explicit durable-persistence policy. The save dialog states that object and column names are stored locally. It does not modify the database, and a restored binding must be reverified.

No source text, vector values, pasted vectors, query vectors, model responses, projection points, search result keys/labels, confirmation tokens, or result-derived generated SQL are persisted durably by default.

## 10. Table binding experience

### 10.1 Why binding exists

An arbitrary result set may come from a CTE, stored procedure, expression, temporary table, join, or derived snapshot. The workbench must not pretend it can safely reconstruct a base-table search from a vector cell alone.

Detached tools are always available when the result data supports them. Search, Index, and most Pipeline actions require an explicit table binding.

### 10.2 Binding entry points

- `Bind to table` button in the capability badge.
- Locked Search, Index, or Pipeline workspace empty state.
- `Edit binding` in the pane overflow.
- Suggested binding banner when result metadata contains base-table lineage hints.

### 10.3 Binding wizard steps

#### Step 1: Choose database object

Fields:

- connection, read-only summary;
- database;
- schema;
- base table;
- vector column.

Only base tables are eligible for `VECTOR_SEARCH`. Views can be selected for detached metadata only and show that limitation.

Suggested lineage is labeled `Suggested from result metadata` and must be confirmed. The wizard verifies the object in catalog metadata before continuing.

#### Step 2: Choose identity and display

Fields:

- one or more key columns;
- label/display column;
- optional source-text column;
- optional group columns for analysis;
- optional embedding-generated timestamp column.

Primary-key columns are preselected when visible. A nonunique identity shows a warning and disables reliable recall comparison until corrected.

#### Step 3: Define vector expectations

Fields:

- expected metric: cosine, euclidean, or negative dot product;
- expected normalization: unknown, unit norm, or not normalized;
- optional external model object;
- optional source expression description;
- optional chunk size and overlap;
- optional notes.

The metric is a profile expectation, not a database constraint. The UI says so.

#### Step 4: Review and verify

Review includes:

- fully qualified object and vector column;
- dimensions and base type from catalog;
- key uniqueness status;
- compatible vector indexes and metrics;
- current permissions;
- model endpoint host or runtime type, without credentials;
- whether the diagnostic session is isolated from the current query session.

Actions:

- `Save locally and bind`
- `Bind for this panel only`
- `Back`

### 10.4 Binding badge states

| State | Badge | Meaning |
| --- | --- | --- |
| None | `Detached` | Result-only analysis. |
| Suggested | `Binding available` | Lineage hint exists but is unverified. |
| Verified | `Table bound` | Catalog verification succeeded. |
| Stale | `Binding changed` | Object metadata no longer matches saved profile. |
| Unavailable | `Binding unavailable` | Connection, permission, or object requirement failed. |

## 11. Profile workspace

### 11.1 Purpose

Profile answers: **Do the vectors look structurally suspicious, and where should I investigate first?**

It must not claim to diagnose semantic quality from geometry alone.

### 11.2 Default layout

```text
Profile
[Rows observed] [Dimensions] [Base type] [Null or unavailable]

Norms                                      Findings
+--------------------------------------+  +----------------------------------+
| histogram with norm1/norm2/norminf   |  | 12 exact duplicate groups        |
| selector and threshold markers       |  | 4 zero vectors                   |
+--------------------------------------+  | 17 centroid-distance outliers    |
                                          | 8 non-finite components          |
Component variance                        +----------------------------------+
+--------------------------------------+  [Inspect affected rows]
| highest and lowest variance dims     |
+--------------------------------------+

Distance sample              Group comparison                 Scope and method
```

### 11.3 Summary cards

| Card | Content |
| --- | --- |
| Rows observed | `5,000 sampled of 2,412,883`, or `12,450 full result`. |
| Dimensions | Expected dimensions plus mismatch count. |
| Base type | `float32 native`, `float16 text fallback`, or mixed/unavailable. |
| Availability | Null, unavailable, malformed, and analyzed counts. |

Cards are buttons only when they open a relevant filtered list. Static cards are not focusable.

### 11.4 Norm panel

Controls:

- norm selector: L2 default, L1, infinity;
- histogram bin count in overflow only;
- near-zero threshold with visible current value;
- optional expected unit norm reference line.

The panel displays median, p5, p95, minimum, maximum, and count near zero. It never labels non-unit vectors as wrong unless the provenance profile explicitly expects unit norm.

### 11.5 Findings panel

Findings are ordered by severity and evidence quality:

1. unreadable or dimension-mismatched cells;
2. non-finite values;
3. exact zero or near-zero vectors;
4. exact duplicate groups;
5. source-content conflicts when a table binding provides source text or key evidence;
6. centroid-distance outliers;
7. low-variance or constant dimensions;
8. group distribution differences.

Each finding includes:

- factual title;
- observed scope;
- count;
- method or threshold;
- `Inspect rows` action;
- optional `Why this matters` disclosure.

Avoid generated prose that sounds causal. Use wording such as `Possible stale or reused embeddings` rather than `Your model pipeline is stale`.

### 11.6 Component variance panel

Show two ranked lists or horizontal bars:

- ten highest-variance dimensions;
- ten lowest-variance dimensions.

Dimension labels use one-based human display, for example `Dimension 418`, while internal ordinals remain zero-based. A details action opens mean, standard deviation, min, max, and missing/non-finite counts.

### 11.7 Distance sample panel

Controls:

- metric: expected metric from binding, otherwise cosine default;
- deterministic pair sample count;
- optional compare within/between selected group field.

Show distribution, median, p5, p95, and sample method. The chart title states `Sampled pair distances`, never `All pair distances`.

### 11.8 Group comparison

When a scalar group column is selected:

- cap visible groups and fold the remainder into `Other`;
- show vector count, median norm, median within-group sampled distance, outlier rate, and nearest-neighbor label agreement when computed;
- disclose rows with null group labels;
- never claim a group is semantically coherent based only on projection.

### 11.9 Row inspector

Selecting a finding opens a resizable inspector with a virtualized row list:

- result-row ordinal or table key;
- bounded label;
- norm;
- reason;
- distance from centroid when applicable;
- actions: `Reveal in Results`, `Add to Compare`, `Use as query vector`, `Open source details`.

## 12. Search workspace

### 12.1 Purpose

Search answers: **What changes between exact and approximate retrieval, why did it happen, and what evidence supports the execution path?**

Search requires a verified base-table binding and a stable key.

### 12.2 Search composer

The composer has four query-vector source tabs:

1. **Selected row**
2. **Text with model**
3. **Paste vector**
4. **Expression**

#### Selected row

- shows result-row ordinal or table key, label, dimensions, base type, and provenance match;
- permits choosing among Compare basket entries;
- warns when the selected vector came from a different dimension or profile.

#### Text with model

- model selector contains verified external model objects;
- multiline source text field;
- optional model parameters JSON in an advanced disclosure;
- `Generate embedding` opens the model-call confirmation described in section 21;
- the generated vector is cached only for the current panel and displayed as a query-vector chip.

#### Paste vector

- accepts a JSON numeric array;
- validates syntax, dimensions, finite values, and base-type conversion;
- shows a bounded preview and normalized byte estimate;
- never accepts a generic object or nested array.

#### Expression

- uses vectors from the Compare basket with a constrained editor:

```text
normalize(A + B - C)
0.7 * A + 0.3 * B
centroid(A, B, C)
```

- syntax is locally parsed, not evaluated with JavaScript `eval`;
- dimensions and profile compatibility are validated;
- prominently marked `Experimental vector arithmetic`.

### 12.3 Search settings

| Setting | Default | Notes |
| --- | --- | --- |
| Metric | Binding expected metric | Labels dot as `Negative dot product`. |
| K | 20 | 1 to approved maximum. |
| Filter | None | Structured builder, not arbitrary SQL. |
| Variants | Exact + Approximate | Forced ANN is opt-in when supported. |
| Actual plan | On for debugger runs | Can be disabled for faster iteration. |
| Repetitions | 1 | Advanced, capped; first run can be treated as warmup only when explicitly selected. |

### 12.4 Structured filter builder

MVP supports AND-combined predicates over verified scalar table columns:

- equals, not equals;
- less than, less than or equal;
- greater than, greater than or equal;
- `IN` with a capped value list;
- is null, is not null.

The builder displays the generated predicate and typed variables. An `Open custom SQL experiment` action places editable SQL in an editor tab but removes it from automated recall comparison until rerun through a supported binding.

### 12.5 Run action

Primary action: `Run comparison`.

Secondary split actions:

- `Run exact only`
- `Run approximate only`
- `Run forced ANN`
- `Open generated T-SQL`

Before execution, the UI states:

- a separate diagnostic connection will be used;
- current temporary tables and uncommitted changes are not visible;
- the target database and table;
- whether an open transaction exists on the query session;
- whether a model call is part of query-vector generation.

### 12.6 Comparison summary

After a successful comparison:

```text
Recall@20          90%  (18 of 20 exact neighbors returned)
Top-20 overlap     18
Exact wall time    842 ms
Approx wall time   17 ms
Forced ANN         Confirmed
Index               vec_chunks_embedding, cosine, version 3
Scope               Filter: category = @p0
```

Every metric has an information tooltip with its exact denominator and method.

`Recall@K` uses set overlap against the exact result. If fewer than K exact qualifying rows exist, the denominator is the exact result count and is shown.

### 12.7 Rank comparison table

Columns:

- exact rank;
- approximate rank;
- rank change;
- table key;
- label;
- exact distance;
- approximate distance;
- status: matched, exact-only, approximate-only;
- actions.

Rows can be grouped by status. Ties show a `Distance tie` indicator when values fall within the approved tolerance. Rank movement is not overstated when ties make order unstable.

### 12.8 Rank-flow view

An optional visual view draws lines from exact rank to approximate rank. It is limited to a modest K, uses shape and line style in addition to color, and always has the rank table as an equivalent representation.

### 12.9 Result details inspector

Selecting a result shows:

- key and label;
- source text when the user has permission and requests it;
- exact and approximate ranks/distances;
- whether the row was filtered or absent;
- vector norm and provenance summary;
- `Reveal in Results` when the row exists in the captured result;
- `Fetch bound row` when it exists only in the base table;
- `Add to Compare`.

### 12.10 Execution evidence

A dedicated panel separates requested mode from proven strategy:

| State | Label |
| --- | --- |
| Forced ANN query succeeded | `ANN confirmed by FORCE_ANN_ONLY` |
| Approved plan signature identifies vector index access | `ANN confirmed by execution plan` |
| Approximate syntax requested but plan evidence is unavailable | `Approximate requested, strategy unverified` |
| Warning or plan shows kNN fallback | `Exact fallback` |
| No compatible index | `No compatible vector index` |

Do not use a green check merely because `WITH APPROXIMATE` was present.

### 12.11 Generated SQL drawer

Every variant has a read-only SQL view with:

- copy;
- open in editor;
- line wrapping;
- parameter declarations;
- capability/version comments;
- no hidden predicates.

The SQL drawer is part of the primary experience, not an obscure diagnostics menu.

## 13. Compare workspace

### 13.1 Purpose

Compare answers: **How do selected vectors differ in original space, and what happens when I combine them experimentally?**

### 13.2 Compare basket

- Holds up to the supported selection cap.
- Entries are labeled A, B, C, and so on for the first items, then by row/key.
- Each entry shows source, dimensions, base type, norm, and provenance profile.
- Incompatible dimensions are allowed in the basket but disabled for joint operations with an explanation.

### 13.3 Two-vector comparison

For A and B show:

- cosine distance;
- Euclidean distance;
- negative dot product;
- L1, L2, and infinity norms;
- top component differences by absolute delta;
- component-difference histogram;
- shared nearest neighbors when a table binding exists;
- neighbor rank comparison.

Do not show a “97% similar” badge.

### 13.4 Pairwise matrix

For three or more vectors:

- metric selector;
- heatmap-like matrix plus accessible table;
- selected cell opens the two-vector comparison;
- diagonal is clearly labeled zero or the metric-specific identity;
- matrix limit and partial state are explicit.

### 13.5 Selection summary

Show:

- centroid;
- medoid;
- most isolated vector within the selection;
- closest pair;
- average pair distance;
- compatible/incompatible count.

Each measure has a method tooltip.

### 13.6 Experimental arithmetic lab

Expression builder supports:

- add and subtract vectors;
- scalar multiply;
- weighted mean;
- centroid;
- L1, L2, or infinity normalization.

Output shows:

- exact expression;
- dimensions;
- output norm;
- component preview;
- nearest bound rows under the selected metric;
- `Use as query vector`;
- `Copy JSON array`;
- `Open search comparison`.

Persistent warning:

> Arithmetic is exploratory. Analogy behavior depends on the embedding model, version, preprocessing, and training objective.

## 14. Projection workspace

### 14.1 Purpose

Projection answers: **What broad structure is visible in a bounded sample, and which original rows should I inspect next?**

MVP uses deterministic PCA 2D only.

### 14.2 Projection toolbar

| Control | Default |
| --- | --- |
| Method | `PCA 2D` |
| Preprocessing | `Center only` |
| Metric for original-space neighbors | Binding metric or cosine |
| Color by | None |
| Label by | Binding label or none |
| Sample | Host-resolved bounded sample |
| Fit | Available |
| Selection tool | Pointer, lasso |

Optional preprocessing `L2 normalize, then center` is explicit and never silently inherited from a search metric.

### 14.3 Canvas behavior

- Custom 2D canvas or equivalent renderer, fully local.
- Pan, zoom, fit, click, lasso, and keyboard point navigation.
- Points use stable screen-space size.
- Selected point uses shape and outline, not color alone.
- Labels are off by default except selected and focused points.
- Dense overlap can use alpha and bounded binning later, but MVP must not silently aggregate points.
- Auto-fit occurs once after first complete projection result.
- Recomputing with changed preprocessing resets the camera only after confirmation when a selection exists.

### 14.4 Projection truth banner

Persistent compact banner:

```text
PCA projection of 5,000 sampled rows. PC1 18.4%, PC2 9.7% of sampled variance.
Distances and search ranking are calculated in the original 1,536-dimensional space.
```

### 14.5 Side inspector

For a selected point:

- result-row ordinal or table key;
- label and selected metadata;
- PC1 and PC2 coordinates;
- norm;
- centroid distance;
- original-space nearest neighbors;
- projected nearest points, clearly separated;
- actions: reveal, compare, query vector, isolate selection.

### 14.6 Color and legend

Categorical fields:

- top categories receive distinct theme-aware styles;
- remainder grouped as `Other`;
- null is distinct;
- high-cardinality warning before applying.

Numeric fields:

- sequential legend with min, median, and max;
- clipped outliers disclosed;
- no red/green-only meaning.

### 14.7 Lasso and selection

After lasso:

- show selected count;
- actions: `Inspect list`, `Add to Compare` when within cap, `Profile selection`, `Clear`;
- selection list is virtualized and keyboard accessible;
- no entire vector payload is attached to each rendered point.

### 14.8 Accessible point list

A synchronized list or table is always available with:

- logical position;
- row/key;
- label;
- PC1 and PC2;
- selected state;
- norm or chosen color value.

Selecting in the list highlights the canvas without stealing focus unexpectedly. Canvas selection updates the list and announces the selected point through a live region.

## 15. Index workspace

### 15.1 Purpose

Index answers: **What vector-index configuration exists, is it compatible with the intended search, and what maintenance or migration action deserves review?**

Requires a verified table binding.

### 15.2 Index overview

Cards:

- index name and type;
- vector column and metric;
- index version;
- approximate staleness;
- quantized key-space use;
- last background task status and time.

Permissions or platform gaps appear at the card level.

### 15.3 Compatibility findings

Examples:

- no vector index on the selected column;
- metric mismatch;
- earlier index version;
- latest syntax required;
- forced ANN unsupported;
- primary clustered key prerequisite not met;
- fewer than required non-null rows for index creation;
- background maintenance failure;
- sustained staleness observation, with no universal threshold claim;
- common filter columns lack obvious supporting indexes, labeled as a review suggestion rather than a command.

### 15.4 Health timeline

MVP may show only the current DMV snapshot because the database does not provide history automatically. Do not draw a fake time series from one sample.

A later `Sample health while pane is open` action can collect in-memory points at an explicit interval. It must state that the history is local, temporary, and begins when sampling starts.

### 15.5 Script actions

- `Generate create vector index script`
- `Generate migration script`
- `Generate health query`
- `Generate supporting-index review query`
- `Open exact vs approximate comparison`

All DDL opens in an editor. No DDL executes from the pane.

### 15.6 Staleness wording

Use:

- `Approximate staleness: 7.2%`
- `Background maintenance last succeeded 4 minutes ago`
- `Review recommended because maintenance failed`

Avoid:

- `Index unhealthy` based only on a fixed staleness threshold.
- `Rebuild now` without workload context.

## 16. Pipeline workspace

### 16.1 Purpose

Pipeline answers: **Which source text, model, preprocessing, and chunk policy produced these vectors, and can selected rows be reproduced?**

### 16.2 Provenance profile

Sections:

- vector column;
- source text column or expression description;
- external model object;
- endpoint host or local runtime type;
- expected dimensions and metric;
- expected normalization;
- chunk size and overlap;
- embedding timestamp column;
- model or batch identifier column;
- local notes.

Unknown fields stay unknown. The tool does not infer a model from dimensions alone.

### 16.3 Re-embed selected row

Flow:

1. Select a bound row and inspect the source text.
2. Choose a model and optional parameters.
3. Review model-call confirmation.
4. Generate a fresh embedding.
5. Compare stored and fresh vectors.
6. Compare their exact nearest-neighbor lists.

Result panel shows:

- source length and bounded preview;
- stored versus generated dimensions;
- cosine, Euclidean, and negative-dot distance;
- norm comparison;
- neighbor overlap and rank movement;
- execution messages and elapsed time;
- no automatic write-back.

### 16.4 Chunk debugger

For one source document:

- source ribbon with character offsets;
- chunk blocks with overlap regions;
- chunk order, offset, length, and set ID when available;
- controls for fixed chunk size and overlap within supported ranges;
- tiny-tail and high-overlap warnings;
- optional explicit `Generate embeddings for chunks` action after model-call confirmation;
- per-chunk nearest-neighbor result summary.

Chunk size is labeled as characters for the current SQL function. Do not call it tokens.

### 16.5 Drift sample

Explicit operation over a bounded sample:

- regenerate vectors with selected model;
- compare stored to generated distance distribution;
- group by insertion date, model/batch column, or another selected scalar column;
- flag likely transition boundaries as observations, not proof of a model migration;
- show call count, failures, retries, and sampled scope.

Because this can be expensive and send substantial data, it requires a higher-friction confirmation than a single-row re-embed.

## 17. Selection, context, and Results-grid synchronization

### 17.1 Identity rule

All detached visual items use `resultRowOrdinal`. They must not call that number a displayed row when the Results grid has local sort or filter applied.

Table-bound search results use the configured table key. A result may have both identities when a captured row maps to the bound key.

### 17.2 Reveal in Results

Flow:

1. Switch to Results.
2. Mount the target grid if necessary.
3. Map `resultRowOrdinal` to current display order.
4. If present, scroll, select, and focus the vector cell.
5. If filtered out, preserve the filter and offer `Clear filter and reveal`.
6. If no captured result row exists, keep the user in Vector and offer `Fetch bound row` or `Open generated SELECT`.

### 17.3 Bidirectional selection

- Grid selection can seed Vector selection when the workbench is already open.
- Vector selection updates the query-result context as a distinct vector selection kind.
- It must not overwrite a grid display-row context until the reveal mapping succeeds.
- Selection changes should be throttled for context updates, never for visible highlight.

## 18. Loading, partial, empty, and error states

### 18.1 State taxonomy

| State | Required UX |
| --- | --- |
| Waiting for execution | Initial preview does not expose Vector until a typed eligible result is terminal. Results continues to show execution progress. A future limited mode may expose a non-analyzing waiting state only if it provides useful controls rather than a rerun prompt. |
| Preparing sample | Progress count, cancel action, operation method, and no stale data presented as current. |
| Full result analyzed | Exact full-result badge and row count. |
| Sample analyzed | Sample badge, method, seed, sampled count, and total count. |
| Scan budget reached | Preserve completed output; state what was scanned and what remains unknown. |
| Local compute budget reached | Preserve complete derived items and explain the stopped operation. |
| Terminal partial query | Persistent banner with cancellation, connection loss, row cap, or store corruption reason. |
| No non-null vectors | Empty state with counts and Results action. |
| Text fallback | Initial preview keeps the value in Results and does not expose Vector. A future limited mode must explain typed-analysis limits and offer verified binding or controlled conversion before text fallback becomes eligible. |
| Dimension mismatch | Isolate affected rows; do not crash the entire analysis. |
| Diagnostic connection unavailable | Detached tools remain usable. |
| Permission denied | Show which workspace operation is unavailable and the permission category when known. |
| Preview feature disabled | Show generated verification or enablement SQL, but do not execute configuration changes. |
| Model call partial | Preserve successful rows, list failures, retries, and cancellation status. |
| Renderer unavailable | Keep tables, findings, and point list usable. |

### 18.2 Honest partial wording

Preferred:

> Showing a deterministic sample of 3,842 rows from 2,412,883 because the 8,000,000-component analysis budget was reached.

> 12 malformed vectors were observed in the 25,000 scanned rows. Remaining rows were not scanned.

Avoid:

> 12 malformed vectors in the table.

unless a complete table scan actually occurred.

## 19. Accessibility

### 19.1 Complete nonvisual workflow

A keyboard or screen-reader user must be able to:

1. Activate the Vector tab through the results tab list.
2. Choose result set and vector column.
3. Understand transport, dimensions, sample, and binding status.
4. Run Profile without using a chart.
5. Navigate findings and affected rows.
6. Compose and run a Search comparison.
7. Read recall, rank changes, and execution evidence in tables.
8. Navigate Projection points through the synchronized list.
9. Select a point and reveal it in Results.
10. Review generated SQL.
11. cancel any operation.

### 19.2 Tab and region semantics

- Results tabs use complete `tablist`, `tab`, and `tabpanel` relationships.
- Workspace navigation uses either vertical tabs or a navigation list with a single selected item, not nested tablists with ambiguous arrow behavior.
- Major regions participate in the Query Studio F6 focus sequence: editor, results tab bar, Vector workspace navigation, main content, inspector, status.
- Drawers return focus to the invoking control.

### 19.3 Charts and canvas

- Every chart has a concise text summary and a data table or list.
- Canvas has an accessible name and instructions.
- Canvas is not flooded with one accessibility node per point.
- Point navigation occurs through the virtualized list.
- Hover information is duplicated in persistent details.
- Selection changes use a polite live region.

### 19.4 Visual accessibility

- Use shape, outline, dash, and text in addition to color.
- Support light, dark, high contrast, high contrast light, and forced-colors modes.
- Respect VS Code reduced-motion and screen-reader classes.
- No required animation. Camera transitions are instant in reduced-motion mode.
- Controls and hit targets remain usable at 200% zoom.
- Legends and status text never overlay chart marks at narrow widths.

## 20. Visual language and theming

### 20.1 General style

The workbench should feel like a first-party Query Studio tool, not an embedded analytics website.

- Use Fluent controls and VS Code theme tokens.
- Prefer compact, information-dense layouts with generous chart whitespace.
- Use borders sparingly; hierarchy comes from headings, alignment, and surface elevation.
- Avoid neon gradients, glowing points, or pseudo-scientific 3D depth.
- Display numbers with locale-aware formatting and stable precision appropriate to the metric.

### 20.2 Status colors

- Error: decode failure, model failure, maintenance failure.
- Warning: partial scope, metric mismatch, unsupported strategy, stale binding.
- Information: preview feature, isolated session, sample method.
- Success: completed operation or confirmed evidence, not merely “looks healthy.”

### 20.3 Distance precision

Default display:

- six significant digits in tables;
- more precision in tooltip/copy;
- scientific notation for very small or large values;
- exact raw value available in details.

Ranks and recall use integer counts alongside percentages.

## 21. Privacy, data egress, and model-call confirmation

### 21.1 Data classification

Treat as result data:

- vector components and binary payloads;
- source text and labels;
- table keys;
- distances, norms, centroids, and duplicate hashes;
- projection coordinates;
- search results;
- model outputs;
- table or column bindings when included with user data context.

None belongs in telemetry, diagnostics, replay descriptors, performance marks, or error logs.

### 21.2 Model-call confirmation dialog

Required fields:

```text
Generate embeddings with dbo.TextEmbedding3Small?

Model type             Embeddings
API format             Azure OpenAI
Endpoint host          example.openai.azure.com
Source                  Selected text cell
Rows / calls            1
Text characters         842
Approximate payload     1.7 KiB
Execution               SQL Server calls the configured endpoint
Result handling         Kept in this panel; not written to the table

[Cancel] [View generated T-SQL] [Generate embedding]
```

For a batch or drift operation, emphasize call count, sampled scope, estimated payload, retry behavior, and cancellation limits.

Never display credentials, credential names when policy forbids them, bearer tokens, or full endpoint query strings.

### 21.3 Webview network rule

The Vector webview performs no network requests. External model communication, when explicitly requested, occurs through the database engine and configured external model.

## 22. Keyboard model

Suggested commands, subject to Query Studio command review:

| Shortcut | Action |
| --- | --- |
| `Ctrl+Alt+V` | Open or focus Vector tab when eligible. |
| `Ctrl+Enter` | Run the currently focused explicit operation when safe. Never triggers a model call without confirmation. |
| `Escape` | Cancel lasso, close drawer, or return focus; a running operation requires the visible Cancel action or a confirmed command. |
| `F6` / `Shift+F6` | Cycle Query Studio focus regions. |
| Arrow keys | Navigate workspace rail or focused list. |
| `Enter` | Activate selected workspace, finding, row, or point. |
| `Space` | Toggle selection in list/matrix contexts. |
| `+` / `-` | Zoom Projection canvas while focused. |
| `0` | Fit Projection while focused. |
| `Ctrl+C` | Copy the focused table cell or selected generated SQL according to normal control semantics. |

Do not overload editor shortcuts while focus remains in Monaco.

## 23. Localization and microcopy

### 23.1 Localization rules

- Every visible string enters the existing localization bundle from the first patch.
- Do not compose sentences from fragments that assume English word order.
- Number, date, time, and byte formatting use locale-aware utilities.
- SQL identifiers remain exact and are visually separated from translated prose.

### 23.2 Preferred terms

| Use | Avoid |
| --- | --- |
| Vector Workbench | AI magic, semantic map |
| Negative dot product | Dot similarity, unless the actual value is transformed |
| Approximate requested, strategy unverified | ANN used |
| Sampled rows | Dataset, when not full |
| Result-row ordinal | Row number, after local sort/filter |
| Exact duplicate | Duplicate meaning |
| Possible provenance mismatch | Wrong model, without evidence |
| Generate script | Fix automatically |
| Text may be sent to the configured model endpoint | Safe model call |

## 24. Design-agent mockup package

The design agent should produce annotated light, dark, and high-contrast mockups for at least these screens:

1. Vector tab first open in typed detached mode, Profile loading.
2. Profile complete with findings and sampled-scope disclosure.
3. Profile row inspector showing duplicate and near-zero cases.
4. Table-binding wizard, all four steps and validation states.
5. Search composer with Selected row source.
6. Search composer with Text with model and confirmation dialog.
7. Search comparison complete with summary, rank table, rank-flow view, and generated SQL drawer.
8. Search execution evidence states: confirmed ANN, unverified strategy, exact fallback, no compatible index.
9. Compare two vectors and experimental arithmetic output.
10. Pairwise matrix with incompatible vector entry.
11. Projection wide layout with selection, inspector, legend, and accessible list.
12. Projection narrow layout at 200% zoom.
13. Index workspace with version 3 healthy state, earlier-version migration state, and permission-limited state.
14. Pipeline re-embed result and chunk ribbon.
15. Float16/text-fallback limited mode.
16. Terminal partial query and analysis-budget states.
17. Pinned result mode with database-aware actions locked.
18. Renderer failure with complete tabular fallback.

Each mockup must annotate:

- focus order;
- keyboard behavior;
- aria role/name expectations;
- responsive breakpoints;
- exact copy for empty, partial, warning, and confirmation states;
- what data is full, sampled, scanned-prefix, or newly executed;
- which controls cause SQL execution or model egress;
- which components are virtualized;
- which values are result data and must not enter telemetry.

## 25. UX acceptance criteria

### 25.1 Core flow

- A user can open Vector from a result without changing the query.
- The pane defaults to Profile and explains scope before presenting findings.
- A user can bind a result to a base table without the tool guessing authority.
- A user can generate and inspect exact and approximate SQL variants.
- Recall and rank changes include counts and denominators.
- ANN evidence is labeled according to proof, not requested syntax alone.
- A user can select any projected point through both canvas and list and reveal it in Results.
- DDL is generated but never executed from the pane.
- Model calls require explicit, informative confirmation.

### 25.2 Truthfulness

- No sampled operation is labeled full.
- No scanned-prefix count is presented as a table-wide count.
- No projection distance is presented as SQL vector distance.
- No JSON text column is automatically interpreted as vector data.
- No model or normalization expectation is inferred from dimensions alone.
- No staleness value alone produces an unconditional rebuild recommendation.

### 25.3 Accessibility

- All core tasks are possible without pointer or canvas interaction.
- All charts and scatterplots have equivalent structured output.
- Focus is visible and stable across drawers, reruns, and workspace changes.
- High-contrast and 200% zoom layouts remain usable.
- Live announcements are concise and do not repeat on every streamed chunk.

### 25.4 Privacy

- Opening Vector sends no network request and performs no model call.
- The model confirmation accurately describes source, model, endpoint host, row count, and egress path.
- No UI copy encourages users to expose vectors through public projector URLs.

## 26. Deferred UX milestones

- UMAP and t-SNE with explicit seeds and parameter education.
- PCA 3D and accessible non-3D parity.
- Float16 quantization impact lab.
- Saved retrieval benchmark suites and cross-run regressions.
- Hybrid vector plus full-text comparison, RRF, and reranking.
- Historical vector-index health sampling.
- Near-duplicate clustering beyond exact hashes.
- User-authored advanced search SQL with a safe reproducibility contract.
- Optional database extended properties for provenance profiles.
- Exportable diagnostic reports.
- CI-friendly benchmark definitions.

## 27. External references reviewed

- [Vector data type](https://learn.microsoft.com/en-us/sql/t-sql/data-types/vector-data-type?view=sql-server-ver17)
- [Vector search and vector indexes](https://learn.microsoft.com/en-us/sql/sql-server/ai/vectors?view=sql-server-ver17)
- [VECTOR_DISTANCE](https://learn.microsoft.com/en-us/sql/t-sql/functions/vector-distance-transact-sql?view=sql-server-ver17)
- [VECTOR_SEARCH](https://learn.microsoft.com/en-us/sql/t-sql/functions/vector-search-transact-sql?view=sql-server-ver17)
- [CREATE VECTOR INDEX](https://learn.microsoft.com/en-us/sql/t-sql/statements/create-vector-index-transact-sql?view=sql-server-ver17)
- [sys.vector_indexes](https://learn.microsoft.com/en-us/sql/relational-databases/system-catalog-views/sys-vector-indexes-transact-sql?view=sql-server-ver17)
- [sys.dm_db_vector_indexes](https://learn.microsoft.com/en-us/sql/relational-databases/system-dynamic-management-objects/sys-dm-db-vector-indexes-transact-sql?view=sql-server-ver17)
- [VECTOR_NORM](https://learn.microsoft.com/en-us/sql/t-sql/functions/vector-norm-transact-sql?view=sql-server-ver17)
- [VECTOR_NORMALIZE](https://learn.microsoft.com/en-us/sql/t-sql/functions/vector-normalize-transact-sql?view=sql-server-ver17)
- [AI_GENERATE_EMBEDDINGS](https://learn.microsoft.com/en-us/sql/t-sql/functions/ai-generate-embeddings-transact-sql?view=sql-server-ver17)
- [AI_GENERATE_CHUNKS](https://learn.microsoft.com/en-us/sql/t-sql/functions/ai-generate-chunks-transact-sql?view=sql-server-ver17)
- [CREATE EXTERNAL MODEL](https://learn.microsoft.com/en-us/sql/t-sql/statements/create-external-model-transact-sql?view=sql-server-ver17)
- [TensorFlow Embedding Projector](https://projector.tensorflow.org/)
- [UMAP parameter guide](https://umap-learn.readthedocs.io/en/latest/parameters.html)
- [scikit-learn t-SNE reference](https://scikit-learn.org/stable/modules/generated/sklearn.manifold.TSNE.html)
- [VS Code webview accessibility and security](https://code.visualstudio.com/api/extension-guides/webview)
