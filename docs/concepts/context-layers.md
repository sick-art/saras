# Context Layers

Saras uses **progressive context disclosure** — instead of injecting the full agent definition into every LLM call, context is assembled in 8 layers, with each layer added only when relevant. This reduces token usage and keeps the model focused.

---

## The 8 Layers

![context-layers](../assets/diagrams/context-layers.svg)

| Layer | Always injected? | Content |
|-------|-----------------|---------|
| **1. Base Persona** | Yes | `persona` + global `tone` |
| **2. Global Rules** | Yes | `global_rules` list |
| **3. Out-of-Scope** | Yes | `out_of_scope` list |
| **4. Interrupt Triggers** | Yes | `interrupt_triggers` — highest priority |
| **5. Active Goal** | Only when a goal is active | Full goal sequences, rules, and tool references |
| **6. Slot State** | Only when slots are in progress | Which slots are filled, which are pending |
| **7. Conversation Summary** | Only when history > threshold | LLM-generated rolling summary of earlier turns |
| **8. Recent History** | Yes (last N turns) | Verbatim last N messages |

---

## Why Not Inject Everything?

Consider an agent with 12 goals, each with 5-step sequences and 3 slots. Injecting all of this on every turn would:

- Waste tokens on irrelevant goals
- Dilute model attention on the active task
- Increase latency and cost linearly with agent complexity

With progressive context, layers 5 and 6 (the most verbose) are only present when the model actually needs them.

---

## Layer Assembly (Runtime)

The executor assembles layers per turn in `executor.py`:

```python
context = []
context.append(build_base_persona(compiled_agent))      # always
context.append(build_global_rules(compiled_agent))       # always
context.append(build_out_of_scope(compiled_agent))       # always
context.append(build_interrupt_triggers(compiled_agent)) # always

if routing.active_goal:
    context.append(build_goal_context(routing.active_goal))  # layer 5
    if routing.active_goal.has_slots:
        context.append(build_slot_state(routing.slot_state)) # layer 6

if len(history) > SUMMARY_THRESHOLD:
    context.append(build_summary(history))  # layer 7

context.append(build_recent_history(history, n=RECENT_TURNS))  # always
```

---

## Tuning

You can adjust the thresholds in `backend/saras/config.py`:

| Setting | Default | Effect |
|---------|---------|--------|
| `CONTEXT_SUMMARY_THRESHOLD` | 20 turns | When to start summarizing history |
| `CONTEXT_RECENT_TURNS` | 6 | How many turns to include verbatim |

---

## Related

- [Executor](../architecture/executor.md) — where layers are assembled at runtime
- [Agent Schema](../architecture/agent-schema.md) — the fields each layer draws from
- [Routing](routing.md) — how the active goal is determined
