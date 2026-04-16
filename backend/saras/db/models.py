"""SQLAlchemy ORM models for all primary entities."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from saras.db.postgres import Base


# ── Projects ──────────────────────────────────────────────────────────────────

class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    agents: Mapped[list["Agent"]] = relationship(back_populates="project")
    datasets: Mapped[list["Dataset"]] = relationship(back_populates="project")
    eval_suites: Mapped[list["EvalSuite"]] = relationship(back_populates="project")


# ── Agents ────────────────────────────────────────────────────────────────────

class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    yaml_content: Mapped[str] = mapped_column(Text, nullable=False)
    compiled_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    current_version: Mapped[str] = mapped_column(String(50), default="1.0.0")
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    project: Mapped["Project"] = relationship(back_populates="agents")
    versions: Mapped[list["AgentVersion"]] = relationship(back_populates="agent", passive_deletes=True)
    runs: Mapped[list["Run"]] = relationship(back_populates="agent", passive_deletes=True)


class AgentVersion(Base):
    __tablename__ = "agent_versions"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    yaml_content: Mapped[str] = mapped_column(Text, nullable=False)
    compiled_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    change_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    agent: Mapped["Agent"] = relationship(back_populates="versions")


# ── Runs + Spans (execution traces) ───────────────────────────────────────────

class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), nullable=True)
    agent_version: Mapped[str | None] = mapped_column(String(50))
    session_id: Mapped[str | None] = mapped_column(String(26))
    status: Mapped[str] = mapped_column(String(50), default="running")  # running|completed|failed
    source: Mapped[str] = mapped_column(String(50), default="simulator")  # simulator|production|sdk
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)

    agent: Mapped["Agent | None"] = relationship(back_populates="runs")
    spans: Mapped[list["Span"]] = relationship(back_populates="run")


class Span(Base):
    __tablename__ = "spans"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    parent_span_id: Mapped[str | None] = mapped_column(String(26))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    # type: llm_call | tool_call | condition | trigger | handoff | sub_agent | slot_fill
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # type-specific data

    run: Mapped["Run"] = relationship(back_populates="spans")


# ── Datasets + Goldens ────────────────────────────────────────────────────────

class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="datasets")
    items: Mapped[list["DatasetItem"]] = relationship(back_populates="dataset")


class DatasetItem(Base):
    __tablename__ = "dataset_items"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"))
    input: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    expected_output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    source: Mapped[str] = mapped_column(String(50), default="human")  # human|auto|llm_annotated
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    dataset: Mapped["Dataset"] = relationship(back_populates="items")


class ReviewQueueItem(Base):
    __tablename__ = "review_queue"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    dataset_id: Mapped[str | None] = mapped_column(ForeignKey("datasets.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending|approved|rejected|edited
    confidence_score: Mapped[float | None] = mapped_column(Float)
    llm_suggested_output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    llm_score: Mapped[float | None] = mapped_column(Float)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ── Eval Suites + Results ─────────────────────────────────────────────────────

class EvalSuite(Base):
    __tablename__ = "eval_suites"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    metric_set_yaml: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="eval_suites")
    runs: Mapped[list["EvalRun"]] = relationship(back_populates="suite", passive_deletes=True)


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    suite_id: Mapped[str] = mapped_column(ForeignKey("eval_suites.id", ondelete="CASCADE"))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"))
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    agent_version: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending|running|completed|failed
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    suite: Mapped["EvalSuite"] = relationship(back_populates="runs")
    results: Mapped[list["EvalResult"]] = relationship(back_populates="eval_run", passive_deletes=True)


class EvalResult(Base):
    __tablename__ = "eval_results"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    eval_run_id: Mapped[str] = mapped_column(ForeignKey("eval_runs.id", ondelete="CASCADE"))
    dataset_item_id: Mapped[str] = mapped_column(ForeignKey("dataset_items.id", ondelete="CASCADE"))
    metric_id: Mapped[str] = mapped_column(String(255), nullable=False)
    score: Mapped[float | None] = mapped_column(Float)
    reasoning: Mapped[str | None] = mapped_column(Text)
    model_used: Mapped[str | None] = mapped_column(String(255))
    turn_index: Mapped[int | None] = mapped_column(Integer)           # null = whole-conversation scope
    scope: Mapped[str] = mapped_column(String(50), default="whole_conversation")  # per_turn|whole_conversation|tool_call
    conversation_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # full history snapshot
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    eval_run: Mapped["EvalRun"] = relationship(back_populates="results")
