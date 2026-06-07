# Conversation State

`ConversationState` stores WootPilot's operational view of a support
conversation. It is separate from the normalized message stream and from
Chatwoot's canonical conversation record.

## Shape

```python
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ConversationState(BaseModel):
    """WootPilot state used to suppress unsafe or annoying automation."""

    model_config = ConfigDict(frozen=True, strict=True)

    tenant_id: str
    provider: str
    provider_account_id: str
    provider_conversation_id: str
    human_operator_active: bool
    human_operator_active_until: datetime | None = None
    last_human_public_message_at: datetime | None = None
    last_customer_message_at: datetime | None = None
    updated_at: datetime
```

## Rules

- Re-read this state immediately before public outbound execution.
- Human-active suppression should block public auto replies, not necessarily
  private notes.
- Use time-bounded suppression windows instead of permanent sticky flags.
- Keep Chatwoot as the system of record for conversation content and assignment.
