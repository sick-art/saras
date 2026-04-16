"""
Evals API — eval suite management, run triggering, results, and SSE progress streaming.

Endpoints:
    GET    /api/projects/{project_id}/evals/suites
    POST   /api/projects/{project_id}/evals/suites
    GET    /api/projects/{project_id}/evals/suites/{suite_id}
    PATCH  /api/projects/{project_id}/evals/suites/{suite_id}
    DELETE /api/projects/{project_id}/evals/suites/{suite_id}
    POST   /api/projects/{project_id}/evals/suites/{suite_id}/runs
    GET    /api/projects/{project_id}/evals/runs
    GET    /api/projects/{project_id}/evals/runs/{run_id}
    GET    /api/projects/{project_id}/evals/runs/{run_id}/items
    GET    /api/projects/{project_id}/evals/runs/{run_id}/items/{item_id}
    GET    /api/projects/{project_id}/evals/runs/{run_id}/stream   (SSE)
    GET    /api/projects/{project_id}/evals/presets
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import new as ulid_new

from saras.db.models import Agent, Dataset, DatasetItem, EvalResult, EvalRun, EvalSuite
from saras.db.postgres import get_db
from saras.db.redis import get_redis
from saras.evals.metrics import parse_metric_set
from saras.evals.presets import list_presets
from saras.evals.runner import run_eval

log = structlog.get_logger()

router = APIRouter(prefix="/projects/{project_id}/evals", tags=["evals"])


# ── Response models ────────────────────────────────────────────────────────────

class EvalSuiteOut(BaseModel):
    id: str
    project_id: str
    name: str
    description: str | None
    agent_id: str | None = None
    metric_set_yaml: str
    run_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class EvalRunOut(BaseModel):
    id: str
    suite_id: str
    dataset_id: str
    agent_id: str | None
    agent_version: str | None
    status: str
    started_at: datetime | None
    ended_at: datetime | None
    summary: dict[str, Any] | None
    result_count: int = 0

    model_config = {"from_attributes": True}


class EvalResultOut(BaseModel):
    id: str
    eval_run_id: str
    dataset_item_id: str
    metric_id: str
    score: float | None
    reasoning: str | None
    model_used: str | None
    turn_index: int | None
    scope: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ItemResultsOut(BaseModel):
    """All results for a single dataset item, with its conversation."""
    dataset_item_id: str
    conversation: dict[str, Any] | None    # from first EvalResult.conversation_json
    expected_output: dict[str, Any] | None = None  # golden expected output
    scores: list[EvalResultOut]


# ── Request models ─────────────────────────────────────────────────────────────

class CreateSuiteRequest(BaseModel):
    name: str
    description: str | None = None
    agent_id: str | None = None
    metric_set_yaml: str = "metrics: []"


class UpdateSuiteRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    agent_id: str | None = None
    metric_set_yaml: str | None = None


class TriggerRunRequest(BaseModel):
    dataset_id: str
    agent_id: str | None = None    # agent to evaluate; required unless stored on suite


class QuickEvalRequest(BaseModel):
    dataset_id: str
    agent_id: str
    metrics: list[str] = ["semantic_similarity", "tool_call_accuracy"]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


async def _get_suite_or_404(
    project_id: str, suite_id: str, db: AsyncSession
) -> EvalSuite:
    result = await db.execute(
        select(EvalSuite)
        .where(EvalSuite.id == suite_id)
        .where(EvalSuite.project_id == project_id)
    )
    suite = result.scalar_one_or_none()
    if not suite:
        raise HTTPException(status_code=404, detail="Eval suite not found")
    return suite


def _run_out(run: EvalRun, result_count: int = 0) -> EvalRunOut:
    return EvalRunOut(
        id=run.id,
        suite_id=run.suite_id,
        dataset_id=run.dataset_id,
        agent_id=run.agent_id,
        agent_version=run.agent_version,
        status=run.status,
        started_at=run.started_at,
        ended_at=run.ended_at,
        summary=run.summary,
        result_count=result_count,
    )


# ── Presets endpoint ───────────────────────────────────────────────────────────

@router.get("/presets")
async def get_presets(project_id: str) -> list[dict]:
    """Return available preset metric definitions for the UI picker."""
    return list_presets()


# ── Eval Suite CRUD ────────────────────────────────────────────────────────────

@router.get("/suites", response_model=list[EvalSuiteOut])
async def list_suites(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[EvalSuiteOut]:
    result = await db.execute(
        select(EvalSuite)
        .where(EvalSuite.project_id == project_id)
        .order_by(EvalSuite.created_at.desc())
    )
    suites = list(result.scalars().all())

    # Run counts
    from sqlalchemy import func
    if suites:
        counts_result = await db.execute(
            select(EvalRun.suite_id, func.count().label("cnt"))
            .where(EvalRun.suite_id.in_([s.id for s in suites]))
            .group_by(EvalRun.suite_id)
        )
        count_map = {row.suite_id: row.cnt for row in counts_result.all()}
    else:
        count_map = {}

    return [
        EvalSuiteOut(
            id=s.id,
            project_id=s.project_id,
            name=s.name,
            description=s.description,
            agent_id=None,  # not stored on EvalSuite — derived from most recent run
            metric_set_yaml=s.metric_set_yaml,
            run_count=count_map.get(s.id, 0),
            created_at=s.created_at,
        )
        for s in suites
    ]


@router.post("/suites", response_model=EvalSuiteOut, status_code=201)
async def create_suite(
    project_id: str,
    body: CreateSuiteRequest,
    db: AsyncSession = Depends(get_db),
) -> EvalSuiteOut:
    # Validate metric YAML is parseable
    try:
        parse_metric_set(body.metric_set_yaml)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid metric_set_yaml: {exc}")

    suite = EvalSuite(
        id=str(ulid_new()),
        project_id=project_id,
        name=body.name,
        description=body.description,
        metric_set_yaml=body.metric_set_yaml,
    )
    db.add(suite)
    await db.commit()
    await db.refresh(suite)

    return EvalSuiteOut(
        id=suite.id,
        project_id=suite.project_id,
        name=suite.name,
        description=suite.description,
        metric_set_yaml=suite.metric_set_yaml,
        run_count=0,
        created_at=suite.created_at,
    )


@router.get("/suites/{suite_id}", response_model=EvalSuiteOut)
async def get_suite(
    project_id: str,
    suite_id: str,
    db: AsyncSession = Depends(get_db),
) -> EvalSuiteOut:
    suite = await _get_suite_or_404(project_id, suite_id, db)

    from sqlalchemy import func
    count_result = await db.execute(
        select(func.count()).where(EvalRun.suite_id == suite_id)
    )
    run_count = count_result.scalar() or 0

    return EvalSuiteOut(
        id=suite.id,
        project_id=suite.project_id,
        name=suite.name,
        description=suite.description,
        metric_set_yaml=suite.metric_set_yaml,
        run_count=run_count,
        created_at=suite.created_at,
    )


@router.patch("/suites/{suite_id}", response_model=EvalSuiteOut)
async def update_suite(
    project_id: str,
    suite_id: str,
    body: UpdateSuiteRequest,
    db: AsyncSession = Depends(get_db),
) -> EvalSuiteOut:
    suite = await _get_suite_or_404(project_id, suite_id, db)

    if body.name is not None:
        suite.name = body.name
    if body.description is not None:
        suite.description = body.description
    if body.metric_set_yaml is not None:
        try:
            parse_metric_set(body.metric_set_yaml)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Invalid metric_set_yaml: {exc}")
        suite.metric_set_yaml = body.metric_set_yaml

    await db.commit()
    await db.refresh(suite)

    return EvalSuiteOut(
        id=suite.id,
        project_id=suite.project_id,
        name=suite.name,
        description=suite.description,
        metric_set_yaml=suite.metric_set_yaml,
        run_count=0,
        created_at=suite.created_at,
    )


@router.delete("/suites/{suite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_suite(
    project_id: str,
    suite_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    suite = await _get_suite_or_404(project_id, suite_id, db)
    await db.delete(suite)
    await db.commit()


# ── Trigger eval run ───────────────────────────────────────────────────────────

@router.post("/suites/{suite_id}/runs", response_model=EvalRunOut, status_code=202)
async def trigger_run(
    project_id: str,
    suite_id: str,
    body: TriggerRunRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> EvalRunOut:
    """Trigger a new eval run. Returns immediately; execution happens in background."""
    suite = await _get_suite_or_404(project_id, suite_id, db)

    # Verify dataset belongs to this project
    dataset = await db.get(Dataset, body.dataset_id)
    if not dataset or dataset.project_id != project_id:
        raise HTTPException(status_code=404, detail="Dataset not found")

    agent_id: str | None = body.agent_id
    if agent_id:
        agent = await db.get(Agent, agent_id)
        if not agent or agent.project_id != project_id:
            raise HTTPException(status_code=404, detail="Agent not found")

    # Build the EvalRun record
    agent_version: str | None = None
    if agent_id:
        _agent = await db.get(Agent, agent_id)
        agent_version = _agent.current_version if _agent else None

    eval_run = EvalRun(
        id=str(ulid_new()),
        suite_id=suite_id,
        dataset_id=body.dataset_id,
        agent_id=agent_id,
        agent_version=agent_version,
        status="pending",
    )
    db.add(eval_run)
    await db.commit()
    await db.refresh(eval_run)

    # Schedule background execution
    eval_run_id = eval_run.id
    background_tasks.add_task(_run_eval_background, eval_run_id)

    log.info("eval.run.triggered", eval_run_id=eval_run_id, suite_id=suite_id)
    return _run_out(eval_run)


async def _run_eval_background(eval_run_id: str) -> None:
    """Background task wrapper — creates its own DB session."""
    from saras.db.postgres import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await run_eval(eval_run_id, db)


# ── Quick eval from golden ──────────────────────────────────────────────────────

@router.post("/quick-eval", response_model=EvalRunOut, status_code=202)
async def quick_eval(
    project_id: str,
    body: QuickEvalRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> EvalRunOut:
    """Create a transient suite + run for quick golden evaluation.

    Accepts a dataset (of golden items), an agent, and a list of metric preset
    keys. Creates a temporary EvalSuite, wires up an EvalRun, and executes in
    the background.
    """
    # Verify agent
    agent = await db.get(Agent, body.agent_id)
    if not agent or agent.project_id != project_id:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Verify dataset
    dataset = await db.get(Dataset, body.dataset_id)
    if not dataset or dataset.project_id != project_id:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Build metric YAML from requested keys
    metric_lines = ["metrics:"]
    for key in body.metrics:
        metric_lines.append(f"  - preset: {key}")
    metric_yaml = "\n".join(metric_lines) + "\n"

    # Validate
    try:
        parse_metric_set(metric_yaml)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid metric keys: {exc}")

    # Create transient suite
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    suite = EvalSuite(
        id=str(ulid_new()),
        project_id=project_id,
        name=f"Quick Eval {now_str}",
        description="Auto-generated quick eval from golden dataset",
        metric_set_yaml=metric_yaml,
    )
    db.add(suite)

    # Create run
    eval_run = EvalRun(
        id=str(ulid_new()),
        suite_id=suite.id,
        dataset_id=body.dataset_id,
        agent_id=body.agent_id,
        agent_version=agent.current_version,
        status="pending",
    )
    db.add(eval_run)
    await db.commit()
    await db.refresh(eval_run)

    # Schedule background execution
    background_tasks.add_task(_run_eval_background, eval_run.id)

    log.info("eval.quick.triggered", eval_run_id=eval_run.id, dataset_id=body.dataset_id)
    return _run_out(eval_run)


# ── Run list + detail ──────────────────────────────────────────────────────────

@router.get("/runs", response_model=list[EvalRunOut])
async def list_runs(
    project_id: str,
    suite_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[EvalRunOut]:
    q = (
        select(EvalRun)
        .join(EvalSuite, EvalRun.suite_id == EvalSuite.id)
        .where(EvalSuite.project_id == project_id)
        .order_by(EvalRun.started_at.desc())
    )
    if suite_id:
        q = q.where(EvalRun.suite_id == suite_id)

    result = await db.execute(q)
    runs = list(result.scalars().all())

    # Result counts
    from sqlalchemy import func
    if runs:
        counts_result = await db.execute(
            select(EvalResult.eval_run_id, func.count().label("cnt"))
            .where(EvalResult.eval_run_id.in_([r.id for r in runs]))
            .group_by(EvalResult.eval_run_id)
        )
        count_map = {row.eval_run_id: row.cnt for row in counts_result.all()}
    else:
        count_map = {}

    return [_run_out(r, count_map.get(r.id, 0)) for r in runs]


@router.get("/runs/{run_id}", response_model=EvalRunOut)
async def get_run(
    project_id: str,
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> EvalRunOut:
    result = await db.execute(
        select(EvalRun)
        .join(EvalSuite, EvalRun.suite_id == EvalSuite.id)
        .where(EvalRun.id == run_id)
        .where(EvalSuite.project_id == project_id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Eval run not found")

    from sqlalchemy import func
    count_result = await db.execute(
        select(func.count()).where(EvalResult.eval_run_id == run_id)
    )
    result_count = count_result.scalar() or 0
    return _run_out(run, result_count)


# ── Per-item results ───────────────────────────────────────────────────────────

@router.get("/runs/{run_id}/items", response_model=list[ItemResultsOut])
async def get_run_items(
    project_id: str,
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[ItemResultsOut]:
    """Return all results grouped by dataset item."""
    # Verify run belongs to this project
    result = await db.execute(
        select(EvalRun)
        .join(EvalSuite, EvalRun.suite_id == EvalSuite.id)
        .where(EvalRun.id == run_id)
        .where(EvalSuite.project_id == project_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Eval run not found")

    results_q = await db.execute(
        select(EvalResult)
        .where(EvalResult.eval_run_id == run_id)
        .order_by(EvalResult.dataset_item_id, EvalResult.turn_index.asc().nulls_last())
    )
    all_results = list(results_q.scalars().all())

    # Group by dataset_item_id
    grouped: dict[str, list[EvalResult]] = {}
    for r in all_results:
        grouped.setdefault(r.dataset_item_id, []).append(r)

    items_out: list[ItemResultsOut] = []
    for item_id, item_results in grouped.items():
        conversation = item_results[0].conversation_json if item_results else None
        # Fetch expected_output from the DatasetItem for golden comparison
        ds_item = await db.get(DatasetItem, item_id)
        expected = ds_item.expected_output if ds_item else None
        scores = [
            EvalResultOut(
                id=r.id,
                eval_run_id=r.eval_run_id,
                dataset_item_id=r.dataset_item_id,
                metric_id=r.metric_id,
                score=r.score,
                reasoning=r.reasoning,
                model_used=r.model_used,
                turn_index=r.turn_index,
                scope=r.scope,
                created_at=r.created_at,
            )
            for r in item_results
        ]
        items_out.append(ItemResultsOut(
            dataset_item_id=item_id,
            conversation=conversation,
            expected_output=expected,
            scores=scores,
        ))

    return items_out


@router.get("/runs/{run_id}/items/{item_id}", response_model=ItemResultsOut)
async def get_run_item(
    project_id: str,
    run_id: str,
    item_id: str,
    db: AsyncSession = Depends(get_db),
) -> ItemResultsOut:
    """Return all results for a single dataset item (with conversation)."""
    result = await db.execute(
        select(EvalRun)
        .join(EvalSuite, EvalRun.suite_id == EvalSuite.id)
        .where(EvalRun.id == run_id)
        .where(EvalSuite.project_id == project_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Eval run not found")

    results_q = await db.execute(
        select(EvalResult)
        .where(EvalResult.eval_run_id == run_id)
        .where(EvalResult.dataset_item_id == item_id)
        .order_by(EvalResult.turn_index.asc().nulls_last())
    )
    item_results = list(results_q.scalars().all())
    if not item_results:
        raise HTTPException(status_code=404, detail="No results for this item")

    conversation = item_results[0].conversation_json
    # Fetch expected_output from the DatasetItem for golden comparison
    ds_item = await db.get(DatasetItem, item_id)
    expected = ds_item.expected_output if ds_item else None
    scores = [
        EvalResultOut(
            id=r.id,
            eval_run_id=r.eval_run_id,
            dataset_item_id=r.dataset_item_id,
            metric_id=r.metric_id,
            score=r.score,
            reasoning=r.reasoning,
            model_used=r.model_used,
            turn_index=r.turn_index,
            scope=r.scope,
            created_at=r.created_at,
        )
        for r in item_results
    ]
    return ItemResultsOut(
        dataset_item_id=item_id,
        conversation=conversation,
        expected_output=expected,
        scores=scores,
    )


# ── SSE progress stream ────────────────────────────────────────────────────────

@router.get("/runs/{run_id}/stream")
async def stream_run_progress(
    project_id: str,
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream eval run progress as Server-Sent Events.

    Subscribes to Redis channel `eval:{run_id}` and relays events to the client.
    If the run is already completed, sends the summary and closes immediately.
    """
    # Verify run belongs to project
    result = await db.execute(
        select(EvalRun)
        .join(EvalSuite, EvalRun.suite_id == EvalSuite.id)
        .where(EvalRun.id == run_id)
        .where(EvalSuite.project_id == project_id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Eval run not found")

    # If already done, return summary immediately
    if run.status in ("completed", "failed"):
        async def _immediate() -> AsyncGenerator[str, None]:
            event_type = "complete" if run.status == "completed" else "error"
            yield _sse({"type": event_type, "summary": run.summary or {}})

        return StreamingResponse(
            _immediate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return StreamingResponse(
        _stream_events(run_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _stream_events(run_id: str) -> AsyncGenerator[str, None]:
    """Subscribe to Redis eval channel and yield SSE events until complete."""
    redis = await get_redis()
    channel = f"eval:{run_id}"

    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)

    try:
        # Send heartbeat every 15 s to keep the connection alive
        heartbeat_interval = 15.0
        elapsed = 0.0

        async for message in pubsub.listen():
            if message["type"] != "message":
                continue

            data = json.loads(message["data"])
            yield _sse(data)

            if data.get("type") in ("complete", "error"):
                break

    except asyncio.CancelledError:
        pass
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
