## Purpose

End-to-end change data capture from PostgreSQL through Debezium and Kafka into PySpark Structured Streaming jobs that land deduplicated rows in ClickHouse. Covers connector configuration, Kafka topic conventions, and the Spark job model (base class, debug vs production sinks, decimal decoding).
## Requirements
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

### Requirement: captured-tables
The Debezium connector SHALL capture row-level changes (INSERT, UPDATE, DELETE) from exactly three PostgreSQL tables: `public.customers`, `public.products`, and `public.orders`.

#### Scenario: insert captured
- **WHEN** a new row is inserted into any of the three tables
- **THEN** a Debezium message with `op = "c"` SHALL appear on the corresponding Kafka topic within 5 seconds

#### Scenario: update captured
- **WHEN** an existing row is updated
- **THEN** a Debezium message with `op = "u"` SHALL appear on the corresponding Kafka topic, containing both `before` and `after` payloads

#### Scenario: delete captured
- **WHEN** a row is deleted
- **THEN** a Debezium message with `op = "d"` SHALL appear on the corresponding Kafka topic, with `after = null` and `before` containing the deleted row's values

---

### Requirement: kafka-topic-naming
Debezium SHALL publish CDC events to topics named `pg.public.{table}` where `{table}` is one of `customers`, `products`, or `orders`.

#### Scenario: topic exists after connector starts
- **WHEN** the connector enters RUNNING state
- **THEN** topics `pg.public.customers`, `pg.public.products`, and `pg.public.orders` SHALL exist in Kafka (visible in Redpanda Console at http://localhost:8080)

---

### Requirement: spark-job-startup
Each Spark CDC job SHALL be submitted via `apps/run_cdc_job.py --job-type {customers|products|orders}` inside the `ed-pyspark-jupyter` container. The Makefile targets (`make cdc-run`, `make cdc-run-products`, `make cdc-run-orders`) SHALL invoke `scripts/run_cdc.sh` which delegates to `data-platform/streaming/spark/scripts/submit_job.sh`.

#### Scenario: starting a job via make
- **WHEN** `make cdc-run-prod` is executed on the host
- **THEN** a `spark-submit` process SHALL start inside `ed-pyspark-jupyter` reading from `pg.public.customers`

#### Scenario: Spark container not running
- **WHEN** `scripts/run_cdc.sh` is called and `ed-pyspark-jupyter` is not running
- **THEN** the script SHALL start the Spark container via `docker-compose up -d` before submitting the job

---

### Requirement: kafka-read-offset
Spark jobs SHALL subscribe to Kafka topics with `startingOffsets=latest`, consuming only new messages produced after the job starts.

#### Scenario: job restart does not replay past events
- **WHEN** a Spark job is stopped and restarted
- **THEN** events produced while the job was stopped SHALL NOT be reprocessed

---

### Requirement: debug-mode
When launched with `--debug`, a Spark job SHALL write transformed rows to the console sink (`format("console")`) and SHALL NOT write to ClickHouse or maintain a checkpoint.

#### Scenario: debug output visible in logs
- **WHEN** `make cdc-run` (debug mode) is running and a Postgres row is inserted
- **THEN** the transformed row SHALL appear in `docker logs ed-pyspark-jupyter` within one trigger interval (default 10 seconds)

#### Scenario: no ClickHouse write in debug mode
- **WHEN** a job runs in debug mode
- **THEN** no data SHALL be written to ClickHouse and no checkpoint directory SHALL be created

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

### Requirement: decimal-decoding
Any Spark transformer handling a PostgreSQL `DECIMAL` or `NUMERIC` column SHALL apply `decode_decimal_udf` (defined in `src/utils/udfs.py`) to convert Debezium's base64-encoded byte representation to a Spark `DecimalType`.

#### Scenario: product price decoded correctly
- **WHEN** a product with price `19.99` is inserted and the products CDC job is running in production mode
- **THEN** the `price` column in `products_cdc` ClickHouse table SHALL contain `19.99` as a Decimal value

#### Scenario: new decimal column requires UDF
- **WHEN** a new `DECIMAL` column is added to a Postgres table and its Spark transformer does not call `decode_decimal_udf`
- **THEN** the Spark job SHALL fail with a type mismatch error or silently produce null/corrupt values

---

### Requirement: base-cdc-job-pattern
New per-table CDC jobs SHALL be implemented as subclasses of `BaseCDCJob` (`data-platform/streaming/spark/src/jobs/base_cdc_job.py`), implementing only the `process()` method to return the transformed DataFrame. Subclasses SHALL NOT re-implement Spark session creation, Kafka reader setup, ClickHouse writer setup, or checkpoint management — these are the base class's responsibility.

#### Scenario: new table follows the abstract pattern
- **WHEN** a new Postgres table is added to CDC capture and its Spark job is created
- **THEN** the job file SHALL define a single class extending `BaseCDCJob` with only `__init__` and `process()`
- **AND** the dispatcher in `apps/run_cdc_job.py` SHALL route to it via a new `--job-type` value

#### Scenario: legacy customers job
- **WHEN** the `customers` job is examined (currently uses the legacy `CDCProcessor` monolith)
- **THEN** it is acknowledged as the one pre-existing exception to this requirement, tracked for migration to `BaseCDCJob`
- **AND** any *modification* to the customers job SHALL be accompanied by a change proposal migrating it to `BaseCDCJob`, not extending the legacy pattern

