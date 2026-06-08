"""store outbound final-check safety context

Revision ID: 0004_outbound_safety_context
Revises: 0003_conversation_status_state
Create Date: 2026-06-08
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0004_outbound_safety_context"
down_revision = "0003_conversation_status_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing_columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("outbound_actions")
    }
    if "safety_context" not in existing_columns:
        op.add_column(
            "outbound_actions",
            sa.Column(
                "safety_context",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
        )


def downgrade() -> None:
    existing_columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("outbound_actions")
    }
    if "safety_context" in existing_columns:
        op.drop_column("outbound_actions", "safety_context")
