"""State contract shared by the customer-support workflow graph."""

from __future__ import annotations

from typing import Annotated, NotRequired, TypedDict

from wootpilot.domain.models import (
    AgentProposal,
    AutomationMode,
    ConversationState,
    NormalizedMessage,
    PolicyDecision,
    StructuredCatalogContext,
    TriageResult,
    WorkflowDecision,
)

__all__ = ["WorkflowState"]


class WorkflowState(TypedDict):
    """State contract shared by every node in the support workflow graph.

    LangGraph passes this dictionary from node to node. Each node reads the
    inputs it needs and returns a partial update that LangGraph merges into the
    next state. Required keys are prepared by the application service before the
    graph starts; optional keys are produced as the workflow advances.

    Keep these keys stable unless the workflow boundary is intentionally being
    migrated. They are part of the checkpoint, audit, and node-to-node contract.
    """

    normalized_message: Annotated[
        NormalizedMessage,
        "Prepared Chatwoot message entering the graph.",
    ]
    conversation_state: Annotated[
        ConversationState,
        "Current replyability, assignment, pause, and human-activity state.",
    ]
    catalog_context: Annotated[
        StructuredCatalogContext,
        "Product and catalog context loaded before model proposal.",
    ]
    automation_mode: Annotated[
        AutomationMode,
        "Tenant/channel automation mode: observe, assist, or public reply.",
    ]
    triage_result: NotRequired[
        Annotated[
            TriageResult,
            "Intent and risk signals produced from the customer message.",
        ]
    ]
    pre_model_policy_decision: NotRequired[
        Annotated[
            PolicyDecision,
            "Deterministic policy result computed before any model call.",
        ]
    ]
    agent_proposal: NotRequired[
        Annotated[
            AgentProposal | None,
            "Structured model proposal, or None when proposal generation failed.",
        ]
    ]
    model_metadata: NotRequired[
        Annotated[
            dict,
            "Provider metadata captured with the model proposal attempt.",
        ]
    ]
    provider_error: NotRequired[
        Annotated[
            str | None,
            "Retryable or permanent provider error from proposal generation.",
        ]
    ]
    post_model_policy_decision: NotRequired[
        Annotated[
            PolicyDecision,
            "Deterministic validation result for the proposed outbound action.",
        ]
    ]
    workflow_decision: NotRequired[
        Annotated[
            WorkflowDecision,
            "Final graph outcome consumed by audit and outbound queueing services.",
        ]
    ]
