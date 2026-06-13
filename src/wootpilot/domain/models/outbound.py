"""Outbound action models."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from wootpilot.domain.models.proposals import AgentActionKind


class OutboundActionStatus(StrEnum):
    """Delivery lifecycle for queued provider-side actions."""

    queued = "queued"
    executing = "executing"
    sent = "sent"
    retryable_failure = "retryable_failure"
    permanent_failure = "permanent_failure"
    blocked_by_policy = "blocked_by_policy"
    superseded = "superseded"


class QueuedOutboundAction(BaseModel):
    """Outbound action read model consumed by the executor.

    The repository builds this from SQLAlchemy rows so application services can
    evaluate delivery policy without depending on ORM implementation details.

    Source customer message ids and provider-created outbound message ids are
    intentionally separate in persistence. The executor must re-check policy and
    human/channel safety immediately before public sends, because a queued
    action can become unsafe while waiting.
    """

    model_config = ConfigDict(strict=True)

    id: str
    tenant_id: str
    channel_id: str
    conversation_id: str
    source_message_id: str
    action_kind: AgentActionKind
    content: str
    safety_context: dict[str, Any] = Field(default_factory=dict)
    status: OutboundActionStatus
    attempt_count: int = 0

    @field_validator("action_kind", mode="before")
    @classmethod
    def coerce_action_kind(cls, value: AgentActionKind | str) -> AgentActionKind:
        return (
            value
            if isinstance(value, AgentActionKind)
            else AgentActionKind(str(value))
        )

    @field_validator("status", mode="before")
    @classmethod
    def coerce_status(cls, value: OutboundActionStatus | str) -> OutboundActionStatus:
        return (
            value
            if isinstance(value, OutboundActionStatus)
            else OutboundActionStatus(str(value))
        )
