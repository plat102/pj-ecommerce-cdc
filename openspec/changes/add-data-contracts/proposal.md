## Why

Schema truth in this pipeline is spread across four independent layers — Postgres DDL (`infrastructure/docker/postgres/init.sql`), Spark `StructType` (`data-platform/streaming/spark/src/schemas/cdc_schemas.py`), ClickHouse DDL (`infrastructure/docker/clickhouse/create_tables.sql`), and Debezium's inferred Avro (in Apicurio) — with no automated drift detection. Adding a column in Postgres without a matching update in ClickHouse or the Spark schema causes silent data loss at the sink, and PII/quality metadata is scattered across UDFs, GX suites, and code comments. This change introduces a per-table declarative contract (ODCS v3.1, Linux Foundation Bitol) as a **read-only human+machine-readable source of truth** for each CDC table, plus a CI drift test that fails PRs when any downstream layer diverges from the contract.

## What Changes

- Add `data-platform/governance/contracts/{customers,products,orders}.yaml` following the Open Data Contract Standard v3.1. Each contract declares:
  - Column schema (name, logical type, required flag)
  - PII classification per column (aligning with existing hash/tokenize rules)
  - Servers block naming the postgres source, kafka topic, and clickhouse sink
  - Ownership + basic quality summary (informational; existing GX suites remain the runtime authority)
- Add a Python drift test at `tests/contracts/test_schema_drift.py` that parses each contract and asserts column-name and logical-type parity across:
  - Postgres `init.sql` (source table)
  - Spark `cdc_schemas.py` (Debezium envelope's `after` block)
  - ClickHouse `create_tables.sql` (`*_cdc` sink)
  - GX suite JSON (column coverage of `expect_column_values_to_not_be_null`)
  - OpenMetadata catalog (columns as ingested from Postgres + ClickHouse via `make ingest-all`) — closes the reconciliation gap between the *declared* contract, the *runtime* views (OM + GX), and the DDL sources that DE and DA both consult when re-checking data
- Wire the drift test into `make test` as a hard gate so PRs fail on divergence. The OM layer check SHALL soft-fail (skip with a diagnostic) when OM is unreachable (dev laptops without the governance stack up); the four DDL/GX layers remain hard gates.
- Add a CI hook that runs `make ingest-all` whenever `init.sql` or `create_tables.sql` changes in a PR, so OM's view of the schema is refreshed before the drift test's OM-layer check runs.
- Add `datacontract-cli>=1.0.13` and a lightweight SQL parser (`sqlglot`) to the `dev` dependency group in `pyproject.toml`.
- Document the contract workflow in `docs/governance.md` (link from the existing "Catalog & lineage" section — contracts are the authoritative side of catalog). Include a "three views" section explaining how the contract, OM catalog, and GX suites relate and cross-check.

**Not in scope** (deferred to future changes):
- Code generation FROM contracts (Phase 3). Contracts stay read-only reference for now; the existing schema files remain hand-maintained.
- ClickHouse `Decimal` scale/precision matching beyond logical type (approximation is enough for Phase 1+2).
- Contract versioning / compatibility rules (BACKWARD/FORWARD). Deferred until schema evolution becomes a real event.
- **Contract ↔ GX *semantic* reconciliation** (e.g., "if contract says `pii=hash`, GX must have a `regex_matches` expectation on the hashed shape"). This depends on a project-local PII vocabulary that does not yet exist and only pays off once we have more than the current three tables / two PII columns. Deferred to a follow-up (`add-contract-pii-vocab` or similar) once we have real cases to inform the mapping. For now, the drift test's GX check remains a coverage-only lower bound (see Decision 6).

## Capabilities

### New Capabilities

None. Contract enforcement is a governance concern that sits naturally alongside existing GX suites, PII rules, and RBAC.

### Modified Capabilities

- `data-governance`: Add four new requirements — `data-contract-yaml-per-table` (contract file existence + shape), `contract-schema-drift-test` (drift-detection semantics across the four DDL/GX layers), `contract-om-catalog-reconciliation` (OM as a fifth soft-fail layer + CI ingest-on-schema-change hook), and `contract-drift-ci-gate` (wire into `make test` as blocking gate).

## Impact

**Depends on** `add-om-ingestion` (must land first). The OM-layer reconciliation check calls `GET /api/v1/tables/name/{fqn}` on the OM server and expects the catalog to be populated by `make ingest-all`; without that change the OM layer would always soft-fail and the reconciliation half of the value is lost. Sequencing: `add-om-ingestion` → `add-data-contracts` → `add-spark-openlineage` → `add-dlq-replay`.

**Files added:**
- `data-platform/governance/contracts/{customers,products,orders}.yaml`
- `tests/contracts/test_schema_drift.py`
- `tests/contracts/__init__.py`
- `tests/contracts/parsers.py` (shared helpers to parse each layer, including an OM REST client)
- `.github/workflows/ingest-on-schema-change.yml` (or equivalent CI hook; see design.md Decision 10 for exact CI surface)

**Files modified:**
- `pyproject.toml` — add `datacontract-cli`, `sqlglot` to `dev` group
- `Makefile` — no new target (drift test picked up by existing `make test` via pytest collection; CI hook calls the pre-existing `make ingest-all` from `add-om-ingestion`)
- `docs/governance.md` — add "Data contracts (source of truth)" and "Three views (contract / OM / GX) and how they cross-check" sections
- `openspec/specs/data-governance/spec.md` — receives four new requirements after archive

**No runtime code changes.** Contracts are read-only reference. Existing GX gate, PII UDFs, RBAC, DLQ topology, and retention scripts stay exactly as they are.

**CI blast radius:** `make test` will start failing if column drift exists in any of the four hard-gate layers (Postgres / Spark / ClickHouse / GX). First run against current state may reveal existing drift (e.g., `_deleted`, `_version` in ClickHouse not in Postgres DDL — expected metadata columns, handled by explicit contract annotation). The OM layer is a soft-fail (skips with a diagnostic when OM is unreachable) so `make test` remains runnable on dev laptops without the governance stack up.

**Dependencies:** `datacontract-cli` is Python-only, ~30MB install. `sqlglot` is pure-Python, no compilation. OM REST client uses `httpx` (already a transitive dep of `datacontract-cli`) or falls back to `urllib` if we want to stay zero-dep.
