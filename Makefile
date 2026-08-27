.PHONY: install start test doctor lint format clean mcp

VENV_PYTHON := $(shell pwd)/.venv/bin/python3
VENV_PIP := $(shell pwd)/.venv/bin/pip
BRIDGE_CLI := $(shell pwd)/.venv/bin/bridge-cli

install:
	$(VENV_PIP) install -e ".[dev,mcp]"

start:
	$(VENV_PYTHON) -m local_ai_gateway.main serve

doctor:
	$(VENV_PYTHON) -m local_ai_gateway.main doctor

test:
	$(VENV_PYTHON) -m pytest tests/ -v

lint:
	$(VENV_PYTHON) -m ruff check .

format:
	$(VENV_PYTHON) -m ruff format .

mcp:
	$(VENV_PYTHON) -m local_ai_gateway.main mcp

cli:
	$(BRIDGE_CLI) --list-tools

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .ruff_cache build dist *.egg-info
