## Why

This baseline proposal documents the existing ecommerce CDC platform so that all future changes can be expressed as deltas against a known, spec-covered state. Without a baseline, there is no common reference for what the system currently does, making it impossible to write meaningful ADDED/MODIFIED/REMOVED requirement diffs.

## What Changes

This is a documentation-only baseline. No code changes. All capabilities below are ADDED as initial specs capturing current production behavior.

## Capabilities

### New Capabilities
- `cdc-pipeline`: End-to-end CDC data flow from Postgres through Debezium and Kafka to PySpark Structured Streaming and ClickHouse
- `streamlit-ui`: Interactive testing UI for generating and observing CDC events across customers, products, and orders
- `analytics`: ClickHouse ReplacingMergeTree deduplication pattern and Grafana dashboard provisioning
- `infrastructure`: Modular Docker Compose stack orchestrated via Makefile with per-service targets

### Modified Capabilities

(none — this is the initial baseline)

## Impact

- Adds `openspec/specs/` with one spec file per capability
- Adds `openspec/changes/baseline/` with PROPOSAL.md, DESIGN.md, TASKS.md
- No code, configuration, or infrastructure files are modified
