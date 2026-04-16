# Architecture Overview

Saras is a monorepo consisting of three main packages: `frontend/`, `backend/`, and `sdk/`. They communicate over HTTP/WebSocket and share a trio of data stores.

---

## System Diagram

![overview-system](../assets/diagrams/overview-system.svg)

---

## Component Responsibilities

| Component | Package | Responsibility |
|-----------|---------|----------------|
| **React Frontend** | `frontend/` | Chat Builder, YAML Editor, Form Builder, Graph View, Simulator pane |
| **Builder API** | `backend/saras/api/builder.py` | Streaming SSE endpoint; accepts user prompt, emits unified YAML diffs |
| **Simulator API** | `backend/saras/api/simulator.py` | WebSocket session; Redis pub/sub fan-out for real-time span events |
| **YAML Compiler** | `backend/saras/core/compiler.py` | Parses agent YAML → `CompiledAgent`; builds system prompt + tool definitions |
| **Validator** | `backend/saras/core/validator.py` | Runs 5 ERROR / 5 WARNING / 2 INFO rules before any execution |
| **Executor** | `backend/saras/core/executor.py` | Assembles context layers, runs tool loop, persists Run/Span to Postgres |
| **Router** | `backend/saras/core/executor.py` | `RouterDecision`, slot fill, goal selection |
| **LiteLLM Adapter** | `backend/saras/providers/litellm.py` | Unified chat/stream completion; provider key routing; tenacity retries |
| **PostgreSQL** | Docker Compose | Primary store — Projects, Agents, AgentVersions, Runs, Spans, Datasets |
| **Redis** | Docker Compose | Real-time span event pub/sub; simulator session history |
| **DuckDB** | Embedded | Embedded analytics on top of Postgres data; powers trace explorer queries |
| **saras-sdk** | `sdk/` | `pip install saras-sdk`; decorators + HTTP ingest for external code |

---

## Request Flow — Chat Builder

![overview-request-flow](../assets/diagrams/overview-request-flow.svg)

---

## Data Model (simplified)

![overview-data-model](../assets/diagrams/overview-data-model.svg)

---

## Next Steps

- [Agent Schema](agent-schema.md) — deep-dive into the YAML format
- [Compiler](compiler.md) — how YAML becomes a runnable agent
- [Executor](executor.md) — the tool loop and span lifecycle
