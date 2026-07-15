## ADDED Requirements

> **Status:** Phase 4 of this change adds a new Streamlit view for triaging DLQ contents across all `*_dlq` topics. Read-only; no replay button by design (see design.md § Non-Goals). Reuses `managers/kafka.py::consume_messages`.

### Requirement: dlq-triage-view
Streamlit SHALL provide a read-only DLQ Triage view at a top-level route (menu label "DLQ Triage") that lists recent messages across every DLQ topic in the stack: `debezium_connect_dlq`, `{customers,products,orders}_dlq` (GX validation), and `{customers,products,orders}_sink_dlq` (Spark sink). The view SHALL consume via the existing `managers/kafka.py::consume_messages` API and render a table with columns `dlq_topic`, `_error_stage`, `_error_class`, `_error_message` (truncated to 80 characters), `key`, `first_seen` (timestamp). Each row SHALL be expandable to reveal the full JSON payload.

#### Scenario: developer inspects DLQ contents
- **WHEN** a developer navigates to the DLQ Triage view in the Streamlit UI after DLQ traffic has occurred
- **THEN** the page SHALL list at least the most-recent 100 DLQ messages across all DLQ topics in a sortable table
- **AND** clicking a row SHALL expand a JSON view showing the full quarantined payload

#### Scenario: empty state renders gracefully
- **WHEN** no DLQ traffic has occurred in the last 5 minutes
- **THEN** the page SHALL render an empty-state message (e.g., "No DLQ messages in the last 5 minutes") and SHALL NOT throw or hang
