# Compiler

The compiler transforms a raw YAML agent definition into a `CompiledAgent` — a structured object containing the final system prompt and tool definitions ready for the executor.

**Entry point:** `backend/saras/core/compiler.py` → `compile_from_yaml(yaml_str: str) -> CompiledAgent`

---

## Compilation Pipeline

![compiler-pipeline](../assets/diagrams/compiler-pipeline.svg)

---

## System Prompt Assembly

The system prompt is built by concatenating these sections in order:

1. **Persona** — verbatim from `persona` field
2. **Tone** — global tone directive
3. **Global Rules** — bulleted list from `global_rules`
4. **Out of Scope** — explicit refusal list
5. **Interrupt Triggers** — high-priority conditions prepended before goal routing
6. **Goal Summaries** — brief descriptions of each goal (conditions only; full sequences injected at runtime by context layers)
7. **Handoffs** — when and how to delegate

The full goal sequences and slot definitions are intentionally **not** injected into the base system prompt — they are added progressively per turn by the executor via [context layers](../concepts/context-layers.md).

---

## Tool Definition Builder

For each tool in `agent.tools`, the compiler produces an LLM-compatible tool schema:

```python
{
    "name": "look_up_order",          # snake_cased from "Look Up Order"
    "description": "Retrieves order details by order ID.\n\nOn failure: ...\nOn empty result: ...",
    "input_schema": {
        "type": "object",
        "properties": {
            "order_id": {"type": "string", "description": "The order ID to look up (required)"}
        },
        "required": ["order_id"]
    }
}
```

`on_failure` and `on_empty_result` are appended to the tool description so the model has recovery instructions without needing extra routing logic.

---

## Routing Context Builder

The `RoutingContext` is assembled fresh each turn by the executor. The compiler only builds the _template_ — the executor fills in runtime values (slot state, conversation history, active goal).

See [Routing](../concepts/routing.md) for the full runtime flow.

---

## Related

- [Agent Schema](agent-schema.md) — the input format
- [Executor](executor.md) — what runs the compiled agent
- [Context Layers](../concepts/context-layers.md) — how context is injected at runtime
