"""
Traces API — run list, run detail, session list, session detail, analytics.

Endpoints:
    GET  /api/projects/{project_id}/runs
         Query params: agent_id, status, source, session_id, limit, offset,
                       started_after, started_before
         Returns: paginated list of Run summaries

    GET  /api/projects/{project_id}/runs/{run_id}
         Returns: full Run with ordered Span list

    GET  /api/projects/{project_id}/sessions
         Query params: agent_id, limit, offset
         Returns: paginated list of Session summaries (runs grouped by session_id)

    GET  /api/projects/{project_id}/sessions/{session_id}
         Returns: session metadata + all runs with their spans

    GET  /api/projects/{project_id}/analytics
         Query params: agent_id, days (default 30)
         Returns: DuckDB analytics summary (cost, latency, models, errors)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, case, or_
from sqlalchemy.ext.asyncio import AsyncSession

from saras.db.models import Agent, Run, Span
from saras.db.postgres import get_db
from saras.tracing.query import analytics_summary

log = structlog.get_logger()

router = APIRouter(prefix="/projects/{project_id}", tags=["traces"])


# ── Response models ────────────────────────────────────────────────────────────

class SpanOut(BaseModel):
    id: str
    run_id: str
    parent_span_id: str | None
    name: str
    type: str
    started_at: datetime
    ended_at: datetime | None
    duration_ms: int | None
    payload: dict[str, Any] | None

    model_config = {"from_attributes": True}


class RunOut(BaseModel):
    id: str
    agent_id: str | None
    agent_name: str | None = None
    agent_version: str | None
    session_id: str | None
    status: str
    source: str
    started_at: datetime
    ended_at: datetime | None
    total_tokens: int
    total_cost_usd: float
    span_count: int | None = None

    model_config = {"from_attributes": True}


class RunDetailOut(RunOut):
    spans: list[SpanOut] = []


class RunListOut(BaseModel):
    runs: list[RunOut]
    total: int
    limit: int
    offset: int


class SessionSummaryOut(BaseModel):
    session_id: str
    agent_id: str | None
    agent_name: str | None
    agent_version: str | None
    run_count: int
    started_at: datetime
    ended_at: datetime | None
    total_tokens: int
    total_cost_usd: float
    status: str  # running | failed | completed


class SessionListOut(BaseModel):
    sessions: list[SessionSummaryOut]
    total: int
    limit: int
    offset: int


class SessionDetailOut(BaseModel):
    session_id: str
    agent_name: str | None
    agent_version: str | None
    runs: list[RunDetailOut]


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _agent_name_map(agent_ids: list[str], db: AsyncSession) -> dict[str, str]:
    """Batch-load agent names for a set of agent_ids."""
    if not agent_ids:
        return {}
    result = await db.execute(
        select(Agent.id, Agent.name).where(Agent.id.in_(agent_ids))
    )
    return {row.id: row.name for row in result.all()}


# ── Run list ───────────────────────────────────────────────────────────────────

@router.get("/runs", response_model=RunListOut)
async def list_runs(
    project_id: str,
    agent_id: str | None = Query(default=None),
    status: str | None = Query(default=None, description="running|completed|failed"),
    source: str | None = Query(default=None, description="simulator|production|sdk"),
    session_id: str | None = Query(default=None),
    started_after: datetime | None = Query(default=None),
    started_before: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> RunListOut:
    # Build base query scoped to project via agent relationship
    # Runs belong to agents which belong to projects.
    base = (
        select(Run)
        .join(Agent, Run.agent_id == Agent.id, isouter=True)
        .where(
            (Agent.project_id == project_id) | (Run.agent_id.is_(None))
        )
    )

    # Filters
    if agent_id:
        base = base.where(Run.agent_id == agent_id)
    if status:
        base = base.where(Run.status == status)
    if source:
        base = base.where(Run.source == source)
    if session_id:
        base = base.where(Run.session_id == session_id)
    if started_after:
        base = base.where(Run.started_at >= started_after)
    if started_before:
        base = base.where(Run.started_at <= started_before)

    # Total count
    count_q = select(func.count()).select_from(base.subquery())
    total_result = await db.execute(count_q)
    total = total_result.scalar() or 0

    # Paginated rows
    rows_q = base.order_by(Run.started_at.desc()).limit(limit).offset(offset)
    rows_result = await db.execute(rows_q)
    runs: list[Run] = list(rows_result.scalars().all())

    # Batch-load agent names
    agent_ids = [r.agent_id for r in runs if r.agent_id]
    name_map = await _agent_name_map(agent_ids, db)

    # Span counts (batch)
    run_ids = [r.id for r in runs]
    span_count_map: dict[str, int] = {}
    if run_ids:
        sc_result = await db.execute(
            select(Span.run_id, func.count().label("cnt"))
            .where(Span.run_id.in_(run_ids))
            .group_by(Span.run_id)
        )
        span_count_map = {row.run_id: row.cnt for row in sc_result.all()}

    run_outs = [
        RunOut(
            id=r.id,
            agent_id=r.agent_id,
            agent_name=name_map.get(r.agent_id or "", None),
            agent_version=r.agent_version,
            session_id=r.session_id,
            status=r.status,
            source=r.source,
            started_at=r.started_at,
            ended_at=r.ended_at,
            total_tokens=r.total_tokens,
            total_cost_usd=r.total_cost_usd,
            span_count=span_count_map.get(r.id),
        )
        for r in runs
    ]

    return RunListOut(runs=run_outs, total=total, limit=limit, offset=offset)


# ── Run detail (with spans) ────────────────────────────────────────────────────

@router.get("/runs/{run_id}", response_model=RunDetailOut)
async def get_run(
    project_id: str,
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> RunDetailOut:
    # Load run (verify it belongs to this project)
    result = await db.execute(
        select(Run)
        .join(Agent, Run.agent_id == Agent.id, isouter=True)
        .where(Run.id == run_id)
        .where(
            (Agent.project_id == project_id) | (Run.agent_id.is_(None))
        )
    )
    run: Run | None = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    # Load spans ordered by started_at
    spans_result = await db.execute(
        select(Span)
        .where(Span.run_id == run_id)
        .order_by(Span.started_at)
    )
    spans: list[Span] = list(spans_result.scalars().all())

    # Agent name
    agent_name: str | None = None
    if run.agent_id:
        agent = await db.get(Agent, run.agent_id)
        if agent:
            agent_name = agent.name

    return RunDetailOut(
        id=run.id,
        agent_id=run.agent_id,
        agent_name=agent_name,
        agent_version=run.agent_version,
        session_id=run.session_id,
        status=run.status,
        source=run.source,
        started_at=run.started_at,
        ended_at=run.ended_at,
        total_tokens=run.total_tokens,
        total_cost_usd=run.total_cost_usd,
        span_count=len(spans),
        spans=[
            SpanOut(
                id=s.id,
                run_id=s.run_id,
                parent_span_id=s.parent_span_id,
                name=s.name,
                type=s.type,
                started_at=s.started_at,
                ended_at=s.ended_at,
                duration_ms=s.duration_ms,
                payload=s.payload,
            )
            for s in spans
        ],
    )


# ── Sessions ───────────────────────────────────────────────────────────────────

@router.get("/sessions", response_model=SessionListOut)
async def list_sessions(
    project_id: str,
    agent_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> SessionListOut:
    """
    Return sessions (groups of runs sharing a session_id) for the project.
    Only returns runs that have a non-null session_id.
    """
    # Aggregation query — group by (session_id, agent_id, agent_version)
    agg_q = (
        select(
            Run.session_id,
            Run.agent_id,
            Run.agent_version,
            func.count(Run.id).label("run_count"),
            func.min(Run.started_at).label("started_at"),
            func.max(Run.ended_at).label("ended_at"),
            func.sum(Run.total_tokens).label("total_tokens"),
            func.sum(Run.total_cost_usd).label("total_cost_usd"),
            # status priority: running > failed > completed
            case(
                (func.bool_or(Run.status == "running"), "running"),
                (func.bool_or(Run.status == "failed"), "failed"),
                else_="completed",
            ).label("status"),
        )
        .join(Agent, Run.agent_id == Agent.id, isouter=True)
        .where(Run.session_id.is_not(None))
        .where(or_(Agent.project_id == project_id, Run.agent_id.is_(None)))
        .group_by(Run.session_id, Run.agent_id, Run.agent_version)
        .order_by(func.min(Run.started_at).desc())
    )
    if agent_id:
        agg_q = agg_q.where(Run.agent_id == agent_id)

    # Total distinct sessions
    count_q = select(func.count()).select_from(agg_q.subquery())
    total_result = await db.execute(count_q)
    total = total_result.scalar() or 0

    # Paginated rows
    rows_result = await db.execute(agg_q.limit(limit).offset(offset))
    rows = rows_result.all()

    # Batch-load agent names
    agent_ids = list({r.agent_id for r in rows if r.agent_id})
    name_map = await _agent_name_map(agent_ids, db)

    sessions = [
        SessionSummaryOut(
            session_id=r.session_id,
            agent_id=r.agent_id,
            agent_name=name_map.get(r.agent_id or "", None),
            agent_version=r.agent_version,
            run_count=r.run_count,
            started_at=r.started_at,
            ended_at=r.ended_at,
            total_tokens=r.total_tokens or 0,
            total_cost_usd=r.total_cost_usd or 0.0,
            status=r.status,
        )
        for r in rows
    ]

    return SessionListOut(sessions=sessions, total=total, limit=limit, offset=offset)


@router.get("/sessions/{session_id}", response_model=SessionDetailOut)
async def get_session(
    project_id: str,
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> SessionDetailOut:
    """Return all runs (with spans) for a given session."""
    # Load runs for this session, project-scoped, ordered by start time
    runs_result = await db.execute(
        select(Run)
        .join(Agent, Run.agent_id == Agent.id, isouter=True)
        .where(Run.session_id == session_id)
        .where(
            (Agent.project_id == project_id) | (Run.agent_id.is_(None))
        )
        .order_by(Run.started_at)
    )
    runs: list[Run] = list(runs_result.scalars().all())
    if not runs:
        raise HTTPException(status_code=404, detail="Session not found")

    # Agent name (from first run that has an agent_id)
    agent_name: str | None = None
    agent_version: str | None = None
    for r in runs:
        if r.agent_id and agent_name is None:
            agent = await db.get(Agent, r.agent_id)
            if agent:
                agent_name = agent.name
                agent_version = r.agent_version
            break

    # Load spans for all runs in one query
    run_ids = [r.id for r in runs]
    spans_result = await db.execute(
        select(Span)
        .where(Span.run_id.in_(run_ids))
        .order_by(Span.started_at)
    )
    all_spans: list[Span] = list(spans_result.scalars().all())

    # Group spans by run_id
    spans_by_run: dict[str, list[Span]] = {}
    for s in all_spans:
        spans_by_run.setdefault(s.run_id, []).append(s)

    run_outs = [
        RunDetailOut(
            id=r.id,
            agent_id=r.agent_id,
            agent_name=agent_name,
            agent_version=r.agent_version,
            session_id=r.session_id,
            status=r.status,
            source=r.source,
            started_at=r.started_at,
            ended_at=r.ended_at,
            total_tokens=r.total_tokens,
            total_cost_usd=r.total_cost_usd,
            span_count=len(spans_by_run.get(r.id, [])),
            spans=[
                SpanOut(
                    id=s.id,
                    run_id=s.run_id,
                    parent_span_id=s.parent_span_id,
                    name=s.name,
                    type=s.type,
                    started_at=s.started_at,
                    ended_at=s.ended_at,
                    duration_ms=s.duration_ms,
                    payload=s.payload,
                )
                for s in spans_by_run.get(r.id, [])
            ],
        )
        for r in runs
    ]

    return SessionDetailOut(
        session_id=session_id,
        agent_name=agent_name,
        agent_version=agent_version,
        runs=run_outs,
    )


# ── Analytics ──────────────────────────────────────────────────────────────────

@router.get("/analytics")
async def get_analytics(
    project_id: str,
    agent_id: str | None = Query(default=None),
    days: int = Query(default=30, ge=1, le=365),
) -> dict[str, Any]:
    """
    DuckDB-powered analytics summary for the project (or a specific agent).
    Returns cost over time, latency percentiles, model usage, and error rates.
    """
    return analytics_summary(agent_id=agent_id, days=days)
