-- Postgres archival policy: move orders older than 1 year into orders_archive.
--
-- Debezium's `table.include.list` in data-platform/cdc/connectors/register-pg.json
-- is explicit and does NOT include public.orders_archive, so archived rows are
-- excluded from the CDC stream by construction.
--
-- Intended to be executed on a monthly schedule (documented in design.md, Pillar 4).
-- This script is idempotent: re-running only moves rows that meet the age cutoff.

CREATE TABLE IF NOT EXISTS orders_archive (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER,
    product_id INTEGER,
    quantity INTEGER NOT NULL,
    order_time TIMESTAMP NOT NULL,
    archived_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- REPLICA IDENTITY FULL would let Debezium capture the archive table if it were
-- ever added to table.include.list; leaving it at the default (DEFAULT/nothing)
-- means an accidental include still produces minimal noise.

BEGIN;

WITH cutoff AS (
    SELECT (CURRENT_TIMESTAMP - INTERVAL '1 year')::timestamp AS ts
),
moved AS (
    DELETE FROM orders o
    USING cutoff
    WHERE o.order_time < cutoff.ts
    RETURNING o.id, o.customer_id, o.product_id, o.quantity, o.order_time
)
INSERT INTO orders_archive (id, customer_id, product_id, quantity, order_time)
SELECT id, customer_id, product_id, quantity, order_time FROM moved
ON CONFLICT (id) DO NOTHING;

COMMIT;
