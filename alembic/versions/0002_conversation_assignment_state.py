"""track Chatwoot assignment in conversation state

Revision ID: 0002_conversation_assignment_state
Revises: 0001_baseline
Create Date: 2026-06-08
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0002_conversation_assignment_state"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversation_states",
        sa.Column("assigned_agent_id", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "conversation_states",
        sa.Column("assigned_team_id", sa.String(length=80), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversation_states", "assigned_team_id")
    op.drop_column("conversation_states", "assigned_agent_id")
