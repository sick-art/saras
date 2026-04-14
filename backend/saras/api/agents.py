from datetime import datetime

import yaml
from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import new as ulid_new

from saras.core.compiler import compile_from_yaml
from saras.core.schema import AgentSchema
from saras.core.validator import validate
from saras.db.models import Agent, AgentVersion
from saras.db.postgres import get_db

router = APIRouter(prefix="/projects/{project_id}/agents", tags=["agents"])


class AgentCreate(BaseModel):
    name: str
    description: str | None = None
    yaml_content: str = ""


class AgentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    yaml_content: str | None = None
    change_summary: str | None = None


class AgentResponse(BaseModel):
    id: str
    project_id: str
    name: str
    description: str | None
    yaml_content: str
    current_version: str
    is_published: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentVersionResponse(BaseModel):
    id: str
    agent_id: str
    version: str
    yaml_content: str
    change_summary: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=list[AgentResponse])
async def list_agents(project_id: str, db: AsyncSession = Depends(get_db)) -> list[Agent]:
    result = await db.execute(
        select(Agent)
        .where(Agent.project_id == project_id)
        .order_by(Agent.updated_at.desc())
    )
    return list(result.scalars().all())


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    project_id: str, body: AgentCreate, db: AsyncSession = Depends(get_db)
) -> Agent:
    agent_id = str(ulid_new())
    agent = Agent(
        id=agent_id,
        project_id=project_id,
        name=body.name,
        description=body.description,
        yaml_content=body.yaml_content,
    )
    db.add(agent)
    # snapshot initial version
    version = AgentVersion(
        id=str(ulid_new()),
        agent_id=agent_id,
        version="1.0.0",
        yaml_content=body.yaml_content,
        change_summary="Initial version",
    )
    db.add(version)
    await db.commit()
    await db.refresh(agent)
    return agent


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(project_id: str, agent_id: str, db: AsyncSession = Depends(get_db)) -> Agent:
    agent = await db.get(Agent, agent_id)
    if not agent or agent.project_id != project_id:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    project_id: str, agent_id: str, body: AgentUpdate, db: AsyncSession = Depends(get_db)
) -> Agent:
    agent = await db.get(Agent, agent_id)
    if not agent or agent.project_id != project_id:
        raise HTTPException(status_code=404, detail="Agent not found")

    if body.name is not None:
        agent.name = body.name
    if body.description is not None:
        agent.description = body.description
    if body.yaml_content is not None:
        agent.yaml_content = body.yaml_content
        # bump patch version and snapshot
        parts = agent.current_version.split(".")
        parts[-1] = str(int(parts[-1]) + 1)
        new_version = ".".join(parts)
        agent.current_version = new_version
        version = AgentVersion(
            id=str(ulid_new()),
            agent_id=agent_id,
            version=new_version,
            yaml_content=body.yaml_content,
            change_summary=body.change_summary,
        )
        db.add(version)

    await db.commit()
    await db.refresh(agent)
    return agent


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(project_id: str, agent_id: str, db: AsyncSession = Depends(get_db)) -> None:
    agent = await db.get(Agent, agent_id)
    if not agent or agent.project_id != project_id:
        raise HTTPException(status_code=404, detail="Agent not found")
    await db.delete(agent)
    await db.commit()


@router.get("/{agent_id}/versions", response_model=list[AgentVersionResponse])
async def list_versions(
    project_id: str, agent_id: str, db: AsyncSession = Depends(get_db)
) -> list[AgentVersion]:
    agent = await db.get(Agent, agent_id)
    if not agent or agent.project_id != project_id:
        raise HTTPException(status_code=404, detail="Agent not found")
    result = await db.execute(
        select(AgentVersion)
        .where(AgentVersion.agent_id == agent_id)
        .order_by(AgentVersion.created_at.desc())
    )
    return list(result.scalars().all())


class ValidateRequest(BaseModel):
    yaml_content: str
    known_agent_names: list[str] = []


class AgentValidateRequest(BaseModel):
    known_agent_names: list[str] = []


@router.post("/{agent_id}/validate")
async def validate_agent(
    project_id: str,
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    body: AgentValidateRequest | None = Body(default=None),
) -> dict:
    """
    Validate the agent's stored YAML and return errors/warnings/info.
    Does NOT save to DB — safe to call on every keypress from the frontend.
    """
    agent = await db.get(Agent, agent_id)
    if not agent or agent.project_id != project_id:
        raise HTTPException(status_code=404, detail="Agent not found")

    known_agent_names = body.known_agent_names if body else []

    try:
        raw = yaml.safe_load(agent.yaml_content)
        if not isinstance(raw, dict) or "agent" not in raw:
            return {
                "valid": False,
                "errors": [{"severity": "error", "code": "invalid_yaml_structure",
                            "message": "YAML must have a top-level 'agent:' key", "path": None}],
                "warnings": [],
                "infos": [],
            }
        schema = AgentSchema.model_validate(raw["agent"])
    except yaml.YAMLError as e:
        return {
            "valid": False,
            "errors": [{"severity": "error", "code": "yaml_parse_error",
                        "message": f"Invalid YAML: {e}", "path": None}],
            "warnings": [],
            "infos": [],
        }
    except ValidationError as e:
        errors = [
            {"severity": "error", "code": "schema_validation_error",
             "message": str(err["msg"]), "path": ".".join(str(p) for p in err["loc"])}
            for err in e.errors()
        ]
        return {"valid": False, "errors": errors, "warnings": [], "infos": []}

    result = validate(schema, known_agent_names=set(known_agent_names))
    return result.to_dict()


@router.post("/validate")
async def validate_yaml(body: ValidateRequest) -> dict:
    """
    Validate a YAML string without needing an existing agent ID.
    Used by the 'New Agent' flow before first save.
    """
    try:
        raw = yaml.safe_load(body.yaml_content)
        if not isinstance(raw, dict) or "agent" not in raw:
            return {
                "valid": False,
                "errors": [{"severity": "error", "code": "invalid_yaml_structure",
                            "message": "YAML must have a top-level 'agent:' key", "path": None}],
                "warnings": [], "infos": [],
            }
        schema = AgentSchema.model_validate(raw["agent"])
    except (yaml.YAMLError, ValidationError) as e:
        return {"valid": False,
                "errors": [{"severity": "error", "code": "parse_error",
                            "message": str(e), "path": None}],
                "warnings": [], "infos": []}

    result = validate(schema, known_agent_names=set(body.known_agent_names))
    return result.to_dict()
