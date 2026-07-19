# Project structure

Top-level layout with one-line annotations. This doc is a **map** — for the runtime picture see [`architecture.md`](architecture.md); for design rationale and requirements see the capability specs under `../openspec/specs/`.

```
pj-ecommerce-cdc/
├── application/
│   └── cdc-testing-ui/                 Streamlit app: CRUD, Kafka monitor, (proposed) DLQ triage
│       ├── app.py                      Entry point; routes to views/
│       ├── views/                      Page modules (customers, products, orders, kafka monitor)
│       ├── managers/                   Postgres + Kafka clients
│       └── config/settings.py          Centralized connection settings
├── data-platform/
│   ├── cdc/connectors/
│   │   └── register-pg.json            Debezium PostgreSQL connector (Apicurio Avro converter)
│   ├── streaming/spark/
│   │   ├── apps/run_cdc_job.py         Dispatcher: --job-type {customers|products|orders} [--debug]
│   │   ├── conf/metrics.properties     Spark PrometheusServlet sink config
│   │   ├── scripts/submit_job.sh       spark-submit wrapper (called from host via scripts/run_cdc.sh)
│   │   └── src/
│   │       ├── jobs/                   base_job -> base_streaming_job -> base_cdc_job
│   │       │                             + customers_cdc_job / product_cdc_job / order_cdc_job
│   │       ├── transformations/        Debezium parser + per-table transformers (apply PII UDFs,
│   │       │                             set _version / _deleted)
│   │       ├── io/                     kafka_client + clickhouse_client (foreachBatch writer)
│   │       ├── governance/             GX gate (with_gx_gate), DLQ helpers
│   │       ├── schemas/cdc_schemas.py  StructTypes for Debezium payloads
│   │       ├── utils/udfs.py           decode_decimal_udf, hash_pii_udf, tokenize_name_udf
│   │       └── config/app_config.py    AppConfig (env-driven: KAFKA_SERVERS, CLICKHOUSE_*, ...)
│   ├── dashboards/
│   │   ├── clickhouse/analytics_views.sql   Business views (sales/customer/product/monitoring)
│   │   └── grafana/                    Provisioned dashboard JSONs
│   └── governance/
│       ├── retention/                  Kafka retention script + Postgres archival SQL
│       └── openmetadata/ingestion/     OpenMetadata ingestion configs (postgres/kafka/clickhouse)
├── infrastructure/
│   ├── docker/                         .env lives HERE (not repo root); 7 compose files
│   │   ├── .env.example
│   │   ├── docker-compose.db.yml
│   │   ├── docker-compose.kafka.yml
│   │   ├── docker-compose.debezium.yml
│   │   ├── docker-compose.ui.yml
│   │   ├── docker-compose.spark.yml
│   │   ├── docker-compose.analytics.yml
│   │   ├── docker-compose.observability.yml
│   │   ├── docker-compose.governance.yml   Not included in `make up` (memory footprint)
│   │   ├── postgres/                   init SQL
│   │   ├── kafka/                      broker + Redpanda Console configs
│   │   ├── clickhouse/                 create_tables.sql (schema, TTL, RBAC), governance-users script
│   │   ├── grafana/provisioning/       datasources/, alerting/, dashboards/ (auto-loaded)
│   │   ├── loki/                       Loki single-binary config
│   │   ├── prometheus/prometheus.yml   Scrape targets
│   │   ├── alloy/                      Alloy config (tails Docker container stdout)
│   │   ├── otel/collector-config.yaml  OTEL Collector pipelines
│   │   ├── postgres-exporter/          Custom queries (replication slot metrics)
│   │   └── jmx-exporter/               JMX-exporter jar + Debezium JMX rules (jar is gitignored)
│   └── terraform/                      Azure VM provisioning (see deploy_azure_vm.md)
├── openspec/                           Source of truth for architecture
│   ├── specs/                          Applied capabilities (cdc-pipeline, analytics, observability,
│   │                                   data-governance, infrastructure, streamlit-ui, python-tooling)
│   ├── changes/                        Active proposals (currently: add-error-handling-dlq)
│   │   └── archive/                    Applied changes (baseline, python-tooling, data-governance,
│   │                                   infra-observability)
│   └── config.yaml
├── scripts/                            Host-side wrappers (run_cdc.sh, sync_dashboards.sh,
│                                       setup_observability.sh, setup_simple_analytics.sh)
├── tests/                              pytest suite
├── docs/                               Human-readable overview (this folder)
├── Makefile                            Canonical entrypoint — run `make help` for target list
├── pyproject.toml + uv.lock            uv-managed Python env (.venv/)
├── AGENTS.md                           Contributor-facing agent notes
├── CLAUDE.md                           Guidance file consumed by the Claude Code CLI (not a doc)
└── README.md
```

## Where does X live?

| Question | Answer |
|---|---|
| Where is the Debezium connector config? | `data-platform/cdc/connectors/register-pg.json` |
| Where is the Spark job entry point? | `data-platform/streaming/spark/apps/run_cdc_job.py` |
| Where is ClickHouse DDL (tables, TTL, role)? | `infrastructure/docker/clickhouse/create_tables.sql` |
| Where are Grafana dashboards checked in? | `data-platform/dashboards/grafana/` (synced by `make sync-dashboards`) |
| Where are Grafana alert rules? | `infrastructure/docker/grafana/provisioning/alerting/{infra-alerts,data_freshness,contact-points}.yml` |
| Where are the Prometheus scrape targets? | `infrastructure/docker/prometheus/prometheus.yml` |
| Where does `.env` go? | `infrastructure/docker/.env` — not the repo root |
| Where is the source of truth for the architecture? | `openspec/specs/` (capability specs); this docs folder mirrors it |
