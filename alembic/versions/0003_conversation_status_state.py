"""track Chatwoot status in conversation state

Revision ID: 0003_conversation_status_state
Revises: 0002_conversation_assignment_state
Create Date: 2026-06-08
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0003_conversation_status_state"
down_revision = "0002_conversation_assignment_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversation_states",
        sa.Column("status", sa.String(length=40), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversation_states", "status")
