# Native TypeScript T-SQL Language Service
## Replacement technical design and phased implementation plan for Query Studio

**Status:** replacement specification, ready for coding-agent handoff.  
**Date:** 2026-07-05.  
**Primary target:** Query Studio editor surface.  
**Primary outcome:** replace Query Studio's STS v1-backed deterministic language features with a native TypeScript language service that uses the new MetadataService and STS2-backed metadata/data-plane endpoints.  
**Initial features:** non-AI completions, tooltips/hover, diagnostics.  
**Separate but planned feature:** go-to-definition and peek-definition through a TypeScript scripting engine.  
**Later/optional feature:** colorization and semantic tokens, without blocking the deterministic LSP feature rollout.  
**Suggested namespaces:**

- `src/sqlLanguage/**` for native language-service core, provider adapters, host integration, tests, and data assets.
- `src/sqlScripting/**` for scripting and definition/peek support.
- Query Studio webview/controller additions under the existing Query Studio feature folders, discovered by searching for `QueryStudioController`, `QsLsp`, `sqlInlineCompletionProvider`, `MetadataService`, `CatalogSnapshot`, and `completionSystemObjectCatalog`.

---

## 0. Coding-agent handoff summary

Build a new Query Studio language service in phases. Do not try to replace everything at once. The service should run inside the VS Code extension host, serve Query Studio's Monaco editor through the existing Query Studio RPC/contract layer, and consume schema truth through a small metadata-provider interface backed by the new MetadataService. The MetadataService remains the only component that talks to STS2 metadata/data-plane endpoints during normal operation.

The implementation should start with the foundation and router, then ship one deterministic feature at a time:

1. **LS-0 Foundation:** settings, routing, old-engine bridge, lexer, segmenter, provider interface, metadata adapter, test harness.
2. **LS-1 Native non-AI completions:** statement sketch parser, binder, completion contexts, ranking, join suggestions, INSERT/EXEC intelligence.
3. **LS-2 Native diagnostics:** lexical/structural diagnostics first, binder diagnostics second, with a strict suppression ladder.
4. **LS-3 Native tooltips/hover and signature help:** object/column/procedure/variable hover plus routine/builtin signature help.
5. **LS-4 Scripting and definition:** TypeScript scripting engine for `CREATE`, `ALTER`, templates, go-to-definition, and peek-definition.
6. **LS-5 Colorization and semantic polish:** semantic tokens, lexer-driven Monaco tokenization, document highlights, folding, code actions, adoption audit.

The service should be **feature-routed**, not cliff-switched. A setting controls the preferred engine, but the router can serve completions natively while diagnostics or definition still fall back to the STS v1 bridge until each native feature graduates.

Recommended setting name:

```jsonc
"mssql.queryStudio.languageService.engine": "sqlToolsService" | "nativeTypeScript"
```

Display name: **Query Studio language service engine**.  
Initial default: `sqlToolsService`.  
Later default candidate: `nativeTypeScript`, after the LS-5 audit.

---

## 1. Review of the draft and replacement decisions

The draft is a strong foundation. It correctly identifies the central architecture: a fully client-side TypeScript service, a metadata-provider seam, a parser/binder pipeline, and phased replacement of STS v1 language features. This replacement keeps those strengths but tightens the parts a coding agent would otherwise have to infer.

### 1.1 Keep from the draft

- **Per-feature routing:** correct and important. The new engine should not require completions, diagnostics, hover, and definition to all be complete before any native feature ships.
- **Metadata decoupling:** correct. The language engine should import only a narrow provider interface, not `CatalogSnapshot`, `MetadataService`, STS2 transport types, or VS Code APIs.
- **Layered parser strategy:** correct. A full vendor-grade T-SQL grammar is not required at first, but a simple `FROM`/`WHERE` scanner is not enough. The right middle path is a tolerant tooling parser that is precise around names, sources, scopes, and clause boundaries.
- **Diagnostics honesty:** correct. False positive schema squiggles are more damaging than missing squiggles. Diagnostics need a suppression ladder and telemetry counters.
- **Scripting as a separate phase:** correct. Definition and peek require object scripting and richer metadata than completions/hover need.
- **Colorization kept separable:** correct. TextMate/Monarch grammar replacement is useful, but it is not the primary reason to remove STS v1.

### 1.2 Changes made in this replacement

| Area | Replacement decision |
|---|---|
| Setting name | Use `mssql.queryStudio.languageService.engine`, not `Use new LSP`. Values are explicit: `sqlToolsService` and `nativeTypeScript`. |
| Phase breakdown | Split diagnostics and hover into separate phases so a coding agent can run feature-by-feature. |
| STS2 boundary | Add an explicit STS2/MetadataService integration section. Native language features do not call STS2 directly in hot paths. MetadataService owns STS2 calls and exposes pinned snapshots. |
| `CREATE OR ALTER` gating | Corrected: `CREATE OR ALTER` is a SQL Server 2016 SP1-era programmability-object feature, not simply a database compatibility-level 130 feature. Gate by server/engine capability, not just compat level. |
| Bridge implementation | Call out that `vscode.execute*Provider` aggregates all registered providers. That may be acceptable for user parity, but if exact STS v1 parity is required, use a direct adapter to the existing STS v1 language client instead. |
| Database context | Add an explicit per-statement database-context model for `USE`, the Query Studio database dropdown, and scripts that switch databases mid-file. |
| Metadata readiness | Define concrete readiness rules and a no-network-in-keystroke invariant. |
| Scripting fidelity | Add scripting fidelity levels and more metadata needs, including identity, computed columns, constraints, indexes, descriptions, and metadata visibility gaps. |
| Testing | Add agent-ready acceptance gates, fixture requirements, golden tests, and regression capture. |
| Delivery | Add implementation file map, module boundaries, task lists, and exit criteria for each phase. |

### 1.3 Problems requiring extra attention

1. **Parser scope creep:** the sketch parser must remain feature-driven. Add grammar only when a feature or corpus failure needs it.
2. **False diagnostics:** diagnostics must never outpace parser/binder certainty. Unknown sources, dynamic SQL, lite metadata, cross-db references, and incomplete hydration should suppress schema diagnostics.
3. **Database context drift:** Query Studio has a selected database and scripts can contain `USE`. Binding must use the correct context for each statement or suppress.
4. **STS v1 bridge side effects:** shadow STS v1 connections can affect URI-keyed state, status UI, or diagnostics. Isolate and tear down aggressively.
5. **Completion latency:** native completions must never await metadata hydration on the keystroke path. They should use the current pinned snapshot and degrade honestly.
6. **Scripting fidelity:** a generated `CREATE TABLE` that looks authoritative but omits important attributes can mislead users. Emit fidelity notes until metadata coverage is complete.
7. **Telemetry privacy:** language-service events must not emit document text or user-written identifiers. Counts, kinds, durations, feature names, readiness states, and stable non-reversible IDs are the safe default.
8. **Monaco/VS Code coordinate mismatches:** normalize UTF-16 offsets, CRLF, zero-based line/column, and token spans once in shared utilities.

---

## 2. Goals, non-goals, and success criteria

### 2.1 Goals

| ID | Goal |
|---|---|
| G1 | Provide native TypeScript implementations for Query Studio non-AI completions, hover/tooltips, signature help, diagnostics, definition/peek, folding, document symbols, document highlights, semantic tokens, and later colorization. |
| G2 | Use MetadataService as the default metadata source, with all schema truth flowing through a small provider interface. |
| G3 | Use STS2-backed endpoints through MetadataService and the existing SQL Data Plane, not through ad hoc language-service queries. |
| G4 | Eliminate the Query Studio dependency on STS v1 language features once native parity is proven. |
| G5 | Make completions better than the old engine, not just equal: FK-aware joins, source/alias-aware columns, `SELECT *` expansion, INSERT column scaffolds, EXEC parameter help, smarter ranking. |
| G6 | Make diagnostics safe: low false-positive rate, explicit suppression, and warning-first severity for schema diagnostics. |
| G7 | Provide a TypeScript scripting engine that powers go-to-definition/peek-definition and can later support Script-as operations. |
| G8 | Keep the core language engine testable and isomorphic: no `vscode`, no Node-only APIs, no STS2 transport imports inside `src/sqlLanguage/core/**`. |
| G9 | Preserve a working old-engine path through a bridge until native features graduate. |
| G10 | Produce evidence for default flip: tests, perf benchmarks, suppression metrics, feature capture, and head-to-head bridge/native latency. |

### 2.2 Non-goals for the first native rollout

- Full SQL Server parser parity with ScriptDOM.
- Full T-SQL syntax diagnostics.
- Formatting or pretty-printing.
- Cross-object rename/refactor.
- Exact SSMS/SMO scripting fidelity for every object attribute on day one.
- Dynamic SQL semantic binding, except later optional analysis of obvious `sp_executesql N'...'` string literals.
- Linked-server binding or broad cross-database hydration, unless MetadataService already supports it.
- Replacing the classic editor by default.
- AI completions. Those already use their own Query Studio/STS2 contract work and should remain separate from deterministic completions.

### 2.3 Success criteria

The native language service is ready to become the Query Studio default only when all of the following are true:

- Native completions cover the acceptance matrix in Appendix A.
- Diagnostics pass the honesty suite with zero known false positives in representative scripts.
- Hover and signature help are at least parity for objects, columns, variables, procedures, functions, and builtins.
- Definition/peek can resolve local script symbols, catalog modules, tables, columns, temp tables, CTEs, aliases, and variables with correct anchors where supported.
- Completion p95 host latency is under 40 ms on the benchmark corpus with a warm metadata snapshot.
- Native mode creates no shadow STS v1 connection for documents whose routed features are fully native.
- Telemetry privacy review is complete.
- The feature router has a documented fallback/circuit-break path.

---

## 3. System placement

```text
Query Studio webview, Monaco editor
  completion / hover / signature / diagnostics / definition / semantic tokens / folding providers
        |
        | Query Studio language-feature RPC contracts
        v
QueryStudioController or equivalent host controller
        |
        v
LanguageFeatureRouter
  per-feature route: nativeTypeScript preferred, sqlToolsService fallback while needed
        |
        +-------------------------------+
        |                               |
        v                               v
Native TSqlLanguageService              STS v1 bridge engine
src/sqlLanguage/**                      shadow v1 connection, provider command bridge,
lexer -> segmenter -> sketch parser     old diagnostics feed where needed
-> overlay -> binder -> feature modules
        |
        v
ISqlLanguageMetadataProvider
        |
        v
CatalogLanguageMetadataProvider
adapter over MetadataService pinned snapshots
        |
        v
MetadataService
hydrated from STS2-backed SQL Data Plane endpoints
        |
        v
STS2 contract and SQL connection/session layer

Definition/peek path:
Binder resolution -> SqlScriptingService -> MetadataService lazy detail reads -> virtual/peek document
```

### 3.1 Core rule

The native engine should not know whether metadata came from STS2, a fixture, a cache file, a live connection, or a future provider. It sees only `ISqlLanguageMetadataProvider`.

### 3.2 Hot-path rule

Completions, hover, signature help, semantic tokens, and diagnostics must not perform network I/O on their interactive path. They use a pinned snapshot. If data is missing, they degrade or suppress and may ask the host to schedule background hydration.

### 3.3 STS2 rule

STS2 integration belongs in MetadataService and SQL Data Plane adapters. New STS2 endpoint work required by this plan should be added as MetadataService hydration or lazy detail reads, not as feature-specific language-service calls.

---

## 4. STS2 and MetadataService integration contract

The prompt asks that this work build on the new metadata service and use STS2 endpoints. The clean design is:

- The **language engine** depends on an interface.
- The **catalog provider adapter** maps that interface to `CatalogSnapshot` and MetadataService detail APIs.
- **MetadataService** owns STS2 calls and caching.
- **STS2 endpoints** provide catalog sections, definitions, and detail reads.

### 4.1 Logical STS2-backed metadata capabilities

Use the actual repository endpoint and contract names where they already exist. The following table describes the logical capabilities the coding agent should map to existing or new STS2 contract methods.

| Logical capability | Used by | Minimum data |
|---|---|---|
| Environment/bootstrap | all features | server version, engine edition, database name, default schema, collation/case-sensitivity, compatibility level, feature flags. |
| Schemas | completions, binding | schema names. |
| Objects and synonyms | completions, binding, hover, scripting | object id/key, schema, name, type/kind, database, synonym target if available, modify/create metadata where already exposed. |
| Columns | completions, binding, hover, scripting | object key, column id, name, ordinal, type display, nullability, identity/computed flags where available, PK flag, collation when non-default. |
| Primary keys and unique constraints | join ranking, scripting, diagnostics | key columns, order, constraint name. |
| Foreign keys | join suggestions, hover, scripting | FK name, parent/ref object, ordered column pairs, disabled/trusted flags if available. |
| Routine parameters | EXEC completions, signature help, hover, scripting | routine key, parameter name, ordinal, type display, output flag, default-known flag if available. |
| Module definitions | hover, definition, scripting | definition text, encrypted/permission-denied/null reason if known. |
| Database list | `USE` completions, database context | database names and online/access state if available. |
| Index details | scripting, later ranking | index name, type, uniqueness, filtered predicate, key columns, sort order, include columns. |
| Constraint details | scripting, hover | default/check definitions, names, column binding, trusted/disabled state. |
| Descriptions/extended properties | hover, completion docs | `MS_Description` and any chosen doc properties. |
| Computed column details | scripting, hover | definition, persisted flag. |
| Identity details | scripting | seed, increment, not-for-replication. |

### 4.2 MetadataService section model

MetadataService should expose readiness per section. The language provider must map these into language-service readiness:

```ts
export type SectionState =
  | "unknown"
  | "loading"
  | "ready"
  | "partial"
  | "failed"
  | "stale";

export interface LanguageReadiness {
  objects: SectionState;
  columns: SectionState;
  parameters: SectionState;
  foreignKeys: SectionState;
  definitions: SectionState | "lazy";
  details: SectionState | "lazy";
  mode: "full" | "lite" | "partial" | "offline";
}
```

Feature behavior by readiness:

| Feature | Minimum readiness | Behavior below readiness |
|---|---|---|
| Keyword/snippet completions | none | Always available. |
| Object completions | `objects=ready|partial` | Return keywords/snippets, local script symbols, and system catalog only. |
| Column completions | `columns=ready` for touched sources | Return only columns from typed sources. Suppress or mark incomplete otherwise. |
| Join suggestions | `foreignKeys=ready` plus columns for participating tables | Fall back to name/type heuristic only if columns are ready. Otherwise no join predicate suggestion. |
| Hover | matching section ready | Show only known facts. Do not claim absent descriptions or missing columns. |
| Binder diagnostics | objects/columns ready for target sources | Suppress schema diagnostics. |
| Signature help | `parameters=ready` for user routines, builtin data available | Use builtins; suppress user routine parameter claims if missing. |
| Scripting | lazy details available | Emit fidelity notes for missing detail sections. |

### 4.3 Pinned snapshot invariant

A language request must see one consistent metadata generation:

```ts
const pinned = provider.pin(overlay, databaseContext);
// all resolve/search/list calls for this request use pinned
```

Do not read `handle.current()` multiple times inside one request. Mixed generations cause ghost columns, false diagnostics, and completion jitter.

### 4.4 Database context model

Binding needs a database context for every statement.

Inputs:

1. Query Studio selected database at document open/connect time.
2. Query Studio `signalDatabaseChanged` events.
3. `USE databaseName` statements in the script, in document order.
4. Three-part names in code.
5. MetadataService hydration coverage.

Required model:

```ts
export interface StatementDatabaseContext {
  initialDatabase?: string;
  effectiveDatabase?: string;
  changedByUseAt?: TextSpan;
  isHydrated: boolean;
  reasonIfUnhydrated?: "unknownDatabase" | "notHydrated" | "offline" | "permission";
}
```

Rules:

- For completions at `USE |`, use `provider.databases()` if available.
- For statements after `USE OtherDb`, resolve against `OtherDb` only if MetadataService has a hydrated or pin-able catalog for that database.
- If the database context is not hydrated, suppress binder diagnostics for catalog names in that statement.
- Do not silently bind against the Query Studio dropdown database after a `USE` changed the script context.
- If a script switches databases repeatedly, maintain a lightweight context map from statement index to effective database.

### 4.5 No network I/O on keystrokes

The host may schedule metadata hydration in response to missing data, but the feature response itself should return from the current snapshot. Example:

```ts
if (!columnsReadyFor(source)) {
  host.scheduleHydration({ kind: "columns", object: source.ref, priority: "interactiveFollowup" });
  return incompleteColumnCompletionResult();
}
```

### 4.6 Metadata visibility and null definitions

Module definitions can be missing for benign reasons: encryption, permission/metadata visibility, or unsupported object type. The scripting and definition flows must distinguish known reasons where MetadataService can provide them, and otherwise emit a neutral note such as `Definition text is not available from the current connection.`

---

## 5. Parser research and decision

### 5.1 Current parser landscape, checked July 2026

There is no off-the-shelf TypeScript parser that simultaneously satisfies these requirements:

- Production-grade T-SQL dialect coverage.
- Error-tolerant mid-edit parsing for IDE use.
- Incremental or statement-scoped performance suitable for keystrokes.
- Name/scope/binder integration.
- Small enough and maintainable enough for the VS Code extension bundle.

| Option | Assessment |
|---|---|
| SqlScriptDOM | Excellent authoritative T-SQL parser and AST library, now open source under MIT, but .NET-based. Use as a dev/test oracle, not as the extension runtime parser. |
| Microsoft.SqlServer.Management.SqlParser | Provides parsing and binding and exposes metadata-provider architecture, but the library itself is not open source. It is a useful architectural precedent, not reusable code. |
| grammars-v4 TSql plus antlr4ng | Credible fallback. antlr4ng is a TypeScript runtime for ANTLR4/ANTLR-ng grammars. The generated grammar is large, not incremental by itself, and grammar bugs become ours. Use as an oracle/prototype or escape hatch. |
| antlr4-c3 | Useful code-completion candidate engine for ANTLR parsers. It still requires a grammar and a symbol table/binder. Useful if the ANTLR escape hatch is chosen. |
| dt-sql-parser | Mature TypeScript SQL parser toolkit with validation/completion/table-column collection for several dialects, but its listed dialects do not include T-SQL. Study patterns, do not adopt directly. |
| node-sql-parser | Supports a TransactSQL mode in current packages, but it is AST-oriented and not designed as an error-tolerant, binder-ready, mid-edit language service. Useful only for experiments. |
| tree-sitter generic SQL | Excellent runtime properties, but available SQL grammars are generic/permissive or non-T-SQL-focused. |
| tree-sitter-tsql | Promising shape, but still early; its README calls out lexer quirks such as configuration functions needing all caps. Not a production basis today. |

### 5.2 Answer to the `FROM`/`WHERE` heuristic question

A simple scanner can be useful for prototypes and fallbacks, but it is not enough as the main design. It fails on normal authoring cases:

```sql
-- Alias is to the right of the caret but must still be known.
SELECT o.| FROM Sales.Orders AS o;

-- CTE name and CTE columns are statement-local.
WITH recent(OrderID, CustomerID) AS (...)
SELECT r.| FROM recent r;

-- Scope differs inside subqueries.
SELECT *
FROM Sales.Orders o
WHERE EXISTS (SELECT 1 FROM Sales.OrderLines l WHERE l.OrderID = o.|);

-- UPDATE alias form is T-SQL-specific.
UPDATE o
SET o.| = 1
FROM Sales.Orders o
JOIN Sales.Customers c ON ...;
```

The replacement design uses a **layered sketch parser**: full lexer, statement segmentation, tolerant clause/name parsing, and a real binder. Expressions can remain balanced-token spans until a feature needs deeper understanding.

### 5.3 Decision

Build a purpose-built TypeScript tooling parser and binder.

Use external parsers as development oracles:

- ScriptDOM oracle for statement kind, spans, parse errors, and name extraction comparison.
- ANTLR grammar oracle for hard corpus cases and escape-hatch prototyping.
- Corpus-driven deepening: add grammar support when a real script or feature test demonstrates the need.

Do not ship ANTLR or ScriptDOM in the extension for the initial native language service.

---

## 6. Native language-service architecture

### 6.1 Package layout

```text
src/sqlLanguage/
  api.ts                         public service interfaces used by Query Studio host
  core/
    text/
      textSnapshot.ts            immutable document text view, offsets, line map
      position.ts                Monaco/VS Code position conversion helpers
    lexer.ts                     full-fidelity T-SQL lexer
    keywords.ts                  keyword classification helpers
    segmenter.ts                 GO batch and statement segmenter
    sketch/
      index.ts                   statement sketch parser entry
      select.ts                  SELECT/query expression skeleton
      dml.ts                     INSERT/UPDATE/DELETE/MERGE skeletons
      ddl.ts                     CREATE/ALTER/DROP headers and CREATE TABLE skeleton
      procedural.ts              DECLARE/IF/WHILE/BEGIN/TRY/EXEC skeletons
      expressionScan.ts          balanced expression scanner and dotted-name extractor
      recovery.ts                anchor sets and tolerant parse helpers
    overlay.ts                   script-local catalog overlay builder
    binder.ts                    scopes, name resolution, occurrences
    context.ts                   caret context classifier
    fuzzy.ts                     deterministic fuzzy/prefix matching
    quote.ts                     identifier quoting and casing helpers
    databaseContext.ts           per-statement database context map
  features/
    completion.ts
    hover.ts
    signatureHelp.ts
    diagnostics.ts
    semanticTokens.ts
    folding.ts
    documentSymbols.ts
    highlights.ts
    codeActions.ts
  provider/
    types.ts                     ISqlLanguageMetadataProvider and pinned view types
    catalogProvider.ts           MetadataService/CatalogSnapshot adapter
    fixtureProvider.ts           tests
    nullProvider.ts              tests and offline behavior
    overlayView.ts               overlay-on-catalog implementation
  host/
    router.ts                    LanguageFeatureRouter
    nativeEngine.ts              service wrapper around core/features
    bridgeEngine.ts              STS v1 bridge wrapper
    scheduler.ts                 idle/background slicing and cancellation
    telemetry.ts                 spans/events, privacy-safe attributes
  data/
    keywords.generated.ts
    builtinFunctions.json
    snippets.json
    statementKeywords.json
  testSupport/
    fourslash.ts
    fixtureCatalog.ts
    assertions.ts

src/sqlScripting/
  api.ts
  service.ts
  emitters/
    moduleEmitter.ts
    tableEmitter.ts
    dmlTemplateEmitter.ts
    alterRewrite.ts
  anchors.ts
  fidelity.ts
  quote.ts                       shared or re-exported from sqlLanguage/core/quote.ts
```

### 6.2 Import boundaries

Enforce with ESLint or an existing repository boundary mechanism:

- `src/sqlLanguage/core/**` may import only core utilities, provider type definitions, and data assets.
- `src/sqlLanguage/features/**` may import core and provider types, but not VS Code, MetadataService concrete classes, STS2 DTOs, or Query Studio controller types.
- `src/sqlLanguage/provider/catalogProvider.ts` may import MetadataService and `CatalogSnapshot`.
- `src/sqlLanguage/host/**` may import VS Code APIs and Query Studio host/controller types.
- `src/sqlScripting/**` may import MetadataService detail APIs through a scripting-specific adapter, but core emitters should remain pure once supplied a snapshot/detail model.

### 6.3 Document analysis model

For each Query Studio document version:

```text
DocumentAnalysis
  L0 TokenStream
  L1 BatchMap and StatementMap
  L2 StatementSketches
  L2.5 ScriptOverlay and DatabaseContextMap
  L3 BoundStatements and OccurrenceIndex
  L4 Feature caches
```

Cache keys:

```text
lexer cache: document version and changed line states
segment cache: token stream version
sketch cache: statement span + statement token hash
binder cache: statement hash + provider generation + overlay hash + database context key
completion cache: statement hash + caret token context + provider generation + overlay hash
```

### 6.4 Scheduling model

- Interactive requests analyze the caret statement immediately.
- Whole-document diagnostics, semantic tokens, symbols, and folding run on a debounce and in time-sliced chunks.
- Every background job carries a document version. Stale jobs cancel silently.
- The first implementation can run in the extension host. The core must remain worker-ready.

---

## 7. Lexer, segmenter, sketch parser, overlay, binder

### 7.1 L0 lexer

Implement one full-fidelity T-SQL lexer and make any existing `lexerLite`/DDL sniffers use it or share its token definitions.

Token categories:

- Whitespace and line endings.
- Line comments and nested block comments.
- Identifiers, bracketed identifiers, double-quoted identifiers.
- Keyword-capable identifiers with `keywordId` metadata, not hard keyword tokens.
- String literals: `'...'`, escaped quotes, `N'...'`.
- Numeric literals: integer, decimal, scientific, money where needed, binary `0x...`.
- Variables: `@local`, `@@system`.
- Temp names: `#local`, `##global`.
- Operators and punctuation.
- `GO` batch separators recognized only at line level under the same rules execution uses.
- SQLCMD directive lines beginning with `:` after whitespace, treated as opaque.

Important rules:

- Do not classify a token as an unrecoverable keyword in the lexer. T-SQL permits many keyword-looking identifiers.
- Preserve token spans exactly for replacement edits, highlights, diagnostics, anchors, and code actions.
- Track line-start states for incremental lexing: block-comment depth, string state if needed, SQLCMD directive state.

### 7.2 L1 batch and statement segmenter

Batch segmentation must match Query Studio execution splitting for `GO`, including `GO n` counts and invalid trailing text diagnostics.

Statement segmentation handles:

- Top-level semicolons.
- Statement-start keywords at depth 0.
- `BEGIN`/`END` tracking for procedural blocks.
- `TRY`/`CATCH` blocks.
- `CREATE|ALTER PROC|PROCEDURE|FUNCTION|VIEW|TRIGGER ... AS` consuming the rest of the batch as the module body.
- Nested segmentation inside module bodies for language features within stored procedures/views/functions.
- `WITH` disambiguation as CTE vs table hint or option based on context.

### 7.3 L2 statement sketch parser

The sketch parser is tolerant and total: it must return a sketch even for half-written SQL.

Minimum statement families:

- `SELECT` query expressions: `WITH`, `SELECT`, `INTO`, `FROM`, joins, `APPLY`, `WHERE`, `GROUP BY`, `HAVING`, `WINDOW`, `ORDER BY`, `OFFSET/FETCH`, `OPTION`, `FOR`.
- Source grammar: table refs, schema-qualified refs, aliases, table hints as balanced opaque spans, derived tables, CTEs, TVF calls, `OPENJSON`, `OPENROWSET`, `VALUES` rowsets.
- `INSERT`: target, optional column list, `VALUES`, `SELECT`, `EXEC` source.
- `UPDATE`: target, alias-target form, `SET`, optional `FROM`, `OUTPUT`.
- `DELETE`: target, `FROM`/`USING` style T-SQL forms, `OUTPUT`.
- `MERGE`: target, source, `ON`, `WHEN` skeleton.
- `DECLARE`: scalar variables, cursors, table variables.
- `EXEC|EXECUTE`: procedure name, named args, positional args, `sp_executesql` recognition.
- Procedural blocks: `IF`, `ELSE`, `WHILE`, `BEGIN/END`, `TRY/CATCH`, `RETURN`, `THROW`, `RAISERROR`, labels.
- DDL headers: `CREATE`, `ALTER`, `DROP` for common object types.
- `CREATE TABLE` column and constraint skeletons.
- `USE` statements for database context.

Expression parsing v1:

- Track balanced parentheses/brackets.
- Extract dotted-name chains and function-call heads.
- Extract aliases in select-list items.
- Track `CASE ... END` for folding and recovery.
- Avoid full operator precedence until a feature requires it.

### 7.4 L2.5 script overlay

The overlay supplies objects created in the script before execution.

Overlay entries:

- `CREATE TABLE #t (...)` and `CREATE TABLE ##t (...)`.
- `SELECT ... INTO #t` with unknown types but known column names.
- `DECLARE @t TABLE (...)`.
- CTE definitions and inferred/declared column names.
- Script-local DDL for real objects, such as `CREATE TABLE dbo.NewTable` then later `SELECT * FROM dbo.NewTable`.
- `ALTER TABLE ... ADD column` deltas where cheap to parse.
- `DROP TABLE #t` ending a temp object from that point forward.

Scope rules:

- CTEs are statement-scoped.
- Table variables are batch-scoped.
- Local temp tables persist across `GO` in the same connection/session, but in the language service they should be modeled in document order unless the host later adds session-aware temp metadata.
- Real object script-local DDL overlays should be clearly marked as speculative/unexecuted.

### 7.5 L3 binder

Binder responsibilities:

- Build scope chains for batch variables, CTEs, query sources, subqueries, derived tables, and correlated references.
- Resolve source aliases before object names.
- Resolve objects through the pinned provider and overlay.
- Resolve qualified columns against the correct source.
- Resolve unqualified columns across visible sources and report ambiguous only when all sources are fully known.
- Resolve `inserted`/`deleted` pseudo-sources in DML/trigger contexts.
- Resolve variables, parameters, table variables, CTE columns, and temp tables.
- Produce occurrence groups for highlights, semantic tokens, and later local rename.
- Produce suppression reasons when binding cannot be honest.

Suppression reasons:

```ts
export type SuppressionReason =
  | "providerNotReady"
  | "columnsNotReady"
  | "databaseNotHydrated"
  | "crossDatabaseUnhydrated"
  | "linkedServer"
  | "opaqueSource"
  | "dynamicSql"
  | "unknownSketchRegion"
  | "unknownOverlayType"
  | "metadataPermission"
  | "quotedIdentifierAmbiguous"
  | "unsupportedSyntax";
```

---

## 8. Metadata provider interface

The engine sees this interface, not MetadataService directly.

```ts
export interface ISqlLanguageMetadataProvider {
  readonly generation: number;
  readonly onDidChange: Event<void>;

  env(): SqlLanguageEnvironment;
  readiness(database?: string): LanguageReadiness;

  pin(options?: PinOptions): IPinnedMetadataView;

  databases(): readonly LangDatabase[] | undefined;

  requestHydration?(request: HydrationRequest): void;
}

export interface PinOptions {
  overlay?: LangOverlay;
  databaseContext?: StatementDatabaseContext;
  requestedSections?: readonly MetadataSection[];
}

export interface SqlLanguageEnvironment {
  currentDatabase?: string;
  defaultSchema: string;
  caseSensitive: boolean;
  engineEdition?: string;
  serverVersion?: string;
  compatibilityLevel?: number;
  capabilities: SqlLanguageServerCapabilities;
}

export interface SqlLanguageServerCapabilities {
  createOrAlterProgrammability: boolean;
  dropIfExists: boolean;
  stringAgg?: boolean;
  graphTables?: boolean;
  ledger?: boolean;
  fabricWarehouse?: boolean;
}

export interface IPinnedMetadataView {
  readonly generation: number;
  readonly env: SqlLanguageEnvironment;
  readonly readiness: LanguageReadiness;

  resolveObject(parts: readonly NamePart[], context?: ResolveContext): LangResolution;
  getObject(ref: LangObjectRef): LangObjectInfo | undefined;
  getColumns(ref: LangObjectRef): readonly LangColumn[] | undefined;
  getParameters(ref: LangObjectRef): readonly LangParam[] | undefined;

  fkFrom(ref: LangObjectRef): readonly LangFkEdge[];
  fkTo(ref: LangObjectRef): readonly LangFkEdge[];

  searchObjects(query: ObjectSearchQuery): readonly LangObjectRef[];
  listSchemas(database?: string): readonly LangSchema[];
  systemObjects(query: SystemObjectQuery): readonly LangObjectRef[];

  getDescription?(ref: LangSymbolRef): string | undefined;
  getDefinition?(ref: LangObjectRef): Promise<DefinitionResult>;
}
```

Important type rules:

- `LangObjectRef` must include database where known.
- `LangObjectRef` should not expose MetadataService implementation classes.
- Comparisons must use collation-aware helpers from the provider environment.
- `getDefinition` is the only async member, and feature modules should call it only through hover/definition resolve paths, not normal completion generation.

---

## 9. Feature router, setting, and old-engine bridge

### 9.1 Setting

```jsonc
{
  "mssql.queryStudio.languageService.engine": "sqlToolsService"
}
```

Allowed values:

- `sqlToolsService`: prefer the existing STS v1 language-service path through the bridge.
- `nativeTypeScript`: prefer the native TypeScript engine for any feature whose native capability is enabled.

Do not expose per-feature user settings initially. Per-feature maturity belongs to the router and rollout table. Add only a few user escape hatches:

```jsonc
"mssql.sqlLanguage.diagnostics.enabled": true,
"mssql.sqlLanguage.keywordCasing": "upper",
"mssql.sqlLanguage.completions.snippets": true,
"mssql.sqlLanguage.definition.mode": "peek"
```

### 9.2 Native capability table

```ts
export interface NativeCapabilityTable {
  completion: FeatureMaturity;
  diagnostics: FeatureMaturity;
  hover: FeatureMaturity;
  signatureHelp: FeatureMaturity;
  definition: FeatureMaturity;
  semanticTokens: FeatureMaturity;
  folding: FeatureMaturity;
  documentSymbols: FeatureMaturity;
  highlights: FeatureMaturity;
}

export type FeatureMaturity =
  | "off"
  | "experimental"
  | "preview"
  | "defaultCandidate"
  | "default";
```

Router rule:

- If preferred engine is `nativeTypeScript` and feature maturity is at least the configured rollout threshold, call native.
- If native throws or times out, circuit-break that feature for the document/session and fall back to bridge if available.
- If preferred engine is `sqlToolsService`, call bridge for old-backed features, but native can still serve features the old engine does not provide if product wants that, such as improved folding or document symbols.

### 9.3 Bridge engine

Bridge options:

1. **Provider-command aggregation:** use VS Code commands such as `vscode.executeCompletionItemProvider`, `vscode.executeHoverProvider`, `vscode.executeSignatureHelpProvider`, and `vscode.executeDefinitionProvider` against the backing `TextDocument` URI.
2. **Direct STS v1 client adapter:** use the existing MSSQL extension language client directly if the repo exposes a stable internal API.

Recommendation:

- Start with provider-command aggregation for speed, but record that it may aggregate non-STS providers. If exact old-engine parity is required, move to a direct STS v1 adapter.

Bridge tasks:

- Create a shadow STS v1 connection for Query Studio documents only when a routed bridge feature is needed.
- Retarget the shadow connection when Query Studio database context changes.
- Tear down the shadow connection on document/model dispose.
- Forward diagnostics via `vscode.languages.onDidChangeDiagnostics` for the backing URI.
- Ensure native diagnostics and bridge diagnostics do not both publish markers for the same feature at the same time.
- Telemetry attribute `engine=sqlToolsServiceBridge` vs `engine=nativeTypeScript` on every feature span.

Bridge risks:

- Shadow connection may create status/OE/UI side effects. If found, add a legacy language-only connection path under a small sanctioned seam.
- Definition through old bridge may create temp files or old virtual docs. Accept as old behavior until LS-4 replaces it.
- Native mode should not create the shadow v1 connection once all routed features are native.

---

## 10. Native completions design

### 10.1 Completion pipeline

```text
caret position
  -> document analysis for caret statement
  -> database context at statement
  -> script overlay up to statement
  -> pinned provider view
  -> binder scope at offset
  -> completion context classification
  -> candidate generation
  -> ranking
  -> item shaping
  -> optional lazy resolve for documentation
```

### 10.2 Completion contexts

| Context | Native candidates |
|---|---|
| Statement start | DML/DDL/procedural keywords, snippets. |
| After `FROM`, `JOIN`, `APPLY`, `UPDATE`, `INTO` | Tables, views, TVFs, synonyms, CTEs, temp tables, table variables, schemas, derived-table snippet. |
| After `schema.` | Objects in schema, filtered by context. |
| After `database.schema.` | Objects if database is hydrated, otherwise suppressed/incomplete. |
| After `alias.` or source ref | Columns of that source, `*`, star expansion action. |
| SELECT list | In-scope columns, source-qualified columns, variables, builtins, scalar UDFs, snippets. |
| WHERE/ON/HAVING expression | Columns, variables, functions, operators/snippets. |
| After `ON` in join | FK join predicate suggestions first, then normal expression suggestions. |
| After `JOIN` table name position | Tables ranked by FK adjacency to sources already in the FROM scope. |
| INSERT column list | Target columns, all-column-list insert, skip identity/computed by default. |
| VALUES position | Placeholder snippets aligned to known target column list. |
| UPDATE SET left side | Target columns only. |
| EXEC procedure position | Procedures and system procedures. |
| EXEC args | Named parameters not already supplied, with `@name = ` insert text. |
| DECLARE type position | System/user data types and `TABLE`. |
| USE | Databases. |
| GROUP BY | Non-aggregate SELECT-list expressions and columns. |
| ORDER BY | SELECT-list aliases, ordinals, columns. |
| Inside comments/strings/opaque spans | No completion, except optional SQLCMD/string-literal future features. |

### 10.3 Join suggestions

Join suggestions are a first native differentiator and should ship with LS-1.

Given:

```sql
SELECT *
FROM Sales.Orders o
JOIN Sales.Customers c ON |
```

If a foreign key exists:

```sql
o.CustomerID = c.CustomerID
```

For composite FK:

```sql
a.Key1 = b.Key1 AND a.Key2 = b.Key2
```

Candidate ranking:

1. Exact FK edges between the new joined source and any prior source.
2. Reverse FK edges.
3. Unique/PK compatible edges if MetadataService has unique constraints.
4. Name and type compatible columns, clearly lower ranked and labeled as inferred.
5. General column/expression candidates.

### 10.4 Star expansion

Provide both:

- Completion item: `Expand columns` when caret is on or near `*` or `alias.*`.
- Code action: replace star with explicit column list.

Formatting rules:

- Single line if short.
- One column per line if over width threshold.
- Preserve alias qualifier if the user used `alias.*`.
- Do not include hidden columns unless a future setting requests them.
- If metadata is incomplete, do not offer expansion.

### 10.5 Ranking model

Rank score should be deterministic and explainable:

```text
context priority
+ prefix/fuzzy match score
+ locality boost
+ FK/relationship boost
+ current schema/default schema boost
+ MRU accept-history boost
- system object penalty unless prefix indicates system intent
- low confidence/inferred penalty
```

Tie-breakers:

1. Exact case-sensitive match when database collation is case-sensitive.
2. Shorter unqualified name.
3. Schema/default schema priority.
4. Alphabetical by display label.

### 10.6 Completion item shaping

- Use Monaco item kinds consistently: table/class, view/interface, column/field, proc/method, function/function, variable/variable, keyword/keyword, snippet/snippet.
- Insert bracketed identifiers only when required or when the original identifier was bracketed in nearby context.
- Commit character `.` only for sources/schemas/databases, not columns.
- Lazy-resolve documentation to avoid creating large Markdown for every item.
- Mark incomplete results when metadata readiness prevented full candidate generation.

### 10.7 Completion acceptance gate

Minimum LS-1 test matrix:

- 150+ fourslash completion cases.
- Every context in 10.2 covered.
- Case-sensitive collation fixture.
- Bracketed identifier fixture.
- CTE, temp table, table variable, derived table, subquery, update alias, insert, exec.
- FK join suggestions, including composite keys.
- No suggestions inside comments/strings.
- Warm snapshot p95 under 40 ms.

---

## 11. Diagnostics design

Diagnostics should ship after completions so the binder has already been exercised by a high-volume feature.

### 11.1 Diagnostic tiers

#### T1 lexical and structural diagnostics

These can be errors if confidence is high:

- Unterminated string literal.
- Unterminated bracketed identifier.
- Unterminated or malformed block comment.
- Unbalanced parentheses at statement end where recovery is certain.
- Invalid `GO` line, such as `GO abc` or trailing junk.
- Duplicate source alias in one FROM scope.
- Obvious malformed `DECLARE @x TABLE` column list where parser certainty is high.

#### T2 binder diagnostics

These start as warnings:

- Invalid object name, mapped to SQL Server error 208 style.
- Invalid column name, mapped to error 207 style.
- Ambiguous column name, mapped to error 209 style.
- Unknown named parameter on a resolved procedure/function.
- Fixed-arity builtin function argument errors for curated builtins only.

Do not emit user-procedure arg-count diagnostics until metadata includes default value information and variadic/system procedure rules are well modeled.

### 11.2 Suppression ladder

No binder diagnostic if any of the following is true:

- Provider object/column readiness is not sufficient for the referenced sources.
- Effective database is not hydrated.
- Cross-database or linked-server reference is not hydrated.
- Source is opaque: dynamic SQL, OPENROWSET, ambiguous TVF, unparsed derived table, unknown table-valued expression.
- Statement region intersects an unknown sketch span.
- Overlay has unknown-typed source that could plausibly provide the column.
- Metadata visibility might hide the object or definition.
- Case sensitivity is unknown.
- Parser recovery consumed tokens around the diagnostic range.

Every suppression increments `sqlLanguage.diag.suppressed` with the reason. The event must not include the identifier text.

### 11.3 Diagnostic delivery

- Debounce after text changes, target 300 ms.
- Slice whole-document passes into small work chunks.
- Cancel stale document versions.
- Publish diagnostics through Query Studio RPC to Monaco markers.
- Keep source string stable: `T-SQL (native)`.
- Include diagnostic codes like `mssql(207)`, `mssql(208)`, and `mssql(209)`.

### 11.4 Diagnostic acceptance gate

- Honesty suite has zero diagnostics for valid tricky scripts.
- False-positive bug list is empty or all known false positives are suppressed before preview.
- 100+ diagnostic fourslash cases.
- Metrics show suppression reasons by count in dogfood.
- No diagnostics while metadata generation is changing or columns are still hydrating.

---

## 12. Hover/tooltips and signature help

### 12.1 Hover behavior

Hover content should be useful but never overclaim.

Examples:

```text
table Sales.Orders
12 columns · PK(OrderID) · 2 foreign keys
```

```text
column o.CustomerID int NOT NULL
FK -> Sales.Customers(CustomerID)
```

```text
alias o = Sales.Orders
```

```text
variable @CustomerID int
Declared at line 12
```

```text
procedure Sales.GetOrders
@CustomerID int, @Since datetime2 = ..., @IncludeClosed bit = ...
```

Content sources:

- Object kind/name from provider.
- Type/nullability from columns/params.
- PK/FK badges from key/FK metadata.
- Descriptions from MetadataService H7/extended properties when available.
- Builtin summaries from curated data.
- Local declarations from parser/binder.

Hover must not fetch definition text by default. It may include a command link for peek definition if available.

### 12.2 Signature help

Triggers:

- `(` for function/routine calls.
- `,` inside argument lists.
- Space after `EXEC procName` if the sketch identifies a procedure call.
- `@` within EXEC argument context.

Sources:

- Routine parameters from provider.
- Builtin signatures from curated data.
- Active parameter by comma index or named argument.

### 12.3 Acceptance gate

- 80+ hover tests.
- 60+ signature tests.
- Builtin signature data spot-checks.
- Null/missing definitions do not break hover.
- Metadata descriptions show only when actually loaded.

---

## 13. Definition, peek, and scripting

Definition is different from completions/diagnostics/hover. It needs object scripting, virtual documents, anchors, and richer metadata. Build it as LS-4 after the core binder is stable.

### 13.1 Scripting service API

```ts
export interface SqlScriptingService {
  script(request: ScriptRequest): Promise<ScriptResult>;
  capabilities(target: ScriptTarget): readonly ScriptOperation[];
}

export interface ScriptRequest {
  target: ScriptTarget;
  operation: ScriptOperation;
  options?: ScriptOptions;
}

export type ScriptOperation =
  | "create"
  | "alter"
  | "createOrAlter"
  | "drop"
  | "dropAndCreate"
  | "selectTop"
  | "insert"
  | "update"
  | "delete"
  | "execute";

export interface ScriptResult {
  text: string;
  anchors: readonly ScriptAnchor[];
  fidelityNotes: readonly string[];
  source: "catalogDefinition" | "synthesized" | "template" | "localDocument";
  metadataGeneration: number;
}

export interface ScriptAnchor {
  symbol: LangSymbolRef;
  span: TextSpan;
  line: number;
  character: number;
}
```

### 13.2 Scripting fidelity levels

Use explicit fidelity levels. Do not pretend to be SSMS/SMO-complete until metadata proves it.

| Level | Name | Meaning |
|---|---|---|
| F0 | Template | Useful query template, not object reconstruction. Example: `SELECT TOP`, `INSERT`, `UPDATE`, `EXEC`. |
| F1 | Basic create | Columns, basic types, nullability, PK when known. |
| F2 | Standard create | Adds identity, computed columns, defaults, checks, unique constraints, FKs, indexes, descriptions where known. |
| F3 | Full create candidate | Adds advanced table features supported by current metadata. Requires round-trip tests. |

Every generated script should include header notes if fidelity is below F3 or if known features were omitted.

### 13.3 Emitters

#### ModuleEmitter

For views, stored procedures, functions, and triggers:

- Prefer catalog definition text.
- If operation is `alter`, rewrite leading `CREATE` to `ALTER` using token-level logic from the lexer.
- If operation is `createOrAlter`, use `CREATE OR ALTER` only when provider capabilities say it is supported and only for supported object kinds: views, stored procedures, functions, triggers.
- If definition is null because encrypted or permission-hidden, return an honest result with no fabricated body.

#### CreateTableEmitter

Generate table DDL from metadata:

- Schema-qualified table name.
- Columns in ordinal order.
- Type rendering: max length, precision, scale, `MAX`, Unicode length handling, datetime/time scale.
- Nullability.
- Identity seed/increment/not-for-replication when known.
- Computed column definitions and `PERSISTED` when known.
- Collation when non-default.
- Sparse/rowguid/timestamp/rowversion/masked/encrypted flags where metadata supports them.
- Default and check constraints.
- Primary key and unique constraints.
- Foreign keys after the table body.
- Indexes after constraints.
- Extended property/description comments or `sp_addextendedproperty`, depending on option.

#### DmlTemplateEmitter

Generate templates:

- `SELECT TOP (1000)` with explicit columns.
- `INSERT` with writable columns and placeholders.
- `UPDATE` with settable columns and PK-based WHERE if available.
- `DELETE` with PK-based WHERE if available.
- `EXEC` with parameters and output markers.

### 13.4 Definition flow

```text
caret -> binder resolution -> target kind -> definition provider
```

Routes:

| Target | Definition result |
|---|---|
| Local alias | In-document alias declaration span. |
| Local variable | In-document `DECLARE` span. |
| CTE | In-document CTE definition span. |
| Temp table created in script | In-document `CREATE TABLE` or `SELECT INTO` span. |
| Table column | Synthesized table CREATE anchored at column line. |
| Table | Synthesized table CREATE anchored at header. |
| View | Catalog definition anchored at select/header if available, otherwise synthesized metadata summary if product accepts. |
| Procedure/function/trigger | Catalog definition anchored at header or parameter span. |
| Parameter | Routine definition anchored at parameter span if definition available, else local declaration/metadata hover style. |
| Synonym | Definition of synonym plus optional target resolution if target hydrated. |

### 13.5 Peek/open delivery

Default mode: `peek`.

Implementation:

- `QsLspDefinition` returns either a real location, a virtual content result, or both.
- Query Studio webview opens a read-only Monaco model for peek content.
- VS Code host registers a `mssql-def:` `TextDocumentContentProvider` for open-to-side.
- Cache virtual docs by object key and metadata generation.
- Invalidate on MetadataService generation change.

### 13.6 Metadata additions for scripting

| Addition | Needed for |
|---|---|
| Identity seed/increment/not-for-replication | `CREATE TABLE` fidelity. |
| Computed column definition/persisted | `CREATE TABLE`, hover. |
| Default/check constraint definitions | `CREATE TABLE`. |
| Full indexes: key order, includes, filters, uniqueness, type | `CREATE TABLE`, later ranking. |
| Unique constraints | join ranking and scripting. |
| Descriptions/extended properties | hover and scripting. |
| Module definition unavailable reason | honest definition/peek. |
| Server feature flags | `CREATE OR ALTER`, `DROP IF EXISTS`, dialect-specific syntax. |

### 13.7 Acceptance gate

- Golden scripts for tables, views, procedures, functions, triggers.
- Column definition anchors tested.
- ALTER rewrite property tests over whitespace/comments/schema-qualified names.
- Encrypted/permission-hidden definition tests.
- Round-trip tests for F2 table scripting on fixture database, or documented exclusions.

---

## 14. Folding, symbols, highlights, semantic tokens, and colorization

These features are useful, but should not delay completions, diagnostics, hover, or definition.

### 14.1 Folding

Can ship early because it needs only lexer/segmenter/sketch:

- `GO` batches.
- Multi-line statements.
- `BEGIN/END`.
- `TRY/CATCH`.
- `CASE/END`.
- Parentheses groups over threshold.
- Block comments.
- `--#region` / `--#endregion`.

### 14.2 Document symbols

- Batches.
- `CREATE` objects.
- CTEs.
- Temp tables/table variables.
- Labels.
- Regions.

### 14.3 Highlights

Binder-powered occurrence highlights:

- Aliases.
- Variables.
- Parameters.
- CTE names.
- Column references that resolve to the same symbol.

### 14.4 Semantic tokens

Semantic token types:

```text
schema, table, view, tempTable, tableVariable, cte, alias,
column, variable, parameter, procedure, function, builtinFunction,
type, label, keyword, systemObject
```

Modifiers:

```text
declaration, readonly, primaryKey, foreignKey, unresolved, inferred, deprecated
```

### 14.5 Colorization options

| Option | Recommendation |
|---|---|
| Keep existing TextMate/Monarch | Safe initial state. Do this while core features are built. |
| Lexer-driven Monaco tokenizer | Good Query Studio improvement once L0 lexer is stable. Can be enabled in LS-5 or behind a preview flag. |
| Semantic tokens | Best long-term visual quality. Use binder output and ship after hover/diagnostics. |
| Regenerate TextMate grammar | Backlog only. It matters mainly when classic editor adopts native engine. |

Do not make colorization a dependency of LS-1 completions.

---

## 15. Data assets

### 15.1 Keywords

Generate `keywords.generated.ts` from a version-pinned source, preferably ScriptDOM token tables or a repository-approved Microsoft T-SQL keyword source. Store provenance in the generated file header.

Keyword entries should include:

```ts
export interface KeywordInfo {
  id: KeywordId;
  text: string;
  category: "statement" | "clause" | "type" | "function" | "operator" | "reserved" | "contextual";
  minServerVersion?: string;
  engineEditions?: readonly string[];
}
```

### 15.2 Builtin functions

`builtinFunctions.json` should include:

- Name.
- Category.
- Signatures.
- Parameter names/types/optional markers.
- Return type summary.
- One-line description.
- Documentation URL.
- Minimum version/engine notes if relevant.

Start with the most common builtins first, but tests should pin the count and important examples.

### 15.3 Snippets

`snippets.json` should support:

- Statement snippets: SELECT, INSERT, UPDATE, DELETE, MERGE, CTE, TRY/CATCH.
- Object snippets: CREATE PROC, CREATE VIEW, CREATE TABLE.
- Query assists: JOIN skeleton, EXISTS skeleton, GROUP BY skeleton.
- Setting `mssql.sqlLanguage.completions.snippets`.

### 15.4 System object catalog

Reuse `completionSystemObjectCatalog.ts` if it already exists. Expose it through `systemObjects()` on the provider so completion code does not special-case its storage.

---

## 16. Performance plan

### 16.1 Budgets

| Operation | Target |
|---|---|
| Full lex 10k lines | under 30 ms. |
| Incremental lex/segment typical edit | under 2 ms. |
| Sketch parse typical statement | p95 under 1 ms. |
| Bind warm statement | p95 under 2 ms. |
| Completion host latency | p50 under 15 ms, p95 under 40 ms. |
| Hover/signature | under 20 ms without lazy definition. |
| Diagnostics 2k-line doc | under 80 ms total CPU, sliced under 8 ms per chunk. |
| Semantic tokens 2k lines | full under 60 ms, delta under 10 ms. |
| Typical per-document language cache | under 20 MB, bounded with LRU. |

### 16.2 Mechanisms

- Token store should avoid object-per-token in hot paths.
- Hash statements by token span and token kinds/text where needed.
- Bind only the caret statement for interactive features.
- Pin metadata once per feature request.
- Use prefix indexes from MetadataService/CatalogSnapshot for object search.
- Cache columns by `LangObjectRef` within the pinned view.
- Limit candidate counts before documentation shaping.
- Lazy-resolve expensive documentation.

### 16.3 Benchmarking

Add `test/sqlLanguage/sqlLanguage.bench.ts` or equivalent.

Benchmarks:

- Lexer full/incremental.
- Segmenter.
- Sketch parser on representative statement corpus.
- Binder on typical joins/subqueries.
- Completion contexts with fixture provider.
- Completion contexts with catalog provider against a test snapshot.
- Diagnostics pass.
- Scripting emitter on fixture tables.

---

## 17. Testing strategy

### 17.1 Fourslash-style harness

Use fixtures with markers:

```sql
SELECT o./*caret*/
FROM Sales.Orders AS o;
```

Expectations:

```ts
expect.completions.includes("OrderID");
expect.completions.excludes("Customers");
expect.completions.top(0).label("OrderID");
expect.diagnostics.none();
expect.hover.contains("Sales.Orders");
expect.definition.anchor("column:Sales.Orders.OrderID");
```

### 17.2 Corpus tests

Sources:

- Existing repository SQL test scripts.
- Query Studio feature scripts.
- WideWorldImporters-like fixture scripts.
- Generated edge-case scripts.
- User-style authoring snippets: incomplete queries, half-written joins, unfinished strings.

### 17.3 Parser oracle tests

Dev/CI-only:

- ScriptDOM parser comparison for statement spans and obvious names.
- ANTLR grammar comparison for selected difficult files.

Do not require perfect agreement. Track metrics and ratchet.

### 17.4 Honesty suite

Scripts that must produce no schema diagnostics unless explicitly expected:

- CTEs.
- Temp tables.
- Table variables.
- SELECT INTO temp table.
- Dynamic SQL.
- OPENJSON/OPENROWSET.
- Synonyms.
- Cross-database names not hydrated.
- 4-part names.
- Lite/partial metadata.
- Mid-hydration generation changes.
- Keyword-looking identifiers.
- Case-sensitive collation cases.
- `USE` database switching.

### 17.5 Provider equivalence tests

Run the same feature tests against:

- Fixture provider.
- Null provider.
- Catalog provider backed by a fixture `CatalogSnapshot`.

### 17.6 Scripting tests

- Golden output for each emitter.
- Anchor location tests.
- Identifier quoting tests.
- ALTER rewrite tests.
- Missing metadata/fidelity note tests.
- Optional engine round-trip tests in a scratch DB.

### 17.7 Integration tests

- Query Studio webview provider calls over RPC.
- Toggle live switch.
- Bridge fallback.
- Shadow connection created only when needed.
- Diagnostics markers appear and clear correctly.
- Database dropdown and `USE` changes update language context.

---

## 18. Observability and privacy

### 18.1 Spans

Add or reuse telemetry vocabulary through the repository's contracts registry:

```text
sqlLanguage.lex
sqlLanguage.segment
sqlLanguage.parse
sqlLanguage.overlay
sqlLanguage.bind
sqlLanguage.completion
sqlLanguage.hover
sqlLanguage.signature
sqlLanguage.diagnostics
sqlLanguage.semanticTokens
sqlLanguage.definition
sqlScripting.script
queryStudio.languageService.route
queryStudio.languageService.bridge
```

Safe span attributes:

- Feature name.
- Engine route.
- Duration.
- Candidate count.
- Diagnostic count.
- Suppression reason counts.
- Provider generation number.
- Readiness states.
- Cache hit/miss.
- Document size bucket.
- Statement kind.
- Completion context kind.

Do not include:

- Query text.
- User-written identifiers.
- Literal values.
- Raw schema names unless existing metadata telemetry policy already permits them.

### 18.2 Status command

Add command:

```text
MSSQL: Show Query Studio Language Service Status
```

It should show:

- Preferred engine setting.
- Effective engine per feature.
- Native capability table.
- Provider readiness by section.
- Current metadata generation.
- Last generation change.
- Cache sizes.
- Diagnostic suppression counts.
- Shadow bridge connection state.

This command is a debugging lantern for both users and coding agents.

---

## 19. Detailed phased execution plan

Each phase should end with typecheck/build/test green, a PROGRESS entry, and a small decision note if anything was deferred.

### B8 / LS-0: Foundation, toggle, router, bridge, lexer, metadata seam

Objective: make the architecture real without claiming native IntelliSense yet.

Tasks:

1. Add setting `mssql.queryStudio.languageService.engine` with default `sqlToolsService`.
2. Add `LanguageFeatureRouter` and feature interface:

```ts
export interface SqlLanguageFeatureEngine {
  completion(req: CompletionRequest): Promise<CompletionResult>;
  hover(req: HoverRequest): Promise<HoverResult | undefined>;
  signatureHelp(req: SignatureRequest): Promise<SignatureResult | undefined>;
  diagnostics(req: DiagnosticsRequest): Promise<DiagnosticsResult>;
  definition(req: DefinitionRequest): Promise<DefinitionResult | undefined>;
  semanticTokens(req: SemanticTokensRequest): Promise<SemanticTokensResult | undefined>;
  folding(req: FoldingRequest): Promise<FoldingResult>;
  documentSymbols(req: SymbolsRequest): Promise<SymbolsResult>;
  highlights(req: HighlightsRequest): Promise<HighlightsResult>;
}
```

3. Wire Query Studio RPC contracts for completion, resolve-completion, hover, signature, diagnostics, definition, folding, symbols, highlights, semantic tokens where not already present.
4. Implement bridge engine using provider commands or direct STS v1 adapter.
5. Ensure shadow STS v1 connection lifecycle is explicit and lazy.
6. Implement provider types, null provider, fixture provider, and catalog provider skeleton.
7. Implement full lexer and line-state incremental lex tests.
8. Implement GO batch/statement segmenter and shared execution-splitter parity tests.
9. Implement text/position utility layer.
10. Add fourslash harness skeleton.
11. Add status command.
12. Add telemetry spans for routing, lexing, parsing placeholder, and bridge calls.

Acceptance gate:

- Toggle changes effective route.
- Bridge completions/hover/diagnostics still work in Query Studio.
- Native lexer and segmenter pass corpus tests.
- No native feature claims schema completion yet.
- Shadow STS v1 connection is not created when no bridge-routed feature is requested.

### B9 / LS-1: Native non-AI completions

Objective: ship native completions behind `nativeTypeScript` preference and capability routing.

Tasks:

1. Implement sketch parser for SELECT/FROM/JOIN/CTE/INSERT/UPDATE/DELETE/EXEC/DECLARE/CREATE TABLE enough for completions.
2. Implement overlay builder for CTEs, temp tables, table variables, and simple script-local DDL.
3. Implement database context map for `USE`.
4. Implement binder for sources, columns, aliases, variables, CTEs, temp tables, and procedure parameters.
5. Implement completion context classifier.
6. Implement candidate generation for every context in Section 10.2.
7. Implement FK join suggestions and join table ranking.
8. Implement star expansion completion item.
9. Implement snippets and keyword casing.
10. Implement ranking and item shaping.
11. Implement lazy completion resolve for docs/details.
12. Add benchmark probes.
13. Promote router capability: `completion=preview` behind setting.

Acceptance gate:

- 150+ completion tests green.
- Warm p95 completion under 40 ms.
- Join suggestions work on FK fixture.
- No network I/O during completion request.
- Incomplete metadata returns honest incomplete results, not wrong results.

### B10 / LS-2: Native diagnostics

Objective: publish native diagnostics with strict suppression and measured honesty.

Tasks:

1. Implement T1 lexer/structural diagnostics.
2. Implement T2 binder diagnostics for 207/208/209-style cases.
3. Implement diagnostic suppression ladder.
4. Implement debounce/sliced diagnostic scheduler.
5. Publish diagnostics through Query Studio RPC.
6. Add suppression telemetry counters.
7. Add user setting `mssql.sqlLanguage.diagnostics.enabled`.
8. Add status-command display for suppression counts.
9. Expand honesty suite.
10. Promote router capability: `diagnostics=preview` behind setting.

Acceptance gate:

- Honesty suite green with zero unexpected diagnostics.
- 100+ diagnostic tests green.
- Dogfood scripts reviewed with no unresolved false positives.
- Diagnostics clear on document close and route switch.

### B11 / LS-3: Native hover/tooltips and signature help

Objective: add metadata-rich tooltips and signature help after binder and diagnostics are stable.

Tasks:

1. Implement hover for objects, columns, aliases, variables, parameters, CTEs, temp tables, procedures, functions, and builtins.
2. Add H7 descriptions/extended properties to MetadataService if not already built.
3. Add builtin function data and signature data.
4. Implement signature help for routines and builtins.
5. Implement lazy docs/description lookup where safe.
6. Add hover Markdown shaping with no unsupported claims.
7. Promote router capabilities: `hover=preview`, `signatureHelp=preview`.

Acceptance gate:

- 80+ hover tests and 60+ signature tests green.
- Missing descriptions/definitions degrade cleanly.
- Hover does not trigger network I/O except explicit lazy resolve paths.

### B12 / LS-4: Scripting engine and go-to/peek-definition

Objective: replace old definition behavior through native binder plus TypeScript scripting.

Tasks:

1. Add `src/sqlScripting/**` API and service.
2. Add MetadataService lazy detail reads required by scripting.
3. Implement ModuleEmitter for catalog definitions.
4. Implement token-level `CREATE` to `ALTER` and `CREATE OR ALTER` rewrite.
5. Implement CreateTableEmitter F1/F2.
6. Implement DmlTemplateEmitter.
7. Implement script anchors.
8. Implement definition routing by bound symbol kind.
9. Implement Query Studio peek virtual Monaco model.
10. Implement `mssql-def:` virtual document provider for open-to-side.
11. Add script-as commands where safe.
12. Promote router capability: `definition=preview`.

Acceptance gate:

- Definition on table column opens generated CREATE at the column line.
- Definition on local symbols navigates in-document.
- Module definition unavailable cases are honest.
- Golden scripts green.
- ALTER rewrite tests green.

### B13 / LS-5: Semantic polish and optional colorization

Objective: add visible quality features and prepare adoption evidence.

Tasks:

1. Implement folding and document symbols if not already shipped in LS-0.
2. Implement document highlights.
3. Implement semantic tokens full and delta.
4. Optionally implement lexer-driven Monaco tokenizer behind preview setting or native engine mode.
5. Implement code actions: expand star, qualify column, add alias, fill GROUP BY.
6. Add colorization/semantic-token tests.
7. Add feature-capture replay for native completion and diagnostics summaries.

Acceptance gate:

- Semantic token tests green.
- No regression in completion/diagnostics perf.
- Optional colorization can be disabled independently if it causes theme regressions.

### B14 / LS-6: Audit, adoption, and default-flip decision

Objective: collect evidence, close gaps, and decide whether native becomes default for Query Studio.

Tasks:

1. Run parity matrix against old STS v1 behavior.
2. Generate native-vs-bridge latency report.
3. Review telemetry suppression counters.
4. Review dogfood false-positive/false-negative diagnostics.
5. Fix or explicitly document remaining deltas.
6. Decide default setting for Query Studio.
7. Decide whether classic editor gets a preview native path.
8. Document deprecation plan for shadow STS v1 language connection in Query Studio.

Acceptance gate:

- Decision memo attached to PROGRESS.
- Release notes drafted.
- Default flip either approved with evidence or deferred with specific blockers.

---

## 20. Coding-agent first steps

A coding agent starting from Query Studio should do this first:

1. Search for Query Studio model/controller/provider code:

```text
QueryStudioController
QueryStudioDocumentModel
sqlInlineCompletionProvider
signalDatabaseChanged
QsLsp
QS_SCHEMA_VERSION
```

2. Search for MetadataService and catalog code:

```text
MetadataService
CatalogSnapshot
catalogModel
completionSystemObjectCatalog
resolveName
buildSchemaContext
```

3. Search for existing observability and contracts patterns:

```text
queryStudio.lsp
contracts registry
feature-capture
Replay Lab
PERF_MODE
```

4. Search for STS v1 language-service hooks:

```text
executeCompletionItemProvider
vscode.executeCompletionItemProvider
onDidChangeDiagnostics
language client
SQL Tools Service
```

5. Build a small LS-0 branch with only:

- setting,
- router,
- bridge,
- null native engine,
- lexer tests,
- provider types.

Do not start with the parser deep end. Get the switchboard humming first, then install the instruments.

---

## 21. Risk register

| Risk | Mitigation |
|---|---|
| Sketch parser grows into unbounded grammar project | Feature-driven parser backlog, oracle tests, and explicit escape hatch to per-statement ANTLR. |
| False diagnostics damage trust | Suppression ladder, warning-first severity, honesty suite, status counters. |
| Metadata incomplete or stale | Readiness-aware features, no-network hot path, generation pinning, background hydration requests. |
| `USE` and database dropdown disagree | Statement-level database context map and suppress when target DB is not hydrated. |
| Bridge side effects | Lazy shadow connection, lifecycle isolation, direct adapter if provider-command aggregation is too broad. |
| Scripting omissions mislead users | Fidelity levels and header notes. |
| Completion ranking feels noisy | Deterministic ranking, test top-N expectations, MRU bounded to document/session. |
| Bundle size grows | Keep parser handwritten initially, data assets curated/gzippable, no shipped ScriptDOM/ANTLR. |
| Worker migration becomes necessary | Keep core pure and serialization-friendly from LS-0. |
| Telemetry accidentally leaks code | Central telemetry wrapper with allowlisted attributes only. |

---

## 22. Open decisions

| Decision | Recommendation |
|---|---|
| Provider-command bridge vs direct STS v1 adapter | Start with provider-command bridge. Move to direct adapter only if aggregation causes parity or noise problems. |
| Native tokenizer in LS-0 or LS-5 | Build lexer in LS-0. Expose lexer-driven colorization in LS-5 or behind a preview setting. |
| `CREATE OR ALTER` output default | Default to `ALTER` for alter operations unless user explicitly requests `createOrAlter` and server capability supports it. |
| Diagnostics severity | T1 errors, T2 warnings until audit. Promote only with evidence. |
| Classic editor adoption | Do not include in core rollout. Add a separate preview setting after Query Studio default decision. |
| Dynamic SQL analysis | Backlog. Start with suppression, then optional `sp_executesql N'...'` analysis later. |
| Cross-database metadata | Suppress unless hydrated. Add multi-db MetadataService support only if product priority requires it. |

---

## Appendix A. Native completion acceptance matrix

| Scenario | Required by LS-1 |
|---|---|
| Keyword at statement start | yes |
| SELECT-list columns by alias | yes |
| SELECT-list unqualified columns | yes |
| WHERE/ON expression columns | yes |
| FROM table search | yes |
| JOIN table search ranked by FK | yes |
| ON predicate from FK | yes |
| Composite FK predicate | yes |
| CTE source and columns | yes |
| Derived table alias columns | yes for explicit aliases, partial for inferred |
| Temp table columns from CREATE TABLE | yes |
| Temp table names from SELECT INTO | yes, unknown types accepted |
| Table variable columns | yes |
| INSERT target column list | yes |
| VALUES placeholders | yes |
| UPDATE SET target columns | yes |
| EXEC procedure names | yes |
| EXEC named parameters | yes |
| Builtin functions | yes |
| User scalar/table functions | yes if metadata ready |
| USE database names | yes if list available |
| ORDER BY aliases | yes |
| GROUP BY fill candidates | yes, can be code-action if not completion |
| Bracket-required identifiers | yes |
| Case-sensitive collation | yes |
| Comments/strings suppress | yes |

---

## Appendix B. Diagnostics acceptance matrix

| Diagnostic | LS-2 support | Notes |
|---|---|---|
| Unterminated string | yes | error |
| Unterminated bracketed identifier | yes | error |
| Unterminated block comment | yes | error or warning based on UX precedent |
| Invalid GO count/trailing junk | yes | error |
| Duplicate alias | yes | warning/error after confidence |
| Invalid object name 208 | yes | warning first, suppress unless objects ready |
| Invalid column name 207 | yes | warning first, suppress unless all sources typed |
| Ambiguous column name 209 | yes | warning first |
| Unknown named EXEC parameter | yes | warning if proc resolved and params ready |
| Syntax grammar errors | partial | do not chase full grammar initially |
| User proc arg count | no initially | metadata lacks defaults and procs can be flexible |
| Dynamic SQL errors | no | suppress |

---

## Appendix C. Metadata detail cookbook for scripting

The coding agent should map these logical needs to existing STS2/MetadataService APIs or add new STS2-backed detail reads through MetadataService.

| Metadata detail | SQL Server source family | Use |
|---|---|---|
| Module definition | `sys.sql_modules`, `OBJECT_DEFINITION` semantics | Module scripting and definition. |
| Identity | `sys.identity_columns` | `IDENTITY(seed, increment)` scripting. |
| Computed columns | `sys.computed_columns` | computed expression and persisted scripting. |
| Default constraints | `sys.default_constraints` | column/table default scripting. |
| Check constraints | `sys.check_constraints` | check scripting and fidelity notes. |
| Indexes | `sys.indexes`, `sys.index_columns` | index scripting. |
| Extended descriptions | `sys.extended_properties` | hover docs and script comments/properties. |
| Foreign keys | `sys.foreign_keys`, `sys.foreign_key_columns` | joins and FK scripting. |
| Key constraints | `sys.key_constraints`, index columns | PK/unique scripting. |

---

## Appendix D. External references checked for this replacement

These links are not runtime dependencies. They are research/provenance references for the design.

- SqlScriptDOM repository: https://github.com/microsoft/SqlScriptDOM
- SqlParser repository notice: https://github.com/microsoft/SqlParser
- Microsoft.SqlServer.Management.SqlParser NuGet: https://www.nuget.org/packages/Microsoft.SqlServer.Management.SqlParser/
- `IMetadataProvider` API shape: https://learn.microsoft.com/en-us/dotnet/api/microsoft.sqlserver.management.sqlparser.metadataprovider.imetadataprovider
- antlr4ng TypeScript runtime: https://github.com/mike-lischke/antlr4ng
- antlr4-c3 completion engine: https://github.com/mike-lischke/antlr4-c3
- dt-sql-parser supported dialects and feature model: https://github.com/DTStack/dt-sql-parser
- node-sql-parser package: https://www.npmjs.com/package/node-sql-parser
- tree-sitter-tsql: https://github.com/Crary-Systems/tree-sitter-tsql
- generic tree-sitter SQL grammar: https://github.com/DerekStride/tree-sitter-sql
- VS Code built-in commands: https://code.visualstudio.com/api/references/commands
- VS Code command guide: https://code.visualstudio.com/api/extension-guides/command
- VS Code semantic highlighting guide: https://code.visualstudio.com/api/language-extensions/semantic-highlight-guide
- SQL Server error 207: https://learn.microsoft.com/en-us/sql/relational-databases/errors-events/mssqlserver-207-database-engine-error
- SQL Server error 208: https://learn.microsoft.com/en-us/sql/relational-databases/errors-events/mssqlserver-208-database-engine-error
- `sys.sql_modules`: https://learn.microsoft.com/en-us/sql/relational-databases/system-catalog-views/sys-sql-modules-transact-sql
- `OBJECT_DEFINITION`: https://learn.microsoft.com/en-us/sql/t-sql/functions/object-definition-transact-sql
- `CREATE OR ALTER` support: https://support.microsoft.com/en-us/topic/kb3190548-update-introduces-create-or-alter-transact-sql-statement-in-sql-server-2016-fd0596f3-9098-329c-a7a5-2e18f29ad1d4
- `CREATE PROCEDURE` syntax with `OR ALTER`: https://learn.microsoft.com/en-us/sql/t-sql/statements/create-procedure-transact-sql
- `CREATE VIEW` `OR ALTER` notes: https://learn.microsoft.com/en-us/sql/t-sql/statements/create-view-transact-sql
- `sys.identity_columns`: https://learn.microsoft.com/en-us/sql/relational-databases/system-catalog-views/sys-identity-columns-transact-sql
- `sys.computed_columns`: https://learn.microsoft.com/en-us/sql/relational-databases/system-catalog-views/sys-computed-columns-transact-sql
- `sys.default_constraints`: https://learn.microsoft.com/en-us/sql/relational-databases/system-catalog-views/sys-default-constraints-transact-sql
- `sys.check_constraints`: https://learn.microsoft.com/en-us/sql/relational-databases/system-catalog-views/sys-check-constraints-transact-sql
- `sys.indexes`: https://learn.microsoft.com/en-us/sql/relational-databases/system-catalog-views/sys-indexes-transact-sql
- `sys.index_columns`: https://learn.microsoft.com/en-us/sql/relational-databases/system-catalog-views/sys-index-columns-transact-sql
