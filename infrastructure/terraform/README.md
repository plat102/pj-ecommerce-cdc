# Deploying Azure VM with Terraform

This guide helps you automatically provision an Ubuntu VM on Azure, pre-installed with Docker & Docker Compose, ready for your CDC project stack.

## Prerequisites

- Azure account (Azure Student recommended)
- Terraform installed ([Install guide](https://learn.hashicorp.com/tutorials/terraform/install-cli))
- Azure CLI installed & logged in (`az login`)

```bash
az account show
```

## Steps

### 1. Clone the repository

```bash
git clone https://github.com/plat102/pj-ecommerce-cdc.git
cd pj-ecommerce-cdc/infrastructure/terraform
```

### 2. Initialize Terraform

```bash
terraform init
```

### 3. Apply Terraform configuration

```bash
terraform apply
```

- Review the plan and type `yes` to confirm.

### 4. Get the VM public IP

- After completion, Terraform will output the VM's public IP address.

```
terraform output public_ip
```

### 5. SSH into the VM

```bash
ssh azureuser@<VM_Public_IP>
```

- Default password: `<password in tfvars>` (change after first login)

### 6. Clone your project & run Docker Compose

```bash
git clone https://github.com/plat102/pj-ecommerce-cdc.git
cd pj-ecommerce-cdc
docker network create ecommerce-network
make up
```

## Notes

- The VM is pre-installed with Docker & Docker Compose via cloud-init.
- Open ports: 22 (SSH), 5432 (Postgres), 8083 (Debezium), 9092 (Kafka), 3000 (Grafana), 8501 (Streamlit UI).
- For production, change passwords and review security settings.
- To destroy resources:

```bash
terraform destroy
```

---

**This setup is for demo, academic, and development purposes.**
