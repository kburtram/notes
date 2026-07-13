# Current Query Studio Problem Parser Design

**Status:** current-state assessment and recommendation.  
**Date:** 2026-07-08.  
**Scope:** Query Studio Problems/squiggles for native TypeScript T-SQL diagnostics.  
**Primary symptom:** typing `fr om` does not produce a syntax error in Problems.

---

## 1. Executive Summary

The current Query Studio Problems implementation is not a full syntax parser. It is a diagnostic pass over a tolerant language-service pipeline:

1. full-fidelity lexer;
2. batch and statement segmenter;
3. statement sketch extractor;
4. script overlay;
5. metadata-aware binder;
6. diagnostics pass with conservative syntax heuristics and binder warnings.

That architecture is a good foundation for completions, hover, definition, and schema warnings. It is not enough for broad syntax-error detection. The current design deliberately avoids false positives by only reporting syntax errors when it is very confident. That policy is why some bad input, including `fr om` in common positions, is missed.

**Recommendation:** do not keep chasing this with many small heuristics. Add one short-term patch for the obvious split-clause keyword cases, then design and build a real native syntax-diagnostics parser component. This should be a focused redesign of the parser/diagnostics layer, not a rewrite of the whole language service. Keep the existing lexer, segmenter, scheduler, router, metadata provider seam, and binder honesty model.

---

## 2. Current User-Visible Flow

Problems in Query Studio flow through these files:

- `extensions/mssql/src/webviews/pages/QueryStudio/app.tsx`
  - Registers Monaco language providers in the webview.
  - Seeds diagnostics once through `QsLangDiagnosticsRequest`.
  - Listens for `QsLangDiagnosticsChangedNotification`.
  - Applies Monaco markers with owner `mssql-sqlLanguage`.
- `extensions/mssql/src/queryStudio/queryStudioController.ts`
  - Creates one `QueryStudioLanguageService` per Query Studio panel/model.
  - Forwards language-service diagnostic changes to the webview.
  - Handles `qs/lang.diagnostics` by calling `languageService.diagnostics()`.
- `extensions/mssql/src/queryStudio/queryStudioLanguageService.ts`
  - Owns the feature router, native engine, STS v1 bridge, and diagnostics scheduler.
  - Schedules native diagnostics after text changes when the diagnostics route is native.
  - Applies `mssql.sqlLanguage.diagnostics.enabled` and `mssql.intelliSense.enableErrorChecking`.
- `extensions/mssql/src/sqlLanguage/host/router.ts`
  - Routes diagnostics to native TypeScript only when the engine preference and capability table allow it.
  - Default setting is still `mssql.queryStudio.languageService.engine = "sqlToolsService"`.
- `extensions/mssql/src/sqlLanguage/host/nativeEngine.ts`
  - Runs lexing, segmentation, sketch parsing, overlay construction, and diagnostics.
- `extensions/mssql/src/sqlLanguage/features/diagnostics.ts`
  - Produces the actual native diagnostic list and suppression counts.

When the engine setting is `sqlToolsService`, diagnostics are pulled from the existing VS Code/mssql diagnostic collection through the bridge. When the engine setting is `nativeTypeScript`, diagnostics come from `features/diagnostics.ts`.

---

## 3. Current Native Pipeline

### 3.1 Lexer

File: `extensions/mssql/src/sqlLanguage/core/lexer.ts`

The lexer is strong and should be kept. It:

- covers every character with tokens, including trivia;
- handles strings, comments, bracketed identifiers, quoted identifiers, temp names, variables, numbers, operators, punctuation, SQLCMD directives, and `GO`;
- marks identifiers with keyword metadata instead of turning them into hard keyword tokens;
- reports unterminated string/comment/identifier tokens through token flags.

Important design choice: keyword-looking text is still an identifier token. Whether `FROM` is a clause, an alias, an object name, or a syntax error is decided later by parser/context code.

### 3.2 Segmenter

File: `extensions/mssql/src/sqlLanguage/core/segmenter.ts`

The segmenter splits:

- batches by `GO` lines;
- statements by top-level semicolons and statement-start keywords;
- module bodies by `CREATE/ALTER ... AS`;
- some continuation patterns like `UNION`, `ELSE`, `WITH ... SELECT`, `INSERT ... SELECT`, `UPDATE ... SET`.

The segmenter is tolerant. Its job is to provide statement units for features, not to validate grammar. Bad statement text still becomes a statement segment whenever possible.

### 3.3 Statement Sketch Parser

Files:

- `extensions/mssql/src/sqlLanguage/core/sketch/index.ts`
- `extensions/mssql/src/sqlLanguage/core/sketch/types.ts`

The sketch parser is a feature-oriented extractor. It records:

- statement kind: `select`, `insert`, `update`, `delete`, `merge`, `declare`, `set`, `exec`, `use`, `createTable`, `moduleHeader`, `ddl`, `procedural`, `other`;
- query scopes;
- clause spans;
- FROM sources;
- select-list items;
- CTEs;
- DML targets;
- EXEC calls;
- table variable/temp table declarations;
- SELECT INTO and CREATE TABLE shapes.

It is intentionally "total": it returns a sketch even for broken or half-written SQL. Recovery is mostly "skip to the next anchor" rather than "create an error node". This is good for completions and hover because incomplete SQL still produces useful context. It is weak for syntax diagnostics because the parser does not preserve a list of expected-token failures.

### 3.4 Script Overlay

File: `extensions/mssql/src/sqlLanguage/core/overlay.ts`

The overlay tracks script-local objects:

- temp tables;
- table variables;
- script-created tables;
- SELECT INTO shapes;
- ALTER TABLE uncertainty.

This is used by completions, hover, definition, and diagnostics so the language service can reason about objects created in the current script without executing the script.

### 3.5 Binder

File: `extensions/mssql/src/sqlLanguage/core/binder.ts`

The binder resolves sources and columns against:

- statement-local CTEs and derived tables;
- overlay objects;
- pinned metadata from the metadata provider;
- system catalog fallback.

It returns suppression reasons instead of guessing. That is a key strength. If metadata is missing, stale, cross-database, ambiguous, or opaque, diagnostics suppress the claim rather than emitting a false warning.

### 3.6 Metadata Provider

Files:

- `extensions/mssql/src/sqlLanguage/provider/types.ts`
- `extensions/mssql/src/sqlLanguage/provider/catalogProvider.ts`
- `extensions/mssql/src/services/metadata/**`

The native engine sees only `ISqlLanguageMetadataProvider` and `IPinnedMetadataView`. It does not import MetadataService or STS2 transport types.

This is the right boundary. MetadataService owns catalog hydration, cache/freshness, STS2/data-plane access, generations, and section readiness. The language service pins one metadata generation per response and degrades honestly when sections are not ready.

### 3.7 Diagnostics

File: `extensions/mssql/src/sqlLanguage/features/diagnostics.ts`

Diagnostics are split into tiers.

**T1 lexical/structural errors:**

- unterminated strings;
- unterminated block comments;
- unterminated bracketed or quoted identifiers;
- invalid `GO` lines;
- unmatched parentheses in certain closed-statement cases;
- duplicate exposed source names in one FROM scope;
- selected "unrecognized statement head" cases.

**T2 binder warnings:**

- invalid object name, 208-style;
- invalid column name, 207-style;
- ambiguous column name, 209-style.

T2 warnings are guarded by the suppression ladder. They are disabled when metadata freshness cannot be validated, when the selected database does not match hydrated metadata, when object/column sections are not ready, or when the syntax shape is not trustworthy.

---

## 4. Why `fr om` Is Missed

There are two likely user cases.

### 4.1 `fr om` as a statement

Text:

```sql
fr om
```

The lexer produces two identifiers: `fr` and `om`. The sketch kind is `other`. The diagnostics pass checks unknown statement heads but is intentionally conservative:

- it flags `SEL ECT * FROM x` because `SEL` + `ECT` joins into statement-start keyword `SELECT`, and the later `FROM` is a betrayal word;
- it suggests statement-start keywords only;
- `FROM` is not a statement-start keyword. It is a clause keyword.

So `fr om` is treated as a possible incomplete or EXEC-less procedure invocation and remains silent.

### 4.2 `fr om` inside a SELECT

Text:

```sql
select * fr om dbo.T
```

The sketch parser sees `SELECT`, then scans the select list until it finds a real clause starter token. Because `fr` and `om` are identifiers, not a `FROM` keyword, they remain inside the select-list span. No FROM clause is recorded. The binder has no source table to check, and the current syntax tier has no production that says "after a select list, this looks like a split FROM clause".

So there is no lexical error, no grammar production error, and no binder warning.

This is not a Monaco/Problems publishing bug. It is a parser-diagnostics coverage gap.

---

## 5. Strengths of the Current Design

The current implementation should not be discarded wholesale.

**Good foundations:**

- The lexer is total, deterministic, and already handles important T-SQL token edge cases.
- The segmenter is aligned with Query Studio execution splitting for `GO`.
- The language engine is pure and testable.
- The metadata seam is clean and does not leak MetadataService or STS2 concerns into parser code.
- The router supports per-feature rollout and fallback.
- The scheduler already supports whole-document diagnostics without blocking the UI.
- The binder's suppression ladder is the right model for semantic/schema diagnostics.
- Diagnostic telemetry avoids document text and identifiers by default.

These pieces are compatible with a better parser.

---

## 6. Current Limitations

### 6.1 No Real Grammar

The sketch parser extracts useful spans but does not enforce productions. It does not have rules like:

- `SELECT <select_list> [FROM <source_list>] [WHERE <expr>] ...`;
- `FROM` must be a single clause keyword token;
- `GROUP` must be followed by `BY`;
- `ORDER` must be followed by `BY`;
- `JOIN` must have a following source;
- `ON` must follow a join;
- `WHERE` cannot appear before `FROM` in a normal SELECT.

Some of these cases happen to be caught later by binder logic, but there is no consistent syntax-error model.

### 6.2 No Expected-Token Diagnostics

The parser does not keep an expected-token set at failure points. Therefore it cannot reliably say:

- "expected FROM";
- "expected BY after ORDER";
- "expected table source after JOIN";
- "expected expression after WHERE";
- "unexpected FROM in select list";
- "unexpected clause keyword here".

Instead, diagnostics rely on a small set of hand-written confidence checks.

### 6.3 No Error Nodes

The sketch parser recovers by skipping, not by producing structured error nodes. That means the diagnostics pass must rediscover syntax mistakes from token patterns after the fact.

A proper syntax diagnostics component should produce recoverable parse errors as part of parsing, while still returning a usable AST/sketch for completions.

### 6.4 Unknown-Head Heuristic Is Too Narrow

The current unknown-head check is designed to avoid false positives for EXEC-less procedure calls:

```sql
sp_help Orders
Sales.GetOrders @CustomerID = 1
myproc @a = 1
```

That is a good constraint, but the current heuristic mainly catches statement-start typos. It does not catch clause-keyword splits such as:

- `fr om`;
- `wh ere`;
- `gr oup by`;
- `ord er by`;
- `jo in`;
- `ha ving`;
- `un ion`.

### 6.5 Statement Sketch Can Misclassify Bad Text as Valid Shape

Because the sketch parser is tolerant, invalid text may become:

- a select-list alias;
- an expression span;
- an opaque source;
- an unknown statement;
- a possible procedure call.

That is acceptable for completions, but diagnostics need a separate "this shape was only recovered, and here is why" channel.

### 6.6 Metadata Warnings Are Better Than Syntax Errors Today

The current binder warnings are more mature than syntax diagnostics. Invalid object and column cases are covered by many tests and use metadata readiness correctly. Syntax diagnostics are intentionally much smaller.

This matters for the product promise. The package setting says native diagnostics publish "syntax errors and schema warnings". Today that is only partially true: schema warnings are relatively well designed; syntax errors are a curated subset.

### 6.7 Bridge Path Is Not a Fix

The STS v1 bridge reads diagnostics from the existing `mssql` diagnostic collection. It can help preserve old behavior, but it does not solve native parser quality:

- it is not integrated with the new metadata service and overlay model;
- it depends on shadow connection state;
- it is not a pure language-service component;
- it cannot be the final Query Studio native architecture if we want rich diagnostics, replay, and metadata-aware honesty.

---

## 7. Minor-Fix Option

A small patch can improve the immediate `fr om` class of bugs:

1. Add split-clause keyword detection.
2. Run it inside known statement contexts, especially SELECT clause scanning.
3. Add focused tests for:
   - `select * fr om Sales.Orders`;
   - `select * from Sales.Orders wh ere OrderID = 1`;
   - `select * from Sales.Orders ord er by OrderID`;
   - `fr om` as a top-level statement, if we decide clause-only typos should be reported.
4. Keep EXEC-less procedure-call protections.

That patch is worth doing because it is user-visible and low-risk if scoped narrowly.

But this approach will not scale. Every new syntax family would need another heuristic. It will produce inconsistent behavior: one typo reports, a nearby typo silently passes, and the team keeps debating individual examples instead of improving the parser model.

---

## 8. Full Parser Recommendation

Build a native TypeScript syntax-diagnostics parser component.

This should be a focused addition under the existing language-service tree, for example:

```text
extensions/mssql/src/sqlLanguage/core/parser/
  parser.ts
  ast.ts
  diagnostics.ts
  recovery.ts
  productions/
    select.ts
    dml.ts
    exec.ts
    ddl.ts
    procedural.ts
```

The parser should reuse:

- `core/lexer.ts` tokens;
- `core/segmenter.ts` batch/statement boundaries;
- `core/text/textSnapshot.ts` position mapping;
- `host/scheduler.ts` sliced diagnostics execution;
- `provider/types.ts` metadata provider seam;
- current binder suppression model for semantic diagnostics.

It should replace or augment `core/sketch` over time. The safest transition is:

1. new parser produces an AST plus syntax diagnostics;
2. a compatibility projection converts AST to the current `StatementSketch`;
3. existing completion/hover/definition/binder code keeps working;
4. once stable, feature modules can consume richer AST nodes directly.

### 8.1 Parser Output

The parser should return:

```ts
interface ParsedDocument {
    readonly batches: readonly ParsedBatch[];
    readonly statements: readonly ParsedStatement[];
    readonly syntaxDiagnostics: readonly ParserDiagnostic[];
    readonly recoveryStats: ParserRecoveryStats;
}

interface ParserDiagnostic {
    readonly range: SqlLanguageRange;
    readonly severity: "error" | "warning";
    readonly code?: string; // usually mssql(102) for syntax
    readonly message: string;
    readonly kind:
        | "unexpectedToken"
        | "missingToken"
        | "splitKeyword"
        | "misorderedClause"
        | "unclosedConstruct"
        | "unsupportedSyntax";
    readonly confidence: "certain" | "probable" | "midEditSuppressed";
}
```

The exact shape can vary, but it needs these properties:

- diagnostics are produced during parsing, not rediscovered later;
- every diagnostic has a recovery decision;
- mid-edit suppressions are explicit and countable;
- no diagnostic telemetry contains SQL text or identifiers.

### 8.2 Recovery Model

The parser should be tolerant, but it should recover through structured rules:

- statement boundaries from the segmenter;
- clause synchronizers: `SELECT`, `FROM`, `WHERE`, `GROUP`, `HAVING`, `ORDER`, `OPTION`, `UNION`, `EXCEPT`, `INTERSECT`, `JOIN`, `ON`;
- parenthesis balancing;
- comma-list recovery;
- keyword-pair recovery (`GROUP BY`, `ORDER BY`);
- split-keyword recovery for reserved statement and clause keywords.

This lets the parser emit a useful error and still produce enough structure for completions.

### 8.3 Syntax vs Binder Responsibilities

Syntax parser responsibilities:

- malformed keywords and split keywords;
- missing required tokens;
- illegal clause order;
- malformed clause pairs;
- unexpected punctuation;
- unmatched delimiters;
- grammar-level statement errors.

Binder responsibilities:

- object existence;
- column existence;
- column ambiguity;
- alias/source resolution;
- metadata-readiness suppression;
- cross-database/linked-server/system-object honesty.

Do not push syntax errors into the binder. Do not make metadata availability affect pure syntax diagnostics.

### 8.4 Metadata and STS2 Integration

The parser itself should not call MetadataService or STS2. It should remain pure.

The binder and semantic diagnostics should continue to use the existing metadata provider seam:

```text
Parser AST/sketch
  -> Binder
      -> IPinnedMetadataView
          -> CatalogLanguageMetadataProvider
              -> MetadataService
                  -> STS2/data-plane metadata hydration
```

Metadata section readiness remains important for 207/208/209 warnings. It should not suppress certain syntax errors such as `fr om`.

### 8.5 SQL Parser / ScriptDOM Role

Using a server-side SQL Parser or ScriptDOM-like component as the primary hot-path parser is not the best fit for Query Studio's webview language service:

- it is cross-process and harder to keep interactive;
- it is not naturally tolerant for half-written editor text;
- it does not know Query Studio overlay objects, current metadata generation, or suppression policy;
- it complicates packaging and versioning;
- it would make diagnostics less inspectable in the existing TypeScript test lane.

However, it would be useful as an oracle:

- build an offline corpus runner comparing native syntax diagnostics against SQL Server/ScriptDOM parse results;
- use disagreements to add tests;
- do not block the editor on that parser.

If high-fidelity validation is required, an STS2 parse endpoint could run in the background or in tests, but the interactive component should remain native TypeScript.

---

## 9. Proposed Implementation Plan

### Phase P0 - Lock Current Behavior and Add Repro Tests

Add tests documenting the current misses and desired behavior:

- `fr om`;
- `select * fr om Sales.Orders`;
- `select * from Sales.Orders wh ere OrderID = 1`;
- valid EXEC-less procedure calls;
- valid aliases that look keyword-ish when quoted or bracketed;
- mid-edit cases that should stay quiet.

This phase can include a narrow `fr om` fix if needed immediately.

### Phase P1 - Parser Infrastructure

Add:

- token cursor utilities;
- parser context and expected-token tracking;
- recoverable diagnostic collector;
- clause synchronizer sets;
- AST node ranges;
- compatibility projection to `StatementSketch`.

Keep existing tests green by initially projecting the same sketches.

### Phase P2 - SELECT and Query Expression Grammar

Implement structured grammar for:

- `SELECT`;
- `TOP`;
- select lists;
- `INTO`;
- `FROM` sources;
- joins and `ON`;
- `WHERE`;
- `GROUP BY`;
- `HAVING`;
- `ORDER BY`;
- set operators;
- subqueries and derived tables;
- CTE prologues.

This phase should close the `fr om` family.

### Phase P3 - DML, EXEC, DDL, and Procedural Coverage

Add parser coverage for:

- INSERT;
- UPDATE;
- DELETE;
- MERGE skeleton;
- EXEC and EXEC-less procedure-call detection;
- DECLARE;
- SET;
- USE;
- CREATE/ALTER/DROP table/module headers;
- BEGIN/END, TRY/CATCH, IF/ELSE, WHILE, RETURN, THROW, RAISERROR.

The goal is not full SQL Server grammar parity yet. The goal is consistent syntax diagnostics for common editor mistakes while preserving tolerance.

### Phase P4 - Diagnostics Integration

Update `features/diagnostics.ts` so:

- lexical diagnostics still come from lexer token flags;
- parser syntax diagnostics come from `ParsedDocument.syntaxDiagnostics`;
- binder warnings still run on the projected sketch/AST;
- suppression counts include parser mid-edit suppressions and recovery counts;
- the >100 diagnostics breaker still applies.

### Phase P5 - Validation and Default Decision

Add:

- corpus comparison against existing SQL Parser/ScriptDOM results where available;
- false-positive dogfood suite;
- performance benchmark for large scripts;
- feature-capture summaries with counts only;
- language status output that separates syntax diagnostics from binder diagnostics.

Only after this should native diagnostics be considered more than preview quality.

---

## 10. Acceptance Criteria

The improved component should satisfy:

- `select * fr om Sales.Orders` reports a syntax error near `fr om`.
- `select * from Sales.Orders wh ere OrderID = 1` reports a syntax error near `wh ere`.
- `select * from Sales.Orders order OrderID` reports expected `BY`.
- `select * from Sales.Orders where` is suppressed or marked mid-edit while the user is still typing, but reports once the statement is clearly closed.
- EXEC-less procedure calls remain clean unless metadata proves the procedure is missing.
- Valid scripts in the current honesty corpus remain clean.
- 207/208/209 warnings keep using metadata readiness and suppression.
- Diagnostics spans/logs contain counts, kinds, durations, readiness, and suppression reasons only.
- Warm diagnostic passes stay within the current scheduler model and do not block completion/hover hot paths.

---

## 11. Decision

Short term: add a small split-clause keyword diagnostic to reduce immediate pain.

Medium term: build the proper parser component. The current system is not "just buggy"; it is doing what it was designed to do, but the design is not broad enough for reliable Problems detection. Minor revisions will keep improving isolated examples, but they will not produce a coherent syntax-error feature.

The right investment is a parser redesign inside the native TypeScript language service, reusing the existing lexer, segmenter, metadata provider, router, scheduler, and binder. That gives Query Studio a real, testable, metadata-aware, privacy-safe problem parser without throwing away the language-service work that already exists.
