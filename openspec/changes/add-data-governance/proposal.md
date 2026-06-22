## Why

The platform has no data governance: no schema registry, no data quality checks, no metadata catalog, no PII protection, no retention policies. PII (customer name and email) flows unmasked through Kafka and lands plaintext in ClickHouse. This change introduces a new `data-governance` capability that owns those concerns.

This is currently a **design-only proposal**. DESIGN.md captures the full direction (four pillars, tool choices, phased rollout). Per-capability delta files and implementation tasks are not yet written; they will be filled in once the design direction is approved.

## What Changes

- Add a new `data-governance` OpenSpec capability covering: schema contracts, data quality validation, metadata/lineage cataloging, PII masking and access control, and lifecycle (TTL/retention/archival).
- MODIFY existing capabilities where governance touches their observable behavior:
  - `cdc-pipeline`: Debezium converter switches from JSON to Avro; Spark jobs gain GX validation and OpenLineage emission; checkpoint path convention becomes version-suffixed.
  - `analytics`: ClickHouse tables gain TTL clauses; new `analyst_readonly` role and row policies; Grafana connects via the new role.
  - `infrastructure`: New `up-governance` / `down-governance` Make targets, new compose file, Schema Registry added to the Kafka compose file.
- Phased rollout (see DESIGN.md): retention → PII → schema-registry+DQ → catalog. Each phase ships independently.

## Capabilities

### New Capabilities
- `data-governance`: Contract enforcement, classification, and lifecycle of data flowing through the CDC pipeline. Owns schema contracts, data quality validation, PII masking and access control, and retention/archival policies.

### Modified Capabilities
- `cdc-pipeline`: Debezium converter, Spark validation/lineage steps, checkpoint path convention.
- `analytics`: ClickHouse TTLs, RBAC roles, row policies.
- `infrastructure`: Governance compose file, new Make targets, Schema Registry service.

## Impact

- Adds `openspec/changes/add-data-governance/DESIGN.md` (this turn).
- Future implementation will add: `openspec/specs/data-governance/spec.md`, per-capability deltas under `changes/add-data-governance/deltas/`, Schema Registry service, OpenMetadata stack, GX suites, PII UDFs, ClickHouse TTL/RBAC migrations.
- No code or configuration files are modified in this design-only turn.
