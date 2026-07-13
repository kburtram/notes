# Native LSP Problems and Completions Implementation Plan

Date: 2026-07-08

This plan uses the reviewed designs in
`native_lsp_problem_completion_designs` as the starting point and turns them
into an incremental implementation path. The goal is to improve correctness and
usefulness without regressing the metadata-backed completion and diagnostics
features that already work.

## Principles

- Parser-owned expectations decide whether completions are useful. Candidate
  producers should not be responsible for guessing whether the caret is in a
  symbol declaration, a type position, a source position, or a predicate.
- Silence is a valid, intentional result. When the parser knows the user is
  typing a new symbol name, the engine should return no completions rather than
  broad keywords.
- Diagnostics should only claim syntax errors when recovery is confident. T-SQL
  allows EXEC-less procedure calls and partially typed statements, so broad
  unknown-token diagnostics are too noisy.
- Binder-backed diagnostics stay behind the existing honesty ladder. If syntax
  recovery marks a statement untrusted, T2 object and column claims are
  suppressed and counted.
- Journal fields should describe decisions by category and count, not by raw
  text, except where existing elevated capture policy already allows labels.

## Phase 0: Vertical Parser Slice

1. Add a parser-owned `CompletionExpectation` module that wraps the current
   classifier and adds C0 declaration/type recognition.
2. Gate completions for net-new symbol contexts:
   - `CREATE TABLE` object and column names.
   - `CREATE PROC/PROCEDURE`, `CREATE VIEW`, `CREATE FUNCTION`, and
     `CREATE TRIGGER` object names.
   - `DECLARE` variable names.
   - table-variable column names.
   - `ALTER TABLE ... ADD` column names.
3. Preserve type suggestions in type positions:
   - `DECLARE @x |`
   - `CREATE TABLE T (Id |`
   - `CREATE TABLE T (Id i|`
   - `ALTER TABLE T ADD NewColumn |`
4. Emit completion journal fields for expectation kind, confidence, and
   suppression reason while preserving existing context fields.
5. Add SELECT syntax recovery diagnostics for split clause keywords and missing
   `BY` after `GROUP`/`ORDER` inside recognized SELECT statements.
6. Suppress T2 binder diagnostics for statements that contain recovered syntax
   errors and count `syntaxUntrusted`.
7. Add focused unit tests for expectation classification, completion gating,
   syntax recovery, and existing EXEC-less procedure protections.

## Phase 1: Shared Statement Parser Model

1. Expand the sketch parser into a reusable parse result with explicit
   statement, clause, declaration, and expression slots.
2. Replace one-off completion guards with expectation rules over the parse
   result.
3. Move diagnostics recovery checks from scanner helpers to parser recovery
   nodes with stable error codes and spans.
4. Add parse tracing counters to the diagnostics journal:
   - statement kind distribution.
   - recovery count by recovery kind.
   - syntax-trust state by statement.
5. Add unit tests for common partial-edit states so parser recovery stays
   tolerant while users type.

## Phase 2: Completion Parser Depth

1. Add symbol-vs-keyword expectation for object definitions, aliases, column
   aliases, parameters, variables, and DDL bodies.
2. Add context-sensitive keyword sets by expectation. Keyword producers should
   be opt-in from the expectation, not global fallback.
3. Keep metadata producers unchanged where they already produce good results:
   table sources, member access, FK joins, INSERT/UPDATE scaffolds, EXEC
   params, overlay objects, and system catalog objects.
4. Add corpus tests for `SELECT`, DML, DDL, modules, variables, temp objects,
   CTEs, derived tables, and system catalogs.
5. Add latency tests with large fixture catalogs and partial metadata readiness.

## Phase 3: Problem Parser Depth

1. Introduce parser recovery nodes for:
   - split keywords in known clauses.
   - missing clause connectors such as `GROUP BY` and `ORDER BY`.
   - misplaced clause keywords at compatible depths.
   - unclosed constructs when a later statement proves the recovery.
2. Keep uncertain cases silent:
   - EXEC-less procedure calls.
   - unknown top-level identifiers without betraying syntax.
   - trailing mid-edit fragments.
   - unsupported statement families.
3. Make binder diagnostics consume parser trust state before binding.
4. Add diagnostic acceptance tests against both null and full metadata
   providers.

## Phase 4: End-to-End and Debug Console Coverage

1. Add Query Studio e2e tests for:
   - no popup or blank completion list in symbol declaration contexts.
   - type suggestions in type positions.
   - `sys.` and `sys.all` catalog completions.
   - Problems entries focusing the Query Studio editor without duplicate tabs.
   - journal spans containing expectation and syntax-recovery fields.
2. Add journal assertions that verify decision categories, not raw user text.
3. Add replay tests from session journals for previously reported regressions:
   disappearing keys, schema suggestions under `sys`, and weak problem
   detection around split keywords.

## Current Slice Acceptance

- `CREATE PROC dbo.p|`, `DECLARE @x|`, `DECLARE @t TABLE (|`, and
  `ALTER TABLE Sales.Orders ADD NewColumn|` return no completions.
- `DECLARE @x |`, `CREATE TABLE T (Id i|`, and
  `ALTER TABLE Sales.Orders ADD NewColumn i|` offer type keywords.
- `select * fr om Sales.Orders` reports a syntax diagnostic suggesting `FROM`.
- `select * from Sales.Orders wh ere OrderID = 1` reports a syntax diagnostic
  suggesting `WHERE`.
- `sp_help Orders`, `Sales.GetOrders @CustomerID = 1`, and half-written `JOIN`
  states remain clean.
- Completion journal spans include `expectationKind`,
  `expectationConfidence`, and `suppressReason` when applicable.
