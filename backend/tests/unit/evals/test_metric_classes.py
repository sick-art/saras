"""Tests for the class-based metric framework.

Covers:
  - Registry: all presets registered, build_metric factory, unknown preset error
  - BaseMetric: _apply_threshold
  - Deterministic metrics: semantic similarity, tool call accuracy, slot fill
  - LLM judge metrics: prompt building, response parsing, mocked measure
"""

from __future__ import annotations

import pytest

from saras.evals.metrics import METRIC_REGISTRY, build_metric, parse_metric_set
from saras.evals.metrics.base import BaseMetric, MetricInput, MetricResult
from saras.evals.metrics.llm_judge import _parse_judge_response
from saras.evals.presets import PRESET_METRICS
from saras.evals.schemas import MetricDefinition, TurnRecord


# ── Fixtures ───────────────────────────────────────────────────────────────────


def _defn(preset: str, **overrides) -> MetricDefinition:
    """Create a MetricDefinition for testing."""
    base = {
        "name": preset,
        "type": "deterministic",
        "scope": "per_turn",
        "description": "test metric",
        "preset": preset,
    }
    base.update(overrides)
    return MetricDefinition(**base)


def _turn(content: str = "hello there", *, turn_index: int = 0) -> TurnRecord:
    return TurnRecord(
        turn_index=turn_index,
        user_message="hi",
        agent_content=content,
        turn_type="response",
    )


def _inp(**overrides) -> MetricInput:
    defaults = {
        "turn": _turn(),
        "expected_text": "hello there",
        "turn_index": 0,
    }
    defaults.update(overrides)
    return MetricInput(**defaults)


# ── Registry tests ─────────────────────────────────────────────────────────────


class TestRegistry:
    def test_all_presets_registered(self):
        """Every preset in PRESET_METRICS should have a registered metric class."""
        for key in PRESET_METRICS:
            assert key in METRIC_REGISTRY, f"Preset '{key}' not in METRIC_REGISTRY"

    def test_unknown_preset_raises(self):
        defn = _defn("nonexistent_metric")
        with pytest.raises(ValueError, match="No metric class registered"):
            build_metric(defn)

    def test_build_metric_returns_base_metric(self):
        defn = _defn("semantic_similarity")
        metric = build_metric(defn)
        assert isinstance(metric, BaseMetric)

    def test_build_metric_passes_judge_model(self):
        defn = _defn("hallucination_detection", type="llm_judge")
        metric = build_metric(defn, judge_model="gpt-4o")
        assert hasattr(metric, "judge_model")
        assert metric.judge_model == "gpt-4o"


# ── BaseMetric tests ───────────────────────────────────────────────────────────


class TestBaseMetric:
    def test_apply_threshold_none(self):
        defn = _defn("semantic_similarity")
        metric = build_metric(defn)
        assert metric._apply_threshold(0.5) is None

    def test_apply_threshold_pass(self):
        defn = _defn("semantic_similarity", threshold=0.7)
        metric = build_metric(defn)
        assert metric._apply_threshold(0.8) is True

    def test_apply_threshold_fail(self):
        defn = _defn("semantic_similarity", threshold=0.7)
        metric = build_metric(defn)
        assert metric._apply_threshold(0.3) is False

    def test_name_property(self):
        defn = _defn("semantic_similarity", name="My Custom Name")
        metric = build_metric(defn)
        assert metric.name == "My Custom Name"


# ── Deterministic metric tests ─────────────────────────────────────────────────


class TestSemanticSimilarity:
    @pytest.mark.asyncio
    async def test_identical_text(self):
        defn = _defn("semantic_similarity")
        metric = build_metric(defn)
        inp = _inp(expected_text="hello there", turn=_turn("hello there"))
        result = await metric.measure(inp)
        assert isinstance(result, MetricResult)
        assert result.score > 0.95
        assert result.model_used == "sentence-transformers/all-MiniLM-L6-v2"

    @pytest.mark.asyncio
    async def test_dissimilar_text(self):
        defn = _defn("semantic_similarity")
        metric = build_metric(defn)
        inp = _inp(expected_text="the weather is sunny", turn=_turn("quantum physics equations"))
        result = await metric.measure(inp)
        assert 0.0 <= result.score <= 1.0
        assert result.score < 0.5

    @pytest.mark.asyncio
    async def test_threshold_applied(self):
        defn = _defn("semantic_similarity", threshold=0.5)
        metric = build_metric(defn)
        inp = _inp(expected_text="hello there", turn=_turn("hello there"))
        result = await metric.measure(inp)
        assert result.passed is True


class TestToolCallAccuracy:
    @pytest.mark.asyncio
    async def test_no_expectations(self):
        defn = _defn("tool_call_accuracy", scope="tool_call")
        metric = build_metric(defn)
        inp = _inp(expected_tools=None)
        result = await metric.measure(inp)
        assert result.score == 1.0
        assert result.model_used == "deterministic"

    @pytest.mark.asyncio
    async def test_correct_tool_called(self):
        defn = _defn("tool_call_accuracy", scope="tool_call")
        metric = build_metric(defn)
        inp = _inp(
            turn=TurnRecord(
                turn_index=0,
                user_message="lookup",
                agent_content="found it",
                turn_type="response",
                tool_calls_made=[
                    {"function": {"name": "order_lookup", "arguments": {"order_number": "123"}}}
                ],
            ),
            expected_tools=[{"turn": 0, "tool_name": "Order Lookup", "required_args": ["order_number"]}],
            turn_index=0,
        )
        result = await metric.measure(inp)
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_missing_tool(self):
        defn = _defn("tool_call_accuracy", scope="tool_call")
        metric = build_metric(defn)
        inp = _inp(
            turn=_turn(),
            expected_tools=[{"turn": 0, "tool_name": "Order Lookup", "required_args": []}],
            turn_index=0,
        )
        result = await metric.measure(inp)
        assert result.score == 0.0
        assert "not called" in result.reasoning


class TestSlotFillEfficiency:
    @pytest.mark.asyncio
    async def test_efficient_response(self):
        defn = _defn("slot_fill_efficiency")
        metric = build_metric(defn)
        inp = _inp(turn=_turn())
        result = await metric.measure(inp)
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_redundant_slot_fill(self):
        defn = _defn("slot_fill_efficiency")
        metric = build_metric(defn)
        inp = _inp(
            turn=TurnRecord(
                turn_index=0,
                user_message="hi",
                agent_content="what's your order number?",
                turn_type="slot_fill",
                router_decision={"unfilled_slots": []},
            ),
        )
        result = await metric.measure(inp)
        assert result.score == 0.5
        assert "redundant" in result.reasoning.lower() or "no unfilled" in result.reasoning.lower()


# ── LLM Judge tests ────────────────────────────────────────────────────────────


class TestLLMJudge:
    def test_parse_judge_response_valid(self):
        raw = '{"score": 4, "reasoning": "Good response."}'
        score, reasoning = _parse_judge_response(raw, "test")
        assert score == 4
        assert "Good" in reasoning

    def test_parse_judge_response_with_surrounding_text(self):
        raw = 'Here is my evaluation:\n{"score": 2, "reasoning": "Partial."}\nHope this helps.'
        score, reasoning = _parse_judge_response(raw, "test")
        assert score == 2

    def test_parse_judge_response_clamps_score(self):
        raw = '{"score": 7, "reasoning": "Too high"}'
        score, _ = _parse_judge_response(raw, "test")
        assert score == 5

    def test_parse_judge_response_invalid_returns_default(self):
        raw = "I cannot evaluate this."
        score, reasoning = _parse_judge_response(raw, "test")
        assert score == 3  # default
        assert "Could not parse" in reasoning

    @pytest.mark.asyncio
    async def test_hallucination_metric_builds(self):
        defn = _defn("hallucination_detection", type="llm_judge")
        metric = build_metric(defn, judge_model="gpt-4o")
        assert metric.name == "hallucination_detection"
        assert metric.judge_model == "gpt-4o"
        assert len(metric.rubric) > 0

    @pytest.mark.asyncio
    async def test_helpfulness_metric_builds(self):
        defn = _defn("helpfulness", type="llm_judge")
        metric = build_metric(defn, judge_model="gpt-4o")
        assert metric.name == "helpfulness"
        assert len(metric.rubric) > 0


# ── parse_metric_set tests ────────────────────────────────────────────────────


class TestParseMetricSet:
    def test_parses_preset_yaml(self):
        yaml_content = "metrics:\n  - preset: semantic_similarity\n  - preset: tool_call_accuracy"
        result = parse_metric_set(yaml_content)
        assert len(result) == 2
        assert result[0].preset == "semantic_similarity"
        assert result[1].preset == "tool_call_accuracy"

    def test_empty_yaml(self):
        result = parse_metric_set("metrics: []")
        assert result == []

    def test_helpfulness_preset_parsable(self):
        yaml_content = "metrics:\n  - preset: helpfulness"
        result = parse_metric_set(yaml_content)
        assert len(result) == 1
        assert result[0].preset == "helpfulness"
        assert result[0].type == "llm_judge"
