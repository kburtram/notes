# Schema Visualizer — Execution Plan

Living build plan. Normative precedence (highest first) — **addendum WINS on conflict**:

1. `schema_visualizer_design_review_addendum.md` (REVIEWED WITH REQUIRED REVISIONS, 2026-07-14) — normative, requirements language
2. Karl's ratification answers (recorded in Decision log below)
3. `visualizer_design.md` (2026-07-13) — architecture + context; unamended sections remain in force

`PROGRESS.md` journal wins over this plan on conflict.

## Working tree

- **Code: `C:\repos\test\langsrv2`** (vscode-mssql, sqltoolsservice, perftest — all `dev/query`). Docs stay in `C:\repos\test\langsrv\notes\vscode-ext-refactor\schema-visualizer\`.
- Heads at build start: vscode-mssql `cfa51b8fa`, sqltoolsservice `018140e2`, perftest `5abc11f` (all clean). NOTE: newer than the heads the addendum reviewed (`37396c3c4` / `88c6149b` / `83e017b9`) — re-verify symbols before editing (addendum §20.1).
- Commit prefixes: `sv:` visualizer feature · `qs:` metadata substrate · `core:` shared extraction / legacy designer instrumentation / v1 updater fixes. Never mix file sets in one commit.
- Live lanes: `STS2_SQLSERVER_SQLLOGIN_CONNSTRING` (local SQL 2025), `STS2_AZURESQLSERVER_CONNSTRING`. Skip-not-fail.

## Decision log (never edit past entries)

| ID | Decision | Source |
|---|---|---|
| D1 | Net-new surface; no backend toggle in shipping designer | design §3, addendum §3.1 |
| D2 | Reads ONLY via MetadataStore leases; no ad-hoc SQL, no v1 for reads, no C# metadata endpoint | addendum §3.2 |
| D3 | Command-scoped legacy handoff; v1 state only after explicit Preview/Publish | addendum §3.3 |
| D4 | DacFx remains apply authority; no self-executed ALTER | addendum §3.4 |
| D5 | P0 = tables-only, read-only. **Views: revisit later** (Karl) — tracked as SV-R11 item, needs capability + visual-language decision | Karl + addendum §3.5/§22.2 |
| D6 | Commit prefix `sv:` confirmed | Karl |
| D7 | Entry points: command palette + **OE v2 database-node menu item**. Classic OE keeps its existing item → old designer, untouched. Classic-OE entry for the visualizer: deferred | Karl + addendum §22.4 |
| D8 | Shared graph components: addendum verified they are NOT pure (A-12) → do the minimal provider-neutral `core:` extraction (SV-R3) before the page depends on them. Karl's "extract on first change" is satisfied in spirit: the impurity finding IS the first change trigger; hard constraint is zero legacy behavior change | Karl + addendum §10/§22.1 |
| D9 | Canonical identity-rich availability-aware model is the truth; `SchemaDesigner.Schema` is an adapter DTO at graph/legacy boundaries only | addendum §4 |
| D10 | Stable graph IDs `table:<objectId>` / `column:<objectId>:<columnId>` / `fk:<constraintObjectId>` / `new-*:<uuid>`; NO generation in IDs; GUIDs minted only at STS replay boundary | addendum §4.4/§4.5 |
| D11 | FK actions mapped by `*_desc` string switch, never numeric cast (catalog 0=NO_ACTION/1=CASCADE vs OnAction 0=CASCADE/1=NO_ACTION) | addendum §5.5 |
| D12 | Identity seed/increment carried as lossless text end-to-end; identity EDITING blocked until wire exactness decided (addendum §5.3 option 3 initially) | addendum §5.3/§22.9 |
| D13 | Drift = visualizer fingerprint change, never generation change; pre-preview = forced `requireLive` full-section snapshot + rebase; preview token gates publish; same v1 session preview→publish | addendum §6/§8.4 |
| D14 | DacFx failure is the safety net, but what we send MUST represent user intent in the designer UI (correlation preconditions, no fabricated values) | Karl + addendum §4.2 |
| D15 | Script output informational-only; compatibility goldens on safe fixtures, correctness (not byte parity) on edge cases | addendum §12/§22.6 |
| D16 | Large-catalog policy: measured internal threshold (~500 start), search-first for large, O(1) lookup layout, cancelable; `ready` = first meaningful paint | addendum §11 |
| D17 | Default/computed edits stay read-only until v1 updater fixed + tested (`core:` in sqltoolsservice) | addendum §9/§22.10 |
| D18 | Bundle acceptance = behavior + budgets, not chunk-graph byte identity | addendum A-17/§10.5 |
| D19 | Backcompat not required for the new surface; don't break existing features; avoid duplicating code unless necessary | Karl |
| D20 | Autonomous run: no user checkpoints; verify continuously via tests + log/diag analysis; PROGRESS.md is the durable state | Karl |

## Phases (addendum §18 — SV-R IDs are canonical)

| ID | Scope | Exit gate |
|---|---|---|
| SV-R0 | Docs, decision log, head verification, register only MISSING markers (schemaVisualizer family + legacy rendered-ready), re-vendor | contracts/vendor/parity tests green |
| SV-R1 | Metadata identity + exact detail (`qs:`): column_id, FK ids/pair ids, SqlTypeSpec facts, identity text, defaults, computed, FK action desc; codec version bump | determinism/codec/action-map/exact-value tests green |
| SV-R2 | Canonical model, capability matrix, fingerprint, graph projection, reducer skeleton (`sv:`) | stable-ID + unchanged-generation invariants green |
| SV-R3 | Provider-neutral `webviews/shared/schemaGraph/` extraction (`core:`) | legacy designer behavior + budgets green; independently revertible |
| SV-R4 | Read-only surface: activation/manager/controller/page/flag/command/OE v2 entry/properties/large-catalog policy | no-v1 tripwire, honesty matrix, live open lane, first-paint marker |
| SV-R5 | Informational SQL definition (P0.1) | compat + correctness goldens |
| SV-R6 | Op capture/normalized log/undo-redo/rebase UX | reducer/normalization/restore/conflict suites |
| SV-R7 | v1 updater fixes + lossless identity wire decision (`core:` sqltoolsservice) | §9 tests green or ops stay disabled |
| SV-R8 | Classic resolver, handoff state machine, correlation/replay, report+publish | lifecycle/preview-token/live-round-trip/drift-race tests |
| SV-R9 | Diagnostics/telemetry polish, Debug Console verification | privacy + trace composition |
| SV-R10 | Perftest: model-phase + rendered-phase pairs, warm/cold, large-catalog diagnostics | first A/B archived; metrics unofficial |
| SV-R11 | Deferred decisions: DAB, views, Table Explorer / classic OE entries, advanced details | separate design notes |

**P0 = SV-R0..R4.** Standing verification chain per batch: tsgo typecheck → `npm run build` → targeted `npx vscode-test` suites → full-suite pass-count watch (4 known dev/query pre-existing failures: sqlScripting strict-host, sqlLanguage sys catalog, OE v2 stableProfileId, CopilotChatEntry flake — anything else is ours) → perftest contracts parity/vendor-sync when registry touched.

## Standing constraints (addendum §20 — verbatim obligations)

Re-read symbols before editing (line numbers stale). One seam per commit. No fabricated metadata. No generation in IDs/fingerprints-as-content. No `typeDisplay` reverse-parsing. No FK enum casts. No lossy identity numbers. No secrets/identifiers in logs or diag. No v1 outside the handoff machine. Dispose every v1 session. No silent rebase. No unbounded sync layout. No stateful component copies under new names. Generated SQL informational only.
