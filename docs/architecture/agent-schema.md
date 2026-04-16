# Agent Schema

Saras agents are defined entirely in YAML. The YAML is the single source of truth — it is rendered simultaneously in the Chat view, Form view, Graph view, and the raw YAML editor.

---

## Design Principles

- **Natural language first** — no DSL, no hidden variables, no underscore IDs
- **Hierarchy over flat config** — structure reflects how the agent actually reasons
- **Tools defined once** — at the agent level with full config; referenced by name inside goals
- **Sequences in plain English** — steps are prose; tool invocations are `@tool: Tool Name` references

---

## Hierarchy

![agent-schema-hierarchy](../assets/diagrams/agent-schema-hierarchy.svg)

---

## Annotated Example

```yaml
name: Support Agent
persona: >
  You are a friendly support agent for Acme Corp.
  You are concise, empathetic, and never make up answers.

tone: professional and warm

global_rules:
  - Never reveal internal pricing formulas.
  - Escalate to a human if the user expresses distress.

interrupt_triggers:
  - If the user says "cancel my account", immediately route to the Cancellation flow.

out_of_scope:
  - Questions about competitors
  - Medical or legal advice

tools:
  - name: Look Up Order
    description: Retrieves order details by order ID.
    inputs:
      order_id: The order ID to look up (required)
    on_failure: Apologize and ask the user to check their confirmation email.
    on_empty_result: Tell the user no order was found and offer to escalate.

  - name: Submit Refund
    description: Submits a refund request for a given order.
    inputs:
      order_id: The order ID to refund (required)
      reason: The reason for the refund (optional)
    on_failure: Inform the user the refund could not be submitted and offer a callback.

goals:
  - name: Handle Refund Request
    conditions:
      - The user mentions a refund, return, or money back
    tone: extra empathetic
    slots:
      - name: order_id
        prompt: What is your order ID?
    sequences:
      - Acknowledge the refund request warmly.
      - You MUST invoke @tool: Look Up Order to verify the order exists.
      - Confirm the order details with the user.
      - You MUST invoke @tool: Submit Refund with the confirmed order ID.
      - Confirm the refund has been submitted and provide a timeline.
    rules:
      - Do not process refunds older than 90 days; escalate instead.

handoffs:
  - name: Escalate to Human
    trigger: The user requests a human, or the issue cannot be resolved automatically.
    target: human_support_queue
```

---

## Schema Types (Pydantic)

Defined in `backend/saras/core/schema.py`:

| Type | Purpose |
|------|---------|
| `AgentSchema` | Root agent definition |
| `AgentTool` | Tool with description, inputs, `on_failure`, `on_empty_result` |
| `Goal` | Named goal with conditions, slots, sequences, rules, tool refs |
| `Condition` | Natural language condition string |
| `Handoff` | Named handoff with trigger and target |
| `InterruptTrigger` | High-priority condition checked before goal routing |
| `SubAgent` | Reference to a child agent for multi-agent delegation |
| `CompiledAgent` | Output of the compiler — system prompt + tool definitions |
| `RoutingContext` | Assembled per-turn context passed to the executor |
| `ContextLayer` | One of 8 progressive context layers |

---

## Related

- [Compiler](compiler.md) — how this schema becomes a runnable `CompiledAgent`
- [Context Layers](../concepts/context-layers.md) — how context is injected progressively per turn
- [Tools](../concepts/tools.md) — full tool configuration reference
