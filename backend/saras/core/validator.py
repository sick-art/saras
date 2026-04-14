"""
Agent Validator — runs structural checks on an AgentSchema and returns
categorised feedback for immediate display in all builder views.

Severity levels:
  ERROR   — blocks simulation and publish
  WARNING — shown but does not block
  INFO    — suggestions / tips

Validators run:
  - Server-side (Python): authoritative, on every PATCH /agents/:id
  - Client-side (TypeScript/Zod): fast live feedback in the YAML editor
    (the TS types in src/types/agent.ts mirror these rules)
"""

from dataclasses import dataclass, field
from enum import Enum

from saras.core.schema import AgentSchema


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationIssue:
    severity: Severity
    code: str          # machine-readable, e.g. "tool_ref_undefined"
    message: str       # human-readable, shown in UI
    path: str | None = None  # e.g. "conditions[0].goals[1].tools[0]"


@dataclass
class ValidationResult:
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]

    @property
    def infos(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.INFO]

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def to_dict(self) -> dict:
        return {
            "valid": self.is_valid,
            "errors": [_issue_dict(i) for i in self.errors],
            "warnings": [_issue_dict(i) for i in self.warnings],
            "infos": [_issue_dict(i) for i in self.infos],
        }


def validate(schema: AgentSchema, known_agent_names: set[str] | None = None) -> ValidationResult:
    """
    Run all validators and return a ValidationResult.

    known_agent_names: names of all agents in the same project.
    Used to validate handoff targets and sub-agent refs.
    """
    result = ValidationResult()
    ctx = _Ctx(schema=schema, result=result, known_agents=known_agent_names or set())

    _check_tool_refs(ctx)
    _check_handoff_targets(ctx)
    _check_sub_agent_refs(ctx)
    _check_required_slot_prompts(ctx)
    _check_required_tool_input_descriptions(ctx)
    _check_has_conditions(ctx)
    _check_unused_tools(ctx)
    _check_conditions_have_goals(ctx)
    _check_escalation_path(ctx)
    _check_interrupt_triggers(ctx)
    _check_persona_length(ctx)
    _check_goals_have_sequences(ctx)
    _check_condition_goal_count(ctx)

    return result


# ── Internal helpers ───────────────────────────────────────────────────────────

@dataclass
class _Ctx:
    schema: AgentSchema
    result: ValidationResult
    known_agents: set[str]

    def error(self, code: str, message: str, path: str | None = None) -> None:
        self.result.issues.append(ValidationIssue(Severity.ERROR, code, message, path))

    def warn(self, code: str, message: str, path: str | None = None) -> None:
        self.result.issues.append(ValidationIssue(Severity.WARNING, code, message, path))

    def info(self, code: str, message: str, path: str | None = None) -> None:
        self.result.issues.append(ValidationIssue(Severity.INFO, code, message, path))


# ── ERROR validators ───────────────────────────────────────────────────────────

def _check_tool_refs(ctx: _Ctx) -> None:
    """Every tool name referenced in a goal must exist in agent.tools."""
    defined = {t.name for t in ctx.schema.tools}
    for ci, condition in enumerate(ctx.schema.conditions):
        for gi, goal in enumerate(condition.goals):
            for ti, tool_name in enumerate(goal.tools):
                if tool_name not in defined:
                    ctx.error(
                        "tool_ref_undefined",
                        (
                            f"Goal '{goal.name}' (under '{condition.name}') references "
                            f"tool '{tool_name}' but no tool by that name is defined. "
                            f"Add it to agent.tools or fix the reference."
                        ),
                        path=f"conditions[{ci}].goals[{gi}].tools[{ti}]",
                    )


def _check_handoff_targets(ctx: _Ctx) -> None:
    """Handoff targets must be known agent names or 'Human Support Queue'."""
    for hi, handoff in enumerate(ctx.schema.handoffs):
        target = handoff.target
        is_human_queue = "human" in target.lower() or "queue" in target.lower()
        if not is_human_queue and ctx.known_agents and target not in ctx.known_agents:
            ctx.error(
                "handoff_target_unknown",
                (
                    f"Handoff '{handoff.name}' targets '{target}' but no agent with "
                    f"that name exists in this project. Create the agent or fix the target."
                ),
                path=f"handoffs[{hi}].target",
            )


def _check_sub_agent_refs(ctx: _Ctx) -> None:
    """Sub-agents with a ref must point to a known agent."""
    for si, sub in enumerate(ctx.schema.sub_agents):
        if sub.ref and ctx.known_agents and sub.name not in ctx.known_agents:
            ctx.error(
                "sub_agent_ref_unknown",
                (
                    f"Sub-agent '{sub.name}' references '{sub.ref}' but no agent with "
                    f"that name is found in this project."
                ),
                path=f"sub_agents[{si}].ref",
            )


def _check_required_slot_prompts(ctx: _Ctx) -> None:
    """Required slots must have an ask_if_missing prompt."""
    for ci, condition in enumerate(ctx.schema.conditions):
        for gi, goal in enumerate(condition.goals):
            for si, slot in enumerate(goal.slots):
                if slot.required and not slot.ask_if_missing:
                    ctx.error(
                        "slot_missing_prompt",
                        (
                            f"Slot '{slot.name}' in goal '{goal.name}' is required "
                            f"but has no 'ask_if_missing' prompt. Add the question to ask."
                        ),
                        path=f"conditions[{ci}].goals[{gi}].slots[{si}].ask_if_missing",
                    )


def _check_required_tool_input_descriptions(ctx: _Ctx) -> None:
    """Required tool inputs must have a description."""
    for ti, tool in enumerate(ctx.schema.tools):
        for ii, inp in enumerate(tool.inputs):
            if inp.required and not inp.description:
                ctx.error(
                    "tool_input_missing_description",
                    (
                        f"Required input '{inp.name}' on tool '{tool.name}' has no "
                        f"description. Add one so the model knows how to fill it."
                    ),
                    path=f"tools[{ti}].inputs[{ii}].description",
                )


def _check_has_conditions(ctx: _Ctx) -> None:
    """An agent with no conditions has no routing targets — probably a mistake."""
    if not ctx.schema.conditions:
        ctx.error(
            "no_conditions",
            (
                "This agent has no conditions defined. The router has nothing to route to. "
                "Add at least one condition with one or more goals."
            ),
            path="conditions",
        )


# ── WARNING validators ─────────────────────────────────────────────────────────

def _check_unused_tools(ctx: _Ctx) -> None:
    """Tools defined but never referenced in any goal are likely a mistake."""
    referenced = ctx.schema.all_referenced_tool_names()
    for tool in ctx.schema.tools:
        if tool.name not in referenced:
            ctx.warn(
                "tool_unused",
                (
                    f"Tool '{tool.name}' is defined but not referenced in any goal. "
                    f"Either add it to a goal's tools list or remove it."
                ),
                path=f"tools[name={tool.name!r}]",
            )


def _check_conditions_have_goals(ctx: _Ctx) -> None:
    for ci, condition in enumerate(ctx.schema.conditions):
        if not condition.goals:
            ctx.warn(
                "condition_no_goals",
                f"Condition '{condition.name}' has no goals defined.",
                path=f"conditions[{ci}].goals",
            )


def _check_escalation_path(ctx: _Ctx) -> None:
    """Agents without any handoff have no escalation path."""
    if not ctx.schema.handoffs:
        ctx.warn(
            "no_handoff",
            (
                "No handoffs are defined. The agent has no escalation path. "
                "Consider adding a human escalation handoff."
            ),
            path="handoffs",
        )


def _check_interrupt_triggers(ctx: _Ctx) -> None:
    """Agents without interrupt triggers have no emergency override."""
    if not ctx.schema.interrupt_triggers:
        ctx.warn(
            "no_interrupt_triggers",
            (
                "No interrupt triggers are defined. The agent has no emergency override "
                "mechanism. Consider adding a safety trigger."
            ),
            path="interrupt_triggers",
        )


def _check_persona_length(ctx: _Ctx) -> None:
    """Very short personas give the model insufficient role context."""
    if ctx.schema.persona and len(ctx.schema.persona.strip()) < 50:
        ctx.warn(
            "persona_too_short",
            (
                "The persona description is very short. A richer persona gives the model "
                "more context to behave consistently. Aim for 2–4 sentences."
            ),
            path="persona",
        )


# ── INFO suggestions ───────────────────────────────────────────────────────────

def _check_goals_have_sequences(ctx: _Ctx) -> None:
    """Goals with rules but no sequence are less predictable."""
    for condition in ctx.schema.conditions:
        for goal in condition.goals:
            if goal.rules and not goal.sequences:
                ctx.info(
                    "goal_no_sequence",
                    (
                        f"Goal '{goal.name}' has rules but no sequence. "
                        f"Adding a sequence makes the agent's behaviour more predictable."
                    ),
                )


def _check_condition_goal_count(ctx: _Ctx) -> None:
    """Many goals under one condition may benefit from sub-agents."""
    for condition in ctx.schema.conditions:
        if len(condition.goals) >= 4:
            ctx.info(
                "many_goals_in_condition",
                (
                    f"Condition '{condition.name}' has {len(condition.goals)} goals. "
                    f"Consider splitting complex conditions across sub-agents."
                ),
            )


# ── Serialisation helper ───────────────────────────────────────────────────────

def _issue_dict(issue: ValidationIssue) -> dict:
    return {
        "severity": issue.severity.value,
        "code": issue.code,
        "message": issue.message,
        "path": issue.path,
    }
