"""LLM-as-judge base metric.

Holds the shared judge prompt structure, LLM call, and JSON response parsing.
Subclasses define their rubric and ``_build_prompt()`` override.
"""

from __future__ import annotations

import json
import re
from abc import abstractmethod

import structlog

from saras.evals.metrics.base import BaseMetric, MetricInput, MetricResult
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


class LLMJudgeMetric(BaseMetric):
    """Abstract base for all LLM-as-judge metrics.

    Subclasses must implement :attr:`rubric` and :meth:`_build_prompt`.
    The shared :meth:`measure` handles the LLM call, JSON parsing, and
    1-5 → 0.0-1.0 normalisation.
    """

    def __init__(self, definition: object, *, judge_model: str) -> None:
        from saras.evals.schemas import MetricDefinition

        super().__init__(definition=definition)  # type: ignore[arg-type]
        self.judge_model = judge_model

    @property
    @abstractmethod
    def rubric(self) -> str:
        """Return the 1-5 scoring rubric for this metric."""
        ...

    @abstractmethod
    def _build_prompt(self, inp: MetricInput) -> str:
        """Build the user message for the judge LLM."""
        ...

    async def measure(self, inp: MetricInput) -> MetricResult:
        user_prompt = self._build_prompt(inp)

        try:
            response = await chat_completion(
                model=self.judge_model,
                messages=[
                    {"role": "system", "content": _JUDGE_SYSTEM},
                    {"role": "user", "content": user_prompt},
                ],
                tools=None,
                temperature=0.0,
                max_tokens=512,
            )
            raw_content = response.content or ""
        except Exception as exc:
            log.error("judge.llm_error", metric=self.name, error=str(exc))
            return MetricResult(
                metric_name=self.name,
                scope=self.definition.scope,
                turn_index=inp.turn_index,
                score=0.0,
                raw_score="error",
                reasoning=f"Judge LLM call failed: {exc}",
                model_used=self.judge_model,
            )

        raw_score_int, reasoning = _parse_judge_response(raw_content, self.name)
        normalised = (raw_score_int - 1) / 4.0

        return MetricResult(
            metric_name=self.name,
            scope=self.definition.scope,
            turn_index=inp.turn_index,
            score=normalised,
            raw_score=f"{raw_score_int}/5",
            reasoning=reasoning,
            model_used=self.judge_model,
            passed=self._apply_threshold(normalised),
        )


# ── Shared helpers ─────────────────────────────────────────────────────────────


def _parse_judge_response(raw: str, metric_name: str) -> tuple[int, str]:
    """Extract (score, reasoning) from LLM response."""
    match = re.search(r"\{[^{}]+\}", raw, re.DOTALL)
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


def _build_agent_context(inp: MetricInput) -> list[str]:
    """Build the agent persona/tone context lines for a judge prompt."""
    lines: list[str] = ["=== AGENT CONTEXT ==="]
    schema = inp.agent_schema
    if schema is not None:
        persona = getattr(schema, "persona", None)
        tone = getattr(schema, "tone", None)
        rules = getattr(schema, "global_rules", None)
        lines.append(f"Persona: {persona or 'Not specified'}")
        lines.append(f"Tone: {tone or 'Not specified'}")
        if rules:
            rules_text = "\n".join(f"  - {r}" for r in rules)
            lines.append(f"Global rules:\n{rules_text}")
    lines.append("")
    return lines


def _build_conversation_excerpt(inp: MetricInput) -> list[str]:
    """Build conversation history lines for a judge prompt."""
    lines: list[str] = []
    conversation = inp.conversation

    if inp.turn is not None and inp.turn_index is not None:
        turn = inp.turn
        lines.append(f"=== TURN {inp.turn_index} TO EVALUATE ===")
        lines.append(f"User: {turn.user_message}")
        lines.append(f"Agent: {turn.agent_content}")
        if turn.tool_calls_made:
            tools_summary = ", ".join(
                tc.get("function", {}).get("name", "unknown")
                for tc in turn.tool_calls_made
            )
            lines.append(f"[Tool calls: {tools_summary}]")
    elif conversation is not None:
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
    return lines
