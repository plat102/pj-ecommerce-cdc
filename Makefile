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
COMPOSE_GOVERNANCE := $(COMPOSE) -f $(DOCKER_DIR)/docker-compose.governance.yml
COMPOSE_OBS := $(COMPOSE) -f $(DOCKER_DIR)/docker-compose.observability.yml
COMPOSE_GX_DOCS := $(COMPOSE) -f $(DOCKER_DIR)/docker-compose.gx-docs.yml

COMPOSE_ALL := $(COMPOSE) \
	-f $(DOCKER_DIR)/docker-compose.db.yml \
	-f $(DOCKER_DIR)/docker-compose.kafka.yml \
	-f $(DOCKER_DIR)/docker-compose.debezium.yml \
	-f $(DOCKER_DIR)/docker-compose.ui.yml \
	-f $(DOCKER_DIR)/docker-compose.spark.yml \
	-f $(DOCKER_DIR)/docker-compose.analytics.yml \
	-f $(DOCKER_DIR)/docker-compose.observability.yml

include $(ENV_FILE)
export $(shell sed 's/=.*//' $(ENV_FILE))

.PHONY: help build up down logs status clean restart \
        up-db down-db up-kafka down-kafka sh-pg \
        up-spark down-spark logs-spark status-spark sh-spark-master \
        restart-spark spark-shell pyspark-shell spark-submit jupyter-token \
        up-analytics down-analytics logs-analytics grafana-url clickhouse-client \
        up-gx-docs down-gx-docs logs-gx-docs sh-gx-docs \
        migrate-governance \
        ingest-pg ingest-kafka ingest-clickhouse ingest-all ingest-status

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
	${MAKE} apply-dlq-topics || echo "❌ Failed to apply DLQ topic retention"
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

apply-dlq-topics: ## Pre-create DLQ topics with explicit retention (idempotent)
	@./scripts/setup_dlq_topics.sh

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
# --- Python Environment (uv) ------------------------
#=====================================================

uv-sync: ## Create/update .venv from pyproject.toml + uv.lock (main + dev groups)
	uv sync --group dev

uv-shell: ## Show activation command for the uv-managed venv
	@echo "Run: . .venv/bin/activate"
	@echo "Or prefix commands with: uv run <cmd>"

uv-clean: ## Remove .venv and uv.lock (also purge legacy venv/ if present)
	rm -rf .venv uv.lock venv

test: ## Run pytest inside the uv-managed venv (exit 5 "no tests" treated as pass)
	@uv run pytest; status=$$?; if [ $$status -eq 5 ]; then exit 0; else exit $$status; fi

#=====================================================
# --- Testing UI -------------------------------------
#=====================================================

run-ui-local: ## Start CDC Testing UI locally via uv (no manual activation needed)
	cd application/cdc-testing-ui && uv run streamlit run app.py --server.port 8501

check-ui-deps: ## Check if UI dependencies are installed (uses .venv)
	uv run python -c "import streamlit, psycopg2, kafka, pandas, plotly; print('All dependencies installed')"

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

demo-data: ## Generate demo data for CDC testing via uv (no manual activation needed)
	cd application/cdc-testing-ui && uv run python demo_data.py

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

#=====================================================
# --- Governance Catalog (OpenMetadata) --------------
#=====================================================

up-governance: ## Start OpenMetadata + MySQL + Elasticsearch (heavy ~4GB RAM). Run `migrate-governance` once on first boot.
	$(COMPOSE_GOVERNANCE) up -d

migrate-governance: ## Bootstrap OpenMetadata schema in MySQL (run once, or after OPENMETADATA_VERSION bump)
	docker run --rm --network ecommerce-network \
	  -e DB_DRIVER_CLASS=com.mysql.cj.jdbc.Driver \
	  -e DB_SCHEME=mysql -e DB_USE_SSL=false \
	  -e DB_HOST=openmetadata-mysql -e DB_PORT=3306 \
	  -e DB_USER=openmetadata_user -e DB_USER_PASSWORD=openmetadata_password \
	  -e OM_DATABASE=openmetadata_db \
	  -e ELASTICSEARCH_HOST=openmetadata-elasticsearch -e ELASTICSEARCH_PORT=9200 -e ELASTICSEARCH_SCHEME=http \
	  -e SERVER_PORT=8585 -e SERVER_ADMIN_PORT=8586 \
	  docker.getcollate.io/openmetadata/server:$(or $(OPENMETADATA_VERSION),1.5.9) \
	  ./bootstrap/openmetadata-ops.sh migrate
	docker restart openmetadata-server

down-governance: ## Stop OpenMetadata stack
	$(COMPOSE_GOVERNANCE) down --remove-orphans

logs-governance: ## Show OpenMetadata logs
	$(COMPOSE_GOVERNANCE) logs -f

status-governance: ## Show OpenMetadata stack status
	$(COMPOSE_GOVERNANCE) ps

INGESTION_IMAGE := docker.getcollate.io/openmetadata/ingestion:$(or $(OPENMETADATA_VERSION),1.5.9)
INGESTION_YAML_DIR := $(PWD)/data-platform/governance/openmetadata/ingestion
# The ingestion image's default entrypoint is `airflow`; override it so we can invoke
# the `metadata` CLI directly for one-shot workflows.
INGESTION_DOCKER_RUN = docker run --rm --network ecommerce-network \
	--entrypoint metadata \
	-v $(INGESTION_YAML_DIR):/ingestion:ro \
	-e OM_INGESTION_JWT=$(OM_INGESTION_JWT) \
	-e CLICKHOUSE_PASSWORD=$(CLICKHOUSE_PASSWORD) \
	$(INGESTION_IMAGE)

ingest-pg: ## Ingest PostgreSQL metadata into OpenMetadata catalog
	@if [ -z "$(OM_INGESTION_JWT)" ]; then echo "OM_INGESTION_JWT is not set. See docs/governance.md for how to obtain a bot JWT."; exit 1; fi
	$(INGESTION_DOCKER_RUN) ingest -c /ingestion/postgres.yaml

ingest-kafka: ## Ingest Kafka topics + Apicurio schemas into OpenMetadata catalog
	@if [ -z "$(OM_INGESTION_JWT)" ]; then echo "OM_INGESTION_JWT is not set. See docs/governance.md for how to obtain a bot JWT."; exit 1; fi
	$(INGESTION_DOCKER_RUN) ingest -c /ingestion/kafka.yaml

ingest-clickhouse: ## Ingest ClickHouse metadata into OpenMetadata catalog
	@if [ -z "$(OM_INGESTION_JWT)" ]; then echo "OM_INGESTION_JWT is not set. See docs/governance.md for how to obtain a bot JWT."; exit 1; fi
	$(INGESTION_DOCKER_RUN) ingest -c /ingestion/clickhouse.yaml

ingest-all: ## Run all three ingestions sequentially (fail-fast). Requires OM_INGESTION_JWT.
	$(MAKE) ingest-pg
	$(MAKE) ingest-kafka
	$(MAKE) ingest-clickhouse

ingest-status: ## Show OpenMetadata service counts (database / messaging / pipeline). Requires OM_INGESTION_JWT.
	@if [ -z "$(OM_INGESTION_JWT)" ]; then echo "OM_INGESTION_JWT is not set. See docs/governance.md for how to obtain a bot JWT."; exit 1; fi
	@echo "OpenMetadata catalog service counts:"
	@for kind in databaseServices messagingServices pipelineServices; do \
	  printf "  %-18s: " "$$kind"; \
	  body=$$(curl -s -H "Authorization: Bearer $(OM_INGESTION_JWT)" "http://localhost:8585/api/v1/services/$$kind?limit=100"); \
	  if [ -z "$$body" ]; then echo "OM unreachable at http://localhost:8585"; exit 1; fi; \
	  echo "$$body" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('data', []))) if 'data' in d else print('AUTH FAILED (' + d.get('message', 'unknown') + ')')"; \
	done

#=====================================================
# --- GX Data Docs (nginx sidecar) -------------------
#=====================================================

up-gx-docs: ## Start GX Data Docs static site at http://localhost:8890
	@mkdir -p data-platform/governance/gx-runtime/uncommitted/data_docs/local_site
	$(COMPOSE_GX_DOCS) up -d

down-gx-docs: ## Stop GX Data Docs static site
	$(COMPOSE_GX_DOCS) down --remove-orphans

logs-gx-docs: ## Show GX Data Docs nginx logs
	$(COMPOSE_GX_DOCS) logs -f

sh-gx-docs: ## Open a shell in the GX Data Docs nginx container
	$(COMPOSE_GX_DOCS) exec gx-data-docs-server sh

#=====================================================
# --- Observability (Loki + Prometheus + Alloy) ------
#=====================================================

up-observability: ## Start observability stack (loki + alloy + prometheus + cadvisor + node-exporter)
	$(COMPOSE_OBS) up -d

down-observability: ## Stop observability stack
	$(COMPOSE_OBS) down --remove-orphans

logs-observability: ## Tail observability stack logs
	$(COMPOSE_OBS) logs -f

status-observability: ## Show observability stack status
	$(COMPOSE_OBS) ps

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

cdc-run: ## Run CDC customers job (debug mode - console output)
	@./scripts/run_cdc.sh --debug

cdc-run-prod: ## Run CDC customers job (production mode - to ClickHouse)
	@./scripts/run_cdc.sh

cdc-run-products: ## Run CDC products job (debug mode - console output)
	@./scripts/run_cdc.sh --job-type products --debug

cdc-run-products-prod: ## Run CDC products job (production mode - to ClickHouse)
	@./scripts/run_cdc.sh --job-type products

cdc-run-orders: ## Run CDC orders job (debug mode - console output)
	@./scripts/run_cdc.sh --job-type orders --debug

cdc-run-orders-prod: ## Run CDC orders job (production mode - to ClickHouse)
	@./scripts/run_cdc.sh --job-type orders

cdc-run-all: ## Run all CDC jobs (customers, products, orders) in debug mode
	@echo "🚀 Running all CDC jobs in background..."
	@./scripts/run_cdc.sh --job-type customers --debug &
	@echo "⏳ Waiting 5 seconds before starting products job..."
	@sleep 5
	@./scripts/run_cdc.sh --job-type products --debug &
	@echo "⏳ Waiting 5 seconds before starting orders job..."
	@sleep 5
	@./scripts/run_cdc.sh --job-type orders --debug &
	@echo "✅ All jobs started! Use 'docker logs -f ed-pyspark-jupyter' to see output"
	@echo "🛑 To stop: docker exec ed-pyspark-jupyter pkill -f 'spark-submit'"

cdc-run-all-prod: ## Run all CDC jobs (customers, products, orders) in production mode
	@echo "🚀 Running all CDC jobs in production mode..."
	@./scripts/run_cdc.sh --job-type customers &
	@echo "⏳ Waiting 5 seconds before starting products job..."
	@sleep 5
	@./scripts/run_cdc.sh --job-type products &
	@echo "⏳ Waiting 5 seconds before starting orders job..."
	@sleep 5
	@./scripts/run_cdc.sh --job-type orders &
	@echo "✅ All jobs started in production mode!"
	@echo "🛑 To stop: docker exec ed-pyspark-jupyter pkill -f 'spark-submit'"

cdc-stop: ## Stop all CDC jobs
	@echo "🛑 Stopping all CDC jobs..."
	@docker exec ed-pyspark-jupyter pkill -f 'spark-submit' || echo "ℹ️  No spark-submit processes"
	@docker exec ed-pyspark-jupyter pkill -f 'pyspark' || echo "ℹ️  No pyspark processes"
	@docker exec ed-pyspark-jupyter pkill -f 'java.*spark' || echo "ℹ️  No Java Spark processes"
	@echo "✅ All CDC jobs stopped!"

cdc-force-stop: ## Force stop all CDC jobs and restart Spark container
	@echo "💀 Force stopping all CDC jobs..."
	@docker exec ed-pyspark-jupyter pkill -9 -f 'spark' || echo "ℹ️  No Spark processes"
	@echo "🔄 Restarting Spark container only..."
	@docker restart ed-pyspark-jupyter
	@echo "⏳ Waiting for container to be ready..."
	@sleep 5
	@echo "✅ All processes killed and Spark container restarted!"

cdc-status: ## Check CDC jobs status
	@echo "📊 Checking CDC jobs status..."
	@docker exec ed-pyspark-jupyter pgrep -f 'spark-submit' > /dev/null && echo "✅ spark-submit jobs are running" || echo "❌ No spark-submit jobs"
	@docker exec ed-pyspark-jupyter pgrep -f 'java.*spark' > /dev/null && echo "✅ Java Spark processes are running" || echo "❌ No Java Spark processes"
	@echo "📋 All Spark-related processes:"
	@docker exec ed-pyspark-jupyter pgrep -fl 'spark' || echo "   None"

CHECKPOINT_ROOT ?= /tmp/spark-checkpoints
cdc-rotate-checkpoint: ## Archive a CDC checkpoint (use: make cdc-rotate-checkpoint TABLE=customers_cdc)
	@if [ -z "$(TABLE)" ]; then echo "TABLE is required (e.g., make cdc-rotate-checkpoint TABLE=customers_cdc)"; exit 2; fi
	@docker exec ed-pyspark-jupyter sh -c '\
		src="$(CHECKPOINT_ROOT)/$(TABLE)"; \
		if [ ! -d "$$src" ]; then echo "no checkpoint at $$src"; exit 0; fi; \
		archive_dir="$(CHECKPOINT_ROOT)/_archived/$$(date +%Y%m%d-%H%M%S)"; \
		mkdir -p "$$archive_dir"; \
		mv "$$src" "$$archive_dir/$(TABLE)"; \
		mkdir -p "$$src"; \
		echo "moved $$src -> $$archive_dir/$(TABLE)"'

#=====================================================
# --- Dashboard Management --------------------------
#=====================================================

sync-dashboards: ## Sync Grafana dashboards from source to provisioning
	@./scripts/sync_dashboards.sh

reload-grafana: sync-dashboards ## Reload Grafana with updated dashboards
	@echo "🔄 Reloading Grafana with updated dashboards..."
	docker restart grafana
	@echo "✅ Grafana reloaded! Check dashboards at http://localhost:3000"


