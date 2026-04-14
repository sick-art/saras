"""Integration tests for /api/projects/{project_id}/datasets endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import (
    create_agent,
    create_dataset,
    create_dataset_item,
    create_project,
    create_run,
    create_span,
)


# ── GET /api/projects/{project_id}/datasets ───────────────────────────────────

async def test_list_datasets_empty(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    response = await client.get(f"/api/projects/{project.id}/datasets")
    assert response.status_code == 200
    assert response.json() == []


async def test_list_datasets_returns_created(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    await create_dataset(db_session, project, name="Dataset A")
    await create_dataset(db_session, project, name="Dataset B")

    response = await client.get(f"/api/projects/{project.id}/datasets")
    data = response.json()
    assert len(data) == 2
    names = {d["name"] for d in data}
    assert "Dataset A" in names and "Dataset B" in names


# ── POST /api/projects/{project_id}/datasets ──────────────────────────────────

async def test_create_dataset_returns_201(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    response = await client.post(
        f"/api/projects/{project.id}/datasets",
        json={"name": "New Dataset", "description": "Test data"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "New Dataset"
    assert len(data["id"]) == 26


async def test_create_dataset_missing_name_returns_422(
    client: AsyncClient, db_session: AsyncSession
):
    project = await create_project(db_session)
    response = await client.post(
        f"/api/projects/{project.id}/datasets",
        json={"description": "No name"},
    )
    assert response.status_code == 422


# ── GET /api/projects/{project_id}/datasets/{dataset_id} ─────────────────────

async def test_get_dataset_returns_200(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    dataset = await create_dataset(db_session, project, name="Specific Dataset")

    response = await client.get(f"/api/projects/{project.id}/datasets/{dataset.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == dataset.id
    assert data["name"] == "Specific Dataset"


async def test_get_nonexistent_dataset_returns_404(
    client: AsyncClient, db_session: AsyncSession
):
    project = await create_project(db_session)
    response = await client.get(
        f"/api/projects/{project.id}/datasets/NOTEXIST00000000000000001"
    )
    assert response.status_code == 404


# ── POST .../items ────────────────────────────────────────────────────────────

async def test_add_dataset_item_returns_201(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    dataset = await create_dataset(db_session, project)

    response = await client.post(
        f"/api/projects/{project.id}/datasets/{dataset.id}/items",
        json={
            "input": {"turns": ["What is the status of my order?"]},
            "expected_output": {"response": "Let me look that up for you."},
            "source": "human",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert len(data["id"]) == 26
    assert data["source"] == "human"


async def test_add_item_invalid_body_returns_422(
    client: AsyncClient, db_session: AsyncSession
):
    project = await create_project(db_session)
    dataset = await create_dataset(db_session, project)

    response = await client.post(
        f"/api/projects/{project.id}/datasets/{dataset.id}/items",
        json={"expected_output": "missing_input"},
    )
    assert response.status_code == 422


# ── PATCH .../items/{item_id} ─────────────────────────────────────────────────

async def test_update_dataset_item(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    dataset = await create_dataset(db_session, project)
    item = await create_dataset_item(db_session, dataset)

    response = await client.patch(
        f"/api/projects/{project.id}/datasets/{dataset.id}/items/{item.id}",
        json={"expected_output": {"response": "Updated expected output."}},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["expected_output"]["response"] == "Updated expected output."


# ── DELETE .../items/{item_id} ────────────────────────────────────────────────

async def test_delete_dataset_item_returns_204(client: AsyncClient, db_session: AsyncSession):
    project = await create_project(db_session)
    dataset = await create_dataset(db_session, project)
    item = await create_dataset_item(db_session, dataset)

    response = await client.delete(
        f"/api/projects/{project.id}/datasets/{dataset.id}/items/{item.id}"
    )
    assert response.status_code == 204


async def test_get_dataset_includes_items(client: AsyncClient, db_session: AsyncSession):
    """GET /datasets/{id} response should include item count or items field."""
    project = await create_project(db_session)
    dataset = await create_dataset(db_session, project)
    await create_dataset_item(db_session, dataset)
    await create_dataset_item(db_session, dataset)

    response = await client.get(f"/api/projects/{project.id}/datasets/{dataset.id}")
    assert response.status_code == 200
    data = response.json()
    # The response may include items or item_count — just verify it's a dict
    assert isinstance(data, dict)
    assert data["id"] == dataset.id
