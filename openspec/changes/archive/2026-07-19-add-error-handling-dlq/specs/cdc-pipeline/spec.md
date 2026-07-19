## MODIFIED Requirements

> **Status:** Two touch points in `cdc-pipeline` gain DLQ semantics: the Debezium connector JSON gains Kafka Connect's `errors.*` block (Phase 1); the Spark production-mode writer wraps `foreachBatch` with `with_sink_dlq` when `ENABLE_SINK_DLQ=1` (Phase 2).

### Requirement: debezium-connector-registration
The Debezium PostgreSQL connector SHALL be registered via POST to the Kafka Connect REST API using the configuration in `data-platform/cdc/connectors/register-pg.json`. The connector name SHALL be `pg-connector-ecommerce`. The connector configuration SHALL use `io.apicurio.registry.utils.converter.AvroConverter` for both key and value, with `apicurio.registry.url = http://schema-registry:8080/apis/registry/v2` and `id-handler=io.apicurio.registry.serde.Legacy4ByteIdHandler` for Confluent-compatible wire format. The Debezium container SHALL run with `ENABLE_APICURIO_CONVERTERS=true` and with the jmx-exporter javaagent enabled via `KAFKA_OPTS`. The connector configuration SHALL additionally declare Kafka Connect's error-handling block: `errors.tolerance=all`, `errors.deadletterqueue.topic.name=debezium_connect_dlq`, `errors.deadletterqueue.context.headers.enable=true`, `errors.deadletterqueue.topic.replication.factor=1`, `errors.log.enable=true`, `errors.log.include.messages=true`.

#### Scenario: successful connector registration
- **WHEN** the stack is running and `make apply-pg-connector` is executed
- **THEN** the connector `pg-connector-ecommerce` SHALL appear in `make list-connectors` with status RUNNING

#### Scenario: connector already exists
- **WHEN** `make apply-pg-connector` is run while the connector already exists
- **THEN** the Kafka Connect API SHALL return a 409 conflict; existing connector state SHALL be unchanged

#### Scenario: error-handling block configured
- **WHEN** `data-platform/cdc/connectors/register-pg.json` is inspected
- **THEN** the six `errors.*` properties listed above SHALL be present in the `config` object

#### Scenario: bad record routed to Kafka Connect DLQ
- **WHEN** a record entering the Debezium connector triggers a converter or transform exception
- **THEN** the connector task SHALL remain in RUNNING state
- **AND** the failing record SHALL appear on the `debezium_connect_dlq` topic with headers `__connect.errors.topic`, `__connect.errors.partition`, `__connect.errors.offset`, `__connect.errors.exception.class.name`, and `__connect.errors.exception.stacktrace`

---

### Requirement: production-mode
When launched without `--debug`, a Spark job SHALL write transformed DataFrames to ClickHouse via `foreachBatch` using the JDBC ClickHouse driver. A checkpoint SHALL be maintained at `{CHECKPOINT_LOCATION}/{table_name}/v1`. When `ENABLE_GX_GATE=1`, the `foreachBatch` function SHALL wrap the ClickHouse writer with a Great Expectations gate that routes invalid rows to `{table}_dlq`. When `ENABLE_SINK_DLQ=1`, the `foreachBatch` function SHALL additionally wrap the writer with a sink DLQ that catches exceptions from the ClickHouse JDBC write and routes the failing batch's rows to `{table}_sink_dlq`. When both flags are set, composition order SHALL be `with_gx_gate(with_sink_dlq(inner_writer, table), table)` so GX filters invalid rows before the sink layer sees them.

#### Scenario: data reaches ClickHouse
- **WHEN** a Postgres row is inserted and all three prod-mode jobs are running
- **THEN** the row SHALL be queryable in the corresponding ClickHouse `*_cdc` table within 15 seconds

#### Scenario: sink DLQ catches ClickHouse write failure
- **WHEN** a Spark CDC job is running with `ENABLE_SINK_DLQ=1` and the ClickHouse JDBC writer raises an exception mid-batch
- **THEN** every row of the failing batch SHALL be written to `{table}_sink_dlq` with `_error_stage="spark_sink"`, `_error_class`, and `_error_message` fields alongside the original row JSON
- **AND** the streaming query SHALL continue processing subsequent batches (the exception SHALL NOT propagate past the wrapper)

#### Scenario: both gates compose without double-DLQ
- **WHEN** `ENABLE_GX_GATE=1` and `ENABLE_SINK_DLQ=1` are both set and a row that fails a GX expectation reaches the writer
- **THEN** the row SHALL land in `{table}_dlq` (from the GX gate) and SHALL NOT appear in `{table}_sink_dlq` — the GX gate filters before the sink layer receives it
