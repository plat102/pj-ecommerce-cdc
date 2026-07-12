## MODIFIED Requirements

> **Status:** Phase 3 introduces two behavior-observable changes to the `cdc-pipeline` capability: Debezium's converter switches from JSON to Avro (with Schema Registry), and the ClickHouse writer optionally gates each micro-batch through a Great Expectations suite before writing. Task 3.8 in tasks.md also mentions an OpenLineage listener addition — that lands in Phase 4, not here.

### Requirement: debezium-connector-registration
The Debezium PostgreSQL connector SHALL be registered via POST to the Kafka Connect REST API using the configuration in `data-platform/cdc/connectors/register-pg.json`. The connector name SHALL be `pg-connector-ecommerce`. The connector configuration SHALL use `io.apicurio.registry.utils.converter.AvroConverter` for both key and value, with `apicurio.registry.url = http://schema-registry:8080/apis/registry/v2`. The Debezium container SHALL run with `ENABLE_APICURIO_CONVERTERS=true` so the bundled Apicurio converter is on the plugin path.

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

---

### Requirement: production-mode
When launched without `--debug`, a Spark job SHALL write transformed DataFrames to ClickHouse via `foreachBatch` using the JDBC ClickHouse driver. A checkpoint SHALL be maintained at `{CHECKPOINT_LOCATION}/{table_name}/v1` (see `checkpoint-versioned-paths`). When `ENABLE_GX_GATE=1`, the `foreachBatch` function SHALL wrap the ClickHouse writer with a Great Expectations gate that routes invalid rows to `{table}_dlq` before delegating valid rows to the ClickHouse write (see `gx-batch-validation` and `dlq-on-validation-failure`).

#### Scenario: data reaches ClickHouse
- **WHEN** a Postgres row is inserted and all three prod-mode jobs are running
- **THEN** the row SHALL be queryable in the corresponding ClickHouse `*_cdc` table within 15 seconds

#### Scenario: checkpoint preserved across restart
- **WHEN** a prod-mode job is stopped cleanly and restarted
- **THEN** the job SHALL resume from the last committed Kafka offset stored in the checkpoint

#### Scenario: GX gate disabled by default
- **WHEN** a Spark CDC job starts without `ENABLE_GX_GATE` set
- **THEN** `create_batch_writer_function` SHALL return the unwrapped writer and no `_dlq` topic writes SHALL occur
