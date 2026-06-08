"""Structured logging helpers for operationally important WootPilot events.

The application deliberately logs workflow and outbound metadata without
customer message bodies, drafted response content, contact identifiers, API
tokens, or raw provider payloads. Persisted rows remain the source of truth;
logs are for live operations, alerting, and latency/error triage.
"""

from __future__ import annotations

import json
import logging
import sys
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
    automation_mode: str,
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
        "automation_mode": automation_mode,
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


def workflow_trace_start(
    *,
    enabled: bool,
    thread_id: str,
    tenant_id: str,
    channel_id: str,
    conversation_id: str,
    message_id: str,
    automation_mode: str,
    content: str,
) -> None:
    """Print a local-only workflow trace header for one graph invocation."""

    if not enabled:
        return
    _trace_line(
        "start",
        "workflow",
        {
            "thread": thread_id,
            "tenant": tenant_id,
            "channel": channel_id,
            "conversation": conversation_id,
            "message": message_id,
            "mode": automation_mode,
            "content": content,
        },
    )


def workflow_trace_update(*, enabled: bool, node: str, update: Any) -> None:
    """Print one developer-facing LangGraph node update."""

    if not enabled:
        return
    _trace_line("step", node, _workflow_update_summary(update))


def workflow_trace_complete(
    *,
    enabled: bool,
    status: str,
    action_kind: str,
    rule_ids: list[str],
) -> None:
    """Print a local-only workflow trace footer for one graph invocation."""

    if not enabled:
        return
    _trace_line(
        "done",
        "workflow",
        {"status": status, "action": action_kind, "rules": rule_ids},
    )


def workflow_trace_enabled(*, env: str, enabled: bool) -> bool:
    """Return whether pretty graph tracing should be printed locally.

    The guard keeps content-rich graph tracing out of tests and production even
    if the setting is accidentally left true. Production should continue relying
    on structured JSON logs and durable audit records.
    """

    return enabled and env in {"local", "public_dev"}


def _workflow_update_summary(update: Any) -> dict[str, Any]:
    """Return a developer-facing summary of one LangGraph state update.

    This intentionally includes customer and model-visible text in local and
    public-dev traces. The caller gates this helper behind `workflow_trace_enabled`
    so it is not used in test or production environments.
    """

    if not isinstance(update, Mapping):
        return {"update": type(update).__name__}
    summary: dict[str, Any] = {}
    if triage := update.get("triage_result"):
        summary["intent"] = getattr(triage, "intent", None)
        summary["risks"] = getattr(triage, "risk_signals", [])
    if policy := update.get("pre_model_policy_decision") or update.get(
        "post_model_policy_decision"
    ):
        summary["policy"] = _enum_value(getattr(policy, "outcome", None))
        summary["rules"] = [
            _enum_value(item) for item in getattr(policy, "rule_ids", [])
        ]
    if proposal := update.get("agent_proposal"):
        summary["proposal_action"] = _enum_value(
            getattr(proposal, "action_kind", None)
        )
        summary["confidence"] = getattr(proposal, "confidence", None)
        summary["risks"] = getattr(proposal, "risk_reasons", [])
        summary["public_message"] = getattr(proposal, "public_message", None)
        summary["private_note"] = getattr(proposal, "private_note", None)
        summary["summary"] = getattr(proposal, "summary", None)
    if decision := update.get("workflow_decision"):
        summary["status"] = _enum_value(getattr(decision, "status", None))
        summary["action"] = _enum_value(getattr(decision, "action_kind", None))
        summary["rules"] = [
            _enum_value(item) for item in getattr(decision, "rule_ids", [])
        ]
        summary["content"] = getattr(decision, "content", None)
        summary["summary"] = getattr(decision, "summary", None)
    if metadata := update.get("model_metadata"):
        if isinstance(metadata, Mapping):
            summary["model_provider"] = metadata.get("provider")
            summary["model"] = metadata.get("model")
            summary["structured_method"] = metadata.get("structured_method")
            summary["latency_ms"] = metadata.get("latency_ms")
    if catalog := update.get("catalog_context"):
        summary["products"] = len(getattr(catalog, "products", []) or [])
        summary["catalog_risks"] = getattr(catalog, "risk_signals", [])
        summary["snapshot"] = getattr(catalog, "snapshot_id", None)
    return {key: value for key, value in summary.items() if value not in (None, [])}


def _trace_line(kind: str, label: str, fields: Mapping[str, Any]) -> None:
    icon = {"start": "->", "step": "=>", "done": "OK"}.get(kind, "--")
    color = {"start": "36", "step": "34", "done": "32"}.get(kind, "0")
    payload = {
        str(key): _json_safe(value)
        for key, value in fields.items()
        if value not in (None, [], "")
    }
    prefix = f"{icon} {label:<28}"
    if sys.stderr.isatty():
        prefix = f"\033[{color}m{prefix}\033[0m"
    print(prefix.rstrip(), file=sys.stderr)
    if payload:
        print(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            file=sys.stderr,
        )


def _enum_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


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
