"""State contract shared by the customer-support workflow graph."""

from __future__ import annotations

from typing import Annotated, NotRequired, TypedDict

from wootpilot.domain.models import (
    AgentProposal,
    AutomationMode,
    CatalogContext,
    ConversationState,
    NormalizedMessage,
    PolicyDecision,
    TriageResult,
    WorkflowDecision,
)

__all__ = ["WorkflowInputState", "WorkflowOutputState", "WorkflowState"]


class WorkflowInputState(TypedDict):
    """Inputs prepared before one support workflow graph run."""

    normalized_message: Annotated[
        NormalizedMessage,
        "Prepared Chatwoot message entering the graph.",
    ]
    conversation_state: Annotated[
        ConversationState,
        "Current replyability, assignment, pause, and human-activity state.",
    ]
    catalog_context: Annotated[
        CatalogContext,
        "Product and catalog context loaded before model proposal.",
    ]
    automation_mode: Annotated[
        AutomationMode,
        "Tenant/channel automation mode: observe, assist, or public reply.",
    ]


class WorkflowOutputState(TypedDict, total=False):
    """Outputs consumed after one support workflow graph run."""

    workflow_decision: Annotated[
        WorkflowDecision,
        "Final graph outcome consumed by audit and outbound queueing services.",
    ]
    pre_model_policy_decision: Annotated[
        PolicyDecision,
        "Deterministic policy result computed before any model call.",
    ]
    post_model_policy_decision: Annotated[
        PolicyDecision,
        "Deterministic validation result for the proposed outbound action.",
    ]
    model_metadata: Annotated[
        dict,
        "Provider metadata captured with the model proposal attempt.",
    ]


class WorkflowState(WorkflowInputState, WorkflowOutputState):
    """Internal state shared by every node in the support workflow graph.

    LangGraph passes this dictionary from node to node. Each node reads the
    inputs it needs and returns a partial update that LangGraph merges into the
    next state. Input keys are prepared by the application service before the
    graph starts; output keys are returned after the graph finishes; internal
    scratch keys are produced as the workflow advances.

    Keep these keys stable unless the workflow boundary is intentionally being
    migrated. They are part of the checkpoint, audit, and node-to-node contract.
    """

    triage_result: NotRequired[
        Annotated[
            TriageResult,
            "Intent and risk signals produced from the customer message.",
        ]
    ]
    agent_proposal: NotRequired[
        Annotated[
            AgentProposal | None,
            "Structured model proposal, or None when proposal generation failed.",
        ]
    ]
