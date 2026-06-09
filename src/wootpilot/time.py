"""Small time and id ports used to keep tests deterministic."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

__all__ = ["Clock", "IdGenerator"]


class Clock:
    """Clock port for injecting deterministic time in tests."""

    def now(self) -> datetime:
        """Return the current UTC time."""

        return datetime.now(UTC)


class IdGenerator:
    """Identifier port for replacing UUID generation in deterministic flows."""

    def new(self) -> str:
        """Return a new opaque application identifier."""

        return str(uuid4())
