# Deploy CDC Ecommerce Project on Azure VM

## 1. Provision VM with Terraform

```sh
cd infrastructure/terraform
terraform init
terraform plan
terraform apply
```

- Get the VM public IP from Terraform output or Azure Portal.

## 2. SSH into the VM

```sh
ssh azureuser@<VM_Public_IP>
```

## 3. Clone the Project

```sh
git clone https://github.com/plat102/pj-ecommerce-cdc.git
cd pj-ecommerce-cdc
```

## 4. Create Environment File

```sh
cp .env.example infrastructure/docker/.env
```

- Edit `infrastructure/docker/.env` to customize environment variables if needed.

## 5. Start All Services

```sh
docker network create ecommerce-network
make up
```

## 6. Access UIs in Browser

- Streamlit UI: `http://<VM_Public_IP>:8501`
- Grafana: `http://<VM_Public_IP>:3000` (user: admin, pass: admin123)
- Debezium UI: `http://<VM_Public_IP>:8085`
- Kafka Console: `http://<VM_Public_IP>:8080`
- Jupyter Spark: `http://<VM_Public_IP>:8888`

## VM Lifecycle Management

- **Create & Update:** Use Terraform to provision and update resources.

  ```sh
  terraform apply
  ```
- **Stop VM (Deallocate):** Use Azure CLI to stop the VM and save costs (resources/data remain).

  ```sh
  az vm deallocate --resource-group <resource_group_name> --name <vm_name>
  ```

  Resource group: `ecommerce-cdc-rg`

  - List all VM:
    - ```bash
      az vm list --resource-group ecommerce-cdc-rg --query "[].name" -o tsv
      ```
  - Show status of all VMs:
    - ```bash
      az vm list --resource-group ecommerce-cdc-rg --show-details --query "[].{name:name, powerState:powerState}" -o table
      ```
  - Start all:
    - ```bash
      for vm in $(az vm list --resource-group ecommerce-cdc-rg --query "[].name" -o tsv); do
        az vm start --resource-group ecommerce-cdc-rg --name $vm
      done
      ```
  - Stop all
    - ```bash
      for vm in $(az vm list --resource-group ecommerce-cdc-rg --query "[].name" -o tsv); do
        az vm deallocate --resource-group ecommerce-cdc-rg --name $vm
      done
      ```
- **Start VM:** Use Azure CLI to start the VM again.

  ```sh
  az vm start --resource-group <resource_group_name> --name <vm_name>
  ```
- **Destroy (Delete):** Use Terraform to remove all resources.

  ```sh
  terraform destroy
  ```

---

**Note:**

- Make sure required ports are open in Azure Network Security Group.
- To update environment variables, edit `.env` and run `make restart`.
