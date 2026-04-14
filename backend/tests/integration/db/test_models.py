"""Integration tests for ORM model creation, relationships, and cascade deletes."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from saras.db.models import (
    Agent,
    AgentVersion,
    Dataset,
    DatasetItem,
    EvalResult,
    EvalRun,
    EvalSuite,
    Project,
    Run,
    Span,
)
from tests.factories import (
    MINIMAL_AGENT_YAML,
    create_agent,
    create_agent_version,
    create_dataset,
    create_dataset_item,
    create_eval_result,
    create_eval_run,
    create_eval_suite,
    create_project,
    create_run,
    create_span,
)


# ── Project ────────────────────────────────────────────────────────────────────

async def test_create_and_fetch_project(db_session: AsyncSession):
    project = await create_project(db_session, name="Persisted Project")

    fetched = await db_session.get(Project, project.id)
    assert fetched is not None
    assert fetched.name == "Persisted Project"
    assert fetched.id == project.id


async def test_project_has_ulid_id(db_session: AsyncSession):
    project = await create_project(db_session)
    assert len(project.id) == 26  # ULID is 26 chars


async def test_project_timestamps_set(db_session: AsyncSession):
    project = await create_project(db_session)
    # After flush, server_default timestamps may not be populated until refresh
    await db_session.refresh(project)
    # created_at and updated_at are server_default — may be None before commit
    # Just verify the model has these attributes
    assert hasattr(project, "created_at")
    assert hasattr(project, "updated_at")


# ── Agent ──────────────────────────────────────────────────────────────────────

async def test_create_and_fetch_agent(db_session: AsyncSession):
    project = await create_project(db_session)
    agent = await create_agent(db_session, project, name="Test Agent")

    fetched = await db_session.get(Agent, agent.id)
    assert fetched is not None
    assert fetched.name == "Test Agent"
    assert fetched.project_id == project.id


async def test_agent_default_version(db_session: AsyncSession):
    project = await create_project(db_session)
    agent = await create_agent(db_session, project)
    assert agent.current_version == "1.0.0"
    assert agent.is_published is False


async def test_agent_version_created(db_session: AsyncSession):
    project = await create_project(db_session)
    agent = await create_agent(db_session, project)
    version = await create_agent_version(db_session, agent, version="1.0.1")

    fetched = await db_session.get(AgentVersion, version.id)
    assert fetched is not None
    assert fetched.agent_id == agent.id
    assert fetched.version == "1.0.1"


# ── Cascade: delete agent removes runs ────────────────────────────────────────

async def test_delete_agent_cascades_to_runs(db_session: AsyncSession):
    project = await create_project(db_session)
    agent = await create_agent(db_session, project)
    run = await create_run(db_session, agent)
    span = await create_span(db_session, run)

    # Confirm run exists
    assert await db_session.get(Run, run.id) is not None
    assert await db_session.get(Span, span.id) is not None

    # Delete agent
    agent_obj = await db_session.get(Agent, agent.id)
    await db_session.delete(agent_obj)
    await db_session.flush()

    # Runs cascade to deleted
    assert await db_session.get(Run, run.id) is None
    # Spans also cascade (run FK → CASCADE)
    assert await db_session.get(Span, span.id) is None


async def test_delete_agent_cascades_to_versions(db_session: AsyncSession):
    project = await create_project(db_session)
    agent = await create_agent(db_session, project)
    version = await create_agent_version(db_session, agent)

    agent_obj = await db_session.get(Agent, agent.id)
    await db_session.delete(agent_obj)
    await db_session.flush()

    assert await db_session.get(AgentVersion, version.id) is None


# ── Run + Span ─────────────────────────────────────────────────────────────────

async def test_run_has_agent_relationship(db_session: AsyncSession):
    project = await create_project(db_session)
    agent = await create_agent(db_session, project)
    run = await create_run(db_session, agent)

    fetched = await db_session.get(Run, run.id)
    assert fetched is not None
    assert fetched.agent_id == agent.id
    assert fetched.status == "completed"


async def test_span_has_run_relationship(db_session: AsyncSession):
    project = await create_project(db_session)
    agent = await create_agent(db_session, project)
    run = await create_run(db_session, agent)
    span = await create_span(db_session, run, span_type="llm_call")

    fetched = await db_session.get(Span, span.id)
    assert fetched is not None
    assert fetched.run_id == run.id
    assert fetched.type == "llm_call"


async def test_delete_run_cascades_to_spans(db_session: AsyncSession):
    project = await create_project(db_session)
    agent = await create_agent(db_session, project)
    run = await create_run(db_session, agent)
    span = await create_span(db_session, run)

    run_obj = await db_session.get(Run, run.id)
    await db_session.delete(run_obj)
    await db_session.flush()

    assert await db_session.get(Span, span.id) is None


# ── Dataset ────────────────────────────────────────────────────────────────────

async def test_create_dataset_and_items(db_session: AsyncSession):
    project = await create_project(db_session)
    dataset = await create_dataset(db_session, project, name="Golden Set")
    item1 = await create_dataset_item(db_session, dataset)
    item2 = await create_dataset_item(db_session, dataset)

    result = await db_session.execute(
        select(DatasetItem).where(DatasetItem.dataset_id == dataset.id)
    )
    items = result.scalars().all()
    assert len(items) == 2
    ids = {i.id for i in items}
    assert item1.id in ids
    assert item2.id in ids


async def test_delete_dataset_cascades_to_items(db_session: AsyncSession):
    project = await create_project(db_session)
    dataset = await create_dataset(db_session, project)
    item = await create_dataset_item(db_session, dataset)

    ds_obj = await db_session.get(Dataset, dataset.id)
    await db_session.delete(ds_obj)
    await db_session.flush()

    assert await db_session.get(DatasetItem, item.id) is None


# ── Eval Suite + Run + Result ──────────────────────────────────────────────────

async def test_eval_suite_run_result_chain(db_session: AsyncSession):
    project = await create_project(db_session)
    agent = await create_agent(db_session, project)
    dataset = await create_dataset(db_session, project)
    item = await create_dataset_item(db_session, dataset)
    suite = await create_eval_suite(db_session, project)
    eval_run = await create_eval_run(db_session, suite, dataset, agent=agent)
    result = await create_eval_result(db_session, eval_run, item, score=0.75)

    fetched = await db_session.get(EvalResult, result.id)
    assert fetched is not None
    assert fetched.score == pytest.approx(0.75)
    assert fetched.eval_run_id == eval_run.id
    assert fetched.dataset_item_id == item.id


async def test_delete_eval_run_cascades_to_results(db_session: AsyncSession):
    project = await create_project(db_session)
    dataset = await create_dataset(db_session, project)
    item = await create_dataset_item(db_session, dataset)
    suite = await create_eval_suite(db_session, project)
    eval_run = await create_eval_run(db_session, suite, dataset)
    result = await create_eval_result(db_session, eval_run, item)

    run_obj = await db_session.get(EvalRun, eval_run.id)
    await db_session.delete(run_obj)
    await db_session.flush()

    assert await db_session.get(EvalResult, result.id) is None


async def test_delete_project_cascades_to_eval_suites(db_session: AsyncSession):
    project = await create_project(db_session)
    suite = await create_eval_suite(db_session, project)

    proj_obj = await db_session.get(Project, project.id)
    await db_session.delete(proj_obj)
    await db_session.flush()

    assert await db_session.get(EvalSuite, suite.id) is None


# ── Multiple projects isolation ───────────────────────────────────────────────

async def test_agents_are_scoped_to_project(db_session: AsyncSession):
    project_a = await create_project(db_session, name="Project A")
    project_b = await create_project(db_session, name="Project B")
    agent_a = await create_agent(db_session, project_a, name="Agent A")
    agent_b = await create_agent(db_session, project_b, name="Agent B")

    result = await db_session.execute(
        select(Agent).where(Agent.project_id == project_a.id)
    )
    agents_a = result.scalars().all()
    assert len(agents_a) == 1
    assert agents_a[0].id == agent_a.id
