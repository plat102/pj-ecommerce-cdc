## ADDED Requirements

### Requirement: data-contract-yaml-per-table

The project SHALL ship one Open Data Contract Standard (ODCS) v3.x YAML file per CDC-covered table at `data-platform/governance/contracts/{customers,products,orders}.yaml`. Each contract SHALL declare, at minimum, the source column list with `name` and `logicalType`, the `required` flag, and the `servers` block naming the Postgres source, Kafka topic, and ClickHouse sink for that table. Columns that undergo a cross-layer transformation (PII masking, decimal decoding, ID widening) SHALL declare it via `customProperties` entries so the drift test can reconcile intentional differences. Sink-only metadata columns (`_version`, `_deleted`) SHALL be declared with `customProperties.origin=sink_metadata` so they are excluded from source-layer checks.

#### Scenario: customers contract declares source schema with PII annotations

- **WHEN** `data-platform/governance/contracts/customers.yaml` is parsed
- **THEN** the `schema` block SHALL contain a model with columns `id`, `name`, `email`, `created_at`
- **AND** column `email` SHALL declare `customProperties` including `pii.classification=sensitive` and `sink.transformation=sha256_salted`
- **AND** column `name` SHALL declare `customProperties` including `pii.classification=sensitive` and `sink.transformation=tokenize_first_initial`

#### Scenario: products contract declares decimal wire encoding

- **WHEN** `data-platform/governance/contracts/products.yaml` is parsed
- **THEN** column `price` SHALL have `logicalType=decimal` with `precision=10` and `scale=2`
- **AND** column `price` SHALL declare `customProperties.wire.encoding=debezium_base64_decimal` and `customProperties.wire.decoder=decode_decimal_udf`

#### Scenario: sink metadata columns are annotated

- **WHEN** any contract file at `data-platform/governance/contracts/*.yaml` is parsed
- **THEN** columns `_version` and `_deleted` SHALL be present in the `schema` block
- **AND** each SHALL declare `customProperties.origin=sink_metadata`

#### Scenario: contract servers block references all pipeline endpoints

- **WHEN** any contract file at `data-platform/governance/contracts/*.yaml` is parsed
- **THEN** the `servers` block SHALL contain entries for `postgres` (referencing schema `public` and the source table), `kafka` (referencing the topic `pg.public.{table}`), and `clickhouse` (referencing database `ecommerce_analytics` and the `{table}_cdc` sink table)

### Requirement: contract-schema-drift-test

A pytest-driven drift test at `tests/contracts/test_schema_drift.py` SHALL, for each contract at `data-platform/governance/contracts/*.yaml`, verify that the contract's column list agrees with all four downstream layers: Postgres DDL (`infrastructure/docker/postgres/init.sql`), Spark schema (`data-platform/streaming/spark/src/schemas/cdc_schemas.py`), ClickHouse DDL (`infrastructure/docker/clickhouse/create_tables.sql`), and the corresponding GX suite (`data-platform/governance/expectations/{table}_cdc_suite.json`). The test SHALL apply the type-mapping table declared in `tests/contracts/parsers.py` (ODCS `logicalType` → per-layer type). Columns declared with `customProperties.origin=sink_metadata` SHALL be excluded from Postgres and Spark checks but required in ClickHouse. Columns with a `customProperties.sink.transformation` annotation SHALL use the annotated post-transform type when compared against ClickHouse.

#### Scenario: contract-to-Postgres drift is detected

- **WHEN** a contract declares column `customers.tax_id` (not sink metadata) and `infrastructure/docker/postgres/init.sql` does not declare it in table `customers`
- **THEN** the drift test SHALL fail with a message identifying the contract file, the layer (`postgres`), the missing column name, and the direction (`contract has, layer missing`)

#### Scenario: layer-to-contract drift is detected

- **WHEN** `infrastructure/docker/clickhouse/create_tables.sql` declares column `orders_cdc.tax_amount` and the corresponding contract at `data-platform/governance/contracts/orders.yaml` does not declare it (and it is not a known metadata column)
- **THEN** the drift test SHALL fail with a message identifying the contract file, the layer (`clickhouse`), the unexpected column name, and the direction (`layer has, contract missing`)

#### Scenario: intentional transformations are not flagged as drift

- **WHEN** contract `customers.yaml` declares `email` with `logicalType=string` and `customProperties.sink.transformation=sha256_salted`
- **AND** ClickHouse DDL declares `customers_cdc.email` as `String`
- **THEN** the drift test SHALL PASS for the ClickHouse layer
- **AND** the test SHALL NOT compare against the raw plaintext logical type

#### Scenario: ID widening from Postgres to ClickHouse is accepted

- **WHEN** contract declares `id` with `logicalType=integer` (mapping to Postgres `SERIAL`/`INTEGER`)
- **AND** ClickHouse DDL declares `id` as `Int64`
- **THEN** the drift test SHALL PASS (the type mapping table permits `integer` → `Int32` OR `Int64`)

#### Scenario: sink metadata columns are required in ClickHouse only

- **WHEN** any contract declares `_version` and `_deleted` with `customProperties.origin=sink_metadata`
- **AND** ClickHouse DDL for the corresponding `*_cdc` table declares both columns
- **AND** Postgres DDL and Spark schema do not declare them
- **THEN** the drift test SHALL PASS for all four layers

#### Scenario: GX suite must cover required columns

- **WHEN** contract declares column `id` with `required: true`
- **AND** the corresponding GX suite at `data-platform/governance/expectations/{table}_cdc_suite.json` does not contain an `expect_column_values_to_not_be_null` expectation on `id`
- **THEN** the drift test SHALL fail with a message identifying the missing expectation

### Requirement: contract-om-catalog-reconciliation

The drift test SHALL treat the OpenMetadata catalog as a fifth reconciliation layer, cross-checked via `GET /api/v1/tables/name/{fqn}` on the OM server (default `http://localhost:8585`, overridable via `OM_BASE_URL` env). For each contract, two OM checks SHALL run: one against the source FQN (`ecommerce-postgres.public.{table}`) and one against the sink FQN (`ecommerce-clickhouse.ecommerce_analytics.{table}_cdc`), matching the service names declared in the `add-om-ingestion` ingestion YAMLs.

Unlike the four DDL/GX layers, OM-layer checks SHALL soft-fail — when the OM server is unreachable, returns 404, or returns a 401/403 authentication error, the corresponding parametrization SHALL be skipped (`pytest.skip`) with a diagnostic message naming the FQN and the reason, rather than failing the test suite. When OM returns a valid column list, the check SHALL apply the same column-name and type comparison as the DDL layers, using the same type-mapping table and the same handling of `customProperties.origin=sink_metadata` (excluded from source, required at sink).

A CI workflow SHALL run `make ingest-all` whenever `infrastructure/docker/postgres/init.sql` or `infrastructure/docker/clickhouse/create_tables.sql` changes in a pull request, so OM's view of the schema is refreshed before the OM-layer drift check runs. Absent this hook, the OM layer becomes a false-positive generator on legitimate schema changes.

#### Scenario: OM-layer check runs against source and sink

- **WHEN** the drift test runs with the OM server reachable and the catalog populated by `make ingest-all`
- **AND** the contract `customers.yaml` declares columns `id`, `name`, `email`, `created_at`, `_version`, `_deleted`
- **THEN** two OM-layer parametrizations SHALL execute — one against `ecommerce-postgres.public.customers` (verifying `id`, `name`, `email`, `created_at`; excluding `_version` and `_deleted`) and one against `ecommerce-clickhouse.ecommerce_analytics.customers_cdc` (verifying all six columns)
- **AND** both SHALL PASS when OM's reported columns match the contract (with type mapping applied)

#### Scenario: OM unreachable is a skip, not a failure

- **WHEN** the drift test runs on a workstation where the governance stack is not up (`http://localhost:8585` returns connection-refused)
- **THEN** the OM-layer parametrizations SHALL be reported as `SKIPPED` with a reason message identifying the FQN and the connection error
- **AND** `make test` SHALL exit with status 0 (assuming no other test failures)
- **AND** the four DDL/GX layers SHALL continue to be hard-gated as normal

#### Scenario: OM disagreement fails the drift test

- **WHEN** the OM server is reachable
- **AND** the contract declares column `orders.discount` (not sink metadata)
- **AND** OM's cached view of `ecommerce-postgres.public.orders` does not include `discount` (e.g., `make ingest-all` was not re-run after the DDL change)
- **THEN** the drift test SHALL fail with a message identifying the contract file, the layer (`om-source`), the missing column, and a hint pointing at `make ingest-all` as the likely remediation

#### Scenario: CI hook re-ingests when schema files change

- **WHEN** a pull request modifies `infrastructure/docker/postgres/init.sql` or `infrastructure/docker/clickhouse/create_tables.sql`
- **THEN** the CI workflow SHALL start the governance stack, run `make ingest-all` to refresh OM, and then run `make test`
- **AND** the OM-layer check SHALL run against the fresh catalog (not skipped, not stale)

### Requirement: contract-drift-ci-gate

The drift test SHALL be discoverable by pytest via the `tests/` collection path used by `make test`, and failures SHALL cause `make test` to exit with a non-zero status. No dedicated Makefile target is required; the test SHALL run as part of the existing `uv run pytest` invocation.

#### Scenario: drift test participates in default test run

- **WHEN** `make test` is run at repository root
- **AND** any contract at `data-platform/governance/contracts/*.yaml` disagrees with any of the four downstream layers on a non-annotated difference
- **THEN** pytest SHALL report at least one failing test in `tests/contracts/test_schema_drift.py`
- **AND** `make test` SHALL exit with a non-zero status

#### Scenario: passing drift test is silent (no false positives on happy path)

- **WHEN** `make test` is run at repository root
- **AND** all contracts agree with all four downstream layers (accounting for annotated transformations and sink metadata)
- **THEN** pytest SHALL report all drift tests as passing
- **AND** `make test` SHALL exit with status 0
