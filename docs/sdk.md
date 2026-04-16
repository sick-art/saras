# SDK

The `saras-sdk` Python package lets you instrument your own code and send spans to Saras from outside the platform — useful when you have existing LLM pipelines or scripts you want to observe and evaluate alongside your Saras-built agents.

!!! note "Coming in Phase 7"
    The SDK is planned for Phase 7 of the Saras roadmap. This page documents the intended interface.

---

## Installation

```bash
pip install saras-sdk
```

---

## Configuration

```python
import saras

saras.configure(
    api_url="http://localhost:8000",   # your Saras backend
    api_key="your-api-key",            # from Settings → API Keys
    project_id="my-project",
)
```

Or via environment variables:

```env
SARAS_API_URL=http://localhost:8000
SARAS_API_KEY=your-api-key
SARAS_PROJECT_ID=my-project
```

---

## Decorators

### `@saras.trace`

Wraps a function as a traced span:

```python
@saras.trace(name="generate_response")
def generate_response(prompt: str) -> str:
    response = openai.chat.completions.create(...)
    return response.choices[0].message.content
```

Every call to `generate_response` will emit a span to Saras with inputs, outputs, and latency.

### `@saras.tool`

Marks a function as a tool call span:

```python
@saras.tool(name="Look Up Order")
def look_up_order(order_id: str) -> dict:
    return db.query("SELECT * FROM orders WHERE id = ?", order_id)
```

---

## Manual Spans

For more control, use the context manager API:

```python
with saras.span(name="custom_step", run_id=run_id) as span:
    result = do_something()
    span.set_output(result)
    span.set_metadata({"model": "claude-opus-4-6", "tokens": 342})
```

---

## HTTP Ingest

If you prefer not to use the Python SDK, you can POST spans directly to the ingest endpoint:

```http
POST /api/ingest/spans
Authorization: Bearer your-api-key
Content-Type: application/json

{
  "run_id": "run_abc123",
  "project_id": "my-project",
  "spans": [
    {
      "span_id": "span_001",
      "name": "generate_response",
      "type": "llm",
      "inputs": {"prompt": "..."},
      "output": "...",
      "latency_ms": 1240,
      "timestamp": "2026-04-14T10:00:00Z"
    }
  ]
}
```

---

## Related

- [Self-Hosting](self-hosting.md) — get a Saras instance running to ingest into
- [Architecture Overview](architecture/overview.md) — where SDK spans fit in the system
