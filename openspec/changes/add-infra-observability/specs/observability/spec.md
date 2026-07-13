## ADDED Requirements

> **Status:** Phase 1 (Foundation) and Phase 2 (Pipeline metrics) requirements are decomposed below. Phases 3/4 remain broad placeholders (`alerting-and-notification`, `service-resilience`, `otel-migration-path`) and will be decomposed as those phases land.
>
> **Decomposition status:**
>
> | Placeholder | Decomposed? | Phase-scoped requirements |
> |---|---|---|
> | `log-aggregation` | Yes (Phase 1) | `central-log-aggregation` |
> | `metrics-collection` | Yes (Phases 1+2) | `prometheus-scrape-configuration`, `container-metrics-collection`, `kafka-lag-metrics`, `debezium-connector-metrics`, `spark-streaming-metrics`, `postgres-replication-metrics` |
> | `grafana-observability-datasources` | Yes (Phase 1, spans Pillars 1+2) | `grafana-observability-datasources` |
> | `alerting-and-notification` | Not yet | `infrastructure-alert-rules`, `alert-contact-point-webhook` |
> | `service-resilience` | Not yet | `service-restart-policies`, `service-healthchecks` |
> | `otel-migration-path` (optional Phase 4) | Not yet | `otel-collector-pipeline`, `otlp-ingestion-endpoint` |

**Phase 1 — Foundation (decomposed from `log-aggregation` and `metrics-collection` for the container/host portion).**

### Requirement: central-log-aggregation
All Docker container stdout/stderr output SHALL be tailed by a Grafana Alloy agent (from `grafana/alloy:v1.4.3`) and shipped to a single-binary Loki instance (`grafana/loki:2.9.10`) with filesystem storage and 168-hour (7-day) retention. Each log stream SHALL carry the labels `container`, `image`, `compose_service`, and `stream`. High-cardinality labels (the Docker-daemon `id`, container SHA) SHALL be dropped by Alloy relabeling.

#### Scenario: developer filters logs by container
- **WHEN** a developer opens Grafana Explore, selects the Loki datasource, and queries `{container="debezium"} |= "ERROR"`
- **THEN** matching lines from the debezium container SHALL be returned within a few seconds

#### Scenario: labels bounded to a small set
- **WHEN** a Loki label query `curl -s http://localhost:3100/loki/api/v1/labels` is executed
- **THEN** the returned label set SHALL include `container`, `image`, `compose_service`, `stream` and SHALL NOT include the Docker-daemon `id` label

#### Scenario: retention enforced
- **WHEN** log lines older than 168 hours exist in Loki
- **THEN** they SHALL be removed by the Loki compactor without manual intervention

### Requirement: prometheus-scrape-configuration
A Prometheus instance (`prom/prometheus:v2.54.1`) SHALL run with `--storage.tsdb.retention.time=7d` and `--storage.tsdb.retention.size=1GB` and scrape configs SHALL live in `infrastructure/docker/prometheus/prometheus.yml` with a global 15-second interval. Phase 1 SHALL scrape at minimum `cadvisor:8080` and `node-exporter:9100`; Phase 2 SHALL extend scrapes to include the exporters and JMX/servlet endpoints defined by `kafka-lag-metrics`, `postgres-replication-metrics`, `debezium-connector-metrics`, `spark-streaming-metrics`.

#### Scenario: retention flags applied
- **WHEN** the running Prometheus process is inspected (e.g., `docker inspect prometheus`)
- **THEN** its command line SHALL include both `--storage.tsdb.retention.time=7d` and `--storage.tsdb.retention.size=1GB`

#### Scenario: Phase 1 targets healthy
- **WHEN** `curl -s http://localhost:9090/api/v1/targets | jq '[.data.activeTargets[] | {job, health}]'` is executed
- **THEN** the `cadvisor` and `node-exporter` jobs SHALL both report `up`

### Requirement: container-metrics-collection
cAdvisor (`gcr.io/cadvisor/cadvisor:v0.49.1`) SHALL run mounted read-only on the Docker socket, `/rootfs`, `/sys`, `/var/lib/docker`, and `/dev/disk`, and expose per-container CPU, memory, network, and disk I/O metrics on port 8080 (container-side; host port 8082 to avoid clashing with redpanda-console). node-exporter (`prom/node-exporter:v1.8.2`) SHALL run with `--path.rootfs=/host` and expose host-level metrics on port 9100. Both SHALL be scraped by Prometheus every 15 seconds. The `id` label SHALL be dropped in scrape-side `metric_relabel_configs` to bound cardinality across container restarts.

#### Scenario: per-container metrics available
- **WHEN** the Container Health dashboard is opened in Grafana
- **THEN** every core CDC-pipeline container (postgres, kafka1, debezium, clickhouse) SHALL show non-null CPU-usage and memory-usage panels

#### Scenario: id label dropped
- **WHEN** any Prometheus metric produced by cAdvisor is inspected via `curl -sG 'http://localhost:9090/api/v1/query' --data-urlencode 'query=container_memory_usage_bytes'`
- **THEN** no returned time series SHALL carry an `id` label

### Requirement: grafana-observability-datasources
Grafana SHALL be provisioned with three datasources: the existing `ClickHouse-Analytics` (business data) plus two new observability datasources — `Loki` pointing at `http://loki:3100` and `Prometheus` pointing at `http://prometheus:9090`. Both new datasources SHALL be provisioned as files under `infrastructure/docker/grafana/provisioning/datasources/`, with `editable: false` so a UI-side edit cannot silently drift from the provisioned truth.

#### Scenario: three datasources present after startup
- **WHEN** the Grafana datasources page `http://localhost:3000/datasources` is opened
- **THEN** `ClickHouse-Analytics`, `Loki`, and `Prometheus` SHALL each be listed with a passing "Save & test"

#### Scenario: datasources are not UI-editable
- **WHEN** an admin opens the Loki or Prometheus datasource in Grafana's UI
- **THEN** the "Save" button SHALL be disabled because `editable: false` is set in the provisioned YAML

**Phase 2 — Pipeline metrics (decomposed from `metrics-collection` for the pipeline-source portion).**

### Requirement: kafka-lag-metrics
A `danielqsj/kafka-exporter:v1.8.0` container SHALL run with `platform: linux/amd64` (image is amd64-only), connect to `kafka1:9092`, and expose Kafka broker + consumer-group metrics on port 9308. Prometheus SHALL scrape it every 15s under the `kafka-exporter` job.

#### Scenario: broker metrics available
- **WHEN** the observability stack is up and connected to a running Kafka broker
- **THEN** `curl -sG 'http://localhost:9090/api/v1/query?query=kafka_brokers'` SHALL return at least one series with value 1

#### Scenario: consumer lag observable when Spark is consuming
- **WHEN** a Spark CDC job is running and consuming from `pg.public.*` topics
- **THEN** `kafka_consumergroup_lag_sum` SHALL be queryable from Prometheus and return non-null values for the Spark consumer group; the Kafka Pipeline dashboard SHALL surface it

### Requirement: debezium-connector-metrics
The Debezium container SHALL run with `KAFKA_OPTS=-javaagent:/opt/jmx-exporter/jmx_prometheus_javaagent-<version>.jar=5556:/opt/jmx-exporter/debezium-jmx.yml` and expose Kafka Connect + Debezium JMX metrics at `http://debezium:5556/metrics`. The jmx-exporter jar SHALL be fetched via `scripts/setup_observability.sh` and bind-mounted from `infrastructure/docker/jmx-exporter/` (the jar itself is gitignored). Prometheus SHALL scrape it under the `debezium-jmx` job. The YAML rule file SHALL translate `kafka.connect.*` and `debezium.postgres.*` MBeans into named metrics (`kafka_connect_connector_status`, `debezium_metrics_*`).

#### Scenario: JMX metrics reachable
- **WHEN** the Debezium container has been running for at least 30 seconds under the observability configuration
- **THEN** `curl http://localhost:5556/metrics` SHALL return a Prometheus-formatted response containing at minimum `kafka_connect_connector_status` and `debezium_metrics_millisecondssincelastevent`

#### Scenario: connector state numeric
- **WHEN** the Debezium `pg-connector-ecommerce` is in RUNNING state
- **THEN** `kafka_connect_connector_status{connector="pg-connector-ecommerce", status="running"}` SHALL return 1 in Prometheus

### Requirement: spark-streaming-metrics
The Spark CDC jobs submitted via `data-platform/streaming/spark/scripts/submit_job.sh` SHALL be launched with `--conf spark.ui.prometheus.enabled=true --conf spark.metrics.conf=<path-to-metrics.properties>`. The `metrics.properties` file SHALL live under `data-platform/streaming/spark/conf/` and declare the built-in `PrometheusServlet` sink. Prometheus SHALL scrape `ed-pyspark-jupyter:4040/metrics/prometheus` under the `spark` job; scrape failures while no Spark job is running SHALL be treated as expected (target `down` is benign).

#### Scenario: metrics endpoint available while a job runs
- **WHEN** a Spark CDC job has been running in production mode for at least 30 seconds
- **THEN** `curl http://localhost:4040/metrics/prometheus` SHALL return Prometheus-formatted metrics including at minimum `spark_streaming_query_lastCompletedBatchId` and `spark_streaming_query_inputRate`

#### Scenario: target down when no Spark job is running
- **WHEN** no Spark job is executing (Spark UI port not bound to a driver)
- **THEN** the Prometheus target `spark` MAY report `down` and this SHALL NOT be considered a stack failure; the Spark Streaming dashboard SHALL indicate the job is not running via the `up{job="spark"}` panel

### Requirement: postgres-replication-metrics
A `prometheuscommunity/postgres-exporter:v0.15.0` container SHALL run with a connection string pointing at the source Postgres database and a custom queries file at `infrastructure/docker/postgres-exporter/queries.yaml` that surfaces `pg_replication_slots` state and `pg_stat_replication` reply lag. Prometheus SHALL scrape it under the `postgres-exporter` job. The custom queries SHALL specifically expose the Debezium replication slot state so the Postgres Replication dashboard can show whether Debezium is connected and how many bytes of WAL are unconsumed.

#### Scenario: Debezium slot state observable
- **WHEN** the Debezium connector is registered and connected to Postgres
- **THEN** `pg_replication_active{slot_name="debezium_slot"}` SHALL be queryable in Prometheus and return 1

#### Scenario: replication lag bytes observable
- **WHEN** postgres-exporter has completed at least one scrape
- **THEN** `pg_replication_lag_bytes{slot_name="debezium_slot"}` SHALL be queryable and return a non-negative value

### Requirement: alerting-and-notification
Alert rules SHALL be provisioned covering the failure classes the pipeline actually hits, and each alert SHALL be wired to at least one contact point so notifications reach an external channel (webhook.site, Slack, or similar) rather than dying in the Grafana UI.

#### Scenario: connector failure notifies
- **WHEN** the Debezium connector `pg-connector-ecommerce` transitions to a state other than RUNNING for more than 1 minute
- **THEN** an alert SHALL fire AND a notification SHALL be posted to the configured webhook contact point

### Requirement: service-resilience
Every service in the stack SHALL declare an appropriate `restart:` policy (stateful services SHALL restart unless stopped explicitly; stateless services SHALL restart on failure), and services with a well-defined readiness check SHALL declare a `healthcheck:` block so `depends_on: { condition: service_healthy }` can be used to sequence startup instead of time-based sleeps.

#### Scenario: kafka auto-recovers from crash
- **WHEN** `docker kill kafka1` is executed against a running stack
- **THEN** within 30 seconds `docker ps` SHALL show `kafka1` in `Up (healthy)` state again, with the restart handled by Docker daemon per the declared policy

#### Scenario: connector waits for kafka health
- **WHEN** the stack starts from a cold `make up`
- **THEN** the `debezium` container SHALL NOT start until `kafka1`'s healthcheck reports `healthy`, replacing the previous time-based startup race
