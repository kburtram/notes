# New Settings Reference (dev/query vs main)

Every setting added on the `dev/query` branch (59 as of vscode-mssql `55cd1d36e`), grouped by feature, plus pastable snippets at the bottom. Defaults shown are the shipped defaults — **everything is off by default** except the Debug Console itself and the language-service niceties.

Related: command visibility follows these settings — a disabled feature hides its palette commands (no more "command not found").

---

## 1. SQL Data Plane (STS2)

The typed query/connection transport every new feature runs on. Turn this on first; Query Studio, OE v2, metadata, and central upload all ride it.

| Setting | Default | What it does |
|---|---|---|
| `mssql.sqlDataPlane.enabled` | `false` | Master switch for the STS2 data plane. |
| `mssql.sqlDataPlane.backend` | `"sts2-jsonrpc"` | Backend binding (`fake` is for tests; http/rest reserved). |

Command: `MS SQL: Show SQL Data-Plane Status` (visible when enabled).

## 2. Query Studio

| Setting | Default | What it does |
|---|---|---|
| `mssql.queryStudio.enabled` | `false` | The Query Studio custom editor + all `mssql.queryStudio.*` commands (New Query, Reopen Active, Open in Classic Editor, Duplicate, Replay Lab, Language Service Status). Late-enables without reload. |
| `mssql.queryStudio.languageService.engine` | `"sqlToolsService"` | `nativeTypeScript` prefers the new native T-SQL language service for graduated features (completions, diagnostics, definition). |
| `mssql.queryStudio.replay.enabled` | `false` | Capture run records for the Replay Lab even while its panel is closed. Records hold SQL **digests** only; replayable SQL text additionally needs Debug Console elevated capture. |

## 3. Native T-SQL language service (`mssql.sqlLanguage.*`)

Behavior knobs for the native engine (used when the engine toggle above is `nativeTypeScript`).

| Setting | Default | What it does |
|---|---|---|
| `mssql.sqlLanguage.completions.snippets` | `true` | Snippet items in completions. |
| `mssql.sqlLanguage.diagnostics.enabled` | `true` | Native diagnostics (18-reason freshness-honest ladder). |

The classic `mssql.intelliSense.*` switches (pre-existing settings, not new) now gate the native engine too: `enableIntelliSense` is the master; `enableSuggestions` covers completions **and** signature help; `enableQuickInfo` covers hover; `enableErrorChecking` gates diagnostics alongside the setting above. Also: a diagnostics pass producing more than 100 errors is withheld entirely (a text file opened as .sql shouldn't drown in squiggles) — it self-heals per pass and shows up as `tooManyDiagnostics` in the Language Service Status suppression counts.
| `mssql.sqlLanguage.keywordCasing` | `"upper"` | Keyword casing for completions/formatting. |
| `mssql.sqlLanguage.definition.mode` | `"peek"` | Go-to-definition shows scripted objects as a peek preview or a pinned read-only tab. |

## 4. Object Explorer v2

| Setting | Default | What it does |
|---|---|---|
| `mssql.objectExplorer.viewMode` | `"classic"` | `v2Preview` switches the OE view to the new MetadataStore-backed tree. |
| `mssql.objectExplorer.v2.showSystemDatabases` | `true` | Show system DBs in the v2 tree. |
| `mssql.objectExplorer.v2.groupBySchema` | `false` | Group objects by schema folders. |
| `mssql.objectExplorer.v2.tablePreviewRowLimit` | `1000` | Row cap for "Preview Table Data". |
| `mssql.objectExplorer.v2.confirmLegacyHandoff` | `true` | Confirm before a v2 command creates a legacy STS v1 connection for a feature handoff. |

## 5. Metadata service + persistent cache

| Setting | Default | What it does |
|---|---|---|
| `mssql.metadata.pollSeconds` | `60` | Base cadence for the background drift-digest poll (0 disables). Backoff to 5×, focus suspension, serverless floor apply automatically. |
| `mssql.metadataCache.enabled` | `false` | Persistent metadata snapshot cache (disk warm-acquire ~9 ms vs live hydration). |
| `mssql.metadataCache.maxAgeDays` | `14` | Snapshot eviction age. |
| `mssql.metadataCache.maxBytes` | `268435456` | Cache size budget (256 MiB). |
| `mssql.metadataCache.offlineMode` | `false` | Serve exclusively from persisted snapshots; strict operations (scripting) refuse or banner. |

Commands (visible when enabled): `Metadata Cache: Show Status / Clear All / Clear for Connection / Enable Offline Mode / Disable Offline Mode`.

## 6. Debug Console + session diagnostics

| Setting | Default | What it does |
|---|---|---|
| `mssql.debugConsole.enabled` | `true` | The in-product diagnostics console (`MS SQL: Open Debug Console`). |
| `mssql.debugConsole.richCollection` | `false` | CPU/memory/event-loop counters and per-span deltas while capture is active (diagnostic-only; off = zero overhead). |
| `mssql.debugConsole.richSnapshotHeartbeat` | `false` | ALSO journal the 2s system.rich.snapshot heartbeat (noisy; per-span deltas usually suffice). |
| `mssql.debugConsole.perfRunsRoot` | `""` | Where in-product self-test runs are stored/imported from (defaults to global storage). |
| `mssql.sessionDiag.enabled` | `false` | Auto-capture classified, redacted diagnostics from startup to shutdown, across sessions. Local only; secrets/connection strings never persisted regardless of mode. |
| `mssql.sessionDiag.captureMode` | `"redacted"` | Default capture mode (`digest` keeps hashes of identifiers). `full` exists only via the time-bounded elevation command. |
| `mssql.sessionDiag.maxSessions` / `maxAgeDays` / `maxTotalMB` | `10` / `14` / `512` | Local store retention. |
| `mssql.sessionDiag.storePath` | `""` | Override the local journal location. |

Commands: `Session Diagnostics: Enable / Disable / Elevate Capture (time-bounded) / Clear Local Data / Open Storage Folder`.

## 7. Central observability upload

| Setting | Default | What it does |
|---|---|---|
| `mssql.centralObservability.enabled` | `false` | "Upload to shared server" in the Debug Console (Exports page). |
| `mssql.centralObservability.targetProfileId` | `""` | Saved connection (profile id or name) whose pinned database holds the central store. No connection strings. |
| `mssql.centralObservability.defaultUploadPolicy` | `"team-default.v1"` | Boundary policy: team-default digests names/paths, drops SQL/rows/prompts/credentials; team-names keeps metadata names; elevated-support also keeps paths. Secrets always refused. |
| `mssql.centralObservability.maxItemBytes` | `1572864` | Per-execute upload batch text budget (tuning knob). |

## 8. AI inline completions (`mssql.copilot.*`)

Gate = `mssql.enableExperimentalFeatures` (pre-existing) **AND** `useSchemaContext`. Easiest path: Debug Console → Completions → **Enable AI completions** (writes both + quiets GitHub Copilot for SQL).

| Setting | Default | What it does |
|---|---|---|
| `mssql.copilot.inlineCompletions.useSchemaContext` | `false` | THE feature switch (with the experimental flag). Builds live schema context for prompts. |
| `mssql.copilot.inlineCompletions.includeSqlDiagnostics` | `true` | Include current SQL diagnostics in the prompt. |
| `mssql.copilot.inlineCompletions.profile` | `"balanced"` | Schema-context budget profile (`focused`/`balanced`/`broad`). |
| `mssql.copilot.inlineCompletions.modelFamily` | `"claude-sonnet-4-6"` | Preferred model family. |
| `mssql.copilot.inlineCompletions.continuationModelFamily` | `""` | Optional cheaper/faster family for continuation-category requests. |
| `mssql.copilot.inlineCompletions.modelVendors` | copilot, anthropic-api, openai-api, xai-api | Vendor priority order for `vscode.lm` model selection. |
| `mssql.copilot.inlineCompletions.enabledCategories` | `["continuation","intent"]` | Which completion categories fire. |
| `mssql.copilot.inlineCompletions.debug.recordWhenClosed` | `false` | Keep recording debug-viewer events while the panel is closed. |
| `mssql.copilot.inlineCompletions.trace.captureEnabled` | `false` | Persist completion traces to disk (feeds the viewer's Sessions tab + replay). |
| `mssql.copilot.inlineCompletions.trace.folder` | `""` | Trace folder override. |
| `mssql.copilot.inlineCompletions.trace.redactPrompts` | `false` | Strip prompt text from persisted traces. |
| `mssql.copilot.inlineCompletions.trace.maxFileSizeMB` | `50` | Trace file cap. |

**SDK model providers** (each of `anthropic` / `openai` / `xai`, all `mssql.copilot.sdkProviders.<vendor>.*`): `enabled` (default false, **requires reload**), `baseUrl`, `timeout` (60000), `env` (API-key env var name or value), `additionalModels`. API keys go in SecretStorage via the `Set <Vendor> API Key` commands (palette-visible once completions are enabled). Without any SDK provider, vendor `copilot` (GitHub Copilot Chat sign-in) is used.

---

## Common settings — pastable snippets

### Turn on everything

```jsonc
{
    // transport + editors
    "mssql.sqlDataPlane.enabled": true,
    "mssql.queryStudio.enabled": true,
    "mssql.queryStudio.languageService.engine": "nativeTypeScript",
    "mssql.queryStudio.replay.enabled": true,
    // object explorer v2
    "mssql.objectExplorer.viewMode": "v2Preview",
    // metadata service + cache
    "mssql.metadataCache.enabled": true,
    // diagnostics: always-on local capture + rich counters
    "mssql.sessionDiag.enabled": true,
    "mssql.debugConsole.richCollection": true,
    // central observability (target = saved profile named central-store,
    // database pinned to PerfCentral — see how_to_use_perftest.md §5)
    "mssql.centralObservability.enabled": true,
    "mssql.centralObservability.targetProfileId": "central-store",
    // AI completions (or click Enable on the Debug Console Completions page)
    "mssql.enableExperimentalFeatures": true,
    "mssql.copilot.inlineCompletions.useSchemaContext": true,
    "mssql.copilot.inlineCompletions.trace.captureEnabled": true
}
```

### Test Query Studio (+ native language service)

```jsonc
{
    "mssql.sqlDataPlane.enabled": true,
    "mssql.queryStudio.enabled": true,
    "mssql.queryStudio.languageService.engine": "nativeTypeScript"
}
```
Then: `MS SQL: Query Studio: New Query`, or open a `.sql` file and `Reopen Active Document in Query Studio`. `Language Service Status` shows the engine's decision trace; `Open Replay Lab` needs `mssql.queryStudio.replay.enabled`.

### Test Metadata Service (+ cache + drift)

```jsonc
{
    "mssql.sqlDataPlane.enabled": true,
    "mssql.queryStudio.enabled": true,
    "mssql.metadataCache.enabled": true,
    "mssql.metadata.pollSeconds": 30
}
```
Then: connect, open Query Studio (completions hydrate the store), restart VS Code and reopen — warm acquire should come from disk (`Metadata Cache: Show Status`, look at `source`). Rename a table out-of-editor to watch drift validation; `Enable Offline Mode` to test snapshot-only honesty.

### Test OE v2

```jsonc
{
    "mssql.sqlDataPlane.enabled": true,
    "mssql.objectExplorer.viewMode": "v2Preview",
    "mssql.queryStudio.enabled": true   // for "New Query (Query Studio)" on nodes
}
```
Then use the OE view: expand/filter/search, Preview Table Data, Script SELECT TOP, and a legacy action to see the confirmed handoff.

### Test AI completions

```jsonc
{
    "mssql.sqlDataPlane.enabled": true,
    "mssql.enableExperimentalFeatures": true,
    "mssql.copilot.inlineCompletions.useSchemaContext": true
}
```
Or press **Enable AI completions** on Debug Console → Completions (also quiets GitHub Copilot for SQL). Needs a model: GitHub Copilot Chat signed in, or `mssql.copilot.sdkProviders.anthropic.enabled: true` + reload + `Set Anthropic API Key`. Open a **connected** `.sql` editor, type, watch ghost text; `MSSQL: Open Inline Completion Debug` (or the button on the Completions page) for full request/prompt/response fidelity.

### Test central observability (product side)

```jsonc
{
    "mssql.centralObservability.enabled": true,
    "mssql.centralObservability.targetProfileId": "central-store",
    "mssql.sessionDiag.enabled": true
}
```
Save a profile `central-store` → `localhost,14333` / database `PerfCentral` (SQL auth, see how_to_use_perftest.md §5). Capture a session, close it (disable capture or restart), Debug Console → Exports → Preview upload → Upload.
