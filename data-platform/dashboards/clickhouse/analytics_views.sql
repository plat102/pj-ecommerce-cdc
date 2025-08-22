-- ===========================================
-- ClickHouse Analytics Views & Tables
-- Ecommerce CDC Analytics Foundation
-- ===========================================

-- Switch to analytics database
USE ecommerce_analytics;

-- ===========================================
-- 1. DAILY SALES METRICS
-- ===========================================

-- Daily sales summary view
CREATE OR REPLACE VIEW daily_sales_summary AS
SELECT 
    toDate(fromUnixTimestamp64Milli(order_time)) as date,
    count(*) as total_orders,
    sum(quantity) as total_items_sold,
    countDistinct(customer_id) as unique_customers,
    countDistinct(product_id) as unique_products_sold,
    avg(quantity) as avg_items_per_order
FROM orders_cdc 
WHERE _deleted = 0
GROUP BY date
ORDER BY date DESC;

-- Monthly sales trends
CREATE OR REPLACE VIEW monthly_sales_summary AS
SELECT 
    toYYYYMM(fromUnixTimestamp64Milli(order_time)) as month,
    count(*) as total_orders,
    sum(quantity) as total_items_sold,
    countDistinct(customer_id) as unique_customers,
    round(avg(quantity), 2) as avg_items_per_order
FROM orders_cdc 
WHERE _deleted = 0
GROUP BY month
ORDER BY month DESC;

-- ===========================================
-- 2. CUSTOMER ANALYTICS
-- ===========================================

-- Customer metrics view
CREATE OR REPLACE VIEW customer_metrics AS
SELECT 
    c.id as customer_id,
    c.name,
    c.email,
    fromUnixTimestamp64Milli(c.created_at) as customer_since,
    count(o.id) as total_orders,
    sum(o.quantity) as total_items_purchased,
    min(fromUnixTimestamp64Milli(o.order_time)) as first_order_date,
    max(fromUnixTimestamp64Milli(o.order_time)) as last_order_date,
    round(avg(o.quantity), 2) as avg_items_per_order,
    dateDiff('day', min(fromUnixTimestamp64Milli(o.order_time)), max(fromUnixTimestamp64Milli(o.order_time))) as customer_lifespan_days
FROM customers_cdc c
LEFT JOIN orders_cdc o ON c.id = o.customer_id AND o._deleted = 0
WHERE c._deleted = 0
GROUP BY c.id, c.name, c.email, c.created_at
HAVING total_orders > 0
ORDER BY total_orders DESC;

-- Top customers by orders
CREATE OR REPLACE VIEW top_customers_by_orders AS
SELECT 
    customer_id,
    name,
    email,
    total_orders,
    total_items_purchased,
    last_order_date
FROM customer_metrics
ORDER BY total_orders DESC
LIMIT 50;

-- ===========================================
-- 3. PRODUCT ANALYTICS  
-- ===========================================

-- Product performance view
CREATE OR REPLACE VIEW product_performance AS
SELECT 
    p.id as product_id,
    p.name as product_name,
    p.price,
    count(o.id) as total_orders,
    sum(o.quantity) as total_quantity_sold,
    countDistinct(o.customer_id) as unique_customers,
    round(avg(o.quantity), 2) as avg_quantity_per_order,
    min(fromUnixTimestamp64Milli(o.order_time)) as first_sale_date,
    max(fromUnixTimestamp64Milli(o.order_time)) as last_sale_date
FROM products_cdc p
LEFT JOIN orders_cdc o ON p.id = o.product_id AND o._deleted = 0
WHERE p._deleted = 0
GROUP BY p.id, p.name, p.price
HAVING total_orders > 0
ORDER BY total_quantity_sold DESC;

-- Top selling products
CREATE OR REPLACE VIEW top_selling_products AS
SELECT 
    product_id,
    product_name,
    price,
    total_orders,
    total_quantity_sold,
    unique_customers,
    last_sale_date
FROM product_performance
ORDER BY total_quantity_sold DESC
LIMIT 20;

-- ===========================================
-- 4. REAL-TIME METRICS
-- ===========================================

-- Recent activity (last 24 hours)
CREATE OR REPLACE VIEW recent_activity AS
SELECT 
    'orders' as activity_type,
    count(*) as count_24h,
    max(fromUnixTimestamp64Milli(order_time)) as last_activity
FROM orders_cdc 
WHERE fromUnixTimestamp64Milli(order_time) >= now() - INTERVAL 1 DAY
  AND _deleted = 0

UNION ALL

SELECT 
    'customers' as activity_type,
    count(*) as count_24h,
    max(fromUnixTimestamp64Milli(created_at)) as last_activity
FROM customers_cdc 
WHERE fromUnixTimestamp64Milli(created_at) >= now() - INTERVAL 1 DAY
  AND _deleted = 0

UNION ALL

SELECT 
    'products' as activity_type,
    count(*) as count_24h,
    max(fromUnixTimestamp64Milli(created_at)) as last_activity
FROM products_cdc 
WHERE fromUnixTimestamp64Milli(created_at) >= now() - INTERVAL 1 DAY
  AND _deleted = 0;

-- Hourly order trends (last 24 hours)
CREATE OR REPLACE VIEW hourly_orders_trend AS
SELECT 
    toHour(fromUnixTimestamp64Milli(order_time)) as hour,
    count(*) as order_count,
    sum(quantity) as total_items
FROM orders_cdc 
WHERE fromUnixTimestamp64Milli(order_time) >= now() - INTERVAL 1 DAY
  AND _deleted = 0
GROUP BY hour
ORDER BY hour;

-- ===========================================
-- 5. SYSTEM HEALTH METRICS
-- ===========================================

-- Data freshness check
CREATE OR REPLACE VIEW data_freshness AS
SELECT 
    'customers' as table_name,
    count(*) as total_records,
    max(fromUnixTimestamp64Milli(_version)) as last_update,
    dateDiff('minute', max(fromUnixTimestamp64Milli(_version)), now()) as minutes_since_last_update
FROM customers_cdc

UNION ALL

SELECT 
    'products' as table_name,
    count(*) as total_records,
    max(fromUnixTimestamp64Milli(_version)) as last_update,
    dateDiff('minute', max(fromUnixTimestamp64Milli(_version)), now()) as minutes_since_last_update
FROM products_cdc

UNION ALL

SELECT 
    'orders' as table_name,
    count(*) as total_records,
    max(fromUnixTimestamp64Milli(_version)) as last_update,
    dateDiff('minute', max(fromUnixTimestamp64Milli(_version)), now()) as minutes_since_last_update
FROM orders_cdc;

-- ===========================================
-- 6. MATERIALIZED VIEW FOR PERFORMANCE
-- ===========================================

-- Daily aggregation materialized view (for fast dashboard queries)
CREATE TABLE IF NOT EXISTS daily_metrics_mv (
    date Date,
    total_orders UInt64,
    total_customers UInt64,
    total_items_sold UInt64,
    unique_products_sold UInt64,
    avg_items_per_order Float64
) ENGINE = SummingMergeTree()
ORDER BY date;

-- Populate materialized view (run this periodically)
INSERT INTO daily_metrics_mv
SELECT 
    toDate(fromUnixTimestamp64Milli(order_time)) as date,
    count(*) as total_orders,
    countDistinct(customer_id) as total_customers,
    sum(quantity) as total_items_sold,
    countDistinct(product_id) as unique_products_sold,
    avg(quantity) as avg_items_per_order
FROM orders_cdc 
WHERE _deleted = 0
  AND toDate(fromUnixTimestamp64Milli(order_time)) = today() - 1
GROUP BY date;
