## MODIFIED Requirements

> **Status:** The existing `dlq-on-validation-failure` requirement gains one refinement: its payload envelope now aligns with the new sibling DLQ topics via the shared `dlq_producer.emit()` helper so downstream tooling (Streamlit triage view, alerting queries) can read all `*_dlq` topics with the same schema.

### Requirement: dlq-on-validation-failure
Rows that fail any column-level expectation SHALL be routed to a `{table}_dlq` Kafka topic before the `foreachBatch` delegates to the ClickHouse writer. The DLQ payload SHALL be produced via the shared `data-platform/streaming/spark/src/governance/dlq_producer.py::emit()` helper so its envelope matches sibling DLQ topics: it SHALL include `_error_stage` (constant `"gx_validation"`), `_error_class` (constant `"ExpectationFailure"`), `_error_message` (the failing expectation name), and `_error_expectation` (the expectation name) alongside the original row JSON. Failing rows SHALL NOT reach the ClickHouse `{table}_cdc` table.

#### Scenario: invalid row lands in DLQ with shared envelope
- **WHEN** a customers CDC event arrives with `id = null` and `ENABLE_GX_GATE=1`
- **THEN** the row SHALL be written to `customers_dlq` with `_error_stage="gx_validation"` and `_error_expectation="expect_column_values_to_not_be_null"`
- **AND** the same row SHALL NOT appear in `customers_cdc`

#### Scenario: valid rows in the same batch still land
- **WHEN** a batch of 10 orders contains one row failing `expect_column_values_to_be_in_set` on `_deleted` and nine passing rows
- **THEN** the nine passing rows SHALL be written to `orders_cdc` and the one failing row SHALL be written to `orders_dlq`

#### Scenario: envelope shape matches sibling DLQs
- **WHEN** a DLQ consumer reads messages from `customers_dlq` (GX) and `customers_sink_dlq` (sink)
- **THEN** both messages SHALL share the required envelope fields `_error_stage`, `_error_class`, `_error_message` — only the constant values differ (`"gx_validation"` vs `"spark_sink"`) so a single parser can handle both
