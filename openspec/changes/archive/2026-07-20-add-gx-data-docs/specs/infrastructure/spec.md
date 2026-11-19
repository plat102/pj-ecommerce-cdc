## MODIFIED Requirements

### Requirement: per-service-targets
Each service group SHALL have dedicated `up-*`, `down-*`, `logs-*`, and `sh-*` Makefile targets allowing developers to operate individual services without affecting others. The governance catalog stack (OpenMetadata + MySQL + Elasticsearch) SHALL be operated via `up-governance` / `down-governance` / `logs-governance` targets and SHALL NOT be included in `make up` because of its memory footprint. The observability stack SHALL be operated via `up-observability` / `down-observability` / `logs-observability` / `status-observability` targets and SHALL be included in `make up` by default. DLQ topic setup SHALL additionally be operated via the standalone Makefile target `apply-dlq-topics`. The GX Data Docs static site SHALL be operated via `up-gx-docs` / `down-gx-docs` / `logs-gx-docs` targets and SHALL NOT be included in `make up` — it is a diagnostic tool reached for during incident review, and its opt-in stance keeps the default `make up` port surface small.

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

#### Scenario: gx-docs is opt-in
- **WHEN** `make up` completes
- **THEN** no `gx-data-docs-server` container SHALL be running

#### Scenario: gx-docs up target starts the sidecar
- **WHEN** `make up-gx-docs` is invoked with the shared network already in place
- **THEN** an `nginx:alpine` container named `gx-data-docs-server` SHALL start with port 8890 published to the host
