# Analytics Platform

Real-time analytics platform for ecommerce CDC data using ClickHouse and Grafana.

## Architecture Overview

```
PostgreSQL → Debezium → Kafka → Spark → ClickHouse → Grafana
                                          ↗️ Views      ↗️ Dashboards
```

### Components

- **ClickHouse**: OLAP database for fast analytics queries
- **Grafana**: Visualization and dashboards
- **Analytics Views**: Pre-computed business metrics

### Auto-refresh Mechanism
```txt
Grafana Dashboard──┐
                   │ (query every 30s)
                   ↓
ClickHouse Views ──┐
                   │ (computed on-demand)
                   ↓
Raw CDC Tables ────┐
                   │ (updated real-time)
                   ↓
Spark Streaming ───┐
                   │ (process CDC events)
                   ↓
Kafka Topics ──────● (real-time stream)
```

## Features Summary

### 📊 Business Metrics
- Daily/monthly sales trends
- Customer insights and VIP analysis
- Product performance tracking
- Real-time activity monitoring

### ⚡ Real-time Updates
- Auto-refresh dashboards (30s-1m)
- CDC pipeline ensures data freshness
- Low latency analytics (seconds)

### 🎯 Key Dashboards
- **Executive Dashboard**: Business overview and KPIs
- **Customer Insights**: Customer behavior and segmentation

## Quick Start

### Setup
```bash
# Start analytics services
./scripts/setup_simple_analytics.sh
```

### Access
- **Grafana**: http://localhost:3000 (admin/admin123)
- **ClickHouse**: http://localhost:8123

### Import Dashboards
1. Open Grafana → Import
2. Upload: `data-platform/dashboards/grafana/executive-dashboard.json`
3. Upload: `data-platform/dashboards/grafana/customer-insights.json`

## Analytics Views

### Sales Analytics
```sql
daily_sales_summary    -- Daily orders, items, customers
monthly_sales_summary  -- Monthly trends
hourly_orders_trend    -- Hourly patterns (last 24h)
```

### Customer Analytics
```sql
customer_metrics       -- Per-customer metrics
top_customers_by_orders -- Top 50 VIP customers
```

### Product Analytics
```sql
product_performance    -- Product performance metrics
top_selling_products   -- Top 20 best sellers
```

### System Monitoring
```sql
recent_activity        -- Last 24h activity
data_freshness         -- CDC data lag monitoring
```

## Data Flow

### Real-time Pipeline
1. **Source**: PostgreSQL database changes
2. **Capture**: Debezium CDC events → Kafka
3. **Process**: Spark Streaming → ClickHouse
4. **Analyze**: ClickHouse views compute metrics
5. **Visualize**: Grafana dashboards display results

### Example: New Order
```
🛒 Order Created → CDC Event → Kafka → Spark → ClickHouse → Grafana Update
                                                    ↓
                                            Views Recalculated
```

```txt
🛒 New Order Created:
└── PostgreSQL INSERT
    └── Debezium captures change
        └── Kafka receives CDC event
            └── Spark processes & writes to ClickHouse
                └── Views auto-update calculations
                    └── Grafana shows new metrics (next refresh)
```

## File Structure

```
data-platform/dashboards/
├── clickhouse/
│   └── analytics_views.sql      # ClickHouse views
└── grafana/
    ├── executive-dashboard.json # Main business dashboard
    └── customer-insights.json   # Customer analytics
```

## Operations Guide
### Configuration

#### ClickHouse
- Database: `ecommerce_analytics`
- HTTP Port: 8123
- Native Port: 9000

#### Grafana
- Auto-configured ClickHouse datasource
- Pre-built dashboards
- Real-time refresh

### Extending Analytics

#### Adding New Views
1. Edit `analytics_views.sql`
2. Create view with business logic
3. Deploy: `docker exec -i clickhouse clickhouse-client < analytics_views.sql`

#### Creating Dashboards
1. Build queries in ClickHouse
2. Create panels in Grafana
3. Export JSON for version control

### Troubleshooting

#### Common Issues
- **No data**: Check CDC pipeline and Spark jobs
- **Stale data**: Verify data_freshness view
- **Slow queries**: Review ClickHouse query logs

## Performance

### Optimizations
- ClickHouse ReplacingMergeTree for CDC deduplication
- Materialized views for heavy computations
- Efficient time-based partitioning

### Monitoring
- Data freshness tracking
- Query performance metrics
- Dashboard usage analytics


### Useful Commands
```bash
# Check ClickHouse
docker exec -it clickhouse clickhouse-client

# Test analytics views
USE ecommerce_analytics;
SELECT * FROM daily_sales_summary LIMIT 5;

# View logs
docker-compose -f docker-compose.analytics.yml logs
```