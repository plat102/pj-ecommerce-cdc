## MODIFIED Requirements

### Requirement: grafana-dashboard-provisioning
Grafana dashboards SHALL be provisioned from JSON files in `data-platform/dashboards/grafana/` and from `infrastructure/docker/grafana/provisioning/dashboards/files/`. The `make sync-dashboards` target SHALL copy these files into the Grafana provisioning mount. `make reload-grafana` SHALL sync and restart the Grafana container. The provisioned ClickHouse datasource at `infrastructure/docker/grafana/provisioning/datasources/clickhouse.yml` SHALL connect using `username: analyst_readonly` (not `default`) and SHALL reference the password via the `$CLICKHOUSE_ANALYST_PASSWORD` env var expansion rather than a literal password. Grafana SHALL additionally be provisioned with Loki and Prometheus datasources at `infrastructure/docker/grafana/provisioning/datasources/loki.yml` and `.../prometheus.yml`, each pointing at their in-network hostnames (`http://loki:3100` and `http://prometheus:9090`). The `Data Governance Overview` dashboard SHALL include two additional panels named `GX Suite Success Rate (24h)` and `Top 5 Failing Expectations` driven by the Prometheus metrics `gx_suite_success_ratio` and `gx_expectation_success_ratio` (see `gx-prometheus-metrics-textfile` in the `data-quality-reporting` capability). Both panels SHALL carry a `links` array pointing at `http://localhost:8890/` for drilldown to the GX Data Docs site.

#### Scenario: dashboard available after sync
- **WHEN** a new JSON dashboard is added to `data-platform/dashboards/grafana/` and `make reload-grafana` is executed
- **THEN** the dashboard SHALL appear in Grafana at http://localhost:3000 without manual import

#### Scenario: GX panels present on Data Governance Overview
- **WHEN** the `Data Governance Overview` dashboard is opened after startup
- **THEN** it SHALL contain panels titled `GX Suite Success Rate (24h)` and `Top 5 Failing Expectations`
- **AND** each SHALL have a link pointing at `http://localhost:8890/`
