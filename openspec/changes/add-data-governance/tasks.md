## 0. Design (this turn)

- [x] 0.1 Write DESIGN.md covering four pillars, tool choices, tradeoffs, and phased rollout
- [x] 0.2 Write PROPOSAL.md describing the new `data-governance` capability and cross-capability deltas
- [x] 0.3 User approves design direction before implementation begins

## 1. Phase 1 — Retention & Lifecycle (Pillar 4)

- [x] 1.1 Add TTL clauses to `infrastructure/docker/clickhouse/create_tables.sql` anchored on `toDateTime(_version / 1000)` (Debezium `ts_ms`): tombstones `WHERE _deleted = 1` expire at `+ INTERVAL 90 DAY`, active rows at `+ INTERVAL 2 YEAR`. No new column required.
- [x] 1.2 Declare explicit Kafka topic retention (`pg.public.*` = 7d, `governance.access_log` = 30d, `*_dlq` = 14d) — see `data-platform/governance/retention/apply-kafka-topic-retention.sh`
- [x] 1.3 Adopt versioned checkpoint paths in `BaseCDCJob`: `{CHECKPOINT_LOCATION}/{table_name}/v1`. Hard-code `v1` in Phase 1 — the `schema_version` integer becomes meaningful in Phase 3 when Schema Registry lands, at which point `make cdc-rotate-checkpoint` (task 1.4) migrates each job to `v2`.
- [x] 1.4 Add `make cdc-rotate-checkpoint TABLE=<name>` target
- [x] 1.5 Write `data-platform/governance/retention/postgres-archive.sql` for `orders` → `orders_archive`
- [x] 1.6 Update `specs/data-governance/spec.md` in this change dir — add `## ADDED Requirements` for `clickhouse-ttl-policies`, `kafka-topic-retention`, `postgres-archival-policy`, `checkpoint-versioned-paths` (decomposed from the current `ttl-retention` placeholder)
- [x] 1.7 Create `specs/analytics/spec.md` in this change dir with `## MODIFIED Requirements` extending `clickhouse-table-engine` to include the TTL clause semantics from task 1.1

## 2. Phase 2 — PII / Access Control / Audit (Pillar 3)

- [x] 2.1 Add `hash_pii_udf` to `data-platform/streaming/spark/src/utils/udfs.py`
- [x] 2.2 Apply hashing/tokenization in `customer_transformer.py`
- [x] 2.3 Add `PII_SALT` to `.env.example` and document salt rotation procedure
- [x] 2.4 Create ClickHouse `analyst_readonly` role + row policies (in `infrastructure/docker/clickhouse/create_tables.sql`); add `CLICKHOUSE_ANALYST_PASSWORD` to `.env.example`; update `infrastructure/docker/grafana/provisioning/datasources/clickhouse.yml` to set `username: analyst_readonly` and reference the new env var for the password
- [x] 2.5 Create `governance.access_log` Kafka topic; emit a startup event from each Spark job and the Streamlit Kafka monitor
- [x] 2.6 Update `specs/data-governance/spec.md` in this change dir — add `## ADDED Requirements` for `pii-hashing-customers-email`, `pii-tokenization-customers-name`, `clickhouse-rbac-roles`, `cdc-consumer-access-log` (decomposed from the current `pii-classification` placeholder)
- [x] 2.7 Update `specs/analytics/spec.md` in this change dir with a `## MODIFIED Requirements` block covering the new `analyst_readonly` role, row policies, and Grafana datasource credential change

## 3. Phase 3 — Schema Registry + Data Quality (Pillar 1)

- [x] 3.1 Add `schema-registry` service to `infrastructure/docker/docker-compose.kafka.yml`
- [x] 3.2 Change Debezium connector to use `AvroConverter` with Schema Registry URL
- [x] 3.3 Add Avro + Schema Registry client jars to `submit_job.sh`
- [x] 3.4 Write GX expectation suites for `customers`, `products`, `orders`
- [x] 3.5 Wrap `create_batch_writer_function` to run GX before write; route failures to `{table}_dlq`
- [x] 3.6 Wire `data_freshness` view to Grafana alerting (10-minute SLO)
- [x] 3.7 Update `specs/data-governance/spec.md` in this change dir — add `## ADDED Requirements` for `schema-registry-publication`, `gx-batch-validation`, `dlq-on-validation-failure`, `freshness-slo-and-alert` (decomposed from the `schema-contract` and `data-quality-gate` placeholders)
- [x] 3.8 Create `specs/cdc-pipeline/spec.md` in this change dir with `## MODIFIED Requirements` covering the Avro converter change in `register-pg.json`, the GX validation step wrapping `create_batch_writer_function`, and the OpenLineage listener addition to `submit_job.sh`
- [x] 3.9 Plan and execute Avro migration: drain JSON topics, delete old checkpoints, switch over (plan documented in `data-platform/governance/schema-registry/avro-migration.md`; execution deferred to when the live stack is available — this task can be verified by running through the runbook, but code changes for the switch itself are all in this change)

## 4. Phase 4 — Metadata & Lineage Catalog (Pillar 2)

- [ ] 4.1 Add `docker-compose.governance.yml` with OpenMetadata + MySQL + Elasticsearch
- [ ] 4.2 Add `up-governance` / `down-governance` / `logs-governance` Make targets
- [ ] 4.3 Write OpenMetadata ingestion configs for Postgres, Kafka, ClickHouse
- [ ] 4.4 Enable OpenLineage Spark listener in `submit_job.sh`
- [ ] 4.5 Populate column descriptions + owner tags on the three CDC tables
- [ ] 4.6 Update `specs/data-governance/spec.md` in this change dir — add `## ADDED Requirements` for `openmetadata-ingestion`, `openlineage-spark-emission`, `column-documentation-coverage` (decomposed from the `lineage-emission` placeholder)
- [ ] 4.7 Create `specs/infrastructure/spec.md` in this change dir with `## MODIFIED Requirements` covering the new `docker-compose.governance.yml`, the `up-governance` / `down-governance` / `logs-governance` Make targets, and the Schema Registry addition to `docker-compose.kafka.yml`

## 5. Archive

- [ ] 5.1 Run `make spec-validate` and ensure all checks pass
- [ ] 5.2 Merge each `specs/<capability>/spec.md` file from this change dir into the corresponding `openspec/specs/<capability>/spec.md`, applying `## MODIFIED Requirements` sections into the existing requirement blocks
- [ ] 5.3 Merge `specs/data-governance/spec.md` into a new `openspec/specs/data-governance/spec.md`, decomposing the five broad placeholder requirements into the 15 phase-scoped requirements listed in `design.md` § "Requirements That Will Be Declared"
- [ ] 5.4 Move `openspec/changes/add-data-governance/` to `openspec/changes/archive/add-data-governance/`
