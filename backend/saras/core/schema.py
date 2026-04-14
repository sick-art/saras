"""
Pydantic models for the Saras YAML agent schema.

Design principles:
- Natural language first: all condition/trigger/handoff descriptions are plain English strings.
  No DSL, no boolean expressions, no hidden variable names.
- Tools are defined once at the agent level with full config (inputs, on_failure, on_empty_result).
  Goals reference tools by name only.
- Hierarchy: Agent > [Persona, Tone, GlobalRules, InterruptTriggers, OutOfScope, Handoffs, Tools]
             > Conditions > Goals > [Tone, Slots, Sequences, Rules, tool-names]
- IDs are auto-generated for internal use; users never author IDs.
"""

from typing import Annotated, Literal
from pydantic import BaseModel, Field, model_validator


# ── Tool sub-models ────────────────────────────────────────────────────────────

class ToolInput(BaseModel):
    name: str = Field(description="Human-readable input name, e.g. 'Order Identifier'")
    description: str = Field(description="What this input represents and how to obtain it")
    required: bool = True


ToolType = Literal["LookupTool", "KnowledgeTool", "ActionTool"]


class AgentTool(BaseModel):
    name: str = Field(description="Unique, descriptive tool name referenced by goals")
    type: ToolType
    description: str = Field(description="What this tool does — shown to the LLM")
    # LookupTool / ActionTool
    endpoint: str | None = None
    auth: str | None = None
    # KnowledgeTool
    source: str | None = None
    collection: str | None = None
    # ActionTool
    confirmation_required: bool = False
    # Inputs
    inputs: list[ToolInput] = Field(default_factory=list)
    # Failure semantics — natural language instructions for the model
    on_failure: str | None = Field(
        default=None,
        description="What the model should do if this tool fails or times out",
    )
    on_empty_result: str | None = Field(
        default=None,
        description="What the model should do if the tool returns no results",
    )


# ── Goal sub-models ────────────────────────────────────────────────────────────

class Slot(BaseModel):
    name: str = Field(description="Human-readable slot name, e.g. 'Order Identifier'")
    description: str = Field(description="What information this slot represents")
    required: bool = True
    ask_if_missing: str | None = Field(
        default=None,
        description="The exact question to ask the user if this slot is not yet filled",
    )


class Sequence(BaseModel):
    name: str
    description: str | None = None
    steps: list[str] = Field(
        description=(
            "Ordered natural language steps. Reference tools as "
            "'You MUST invoke @tool: <Tool Name> before ...' embedded in a sentence."
        )
    )


class Goal(BaseModel):
    name: str
    description: str = Field(
        description="What to achieve in this goal context — plain English"
    )
    tone: str | None = Field(
        default=None,
        description="Goal-specific tone override — plain English description",
    )
    slots: list[Slot] = Field(default_factory=list)
    sequences: list[Sequence] = Field(default_factory=list)
    rules: list[str] = Field(
        default_factory=list,
        description="Plain English constraints specific to this goal",
    )
    tools: list[str] = Field(
        default_factory=list,
        description="Names of agent-level tools available in this goal",
    )


# ── Condition ─────────────────────────────────────────────────────────────────

class Condition(BaseModel):
    name: str
    description: str = Field(
        description=(
            "Plain English description of when this condition applies. "
            "The router LLM evaluates this against the conversation at runtime."
        )
    )
    goals: list[Goal] = Field(default_factory=list)


# ── Root-level blocks ──────────────────────────────────────────────────────────

class Handoff(BaseModel):
    name: str
    description: str = Field(
        description=(
            "Plain English description of when to transfer — "
            "no code or boolean expressions."
        )
    )
    target: str = Field(
        description="Target agent name (must exist in project) or 'Human Support Queue'"
    )
    context_to_pass: str | None = Field(
        default=None,
        description="What context to include in the handoff bundle — plain English",
    )


class InterruptTrigger(BaseModel):
    name: str
    description: str = Field(
        description=(
            "Plain English description of when to fire this interrupt. "
            "Checked before every model response."
        )
    )
    action: str | None = Field(
        default=None,
        description="What to do when triggered — plain English instruction",
    )


class SubAgent(BaseModel):
    name: str
    ref: str | None = Field(default=None, description="Path to another agent YAML file")
    inline: "AgentSchema | None" = Field(
        default=None, description="Inline agent definition for simple sub-agents"
    )

    @model_validator(mode="after")
    def must_have_ref_or_inline(self) -> "SubAgent":
        if self.ref is None and self.inline is None:
            raise ValueError("SubAgent must have either 'ref' or 'inline' defined")
        return self


class AgentModels(BaseModel):
    primary: str = Field(description="Main reasoning and response generation model")
    router: str | None = Field(
        default=None,
        description="Fast model for condition evaluation, goal routing, slot detection",
    )
    judge: str | None = Field(
        default=None,
        description="High-quality model for self-eval and edge-case judgment",
    )
    fallback: str | None = Field(
        default=None, description="Model to use if primary is unavailable"
    )


# ── Top-level agent schema ─────────────────────────────────────────────────────

class AgentSchema(BaseModel):
    """
    Complete agent definition. This is the canonical data model.
    The YAML string is the source of truth; this model is always derived from it.
    """

    name: str
    version: str = "1.0.0"
    description: str | None = None

    models: AgentModels = Field(
        default_factory=lambda: AgentModels(primary="gpt-5.4-mini")
    )

    # Identity
    persona: str | None = Field(
        default=None,
        description="Natural language role brief — written like briefing a new employee",
    )
    tone: str | None = Field(
        default=None,
        description="Default communication style — plain English description",
    )

    # Always-active constraints
    global_rules: list[str] = Field(
        default_factory=list,
        description="Platform-wide invariants active regardless of condition/goal",
    )

    # Emergency overrides — checked before every response
    interrupt_triggers: list[InterruptTrigger] = Field(default_factory=list)

    # Topics to refuse
    out_of_scope: list[str] = Field(default_factory=list)

    # Transfer rules
    handoffs: list[Handoff] = Field(default_factory=list)

    # Tool definitions — referenced by name inside goals
    tools: list[AgentTool] = Field(default_factory=list)

    # Main behavior tree
    conditions: list[Condition] = Field(default_factory=list)

    # Child agents
    sub_agents: list[SubAgent] = Field(default_factory=list)

    def tool_by_name(self, name: str) -> AgentTool | None:
        return next((t for t in self.tools if t.name == name), None)

    def all_referenced_tool_names(self) -> set[str]:
        names: set[str] = set()
        for condition in self.conditions:
            for goal in condition.goals:
                names.update(goal.tools)
        return names

    def defined_tool_names(self) -> set[str]:
        return {t.name for t in self.tools}


# Allow SubAgent.inline to reference AgentSchema
SubAgent.model_rebuild()


# ── Compiled agent (output of compiler.py) ────────────────────────────────────

class ToolDefinition(BaseModel):
    """Provider-agnostic tool definition for LLM function calling."""
    name: str
    description: str
    input_schema: dict  # JSON Schema for inputs


class ContextLayer(BaseModel):
    """
    A single layer in the progressive context disclosure stack.
    Layers are assembled per-turn by the executor based on routing decisions.
    """
    layer: Annotated[int, Field(ge=1, le=8)]
    label: str
    content: str
    always_inject: bool = False  # True for Layer 1 (global rules + persona)


class RoutingContext(BaseModel):
    """
    Natural-language routing context passed to the router model each turn.
    Never compiled to code — always kept as NL for LLM interpretation.
    """
    interrupt_triggers: list[dict]   # {name, description, action}
    handoffs: list[dict]             # {name, description, target}
    conditions: list[dict]           # {name, description}
    # goals per condition: nested dict keyed by condition name
    goals_by_condition: dict[str, list[dict]]


class CompiledAgent(BaseModel):
    """
    The output of the compiler. Passed to the executor for each turn.
    """
    agent_id: str
    agent_version: str
    schema_: AgentSchema = Field(alias="schema")

    # Base system prompt: persona + tone + global_rules + out_of_scope
    # (assembled once; goal/condition context injected per-turn by executor)
    base_system_prompt: str

    # All tool definitions in provider-native-compatible format
    tool_definitions: list[ToolDefinition]

    # NL routing context for router model
    routing_context: RoutingContext

    # Context layers (Layer 1 always injected; rest injected on demand)
    context_layers: list[ContextLayer]

    model_config = {"populate_by_name": True}
