"""LangGraph checkpointer selection by runtime profile."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from wootpilot.domain.models import CheckpointerProfile
from wootpilot.settings import Settings


class CheckpointerConfigurationError(RuntimeError):
    """Raised when the configured checkpoint backend cannot be created."""


@asynccontextmanager
async def checkpointer_from_settings(
    settings: Settings,
) -> AsyncIterator[object | None]:
    """Yield the LangGraph checkpointer selected by `WOOTPILOT_CHECKPOINTER`.

    Memory is useful for unit tests, SQLite for local/alpha async runtime, and
    Postgres for production. Postgres is optional in local installs so the error
    explains the missing package instead of failing at import time elsewhere.
    """

    profile = settings.checkpointer
    if profile is CheckpointerProfile.none:
        yield None
        return
    if profile is CheckpointerProfile.memory:
        from langgraph.checkpoint.memory import InMemorySaver

        yield InMemorySaver()
        return
    if profile is CheckpointerProfile.sqlite:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        checkpoint_path = _sqlite_checkpoint_path(settings.db_url)
        async with AsyncSqliteSaver.from_conn_string(str(checkpoint_path)) as saver:
            yield saver
        return
    if profile is CheckpointerProfile.postgres:
        try:
            from langgraph.checkpoint.postgres.aio import (  # pyright: ignore[reportMissingImports]
                AsyncPostgresSaver,
            )
        except ModuleNotFoundError as exc:
            raise CheckpointerConfigurationError(
                "WOOTPILOT_CHECKPOINTER=postgres requires "
                "langgraph-checkpoint-postgres"
            ) from exc
        async with AsyncPostgresSaver.from_conn_string(settings.db_url) as saver:
            yield saver
        return
    raise CheckpointerConfigurationError(f"unknown checkpointer profile: {profile}")


def _sqlite_checkpoint_path(db_url: str) -> Path:
    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if db_url.startswith(prefix):
            app_path = Path(db_url.removeprefix(prefix))
            return app_path.with_name(f"{app_path.stem}-checkpoints{app_path.suffix}")
    raise CheckpointerConfigurationError(
        "WOOTPILOT_CHECKPOINTER=sqlite requires a sqlite database URL"
    )
