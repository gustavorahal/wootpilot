"""Audit and context snapshot vocabulary."""

from __future__ import annotations

from enum import StrEnum


class ContextSnapshotKind(StrEnum):
    """Kinds of context snapshots persisted for auditability."""

    catalog = "catalog"


class AuditEventType(StrEnum):
    """Audit event names emitted by application use cases.

    Audit records explain important WootPilot decisions without copying raw
    provider payloads into every record. The ids stored beside these event names
    link back to raw events, normalized messages, context snapshots, policy
    decisions, agent runs, and outbound actions.
    """

    channel_state_updated = "channel_state_updated"
    webhook_ignored = "webhook_ignored"
    message_ignored = "message_ignored"
    support_workflow_completed = "support_workflow_completed"
