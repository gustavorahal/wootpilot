"""Named routes and routing functions for the customer-support workflow graph."""

from __future__ import annotations

from enum import StrEnum

from wootpilot.domain.models import AgentActionKind, AgentRunStatus, AutomationMode
from wootpilot.workflow.state import WorkflowState

__all__ = [
    "WORKFLOW_BRANCH_DESCRIPTIONS",
    "WorkflowBranch",
    "route_after_final_decision",
    "route_after_invoke",
    "route_after_proposal",
    "route_after_policy",
    "route_after_validate",
]


class WorkflowBranch(StrEnum):
    """Named conditional routes in the support workflow graph."""

    description: str

    def __new__(cls, value: str, description: str):
        member = str.__new__(cls, value)
        member._value_ = value
        member.description = description
        return member

    ignore_non_customer_public_turn = (
        "ignore_non_customer_public_turn",
        "Inbound public customer message required.",
    )
    eligible_customer_public_turn = (
        "eligible_customer_public_turn",
        "Continue because the customer turn is eligible.",
    )
    stop_pre_model_policy_block = (
        "stop_pre_model_policy_block",
        "Stop before model call due to conversation policy.",
    )
    continue_policy_allows_model = (
        "continue_policy_allows_model",
        "Continue because pre-model policy allows it.",
    )
    stop_model_proposal_failed = (
        "stop_model_proposal_failed",
        "Stop because the model/provider did not propose.",
    )
    continue_proposal_generated = (
        "continue_proposal_generated",
        "Continue with the generated proposal.",
    )
    stop_post_model_policy_block = (
        "stop_post_model_policy_block",
        "Stop because proposal validation blocked it.",
    )
    queue_private_review_note = (
        "queue_private_review_note",
        "Queue a private review note instead of public text.",
    )
    continue_action_policy_approved = (
        "continue_action_policy_approved",
        "Continue because proposal validation passed.",
    )
    observe_only = (
        "observe_only",
        "Observe mode records the proposal only.",
    )
    stop_missing_model_proposal = (
        "stop_missing_model_proposal",
        "Stop if an approved path somehow lacks a proposal.",
    )
    queue_assist_private_note = (
        "queue_assist_private_note",
        "Assist mode and non-public proposals become private notes.",
    )
    queue_public_reply = (
        "queue_public_reply",
        "Public-reply mode may queue a customer-visible reply.",
    )


WORKFLOW_BRANCH_DESCRIPTIONS = {
    branch.value: branch.description for branch in WorkflowBranch
}
"""Human-readable branch descriptions used by generated workflow diagrams."""


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


def route_after_proposal(state: WorkflowState) -> WorkflowBranch:
    """Route after proposal generation succeeds or fails."""

    if "workflow_decision" in state:
        return WorkflowBranch.stop_model_proposal_failed
    return WorkflowBranch.continue_proposal_generated


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
