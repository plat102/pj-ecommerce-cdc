## MODIFIED Requirements

### Requirement: full-stack-startup
`make up` SHALL start all seven service groups (db, kafka, debezium, ui, spark, analytics, observability) using `docker-compose` with all seven compose files. After Kafka reports healthy AND before the Debezium PostgreSQL connector is applied, `make up` SHALL invoke `make apply-dlq-topics` to pre-create every DLQ topic with explicit retention config (see `dlq-topic-retention` in `error-handling`). Startup ordering SHALL rely on `depends_on: { condition: service_healthy }` where healthchecks exist, replacing time-based sleeps.

#### Scenario: full stack running after make up
- **WHEN** `make up` completes without error
- **THEN** all core services (postgres, kafka1, zookeeper, debezium, debezium-ui, redpanda-console, schema-registry, ed-pyspark-jupyter, clickhouse, grafana, cdc-testing-ui) AND all observability services (loki, alloy, prometheus, cadvisor, node-exporter, kafka-exporter, postgres-exporter) SHALL have status `running` in `make status`

#### Scenario: DLQ topics pre-created
- **WHEN** `make up` completes on a cold stack
- **THEN** `kafka-topics --list --bootstrap-server localhost:9092` SHALL include every DLQ topic (`debezium_connect_dlq`, `{customers,products,orders}_cdc_dlq`, `{customers,products,orders}_cdc_sink_dlq`) even though no bad record has yet been produced

#### Scenario: connector auto-applied after DLQ topics exist
- **WHEN** `make up` completes
- **THEN** `make check-connector` SHALL show connector `pg-connector-ecommerce` with status RUNNING
- **AND** the `debezium_connect_dlq` topic SHALL already exist on the broker at the moment the connector is registered

#### Scenario: health-gated startup
- **WHEN** `make up` is invoked cold (no containers running)
- **THEN** the `debezium` container SHALL wait for `kafka1` and `schema-registry` healthchecks to report `healthy` before starting (no more time-based sleep in the Makefile)

---

### Requirement: per-service-targets
Each service group SHALL have dedicated `up-*`, `down-*`, `logs-*`, and `sh-*` Makefile targets allowing developers to operate individual services without affecting others. The governance catalog stack (OpenMetadata + MySQL + Elasticsearch) SHALL be operated via `up-governance` / `down-governance` / `logs-governance` targets and SHALL NOT be included in `make up` because of its memory footprint. The observability stack SHALL be operated via `up-observability` / `down-observability` / `logs-observability` / `status-observability` targets and SHALL be included in `make up` by default. DLQ topic setup SHALL additionally be operated via the standalone Makefile target `apply-dlq-topics` (idempotent, safe to re-run) so operators can drift-correct or apply operator overrides without re-running the whole stack.

#### Scenario: start only db and kafka
- **WHEN** `make up-db` and `make up-kafka` are run without `make up`
- **THEN** only postgres, zookeeper, kafka1, redpanda-console, and schema-registry containers SHALL start

#### Scenario: shell access to postgres
- **WHEN** `make sh-pg` is executed with the db service running
- **THEN** a `psql` shell SHALL open connected to the `ecommerce` database as the configured user

#### Scenario: apply-dlq-topics is standalone
- **WHEN** the stack is already running and `make apply-dlq-topics` is invoked
- **THEN** the target SHALL exec into `kafka1` and run the DLQ topic setup script, without touching any other container
- **AND** re-running the target immediately SHALL succeed with no error (idempotent)
