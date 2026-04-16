"""Unit tests for saras.core.executor — run_turn() with mocked LLM."""

from __future__ import annotations

import asyncio
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


def make_mock_tool_call(tool_name: str, arguments: dict, call_id: str = "tc_1"):
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = tool_name
    tc.function.arguments = json.dumps(arguments)
    return tc


def make_mock_raw(content: str, tool_calls=None):
    choice = MagicMock()
    choice.message.content = content
    choice.message.tool_calls = tool_calls
    choice.finish_reason = "stop" if not tool_calls else "tool_calls"
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


@pytest.mark.asyncio
async def test_interrupt_path_reports_tokens_regression():
    """Regression guard: interrupt path previously dropped primary-call tokens
    via a dead _update_tokens helper. Tokens must be accumulated."""
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
        return make_mock_raw("Call 911 now.")

    with patch("litellm.acompletion", side_effect=mock_completion):
        with patch("saras.db.redis.publish", new=AsyncMock()):
            from saras.core.executor import run_turn

            result = await run_turn(
                compiled=compiled,
                history=[],
                user_message="emergency",
            )

    assert result.type == "interrupt"
    # Primary model reported 100/50; router count_tokens adds more.
    assert result.total_output_tokens >= 50
    assert result.total_input_tokens > 0


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


# ── run_turn: router parse + retry behaviour ──────────────────────────────────

@pytest.mark.asyncio
async def test_router_retries_on_invalid_json():
    """First response is garbage JSON; retry returns valid JSON. No parse-error span."""
    compiled = get_compiled()
    call_count = 0

    async def mock_completion(**kwargs):
        nonlocal call_count
        call_count += 1
        # call 1: router garbage. call 2: router retry valid. call 3: primary.
        if call_count == 1:
            return make_mock_raw("THIS IS NOT JSON")
        if call_count == 2:
            return make_mock_raw(router_json())
        return make_mock_raw("How can I help?")

    with patch("litellm.acompletion", side_effect=mock_completion):
        with patch("saras.db.redis.publish", new=AsyncMock()):
            from saras.core.executor import run_turn

            result = await run_turn(
                compiled=compiled,
                history=[],
                user_message="Hi",
            )

    assert isinstance(result, TurnResult)
    assert result.router_decision is not None
    assert result.router_decision.active_condition == "Order Inquiry"
    span_types = [s["span_type"] for s in result.spans]
    assert "router_parse_error" not in span_types
    assert call_count == 3  # router + retry + primary


@pytest.mark.asyncio
async def test_router_emits_parse_error_span_after_retry_exhausted():
    """Both router attempts fail → parse_error span + empty RouterDecision."""
    compiled = get_compiled()
    call_count = 0

    async def mock_completion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return make_mock_raw("still not json")
        return make_mock_raw("Generic reply.")

    with patch("litellm.acompletion", side_effect=mock_completion):
        with patch("saras.db.redis.publish", new=AsyncMock()):
            from saras.core.executor import run_turn

            result = await run_turn(
                compiled=compiled,
                history=[],
                user_message="Hi",
            )

    assert isinstance(result, TurnResult)
    span_types = [s["span_type"] for s in result.spans]
    assert "router_parse_error" in span_types
    # Fallback RouterDecision is all-None
    assert result.router_decision.active_condition is None


# ── run_turn: slot state accumulation ────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_turn_confirmed_slots_not_re_asked():
    """Slots already in slot_state should be filtered from unfilled_slots."""
    compiled = get_compiled()
    call_count = 0

    async def mock_completion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Router returns "Order Number" as unfilled; executor filters it out
            # because slot_state already has it.
            return make_mock_raw(router_json(
                unfilled_slots=["Order Number"],
                extracted_slot_values={},
            ))
        return make_mock_raw("Looks good.")

    with patch("litellm.acompletion", side_effect=mock_completion):
        with patch("saras.db.redis.publish", new=AsyncMock()):
            from saras.core.executor import run_turn

            result = await run_turn(
                compiled=compiled,
                history=[],
                user_message="What is the status?",
                slot_state={"Order Number": "ORD-999"},
            )

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


@pytest.mark.asyncio
async def test_router_decision_span_captures_user_message():
    """router_decision carries user_message so the Chat tab can reconstruct
    turns that emit no llm_call_* spans (slot_fill/interrupt/handoff)."""
    compiled = get_compiled()
    call_count = 0

    async def mock_completion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_mock_raw(router_json())
        return make_mock_raw("ok")

    with patch("litellm.acompletion", side_effect=mock_completion):
        with patch("saras.db.redis.publish", new=AsyncMock()):
            from saras.core.executor import run_turn

            result = await run_turn(
                compiled=compiled,
                history=[],
                user_message="where's my order",
            )

    rd = next(s for s in result.spans if s["span_type"] == "router_decision")
    assert rd["data"]["user_message"] == "where's my order"


@pytest.mark.asyncio
async def test_turn_complete_span_captures_content_and_type():
    """turn_complete includes content + turn_type for every branch — this is
    what the Chat tab reads as the authoritative assistant output."""
    compiled = get_compiled()
    call_count = 0

    async def mock_completion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_mock_raw(router_json())
        return make_mock_raw("Order is on its way.")

    with patch("litellm.acompletion", side_effect=mock_completion):
        with patch("saras.db.redis.publish", new=AsyncMock()):
            from saras.core.executor import run_turn

            result = await run_turn(
                compiled=compiled,
                history=[],
                user_message="status?",
            )

    tc = next(s for s in result.spans if s["span_type"] == "turn_complete")
    assert tc["data"]["content"] == "Order is on its way."
    assert tc["data"]["turn_type"] == "response"


@pytest.mark.asyncio
async def test_slot_fill_turn_complete_carries_question():
    """Slot-fill branch emits no llm_call_* spans; the chat tab relies on
    turn_complete.content for the assistant-visible question."""
    compiled = get_compiled()

    async def mock_completion(**kwargs):
        return make_mock_raw(router_json(unfilled_slots=["Order Number"]))

    with patch("litellm.acompletion", side_effect=mock_completion):
        with patch("saras.db.redis.publish", new=AsyncMock()):
            from saras.core.executor import run_turn

            result = await run_turn(
                compiled=compiled,
                history=[],
                user_message="check it",
            )

    tc = next(s for s in result.spans if s["span_type"] == "turn_complete")
    assert tc["data"]["turn_type"] == "slot_fill"
    assert tc["data"]["content"]  # non-empty question


@pytest.mark.asyncio
async def test_interrupt_path_emits_llm_spans():
    """Interrupt branch must emit llm_call_start/end so the Traces UI can
    render its prompt and response — previously it called chat_completion
    without wrapping spans, making interrupt turns disappear from the Chat tab."""
    compiled = get_compiled()
    call_count = 0

    async def mock_completion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_mock_raw(router_json(
                interrupt_triggered="Emergency Override",
                interrupt_action="Provide emergency info.",
            ))
        return make_mock_raw("Call 911 now.")

    with patch("litellm.acompletion", side_effect=mock_completion):
        with patch("saras.db.redis.publish", new=AsyncMock()):
            from saras.core.executor import run_turn

            result = await run_turn(
                compiled=compiled,
                history=[],
                user_message="help",
            )

    span_types = [s["span_type"] for s in result.spans]
    assert "llm_call_start" in span_types
    assert "llm_call_end" in span_types


@pytest.mark.asyncio
async def test_cancelled_turn_marks_run_cancelled():
    """When run_turn is cancelled mid-flight, the Run row must be marked
    'cancelled' (not left in 'running'). Without this the Traces UI showed
    sessions stuck on 'running' forever."""
    compiled = get_compiled()

    # Router returns, then primary call hangs until cancelled.
    call_count = 0

    async def mock_completion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_mock_raw(router_json())
        # Primary call — never returns; simulates a long-running LLM call
        await asyncio.sleep(10)
        return make_mock_raw("unreachable")

    # Minimal fake AsyncSession that records Run.status changes.
    class FakeSession:
        def __init__(self):
            self.run_row = None
            self.committed = False

        def add(self, obj):
            # Only keep Run instances around for status inspection
            if obj.__class__.__name__ == "Run":
                self.run_row = obj

        async def flush(self):
            pass

        async def commit(self):
            self.committed = True

        async def get(self, _model, _id):
            return self.run_row

    fake_db = FakeSession()

    with patch("litellm.acompletion", side_effect=mock_completion):
        with patch("saras.db.redis.publish", new=AsyncMock()):
            from saras.core.executor import run_turn

            task = asyncio.create_task(run_turn(
                compiled=compiled,
                history=[],
                user_message="slow",
                db=fake_db,  # type: ignore[arg-type]
            ))
            # Give the task a chance to start the primary (mock) call, then cancel.
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    assert fake_db.run_row is not None
    assert fake_db.run_row.status == "cancelled"
    assert fake_db.committed is True


@pytest.mark.asyncio
async def test_router_decision_span_captures_system_prompt():
    """router_decision span payload includes both system_prompt and user prompt."""
    compiled = get_compiled()
    call_count = 0

    async def mock_completion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_mock_raw(router_json())
        return make_mock_raw("ok")

    with patch("litellm.acompletion", side_effect=mock_completion):
        with patch("saras.db.redis.publish", new=AsyncMock()):
            from saras.core.executor import run_turn

            result = await run_turn(
                compiled=compiled,
                history=[],
                user_message="hey",
            )

    rd = next(s for s in result.spans if s["span_type"] == "router_decision")
    assert "system_prompt" in rd["data"]
    assert "prompt" in rd["data"]
    assert "routing assistant" in rd["data"]["system_prompt"].lower()


@pytest.mark.asyncio
async def test_llm_call_start_span_captures_system_prompt():
    """llm_call_start span payload has an explicit system_prompt field."""
    compiled = get_compiled()
    call_count = 0

    async def mock_completion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_mock_raw(router_json())
        return make_mock_raw("ok")

    with patch("litellm.acompletion", side_effect=mock_completion):
        with patch("saras.db.redis.publish", new=AsyncMock()):
            from saras.core.executor import run_turn

            result = await run_turn(
                compiled=compiled,
                history=[],
                user_message="hey",
            )

    lls = next(s for s in result.spans if s["span_type"] == "llm_call_start")
    assert "system_prompt" in lls["data"]
    assert isinstance(lls["data"]["system_prompt"], str)


# ── run_turn: tool error path ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tool_error_emits_span_and_continues():
    """If _execute_tool raises, a tool_error span is emitted and the model
    receives a JSON error payload so it can recover."""
    compiled = get_compiled()
    call_count = 0

    async def mock_completion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_mock_raw(router_json())
        if call_count == 2:
            return make_mock_raw(
                "",
                tool_calls=[make_mock_tool_call("order_lookup", {"id": "x"})],
            )
        return make_mock_raw("I couldn't fetch that; can you try again?")

    async def raising_tool(name, args, compiled):
        raise RuntimeError("tool exploded")

    with patch("litellm.acompletion", side_effect=mock_completion):
        with patch("saras.db.redis.publish", new=AsyncMock()):
            with patch("saras.core.executor._execute_tool", side_effect=raising_tool):
                from saras.core.executor import run_turn

                result = await run_turn(
                    compiled=compiled,
                    history=[],
                    user_message="look up my order",
                )

    span_types = [s["span_type"] for s in result.spans]
    assert "tool_error" in span_types
    # Follow-up LLM call should still happen
    assert result.type == "response"
    assert result.content


# ── run_turn: tool loop exceeded ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tool_loop_exceeded_emits_span():
    """Model that keeps calling tools forever hits MAX_TOOL_ITERATIONS and emits
    a tool_loop_exceeded span. final_content prefers the last non-empty text."""
    compiled = get_compiled()
    call_count = 0

    async def mock_completion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_mock_raw(router_json())
        # Always ask for a tool; include a last-ditch text so final_content uses it
        return make_mock_raw(
            "still working...",
            tool_calls=[make_mock_tool_call("order_lookup", {"id": "x"}, call_id=f"tc_{call_count}")],
        )

    async def mock_tool(name, args, compiled):
        return json.dumps({"status": "ok"})

    with patch("litellm.acompletion", side_effect=mock_completion):
        with patch("saras.db.redis.publish", new=AsyncMock()):
            with patch("saras.core.executor._execute_tool", side_effect=mock_tool):
                from saras.core.executor import run_turn

                result = await run_turn(
                    compiled=compiled,
                    history=[],
                    user_message="go",
                )

    span_types = [s["span_type"] for s in result.spans]
    assert "tool_loop_exceeded" in span_types
    assert result.content == "still working..."


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
