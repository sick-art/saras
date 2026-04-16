"""
WebSocket Simulation Endpoint.

WS /api/projects/{project_id}/agents/{agent_id}/simulate

Client → Server messages:
  { "type": "user_message", "content": "..." }
  { "type": "reset" }             — clear conversation history
  { "type": "end_session" }       — cancel any in-flight turn and close the WS

Server → Client messages:
  { "type": "span", "span_type": "...", "data": {...} }
  { "type": "agent_message", "content": "...", "turn_type": "response|slot_fill|interrupt|handoff" }
  { "type": "turn_start" }
  { "type": "turn_end", "tokens": { ... }, "cost_usd": 0.0 }
  { "type": "turn_cancelled" }    — emitted when a running turn was cancelled
  { "type": "session_ended" }     — ack for end_session
  { "type": "error", "message": "..." }

Architecture:
- Each WebSocket connection gets a unique session_id and a Redis pub/sub channel.
- executor.run_turn() is called per user message and emits span events to Redis.
- A background Redis subscriber task relays those events to the WebSocket client.
- This decouples the executor (which may run async/in a task queue) from the WS connection.
- Each turn's Run row is pre-allocated in this layer so we can always sync its
  terminal state (completed / failed / cancelled) to DuckDB even when the turn
  is cancelled mid-flight. If we relied on run_turn to create the Run row we'd
  lose the run_id on cancellation paths.
"""

from __future__ import annotations

import asyncio
import json

import structlog
import yaml
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import new as ulid_new

from datetime import UTC, datetime

from saras.core.compiler import compile_from_yaml
from saras.core.executor import run_turn
from saras.db.models import Agent, Run
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
        current_turn_run_id: str | None = None

        async def _cancel_current_turn() -> None:
            """Cancel the running turn task and wait for run_turn's handler to
            finalise the Run row. Always sync to DuckDB afterwards so a cancel
            leaves the trace in a consistent terminal state."""
            nonlocal current_turn_task, current_turn_run_id
            if current_turn_task and not current_turn_task.done():
                current_turn_task.cancel()
                try:
                    await current_turn_task
                except (asyncio.CancelledError, Exception):
                    pass
            if current_turn_run_id:
                try:
                    await sync_completed_run(current_turn_run_id, session)
                except Exception as exc:
                    log.warning("simulator.sync_after_cancel_error", error=str(exc))
            current_turn_task = None
            current_turn_run_id = None

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
                    # Cancel any in-flight turn, sync its terminal state, then close.
                    await _cancel_current_turn()
                    await websocket.send_json({"type": "session_ended"})
                    await websocket.close()
                    break

                if msg_type == "reset":
                    conversation_history = []
                    slot_state = {}
                    last_active_condition = None
                    await websocket.send_json({"type": "reset_ack"})
                    continue

                if msg_type != "user_message":
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Unknown message type: {msg_type}",
                    })
                    continue

                user_content = msg.get("content", "").strip()
                if not user_content:
                    continue

                await websocket.send_json({"type": "turn_start"})

                # Append user message to history
                conversation_history.append({"role": "user", "content": user_content})

                # Pre-allocate the Run row so that its id survives cancellation or
                # unexpected errors — we need it to finalise DuckDB sync on every
                # terminal path, not just success.
                current_turn_run_id = str(ulid_new())
                session.add(Run(
                    id=current_turn_run_id,
                    agent_id=compiled.agent_id or None,
                    agent_version=compiled.agent_version,
                    session_id=session_id,
                    source="simulator",
                    status="running",
                ))
                await session.flush()

                current_turn_task = asyncio.create_task(run_turn(
                    compiled=compiled,
                    history=conversation_history[:-1],  # history before this message
                    user_message=user_content,
                    slot_state=slot_state,
                    run_id=current_turn_run_id,
                    session_id=session_id,
                    redis_channel=redis_channel,
                    db=session,
                ))

                terminated_run_id = current_turn_run_id
                try:
                    result = await current_turn_task
                except asyncio.CancelledError:
                    log.info("simulator.turn_cancelled", session_id=session_id)
                    await websocket.send_json({"type": "turn_cancelled"})
                    # run_turn already marked the Run 'cancelled'; sync to DuckDB.
                    if terminated_run_id:
                        try:
                            await sync_completed_run(terminated_run_id, session)
                        except Exception as exc:
                            log.warning("simulator.sync_after_cancel_error", error=str(exc))
                    current_turn_task = None
                    current_turn_run_id = None
                    continue
                except Exception as e:
                    log.error("simulator.run_turn_error", error=str(e))
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Execution error: {e}",
                    })
                    # Best-effort: ensure the Run row reflects failure even if the
                    # executor's own handler didn't commit (e.g. if the session
                    # itself errored).
                    if terminated_run_id:
                        try:
                            run_obj = await session.get(Run, terminated_run_id)
                            if run_obj and run_obj.status == "running":
                                run_obj.status = "failed"
                                run_obj.ended_at = datetime.now(UTC)
                                await session.commit()
                            await sync_completed_run(terminated_run_id, session)
                        except Exception as sync_err:
                            log.warning("simulator.sync_after_error_error", error=str(sync_err))
                    current_turn_task = None
                    current_turn_run_id = None
                    continue

                current_turn_task = None
                current_turn_run_id = None

                # Update accumulated slot state from this turn's result
                new_condition = result.router_decision.active_condition if result.router_decision else None
                if new_condition != last_active_condition:
                    slot_state = {}
                    last_active_condition = new_condition
                slot_state.update(result.slot_state)

                conversation_history.append({"role": "assistant", "content": result.content})

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

                if result.run_id:
                    await sync_completed_run(result.run_id, session)

        except WebSocketDisconnect:
            log.info("simulator.disconnected", session_id=session_id)

        finally:
            # Client closed mid-turn (tab close, network drop, etc.) — cancel
            # the in-flight task so run_turn can mark its Run 'cancelled', then
            # sync that terminal state to DuckDB.
            await _cancel_current_turn()
            relay_task.cancel()
            try:
                await pubsub.unsubscribe(redis_channel)
                await pubsub.aclose()
            except Exception:
                pass

    finally:
        await session.close()
