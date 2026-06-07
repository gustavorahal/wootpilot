# Audit Records

`AuditRecord` is the durable explanation of what WootPilot did or chose not to
do. It should connect raw events, normalized messages, context snapshots, policy
decisions, agent proposals, and outbound actions without logging unnecessary raw
payloads.

## Shape

```python
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class AuditEventType(StrEnum):
    event_ignored = "event_ignored"
    agent_invoked = "agent_invoked"
    proposal_created = "proposal_created"
    action_queued = "action_queued"
    action_sent = "action_sent"
    action_blocked = "action_blocked"
    action_failed = "action_failed"


class AuditRecord(BaseModel):
    """Durable, redacted explanation of a WootPilot workflow event."""

    model_config = ConfigDict(frozen=True, strict=True)

    id: str
    tenant_id: str
    event_type: AuditEventType
    raw_event_id: str | None = None
    normalized_message_id: str | None = None
    agent_run_id: str | None = None
    context_snapshot_ids: list[str] = Field(default_factory=list)
    outbound_action_id: str | None = None
    policy_decision_id: str | None = None
    summary: str
    created_at: datetime
```

## Rules

- Audit records should be redacted by default.
- Use ids to correlate detailed records rather than copying raw payloads into
  every audit entry.
- Record ignored events when the reason matters for debugging or safety.
- Preserve enough detail to explain public replies and blocked public replies.
