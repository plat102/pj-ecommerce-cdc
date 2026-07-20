## MODIFIED Requirements

### Requirement: gx-batch-validation
Each Spark CDC job SHALL run a Great Expectations suite (loaded from `data-platform/governance/expectations/{table}_cdc_suite.json` — matching the `table_name` used to instantiate the gate) against every micro-batch DataFrame **before** the ClickHouse write. Suites SHALL be gated by the `ENABLE_GX_GATE=1` environment variable so dev environments without the `great_expectations` package continue to function unchanged. When `ENABLE_GX_DATA_DOCS=1` is also set, the real Great Expectations engine SHALL run as a second-pass reporter alongside the inline gate (see `gx-real-engine-runner` in the `data-quality-reporting` capability); the inline gate SHALL remain the authoritative row-drop decision.

#### Scenario: valid rows written to ClickHouse
- **WHEN** a batch of CDC events passes every column-level expectation in the table's suite
- **THEN** all rows in the batch SHALL be written to the ClickHouse `{table}_cdc` table via the existing JDBC writer

#### Scenario: expectation suite path
- **WHEN** the customers CDC job starts under `ENABLE_GX_GATE=1`
- **THEN** the suite SHALL be resolved from `${GX_SUITE_DIR:-/home/jupyter/governance/expectations}/customers_cdc_suite.json` (matching the `table_name` used to instantiate the gate) and SHALL contain at least the `expect_column_values_to_not_be_null` expectation on `id` and `_version`

#### Scenario: real GX engine second-pass when opt-in
- **WHEN** `ENABLE_GX_GATE=1` and `ENABLE_GX_DATA_DOCS=1` are both set
- **THEN** each batch SHALL be validated by the inline gate (authoritative) AND by the real GX engine (reporting only)
- **AND** the row-drop decision SHALL be identical to what the inline gate alone would have produced (GX cannot influence landing)
