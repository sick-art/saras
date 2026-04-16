# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run Commands

The app runs via Docker Compose. Use `docker compose exec` for all runtime operations (logs, migrations, debugging).

```bash
docker compose up
```

Services: Postgres 16 (:5432), Redis 7 (:6379), Backend (:8000), Frontend (:3000 prod / :5173 dev).

### Common Docker Operations

```bash
docker compose logs -f backend                    # Tail backend logs
docker compose logs -f frontend                   # Tail frontend logs
docker compose exec backend alembic upgrade head  # Run migrations
docker compose exec backend alembic revision --autogenerate -m "description"  # Create migration
docker compose exec db psql -U saras saras        # Postgres shell
docker compose exec redis redis-cli               # Redis shell
```

### Tests & Linting (run locally via uv)

```bash
cd backend
uv run pytest tests/unit/ -v                                        # Run unit tests
uv run pytest tests/unit/core/test_executor.py::test_name -v        # Single test
uv run ruff check saras/                                            # Lint
uv run ruff format saras/                                           # Format
uv run mypy saras/                                                  # Type check (strict mode)
```

Coverage target is 70% (enforced in pyproject.toml addopts). Unit tests mock LLM calls via `litellm.acompletion` patches.

### Frontend (when running outside Docker)

```bash
cd frontend
npm install
npm run dev                            # Vite dev server on :5173
npm run build                          # Production build
npm run typecheck                      # tsc --noEmit
npm run lint                           # eslint
npm run format                         # prettier
```

## Architecture

Saras is a self-hosted agent building platform covering Build → Simulate → Observe → Evaluate.

### Agent Definition Flow (YAML-first)

YAML is the single source of truth for agent definitions. It flows through:

1. **YAML string** → stored in `Agent.yaml_content` (Postgres)
2. **Compiler** (`core/compiler.py`) → `CompiledAgent` with base system prompt, tool defs, routing context
3. **Executor** (`core/executor.py`) → `run_turn()` processes one user message through router → slot fill → primary LLM → tool loop
4. **Context Layers** (8 total): Layer 1 always injected (persona/tone/rules); Layers 2-6 injected per router decision; Layers 7-8 injected at runtime (tool results, memory)

Schema types: `core/schema.py` (Python) ↔ `types/agent.ts` (TypeScript) — these must stay in sync.

### Real-time Communication

- **Simulator**: WebSocket at `/api/projects/{id}/agents/{id}/simulate`. Executor emits span events to Redis pub/sub; a background subscriber relays them to the WebSocket client.
- **Builder Chat**: SSE stream at `/api/projects/{id}/agents/{id}/builder/chat`. Returns delta text chunks and YAML diffs that the frontend applies live.

### State Management

Frontend uses Zustand (`stores/agent.store.ts`). `yamlContent` is the source of truth; `parsedSchema` is derived. The builder has four views (chat, form, graph, yaml) all reading/writing the same YAML state.

### Data Storage

- **PostgreSQL**: All CRUD (projects, agents, versions, runs, spans, datasets, evals)
- **DuckDB**: Analytics aggregations (cost over time, latency percentiles, model usage). Synced from Postgres via `tracing/collector.py`
- **Redis**: Real-time span fan-out during simulation, pub/sub channels per run

### Test Infrastructure

- **testcontainers** for session-scoped Postgres + Redis (integration/e2e tests)
- **pytest-asyncio** with `asyncio_mode = "auto"`
- Per-test DB rollback via SQLAlchemy savepoints
- Factory helpers in `tests/factories.py` (plain async functions, not factory_boy)
- LLM mocking: patches `litellm.acompletion` with canned responses from `tests/fixtures/llm_responses/`
- Known caveat: `main.py` lifespan has a NameError on `engine.dispose()` at shutdown — tests replace the lifespan with a no-op

### API Route Structure

All routes prefixed `/api/`. Key patterns:
- REST CRUD: `/projects/{id}/agents`, `/projects/{id}/datasets`, `/projects/{id}/evals/suites`
- Streaming: `/builder/chat` (SSE), `/simulate` (WebSocket)
- Analytics: `/projects/{id}/analytics` (DuckDB queries)
- Samples: `/samples` (pre-made agents), `/clone-sample`

### Agent Schema Design Rules

- No IDs or underscores in user-facing YAML — use human-readable `name:` fields
- All conditions, triggers, handoffs are plain English evaluated by the router LLM at runtime
- Tools defined once at agent level with full config (including `on_failure`, `on_empty_result`)
- Goals reference tools by name (string match)
- Sequence steps use natural language with embedded `@tool: Tool Name` references

## Frontend UI

The frontend uses shadcn with the **Mira theme** and **Base UI** components. When adding or modifying UI components, use the `/shadcn` and `/frontend-design` skills to add components and ensure they follow the installed theme. Do not manually create shadcn components — always use the skill so the theme and Base UI style are respected.

Use frontend-design skill to follow good frontend design principles before writing/implementing UI features.
## Code Style

- Backend: ruff (line-length 100, py311), mypy strict, pre-commit hooks configured
- Frontend: ESLint + Prettier, TypeScript strict, shadcn Mira theme with Base UI components
- Git commits: no `Co-Authored-By:` trailers
