# portfolio-tool — developer workflow.
# `make check` = format-check + lint + types + tests (the spec's acceptance gate).
.DEFAULT_GOAL := help
PY ?= python

.PHONY: help install fmt lint types test check run-mock clean

help:  ## Show this help.
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-12s %s\n", $$1, $$2}'

install:  ## Create venv deps (run inside an activated venv).
	$(PY) -m pip install -e ".[dev,dashboard]"

fmt:  ## Auto-format.
	ruff format app tests
	ruff check --fix app tests

lint:  ## Lint (no changes).
	ruff format --check app tests
	ruff check app tests

types:  ## Static type check.
	mypy app

test:  ## Run tests with coverage gate.
	pytest

check: lint types test  ## Full acceptance gate: format + lint + types + tests.

run-mock:  ## Generate all reports from fixtures (zero credentials).
	$(PY) -m app.cli run-all --mock

clean:  ## Remove caches and generated run outputs.
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	find reports/runs -mindepth 1 -maxdepth 1 -type d -exec rm -rf {} +
