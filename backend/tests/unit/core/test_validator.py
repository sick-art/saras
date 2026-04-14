"""Unit tests for saras.core.validator — ValidationResult checks."""

from __future__ import annotations

import pytest

from saras.core.schema import (
    AgentSchema,
    AgentTool,
    Condition,
    Goal,
    Handoff,
    InterruptTrigger,
    Sequence,
    Slot,
    SubAgent,
    ToolInput,
)
from saras.core.validator import Severity, validate


# ── Helpers ───────────────────────────────────────────────────────────────────

def minimal_valid_schema(**overrides) -> AgentSchema:
    """
    Build a schema that passes all ERROR validators.
    Warnings/infos may still be present.
    """
    defaults = dict(
        name="Valid Agent",
        persona="You are a helpful and professional support agent with five years of experience.",
        conditions=[
            Condition(
                name="Order Inquiry",
                description="User is asking about an order",
                goals=[Goal(name="Track Order", description="Track the order")],
            )
        ],
        handoffs=[Handoff(name="H", description="Escalate", target="Human Support Queue")],
        interrupt_triggers=[InterruptTrigger(name="Emergency", description="Safety emergency")],
    )
    defaults.update(overrides)
    return AgentSchema(**defaults)


# ── ERROR: tool_ref_undefined ─────────────────────────────────────────────────

def test_undefined_tool_reference_is_error():
    schema = AgentSchema(
        name="Test",
        conditions=[
            Condition(
                name="C1",
                description="desc",
                goals=[Goal(name="G1", description="desc", tools=["Undefined Tool"])],
            )
        ],
    )
    result = validate(schema)
    errors = [e for e in result.errors if e.code == "tool_ref_undefined"]
    assert errors, "Expected tool_ref_undefined error"
    assert "Undefined Tool" in errors[0].message


def test_defined_tool_reference_has_no_error():
    schema = AgentSchema(
        name="Test",
        tools=[AgentTool(name="My Tool", type="LookupTool", description="desc")],
        conditions=[
            Condition(
                name="C1",
                description="desc",
                goals=[Goal(name="G1", description="desc", tools=["My Tool"])],
            )
        ],
    )
    result = validate(schema)
    tool_errors = [e for e in result.errors if e.code == "tool_ref_undefined"]
    assert not tool_errors


# ── ERROR: no_conditions ──────────────────────────────────────────────────────

def test_no_conditions_is_error():
    schema = AgentSchema(name="Test")
    result = validate(schema)
    assert any(e.code == "no_conditions" for e in result.errors)


def test_has_conditions_no_error():
    schema = AgentSchema(
        name="Test",
        conditions=[Condition(name="C1", description="desc")],
    )
    result = validate(schema)
    assert not any(e.code == "no_conditions" for e in result.errors)


# ── ERROR: slot_missing_prompt ────────────────────────────────────────────────

def test_required_slot_without_prompt_is_error():
    schema = AgentSchema(
        name="Test",
        conditions=[
            Condition(
                name="C1",
                description="desc",
                goals=[
                    Goal(
                        name="G1",
                        description="desc",
                        slots=[Slot(name="Email", description="Customer email", required=True)],
                    )
                ],
            )
        ],
    )
    result = validate(schema)
    assert any(e.code == "slot_missing_prompt" for e in result.errors)


def test_slot_with_prompt_no_error():
    schema = AgentSchema(
        name="Test",
        conditions=[
            Condition(
                name="C1",
                description="desc",
                goals=[
                    Goal(
                        name="G1",
                        description="desc",
                        slots=[
                            Slot(
                                name="Email",
                                description="Customer email",
                                required=True,
                                ask_if_missing="What is your email address?",
                            )
                        ],
                    )
                ],
            )
        ],
    )
    result = validate(schema)
    assert not any(e.code == "slot_missing_prompt" for e in result.errors)


# ── ERROR: handoff_target_unknown ─────────────────────────────────────────────

def test_handoff_unknown_target_is_error_when_known_agents_provided():
    schema = AgentSchema(
        name="Test",
        conditions=[Condition(name="C1", description="desc")],
        handoffs=[Handoff(name="H", description="desc", target="NonExistentAgent")],
    )
    result = validate(schema, known_agent_names={"OtherAgent"})
    assert any(e.code == "handoff_target_unknown" for e in result.errors)


def test_handoff_human_queue_target_never_errors():
    schema = AgentSchema(
        name="Test",
        conditions=[Condition(name="C1", description="desc")],
        handoffs=[Handoff(name="H", description="desc", target="Human Support Queue")],
    )
    result = validate(schema, known_agent_names={"OtherAgent"})
    assert not any(e.code == "handoff_target_unknown" for e in result.errors)


def test_handoff_target_not_checked_without_known_agents():
    schema = AgentSchema(
        name="Test",
        conditions=[Condition(name="C1", description="desc")],
        handoffs=[Handoff(name="H", description="desc", target="MysteryAgent")],
    )
    # No known_agent_names provided — validator skips the check
    result = validate(schema)
    assert not any(e.code == "handoff_target_unknown" for e in result.errors)


# ── WARNING: tool_unused ──────────────────────────────────────────────────────

def test_unreferenced_tool_is_warning():
    schema = minimal_valid_schema(
        tools=[AgentTool(name="Unused Tool", type="ActionTool", description="never used")]
    )
    result = validate(schema)
    assert any(w.code == "tool_unused" for w in result.warnings)


def test_referenced_tool_no_unused_warning():
    schema = AgentSchema(
        name="Test",
        tools=[AgentTool(name="My Tool", type="LookupTool", description="desc")],
        conditions=[
            Condition(
                name="C1",
                description="desc",
                goals=[Goal(name="G1", description="desc", tools=["My Tool"])],
            )
        ],
        handoffs=[Handoff(name="H", description="desc", target="Human Support Queue")],
        interrupt_triggers=[InterruptTrigger(name="E", description="emergency")],
    )
    result = validate(schema)
    assert not any(w.code == "tool_unused" for w in result.warnings)


# ── WARNING: no_handoff ───────────────────────────────────────────────────────

def test_no_handoff_is_warning():
    schema = AgentSchema(
        name="Test",
        conditions=[Condition(name="C1", description="desc")],
    )
    result = validate(schema)
    assert any(w.code == "no_handoff" for w in result.warnings)


# ── WARNING: no_interrupt_triggers ───────────────────────────────────────────

def test_no_interrupt_triggers_is_warning():
    schema = AgentSchema(
        name="Test",
        conditions=[Condition(name="C1", description="desc")],
    )
    result = validate(schema)
    assert any(w.code == "no_interrupt_triggers" for w in result.warnings)


# ── WARNING: persona_too_short ────────────────────────────────────────────────

def test_short_persona_is_warning():
    schema = minimal_valid_schema(persona="Short.")
    result = validate(schema)
    assert any(w.code == "persona_too_short" for w in result.warnings)


def test_long_persona_no_warning():
    schema = minimal_valid_schema(
        persona="You are a highly experienced customer support specialist with over a decade of expertise."
    )
    result = validate(schema)
    assert not any(w.code == "persona_too_short" for w in result.warnings)


# ── INFO: goal_no_sequence ────────────────────────────────────────────────────

def test_goal_with_rules_but_no_sequence_is_info():
    schema = minimal_valid_schema(
        conditions=[
            Condition(
                name="C1",
                description="desc",
                goals=[Goal(name="G1", description="desc", rules=["Rule 1"])],
            )
        ]
    )
    result = validate(schema)
    assert any(i.code == "goal_no_sequence" for i in result.infos)


def test_goal_with_rules_and_sequence_no_info():
    schema = minimal_valid_schema(
        conditions=[
            Condition(
                name="C1",
                description="desc",
                goals=[
                    Goal(
                        name="G1",
                        description="desc",
                        rules=["Rule 1"],
                        sequences=[Sequence(name="Flow", steps=["Step 1"])],
                    )
                ],
            )
        ]
    )
    result = validate(schema)
    assert not any(i.code == "goal_no_sequence" for i in result.infos)


# ── INFO: many_goals_in_condition ─────────────────────────────────────────────

def test_four_goals_in_condition_is_info():
    goals = [Goal(name=f"Goal {i}", description="desc") for i in range(4)]
    schema = minimal_valid_schema(
        conditions=[Condition(name="C1", description="desc", goals=goals)]
    )
    result = validate(schema)
    assert any(i.code == "many_goals_in_condition" for i in result.infos)


# ── is_valid / to_dict ────────────────────────────────────────────────────────

def test_valid_schema_is_valid_true():
    schema = minimal_valid_schema()
    result = validate(schema)
    assert result.is_valid  # no errors (warnings may exist)


def test_invalid_schema_is_valid_false():
    schema = AgentSchema(name="Test")  # no conditions → ERROR
    result = validate(schema)
    assert not result.is_valid


def test_to_dict_structure():
    schema = minimal_valid_schema()
    d = validate(schema).to_dict()
    assert "valid" in d
    assert "errors" in d
    assert "warnings" in d
    assert "infos" in d
    assert isinstance(d["errors"], list)


def test_severity_values():
    assert Severity.ERROR == "error"
    assert Severity.WARNING == "warning"
    assert Severity.INFO == "info"
