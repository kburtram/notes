# Claude Design Brief — Query Studio
## SSMS-parity composite SQL query document for VS Code, reviewed v2

**Deliverable:** build a single-page interactive React prototype of a composite SQL query editor document. It should represent the content area of a VS Code custom editor tab: embedded Monaco SQL editor, embedded results area, embedded toolbar, embedded per-document status bar, and a minimal mock tab strip for context. Desktop first, minimum 1200px wide. Dark, light, and high-contrast-aware token coverage. All data mocked client-side.

**Audience for this brief:** a design/prototyping agent. Build the prototype. Do not merely describe it.

**Design intent:** recreate the SSMS query-window workflow inside VS Code without importing SSMS chrome. The surface should feel native to VS Code, but preserve SSMS's density, speed, immediate feedback, connection awareness, and result-grid ergonomics.

---

## 0. Review upgrades folded into this v2 brief

The prior brief was already strong. This version tightens the design around the parts that usually turn into implementation dragons:

- Connection state is now treated as a safety surface, not only decoration. Reconnect, connection lost, transaction-warning, and environment/accent states are included.
- Results are explicitly streaming. The prototype should show progressive row arrival, cancellation with partial rows, and a paused/backpressure state so the UX does not accidentally assume atomic result sets.
- Accessibility and keyboard behavior are first-class. Density must not become a fog machine for screen readers, focus order, contrast, or high-contrast themes.
- Grid semantics are more precise: truncation, large values, NULL, typed cells, copy formats, column resizing, selection ranges, and stale/corrupt-result states are called out.
- The status bar is defined as a per-document telemetry and safety strip. It must keep editor cursor, grid selection, connection, elapsed time, row count, and execution result distinct.
- The prototype includes design seams for later real integrations: metadata hydration, inline completions, query replay/capture, and perf/debug markers. These are not implemented as real services in the prototype, but the UI should leave honest places for them.

---

## 1. What this is

Microsoft's `vscode-mssql` extension is getting a new custom document editor, **Query Studio**, that reproduces the SQL Server Management Studio query window experience inside a single VS Code editor tab.

Today, the extension commonly splits work across:

- a normal VS Code text editor;
- a docked Results/Messages panel;
- optional preview webviews;
- connection state in global status bars or external views.

Query Studio unifies the core workflow into one document:

- SQL editor;
- toolbar;
- database/connection selector;
- Results / Messages / Execution Plan tabs;
- virtualized result grids;
- per-document status bar;
- execution state, elapsed timer, row count, grid cell, editor cursor, and connection identity.

The prototype validates the user experience before implementation. It should behave like a professional database tool living comfortably inside VS Code, not a themed screenshot.

---

## 2. Reference behavior to preserve, restyled for VS Code

The reference is the SSMS 21-style query window shown in the supplied screenshot.

Important semantics to preserve:

- **Document tab title:** `SQLQuery1.sql (sa (159))*` format: filename, login + SPID in parentheses, dirty marker. In the prototype, render a minimal mock tab strip above the document only for context.
- **Editor:** SQL text with syntax highlighting, line numbers, right annotation scrollbar, SQL font density.
- **Execution:** F5 / Ctrl+E executes selection if non-empty, otherwise the whole document. The editor remains editable while execution runs.
- **Results region:** absent before first execution. Appears only after a successful, failed, or partial execution creates output.
- **Results tabs:** `Results`, `Messages`, `Execution Plan`. Plan appears only when a plan exists.
- **Results grid:** row-number gutter, sticky headers, SSMS-style dense cells, pale warning-style `NULL` cells, single-cell focus border, range selection, horizontal scroll.
- **Messages:** rows affected, completion time, server errors, PRINT/RAISERROR-like text. Error blocks are clickable and navigate to editor line.
- **Elapsed timer:** ticks live during execution, freezes at terminal state.
- **Cancel:** while executing, Cancel is visually prominent and can terminate the mock execution.
- **Status bar:** document-scoped, connection-colored, with connection, database, elapsed, cursor, grid selection, and row count.
- **Multiple result sets:** each result set is visible and independently scrollable or captioned in one outer scroller.

A useful framing: SSMS gives the *workflow grammar*; VS Code gives the *visual language*.

---

## 3. Hard constraints

1. **VS Code design tokens only.** Use VS Code CSS custom properties (`--vscode-*`) for every UI color. The only literal hex values allowed are mock connection accent colors in seed data, and those must be blended into token-derived surfaces.
2. **Codicons only for icons.** Do not use emoji in the UI. The brief may use emoji as prose shorthand, but the prototype must render Codicons, text, or CSS shapes.
3. **Document content area only.** Render the custom editor surface plus a minimal mock tab strip. Do not build VS Code's activity bar, side bar, global status bar, command palette, or full workbench.
4. **Monaco preferred.** Use Monaco Editor via npm or CDN if feasible. Language `sql`, minimap off, line numbers on. If Monaco fails to load, use a styled text area with a syntax-highlight overlay fallback, but the rest of the interactions must still work.
5. **Everything mocked client-side.** No backend. Mock connect latency 400–900 ms, execute latency 250 ms–2.5 s, streaming pages for large grids.
6. **Theme completeness.** Provide visible dark/light toggle plus high-contrast resilience. Every element must remain readable when core tokens shift.
7. **No dead controls.** Every visible control must either work in the mock or be disabled with an explicit VS Code-style tooltip. Only SQLCMD mode may be disabled as “coming later.”
8. **State reachability.** Every state and interaction script listed below must be reachable without editing source code.
9. **Professional density.** 24 px grid rows, 30 px tab strip, 35 px toolbar, 24 px status bar, 2 px radii max, no card-like bulk, no ornamental shadows.

---

## 4. Layout

Default after first execution:

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ mock VS Code tab strip: SQLQuery1.sql (sa (159)) ●                         │
├────────────────────────────────────────────────────────────────────────────┤
│ TOOLBAR 35px                                                               │
│ plug Connect ▾ | database Sts2TestDb ▾ | play Execute ▾ | stop | Parse | … │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│ EDITOR: Monaco SQL                                         upper pane       │
│                                                                            │
├──────────────────── splitter 4px, draggable, double-click reset ───────────┤
│ RESULTS TAB STRIP 30px: Results | Messages | Execution Plan       Export   │
│ ┌────────────────────────────────────────────────────────────────────────┐ │
│ │ RESULTS REGION: grid / text / messages / plan                          │ │
│ └────────────────────────────────────────────────────────────────────────┘ │
├────────────────────────────────────────────────────────────────────────────┤
│ STATUS BAR 24px, connection-tinted                                         │
│ ✓ Query executed successfully.      lock localhost (17.0 RTM) | sa (159)   │
│                                     Sts2TestDb | 00:00:00 | Ln 2, Col 32   │
│                                     Row 1, Col 1 | 7 rows                  │
└────────────────────────────────────────────────────────────────────────────┘
```

Before first execution:

- toolbar and status bar are visible;
- editor takes all remaining height;
- results tab strip and results region are absent, not empty-collapsed;
- status reads `Ready — not connected` or `Connected.` depending on connection state.

Default split after first output: 55% editor, 45% results. `Ctrl+R` toggles results collapsed/expanded. Splitter double-click resets to 55/45.

---

## 5. Component specifications

### 5.1 Mock tab strip

Render a single VS Code-like tab above the document. It is context, not a real workbench.

States:

| State | Title |
|---|---|
| Never connected, clean | `SQLQuery1.sql` |
| Connected, clean | `SQLQuery1.sql (sa (159))` |
| Connected, dirty | `SQLQuery1.sql (sa (159)) ●` |
| Connection lost | `SQLQuery1.sql (lost) ●` |
| Teal profile | `SQLQuery1.sql (sa (204)) ●` |

Use token backgrounds and borders. Dirty marker can be a small dot, not necessarily an asterisk, because the actual VS Code tab would own dirty UI.

### 5.2 Toolbar

Height 35 px. Background `--vscode-editorWidget-background`; bottom border `--vscode-editorWidget-border`; top 2 px connection-accent line when connected.

Left-to-right groups with thin separators:

| Group | Controls | States and behaviors |
|---|---|---|
| Connection | Connect/Disconnect split button with `codicon-plug`; dropdown: Connect…, Disconnect, Change Connection…, Reconnect | Disconnected: primary Connect. Connected: subdued Disconnect. Lost: warning-styled Reconnect. Connecting: spinner and disabled dependent controls. |
| Database | Database combo: `codicon-database` + name + chevron, width 180 px | Disabled when disconnected/lost/executing. Open as filterable list. Selecting shows 300 ms spinner and appends database-context message. Names must ellipsize. |
| Execute | Execute `codicon-play`, Cancel `codicon-debug-stop`, Parse `codicon-check` | Execute disabled when disconnected/lost; tooltip explains. While executing, Execute becomes spinner/subdued and Cancel becomes prominent. Parse is momentary and writes parse messages. |
| Plan | Estimated Plan, Include Actual Plan toggle | Estimated Plan runs mock plan-only flow. Actual Plan toggle persists across executions; plan tab appears when a run produces a plan. |
| Results routing | Grid/Text toggle pair, Save Results As… menu | Grid default. Text mode re-renders existing results without re-execution. Save menu mocks CSV, JSON, Markdown and shows toast. |
| Diagnostics | Small trace/capture icon button | Opens a tiny mock popover: `Trace: recording digests`, `Replay: not armed`, `Rows streamed: N`. This proves the observability seam without turning the prototype into a debug console. |
| Overflow | `…` menu | Comment Selection, Uncomment, Toggle SQLCMD Mode disabled with tooltip “coming later.” |

Tooltips should appear with keybinding hints after a short delay.

### 5.3 Editor

Monaco configuration:

- language `sql`;
- font `var(--vscode-editor-font-family)`, size `var(--vscode-editor-font-size, 13px)`;
- minimap off by default;
- word wrap off;
- line numbers on;
- render line highlight;
- scrollbar annotations mocked with a thin marker track.

Seed content:

```sql
select *
from sys.databases;
```

Selection behavior:

- If a non-empty selection exists, Execute runs only the selection.
- Show a toast such as `Executing selection (1 statement)` to prove the wiring.
- Cursor movement updates `Ln x, Col y` in the status bar live.
- Errors from Messages click target should move the cursor to the referenced line and briefly flash the line highlight.

Prototype should reserve space for future inline completions, but no completion UI is required. A small optional ghost-text debug script is acceptable only if it does not distract from the query editor UX.

### 5.4 Splitter and results collapse

- Splitter hit area 4 px, cursor `row-resize`.
- Hover color `--vscode-sash-hoverBorder`.
- Drag reflows editor and results live; no ghost bar.
- Double-click resets split.
- `Ctrl+R` collapses/expands the results region.
- When collapsed, status bar still shows last row count and result message.
- When execution completes while collapsed, keep it collapsed but show an unobtrusive status hint `Results updated`.

### 5.5 Results tab strip

Height 30 px. Style like VS Code panel tabs: no uppercase conversion.

Tabs:

- `Results` with grid icon;
- `Messages` with output icon;
- `Execution Plan` with graph icon, present only when the session has a plan result.

Right side:

- result-set count chip when >1, e.g. `3 result sets`;
- export icon mirroring Save Results;
- optional streaming chip while rows are still arriving, e.g. `Streaming 3,120 rows…`.

Error badge:

- Messages tab shows badge count when last execution produced errors.
- Auto-switch to Messages on first error unless user has pinned Results manually during execution. Prototype can implement the simple behavior: switch immediately.

Keyboard:

- Left/Right switch tabs when tab strip has focus.
- F6 cycles focus editor → results tab strip → active results body → toolbar → editor.

### 5.6 Results grid

This is the heart of the prototype.

Requirements:

- Virtualized rows with fixed 24 px height.
- Smooth 10,000-row scrolling using a render window and overscan.
- Sticky header row.
- Row-number gutter, right-aligned, non-selectable.
- Cell font `var(--vscode-editor-font-family)` at 12 px.
- Header font UI 12 px, medium weight.
- Column auto-fit on first render to header/content, max 300 px.
- User-resizable columns by header-edge drag.
- Horizontal scrollbar for wide result sets.
- No data cards, no row zebra sparkle. Dense grid, quiet chrome.

Cell semantics:

| Cell type | Rendering |
|---|---|
| NULL | Literal `NULL`, italic, warning-background tint around 35% opacity, description foreground. Must be visually distinct at scale. |
| Selected | 1 px `--vscode-focusBorder` outline for anchor cell. Range selection uses `--vscode-editor-selectionBackground`. |
| Truncated large value | Suffix glyph or corner marker; tooltip `Value truncated for display. Open Cell to view full mock value.` |
| Error/corrupt set | Do not show corrupt rows as normal truth. Show banner `Result set incomplete or corrupt — see Messages.` |

Selection:

- Click cell selects one cell.
- Drag or Shift+click selects a range.
- Click row number selects row.
- Click header selects column.
- Ctrl+A selects all visible result cells.
- Status updates `Row r, Col c` using the top-left selected cell.

Selection summary:

- For multi-cell numeric selections, show floating bottom-right chip: `Σ 28  Avg 4  Count 7  Nulls 0`.
- Hide for single-cell or nonnumeric-only selections.

Copy and context menu:

- Ctrl+C copies TSV to clipboard.
- Context menu: Copy, Copy with Headers, Select All, Save Results As…, View Cell.
- View Cell opens modal with full text, type label, null/truncated flags, and copy button. Prove it on `owner_sid` and on long `payload` values in the 10k script.

Multiple result sets:

- Render stacked grids in one outer scroll.
- Each grid has a 22 px caption row, e.g. `Result 2 — 3 rows`.
- Each grid may have an inner max-height only if needed; prefer one outer scroll with sticky captions if it feels more native.
- Combined status row count equals total across all completed/truncated result sets.

Streaming:

- For 10k rows, rows should arrive in pages. The row count grows while `complete=false`.
- If the user is scrolled to the bottom, follow tail. If not, preserve scroll position and show a small `Rows added` chip.

### 5.7 Results-as-text mode

Monospace read-only block that uses SSMS-style fixed-width output:

```text
name                  database_id  source_database_id
--------------------  -----------  ------------------
master                1            NULL
...

(7 rows affected)
```

Use the same result data. Switching between Grid and Text must not re-execute.

### 5.8 Messages tab

Monospace, 12 px, selectable text, auto-scroll to bottom on appended messages unless the user scrolled up.

Message kinds:

| Kind | Rendering |
|---|---|
| Info | Default foreground. Examples: `(7 rows affected)`, `Completion time: 2026-07-04T09:54:18.412-07:00`. |
| Warning | Warning foreground or badge; used for cancelled/partial results. |
| Error | Error foreground. Block includes `Msg 208, Level 16, State 1, Line 2` and message text. Entire block hover-underlined and clickable. |
| Batch separator | Dim rule `----- Batch 2 -----` when multiple batches produce messages. |

Clicking an error block moves the editor cursor to that line and flashes the line highlight.

### 5.9 Execution Plan tab

Visual mock only. The goal is composite layout, theming, and interaction, not plan semantics.

Render:

- 6–8 operator nodes;
- right-to-left flow with a `SELECT` root at left;
- connectors with stroke width representing row count;
- nodes show icon, operator name, cost percent;
- hover card with five mock properties;
- pan by drag;
- Ctrl+wheel zoom;
- small toolbar: `+`, `−`, `100%`, `Fit`.

When Include Actual Plan is on, execution should produce Results and Plan. Focus behavior: after execution, focus Results by default unless the plan-only command was used. A small plan badge should indicate plan availability.

### 5.10 Per-document status bar

Height 24 px. Background blends `--vscode-statusBar-background` with the connection accent. Foreground auto-contrasts. Segments are separated by 1 px dividers at roughly 40% opacity.

Segments:

| Segment | Content by state |
|---|---|
| Result message | `Ready — not connected`, `Connected.`, `Executing query…`, `Query executed successfully.`, `Query completed with errors.`, `Query was cancelled by user.`, `Connection lost.` |
| Server | `lock localhost (17.0 RTM)` when encrypted; omit lock when not encrypted. Use Codicon, not emoji. |
| Login | `sa (159)` |
| Database | `Sts2TestDb`, live-updated on database switch or script-internal USE mock. |
| Elapsed | `00:00:00`, ticks while executing, freezes at terminal. |
| Editor cursor | `Ln 2, Col 32` |
| Grid cell | `Row 1, Col 1`, only when grid selection exists. |
| Rows | `7 rows`, combined across result sets. |
| Diagnostics mini | Optional compact chip in prototype: `trace` or `streaming`. Keep unobtrusive. |

State styling:

- Success: success foreground or icon token.
- Errors: only the result-message segment gets error-background tint, not the entire bar.
- Cancelled/partial: warning tint and grid banner.
- Lost connection: warning segment plus Reconnect action in toolbar.

Connection color:

- Seed profile accent `#F3E28A` yellow.
- Teal profile accent in Change Connection script.
- Blend accent with token background: stronger in light theme, subtler in dark.
- Disconnected/lost uses neutral background with state-specific segment tint.

### 5.11 Connection flow

Never-connected state:

- Editor full-height.
- No modal on open.
- Toolbar Connect button has subtle primary treatment.
- Status reads `Ready — not connected`.

Connect:

- Click Connect → mock VS Code quick-pick overlay.
- List 3 saved profiles:
  - `localhost — sa`;
  - `localhost — sa (yellow)`;
  - `perf-lab\sql2025 — integrated (teal)`;
  - plus `+ New connection…` which toasts `Connection dialog not implemented in prototype`.
- Pick → 600 ms spinner → connected state.
- Tab title gains login/SPID.
- Database combo enables.
- Status bar populates.

Lost connection:

- Trigger via overflow debug item or script.
- Active query terminates as connection lost.
- Results already complete remain visible; partial rows get warning banner.
- Status reads `Connection lost.`
- Toolbar shows Reconnect.

Transaction-warning mock:

- On Disconnect after toggling `Mock open transaction` in overflow debug menu, show modal: `This connection has an open transaction. Commit, Rollback, or Cancel disconnect?`
- Buttons may only toast, but the state should be reachable because this is an important SSMS-parity close behavior.

### 5.12 Accessibility and focus

Minimum requirements:

- Keyboard access for toolbar, database list, result tabs, grid cells, context menu, modal, and status bar actions.
- F6 focus cycle as defined above.
- Visible focus ring using `--vscode-focusBorder`.
- ARIA labels for icon buttons.
- Grid announces current cell and selected range in a lightweight way.
- High contrast tokens must remain legible.
- Respect `prefers-reduced-motion`: remove slide animation and pulsing dot when reduced motion is on.
- Toasts should be non-blocking and screen-reader announceable.

Accessibility audit beyond this is out of scope for the prototype, but do not design anything obviously hostile to it.

---

## 6. Interaction scripts to implement

All scripts must work end-to-end.

1. **Connect:** quick-pick flow, populate status, enable database combo, title updates.
2. **Execute happy path:** seed query via F5 or Execute → executing state, elapsed timer, Cancel enabled, streaming briefly, results slide in, 7-row grid, Messages contains rows affected and completion time, status success.
3. **Big grid:** query containing `-- demo: 10k` or debug menu item executes 10,000-row generator. Rows stream in pages. Scrolling remains fluid. Status `10000 rows` at completion.
4. **Multiple result sets:** query with two `SELECT` statements separated by `GO` renders two stacked grids: 7 rows + 3 rows, captions, combined `10 rows`.
5. **Error:** `select * from missing_table;` → auto-switch Messages, error block, clickable line navigation, status warning/error, Messages badge `1`.
6. **Cancel:** run 10k query, press Cancel within first second → partial grid remains with banner `Results incomplete — query cancelled (3,120 of ~10,000 rows)` and status cancelled.
7. **Actual plan:** toggle Include Actual Plan → execute → Execution Plan tab appears and plan view is available. Toggle off removes plan tab on next run.
8. **Estimated plan:** click Estimated Plan → no data rows, plan tab opens, Messages says query was parsed/estimated and not executed.
9. **Database switch:** select `WideWorldImportersDb` → spinner → status db updates; Messages gains `Changed database context to 'WideWorldImportersDb'.`
10. **Results-to-text:** toggle Text mode after a run → fixed-width text output appears without re-executing.
11. **Splitter:** drag; double-click reset; Ctrl+R collapse/restore.
12. **Change connection:** select teal profile → status/accent recolor live, SPID changes, Messages notes connection changed.
13. **Theme toggle:** dark ⇄ light ⇄ high contrast-ish token set with no unreadable elements.
14. **No-row result:** query `update dbo.T set x = 1 where 1 = 0;` mock → no grid, Messages `(0 rows affected)`, status success, Results tab can show `No result sets` empty state.
15. **Large cell:** run 10k generator, open a long payload in View Cell.
16. **Lost connection:** trigger during running query → status lost, cancel disabled, partial data marked incomplete, Reconnect available.
17. **Transaction warning:** toggle mock open transaction then disconnect → commit/rollback/cancel modal appears.
18. **Accessibility path:** using keyboard only, connect, execute, move to grid, copy a selected range, open messages, navigate error.

---

## 7. Visual language

Use only VS Code tokens. Core token families:

- backgrounds: `--vscode-editor-background`, `--vscode-editorWidget-background`, `--vscode-panel-background`;
- borders: `--vscode-editorWidget-border`, `--vscode-panel-border`, `--vscode-contrastBorder`;
- foregrounds: `--vscode-foreground`, `--vscode-descriptionForeground`, `--vscode-disabledForeground`;
- lists/tabs: `--vscode-list-hoverBackground`, `--vscode-list-activeSelectionBackground`, `--vscode-panelTitle-activeForeground`, `--vscode-panelTitle-activeBorder`, `--vscode-panelTitle-inactiveForeground`;
- focus: `--vscode-focusBorder`;
- buttons: `--vscode-button-background`, `--vscode-button-foreground`, `--vscode-toolbar-hoverBackground`;
- inputs/dropdowns: `--vscode-input-background`, `--vscode-input-border`, `--vscode-dropdown-background`, `--vscode-dropdown-foreground`, `--vscode-dropdown-border`;
- status: `--vscode-statusBar-background`, `--vscode-statusBar-foreground`, `--vscode-statusBarItem-warningBackground`, `--vscode-statusBarItem-errorBackground`;
- validation: `--vscode-inputValidation-warningBackground`, `--vscode-inputValidation-errorBackground`, `--vscode-errorForeground`;
- SQL/editor: `--vscode-editor-font-family`, `--vscode-editor-font-size`, `--vscode-editor-selectionBackground`, `--vscode-editorLineNumber-foreground`.

Densities:

| Element | Size |
|---|---:|
| Toolbar | 35 px |
| Results tab strip | 30 px |
| Grid row | 24 px |
| Result-set caption | 22 px |
| Status bar | 24 px |
| Splitter hit area | 4 px |
| Primary UI font | 13 px |
| Small labels | 11–12 px |
| Grid/code font | 12 px |

Motion:

- Results region appears with 150 ms ease only if reduced motion is not requested.
- Executing dot may pulse subtly unless reduced motion.
- No decorative animation.

---

## 8. Seed data

Connected profile:

```text
server: localhost (17.0 RTM)
login: sa
SPID: 159
database: Sts2TestDb
encrypted: true
accent: #F3E28A
```

Teal profile:

```text
server: perf-lab\sql2025 (17.0 RTM)
login: sa
SPID: 204
database: PerfHarness
encrypted: true
accent: #55C8C2
```

Database list:

```text
master
tempdb
model
msdb
WideWorldImportersDb
ShowplanJsonTest
Sts2TestDb
```

`sys.databases` result set columns, in order:

```text
name, database_id, source_database_id, owner_sid, create_date, compatibility_level,
collation_name, user_access, user_access_desc, is_read_only, is_auto_close_on,
is_auto_shrink_on, state, state_desc, is_in_standby, is_cleanly_shutdown
```

Rows:

| name | database_id | source_database_id | owner_sid | create_date | compatibility_level | collation_name | user_access | user_access_desc | is_read_only | is_auto_close_on | is_auto_shrink_on | state | state_desc | is_in_standby | is_cleanly_shutdown |
|---|---:|---|---|---|---:|---|---:|---|---:|---:|---:|---:|---|---:|---:|
| master | 1 | NULL | 0x01 | 2003-04-08 09:13:36.390 | 170 | SQL_Latin1_General_CP1_CI_AS | 0 | MULTI_USER | 0 | 0 | 0 | 0 | ONLINE | 0 | 0 |
| tempdb | 2 | NULL | 0x01 | 2026-07-04 16:52:02.430 | 170 | SQL_Latin1_General_CP1_CI_AS | 0 | MULTI_USER | 0 | 0 | 0 | 0 | ONLINE | 0 | 0 |
| model | 3 | NULL | 0x01 | 2003-04-08 09:13:36.390 | 170 | SQL_Latin1_General_CP1_CI_AS | 0 | MULTI_USER | 0 | 0 | 0 | 0 | ONLINE | 0 | 0 |
| msdb | 4 | NULL | 0x01 | 2026-01-29 18:40:16.640 | 170 | SQL_Latin1_General_CP1_CI_AS | 0 | MULTI_USER | 0 | 0 | 0 | 0 | ONLINE | 0 | 0 |
| WideWorldImportersDb | 5 | NULL | 0x01 | 2026-02-19 02:40:58.337 | 130 | Latin1_General_100_CI_AS | 0 | MULTI_USER | 0 | 0 | 0 | 0 | ONLINE | 0 | 0 |
| ShowplanJsonTest | 6 | NULL | 0x01 | 2026-03-19 00:58:57.543 | 170 | SQL_Latin1_General_CP1_CI_AS | 0 | MULTI_USER | 0 | 0 | 0 | 0 | ONLINE | 0 | 0 |
| Sts2TestDb | 7 | NULL | 0x01 | 2026-06-15 17:16:54.323 | 170 | SQL_Latin1_General_CP1_CI_AS | 0 | MULTI_USER | 0 | 0 | 0 | 0 | ONLINE | 0 | 0 |

Second result set for multi-result script:

| object_id | name | type_desc |
|---:|---|---|
| 1001 | Sales.Orders | USER_TABLE |
| 1002 | Sales.OrderLines | USER_TABLE |
| 1003 | Application.People | USER_TABLE |

10k generator:

- `id`: 1..10000;
- `guid`: deterministic pseudo GUID;
- `created_at`: spread over 90 days;
- `amount`: money-ish, around 8% NULL;
- `status`: OPEN/CLOSED/PENDING;
- `payload`: 40–120 characters lorem-style text, with some long values for View Cell.

NULL values must appear in big data so NULL styling is visible at scale.

---

## 9. Keyboard map

| Keys | Action |
|---|---|
| F5, Ctrl+E | Execute selection if any, otherwise document |
| Alt+Break, Alt+B | Cancel executing query |
| Ctrl+R | Toggle results pane |
| Ctrl+L | Display Estimated Plan |
| Ctrl+M | Toggle Include Actual Plan |
| Ctrl+S | Mock save / dirty marker clear |
| Ctrl+Z / Ctrl+Y | Editor undo/redo if Monaco available |
| Ctrl+K Ctrl+C / Ctrl+K Ctrl+U | Comment / uncomment selection |
| F6 | Cycle focus editor → tabs → grid/messages/plan → toolbar |
| Results tabs Left/Right | Switch result tabs |
| Grid Ctrl+C | Copy selection TSV |
| Grid Ctrl+A | Select all result cells |

Tooltips must include keybindings where relevant.

---

## 10. Acceptance checklist

- [ ] All 18 interaction scripts work.
- [ ] Results region absent before first execution.
- [ ] Execute selection-if-any behavior demonstrable.
- [ ] Live elapsed timer ticks and freezes correctly.
- [ ] Cancel leaves partial rows with truthful incomplete banner.
- [ ] 10k grid scrolls smoothly and is visibly virtualized.
- [ ] Rows stream incrementally instead of popping atomically.
- [ ] NULL styling is distinct and visible.
- [ ] Selection range, summary chip, copy, copy-with-headers, and View Cell work.
- [ ] Multiple result sets render as stacked grids with captions.
- [ ] Messages error block click navigates to editor line.
- [ ] Results-to-text reuses existing data without re-execution.
- [ ] Execution Plan tab pans, zooms, and themes correctly.
- [ ] Connection accent affects toolbar top line and status bar only, not random chrome.
- [ ] Lost connection and reconnect states are reachable.
- [ ] Database switch updates status and messages.
- [ ] Transaction-warning mock is reachable.
- [ ] Dark, light, and high-contrast-ish token sets have no unreadable elements.
- [ ] All visible controls work or are disabled with honest tooltip.
- [ ] No raw emoji icons in UI.
- [ ] Reduced-motion mode removes nonessential animation.

---

## 11. Out of scope for the prototype

- Real SQL connections.
- Real SQL parsing beyond simple script detection.
- Real STS2, MetadataService, or LSP calls.
- Object Explorer.
- Real save-to-disk export.
- Real execution-plan parsing.
- Real AI completions UI.
- Mobile layout.
- Full accessibility audit.
- Pixel-identical SSMS skinning.

---

## 12. Implementation notes for the prototype

Use a single React app with a small state machine:

```text
connection: disconnected | connecting | connected | lost
execution: idle | executing | cancelRequested | succeeded | failed | canceled | connectionLost
results: absent | streaming | complete | partial | corrupt
viewMode: grid | text
activeTab: results | messages | plan
```

Mock execution should be an async generator emitting events resembling the real backend:

```ts
type MockQueryEvent =
  | { type: "accepted"; queryId: string }
  | { type: "resultSetStarted"; resultSetId: string; columns: Column[] }
  | { type: "rowsPage"; resultSetId: string; rowOffset: number; rows: Cell[][] }
  | { type: "message"; kind: "info" | "warning" | "error"; text: string; line?: number }
  | { type: "resultSetEnded"; resultSetId: string; rowCount: number }
  | { type: "plan"; planId: string }
  | { type: "complete"; status: "succeeded" | "failed" | "canceled" | "connectionLost" };
```

This keeps the prototype honest about streaming, cancellation, and partial data. Do not write a mock that returns one giant result array after a timeout and then try to retrofit streaming later. That path is a swamp in nice shoes.

Use browser storage only for prototype preferences such as split ratio and theme. Do not persist mock result data beyond the session.
