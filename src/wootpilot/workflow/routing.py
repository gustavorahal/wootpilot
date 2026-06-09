"""Pure routing functions for the customer-support workflow graph."""

from __future__ import annotations

from wootpilot.domain.models import AgentActionKind, AgentRunStatus, AutomationMode
from wootpilot.workflow.branches import WorkflowBranch
from wootpilot.workflow.state import WorkflowState

__all__ = [
    "route_after_final_decision",
    "route_after_invoke",
    "route_after_llm",
    "route_after_policy",
    "route_after_validate",
]


def route_after_invoke(state: WorkflowState) -> WorkflowBranch:
    """Route away from the graph when the inbound turn should be ignored."""

    if "workflow_decision" in state:
        return WorkflowBranch.ignore_non_customer_public_turn
    return WorkflowBranch.eligible_customer_public_turn


def route_after_policy(state: WorkflowState) -> WorkflowBranch:
    """Route after pre-model policy has accepted or blocked the turn."""

    if "workflow_decision" in state:
        return WorkflowBranch.stop_pre_model_policy_block
    return WorkflowBranch.continue_policy_allows_model


def route_after_llm(state: WorkflowState) -> WorkflowBranch:
    """Route after model proposal generation succeeds or fails."""

    if "workflow_decision" in state:
        return WorkflowBranch.stop_model_proposal_failed
    return WorkflowBranch.continue_model_proposed_action


def route_after_validate(state: WorkflowState) -> WorkflowBranch:
    """Route after post-model policy accepts, blocks, or queues review."""

    decision = state.get("workflow_decision")
    if decision is None:
        return WorkflowBranch.continue_action_policy_approved
    if (
        decision.status is AgentRunStatus.queued_action
        and decision.action_kind is AgentActionKind.private_note
    ):
        return WorkflowBranch.queue_private_review_note
    return WorkflowBranch.stop_post_model_policy_block


def route_after_final_decision(state: WorkflowState) -> WorkflowBranch:
    """Choose the final observe, private-note, or public-reply path."""

    proposal = state.get("agent_proposal")
    if state["automation_mode"] is AutomationMode.observe:
        return WorkflowBranch.observe_only
    if proposal is None:
        return WorkflowBranch.stop_missing_model_proposal
    if (
        state["automation_mode"] is AutomationMode.assist
        or proposal.action_kind is not AgentActionKind.public_message
    ):
        return WorkflowBranch.queue_assist_private_note
    return WorkflowBranch.queue_public_reply
