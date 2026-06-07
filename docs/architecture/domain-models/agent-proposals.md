# Agent Proposals

The LLM should propose an action. WootPilot should decide execution state.

```python
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class AgentActionKind(StrEnum):
    none = "none"
    public_message = "public_message"
    private_note = "private_note"


class AgentProposal(BaseModel):
    """LLM-produced proposal that must pass deterministic policy before use."""

    model_config = ConfigDict(strict=True)

    action_kind: AgentActionKind
    summary: str
    public_message: str | None = None
    private_note: str | None = None
    risk_reasons: list[str] = Field(default_factory=list)
    context_snapshot_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class AgentRunStatus(StrEnum):
    ignored = "ignored"
    proposed = "proposed"
    blocked_by_policy = "blocked_by_policy"
    queued_action = "queued_action"
    sent_public_message = "sent_public_message"
    sent_private_note = "sent_private_note"
    failed = "failed"
```

The model must not set `sent_public_message`, `sent_private_note`, or `failed`.
Those are system outcomes based on guard checks, outbox execution, and channel
API results.

## Rules

- Treat model output as a proposal, not as a fact about what happened.
- Keep action kinds small and explicit.
- Include context snapshot ids so reviewers can trace why the proposal was made.
- Use deterministic policy to transform a proposal into a queued action,
  blocked action, or audit-only shadow result.
- Assign final run status only after guard checks and channel API calls.
