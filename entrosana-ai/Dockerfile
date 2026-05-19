FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Build dependencies for psycopg2/asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Copy source first — hatchling needs the `app/` package present to resolve
# `[tool.hatch.build.targets.wheel] packages = ["app"]` at install time.
COPY pyproject.toml README.md ./
COPY app/ ./app/
COPY alembic.ini ./
COPY migrations/ ./migrations/

# Install the package + its runtime deps (one layer; cache is invalidated when
# either pyproject.toml or app/ changes — acceptable for a small monolith).
RUN pip install -e .

# Non-root user
RUN useradd --create-home --uid 1000 entrosana && chown -R entrosana:entrosana /app
USER entrosana

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
