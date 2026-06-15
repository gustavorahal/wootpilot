"""Node behavior for the customer-support workflow graph."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from langgraph.types import Command

from wootpilot.application.policy import (
    pre_model_policy,
    triage_message,
    validate_proposal,
)
from wootpilot.domain.models import (
    AgentActionKind,
    AutomationMode,
    ModelProposalResult,
    PolicyOutcome,
)
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

END_NODE: Literal["__end__"] = "__end__"


@dataclass(frozen=True)
class WorkflowNodes:
    """Executable node collection for one compiled support workflow graph."""

    proposal_generator: ModelProposalPort
    clock: Clock
    ids: IdGenerator

    async def should_invoke(
        self,
        state: WorkflowState,
    ) -> Command[Literal["triage_message", "__end__"]]:
        """Checks whether this message should run WootPilot."""

        message = state["normalized_message"]
        if message.is_customer_public_inbound():
            return Command(update={}, goto="triage_message")
        return Command(
            update={"workflow_decision": non_customer_turn_decision()},
            goto=END_NODE,
        )

    async def triage_message(self, state: WorkflowState) -> dict[str, object]:
        """Classifies intent and risk signals from the customer text."""

        return {"triage_result": triage_message(state["normalized_message"])}

    async def policy_gate(
        self,
        state: WorkflowState,
    ) -> Command[Literal["generate_proposal", "__end__"]]:
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
            return Command(
                update={
                    "pre_model_policy_decision": decision,
                    "workflow_decision": pre_model_policy_blocked_decision(
                        decision=decision,
                        triage=triage,
                    ),
                },
                goto=END_NODE,
            )
        return Command(
            update={"pre_model_policy_decision": decision},
            goto="generate_proposal",
        )

    async def generate_proposal(
        self,
        state: WorkflowState,
    ) -> Command[Literal["validate_outbound_action", "__end__"]]:
        """Generates a structured support action proposal."""

        result: ModelProposalResult = await self.proposal_generator.propose(
            message=state["normalized_message"],
            conversation_state=state["conversation_state"],
            catalog_context=state["catalog_context"],
        )
        provider_error = result.retryable_error or result.permanent_error
        if provider_error:
            return Command(
                update={
                    "agent_proposal": None,
                    "model_metadata": result.metadata,
                    "provider_error": provider_error,
                    "workflow_decision": model_proposal_failed_decision(
                        provider_error
                    ),
                },
                goto=END_NODE,
            )
        return Command(
            update={
                "agent_proposal": result.proposal,
                "model_metadata": result.metadata,
                "provider_error": None,
            },
            goto="validate_outbound_action",
        )

    async def validate_outbound_action(
        self,
        state: WorkflowState,
    ) -> Command[
        Literal[
            "build_observe_decision",
            "build_private_note_action",
            "build_public_message_action",
            "build_missing_proposal_failure",
            "__end__",
        ]
    ]:
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
                return Command(
                    update={
                        "post_model_policy_decision": decision,
                        "workflow_decision": public_reply_review_decision(
                            proposal=proposal,
                            decision=decision,
                            triage=triage,
                            note=review_note,
                        ),
                    },
                    goto=END_NODE,
                )
            return Command(
                update={
                    "post_model_policy_decision": decision,
                    "workflow_decision": post_model_policy_blocked_decision(
                        proposal=proposal,
                        decision=decision,
                    ),
                },
                goto=END_NODE,
            )
        return Command(
            update={"post_model_policy_decision": decision},
            goto=_final_decision_destination(state),
        )

    async def build_observe_decision(
        self,
        state: WorkflowState,
    ) -> dict[str, object]:
        """Records a proposal without creating an outbound action."""

        proposal = state.get("agent_proposal")
        if proposal is None:
            return await self.build_missing_proposal_failure(state)
        return {"workflow_decision": observe_decision(proposal)}

    async def build_private_note_action(
        self,
        state: WorkflowState,
    ) -> dict[str, object]:
        """Queues an internal note for a human agent."""

        proposal = state.get("agent_proposal")
        if proposal is None:
            return await self.build_missing_proposal_failure(state)
        return {"workflow_decision": private_note_decision(proposal)}

    async def build_public_message_action(
        self,
        state: WorkflowState,
    ) -> dict[str, object]:
        """Queues a customer-visible reply for delivery."""

        proposal = state.get("agent_proposal")
        if proposal is None:
            return await self.build_missing_proposal_failure(state)
        return {"workflow_decision": public_message_decision(proposal)}

    async def build_missing_proposal_failure(
        self,
        state: WorkflowState,
    ) -> dict[str, object]:
        """Fails defensively if no model proposal exists."""

        return {"workflow_decision": missing_model_proposal_decision()}


def _final_decision_destination(
    state: WorkflowState,
) -> Literal[
    "build_observe_decision",
    "build_private_note_action",
    "build_public_message_action",
    "build_missing_proposal_failure",
]:
    """Choose the final observe, private-note, or public-reply builder."""

    proposal = state.get("agent_proposal")
    if state["automation_mode"] is AutomationMode.observe:
        return "build_observe_decision"
    if proposal is None:
        return "build_missing_proposal_failure"
    if (
        state["automation_mode"] is AutomationMode.assist
        or proposal.action_kind is not AgentActionKind.public_message
    ):
        return "build_private_note_action"
    return "build_public_message_action"
