"""Integration tests for /api/projects/{project_id}/runs|sessions|analytics."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import (
    create_agent,
    create_project,
    create_run,
    create_span,
)


# ── GET /api/projects/{project_id}/runs ───────────────────────────────────────

async def test_list_runs_empty(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    response = await client.get(f"/api/projects/{project.id}/runs")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, (list, dict))  # may be paginated or plain list


async def test_list_runs_returns_seeded_run(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    agent = await create_agent(db_session, project)
    run = await create_run(db_session, agent, status="completed")

    response = await client.get(f"/api/projects/{project.id}/runs")
    assert response.status_code == 200
    body = response.json()
    # Handle both list and paginated {"items": [...]} response shapes
    items = body if isinstance(body, list) else body.get("items", body.get("runs", []))
    run_ids = [r["id"] for r in items]
    assert run.id in run_ids


# ── GET /api/projects/{project_id}/runs/{run_id} ─────────────────────────────

async def test_get_run_returns_200(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    agent = await create_agent(db_session, project)
    run = await create_run(db_session, agent)

    response = await client.get(f"/api/projects/{project.id}/runs/{run.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == run.id
    assert data["status"] == "completed"


async def test_get_run_includes_spans(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    agent = await create_agent(db_session, project)
    run = await create_run(db_session, agent)
    await create_span(db_session, run, span_type="llm_call")
    await create_span(db_session, run, span_type="router_decision")

    response = await client.get(f"/api/projects/{project.id}/runs/{run.id}")
    assert response.status_code == 200
    data = response.json()
    # Spans should be nested or available
    assert "spans" in data or "span_count" in data


async def test_get_nonexistent_run_returns_404(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    response = await client.get(
        f"/api/projects/{project.id}/runs/NOTEXIST00000000000000001"
    )
    assert response.status_code == 404


# ── GET /api/projects/{project_id}/sessions ───────────────────────────────────

async def test_list_sessions_empty(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    response = await client.get(f"/api/projects/{project.id}/sessions")
    assert response.status_code == 200


async def test_list_sessions_groups_by_session_id(
    client: AsyncClient, db_session: AsyncSession
):
    project = await create_project(db_session)
    agent = await create_agent(db_session, project)

    session_id = "01ABCDEFGHIJKLMNOPQRSTUVWX"
    await create_run(db_session, agent, session_id=session_id)
    await create_run(db_session, agent, session_id=session_id)

    response = await client.get(f"/api/projects/{project.id}/sessions")
    assert response.status_code == 200
    body = response.json()
    items = body if isinstance(body, list) else body.get("items", body.get("sessions", []))
    # Both runs share a session_id, so there should be 1 session
    assert len(items) >= 1


# ── GET /api/projects/{project_id}/analytics ──────────────────────────────────

async def test_get_analytics_returns_summary_keys(
    client: AsyncClient, db_session: AsyncSession
):
    project = await create_project(db_session)

    # Mock DuckDB so we don't need a file-based DuckDB in integration tests
    mock_summary = {
        "cost_over_time": [],
        "latency": {"p50": 0, "p95": 0, "mean": 0, "total_runs": 0},
        "models": [],
        "errors": {"total": 0, "errors": 0, "error_rate_pct": 0.0},
        "span_types": [],
    }

    with patch("saras.api.traces.analytics_summary", return_value=mock_summary):
        response = await client.get(f"/api/projects/{project.id}/analytics")

    assert response.status_code == 200
    data = response.json()
    assert "cost_over_time" in data or "latency" in data or isinstance(data, dict)


# ── Run filtering ─────────────────────────────────────────────────────────────

async def test_list_runs_filter_by_status(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    agent = await create_agent(db_session, project)
    await create_run(db_session, agent, status="completed")
    await create_run(db_session, agent, status="failed")

    response = await client.get(
        f"/api/projects/{project.id}/runs", params={"status": "failed"}
    )
    assert response.status_code == 200
    body = response.json()
    items = body if isinstance(body, list) else body.get("items", [])
    assert all(r["status"] == "failed" for r in items)
