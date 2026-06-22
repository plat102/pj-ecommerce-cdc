## Purpose

ClickHouse storage semantics for CDC-deduplicated data plus the Grafana dashboard surface. Establishes the `ReplacingMergeTree` + `_version` + `_deleted` + `FINAL` pattern that lets stateless Spark jobs land all CDC events without explicit deduplication, and the provisioning workflow for Grafana dashboards and ClickHouse analytics views.

## Requirements

### Requirement: clickhouse-table-engine
All CDC target tables in ClickHouse (`customers_cdc`, `products_cdc`, `orders_cdc`) SHALL use the `ReplacingMergeTree(_version)` engine, ordered by the table's primary key column (`id`). The schema is defined in `infrastructure/docker/clickhouse/create_tables.sql`.

#### Scenario: duplicate events deduplicated automatically
- **WHEN** multiple CDC events for the same row `id` are written to ClickHouse (e.g., insert followed by two updates)
- **THEN** a `SELECT * FROM {table}_cdc FINAL` query SHALL return only the row with the highest `_version` value

---

### Requirement: version-column
Each CDC table row SHALL carry a `_version` column of type `UInt64` populated from the Debezium `ts_ms` field (milliseconds since epoch). This value drives ReplacingMergeTree deduplication.

#### Scenario: later event has higher version
- **WHEN** an UPDATE event arrives after an INSERT for the same `id`
- **THEN** the UPDATE row SHALL have a higher `_version` than the INSERT row
- **AND** `SELECT FINAL` SHALL return the UPDATE row's column values

---

### Requirement: deleted-flag
Each CDC table row SHALL carry a `_deleted` column of type `UInt8` (default 0). The Spark transformer SHALL set `_deleted = 1` when the Debezium `op` field equals `"d"` (delete operation).

#### Scenario: deleted row excluded from active view
- **WHEN** a row is deleted in Postgres and the `_deleted = 1` event is written to ClickHouse
- **THEN** an application query filtering `WHERE _deleted = 0` on the `FINAL` result SET SHALL NOT return that row

---

### Requirement: final-modifier-for-dedup
All queries that require deduplicated, current-state results SHALL use the `FINAL` query modifier (e.g., `SELECT * FROM customers_cdc FINAL WHERE _deleted = 0`).

#### Scenario: without FINAL shows duplicates
- **WHEN** a query is run without FINAL after multiple events for the same row id
- **THEN** multiple rows for the same id MAY be returned (ReplacingMergeTree merges are async)

#### Scenario: with FINAL shows single latest row
- **WHEN** a query includes FINAL
- **THEN** exactly one row per primary key SHALL be returned, reflecting the latest known state

---

### Requirement: grafana-dashboard-provisioning
Grafana dashboards SHALL be provisioned from JSON files in `data-platform/dashboards/grafana/`. The `make sync-dashboards` target SHALL copy these files into the Grafana provisioning mount. `make reload-grafana` SHALL sync and restart the Grafana container.

#### Scenario: dashboard available after sync
- **WHEN** a new JSON dashboard is added to `data-platform/dashboards/grafana/` and `make reload-grafana` is executed
- **THEN** the dashboard SHALL appear in Grafana at http://localhost:3000 without manual import

#### Scenario: dashboard source of truth
- **WHEN** a dashboard is modified in Grafana's UI and then `make reload-grafana` is run
- **THEN** the provisioned JSON file version SHALL overwrite any UI-only changes

---

### Requirement: analytics-views
ClickHouse analytics views SHALL be defined in `data-platform/dashboards/clickhouse/analytics_views.sql`. These views encapsulate `FINAL`-based queries for use by Grafana without exposing raw deduplication logic to dashboard queries.

#### Scenario: grafana queries views not raw tables
- **WHEN** a Grafana dashboard panel queries data
- **THEN** the panel SQL SHALL reference named analytics views, not raw `*_cdc` tables directly
