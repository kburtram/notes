# Preview release notes draft — Query Studio + SQL AI Completions (Phase 2)

Status: DRAFT (B7/M6, 2026-07-05). Source of truth for what ships behind the
preview gates and what we say about it. Trim marketing-speak before use.

## Feature summary

### Query Studio (preview, `mssql.queryStudio.enabled`)
An SSMS-parity composite query editor for `.sql` files: Monaco editor with
host-synced text, GO batch splitting with continue-on-error semantics,
streaming results grid with spill-backed row store, verbatim Messages tab
with click-to-line, estimated/actual plan capture, database dropdown +
script `USE` tracking, cancel with honest partial results. Runs exclusively
on the STS2 data plane (`mssql.sqlDataPlane.enabled`, backend
`sts2-jsonrpc`).

### SQL AI inline completions (ported + integrated)
The completions engine (intent detection, schema-aware prompts, sanitizer
chain, model selection incl. Anthropic/OpenAI/xAI SDK providers via
`languageModelChatProviders`) now runs against the MetadataService catalog
in BOTH editors: the classic query editor (standard VS Code inline
completions) and Query Studio's Monaco surface (ghost text over the same
provider pipeline, acceptance telemetry identical).

### Observability & replay (the part reviewers should poke at)
- Every layer is instrumented on one substrate: editor markers
  (`queryStudio.*` incl. cancel/windowFetch/sync spans), data-plane spans
  (`sqlDataPlane.*`), metadata spans (`metadata.hydrate/contextBuild/
  drift`), completions pipeline (`completions.request` span + stage/result
  instants), all visible on the Debug Console timeline with Trace Identity
  correlation.
- A shared feature-capture framework provides rich event capture with
  settings snapshots, session-only overrides, trace files (redaction +
  size caps), and a generic replay engine (cart, snapshot/override/live
  config modes, sequential + matrix runs, replay tagging).
- **Completions debug panel**: full event capture (stages, prompts under
  gated capture, applied settings), replay cart with per-row config
  overrides, matrix runs (profile × schema budget), trace session browser.
- **Query Studio Replay Lab** (`mssql.queryStudio.openReplayLab`): every
  armed run captures a QsRunRecord (batch descriptors, outcomes, timings,
  catalog generation); replay re-drives records through the normal data
  plane with database/mode overrides, sequential or matrix.

## Privacy model (verbatim for docs)
- SQL text, result rows, prompts: NEVER in diagnostics by default. Run
  records store salted digests; replayable SQL text requires explicit
  Debug Console elevated capture (time-bounded, local-only) and the
  effective policy is recorded on every record.
- Secrets/connection strings/tokens: never plaintext in any mode.
- Spill files hold result data locally and are excluded from exports.
- Privacy canary suites cover classification, session journals, harness
  wire, run-record traces, completions trace redaction, and settings
  snapshots (secret-pattern settings always tokenized).

## Settings (preview surface)
`mssql.queryStudio.enabled`, `mssql.queryStudio.replay.enabled`,
`mssql.sqlDataPlane.enabled` / `.backend`, `mssql.metadata.*`,
`mssql.copilot.inlineCompletions.*` (incl. trace.* capture controls),
`mssql.copilot.sdkProviders.*`.

## Known gaps at preview (honest list)
- Shadow-LSP language bridge (completions/hover in QS Monaco beyond AI
  ghost text) not yet wired; `queryStudio.lsp.*` spans reserved.
- STS2 worksheet row 1 (verbatim result-stream messages) must be verified
  against the service before any parity CLAIM ships in docs.
- Replay of digest-only records is refused by design (capture with
  elevation to replay).
- Debug Console `completions`/`replay` left-rail pages point at the
  dedicated panels; embedded DC pages are follow-up UX.
- B5 disk cache (catalog persistence across sessions) not yet shipped.
