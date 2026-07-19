## Context

The CDC pipeline has three failure surfaces where bad data can enter:

1. **Kafka Connect (Debezium)**: A malformed Postgres WAL entry, an Apicurio schema outage mid-flight, or a converter incompatibility. Default Debezium behavior: connector goes to `FAILED` state, downstream stalls.
2. **Spark source (Kafka reader)**: An Avro decode error on a specific message. Default Spark behavior: streaming query throws, whole micro-batch aborts, checkpoint stays put so the next attempt re-reads the same message and re-crashes.
3. **Spark sink (ClickHouse JDBC writer)**: A constraint violation, timeout, or ClickHouse restart in the middle of `foreachBatch`. Default behavior: exception propagates, Spark task retries per `spark.task.maxFailures`, then the whole streaming query fails.

Exactly one of these (validation via GX inside `foreachBatch`) has a DLQ path today, added by `add-data-governance` Phase 3. That leaves the other two uncovered.

There's also a secondary problem: the existing `{table}_dlq` topics carry a payload shape defined only by the GX gate's `with_gx_gate()` implementation. If we add sibling DLQs, we want them to share a common envelope so a single consumer (the future Streamlit triage page, a future replay tool) can read all of them.

This design covers all three failure surfaces and unifies the DLQ payload shape.

## Goals / Non-Goals

**Goals:**
- Every failure class that today either crashes the pipeline or drops the record silently gets a DLQ path.
- All DLQ topics share a common payload envelope so downstream tooling (Streamlit triage, alerts, future replay) is stage-agnostic.
- DLQ traffic is observable: a Grafana dashboard queries per-topic DLQ throughput; a Grafana alert fires when *any* `*_dlq` topic sees >0 messages in a 5-minute window.
- A Streamlit page lets a developer browse recent DLQ contents without shelling into Kafka.
- All configuration lands as spec requirements so `openspec validate` catches drift.

**Non-Goals:**
- **Automatic DLQ replay.** Bad data should be inspected, not silently retried. Replay tooling is a future change.
- **Cross-topic DLQ correlation.** Each stage owns its own DLQ. Correlating a Kafka Connect DLQ event with a downstream Spark sink DLQ event is out of scope — the timestamp + Kafka offset headers are enough for manual correlation.
- **Retry policy tuning inside Spark tasks.** `spark.task.maxFailures` stays at its default. DLQ is a *terminal* path — when a batch of valid rows can't be written to ClickHouse (network blip), Spark's built-in retry handles it; only when retries are exhausted does the DLQ path fire.
- **DLQ topic retention changes.** Phase 1 governance already declared `*_dlq` retention = 14 days. That policy applies to the new sibling DLQ topics too.
- **Schema-level DLQ for Apicurio Registry outages.** If Apicurio is down, Debezium can't publish anything (Avro serialize needs the registry); the connector fails cleanly. Not a DLQ scenario.

## Three Pillars

Aligned with the three failure surfaces.

### Pillar 1 — Kafka Connect DLQ (config-only)

**Tool choice:** Kafka Connect's built-in error handling (`errors.*` connector config).

**Behavior the spec will encode:**
- The Debezium PostgreSQL connector configuration in `data-platform/cdc/connectors/register-pg.json` SHALL declare:
  - `errors.tolerance=all` — do not fail the task on individual record errors.
  - `errors.deadletterqueue.topic.name=debezium_connect_dlq` — single topic across all three source tables (unlike the per-table DLQs used downstream; Kafka Connect only supports one DLQ topic per connector).
  - `errors.deadletterqueue.context.headers.enable=true` — record the original topic, partition, offset, exception class, and stack trace in Kafka headers on the DLQ message.
  - `errors.deadletterqueue.topic.replication.factor=1` — single-broker local dev.
  - `errors.log.enable=true`, `errors.log.include.messages=true` — also log to stderr for Loki central-logs correlation.
- Failure classes routed here: converter errors (Avro decode/encode fail, schema-registry lookup miss), transform errors (SMTs, none configured today), and per-record source errors from the Postgres connector.

**Where it plugs in (reuse, don't rebuild):**
- Kafka Connect ships this — no plugin install, no image rebuild.
- Topic `debezium_connect_dlq` auto-creates on first bad record (broker `auto.create.topics.enable=true` in local dev).

**Tradeoff:** All three source tables share one DLQ topic. Downstream tooling can partition on the `__connect.errors.topic` header if per-table triage is needed.

### Pillar 2 — Spark Sink DLQ (mirror of `with_gx_gate`)

**Tool choice:** Wrap `ClickHouseWriter.create_batch_writer_function` with a try/except that routes failing batches to `{table}_sink_dlq`.

**Behavior the spec will encode:**
- A new module `data-platform/streaming/spark/src/governance/error_handling.py` provides `with_sink_dlq(inner_writer, table)`, a foreachBatch wrapper.
- On `Exception` in the inner writer, the wrapper:
  - Serializes each row of the failing batch to JSON.
  - Adds `_error_class` (exception class name), `_error_message` (str(exception)), `_error_stage` (constant `"spark_sink"`).
  - Writes to `{table}_sink_dlq` via the existing Kafka producer plumbing already used by `with_gx_gate`.
  - Does NOT re-raise — the batch is considered handled once DLQ'd.
- Opt-in via env `ENABLE_SINK_DLQ=1` so dev environments that want the pre-existing crash-on-fail behavior are unaffected. Symmetric with `ENABLE_GX_GATE`.
- The two gates compose: `with_gx_gate(with_sink_dlq(inner_writer, table), table)`. GX filters invalid rows first (to `{table}_dlq`), sink DLQ catches ClickHouse write failures on the surviving rows (to `{table}_sink_dlq`).

**Where it plugs in:**
- `data-platform/streaming/spark/src/io/clickhouse_client.py::create_batch_writer_function` — add opt-in wrapping when `ENABLE_SINK_DLQ=1` is present.
- Reuses the Kafka producer path in the existing `with_gx_gate` implementation (`src/governance/quality.py::_write_dlq`) — extract the common producer helper.

**Tradeoff:** Sink DLQ swallows the exception, which means a persistent ClickHouse outage will silently DLQ everything until Spark's own back-pressure kicks in. Mitigation: the `dlq_traffic_present` alert (Pillar 3) fires the moment DLQ traffic starts.

### Pillar 3 — DLQ Observability

**Tool choice:** Grafana dashboard + Grafana Unified Alerting rule + Streamlit triage view.

**Behavior the spec will encode:**

**Grafana Central DLQ dashboard** (`infrastructure/docker/grafana/provisioning/dashboards/files/observability/central-dlq.json`):
- Panel: DLQ message rate per topic (`sum by (topic) (rate(kafka_topic_partition_current_offset{topic=~".+_dlq"}[5m]))` via kafka-exporter).
- Panel: Total DLQ messages by topic (bar chart).
- Panel: Latest DLQ log lines from producers (Loki query filtered on `container=~"debezium|ed-pyspark-jupyter"` + `|~ "DLQ"`).

**Grafana alert rule** in `infrastructure/docker/grafana/provisioning/alerting/infra-alerts.yml` (extends the existing 5 rules to 6):
- `dlq_traffic_present`: `sum by (topic) (increase(kafka_topic_partition_current_offset{topic=~".+_dlq"}[5m])) > 0`, `for: 1m`, `severity: warning`. Fires the moment any DLQ receives its first message.

**Streamlit DLQ Triage view** (`application/cdc-testing-ui/views/dlq_triage.py`):
- New tab in the Streamlit UI.
- Uses the existing `managers/kafka.py::consume_messages` with topic filter `pattern=".+_dlq"`.
- Table columns: `dlq_topic`, `_error_stage`, `_error_class`, `_error_message` (truncated), `key`, `first_seen`, `Full payload` (expander).
- Read-only. No replay button by design.

**Where it plugs in:**
- Dashboard + alert land in existing `observability` and `Observability Alerts` folders.
- Streamlit view registers in `application/cdc-testing-ui/app.py` route table.
- All three read from Kafka via existing infrastructure — no new services.

## Decisions

**Kafka Connect DLQ = one topic across all tables, Spark DLQs = one per table**
Kafka Connect only supports one DLQ per connector; enforcing per-table would need three connectors. Not worth the complexity. Spark side is different — `foreachBatch` runs per streaming query, so per-table DLQ topics fall out naturally and give better UX in the triage view.

**Payload envelope is JSON with `_error_*` fields, not Avro**
DLQ contents are human-diagnostic first, machine-consumed second. JSON stays readable in `kcat`, in Streamlit, and in Grafana's Loki panels. If we ever need schema evolution on DLQ payloads, the JSON structure with `_error_stage` discriminator supports it.

**Both Spark gates are opt-in via env vars**
Mirrors the existing `ENABLE_GX_GATE` pattern. Dev environments that want the pre-existing "fail loud" behavior (useful when developing a transformer) stay unaffected. Production sets both `ENABLE_GX_GATE=1` and `ENABLE_SINK_DLQ=1`.

**No automatic replay tooling in this change**
Manual triage in Streamlit is the intended workflow. Bad data should get eyes on it. A replay tool is a separate change once the triage workflow has been used enough to know what a good UX looks like.

**Reuse Grafana Unified Alerting, not Alertmanager**
Consistent with observability Phase 3. One less service.

## Risks / Trade-offs

**Silent sink DLQ during a real outage.** If ClickHouse is down for 20 minutes, `with_sink_dlq` will happily DLQ every batch. Mitigation: `dlq_traffic_present` alert (1-minute confirmation window) fires immediately. Additional mitigation: the alert routes to the default webhook contact point provisioned in Phase 3 observability, so it reaches wherever real alerts go.

**Kafka Connect DLQ headers can grow large.** Full stack traces in Kafka message headers. Kafka broker default `message.max.bytes=1048588` handles single-record traces fine, but if a downstream tool aggregates headers, it should be aware. Not a concern for local dev.

**DLQ topics count against Prometheus cardinality.** Each `{table}_sink_dlq` + `{table}_dlq` + `debezium_connect_dlq` = 7 new topic labels in Prometheus. Well under any cardinality concern.

**Two DLQs per table can create double-DLQ risk.** If GX passes a row and Spark's sink then rejects it, the row is DLQ'd exactly once (in `_sink_dlq`). If GX rejects a row, sink never sees it (in `_dlq`). Composable, no double-DLQ.

**Streamlit polling DLQ topics adds Kafka consumer group churn.** Same pattern the existing Streamlit Kafka monitor uses. Existing `governance.access_log` topic already receives Streamlit's startup events (from `add-data-governance` Phase 2). No new pressure.

**Debezium DLQ topic name collision.** If `debezium_connect_dlq` topic exists from a prior run under a different tenant, records may interleave. Local-dev-only; not addressed.

## Phased Rollout

Each phase independently shippable.

**Phase 1 — Kafka Connect DLQ (config-only)**
- Modify `data-platform/cdc/connectors/register-pg.json` with the 5 `errors.*` properties.
- Re-apply the connector via `make apply-pg-connector`.
- **Exit criteria:** `kafka-topics --list` shows `debezium_connect_dlq` after the first bad record (verify by temporarily setting `value.converter.schemas.enable=false` on an already-Avro topic to force a converter error, then reverting). Alternatively: connector remains RUNNING through a manually-introduced schema mismatch.

**Phase 2 — Spark sink DLQ**
- Add `src/governance/error_handling.py::with_sink_dlq`.
- Refactor `src/governance/quality.py::_write_dlq` into a shared helper `src/governance/dlq_producer.py` (both gates use it).
- Modify `ClickHouseWriter.create_batch_writer_function` to compose `with_sink_dlq` when `ENABLE_SINK_DLQ=1`.
- Add unit tests: `tests/spark/test_sink_dlq.py` (mock ClickHouse writer that raises, assert row lands in DLQ topic with correct envelope).
- **Exit criteria:** Test passes. Live smoke: `docker stop clickhouse`, run a Spark job with `ENABLE_SINK_DLQ=1`, insert into Postgres, verify rows appear in `customers_sink_dlq` topic. Restart ClickHouse.

**Phase 3 — DLQ observability**
- New `central-dlq.json` dashboard in `infrastructure/docker/grafana/provisioning/dashboards/files/observability/`.
- New `dlq_traffic_present` rule appended to `infrastructure/docker/grafana/provisioning/alerting/infra-alerts.yml`.
- **Exit criteria:** Dashboard renders. Force a bad record → alert fires within 1m + webhook receives POST.

**Phase 4 — Streamlit DLQ triage view**
- New `application/cdc-testing-ui/views/dlq_triage.py` reusing `managers/kafka.py`.
- Register route in `application/cdc-testing-ui/app.py`.
- Reuse pytest fixtures from `tests/streamlit/conftest.py` for a mocked-consumer test.
- **Exit criteria:** UI navigation to `DLQ Triage` shows recent rows from all DLQ topics; empty state renders correctly when no DLQ traffic.

## Requirements That Will Be Declared

New `openspec/specs/error-handling/spec.md` at archive time:

| Pillar | Requirement (kebab-name) | One-line summary |
|--------|--------------------------|------------------|
| 1 | `kafka-connect-dlq-config` | `register-pg.json` declares `errors.tolerance=all` + DLQ topic + headers enabled |
| 1 | `kafka-connect-dlq-topic` | `debezium_connect_dlq` topic auto-creates on first bad record; headers carry original topic/partition/offset/exception |
| 2 | `spark-sink-dlq-wrapper` | `with_sink_dlq(inner, table)` catches exceptions, writes to `{table}_sink_dlq`, does not re-raise |
| 2 | `spark-sink-dlq-envelope` | DLQ payload carries `_error_stage`, `_error_class`, `_error_message` alongside the original row JSON |
| 2 | `spark-sink-dlq-opt-in` | `ENABLE_SINK_DLQ=1` env var toggles the wrapper; default off preserves existing crash-on-fail behavior |
| 2 | `dlq-envelope-shared` | GX-gate DLQ (`with_gx_gate`) and sink DLQ (`with_sink_dlq`) share the `_error_*` envelope fields via `dlq_producer.emit()` |
| 3 | `central-dlq-dashboard` | Grafana `Observability` folder gains a "Central DLQ" dashboard with per-topic rate, totals, and latest producer logs |
| 3 | `dlq-traffic-alert-rule` | `dlq_traffic_present` fires when any `*_dlq` topic sees >0 messages in 5-minute window; 1m confirmation, warning severity |
| 4 | `streamlit-dlq-triage-view` | Streamlit `DLQ Triage` tab lists recent DLQ contents across all DLQ topics; read-only |

Nine requirements. Aligns with the 8-12 target used by prior changes.

## Cross-Capability Modifications

- **`cdc-pipeline`**: `debezium-connector-registration` scenario extended with `errors.*` block; `production-mode` scenario extended with the sink DLQ composition (`with_gx_gate(with_sink_dlq(...), table)`).
- **`data-governance`**: `dlq-on-validation-failure` payload-shape refined to reference the shared `dlq_producer` envelope (`_error_stage: "gx_validation"`, `_error_expectation: <name>`).
- **`observability`**: `infrastructure-alert-rules` scenario extended to include `dlq_traffic_present` in the minimum rule set.
- **`streamlit-ui`**: new requirement for the DLQ triage view.

No changes to `analytics`, `python-tooling`, or `infrastructure`.

## Out of Scope

- Automatic DLQ replay.
- Cross-topic DLQ correlation UI.
- Custom retention per DLQ topic (uses the shared 14-day policy from Phase 1 governance).
- DLQ export to ClickHouse for long-term analysis. Feasible via OTEL Collector's Kafka receiver → ClickHouse exporter, but out of this change.
- Retry-with-backoff for transient sink failures. Spark's built-in `spark.task.maxFailures` covers transient JDBC blips; only exhausted retries hit the DLQ.
- Handling DLQ producer failures (recursive DLQ). If the DLQ topic itself is unavailable, the wrapper logs at ERROR level and re-raises the original exception — falling back to the crash-on-fail behavior.
