"""Unit tests for saras.core.schema — AgentSchema Pydantic models."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from saras.core.schema import (
    AgentModels,
    AgentSchema,
    AgentTool,
    Condition,
    Goal,
    Handoff,
    InterruptTrigger,
    Slot,
    SubAgent,
)

ASSETS_DIR = Path(__file__).parents[4] / "saras" / "assets"
FIXTURE_YAML = Path(__file__).parents[2] / "fixtures" / "sample_agent.yaml"


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_agent_schema(yaml_path: Path) -> AgentSchema:
    raw = yaml.safe_load(yaml_path.read_text())
    return AgentSchema.model_validate(raw["agent"])


# ── Minimal valid schema ───────────────────────────────────────────────────────

def test_minimal_schema_parses():
    """A schema with only the required 'name' field should parse successfully."""
    schema = AgentSchema(name="Minimal Agent")
    assert schema.name == "Minimal Agent"
    assert schema.version == "1.0.0"
    assert schema.conditions == []
    assert schema.tools == []
    assert schema.global_rules == []


def test_fixture_sample_agent_parses():
    """The test fixture YAML should parse into a valid AgentSchema."""
    schema = load_agent_schema(FIXTURE_YAML)
    assert schema.name == "Test Support Agent"
    assert len(schema.conditions) == 1
    assert len(schema.tools) == 1
    assert schema.tools[0].name == "Order Lookup"
    assert len(schema.conditions[0].goals) == 1


# ── Sample asset YAMLs ────────────────────────────────────────────────────────

@pytest.mark.parametrize("filename", [
    "sample_customer_support.yaml",
    "sample_financial_analyst.yaml",
    "sample_travel_concierge.yaml",
])
def test_sample_asset_yamls_parse(filename: str):
    """All bundled sample agent YAMLs must parse without error."""
    path = ASSETS_DIR / filename
    schema = load_agent_schema(path)
    assert schema.name  # non-empty name
    assert schema.models.primary  # has a primary model


# ── Field validation ──────────────────────────────────────────────────────────

def test_missing_name_raises():
    """AgentSchema without 'name' should raise ValidationError."""
    with pytest.raises(ValidationError, match="name"):
        AgentSchema.model_validate({})


def test_tool_invalid_type_raises():
    """AgentTool with an unsupported type should raise ValidationError."""
    with pytest.raises(ValidationError):
        AgentTool(
            name="Bad Tool",
            type="UnknownTool",
            description="Should fail",
        )


def test_tool_valid_types_accepted():
    """All three valid ToolType literals are accepted."""
    for tool_type in ("LookupTool", "KnowledgeTool", "ActionTool"):
        t = AgentTool(name=f"{tool_type} Tool", type=tool_type, description="desc")
        assert t.type == tool_type


def test_agent_models_defaults():
    models = AgentModels(primary="claude-sonnet-4-6")
    assert models.primary == "claude-sonnet-4-6"
    assert models.router is None
    assert models.fallback is None


# ── Sub-agent validation ──────────────────────────────────────────────────────

def test_sub_agent_requires_ref_or_inline():
    """SubAgent without ref or inline should raise ValueError."""
    with pytest.raises(ValidationError, match="ref.*inline|inline.*ref"):
        SubAgent(name="Orphan")


def test_sub_agent_with_ref_is_valid():
    sub = SubAgent(name="Support Agent", ref="support.yaml")
    assert sub.ref == "support.yaml"
    assert sub.inline is None


# ── Helper methods ────────────────────────────────────────────────────────────

def test_tool_by_name_found():
    schema = AgentSchema(
        name="Test",
        tools=[AgentTool(name="Order Lookup", type="LookupTool", description="desc")],
    )
    tool = schema.tool_by_name("Order Lookup")
    assert tool is not None
    assert tool.name == "Order Lookup"


def test_tool_by_name_not_found():
    schema = AgentSchema(name="Test")
    assert schema.tool_by_name("Nonexistent") is None


def test_all_referenced_tool_names():
    schema = AgentSchema(
        name="Test",
        conditions=[
            Condition(
                name="C1",
                description="Condition one",
                goals=[Goal(name="G1", description="Goal one", tools=["Tool A", "Tool B"])],
            )
        ],
    )
    refs = schema.all_referenced_tool_names()
    assert refs == {"Tool A", "Tool B"}


def test_defined_tool_names():
    schema = AgentSchema(
        name="Test",
        tools=[
            AgentTool(name="Tool A", type="LookupTool", description="A"),
            AgentTool(name="Tool B", type="ActionTool", description="B"),
        ],
    )
    assert schema.defined_tool_names() == {"Tool A", "Tool B"}


# ── Slot model ────────────────────────────────────────────────────────────────

def test_slot_optional_ask_if_missing():
    """ask_if_missing defaults to None and is not required."""
    slot = Slot(name="Phone Number", description="Customer phone", required=False)
    assert slot.ask_if_missing is None
    assert slot.required is False


# ── Interrupt trigger ─────────────────────────────────────────────────────────

def test_interrupt_trigger_optional_action():
    trigger = InterruptTrigger(
        name="Safety",
        description="Customer mentions safety emergency",
    )
    assert trigger.action is None


# ── Handoff model ─────────────────────────────────────────────────────────────

def test_handoff_requires_target():
    with pytest.raises(ValidationError, match="target"):
        Handoff(name="Escalate", description="When needed")  # type: ignore[call-arg]


def test_handoff_context_optional():
    h = Handoff(name="H", description="desc", target="Human Support Queue")
    assert h.context_to_pass is None
