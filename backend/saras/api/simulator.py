"""
WebSocket Simulation Endpoint.

WS /api/projects/{project_id}/agents/{agent_id}/simulate

Client → Server messages:
  { "type": "user_message", "content": "..." }
  { "type": "reset" }             — clear conversation history
  { "type": "end_simulation" }    — cancel any in-flight turn and close session
  { "type": "end_session" }       — graceful close (kept for compat)

Server → Client messages:
  { "type": "span", "span_type": "...", "data": {...} }
  { "type": "agent_message", "content": "...", "turn_type": "response|slot_fill|interrupt|handoff" }
  { "type": "turn_start" }
  { "type": "turn_end", "tokens": { ... }, "cost_usd": 0.0 }
  { "type": "turn_cancelled" }    — emitted when end_simulation cancels a running turn
  { "type": "simulation_ended" }  — ack for end_simulation
  { "type": "error", "message": "..." }

Architecture:
- Each WebSocket connection gets a unique session_id and a Redis pub/sub channel.
- executor.run_turn() is called per user message and emits span events to Redis.
- A background Redis subscriber task relays those events to the WebSocket client.
- This decouples the executor (which may run async/in a task queue) from the WS connection.
"""

from __future__ import annotations

import asyncio
import json

import structlog
import yaml
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import new as ulid_new

from saras.core.compiler import compile_from_yaml
from saras.core.executor import run_turn
from saras.db.models import Agent
from saras.db.postgres import get_db
from saras.db.redis import get_redis
from saras.tracing.collector import sync_completed_run

log = structlog.get_logger()

router = APIRouter(prefix="/projects/{project_id}/agents", tags=["simulator"])


# ── WebSocket handler ──────────────────────────────────────────────────────────

@router.websocket("/{agent_id}/simulate")
async def simulate(
    websocket: WebSocket,
    project_id: str,
    agent_id: str,
    mode: str = Query(default="standard"),  # "standard" | "good" | "bad"
) -> None:
    """
    WebSocket simulation endpoint.

    Lifecycle:
    1. Accept connection, load + compile agent from DB.
    2. Subscribe to a session-scoped Redis channel for span fan-out.
    3. Loop: receive user messages → run_turn() → stream spans + final response.
    """
    await websocket.accept()

    # ── Load agent from DB ─────────────────────────────────────────────────────
    # We use a fresh session per connection (not dependency injection, since WS
    # doesn't have the request/response lifecycle that Depends() expects).
    from saras.db.postgres import AsyncSessionLocal  # local import to avoid circular

    session: AsyncSession = AsyncSessionLocal()
    try:
        agent: Agent | None = await session.get(Agent, agent_id)
        if not agent or agent.project_id != project_id:
            await websocket.send_json({"type": "error", "message": "Agent not found"})
            await websocket.close(code=4004)
            return

        if not agent.yaml_content:
            await websocket.send_json({"type": "error", "message": "Agent has no YAML content"})
            await websocket.close(code=4400)
            return

        # Compile agent
        try:
            compiled = compile_from_yaml(
                agent.yaml_content,
                agent_id=agent.id,
                agent_version=agent.current_version,
            )
        except (ValueError, ValidationError) as e:
            await websocket.send_json({"type": "error", "message": f"Agent compilation failed: {e}"})
            await websocket.close(code=4400)
            return

        # ── Session setup ──────────────────────────────────────────────────────
        session_id = str(ulid_new())
        redis_channel = f"sim:{session_id}"
        conversation_history: list[dict] = []
        slot_state: dict[str, str] = {}             # Accumulated slot values across turns
        last_active_condition: str | None = None    # Track condition changes to reset slot state

        await websocket.send_json({
            "type": "connected",
            "session_id": session_id,
            "agent_name": agent.name,
            "agent_version": agent.current_version,
            "sim_mode": mode,
        })

        # ── Redis pub/sub fan-out task ─────────────────────────────────────────
        redis = get_redis()
        pubsub = redis.pubsub()
        await pubsub.subscribe(redis_channel)

        async def _redis_relay() -> None:
            """Background task: forward Redis span events to WebSocket."""
            try:
                async for raw_msg in pubsub.listen():
                    if raw_msg["type"] != "message":
                        continue
                    try:
                        event = json.loads(raw_msg["data"])
                        await websocket.send_json(event)
                    except Exception:
                        pass
            except asyncio.CancelledError:
                pass

        relay_task = asyncio.create_task(_redis_relay())

        # ── Main message loop ──────────────────────────────────────────────────
        current_turn_task: asyncio.Task | None = None
        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                    continue

                msg_type = msg.get("type")

                if msg_type == "end_session":
                    await websocket.send_json({"type": "session_ended"})
                    await websocket.close()
                    break

                if msg_type == "end_simulation":
                    # Cancel any in-flight turn task immediately
                    if current_turn_task and not current_turn_task.done():
                        current_turn_task.cancel()
                        try:
                            await current_turn_task
                        except (asyncio.CancelledError, Exception):
                            pass
                    current_turn_task = None
                    await websocket.send_json({"type": "simulation_ended"})
                    await websocket.close()
                    break

                if msg_type == "reset":
                    conversation_history = []
                    slot_state = {}
                    last_active_condition = None
                    await websocket.send_json({"type": "reset_ack"})
                    continue

                if msg_type != "user_message":
                    await websocket.send_json({"type": "error", "message": f"Unknown message type: {msg_type}"})
                    continue

                user_content = msg.get("content", "").strip()
                if not user_content:
                    continue

                await websocket.send_json({"type": "turn_start"})

                # Append user message to history
                conversation_history.append({"role": "user", "content": user_content})

                # Run turn as a tracked task so it can be cancelled by end_simulation
                current_turn_task = asyncio.create_task(run_turn(
                    compiled=compiled,
                    history=conversation_history[:-1],  # history before this message
                    user_message=user_content,
                    slot_state=slot_state,
                    session_id=session_id,
                    redis_channel=redis_channel,
                    db=session,
                    sim_mode=mode,
                ))
                try:
                    result = await current_turn_task
                except asyncio.CancelledError:
                    log.info("simulator.turn_cancelled", session_id=session_id)
                    await websocket.send_json({"type": "turn_cancelled"})
                    current_turn_task = None
                    continue
                except Exception as e:
                    log.error("simulator.run_turn_error", error=str(e))
                    await websocket.send_json({"type": "error", "message": f"Execution error: {e}"})
                    current_turn_task = None
                    continue
                current_turn_task = None

                # Update accumulated slot state from this turn's result
                new_condition = result.router_decision.active_condition if result.router_decision else None
                if new_condition != last_active_condition:
                    # Condition changed — clear slot state for new flow
                    slot_state = {}
                    last_active_condition = new_condition
                slot_state.update(result.slot_state)

                # Append assistant response to history
                conversation_history.append({"role": "assistant", "content": result.content})

                # Emit final agent message
                await websocket.send_json({
                    "type": "agent_message",
                    "content": result.content,
                    "turn_type": result.type,
                    "router_decision": result.router_decision.model_dump() if result.router_decision else None,
                })

                await websocket.send_json({
                    "type": "turn_end",
                    "tokens": {
                        "input": result.total_input_tokens,
                        "output": result.total_output_tokens,
                    },
                    "cost_usd": result.estimated_cost_usd,
                    "run_id": result.run_id,
                })

                # Sync completed run to DuckDB for analytics
                if result.run_id:
                    await sync_completed_run(result.run_id, session)

        except WebSocketDisconnect:
            log.info("simulator.disconnected", session_id=session_id)

        finally:
            # Cancel any in-flight turn (e.g. client disconnected mid-turn)
            if current_turn_task and not current_turn_task.done():
                current_turn_task.cancel()
                try:
                    await current_turn_task
                except (asyncio.CancelledError, Exception):
                    pass
            relay_task.cancel()
            try:
                await pubsub.unsubscribe(redis_channel)
                await pubsub.aclose()
            except Exception:
                pass

    finally:
        await session.close()
