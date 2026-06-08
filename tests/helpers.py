from __future__ import annotations

import hmac
import json
from datetime import UTC, datetime
from hashlib import sha256


def signed_headers(
    payload: dict, secret: str = "test-secret", timestamp: int | None = None
):
    timestamp = timestamp or int(datetime.now(UTC).timestamp())
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    digest = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + body, sha256
    ).hexdigest()
    return body, {
        "X-Chatwoot-Timestamp": str(timestamp),
        "X-Chatwoot-Signature": f"sha256={digest}",
        "X-Chatwoot-Delivery": f"delivery-{_delivery_source_id(payload)}",
    }


def _delivery_source_id(payload: dict) -> str:
    message = payload.get("message")
    if isinstance(message, dict) and message.get("id") is not None:
        return str(message["id"])
    if payload.get("id") is not None:
        return str(payload["id"])
    return "event"


def customer_message_payload(
    message_id: int = 101,
    content: str = "Do you have TBI?",
    *,
    message_type: str = "incoming",
    private: bool = False,
    sender_type: str = "contact",
    assignee_id: int | None = None,
    team_id: int | None = None,
    attachments: list[dict] | None = None,
):
    conversation = {
        "id": 3,
        "status": "open",
        "can_reply": True,
        "labels": [],
        "custom_attributes": {},
    }
    if assignee_id is not None:
        conversation["assignee_id"] = assignee_id
    if team_id is not None:
        conversation["team_id"] = team_id
    return {
        "event": "message_created",
        "message": {
            "id": message_id,
            "content": content,
            "attachments": attachments or [],
            "message_type": message_type,
            "private": private,
            "created_at": datetime.now(UTC).isoformat(),
            "account": {"id": 1},
            "inbox": {"id": 2},
            "conversation": conversation,
            "sender": {"id": 4, "type": sender_type},
        },
    }


def conversation_event_payload(
    *,
    event: str = "conversation_updated",
    conversation_id: int = 3,
    assignee_id: int | None = None,
    team_id: int | None = None,
    status: str = "open",
    can_reply: bool = True,
    labels: list[str] | None = None,
    custom_attributes: dict | None = None,
):
    payload = {
        "event": event,
        "id": conversation_id,
        "account_id": 1,
        "inbox_id": 2,
        "status": status,
        "can_reply": can_reply,
        "labels": labels or [],
        "custom_attributes": custom_attributes or {},
        "changed_attributes": {},
        "updated_at": datetime.now(UTC).isoformat(),
    }
    if assignee_id is not None:
        payload["assignee_id"] = assignee_id
    if team_id is not None:
        payload["team_id"] = team_id
    return payload
