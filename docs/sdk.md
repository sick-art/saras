# SDK

The `saras-sdk` Python package will let you instrument your own code and ingest spans into Saras alongside agents you build in the platform.

!!! note "Planned — not yet shipped"
    The SDK package is on the roadmap and not part of the current backend. This page documents the intended interface so the API surface is reviewable in advance. Until the SDK lands, use the platform-built executor and the trace API directly.

---

## Intended Interface

### Installation

```bash
pip install saras-sdk
```

### Configuration

```python
import saras

saras.configure(
    api_url="http://localhost:8000",
    api_key="your-api-key",          # value of SARAS_API_KEY in your backend .env
    project_id="my-project",
)
```

Or via environment variables:

```env
SARAS_API_URL=http://localhost:8000
SARAS_API_KEY=your-api-key
SARAS_PROJECT_ID=my-project
```

### Decorators

```python
@saras.trace(name="generate_response")
def generate_response(prompt: str) -> str:
    ...

@saras.tool(name="Order Lookup")
def order_lookup(order_id: str) -> dict:
    ...
```

Each call emits a span carrying inputs, outputs, latency, and any tokens/cost the wrapped code reports.

### Manual spans

```python
with saras.span(name="custom_step", run_id=run_id) as span:
    result = do_something()
    span.set_output(result)
    span.set_metadata({"model": "claude-opus-4-6", "tokens": 342})
```

---

## Until the SDK Lands

If you need to ship spans from outside the platform today, you can:

- Use the platform's WebSocket simulator endpoint as a reference for the span shapes the UI understands. See [backend/saras/api/simulator.py](../backend/saras/api/simulator.py) and [backend/saras/core/executor.py](../backend/saras/core/executor.py).
- Read [backend/saras/db/models.py](../backend/saras/db/models.py) for the `Run` and `Span` schemas and write directly to Postgres via Alembic-managed tables (use the same shape the executor uses).
- Watch the [changelog](changelog.md) for the SDK release.

---

## Related

- [Self-Hosting](self-hosting.md) — get a Saras instance running to ingest into
- [Architecture Overview](architecture/overview.md) — where SDK spans will fit in the system
- [Executor](architecture/executor.md) — the canonical span shapes Saras emits today
