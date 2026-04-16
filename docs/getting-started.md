# Getting Started

This guide takes you from a fresh clone to a running agent you've simulated and evaluated — in about ten minutes.

---

## 1. Install

You need **Docker Engine 24+** with **Docker Compose v2** and at least one LLM provider key (Anthropic, OpenAI, or Google).

```bash
git clone https://github.com/sick-art/saras.git
cd saras
cp .env.example .env
```

Open `.env` and set at least one provider key:

```env
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...
SARAS_API_KEY=change-me-in-production
```

Start the stack and apply migrations:

```bash
docker compose up -d
docker compose exec backend alembic upgrade head
```

The UI is now at [http://localhost:3000](http://localhost:3000). Full deployment options live in [Self-Hosting](self-hosting.md).

---

## 2. Create your first agent

You have two starting points:

- **From a sample** — open the **Samples** gallery and clone one. Good for seeing a complete agent (persona, tools, conditions, goals, sequences) before writing your own.
- **From scratch** — create a new agent in a project and describe it in the **Chat** view. The builder will write the YAML for you and stream diffs back as you refine it.

The agent definition has four interchangeable views, all reading the same YAML:

| View | When to use it |
|------|----------------|
| **Chat** | Describe changes in plain English — "add a refund condition that asks for the order ID" |
| **Outline / Form** | Click into a condition, goal, tool, or sequence and edit fields directly |
| **Graph** | See the conversational structure as nodes and handoffs |
| **YAML** | Power-user editing in a Monaco editor |

The [Agent Schema reference](architecture/agent-schema.md) explains every field.

---

## 3. Simulate

Open the **Simulate** tab on your agent. Type a user message and watch the executor run live: router decisions, slot fills, LLM calls, tool calls, and handoffs all stream in as spans over a WebSocket.

This is the fastest way to find broken conditions, missing tools, or vague rules — fix them in the builder, save, and run the next turn.

---

## 4. Evaluate

When the agent is roughly working, move to the **Evals** tab.

1. Build a **dataset** — either by hand, by importing CSV, or by promoting interesting runs from the Traces view.
2. Pick a **metric suite** — preset deterministic checks (tool-call correctness, handoff routing) or LLM-as-judge presets (helpfulness, factuality, tone).
3. Run the suite against the dataset. Failures land in the **Review queue**, where you can label them and feed them back into the dataset for the next iteration.

This is the loop: build → simulate → evaluate → fix → re-evaluate.

---

## 5. Deploy

The same `docker compose up -d` you ran in step 1 is your production stack. Production hardening (TLS, secrets, backups) is covered in [Self-Hosting → Production Deployment](self-hosting.md#production-deployment).

---

## Where to go next

- [Agent Schema](architecture/agent-schema.md) — every field of the YAML, with an annotated example
- [Context Layers](concepts/context-layers.md) — how Saras keeps prompts focused as agents grow
- [Routing](concepts/routing.md) — how the router picks the next condition or goal
- [Tools](concepts/tools.md) — defining tools, failure handling, and empty-result behaviour
- [Architecture Overview](architecture/overview.md) — the full system diagram
