## MODIFIED Requirements

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

### Requirement: grafana-dashboard-provisioning
Grafana dashboards SHALL be provisioned from JSON files in `data-platform/dashboards/grafana/`. The `make sync-dashboards` target SHALL copy these files into the Grafana provisioning mount. `make reload-grafana` SHALL sync and restart the Grafana container. The provisioned ClickHouse datasource at `infrastructure/docker/grafana/provisioning/datasources/clickhouse.yml` SHALL connect using `username: analyst_readonly` (not `default`) and SHALL reference the password via the `$CLICKHOUSE_ANALYST_PASSWORD` env var expansion rather than a literal password.

#### Scenario: dashboard available after sync
- **WHEN** a new JSON dashboard is added to `data-platform/dashboards/grafana/` and `make reload-grafana` is executed
- **THEN** the dashboard SHALL appear in Grafana at http://localhost:3000 without manual import

#### Scenario: dashboard source of truth
- **WHEN** a dashboard is modified in Grafana's UI and then `make reload-grafana` is run
- **THEN** the provisioned JSON file version SHALL overwrite any UI-only changes

#### Scenario: Grafana datasource uses analyst_readonly
- **WHEN** the provisioned `clickhouse.yml` datasource file is inspected
- **THEN** `jsonData.username` SHALL be `analyst_readonly` and `secureJsonData.password` SHALL be the literal string `$CLICKHOUSE_ANALYST_PASSWORD` (expanded by Grafana at runtime)
