COMPOSE_BASE = docker compose -f docker-compose.yml -f docker-compose.core.yml
COMPOSE_FULL = $(COMPOSE_BASE) -f docker-compose.apps.yml -f docker-compose.workers.yml
COMPOSE_DEV  = $(COMPOSE_FULL) -f docker-compose.override.yml

up:
	$(COMPOSE_DEV) up -d

build:
	$(COMPOSE_DEV) up -d --build

dev:
	$(COMPOSE_DEV) up -d

down:
	$(COMPOSE_DEV) down

logs:
	$(COMPOSE_DEV) logs -f

core:
	$(COMPOSE_BASE) up -d