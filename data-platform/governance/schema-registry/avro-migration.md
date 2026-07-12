# Avro migration runbook

Switching the Debezium connector from JSON to Avro changes the wire format
of every `pg.public.*` topic. Existing Spark checkpoints encode the JSON
parser state; restarting Spark jobs against Avro topics without draining
will fail at the schema layer with a corrupt-message loop.

This runbook is the sequence to execute the switchover in Phase 3. It is
**not** a normal deployment step — run it once during the Avro cutover,
then delete this file's execution notes (keep the doc for reference).

## Pre-flight

1. Confirm Schema Registry is reachable: `curl http://localhost:8081/apis/registry/v2/groups/default/artifacts` returns `[]` or existing artifacts. (Apicurio's native API. `/apis/ccompat/v7/subjects` also works if a client expects the Confluent-shaped endpoint.)
2. Confirm every consumer is idle (or acceptable to lose in-flight events):
   - `make cdc-status` shows no active spark-submit processes; if any, `make cdc-stop`.
   - Streamlit Kafka monitor session closed (nothing consuming from `pg.public.*`).
3. Snapshot ClickHouse row counts for the three `*_cdc` tables. Useful for a post-cutover reconciliation sanity check.

## Drain

For each of the three CDC topics, wait until no consumer lag remains:

```bash
docker exec kafka1 kafka-consumer-groups \
  --bootstrap-server kafka1:9092 --list

# For each consumer group tied to pg.public.*:
docker exec kafka1 kafka-consumer-groups \
  --bootstrap-server kafka1:9092 \
  --group <group> --describe
```

Confirm `LAG = 0` (or acceptable) before proceeding.

## Delete old checkpoints

Spark checkpoints under `${CHECKPOINT_LOCATION}` encode the JSON parsing
state and MUST be dropped before switching to Avro. Under the versioned
checkpoint convention (`{table}/v1` — see Phase 1 requirement
`checkpoint-versioned-paths`), Avro cutover moves to `v2`:

```bash
# Phase 3 introduces the schema-version bump. `make cdc-rotate-checkpoint`
# (task 1.4) is the codified path, but for a cutover, delete manually to
# be sure:
docker exec ed-pyspark-jupyter rm -rf /tmp/checkpoints/customers/v1
docker exec ed-pyspark-jupyter rm -rf /tmp/checkpoints/products/v1
docker exec ed-pyspark-jupyter rm -rf /tmp/checkpoints/orders/v1
```

Then update `BaseCDCJob.CHECKPOINT_VERSION = "v2"` (single-line change).

## Switch over

1. `make apply-pg-connector` — the connector JSON now points at Avro + Schema Registry (already committed in this change).
2. Trigger a small write to Postgres to generate a demo event. Verify Apicurio Registry now has artifacts:
   ```bash
   curl http://localhost:8081/apis/registry/v2/groups/default/artifacts
   # → {"count": 6, "artifacts": [{"id": "pg.public.customers-key", ...}, ...]}
   ```
3. `make cdc-run-all-prod` to restart Spark jobs with the new `v2` checkpoint path against Avro topics.
4. Verify no error loop in `make logs-spark` and that row counts in ClickHouse resume growing.

## Rollback

If the switchover breaks, revert the Debezium connector JSON to the JSON
converter (previous commit), restart the connector, keep the `v2`
checkpoints for the eventual retry, and open an incident.

The DLQ topics (`customers_dlq`, `products_dlq`, `orders_dlq`) do not need
to be pre-created — Kafka auto-creates them on first write. If auto-create
is disabled in the environment, create them upfront with the same
retention as `*_dlq` in the Phase 1 retention policy (14 days).
