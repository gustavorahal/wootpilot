"""Small operational CLI for local development."""

from __future__ import annotations

import argparse
import asyncio
import importlib
from datetime import timedelta
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol

from sqlalchemy.engine import make_url

from wootpilot.application.outbound import ExecuteOutboundActions
from wootpilot.catalog.factory import catalog_connector_from_settings
from wootpilot.evals.golden import load_golden_cases, run_golden_case
from wootpilot.observability import configure_langsmith
from wootpilot.persistence.database import init_database, make_session_factory
from wootpilot.persistence.repositories import OUTBOUND_NOTIFY_CHANNEL, Repository
from wootpilot.settings import Settings, get_settings
from wootpilot.time import Clock

__all__ = ["main"]


def main() -> None:
    """Run local operational commands for database, catalog, and workflow checks."""

    parser = argparse.ArgumentParser(prog="wootpilot")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db")
    execute = sub.add_parser("execute-outbound")
    execute.add_argument("--limit", type=int, default=10)
    worker = sub.add_parser("outbound-worker")
    worker.add_argument("--limit", type=int, default=10)
    worker.add_argument("--interval", type=float, default=0.5)
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
        print(_format_outbound_counts(counts))
    elif args.command == "outbound-worker":
        asyncio.run(
            _outbound_worker(
                settings,
                limit=args.limit,
                interval=args.interval,
            )
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


async def _outbound_worker(settings: Settings, *, limit: int, interval: float) -> None:
    """Continuously execute queued outbound actions until interrupted."""

    wakeup = _outbound_wakeup_from_settings(settings)
    print(
        f"outbound worker started: limit={limit} interval={interval:g}s "
        f"wakeup={wakeup.name}"
    )
    try:
        async with wakeup:
            while True:
                counts = await _execute_outbound(settings, limit)
                if any(counts.values()):
                    print(_format_outbound_counts(counts))
                await wakeup.wait(
                    wait_seconds=await _outbound_wait_seconds(
                        settings,
                        wakeup=wakeup,
                        fallback_seconds=interval,
                    )
                )
    except KeyboardInterrupt:
        print("outbound worker stopped")


class _OutboundWakeup(Protocol):
    name: str

    async def __aenter__(self) -> _OutboundWakeup:
        """Open any resources needed while the worker loop is active."""
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close worker wakeup resources."""
        ...

    async def wait(self, *, wait_seconds: float) -> None:
        """Wait until work might be available or the fallback timeout elapses."""
        ...


class _PollingOutboundWakeup:
    name = "polling"

    async def __aenter__(self) -> _PollingOutboundWakeup:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc, traceback

    async def wait(self, *, wait_seconds: float) -> None:
        await asyncio.sleep(wait_seconds)


class _PostgresOutboundWakeup:
    name = "postgres-listen-notify"

    def __init__(self, db_url: str) -> None:
        self.db_url = db_url
        self.connection: Any | None = None

    async def __aenter__(self) -> _PostgresOutboundWakeup:
        psycopg = importlib.import_module("psycopg")
        connection = await psycopg.AsyncConnection.connect(
            conninfo=_postgres_conninfo(self.db_url),
            autocommit=True,
        )
        await connection.execute(f"LISTEN {OUTBOUND_NOTIFY_CHANNEL}")
        self.connection = connection
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc, traceback
        if self.connection is not None:
            await self.connection.close()

    async def wait(self, *, wait_seconds: float) -> None:
        if self.connection is None:
            await asyncio.sleep(wait_seconds)
            return
        async for _ in self.connection.notifies(
            timeout=wait_seconds,
            stop_after=1,
        ):
            return


def _outbound_wakeup_from_settings(settings: Settings) -> _OutboundWakeup:
    """Select wakeup behavior from the configured database dialect."""

    if _db_drivername(settings).startswith("postgresql"):
        return _PostgresOutboundWakeup(settings.db_url)
    return _PollingOutboundWakeup()


def _db_drivername(settings: Settings) -> str:
    return make_url(settings.db_url).drivername


def _postgres_conninfo(db_url: str) -> str:
    return make_url(db_url).set(drivername="postgresql").render_as_string(
        hide_password=False
    )


def _format_outbound_counts(counts: dict[str, int]) -> str:
    return (
        f"sent={counts['sent']} blocked={counts['blocked']} "
        f"failed={counts['failed']} superseded={counts['superseded']}"
    )


async def _outbound_wait_seconds(
    settings: Settings,
    *,
    wakeup: _OutboundWakeup,
    fallback_seconds: float,
) -> float:
    if wakeup.name != _PostgresOutboundWakeup.name:
        return fallback_seconds

    now = Clock().now()
    factory = make_session_factory(settings)
    async with factory() as session:
        due_at = await Repository(session).next_outbound_action_due_at(
            now=now,
            public_reply_delay=timedelta(
                seconds=settings.outbound_public_reply_delay_seconds
            ),
        )
    if due_at is None:
        return fallback_seconds
    seconds_until_due = (due_at - now).total_seconds()
    return max(0.0, min(fallback_seconds, seconds_until_due))


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
