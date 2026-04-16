# Why Saras?

## The Gap

Building production-grade AI agents requires more than just a prompt and an LLM call. You need to:

- **Design** the agent's behavior, tools, and escalation paths
- **Simulate** it before you ship to catch edge cases
- **Deploy** it reliably with proper infrastructure
- **Observe** what's actually happening in production conversations
- **Evaluate** whether it's meeting quality targets
- **Improve** it continuously based on real data

Every existing tool covers at most two of these phases — and none of them talk to each other:

| Tool | Build | Simulate | Observe | Evaluate | Improve |
|------|:-----:|:--------:|:-------:|:--------:|:-------:|
| LangSmith | — | — | Partial | Partial | — |
| Phoenix (Arize) | — | — | Yes | Partial | — |
| Braintrust | — | — | — | Yes | Partial |
| PromptLayer | — | — | Partial | — | — |
| **Saras** | **Yes** | **Yes** | **Yes** | **Yes** | **Yes** |

The result is teams cobbling together 3-4 tools, manually exporting data between them, and losing the feedback loop that makes agents actually get better over time.

---

## The Saras Approach

### 1. YAML as the single source of truth

Agent behavior is defined in a human-readable YAML schema — not in code, not in a proprietary DSL. The same YAML is rendered in four views simultaneously:

- **Chat** — describe changes in natural language, get diffs back
- **Form** — structured field editor for non-technical users
- **Graph** — visual node diagram of goals, conditions, and handoffs
- **Raw YAML** — full control for power users

### 2. Natural language, not code

Conditions, triggers, and sequences are written in plain English. There are no regex patterns, no hidden variables, no underscore IDs. A product manager should be able to read and understand an agent definition.

### 3. Progressive context, not prompt stuffing

Most frameworks dump the entire agent configuration into every LLM call. Saras injects context in [8 progressive layers](concepts/context-layers.md) — only the active goal's sequences and slots are injected when relevant. This cuts token usage and keeps the model focused.

### 4. The feedback loop is built in

Saras captures every span from every conversation. Those spans feed directly into the Eval runner, which surfaces regressions. Eval failures can be promoted to a golden dataset. The golden dataset feeds back into the builder. The loop closes.

---

## What Saras is Not

- **Not a framework** — you don't write Python to define agent behavior
- **Not a hosted service** — Saras is self-hosted via Docker Compose; you own your data
- **Not LLM-specific** — LiteLLM means you can use Claude, GPT-4o, Gemini, or any compatible model
- **Not limited to chatbots** — the agent model supports multi-agent delegation, background tasks, and tool-heavy workflows

---

## Who is it for?

- **AI engineers** building production agents who are tired of re-implementing the same eval and observability plumbing
- **Product teams** who want to own the agent definition without needing to read Python
- **Platform teams** who want a self-hosted, auditable, data-sovereign alternative to hosted SaaS tools
