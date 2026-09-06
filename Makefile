.PHONY: test lint format check run docker-run docs benchmark

# Install dependencies for development
install:
	pip install -e ".[dev]"
	pip install pydantic-settings aiosqlite uvicorn

# Run tests with coverage
test:
	pytest tests/ -v --cov=core --cov=memory --cov=vision --cov=api --cov-fail-under=39

# Lint codebase (Type checking and fast linting)
lint:
	ruff check .
	mypy core/ memory/ vision/ api.py

# Auto-format codebase
format:
	ruff format .
	black .

# Run both linting and testing
check: lint test

# Run the API locally
run:
	uvicorn api:app --host 127.0.0.1 --port 8000 --reload

# Start everything via Docker
docker-run:
	docker-compose up --build

# Run deterministic benchmark suite (if tests exist in benchmarks folder)
benchmark:
	pytest benchmarks/ -v --asyncio-mode=auto
