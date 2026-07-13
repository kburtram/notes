# Query Studio Native T-SQL Completions: Parser-Aware Design
## Proposed design updates for context-aware non-AI completions, ranking, advanced suggestions, and quiet failure modes

**Status:** proposed implementation design for `dev/query`.

**Scope:** native TypeScript non-AI completions for Query Studio. AI completions are intentionally out of scope except where they share the metadata substrate.

**Primary inputs:** `current_completions_parser_design.md`, `current_problem_parser_design.md`, `05-tsql-language-service-design.md`, the metadata substrate review pack, and the current `dev/query` source shape.

**Core recommendation:** keep the current completion engine's metadata producers, binder, overlay, FK join logic, star expansion, INSERT/UPDATE/EXEC intelligence, and deterministic ranking. Replace the broad caret-context classifier with a parser-owned `CompletionExpectation` API that says what category of thing is legal at the caret, including when the correct answer is no suggestions.

---

## 0. Executive summary

The native completion engine is already useful. It has a full lexer, segmenter, tolerant sketch parser, overlay, binder, pinned metadata view, candidate producers, deterministic ranking, and tests for many high-value cases such as aliases to the right of the caret, FK-aware joins, temp/table variables, INSERT column lists, UPDATE SET, EXEC parameters, system catalogs, USE databases, and star expansion.

The weak point is not metadata. It is grammar expectation at the caret. The current `CompletionContext` classifier can often identify the nearest clause, but when it cannot prove a better context it falls back to a broad expression context. That fallback is why `CREATE TABLE My` could offer `MODIFY` and `JSON_MODIFY`: the engine did not know the user was declaring a new symbol, so fuzzy matching made wrong candidates look plausible.

The completion engine should become parser-aware:

```text
caret offset
  -> ParsedDocument
  -> CompletionExpectation
  -> CandidateCategory gates
  -> Producers
  -> Ranking
  -> Monaco item shaping
```

The main product rule is simple: **blank is a valid completion result**. When the engine is at a declaration name, unsupported grammar region, unsafe DDL position, string/comment, or untrusted parser recovery point, it should return nothing. It should not play keyword confetti.

---

## 1. Current-state review

### 1.1 What to keep

| Area | Keep because |
|---|---|
| Metadata provider seam | Completions read `IPinnedMetadataView` and do not import MetadataService or STS2 DTOs. This keeps the engine rehostable and testable. |
| Pinned generation discipline | One request uses one metadata generation. This prevents mixed-generation ghost suggestions. |
| Overlay | CTEs, temp tables, table variables, script-created tables, and SELECT INTO objects are essential for smart completions before execution. |
| Binder | Source aliases, columns, derived/CTE shapes, UPDATE alias-form, case sensitivity, and suppression reasons are strong. |
| Candidate producers | Existing producers cover table sources, schemas, columns, variables, builtins, snippets, FK joins, INSERT, UPDATE, EXEC, types, and databases. |
| Ranking | Deterministic score plus kind priority is the right spine. |
| Incomplete results | `isIncomplete` and incomplete reasons are correct for lazy metadata and retrigger flows. |
| No network on hot path | Completion should never wait for metadata hydration. The host may kick background hydration. |
| Tests | The current completion suite already covers many feature-level wins and should keep growing. |

### 1.2 What to change

| Gap | Needed change |
|---|---|
| Classifier is too broad | Replace broad fallback with parser-owned expectations. |
| No declaration-symbol model | Add `declarationName` and related `none` expectations so new-symbol positions stay silent. |
| DDL grammar is too thin | Model enough DDL to distinguish name declarations, type positions, table constraints, and ALTER actions. |
| Diagnostics and completions diverge | Use the same parser and recovery facts as problem detection. |
| Fuzzy match amplifies wrong context | Gate candidate categories before fuzzy matching. Do not try to fix this globally in `matchScore`. |
| Trigger policy cannot fix grammar noise | Automatic trigger policy stays, but grammar expectation decides what can appear. |
| Partial metadata needs more explicit policy | Keep stale-safe completions immediate, but expose freshness/source/incomplete states in status and telemetry. |

---

## 2. Design goals

| ID | Goal |
|---|---|
| C-G1 | Be best-in-class for normal T-SQL authoring: SELECT, JOIN, predicates, INSERT, UPDATE, EXEC, DECLARE, USE, CREATE TABLE, and module bodies. |
| C-G2 | Never show broad unrelated suggestions in positions where a new identifier is being declared. |
| C-G3 | Use parser expectation, not post-hoc filters, to decide candidate categories. |
| C-G4 | Preserve current high-value features: FK join suggestions, star expansion, alias resolution, insert/update scaffolds, EXEC named args, system catalog support, and deterministic ranking. |
| C-G5 | Keep the hot path synchronous and local: no network I/O, no metadata hydration waits, no VS Code API dependency inside core. |
| C-G6 | Degrade honestly: return empty, partial, or incomplete results rather than guessing. |
| C-G7 | Support explicit manual invocation without becoming spammy on automatic triggers. |
| C-G8 | Provide observable counts and decisions without logging SQL text or identifiers. |
| C-G9 | Share parser infrastructure with diagnostics, but keep candidate production and ranking separate. |
| C-G10 | Make the implementation incremental so existing completion behavior can stay green while expectation-driven contexts roll out. |

---

## 3. Non-goals

- AI completions and remote model prompt shaping.
- Full T-SQL grammar parity in the first completion parser batch.
- Natural-language suggestions.
- Cross-object refactoring or schema changes.
- Blocking on live metadata for completion correctness.
- Style linting.
- Full formatting or SQL code generation beyond snippets and small scaffolds.

---

## 4. Target architecture

```text
Query Studio Monaco completion provider
  -> qs/lang.completion RPC
      -> QueryStudioLanguageService
          -> LanguageFeatureRouter
              -> NativeSqlLanguageEngine.completion
                  -> DocumentAnalysis cache
                      lexer + segmenter + parser v2
                      overlay + binder
                  -> expectationAt(caret)
                  -> computeCompletionFromExpectation
                      category gates
                      producers
                      ranking
                      item shaping
```

### 4.1 Module layout

```text
src/sqlLanguage/core/parser/
  cursorExpectation.ts          # produces CompletionExpectation from ParsedDocument
  expected.ts                   # expected-token and keyword sets
  projection.ts                 # AST -> current StatementSketch compatibility

src/sqlLanguage/features/completion/
  index.ts                      # public computeCompletion entry point
  expectationAdapter.ts          # temporary bridge from CompletionExpectation to producers
  producers/
    keywords.ts
    snippets.ts
    objects.ts
    columns.ts
    joins.ts
    dml.ts
    exec.ts
    types.ts
    databases.ts
  ranking.ts
  replaceRange.ts
  triggerPolicy.ts
  itemDocs.ts

src/sqlLanguage/core/context.ts
  temporary legacy classifier, eventually reduced to a compatibility shim
```

The first implementation can keep `features/completion.ts` as the public entry point and gradually move internals. Do not do a huge file shuffle before the parser expectation API lands.

### 4.2 New data flow

```ts
const analysis = analyzer.getOrCreateAnalysis(snapshot);
const parsed = analysis.parsed;
const expectation = expectationAt(parsed, caretOffset, {
    triggerKind,
    triggerCharacter,
    manualInvoke,
});
const binding = bindForExpectation(expectation, analysis, pinned);
return computeCompletionFromExpectation({ expectation, binding, overlay, pinned, ... });
```

Parser expectation is the gate. Candidate producers are not allowed to overrule it.

---

## 5. `CompletionExpectation` contract

### 5.1 Shape

```ts
export interface CompletionExpectation {
    readonly kind: CompletionExpectationKind;
    readonly confidence: "certain" | "probable" | "none";
    readonly span: SqlTextSpan;
    readonly replacementSpan: SqlTextSpan;
    readonly prefix: string;
    readonly trigger: CompletionTriggerInfo;
    readonly scopeId?: number;
    readonly statementId?: number;
    readonly clause?: ParsedClauseKind;
    readonly qualifier?: readonly string[];
    readonly expectedKeywords?: readonly string[];
    readonly allowedObjectKinds?: readonly LangObjectKind[];
    readonly suppressReason?: CompletionSuppressReason;
    readonly recovery?: RecoveryDecision;
    readonly metadataNeed?: CompletionMetadataNeed;
}

export type CompletionExpectationKind =
    | "none"
    | "statementKeyword"
    | "clauseKeyword"
    | "tableSource"
    | "schemaMember"
    | "databaseMember"
    | "memberAccess"
    | "columnExpression"
    | "valueExpression"
    | "predicateExpression"
    | "joinTableSource"
    | "joinPredicate"
    | "insertTarget"
    | "insertColumnList"
    | "insertValues"
    | "updateTarget"
    | "updateSetTarget"
    | "execProcedure"
    | "execArgumentName"
    | "execArgumentValue"
    | "declareVariableName"
    | "typeName"
    | "databaseName"
    | "declarationName"
    | "tableConstraint"
    | "alterTableAction"
    | "moduleParameter"
    | "setOption";

export type CompletionSuppressReason =
    | "comment"
    | "string"
    | "sqlcmd"
    | "declarationName"
    | "newColumnName"
    | "unsupportedSyntax"
    | "untrustedRecovery"
    | "midEditUnknown"
    | "automaticWhitespace"
    | "metadataUnavailable"
    | "noUsefulContext";

export interface CompletionMetadataNeed {
    readonly objects?: boolean;
    readonly columns?: boolean;
    readonly parameters?: boolean;
    readonly foreignKeys?: boolean;
    readonly databases?: boolean;
    readonly lazyObject?: LangObjectRef;
}
```

### 5.2 Semantics by expectation kind

| Expectation | Candidate categories |
|---|---|
| `none` | no suggestions |
| `statementKeyword` | statement keywords, snippets, optional default completions |
| `clauseKeyword` | only legal clause keywords for current grammar state |
| `tableSource` | schemas, tables, views, TVFs, synonyms, CTEs, temp tables, table variables, derived-table snippet |
| `joinTableSource` | FK-adjacent tables first, then normal table sources |
| `schemaMember` | objects in schema, kind-filtered by context |
| `databaseMember` | schemas in current database if hydrated, otherwise incomplete |
| `memberAccess` | columns for source alias/object, schema/database members when qualifier is a schema/database |
| `columnExpression` | visible columns, select-list aliases where legal, variables, functions, expression keywords |
| `predicateExpression` | columns, variables, functions, predicate keywords, EXISTS/IN snippets |
| `valueExpression` | variables, parameters, scalar functions, constants/snippets, expression keywords |
| `joinPredicate` | FK predicates and compatible name/type predicates, then predicate expression |
| `insertTarget` | table-like objects |
| `insertColumnList` | writable target columns and all-columns scaffold |
| `insertValues` | placeholder scaffold aligned to column list, variables, constants |
| `updateTarget` | table-like objects or aliases in UPDATE FROM shape |
| `updateSetTarget` | writable target columns with `col = ` scaffold |
| `execProcedure` | user procedures, system procedures, snippets |
| `execArgumentName` | remaining named parameters with `@p = ` scaffold |
| `execArgumentValue` | variables, constants, columns only when expression context allows |
| `declareVariableName` | no suggestions by default; future template only |
| `typeName` | system types, table type if available, `TABLE` when grammar allows it |
| `databaseName` | provider databases, with incomplete when unavailable |
| `declarationName` | no suggestions by default |
| `tableConstraint` | `CONSTRAINT`, `PRIMARY KEY`, `UNIQUE`, `FOREIGN KEY`, `CHECK`, `DEFAULT` where grammar allows |
| `alterTableAction` | `ADD`, `DROP`, `ALTER COLUMN`, `WITH CHECK`, context-specific actions |
| `moduleParameter` | variable declaration support, types, OUTPUT keyword |
| `setOption` | SET options and local variable assignment based on parser context |

---

## 6. Candidate gating rules

### 6.1 No producer without a matching expectation

Candidate producers should have explicit gates:

```ts
interface CandidateProducer {
    readonly id: string;
    readonly expects: readonly CompletionExpectationKind[];
    produce(input: ProducerInput): ProducerResult;
}
```

The aggregator invokes a producer only if `expectation.kind` is in `expects`. This prevents `addBuiltins` from running in a declaration-name context and prevents table sources from appearing in predicate-only contexts.

### 6.2 No fuzzy matching before category gating

The pipeline should be:

```text
expectation kind -> candidate category -> raw candidates -> prefix/match -> ranking
```

Never:

```text
all candidates -> fuzzy match -> hope ranking fixes it
```

Fuzzy matching is a amplifier. It should amplify the right shelf of books, not open every cabinet in the house.

### 6.3 Declaration positions are quiet

Default quiet positions:

- `CREATE TABLE My/*caret*/`;
- `CREATE TABLE dbo./*caret*/` when declaring a new object name;
- `CREATE TABLE My (/*caret*/` when declaring a new column name;
- `DECLARE @x/*caret*/` while typing variable name;
- `CREATE PROC MyProc/*caret*/` while typing procedure name;
- `CREATE VIEW v/*caret*/` before `AS`;
- `CREATE FUNCTION f/*caret*/` before parameter/type grammar; 
- `ALTER TABLE t ADD NewColumn/*caret*/` before type position.

Future optional name-template completions can be added deliberately, but the default engine should return empty. A silent owl is wiser than a loud autocomplete ferret.

---

## 7. Parser expectation details

### 7.1 Cursor expectation algorithm

At the caret:

1. Find the innermost parsed statement and AST node containing the offset.
2. If inside comment/string/SQLCMD token, return `none`.
3. If parser has a recovery event covering the offset:
   - if recovery is trusted for completion, use its expected set;
   - otherwise return `none` with `untrustedRecovery`.
4. If offset is in a known declaration-name span, return `declarationName` or `none`.
5. If after a dot, return `memberAccess` with qualifier chain and prefix.
6. If inside a clause, use the production state to return the expected category.
7. If the statement is complete and trigger is automatic whitespace, return `none`.
8. If at a statement boundary, return `statementKeyword`.
9. Otherwise return `none` unless the parser can prove a value or column expression.

This intentionally removes the legacy default of `expression, clause=body`.

### 7.2 Mid-edit handling

Examples:

| Input | Expectation |
|---|---|
| `SELECT * FROM ` | `tableSource` |
| `SELECT * FROM Sales.Orders o WHERE ` | `predicateExpression` |
| `SELECT * FROM Sales.Orders o WHERE o.` | `memberAccess` |
| `SELECT * FROM Sales.Orders o JOIN ` | `joinTableSource` |
| `SELECT * FROM Sales.Orders o JOIN Sales.Customers c ON ` | `joinPredicate` |
| `SELECT * FROM Sales.Orders o ORDER ` | `clauseKeyword` with expected `BY` |
| `CREATE TABLE My (` | `none` or `declarationName` with suppress reason `newColumnName` |
| `CREATE TABLE My (Id ` | `typeName` |
| `CREATE TABLE My (Id i` | `typeName` with prefix `i` |

### 7.3 Recovery and completions

Parser recovery can improve completions after typos, but only when it is safe.

| Recovery | Completion behavior |
|---|---|
| split `fr om` recovered as FROM | table-source context after recovered FROM if caret is after it; no column claims from untrusted skipped text |
| missing `BY` after ORDER | suggest `BY` as clause keyword |
| unmatched trailing `(` | suppress if mid-edit |
| skipped unknown tokens before WHERE | allow predicate completions only after synchronizer, not inside skipped run |
| unsupported statement family | statement-start keywords only at clear boundaries, otherwise none |

---

## 8. Producer design

### 8.1 Object and source producer

Inputs:

```ts
interface ObjectProducerInput {
    readonly expectation: CompletionExpectation;
    readonly pinned: IPinnedMetadataView;
    readonly overlay: ScriptOverlay;
    readonly scope: BoundScopeInfo;
    readonly prefix: string;
}
```

Rules:

- Use `searchObjects({ prefix, kinds, limit })` for catalog objects.
- Add overlay objects before catalog objects when both match.
- Add CTEs only in statement scope.
- Add schemas as narrowing candidates only where `schema.` is useful.
- Do not list procedures in `FROM` except TVFs.
- When `objects` readiness is loading/stale/failed, return overlay/schema safe items and mark incomplete if retry can help.
- Never block for hydration.

### 8.2 Member-access producer

Cases:

1. Qualifier resolves to visible source alias: return columns.
2. Qualifier resolves to schema name in table-source context: return objects in schema.
3. Qualifier resolves to current database name: return schemas.
4. Qualifier is cross-database not hydrated: return empty and incomplete with `crossDatabaseUnhydrated`.
5. Qualifier unresolved: return empty.
6. Columns lazy/not loaded: kick background hydration through host seam and return incomplete.

This producer must stay strict. If `o.` cannot be resolved, do not list all columns in the database.

### 8.3 Column/value expression producer

- Visible columns from current scope, inner to outer.
- Qualify ambiguous column labels as `alias.ColumnName`.
- Include variables and parameters in scope.
- Include built-in scalar functions.
- Include expression keywords only legal for the production state.
- Include select-list aliases only where T-SQL allows them: ORDER BY, sometimes GROUP BY depending parser policy and SQL Server semantics review.
- Do not add table sources in predicate positions.

### 8.4 Join suggestions producer

Join table ranking and ON predicate suggestions remain a marquee feature.

#### Join table source ranking

When expectation is `joinTableSource`:

1. Collect existing FROM sources with resolved object refs.
2. Use `fkFrom` and `fkTo` to find adjacent tables.
3. Boost adjacent tables above general object search.
4. Prefer tables not already in the FROM set unless self-join is likely or explicitly typed.
5. Include detail such as `FK to Sales.Orders` without logging object names in telemetry.
6. If FK section is not ready, mark incomplete and use normal table-source ranking.

#### Join predicate suggestions

When expectation is `joinPredicate`:

- Generate complete equality predicates for FK edges between the newly joined source and prior sources.
- Support composite FKs: `a.K1 = b.K1 AND a.K2 = b.K2`.
- Support reverse direction.
- Rank named FK edges first.
- Add lower-ranked name/type compatible predicates only when column metadata is ready and no FK candidate exists.
- Never fabricate predicate suggestions with unknown columns.

### 8.5 INSERT producer

Expectations:

- `insertTarget`: table-like objects.
- `insertColumnList`: writable columns, excluding identity/computed and already-listed columns.
- `insertValues`: snippet placeholders aligned to known columns.

Details:

- `(all columns)` item should insert all writable columns, formatted as a list.
- Values scaffold should be retriggered after column list if parser can infer column order.
- If target columns are not ready, return incomplete rather than guessing.

### 8.6 UPDATE producer

Expectations:

- `updateTarget`: table-like objects or alias target when parser sees UPDATE FROM.
- `updateSetTarget`: writable target columns with `Column = ` scaffold.
- `valueExpression`: RHS expressions.

Rules:

- Resolve UPDATE alias targets through FROM clause.
- Exclude computed columns when metadata says so.
- Identity column behavior should be conservative: do not exclude from UPDATE solely because identity unless SQL Server rules are verified for the target context. Computed columns should be excluded.

### 8.7 EXEC producer

Expectations:

- `execProcedure`: procedures.
- `execArgumentName`: remaining named parameters.
- `execArgumentValue`: variables, constants, and expressions.

Rules:

- Resolve system procedures from curated catalog when live metadata lacks them.
- Track supplied named parameters.
- Include output marker for output params, for example detail `int OUTPUT` and insert text `@Total = `.
- Do not flag or suppress unknown proc completions based on partial metadata; return partial results.

### 8.8 Type producer

Expectations:

- `typeName`, `moduleParameter`, CREATE TABLE column type positions.

Items:

- system types with common sizes, for example `INT`, `BIGINT`, `BIT`, `DATE`, `DATETIME2`, `NVARCHAR(50)`, `NVARCHAR(MAX)`, `DECIMAL(18,2)`, `UNIQUEIDENTIFIER`;
- `TABLE` only in `DECLARE @t` context;
- user-defined types when metadata section exists in a future extension;
- snippets for `IDENTITY(1,1)` only after a type in column options, not in type position.

### 8.9 Keyword producer

`clauseKeyword` should list only legal next keywords. Examples:

| Context | Keywords |
|---|---|
| after SELECT list | `FROM`, `WHERE`, `GROUP BY`, `HAVING`, `ORDER BY`, `OPTION`, `UNION` as legal for the current state |
| after `ORDER` | `BY` only |
| after `GROUP` | `BY` only |
| after table source before predicate | `WHERE`, `GROUP BY`, `HAVING`, `ORDER BY`, `OPTION`, set operators |
| after JOIN source | `ON` except CROSS JOIN/APPLY variants |
| ALTER TABLE after object | `ADD`, `DROP`, `ALTER COLUMN`, `WITH CHECK`, `CHECK`, `NOCHECK` depending state |

Default SQL Tools Service keyword text can still be used at `statementKeyword`, but it should not leak into expression or declaration contexts.

---

## 9. Ranking design

### 9.1 Score inputs

```ts
score =
    expectationPriority
  + candidateKindPriority
  + matchScore
  + localityBoost
  + relationBoost
  + recencyBoost
  + exactCaseBoost
  - noisePenalty
```

### 9.2 Ranking rules

| Rule | Details |
|---|---|
| Prefix first | Exact prefix and word-boundary prefix outrank ordered-subsequence fuzzy. |
| Expectation dominates | A candidate from the exact expected category outranks generic defaults. |
| Local columns first | Current source columns, target columns, and recently used variables outrank global functions. |
| FK relationship boost | FK-adjacent join targets and predicates outrank generic table suggestions. |
| System penalty | System objects/functions rank lower unless prefix signals system intent: `sys`, `sp_`, `@@`, `fn_`. |
| Snippet floor | Snippets sort below concrete keywords/objects unless manual invocation and prefix exactly matches snippet key. |
| Deterministic tie break | ordinal compare on stable label, not locale-dependent ordering. |

### 9.3 Prefix and replacement ranges

The expectation API should return replacement spans, not let each producer guess.

Examples:

| Input | Replacement |
|---|---|
| `SELECT * FROM Sal/*caret*/` | `Sal` |
| `SELECT * FROM Sales./*caret*/` | zero-width after dot |
| `SELECT o.Or/*caret*/ FROM ...` | `Or` |
| `ORDER /*caret*/` expecting BY | zero-width after whitespace, or replace current partial word if present |
| `CREATE TABLE My/*caret*/` | no completion |

Use token spans to avoid replacing brackets, quoted identifiers, or dot chains incorrectly.

---

## 10. Trigger policy

### 10.1 Trigger kinds

| Trigger | Policy |
|---|---|
| `.` | Always ask parser; member access can return empty quickly. |
| space | Only show if expectation has high-value whitespace trigger: FROM, JOIN, EXEC args, type position, clause keyword. Suppress after complete statements. |
| `@` | Variables/parameters in contexts where values or declaration variable names are expected. Declaration variable name stays quiet except manual template future. |
| `(` | Signature help usually owns this; completion only for INSERT column list, VALUES scaffold, table-valued constructs where useful. |
| manual invoke | Broader but still expectation-gated. It may show statement keywords where auto would be quiet, but it must not show expression candidates in declaration names. |

### 10.2 Automatic whitespace suppression

Automatic completions after whitespace should require one of:

- parser expects a table source after `FROM` or `JOIN`;
- parser expects a predicate after `ON` or `WHERE`;
- parser expects a clause keyword after `ORDER` or `GROUP`;
- parser expects an EXEC argument;
- parser expects a type name;
- parser expects a database after `USE`;
- parser expects a statement keyword at an empty statement boundary.

Everything else should stay silent. Manual Ctrl+Space can ask for more, but still through expectation gates.

---

## 11. Metadata freshness and cache policy

Completions are stale-safe. They should use `MetadataPolicies.completion` or the current equivalent:

- allow stale memory or disk snapshot;
- start background refresh when stale beyond configured threshold;
- never block on validation;
- return incomplete when the needed section is loading or missing and retrigger can help;
- request hydration for lazy columns or parameters only through fire-and-forget host seam.

### 11.1 Readiness mapping

| Metadata state | Completion behavior |
|---|---|
| objects ready, columns ready | full metadata completions |
| objects loading | overlay/local suggestions plus incomplete |
| objects failed | overlay/local suggestions, no catalog object claims, status/incomplete reason |
| columns loading | table sources okay, member-access columns empty/incomplete |
| parameters loading | procedures okay, EXEC args empty/incomplete |
| foreignKeys loading | JOIN table/predicate relation boosts disabled/incomplete |
| offline snapshot | completions serve snapshot with offline status, no live-validation wait |

### 11.2 Incomplete reason vocabulary

```ts
export type CompletionIncompleteReason =
    | "objectsNotReady"
    | "columnsNotReady"
    | "parametersNotReady"
    | "foreignKeysNotReady"
    | "crossDatabaseUnhydrated"
    | "metadataStaleRefreshStarted"
    | "offlineSnapshot"
    | "lazyHydrationRequested"
    | "resultCapped";
```

These are user-hidden by default but important for status, tests, and diagnostics.

---

## 12. Advanced features to preserve and deepen

### 12.1 FK-aware joins

Current FK join behavior should graduate from producer feature to expectation-driven flagship feature.

Acceptance examples:

```sql
SELECT * FROM Sales.Orders o JOIN /*caret*/
```

Expected:

- `Sales.Customers` and `Sales.OrderLines` rank before unrelated tables when FK metadata is ready.
- If FK metadata is loading, normal table source suggestions appear and result is incomplete.

```sql
SELECT * FROM Sales.Orders o JOIN Sales.Customers c ON /*caret*/
```

Expected:

- first item is `o.CustomerID = c.CustomerID` when FK exists.
- composite keys insert full multi-predicate.

### 12.2 Star expansion

Preserve current `Expand columns` item and code-action path, but gate it through parser expectation:

- only at `*` or `alias.*` tokens in SELECT list;
- not inside COUNT(*), EXISTS SELECT 1, comments, strings, or multiplication expressions;
- only when source columns are ready;
- include incomplete reason when hidden due to columns not ready.

### 12.3 GROUP BY and ORDER BY assists

- ORDER BY: select-list aliases, ordinals as optional snippets, columns.
- GROUP BY: non-aggregate select expressions that are simple columns or aliases if allowed by server semantics review; do not generate function/expression groupings unless parser/binder can trust them.

### 12.4 Alias generation

In table-source contexts, optional snippets can offer:

```sql
Sales.Orders AS o
Sales.Customers AS c
```

Alias generation should be deterministic and collision-aware:

- use initials from object name words;
- avoid aliases already in scope;
- prefer `o`, `c`, `ol` style;
- never force alias generation ahead of plain object insertion.

### 12.5 System catalog and builtins

Keep curated static system catalog. Improvements:

- use expectation to show system objects only in object contexts;
- use `sys.` prefix to boost system objects;
- use function signatures for signature help and completion docs;
- keep system object columns static and type-optional, with honesty flags.

---

## 13. Diagnostics and completions sharing boundary

Shared:

- lexer;
- segmenter;
- parser AST;
- error nodes;
- expected token facts;
- recovery facts;
- cursor expectation API;
- StatementSketch projection;
- overlay;
- binder;
- fixture catalog and corpus.

Separate:

- diagnostic severity, message, and publishing policy;
- completion candidate producers;
- ranking;
- snippets;
- trigger policy;
- Monaco item shaping;
- metadata hydration kick policy;
- performance budgets.

Do not put candidate logic inside the parser. The parser says "table source expected". The completion feature decides which tables, schemas, snippets, filters, and rankings to return.

---

## 14. Implementation phases

### C0 - Stabilize current behavior and guard noisy contexts

Tasks:

1. Keep local CREATE TABLE declaration fix.
2. Add declaration-name guards for:
   - CREATE PROC/PROCEDURE;
   - CREATE VIEW;
   - CREATE FUNCTION;
   - CREATE TRIGGER;
   - DECLARE variable name;
   - CREATE TABLE column name;
   - ALTER TABLE ADD column name before type.
3. Add tests that these contexts return zero items.
4. Add negative tests proving type positions still suggest types.
5. Do not weaken fuzzy matching globally.

Acceptance:

- `CREATE TABLE My`, `CREATE TABLE dbo.`, and `CREATE TABLE My (` stay quiet.
- `CREATE TABLE My (Id i` suggests `INT` and other type names.
- Existing completion tests remain green.

### C1 - Parser expectation infrastructure

Tasks:

1. Add `CompletionExpectation` types in `core/parser/cursorExpectation.ts`.
2. Build expectation lookup from parser v2 where available.
3. Add fallback adapter from current `CompletionContext` for contexts not yet parser-backed.
4. Add `expectationAdapter.ts` to map expectation kinds to current candidate producers.
5. Add tests for expectation snapshots independent of completion items.

Acceptance:

- completion behavior is unchanged for current tested contexts.
- expectation tests prove `declarationName`, `tableSource`, `memberAccess`, `predicateExpression`, and `statementKeyword` for simple scripts.

### C2 - SELECT and query-expression expectations

Tasks:

1. Add parser-backed expectations for SELECT list, FROM, JOIN, ON, WHERE, GROUP BY, HAVING, ORDER BY, set operators, and subqueries.
2. Gate table/object/column producers by these expectations.
3. Remove broad expression fallback for SELECT-family statements.
4. Add split-keyword recovery behavior so completions after repaired clauses are sane.

Acceptance:

- `SELECT * FROM ` suggests table sources.
- `SELECT * FROM Sales.Orders o WHERE ` suggests predicate-expression items.
- `SELECT * FROM Sales.Orders o JOIN ` ranks FK-adjacent tables first.
- `SELECT * FROM Sales.Orders o ORDER ` suggests `BY` only.
- `SELECT * fr om Sales.Orders` does not show random expression completions in the `fr`/`om` region.

### C3 - DML and EXEC expectations

Tasks:

1. Add expectations for INSERT target, INSERT columns, VALUES, UPDATE target, UPDATE SET, DELETE target, MERGE skeleton.
2. Add EXEC procedure and argument expectations.
3. Preserve existing producer behavior behind explicit expectation gates.
4. Add tests for incomplete metadata and lazy hydration.

Acceptance:

- INSERT and UPDATE tests remain green.
- EXEC named parameter suggestions remain green.
- No table-source suggestions in VALUES or SET RHS unless expression context genuinely allows object-valued functions.

### C4 - DDL and procedural expectations

Tasks:

1. Add declarationName and typeName precision for CREATE TABLE and DECLARE.
2. Add ALTER TABLE action completions.
3. Add module header parameter completions.
4. Parse module bodies as nested statements for normal completions.
5. Suppress noisy completions in unsupported procedural regions.

Acceptance:

- DDL name positions stay silent.
- Type positions suggest types.
- ALTER TABLE action positions suggest actions.
- Stored-procedure body SELECT/JOIN completions work normally.

### C5 - Ranking and advanced polish

Tasks:

1. Add expectation priority into score.
2. Add local MRU accept history, capped and per document.
3. Add alias generation item behind a setting or preview flag.
4. Add candidate explanation debug output for tests.
5. Add lazy documentation resolve for heavy docs.

Acceptance:

- ranking is deterministic.
- FK suggestions stay above generic suggestions.
- snippets do not outrank real symbols unless exact snippet key is typed.

### C6 - Validation and default-readiness review

Tasks:

1. Expand completion fourslash corpus to 150+ cases.
2. Run native-vs-bridge comparison for common contexts.
3. Add perftest scenario for completion latency and result quality counters.
4. Add dogfood feature-capture summaries with counts only.
5. Review incomplete reasons and metadata section readiness behavior.

Acceptance:

- common cases are nearly always high-confidence.
- low-confidence contexts are silent.
- completion p95 stays under budget.

---

## 15. Acceptance matrix

### 15.1 Silence and suppression

| Input | Expected |
|---|---|
| `CREATE TABLE My/*caret*/` | zero items |
| `CREATE TABLE dbo./*caret*/` | zero items |
| `CREATE TABLE My (/*caret*/` | zero items |
| `DECLARE @x/*caret*/` | zero items by default |
| `CREATE PROC dbo.p/*caret*/` | zero items before body/header completion state |
| inside string/comment/SQLCMD | zero items |
| unsupported or untrusted parser recovery region | zero items or minimal legal keyword only, never broad expression set |

### 15.2 Basic correctness

| Input | Expected highlights |
|---|---|
| `SELECT * FROM /*caret*/` | tables, views, TVFs, synonyms, schemas, overlay sources |
| `SELECT * FROM Sales./*caret*/` | Sales objects only |
| `SELECT * FROM FixtureDb./*caret*/` | schemas when current database is hydrated |
| `SELECT o./*caret*/ FROM Sales.Orders o` | Orders columns |
| `SELECT o./*caret*/ FROM Sales.Orders AS o` with alias right of caret | Orders columns |
| `SELECT * FROM Sales.Orders o WHERE /*caret*/` | columns, variables, functions, predicate keywords |
| `SELECT * FROM Sales.Orders o WHERE o./*caret*/` | Orders columns only |
| `SELECT * FROM Sales.Orders o ORDER BY /*caret*/` | select aliases and columns |
| `USE /*caret*/` | database list or incomplete |

### 15.3 Advanced cases

| Input | Expected |
|---|---|
| `SELECT * FROM Sales.Orders o JOIN /*caret*/` | FK-adjacent tables first |
| `... JOIN Sales.Customers c ON /*caret*/` | FK predicate first |
| `INSERT INTO Sales.Orders (/*caret*/` | writable columns, all-columns item |
| `UPDATE o SET /*caret*/ FROM Sales.Orders o` | target columns with assignment scaffold |
| `EXEC Sales.GetOrders @CustomerID = 1, /*caret*/` | remaining params only |
| `CREATE TABLE My (Id i/*caret*/` | type names matching prefix `i` |
| `ALTER TABLE Sales.Orders /*caret*/` | ALTER TABLE actions |

### 15.4 Performance and honesty

- Completion request never awaits live metadata hydration.
- If needed metadata section is loading, return partial/empty with `isIncomplete` where useful.
- If objects are unavailable, do not invent object suggestions.
- If columns are unavailable, do not invent column suggestions.
- If FK metadata is unavailable, join relationship boosts disappear but table source completions still work.
- Telemetry contains expectation kind, item count, incomplete reason, readiness, and duration only.

---

## 16. Performance targets

| Path | Target |
|---|---|
| Warm member access completion | p95 < 2 ms engine time |
| Warm table-source completion | p95 < 5 ms engine time for normal catalogs, capped results |
| FK join predicate suggestion | p95 < 5 ms after metadata is pinned |
| Parser expectation lookup for caret statement | p95 < 2 ms |
| Large document current-statement completion | must not parse the entire document synchronously if cache is stale |
| Metadata not ready | return quickly with incomplete, do not wait |

The current engine has very low warm completion latency in tests. Parser-aware expectations should protect that by reusing cached analysis and parsing only the caret statement when necessary.

---

## 17. Observability and privacy

Add or extend these spans/events through the contracts registry before emitting:

```text
sqlLanguage.completion.request
sqlLanguage.completion.expectation
sqlLanguage.completion.produce
sqlLanguage.completion.rank
sqlLanguage.completion.incomplete
```

Allowed fields:

- expectation kind;
- trigger kind and trigger character category, not raw text;
- item count bucket;
- producer count by producer id;
- incomplete reason;
- metadata readiness states;
- metadata freshness source/freshness states;
- duration buckets;
- result capped boolean;
- suppress reason.

Forbidden fields:

- SQL text;
- prefix text;
- identifier names;
- object names;
- database names;
- string literal content;
- connection strings;
- model prompts or AI content.

### 17.1 Debug-only explanation

For unit tests and local feature capture, add a redacted explanation mode:

```ts
interface CompletionDebugSummary {
    readonly expectationKind: CompletionExpectationKind;
    readonly suppressReason?: CompletionSuppressReason;
    readonly producerCounts: Record<string, number>;
    readonly incompleteReason?: CompletionIncompleteReason;
    readonly capped: boolean;
}
```

Do not include candidate labels in diagnostics. Tests can inspect labels directly in process.

---

## 18. Coding-agent first task list

Start with a narrow, high-value slice:

1. Add `CompletionExpectation` and `CompletionExpectationKind` types.
2. Add `expectationAt` for current parser/sketch with a small compatibility implementation.
3. Change `NativeSqlLanguageEngine.completion` to compute expectation and then call an adapter to existing `computeCompletion`.
4. Add a strict `none/declarationName` path that bypasses all producers.
5. Add tests for declaration-name silence across CREATE TABLE, CREATE PROC, CREATE VIEW, CREATE FUNCTION, DECLARE, and table variable column names.
6. Add expectation tests for SELECT FROM, WHERE, member access, JOIN, EXEC, INSERT, UPDATE, USE.
7. Keep current completion item tests green.
8. Only after this, start parser v2 integration from the problem-detection plan.

---

## 19. Rollout policy

- Keep the existing language-service router and native capability table.
- New expectation-driven completion can remain under native engine preview while behavior is validated.
- Do not add a user setting for every producer. Use internal flags and tests during rollout.
- Route failures through existing circuit breaker.
- Fallback to STS bridge is acceptable while native is preview, but native should not silently ask bridge for metadata or suggestions.
- Default flip should require both quality and latency evidence, not just test count.

---

## 20. Decision

Do not rewrite the completion engine. Make it parser-aware.

The completion service already has valuable producers and metadata integration. The issue is that it sometimes invites the whole orchestra when the score calls for silence. A shared parser expectation API fixes the category decision before ranking, preserves existing advanced features, and gives completions and Problems one grammar truth while keeping their feature-specific policies separate.
