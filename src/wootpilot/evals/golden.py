"""Golden conversation evaluation runner for the support workflow.

Golden cases are deterministic workflow regression checks. They exercise the
LangGraph policy/routing graph with synthetic domain inputs and a fake model
proposal generator, so changes in graph behavior are visible without depending
on Chatwoot, OpenRouter, the database, or a live catalog connector. This is not
an end-to-end test harness; it is a compact behavior contract for the
workflow's final decision.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from wootpilot.domain.models import (
    AgentActionKind,
    AgentProposal,
    AutomationMode,
    CatalogContext,
    ConversationState,
    MessageAuthorType,
    MessageDirection,
    MessageVisibility,
    ModelProposalResult,
    NormalizedMessage,
)
from wootpilot.workflow.graph import build_graph


class GoldenConversationCase(BaseModel):
    """Fixture schema for one provider-free workflow expectation.

    A case contains the customer message, conversation state flags, catalog
    risk signals, and model proposal that should be fed into the graph, plus
    the final workflow status/action/rules expected from those inputs.
    """

    model_config = ConfigDict(strict=True)

    id: str
    automation_mode: AutomationMode
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

    @field_validator("automation_mode", mode="before")
    @classmethod
    def parse_automation_mode(cls, value: AutomationMode | str) -> AutomationMode:
        return AutomationMode(value) if isinstance(value, str) else value

    @field_validator("proposal_action_kind", mode="before")
    @classmethod
    def parse_action_kind(cls, value: AgentActionKind | str) -> AgentActionKind:
        return AgentActionKind(value) if isinstance(value, str) else value


class _StaticProposalGenerator:
    """Proposal generator that returns the action encoded in a golden fixture."""

    def __init__(self, case: GoldenConversationCase) -> None:
        self.case = case

    async def propose(self, **kwargs: object) -> ModelProposalResult:
        """Return fixture-defined proposal data for graph-level evaluation."""

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


async def run_golden_case(case: GoldenConversationCase) -> dict[str, Any]:
    """Run one golden fixture through the real support workflow graph.

    The graph receives synthetic `NormalizedMessage`, `ConversationState`, and
    `CatalogContext` objects so the eval stays focused on policy and
    routing behavior. `_StaticProposalGenerator` injects fixture-defined model
    output instead of calling an LLM provider.

    Args:
        case: Validated golden conversation fixture.

    Returns:
        Compact workflow decision data used by the CLI to compare expectations.
    """

    now = datetime.now(UTC)
    graph = build_graph(proposal_generator=_StaticProposalGenerator(case))
    result = await graph.ainvoke(
        {
            "normalized_message": NormalizedMessage(
                id=f"{case.id}-message",
                raw_event_id=f"{case.id}-raw",
                tenant_id="tenant-1",
                channel_id="channel-1",
                conversation_id=f"{case.id}-conversation",
                message_id=f"{case.id}-provider-message",
                direction=MessageDirection.inbound,
                visibility=MessageVisibility.public,
                author_type=MessageAuthorType.customer,
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
                human_active_until=now if case.state.get("human_active") else None,
                updated_at=now,
            ),
            "catalog_context": CatalogContext(
                query=case.message,
                # Golden fixtures currently exercise catalog policy through
                # risk signals only; product snapshots can be added later when
                # price/availability examples need full catalog context.
                products=[],
                risk_signals=case.catalog_risk_signals,
            ),
            "automation_mode": case.automation_mode,
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


def load_golden_cases(path: Path) -> list[GoldenConversationCase]:
    """Load and validate golden workflow fixtures from a JSON file.

    Args:
        path: JSON file containing a list of golden conversation objects.

    Returns:
        Validated golden cases ready for graph execution.

    Raises:
        ValueError: If the JSON root is not a list.
    """

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("golden conversation fixture must contain a list")
    return [GoldenConversationCase.model_validate(item) for item in data]
