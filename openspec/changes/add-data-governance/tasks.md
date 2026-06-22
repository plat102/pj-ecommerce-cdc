## 0. Design (this turn)

- [x] 0.1 Write DESIGN.md covering four pillars, tool choices, tradeoffs, and phased rollout
- [x] 0.2 Write PROPOSAL.md describing the new `data-governance` capability and cross-capability deltas
- [ ] 0.3 User approves design direction before implementation begins

## 1. Phase 1 — Retention & Lifecycle (Pillar 4)

- [ ] 1.1 Add TTL clauses to `infrastructure/docker/clickhouse/create_tables.sql` (90d tombstones, 2y active rows, anchored on `event_time`)
- [ ] 1.2 Declare explicit Kafka topic retention (`pg.public.*` = 7d, `governance.access_log` = 30d, `*_dlq` = 14d)
- [ ] 1.3 Adopt versioned checkpoint paths (`{table}/v{schema_version}`) in `BaseCDCJob`
- [ ] 1.4 Add `make cdc-rotate-checkpoint TABLE=<name>` target
- [ ] 1.5 Write `data-platform/governance/retention/postgres-archive.sql` for `orders` → `orders_archive`
- [ ] 1.6 Write `deltas/data-governance.md` ADDED requirements: `clickhouse-ttl-policies`, `kafka-topic-retention`, `postgres-archival-policy`, `checkpoint-versioned-paths`
- [ ] 1.7 Write `deltas/analytics.md` MODIFIED requirement for TTL semantics

## 2. Phase 2 — PII / Access Control / Audit (Pillar 3)

- [ ] 2.1 Add `hash_pii_udf` to `data-platform/streaming/spark/src/utils/udfs.py`
- [ ] 2.2 Apply hashing/tokenization in `customer_transformer.py`
- [ ] 2.3 Add `PII_SALT` to `.env.example` and document salt rotation procedure
- [ ] 2.4 Create ClickHouse `analyst_readonly` role + row policies; point Grafana datasource at it
- [ ] 2.5 Create `governance.access_log` Kafka topic; emit a startup event from each Spark job and the Streamlit Kafka monitor
- [ ] 2.6 Write `deltas/data-governance.md` ADDED requirements: `pii-hashing-customers-email`, `pii-tokenization-customers-name`, `clickhouse-rbac-roles`, `cdc-consumer-access-log`
- [ ] 2.7 Write `deltas/analytics.md` MODIFIED requirement for RBAC

## 3. Phase 3 — Schema Registry + Data Quality (Pillar 1)

- [ ] 3.1 Add `schema-registry` service to `infrastructure/docker/docker-compose.kafka.yml`
- [ ] 3.2 Change Debezium connector to use `AvroConverter` with Schema Registry URL
- [ ] 3.3 Add Avro + Schema Registry client jars to `submit_job.sh`
- [ ] 3.4 Write GX expectation suites for `customers`, `products`, `orders`
- [ ] 3.5 Wrap `create_batch_writer_function` to run GX before write; route failures to `{table}_dlq`
- [ ] 3.6 Wire `data_freshness` view to Grafana alerting (10-minute SLO)
- [ ] 3.7 Write `deltas/data-governance.md` ADDED requirements: `schema-registry-publication`, `gx-batch-validation`, `dlq-on-validation-failure`, `freshness-slo-and-alert`
- [ ] 3.8 Write `deltas/cdc-pipeline.md` MODIFIED requirements for the new validation/lineage steps and Avro converter
- [ ] 3.9 Plan and execute Avro migration: drain JSON topics, delete old checkpoints, switch over

## 4. Phase 4 — Metadata & Lineage Catalog (Pillar 2)

- [ ] 4.1 Add `docker-compose.governance.yml` with OpenMetadata + MySQL + Elasticsearch
- [ ] 4.2 Add `up-governance` / `down-governance` / `logs-governance` Make targets
- [ ] 4.3 Write OpenMetadata ingestion configs for Postgres, Kafka, ClickHouse
- [ ] 4.4 Enable OpenLineage Spark listener in `submit_job.sh`
- [ ] 4.5 Populate column descriptions + owner tags on the three CDC tables
- [ ] 4.6 Write `deltas/data-governance.md` ADDED requirements: `openmetadata-ingestion`, `openlineage-spark-emission`, `column-documentation-coverage`
- [ ] 4.7 Write `deltas/infrastructure.md` MODIFIED requirements for governance Make targets and compose file

## 5. Archive

- [ ] 5.1 Run `make spec-validate` and ensure all checks pass
- [ ] 5.2 Apply each delta into `openspec/specs/<capability>/spec.md`
- [ ] 5.3 Create `openspec/specs/data-governance/spec.md` from accumulated ADDED requirements
- [ ] 5.4 Move `openspec/changes/add-data-governance/` to `openspec/changes/archive/add-data-governance/`
