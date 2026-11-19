## 0. Design (this turn)

- [x] 0.1 Write proposal.md
- [x] 0.2 Write design.md — 6 decisions covering endpoint verification, .env-driven flag, pipeline service registration, batch-lineage smoke, best-effort transport, docs colocation
- [x] 0.3 Write tasks.md (this file)
- [x] 0.4 Write specs deltas: MODIFIED `data-governance/openlineage-spark-emission` (env-driven + best-effort), NEW `data-governance/openlineage-spark-service-registration`, NEW `data-governance/openlineage-spark-lineage-edges`, MODIFIED `infrastructure/per-service-targets` for `om-register-spark`
- [ ] 0.5 Depends on `add-om-ingestion` having been implemented and archived (blocks Phase 1)
- [ ] 0.6 User approves design direction before implementation begins

## 1. Phase 1 — Endpoint + registration verification

- [ ] 1.1 With `add-om-ingestion` already applied, hand-craft a minimal OpenLineage JSON event and POST it to both `http://localhost:8585/api/v1/openlineage` and `http://localhost:8585/api/v1/openlineage/v1/lineage`. Determine which returns 2xx. Update `submit_job.sh`'s hard-coded `OPENLINEAGE_URL` default if the current path is wrong.
- [ ] 1.2 Verify OM 1.5.9's `POST /api/v1/services/pipelineServices` accepts a minimal `{"name": "ecommerce-cdc-spark", "serviceType": "Spark"}` body without additional required fields. If it demands more, adjust the registration script accordingly.

## 2. Phase 2 — Compose + env

- [ ] 2.1 Update `infrastructure/docker/docker-compose.spark.yml` — add `ENABLE_OPENLINEAGE: ${ENABLE_OPENLINEAGE:-}` to the `environment:` block (alongside the existing `ENABLE_GX_*` entries).
- [ ] 2.2 Update `.env.example` — add commented `ENABLE_OPENLINEAGE=1` placeholder with a one-line note referencing `docs/governance.md`.
- [ ] 2.3 Verify `docker-compose up -d --force-recreate ed-pyspark-jupyter` propagates the flag: `docker exec ed-pyspark-jupyter env | grep ENABLE_OPENLINEAGE`.

## 3. Phase 3 — Registration script + Makefile target

- [ ] 3.1 Write `scripts/om_register_spark_service.sh` — thin bash wrapper: `curl -sf -X PUT` (idempotent upsert) to `http://localhost:8585/api/v1/services/pipelineServices` with the JSON body from task 1.2. Include `Authorization: Bearer $OPENMETADATA_JWT_TOKEN`. Exit 0 on 200/201; exit 1 on 4xx/5xx with a message.
- [ ] 3.2 Add Makefile target `om-register-spark` → `./scripts/om_register_spark_service.sh`. Update `.PHONY`.

## 4. Phase 4 — Live smoke

- [ ] 4.1 `make om-register-spark` — verify exit 0. Curl `http://localhost:8585/api/v1/services/pipelineServices/name/ecommerce-cdc-spark` returns 200 with `serviceType: Spark`.
- [ ] 4.2 Re-run `make om-register-spark` — verify still 0, no duplicate entities.
- [ ] 4.3 Set `ENABLE_OPENLINEAGE=1` in `infrastructure/docker/.env`, `docker-compose up -d --force-recreate ed-pyspark-jupyter`, wait for container.
- [ ] 4.4 Start `make cdc-run-products-prod`, wait for `Streaming job started` (~30s from a warm ivy cache).
- [ ] 4.5 Insert a Postgres products row. Wait for `MicroBatchExecution: Streaming query made progress` line, then ~15s more for the OM event to be POSTed.
- [ ] 4.6 Verify OpenMetadata received the event: `curl -sG http://localhost:8585/api/v1/lineage/pipelineService/name/ecommerce-cdc-spark` (or the version-appropriate lineage endpoint) returns a non-empty edges array.
- [ ] 4.7 Verify UI: open http://localhost:8585, navigate to Explore → Pipeline Services → `ecommerce-cdc-spark` → Lineage tab. Confirm an inbound edge from `ecommerce-kafka.pg.public.products` and outbound to `ecommerce-clickhouse.ecommerce_analytics.products_cdc`.
- [ ] 4.8 Negative smoke — best-effort: `docker stop openmetadata-server`, insert a Postgres row, verify the Spark job continues processing without error (log level WARN, no exception), then `docker start openmetadata-server` and confirm subsequent batches resume publishing.
- [ ] 4.9 Opt-out: unset `ENABLE_OPENLINEAGE` in `.env`, `docker-compose up -d --force-recreate ed-pyspark-jupyter`, restart CDC job, insert a row, verify no OpenLineage POSTs (grep container network egress or verify OM lineage endpoint receives nothing new).

## 5. Phase 5 — Docs

- [ ] 5.1 Extend `docs/governance.md` (created by `add-om-ingestion`) with a "Spark lineage" section — how to enable (`ENABLE_OPENLINEAGE=1` in `.env` + `make om-register-spark` + restart Spark), what to see in the UI, common failure modes (endpoint mismatch, missing target service, Kafka topic naming mismatch), how to disable.

## 6. Archive

- [ ] 6.1 Run `openspec validate --changes --specs` — all pass.
- [ ] 6.2 `openspec archive add-spark-openlineage --yes`.
- [ ] 6.3 Verify main specs post-archive: `data-governance` capability has `openlineage-spark-emission` updated + `openlineage-spark-service-registration` + `openlineage-spark-lineage-edges` added; `infrastructure/per-service-targets` mentions `om-register-spark`.
- [ ] 6.4 Tick post-archive tasks in the archived file.
