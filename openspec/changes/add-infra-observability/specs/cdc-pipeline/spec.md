## MODIFIED Requirements

> **Status:** Phase 2 of `add-infra-observability` extends two CDC-pipeline services to expose metrics: Spark enables its built-in Prometheus servlet via `submit_job.sh` configs, and Debezium's Kafka Connect JVM runs a jmx-exporter javaagent sidecar. Neither adds a new container.

### Requirement: debezium-connector-registration
The Debezium PostgreSQL connector SHALL be registered via POST to the Kafka Connect REST API using the configuration in `data-platform/cdc/connectors/register-pg.json`. The connector name SHALL be `pg-connector-ecommerce`. The connector configuration SHALL use `io.apicurio.registry.utils.converter.AvroConverter` for both key and value, with `apicurio.registry.url = http://schema-registry:8080/apis/registry/v2`. The Debezium container SHALL run with `ENABLE_APICURIO_CONVERTERS=true` so the bundled Apicurio converter is on the plugin path. The Debezium container SHALL additionally run with the jmx-exporter javaagent enabled via `KAFKA_OPTS=-javaagent:/opt/jmx-exporter/jmx_prometheus_javaagent.jar=5556:/opt/jmx-exporter/debezium-jmx.yml` so connector metrics are exposed at `http://debezium:5556/metrics` for Prometheus scraping.

#### Scenario: successful connector registration
- **WHEN** the stack is running and `make apply-pg-connector` is executed
- **THEN** the connector `pg-connector-ecommerce` SHALL appear in `make list-connectors` with status RUNNING

#### Scenario: connector already exists
- **WHEN** `make apply-pg-connector` is run while the connector already exists
- **THEN** the Kafka Connect API SHALL return a 409 conflict; existing connector state SHALL be unchanged

#### Scenario: Apicurio Avro converter configured
- **WHEN** `data-platform/cdc/connectors/register-pg.json` is inspected
- **THEN** `config.key.converter` and `config.value.converter` SHALL both be `io.apicurio.registry.utils.converter.AvroConverter`
- **AND** `config.key.converter.apicurio.registry.url` and `config.value.converter.apicurio.registry.url` SHALL both be `http://schema-registry:8080/apis/registry/v2`

#### Scenario: jmx-exporter agent metrics reachable
- **WHEN** the Debezium container has been running for at least 30 seconds
- **THEN** `curl http://localhost:5556/metrics` SHALL return a Prometheus-formatted response containing at minimum `kafka_connect_connector_status` and `debezium_metrics_MilliSecondsSinceLastEvent`

---

### Requirement: production-mode
When launched without `--debug`, a Spark job SHALL write transformed DataFrames to ClickHouse via `foreachBatch` using the JDBC ClickHouse driver. A checkpoint SHALL be maintained at `{CHECKPOINT_LOCATION}/{table_name}/v1` (see `checkpoint-versioned-paths`). When `ENABLE_GX_GATE=1`, the `foreachBatch` function SHALL wrap the ClickHouse writer with a Great Expectations gate that routes invalid rows to `{table}_dlq` before delegating valid rows to the ClickHouse write (see `gx-batch-validation` and `dlq-on-validation-failure`). The Spark job SHALL enable the built-in Prometheus servlet via `--conf spark.ui.prometheus.enabled=true --conf spark.metrics.conf=/home/jupyter/spark-conf/metrics.properties` so streaming and executor metrics are exposed at `http://ed-pyspark-jupyter:4040/metrics/prometheus` for Prometheus scraping.

#### Scenario: data reaches ClickHouse
- **WHEN** a Postgres row is inserted and all three prod-mode jobs are running
- **THEN** the row SHALL be queryable in the corresponding ClickHouse `*_cdc` table within 15 seconds

#### Scenario: checkpoint preserved across restart
- **WHEN** a prod-mode job is stopped cleanly and restarted
- **THEN** the job SHALL resume from the last committed Kafka offset stored in the checkpoint

#### Scenario: GX gate disabled by default
- **WHEN** a Spark CDC job starts without `ENABLE_GX_GATE` set
- **THEN** `create_batch_writer_function` SHALL return the unwrapped writer and no `_dlq` topic writes SHALL occur

#### Scenario: Prometheus servlet exposes streaming metrics
- **WHEN** a Spark CDC job has been running in prod mode for at least 30 seconds
- **THEN** `curl http://localhost:4040/metrics/prometheus` SHALL return a Prometheus-formatted response containing at minimum `spark_streaming_query_lastCompletedBatchId` and `spark_streaming_query_inputRate`
