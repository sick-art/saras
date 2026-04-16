"""BLEU-4 metric — n-gram precision."""

from __future__ import annotations

from saras.evals.metrics.base import BaseMetric, MetricInput, MetricResult
from saras.evals.metrics.registry import register


@register("bleu")
class BleuMetric(BaseMetric):
    """Deterministic BLEU-4 score between actual and expected text."""

    async def measure(self, inp: MetricInput) -> MetricResult:
        try:
            from nltk.translate.bleu_score import (  # type: ignore[import]
                SmoothingFunction,
                sentence_bleu,
            )
        except ImportError:
            raise RuntimeError(
                "nltk is not installed. Add it to pyproject.toml: nltk>=3.8.0"
            )

        actual = (inp.turn.agent_content if inp.turn else "") or ""
        expected = inp.expected_text or ""

        reference = [expected.split()]
        hypothesis = actual.split()
        smoothing = SmoothingFunction().method1
        bleu: float = sentence_bleu(
            reference, hypothesis, smoothing_function=smoothing
        )

        return MetricResult(
            metric_name=self.name,
            scope=self.definition.scope,
            turn_index=inp.turn_index,
            score=bleu,
            raw_score=f"{bleu:.3f}",
            reasoning=f"BLEU-4 = {bleu:.3f}",
            model_used="nltk",
            passed=self._apply_threshold(bleu),
        )
