DOCKER_DIR := infrastructure/docker
ENV_FILE := $(DOCKER_DIR)/.env
PROJECT_NAME := ecommerce-cdc

COMPOSE = docker-compose -p $(PROJECT_NAME) --env-file $(ENV_FILE)

COMPOSE_DB := $(COMPOSE) -f $(DOCKER_DIR)/docker-compose.db.yml
COMPOSE_KAFKA := $(COMPOSE) -f $(DOCKER_DIR)/docker-compose.kafka.yml

COMPOSE_ALL := $(COMPOSE) \
	-f $(DOCKER_DIR)/docker-compose.db.yml \
	-f $(DOCKER_DIR)/docker-compose.kafka.yml 

include $(ENV_FILE)
export $(shell sed 's/=.*//' $(ENV_FILE))

.PHONY: help build up down logs status clean restart \
        up-db down-db up-kafka down-kafka sh-pg

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

#=====================================================
# --- full -------------------------------------------
#=====================================================

up: ## Start entire stack
	$(COMPOSE_ALL) up -d

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
