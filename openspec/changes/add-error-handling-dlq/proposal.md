## Why

The CDC pipeline has exactly one dead-letter path today: `dlq-on-validation-failure` from `add-data-governance` Phase 3, which catches Great Expectations validation failures inside Spark's `foreachBatch` and routes bad rows to `{table}_dlq`. That covers one narrow failure class — column-level DQ violations after Spark has already parsed the record.

Everything else fails silently or crashes the pipeline:

- **Kafka Connect deserialization/converter errors**: Debezium currently uses default error handling (`errors.tolerance=none`). A malformed WAL entry, a schema-registry outage mid-flight, or an incompatible schema evolution takes the whole connector `FAILED` state.
- **Spark sink failures**: `create_batch_writer_function` in `src/io/clickhouse_client.py` catches ClickHouse write errors and re-raises. A JDBC constraint violation, a network blip, or a ClickHouse restart kills the batch — retry policy is "let Spark re-consume from checkpoint, hope it works this time".
- **Spark source parse errors**: If a message on `pg.public.*` has a schema mismatch after an evolution, the Avro decoder throws inside the streaming query. No isolation of the bad record — the whole micro-batch aborts.
- **No DLQ observability**: even for the GX-gate DLQ that exists, there is no dashboard, no alert on DLQ traffic, and no way to browse quarantined rows without shelling into Kafka.

This proposal closes the gap by adding DLQ coverage across all three CDC pipeline stages and by adding DLQ-aware observability.

## What Changes

- Add a new `error-handling` OpenSpec capability owning DLQ semantics across the pipeline: which topics exist, what payload shape they carry, what triggers a DLQ write, and how DLQs are observed and drained.
- MODIFY existing capabilities where DLQ behavior touches them:
  - **`cdc-pipeline`**: Debezium connector gains Kafka Connect built-in DLQ (`errors.tolerance=all`, `errors.deadletterqueue.topic.name=debezium_connect_dlq`). Spark's `ClickHouseWriter.create_batch_writer_function` gains a sink-error DLQ wrapper mirroring the existing `with_gx_gate` pattern; failing batches route rows to `{table}_sink_dlq` with the exception message.
  - **`data-governance`**: `dlq-on-validation-failure` (Phase 3 GX gate) already exists — SPEC-only refinement to align its payload shape with the new sibling DLQ topics so a single downstream consumer can read all of them.
  - **`observability`**: adds a Central DLQ dashboard querying Kafka via `kafka-exporter` topic metrics + Loki logs from DLQ producers, plus an alert rule `dlq_traffic_present` firing when any `*_dlq` topic sees >0 messages in 5 minutes.
  - **`streamlit-ui`**: adds a `DLQ Triage` page listing recent quarantined rows with columns `dlq_topic`, `error_class`, `key`, `payload`, `first_seen`.
- Phased rollout (see DESIGN.md): Kafka Connect DLQ → Spark sink DLQ → observability (dashboard + alert) → Streamlit triage page. Each phase independently shippable.

## Capabilities

### New Capabilities
- `error-handling`: Owns DLQ topics, payload shape, producer wrapping across Kafka Connect + Spark, and the observability of quarantined data. Boundary with `data-governance`: data-governance owns *what makes a row invalid* (GX suites); error-handling owns *what happens after a row is declared bad*.

### Modified Capabilities
- `cdc-pipeline`: `debezium-connector-registration` gains `errors.*` config; `production-mode` wraps the sink writer with the new DLQ gate.
- `data-governance`: `dlq-on-validation-failure` scenarios refine payload-shape guarantees so all DLQ producers share a common envelope.
- `observability`: `infrastructure-alert-rules` gains `dlq_traffic_present`; new Central DLQ dashboard.
- `streamlit-ui`: gains a DLQ triage view.

## Impact

- Adds `openspec/changes/add-error-handling-dlq/{DESIGN.md,PROPOSAL.md,TASKS.md}` plus delta specs for `error-handling` (new), `cdc-pipeline`, `data-governance`, `observability`, `streamlit-ui`.
- Future implementation will: modify `data-platform/cdc/connectors/register-pg.json` with `errors.*` block; modify `data-platform/streaming/spark/src/io/clickhouse_client.py` to wrap `create_batch_writer_function` with a sink DLQ; add a new `data-platform/streaming/spark/src/governance/error_handling.py` (`with_sink_dlq()` mirror of `with_gx_gate`); add Grafana Central DLQ dashboard JSON + alert rule; add `application/cdc-testing-ui/views/dlq_triage.py` querying Kafka via existing `managers/kafka.py`.
- No changes to source schema, transformer logic, or ClickHouse table definitions — this is a wrapping layer around existing code paths.
- Non-goals include automatic DLQ replay (manual by design — bad data should be inspected, not silently retried), cross-topic DLQ correlation (each stage owns its own DLQ), and DLQ retention beyond the existing 14-day topic policy set in Phase 1 governance.
