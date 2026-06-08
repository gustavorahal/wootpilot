"""Render the WootPilot support workflow graph documentation artifacts.

The Mermaid source is committed because it is reviewable in diffs. The PNG is
also committed because many Markdown renderers and repository browsers display
image files more reliably than Mermaid diagrams.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from langchain_core.runnables.graph import MermaidDrawMethod
from langchain_core.runnables.graph_mermaid import draw_mermaid_png

from wootpilot.domain.models import ModelProposalResult
from wootpilot.workflow.graph import (
    WORKFLOW_BRANCH_DESCRIPTIONS,
    WORKFLOW_NODE_DESCRIPTIONS,
    build_support_graph,
)

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DOCS = ROOT / "docs" / "reference"
MERMAID_PATH = REFERENCE_DOCS / "support-workflow-graph.mmd"
PNG_PATH = REFERENCE_DOCS / "support-workflow-graph.png"


class DiagramModelPort:
    """Minimal model port for compiling the graph without provider credentials."""

    async def propose(self, **kwargs) -> ModelProposalResult:
        raise RuntimeError("Diagram rendering compiles the graph but never invokes it.")


def main() -> None:
    graph = build_support_graph(model_port=DiagramModelPort()).get_graph()
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


def _annotate_node_line(line: str) -> str:
    for node, description in WORKFLOW_NODE_DESCRIPTIONS.items():
        plain_definition = f"\t{node}({node})"
        if line == plain_definition:
            label = f"{node}<br/>{escape(description, quote=False)}"
            return f'\t{node}("{label}")'
    return line


if __name__ == "__main__":
    main()
