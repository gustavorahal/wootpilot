"""store normalized message provider identity

Revision ID: 0006_message_provider_identity
Revises: 0005_outbound_retry_schedule
Create Date: 2026-06-08
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0006_message_provider_identity"
down_revision = "0005_outbound_retry_schedule"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing_columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("conversation_messages")
    }
    additions = [
        (
            "provider",
            sa.Column(
                "provider",
                sa.String(length=40),
                nullable=False,
                server_default="chatwoot",
            ),
        ),
        (
            "provider_account_id",
            sa.Column(
                "provider_account_id",
                sa.String(length=80),
                nullable=False,
                server_default="",
            ),
        ),
        (
            "provider_inbox_id",
            sa.Column(
                "provider_inbox_id",
                sa.String(length=80),
                nullable=False,
                server_default="",
            ),
        ),
        (
            "provider_conversation_id",
            sa.Column(
                "provider_conversation_id",
                sa.String(length=80),
                nullable=False,
                server_default="",
            ),
        ),
        (
            "provider_message_id",
            sa.Column(
                "provider_message_id",
                sa.String(length=80),
                nullable=False,
                server_default="",
            ),
        ),
        (
            "provider_contact_id",
            sa.Column("provider_contact_id", sa.String(length=80), nullable=True),
        ),
        (
            "attachments",
            sa.Column(
                "attachments",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
        ),
    ]
    for column_name, column in additions:
        if column_name not in existing_columns:
            op.add_column("conversation_messages", column)


def downgrade() -> None:
    existing_columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("conversation_messages")
    }
    for column_name in (
        "attachments",
        "provider_contact_id",
        "provider_message_id",
        "provider_conversation_id",
        "provider_inbox_id",
        "provider_account_id",
        "provider",
    ):
        if column_name in existing_columns:
            op.drop_column("conversation_messages", column_name)
