# Shared Metadata Cache diagram set

This set decomposes the original one-page poster into four report-ready figures. The diagrams use a consistent 16:9 layout and palette, with enough detail to stand alone without forcing all implementation and policy details into one canvas.

## Recommended use

1. **`01_metadata_cache_architecture_overview`** - the primary architecture figure. It shows downstream consumers, the provider/lease seams, extension-host ownership, the immutable snapshot, live STS2 hydration, and optional persistence. The consumer row is explicitly marked as downstream integration rather than product routing shipped by PR #22836.
2. **`02_metadata_catalog_data_layout`** - the data-model figure. It explains H0-H7 row ingestion, string interning, the parallel structure-of-arrays tables, atomic publication, immutable generations, indexes, and pinned reads.
3. **`03_metadata_acquisition_freshness_drift`** - the runtime behavior figure. It shows cache-first acquisition, the four freshness policies, the dynamic offline boundary, dedicated metadata sessions, one-active-query behavior, the H0 identity gate, drift detection, and coalesced refresh.
4. **`04_metadata_cache_persistence_protocol`** - the persistence figure. It shows the on-disk representation, complete read trust chain, safe-miss behavior, canonical/privacy-projected writes, manifest-last commit, and cross-window authority under the per-key publication lock.

The original dense poster remains useful as a one-page appendix or implementation reference. For the main body of a design report, use the overview plus the focused figure that matches each section.

## Suggested captions

**Figure 1 - Shared metadata architecture and consumer flow.** The PR #22836 substrate owns key-correct leases, immutable catalog snapshots, live hydration, and optional persistence. Downstream language, AI, Query Studio, Object Explorer, scripting, and visualization consumers use leases or pinned views and do not bypass the shared store.

**Figure 2 - Compact immutable catalog layout.** H0-H7 catalog rows are accumulated in a private structure-of-arrays builder with one interned string table and owner indexes. `build()` atomically publishes a `CatalogSnapshot`; readers pin one generation and use pure synchronous APIs.

**Figure 3 - Acquisition, freshness, and drift.** Acquisition first attempts a verified local snapshot and resolves live infrastructure only when network policy permits. Consumer freshness intent is expressed through `allowStale`, `requireValidated`, `requireLive`, or `offlineSnapshot`; drift signals coalesce into a full H0-H7 refresh.

**Figure 4 - Persistent-cache trust and publication protocol.** A disk entry is adopted only after manifest, key, byte, logical-shape/hash, and policy checks. Writes use canonical privacy-projected payloads, content addressing, a per-key authority lock, atomic payload replacement, and manifest-last publication.

## Formats

- **SVG** - editable vector source for Figma, Illustrator, Inkscape, or direct web use.
- **PDF** - vector figure suitable for LaTeX and technical reports.
- **PNG** - 3840 x 2160 raster export suitable for slides and documents.
- **`metadata_cache_diagrams.pdf`** - all four vector figures in one four-page PDF.
- **`metadata_cache_diagrams_contact_sheet.png`** - quick 2x2 review sheet.

## LaTeX example

```tex
\begin{figure*}[t]
  \centering
  \includegraphics[width=\textwidth]{01_metadata_cache_architecture_overview.pdf}
  \caption{Shared metadata architecture and consumer flow.}
  \label{fig:metadata-architecture}
\end{figure*}
```
