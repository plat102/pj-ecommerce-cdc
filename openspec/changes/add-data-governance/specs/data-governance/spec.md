## ADDED Requirements

> **Status:** Placeholder requirements for the design-only phase of this proposal. Detailed scenarios for each phase (retention, PII, schema-registry+DQ, catalog) will be filled in as that phase reaches implementation. See `design.md` for the full direction.
>
> **On archive**, each broad placeholder below decomposes into the phase-scoped requirements listed in `design.md` § "Requirements That Will Be Declared":
>
> | Placeholder here | Decomposes into (on archive) |
> |---|---|
> | `pii-classification` | `pii-hashing-customers-email`, `pii-tokenization-customers-name`, `clickhouse-rbac-roles`, `cdc-consumer-access-log` |
> | `ttl-retention` | `clickhouse-ttl-policies`, `kafka-topic-retention`, `postgres-archival-policy`, `checkpoint-versioned-paths` |
> | `schema-contract` | `schema-registry-publication` |
> | `data-quality-gate` | `gx-batch-validation`, `dlq-on-validation-failure`, `freshness-slo-and-alert` |
> | `lineage-emission` | `openmetadata-ingestion`, `openlineage-spark-emission`, `column-documentation-coverage` |

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

---

## Phase 1 — Retention & Lifecycle (decomposed from `ttl-retention`)

The four requirements below are the phase-scoped decomposition of the `ttl-retention` placeholder for Phase 1 (Pillar 4). They coexist with the placeholder until archive (task 5.3), when the placeholder is replaced by these narrow requirements.

### Requirement: clickhouse-ttl-policies
Each ClickHouse CDC table (`customers_cdc`, `products_cdc`, `orders_cdc`) SHALL declare two TTL clauses anchored on the Debezium change timestamp: `toDateTime(_version / 1000) + INTERVAL 90 DAY DELETE WHERE _deleted = 1` (tombstone retention) and `toDateTime(_version / 1000) + INTERVAL 2 YEAR DELETE` (active-row retention). The TTL definitions live in `infrastructure/docker/clickhouse/create_tables.sql`.

#### Scenario: tombstone row expires after 90 days
- **WHEN** a row with `_deleted = 1` and a `_version` older than 90 days ago is processed during a ClickHouse merge
- **THEN** the row SHALL be removed from the table

#### Scenario: active row expires after 2 years
- **WHEN** any row with a `_version` older than 2 years ago is processed during a ClickHouse merge
- **THEN** the row SHALL be removed from the table regardless of `_deleted` value

### Requirement: kafka-topic-retention
Kafka topics SHALL carry explicit `retention.ms` configuration set by `data-platform/governance/retention/apply-kafka-topic-retention.sh`: `pg.public.*` topics = 7 days, `governance.access_log` = 30 days, `*_dlq` topics = 14 days. Governance and DLQ topics that do not yet exist SHALL be created by the same script with the correct retention.

#### Scenario: retention applied to existing pg topic
- **WHEN** the retention script runs and a `pg.public.customers` topic already exists
- **THEN** its `retention.ms` SHALL be updated to `604800000` (7 days in ms)

#### Scenario: governance topic created with retention
- **WHEN** the retention script runs and `governance.access_log` does not exist
- **THEN** it SHALL be created with `retention.ms=2592000000` (30 days)

### Requirement: postgres-archival-policy
`data-platform/governance/retention/postgres-archive.sql` SHALL define an `orders_archive` table and, on execution, move rows from `orders` where `order_time` is older than 1 year into it. The archive table SHALL NOT appear in the Debezium connector's `table.include.list`.

#### Scenario: rows older than one year moved to archive
- **WHEN** the archival SQL is executed against a database containing `orders` rows with `order_time < CURRENT_TIMESTAMP - INTERVAL '1 year'`
- **THEN** those rows SHALL exist in `orders_archive` and SHALL NOT exist in `orders`

#### Scenario: archive table excluded from CDC
- **WHEN** the Debezium connector configuration in `data-platform/cdc/connectors/register-pg.json` is inspected
- **THEN** `table.include.list` SHALL NOT contain `public.orders_archive`

### Requirement: checkpoint-versioned-paths
`BaseCDCJob` in `data-platform/streaming/spark/src/jobs/base_cdc_job.py` SHALL construct Spark checkpoint paths as `{CHECKPOINT_LOCATION}/{table_name}/v{schema_version}`. Phase 1 hard-codes `schema_version = 1`; the integer becomes a live schema version once Schema Registry lands in Phase 3.

#### Scenario: checkpoint path includes version suffix
- **WHEN** a CDC job starts in production mode
- **THEN** the Spark `checkpointLocation` option SHALL be `{CHECKPOINT_LOCATION}/{table_name}/v1`
