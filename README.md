# CDC Ecommerce Project

This project is a demo platform for Change Data Capture (CDC) in ecommerce, featuring:

- Streamlit UI for editing/viewing data
- Kafka, Debezium, Postgres, Spark, ClickHouse, Grafana dashboards

## Technical stack


| **Layer**                    | **Technology**           | **Purpose**                                           |
| ---------------------------------- | ------------------------------ | ----------------------------------------------------------- |
| **Data Source (OLTP)**       | PostgreSQL                     | Source transactional database for CDC demo.                 |
| **Change Data Capture**      | Debezium                       | Captures row-level changes and streams to Kafka.            |
| **Event Streaming**          | Kafka / Redpanda               | Message broker for CDC events.                              |
| **Stream Processing**        | PySpark (Structured Streaming) | Transforms, enriches, and deduplicates CDC data.            |
| **Analytics Storage (OLAP)** | ClickHouse                     | Stores processed data for fast analytical queries.          |
| **Visualization**            | Grafana                        | Dashboards for monitoring CDC pipelines.                    |
| **Demo UI**                  | Streamlit                      | Interactive interface to test CDC and generate sample data. |
| **Infrastructure Setup**   | Docker Compose, Makefile       | Manages local deployment and service automation.            |

![1760612911844](image/README/1760612911844.png)

## Requirements

- Docker & Docker Compose installed
	- [Install Docker](https://docs.docker.com/get-docker/)
	- [Install Docker Compose](https://docs.docker.com/compose/install/)
- GNU Make installed
  - [Install Make](https://www.gnu.org/software/make/)

### Installation on Ubuntu

Install required tools with the following commands:

```bash
# Install Docker
sudo apt update
sudo apt install -y docker.io
sudo systemctl enable docker
sudo systemctl start docker

# Install Docker Compose
sudo apt install -y docker-compose

# Install GNU Make
sudo apt install -y make
```

## Quick Start (Docker Only)

Clone the repository, copy environment file, and run the entire CDC Ecommerce stack:

```bash
git clone https://github.com/plat102/pj-ecommerce-cdc.git
cd pj-ecommerce-cdc

# Create the .env file
cp .env.example infrastructure/docker/.env

 # Start all services (DB, Kafka, Debezium, UI, Spark, Analytics...)
make up
```

## Available Dashboards & UIs

After running `make up`, you can access the following interfaces:

- **Streamlit UI (CDC Testing UI):**

  - [http://localhost:8501](http://localhost:8501)
  - Edit and view data, test CDC flows interactively.

  ![Streamlit UI](docs/images/streamlit-ui.png)
- **Grafana Dashboard:**

  - [http://localhost:3000](http://localhost:3000)
  - Visualize analytics and metrics (default user: `admin`, password: `admin123`).
  - Query and explore analytics data in ClickHouse.

  ![Grafana Dashboard](docs/images/grafana.png)
- **Debezium UI:**

  - [http://localhost:8085](http://localhost:8085)
  - Manage CDC connectors and monitor their status.

  ![Debezium UI](docs/images/debezium-ui.png)
- **Kafka Console (Redpanda Console):**

  - [http://localhost:8080](http://localhost:8080)
  - Inspect Kafka topics, messages, and consumer groups.

  ![Kafka Console](docs/images/kafka-console.png)

---
