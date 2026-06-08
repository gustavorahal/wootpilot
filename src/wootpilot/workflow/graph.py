"""LangGraph support workflow.

Stable state keys:
normalized_message, conversation_state, catalog_context, bot_mode,
triage_result, pre_model_policy_decision, agent_proposal, model_metadata,
post_model_policy_decision, workflow_decision.
"""

from __future__ import annotations

from typing import NotRequired, TypedDict

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


class SupportWorkflowState(TypedDict):
    normalized_message: NormalizedMessage
    conversation_state: ConversationState
    catalog_context: StructuredCatalogContext
    bot_mode: BotMode
    triage_result: NotRequired[TriageResult]
    pre_model_policy_decision: NotRequired[PolicyDecision]
    agent_proposal: NotRequired[AgentProposal | None]
    model_metadata: NotRequired[dict]
    provider_error: NotRequired[str | None]
    post_model_policy_decision: NotRequired[PolicyDecision]
    workflow_decision: NotRequired[WorkflowDecision]


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

    async def should_invoke(state: SupportWorkflowState) -> dict:
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

    async def triage_node(state: SupportWorkflowState) -> dict:
        return {"triage_result": triage_message(state["normalized_message"])}

    async def policy_gate(state: SupportWorkflowState) -> dict:
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

    async def llm_proposal(state: SupportWorkflowState) -> dict:
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

    async def validate_outbound_action(state: SupportWorkflowState) -> dict:
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

    async def build_workflow_decision(state: SupportWorkflowState) -> dict:
        proposal = state.get("agent_proposal")
        if proposal is None:
            return {
                "workflow_decision": WorkflowDecision(
                    status=AgentRunStatus.failed,
                    summary="No proposal was available after validation.",
                    rule_ids=["model.no_proposal"],
                )
            }
        bot_mode = state["bot_mode"]
        if bot_mode is BotMode.shadow:
            return {
                "workflow_decision": WorkflowDecision(
                    status=AgentRunStatus.proposed,
                    action_kind=AgentActionKind.none,
                    summary=proposal.summary,
                    risk_reasons=proposal.risk_reasons,
                )
            }
        if (
            bot_mode is BotMode.copilot
            or proposal.action_kind is not AgentActionKind.public_message
        ):
            content = (
                proposal.private_note or proposal.public_message or proposal.summary
            )
            return {
                "workflow_decision": WorkflowDecision(
                    status=AgentRunStatus.queued_action,
                    action_kind=AgentActionKind.private_note,
                    content=content,
                    summary=proposal.summary,
                    risk_reasons=proposal.risk_reasons,
                )
            }
        return {
            "workflow_decision": WorkflowDecision(
                status=AgentRunStatus.queued_action,
                action_kind=AgentActionKind.public_message,
                content=proposal.public_message,
                summary=proposal.summary,
                risk_reasons=proposal.risk_reasons,
            )
        }

    def route_after_invoke(state: SupportWorkflowState) -> str:
        return END if "workflow_decision" in state else "triage_message"

    def route_after_policy(state: SupportWorkflowState) -> str:
        return END if "workflow_decision" in state else "llm_proposal"

    def route_after_llm(state: SupportWorkflowState) -> str:
        return END if "workflow_decision" in state else "validate_outbound_action"

    def route_after_validate(state: SupportWorkflowState) -> str:
        return END if "workflow_decision" in state else "build_workflow_decision"

    graph = StateGraph(SupportWorkflowState)
    graph.add_node("should_invoke", should_invoke)
    graph.add_node("triage_message", triage_node)
    graph.add_node("policy_gate", policy_gate)
    graph.add_node("llm_proposal", llm_proposal)
    graph.add_node("validate_outbound_action", validate_outbound_action)
    graph.add_node("build_workflow_decision", build_workflow_decision)
    graph.set_entry_point("should_invoke")
    graph.add_conditional_edges("should_invoke", route_after_invoke)
    graph.add_edge("triage_message", "policy_gate")
    graph.add_conditional_edges("policy_gate", route_after_policy)
    graph.add_conditional_edges("llm_proposal", route_after_llm)
    graph.add_conditional_edges("validate_outbound_action", route_after_validate)
    graph.add_edge("build_workflow_decision", END)
    return graph.compile(checkpointer=checkpointer)


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
