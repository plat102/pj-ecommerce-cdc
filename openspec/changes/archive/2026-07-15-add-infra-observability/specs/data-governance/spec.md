## MODIFIED Requirements

> **Status:** `add-data-governance` archived with a freshness alert rule provisioned but no contact point wired — alerts fired silently in the Grafana UI. Observability Phase 3 provisions a default webhook contact point; this MODIFY threads the freshness alert to use it, closing the archived-governance gap.

### Requirement: freshness-slo-and-alert
The ClickHouse `data_freshness` view SHALL be wired to a Grafana alert rule that fires when any target table has `minutes_since_last_update > 10`. The alert rule SHALL be provisioned via `infrastructure/docker/grafana/provisioning/alerting/data_freshness.yml` (not hand-configured in the Grafana UI). The rule SHALL reference the default contact point provisioned by observability Phase 3 so notifications reach an external channel (webhook / Slack) rather than terminating in the Grafana UI.

#### Scenario: alert rule provisioned
- **WHEN** Grafana boots with the alerting provisioning file present
- **THEN** the rule `cdc_freshness_10min_slo` SHALL exist in the `data-governance` folder with `for: 2m`
- **AND** the rule's SQL SHALL query `SELECT max(minutes_since_last_update) AS value FROM data_freshness`

#### Scenario: stalled pipeline triggers alert
- **WHEN** Spark CDC jobs are stopped and no new events reach ClickHouse for > 10 minutes
- **THEN** the `cdc_freshness_10min_slo` rule SHALL enter the `Alerting` state after its 2-minute confirmation window

#### Scenario: freshness alert routes to default contact point
- **WHEN** the `cdc_freshness_10min_slo` rule enters the `Alerting` state
- **THEN** a notification SHALL be posted to the default contact point (webhook or Slack) provisioned by observability Phase 3 from `OBS_ALERT_WEBHOOK_URL` / `OBS_SLACK_WEBHOOK_URL` env vars
