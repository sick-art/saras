"""Integration tests for /api/projects/{project_id}/agents endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import MINIMAL_AGENT_YAML, create_agent, create_project

FIXTURE_YAML = (Path(__file__).parents[2] / "fixtures" / "sample_agent.yaml").read_text()

# Invalid YAML — references tool that isn't defined
INVALID_AGENT_YAML = """\
agent:
  name: "Bad Agent"
  version: "1.0.0"
  models:
    primary: "gpt-4o-mini"
  conditions:
    - name: "C1"
      description: "A condition"
      goals:
        - name: "G1"
          description: "A goal"
          tools:
            - "Undefined Tool"
"""


# ── GET /api/projects/{project_id}/agents ─────────────────────────────────────

async def test_list_agents_empty(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    response = await client.get(f"/api/projects/{project.id}/agents")
    assert response.status_code == 200
    assert response.json() == []


async def test_list_agents_returns_agents(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    await create_agent(db_session, project, name="Agent One")
    await create_agent(db_session, project, name="Agent Two")

    response = await client.get(f"/api/projects/{project.id}/agents")
    data = response.json()
    assert len(data) == 2
    names = {a["name"] for a in data}
    assert "Agent One" in names
    assert "Agent Two" in names


async def test_list_agents_only_returns_own_project(
    client: AsyncClient, db_session: AsyncSession
):
    project_a = await create_project(db_session, name="Project A")
    project_b = await create_project(db_session, name="Project B")
    await create_agent(db_session, project_a, name="Agent A")
    await create_agent(db_session, project_b, name="Agent B")

    response = await client.get(f"/api/projects/{project_a.id}/agents")
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Agent A"


# ── POST /api/projects/{project_id}/agents ────────────────────────────────────

async def test_create_agent_returns_201(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    response = await client.post(
        f"/api/projects/{project.id}/agents",
        json={"name": "New Agent", "description": "A fresh agent"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "New Agent"
    assert data["project_id"] == project.id
    assert len(data["id"]) == 26


async def test_create_agent_with_yaml(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    response = await client.post(
        f"/api/projects/{project.id}/agents",
        json={"name": "YAML Agent", "yaml_content": MINIMAL_AGENT_YAML},
    )
    assert response.status_code == 201
    assert response.json()["yaml_content"] == MINIMAL_AGENT_YAML


async def test_create_agent_missing_name_returns_422(
    client: AsyncClient, db_session: AsyncSession
):
    project = await create_project(db_session)
    response = await client.post(
        f"/api/projects/{project.id}/agents",
        json={"description": "No name"},
    )
    assert response.status_code == 422


# ── GET /api/projects/{project_id}/agents/{agent_id} ─────────────────────────

async def test_get_agent_returns_200(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    agent = await create_agent(db_session, project, name="Specific Agent")

    response = await client.get(f"/api/projects/{project.id}/agents/{agent.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == agent.id
    assert data["name"] == "Specific Agent"


async def test_get_nonexistent_agent_returns_404(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    response = await client.get(f"/api/projects/{project.id}/agents/NOTEXIST00000000000000001")
    assert response.status_code == 404


# ── PATCH /api/projects/{project_id}/agents/{agent_id} ───────────────────────

async def test_patch_agent_name(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    agent = await create_agent(db_session, project, name="Old Name")

    response = await client.patch(
        f"/api/projects/{project.id}/agents/{agent.id}",
        json={"name": "New Name"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "New Name"


async def test_patch_agent_yaml_creates_version(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    agent = await create_agent(db_session, project)

    await client.patch(
        f"/api/projects/{project.id}/agents/{agent.id}",
        json={"yaml_content": MINIMAL_AGENT_YAML, "change_summary": "First real YAML"},
    )

    versions_resp = await client.get(f"/api/projects/{project.id}/agents/{agent.id}/versions")
    assert versions_resp.status_code == 200
    assert len(versions_resp.json()) >= 1


# ── DELETE /api/projects/{project_id}/agents/{agent_id} ──────────────────────

async def test_delete_agent_returns_204(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    agent = await create_agent(db_session, project)

    response = await client.delete(f"/api/projects/{project.id}/agents/{agent.id}")
    assert response.status_code == 204


async def test_delete_agent_then_get_returns_404(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    agent = await create_agent(db_session, project)

    await client.delete(f"/api/projects/{project.id}/agents/{agent.id}")
    r = await client.get(f"/api/projects/{project.id}/agents/{agent.id}")
    assert r.status_code == 404


# ── POST .../validate ─────────────────────────────────────────────────────────

async def test_validate_valid_yaml_returns_no_errors(
    client: AsyncClient, db_session: AsyncSession
):
    project = await create_project(db_session)
    agent = await create_agent(db_session, project, yaml_content=FIXTURE_YAML)

    response = await client.post(
        f"/api/projects/{project.id}/agents/{agent.id}/validate",
    )
    assert response.status_code == 200
    data = response.json()
    assert "errors" in data
    assert data["errors"] == []


async def test_validate_invalid_yaml_returns_errors(
    client: AsyncClient, db_session: AsyncSession
):
    project = await create_project(db_session)
    agent = await create_agent(db_session, project, yaml_content=INVALID_AGENT_YAML)

    response = await client.post(
        f"/api/projects/{project.id}/agents/{agent.id}/validate",
    )
    assert response.status_code == 200
    data = response.json()
    errors = data.get("errors", [])
    assert len(errors) > 0
    codes = [e["code"] for e in errors]
    assert "tool_ref_undefined" in codes


# ── GET .../versions ──────────────────────────────────────────────────────────

async def test_list_versions_initially_empty_or_has_initial(
    client: AsyncClient, db_session: AsyncSession
):
    project = await create_project(db_session)
    agent = await create_agent(db_session, project)

    response = await client.get(f"/api/projects/{project.id}/agents/{agent.id}/versions")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
