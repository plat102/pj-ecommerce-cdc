## Context

The `pj-ecommerce-cdc` demo runs 10 containers on a single Docker-Compose stack. Two OpenSpec changes have already archived: `add-data-governance` (data-side observability: freshness SLO, DLQ, PII masking, lineage) and `add-python-tooling` (uv + pytest). What's still missing is the *infrastructure-side* observability that most Data Engineering teams put around a CDC pipeline:

- **No central log aggregator.** Every container logs to stdout; developers use `docker logs` or a fan of `make logs-*` terminals. Correlating "Spark job died at 14:32" with "Debezium reconnected at 14:31" requires humans doing the correlation by eye.
- **No infrastructure metrics.** Grafana currently shows only ClickHouse business data (orders/customers/products dashboards). Container CPU/RAM, Kafka consumer lag, Debezium connector state, Spark streaming progress, and Postgres replication lag are all invisible.
- **No wired alerts.** The single alert rule (`cdc_freshness_10min_slo` from `add-data-governance` Phase 3) has no contact point provisioned — it fires silently in the Grafana UI.
- **No restart policies, incomplete healthchecks.** Every container will stop on crash and stay stopped. Only the OpenMetadata governance stack has `healthcheck:` blocks; the CDC pipeline containers rely on time-based `sleep` in Makefile targets to sequence startup (e.g., `apply-pg-connector` runs blindly after `make up`).
- **Dangling OTEL reference.** The existing Grafana ClickHouse datasource (`infrastructure/docker/grafana/provisioning/datasources/clickhouse.yml`) declares `otel_logs` and `otel_traces` tables that nothing populates. Suggests prior intent that never landed.

This document is the design for a new `observability` OpenSpec capability that consolidates these concerns. It does **not** create the file tree or edit any docker-compose files yet — those follow once the design direction is approved.

## Goals / Non-Goals

**Goals:**
- Central log aggregation with a query UI where developers can filter across all containers (`{container="debezium"} |= "ERROR"`).
- Infrastructure metrics for every service in the stack — CPU, memory, disk, network — visible in Grafana without opening five UIs.
- Pipeline-specific metrics: Kafka consumer lag by group, Debezium connector state (RUNNING/PAUSED/FAILED), Spark streaming batch progress, Postgres replication slot lag.
- Wired alerting: at least 5 rules covering the classes of failure the pipeline actually hits, with notifications reaching an external channel (webhook.site or Slack) rather than dying in the UI.
- Restart policies and healthchecks that eliminate the "kill kafka1 and everything else falls over silently" failure mode, and that let `depends_on: condition: service_healthy` replace time-based `sleep` in the Makefile.
- All requirements expressible as OpenSpec specs so `openspec validate` verifies them structurally.

**Non-Goals:**
- Azure VM prod deployment concerns. `infrastructure/terraform/` exists but this change explicitly targets local dev only.
- Instrumenting Spark or Streamlit code with the OpenTelemetry SDK for distributed tracing. Phase 4 (optional) provides the *ingress* (OTLP endpoint) but does not add SDK code to Spark jobs or Streamlit views.
- Log/metric retention beyond 7 days. Local dev doesn't need it.
- A production-grade Alertmanager topology with routing/silencing rules. Grafana 10.x's bundled Alertmanager is sufficient.
- ClickHouse-side observability tables (dedicated OTEL schemas populated by an OTEL exporter). Deliberately avoided — the whole point of adding Loki/Prometheus is to keep observability workload off ClickHouse so the Phase 3 freshness SLO isn't fighting for merge budget.
- Container image size optimization. Every image tag is pinned but no custom builds.
- Bumping Grafana version. Existing 10.3.12 stays.

## Four Pillars

Structured to mirror the shape of `add-data-governance`'s four-pillar design. Each pillar is independently shippable.

### Pillar 1 — Central Log Aggregation

**Tool choice:** **Grafana Loki** (single-binary, filesystem storage) + **Grafana Alloy** as the log shipper.

**Behavior the spec will encode:**
- Loki runs single-binary at `loki:3100` with filesystem storage under `/loki/chunks`, 7-day retention.
- Alloy runs a Docker container-log tailer over `/var/lib/docker/containers/*/*.log` (bind-mounted read-only) and relabels each line with `container`, `image`, and `compose_service` labels before writing to Loki.
- Grafana provisions a Loki datasource pointing at `http://loki:3100`.
- A `central-logs` dashboard exposes a Loki logs panel with a `$container` template variable so developers can quickly filter to one container.

**Where it plugs in (reuse, don't rebuild):**
- `infrastructure/docker/grafana/provisioning/datasources/` — add `loki.yml` alongside the existing `clickhouse.yml`.
- `infrastructure/docker/grafana/provisioning/dashboards/files/` — add `central-logs.json` alongside the three existing dashboards. The provisioning config (`dashboards.yml`) already declares `updateIntervalSeconds: 10`, so new files are picked up automatically.
- Alloy needs Docker socket read access (`/var/run/docker.sock:/var/run/docker.sock:ro`) to enumerate containers.

**Tradeoff:** Alloy vs Promtail vs Fluentbit vs OTEL Collector for the shipping side. Alloy is Grafana Labs' 2024-era successor to Grafana Agent and Promtail, uses HCL config (short/readable), and is deeply integrated with the Grafana stack. Promtail is deprecated. Fluentbit is generic but adds a mental-model tax. OTEL Collector is the vendor-neutral standard and unlocks tracing, but has verbose YAML config. Chose Alloy for Phase 1 ergonomics; Phase 4 layers OTEL Collector on top for the learning path.

### Pillar 2 — Infrastructure Metrics

**Tool choice:** **Prometheus** with 7-day retention + **cAdvisor** (per-container) + **node-exporter** (host-level).

**Behavior the spec will encode:**
- Prometheus runs at `prometheus:9090` with `--storage.tsdb.retention.time=7d` and `--storage.tsdb.retention.size=1GB` for local dev bounds.
- cAdvisor runs at `cadvisor:8082` (bound to `8082` host-side to avoid clash with redpanda-console on `8080`); scrapes per-container CPU, memory, network, disk I/O from the Docker socket.
- node-exporter runs at `node-exporter:9100` for host-level disk/RAM headroom signal. On Docker Desktop Mac, this reports the Linux VM (not macOS), which is still useful for detecting when the pipeline itself has run the VM out of RAM.
- Grafana provisions a Prometheus datasource pointing at `http://prometheus:9090`.
- A `container-health` dashboard imports Grafana ID **14282** (cAdvisor Compute Resources) with a relabel step to drop the high-cardinality `id` label and keep only `name`, `image`, `compose_service`.

**Where it plugs in:**
- `infrastructure/docker/prometheus/prometheus.yml` — new file, Phase 1 scrape configs for cAdvisor + node-exporter; Phase 2 extends with exporter targets.
- `infrastructure/docker/grafana/provisioning/datasources/prometheus.yml` — new datasource file.
- `infrastructure/docker/grafana/provisioning/dashboards/files/container-health.json` — imported dashboard, adapted.

### Pillar 3 — Pipeline-Specific Metrics

**Tool choice per component:**

| Source | Approach | Rationale |
|--------|----------|-----------|
| Kafka | `danielqsj/kafka-exporter` container scraping kafka1:9092 | Standard, single-purpose; exposes consumer group lag which is *the* Kafka observability question. |
| Debezium | jmx-exporter as `-javaagent:` sidecar inside Debezium container | Debezium/Kafka Connect exposes rich JMX MBeans (connector state, snapshot progress, commit lag). Sidecar approach avoids a separate container. |
| Spark | Built-in Prometheus servlet enabled via `spark.ui.prometheus.enabled=true` | Spark 3.x ships this natively; no new container, just a `--conf` flag and a Prometheus scrape target. |
| Postgres | `prometheuscommunity/postgres-exporter` container | Standard; exposes `pg_stat_replication` for CDC replication slot lag. |

**Behavior the spec will encode:**
- Prometheus scrapes each of the four sources every 15–30 seconds; targets configured in `prometheus.yml`.
- Debezium container gains `KAFKA_OPTS=-javaagent:/opt/jmx-exporter/jmx_prometheus_javaagent.jar=5556:/opt/jmx-exporter/debezium-jmx.yml` env var + bind mounts. The jar itself is fetched by a first-run setup script (`scripts/setup_observability.sh`), not committed.
- Spark's `submit_job.sh` gains `--conf spark.ui.prometheus.enabled=true --conf spark.metrics.conf=metrics.properties`, with a new `data-platform/streaming/spark/conf/metrics.properties` file defining the Prometheus sink.
- Four dashboards land: `kafka-pipeline.json`, `debezium-connector.json`, `spark-streaming.json`, `postgres-replication.json`.

**Where it plugs in:**
- `infrastructure/docker/docker-compose.observability.yml` — kafka-exporter, postgres-exporter services (Phase 2).
- `infrastructure/docker/docker-compose.debezium.yml` — env var + bind mounts for jmx-exporter sidecar (Phase 2).
- `infrastructure/docker/jmx-exporter/debezium-jmx.yml` — MBean → metric mapping (new file).
- `data-platform/streaming/spark/conf/metrics.properties` — new file.
- `data-platform/streaming/spark/scripts/submit_job.sh` — `--conf` flags added to `spark-submit`.

**Tradeoff:** JMX-exporter jar is not committed to the repo (~700KB binary; also license consideration). A setup script downloads it on first `make up-observability`. Trade-off: adds a soft dependency ("did you run the setup script?") vs bloating the repo with a binary. Setup script also lets us pin a version-consistent jar independently of the Debezium image.

### Pillar 4 — Alerts, Contact Points, and Service Resilience

**Tool choice:** Grafana 10.x's built-in **Unified Alerting** with the bundled Alertmanager. **No separate Alertmanager container.**

**Behavior the spec will encode:**
- Alert rules provisioned via `infrastructure/docker/grafana/provisioning/alerting/infra-alerts.yml` — 5 rules covering: Kafka consumer lag > 10k msgs, Debezium connector not RUNNING, Spark streaming job absent, container memory > 90% of limit, container restart loop.
- Contact points provisioned via `infrastructure/docker/grafana/provisioning/alerting/contact-points.yml` — reads `OBS_ALERT_WEBHOOK_URL` from `.env` (webhook.site for dev) and optionally `OBS_SLACK_WEBHOOK_URL` for Slack incoming webhooks.
- The existing `data_freshness.yml` alert (from `add-data-governance` Phase 3) is MODIFIED to reference the same default contact point (closes the archived-governance gap where that alert had no wired notification).
- All 10 core CDC-pipeline services gain `restart:` policies (`unless-stopped` for stateful, `on-failure:3` for stateless; `ed-pyspark-jupyter` intentionally left unrestarted so Spark job death is visible via the alert).
- Services missing healthchecks (`postgres`, `kafka1`, `debezium`, `clickhouse`, `schema-registry`, `grafana`, plus the new `loki`/`prometheus`) gain them, allowing `depends_on: { condition: service_healthy }` to replace time-based sleeps in the Makefile.

**Where it plugs in:**
- `infrastructure/docker/grafana/provisioning/alerting/` — new files alongside existing `data_freshness.yml`.
- Every `infrastructure/docker/docker-compose.*.yml` — add restart + healthcheck stanzas.
- `.env.example` — add `OBS_ALERT_WEBHOOK_URL=` and `OBS_SLACK_WEBHOOK_URL=` placeholders with comments pointing to webhook.site for dev.

## Decisions

**Grafana stack (Loki + Prometheus), not OTEL → ClickHouse**
The Grafana ClickHouse datasource already declares `otel_logs`/`otel_traces` tables, hinting at a previous plan to store observability in ClickHouse. Rejected because: (1) ClickHouse is our OLAP layer for business dashboards and the Phase 3 governance `data_freshness` SLO; storing high-cardinality observability data there creates merge contention that could push freshness beyond the 10-minute SLO. (2) Loki + Prometheus are the ecosystem standard for DE observability (2024-2026); the skill transfers. (3) LogQL + PromQL native to Grafana; no need for custom SQL views. Phase 4 optionally populates the dangling `otel_logs`/`otel_traces` tables via OTEL Collector but the *primary* storage stays Loki/Prometheus.

**Grafana Alloy for logs in Phase 1; OTEL Collector as Phase 4 (optional)**
Alloy ships in 1-2 hours of config work with tight Grafana integration. OTEL Collector is the vendor-neutral standard but adds ~2-3 hours of config verbosity for identical Phase 1 outcomes. Ship Alloy first; Phase 4 layers OTEL on top for the learning path and to unlock traces later. Both can coexist writing to Loki (Loki dedupes).

**Observability stack is part of `make up` by default**
Phase 1+2 sum ~700MB RAM. Under the 1GB budget. The whole product goal is "developers see the single-pane-of-glass view from day one" — opt-in defeats this. Contrast with the OpenMetadata governance stack (~4GB) which stays opt-in via `make up-governance`.

**No new capability for restart policies + healthchecks; they live under `observability`**
Reasoning: healthchecks and restart policies exist *for* observability outcomes (auto-recovery, `depends_on: service_healthy` sequencing, `docker ps` reflecting real health). They're implemented in infra compose files but their *purpose* is observability. Requirement lives in `observability`; the `infrastructure` capability gets a MODIFIED delta noting the docker-compose changes.

**Fix Phase 3 governance freshness alert here**
The `add-data-governance` change archived with `freshness-slo-and-alert` requiring a rule but not a contact point. Rather than leave the gap open or open a mini-change, this proposal MODIFIES that requirement to wire the contact point provisioned by observability Phase 3. Documented as a cross-capability modification.

**cAdvisor bound to host `8082` not default `8080`**
Redpanda Console already binds `8080`. cAdvisor's *container-side* port stays `8080`; only the host mapping shifts to `8082`.

**jmx-exporter jar bootstrapped by setup script, not committed**
~700KB binary; fetch via `scripts/setup_observability.sh` on first `make up-observability`, `.gitignore` the jar itself. Config file (`debezium-jmx.yml`) is committed.

**Prometheus 7-day retention**
Local dev doesn't need historical data. 7d bounds disk usage to ~500MB on `prometheus_data` volume. `make down` removes the volume per the existing `destructive-teardown` contract; document this explicitly rather than special-case it.

**Include `container_restart_loop` alert**
Cheap to add (uses cAdvisor metric already scraped), catches the exact scenario the new restart policies introduce (auto-restart succeeding but immediately re-crashing). Prevents "restart:unless-stopped hides a real failure" mode.

## Risks / Trade-offs

**RAM budget honesty**
Sum of Phase 1+2: loki 150 + alloy 100 + prometheus 200 + cadvisor 100 + node-exporter 30 + kafka-exporter 40 + postgres-exporter 40 + jmx sidecar 50 = **710MB**. Under the 1GB budget but leaves little headroom. If Prometheus retention stretches beyond 7d or dashboards grow heavier, revisit; may need to bump the Docker Desktop VM allocation.

**Log volume vs Loki filesystem storage**
Streamlit + Spark are chatty. Alloy shipping ~1000 lines/min from Streamlit alone across 6 CDC services will churn Loki chunks. Mitigation: `limits_config.reject_old_samples: true`, `retention_period: 168h` (7 days), `ingester.chunk_target_size` set to bound memory. Expect ~500MB steady-state on `loki_data` volume.

**Prometheus cardinality footguns**
cAdvisor's default labels explode cardinality when Docker Compose recreates services with new container IDs. Use Alloy/scrape relabeling to drop `id`, keep `name`/`image`/`compose_service` only. Same for kafka-exporter — avoid per-partition metric explosion by not enabling that flag.

**Persistence across `make down`**
Existing `destructive-teardown` requirement (`openspec/specs/infrastructure/spec.md:41`) states `make down` removes all volumes. Loki + Prometheus volumes go too. Intentional consistency with existing contract; document explicitly in the new spec so nobody expects observability data to survive a destructive teardown. Recovery: re-run `make up`.

**jmx-exporter agent bootstrap**
Jar isn't in the image, isn't committed. A setup script handles the first-run download. If a developer skips the script and runs `make up-observability` directly, Debezium may fail to boot (javaagent path missing). Mitigation: the setup script is idempotent and can be called from `up-observability` target, or provide a healthcheck-style check on debezium startup. Simpler: document in README + fail fast in the setup script.

**arm64 Mac + Rosetta**
Loki, Prometheus, Alloy, cAdvisor, node-exporter, postgres-exporter all ship native arm64. kafka-exporter (`danielqsj/kafka-exporter`) is amd64-only — force `platform: linux/amd64` on that service. All other services can omit `platform:` and let Docker Desktop pick native.

**Grafana bundled Alertmanager limitations**
Grafana 10.x's built-in Alertmanager doesn't support high-availability routing or complex silencing rules. Fine for local dev; a real prod deployment would need a separate Alertmanager cluster. Not in scope.

**Ports checked for collision**
New ports: 3100 (Loki), 8082 (cAdvisor host), 9090 (Prometheus), 9100 (node-exporter), 9187 (postgres-exporter), 9308 (kafka-exporter), 5556 (debezium jmx), 12345 (Alloy UI). Phase 4 adds 4317 (OTLP gRPC), 4318 (OTLP HTTP), 8889 (OTEL telemetry). Cross-checked against existing: 2181, 3000, 4040, 5432, 8080, 8081, 8083, 8085, 8123, 8501, 8585, 8888, 9000, 9092, 9093. No conflicts.

**OTEL Collector Phase 4 is genuinely optional**
Phase 4 exists so the change has an OTEL learning path and closes the dangling `otel_logs`/`otel_traces` reference. But shipping Phases 1-3 alone gets the developer the observability win. Design decision: don't gate archive on Phase 4.

## Phased Rollout

Each phase independently shippable; ship in order but stop at any phase if value is sufficient.

**Phase 1 — Foundation (Pillar 1 + Pillar 2)**
- Central logs (Loki + Alloy) and infra metrics (Prometheus + cAdvisor + node-exporter); 2 dashboards.
- Exit criteria: `curl http://localhost:3100/ready` returns "ready"; Prometheus `/targets` shows cAdvisor + node-exporter `up`; Grafana Explore → Loki filter `container="debezium"` shows recent lines; Container Health dashboard populated for all core services.
- Highest risk-reduction per line of code: one dashboard now correlates what previously required 5 terminals.

**Phase 2 — Pipeline Metrics (Pillar 3)**
- Kafka + Postgres exporters, Debezium JMX sidecar, Spark Prometheus servlet; 4 dashboards.
- Exit criteria: Prometheus targets page shows all six exporters `up`; kafka consumer lag metric returns non-null after a Spark job runs; Debezium dashboard shows connector RUNNING; Spark dashboard shows batches processed > 0.
- Highest ongoing debug value: consumer lag alone answers most "why is my pipeline slow?" questions.

**Phase 3 — Alerts + Reliability (Pillar 4)**
- 5 new alert rules + contact points; restart policies + healthchecks on every service; MODIFY existing freshness alert to wire contact point.
- Exit criteria: `docker stop ed-pyspark-jupyter` → 5m → `spark_streaming_job_absent` alert in Firing state + notification POST at webhook.site; `docker kill kafka1` → auto-restart within 30s; `make status` shows every service `healthy`.
- Closes the "alerts fire silently" gap.

**Phase 4 — OTEL Collector (optional, migration path)**
- OTEL Collector as unified ingress (filelog + prometheus receivers → loki + prometheusremotewrite exporters); populate `otel_logs`/`otel_traces` ClickHouse tables.
- Exit criteria: OTEL Collector container reports zero dropped/refused batches; Loki still ingests logs (now via OTEL path); OTLP endpoint accepts a test payload from `curl -H 'Content-Type: application/json' -d @sample.json http://localhost:4318/v1/logs`.
- Optional: only ship if the learning path or future tracing plans warrant it.

## Requirements That Will Be Declared

These will become `### Requirement:` blocks in `openspec/specs/observability/spec.md` once the change archives. Listed here for review; **not** authoritative until they exist as scenarios with WHEN/THEN.

| Pillar | Requirement (kebab-name) | One-line summary |
|--------|--------------------------|------------------|
| 1 | `central-log-aggregation` | Alloy tails Docker container logs and ships to Loki with `container`/`image`/`compose_service` labels; 7d retention. |
| 2 | `prometheus-scrape-configuration` | Prometheus with 7d/1GB retention scrapes cAdvisor + node-exporter (Phase 1) and exporters (Phase 2). |
| 2 | `container-metrics-collection` | cAdvisor exposes per-container CPU/mem/net/disk metrics from the Docker socket; scraped every 15s. |
| 1+2 | `grafana-observability-datasources` | Grafana provisioned with Loki + Prometheus datasources alongside existing ClickHouse. |
| 3 | `kafka-lag-metrics` | kafka-exporter surfaces consumer-group lag; Kafka Pipeline dashboard visualizes it. |
| 3 | `debezium-connector-metrics` | Debezium JVM runs with jmx-exporter javaagent exposing connector state + commit lag as Prometheus metrics. |
| 3 | `spark-streaming-metrics` | Spark's Prometheus servlet is enabled; Prometheus scrapes `ed-pyspark-jupyter:4040/metrics/prometheus`. |
| 3 | `postgres-replication-metrics` | postgres-exporter exposes `pg_stat_replication` lag; scraped every 30s. |
| 4 | `infrastructure-alert-rules` | Grafana provisions at minimum 5 alert rules: kafka lag, connector state, spark absence, container memory, restart loop. |
| 4 | `alert-contact-point-webhook` | Default contact point provisioned from `OBS_ALERT_WEBHOOK_URL` env; unset means Grafana-UI-only. |
| 4 | `service-restart-policies` | Stateful services `restart: unless-stopped`; stateless `on-failure:3`; `ed-pyspark-jupyter` unrestarted. |
| 4 | `service-healthchecks` | postgres, kafka1, debezium, clickhouse, schema-registry, grafana, loki, prometheus each declare a `healthcheck:` block. |
| 4 (Phase 4 optional) | `otel-collector-pipeline` | otel-collector-contrib runs filelog + prometheus receivers → loki + prometheusremotewrite exporters. |
| 4 (Phase 4 optional) | `otlp-ingestion-endpoint` | OTEL Collector exposes OTLP gRPC :4317 + HTTP :4318 for future SDK instrumentation. |

## Cross-Capability Modifications

- **`infrastructure`**: `per-service-targets` gains the `up-observability` family; `full-stack-startup` includes the new services; `volume-preservation` and `destructive-teardown` mention `loki_data` + `prometheus_data` volumes; restart policies + healthcheck definitions land in specific service-group compose files.
- **`analytics`**: Grafana grows two new datasources (Loki + Prometheus) alongside existing ClickHouse; six new dashboards land alongside the existing three business dashboards.
- **`data-governance`**: `freshness-slo-and-alert` scenario gains a contact-point reference (closes archived gap).
- **`cdc-pipeline`**: `submit_job.sh` gains Spark Prometheus servlet configs (Phase 2); Debezium docker-compose gains jmx-exporter javaagent sidecar env + bind mounts (Phase 2).

No changes to `python-tooling` or `streamlit-ui` (observability observes them without their needing to change).

## Out of Scope

- Azure VM prod deployment (repo has `infrastructure/terraform/` but this change is local-dev-focused).
- OpenTelemetry SDK instrumentation of Spark jobs or Streamlit views (Phase 4 provides the ingress; SDK integration is a separate future change).
- Production-grade Alertmanager (routing, silencing, HA); Grafana bundled is enough for dev.
- Long-term retention (>7d) or observability data lake.
- Custom-built Docker images (Debezium jmx-exporter is a sidecar, not a rebuild).
- Grafana version bump (10.3.12 stays).
- Log parsing / structured logs beyond what Docker JSON log driver provides.
- Trace-based root cause analysis (Phase 4 lays the OTEL pipe, doesn't add tracing instrumentation).
