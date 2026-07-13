# Chat to Data — Design Addendum and Execution Amendments
## Composable result access, transform engine, AI-tool hardening, and QO-branch integration

**Status:** review addendum to `chat_to_data_execution_plan.md` (the reviewed design + coding-agent execution plan), 2026-07-09.
**Precedence:** base plan + this addendum are the spec. **This addendum wins over the base plan on conflicts.** The build journal (§9, Journal) wins over both.
**Repos/branches:** `vscode-mssql` `dev/query` (primary), `sqltoolsservice` `dev/query` (future tiers only), `perftest` `dev/query` (contracts + scenarios).
**Companion docs:** `chat_to_data_execution_plan.md` (base plan), `query_optimization_plan.md` + `query_editor_results_execution.md` (QO design/current-state), `EXECUTION_PLAN.md` + `PROGRESS.md` (QO batches/journal — the QO journal describes changes already on local `dev/query` that the base plan does not know about; §0 below reconciles).

**Upload note:** `chat_to_data.md` and `chat_to_data_execution_plan.md` as provided are byte-identical (same md5). This addendum treats that single document — the reviewed execution plan — as the base. The original draft it reviews was not needed; the base plan restates everything it keeps or replaces.

---

## 0. Verified current-state deltas (BINDING)

The base plan's "current implementation truth" (§2) was accurate for the pre-QO tree. Since then, QO-1..QO-3 landed and QO-9a is in flight (see QO `PROGRESS.md` Entries 1–4). Source inspection 2026-07-09 confirms the following corrections and additions. These are binding on all C2D batches.

**Important for the agent:** the public `microsoft/vscode-mssql` `dev/query` remote does **not** yet contain the QO-1..QO-3 commits (`e70bd4dd4`, `a60b40879`, `df75251a1`); they exist in the local checkout. Build against the **local** tree. Before starting C2D-1, re-run the §12.1 current-state verification greps against the local checkout and record any drift in the journal.

1. **ExecutionHost run start has changed (QO-1/QO-2).** The base plan §8.2 quotes the pre-QO shape (`this.rowStore?.dispose(); this.rowStore = new RowStore(...)`, public tree `executionHost.ts:106–110`). On local HEAD, run start additionally: resolves **one `ResolvedQueryTuningParams` snapshot per run** (precedence `run ?? store ?? tuning.overrides ?? profile ?? dedicated setting ?? default`), derives RowStore limits from it (the hardcoded `DEFAULT_LIMITS` consumption is gone), passes the run's **`diagnosticsLevel` into the RowStore constructor**, calls `beginRunRecord(...)` (replay run records, `replay/qsRunCapture.ts`), and sends wire params (`pageRows`/`pageBytes`/`maxCellBytes`) on every user batch. Consequences:
   - `RetainedRowStore` must wrap the **new** constructor signature and preserve the tuning-derived limits and diagnostics level.
   - Snapshots must **capture `tuningDigest` + `tuningProfile` + run-record id** at creation (§1.6). This is free provenance: perftest can later correlate snapshot read performance with the tuning combo that produced the store.
   - `ExecutionHost.dispose()` currently force-disposes the store (`rowStore?.dispose()`); after C2D-1 it must instead `releaseLiveOwner("documentClosed" | "extensionDeactivate")` — with the deactivation path still guaranteeing a sweep (§5.4).
2. **RowStore has grown QO-2 instrumentation.** Append/spill-write/spill-read/materialize accumulators surfaced via `stats` and stamped as aggregates on `query.complete`; per-page markers at verbose only; `getRows` per-cell null/non-empty scanning is verbose-gated (null bitmap always built). Snapshot read paths must ride the **same** counters (the store doesn't care who is asking) plus the `reason` tag (§1.7) so QO-6's cache policy can distinguish viewport reads from sample/transform scans.
3. **QO-3 landed limits end-to-end.** `pageRows`/`pageBytes`/`maxCellBytes` are honored by STS2 with capability flags; values above pinned service maxima clamp server-side. Irrelevant to snapshot mechanics but relevant to honesty metadata: cells in the store may already be `TruncatedCellEncoding` markers (see 8 below), and `lowMemory`-profile runs produce smaller cells — snapshots inherit whatever the run captured, never more.
4. **File-name corrections (base plan §5/§23).** There is no `src/queryStudio/queryStudioProvider.ts`. The provider is `src/queryStudio/queryStudioEditorProvider.ts` — a `CustomTextEditorProvider` with a **module-level** `liveModels: Map<string, QueryStudioDocumentModel>` (`:32`), plus `pendingOpenContexts` and `explicitClassicOpenUntil`. Live-source registration/deregistration hooks at model create (`liveModels.set`, ~`:104`) and the two delete paths (~`:128`, `:138`). The base plan's rule stands: the access service must **not** scan `liveModels`; the model registers itself.
5. **`QsUpdateGridSelectionRequest` confirmed as described.** Payload `{ row?; column?; rangeRows?; rangeCols? }` (`sharedInterfaces/queryStudio.ts:419`), handler is literally `async () => undefined` (`queryStudioController.ts:736`). The base plan §9.4 replacement payload stands, with one addition: include `snapshotView?: { snapshotId: string }` so pinned documents reuse the same message shape.
6. **The existing `mssql_run_query` LM tool returns unbounded rows.** `src/copilot/tools/runQueryTool.ts` executes via the **legacy** STS lane (`query/simpleexecute`) and returns `JSON.stringify({ success, rowCount, columnInfo, rows: result.rows })` — every row, no cap, no truncation metadata, one pre-execution confirmation. This is the single biggest gap in the base plan: a model holding both `mssql_run_query` (unbounded) and `mssql_query_results` (bounded, gated) will route around the careful tool. §4.1 makes reconciliation a required task. Also note: `simpleexecute` results never touch the Query Studio RowStore — AI-run queries are invisible to the snapshot layer in v1 (future tier hook in §4.6).
7. **AI surface inventory (verified).** 13 LM tools registered in `MainController.registerLanguageModelTools()` (`mainController.ts:940+`) via a shared `ToolBase` (`call` + `prepareInvocation` returning `{ invocationMessage, confirmationMessages }`). One chat participant `mssql.agent` (sticky, commands incl. `runQuery`, `explain`). Two custom editors: `mssql.executionPlanView` (`*.sqlplan`, priority default) and `mssql.queryStudio` (`*.sql`, priority option) — copy their contribution shape for `mssql.queryResultsSnapshot`.
8. **Cell encoding facts the sampler/profiler/transform engine must honor.** `CompactPage.values` holds `undefined` for NULL cells (use the `nullBitmap`, not value comparison); byte-capped cells hold `TruncatedCellEncoding` markers (`{ $t: "truncated", of, bytes?, digest?, v }`, guard `isTruncatedCellEncoding`, `services/sqlDataPlane/api.ts:317`). `QsCellWindow` is the post-flattening shape ("tagged unions never cross postMessage") and already carries `truncatedBitmap?`. §1.5 defines one normalizing accessor so no algorithm ever branches on encoding.
9. **Messages today.** Pre-QO-7, messages are a plain `QsMessageRow[]` on `ExecutionHost` (`messages` field, cleared per run, `getMessages(afterIndex?)` accessor). QO-7 will move them to a host-owned `MessageStore` with windows. §5.6 defines `QueryResultMessageCapture` as an interface now so the swap is invisible to snapshots.
10. **Observability registry mechanics (verified in perftest).** `packages/observability-contracts/src/registry/event-types.json`: 81 events / 11 metrics; each event = `{ name, kind, phase, pairsWith (explicit — never guessed), feature, processRoles, timingClass, measurementEligible, attrs: { attrName: classification }, attrsComplete }`; attr classifications in use: `structuralMetadata` | `safeEnum` | `diagnosticMetric`. New vocabulary lands in the registry **first**, then regenerate + re-vendor into both repos, then emit (QO invariant 9). §7 gives paste-ready entries. The base plan's §18 note ("if the branch requires registry-first") is wrong-way-soft: the branch **does** require it.
11. **QO-9a caution transfers.** The 100-result-set scenario found a real per-query-vs-per-set ack-ordinal deadlock (QO journal Entry 4, D-0015). Multi-result-set shapes are where lifecycle bugs hide. The C2D scenario set (§8.6) must include a many-result-set pin/snapshot shape, and CLI note: repeated `--scenario` flags run only the last one — use the config scenario list.
12. **Store corruption/truncation surfaces exist.** `RowStore` per-set state carries `truncatedReason` (`maxRowsPerResultSet` and end-of-set reasons) and `corrupt` (set by `markCorrupt` and by spill-read failure at `rowStore.ts:373`). Frozen summaries must copy both at snapshot time, and later store-level corruption must surface through snapshot `status()` (short/corrupt windows, never throws through UI — base plan §8.3 row stands).

---

## 1. Contract amendments (BINDING API changes to the base plan)

### 1.1 Async-first everywhere

The base plan is internally inconsistent: `QueryResultAccessService.getRows` and `LiveQueryResultSource.getRows` return `QsCellWindow` synchronously, while `QueryResultsPaneDataSource.getRows` returns a Promise and `QueryResultArtifact.getRows` returns `Promise | QsCellWindow`. A coding agent will faithfully implement the contradiction.

**Rule:** every read on `QueryResultAccessService`, `IQueryResultStore`, `LiveQueryResultSource`, and `QueryResultArtifact` is `Promise`-returning, even while the V1 adapter wraps the synchronous `RowStore.getRows` in `Promise.resolve(...)`. Rationale: QO-6 makes the store async (spill reads), and Tiers 1–3 (ResultStoreV2 / STS2 artifacts / remote) are inherently async. Retrofitting async onto a sync contract after three consumers exist is the expensive direction.

The one place sync remains: internal live-run append plumbing inside `ExecutionHost` until QO-6 lands its own async `appendPage`.

### 1.2 Adopt the QO window request shape (with `reason`) as the facade read

Replace the base plan's `getRows(resultSetId, start, count)` facade signature with the `query_optimization_plan.md` §3.2 request object, extended:

```ts
export interface CellWindowRequest {
    readonly resultSetId: string;
    readonly rowStart: number;
    readonly rowCount: number;
    readonly columnStart?: number;          // honored post-QO-7; ignored (full width) before
    readonly columnCount?: number;
    readonly includeColumns?: readonly number[];
    readonly reason:
        | "grid" | "copy" | "text" | "export" | "cellDocument" | "plan"
        | "sample" | "profile" | "transform" | "aiTool" | "diagnostic";
    readonly budget?: EvalBudgetRef;        // §3.5; window reads normally omit
}

export interface IQueryResultStore {
    readonly storeId: string;
    readonly runId: string;
    readonly createdEpochMs: number;
    readonly kind: "rowStoreV1" | "resultStoreV2" | "sts2" | "remote";

    retain(owner: QueryResultLeaseOwner): QueryResultStoreLease;
    getWindow(req: CellWindowRequest): Promise<QsCellWindow>;
    getCell(req: CellLookupRequest): Promise<QueryResultCellValue>;
    streamRows(req: RowStreamRequest): AsyncIterable<QsCellWindow>;   // chunked pull; §3.4
    summary(resultSetId: string): QueryResultSetFrozenSummary | undefined;
    stats(): QueryResultStoreStats;
    demote?(targetMemoryBytes: number): void;                          // §5.1; optional pre-QO-6
}
```

Why this matters now: `reason` is the exact hook QO-6's cache policy needs ("export/scan reads stream WITHOUT LRU re-admission"). If the snapshot layer's sample/profile/transform scans arrive untagged, they will thrash the pinned document's viewport pages the same way exports thrash the live grid today. The V1 adapter maps `getWindow` → `RowStore.getRows` and simply records `reason` in its counters; QO-6 then implements the policy behind the unchanged facade. `QsCellWindow` stays the universal window/element type across all tiers — it already carries `nullBitmap`/`typeHints`/`truncatedBitmap` and the webview consumes it natively.

`streamRows` in V1 is a trivial generator over `getWindow` chunks (`transformChunkRows`, §6); it exists so the transform engine, export, and profiler share one iteration idiom from day one.

### 1.3 One enforcement gate inside the service (not inside the tool)

The base plan puts confirmation "in the tool" (§13). That makes the tool the security boundary; a second consumer (participant, command, a future notebook bridge) would re-implement or forget it. Amend:

- **All value-bearing reads** (`values` output class, §1.4) on `QueryResultAccessService` require a `ResultAccessGrant`. No grant → typed `needsConfirmation` denial. This is enforced in the service, unit-testable, and immune to buggy callers.
- A single `ResultAccessGate` mints grants and is the only component allowed to:

```ts
export interface ResultAccessGrant {
    readonly grantId: string;                 // crypto-random
    readonly snapshotId: string;
    readonly ownerKey: string;                // conversation/tool-session key, §1.8
    readonly operationClass: "values" | "sqlText" | "messageText" | "planXml" | "export";
    readonly scope?: { resultSetIds?: readonly string[]; maxRows?: number; maxBytes?: number };
    readonly expiresEpochMs: number;          // default: single-use, 2-minute expiry
    readonly remainingUses: number;           // default 1
}
```

- Consent surfaces: for LM tools, `prepareInvocation.confirmationMessages` remains the human-consent UI (VS Code shows it before `call` runs); `call` then asks the gate to mint, passing the invocation context. For the `@query` participant and commands, the gate shows its own modal (`window.showWarningMessage({ modal: true }, ...)`) before minting. Either way: **mint → grant → service read**, and the mint/denial is a diagnostics event (`aiTool.confirmation` with outcome, §7).
- Default grant policy: single-use, per-invocation. A per-snapshot-per-conversation remembered grant ("don't ask again for this snapshot in this chat") is decision **C2D-D-02** (§10) — default OFF until designed; if added, it must be revocable and visible in `showStatus`.

### 1.4 Output classification is computed, not assumed

The base plan's per-operation confirmation table (§13.2) is right for whole operations but breaks down once transforms exist (§3): a `groupBy` result contains raw cell values as group keys; a `count` does not. Replace the operation table with a **classification function over the output**, applied uniformly by the gate:

| Output field kind | Class | Confirmation |
|---|---|---|
| row/column counts, durations, bytes, page/spill stats, truncation **flags** | structural | no |
| null counts, non-empty counts, per-column byte stats, histogram **bucket counts** with caller-supplied boundaries | aggregate-numeric | no |
| `count`, `nullCount`, `sum`, `avg`, `stddev`, `distinctCount` | aggregate-numeric | no (see C2D-D-03 for enterprise-policy hook on `sum`/`avg`) |
| `min`, `max`, `topK` values, `groupBy` **keys**, sample rows, `get_rows` windows, auto-derived histogram boundaries | values | **yes** |
| SQL text, message text, plan XML, cell content | their base-plan classes | **yes** |

Crisp rule: **any output byte that is, or derives verbatim from, a cell value is `values` class.** Boundaries/literals the caller supplied themselves are not a leak in the *output* (they already knew them) — but they are data in *diagnostics* (§3.7).

### 1.5 `CellReader` — one normalizing accessor

All host-side consumers (sampler, profiler, transform engine, export writers) read cells through one helper that hides encodings:

```ts
export interface CellRead {
    readonly value: unknown;            // undefined when null
    readonly isNull: boolean;           // from bitmap, never value comparison
    readonly isTruncated: boolean;      // marker or truncatedBitmap
    readonly truncation?: { of: "string" | "binary"; bytes?: number; digest?: string };
    readonly typeHint?: string;
}
export function cellAt(window: QsCellWindow, row: number, col: number): CellRead;
export function pageCellAt(page: CompactPage, columns: QsResultColumn[], row: number, col: number): CellRead;
```

Rules: nulls come from the bitmap; truncated cells expose the prefix as `value` with `isTruncated: true`; profilers count truncated cells and never hash/compare a prefix as if it were the full value (use `truncation.digest` for equality when present, else treat as incomparable). This closes a subtle correctness hole: a `distinctCount` over a truncated column would otherwise silently merge distinct values sharing a prefix.

### 1.6 Snapshot provenance capture

Extend `QueryResultSnapshot` frozen capture with: `runRecordId` (from `beginRunRecord`), `tuningDigest`, `tuningProfile`, and `storeKind`. Extend `describeSnapshot` with the same (all structural/safe-enum). This ties every snapshot to the replayable run record and tuning combo — the perftest spread reports get snapshot-read numbers keyed by producer configuration for free.

`runId`: reuse/derive from the existing run-record identity rather than inventing a second id space; if the record id shape is unsuitable as a public opaque id, generate `qsrun_<random8>` and stamp it into the run record so the two are joined. Record which in the journal.

### 1.7 `reason` propagation is mandatory

Every service read carries `reason` down to the store (per §1.2) and up into diagnostics attrs (`safeEnum`). The pinned document's `qs/getRows` maps to `reason: "grid"`; exports to `"export"`; the AI tool's `get_rows` to `"aiTool"`; engine scans to `"transform"`. This one enum is the joint between C2D and QO-6 — omit it and the two efforts collide later.

### 1.8 Owner scoping is best-effort — say so in the design

VS Code's LM-tool API does not hand tools a durable, spoof-proof conversation identity in all invocation paths. Derive `ownerKey` from the best available context (chat participant request context when present; else a per-window tool-session nonce), and document plainly: **unguessable snapshot ids + the grant gate are the primary controls; owner scoping prevents accidents, not adversaries.** Tests assert the accident-prevention behavior (a lease acquired under key A is not resolvable under key B), not a security property the platform can't provide.

---

## 2. What the base plan already gets right (keep, do not re-litigate)

Snapshot-platform-first ordering; leases with a single wrapper owning real `dispose`; O(result-set-count) snapshot creation; frozen summaries + clamped row counts; readonly custom document over a virtual URI with the FileSystemProvider fallback spike; shared-pane extraction instead of a grid fork; `Qs*` RPC reuse in slice 1; context service + resolution ladder; completed-only rule; STS2 untouched in phase 1; the §24 design checklist. All C2D batches inherit these unchanged except where §§1, 3–8 amend them.

---

## 3. The composable data layer (new design — the core of this addendum)

The base plan gives storage, leases, and one-off `sampleRows`/`profileResultSet` operations. The product goal is broader: result data available across the product, with AI (and later plotting and notebooks) able to *ask questions about* data it should never scan row-by-row. That requires a real separation between **storage/retrieval** and **transformation**, with composition between them — conceptually like C++ containers/ranges/algorithms (deliberately *not* that API surface area; the parallel is the separation of concerns, not the template zoo).

### 3.1 Concept mapping

| STL concept | This design | Notes |
|---|---|---|
| container | `IQueryResultStore` / snapshot | owns bytes, bounded, tiered (V1/V2/STS2/remote) |
| iterator | `streamRows` chunk pull (`AsyncIterable<QsCellWindow>`) | one iteration idiom for engine/export/profiler |
| range/view | `RowRange` (§3.3) | lazy, cheap to construct, composable, never materializes on construction |
| algorithm | transform ops + terminals (§3.4) | pure, bounded, single-pass where possible, storage-agnostic |
| execution policy | `EvalBudget` (§3.5) | every evaluation runs under an explicit budget and reports honesty stats |

Separation rules (binding): algorithms never know the storage kind; stores never know algorithms; the only coupling is `CellWindowRequest`/`QsCellWindow`/`CellReader`. UI, AI, plotting, and notebooks are all *consumers of evaluations*, never row-loop authors.

### 3.2 Why a serializable spec instead of callbacks

Transformations are expressed as a small, versioned, serializable JSON **transform spec** — a mini logical plan — rather than host-side callbacks, because the spec is simultaneously: (a) the AI tool's input (`evaluate_transform`, §4.2) with strict schema validation and **no code execution**; (b) the definition of a derived snapshot (§3.6) — parent + spec, reproducible; (c) auditable and digestible (`specDigest = sha256[0:12]` of canonical JSON) for diagnostics and replay; (d) a future pushdown unit — the same spec can later compile to SQL/STS2 server-side evaluation without changing any consumer. Callbacks give you none of these.

### 3.3 `RowRange` (view)

```ts
export interface RowRange {
    readonly snapshotId: string;
    readonly resultSetId: string;
    readonly rows:
        | { kind: "all" }
        | { kind: "span"; start: number; count: number }
        | { kind: "sourceRowIds"; ids: readonly number[] }          // selection / derived
        | { kind: "derived"; derivedSnapshotId: string };
    readonly columns?: readonly number[];                            // ordinals; omitted = all
}
```

Construction is O(1). Materialization happens only through the engine or a window fetch, always bounded.

### 3.4 Transform spec v1

```jsonc
{
  "v": 1,
  "source": { "snapshotId": "…", "resultSetId": "…", "rows": { "kind": "all" }, "columns": [0, 3, 5] },
  "ops": [
    { "op": "filter", "pred": { "and": [
        { "col": 3, "cmp": "ge", "value": 100 },
        { "not": { "col": 5, "cmp": "isNull" } } ] } },
    { "op": "project", "columns": [0, 3] },
    { "op": "slice", "offset": 0, "limit": 100000 }
  ],
  "terminal": { "kind": "groupBy", "keys": [0], "aggs": [
      { "fn": "count" }, { "fn": "avg", "col": 3 } ],
      "maxGroups": 1000, "orderBy": { "agg": 0, "dir": "desc" }, "limitGroups": 50 }
}
```

**Ops (row-to-row, fusable):** `filter` (predicate tree `and`/`or`/`not` over leaves `{col, cmp, value?}` with `cmp ∈ eq|ne|lt|le|gt|ge|isNull|notNull|contains|startsWith|inSet`), `project`, `slice`. Comparison typing: numeric compare when both sides coerce cleanly per `typeHints`, else ordinal string compare; document the coercion table in code; truncated cells compare per §1.5 (incomparable → predicate false, counted in `EvalStats.truncatedCellsSkipped`).

**Terminals (exactly one):**

| Terminal | Output class (§1.4) | Bounded algorithm |
|---|---|---|
| `rows { limit }` | values | window materialize, ≤ `maxOutputCells`/`maxOutputBytes` |
| `aggregate { aggs[] }` | aggregate-numeric (except `min`/`max` → values) | streaming accumulators, one pass |
| `groupBy { keys, aggs, maxGroups, … }` | **values** (keys) + aggregate-numeric | hash groups capped at `maxGroups`; overflow rows accumulate into one `__other__` bucket with `overflowGroups` count — never unbounded, never silently dropped |
| `topK { col, k, by: value\|frequency }` | values | heap (by value) / space-saving sketch (by frequency, approximation flagged) |
| `histogram { col, boundaries? }` | aggregate-numeric with caller boundaries; values if boundaries auto-derived | one pass; `auto` = min/max pre-pass charged against the same budget |
| `distinctCount { col, exactCap }` | aggregate-numeric | exact hash-set to `maxDistinctExact`, then `{ atLeast: cap, exact: false }`; HLL is future (C2D-D-06) |
| `sample { strategy, n }` | values | strategies from base plan §14.1 + `reservoir` (uniform without O(rowCount) windows) |

**Sorting** is deliberately not a v1 op: full sort is unbounded. `topK` and `groupBy.orderBy` cover the real asks; grid-side sort stays threshold-gated as today; a `derived`-snapshot sort under `maxDerivedRows` is a follow-on (C2D-D-07).

### 3.5 Engine execution model

Single-pass **fusion**: filter/project/slice and the terminal accumulate in one chunked scan (`streamRows`, `reason: "transform"`, chunk = `transformChunkRows`). Cooperative yielding every `transformYieldEveryRows` rows (`setImmediate`) — the extension host UI thread is shared; a 1M-row scan must not freeze completions. `CancellationToken` checked at every yield point.

```ts
export interface EvalBudget {
    maxRowsScanned: number;   // default 1_000_000
    maxEvalMs: number;        // default 10_000
    maxGroups: number;        // default 10_000
    maxOutputCells: number;   // default 10_000
    maxOutputBytes: number;   // default 1 MiB (shares AI caps)
}
export interface EvalStats {
    rowsScanned: number; rowsMatched: number; elapsedMs: number;
    partial: boolean;                       // budget cut in — result covers a prefix
    partialReason?: "rows" | "time" | "groups" | "outputBytes" | "canceled";
    truncatedCellsSkipped: number;
    spillReads: number; cacheHits: number;  // from store counters
}
```

**Honesty discipline (mirrors QO invariant 4):** every result carries `EvalStats`; a budget-cut result says `partial: true` + reason and states the scanned prefix — it never pretends to be the full answer. AI tool output includes these stats verbatim so the model can reason about coverage ("aggregate over first 1,000,000 of 4.2M rows").

**Determinism:** given (immutable snapshot, spec, budget), results are deterministic — `reservoir` sampling uses a seeded PRNG (seed = specDigest) — enabling golden tests and replay.

Worker-thread offload is **not** v1 (C2D-D-05): measure first; the QO-6 async store plus yielding may suffice. The engine's chunk-pull shape makes the later move mechanical.

### 3.6 Derived snapshots

`deriveSnapshot(parentSnapshotId, spec /* row-producing: ops only, or terminal rows */, owner)`:

- Evaluates the spec once (budgeted) collecting **matching `sourceRowId`s up to `maxDerivedRows`** (default 100k); over cap → typed error offering export instead. No page copies.
- Produces a new immutable snapshot: same store lease, `rows: { kind: "sourceRowIds"/index }`, frozen derived row count, `parentSnapshotId` + `specDigest` lineage in `describeSnapshot`.
- Grid-windowable: `getWindow` over a derived snapshot maps derived offsets → source row ids → underlying windows (batched, still bounded). This is the "AI filters, user pins the filtered view" flow — the demo that proves the composability, and the eventual replacement for webview in-memory sort/filter above threshold.
- Retention: derived snapshots are leases on the parent's store like any other; disposing the parent snapshot object does not kill the store while a derived lease lives.

### 3.7 Diagnostics classification of specs

Loggable (structural/safeEnum): op kinds, terminal kind, column **ordinals**, predicate node count, `specDigest`, budget values, all `EvalStats`. Never logged: filter/inSet **literal values** (user- or model-supplied data), column **names** (identifiers — digests only if needed), any output values. The privacy canary (§8.5) seeds a sentinel filter literal and asserts its absence from every diagnostics payload.

### 3.8 Consumers, unified

- `profileResultSet` and `sampleRows` are **re-based as canned specs** run through the engine (shape/null tiers = `aggregate`; value tiers = `topK`/`min`/`max`/`sample` behind the gate). One scan implementation, one budget/honesty story, one test surface — do not ship a bespoke profiler in C2D-5 and rewrite it in C2D-7.
- The AI tool gains one operation, `evaluate_transform` (§4.2).
- **Plotting (later consumer, design hook only):** a chart = transform spec (`groupBy`/`histogram`) + chart kind, rendered in a webview from the bounded aggregate output — raw rows never enter the renderer. No batch work now; the engine's output shape is already chart-feedable.
- **Notebooks/Python (future tier, design hooks only):** the honest v1 bridge is **export**: add `arrow` (Arrow IPC / Feather v2) to the export-writer roadmap because CSV destroys the type fidelity §9.1 of the QO plan fights for (decimals, temporals); a generated scaffold cell (`pd.read_feather(path)`) plus explicit confirmed export covers "expose data to a Python cell" without inventing a kernel protocol. A live lazy bridge (local endpoint speaking the same window/sample contract into a shared kernel) is Tier-3-shaped — same `IQueryResultStore` semantics over a transport — record as future work, build nothing now. Dependency note: `apache-arrow` npm adds real bundle weight → decision **C2D-D-04**; Parquet-in-JS is heavier still, not v1.

### 3.9 Non-goals of the transform layer (v1)

No SQL pushdown (spec is designed to allow it later); no cross-snapshot joins; no user-defined functions or expressions beyond the predicate grammar; no mutation (derive, never edit); no persistence of specs beyond the snapshot registry.

---

## 4. AI-surface amendments

### 4.1 `mssql_run_query` reconciliation (REQUIRED, C2D-5)

Leaving `mssql_run_query` unbounded next to the new tool makes the new tool decorative. Two-step reconciliation:

- **P0 (in C2D-5, small diff):** cap `rows` serialized into the tool result at `mssql.queryResults.ai.maxRowsPerResponse` / `maxBytesPerResponse`, add `{ truncated: true, totalRowCount, returnedRowCount }` metadata, and append guidance text pointing at `mssql_query_results` for bounded continued access. No behavior removal; existing agent flows keep working on small results. Update the tool description so models learn the division of labor (run = execute + head; query_results = analyze).
- **P1 (future tier, after C2D-T; hook only now):** optional routing of agent-executed queries through a **headless Query Studio run** (ExecutionHost without an editor) into a `RetainedRowStore`, returning `{ snapshotHandle, headSample, describe }`. Reserve `LiveQueryResultSource.sourceKind: "queryStudio" | "headless"` in the type now; build nothing else. This unifies "AI ran a query" with the snapshot platform and retires the legacy `simpleexecute` lane for agent use.

### 4.2 Tool operation set (amended)

Add `evaluate_transform` (spec in, gated-by-output-class result out) and `derive_snapshot` to the base plan's operations. Amended classification (gate computes per §1.4; table is the expectation, the function is the law):

| Operation | Confirmation |
|---|---|
| `list_live`, `list_snapshots`, `describe_snapshot` (schema/counts), `create_snapshot`, `release_snapshot` | no |
| `evaluate_transform` → aggregate-numeric-only output | no |
| `evaluate_transform` → any `values`-class field (rows/sample/topK/min/max/groupBy keys/auto-histogram) | **yes** |
| `derive_snapshot` | no (handle only, no values returned) |
| `sample_rows`, `get_rows` | yes |
| `profile_result_set` shape/safe-count tiers | no; value tiers **yes** |
| `describe_snapshot` with SQL/message text | yes |
| `export_snapshot` | **yes**, with §4.4 wording |

### 4.3 Confirmation UX — API truth correction

VS Code LM-tool confirmations render **Continue/Cancel** from `confirmationMessages { title, message: MarkdownString }`. There is no third "Show details" button (base plan §13.3). Fold the details (source title, snapshot age, result-set/row/column counts, requested bounds, approx bytes, which sensitive classes are included, requester, reason) into the markdown message itself. Participant/command paths use the gate's own modal with equivalent content (§1.3).

### 4.4 Prompt-injection and exfiltration hygiene

- **Cell values are untrusted text.** Tool results wrap values in clearly delimited data blocks with a fixed preamble instructing the model to treat contents as data, never instructions; control characters stripped/escaped; per-cell bytes capped (`DEFAULT_AI_SINGLE_CELL_BYTES` stands). This mitigates, not solves — record as an accepted residual risk in the design doc; do not claim otherwise.
- **Export is an exfil channel with a user gate.** A confirmed `export_snapshot` places full data on disk where other tools (file readers) can access it without further row confirmations. The confirmation message must say exactly that ("writes the full result data to `<path>`; other tools and processes can read that file"). AI-initiated exports always show the destination.
- **Resource caps per conversation:** max concurrent snapshots per `ownerKey` (default 5), max concurrent `evaluate_transform` (default 1, queue depth 2), `aiTool` leases always TTL'd. Prevents a chatty agent from pinning the retention budget (§5.2) or saturating the host with scans.

### 4.5 Base-plan §13 items unchanged

Tool-before-participant ordering, thin `@query` orchestration over the same service, inline-completion separation, and `@query /python` scaffold-first stance all stand — with `/python` now pointing at the §3.8 arrow-export bridge when it eventually lands.

---

## 5. Storage and lifecycle amendments

### 5.1 Retained-store memory demotion (new; big win, cheap)

A live `RowStore` holds up to 64 MiB of hot pages because the user is scrolling it. A retained store behind a pinned document is read-occasionally. Without demotion, ten pinned snapshots can hold ~640 MiB of extension-host heap doing nothing.

On `releaseLiveOwner(...)`: shrink the store's memory cap to `retainedStoreMemoryBytes` (default 8 MiB). Pre-QO-6 (sync spill): **lazy** demotion only — set the cap; natural touches evict; do not synchronously spill tens of MiB on the release path (that's a host stall). Post-QO-6: eager async demotion through the spill queue. Re-promotion on sustained pinned-doc scrolling is optional polish (C2D-8). Expose `demote()` on the facade as optional (§1.2).

### 5.2 Retention accounting is per-STORE, and the numbers must cohere

Two coherence bugs in the base plan's §15.3/§16.3 numbers as written:

1. `snapshot.maxUnpinned: 10` × per-store spill cap 2 GiB → worst-case ~20 GiB on disk while `maxRetainedBytesMb: 2048` claims a 2 GiB budget. The unit of cost is the **store** (memory + spill), not the snapshot; multiple snapshots/leases on one store cost once. Retention math dedupes by `storeId`; `showStatus` reports both counts and deduped bytes.
2. Enforcement points: at snapshot **create** (would the newly retained store exceed the global budget? → sweep expired/LRU-unpinned first, then refuse with the base plan's clear error) and on the periodic sweep. Leased snapshots are never silently disposed (unchanged).

### 5.3 Lifecycle state machine + race rules

`RetainedRowStore`: `active → draining → disposed`. `retain`/`acquireSnapshot` succeed only in `active`; release of the final lease moves `active → draining` (cleanup scheduled) `→ disposed`. All of `release`, `dispose`, `releaseLiveOwner` are idempotent; `acquire` racing a retention sweep either gets a valid lease or a clean `undefined` — never a lease on a disposing store. The sweep takes a registry-level mutex per store transition. Unit tests drive these interleavings explicitly (§8.2); this is where a lease system rots if left to vibes.

### 5.4 Spill directory crash-safety

Per-run spill dirs must be attributable to a session so a startup sweep can reclaim orphans from crashed hosts without racing a live sibling window: name run dirs `run<counter>_<sessionNonce>` (nonce generated per extension activation) and write a `session.lock` heartbeat file (mtime-touched on a slow timer) at the spill root. Startup sweep deletes run dirs whose session nonce has a stale/absent lock. Deactivation still best-effort sweeps everything it owns (base plan §8.3 row stands). This moves from C2D-8 "hardening" to a C2D-1 requirement — leaked multi-GiB spill files from one crash during dogfood is how features get turned off.

### 5.5 QO-6 coordination (merge choreography)

C2D and QO-6 both touch the store. The commuting order:

1. **C2D-1 lands the facade first** (`IQueryResultStore` per §1.2, `RetainedRowStore`, leases, `reason` plumbed) with the V1 sync-inside/async-outside adapter. C2D-2/3 build on it.
2. **QO-6 then implements behind the facade** — async spill, frame v2, protected/probationary cache, the `reason:"export"`-style no-readmit policy (now generalized to all scan reasons per §1.7). The facade and its contract kit (§8.1) are QO-6's target interface; consumers don't change.
3. If the schedule inverts (QO-6 first), the contract kit still protects; the facade adapter then wraps the async store natively. Either way, record the chosen order in both journals.

Two technical joints: (a) once appendPage backpressure exists, snapshot scan reads share the spill file/queue with live ingestion — reads use **positioned** async reads (`fs.read` with `position`; the current single-fd `readSync`/`writeSync` pairing is already positional, keep it that way) and the QO-6 queue gives appends priority over scans, scans over nothing (a background sample must not starve a streaming query, per QO's protected-viewport principle); (b) frame v2 spill of already-encoded pages (QO-5/6) is invisible through the facade by construction.

### 5.6 Message capture is an interface (QO-7 joint)

```ts
export interface QueryResultMessageCapture {
    readonly summary: QueryResultMessageSummary;   // counts, hasErrors, firstErrorIndex
    getWindow?(start: number, count: number): Promise<{ messages: QsMessageRow[] }>;
    getText?(req: { includeTimestamps: boolean; range?: {start: number; count: number} }): Promise<string>;
}
```

V1 (`includeMessages: "allLocal"` under threshold): frozen array copy behind the interface. Post-QO-7: a frozen range over the host `MessageStore`. Base-plan policy (summary always; full text local-only under threshold; AI needs confirmation) unchanged.

### 5.7 Snapshots during multi-set streaming runs

Per-result-set pinning of a **complete** set while later sets stream is legal (base plan §8.4 keeps the simpler run-not-streaming rule for slice 1; when the per-set rule lands): concurrent appends to *other* sets are safe (pages are per-set), frozen row-count clamp guards the pinned set, and LRU/spill churn from continued ingestion is just the normal read path. The failure modes to test: run **cancel** and cap-`truncatedReason` after the pin (snapshot flags must reflect the frozen state at pin time, not the run's final state), `markCorrupt` on a *different* set (pinned set unaffected), and spill-read corruption after pin (short/corrupt window surfaced through snapshot `status()`). Reuse the QO-9a 100-result-set fixture — that shape already found one lifecycle bug this month.

### 5.8 Web extension host

`RowStore` is `fs`-sync desktop code; phase 1 is **desktop-only**. Gate activation of pinned docs/tool on `env.uiKind`/fs availability with a clear "not available in web" notice; the facade's `kind` field is the eventual web path (`webIndexedDbPageStore`, QO plan §3.4). One sentence in docs, one guard in code, zero surprises.

### 5.9 Pinned webview memory

`retainContextWhenHidden: true` × N pinned tabs multiplies renderer memory. Accept for slice 1 with a documented soft cap (warn via status when pinned docs > 8), and note the follow-on: serialize/rehydrate via `getState`/`setState` so hidden pinned tabs can drop their webview. The pinned bootstrap state must include the same grid style/capability payload live QS sends (post-QO-1 that includes the tuning-derived grid policy in `QsState`); the pinned controller synthesizes a snapshot-state equivalent with execution fields absent.

---

## 6. Parameter and settings discipline (QO invariant 11 applied)

The base plan hardcodes AI/engine constants (`DEFAULT_AI_ROW_LIMIT` etc.). Branch law: **no new perf-relevant constant lands unregistered.** These are service-lifetime knobs, not per-run QueryTuning params, so: define a small `queryResultsParams` module reusing the QO-1 normalize/digest helpers, resolved from `mssql.queryResults.*` settings with a single **`mssql.queryResults.overrides`** object setting as the perftest per-combo carrier (mirroring `mssql.queryStudio.tuning.overrides` so the QO-9b spread factory sweeps these identically).

| Knob | Default | Sweepable |
|---|---:|:---:|
| `ai.maxRowsPerResponse` / `ai.maxBytesPerResponse` / `ai.maxCellBytes` | 100 / 1 MiB / 16 KiB | ✓ |
| `ai.snapshotTtlMinutes` / `ai.maxSnapshotsPerConversation` | 30 / 5 | ✓ |
| `snapshot.maxUnpinnedStores` / `snapshot.maxRetainedBytesMb` | 10 / 2048 | ✓ |
| `retainedStoreMemoryBytes` | 8 MiB | ✓ |
| `transform.chunkRows` / `transform.yieldEveryRows` | 2048 / 8192 | ✓ |
| `transform.maxRowsScanned` / `maxEvalMs` / `maxGroups` / `maxDistinctExact` | 1M / 10 000 / 10 000 / 100 000 | ✓ |
| `derived.maxRows` | 100 000 | ✓ |
| `pinnedDocuments.enabled` / `ai.enabled` | true / true | policy, not swept |

Resolved snapshot digest (`qrParamsDigest`) stamps `aiTool.invoke` and `transform.evaluate` events — same comparability story as `tuningDigest`.

---

## 7. Observability amendments (registry-first mechanics)

Base plan §18's name list stands; this section makes it executable against the verified registry shape (§0.10). Feature: `queryResults`. Process roles: `extensionHost` (all), `webview` for pin-paint marks. All pairs explicit via `pairsWith`. Paste-ready exemplars (extend the family in this exact shape):

```jsonc
{ "name": "mssql.queryResults.snapshot.create.begin", "kind": "marker", "phase": "begin",
  "pairsWith": "mssql.queryResults.snapshot.create.end", "feature": "queryResults",
  "processRoles": ["extensionHost"], "timingClass": "sameProcessMonotonic",
  "measurementEligible": true, "attrs": {}, "attrsComplete": false },
{ "name": "mssql.queryResults.snapshot.create.end", "kind": "marker", "phase": "end",
  "pairsWith": "mssql.queryResults.snapshot.create.begin", "feature": "queryResults",
  "processRoles": ["extensionHost"], "timingClass": "sameProcessMonotonic",
  "measurementEligible": true,
  "attrs": { "resultSetCount": "structuralMetadata", "totalRows": "structuralMetadata",
             "ownerKind": "safeEnum", "purpose": "safeEnum", "scanFree": "safeEnum" },
  "attrsComplete": true },
{ "name": "mssql.queryResults.transform.evaluate.end", "kind": "marker", "phase": "end",
  "pairsWith": "mssql.queryResults.transform.evaluate.begin", "feature": "queryResults",
  "processRoles": ["extensionHost"], "timingClass": "sameProcessMonotonic",
  "measurementEligible": true,
  "attrs": { "terminalKind": "safeEnum", "opCount": "structuralMetadata",
             "rowsScanned": "diagnosticMetric", "rowsMatched": "diagnosticMetric",
             "partial": "safeEnum", "partialReason": "safeEnum",
             "specDigest": "structuralMetadata", "reason": "safeEnum" },
  "attrsComplete": true }
```

Derived metrics registered alongside: `mssql.queryResults.snapshot.create`, `.pin.open`, `.window`, `.transform.evaluate`, `.sample`, `.profile`.

Additional events beyond the base list: `transform.evaluate.begin/end`, `transform.canceled`, `derive.begin/end`, `demote.begin/end`, `grant.minted` / `grant.denied` (attrs: `operationClass` safeEnum, `outcome` safeEnum — these subsume the base plan's `aiTool.confirmation`/`aiTool.denied`).

**Emission gating by `diagnosticsLevel` (QO-2, exists):** minimal = lifecycle (create/dispose, pin open/close, tool invoke, grant outcomes); diagnostic = per-operation aggregates (`EvalStats`, window-serve totals); verbose = per-window/per-chunk. `scanFree: true` on `snapshot.create.end` is the standing regression proof that creation stayed O(result-set-count).

**Registry-first is per batch, not deferred:** the base plan parks vocabulary work in C2D-8; that violates the contracts discipline. Each batch registers its family before first emission (C2D-1 registers snapshot/lease/demote; C2D-T registers transform/derive; C2D-5 registers grant/tool), regenerating + re-vendoring both repos each time — the QO-1/QO-2 entries in the QO journal are the worked example including the conformance-failure mode when this is skipped.

**Debug Console alignment:** `mssql.queryResults.showStatus` (base plan §18.3, plus deduped store-bytes per §5.2, recent grants/denials, and active `EvalStats` for in-flight scans) is v1. A page in the internal debug/diagnostic webview — leases, snapshots, transform history by digest + op kinds, denial log — is the follow-on round, same posture as the QO Debug-Console tuning page: C2D must make it *possible* (all status data behind one queryable service call), not build it.

---

## 8. Test-plan additions (beyond base plan §19)

### 8.1 Store contract kit
One shared test suite parameterized over `IQueryResultStore` implementations (V1 adapter now; ResultStoreV2, and any fake, later): window equivalence vs a reference in-memory oracle, clamping, reason tagging, truncation/corrupt surfacing, lease semantics, stats monotonicity, `streamRows` ≡ concatenated `getWindow`. QO-6 inherits its acceptance suite for free.

### 8.2 Lifecycle interleavings
Deterministic tests for §5.3's races (acquire-vs-sweep, double release, release-during-drain, dispose idempotency) plus fake-timer TTL sweeps; a randomized interleaving stress (seeded) over acquire/release/sweep/demote with the invariant "no lease ever observes a disposed store."

### 8.3 Transform engine
Golden tests vs a naive full-materialize reference on small fixtures for every op/terminal; property tests (random specs × random small snapshots, engine ≡ reference); budget-honesty tests (every cap → `partial` + correct reason + prefix semantics); cancellation actually halts at a yield point (rowsScanned stops advancing); determinism incl. seeded reservoir; truncated-cell comparison semantics per §1.5; groupBy overflow-bucket accounting sums to rowsMatched.

### 8.4 Gate enforcement (service-level)
Value-class reads without a grant fail **at the service** even when invoked through a deliberately misbehaving fake tool; grants are single-use/expiring; ownerKey-A grant unusable under key-B; classification function unit-matrix over every terminal/output-field combination in §1.4.

### 8.5 Privacy canaries (mechanics)
Fixture rows seed a sentinel value (`CANARY_<random>`); a test filter uses a sentinel literal (`LITCANARY_<random>`). Assert both absent from: all marker/event attrs at every diagnostics level, `showStatus` output, tool results for metadata-only ops, and the registry-conformance capture of a full pin→sample→transform run. This is the "part of done" bar QO invariant 8 already sets.

### 8.6 Perf scenarios (perftest, reuse QO-9a substrate)
Family `queryresults-*`, `maturity:"exploratory"`, wallclock unofficial, registered via the same shape-factory pattern as `registerQueryStudioShape`, over the **existing** QO-9a fixtures (100k-narrow, wide-1000×300, large-cells, 100-resultsets): `pin-after-100k` (run→pin→first pinned paint), `pin-survives-rerun` (rerun source, assert pinned window equivalence + timings), `snapshot-create-scanfree-1m` (flag-gated with the 1M seed decision), `transform-groupby-100k` (rows/s target + partial=false), `sample-100-from-spilled`, `retention-sweep-50`, `pin-multiset-100` (§5.7 shape), `demote-then-scroll` (post-demotion first-window latency). Budgets: base plan §16.1 stands; add transform scan throughput ≥ 200k rows/s on 100k-narrow (validate against baseline, tune knob defaults from data — the QO-9b spread machinery sweeps `mssql.queryResults.overrides` identically to tuning overrides).

---

## 9. Execution-plan amendments

Batch identity and exit gates from base plan §20 stand except as amended below. **New batch C2D-T inserted between C2D-4 and C2D-5** so the tool's sample/profile/evaluate operations are engine-backed from day one instead of bespoke-then-rewritten.

| Batch | Amendments (delta only) |
|---|---|
| **C2D-0** | Add: local current-state re-verification (§12.1 greps) recorded in journal; spike also confirms tab-restore-after-reload hits `openCustomDocument` → expired-document path cleanly; decide `Qs*`-reuse question and record. |
| **C2D-1** | Facade per §1.2 (async, `getWindow`+`reason`, `streamRows`); provenance capture §1.6; demotion cap-shrink §5.1; per-store budget accounting §5.2; lifecycle state machine §5.3; session-nonce spill dirs + startup orphan sweep §5.4 (moved up from C2D-8); register snapshot/lease/demote vocabulary first §7; store contract kit §8.1 + interleaving tests §8.2. Exit-gate additions: contract kit green; `scanFree` attr proven; orphan sweep test green; no unregistered constants (§6 module exists with the retention/AI knobs it needs so far). |
| **C2D-2** | Selection payload gains `snapshotView` (§0.5). Unchanged otherwise. |
| **C2D-3** | Pinned bootstrap state parity note §5.9; `qs/getRows` maps to `reason:"grid"`. |
| **C2D-4** | Unchanged + context resolution order still per base §12.2. |
| **C2D-T (new)** | `CellReader` §1.5; transform spec v1 + validation + digest §3.4; fused engine + budgets/honesty/cancel §3.5; derived snapshots §3.6; re-base sampler/profiler as canned specs §3.8; register transform/derive vocabulary; §8.3 tests; `transform-groupby-100k` + `sample-100-from-spilled` scenarios. Exit gate: golden+property suites green; budget-cut honesty proven; cancellation halts mid-scan; canned profile ≡ old ad-hoc expectations; canary incl. filter-literal passes. |
| **C2D-5** | Gate-in-service §1.3 + classification function §1.4 (+ §8.4 tests); ops `evaluate_transform`/`derive_snapshot` §4.2; confirmation UX per §4.3; **`mssql_run_query` P0 cap** §4.1; per-conversation caps §4.4; grant vocabulary registered. Exit-gate additions: service rejects ungated value reads under hostile fake caller; run_query outputs bounded with truncation metadata. |
| **C2D-6** | `@query` unchanged; consent via the gate's modal path. |
| **C2D-7** | Now: report generation over engine outputs; value-tier profiling polish; derived-snapshot **pinning** (pin a filtered view); progress UI for long scans. The sampler/profiler build itself moved to C2D-T. |
| **C2D-8** | Loses the items moved to C2D-1/§7; gains: webview `getState` rehydrate spike §5.9; demotion re-promotion polish; `queryresults-*` scenario completion + baseline runs recorded; knob-default tuning from spread data (record decisions in journal). |
| **C2D-9** | Unchanged, plus arrow-export decision execution if C2D-D-04 approves; headless-run P1 lives here or later. |

**Sequencing vs QO (record the choice in both journals):** recommended interleave — finish QO-9a baselines (in flight), then **C2D-0..3 before QO-6** (§5.5 rationale: facade-first), then QO-6/QO-7 behind the facade, then C2D-4/T/5 in parallel with QO-5/QO-4 (disjoint files), then the tails. File-ownership boundary while parallel: C2D owns `src/queryResults/**` and makes wrap-don't-rewrite edits in `executionHost.ts`; QO owns `rowStore.ts` internals and STS2. The contract kit is the treaty line.

**Verification chain per batch:** identical to QO `EXECUTION_PLAN.md` §4 (build:extension + build:webviews + lint + suite for vscode-mssql; perftest build + workspace tests + conformance + doctor; contract regeneration/re-vendor on any registry change; run IDs + metric deltas journaled for any perf claim). Known pre-existing suite failures as of QO Entry 4: sqlScripting strict-host CACHE-6, sqlLanguage `sys.all_*` scoping, CopilotChatEntry alternating flake — not C2D's to fix; verify failures against a stash-run of clean HEAD before attributing.

**Journal:** this effort keeps its **own** `PROGRESS.md` beside these docs (same rules as QO's: one entry per batch/sub-batch, commits, deviations, residuals; journal wins on conflicts; restart = journal → base plan → this addendum → continue from first unfinished batch). Entry 0 = plan established, referencing this addendum's §0 verification.

---

## 10. Decisions (defaults; decide during build, record in journal)

| ID | Decision | Default position |
|---|---|---|
| C2D-D-01 | QO-6 ordering | facade-first (C2D-0..3 before QO-6); §5.5 |
| C2D-D-02 | Remembered per-snapshot-per-conversation grants | OFF; per-invocation single-use until revocation UX designed |
| C2D-D-03 | `sum`/`avg` classification | aggregate-numeric (no confirm); add an enterprise-policy hook point so a stricter mode can flip them to `values` |
| C2D-D-04 | Arrow IPC export dependency | deferred to C2D-9; approve only with bundle-size measurement; Parquet not considered v1 |
| C2D-D-05 | Worker-thread transform engine | no; yield-based first, measure via `transform-groupby-*` scenarios before adding a worker |
| C2D-D-06 | Approximate distinct (HLL) | no; exact-under-cap with honest `atLeast` overflow |
| C2D-D-07 | Derived-snapshot sort terminal | not v1; topK + grid threshold sort cover asks; revisit with dogfood demand |
| C2D-D-08 | `run_query` P0 cap value | `ai.maxRowsPerResponse` (100) — deliberately same knob; revisit if agent flows need a distinct execute-head size |
| C2D-D-09 | Pinned-tab soft cap / rehydrate | soft-warn at 8; `getState` rehydrate only if dogfood memory data demands |
| C2D-D-10 | `mssql.queryResults.overrides` visibility | internal/preview (matches `tuning.overrides` posture) until spread data tunes defaults |

---

## 11. Amended design checklist (append to base plan §24)

- Is this read tagged with a `reason`, and does that reason reach the store and diagnostics?
- Is this surface `Promise`-returning even though V1 resolves synchronously?
- If this output contains any byte derived verbatim from a cell value, does it pass the gate?
- Does this evaluation carry a budget, and does a budget cut produce `partial: true` with a reason instead of a confident lie?
- Is every new constant a registered knob under `mssql.queryResults.*`?
- Was the vocabulary registered + regenerated + re-vendored **before** first emission?
- Would the QO-9a 100-result-set shape break this? Run it.
- Does the sentinel canary — value *and* filter literal — stay out of every diagnostic surface?

---

## 12. Coding-agent handoff amendments

### 12.1 Current-state verification (run first, journal the results)

Against the **local** checkout (`extensions/mssql`):

```text
grep -n "resolve\|tuning\|beginRunRecord\|diagnosticsLevel" src/queryStudio/executionHost.ts
grep -n "constructor\|stats\|markCorrupt\|truncatedReason" src/queryStudio/rowStore.ts
grep -n "QsUpdateGridSelectionRequest" src/queryStudio/queryStudioController.ts src/sharedInterfaces/queryStudio.ts
grep -n "liveModels" src/queryStudio/queryStudioEditorProvider.ts
grep -n "rows: result.rows" src/copilot/tools/runQueryTool.ts
ls src/sharedInterfaces/queryTuning.ts src/queryStudio/tuning/
```

Expected: QO-1..3 shapes per §0.1–0.3 present. Any mismatch → journal it and adjust before writing C2D-1 code.

### 12.2 Files-to-inspect corrections (base plan §23)

Replace `queryStudioProvider.ts` with `queryStudioEditorProvider.ts`; add `src/sharedInterfaces/queryTuning.ts`, `src/queryStudio/tuning/queryTuningResolver.ts`, `src/queryStudio/replay/qsRunCapture.ts`, `src/services/sqlDataPlane/api.ts` (CompactPage/TruncatedCellEncoding), `src/copilot/tools/runQueryTool.ts` + `toolBase.ts`, and in perftest: `packages/observability-contracts/src/registry/event-types.json`, `packages/perftest-cli/src/scenarios/registry.ts`.

### 12.3 First-PR target (amended)

Base plan §23 list, with: item 4's service surface per §1.2 (async, `getWindow`+`reason`), plus §5.3 state machine, §5.4 session-nonce dirs + startup sweep, §5.1 cap-shrink demotion, §1.6 provenance fields, the §6 params module (retention/AI knobs only so far), the §7 C2D-1 vocabulary registered/regenerated/re-vendored, and the §8.1 contract kit + §8.2 interleaving tests.

### 12.4 Do-not-do additions (first PR)

Base plan §23 list stands; add: do not implement the transform engine, gate, or any tool operation; do not modify `runQueryTool.ts` yet; do not touch `rowStore.ts` internals beyond what the wrapper strictly requires (QO-6 owns that file's future); do not emit any event not yet in the registry.

---

*If a seam still smells like wet cardboard after this addendum, the missing piece is probably a `reason`, a budget, or a grant — add whichever is absent before adding code.*
