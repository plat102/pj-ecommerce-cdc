## Why

The `pj-ecommerce-cdc` stack runs 10+ containers (postgres, kafka, zookeeper, debezium, schema-registry, redpanda-console, clickhouse, grafana, spark, streamlit UI) plus optional OpenMetadata governance stack. After Phase 3 of `add-data-governance` archived, the observability posture is:

- **Logs**: stdout only. Debugging a Spark failure requires 3–5 `make logs-*` terminals to correlate with Kafka/Debezium.
- **Metrics**: Grafana has 3 dashboards over ClickHouse business data. Zero visibility into container CPU/RAM, Kafka consumer lag, Debezium connector state, Spark job progress, or Postgres replication lag.
- **Alerting**: exactly one rule (`cdc_freshness_10min_slo` from `data-governance`) with **no contact point wired** — alerts fire silently in the Grafana UI.
- **Resilience**: no `restart:` policies on any service; only OpenMetadata's own services (Phase 4 governance) have healthchecks.
- **Dangling OTEL reference**: Grafana ClickHouse datasource declares `otel_logs` and `otel_traces` tables that nothing populates.

The result is a "log into three terminals and pray" debugging workflow. When the freshness alert would fire, nobody sees it. This proposal adds a proper infrastructure observability layer for local development that follows Data Engineering best practices: separation of observability from OLAP storage, Grafana-native tooling (Loki + Prometheus + Alloy) in Phase 1, and OpenTelemetry Collector as an optional Phase 4 migration path.

This is currently a **design-only proposal**. Implementation begins only after user approval.

## What Changes

- Add a new `observability` OpenSpec capability covering: central log aggregation, container + host metrics, pipeline-specific metrics (Kafka lag, Debezium connector state, Spark streaming, Postgres replication), alerting with wired contact points, service restart policies, and healthchecks.
- MODIFY existing capabilities where observability touches their observable behavior:
  - **`infrastructure`**: new `docker-compose.observability.yml`, new `up-observability` / `down-observability` / `logs-observability` / `status-observability` Make targets; the observability compose file joins `COMPOSE_ALL` so `make up` includes it by default (~700MB budget, under the 1GB cap); restart policies and healthchecks added to existing services.
  - **`analytics`**: Grafana grows Loki + Prometheus datasources alongside the existing ClickHouse one, and 6 new infrastructure dashboards alongside the existing 3 business dashboards.
  - **`data-governance`**: `freshness-slo-and-alert` gains a wired contact point (closes the archived-governance gap where the alert fired silently).
  - **`cdc-pipeline`**: `submit_job.sh` gains Spark Prometheus servlet configs (Phase 2); Debezium container gains a jmx-exporter javaagent sidecar for connector metrics (Phase 2).
- **Storage backend decision**: Grafana stack (Loki filesystem for logs, Prometheus TSDB for metrics), both with 7-day retention for local dev. Rationale in DESIGN.md § Decisions.
- **Log/metric collector decision**: Grafana Alloy in Phase 1 (fast to configure, Grafana-native), with OTEL Collector as an optional Phase 4 migration path (vendor-neutral, unlocks future distributed tracing and populates the dangling `otel_logs`/`otel_traces` ClickHouse tables).
- Phased rollout (see DESIGN.md): foundation → pipeline metrics → alerts + reliability → optional OTEL migration. Each phase independently shippable.

## Capabilities

### New Capabilities

- `observability`: Owns infrastructure log aggregation (Loki + Alloy tailing Docker container logs), metrics collection (Prometheus + cAdvisor + node-exporter + kafka-exporter + postgres-exporter + Debezium JMX + Spark servlet), alert rule provisioning and contact-point wiring (Grafana Unified Alerting), and service resilience (restart policies + healthchecks). Data-governance retains ownership of *data* observability (freshness SLO, DLQ, lineage); observability owns *infrastructure* observability.

### Modified Capabilities

- `infrastructure`: adds observability compose file to canonical target set, adds restart policies + healthchecks as first-class requirements, extends `full-stack-startup` and `volume-preservation` to cover Loki/Prometheus volumes.
- `analytics`: Grafana provisioning grows two datasources (Loki, Prometheus) and six dashboards (container-health, central-logs, kafka-pipeline, debezium-connector, spark-streaming, postgres-replication) alongside the existing three business dashboards.
- `data-governance`: `freshness-slo-and-alert` scenario adds a contact-point reference (closes the archived-governance gap).
- `cdc-pipeline`: `submit_job.sh` scenario gains Spark Prometheus servlet configs; Debezium docker-compose scenario gains the jmx-exporter javaagent sidecar.

## Impact

- Adds `openspec/changes/add-infra-observability/{DESIGN.md,PROPOSAL.md,TASKS.md}`, plus delta specs for `observability` (new), `infrastructure`, `analytics`, `data-governance`, `cdc-pipeline` (this turn).
- Future implementation will: add `docker-compose.observability.yml` (loki + alloy + prometheus + cadvisor + node-exporter, with kafka-exporter + postgres-exporter added in Phase 2); add config files for Prometheus scrape configs, Loki storage, Alloy log tailing; add new Grafana datasource + dashboard + alerting provisioning files; add jmx-exporter javaagent sidecar to Debezium; enable Spark's built-in Prometheus servlet; add restart policies + healthchecks to all existing services; wire contact points via `.env` variables (`OBS_ALERT_WEBHOOK_URL`, `OBS_SLACK_WEBHOOK_URL`).
- No code changes to Spark transformers, Streamlit UI, or ClickHouse table DDL — this change is purely observability infrastructure.
- Non-goals include Azure VM prod concerns, distributed tracing SDK integration in Spark/Streamlit (Phase 4 lays the pipe but doesn't instrument), full Alertmanager topology (Grafana 10.x bundled Alertmanager is sufficient), and ClickHouse-side observability tables (avoided intentionally — separation from OLAP).
