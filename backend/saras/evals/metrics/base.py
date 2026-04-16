"""Base abstractions for the eval metric framework.

Every metric inherits from BaseMetric and implements ``async measure()``.
Metrics are stateless callables — they hold configuration (threshold, model name)
but never conversation state. Inspired by RAGAS's composable metric pattern.

MetricInput is a unified envelope — each metric picks the fields it needs.
MetricResult replaces JudgeScore (structurally identical fields).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from saras.evals.schemas import (
        ConversationRecord,
        MetricDefinition,
        TurnRecord,
    )


# ── Input / Output models ──────────────────────────────────────────────────────


class MetricInput(BaseModel):
    """Unified input envelope for all metrics.

    Each metric reads only the fields it needs. The runner populates all
    fields so that every metric receives a complete picture of the turn
    or conversation it is scoring.
    """

    turn: Any | None = None  # TurnRecord
    expected_text: str | None = None
    expected_tools: list[dict[str, Any]] | None = None
    conversation: Any | None = None  # ConversationRecord
    agent_schema: Any | None = None  # AgentSchema
    turn_index: int = 0
    metric_definition: Any | None = None  # MetricDefinition


class MetricResult(BaseModel):
    """Result returned by every metric.

    Replaces the earlier JudgeScore with the same field names and semantics.
    ``score`` is always normalised to [0.0, 1.0].
    """

    metric_name: str
    scope: str
    turn_index: int | None = None
    score: float  # 0.0-1.0
    raw_score: str  # e.g. "4/5" or "0.82"
    reasoning: str
    model_used: str
    passed: bool | None = None


# ── Base metric ────────────────────────────────────────────────────────────────


class BaseMetric(ABC):
    """Abstract base for all eval metrics.

    Subclasses must implement :meth:`measure` which takes a :class:`MetricInput`
    and returns a :class:`MetricResult`. All metrics are async-first.
    """

    def __init__(self, definition: Any) -> None:
        self.definition = definition

    @property
    def name(self) -> str:
        return self.definition.name

    @property
    def threshold(self) -> float | None:
        return self.definition.threshold

    @abstractmethod
    async def measure(self, inp: MetricInput) -> MetricResult:
        """Score the input and return a MetricResult."""
        ...

    def _apply_threshold(self, score: float) -> bool | None:
        """Return ``True`` if *score* meets the threshold, ``False`` if not,
        or ``None`` when no threshold is configured."""
        if self.threshold is not None:
            return score >= self.threshold
        return None
