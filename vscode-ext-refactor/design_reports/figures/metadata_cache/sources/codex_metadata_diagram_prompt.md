# Shared metadata cache — standalone image-generation prompt

Copy the complete prompt below into an image-generation model. It is intentionally self-contained: the renderer should not need the report or either code repository.

```text
Use case: infographic-diagram
Asset type: a publication-quality landscape systems-architecture diagram for a technical LaTeX design report

Primary request:
Create one precise, clean diagram titled “Shared Metadata Cache: Memory, Persistence, and Consumer Flow”. Explain how vscode-mssql turns SQL Server catalog rows into immutable in-memory metadata snapshots, shares them across product features, loads and saves the optional persistent cache, detects drift, and refreshes safely. This is an engineering diagram, not decorative concept art.

Architecture basis:
This is a composite as-built view. The metadata/cache substrate is the implementation reviewed in vscode-mssql PR #22836. The top consumer wiring reflects the downstream dev/refactor integration: Query Studio, the native T-SQL language service, AI inline completions, Object Explorer v2, scripting, and the schema visualizer all reuse the shared MetadataStore. Make the scope note visible but small: “Composite view: PR #22836 substrate + dev/refactor consumers”.

Canvas and visual style:
- 16:9 landscape, very high resolution, suitable for a report or presentation; use the whole canvas.
- Flat vector-like technical infographic; white or very pale blue-gray background; no gradients, 3D, isometric perspective, code screenshots, mascots, or decorative database clip art.
- Crisp dark-ink typography, generous whitespace, disciplined alignment, rounded rectangular cards, thin container outlines, and orthogonal or gently curved arrows that do not cross labels.
- Match this restrained report palette: dark ink #18222D, slate #4D5B6A, violet #6D5BD0 / dark violet #4E3DA8 for ownership and control, teal #0C7C86 with pale mint #E9F7F4 for in-memory data, amber #A86500 with pale amber #FFF5DD for disk cache and persistence, pale blue-gray #EAF0F5 for infrastructure, green #277A55 with pale green #EAF7F0 for gates that pass, and muted red #A43842 with pale red #FFF0F1 only for rejection, corruption, or unavailable paths.
- Use a modern humanist sans-serif. All labels must be horizontal and readable at normal page zoom; never solve crowding with tiny text.

Overall composition:
Use four clearly separated regions with the immutable CatalogSnapshot as the visual center:
1. A top band named “Consumers — leases and pinned views only”.
2. A middle-left band named “Extension-host ownership and policy”.
3. A large middle region named “In-memory catalog layout”.
4. A bottom split: “Persistent disk cache” on the left and “Live hydration and drift” on the right.

Make the principal reading path obvious:
SQL Server → STS2 dedicated metadata sessions → H0–H7 row pages → CatalogBuilder → atomic CatalogSnapshot generation N+1 → shared leases/pinned views → consumers.
Show the persistence loop separately:
disk cache → verify and rehydrate → CatalogSnapshot, and CatalogSnapshot → debounce/canonicalize/gzip/atomic commit → disk cache.

TOP BAND — CONSUMERS:
Draw six compact consumer cards. None of them may connect directly to disk files, STS2, or SQL Server.

1. “Query Studio”
   Subtext: “document/database binding • acquires DatabaseCatalogLease • successful DDL → notifyExecutedBatch”.
   It reuses the same lease for native language features and AI context.

2. “Native T-SQL language service”
   Subtext: “CatalogLanguageMetadataProvider → IPinnedMetadataView • pin once per request • synchronous snapshot reads”.
   List: “completion • hover • signature • definition • diagnostics”.
   Add a small invariant pill: “no network on the keystroke path”.
   Completion uses allowStale and starts refresh asynchronously. Diagnostics use requireValidated and suppress schema claims when objects/columns are not trustworthy. The only sanctioned asynchronous read from a pin is an explicit lazy module-definition resolve.

3. “AI inline completions”
   Subtext: “Query Studio handle or classic-editor shared lease • allowStale(aiContext)”.
   Show a tiny internal pipeline: “pinned CatalogSnapshot → bounded deterministic schema context → relevance selection → model prompt”.
   Add: “derived context cache keyed by identity + generation + budget”.
   It never performs its own catalog query and never reads cache files.

4. “Object Explorer v2”
   Subtext: “one server lease + lazy database leases • requireValidated browse • pin once per expand”.
   Add: “server/database auxiliary sections hydrate lazily” and “failed or unavailable ≠ empty folder”.

5. “Scripting”
   Subtext: “requireLive for fidelity-sensitive output • explicit offline path only • one pinned view”.

6. “Schema visualizer”
   Subtext: “DatabaseCatalogLease → one CatalogSnapshot → graph model • no ad-hoc catalog SQL”.

Below the consumer cards, draw two narrow interface bars:
- “Language-provider seam — ISqlLanguageMetadataProvider / IPinnedMetadataView” under the language and scripting consumers.
- “Lease surface — ServerCatalogLease / DatabaseCatalogLease” under Query Studio, AI, Object Explorer v2, and the visualizer.
Both bars flow into the shared MetadataStore, never into the cache directly.

MIDDLE-LEFT — EXTENSION-HOST OWNERSHIP AND POLICY:
Draw one violet container titled “MetadataStoreService / MetadataStore — one per extension host”. Inside it show two maps:

- “Server map: sfp_* → ServerMetadataService + server auxiliary catalog”
- “Database map: {sfp_*, exact database spelling} → MetadataService + main source + auxiliary source + listeners”

Inside or immediately below the container list these lifecycle properties:
- “same-key first acquire is single-flight”
- “ref-counted leases”
- “zero-ref database stays warm for bounded idle TTL”
- “idle database LRU cap”
- “deferred credentials and lazy provider resolution”
- “dynamic network-authorization gate”
- “per-server validation limiter”

Show the key correctness rule prominently:
“H0 DB_NAME() + catalog case rule must match the requested database key before H1 or any cache publication”.
A muted-red reject arrow must say: “mismatch / timeout / identity drift → fence epoch, recycle session, no cross-key publish”.

Add a four-segment policy router directly under MetadataStore:
- “allowStale — serve now; optional background refresh”
- “requireValidated — TTL or coalesced T1 digest; refresh if changed”
- “requireLive — join/start full refresh; unavailable on failure”
- “offlineSnapshot — zero resolver/session/query/timer/auxiliary work; disk/memory hit is stale, miss unavailable”

Make clear that caller timeouts or aborts stop only that caller’s wait; they do not cancel coalesced hydration or validation shared by other leases.

LARGE CENTER — IN-MEMORY CATALOG LAYOUT:
This is the visual focal point. Draw two adjacent mint/teal cards with a strong arrow between them.

Left card title: “CatalogBuilder — private, mutable during hydration”.
Depict a compact memory layout, not a tree of heap objects:
- “strings[] + stringIndex” as one intern table.
- Parallel structure-of-arrays tables whose integer *Sym fields point into strings[]:
  “schemas: schemaIds | schemaNameSyms”
  “objects: objectIds | schemaIds | nameSyms | kinds | modifyDates”
  “columns: ownerIndex | nameSym | typeSym | nullable | identity | computed | exact detail arrays”
  “keys: ownerIndex | constraintNameSym | kind | ordered columnSym”
  “foreign keys: fromId | toId | nameSym | constraintId | actions”
  “FK pairs: constraintId | ordinal | fromColumnSym/Id | toColumnSym/Id”
  “parameters: ownerIndex | ordinal | nameSym | typeSym | output”
  “descriptions: ownerIndex | optional columnSym | valueSym”
- Add “objectIndexById → O(1) dependent-row append”.
- Use thin pointer lines from several *Sym columns back to strings[] so interning is visually obvious.

Arrow from builder to snapshot must read:
“build(generation N+1, readiness, mode) — atomic full replacement”.

Right card title: “CatalogSnapshot — immutable generation N”.
Show three subsections:

A. Header / truth:
“generation • capturedAtUtc • optional contentHash • mode: full | partial | lite”
“per-section readiness: absent | loading | ready | failed | stale | lite”
Add: “readiness/completeness is separate from freshness/age”.

B. Shared SoA storage and read-only indexes:
“same interned arrays”
“objectId → object index”
“folded-name prefix index”
“schemaId → schema name”
“column and parameter [start,end) ranges”
“PK/UQ, FK-pair, FK-degree, description maps”

C. Pure synchronous APIs:
“resolveName • search • listSchemas/listObjects • getColumns • getKeys • getFKs • getParameters • build bounded schema context”.

Draw multiple thin snapshot tabs behind generation N and label them “older generations remain valid for holders”. Consumers pin one tab for the whole response and never mix generations.

Beside the snapshot, draw a small separate memory-only box:
“Lazy module definitions — sys.sql_modules on explicit resolve • cached only for current generation • never in persistent payload”.

BOTTOM-RIGHT — LIVE HYDRATION AND DRIFT:
Draw a blue-gray session/infrastructure lane:
“LazyMetadataConnection” → “SQL Data Plane service view” → “STS2 local backend” → “SQL Server sys.* catalogs”.
Label the protocol arrows “v2/connection.open” and “v2/query.execute → result metadata + row pages + query.complete”.
State explicitly: “No v2/metadata.* endpoint today; catalog SQL runs over generic STS2 query execution”.

Show three dedicated session lanes:
- “Main DB lane — serial H0–H7, T1 digest, lazy definitions”
- “DB auxiliary lane — separate session source; catalog-wide FIFO across section keys”
- “Server metadata / server auxiliary — independent sources”
Place a badge over STS2: “one active query per physical connection”.
User query/F5 sessions are separate and must not appear inside these lanes.

Show the hydration ladder as a clean horizontal sequence:
- “H0 environment + authoritative database identity”
- “H1 schemas”
- “H2 objects + synonyms”
- “H3 columns + exact type/default/identity/computed facts”
- “H4 PK/UQ”
- “H5/H5B FKs + ordered column pairs”
- “H6 parameters”
- “H7 descriptions”
H0 gates all later publication. H3–H7 failures are recorded as failed/partial, not converted to empty success. A watchdog fences abandoned results and recycles a timed-out source before retry.

Below the ladder, show three drift inputs merging into one coalesced refresh arrow back to CatalogBuilder:
- “successful local DDL sniff: CREATE / ALTER / DROP / SP_RENAME; EXEC → digest”
- “T1 cheap digest: visible object count + objectId + schemaId + byte-exact name + modifyDate”
- “explicit consumer validation or refresh policy”
Label the result: “changed → coalesced full H0–H7 refresh → publish generation N+1; unchanged → validation timestamp only”.

BOTTOM-LEFT — PERSISTENT DISK CACHE:
Use an amber container titled “Optional persistent database cache — not the authority”. Include the exact conceptual path:
“globalStorage/metadata-cache/v1/”
“index.json  (advisory listing/access/LRU; approximate across windows)”
“databases/<sfp_*>/<dbh_...>/”
“  .publication.lock”
“  manifest.json”
“  catalog.<compressed-sha256>.json.gz”

Clarify that only database CatalogSnapshots are persisted in this design; server catalogs and auxiliary sections are live/lazy memory structures.

Draw a numbered READ path from disk to CatalogSnapshot:
1. “validate manifest format / codec / model / shape”
2. “bind requested key: server fingerprint + database hash + optional exact name”
3. “check file, compressed-size bound, compressed SHA-256, bounded gunzip”
4. “parse and validate parallel-array + referential invariants”
5. “recompute canonical logical contentHash”
6. “intersect current privacy/readiness policy; rehydrate and publish with original capture age + generation”
Any failed proof must follow a muted-red branch labeled “safe miss → manifest invalidated; quarantine/delete best effort; live hydrate only if network policy allows”.

Draw a numbered WRITE path from CatalogSnapshot to disk:
1. “eligible published snapshot; debounce 5 s; latest generation wins”
2. “CatalogCodecView → canonical cm2 JSON in frozen field order”
3. “privacy projection: omit descriptions, module text, row counts, and default/computed SQL definitions”
4. “logical contentHash = csh_* over canonical uncompressed JSON”
5. “gzip; compressed SHA-256; enforce 32 MiB entry cap”
6. “acquire exclusive per-key publication lock”
7. “compare global authority by capturedAtUtc; equal time breaks by ordinal contentHash”
8. “payload temp + fsync + rename”
9. “manifest temp + fsync + rename LAST”
10. “postcheck winning writer; if same logical content and policy, rewrite manifest validation only”

Inside a miniature manifest card, show only these representative fields:
“producer • writerId • key • capture/generation/source • validation • environment • readiness/mode • stats/privacy • payload file/SHA/contentHash”.

At the bottom of the disk container add:
“default off • max age 14 days • total budget 256 MiB • 32 MiB compressed/entry • orphan grace 10 min”.
Add “clear removes manifest first; remaining payload bytes are inert”.
Add a lock icon with “content addressing protects bytes; the per-key critical section protects publication authority”.

ARROWS AND LEGEND:
- Solid violet arrow = ownership, lease, or synchronous call.
- Solid teal arrow = metadata rows or immutable snapshot data.
- Dashed violet arrow = asynchronous refresh, notification, or debounced work.
- Amber double arrow = verified disk read/write.
- Dashed red arrow = reject, safe miss, corruption, identity drift, or unavailable result.
- Include a compact legend in an unused corner.

Prominent invariants, rendered as four small pills across the bottom edge:
“PIN ONCE PER RESPONSE”
“FAILURE IS NEVER EMPTINESS”
“NO NETWORK ON THE KEYSTROKE PATH”
“MANIFEST LAST; CACHE IS NOT AUTHORITY”

Accuracy constraints:
- Consumers communicate with leases or pinned views, never directly with the disk cache, STS2, or SQL Server.
- The persistent cache communicates through MetadataCacheCoordinator/MetadataStore and stores the canonical snapshot projection; it is not a second mutable catalog model.
- Do not show a dedicated STS2 metadata endpoint; it does not exist in this architecture.
- Do not show parallel catalog queries on one STS2 connection; one physical connection permits one active query.
- Do not imply that a cache hit is automatically fresh or live.
- Do not collapse readiness, freshness, source, and mode into one boolean.
- Do not show secrets, passwords, tokens, connection strings, SQL result values, prompts, module text, or descriptions inside telemetry or persistence.
- Do not depict generation as cross-process publication authority; disk authority uses capture time plus content-hash tie-break.
- Do not label failed or unavailable metadata as an empty list or empty folder.
- Do not invent additional services, queues, databases, or network hops.

Text rendering constraints:
Render all quoted titles, interface names, protocol names, H0–H7 labels, policy names, and invariant pills verbatim. Use no lorem ipsum and no random extra labels. If the canvas cannot carry every low-level bullet legibly, preserve the main architecture, memory layout, cache read/write trust chain, consumer relationships, and invariant pills; shorten secondary prose instead of reducing the font below readable size.

Avoid:
photorealism, 3D cylinders, clouds, neon cyberpunk styling, heavy shadows, gradients, decorative icons, crowded spaghetti arrows, tiny footnotes, fake UI chrome, code screenshots, watermarks, logos, trademarks, or any text not requested above.
```
