import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from saras.config import get_settings
from saras.db.redis import close as redis_close
from saras.db.duckdb import close as duckdb_close, get_duckdb
from saras.api import health, projects, agents, builder, simulator, samples, traces, datasets, evals

# ── Logging ───────────────────────────────────────────────────────────────────

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
)
log = structlog.get_logger()


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    log.info("saras.startup", environment=settings.environment)

    # Bootstrap DuckDB analytics tables
    get_duckdb()

    yield

    await redis_close()
    duckdb_close()
    await engine.dispose()
    log.info("saras.shutdown")


# ── App ───────────────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Saras API",
        description="E2E Agent Building Platform",
        version="0.1.0",
        docs_url="/docs" if settings.environment == "development" else None,
        redoc_url="/redoc" if settings.environment == "development" else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(health.router, prefix="/api")
    app.include_router(projects.router, prefix="/api")
    app.include_router(agents.router, prefix="/api")
    app.include_router(builder.router, prefix="/api")
    app.include_router(simulator.router, prefix="/api")
    app.include_router(samples.router, prefix="/api")
    app.include_router(traces.router, prefix="/api")
    app.include_router(datasets.router, prefix="/api")
    app.include_router(evals.router, prefix="/api")

    return app


app = create_app()
