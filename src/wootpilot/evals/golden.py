"""Golden conversation evaluation runner for the support workflow."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from wootpilot.domain.models import (
    AgentActionKind,
    AgentProposal,
    BotMode,
    ConversationState,
    ModelProposalResult,
    NormalizedMessage,
    StructuredCatalogContext,
)
from wootpilot.workflow.graph import build_support_graph


class GoldenConversation(BaseModel):
    """A deterministic, provider-free workflow behavior expectation."""

    model_config = ConfigDict(strict=True)

    id: str
    bot_mode: BotMode
    message: str
    proposal_action_kind: AgentActionKind = AgentActionKind.public_message
    proposal_public_message: str | None = None
    proposal_private_note: str | None = None
    proposal_risk_reasons: list[str] = Field(default_factory=list)
    catalog_risk_signals: list[str] = Field(default_factory=list)
    state: dict[str, Any] = Field(default_factory=dict)
    expected_status: str
    expected_action_kind: str
    expected_rule_ids: list[str] = Field(default_factory=list)

    @field_validator("bot_mode", mode="before")
    @classmethod
    def parse_bot_mode(cls, value):
        return BotMode(value) if isinstance(value, str) else value

    @field_validator("proposal_action_kind", mode="before")
    @classmethod
    def parse_action_kind(cls, value):
        return AgentActionKind(value) if isinstance(value, str) else value


class StaticProposalPort:
    def __init__(self, case: GoldenConversation):
        self.case = case

    async def propose(self, **kwargs) -> ModelProposalResult:
        return ModelProposalResult(
            proposal=AgentProposal(
                action_kind=self.case.proposal_action_kind,
                summary=f"Golden proposal for {self.case.id}",
                public_message=self.case.proposal_public_message,
                private_note=self.case.proposal_private_note,
                risk_reasons=self.case.proposal_risk_reasons,
                confidence=0.8,
            ),
            metadata={"provider": "golden"},
        )


async def run_golden_case(case: GoldenConversation) -> dict[str, Any]:
    now = datetime.now(UTC)
    graph = build_support_graph(model_port=StaticProposalPort(case))
    result = await graph.ainvoke(
        {
            "normalized_message": NormalizedMessage(
                id=f"{case.id}-message",
                raw_event_id=f"{case.id}-raw",
                tenant_id="tenant-1",
                channel_id="channel-1",
                conversation_id=f"{case.id}-conversation",
                message_id=f"{case.id}-provider-message",
                direction="inbound",
                visibility="public",
                author_type="customer",
                content=case.message,
                created_at=now,
            ),
            "conversation_state": ConversationState(
                id=f"{case.id}-state",
                tenant_id="tenant-1",
                channel_id="channel-1",
                conversation_id=f"{case.id}-conversation",
                replyable=case.state.get("replyable", True),
                paused=case.state.get("paused", False),
                auto_ok=case.state.get("auto_ok", False),
                human_active_until=now if case.state.get("human_active") else None,
                updated_at=now,
            ),
            "catalog_context": StructuredCatalogContext(
                query=case.message,
                products=[],
                risk_signals=case.catalog_risk_signals,
            ),
            "bot_mode": case.bot_mode,
        },
        config={
            "configurable": {
                "thread_id": (
                    f"tenant:tenant-1:channel:channel-1:"
                    f"conversation:{case.id}-conversation"
                )
            }
        },
    )
    decision = result["workflow_decision"]
    return {
        "id": case.id,
        "status": decision.status.value,
        "action_kind": decision.action_kind.value,
        "rule_ids": decision.rule_ids,
    }


def load_golden_cases(path: Path) -> list[GoldenConversation]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("golden conversation fixture must contain a list")
    return [GoldenConversation.model_validate(item) for item in data]
