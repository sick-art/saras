# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

# Pull in the uv binary from the official image — no need to pip-install it.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# System deps (gcc for any wheels that need to build from source; libpq for psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Keep uv deterministic and use the system Python interpreter (no project venv)
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/usr/local

# Install dependencies first (cached separately from source). The cache mount
# persists uv's wheel/download cache across builds, so even when pyproject.toml
# changes only the touched packages are re-resolved — not re-downloaded.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Copy source and install the project itself
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Data dir for DuckDB
RUN mkdir -p /data

# Entrypoint: creates DB tables then starts uvicorn
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

CMD ["/app/entrypoint.sh"]
