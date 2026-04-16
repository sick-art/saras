"""Eval metric framework — class-based metrics with registry dispatch.

Usage::

    from saras.evals.metrics import build_metric, METRIC_REGISTRY
    from saras.evals.schemas import MetricDefinition

    defn = MetricDefinition(name="Semantic Sim", type="deterministic",
                            scope="per_turn", description="...",
                            preset="semantic_similarity")
    metric = build_metric(defn)
    result = await metric.measure(inp)
"""

from __future__ import annotations

import yaml

from saras.evals.metrics.base import BaseMetric, MetricInput, MetricResult
from saras.evals.metrics.registry import METRIC_REGISTRY, build_metric, register
from saras.evals.presets import resolve_metric
from saras.evals.schemas import MetricDefinition

# Import all metric modules to trigger @register decorators
from saras.evals.metrics import (  # noqa: F401
    bleu,
    completion_metrics,
    context_metrics,
    llm_judge,
    quality_metrics,
    rouge_l,
    semantic_similarity,
    slot_fill_efficiency,
    tone_metric,
    tool_call_accuracy,
)


# ── Metric set YAML parser ────────────────────────────────────────────────────


def parse_metric_set(yaml_content: str) -> list[MetricDefinition]:
    """Parse a metric set YAML string into resolved MetricDefinition objects."""
    data = yaml.safe_load(yaml_content) or {}
    raw_metrics: list[dict] = data.get("metrics", [])
    return [resolve_metric(m) for m in raw_metrics]


__all__ = [
    "BaseMetric",
    "MetricInput",
    "MetricResult",
    "METRIC_REGISTRY",
    "build_metric",
    "register",
    "parse_metric_set",
    # Legacy functional shims — kept for backward compatibility with old tests
    "score_bleu",
    "score_rouge_l",
    "score_slot_fill_efficiency",
    "score_tool_call_accuracy",
]


# ── Legacy functional shims ───────────────────────────────────────────────────
# These wrap the new class-based metrics and return JudgeScore for backwards
# compatibility with code that used the old saras.evals.metrics module.

import asyncio as _asyncio
from saras.evals.schemas import JudgeScore as _JudgeScore, TurnRecord as _TurnRecord


def _result_to_judge_score(result: MetricResult) -> _JudgeScore:
    return _JudgeScore(
        metric_name=result.metric_name,
        scope=result.scope,
        turn_index=result.turn_index,
        score=result.score,
        raw_score=result.raw_score,
        reasoning=result.reasoning,
        model_used=result.model_used,
        passed=result.passed,
    )


def _run(coro):  # type: ignore[no-untyped-def]
    """Run a coroutine synchronously, compatible with existing event loops."""
    try:
        loop = _asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(_asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return _asyncio.run(coro)


def _make_defn(preset_key: str, source: MetricDefinition) -> MetricDefinition:
    """Build a MetricDefinition with the correct preset from a legacy definition."""
    return MetricDefinition(
        name=source.name,
        type=source.type,
        scope=source.scope,
        description=source.description,
        preset=preset_key,
        threshold=source.threshold,
        rubric=source.rubric,
    )


def score_rouge_l(metric: MetricDefinition, *, actual: str, expected: str) -> _JudgeScore:
    """Legacy shim: score ROUGE-L using the class-based RougeLMetric."""
    m = build_metric(_make_defn("rouge_l", metric))
    turn = _TurnRecord(
        turn_index=0, user_message="", agent_content=actual, turn_type="response"
    )
    inp = MetricInput(turn=turn, expected_text=expected, turn_index=0)
    result = _run(m.measure(inp))
    return _result_to_judge_score(result)


def score_bleu(metric: MetricDefinition, *, actual: str, expected: str) -> _JudgeScore:
    """Legacy shim: score BLEU-4 using the class-based BleuMetric."""
    m = build_metric(_make_defn("bleu", metric))
    turn = _TurnRecord(
        turn_index=0, user_message="", agent_content=actual, turn_type="response"
    )
    inp = MetricInput(turn=turn, expected_text=expected, turn_index=0)
    result = _run(m.measure(inp))
    return _result_to_judge_score(result)


def score_tool_call_accuracy(
    metric: MetricDefinition,
    turn: _TurnRecord,
    *,
    expected_tools: list[dict] | None,
    turn_index: int,
) -> _JudgeScore:
    """Legacy shim: score tool call accuracy using the class-based metric."""
    m = build_metric(_make_defn("tool_call_accuracy", metric))
    inp = MetricInput(turn=turn, expected_tools=expected_tools, turn_index=turn_index)
    result = _run(m.measure(inp))
    return _result_to_judge_score(result)


def score_slot_fill_efficiency(
    metric: MetricDefinition,
    turn: _TurnRecord,
    *,
    turn_index: int,
) -> _JudgeScore:
    """Legacy shim: score slot fill efficiency using the class-based metric."""
    m = build_metric(_make_defn("slot_fill_efficiency", metric))
    inp = MetricInput(turn=turn, turn_index=turn_index)
    result = _run(m.measure(inp))
    return _result_to_judge_score(result)
