from __future__ import annotations

import logging
from typing import Any

import pytest
import respx
from httpx import Response

from wootpilot.application.errors import ChatwootResponseError
from wootpilot.integrations.chatwoot import ChatwootClient, provider_event_id
from wootpilot.settings import Settings


def test_provider_event_id_fallback_is_stable_for_payload_without_ids() -> None:
    first = {"event": "conversation_updated", "meta": {"b": 2, "a": 1}}
    second = {"meta": {"a": 1, "b": 2}, "event": "conversation_updated"}

    assert provider_event_id(first, None) == provider_event_id(second, None)
    assert provider_event_id(first, None).startswith("conversation_updated:")


@respx.mock
async def test_chatwoot_client_logs_message_api_latency(caplog) -> None:
    settings_values: dict[str, Any] = {
        "chatwoot_base_url": "https://chatwoot.example.test",
        "chatwoot_account_id": "1",
        "chatwoot_api_token": "token",
        "chatwoot_webhook_secret": "secret",
    }
    settings = Settings(**settings_values)
    route = respx.post(
        "https://chatwoot.example.test/api/v1/accounts/1/"
        "conversations/3/messages"
    ).mock(return_value=Response(200, json={"id": 42}))
    caplog.set_level(logging.INFO, logger="wootpilot.integrations.chatwoot")

    provider_message_id = await ChatwootClient(settings).create_message(
        conversation_id="3",
        content="Suggested reply",
        private=True,
    )

    assert provider_message_id == "42"
    assert route.called
    log_record = next(
        record
        for record in caplog.records
        if getattr(record, "wootpilot_event", "")
        == "chatwoot_api_call_completed"
    )
    assert log_record.wootpilot_fields["operation"] == "create_message"
    assert log_record.wootpilot_fields["status"] == "success"
    assert log_record.wootpilot_fields["status_code"] == 200
    assert log_record.wootpilot_fields["provider_message_id"] == "42"
    assert isinstance(log_record.wootpilot_fields["latency_ms"], int)
    assert "content" not in log_record.wootpilot_fields
    assert "Suggested reply" not in str(log_record.wootpilot_fields)


@respx.mock
async def test_chatwoot_client_sets_conversation_status(caplog) -> None:
    settings_values: dict[str, Any] = {
        "chatwoot_base_url": "https://chatwoot.example.test",
        "chatwoot_account_id": "1",
        "chatwoot_api_token": "token",
        "chatwoot_webhook_secret": "secret",
    }
    settings = Settings(**settings_values)
    route = respx.post(
        "https://chatwoot.example.test/api/v1/accounts/1/"
        "conversations/3/toggle_status",
        json={"status": "pending"},
    ).mock(return_value=Response(200, json={"payload": {"success": True}}))
    caplog.set_level(logging.INFO, logger="wootpilot.integrations.chatwoot")

    await ChatwootClient(settings).set_conversation_status(
        conversation_id="3",
        status="pending",
    )

    assert route.called
    log_record = next(
        record
        for record in caplog.records
        if getattr(record, "wootpilot_event", "")
        == "chatwoot_api_call_completed"
    )
    assert log_record.wootpilot_fields["operation"] == "set_conversation_status"
    assert log_record.wootpilot_fields["status"] == "success"
    assert log_record.wootpilot_fields["status_code"] == 200
    assert log_record.wootpilot_fields["conversation_status"] == "pending"
    assert "token" not in str(log_record.wootpilot_fields)


@respx.mock
async def test_chatwoot_client_adds_conversation_label_without_dropping_existing(
    caplog,
) -> None:
    settings_values: dict[str, Any] = {
        "chatwoot_base_url": "https://chatwoot.example.test",
        "chatwoot_account_id": "1",
        "chatwoot_api_token": "token",
        "chatwoot_webhook_secret": "secret",
    }
    settings = Settings(**settings_values)
    get_route = respx.get(
        "https://chatwoot.example.test/api/v1/accounts/1/conversations/3"
    ).mock(
        return_value=Response(
            200,
            json={
                "payload": {
                    "id": 3,
                    "can_reply": True,
                    "labels": ["existing"],
                    "custom_attributes": {},
                }
            },
        )
    )
    post_route = respx.post(
        "https://chatwoot.example.test/api/v1/accounts/1/conversations/3/labels",
        json={"labels": ["existing", "wootpilot-needs-human"]},
    ).mock(return_value=Response(200, json={"payload": ["existing"]}))
    caplog.set_level(logging.INFO, logger="wootpilot.integrations.chatwoot")

    await ChatwootClient(settings).add_conversation_labels(
        conversation_id="3",
        labels=["wootpilot-needs-human"],
    )

    assert get_route.called
    assert post_route.called
    log_record = next(
        record
        for record in caplog.records
        if getattr(record, "wootpilot_event", "")
        == "chatwoot_api_call_completed"
        and record.wootpilot_fields["operation"] == "set_conversation_labels"
    )
    assert log_record.wootpilot_fields["status"] == "success"
    assert log_record.wootpilot_fields["status_code"] == 200
    assert log_record.wootpilot_fields["label_count"] == 2
    assert "wootpilot-needs-human" not in str(log_record.wootpilot_fields)


@respx.mock
async def test_chatwoot_client_raises_typed_response_error(caplog) -> None:
    settings_values: dict[str, Any] = {
        "chatwoot_base_url": "https://chatwoot.example.test",
        "chatwoot_account_id": "1",
        "chatwoot_api_token": "token",
        "chatwoot_webhook_secret": "secret",
    }
    settings = Settings(**settings_values)
    respx.post(
        "https://chatwoot.example.test/api/v1/accounts/1/"
        "conversations/3/messages"
    ).mock(return_value=Response(503, json={"error": "temporarily unavailable"}))
    caplog.set_level(logging.WARNING, logger="wootpilot.integrations.chatwoot")

    with pytest.raises(ChatwootResponseError) as error:
        await ChatwootClient(settings).create_message(
            conversation_id="3",
            content="Suggested reply",
            private=True,
        )

    assert error.value.code == "chatwoot_http_503"
    assert error.value.retryable is True
    log_record = next(
        record
        for record in caplog.records
        if getattr(record, "wootpilot_event", "")
        == "chatwoot_api_call_completed"
    )
    assert log_record.wootpilot_fields["status"] == "failed"
    assert log_record.wootpilot_fields["status_code"] == 503


@respx.mock
async def test_chatwoot_client_rejects_invalid_success_payload() -> None:
    settings_values: dict[str, Any] = {
        "chatwoot_base_url": "https://chatwoot.example.test",
        "chatwoot_account_id": "1",
        "chatwoot_api_token": "token",
        "chatwoot_webhook_secret": "secret",
    }
    settings = Settings(**settings_values)
    respx.post(
        "https://chatwoot.example.test/api/v1/accounts/1/"
        "conversations/3/messages"
    ).mock(return_value=Response(200, json={"payload": []}))

    with pytest.raises(ChatwootResponseError) as error:
        await ChatwootClient(settings).create_message(
            conversation_id="3",
            content="Suggested reply",
            private=True,
        )

    assert error.value.code == "chatwoot_response_invalid_message_payload"
