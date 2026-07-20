## 0. Design (this turn)

- [x] 0.1 Write proposal.md
- [x] 0.2 Write design.md — 6 decisions covering ephemeral runner, version pinning, JWT auth, ingest-status target, docs entry point, fail-fast composite
- [x] 0.3 Write tasks.md (this file)
- [x] 0.4 Write specs deltas: MODIFIED `data-governance/openmetadata-ingestion` with 6 new scenarios (per-source + idempotency + fail-fast + status); MODIFIED `infrastructure/per-service-targets` for the five new Makefile targets
- [ ] 0.5 User approves design direction before implementation begins

## 1. Phase 1 — Verification prerequisites

- [ ] 1.1 Verify `openmetadata/ingestion:1.5.9` runs `metadata ingest --help` without error via a one-shot `docker run --rm --network ecommerce-network` — confirms network reachability and that no additional connector extras are needed for our three sources.
- [ ] 1.2 Verify each of the three ingestion YAMLs (`postgres.yaml`, `kafka.yaml`, `clickhouse.yaml`) contains a `workflowConfig.openMetadataServerConfig.securityConfig.jwtToken` field capable of receiving env expansion. If not, add it (uniform pattern). Commit any YAML edits as a single "prep" chunk.
- [ ] 1.3 Determine OM 1.5.9 default admin JWT: shell into `openmetadata-server`, cat `/opt/openmetadata/conf/openmetadata.yaml`, extract the `jwtTokenConfiguration` block. Record whether the admin token is a well-known constant (hardcode as default in `.env.example`) or per-install generated (docs need "grab from …" step).

## 2. Phase 2 — Makefile targets

- [ ] 2.1 Add `INGESTION_IMAGE := docker.getcollate.io/openmetadata/ingestion:$(or $(OPENMETADATA_VERSION),1.5.9)` variable near the top of the Makefile (after existing `COMPOSE_*` block).
- [ ] 2.2 Add `ingest-pg`, `ingest-kafka`, `ingest-clickhouse` targets. Each SHALL: `docker run --rm --network ecommerce-network -v $(PWD)/data-platform/governance/openmetadata/ingestion:/ingestion:ro -e OPENMETADATA_JWT_TOKEN=$(OPENMETADATA_JWT_TOKEN) $(INGESTION_IMAGE) metadata ingest -c /ingestion/<source>.yaml`. Include a `## help` comment string.
- [ ] 2.3 Add `ingest-all` target: `$(MAKE) ingest-pg && $(MAKE) ingest-kafka && $(MAKE) ingest-clickhouse` (fail-fast on first error).
- [ ] 2.4 Add `ingest-status` target: three `curl -sf http://localhost:8585/api/v1/services/{databaseServices,messagingServices,pipelineServices}?limit=100 | jq '.data | length'` calls with human-readable prefixes; exit non-zero if OM unreachable.
- [ ] 2.5 Update `.PHONY` to include `ingest-pg ingest-kafka ingest-clickhouse ingest-all ingest-status`.

## 3. Phase 3 — Env + docs

- [ ] 3.1 Update `.env.example` — add commented `OPENMETADATA_JWT_TOKEN` placeholder with a one-line note pointing at the default admin token path (or the OM UI "Bots" page for token retrieval, depending on task 1.3 outcome).
- [ ] 3.2 Create `docs/governance.md` with sections: intro (what OM does here), "Populate the catalog" (`make up-governance && make ingest-all`), "Verify" (`make ingest-status`), "Where to look in the UI" (Explore → Databases → `ecommerce-postgres`, etc.), "When to re-ingest", "Troubleshooting" (JWT auth, connection refused, image pull, arm64/amd64 platform notes).

## 4. Phase 4 — Live smoke

- [ ] 4.1 `make up-governance` from clean, wait for `openmetadata-server` health check to pass (~90s from cold, ~15s if MySQL/ES volumes warm).
- [ ] 4.2 `make ingest-pg` — verify exit 0, then `curl -sf http://localhost:8585/api/v1/services/databaseServices/name/ecommerce-postgres` returns 200 with a body containing the service definition.
- [ ] 4.3 `make ingest-kafka` — verify `curl -sf http://localhost:8585/api/v1/services/messagingServices/name/ecommerce-kafka` returns 200 and includes the three `pg.public.*` topics.
- [ ] 4.4 `make ingest-clickhouse` — verify `curl -sf http://localhost:8585/api/v1/services/databaseServices/name/ecommerce-clickhouse` returns 200 and includes the three `*_cdc` tables.
- [ ] 4.5 `make ingest-status` — verify output shows Database services: 2, Messaging services: 1.
- [ ] 4.6 Idempotency: re-run `make ingest-all` and confirm exit 0 with no duplicate services in the status output.
- [ ] 4.7 Fail-fast: `make stop` postgres only, then `make ingest-all` — verify Postgres step fails, Kafka + ClickHouse steps do NOT run.

## 5. Archive

- [ ] 5.1 Run `openspec validate --changes --specs` — all pass.
- [ ] 5.2 `openspec archive add-om-ingestion --yes`.
- [ ] 5.3 Verify main specs post-archive: `data-governance/openmetadata-ingestion` gained the new scenarios; `infrastructure/per-service-targets` mentions `ingest-*`.
- [ ] 5.4 Tick post-archive tasks in the archived file.
