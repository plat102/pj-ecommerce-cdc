## 0. Design (this turn)

- [x] 0.1 Write proposal.md
- [x] 0.2 Write design.md covering topic settings, wire-in position, doc surface
- [x] 0.3 Write tasks.md (this file)
- [x] 0.4 Write specs deltas: `error-handling` ADDED `dlq-topic-retention` + `dlq-topic-partitions-and-replication`; `infrastructure` MODIFIED `full-stack-startup` + `per-service-targets`
- [x] 0.5 User approves design direction before implementation begins

## 1. Phase 1 — Script + Makefile wire

- [x] 1.1 Create `scripts/setup_dlq_topics.sh` — bash script that defines the 7 DLQ topics as a hard-coded array, reads `DLQ_RETENTION_MS` / `DLQ_RETENTION_BYTES` env with the design defaults, and runs a two-pass loop: `kafka-topics --create --if-not-exists` for missing topics, then `kafka-configs --alter --add-config` on every topic for drift correction. Uses `set -euo pipefail`.
- [x] 1.2 Add `apply-dlq-topics` target to `Makefile` calling `./scripts/setup_dlq_topics.sh`.
- [x] 1.3 Wire `apply-dlq-topics` into `make up` — inserted immediately before `apply-pg-connector` so DLQ topics exist before the first bad record can route through the connector.
- [x] 1.4 `chmod +x scripts/setup_dlq_topics.sh` — mode 100755 committed.
- [x] 1.5 Updated `.env.example` with commented `DLQ_RETENTION_MS` / `DLQ_RETENTION_BYTES` placeholders and a note explaining the drift-correct semantics.

## 2. Phase 2 — Documentation

- [x] 2.1 Added "DLQ operations" section to `docs/observability.md` immediately before "Verify locally". 3 paragraphs: retention semantics + Loki cross-reference; emergency-raise via `DLQ_RETENTION_MS=... make apply-dlq-topics` (transient by design) with note on persisting via `.env`; drain semantics (delete+recreate, or wait retention out).

## 3. Phase 3 — Live smoke

- [~] 3.1 Cold-start smoke — **skipped**. Requires `make down` + `make up` which destroys all volumes (Postgres data, Kafka offsets, ClickHouse tables); the demo stack has active DLQ traffic from earlier smokes we want to preserve for the Streamlit view. Behavior is covered transitively by the idempotency and drift-correct smokes below: `make up` invokes `apply-dlq-topics` which is the same script we exercised.
- [x] 3.2 Retention config verification — for all 7 DLQ topics (`debezium_connect_dlq`, `{customers,products,orders}_cdc_dlq`, `{customers,products,orders}_cdc_sink_dlq`), `kafka-configs --describe` reports `retention.ms=604800000`, `retention.bytes=104857600`, `cleanup.policy=delete`.
- [x] 3.3 Idempotency smoke — second consecutive run of `./scripts/setup_dlq_topics.sh` exits 0 with "PASS 7 DLQ topics configured", no error output.
- [x] 3.4 Drift-correct smoke — manually altered `customers_cdc_dlq` to `retention.ms=99999`; ran the script; retention restored to `604800000`.
- [x] 3.5 Operator-override smoke — `DLQ_RETENTION_MS=2592000000 ./scripts/setup_dlq_topics.sh` set retention to 30 days across all 7 topics; subsequent run without the env var drifted it back to `604800000`.

## 4. Archive

- [ ] 4.1 Run `openspec validate --changes --specs` — all pass.
- [ ] 4.2 `openspec archive add-dlq-retention --yes` — merge deltas into main specs.
- [ ] 4.3 Verify main specs post-archive: `error-handling` gains `dlq-topic-retention` + `dlq-topic-partitions-and-replication` requirements; `infrastructure` MODIFIED as declared.
- [ ] 4.4 Tick post-archive tasks in the archived tasks.md.
