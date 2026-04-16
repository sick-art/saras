# Agent Builder Roadmap

Tracks UX/UI improvements deferred from the [tree-form redesign](#current-state).

## Current State

The form editor is being rewritten as an **outline tree + dynamic form** with full
schema coverage and bidirectional YAML sync. This replaces the previous flat block
list that only covered ~60% of the schema.

## Deferred — Smart YAML Editor

The Monaco-based YAML editor should grow these capabilities so power users can stay in YAML:

- **Slash-command completion** — Typing `/persona-`, `/tool-`, `/goal-`, `/condition-`,
  `/interrupt-`, `/handoff-`, `/tone-` opens a picker of matching playbooks and
  inserts the snippet at the cursor with correct indentation.
- **Cross-reference autocomplete** — Inside a goal's `tools:` block, suggest
  defined tool names from `parsedSchema.tools[*].name`. Same for sub-agent
  names inside `target:`.
- **Hover docs** — Hover on schema field keys (`persona:`, `type:`, `slots:`) to
  see a description from a static map keyed by JSONPath.
- **Validation markers + quick-fixes** — Surface `validationResult` errors as
  Monaco markers at precise YAML lines. Quick-fix providers for common issues
  ("Tool 'XXX' is undefined → Insert tool definition" inserts the tool stub).

Implementation file (planned): `frontend/src/pages/agents/AgentBuilder/yaml-monaco-extras.ts`

## Deferred — Reusable Playbook Library

A library of pre-built YAML snippets that can be browsed and inserted, accelerating
agent authoring.

**Categories:**
- Personas (customer support, sales agent, technical assistant, financial analyst, travel concierge)
- Tones (friendly, formal, empathetic, concise)
- Tools (lookup-user, lookup-order, send-email, create-ticket, knowledge-base-search, refund-action)
- Goals (collect-user-info, verify-identity, recommend-product, troubleshoot-issue, escalate-to-human)
- Conditions (order-inquiry, billing-question, returns-and-refunds, technical-support)
- Interrupts (profanity, fraud-attempt, urgent-safety, abusive-language)
- Handoffs (senior-agent, billing-team, fraud-team, accessibility)

**Storage:** `frontend/src/lib/playbooks/{category}/*.yaml` with frontmatter:
```yaml
# ---
# id: persona-customer-support
# name: Customer Support
# category: persona
# description: Friendly support specialist with policy knowledge
# tags: [support, retail, customer-facing]
# parentPath: persona  # where to insert when "smart insert"
# ---
You are Mara, a friendly customer support specialist…
```

**UI surface:** A `LibraryPanel` side panel in the builder with search,
category accordion, preview drawer, and insert actions (insert at cursor /
smart insert into correct parent).

**Phase 2:** Custom user snippets — let users save their own as snippets to reuse
across agents.

## Deferred — Builder Tabs Simplification

Once the smart editor + library land, collapse the four-tab structure into a
single integrated workspace:

- **Build** (default) — Outline (left) + smart YAML editor (center) + Library (right)
- **Chat** — kept as separate tab (per user preference)
- **YAML** — distraction-free full-screen Monaco

The current Form tab becomes redundant once the outline can drive YAML editing
and the smart editor handles autocomplete inline. The Graph tab should be
removed from the builder entirely; the simulator's `LiveGraph` covers the
visualization use case.
