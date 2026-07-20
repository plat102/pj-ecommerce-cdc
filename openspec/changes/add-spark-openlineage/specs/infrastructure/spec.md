## MODIFIED Requirements

### Requirement: per-service-targets
Each service group SHALL have dedicated `up-*`, `down-*`, `logs-*`, and `sh-*` Makefile targets allowing developers to operate individual services without affecting others. The governance catalog stack (OpenMetadata + MySQL + Elasticsearch) SHALL be operated via `up-governance` / `down-governance` / `logs-governance` targets and SHALL NOT be included in `make up` because of its memory footprint. The observability stack SHALL be operated via `up-observability` / `down-observability` / `logs-observability` / `status-observability` targets and SHALL be included in `make up` by default. DLQ topic setup SHALL additionally be operated via the standalone Makefile target `apply-dlq-topics`. The GX Data Docs static site SHALL be operated via `up-gx-docs` / `down-gx-docs` / `logs-gx-docs` targets and SHALL NOT be included in `make up`. OpenMetadata catalog ingestion SHALL be operated via `ingest-pg`, `ingest-kafka`, `ingest-clickhouse`, `ingest-all`, and `ingest-status` targets (from `openmetadata-ingestion` capability). OpenMetadata pipeline-service bootstrap for the Spark job SHALL be operated via the standalone Makefile target `om-register-spark` — idempotent, prerequisite for `openlineage-spark-lineage-edges` to render.

#### Scenario: start only db and kafka
- **WHEN** `make up-db` and `make up-kafka` are run without `make up`
- **THEN** only postgres, zookeeper, kafka1, redpanda-console, and schema-registry containers SHALL start

#### Scenario: om-register-spark is standalone and idempotent
- **WHEN** `make om-register-spark` is invoked against a healthy OpenMetadata stack
- **THEN** the target SHALL create OR update the `ecommerce-cdc-spark` pipeline service in OM without touching any other container
- **AND** re-running the target immediately SHALL succeed with no error
