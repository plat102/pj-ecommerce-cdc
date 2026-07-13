## 0. Design (this turn)

- [x] 0.1 Write PROPOSAL.md describing the new `observability` capability and cross-capability deltas
- [x] 0.2 Write DESIGN.md covering four pillars, tool choices, tradeoffs, and phased rollout
- [x] 0.3 Write TASKS.md (this file)
- [x] 0.4 Write initial `specs/observability/spec.md` with placeholder requirements and the placeholder → phase-scoped mapping table
- [x] 0.5 Write `specs/infrastructure/spec.md` (MODIFIED) for full-stack-startup + volume-preservation + destructive-teardown + per-service-targets
- [x] 0.6 Write `specs/analytics/spec.md` (MODIFIED) for grafana-dashboard-provisioning growing Loki + Prometheus datasources
- [x] 0.7 Write `specs/data-governance/spec.md` (MODIFIED) for freshness-slo-and-alert gaining contact-point wiring
- [x] 0.8 Write `specs/cdc-pipeline/spec.md` (MODIFIED) for Debezium jmx-exporter javaagent + Spark Prometheus servlet
- [ ] 0.9 User approves design direction before implementation begins

## 1. Phase 1 — Foundation: central logs + container metrics

- [ ] 1.1 Create `infrastructure/docker/docker-compose.observability.yml` with services: `loki:2.9.10` (port 3100, filesystem storage, `loki_data` volume), `grafana/alloy:v1.4.3` (port 12345, mounts `/var/run/docker.sock:ro` + `/var/lib/docker/containers:ro`), `prometheus:v2.54.1` (port 9090, `prometheus_data` volume, 7d/1GB retention flags), `gcr.io/cadvisor/cadvisor:v0.49.1` (port 8082 host → 8080 container to avoid clash with redpanda-console; mounts Docker socket + rootfs read-only), `prom/node-exporter:v1.8.2` (port 9100). All services attach to the shared `ecommerce-cdc_ecommerce-network`.
- [ ] 1.2 Create `infrastructure/docker/loki/loki-config.yaml` — single-binary Loki config with filesystem storage under `/loki/chunks`, 168h (7d) retention, `limits_config.reject_old_samples: true` to bound memory.
- [ ] 1.3 Create `infrastructure/docker/alloy/config.alloy` — HCL config with `loki.source.file` tailing `/var/lib/docker/containers/*/*.log`, `loki.process` stage that extracts container name from the log path and relabels with `container`, `image`, `compose_service`; drops the high-cardinality `id` label; writes to `loki:3100`.
- [ ] 1.4 Create `infrastructure/docker/prometheus/prometheus.yml` — global 15s scrape interval; scrape configs for `cadvisor:8080` and `node-exporter:9100` (Phase 1 targets only).
- [ ] 1.5 Create `infrastructure/docker/grafana/provisioning/datasources/loki.yml` — datasource named `Loki` pointing at `http://loki:3100`, no auth.
- [ ] 1.6 Create `infrastructure/docker/grafana/provisioning/datasources/prometheus.yml` — datasource named `Prometheus` pointing at `http://prometheus:9090`, `jsonData.timeInterval: 15s`.
- [ ] 1.7 Add two Grafana dashboards under `infrastructure/docker/grafana/provisioning/dashboards/files/`: `container-health.json` (adapt Grafana ID 14282, cAdvisor Compute Resources) and `central-logs.json` (hand-build with Loki logs panel + `$container` template variable, log rate stat, error-line rate stat).
- [ ] 1.8 Add Makefile section for observability: `COMPOSE_OBS := $(COMPOSE) -f $(DOCKER_DIR)/docker-compose.observability.yml`; targets `up-observability`, `down-observability`, `logs-observability`, `status-observability`; add the observability compose file to `COMPOSE_ALL` variable so `make up` includes it.
- [ ] 1.9 Verify: `make up` starts all 5 new services; `curl http://localhost:3100/ready` returns `ready`; `curl http://localhost:9090/-/ready` returns 200; `curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[].health'` shows only `up` values; Grafana Explore → Loki filter `{container="debezium"}` returns lines within 30s of stack startup; Container Health dashboard shows non-null panels for postgres, kafka1, clickhouse.
- [ ] 1.10 Update `specs/observability/spec.md` in this change dir — add `## ADDED Requirements` for `central-log-aggregation`, `prometheus-scrape-configuration`, `container-metrics-collection`, `grafana-observability-datasources` (decomposed from `log-aggregation` and `metrics-collection` placeholders).
- [ ] 1.11 Update `specs/infrastructure/spec.md` in this change dir — extend `per-service-targets` scenario "observability stack included in make up".
- [ ] 1.12 Update `specs/analytics/spec.md` in this change dir — scenarios for Loki + Prometheus datasources visible in Grafana.
- [ ] 1.13 Update `README.md` and `CLAUDE.md` service URL sections to add http://localhost:3100 (Loki), http://localhost:9090 (Prometheus), http://localhost:8082 (cAdvisor).

## 2. Phase 2 — Pipeline metrics

- [ ] 2.1 Add to `infrastructure/docker/docker-compose.observability.yml`: `danielqsj/kafka-exporter:v1.8.0` service (port 9308, `platform: linux/amd64` — amd64-only image, needs Rosetta on arm64 Mac), with `--kafka.server=kafka1:9092` and `--kafka.version=3.7.0`. Add `prometheuscommunity/postgres-exporter:v0.15.0` service (port 9187) with `DATA_SOURCE_NAME` env pointing at postgres.
- [ ] 2.2 Create `scripts/setup_observability.sh` — idempotent script fetching `jmx_prometheus_javaagent-0.20.0.jar` (~700KB) from Maven Central into `infrastructure/docker/jmx-exporter/`; add `infrastructure/docker/jmx-exporter/*.jar` to `.gitignore`.
- [ ] 2.3 Create `infrastructure/docker/jmx-exporter/debezium-jmx.yml` — MBean → metric mapping covering `kafka.connect:type=connector-metrics,connector=*`, `debezium.postgres:type=connector-metrics,*`, JVM heap/gc metrics.
- [ ] 2.4 Modify `infrastructure/docker/docker-compose.debezium.yml`: add bind mounts for `infrastructure/docker/jmx-exporter:/opt/jmx-exporter:ro`; add `KAFKA_OPTS=-javaagent:/opt/jmx-exporter/jmx_prometheus_javaagent-0.20.0.jar=5556:/opt/jmx-exporter/debezium-jmx.yml` env; expose port `5556`.
- [ ] 2.5 Create `data-platform/streaming/spark/conf/metrics.properties` — Spark metrics config declaring the Prometheus sink at `/metrics/prometheus`.
- [ ] 2.6 Modify `data-platform/streaming/spark/scripts/submit_job.sh`: add `--conf spark.ui.prometheus.enabled=true --conf spark.metrics.conf=/home/jupyter/spark-conf/metrics.properties`; add bind mount of `metrics.properties` if not already mounted via existing streaming volume.
- [ ] 2.7 Extend `infrastructure/docker/prometheus/prometheus.yml` with scrape configs: `kafka-exporter:9308`, `postgres-exporter:9187`, `debezium:5556`, `ed-pyspark-jupyter:4040/metrics/prometheus`.
- [ ] 2.8 Add Grafana dashboards under `infrastructure/docker/grafana/provisioning/dashboards/files/`: `kafka-pipeline.json` (adapt ID 7589), `debezium-connector.json` (hand-build), `spark-streaming.json` (hand-build), `postgres-replication.json` (adapt ID 9628).
- [ ] 2.9 Verify: Prometheus `/targets` shows all 6 exporters `up`; after `make cdc-run-prod` and 1 minute, `curl -s 'http://localhost:9090/api/v1/query?query=kafka_consumergroup_lag_sum' | jq '.data.result | length'` returns > 0; Debezium dashboard shows connector state = 1 (RUNNING); Spark dashboard shows batches processed > 0.
- [ ] 2.10 Update `specs/observability/spec.md` — add `## ADDED Requirements` for `kafka-lag-metrics`, `debezium-connector-metrics`, `spark-streaming-metrics`, `postgres-replication-metrics` (decomposed from `metrics-collection` placeholder).
- [ ] 2.11 Update `specs/cdc-pipeline/spec.md` — scenarios for jmx-exporter metrics reachable + Spark Prometheus servlet.

## 3. Phase 3 — Alerts + reliability

- [ ] 3.1 Create `infrastructure/docker/grafana/provisioning/alerting/contact-points.yml` — provisioned contact points: `default-webhook` reading `$OBS_ALERT_WEBHOOK_URL`, optional `slack` reading `$OBS_SLACK_WEBHOOK_URL`. If both env vars are unset, provisioning should still succeed (Grafana keeps alerts in-UI).
- [ ] 3.2 Create `infrastructure/docker/grafana/provisioning/alerting/infra-alerts.yml` with 5 rules (folder `observability`): `kafka_consumer_lag_high` (`sum by (consumergroup) (kafka_consumergroup_lag) > 10000` for 5m, warning); `debezium_connector_not_running` (JMX-derived state expression, for 1m, critical); `spark_streaming_job_absent` (`absent(...)` or `increase(...) == 0`, for 5m, critical); `container_memory_over_90pct` (cAdvisor ratio > 0.9, for 10m, warning); `container_restart_loop` (`changes(container_start_time_seconds[10m]) > 3`, for 2m, critical).
- [ ] 3.3 Modify `infrastructure/docker/grafana/provisioning/alerting/data_freshness.yml` — add `notificationSettings.receiver: default-webhook` to close the archived-governance contact-point gap.
- [ ] 3.4 Add `restart:` policies to all compose files. `docker-compose.db.yml` (postgres: `unless-stopped`), `docker-compose.kafka.yml` (kafka1/zookeeper/schema-registry: `unless-stopped`; redpanda-console: `on-failure:3`), `docker-compose.debezium.yml` (debezium: `on-failure:3`; debezium-ui: `on-failure:3`), `docker-compose.analytics.yml` (clickhouse: `unless-stopped`; grafana: `unless-stopped`), `docker-compose.ui.yml` (cdc-testing-ui: `on-failure:3`), `docker-compose.observability.yml` (loki/prometheus: `unless-stopped`; alloy/cadvisor/node-exporter/kafka-exporter/postgres-exporter: `on-failure:3`), `docker-compose.spark.yml` (ed-pyspark-jupyter: NO restart policy — intentional so death is visible via alert).
- [ ] 3.5 Add `healthcheck:` blocks to services missing them: `postgres` (`pg_isready`), `kafka1` (`kafka-topics --list`), `debezium` (`curl -f localhost:8083/connectors`), `clickhouse` (`wget --spider localhost:8123/ping`), `schema-registry` (`curl -f localhost:8080/apis/registry/v2/system/info`), `grafana` (`curl -f localhost:3000/api/health`), `loki` (`wget -O- localhost:3100/ready`), `prometheus` (`wget -O- localhost:9090/-/ready`). Intervals 10-30s, retries 5-10.
- [ ] 3.6 Add health-based `depends_on` where startup races exist: `debezium.depends_on.kafka1.condition: service_healthy`, `debezium.depends_on.schema-registry.condition: service_healthy`. Update `make up`'s connector-apply step to no longer need the time-based sleep (rely on Debezium REST becoming healthy).
- [ ] 3.7 Update `.env.example` with `OBS_ALERT_WEBHOOK_URL=` (comment: "webhook.site test URL for dev; override in .env") and `OBS_SLACK_WEBHOOK_URL=` (comment: "optional; Slack incoming webhook URL").
- [ ] 3.8 Verify: `docker stop ed-pyspark-jupyter` → 5 minutes → `http://localhost:3000/alerting/list` shows `spark_streaming_job_absent` in `Firing`; if `OBS_ALERT_WEBHOOK_URL` is set to a webhook.site URL, its inbox shows a POST payload; `docker kill kafka1` → within 30 seconds `docker ps` shows kafka1 back `Up (healthy)`; `make status` shows every service in a `healthy` state.
- [ ] 3.9 Update `specs/observability/spec.md` — add `## ADDED Requirements` for `infrastructure-alert-rules`, `alert-contact-point-webhook`, `service-restart-policies`, `service-healthchecks` (decomposed from `alerting-and-notification` + `service-resilience` placeholders).
- [ ] 3.10 Update `specs/data-governance/spec.md` — the freshness alert now references the default contact point (scenario added).

## 4. Phase 4 — OTEL Collector (optional migration path)

- [ ] 4.1 Add to `infrastructure/docker/docker-compose.observability.yml`: `otel/opentelemetry-collector-contrib:0.109.0` service (ports 4317 OTLP gRPC, 4318 OTLP HTTP, 8889 telemetry).
- [ ] 4.2 Create `infrastructure/docker/otel/collector-config.yaml` — receivers: `filelog` tailing Docker container logs, `prometheus` scraping cAdvisor + exporters; exporters: `loki` (writes to loki:3100), `prometheusremotewrite` (writes to prometheus:9090/api/v1/write); pipelines for logs + metrics.
- [ ] 4.3 (Optional inside Phase 4) Add ClickHouse exporter to OTEL pipeline populating the existing `otel_logs` / `otel_traces` tables referenced by the Grafana ClickHouse datasource. Closes the baseline dangling reference.
- [ ] 4.4 Keep Alloy running alongside OTEL Collector (dual write; Loki dedupes). Document in `README.md` that Alloy → OTEL migration is optional.
- [ ] 4.5 Verify: OTEL Collector `/metrics` at `http://localhost:8889/metrics` shows zero refused/dropped batches; Loki still ingests logs (test with `curl -sG http://localhost:3100/loki/api/v1/query --data-urlencode 'query={container="debezium"}'`); `curl -X POST -H 'Content-Type: application/json' -d '{"resourceLogs":[]}' http://localhost:4318/v1/logs` returns 200.
- [ ] 4.6 Update `specs/observability/spec.md` — add `## ADDED Requirements` for `otel-collector-pipeline`, `otlp-ingestion-endpoint` (decomposed from `otel-migration-path` placeholder).

## 5. Archive

- [ ] 5.1 Run `openspec validate --changes --specs` and ensure all checks pass.
- [ ] 5.2 Merge each `specs/<capability>/spec.md` file from this change dir into the corresponding `openspec/specs/<capability>/spec.md`, applying `## MODIFIED Requirements` sections into the existing requirement blocks (`openspec archive` does this automatically).
- [ ] 5.3 Merge `specs/observability/spec.md` into a new `openspec/specs/observability/spec.md`, decomposing the 5 broad placeholder requirements into the 12-14 phase-scoped requirements listed in `design.md` § "Requirements That Will Be Declared". Remove placeholders in change dir before archive so only phase-scoped requirements land in main spec (mirrors `add-data-governance` archive pattern).
- [ ] 5.4 Move `openspec/changes/add-infra-observability/` to `openspec/changes/archive/YYYY-MM-DD-add-infra-observability/` (`openspec archive` handles this).
