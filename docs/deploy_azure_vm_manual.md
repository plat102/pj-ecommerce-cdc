
# Guide: Deploying the Entire Project on Azure Student VM

## 1. Register for Azure Student
- Visit https://azure.microsoft.com/en-us/free/students/
- Sign up for an Azure Student account to receive $100 free credit for 1 year (no credit card required).

## 2. Create an Ubuntu VM on Azure
- Go to Azure Portal > Virtual Machines > Create
- Select Ubuntu Server 22.04 LTS (or the latest version)
- Choose a small size: B1s or B2s (cost-effective)
- Set up user/password or SSH key
- Open the required ports:
  - 22 (SSH)
  - 5432 (Postgres)
  - 8083 (Debezium)
  - 9092 (Kafka)
  - 3000 (Grafana)
  - 8501 (Streamlit UI)
  - Other ports as needed

## 3. Install Docker & Docker Compose on the VM
```bash
sudo apt update
sudo apt install -y docker.io docker-compose
sudo usermod -aG docker $USER
```
- Log out and log back in to apply Docker permissions.

## 4. Clone the Project to the VM
```bash
git clone https://github.com/plat102/pj-ecommerce-cdc.git
cd pj-ecommerce-cdc
```

## 5. Run Services with Docker Compose
- Make sure you have a `docker-compose.yml` file configured for all services: Postgres, Kafka, Debezium, Spark, ClickHouse, Grafana, Streamlit UI, etc.
- Run:
```bash
docker-compose up -d
```

## 6. Check the Services
- Access the services via: `http://<VM_Public_IP>:<port>`
  - Streamlit UI: `http://<VM_Public_IP>:8501`
  - Grafana: `http://<VM_Public_IP>:3000`
  - Debezium: `http://<VM_Public_IP>:8083`
  - etc.

## 7. Share with Friends/Instructor
- Send the public IP + port links so everyone can access, edit data, and view dashboards.

## 8. Notes
- For security, change default passwords for services or configure firewall rules.
- If you run out of credit, you can delete and recreate the VM.
- Not for production use—recommended for demo/academic purposes only.

---
**This document is for deploying the entire Docker stack on an Azure Student VM, suitable for academic projects, demos, and learning.**
