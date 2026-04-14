"""
Shared pytest fixtures for the Saras backend test suite.

Fixture scopes:
  session  → containers (Postgres, Redis), engine, table setup
  function → DB session (rolled back after each test), HTTP client, LLM mock
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

# ── Fixture paths ─────────────────────────────────────────────────────────────

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Any:
    """Load a JSON fixture file relative to the fixtures/ directory."""
    with open(FIXTURES_DIR / name) as f:
        return json.load(f)


def load_yaml_fixture(name: str) -> str:
    """Load a YAML fixture file as a raw string."""
    return (FIXTURES_DIR / name).read_text()


# ── Mock LLM response helpers ─────────────────────────────────────────────────

def make_mock_llm_response(content: str = "Mock response", tool_calls=None) -> MagicMock:
    """
    Create a MagicMock that matches the structure LiteLLM returns.
    LLMResponse wraps raw.choices[0].message.content / .tool_calls etc.
    """
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_choice.message.tool_calls = tool_calls
    mock_choice.finish_reason = "stop"

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 100
    mock_usage.completion_tokens = 50

    mock_raw = MagicMock()
    mock_raw.choices = [mock_choice]
    mock_raw.usage = mock_usage
    return mock_raw


# ── Session-scoped containers ─────────────────────────────────────────────────

@pytest.fixture(scope="session")
def postgres_container():
    """Start a throwaway Postgres container for the entire test session."""
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture(scope="session")
def redis_container():
    """Start a throwaway Redis container for the entire test session."""
    with RedisContainer("redis:7-alpine") as r:
        yield r


@pytest.fixture(scope="session")
def postgres_url(postgres_container: PostgresContainer) -> str:
    """asyncpg-compatible connection URL from the test container."""
    url = postgres_container.get_connection_url()
    # testcontainers returns postgresql+psycopg2://… — we need asyncpg
    return url.replace("psycopg2", "asyncpg")


@pytest.fixture(scope="session")
def redis_url(redis_container: RedisContainer) -> str:
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    return f"redis://{host}:{port}"


# ── Session-scoped engine (tables created once) ───────────────────────────────

@pytest_asyncio.fixture(scope="session")
async def test_engine(postgres_url: str):
    """
    Create an async SQLAlchemy engine pointed at the test container.
    All ORM tables are created once; dropped after the session.
    """
    from saras.db.postgres import Base
    from saras.db import models  # noqa: F401 — ensures all models register on Base

    engine = create_async_engine(postgres_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


# ── Per-test DB session with automatic rollback ───────────────────────────────

@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Each test receives an AsyncSession bound to a connection that starts a
    transaction.  After the test, the transaction is rolled back so the DB
    is left clean for the next test.

    join_transaction_mode="create_savepoint" ensures that session.commit()
    inside route handlers only flushes to a savepoint (not the outer
    transaction), allowing rollback to work correctly.
    """
    connection = await test_engine.connect()
    trans = await connection.begin()
    session = AsyncSession(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )

    yield session

    await session.close()
    await trans.rollback()
    await connection.close()


# ── LLM mock ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_litellm(mocker):
    """
    Patches litellm.acompletion so no real LLM calls are made.

    Call sequence:
      1st call  → router JSON (RouterDecision-shaped content)
      2nd+ call → plain text response (llm_turn.json content)

    Returns a list tracking call count for test assertions.
    """
    router_content = json.dumps(load_fixture("llm_responses/router_decision.json"))
    turn_content = load_fixture("llm_responses/llm_turn.json")["content"]
    call_log: list[dict] = []

    async def _mock_completion(**kwargs):
        call_log.append({"model": kwargs.get("model"), "n_messages": len(kwargs.get("messages", []))})
        # Router calls use small context; primary calls use larger
        n_messages = len(kwargs.get("messages", []))
        if n_messages <= 2:
            return make_mock_llm_response(content=router_content)
        return make_mock_llm_response(content=turn_content)

    mocker.patch("litellm.acompletion", side_effect=_mock_completion)
    return call_log


# ── FastAPI test HTTP client ───────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client(
    db_session: AsyncSession,
    mocker,
) -> AsyncGenerator[AsyncClient, None]:
    """
    httpx.AsyncClient wired to the FastAPI app with:
      - DB dependency overridden to use the test session
      - Lifespan replaced with a no-op (avoids startup/shutdown side effects)
      - Redis publish mocked to prevent connection errors
      - litellm.acompletion mocked
    """
    from saras.main import app
    from saras.db.postgres import get_db

    # No-op lifespan — avoids DuckDB bootstrap and redis/engine shutdown bugs
    @asynccontextmanager
    async def _test_lifespan(_app):
        yield

    app.router.lifespan_context = _test_lifespan

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    # Silence Redis to avoid needing a real connection in most API tests
    mocker.patch("saras.db.redis.publish", new=AsyncMock())
    # Mock LLM calls globally for all client-based tests
    router_content = json.dumps(load_fixture("llm_responses/router_decision.json"))
    turn_content = load_fixture("llm_responses/llm_turn.json")["content"]
    call_log: list[dict] = []

    async def _mock_completion(**kwargs):
        call_log.append({"model": kwargs.get("model")})
        n = len(kwargs.get("messages", []))
        if n <= 2:
            return make_mock_llm_response(content=router_content)
        return make_mock_llm_response(content=turn_content)

    mocker.patch("litellm.acompletion", side_effect=_mock_completion)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
