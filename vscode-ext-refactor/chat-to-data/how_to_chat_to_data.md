# How to Use Chat-to-Data

A user guide for the Chat-to-Data feature set built on `dev/query` (C2D-0…8, journaled in
`PROGRESS.md`). Chat-to-Data is three related capabilities over Query Studio results:

1. **Result snapshots** — immutable, retained copies of a result set that outlive the query run.
2. **Pinned result tabs** — pop a result pane out of Query Studio into its own read-only document
   that survives reruns, disconnects, and edits.
3. **Chat with your data** — the `@query` chat participant and the `mssql_query_results` Copilot
   tool, which analyze results through a bounded, confirmation-gated access layer (raw values
   never reach the model without your explicit approval).

Everything is additive and behind preview flags — with the flags off, the extension behaves
exactly like `main`.

---

## 1. Prerequisites

| Setting | Default | What it gates |
|---|---|---|
| `mssql.queryStudio.enabled` | — | Query Studio itself (all of Chat-to-Data lives beside it) |
| `mssql.queryResults.pinnedDocuments.enabled` | `true` | Pinned result tabs |
| `mssql.queryResults.ai.enabled` | `true` | AI access to snapshots (`@query`, the Copilot tool) |

Run a query in a Query Studio document first — every feature below starts from a live result set
or a snapshot of one.

---

## 2. Pinning results to a tab

**What it does:** freezes the current results (all complete result sets, messages included) into a
snapshot and opens it as a read-only document beside the editor. The tab keeps working after you
rerun the query, change the SQL, or disconnect — it's your "before" copy for comparisons.

**Three ways to pin:**

- The **pin button** in the Query Studio results pane.
- Command palette: **MS SQL: Query Studio: Pin Results to New Tab** (visible while a Query Studio
  result grid is active).
- In chat: `@query /pin`.

The tab is named like `Pinned Results 14.32.05 a1b2.mssqlresults`. Inside it you get the full
grid (virtualized — 100k+ rows are fine), export/save-as, open-cell-as-document, query plan (when
captured), and the messages pane.

**Lifecycle facts:**

- A pinned tab holds a lease on its snapshot; closing the last tab for a snapshot releases the
  data (memory and spill are reclaimed).
- Opening a **9th** pinned tab shows a one-time memory-pressure warning — each tab retains its
  result data. Close tabs you're done with.
- Unpinned snapshots (e.g. ones an AI chat created) expire on a TTL
  (`mssql.queryResults.snapshot.ttlMinutes`, default 30) or LRU cleanup
  (`maxUnpinnedStores`, default 10; total budget `maxRetainedBytesMb`, default 2048).
- Pinning an AI-created snapshot "graduates" it out of TTL reach — it lives as long as its tab.

---

## 3. `@query` — the chat participant

Type `@query` in the Copilot Chat panel. It targets the **active pinned tab** if one is focused,
otherwise the most recent live Query Studio results.

| Command | What it does | Values shown to the model? |
|---|---|---|
| `/list` | Lists live results and retained snapshots with ids, shapes, and ages | No |
| `/summarize` | Schema, row counts, null ratios per column (computed locally) | No |
| `/profile` | `/summarize` plus min/max per column | **Asks first** (modal) — min/max are data values |
| `/report` | A written Markdown report: local statistics plus, if you approve, a 10-row head/tail sample the model uses for prose | **Asks once** ("Allow") for the sample; declining still produces a stats-only report |
| `/pin` | Pins the target results to a new tab | No |

Examples:

```
@query /summarize
@query /profile           ← modal: "Share min/max values…?"
@query /report            ← modal: "Share a 10-row sample…?"
@query /pin
```

Free-form questions (`@query how many null emails are in these results?`) work too — the
participant computes what it can locally and tells you when something would need a value grant.

---

## 4. `mssql_query_results` — the Copilot agent-mode tool

In agent mode, Copilot can call the **MSSQL Query Result Snapshots** tool to work with your
results the way you would: snapshot, inspect, transform, derive, pin. Useful prompts:

- *"Summarize the results I just ran and tell me which columns look like keys."*
- *"Group these results by Status and count each group."*
- *"Filter this result set to rows where Total > 1000, then pin that view for me."*
- *"Sample 20 random rows and describe data quality problems."*

**Operations** (what you'll see in the tool-call confirmations):
`list_live`, `list_snapshots`, `create_snapshot`, `describe_snapshot`, `get_rows`, `sample_rows`,
`evaluate_transform`, `derive_snapshot`, `pin_snapshot`, `release_snapshot`.

**The transform engine** is the "apply algorithms to result data" pattern: the model submits a
small JSON plan — filter predicates, projections, slices, then a terminal like `aggregate`
(count/sum/avg/stddev/nullCount), `groupBy`, `topK`, `histogram`, `distinctCount`, or `sample` —
and the engine evaluates it in a single streaming pass over the snapshot (no SQL re-execution, no
cache pollution; ~100k rows in well under a second). Results are honest: if a scan hit a row/time
budget, the output is marked `partial` with the reason.

**The derive → pin flow** is the headline trick: `derive_snapshot` materializes a filtered
row-id view over a parent snapshot (with lineage recorded), and `pin_snapshot` opens it as a
regular pinned tab — so "show me only the failing rows in a tab" is one agent request.

**Also note:** the general `mssql_run_query` tool's responses are capped at 100 rows when Query
Studio + AI results are enabled — the tool response includes guidance telling the model to use
snapshots/transforms for anything bigger, instead of dumping rows into context.

---

## 5. The privacy and confirmation model

The design rule: **aggregates are free, values need a grant.**

- Operations whose output class is *aggregate-numeric* (counts, sums, null ratios, histograms of
  numeric buckets) run without confirmation — no cell values leave the extension host.
- Operations whose output contains *values* (`get_rows`, `sample_rows`, group-by keys, min/max,
  topK, samples) require a **single-use grant**: you approve in a confirmation dialog, the grant
  is scoped to that snapshot + conversation + operation class, and it expires in ~2 minutes.
- Per conversation, AI access is bounded: max 5 snapshots, 100 rows / 1 MB per response, 16 KB
  per cell.
- Values that do go to the model ride inside randomly-fenced *treat-as-data* blocks with control
  characters stripped — result cells can't smuggle prompt instructions.
- Everything auditable: see §6.

Declining a grant is always safe — the operation degrades (stats-only report, refused rows) and
nothing is sent.

---

## 6. Diagnostics and troubleshooting

**MS SQL: Query Results: Show Snapshot Status** (command palette) is the lantern. It shows every
retained store (id, kind, rows, bytes, leases, age), the retention budget, spill state, and
`recentGrantActivity` — the last 32 grant mints/denials with operation class and age, so you can
audit exactly when value access was allowed.

Everything also emits to the Debug Console observability timeline under the
`mssql.queryResults.*` event family (snapshot create/dispose, pin open/close/rendered, transform
evaluate, grants, AI tool invocations — names and SQL text never ride events).

Common gotchas:

- **"@query says there are no results"** — run a query in a *Query Studio* document first
  (classic query editor results aren't snapshot sources), or focus the pinned tab you mean.
- **"That snapshot no longer exists"** — an unpinned snapshot hit its TTL. Recreate it, or pin
  next time to keep it.
- **Pinned tab shows "expired"** — the underlying store was disposed (budget pressure after a
  restart). The tab tells you honestly rather than showing stale data.
- **Tool refuses `evaluate_transform`** — the transform's output class was `values` and the
  grant was declined/expired; approve the confirmation or use an aggregate terminal.
- Advanced knobs (transform budgets, AI response caps) live under the
  `mssql.queryResults.overrides` object setting — defaults are journaled in
  `chat_to_data_execution_plan.md` and generally shouldn't need touching.

---

## 7. Where things live (for developers)

- Code: `extensions/mssql/src/queryResults/**` (access service, leases, transform engine, gate,
  tool, `@query` participant) + `src/queryStudio/**` integration points. Commit prefix `c2d:`.
- Specs: `coding-docs/chat-to-data/chat_to_data_execution_plan.md` + `chat_to_data_addendum.md`
  (addendum wins); build journal `PROGRESS.md` (journal wins over both).
- Perf scenarios: `queryresults-pin-after-100k`, `queryresults-pin-survives-rerun`,
  `queryresults-transform-groupby-100k` in the perftest registry.
