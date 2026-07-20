## Context

The OpenMetadata stack (MySQL + Elasticsearch + OM server) came online in an earlier change (`add-data-governance` Phase 4 / recent OM bootstrap repair). Ingestion YAMLs — the actual metadata-scraping recipes — exist at `data-platform/governance/openmetadata/ingestion/{postgres,kafka,clickhouse}.yaml` and are correctly configured for in-network hostnames (`postgres:5432`, `kafka1:9092`, `clickhouse:8123`). What's missing is a *way to run them* without operators having to `pip install openmetadata-ingestion` on the host.

The OpenMetadata org publishes an official `docker.getcollate.io/openmetadata/ingestion:1.5.9` image that bundles the CLI, all connector extras (Postgres, Kafka, ClickHouse, and dozens more), and Airflow. We want the CLI parts, not Airflow — the OM stack is on-demand in this repo (per the header comment in `docker-compose.governance.yml`), and running a scheduler container 24/7 for what an operator invokes maybe monthly is wasteful.

The three YAML files use hostnames that resolve inside the `ecommerce-network` Docker network (`postgres:5432`, `kafka1:9092`, `clickhouse:8123`, `openmetadata-server:8585`). The ingestion CLI must run on the same network for those hostnames to resolve. That constrains us to `docker run --network ecommerce-network` — running the CLI on the host would need the YAMLs rewritten to `localhost:*` published ports, which we're not doing.

## Goals / Non-Goals

**Goals:**
- One-command ingestion: `make ingest-pg`, `ingest-kafka`, `ingest-clickhouse`, plus `ingest-all`.
- No new long-running container in `make up-governance` — ephemeral `docker run --rm` per invocation.
- Idempotent: re-running any target updates existing OM entries rather than creating duplicates (this is the CLI's default behavior; the design just formalizes the guarantee in a spec scenario).
- `ingest-status` sanity target: curl the OM REST API, print counts of database / messaging services, so operators can verify without opening the UI.
- Docs surface: `docs/governance.md` becomes the first stop for anyone thinking "how do I make OM show something?"

**Non-Goals:**
- Airflow-based scheduling. Follow-up change if needed.
- OM authentication beyond the default admin JWT. `OPENMETADATA_JWT_TOKEN` in `.env.example` is a hook; hardening is separate.
- Spark OpenLineage lineage (change `add-spark-openlineage`, depends on this).
- Custom glossary / classification tag bootstrap.
- ClickHouse `lineage` extraction — OM 1.5's ClickHouse connector supports it, but requires configuring a query-log source we don't run. Metadata-only for now.

## Decisions

### D1. Ephemeral `docker run --rm` per target, not a scheduled service

Each `make ingest-*` target expands to:

```
docker run --rm \
    --network ecommerce-network \
    -v $(PWD)/data-platform/governance/openmetadata/ingestion:/ingestion:ro \
    -e OPENMETADATA_JWT_TOKEN=$(OPENMETADATA_JWT_TOKEN) \
    docker.getcollate.io/openmetadata/ingestion:$(OPENMETADATA_VERSION) \
    metadata ingest -c /ingestion/<source>.yaml
```

Rationale:
- Zero footprint when not running. RAM cost during a run is ~500MB (the CLI + connector JARs); zero afterward. An Airflow scheduler would pin ~500MB permanently for a job that runs on operator whim.
- Same lifecycle as `apply-pg-connector` (the Debezium bootstrap) — one-shot side effect via `docker run` / `curl`, invoked by operators, not part of the always-on stack.
- Reversible: nothing to `down` — the container is gone after ingestion. Only side effect is the OM database.

Alternative rejected: bake ingestion into `docker-compose.governance.yml` as a `restart: no` one-shot service. Would work but couples ingestion cadence to compose lifecycle (`up-governance` triggers a run), which is wrong — operators want to control when.

Alternative rejected: cron on the host. Portable across dev machines is a nightmare; `make ingest-all` in a hook is simpler.

### D2. Pin the ingestion image to OM server version

`OPENMETADATA_VERSION` in `.env` (already defined for the OM server, defaults to `1.5.9`) drives both the server image and the ingestion image. Version skew between the two is a common source of "unexpected schema field" errors.

Alternative rejected: pin ingestion to `latest`. OM's `latest` tag has broken us before during other stacks — matched-version is the safer default.

### D3. JWT via `OPENMETADATA_JWT_TOKEN` env var, default from OM bootstrap

OM 1.5 boots with a well-known admin bot token that the ingestion CLI can pick up if `OPENMETADATA_JWT_TOKEN` is set. Alternative auth (SSO, custom OIDC) is out of scope; the ingestion CLI reads the token from `serverConfig.securityConfig.jwtToken` in each YAML. We want to keep the YAMLs generic (checked in, no secrets) — inject the token via env instead.

Ingestion YAML pattern (already in place):
```yaml
workflowConfig:
  openMetadataServerConfig:
    hostPort: http://openmetadata-server:8585/api
    authProvider: openmetadata
    securityConfig:
      jwtToken: "${OPENMETADATA_JWT_TOKEN}"
```

The CLI does `.expand()` on env references. Confirmed present in the three YAMLs during verification (Impact section covers the check).

### D4. `ingest-status` as the "did it work?" affordance

Rather than open http://localhost:8585 and eyeball, `make ingest-status` calls three OM REST endpoints and prints a compact summary:

```
$ make ingest-status
Database services:  1  (ecommerce-postgres)
Messaging services: 1  (ecommerce-kafka)
Analytics services: 1  (ecommerce-clickhouse)
Total tables:       3  (customers, products, orders)
Total topics:       ~15 (pg.public.*, *_cdc_dlq, ...)
```

Simpler than curl-eyeball and doubles as a smoke check for CI-ish operator workflows. Implementation: `curl -sf http://localhost:8585/api/v1/services/databaseServices?limit=100 | jq '.data | length'` and friends.

### D5. `docs/governance.md` as the entry point

`docs/observability.md` covers the metrics/logging plane. Governance (OM catalog, lineage) deserves its own page — it's a different mental model and different set of URLs. Sections:

1. What OM does in this stack (one paragraph).
2. Populate the catalog (`make up-governance && make ingest-all`).
3. Verify (`make ingest-status`).
4. Where to look in the UI.
5. When to re-ingest (schema change, new tables).
6. Troubleshooting (JWT auth failures, network errors).

Section 7 ("Spark lineage") lands in a follow-up change (`add-spark-openlineage`).

### D6. `ingest-all` fail-fast, not best-effort

`ingest-all` is a `$(MAKE) ingest-pg && $(MAKE) ingest-kafka && $(MAKE) ingest-clickhouse`. If Postgres ingestion fails (e.g., Postgres container down), Kafka doesn't run. Rationale: an operator who runs `ingest-all` on a partially-up stack should see the first failure loudly, not scroll past it to find that Kafka also failed for the same reason. Cheaper to fix once and re-run than to debug three cascading errors.

## Risks / Trade-offs

- **[Risk] Ingestion image is amd64-only on some connector variants** → Mitigation: `openmetadata/ingestion:1.5.9` is `linux/amd64` + `linux/arm64` multi-arch. If a specific connector isn't arm64-clean, add `--platform linux/amd64` to the specific target and note it in `docs/governance.md`. Verify during implementation.
- **[Risk] JWT token in `.env` leaks if operators commit `.env`** → Mitigation: `.env` is git-ignored; `.env.example` carries only a comment pointing at the default admin token path (`/opt/openmetadata/conf/openmetadata.yaml` inside `openmetadata-server`), not the token itself.
- **[Risk] Ingestion YAML hostname assumption (`postgres:5432`) breaks when operators pause postgres between `up-governance` and `ingest-pg`** → Mitigation: `ingest-status` is the canary. If Postgres is down, the ingestion CLI raises with a clear "connection refused" error; the operator restarts Postgres and re-runs (idempotent). Documented in Troubleshooting.
- **[Risk] OM 1.5 REST endpoints for status counting change in future OM versions** → Mitigation: `ingest-status` is a Make target, not a spec-level guarantee. If the API changes on a version bump, we adjust the target; the spec-level requirement is "operators can verify catalog population from the CLI," not "specifically these endpoints."
- **[Trade-off] Ephemeral runs mean no ingestion history in Airflow UI** → Accepted. `make` invocation history in shell history is the audit trail for on-demand runs. A future change can add Airflow if scheduling becomes a real ask.
- **[Trade-off] `ingest-all` doesn't parallelize** → Accepted. Three sources, ~30s each, ~90s total. Parallel would be ~30s but adds error-handling complexity and image-pull contention.

## Migration Plan

No migration needed — this is additive. Rollback is `git revert`; nothing persists outside OM's database that this change created (and even that is regenerable).

## Open Questions

- **Which admin JWT does OM 1.5.9 ship with by default?** Verify during implementation by shelling into `openmetadata-server` and reading `/opt/openmetadata/conf/openmetadata.yaml`. If the token is a well-known constant, hardcode as the `OPENMETADATA_JWT_TOKEN` default in `.env.example`. If it's per-install generated, the docs need a "grab the token from …" step.
- **Does the ClickHouse ingestion YAML need `queryLogTable` set for lineage?** Not for this change (metadata-only), but note the answer for `add-spark-openlineage`.
- **Should `ingest-all` be added to `make up-governance` as an optional post-hook?** Currently no — up-governance is stack lifecycle, ingest-* is data lifecycle. Revisit if operators consistently forget to ingest.
