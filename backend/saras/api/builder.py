"""
Conversational Agent Builder — streaming SSE endpoint.

POST /api/projects/{project_id}/agents/{agent_id}/builder/chat

Accepts:
  { "message": string, "yaml_content": string }

Returns a streaming Server-Sent Events response.
Each event is a JSON object. Event types:

  { "type": "delta", "text": "..." }          — streamed text chunk
  { "type": "yaml_diff", "diff": "..." }       — unified diff of YAML change
  { "type": "updated_yaml", "yaml": "..." }    — full updated YAML string
  { "type": "done" }                            — stream complete
  { "type": "error", "message": "..." }         — error (stream ends after this)

The LLM is prompted as a YAML agent editor.
It receives the current YAML and the user's natural language instruction,
and returns structured JSON: { "explanation": "...", "updated_yaml": "..." }.
The diff is computed server-side from original vs updated YAML.
"""

from __future__ import annotations

import difflib
import json
from collections.abc import AsyncGenerator

import structlog
import yaml
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from saras.db.postgres import get_db
from saras.db.models import Agent
from saras.providers.litellm import stream_completion

log = structlog.get_logger()

router = APIRouter(prefix="/projects/{project_id}/agents", tags=["builder"])


# ── Request / Response ─────────────────────────────────────────────────────────

class BuilderChatRequest(BaseModel):
    message: str
    yaml_content: str = ""
    model: str = "gpt-5.4-mini"


# ── LLM prompt ────────────────────────────────────────────────────────────────

_BUILDER_SYSTEM = """\
You are an expert agent YAML editor for the Saras agent platform.

The user gives you a natural language instruction describing a change to make to their agent.
Your job is to apply that change to the current YAML and return the result as JSON.

Saras YAML structure (top-level keys under `agent:`):
  name, version, description, models, persona, tone,
  global_rules (list of strings), interrupt_triggers (list of {name, description, action}),
  out_of_scope (list of strings), handoffs (list of {name, description, target, context_to_pass}),
  tools (list of {name, type, description, endpoint?, inputs?, on_failure?, on_empty_result?}),
  conditions (list of {name, description, goals: [{name, description, tone?, slots?, sequences?, rules?, tools?}]}),
  sub_agents (list of {name, ref?|inline?})

Design rules:
- All condition/trigger/handoff descriptions are plain English — no code or boolean expressions.
- Tool names are human-readable (e.g. "Order Lookup", not "order_lookup").
- Goals reference tool names as plain strings in their 'tools' list.
- Sequences reference tools like: "You MUST invoke @tool: Order Lookup before responding."
- Never add IDs or internal identifiers — users never author those.

Return ONLY this JSON (no markdown fences):
{
  "explanation": "<one or two sentences describing what you changed>",
  "updated_yaml": "<full updated YAML string>"
}

If the YAML is empty or invalid, create a minimal valid agent scaffold from the user's instruction.
If the user's instruction is ambiguous, make a reasonable interpretation and note it in explanation.
"""


# ── SSE helpers ────────────────────────────────────────────────────────────────

def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _unified_diff(original: str, updated: str, filename: str = "agent.yaml") -> str:
    a_lines = original.splitlines(keepends=True)
    b_lines = updated.splitlines(keepends=True)
    diff = difflib.unified_diff(a_lines, b_lines, fromfile=f"a/{filename}", tofile=f"b/{filename}")
    return "".join(diff)


# ── Streaming generator ────────────────────────────────────────────────────────

async def _stream_builder(
    message: str,
    yaml_content: str,
    model: str,
) -> AsyncGenerator[str, None]:
    """
    Drive the builder LLM and stream SSE events to the client.

    Protocol:
    1. Stream text deltas while the model generates the explanation
    2. Once the full response is collected, parse the JSON
    3. Emit yaml_diff + updated_yaml events
    4. Emit done
    """
    messages = [
        {"role": "system", "content": _BUILDER_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Current YAML:\n```yaml\n{yaml_content or '# (empty)'}\n```\n\n"
                f"Instruction: {message}"
            ),
        },
    ]

    full_response = ""
    explanation_done = False

    try:
        async for chunk in stream_completion(model=model, messages=messages, temperature=0.3, max_tokens=4096):
            full_response += chunk

            # Stream the explanation portion as text deltas.
            # We detect when the "explanation" value ends (before "updated_yaml" key).
            if not explanation_done and '"updated_yaml"' not in full_response:
                # Strip partial JSON framing to extract only the explanation text
                cleaned = full_response.lstrip()
                for prefix in ('{"explanation":', '{ "explanation":'):
                    if cleaned.startswith(prefix):
                        cleaned = cleaned[len(prefix):].lstrip().lstrip('"')
                        break
                yield _sse({"type": "delta", "text": chunk})
            elif not explanation_done:
                explanation_done = True
                yield _sse({"type": "delta", "text": ""})  # flush

    except Exception as e:
        log.error("builder.stream_error", error=str(e))
        yield _sse({"type": "error", "message": str(e)})
        return

    # Parse the complete JSON response
    try:
        raw = full_response.strip()
        # Strip markdown fences if model added them despite instructions
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:]).rsplit("```", 1)[0].strip()

        parsed = json.loads(raw)
        updated_yaml: str = parsed.get("updated_yaml", yaml_content)
        explanation: str = parsed.get("explanation", "")

        # Validate the updated YAML is parseable
        try:
            yaml.safe_load(updated_yaml)
        except yaml.YAMLError as ye:
            yield _sse({"type": "error", "message": f"Model returned invalid YAML: {ye}"})
            return

        # Compute diff
        diff = _unified_diff(yaml_content or "", updated_yaml)
        if diff:
            yield _sse({"type": "yaml_diff", "diff": diff})

        yield _sse({"type": "updated_yaml", "yaml": updated_yaml})
        yield _sse({"type": "explanation", "text": explanation})

    except json.JSONDecodeError as e:
        log.warning("builder.json_parse_error", error=str(e), raw=full_response[:500])
        yield _sse({"type": "error", "message": "Model returned an unexpected response. Please try again."})
        return

    yield _sse({"type": "done"})


# ── Endpoint ───────────────────────────────────────────────────────────────────

@router.post("/{agent_id}/builder/chat")
async def builder_chat(
    project_id: str,
    agent_id: str,
    body: BuilderChatRequest,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    Streaming conversational builder endpoint.
    Verifies the agent belongs to the project, then streams SSE events.
    """
    # Verify agent exists and belongs to this project
    agent = await db.get(Agent, agent_id)
    if not agent or agent.project_id != project_id:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Use agent's current YAML if none provided in request
    yaml_content = body.yaml_content or agent.yaml_content or ""

    return StreamingResponse(
        _stream_builder(body.message, yaml_content, body.model),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/builder/chat")
async def builder_chat_no_agent(
    project_id: str,
    body: BuilderChatRequest,
) -> StreamingResponse:
    """
    Streaming builder endpoint for new agents (no agent_id yet).
    Used in the 'New Agent' flow before first save.
    """
    return StreamingResponse(
        _stream_builder(body.message, body.yaml_content, body.model),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
