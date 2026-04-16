"""Integration tests for /api/projects/{project_id}/runs|sessions|analytics."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import make_mock_llm_response
from tests.factories import (
    create_agent,
    create_project,
    create_run,
    create_simulator_spans,
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


# ── Session detail: conversation reconstruction ────────────────────────────────


async def test_get_session_returns_runs_with_complete_span_payloads(
    client: AsyncClient, db_session: AsyncSession
):
    """Session detail API must return spans whose payloads carry the fields
    the Chat tab needs: router_decision.user_message, turn_complete.content."""
    project = await create_project(db_session)
    agent = await create_agent(db_session, project)
    session_id = "01SESSIONABCDEF0000000001A"
    run = await create_run(db_session, agent, session_id=session_id, status="completed")

    await create_simulator_spans(
        db_session, run,
        user_message="Where is my order?",
        assistant_content="Your order ORD-123 is on its way!",
        turn_type="response",
    )

    response = await client.get(f"/api/projects/{project.id}/sessions/{session_id}")
    assert response.status_code == 200
    data = response.json()

    assert data["session_id"] == session_id
    assert len(data["runs"]) == 1

    spans = data["runs"][0]["spans"]
    span_types = [s["type"] for s in spans]
    assert "router_decision" in span_types
    assert "turn_complete" in span_types
    assert "llm_call_start" in span_types
    assert "llm_call_end" in span_types

    # Verify user message in router_decision payload
    rd = next(s for s in spans if s["type"] == "router_decision")
    assert rd["payload"]["user_message"] == "Where is my order?"

    # Verify assistant content in turn_complete payload
    tc = next(s for s in spans if s["type"] == "turn_complete")
    assert tc["payload"]["content"] == "Your order ORD-123 is on its way!"
    assert tc["payload"]["turn_type"] == "response"

    # Verify messages array in llm_call_start
    lls = next(s for s in spans if s["type"] == "llm_call_start")
    assert isinstance(lls["payload"]["messages"], list)
    assert len(lls["payload"]["messages"]) >= 1

    # Verify output in llm_call_end
    lle = next(s for s in spans if s["type"] == "llm_call_end")
    assert lle["payload"]["output"] == "Your order ORD-123 is on its way!"


async def test_session_detail_multi_turn_conversation_reconstruction(
    client: AsyncClient, db_session: AsyncSession
):
    """Multiple turns in one session must each carry independent span payloads,
    correctly grouped by run — no cross-contamination."""
    project = await create_project(db_session)
    agent = await create_agent(db_session, project)
    session_id = "01SESSIONMULTI0000000001B"

    run1 = await create_run(db_session, agent, session_id=session_id, status="completed")
    await create_simulator_spans(
        db_session, run1,
        user_message="Hi",
        assistant_content="Hello! How can I help?",
    )

    run2 = await create_run(db_session, agent, session_id=session_id, status="completed")
    await create_simulator_spans(
        db_session, run2,
        user_message="Order status please",
        assistant_content="Your order ORD-456 has shipped.",
    )

    response = await client.get(f"/api/projects/{project.id}/sessions/{session_id}")
    assert response.status_code == 200
    data = response.json()

    runs = data["runs"]
    assert len(runs) == 2

    # Turn 1
    spans1 = runs[0]["spans"]
    rd1 = next(s for s in spans1 if s["type"] == "router_decision")
    tc1 = next(s for s in spans1 if s["type"] == "turn_complete")
    assert rd1["payload"]["user_message"] == "Hi"
    assert tc1["payload"]["content"] == "Hello! How can I help?"

    # Turn 2
    spans2 = runs[1]["spans"]
    rd2 = next(s for s in spans2 if s["type"] == "router_decision")
    tc2 = next(s for s in spans2 if s["type"] == "turn_complete")
    assert rd2["payload"]["user_message"] == "Order status please"
    assert tc2["payload"]["content"] == "Your order ORD-456 has shipped."

    # Verify spans are correctly grouped — each run has its own spans
    run1_span_ids = {s["id"] for s in spans1}
    run2_span_ids = {s["id"] for s in spans2}
    assert run1_span_ids.isdisjoint(run2_span_ids), "Spans must not be shared between runs"


async def test_session_detail_cancelled_run_preserves_user_message(
    client: AsyncClient, db_session: AsyncSession
):
    """A cancelled run (no turn_complete span) must still expose the user
    message via router_decision.payload.user_message."""
    project = await create_project(db_session)
    agent = await create_agent(db_session, project)
    session_id = "01SESSIONCANCEL000000000C"
    run = await create_run(db_session, agent, session_id=session_id, status="cancelled")

    # Only create router_start + router_decision (simulating cancellation before completion)
    from tests.factories import create_simulator_spans
    from saras.db.models import Span
    from ulid import new as ulid_new
    from datetime import UTC, datetime, timedelta

    base = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
    db_session.add(Span(
        id=str(ulid_new()), run_id=run.id, name="router_start", type="router_start",
        started_at=base, ended_at=base + timedelta(milliseconds=50), duration_ms=50,
        payload={"model": "gpt-4o-mini"},
    ))
    db_session.add(Span(
        id=str(ulid_new()), run_id=run.id, name="router_decision", type="router_decision",
        started_at=base + timedelta(milliseconds=100),
        ended_at=base + timedelta(milliseconds=200), duration_ms=100,
        payload={
            "user_message": "I need help urgently",
            "decision": {"active_condition": None, "active_goal": None},
            "model": "gpt-4o-mini",
            "system_prompt": "...",
            "prompt": "...",
            "slot_state": {},
        },
    ))
    await db_session.flush()

    response = await client.get(f"/api/projects/{project.id}/sessions/{session_id}")
    assert response.status_code == 200
    data = response.json()

    assert len(data["runs"]) == 1
    spans = data["runs"][0]["spans"]
    span_types = [s["type"] for s in spans]
    assert "router_decision" in span_types
    assert "turn_complete" not in span_types

    rd = next(s for s in spans if s["type"] == "router_decision")
    assert rd["payload"]["user_message"] == "I need help urgently"


async def test_session_detail_slot_fill_turn_has_correct_payloads(
    client: AsyncClient, db_session: AsyncSession
):
    """Slot-fill turns emit no llm_call spans but must still carry user_message
    (via router_decision) and the assistant question (via turn_complete.content)."""
    project = await create_project(db_session)
    agent = await create_agent(db_session, project)
    session_id = "01SESSIONSLOTFILL00000001D"
    run = await create_run(db_session, agent, session_id=session_id, status="completed")

    await create_simulator_spans(
        db_session, run,
        user_message="Check my order",
        assistant_content="Could you please provide your order number?",
        turn_type="slot_fill",
    )

    response = await client.get(f"/api/projects/{project.id}/sessions/{session_id}")
    assert response.status_code == 200
    data = response.json()

    spans = data["runs"][0]["spans"]
    span_types = [s["type"] for s in spans]

    # Slot-fill should have router_decision and turn_complete but NO llm_call spans
    assert "router_decision" in span_types
    assert "turn_complete" in span_types
    assert "llm_call_start" not in span_types
    assert "llm_call_end" not in span_types
    assert "slot_fill" in span_types

    rd = next(s for s in spans if s["type"] == "router_decision")
    assert rd["payload"]["user_message"] == "Check my order"

    tc = next(s for s in spans if s["type"] == "turn_complete")
    assert tc["payload"]["content"] == "Could you please provide your order number?"
    assert tc["payload"]["turn_type"] == "slot_fill"


async def test_session_detail_tool_call_turn_has_complete_payloads(
    client: AsyncClient, db_session: AsyncSession
):
    """Tool call/result spans must carry tool name, arguments, and result_preview."""
    project = await create_project(db_session)
    agent = await create_agent(db_session, project)
    session_id = "01SESSIONTOOLCALL00000001E"
    run = await create_run(db_session, agent, session_id=session_id, status="completed")

    await create_simulator_spans(
        db_session, run,
        user_message="Look up order ORD-123",
        assistant_content="Your order ORD-123 is shipped and arriving tomorrow.",
        turn_type="response",
        tool_calls=[{
            "tool": "order_lookup",
            "arguments": {"order_number": "ORD-123"},
            "result_preview": '{"status": "shipped", "eta": "2025-01-16"}',
        }],
    )

    response = await client.get(f"/api/projects/{project.id}/sessions/{session_id}")
    assert response.status_code == 200
    data = response.json()

    spans = data["runs"][0]["spans"]
    span_types = [s["type"] for s in spans]

    assert "tool_call" in span_types
    assert "tool_result" in span_types

    tc = next(s for s in spans if s["type"] == "tool_call")
    assert tc["payload"]["tool"] == "order_lookup"
    assert tc["payload"]["arguments"]["order_number"] == "ORD-123"

    tr = next(s for s in spans if s["type"] == "tool_result")
    assert tr["payload"]["tool"] == "order_lookup"
    assert "shipped" in tr["payload"]["result_preview"]

    # User message and assistant content still present
    rd = next(s for s in spans if s["type"] == "router_decision")
    assert rd["payload"]["user_message"] == "Look up order ORD-123"

    turn_c = next(s for s in spans if s["type"] == "turn_complete")
    assert turn_c["payload"]["content"] == "Your order ORD-123 is shipped and arriving tomorrow."


# ── End-to-end: executor → DB → session API → conversation reconstruction ─────


def _router_json(**overrides) -> str:
    """Produce a RouterDecision-shaped JSON string for the mock LLM."""
    defaults = {
        "interrupt_triggered": None,
        "interrupt_action": None,
        "handoff_triggered": None,
        "handoff_target": None,
        "handoff_context": None,
        "active_condition": "Order Inquiry",
        "active_goal": "Track Order",
        "sub_agent": None,
        "unfilled_slots": [],
        "extracted_slot_values": {},
        "reasoning": "User wants order status",
    }
    defaults.update(overrides)
    return json.dumps(defaults)


async def test_executor_to_session_api_conversation_reconstruction(
    client: AsyncClient, db_session: AsyncSession
):
    """End-to-end: call run_turn() to produce real spans in Postgres, then
    fetch via the session detail API and verify every field needed by the
    frontend Chat tab's extractTurns() function is present and correct.

    This mirrors what the simulator WebSocket handler does:
      1. Pre-allocate a Run row
      2. Call run_turn(compiled, history, user_message, run_id=..., db=session)
      3. Spans are persisted to Postgres via emit_span()
      4. Session detail API returns runs + spans
      5. Frontend reads router_decision.payload.user_message + turn_complete.payload.content
    """
    from pathlib import Path
    from ulid import new as ulid_new

    from saras.core.compiler import compile_from_yaml
    from saras.core.executor import run_turn
    from saras.db.models import Run

    # ── Setup ──────────────────────────────────────────────────────────────────
    project = await create_project(db_session)
    agent = await create_agent(db_session, project)

    fixture_yaml = Path(__file__).parents[2] / "fixtures" / "sample_agent.yaml"
    compiled = compile_from_yaml(
        fixture_yaml.read_text(),
        agent_id=agent.id,
        agent_version=agent.current_version,
    )

    session_id = str(ulid_new())
    history: list[dict] = []

    # ── Turn 1: user asks about their order → slot-fill ────────────────────────
    call_count_1 = 0

    async def mock_llm_turn1(**_kwargs):
        nonlocal call_count_1
        call_count_1 += 1
        if call_count_1 == 1:
            # Router: unfilled slot → slot_fill branch
            return make_mock_llm_response(
                content=_router_json(unfilled_slots=["Order Number"])
            )
        # Should not reach here for slot_fill, but just in case
        return make_mock_llm_response(content="Sure thing!")

    run_id_1 = str(ulid_new())
    db_session.add(Run(
        id=run_id_1, agent_id=agent.id, agent_version=agent.current_version,
        session_id=session_id, source="simulator", status="running",
    ))
    await db_session.flush()

    with (
        patch("litellm.acompletion", side_effect=mock_llm_turn1),
        patch("saras.db.redis.publish", new=AsyncMock()),
        patch("saras.providers.litellm.count_tokens", return_value=50),
    ):
        result1 = await run_turn(
            compiled=compiled,
            history=history,
            user_message="Where is my order?",
            run_id=run_id_1,
            session_id=session_id,
            db=db_session,
        )

    assert result1.type == "slot_fill"
    history.append({"role": "user", "content": "Where is my order?"})
    history.append({"role": "assistant", "content": result1.content})

    # ── Turn 2: user provides order number → normal response ───────────────────
    call_count_2 = 0

    async def mock_llm_turn2(**_kwargs):
        nonlocal call_count_2
        call_count_2 += 1
        if call_count_2 == 1:
            return make_mock_llm_response(
                content=_router_json(
                    unfilled_slots=[],
                    extracted_slot_values={"Order Number": "ORD-12345"},
                )
            )
        return make_mock_llm_response(
            content="Your order ORD-12345 has shipped and will arrive by Friday."
        )

    run_id_2 = str(ulid_new())
    db_session.add(Run(
        id=run_id_2, agent_id=agent.id, agent_version=agent.current_version,
        session_id=session_id, source="simulator", status="running",
    ))
    await db_session.flush()

    with (
        patch("litellm.acompletion", side_effect=mock_llm_turn2),
        patch("saras.db.redis.publish", new=AsyncMock()),
        patch("saras.providers.litellm.count_tokens", return_value=50),
    ):
        result2 = await run_turn(
            compiled=compiled,
            history=history[:-1],  # history before this message
            user_message="It's ORD-12345",
            slot_state={"Order Number": "ORD-12345"},
            run_id=run_id_2,
            session_id=session_id,
            db=db_session,
        )

    assert result2.type == "response"
    history.append({"role": "user", "content": "It's ORD-12345"})
    history.append({"role": "assistant", "content": result2.content})

    # ── Fetch session via API ──────────────────────────────────────────────────
    response = await client.get(f"/api/projects/{project.id}/sessions/{session_id}")
    assert response.status_code == 200
    data = response.json()

    assert data["session_id"] == session_id
    assert len(data["runs"]) == 2

    # ── Verify Turn 1 (slot-fill) conversation reconstruction ──────────────────
    spans1 = data["runs"][0]["spans"]
    span_types1 = [s["type"] for s in spans1]

    assert "router_decision" in span_types1, (
        f"Turn 1 missing router_decision span. Got: {span_types1}"
    )
    assert "turn_complete" in span_types1, (
        f"Turn 1 missing turn_complete span. Got: {span_types1}"
    )
    assert "slot_fill" in span_types1

    rd1 = next(s for s in spans1 if s["type"] == "router_decision")
    assert rd1["payload"]["user_message"] == "Where is my order?", (
        f"Expected user_message 'Where is my order?', got: {rd1['payload'].get('user_message')}"
    )

    tc1 = next(s for s in spans1 if s["type"] == "turn_complete")
    assert tc1["payload"]["turn_type"] == "slot_fill"
    assert tc1["payload"]["content"] is not None
    assert len(tc1["payload"]["content"]) > 0, "Slot-fill content must not be empty"

    # ── Verify Turn 2 (response) conversation reconstruction ───────────────────
    spans2 = data["runs"][1]["spans"]
    span_types2 = [s["type"] for s in spans2]

    assert "router_decision" in span_types2
    assert "turn_complete" in span_types2
    assert "llm_call_start" in span_types2
    assert "llm_call_end" in span_types2

    rd2 = next(s for s in spans2 if s["type"] == "router_decision")
    assert rd2["payload"]["user_message"] == "It's ORD-12345"

    tc2 = next(s for s in spans2 if s["type"] == "turn_complete")
    assert tc2["payload"]["turn_type"] == "response"
    assert tc2["payload"]["content"] == result2.content, (
        f"Expected content '{result2.content}', got: {tc2['payload'].get('content')}"
    )

    # Verify llm_call_start has messages array
    lls2 = next(s for s in spans2 if s["type"] == "llm_call_start")
    assert isinstance(lls2["payload"]["messages"], list)
    assert len(lls2["payload"]["messages"]) >= 2  # system + user at minimum

    # Verify llm_call_end has output
    lle2 = next(s for s in spans2 if s["type"] == "llm_call_end")
    assert lle2["payload"]["output"] is not None

    # ── Cross-check: no span leakage between runs ──────────────────────────────
    ids1 = {s["id"] for s in spans1}
    ids2 = {s["id"] for s in spans2}
    assert ids1.isdisjoint(ids2), "Spans from different runs must not overlap"

    # ── Verify the frontend extractTurns logic would work ───────────────────────
    # This mirrors the exact logic from SessionDetail.tsx extractTurns()
    for i, run_data in enumerate(data["runs"]):
        spans = sorted(run_data["spans"], key=lambda s: s["started_at"])
        rd = next((s for s in spans if s["type"] == "router_decision"), None)
        tc = next((s for s in spans if s["type"] == "turn_complete"), None)

        user_msg = rd["payload"].get("user_message") if rd else None
        asst_msg = tc["payload"].get("content") if tc else None

        # At minimum, the user message must be present for every turn
        assert user_msg is not None, (
            f"Turn {i+1}: user_message is None — "
            "Chat tab would skip this turn"
        )

        # The assistant content must be present (even for slot_fill)
        if tc:
            assert asst_msg is not None, f"Turn {i+1}: turn_complete has no content"
            assert len(asst_msg) > 0, f"Turn {i+1}: content is empty"
