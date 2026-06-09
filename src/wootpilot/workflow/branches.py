"""Named routes used by the customer-support workflow graph."""

from __future__ import annotations

from enum import StrEnum

__all__ = ["WORKFLOW_BRANCH_DESCRIPTIONS", "WorkflowBranch"]


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
    continue_model_proposed_action = (
        "continue_model_proposed_action",
        "Continue with the model's proposed action.",
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
