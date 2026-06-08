"""Small time and id ports used to keep tests deterministic."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4


class Clock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class IdGenerator:
    def new(self) -> str:
        return str(uuid4())
