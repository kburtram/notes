# Vector Workbench Mockup v2 — Revision Brief for the Design Agent

**Date:** 2026-07-10
**Inputs you should have alongside this brief:** the v1 mockup (`Query_Studio_Vector_Workbench.html`), the normative UX spec (`query_studio_vector_workbench_ux_spec.md`), and optionally the review addendum (`design_addendum.md`) for rationale.
**Precedence:** the UX spec remains normative for behavior, states, copy rules, and accessibility. This brief overrides the spec and v1 only on *visual language and composition*. Where this brief is silent, keep v1's choice.

---

## 1. The diagnosis, in one paragraph

v1 used the right materials (VS Code theme tokens, codicons, a real status bar, three themes, no gradients) but composed them like a BI dashboard: a KPI card row, bordered cards with tinted header bars and pill chips, a centered max-width page that scrolls, question-style subtitles, and a two-line website sidebar. The target is not a dashboard. It is a **results-pane tool** — a sibling of the Results grid, Messages, and Query Plan tabs — used by DBAs and retrieval engineers who live in SSMS and VS Code. Think SSMS results pane, VS Code panel, Query Store, PerfView: data first, chrome last, everything dense, everything keyboard-reachable. If a component would look at home in PowerBI, a marketing site, or a slide, redesign it.

## 2. Keep list — do not regress these

- VS Code theme tokens throughout; dark / light / high-contrast parity; the theme switcher affordance for preview purposes.
- Codicons as the only icon system.
- The 24 px status bar with the scope summary and the `No network requests` assertion.
- The capability popover as a plain facts table, including the line "Facts probed from the connection, not marketing labels."
- The model-call confirmation dialog's field set and honesty (tighten its radii/spacing per §4; content stays).
- The six-workspace set, the header's Result / Vector column selectors, binding and scope badges, and the generated-SQL drawer being part of the primary experience.
- Honest microcopy everywhere: sampled vs full, denominators, evidence labels, "Experimental vector arithmetic," "parsed locally, never eval()".
- No gradients, no glow, no 3-D, no emoji. v1 already honored this; v2 must too.

## 3. House style constants (normative — from the shipping Query Studio code)

The live Query Studio stylesheet states its own contract: **"toolbar 35px, status 24px, 2px radii max, VS Code tokens only, no ornamental chrome."** Apply these numbers everywhere:

| Token | Value |
| --- | --- |
| Base font / control font | 13 px / 12 px, `--vscode-font-family` |
| Numeric + code font | `--vscode-editor-font-family` (Cascadia/Consolas), always for numbers in tables |
| Border radius | **≤ 2 px, everywhere.** No pills, no rounded cards. |
| Results tab strip | 30 px strip, 24 px **text-only** tabs, active = 2 px bottom border `--vscode-focusBorder`. No icons in tabs. |
| Toolbar rows | 35 px (primary) / 28–30 px (secondary), buttons 26 px high, radius 2, transparent bg, hover `--vscode-toolbar-hoverBackground`, primary uses `--vscode-button-background` |
| Status bar | 24 px, segmented items separated by hairlines |
| Splitters | 4 px, `--vscode-editorWidget-border`, hover `--vscode-focusBorder` |
| Data-grid rows | ~24 px, alternating row backgrounds per Fluent result-grid tokens, right-aligned monospace numerics, resizable/sortable headers |
| Section separation | 1 px rules (`--vscode-panel-border`) and 11 px UPPERCASE section labels in `--vscode-descriptionForeground` — the VS Code panel-header pattern. This is the **only** sanctioned uppercase. |
| Shadows | Menus, popovers, and dialogs only. Never on in-pane content. |
| Backgrounds | Pane = `--vscode-panel-background` / editor background. No tinted section headers, no `surface2` card bodies. |

## 4. Global revisions (R1–R12)

**R1 — Delete the KPI card row.** Replace Profile's four summary cards with a single-line **facts strip** directly under the header: `Rows 5,000 sampled of 2,412,883 · Dimensions 1,536 · float32 native · Null/unavailable 214`. Labels in description-foreground, values in monospace foreground, hairline-separated. Warnings get a codicon + warning-foreground word inline, not a chip. Total height ≤ 24 px.

**R2 — Dissolve the cards.** No bordered, radius-6, header-barred containers anywhere. Sections are flat regions on the pane background, introduced by an 11 px uppercase label with a 1 px rule, or separated by splitters where the region is resizable (e.g., main content vs inspector). Hierarchy comes from alignment and typography, not boxes.

**R3 — Ban pill chips.** Every v1 chip becomes either (a) inline codicon + word in a semantic foreground color (`$(warning) Sampled`, `$(pass) Executed`), or (b) a row in a details popover. Zero rounded-rectangle badges in v2. The one exception: the header's binding/scope **badges** may keep a 1 px border at radius 2 because they are interactive buttons — style them like `qs-btn`, not like tags.

**R4 — Fill the pane.** Remove `max-width` entirely. Each workspace is a fixed layout filling the results body; **inner regions scroll, the page does not** (grids, lists, SQL view own their scrollbars — mirror Query Studio's fill-mode rule where one grid's virtualized scrollbar is *the* scrollbar). Exception: Profile may vertically stack-and-scroll only in the narrow (<640 px) layout.

**R5 — Real data grids.** Rank comparison, findings, affected-rows inspector, accessible point list, pairwise matrix companion table, and Index catalog lists are rendered as the existing Fluent result grid (SlickGrid look): 24 px rows, column headers in normal case with sort affordances, resizable columns, row-number gutter where it helps, selection highlighting per grid tokens, right-aligned monospace numerics at 6 significant digits. Column headers are not uppercase-letterspaced labels. Status columns use codicon + word (`$(pass) matched`, `$(arrow-down) −4`).

**R6 — One toolbar idiom for controls.** Workspace-level controls (metric, K, variants, color-by, fit, run) live on 28–30 px toolbar rows of native-styled controls: VS Code dropdown-styled selects, 26 px buttons, compact number steppers, checkbox-styled variant toggles with codicon checks. Not floating labeled control clusters with 18 px gaps; not segmented "settings panels."

**R7 — Chrome states facts; empty states teach.** Delete the interrogative subtitles next to workspace headings ("Do the stored vectors look structurally healthy?", "the target you search against", "exactly what executed"). Workspace heading is the word alone — or drop the heading entirely where the rail already says it and spend the row on the facts strip. The question copy moves verbatim into each workspace's empty state, where it earns its keep.

**R8 — One-line rail.** Workspace rail: 22–24 px items, codicon + label, active = list-active-selection background, gated = lock codicon at right, width ~160 px. Remove the 10 px sub-captions. Remove the "Evidence legend" block from the rail — evidence labels are explained where evidence appears (Search evidence panel) or in a status-bar popover.

**R9 — Scope appears once.** The header scope badge is the single interactive owner (opens details popover). The status bar carries the passive summary. Delete all per-panel "Sampled"/"Local" chips — with R2/R3 they have nowhere to live anyway, and the facts strip already states scope.

**R10 — Charts in the utility register.** Histograms and bar lists keep their current bones but drop containers: hairline baseline, bars in `--vscode-charts-*`, 10 px monospace axis extremes, stats as a small label/value grid beneath (label description-foreground, value monospace). Annotate median/p5/p95 as tick marks on the baseline rather than a separate stat card. No chart titles-with-chips; the section label is the title.

**R11 — Banner discipline.** The Projection truth banner and isolation notices render as single-line info bars styled like status-bar warning/info items (background from `--vscode-inputValidation-*`, 3 px left accent acceptable, radius 0–2, ≤ 24 px tall), not padded callout boxes.

**R12 — Numbers.** Locale-aware thousands separators, 6 significant digits in tables (full precision in tooltips/copy per spec §20.3), monospace, right-aligned in any columnar context. Byte counts in KiB/MiB. Never center-align a number.

## 5. Per-workspace directives

**Profile.** Facts strip (R1). Then a two-column dense layout: left — Norms (histogram + selector as 3 small text-toggle buttons + stats grid) above Component variance (two compact ranked bar lists, dimension ids in 10 px mono); right — Findings as a data grid/list (severity codicon, factual title, count right-aligned mono, method in 10 px mono description text, chevron) above Sampled pair distances. Group comparison becomes a data grid spanning the bottom. Row inspector opens as the right-side drawer, itself a data grid + detail fields.

**Search.** Composer collapses to: source-tab row (24 px text tabs, same pattern as results tabs) + one content row per source + one settings toolbar row (Metric select · K stepper · Variants as three checkbox toggles · Plan toggle · Filters button with count) + a right-aligned primary `Run comparison` with a split chevron for the secondary runs. Pre-run disclosure (isolated session, txn warning) is one info line above the button, not a panel. Results: comparison summary as a facts strip (`Recall@20 90% (18/20) · Overlap 18 · Exact 842 ms · Approx 17 ms`), the evidence panel as a compact label/value block with codicon states — including the filter-semantics line (`Iterative filtering` vs `Post-filtered, TOP_N ×5`) and the staleness stamp when available — then the rank grid (R5) with the rank-flow SVG as an optional narrow companion column, then the SQL drawer (keep v1's drawer behavior; flatten its chrome).

**Compare.** Basket entries as 24 px list rows (mono key, label, dims, norm) with A/B/C prefix letters in badge-free mono. Two-vector metrics as a label/value grid, top-|Δ| dimensions and the new contribution view as compact ranked bar lists. Pairwise matrix: flat heat cells with 1 px gaps, mono values on hover/selection, accessible table adjacent. Arithmetic lab: single mono input row + `$(beaker) Experimental vector arithmetic` as plain warning-colored text, output as a label/value grid.

**Projection.** Toolbar row per R6. Canvas fills; legend overlay becomes a flat 1 px-bordered panel (radius 2, no shadow, square 8 px swatches); zoom cluster likewise. Truth banner per R11, now including the third-component line (`PC1 18.4% · PC2 9.7% · next 8.9% not shown`). Accessible point list is a grid (R5) in the inspector or bottom drawer, synchronized selection.

**Index.** Replace the card grid with a **properties grid** (two-column label/value, hairline rows — VS Code settings register) for index name/type/metric/version/staleness/last-maintenance, findings as the same list pattern as Profile findings, and script actions as a plain command list (`$(file-code) Generate create vector index script`). Health "timeline" area renders the current-snapshot-only state honestly per spec §15.4.

**Pipeline.** Provenance profile as a properties grid. Chunk ribbon: keep the offset ribbon concept; flatten chunk blocks to radius-2, 1 px borders, overlap regions as hatched/tinted spans with a text key. Re-embed result as label/value grid + a small before/after distance table. Confirmation dialog: keep content, radius 2, standard dialog shadow only.

## 6. Component vocabulary

**Allowed:** codicon+text inline statuses · facts strips · 11 px uppercase section labels with hairline rules · properties grids · Fluent result grids · toolbar rows with native-styled controls · status-bar segments · single-line severity info bars · flat legend/zoom overlays (1 px border, radius 2) · monospace numerics · popovers and menus with standard shadow.

**Banned:** KPI/stat cards · pill chips and tag badges · tinted section-header bars · card containers with radius > 2 · shadows on in-pane content · max-width centered columns · icons inside results tabs · two-line nav items · decorative subtitles in chrome · uppercase letter-spaced table headers · display-size numerals (> 15 px) anywhere except dialogs · progress "hero" moments.

## 7. Copy rules for v2

Spec §23 stands. Additionally: chrome is declarative and terse (`Profile`, `Sampled pair distances`, `Executed`); questions and explanations live in empty states and `Why this matters` disclosures; no rhetorical garnish in headers; every number that is sampled says so once, in its authoritative location (R9), not per widget.

## 8. Screens to re-render (minimum set)

1. Profile complete, wide (the reference screen — most rules land here).
2. Profile row inspector open (drawer + grid).
3. Search composer, Selected-row source, pre-run.
4. Search comparison complete: facts strip, evidence incl. filter-semantics + staleness lines, rank grid, SQL drawer open.
5. Search evidence states strip: confirmed / unverified / exact fallback / no index.
6. Projection wide with selection, flat legend, truth banner with third component.
7. Index workspace, properties grid + findings + scripts (healthy v3 and legacy-migration states).
8. Pipeline re-embed result + chunk ribbon.
9. Narrow (<640 px) Profile and Search.
10. All of the above in dark; screens 1, 4, 6 additionally in light and high-contrast.
11. Every screen also captured at **1280×720**.

Carry over v1's annotation duties from spec §24 (focus order, aria, breakpoints, egress markers, virtualization).

## 9. Acceptance checklist for v2

- [ ] Zero border-radius values above 2 px in pane content (dialogs/menus exempt).
- [ ] Zero pill/tag chips; every v1 chip accounted for as inline text or popover row.
- [ ] Zero cards: no bordered container with a tinted header bar exists.
- [ ] No `max-width` on workspace content; pane fills; inner regions scroll, page does not (wide/medium).
- [ ] Results tab strip: text-only 24 px tabs, 2 px active underline, no icons.
- [ ] Rank comparison is a sortable, resizable, selectable data grid with 24 px rows and right-aligned mono numerics.
- [ ] Facts strip replaces the KPI row; largest numeral in any workspace ≤ 15 px.
- [ ] Rail items single-line; no legend in the rail.
- [ ] Scope stated exactly twice: header badge (interactive) + status bar (passive); zero per-panel scope chips.
- [ ] No interrogative or decorative subtitles in chrome; questions present in empty states.
- [ ] Evidence panel includes filter-semantics and (when available) staleness lines.
- [ ] Truth banner is a ≤ 24 px info bar and reports the third component.
- [ ] At 1280×720, screen 4 shows ≥ 12 rank-grid rows and ≥ 2× the visible data rows of v1's equivalent, with no horizontal page scroll.
- [ ] Squint test: at 25% zoom, screens 1 and 4 read as VS Code panels, not dashboards. If any region would look at home in PowerBI, it fails.
- [ ] Dark/light/HC parity maintained; all states from spec §18 still representable in the new vocabulary.
