## Context

`add-error-handling-dlq` introduced 8 DLQ topics but left retention entirely to Kafka broker defaults. The demo stack uses `confluentinc/cp-kafka:7.5.0` in KRaft-less mode via Zookeeper; the broker's `log.retention.hours` is inherited from the Docker image default (168 hours = 7 days) but `log.retention.bytes=-1` means no size cap. Combined with the DLQ Triage view that consumes from `earliest` for the 5-min window filter, this makes the DLQ topics grow linearly with time and cold-start slowness with them.

The three touch-points that matter:
- **Kafka broker** does not know these topics need special treatment until we tell it.
- **Debezium connector** and **Spark sink wrapper** auto-produce to DLQ topics that don't exist yet; broker `auto.create.topics.enable=true` handles creation, but the created topic inherits broker defaults, not what we want.
- **Streamlit DLQ Triage** and **`central-dlq` Grafana dashboard** query all `*_dlq` topics uniformly, so any per-topic knob has to be applied consistently or the observability layer misrepresents the DLQ state.

Two natural approaches:

1. Set broker-level `log.retention.hours` + `log.retention.bytes` lower and let auto-create pick them up. **Rejected**: this pollutes non-DLQ topics too (`pg.public.*`, `debezium_connect_{configs,offsets,statuses}`) and breaks the CDC replay guarantee for real business data.
2. Pre-create DLQ topics with per-topic overrides. **Chosen**: aligns retention with the DLQ semantic (short-lived triage buffer) without touching business-data retention.

## Goals / Non-Goals

**Goals:**
- Every `*_dlq` topic in the stack has explicit `retention.ms` and `retention.bytes` overrides applied on stack startup.
- Idempotent: `make up` can run 10 times, topic config remains what we declared.
- Reproducible defaults + easy operator override (env vars for temporary post-incident retention bumps).
- Observable: the retention config is queryable via the Kafka Admin API so Grafana can eventually surface it.
- Zero impact on business data topics.

**Non-Goals:**
- Automatic archive/tiered storage on retention expiry — the demo stack has no cold tier, and re-adding expired DLQ records is a Phase-3 replay concern (a future `add-dlq-replay` change).
- Compaction-based retention (`cleanup.policy=compact`) — DLQ is an event log; compaction would silently drop distinct failures that share a Kafka key.
- Per-topic distinct retention. Every DLQ gets the same treatment; if a specific DLQ needs longer retention for a diagnosed incident, the operator raises it via the script's env vars and lets it drift-correct back on next boot.
- Ripping out Kafka's `auto.create.topics.enable=true`. Even after pre-creation, that fallback stays useful for future DLQ additions (e.g. a new source connector).

## Decisions

### D1. Kafka topic settings

| Setting | Value | Rationale |
|---|---|---|
| `retention.ms` | `604800000` (7 days) | Matches Loki `retention_period: 168h` set in `add-infra-observability` Phase 1. Operators who cross-reference DLQ Triage with Loki logs get symmetric visibility windows. |
| `retention.bytes` | `104857600` (100 MB) | Bounds worst-case disk pressure at 8 × 100 MB = 800 MB shared with the observability stack (700 MB) inside the ~2 GB DLQ+observability budget. |
| `cleanup.policy` | `delete` | Time-based expiry. Compaction would collapse distinct errors sharing the same Kafka key (all `spark_sink` failures on `products_cdc` share `key="products_cdc"`). |
| `min.insync.replicas` | not set | Broker default; single-broker dev cluster makes ISR discussion moot. |
| `replication.factor` | `1` | Explicit — matches the Debezium `errors.deadletterqueue.topic.replication.factor` we set in `add-error-handling-dlq` Phase 1. |
| `partitions` | `1` | Single-partition is enough for DLQ throughput; also makes the Streamlit consumer's ordering guarantees trivial. |

Overrideable via env vars `DLQ_RETENTION_MS`, `DLQ_RETENTION_BYTES` — the script reads these with the values above as defaults.

### D2. Topic list source of truth

Hard-coded array in `scripts/setup_dlq_topics.sh`:

```
DLQ_TOPICS=(
  debezium_connect_dlq
  customers_cdc_dlq products_cdc_dlq orders_cdc_dlq
  customers_cdc_sink_dlq products_cdc_sink_dlq orders_cdc_sink_dlq
)
```

**Rejected alternative**: dynamic discovery via `kafka-topics --list | grep _dlq` on each boot. That only works after topics exist, defeats the whole point of pre-creation, and would flap on a fresh stack where no DLQ has been produced to yet.

The list stays in sync with two other lists:
- `application/cdc-testing-ui/views/dlq_triage.py::DLQ_TOPICS` (Streamlit consumer)
- Grafana `central-dlq.json` topic regex `.+_dlq` (implicit match; safe as long as no *non-DLQ* topic happens to end in `_dlq`, which is our convention anyway)

We accept this drift risk because there are only 3 places, each authored per change, and the retention spec has a scenario that will fail loudly if a new DLQ topic gets added without a matching entry.

### D3. Script mechanics

- Runs inside the `kafka1` container via `docker exec kafka1 kafka-topics --create ... --if-not-exists`, so the script has no host-side kafka-client dependency.
- Two-pass: first pass `--create --if-not-exists` (idempotent creation), second pass `--alter --config retention.ms=... --config retention.bytes=...` (drift-correct existing topics).
- Exits non-zero if any topic-level operation fails, so `make up` visibly breaks instead of silently proceeding with wrong retention.

### D4. Wire-in position in `make up`

`make up` currently sequences roughly: docker-compose up → wait-for-kafka-healthy → `make apply-pg-connector`. The new target `apply-dlq-topics` slots between kafka-healthy and connector-apply. Rationale: at connector-apply time we want the `debezium_connect_dlq` topic already sized correctly. For Spark-sink DLQs, timing is less critical (spark jobs launch on demand), but doing all 7 in one shot keeps operator model simple ("stack up = every DLQ configured").

**Rejected**: run the script inside the Kafka container's healthcheck. That would over-invoke it on every healthcheck cycle and pollute logs.

**Rejected**: run it as a compose `depends_on: service_completed_successfully` init container. Too heavy for one `kafka-topics --alter` invocation; adds a new container to `docker ps`.

### D5. Documentation surface

New section in `docs/observability.md` titled "DLQ operations", covering:

1. What retention means for DLQ triage: after 7 days a quarantined record is gone forever; if you need longer, bump retention *before* the DLQ starts filling.
2. Emergency-raise workflow: `DLQ_RETENTION_MS=2592000000 make apply-dlq-topics` (30 days) and note that this drift-corrects itself back on next boot.
3. When to drain vs escalate: a drain isn't offered by this change; if you need to zero a DLQ, delete + re-create the topic (or wait retention out). Escalation = the underlying issue in Kafka Connect / GX / Spark sink.

Keep it three paragraphs max. The runbook lives in observability.md rather than a new dedicated file because DLQ *is* an observability concern and operators land in that doc first.

## Risks / Trade-offs

- **[Risk] New DLQ added to code without matching entry in the script**  →  Mitigation: the retention spec includes a scenario that asserts every topic matching `.+_dlq` on the broker has the required retention config; a smoke run of `kafka-configs --describe --all-topics-with-configs` catches drift. Post-change, review checklist for `add-*-dlq` changes gains an item "update `scripts/setup_dlq_topics.sh` + `dlq_triage.py::DLQ_TOPICS`".
- **[Risk] Operator raises `DLQ_RETENTION_MS` for forensics and forgets; next `make up` silently drift-corrects back**  →  Mitigation: docs section explicitly notes this behavior; the drift-back is a feature (prevents accidental permanent bumps), not a bug. If operators need durable overrides, they edit `.env` where the override persists across `make up` runs.
- **[Risk] 100 MB per topic is too small for a real incident**  →  Mitigation: the env-var override path exists; also, the alert `dlq_traffic_present` (from Phase 3) fires within 1 minute of the first bad record, so the operator gets 7 days of context long before the size cap becomes constraining for typical triage.
- **[Trade-off] Delete-not-compact means duplicate errors count against size**  →  Accepted: DLQ triage cares about *distinct* failures, but the wire semantic is "every message = one failure event"; compacting would obscure repeat-fire patterns operators need to see. Grafana `central-dlq` dashboard already shows per-topic *rate*, which surfaces the repeat pattern separately from the raw count.
- **[Trade-off] 1 partition = no parallelism for DLQ consumers**  →  Accepted: DLQ throughput is by definition low; the Streamlit view is single-consumer; even under a "everything's failing" scenario, 1 partition at 100 MB caps at ~5-6k messages, well within a single consumer's read budget.
