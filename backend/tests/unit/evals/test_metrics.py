"""Unit tests for saras.evals.metrics — deterministic scorers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from saras.evals.metrics import (
    score_bleu,
    score_rouge_l,
    score_slot_fill_efficiency,
    score_tool_call_accuracy,
)
from saras.evals.schemas import JudgeScore, MetricDefinition, TurnRecord


# ── Fixture helpers ───────────────────────────────────────────────────────────

def make_metric(
    name: str = "test_metric",
    type: str = "deterministic",
    scope: str = "whole_conversation",
    threshold: float | None = None,
) -> MetricDefinition:
    return MetricDefinition(
        name=name,
        type=type,
        scope=scope,
        description="Test metric",
        threshold=threshold,
    )


def make_turn(
    turn_type: str = "response",
    tool_calls: list | None = None,
    router_decision: dict | None = None,
) -> TurnRecord:
    return TurnRecord(
        turn_index=1,
        user_message="Hello",
        agent_content="Hi there!",
        turn_type=turn_type,
        tool_calls_made=tool_calls or [],
        router_decision=router_decision,
    )


# ── ROUGE-L ───────────────────────────────────────────────────────────────────

def test_rouge_l_perfect_match():
    metric = make_metric()
    result = score_rouge_l(metric, actual="hello world", expected="hello world")
    assert result.score == pytest.approx(1.0)


def test_rouge_l_empty_prediction():
    metric = make_metric()
    result = score_rouge_l(metric, actual="", expected="hello world")
    assert result.score == pytest.approx(0.0)


def test_rouge_l_partial_overlap():
    metric = make_metric()
    result = score_rouge_l(
        metric,
        actual="The order is on its way",
        expected="Your order is currently on its way to you",
    )
    assert 0.0 < result.score < 1.0


def test_rouge_l_score_in_range():
    metric = make_metric()
    result = score_rouge_l(metric, actual="some prediction", expected="some reference text")
    assert 0.0 <= result.score <= 1.0


def test_rouge_l_returns_judge_score():
    metric = make_metric(name="rouge_test")
    result = score_rouge_l(metric, actual="test", expected="test")
    assert isinstance(result, JudgeScore)
    assert result.metric_name == "rouge_test"
    assert result.model_used == "rouge-score"


def test_rouge_l_threshold_passed():
    metric = make_metric(threshold=0.5)
    result = score_rouge_l(metric, actual="hello world", expected="hello world")
    assert result.passed is True


def test_rouge_l_threshold_failed():
    metric = make_metric(threshold=0.9)
    result = score_rouge_l(metric, actual="completely different", expected="hello world test")
    assert result.passed is False


def test_rouge_l_no_threshold_passed_is_none():
    metric = make_metric(threshold=None)
    result = score_rouge_l(metric, actual="hello", expected="hello")
    assert result.passed is None


# ── BLEU-4 ────────────────────────────────────────────────────────────────────

def test_bleu_perfect_match():
    metric = make_metric()
    result = score_bleu(metric, actual="hello world test sentence", expected="hello world test sentence")
    assert result.score == pytest.approx(1.0, abs=0.01)


def test_bleu_empty_prediction():
    metric = make_metric()
    result = score_bleu(metric, actual="", expected="hello world")
    assert result.score == pytest.approx(0.0, abs=0.01)


def test_bleu_score_in_range():
    metric = make_metric()
    result = score_bleu(metric, actual="some text here", expected="other reference text there")
    assert 0.0 <= result.score <= 1.0


def test_bleu_returns_judge_score():
    metric = make_metric(name="bleu_test")
    result = score_bleu(metric, actual="test", expected="test")
    assert isinstance(result, JudgeScore)
    assert result.metric_name == "bleu_test"
    assert result.model_used == "nltk"


# ── Tool call accuracy ────────────────────────────────────────────────────────

def test_tool_accuracy_no_expectations_is_neutral():
    """When expected_tools is None, score=1.0 (cannot judge)."""
    metric = make_metric(scope="tool_call")
    turn = make_turn()
    result = score_tool_call_accuracy(metric, turn, expected_tools=None, turn_index=1)
    assert result.score == pytest.approx(1.0)


def test_tool_accuracy_no_expectations_for_this_turn():
    """When expected_tools has entries but none for this turn, score=1.0."""
    metric = make_metric(scope="tool_call")
    turn = make_turn()
    expected = [{"turn": 2, "tool_name": "Order Lookup", "required_args": ["order_number"]}]
    result = score_tool_call_accuracy(metric, turn, expected_tools=expected, turn_index=1)
    assert result.score == pytest.approx(1.0)


def test_tool_accuracy_correct_tool_called():
    metric = make_metric(scope="tool_call")
    turn = make_turn(
        tool_calls=[{"function": {"name": "order_lookup", "arguments": {"order_number": "123"}}}]
    )
    expected = [{"turn": 1, "tool_name": "Order Lookup", "required_args": ["order_number"]}]
    result = score_tool_call_accuracy(metric, turn, expected_tools=expected, turn_index=1)
    assert result.score == pytest.approx(1.0)


def test_tool_accuracy_missing_tool():
    metric = make_metric(scope="tool_call")
    turn = make_turn(tool_calls=[])  # no tool calls made
    expected = [{"turn": 1, "tool_name": "Order Lookup", "required_args": []}]
    result = score_tool_call_accuracy(metric, turn, expected_tools=expected, turn_index=1)
    assert result.score == pytest.approx(0.0)
    assert "not called" in result.reasoning.lower()


def test_tool_accuracy_score_in_range():
    metric = make_metric(scope="tool_call")
    turn = make_turn(
        tool_calls=[{"function": {"name": "order_lookup", "arguments": {}}}]
    )
    expected = [
        {"turn": 1, "tool_name": "Order Lookup", "required_args": []},
        {"turn": 1, "tool_name": "Payment Lookup", "required_args": []},
    ]
    result = score_tool_call_accuracy(metric, turn, expected_tools=expected, turn_index=1)
    # 1 out of 2 correct
    assert result.score == pytest.approx(0.5)


# ── Slot fill efficiency ──────────────────────────────────────────────────────

def test_slot_fill_efficient_response():
    """Normal response with no unfilled slots → score=1.0."""
    metric = make_metric(scope="per_turn")
    turn = make_turn(
        turn_type="response",
        router_decision={"unfilled_slots": [], "extracted_slot_values": {}},
    )
    result = score_slot_fill_efficiency(metric, turn, turn_index=1)
    assert result.score == pytest.approx(1.0)


def test_slot_fill_response_with_unfilled_slots_penalized():
    """Agent gave a response despite having unfilled required slots → score=0.5."""
    metric = make_metric(scope="per_turn")
    turn = make_turn(
        turn_type="response",
        router_decision={"unfilled_slots": ["Order Number"], "extracted_slot_values": {}},
    )
    result = score_slot_fill_efficiency(metric, turn, turn_index=1)
    assert result.score == pytest.approx(0.5)


def test_slot_fill_correct_ask():
    """Agent asked a slot-fill question with unfilled slots → score=1.0."""
    metric = make_metric(scope="per_turn")
    turn = make_turn(
        turn_type="slot_fill",
        router_decision={"unfilled_slots": ["Order Number"], "extracted_slot_values": {}},
    )
    result = score_slot_fill_efficiency(metric, turn, turn_index=1)
    assert result.score == pytest.approx(1.0)


def test_slot_fill_redundant_ask_penalized():
    """Agent asked a slot-fill question despite no unfilled slots → score=0.5."""
    metric = make_metric(scope="per_turn")
    turn = make_turn(
        turn_type="slot_fill",
        router_decision={"unfilled_slots": [], "extracted_slot_values": {}},
    )
    result = score_slot_fill_efficiency(metric, turn, turn_index=1)
    assert result.score == pytest.approx(0.5)
