"""LangGraph topology for the customer-support workflow.

The workflow package is split by reading concern:

- Workflow state lives in `state.py`.
- Node behavior lives in `nodes.py`: what each workflow step does.
- Decision construction lives in `decisions.py`: how final outcomes are shaped.
- Graph assembly lives here in `graph.py`: LangGraph node and edge wiring.

This module intentionally keeps only the assembly layer so the central workflow
map stays easy to scan before readers jump into state, nodes, or decision
helpers.
"""

from __future__ import annotations

from langgraph.graph import START, StateGraph

from wootpilot.domain.ports import ModelProposalPort
from wootpilot.time import Clock, IdGenerator
from wootpilot.workflow.nodes import WorkflowNodes
from wootpilot.workflow.state import (
    WorkflowInputState,
    WorkflowOutputState,
    WorkflowState,
)

__all__ = [
    "WorkflowInputState",
    "WorkflowOutputState",
    "WorkflowState",
    "build_graph",
]


def build_graph(
    *,
    proposal_generator: ModelProposalPort,
    clock: Clock | None = None,
    ids: IdGenerator | None = None,
    checkpointer=None,
):
    """Build the compiled LangGraph workflow used by application services.

    This module intentionally reads like a map: node behavior, routing
    decisions and state contracts live in focused sibling modules so the
    central graph topology stays easy to scan.
    """

    nodes = WorkflowNodes(
        proposal_generator=proposal_generator,
        clock=clock or Clock(),
        ids=ids or IdGenerator(),
    )

    graph = StateGraph(
        WorkflowState,
        input_schema=WorkflowInputState,
        output_schema=WorkflowOutputState,
    )
    graph.add_node("should_invoke", nodes.should_invoke)
    graph.add_node("triage_message", nodes.triage_message)
    graph.add_node("policy_gate", nodes.policy_gate)
    graph.add_node("generate_proposal", nodes.generate_proposal)
    graph.add_node("validate_outbound_action", nodes.validate_outbound_action)

    graph.add_edge(START, "should_invoke")
    graph.add_edge("triage_message", "policy_gate")
    return graph.compile(checkpointer=checkpointer)
