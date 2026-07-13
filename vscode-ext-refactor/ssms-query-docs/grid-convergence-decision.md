# QS-2 Decision Record: Query Studio results grid — custom table vs Fluent/slickgrid

**Status:** recommendation recorded 2026-07-06 (remaining-tasks pass, QS-2). Awaiting Karl's ratification; no code change required for the recommended path.
**Context:** Query Studio's results grid is a custom row-virtualized HTML table (built B3, extended through the QS-P1 QoL batch). Classic query results use slickgrid (jQuery-era, headerFilter plugin) and, in newer surfaces, FluentResultGrid. The revised remaining-tasks doc requires this decision before public preview.

## Recommendation

**Keep the custom virtualized table for the Query Studio preview. Do not adopt slickgrid. Treat FluentResultGrid convergence as a post-preview option, taken only if a concrete need (feature or maintenance) materializes — not as a scheduled migration.**

## Rationale

### Performance (measured)
- The custom grid renders the 10k-row scenario within the standing gate band every run (`querystudio-query-10k` official, 389–1100ms wallclock across the accrued history — dominated by backend + wire, not grid work); `resultsRendered` double-rAF marks put render at ~167ms for 10k rows.
- Row virtualization with dynamic row height (24px + rowPadding), IntersectionObserver lazy-mounting for many-grid scripts, and 512-row chunked materialization for in-memory sort/filter were all built directly against the QS data plane's windowed `QsGetRows` model. A grid swap re-opens every one of those code paths.
- Column virtualization is NOT implemented (recorded deviation) — but neither classic grid has it wired for our result shapes either; the wide-columns case is bounded today by the display clamp and is on the QS-3 scenario list to measure before optimizing.

### Maintenance
- slickgrid is the legacy path: jQuery-based, plugin-configured, and the thing the modernization effort is walking away from. Adopting it in the NEW editor would be strategy-inverted.
- FluentResultGrid is the plausible convergence target, but adopting it means: rework of windowed-fetch integration (it expects different data adapters), re-implementing the QoL features already shipped on the custom grid (NULL theme tokens, XML/JSON cell links via content sniffing, display clamps with link-out, in-memory filter/sort with the classic threshold semantics, alt-row striping under virtualization spacers), and a webview bundle-size hit — for no user-visible gain in the preview.
- The custom grid is ~small, dependency-free, fully theme-token native, and covered by 30+ unit tests (gridOps/gridStyle/cellDocument) plus the live gate.

### When to revisit (explicit triggers)
1. A required feature lands more cheaply on FluentResultGrid than on the custom table (e.g. column virtualization for the wide-columns case, if QS-3 measurement shows it matters; or column resize/reorder parity demands).
2. The product converges other result surfaces on FluentResultGrid and consistency pressure becomes real.
3. Grid-local defect rate in dogfood suggests the custom implementation is under-engineered for the long tail.

QS-3 (wide/blob perf scenarios, queued in this pass) supplies the measurement that would trigger (1).

## Alternatives considered
- **Adopt slickgrid now:** rejected — legacy dependency in the new stack; its headerFilter/in-memory model was already re-implemented natively with classic threshold semantics.
- **Adopt FluentResultGrid now:** rejected for preview — rework + bundle cost with zero preview-visible gain; revisit on the triggers above.
- **Hybrid (Fluent for grids under N rows):** rejected — two grid implementations in one page is the worst maintenance outcome.

## Consequences
- `autoSizeColumnsMode` stays unimplemented (CSS ellipsis) until a trigger fires; recorded as an accepted preview gap.
- The fluentSlickGrid.css theme delta from the completions branch stays unported (classic-grid styling decision, independent).
