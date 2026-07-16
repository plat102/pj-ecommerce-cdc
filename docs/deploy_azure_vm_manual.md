# Deploy on Azure Student VM (manual, portal-only)

Portal + SSH walk-through — no Terraform. Suitable for demos and academic use. For the Terraform-based flow see [`deploy_azure_vm.md`](deploy_azure_vm.md); for what actually runs see [`architecture.md`](architecture.md).

## 1. Register for Azure Student

- https://azure.microsoft.com/en-us/free/students/
- $100 free credit for 1 year, no credit card required.

## 2. Create an Ubuntu VM

- Azure Portal → Virtual Machines → Create.
- Image: Ubuntu Server 22.04 LTS (or later).
- Size: `B2s` or larger — `B1s` is too small once the observability stack is on.
- Authentication: SSH key preferred.
- Inbound ports (Network Security Group):

| Port | Service |
|---|---|
| 22 | SSH |
| 8501 | Streamlit UI |
| 3000 | Grafana |
| 8085 | Debezium UI |
| 8083 | Kafka Connect REST |
| 8080 | Redpanda Console |
| 8081 | Apicurio Registry |
| 8123 / 9000 | ClickHouse HTTP / native |
| 4040 / 8888 | Spark UI / Jupyter |
| 9090 | Prometheus |
| 3100 | Loki (query API) |
| 8082 | cAdvisor |
| 9100 | node-exporter |
| 12345 | Alloy |
| 8889 / 4317 / 4318 | OTEL Collector self-metrics / OTLP gRPC / OTLP HTTP |

Open source-DB ports (5432, 9092) only if you need external access; otherwise leave them internal.

## 3. Install Docker

```sh
sudo apt update
sudo apt install -y docker.io docker-compose-plugin make git
sudo usermod -aG docker $USER
# log out + back in for group membership to take effect
```

## 4. Clone and configure

```sh
git clone https://github.com/plat102/pj-ecommerce-cdc.git
cd pj-ecommerce-cdc
cp .env.example infrastructure/docker/.env
# edit infrastructure/docker/.env — set GRAFANA_ADMIN_PASSWORD, POSTGRES_PASSWORD,
# CLICKHOUSE_ANALYST_PASSWORD, PII_SALT, OBS_ALERT_WEBHOOK_URL, ...
```

The `.env` path is deliberate — `make up` will fail if `.env` sits at the repo root instead.

## 5. Start the stack

```sh
docker network create ecommerce-network
make up
```

`make up` composes seven docker-compose files (db, kafka, debezium, ui, spark, analytics, observability) under project name `ecommerce-cdc` and auto-registers the Debezium PostgreSQL connector after services report healthy. See `CLAUDE.md` for the full make-target reference.

## 6. Verify

```sh
make status              # container states + healthchecks
make check-connector     # Debezium connector status (RUNNING expected)
```

Open the UIs at `http://<VM_Public_IP>:<port>` — port list in section 2.

Grafana login: `admin` / `<GRAFANA_ADMIN_PASSWORD>` from `.env`.

## 7. Share

Send the VM public IP and port list. Everyone with network access to those ports can drive the demo and view dashboards.

## 8. Notes

- **Change default passwords** in `.env` before exposing the VM — the file ships with example values.
- Deallocate the VM when idle to save credit: `az vm deallocate --resource-group <rg> --name <vm>`.
- `make down` wipes all volumes (Postgres, Kafka, ClickHouse, Loki, Prometheus, Spark checkpoints). Use `make stop` / `make start` to preserve state.
- Not for production — demo/academic use only.
