# Multi-Agent

Saras supports multi-agent systems where a **root agent** delegates to one or more **sub-agents**. From the user's perspective, the conversation remains a single coherent thread.

---

## Delegation Model

![multi-agent-delegation](../assets/diagrams/multi-agent-delegation.svg)

The root agent is responsible for:
- Routing the user message to the correct sub-agent based on conditions
- Maintaining the global conversation context
- Synthesizing sub-agent responses before replying to the user

Sub-agents are full `AgentSchema` definitions — they have their own persona, tools, goals, and rules.

---

## Schema

Sub-agents are declared at the root agent level:

```yaml
name: Orchestrator
persona: You coordinate between specialist agents.

sub_agents:
  - name: Billing Specialist
    agent_id: billing-agent-v2
    trigger: The user has a billing, invoice, or payment question.

  - name: Technical Support
    agent_id: tech-support-v1
    trigger: The user reports a bug, error, or technical issue.
```

The `trigger` is a natural language condition evaluated by the router — same mechanism as goal conditions.

---

## Execution Flow

![multi-agent-sequence](../assets/diagrams/multi-agent-sequence.svg)

---

## Context Handoff

When the root delegates to a sub-agent, it passes:

- **Conversation history** up to this point (summarized if long)
- **Active slots** from the root agent that are relevant to the sub-agent
- **Routing reason** — why this sub-agent was selected

The sub-agent does not receive the root's full system prompt — only what is relevant to its task.

---

## Span Attribution

Each sub-agent execution produces its own spans, tagged with:

```json
{
  "agent_id": "billing-agent-v2",
  "parent_run_id": "run_root_xyz",
  "delegation_reason": "billing question"
}
```

This allows the trace explorer to show the full delegation tree.

---

## Related

- [Executor](executor.md) — single-agent execution model
- [Routing](../concepts/routing.md) — how triggers are evaluated
- [Agent Schema](agent-schema.md) — `SubAgent` type reference
