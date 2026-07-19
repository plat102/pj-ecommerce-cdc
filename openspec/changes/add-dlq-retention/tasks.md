## 0. Design (this turn)

- [x] 0.1 Write proposal.md
- [x] 0.2 Write design.md covering topic settings, wire-in position, doc surface
- [x] 0.3 Write tasks.md (this file)
- [x] 0.4 Write specs deltas: `error-handling` ADDED `dlq-topic-retention` + `dlq-topic-partitions-and-replication`; `infrastructure` MODIFIED `full-stack-startup` + `per-service-targets`
- [ ] 0.5 User approves design direction before implementation begins

## 1. Phase 1 — Script + Makefile wire

- [ ] 1.1 Create `scripts/setup_dlq_topics.sh` — bash script that:
  - Defines the DLQ topic list from D2 as a bash array.
  - Reads `DLQ_RETENTION_MS` (default `604800000`) and `DLQ_RETENTION_BYTES` (default `104857600`) from env.
  - For each topic: `docker exec kafka1 kafka-topics --bootstrap-server localhost:9092 --create --if-not-exists --topic <name> --partitions 1 --replication-factor 1 --config retention.ms=$DLQ_RETENTION_MS --config retention.bytes=$DLQ_RETENTION_BYTES --config cleanup.policy=delete`.
  - Second pass, for drift correction: `docker exec kafka1 kafka-configs --bootstrap-server localhost:9092 --entity-type topics --entity-name <name> --alter --add-config retention.ms=$DLQ_RETENTION_MS,retention.bytes=$DLQ_RETENTION_BYTES,cleanup.policy=delete`.
  - Exits non-zero on any topic-op failure (`set -e`).
- [ ] 1.2 Add `apply-dlq-topics` target to `Makefile` calling `./scripts/setup_dlq_topics.sh`. Ensure it can run standalone (stack must already be up).
- [ ] 1.3 Wire `apply-dlq-topics` into `make up` — call it after `docker-compose up -d` completes and Kafka is healthy, but before `apply-pg-connector`. Look at how `apply-pg-connector` is currently invoked in `up` and slot the new target immediately before it.
- [ ] 1.4 `chmod +x scripts/setup_dlq_topics.sh` and verify permission is committed.
- [ ] 1.5 Update `.env.example` with commented-out `DLQ_RETENTION_MS` and `DLQ_RETENTION_BYTES` placeholders so operators discover the override knobs.

## 2. Phase 2 — Documentation

- [ ] 2.1 Add "DLQ operations" section to `docs/observability.md` (3 paragraphs max):
  - Retention semantics: 7d / 100 MB defaults, cross-references to Loki retention.
  - Emergency-raise workflow: `DLQ_RETENTION_MS=2592000000 make apply-dlq-topics` for a 30-day forensic window, with the drift-back caveat.
  - Drain semantics: no built-in drain; delete + re-create (or wait retention out) is the only zeroing path this change offers.

## 3. Phase 3 — Live smoke

- [ ] 3.1 Cold-start smoke: `make down` → `make up`, then `docker exec kafka1 kafka-topics --list --bootstrap-server localhost:9092 | grep -c _dlq` returns 7 before any bad record has occurred.
- [ ] 3.2 Retention config verification: for each of the 7 topics, run `docker exec kafka1 kafka-configs --bootstrap-server localhost:9092 --entity-type topics --entity-name <name> --describe` and confirm `retention.ms=604800000`, `retention.bytes=104857600`, `cleanup.policy=delete` are present.
- [ ] 3.3 Idempotency smoke: run `make apply-dlq-topics` a second time immediately — exit 0, no diff.
- [ ] 3.4 Drift-correct smoke: manually alter one topic (`kafka-configs --alter --add-config retention.ms=99999`), run `make apply-dlq-topics`, verify retention restored.
- [ ] 3.5 Operator-override smoke: `DLQ_RETENTION_MS=2592000000 make apply-dlq-topics` → verify retention now 30d; then `make apply-dlq-topics` (no env) → verify drift-back to 7d.

## 4. Archive

- [ ] 4.1 Run `openspec validate --changes --specs` — all pass.
- [ ] 4.2 `openspec archive add-dlq-retention --yes` — merge deltas into main specs.
- [ ] 4.3 Verify main specs post-archive: `error-handling` gains `dlq-topic-retention` + `dlq-topic-partitions-and-replication` requirements; `infrastructure` MODIFIED as declared.
- [ ] 4.4 Tick post-archive tasks in the archived tasks.md.
