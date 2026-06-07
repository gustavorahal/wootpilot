# Normalized Messages

`NormalizedMessage` is WootPilot's internal message representation after channel
normalization. It should preserve provider identity and support-routing context
without exposing raw Chatwoot payload structure to domain services.

## Shape

```python
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class MessageAuthorType(StrEnum):
    customer = "customer"
    human_agent = "human_agent"
    bot = "bot"
    system = "system"
    unknown = "unknown"


class MessageDirection(StrEnum):
    inbound = "inbound"
    outbound = "outbound"


class MessageVisibility(StrEnum):
    public = "public"
    private = "private"


class AttachmentMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    provider_attachment_id: str | None = None
    content_type: str | None = None
    file_name: str | None = None
    url: str | None = None


class NormalizedMessage(BaseModel):
    """Channel-independent message WootPilot can reason about safely."""

    model_config = ConfigDict(frozen=True, strict=True)

    tenant_id: str
    provider: str
    provider_account_id: str
    provider_inbox_id: str
    provider_conversation_id: str
    provider_message_id: str
    provider_contact_id: str | None = None
    author_type: MessageAuthorType
    direction: MessageDirection
    visibility: MessageVisibility
    text: str
    attachments: list[AttachmentMetadata] = Field(default_factory=list)
    created_at: datetime
```

## Rules

- Preserve provider account, inbox, conversation, message, and contact ids.
- Ignore private notes, outbound messages, bot echoes, and system events before
  invoking the LLM.
- Keep raw webhook payloads in raw event storage, not on `NormalizedMessage`.
- Keep the text as received except for safe normalization such as trimming null
  bytes or invalid encoding artifacts.
