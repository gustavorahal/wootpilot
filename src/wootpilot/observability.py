"""Structured logging helpers for operationally important WootPilot events.

The application deliberately logs workflow and outbound metadata without
customer message bodies, drafted response content, contact identifiers, API
tokens, or raw provider payloads. Persisted rows remain the source of truth;
logs are for live operations, alerting, and latency/error triage.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from enum import Enum
from typing import Any

RESERVED_LOG_RECORD_KEYS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)


class JsonEventFormatter(logging.Formatter):
    """Render log records as compact JSON objects.

    The formatter includes standard routing fields and flattens caller-provided
    structured metadata from ``record.wootpilot_fields``. It intentionally
    leaves content redaction to call sites so each domain boundary has to make
    an explicit decision about which fields are operationally safe.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": getattr(record, "wootpilot_event", record.getMessage()),
        }
        fields = getattr(record, "wootpilot_fields", {})
        if isinstance(fields, Mapping):
            payload.update(_json_safe(fields))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def configure_logging(level: str) -> None:
    """Configure process logging for JSON events while preserving test handlers."""

    root = logging.getLogger()
    root.setLevel(_level(level))
    formatter = JsonEventFormatter()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        root.addHandler(handler)
        return
    for handler in root.handlers:
        handler.setFormatter(formatter)


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """Emit one structured event with JSON-safe field values."""

    logger.log(
        level,
        event,
        extra={
            "wootpilot_event": event,
            "wootpilot_fields": _json_safe(fields),
        },
    )


def workflow_log_fields(
    *,
    agent_run_id: str,
    raw_event_id: str,
    normalized_message_id: str,
    tenant_id: str,
    channel_id: str,
    conversation_id: str,
    bot_mode: str,
    status: str,
    action_kind: str,
    rule_ids: list[str],
    risk_reasons: list[str],
    model_metadata: Mapping[str, Any],
    high_latency_threshold_ms: int,
) -> dict[str, Any]:
    """Build the non-sensitive log envelope for a completed workflow run."""

    latency_ms = _int_or_none(model_metadata.get("latency_ms"))
    return {
        "agent_run_id": agent_run_id,
        "raw_event_id": raw_event_id,
        "normalized_message_id": normalized_message_id,
        "tenant_id": tenant_id,
        "channel_id": channel_id,
        "conversation_id": conversation_id,
        "bot_mode": bot_mode,
        "status": status,
        "action_kind": action_kind,
        "rule_ids": rule_ids,
        "risk_reasons": risk_reasons,
        "model_provider": model_metadata.get("provider"),
        "model": model_metadata.get("model"),
        "provider_model_name": model_metadata.get("provider_model_name"),
        "provider_generation_id": model_metadata.get("provider_generation_id"),
        "structured_method": model_metadata.get("structured_method"),
        "latency_ms": latency_ms,
        "high_latency": latency_ms is not None
        and latency_ms >= high_latency_threshold_ms,
    }


def outbound_log_fields(
    *,
    action_id: str,
    tenant_id: str,
    channel_id: str,
    conversation_id: str,
    action_kind: str,
    status: str,
    provider_message_id: str | None = None,
    failure_reason: str | None = None,
) -> dict[str, Any]:
    """Build the non-sensitive log envelope for outbound execution outcomes."""

    return {
        "action_id": action_id,
        "tenant_id": tenant_id,
        "channel_id": channel_id,
        "conversation_id": conversation_id,
        "action_kind": action_kind,
        "status": status,
        "provider_message_id": provider_message_id,
        "failure_reason": failure_reason,
    }


def _level(value: str) -> int:
    return getattr(logging, value.upper(), logging.INFO)


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_json_safe(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)
