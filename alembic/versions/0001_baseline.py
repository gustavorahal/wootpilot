"""baseline schema

Revision ID: 0001_baseline
Revises:
Create Date: 2026-06-08
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "raw_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_event_id", sa.String(length=160), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "provider", "provider_event_id", name="uq_raw_provider_event"
        ),
    )
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("raw_event_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=80), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_account_id", sa.String(length=80), nullable=False),
        sa.Column("provider_inbox_id", sa.String(length=80), nullable=False),
        sa.Column("provider_conversation_id", sa.String(length=80), nullable=False),
        sa.Column("provider_message_id", sa.String(length=80), nullable=False),
        sa.Column("provider_contact_id", sa.String(length=80), nullable=True),
        sa.Column("channel_id", sa.String(length=80), nullable=False),
        sa.Column("conversation_id", sa.String(length=80), nullable=False),
        sa.Column("message_id", sa.String(length=80), nullable=False),
        sa.Column("contact_id", sa.String(length=80), nullable=True),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("visibility", sa.String(length=20), nullable=False),
        sa.Column("author_type", sa.String(length=40), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("attachments", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["raw_event_id"], ["raw_events.id"]),
        sa.UniqueConstraint(
            "tenant_id", "channel_id", "message_id", name="uq_channel_message"
        ),
    )
    op.create_table(
        "conversation_states",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=80), nullable=False),
        sa.Column("channel_id", sa.String(length=80), nullable=False),
        sa.Column("conversation_id", sa.String(length=80), nullable=False),
        sa.Column("human_active_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_human_public_message_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "last_customer_message_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("replyable", sa.Boolean(), nullable=False),
        sa.Column("paused", sa.Boolean(), nullable=False),
        sa.Column("auto_ok", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "channel_id", "conversation_id", name="uq_conversation_state"
        ),
    )
    op.create_table(
        "context_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=80), nullable=False),
        sa.Column("conversation_id", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=60), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("normalized_message_id", sa.String(length=36), nullable=False),
        sa.Column("raw_event_id", sa.String(length=36), nullable=False),
        sa.Column("bot_mode", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=60), nullable=False),
        sa.Column("workflow_decision", sa.JSON(), nullable=False),
        sa.Column("model_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["normalized_message_id"], ["conversation_messages.id"]
        ),
        sa.ForeignKeyConstraint(["raw_event_id"], ["raw_events.id"]),
    )
    op.create_table(
        "policy_decisions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("agent_run_id", sa.String(length=36), nullable=True),
        sa.Column("normalized_message_id", sa.String(length=36), nullable=False),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.Column("outcome", sa.String(length=40), nullable=False),
        sa.Column("rule_ids", sa.JSON(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"]),
        sa.ForeignKeyConstraint(
            ["normalized_message_id"], ["conversation_messages.id"]
        ),
    )
    op.create_table(
        "outbound_actions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("agent_run_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=80), nullable=False),
        sa.Column("channel_id", sa.String(length=80), nullable=False),
        sa.Column("conversation_id", sa.String(length=80), nullable=False),
        sa.Column("source_message_id", sa.String(length=80), nullable=False),
        sa.Column("action_kind", sa.String(length=40), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("provider_message_id", sa.String(length=80), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"]),
        sa.UniqueConstraint("idempotency_key", name="uq_outbound_idempotency"),
    )
    op.create_table(
        "audit_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("raw_event_id", sa.String(length=36), nullable=True),
        sa.Column("normalized_message_id", sa.String(length=36), nullable=True),
        sa.Column("agent_run_id", sa.String(length=36), nullable=True),
        sa.Column("policy_decision_id", sa.String(length=36), nullable=True),
        sa.Column("context_snapshot_ids", sa.JSON(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["raw_event_id"], ["raw_events.id"]),
        sa.ForeignKeyConstraint(
            ["normalized_message_id"], ["conversation_messages.id"]
        ),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"]),
        sa.ForeignKeyConstraint(["policy_decision_id"], ["policy_decisions.id"]),
    )


def downgrade() -> None:
    for table in [
        "audit_records",
        "outbound_actions",
        "policy_decisions",
        "agent_runs",
        "context_snapshots",
        "conversation_states",
        "conversation_messages",
        "raw_events",
    ]:
        op.drop_table(table)
