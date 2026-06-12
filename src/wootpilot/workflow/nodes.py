"""Node behavior for the customer-support workflow graph."""

from __future__ import annotations

from dataclasses import dataclass

from wootpilot.application.policy import (
    pre_model_policy,
    triage_message,
    validate_proposal,
)
from wootpilot.domain.models import ModelProposalResult, PolicyOutcome
from wootpilot.domain.ports import ModelProposalPort
from wootpilot.time import Clock, IdGenerator
from wootpilot.workflow.decisions import (
    missing_model_proposal_decision,
    model_proposal_failed_decision,
    non_customer_turn_decision,
    observe_decision,
    post_model_policy_blocked_decision,
    pre_model_policy_blocked_decision,
    private_note_decision,
    public_message_decision,
    public_reply_review_decision,
    public_reply_review_note,
)
from wootpilot.workflow.state import WorkflowState

__all__ = ["WorkflowNodes"]


@dataclass(frozen=True)
class WorkflowNodes:
    """Executable node collection for one compiled support workflow graph."""

    proposal_generator: ModelProposalPort
    clock: Clock
    ids: IdGenerator

    async def should_invoke(self, state: WorkflowState) -> dict:
        """Checks whether this message should run WootPilot."""

        message = state["normalized_message"]
        if message.is_customer_public_inbound():
            return {}
        return {"workflow_decision": non_customer_turn_decision()}

    async def triage_message(self, state: WorkflowState) -> dict:
        """Classifies intent and risk signals from the customer text."""

        return {"triage_result": triage_message(state["normalized_message"])}

    async def policy_gate(self, state: WorkflowState) -> dict:
        """Applies deterministic pre-model conversation policy."""

        triage = state.get("triage_result")
        if triage is None:
            raise RuntimeError("policy_gate requires triage_result")
        decision = pre_model_policy(
            message=state["normalized_message"],
            state=state["conversation_state"],
            triage=triage,
            automation_mode=state["automation_mode"],
            now=self.clock.now(),
            ids=self.ids,
        )
        if decision.outcome is PolicyOutcome.block:
            return {
                "pre_model_policy_decision": decision,
                "workflow_decision": pre_model_policy_blocked_decision(
                    decision=decision,
                    triage=triage,
                ),
            }
        return {"pre_model_policy_decision": decision}

    async def generate_proposal(self, state: WorkflowState) -> dict:
        """Generates a structured support action proposal."""

        result: ModelProposalResult = await self.proposal_generator.propose(
            message=state["normalized_message"],
            conversation_state=state["conversation_state"],
            catalog_context=state["catalog_context"],
        )
        provider_error = result.retryable_error or result.permanent_error
        if provider_error:
            return {
                "agent_proposal": None,
                "model_metadata": result.metadata,
                "provider_error": provider_error,
                "workflow_decision": model_proposal_failed_decision(provider_error),
            }
        return {
            "agent_proposal": result.proposal,
            "model_metadata": result.metadata,
            "provider_error": None,
        }

    async def validate_outbound_action(self, state: WorkflowState) -> dict:
        """Checks the proposed action before any queueing."""

        proposal = state.get("agent_proposal")
        triage = state.get("triage_result")
        if triage is None:
            raise RuntimeError("validate_outbound_action requires triage_result")
        decision = validate_proposal(
            proposal=proposal,
            automation_mode=state["automation_mode"],
            triage=triage,
            catalog_context=state["catalog_context"],
            now=self.clock.now(),
            ids=self.ids,
        )
        if decision.outcome is PolicyOutcome.block:
            review_note = public_reply_review_note(
                proposal=proposal,
                automation_mode=state["automation_mode"],
                rule_ids=decision.rule_ids,
                triage=triage,
            )
            if review_note:
                return {
                    "post_model_policy_decision": decision,
                    "workflow_decision": public_reply_review_decision(
                        proposal=proposal,
                        decision=decision,
                        triage=triage,
                        note=review_note,
                    ),
                }
            return {
                "post_model_policy_decision": decision,
                "workflow_decision": post_model_policy_blocked_decision(
                    proposal=proposal,
                    decision=decision,
                ),
            }
        return {"post_model_policy_decision": decision}

    async def route_final_decision(self, state: WorkflowState) -> dict:
        """Chooses the final non-sending, note, or public action.

        This node intentionally returns no state. It exists so the final routing
        choice is visible in LangGraph topology diagrams.
        """

        return {}

    async def build_observe_decision(self, state: WorkflowState) -> dict:
        """Records a proposal without creating an outbound action."""

        proposal = state.get("agent_proposal")
        if proposal is None:
            return await self.build_missing_proposal_failure(state)
        return {"workflow_decision": observe_decision(proposal)}

    async def build_private_note_action(self, state: WorkflowState) -> dict:
        """Queues an internal note for a human agent."""

        proposal = state.get("agent_proposal")
        if proposal is None:
            return await self.build_missing_proposal_failure(state)
        return {"workflow_decision": private_note_decision(proposal)}

    async def build_public_message_action(self, state: WorkflowState) -> dict:
        """Queues a customer-visible reply for delivery."""

        proposal = state.get("agent_proposal")
        if proposal is None:
            return await self.build_missing_proposal_failure(state)
        return {"workflow_decision": public_message_decision(proposal)}

    async def build_missing_proposal_failure(self, state: WorkflowState) -> dict:
        """Fails defensively if no model proposal exists."""

        return {"workflow_decision": missing_model_proposal_decision()}
