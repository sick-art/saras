# Context Layers

Saras uses **progressive context disclosure**. Instead of stuffing the full agent definition into every LLM call, context is pre-split into 8 layers and the executor only injects the ones relevant to the current turn.

This keeps tokens down, keeps the model focused, and lets agents scale to many goals without paying for all of them on every message.

---

## The 8 Layers

| # | Label | Always injected? | Built at | Content |
|---|-------|------------------|----------|---------|
| 1 | `base` | **Yes** | Compile time | `persona` + `tone` + `global_rules` + `out_of_scope` + list of `interrupt_triggers` (names + first sentence) |
| 2 | `condition:<Name>` | Only the active one | Compile time | Active condition name + full description |
| 3 | `goal:<Condition>:<Goal>` | Only the active one | Compile time | Active goal description + optional `tone` override |
| 4 | (slot fill) | Runtime short-circuit | Runtime | Injected as a direct `ask_if_missing` question — never reaches the primary LLM |
| 5 | `sequence:<Condition>:<Goal>:<Seq>` | All sequences for the active goal | Compile time | Numbered steps, including `@tool:` references |
| 6 | `goal_rules_tools:<Condition>:<Goal>` | Only for the active goal | Compile time | Goal-scoped rules + descriptions of allowed tools |
| 7 | tool results | Inline during tool loop | Runtime | Tool output is appended to the message array as `role=tool` entries |
| 8 | memory | Reserved | Runtime | Future: cross-turn retrieved memory |

Layers 1–6 are produced up front by [compiler.py](../../backend/saras/core/compiler.py) → `_build_context_layers`. Layers 7 and 8 are purely runtime.

---

## Assembly Per Turn

The executor's `_assemble_system_prompt(compiled, decision)` picks layers by label based on the `RouterDecision`:

![Context layer assembly: always inject Layer 1, then branch on decision type — interrupt/handoff skip goal layers, goal path adds Layers 2, 3, 5, 6 → chat_completion loop with Layer 7 tool results until no more tool_calls](../assets/diagrams/context-layers-assembly.excalidraw)

Two branches skip goal layers entirely:

- **Interrupt** — Layer 1 + `EMERGENCY OVERRIDE — <trigger.name>: <trigger.action>`.
- **Handoff** — Layer 1 + `HANDOFF REQUIRED — transfer this conversation to: <target>. Pass this context: <context_to_pass>`.

Slot fill (Layer 4) never reaches the primary model at all — the executor short-circuits with the slot's `ask_if_missing` prompt directly.

---

## Why Not Inject Everything?

Consider an agent with 12 conditions, each with 2 goals, each with 2 sequences of 5 steps, and 5 tools. Naive prompt stuffing would feed **every** goal's sequences and every tool's recovery guidance on every turn — mostly irrelevant to the message being handled.

Progressive layers mean:

- Only the active goal's sequences are in-context (typically 1 goal out of N).
- Only tools usable in the active goal appear in the `tools=...` parameter to the LLM.
- `on_failure` / `on_empty_result` guidance lives on the tool definition description rather than in the system prompt, so the model only sees it when it's about to call that tool.

The cost saving is quadratic in agent complexity.

---

## Implementation Notes

- Labels are deterministic and stable (`f"goal:{cond.name}:{goal.name}"`). The executor looks them up by label — it never re-parses YAML.
- `always_inject=True` is set on Layer 1 only; every other layer is conditional.
- Layer 1 is also exposed as `CompiledAgent.base_system_prompt` for callers that want just the base prompt (e.g. debugging, prompt previews in the builder).

---

## Related

- [Compiler](../architecture/compiler.md) — where layers 1–6 are built
- [Executor](../architecture/executor.md) — where layers are selected and assembled each turn
- [Agent Schema](../architecture/agent-schema.md) — the fields each layer draws from
- [Routing](routing.md) — how the active condition/goal is chosen
