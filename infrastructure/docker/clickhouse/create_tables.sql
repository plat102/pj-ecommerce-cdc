CREATE DATABASE IF NOT EXISTS ecommerce_analytics;
CREATE TABLE ecommerce_analytics.customers_cdc (
    id Int64,
    name String,
    email String,
    created_at Int64,
    _version UInt64,
    _deleted UInt8 DEFAULT 0
) ENGINE = ReplacingMergeTree(_version)
ORDER BY id;