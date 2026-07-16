# Data governance

Everything the CDC pipeline does to keep data trustworthy — i.e. prevent schema violations, exposing raw PII, writing invalid rows, and losing audit trails: **schema contracts**, **PII masking**, **quality gate**, **DLQ topology**, **RBAC**, **retention / TTL**, and **catalog + lineage**.

Prerequisite reading: [`architecture.md`](architecture.md) for the pipeline these controls wrap.

Capability boundary: `data-governance` decides *what makes a row invalid* (GX suites, schema mismatches, PII contracts). `error-handling` (proposed change `add-error-handling-dlq`) decides *what happens after* — the DLQ topology below already spans both.

## Schema Registry (Apicurio)

- Debezium key/value converter: `io.apicurio.registry.utils.converter.AvroConverter`.
- Endpoint (in-network): `http://schema-registry:8080/apis/registry/v2`.
- Debezium container runs with `ENABLE_APICURIO_CONVERTERS=true`.
- Host access: http://localhost:8081.
- Connector config: `data-platform/cdc/connectors/register-pg.json` (connector name `pg-connector-ecommerce`, captures `public.customers`, `public.products`, `public.orders`).

## PII masking in Spark

Applied inside the transformers before write to ClickHouse (raw values never land in the analytics store):

| Column | UDF | Output shape |
|---|---|---|
| `customers.email` | `hash_pii_udf` | 64-char lowercase hex SHA-256 salted with `PII_SALT` |
| `customers.name` | `tokenize_name_udf` | `{first-initial-uppercase}.{6-hex}` (e.g. `A.7f3c9d`) |

UDFs live in `data-platform/streaming/spark/src/utils/udfs.py`. Salt comes from the `PII_SALT` env var (set in `infrastructure/docker/.env` — leave as a placeholder in git).

## Data quality gate

Spark's `foreachBatch` writer is wrapped with `with_gx_gate` — each micro-batch runs a Great Expectations suite before the ClickHouse append. Rows that fail expectations are routed to `{table}_dlq` on Kafka instead of dropped.

## DLQ topology

Solid arrows = happy path. Dashed arrows = quarantine. Dashed nodes = not yet implemented (see status table below).

```mermaid
flowchart LR
    PG[("Postgres")] --> DBZ["Debezium"]
    DBZ -->|good| K[("Kafka pg.public.*")]
    DBZ -.->|"deser / converter errors"| CDLQ[("debezium_connect_dlq")]

    K --> SP["Spark job"]
    SP -->|passes GX| CH[("ClickHouse *_cdc")]
    SP -.->|"fails GX"| GDLQ[("&lt;table&gt;_dlq")]
    SP -.->|"sink write error"| SDLQ[("&lt;table&gt;_sink_dlq")]

    CDLQ --> UI["Streamlit DLQ Triage"]
    GDLQ --> UI
    SDLQ --> UI

    classDef proposed stroke-dasharray: 4 4
    class SDLQ,UI proposed
```

Status legend:

| DLQ topic | Trigger | Status |
|---|---|---|
| `{table}_dlq` | GX suite fails for a row inside `foreachBatch` | **applied** (data-governance Phase 3) |
| `debezium_connect_dlq` | Kafka Connect deserialization / converter error (`errors.tolerance=all`) | **Phase 1 applied** (commit `c1a55ce`) |
| `{table}_sink_dlq` | Spark → ClickHouse JDBC write failure | **proposed** (Phase 2 of `add-error-handling-dlq`) |
| Central DLQ dashboard + `dlq_traffic_present` alert | > 0 messages on any `*_dlq` in 5 min | **proposed** (Phase 3) |
| Streamlit `DLQ Triage` page | Browse quarantined rows by `dlq_topic`, `error_class`, `key`, `payload`, `first_seen` | **proposed** (Phase 4) |

Non-goals for the error-handling change: automatic DLQ replay (manual by design), cross-topic correlation (each stage owns its own DLQ), retention beyond the 14-day topic policy set below.

## RBAC (ClickHouse)

- Role `analyst_readonly` — declared in `infrastructure/docker/clickhouse/create_tables.sql`.
- Grants: `SELECT` on `customers_cdc`, `products_cdc`, `orders_cdc`. No `INSERT` / `ALTER` / `DROP`.
- Row policy: only rows where `_deleted = 0` are visible.
- User is created at container init by `create_governance_users.sh` using `CLICKHOUSE_ANALYST_PASSWORD` (in `.env`, placeholder in git).
- Grafana's `ClickHouse-Analytics` datasource connects as `analyst_readonly` — dashboards can never see tombstones or mutate data.

## Retention & TTL

**Kafka** — applied by `data-platform/governance/retention/apply-kafka-topic-retention.sh`:

| Topic pattern | `retention.ms` |
|---|---|
| `pg.public.*` | 7 days (`604800000`) |
| `governance.access_log` | 30 days (`2592000000`) |
| `*_dlq` | 14 days |

**ClickHouse** — TTL clauses on every `*_cdc` table anchored on `toDateTime(_version / 1000)`:

| Rule | Retention |
|---|---|
| `WHERE _deleted = 1 DELETE` | 90 days (tombstones) |
| `DELETE` (unconditional) | 2 years (active rows) |

**Postgres** — `data-platform/governance/retention/postgres-archive.sql` defines an `orders_archive` table and moves rows with `order_time < now() - INTERVAL '1 year'` into it. The archive table is **excluded** from Debezium's `table.include.list` so archival never generates spurious CDC traffic.

## Checkpoint versioning

Spark checkpoints live at `{CHECKPOINT_LOCATION}/{table}/v{schema_version}` (Phase 1 hard-codes `schema_version = 1`). Prevents checkpoint corruption when a job's transform/schema shape changes but the checkpoint path stays constant — bump the version, get a fresh path.

Base class: `data-platform/streaming/spark/src/jobs/base_cdc_job.py`.

## Catalog & lineage (optional)

- **OpenMetadata** ingestion configs live under `data-platform/governance/openmetadata/ingestion/` (postgres.yaml, kafka.yaml, clickhouse.yaml). Operated via `make up-governance` / `down-governance` — not included in `make up` because of the memory footprint (MySQL + Elasticsearch).
- **OpenLineage** Spark listener is gated by `ENABLE_OPENLINEAGE=1`; when on, Spark emits lineage events for each streaming query.
- Column-level documentation lives in `COMMENT` clauses inside `infrastructure/docker/clickhouse/create_tables.sql`.

## Where to look

| Thing | Path |
|---|---|
| Debezium connector JSON | `data-platform/cdc/connectors/register-pg.json` |
| PII UDFs | `data-platform/streaming/spark/src/utils/udfs.py` |
| Transformers (apply PII) | `data-platform/streaming/spark/src/transformations/*_cdc_transformer.py` |
| GX gate | `data-platform/streaming/spark/src/governance/` |
| ClickHouse DDL (tables, TTL, role) | `infrastructure/docker/clickhouse/create_tables.sql` |
| ClickHouse governance-users init | `infrastructure/docker/clickhouse/create_governance_users.sh` |
| Kafka retention script | `data-platform/governance/retention/apply-kafka-topic-retention.sh` |
| Postgres archival | `data-platform/governance/retention/postgres-archive.sql` |
| OpenMetadata ingestion | `data-platform/governance/openmetadata/ingestion/` |
| DLQ proposal | `openspec/changes/add-error-handling-dlq/` |
