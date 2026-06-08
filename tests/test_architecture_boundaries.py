from __future__ import annotations

import ast
from pathlib import Path


def test_domain_package_has_no_outer_layer_imports() -> None:
    forbidden_prefixes = {
        "fastapi",
        "httpx",
        "sqlalchemy",
        "langchain",
        "langchain_openrouter",
        "langgraph",
        "wootpilot.api",
        "wootpilot.application",
        "wootpilot.catalog",
        "wootpilot.integrations",
        "wootpilot.persistence",
        "wootpilot.workflow",
    }

    violations = _import_violations(
        Path("src/wootpilot/domain"),
        forbidden_prefixes=forbidden_prefixes,
    )

    assert violations == []


def test_langgraph_workflow_module_does_not_import_side_effect_adapters() -> None:
    forbidden_prefixes = {
        "wootpilot.api",
        "wootpilot.catalog",
        "wootpilot.integrations.chatwoot",
        "wootpilot.persistence",
        "sqlalchemy",
        "httpx",
    }

    violations = _import_violations(
        Path("src/wootpilot/workflow"),
        forbidden_prefixes=forbidden_prefixes,
    )

    assert violations == []


def _import_violations(
    root: Path,
    *,
    forbidden_prefixes: set[str],
) -> list[dict[str, str | int]]:
    violations = []
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            imported_modules = []
            if isinstance(node, ast.Import):
                imported_modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported_modules = [node.module or ""]
            else:
                continue
            for module in imported_modules:
                if any(
                    module == prefix or module.startswith(f"{prefix}.")
                    for prefix in forbidden_prefixes
                ):
                    violations.append(
                        {
                            "path": str(path),
                            "line": node.lineno,
                            "module": module,
                        }
                    )
    return violations
