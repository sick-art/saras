"""Integration tests for /api/projects endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import create_agent, create_project


# ── GET /api/projects ─────────────────────────────────────────────────────────

async def test_list_projects_empty(client: AsyncClient):
    response = await client.get("/api/projects")
    assert response.status_code == 200
    assert response.json() == []


async def test_list_projects_returns_created(client: AsyncClient, db_session: AsyncSession):
    await create_project(db_session, name="Alpha Project")
    await create_project(db_session, name="Beta Project")

    response = await client.get("/api/projects")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    names = {p["name"] for p in data}
    assert "Alpha Project" in names
    assert "Beta Project" in names


# ── POST /api/projects ────────────────────────────────────────────────────────

async def test_create_project_returns_201(client: AsyncClient):
    response = await client.post(
        "/api/projects",
        json={"name": "My Project", "description": "A test project"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "My Project"
    assert data["description"] == "A test project"
    assert len(data["id"]) == 26  # ULID


async def test_create_project_without_description(client: AsyncClient):
    response = await client.post("/api/projects", json={"name": "Minimal"})
    assert response.status_code == 201
    assert response.json()["description"] is None


async def test_create_project_missing_name_returns_422(client: AsyncClient):
    response = await client.post("/api/projects", json={"description": "No name"})
    assert response.status_code == 422


# ── GET /api/projects/{id} ────────────────────────────────────────────────────

async def test_get_project_returns_200(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session, name="Specific Project")

    response = await client.get(f"/api/projects/{project.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == project.id
    assert data["name"] == "Specific Project"


async def test_get_nonexistent_project_returns_404(client: AsyncClient):
    response = await client.get("/api/projects/NONEXISTENTID00000000000001")
    assert response.status_code == 404


# ── DELETE /api/projects/{id} ─────────────────────────────────────────────────

async def test_delete_project_returns_204(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session, name="To Delete")

    response = await client.delete(f"/api/projects/{project.id}")
    assert response.status_code == 204


async def test_delete_project_then_get_returns_404(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session, name="Delete Me")

    await client.delete(f"/api/projects/{project.id}")
    response = await client.get(f"/api/projects/{project.id}")
    assert response.status_code == 404


async def test_delete_nonexistent_project_returns_404(client: AsyncClient):
    response = await client.delete("/api/projects/NONEXISTENTID00000000000001")
    assert response.status_code == 404


# ── Response schema ───────────────────────────────────────────────────────────

async def test_project_response_has_timestamps(client: AsyncClient):
    response = await client.post("/api/projects", json={"name": "Timestamped"})
    data = response.json()
    assert "created_at" in data
    assert "updated_at" in data
    assert data["created_at"] is not None


# ── Cascade: delete project removes agents ────────────────────────────────────

async def test_delete_project_removes_child_agents(
    client: AsyncClient, db_session: AsyncSession
):
    project = await create_project(db_session, name="Parent")
    agent = await create_agent(db_session, project, name="Child Agent")

    # Verify agent exists
    r = await client.get(f"/api/projects/{project.id}/agents/{agent.id}")
    assert r.status_code == 200

    # Delete the project
    await client.delete(f"/api/projects/{project.id}")

    # Agent should no longer be accessible
    r2 = await client.get(f"/api/projects/{project.id}/agents/{agent.id}")
    assert r2.status_code in (404, 422)
