# Analytics

Real-time analytics surface built on top of the CDC pipeline: **ClickHouse** as the OLAP store, **Grafana** as the visualization + alerting layer.

Prerequisite reading: [`architecture.md`](architecture.md) covers the pipeline plumbing (Postgres → Debezium → Kafka → Spark → ClickHouse). This doc picks up at "row has landed in ClickHouse; now what?".

## Deduplication model

Every CDC target table (`customers_cdc`, `products_cdc`, `orders_cdc`) uses the `ReplacingMergeTree(_version)` engine ordered by the primary key `id`, with two extra columns:

- `_version` (`UInt64`) — Debezium `ts_ms`; the newest event wins.
- `_deleted` (`UInt8`) — set to 1 when the Debezium `op = "d"`.

Any query that needs the current state uses the `FINAL` modifier and filters `_deleted = 0`:

```sql
SELECT * FROM ecommerce_analytics.customers_cdc FINAL WHERE _deleted = 0;
```

Merges are asynchronous, so queries without `FINAL` may return duplicates. TTL clauses drop tombstones after 90 days and any row after 2 years — see [`governance.md`](governance.md#retention--ttl).

DDL: `infrastructure/docker/clickhouse/create_tables.sql`.

## Grafana datasources

Three provisioned datasources:

| Datasource | Points at | `editable` | Purpose |
|---|---|---|---|
| `ClickHouse-Analytics` | `http://clickhouse:8123` | `true` | Business data — used by all analytics dashboards. Connects as `analyst_readonly` (row policy filters tombstones automatically). |
| `Loki` | `http://loki:3100` | `false` | Container logs (via Grafana Explore) |
| `Prometheus` | `http://prometheus:9090` | `false` | Pipeline + host metrics |

The ClickHouse datasource is left editable so analysts can tweak query settings; observability datasources are locked to prevent UI-side drift from the provisioned config.

Files: `infrastructure/docker/grafana/provisioning/datasources/`.

## Provisioned dashboards

Sourced from `data-platform/dashboards/grafana/`, synced into Grafana by `make sync-dashboards` (calls `scripts/sync_dashboards.sh`):

- `executive-dashboard.json` — business overview and KPIs
- `customer-insights.json` — customer behavior and segmentation
- `test-dashboard.json` — reserved for ad-hoc panels

Add a new dashboard by dropping its JSON into `data-platform/dashboards/grafana/` and running `make reload-grafana` (sync + restart Grafana container).

## Analytics views

Defined in `data-platform/dashboards/clickhouse/analytics_views.sql`.

**Sales**
```sql
daily_sales_summary     -- daily orders, items, customers
monthly_sales_summary   -- monthly trends
hourly_orders_trend     -- hourly patterns, last 24 h
```

**Customer**
```sql
customer_metrics             -- per-customer metrics
top_customers_by_orders      -- top 50 VIP customers
```

**Product**
```sql
product_performance   -- performance metrics per product
top_selling_products  -- top 20 best sellers
```

**System monitoring**
```sql
recent_activity   -- last-24 h activity
data_freshness    -- CDC lag, drives cdc_freshness_10min_slo alert
```

Redeploy after edits:
```sh
docker exec -i clickhouse clickhouse-client < data-platform/dashboards/clickhouse/analytics_views.sql
```

## Auto-refresh chain

```
Grafana dashboard
  | (query every 30s)
  v
ClickHouse view  (computed on demand)
  | 
  v
*_cdc tables  (updated by Spark micro-batches)
  |
  v
Spark Structured Streaming  (Kafka -> ClickHouse)
  |
  v
Kafka topic  pg.public.{table}
```

## Access

- Grafana — http://localhost:3000, login `admin` / `<GRAFANA_ADMIN_PASSWORD>` (from `infrastructure/docker/.env`).
- ClickHouse HTTP — http://localhost:8123. Interactive: `make clickhouse-client`.

## Troubleshooting

- **No data**: check the CDC pipeline (`make check-connector`, `make cdc-status`).
- **Stale data**: query the `data_freshness` view; the `cdc_freshness_10min_slo` alert fires when lag exceeds threshold.
- **Slow queries**: inspect ClickHouse query logs (`SELECT * FROM system.query_log ORDER BY event_time DESC LIMIT 20`).
- **Dashboard shows tombstones**: dashboards must use `FINAL WHERE _deleted = 0` (the `analyst_readonly` row policy also strips tombstones).
