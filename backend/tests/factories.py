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


# ── Simulator span helper ────────────────────────────────────────────────────

async def create_simulator_spans(
    db: AsyncSession,
    run: Run,
    *,
    user_message: str = "Hello",
    assistant_content: str = "Hi there!",
    turn_type: str = "response",
    model: str = "gpt-4o-mini",
    tool_calls: list[dict[str, Any]] | None = None,
) -> list[Span]:
    """Create a realistic set of spans for one simulator turn.

    Mimics what run_turn() produces through emit_span(). Each span gets an
    explicit started_at with small sequential offsets for deterministic ordering.
    """
    from datetime import UTC, datetime, timedelta

    base_time = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
    spans: list[Span] = []
    offset_ms = 0

    def _next_time() -> datetime:
        nonlocal offset_ms
        t = base_time + timedelta(milliseconds=offset_ms)
        offset_ms += 50
        return t

    # router_start
    spans.append(Span(
        id=str(ulid_new()), run_id=run.id, name="router_start", type="router_start",
        started_at=_next_time(), ended_at=_next_time(), duration_ms=50,
        payload={"model": model},
    ))

    # router_decision
    decision_payload: dict[str, Any] = {
        "user_message": user_message,
        "decision": {
            "active_condition": "General",
            "active_goal": "Assist",
            "interrupt_triggered": None,
            "handoff_triggered": None,
            "unfilled_slots": [],
            "extracted_slot_values": {},
        },
        "model": model,
        "system_prompt": "You are a routing assistant.",
        "prompt": f"NEW USER MESSAGE: {user_message}",
        "slot_state": {},
    }
    spans.append(Span(
        id=str(ulid_new()), run_id=run.id, name="router_decision", type="router_decision",
        started_at=_next_time(), ended_at=_next_time(), duration_ms=100,
        payload=decision_payload,
    ))

    # Slot-fill / handoff / interrupt branches skip LLM calls
    if turn_type not in ("slot_fill", "handoff"):
        # llm_call_start
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": user_message},
        ]
        spans.append(Span(
            id=str(ulid_new()), run_id=run.id, name="llm_call_start", type="llm_call_start",
            started_at=_next_time(), ended_at=None, duration_ms=None,
            payload={
                "model": model, "iteration": 0,
                "n_messages": len(messages),
                "system_prompt": messages[0]["content"],
                "messages": messages,
            },
        ))

        # llm_call_end
        tool_calls_out = None
        if tool_calls:
            tool_calls_out = [
                {"id": f"tc_{i}", "name": tc["tool"], "arguments": tc.get("arguments", {})}
                for i, tc in enumerate(tool_calls)
            ]
        spans.append(Span(
            id=str(ulid_new()), run_id=run.id, name="llm_call_end", type="llm_call_end",
            started_at=_next_time(), ended_at=_next_time(), duration_ms=200,
            payload={
                "model": model, "iteration": 0,
                "input_tokens": 100, "output_tokens": 50,
                "stop_reason": "tool_calls" if tool_calls else "end_turn",
                "output": assistant_content if not tool_calls else None,
                "tool_calls": tool_calls_out,
            },
        ))

        # Tool call/result pairs
        if tool_calls:
            for tc in tool_calls:
                spans.append(Span(
                    id=str(ulid_new()), run_id=run.id, name="tool_call", type="tool_call",
                    started_at=_next_time(), ended_at=None, duration_ms=None,
                    payload={"tool": tc["tool"], "arguments": tc.get("arguments", {})},
                ))
                spans.append(Span(
                    id=str(ulid_new()), run_id=run.id, name="tool_result", type="tool_result",
                    started_at=_next_time(), ended_at=_next_time(), duration_ms=100,
                    payload={"tool": tc["tool"], "result_preview": tc.get("result_preview", '{"status": "ok"}')},
                ))

    if turn_type == "slot_fill":
        spans.append(Span(
            id=str(ulid_new()), run_id=run.id, name="slot_fill", type="slot_fill",
            started_at=_next_time(), ended_at=_next_time(), duration_ms=10,
            payload={"slot_name": "Order Number"},
        ))

    if turn_type == "interrupt":
        spans.append(Span(
            id=str(ulid_new()), run_id=run.id, name="interrupt_triggered", type="interrupt_triggered",
            started_at=_next_time(), ended_at=_next_time(), duration_ms=5,
            payload={"trigger": "Emergency", "action": "Provide emergency info."},
        ))

    if turn_type == "handoff":
        spans.append(Span(
            id=str(ulid_new()), run_id=run.id, name="handoff_triggered", type="handoff_triggered",
            started_at=_next_time(), ended_at=_next_time(), duration_ms=5,
            payload={"handoff": "Human Escalation", "target": "Human Support Queue"},
        ))

    # turn_complete — always present for completed runs
    spans.append(Span(
        id=str(ulid_new()), run_id=run.id, name="turn_complete", type="turn_complete",
        started_at=_next_time(), ended_at=_next_time(), duration_ms=500,
        payload={
            "content": assistant_content,
            "turn_type": turn_type,
            "duration_ms": 500,
            "total_input_tokens": 150,
            "total_output_tokens": 50,
            "estimated_cost_usd": 0.001,
        },
    ))

    for s in spans:
        db.add(s)
    await db.flush()
    return spans


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
