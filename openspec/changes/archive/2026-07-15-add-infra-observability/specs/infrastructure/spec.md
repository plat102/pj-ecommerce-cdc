## MODIFIED Requirements

> **Status:** Phase 1 adds a new `docker-compose.observability.yml` file (loki + alloy + prometheus + cadvisor + node-exporter), Phase 2 extends it with exporters (kafka + postgres), and Phase 3 adds `restart:` policies and `healthcheck:` blocks to every service in the stack. The observability compose file joins `COMPOSE_ALL` so `make up` includes it by default (~700MB budget, under 1GB). This differs from the governance stack which stays opt-in at ~4GB.

### Requirement: full-stack-startup
`make up` SHALL start all seven service groups (db, kafka, debezium, ui, spark, analytics, observability) using `docker-compose` with all seven compose files and SHALL automatically apply the Debezium PostgreSQL connector after services start. Startup ordering SHALL rely on `depends_on: { condition: service_healthy }` where healthchecks exist, replacing time-based sleeps.

#### Scenario: full stack running after make up
- **WHEN** `make up` completes without error
- **THEN** all core services (postgres, kafka1, zookeeper, debezium, debezium-ui, redpanda-console, schema-registry, ed-pyspark-jupyter, clickhouse, grafana, cdc-testing-ui) AND all observability services (loki, alloy, prometheus, cadvisor, node-exporter, kafka-exporter, postgres-exporter) SHALL have status `running` in `make status`

#### Scenario: connector auto-applied
- **WHEN** `make up` completes
- **THEN** `make check-connector` SHALL show connector `pg-connector-ecommerce` with status RUNNING

#### Scenario: health-gated startup
- **WHEN** `make up` is invoked cold (no containers running)
- **THEN** the `debezium` container SHALL wait for `kafka1` and `schema-registry` healthchecks to report `healthy` before starting (no more time-based sleep in the Makefile)

---

### Requirement: volume-preservation
`make stop` SHALL stop all containers while preserving Docker volumes (Postgres data, Kafka offsets, ClickHouse data, Spark checkpoints, Loki chunks, Prometheus TSDB). `make start` SHALL restart stopped containers restoring all persisted state.

#### Scenario: stop and start cycle preserves observability data
- **WHEN** `make stop` is run followed by `make start`
- **THEN** Postgres data, Kafka topic offsets, ClickHouse tables, Spark checkpoints, Loki `loki_data` volume, and Prometheus `prometheus_data` volume SHALL all be intact

---

### Requirement: destructive-teardown
`make down` SHALL stop and remove all containers AND all associated Docker volumes, including the observability volumes (`loki_data`, `prometheus_data`). This operation is destructive and irreversible.

#### Scenario: data lost after make down
- **WHEN** `make down` is executed
- **THEN** all volumes SHALL be removed and subsequent `make up` SHALL start with empty Postgres, Kafka, ClickHouse, Loki, and Prometheus state

---

### Requirement: per-service-targets
Each service group SHALL have dedicated `up-*`, `down-*`, `logs-*`, and `sh-*` Makefile targets allowing developers to operate individual services without affecting others. The governance catalog stack (OpenMetadata + MySQL + Elasticsearch) SHALL be operated via `up-governance` / `down-governance` / `logs-governance` targets and SHALL NOT be included in `make up` because of its memory footprint. The observability stack (loki + alloy + prometheus + cadvisor + node-exporter + exporters) SHALL be operated via `up-observability` / `down-observability` / `logs-observability` / `status-observability` targets and SHALL be included in `make up` by default because its footprint (~700MB) fits within the local-dev budget and its value comes precisely from being present during normal operation.

#### Scenario: start only db and kafka
- **WHEN** `make up-db` and `make up-kafka` are run without `make up`
- **THEN** only postgres, zookeeper, kafka1, redpanda-console, and schema-registry containers SHALL start

#### Scenario: shell access to postgres
- **WHEN** `make sh-pg` is executed with the db service running
- **THEN** a `psql` shell SHALL open connected to the `ecommerce` database as the configured user

#### Scenario: governance stack starts independently
- **WHEN** `make up-governance` is run against a repo where `make up` is already running
- **THEN** OpenMetadata, its MySQL, and its Elasticsearch containers SHALL start alongside (attaching to the shared `ecommerce-network`), and the existing CDC containers SHALL be unaffected

#### Scenario: governance stack absent from make up
- **WHEN** `make up` is run
- **THEN** neither `openmetadata-server`, `openmetadata-mysql`, nor `openmetadata-elasticsearch` SHALL appear in the resulting container list

#### Scenario: observability stack included in make up
- **WHEN** `make up` is run
- **THEN** loki, alloy, prometheus, cadvisor, node-exporter, kafka-exporter, and postgres-exporter SHALL all appear in `make status` alongside the core CDC containers
