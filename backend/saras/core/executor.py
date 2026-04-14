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

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import new as ulid_new

from saras.core.schema import CompiledAgent, ContextLayer
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

_ROUTER_SYSTEM_BAD = """\
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
- For slot extraction: only extract slot values that are explicitly and clearly stated in the LATEST user message.
  Do not infer from context or earlier conversation turns. If in any doubt, leave the slot as unfilled.
- In unfilled_slots, include any required slot you are not 100% certain about, even if it was mentioned before.
- If no condition applies, set both to null.
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
    Execute a tool call. Phase 2: returns a mock response.
    Phase 3: will route to the tool's endpoint via HTTP.
    """
    tool = next((t for t in compiled.schema_.tools if _snake(t.name) == tool_name), None)
    if tool is None:
        return json.dumps({"error": f"Tool '{tool_name}' not found in agent definition"})

    # Phase 2: mock response — return a placeholder so the model can continue
    log.info("executor.tool_mock", tool=tool_name, args=arguments)
    return json.dumps({
        "status": "mock",
        "message": f"[Phase 2 mock] Tool '{tool.name}' called with: {arguments}",
        "result": None,
    })


def _snake(name: str) -> str:
    return name.lower().replace(" ", "_").replace("-", "_")


# ── Span helpers ───────────────────────────────────────────────────────────────

def _span_event(span_type: str, data: dict) -> dict:
    return {
        "type": "span",
        "span_type": span_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
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
    sim_mode: str = "standard",  # "standard" | "good" | "bad"
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

    # Create or reuse Run
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

    # ── Step 1: Router call ────────────────────────────────────────────────────

    router_model = compiled.schema_.models.router or compiled.schema_.models.primary
    router_span_id = str(ulid_new())
    await emit_span("router_start", {"model": router_model, "sim_mode": sim_mode}, span_id=router_span_id)

    current_slot_state: dict[str, str] = dict(slot_state) if slot_state else {}

    # In bad mode: use the looser router prompt so it misses slot extractions
    router_system = _ROUTER_SYSTEM_BAD if sim_mode == "bad" else _ROUTER_SYSTEM

    router_messages = [
        {"role": "system", "content": router_system},
        {"role": "user", "content": _build_router_prompt(compiled, history, user_message, current_slot_state)},
    ]

    try:
        router_resp: LLMResponse = await chat_completion(
            model=router_model,
            messages=router_messages,
            tools=None,
            temperature=0.0,
            max_tokens=512,
        )
        router_raw = router_resp.content.strip()
        # Strip markdown code fences if present
        if router_raw.startswith("```"):
            router_raw = "\n".join(router_raw.split("\n")[1:])
            router_raw = router_raw.rsplit("```", 1)[0].strip()
        decision_dict = json.loads(router_raw)
        decision = RouterDecision(**decision_dict)
    except Exception as e:
        log.warning("executor.router_parse_error", error=str(e))
        decision = RouterDecision()  # Fallback: no routing

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
        # Include the prompt sent to the router so it's inspectable in traces
        "prompt": router_messages[1]["content"] if len(router_messages) > 1 else None,
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
        resp = await chat_completion(
            model=compiled.schema_.models.primary,
            messages=messages,
            max_tokens=1024,
        )
        _update_tokens(resp, compiled, total_input_tokens, total_output_tokens)
        if db:
            await db.commit()
        return TurnResult(
            type="interrupt",
            content=resp.content,
            router_decision=decision,
            run_id=run_id,
            spans=spans_collected,
            total_input_tokens=total_input_tokens,
            slot_state=current_slot_state,
        )

    # ── Step 2b: Handoff ──────────────────────────────────────────────────────

    if decision.handoff_triggered:
        await emit_span("handoff_triggered", {
            "handoff": decision.handoff_triggered,
            "target": decision.handoff_target,
        })
        if db:
            await db.commit()
        return TurnResult(
            type="handoff",
            content=(
                f"I'm transferring you to {decision.handoff_target}. "
                + (f"Context: {decision.handoff_context}" if decision.handoff_context else "")
            ),
            router_decision=decision,
            run_id=run_id,
            spans=spans_collected,
            slot_state=current_slot_state,
        )

    # ── Step 3: Slot fill check ────────────────────────────────────────────────

    if decision.unfilled_slots and decision.active_condition and decision.active_goal:
        slot_name = decision.unfilled_slots[0]
        await emit_span("slot_fill", {"slot_name": slot_name})

        # Find the slot definition to get ask_if_missing
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
        if db:
            await db.commit()
        return TurnResult(
            type="slot_fill",
            content=question,
            router_decision=decision,
            run_id=run_id,
            spans=spans_collected,
            slot_state=current_slot_state,
        )

    # ── Step 4: Assemble augmented prompt ──────────────────────────────────────

    system_prompt = _assemble_system_prompt(compiled, decision)

    # Inject sim_mode guidance so the primary model behaves consistently with the mode
    if sim_mode == "good":
        system_prompt += (
            "\n\n[SIMULATION — IDEAL BEHAVIOUR] You are demonstrating perfect agent behaviour "
            "for golden-dataset collection. Follow every rule and sequence step exactly. "
            "Never ask for information already provided anywhere in the conversation. "
            "Always call the required tool before giving a response. Be specific: exact times, "
            "prices, and confirmation numbers. Do not guess or hallucinate data."
        )
    elif sim_mode == "bad":
        system_prompt += (
            "\n\n[SIMULATION — FLAWED BEHAVIOUR] You are demonstrating suboptimal agent behaviour "
            "for contrast-dataset collection. Occasionally: ask for information the user already "
            "provided, give vague responses without specific details, skip confirming booking "
            "details before proceeding, or provide general answers instead of using tools. "
            "Be inconsistent with rule application. This is intentional for evaluation purposes."
        )

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
    # good mode: deterministic; bad mode: more random; standard: default
    primary_temperature = 0.0 if sim_mode == "good" else (0.7 if sim_mode == "bad" else 0.3)

    for iteration in range(MAX_TOOL_ITERATIONS):
        llm_span_id = str(ulid_new())
        await emit_span("llm_call_start", {
            "model": primary_model,
            "iteration": iteration,
            "n_messages": len(messages),
            "sim_mode": sim_mode,
            # Full prompt sent to the model — serialized for trace inspection
            "messages": _serialize_messages(messages),
        }, span_id=llm_span_id)

        resp = await chat_completion(
            model=primary_model,
            messages=messages,
            tools=available_tools if available_tools else None,
            temperature=primary_temperature,
            max_tokens=2048,
        )

        in_tok = resp.usage["input_tokens"]
        out_tok = resp.usage["output_tokens"]
        total_input_tokens += in_tok
        total_output_tokens += out_tok

        await emit_span("llm_call_end", {
            "model": primary_model,
            "iteration": iteration,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "stop_reason": resp.stop_reason,
            # Model output — text response and/or tool calls
            "output": resp.content or None,
            "tool_calls": resp.tool_calls if resp.tool_calls else None,
        })

        # No tool calls → final response
        if not resp.tool_calls:
            final_content = resp.content
            break

        # Process tool calls
        # Use OpenAI tool-call format — LiteLLM converts this to Anthropic format
        # when the target model is Claude. Anthropic format in the message list is
        # NOT converted back for OpenAI, which causes the "Invalid user message" error.
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

            result_str = await _execute_tool(tc["name"], tc["arguments"], compiled)
            tool_calls_made.append({"tool": tc["name"], "arguments": tc["arguments"], "result": result_str})

            await emit_span("tool_result", {
                "tool": tc["name"],
                "result_preview": result_str[:200],
            })

            # One message per tool result (OpenAI format; works with LiteLLM for all providers)
            tool_result_msgs.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result_str,
            })

        # Append assistant turn + all tool results
        messages.append(assistant_tool_call_msg)
        messages.extend(tool_result_msgs)

    else:
        # Hit MAX_TOOL_ITERATIONS without a text response
        final_content = "I've processed your request. Is there anything else I can help you with?"

    # ── Step 6: Cost estimation and finalise run ───────────────────────────────

    cost = estimate_cost(primary_model, total_input_tokens, total_output_tokens)
    duration_ms = int((time.perf_counter() - t_start) * 1000)

    await emit_span("turn_complete", {
        "duration_ms": duration_ms,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "estimated_cost_usd": cost,
    })

    if db and run_id:
        run_obj = await db.get(Run, run_id)
        if run_obj:
            run_obj.status = "completed"
            run_obj.ended_at = datetime.now(timezone.utc)
            run_obj.total_tokens = total_input_tokens + total_output_tokens
            run_obj.total_cost_usd = cost
        await db.commit()

    return TurnResult(
        type="response",
        content=final_content,
        router_decision=decision,
        tool_calls_made=tool_calls_made,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        estimated_cost_usd=cost,
        run_id=run_id,
        spans=spans_collected,
        slot_state=current_slot_state,
    )


def _update_tokens(resp: LLMResponse, compiled: CompiledAgent,
                   input_acc: int, output_acc: int) -> None:
    input_acc += resp.usage["input_tokens"]
    output_acc += resp.usage["output_tokens"]
