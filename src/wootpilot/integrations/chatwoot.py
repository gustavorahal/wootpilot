"""Chatwoot webhook translation and API writing helpers."""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from hashlib import sha256
from json import JSONDecodeError
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from wootpilot.application.errors import (
    ChatwootApiError,
    ChatwootResponseError,
    ChatwootTransportError,
)
from wootpilot.domain.models import (
    AttachmentMetadata,
    ChannelEvent,
    ConversationStatus,
    MessageAuthorType,
    MessageDirection,
    MessageVisibility,
    NormalizedMessage,
    Provider,
)
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
    status: ConversationStatus | None = None
    labels: list[str] = Field(default_factory=list)
    custom_attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("status", mode="before")
    @classmethod
    def coerce_status(
        cls, value: ConversationStatus | str | None
    ) -> ConversationStatus | None:
        return _conversation_status(value)


def event_type(payload: dict[str, Any]) -> str:
    """Return Chatwoot's event name across supported webhook payload shapes."""

    return str(
        payload.get("event") or payload.get("event_type") or payload.get("name") or ""
    )


def provider_event_id(payload: dict[str, Any], delivery_id: str | None) -> str:
    """Return a stable idempotency key for one Chatwoot webhook delivery.

    Chatwoot deployments may omit a delivery id, so the fallback combines the
    event type with a message id when available, otherwise a canonical payload
    hash.
    """

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
    """Translate a Chatwoot message webhook into WootPilot's message contract.

    Returns:
        A normalized message for `message_created` payloads, or `None` when the
        payload is not a message event WootPilot should store.
    """

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
        MessageDirection.inbound
        if message_type in {"incoming", "0", "inbound"}
        else MessageDirection.outbound
    )
    visibility = (
        MessageVisibility.private
        if bool(message.get("private"))
        else MessageVisibility.public
    )
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
        provider=Provider.chatwoot,
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
        status=_conversation_status(conversation.get("status")),
        replyable=conversation.get("can_reply"),
        paused="wootpilot-paused" in label_set
        or bool(custom_attributes.get("wootpilot_paused")),
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


def _author_type(
    message: dict[str, Any],
    sender: dict[str, Any],
) -> MessageAuthorType:
    sender_type = str(sender.get("type") or message.get("sender_type") or "").lower()
    if "contact" in sender_type:
        return MessageAuthorType.customer
    if "user" in sender_type:
        return MessageAuthorType.human_agent
    if "agentbot" in sender_type or "bot" in sender_type:
        return MessageAuthorType.bot
    return (
        MessageAuthorType.customer
        if str(message.get("message_type")) == "incoming"
        else MessageAuthorType.human_agent
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


def _conversation_status(value: Any) -> ConversationStatus | None:
    if value in {None, ""}:
        return None
    try:
        return ConversationStatus(str(value))
    except ValueError:
        return None


class ChatwootClient:
    """Minimal Chatwoot writer for private notes and public replies."""

    def __init__(
        self, settings: Settings, client: httpx.AsyncClient | None = None
    ) -> None:
        """Create a Chatwoot API client.

        Args:
            settings: Runtime settings containing Chatwoot base URL, account id,
                and API token.
            client: Optional HTTP client supplied by tests or shared callers.
        """

        self.settings = settings
        self.client = client

    @property
    def _account_base_url(self) -> str:
        return (
            f"{str(self.settings.chatwoot_base_url).rstrip('/')}/api/v1/accounts/"
            f"{self.settings.chatwoot_account_id}"
        )

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "api-access-token": self.settings.chatwoot_api_token,
            "Accept": "application/json",
        }

    async def create_message(
        self,
        *,
        conversation_id: str,
        content: str,
        private: bool,
    ) -> str:
        """Create a Chatwoot message and return its provider message id.

        Raises:
            ChatwootApiError: If the request fails or Chatwoot returns an
                invalid create-message response.
        """

        operation = "create_message"
        status_code: int | None = None
        started = time.perf_counter()
        try:
            response, status_code = await self._send_request(
                method="POST",
                path=f"/conversations/{conversation_id}/messages",
                payload={"content": content, "private": private},
            )
            response.raise_for_status()
            data = response.json()
            provider_message_id = _message_id_from_create_response(
                data,
                operation=operation,
                status_code=status_code,
            )
            self._log_api_call(
                operation=operation,
                conversation_id=conversation_id,
                status="success",
                status_code=status_code,
                latency_ms=round((time.perf_counter() - started) * 1000),
                provider_message_id=provider_message_id,
                private=private,
            )
            return provider_message_id
        except (httpx.HTTPError, JSONDecodeError, ValueError, ChatwootApiError) as exc:
            error = _chatwoot_error(operation, exc, status_code=status_code)
            self._log_api_call(
                operation=operation,
                conversation_id=conversation_id,
                status="failed",
                status_code=error.status_code,
                latency_ms=round((time.perf_counter() - started) * 1000),
                private=private,
                level=logging.WARNING,
            )
            raise error from exc

    async def set_conversation_status(
        self,
        *,
        conversation_id: str,
        status: str,
    ) -> None:
        """Set Chatwoot's conversation status after WootPilot finishes a write."""

        await self._post_json(
            operation="set_conversation_status",
            conversation_id=conversation_id,
            path=f"/conversations/{conversation_id}/toggle_status",
            payload={"status": status},
            conversation_status=status,
        )

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

        await self._post_json(
            operation="set_conversation_labels",
            conversation_id=conversation_id,
            path=f"/conversations/{conversation_id}/labels",
            payload={"labels": labels},
            label_count=len(labels),
        )

    async def get_conversation_safety(
        self,
        *,
        conversation_id: str,
    ) -> ChannelSafetyState:
        """Fetch fresh channel state for final public-send safety checks."""

        data = await self._get_json(
            operation="get_conversation_safety",
            conversation_id=conversation_id,
            path=f"/conversations/{conversation_id}",
        )
        return _conversation_safety_from_response(conversation_id, data)

    async def _post_json(
        self,
        *,
        operation: str,
        conversation_id: str,
        path: str,
        payload: dict[str, Any],
        private: bool | None = None,
        conversation_status: str | None = None,
        label_count: int | None = None,
    ) -> dict[str, Any]:
        return await self._request_json(
            method="POST",
            operation=operation,
            conversation_id=conversation_id,
            path=path,
            payload=payload,
            private=private,
            conversation_status=conversation_status,
            label_count=label_count,
        )

    async def _get_json(
        self,
        *,
        operation: str,
        conversation_id: str,
        path: str,
    ) -> dict[str, Any]:
        return await self._request_json(
            method="GET",
            operation=operation,
            conversation_id=conversation_id,
            path=path,
            payload=None,
        )

    async def _request_json(
        self,
        *,
        method: str,
        operation: str,
        conversation_id: str,
        path: str,
        payload: dict[str, Any] | None,
        private: bool | None = None,
        conversation_status: str | None = None,
        label_count: int | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        status_code: int | None = None
        try:
            response, status_code = await self._send_request(
                method=method,
                path=path,
                payload=payload,
            )
            response.raise_for_status()
            self._log_api_call(
                operation=operation,
                conversation_id=conversation_id,
                status="success",
                status_code=status_code,
                latency_ms=round((time.perf_counter() - started) * 1000),
                private=private,
                conversation_status=conversation_status,
                label_count=label_count,
            )
            return response.json()
        except (httpx.HTTPError, JSONDecodeError, ValueError, ChatwootApiError) as exc:
            error = _chatwoot_error(operation, exc, status_code=status_code)
            self._log_api_call(
                operation=operation,
                conversation_id=conversation_id,
                status="failed",
                status_code=error.status_code,
                latency_ms=round((time.perf_counter() - started) * 1000),
                private=private,
                conversation_status=conversation_status,
                label_count=label_count,
                level=logging.WARNING,
            )
            raise error from exc

    async def _send_request(
        self,
        *,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
    ) -> tuple[httpx.Response, int]:
        url = f"{self._account_base_url}{path}"
        if self.client:
            response = await self.client.request(
                method, url, json=payload, headers=self._headers
            )
        else:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.request(
                    method, url, json=payload, headers=self._headers
                )
        return response, response.status_code

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
            provider=Provider.chatwoot,
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
        status=_conversation_status(payload.get("status")),
        labels=labels,
        custom_attributes=custom_attributes,
    )


def _message_id_from_create_response(
    data: Any,
    *,
    operation: str,
    status_code: int | None,
) -> str:
    if not isinstance(data, dict):
        raise ChatwootResponseError(
            "chatwoot_response_invalid_message_payload",
            operation=operation,
            retryable=False,
            status_code=status_code,
        )
    payload = data.get("payload")
    if payload is not None and not isinstance(payload, dict):
        raise ChatwootResponseError(
            "chatwoot_response_invalid_message_payload",
            operation=operation,
            retryable=False,
            status_code=status_code,
        )
    message = data.get("id") or (payload or {}).get("id")
    if message in {None, ""}:
        raise ChatwootResponseError(
            "chatwoot_response_missing_message_id",
            operation=operation,
            retryable=False,
            status_code=status_code,
        )
    return str(message)


def _chatwoot_error(
    operation: str,
    exc: httpx.HTTPError | ValueError | ChatwootApiError,
    *,
    status_code: int | None,
) -> ChatwootApiError:
    if isinstance(exc, ChatwootApiError):
        return exc
    if isinstance(exc, httpx.HTTPStatusError):
        response_status = exc.response.status_code
        return ChatwootResponseError(
            f"chatwoot_http_{response_status}",
            operation=operation,
            retryable=_retryable_status(response_status),
            status_code=response_status,
        )
    if isinstance(exc, httpx.HTTPError):
        return ChatwootTransportError(
            exc.__class__.__name__,
            operation=operation,
            retryable=True,
            status_code=status_code,
        )
    return ChatwootResponseError(
        exc.__class__.__name__,
        operation=operation,
        retryable=False,
        status_code=status_code,
    )


def _retryable_status(status_code: int | None) -> bool:
    return status_code in {408, 409, 425, 429, 500, 502, 503, 504}
