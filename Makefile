# Bahi — all local workflows go through make.
# Profile swap: make run PROFILE=sarvam   (sources envs/sarvam.env)

VENV := server/.venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
PROFILE ?= offline

.PHONY: setup run test lint typecheck check clean

setup: ## create venv + install server in editable mode with dev deps
	python3.12 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e "server[dev]"

run: ## start the FastAPI dev server with the selected PROFILE
	set -a; . envs/$(PROFILE).env; set +a; \
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

clean:
	rm -rf $(VENV) server/.mypy_cache server/.ruff_cache server/.pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
