# Metadata cache diagram assets

This directory keeps the complete diagram set used by
`metadata_service_design_and_validation_report.tex` together with its source
artifacts.

## Layout

- `composites/codex_metadata_cache_composite.png` is the image-generated
  single-canvas memory, persistence, hydration, and consumer-flow study.
- `composites/external_metadata_cache_diagrams.png` is the alternate tall
  four-part composite moved from `metadata-cache-diagrams.png`.
- `diagram_set/` is the complete extracted bundle. It contains four focused
  diagrams in editable SVG, report-ready PDF, and high-resolution PNG forms,
  plus the contact sheet, combined four-page PDF, generator script, and the
  bundle's original README.
- `sources/codex_metadata_diagram_prompt.md` is the standalone prompt used for
  the Codex composite.
- `sources/metadata_cache_diagrams.zip` is the original bundle, retained
  unchanged as an archive.

## Report use

The report embeds both alternate composites and the PNG contact sheet. It uses
the individual PDF files for the four focused diagrams so that labels remain
vector-sharp when the report is enlarged. The PNG and SVG variants remain here
for slides, web use, and editing; they are intentionally not embedded a second
time.

The composites are visual design studies. When a rendered label differs from
the reviewed implementation evidence, the report prose, deterministic TikZ
figures, and source code take precedence.
