## MODIFIED Requirements

### Requirement: openlineage-spark-emission
When `ENABLE_OPENLINEAGE=1` is set at Spark job submission time, `data-platform/streaming/spark/scripts/submit_job.sh` SHALL wire the OpenLineage Spark listener into `spark-submit` and emit lineage events to OpenMetadata's OpenLineage endpoint at `http://openmetadata-server:8585/api/v1/openlineage` (or the version-appropriate path verified during implementation). The `ENABLE_OPENLINEAGE` flag SHALL be `.env`-driven — declared as a placeholder in `.env.example` and passed through to the Spark container via `docker-compose.spark.yml`'s `environment:` block — so operators toggle it once in `.env` and restart the Spark container, mirroring the `ENABLE_GX_DATA_DOCS` pattern from the `data-quality-reporting` capability. The listener SHALL be off by default so dev environments without a lineage collector are unaffected. When the listener fails to reach the OM endpoint (5xx, timeout, DNS resolution failure), the Spark job SHALL continue processing without error — lineage is best-effort observability, never a gate on the pipeline.

#### Scenario: listener wired when enabled
- **WHEN** `submit_job.sh` runs with `ENABLE_OPENLINEAGE=1`
- **THEN** the resulting `spark-submit` command SHALL include `--conf spark.extraListeners=io.openlineage.spark.agent.OpenLineageSparkListener`
- **AND** the `--packages` list SHALL include `io.openlineage:openlineage-spark_2.12:1.24.2`

#### Scenario: listener absent by default
- **WHEN** `submit_job.sh` runs without `ENABLE_OPENLINEAGE`
- **THEN** the `spark-submit` command SHALL NOT reference OpenLineage in any `--conf` flag

#### Scenario: env flag propagates through compose
- **WHEN** `.env` sets `ENABLE_OPENLINEAGE=1` and the Spark container is recreated via `docker-compose up -d --force-recreate ed-pyspark-jupyter`
- **THEN** `docker exec ed-pyspark-jupyter env | grep ENABLE_OPENLINEAGE` SHALL print `ENABLE_OPENLINEAGE=1`

#### Scenario: OM downtime does not fail Spark
- **WHEN** the Spark job runs with `ENABLE_OPENLINEAGE=1` and the `openmetadata-server` container is stopped
- **THEN** the Spark job SHALL continue processing micro-batches without error, and dropped lineage events SHALL be logged at WARN level (not raised)

### Requirement: openlineage-spark-service-registration
The Spark job SHALL be registered in OpenMetadata as a pipeline service named `ecommerce-cdc-spark` (matching the default `spark.openlineage.namespace` value in `submit_job.sh`) before OpenLineage events can bind to a service entity. Registration SHALL be performed by an idempotent Makefile target `om-register-spark` that POSTs / PUTs to `http://localhost:8585/api/v1/services/pipelineServices` with `serviceType: Spark`. Re-invocation SHALL succeed without error and SHALL update rather than duplicate.

#### Scenario: registration creates the service
- **WHEN** `make om-register-spark` runs against a healthy OpenMetadata stack that does not already have the service
- **THEN** an entry named `ecommerce-cdc-spark` with `serviceType: Spark` SHALL exist at `http://localhost:8585/api/v1/services/pipelineServices/name/ecommerce-cdc-spark`

#### Scenario: re-registration is idempotent
- **WHEN** `make om-register-spark` is invoked twice in succession
- **THEN** the second invocation SHALL succeed with no error AND SHALL NOT create a duplicate service

### Requirement: openlineage-spark-lineage-edges
When a Spark CDC job runs with `ENABLE_OPENLINEAGE=1` and produces micro-batches, OpenMetadata's Lineage tab for the `ecommerce-cdc-spark` pipeline service SHALL show:
- an inbound edge from the Kafka topic ingested by the job (e.g., `pg.public.products` for the products CDC job), and
- an outbound edge to the ClickHouse table written by the job (e.g., `ecommerce_analytics.products_cdc`).

Both edges depend on the corresponding source datasets existing in OpenMetadata — that is, `ecommerce-kafka` and `ecommerce-clickhouse` services SHALL have been previously ingested via the `openmetadata-ingestion` capability. Without those services, OM SHALL still receive OpenLineage events but SHALL NOT render bound edges.

#### Scenario: lineage edges visible after first batch
- **GIVEN** `ecommerce-kafka` and `ecommerce-clickhouse` services are ingested in OpenMetadata
- **AND** `make om-register-spark` has succeeded
- **AND** the Spark products CDC job is running with `ENABLE_OPENLINEAGE=1`
- **WHEN** a Postgres row is inserted and a micro-batch commits
- **THEN** within 30 seconds, the Lineage tab for `ecommerce-cdc-spark` in OpenMetadata SHALL show an edge from `pg.public.products` (in `ecommerce-kafka`) to `ecommerce_analytics.products_cdc` (in `ecommerce-clickhouse`)

#### Scenario: no target service yields no bound edges
- **GIVEN** `ecommerce-kafka` service has NOT been ingested in OpenMetadata
- **WHEN** the Spark job runs with `ENABLE_OPENLINEAGE=1` and processes a batch
- **THEN** OpenMetadata SHALL accept the OpenLineage POSTs without error AND SHALL NOT show bound edges in the Lineage tab (the events sit unbound)
