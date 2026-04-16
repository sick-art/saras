"""
Datasets API — CRUD for datasets and dataset items, plus golden ingestion.

Endpoints:
    GET    /api/projects/{project_id}/datasets
    POST   /api/projects/{project_id}/datasets
    GET    /api/projects/{project_id}/datasets/{dataset_id}
    POST   /api/projects/{project_id}/datasets/{dataset_id}/items
    PATCH  /api/projects/{project_id}/datasets/{dataset_id}/items/{item_id}
    DELETE /api/projects/{project_id}/datasets/{dataset_id}/items/{item_id}

    POST   /api/projects/{project_id}/datasets/{dataset_id}/items/from-simulation
           Body: { "history": [...], "agent_id": "...", "metadata": {...} }
           Reconstructs (user turns, agent responses) as a golden dataset item.

    POST   /api/projects/{project_id}/datasets/{dataset_id}/items/from-session
           Body: { "session_id": "..." }
           Reconstructs a multi-turn conversation from Span records as a golden item.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import new as ulid_new

from saras.db.models import Dataset, DatasetItem, Run, Span
from saras.db.postgres import get_db

log = structlog.get_logger()

router = APIRouter(prefix="/projects/{project_id}", tags=["datasets"])


# ── Response models ────────────────────────────────────────────────────────────

class DatasetItemOut(BaseModel):
    id: str
    dataset_id: str
    input: dict[str, Any]
    expected_output: dict[str, Any] | None
    source: str
    metadata: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DatasetOut(BaseModel):
    id: str
    project_id: str
    name: str
    description: str | None
    item_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class DatasetDetailOut(DatasetOut):
    items: list[DatasetItemOut] = []


# ── Request models ─────────────────────────────────────────────────────────────

class CreateDatasetRequest(BaseModel):
    name: str
    description: str | None = None


class CreateItemRequest(BaseModel):
    input: dict[str, Any]
    expected_output: dict[str, Any] | None = None
    source: str = "human"
    metadata: dict[str, Any] | None = None


class UpdateItemRequest(BaseModel):
    input: dict[str, Any] | None = None
    expected_output: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class FromSimulationRequest(BaseModel):
    """Create a golden item from a live simulator conversation."""
    history: list[dict[str, Any]]   # OpenAI-format messages [{role, content}, ...]
    agent_id: str | None = None
    metadata: dict[str, Any] | None = None
    tool_calls_per_turn: list[dict[str, Any]] | None = None
    # Optional: tool calls made per turn for expected_output.tool_calls.
    # Format: [{"turn": 0, "tool_name": "...", "required_args": [...]}, ...]


class FromSessionRequest(BaseModel):
    """Create a golden item from a historic trace session."""
    session_id: str
    metadata: dict[str, Any] | None = None


# ── Helpers ────────────────────────────────────────────────────────────────────

def _item_out(item: DatasetItem) -> DatasetItemOut:
    return DatasetItemOut(
        id=item.id,
        dataset_id=item.dataset_id,
        input=item.input,
        expected_output=item.expected_output,
        source=item.source,
        metadata=item.metadata_,
        created_at=item.created_at,
    )


async def _get_dataset_or_404(
    project_id: str, dataset_id: str, db: AsyncSession
) -> Dataset:
    result = await db.execute(
        select(Dataset)
        .where(Dataset.id == dataset_id)
        .where(Dataset.project_id == project_id)
    )
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return dataset


def _reconstruct_from_history(
    history: list[dict[str, Any]],
) -> tuple[list[str], list[str]]:
    """Extract (user_turns, agent_turns) from OpenAI-format history."""
    user_turns: list[str] = []
    agent_turns: list[str] = []
    for msg in history:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                c.get("text", "") for c in content if isinstance(c, dict)
            )
        if role == "user":
            user_turns.append(str(content))
        elif role == "assistant":
            agent_turns.append(str(content))
    return user_turns, agent_turns


# ── Dataset CRUD ───────────────────────────────────────────────────────────────

@router.get("/datasets", response_model=list[DatasetOut])
async def list_datasets(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[DatasetOut]:
    result = await db.execute(
        select(Dataset).where(Dataset.project_id == project_id).order_by(Dataset.created_at.desc())
    )
    datasets = list(result.scalars().all())

    # Count items per dataset
    from sqlalchemy import func
    counts_result = await db.execute(
        select(DatasetItem.dataset_id, func.count().label("cnt"))
        .where(DatasetItem.dataset_id.in_([d.id for d in datasets]))
        .group_by(DatasetItem.dataset_id)
    )
    count_map = {row.dataset_id: row.cnt for row in counts_result.all()}

    return [
        DatasetOut(
            id=d.id,
            project_id=d.project_id,
            name=d.name,
            description=d.description,
            item_count=count_map.get(d.id, 0),
            created_at=d.created_at,
        )
        for d in datasets
    ]


@router.post("/datasets", response_model=DatasetOut, status_code=201)
async def create_dataset(
    project_id: str,
    body: CreateDatasetRequest,
    db: AsyncSession = Depends(get_db),
) -> DatasetOut:
    dataset = Dataset(
        id=str(ulid_new()),
        project_id=project_id,
        name=body.name,
        description=body.description,
    )
    db.add(dataset)
    await db.commit()
    await db.refresh(dataset)
    return DatasetOut(
        id=dataset.id,
        project_id=dataset.project_id,
        name=dataset.name,
        description=dataset.description,
        item_count=0,
        created_at=dataset.created_at,
    )


@router.get("/datasets/{dataset_id}", response_model=DatasetDetailOut)
async def get_dataset(
    project_id: str,
    dataset_id: str,
    db: AsyncSession = Depends(get_db),
) -> DatasetDetailOut:
    dataset = await _get_dataset_or_404(project_id, dataset_id, db)

    items_result = await db.execute(
        select(DatasetItem)
        .where(DatasetItem.dataset_id == dataset_id)
        .order_by(DatasetItem.created_at.asc())
    )
    items = list(items_result.scalars().all())

    return DatasetDetailOut(
        id=dataset.id,
        project_id=dataset.project_id,
        name=dataset.name,
        description=dataset.description,
        item_count=len(items),
        created_at=dataset.created_at,
        items=[_item_out(i) for i in items],
    )


# ── Item CRUD ──────────────────────────────────────────────────────────────────

@router.post("/datasets/{dataset_id}/items", response_model=DatasetItemOut, status_code=201)
async def create_item(
    project_id: str,
    dataset_id: str,
    body: CreateItemRequest,
    db: AsyncSession = Depends(get_db),
) -> DatasetItemOut:
    await _get_dataset_or_404(project_id, dataset_id, db)
    item = DatasetItem(
        id=str(ulid_new()),
        dataset_id=dataset_id,
        input=body.input,
        expected_output=body.expected_output,
        source=body.source,
        metadata_=body.metadata,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _item_out(item)


@router.patch("/datasets/{dataset_id}/items/{item_id}", response_model=DatasetItemOut)
async def update_item(
    project_id: str,
    dataset_id: str,
    item_id: str,
    body: UpdateItemRequest,
    db: AsyncSession = Depends(get_db),
) -> DatasetItemOut:
    await _get_dataset_or_404(project_id, dataset_id, db)
    item = await db.get(DatasetItem, item_id)
    if not item or item.dataset_id != dataset_id:
        raise HTTPException(status_code=404, detail="Dataset item not found")

    if body.input is not None:
        item.input = body.input
    if body.expected_output is not None:
        item.expected_output = body.expected_output
    if body.metadata is not None:
        item.metadata_ = body.metadata

    await db.commit()
    await db.refresh(item)
    return _item_out(item)


@router.delete("/datasets/{dataset_id}/items/{item_id}", status_code=204)
async def delete_item(
    project_id: str,
    dataset_id: str,
    item_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    await _get_dataset_or_404(project_id, dataset_id, db)
    item = await db.get(DatasetItem, item_id)
    if not item or item.dataset_id != dataset_id:
        raise HTTPException(status_code=404, detail="Dataset item not found")
    await db.delete(item)
    await db.commit()


# ── Golden ingestion ───────────────────────────────────────────────────────────

@router.post(
    "/datasets/{dataset_id}/items/from-simulation",
    response_model=DatasetItemOut,
    status_code=201,
)
async def create_item_from_simulation(
    project_id: str,
    dataset_id: str,
    body: FromSimulationRequest,
    db: AsyncSession = Depends(get_db),
) -> DatasetItemOut:
    """Create a golden dataset item from a live simulator conversation history.

    Extracts user turns as `input.turns` and agent responses as
    `expected_output.turns` so the item can be used for regression testing.
    """
    await _get_dataset_or_404(project_id, dataset_id, db)

    user_turns, agent_turns = _reconstruct_from_history(body.history)
    if not user_turns:
        raise HTTPException(status_code=422, detail="history contains no user messages")

    metadata = body.metadata or {}
    if body.agent_id:
        metadata["agent_id"] = body.agent_id
    metadata["source_type"] = "simulation"

    item = DatasetItem(
        id=str(ulid_new()),
        dataset_id=dataset_id,
        input={"turns": user_turns},
        expected_output={
            "turns": agent_turns,
            **({"tool_calls": body.tool_calls_per_turn} if body.tool_calls_per_turn else {}),
        },
        source="auto",
        metadata_=metadata,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    log.info(
        "dataset.item.from_simulation",
        item_id=item.id,
        turns=len(user_turns),
        agent_id=body.agent_id,
    )
    return _item_out(item)


@router.post(
    "/datasets/{dataset_id}/items/from-session",
    response_model=DatasetItemOut,
    status_code=201,
)
async def create_item_from_session(
    project_id: str,
    dataset_id: str,
    body: FromSessionRequest,
    db: AsyncSession = Depends(get_db),
) -> DatasetItemOut:
    """Create a golden dataset item from a historic trace session.

    Reconstructs the conversation from Run + Span records in Postgres.
    User messages come from 'user_message' spans; agent responses from
    'agent_response' or 'llm_call_end' spans.
    """
    from saras.db.models import Agent

    await _get_dataset_or_404(project_id, dataset_id, db)

    # Load all runs in the session
    runs_result = await db.execute(
        select(Run)
        .join(Agent, Run.agent_id == Agent.id, isouter=True)
        .where(Run.session_id == body.session_id)
        .where(
            (Agent.project_id == project_id) | (Run.agent_id.is_(None))
        )
        .order_by(Run.started_at)
    )
    runs = list(runs_result.scalars().all())
    if not runs:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{body.session_id}' not found in this project",
        )

    # Load all spans for these runs
    run_ids = [r.id for r in runs]
    spans_result = await db.execute(
        select(Span)
        .where(Span.run_id.in_(run_ids))
        .order_by(Span.started_at)
    )
    all_spans = list(spans_result.scalars().all())

    # Reconstruct conversation from spans
    # Each run = one user turn; extract user_message and agent final response
    user_turns: list[str] = []
    agent_turns: list[str] = []

    spans_by_run: dict[str, list[Span]] = {}
    for s in all_spans:
        spans_by_run.setdefault(s.run_id, []).append(s)

    for run in runs:
        run_spans = spans_by_run.get(run.id, [])

        # User message: look in run metadata or first span
        user_msg: str | None = None
        agent_response: str | None = None

        for span in run_spans:
            payload = span.payload or {}
            if span.type in ("user_message",) and not user_msg:
                user_msg = payload.get("content") or payload.get("message")
            if span.type in ("llm_call_end", "agent_response") and not agent_response:
                agent_response = payload.get("content") or payload.get("response")
            if span.type == "router_decision" and not user_msg:
                # Router span sometimes carries the user message
                user_msg = payload.get("user_message")

        # Fallback: check run metadata
        if not user_msg and run.metadata_:
            user_msg = run.metadata_.get("user_message")

        if user_msg:
            user_turns.append(user_msg)
        if agent_response:
            agent_turns.append(agent_response)

    if not user_turns:
        raise HTTPException(
            status_code=422,
            detail="Could not reconstruct user messages from session spans. "
            "Ensure the session has completed runs with span payloads.",
        )

    agent_id = runs[0].agent_id if runs else None
    metadata = body.metadata or {}
    metadata["session_id"] = body.session_id
    metadata["source_type"] = "session"
    if agent_id:
        metadata["agent_id"] = agent_id

    item = DatasetItem(
        id=str(ulid_new()),
        dataset_id=dataset_id,
        input={"turns": user_turns},
        expected_output={"turns": agent_turns} if agent_turns else None,
        source="auto",
        metadata_=metadata,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    log.info(
        "dataset.item.from_session",
        item_id=item.id,
        session_id=body.session_id,
        turns=len(user_turns),
    )
    return _item_out(item)
