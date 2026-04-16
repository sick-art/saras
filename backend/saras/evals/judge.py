"""LLM-as-judge evaluator (legacy).

.. deprecated::
    This module is no longer used by the eval runner. The canonical
    implementation lives in :mod:`saras.evals.metrics.llm_judge` via the
    :class:`~saras.evals.metrics.llm_judge.LLMJudgeMetric` abstract base class
    and its subclasses in ``quality_metrics.py``, ``completion_metrics.py``, etc.

    This file is kept for reference only and will be removed in a future cleanup.
"""

from __future__ import annotations

import json
import re

import structlog

from saras.core.schema import AgentSchema
from saras.evals.schemas import ConversationRecord, JudgeScore, MetricDefinition
from saras.providers.litellm import chat_completion

log = structlog.get_logger()

_JUDGE_SYSTEM = """\
You are an expert evaluator for AI agent conversations. Your job is to assess \
the quality of an AI agent's responses against a specific metric.

You will be given:
1. The agent's persona and tone guidelines (to understand the intended behaviour)
2. A specific metric with a scoring rubric
3. A conversation excerpt to evaluate

You MUST respond with ONLY a JSON object in this format:
{"score": <integer 1-5>, "reasoning": "<2-3 clear sentences explaining the score>"}

Do not include any text outside the JSON object.
"""


def _build_judge_prompt(
    metric: MetricDefinition,
    conversation: ConversationRecord,
    turn_index: int | None,
    agent_schema: AgentSchema,
) -> str:
    """Build the user message for the judge LLM."""
    lines: list[str] = []

    # Agent context
    lines.append("=== AGENT CONTEXT ===")
    lines.append(f"Persona: {agent_schema.persona or 'Not specified'}")
    lines.append(f"Tone: {agent_schema.tone or 'Not specified'}")
    if agent_schema.global_rules:
        rules_text = "\n".join(f"  - {r}" for r in agent_schema.global_rules)
        lines.append(f"Global rules:\n{rules_text}")
    lines.append("")

    # Metric
    lines.append("=== METRIC TO EVALUATE ===")
    lines.append(f"Name: {metric.name}")
    lines.append(f"Description: {metric.description}")
    if metric.rubric:
        lines.append(f"Scoring rubric:\n{metric.rubric}")
    lines.append("")

    # Conversation excerpt
    if turn_index is not None:
        # Per-turn: show only the relevant turn pair
        history = conversation.history
        # Find the user+assistant pair at turn_index
        turn = next((t for t in conversation.turns if t.turn_index == turn_index), None)
        if turn:
            lines.append(f"=== TURN {turn_index} TO EVALUATE ===")
            lines.append(f"User: {turn.user_message}")
            lines.append(f"Agent: {turn.agent_content}")
            if turn.tool_calls_made:
                tools_summary = ", ".join(
                    tc.get("function", {}).get("name", "unknown")
                    for tc in turn.tool_calls_made
                )
                lines.append(f"[Tool calls: {tools_summary}]")
        else:
            # Fallback: show full history
            lines.append("=== CONVERSATION ===")
            for msg in history:
                role = msg.get("role", "unknown").upper()
                content = msg.get("content", "")
                if isinstance(content, list):
                    content = " ".join(
                        c.get("text", "") for c in content if isinstance(c, dict)
                    )
                lines.append(f"{role}: {content}")
    else:
        # Whole-conversation scope: show full history
        lines.append("=== FULL CONVERSATION ===")
        for msg in conversation.history:
            role = msg.get("role", "unknown").upper()
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    c.get("text", "") for c in content if isinstance(c, dict)
                )
            lines.append(f"{role}: {content}")

    lines.append("")
    lines.append("Respond ONLY with JSON: {\"score\": <1-5>, \"reasoning\": \"...\"}")

    return "\n".join(lines)


def _parse_judge_response(raw: str, metric_name: str) -> tuple[int, str]:
    """Extract (score, reasoning) from LLM response. Falls back gracefully."""
    # Try to find JSON in the response
    match = re.search(r'\{[^{}]+\}', raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            score = int(data.get("score", 3))
            reasoning = str(data.get("reasoning", "No reasoning provided."))
            return max(1, min(5, score)), reasoning
        except (json.JSONDecodeError, ValueError):
            pass

    log.warning("judge.parse_failed", metric=metric_name, raw=raw[:200])
    return 3, f"Could not parse judge response. Raw output: {raw[:300]}"


async def run_llm_judge(
    metric: MetricDefinition,
    conversation: ConversationRecord,
    turn_index: int | None,
    agent_schema: AgentSchema,
    judge_model: str,
) -> JudgeScore:
    """Run LLM-as-judge for a metric.

    Args:
        metric: The metric definition (must be type=llm_judge).
        conversation: Full conversation record for this dataset item.
        turn_index: None for whole_conversation scope, int for per_turn scope.
        agent_schema: Parsed agent YAML schema (for persona/tone context).
        judge_model: LiteLLM model string to use as judge.
    """
    user_prompt = _build_judge_prompt(metric, conversation, turn_index, agent_schema)

    try:
        response = await chat_completion(
            model=judge_model,
            messages=[
                {"role": "system", "content": _JUDGE_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            tools=None,
            temperature=0.0,          # deterministic scoring
            max_tokens=512,
        )
        raw_content = response.content or ""
    except Exception as exc:
        log.error("judge.llm_error", metric=metric.name, error=str(exc))
        return JudgeScore(
            metric_name=metric.name,
            scope=metric.scope,
            turn_index=turn_index,
            score=0.0,
            raw_score="error",
            reasoning=f"Judge LLM call failed: {exc}",
            model_used=judge_model,
        )

    raw_score_int, reasoning = _parse_judge_response(raw_content, metric.name)

    # Normalise 1–5 → 0.0–1.0
    normalised = (raw_score_int - 1) / 4.0

    passed = None
    if metric.threshold is not None:
        passed = normalised >= metric.threshold

    return JudgeScore(
        metric_name=metric.name,
        scope=metric.scope,
        turn_index=turn_index,
        score=normalised,
        raw_score=f"{raw_score_int}/5",
        reasoning=reasoning,
        model_used=judge_model,
        passed=passed,
    )
