"""
Agent Compiler — turns an AgentSchema into a CompiledAgent.

What it does:
1. Assembles the base system prompt from: persona + tone + global_rules + out_of_scope
   (written as coherent prose, not a key/value dump)
2. Builds provider-agnostic tool definitions (name + description + JSON Schema inputs)
3. Builds the RoutingContext (NL conditions/triggers/handoffs kept as natural language)
4. Prepares the 8 progressive context layers for per-turn assembly by the executor

What it does NOT do:
- Evaluate any natural language conditions (that's the router model's job at runtime)
- Call any LLMs
- Store anything to DB
"""

import textwrap
import yaml
from pydantic import ValidationError

from saras.core.schema import (
    AgentSchema,
    AgentTool,
    CompiledAgent,
    ContextLayer,
    RoutingContext,
    ToolDefinition,
)


# ── Public API ─────────────────────────────────────────────────────────────────

def compile_from_yaml(yaml_content: str, agent_id: str = "", agent_version: str = "1.0.0") -> CompiledAgent:
    """Parse YAML string and compile to a CompiledAgent."""
    raw = yaml.safe_load(yaml_content)
    if not isinstance(raw, dict) or "agent" not in raw:
        raise ValueError("YAML must have a top-level 'agent:' key")
    schema = AgentSchema.model_validate(raw["agent"])
    return compile_schema(schema, agent_id=agent_id, agent_version=agent_version)


def compile_schema(schema: AgentSchema, agent_id: str = "", agent_version: str = "1.0.0") -> CompiledAgent:
    """Compile an already-parsed AgentSchema to a CompiledAgent."""
    return CompiledAgent(
        agent_id=agent_id,
        agent_version=agent_version,
        schema=schema,
        base_system_prompt=_build_base_system_prompt(schema),
        tool_definitions=_build_tool_definitions(schema),
        routing_context=_build_routing_context(schema),
        context_layers=_build_context_layers(schema),
    )


# ── System prompt assembly ─────────────────────────────────────────────────────

def _build_base_system_prompt(schema: AgentSchema) -> str:
    """
    Assemble Layer 1 context: persona + tone + global_rules + out_of_scope.
    Written as coherent prose that reads naturally to a language model.
    NOT a structured dump of YAML keys.
    """
    parts: list[str] = []

    # Persona
    if schema.persona:
        parts.append(schema.persona.strip())

    # Tone
    if schema.tone:
        parts.append(f"Communication style:\n{schema.tone.strip()}")

    # Global rules
    if schema.global_rules:
        rules_text = "\n".join(f"- {r}" for r in schema.global_rules)
        parts.append(f"You must always follow these rules, without exception:\n{rules_text}")

    # Out of scope
    if schema.out_of_scope:
        oos_text = "\n".join(f"- {item}" for item in schema.out_of_scope)
        parts.append(
            f"You must refuse to engage with the following topics. "
            f"Politely redirect the conversation instead:\n{oos_text}"
        )

    return "\n\n".join(parts)


# ── Tool definitions ───────────────────────────────────────────────────────────

def _build_tool_definitions(schema: AgentSchema) -> list[ToolDefinition]:
    """Convert AgentTool entries into provider-agnostic tool definitions."""
    return [_tool_to_definition(t) for t in schema.tools]


def _tool_to_definition(tool: AgentTool) -> ToolDefinition:
    """
    Build a JSON-Schema-based tool definition compatible with both
    Anthropic tool_use and OpenAI function_calling formats.
    """
    properties: dict = {}
    required_inputs: list[str] = []

    for inp in tool.inputs:
        properties[_snake(inp.name)] = {
            "type": "string",
            "description": inp.description,
        }
        if inp.required:
            required_inputs.append(_snake(inp.name))

    # Append failure guidance to the tool description so the model
    # sees it in tool_use context (not just in the system prompt)
    description_parts = [tool.description]
    if tool.on_failure:
        description_parts.append(f"On failure: {tool.on_failure.strip()}")
    if tool.on_empty_result:
        description_parts.append(f"If no results: {tool.on_empty_result.strip()}")

    return ToolDefinition(
        name=_snake(tool.name),  # LLM-friendly snake_case name
        description=" | ".join(description_parts),
        input_schema={
            "type": "object",
            "properties": properties,
            "required": required_inputs,
        },
    )


# ── Routing context ────────────────────────────────────────────────────────────

def _build_routing_context(schema: AgentSchema) -> RoutingContext:
    """
    Build the NL routing context sent to the router model each turn.
    Everything stays as natural language — never compiled to code.
    """
    return RoutingContext(
        interrupt_triggers=[
            {
                "name": t.name,
                "description": t.description,
                "action": t.action,
            }
            for t in schema.interrupt_triggers
        ],
        handoffs=[
            {
                "name": h.name,
                "description": h.description,
                "target": h.target,
                "context_to_pass": h.context_to_pass,
            }
            for h in schema.handoffs
        ],
        conditions=[
            {"name": c.name, "description": c.description}
            for c in schema.conditions
        ],
        goals_by_condition={
            c.name: [
                {
                    "name": g.name,
                    "description": g.description,
                    "has_slots": bool(g.slots),
                    "has_sequences": bool(g.sequences),
                    "tool_names": g.tools,
                }
                for g in c.goals
            ]
            for c in schema.conditions
        },
    )


# ── Progressive context layers ─────────────────────────────────────────────────

def _build_context_layers(schema: AgentSchema) -> list[ContextLayer]:
    """
    Pre-build all 8 context layers. The executor assembles them per-turn
    based on routing decisions. Layer 1 is always injected.

    Layer 1: global_rules + interrupt_triggers + persona + agent tone  (always)
    Layer 2: active condition name + description
    Layer 3: active goal description + goal tone override
    Layer 4: unfilled slot — name + ask_if_missing prompt
    Layer 5: active sequence steps as guidance
    Layer 6: active goal rules + scoped tool descriptions
    Layer 7: tool results (injected inline by executor, not pre-built)
    Layer 8: retrieved cross-turn memory (injected by executor, not pre-built)
    """
    layers: list[ContextLayer] = []

    # Layer 1 — always injected (base system prompt + interrupt trigger names)
    interrupt_names = ", ".join(t.name for t in schema.interrupt_triggers) or "none defined"
    layer1_content = _build_base_system_prompt(schema)
    if schema.interrupt_triggers:
        trigger_list = "\n".join(
            f"- {t.name}: {_first_sentence(t.description)}"
            for t in schema.interrupt_triggers
        )
        layer1_content += (
            f"\n\nBefore every response, check for these emergency situations "
            f"(they override all other behaviour):\n{trigger_list}"
        )
    layers.append(ContextLayer(
        layer=1,
        label="base",
        content=layer1_content,
        always_inject=True,
    ))

    # Layers 2–6 are templates; the executor fills in placeholders at runtime.
    # We pre-build one entry per condition/goal combination so the executor can
    # look them up by (condition_name, goal_name) key.
    # Here we just store generic templates; dynamic ones are built in executor.py.

    # Layer 2 template — condition context
    for condition in schema.conditions:
        layers.append(ContextLayer(
            layer=2,
            label=f"condition:{condition.name}",
            content=(
                f"The current situation is: {condition.name}\n"
                f"{condition.description.strip()}"
            ),
        ))

        # Layer 3 templates — goal context
        for goal in condition.goals:
            goal_content = f"Your current goal: {goal.name}\n{goal.description.strip()}"
            if goal.tone:
                goal_content += f"\n\nTone for this goal: {goal.tone.strip()}"
            layers.append(ContextLayer(
                layer=3,
                label=f"goal:{condition.name}:{goal.name}",
                content=goal_content,
            ))

            # Layer 5 templates — sequence steps
            for seq in goal.sequences:
                steps_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(seq.steps))
                layers.append(ContextLayer(
                    layer=5,
                    label=f"sequence:{condition.name}:{goal.name}:{seq.name}",
                    content=(
                        f"Follow this sequence — {seq.name}:\n{steps_text}"
                    ),
                ))

            # Layer 6 — goal rules + scoped tool guidance
            if goal.rules or goal.tools:
                rule_parts: list[str] = []
                if goal.rules:
                    rule_list = "\n".join(f"- {r}" for r in goal.rules)
                    rule_parts.append(f"Rules for this goal:\n{rule_list}")
                if goal.tools:
                    tool_descs = []
                    for tool_name in goal.tools:
                        tool = schema.tool_by_name(tool_name)
                        if tool:
                            tool_descs.append(f"- {tool.name} ({tool.type}): {tool.description}")
                    if tool_descs:
                        rule_parts.append("Available tools:\n" + "\n".join(tool_descs))
                layers.append(ContextLayer(
                    layer=6,
                    label=f"goal_rules_tools:{condition.name}:{goal.name}",
                    content="\n\n".join(rule_parts),
                ))

    return layers


# ── Utilities ──────────────────────────────────────────────────────────────────

def _snake(name: str) -> str:
    """Convert a human-readable name to snake_case for LLM tool names."""
    return name.lower().replace(" ", "_").replace("-", "_")


def _first_sentence(text: str) -> str:
    """Return the first sentence of a block of text."""
    sentence = text.strip().split(".")[0]
    return sentence[:200]  # cap length
