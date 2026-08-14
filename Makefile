.PHONY: install start test doctor lint format clean mcp

install:
	pip install -e ".[dev,mcp]"

start:
	python3 -m local_ai_gateway.main serve

doctor:
	python3 -m local_ai_gateway.main doctor

test:
	pytest tests/ -v

lint:
	ruff check .

format:
	ruff format .

mcp:
	python3 -m local_ai_gateway.main mcp

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .ruff_cache build dist *.egg-info
