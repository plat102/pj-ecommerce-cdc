DOCKER_DIR := infrastructure/docker
ENV_FILE := $(DOCKER_DIR)/.env
PROJECT_NAME := ecommerce-cdc

COMPOSE = docker-compose -p $(PROJECT_NAME) --env-file $(ENV_FILE)

COMPOSE_DB := $(COMPOSE) -f $(DOCKER_DIR)/docker-compose.db.yml
COMPOSE_KAFKA := $(COMPOSE) -f $(DOCKER_DIR)/docker-compose.kafka.yml
COMPOSE_DBZ := $(COMPOSE) -f $(DOCKER_DIR)/docker-compose.debezium.yml
COMPOSE_UI := $(COMPOSE) -f $(DOCKER_DIR)/docker-compose.ui.yml
COMPOSE_SPARK := $(COMPOSE) -f $(DOCKER_DIR)/docker-compose.spark.yml
COMPOSE_ANALYTICS := $(COMPOSE) -f $(DOCKER_DIR)/docker-compose.analytics.yml

COMPOSE_ALL := $(COMPOSE) \
	-f $(DOCKER_DIR)/docker-compose.db.yml \
	-f $(DOCKER_DIR)/docker-compose.kafka.yml \
	-f $(DOCKER_DIR)/docker-compose.debezium.yml \
	-f $(DOCKER_DIR)/docker-compose.ui.yml \
	-f $(DOCKER_DIR)/docker-compose.spark.yml \
	-f $(DOCKER_DIR)/docker-compose.analytics.yml

include $(ENV_FILE)
export $(shell sed 's/=.*//' $(ENV_FILE))

.PHONY: help build up down logs status clean restart \
        up-db down-db up-kafka down-kafka sh-pg \
        up-spark down-spark logs-spark status-spark sh-spark-master \
        restart-spark spark-shell pyspark-shell spark-submit jupyter-token \
        up-analytics down-analytics logs-analytics grafana-url clickhouse-client

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

#=====================================================
# --- DB ---------------------------------------------
#=====================================================

up-db: ## Start PostgreSQL service
	$(COMPOSE_DB) up -d

down-db: ## Stop PostgreSQL service
	$(COMPOSE_DB) down --remove-orphans

sh-pg: ## Connect to PostgreSQL shell
	$(COMPOSE_DB) exec postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

#=====================================================
# --- Kafka ------------------------------------------
#=====================================================

up-kafka: ## Start Kafka + Zookeeper
	$(COMPOSE_KAFKA) up -d

down-kafka: ## Stop Kafka + Zookeeper
	$(COMPOSE_KAFKA) down --remove-orphans

sh-kafka: ## Connect to Kafka shell
	$(COMPOSE_KAFKA) exec kafka1 bash

#=====================================================
# --- full -------------------------------------------
#=====================================================

up: ## Start entire stack
	$(COMPOSE_ALL) up -d
	${MAKE} apply-pg-connector || echo "❌ Failed to apply PostgreSQL connector"

start: ## Start all containers
	$(COMPOSE_ALL) start

stop: ## Stop all containers
	$(COMPOSE_ALL) stop

build: ## Build images for full stack
	$(COMPOSE_ALL) build

logs: ## Show logs
	$(COMPOSE_ALL) logs -f

status: ## Show container status
	$(COMPOSE_ALL) ps

down: ## Stop + remove containers and volumes
	$(COMPOSE_ALL) down -v --remove-orphans

restart: ## Restart full stack
	$(MAKE) down
	$(MAKE) up

#=====================================================
# --- Debezium ---------------------------------------
#=====================================================

up-debezium: ## Start Debezium service
	$(COMPOSE) \
		-f $(DOCKER_DIR)/docker-compose.kafka.yml \
		-f $(DOCKER_DIR)/docker-compose.debezium.yml \
		up -d debezium debezium-ui

down-debezium: ## Stop Debezium service
	$(COMPOSE) \
		-f $(DOCKER_DIR)/docker-compose.debezium.yml \
		down --remove-orphans debezium debezium-ui

sh-debezium: ## Connect to Debezium shell
	$(COMPOSE_DBZ) exec debezium bash

apply-pg-connector: ## Apply PostgreSQL CDC connector
	curl -X POST http://localhost:8083/connectors \
		-H "Content-Type: application/json" \
		-d @data-platform/cdc/connectors/register-pg.json

check-connector: ## Check connector status
	@echo "📋 Checking connector status..."
	@curl -s http://localhost:8083/connectors/pg-connector-ecommerce/status | python -m json.tool || echo "❌ Connector not found or Debezium not running"

list-connectors: ## List all connectors
	@echo "📋 Listing all connectors..."
	@curl -s http://localhost:8083/connectors | python -m json.tool || echo "❌ Debezium not running"

delete-connector: ## Delete PostgreSQL connector
	@echo "🗑️ Deleting connector..."
	@curl -X DELETE http://localhost:8083/connectors/pg-connector-ecommerce || echo "❌ Failed to delete connector"

restart-connector: ## Restart PostgreSQL connector
	@echo "🔄 Restarting connector..."
	@curl -X POST http://localhost:8083/connectors/pg-connector-ecommerce/restart || echo "❌ Failed to restart connector"

#=====================================================
# --- Python Environment ----------------------------
#=====================================================

setup-venv: ## Setup Python virtual environment
	./setup_venv.sh

activate-venv: ## Show activation command
	@echo "Run: source venv/bin/activate"

clean-venv: ## Remove virtual environment
	rm -rf venv

check-venv: ## Check if virtual environment is active
	@if [ -z "$$VIRTUAL_ENV" ]; then \
		echo "❌ Virtual environment is not active"; \
		echo "💡 Run: source venv/bin/activate"; \
		exit 1; \
	else \
		echo "✅ Virtual environment is active: $$VIRTUAL_ENV"; \
	fi

install-deps: check-venv ## Install Python dependencies (requires active venv)
	pip install -r requirements.txt

install-system-pip: ## Install pip system-wide (Ubuntu/Debian)
	sudo apt update && sudo apt install python3-pip -y

setup-python: ## Setup complete Python environment (system pip + venv + deps)
	@echo "🐍 Setting up complete Python environment..."
	@if ! command -v pip3 >/dev/null 2>&1; then \
		echo "📦 Installing pip..."; \
		sudo apt update && sudo apt install python3-pip -y; \
	fi
	@echo "📁 Setting up virtual environment..."
	$(MAKE) setup-venv
	@echo "✅ Python environment ready!"
	@echo "💡 To activate: source venv/bin/activate"

freeze-deps: ## Freeze current dependencies
	pip freeze > requirements.txt

#=====================================================
# --- Testing UI -------------------------------------
#=====================================================

run-ui-local: ## Start CDC Testing UI locally (requires active venv)
	cd application/cdc-testing-ui && streamlit run app.py --server.port 8501

check-ui-deps: ## Check if UI dependencies are installed
	python -c "import streamlit, psycopg2, kafka, pandas, plotly; print('✅ All dependencies installed')"

up-ui: ## Start CDC Testing UI as Docker service
	$(COMPOSE) \
		-f $(DOCKER_DIR)/docker-compose.db.yml \
		-f $(DOCKER_DIR)/docker-compose.kafka.yml \
		-f $(DOCKER_DIR)/docker-compose.ui.yml \
		up -d cdc-testing-ui

down-ui: ## Stop CDC Testing UI Docker service
	$(COMPOSE) \
		-f $(DOCKER_DIR)/docker-compose.db.yml \
		-f $(DOCKER_DIR)/docker-compose.kafka.yml \
		-f $(DOCKER_DIR)/docker-compose.ui.yml \
	down cdc-testing-ui --remove-orphans

build-ui: ## Build CDC Testing UI Docker image
	$(COMPOSE) \
		-f $(DOCKER_DIR)/docker-compose.db.yml \
		-f $(DOCKER_DIR)/docker-compose.kafka.yml \
		-f $(DOCKER_DIR)/docker-compose.ui.yml \
	build  cdc-testing-ui


logs-ui: ## Show CDC Testing UI logs
	$(COMPOSE_UI) logs -f

demo-data: ## Generate demo data for CDC testing (requires active venv)
	cd application/cdc-testing-ui && python demo_data.py

quick-start: ## Quick start for development (up + connector + demo data + ui)
	@echo "🚀 Starting CDC development environment..."
	$(MAKE) up
	@echo "⏳ Waiting for services to be ready..."
	@sleep 15
	@echo "🔌 Applying PostgreSQL connector..."
	$(MAKE) apply-pg-connector
	@echo "⏳ Waiting for connector to be ready..."
	@sleep 5
	@echo "📊 Checking connector status..."
	$(MAKE) check-connector
	@echo "🎲 Generating demo data..."
	$(MAKE) demo-data
	@echo "✅ Setup completed!"
	@echo "🌐 Access the UI at: http://localhost:8501"
	@echo "🔧 Debezium UI: http://localhost:8085"
	@echo "📡 Kafka Console: http://localhost:8080"
	@echo "📊 Grafana Dashboard: http://localhost:3000 (admin/admin123)"
	@echo "🗄️  ClickHouse: http://localhost:8123"

#=====================================================
# --- Spark ------------------------------------------
#=====================================================

up-spark: ## Start Spark + Jupyter service
	$(COMPOSE_SPARK) up -d

down-spark: ## Stop Spark + Jupyter service
	$(COMPOSE_SPARK) down --remove-orphans

logs-spark: ## Show Spark + Jupyter logs
	$(COMPOSE_SPARK) logs -f

status-spark: ## Show Spark + Jupyter container status
	$(COMPOSE_SPARK) ps

sh-spark: ## Connect to Spark + Jupyter container shell
	$(COMPOSE_SPARK) exec ed-pyspark-jupyter bash

restart-spark: ## Restart Spark + Jupyter service
	$(MAKE) down-spark
	$(MAKE) up-spark

spark-shell: ## Start Spark shell in container
	$(COMPOSE_SPARK) exec ed-pyspark-jupyter spark-shell

pyspark-shell: ## Start PySpark shell in container
	$(COMPOSE_SPARK) exec ed-pyspark-jupyter pyspark

spark-submit: ## Submit a Spark application (use: make spark-submit APP=your-app.py)
	$(COMPOSE_SPARK) exec ed-pyspark-jupyter spark-submit /home/jupyter/src-streaming/$(APP)

jupyter-token: ## Get Jupyter notebook access info
	@echo "🔗 Jupyter Lab URL: http://localhost:8888"
	@echo "🔗 Spark UI URL: http://localhost:4040"
	@echo "💡 Default setup should not require token"
	$(COMPOSE_SPARK) exec ed-pyspark-jupyter jupyter lab list 2>/dev/null || echo "ℹ️  Container may not be running"

#=====================================================
# --- Analytics (ClickHouse + Grafana) --------------
#=====================================================

up-analytics: ## Start ClickHouse + Grafana services
	$(COMPOSE_ANALYTICS) up -d

down-analytics: ## Stop ClickHouse + Grafana services
	$(COMPOSE_ANALYTICS) down --remove-orphans

logs-analytics: ## Show ClickHouse + Grafana logs
	$(COMPOSE_ANALYTICS) logs -f

status-analytics: ## Show ClickHouse + Grafana status
	$(COMPOSE_ANALYTICS) ps

restart-analytics: ## Restart ClickHouse + Grafana services
	$(MAKE) down-analytics
	$(MAKE) up-analytics

clickhouse-client: ## Connect to ClickHouse client
	$(COMPOSE_ANALYTICS) exec clickhouse clickhouse-client

grafana-url: ## Show Grafana access info
	@echo "🔗 Grafana URL: http://localhost:3000"
	@echo "👤 Username: admin"
	@echo "🔑 Password: admin123"
	@echo "🗄️  ClickHouse: http://clickhouse:8123"

analytics-info: ## Show all analytics service URLs
	@echo "📊 Analytics Services:"
	@echo "🔗 Grafana Dashboard: http://localhost:3000 (admin/admin123)"
	@echo "🗄️  ClickHouse HTTP: http://localhost:8123"
	@echo "⚡ ClickHouse Native: localhost:9000"

#=====================================================
# --- CDC Spark Jobs ---------------------------------
#=====================================================

cdc-run: ## Run CDC customers job (simple command)
	@./scripts/run_cdc.sh
