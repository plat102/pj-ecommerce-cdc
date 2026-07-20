## 0. Prerequisites

- [ ] 0.1 Confirm `add-om-ingestion` is archived (or at minimum: `make ingest-all` target exists, ingestion YAMLs are wired, the governance stack is bring-up-able). If not, block on that change first — see design.md Migration Plan.
- [ ] 0.2 Bring up the governance stack: `make up-governance && make ingest-all`. Verify `curl -sf http://localhost:8585/api/v1/tables/name/ecommerce-postgres.public.customers | jq .columns` returns a non-empty column list (used later by the OM-layer drift check).

## 1. Dev environment prep

- [ ] 1.1 Add `datacontract-cli>=1.0.13` and `sqlglot>=25.0.0` to the `dev` dependency group in `pyproject.toml`
- [ ] 1.2 Run `make uv-sync` and confirm both packages resolve without lock conflicts
- [ ] 1.3 Verify `uv run datacontract --version` returns 1.0.13 or newer (smoke test the CLI is available)
- [ ] 1.4 Confirm `httpx` resolves as a transitive dep of `datacontract-cli` (used by the OM REST client in §3.2). If it doesn't, add it explicitly to the `dev` group.

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
  - `OMClient` — thin wrapper around `httpx` (or `urllib` fallback) with base URL `http://localhost:8585` (overridable via `OM_BASE_URL` env), Bearer auth from `OPENMETADATA_JWT_TOKEN`, one method `fetch_table(fqn: str) -> list[Column] | None` that returns `None` on connection error / 404 / auth failure with a logged reason
  - `parse_om_table(fqn: str, client: OMClient) -> list[Column] | None` — passthrough for consistency with the other `parse_*` functions
  - Type-mapping table constant `TYPE_MAP: dict[str, dict[Layer, set[str]]]` — maps ODCS `logicalType` to acceptable per-layer types (integer→{Int32, Int64}, etc.). The `om` layer accepts the same types as Postgres for source-side FQNs and the same as ClickHouse for sink-side FQNs.
- [ ] 3.3 Create `tests/contracts/test_schema_drift.py` with pytest parametrization: for each contract file × each layer (postgres, spark, clickhouse, gx, om-source, om-sink), one test. Failures on the four DDL/GX layers report contract path, layer, missing/extra columns, and type mismatches. For OM layers: if `parse_om_table` returns `None`, call `pytest.skip(reason)` — the test is skipped, not failed, and the skip message names the FQN and why (unreachable / 404 / auth). If OM returns columns, apply the same comparison as the DDL layers.
- [ ] 3.4 Add a helper `filter_metadata_columns(contract_columns, layer)` that drops columns with `customProperties.origin=sink_metadata` when comparing against postgres, spark, or om-source (sink metadata columns SHALL still be required in clickhouse and om-sink).
- [ ] 3.5 Add helper `contract_to_om_fqn(contract: Contract, layer: Literal["om-source", "om-sink"]) -> str` that resolves the OM FQN from the contract's `servers` block (e.g., `ecommerce-postgres.public.customers` for source, `ecommerce-clickhouse.ecommerce_analytics.customers_cdc` for sink). Match the service names declared in `add-om-ingestion` ingestion YAMLs — if those change, this helper is the single point to update.

## 4. Bootstrap and iterate

- [ ] 4.1 Run `uv run pytest tests/contracts/ -v` — expect failures on first run since contracts were written from best-guess mapping
- [ ] 4.2 For each failure on the four DDL/GX layers, decide direction: fix the contract to match code, OR fix the code (schema file / DDL) to match contract intent. Prefer aligning contract to code for the initial commit — code is running reality.
- [ ] 4.3 For OM-layer failures (not skips): re-run `make ingest-all` to refresh OM. If it still diverges, either the contract or the DDL is genuinely wrong — same decision as above.
- [ ] 4.4 Iterate until all drift tests pass (or OM layers skip with the expected reason when the governance stack isn't up)
- [ ] 4.5 Re-run full `make test` and confirm nothing else regressed
- [ ] 4.6 Tear down the governance stack (`make down-governance`), re-run `make test`, and confirm the OM layers cleanly skip rather than fail — this validates the soft-fail contract on dev laptops without OM

## 5. CI ingest-on-schema-change hook

- [ ] 5.1 Add a CI workflow (assuming GHA: `.github/workflows/ingest-on-schema-change.yml`) that triggers on `paths: [infrastructure/docker/postgres/init.sql, infrastructure/docker/clickhouse/create_tables.sql]`. The workflow SHALL: (a) start the governance stack (`make up-governance`), (b) wait for OM readiness (`curl -sf http://localhost:8585/api/v1/system/version`), (c) run `make ingest-all`, (d) run `make test`. If the repo uses a different CI system, mirror the same steps there.
- [ ] 5.2 Add a fallback matrix entry for when neither schema file changed: `make test` runs without the pre-ingest step; the OM-layer check either skips (OM not up in CI) or runs against whatever the previous ingest snapshot showed (accepted, since no schema change means no drift risk from this PR).
- [ ] 5.3 Document the CI hook in `docs/governance.md` — one paragraph explaining what triggers it and why (so contributors don't wonder why some PRs run `make ingest-all` and others don't).

## 6. Documentation and wire-up

- [ ] 6.1 Add a "Data contracts (source of truth)" section to `docs/governance.md`, placed above the existing "Catalog & lineage (optional)" section. Explain: what contracts declare, where they live, how the drift test enforces them, and how to add a new column (edit contract, edit code, drift test verifies).
- [ ] 6.2 Add a "Three views (contract / OM / GX) and how they cross-check" subsection to `docs/governance.md`. Include the table from design.md Context, name the audience (DE + DA re-checking data), and state which cross-checks are enforced vs. deferred (schema: enforced via drift test; PII semantics: deferred, see Decision 11).
- [ ] 6.3 Update the "Where to look" table in `docs/governance.md` to include `Data contracts | data-platform/governance/contracts/`
- [ ] 6.4 Verify `openspec show add-data-contracts --json --deltas-only` reports the four new requirements (data-contract-yaml-per-table, contract-schema-drift-test, contract-om-catalog-reconciliation, contract-drift-ci-gate)

## 7. Verification and archive prep

- [ ] 7.1 Run `openspec validate add-data-contracts --strict` — must pass
- [ ] 7.2 Run `make test` with governance stack up — must pass with all drift tests (including OM layers) included
- [ ] 7.3 Run `make test` with governance stack down — must pass with OM layers skipping cleanly
- [ ] 7.4 Manually verify each scenario from the delta spec by inducing the failure (e.g., temporarily add an unannotated column to a contract, confirm test fails with the expected message; drop a column in OM by editing an ingestion YAML filter, re-ingest, confirm OM-layer check fails; then revert)
- [ ] 7.5 Confirm no runtime code path changed — `git diff` on `data-platform/streaming/`, `infrastructure/docker/postgres/`, `infrastructure/docker/clickhouse/` shows only content-preserving edits (if any bootstrap correction was needed)
