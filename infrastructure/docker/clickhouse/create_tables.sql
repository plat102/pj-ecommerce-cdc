CREATE DATABASE IF NOT EXISTS ecommerce_analytics;
CREATE TABLE IF NOT EXISTS ecommerce_analytics.customers_cdc (
    id Int64,
    name String,
    email String,
    created_at Int64,
    _version UInt64,
    _deleted UInt8 DEFAULT 0
) ENGINE = ReplacingMergeTree(_version)
ORDER BY id
TTL toDateTime(_version / 1000) + INTERVAL 90 DAY DELETE WHERE _deleted = 1,
    toDateTime(_version / 1000) + INTERVAL 2 YEAR DELETE;

-- Products CDC table
CREATE TABLE IF NOT EXISTS ecommerce_analytics.products_cdc (
    id Int64,
    name String,
    price Decimal(10, 2),
    created_at Int64,
    _version UInt64,
    _deleted UInt8 DEFAULT 0
) ENGINE = ReplacingMergeTree(_version)
ORDER BY id
TTL toDateTime(_version / 1000) + INTERVAL 90 DAY DELETE WHERE _deleted = 1,
    toDateTime(_version / 1000) + INTERVAL 2 YEAR DELETE;

-- Orders CDC table
CREATE TABLE IF NOT EXISTS ecommerce_analytics.orders_cdc (
    id Int64,
    customer_id Int64,
    product_id Int64,
    quantity Int32,
    order_time Int64,
    _version UInt64,
    _deleted UInt8 DEFAULT 0
) ENGINE = ReplacingMergeTree(_version)
ORDER BY id
TTL toDateTime(_version / 1000) + INTERVAL 90 DAY DELETE WHERE _deleted = 1,
    toDateTime(_version / 1000) + INTERVAL 2 YEAR DELETE;
