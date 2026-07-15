## MODIFIED Requirements

> **Status:** Phase 3 of this change extends the `infrastructure-alert-rules` requirement to include the new `dlq_traffic_present` rule alongside the 5 rules provisioned by `add-infra-observability` Phase 3.

### Requirement: infrastructure-alert-rules
Grafana SHALL be provisioned with alert rules covering the failure classes the pipeline actually hits. The rules SHALL live under `infrastructure/docker/grafana/provisioning/alerting/infra-alerts.yml` and SHALL include at minimum: `kafka_consumer_lag_high` (sum-by-consumergroup lag > 10000, for 5m, warning); `debezium_connector_not_running` (kafka_connect_connector_status{status="running"} < 1, for 1m, critical); `spark_streaming_job_absent` (no batch progress in 10 min, for 5m, critical); `container_memory_over_90pct` (cAdvisor usage/limit > 0.9, for 10m, warning); `container_restart_loop` (>3 restarts in 10 min, for 2m, critical); `dlq_traffic_present` (any `*_dlq` topic sees >0 messages in a 5-minute window, for 1m, warning). All rules SHALL live in the `Observability Alerts` Grafana folder.

#### Scenario: six infra rules provisioned
- **WHEN** the Grafana Alerting page (`http://localhost:3000/alerting/list`) is opened after startup
- **THEN** the folder `Observability Alerts` SHALL contain (at minimum) the six rules named above, each with a non-empty `condition`, `for` duration, and severity label

#### Scenario: connector failure fires alert
- **WHEN** the Debezium connector transitions away from RUNNING for more than 1 minute
- **THEN** the `debezium_connector_not_running` rule SHALL enter the `Alerting` state

#### Scenario: DLQ traffic fires alert
- **WHEN** any `*_dlq` topic receives its first message
- **THEN** the `dlq_traffic_present` rule SHALL enter the `Firing` state within the 1-minute confirmation window
- **AND** the alert SHALL route to the default-webhook contact point provisioned by `alert-contact-point-webhook`
