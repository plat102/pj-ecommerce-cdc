## ADDED Requirements

> **Status:** Phase 1 (Kafka Connect DLQ) requirements are decomposed below. Phases 2/3/4 remain broad placeholders.
>
> **Decomposition status:**
>
> | Placeholder | Decomposed? | Phase-scoped requirements |
> |---|---|---|
> | `kafka-connect-error-handling` | Yes (Phase 1) | `kafka-connect-dlq-config`, `kafka-connect-dlq-topic` |
> | `spark-sink-dlq` | Not yet | `spark-sink-dlq-wrapper`, `spark-sink-dlq-envelope`, `spark-sink-dlq-opt-in`, `dlq-envelope-shared` |
> | `dlq-observability` | Not yet | `central-dlq-dashboard`, `dlq-traffic-alert-rule` |
> | `dlq-triage-ui` | Not yet | `streamlit-dlq-triage-view` |

**Phase 1 — Kafka Connect DLQ (decomposed from `kafka-connect-error-handling`).**

### Requirement: kafka-connect-dlq-config
The Debezium PostgreSQL connector configuration in `data-platform/cdc/connectors/register-pg.json` SHALL declare six `errors.*` properties enabling Kafka Connect's built-in per-record error handling: `errors.tolerance=all`, `errors.deadletterqueue.topic.name=debezium_connect_dlq`, `errors.deadletterqueue.context.headers.enable=true`, `errors.deadletterqueue.topic.replication.factor=1`, `errors.log.enable=true`, `errors.log.include.messages=true`.

#### Scenario: connector config has errors.* block
- **WHEN** `curl http://localhost:8083/connectors/pg-connector-ecommerce/config` is executed
- **THEN** the response body SHALL contain all six `errors.*` properties above with the exact values named

#### Scenario: apply-pg-connector re-registers with errors block
- **WHEN** `make apply-pg-connector` runs against a stack where the connector already exists (409 conflict) after the JSON was updated
- **THEN** deleting the existing connector via `curl -X DELETE http://localhost:8083/connectors/pg-connector-ecommerce` and re-applying SHALL result in a RUNNING connector whose config now includes the errors block

### Requirement: kafka-connect-dlq-topic
The `debezium_connect_dlq` Kafka topic SHALL auto-create only when the connector routes its first bad record (Kafka broker default `auto.create.topics.enable=true`); the topic SHALL NOT exist during steady-state operation. When it exists, every message SHALL carry Kafka headers `__connect.errors.topic`, `__connect.errors.partition`, `__connect.errors.offset`, `__connect.errors.exception.class.name`, and `__connect.errors.exception.stacktrace` populated by Kafka Connect's DLQ handler.

#### Scenario: DLQ topic absent during steady-state
- **WHEN** the CDC pipeline is operating normally with no source data corruption
- **THEN** `kafka-topics --list` SHALL NOT include `debezium_connect_dlq`

#### Scenario: bad record routed to DLQ with headers
- **WHEN** a record entering the connector triggers a converter or transform exception
- **THEN** the record SHALL appear on `debezium_connect_dlq` with all five `__connect.errors.*` headers populated
- **AND** the connector task SHALL remain in RUNNING state

### Requirement: spark-sink-dlq
Each Spark CDC job SHALL wrap its ClickHouse `foreachBatch` writer with a dead-letter path that catches exceptions during the write and routes the failing batch's rows to a per-table sink DLQ topic. The wrapping SHALL be opt-in via the `ENABLE_SINK_DLQ=1` environment variable to preserve the existing crash-on-fail behavior in dev environments. DLQ payload envelopes SHALL be shared across the GX-validation DLQ and the sink DLQ so a single downstream consumer can read all DLQ topics without stage-specific parsing.

#### Scenario: sink failure routes rows to DLQ
- **WHEN** the ClickHouse JDBC writer raises an exception during `foreachBatch` and `ENABLE_SINK_DLQ=1`
- **THEN** every row in the failing batch SHALL be published to `{table}_sink_dlq`
- **AND** each DLQ message SHALL carry `_error_stage="spark_sink"`, `_error_class`, and `_error_message` alongside the original row JSON

### Requirement: dlq-observability
DLQ traffic across all `*_dlq` topics SHALL be surfaced in Grafana via both a dedicated dashboard and an alert rule that fires the moment any DLQ receives its first message within a 5-minute window.

#### Scenario: dashboard renders DLQ traffic
- **WHEN** the "Central DLQ" dashboard is opened in Grafana's Observability folder
- **THEN** it SHALL show per-topic message rate for all `*_dlq` topics via kafka-exporter metrics

#### Scenario: alert fires on DLQ traffic
- **WHEN** any `*_dlq` topic receives its first message
- **THEN** the `dlq_traffic_present` alert SHALL enter Firing state within its 1-minute confirmation window and route to the default-webhook contact point

### Requirement: dlq-triage-ui
The Streamlit UI SHALL provide a read-only DLQ triage view listing recent contents from all DLQ topics, with each row showing at minimum: source DLQ topic, error stage, error class, truncated error message, message key, first-seen timestamp, and expandable full payload.

#### Scenario: developer inspects a DLQ row
- **WHEN** a developer opens the Streamlit "DLQ Triage" view after DLQ traffic exists
- **THEN** the page SHALL list the recent DLQ messages across every `*_dlq` topic (Kafka Connect + Spark GX + Spark sink) in a single table
