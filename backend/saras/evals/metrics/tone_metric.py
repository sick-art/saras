"""Tone metric: Tone Consistency.

Per-turn LLM-as-judge metric evaluating tone and persona adherence.
"""

from __future__ import annotations

from saras.evals.metrics.base import MetricInput
from saras.evals.metrics.llm_judge import (
    LLMJudgeMetric,
    _build_agent_context,
    _build_conversation_excerpt,
)
from saras.evals.metrics.registry import register


@register("tone_consistency")
class ToneConsistencyMetric(LLMJudgeMetric):
    """Per-turn LLM judge: does the agent's tone match its configured persona?"""

    @property
    def rubric(self) -> str:
        return """\
1 - Completely off-tone or out of character
2 - Noticeably inconsistent with defined persona/tone
3 - Generally appropriate but a few phrases feel off
4 - Consistent tone with only very minor lapses
5 - Perfectly on-tone throughout"""

    def _build_prompt(self, inp: MetricInput) -> str:
        lines = _build_agent_context(inp)
        lines += [
            "=== METRIC TO EVALUATE ===",
            f"Name: {self.name}",
            "Description: Does the agent's response match the tone and persona "
            "defined in its configuration?",
            f"Scoring rubric:\n{self.rubric}",
        ]
        lines += _build_conversation_excerpt(inp)
        lines.append(
            'Respond ONLY with JSON: {"score": <1-5>, "reasoning": "..."}'
        )
        return "\n".join(lines)
