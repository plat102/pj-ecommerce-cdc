DOCKER_DIR := infrastructure/docker
ENV_FILE := $(DOCKER_DIR)/.env
PROJECT_NAME := ecommerce-cdc

COMPOSE = docker-compose -p $(PROJECT_NAME) --env-file $(ENV_FILE)

COMPOSE_DB := $(COMPOSE) -f $(DOCKER_DIR)/docker-compose.db.yml
COMPOSE_KAFKA := $(COMPOSE) -f $(DOCKER_DIR)/docker-compose.kafka.yml
COMPOSE_DBZ := $(COMPOSE) -f $(DOCKER_DIR)/docker-compose.debezium.yml
COMPOSE_UI := $(COMPOSE) -f $(DOCKER_DIR)/docker-compose.ui.yml
COMPOSE_SPARK := $(COMPOSE) -f $(DOCKER_DIR)/docker-compose.spark.yml

COMPOSE_ALL := $(COMPOSE) \
	-f $(DOCKER_DIR)/docker-compose.db.yml \
	-f $(DOCKER_DIR)/docker-compose.kafka.yml \
	-f $(DOCKER_DIR)/docker-compose.debezium.yml \
	-f $(DOCKER_DIR)/docker-compose.ui.yml \
	-f $(DOCKER_DIR)/docker-compose.spark.yml

include $(ENV_FILE)
export $(shell sed 's/=.*//' $(ENV_FILE))

.PHONY: help build up down logs status clean restart \
        up-db down-db up-kafka down-kafka sh-pg \
        up-spark down-spark logs-spark status-spark sh-spark-master \
        restart-spark spark-shell pyspark-shell spark-submit jupyter-token

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

install-deps: ## Install Python dependencies (requires active venv)
	pip install -r requirements.txt

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

#=====================================================
# --- Spark ------------------------------------------
#=====================================================

up-spark: ## Start Spark cluster
	$(COMPOSE_SPARK) up -d

down-spark: ## Stop Spark cluster
	$(COMPOSE_SPARK) down --remove-orphans

logs-spark: ## Show Spark logs
	$(COMPOSE_SPARK) logs -f

status-spark: ## Show Spark container status
	$(COMPOSE_SPARK) ps

sh-spark-master: ## Connect to Spark master shell
	$(COMPOSE_SPARK) exec spark-standalone bash

sh-spark-worker: ## Connect to Spark worker shell  
	$(COMPOSE_SPARK) exec spark-standalone bash

restart-spark: ## Restart Spark cluster
	$(MAKE) down-spark
	$(MAKE) up-spark

spark-shell: ## Start Spark shell
	$(COMPOSE_SPARK) exec spark-standalone spark-shell --master spark://spark-standalone:7077

pyspark-shell: ## Start PySpark shell
	$(COMPOSE_SPARK) exec spark-standalone pyspark --master spark://spark-standalone:7077

spark-submit: ## Submit a Spark application (use: make spark-submit APP=your-app.py)
	$(COMPOSE_SPARK) exec spark-standalone spark-submit --master spark://spark-standalone:7077 /opt/spark-apps/$(APP)

jupyter-token: ## Get Jupyter notebook token
	$(COMPOSE_SPARK) exec jupyter-spark jupyter lab list
