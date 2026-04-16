"""Tool call accuracy metric — checks correct tools + required args."""

from __future__ import annotations

import json
from typing import Any

from saras.evals.metrics.base import BaseMetric, MetricInput, MetricResult
from saras.evals.metrics.registry import register


@register("tool_call_accuracy")
class ToolCallAccuracyMetric(BaseMetric):
    """Deterministic tool call accuracy — correct tools called with required args."""

    async def measure(self, inp: MetricInput) -> MetricResult:
        expected_tools = inp.expected_tools
        turn = inp.turn
        turn_index = inp.turn_index

        if not expected_tools or not turn:
            return MetricResult(
                metric_name=self.name,
                scope=self.definition.scope,
                turn_index=turn_index,
                score=1.0,
                raw_score="N/A",
                reasoning="No expected tool calls defined — skipped.",
                model_used="deterministic",
            )

        expected_this_turn = [t for t in expected_tools if t.get("turn") == turn_index]
        if not expected_this_turn:
            return MetricResult(
                metric_name=self.name,
                scope=self.definition.scope,
                turn_index=turn_index,
                score=1.0,
                raw_score="N/A",
                reasoning=f"No tool call expectation for turn {turn_index}.",
                model_used="deterministic",
            )

        actual_tool_names = {
            tc.get("function", {}).get("name", "") for tc in turn.tool_calls_made
        }

        hits = 0
        issues: list[str] = []
        for exp in expected_this_turn:
            exp_name = exp.get("tool_name", "").lower().replace(" ", "_")
            if exp_name not in actual_tool_names:
                issues.append(f"Expected tool '{exp['tool_name']}' was not called")
                continue
            required_args: list[str] = exp.get("required_args", [])
            matching_call = next(
                (
                    tc
                    for tc in turn.tool_calls_made
                    if tc.get("function", {}).get("name", "") == exp_name
                ),
                None,
            )
            if matching_call and required_args:
                args = matching_call.get("function", {}).get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                missing = [a for a in required_args if a not in args]
                if missing:
                    issues.append(
                        f"Tool '{exp['tool_name']}' missing args: {missing}"
                    )
                    continue
            hits += 1

        score = hits / len(expected_this_turn) if expected_this_turn else 1.0
        reasoning = (
            f"{hits}/{len(expected_this_turn)} expected tool calls correct."
            + (f" Issues: {'; '.join(issues)}" if issues else "")
        )

        return MetricResult(
            metric_name=self.name,
            scope=self.definition.scope,
            turn_index=turn_index,
            score=score,
            raw_score=f"{hits}/{len(expected_this_turn)}",
            reasoning=reasoning,
            model_used="deterministic",
            passed=self._apply_threshold(score),
        )
