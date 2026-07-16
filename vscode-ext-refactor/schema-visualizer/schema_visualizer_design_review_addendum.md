# Schema Visualizer Design Review Addendum

**Status:** REVIEWED WITH REQUIRED REVISIONS  
**Review date:** 2026-07-14  
**Applies to:** `visualizer_design.md`, dated 2026-07-13  
**Source document SHA-256:** `10a3e8c8c176e0b4e07770e3c2bdc1bbadba8f68ff44605eb627eb99297ed05a`  
**Target branch:** `dev/query` in all three repositories  
**Disposition:** Approve the architectural direction, subject to the normative corrections in this addendum.

Reviewed repository heads:

| Repository | `dev/query` head reviewed |
|---|---|
| `microsoft/vscode-mssql` | `37396c3c44e1c80224b7261894dd14b06abb46a0` |
| `microsoft/sqltoolsservice` | `88c6149bce6caef21e00662011c03db20be6bbbc` |
| `kburtram/perftest` | `83e017b95e55e680aa811a5f9baa2bb755d94da6` |

## 0. Precedence and interpretation

This addendum is normative for implementation.

Where this addendum conflicts with `visualizer_design.md`, this addendum wins. Sections of the original design not changed here remain in force.

The terms **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements language for the implementation agent.

Repository paths and symbol names are more authoritative than line numbers. The branches are active and line numbers will move.

---

## 1. Executive review

The central architecture is correct:

1. Build a separate, configuration-gated Schema Visualizer surface.
2. Read schema data only through `MetadataStore` leases backed by the SQL Data Plane.
3. Add no STS2 schema-designer endpoint.
4. Permit legacy STS v1/DacFx traffic only after an explicit Preview or Publish action.
5. Keep DacFx authoritative for report and apply.
6. Reuse visual design and rendering code where it is genuinely provider-neutral.
7. Ship tables-only, read-only P0 first.
8. Defer DAB, views, and classic Object Explorer integration.

The plan should not be implemented exactly as written, however. Several details currently turn a sound architecture into a correctness risk:

- A metadata `generation` is a hydration sequence number, not a schema-content revision.
- `requireValidated` currently uses a cheap database digest that does not cover columns, keys, foreign keys, defaults, identities, or computed-column details.
- Graph IDs containing `generation` are unstable across harmless refreshes.
- The legacy `SchemaDesigner.Schema` DTO cannot faithfully represent unknown metadata, catalog identities, exact identity values, or richer type information.
- The existing webview does define semantic edit types, but normal UI editing and undo/redo do not currently produce a semantic operation log.
- The existing OE v2 classic-handoff service returns an owner URI, not the connection string and token required by `schemaDesigner/createSession`.
- The v1 report and publish calls form a stateful transaction-like sequence that needs an explicit lifecycle and revision token.
- The v1 updater has correctness holes for default-only and computed-column-only changes.
- SQL catalog FK action numbers cannot be cast directly to the existing `OnAction` enum.
- The current synchronous Dagre layout is likely to dominate large-catalog opening time, regardless of a fast metadata acquire.

The recommended disposition is therefore:

> **Ratify the architecture, amend the data model and commit protocol, then implement.**

---

## 2. Findings requiring design changes

| ID | Severity | Finding | Required disposition |
|---|---|---|---|
| A-01 | Blocker for edits | `CatalogSnapshot.generation` increments after every successful hydration, including unchanged hydrations. | Do not use generation as drift detection, object identity, or a rebase token. |
| A-02 | Blocker for stable UI | Proposed IDs such as `sv:<generation>:<objectId>` change on every hydration. | Use catalog IDs independent of generation. |
| A-03 | Blocker for publish safety | `requireValidated` presently validates with the T1 cheap digest, which covers object-level facts but not the full designer projection. | Use a forced live refresh and an explicit visualizer fingerprint before preview/publish. |
| A-04 | Blocker for correctness | `SchemaDesigner.Schema` requires concrete values where metadata may be unknown and lacks catalog identities and exact type semantics. | Introduce a canonical Schema Visualizer model, then adapt it to the legacy graph shape. |
| A-05 | Blocker for rename-safe replay | The metadata store currently discards `sys.columns.column_id` and FK pair column IDs. | Retain table, column, FK constraint, and FK pair IDs in the substrate. |
| A-06 | Blocker for numeric fidelity | TS uses JavaScript `number` for identity seed/increment while STS uses nullable `decimal`; `sys.identity_columns` exposes `sql_variant`. | Preserve exact values as strings or another lossless representation until the v1 boundary. |
| A-07 | Major | A semantic `SchemaDesignerEdit` union already exists, but manual UI operations and undo/redo are graph-snapshot based. | Reuse it as ingress vocabulary, but normalize to an internal operation format with identities and preconditions. |
| A-08 | Blocker for handoff | `PreparedConnection` does not contain enough information to reconstruct a classic connection string, and `OeV2ClassicHandoffService` exposes an owner URI rather than schema-designer credentials. | Add a dedicated, injected classic publish resolver. |
| A-09 | Blocker for lifecycle | `publishSession` publishes the DacFx state prepared by the most recent successful `getReport`. | Keep the same v1 session alive through preview and confirmation, and invalidate it on any edit or drift. |
| A-10 | Blocker for some edits | `DeepCompareColumn` omits default and computed fields; formula/persisted changes are not reliably propagated when `IsComputed` remains true. | Fix and test the v1 updater before enabling those edit operations. |
| A-11 | Blocker for FK fidelity | SQL catalog referential-action values and `SchemaDesigner.OnAction` numeric values differ for NO_ACTION and CASCADE. | Map by explicit switch or description string. Never cast. |
| A-12 | Major | `SchemaDesignerFlow` and `SchemaDesignerTableNode` import legacy state context, event buses, diff providers, and Copilot providers. | Extract a provider-neutral graph shell before relying on shared imports. |
| A-13 | Major | Current Dagre layout is synchronous, and edge setup performs a `nodes.find` for each edge. | Add O(1) node lookup, a large-catalog policy, and cancelable/off-main-thread layout where needed. |
| A-14 | Major | The proposed byte-parity script goal would preserve legacy generator limitations such as unescaped identifiers and lossy PK representation. | Separate compatibility parity from SQL correctness and label generated DDL as informational. |
| A-15 | Major | The existing perftest scenario ends at extension-host `schemaDesigner.init.end`, not webview first paint. | Add comparable model-ready and rendered-ready metrics to both surfaces. |
| A-16 | Major | Catalog visibility is permission-scoped even when queries succeed. | Model capability and visibility limits explicitly; do not interpret a successful query as globally complete schema truth. |
| A-17 | Minor/Major | Adding a second esbuild entry can legitimately reshape shared chunks. | Do not require the legacy entry's exact chunk graph to remain byte-identical. Test behavior and budgets instead. |
| A-18 | Major | Automatic webview request spans are named `webview.<source>.<method>`, not `mssql.schemaVisualizer.*`. | Register explicit product markers separately and avoid double-counting RPC spans. |

---

## 3. Ratified architectural decisions

The following decisions from the original design are accepted without reservation:

### 3.1 Separate preview surface

The Schema Visualizer remains a separate controller, command, manager, webview entry, setting, telemetry view, and diagnostics family. It must not be implemented as a backend toggle inside the shipping Schema Designer controller.

### 3.2 MetadataStore is the only read substrate

The visualizer must acquire a `DatabaseCatalogLease` through the shared `MetadataStore`. It must not:

- run ad hoc catalog SQL from the controller,
- use the user's interactive query session,
- create a second metadata cache,
- call v1 for diagram, properties, refresh, search, export, or ordinary definition display,
- add a new C# metadata endpoint.

### 3.3 Command-scoped legacy handoff

Legacy state may be created only after an explicit Preview Changes or Publish action. Merely opening, filtering, arranging, exporting, reading properties, or generating an informational definition must never create a classic connection or a v1 schema-designer session.

### 3.4 DacFx remains the apply authority

The visualizer must not generate and execute its own ALTER script as the publish mechanism. Its local edit model is converted into a v1-ID-bearing target model, then sent through `getReport` and `publishSession`.

### 3.5 P0 remains tables-only and read-only

Views, stored modules, DAB, classic Object Explorer context menus, and editable operations do not belong in the first implementation slice.

---

## 4. Required canonical model

### 4.1 Do not make `SchemaDesigner.Schema` the visualizer's source of truth

The original design proposes:

```text
CatalogSnapshot -> SchemaDesigner.Schema -> React Flow
```

That is acceptable for a short read-only spike, but not as the production model. The required production path is:

```text
CatalogSnapshot
  -> SchemaVisualizerCatalogModel
  -> SchemaGraphProjection
  -> React Flow
```

At commit time:

```text
SchemaVisualizerCatalogModel + normalized edit operations
  -> current v1 baseline from createSession
  -> v1-ID-bearing SchemaDesigner.Schema
```

`SchemaDesigner.Schema` is a compatibility DTO at the graph and legacy handoff boundaries. It is not the canonical metadata model.

### 4.2 Why a separate model is required

The legacy DTO cannot express all of the following safely:

- `object_id`, `column_id`, and FK constraint object IDs,
- ordered FK pair identities,
- known versus unknown field values,
- section readiness and failure reasons,
- schema descriptions,
- exact identity seed/increment values,
- alias/user-defined type identity,
- raw byte length versus logical character length,
- catalog collation and case-sensitivity rules,
- permission-limited or unsupported fields,
- a stable baseline fingerprint,
- table and constraint details not represented by the legacy designer.

Forcing these into required primitive fields creates fake data. Fake data is especially dangerous because an unrelated edit can accidentally publish the fabricated value.

### 4.3 Suggested core types

The implementation may adjust names, but it should preserve these concepts:

```ts
export type AvailabilityReason =
    | "sectionUnavailable"
    | "permissionLimited"
    | "notHydrated"
    | "unsupported"
    | "notApplicable";

export type Available<T> =
    | { state: "known"; value: T }
    | { state: "unknown"; reason: AvailabilityReason };

export interface CatalogEntityIdentity {
    objectId: number;
}

export interface CatalogColumnIdentity extends CatalogEntityIdentity {
    columnId: number;
}

export interface SqlTypeSpec {
    displayText: string;
    typeName: string;
    typeSchema?: string;
    systemTypeId: number;
    userTypeId: number;
    isUserDefined: boolean;
    isAssemblyType: boolean;
    maxLengthBytes: number;
    logicalLength?: number | "max";
    precision: number;
    scale: number;
    collationName?: string;
    vectorDimensions?: number;
    vectorBaseType?: number;
}

export interface VisualizerColumn {
    identity: CatalogColumnIdentity;
    graphId: string;
    ordinal: number;
    name: string;
    type: SqlTypeSpec;
    nullable: boolean;
    primaryKeyMembership: Available<{
        constraintObjectId?: number;
        constraintName: string;
        keyOrdinal: number;
    }>;
    identitySpec: Available<{
        seedText: string;
        incrementText: string;
        notForReplication?: boolean;
    }>;
    defaultConstraint: Available<{
        objectId?: number;
        name?: string;
        definition: string;
    }>;
    computed: Available<{
        definition: string;
        persisted: boolean;
    }>;
    description: Available<string>;
}

export interface VisualizerForeignKey {
    identity: CatalogEntityIdentity;
    graphId: string;
    name: string;
    fromObjectId: number;
    toObjectId: number;
    columnPairs: Array<{
        fromColumnId: number;
        toColumnId: number;
        fromColumnName: string;
        toColumnName: string;
        ordinal: number;
    }>;
    onDelete: Available<"NO_ACTION" | "CASCADE" | "SET_NULL" | "SET_DEFAULT">;
    onUpdate: Available<"NO_ACTION" | "CASCADE" | "SET_NULL" | "SET_DEFAULT">;
}

export interface SchemaVisualizerCatalogModel {
    databaseIdentity: {
        serverFingerprint: string;
        database: string;
    };
    caseSensitive: boolean;
    tables: VisualizerTable[];
    source: {
        generation: number;
        capturedAtUtc: string;
        freshness: string;
        sectionReadiness: Record<string, string>;
        fingerprint: string;
    };
}
```

This is illustrative, not a demand for every optional field in P0. The identity, availability, exact numeric, and fingerprint concepts are mandatory.

### 4.4 Stable graph identities

Do not include metadata generation in node, column, edge, layout, selection, or operation identity.

Recommended IDs:

```text
table:<objectId>
column:<objectId>:<columnId>
fk:<constraintObjectId>
new-table:<uuid>
new-column:<uuid>
new-fk:<uuid>
```

A stable profile/database key belongs in the controller/manager key, not necessarily in every node ID, because a webview instance is already database-scoped.

`object_id` can be reused after an object is dropped and recreated. That does not justify adding generation to the graph ID. Reuse is handled by the baseline fingerprint and operation preconditions.

### 4.5 Local IDs versus v1 IDs

Local catalog-backed IDs may be arbitrary stable strings.

Any `SchemaDesigner.Schema` sent to STS must use valid GUID strings for table, column, and FK IDs because the C# contracts use `Guid`.

For existing entities, copy the GUIDs from the current v1 baseline. For newly created entities, generate UUIDs at replay time or carry valid UUIDs from the internal operation model.

Never send `table:123`, `sv:7:123`, or another non-GUID local ID to STS.

---

## 5. Metadata substrate amendments

### 5.1 Retain identities already present in catalog SQL

The H3 query already retrieves `column_id`; it must no longer discard it.

The H5/H5B path must retain:

- FK constraint `object_id`,
- parent `column_id`,
- referenced `column_id`,
- constraint-column ordinal,
- parent and referenced names for display and diagnostics.

Required projection changes:

```ts
export interface ColumnInfo {
    columnId: number;
    ordinal: number;
    // existing and new details
}

export interface FkEdge {
    constraintObjectId: number;
    // existing fields
}

export interface FkColumnPair {
    ordinal: number;
    fromColumnId: number;
    toColumnId: number;
    fromColumn: string;
    toColumn: string;
}
```

Names remain useful for display and correlation diagnostics. IDs are the durable in-snapshot identity.

### 5.2 Preserve exact type semantics

Do not treat `max_length`, `precision`, and `scale` as three fields that can simply be copied into the legacy DTO.

`sys.columns.max_length` is bytes, not logical characters. For `nvarchar` and `nchar`, the logical character count is normally half the byte count. `-1` means a max type. User-defined alias types, XML, vector, and future types require more context than a name and length.

The metadata extension should retain at least:

- `column_id`,
- `system_type_id`,
- `user_type_id`,
- user type schema and name,
- system/base type name,
- `is_user_defined`,
- `is_assembly_type`,
- `max_length` in bytes,
- precision,
- scale,
- collation,
- vector metadata when available,
- a canonical display string.

Keep both raw semantics and display text. Do not attempt to reverse-parse `typeDisplay` during commit.

### 5.3 Identity values must be lossless

`sys.identity_columns.seed_value` and `increment_value` are `sql_variant`. The STS contract uses nullable `decimal`. The current TypeScript contract uses JavaScript `number`.

The metadata layer must return a normalized exact textual representation, for example:

```ts
identitySeedText?: string;
identityIncrementText?: string;
```

Do not convert to JavaScript `number` before checking range and scale. An identity value beyond `Number.MAX_SAFE_INTEGER` must not be rounded.

Before enabling identity edits, choose one of these explicit solutions:

1. Change the shared TS/C# wire contract to accept exact decimal text with validation and conversion in C#.
2. Add a handoff-only exact-value DTO and converter.
3. Temporarily block identity values that cannot be represented exactly by the legacy wire contract, with a typed error.

Silent precision loss is not acceptable.

### 5.4 Defaults and computed columns

The H3 extension should preserve:

- default constraint object ID,
- default constraint name,
- exact definition text,
- computed definition,
- computed persisted flag,
- identity seed/increment exact text,
- identity not-for-replication if edit parity requires it.

Do not collapse a missing query result, permission failure, or unsupported engine field into an empty string.

### 5.5 Foreign key actions

Query the description columns where possible:

```text
delete_referential_action_desc
update_referential_action_desc
```

Normalize them to the string union:

```text
NO_ACTION | CASCADE | SET_NULL | SET_DEFAULT
```

Do not cast the catalog's numeric value to `SchemaDesigner.OnAction`.

The catalog values are:

```text
0 NO_ACTION
1 CASCADE
2 SET_NULL
3 SET_DEFAULT
```

The existing designer enum is:

```text
0 CASCADE
1 NO_ACTION
2 SET_NULL
3 SET_DEFAULT
```

An unchecked cast swaps the two most common actions.

### 5.6 Cache codec and content hash

The current cache codec freezes payload field order and uses `CATALOG_MODEL_VERSION = "cm1"`.

For the new arrays:

- append new canonical fields rather than inserting into the existing order,
- bump the model version,
- update strict payload validation,
- update direct-array adoption,
- update determinism and round-trip tests,
- update fixture builders,
- confirm that descriptions remain excluded when cache privacy policy excludes them.

A model-version mismatch should remain a clean cache miss.

### 5.7 Visualizer-specific fingerprint

The existing snapshot `contentHash` is optional and set by the cache codec path. It is not a reliable always-present edit baseline.

Add a pure deterministic visualizer fingerprint over schema-relevant content. It should include, in canonical order:

- database identity,
- table object IDs, schema, and names,
- column IDs, order, names, exact type facts, nullability, identity, default, and computed facts,
- key identities/names/order used by the visualizer,
- FK IDs, endpoints, ordered column pairs, and actions.

It should exclude:

- generation,
- capture timestamp,
- layout positions,
- selections,
- descriptions unless descriptions become editable,
- diagnostic status messages.

Identical full hydrations must produce the same fingerprint. A change to any commit-relevant field must change it.

### 5.8 Section capability matrix

The visualizer should not use a single `mode === "partial"` switch for all behavior. Define explicit capabilities:

| Capability | Required metadata |
|---|---|
| Table list | schemas + objects |
| Diagram nodes | objects + columns |
| Relationship edges | objects + columns + foreign keys |
| Key properties | keys |
| Descriptions | descriptions, optional |
| Informational table script | columns + keys + foreign keys + exact detail fields |
| Edit a field | the field's source section must be known |
| Preview/publish | forced live snapshot, all operation-dependent sections ready |

A failed descriptions section must not prevent a table diagram. A failed columns section must not render an empty table list as though the database has no columns.

---

## 6. Freshness and drift protocol

### 6.1 Generation is not drift

A successful full hydration builds a new snapshot and increments `generation`, even when catalog content did not change.

Therefore:

- do not show a drift toast solely because generation changed,
- do not use generation in graph IDs,
- do not reject a publish solely because generation changed,
- do not treat generation equality as proof that schema content is unchanged.

Generation remains useful for cache scoping, module-definition cache lifetime, and diagnostics.

### 6.2 `requireValidated` is not a full schema validation

The current T1 cheap digest is object-oriented. It does not guarantee detection of:

- a column type change,
- nullability change,
- default change,
- computed formula change,
- identity change,
- key membership change,
- FK column mapping change,
- FK action change.

`MetadataPolicies.oeBrowse` is appropriate for responsive browsing. It is not sufficient as the last commit guard.

### 6.3 Open behavior

For read-only P0:

1. Acquire the lease.
2. Call `ensureFresh` with the OE browse policy.
3. Inspect `freshness`, `source`, `validation`, and section readiness.
4. Render a validated/live snapshot normally.
5. On timeout with a stale retained snapshot, either:
   - render it with a clear stale banner and disabled edit affordances, or
   - offer Retry and explicit offline display.
6. Never call a stale snapshot "current."

For editable P1:

- editing should begin only from a full-enough baseline,
- unknown fields remain disabled,
- the UI must retain the baseline fingerprint used to create the edit log.

### 6.4 Change notifications

`lease.onDidChange` can represent status transitions, disk publication, background hydration, or a new live generation.

On each notification:

1. Pin one snapshot.
2. Build its visualizer fingerprint if required sections are ready.
3. Compare it with the last rendered and editing-baseline fingerprints.
4. If the fingerprint is unchanged, update freshness/status without declaring schema drift.
5. If changed and the editor is clean, refresh while preserving layout by stable graph IDs.
6. If changed and the editor is dirty, keep the current edit baseline, mark an incoming change, and offer rebase or discard.

### 6.5 Required pre-preview sequence

Before creating v1 state:

1. Call `ensureFresh` with a `requireLive` policy and `allowPartial: false` for operation-dependent sections.
2. Refuse if freshness is unavailable or required sections are not ready.
3. Pin exactly one snapshot.
4. Build its canonical model and fingerprint.
5. Rebase the operation log onto that model.
6. Stop on any precondition conflict.
7. Only then resolve classic credentials and call v1 `createSession`.

### 6.6 Correlation against the v1 baseline

The `createSession` response is a fresh DacFx view of the actual database and is the final baseline for replay.

Correlate only against that response. Use:

- exact schema/name matches first,
- collation-aware fallback only when the database is case-insensitive,
- explicit rename operations to preserve old identity,
- column names plus table identity for existing columns,
- hard failure for ambiguity or absence,
- dependency checks for FK targets and mapped columns.

For every touched entity, verify relevant before-values or an entity fingerprint. Do not silently replay onto an object that merely has the same current name but no longer matches the operation's baseline.

Untouched entities should be copied from the v1 baseline unchanged. This is essential because the metadata projection and legacy projection are not identical.

### 6.7 Preview to publish drift check

After `getReport`, the user may spend time reviewing the report. Before `publishSession`:

1. Confirm the current edit revision equals the preview revision.
2. Force another live metadata refresh.
3. Recompute the full visualizer fingerprint.
4. If it differs from the fingerprint used for preview, dispose the v1 session and require a new preview.
5. If it matches, publish through the same v1 session.

This closes most of the report-review race. A final external DDL can still race between the last check and DacFx publish; handle the resulting publish failure, dispose, refresh, and present an actionable retry.

---

## 7. Editing and operation log

### 7.1 Reuse existing edit vocabulary, but do not persist it raw

`src/sharedInterfaces/schemaDesigner.ts` already defines:

- `TableRef`,
- `ColumnRef`,
- `ForeignKeyRef`,
- `ColumnCreate`,
- `ForeignKeyCreate`,
- `SchemaDesignerEdit`,
- `applyEdits`.

This should remain the common ingress vocabulary for LM tool edits and other callers.

It is not sufficient as the internal durable log because it is name-first, IDs are optional, and it contains no baseline preconditions.

Normalize each accepted edit into an internal versioned operation:

```ts
export interface SchemaVisualizerEditV1 {
    version: 1;
    operationId: string;
    kind: string;
    target: {
        objectId?: number;
        columnId?: number;
        constraintObjectId?: number;
        baselineSchema?: string;
        baselineName?: string;
    };
    precondition: {
        baselineFingerprint: string;
        entityFingerprint?: string;
        before?: unknown;
    };
    payload: unknown;
}
```

The exact shape should be a discriminated union, not `unknown`, in production.

### 7.2 React Flow is a projection, not the edit authority

The existing designer stores authoritative state in React Flow and pushes complete `ReactFlowJsonObject` snapshots for undo/redo.

The visualizer's editable mode should instead use:

```text
canonical baseline + operation history + history cursor
```

The graph is derived from the resulting model.

Benefits:

- rename semantics remain explicit,
- rebase is deterministic,
- undo and redo move the operation cursor,
- preview invalidation is a simple edit revision check,
- LM tool and manual edits use the same reducer,
- graph positions are not mixed with schema semantics,
- correlation and conflict receipts are testable without React.

### 7.3 Operation support matrix

Define the first editable release deliberately:

| Operation | Recommended first-edit release |
|---|---|
| Add/drop/rename table | Yes |
| Change table schema | Yes, with collision checks |
| Add/drop/rename column | Yes |
| Change type/length/precision/scale | Yes for supported type capabilities |
| Change nullability | Yes |
| Reorder columns | Only if a first-class `move_column` operation is added |
| Add/drop/change FK | Yes after exact pair/action metadata lands |
| Identity edit | Only after lossless wire representation is solved |
| Default edit | Only after v1 updater fixes and tests |
| Computed formula/persisted edit | Only after v1 updater fixes and tests |
| Views/modules | No |
| Index/check-constraint editing | No |

Do not expose an edit control merely because the legacy editor currently has one. The visualizer must have exact baseline data and a tested replay path for that field.

### 7.4 Operation normalization

Before preview, normalize the log:

- add then drop of the same new entity cancels,
- consecutive renames coalesce while preserving the original baseline name,
- repeated property sets keep the original before-value and final after-value,
- a drop removes subsequent edits to the dropped entity,
- FK operations are ordered after required table/column creation and rename operations,
- generated IDs remain stable within the local editing session.

The normalized log is what diagnostics count and what replay tests consume.

### 7.5 Rebase

When metadata changes while dirty:

1. Obtain a full live new baseline.
2. Replay the normalized operation log through the pure reducer.
3. Check every precondition.
4. Return:
   - cleanly rebased,
   - rebased with warnings,
   - conflict list with operation IDs.
5. Never discard edits automatically.

The same reducer should power the pre-preview rebase.

---

## 8. Classic connection and v1 handoff

### 8.1 Do not clone the OE v2 handoff API verbatim

`OeV2ClassicHandoffService` solves a related policy problem, but its output is a connected owner URI. `schemaDesigner/createSession` currently requires:

- a classic connection string,
- an optional access token,
- database name.

`PreparedConnection` intentionally contains profile references and credential-provider closures, not enough information to reconstruct the classic connection string.

Create a dedicated injected seam, for example:

```ts
export interface SchemaVisualizerClassicPublishResolver {
    resolve(input: {
        stableProfileId: string;
        database: string;
        expectedServerFingerprint: string;
    }): Promise<{
        connectionString: string;
        accessToken?: string;
        principalFingerprint?: string;
        dispose(): void;
    }>;
}
```

The resolver should:

- re-resolve the stored profile at command time,
- use existing `ConnectionManager` preparation only inside the handoff seam,
- set the exact target database,
- obtain a fresh access token when needed,
- verify the resolved server/database identity,
- avoid retaining credentials after session creation,
- never log or include the connection string in keys,
- support the same explicit confirmation policy as other legacy handoffs.

### 8.2 Manager keys

The visualizer manager key should use non-secret identity:

```text
<stableProfileId>|<serverFingerprint>|<database>|<mode>
```

Do not use a connection string as a cache key.

### 8.3 Handoff state machine

Implement an explicit state machine:

```text
idle
  -> refreshingBaseline
  -> resolvingClassicConnection
  -> creatingSession
  -> correlating
  -> generatingReport
  -> awaitingConfirmation
  -> publishing
  -> refreshingAfterPublish
  -> idle
```

Failure and cancellation from any state after session creation go through:

```text
disposingSession -> idle/failed
```

### 8.4 Preview token

After a successful report, hold:

```ts
interface PublishPreviewToken {
    sessionId: string;
    editRevision: number;
    normalizedOperationsHash: string;
    catalogFingerprint: string;
    legacyTargetHash: string;
    report: SchemaDesigner.GetReportResponse;
}
```

`publishSession` is allowed only when:

- the token exists,
- the edit revision is unchanged,
- the operation hash is unchanged,
- the final drift check passed,
- the same v1 session is still alive,
- no report error occurred.

### 8.5 Disposal rules

A v1 session must be disposed on:

- report cancellation,
- report failure,
- publish success,
- publish failure,
- any edit after report,
- refresh/rebase after report,
- panel close,
- extension deactivation,
- connection/profile removal,
- handoff timeout,
- a second preview attempt replacing the first.

Use `try/finally` around every session-owning path. Add a session-leak test that records created and disposed IDs.

### 8.6 Exact v1 request sequence

Browse path:

```text
zero schemaDesigner/* requests
```

Successful publish path:

```text
schemaDesigner/createSession
schemaDesigner/getReport
schemaDesigner/publishSession
schemaDesigner/disposeSession
```

Canceled preview path:

```text
schemaDesigner/createSession
schemaDesigner/getReport
schemaDesigner/disposeSession
```

Correlation failure path:

```text
schemaDesigner/createSession
schemaDesigner/disposeSession
```

No `getDefinition` or `generateScript` is needed from v1 for the visualizer's ordinary read paths.

---

## 9. Required legacy updater fixes before full edit parity

The design calls the v1 pipeline proven, which is directionally fair, but two existing behaviors are load-bearing for this port.

### 9.1 `DeepCompareColumn` omissions

`SchemaDesignerUtils.DeepCompareColumn` currently compares identity, type, nullability, PK, length, precision, and scale, but not:

- `DefaultValue`,
- `IsComputed`,
- `ComputedFormula`,
- `ComputedPersisted`.

A default-only or formula-only operation may therefore fail to mark the table as modified.

### 9.2 Computed formula update path

`SchemaDesignerUpdater.UpdateColumnProperties` updates computed formula and persisted state primarily when `IsComputed` itself changes. It must also update formula, persisted state, and persisted nullability when both source and target remain computed but those properties change.

### 9.3 Required tests

Before enabling these operations in the visualizer, add STS unit/integration tests for:

- default expression only,
- add default,
- remove default,
- computed formula only,
- persisted flag only,
- computed nullable state where supported,
- computed to regular,
- regular to computed,
- identity seed only,
- identity increment only,
- values outside JavaScript safe-integer range through the chosen wire solution.

These may be separate `core:` changes. They are not optional if the corresponding visualizer controls are enabled.

---

## 10. Graph and webview reuse

### 10.1 Current components are not fully pure

The original design correctly identifies reusable modern React Flow code, but the import boundary is wider than stated.

`SchemaDesignerFlow` imports and depends on:

- `SchemaDesignerContext`,
- selector state,
- global event bus,
- deleted-item diff helpers,
- change context,
- Copilot review UI,
- schema mutation utilities.

`SchemaDesignerTableNode` also imports legacy context, selectors, event bus, diff context, and edit actions.

A new page that directly imports those components inherits substantial legacy behavior and RPC assumptions.

### 10.2 Required shared extraction

Perform a small, behavior-preserving `core:` extraction before the visualizer page depends on shared graph code.

Suggested structure:

```text
src/webviews/shared/schemaGraph/
  schemaGraphTypes.ts
  SchemaGraphCanvas.tsx
  SchemaGraphTableNode.tsx
  schemaGraphAdapter.ts
  schemaGraphLayout.ts
  schemaGraphDimensions.ts
```

Provider-neutral components receive data and callbacks:

```ts
interface SchemaGraphCanvasProps {
    nodes: SchemaGraphNode[];
    edges: SchemaGraphEdge[];
    readOnly: boolean;
    showDiff?: boolean;
    onEditTable?: (id: string) => void;
    onDeleteTable?: (id: string) => void;
    onConnect?: (...) => void;
    onSelectionChange?: (...) => void;
}
```

Legacy Schema Designer supplies an adapter backed by its current context and event bus. Schema Visualizer supplies its own controller.

### 10.3 Extraction constraints

The extraction commit must:

- change no behavior in the existing designer,
- preserve localization,
- preserve accessibility labels and keyboard handling,
- preserve export rendering,
- preserve current diff highlighting,
- keep DAB and Copilot imports out of the neutral graph module,
- have focused component or interaction tests,
- be independently revertible.

### 10.4 Import allowlist

Until extraction is complete, the visualizer should import only demonstrably pure leaf modules. Add a lint rule or test forbidding imports from legacy stateful modules such as:

```text
SchemaDesigner/schemaDesignerStateProvider
SchemaDesigner/schemaDesignerEvents
SchemaDesigner/definition/copilot
SchemaDesigner/editor
```

### 10.5 Bundle assertions

Because esbuild uses multi-entry ESM splitting, adding a second entry that shares code may hoist modules into new common chunks. The exact Schema Designer chunk graph can change without a regression.

Test these instead:

- no `@xyflow/react`, Dagre, Monaco, or DAB code in eager extension-host chunks,
- no duplicate React or React Flow copies,
- visualizer entry initial-byte budget,
- legacy Schema Designer static-closure byte budget does not regress materially,
- legacy open behavior and tests remain green,
- shared chunk manifest remains valid,
- no DAB code enters the visualizer's static closure.

---

## 11. Large-catalog policy

### 11.1 Metadata speed is not graph speed

A warm metadata acquire near 9 ms and a 148 ms catalog hydration do not imply a 10,000-table diagram can be rendered or arranged interactively.

The current layout function:

- runs Dagre synchronously on the webview thread,
- scans `nodes.find(...)` for each edge,
- lays out all visible nodes before first meaningful paint.

This can dominate open time and freeze the UI.

### 11.2 Required algorithmic fix

At minimum:

- build a `Map<string, Node>` once,
- replace per-edge linear node searches with O(1) lookup,
- measure adapter, layout, React state update, and paint separately,
- make auto-layout cancelable,
- avoid rerunning layout after a metadata refresh when stable node positions can be retained.

### 11.3 Initial scope policy

Implement an internal large-catalog threshold, tuned by measurement.

Recommended initial behavior:

| Table count | Open behavior |
|---|---|
| Small catalog | Render all tables and auto-layout. |
| Medium catalog | Render all with progressive/cancelable layout, subject to measured budget. |
| Large catalog | Open search-first or with a selected subset, not an unconditional all-table Dagre pass. |

A starting threshold around 500 rendered tables is reasonable for dogfood, but it should be treated as a measured internal policy, not a public contract.

For large catalogs, support:

- search and add-to-canvas,
- selected table plus N-hop FK neighborhood,
- schema filter,
- "add all matching" with a warning,
- a visible count of included versus total tables,
- background relationship expansion,
- preserved positions keyed by stable graph IDs.

### 11.4 Worker decision

If measured layout exceeds the responsiveness budget, move it to a dedicated web worker. If a worker is used:

- add a separate bundle entry or supported worker build path,
- opt the webview CSP into workers explicitly,
- pass plain serializable graph facts,
- support cancellation by request ID,
- discard stale worker results after a model or filter revision.

### 11.5 Ready semantics

`mssql.schemaVisualizer.ready` must mean first meaningful rendered graph state, not merely "model sent to webview."

Suggested condition:

- required model received,
- initial subset chosen,
- layout completed or deliberately skipped,
- React Flow contains the expected node/edge count,
- one animation frame has completed after commit.

---

## 12. Definition and scripting review

### 12.1 Separate legacy compatibility from correctness

The existing C# `SchemaCreationScriptGenerator` is a useful compatibility reference, but it is not a complete catalog scripting engine.

Observed limitations include:

- identifiers are bracketed but closing brackets are not escaped,
- PK constraint names are omitted,
- composite PK order is derived from table column order rather than explicit key ordinal,
- cluster/sort/index details are omitted,
- default constraint names are omitted,
- unsupported and alias types are simplified,
- empty or unresolved FK mappings can silently produce no script,
- the schema DTO cannot carry all metadata needed for faithful DDL.

A byte-for-byte port would preserve these behaviors.

### 12.2 Recommended P0 behavior

Provide an **Informational CREATE Script** command with clear non-authoritative labeling.

Use the canonical visualizer model. For any unknown or unsupported field:

- omit the unsafe clause,
- add a warning in the UI,
- never substitute a concrete value.

The script is for inspection and copying. It is not the publish artifact.

### 12.3 Testing strategy

Use two test groups:

1. **Compatibility goldens** for ordinary safe fixtures where parity with the existing generator is desirable.
2. **Correctness cases** for:
   - `]` in identifiers,
   - Unicode and max lengths,
   - alias/user-defined types,
   - decimal and time scale,
   - exact identity values,
   - named defaults,
   - computed columns,
   - composite PK order,
   - composite FK order,
   - all referential actions,
   - self-referencing FKs.

When intentionally correcting legacy output, document the difference rather than forcing byte parity.

### 12.4 Other definition formats

The existing non-SQL definition generators are already client-side. They may be reused through a compatibility projection, but each must be tested against:

- unknown fields,
- user-defined types,
- composite keys,
- names requiring escaping,
- partial metadata.

### 12.5 Module definitions

`getModuleDefinition(objectId)` is appropriate for views, procedures, and functions in a later phase. It does not replace table DDL generation and should not expand P0 beyond tables.

---

## 13. Diagnostics and telemetry corrections

### 13.1 Existing registry entries

`mssql.schemaDesigner.init.begin` and `.end` are already present in the observability registry and emitted by the existing controller. Do not register duplicate or differently shaped entries.

Register only missing events and re-vendor before first emission.

### 13.2 Recommended visualizer markers

Use explicit names and phases:

```text
mssql.schemaVisualizer.open.begin
mssql.schemaVisualizer.open.end
mssql.schemaVisualizer.modelReady
mssql.schemaVisualizer.layout.begin
mssql.schemaVisualizer.layout.end
mssql.schemaVisualizer.ready
mssql.schemaVisualizer.refresh.begin
mssql.schemaVisualizer.refresh.end
mssql.schemaVisualizer.driftDetected
mssql.schemaVisualizer.rebase.begin
mssql.schemaVisualizer.rebase.end
mssql.schemaVisualizer.commit.handoff.begin
mssql.schemaVisualizer.commit.handoff.end
mssql.schemaVisualizer.publish.begin
mssql.schemaVisualizer.publish.end
```

Recommended semantics:

- `open.end`: extension-host model preparation completed.
- `modelReady`: model delivered/accepted by the webview.
- `ready`: first meaningful rendered graph, emitted as a calibrated webview mark.
- `handoff`: classic resolution through report readiness.
- `publish`: confirmed publish only.

### 13.3 Automatic RPC spans

`WebviewBaseController.onRequest` already emits diagnostics spans named:

```text
webview.<sourceFile>.<method>
```

For a `schemaVisualizer` entry and `sv/getModel` method, that is not the same as an explicit `mssql.schemaVisualizer.*` marker.

Do not assume automatic spans satisfy perftest marker contracts. Keep explicit markers for product phases and use automatic spans for trace detail.

### 13.4 Safe attributes

Allowed examples:

- table count,
- column count,
- FK count,
- rendered table count,
- generation,
- freshness enum,
- source enum,
- validation tier,
- layout mode,
- operation count,
- correlation count,
- conflict count,
- data-loss boolean,
- outcome enum,
- duration.

Do not emit:

- server name,
- database name,
- schema/table/column/constraint names,
- SQL text,
- generated scripts,
- connection strings,
- access tokens,
- descriptions,
- operation payloads.

### 13.5 Cache state

Derive cache/freshness labels from `FreshCatalogResult.source`, `freshness`, and validation facts. Do not synthesize a single `warm|cold|offline` value that hides stale or validation failure.

### 13.6 Legacy instrumentation

Add a legacy webview rendered-ready marker in addition to extension-host init instrumentation. This is required for fair end-to-end comparison.

Keep the legacy instrumentation change independent and behavior-free.

---

## 14. Perftest corrections

### 14.1 Current comparison is not apples-to-apples

The current `schema-designer-open` scenario waits for `mssql.schemaDesigner.init.end`, which is emitted after the extension host receives the DacFx schema. It does not prove that Dagre layout and React Flow paint completed.

If `schema-visualizer-open` waits for `mssql.schemaVisualizer.ready` after paint, the candidate is measured to a later endpoint than the baseline.

### 14.2 Required metric pairs

Create two comparisons:

#### Host/model phase

```text
legacy:    schemaDesigner.init.begin -> schemaDesigner.init.end
candidate: schemaVisualizer.open.begin -> schemaVisualizer.open.end
```

This measures DacFx session/model load versus metadata acquire and adaptation.

#### End-to-end rendered phase

```text
legacy:    command/root -> schemaDesigner.ready
candidate: command/root -> schemaVisualizer.ready
```

Both ready markers must mean first meaningful graph paint.

### 14.3 Scope equality

A head-to-head run must use:

- the same database,
- the same table set,
- the same filter,
- equivalent layout policy,
- equivalent extension activation state,
- an explicit cache condition.

Do not compare a full legacy diagram with a filtered visualizer subset without labeling the scope difference.

### 14.4 Warm and cold variants

Separate:

- live cold metadata hydration,
- warm in-memory lease,
- warm disk cache acquire followed by validation,
- stale disk snapshot,
- `sts2-local`,
- `ts-native`.

A warm scenario should assert its cache/source precondition in markers. Otherwise a cache miss can quietly contaminate the distribution.

### 14.5 Large-catalog scenarios

Add diagnostic scenarios for:

- 100 tables,
- 1,000 tables,
- a 10,000-object catalog,
- high FK density,
- composite FK density,
- search-first large-catalog open.

Measure:

- metadata wait,
- adapter time,
- layout time,
- first paint,
- heap delta,
- event-loop delay,
- node and edge counts.

Keep metrics unofficial until enough baseline history exists.

### 14.6 Registry and build discipline

Continue the contracts-first rule:

1. update observability contracts,
2. generate/re-vendor,
3. build perftest distribution,
4. run vendor/parity tests,
5. run scenarios.

Use symbol-based registry edits rather than frozen line numbers.

---

## 15. Error and honesty contract

Define typed error/outcome codes shared between controller and webview:

```text
metadataUnavailable
metadataStale
sectionUnavailable
permissionLimited
unsupportedType
baselineChanged
rebaseConflict
correlationNotFound
correlationAmbiguous
classicHandoffDeclined
classicHandoffUnavailable
classicIdentityMismatch
reportFailed
previewInvalidated
publishFailed
refreshAfterPublishFailed
sessionDisposed
```

Required UI behavior:

| Condition | UI |
|---|---|
| No snapshot and hydrate failed | Error state with retry, not empty diagram |
| Stale retained snapshot | Stale banner, source/freshness fact, edit disabled |
| Objects ready, columns failed | Table list may render; column/diagram capability explains failure |
| FK actions unknown | Show Unknown, do not display NO ACTION |
| Description absent by privacy policy | Show Not cached or Unavailable, not empty description as fact |
| Metadata changed while clean | Refresh preserving layout |
| Metadata changed while dirty | Drift banner and rebase/discard options |
| Correlation conflict | Stop before report and list safe, non-sensitive conflict summaries |
| Report warns data loss | Existing DacFx report UX remains authoritative |
| Publish succeeds but refresh fails | Report publish success and separately report refresh failure |

---

## 16. Persistence and restore

### 16.1 P0

Read-only P0 may reopen from metadata and need not persist schema state. Persisting layout is optional.

### 16.2 Editable mode

For dirty-state restoration, persist only safe local state:

- stable profile ID,
- server fingerprint,
- database,
- baseline fingerprint,
- normalized operation log,
- operation-history cursor,
- selected subset/filter,
- graph positions keyed by stable IDs,
- view preferences.

Never persist:

- connection strings,
- passwords,
- access tokens,
- full generated scripts by default,
- descriptions unless covered by an explicit privacy policy.

On restore:

1. reacquire metadata,
2. obtain a full live snapshot,
3. compare the baseline fingerprint,
4. replay/rebase the operation log,
5. present conflicts before enabling publish.

Closing a dirty editor must retain the existing restore/discard safety behavior.

---

## 17. Testing addendum

### 17.1 Metadata and codec tests

Add fixtures for:

- stable `column_id` retention,
- non-sequential column IDs,
- FK constraint IDs,
- ordered FK column IDs,
- all four FK actions,
- Unicode length conversion,
- `max` types,
- binary types,
- decimal/numeric precision and scale,
- datetime/time scale,
- alias types,
- user-defined types,
- vector metadata where supported,
- default constraint name and expression,
- identity seed/increment exact values,
- computed definition and persisted,
- case-sensitive names differing only by case,
- permission-flavored section failure,
- disk cache with descriptions excluded,
- codec version mismatch,
- deterministic full fingerprint.

Required invariant:

```text
unchanged live hydration at generation N and N+1
=> identical visualizer fingerprint
=> identical graph IDs
```

### 17.2 Adapter tests

Test:

- catalog model to graph projection,
- no generation in IDs,
- stable layout keys,
- unknown values remain unknown,
- no failed section becomes an empty-success model,
- deterministic ordering,
- self-referencing FK,
- composite FK,
- missing referenced object during raced DDL,
- partial capability matrix.

### 17.3 Operation reducer tests

Test every operation plus:

- rename followed by property change,
- table schema move plus FK edit,
- add then drop normalization,
- repeated rename coalescing,
- undo/redo cursor,
- rebase success,
- rebase conflict,
- case-sensitive resolution,
- ambiguous case-insensitive resolution,
- FK-to-renamed-table ordering,
- generated entity UUID stability,
- unsupported operation rejection.

### 17.4 Handoff tests

Use a fake v1 service and resolver to prove:

- no handoff during browse,
- exact request order,
- same session used for report and publish,
- report failure prevents publish,
- edit after report invalidates preview,
- drift after report invalidates preview,
- correlation failure disposes session,
- user cancellation disposes session,
- panel close disposes session,
- resolver failure creates no session,
- resolved database/server mismatch blocks createSession,
- all created sessions are disposed exactly once.

### 17.5 No-v1 tripwire

The tripwire should forbid legacy schema-designer behavior specifically:

- no `schemaDesigner/createSession`,
- no `schemaDesigner/getDefinition`,
- no `schemaDesigner/getReport`,
- no `schemaDesigner/publishSession`,
- no classic connection resolution.

Do not write a blanket assertion that accidentally rejects legitimate SQL Data Plane traffic for the `sts2-local` backend.

Add a companion test proving the explicit preview/publish path does cross the seam.

### 17.6 Legacy updater tests

Add the tests in Section 9 before enabling corresponding edit controls.

### 17.7 Webview and component tests

Test:

- read-only table node behavior,
- no editor drawer in P0,
- filters,
- export,
- first-paint marker,
- stale and partial banners,
- drift while dirty,
- rebase conflict UI,
- keyboard/accessibility behavior after shared extraction,
- no DAB or Copilot dependency in visualizer static closure.

### 17.8 Bundle tests

Test:

- eager extension host remains free of graph libraries,
- no duplicate React/React Flow,
- visualizer entry budget,
- legacy entry budget,
- modulepreload manifest correctness,
- worker closure if a layout worker is added.

Do not require byte-identical chunk names or an unchanged shared-chunk graph.

### 17.9 Live lanes

Read-only lane:

- acquire metadata,
- compare table count and identities,
- compare columns by `object_id` and `column_id`,
- compare FK pairs and actions,
- verify zero legacy schema-designer calls.

Publish lane:

- add a table,
- rename a column,
- add a composite FK,
- preview,
- publish,
- force metadata refresh,
- verify catalog state,
- clean up.

Conflict lane:

- begin local edit,
- change a touched object externally,
- prove preview is blocked,
- rebase or discard,
- prove no publish occurred.

### 17.10 Privacy tests

Use canary identifiers and descriptions. Scan:

- diagnostics journals,
- Debug Console exports,
- telemetry payloads,
- perftest artifacts,
- serialized restore state,
- metadata cache when descriptions are disabled.

---

## 18. Revised phase plan

| ID | Scope | Exit gate |
|---|---|---|
| SV-R0 | Ratify original design plus this addendum; seed decision log; verify branch heads; register only missing markers. | Design accepted; contracts/vendor sync green. |
| SV-R1 | Metadata identity and exact-detail extension: column IDs, type facts, identity text, defaults, computed details, FK IDs/pair IDs/actions; cache version bump. | Determinism, codec, action mapping, exact-value tests green. |
| SV-R2 | Canonical visualizer model, capability matrix, fingerprint, graph projection, pure rebase reducer skeleton. | Stable-ID and unchanged-generation invariants green. |
| SV-R3 | Provider-neutral graph extraction in an isolated `core:` commit. | Existing Schema Designer behavior and bundle budgets green. |
| SV-R4 | Read-only visualizer controller/page/manager, flag, command, OE v2 entry, properties, large-catalog policy. | No-v1 tripwire, honesty matrix, live open lane, first-paint marker green. |
| SV-R5 | Informational SQL definition and existing client-side format integration. | Compatibility and correctness goldens green. |
| SV-R6 | Operation capture, normalized log, operation-based undo/redo, rebase UX. | Pure reducer, normalization, restore, conflict suites green. |
| SV-R7 | Legacy updater correctness fixes and lossless identity wire decision. | Default/computed/identity tests green or operations remain disabled. |
| SV-R8 | Dedicated classic resolver, handoff state machine, v1 replay/correlation, report and publish. | Session lifecycle, preview token, live round-trip, drift race tests green. |
| SV-R9 | Diagnostics/telemetry polish and Debug Console verification. | Privacy and trace composition green. |
| SV-R10 | Perftest model and rendered comparisons, warm/cold and large-catalog variants. | First A/B report archived; scenarios remain diagnostic/unofficial. |
| SV-R11 | Decide DAB, views, Table Explorer/classic OE entries, and advanced details. | Separate design decisions. |

### 18.1 P0 definition

P0 should be SV-R0 through SV-R4:

- tables-only,
- read-only,
- metadata-only,
- properties with honest availability,
- stable IDs,
- large-catalog protection,
- no v1 traffic,
- first-paint diagnostics.

Informational definitions may be P0.1 rather than blocking the first diagram demo.

---

## 19. Suggested file layout

### 19.1 `vscode-mssql`

```text
extensions/mssql/src/schemaVisualizer/
  schemaVisualizerActivation.ts
  schemaVisualizerManager.ts
  schemaVisualizerController.ts
  schemaVisualizerContracts.ts
  model/
    schemaVisualizerModel.ts
    catalogToVisualizerModel.ts
    visualizerFingerprint.ts
    visualizerToGraphProjection.ts
    schemaVisualizerEdit.ts
    schemaVisualizerEditReducer.ts
    schemaVisualizerRebase.ts
  metadata/
    schemaVisualizerFreshness.ts
    schemaVisualizerCapabilities.ts
  handoff/
    schemaVisualizerClassicPublishResolver.ts
    schemaVisualizerHandoffStateMachine.ts
    correlateLegacyBaseline.ts
    replayEditsToLegacySchema.ts
    publishPreviewToken.ts
  scripting/
    schemaVisualizerSqlGenerator.ts
  diagnostics/
    schemaVisualizerDiagnostics.ts
```

```text
extensions/mssql/src/webviews/pages/SchemaVisualizer/
  index.tsx
  schemaVisualizerPage.tsx
  schemaVisualizerStateProvider.tsx
  schemaVisualizerToolbar.tsx
  schemaVisualizerProperties.tsx
  schemaVisualizerStatusBanner.tsx
  schemaVisualizerConflictPanel.tsx
```

```text
extensions/mssql/src/webviews/shared/schemaGraph/
  schemaGraphTypes.ts
  SchemaGraphCanvas.tsx
  SchemaGraphTableNode.tsx
  schemaGraphLayout.ts
  schemaGraphDimensions.ts
```

Metadata substrate changes remain under:

```text
extensions/mssql/src/services/metadata/
  catalogModel.ts
  metadataService.ts
  cache/metadataCacheCodec.ts
  fixtures and tests
```

Prefer a new `sharedInterfaces/schemaVisualizer.ts` for visualizer-specific RPCs. Do not overload the legacy Schema Designer contract with metadata-only states unless the type is genuinely shared.

### 19.2 `sqltoolsservice`

No new endpoint is required.

Expected changes are limited to correctness and tests in:

```text
src/Microsoft.SqlTools.ServiceLayer/SchemaDesigner/
  SchemaDesignerUtils.cs
  SchemaDesignerUpdater.cs
  related unit/integration tests
```

A shared wire-contract change for exact identity values is allowed only after a separate compatibility review.

### 19.3 `perftest`

Expected changes:

```text
packages/observability-contracts/src/registry/event-types.json
packages/perftest-cli/src/scenarios/registry.ts
examples/config.designers.local.jsonc or a visualizer-specific config
head-to-head phase maps
scenario fixtures and docs
```

---

## 20. Implementation constraints for an AI coding agent

The implementation agent should follow these rules:

1. Re-read current branch symbols before editing. Do not trust frozen line numbers.
2. Make one architectural seam per commit.
3. Keep `core:` extraction commits behavior-preserving and independently testable.
4. Do not implement editable controls before their metadata and replay fields are exact.
5. Do not fabricate unknown metadata values.
6. Do not use `generation` as a content hash.
7. Do not place `generation` in graph IDs.
8. Do not parse `typeDisplay` to reconstruct SQL type semantics.
9. Do not cast FK action integers into `OnAction`.
10. Do not convert identity seed/increment to JavaScript number without an exactness proof.
11. Do not persist or log connection strings, tokens, SQL text, or identifiers.
12. Do not call v1 outside the explicit handoff state machine.
13. Do not call `publishSession` without a valid, current preview token.
14. Dispose every created v1 session.
15. Do not silently rebase dirty edits.
16. Do not run synchronous all-catalog layout without a measured size policy.
17. Do not copy stateful Schema Designer components into the new page under a different name.
18. Do not make exact esbuild chunk topology an acceptance criterion.
19. Keep all generated SQL informational; DacFx remains the apply authority.
20. Add tests before enabling each operation family.

---

## 21. Acceptance checklist

The feature is ready for preview only when all applicable items are true.

### Read path

- [ ] Opening the visualizer creates no v1 schema-designer session.
- [ ] All schema reads come from one pinned `CatalogSnapshot` per response.
- [ ] Required section failures produce honest errors, not empty success.
- [ ] Stale data is visibly labeled.
- [ ] Stable graph IDs survive unchanged refreshes and generation changes.
- [ ] Large catalogs do not trigger an unbounded synchronous layout.
- [ ] Descriptions follow cache privacy policy.
- [ ] No identifiers appear in diagnostics or telemetry.

### Metadata

- [ ] `column_id` is retained.
- [ ] FK constraint and pair column IDs are retained.
- [ ] FK actions are explicitly mapped.
- [ ] Type semantics are stored without reverse-parsing display strings.
- [ ] Identity values are lossless.
- [ ] Cache model version and canonical fields are updated.
- [ ] Visualizer fingerprint is deterministic and generation-independent.

### Editing

- [ ] Manual and LM edits enter one pure reducer.
- [ ] Internal operations have identities and preconditions.
- [ ] Undo/redo is operation-based.
- [ ] Rebase is deterministic and conflict-aware.
- [ ] Unsupported or unknown fields are not editable.
- [ ] Created entities receive valid GUIDs before STS replay.

### Handoff

- [ ] Classic credentials resolve only on explicit preview/publish.
- [ ] Resolved database/server identity is verified.
- [ ] Current metadata is forced live before preview.
- [ ] Touched entities correlate against the new v1 baseline.
- [ ] Report and publish use the same session.
- [ ] Any edit or drift invalidates the preview.
- [ ] Final drift check runs before publish.
- [ ] Every session is disposed on every exit path.
- [ ] Successful publish is followed by a forced metadata refresh.

### Legacy safety

- [ ] Existing Schema Designer behavior is unchanged by shared extraction.
- [ ] Legacy default/computed updater tests pass before those operations ship.
- [ ] Existing designer has a rendered-ready marker for fair comparison.
- [ ] Standing tests and perf pairs do not regress.

### Performance

- [ ] Host model time and rendered-ready time are separate metrics.
- [ ] Head-to-head scopes are equivalent.
- [ ] Warm scenarios prove the expected cache state.
- [ ] Large-catalog scenarios report node, edge, layout, paint, memory, and event-loop facts.
- [ ] New metrics remain unofficial until baseline history exists.

---

## 22. Recommended decisions for the original open questions

1. **Shared component extraction:** pre-extract the smallest provider-neutral read-only graph shell before SV-R4. Do not wait until the first visualizer-specific modification.
2. **Views:** tables-only in P0. Add views only under a separate capability and visual-language decision.
3. **Commit prefix:** keep `sv:` for visualizer feature code, `qs:` for metadata substrate, and `core:` for legacy/shared extraction or updater fixes.
4. **Classic Object Explorer entry:** defer. Command palette and OE v2 are sufficient for preview.
5. **DAB:** defer until after editable publish is stable.
6. **Script parity:** compatibility on ordinary fixtures, correctness on edge cases, informational-only output.
7. **Large-catalog threshold:** implement an internal measured threshold and search-first mode. Do not promise full 10k-table canvas rendering as the P0 headline.
8. **Unknown FK actions:** render Unknown and disable action editing. Never default to NO_ACTION.
9. **Identity values:** do not enable editing until exact wire handling is decided.
10. **Computed/default editing:** fix the v1 updater first or keep these controls read-only.

---

## 23. Final assessment

The proposed feature is a strong fit for the new data-plane and metadata architecture. The separation between metadata-backed reads and deliberate DacFx-backed apply is the right seam.

The most important conceptual correction is this:

> The visualizer must be built around a canonical, identity-rich, availability-aware schema model and a versioned semantic operation log. The legacy `SchemaDesigner.Schema` is an adapter format, not the truth model.

The most important publish correction is this:

> A commit is not "refresh, compare generation, then call v1." It is "force a live full baseline, rebase operations, create a fresh DacFx baseline, correlate touched entities with preconditions, preview in a held session, revalidate, then publish that exact preview session."

The most important performance correction is this:

> Fast metadata does not make an all-catalog React Flow layout free. Metadata, adaptation, layout, and paint must be measured and governed separately.

With those changes, the plan is suitable to hand to an AI coding agent and has a credible path to a safe P0, an observable performance story, and an editable release that does not trade latency for schema correctness.

---

## Appendix A. Reviewed implementation evidence

The review inspected these current symbols on `dev/query`:

### `vscode-mssql`

- `services/metadata/catalogModel.ts`
  - `ColumnInfo`
  - `FkEdge`, `FkColumnPair`, `FkDetail`
  - `CatalogBuilder`
  - `CatalogSnapshot`
- `services/metadata/metadataService.ts`
  - H0-H7 queries
  - `typeDisplay`
  - `hydrate`
  - `validateEntry`
  - `ensureFreshEntry`
- `services/metadata/cache/metadataFreshness.ts`
  - `MetadataPolicies.oeBrowse`
  - `requireValidated`
  - `requireLive`
- `services/metadata/cache/metadataCacheCodec.ts`
  - canonical payload fields
  - `CATALOG_MODEL_VERSION`
  - content-hash behavior
- `services/metadata/profileAuthAdapter.ts`
  - `PreparedConnection`
  - `stableProfileId`
- `objectExplorer/v2/legacy/oeV2ClassicHandoffService.ts`
- `sharedInterfaces/schemaDesigner.ts`
  - graph DTOs
  - `SchemaDesignerEdit`
  - `applyEdits`
- `schemaDesigner/schemaDesignerWebviewController.ts`
- `schemaDesigner/schemaDesignerWebviewManager.ts`
- `webviews/pages/SchemaDesigner/schemaDesignerStateProvider.tsx`
- `webviews/pages/SchemaDesigner/graph/SchemaDiagramFlow.tsx`
- `webviews/pages/SchemaDesigner/graph/schemaDesignerTableNode.tsx`
- `webviews/pages/SchemaDesigner/model/schemaToFlowState.ts`
- `webviews/pages/SchemaDesigner/model/schemaFromFlowState.ts`
- `webviews/pages/SchemaDesigner/model/flowLayout.ts`
- `controllers/webviewBaseController.ts`
- `scripts/bundle-webviews.js`

### `sqltoolsservice`

- `SchemaDesignerSession.cs`
- `SchemaDesignerUpdater.cs`
- `SchemaDesignerUtils.cs`
- `SchemaDesignerScriptGenerator.cs`
- `Contracts/SchemaDesignerTable.cs`
- `Contracts/SchemaDesignerColumn.cs`
- `Contracts/SchemaDesignerForeignKey.cs`

### `perftest`

- `observability-contracts/src/registry/event-types.json`
- `perftest-cli/src/scenarios/registry.ts`
- current `schema-designer-open` scenario and marker pairing

### SQL catalog references

The review also checked the current Microsoft Learn definitions for:

- `sys.columns`,
- `sys.identity_columns`,
- `sys.foreign_keys`.

These confirm byte-length semantics, non-sequential `column_id`, `sql_variant` identity values, metadata visibility limits, and referential-action numeric values.
