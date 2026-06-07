# Outbound Actions

`OutboundAction` is a durable requested side effect against a channel. For version
1, the target channel is Chatwoot and the action kind is either a public message
or private note.

The agent graph may propose an action, but only the outbound executor should mark
an action as sent or failed.

## Shape

```python
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from wootpilot.domain.policy_decisions import PolicyDecision


class OutboundActionKind(StrEnum):
    public_message = "public_message"
    private_note = "private_note"


class OutboundActionStatus(StrEnum):
    queued = "queued"
    executing = "executing"
    sent = "sent"
    blocked_by_policy = "blocked_by_policy"
    failed_retryable = "failed_retryable"
    failed_permanent = "failed_permanent"
    cancelled = "cancelled"


class OutboundTarget(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    tenant_id: str
    provider: str
    provider_account_id: str
    provider_conversation_id: str


class OutboundAction(BaseModel):
    """Idempotent channel side effect requested by WootPilot."""

    model_config = ConfigDict(frozen=True, strict=True)

    id: str
    agent_run_id: str
    target: OutboundTarget
    kind: OutboundActionKind
    content: str
    idempotency_key: str
    status: OutboundActionStatus
    policy_decision: PolicyDecision
    provider_message_id: str | None = None
    attempt_count: int = Field(default=0, ge=0)
    next_attempt_at: datetime | None = None
    error_code: str | None = None
    created_at: datetime
    updated_at: datetime
```

## Rules

- Build `idempotency_key` from stable inputs, not timestamps or retry attempts.
- Re-check policy and human-active state immediately before public sends.
- Keep status transitions explicit and persisted.
- Retry only actions that are safe to retry idempotently.
- Do not let the LLM assign final execution status.
