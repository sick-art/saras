"""Context metrics: Context Precision and Context Recall.

Both are per-turn LLM-as-judge metrics evaluating how the agent uses context.
"""

from __future__ import annotations

from saras.evals.metrics.base import MetricInput
from saras.evals.metrics.llm_judge import (
    LLMJudgeMetric,
    _build_agent_context,
    _build_conversation_excerpt,
)
from saras.evals.metrics.registry import register


@register("context_precision")
class ContextPrecisionMetric(LLMJudgeMetric):
    """Per-turn LLM judge: did the agent use only relevant context?"""

    @property
    def rubric(self) -> str:
        return """\
1 - Response dominated by irrelevant context or the wrong topic entirely
2 - Significant irrelevant content mixed with relevant
3 - Mostly relevant with one or two unnecessary diversions
4 - Highly relevant with only minor tangents
5 - Perfectly precise: only relevant context, nothing extraneous"""

    def _build_prompt(self, inp: MetricInput) -> str:
        lines = _build_agent_context(inp)
        lines += [
            "=== METRIC TO EVALUATE ===",
            f"Name: {self.name}",
            "Description: Did the agent use only relevant context in its response? "
            "Penalises injecting irrelevant information or confusing the user with "
            "unrelated topics.",
            f"Scoring rubric:\n{self.rubric}",
        ]
        lines += _build_conversation_excerpt(inp)
        lines.append(
            'Respond ONLY with JSON: {"score": <1-5>, "reasoning": "..."}'
        )
        return "\n".join(lines)


@register("context_recall")
class ContextRecallMetric(LLMJudgeMetric):
    """Per-turn LLM judge: did the agent include all relevant information?"""

    @property
    def rubric(self) -> str:
        return """\
1 - Critical information omitted — user is left without key details they need
2 - Several important pieces of available information were not surfaced
3 - Most relevant info included but one notable gap
4 - Nearly complete — only minor details omitted
5 - Comprehensive: agent surfaced all relevant available information"""

    def _build_prompt(self, inp: MetricInput) -> str:
        lines = _build_agent_context(inp)
        lines += [
            "=== METRIC TO EVALUATE ===",
            f"Name: {self.name}",
            "Description: Did the agent include all relevant information it had "
            "access to (from tool results, prior slots, agent knowledge) in its "
            "response?",
            f"Scoring rubric:\n{self.rubric}",
        ]
        lines += _build_conversation_excerpt(inp)
        lines.append(
            'Respond ONLY with JSON: {"score": <1-5>, "reasoning": "..."}'
        )
        return "\n".join(lines)
