from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import TracebackType

from wootpilot.cli import (
    _outbound_wait_seconds,
    _outbound_wakeup_from_settings,
    _outbound_worker,
    _PostgresOutboundWakeup,
)
from wootpilot.settings import Settings


async def test_outbound_worker_runs_until_interrupted(
    monkeypatch,
    capsys,
) -> None:
    calls = 0

    async def fake_execute_outbound(
        settings: Settings,
        limit: int,
    ) -> dict[str, int]:
        nonlocal calls
        assert settings.chatwoot_webhook_secret == "secret"
        assert limit == 7
        calls += 1
        return {"sent": 1, "blocked": 0, "failed": 0, "superseded": 0}

    async def fake_sleep(interval: float) -> None:
        assert interval == 0.5
        raise KeyboardInterrupt

    monkeypatch.setattr("wootpilot.cli._execute_outbound", fake_execute_outbound)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    await _outbound_worker(
        Settings(chatwoot_webhook_secret="secret"),
        limit=7,
        interval=0.5,
    )

    captured = capsys.readouterr()
    assert calls == 1
    assert "outbound worker started: limit=7 interval=0.5s" in captured.out
    assert "sent=1 blocked=0 failed=0 superseded=0" in captured.out
    assert "outbound worker stopped" in captured.out


async def test_sqlite_outbound_worker_uses_polling_wakeup() -> None:
    wakeup = _outbound_wakeup_from_settings(
        Settings(
            chatwoot_webhook_secret="secret",
            db_url="sqlite+aiosqlite:///./data/wootpilot.db",
        )
    )

    assert wakeup.name == "polling"


async def test_postgres_outbound_worker_listens_on_hard_coded_channel(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeConnection:
        def __init__(self) -> None:
            self.commands: list[str] = []
            self.closed = False

        async def execute(self, command: str) -> None:
            self.commands.append(command)

        def notifies(
            self,
            *,
            timeout: float | None = None,
            stop_after: int | None = None,
        ) -> AsyncIterator[None]:
            del timeout, stop_after

            async def notifications() -> AsyncIterator[None]:
                await asyncio.sleep(3600)
                yield None

            return notifications()

        async def close(self) -> None:
            self.closed = True

    fake_connection = FakeConnection()

    class FakeAsyncConnection:
        @staticmethod
        async def connect(*, conninfo: str, autocommit: bool) -> FakeConnection:
            captured["conninfo"] = conninfo
            captured["autocommit"] = autocommit
            return fake_connection

    class FakePsycopg:
        AsyncConnection = FakeAsyncConnection

    def fake_import_module(name: str) -> type[FakePsycopg]:
        assert name == "psycopg"
        return FakePsycopg

    monkeypatch.setattr("wootpilot.cli.importlib.import_module", fake_import_module)

    wakeup = _outbound_wakeup_from_settings(
        Settings(
            chatwoot_webhook_secret="secret",
            db_url="postgresql+psycopg://user:pass@localhost/wootpilot",
        )
    )

    assert wakeup.name == "postgres-listen-notify"
    assert isinstance(wakeup, _PostgresOutboundWakeup)

    async with wakeup:
        assert captured == {
            "conninfo": "postgresql://user:pass@localhost/wootpilot",
            "autocommit": True,
        }
        assert fake_connection.commands == ["LISTEN wootpilot_outbound_queue"]

    assert fake_connection.closed is True


async def test_postgres_outbound_wait_seconds_uses_next_due_time(
    monkeypatch,
) -> None:
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    captured: dict[str, object] = {}

    class FakeClock:
        def now(self) -> datetime:
            return now

    class FakeSessionFactory:
        def __call__(self) -> FakeSessionFactory:
            return self

        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            traceback: TracebackType | None,
        ) -> None:
            del exc_type, exc, traceback

    class FakeRepository:
        def __init__(self, session: object) -> None:
            del session

        async def next_outbound_action_due_at(
            self,
            *,
            now: datetime,
            public_reply_delay: timedelta,
        ) -> datetime:
            captured["now"] = now
            captured["public_reply_delay"] = public_reply_delay
            return now + timedelta(seconds=0.2)

    class FakePostgresWakeup:
        name = "postgres-listen-notify"

        async def __aenter__(self) -> FakePostgresWakeup:
            return self

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            traceback: TracebackType | None,
        ) -> None:
            del exc_type, exc, traceback

        async def wait(self, *, wait_seconds: float) -> None:
            del wait_seconds

    monkeypatch.setattr("wootpilot.cli.Clock", FakeClock)
    monkeypatch.setattr(
        "wootpilot.cli.make_session_factory",
        lambda settings: FakeSessionFactory(),
    )
    monkeypatch.setattr("wootpilot.cli.Repository", FakeRepository)

    wait_seconds = await _outbound_wait_seconds(
        Settings(
            chatwoot_webhook_secret="secret",
            outbound_public_reply_delay_seconds=2.0,
        ),
        wakeup=FakePostgresWakeup(),
        fallback_seconds=0.5,
    )

    assert wait_seconds == 0.2
    assert captured == {
        "now": now,
        "public_reply_delay": timedelta(seconds=2),
    }
