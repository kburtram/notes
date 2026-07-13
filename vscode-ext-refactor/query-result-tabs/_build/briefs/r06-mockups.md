# R06 — Mockup brief: Vector B + Spatial HTML prototypes (`.dc.html`) and the DC runtime (`support.js`)

Sources (read completely):

- `C:/repos/test/coding-docs/query-result-tabs/Query Studio - Vector B.dc.html` (989 lines) — **VB** below
- `C:/repos/test/coding-docs/query-result-tabs/support.js` (1717 lines) — **SJ** below
- `C:/repos/test/coding-docs/query-result-tabs/Query Studio - Spatial.dc.html` (795 lines) — **SP** below

These are *working, interactive* prototypes: open the `.dc.html` file over HTTP next to `support.js` and it boots React 18.3.1 from unpkg and renders a fully clickable mock. They define the UX bar for the two new lazy result tabs. Screenshots of the vector states exist alongside (`vec_profile.png`, `vec_search_results.png`, etc.).

---

## 1. What the DC runtime (`support.js`) is — and why you should NOT port it

`support.js` is a generated micro-framework ("dc-runtime", header at SJ:1: `// GENERATED from dc-runtime/src/*.ts — do not edit`). It exists only to make single-file HTML mockups executable. **None of it ships**; you only need to understand it well enough to mechanically translate the templates to React/TSX.

How a `.dc.html` file works:

- The page body contains one `<x-dc>…</x-dc>` template plus a `<script type="text/x-dc" data-dc-script>` defining `class Component extends DCLogic` (parse: SJ:24–55; boot: SJ:150–200). `DCLogic` (`StreamableLogic`, SJ:718–752) is a React-component-shaped class: `this.props`, `this.state`, `setState(update, cb)`, `forceUpdate()`, `componentDidMount/DidUpdate/WillUnmount`, and one extra method **`renderVals()`** which returns a flat object; the template renders against `{...props, ...renderVals()}` (SJ:986).
- Template syntax → React translation table:
  - `{{ expr }}` in text/attrs — a *safe path resolver*, not eval: identifiers, dotted paths, `[index]`, `==/!=/===/!==`, `!`, literals only (SJ:202–294). Becomes plain JSX expressions.
  - `<sc-for list="{{ xs }}" as="x" hint-placeholder-count="N">` → `xs.map(x => …)` (SJ:518–552). `hint-placeholder-*` attrs are streaming-skeleton hints — drop them.
  - `<sc-if value="{{ cond }}" hint-placeholder-val="…">` → `{cond && …}` (SJ:553–567).
  - `style="…"` string values are converted to React style objects via `cssToObj` (SJ:362–371, applied at SJ:704). The logic classes also pass **already-camelCased JS style objects** through template values (e.g. `style="{{ rt.style }}"`) — these are directly reusable as React `style` props.
  - `style-hover="css"` (and `style-focus` etc.) → dynamically inserted pseudo-class rules in a shared stylesheet (`createPseudoSheet`, SJ:1376–1395; class names `scp0`, `scp1`, …). In product code replace with real CSS classes / `:hover` rules.
  - `onClick="{{ fn }}"` etc. → React event props via `EVENT_MAP` (SJ:317–333).
  - `ref="{{ setter }}"` → callback refs (used heavily for canvas/DOM fast paths).
  - `<helmet>` hoists `<link>`/`<style>` into `<head>` (SJ:1263–1374). Both mockups load codicons from `https://cdn.jsdelivr.net/npm/@vscode/codicons@0.0.35/dist/codicon.css` (VB:11, SP:11) — in product, the extension's bundled codicon font replaces this.
- Everything else in SJ is mockup infrastructure you can ignore for the build: streaming placeholders + shimmer CSS (`BASE_CSS`, SJ:86–131), error boundaries and hot-swap of logic classes (SJ:789–1007), `x-import` external-module loader with Babel-standalone for JSX (SJ:1056–1248), sibling-component fetch by name (`ensureFetched`, SJ:1448–1491), atomic CSS utility classes (SJ:1257–1261 — *not used* by either mockup), postMessage editor bridge (SJ:1654–1711), React/ReactDOM 18.3.1 UMD + SRI pins (SJ:1044–1049).
- One relevant behavioral note: `DCLogic.componentDidUpdate(prevProps)` in the mocks is called with *prevProps*, and both mocks implement their own "what changed" memo via `this._last` (VB:589–592, SP:403–412) — when porting to real React components this becomes ordinary `useEffect` dependency lists.

**Porting stance:** the templates translate ~1:1 to JSX; the logic classes translate ~1:1 to a hook/component pair (state object → `useState`/`useReducer`; instance fields like `this.view`, `this.pv` → `useRef`; `renderVals()` body → the component render body). The DC runtime itself: discard.

---

## 2. Shared design system (both mockups)

### 2.1 Fonts and base metrics

- Root font stack (VB:15, SP:15):
  `--vscode-font-family: "Segoe WPC","Segoe UI",system-ui,-apple-system,sans-serif`
  `--vscode-editor-font-family: "Cascadia Code","Consolas","Courier New",monospace`
- Base UI font size **13px** on the root (VB:77, SP:78). Dense secondary text at 12 / 11.5 / 11 / 10.5 / 10px; chart axis text 9–10px. Monospace via class `vb-mono` (VB:72) / inline `fontFamily:var(--vscode-editor-font-family)`.
- Structural row heights (verbatim): results-tab strip 30px (VB:80) / 31px (SP:81); header toolbar 35px (VB:89) / min 38px wrapping (SP:95); facts strip 24px (VB:112); grid/list rows **24px** (vector) and **44px** (spatial feature list); grid header rows 22–24px; status bar **24px** (VB:459, SP:258); rail width 160px (VB:102); inspector drawer 340px (VB:438); projection side list 260px (VB:369); spatial feature panel 322px (SP:225).
- Radii: 2px everywhere in vector; spatial is slightly softer (3px buttons, 5–7px cards/menus, 12px pill for the coordinate readout SP:167).
- Focus: `:focus-visible{outline:1px solid var(--vscode-focusBorder);outline-offset:-1px}` (VB:64); spatial uses 2px (SP:64).
- Scrollbars: webkit 12px (VB:68–70) / 14px (SP:68–70) with `--vscode-scrollbarSlider-background` thumbs, `background-clip:content-box`, 3px transparent border.
- Reduced motion honored globally: `@media (prefers-reduced-motion:reduce){*{animation-duration:.001ms!important;…}}` (VB:74, SP:75) and checked in JS (`matchMedia('(prefers-reduced-motion: reduce)')`, VB:519, SP:315) to skip animations/timers.
- Screen-reader live region: visually-hidden div with `aria-live="polite"` + `announce(msg)` helper (VB:508/597, SP:220/431).

### 2.2 Theme token values (three themes via `[data-theme="dark|light|hc"]` on the pane root)

Both mockups define the same `--vscode-*` palette locally so the mock runs standalone. **In product these must NOT be redefined — the webview inherits real VS Code theme variables**; the tokens below are the design intent and the fallback values used in the mocks.

Dark (VB:16–31, SP:16–31):
`--vscode-foreground:#cccccc; --vscode-editor-background:#1e1e1e; --vscode-editor-foreground:#d4d4d4; --vscode-editorWidget-background:#252526; --vscode-editorWidget-border:#454545; --vscode-panel-background:#1e1e1e; --vscode-panel-border:#2b2b2b; --vscode-focusBorder:#007fd4; --vscode-descriptionForeground:#9d9d9d; --vscode-disabledForeground:#7f7f7f; --vscode-input-background:#3c3c3c; --vscode-input-foreground:#cccccc; --vscode-input-border:#3c3c3c; --vscode-dropdown-background:#3c3c3c; --vscode-dropdown-foreground:#f0f0f0; --vscode-dropdown-border:#454545; --vscode-button-background:#0e639c; --vscode-button-foreground:#ffffff; --vscode-button-hoverBackground:#1177bb; --vscode-button-secondaryBackground:#3a3d41; --vscode-toolbar-hoverBackground:#5a5d5e50; --vscode-list-hoverBackground:#2a2d2e; --vscode-list-activeSelectionBackground:#04395e; --vscode-list-activeSelectionForeground:#ffffff; --vscode-statusBar-background:#2d2d2d; --vscode-statusBar-foreground:#cccccc; --vscode-inputValidation-warningBackground:#352a05; --vscode-inputValidation-warningBorder:#b89500; --vscode-inputValidation-infoBackground:#063b49; --vscode-inputValidation-infoBorder:#1a85b8; --vscode-inputValidation-errorBackground:#5a1d1d; --vscode-inputValidation-errorBorder:#be1100; --vscode-errorForeground:#f48771; --vscode-tab-activeForeground:#ffffff; --vscode-tab-inactiveForeground:#969696; --vscode-editorGroupHeader-tabsBackground:#252526; --vscode-panelTitle-activeBorder:#007fd4; --vscode-scrollbarSlider-background:#79797966; --vscode-widget-shadow:#00000066; --vscode-notifications-background:#252526; --vscode-notifications-border:#454545; --vscode-charts-blue:#4daafc; --vscode-charts-green:#89d185; --vscode-charts-orange:#d18616; --vscode-charts-purple:#c586c0; --vscode-charts-red:#f14c4c; --vscode-charts-yellow:#cca700`

Light (VB:32–47): `foreground:#3b3b3b; editor-background:#ffffff; editorWidget-background:#f8f8f8; panel-border:#e5e5e5; focusBorder:#005fb8; descriptionForeground:#717171; button-background:#005fb8; list-activeSelectionBackground:#0060c0; statusBar-background:#dddddd; charts-blue:#1a73e8; charts-green:#2a8a4a; charts-orange:#bf6a02; charts-purple:#8a3ffc; charts-red:#cd3131; charts-yellow:#946800` (SP light has a typo `--vscode-charts-yellow:#b5900` at SP:46 — treat as `#946800`).

HC (VB:48–63): black backgrounds, `--vscode-contrastBorder:#6fc3df`, `focusBorder/#f38518` accents, transparent hovers.

Mock-only custom tokens (define product equivalents):

- Vector: `--vb-zebra` (zebra row tint: dark `#2a2d2e50`, light `#f4f6fa`, hc `#0a0a0a`) and `--vb-canvas` (chart/sql/canvas background: dark `#181818`, light `#fbfbfb`, hc `#000000`) — VB:31/47/63.
- Spatial: `--map-bg` (dark `#191919`, light `#ffffff`, hc `#000000`), `--map-grid`, `--map-grid-strong`, `--map-label`, `--map-vignette` (dark `#00000055`), `--map-frost` (frosted overlay chip bg: dark `#252526ee`, light `#ffffffee`, hc `#000000f2`) — SP:31/47/63.
- Spatial canvas paints from a JS theme map `colorsByTheme` (SP:307–311), *not* CSS vars — canvas can't read `var()` directly. Values (dark): `bg:'#191919', grid:'rgba(90,110,160,.16)', gridStrong:'rgba(110,132,190,.30)', label:'#8492b5', point:'#4daafc', line:'#e0a33e', polyStroke:'#4ec9b0', polyFill:'rgba(78,201,176,.16)', unsupported:'#a2726f', sel:'#ffffff', selAccent:'#4daafc', halo:'rgba(77,170,252,.30)'`; light: `point:'#1a73e8', line:'#bf6a02', polyStroke:'#2a8a6f', polyFill:'rgba(42,138,111,.14)', sel:'#0b3d91', halo:'rgba(26,115,232,.24)'`; hc: `sel/selAccent:'#f38518', halo:'rgba(243,133,24,.45)'`. The vector projection canvas instead resolves CSS vars at draw time with `getComputedStyle(root).getPropertyValue(name)` (VB:656) — either approach works; resolve-at-draw keeps theme sync automatic.

### 2.3 Reusable control style recipes (verbatim from `renderVals`)

Vector (VB:672–687): `selBtn` (dropdown-style button 26px, `background:var(--vscode-dropdown-background)`, 1px dropdown-border, radius 2, font 12); `selBtnSm` 24px; `iconBtn` 26×26 transparent; `iconBtnSm` 20×22; `hdrBtn` 24px outlined transparent chip, font 11.5; `secondaryBtn` 22px outlined transparent, font 11.5; `stepBtn` 22×22 borderless (for −/+ steppers); `ctlLabel` 11px descriptionForeground; `inputStyle` 24px mono 12px input; `secLabel` **section header pattern**: `font-size:11px; text-transform:uppercase; letter-spacing:.06em; color:descriptionForeground; border-bottom:1px solid panel-border; padding-bottom:3px; margin-bottom:7px` with right-aligned `secMeta` (10px, no transform) for provenance notes like "local · 5,000 sampled"; `runBtn`/`runChev` split primary button (22px, radius `2px 0 0 2px` / `0 2px 2px 0`, divider `1px solid #ffffff44`) (VB:751–752).
Tab styles: 24px text tabs with `border-bottom:2px solid var(--vscode-panelTitle-activeBorder)` when active, `tab-activeForeground/tab-inactiveForeground` (VB:673).
Menu recipe `mBase(rect,width)` (VB:837): `position:fixed` under the anchor rect, clamped to window, `background:dropdown-background`, 1px dropdown-border, radius 2, `box-shadow:0 4px 16px var(--vscode-widget-shadow)`, `padding:4px 0`, zIndex 42. Menu items: icon 16px column + label + optional 10px detail line + trailing `codicon-check` (VB:838, template VB:471–475). Popover recipe (VB:859): 322px, `editorWidget-background/border`, shadow `0 6px 20px`, zIndex 43.
Toast recipe (VB:607, SP:598): centered column at `bottom:34px`, zIndex 60, notification colors, auto-dismiss 2600ms, `aria-live="polite"` container.
Spatial variants (SP:614–622, 757–759): same shapes at radius 3, plus `selBtnWarn` (warning border for the SRID group picker), `btnActive(on)` toggling to button colors for pressed toolbar toggles, `floatBtn` 32×30 for the on-map zoom cluster, `drawerIconBtn` 30×26 secondary.

Z-index layering used: status bar 6, hover card 6, details drawer 7, overlays 8, menus 40–43, model dialog 55, toasts 60.

---

## 3. Vector Workbench mockup (VB) — component inventory & behavior

### 3.1 Top-level DOM (VB:77–509)

```
#vb-root (100vh column; padding-bottom:24px for the absolute status bar)
├─ Results tab strip 30px, role=tablist: mock shows [Results][Vector*][Messages][Query Plan], but product order is [Results][Messages][Vector*][Query Plan] per the 2026-07-12 user override; theme switch buttons are mock-only (VB:80–86)
├─ Header toolbar 35px: pane icon (codicon-symbol-array, charts-purple) ·
│    result-set picker "Chunk search (top 50)" · column picker "embedding  1536·f32" ·
│    spacer · capability badge "Model enabled" (codicon-verified, green) ·
│    binding badge (bound: codicon-key green "dbo.DocumentChunks" / detached: codicon-debug-disconnect) ·
│    scope badge "Sample 5,000" (codicon-list-selection, orange) · overflow "…"        (VB:88–98)
├─ Body row
│  ├─ Workspace rail 160px, role=navigation: Profile(codicon-pulse) Search(codicon-search-fuzzy)
│  │    Compare(codicon-git-compare) Projection(codicon-graph-scatter) Index(codicon-database)
│  │    Pipeline(codicon-sparkle); Search+Index show codicon-lock and are disabled when binding!=='bound'
│  │    (setWorkspace guard + toast, VB:606, 694–696)
│  ├─ Workspace content (ref setContentEl; ResizeObserver → state.narrow = width<640, VB:588)
│  │  ├─ Facts strip 24px: pipe-separated key/value segments, per-workspace content (VB:111–117, 698–708)
│  │  └─ one of six workspaces (below)
│  └─ Findings Inspector drawer 340px (conditional, VB:436–455)
├─ Status bar 24px (absolute bottom): "5,000 sampled of 2,412,883 · 1,536-D float32" ·
│    [Evidence] legend button · "Diagnostic session isolated" · "No network requests" (VB:458–465)
├─ Menus / popovers / model-call dialog / toasts / sr-live (VB:467–508)
```

State model (VB:518–531) — the full pane state an implementation needs: `theme, reduced, workspace, binding('bound'|'detached'), narrow, normType('norm2'|'norm1'|'norminf'), inspector, inspectorScrollTop, searchSource('row'|'text'|'paste'|'expr'), searchK(1..100), searchMetric('cosine'|'euclidean'|'dot'), searchVariants{exact,approx,forced}, runMode('single'|'harness'|'sweep'), searchState('idle'|'running'|'done'), searchElapsed, sqlTab('exact'|'approx'|'forced'|'repro'), sqlOpen, searchText, pasteJson, expr, evidence('confirmed'|'unverified'|'fallback'|'noindex'), indexVer('v3'|'legacy'), rankSort{col,dir}, rankW{c0:62,c1:66,c2:52,c4:92,c5:92,c6:110}, rankSel, menu, menuRect, popKind, cmpExpr, idxScript, modelDialog, reembedDone, chunkSize(200..2000 step 50), chunkOverlap(0..50 step 5), projColorBy('category'|'none'|'norm'), projSel, projListScrollTop, toasts`. Theme persists to localStorage key **`vb.theme`** (VB:516/605).

### 3.2 Profile workspace (VB:119–173, values 710–737)

Two scrollable columns (`grid-template-columns:1fr 1fr; gap:0 18px`; stacks vertically when `narrow`) over a pinned bottom "Group comparison" strip (`maxHeight:190px`).

- **Norms histogram**: L2/L1/L∞ pill tabs; 24 bins as a flexbox of divs — each bar `flex:1; height:(count/max*100)%; minHeight:2px; background:var(--vscode-charts-blue); opacity:.85`, bin 0 turns warning color when near-zero vectors exist (VB:719). Percentile ticks p5/median/p95 are 1×6px absolute divs on the baseline (VB:720–721); L2 shows a dashed green vertical "unit norm" reference line (VB:722–723). Axis min/max labels; 6-stat grid (median/p5/p95/min/max/near-0, near-0 in warning color). Chart height **84px**, `gap:1px`, bottom border as axis.
- **Component variance**: Highest/Lowest 8 rows each — `dim NNNN` label (58px) + 7px track (`background:panel-border`) + proportional fill div (blue for high, descriptionForeground for low) + right-aligned value (VB:140–141, 726–728). Lowest formats `<1e-6` as `~0`, else exponential.
- **Findings list** (6 items, VB:552–559): rows 32px — severity codicon (error `codicon-error` red / warn `codicon-warning`+`codicon-circle-slash`+`codicon-copy`+`codicon-target` yellow / info `codicon-info` gray), title, 10px mono method line ("SHA-256 of float32 bytes + byte verify", "cosine distance from sample centroid · p99", "per-dimension variance < 1e-5"), count, chevron. Click → opens the Inspector drawer.
- **Sampled pair distances**: identical histogram recipe, "cosine · 10,000 pairs · local", axis 0.0–1.0, 3 stats.
- **Group comparison grid**: header `grid-template-columns:1.5fr 0.7fr 0.9fr 1.1fr 0.7fr` — Group (color dot 8×8) / Vectors / Median norm / Median within-dist / Outlier % (warning color when ≥3%) with zebra `--vb-zebra` rows (VB:734–737).

Facts strip in Profile: `Rows 5,000 sampled of 2,412,883 · Dimensions 1,536 · Base type float32 native · Null / unavailable 12 / 0 · Near-zero 8(warning)` (VB:703).

### 3.3 Search workspace (VB:175–319)

Stacked rows: **source tabs** (26px underline tabs: `Selected row / Text with model / Paste vector / Expression`) → **source content row** (per-source: row provenance line with `VECTOR(1536, float32)` + green "provenance match"; text input + "Generate…" sparkle button + warning "model call — confirmation required"; paste input with placeholder `[0.0123, -0.044, …] — flat JSON array of 1,536 finite numbers` + "validated: syntax · dims · finite · float32"; expression input + yellow beaker "Experimental vector arithmetic · A,B,C = Compare basket · parsed locally, never eval()") → **settings row** (Mode dropdown `Single comparison / Self-recall · N=50 / K-sweep`; Metric dropdown cosine/euclidean/dot; K stepper −/+; three variant check-chips Exact/Approx/Forced ANN using `codicon-check`/`codicon-circle-large-outline`; filter chip `category='Technical'`) → **disclosure + run row** (info line: "Isolated diagnostic session · target dbo.DocumentChunks · no open transaction · no model call · cost: ≤3 statements" — cost text per mode VB:748) with split Run button that shows `codicon-loading` spin + elapsed seconds while running (fake durations 900/1600/1200ms, VB:619–621).

Idle state teaches (VB:227–233): big `codicon-search-fuzzy`, headline "What changes between exact and approximate retrieval — and what proves it?", body copy re recall denominators / proven ANN path.

Done state:

- **Evidence block** (VB:239–244, rows VB:756–768): 5 rows of `key (150px) · status codicon · value · mono meta`, driven by demo `evidence` + `indexVer` state — e.g. `Execution path / codicon-pass green / "ANN confirmed via FORCE_ANN_ONLY" / "vec_DocumentChunks_embedding · cosine"`; `Filter semantics` (v3: "Iterative filtering (during traversal)" green; legacy: "Post-filtered after approximate retrieval · TOP_N oversampled ×5 (disclosed)" warning); `Index staleness at run 12.3% (sys.dm_db_vector_indexes · same session, same instant)`; `Syntax probes`; `Recall denominator`. Header has "Open repro script" button → opens SQL drawer on the repro tab.
- **Single mode — rank grid** (VB:246–267, cols VB:770–781, rows VB:782–799): columns `Exact(62) Approx(66) Δ(52) Neighbor(flex) Exact d(92) Approx d(92) Status(110)`, widths in state `rankW`, all sortable (`sortRank`, null-last comparator VB:785) with `codicon-arrow-up/down` sort icons, and resizable via a 5px `cursor:col-resize` handle (`rankResizeDown` VB:623 + global mousemove `_gmove` VB:599 clamping 36–400px). Row cells: Δ colored (positive=warning arrow-down=worse, negative=green arrow-up), status chips `matched(codicon-pass green)/exact-only(codicon-warning yellow)/approx-only(codicon-info blue)`, category color dot, mono `#key`, click selects row (activeSelection colors). 24px rows, zebra.
- **Rank flow diagram** (VB:258–265, geometry VB:800–803): a 150px right sidebar with an inline **SVG** slope graph: 120-wide, `rankFlowH = 6*2 + 19*15 + 8`; a cubic Bézier per matched row `M 0 y1 C 55 y1 55 y2 120 y2` colored gray (Δ=0) / warning (dropped) / green (improved), endpoint circles r=2. Hidden when `narrow`.
- **Harness mode** (VB:269–284): left 300px — Recall@20 histogram (10 bins, 74px tall, same div-bar recipe), stats (median/p5/worst), explanatory copy "Leave-one-out: each sampled row's own vector queries the index; its exact top-20 is the truth set. 2N = 100 bounded statements, sequential, cancellable." Right — "Worst offenders" grid `90px 1fr 90px 70px 80px` (Query row / Label / Recall@20 (warning if <0.85) / Missing / Approx ms).
- **Sweep mode** (VB:286–303): left 330px — per-K dual bars: 8px blue recall bar over 3px orange time bar with `K=10 · 95% · 14 ms` mono labels; note "Blue = recall, orange = approximate wall time." Right — sweep grid `50px 80px 74px 80px 80px 1fr` (K / Recall@K / Overlap / Approx ms / Speedup × / Note).
- **Generated T-SQL drawer** (VB:304–317): 24px collapsed header row `chevron · "GENERATED T-SQL" · green "Executed" play chip · "exactly what executed · parameters shown"`; expanded: tab row Exact/Approximate/Forced ANN/Repro script + copy + open-in-editor icon buttons, then a 170px `<pre class="vb-mono">` (11px/15px) on `--vb-canvas`. SQL text is real product-shaped T-SQL (`_sqlFor`, VB:581–586): exact uses `VECTOR_DISTANCE('cosine', @q, t.[embedding])`; approx v3 uses `SELECT TOP (20) WITH APPROXIMATE … FROM VECTOR_SEARCH(TABLE=…, COLUMN=[embedding], SIMILAR_TO=@q, METRIC='cosine')` with `WHERE` after the TVF alias; legacy v2 uses `TOP_N = 100  -- K × 5 oversample`; forced adds `WITH (FORCE_ANN_ONLY)`; repro concatenates capability check (`SERVERPROPERTY('ProductVersion')`, `OBJECT_ID('sys.dm_db_vector_indexes')`), index-version check via `sys.vector_indexes`/`JSON_VALUE(build_parameters,'$.Version')`, the three variants, and a health query on `sys.dm_db_vector_indexes` (`approximate_staleness_percent`, `last_background_task_succeeded`).

Facts strip per mode (VB:704–707): single `Recall@20 90% (18/20) · Overlap · Exact 842 ms · Approx 17 ms (50×) · Staleness at run 12.3%`; harness `Median recall@20 · p5 · Worst · Queries 50 sampled rows · Statements 100 · sequential`; sweep `K values 10·20·50·100 · Exact baseline 842 ms · Best trade-off K=20 · 90% · 17 ms`.

### 3.4 Compare workspace (VB:323–350, data VB:866–876)

Two scroll columns. Left: **Compare basket** (grid `22px 74px 1fr 90px 76px`: A/B/C, key, dot+label, `1536·f32`, norm); **A ↔ B metrics** property rows (`propRow` = space-between 22px bordered rows; Cosine/Euclidean/Negative dot/L1/L2/L∞ — header note "each metric named — no single "% similar""); **Pairwise distance matrix** 3×3 (grid `22px 1fr 1fr 1fr`, cell heat via `color-mix(in srgb, var(--vscode-charts-blue) N%, transparent)` where N=v*60, VB:874); **Selection summary** (Centroid/Medoid/Most isolated/Closest pair/Avg pair distance/Compatible). Right: **Top |Δ| dimensions** and **Top contributions (aᵢ·bᵢ)** — same 7px bar-row recipe (Δ: blue/orange sign colors; contributions: green/red); **Arithmetic**: expression input `normalize(A + B - C)` + "Use as query vector" (→ jumps to Search with source=expr, VB:965), output rows, nearest-bound-rows mini grid, disclaimer copy.

### 3.5 Projection workspace (VB:352–381, canvas code VB:647–667, list VB:883–886)

- Header 28px: static "PCA 2D · Center only", `Color by` dropdown (Category/None/Norm), Fit button.
- **Truth banner** 22px (warning background + 3px warning left border, VB:362): "PCA 2D · 5,000 sampled rows · PC1 18.4% · PC2 9.7% · next 8.9% not shown · **distances and ranking are computed in the original 1,536-D space, not from these coordinates**" (VB:882).
- **Canvas scatter** (`role="application"` with keyboard/AT label, VB:364): full-bleed `<canvas>` sized by ResizeObserver × devicePixelRatio (`projResize`, VB:652). View transform `{cx,cy,scale}` with `projW2S`/`projS2W` (VB:653–654). Draw (`projDraw`, VB:656–660): clear → fill `--vb-canvas` → axis cross-hairs in panel-border → for each of 1,200 points, cull offscreen ±6px, `arc(r=2.4)`, `globalAlpha:.82`, fill with category color resolved from CSS vars — or, for color-by-norm, computed `hsl(210−t*150,68%,55%)` ramp — → selected point gets a 6px focusBorder ring stroke. Interactions: drag-pan via global mousemove (VB:599), wheel zoom **to cursor** with scale clamp 6–1200 and world-point-under-cursor preservation (VB:663), click-pick = nearest point within 7px (`bd=49` px², VB:664), zoom buttons ±25%/-20% around center (VB:667), Fit = bounding box × 0.86 padding (VB:655). Overlay chips: legend (top-left, panel colors, pointer-events:none) and a vertical zoom cluster (top-right: add / screen-full / remove).
- **Right list** 260px: optional selected-point property card (`Group / ‖v‖ (original) / PC1·PC2 (local) / Centroid distance / Nearest (1,536-D)`), then a **manually virtualized** point list: rowH 24, absolute-positioned rows inside a spacer div `height:count*24`, window = `floor(scrollTop/24)−4 … +viewport/24+8` (VB:883–885). Selection is bidirectional: canvas click scrolls the list to center the row (`projSelect`, VB:665); list click selects on canvas.
- Redraw policy (VB:589–592): on workspace switch → delayed 50ms `projResize()+projFit()`; on projSel/colorBy/theme change → `projDraw()` only. Pan/zoom mutate `this.pv` and call `projDraw()` directly **without setState** — a critical perf pattern to keep.

### 3.6 Index workspace (VB:383–399, data VB:888–920)

Two columns. Left: **Properties** propRow list (Index `vec_DocumentChunks_embedding`; Type · metric `DiskANN · cosine`; Version v3 green / v2 warning; Rows indexed `2,412,883 · 0 pending`; Approximate staleness `7.2%` with a long tooltip about 0–5% steady state / rebuild-on-recall-degradation guidance VB:895; Quantized keys used 41%; Last background task succeeded · 4 min ago; Health history unavailable — current snapshot only; Health DMV present; Edition gate Enterprise) + **Findings** list (v3 set vs legacy set, VB:903–917, e.g. "TRUNCATE TABLE blocked while index exists · drop → truncate → repopulate ≥100 rows → recreate", "Filter column "category" has no supporting index · review suggestion, not a command"). Right: **Scripts** — 5 selectable generators (`create/migrate/health/support/gates`) with header badge "generated — never executed by this pane" (blue `codicon-code`), copy/open-in-editor buttons, `<pre>` viewer. Script text at VB:641–646 includes `CREATE VECTOR INDEX … WITH (METRIC='cosine', TYPE='diskann')`, migration DROP/CREATE with service-impact comment, health DMV snapshot, supporting `CREATE INDEX [ix_DocumentChunks_category]`, and config gates (`ALTER DATABASE SCOPED CONFIGURATION SET PREVIEW_FEATURES = ON`, `sp_configure 'external rest endpoint enabled'`, `'external AI runtimes enabled'`).

### 3.7 Pipeline workspace (VB:401–433, data VB:922–929)

Left: **Provenance** propRows (Vector column embedding / Source text column chunk_text / External model dbo.TextEmbedding3Small / Model type EMBEDDINGS (only supported type) / API format Azure OpenAI · external egress / Endpoint host example.openai.azure.com / Dimensions 1,536 / Expected metric cosine / Expected normalization unit norm / Chunk size-overlap / Embedded-at column). Right: **Re-embed selected row** — quoted source text block on `--vb-canvas`, "Re-embed & compare…" sparkle button → **model-call confirmation dialog**, after confirm shows green "Executed · one confirmed model call" + result rows (Cosine stored↔fresh 0.0041 / Euclidean / Negative dot / Norms / Neighbor overlap 19 of 20 / Rank movement 2 positions). Bottom: **Chunk debugger** — Size (200–2000, step 50) and Overlap % (0–50, step 5) steppers, "Generate embeddings for chunks…" button, and a flexbox chunk visualization: 5 colored chunk boxes (`color-mix(… 14%, transparent)` fills, colored 1px borders) separated by hatched overlap spans `repeating-linear-gradient(45deg, var(--vscode-descriptionForeground) 0 2px, transparent 2px 5px)` whose width tracks overlap% (VB:926–927); caption "Hatched spans are overlap regions shared between adjacent chunks."

**Model-call confirmation dialog** (VB:491–501, rows VB:929): centered 440px card over `#00000077` scrim, zIndex 55 — title "Re-embed selected row?" / "Generate embeddings for 5 chunks?", propRows (Model / Model type / API format / Endpoint host / Source / Rows-calls / Text characters / Approx payload / Execution "SQL Server calls the external endpoint — text leaves your environment" / Result handling "kept in this panel · not written to the table"), warning strip, buttons Cancel / View generated T-SQL / **Generate embedding** (primary).

### 3.8 Findings Inspector drawer (VB:436–455, rows VB:822–833)

340px right drawer: 26px header (severity icon, uppercase "Affected rows · N", close), description block, grid header `74px 1fr 74px 74px` (Key / Label / ‖v‖ / Reason), **manually virtualized** row list (rowH 24, same spacer/window technique, window −3/+6, VB:825–829; reason cell colored per finding severity), footer actions: `Reveal in Results` (codicon-table) / `Add to Compare` (codicon-add) / `Use as query` (codicon-search-fuzzy → switches to Search workspace).

### 3.9 Popovers (VB:857–863) — content worth keeping verbatim

- **Capability** ("Vector capabilities", note "Facts probed from the connection, not marketing labels."): Vector transport `Native float32 binary`; Dimensions · base type; Exact distance Available; Approximate search Available · preview; Vector index name; Index version; Health DMV present; Embedding model `dbo.TextEmbedding3Small · EMBEDDINGS`; API format `Azure OpenAI · external egress` (warning); `external rest endpoint enabled 1 (box/MI gate)`; `external AI runtimes enabled 0 · ONNX unavailable`; `PREVIEW_FEATURES ON (database-scoped)`; Diagnostic session Isolated connection.
- **Scope** ("Analysis scope", note "Deterministic uniform-window sample · seeded · disclosed method. Local computations never see rows outside this sample."): Sample rows 5,000 of 2,412,883; Method uniform windows · seed 770511; Packed input 29.3 MiB of 64 MiB budget; Rows scanned 25,000 cap · scan bytes disclosed; Full-scan option available · higher budget.
- **Evidence legend** (from status bar): Result=blue codicon-table "from the captured query result"; Catalog=purple codicon-database; Executed=green codicon-play "newly executed SQL, shown verbatim"; Local=orange codicon-device-desktop "computed locally on the sample"; Interpretation=yellow codicon-lightbulb "heuristic reading, never a verdict". Tagline: "Every number names its source. Nothing green is unproven."

### 3.10 Mock data generation (replace with real computation in product)

Deterministic seeded RNG `_rng(seed)` — mulberry32 (VB:539) — plus Box-Muller `_normal` (VB:540). Seeds: profile/pca **770511** (VB:542), search **4242** (VB:566), harness **9911** (VB:575), inspector rows `f.id.length*97+f.count` (VB:825), spatial **20260710** (SP:336). Constants: `DIM=1536, TOTAL=2412883, SAMPLE=5000` (VB:543). Categories with chart colors: Technical=blue, Billing=green, Legal=purple, Support=orange, Other=descriptionForeground (VB:544). `_genSearch` (VB:566–574) fabricates exact top-20 + approx list with 2 drops + 2 approx-only extras and computes per-row `status/delta`, overlap, `recall`, `exactMs:842, approxMs:17, forcedMs:19, denom:20, staleness:12.3`. These shapes (`{rows, overlap, recall, exactMs, approxMs, …}`) are a good starting contract for the real reducer.

---

## 4. Spatial Visualizer mockup (SP) — component inventory & behavior

### 4.1 Top-level DOM (SP:78–299)

```
#sp-root (100vh column)
├─ Results tab strip 31px: icon+text tabs [Results codicon-table][Spatial codicon-globe*][Messages codicon-output][Query Plan codicon-graph] + Theme buttons; the Results tab flashes info-background briefly after "Reveal in Results" (revealFlash, SP:610–611)
├─ Toolbar (wrapping, min 38px, editorWidget background): Result set picker · Spatial column picker
│    (icon codicon-globe for geography / codicon-symbol-namespace for geometry) · Label column picker ·
│    conditional SRID-group picker (warning border) · spacer · Projection picker (disabled for
│    Cartesian data) · | · zoom-out / range slider (0..1000, accent-color button-background) /
│    zoom-in / % readout · | · Fit · Layers toggle · Feature-list toggle · … more     (SP:95–134)
├─ Optional info banner (info/warning bg + colored bottom border + optional action button) (SP:137–143)
├─ Body row
│  ├─ MAP (flex:1, role=application, tabindex=0, aria-label describes keys) (SP:148–221)
│  │  ├─ <canvas> full-bleed
│  │  ├─ Legend chip (top-left, --map-frost + backdrop-filter:blur(6px), radius 6): per-gtype swatch
│  │  │    rows + counts + dashed-swatch "Skipped N" row (SP:154–164)
│  │  ├─ Coordinate readout pill (bottom-left, direct-DOM, fades via opacity) (SP:167)
│  │  ├─ Scale bar (bottom-right, direct-DOM width + label) (SP:170–173)
│  │  ├─ Floating zoom cluster (top-right: + / fit / −) (SP:176–180)
│  │  ├─ Hover card (direct-DOM: icon+title+`Type · Row N · SRID S`, repositioned by transform,
│  │  │    flips near right/bottom edges) (SP:183–186, 546)
│  │  ├─ Selected-feature drawer (bottom-right 290px card, sp-pop animation): header icon+title+close;
│  │  │    key/value rows (Row/Type/SRID/Label/Coordinates|Vertices/Status with per-status colors);
│  │  │    footer [Reveal in Results (primary)] [zoom-to] [copy summary] (SP:189–207, 660–678)
│  │  ├─ Full-map overlays: preparing (spinner) / empty / rendererDown (with "Show feature list"
│  │  │    action) / nothing-to-render (SP:210–218, 702–707)
│  │  └─ sr-only live region (SP:220)
│  └─ Feature list panel 322px (toggleable): header "Features · N rows" + hide chevron; filter input
│       ("Filter by label or row…", clearable); manually virtualized listbox (rowH 44) with
│       aria-activedescendant + full keyboard nav; per-row: gtype icon (colored; gray when skipped),
│       label, "Row N", "Type · SRID S", status badge pill (NULL/empty/unsupported/not transported);
│       rows not in the active SRID group render at opacity .5; empty-search message (SP:224–254)
├─ Status bar 24px: "SetName · N features" | N shown | N skipped | N vertices | SRID | geography/geometry | Offline (SP:258–262, 709–720)
├─ Menus popover · Layers popover ("Coordinate graticule / Feature labels / Geodesic densify (geography)" checkboxes + "Basemap: Offline — no network requests") · toasts (SP:264–297)
```

State (SP:314–323): `theme, reduced, activeSetId, spatialCol, labelCol('(None)'), projection('auto'|'equirect'|'mercator'), sridGroup, layers{graticule:true,labels:false,densify:true}, showFeatureList, search, listScrollTop, listViewportH, hover, selected{row,col}, listHoverRow, menu, menuRect, layersOpen, scenario('ready'|'preparing'|'partial'|'budget'|'empty'|'rendererDown'), toasts, revealFlash`. Non-state instance fields: `view{cx,cy,scale}`, `W,H,dpr`, element refs. Theme persists to localStorage **`sp.theme`** (SP:306/591).

### 4.2 Data model (SP:335–390) — the feature contract

Features: `{row, kind:'geography'|'geometry', srid, geom:{t:'Point',c:[x,y]}|{t:'LineString',c:[[x,y]…]}|{t:'Polygon',rings:[[[x,y]…]…]}|null, label, extra:{col:val}, status, reason?, sourceBytes?, gtype?}` with statuses `renderable | null | empty | unsupportedSemantics (reason:'geographyEdge') | unrenderable (reason:'maxCellBytes')`. Result sets: `{id,name,rowCount,complete,truncatedReason?,columns:[{name,type,spatial?,kind?,srid?}],spatialCols,labelCols,features:{colName:[…]}}`. Four demo sets: **r1 Customer Addresses** (geography 4326: ~800 jittered metro points incl. EU cities + 6 NULL + 3 empty + 1 oversized 2,310,442-byte row; second column DeliveryZone = geography polygons all `unsupportedSemantics/geographyEdge`); **r2 Sales Territories** (geometry SRID 0 polygons, one with an interior ring/hole — `fill('evenodd')` matters); **r3 City Network** (mixed geometry SRID 0: 3 park polygons, 6 road linestrings, 22 station points); **r4 Regional Sensors** (**mixed SRIDs** in one column: 22×SRID 0 + 14×SRID 3857; `complete:false, truncatedReason:'rowLimit'`).

Derived selectors (SP:436–458): `activeSet, activeColMeta, rawFeatures, sridGroups()` (group renderables by `kind+':'+srid`), `activeGroup()` (user choice else first), `renderFeatures()` (renderable + in active group — **groups are never overlaid**), `listFeatures()` (all statuses, search-filtered by label or row number), `isGeographic()` (kind==='geography' || srid 4326/3857), `projMode()` → `'cartesian' | 'mercator' | 'equirect'` (auto: 3857→mercator else equirect).

### 4.3 Canvas rendering pipeline (SP:490–527)

`_paint()` order: `setTransform(dpr,0,0,dpr,0,0)` → clear → fill `C.bg` → early-return for overlay scenarios → graticule (if layer on) → **dark-theme-only radial vignette** (`rgba(0,0,0,.35)` at edges, SP:496) → polygons (`fill('evenodd')` with `C.polyFill`, stroke `C.polyStroke`, width 3 when selected) → lines (selected first gets a 7px `C.halo` under-stroke, then `C.line` 2px/3px) → points (radius 3.4, 4.2 in HC; +2.4 selected, +1.4 hovered; `globalAlpha:.92`; 1px contrast ring — white in light, black-alpha in dark; offscreen culled ±20px) → selection decoration (`_drawSelection`: point = double ring 9px sel+selAccent; line/polygon = dashed `[4,3]` selAccent bbox +4px margin) → labels (only when `labelCol!=='(None)'`, layer on, and ≤140 features; 11px, offset +7px, `C.label`).

Graticule `_drawGrid` (SP:512–520): nice-step selection from `stepsGeo=[0.5,1,2,5,10,15,30,45,90]` (degrees) or `stepsCart=[1,2,5,…,1000000]` targeting ≥90px spacing; zero axes use `gridStrong`; edge labels via `_fmtLon` (wraps to ±180°) / `_fmtLat` / `_fmtNum` (k-suffix); when in auto-mercator over 4326 data, y labels are inverse-Mercator'd back to latitude (SP:519).

Projection math: `mercY(lat)=180/π·ln(tan(π/4+lat·π/360))` clamped ±85°, `invMercY` (SP:461–462); `toWorld` passes 3857 through untouched, Mercator-transforms 4326 when mercator mode, identity otherwise (SP:463); `worldToScreen`/`screenToWorld` center-based `{cx,cy,scale}` transform with y-flip (SP:464–465).

View management: `fit(instant)` = bbox × 0.86 pad, single-point clamp (`scale ≤ 24` geo / `2.2` cart), max 4000 (SP:470–476); animated via `_animateTo` — 340ms cubic ease-out, **geometric** scale interpolation `from.scale*Math.pow(target/from, e)`, plus a 380ms `setTimeout` fallback snap because rAF pauses in unfocused iframes (SP:477–482); `reduced` motion skips animation. `_zoomAt(factor,sx,sy)` keeps the world point under the cursor fixed; clamps scale to `baseScale/8 … baseScale*64` (SP:548). Zoom slider maps log-scale: `v = (log(scale/base)/log(64)+0.5)*500` (SP:485). Scale bar picks a nice 1/2/5×10ⁿ value near 70px and prints `°`/`′` for geo, `u`/`k u` for Cartesian (SP:486–488).

Hit-testing `_pick(sx,sy)` (SP:530–537): points first (nearest within 8px, `bestD=64` px²), then line segments (`_distSeg` point-to-segment < 6px), then polygon containment (ray cast `_inPoly` on outer ring). Drag vs click disambiguated by a 3px `moved` threshold (SP:541–543).

### 4.4 Interactions & perf patterns worth copying

- **Direct-DOM fast paths** — mousemove and zoom never call setState for visuals: hover card position (`transform:translate(x,y)` + opacity, SP:546), coordinate readout text (SP:547), zoom % label and slider value (SP:485), scale-bar width — all mutated via refs. Only the *hovered row identity* enters state (to restyle the point), and even that is diffed first (SP:544).
- Global `mousemove/mouseup` listeners with `capture:true` registered once at mount for drag (SP:397–398; VB same at 588) so drags survive leaving the element.
- ResizeObserver on the map element → re-size canvas backing store W×dpr, H×dpr and repaint (SP:399–400/468; VB:649/652).
- `componentDidUpdate` change-detection buckets: `relayout` (set/col/projection/group/scenario → fit+draw), `redraw` (theme/selected/hover/layers → draw only), `relist` (panel toggle → resize) (SP:403–412).
- Keyboard: map — arrows pan 40px-worth, `+/=` `-/_` zoom 1.3×, `f` fit, `Escape` clears selection (SP:551); list — Up/Down/Home/End move selection, Enter zooms to feature (SP:568). Wheel zooms to cursor; double-click zooms 1.8× at point (SP:549–550).
- Selection flows: map click → select + announce + auto-scroll list (`_ensureListVisible` centers row, SP:567); list click → select + (unless reduced-motion) zoom-to (SP:570); skipped features are selectable in the list for inspection but not drawn (SP:569). "Reveal in Results" flashes the Results tab and toasts (SP:557).
- Copy summary format: `Label — Type, kind, SRID n (x, y)` (SP:560).
- Banners (SP:694–700): terminal partial ("Result set is a terminal partial — the query was truncated at the row limit…"), feature budget ("showing N features from the first 25,000 of M scanned rows. Remaining feature count unknown."), multi-SRID ("Multiple coordinate systems in this column (SRID 4326 ×22, SRID 3857 ×14). Showing … — groups are never overlaid without a proven transform." + `Switch group` action), geography-edge ("N geography line/polygon values are valid but not drawn — their edges are geodesic arcs the preview renderer does not yet support. Inspect them in the feature list.").
- Overlays (SP:702–707): `preparing` "Preparing spatial features… / Scanning result rows and decoding geometry within bounded budgets."; `empty`; `rendererDown` "Map renderer unavailable / The canvas renderer could not start. Your features are still available as a list and in the Results grid." + action; implicit nothing-to-render.
- Status bar segments (SP:713–720): `N shown / N skipped / N vertices / SRID x / geography|geometry / Offline` — vertex count computed per frame from rendered features (SP:649).

---

## 5. Chart/plot implementation summary (what draws what)

| Visualization | Tech | Where |
|---|---|---|
| Norm / pair-distance / recall histograms | **DOM flexbox divs** (height %, gap 1px, title tooltips, absolute tick divs) | VB:129–133, 157–160, 273; recipes VB:719–731, 807 |
| Component variance / Δ-dims / contributions / sweep bars | DOM track+fill divs (7px / 8px+3px) | VB:140–141, 338–340, 292–293; VB:727–728, 816 |
| Rank flow slope graph | **Inline SVG** cubic Béziers + circles | VB:262, geometry VB:800–803 |
| Pairwise heat matrix | DOM grid + `color-mix` backgrounds | VB:332, VB:874 |
| Chunk overlap diagram | DOM flexbox + `repeating-linear-gradient` hatch | VB:429, VB:926–927 |
| PCA projection scatter | **Canvas 2D**, ref-driven, DPR-aware, pan/zoom/pick | VB:364–368, VB:647–667 |
| Spatial map (grid, polygons/lines/points, selection, labels, vignette) | **Canvas 2D**, ref-driven, DPR-aware | SP:148–221, SP:490–527 |

No chart library anywhere. Everything is hand-rolled and small — this ports cleanly and keeps the bundle light for lazy loading.

---

## 6. Port judgment: near-verbatim vs re-implement

**Near-verbatim ports (keep the code, translate syntax):**
- Both canvas engines: view transform, fit/zoom-at-cursor/clamps, `_paint`/`projDraw` draw order, graticule nice-step logic, Mercator math, hit-testing (`_pick`, `_distSeg`, `_inPoly`), selection decoration, DPR resize, animated fit with rAF fallback. These are self-contained pure-ish methods over `{cx,cy,scale}` + feature arrays.
- All inline style objects in `renderVals` (they're already React style objects) and the CSS token usage — but move repeated recipes into CSS classes; per-row inline objects for thousands of rows would be GC churn in product.
- Histogram/bar/slope-graph markup and math; the div-based charts are trivially JSX.
- Copy text: evidence rows, popover contents, banner/overlay/status copy, findings text, SQL templates (`_sqlFor`, `_indexSql`) — these encode the product's honesty/evidence language and should be preserved verbatim where the backend supports it.
- Perf patterns: direct-DOM refs for hover/coords/zoom readouts, no-setState canvas pan/zoom, change-bucket effects, capture-phase global drag listeners, offscreen culling, virtualized lists with spacer+window.

**Re-implement / replace in product:**
- The DC runtime entirely (templates → TSX; `DCLogic` → function components/hooks; `style-hover` → CSS).
- Data: all `_seed/_gen*` fabrication → real data from sqltoolsservice; keep the *shapes* (`search.rows[{exactRank,approxRank,delta,status,exactDist,approxDist,…}]`, spatial feature/status contract) as the view-model contracts.
- Manual virtualization → either keep (it's ~15 lines and predictable) or use the product's existing virtualized list; note the mock re-renders the window from state `scrollTop` — throttle or move to rAF in product.
- Menus/popovers/dialog → product's context-menu/dropdown/dialog components (the mock's `position:fixed` + rect math is throwaway); keep item content/detail/check semantics.
- Theme switching — mock's `data-theme` + local token definitions must be dropped; consume live VS Code tokens; spatial's `colorsByTheme` map should be re-derived from computed CSS vars (as the vector projection already does at VB:656) or from the theme-kind only.
- `localStorage` persistence (`vb.theme`, `sp.theme`) → webview state/memento; per-pane persisted state should extend to workspace choice, K/metric/variants, layers, list visibility.
- Codicon CDN link → bundled codicon font.
- Clipboard `navigator.clipboard.writeText` try/catch (VB:616, SP:559) → webview clipboard API path.
- Mock demo affordances to strip: theme buttons in tab strip, "Demo · index version / evidence state" overflow sections (VB:848–856), "Prototype demo states" menu (SP:734–741), toasts saying "(mock)".

---

## 7. Polish/completeness: Vector vs Spatial

- **Spatial is the more finished interaction prototype.** It has: full keyboard support on map + list, direct-DOM fast paths everywhere (60fps hover/pan without React renders), animated fit with reduced-motion + rAF-pause fallbacks, scale bar + coordinate readout + zoom slider sync, complete degraded-state matrix (preparing/partial/budget/empty/rendererDown/multi-SRID/geography-edge), status-badge taxonomy for skipped rows, aria-activedescendant listbox, hover-card edge flipping, and reveal-flash feedback on the Results tab. Its single canvas covers all content.
- **Vector is broader but shallower per-surface.** Six workspaces, richer information design (evidence blocks, facts strips, popovers) and more copy, but: several actions are toast-stubs ("Opened in a new editor (mock)", "Model-call confirmation opens here (next pass)" VB:948, reveal/compare actions VB:962), results are pre-fabricated rather than computed from inputs (K/metric/filter changes don't alter the fake result), no keyboard nav on the rank grid or map-equivalent beyond browser defaults, projection canvas lacks hover cards/coordinate readouts/scale affordances that spatial has, and there's no animated transitions. Its `sc-if`-per-workspace template means every workspace unmounts on switch (state like search results lives on the instance, surviving switches — mirror that in product with kept-alive view-models).
- Both share identical scaffolding conventions (tab strip / toolbar / status bar / menus / toasts / live regions / virtualization / seeded RNG), so a **shared pane shell + shared primitives layer** (section header, propRow, chip buttons, menu, toast, histogram, virtual list, canvas-viewport hook) is directly justified by the mocks.

## 8. Perf notes to carry into the product build (relative to the perf mandate)

- Nothing in either mock requires a chart/map dependency — lazy chunks can stay tiny.
- High-frequency paths (mousemove, wheel, drag, scroll) already avoid React state in spatial; replicate in the vector projection list/rank grid (mock does setState per scroll event — throttle).
- Canvas repaint is full-frame per interaction; at mock scale (≤1.2k points / ≤900 features) that's fine, but product budgets (25k rows scan cap, feature budgets, 64 MiB packed-input budget per the scope popover) are already named in the mock copy — surface the same numbers in the real facts/scope UI and in session-diag timings.
- Both mocks compute derived aggregates (`vertices`, `byType`, group counts) inside render on every pass (SP:639–649) — memoize in product.
- Instrumentation hooks the mocks imply but don't implement: run elapsed timer (VB:619), staleness-at-run capture, "cost: ≤N statements" disclosures, preparing overlay ("bounded budgets") — each maps to a timing/metric log point at component entry per the build's logging requirement.
