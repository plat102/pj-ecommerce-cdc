# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## What this project is

End-to-end Change Data Capture demo: PostgreSQL → Debezium → Kafka → PySpark Structured Streaming → ClickHouse → Grafana, plus a Streamlit UI to drive CDC events for testing. Everything runs locally via Docker Compose; the Makefile is the canonical entrypoint.

## Common commands

All orchestration goes through the Makefile, which composes six `docker-compose.*.yml` files in `infrastructure/docker/` under project name `ecommerce-cdc`. Before running anything, `.env` must exist at `infrastructure/docker/.env` (copy from `.env.example`).

Stack lifecycle:
- `make up` — start the full stack (db + kafka + debezium + ui + spark + analytics) and auto-register the Postgres Debezium connector
- `make down` — stop and remove containers **and volumes** (destructive)
- `make stop` / `make start` — preserve volumes
- `make quick-start` — `up` + wait + apply connector + generate demo data
- `make status` / `make logs`

Per-service variants exist for each group: `up-db`, `up-kafka`, `up-debezium`, `up-spark`, `up-analytics`, `up-ui` (and matching `down-*`, `logs-*`, `sh-*`).

Debezium connector:
- `make apply-pg-connector` — POSTs `data-platform/cdc/connectors/register-pg.json` to `http://localhost:8083/connectors`
- `make check-connector` / `make list-connectors` / `make restart-connector` / `make delete-connector`

CDC Spark jobs (run inside the `ed-pyspark-jupyter` container):
- `make cdc-run` — customers job, debug mode (console sink)
- `make cdc-run-prod` — customers job, production mode (ClickHouse sink)
- `make cdc-run-products` / `cdc-run-products-prod`
- `make cdc-run-orders` / `cdc-run-orders-prod`
- `make cdc-run-all` / `cdc-run-all-prod` — start customers, products, orders in background
- `make cdc-stop` — `pkill` spark-submit/pyspark inside the Spark container
- `make cdc-force-stop` — SIGKILL + restart the Spark container
- `make cdc-status`

The underlying chain: `scripts/run_cdc.sh` → `docker exec ed-pyspark-jupyter` → `data-platform/streaming/spark/scripts/submit_job.sh` → `spark-submit apps/run_cdc_job.py --job-type {customers|products|orders} [--debug]`. To submit ad-hoc apps: `make spark-submit APP=your-app.py` (path is relative to `/home/jupyter/src-streaming/`).

Streamlit UI:
- `make up-ui` (Docker) — http://localhost:8501
- `make run-ui-local` — host Python, requires active venv
- `make demo-data` — populate Postgres with sample rows

Dashboards:
- `make sync-dashboards` — copies JSONs from `data-platform/dashboards/grafana/` into Grafana provisioning
- `make reload-grafana` — sync + restart Grafana container

Local Python env:
- `make uv-sync` — creates `./.venv` from `pyproject.toml` + `uv.lock` (main + dev groups). No manual activation needed for `make` targets; they use `uv run` internally. For interactive work: `. .venv/bin/activate` or prefix commands with `uv run`.
- `make test` — runs `uv run pytest` (exit code 5 "no tests collected" is mapped to 0).
- `make uv-clean` — removes `.venv/`, `uv.lock`, and any stale `venv/`.

Shell access:
- `make sh-pg`, `make sh-kafka`, `make sh-debezium`, `make sh-spark`, `make clickhouse-client`

## Architecture

### Pipeline
```
Postgres → Debezium → Kafka (topics pg.public.{customers,orders,products})
       → Spark Structured Streaming (per-table jobs)
       → ClickHouse (ReplacingMergeTree CDC tables + analytics views)
       → Grafana
```
Streamlit UI talks directly to Postgres (writes that Debezium captures) and to Kafka (read-only monitor view).

### Repo layout
- `application/cdc-testing-ui/` — Streamlit app. `app.py` is the entry; routes to page modules under `views/`. `managers/` holds Postgres/Kafka clients; `config/settings.py` centralizes connection settings.
- `data-platform/cdc/connectors/register-pg.json` — Debezium connector definition (topics, table whitelist, snapshot mode).
- `data-platform/streaming/spark/` — PySpark code.
  - `apps/run_cdc_job.py` — single entry point; `--job-type` dispatches to one of three job classes.
  - `src/jobs/` — `base_job.py` → `base_streaming_job.py` → `base_cdc_job.py` (handles Spark session, Kafka reader, ClickHouse writer, checkpointing, console vs production sink switch). Concrete jobs (`customers_cdc_job.py`, `product_cdc_job.py`, `order_cdc_job.py`) subclass `BaseCDCJob` and only implement `process()`.
  - `src/transformations/` — `kafka_parser.py` parses Debezium envelopes; per-table transformers handle table-specific schema and the `_version`/`_deleted` columns used by ClickHouse `ReplacingMergeTree` for deduplication.
  - `src/io/` — `kafka_client.py` (reader), `clickhouse_client.py` (`create_batch_writer_function` is what `foreachBatch` invokes).
  - `src/schemas/cdc_schemas.py` — Spark `StructType`s for Debezium payload shapes.
  - `src/utils/udfs.py` — includes `decode_decimal_udf` for Debezium's base64-encoded `DECIMAL`/`NUMERIC` values (a known gotcha; see README).
  - `src/config/app_config.py` — `AppConfig` reads env vars: `KAFKA_SERVERS`, `CLICKHOUSE_*`, `SPARK_*`, `CHECKPOINT_LOCATION`, `TRIGGER_INTERVAL`, `DEBUG_MODE`. Defaults assume in-container hostnames (`kafka1:9092`, `clickhouse:8123`).
- `data-platform/dashboards/` — source-of-truth Grafana JSON dashboards and ClickHouse analytics view SQL. `sync_dashboards.sh` copies these into the Grafana provisioning mount.
- `infrastructure/docker/` — six compose files split by service group; the Makefile composes them together. Service-specific configs live in subfolders (`postgres/`, `kafka/`, `clickhouse/create_tables.sql`, `grafana/provisioning/`, etc.).
- `infrastructure/terraform/` — Azure VM deployment (see `docs/deploy_azure_vm.md`).
- `scripts/` — host-side wrappers (`run_cdc.sh`, `setup_simple_analytics.sh`, `sync_dashboards.sh`).

### Job model
Each CDC job is a subclass of `BaseCDCJob`. The base class:
- creates the Spark session with Kafka + ClickHouse JDBC packages,
- reads from a Kafka topic with `startingOffsets=latest`,
- in `--debug` mode writes to console; otherwise writes via `foreachBatch` to ClickHouse with checkpoint at `{checkpoint_location}/{table_name}`.
Subclasses implement `process()` to return the transformed `DataFrame`. The dispatcher in `apps/run_cdc_job.py` calls `job.start_streaming(process_func=job.process, table_name="...")` then `wait_for_termination()`.

### CDC deduplication
ClickHouse target tables use `ReplacingMergeTree` keyed on `_version` (sourced from Debezium `ts_ms`) and carry a `_deleted` flag. Queries that need fully-deduped state use `FINAL`. Schema: `infrastructure/docker/clickhouse/create_tables.sql`.

## Conventions and gotchas

- **`.env` lives at `infrastructure/docker/.env`**, not the repo root. `make up` won't work without it.
- **Spark job changes require restart, not rebuild**: code is bind-mounted into `ed-pyspark-jupyter`. Use `make cdc-stop` then re-run, or `cdc-force-stop` if processes hang.
- **`make down` deletes volumes** (Postgres data, Kafka offsets, ClickHouse data, Spark checkpoints). Use `make stop` to preserve state.
- **Checkpoints are not versioned**: changing a job's transform/schema while keeping the same `table_name` checkpoint can corrupt state. Delete the checkpoint dir for that table when reshaping output.
- **Debezium decimals**: any new numeric column flowing through CDC needs `decode_decimal_udf` (or equivalent) on the Spark side — Debezium serializes them as base64 with scale metadata.
- **Hostnames**: Spark/ClickHouse code uses in-container DNS names (`kafka1`, `clickhouse`, `postgres`). Host-side tools (Streamlit local mode, scripts) use `localhost` and the published ports in `.env`.
- **Connector name** is `pg-connector-ecommerce` (used by all `*-connector` Make targets).

## Service URLs (after `make up`)
- Streamlit UI: http://localhost:8501
- Grafana: http://localhost:3000 (admin / `GRAFANA_ADMIN_PASSWORD` from `.env`)
- Debezium UI: http://localhost:8085 — Connect REST API: http://localhost:8083
- Redpanda Console (Kafka): http://localhost:8080
- ClickHouse HTTP: http://localhost:8123 — native: 9000
- Spark UI: http://localhost:4040 — Jupyter: http://localhost:8888
