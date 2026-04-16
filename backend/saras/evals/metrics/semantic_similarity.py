"""Semantic similarity metric — cosine similarity via sentence-transformers."""

from __future__ import annotations

from saras.evals.metrics.base import BaseMetric, MetricInput, MetricResult
from saras.evals.metrics.registry import register


def _get_sentence_model():
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore[import]

        return SentenceTransformer("all-MiniLM-L6-v2")
    except ImportError:
        raise RuntimeError(
            "sentence-transformers is not installed. "
            "Add it to pyproject.toml: sentence-transformers>=2.7.0"
        )


@register("semantic_similarity")
class SemanticSimilarityMetric(BaseMetric):
    """Deterministic cosine similarity between actual and expected text."""

    async def measure(self, inp: MetricInput) -> MetricResult:
        import numpy as np  # type: ignore[import]

        actual = (inp.turn.agent_content if inp.turn else "") or ""
        expected = inp.expected_text or ""

        model = _get_sentence_model()
        embeddings = model.encode([actual, expected], convert_to_numpy=True)
        a, b = embeddings[0], embeddings[1]
        cos_sim: float = float(
            np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10)
        )
        cos_sim = max(0.0, min(1.0, cos_sim))

        return MetricResult(
            metric_name=self.name,
            scope=self.definition.scope,
            turn_index=inp.turn_index,
            score=cos_sim,
            raw_score=f"{cos_sim:.3f}",
            reasoning=f"Cosine similarity = {cos_sim:.3f}",
            model_used="sentence-transformers/all-MiniLM-L6-v2",
            passed=self._apply_threshold(cos_sim),
        )
