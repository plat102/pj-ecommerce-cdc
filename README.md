# CDC Ecommerce Project

This project is a demo platform for Change Data Capture (CDC) in ecommerce, featuring:
- Streamlit UI for editing/viewing data
- Kafka, Debezium, Postgres, Spark, ClickHouse, Grafana dashboards


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

## Development

```bash
# Generate demo data
make demo-data

# Build Docker image
make build-ui
```
