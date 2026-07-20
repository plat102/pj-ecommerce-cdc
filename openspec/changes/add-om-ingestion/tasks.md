## 0. Design (this turn)

- [x] 0.1 Write proposal.md
- [x] 0.2 Write design.md — 6 decisions covering ephemeral runner, version pinning, JWT auth, ingest-status target, docs entry point, fail-fast composite
- [x] 0.3 Write tasks.md (this file)
- [x] 0.4 Write specs deltas: MODIFIED `data-governance/openmetadata-ingestion` with 6 new scenarios (per-source + idempotency + fail-fast + status); MODIFIED `infrastructure/per-service-targets` for the five new Makefile targets
- [x] 0.5 User approves design direction before implementation begins

## 1. Phase 1 — Verification prerequisites

- [x] 1.1 Verified `openmetadata/ingestion:1.5.9` — network reachable, `metadata` CLI available at `/home/airflow/.local/bin/metadata`. Discovery: the image's default entrypoint is `airflow`, not `metadata`, so the Makefile targets pass `--entrypoint metadata` (see Makefile `INGESTION_DOCKER_RUN`).
- [x] 1.2 Verified the three YAMLs. All use `${OM_INGESTION_JWT}` for JWT expansion (env var name chosen over the tasks.md-proposed `OPENMETADATA_JWT_TOKEN` — kept the existing shorter name in the YAMLs to avoid churn). Fixed `clickhouse.yaml` during Phase 4: OM 1.5.9's ClickHouse connector rejects the `authType: password:` shape and expects `password:` at the top level of `serviceConnection.config`.
- [x] 1.3 OM 1.5.9 uses per-install RSA keys (from `/opt/openmetadata/conf/openmetadata.yaml`: `rsapublicKeyFilePath`, `rsaprivateKeyFilePath`) — the JWT is NOT a well-known constant. Docs now instruct operators to grab the long-lived `ingestion-bot` JWT via OM Settings → Bots (UI path) or via the two-step admin login + user-fetch API (CLI path). Both are documented in `docs/governance.md#obtain-the-ingestion-jwt`.

## 2. Phase 2 — Makefile targets

- [x] 2.1 Added `INGESTION_IMAGE` variable (and `INGESTION_YAML_DIR`, `INGESTION_DOCKER_RUN` helpers) in the Governance Catalog section of the Makefile (after `status-governance`).
- [x] 2.2 Added `ingest-pg`, `ingest-kafka`, `ingest-clickhouse`. Each guards on `OM_INGESTION_JWT` being non-empty and runs `metadata ingest -c /ingestion/<source>.yaml` via the ephemeral `docker run --rm` invocation. Env expansion of `${OM_INGESTION_JWT}` and `${CLICKHOUSE_PASSWORD}` inside the YAMLs is handled by passing both vars through `-e` to the container.
- [x] 2.3 Added `ingest-all` — sequential `$(MAKE) ingest-pg`, `$(MAKE) ingest-kafka`, `$(MAKE) ingest-clickhouse` (fail-fast confirmed in task 4.7).
- [x] 2.4 Added `ingest-status` — loops over the three service kinds with `Authorization: Bearer $(OM_INGESTION_JWT)` (OM 1.5.9 endpoints require auth); prints "AUTH FAILED" on unauthorized response, "OM unreachable" on empty body. Non-zero exit if OM unreachable or the JWT is unset.
- [x] 2.5 `.PHONY` updated with all five targets.

## 3. Phase 3 — Env + docs

- [x] 3.1 Added commented `OM_INGESTION_JWT` placeholder to `.env.example` with a note explaining the per-install nature and pointing at `docs/governance.md`.
- [x] 3.2 `docs/governance.md` already existed from prior changes. Extended its "Catalog & lineage" section with three new subsections: "Populate the catalog" (workflow + idempotency + filters), "Obtain the ingestion JWT" (both UI and CLI paths), and "After ingestion" (what the operator should see in OM Explore).

## 4. Phase 4 — Live smoke

- [x] 4.1 `make up-governance` was already running when I started; OM at http://localhost:8585 healthy.
- [x] 4.2 `make ingest-pg` — 6 records, 0 errors, "Success %: 100.0". `curl … /services/databaseServices/name/ecommerce-postgres` returns 200 with `serviceType: Postgres`.
- [x] 4.3 `make ingest-kafka` — 18 records, 0 errors. `curl … /services/messagingServices/name/ecommerce-kafka` returns 200; `GET /topics?service=ecommerce-kafka` returns 17 topics including CDC (`customers_cdc`, `pg.public.*`) and DLQ (`*_dlq`, `*_sink_dlq`) topics. Note: 16 warnings on Debezium's `io.debezium.connector.postgresql.Source` nested Avro type — expected interop gotcha, doesn't block ingestion.
- [x] 4.4 `make ingest-clickhouse` — after fixing `authType` shape (see task 1.2), 6 records, 0 errors. `GET /tables?service=ecommerce-clickhouse` returns 6 tables (`customers`, `customers_cdc`, `orders`, `orders_cdc`, `products`, `products_cdc`).
- [x] 4.5 `make ingest-status` — databaseServices: 2, messagingServices: 1, pipelineServices: 0 (matches spec expectation; pipelineServices stays 0 until `add-spark-openlineage` lands).
- [x] 4.6 Idempotency: re-ran `make ingest-all` — all three workflows returned Success 100%, counts remain 2 / 1 / 0.
- [x] 4.7 Fail-fast: temporarily changed `hostPort: postgres:5432` → `postgres-nope:5432` in `postgres.yaml`. `make ingest-all` failed on Postgres step, did not proceed to Kafka or ClickHouse. Restored the YAML.

## 5. Archive

- [ ] 5.1 Run `openspec validate --changes --specs` — all pass.
- [ ] 5.2 `openspec archive add-om-ingestion --yes`.
- [ ] 5.3 Verify main specs post-archive: `data-governance/openmetadata-ingestion` gained the new scenarios; `infrastructure/per-service-targets` mentions `ingest-*`.
- [ ] 5.4 Tick post-archive tasks in the archived file.
