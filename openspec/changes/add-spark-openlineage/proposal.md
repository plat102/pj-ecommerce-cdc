## Why

`submit_job.sh` already wires an OpenLineage listener behind `ENABLE_OPENLINEAGE=1`: the flag adds `spark.extraListeners=io.openlineage.spark.agent.OpenLineageSparkListener` + an HTTP transport pointing at `http://openmetadata-server:8585/api/v1/openlineage`. But the flag is never set anywhere (not in `.env.example`, not in `docker-compose.spark.yml`), the OM endpoint expects a service entry to bind lineage to (see `add-om-ingestion`), and nobody has verified the lineage edges show up. Result: the wiring is dead code — turn it on and the Spark job either 404s on the OM endpoint or silently drops events. Operators can't answer "when a CDC batch lands in ClickHouse, what upstream Postgres tables did it touch?" from OM, even though every piece needed to answer it is theoretically in place.

## What Changes

- Make `ENABLE_OPENLINEAGE=1` a first-class opt-in via `.env` (like `ENABLE_GX_DATA_DOCS` from `add-gx-data-docs`): compose reads the flag, passes it through to the Spark container, `submit_job.sh` already picks it up.
- Verify + document the OM 1.5 OpenLineage endpoint path (`/api/v1/openlineage/v1/lineage` vs `/api/v1/openlineage`) — the wiring in `submit_job.sh` was authored speculatively and may not match the shipped OM version. Fix as needed.
- Register the Spark job as a "pipeline service" in OM before Spark starts pushing events. Add a bootstrap script `scripts/om_register_spark_service.sh` that POSTs a service entry via OM REST (`type=Spark`, `serviceName=ecommerce-cdc-spark`, matching the namespace in `submit_job.sh`).
- Wire the bootstrap into a new Makefile target `om-register-spark` (idempotent — safe to re-run). `ingest-all` in `add-om-ingestion` gains a follow-up hint pointing at this target.
- Live smoke: with `ENABLE_OPENLINEAGE=1` on a running products CDC job, verify OM Explore → `ecommerce-cdc-spark` shows the START/COMPLETE events and the "Lineage" tab shows an edge from `ecommerce-postgres.public.products` → `ecommerce-clickhouse.ecommerce_analytics.products_cdc`.
- Docs: extend `docs/governance.md` (created by `add-om-ingestion`) with a "Spark lineage" section — how to enable, what edges to expect, common failure modes (endpoint mismatch, missing target service).

## Capabilities

### New Capabilities
_(none — extends existing capabilities.)_

### Modified Capabilities
- `data-governance`: adds three requirements — `spark-openlineage-listener` (formalizes the `ENABLE_OPENLINEAGE=1` opt-in and the `spark.extraListeners` config path), `spark-openlineage-service-registration` (the `om-register-spark` target and its idempotency), and `spark-openlineage-lineage-edges` (the assertion that Postgres → Spark → ClickHouse edges appear in the OM Lineage tab for a CDC job).
- `infrastructure`: extends `per-service-targets` for `om-register-spark`.

## Impact

**Depends on** `add-om-ingestion` (must land first). Spark can only publish lineage to services that already exist in OM's catalog — that's what change #1 creates. Attempting to enable OpenLineage without ingestion first yields 404s from OM and drops the events silently.

**New files:**
- `scripts/om_register_spark_service.sh` (thin `curl` wrapper for OM REST)

**Modified files:**
- `Makefile` — new target `om-register-spark`, `.PHONY` update
- `infrastructure/docker/docker-compose.spark.yml` — pass `ENABLE_OPENLINEAGE` from host env through to the Spark container (mirroring how `ENABLE_GX_GATE` / `ENABLE_GX_DATA_DOCS` are wired)
- `.env.example` — commented `ENABLE_OPENLINEAGE=1` placeholder with one-line note
- `data-platform/streaming/spark/scripts/submit_job.sh` — potentially adjust the endpoint path if OM 1.5 expects `/v1/openlineage/v1/lineage` (verify during implementation)
- `docs/governance.md` — new "Spark lineage" section

**Runtime behavior:**
- Default: `ENABLE_OPENLINEAGE` unset → `submit_job.sh` skips the listener block entirely (already the case today). No overhead.
- Opt-in: `ENABLE_OPENLINEAGE=1 make cdc-run-products-prod` produces START/COMPLETE events on every micro-batch; OM's Lineage tab shows the edge within seconds of the first batch.

**No breaking changes.** The `ENABLE_OPENLINEAGE=1` flag was always opt-in; this change just makes it *actually work* end-to-end.

**Deferred / non-goals:**
- Column-level lineage (OpenLineage supports it via `spark.openlineage.columnLineage.enabled` but requires further verification — a follow-up change).
- Custom facets or `spark.openlineage.parentJobName` overrides for grouping — accept defaults.
- OM's `/api/v1/lineage` graph query wiring into Grafana — a UI concern separate from the ingestion pipeline.
- Historical backfill of lineage — only forward events from the moment the flag is enabled.
