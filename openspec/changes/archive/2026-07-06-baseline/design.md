## Context

The ecommerce CDC platform demonstrates real-time change data capture from a PostgreSQL OLTP database to a ClickHouse OLAP store via Debezium, Kafka, and PySpark Structured Streaming. Everything runs locally under Docker Compose. The Makefile is the single entrypoint for all lifecycle operations.

## Goals / Non-Goals

**Goals:**
- Capture row-level changes (INSERT/UPDATE/DELETE) from three Postgres tables in near real-time
- Transform and deduplicate CDC events in Spark before writing to ClickHouse
- Expose live analytics through Grafana dashboards backed by ClickHouse views
- Provide a Streamlit UI to drive CDC events interactively for demo and testing

**Non-Goals:**
- Production-grade SLA or HA (single-node Kafka, local Spark, no replication)
- Multi-tenant or multi-environment deployment (single local stack only)
- Schema registry or Avro encoding (plain JSON Debezium serialization)
- Automated test suite (no test runner configured)

## Decisions

**ReplacingMergeTree for CDC deduplication**
Debezium emits multiple messages per row (insert, updates, delete). Rather than deduplicating in Spark (stateful streaming, complex), ClickHouse ReplacingMergeTree handles it: the engine keeps only the row with the highest `_version` per primary key. Queries use `FINAL` to materialize the latest state. This keeps Spark jobs stateless and simple.

**`_version` from Debezium `ts_ms`, `_deleted` from `op`**
`ts_ms` is a monotonically increasing millisecond timestamp from the Debezium envelope. It is used as `_version` to order events. The `op` field (`c`=create, `u`=update, `d`=delete, `r`=snapshot read) drives the `_deleted` flag (1 when `op = 'd'`, 0 otherwise).

**Debezium decimal encoding requires a custom UDF**
PostgreSQL DECIMAL/NUMERIC columns are serialized by Debezium as base64-encoded byte arrays with scale metadata. Spark receives these as binary values that cannot be cast to DecimalType directly. `decode_decimal_udf` in `src/utils/udfs.py` decodes base64 bytes using `int.from_bytes` and applies a fixed scale (2 for currency). Any new decimal column needs an equivalent UDF registered before the transformer runs.

**Layered Spark job architecture**
`BaseCDCJob` handles Spark session creation, Kafka reader initialization, ClickHouse writer setup, checkpoint management, and the debug/production sink switch. Concrete jobs (`CustomersCDCJob`, `ProductCDCJob`, `OrderCDCJob`) only implement `process()` returning a transformed DataFrame. Adding a new table requires creating `{table}_cdc_job.py` + `{table}_cdc_transformer.py` — no changes to the base class.

**Two Spark job patterns exist (legacy vs. new)**
`CDCProcessor` (customers) is the original monolithic class. Products and orders use the `BaseCDCJob` abstract subclass pattern. Both work. Long-term intent is to migrate customers to the abstract pattern.

**Modular Docker Compose (6 files)**
Services are split into db, kafka, debezium, spark, analytics, and ui compose files. This allows developers to start only the subset they need (e.g., `make up-db up-kafka`) without waiting for Spark or Grafana. The Makefile composes all 6 into `COMPOSE_ALL` for `make up`.

**`.env` lives in `infrastructure/docker/`, not repo root**
The Makefile uses `--env-file $(ENV_FILE)` and `include $(ENV_FILE)` to export all variables. Placing `.env` beside the compose files reduces the risk of accidentally committing it at the root and keeps infra config co-located with the infra files.

## Risks / Trade-offs

**Checkpoint corruption on schema change**
If a Spark job's output schema changes (column added, removed, or renamed) while the same `table_name` checkpoint is reused, the checkpoint metadata becomes invalid and the job will either fail with a schema mismatch or produce malformed ClickHouse rows. This is an operational footgun — the system does not enforce or detect it. Mitigation: delete `{CHECKPOINT_LOCATION}/{table_name}` before restarting after a schema change. Long-term fix: versioned checkpoint paths (e.g., `/checkpoints/orders_cdc/v2`) so a schema change picks a fresh path automatically. *(This used to be encoded as `Requirement: checkpoint-schema-invariant` in `cdc-pipeline/spec.md`; removed because it constrains the operator, not the system.)*

**`startingOffsets=latest` means no backfill on job restart**
Spark jobs start from the latest Kafka offset each time. Any CDC events produced while a job was stopped are permanently skipped. This is intentional for a demo context but unacceptable in production; would need `earliest` or stored offsets for production use.

**Hardcoded decimal scale**
`decode_decimal_udf` uses scale=2 for all decimal columns. A table with decimal columns at different scales (e.g., weight at scale 3) will silently produce wrong values. Each distinct scale requires a separate UDF variant.

**`make down` deletes all volumes**
There is no warning prompt. Running `make down` destroys Postgres data, Kafka offsets, Spark checkpoints, and ClickHouse data. Use `make stop` to preserve state between sessions.
