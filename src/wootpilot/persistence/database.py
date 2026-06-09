"""Database engine/session helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from wootpilot.persistence.models import Base
from wootpilot.settings import Settings


def make_engine(settings: Settings) -> AsyncEngine:
    """Create an async SQLAlchemy engine with WootPilot runtime defaults.

    SQLite uses `NullPool` because local and test processes are short-lived and
    should not keep aiosqlite worker threads alive after commands finish.
    """

    connect_args = (
        {"check_same_thread": False} if settings.db_url.startswith("sqlite") else {}
    )
    if settings.db_url.startswith("sqlite"):
        # aiosqlite keeps a worker thread per pooled connection. NullPool closes
        # connections promptly, which matches WootPilot's single-worker SQLite
        # profile and avoids dangling threads in short-lived tests/CLI commands.
        engine = create_async_engine(
            settings.db_url,
            connect_args=connect_args,
            poolclass=NullPool,
        )
    else:
        engine = create_async_engine(settings.db_url, connect_args=connect_args)
    if settings.db_url.startswith("sqlite"):
        _install_sqlite_pragmas(engine)
    return engine


def make_session_factory(settings: Settings) -> async_sessionmaker[AsyncSession]:
    """Create the session factory used by API requests, CLI commands, and tests."""

    return async_sessionmaker(make_engine(settings), expire_on_commit=False)


async def init_database(settings: Settings) -> None:
    """Create all currently declared tables for early-stage local deployments."""

    engine = make_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


async def sqlite_pragmas(settings: Settings) -> dict[str, str]:
    """Return SQLite runtime pragma values for readiness checks and tests."""

    engine = make_engine(settings)
    async with engine.connect() as conn:
        journal_mode = await conn.scalar(text("PRAGMA journal_mode"))
        foreign_keys = await conn.scalar(text("PRAGMA foreign_keys"))
        busy_timeout = await conn.scalar(text("PRAGMA busy_timeout"))
    await engine.dispose()
    return {
        "journal_mode": str(journal_mode),
        "foreign_keys": str(foreign_keys),
        "busy_timeout": str(busy_timeout),
    }


async def session_scope(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Yield a transaction-scoped session and rollback on any escaping error.

    Args:
        factory: Async SQLAlchemy session factory created for the current
            runtime settings.
    """

    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _install_sqlite_pragmas(engine: AsyncEngine) -> None:
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record) -> None:
        del connection_record
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()
