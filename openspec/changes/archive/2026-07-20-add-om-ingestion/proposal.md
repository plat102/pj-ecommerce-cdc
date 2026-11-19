## Why

`make up-governance` brings the OpenMetadata stack (MySQL + Elasticsearch + OM server) online, but the catalog you land on at http://localhost:8585 is empty — no database services, no messaging services, no tables, no topics. Three ingestion YAMLs already exist at `data-platform/governance/openmetadata/ingestion/{postgres,kafka,clickhouse}.yaml`, but running them requires `pip install "openmetadata-ingestion[postgres]==1.5.9"` on the host and remembering to invoke `metadata ingest -c <file>` manually. Result: OM is dressed but bare — operators open it, see nothing, and lose confidence that governance is wired in at all.

## What Changes

- Add a `docker run --rm openmetadata/ingestion:1.5.9` wrapper for each ingestion YAML — no host `pip install`, no long-running scheduler container.
- New Makefile targets: `ingest-pg`, `ingest-kafka`, `ingest-clickhouse`, `ingest-all` (runs the three sequentially with fail-fast semantics), `ingest-status` (curls `http://localhost:8585/api/v1/services/databaseServices` and friends, prints service counts).
- `.env.example` bump: `OPENMETADATA_JWT_TOKEN` placeholder with a one-line note pointing at the default admin path. The ingestion CLI needs a JWT; OM 1.5 ships a well-known admin token but this hook lets operators rotate.
- Docs: create `docs/governance.md` (does not exist today) with a "Populate the catalog" section — `make up-governance && make ingest-all`, expected wall-clock (~90s for three services on a warm image), how to interpret `ingest-status` output, and links to the OM UI (Explore → Databases / Messaging Services).
- Ingestion is idempotent by design: re-running a target updates existing entries rather than creating duplicates. Documented as a scenario in the spec deltas.

## Capabilities

### New Capabilities
_(none — this change extends existing capabilities rather than introducing a new one.)_

### Modified Capabilities
- `data-governance`: adds three requirements — `om-ingestion-postgres`, `om-ingestion-kafka`, `om-ingestion-clickhouse` — each specifying the service name, source hostnames, table/topic filter, and the "re-run is idempotent" scenario. Also adds one requirement `om-ingest-status-target` so `make ingest-status` becomes part of the operator's toolbox for verifying catalog population.
- `infrastructure`: extends `per-service-targets` for the four new `ingest-*` Makefile targets and clarifies that ingestion is on-demand (never in `make up`).

## Impact

**New files:**
- `docs/governance.md` (new)

**Modified files:**
- `Makefile` — five new targets, `.PHONY` update
- `.env.example` — `OPENMETADATA_JWT_TOKEN` placeholder

**Unchanged (deliberately):**
- `docker-compose.governance.yml` — no new long-running service; ephemeral `docker run` keeps `make up-governance` RAM footprint identical.
- The three ingestion YAMLs — already in the right shape.

**Runtime behavior:**
- Default: nothing changes. Operators who don't invoke `ingest-*` see the current empty OM.
- Opt-in: `make ingest-all` produces `ecommerce-postgres` / `ecommerce-kafka` / `ecommerce-clickhouse` service entries in OM with their tables/topics; re-running updates rather than duplicates.

**No breaking changes.** No existing target's behavior changes; no compose file is restructured.

**Deferred / non-goals:**
- Spark OpenLineage integration (separate change `add-spark-openlineage`, depends on this one for target service entries).
- Airflow-based ingestion scheduling — the container image supports it but we're keeping ingestion on-demand.
- OM authentication beyond the default admin (a separate hardening change if needed).
- Custom OM classification tags / glossary bootstrap — hand-authored via UI for now.
