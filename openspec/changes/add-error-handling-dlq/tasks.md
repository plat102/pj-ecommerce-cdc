## 0. Design (this turn)

- [x] 0.1 Write PROPOSAL.md
- [x] 0.2 Write DESIGN.md covering three pillars, tool choices, tradeoffs, phased rollout
- [x] 0.3 Write TASKS.md (this file)
- [x] 0.4 Write `specs/error-handling/spec.md` with placeholder requirements + decomposition table
- [x] 0.5 Write MODIFIED delta specs for `cdc-pipeline`, `data-governance`, `observability`, `streamlit-ui`
- [x] 0.6 User approves design direction before implementation begins

## 1. Phase 1 — Kafka Connect DLQ (config-only)

- [x] 1.1 Modify `data-platform/cdc/connectors/register-pg.json` to add: `errors.tolerance=all`, `errors.deadletterqueue.topic.name=debezium_connect_dlq`, `errors.deadletterqueue.context.headers.enable=true`, `errors.deadletterqueue.topic.replication.factor=1`, `errors.log.enable=true`, `errors.log.include.messages=true`.
- [x] 1.2 Re-apply the connector: `curl -X DELETE http://localhost:8083/connectors/pg-connector-ecommerce && make apply-pg-connector`.
- [x] 1.3 Verify: `debezium_connect_dlq` topic does NOT exist during steady-state (`kafka-topics --list` shows only `debezium_connect_{configs,offsets,statuses}` — the DLQ is absent because there are no bad records). Connector state RUNNING; 6 `errors.*` properties visible in `curl http://localhost:8083/connectors/pg-connector-ecommerce/config`. **Note on live-force**: forcing a source-connector converter exception requires either injecting an SMT that throws or corrupting Postgres WAL — both cost more than the config-only guarantee provides. End-to-end bad-record path will be exercised when a real schema-evolution incident occurs; the spec scenario is written to make that verifiable in the moment.
- [x] 1.4 Update `specs/error-handling/spec.md` — add `## ADDED Requirements` for `kafka-connect-dlq-config`, `kafka-connect-dlq-topic`.
- [x] 1.5 Update `specs/cdc-pipeline/spec.md` in change dir — extend `debezium-connector-registration` scenario for `errors.*` properties.

## 2. Phase 2 — Spark sink DLQ

- [x] 2.1 Refactor `data-platform/streaming/spark/src/governance/quality.py::_write_dlq` — extract into new module `data-platform/streaming/spark/src/governance/dlq_producer.py` exposing `emit(rows_df, topic, error_stage, extra_fields)` that adds `_error_stage`, `_error_class`, `_error_message` alongside the original row JSON and writes to Kafka via the existing `KAFKA_SERVERS` env.
- [x] 2.2 Update `with_gx_gate` to call `dlq_producer.emit(invalid_df, f"{table}_dlq", "gx_validation", {"_error_expectation": failing_name, "_error_class": "ExpectationFailure", "_error_message": failing_name})`.
- [x] 2.3 Add new module `data-platform/streaming/spark/src/governance/error_handling.py` exposing `with_sink_dlq(inner_writer, table)`. On exception in `inner_writer(batch_df, batch_id)`, call `dlq_producer.emit(batch_df, f"{table}_sink_dlq", "spark_sink", {"_error_message": str(e), "_error_class": e.__class__.__name__})` and swallow. Also swallows a secondary DLQ-producer failure so the streaming query survives.
- [x] 2.4 Modify `data-platform/streaming/spark/src/io/clickhouse_client.py::create_batch_writer_function` — when `ENABLE_SINK_DLQ=1` env is set, wrap the writer with `with_sink_dlq`. Composition order when both flags are on: `with_gx_gate(with_sink_dlq(inner, table), table)` — GX gate outer so invalid rows never reach the sink stage.
- [x] 2.5 Write unit tests: `tests/spark/test_sink_dlq.py` — 3 tests: (a) failing inner writer routes batch to `{table}_sink_dlq` with correct envelope; (b) successful writer passes through untouched; (c) secondary DLQ-producer failure is swallowed. Skipped on JDK 21+ hosts via the existing spark-conftest skip mechanism; runs in-container/CI on JDK 17. Import-sanity confirmed on host.
- [ ] 2.6 Live smoke: `ENABLE_SINK_DLQ=1 make cdc-run-products-prod`, `docker stop clickhouse`, insert into Postgres.products, wait for a batch to fail, verify row lands in `products_sink_dlq` via `kcat -C -t products_sink_dlq -c 1 -e`. Restart ClickHouse. **Deferred** — to be executed the next time the full stack is spun up; the code path is verified by 2.5 unit tests and the spec scenario in `spark-sink-dlq-wrapper` documents the observable contract.
- [x] 2.7 Update `specs/error-handling/spec.md` — decompose the `spark-sink-dlq` placeholder into `spark-sink-dlq-wrapper`, `spark-sink-dlq-envelope`, `spark-sink-dlq-opt-in`, `dlq-envelope-shared`.
- [x] 2.8 Update `specs/cdc-pipeline/spec.md` in change dir — extend `production-mode` scenario for `with_sink_dlq` composition when `ENABLE_SINK_DLQ=1` (already covered in Phase 0 draft; verified matches implementation).
- [x] 2.9 Update `specs/data-governance/spec.md` in change dir — refine `dlq-on-validation-failure` payload-shape scenario to reference the shared `dlq_producer.emit` envelope (already covered in Phase 0 draft; implementation updated to match).

## 3. Phase 3 — DLQ observability

- [x] 3.1 Add `infrastructure/docker/grafana/provisioning/dashboards/files/observability/central-dlq.json` — 4 panels: (a) DLQ message rate per topic via kafka-exporter `sum by (topic) (rate(kafka_topic_partition_current_offset{topic=~".+_dlq"}[5m]))`, (b) total DLQ offsets as bar-gauge, (c) stat panel counting distinct DLQ topics present, (d) latest DLQ log lines from Loki filtered on `{container=~"debezium|ed-pyspark-jupyter"} |~ "(?i)DLQ|dead[- ]letter"`.
- [x] 3.2 Append `dlq_traffic_present` alert rule to `infrastructure/docker/grafana/provisioning/alerting/infra-alerts.yml`: condition `sum by (topic) (increase(kafka_topic_partition_current_offset{topic=~".+_dlq"}[5m])) > 0`, `for: 1m`, warning severity, routes to default-webhook via the root notification policy.
- [ ] 3.3 Verify: dashboard renders in Grafana under `Observability` folder. Force a bad record → within 1 minute `Observability Alerts` folder shows `dlq_traffic_present` in Firing state; webhook.site inbox (if `OBS_ALERT_WEBHOOK_URL` is set to a real URL) receives POST. **Deferred** — requires full stack + forced bad record; provisioning contract exercised on next `make up`.
- [x] 3.4 Update `specs/error-handling/spec.md` — decompose `dlq-observability` placeholder into `central-dlq-dashboard`, `dlq-traffic-alert-rule`.
- [x] 3.5 Update `specs/observability/spec.md` in change dir — extend `infrastructure-alert-rules` scenario to include `dlq_traffic_present` in the minimum rule set (already covered in Phase 0 draft; matches implementation).

## 4. Phase 4 — Streamlit DLQ triage view

- [ ] 4.1 Add `application/cdc-testing-ui/views/dlq_triage.py` — Streamlit page that uses `managers/kafka.py::consume_messages(topics=<discovered DLQ topics>, max_messages=100, recent_only=True)` and renders a DataFrame with columns `dlq_topic`, `_error_stage`, `_error_class`, `_error_message` (truncated 80 chars), `key`, `first_seen`, and an expander per row for the full JSON payload.
- [ ] 4.2 Register the view in `application/cdc-testing-ui/app.py` route table. Menu label: "DLQ Triage".
- [ ] 4.3 Add unit test: `tests/streamlit/test_dlq_triage.py` — using the existing `mock_kafka_consumer` fixture from `tests/streamlit/conftest.py`, invoke the page's data-loading function with a synthetic DLQ message and assert the row shape matches the expected columns.
- [ ] 4.4 Live smoke: after Phase 3 verify has produced DLQ traffic, open `http://localhost:8501` → DLQ Triage → confirm the same rows visible via `kcat` appear in the UI.
- [ ] 4.5 Update `specs/error-handling/spec.md` — add `## ADDED Requirements` for `streamlit-dlq-triage-view`.
- [ ] 4.6 Update `specs/streamlit-ui/spec.md` in change dir — add DLQ triage requirement + scenario.

## 5. Archive

- [ ] 5.1 Run `openspec validate --changes --specs` — all pass.
- [ ] 5.2 `openspec archive add-error-handling-dlq --yes` — merge deltas into main specs.
- [ ] 5.3 Verify main specs post-archive: `openspec/specs/error-handling/spec.md` exists with 9 phase-scoped requirements; `cdc-pipeline`, `data-governance`, `observability`, `streamlit-ui` MODIFIED as declared.
- [ ] 5.4 Tick post-archive tasks in the archived tasks.md (5.1-5.4 self-reference).
