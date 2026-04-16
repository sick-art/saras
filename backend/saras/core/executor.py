"""
Agent Turn Execution Engine.

run_turn(compiled, history, message) → TurnResult

Execution steps per turn:
1. Router model call → RouterDecision
   - Which interrupt trigger fired (if any)
   - Which handoff to invoke (if any)
   - Active condition + goal
   - Unfilled required slots (from goal's slot definitions)

2. Slot fill loop
   - If required slots are missing, return a slot-fill question instead of running the main model.

3. Assemble augmented system prompt from context layers
   - Layer 1 always included
   - Layers 2–6 injected based on RouterDecision
   - Layer 7 (tool results) injected inline during tool loop
   - Layer 8 (memory) reserved for future use

4. Primary model call with tool execution loop
   - Call primary model with assembled prompt + tools for active goal
   - If model requests tool calls: mock-execute them (real execution wired in Phase 3),
     append tool results, call model again (max 5 tool iterations)

5. Emit Redis span events
   - Every sub-step (router call, slot fill, llm call, tool call) emits a span event
     to the agent's Redis channel for WebSocket fan-out in the simulator

6. Persist Run + Spans to Postgres (when run_id provided)

Sub-agent delegation:
   - If RouterDecision.sub_agent is set, invoke run_turn recursively with isolated context.
   - Root synthesises the sub-agent result.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import new as ulid_new

from saras.core.schema import AgentTool, CompiledAgent, ContextLayer
from saras.db.models import Run, Span
from saras.db.redis import publish
from saras.providers.litellm import (
    LLMResponse,
    chat_completion,
    count_tokens,
    estimate_cost,
)

log = structlog.get_logger()

# Maximum tool-call iterations per primary model call before stopping
MAX_TOOL_ITERATIONS = 5

# Sampling temperature for the primary model. Low but non-zero so the model has
# a little room to rephrase while still following rules deterministically.
PRIMARY_TEMPERATURE = 0.3


# ── Decision models ────────────────────────────────────────────────────────────

class RouterDecision(BaseModel):
    """Output of the router model call."""
    interrupt_triggered: str | None = None          # Interrupt trigger name, if fired
    interrupt_action: str | None = None             # Action description
    handoff_triggered: str | None = None            # Handoff name, if triggered
    handoff_target: str | None = None               # Transfer target
    handoff_context: str | None = None              # Context to pass
    active_condition: str | None = None             # Active condition name
    active_goal: str | None = None                  # Active goal name
    sub_agent: str | None = None                    # Sub-agent name to delegate to
    unfilled_slots: list[str] = []                  # Required slot names not yet filled
    extracted_slot_values: dict[str, str] = {}      # Slot values extracted from the user message
    reasoning: str | None = None                    # Router's brief reasoning (for tracing)


class SlotFillResult(BaseModel):
    """Returned when the agent needs to ask a slot-fill question."""
    type: str = "slot_fill"
    question: str
    slot_name: str


class TurnResult(BaseModel):
    """Final output of a completed turn."""
    type: str = "response"                          # "response" | "slot_fill" | "interrupt" | "handoff"
    content: str                                    # Agent's text response
    router_decision: RouterDecision | None = None
    tool_calls_made: list[dict] = []
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    run_id: str | None = None
    spans: list[dict] = []
    slot_state: dict[str, str] = {}                 # Accumulated confirmed slot values for this session


# ── Router prompt ──────────────────────────────────────────────────────────────

_ROUTER_SYSTEM = """\
You are a routing assistant. Given the agent's configuration and the current conversation,
your job is to analyse the situation and return a JSON routing decision.

You must return ONLY a JSON object with these fields:
{
  "interrupt_triggered": "<trigger name or null>",
  "interrupt_action": "<action description or null>",
  "handoff_triggered": "<handoff name or null>",
  "handoff_target": "<target name or null>",
  "handoff_context": "<what context to pass or null>",
  "active_condition": "<condition name or null>",
  "active_goal": "<goal name or null>",
  "sub_agent": "<sub-agent name or null>",
  "unfilled_slots": ["<slot name>", ...],
  "extracted_slot_values": {"<slot name>": "<extracted value>"},
  "reasoning": "<one sentence about your decision>"
}

Rules:
- Check interrupt triggers FIRST. If one fires, set interrupt_triggered and stop.
- Check handoffs SECOND. If one fires, set handoff_triggered and stop.
- Then pick the single most relevant condition + goal for the user's message.
- ALREADY CONFIRMED SLOTS are listed in the prompt — treat those as filled and NEVER include them in unfilled_slots.
- For the active goal, scan the ENTIRE conversation history (not just the latest message) for slot values.
  Extract any slot values mentioned anywhere in the conversation, even if expressed naturally or indirectly
  (e.g. "flying from toronto to paris" fills "Origin Airport"="Toronto" and "Destination Airport"="Paris";
   "it's just me travelling" fills "Passenger Count"="1"; "next Friday" fills "Departure Date" with the date).
  Put ALL found values in extracted_slot_values.
- In unfilled_slots, list ONLY required slots where you genuinely cannot find the value anywhere in the
  conversation history OR in ALREADY CONFIRMED SLOTS. If you can infer a slot from context, extract it.
- If no condition applies, set both active_condition and active_goal to null.
- NEVER invent condition or goal names — use exact names from the configuration.
- Return only valid JSON, nothing else.
"""

def _build_router_prompt(
    compiled: CompiledAgent,
    history: list[dict],
    user_message: str,
    slot_state: dict[str, str] | None = None,
) -> str:
    """Build the user message for the router model."""
    ctx = compiled.routing_context

    lines = ["=== AGENT ROUTING CONFIGURATION ===\n"]

    if ctx.interrupt_triggers:
        lines.append("INTERRUPT TRIGGERS (checked first):")
        for t in ctx.interrupt_triggers:
            lines.append(f"  - {t['name']}: {t['description']}")
            if t.get("action"):
                lines.append(f"    Action: {t['action']}")
        lines.append("")

    if ctx.handoffs:
        lines.append("HANDOFFS (checked second):")
        for h in ctx.handoffs:
            lines.append(f"  - {h['name']}: {h['description']} → {h['target']}")
        lines.append("")

    if ctx.conditions:
        lines.append("CONDITIONS AND GOALS:")
        for c in ctx.conditions:
            lines.append(f"  Condition: {c['name']} — {c['description']}")
            for g in ctx.goals_by_condition.get(c["name"], []):
                slot_info = f" [needs slots: {', '.join(g['tool_names'])}]" if g.get("has_slots") else ""
                lines.append(f"    Goal: {g['name']} — {g['description']}{slot_info}")
        lines.append("")

    # Slot definitions for all goals so router can check what's unfilled
    slot_registry: dict[str, list[dict]] = {}
    for condition in compiled.schema_.conditions:
        for goal in condition.goals:
            if goal.slots:
                slot_registry[goal.name] = [
                    {"name": s.name, "required": s.required, "ask_if_missing": s.ask_if_missing}
                    for s in goal.slots
                ]
    if slot_registry:
        lines.append("SLOT DEFINITIONS PER GOAL:")
        for goal_name, slots in slot_registry.items():
            lines.append(f"  {goal_name}:")
            for s in slots:
                lines.append(f"    - {s['name']} (required={s['required']})")
        lines.append("")

    # Already confirmed slot values (do not re-ask for these)
    if slot_state:
        lines.append("ALREADY CONFIRMED SLOTS (do NOT include these in unfilled_slots):")
        for slot_name, slot_value in slot_state.items():
            lines.append(f"  - {slot_name}: {slot_value}")
        lines.append("")

    # Recent conversation context (last 6 messages)
    if history:
        lines.append("RECENT CONVERSATION (last 6 turns):")
        for msg in history[-6:]:
            role = msg.get("role", "user").upper()
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    block.get("text", "") for block in content if isinstance(block, dict)
                )
            lines.append(f"  {role}: {content[:300]}")
        lines.append("")

    lines.append(f"NEW USER MESSAGE: {user_message}")
    lines.append(
        "\nIMPORTANT: Before marking any slot as unfilled, scan every turn in RECENT CONVERSATION "
        "above. If the user has already provided that information in any form, extract it now."
    )

    return "\n".join(lines)


# ── Context assembly ───────────────────────────────────────────────────────────

def _assemble_system_prompt(compiled: CompiledAgent, decision: RouterDecision) -> str:
    """
    Build the full system prompt for the primary model call.
    Layer 1 always injected. Layers 2–6 injected per routing decision.
    """
    parts: list[str] = []

    def _layer(label: str) -> ContextLayer | None:
        return next((l for l in compiled.context_layers if l.label == label), None)

    # Layer 1 — always
    base = _layer("base")
    if base:
        parts.append(base.content)

    if decision.interrupt_triggered:
        trigger = next(
            (t for t in compiled.schema_.interrupt_triggers
             if t.name == decision.interrupt_triggered),
            None,
        )
        if trigger and trigger.action:
            parts.append(f"EMERGENCY OVERRIDE — {trigger.name}:\n{trigger.action}")
        return "\n\n".join(parts)

    if decision.handoff_triggered:
        handoff = next(
            (h for h in compiled.schema_.handoffs if h.name == decision.handoff_triggered),
            None,
        )
        if handoff:
            ctx_note = f" Pass this context: {handoff.context_to_pass}" if handoff.context_to_pass else ""
            parts.append(
                f"HANDOFF REQUIRED — transfer this conversation to: {handoff.target}.{ctx_note}"
            )
        return "\n\n".join(parts)

    # Layer 2 — condition context
    if decision.active_condition:
        layer2 = _layer(f"condition:{decision.active_condition}")
        if layer2:
            parts.append(layer2.content)

    # Layer 3 — goal context
    if decision.active_condition and decision.active_goal:
        layer3 = _layer(f"goal:{decision.active_condition}:{decision.active_goal}")
        if layer3:
            parts.append(layer3.content)

        # Layer 5 — sequence steps (inject all sequences for active goal)
        condition = next(
            (c for c in compiled.schema_.conditions if c.name == decision.active_condition),
            None,
        )
        if condition:
            goal = next((g for g in condition.goals if g.name == decision.active_goal), None)
            if goal:
                for seq in goal.sequences:
                    layer5 = _layer(
                        f"sequence:{decision.active_condition}:{decision.active_goal}:{seq.name}"
                    )
                    if layer5:
                        parts.append(layer5.content)

        # Layer 6 — goal rules + scoped tool descriptions
        layer6 = _layer(f"goal_rules_tools:{decision.active_condition}:{decision.active_goal}")
        if layer6:
            parts.append(layer6.content)

    return "\n\n".join(parts)


# ── Tool execution (mock for Phase 2; real HTTP in Phase 3) ───────────────────

async def _execute_tool(tool_name: str, arguments: dict, compiled: CompiledAgent) -> str:
    """
    Execute a tool call. Phase 2: deterministic, realistic mock payload generated
    by Python (faker + heuristics).
    Phase 3: will route to the tool's endpoint via HTTP.
    """
    tool = next((t for t in compiled.schema_.tools if _snake(t.name) == tool_name), None)
    if tool is None:
        return json.dumps({"error": f"Tool '{tool_name}' not found in agent definition"})

    log.info("executor.tool_mock", tool=tool_name, args=arguments)
    payload = _mock_tool_payload(tool, arguments)
    return json.dumps(payload, default=str)


def _mock_tool_payload(tool: AgentTool, arguments: dict) -> dict:
    """
    Build a realistic mock response for a tool call. Deterministic for a given
    (tool name, arguments) pair so repeated calls return the same payload.

    Shape depends on tool type:
      - LookupTool  → record-shaped object inferred from tool/input names
      - KnowledgeTool → results[] with title/snippet/source/score
      - ActionTool  → success envelope with a generated confirmation id
    """
    from faker import Faker

    seed = f"{tool.name}|{json.dumps(arguments, sort_keys=True, default=str)}"
    fake = Faker()
    Faker.seed(abs(hash(seed)) % (2**31))

    if tool.type == "KnowledgeTool":
        return _mock_knowledge_results(tool, arguments, fake)
    if tool.type == "ActionTool":
        return _mock_action_result(tool, arguments, fake)
    return _mock_lookup_record(tool, arguments, fake)


def _mock_lookup_record(tool: AgentTool, arguments: dict, fake) -> dict:
    """Build a realistic record payload for a LookupTool based on keyword
    heuristics over the tool name and input names."""
    name_lc = tool.name.lower()
    record: dict = {"found": True}

    # Echo all provided arguments under their original keys so the model can
    # reason about what was looked up.
    for key, value in arguments.items():
        record[key] = value

    if "order" in name_lc:
        record.update({
            "order_number": arguments.get("order_number")
                or arguments.get("order_id")
                or f"ORD-{fake.random_int(10000, 99999)}",
            "status": fake.random_element([
                "processing", "shipped", "out_for_delivery", "delivered", "returned"
            ]),
            "placed_at": fake.date_time_between(start_date="-30d").isoformat(),
            "estimated_delivery": fake.date_between(start_date="+1d", end_date="+7d").isoformat(),
            "tracking_number": f"1Z{fake.bothify('??#########').upper()}",
            "carrier": fake.random_element(["UPS", "FedEx", "USPS", "DHL"]),
            "customer": {
                "name": fake.name(),
                "email": arguments.get("customer_email") or fake.email(),
            },
            "items": [
                {
                    "sku": f"SKU-{fake.random_int(1000, 9999)}",
                    "name": fake.catch_phrase(),
                    "quantity": fake.random_int(1, 3),
                    "price": round(fake.pyfloat(min_value=10, max_value=200), 2),
                }
                for _ in range(fake.random_int(1, 3))
            ],
            "subtotal": round(fake.pyfloat(min_value=20, max_value=400), 2),
            "shipping_address": {
                "line1": fake.street_address(),
                "city": fake.city(),
                "state": fake.state_abbr(),
                "postal_code": fake.postcode(),
                "country": "US",
            },
        })
    elif "customer" in name_lc or "user" in name_lc or "account" in name_lc:
        record.update({
            "customer_id": arguments.get("customer_id") or f"CUST-{fake.random_int(10000, 99999)}",
            "name": fake.name(),
            "email": arguments.get("email") or fake.email(),
            "phone": fake.phone_number(),
            "created_at": fake.date_time_between(start_date="-2y").isoformat(),
            "tier": fake.random_element(["standard", "silver", "gold", "platinum"]),
            "lifetime_value": round(fake.pyfloat(min_value=50, max_value=5000), 2),
            "open_tickets": fake.random_int(0, 3),
        })
    elif "product" in name_lc or "inventory" in name_lc or "sku" in name_lc:
        record.update({
            "sku": arguments.get("sku") or f"SKU-{fake.random_int(1000, 9999)}",
            "name": fake.catch_phrase(),
            "description": fake.sentence(nb_words=12),
            "price": round(fake.pyfloat(min_value=5, max_value=500), 2),
            "currency": "USD",
            "in_stock": fake.boolean(chance_of_getting_true=80),
            "stock_level": fake.random_int(0, 250),
            "category": fake.random_element(["apparel", "electronics", "home", "beauty", "sports"]),
        })
    elif "payment" in name_lc or "invoice" in name_lc or "transaction" in name_lc:
        record.update({
            "transaction_id": f"txn_{fake.uuid4()[:12]}",
            "amount": round(fake.pyfloat(min_value=5, max_value=800), 2),
            "currency": "USD",
            "status": fake.random_element(["succeeded", "pending", "refunded"]),
            "method": fake.random_element(["card", "paypal", "bank_transfer"]),
            "card_last4": fake.credit_card_number()[-4:],
            "processed_at": fake.date_time_between(start_date="-30d").isoformat(),
        })
    elif "shipment" in name_lc or "tracking" in name_lc or "delivery" in name_lc:
        record.update({
            "tracking_number": arguments.get("tracking_number")
                or f"1Z{fake.bothify('??#########').upper()}",
            "carrier": fake.random_element(["UPS", "FedEx", "USPS", "DHL"]),
            "status": fake.random_element(["in_transit", "out_for_delivery", "delivered"]),
            "last_update": fake.date_time_between(start_date="-3d").isoformat(),
            "last_location": f"{fake.city()}, {fake.state_abbr()}",
            "estimated_delivery": fake.date_between(start_date="+1d", end_date="+5d").isoformat(),
        })
    elif "reservation" in name_lc or "booking" in name_lc:
        record.update({
            "confirmation_code": fake.bothify("??######").upper(),
            "status": fake.random_element(["confirmed", "pending", "cancelled"]),
            "start_date": fake.date_between(start_date="+1d", end_date="+30d").isoformat(),
            "end_date": fake.date_between(start_date="+31d", end_date="+40d").isoformat(),
            "guests": fake.random_int(1, 4),
            "total": round(fake.pyfloat(min_value=100, max_value=2000), 2),
            "currency": "USD",
        })
    else:
        # Generic record — include some useful fields derived from inputs
        record.update({
            "id": f"rec_{fake.uuid4()[:12]}",
            "created_at": fake.date_time_between(start_date="-90d").isoformat(),
            "updated_at": fake.date_time_between(start_date="-7d").isoformat(),
            "status": "active",
        })

    return record


def _mock_knowledge_results(tool: AgentTool, arguments: dict, fake) -> dict:
    """Build a search-results payload for a KnowledgeTool."""
    query = (
        arguments.get("query")
        or arguments.get("question")
        or arguments.get("search")
        or next(iter(arguments.values()), None)
    )
    source_base = tool.source or tool.collection or "kb"
    count = fake.random_int(2, 4)
    results = []
    for _ in range(count):
        results.append({
            "title": fake.sentence(nb_words=6).rstrip("."),
            "snippet": " ".join(fake.paragraphs(nb=1)),
            "source": f"{source_base}/articles/{fake.slug()}",
            "score": round(fake.pyfloat(min_value=0.55, max_value=0.98), 2),
        })
    return {
        "query": query,
        "result_count": count,
        "results": sorted(results, key=lambda r: r["score"], reverse=True),
    }


def _mock_action_result(tool: AgentTool, arguments: dict, fake) -> dict:
    """Build a success-envelope payload for an ActionTool."""
    name_lc = tool.name.lower()
    if "refund" in name_lc:
        id_key, id_val = "refund_id", f"re_{fake.uuid4()[:12]}"
    elif "ticket" in name_lc:
        id_key, id_val = "ticket_id", f"TKT-{fake.random_int(10000, 99999)}"
    elif "cancel" in name_lc:
        id_key, id_val = "cancellation_id", f"can_{fake.uuid4()[:12]}"
    elif "book" in name_lc or "reserv" in name_lc:
        id_key, id_val = "confirmation_code", fake.bothify("??######").upper()
    elif "send" in name_lc or "email" in name_lc or "notify" in name_lc:
        id_key, id_val = "message_id", f"msg_{fake.uuid4()[:12]}"
    else:
        id_key, id_val = "confirmation_id", f"cnf_{fake.uuid4()[:12]}"

    return {
        "success": True,
        id_key: id_val,
        "completed_at": datetime.now(UTC).isoformat(),
        "arguments": arguments,
    }


def _snake(name: str) -> str:
    return name.lower().replace(" ", "_").replace("-", "_")


# ── Span helpers ───────────────────────────────────────────────────────────────

def _span_event(span_type: str, data: dict) -> dict:
    return {
        "type": "span",
        "span_type": span_type,
        "timestamp": datetime.now(UTC).isoformat(),
        "data": data,
    }


async def _emit(channel: str, event: dict) -> None:
    """Publish a span event to Redis for WebSocket fan-out."""
    try:
        await publish(channel, json.dumps(event))
    except Exception as e:
        log.warning("executor.redis_publish_error", error=str(e))


# ── Message serialization ──────────────────────────────────────────────────────

def _serialize_messages(messages: list[dict]) -> list[dict]:
    """
    Normalize the messages list into a clean, JSON-serializable form for
    storage in span payloads.  Handles all LiteLLM message shapes:
      - str content              → kept as-is
      - None content             → kept as None
      - list[block] content      → blocks cleaned to JSON-safe dicts
      - assistant + tool_calls   → tool_calls array preserved
      - role: "tool" messages    → content kept as string
    """
    out = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content")
        tool_calls = msg.get("tool_calls")

        if content is None:
            clean_content: Any = None
        elif isinstance(content, str):
            clean_content = content
        elif isinstance(content, list):
            clean_content = []
            for block in content:
                if isinstance(block, dict):
                    clean_content.append({
                        k: v for k, v in block.items()
                        if isinstance(v, (str, int, float, bool, dict, list, type(None)))
                    })
                else:
                    clean_content.append(str(block))
        else:
            clean_content = str(content)

        entry: dict[str, Any] = {"role": role, "content": clean_content}

        # Preserve tool_calls on assistant messages
        if tool_calls:
            entry["tool_calls"] = [
                {
                    "id": tc.get("id", ""),
                    "type": tc.get("type", "function"),
                    "function": {
                        "name": tc.get("function", {}).get("name", ""),
                        "arguments": tc.get("function", {}).get("arguments", "{}"),
                    },
                }
                for tc in tool_calls
                if isinstance(tc, dict)
            ]

        # Preserve tool_call_id on tool result messages
        if role == "tool" and "tool_call_id" in msg:
            entry["tool_call_id"] = msg["tool_call_id"]

        out.append(entry)
    return out


# ── Main entry point ───────────────────────────────────────────────────────────

async def run_turn(
    compiled: CompiledAgent,
    history: list[dict],
    user_message: str,
    *,
    slot_state: dict[str, str] | None = None,
    run_id: str | None = None,
    session_id: str | None = None,
    parent_span_id: str | None = None,
    db: AsyncSession | None = None,
    redis_channel: str | None = None,
) -> TurnResult:
    """
    Execute one agent turn.

    Args:
        compiled: The compiled agent (from compiler.py).
        history: Conversation history in OpenAI message format.
        user_message: The user's new message.
        run_id: Existing Run ID for trace persistence (created if None + db provided).
        session_id: Session ID to group multiple turns into one conversation session.
        parent_span_id: Parent span for nested sub-agent calls.
        db: AsyncSession for Postgres persistence (optional — skip if None).
        redis_channel: Redis pub/sub channel for real-time span events.

    Returns:
        TurnResult with the agent's response and trace metadata.
    """
    t_start = time.perf_counter()
    total_input_tokens = 0
    total_output_tokens = 0
    spans_collected: list[dict] = []
    tool_calls_made: list[dict] = []

    if db and run_id is None:
        run_id = str(ulid_new())
        run = Run(
            id=run_id,
            agent_id=compiled.agent_id or None,
            agent_version=compiled.agent_version,
            session_id=session_id,
            source="simulator",
            status="running",
        )
        db.add(run)
        await db.flush()

    async def emit_span(span_type: str, data: dict, span_id: str | None = None) -> str:
        sid = span_id or str(ulid_new())
        event = _span_event(span_type, {"span_id": sid, "run_id": run_id, **data})
        spans_collected.append(event)
        if redis_channel:
            await _emit(redis_channel, event)
        if db and run_id:
            span = Span(
                id=sid,
                run_id=run_id,
                parent_span_id=parent_span_id,
                name=span_type,
                type=span_type,
                payload=data,
            )
            db.add(span)
        return sid

    async def _mark_terminal(status: str) -> None:
        """Mark the Run row with a terminal status and commit, swallowing commit errors.

        Used for both happy-path completion and error/cancellation paths so any
        turn that started always reaches a terminal status (never stuck in 'running').
        """
        if not (db and run_id):
            return
        run_obj = await db.get(Run, run_id)
        if run_obj:
            run_obj.status = status
            run_obj.ended_at = datetime.now(UTC)
        try:
            await db.commit()
        except Exception as commit_err:
            log.warning("executor.terminal_commit_error", status=status, error=str(commit_err))

    try:
        result = await _run_turn_body(
            compiled=compiled,
            history=history,
            user_message=user_message,
            slot_state=slot_state,
            run_id=run_id,
            emit_span=emit_span,
            spans_collected=spans_collected,
            tool_calls_made=tool_calls_made,
            t_start=t_start,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
        )
        if db and run_id:
            run_obj = await db.get(Run, run_id)
            if run_obj:
                run_obj.status = "completed"
                run_obj.ended_at = datetime.now(UTC)
                run_obj.total_tokens = result.total_input_tokens + result.total_output_tokens
                run_obj.total_cost_usd = result.estimated_cost_usd
        if db:
            await db.commit()
        return result
    except asyncio.CancelledError:
        # Client ended the simulation or WS dropped mid-turn.
        # CancelledError inherits from BaseException, not Exception — must be
        # handled separately so the Run never stays 'running' forever.
        log.info("executor.turn_cancelled", run_id=run_id)
        await _mark_terminal("cancelled")
        raise
    except Exception:
        await _mark_terminal("failed")
        raise


async def _run_turn_body(
    *,
    compiled: CompiledAgent,
    history: list[dict],
    user_message: str,
    slot_state: dict[str, str] | None,
    run_id: str | None,
    emit_span,
    spans_collected: list[dict],
    tool_calls_made: list[dict],
    t_start: float,
    total_input_tokens: int,
    total_output_tokens: int,
) -> TurnResult:
    # ── Step 1: Router call ────────────────────────────────────────────────────

    router_model = compiled.schema_.models.router or compiled.schema_.models.primary
    router_span_id = str(ulid_new())
    await emit_span("router_start", {"model": router_model}, span_id=router_span_id)

    current_slot_state: dict[str, str] = dict(slot_state) if slot_state else {}

    router_user_prompt = _build_router_prompt(
        compiled, history, user_message, current_slot_state,
    )
    router_messages = [
        {"role": "system", "content": _ROUTER_SYSTEM},
        {"role": "user", "content": router_user_prompt},
    ]

    decision, parse_error = await _call_router_with_retry(router_model, router_messages)
    if parse_error is not None:
        await emit_span("router_parse_error", {
            "error": parse_error["error"],
            "raw_output": parse_error["raw_output"],
            "model": router_model,
        })

    # Merge newly extracted slot values into accumulated state
    if decision.extracted_slot_values:
        current_slot_state.update(decision.extracted_slot_values)

    # Filter unfilled_slots against accumulated state — never re-ask confirmed slots
    decision.unfilled_slots = [
        s for s in decision.unfilled_slots if s not in current_slot_state
    ]

    total_input_tokens += count_tokens(router_model, router_messages)
    await emit_span("router_decision", {
        "decision": decision.model_dump(),
        "model": router_model,
        "slot_state": current_slot_state,
        # Both prompts captured so the dialog in the simulator can show them separately
        "system_prompt": _ROUTER_SYSTEM,
        "prompt": router_messages[1]["content"],
        # Raw user message for this turn — lets the Chat tab reconstruct the
        # conversation reliably even when a turn emits no llm_call_* spans
        # (slot_fill / handoff / interrupt).
        "user_message": user_message,
    })

    # ── Step 2: Interrupt override ─────────────────────────────────────────────

    if decision.interrupt_triggered:
        await emit_span("interrupt_triggered", {
            "trigger": decision.interrupt_triggered,
            "action": decision.interrupt_action,
        })
        system_prompt = _assemble_system_prompt(compiled, decision)
        messages = [
            {"role": "system", "content": system_prompt},
            *history,
            {"role": "user", "content": user_message},
        ]
        interrupt_model = compiled.schema_.models.primary
        # Wrap the interrupt chat call in the same llm_call_start/end spans as
        # the main tool loop so the Traces UI can render its prompt + response.
        await emit_span("llm_call_start", {
            "model": interrupt_model,
            "iteration": 0,
            "n_messages": len(messages),
            "system_prompt": system_prompt,
            "messages": _serialize_messages(messages),
        })
        resp = await chat_completion(
            model=interrupt_model,
            messages=messages,
            max_tokens=1024,
        )
        in_tok = resp.usage["input_tokens"]
        out_tok = resp.usage["output_tokens"]
        total_input_tokens += in_tok
        total_output_tokens += out_tok
        await emit_span("llm_call_end", {
            "model": interrupt_model,
            "iteration": 0,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "stop_reason": resp.stop_reason,
            "output": resp.content or None,
            "tool_calls": None,
        })
        cost = estimate_cost(interrupt_model, total_input_tokens, total_output_tokens)
        await _finalize_run(
            total_input_tokens, total_output_tokens, cost, emit_span, t_start,
            turn_type="interrupt", content=resp.content or "",
        )
        return TurnResult(
            type="interrupt",
            content=resp.content,
            router_decision=decision,
            run_id=run_id,
            spans=spans_collected,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            estimated_cost_usd=cost,
            slot_state=current_slot_state,
        )

    # ── Step 2b: Handoff ──────────────────────────────────────────────────────

    if decision.handoff_triggered:
        await emit_span("handoff_triggered", {
            "handoff": decision.handoff_triggered,
            "target": decision.handoff_target,
        })
        cost = estimate_cost(
            compiled.schema_.models.primary, total_input_tokens, total_output_tokens,
        )
        handoff_content = (
            f"I'm transferring you to {decision.handoff_target}. "
            + (f"Context: {decision.handoff_context}" if decision.handoff_context else "")
        )
        await _finalize_run(
            total_input_tokens, total_output_tokens, cost, emit_span, t_start,
            turn_type="handoff", content=handoff_content,
        )
        return TurnResult(
            type="handoff",
            content=handoff_content,
            router_decision=decision,
            run_id=run_id,
            spans=spans_collected,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            estimated_cost_usd=cost,
            slot_state=current_slot_state,
        )
    # ── Step 3: Slot fill check ────────────────────────────────────────────────

    if decision.unfilled_slots and decision.active_condition and decision.active_goal:
        slot_name = decision.unfilled_slots[0]
        await emit_span("slot_fill", {"slot_name": slot_name})

        ask_question: str | None = None
        for cond in compiled.schema_.conditions:
            if cond.name == decision.active_condition:
                for goal in cond.goals:
                    if goal.name == decision.active_goal:
                        for slot in goal.slots:
                            if slot.name == slot_name:
                                ask_question = slot.ask_if_missing
                                break

        question = ask_question or f"Could you please provide your {slot_name}?"
        cost = estimate_cost(
            compiled.schema_.models.primary, total_input_tokens, total_output_tokens,
        )
        await _finalize_run(
            total_input_tokens, total_output_tokens, cost, emit_span, t_start,
            turn_type="slot_fill", content=question,
        )
        return TurnResult(
            type="slot_fill",
            content=question,
            router_decision=decision,
            run_id=run_id,
            spans=spans_collected,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            estimated_cost_usd=cost,
            slot_state=current_slot_state,
        )

    # ── Step 4: Assemble augmented prompt ──────────────────────────────────────

    system_prompt = _assemble_system_prompt(compiled, decision)

    # Filter tool definitions to those available in the active goal
    available_tools = compiled.tool_definitions
    if decision.active_condition and decision.active_goal:
        for cond in compiled.schema_.conditions:
            if cond.name == decision.active_condition:
                for goal in cond.goals:
                    if goal.name == decision.active_goal and goal.tools:
                        goal_tool_names = {_snake(t) for t in goal.tools}
                        available_tools = [
                            td for td in compiled.tool_definitions
                            if td.name in goal_tool_names
                        ]
                        break

    # ── Step 5: Primary model call with tool loop ──────────────────────────────

    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        *history,
        {"role": "user", "content": user_message},
    ]

    primary_model = compiled.schema_.models.primary
    final_content: str | None = None
    last_text_from_model: str | None = None
    hit_iteration_limit = False

    for iteration in range(MAX_TOOL_ITERATIONS):
        llm_span_id = str(ulid_new())
        await emit_span("llm_call_start", {
            "model": primary_model,
            "iteration": iteration,
            "n_messages": len(messages),
            # Explicit system_prompt field for the simulator debug dialog; also
            # included as messages[0] for complete conversation inspection.
            "system_prompt": system_prompt,
            "messages": _serialize_messages(messages),
        }, span_id=llm_span_id)

        resp = await chat_completion(
            model=primary_model,
            messages=messages,
            tools=available_tools if available_tools else None,
            temperature=PRIMARY_TEMPERATURE,
            max_tokens=2048,
        )

        in_tok = resp.usage["input_tokens"]
        out_tok = resp.usage["output_tokens"]
        total_input_tokens += in_tok
        total_output_tokens += out_tok

        if resp.content:
            last_text_from_model = resp.content

        await emit_span("llm_call_end", {
            "model": primary_model,
            "iteration": iteration,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "stop_reason": resp.stop_reason,
            "output": resp.content or None,
            "tool_calls": resp.tool_calls if resp.tool_calls else None,
        })

        if not resp.tool_calls:
            final_content = resp.content
            break

        # OpenAI tool-call format — LiteLLM converts to Anthropic format for Claude.
        assistant_tool_call_msg: dict = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["arguments"]),
                    },
                }
                for tc in resp.tool_calls
            ],
        }
        tool_result_msgs: list[dict] = []

        for tc in resp.tool_calls:
            await emit_span("tool_call", {
                "tool": tc["name"],
                "arguments": tc["arguments"],
            })

            try:
                result_str = await _execute_tool(tc["name"], tc["arguments"], compiled)
                tool_calls_made.append({
                    "tool": tc["name"],
                    "arguments": tc["arguments"],
                    "result": result_str,
                })
                await emit_span("tool_result", {
                    "tool": tc["name"],
                    "result_preview": result_str[:200],
                })
            except Exception as exc:
                err_msg = str(exc)
                log.exception("executor.tool_error", tool=tc["name"])
                await emit_span("tool_error", {
                    "tool": tc["name"],
                    "arguments": tc["arguments"],
                    "error": err_msg,
                })
                # Hand the model a JSON error payload so it can recover gracefully
                result_str = json.dumps({"error": err_msg, "tool": tc["name"]})
                tool_calls_made.append({
                    "tool": tc["name"],
                    "arguments": tc["arguments"],
                    "result": result_str,
                    "error": err_msg,
                })

            tool_result_msgs.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result_str,
            })

        messages.append(assistant_tool_call_msg)
        messages.extend(tool_result_msgs)
    else:
        hit_iteration_limit = True

    if hit_iteration_limit:
        await emit_span("tool_loop_exceeded", {
            "iterations": MAX_TOOL_ITERATIONS,
            "last_tool_calls": [tc["tool"] for tc in tool_calls_made[-MAX_TOOL_ITERATIONS:]],
        })
        # Prefer the most recent real model text; fall back to a neutral message
        # only if the model never produced any text across every iteration.
        final_content = last_text_from_model or (
            "I wasn't able to finish using the tools I have available. "
            "Could you tell me more about what you'd like me to do?"
        )

    # ── Step 6: Cost estimation and finalise run ───────────────────────────────

    cost = estimate_cost(primary_model, total_input_tokens, total_output_tokens)
    await _finalize_run(
        total_input_tokens, total_output_tokens, cost, emit_span, t_start,
        turn_type="response", content=final_content or "",
    )

    return TurnResult(
        type="response",
        content=final_content or "",
        router_decision=decision,
        tool_calls_made=tool_calls_made,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        estimated_cost_usd=cost,
        run_id=run_id,
        spans=spans_collected,
        slot_state=current_slot_state,
    )


# ── Router helpers ─────────────────────────────────────────────────────────────

async def _call_router_with_retry(
    router_model: str,
    router_messages: list[dict],
) -> tuple[RouterDecision, dict | None]:
    """
    Call the router and parse its JSON output, retrying once on parse failure.

    Returns (decision, parse_error). parse_error is None on success, otherwise
    a dict with 'error' and 'raw_output' describing the final failure.
    """
    attempt_messages = list(router_messages)
    last_raw = ""
    last_err: Exception | None = None

    for attempt in range(2):
        try:
            resp: LLMResponse = await chat_completion(
                model=router_model,
                messages=attempt_messages,
                tools=None,
                temperature=0.0,
                max_tokens=512,
            )
            last_raw = (resp.content or "").strip()
            cleaned = last_raw
            if cleaned.startswith("```"):
                cleaned = "\n".join(cleaned.split("\n")[1:])
                cleaned = cleaned.rsplit("```", 1)[0].strip()
            decision = RouterDecision(**json.loads(cleaned))
            return decision, None
        except Exception as e:
            last_err = e
            log.warning("executor.router_parse_error", attempt=attempt, error=str(e))
            if attempt == 0:
                attempt_messages = [
                    *router_messages,
                    {"role": "assistant", "content": last_raw},
                    {"role": "user", "content": (
                        "Your previous response was not valid JSON. Return ONLY the JSON "
                        "object specified in the system instructions, with no prose, no "
                        "code fences, and no commentary."
                    )},
                ]

    return RouterDecision(), {"error": str(last_err), "raw_output": last_raw}


async def _finalize_run(
    total_input_tokens: int,
    total_output_tokens: int,
    cost: float,
    emit_span,
    t_start: float,
    *,
    turn_type: str,
    content: str,
) -> None:
    """Emit the turn_complete span. Run-row status/ended_at is updated in run_turn().

    turn_type and content are embedded in the payload so Chat-tab reconstruction
    has a single reliable source for the final assistant output per turn, no
    matter which branch produced it (response / slot_fill / interrupt / handoff).
    """
    duration_ms = int((time.perf_counter() - t_start) * 1000)
    await emit_span("turn_complete", {
        "duration_ms": duration_ms,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "estimated_cost_usd": cost,
        "turn_type": turn_type,
        "content": content,
    })
