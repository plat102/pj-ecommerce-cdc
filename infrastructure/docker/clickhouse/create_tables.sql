CREATE DATABASE IF NOT EXISTS ecommerce_analytics;
CREATE TABLE IF NOT EXISTS ecommerce_analytics.customers_cdc (
    id Int64 COMMENT 'Customer PK, sourced from postgres public.customers.id',
    name String COMMENT 'Tokenized name (initial + short salted hash). See openspec data-governance pii-tokenization-customers-name.',
    email String COMMENT 'Deterministic SHA-256 of the raw email under PII_SALT (64-char hex). See pii-hashing-customers-email.',
    created_at Int64 COMMENT 'Source row creation timestamp (microseconds since epoch, from Debezium)',
    _version UInt64 COMMENT 'Debezium ts_ms; used by ReplacingMergeTree to dedupe',
    _deleted UInt8 DEFAULT 0 COMMENT '1 when the source row was deleted (op=d); row policies hide these from analysts'
) ENGINE = ReplacingMergeTree(_version)
ORDER BY id
COMMENT 'CDC-projected customers table. Owner: data-platform. Source: postgres.public.customers via Debezium/Spark. Contains hashed/tokenized PII only — NEVER put raw email or name here.'
TTL toDateTime(_version / 1000) + INTERVAL 90 DAY DELETE WHERE _deleted = 1,
    toDateTime(_version / 1000) + INTERVAL 2 YEAR DELETE;

-- Products CDC table
CREATE TABLE IF NOT EXISTS ecommerce_analytics.products_cdc (
    id Int64 COMMENT 'Product PK, from postgres public.products.id',
    name String COMMENT 'Product display name (not PII)',
    price Decimal(10, 2) COMMENT 'Decoded from Debezium base64 NUMERIC via decode_decimal_udf',
    created_at Int64 COMMENT 'Source row creation timestamp (microseconds since epoch)',
    _version UInt64 COMMENT 'Debezium ts_ms; ReplacingMergeTree dedupe key',
    _deleted UInt8 DEFAULT 0 COMMENT '1 when the source row was deleted'
) ENGINE = ReplacingMergeTree(_version)
ORDER BY id
COMMENT 'CDC-projected products table. Owner: data-platform. Source: postgres.public.products.'
TTL toDateTime(_version / 1000) + INTERVAL 90 DAY DELETE WHERE _deleted = 1,
    toDateTime(_version / 1000) + INTERVAL 2 YEAR DELETE;

-- Orders CDC table
CREATE TABLE IF NOT EXISTS ecommerce_analytics.orders_cdc (
    id Int64 COMMENT 'Order PK, from postgres public.orders.id',
    customer_id Int64 COMMENT 'FK to customers_cdc.id (joinable across hashed identities via customers_cdc.id since id is not PII)',
    product_id Int64 COMMENT 'FK to products_cdc.id',
    quantity Int32 COMMENT 'Order line quantity; positive integer',
    order_time Int64 COMMENT 'Source order placement time (microseconds since epoch)',
    _version UInt64 COMMENT 'Debezium ts_ms; ReplacingMergeTree dedupe key',
    _deleted UInt8 DEFAULT 0 COMMENT '1 when the source row was deleted'
) ENGINE = ReplacingMergeTree(_version)
ORDER BY id
COMMENT 'CDC-projected orders table. Owner: data-platform. Source: postgres.public.orders.'
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
