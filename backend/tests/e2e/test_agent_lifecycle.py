"""
E2E test: Full agent lifecycle through the API.

Exercises the complete user journey:
  1. Create project
  2. Create agent with valid YAML
  3. Validate agent — assert zero errors
  4. Create dataset + add item
  5. Create eval suite
  6. Trigger eval run (background task mocked)
  7. Verify eval run recorded in DB
  8. Retrieve eval results

All LLM calls are mocked. Real Postgres + Redis via testcontainers.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

FIXTURE_YAML = (Path(__file__).parents[1] / "fixtures" / "sample_agent.yaml").read_text()
MINIMAL_METRIC_YAML = """\
metrics:
  - preset: goal_completion
  - preset: response_quality
"""


async def test_full_agent_lifecycle(client: AsyncClient, db_session: AsyncSession):
    """
    Smoke-test the happy path from project creation through eval run creation.
    """

    # ── Step 1: Create project ─────────────────────────────────────────────────
    r = await client.post(
        "/api/projects",
        json={"name": "E2E Test Project", "description": "End-to-end lifecycle test"},
    )
    assert r.status_code == 201, f"Create project failed: {r.text}"
    project_id = r.json()["id"]
    assert len(project_id) == 26

    # ── Step 2: Create agent with full YAML ────────────────────────────────────
    r = await client.post(
        f"/api/projects/{project_id}/agents",
        json={
            "name": "E2E Support Agent",
            "description": "Agent used in e2e test",
            "yaml_content": FIXTURE_YAML,
        },
    )
    assert r.status_code == 201, f"Create agent failed: {r.text}"
    agent_id = r.json()["id"]

    # ── Step 3: Validate agent ─────────────────────────────────────────────────
    r = await client.post(f"/api/projects/{project_id}/agents/{agent_id}/validate")
    assert r.status_code == 200, f"Validate failed: {r.text}"
    validation = r.json()
    assert validation.get("errors", []) == [], (
        f"Expected zero errors, got: {validation.get('errors')}"
    )

    # ── Step 4: Create dataset + add an item ───────────────────────────────────
    r = await client.post(
        f"/api/projects/{project_id}/datasets",
        json={"name": "E2E Dataset", "description": "For lifecycle test"},
    )
    assert r.status_code == 201, f"Create dataset failed: {r.text}"
    dataset_id = r.json()["id"]

    r = await client.post(
        f"/api/projects/{project_id}/datasets/{dataset_id}/items",
        json={
            "input": {"turns": ["What is the status of my order ORD-123?"]},
            "expected_output": {
                "response": "Your order ORD-123 is on its way and should arrive by Friday."
            },
            "source": "human",
        },
    )
    assert r.status_code == 201, f"Add dataset item failed: {r.text}"

    # ── Step 5: Create eval suite ──────────────────────────────────────────────
    r = await client.post(
        f"/api/projects/{project_id}/evals/suites",
        json={
            "name": "E2E Eval Suite",
            "description": "Lifecycle test suite",
            "metric_set_yaml": MINIMAL_METRIC_YAML,
        },
    )
    assert r.status_code == 201, f"Create eval suite failed: {r.text}"
    suite_id = r.json()["id"]

    # ── Step 6: Trigger eval run (background task mocked) ─────────────────────
    with patch("saras.api.evals.run_eval", new=AsyncMock()):
        r = await client.post(
            f"/api/projects/{project_id}/evals/suites/{suite_id}/runs",
            json={"agent_id": agent_id, "dataset_id": dataset_id},
        )
    assert r.status_code in (200, 201, 202), f"Trigger eval run failed: {r.text}"
    eval_run_id = r.json()["id"]
    assert r.json()["status"] in ("pending", "running")

    # ── Step 7: Verify eval run is recorded ────────────────────────────────────
    r = await client.get(f"/api/projects/{project_id}/evals/runs/{eval_run_id}")
    assert r.status_code == 200, f"Get eval run failed: {r.text}"
    data = r.json()
    assert data["id"] == eval_run_id
    assert data["suite_id"] == suite_id
    assert data["dataset_id"] == dataset_id

    # ── Step 8: List all eval runs for the project ─────────────────────────────
    r = await client.get(f"/api/projects/{project_id}/evals/runs")
    assert r.status_code == 200
    run_ids = [run["id"] for run in r.json()]
    assert eval_run_id in run_ids

    # ── Step 9: Verify agent still accessible ──────────────────────────────────
    r = await client.get(f"/api/projects/{project_id}/agents/{agent_id}")
    assert r.status_code == 200
    assert r.json()["name"] == "E2E Support Agent"

    # ── Step 10: Cleanup — delete the project ─────────────────────────────────
    r = await client.delete(f"/api/projects/{project_id}")
    assert r.status_code == 204

    # Confirm cascade: agent no longer accessible
    r = await client.get(f"/api/projects/{project_id}/agents/{agent_id}")
    assert r.status_code in (404, 422)


async def test_agent_validation_catches_undefined_tool(
    client: AsyncClient, db_session: AsyncSession
):
    """E2E: Create an agent with a broken YAML and verify validation catches it."""
    broken_yaml = """\
agent:
  name: "Broken Agent"
  version: "1.0.0"
  models:
    primary: "gpt-4o-mini"
  conditions:
    - name: "Order Issue"
      description: "User has an order issue"
      goals:
        - name: "Fix Order"
          description: "Resolve the order issue"
          tools:
            - "Ghost Tool"
"""
    r = await client.post(
        "/api/projects",
        json={"name": "Broken Agent Project"},
    )
    project_id = r.json()["id"]

    r = await client.post(
        f"/api/projects/{project_id}/agents",
        json={"name": "Broken", "yaml_content": broken_yaml},
    )
    agent_id = r.json()["id"]

    r = await client.post(f"/api/projects/{project_id}/agents/{agent_id}/validate")
    assert r.status_code == 200
    errors = r.json().get("errors", [])
    assert any(e["code"] == "tool_ref_undefined" for e in errors)


async def test_create_multiple_agents_in_project(
    client: AsyncClient, db_session: AsyncSession
):
    """E2E: Multiple agents can be created under one project."""
    r = await client.post("/api/projects", json={"name": "Multi-Agent Project"})
    project_id = r.json()["id"]

    for i in range(3):
        r = await client.post(
            f"/api/projects/{project_id}/agents",
            json={"name": f"Agent {i}", "yaml_content": FIXTURE_YAML},
        )
        assert r.status_code == 201

    r = await client.get(f"/api/projects/{project_id}/agents")
    assert len(r.json()) == 3
