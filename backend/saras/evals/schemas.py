"""Pydantic models for the eval system."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ── Metric definitions ─────────────────────────────────────────────────────────

class MetricDefinition(BaseModel):
    name: str
    type: Literal["llm_judge", "deterministic"]
    scope: Literal["per_turn", "whole_conversation", "tool_call"]
    description: str
    preset: str | None = None          # preset key if using a built-in
    rubric: str | None = None          # for llm_judge metrics
    threshold: float | None = None     # optional pass/fail cutoff (0.0–1.0)


class MetricSet(BaseModel):
    metrics: list[MetricDefinition]


# ── Dataset item input shapes (stored in DatasetItem.input JSONB) ──────────────

class SimulatedScenario(BaseModel):
    persona: str
    goal: str
    max_turns: int = 8
    stop_signal: str | None = None


class ScriptedTestCase(BaseModel):
    """input.turns — list of user messages (scripted)."""
    turns: list[str]


class SimulatedTestCase(BaseModel):
    """input.scenario — LLM-driven user simulation."""
    scenario: SimulatedScenario


# ── Conversation record (produced by the runner per dataset item) ──────────────

class TurnRecord(BaseModel):
    """Snapshot of a single conversation turn for scoring."""
    turn_index: int
    user_message: str
    agent_content: str
    turn_type: str                     # response|slot_fill|interrupt|handoff
    tool_calls_made: list[dict[str, Any]] = Field(default_factory=list)
    router_decision: dict[str, Any] | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class ConversationRecord(BaseModel):
    """Full conversation result for one dataset item."""
    item_id: str
    history: list[dict[str, Any]]      # OpenAI-format messages
    turns: list[TurnRecord]
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    error: str | None = None           # set if conversation failed


# ── Judge output ───────────────────────────────────────────────────────────────

class JudgeScore(BaseModel):
    """Legacy output model — retained for backwards compatibility.

    New code should use MetricResult from saras.evals.metrics.base directly.
    """
    metric_name: str
    scope: str
    turn_index: int | None = None      # None = whole-conversation
    score: float                       # 0.0–1.0 normalised
    raw_score: str                     # e.g. "4/5" or "0.82"
    reasoning: str
    model_used: str
    passed: bool | None = None         # None if no threshold configured
