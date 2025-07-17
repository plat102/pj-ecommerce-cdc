DOCKER_DIR=infrastructure/docker
DOCKER_COMPOSE_FILE=$(DOCKER_DIR)/docker-compose.yml
DOCKER_ENV_FILE=$(DOCKER_DIR)/.env
PROJECT_NAME=ecommerce-cdc
COMPOSE := docker-compose -p $(PROJECT_NAME) -f $(DOCKER_COMPOSE_FILE) --env-file $(DOCKER_ENV_FILE)

# Load all vars from .env into Make environment
include $(DOCKER_ENV_FILE)
export $(shell sed 's/=.*//' $(DOCKER_ENV_FILE))

.PHONY: help build up down logs status clean restart sh-pg

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build: ## Build the Docker images
	docker-compose -p $(PROJECT_NAME) -f $(DOCKER_COMPOSE_FILE) --env-file $(DOCKER_ENV_FILE) build

up: ## Start the Docker containers
	$(COMPOSE) up -d

down: ## Stop and remove the Docker containers
	$(COMPOSE) down

logs: ## View the logs of the Docker containers
	$(COMPOSE) logs -f

status: ## Show the status of the Docker containers
	docker-compose -p $(PROJECT_NAME) -f $(DOCKER_COMPOSE_FILE) --env-file $(DOCKER_ENV_FILE) ps

clean: ## Clean up containers and volumes for this project only`
	docker-compose -p $(PROJECT_NAME) -f $(DOCKER_COMPOSE_FILE) --env-file $(DOCKER_ENV_FILE) down -v

restart: down up

sh-pg: ## Connect to the PostgreSQL container shell
	$(COMPOSE) exec postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)