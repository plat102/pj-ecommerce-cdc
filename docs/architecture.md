# Architecture

End-to-end Change Data Capture demo: **PostgreSQL → Debezium → Kafka → PySpark Structured Streaming → ClickHouse → Grafana**, with a Streamlit UI for driving CDC events, a Loki+Prometheus observability stack, and a governance layer (Apicurio schema registry, PII masking, GX validation gate, DLQ, RBAC, retention). Everything runs locally via Docker Compose orchestrated by the `Makefile` at the repo root.

Prerequisite: create `infrastructure/docker/.env` from `.env.example` before running any `make` target — the Makefile has no fallback.

## High-level architecture

```mermaid
flowchart LR
    subgraph Source["Source"]
        PG[(PostgreSQL<br/>ecommerce)]
        UI[Streamlit UI<br/>CRUD + Kafka monitor]
    end

    subgraph CDC["CDC capture"]
        DBZ[Debezium<br/>Kafka Connect]
        REG[Apicurio<br/>Schema Registry]
        RP[Redpanda Console]
    end

    subgraph Bus["Streaming bus"]
        K[(Kafka<br/>pg.public.customers<br/>pg.public.products<br/>pg.public.orders)]
    end

    subgraph Streaming["Streaming"]
        SP["Spark Structured Streaming<br/>customers / products / orders jobs<br/>PII masking + GX gate"]
    end

    subgraph Serving["Serving"]
        CH[("ClickHouse<br/>*_cdc ReplacingMergeTree<br/>analytics views")]
        GF[Grafana<br/>dashboards + alerts]
    end

    subgraph Obs["Observability (sidecar)"]
        ALLOY[Grafana Alloy] --> LOKI[(Loki)]
        EXP["cAdvisor / node-exporter<br/>Kafka / Postgres / Debezium-JMX / Spark exporters"] --> PROM[("Prometheus")]
        OTEL["OTEL Collector<br/>OTLP :4317 / :4318"]
        OTEL --> LOKI
        OTEL --> CH
    end

    subgraph Gov["Governance & DLQ"]
        GX["GX validation gate"] -.->|bad rows| DLQ[("*_dlq topics")]
        DBZ -.->|"deser errors<br/>Phase 1"| CDLQ[("debezium_connect_dlq")]
    end

    UI -->|writes| PG
    UI -->|read-only| K
    PG --> DBZ
    DBZ <--> REG
    DBZ --> K
    RP -.-> K
    K --> SP
    SP --> GX
    GX --> CH
    CH --> GF
    LOKI --> GF
    PROM --> GF
```

## Components

| Component | Host port(s) | Purpose |
|---|---|---|
| PostgreSQL | 5432 | Source OLTP database (`ecommerce`) |
| Debezium (Kafka Connect) | 8083 (REST), 5556 (JMX) | Captures WAL → Kafka; Apicurio Avro converter |
| Debezium UI | 8085 | Web UI for connector state |
| Apicurio Registry | 8081 | Avro schema storage (`http://schema-registry:8080/apis/registry/v2` in-network) |
| Kafka (kafka1) + Zookeeper | 9092 | Streaming bus, topics `pg.public.{customers,products,orders}` |
| Redpanda Console | 8080 | Read-only Kafka browser |
| Spark (ed-pyspark-jupyter) | 4040 (UI), 8888 (Jupyter) | PySpark Structured Streaming jobs |
| ClickHouse | 8123 (HTTP), 9000 (native) | OLAP store (`ecommerce_analytics`) with `ReplacingMergeTree` CDC tables |
| Streamlit UI | 8501 | CRUD driver + Kafka monitor |
| Grafana | 3000 | Dashboards + Unified Alerting; three provisioned datasources (ClickHouse, Loki, Prometheus) |
| Loki | 3100 | Log store (7-day retention) |
| Prometheus | 9090 | Metrics store (7d / 1GB cap) |
| Grafana Alloy | 12345 | Tails container stdout → Loki |
| cAdvisor | 8082 | Per-container CPU/mem/net/disk metrics |
| node-exporter | 9100 | Host-level metrics |
| Kafka / Postgres / JMX exporters | 9308, 9187, 5556 | Pipeline-source metrics |
| OTEL Collector | 4317 (gRPC), 4318 (HTTP), 8889 (self-metrics) | Unified ingress → Loki + ClickHouse `otel_logs` / `otel_traces` |

Docker Compose is split into seven files under `infrastructure/docker/` (`db`, `kafka`, `debezium`, `ui`, `spark`, `analytics`, `observability`) — `make up` composes them all under the `ecommerce-cdc` project name. Common Makefile targets: `make up` / `make down` / `make stop` / `make start` / `make status` / `make logs`; per-service groups have their own `up-*` / `down-*` / `logs-*` / `sh-*` targets. Run `make help` (or read the `Makefile`) for the full list.

## Record flow (single row)

```mermaid
sequenceDiagram
    autonumber
    participant PG as PostgreSQL
    participant DBZ as Debezium
    participant REG as Apicurio
    participant K as Kafka<br/>pg.public.customers
    participant SP as Spark job<br/>customers_cdc
    participant CH as ClickHouse<br/>customers_cdc
    participant GF as Grafana

    PG->>DBZ: WAL entry (INSERT / UPDATE / DELETE)
    DBZ->>REG: register / fetch Avro schema
    DBZ->>K: publish Debezium envelope
    K->>SP: micro-batch (startingOffsets=latest)
    Note over SP: parse Debezium envelope,<br/>decode DECIMAL via UDF,<br/>hash/tokenize PII,<br/>set _version = ts_ms, _deleted = (op=="d")
    SP->>SP: GX validation gate
    alt row passes
        SP->>CH: foreachBatch JDBC append
    else row fails
        SP->>K: publish to {table}_dlq
    end
    SP->>SP: commit checkpoint<br/>{CHECKPOINT_LOCATION}/{table}/v1
    GF->>CH: 30s dashboard refresh<br/>(SELECT ... FINAL WHERE _deleted=0)
```

## Cross-cutting concerns

- **Analytics** — dedup model, provisioned dashboards, ClickHouse views. See [`analytics.md`](analytics.md).
- **Observability** — Loki+Alloy logs, Prometheus + exporters, five infra alerts, optional OTEL Collector. See [`observability.md`](observability.md).
- **Governance & DLQ** — Apicurio schema contracts, PII masking, GX gate, DLQ topology (GX DLQ applied; Kafka Connect DLQ Phase 1 applied; Spark sink DLQ proposed), RBAC, retention/TTL. See [`governance.md`](governance.md).

## Repo layout

See [`project-structure.md`](project-structure.md).

## Local service URLs (after `make up`)

Core:
- Streamlit UI — http://localhost:8501
- Grafana — http://localhost:3000 (`admin` / `<GRAFANA_ADMIN_PASSWORD>` from `infrastructure/docker/.env`)
- Debezium UI — http://localhost:8085 · Connect REST — http://localhost:8083
- Redpanda Console — http://localhost:8080
- Apicurio Registry — http://localhost:8081
- ClickHouse — http://localhost:8123 (HTTP) · 9000 (native)
- Spark UI — http://localhost:4040 · Jupyter — http://localhost:8888

Observability:
- Prometheus — http://localhost:9090
- Loki — http://localhost:3100 (query API only; use Grafana Explore)
- cAdvisor — http://localhost:8082 · node-exporter — http://localhost:9100/metrics
- Alloy — http://localhost:12345
- OTEL Collector — self-metrics http://localhost:8889/metrics · OTLP gRPC :4317 · OTLP HTTP :4318

## Screenshots

- ![Debezium UI](images/debezium-ui.png)
- ![Redpanda Console](images/kafka-console.png)
- ![Streamlit UI](images/streamlit-ui.png)
- ![Grafana](images/grafana.png)
