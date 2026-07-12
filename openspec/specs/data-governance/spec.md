# data-governance Specification

## Purpose
TBD - created by archiving change add-data-governance. Update Purpose after archive.
## Requirements
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

---

**Phase 2 — PII / Access Control / Audit (decomposed from `pii-classification`).**

The four requirements below are the phase-scoped decomposition of the `pii-classification` placeholder for Phase 2 (Pillar 3).

### Requirement: pii-hashing-customers-email
`customers.email` values SHALL be transformed to a deterministic SHA-256 digest, salted with the `PII_SALT` environment variable, before being written to `ecommerce_analytics.customers_cdc` in ClickHouse. The transformation lives in `data-platform/streaming/spark/src/utils/udfs.py` (`hash_pii_udf`) and is applied by `data-platform/streaming/spark/src/transformations/customers_cdc_transformer.py`.

#### Scenario: raw email never lands in ClickHouse
- **WHEN** a CDC event with a non-null `customers.email` value is transformed by `CustomersCDCTransformer.transform_customers_cdc_for_clickhouse`
- **THEN** the output row's `email` column SHALL be a 64-character lowercase hex SHA-256 digest and SHALL NOT equal the source plaintext

#### Scenario: hash is deterministic under fixed salt
- **WHEN** the same email value is transformed twice with the same `PII_SALT`
- **THEN** both transformed values SHALL be byte-identical, so downstream joins by hashed email are stable

### Requirement: pii-tokenization-customers-name
`customers.name` values SHALL be transformed into an irreversible token of the form `{first-initial-uppercase}.{6-hex-chars}` (where the hex is SHA-256 of the remaining characters with `PII_SALT`) before being written to `ecommerce_analytics.customers_cdc`. The transformation is implemented by `tokenize_name_udf` in `data-platform/streaming/spark/src/utils/udfs.py`.

#### Scenario: name landed in ClickHouse is tokenized
- **WHEN** a CDC event with a non-null `customers.name` value is transformed
- **THEN** the output row's `name` column SHALL match the pattern `[A-Z]\.[0-9a-f]{6}` and SHALL NOT contain the original full name

### Requirement: clickhouse-rbac-roles
ClickHouse SHALL declare a role `analyst_readonly` in `infrastructure/docker/clickhouse/create_tables.sql` with SELECT-only grants on `customers_cdc`, `products_cdc`, and `orders_cdc`, plus row policies that restrict the visible rows to `_deleted = 0`. The matching user is created at container init from `create_governance_users.sh` using the `CLICKHOUSE_ANALYST_PASSWORD` env var. `infrastructure/docker/grafana/provisioning/datasources/clickhouse.yml` SHALL connect using `username: analyst_readonly` and reference `$CLICKHOUSE_ANALYST_PASSWORD` for the password.

#### Scenario: analyst role sees only active rows
- **WHEN** a user connected as `analyst_readonly` runs `SELECT * FROM ecommerce_analytics.customers_cdc`
- **THEN** the result set SHALL contain no rows where `_deleted = 1`

#### Scenario: analyst role cannot write
- **WHEN** a user connected as `analyst_readonly` runs an `INSERT`, `ALTER`, or `DROP` against any table in `ecommerce_analytics`
- **THEN** ClickHouse SHALL reject the statement with an access-denied error

#### Scenario: Grafana datasource uses analyst credentials
- **WHEN** the Grafana provisioning file `infrastructure/docker/grafana/provisioning/datasources/clickhouse.yml` is inspected
- **THEN** `jsonData.username` SHALL be `analyst_readonly` and `secureJsonData.password` SHALL reference `$CLICKHOUSE_ANALYST_PASSWORD` rather than a literal password

### Requirement: cdc-consumer-access-log
Every consumer of the CDC Kafka topics SHALL emit a single startup event to the `governance.access_log` Kafka topic on process start. The event SHALL be a JSON object containing `event: "consumer_start"`, `principal`, `topics` (the subscribed set), `timestamp`, `host`, and `pid`. Failure to emit SHALL be logged but SHALL NOT block the consumer.

#### Scenario: Spark CDC job emits startup event
- **WHEN** `data-platform/streaming/spark/apps/run_cdc_job.py` starts a job with `--job-type customers`
- **THEN** exactly one event with `principal = "spark-customers-cdc"` and `topics = ["pg.public.customers"]` SHALL be published to `governance.access_log`

#### Scenario: Streamlit Kafka monitor emits startup event
- **WHEN** a Streamlit session opens the Kafka monitor view for the first time
- **THEN** exactly one event with `principal = "streamlit-kafka-monitor"` SHALL be published to `governance.access_log` for the session

---

**Phase 3 — Schema Registry + Data Quality (decomposed from `schema-contract` and `data-quality-gate`).** The four requirements below are the phase-scoped decomposition for Phase 3 (Pillar 1).

### Requirement: schema-registry-publication
The Debezium PostgreSQL source connector SHALL use `io.apicurio.registry.utils.converter.AvroConverter` with an `apicurio.registry.url` value pointing at the Apicurio Registry service (`http://schema-registry:8080/apis/registry/v2`). Each of the three CDC topics (`pg.public.customers`, `pg.public.products`, `pg.public.orders`) SHALL have a registered key artifact and value artifact in Apicurio Registry after the first CDC event flows through.

#### Scenario: connector uses Apicurio Avro converter
- **WHEN** `data-platform/cdc/connectors/register-pg.json` is inspected
- **THEN** both `key.converter` and `value.converter` SHALL be `io.apicurio.registry.utils.converter.AvroConverter`
- **AND** both `key.converter.apicurio.registry.url` and `value.converter.apicurio.registry.url` SHALL be `http://schema-registry:8080/apis/registry/v2`
- **AND** both `.apicurio.registry.auto-register` SHALL be `"true"` (Debezium creates the artifact on first publish)

#### Scenario: artifacts registered after first message
- **WHEN** a CDC event is produced to `pg.public.customers` after applying the Avro connector config
- **THEN** the Apicurio Registry SHALL contain artifacts with IDs `pg.public.customers-key` and `pg.public.customers-value` in the default group with at least one registered version each

### Requirement: gx-batch-validation
Each Spark CDC job SHALL run a Great Expectations suite (loaded from `data-platform/governance/expectations/{table}_suite.json`) against every micro-batch DataFrame **before** the ClickHouse write. Suites SHALL be gated by the `ENABLE_GX_GATE=1` environment variable so dev environments without the `great_expectations` package continue to function unchanged.

#### Scenario: valid rows written to ClickHouse
- **WHEN** a batch of CDC events passes every column-level expectation in the table's suite
- **THEN** all rows in the batch SHALL be written to the ClickHouse `{table}_cdc` table via the existing JDBC writer

#### Scenario: expectation suite path
- **WHEN** the customers CDC job starts under `ENABLE_GX_GATE=1`
- **THEN** the suite SHALL be resolved from `${GX_SUITE_DIR:-/home/jupyter/governance/expectations}/customers_suite.json` and SHALL contain at least the `expect_column_values_to_not_be_null` expectation on `id` and `_version`

### Requirement: dlq-on-validation-failure
Rows that fail any column-level expectation SHALL be routed to a `{table}_dlq` Kafka topic before the `foreachBatch` delegates to the ClickHouse writer. The DLQ payload SHALL be the JSON serialization of the failing row plus a `_failed_expectation` field naming the first failing expectation type. Failing rows SHALL NOT reach the ClickHouse `{table}_cdc` table.

#### Scenario: invalid row lands in DLQ
- **WHEN** a customers CDC event arrives with `id = null` and `ENABLE_GX_GATE=1`
- **THEN** the row SHALL be written to `customers_dlq` with `_failed_expectation = "expect_column_values_to_not_be_null"`
- **AND** the same row SHALL NOT appear in `customers_cdc`

#### Scenario: valid rows in the same batch still land
- **WHEN** a batch of 10 orders contains one row failing `expect_column_values_to_be_in_set` on `_deleted` and nine passing rows
- **THEN** the nine passing rows SHALL be written to `orders_cdc` and the one failing row SHALL be written to `orders_dlq`

### Requirement: freshness-slo-and-alert
The ClickHouse `data_freshness` view SHALL be wired to a Grafana alert rule that fires when any target table has `minutes_since_last_update > 10`. The alert rule SHALL be provisioned via `infrastructure/docker/grafana/provisioning/alerting/data_freshness.yml` (not hand-configured in the Grafana UI).

#### Scenario: alert rule provisioned
- **WHEN** Grafana boots with the alerting provisioning file present
- **THEN** the rule `cdc_freshness_10min_slo` SHALL exist in the `data-governance` folder with `for: 2m`
- **AND** the rule's SQL SHALL query `SELECT max(minutes_since_last_update) AS value FROM data_freshness`

#### Scenario: stalled pipeline triggers alert
- **WHEN** Spark CDC jobs are stopped and no new events reach ClickHouse for > 10 minutes
- **THEN** the `cdc_freshness_10min_slo` rule SHALL enter the `Alerting` state after its 2-minute confirmation window

---

**Phase 4 — Metadata & Lineage Catalog (decomposed from `lineage-emission`).** The three requirements below are the phase-scoped decomposition for Phase 4 (Pillar 2).

### Requirement: openmetadata-ingestion
The project SHALL ship OpenMetadata ingestion configuration files for each system in the CDC pipeline it owns as a data producer or consumer: PostgreSQL source, Kafka + Schema Registry, and ClickHouse sink. Each config SHALL live under `data-platform/governance/openmetadata/ingestion/{postgres,kafka,clickhouse}.yaml` and be runnable via `metadata ingest -c <path>`.

#### Scenario: three ingestion configs exist
- **WHEN** `data-platform/governance/openmetadata/ingestion/` is inspected
- **THEN** it SHALL contain `postgres.yaml`, `kafka.yaml`, and `clickhouse.yaml`, each declaring a `source`, `sink` (`metadata-rest`), and `workflowConfig` block

#### Scenario: kafka config uses Apicurio ccompat endpoint
- **WHEN** `kafka.yaml` is inspected
- **THEN** `source.serviceConnection.config.schemaRegistryURL` SHALL be `http://schema-registry:8080/apis/ccompat/v7` (Apicurio's Confluent-compatible endpoint, which OpenMetadata's kafka ingestion targets natively)

### Requirement: openlineage-spark-emission
When `ENABLE_OPENLINEAGE=1` is set at Spark job submission time, `data-platform/streaming/spark/scripts/submit_job.sh` SHALL wire the OpenLineage Spark listener into `spark-submit` and emit lineage events to OpenMetadata's OpenLineage endpoint. The listener SHALL be off by default so dev environments without a lineage collector are unaffected.

#### Scenario: listener wired when enabled
- **WHEN** `submit_job.sh` runs with `ENABLE_OPENLINEAGE=1`
- **THEN** the resulting `spark-submit` command SHALL include `--conf spark.extraListeners=io.openlineage.spark.agent.OpenLineageSparkListener`
- **AND** the `--packages` list SHALL include `io.openlineage:openlineage-spark_2.12:1.24.2`

#### Scenario: listener absent by default
- **WHEN** `submit_job.sh` runs without `ENABLE_OPENLINEAGE`
- **THEN** the `spark-submit` command SHALL NOT reference OpenLineage in any `--conf` flag

### Requirement: column-documentation-coverage
Every column in the three ClickHouse CDC tables (`customers_cdc`, `products_cdc`, `orders_cdc`) SHALL carry a `COMMENT` clause explaining what the value represents and, for PII columns, the transformation that produced it. Each table SHALL also carry a table-level `COMMENT` naming its owner and its source.

#### Scenario: every column has a COMMENT
- **WHEN** `SHOW CREATE TABLE ecommerce_analytics.customers_cdc` (and products_cdc, orders_cdc) is inspected
- **THEN** every column SHALL have a non-empty `COMMENT '...'` clause

#### Scenario: PII columns explain their transformation
- **WHEN** the COMMENT for `customers_cdc.email` or `customers_cdc.name` is read
- **THEN** it SHALL reference the applicable governance requirement (`pii-hashing-customers-email` or `pii-tokenization-customers-name`)

#### Scenario: tables carry owner + source
- **WHEN** the table-level COMMENT for any CDC table is read
- **THEN** it SHALL name the owner (`data-platform`) and the source (the corresponding `postgres.public.*` table)

