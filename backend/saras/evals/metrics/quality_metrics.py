"""Quality metrics: Hallucination detection and Helpfulness.

Both are per-turn LLM-as-judge metrics.
"""

from __future__ import annotations

from saras.evals.metrics.base import MetricInput
from saras.evals.metrics.llm_judge import (
    LLMJudgeMetric,
    _build_agent_context,
    _build_conversation_excerpt,
)
from saras.evals.metrics.registry import register


# ── Hallucination Detection ────────────────────────────────────────────────────


@register("hallucination_detection")
class HallucinationMetric(LLMJudgeMetric):
    """Per-turn LLM judge: did the agent state anything not grounded in sources?"""

    @property
    def rubric(self) -> str:
        return """\
1 - Clear hallucination: agent stated fabricated facts not grounded in any available source
2 - Likely hallucination: agent stated specific claims with no apparent grounding
3 - Uncertain: response contains claims that could be inferred but aren't clearly grounded
4 - Mostly grounded: minor extrapolation but no clear fabrication
5 - Fully grounded: every claim is traceable to tool results, the agent schema, or user input"""

    def _build_prompt(self, inp: MetricInput) -> str:
        lines = _build_agent_context(inp)
        lines += [
            "=== METRIC TO EVALUATE ===",
            f"Name: {self.name}",
            f"Description: Did the agent state anything not grounded in tool results, "
            "the agent schema, or information the user explicitly provided?",
            f"Scoring rubric:\n{self.rubric}",
        ]
        lines += _build_conversation_excerpt(inp)
        lines.append(
            'Respond ONLY with JSON: {"score": <1-5>, "reasoning": "..."}'
        )
        return "\n".join(lines)


# ── Helpfulness ─────────────────────────────────────────────────────────────────


@register("helpfulness")
class HelpfulnessMetric(LLMJudgeMetric):
    """Per-turn LLM judge: did the agent help the user accomplish their intent?"""

    @property
    def rubric(self) -> str:
        return """\
1 - Actively unhelpful or misleading — the response makes the user's situation worse
2 - Mostly unhelpful — the response is tangential, evasive, or misses the user's intent
3 - Somewhat helpful — partial answer but lacks completeness or clarity
4 - Very helpful — addresses the user's need clearly and thoroughly
5 - Proactively helpful — not only answers the question but anticipates follow-up needs"""

    def _build_prompt(self, inp: MetricInput) -> str:
        lines = _build_agent_context(inp)
        lines += [
            "=== METRIC TO EVALUATE ===",
            f"Name: {self.name}",
            "Description: Did the agent help the user accomplish their intent? "
            "Consider clarity, completeness, and proactiveness.",
            f"Scoring rubric:\n{self.rubric}",
        ]
        lines += _build_conversation_excerpt(inp)
        lines.append(
            'Respond ONLY with JSON: {"score": <1-5>, "reasoning": "..."}'
        )
        return "\n".join(lines)
