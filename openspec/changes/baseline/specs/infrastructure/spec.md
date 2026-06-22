## ADDED Requirements

### Requirement: env-file-location
The environment file SHALL live at `infrastructure/docker/.env`. It MUST be created by copying `.env.example` before running any Makefile target. The Makefile SHALL NOT fall back to a default if `.env` is missing.

#### Scenario: make up without .env
- **WHEN** `make up` is executed without `infrastructure/docker/.env` existing
- **THEN** the Makefile SHALL fail with an error rather than using empty variable values

#### Scenario: env file populated from example
- **WHEN** the user runs `cp .env.example infrastructure/docker/.env`
- **THEN** all required variables (Postgres, Kafka, ClickHouse, Grafana, Spark image tags) SHALL be present with working defaults

### Requirement: full-stack-startup
`make up` SHALL start all six service groups (db, kafka, debezium, ui, spark, analytics) using `docker-compose` with all six compose files and SHALL automatically apply the Debezium PostgreSQL connector after services start.

#### Scenario: full stack running after make up
- **WHEN** `make up` completes without error
- **THEN** all services (postgres, kafka1, zookeeper, debezium, debezium-ui, ed-pyspark-jupyter, clickhouse, grafana, cdc-testing-ui) SHALL have status `running` in `make status`

#### Scenario: connector auto-applied
- **WHEN** `make up` completes
- **THEN** `make check-connector` SHALL show connector `pg-connector-ecommerce` with status RUNNING

### Requirement: volume-preservation
`make stop` SHALL stop all containers while preserving Docker volumes (Postgres data, Kafka offsets, ClickHouse data, Spark checkpoints). `make start` SHALL restart stopped containers restoring all persisted state.

#### Scenario: stop and start cycle
- **WHEN** `make stop` is run followed by `make start`
- **THEN** Postgres data, Kafka topic offsets, ClickHouse tables, and Spark checkpoints SHALL all be intact

### Requirement: destructive-teardown
`make down` SHALL stop and remove all containers AND all associated Docker volumes. This operation is destructive and irreversible.

#### Scenario: data lost after make down
- **WHEN** `make down` is executed
- **THEN** all volumes SHALL be removed and subsequent `make up` SHALL start with empty Postgres, Kafka, and ClickHouse state

### Requirement: per-service-targets
Each service group SHALL have dedicated `up-*`, `down-*`, `logs-*`, and `sh-*` Makefile targets allowing developers to operate individual services without affecting others.

#### Scenario: start only db and kafka
- **WHEN** `make up-db` and `make up-kafka` are run without `make up`
- **THEN** only postgres, zookeeper, kafka1, and redpanda-console containers SHALL start

#### Scenario: shell access to postgres
- **WHEN** `make sh-pg` is executed with the db service running
- **THEN** a `psql` shell SHALL open connected to the `ecommerce` database as the configured user

### Requirement: connector-name
The Debezium PostgreSQL connector SHALL always be named `pg-connector-ecommerce`. All connector management targets (`make check-connector`, `make restart-connector`, `make delete-connector`) SHALL reference this fixed name.

#### Scenario: connector management targets use fixed name
- **WHEN** `make check-connector` is executed
- **THEN** the Kafka Connect REST API SHALL be queried at `/connectors/pg-connector-ecommerce/status`

### Requirement: spark-code-bind-mount
Spark job source code at `data-platform/streaming/spark/` SHALL be bind-mounted into the `ed-pyspark-jupyter` container at `/home/jupyter/src-streaming/spark/`. Code changes on the host SHALL take effect in the container without a Docker image rebuild.

#### Scenario: code change without rebuild
- **WHEN** a Python file in `data-platform/streaming/spark/src/` is edited on the host
- **THEN** running `make cdc-stop` followed by `make cdc-run-prod` SHALL execute the updated code without `docker build`

### Requirement: hostname-separation
Services running inside containers SHALL use Docker internal DNS names (`kafka1`, `clickhouse`, `postgres`) for inter-service communication. Host-side tools (Streamlit local mode, `scripts/run_cdc.sh`, CLI tools) SHALL use `localhost` with the published ports from `.env`.

#### Scenario: spark reads kafka by internal hostname
- **WHEN** a Spark job reads from Kafka
- **THEN** the bootstrap servers SHALL resolve to `kafka1:9092` (internal) not `localhost:9093`

#### Scenario: host-side script connects to postgres
- **WHEN** `make demo-data` is run from the host
- **THEN** the Streamlit demo_data.py script SHALL connect to `localhost:5432`
