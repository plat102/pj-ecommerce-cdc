## MODIFIED Requirements

> **Status:** Grafana grows two new provisioned datasources (Loki + Prometheus) alongside the existing ClickHouse one, and six new observability dashboards alongside the existing three business dashboards. The datasource path for observability sources is separate from the ClickHouse business path, so this delta extends `grafana-dashboard-provisioning` rather than replacing it.

### Requirement: grafana-dashboard-provisioning
Grafana dashboards SHALL be provisioned from JSON files in `data-platform/dashboards/grafana/` and from `infrastructure/docker/grafana/provisioning/dashboards/files/`. The `make sync-dashboards` target SHALL copy these files into the Grafana provisioning mount. `make reload-grafana` SHALL sync and restart the Grafana container. The provisioned ClickHouse datasource at `infrastructure/docker/grafana/provisioning/datasources/clickhouse.yml` SHALL connect using `username: analyst_readonly` (not `default`) and SHALL reference the password via the `$CLICKHOUSE_ANALYST_PASSWORD` env var expansion rather than a literal password. Grafana SHALL additionally be provisioned with Loki and Prometheus datasources at `infrastructure/docker/grafana/provisioning/datasources/loki.yml` and `.../prometheus.yml`, each pointing at their in-network hostnames (`http://loki:3100` and `http://prometheus:9090`).

#### Scenario: dashboard available after sync
- **WHEN** a new JSON dashboard is added to `data-platform/dashboards/grafana/` and `make reload-grafana` is executed
- **THEN** the dashboard SHALL appear in Grafana at http://localhost:3000 without manual import

#### Scenario: dashboard source of truth
- **WHEN** a dashboard is modified in Grafana's UI and then `make reload-grafana` is run
- **THEN** the provisioned JSON file version SHALL overwrite any UI-only changes

#### Scenario: Grafana datasource uses analyst_readonly
- **WHEN** the provisioned `clickhouse.yml` datasource file is inspected
- **THEN** `jsonData.username` SHALL be `analyst_readonly` and `secureJsonData.password` SHALL be the literal string `$CLICKHOUSE_ANALYST_PASSWORD` (expanded by Grafana at runtime)

#### Scenario: Grafana has three datasources after Phase 1 of observability
- **WHEN** the Grafana datasources page (`http://localhost:3000/datasources`) is inspected
- **THEN** three datasources SHALL be present: `ClickHouse-Analytics`, `Loki`, and `Prometheus`, each with a passing "Save & test"

#### Scenario: observability dashboards ship alongside business dashboards
- **WHEN** the Grafana dashboards folder is inspected after `make up`
- **THEN** the existing business dashboards (executive-dashboard, customer-insights, test-dashboard) SHALL coexist with the observability dashboards (container-health, central-logs, kafka-pipeline, debezium-connector, spark-streaming, postgres-replication)
