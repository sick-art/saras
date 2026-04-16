"""ROUGE-L metric — longest common subsequence F1."""

from __future__ import annotations

from saras.evals.metrics.base import BaseMetric, MetricInput, MetricResult
from saras.evals.metrics.registry import register


def _get_rouge_scorer():
    try:
        from rouge_score import rouge_scorer  # type: ignore[import]

        return rouge_scorer.RougeScorer(["rougeL"], use_stemmer=True)
    except ImportError:
        raise RuntimeError(
            "rouge-score is not installed. Add it to pyproject.toml: rouge-score>=0.1.2"
        )


@register("rouge_l")
class RougeLMetric(BaseMetric):
    """Deterministic ROUGE-L F1 between actual and expected text."""

    async def measure(self, inp: MetricInput) -> MetricResult:
        actual = (inp.turn.agent_content if inp.turn else "") or ""
        expected = inp.expected_text or ""

        scorer = _get_rouge_scorer()
        result = scorer.score(expected, actual)
        f1: float = result["rougeL"].fmeasure  # type: ignore[index]

        return MetricResult(
            metric_name=self.name,
            scope=self.definition.scope,
            turn_index=inp.turn_index,
            score=f1,
            raw_score=f"{f1:.3f}",
            reasoning=f"ROUGE-L F1 = {f1:.3f}",
            model_used="rouge-score",
            passed=self._apply_threshold(f1),
        )
