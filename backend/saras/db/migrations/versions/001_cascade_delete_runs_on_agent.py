"""cascade delete runs on agent

Revision ID: 001
Revises:
Create Date: 2026-04-12

Change runs.agent_id FK from SET NULL to CASCADE so that deleting an agent
also deletes all associated runs (and their spans, which already CASCADE from runs).
"""

from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the existing FK (PostgreSQL auto-names it <table>_<col>_fkey)
    op.drop_constraint("runs_agent_id_fkey", "runs", type_="foreignkey")
    op.create_foreign_key(
        "runs_agent_id_fkey",
        "runs",
        "agents",
        ["agent_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("runs_agent_id_fkey", "runs", type_="foreignkey")
    op.create_foreign_key(
        "runs_agent_id_fkey",
        "runs",
        "agents",
        ["agent_id"],
        ["id"],
        ondelete="SET NULL",
    )
