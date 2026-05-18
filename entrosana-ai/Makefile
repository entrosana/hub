# entrosana-api developer commands

.PHONY: install run lint test fmt migrate dev-up dev-down build clean

install:
	uv sync || pip install -e ".[dev]"

run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker:
	celery -A app.tasks worker --loglevel=info

lint:
	ruff check app tests
	ruff format --check app tests
	mypy app

fmt:
	ruff format app tests
	ruff check --fix app tests

test:
	pytest -v --cov=app

migrate:
	alembic upgrade head

migration:
	alembic revision --autogenerate -m "$(MSG)"

dev-up:
	docker compose -f docker/dev-stack.yml up -d

dev-down:
	docker compose -f docker/dev-stack.yml down

build:
	docker build -t entrosana-api:dev .

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov dist build *.egg-info
