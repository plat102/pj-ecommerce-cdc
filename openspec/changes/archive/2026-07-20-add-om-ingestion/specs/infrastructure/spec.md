## MODIFIED Requirements

### Requirement: per-service-targets
Each service group SHALL have dedicated `up-*`, `down-*`, `logs-*`, and `sh-*` Makefile targets allowing developers to operate individual services without affecting others. The governance catalog stack (OpenMetadata + MySQL + Elasticsearch) SHALL be operated via `up-governance` / `down-governance` / `logs-governance` targets and SHALL NOT be included in `make up` because of its memory footprint. The observability stack SHALL be operated via `up-observability` / `down-observability` / `logs-observability` / `status-observability` targets and SHALL be included in `make up` by default. DLQ topic setup SHALL additionally be operated via the standalone Makefile target `apply-dlq-topics`. The GX Data Docs static site SHALL be operated via `up-gx-docs` / `down-gx-docs` / `logs-gx-docs` targets and SHALL NOT be included in `make up`. OpenMetadata catalog ingestion SHALL be operated via the standalone Makefile targets `ingest-pg`, `ingest-kafka`, `ingest-clickhouse`, `ingest-all` (runs the three sequentially with fail-fast semantics), and `ingest-status` (queries the OM REST API for a summary). These `ingest-*` targets SHALL NOT be included in `make up` or `make up-governance` — ingestion cadence is operator-controlled.

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

#### Scenario: ingest targets are on-demand
- **WHEN** `make up` and `make up-governance` complete
- **THEN** no ingestion container SHALL be running AND OpenMetadata SHALL remain in whatever ingested state it was previously left in (populated or empty)

#### Scenario: ingest-all is a sequential composite
- **WHEN** `make ingest-all` is invoked
- **THEN** it SHALL run `make ingest-pg`, then `make ingest-kafka`, then `make ingest-clickhouse`, in that order, aborting on the first failure
