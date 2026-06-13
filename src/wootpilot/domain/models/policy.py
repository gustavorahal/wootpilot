"""Deterministic policy models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PolicyOutcome(StrEnum):
    """Deterministic policy verdict for a checkpoint."""

    allow = "allow"
    block = "block"
    review = "review"


class PolicyStage(StrEnum):
    """Deterministic policy checkpoints inside a workflow run."""

    pre_model = "pre_model"
    post_model = "post_model"


class PolicyRule(StrEnum):
    """Stable rule IDs explaining why a workflow or outbound action was blocked."""

    ingress_customer_public_inbound_required = (
        "ingress.customer_public_inbound_required"
    )
    conversation_not_replyable = "conversation.not_replyable"
    conversation_resolved = "conversation.resolved"
    conversation_wootpilot_paused = "conversation.wootpilot_paused"
    conversation_human_active = "conversation.human_active"
    conversation_assigned_to_human = "conversation.assigned_to_human"
    conversation_superseded_by_new_customer_message = (
        "conversation.superseded_by_new_customer_message"
    )
    conversation_safety_state_missing = "conversation.safety_state_missing"
    conversation_id_mismatch = "conversation.id_mismatch"
    channel_not_replyable = "channel.not_replyable"
    channel_resolved = "channel.resolved"
    channel_wootpilot_paused = "channel.wootpilot_paused"
    channel_assigned_to_human = "channel.assigned_to_human"
    intent_human_requested = "intent.human_requested"
    model_no_proposal = "model.no_proposal"
    model_proposal_failed = "model.proposal_failed"
    public_no_internal_reasoning = "public.no_internal_reasoning"
    public_risk_requires_review = "public.risk_requires_review"
    public_proposal_risk_requires_review = "public.proposal_risk_requires_review"
    public_price_requires_mentionable_snapshot = (
        "public.price_requires_mentionable_snapshot"
    )
    mode_public_reply_not_enabled = "mode.public_reply_not_enabled"
    content_empty = "content.empty"
    unknown_action_kind = "unknown_action_kind"


class TriageResult(BaseModel):
    """Deterministic pre-model classification for one customer turn.

    Triage should reduce unnecessary model calls and select context/policy paths;
    it should not make final public claims. Unknown or sensitive intents should
    bias toward human review rather than forcing a confident label.
    """

    model_config = ConfigDict(strict=True)

    should_invoke: bool
    intent: str
    risk_signals: list[str] = Field(default_factory=list)
    reason: str | None = None


class PolicyDecision(BaseModel):
    """Deterministic policy result for an auditable workflow checkpoint.

    Policy decisions should be reproducible from their inputs and use stable
    `PolicyRule` ids so tests, audit records, and operator notes can explain
    exactly why a turn was allowed or blocked. Free-form model reasoning must
    not become policy.
    """

    model_config = ConfigDict(strict=True)

    id: str
    stage: PolicyStage
    outcome: PolicyOutcome
    rule_ids: list[PolicyRule] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    @field_validator("stage", mode="before")
    @classmethod
    def coerce_stage(cls, value: PolicyStage | str) -> PolicyStage:
        return value if isinstance(value, PolicyStage) else PolicyStage(str(value))

    @field_validator("rule_ids", mode="before")
    @classmethod
    def coerce_rule_ids(cls, value: list[PolicyRule | str]) -> list[PolicyRule]:
        return [
            item if isinstance(item, PolicyRule) else PolicyRule(str(item))
            for item in value
        ]
