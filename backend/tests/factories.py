"""
Test data factory helpers.

These are simple builder functions (not full factory_boy factories) that
create ORM model instances and optionally flush them to a test DB session.
Using plain functions keeps test setup readable without fighting async SQLAlchemy.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from ulid import new as ulid_new

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

# ── Minimal valid agent YAML (used when a test needs a compilable agent) ──────

MINIMAL_AGENT_YAML = """\
agent:
  name: "Factory Agent"
  version: "1.0.0"
  models:
    primary: "gpt-4o-mini"
    router: "gpt-4o-mini"
  persona: >
    You are a helpful test agent created by the test factory.
    You handle simple test scenarios efficiently and reliably.
  tone: "Professional and concise."
  global_rules:
    - Always respond in plain language.
  interrupt_triggers:
    - name: "Emergency"
      description: "The user mentions a safety emergency."
      action: "Provide emergency contacts immediately."
  handoffs:
    - name: "Human Escalation"
      description: "The user requests a human agent."
      target: "Human Support Queue"
  tools:
    - name: "Order Lookup"
      type: "LookupTool"
      description: "Looks up an order by order number."
      endpoint: "https://api.example.com/orders"
      inputs:
        - name: "Order Number"
          description: "The order ID to look up."
          required: true
  conditions:
    - name: "Order Inquiry"
      description: "The user is asking about an existing order."
      goals:
        - name: "Track Order"
          description: "Help the user track their order."
          slots:
            - name: "Order Number"
              description: "The order identifier."
              required: true
              ask_if_missing: "Could you provide your order number?"
          tools:
            - "Order Lookup"
"""


# ── Project ────────────────────────────────────────────────────────────────────

async def create_project(
    db: AsyncSession,
    *,
    name: str = "Test Project",
    description: str | None = "A project created for testing.",
) -> Project:
    obj = Project(id=str(ulid_new()), name=name, description=description)
    db.add(obj)
    await db.flush()
    return obj


# ── Agent ──────────────────────────────────────────────────────────────────────

async def create_agent(
    db: AsyncSession,
    project: Project,
    *,
    name: str = "Test Agent",
    description: str | None = "An agent created for testing.",
    yaml_content: str | None = None,
    current_version: str = "1.0.0",
    is_published: bool = False,
) -> Agent:
    obj = Agent(
        id=str(ulid_new()),
        project_id=project.id,
        name=name,
        description=description,
        yaml_content=yaml_content or MINIMAL_AGENT_YAML,
        current_version=current_version,
        is_published=is_published,
    )
    db.add(obj)
    await db.flush()
    return obj


async def create_agent_version(
    db: AsyncSession,
    agent: Agent,
    *,
    version: str = "1.0.1",
    yaml_content: str | None = None,
    change_summary: str | None = "Test version bump",
) -> AgentVersion:
    obj = AgentVersion(
        id=str(ulid_new()),
        agent_id=agent.id,
        version=version,
        yaml_content=yaml_content or MINIMAL_AGENT_YAML,
        change_summary=change_summary,
    )
    db.add(obj)
    await db.flush()
    return obj


# ── Run + Span ─────────────────────────────────────────────────────────────────

async def create_run(
    db: AsyncSession,
    agent: Agent,
    *,
    status: str = "completed",
    source: str = "simulator",
    session_id: str | None = None,
    total_tokens: int = 250,
    total_cost_usd: float = 0.001,
    metadata: dict[str, Any] | None = None,
) -> Run:
    obj = Run(
        id=str(ulid_new()),
        agent_id=agent.id,
        agent_version=agent.current_version,
        session_id=session_id or str(ulid_new()),
        status=status,
        source=source,
        total_tokens=total_tokens,
        total_cost_usd=total_cost_usd,
        metadata_=metadata,
    )
    db.add(obj)
    await db.flush()
    return obj


async def create_span(
    db: AsyncSession,
    run: Run,
    *,
    span_type: str = "llm_call",
    name: str | None = None,
    duration_ms: int = 200,
    payload: dict[str, Any] | None = None,
) -> Span:
    obj = Span(
        id=str(ulid_new()),
        run_id=run.id,
        name=name or span_type,
        type=span_type,
        duration_ms=duration_ms,
        payload=payload or {"model": "gpt-4o-mini", "input_tokens": 100, "output_tokens": 50},
    )
    db.add(obj)
    await db.flush()
    return obj


# ── Dataset ────────────────────────────────────────────────────────────────────

async def create_dataset(
    db: AsyncSession,
    project: Project,
    *,
    name: str = "Test Dataset",
    description: str | None = "A dataset for testing.",
) -> Dataset:
    obj = Dataset(
        id=str(ulid_new()),
        project_id=project.id,
        name=name,
        description=description,
    )
    db.add(obj)
    await db.flush()
    return obj


async def create_dataset_item(
    db: AsyncSession,
    dataset: Dataset,
    *,
    input_data: dict[str, Any] | None = None,
    expected_output: dict[str, Any] | None = None,
    source: str = "human",
) -> DatasetItem:
    obj = DatasetItem(
        id=str(ulid_new()),
        dataset_id=dataset.id,
        input=input_data or {"turns": ["What is the status of my order?"]},
        expected_output=expected_output or {"response": "Let me look that up for you."},
        source=source,
    )
    db.add(obj)
    await db.flush()
    return obj


# ── Eval Suite + Run + Result ──────────────────────────────────────────────────

MINIMAL_METRIC_YAML = """\
metrics:
  - preset: goal_completion
  - preset: response_quality
"""


async def create_eval_suite(
    db: AsyncSession,
    project: Project,
    *,
    name: str = "Test Eval Suite",
    description: str | None = "An eval suite for testing.",
    metric_set_yaml: str | None = None,
) -> EvalSuite:
    obj = EvalSuite(
        id=str(ulid_new()),
        project_id=project.id,
        name=name,
        description=description,
        metric_set_yaml=metric_set_yaml or MINIMAL_METRIC_YAML,
    )
    db.add(obj)
    await db.flush()
    return obj


async def create_eval_run(
    db: AsyncSession,
    suite: EvalSuite,
    dataset: Dataset,
    *,
    agent: Agent | None = None,
    status: str = "completed",
    summary: dict[str, Any] | None = None,
) -> EvalRun:
    obj = EvalRun(
        id=str(ulid_new()),
        suite_id=suite.id,
        dataset_id=dataset.id,
        agent_id=agent.id if agent else None,
        agent_version=agent.current_version if agent else None,
        status=status,
        summary=summary or {"total_items": 1, "avg_score": 0.85},
    )
    db.add(obj)
    await db.flush()
    return obj


async def create_eval_result(
    db: AsyncSession,
    eval_run: EvalRun,
    dataset_item: DatasetItem,
    *,
    metric_id: str = "goal_completion",
    score: float = 0.85,
    reasoning: str = "The agent completed the goal successfully.",
    model_used: str = "gpt-4o-mini",
    scope: str = "whole_conversation",
) -> EvalResult:
    obj = EvalResult(
        id=str(ulid_new()),
        eval_run_id=eval_run.id,
        dataset_item_id=dataset_item.id,
        metric_id=metric_id,
        score=score,
        reasoning=reasoning,
        model_used=model_used,
        scope=scope,
    )
    db.add(obj)
    await db.flush()
    return obj
