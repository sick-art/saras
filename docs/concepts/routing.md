# Routing

Routing is the decision the executor makes at the start of every turn: which goal (if any) should handle this message, and what context should be assembled?

---

## RouterDecision

The `RouterDecision` is computed before each LLM call:

![routing-decision](../assets/diagrams/routing-decision.svg)

### Decision Types

| Decision | Description |
|----------|-------------|
| `interrupt` | An `interrupt_trigger` fired — highest priority, overrides active goal |
| `handoff` | A handoff trigger fired — route to external target |
| `continue_goal` | Active goal has unfilled required slots — continue slot fill |
| `new_goal` | A goal's conditions match the user message |
| `fallback` | Nothing matched — respond from persona + global rules only |

---

## Condition Matching

Conditions are **natural language strings** evaluated by the LLM as part of the routing prompt. There is no regex or keyword matching.

Example goal conditions:

```yaml
goals:
  - name: Handle Refund Request
    conditions:
      - The user mentions a refund, return, or wanting money back
      - The user says their order was wrong or damaged
```

The router sends these conditions to a lightweight LLM call:

```
Given the user's message, which of the following conditions is true?
[list of conditions from all goals]

User message: "I want to return my order"
```

The LLM returns the matching condition → executor selects the corresponding goal.

---

## Slot Fill

When a goal has `slots`, the executor tracks fill state per session in Redis:

```python
slot_state = {
    "order_id": None,      # not yet collected
    "reason": "damaged"    # collected in previous turn
}
```

If any **required** slot is unfilled when a goal is entered, the executor routes to `continue_goal` and injects the slot's `prompt` into the next LLM call:

```
[Active goal: Handle Refund Request]
[Slots needed: order_id]
[Prompt the user for: What is your order ID?]
```

Once all required slots are filled, the executor proceeds to the goal's sequences.

---

## Interrupt Triggers

Interrupt triggers are checked **before** goal routing on every turn. They are designed for high-priority conditions that must preempt whatever the agent is doing:

```yaml
interrupt_triggers:
  - If the user says "cancel my account", immediately route to the Cancellation flow.
  - If the user expresses distress or uses crisis keywords, escalate to a human immediately.
```

An interrupt suspends the active goal (slot state is preserved) and handles the interrupt. The agent may resume the original goal afterward if appropriate.

---

## Routing Context Object

The full `RoutingContext` passed to the executor each turn:

```python
@dataclass
class RoutingContext:
    decision: Literal["interrupt", "handoff", "continue_goal", "new_goal", "fallback"]
    active_goal: Goal | None
    slot_state: dict[str, str | None]
    matched_condition: str | None
    handoff_target: str | None
    interrupt_trigger: str | None
```

---

## Related

- [Executor](../architecture/executor.md) — where `RouterDecision` is consumed
- [Context Layers](context-layers.md) — how the active goal's context is injected
- [Agent Schema](../architecture/agent-schema.md) — conditions, slots, interrupt triggers
