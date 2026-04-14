"""
Sample agent templates API.

GET  /api/samples                   — list all available sample agents (metadata only)
GET  /api/samples/{slug}            — return full YAML content for a sample
POST /api/projects/{id}/agents/clone-sample  — create a new agent from a sample YAML
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import new as ulid_new

from saras.db.models import Agent, AgentVersion
from saras.db.postgres import get_db

router = APIRouter(tags=["samples"])

# ── Asset resolution ───────────────────────────────────────────────────────────

ASSETS_DIR = Path(__file__).parent.parent / "assets"


def _load_yaml_file(slug: str) -> str:
    """Load a sample YAML file from the assets directory."""
    path = ASSETS_DIR / f"{slug}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Sample '{slug}' not found")
    return path.read_text(encoding="utf-8")


# ── Sample registry ────────────────────────────────────────────────────────────
# Each entry defines the metadata shown in the UI.

SAMPLES: list[dict] = [
    {
        "slug": "sample_customer_support",
        "name": "E-commerce Customer Support",
        "description": (
            "A full-featured support agent for an online retailer. "
            "Handles order tracking, returns, refunds, billing disputes, "
            "and product questions — with slots, sequences, tools, and "
            "human escalation handoffs."
        ),
        "tags": ["e-commerce", "customer support", "tools", "handoffs"],
        "complexity": "full",   # starter | intermediate | full
    },
]

_SLUG_INDEX = {s["slug"]: s for s in SAMPLES}


# ── Response models ────────────────────────────────────────────────────────────

class SampleMeta(BaseModel):
    slug: str
    name: str
    description: str
    tags: list[str]
    complexity: str


class SampleDetail(SampleMeta):
    yaml_content: str


class CloneSampleRequest(BaseModel):
    slug: str
    name: str | None = None  # override the agent name; defaults to sample name


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/samples", response_model=list[SampleMeta])
async def list_samples() -> list[dict]:
    """Return metadata for all available sample agents."""
    return SAMPLES


@router.get("/samples/{slug}", response_model=SampleDetail)
async def get_sample(slug: str) -> dict:
    """Return full YAML content for a single sample agent."""
    meta = _SLUG_INDEX.get(slug)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Sample '{slug}' not found")
    yaml_content = _load_yaml_file(slug)
    return {**meta, "yaml_content": yaml_content}


@router.post(
    "/projects/{project_id}/agents/clone-sample",
    status_code=status.HTTP_201_CREATED,
)
async def clone_sample(
    project_id: str,
    body: CloneSampleRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Create a new agent in the given project by cloning a sample YAML.
    Returns the new agent record (same shape as AgentResponse).
    """
    meta = _SLUG_INDEX.get(body.slug)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Sample '{body.slug}' not found")

    yaml_content = _load_yaml_file(body.slug)

    # Optionally patch the agent name inside the YAML
    agent_name = body.name or meta["name"]
    try:
        raw = yaml.safe_load(yaml_content)
        if isinstance(raw, dict) and "agent" in raw:
            raw["agent"]["name"] = agent_name
            yaml_content = yaml.dump(raw, allow_unicode=True, sort_keys=False, width=100)
    except Exception:
        pass  # keep original YAML if patching fails

    agent_id = str(ulid_new())
    agent = Agent(
        id=agent_id,
        project_id=project_id,
        name=agent_name,
        description=meta["description"],
        yaml_content=yaml_content,
        current_version="1.0.0",
    )
    db.add(agent)

    version = AgentVersion(
        id=str(ulid_new()),
        agent_id=agent_id,
        version="1.0.0",
        yaml_content=yaml_content,
        change_summary=f"Cloned from sample: {meta['name']}",
    )
    db.add(version)
    await db.commit()
    await db.refresh(agent)

    return {
        "id": agent.id,
        "project_id": agent.project_id,
        "name": agent.name,
        "description": agent.description,
        "yaml_content": agent.yaml_content,
        "current_version": agent.current_version,
        "is_published": agent.is_published,
        "created_at": agent.created_at.isoformat(),
        "updated_at": agent.updated_at.isoformat(),
    }
