# Query Studio Bootstrap Performance Plan (BOOT-1..4)

**Authored:** 2026-07-10 from Karl's P0 directive: the "Open Query Studio Window" scenario
(± initial SQL, autoRun `SELECT 100` → results visible, execution assumed ~0) must be
Amazon-above-the-fold fast within webview constraints, with **zero waste on the path, 100%
phase visibility in the session journal, and tests that FAIL when anyone adds a dependency
to the critical path**. Future spatial/vector result tabs (`coding-docs/query-result-tabs`)
must be **0-cost for queries that don't use them**.

## Measured truth (2026-07-10, dev build, webviews-metafile.json)

Static init-load closure of `dist/views/queryStudio.js`: **16 chunks, 14.3 MB of code,
78 MB on disk** (inline dev sourcemaps — the webview fetches all of it on open).

| KB | Package | Verdict |
|---|---|---|
| 7,239 | monaco-editor (core; languages already lazy ×85 chunks) | legitimate critical path |
| 2,010 | azdataGraph (execution-plan graphs) | **WASTE at init** — static via queryPlanTab |
| 1,172+54+76+56+72 | @slickgrid-universal + slickgrid-react + sortablejs + multiple-select + calendar | **phase-2, not init** |
| 986 | react-dom | shell |
| ~900 | @fluentui/* + griffel + tabster | shell |
| 170 | FluentResultGrid (ours) | phase-2 |

Today's gates: querystudio-open wallclock 110ms (warm) → 1963/4800ms (cold reps).

## Loading phases (the architecture)

- **P0 shell (init render)**: webview HTML → entry chunk → react + fluent shell + Monaco →
  editor interactive. NOTHING ELSE. Target: entry closure = monaco + shell only.
- **P1 known-need prefetch (idle, post-editor-interactive)**: grid stack (FluentResultGrid +
  slickgrid) via dynamic import kicked on `requestIdleCallback` after the editor paints.
  AutoRun results arriving before the chunk resolves render a lightweight placeholder that
  swaps in (rare; local chunk load ≈ ms).
- **P2 on-use only**: query-plan tab (azdataGraph), replay panels, and ALL future heavy tabs
  (spatial map libs, vector viz) load on first activation of their surface. The lazy-tab
  contract for query-result-tabs: a results tab contributes `{ id, label, appliesTo(resultSet),
  loader: () => import(...) }` — `appliesTo` is cheap metadata sniffing (column type names);
  the loader never runs unless the user opens the tab.
- CSS stays in the entry stylesheet (statically imported css-only side-imports) so lazy JS
  chunks don't strand their styles — esbuild moves dynamic-chunk CSS out of the entry css,
  which would otherwise unstyle the grid.

## Batches

### BOOT-1 — instrumentation (core: + qs:)
Registry-first vocabulary `mssql.queryStudio.boot.*` (webviewMark, epochAligned):
`scriptStart` (module eval begins), `reactMount`, `monacoReady`, `editorInteractive`
(first paint with editor mounted — THE above-the-fold moment), `gridChunkRequested/Loaded`,
`planChunkLoaded`, `autoRunStart`. Metrics: `open.toEditorInteractive`
(open.begin → boot.editorInteractive, boundary) and `open.toResultsRendered`
(open.begin → resultsRendered). A `queryStudio.boot.summary` diag event lands the full
phase table in the session journal per open.

### BOOT-2 — staged loading + waste removal (qs:)
1. `queryPlanTab` → React.lazy (azdataGraph leaves init; loads on plan-tab activation).
2. Grid stack (`results`/`resultsGrid`/FluentResultGrid) → React.lazy + idle prefetch after
   editorInteractive; placeholder honesty if results beat the chunk.
3. CSS side-imports hoisted to entry (`FluentResultGrid*.css`, `table.css`, plan css).
4. Dev sourcemaps `inline` → `linked` for webviews AND extension bundles (78 MB → ~14 MB
   fetched; maps load only when devtools opens).
5. `modulepreload` manifest: bundler emits the entry's static-closure chunk list
   (`dist/views/<entry>.preload.json`); the provider injects `<link rel="modulepreload">`
   so the ESM import waterfall becomes one parallel fetch wave.
6. Metafile emitted ALWAYS (prod too) — the budget guard's input.

### BOOT-3 — regression guards (qs: tests)
`queryStudioBundleBudget.test.ts` over webviews-metafile.json (FAILS if missing — the
chain must bundle first):
- Static-closure package DENYLIST: azdataGraph, @slickgrid-universal, slickgrid-react,
  sortablejs, multiple-select-vanilla, vanilla-calendar-pro, and forward-looking heavy names
  (maplibre-gl, leaflet, deck.gl, plotly*, chart.js, echarts, three, cesium, @arcgis, d3).
  Anyone re-adding a static edge to the init path fails the suite by name.
- Code-byte CEILING on the closure (post-split measurement + ~10% headroom).
- The entry closure must not grow new chunks silently (chunk-count ceiling).
Emitted-marker conformance (existing perf-marker test) covers the new boot.* names.

### BOOT-4 — perftest scenario + baselines (perftest)
- Vocabulary for boot marks + derived metrics; regenerate/vendor.
- `querystudio-open-autorun`: provision → newQueryFromContext(initialSql "SELECT 100",
  autoRun) → wait resultsRendered; metrics open.toEditorInteractive +
  open.toResultsRendered + wallclock. Existing querystudio-open gains
  open.toEditorInteractive.
- Before/after harness runs recorded in the journal; knob = none (structure, not tuning).

## Non-goals now (journaled follow-ups)
- Entry CSS split (1.5 MB queryStudio.css) — parse cost is second-order; revisit with data.
- Monaco trimming (feature imports) — highest-risk/large-reward; separate spike.
- Prod-minified size budgets (dev budgets guard the graph; prod tracks automatically).
