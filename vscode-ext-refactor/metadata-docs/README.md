# metadata-docs — deep review pack for the metadata substrate

**Created 2026-07-06** for a deep design review of the metadata area (MetadataStore / MetadataService / CatalogModel) and its four consumers (Query Studio, native language service, AI completions, Object Explorer v2).

| File | What it is |
|---|---|
| `metadata-substrate-design.md` | The deep as-built design notes: three layers, the two consumer seams, per-consumer contracts, privacy/observability boundaries, measured performance, a 12-entry decision log with alternatives, honest gaps, and a suggested review path. Code truth: vscode-mssql `99a44957c`, sqltoolsservice `7532d145`. |
| `METADATA_DESIGN_VISUALS.tex` | Five TikZ diagram pages in the same visual language as the STS2 review pack (`sqltoolsservice/refactor_docs/STS2_REVIEW_PACKAGE/diagrams/`): (1) layered architecture, (2) identity/keys + lease lifecycle state machine, (3) hydration ladder + generations + drift loop, (4) consumer flows + privacy gates, (5) session strategy + measured numbers + gaps. Compile with `pdflatex METADATA_DESIGN_VISUALS.tex` (twice). Authored without local TeX tooling — any compile complaint should be a one-line fix, not structural. |

Related source-of-truth docs: `oe-docs/metadata_service_oe_v2_design.md` (the store spec this implements/deviates from), `ssms-query-docs/02-metadata-service-design.reviewed.md` (the original engine spec), and the PROGRESS journals (`oe-docs`, `language-service-docs`, `ssms-query-docs`) for the batch-by-batch build record.
