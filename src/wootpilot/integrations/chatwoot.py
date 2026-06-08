"""Chatwoot webhook translation and API writing helpers."""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from wootpilot.domain.models import AttachmentMetadata, ChannelEvent, NormalizedMessage
from wootpilot.observability import log_event
from wootpilot.settings import Settings
from wootpilot.time import IdGenerator

logger = logging.getLogger(__name__)


class ChannelSafetyState(BaseModel):
    """Fresh channel state used by final public-send policy checks."""

    model_config = ConfigDict(strict=True)

    conversation_id: str
    replyable: bool | None = None
    paused: bool = False
    assigned_agent_id: str | None = None
    assigned_team_id: str | None = None
    status: str | None = None
    labels: list[str] = Field(default_factory=list)
    custom_attributes: dict[str, Any] = Field(default_factory=dict)


def event_type(payload: dict[str, Any]) -> str:
    return str(
        payload.get("event") or payload.get("event_type") or payload.get("name") or ""
    )


def provider_event_id(payload: dict[str, Any], delivery_id: str | None) -> str:
    if delivery_id:
        return delivery_id
    raw_message = payload.get("message")
    message = raw_message if isinstance(raw_message, dict) else payload
    message_id = message.get("id") or payload.get("id")
    if message_id:
        return f"{event_type(payload) or 'event'}:{message_id}"
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return f"{event_type(payload) or 'event'}:{sha256(canonical).hexdigest()}"


def translate_message(
    *,
    payload: dict[str, Any],
    raw_event_id: str,
    ids: IdGenerator,
) -> NormalizedMessage | None:
    evt = event_type(payload)
    if evt and evt != "message_created":
        return None
    message = (
        payload.get("message") if isinstance(payload.get("message"), dict) else payload
    )
    if not isinstance(message, dict):
        return None
    message_id = message.get("id")
    conversation = _dict(message.get("conversation") or payload.get("conversation"))
    account = _dict(
        message.get("account") or payload.get("account") or conversation.get("account")
    )
    inbox = _dict(
        message.get("inbox") or payload.get("inbox") or conversation.get("inbox")
    )
    sender = _dict(message.get("sender") or payload.get("sender"))
    if message_id is None or not conversation.get("id"):
        return None

    message_type = str(message.get("message_type") or "")
    direction = (
        "inbound" if message_type in {"incoming", "0", "inbound"} else "outbound"
    )
    visibility = "private" if bool(message.get("private")) else "public"
    author_type = _author_type(message, sender)
    created_at = _created_at(message.get("created_at") or payload.get("created_at"))
    content = str(message.get("content") or "").strip()
    labels = conversation.get("labels") or payload.get("labels") or []
    custom_attributes = conversation.get("custom_attributes") or {}
    assigned_agent_id = _assigned_agent_id(conversation)
    assigned_team_id = _assigned_team_id(conversation)
    account_id = account.get("id") or payload.get("account_id") or "default"
    inbox_id = inbox.get("id") or conversation.get("inbox_id") or "chatwoot"
    conversation_id = conversation.get("id")
    contact_id = str(sender.get("id")) if sender.get("id") is not None else None
    attachments = _attachments(message.get("attachments") or payload.get("attachments"))

    return NormalizedMessage(
        id=ids.new(),
        raw_event_id=raw_event_id,
        tenant_id=str(account_id),
        provider="chatwoot",
        provider_account_id=str(account_id),
        provider_inbox_id=str(inbox_id),
        provider_conversation_id=str(conversation_id),
        provider_message_id=str(message_id),
        provider_contact_id=contact_id,
        channel_id=str(inbox_id),
        conversation_id=str(conversation_id),
        message_id=str(message_id),
        contact_id=contact_id,
        direction=direction,
        visibility=visibility,
        author_type=author_type,
        content=content,
        attachments=attachments,
        created_at=created_at,
        metadata={
            "chatwoot": {
                "account_id": account_id,
                "inbox_id": inbox_id,
                "conversation_id": conversation_id,
                "message_id": message_id,
                "sender_type": sender.get("type"),
                "labels": labels,
                "custom_attributes": custom_attributes,
                "status": conversation.get("status"),
                "can_reply": conversation.get("can_reply"),
                "assigned_agent_id": assigned_agent_id,
                "assigned_team_id": assigned_team_id,
            }
        },
    )


def _attachments(value: Any) -> list[AttachmentMetadata]:
    if not isinstance(value, list):
        return []
    attachments = []
    for item in value:
        if not isinstance(item, dict):
            continue
        attachments.append(
            AttachmentMetadata(
                provider_attachment_id=str(item.get("id"))
                if item.get("id") is not None
                else None,
                content_type=item.get("content_type")
                or item.get("file_type")
                or item.get("extension"),
                file_name=item.get("file_name") or item.get("filename"),
                url=item.get("data_url") or item.get("download_url") or item.get("url"),
            )
        )
    return attachments


def translate_channel_event(
    *,
    payload: dict[str, Any],
    raw_event_id: str,
    ids: IdGenerator,
) -> ChannelEvent | None:
    """Translate Chatwoot conversation webhooks into safety-state updates."""

    evt = event_type(payload)
    if evt not in {
        "conversation_created",
        "conversation_updated",
        "conversation_status_changed",
    }:
        return None
    conversation = _conversation_payload(payload)
    conversation_id = conversation.get("id") or payload.get("conversation_id")
    if conversation_id is None:
        return None
    account = _dict(conversation.get("account") or payload.get("account"))
    labels = conversation.get("labels") or payload.get("labels") or []
    custom_attributes = conversation.get("custom_attributes") or {}
    if not isinstance(custom_attributes, dict):
        custom_attributes = {}
    label_set = {str(item) for item in labels}
    return ChannelEvent(
        id=ids.new(),
        raw_event_id=raw_event_id,
        event_type=evt,
        tenant_id=str(
            account.get("id") or payload.get("account_id") or payload.get("accountId")
            or "default"
        ),
        channel_id=str(
            conversation.get("inbox_id")
            or conversation.get("inboxId")
            or _dict(conversation.get("inbox")).get("id")
            or "chatwoot"
        ),
        conversation_id=str(conversation_id),
        status=str(conversation.get("status")) if conversation.get("status") else None,
        replyable=conversation.get("can_reply"),
        paused="wootpilot-paused" in label_set
        or bool(custom_attributes.get("wootpilot_paused")),
        auto_ok="wootpilot-auto-ok" in label_set
        or bool(custom_attributes.get("wootpilot_auto_ok")),
        assigned_agent_id=_assigned_agent_id(conversation),
        assigned_team_id=_assigned_team_id(conversation),
        created_at=_created_at(
            conversation.get("updated_at") or payload.get("created_at")
        ),
        metadata={
            "chatwoot": {
                "changed_attributes": payload.get("changed_attributes") or {},
                "labels": labels,
                "custom_attributes": custom_attributes,
            }
        },
    )


def _conversation_payload(payload: dict[str, Any]) -> dict[str, Any]:
    conversation = _dict(payload.get("conversation"))
    if conversation:
        return conversation
    return payload


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _assigned_agent_id(conversation: dict[str, Any]) -> str | None:
    value = (
        conversation.get("assignee_id")
        or conversation.get("assigneeId")
        or _dict(conversation.get("assignee")).get("id")
        or _dict(_dict(conversation.get("meta")).get("assignee")).get("id")
    )
    return str(value) if value not in {None, ""} else None


def _assigned_team_id(conversation: dict[str, Any]) -> str | None:
    value = (
        conversation.get("team_id")
        or conversation.get("teamId")
        or _dict(conversation.get("team")).get("id")
        or _dict(_dict(conversation.get("meta")).get("team")).get("id")
    )
    return str(value) if value not in {None, ""} else None


def _author_type(message: dict[str, Any], sender: dict[str, Any]) -> str:
    sender_type = str(sender.get("type") or message.get("sender_type") or "").lower()
    if "contact" in sender_type:
        return "customer"
    if "user" in sender_type:
        return "human_agent"
    if "agentbot" in sender_type or "bot" in sender_type:
        return "bot"
    return (
        "customer" if str(message.get("message_type")) == "incoming" else "human_agent"
    )


def _created_at(value: Any) -> datetime:
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, tz=UTC)
    if isinstance(value, str) and value:
        text = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            pass
    return datetime.now(UTC)


class ChatwootClient:
    """Minimal Chatwoot writer for private notes and public replies."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self.client = client

    async def create_message(
        self,
        *,
        conversation_id: str,
        content: str,
        private: bool,
    ) -> str:
        url = (
            f"{str(self.settings.chatwoot_base_url).rstrip('/')}/api/v1/accounts/"
            f"{self.settings.chatwoot_account_id}/conversations/{conversation_id}/messages"
        )
        payload = {"content": content, "private": private}
        headers = {
            "api-access-token": self.settings.chatwoot_api_token,
            "Accept": "application/json",
        }
        started = time.perf_counter()
        status_code: int | None = None
        try:
            if self.client:
                response = await self.client.post(url, json=payload, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=20) as client:
                    response = await client.post(url, json=payload, headers=headers)
            status_code = response.status_code
            response.raise_for_status()
            data = response.json()
            message = data.get("id") or data.get("payload", {}).get("id")
            provider_message_id = str(message or "")
            self._log_api_call(
                operation="create_message",
                conversation_id=conversation_id,
                status="success",
                status_code=status_code,
                latency_ms=round((time.perf_counter() - started) * 1000),
                provider_message_id=provider_message_id,
                private=private,
            )
            return provider_message_id
        except Exception:
            self._log_api_call(
                operation="create_message",
                conversation_id=conversation_id,
                status="failed",
                status_code=status_code,
                latency_ms=round((time.perf_counter() - started) * 1000),
                private=private,
                level=logging.WARNING,
            )
            raise

    async def set_conversation_status(
        self,
        *,
        conversation_id: str,
        status: str,
    ) -> None:
        """Set Chatwoot's conversation status after WootPilot finishes a write."""

        url = (
            f"{str(self.settings.chatwoot_base_url).rstrip('/')}/api/v1/accounts/"
            f"{self.settings.chatwoot_account_id}/conversations/{conversation_id}/toggle_status"
        )
        payload = {"status": status}
        headers = {
            "api-access-token": self.settings.chatwoot_api_token,
            "Accept": "application/json",
        }
        started = time.perf_counter()
        status_code: int | None = None
        try:
            if self.client:
                response = await self.client.post(url, json=payload, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=20) as client:
                    response = await client.post(url, json=payload, headers=headers)
            status_code = response.status_code
            response.raise_for_status()
            self._log_api_call(
                operation="set_conversation_status",
                conversation_id=conversation_id,
                status="success",
                status_code=status_code,
                latency_ms=round((time.perf_counter() - started) * 1000),
                conversation_status=status,
            )
        except Exception:
            self._log_api_call(
                operation="set_conversation_status",
                conversation_id=conversation_id,
                status="failed",
                status_code=status_code,
                latency_ms=round((time.perf_counter() - started) * 1000),
                conversation_status=status,
                level=logging.WARNING,
            )
            raise

    async def add_conversation_labels(
        self,
        *,
        conversation_id: str,
        labels: list[str],
    ) -> None:
        """Merge labels onto a conversation without dropping existing labels."""

        existing = await self.get_conversation_safety(conversation_id=conversation_id)
        merged = sorted({*existing.labels, *labels})
        await self.set_conversation_labels(
            conversation_id=conversation_id,
            labels=merged,
        )

    async def set_conversation_labels(
        self,
        *,
        conversation_id: str,
        labels: list[str],
    ) -> None:
        """Replace Chatwoot conversation labels with the provided full label set."""

        url = (
            f"{str(self.settings.chatwoot_base_url).rstrip('/')}/api/v1/accounts/"
            f"{self.settings.chatwoot_account_id}/conversations/{conversation_id}/labels"
        )
        payload = {"labels": labels}
        headers = {
            "api-access-token": self.settings.chatwoot_api_token,
            "Accept": "application/json",
        }
        started = time.perf_counter()
        status_code: int | None = None
        try:
            if self.client:
                response = await self.client.post(url, json=payload, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=20) as client:
                    response = await client.post(url, json=payload, headers=headers)
            status_code = response.status_code
            response.raise_for_status()
            self._log_api_call(
                operation="set_conversation_labels",
                conversation_id=conversation_id,
                status="success",
                status_code=status_code,
                latency_ms=round((time.perf_counter() - started) * 1000),
                label_count=len(labels),
            )
        except Exception:
            self._log_api_call(
                operation="set_conversation_labels",
                conversation_id=conversation_id,
                status="failed",
                status_code=status_code,
                latency_ms=round((time.perf_counter() - started) * 1000),
                label_count=len(labels),
                level=logging.WARNING,
            )
            raise

    async def get_conversation_safety(
        self,
        *,
        conversation_id: str,
    ) -> ChannelSafetyState:
        url = (
            f"{str(self.settings.chatwoot_base_url).rstrip('/')}/api/v1/accounts/"
            f"{self.settings.chatwoot_account_id}/conversations/{conversation_id}"
        )
        headers = {
            "api-access-token": self.settings.chatwoot_api_token,
            "Accept": "application/json",
        }
        started = time.perf_counter()
        status_code: int | None = None
        try:
            if self.client:
                response = await self.client.get(url, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=20) as client:
                    response = await client.get(url, headers=headers)
            status_code = response.status_code
            response.raise_for_status()
            safety = _conversation_safety_from_response(
                conversation_id, response.json()
            )
            self._log_api_call(
                operation="get_conversation_safety",
                conversation_id=conversation_id,
                status="success",
                status_code=status_code,
                latency_ms=round((time.perf_counter() - started) * 1000),
            )
            return safety
        except Exception:
            self._log_api_call(
                operation="get_conversation_safety",
                conversation_id=conversation_id,
                status="failed",
                status_code=status_code,
                latency_ms=round((time.perf_counter() - started) * 1000),
                level=logging.WARNING,
            )
            raise

    def _log_api_call(
        self,
        *,
        operation: str,
        conversation_id: str,
        status: str,
        status_code: int | None,
        latency_ms: int,
        provider_message_id: str | None = None,
        private: bool | None = None,
        conversation_status: str | None = None,
        label_count: int | None = None,
        level: int = logging.INFO,
    ) -> None:
        log_event(
            logger,
            "chatwoot_api_call_completed",
            level=level,
            provider="chatwoot",
            operation=operation,
            account_id=self.settings.chatwoot_account_id,
            conversation_id=conversation_id,
            status=status,
            status_code=status_code,
            latency_ms=latency_ms,
            provider_message_id=provider_message_id,
            private=private,
            conversation_status=conversation_status,
            label_count=label_count,
        )


def _conversation_safety_from_response(
    conversation_id: str, data: dict[str, Any]
) -> ChannelSafetyState:
    payload = data.get("payload") or data.get("data") or data
    if isinstance(payload, dict) and isinstance(payload.get("conversation"), dict):
        payload = payload["conversation"]
    if not isinstance(payload, dict):
        payload = {}
    labels = [str(item) for item in payload.get("labels") or []]
    custom_attributes = payload.get("custom_attributes") or {}
    if not isinstance(custom_attributes, dict):
        custom_attributes = {}
    return ChannelSafetyState(
        conversation_id=str(payload.get("id") or conversation_id),
        replyable=payload.get("can_reply"),
        paused="wootpilot-paused" in labels
        or bool(custom_attributes.get("wootpilot_paused")),
        assigned_agent_id=_assigned_agent_id(payload),
        assigned_team_id=_assigned_team_id(payload),
        status=str(payload.get("status")) if payload.get("status") else None,
        labels=labels,
        custom_attributes=custom_attributes,
    )
