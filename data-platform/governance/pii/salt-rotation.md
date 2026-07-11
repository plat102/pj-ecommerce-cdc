# PII_SALT Rotation Runbook

`PII_SALT` (defined in `infrastructure/docker/.env`) is the salt fed into
`hash_pii_udf` and `tokenize_name_udf` in
`data-platform/streaming/spark/src/utils/udfs.py`. The hashing is
deterministic, so the same email + salt always produces the same digest —
which is what makes analyst joins across systems work. Rotating the salt
invalidates every historical hashed value in ClickHouse.

Treat salt rotation as a backfill event, not a config tweak.

## When to rotate

- The salt has leaked (e.g. it appears in a leaked `.env`, a shared
  screenshot, a chat log).
- The salt hasn't been rotated in ≥12 months and rotation is part of the
  team's routine credential hygiene.
- A dependency change (e.g. moving away from SHA-256) requires re-hashing.

Do **not** rotate the salt for scheduled convenience windows — the cost is
proportional to how much history lives in ClickHouse, not to how often the
key changes.

## Procedure

1. **Coordinate.** Announce the rotation window. During the window,
   historical joins by hashed email between ClickHouse and other systems
   will be inconsistent (some rows hashed with old salt, some with new).

2. **Choose a new salt.** Use a random 32+ byte value:

   ```bash
   openssl rand -hex 32
   ```

3. **Stop CDC jobs.** `make cdc-stop` — a running job with the old salt in
   memory would keep writing old-salt hashes while ClickHouse is being
   backfilled with new-salt hashes.

4. **Update the salt.** Edit `infrastructure/docker/.env`:

   ```
   PII_SALT=<new value>
   ```

   Never check the real salt into git — `.env` is gitignored;
   `.env.example` carries the placeholder only.

5. **Re-hash ClickHouse from Postgres.** Postgres holds the plaintext
   source of truth. Truncate `ecommerce_analytics.customers_cdc`, delete
   the customers checkpoint (`make cdc-rotate-checkpoint TABLE=customers`
   is the safe way), then let the CDC job replay from Debezium — the
   Debezium `snapshot.mode=initial` behavior in `register-pg.json` will
   re-emit every row, which Spark will hash with the new salt.

6. **Restart CDC jobs.** `make cdc-run-all-prod`.

7. **Validate.** After the customers job catches up, spot-check:

   ```sql
   SELECT count() FROM ecommerce_analytics.customers_cdc FINAL
   WHERE _deleted = 0;
   ```

   Row count should match `SELECT count(*) FROM public.customers` in
   Postgres. Any pre-rotation Grafana panels that joined on the hashed
   email will need a full page refresh to invalidate cached results.

## What can't be recovered

- **External systems that stored old-salt hashes.** If a downstream
  consumer (a BI tool, a marketing pipeline) persisted hashed emails, its
  copies are now stale until re-hashed. Coordinate the rotation with
  those consumers.
- **`governance.access_log` history.** The access log doesn't carry PII
  and is unaffected.
