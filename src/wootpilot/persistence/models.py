"""SQLAlchemy persistence models for WootPilot-owned operational records."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

__all__ = [
    "AgentRunRow",
    "AuditRecordRow",
    "Base",
    "ContextSnapshotRow",
    "ConversationMessageRow",
    "ConversationStateRow",
    "OutboundActionRow",
    "PolicyDecisionRow",
    "RawEventRow",
]


class Base(DeclarativeBase):
    pass


class RawEventRow(Base):
    __tablename__ = "raw_events"
    __table_args__ = (UniqueConstraint("provider", "provider_event_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider: Mapped[str] = mapped_column(String(40))
    provider_event_id: Mapped[str] = mapped_column(String(160))
    event_type: Mapped[str] = mapped_column(String(80))
    payload_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(40))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ConversationMessageRow(Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (UniqueConstraint("tenant_id", "channel_id", "message_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    raw_event_id: Mapped[str] = mapped_column(ForeignKey("raw_events.id"))
    tenant_id: Mapped[str] = mapped_column(String(80))
    provider: Mapped[str] = mapped_column(String(40), default="chatwoot")
    provider_account_id: Mapped[str] = mapped_column(String(80), default="")
    provider_inbox_id: Mapped[str] = mapped_column(String(80), default="")
    provider_conversation_id: Mapped[str] = mapped_column(String(80), default="")
    provider_message_id: Mapped[str] = mapped_column(String(80), default="")
    provider_contact_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    channel_id: Mapped[str] = mapped_column(String(80))
    conversation_id: Mapped[str] = mapped_column(String(80))
    message_id: Mapped[str] = mapped_column(String(80))
    contact_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    direction: Mapped[str] = mapped_column(String(20))
    visibility: Mapped[str] = mapped_column(String(20))
    author_type: Mapped[str] = mapped_column(String(40))
    content: Mapped[str] = mapped_column(Text)
    attachments: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    message_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON)


class ConversationStateRow(Base):
    __tablename__ = "conversation_states"
    __table_args__ = (UniqueConstraint("tenant_id", "channel_id", "conversation_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(80))
    channel_id: Mapped[str] = mapped_column(String(80))
    conversation_id: Mapped[str] = mapped_column(String(80))
    human_active_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_human_public_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_customer_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    assigned_agent_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    assigned_team_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    replyable: Mapped[bool] = mapped_column(Boolean, default=True)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ContextSnapshotRow(Base):
    __tablename__ = "context_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(80))
    conversation_id: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(60))
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AgentRunRow(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    normalized_message_id: Mapped[str] = mapped_column(
        ForeignKey("conversation_messages.id")
    )
    raw_event_id: Mapped[str] = mapped_column(ForeignKey("raw_events.id"))
    automation_mode: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(60))
    workflow_decision: Mapped[dict[str, Any]] = mapped_column(JSON)
    model_metadata: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PolicyDecisionRow(Base):
    __tablename__ = "policy_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_runs.id"), nullable=True
    )
    normalized_message_id: Mapped[str] = mapped_column(
        ForeignKey("conversation_messages.id")
    )
    stage: Mapped[str] = mapped_column(String(40))
    outcome: Mapped[str] = mapped_column(String(40))
    rule_ids: Mapped[list[str]] = mapped_column(JSON)
    details: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OutboundActionRow(Base):
    __tablename__ = "outbound_actions"
    __table_args__ = (
        UniqueConstraint("idempotency_key"),
        Index("ix_outbound_status_next_attempt", "status", "next_attempt_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent_run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"))
    tenant_id: Mapped[str] = mapped_column(String(80))
    channel_id: Mapped[str] = mapped_column(String(80))
    conversation_id: Mapped[str] = mapped_column(String(80))
    source_message_id: Mapped[str] = mapped_column(String(80))
    action_kind: Mapped[str] = mapped_column(String(40))
    content: Mapped[str] = mapped_column(Text)
    safety_context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(40))
    idempotency_key: Mapped[str] = mapped_column(String(200))
    provider_message_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditRecordRow(Base):
    __tablename__ = "audit_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    raw_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("raw_events.id"), nullable=True
    )
    normalized_message_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversation_messages.id"), nullable=True
    )
    agent_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_runs.id"), nullable=True
    )
    policy_decision_id: Mapped[str | None] = mapped_column(
        ForeignKey("policy_decisions.id"), nullable=True
    )
    context_snapshot_ids: Mapped[list[str]] = mapped_column(JSON)
    event_type: Mapped[str] = mapped_column(String(80))
    summary: Mapped[str] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
