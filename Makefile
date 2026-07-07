# Bahi — all local workflows go through make.
# Profile swap: make run PROFILE=sarvam   (sources envs/sarvam.env)

VENV := server/.venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
PROFILE ?= offline
# source secrets (.env, gitignored) then the selected provider profile
LOAD_ENV = set -a; [ -f .env ] && . ./.env; . envs/$(PROFILE).env; set +a

.PHONY: setup run test lint typecheck check clean

setup: ## create venv + install server in editable mode with dev deps
	python3.12 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e "server[dev]"

run: ## start the FastAPI dev server with the selected PROFILE
	$(LOAD_ENV); \
	cd server && .venv/bin/uvicorn bahi.api.app:app --reload --port 8000

test: ## run the test suite
	cd server && .venv/bin/pytest

test-one: ## run a single test: make test-one T=tests/unit/test_config.py::test_name
	cd server && .venv/bin/pytest $(T)

lint:
	cd server && .venv/bin/ruff check src tests

format:
	cd server && .venv/bin/ruff check --fix src tests && .venv/bin/ruff format src tests

typecheck:
	cd server && .venv/bin/mypy

check: lint typecheck test ## the phase-gate trio

probe-tts: ## live TTS probe: make probe-tts PROFILE=sarvam TEXT="..." [OUT=probe_out.wav]
	$(LOAD_ENV); \
	cd server && .venv/bin/python -m bahi.probes tts "$(TEXT)" "$(or $(OUT),probe_out.wav)"

probe-stt: ## live STT probe: make probe-stt PROFILE=sarvam FILE=probe_out.wav
	$(LOAD_ENV); \
	cd server && .venv/bin/python -m bahi.probes stt "$(FILE)"

probe-llm: ## live LLM probe: make probe-llm PROFILE=sarvam TEXT="..." [ROLE=orchestrator]
	$(LOAD_ENV); \
	cd server && .venv/bin/python -m bahi.probes llm "$(TEXT)" --role "$(or $(ROLE),orchestrator)"

mcp: ## run the ledger as a standalone stdio MCP server
	cd server && .venv/bin/python -m bahi.mcp_server

migrate: ## apply alembic migrations to DATABASE_URL
	cd server && .venv/bin/alembic upgrade head

clean:
	rm -rf $(VENV) server/.mypy_cache server/.ruff_cache server/.pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
