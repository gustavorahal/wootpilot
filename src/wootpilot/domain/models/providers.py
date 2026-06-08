"""Provider and webhook result vocabulary."""

from __future__ import annotations

from enum import StrEnum


class Provider(StrEnum):
    """External channel provider identifiers stored on normalized events."""

    chatwoot = "chatwoot"


class RawEventStatus(StrEnum):
    """Processing status for an authenticated provider webhook delivery."""

    received = "received"
    processed = "processed"
    ignored = "ignored"
    duplicate = "duplicate"


class WebhookResultStatus(StrEnum):
    """Status values returned by webhook application handling."""

    processed = "processed"
    ignored = "ignored"
    duplicate = "duplicate"
