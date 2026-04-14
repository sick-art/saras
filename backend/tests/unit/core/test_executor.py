"""Unit tests for saras.core.executor — run_turn() with mocked LLM."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from saras.core.compiler import compile_from_yaml
from saras.core.executor import RouterDecision, TurnResult, _build_router_prompt, _snake

FIXTURE_YAML = Path(__file__).parents[2] / "fixtures" / "sample_agent.yaml"


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_compiled():
    return compile_from_yaml(FIXTURE_YAML.read_text(), agent_id="agent-1")


def make_mock_raw(content: str, tool_calls=None):
    choice = MagicMock()
    choice.message.content = content
    choice.message.tool_calls = tool_calls
    choice.finish_reason = "stop"
    usage = MagicMock()
    usage.prompt_tokens = 100
    usage.completion_tokens = 50
    raw = MagicMock()
    raw.choices = [choice]
    raw.usage = usage
    return raw


def router_json(**overrides) -> str:
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


# ── run_turn: standard response ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_turn_returns_response():
    """Standard turn: router decision → primary model call → TurnResult."""
    compiled = get_compiled()
    call_count = 0

    async def mock_completion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_mock_raw(router_json())
        return make_mock_raw("Your order ORD-123 is on its way!")

    with patch("litellm.acompletion", side_effect=mock_completion):
        with patch("saras.db.redis.publish", new=AsyncMock()):
            from saras.core.executor import run_turn

            result = await run_turn(
                compiled=compiled,
                history=[],
                user_message="Where is my order?",
            )

    assert isinstance(result, TurnResult)
    assert result.type == "response"
    assert result.content == "Your order ORD-123 is on its way!"
    assert call_count == 2  # router + primary


# ── run_turn: slot fill path ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_turn_slot_fill():
    """When router returns unfilled_slots, run_turn returns type=slot_fill."""
    compiled = get_compiled()
    call_count = 0

    async def mock_completion(**kwargs):
        nonlocal call_count
        call_count += 1
        return make_mock_raw(router_json(unfilled_slots=["Order Number"]))

    with patch("litellm.acompletion", side_effect=mock_completion):
        with patch("saras.db.redis.publish", new=AsyncMock()):
            from saras.core.executor import run_turn

            result = await run_turn(
                compiled=compiled,
                history=[],
                user_message="Where is my order?",
            )

    assert result.type == "slot_fill"
    assert "order number" in result.content.lower()
    assert call_count == 1  # only router called; primary skipped


# ── run_turn: interrupt triggered ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_turn_interrupt_triggered():
    """When router fires an interrupt, run_turn returns type=interrupt."""
    compiled = get_compiled()
    call_count = 0

    async def mock_completion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_mock_raw(router_json(
                interrupt_triggered="Emergency Override",
                interrupt_action="Provide emergency services info.",
            ))
        return make_mock_raw("Please call emergency services immediately.")

    with patch("litellm.acompletion", side_effect=mock_completion):
        with patch("saras.db.redis.publish", new=AsyncMock()):
            from saras.core.executor import run_turn

            result = await run_turn(
                compiled=compiled,
                history=[],
                user_message="I think I'm having a medical emergency.",
            )

    assert result.type == "interrupt"
    assert result.router_decision is not None
    assert result.router_decision.interrupt_triggered == "Emergency Override"


# ── run_turn: handoff triggered ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_turn_handoff_triggered():
    """When router fires a handoff, run_turn returns type=handoff."""
    compiled = get_compiled()

    async def mock_completion(**kwargs):
        return make_mock_raw(router_json(
            handoff_triggered="Human Escalation",
            handoff_target="Human Support Queue",
            handoff_context="Customer has complex billing issue.",
        ))

    with patch("litellm.acompletion", side_effect=mock_completion):
        with patch("saras.db.redis.publish", new=AsyncMock()):
            from saras.core.executor import run_turn

            result = await run_turn(
                compiled=compiled,
                history=[],
                user_message="I want to talk to a human.",
            )

    assert result.type == "handoff"
    assert "Human Support Queue" in result.content
    assert result.router_decision.handoff_triggered == "Human Escalation"


# ── run_turn: router parse error fallback ─────────────────────────────────────

@pytest.mark.asyncio
async def test_run_turn_router_parse_error_falls_back():
    """If router returns invalid JSON, executor falls back to no routing."""
    compiled = get_compiled()
    call_count = 0

    async def mock_completion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_mock_raw("THIS IS NOT JSON")
        return make_mock_raw("I can help you with that.")

    with patch("litellm.acompletion", side_effect=mock_completion):
        with patch("saras.db.redis.publish", new=AsyncMock()):
            from saras.core.executor import run_turn

            result = await run_turn(
                compiled=compiled,
                history=[],
                user_message="Hello",
            )

    # Should not raise; falls back to empty RouterDecision → calls primary model
    assert isinstance(result, TurnResult)


# ── run_turn: slot state accumulation ────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_turn_confirmed_slots_not_re_asked():
    """Slots already in slot_state should be filtered from unfilled_slots."""
    compiled = get_compiled()

    # Router returns "Order Number" as unfilled, but slot_state already has it
    async def mock_completion(**kwargs):
        return make_mock_raw(router_json(
            unfilled_slots=["Order Number"],
            extracted_slot_values={},
        ))

    with patch("litellm.acompletion", side_effect=mock_completion):
        with patch("saras.db.redis.publish", new=AsyncMock()):
            from saras.core.executor import run_turn

            result = await run_turn(
                compiled=compiled,
                history=[],
                user_message="What is the status?",
                slot_state={"Order Number": "ORD-999"},  # already confirmed
            )

    # Since Order Number is already confirmed, unfilled_slots becomes []
    # → executor should proceed to primary model call, not slot fill
    # (router still returns unfilled, but executor filters confirmed ones out)
    assert result.router_decision is not None
    assert "Order Number" not in result.router_decision.unfilled_slots


# ── run_turn: spans emitted ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_turn_emits_spans():
    """run_turn should populate spans list on the result."""
    compiled = get_compiled()
    call_count = 0

    async def mock_completion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_mock_raw(router_json())
        return make_mock_raw("Here is your order status.")

    with patch("litellm.acompletion", side_effect=mock_completion):
        with patch("saras.db.redis.publish", new=AsyncMock()):
            from saras.core.executor import run_turn

            result = await run_turn(
                compiled=compiled,
                history=[],
                user_message="Order status please",
            )

    assert len(result.spans) > 0
    span_types = [s["span_type"] for s in result.spans]
    assert "router_start" in span_types
    assert "router_decision" in span_types


# ── _build_router_prompt ──────────────────────────────────────────────────────

def test_build_router_prompt_includes_user_message():
    compiled = get_compiled()
    prompt = _build_router_prompt(compiled, [], "Hello world")
    assert "Hello world" in prompt


def test_build_router_prompt_includes_slot_state():
    compiled = get_compiled()
    prompt = _build_router_prompt(
        compiled, [], "Order status", slot_state={"Order Number": "ORD-123"}
    )
    assert "ORD-123" in prompt
    assert "ALREADY CONFIRMED" in prompt


def test_build_router_prompt_includes_history():
    compiled = get_compiled()
    history = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello! How can I help?"},
    ]
    prompt = _build_router_prompt(compiled, history, "New message")
    assert "Hi" in prompt
    assert "How can I help" in prompt


# ── _snake helper ─────────────────────────────────────────────────────────────

def test_snake_lowercase():
    assert _snake("Order Lookup") == "order_lookup"


def test_snake_hyphen():
    assert _snake("my-tool") == "my_tool"
