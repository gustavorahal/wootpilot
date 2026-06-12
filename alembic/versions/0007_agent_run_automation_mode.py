"""rename agent run bot mode to automation mode

Revision ID: 0007_agent_run_automation_mode
Revises: 0006_message_provider_identity
Create Date: 2026-06-12
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0007_agent_run_automation_mode"
down_revision = "0006_message_provider_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing_columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("agent_runs")
    }
    if "automation_mode" in existing_columns:
        return
    if "bot_mode" in existing_columns:
        op.alter_column(
            "agent_runs",
            "bot_mode",
            new_column_name="automation_mode",
            existing_type=sa.String(length=40),
            existing_nullable=False,
        )
        return
    op.add_column(
        "agent_runs",
        sa.Column(
            "automation_mode",
            sa.String(length=40),
            nullable=False,
            server_default="public_reply",
        ),
    )


def downgrade() -> None:
    existing_columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("agent_runs")
    }
    if "bot_mode" in existing_columns:
        return
    if "automation_mode" in existing_columns:
        op.alter_column(
            "agent_runs",
            "automation_mode",
            new_column_name="bot_mode",
            existing_type=sa.String(length=40),
            existing_nullable=False,
        )
