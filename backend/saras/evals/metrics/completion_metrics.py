"""Completion metrics: Goal Completion.

Whole-conversation LLM-as-judge metric.
"""

from __future__ import annotations

from saras.evals.metrics.base import MetricInput
from saras.evals.metrics.llm_judge import (
    LLMJudgeMetric,
    _build_agent_context,
    _build_conversation_excerpt,
)
from saras.evals.metrics.registry import register


@register("goal_completion")
class GoalCompletionMetric(LLMJudgeMetric):
    """Whole-conversation LLM judge: did the agent achieve the user's goal?"""

    @property
    def rubric(self) -> str:
        return """\
1 - Goal not addressed or agent failed entirely
2 - Agent attempted but missed key steps or gave wrong information
3 - Goal partially complete — main intent addressed but gaps remain
4 - Goal complete with only minor gaps or unnecessary friction
5 - Goal fully and gracefully achieved, user would leave satisfied"""

    def _build_prompt(self, inp: MetricInput) -> str:
        lines = _build_agent_context(inp)
        lines += [
            "=== METRIC TO EVALUATE ===",
            f"Name: {self.name}",
            "Description: Did the agent fully achieve the user's stated goal "
            "by the end of the conversation?",
            f"Scoring rubric:\n{self.rubric}",
        ]
        lines += _build_conversation_excerpt(inp)
        lines.append(
            'Respond ONLY with JSON: {"score": <1-5>, "reasoning": "..."}'
        )
        return "\n".join(lines)
