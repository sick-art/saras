# Executor

The executor is the runtime core of Saras. It takes a `CompiledAgent` and a conversation turn, assembles the right context, runs the LLM tool loop, and persists every span.

**Entry point:** `backend/saras/core/executor.py`

---

## Turn Lifecycle

![executor-turn-lifecycle](../assets/diagrams/executor-turn-lifecycle.svg)

---

## RouterDecision

Before each LLM call, the executor makes a routing decision:

| Decision | When |
|----------|------|
| **New goal** | User message matches a goal's conditions |
| **Continue goal** | Active goal's slot fill is incomplete |
| **Interrupt** | An `interrupt_trigger` condition fires |
| **Handoff** | A handoff trigger condition fires |
| **Fallback** | No goal matches; agent responds from persona + global rules |

---

## Tool Loop

The executor runs a multi-turn tool loop within a single user turn:

1. Send assembled context + user message to LiteLLM
2. If the model returns a tool call → execute the tool
3. Emit a `span_event` to Redis with tool name, inputs, outputs, latency
4. Feed the tool result back into the next LLM call
5. Repeat until the model returns a final text response
6. Stream the final response tokens to the client

---

## Span Events

Every significant action within a turn emits a structured span event on the Redis channel `spans:{run_id}`:

```json
{
  "type": "tool_call",
  "span_id": "span_abc123",
  "run_id": "run_xyz",
  "tool_name": "look_up_order",
  "inputs": {"order_id": "ORD-9876"},
  "output": {"status": "shipped", "eta": "2026-04-16"},
  "latency_ms": 342,
  "timestamp": "2026-04-14T10:23:01Z"
}
```

The Simulator UI subscribes to this channel via WebSocket and renders span events in real time on the LiveGraph.

---

## Persistence

At the end of each turn, the executor writes:

- **Run** — one row per conversation session (`backend/saras/db/models.py`)
- **Span** — one row per LLM call or tool call within the turn

These are the raw records that power the [Observability](../architecture/overview.md) trace explorer and Eval runner.

---

## Related

- [Compiler](compiler.md) — produces the `CompiledAgent` the executor receives
- [Routing](../concepts/routing.md) — `RouterDecision` and slot fill logic
- [Context Layers](../concepts/context-layers.md) — how the 8 layers are assembled per turn
