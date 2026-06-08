"""LLM proposal models.

The model adapter produces proposals, not execution facts. Everything here is
input to deterministic WootPilot policy and outbound execution, never proof that
anything was sent to a customer.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentActionKind(StrEnum):
    """Action shape selected by the workflow before outbound execution."""

    none = "none"
    public_message = "public_message"
    private_note = "private_note"


class AgentProposal(BaseModel):
    """LLM-produced action proposal; never a final execution result.

    The model proposes content and risk reasons. WootPilot decides whether that
    proposal becomes a queued action, a private review note, a blocked decision,
    or an audit-only shadow result. The model must not assign final send/failure
    status.
    """

    model_config = ConfigDict(strict=True)

    action_kind: AgentActionKind
    summary: str
    public_message: str | None = None
    private_note: str | None = None
    risk_reasons: list[str] = Field(default_factory=list)
    context_snapshot_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    error_code: str | None = None


class ModelProposalResult(BaseModel):
    """Model adapter result including proposal and provider metadata."""

    model_config = ConfigDict(strict=True)

    proposal: AgentProposal | None = None
    retryable_error: str | None = None
    permanent_error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
