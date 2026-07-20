## Purpose

ClickHouse storage semantics for CDC-deduplicated data plus the Grafana dashboard surface. Establishes the `ReplacingMergeTree` + `_version` + `_deleted` + `FINAL` pattern that lets stateless Spark jobs land all CDC events without explicit deduplication, and the provisioning workflow for Grafana dashboards and ClickHouse analytics views.
## Requirements
### Requirement: clickhouse-table-engine
All CDC target tables in ClickHouse (`customers_cdc`, `products_cdc`, `orders_cdc`) SHALL use the `ReplacingMergeTree(_version)` engine, ordered by the table's primary key column (`id`). Each table SHALL additionally declare a two-clause TTL anchored on `toDateTime(_version / 1000)`: 90 days for tombstones (`WHERE _deleted = 1`) and 2 years for active rows. The same migration file (`infrastructure/docker/clickhouse/create_tables.sql`) SHALL declare the `analyst_readonly` role with `SELECT`-only grants on all three CDC tables and row policies that restrict visible rows to `_deleted = 0`. The role's user identity is created at container init from `create_governance_users.sh` using the `CLICKHOUSE_ANALYST_PASSWORD` env var.

#### Scenario: duplicate events deduplicated automatically
- **WHEN** multiple CDC events for the same row `id` are written to ClickHouse (e.g., insert followed by two updates)
- **THEN** a `SELECT * FROM {table}_cdc FINAL` query SHALL return only the row with the highest `_version` value

#### Scenario: tombstone row expires after 90 days
- **WHEN** a row with `_deleted = 1` and a `_version` older than 90 days ago is processed during a ClickHouse merge
- **THEN** the row SHALL be removed from the table

#### Scenario: active row expires after 2 years
- **WHEN** any row with a `_version` older than 2 years ago is processed during a ClickHouse merge
- **THEN** the row SHALL be removed regardless of `_deleted` value

#### Scenario: analyst_readonly role restricted to active rows
- **WHEN** a user connected as `analyst_readonly` runs `SELECT * FROM ecommerce_analytics.customers_cdc`
- **THEN** the result set SHALL exclude every row where `_deleted = 1`

#### Scenario: analyst_readonly role cannot mutate
- **WHEN** a user connected as `analyst_readonly` attempts `INSERT`, `ALTER`, or `DROP` on any CDC table
- **THEN** ClickHouse SHALL reject the statement with an access-denied error

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
Grafana dashboards SHALL be provisioned from JSON files in `data-platform/dashboards/grafana/` and from `infrastructure/docker/grafana/provisioning/dashboards/files/`. The `make sync-dashboards` target SHALL copy these files into the Grafana provisioning mount. `make reload-grafana` SHALL sync and restart the Grafana container. The provisioned ClickHouse datasource at `infrastructure/docker/grafana/provisioning/datasources/clickhouse.yml` SHALL connect using `username: analyst_readonly` (not `default`) and SHALL reference the password via the `$CLICKHOUSE_ANALYST_PASSWORD` env var expansion rather than a literal password. Grafana SHALL additionally be provisioned with Loki and Prometheus datasources at `infrastructure/docker/grafana/provisioning/datasources/loki.yml` and `.../prometheus.yml`, each pointing at their in-network hostnames (`http://loki:3100` and `http://prometheus:9090`). The `Data Governance Overview` dashboard SHALL include two additional panels named `GX Suite Success Rate (24h)` and `Top 5 Failing Expectations` driven by the Prometheus metrics `gx_suite_success_ratio` and `gx_expectation_success_ratio` (see `gx-prometheus-metrics-textfile` in the `data-quality-reporting` capability). Both panels SHALL carry a `links` array pointing at `http://localhost:8890/` for drilldown to the GX Data Docs site.

#### Scenario: dashboard available after sync
- **WHEN** a new JSON dashboard is added to `data-platform/dashboards/grafana/` and `make reload-grafana` is executed
- **THEN** the dashboard SHALL appear in Grafana at http://localhost:3000 without manual import

#### Scenario: GX panels present on Data Governance Overview
- **WHEN** the `Data Governance Overview` dashboard is opened after startup
- **THEN** it SHALL contain panels titled `GX Suite Success Rate (24h)` and `Top 5 Failing Expectations`
- **AND** each SHALL have a link pointing at `http://localhost:8890/`

### Requirement: analytics-views
ClickHouse analytics views SHALL be defined in `data-platform/dashboards/clickhouse/analytics_views.sql`. These views encapsulate `FINAL`-based queries for use by Grafana without exposing raw deduplication logic to dashboard queries.

#### Scenario: grafana queries views not raw tables
- **WHEN** a Grafana dashboard panel queries data
- **THEN** the panel SQL SHALL reference named analytics views, not raw `*_cdc` tables directly

