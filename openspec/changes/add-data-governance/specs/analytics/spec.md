## MODIFIED Requirements

### Requirement: clickhouse-table-engine
All CDC target tables in ClickHouse (`customers_cdc`, `products_cdc`, `orders_cdc`) SHALL use the `ReplacingMergeTree(_version)` engine, ordered by the table's primary key column (`id`). Each table SHALL additionally declare a two-clause TTL anchored on `toDateTime(_version / 1000)`: 90 days for tombstones (`WHERE _deleted = 1`) and 2 years for active rows. The schema (engine + TTL) is defined in `infrastructure/docker/clickhouse/create_tables.sql`.

#### Scenario: duplicate events deduplicated automatically
- **WHEN** multiple CDC events for the same row `id` are written to ClickHouse (e.g., insert followed by two updates)
- **THEN** a `SELECT * FROM {table}_cdc FINAL` query SHALL return only the row with the highest `_version` value

#### Scenario: tombstone row expires after 90 days
- **WHEN** a row with `_deleted = 1` and a `_version` older than 90 days ago is processed during a ClickHouse merge
- **THEN** the row SHALL be removed from the table

#### Scenario: active row expires after 2 years
- **WHEN** any row with a `_version` older than 2 years ago is processed during a ClickHouse merge
- **THEN** the row SHALL be removed regardless of `_deleted` value
