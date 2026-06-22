## ADDED Requirements

> **Status:** Placeholder requirements for the design-only phase of this proposal. Detailed scenarios for each phase (retention, PII, schema-registry+DQ, catalog) will be filled in as that phase reaches implementation. See `design.md` for the full direction.

### Requirement: pii-classification
PII columns (name, email, and any future contact fields) SHALL be marked in a central classification manifest and masked before landing in ClickHouse production tables that downstream consumers (Grafana, BI tools) can read.

#### Scenario: classified columns masked in analytics
- **WHEN** a CDC event for a PII-classified column reaches the ClickHouse analytics layer
- **THEN** the value visible to read-only analytics roles SHALL be masked (hashed or redacted) rather than the raw source value

### Requirement: ttl-retention
ClickHouse CDC tables SHALL declare a TTL clause defining the retention window for raw event history. Rows older than the TTL SHALL be removed automatically by ClickHouse.

#### Scenario: old rows expire
- **WHEN** a row in a CDC table is older than the table's configured TTL
- **THEN** ClickHouse merges SHALL drop the row without manual intervention

### Requirement: schema-contract
CDC event payloads SHALL be serialized against a registered schema (Avro or Protobuf) rather than ad-hoc JSON. Schema evolution SHALL go through a registry that enforces backward/forward compatibility rules per topic.

#### Scenario: incompatible producer rejected
- **WHEN** a producer attempts to publish a payload that violates the registered compatibility rule for its topic
- **THEN** the registry SHALL reject the schema and the producer SHALL fail to publish

### Requirement: data-quality-gate
Each Spark CDC job SHALL run a configured data-quality validation step (e.g., Great Expectations suite) on each micro-batch. Records that fail validation SHALL be routed to a quarantine sink rather than the production table.

#### Scenario: invalid row quarantined
- **WHEN** a CDC event fails a configured DQ check (null required field, out-of-range value, etc.)
- **THEN** the Spark job SHALL write the record to a quarantine table and SHALL NOT write it to the production `*_cdc` table

### Requirement: lineage-emission
Spark CDC jobs SHALL emit OpenLineage events on job start, completion, and failure, capturing input Kafka topic, output ClickHouse table, and row counts per batch.

#### Scenario: lineage events captured
- **WHEN** a Spark CDC job runs a micro-batch end-to-end
- **THEN** at least one OpenLineage `START` event and one `COMPLETE` event SHALL be emitted to the configured lineage collector, naming the Kafka topic input and ClickHouse table output
