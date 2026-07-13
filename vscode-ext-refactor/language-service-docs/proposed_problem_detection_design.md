# Query Studio Native T-SQL Problem Detection: Parser v2 Design
## Proposed design updates for syntax diagnostics, semantic warnings, recovery, testability, and observability

**Status:** proposed implementation design for `dev/query`.

**Scope:** non-AI native TypeScript language-service diagnostics for Query Studio, with a parser substrate shared by completions, hover, definition, folding, symbols, and future semantic tokens.

**Primary inputs:** `current_problem_parser_design.md`, `current_completions_parser_design.md`, `05-tsql-language-service-design.md`, the metadata substrate review pack, and the current `dev/query` source shape.

**Core recommendation:** keep the lexer, segmenter, metadata provider seam, overlay, binder honesty model, router, and scheduler. Add a real parser layer that produces error nodes, expected-token facts, recovery decisions, and a compatibility projection back to the current `StatementSketch`. Do not keep adding one-off syntax heuristics as the main plan.

---

## 0. Executive summary

The current problem detector is intentionally conservative. That was the correct first implementation posture: a bad squiggle on valid SQL is worse than silence. It now needs a stronger parser because common invalid SQL can pass through the tolerant sketch pipeline as plausible but opaque text. The visible example is `fr om`: the lexer correctly sees two identifiers, the sketch parser stays tolerant, and diagnostics do not have a production that says the SELECT grammar expected a single `FROM` clause token.

The fix is not a separate diagnostics grammar. Completions are failing in the same class of places, just with the opposite symptom: they sometimes suggest too much instead of reporting too little. Both features need one shared parser front-end that can answer two related questions:

```text
Diagnostics: what was syntactically invalid, where did recovery happen, and how confident are we?
Completions: what token category is expected at the caret, and is silence the correct answer?
```

The design below introduces `core/parser/**` as a focused addition inside the existing TypeScript language service:

```text
lexer
  -> segmenter
      -> parser v2 AST + error nodes + recovery facts
          -> StatementSketch projection, for current binder compatibility
          -> syntax diagnostics adapter
          -> completion expectation adapter
          -> binder and semantic diagnostics
```

The initial parser does not need to implement every corner of T-SQL. It needs to be excellent for normal query authoring: SELECT, joins, predicates, GROUP/ORDER, INSERT, UPDATE, DELETE, EXEC, DECLARE, USE, common CREATE/ALTER headers, module bodies, and enough CREATE TABLE to serve overlay, completions, and diagnostics. Exotic constructs should produce an `unsupported` or `opaque` node, not a speculative diagnostic.

Tiny goblin rule: the parser may squint, but it must not hallucinate. If it cannot prove an error, it records recovery and suppresses the marker.

---

## 1. Current-state review

### 1.1 What is already good

Keep these pieces. They are the floorboards, not debris.

| Area | Keep because |
|---|---|
| Full-fidelity lexer | It covers every character, marks keyword-capable identifiers without forcing them into hard keyword tokens, and already reports lexical failures such as unterminated strings and comments. |
| Batch and statement segmenter | It is aligned with Query Studio execution splitting around `GO` and already understands semicolons, statement-start keywords, module bodies, and continuation patterns. |
| Tolerant sketch parser | It extracts enough feature facts for many useful language features: scopes, clauses, FROM sources, CTEs, table variables, DML targets, INSERT lists, EXEC calls, and script-local DDL. |
| Script overlay | It is the right place to model temp tables, table variables, CTEs, script-created objects, SELECT INTO, and uncertainty after ALTER. |
| Binder suppression model | It returns suppression reasons instead of guessing. This is exactly the right behavior for 207/208/209-style semantic warnings. |
| Metadata provider seam | The native engine reads `ISqlLanguageMetadataProvider` / `IPinnedMetadataView`, not concrete MetadataService or STS2 wire DTOs. |
| Router and scheduler | Feature routing, fallback, diagnostics scheduling, cancellation, and circuit breaking already exist. |
| Privacy model | Current diagnostics telemetry uses counts, kinds, durations, readiness, and suppression reasons rather than SQL text or identifiers. |

### 1.2 The problem areas

The current pipeline is a feature extractor, not a grammar validator. That means it has several expected failure modes:

1. **No expected-token model.** The sketch parser records useful facts after it recognizes them, but it does not preserve what it expected when recognition failed.
2. **No error nodes.** Recovery is mostly "skip to the next anchor," so diagnostics must rediscover syntax mistakes later from token patterns.
3. **No recovery confidence.** The engine cannot consistently distinguish a certain syntax error from an incomplete mid-edit region.
4. **Unknown-head protection is too coarse.** Silence for EXEC-less procedure calls is important, but it also hides split clause keywords such as `fr om` in some contexts.
5. **Grammar and feature logic are split.** Diagnostics has syntax heuristics. Completions has caret-context heuristics. Both drift from the same missing parser fact.
6. **DDL and procedural grammar are thin.** This is fine for first-pass completions, but it is too weak for Problems once users author stored procedures, table definitions, IF/ELSE, TRY/CATCH, and ALTER scripts.

---

## 2. Design goals

| ID | Goal |
|---|---|
| P-G1 | Detect common syntax errors with high confidence and low noise. |
| P-G2 | Preserve silence under uncertainty, especially for mid-edit, dynamic SQL, EXEC-less procedure calls, unmodeled dialect regions, and metadata-opaque constructs. |
| P-G3 | Produce syntax diagnostics during parsing rather than rediscovering them after parsing. |
| P-G4 | Keep semantic diagnostics in the binder, not the parser. |
| P-G5 | Keep metadata out of the parser. Metadata readiness can suppress semantic warnings, but it must not suppress pure syntax errors. |
| P-G6 | Share parser output with completions through a cursor expectation API. |
| P-G7 | Maintain compatibility with the existing `StatementSketch` and binder while the richer AST rolls out. |
| P-G8 | Make diagnostics observable, testable, and corpus-driven without collecting SQL text or object names in telemetry. |
| P-G9 | Stay fast: diagnostics may be debounced and sliced, but they must never block completion, hover, typing, execution, or Query Studio text sync. |
| P-G10 | Make every diagnostic explainable through a code, confidence, recovery decision, and suppression policy. |

---

## 3. Non-goals

- Full SQL Server grammar parity in the first parser batch.
- Query execution validation. The parser must not call SQL Server to decide syntax.
- Formatting, linting preferences, style warnings, or code-quality hints.
- Refactoring or rename.
- SQLCMD interpretation beyond treating directives as structured opaque regions.
- Deep dynamic SQL parsing inside string literals by default.
- Destructive or noisy semantic claims when metadata is stale, partial, offline, or unvalidated.

---

## 4. Target architecture

```text
src/sqlLanguage/core/lexer.ts
  total token stream, keyword metadata, trivia, token flags

src/sqlLanguage/core/segmenter.ts
  GO batches, statement spans, module-body spans

src/sqlLanguage/core/parser/**
  parse document and statements
  produce AST, expected-token facts, error nodes, recovery stats
  project to StatementSketch for current binder and overlays

src/sqlLanguage/core/binder.ts
  bind projected sketch or richer AST against overlay + pinned metadata
  produce source and column resolution, ambiguity, suppression reasons

src/sqlLanguage/features/diagnostics.ts
  collect lexer diagnostics
  map parser diagnostics to SqlDiagnostic
  run binder semantic warnings when syntax and freshness permit
  publish suppression/recovery counts

src/sqlLanguage/host/nativeEngine.ts
  own analysis cache, provider pinning, freshness policy, scheduling, cancellation
```

### 4.1 Parser v2 module layout

```text
extensions/mssql/src/sqlLanguage/core/parser/
  ast.ts                    # AST node shapes, node kinds, spans, node ids
  parseDocument.ts           # batch/statement orchestration over segmenter output
  parserContext.ts           # token cursor, depth stack, diagnostics sink
  expected.ts                # ExpectedSet, expected-token helpers, keyword pairs
  recovery.ts                # synchronizers, error nodes, recovery confidence
  projection.ts              # ParsedStatement -> StatementSketch compatibility
  cursorExpectation.ts       # shared with completions, no completion producers here
  diagnostics.ts             # ParserDiagnostic -> syntax diagnostic facts
  productions/
    query.ts                 # SELECT, CTE, set operators, FROM, joins, clauses
    expressions.ts           # balanced expressions, name refs, function calls, CASE
    dml.ts                   # INSERT, UPDATE, DELETE, MERGE skeleton
    exec.ts                  # EXEC and EXEC-less call recognition
    ddl.ts                   # CREATE/ALTER/DROP headers, CREATE TABLE columns
    procedural.ts            # BEGIN/END, IF/ELSE, TRY/CATCH, WHILE, RETURN, THROW
    declare.ts               # DECLARE variables and table variables
    use.ts                   # USE database
  testSupport/
    parserDump.ts            # stable debug dump for fixtures and golden review
    oracleAdapters.ts         # dev-only ScriptDOM/ANTLR comparison shapes
```

### 4.2 Dependency rules

| Layer | May import | Must not import |
|---|---|---|
| `core/parser/**` | lexer, segmenter, text ranges, keyword data | MetadataService, STS2 DTOs, vscode, diagnostics substrate, completion producers |
| `features/diagnostics.ts` | parser diagnostics, binder, provider seam | concrete MetadataStore, STS2 wire DTOs, raw data-plane API |
| `host/nativeEngine.ts` | router, provider, metadata policies, diagnostics substrate | parser internals other than public parser API |
| parser oracle tools | ScriptDOM CLI output, ANTLR output, corpus files | product runtime bundle |

Add an import-boundary test before parser integration. It should fail if `core/parser/**` imports metadata, `vscode`, `diagnosticsCore`, or STS2 transport types.

---

## 5. Parser output contracts

### 5.1 Public parse result

```ts
export interface ParsedDocument {
    readonly version: number;
    readonly textHash: string;
    readonly batches: readonly ParsedBatch[];
    readonly statements: readonly ParsedStatement[];
    readonly syntaxDiagnostics: readonly ParserDiagnostic[];
    readonly recoveryStats: ParserRecoveryStats;
    readonly parseMode: "full" | "partial";
}

export interface ParsedBatch {
    readonly ordinal: number;
    readonly span: SqlTextSpan;
    readonly tokenSpan: TokenSpan;
    readonly repeatCount: number;
    readonly goTokenIndex?: number;
    readonly statements: readonly number[];
}

export interface ParsedStatement {
    readonly id: number;
    readonly batchOrdinal: number;
    readonly ordinalInBatch: number;
    readonly globalOrdinal: number;
    readonly kind: ParsedStatementKind;
    readonly span: SqlTextSpan;
    readonly tokenSpan: TokenSpan;
    readonly root: AstNodeId;
    readonly sketch?: StatementSketch;
    readonly trust: StatementTrust;
    readonly recovery: readonly RecoveryEvent[];
}

export type ParsedStatementKind =
    | "select"
    | "insert"
    | "update"
    | "delete"
    | "merge"
    | "exec"
    | "declare"
    | "set"
    | "use"
    | "createTable"
    | "moduleHeader"
    | "ddl"
    | "procedural"
    | "transaction"
    | "unknown";

export interface StatementTrust {
    readonly syntax: "valid" | "recovered" | "unsupported" | "midEdit";
    readonly bindingEligible: boolean;
    readonly completionEligible: boolean;
    readonly reason?: ParserSuppressionReason;
}
```

### 5.2 AST node model

Keep the AST compact and feature-oriented. Do not build a ScriptDOM clone.

```ts
export interface AstNodeBase {
    readonly id: AstNodeId;
    readonly kind: AstNodeKind;
    readonly span: SqlTextSpan;
    readonly tokenSpan: TokenSpan;
    readonly children?: readonly AstNodeId[];
    readonly flags?: readonly AstNodeFlag[];
}

export type AstNodeKind =
    | "SelectStatement"
    | "QueryExpression"
    | "CteList"
    | "SelectList"
    | "FromClause"
    | "TableSource"
    | "Join"
    | "PredicateExpression"
    | "NameReference"
    | "FunctionCall"
    | "DeclareStatement"
    | "CreateTableStatement"
    | "CreateTableColumn"
    | "ModuleHeader"
    | "BeginEndBlock"
    | "ErrorNode"
    | "OpaqueNode";

export interface ErrorNode extends AstNodeBase {
    readonly kind: "ErrorNode";
    readonly diagnosticId: number;
    readonly expected: ExpectedSet;
    readonly recovery: RecoveryDecision;
}
```

### 5.3 Parser diagnostics

```ts
export interface ParserDiagnostic {
    readonly id: number;
    readonly range: SqlLanguageRange;
    readonly span: SqlTextSpan;
    readonly severity: "error" | "warning" | "hint";
    readonly code: ParserDiagnosticCode;
    readonly message: string;
    readonly kind:
        | "unexpectedToken"
        | "missingToken"
        | "splitKeyword"
        | "misorderedClause"
        | "unclosedConstruct"
        | "unsupportedSyntax"
        | "midEditSuppressed";
    readonly confidence: DiagnosticConfidence;
    readonly expected?: ExpectedSet;
    readonly recovery: RecoveryDecision;
    readonly publish: boolean;
}

export type DiagnosticConfidence = "certain" | "probable" | "suppressedMidEdit" | "suppressedUnsupported";

export type ParserDiagnosticCode =
    | "mssql(102)"        // generic incorrect syntax near token
    | "mssql(105)"        // unclosed quotation mark
    | "mssql(113)"        // missing end comment marker
    | "mssql(156)"        // incorrect syntax near keyword
    | "mssql-native(LS1001)"  // parser-specific syntax recovery detail
    | "mssql-native(LS1002)"  // split keyword
    | "mssql-native(LS1003)"; // unsupported but recognized grammar family
```

Use SQL Server-style numbers where they are clear and familiar. Use `mssql-native(...)` only for facts that do not map cleanly to a stable server message.

### 5.4 Recovery facts

```ts
export interface RecoveryDecision {
    readonly strategy:
        | "none"
        | "insertMissingToken"
        | "skipUnexpectedToken"
        | "splitKeywordRepair"
        | "skipToClauseSynchronizer"
        | "skipToStatementBoundary"
        | "balanceDelimiter"
        | "opaqueUntilBoundary";
    readonly skippedTokenCount: number;
    readonly synchronizer?: string;
    readonly canContinueBinding: boolean;
    readonly canContinueCompletion: boolean;
}

export interface ParserRecoveryStats {
    readonly totalRecoveries: number;
    readonly byStrategy: Readonly<Record<string, number>>;
    readonly suppressedMidEdit: number;
    readonly unsupportedRegions: number;
    readonly maxSkippedTokenRun: number;
}
```

Recovery is not just an implementation detail. It drives diagnostic publishing, binder eligibility, and completion confidence.

---

## 6. Diagnostic publishing policy

### 6.1 Diagnostic tiers

| Tier | Source | Examples | Publishing rule |
|---|---|---|---|
| T0 lexical | lexer token flags | unclosed string, unclosed comment, invalid GO line | publish when token flag is certain |
| T1 parser syntax | parser v2 | split keyword, missing BY after ORDER, JOIN without source, ON without join, clause order errors | publish only when recovery confidence meets the rule below |
| T2 semantic binder | binder + pinned metadata | invalid object 208, invalid column 207, ambiguous column 209, unknown named parameter | publish only when syntax is trustworthy and metadata freshness/readiness meets policy |
| T3 optional assist hints | future | probable typo, unsupported construct note | off by default unless dogfood data justifies it |

### 6.2 Confidence ladder

| Confidence | Meaning | Default Problems behavior |
|---|---|---|
| `certain` | The grammar expected a token category, got something impossible, and recovery has a safe synchronizer. | Publish. |
| `probable` | Strong typo shape, but a rare valid interpretation exists. Example: bare top-level `fr om` could theoretically be an EXEC-less procedure call. | Publish only for whitelisted cases after false-positive corpus review, or as hint in dogfood builds. |
| `suppressedMidEdit` | The user appears to be in the middle of typing an incomplete construct. | Do not publish. Count it. |
| `suppressedUnsupported` | Parser entered an unsupported grammar family or opaque region. | Do not publish syntax claims inside it. Count it. |

This keeps the product rule crisp: normal SQL gets useful squiggles, strange SQL gets silence rather than a noisy courtroom drama.

### 6.3 Statement trust and binder gating

Semantic warnings must require a parse shape that can support them.

```ts
function canRunBinderDiagnostics(statement: ParsedStatement, freshness: MetadataFreshness): boolean {
    return statement.trust.bindingEligible
        && statement.trust.syntax !== "unsupported"
        && statement.trust.syntax !== "midEdit"
        && freshness === "validated";
}
```

If syntax recovery skipped a FROM clause, a derived table alias, a JOIN source, or a SELECT item list, binder diagnostics for columns in that region must be suppressed. It is better to report one syntax error than to carpet-bomb the statement with secondary invalid-column warnings.

### 6.4 Maximum diagnostic breaker

Keep the existing breaker and make it explicit:

- maximum diagnostics per document: default 100;
- maximum parser syntax diagnostics per statement: default 8;
- after the breaker, add one suppressed count reason, not a marker;
- never publish cascading semantic diagnostics after an early parser failure in the same statement.

---

## 7. Grammar coverage plan

### 7.1 Phase 1 grammar: SELECT and query expressions

This phase closes the worst common authoring gaps.

Supported with structured parser facts:

- CTE prologue: `WITH cte [(cols)] AS (...)`.
- SELECT modifiers: `DISTINCT`, `ALL`, `TOP (...) [PERCENT] [WITH TIES]`.
- SELECT list: expression spans, aliases, comma-list recovery, `*`, `alias.*`.
- INTO: object target.
- FROM: table sources, aliases, derived tables, TVFs as source-shaped calls, VALUES-derived source, basic table hints as balanced opaque spans.
- JOIN/APPLY: join kind, right source, ON span, missing source diagnostic, missing ON diagnostic for joined source when needed.
- WHERE, GROUP BY, HAVING, ORDER BY, OPTION, FOR: clause order and clause-pair diagnostics.
- GROUP BY and ORDER BY keyword pairs.
- Set operators: UNION, UNION ALL, EXCEPT, INTERSECT.
- Parenthesized subqueries and correlated scope boundaries.

Certain diagnostics from this phase:

| Input | Diagnostic |
|---|---|
| `select * fr om Sales.Orders` | split keyword near `fr om`, expected `FROM` or end of select list depending context |
| `select * from Sales.Orders wh ere OrderID = 1` | split keyword near `wh ere` |
| `select * from Sales.Orders order OrderID` | expected `BY` after `ORDER` |
| `select * from Sales.Orders group OrderID` | expected `BY` after `GROUP` |
| `select * from Sales.Orders join` | expected table source after `JOIN`, suppressed if trailing mid-edit until statement closes |
| `select * from Sales.Orders join Sales.Customers` | expected `ON` after joined table, suppressed for CROSS JOIN / CROSS APPLY |
| `select * from Sales.Orders where where` | unexpected `WHERE` in predicate |

### 7.2 Phase 2 grammar: DML and EXEC

Supported:

- INSERT target, column list, VALUES rows, INSERT SELECT, INSERT EXEC.
- UPDATE target, SET assignments, FROM alias-target form.
- DELETE target and FROM form.
- MERGE skeleton with target, source, ON, WHEN branches as coarse structured nodes.
- EXEC procedure name and arguments, named arguments, OUTPUT marker.
- EXEC-less procedure-call detection for safe silence.

Diagnostics:

- missing target after INSERT/UPDATE/DELETE;
- missing SET after UPDATE target, unless UPDATE FROM shape is still mid-edit;
- malformed INSERT column list or VALUES comma list;
- unknown keyword inside EXEC argument list only when grammar can prove it is not an argument;
- no syntax diagnostics for EXEC-less calls unless there is a betrayal clause or metadata proves the head is not callable and the rest is impossible as arguments.

### 7.3 Phase 3 grammar: DDL and procedural

Supported:

- CREATE/ALTER/DROP TABLE headers and CREATE TABLE column/constraint lists.
- CREATE/ALTER PROC, VIEW, FUNCTION, TRIGGER headers and module body transition.
- ALTER TABLE actions: ADD, DROP, ALTER COLUMN, ADD CONSTRAINT, DROP CONSTRAINT.
- DECLARE scalar variables and table variables.
- SET options and assignments.
- USE.
- BEGIN/END, IF/ELSE, WHILE, TRY/CATCH, RETURN, THROW, RAISERROR.
- Transaction statements.

Diagnostics:

- missing object name after CREATE/ALTER target keyword, suppressed while typing declaration name;
- missing type after variable or column declaration, with mid-edit suppression;
- invalid clause order inside CREATE TABLE list;
- malformed BEGIN/END pairing where the statement is closed;
- missing CATCH after TRY only when END TRY exists and no CATCH follows before boundary.

---

## 8. Split keyword detection

Split keyword detection should be part of parser recovery, not a loose text regex.

### 8.1 Algorithm

At a grammar failure point:

1. Build the expected keyword set from the active production.
2. Look at the next one to three significant identifier tokens.
3. Join their raw text with no whitespace and compare against expected keywords and keyword pairs.
4. Require that each token is an unquoted identifier, not bracketed or quoted.
5. Require that the joined span has no comments between parts.
6. If joined text equals an expected keyword, emit `splitKeyword` with strategy `splitKeywordRepair`.
7. Advance the parser as if the intended keyword appeared, so downstream facts remain useful.

### 8.2 Examples

| Context | Input | Expected set | Action |
|---|---|---|---|
| SELECT list after `*` | `fr om` | `FROM`, `WHERE`, `GROUP`, `ORDER`, end | diagnostic, recover as `FROM` |
| Predicate after source | `wh ere` | `WHERE`, `GROUP`, `ORDER`, end | diagnostic, recover as `WHERE` |
| Clause pair | `ord er by` | `ORDER BY` | diagnostic, recover as `ORDER BY` |
| Statement start | `sel ect * from x` | statement keywords | diagnostic, recover as `SELECT` |
| Statement start | `fr om` | statement keywords only | do not publish as certain; see EXEC-less policy |

### 8.3 EXEC-less procedure-call protection

The dangerous shape is:

```sql
procName arg1, @p = 2
```

The parser must preserve current silence for valid or possibly valid procedure calls. Use this policy:

```text
At top-level unknown head:
  - If joined split tokens form a statement-start keyword and later tokens betray the same statement family, publish.
  - If joined split tokens form only a clause keyword, publish only inside a known statement production.
  - For bare top-level clause splits such as `fr om`, create a suppressed/probable recovery fact unless a dogfood setting enables probable syntax hints.
  - If metadata validates the head as a procedure, suppress syntax diagnostics for EXEC-less form.
  - If args include variables, named parameters, string/number literals, or assignment-like tokens, bias toward silence.
```

This means `select * fr om t` is a certain error. Bare `fr om` can still be treated as a probable typo in dogfood, but the default product should wait for evidence before publishing it as an error.

---

## 9. Syntax diagnostics adapter

### 9.1 Input and output

```ts
export interface SyntaxDiagnosticsInput {
    readonly text: string;
    readonly parsed: ParsedDocument;
    readonly tokens: readonly Token[];
    readonly positionAt: (offset: number) => SqlLanguagePosition;
    readonly options: SyntaxDiagnosticOptions;
}

export interface SyntaxDiagnosticOptions {
    readonly publishProbableSyntax: boolean;
    readonly maxDiagnosticsPerStatement: number;
    readonly maxDiagnosticsPerDocument: number;
    readonly suppressWhileTyping: boolean;
}
```

The adapter maps parser facts to user markers. It does not parse text again.

### 9.2 Message style

Messages should be short and familiar:

- `Incorrect syntax near 'fr om'. Did you mean FROM?`
- `Expected BY after ORDER.`
- `Expected table source after JOIN.`
- `Unexpected WHERE. A WHERE clause already exists in this query expression.`
- `Unclosed parenthesis.`

Avoid clever messages and avoid listing huge expected-token sets. The dragon has enough teeth already.

### 9.3 Range policy

| Diagnostic kind | Range |
|---|---|
| split keyword | full joined split span, for example `fr om` |
| missing token | zero-width range at insertion point, expanded to previous token if Monaco cannot render it clearly |
| unexpected token | offending token span |
| unclosed construct | opening token span when closing token is absent |
| misordered clause | unexpected clause keyword span |

---

## 10. Semantic diagnostics integration

Keep current T2 warnings, but gate them with parser trust.

### 10.1 Updated diagnostics flow

```ts
export function computeDiagnostics(input: DiagnosticsComputeInput): DiagnosticsPassResult {
    const lexical = collectLexicalDiagnostics(input.tokens);
    const parsed = input.parsed ?? parseDocument(...);
    const syntax = mapParserDiagnostics(parsed);

    if (syntax.hitDocumentBreaker) {
        return combine(lexical, syntax, noSemanticWarnings(...));
    }

    const semantic = [];
    for (const statement of parsed.statements) {
        if (!statement.trust.bindingEligible) {
            count(statement.trust.reason ?? "unsupportedSyntax");
            continue;
        }
        if (hasBlockingSyntaxDiagnostic(statement)) {
            count("syntaxUntrusted");
            continue;
        }
        semantic.push(...computeBinderDiagnostics(projectedSketch(statement)));
    }

    return combine(lexical, syntax, semantic);
}
```

Add suppression reasons:

```ts
export type DiagnosticSuppressionReason =
    | ExistingReason
    | "syntaxUntrusted"
    | "parserMidEdit"
    | "parserUnsupported"
    | "parserRecoveryTooLarge"
    | "parserDiagnosticBreaker";
```

### 10.2 Metadata freshness interplay

- Pure syntax diagnostics do not require metadata and do not call MetadataService.
- Binder warnings require `MetadataPolicies.diagnosticsBinder` or equivalent freshness.
- If freshness returns stale/unvalidated, suppress binder warnings and count `metadataNotValidated`.
- If metadata generation changes during diagnostics, host cancels and reschedules.

This matches the existing cache/freshness split: syntax belongs to the editor text; semantic object truth belongs to a pinned and validated metadata view.

---

## 11. Analysis cache and scheduling

### 11.1 Cache shape

```ts
interface NativeDocumentAnalysis {
    readonly textVersion: number;
    readonly tokenResult: TokenizationResult;
    readonly segmentResult: SegmentResult;
    readonly parsed: ParsedDocument;
    readonly overlay: ScriptOverlay;
    readonly projectedSketches: readonly StatementSketch[];
    readonly parseDiagnosticsHash: string;
}
```

Cache keys:

- text version for lexer, segmenter, parser, overlay;
- metadata generation for binder results only;
- metadata freshness result for diagnostics T2 only.

Do not reparse because metadata changed. Metadata changes invalidate binder and semantic diagnostics, not syntax.

### 11.2 Sliced diagnostics

Recommended scheduler behavior:

- tokenize and segment synchronously for current document version;
- parse in batches with a time budget, yielding between statements for large documents;
- publish lexical diagnostics early only if parser pass is delayed by document size;
- run binder diagnostics after parser diagnostics, again sliced by statement;
- cancel stale passes on text edit or metadata generation change;
- never block completion/hover requests behind diagnostics.

### 11.3 Performance targets

Measure and tune rather than treating these as prophecy, but use them as starting budgets:

| Scenario | Target |
|---|---|
| Parse current caret statement | p95 < 2 ms for common statements |
| Whole-document parse, 1k lines | p95 < 25 ms total, sliced |
| Whole-document parse, 10k lines | p95 < 150 ms total, sliced, no UI stall |
| Diagnostic publish after last edit | debounce 250 to 500 ms, cancel stale passes |
| Binder T2 pass with warm metadata | p95 < 50 ms for 1k-line normal scripts |
| No metadata or stale metadata | syntax still publishes, T2 suppressed quickly |

---

## 12. Testing strategy

### 12.1 Unit test families

```text
extensions/mssql/test/unit/sqlLanguageParser.test.ts
extensions/mssql/test/unit/sqlLanguageSyntaxDiagnostics.test.ts
extensions/mssql/test/unit/sqlLanguageParserProjection.test.ts
extensions/mssql/test/unit/sqlLanguageDiagnosticsParserIntegration.test.ts
```

Test suites:

1. **Lexer and segmenter preservation.** Existing tests remain green.
2. **Parser dumps.** Golden AST/recovery dumps for small fixtures.
3. **Syntax diagnostics.** Focused input/output marker tests.
4. **Projection compatibility.** Parser projection produces equivalent `StatementSketch` facts for existing completion/diagnostic fixtures.
5. **Suppression honesty.** Uncertain regions produce counts, not markers.
6. **EXEC-less procedure protection.** Valid and ambiguous procedure-call shapes stay clean.
7. **Mid-edit suppression.** Incomplete WHERE/JOIN/paren states stay quiet until closed.
8. **Large document stability.** Random generated scripts do not throw and respect breaker limits.

### 12.2 Corpus tiers

| Tier | Contents | Purpose |
|---|---|---|
| Core fixtures | hand-written minimal examples | exact unit behavior |
| Product corpus | sanitized Query Studio dogfood snippets with object names hashed or replaced | common real shapes |
| Parser torture | deeply nested parentheses, comments, strings, GO, modules | totality and performance |
| Negative corpus | known invalid examples | diagnostic coverage |
| Clean corpus | valid scripts from samples, generated tables/procs | false-positive protection |
| Oracle corpus | scripts parsed by ScriptDOM/ANTLR tool in CI | gap discovery, not runtime dependency |

### 12.3 False-positive gate

Before promoting native diagnostics beyond preview:

- clean corpus must have zero unexpected syntax diagnostics;
- false-positive triage file must list every accepted exception;
- every new syntax diagnostic kind needs at least one clean-corpus guard test;
- dogfood telemetry should show diagnostic suppression and published counts by code, not text.

### 12.4 Fourslash diagnostic fixture shape

```ts
diagnose(`
SELECT * fr om Sales.Orders
         ^^^^^ mssql-native(LS1002) Incorrect syntax near 'fr om'. Did you mean FROM?
`);
```

Use stable ranges and code checks. Avoid matching entire prose unless the message is part of UX acceptance.

---

## 13. Observability and privacy

### 13.1 Span/event families

Add these through the existing observability contract path before emitting:

```text
sqlLanguage.parser.parse
sqlLanguage.parser.recover
sqlLanguage.diagnostics.syntax
sqlLanguage.diagnostics.semantic
sqlLanguage.diagnostics.publish
```

Fields may include:

- token count bucket;
- statement count bucket;
- elapsed ms bucket;
- parser version;
- parser coverage mode;
- diagnostic code counts;
- confidence counts;
- recovery strategy counts;
- suppression reason counts;
- breaker hit boolean;
- provider readiness states;
- freshness result states.

Fields must not include:

- SQL text;
- identifiers;
- object names;
- string literal contents;
- database names;
- server names;
- result rows;
- connection strings;
- tokens that could reconstruct user text.

### 13.2 Status output

Extend language status command with:

```ts
interface ParserStatus {
    readonly parserVersion: string;
    readonly lastParseMs?: number;
    readonly lastStatementCount?: number;
    readonly lastDiagnosticCountsByCode?: Record<string, number>;
    readonly lastRecoveryCounts?: Record<string, number>;
    readonly lastSuppressionCounts?: Record<string, number>;
    readonly nativeDiagnosticsEnabled: boolean;
}
```

---

## 14. Implementation phases

### P0 - Lock current behavior and immediate split-keyword patch

Tasks:

1. Add tests for the current missing cases and the desired behavior.
2. Implement parser-independent split keyword detection only where it is low risk:
   - inside known SELECT clause scanning;
   - after recognized clause anchors;
   - not for arbitrary unknown top-level heads unless publishProbableSyntax is enabled.
3. Add regression tests for EXEC-less procedures.
4. Add suppression counters for split-keyword cases that are detected but not published.

Acceptance:

- `select * fr om Sales.Orders` produces a syntax diagnostic.
- `select * from Sales.Orders wh ere OrderID = 1` produces a syntax diagnostic.
- `sp_help Orders` stays clean.
- `Sales.GetOrders @CustomerID = 1` stays clean if metadata cannot prove otherwise.

### P1 - Parser infrastructure

Tasks:

1. Add `core/parser/**` scaffolding.
2. Add token cursor and parser context.
3. Add expected-token and recovery sink types.
4. Add parser AST base nodes and parser dump test support.
5. Add `projection.ts` that returns existing `StatementSketch` from parsed statements.
6. Wire parser behind a hidden internal flag but keep existing sketch path as default.

Acceptance:

- parser is total for existing completion and diagnostics fixture corpus;
- projection matches existing sketch facts for current covered cases;
- no behavior changes in published diagnostics unless hidden flag enabled.

### P2 - SELECT/query grammar and syntax diagnostics

Tasks:

1. Implement SELECT/CTE/FROM/JOIN/WHERE/GROUP/HAVING/ORDER/set operators.
2. Implement split-keyword repair using expected sets.
3. Implement clause-order and keyword-pair diagnostics.
4. Integrate parser diagnostics into `features/diagnostics.ts` behind a route flag.
5. Add false-positive corpus gate for SELECT scripts.

Acceptance:

- common SELECT syntax errors are caught.
- existing 207/208/209 semantic tests remain green.
- completions still use current classifier through projection.

### P3 - DML, EXEC, DECLARE, USE

Tasks:

1. Implement INSERT/UPDATE/DELETE/MERGE skeleton productions.
2. Implement EXEC and EXEC-less protection.
3. Implement DECLARE and table variable parser facts.
4. Implement USE parser facts.
5. Expand projection to preserve overlay and binder behavior.

Acceptance:

- DML syntax tests pass without completion regressions.
- EXEC-less call corpus remains quiet.
- overlay tests still pass.

### P4 - DDL and procedural common grammar

Tasks:

1. Implement CREATE TABLE names, columns, and table constraints enough for overlay.
2. Implement ALTER TABLE action recognition.
3. Implement module headers and body transition.
4. Implement BEGIN/END, IF/ELSE, TRY/CATCH, WHILE, RETURN, THROW.
5. Add module-body nested statement parsing.

Acceptance:

- DDL/proc authoring common cases produce either useful syntax errors or honest silence.
- no new DDL noise in declaration-name positions.

### P5 - Parser becomes default syntax source

Tasks:

1. Remove or retire duplicated diagnostics syntax heuristics that parser covers.
2. Keep lexical diagnostics in lexer.
3. Keep binder diagnostics as T2.
4. Add parser status output and observability.
5. Run native-vs-bridge and dogfood review.

Acceptance:

- parser diagnostics are default when native diagnostics are routed.
- route fallback still works.
- false-positive gate remains green.

### P6 - Corpus/oracle hardening

Tasks:

1. Add dev-only ScriptDOM oracle runner.
2. Add parser dump triage report.
3. Add divergence buckets: missing diagnostic, extra diagnostic, different statement kind, different source extraction.
4. Feed the top real gaps into P7+ backlog.

Acceptance:

- CI can run oracle checks in an optional or nightly lane.
- runtime bundle has no oracle dependency.

---

## 15. Coding-agent first task list

Start with a small slice that proves the architecture without rewriting everything:

1. Create `core/parser/ast.ts`, `expected.ts`, `recovery.ts`, `parserContext.ts`, and `parseDocument.ts` with minimal SELECT support.
2. Create `projection.ts` and make it produce a `StatementSketch` compatible with existing SELECT tests.
3. Add `sqlLanguageParser.test.ts` with parser dump tests for:
   - `SELECT * FROM Sales.Orders`;
   - `SELECT * fr om Sales.Orders`;
   - `SELECT * FROM Sales.Orders ORDER OrderID`;
   - `SELECT * FROM Sales.Orders WHERE` mid-edit.
4. Wire parser into diagnostics behind an internal option, not a user setting.
5. Add diagnostics tests for split keyword in SELECT context.
6. Keep the old syntax diagnostics path alive until P5.

---

## 16. Acceptance checklist for this design

A coding agent should not call the feature done until these statements are true:

- The parser never throws on arbitrary editor text.
- Parser diagnostics are produced by parser recovery decisions, not by a second scan of strings.
- `fr om` inside a SELECT is caught without breaking EXEC-less procedure calls.
- Binder diagnostics are suppressed after untrusted syntax recovery.
- The existing completion suite stays green through the projection adapter.
- Telemetry contains counts and kinds, never SQL text or identifiers.
- Parser output can serve both diagnostics and completion expectations.
- The implementation can be rolled out behind the existing language-service router.

---

## 17. Decision

Build parser v2 as a shared language-service substrate. Ship a small split-keyword patch only as a bridge to the real architecture.

The current Problems implementation is not merely missing a few if-statements. It lacks the grammar state needed to make confident, explainable syntax claims. A parser with error nodes, expected-token facts, and recovery decisions gives Query Studio the diagnostic quality bar it needs while preserving the best parts of the existing implementation: pinned metadata, conservative semantic warnings, performance slicing, and privacy-safe observability.
