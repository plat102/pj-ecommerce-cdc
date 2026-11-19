## MODIFIED Requirements

### Requirement: openmetadata-ingestion
The project SHALL ship OpenMetadata ingestion configuration files for each system in the CDC pipeline it owns as a data producer or consumer: PostgreSQL source, Kafka + Schema Registry, and ClickHouse sink. Each config SHALL live under `data-platform/governance/openmetadata/ingestion/{postgres,kafka,clickhouse}.yaml` and SHALL be runnable via one-command Makefile wrappers that do not require any host-side `pip install`. Each wrapper SHALL invoke the CLI inside an ephemeral `openmetadata/ingestion:${OPENMETADATA_VERSION}` container attached to the `ecommerce-network` Docker network so in-network hostnames in the YAML (`postgres:5432`, `kafka1:9092`, `clickhouse:8123`, `openmetadata-server:8585`) resolve without modification. Ingestion SHALL be on-demand — not started by `make up-governance`.

#### Scenario: three ingestion configs exist
- **WHEN** `data-platform/governance/openmetadata/ingestion/` is inspected
- **THEN** it SHALL contain `postgres.yaml`, `kafka.yaml`, and `clickhouse.yaml`, each declaring a `source`, `sink` (`metadata-rest`), and `workflowConfig` block

#### Scenario: kafka config uses Apicurio ccompat endpoint
- **WHEN** `kafka.yaml` is inspected
- **THEN** `source.serviceConnection.config.schemaRegistryURL` SHALL be `http://schema-registry:8080/apis/ccompat/v7` (Apicurio's Confluent-compatible endpoint, which OpenMetadata's kafka ingestion targets natively)

#### Scenario: postgres ingestion produces a database service
- **WHEN** `make ingest-pg` runs against a healthy OpenMetadata stack + healthy Postgres
- **THEN** an `ecommerce-postgres` database service SHALL appear in OpenMetadata containing at minimum the tables `public.customers`, `public.products`, `public.orders`

#### Scenario: kafka ingestion produces a messaging service
- **WHEN** `make ingest-kafka` runs against a healthy OM stack + healthy Kafka/Apicurio
- **THEN** an `ecommerce-kafka` messaging service SHALL appear in OpenMetadata containing at minimum the topics `pg.public.customers`, `pg.public.products`, `pg.public.orders`

#### Scenario: clickhouse ingestion produces a database service
- **WHEN** `make ingest-clickhouse` runs against a healthy OM stack + healthy ClickHouse
- **THEN** an `ecommerce-clickhouse` database service SHALL appear in OpenMetadata containing at minimum the tables `ecommerce_analytics.customers_cdc`, `products_cdc`, `orders_cdc`

#### Scenario: ingestion is idempotent
- **WHEN** any `make ingest-*` target is invoked twice in succession
- **THEN** the second run SHALL succeed without error AND SHALL update existing OpenMetadata entries rather than creating duplicates

#### Scenario: ingest-all fails fast
- **WHEN** `make ingest-all` runs with one of the three source systems unavailable (e.g., Postgres stopped)
- **THEN** the first failing target SHALL exit non-zero AND subsequent targets in the chain SHALL NOT execute

#### Scenario: ingest-status reports service counts
- **WHEN** `make ingest-status` runs against a healthy OpenMetadata stack
- **THEN** it SHALL print counts of database services, messaging services, and (optionally) their table/topic totals derived from the OpenMetadata REST API at `http://localhost:8585/api/v1/services/*`
- **AND** SHALL exit non-zero if OpenMetadata is unreachable
