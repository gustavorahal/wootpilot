from __future__ import annotations

from datetime import UTC, datetime
from importlib.metadata import metadata
from pathlib import Path

from sqlalchemy.dialects import postgresql, sqlite

from wootpilot.domain.models import CheckpointerProfile, RuntimeEnvironment
from wootpilot.persistence.database import init_database, sqlite_pragmas
from wootpilot.persistence.repositories import queued_outbound_actions_statement
from wootpilot.settings import Settings
from wootpilot.workflow.checkpoints import (
    checkpointer_from_settings,
)


async def test_sqlite_profile_sets_runtime_pragmas(tmp_path: Path) -> None:
    settings = Settings(
        env=RuntimeEnvironment.test,
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'ready.db'}",
        chatwoot_webhook_secret="secret",
    )
    await init_database(settings)

    pragmas = await sqlite_pragmas(settings)

    assert pragmas["journal_mode"].lower() == "wal"
    assert pragmas["foreign_keys"] == "1"
    assert int(pragmas["busy_timeout"]) >= 5000


async def test_checkpointer_factory_selects_memory_profile() -> None:
    settings = Settings(
        checkpointer=CheckpointerProfile.memory,
        chatwoot_webhook_secret="secret",
    )

    async with checkpointer_from_settings(settings) as saver:
        assert saver.__class__.__name__ == "InMemorySaver"


async def test_checkpointer_factory_selects_sqlite_profile(tmp_path: Path) -> None:
    settings = Settings(
        checkpointer=CheckpointerProfile.sqlite,
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'checkpoint.db'}",
        chatwoot_webhook_secret="secret",
    )

    async with checkpointer_from_settings(settings) as saver:
        assert saver.__class__.__name__ == "AsyncSqliteSaver"


def test_project_declares_postgres_optional_dependencies() -> None:
    requires_dist = metadata("wootpilot").get_all("Requires-Dist") or []

    assert any(
        "psycopg" in item and "extra == 'postgres'" in item
        for item in requires_dist
    )
    assert any(
        "langgraph-checkpoint-postgres" in item and "extra == 'postgres'" in item
        for item in requires_dist
    )


def test_postgres_outbound_dequeue_query_uses_skip_locked() -> None:
    statement = queued_outbound_actions_statement(
        limit=5,
        now=datetime.now(UTC),
        dialect_name="postgresql",
    )
    compiled = str(statement.compile(dialect=postgresql.dialect()))

    assert "FOR UPDATE SKIP LOCKED" in compiled


def test_sqlite_outbound_dequeue_query_does_not_use_row_locks() -> None:
    statement = queued_outbound_actions_statement(
        limit=5,
        now=datetime.now(UTC),
        dialect_name="sqlite",
    )
    compiled = str(statement.compile(dialect=sqlite.dialect()))

    assert "FOR UPDATE" not in compiled


def test_outbound_dequeue_query_includes_only_due_retryable_actions() -> None:
    now = datetime.now(UTC)
    statement = queued_outbound_actions_statement(
        limit=5,
        now=now,
        dialect_name="sqlite",
    )
    compiled = str(
        statement.compile(
            dialect=sqlite.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "outbound_actions.status = 'queued'" in compiled
    assert "outbound_actions.status = 'retryable_failure'" in compiled
    assert "outbound_actions.next_attempt_at IS NOT NULL" in compiled
    assert "<=" in compiled
    assert str(now.year) in compiled
