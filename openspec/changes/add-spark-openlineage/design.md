## Context

`data-platform/streaming/spark/scripts/submit_job.sh` already contains this block (lines ~17-28):

```bash
if [[ "${ENABLE_OPENLINEAGE:-0}" == "1" ]]; then
    OPENLINEAGE_URL="${OPENLINEAGE_URL:-http://openmetadata-server:8585/api/v1/openlineage}"
    OPENLINEAGE_NAMESPACE="${OPENLINEAGE_NAMESPACE:-ecommerce-cdc-spark}"
    OPENLINEAGE_CONFS=(
        --conf spark.extraListeners=io.openlineage.spark.agent.OpenLineageSparkListener
        --conf spark.openlineage.transport.type=http
        --conf spark.openlineage.transport.url=$OPENLINEAGE_URL
        --conf spark.openlineage.namespace=$OPENLINEAGE_NAMESPACE
    )
fi
```

And `submit_job.sh`'s packages list already includes `io.openlineage:openlineage-spark_2.12:1.24.2`. All the wiring is there; nothing has ever been enabled or verified. `ENABLE_OPENLINEAGE` isn't in `.env.example`, `docker-compose.spark.yml` doesn't pass it through, and — critically — the OM endpoint `/api/v1/openlineage` needs a Spark service entry to bind lineage to. That entry doesn't exist until `add-om-ingestion` runs and creates the database + messaging service entries that lineage edges will point *into*, plus a separate call to register the Spark side as a "pipeline service."

The OpenLineage 1.24.2 listener publishes JSON events (schema version 1) on every Spark job lifecycle transition. OM 1.5's `/api/v1/openlineage` accepts POST bodies conforming to that schema and derives lineage nodes/edges from `inputs[]` and `outputs[]` in the event. For a Spark Structured Streaming query reading from Kafka and writing to ClickHouse JDBC, the listener emits:
- `inputs`: the Kafka topic (`pg.public.products`) with fully-qualified dataset name.
- `outputs`: the ClickHouse JDBC target (`ecommerce_analytics.products_cdc`).

For OM to render the edge, both datasets must resolve to existing OM entries. That's the load-bearing dependency on `add-om-ingestion`.

## Goals / Non-Goals

**Goals:**
- Turning on `ENABLE_OPENLINEAGE=1` produces visible edges in OM's Lineage tab within ~30s of the first micro-batch.
- The wiring is `.env`-driven, mirroring the `ENABLE_GX_DATA_DOCS` pattern from `add-gx-data-docs` — no runtime code path change, no compose recreate needed per session.
- The Spark side is registered as an OM pipeline service via a small bootstrap target (`make om-register-spark`), idempotent, so operators don't manually clickthrough the OM UI.
- Documented in `docs/governance.md` (extending the "Populate the catalog" section from `add-om-ingestion` with a "Spark lineage" section) — what to enable, what to expect, what to check when it doesn't appear.

**Non-Goals:**
- Column-level lineage. OpenLineage 1.24 supports it via `spark.openlineage.columnLineage.enabled=true`, but the Kafka read side often produces null column facets for CDC payloads (Debezium envelope, not tabular). Follow-up change.
- Historical backfill. Lineage begins from the moment the flag flips on. No back-population from Debezium history.
- Custom parent-job grouping via `spark.openlineage.parentJobName`. Accept per-batch job names.
- OpenLineage transport modes beyond `http` (Kafka transport, file transport). HTTP straight to OM is sufficient.
- Lineage for the Streamlit UI's direct Postgres writes. UI is out-of-band relative to the CDC pipeline.

## Decisions

### D1. Verify the OM endpoint path during implementation, don't assume

The wiring in `submit_job.sh` targets `http://openmetadata-server:8585/api/v1/openlineage`. Community evidence for OM 1.5 shows the actual path is `/api/v1/openlineage/v1/lineage` (the OpenLineage spec's canonical `/v1/lineage` under OM's `/api/v1/openlineage` prefix). Task 1.1 in `tasks.md` will POST a hand-crafted OpenLineage event to both candidate paths and use whichever returns 200/202. If neither works, the task fails loudly and the design gets revised before more work happens.

Alternative rejected: guess and ship. If we guess wrong, the Spark listener 404s silently and nothing appears in OM — same failure mode as if OpenLineage was never enabled. Waste of Phase 4 smoke time.

### D2. `ENABLE_OPENLINEAGE` is `.env`-driven, wired through compose

Match the `add-gx-data-docs` pattern:

```yaml
# docker-compose.spark.yml
environment:
  ENABLE_OPENLINEAGE: ${ENABLE_OPENLINEAGE:-}
```

Rationale:
- Operator sets it once in `.env`, restart Spark container, done.
- `submit_job.sh` already reads it; no code change to the launcher.
- Consistent with the existing GX toggles — same mental model for opt-in features.

Alternative rejected: `docker exec -e` per invocation. Fragile (must be repeated every launch), doesn't survive container recreate.

### D3. Spark registered as an OM "Pipeline Service" with type `Spark`

OM's data model has separate service types for databases, messaging, and pipelines. Spark falls under Pipeline. The registration:

```bash
curl -sf -X POST \
    -H "Authorization: Bearer $OPENMETADATA_JWT_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
      "name": "ecommerce-cdc-spark",
      "serviceType": "Spark",
      "connection": { "config": { "type": "Spark" } }
    }' \
    http://localhost:8585/api/v1/services/pipelineServices
```

Wrapped as `scripts/om_register_spark_service.sh` — idempotent via a `PUT` on the same endpoint (OM upserts), so re-running `make om-register-spark` is safe.

Alternative rejected: register the service inside `submit_job.sh` at Spark start. Would coupling launch to OM availability; if OM is down, Spark shouldn't fail. Bootstrap script is a separate operator concern.

### D4. Verify lineage during Phase 4 by producing a real batch

The smoke test is: `ENABLE_OPENLINEAGE=1 make cdc-run-products-prod`, insert a Postgres row, wait ~15s, then open OM Explore → `ecommerce-cdc-spark` → Lineage tab. Expected: node for the Spark job with an inbound edge from `ecommerce-kafka.pg.public.products` (the input topic — because Spark reads Kafka, not Postgres directly; the Postgres→Kafka edge is Debezium's territory and OM won't derive it from Spark's events) and an outbound edge to `ecommerce-clickhouse.ecommerce_analytics.products_cdc`.

**Important expectation adjustment:** The proposal mentioned "Postgres → Spark → ClickHouse" but OpenLineage from Spark can only see what Spark reads/writes directly. So the actual expected edge is **Kafka → Spark → ClickHouse**. The Postgres side of the graph exists in OM (from `add-om-ingestion`) and is connected via Debezium's schema, but OpenLineage from Spark alone won't draw the Postgres→Kafka edge. Noted here so Phase 4 verification doesn't chase a phantom.

### D5. Best-effort: OM downtime does not fail the Spark job

The OpenLineage HTTP transport's default is fail-open — if the endpoint 5xx's or times out, the event is dropped and Spark keeps processing. That's what we want for a demo stack. Confirmed by inspecting the `openlineage-spark_2.12:1.24.2` source; if a future upgrade changes this default, add `spark.openlineage.transport.timeoutInMillis=5000` and `spark.openlineage.transport.raiseOnFailure=false` explicitly.

### D6. Docs section colocated with `add-om-ingestion`'s output

`docs/governance.md` (created by change #1) gains a new section "Spark lineage" appended after "Populate the catalog." Rationale: operators reading about OM ingestion should discover lineage in the same flow, not have to hunt in a separate doc.

## Risks / Trade-offs

- **[Risk] OM 1.5 endpoint path is different from what `submit_job.sh` assumes** → Mitigation: D1 verification test before any smoke. If different, fix `submit_job.sh` before Phase 4.
- **[Risk] OpenLineage listener silently swallows events when the service isn't registered** → Mitigation: `make om-register-spark` is a mandatory prerequisite documented and tested. Phase 4 smoke also checks OM `POST /api/v1/openlineage` returns non-4xx for a hand-crafted event before enabling the listener in Spark.
- **[Risk] Kafka source dataset naming may not match the ingested Kafka topic name in OM** → Mitigation: verify during smoke that OpenLineage's `kafka://kafka1:9092/pg.public.products` dataset URN matches OM's Kafka topic entry. If it doesn't (topic prefix mismatch, cluster URL mismatch), configure `spark.openlineage.dataset.namespaceResolver.kafka` or a facet override. Documented as a known-hiccup in `docs/governance.md`.
- **[Risk] Every Structured Streaming micro-batch fires a full START/COMPLETE, flooding OM with events** → Mitigation: verify during smoke. If event rate is a problem, configure `spark.openlineage.job.owners.name=ecommerce-cdc` + `spark.openlineage.appName=ecommerce-cdc-spark` to deduplicate. Defer until we see the actual rate.
- **[Trade-off] No column-level lineage in v1** → Accepted. Batch-level edges are the demo-relevant story.
- **[Trade-off] Lineage only forward from opt-in** → Accepted. Backfill is a separate operator concern.

## Migration Plan

Depends on `add-om-ingestion` being deployed first. Order:
1. Land + verify `add-om-ingestion` (produces `ecommerce-postgres`, `ecommerce-kafka`, `ecommerce-clickhouse` service entries).
2. Land this change (adds the Spark pipeline service + turns on the listener).
3. Enable `ENABLE_OPENLINEAGE=1` in `.env`.
4. Restart the Spark container.

Rollback: `git revert` + `ENABLE_OPENLINEAGE=` (empty) in `.env` + Spark container restart. OM keeps the historical events; the Lineage tab just stops updating.

## Open Questions

- **Exact OM 1.5.9 OpenLineage endpoint path** (D1) — verify with a `curl` before implementation. Two candidates: `/api/v1/openlineage` and `/api/v1/openlineage/v1/lineage`.
- **Does OM 1.5.9's Spark pipeline service type accept the minimal `{"type": "Spark"}` connection config**, or does it require additional fields (host, port)? Check with the OM REST doc at http://localhost:8585/docs during Phase 1.
- **Kafka topic naming convention alignment**: does `add-om-ingestion`'s Kafka ingestion produce topic entries with names like `pg.public.products` or with a cluster prefix like `ecommerce-kafka.pg.public.products`? Whichever OM uses drives the OpenLineage dataset URN configuration in Spark.
