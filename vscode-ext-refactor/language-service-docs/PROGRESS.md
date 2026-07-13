# T-SQL Language Service — Progress Journal

Restart protocol: read `EXECUTION_PLAN.md` (batch statuses + local-reality
notes + worksheet), then spec `05-tsql-language-service-design.md`. House
rules carry over from the Query Studio effort
(`coding-docs/ssms-query-docs/EXECUTION_PLAN.md` + `compact-handoff.md`):
commit isolation core:/ls:/qs:, CRLF files, commit from repo root, cd to
extensions/mssql before npx, contracts regenerate+re-vendor workflow,
privacy rules (no SQL text / identifiers / secrets in diagnostics by
default), NEVER `mssql.sts2.*` settings.

## 2026-07-05 - Entry 1: Plan authored; pre-flight evaluation + worksheet row 1 service fix

CONTEXT: B1–B7 of the Query Studio plan are complete (see
ssms-query-docs/PROGRESS.md Entries 1–9). Karl's directive: finish pending
QS/instrumentation work, run a full evaluation, then start the language
service — full TypeScript T-SQL language service for Query Studio with an
engine toggle (STS v1 bridge vs native), starting with completions on a
clean metadata-provider interface for future rehosting.

FULL EVALUATION (all green, 2026-07-05):
- vscode-mssql @ 0f4032d90: tsgo extension+webviews clean; `npm run build`
  0 errors; `npx vscode-test` 3390 passing / 12 pending / 1 failing = the
  known Copilot-owned copilotChatEntry hook-timeout flake only.
- perftest @ f36d409: workspaces 110/110.
- Gates (config.eval.local.jsonc, 3 official reps + 1 warmup each, run
  2026-07-05T18-16-21Z_a8d3f243, 16/16 passed exit 0): debug-console-smoke
  9.9–14.5ms; querystudio-open passed (noisy box: 1190–5362ms band, within
  gate); querystudio-query-10k 553.7/576.4/1060.0/794.2ms official — the
  multi-rep baseline history residual from Entry 9 is now accruing;
  query-10k-results official (608.9–3779ms band, passed).

STS2 WORKSHEET ROW 1 ANSWERED (the open preview blocker): verified against
sqltoolsservice dev/query source. VERDICT: message text is verbatim by
construction on the client-bound wire (JSON escaping only; no rewording,
truncation, localization, or redaction — SecretRedactor touches inbound
request params pre-journal only; WireValueEncoder truncation applies to row
cells, not messages). rowsAffected is structured on v2/query.complete
(client renders "(N rows affected)" itself — confirms row 4). BUT two gaps
found and FIXED service-side (SqlClient driver never subscribed
SqlConnection.InfoMessage → PRINT/RAISERROR≤10 never delivered; wire message
omitted `line`):
- SqlClientSession.ExecuteAsync now subscribes InfoMessage (SPEC §10.2
  mandate), queues ServerMessage("info", number, class, verbatim text,
  line>0?line:null), drains at pump boundaries, unsubscribes in finally.
- DriverEffectRunner + Sts2CoreReducer pass `line` through to
  v2/query.message (client wire type V2MessageNotification already declared
  `line?: number` — the client was written expecting it).
- FakeQueryStep gains `Line`; FakeDriver passes it; new QueryFlowTests case
  ServerMessagePassesThroughVerbatimWithLine (verbatim text with
  quotes/backslashes + structured line + null-line case).
- NOT added: `state` on v2/query.message (SPEC's ServerMessage has no State;
  terminal error.server already carries state; kept minimal). messageClass
  remains "info" for InfoMessage-sourced messages.

DECISIONS:
- Commit prefix `ls:` added for src/sqlLanguage/** + src/sqlScripting/**
  (own PR train; core:/qs: unchanged).
- Bridge = provider-command aggregation first (spec §9.3), shadow v1
  connection lazy on the backing document URI; direct STS v1 adapter only
  if aggregation pollutes (worksheet #1).
- batchSplitter stays untouched in LS-0; full lexer built separately;
  convergence recorded as follow-up (metadata DDL sniffer shares it).
- Entry 9 residuals NOT in this plan's scope, dispositioned: B5 disk cache
  (backlog — revisit when language-service cold-start metrics exist; warm
  completions need it most), plan TAB rendering (backlog, orthogonal
  feature), DC embedding of feature panels (backlog UX), 30-min dogfood
  resync gate + SqlLogin live seeding (need human/live env).

NEXT: B8 / LS-0 per EXECUTION_PLAN.md.

## 2026-07-05 - Entry 2: B8 / LS-0 COMPLETE (foundation, toggle, router, bridge, lexer, provider seam)

SHIPPED — vscode-mssql (dev/query):
- core: d769cadea — re-vendored contract (perftest cb2c807: sqlLanguage./
  sqlScripting./queryStudio.languageService. span families) + banned-imports
  gains the sqlLanguage purity clause (core/features/data/provider-types:
  no vscode, no node builtins, nothing outside src/sqlLanguage) AND the
  long-documented STS2 wire containment clause (now lint, not prose).
- ls: bc3eb826c — pure core: TextSnapshot (one place for UTF-16
  offset<->position); full-fidelity total lexer (nested block comments,
  N'...', bracket/quoted escapes, variables, temp names, hex/scientific,
  keyword METADATA on identifiers — never hard keyword tokens; GO with
  EXACT execution-splitter parity incl. "GO abc"-is-content; SQLCMD ':'
  lines opaque; per-line start states for future incremental lexing);
  keywords.generated.ts (269 entries, 184 reserved, curated + provenance);
  segmenter (batches: GO n/max(1,n), empty dropped, comments are content —
  parity corpus asserted vs splitBatches; statements: tolerant v1 with
  reserved-only boundaries, continuation suppression, BEGIN TRAN vs block,
  CASE/END, module AS body); provider seam ISqlLanguageMetadataProvider +
  IPinnedMetadataView (+null/fixture providers); SqlLanguageFeatureEngine
  API; LanguageFeatureRouter (maturity gate, circuit breaker,
  ...route spans); NativeSqlLanguageEngine (analysis cache + lex/segment
  spans); folding + documentSymbols ship NATIVE in LS-0.
- ls: catalogProvider (CatalogSnapshot adapter: resolution/columns+PK/FK
  pairs/params/search/schemas; env unified from snapshot H0 + session
  serverVersion; CREATE OR ALTER gated 13.0.4001+/14+; offline pin view),
  bridgeEngine (provider-command aggregation over the backing document;
  bridge spans; pull diagnostics from the "mssql" collection), fourslash
  harness + STANDARD_FIXTURE_CATALOG.
- qs: facade queryStudioLanguageService (router + engines per document;
  LAZY shadow STS v1 connection via connectionManager on the backing URI —
  created on first bridge-routed request only, invalidated on database
  change, disposed with the panel; onDidCloseTextDocument is the safety
  net); binding exposes shadowConnectionProfile (no credentials — password
  resolution stays in the connection store path).
- qs: contracts sharedInterfaces/queryStudioLanguage.ts (qs/lang.* x8 +
  diagnosticsChanged notification); controller handlers 1:1 onto the
  facade; webview Monaco providers (completion/hover/signature/definition/
  folding/documentSymbols + setModelMarkers via push+seed); setting
  mssql.queryStudio.languageService.engine (sqlToolsService default);
  command mssql.queryStudio.languageServiceStatus (OutputChannel lantern:
  preference, per-feature route table, readiness, generation, shadow
  state).

TESTS: 34 new (21 core: lexer corpus/coverage invariant/GO rules/parity
corpus/statement rules/router circuit-break/folding/symbols; 13 provider+
harness: fourslash, fixture catalog, catalog-adapter offline honesty,
capability version gating; 2 shadow-lifecycle gate tests: native-only
traffic never creates the shadow connection).

DEVIATIONS: core/keywords.ts helpers folded into the data asset + lexer
(add when the B9 parser needs classification beyond category/reserved).
Batch-level GO-junk diagnostic deferred to B10 T1 (parity: junk lines are
content). Bridge definition cross-file targets open beside (old behavior
until LS-4). highlights/semanticTokens unserved (B13). batchSplitter
convergence onto the full lexer = recorded follow-up (DDL sniffer shares
it; do not destabilize).

WORKSHEET: #1 (aggregation pollution) + #2 (shadow status-bar side
effects) + #3 (backing-doc close vs custom-editor lifetime) remain OPEN —
need live dogfood with a connected QS document; #6 (webview Monaco
isolation) answered by construction (webview Monaco has no VS Code-level
providers).

VERIFIED (2026-07-05): tsgo extension + webviews clean; extension AND
repo-root builds 0 error lines; eslint clean on the new tree (purity rule
active); full `npx vscode-test` green except the known copilotChatEntry
flake (12 pending; +34 sqlLanguage tests); gates re-run post-B8 (run
9669ec57, 16/16 passed): querystudio-query-10k 546.4–562.0ms official (no
regression vs ~551ms pre-B8), query-10k-results/querystudio-open/
debug-console-smoke all passed. Commits: perftest cb2c807 (core:
vocabulary); vscode-mssql d769cadea (core:), bc3eb826c (ls:), b00b77308
(qs:). Both trees clean.

NEXT: B9 / LS-1 native completions (sketch parser, overlay, database
context, binder, context classifier, candidates incl. FK joins + star
expansion, ranking, snippets, H3 identity/computed extension, 150+
fourslash cases, p95 < 40ms bench).

## 2026-07-05 - Entry 3: B9 / LS-1 native completions — functional core COMPLETE

SHIPPED — vscode-mssql (dev/query):
- ls: core/sketch (tolerant TOTAL statement sketch: query expressions with
  clause spans, nested scopes for subqueries/derived tables, FROM source
  grammar incl. TVFs/table hints/@tablevar sources, CTEs with declared or
  body-inferred columns, INSERT target+column list+VALUES/SELECT/EXEC
  source, UPDATE alias form+SET, DELETE, MERGE skeleton, DECLARE scalars +
  @t TABLE columns, EXEC named/positional args + dynamic-SQL opacity,
  CREATE TABLE (#temp) columns skipping constraints, SELECT INTO, USE);
  core/overlay (temp tables/table variables/script tables with batch/
  document visibility; DROP tracking deferred to B10); core/binder v1
  (alias-before-object resolution, scope chains innermost-out, CTE/overlay/
  catalog/derived column sources, suppression reasons instead of guesses,
  cross-db/linked-server honesty); core/context (caret classifier for all
  design §10.2 contexts; comment/string/sqlcmd suppression; trailing
  mid-edit tolerance); core/fuzzy (deterministic explainable scores);
  core/quote (bracket-when-required); features/completion (per-context
  candidates: FK JOIN predicates incl. reverse edges ranked FIRST at ON,
  FK-adjacency table ranking after JOIN, star expansion with explicit
  replaceRange + incomplete-metadata refusal, INSERT writable-column
  scaffolds skipping identity/computed + (all columns) item, UPDATE SET
  "col = " scaffolds via alias-form target resolution, EXEC remaining
  named params with OUTPUT badges, DECLARE types, USE databases, ORDER
  BY/GROUP BY select-aliases, builtins/variables/keywords in expressions,
  ambiguity-qualified column labels, deterministic §10.5 ranking with
  kind priorities + boosts, honest isIncomplete + incompleteReason);
  data/builtinFunctions.generated (157 builtins w/ signatures + docUrls) +
  data/snippets (23); engine wiring (analysis cache extended with sketches
  + overlay; sqlLanguage.parse/completion spans — context kind + counts
  only); router capability completion=preview.
- SEGMENTER fix (found by B9 tests): statement-aware continuation
  allowances — UPDATE→SET, INSERT→SELECT/EXEC, WITH→first DML, MERGE→WHEN
  branches (chaining on consumption) — so multi-clause statements are ONE
  statement; column-name reader skips trivia after commas.
- qs: MetadataService H3 + catalogModel gain is_identity/is_computed
  (appended to H3 select; boolean|0/1 wire-tolerant parse; snapshot sets
  flags only when true; buildSchemaContext BYTE-IDENTICAL — MD-4 golden
  parity 8/8 verified); catalogProvider maps them; settings
  mssql.sqlLanguage.completions.snippets + keywordCasing; facade passes
  engine options; QsLang contract + webview honor replaceRange.

TESTS: 93 sqlLanguage total (16 sketch, 44 completion incl. honesty/
casing/brackets/case-sensitivity, latency probe, + B8's 33 updated). Warm
completion on a 2k-line doc: median 0.05ms / p95 0.15ms (analysis-cache
warm path; unit-lane ceiling 100ms; the §16.1 40ms budget refers to host
latency which includes one cold analyze on edit — well within budget).

DEVIATIONS/RESIDUALS toward the LS-1 gate: fourslash count 60 net new vs
the 150+ acceptance bar (grows through B10+; matrix coverage is complete
per-context, depth grows); core/databaseContext.ts (USE map) not yet
split out — USE completions work, per-statement effective-db binding
lands with B10 suppression needs; keywordCasing "lower" replaces spec's
"asTyped" hint; MRU accept-history boost deferred; lazy documentation
resolve deferred (docs ride the items — small); PERF_MODE probe +
perftest completion-latency scenario deferred to B14 head-to-head;
system-proc catalog (sp_*) not exposed via systemObjects() yet
(worksheet #5). LIVE QS dogfood of native completions pending (toggle
mssql.queryStudio.languageService.engine=nativeTypeScript).

VERIFIED (2026-07-05): tsgo extension+webviews clean; extension + repo-root
builds 0 error lines; eslint clean (purity boundaries enforced); full
`npx vscode-test` 3484 passing / 12 pending / 1 failing = the known
copilotChatEntry flake (+94 tests over the B8 baseline; 93 sqlLanguage);
MD-4 golden parity 8/8 after the H3 extension; gates post-B9 (run
250ba3cc, 16/16 passed): querystudio-query-10k 389.0–565.2ms official,
query-10k-results/querystudio-open/debug-console-smoke passed. Commits:
vscode-mssql 06752beb6 (ls:), 5d3979935 (qs:). Both trees clean.

NEXT: B10 / LS-2 native diagnostics (T1 lexical/structural + T2 binder
207/208/209 with the suppression ladder, debounce/sliced scheduler,
honesty suite) per EXECUTION_PLAN.md; grow the fourslash corpus toward
the 150+ LS-1 bar en route; live QS dogfood of native completions
(engine=nativeTypeScript) is the standing manual validation ask.

## 2026-07-06 - Entry 4: B10 / LS-2 COMPLETE (native diagnostics)

Context: built during the remaining-tasks pass (task queue in
central_remaining_docs_review_pack/remaining_tasks.md; OE v2 B15-B21
complete + validated live per oe-docs PROGRESS).

SHIPPED — vscode-mssql ls: 5358da450 + qs: 47176417e:
- features/diagnostics.ts: T1 lexical/structural ERRORS (unterminated
  string mssql(105)/comment mssql(113)/identifiers, invalid-GO lines,
  certain-recovery paren imbalance mssql(102), duplicate exposed source
  names) + T2 binder WARNINGS (208 object / 207 column / 209 ambiguous,
  server-style messages) behind the §11.2 SUPPRESSION LADDER — 16
  counted reasons; suppress-never-guess; no identifier text in diag
  metadata; resumable per-statement pass; innermost-scope-first
  resolution (correlated subqueries never false-209).
- host/scheduler.ts: 300ms debounce, 8ms slice budget with yields, stale
  cancel stamped by version AND metadata generation (provider changes
  abort in-flight passes). core/databaseContext.ts: per-statement USE
  map (B9 deferral landed). Router: diagnostics=preview.
- qs: ONE publisher per document (bridge forwarding gated off when
  natively routed; route-switch republish), diagnostics.enabled setting
  (false → publish empty, markers clear), suppression counts + scheduler
  state in the status lantern; markers via existing diagnosticsChanged →
  setModelMarkers, source "T-SQL (native)".
- FIX (B9 latent): ALTER TABLE fabricated a phantom zero-column overlay
  object — now overlay.alteredNames marks shapes untrustworthy (this
  would have poisoned completions too).

TESTS: +143 (127 diagnostics incl. the 62-case §17.4 honesty corpus —
CTEs incl. recursive, temp tables incl. session-invisible/ALTER'd,
table variables, SELECT INTO, dynamic SQL, OPENJSON/OPENROWSET,
synonyms, cross-db, 4-part, lite/partial/loading metadata,
keyword-lookalike identifiers, CS collation, USE switching, mid-edit —
ALL zero unexpected diagnostics; 9 scheduler; 7 facade publish/mutual-
exclusion). Targeted language band 251/0.

DEVIATIONS: MERGE fully suppressed (unsupportedSyntax — skeleton sketch
can't honestly bind WHEN branches); T2 scoped to 207/208/209 per plan
(no named-param/arity checks); DECLARE @x TABLE malformed-column T1
skipped (tolerant sketch lacks certainty); module bodies KEEP 207/209
(matches STS/SSMS deferred-name-resolution behavior — recorded
decision); UNION/EXCEPT branch ambiguity suppressed (setOperationScope)
until per-branch scopes exist.

FINDINGS for B11+: SELECT INTO overlay drops unaliased column names —
hover must not trust those shapes (columnsUntyped suppression covers
diagnostics); segmenter splits FETCH NEXT off OFFSET (harmless, add a
continuation allowance later); consider routing the first synchronous
diagnostics pull through the scheduler for huge documents.

VERIFIED (2026-07-06): tsgo extension+webviews clean; repo build 0
errors; eslint clean (purity boundaries active); full suite 3711
passing / 12 pending / 1 failing (known copilotChatEntry flake); gates
20/20 (run 2026-07-06T06-15-40Z_6548c15b incl. objectexplorerv2-browse).
Tree clean at 47176417e.

NEXT: B11 / LS-3 hover + signature help (H7 descriptions hydration on
the metadata side; hover honesty incl. the SELECT INTO finding above).

## 2026-07-06 - Entry 5: B11 / LS-3 COMPLETE (hover + signature help + H7)

SHIPPED — vscode-mssql ls: 25b272149 + qs: 83b20f5f4 (+ oe: 8d9393943
fixture): features/hover.ts (markdown hover per bound symbol kind w/
strict section-readiness gating, PK/identity/computed/FK badges, H7
descriptions, trustworthy-shapes-only for overlay objects — honors B10's
alteredNames + SELECT INTO findings, never overclaims);
features/signatureHelp.ts (innermost-call scan w/ grouping-paren
stepping, builtin overloads from the data asset, user routines, EXEC
named/positional w/ named-wins); router hover/signatureHelp=preview;
sqlLanguage.hover/.signature spans (kind/counts only). H7: MS_Description
hydration (sys.extended_properties class 1, objects+columns via
COL_NAME — no sys.columns substring, fixture-matcher safe), section
'descriptions' w/ failed-honesty, additive SoA + getDescription
(CS-aware), buildSchemaContext BYTE-IDENTICAL (parity 10/10; privacy
gate test: descriptions never in schema context/remoteLm). FIXES en
route: declare-type reader stopped at TYPE_ENDERS (module params typed
"int AS"); reserved-word builtins (LEFT/COALESCE/CONVERT…) accepted as
callees.

TESTS: 111 hover (bar 80) + 60 signature (bar 60) + 6 H7 — full honesty
set (per-section lite/loading/failed, offline, SELECT INTO, ALTER'd
temps, MERGE, USE switch, cross-db/linked refusal, CS collation,
ambiguity, comments/strings/sqlcmd never hover). Targeted band 480/0.

DEVIATIONS: PK/FK badges from the existing seam (no IPinnedMetadataView
widening); column counts require columns==='ready' strictly; activeParameter
unclamped (LSP-conformant); INSERT bare-column hover restricted to the
column-list span.

FINDINGS for B12: SourceRef.span excludes the alias (definition-on-alias
needs resolveQualifier); hoist readChainAround/findEnclosingCall to core/
(third copy otherwise); callee/name classifiers must whitelist
reserved-word builtins; catalog pinned view fkTo still returns empty
column pairs (snapshot has getForeignKeyDetailsTo — wire through for
referenced-side badges); H7 values CAST nvarchar(4000) — silent
truncation fine for hover, revisit for scripting F2.

VERIFIED (2026-07-06): tsgo both configs clean; repo build 0 errors;
full suite 3888 passing / 12 pending / 1 failing (known flake; targeted
band 480/0 incl. golden parity 10/10, OE 21, store 8, scale 5); gates
20/20 (run 2026-07-06T07-07-26Z_c4496083). Trees clean at 8d9393943.

NEXT: B12 / LS-4 scripting engine + definition/peek.

## 2026-07-06 - Entry 6: B12 / LS-4 COMPLETE (scripting engine + definition/peek)

SHIPPED — vscode-mssql core: f72652c4a (sqlScripting purity clause) +
ls: 55a97f065 + qs: 2a94d6c5d:
- src/sqlScripting/**: pure engine — SqlScriptingEngine facade;
  ModuleEmitter (verbatim module text, token-level CREATE/ALTER/CREATE OR
  ALTER head rewrites preserving comments, capability-gated ≥13.0.4001/
  14+); CreateTableEmitter F1 (columns/types/nullability/identity/PK) +
  F2 (named PK/UNIQUE key-order, named FKs w/ ordered pairs,
  MS_Description comments); DmlTemplateEmitter; anchor-tracking writer;
  FIDELITY NOTES on every script (defaults/checks/indexes/collation/
  seed-inc always declared missing); encrypted/permission honesty
  (refusals, never fabricated scripts). Triggers/drop/dropAndCreate/
  synonym-targets honestly unsupported (recorded deviations).
- features/definition.ts: §13.4 routing — script-local symbols to EXACT
  in-document ranges (alias declarations token-located per the B11
  span finding; CTE/temp/derived column anchors); catalog objects/
  columns → scripted definitions w/ anchors. core/nameChain.ts: hover/
  signature resolvers HOISTED (B11 finding; reserved-builtin whitelist
  centralized). catalogProvider: definitions readiness="lazy",
  getKeyConstraints, fkTo NOW SERVES H5B COLUMN PAIRS (B11 residual
  closed). Router definition=preview.
- qs: LAZY sys.sql_modules per-object reads (per-generation cache,
  in-flight dedupe, IsEncrypted vs permission disambiguation, failures
  never cached) + per-entry SESSION LANE (runExclusive) serializing
  hydration/digest/lazy reads on the one-active-query session (real
  contention-class fix); store lease getModuleDefinition; mssql-def:
  TextDocumentContentProvider (cacheKey {db}:{objectId}:op:{generation},
  LRU 32, honest expiry, opens Beside at anchor);
  mssql.sqlLanguage.definition.mode (peek|open).

TESTS: +131 (62 scripting goldens, 53 definition, 11 lazy-read, 5
delivery). Targeted band 611/0; golden parity 10/10.

FINDINGS for B13/B14: webview Monaco could host a real peek widget via
in-webview models (removes the "no definition" toast for scripted
targets — B13 polish); document-symbols/highlights can reuse
creationSpan/findNameTokenIn; B14 head-to-head must account for lazy
definition reads queueing behind in-flight hydration (cold path);
cacheKey shape is the sharing unit for future OE v2 Script-As commands.

VERIFIED (2026-07-06): tsgo both configs clean; repo build 0 errors;
full suite 4019 passing / 12 pending / 1 failing (known flake); gates
20/20 (run 2026-07-06T09-10-18Z_aa6db70c) against the dispose-ack-FIXED
service (sqltoolsservice 328b47b6 — P0 latent determinism bug found by
the M7 10k sweep, seed 7496: query.cancel during Disposing stomped the
dispose ack; see sqltoolsservice artifacts/verification-report.md).
Trees clean at 2a94d6c5d.

NEXT: B13 semantic polish + B14 audit/flip remain per plan (P1 — not in
the current remaining-tasks P0 queue). Remaining-tasks queue continues:
STS2-3 maxCellBytes + QS-3 wide/blob scenarios.

## 2026-07-07 - Entry 7: LS fill-out (diagnostics/hover/signature to live parity)

Karl reported no squiggles/tooltips in Query Studio. Journal proved all
features were wired and passes ran; the real gaps were fixed and shipped
as vscode-mssql ls: 3a7eb3c8e + qs: 11b2f742f:
- System-object catalog: curated data moved src/copilot -> sqlLanguage/data
  (copilot re-exports), pinned-view decorator at the engine pin seam;
  sys/INFORMATION_SCHEMA resolve for completion/hover/diagnostics/
  signature/definition. Live wins; negative objectIds; column 207s stay
  suppressed (curated subsets); closes the round-3 follow-up 1b.
- T1 unrecognized statement: unmapped identifier head + reserved body
  betrayal word => error with did-you-mean (SEL+ECT split detected).
  Proc-call heads stay silent by construction.
- Diagnostics hydration kick: columnsNotReady now fires the de-duped
  requestHydration (background) so 207 checks self-heal.
- mssql.intelliSense.* gates the native engine (suggestions=completions+
  signature, quickInfo=hover, errorChecking=diagnostics); >100-error
  passes withheld (tooManyDiagnostics, stateless); hover/signature/
  definition converge on textHash like completions.

VERIFIED (2026-07-07): tsgo both configs; full suite 4231 passing / 12
pending / 1 failing = the now-IDENTIFIED pre-existing flake
(CopilotChatEntry before-each hook timeout; passes in isolation).
Targeted sqlLanguage band 514/0. Trees clean at 11b2f742f.

## 2026-07-09 - Entry 8: Structural unit-run diagnostics (dogfood-driven)

Karl's repro (`select * from sys.all_columns c WHE er c.column_id != 0` —
no squiggle) exposed the architectural gap: the sketcher swallows
unparseable residue into the enclosing clause span, and nothing validated
depth-0 token sequences. Probing showed five common typo shapes producing
nothing or a MISLEADING 207 ("select a b c" → invalid column 'a').

Fix (`features/diagnostics.ts` `checkStructuralUnitRuns`, T1): SQL grammar
never allows runs of adjacent VALUE UNITS (dotted chains incl. call parens,
literals, variables, parenthesized groups) without a separator — threshold
3 where trailing aliases are legal (selectList/from/output/into/residue),
2 in expression clauses (where/on/having/groupBy/orderBy/setAssignments);
residue directly after an expression clause INHERITS its run (trailing
junk falls outside the sketched span). Extras: item-head `* name`
("select * form t" — `*` cannot take an alias), dangling comma before a
clause keyword, GROUPING/SETS/ROLLUP/CUBE breakers in groupBy. Reporting:
once per run, positioned at the run word within one Damerau edit / prefix
of a clause-appropriate keyword (per-clause candidate sets → "did you mean
WHERE/JOIN/SET?"), else at the crossing unit; mssql(102) errors; flagged
statements count syntaxUntrusted and skip ALL binder claims (kills the
misleading 207s). Mid-edit honesty: runs touching the document's last
significant token stay silent (typing "where a b|" toward BETWEEN).

Catches now: WHE er (split+typo), wher-as-alias, joim, update...st,
a b c select list, "= 1 2", "select * form", "select id, from". Verified:
12 new tests, all 176 diagnostics tests green (HONESTY SUITE untouched),
26-statement legal-SQL battery (temporal, TABLESAMPLE, PIVOT, GROUPING
SETS, FOR XML, OPENJSON, hints, window functions) zero false positives.
Full suite 4371/3 known pre-existing. Commit e168c7697.
