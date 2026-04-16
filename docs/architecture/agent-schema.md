# Agent Schema

Saras agents are defined entirely in YAML. The YAML is the single source of truth — it is rendered simultaneously in the Chat view, Outline + Form view, Graph view, and the raw YAML editor.

**Canonical Python model:** [backend/saras/core/schema.py](../../backend/saras/core/schema.py)
**Mirrored TypeScript types:** [frontend/src/types/agent.ts](../../frontend/src/types/agent.ts)

---

## Design Principles

- **Natural language first** — all condition, trigger, and handoff descriptions are plain English strings. No DSL, no boolean expressions, no hidden variable names.
- **Human-readable names only** — tool names, goal names, slot names, and condition names are written like you'd say them in English (`Order Lookup`, not `order_lookup`). IDs are never authored by the user.
- **Tools defined once** — tools live at the agent level with full config (`type`, `inputs`, `on_failure`, `on_empty_result`). Goals reference tools by name.
- **Hierarchy reflects reasoning** — `Agent → Conditions → Goals → (Slots, Sequences, Rules, Tool refs)`. Sequences are numbered natural-language steps with embedded `@tool: Tool Name` references.

---

## Hierarchy

![Agent schema hierarchy: Agent root → persona/tone, global_rules, interrupt_triggers, out_of_scope, handoffs, tools, sub_agents, and conditions → goals → slots/sequences/rules/tools](../assets/diagrams/agent-hierarchy.excalidraw)

---

## Annotated Example

```yaml
agent:
  name: Support Agent
  version: "1.0.0"
  description: Friendly support agent for Acme Corp.

  models:
    primary: claude-sonnet-4-6
    router: claude-haiku-4-5-20251001

  persona: >
    You are a friendly support agent for Acme Corp. You are concise,
    empathetic, and never make up answers.

  tone: professional and warm

  global_rules:
    - Never reveal internal pricing formulas.
    - Escalate to a human if the user expresses distress.

  interrupt_triggers:
    - name: Crisis Signal
      description: >
        The user expresses distress, self-harm, or emergency language.
      action: >
        Acknowledge calmly, share a crisis hotline, and transfer to a human.

  out_of_scope:
    - Questions about competitors
    - Medical or legal advice

  handoffs:
    - name: Escalate to Human
      description: >
        The user requests a human, or the issue cannot be resolved automatically.
      target: Human Support Queue
      context_to_pass: Order ID, refund reason, and the last two turns.

  tools:
    - name: Order Lookup
      type: LookupTool
      description: Retrieves order details by order ID.
      inputs:
        - name: Order Identifier
          description: The order number the customer provided (e.g. ORD-12345).
          required: true
      on_failure: Apologize and ask the user to check their confirmation email.
      on_empty_result: Tell the user no order was found and offer to escalate.

    - name: Submit Refund
      type: ActionTool
      description: Submits a refund request for a given order.
      confirmation_required: true
      inputs:
        - name: Order Identifier
          description: The order number being refunded.
          required: true
        - name: Refund Reason
          description: Short reason provided by the user.
          required: false
      on_failure: Inform the user the refund could not be submitted and offer a callback.

  conditions:
    - name: Refund Requested
      description: >
        The user mentions a refund, return, money back, or says the order was wrong.
      goals:
        - name: Handle Refund Request
          description: Verify the order and submit a refund when eligible.
          tone: extra empathetic
          slots:
            - name: Order Identifier
              description: The order the refund is for.
              required: true
              ask_if_missing: What is the order number on your confirmation email?
          sequences:
            - name: Verify and refund
              steps:
                - Acknowledge the refund request warmly.
                - You MUST invoke @tool: Order Lookup to verify the order exists.
                - Confirm the order details with the user.
                - You MUST invoke @tool: Submit Refund with the confirmed order ID.
                - Confirm the refund has been submitted and provide a timeline.
          rules:
            - Do not process refunds older than 90 days; escalate instead.
          tools:
            - Order Lookup
            - Submit Refund
```

---

## Schema Reference

All types are defined in [backend/saras/core/schema.py](../../backend/saras/core/schema.py).

### `AgentSchema` (root)

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | Required. Shown in the UI and used for handoff targeting. |
| `version` | string | Defaults to `"1.0.0"`. |
| `description` | string? | Optional one-liner. |
| `models` | `AgentModels` | `primary` (required), plus optional `router`, `judge`, `fallback`. |
| `persona` | string? | Natural language role brief. |
| `tone` | string? | Default communication style. |
| `global_rules` | string[] | Always-active invariants. |
| `interrupt_triggers` | `InterruptTrigger[]` | Checked before every response. |
| `out_of_scope` | string[] | Topics to refuse. |
| `handoffs` | `Handoff[]` | Transfer rules. |
| `tools` | `AgentTool[]` | Tool catalogue referenced by name. |
| `conditions` | `Condition[]` | The main behavior tree. |
| `sub_agents` | `SubAgent[]` | Child agents for delegation. |

### `AgentTool`

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | Human-readable, referenced by goals and `@tool:` in sequences. |
| `type` | `LookupTool \| KnowledgeTool \| ActionTool` | Drives mock payload shape in Phase 2. |
| `description` | string | Shown to the LLM. |
| `endpoint` / `auth` | string? | For Lookup / Action tools (Phase 3). |
| `source` / `collection` | string? | For Knowledge tools (Phase 3). |
| `confirmation_required` | bool | ActionTool only. |
| `inputs` | `ToolInput[]` | Each has `name`, `description`, `required`. |
| `on_failure` | string? | Natural-language recovery instruction. |
| `on_empty_result` | string? | Natural-language instruction when the result is empty. |

### `Condition` → `Goal`

Conditions hold one or more goals. A goal has:

| Field | Type | Notes |
|-------|------|-------|
| `name`, `description` | string | Human-readable. |
| `tone` | string? | Optional goal-local tone override. |
| `slots` | `Slot[]` | Each with `ask_if_missing` prompt. |
| `sequences` | `Sequence[]` | Each sequence has a `name` and ordered `steps` (strings). |
| `rules` | string[] | Constraints specific to this goal. |
| `tools` | string[] | Names of agent-level tools available here. |

### `Handoff`, `InterruptTrigger`, `SubAgent`

- `Handoff`: `name`, `description`, `target` (agent name or `"Human Support Queue"`), `context_to_pass`.
- `InterruptTrigger`: `name`, `description`, optional `action`. Evaluated before goal routing.
- `SubAgent`: either `ref` (agent name in project) or `inline` (embedded `AgentSchema`).

### Compiled artefacts

| Type | Produced by | Purpose |
|------|-------------|---------|
| `CompiledAgent` | [compiler.py](../../backend/saras/core/compiler.py) | `base_system_prompt`, `tool_definitions`, `routing_context`, `context_layers[]` |
| `RoutingContext` | compiler | NL routing context passed to the router model each turn |
| `ContextLayer` | compiler | One of 8 progressive layers — see [Context Layers](../concepts/context-layers.md) |
| `ToolDefinition` | compiler | Provider-agnostic function-calling shape (`name`, `description`, JSON Schema) |

---

## Related

- [Compiler](compiler.md) — how the schema becomes a `CompiledAgent`
- [Context Layers](../concepts/context-layers.md) — what the compiler emits for progressive disclosure
- [Tools](../concepts/tools.md) — tool authoring reference
