# Saras

**Saras** is a self-hosted, open-source platform for building conversational agents — fast, without a heavy engineering team, and without orchestration becoming the blocker.

---

## The Problem

Building a production-grade conversational agent today usually means stitching together routing logic, tool calling, context management, eval harnesses, and tracing — before you've even written a single conversational flow. For teams without a dedicated AI infra crew, the orchestration plumbing becomes the project, and the actual agent behaviour gets squeezed.

Saras flips that. The hard parts — routing between conditions, layering context, slot filling, handoffs, tool retries — are handled by the platform. Teams focus on what actually shapes the agent's quality:

- **Writing conversational flows and rules** in plain English
- **Simulating** them against realistic user turns
- **Evaluating** them with metric suites and LLM judges
- **Iterating** until the agent is robust

---

## How Saras Compares

A few tools sit in adjacent territory. Each makes different trade-offs:

| Tool | Strengths | Trade-off vs. Saras |
|------|-----------|---------------------|
| **OpenAI AgentKit** | First-party tool integrations, voice, vision, hosted infra | Vendor-locked to OpenAI models; less control over routing and context |
| **n8n** | Massive connector library, generic workflow automation | Workflow-first, not conversation-first; no built-in agent eval loop |
| **Replit Agents** | Instant prototyping, code generation focus | Aimed at building software, not running customer-facing conversational agents |
| **Saras** | YAML-first conversational agent definition, built-in simulate + observe + evaluate, self-hosted | **Text-only today** — voice and richer modalities are on the roadmap, not in the box |

Saras is intentionally narrow: text-based conversational agents, end-to-end, owned by your team. Voice agents and a broader connector catalogue are future scope.

---

## Lifecycle

![Saras lifecycle: Build → Simulate → Deploy → Observe → Evaluate, looping back to Build](assets/diagrams/lifecycle.excalidraw)

| Phase | What happens |
|-------|-------------|
| **Build** | Define agents in YAML — persona, tools, conditions, goals, sequences, handoffs |
| **Simulate** | Drive the agent over a WebSocket; watch every span land in real time |
| **Deploy** | Ship via Docker Compose; route traffic through the executor |
| **Observe** | Persist runs and spans to Postgres; aggregate to DuckDB; explore in the Traces UI |
| **Evaluate** | Run preset or custom metric suites against trace data and golden datasets |
| **Improve** | Promote review-queue items into datasets; feed back into the builder |

---

## Quick Links

- [Getting Started](getting-started.md) — Clone, configure, build your first agent, simulate, and evaluate
- [Architecture Overview](architecture/overview.md) — System diagram and component map
- [Agent Schema](architecture/agent-schema.md) — The YAML format with an annotated example
- [Self-Hosting](self-hosting.md) — Get running in minutes with Docker Compose
- [SDK](sdk.md) — Planned interface for instrumenting external code
