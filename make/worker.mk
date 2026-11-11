# conductor-worker: the stateless Python executor pool (Whisper, LLM,
# TTS, FFmpeg). See services/worker/ and docs/services/worker.md. Not a Go
# service, so it isn't picked up by make/v2.mk's build:v2/test:v2 loops
# and gets its own targets here, using uv for dependency management.

WORKER_PYTHONPATH := $(PWD)/contracts/gen/python:$(PWD)/services/worker/src

.PHONY: worker\:build worker\:test worker\:run \
	worker\:docker-build worker\:docker-up worker\:docker-down worker\:docker-logs

worker\:build: ## Install worker's dependencies with uv (also regenerates Python proto stubs)
	cd services/worker && uv sync --group dev
	$(MAKE) proto\:generate-python

worker\:test: ## Run worker's unit tests (fakes only, no live provider calls)
	$(MAKE) worker\:build
	cd services/worker && PYTHONPATH=$(WORKER_PYTHONPATH) uv run pytest tests

worker\:run: ## Run worker locally against dockerized infra (loads services/worker/.env itself)
	$(MAKE) worker\:build
	@test -f services/worker/.env || { cp services/worker/.env.example services/worker/.env; echo "Created services/worker/.env from .env.example"; }
	cd services/worker && set -a && . ./.env && set +a && \
		PYTHONPATH=$(WORKER_PYTHONPATH) uv run python src/main.py

worker\:docker-build: ## Build conductor-worker's Docker image
	docker build -f services/worker/worker.dockerfile -t media-notes/conductor-worker:local .

worker\:docker-up: ## Run conductor-worker inside docker-compose, alongside infra (requires infra:up)
	$(COMPOSE) up -d --build conductor-worker

worker\:docker-down: ## Stop conductor-worker's docker-compose container
	$(COMPOSE) rm -sf conductor-worker

worker\:docker-logs: ## Follow conductor-worker's docker-compose logs
	$(COMPOSE) logs -f conductor-worker
