"""eval schema additions: agent tracking on EvalRun, turn scope on EvalResult

Revision ID: 002
Revises: 001
Create Date: 2026-04-13

Adds:
- eval_runs.agent_id (FK → agents.id, nullable, SET NULL on delete)
- eval_runs.agent_version (varchar, nullable)
- eval_results.turn_index (int, nullable — null means whole-conversation scope)
- eval_results.scope (varchar — per_turn | whole_conversation | tool_call)
- eval_results.conversation_json (jsonb, nullable — full history snapshot)
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── eval_runs additions ───────────────────────────────────────────────────
    op.add_column(
        "eval_runs",
        sa.Column("agent_id", sa.String(26), nullable=True),
    )
    op.add_column(
        "eval_runs",
        sa.Column("agent_version", sa.String(50), nullable=True),
    )
    op.create_foreign_key(
        "eval_runs_agent_id_fkey",
        "eval_runs",
        "agents",
        ["agent_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ── eval_results additions ────────────────────────────────────────────────
    op.add_column(
        "eval_results",
        sa.Column("turn_index", sa.Integer(), nullable=True),
    )
    op.add_column(
        "eval_results",
        sa.Column("scope", sa.String(50), nullable=True, server_default="whole_conversation"),
    )
    op.add_column(
        "eval_results",
        sa.Column("conversation_json", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("eval_results", "conversation_json")
    op.drop_column("eval_results", "scope")
    op.drop_column("eval_results", "turn_index")

    op.drop_constraint("eval_runs_agent_id_fkey", "eval_runs", type_="foreignkey")
    op.drop_column("eval_runs", "agent_version")
    op.drop_column("eval_runs", "agent_id")
