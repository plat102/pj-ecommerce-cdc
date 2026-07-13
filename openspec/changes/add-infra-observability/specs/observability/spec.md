## ADDED Requirements

> **Status:** Placeholder requirements for the design-only phase of this proposal. Detailed scenarios for each phase (foundation, pipeline metrics, alerts + reliability, optional OTEL) will be filled in as that phase reaches implementation. See `design.md` for the full direction.
>
> **On archive**, each broad placeholder below decomposes into the phase-scoped requirements listed in `design.md` § "Requirements That Will Be Declared":
>
> | Placeholder here | Decomposes into (on archive) |
> |---|---|
> | `log-aggregation` | `central-log-aggregation`, `grafana-observability-datasources` (Loki side) |
> | `metrics-collection` | `prometheus-scrape-configuration`, `container-metrics-collection`, `grafana-observability-datasources` (Prom side), `kafka-lag-metrics`, `debezium-connector-metrics`, `spark-streaming-metrics`, `postgres-replication-metrics` |
> | `alerting-and-notification` | `infrastructure-alert-rules`, `alert-contact-point-webhook` |
> | `service-resilience` | `service-restart-policies`, `service-healthchecks` |
> | `otel-migration-path` (optional Phase 4) | `otel-collector-pipeline`, `otlp-ingestion-endpoint` |

### Requirement: log-aggregation
All Docker container stdout/stderr output SHALL be tailed by a shipping agent and stored in a queryable log store, with each line tagged by container identity so a developer can filter to one service across the whole stack.

#### Scenario: developer filters logs by container
- **WHEN** a developer opens Grafana Explore, selects the log datasource, and queries `{container="debezium"} |= "ERROR"`
- **THEN** matching lines from the debezium container SHALL be returned within a few seconds, without requiring shell access or `docker logs`

### Requirement: metrics-collection
Infrastructure and pipeline metrics from every service in the stack SHALL be scraped by a Prometheus-compatible collector and be queryable via a Grafana datasource, covering container-level (CPU, memory, network, disk) and pipeline-level (Kafka consumer lag, Debezium connector state, Spark streaming progress, Postgres replication lag) signals.

#### Scenario: kafka consumer lag observable
- **WHEN** a Spark CDC job is running and consuming from a `pg.public.*` topic
- **THEN** the metric `kafka_consumergroup_lag_sum` for that consumer group SHALL be queryable from Grafana's Prometheus datasource and SHALL return non-null values

#### Scenario: container memory observable
- **WHEN** the observability dashboard "Container Health" is opened
- **THEN** every core CDC-pipeline container (postgres, kafka1, debezium, clickhouse) SHALL show non-null CPU and memory panels

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
