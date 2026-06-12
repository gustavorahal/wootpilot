"""LangGraph topology for the customer-support workflow.

The workflow package is split by reading concern:

- Workflow vocabulary lives in `state.py` and `branches.py`.
- Node behavior lives in `nodes.py`: what each workflow step does.
- Routing behavior lives in `routing.py`: which path comes next.
- Decision construction lives in `decisions.py`: how final outcomes are shaped.
- Graph assembly lives here in `graph.py`: LangGraph node and edge wiring.

This module intentionally keeps only the assembly layer so the central workflow
map stays easy to scan before readers jump into state, nodes, routing, or
decision helpers.
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from wootpilot.domain.ports import ModelProposalPort
from wootpilot.time import Clock, IdGenerator
from wootpilot.workflow.branches import (
    WORKFLOW_BRANCH_DESCRIPTIONS,
    WorkflowBranch,
)
from wootpilot.workflow.nodes import WorkflowNodes
from wootpilot.workflow.routing import (
    route_after_final_decision,
    route_after_invoke,
    route_after_llm,
    route_after_policy,
    route_after_validate,
)
from wootpilot.workflow.state import WorkflowState

__all__ = [
    "WORKFLOW_BRANCH_DESCRIPTIONS",
    "WorkflowBranch",
    "WorkflowState",
    "build_graph",
]

def build_graph(
    *,
    model_port: ModelProposalPort,
    clock: Clock | None = None,
    ids: IdGenerator | None = None,
    checkpointer=None,
):
    """Build the compiled LangGraph workflow used by application services.

    This module intentionally reads like a map: node behavior, routing
    decisions, branch vocabulary, and state contracts live in focused sibling
    modules so the central graph topology stays easy to scan.
    """

    nodes = WorkflowNodes(
        model_port=model_port,
        clock=clock or Clock(),
        ids=ids or IdGenerator(),
    )

    graph = StateGraph(WorkflowState)
    graph.add_node("should_invoke", nodes.should_invoke)
    graph.add_node("triage_message", nodes.triage_message)
    graph.add_node("policy_gate", nodes.policy_gate)
    graph.add_node("llm_proposal", nodes.llm_proposal)
    graph.add_node("validate_outbound_action", nodes.validate_outbound_action)
    graph.add_node("route_final_decision", nodes.route_final_decision)
    graph.add_node("build_observe_decision", nodes.build_observe_decision)
    graph.add_node("build_private_note_action", nodes.build_private_note_action)
    graph.add_node("build_public_message_action", nodes.build_public_message_action)
    graph.add_node(
        "build_missing_proposal_failure",
        nodes.build_missing_proposal_failure,
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
            WorkflowBranch.observe_only: "build_observe_decision",
            WorkflowBranch.stop_missing_model_proposal: (
                "build_missing_proposal_failure"
            ),
            WorkflowBranch.queue_assist_private_note: "build_private_note_action",
            WorkflowBranch.queue_public_reply: "build_public_message_action",
        },
    )
    graph.add_edge("build_observe_decision", END)
    graph.add_edge("build_private_note_action", END)
    graph.add_edge("build_public_message_action", END)
    graph.add_edge("build_missing_proposal_failure", END)
    return graph.compile(checkpointer=checkpointer)
