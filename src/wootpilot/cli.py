"""Small operational CLI for local development."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from wootpilot.application.outbound import ExecuteOutboundActions
from wootpilot.catalog.factory import catalog_connector_from_settings
from wootpilot.evals.golden import load_golden_cases, run_golden_case
from wootpilot.observability import configure_langsmith
from wootpilot.persistence.database import init_database, make_session_factory
from wootpilot.settings import Settings, get_settings

__all__ = ["main"]


def main() -> None:
    """Run local operational commands for database, catalog, and workflow checks."""

    parser = argparse.ArgumentParser(prog="wootpilot")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db")
    execute = sub.add_parser("execute-outbound")
    execute.add_argument("--limit", type=int, default=10)
    eval_golden = sub.add_parser("eval-golden")
    eval_golden.add_argument(
        "--fixture",
        default="tests/fixtures/golden/conversations.json",
    )
    search = sub.add_parser("catalog-search")
    search.add_argument("query")
    args = parser.parse_args()
    settings = get_settings()
    configure_langsmith(settings)
    if args.command == "init-db":
        asyncio.run(init_database(settings))
        print("database initialized")
    elif args.command == "execute-outbound":
        counts = asyncio.run(_execute_outbound(settings, args.limit))
        print(
            f"sent={counts['sent']} blocked={counts['blocked']} "
            f"failed={counts['failed']}"
        )
    elif args.command == "catalog-search":
        asyncio.run(_catalog_search(settings, args.query))
    elif args.command == "eval-golden":
        raise SystemExit(asyncio.run(_eval_golden(Path(args.fixture))))


async def _execute_outbound(settings: Settings, limit: int) -> dict[str, int]:
    """Execute queued outbound actions from the CLI using configured settings."""

    factory = make_session_factory(settings)
    async with factory() as session:
        executor = ExecuteOutboundActions(settings=settings, session=session)
        counts = await executor.run_once(limit=limit)
        await session.commit()
        return counts


async def _catalog_search(settings: Settings, query: str) -> None:
    """Print a compact catalog search result for local connector debugging."""

    result = await catalog_connector_from_settings(settings).search(query)
    for product in result.products:
        print(f"{product.name} | {product.sku or '-'} | {product.permalink or '-'}")


async def _eval_golden(path: Path) -> int:
    """Run golden conversation fixtures and return a process exit code."""

    failures = []
    for case in load_golden_cases(path):
        result = await run_golden_case(case)
        missing_rules = set(case.expected_rule_ids) - set(result["rule_ids"])
        if (
            result["status"] != case.expected_status
            or result["action_kind"] != case.expected_action_kind
            or missing_rules
        ):
            failures.append(
                {
                    "id": case.id,
                    "expected_status": case.expected_status,
                    "actual_status": result["status"],
                    "expected_action_kind": case.expected_action_kind,
                    "actual_action_kind": result["action_kind"],
                    "missing_rules": sorted(missing_rules),
                    "actual_rules": result["rule_ids"],
                }
            )
    if failures:
        for failure in failures:
            print(f"fail: {failure}")
        return 1
    print(f"ok: {len(load_golden_cases(path))} golden conversation(s) passed")
    return 0
