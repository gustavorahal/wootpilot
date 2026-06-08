"""Workflow decision models."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from wootpilot.domain.models.policy import PolicyRule
from wootpilot.domain.models.proposals import AgentActionKind


class AgentRunStatus(StrEnum):
    """Final workflow outcomes stored on an agent run."""

    ignored = "ignored"
    proposed = "proposed"
    blocked_by_policy = "blocked_by_policy"
    queued_action = "queued_action"
    sent_public_message = "sent_public_message"
    sent_private_note = "sent_private_note"
    failed = "failed"


class WorkflowDecision(BaseModel):
    """Final graph decision consumed by audit and outbound queueing.

    `WorkflowDecision` is the boundary where graph reasoning becomes durable
    application intent. It still does not mean a Chatwoot side effect happened:
    queued actions must be claimed and executed by the outbound worker.
    """

    model_config = ConfigDict(strict=True)

    status: AgentRunStatus
    action_kind: AgentActionKind = AgentActionKind.none
    content: str | None = None
    summary: str
    rule_ids: list[PolicyRule] = Field(default_factory=list)
    risk_reasons: list[str] = Field(default_factory=list)

    @field_validator("rule_ids", mode="before")
    @classmethod
    def coerce_rule_ids(cls, value: list[PolicyRule | str]) -> list[PolicyRule]:
        return [
            item if isinstance(item, PolicyRule) else PolicyRule(str(item))
            for item in value
        ]
