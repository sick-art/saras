"""Integration tests for /api/projects/{project_id}/evals endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import (
    MINIMAL_METRIC_YAML,
    create_agent,
    create_dataset,
    create_dataset_item,
    create_eval_result,
    create_eval_run,
    create_eval_suite,
    create_project,
)


# ── GET /api/projects/{project_id}/evals/suites ───────────────────────────────

async def test_list_eval_suites_empty(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    response = await client.get(f"/api/projects/{project.id}/evals/suites")
    assert response.status_code == 200
    assert response.json() == []


async def test_list_eval_suites_returns_created(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    await create_eval_suite(db_session, project, name="Suite A")
    await create_eval_suite(db_session, project, name="Suite B")

    response = await client.get(f"/api/projects/{project.id}/evals/suites")
    data = response.json()
    assert len(data) == 2
    names = {s["name"] for s in data}
    assert "Suite A" in names and "Suite B" in names


# ── POST /api/projects/{project_id}/evals/suites ─────────────────────────────

async def test_create_eval_suite_returns_201(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    response = await client.post(
        f"/api/projects/{project.id}/evals/suites",
        json={
            "name": "New Eval Suite",
            "description": "Testing evaluation",
            "metric_set_yaml": MINIMAL_METRIC_YAML,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "New Eval Suite"
    assert len(data["id"]) == 26


async def test_create_eval_suite_missing_name_returns_422(
    client: AsyncClient, db_session: AsyncSession
):
    project = await create_project(db_session)
    response = await client.post(
        f"/api/projects/{project.id}/evals/suites",
        json={"metric_set_yaml": MINIMAL_METRIC_YAML},
    )
    assert response.status_code == 422


# ── GET /api/projects/{project_id}/evals/suites/{suite_id} ───────────────────

async def test_get_eval_suite_returns_200(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    suite = await create_eval_suite(db_session, project, name="Specific Suite")

    response = await client.get(f"/api/projects/{project.id}/evals/suites/{suite.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == suite.id
    assert data["name"] == "Specific Suite"


async def test_get_nonexistent_suite_returns_404(
    client: AsyncClient, db_session: AsyncSession
):
    project = await create_project(db_session)
    response = await client.get(
        f"/api/projects/{project.id}/evals/suites/NOTEXIST00000000000000001"
    )
    assert response.status_code == 404


# ── PATCH /api/projects/{project_id}/evals/suites/{suite_id} ─────────────────

async def test_patch_eval_suite_name(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    suite = await create_eval_suite(db_session, project, name="Old Suite Name")

    response = await client.patch(
        f"/api/projects/{project.id}/evals/suites/{suite.id}",
        json={"name": "Updated Suite Name"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Updated Suite Name"


# ── DELETE /api/projects/{project_id}/evals/suites/{suite_id} ─────────────────

async def test_delete_eval_suite_returns_204(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    suite = await create_eval_suite(db_session, project, name="To Delete")

    response = await client.delete(
        f"/api/projects/{project.id}/evals/suites/{suite.id}"
    )
    assert response.status_code == 204

    # Verify suite no longer appears in list
    list_resp = await client.get(f"/api/projects/{project.id}/evals/suites")
    assert all(s["id"] != suite.id for s in list_resp.json())


async def test_delete_eval_suite_not_found_returns_404(
    client: AsyncClient, db_session: AsyncSession
):
    project = await create_project(db_session)
    response = await client.delete(
        f"/api/projects/{project.id}/evals/suites/NOTEXIST00000000000000001"
    )
    assert response.status_code == 404


async def test_delete_eval_suite_wrong_project_returns_404(
    client: AsyncClient, db_session: AsyncSession
):
    project_a = await create_project(db_session, name="Project A")
    project_b = await create_project(db_session, name="Project B")
    suite = await create_eval_suite(db_session, project_a)

    response = await client.delete(
        f"/api/projects/{project_b.id}/evals/suites/{suite.id}"
    )
    assert response.status_code == 404


async def test_delete_eval_suite_cascades_runs_and_results(
    client: AsyncClient, db_session: AsyncSession
):
    project = await create_project(db_session)
    agent = await create_agent(db_session, project)
    dataset = await create_dataset(db_session, project)
    item = await create_dataset_item(db_session, dataset)
    suite = await create_eval_suite(db_session, project)
    eval_run = await create_eval_run(db_session, suite, dataset, agent=agent)
    await create_eval_result(db_session, eval_run, item)

    response = await client.delete(
        f"/api/projects/{project.id}/evals/suites/{suite.id}"
    )
    assert response.status_code == 204

    # Suite, run, and result should all be gone
    suite_resp = await client.get(f"/api/projects/{project.id}/evals/suites/{suite.id}")
    assert suite_resp.status_code == 404

    runs_resp = await client.get(f"/api/projects/{project.id}/evals/runs")
    run_ids = [r["id"] for r in runs_resp.json()]
    assert eval_run.id not in run_ids


# ── POST .../suites/{suite_id}/runs ──────────────────────────────────────────

async def test_trigger_eval_run_returns_accepted(
    client: AsyncClient, db_session: AsyncSession
):
    project = await create_project(db_session)
    agent = await create_agent(db_session, project)
    dataset = await create_dataset(db_session, project)
    await create_dataset_item(db_session, dataset)
    suite = await create_eval_suite(db_session, project)

    # Mock the background eval runner to prevent actual LLM calls
    with patch("saras.api.evals.run_eval", new=AsyncMock()):
        response = await client.post(
            f"/api/projects/{project.id}/evals/suites/{suite.id}/runs",
            json={"agent_id": agent.id, "dataset_id": dataset.id},
        )

    assert response.status_code in (200, 201, 202)
    data = response.json()
    assert "id" in data
    assert data["status"] in ("pending", "running")


# ── GET /api/projects/{project_id}/evals/runs ────────────────────────────────

async def test_list_eval_runs_empty(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    response = await client.get(f"/api/projects/{project.id}/evals/runs")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


async def test_list_eval_runs_returns_seeded(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    dataset = await create_dataset(db_session, project)
    suite = await create_eval_suite(db_session, project)
    eval_run = await create_eval_run(db_session, suite, dataset)

    response = await client.get(f"/api/projects/{project.id}/evals/runs")
    data = response.json()
    run_ids = [r["id"] for r in data]
    assert eval_run.id in run_ids


# ── GET /api/projects/{project_id}/evals/runs/{run_id} ───────────────────────

async def test_get_eval_run_returns_200(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    dataset = await create_dataset(db_session, project)
    suite = await create_eval_suite(db_session, project)
    eval_run = await create_eval_run(db_session, suite, dataset, status="completed")

    response = await client.get(f"/api/projects/{project.id}/evals/runs/{eval_run.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == eval_run.id
    assert data["status"] == "completed"


# ── GET .../runs/{run_id}/items ───────────────────────────────────────────────

async def test_get_eval_run_items(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    dataset = await create_dataset(db_session, project)
    suite = await create_eval_suite(db_session, project)
    eval_run = await create_eval_run(db_session, suite, dataset, status="completed")
    item = await create_dataset_item(db_session, dataset)
    await create_eval_result(db_session, eval_run, item, score=0.9)

    response = await client.get(
        f"/api/projects/{project.id}/evals/runs/{eval_run.id}/items"
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["score"] == pytest.approx(0.9)


# ── GET /api/projects/{project_id}/evals/presets ─────────────────────────────

async def test_list_presets_returns_list(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    response = await client.get(f"/api/projects/{project.id}/evals/presets")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    # Each preset should have a name/key
    assert all("name" in p or "key" in p or "preset" in p for p in data)
