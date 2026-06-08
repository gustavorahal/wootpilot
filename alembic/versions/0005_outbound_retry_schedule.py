"""add outbound retry schedule fields

Revision ID: 0005_outbound_retry_schedule
Revises: 0004_outbound_safety_context
Create Date: 2026-06-08
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0005_outbound_retry_schedule"
down_revision = "0004_outbound_safety_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing_columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("outbound_actions")
    }
    if "attempt_count" not in existing_columns:
        op.add_column(
            "outbound_actions",
            sa.Column(
                "attempt_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )
    if "next_attempt_at" not in existing_columns:
        op.add_column(
            "outbound_actions",
            sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "error_code" not in existing_columns:
        op.add_column(
            "outbound_actions",
            sa.Column("error_code", sa.String(length=120), nullable=True),
        )
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_outbound_status_next_attempt "
            "ON outbound_actions (status, next_attempt_at)"
        )
    elif "ix_outbound_status_next_attempt" not in {
        index["name"] for index in sa.inspect(bind).get_indexes("outbound_actions")
    }:
        op.create_index(
            "ix_outbound_status_next_attempt",
            "outbound_actions",
            ["status", "next_attempt_at"],
        )


def downgrade() -> None:
    existing_indexes = {
        index["name"]
        for index in sa.inspect(op.get_bind()).get_indexes("outbound_actions")
    }
    if "ix_outbound_status_next_attempt" in existing_indexes:
        op.drop_index(
            "ix_outbound_status_next_attempt",
            table_name="outbound_actions",
        )
    existing_columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("outbound_actions")
    }
    for column_name in ("error_code", "next_attempt_at", "attempt_count"):
        if column_name in existing_columns:
            op.drop_column("outbound_actions", column_name)
