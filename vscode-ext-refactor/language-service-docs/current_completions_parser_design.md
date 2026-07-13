# Current Query Studio Completions Parser Design

**Status:** current-state assessment, local fix note, and recommendation.  
**Date:** 2026-07-08.  
**Scope:** Query Studio native TypeScript non-AI completions.  
**Primary symptom:** in `CREATE TABLE My`, the completion window offered unrelated keywords/functions such as `MODIFY` and `JSON_MODIFY`, even though the user was typing a net-new symbol.

---

## 1. Executive Summary

The native completion engine is more mature than the current Problems/syntax-diagnostics path for metadata-aware scenarios. It already has:

1. a full-fidelity lexer;
2. a batch/statement segmenter;
3. a tolerant statement sketch parser;
4. a script overlay for CTEs, temp tables, table variables, and script-created objects;
5. a binder over pinned metadata;
6. a cursor context classifier;
7. per-context candidate producers and deterministic ranking.

That is enough for many useful completion cases: alias columns, `sys.` member access, `FROM` sources, FK-aware joins, INSERT column lists, UPDATE SET targets, EXEC parameters, USE databases, snippets, keywords, and system catalog objects.

It is not enough for every editor position. The current context classifier often knows the nearest clause, but it does not know the grammar expectation at the caret. When it cannot prove a specific context, it falls back to a generic expression/body context. That fallback is what caused `CREATE TABLE My` to show `MODIFY` and `JSON_MODIFY`: `My` was treated as an expression prefix, and fuzzy matching found unrelated words.

**Recommendation:** completion improvements and problem-parser improvements should share one parser front-end. Do not build two separate grammars. The right medium-term feature is a proper native parser plus a cursor expectation API that serves both diagnostics and completions. Short term, keep fixing isolated high-confidence cases with narrow guards. The `CREATE TABLE` declaration-symbol case has been fixed locally by suppressing completions in known declaration-symbol positions.

---

## 2. Current User-Visible Flow

Completion requests flow through these files:

- `extensions/mssql/src/webviews/pages/QueryStudio/app.tsx`
  - Registers Monaco's completion item provider for the webview `sql` language.
  - Trigger characters are `.`, space, `@`, and `(`.
  - Adds a short stale-state delay for trigger characters other than `.`.
  - Flushes pending edits before calling the host.
  - Sends `QsLangCompletionRequest` with line, character, text hash, trigger kind, and trigger character.
  - Maps returned items into Monaco completion items, including `replaceRange`, snippets, details, docs, sort text, filter text, and commit characters.

- `extensions/mssql/src/queryStudio/queryStudioController.ts`
  - Handles `qs/lang.completion`.
  - Calls `QueryStudioLanguageService.completion(...)`.

- `extensions/mssql/src/queryStudio/queryStudioLanguageService.ts`
  - Applies the IntelliSense suggestions gate.
  - Ensures metadata freshness under `MetadataPolicies.completion`.
  - Routes through the language-service router.

- `extensions/mssql/src/sqlLanguage/host/router.ts`
  - Routes completion to the native engine when the effective engine and capability table allow it.
  - Completion is a preview-capable native feature.

- `extensions/mssql/src/sqlLanguage/host/nativeEngine.ts`
  - Reuses the document analysis cache.
  - Suppresses automatic whitespace-triggered completions in known empty-space cases.
  - Pins the metadata view for one request.
  - Binds the statement and classifies the caret context.
  - Calls `computeCompletion`.
  - Emits diagnostic spans with context kind, counts, readiness, incomplete state, and privacy-classified fields.

---

## 3. Current Native Pipeline

### 3.1 Lexing and Segmentation

Files:

- `extensions/mssql/src/sqlLanguage/core/lexer.ts`
- `extensions/mssql/src/sqlLanguage/core/segmenter.ts`

The lexer and segmenter are shared with diagnostics, hover, signature help, definition, folding, and symbols.

The lexer is total and full-fidelity. It produces tokens for identifiers, quoted names, bracketed names, temp names, variables, strings, comments, SQLCMD directives, punctuation, operators, `GO`, and trivia.

The segmenter splits batches and statements. It understands `GO`, statement-start keywords, semicolons, module-body transitions, and selected statement continuation patterns.

These layers are good foundations and should remain shared.

### 3.2 Sketch Parser

Files:

- `extensions/mssql/src/sqlLanguage/core/sketch/index.ts`
- `extensions/mssql/src/sqlLanguage/core/sketch/types.ts`

The sketch parser is tolerant and total. It records feature-oriented facts, not a full AST:

- statement kind;
- query scopes;
- clause spans;
- FROM sources;
- select items and aliases;
- CTEs;
- DECLARE variables and table variables;
- DML targets;
- INSERT column lists;
- EXEC procedure and argument spans;
- USE target;
- CREATE/ALTER TABLE overlay facts;
- SELECT INTO overlay facts.

For completion, this is useful because it gives the binder enough structure to answer "what sources and columns are visible here?" It is not enough to answer every "what token category is expected here?" question.

### 3.3 Overlay

File: `extensions/mssql/src/sqlLanguage/core/overlay.ts`

The overlay exposes script-local symbols:

- CTEs;
- temp tables;
- table variables;
- script-created tables;
- SELECT INTO outputs;
- dropped objects;
- ALTER'd object shape distrust.

Completions use this to offer local objects and columns before or alongside catalog metadata.

### 3.4 Binder

File: `extensions/mssql/src/sqlLanguage/core/binder.ts`

The binder resolves the sketch against the overlay and pinned metadata. It supports:

- source aliases;
- source lookup to the right of the caret;
- unqualified and qualified column visibility;
- derived table and CTE columns;
- INSERT/UPDATE target columns;
- case-sensitive matching;
- suppression reasons when metadata is incomplete or unsafe.

This is one of the strongest parts of the current completion implementation.

### 3.5 Context Classifier

File: `extensions/mssql/src/sqlLanguage/core/context.ts`

The classifier maps the caret offset to a `CompletionContext`:

- `none`
- `statementStart`
- `memberAccess`
- `tableSource`
- `joinPredicate`
- `expression`
- `insertColumnList`
- `updateSetTarget`
- `execProcedure`
- `execArgs`
- `declareType`
- `useDatabase`

After the local fix, `none` also has a `declarationSymbol` reason for known CREATE TABLE declaration-symbol positions.

This classifier is the current "completion parser" in practice. It uses token position, sketch kind, clause spans, and local token patterns. It is not a grammar parser and does not maintain a complete expected-token set.

### 3.6 Candidate Production and Ranking

File: `extensions/mssql/src/sqlLanguage/features/completion.ts`

`computeCompletion` takes the classified context and emits candidates:

- statement keywords and default SQL Tools Service keyword text;
- snippets;
- member-access columns or schema objects;
- table/view/table-function/synonym sources;
- schemas;
- FK-adjacent JOIN tables;
- FK JOIN predicates;
- visible columns;
- variables;
- built-in functions;
- expression keywords;
- SELECT star expansion;
- INSERT column-list scaffolds;
- UPDATE SET column assignments;
- EXEC procedures and remaining parameters;
- DECLARE types;
- USE databases.

Ranking is deterministic. Items get a fuzzy-match score, a kind priority, and optional context boosts. Snippets intentionally sort below keywords. The result is capped at `MAX_ITEMS`, with `isIncomplete` used for honest retrigger cases.

### 3.7 Metadata Provider

Files:

- `extensions/mssql/src/sqlLanguage/provider/types.ts`
- `extensions/mssql/src/sqlLanguage/provider/catalogProvider.ts`
- `extensions/mssql/src/services/metadata/**`

The native engine sees only `IPinnedMetadataView` and related provider interfaces. `MetadataService` owns STS2/data-plane hydration, readiness, and snapshot generations.

Completions must never block on metadata hydration. If data is not ready, they return empty or partial honest results and mark the response incomplete where retriggering can help.

---

## 4. Why `CREATE TABLE My` Was Wrong

Text:

```sql
CREATE TABLE My
```

The lexer produces identifiers/keywords for `CREATE`, `TABLE`, and `My`.

The sketch parser recognizes the statement as `createTable` and records `My` as a created table name. It does not create a grammar expectation saying "the user is currently declaring a symbol; suggestions should be empty."

The context classifier had no special CREATE TABLE declaration-symbol state. With no clause and no statement-start position, it fell back to:

```text
expression, clause=body, prefix=My
```

The completion engine then added expression candidates:

- built-in functions;
- expression keywords;
- default SQL keyword text.

The fuzzy matcher accepted unrelated items whose filter text matched the typed prefix well enough, such as `MODIFY` and `JSON_MODIFY`. Monaco then displayed a noisy popup in a position where no useful prediction exists.

This was not a metadata bug. It was not a Monaco mapping bug. It was a missing context classification for declaration-symbol positions.

---

## 5. Local Fix Applied

The local fix adds a narrow guard in:

```text
extensions/mssql/src/sqlLanguage/core/context.ts
```

For `CREATE TABLE` statements, the classifier now returns:

```text
none, reason=declarationSymbol
```

in these positions:

- after `CREATE TABLE` where an object name is being typed;
- after a schema qualifier in `CREATE TABLE dbo.`;
- at the start of the CREATE TABLE column list where a new column name is being typed.

Regression coverage was added in:

```text
extensions/mssql/test/unit/sqlLanguageCompletion.test.ts
```

New focused cases:

- `CREATE TABLE My/*caret*/` returns zero items;
- `CREATE TABLE dbo./*caret*/` returns zero items;
- `CREATE TABLE My (/*caret*/` returns zero items.

This is intentionally narrow. It stops the bad popup from the screenshot without pretending the engine has a full DDL completion grammar.

---

## 6. Strengths of the Current Completion Design

The completion engine should not be discarded.

**Strong areas:**

- The request path is cleanly routed through Query Studio RPC and the language-service router.
- The native core is pure TypeScript and testable without VS Code APIs.
- The lexer and segmenter are shared foundations.
- The sketch parser already extracts enough structure for many metadata-aware completions.
- The binder is good at alias/source/column resolution.
- Metadata readiness is explicit and honest.
- `sys.` and `INFORMATION_SCHEMA.` use the static system catalog when live metadata is not enough.
- Completion does not perform network I/O on the keystroke path.
- Ranking is deterministic and tested.
- The unit suite already covers many real completion contexts.

This is a solid LS-1 implementation. Its main weakness is not the metadata side; it is grammar expectation at the caret.

---

## 7. Current Limitations

### 7.1 No General Expected-Position Model

The classifier returns broad contexts such as `expression` or `tableSource`. It does not return a structured expected position such as:

- declaration symbol;
- type name;
- table source;
- object member;
- column expression;
- value expression;
- statement keyword;
- clause keyword;
- no suggestion.

Without this, the engine must guess from local tokens and clause spans.

### 7.2 Generic Expression Fallback Is Too Broad

The final fallback is:

```text
expression, clause=body
```

That fallback adds columns, variables, built-ins, expression keywords, and sometimes default keywords. It is useful inside real expressions. It is noisy in DDL, procedural bodies, and malformed statements where the engine has not identified a better context.

The `CREATE TABLE My` bug came from this fallback.

### 7.3 DDL Coverage Is Thin

The sketch parser recognizes CREATE/ALTER TABLE primarily for overlay construction. It does not model the DDL grammar enough to know all useful completion positions:

- object declaration name;
- column declaration name;
- column type;
- table constraints;
- `ALTER TABLE ... ADD/DROP/ALTER`;
- index options;
- `CREATE PROC` parameter declarations;
- `CREATE VIEW AS SELECT`;
- module body transitions.

The local fix handles the most harmful declaration-symbol popup. It does not make DDL completions complete.

### 7.4 Completion Contexts and Diagnostics Parse Differently

Diagnostics and completions share lexer, segmenter, sketch, binder, and metadata. But their actual "what is wrong / what is expected here" logic is split:

- diagnostics uses `features/diagnostics.ts` heuristics;
- completions uses `core/context.ts` plus `features/completion.ts`.

This leads to drift. A position can be unknown to diagnostics and over-suggestive to completions for the same underlying reason: the shared parser did not record enough grammar state.

### 7.5 No Error Nodes or Recovery Decisions

The sketch parser recovers by scanning to anchors and collecting useful spans. It does not produce structured recoverable parse nodes such as:

- missing token;
- unexpected token;
- split keyword;
- declaration name expected;
- type expected;
- clause order violation.

Completions would benefit from the same recovery model diagnostics need. At a recovery point, the engine should know whether to suggest a keyword, an object, a column, a type, or nothing.

### 7.6 Fuzzy Matching Can Amplify Bad Contexts

The fuzzy matcher is useful in the right context. For example, it lets `sys.aun` find `allocation_units`.

In the wrong context, fuzzy matching makes noise look smart. If the context falls back to expression and the user types a new symbol, unrelated candidates can match as ordered subsequences.

The fix is not to weaken fuzzy matching globally. The fix is to classify the context correctly before candidate generation.

### 7.7 Trigger Policy Is Not Enough

The webview already has trigger-character delay and the native engine suppresses some automatic whitespace completions. That helps with popup timing and empty-space cases.

It cannot solve grammar-specific noise. Explicit Ctrl+Space and typed-prefix triggers still need a correct "what kind of thing belongs here?" answer.

---

## 8. Relationship to the Problem Parser

This is overlapped with the problem-parser work.

The two features need different outputs:

- Problems need syntax diagnostics, severity, spans, messages, suppression counts, and recovery stats.
- Completions need a fast cursor expectation, candidate category, binder scope, allowed keyword set, metadata query shape, replacement range, and incomplete reason.

But they should not have separate grammars. Both should consume the same parser front-end:

```text
lexer
  -> segmenter
      -> parser AST/recovery
          -> syntax diagnostics
          -> completion expectation at caret
          -> binder projection
          -> hover/definition/signature support
```

The parser should be shared; the feature-specific adapters should remain separate.

---

## 9. Recommended Parser Direction

Build the parser component proposed in `current_problem_parser_design.md`, but explicitly include a completion expectation API.

Example shape:

```ts
interface ParsedDocument {
    readonly batches: readonly ParsedBatch[];
    readonly statements: readonly ParsedStatement[];
    readonly syntaxDiagnostics: readonly ParserDiagnostic[];
    readonly recoveryStats: ParserRecoveryStats;
}

interface CompletionExpectation {
    readonly kind:
        | "none"
        | "statementKeyword"
        | "clauseKeyword"
        | "tableSource"
        | "memberAccess"
        | "columnExpression"
        | "valueExpression"
        | "typeName"
        | "databaseName"
        | "procedureName"
        | "procedureArgument"
        | "declarationSymbol";
    readonly scopeId: number;
    readonly prefix: string;
    readonly qualifier?: readonly string[];
    readonly allowedKeywords?: readonly string[];
    readonly suppressReason?: string;
}
```

The parser should expose:

```ts
function expectationAt(document: ParsedDocument, offset: number): CompletionExpectation;
```

The completion feature should then map expectation kinds to candidate producers:

- `statementKeyword` -> statement/default keywords and snippets;
- `clauseKeyword` -> only legal clause keywords for this grammar state;
- `tableSource` -> metadata/overlay table sources and schemas;
- `memberAccess` -> columns or schema/database members;
- `columnExpression` -> visible columns, variables, built-ins, expression keywords;
- `valueExpression` -> variables, built-ins, expression keywords, parameters;
- `typeName` -> type keywords and user-defined types when metadata supports them;
- `databaseName` -> database list;
- `procedureName` -> procedures;
- `procedureArgument` -> remaining params and variables;
- `declarationSymbol` -> no suggestions unless a future name-template feature exists;
- `none` -> no suggestions.

This gives completions a principled "blank is correct" answer.

---

## 10. What To Lump Together vs Keep Separate

### Lump Together

Build these once and share them:

- real parser front-end;
- AST/ranges;
- recovery model;
- expected-token tracking;
- cursor expectation API;
- compatibility projection to `StatementSketch`;
- parser corpus and SQL Parser/ScriptDOM oracle comparison;
- telemetry counters for parser recovery and expectation kinds.

### Keep Separate

Keep these feature-specific:

- completion candidate producers;
- completion ranking;
- snippet policy;
- metadata hydration kick policy;
- diagnostics severity/message/code policy;
- diagnostics suppression ladder;
- Monaco trigger/delay policy;
- feature-specific tests and acceptance criteria.

In short: one parser, separate feature adapters.

---

## 11. Short-Term Fix Plan

Short-term completion fixes should be narrow and context-backed:

1. Add `none/declarationSymbol` for other obvious declaration sites:
   - `CREATE PROC name`;
   - `CREATE VIEW name`;
   - `CREATE FUNCTION name`;
   - `DECLARE @variable` variable-name position;
   - table-variable column declaration names.
2. Add tests for every no-suggestion context.
3. Avoid global fuzzy-match changes.
4. Avoid broad suppression in all DDL; suppress only when the parser/context is confident that a net-new symbol is being declared.
5. Prefer explicit context kinds over ad hoc filters inside `computeCompletion`.

The `CREATE TABLE` screenshot fix is the first example of this policy.

---

## 12. Medium-Term Implementation Plan

### Phase C0 - Stabilize Current Completion Behavior

Add targeted tests around:

- no suggestions for declaration symbols;
- no suggestions in blank expression whitespace when no useful context exists;
- legal keyword suggestions at statement start;
- legal clause suggestions after SELECT list;
- object suggestions only in table-source/member contexts;
- columns only when source/binder context supports them.

### Phase C1 - Parser Expectation Infrastructure

Extend the parser work with:

- token cursor utilities;
- expected-token tracking;
- parser recovery nodes;
- `CompletionExpectation`;
- expectation lookup by offset;
- compatibility projection to current `CompletionContext`.

Initially, the expectation API can feed the existing `CompletionContext` union so candidate generation remains stable.

### Phase C2 - SELECT and Query Expressions

Make completion expectations precise for:

- SELECT list;
- `FROM`;
- joins;
- `ON`;
- `WHERE`;
- `GROUP BY`;
- `HAVING`;
- `ORDER BY`;
- set operators;
- subqueries and derived tables.

This should also improve Problems for split-clause cases like `fr om`.

### Phase C3 - DML and EXEC

Make expectations precise for:

- INSERT target and column list;
- VALUES;
- UPDATE target and SET assignments;
- DELETE target and FROM;
- MERGE skeleton;
- EXEC procedure names;
- EXEC named parameters and values.

### Phase C4 - DDL and Procedural

Add enough DDL/procedural grammar for honest completions:

- declaration-symbol positions stay silent;
- type positions suggest types;
- ALTER TABLE action positions suggest valid actions;
- module header parameter type positions suggest types;
- module body uses normal statement parsing.

### Phase C5 - Validation and Default Decision

Validate with:

- focused unit tests;
- dogfood session journals;
- feature-capture summaries;
- perftest completion latency scenario;
- native-vs-bridge comparison where bridge behavior is still useful.

---

## 13. Acceptance Criteria

The improved completion parser should satisfy:

- `CREATE TABLE My` does not show unrelated keyword/function suggestions.
- `CREATE TABLE dbo.` stays silent rather than listing existing schema objects.
- `CREATE TABLE My (` stays silent for a new column name.
- `CREATE TABLE My (Id i` suggests type names, not expression keywords.
- `SELECT * FROM ` suggests table sources.
- `SELECT * FROM sys.` suggests system objects only.
- `SELECT * FROM sys.all` uses ordered-subsequence matching within system objects.
- `SELECT * FROM Sales.Orders o WHERE o.` suggests columns only.
- `SELECT * FROM Sales.Orders o WHERE ` suggests columns/variables/expression helpers, not table sources.
- `SELECT * FROM Sales.Orders o JOIN ` ranks FK-adjacent tables first.
- `EXEC ` suggests procedures.
- `EXEC Sales.GetOrders ` suggests remaining parameters and variables.
- `GO` at statement start ranks `GO` first.
- Blank space after complete statements stays silent on automatic whitespace trigger.
- Snippets sort below keywords.
- Completion requests never await metadata hydration.
- Metadata-incomplete cases return honest empty/partial results with `isIncomplete` where useful.

---

## 14. Decision

Completions are in better shape than Problems for metadata-aware editor help, but they are not in good enough shape for grammar-sensitive contexts. The bad `CREATE TABLE My` popup is the same architectural smell as missing `fr om` diagnostics: the current parser does not expose enough grammar state.

Do not rewrite completions separately. Build a shared parser with a cursor expectation API and let completions and Problems consume it through separate adapters.

In the meantime, keep applying narrow fixes for high-confidence contexts where showing nothing is clearly better than guessing. The local `CREATE TABLE` declaration-symbol suppression is one of those fixes.
