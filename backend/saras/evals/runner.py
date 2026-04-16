"""Multi-turn eval runner.

Orchestrates the full evaluation pipeline for one EvalRun:
  1. Load agent, dataset, eval suite from Postgres
  2. Compile the agent
  3. For each DatasetItem:
      a. Run the conversation (scripted or simulated)
      b. Score each turn + the full conversation
      c. Save EvalResult rows to Postgres
  4. Update EvalRun.summary with aggregate stats

Publishes progress events to Redis so the SSE endpoint can stream them to
the frontend in real time.

Key design decisions:
  - Reuses core/executor.run_turn() verbatim — eval conversations go through
    the exact same execution path as live simulator sessions.
  - Does NOT use WebSocket — progress is pushed via Redis pub/sub to SSE handler.
  - Simulated user turns call a lightweight persona LLM separate from the agent.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog
import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import new as ulid_new

from saras.core.compiler import compile_from_yaml
from saras.core.executor import TurnResult, run_turn
from saras.core.schema import AgentSchema
from saras.db.models import Agent, Dataset, DatasetItem, EvalResult, EvalRun, EvalSuite
from saras.db.redis import get_redis, publish
from saras.evals.metrics import (
    MetricInput,
    MetricResult,
    build_metric,
    parse_metric_set,
)
from saras.evals.schemas import (
    ConversationRecord,
    MetricDefinition,
    SimulatedScenario,
    TurnRecord,
)
from saras.providers.litellm import chat_completion

log = structlog.get_logger()

# Persona LLM system prompt template
_PERSONA_SYSTEM = """\
You are roleplaying as a user with the following profile:

Persona: {persona}
Goal: {goal}
{stop_signal_instruction}

Rules:
- Stay in character as this user throughout the conversation.
- Generate ONLY the user's next message — one short message at a time.
- Once your goal is achieved or the agent has completed what you needed, \
respond with exactly: CONVERSATION_COMPLETE
- If the conversation has stalled or the agent cannot help, respond with: CONVERSATION_COMPLETE
- Never break character or acknowledge that you are an AI.
- Keep messages natural and conversational, as a real user would write them.
"""

_PERSONA_STOP_SIGNAL = "When this happens, respond with CONVERSATION_COMPLETE: {stop_signal}"


# ── Main entry point ───────────────────────────────────────────────────────────

async def run_eval(eval_run_id: str, db: AsyncSession) -> None:
    """Execute an EvalRun end-to-end. Called as a background task."""
    log.info("eval.run.start", eval_run_id=eval_run_id)

    eval_run = await db.get(EvalRun, eval_run_id)
    if not eval_run:
        log.error("eval.run.not_found", eval_run_id=eval_run_id)
        return

    # Mark as running
    from datetime import datetime, timezone
    eval_run.status = "running"
    eval_run.started_at = datetime.now(timezone.utc)
    await db.commit()

    redis_channel = f"eval:{eval_run_id}"

    try:
        # Load suite + agent
        suite: EvalSuite | None = await db.get(EvalSuite, eval_run.suite_id)
        if not suite:
            raise ValueError(f"EvalSuite {eval_run.suite_id} not found")

        agent: Agent | None = await db.get(Agent, eval_run.agent_id) if eval_run.agent_id else None
        if not agent:
            raise ValueError("EvalRun has no agent_id — cannot run eval")

        # Load dataset items
        items_result = await db.execute(
            select(DatasetItem).where(DatasetItem.dataset_id == eval_run.dataset_id)
        )
        items: list[DatasetItem] = list(items_result.scalars().all())
        if not items:
            raise ValueError("Dataset has no items")

        # Parse metrics + compile agent
        metrics = parse_metric_set(suite.metric_set_yaml)
        compiled = compile_from_yaml(agent.yaml_content, agent.id, agent.current_version)
        schema: AgentSchema = compiled.schema_

        # Judge model — use agent's judge model or fall back to primary
        judge_model: str = schema.models.judge or schema.models.primary

        total = len(items)
        all_scores: dict[str, list[float]] = {}  # metric_name → [scores]

        for idx, item in enumerate(items):
            log.info("eval.item.start", eval_run_id=eval_run_id, item_id=item.id, idx=idx)

            try:
                conversation = await _run_conversation(compiled, item, eval_run_id)
            except Exception as exc:
                log.error("eval.item.conversation_failed", item_id=item.id, error=str(exc))
                conversation = ConversationRecord(
                    item_id=item.id,
                    history=[],
                    turns=[],
                    error=str(exc),
                )

            # Score the conversation
            scores = await _score_conversation(
                conversation, item, metrics, schema, judge_model
            )

            # Persist results
            await _save_results(eval_run_id, item.id, scores, conversation, db)

            # Accumulate for summary
            for s in scores:
                all_scores.setdefault(s.metric_name, []).append(s.score)

            # Publish progress event
            await _publish(redis_channel, {
                "type": "item_done",
                "item_id": item.id,
                "completed": idx + 1,
                "total": total,
                "scores": {s.metric_name: s.score for s in scores},
                "tokens": conversation.total_tokens,
                "cost_usd": conversation.total_cost_usd,
            })

        # Build summary
        summary: dict[str, Any] = {
            "total_items": total,
            "metrics": {
                name: {
                    "avg_score": sum(vals) / len(vals) if vals else 0.0,
                    "min_score": min(vals) if vals else 0.0,
                    "max_score": max(vals) if vals else 0.0,
                    "pass_rate": (
                        sum(1 for v in vals if v >= 0.6) / len(vals)
                        if vals else 0.0
                    ),
                }
                for name, vals in all_scores.items()
            },
        }

        eval_run.status = "completed"
        eval_run.ended_at = datetime.now(timezone.utc)
        eval_run.summary = summary
        await db.commit()

        await _publish(redis_channel, {"type": "complete", "summary": summary})
        log.info("eval.run.complete", eval_run_id=eval_run_id)

    except Exception as exc:
        log.error("eval.run.failed", eval_run_id=eval_run_id, error=str(exc))
        eval_run.status = "failed"
        eval_run.ended_at = datetime.now(timezone.utc)
        eval_run.summary = {"error": str(exc)}
        await db.commit()
        await _publish(redis_channel, {"type": "error", "message": str(exc)})


# ── Conversation execution ─────────────────────────────────────────────────────

async def _run_conversation(
    compiled: Any,
    item: DatasetItem,
    eval_run_id: str,
) -> ConversationRecord:
    """Execute a full multi-turn conversation for a dataset item."""
    input_data: dict[str, Any] = item.input or {}

    if "turns" in input_data:
        return await _run_scripted(compiled, input_data["turns"], item.id)
    elif "scenario" in input_data:
        scenario = SimulatedScenario(**input_data["scenario"])
        return await _run_simulated(compiled, scenario, item.id)
    else:
        raise ValueError(
            f"DatasetItem {item.id} has unrecognised input format. "
            "Expected {'turns': [...]} or {'scenario': {...}}"
        )


async def _run_scripted(
    compiled: Any,
    turns: list[str],
    item_id: str,
) -> ConversationRecord:
    """Execute a scripted conversation (fixed user messages)."""
    history: list[dict] = []
    slot_state: dict[str, str] = {}
    turn_records: list[TurnRecord] = []
    total_tokens = 0
    total_cost = 0.0

    for idx, user_message in enumerate(turns):
        result: TurnResult = await run_turn(
            compiled,
            history,
            user_message,
            slot_state=slot_state,
        )
        slot_state = result.slot_state

        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": result.content})

        turn_records.append(TurnRecord(
            turn_index=idx,
            user_message=user_message,
            agent_content=result.content,
            turn_type=result.type,
            tool_calls_made=result.tool_calls_made,
            router_decision=result.router_decision.model_dump() if result.router_decision else None,
            input_tokens=result.total_input_tokens,
            output_tokens=result.total_output_tokens,
            cost_usd=result.estimated_cost_usd,
        ))
        total_tokens += result.total_input_tokens + result.total_output_tokens
        total_cost += result.estimated_cost_usd

    return ConversationRecord(
        item_id=item_id,
        history=history,
        turns=turn_records,
        total_tokens=total_tokens,
        total_cost_usd=total_cost,
    )


async def _run_simulated(
    compiled: Any,
    scenario: SimulatedScenario,
    item_id: str,
) -> ConversationRecord:
    """Execute a simulated conversation where an LLM plays the user role."""
    history: list[dict] = []
    slot_state: dict[str, str] = {}
    turn_records: list[TurnRecord] = []
    total_tokens = 0
    total_cost = 0.0

    persona_model = compiled.schema_.models.router  # use fast model for persona

    for idx in range(scenario.max_turns):
        # Generate user message from persona LLM
        user_message = await _generate_user_message(
            persona_model, scenario, history
        )
        if user_message is None:
            log.info("eval.simulated.complete", item_id=item_id, turns=idx)
            break

        result: TurnResult = await run_turn(
            compiled,
            history,
            user_message,
            slot_state=slot_state,
        )
        slot_state = result.slot_state

        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": result.content})

        turn_records.append(TurnRecord(
            turn_index=idx,
            user_message=user_message,
            agent_content=result.content,
            turn_type=result.type,
            tool_calls_made=result.tool_calls_made,
            router_decision=result.router_decision.model_dump() if result.router_decision else None,
            input_tokens=result.total_input_tokens,
            output_tokens=result.total_output_tokens,
            cost_usd=result.estimated_cost_usd,
        ))
        total_tokens += result.total_input_tokens + result.total_output_tokens
        total_cost += result.estimated_cost_usd

    return ConversationRecord(
        item_id=item_id,
        history=history,
        turns=turn_records,
        total_tokens=total_tokens,
        total_cost_usd=total_cost,
    )


async def _generate_user_message(
    model: str,
    scenario: SimulatedScenario,
    history: list[dict],
) -> str | None:
    """Call a persona LLM to generate the next user message.

    Returns None when the conversation should end (goal achieved or stalled).
    """
    stop_instruction = ""
    if scenario.stop_signal:
        stop_instruction = _PERSONA_STOP_SIGNAL.format(stop_signal=scenario.stop_signal)

    system = _PERSONA_SYSTEM.format(
        persona=scenario.persona,
        goal=scenario.goal,
        stop_signal_instruction=stop_instruction,
    )

    messages: list[dict] = [{"role": "system", "content": system}]
    # Provide conversation history in reverse-role format (agent → user from persona's perspective)
    for msg in history:
        role = "assistant" if msg["role"] == "user" else "user"
        messages.append({"role": role, "content": msg.get("content", "")})

    # Add a trigger for the first turn
    if not history:
        messages.append({"role": "user", "content": "Start the conversation to achieve your goal."})

    try:
        response = await chat_completion(
            model=model,
            messages=messages,
            tools=None,
            temperature=0.7,
            max_tokens=256,
        )
        content = (response.content or "").strip()
    except Exception as exc:
        log.error("eval.persona.llm_error", error=str(exc))
        return None

    if "CONVERSATION_COMPLETE" in content:
        return None

    return content


# ── Scoring ────────────────────────────────────────────────────────────────────

async def _score_conversation(
    conversation: ConversationRecord,
    item: DatasetItem,
    metrics: list[MetricDefinition],
    schema: AgentSchema,
    judge_model: str,
) -> list[MetricResult]:
    """Score the conversation across all metrics using the metric registry."""
    scores: list[MetricResult] = []

    expected_output: dict[str, Any] = item.expected_output or {}
    expected_turns: list[str] = expected_output.get("turns", [])
    expected_tools: list[dict] = expected_output.get("tool_calls", [])

    # Build metric instances once — each knows how to score itself
    metric_instances = [
        build_metric(m, judge_model=judge_model) for m in metrics
    ]

    for metric_inst in metric_instances:
        defn = metric_inst.definition

        if defn.scope == "whole_conversation":
            inp = MetricInput(
                conversation=conversation,
                agent_schema=schema,
                metric_definition=defn,
            )
            result = await metric_inst.measure(inp)
            scores.append(result)

        elif defn.scope in ("per_turn", "tool_call"):
            for turn in conversation.turns:
                turn_idx = turn.turn_index
                expected_text = (
                    expected_turns[turn_idx]
                    if turn_idx < len(expected_turns)
                    else ""
                )

                # Skip deterministic golden-match metrics when no golden exists
                if (
                    defn.preset in ("semantic_similarity", "rouge_l", "bleu")
                    and not expected_text
                ):
                    continue

                inp = MetricInput(
                    turn=turn,
                    expected_text=expected_text or None,
                    expected_tools=expected_tools or None,
                    conversation=conversation,
                    agent_schema=schema,
                    turn_index=turn_idx,
                    metric_definition=defn,
                )
                result = await metric_inst.measure(inp)
                scores.append(result)

    return scores


# ── Persistence ────────────────────────────────────────────────────────────────

async def _save_results(
    eval_run_id: str,
    item_id: str,
    scores: list[MetricResult],
    conversation: ConversationRecord,
    db: AsyncSession,
) -> None:
    """Persist MetricResult objects as EvalResult rows."""
    conversation_snapshot = conversation.model_dump(mode="json")

    for score in scores:
        result = EvalResult(
            id=str(ulid_new()),
            eval_run_id=eval_run_id,
            dataset_item_id=item_id,
            metric_id=score.metric_name,
            score=score.score,
            reasoning=score.reasoning,
            model_used=score.model_used,
            turn_index=score.turn_index,
            scope=score.scope,
            conversation_json=conversation_snapshot,
        )
        db.add(result)

    await db.commit()


# ── Redis helper ───────────────────────────────────────────────────────────────

async def _publish(channel: str, payload: dict[str, Any]) -> None:
    """Publish a progress event to Redis (best-effort)."""
    try:
        await publish(channel, json.dumps(payload))
    except Exception as exc:
        log.warning("eval.redis.publish_failed", channel=channel, error=str(exc))
