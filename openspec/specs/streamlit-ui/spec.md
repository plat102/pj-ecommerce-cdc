## Purpose

Streamlit-based testing UI for driving and observing CDC events. Provides CRUD pages against the three Postgres source tables, a read-only Kafka monitor of Debezium envelopes, and a batch generator for throughput testing. Connection settings differ between Docker-network and host-local execution modes.
## Requirements
### Requirement: crud-customers
The Streamlit UI SHALL allow users to INSERT, UPDATE, and DELETE rows in the PostgreSQL `customers` table via the Customers page (`views/customers.py`).

#### Scenario: insert new customer
- **WHEN** a user fills in name and email fields and submits the add form
- **THEN** a new row SHALL be inserted into `public.customers` and appear in the customers list on refresh

#### Scenario: update customer
- **WHEN** a user selects a customer and submits edited name or email
- **THEN** the corresponding row SHALL be updated in `public.customers` and Debezium SHALL capture the change

#### Scenario: delete customer
- **WHEN** a user selects a customer and confirms deletion
- **THEN** the row SHALL be deleted from `public.customers` and Debezium SHALL capture a delete event

---

### Requirement: crud-products
The Streamlit UI SHALL allow users to INSERT, UPDATE, and DELETE rows in the PostgreSQL `products` table via the Products page (`views/products.py`). Product price SHALL be accepted as a decimal number.

#### Scenario: insert product with price
- **WHEN** a user adds a product with a decimal price (e.g., 9.99)
- **THEN** the price SHALL be stored correctly in Postgres and Debezium SHALL emit the decimal-encoded value

#### Scenario: delete product
- **WHEN** a user deletes a product
- **THEN** the row SHALL be removed from `public.products` and a delete event SHALL be captured

---

### Requirement: crud-orders
The Streamlit UI SHALL allow users to INSERT and DELETE rows in the PostgreSQL `orders` table via the Orders page (`views/orders.py`). Order creation SHALL require selecting an existing customer and product.

#### Scenario: create order
- **WHEN** a user selects a customer, selects a product, and submits the order form
- **THEN** a new row SHALL be inserted into `public.orders` referencing valid `customer_id` and `product_id`

#### Scenario: delete order
- **WHEN** a user deletes an order
- **THEN** the row SHALL be removed from `public.orders` and a delete event SHALL be captured by Debezium

---

### Requirement: kafka-monitor
The Kafka Monitor page (`views/kafka_monitor.py`) SHALL display raw Debezium envelope messages consumed from all three CDC topics in read-only mode. The UI SHALL NOT produce any messages to Kafka.

#### Scenario: view recent CDC messages
- **WHEN** a user opens the Kafka Monitor page
- **THEN** recent messages from `pg.public.customers`, `pg.public.products`, and `pg.public.orders` SHALL be displayed, including topic, partition, offset, timestamp, and raw JSON value

#### Scenario: no message production
- **WHEN** any action is taken in the Kafka Monitor view
- **THEN** no messages SHALL be produced to any Kafka topic

---

### Requirement: batch-testing
The Batch Testing page (`views/batch_testing.py`) SHALL allow users to bulk-insert sample rows into Postgres to test CDC throughput.

#### Scenario: bulk insert generates CDC events
- **WHEN** a user triggers bulk insert of N customers/products/orders
- **THEN** N corresponding Debezium messages SHALL appear on the relevant Kafka topics

---

### Requirement: connection-config
The UI SHALL read database and Kafka connection settings from environment variables via `config/settings.py`. In Docker mode, the UI SHALL connect to `postgres:5432` and `kafka1:9092`. In local host mode (`make run-ui-local`), the UI SHALL connect to `localhost` with the published ports from `.env`.

#### Scenario: docker mode connectivity
- **WHEN** the UI container starts via `make up-ui`
- **THEN** the UI SHALL connect to Postgres and Kafka using in-container hostnames and display a green connection status indicator

#### Scenario: host mode connectivity
- **WHEN** the UI is started via `make run-ui-local` with an active venv
- **THEN** the UI SHALL connect to `localhost` on the ports defined in `infrastructure/docker/.env`

---

### Requirement: session-state-caching
The UI SHALL cache Postgres and Kafka manager instances in Streamlit session state (via `utils/helpers.py`) to avoid reconnecting on every user interaction.

#### Scenario: no reconnect on navigation
- **WHEN** a user navigates between pages (e.g., Customers to Products)
- **THEN** the existing DB and Kafka connections SHALL be reused without establishing new connections

### Requirement: dlq-triage-view
Streamlit SHALL provide a read-only DLQ Triage view at a top-level route (menu label "DLQ Triage") that lists recent messages across every DLQ topic in the stack: `debezium_connect_dlq`, `{customers,products,orders}_dlq` (GX validation), and `{customers,products,orders}_sink_dlq` (Spark sink). The view SHALL consume via the existing `managers/kafka.py::consume_messages` API and render a table with columns `dlq_topic`, `_error_stage`, `_error_class`, `_error_message` (truncated to 80 characters), `key`, `first_seen` (timestamp). Each row SHALL be expandable to reveal the full JSON payload.

#### Scenario: developer inspects DLQ contents
- **WHEN** a developer navigates to the DLQ Triage view in the Streamlit UI after DLQ traffic has occurred
- **THEN** the page SHALL list at least the most-recent 100 DLQ messages across all DLQ topics in a sortable table
- **AND** clicking a row SHALL expand a JSON view showing the full quarantined payload

#### Scenario: empty state renders gracefully
- **WHEN** no DLQ traffic has occurred in the last 5 minutes
- **THEN** the page SHALL render an empty-state message (e.g., "No DLQ messages in the last 5 minutes") and SHALL NOT throw or hang

