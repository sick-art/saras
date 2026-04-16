# Self-Hosting

Saras runs entirely in Docker Compose — no SaaS dependencies, no proprietary cloud services. Bring your own LLM provider keys.

---

## Prerequisites

- **Docker Engine 24+** with **Docker Compose v2**
- **4 GB RAM** minimum (8 GB recommended)
- At least one **LLM provider key** — Anthropic, OpenAI, or Google

---

## Quickstart

**1. Clone the repo**

```bash
git clone https://github.com/sick-art/saras.git
cd saras
```

**2. Configure environment**

```bash
cp .env.example .env
```

Edit `.env` and provide at least one provider key:

```env
# ── LLM Providers (at least one required) ─────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...

# ── Saras API ─────────────────────────────────────────────────────────────
SARAS_API_KEY=change-me-in-production
CORS_ORIGINS=http://localhost:3000

# ── Environment ───────────────────────────────────────────────────────────
ENVIRONMENT=development
LOG_LEVEL=INFO
```

The `.env` is also consumed by the backend container via `env_file:` in [docker-compose.yml](../docker-compose.yml). Database and Redis URLs are wired automatically inside the compose network.

**3. Start everything**

```bash
docker compose up -d
```

| Service | Port | Notes |
|---------|------|-------|
| `frontend` | 3000 | React UI, prod build served from a slim image |
| `backend` | 8000 | FastAPI app (`/api/...`, `/docs` in dev) |
| `postgres` | 5432 | Postgres 16 alpine, healthcheck enabled |
| `redis` | 6379 | Redis 7 alpine with AOF persistence |

The backend mounts a named volume at `/data` for the embedded DuckDB analytics file (`DUCKDB_PATH=/data/analytics.duckdb`).

**4. Run migrations**

```bash
docker compose exec backend alembic upgrade head
```

**5. Open the UI**

[http://localhost:3000](http://localhost:3000)

---

## Common Operations

```bash
# Logs
docker compose logs -f backend
docker compose logs -f frontend

# Migrations
docker compose exec backend alembic upgrade head
docker compose exec backend alembic revision --autogenerate -m "description"

# Postgres shell
docker compose exec postgres psql -U saras saras

# Redis shell
docker compose exec redis redis-cli
```

For local backend development outside the container (e.g. running tests, linting):

```bash
cd backend
uv run pytest tests/unit/ -v
uv run ruff check saras/
uv run mypy saras/
```

For frontend development outside the container:

```bash
cd frontend
npm install
npm run dev          # Vite dev server on :5173
npm run typecheck
npm run lint
```

---

## Production Deployment

The same `docker-compose.yml` works for production. Recommended hardening:

- Put a reverse proxy (Caddy, nginx, Cloudflare Tunnel) in front of the frontend container; terminate TLS there.
- Expose only the proxy publicly. Postgres and Redis should stay on the compose network.
- Set `ENVIRONMENT=production` to disable `/docs` and `/redoc`.
- Rotate `SARAS_API_KEY`.
- Replace the Postgres credentials in `docker-compose.yml` (default `saras:saras`) with strong values, or move them into the env file and reference them.
- Take regular backups of the `postgres_data` volume.

---

## Updating

```bash
git pull
docker compose pull
docker compose up -d --build
docker compose exec backend alembic upgrade head
```

---

## Data

All persistent data lives in named Docker volumes:

| Volume | Contents |
|--------|----------|
| `postgres_data` | Projects, agents, runs, spans, datasets, evals — the canonical store |
| `redis_data` | Redis AOF persistence (recoverable session state) |
| `saras_data` | Embedded DuckDB analytics file (`/data/analytics.duckdb`) |

`postgres_data` is the only one you must back up; the others can be regenerated.
