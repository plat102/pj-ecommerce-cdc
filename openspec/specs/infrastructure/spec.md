## Purpose

Local Docker Compose orchestration for the full CDC stack, exposed through Makefile targets. Defines the `.env` location contract, the six-service-group layout, per-service lifecycle targets, the destructive vs preserving teardown distinction, and the in-container-DNS vs host-localhost hostname convention.
## Requirements
### Requirement: env-file-location
The environment file SHALL live at `infrastructure/docker/.env`. It MUST be created by copying `.env.example` before running any Makefile target. The Makefile SHALL NOT fall back to a default if `.env` is missing.

#### Scenario: make up without .env
- **WHEN** `make up` is executed without `infrastructure/docker/.env` existing
- **THEN** the Makefile SHALL fail with an error rather than using empty variable values

#### Scenario: env file populated from example
- **WHEN** the user runs `cp .env.example infrastructure/docker/.env`
- **THEN** all required variables (Postgres, Kafka, ClickHouse, Grafana, Spark image tags) SHALL be present with working defaults

---

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

### Requirement: connector-name
The Debezium PostgreSQL connector SHALL always be named `pg-connector-ecommerce`. All connector management targets (`make check-connector`, `make restart-connector`, `make delete-connector`) SHALL reference this fixed name.

#### Scenario: connector management targets use fixed name
- **WHEN** `make check-connector` is executed
- **THEN** the Kafka Connect REST API SHALL be queried at `/connectors/pg-connector-ecommerce/status`

---

### Requirement: spark-code-bind-mount
Spark job source code at `data-platform/streaming/spark/` SHALL be bind-mounted into the `ed-pyspark-jupyter` container at `/home/jupyter/src-streaming/spark/`. Code changes on the host SHALL take effect in the container without a Docker image rebuild.

#### Scenario: code change without rebuild
- **WHEN** a Python file in `data-platform/streaming/spark/src/` is edited on the host
- **THEN** running `make cdc-stop` followed by `make cdc-run-prod` SHALL execute the updated code without `docker build`

---

### Requirement: hostname-separation
Services running inside containers SHALL use Docker internal DNS names (`kafka1`, `clickhouse`, `postgres`) for inter-service communication. Host-side tools (Streamlit local mode, `scripts/run_cdc.sh`, CLI tools) SHALL use `localhost` with the published ports from `.env`.

#### Scenario: spark reads kafka by internal hostname
- **WHEN** a Spark job reads from Kafka
- **THEN** the bootstrap servers SHALL resolve to `kafka1:9092` (internal) not `localhost:9093`

#### Scenario: host-side script connects to postgres
- **WHEN** `make demo-data` is run from the host
- **THEN** the Streamlit demo_data.py script SHALL connect to `localhost:5432`

### Requirement: python-environment-convention
The canonical Python virtual environment for local development SHALL be `.venv/` at the repo root, managed by uv. uv's default in-project venv behavior SHALL be relied on (no repo-scoped config file is required). `setup_venv.sh` and any `venv/` directory SHALL NOT exist as canonical entry points — `make uv-sync` is the sole setup command.

#### Scenario: fresh clone installs via uv
- **WHEN** a developer clones the repo and runs `make uv-sync`
- **THEN** a `.venv/` directory SHALL be created at the repo root with all main and dev dependencies from `pyproject.toml` installed, resolved against `uv.lock`

#### Scenario: no legacy venv script
- **WHEN** the repo is inspected for setup scripts
- **THEN** `setup_venv.sh` SHALL NOT exist and no Makefile target SHALL reference `venv/` (only `.venv/`)

### Requirement: makefile-uv-targets
The Makefile SHALL provide `uv-sync`, `uv-shell`, `uv-clean`, and `test` targets. The retired venv-family targets (`setup-venv`, `activate-venv`, `clean-venv`, `check-venv`, `install-deps`, `setup-python`) SHALL NOT reappear.

#### Scenario: make test runs pytest via uv
- **WHEN** `make test` is run
- **THEN** the target SHALL execute `uv run pytest` and exit 0 when tests pass (or when zero tests are collected)

#### Scenario: retired targets absent
- **WHEN** `make help` output is inspected
- **THEN** none of `setup-venv`, `activate-venv`, `clean-venv`, `check-venv`, `install-deps`, `setup-python` SHALL appear

### Requirement: streamlit-image-python-source-of-truth
The Streamlit application container defined by `infrastructure/docker/streamlit/Dockerfile` SHALL install Python dependencies from `pyproject.toml` and `uv.lock` via a multi-stage build in which stage 1 runs `uv export --no-hashes --no-dev -o requirements.txt` and stage 2 runs `pip install -r requirements.txt` on the exported file. It SHALL NOT reference a repo-tracked `requirements.txt`.

#### Scenario: streamlit build uses uv export
- **WHEN** the Streamlit Docker image is rebuilt
- **THEN** the build steps SHALL read dependencies from `pyproject.toml` and `uv.lock`, generating `requirements.txt` ephemerally at build time; no `requirements.txt` file SHALL be committed to the repo

