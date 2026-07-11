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

-- ----------------------------------------------------------------------------
-- Governance Phase 2 — RBAC
-- ----------------------------------------------------------------------------
-- analyst_readonly is the role Grafana connects as. It gets SELECT on the
-- CDC tables plus row policies that hide tombstones (_deleted = 1) so
-- analytics dashboards never surface deleted state.
-- The matching user is created by
--   /docker-entrypoint-initdb.d/create_governance_users.sh
-- because the ClickHouse init loader doesn't interpolate env vars inside
-- .sql files and we don't want the analyst password checked into git.

CREATE ROLE IF NOT EXISTS analyst_readonly;

GRANT SELECT ON ecommerce_analytics.customers_cdc TO analyst_readonly;
GRANT SELECT ON ecommerce_analytics.products_cdc  TO analyst_readonly;
GRANT SELECT ON ecommerce_analytics.orders_cdc    TO analyst_readonly;

CREATE ROW POLICY IF NOT EXISTS hide_tombstones_customers
    ON ecommerce_analytics.customers_cdc
    FOR SELECT USING _deleted = 0
    TO analyst_readonly;

CREATE ROW POLICY IF NOT EXISTS hide_tombstones_products
    ON ecommerce_analytics.products_cdc
    FOR SELECT USING _deleted = 0
    TO analyst_readonly;

CREATE ROW POLICY IF NOT EXISTS hide_tombstones_orders
    ON ecommerce_analytics.orders_cdc
    FOR SELECT USING _deleted = 0
    TO analyst_readonly;
