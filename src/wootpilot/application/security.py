"""Webhook authentication for Chatwoot signed deliveries."""

from __future__ import annotations

import hmac
from datetime import UTC, datetime
from hashlib import sha256

from fastapi import HTTPException

from wootpilot.settings import Settings


def verify_chatwoot_signature(
    *,
    settings: Settings,
    headers: dict[str, str],
    body: bytes,
    now: datetime,
) -> None:
    """Validate Chatwoot's timestamped HMAC webhook signature.

    Args:
        settings: Runtime settings containing header names, shared secret, and
            replay window.
        headers: Lower-cased request headers from the ASGI route.
        body: Raw request body used as signed material.
        now: Current time supplied by the caller for deterministic tests.

    Raises:
        HTTPException: If the secret is missing, signature headers are missing
            or malformed, the timestamp is stale, or the digest does not match.
    """

    secret = settings.chatwoot_webhook_secret
    if not secret or secret == "change-me":
        raise HTTPException(status_code=401, detail="webhook secret is not configured")

    signature = headers.get(settings.chatwoot_webhook_signature_header.lower())
    timestamp = headers.get(settings.chatwoot_webhook_timestamp_header.lower())
    if not signature or not timestamp:
        raise HTTPException(
            status_code=401, detail="missing Chatwoot signature headers"
        )

    try:
        timestamp_value = int(timestamp)
    except ValueError as exc:
        raise HTTPException(
            status_code=401, detail="invalid webhook timestamp"
        ) from exc

    received = datetime.fromtimestamp(timestamp_value, tz=UTC)
    if abs((now - received).total_seconds()) > settings.webhook_replay_window_seconds:
        raise HTTPException(status_code=401, detail="stale webhook timestamp")

    signed_body = timestamp.encode("utf-8") + b"." + body
    digest = hmac.new(secret.encode("utf-8"), signed_body, sha256).hexdigest()
    expected = f"sha256={digest}"
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="invalid Chatwoot signature")
