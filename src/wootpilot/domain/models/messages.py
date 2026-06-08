"""Message and channel-event models.

Chatwoot webhook payloads are translated into these objects before policy or
LangGraph sees them. The goal is to preserve provider identity and routing
context without letting raw provider DTO shape leak into domain services.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from wootpilot.domain.models.conversations import ConversationStatus
from wootpilot.domain.models.providers import Provider


class MessageDirection(StrEnum):
    """Direction of a message from WootPilot's point of view."""

    inbound = "inbound"
    outbound = "outbound"


class MessageVisibility(StrEnum):
    """Whether a message is customer-visible or an internal note."""

    public = "public"
    private = "private"


class MessageAuthorType(StrEnum):
    """Normalized author roles used by policy and conversation-state updates."""

    customer = "customer"
    human_agent = "human_agent"
    bot = "bot"


class AttachmentMetadata(BaseModel):
    """Provider attachment metadata safe to carry into policy decisions."""

    model_config = ConfigDict(strict=True)

    provider_attachment_id: str | None = None
    content_type: str | None = None
    file_name: str | None = None
    url: str | None = None


class NormalizedMessage(BaseModel):
    """Provider message translated into WootPilot's channel-neutral contract.

    Preserve provider account, inbox, conversation, message, and contact ids so
    webhook handling, audit records, and outbound idempotency can be correlated
    without leaking raw Chatwoot payloads into policy or graph code. Raw webhook
    bodies belong in raw event storage, not on this model.
    """

    model_config = ConfigDict(strict=True)

    id: str
    raw_event_id: str
    tenant_id: str
    provider: Provider = Provider.chatwoot
    provider_account_id: str = ""
    provider_inbox_id: str = ""
    provider_conversation_id: str = ""
    provider_message_id: str = ""
    provider_contact_id: str | None = None
    channel_id: str
    conversation_id: str
    message_id: str
    contact_id: str | None = None
    direction: MessageDirection
    visibility: MessageVisibility
    author_type: MessageAuthorType
    content: str
    attachments: list[AttachmentMetadata] = Field(default_factory=list)
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("provider", mode="before")
    @classmethod
    def coerce_provider(cls, value: Provider | str) -> Provider:
        return value if isinstance(value, Provider) else Provider(str(value))

    @field_validator("direction", mode="before")
    @classmethod
    def coerce_direction(cls, value: MessageDirection | str) -> MessageDirection:
        return (
            value
            if isinstance(value, MessageDirection)
            else MessageDirection(str(value))
        )

    @field_validator("visibility", mode="before")
    @classmethod
    def coerce_visibility(cls, value: MessageVisibility | str) -> MessageVisibility:
        return (
            value
            if isinstance(value, MessageVisibility)
            else MessageVisibility(str(value))
        )

    @field_validator("author_type", mode="before")
    @classmethod
    def coerce_author_type(cls, value: MessageAuthorType | str) -> MessageAuthorType:
        return (
            value
            if isinstance(value, MessageAuthorType)
            else MessageAuthorType(str(value))
        )

    def is_customer_public_inbound(self) -> bool:
        """Return whether this message is eligible to start agent handling."""

        return (
            self.direction is MessageDirection.inbound
            and self.visibility is MessageVisibility.public
            and self.author_type is MessageAuthorType.customer
            and bool(self.content.strip())
        )

    def is_human_public_reply(self) -> bool:
        """Return whether this message marks a human as active in Chatwoot."""

        return (
            self.direction is MessageDirection.outbound
            and self.visibility is MessageVisibility.public
            and self.author_type is MessageAuthorType.human_agent
        )


class ChannelEvent(BaseModel):
    """Non-message Chatwoot conversation event that updates local safety state."""

    model_config = ConfigDict(strict=True)

    id: str
    raw_event_id: str
    event_type: str
    tenant_id: str
    channel_id: str
    conversation_id: str
    status: ConversationStatus | None = None
    replyable: bool | None = None
    paused: bool = False
    auto_ok: bool = False
    assigned_agent_id: str | None = None
    assigned_team_id: str | None = None
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)

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
