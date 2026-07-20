## 1. Dev environment prep

- [ ] 1.1 Add `datacontract-cli>=1.0.13` and `sqlglot>=25.0.0` to the `dev` dependency group in `pyproject.toml`
- [ ] 1.2 Run `make uv-sync` and confirm both packages resolve without lock conflicts
- [ ] 1.3 Verify `uv run datacontract --version` returns 1.0.13 or newer (smoke test the CLI is available)

## 2. Contract file scaffolding

- [ ] 2.1 Create directory `data-platform/governance/contracts/`
- [ ] 2.2 Create `data-platform/governance/contracts/customers.yaml` with ODCS v3.1 header, `info` block (owner, description), `servers` block (postgres/kafka/clickhouse), and `schema` block with columns `id`, `name`, `email`, `created_at`, `_version`, `_deleted`. Annotate `email` and `name` with PII `customProperties`; annotate `_version` and `_deleted` with `origin=sink_metadata`.
- [ ] 2.3 Create `data-platform/governance/contracts/products.yaml` with the same shape. Include `price` with `logicalType=decimal`, `precision=10`, `scale=2`, and wire-encoding `customProperties`.
- [ ] 2.4 Create `data-platform/governance/contracts/orders.yaml` with columns `id`, `customer_id`, `product_id`, `quantity`, `order_time`, `_version`, `_deleted`.
- [ ] 2.5 Validate each contract file parses cleanly with `uv run datacontract lint data-platform/governance/contracts/customers.yaml` (and the other two)

## 3. Drift-test infrastructure

- [ ] 3.1 Create `tests/contracts/__init__.py` (empty)
- [ ] 3.2 Create `tests/contracts/parsers.py` containing:
  - `parse_postgres_ddl(path: Path) -> dict[str, list[Column]]` — uses `sqlglot` to extract table→column list from `init.sql`
  - `parse_clickhouse_ddl(path: Path) -> dict[str, list[Column]]` — same for `create_tables.sql`, dialect `clickhouse`, filtering to `*_cdc` tables
  - `parse_spark_schema(path: Path) -> dict[str, list[Column]]` — uses `ast` module to walk `cdc_schemas.py`, extract each `get_*_value_schema` function's `after` block columns
  - `parse_gx_suite(path: Path) -> set[str]` — reads JSON, returns column names covered by `expect_column_values_to_not_be_null`
  - `parse_contract(path: Path) -> Contract` — reads ODCS YAML into a typed structure with column list + customProperties
  - Type-mapping table constant `TYPE_MAP: dict[str, dict[Layer, set[str]]]` — maps ODCS `logicalType` to acceptable per-layer types (integer→{Int32, Int64}, etc.)
- [ ] 3.3 Create `tests/contracts/test_schema_drift.py` with pytest parametrization: for each contract file × each layer (postgres, spark, clickhouse, gx), one test. Failures report contract path, layer, missing/extra columns, and type mismatches.
- [ ] 3.4 Add a helper `filter_metadata_columns(contract_columns, layer)` that drops columns with `customProperties.origin=sink_metadata` when comparing against postgres or spark

## 4. Bootstrap and iterate

- [ ] 4.1 Run `uv run pytest tests/contracts/ -v` — expect failures on first run since contracts were written from best-guess mapping
- [ ] 4.2 For each failure, decide direction: fix the contract to match code, OR fix the code (schema file / DDL) to match contract intent. Prefer aligning contract to code for the initial commit — code is running reality.
- [ ] 4.3 Iterate until all drift tests pass
- [ ] 4.4 Re-run full `make test` and confirm nothing else regressed

## 5. Documentation and wire-up

- [ ] 5.1 Add a "Data contracts (source of truth)" section to `docs/governance.md`, placed above the existing "Catalog & lineage (optional)" section. Explain: what contracts declare, where they live, how the drift test enforces them, and how to add a new column (edit contract, edit code, drift test verifies).
- [ ] 5.2 Update the "Where to look" table in `docs/governance.md` to include `Data contracts | data-platform/governance/contracts/`
- [ ] 5.3 Verify `openspec show add-data-contracts --json --deltas-only` reports the three new requirements

## 6. Verification and archive prep

- [ ] 6.1 Run `openspec validate add-data-contracts --strict` — must pass
- [ ] 6.2 Run `make test` — must pass with drift tests included
- [ ] 6.3 Manually verify each scenario from the delta spec by inducing the failure (e.g., temporarily add an unannotated column to a contract, confirm test fails with the expected message; then revert)
- [ ] 6.4 Confirm no runtime code path changed — `git diff` on `data-platform/streaming/`, `infrastructure/docker/postgres/`, `infrastructure/docker/clickhouse/` shows only content-preserving edits (if any bootstrap correction was needed)
