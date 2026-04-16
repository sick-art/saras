"""Slot fill efficiency metric — penalises redundant or missed slot questions."""

from __future__ import annotations

from saras.evals.metrics.base import BaseMetric, MetricInput, MetricResult
from saras.evals.metrics.registry import register


@register("slot_fill_efficiency")
class SlotFillEfficiencyMetric(BaseMetric):
    """Deterministic slot fill efficiency score."""

    async def measure(self, inp: MetricInput) -> MetricResult:
        turn = inp.turn
        if not turn:
            return MetricResult(
                metric_name=self.name,
                scope=self.definition.scope,
                turn_index=inp.turn_index,
                score=1.0,
                raw_score="N/A",
                reasoning="No turn data — skipped.",
                model_used="deterministic",
            )

        decision = turn.router_decision or {}
        unfilled = decision.get("unfilled_slots", [])
        issues: list[str] = []

        if turn.turn_type == "slot_fill":
            if not unfilled:
                issues.append(
                    "Agent asked a slot-fill question despite no unfilled required slots"
                )
        elif turn.turn_type == "response" and unfilled:
            issues.append(
                f"Agent responded without filling required slots: {unfilled}"
            )

        if issues:
            score = 0.5
            reasoning = "Slot fill issues: " + "; ".join(issues)
        else:
            score = 1.0
            reasoning = "Slot fill behaviour is efficient for this turn."

        return MetricResult(
            metric_name=self.name,
            scope=self.definition.scope,
            turn_index=inp.turn_index,
            score=score,
            raw_score=f"{score:.1f}",
            reasoning=reasoning,
            model_used="deterministic",
            passed=self._apply_threshold(score),
        )
