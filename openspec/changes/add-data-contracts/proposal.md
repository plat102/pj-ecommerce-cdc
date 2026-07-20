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
- Wire the drift test into `make test` as a hard gate so PRs fail on divergence.
- Add `datacontract-cli>=1.0.13` and a lightweight SQL parser (`sqlglot`) to the `dev` dependency group in `pyproject.toml`.
- Document the contract workflow in `docs/governance.md` (link from the existing "Catalog & lineage" section — contracts are the authoritative side of catalog).

**Not in scope** (deferred to future changes):
- Code generation FROM contracts (Phase 3). Contracts stay read-only reference for now; the existing schema files remain hand-maintained.
- ClickHouse `Decimal` scale/precision matching beyond logical type (approximation is enough for Phase 1+2).
- Contract versioning / compatibility rules (BACKWARD/FORWARD). Deferred until schema evolution becomes a real event.

## Capabilities

### New Capabilities

None. Contract enforcement is a governance concern that sits naturally alongside existing GX suites, PII rules, and RBAC.

### Modified Capabilities

- `data-governance`: Add three new requirements — `data-contract-yaml-per-table` (contract file existence + shape), `contract-schema-drift-test` (drift-detection semantics across four layers), and `contract-drift-ci-gate` (wire into `make test` as blocking gate).

## Impact

**Files added:**
- `data-platform/governance/contracts/{customers,products,orders}.yaml`
- `tests/contracts/test_schema_drift.py`
- `tests/contracts/__init__.py`
- `tests/contracts/parsers.py` (shared helpers to parse each layer)

**Files modified:**
- `pyproject.toml` — add `datacontract-cli`, `sqlglot` to `dev` group
- `Makefile` — no new target (drift test picked up by existing `make test` via pytest collection)
- `docs/governance.md` — add "Data contracts (source of truth)" section
- `openspec/specs/data-governance/spec.md` — receives three new requirements after archive

**No runtime code changes.** Contracts are read-only reference. Existing GX gate, PII UDFs, RBAC, DLQ topology, and retention scripts stay exactly as they are.

**CI blast radius:** `make test` will start failing if column drift exists. First run against current state may reveal existing drift (e.g., `_deleted`, `_version` in ClickHouse not in Postgres DDL — expected metadata columns, handled by explicit contract annotation).

**Dependencies:** `datacontract-cli` is Python-only, ~30MB install. `sqlglot` is pure-Python, no compilation.
