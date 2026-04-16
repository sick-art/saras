# Tools

Tools are the actions your agent can take — API calls, database lookups, form submissions. In Saras, tools are **defined once at the agent level** and **referenced by name inside goals**.

---

## Tool Definition

```yaml
tools:
  - name: Look Up Order          # Human-readable name (used for @tool references)
    description: >
      Retrieves order details by order ID from the order management system.
    inputs:
      order_id: The order ID to look up (required)
      include_history: Whether to include order history (optional, default false)
    on_failure: >
      Apologize to the user and ask them to check their confirmation email
      for the correct order ID.
    on_empty_result: >
      Tell the user no order was found with that ID and offer to escalate
      to a human agent.
```

### Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Human-readable name. Referenced in sequences as `@tool: Name`. |
| `description` | Yes | What the tool does. Shown to the LLM in the tool schema. |
| `inputs` | Yes | Key-value map of input name → description. Append `(required)` or `(optional)` to the value. |
| `on_failure` | Recommended | Natural language instruction to the agent if the tool call throws an error. |
| `on_empty_result` | Recommended | Natural language instruction if the tool returns no data. |

---

## Referencing Tools in Goals

Tools are referenced inside goal sequences using the `@tool: Tool Name` syntax:

```yaml
goals:
  - name: Handle Refund Request
    sequences:
      - Acknowledge the refund request warmly.
      - You MUST invoke @tool: Look Up Order to verify the order exists.
      - Confirm the order details with the user before proceeding.
      - You MUST invoke @tool: Submit Refund with the confirmed order ID.
      - Confirm the refund has been submitted and give the user a timeline.
```

The `You MUST invoke` phrasing is intentional — it signals a hard requirement to the LLM, not a suggestion.

---

## Tool Schema (Compiled)

The compiler transforms your tool definition into an LLM-compatible schema. For the example above:

```json
{
  "name": "look_up_order",
  "description": "Retrieves order details by order ID from the order management system.\n\nOn failure: Apologize to the user...\nOn empty result: Tell the user no order was found...",
  "input_schema": {
    "type": "object",
    "properties": {
      "order_id": {
        "type": "string",
        "description": "The order ID to look up (required)"
      },
      "include_history": {
        "type": "string",
        "description": "Whether to include order history (optional, default false)"
      }
    },
    "required": ["order_id"]
  }
}
```

The `required` array is inferred from which inputs have `(required)` in their description.

---

## Tool Execution

Tools are executed by the **executor's tool loop**. Each tool call produces a span:

![tools-execution](../assets/diagrams/tools-execution.svg)

---

## Tool Scoping

A tool defined at the agent level is available to **all goals** unless you restrict it. To make a tool available only within a specific goal, list it under that goal's `tools` key:

```yaml
goals:
  - name: Handle Refund Request
    tools:
      - Submit Refund    # only callable within this goal
```

---

## Related

- [Agent Schema](../architecture/agent-schema.md) — full schema reference
- [Executor](../architecture/executor.md) — how the tool loop runs
- [Routing](routing.md) — how goals and tool availability are selected
