"""LangGraph support workflow."""

from __future__ import annotations

from enum import StrEnum
from inspect import getdoc
from typing import Annotated, NotRequired, TypedDict

from langgraph.graph import END, StateGraph

from wootpilot.application.policy import (
    pre_model_policy,
    triage_message,
    validate_proposal,
)
from wootpilot.domain.models import (
    AgentActionKind,
    AgentProposal,
    AgentRunStatus,
    BotMode,
    ConversationState,
    ModelProposalResult,
    NormalizedMessage,
    PolicyDecision,
    PolicyOutcome,
    StructuredCatalogContext,
    TriageResult,
    WorkflowDecision,
)
from wootpilot.domain.ports import ModelProposalPort
from wootpilot.time import Clock, IdGenerator

WORKFLOW_NODE_DESCRIPTIONS: dict[str, str] = {}
"""Human-readable node descriptions populated from graph node docstrings."""


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
    shadow_observe_only = (
        "shadow_observe_only",
        "Shadow mode records the proposal only.",
    )
    stop_missing_model_proposal = (
        "stop_missing_model_proposal",
        "Stop if an approved path somehow lacks a proposal.",
    )
    queue_copilot_or_private_note = (
        "queue_copilot_or_private_note",
        "Copilot/non-public proposals become private notes.",
    )
    queue_limited_auto_public_reply = (
        "queue_limited_auto_public_reply",
        "Limited auto may queue a public reply.",
    )


WORKFLOW_BRANCH_DESCRIPTIONS = {
    branch.value: branch.description for branch in WorkflowBranch
}
"""Human-readable branch descriptions used by generated workflow diagrams."""


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
    bot_mode: Annotated[
        BotMode,
        "Tenant/channel operating mode: shadow, copilot, or limited auto.",
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


def build_support_graph(
    *,
    model_port: ModelProposalPort,
    clock: Clock | None = None,
    ids: IdGenerator | None = None,
    checkpointer=None,
    suppress_public_auto_when_assigned: bool = True,
):
    clock = clock or Clock()
    ids = ids or IdGenerator()

    async def should_invoke(state: WorkflowState) -> dict:
        """Checks whether this message should run WootPilot."""

        message = state["normalized_message"]
        invoke = message.direction == "inbound" and message.visibility == "public"
        if invoke:
            return {}
        return {
            "workflow_decision": WorkflowDecision(
                status=AgentRunStatus.ignored,
                summary="Message is not an eligible public inbound customer turn.",
                rule_ids=["ingress.customer_public_inbound_required"],
            )
        }

    async def triage_node(state: WorkflowState) -> dict:
        """Classifies intent and risk signals from the customer text."""

        return {"triage_result": triage_message(state["normalized_message"])}

    async def policy_gate(state: WorkflowState) -> dict:
        """Applies deterministic pre-model conversation policy."""

        triage = state.get("triage_result")
        if triage is None:
            raise RuntimeError("policy_gate requires triage_result")
        decision = pre_model_policy(
            message=state["normalized_message"],
            state=state["conversation_state"],
            triage=triage,
            bot_mode=state["bot_mode"],
            suppress_public_auto_when_assigned=suppress_public_auto_when_assigned,
            now=clock.now(),
            ids=ids,
        )
        if decision.outcome is PolicyOutcome.block:
            return {
                "pre_model_policy_decision": decision,
                "workflow_decision": WorkflowDecision(
                    status=AgentRunStatus.blocked_by_policy,
                    summary="Pre-model policy blocked the workflow.",
                    rule_ids=decision.rule_ids,
                    risk_reasons=triage.risk_signals,
                ),
            }
        return {"pre_model_policy_decision": decision}

    async def llm_proposal(state: WorkflowState) -> dict:
        """Asks the model for a structured support action proposal."""

        result: ModelProposalResult = await model_port.propose(
            message=state["normalized_message"],
            conversation_state=state["conversation_state"],
            catalog_context=state["catalog_context"],
        )
        if result.retryable_error or result.permanent_error:
            return {
                "agent_proposal": None,
                "model_metadata": result.metadata,
                "provider_error": result.retryable_error or result.permanent_error,
                "workflow_decision": WorkflowDecision(
                    status=AgentRunStatus.failed,
                    summary="Model proposal failed.",
                    rule_ids=["model.proposal_failed"],
                    risk_reasons=[
                        result.retryable_error or result.permanent_error or "unknown"
                    ],
                ),
            }
        return {
            "agent_proposal": result.proposal,
            "model_metadata": result.metadata,
            "provider_error": None,
        }

    async def validate_outbound_action(state: WorkflowState) -> dict:
        """Checks the proposed action before any queueing."""

        proposal = state.get("agent_proposal")
        triage = state.get("triage_result")
        if triage is None:
            raise RuntimeError("validate_outbound_action requires triage_result")
        decision = validate_proposal(
            proposal=proposal,
            bot_mode=state["bot_mode"],
            triage=triage,
            catalog_context=state["catalog_context"],
            now=clock.now(),
            ids=ids,
        )
        if decision.outcome is PolicyOutcome.block:
            review_note = _limited_auto_review_note(
                proposal=proposal,
                bot_mode=state["bot_mode"],
                rule_ids=decision.rule_ids,
                triage=triage,
            )
            if review_note:
                return {
                    "post_model_policy_decision": decision,
                    "workflow_decision": WorkflowDecision(
                        status=AgentRunStatus.queued_action,
                        action_kind=AgentActionKind.private_note,
                        content=review_note,
                        summary="Public reply requires human review.",
                        rule_ids=decision.rule_ids,
                        risk_reasons=triage.risk_signals
                        + (proposal.risk_reasons if proposal else []),
                    ),
                }
            return {
                "post_model_policy_decision": decision,
                "workflow_decision": WorkflowDecision(
                    status=AgentRunStatus.blocked_by_policy,
                    summary="Post-model policy blocked the proposed action.",
                    rule_ids=decision.rule_ids,
                    risk_reasons=proposal.risk_reasons if proposal else [],
                ),
            }
        return {"post_model_policy_decision": decision}

    async def route_final_decision(state: WorkflowState) -> dict:
        """Chooses the final non-sending, note, or public action.

        This node intentionally returns no state. It exists so the final routing
        choice is visible in LangGraph topology diagrams.
        """

        return {}

    async def build_shadow_decision(state: WorkflowState) -> dict:
        """Records a proposal without creating an outbound action."""

        proposal = state.get("agent_proposal")
        if proposal is None:
            return await build_missing_proposal_failure(state)
        return {
            "workflow_decision": WorkflowDecision(
                status=AgentRunStatus.proposed,
                action_kind=AgentActionKind.none,
                summary=proposal.summary,
                risk_reasons=proposal.risk_reasons,
            )
        }

    async def build_private_note_action(state: WorkflowState) -> dict:
        """Queues an internal note for a human agent."""

        proposal = state.get("agent_proposal")
        if proposal is None:
            return await build_missing_proposal_failure(state)
        content = proposal.private_note or proposal.public_message or proposal.summary
        return {
            "workflow_decision": WorkflowDecision(
                status=AgentRunStatus.queued_action,
                action_kind=AgentActionKind.private_note,
                content=content,
                summary=proposal.summary,
                risk_reasons=proposal.risk_reasons,
            )
        }

    async def build_public_message_action(state: WorkflowState) -> dict:
        """Queues a customer-visible reply for delivery."""

        proposal = state.get("agent_proposal")
        if proposal is None:
            return await build_missing_proposal_failure(state)
        return {
            "workflow_decision": WorkflowDecision(
                status=AgentRunStatus.queued_action,
                action_kind=AgentActionKind.public_message,
                content=proposal.public_message,
                summary=proposal.summary,
                risk_reasons=proposal.risk_reasons,
            )
        }

    async def build_missing_proposal_failure(state: WorkflowState) -> dict:
        return {
            "workflow_decision": WorkflowDecision(
                status=AgentRunStatus.failed,
                summary="No proposal was available after validation.",
                rule_ids=["model.no_proposal"],
            )
        }

    async def build_missing_proposal_failure_node(
        state: WorkflowState,
    ) -> dict:
        """Fails defensively if no model proposal exists."""

        return await build_missing_proposal_failure(state)

    def route_after_invoke(state: WorkflowState) -> WorkflowBranch:
        if "workflow_decision" in state:
            return WorkflowBranch.ignore_non_customer_public_turn
        return WorkflowBranch.eligible_customer_public_turn

    def route_after_policy(state: WorkflowState) -> WorkflowBranch:
        if "workflow_decision" in state:
            return WorkflowBranch.stop_pre_model_policy_block
        return WorkflowBranch.continue_policy_allows_model

    def route_after_llm(state: WorkflowState) -> WorkflowBranch:
        if "workflow_decision" in state:
            return WorkflowBranch.stop_model_proposal_failed
        return WorkflowBranch.continue_model_proposed_action

    def route_after_validate(state: WorkflowState) -> WorkflowBranch:
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
        proposal = state.get("agent_proposal")
        if state["bot_mode"] is BotMode.shadow:
            return WorkflowBranch.shadow_observe_only
        if proposal is None:
            return WorkflowBranch.stop_missing_model_proposal
        if (
            state["bot_mode"] is BotMode.copilot
            or proposal.action_kind is not AgentActionKind.public_message
        ):
            return WorkflowBranch.queue_copilot_or_private_note
        return WorkflowBranch.queue_limited_auto_public_reply

    _sync_node_descriptions(
        {
            "should_invoke": should_invoke,
            "triage_message": triage_node,
            "policy_gate": policy_gate,
            "llm_proposal": llm_proposal,
            "validate_outbound_action": validate_outbound_action,
            "route_final_decision": route_final_decision,
            "build_shadow_decision": build_shadow_decision,
            "build_private_note_action": build_private_note_action,
            "build_public_message_action": build_public_message_action,
            "build_missing_proposal_failure": build_missing_proposal_failure_node,
        }
    )

    graph = StateGraph(WorkflowState)
    graph.add_node("should_invoke", should_invoke)
    graph.add_node("triage_message", triage_node)
    graph.add_node("policy_gate", policy_gate)
    graph.add_node("llm_proposal", llm_proposal)
    graph.add_node("validate_outbound_action", validate_outbound_action)
    graph.add_node("route_final_decision", route_final_decision)
    graph.add_node("build_shadow_decision", build_shadow_decision)
    graph.add_node("build_private_note_action", build_private_note_action)
    graph.add_node("build_public_message_action", build_public_message_action)
    graph.add_node(
        "build_missing_proposal_failure",
        build_missing_proposal_failure_node,
    )
    graph.set_entry_point("should_invoke")
    graph.add_conditional_edges(
        "should_invoke",
        route_after_invoke,
        {
            WorkflowBranch.ignore_non_customer_public_turn: END,
            WorkflowBranch.eligible_customer_public_turn: "triage_message",
        },
    )
    graph.add_edge("triage_message", "policy_gate")
    graph.add_conditional_edges(
        "policy_gate",
        route_after_policy,
        {
            WorkflowBranch.stop_pre_model_policy_block: END,
            WorkflowBranch.continue_policy_allows_model: "llm_proposal",
        },
    )
    graph.add_conditional_edges(
        "llm_proposal",
        route_after_llm,
        {
            WorkflowBranch.stop_model_proposal_failed: END,
            WorkflowBranch.continue_model_proposed_action: "validate_outbound_action",
        },
    )
    graph.add_conditional_edges(
        "validate_outbound_action",
        route_after_validate,
        {
            WorkflowBranch.stop_post_model_policy_block: END,
            WorkflowBranch.queue_private_review_note: END,
            WorkflowBranch.continue_action_policy_approved: "route_final_decision",
        },
    )
    graph.add_conditional_edges(
        "route_final_decision",
        route_after_final_decision,
        {
            WorkflowBranch.shadow_observe_only: "build_shadow_decision",
            WorkflowBranch.stop_missing_model_proposal: (
                "build_missing_proposal_failure"
            ),
            WorkflowBranch.queue_copilot_or_private_note: "build_private_note_action",
            WorkflowBranch.queue_limited_auto_public_reply: (
                "build_public_message_action"
            ),
        },
    )
    graph.add_edge("build_shadow_decision", END)
    graph.add_edge("build_private_note_action", END)
    graph.add_edge("build_public_message_action", END)
    graph.add_edge("build_missing_proposal_failure", END)
    return graph.compile(checkpointer=checkpointer)


def _sync_node_descriptions(nodes: dict[str, object]) -> None:
    """Refresh diagram node descriptions from the graph node docstrings."""

    WORKFLOW_NODE_DESCRIPTIONS.clear()
    for name, node in nodes.items():
        description = getdoc(node)
        if description is None:
            raise RuntimeError(f"Support workflow node {name!r} needs a docstring")
        WORKFLOW_NODE_DESCRIPTIONS[name] = description.splitlines()[0]


def _limited_auto_review_note(
    *,
    proposal: AgentProposal | None,
    bot_mode: BotMode,
    rule_ids: list[str],
    triage: TriageResult,
) -> str | None:
    """Build a private handoff note when public auto-send is denied.

    The unsafe public draft is intentionally not copied into the note. A human
    gets the review reason and model summary, while customer-visible text still
    requires human composition inside Chatwoot.
    """

    if bot_mode is not BotMode.limited_auto or proposal is None:
        return None
    if proposal.action_kind is not AgentActionKind.public_message:
        return None
    reasons = sorted(set(rule_ids + triage.risk_signals + proposal.risk_reasons))
    lines = [
        "WootPilot did not send a public reply because this turn needs human review.",
        f"Summary: {proposal.summary}",
    ]
    if reasons:
        lines.append(f"Review reasons: {', '.join(reasons)}")
    return "\n".join(lines)
