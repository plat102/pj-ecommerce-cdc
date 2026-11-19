# Deploy on Azure VM (Terraform)

Provisions an Ubuntu VM with Terraform, then runs the full stack via `make up`. For a manual (portal-only) walk-through see [`deploy_azure_vm_manual.md`](deploy_azure_vm_manual.md). For what actually runs on the VM see [`architecture.md`](architecture.md).

## 1. Provision the VM

```sh
cd infrastructure/terraform
terraform init
terraform plan
terraform apply
```

Capture the VM public IP from Terraform output or the Azure Portal.

## 2. SSH in

```sh
ssh azureuser@<VM_Public_IP>
```

## 3. Clone the project

```sh
git clone https://github.com/plat102/pj-ecommerce-cdc.git
cd pj-ecommerce-cdc
```

## 4. Create the env file

`.env` lives at `infrastructure/docker/.env` (not the repo root):

```sh
cp .env.example infrastructure/docker/.env
# edit infrastructure/docker/.env — set POSTGRES_PASSWORD, GRAFANA_ADMIN_PASSWORD,
# CLICKHOUSE_ANALYST_PASSWORD, PII_SALT, OBS_ALERT_WEBHOOK_URL, ... to real values
```

## 5. Start all services

```sh
docker network create ecommerce-network
make up
```

`make up` composes seven files under project name `ecommerce-cdc` (db, kafka, debezium, ui, spark, analytics, observability) and auto-registers the Debezium connector after services report healthy.

Verify the connector: `make check-connector` — expect `pg-connector-ecommerce` in `RUNNING` state. If not, see [`governance.md`](governance.md#schema-registry-apicurio) for connector config and [`observability.md`](observability.md#log-pipeline-loki--alloy) for reading Debezium logs.

## 6. Open the UIs

Replace `<VM_Public_IP>` with the address from step 1. Credentials come from `.env`.

**Core**

| Service | URL |
|---|---|
| Streamlit UI | `http://<VM_Public_IP>:8501` |
| Grafana | `http://<VM_Public_IP>:3000` (`admin` / `<GRAFANA_ADMIN_PASSWORD>`) |
| Debezium UI | `http://<VM_Public_IP>:8085` |
| Kafka Connect REST | `http://<VM_Public_IP>:8083` |
| Redpanda Console | `http://<VM_Public_IP>:8080` |
| Apicurio Registry | `http://<VM_Public_IP>:8081` |
| ClickHouse HTTP | `http://<VM_Public_IP>:8123` (native port 9000) |
| Spark UI | `http://<VM_Public_IP>:4040` |
| Jupyter | `http://<VM_Public_IP>:8888` |

**Observability**

| Service | URL |
|---|---|
| Prometheus | `http://<VM_Public_IP>:9090` |
| Loki (query API) | `http://<VM_Public_IP>:3100` — view logs via Grafana Explore |
| cAdvisor | `http://<VM_Public_IP>:8082` |
| node-exporter | `http://<VM_Public_IP>:9100/metrics` |
| Alloy | `http://<VM_Public_IP>:12345` |
| OTEL Collector self-metrics | `http://<VM_Public_IP>:8889/metrics` |
| OTEL Collector OTLP | gRPC `:4317`, HTTP `:4318` |

Open matching inbound ports in the Azure Network Security Group.

## VM lifecycle

- **Update infrastructure** — `terraform apply` (resource group: `ecommerce-cdc-rg`).
- **Deallocate to save cost** (preserves disks):
  ```sh
  az vm deallocate --resource-group ecommerce-cdc-rg --name <vm_name>
  ```
- **List VMs in the RG**:
  ```sh
  az vm list --resource-group ecommerce-cdc-rg --query "[].name" -o tsv
  ```
- **Status of all VMs**:
  ```sh
  az vm list --resource-group ecommerce-cdc-rg --show-details \
    --query "[].{name:name, powerState:powerState}" -o table
  ```
- **Start / stop all**:
  ```sh
  for vm in $(az vm list --resource-group ecommerce-cdc-rg --query "[].name" -o tsv); do
    az vm start      --resource-group ecommerce-cdc-rg --name $vm    # or: deallocate
  done
  ```
- **Destroy everything** — `terraform destroy`.

## Notes

- To pick up `.env` edits: `make restart`.
- To reset all data (Postgres, Kafka, ClickHouse, Loki, Prometheus, Spark checkpoints): `make down` (destructive) then `make up`.
- To preserve state across a stop/start: use `make stop` and `make start` — volumes survive.
