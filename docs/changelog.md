# Changelog

## Unreleased

### Builder
- Outline + per-node form replaces the previous flat block list — full schema coverage with bidirectional YAML sync.
- Chat builder streams explanation deltas and YAML diffs over SSE; the editor applies the updated YAML live.
- YAML / Form / Graph / Chat all share the same Zustand store with `yamlContent` as source of truth.

### Simulator
- WebSocket session at `/api/projects/{id}/agents/{id}/simulate` with cancel-mid-turn safety.
- Real-time span fan-out via Redis pub/sub on `spans:{run_id}`.
- LiveGraph and ConversationPane render router decisions, LLM calls, tool calls, slot fills, interrupts, and handoffs as they happen.

### Executor
- Router → slot fill → primary LLM tool loop with `MAX_TOOL_ITERATIONS = 5`.
- Slot fill short-circuits the primary model call; values extracted from the **whole** conversation, not just the last message.
- Deterministic Faker-backed mock payloads per tool type (LookupTool / KnowledgeTool / ActionTool) for Phase 2.
- Run rows always reach a terminal state (`completed` / `failed` / `cancelled`) even on WebSocket drop.

### Observability
- Traces UI: runs list, run detail with full span tree, sessions grouping, DuckDB-backed analytics.
- DuckDB sync from Postgres via `tracing/collector.py` after every completed run.

### Evals
- Suite + run model with SSE progress streaming.
- Preset metrics: `goal_completion`, `hallucination_detection`, plus deterministic `tool_call_accuracy`, `slot_fill_efficiency`, `tone`, semantic similarity, BLEU, ROUGE-L, completion / context metrics.
- LLM judge runner with rubric-based scoring; per-turn or whole-conversation scope.

### Platform
- Postgres 16 + Redis 7 + DuckDB via Docker Compose.
- LiteLLM provider adapter with tenacity retries; supports Anthropic, OpenAI, and Google.
- Frontend rebuilt on shadcn (Mira theme) + Base UI.

---

*Saras follows [Semantic Versioning](https://semver.org). Releases will be tagged once the platform reaches a stable public API.*
