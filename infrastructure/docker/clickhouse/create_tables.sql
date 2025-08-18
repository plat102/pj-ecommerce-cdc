CREATE DATABASE IF NOT EXISTS ecommerce_analytics;
CREATE TABLE IF NOT EXISTS ecommerce_analytics.customers_cdc (
    id Int64,
    name String,
    email String,
    created_at Int64,
    _version UInt64,
    _deleted UInt8 DEFAULT 0
) ENGINE = ReplacingMergeTree(_version)
ORDER BY id;

-- Products CDC table
CREATE TABLE IF NOT EXISTS ecommerce_analytics.products_cdc (
    id Int64,
    name String,
    price Decimal(10, 2),
    created_at Int64,
    _version UInt64,
    _deleted UInt8 DEFAULT 0
) ENGINE = ReplacingMergeTree(_version)
ORDER BY id;
