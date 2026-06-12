"""Render the WootPilot support workflow graph documentation artifacts.

The Mermaid source is committed because it is reviewable in diffs. The PNG is
also committed because many Markdown renderers and repository browsers display
image files more reliably than Mermaid diagrams.
"""

from __future__ import annotations

from html import escape
from inspect import getdoc
from pathlib import Path

from langchain_core.runnables.graph import MermaidDrawMethod
from langchain_core.runnables.graph_mermaid import draw_mermaid_png

from wootpilot.domain.models import ModelProposalResult
from wootpilot.time import Clock, IdGenerator
from wootpilot.workflow.graph import build_graph
from wootpilot.workflow.nodes import WorkflowNodes
from wootpilot.workflow.routes import WORKFLOW_BRANCH_DESCRIPTIONS

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DOCS = ROOT / "docs" / "reference"
MERMAID_PATH = REFERENCE_DOCS / "support-workflow-graph.mmd"
PNG_PATH = REFERENCE_DOCS / "support-workflow-graph.png"
WORKFLOW_NODE_DESCRIPTIONS: dict[str, str] = {}
"""Node descriptions used only while rendering workflow documentation."""


class DiagramProposalGenerator:
    """Minimal proposal generator for compiling graph documentation."""

    async def propose(self, **kwargs) -> ModelProposalResult:
        raise RuntimeError("Diagram rendering compiles the graph but never invokes it.")


def main() -> None:
    proposal_generator = DiagramProposalGenerator()
    sync_node_descriptions_for_diagram(proposal_generator)
    graph = build_graph(proposal_generator=proposal_generator).get_graph()
    mermaid = _annotate_mermaid(graph.draw_mermaid())
    MERMAID_PATH.write_text(mermaid, encoding="utf-8")
    PNG_PATH.write_bytes(
        draw_mermaid_png(
            mermaid,
            draw_method=MermaidDrawMethod.API,
        )
    )
    print(f"Wrote {MERMAID_PATH.relative_to(ROOT)}")
    print(f"Wrote {PNG_PATH.relative_to(ROOT)}")


def _annotate_mermaid(mermaid: str) -> str:
    """Add source-controlled descriptions to LangGraph's generated Mermaid."""

    lines = [_annotate_node_line(line) for line in mermaid.splitlines()]
    annotated = "\n".join(lines)
    for branch, description in WORKFLOW_BRANCH_DESCRIPTIONS.items():
        label = f"-. &nbsp;{branch}&nbsp; .->"
        rich_label = f'-. "{branch}<br/>{escape(description, quote=False)}" .->'
        annotated = annotated.replace(label, rich_label)
    return annotated + "\n"


def sync_node_descriptions_for_diagram(
    proposal_generator: DiagramProposalGenerator,
) -> None:
    """Refresh Mermaid node descriptions from workflow node docstrings."""

    nodes = WorkflowNodes(
        proposal_generator=proposal_generator,
        clock=Clock(),
        ids=IdGenerator(),
    )
    WORKFLOW_NODE_DESCRIPTIONS.clear()
    for name, node in {
        "should_invoke": nodes.should_invoke,
        "triage_message": nodes.triage_message,
        "policy_gate": nodes.policy_gate,
        "generate_proposal": nodes.generate_proposal,
        "validate_outbound_action": nodes.validate_outbound_action,
        "route_final_decision": nodes.route_final_decision,
        "build_observe_decision": nodes.build_observe_decision,
        "build_private_note_action": nodes.build_private_note_action,
        "build_public_message_action": nodes.build_public_message_action,
        "build_missing_proposal_failure": nodes.build_missing_proposal_failure,
    }.items():
        description = getdoc(node)
        if description is None:
            raise RuntimeError(f"Support workflow node {name!r} needs a docstring")
        WORKFLOW_NODE_DESCRIPTIONS[name] = description.splitlines()[0]


def _annotate_node_line(line: str) -> str:
    for node, description in WORKFLOW_NODE_DESCRIPTIONS.items():
        plain_definition = f"\t{node}({node})"
        if line == plain_definition:
            label = f"{node}<br/>{escape(description, quote=False)}"
            return f'\t{node}("{label}")'
    return line


if __name__ == "__main__":
    main()
