# Saras

**Saras** is a self-hosted, open-source platform for the full agent lifecycle — from building and simulating agents to deploying, observing, evaluating, and improving them.

---

## The Problem

No single tool covers the complete agent lifecycle today.

| Tool | Build | Simulate | Observe | Evaluate | Improve |
|------|-------|----------|---------|----------|---------|
| LangSmith | — | — | Partial | Partial | — |
| Phoenix | — | — | Yes | Partial | — |
| Braintrust | — | — | — | Yes | — |
| **Saras** | **Yes** | **Yes** | **Yes** | **Yes** | **Yes** |

Saras unifies these with a first-class YAML-based agent builder that abstracts orchestration and context engineering from users.

---

## Lifecycle

![lifecycle](assets/diagrams/lifecycle.svg)

| Phase | What happens |
|-------|-------------|
| **Build** | Define agents in YAML — persona, tools, goals, conditions, handoffs |
| **Simulate** | Run conversations against your agent in a sandboxed WebSocket session |
| **Deploy** | Ship via Docker Compose; route traffic through the executor |
| **Observe** | Ingest spans and traces; explore in the DuckDB-backed trace UI |
| **Evaluate** | Run metric sets and LLM-as-judge against trace data |
| **Improve** | Feed golden datasets back into the builder; close the loop |

---

## Quick Links

- [Why Saras?](why-saras.md) — The design rationale and what makes Saras different
- [Architecture Overview](architecture/overview.md) — System diagram and component map
- [Self-Hosting](self-hosting.md) — Get running in minutes with Docker Compose
- [SDK](sdk.md) — Instrument your own code with `saras-sdk`
