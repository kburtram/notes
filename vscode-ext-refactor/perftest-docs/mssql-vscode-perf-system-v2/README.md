# MSSQL VS Code Performance System v2 Package

This package contains an implementation-ready design refresh for the MSSQL for VS Code end-to-end scenario performance system.

## Files

- `MSSQL_VSCODE_PERF_SYSTEM_DESIGN_V2.md` - detailed review and improved design.
- `schemas/perf-result.schema.json` - draft JSON Schema for per-repetition result records.
- `schemas/perf-config.schema.json` - draft JSON Schema for run configs.
- `schemas/marker.schema.json` - draft JSON Schema for line-delimited marker records.
- `sql/perf-store.schema.sql` - starter SQLite schema for local history, metrics, artifacts, baselines, and comparisons.
- `examples/config.measurement.local.jsonc` - sample cheap measurement-pass config.
- `examples/config.diagnostic.local.jsonc` - sample rich diagnostic-pass config.
- `examples/result.example.json` - valid result example for schema tests.

## Suggested next action

Start with Milestone 0 and Milestone 1 in the design doc: implement contracts, the CLI skeleton, the local control server, the automation extension handshake, `markers.jsonl`, `result.json`, SQLite insertion, and a simple report for a no-op scenario.
