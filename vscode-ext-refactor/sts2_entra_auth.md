# STS2 / SQL Data Plane Entra Authentication

**Status:** implemented first slice, pending live VS Code dogfood after extension reload  
**Date:** 2026-07-11  
**Branches reviewed:** `vscode-mssql dev/query`, `sqltoolsservice dev/query`, `perftest dev/query`  
**Scope:** Query Studio, Object Explorer v2, MetadataStore consumers, inline-completion metadata, STS2 wire/runtime, diagnostics, replay, and performance-test hooks

## 1. Decision summary

The immediate AzureMFA failure is an extension profile-adaptation bug, not an Azure SQL, account, network, or SqlClient failure.

The selected design is:

1. Saved `AzureMFA` profiles map to the SQL Data Plane semantic auth kind `aad`.
2. The extension owns interactive/account-based token acquisition.
3. A small `ProfileTokenSource` is injected at the same boundary as the credential-store `ProfileSecretSource`.
4. The production token source uses VS Code authentication sessions and requests the SQL resource for the configured Azure cloud.
5. STS2 receives one opaque, short-lived SQL access token only when a physical SQL session opens.
6. STS2 Core and replay do not acquire, refresh, interpret, or persist tokens.
7. Query Studio, OE v2, MetadataStore, central upload, metadata-cache probes, and classic-editor completion metadata use the same profile preparation function.
8. Unsupported authentication types fail before JSON-RPC rather than silently becoming SQL Login.
9. Static access-token sessions do not use SqlClient pooling until renewable token callbacks and principal-safe pool partitioning are designed.

This keeps the v2 feature stack independent from `ConnectionManager.connect`, classic OE RPCs, and the legacy STS authentication provider. It intentionally shares the VS Code account/session store, not the legacy connection implementation.

## 2. Incident evidence

The latest diagnostic session was:

`%APPDATA%/Code/User/globalStorage/ms-mssql.mssql/session-diag/sessions/sess_20260711221704_1796/events/segment-000001.jsonl`

The relevant sequence was:

| Sequence  | Observation                                                                                                  |
| --------- | ------------------------------------------------------------------------------------------------------------ |
| 1043      | OE v2 starts opening one saved profile through the Data Plane.                                               |
| 1044      | `sqlDataPlane.openSession` records wire auth kind `sqlLogin`.                                                |
| 1068-1070 | SqlClient returns error 18456, `Login failed for user ''`.                                                   |
| 1167-1180 | Classic v1 opens the same saved profile and reaches `mssql.connection.ready`; classic OE expansion succeeds. |

The failed v2 fingerprint was recomputed from the saved connections and matched the `AzureMFA` profile. That profile contains `email`, `accountId`, and `tenantId`, but no SQL `user`. The old adapter discarded those Entra fields, classified every non-integrated profile as SQL auth, and produced an empty SQL login.

This rules out:

- invalid server or database;
- an unavailable Azure SQL endpoint;
- a missing VS Code sign-in for the successful v1 attempt;
- an STS2 SqlClient inability to use access tokens;
- a general OE v2 session or metadata failure.

## 3. Existing-system inventory

### 3.1 Classic v1 connection

Classic connection preparation calls `ConnectionManager.prepareConnectionInfo`.

For `AzureMFA`, `refreshEntraTokenIfNeeded` currently has two historical strategies:

- VS Code authentication sessions when the VS Code accounts feature is enabled;
- the older extension MSAL account store plus STS `SqlAuthenticationProvider` otherwise.

The default/current product configuration uses VS Code accounts. The token is acquired for the configured cloud's SQL resource, placed on the transient connection details, and sent to classic STS. Persisted profiles intentionally do not retain the access token.

### 3.2 SQL Data Plane profile boundary before this change

`profileAuthAdapter.ts` previously:

- retained only server, database, user, and basic TLS facts;
- recognized only an authentication string containing `integrated`;
- mapped every other value to `sql`;
- created only a `passwordProvider`;
- omitted `email`, `accountId`, and `tenantId`;
- allowed OE v2 to repeat the same two-way heuristic.

Query Studio then repeated profile/auth assembly for its main session, master database list, auxiliary sessions, and metadata acquisition.

### 3.3 STS2 before this change

The Data Plane and STS2 already had the necessary direct-token path:

- `SqlConnectionProfileRef.authKind` includes `aad` and `bearer`;
- `AuthProviderBundle` includes a deferred `tokenProvider`;
- `Sts2Backend` maps `aad`/`bearer` to STS2 `accessToken` auth;
- the gateway tokenizes auth secrets before journaling;
- the runtime resolves the secret only at the driver edge;
- `SqlClientDriver` assigns the result to `SqlConnection.AccessToken`.

The client used the non-canonical field name `accessToken`; STS2 SPEC section 7.4 defines the field as `token`. It happened to work because the redactor recognized both names and the runtime selected the first resolved secret. This change uses canonical `auth.token` and hardens runtime selection.

## 4. Requirements and non-goals

### 4.1 Requirements

- A saved AzureMFA profile that works in classic v1's VS Code account mode must open through STS2 v2.
- The token must come from the same VS Code account/session system used by current v1.
- No raw token, password, account ID, tenant ID, email, or endpoint may enter diagnostics, journals, replay descriptors, exports, or perf results.
- Token acquisition must be deferred until a physical SQL open.
- Every secondary session must use the same auth semantics as the primary session.
- Metadata cache identities must be partitioned by Entra principal and tenant.
- Missing accounts, token failures, and unsupported auth kinds must be classified as auth/preparation failures before SQL receives a bogus login.
- An explicit saved account/tenant must never silently fall back to a different resolved identity.
- Credential acquisition and the STS2 open request must share one bounded open deadline.
- The OE v2 no-v1 architecture tripwire must remain intact.
- The design must remain usable by a future remote/web Data Plane adapter.

### 4.2 Non-goals for this slice

- Adding MSAL or Azure.Identity to STS2 Core.
- Asking STS2 to launch an interactive sign-in.
- Reusing classic `ConnectionManager.connect` from Query Studio or OE v2.
- Persisting a second access-token cache.
- Implementing hosted OBO or managed identity.
- Treating `ActiveDirectoryDefault` or service principal credentials as SQL Login.
- Designing a renewable host-token callback protocol in the STS2 journal in this patch.
- Rehosting the legacy extension-owned MSAL account store in the SQL Data Plane. This slice fails that mode with an actionable setting/profile error; a clean second provider remains design work.

## 5. Authentication matrix

| Saved profile authentication type    | Data Plane kind | Credential provider | Current result                                                                    |
| ------------------------------------ | --------------- | ------------------- | --------------------------------------------------------------------------------- |
| missing / empty                      | `sql`           | password            | Supported for classic compatibility.                                              |
| `SqlLogin`                           | `sql`           | password            | Supported. Explicit empty SQL passwords remain possible.                          |
| `Integrated`                         | `integrated`    | none                | Supported.                                                                        |
| `AzureMFA`                           | `aad`           | SQL access token    | Supported with `useVscodeAccountsForEntraMFA`; legacy MSAL mode fails explicitly. |
| `ActiveDirectoryInteractive`         | `aad`           | SQL access token    | Same VS Code account-mode requirement as `AzureMFA`.                              |
| `ActiveDirectoryDefault`             | none            | none                | Explicitly unsupported by this Data Plane slice.                                  |
| `ActiveDirectoryServicePrincipal`    | none            | none                | Explicitly unsupported by this Data Plane slice.                                  |
| unknown values                       | none            | none                | Explicitly unsupported.                                                           |
| direct internal `bearer` profile ref | `bearer`        | caller token        | Still supported by the Data Plane API; not inferred from saved profiles.          |

The unsupported modes need separate semantics:

- `ActiveDirectoryDefault` means the identity of the process/host. In a remote backend, that may be the web application's managed identity, not the VS Code user.
- `ActiveDirectoryServicePrincipal` is an OAuth client credential. Calling it SQL Login is incorrect even though both carry a user-like ID and a secret.

## 6. Extension design

### 6.1 Pure profile adapter

`services/metadata/profileAuthAdapter.ts` remains free of VS Code and Azure UI dependencies.

It now exposes two host seams:

```ts
interface ProfileSecretSource {
  lookupPassword(profile: unknown): Promise<string>;
}

interface ProfileTokenSource {
  acquireSqlAccessToken(
    profile: StoredConnectionProfile,
  ): Promise<string | undefined>;
}
```

`prepareConnection(profile, secrets, tokens)` returns:

- the sanitized `SqlConnectionProfileRef`;
- the deferred `AuthProviderBundle`;
- the resolved semantic auth kind;
- non-reversible profile/server fingerprints;
- display/default database facts.

The adapter performs an exact switch. It does not use substring matching and does not default an unknown value to SQL Login.

### 6.2 VS Code SQL token source

`services/sqlDataPlane/vscodeSqlTokenSource.ts` is the product implementation of `ProfileTokenSource`.

It:

1. requires `mssql.preview.useVscodeAccountsForEntraMFA`; legacy MSAL-only profiles receive an actionable unsupported-account-store error rather than an ambiguous missing-account failure;
2. resolves a VS Code account by saved account ID, compatible account ID, or email/user label;
3. rejects a resolved account that is not ID-compatible with an explicit saved account;
4. rejects a resolved tenant that differs from an explicit saved tenant rather than silently using the default tenant under the requested cache identity;
5. selects the account's default tenant only when the profile did not pin one;
6. rejects a known token with less than 60 seconds of lifetime;
7. resolves the SQL resource endpoint for the configured public/sovereign cloud;
8. first attempts a silent VS Code authentication session;
9. permits the existing VS Code auth helper to create a session when required;
10. returns only the access-token string to the Data Plane closure;
11. retains no completed token cache;
12. coalesces concurrent acquisition for the same account/tenant/label while the request is in flight.

The in-flight map is not an identity store. Its promise is removed on success or failure, and the underlying VS Code authentication provider remains the owner of session/token caching and refresh.

### 6.3 Composition

The product singleton is injected from `MainController` into:

- OE v2 activation/controller;
- classic-editor completion metadata;
- central observability target resolution;
- metadata-cache performance probes.

Query Studio currently obtains the same stateless singleton directly because `DocumentSessionBinding` is created by document models outside the main controller's constructor graph. Its profile assembly still goes through the same pure adapter.

A future cleanup can inject a Query Studio binding factory, but no classic connection dependency is introduced by this slice.

### 6.4 Secondary sessions

Query Studio now prepares the profile once during `open` and retains the resulting providers. The same `PreparedConnection` auth bundle is reused for:

- the user query session;
- master-scoped database enumeration;
- vector diagnostic/model auxiliary sessions;
- reconnect/database switch;
- metadata sessions through a new prepared value with the same token source.

Reusing the closure does not reuse a raw token. Every invocation calls the token source again, and VS Code auth decides whether the cached session token remains valid.

OE v2 passes one prepared connection to its proof session and metadata coordinator. The integration test keeps spies on classic STS `sendRequest` and `ConnectionManager.connect`; both remain unused.

## 7. Identity and cache isolation

Previous profile/server fingerprints included server, database, user, auth kind, and TLS facts. AzureMFA profiles can have an empty `user`, so two accounts could alias the same MetadataStore/cache key.

The fingerprint input now also includes:

- the first non-empty `user` or `email` (classic normalization may persist `user: ""` for AzureMFA);
- `accountId`;
- `tenantId`.

The resulting value remains a truncated SHA-256/base64url digest. Raw identity values do not appear in keys, status dumps, diagnostics, or persistent cache paths.

Changing the key intentionally makes pre-change AzureMFA metadata cache entries unreachable. This is safer than reusing metadata captured under a different security context. Normal cache eviction removes the old entries later.

## 8. STS2 wire and driver behavior

### 8.1 Direct-token wire shape

The canonical open profile is:

```json
{
  "auth": {
    "kind": "accessToken",
    "token": "<opaque SQL token>"
  }
}
```

The extension fails locally with `SqlDataPlane.Auth` if:

- there is no token provider;
- token acquisition throws;
- the provider returns `undefined` or an empty string;
- the resolved account or tenant differs from an explicitly saved identity;
- the returned token is already expired or within the 60-second open safety window;
- the profile belongs to legacy MSAL account mode rather than VS Code account mode.

No knowingly empty token request is sent to `v2/connection.open`.

Token/password acquisition and `v2/connection.open` consume one end-to-end open deadline. If an interactive provider outlives that deadline, its eventual completion cannot send a late open. OE v2 also treats disconnect/reconnect as a generation boundary and closes any session returned by a superseded attempt.

### 8.2 Runtime credential selection

The hardened runtime selects the credential field from `auth.kind` rather than choosing the first tokenized auth property:

- `sqlLogin` resolves `password`;
- `accessToken` resolves canonical `token`;
- the old `accessToken` field is a transition alias only;
- mixed or duplicate credential fields are invalid;
- missing/empty access tokens are invalid;
- integrated auth carries no secret.

### 8.3 Pooling policy

`SqlConnection.AccessToken` is part of the SqlClient pool key. Rotating short-lived bearer strings with normal pooling can create unbounded pools and retain token material beyond the STS2 secret side-table lifetime.

For this static direct-token slice, STS2 sets `Pooling=false` for access-token opens.

Renewable pooled auth is deferred until the driver has:

- an abstraction such as `IDbAccessTokenSource` outside Core;
- a stable `AccessTokenCallback` per security context;
- pool partitioning by principal/account, tenant, auth strategy, and route/deployment realm;
- exact pool invalidation on logout/context revocation;
- cancellation, expiry, claims-challenge, and bounded-registry tests.

### 8.4 Connection ownership

SqlClient connection construction, access-token assignment, open, and server-info probing are one ownership region. Any failure before ownership transfers to `SqlClientSession` disposes the connection.

## 9. Secret, journal, and replay model

The access token exists in these locations only:

1. the VS Code authentication session/provider;
2. a short-lived extension promise/local variable;
3. the outbound JSON-RPC auth field;
4. the STS2 in-memory secret side table after gateway tokenization;
5. the driver request and `SqlConnection.AccessToken` until connection disposal.

It does not enter:

- Core envelopes as plaintext;
- journal JSON;
- replay descriptors;
- diagnostic events;
- export bundles;
- Query Studio document models;
- MetadataStore snapshots;
- perftest result/config artifacts.

Replay consumes recorded effect responses and does not execute the driver or reacquire tokens. A replay therefore validates deterministic orchestration, not live identity infrastructure.

The implementation uses random opaque refs in the form `secret:ref:<random>:<counter>`. Older SPEC text describing `secret:sha256` is stale and must not be treated as implementation truth.

## 10. Diagnostics and observability

### 10.1 New token span

`sqlDataPlane.auth.token` records:

- semantic auth kind;
- booleans indicating whether account, tenant, and label hints existed;
- duration;
- fixed result enum;
- coarse expiry bucket;
- fixed error class.

`sqlDataPlane.auth.token.coalesced` records that a concurrent open joined an in-flight acquisition.

Forbidden fields include raw account/tenant/label, resource endpoint, token, provider exception message, and claims.

The observability registry uses a longest-prefix `sqlDataPlane.auth.token.*` contract with an exhaustive safe-attribute set. The general `sqlDataPlane.*` family remains non-exhaustive and does not inherit token-specific fields.

### 10.2 Open-session and feature markers

The STS2 open span records stable Data Plane/backend error codes and server error number, not the raw provider/SqlClient message.

OE v2 keeps the actionable failure message in its in-memory UI state but emits only an error class.

Query Studio keeps the actionable message for its error dialog but its `mssql.queryStudio.connect.ready` marker records only a stable class/code in `reason`.

Metadata hydration, freshness, server-catalog, auxiliary-catalog, and completion logs likewise emit only the stable error `code`/class. Provider messages remain in interactive primary-connect UI only; they are not written to Session Diag, PerfMode, or persistent extension logs.

Expected post-fix diagnostic shape:

- token span result `acquired`;
- `sqlDataPlane.openSession` wire `authKind=accessToken`;
- Query Studio/OE ready/connected;
- no `sqlLogin` open for an AzureMFA profile;
- no account/token canary in the session journal.

## 11. Test coverage

### 11.1 Extension unit and hosted tests

The regression suites cover:

- exhaustive profile auth mapping;
- missing auth defaults to SQL Login;
- AzureMFA with no `user` and populated email/account/tenant;
- lazy token lookup and zero password lookups for AzureMFA;
- account/tenant fingerprint isolation and non-reversibility;
- unsupported Default, service principal, and unknown auth values;
- canonical STS2 `auth.token` wire shape;
- exactly one provider call per open;
- missing/empty/provider-failure classification before RPC;
- token/account/tenant/email diagnostic canaries;
- token acquisition single-flight;
- explicit account/tenant drift and near-expiry rejection;
- provider-failure privacy and single-flight cleanup;
- metadata/completion failure-log privacy;
- end-to-end auth/open deadline with no late RPC;
- OE disconnect-during-open supersession and unsupported-auth UI state;
- OE v2 plus metadata opens through injected token auth;
- no classic STS or `ConnectionManager.connect` use.

### 11.2 STS2 tests

The server suites cover:

- access token never enters the connection string;
- static-token pooling disabled;
- canonical field and legacy alias behavior;
- mixed/missing/empty token rejection;
- SQL empty-password compatibility;
- secret refs cleaned on all tested open terminals;
- connection disposal on every pre-session failure.

### 11.3 Live dogfood gate

After rebuilding/patching STS and reloading the extension:

1. Enable the SQL Data Plane, OE v2 preview, and `mssql.preview.useVscodeAccountsForEntraMFA`.
2. Connect the known SQL Login profile in OE v2 and Query Studio.
3. Connect the known AzureMFA profile in OE v2 and Query Studio.
4. Expand databases and one database catalog to force metadata sessions.
5. In Query Studio, list databases through the master session and open one auxiliary session path.
6. Let a token age or sign out/in, then reconnect.
7. Inspect the new Session Diag journal.
8. Assert AzureMFA opens are `accessToken`, SQL Login remains `sqlLogin`, and no identity/token values occur in diagnostics.

Available environment-variable lanes are:

- `STS2_SQLSERVER_CONNSTRING` for local/on-prem SQL;
- `STS2_AZURESQLSERVER_CONNSTRING` for Azure SQL Login;
- `STS2_AZURESQLSERVER_ENTRAID_CONNSTRING` for Azure server/database/TLS facts while the extension supplies the VS Code token.

Tests and scripts must report only presence, selected auth mode, and safe option names. They must never print the values.

## 12. Perftest integration

Existing Query Studio and OE v2 perf scenarios already exercise the same product commands and Data Plane opens once a suitable saved profile is provisioned.

Automated Entra performance runs need a separate authenticated-profile policy because normal perf profiles are disposable and must not copy VS Code authentication secrets into artifacts.

Recommended lanes:

1. **CI SQL Login lane:** unchanged, deterministic, official metrics.
2. **Developer Entra smoke:** reuse an explicitly selected existing VS Code user-data profile, run connect/browse/query once, store only redacted diagnostics, and mark results diagnostic/non-comparable.
3. **Managed hosted lane later:** use workload identity or OBO in the backend with no interactive desktop state; this can become a controlled performance lane.

Do not extend `ConnectionProfileSpec` with a raw bearer token. If account/tenant hints are added, they are control-channel credentials metadata and must be omitted/digested from results and logs.

Until that contract/profile work lands, the in-extension self-test marks AzureMFA and other non-SQL/non-Integrated profiles unavailable. It must never advertise an Entra profile and then coerce it to Integrated authentication.

The `sqlDataPlane.*` span family already admits the new token spans with `measurementEligible=false`. Token acquisition duration is diagnostic context, not an official Query Studio performance metric unless a future controlled identity scenario defines it explicitly.

## 13. Rollout and compatibility

1. Land adapter/token-source/client tests.
2. Land STS2 credential-field and pooling hardening.
3. Build/publish STS2 and patch it into the local extension.
4. Reload VS Code so the extension host uses the new bundle and STS executable.
5. Dogfood SQL Login and AzureMFA in Query Studio and OE v2.
6. Compare the post-fix session with `sess_20260711221704_1796`.
7. Run the existing Query Studio/OE v2 performance scenarios for SQL Login.
8. Add the diagnostic Entra smoke lane only after the user-data/profile policy is reviewed.

Backward compatibility:

- SQL Login and Integrated wire behavior are unchanged.
- STS2 accepts the former `accessToken` field only as a bounded transition alias.
- Unknown auth types now fail earlier and more clearly; this is an intentional correctness change.
- AzureMFA metadata cache keys change because account and tenant are now included.
- Explicit account/tenant drift is rejected instead of silently caching data under the requested identity.
- Legacy extension-MSAL profiles are not silently interpreted as VS Code accounts. This slice requires VS Code account mode and reports how to enable/reselect it.
- Remote adapters implementing `ISqlConnectionService` continue receiving a deferred token provider; they choose how to serialize/host it.

## 14. Deferred design work

### 14.1 Renewable credentials and pooling

Design a provider-neutral renewable credential source in `Sts2.Abstractions` and a runtime registry keyed by an opaque security-context ref. Keep the source object and live token outside Core and journals. Adapt it to a stable SqlClient `AccessTokenCallback` at the driver edge.

### 14.2 Hosted OBO and managed identity

For the Query Studio web backend:

- prefer host-side OBO when SQL must see the VS Code user;
- prefer managed identity when policy permits a service principal at SQL;
- advertise supported auth strategies in initialize capabilities;
- bind credential contexts to the authenticated Hop A principal and route realm;
- never accept an arbitrary SQL bearer solely because the caller can reach the endpoint.

See `querystudio_web_backend.md` sections 10-12 for the hosted trust-boundary design.

### 14.3 Additional auth kinds

Specify `ActiveDirectoryDefault` and service principal semantics as explicit protocol capabilities. Do not overload `sqlLogin` or `accessToken`.

### 14.4 Remaining STS2 lifecycle hardening

The audit also found follow-up work not required to fix this incident:

- track and await open tasks during runtime disposal;
- settle pending request promises on clean session disposal;
- expose/clear secret-table health safely at teardown;
- sanitize all fatal/component exception messages before wire/health output;
- make auth retryability and reauthentication-required states explicit;
- prevent raw-secret record `ToString()` output;
- add expiry/claims-challenge tests for renewable providers.

## 15. Review questions

1. Should direct static SQL token pass-through remain a production-supported STS2 mode after renewable host credentials exist?
2. Is `ActiveDirectoryDefault` allowed for a remote backend where it means the backend identity rather than the VS Code user?
3. Must every hosted SQL connection preserve end-user identity, or may selected routes use managed identity?
4. What event invalidates existing sessions and exact pools on account sign-out or tenant change?
5. Should Query Studio receive its token source through a binding factory to remove the remaining product singleton import?
6. Which authenticated reusable VS Code profile, if any, is acceptable for diagnostic Entra performance smoke runs?
7. When may token acquisition become an official measured span rather than diagnostic context?
8. Is legacy extension-owned MSAL account mode still a required Query Studio/OE v2 compatibility surface, or can VS Code account auth become the migration boundary?
