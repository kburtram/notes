# Query Studio — Design Addendum (final notes before build)

**Applies to the reviewed v2 set:**
`01-query-studio-ux-brief-claude-design_reviewed.md` · `02-metadata-service-design_reviewed.md` · `03-sts2-client-adapter-design_reviewed.md` · `04-query-studio-master-design_reviewed.md`

**Precedence:** reviewed v2 docs + this addendum supersede the v1 docs entirely. Where this addendum conflicts with a v2 doc, this addendum wins. Where the repo conflicts with any doc, the repo wins for the slice and the deviation is recorded (per doc 04 §23).

---

## 1. Verdict

The reviewed set is ready to hand off, with the adjustments below folded in. The review's four biggest changes are all correct and are hereby ratified as binding:

1. **One `QueryStudioDocumentModel` per URI**, panels attach (doc 04 §4.2). This also quietly fixes a v1 inconsistency: the shadow v1 language-service connection is URI-keyed, so per-panel independent sessions could never have worked cleanly.
2. **SQL Data Plane naming and the backend-binding layer** distinct from transports (doc 03 §0/§2/§7). This matches the actual product goal — the Azure-portal-style host may front semantics with something that isn't STS2 at all — and `HostedRestBackend` + capability honesty is the right shape for that.
3. **Dedicated metadata session, hybrid strategy** (doc 02 §8). Correct call; §3.2 below fixes the ownership gap it left open.
4. **Typed `CellValue` model** (doc 03 §5). Correct for a query tool; §3.3 below adds the ingest-cost guardrails so it doesn't melt on 5M rows.

Also ratified: streaming-honest prototype + lost-connection/transaction/accessibility scripts (doc 01), digest tiers and ServerCatalog (doc 02), the plan-detection heuristic badge, and the RowStore spill privacy rules.

Handoff plan:
- **Claude Design** gets doc 01 alone, plus §7 of this addendum appended to the brief.
- **Coding agents** get docs 02–04 + this addendum. M0 (editor shell/sync) and AD-0/AD-1 (domain API + contract pinning) can start in parallel immediately; §6's contract worksheet is the STS2-side action list.

---

## 2. Canonical names, files, and settings

1. **File references.** The v2 docs cite `*.reviewed.md` (dot); the actual files are `*_reviewed.md` (underscore). Before handing to agents, rename the set to drop the suffix entirely — `01-query-studio-ux-brief.md`, `02-metadata-service-design.md`, `03-sql-data-plane-design.md`, `04-query-studio-master-design.md` — and note that doc 03's filename changes to match its reviewed title (it is no longer "sts2-client-adapter"; STS2 is a binding).
2. **Settings namespace — one flag story.** Doc 03 §17 lists both `mssql.sqlDataPlane.*` and `mssql.sts2.enabled`/`mssql.sts2.transport` "coexisting." Do not ship two flags that can disagree. Binding decision: **`mssql.sqlDataPlane.enabled` and `mssql.sqlDataPlane.backend` are the only user-facing switches.** No `mssql.sts2.*` settings exist. Service-side STS2 activation state is *reported* (availability reason `notEnabledOnService`, and in `MSSQL: Show SQL data-plane status`), never configured from a second client flag. `preemptBackground` lives under `mssql.sqlDataPlane.` as reviewed (the v1 `mssql.queryStudio.preemptBackground` / `mssql.sts2.*` spellings are dead).
3. **Naming freeze:** freeze **Query Studio** now. Identifiers `mssql.queryStudio.*`, `queryStudio` feature bucket, `Qs*` contracts are final for the codebase; any marketing rename later is display-string-only. (Doc 04 asked for this decision before M1 — this is it.)
4. Minor copy fixes when renaming: doc 02 MD-1 "borrrowed" typo; doc 02/04 header cross-references updated to the new filenames.

---

## 3. Cross-doc reconciliations (binding design deltas)

### 3.1 Where `withOverlay` lives

Doc 02 puts `withOverlay?` on `CatalogHandle` (§5.3) and sketches `CatalogSnapshotView extends CatalogSnapshot` (§12). Overlays are per-parse-pass and must pin one generation, so: **`withOverlay` moves to `CatalogSnapshot`.** The handle never carries it. (The binder acquires `current()`, overlays, binds, discards.)

### 3.2 Dedicated metadata session — ownership (the one real gap)

Doc 02 §5.1 still signs `acquireDatabase(session: ISqlSession, …)` while §8.2 says "Query Studio opens a dedicated metadata session." Follow that literally and two documents on the same server/database each open their own dedicated session and hand different sessions to one refcounted catalog — poll ownership becomes ambiguous and dies when the first document closes.

Binding resolution: **MetadataService owns dedicated-session lifecycle; features supply a source, not a session.**

```ts
export type MetadataSessionSource =
  | { kind: "borrowed"; session: ISqlSession }                       // fallback / web hosts
  | { kind: "dedicated";
      connectionService: ISqlConnectionService;                      // injected data-plane service
      profileRef: SqlConnectionProfileRef;                           // incl. token providers
      applicationName: "vscode-mssql-metadata" };

acquireServer(source: MetadataSessionSource, opts?): Promise<ServerCatalogHandle>;
acquireDatabase(source: MetadataSessionSource, key: { database: string }, opts?): Promise<CatalogHandle>;
```

Rules:
- **One dedicated metadata session per `ServerKey`** (not per database, not per document), opened lazily on first dedicated acquire, refcounted by all catalogs under that server, closed on idle TTL with the last catalog.
- That session serves the ServerCatalog and every database catalog on the server by issuing `USE [db]` guards between step groups on its own private, serialized queue. (Catalog views are database-scoped; a private `USE` on a metadata-only session is safe and simpler than three-part-name query rewrites.)
- Session loss → reopen via the stored `profileRef`; one reopen attempt per trigger, then fall back to borrowed sources with the status warning doc 02 §8.2 already defines.
- `notifyExecutedBatch` and database-context signals still come from the *document* session (they always did); the source split changes nothing there.
- The `applicationName` must be distinct (`vscode-mssql-metadata`) so DBAs and the self-test suppression logic can tell it apart.

### 3.3 CellValue lifecycle and the row-payload budget

Doc 03 §5.2's tagged-union `CellValue` is right for correctness; naïvely materializing one object per cell at ingest is wrong for 5M-row results. Binding rules:

1. **Decode boundary.** Bindings may deliver pages in a compact wire-faithful encoding plus column-level type info; full `CellValue` materialization is lazy — at invariant-check time only the fields checks need (counts/offsets), at window-serve/serialize time for real. RowStore never retains decoded `CellValue[][]` beyond the page LRU.
2. **Spill frame format v1:** length-prefixed JSON page frames of the *compact* encoding (values + null bitmap + type table), not serialized `CellValue` unions. Binary columnar is post-v1, decided by measurement.
3. **Exactness rule:** `decimal/numeric/money/bigint` beyond safe-integer range and high-precision datetimes carry string values with `exact:false` never silently set — the binding either preserves the exact token or marks the loss.
4. **Perf gates (added to doc 04 §20.4):** ingest ≥ 100k rows/s on the 10k scenario hardware class; retained heap during streaming ≤ 2× wire bytes for the in-flight window; `QsGetRows` p95 targets unchanged.
5. This confirms doc 04 Appendix A: the `CellWindow` webview payload is the compact shape (values + null bitmap + type hints); tagged unions never cross postMessage.

### 3.4 Error line mapping — exact formula

Doc 04 §12.4's `documentLine = selectionStartLine + batch.startLine + serverLine - 1` double-counts unless coordinate spaces are pinned. Binding definition:

- Splitter emits `batch.startLine` **0-based, relative to the executed text** (selection or document).
- `selectionStartLine` is **1-based document line** of the executed text's first line (1 when executing the whole document).
- `documentLine (1-based) = selectionStartLine + batch.startLine + (serverLine − 1)`.
- Column: only relevant when `batch.startLine == 0` and the selection starts mid-line; then `documentColumn = selectionStartColumn + (serverColumn − 1)` if a column exists, else column 1.
- Test vector: selection starting at document line 10 col 5; batch 2 starts at executed-text line 4; server error `Line 3` → document line 10 + 4 + 2 = 16, column 1.
- Missing/zero server line → navigate to the batch's first line (already specified).

### 3.5 Marker pairing for connect

Doc 04 §17.1 lists `mssql.queryStudio.connect` as "begin/ready/end". The marker contract pairs begin/end by name; pin it: **the official pair is `connect.begin` → `connect.ready`** (mirrors `mssql.connection.begin/ready`). Failure emits `connect.ready` with `error`+`reason` attrs (the standing failure-path rule) — there is no third `end` phase.

### 3.6 `QsRowsAppended` carries counts only

`QsRowsAppended = { resultSetId, newRowCount, complete }` — never row data. Row data crosses only via `QsGetRows`. (Doc 04 §9.2 implies this; make it explicit so no agent "optimizes" by inlining rows.)

### 3.7 Transaction guard runs on the document session

`SELECT @@TRANCOUNT` is meaningful only on the session that owns the transaction. It runs on the **document's data-plane session, interactive lane** — never on the metadata session (which would cheerfully report 0 forever).

### 3.8 SET wrappers are standalone batches

`SET SHOWPLAN_XML ON|OFF`, `SET STATISTICS XML ON|OFF`, and `SET PARSEONLY ON|OFF` must each execute as their own single-statement batch (SHOWPLAN errors when combined with other statements). Notes to encode: `USE` still *executes* under SHOWPLAN (documented engine exception) — database tracking stays live during estimated-plan runs; `PARSEONLY` is syntax-only (no binding/name resolution) — the Parse command's UI copy should say "Syntax checked" not "Validated".

### 3.9 Definition navigation crosses the webview boundary

`QsLspDefinition` results resolving **inside** the current document → `QsRevealPosition`. Results resolving to **another file** → host opens it with `vscode.window.showTextDocument` at the target range (the webview Monaco cannot host foreign documents). Same rule for any future references/peek features.

---

## 4. Keybinding conflicts — decided

The parity map collides with VS Code defaults in ways the docs didn't adjudicate. Decisions:

| Key | SSMS meaning | VS Code default | Decision |
|---|---|---|---|
| F5 | Execute | Start debugging | Package-level binding with `when: activeCustomEditorId == 'mssql.queryStudio'` **and** webview-internal. Shadowing debug-start while our editor is focused is the point of parity; document it. |
| Ctrl+E | Execute | Quick Open (recent files) | **Webview-internal only** (Monaco/grid focus). No package-level binding — shadowing Quick Open whenever the tab is active would enrage VS Code natives. |
| Ctrl+L | Estimated plan | Expand line selection (editor) | **Webview-internal only**, and only when Monaco does *not* have a selection-expansion gesture in flight is too clever — simpler: Ctrl+L = estimated plan inside our webview, with `keybindingProfile` escape below. |
| Ctrl+M | Toggle actual plan | Toggle tab-moves-focus (accessibility) | **Webview-internal only.** Never register package-level Ctrl+M — it must keep working for accessibility users everywhere else. |
| Alt+Break / Alt+B | Cancel | — | As specced. |

Add setting `mssql.queryStudio.keybindingProfile: "ssms" | "vscode"` (default `ssms`): the `vscode` profile drops Ctrl+E/Ctrl+L/Ctrl+M overrides inside the webview (toolbar + F5 remain). Cheap to implement (one keybinding table), and it defuses the inevitable issue thread.

Prototype note (also in §7): in a real browser, F5 reloads the page — doc 01's prototype must `preventDefault` F5 and additionally offer Ctrl+Enter as an execute alias so demos don't get torpedoed by muscle memory.

---

## 5. Two integration realities the docs under-specified

### 5.1 Status-bar interop when a webview is focused

When a custom editor panel is active, `vscode.window.activeTextEditor` is **undefined**. The existing per-URI connection status view logic keys off active-text-editor changes and will hide or misattribute status while Query Studio is focused. M1 scope addition: `DocumentSessionBinding`'s status interop must drive show/hide from tab activation (`window.tabGroups.onDidChangeTabs` / the panel's `onDidChangeViewState`), mapping the active Query Studio tab to its URI. Add a unit/integration test: focus classic editor → focus Query Studio tab → status item reflects the Studio document; focus a non-SQL editor → hides.

### 5.2 PERF_MODE webview mark bridge in the Query Studio page

`querystudio-query-10k`'s official metric ends at `mssql.queryStudio.resultsRendered`, which is **webview-emitted**. The classic scenario only works because the QueryResult page ships the webview mark bridge that forwards marks to the extension-host `Perf` queue. The Query Studio webview must wire the same bridge (reuse the existing utility) from M2, or the scenario's `waitForMarker` end condition never fires and the head-to-head chart Karl wants for M6 doesn't exist. Timing honesty is unchanged: scenario wallclock stays driver-plane monotonic; the webview marker is the semantic end signal.

### 5.3 Monaco packaging gotchas (M0 checklist)

- Use the ESM `monaco-editor` build with the existing webview bundler; ship `editor.worker` as a bundled local resource. Webview CSP must permit `worker-src` for local/blob workers — "CSP strict" (doc 04 §6) needs this carve-out or Monaco tokenization runs on the UI thread and typing latency targets die quietly.
- Set `MonacoEnvironment.getWorker` explicitly; do not rely on path heuristics inside a webview URI scheme.
- Track the chunk size from the first M0 build (doc 04 §10.1's "tracked" made concrete: fail CI over 4 MB gz until consciously raised).

---

## 6. STS2 contract reconciliation worksheet (consolidated, prioritized)

Doc 03 §20 and doc 04 Appendix C list the questions; this pins **when each must close** so AD-1 can file them as issues against the STS2 workstream on day one.

| # | Item | Blocks | Notes |
|---|---|---|---|
| 1 | **Verbatim result-stream messages** (PRINT/RAISERROR/rows-affected/db-context reach the requesting client; journal redaction independent) | M2 exit for any parity claim; preview absolutely | The single highest-risk item. If current behavior sanitizes, raise immediately — it's a service change, not a client workaround. |
| 2 | Ack wire shape (request vs notification; per-page vs high-water; post-cancel behavior) | AD-1 → AD-2 | Ledger supports both; pick one. |
| 3 | Dispose/complete ordering ADR (R008) | Preview (synthesizer protects dev builds) | Adapter default depends on the ADR. |
| 4 | Structured `rowsAffected` on complete | M2 (message-parse fallback exists, tagged `rowsAffectedSource`) | |
| 5 | SPID + server version/encryption in open result | M1 (probe fallback exists) | |
| 6 | Query options honored vs hints (R024) | AD-3 | Capabilities `pageBytesHonored`/`maxCellBytesHonored` report it. |
| 7 | Plan result metadata / structured plan event | M3 (heuristic + badge is the fallback) | |
| 8 | Fatal/unavailable exact semantics for pending + future requests | AD-2 | Conformance transcripts encode the answer. |
| 9 | Capture request vs host policy effective-mode reporting | M6 (replay elevated capture) | |
| 10 | `v2/initialize` method name + capability schema | AD-1 | First thing `wire/v2.ts` pins. |

Process: AD-1's deliverable includes this table filled in with CONTRACT.md citations or filed service-issue links; any row still open at its "blocks" milestone is an explicit gate exception signed off in the slice notes.

---

## 7. Claude Design handoff notes (append to doc 01)

Hand doc 01 to Claude Design as-is, plus these environment constraints:

1. **Monaco: CDN only** (cdnjs) in the prototype environment; implement the styled-textarea fallback path for real, not as an afterthought — CDN loads do fail.
2. **Storage: feature-detect.** `localStorage` may be unavailable or throw in the hosting sandbox. Wrap prototype-preference persistence (split ratio, theme) in a try/catch with an in-memory fallback; never let a storage exception break first render.
3. **F5:** `preventDefault` and bind it, but also bind **Ctrl+Enter** as an execute alias and show it in the tooltip — browser-reload muscle memory will otherwise reload the demo mid-pitch.
4. **High contrast:** implement as a third token set (approximate VS Code HC values: transparent-ish backgrounds, `--vscode-contrastBorder` on every container) toggled alongside dark/light — approximation is fine, unreadability is not.
5. **Single deliverable:** one self-contained page/app; no server, no build-time env assumptions; seed data embedded exactly per doc 01 §8.
6. The mock execution engine's event union (doc 01 §12) is intentionally shaped like the production sink (doc 03 §4.4). Keep the names aligned — this prototype's streaming behavior is the reference implementation for the grid's follow-tail/paused/partial states.

---

## 8. Agent handoff plan

- **Slice order** unchanged from doc 04 §21 (M0…M6) with AD-0/AD-1 parallel to M0 and MD-0/MD-1 parallel to M1/M4 as their gates state. Each slice: minimal diff, tests included, full verification chain, standing perf pair green (`query-10k-results`, `debug-console-smoke`), no commits unless instructed.
- **Docs per phase:** M0 → doc 04 §§6–10 + this addendum §§4–5.3; AD-x → doc 03 + §3.3/§6 here; M2 → doc 04 §§12–13 + §3.3–3.4 here; M4 → doc 02 + §3.1–3.2 here; M5 → doc 04 §15 + doc 02 §10/§16.4; M6 → doc 04 §17 + §5.2/§6 here.
- **Hard rules restated once:** no SQL text/rows/secrets in diag by default; every event through `classify()`; no STS2 wire DTOs outside `src/services/sts2/`; no legacy-STS edits outside the two sanctioned seams (profile-selection factoring, shadow LSP); no unframed stdout; PERF_MODE-only commands don't exist outside perf mode; protocol violations are data-integrity failures.
- **Deviation protocol:** repo wins → record in slice notes → update the doc in the same PR when the deviation is structural.

## 9. Residual decision register (small, non-blocking)

| Decision | Default until revisited |
|---|---|
| Spill frame format binary/columnar | JSON frames v1 per §3.3; revisit with measured bytes/row + decode p95 |
| Excel export | Deferred; CSV covers v1 |
| `keybindingProfile` default | `ssms` per §4; revisit with dogfood feedback |
| Descriptions (MS_Description) in AI schema context | Off in `remoteLm` projections until doc 02 open-question 3 is settled; on for local formats |
| `queryStudio.webCompat` lint list (from v1 doc 04 §15) | Reinstated as a lightweight repo checklist from M1 — cheap insurance for the web-mode future |
| Doc set filenames | Rename per §2.1 at handoff |
