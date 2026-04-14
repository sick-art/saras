"""Unit tests for saras.core.compiler — YAML → CompiledAgent."""

from __future__ import annotations

from pathlib import Path

import pytest

from saras.core.compiler import (
    _snake,
    compile_from_yaml,
    compile_schema,
)
from saras.core.schema import (
    AgentModels,
    AgentSchema,
    AgentTool,
    Condition,
    Goal,
    Handoff,
    InterruptTrigger,
    Sequence,
    Slot,
    ToolInput,
)

FIXTURE_YAML = Path(__file__).parents[2] / "fixtures" / "sample_agent.yaml"


# ── compile_from_yaml ─────────────────────────────────────────────────────────

def test_compile_from_yaml_success():
    compiled = compile_from_yaml(FIXTURE_YAML.read_text(), agent_id="test-id")
    assert compiled.agent_id == "test-id"
    assert compiled.base_system_prompt
    assert len(compiled.tool_definitions) == 1
    assert compiled.tool_definitions[0].name == "order_lookup"


def test_compile_from_yaml_missing_top_key_raises():
    with pytest.raises(ValueError, match="top-level 'agent:'"):
        compile_from_yaml("name: no_agent_key\n")


def test_compile_from_yaml_invalid_yaml_raises():
    with pytest.raises(Exception):
        compile_from_yaml(": invalid: yaml: [{{")


# ── System prompt assembly ────────────────────────────────────────────────────

def test_base_system_prompt_contains_persona():
    schema = AgentSchema(
        name="Test",
        persona="You are a helpful assistant for testing.",
    )
    compiled = compile_schema(schema)
    assert "helpful assistant for testing" in compiled.base_system_prompt


def test_base_system_prompt_contains_tone():
    schema = AgentSchema(
        name="Test",
        tone="Be concise and professional.",
    )
    compiled = compile_schema(schema)
    assert "concise and professional" in compiled.base_system_prompt


def test_base_system_prompt_contains_global_rules():
    schema = AgentSchema(
        name="Test",
        global_rules=["Never share customer data.", "Always verify identity."],
    )
    compiled = compile_schema(schema)
    assert "Never share customer data" in compiled.base_system_prompt
    assert "Always verify identity" in compiled.base_system_prompt


def test_base_system_prompt_contains_out_of_scope():
    schema = AgentSchema(
        name="Test",
        out_of_scope=["Investment advice", "Medical questions"],
    )
    compiled = compile_schema(schema)
    assert "Investment advice" in compiled.base_system_prompt
    assert "Medical questions" in compiled.base_system_prompt


def test_base_system_prompt_empty_when_no_fields():
    schema = AgentSchema(name="Test")
    compiled = compile_schema(schema)
    assert compiled.base_system_prompt == ""


# ── Tool definitions ──────────────────────────────────────────────────────────

def test_tool_compiled_to_snake_case_name():
    schema = AgentSchema(
        name="Test",
        tools=[AgentTool(name="Order Lookup", type="LookupTool", description="Looks up orders")],
    )
    compiled = compile_schema(schema)
    assert len(compiled.tool_definitions) == 1
    assert compiled.tool_definitions[0].name == "order_lookup"


def test_tool_description_preserved():
    schema = AgentSchema(
        name="Test",
        tools=[AgentTool(name="Tool", type="ActionTool", description="Does something important")],
    )
    compiled = compile_schema(schema)
    assert "Does something important" in compiled.tool_definitions[0].description


def test_tool_on_failure_appended_to_description():
    schema = AgentSchema(
        name="Test",
        tools=[AgentTool(
            name="Fragile Tool",
            type="LookupTool",
            description="Looks things up",
            on_failure="Apologize and retry later",
        )],
    )
    compiled = compile_schema(schema)
    assert "Apologize and retry later" in compiled.tool_definitions[0].description


def test_tool_inputs_become_json_schema_properties():
    schema = AgentSchema(
        name="Test",
        tools=[AgentTool(
            name="Search",
            type="LookupTool",
            description="Searches",
            inputs=[
                ToolInput(name="Search Query", description="What to search for", required=True),
                ToolInput(name="Max Results", description="How many results", required=False),
            ],
        )],
    )
    compiled = compile_schema(schema)
    td = compiled.tool_definitions[0]
    props = td.input_schema["properties"]
    assert "search_query" in props
    assert "max_results" in props
    assert "search_query" in td.input_schema["required"]
    assert "max_results" not in td.input_schema["required"]


def test_no_tools_compiles_empty_list():
    schema = AgentSchema(name="Test")
    compiled = compile_schema(schema)
    assert compiled.tool_definitions == []


# ── Routing context ───────────────────────────────────────────────────────────

def test_routing_context_conditions():
    schema = AgentSchema(
        name="Test",
        conditions=[
            Condition(name="Order Inquiry", description="User asking about an order"),
            Condition(name="Return Request", description="User wants to return"),
        ],
    )
    compiled = compile_schema(schema)
    rc = compiled.routing_context
    condition_names = [c["name"] for c in rc.conditions]
    assert "Order Inquiry" in condition_names
    assert "Return Request" in condition_names


def test_routing_context_goals_by_condition():
    schema = AgentSchema(
        name="Test",
        conditions=[
            Condition(
                name="Order Inquiry",
                description="User asking about order",
                goals=[
                    Goal(name="Track Order", description="Track their order"),
                    Goal(name="Cancel Order", description="Cancel their order"),
                ],
            )
        ],
    )
    compiled = compile_schema(schema)
    goals = compiled.routing_context.goals_by_condition["Order Inquiry"]
    goal_names = [g["name"] for g in goals]
    assert "Track Order" in goal_names
    assert "Cancel Order" in goal_names


def test_routing_context_interrupt_triggers():
    schema = AgentSchema(
        name="Test",
        interrupt_triggers=[
            InterruptTrigger(name="Safety", description="Emergency situation", action="Call 911"),
        ],
    )
    compiled = compile_schema(schema)
    triggers = compiled.routing_context.interrupt_triggers
    assert len(triggers) == 1
    assert triggers[0]["name"] == "Safety"
    assert triggers[0]["action"] == "Call 911"


def test_routing_context_handoffs():
    schema = AgentSchema(
        name="Test",
        handoffs=[
            Handoff(name="Human", description="Escalate to human", target="Human Support Queue"),
        ],
    )
    compiled = compile_schema(schema)
    handoffs = compiled.routing_context.handoffs
    assert len(handoffs) == 1
    assert handoffs[0]["target"] == "Human Support Queue"


# ── Context layers ────────────────────────────────────────────────────────────

def test_layer_1_always_injected():
    """Layer 1 (base) must have always_inject=True."""
    schema = AgentSchema(name="Test", persona="You are a test agent.")
    compiled = compile_schema(schema)
    layer1 = next(l for l in compiled.context_layers if l.label == "base")
    assert layer1.always_inject is True
    assert layer1.layer == 1


def test_condition_layer_2_created():
    schema = AgentSchema(
        name="Test",
        conditions=[Condition(name="C1", description="First condition")],
    )
    compiled = compile_schema(schema)
    layer2 = next((l for l in compiled.context_layers if l.label == "condition:C1"), None)
    assert layer2 is not None
    assert layer2.layer == 2
    assert "C1" in layer2.content


def test_goal_layer_3_created():
    schema = AgentSchema(
        name="Test",
        conditions=[
            Condition(
                name="C1",
                description="Condition",
                goals=[Goal(name="G1", description="Goal one description")],
            )
        ],
    )
    compiled = compile_schema(schema)
    layer3 = next((l for l in compiled.context_layers if l.label == "goal:C1:G1"), None)
    assert layer3 is not None
    assert layer3.layer == 3
    assert "Goal one description" in layer3.content


def test_sequence_layer_5_created():
    schema = AgentSchema(
        name="Test",
        conditions=[
            Condition(
                name="C1",
                description="Condition",
                goals=[
                    Goal(
                        name="G1",
                        description="Goal",
                        sequences=[Sequence(name="Flow", steps=["Step 1", "Step 2"])],
                    )
                ],
            )
        ],
    )
    compiled = compile_schema(schema)
    layer5 = next((l for l in compiled.context_layers if l.label == "sequence:C1:G1:Flow"), None)
    assert layer5 is not None
    assert layer5.layer == 5
    assert "Step 1" in layer5.content
    assert "Step 2" in layer5.content


# ── snake helper ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("input_name,expected", [
    ("Order Lookup", "order_lookup"),
    ("Search Query", "search_query"),
    ("My-Tool", "my_tool"),
    ("already_snake", "already_snake"),
    ("UPPER CASE", "upper_case"),
])
def test_snake_conversion(input_name: str, expected: str):
    assert _snake(input_name) == expected
