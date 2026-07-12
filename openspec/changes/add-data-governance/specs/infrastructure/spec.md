## MODIFIED Requirements

> **Status:** Phase 3 added the `schema-registry` service to `docker-compose.kafka.yml`, and Phase 4 adds a new `docker-compose.governance.yml` (OpenMetadata + MySQL + Elasticsearch) with matching `up-governance` / `down-governance` / `logs-governance` targets. The governance compose is split from the main stack because it consumes ~4GB RAM and is not needed to run the CDC pipeline itself. On archive, these deltas merge into `openspec/specs/infrastructure/spec.md`.

### Requirement: per-service-targets
Each service group SHALL have dedicated `up-*`, `down-*`, `logs-*`, and `sh-*` Makefile targets allowing developers to operate individual services without affecting others. The governance catalog stack (OpenMetadata + MySQL + Elasticsearch) SHALL be operated via `up-governance` / `down-governance` / `logs-governance` targets and SHALL NOT be included in `make up` because of its memory footprint.

#### Scenario: start only db and kafka
- **WHEN** `make up-db` and `make up-kafka` are run without `make up`
- **THEN** only postgres, zookeeper, kafka1, redpanda-console, and schema-registry containers SHALL start (schema-registry is part of the kafka service group as of Phase 3)

#### Scenario: shell access to postgres
- **WHEN** `make sh-pg` is executed with the db service running
- **THEN** a `psql` shell SHALL open connected to the `ecommerce` database as the configured user

#### Scenario: governance stack starts independently
- **WHEN** `make up-governance` is run against a repo where `make up` is already running
- **THEN** OpenMetadata, its MySQL, and its Elasticsearch containers SHALL start alongside (attaching to the shared `ecommerce-network`), and the existing CDC containers SHALL be unaffected

#### Scenario: governance stack absent from make up
- **WHEN** `make up` is run
- **THEN** neither `openmetadata-server`, `openmetadata-mysql`, nor `openmetadata-elasticsearch` SHALL appear in the resulting container list
