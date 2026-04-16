# Self-Hosting

Saras runs entirely in Docker Compose — no cloud dependencies, no SaaS accounts required.

---

## Prerequisites

- Docker Engine 24+ and Docker Compose v2
- 4 GB RAM minimum (8 GB recommended for running local LLMs)
- An LLM API key (Anthropic, OpenAI, or Gemini) — or a local Ollama instance

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

Edit `.env` and set at minimum:

```env
# Required: at least one LLM provider key
ANTHROPIC_API_KEY=sk-ant-...
# or
OPENAI_API_KEY=sk-...

# Required: secret key for session signing
SECRET_KEY=change-me-to-a-random-string

# Optional: defaults shown
POSTGRES_DB=saras
POSTGRES_USER=saras
POSTGRES_PASSWORD=saras
REDIS_URL=redis://redis:6379/0
```

**3. Start all services**

```bash
docker compose up -d
```

This starts:

| Service | Port | Description |
|---------|------|-------------|
| `frontend` | 3000 | React UI (Nginx) |
| `backend` | 8000 | FastAPI backend |
| `postgres` | 5432 | PostgreSQL database |
| `redis` | 6379 | Redis pub/sub |

**4. Run migrations**

```bash
docker compose exec backend alembic upgrade head
```

**5. Open the UI**

Navigate to [http://localhost:3000](http://localhost:3000).

---

## Production Deployment

For production, swap the dev compose file with the production one and put a reverse proxy (nginx, Caddy, or Cloudflare Tunnel) in front:

```bash
docker compose -f docker-compose.yml up -d
```

Recommended setup:
- Reverse proxy handles TLS termination on port 443
- Frontend and backend exposed on the same domain (`/` and `/api/`)
- PostgreSQL and Redis not exposed publicly

---

## Updating

```bash
git pull
docker compose pull
docker compose up -d
docker compose exec backend alembic upgrade head
```

---

## Data

All data lives in Docker named volumes:

| Volume | Contents |
|--------|----------|
| `saras_postgres_data` | All agent definitions, runs, spans, evals |
| `saras_redis_data` | Redis persistence (optional) |

Back up `saras_postgres_data` regularly for production deployments.
