## ADDED Requirements

> **Status:** All four phases decomposed.
>
> **Decomposition status:**
>
> | Placeholder | Decomposed? | Phase-scoped requirements |
> |---|---|---|
> | `kafka-connect-error-handling` | Yes (Phase 1) | `kafka-connect-dlq-config`, `kafka-connect-dlq-topic` |
> | `spark-sink-dlq` | Yes (Phase 2) | `spark-sink-dlq-wrapper`, `spark-sink-dlq-envelope`, `spark-sink-dlq-opt-in`, `dlq-envelope-shared` |
> | `dlq-observability` | Yes (Phase 3) | `central-dlq-dashboard`, `dlq-traffic-alert-rule` |
> | `dlq-triage-ui` | Yes (Phase 4) | `streamlit-dlq-triage-view` |

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

**Phase 2 — Spark sink DLQ (decomposed from `spark-sink-dlq`).**

### Requirement: dlq-envelope-shared
All DLQ paths in the Spark pipeline SHALL emit messages through a single shared helper module `data-platform/streaming/spark/src/governance/dlq_producer.py` exposing `emit(rows_df, topic, error_stage, extra_fields)`. Every DLQ message SHALL be enriched with `_error_stage` and any caller-supplied `extra_fields` (e.g., `_error_class`, `_error_message`, `_error_expectation`), and the full original row SHALL be preserved as a JSON string in the Kafka message value. Kafka bootstrap SHALL be read from `KAFKA_SERVERS` env, defaulting to `kafka1:9092`.

#### Scenario: shared envelope emitted by GX gate and sink wrapper
- **WHEN** either `with_gx_gate` or `with_sink_dlq` routes a batch to a DLQ topic
- **THEN** the Kafka message value SHALL be a single JSON string containing the original row columns plus `_error_stage` and any extra fields
- **AND** a downstream consumer SHALL be able to parse messages from `{table}_dlq` and `{table}_sink_dlq` with the same schema logic

### Requirement: spark-sink-dlq-wrapper
The Spark CDC pipeline SHALL provide a `with_sink_dlq(inner_writer, table)` wrapper in `data-platform/streaming/spark/src/governance/error_handling.py` that catches any exception raised by the inner `foreachBatch` writer and routes the failing batch's rows to `{table}_sink_dlq` via `dlq_producer.emit(..., error_stage="spark_sink")`. The wrapper SHALL swallow both the primary write exception AND any secondary exception from the DLQ producer itself, so the streaming query never dies from a transient sink failure.

#### Scenario: inner writer raises, batch is routed to sink DLQ
- **WHEN** the ClickHouse JDBC writer raises an exception during `foreachBatch` and the writer has been wrapped with `with_sink_dlq`
- **THEN** every row in the failing batch SHALL be published to `{table}_sink_dlq`
- **AND** the wrapped function SHALL NOT re-raise the exception

#### Scenario: DLQ producer itself fails, no crash
- **WHEN** the inner writer raises AND `dlq_producer.emit` also raises (e.g., Kafka unreachable)
- **THEN** the wrapper SHALL log both errors and return normally without propagating either exception

### Requirement: spark-sink-dlq-envelope
Every message published to a `{table}_sink_dlq` topic SHALL include, in addition to the original row columns, the fields `_error_stage="spark_sink"`, `_error_class` (the Python exception class name, e.g., `"RuntimeError"`), and `_error_message` (the stringified exception).

#### Scenario: sink DLQ message shape
- **WHEN** a `{table}_sink_dlq` message is inspected (e.g., via `kcat -C -t products_sink_dlq -c 1 -e`)
- **THEN** the JSON payload SHALL contain `_error_stage`, `_error_class`, and `_error_message` at the top level alongside the original row's columns

### Requirement: spark-sink-dlq-opt-in
The sink DLQ wrapping SHALL be opt-in via the `ENABLE_SINK_DLQ=1` environment variable, applied inside `ClickHouseWriter.create_batch_writer_function`. When both `ENABLE_SINK_DLQ=1` and `ENABLE_GX_GATE=1` are set, the composition SHALL be `with_gx_gate(with_sink_dlq(inner, table), table)` — GX gate outer so invalid rows never reach the sink wrapper stage. When `ENABLE_SINK_DLQ` is unset or not `"1"`, the writer SHALL behave exactly as it did before this change (crash-on-fail, no DLQ), preserving the loud-failure default for dev.

#### Scenario: opt-in composition order
- **WHEN** `create_batch_writer_function` is invoked with both `ENABLE_SINK_DLQ=1` and `ENABLE_GX_GATE=1`
- **THEN** the returned function SHALL be equivalent to `with_gx_gate(with_sink_dlq(<inner>, table), table)`

#### Scenario: opt-out is the default
- **WHEN** neither `ENABLE_SINK_DLQ` nor `ENABLE_GX_GATE` is set
- **THEN** `create_batch_writer_function` SHALL return the raw ClickHouse writer with no wrappers
- **AND** a sink exception SHALL propagate and terminate the streaming query as before

**Phase 3 — DLQ observability (decomposed from `dlq-observability`).**

### Requirement: central-dlq-dashboard
A Grafana dashboard `Central DLQ` (uid `central-dlq`) SHALL be provisioned under `infrastructure/docker/grafana/provisioning/dashboards/files/observability/central-dlq.json` and rendered in the `Observability` folder. The dashboard SHALL include at minimum: (a) a time-series panel showing `sum by (topic) (rate(kafka_topic_partition_current_offset{topic=~".+_dlq"}[5m]))`, (b) a per-topic total offset bar-gauge, (c) a stat panel counting the number of distinct DLQ topics currently present, and (d) a Loki logs panel filtered on `{container=~"debezium|ed-pyspark-jupyter"} |~ "(?i)DLQ|dead[- ]letter"`.

#### Scenario: dashboard renders
- **WHEN** the `Central DLQ` dashboard is opened in Grafana under the `Observability` folder
- **THEN** all four panels SHALL be present and populated once the corresponding data sources have data
- **AND** the dashboard uid SHALL be `central-dlq`

### Requirement: dlq-traffic-alert-rule
An alert rule `dlq_traffic_present` SHALL be provisioned in `infrastructure/docker/grafana/provisioning/alerting/infra-alerts.yml` alongside the existing infra alerts. The rule SHALL fire when `sum by (topic) (increase(kafka_topic_partition_current_offset{topic=~".+_dlq"}[5m])) > 0` sustains for a `for: 1m` confirmation window, with `severity: warning` and `pillar: error-handling` labels. It SHALL route to the same `default-webhook` contact point as the other observability alerts via the root notification policy.

#### Scenario: alert fires on DLQ traffic
- **WHEN** any `*_dlq` topic receives its first message
- **THEN** the `dlq_traffic_present` alert SHALL enter `Firing` state within its 1-minute confirmation window
- **AND** the alert SHALL route to the `default-webhook` contact point provisioned by `alert-contact-point-webhook`

#### Scenario: alert lives with sibling infra alerts
- **WHEN** the Grafana Alerting page (`http://localhost:3000/alerting/list`) is opened after startup
- **THEN** the `Observability Alerts` folder SHALL contain `dlq_traffic_present` alongside the five rules provisioned by `add-infra-observability`

**Phase 4 — DLQ triage UI (decomposed from `dlq-triage-ui`).**

### Requirement: streamlit-dlq-triage-view
The Streamlit UI SHALL provide a read-only DLQ triage view under `application/cdc-testing-ui/views/dlq_triage.py`, registered in `app.py` and reachable from the sidebar menu label `"🚨 DLQ Triage"`. The view SHALL consume from the fixed set of DLQ topics `debezium_connect_dlq`, `{customers,products,orders}_dlq`, and `{customers,products,orders}_sink_dlq` via `managers.kafka.KafkaManager.consume_messages` and render each message as a row with columns `dlq_topic`, `_error_stage`, `_error_class`, `_error_message` (truncated to 80 characters), `key`, `first_seen`. Each row SHALL have an expander that shows the full JSON payload. The row-construction logic SHALL live in a pure function `build_triage_rows(messages)` so it can be unit-tested without a running Streamlit runtime.

#### Scenario: developer inspects DLQ contents
- **WHEN** a developer opens the DLQ Triage view after DLQ traffic exists
- **THEN** the page SHALL list the recent DLQ messages across every `*_dlq` topic in a single sortable table
- **AND** clicking a row's expander SHALL reveal the full JSON payload

#### Scenario: empty state renders gracefully
- **WHEN** no DLQ traffic has occurred within the selected time window
- **THEN** the page SHALL render an informational empty-state message explaining that steady-state has no DLQ traffic, and SHALL NOT throw or hang

#### Scenario: Kafka Connect raw bytes tolerated
- **WHEN** a `debezium_connect_dlq` message contains a raw non-JSON payload (the record that failed the converter)
- **THEN** `build_triage_rows` SHALL surface a `_raw` fallback field inside the payload and MUST NOT raise
- **AND** the row SHALL display `_error_stage="unknown"` since Kafka Connect's DLQ envelope is header-based rather than value-based
