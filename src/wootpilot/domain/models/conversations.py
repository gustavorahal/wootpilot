"""Conversation safety-state models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator


class ConversationStatus(StrEnum):
    """Conversation lifecycle states WootPilot currently makes decisions on."""

    open = "open"
    pending = "pending"
    resolved = "resolved"


class ConversationState(BaseModel):
    """Current safety state for a provider conversation.

    This model is intentionally conservative. `auto_ok` is the explicit escape
    hatch that allows automation to continue despite assignment or recent human
    activity; without it, WootPilot should assume a human is in control.

    Chatwoot remains the system of record for conversation content and
    assignment. This state is WootPilot's local suppression view and should be
    re-checked, together with fresh channel state, before public sends.
    """

    model_config = ConfigDict(strict=True)

    id: str
    tenant_id: str
    channel_id: str
    conversation_id: str
    human_active_until: datetime | None = None
    last_human_public_message_at: datetime | None = None
    last_customer_message_at: datetime | None = None
    assigned_agent_id: str | None = None
    assigned_team_id: str | None = None
    status: ConversationStatus | None = None
    replyable: bool = True
    paused: bool = False
    auto_ok: bool = False
    updated_at: datetime

    @field_validator("status", mode="before")
    @classmethod
    def coerce_status(
        cls, value: ConversationStatus | str | None
    ) -> ConversationStatus | None:
        if value in {None, ""}:
            return None
        return (
            value
            if isinstance(value, ConversationStatus)
            else ConversationStatus(str(value))
        )
