from __future__ import annotations

import json
import logging
from hashlib import sha256

from fastapi.testclient import TestClient
from helpers import conversation_event_payload, customer_message_payload, signed_headers
from sqlalchemy import create_engine, text

from wootpilot.domain.models import AgentRunStatus, WorkflowDecision


def test_valid_customer_message_stores_and_runs_shadow(client: TestClient, env) -> None:
    payload = customer_message_payload(
        content="Tenho interesse em chicote aircooled",
        attachments=[
            {
                "id": 55,
                "content_type": "image/png",
                "file_name": "part.png",
                "data_url": "https://chatwoot.example.test/rails/active_storage/55",
            }
        ],
    )
    body, headers = signed_headers(payload)
    response = client.post("/webhooks/chatwoot", content=body, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "processed"
    assert data["workflow_status"] == "proposed"

    db_path = env["WOOTPILOT_DB_URL"].removeprefix("sqlite+aiosqlite:///")
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        assert conn.scalar(text("select count(*) from raw_events")) == 1
        assert conn.scalar(text("select count(*) from conversation_messages")) == 1
        assert conn.scalar(text("select count(*) from agent_runs")) == 1
        assert conn.scalar(text("select count(*) from outbound_actions")) == 0
        stored_hash = conn.scalar(text("select payload_hash from raw_events"))
        message = conn.execute(
            text(
                "select provider, provider_account_id, provider_inbox_id, "
                "provider_conversation_id, provider_message_id, "
                "provider_contact_id, attachments from conversation_messages"
            )
        ).one()
    assert stored_hash == sha256(body).hexdigest()
    assert message.provider == "chatwoot"
    assert message.provider_account_id == "1"
    assert message.provider_inbox_id == "2"
    assert message.provider_conversation_id == "3"
    assert message.provider_message_id == "101"
    assert message.provider_contact_id == "4"
    attachments = json.loads(message.attachments)
    assert attachments[0]["provider_attachment_id"] == "55"
    assert attachments[0]["content_type"] == "image/png"


def test_invalid_signature_rejected_and_stores_nothing(
    client: TestClient, env, caplog
) -> None:
    payload = customer_message_payload()
    body, headers = signed_headers(payload)
    headers["X-Chatwoot-Signature"] = "sha256=bad"
    caplog.set_level(logging.WARNING, logger="wootpilot.api.main")
    response = client.post("/webhooks/chatwoot", content=body, headers=headers)
    assert response.status_code == 401
    log_record = next(
        record
        for record in caplog.records
        if getattr(record, "wootpilot_event", "") == "webhook_authentication_failed"
    )
    assert log_record.wootpilot_fields["provider"] == "chatwoot"
    assert log_record.wootpilot_fields["status_code"] == 401
    assert log_record.wootpilot_fields["reason"] == "invalid Chatwoot signature"
    assert isinstance(log_record.wootpilot_fields["latency_ms"], int)

    db_path = env["WOOTPILOT_DB_URL"].removeprefix("sqlite+aiosqlite:///")
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        assert conn.scalar(text("select count(*) from raw_events")) == 0


def test_duplicate_delivery_does_not_duplicate_message(client: TestClient, env) -> None:
    payload = customer_message_payload()
    body, headers = signed_headers(payload)
    first = client.post("/webhooks/chatwoot", content=body, headers=headers)
    second = client.post("/webhooks/chatwoot", content=body, headers=headers)
    assert first.json()["status"] == "processed"
    assert second.json()["status"] == "duplicate"

    db_path = env["WOOTPILOT_DB_URL"].removeprefix("sqlite+aiosqlite:///")
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        assert conn.scalar(text("select count(*) from raw_events")) == 1
        assert conn.scalar(text("select count(*) from conversation_messages")) == 1


def test_same_message_with_new_delivery_preserves_duplicate_raw_event(
    client: TestClient,
    env,
) -> None:
    payload = customer_message_payload()
    body, headers = signed_headers(payload)
    second_headers = dict(headers)
    second_headers["X-Chatwoot-Delivery"] = "delivery-same-message-new-delivery"

    first = client.post("/webhooks/chatwoot", content=body, headers=headers)
    second = client.post("/webhooks/chatwoot", content=body, headers=second_headers)

    assert first.json()["status"] == "processed"
    assert second.json()["status"] == "duplicate"
    assert second.json()["raw_event_id"] != first.json()["raw_event_id"]

    db_path = env["WOOTPILOT_DB_URL"].removeprefix("sqlite+aiosqlite:///")
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        assert conn.scalar(text("select count(*) from raw_events")) == 2
        assert conn.scalar(text("select count(*) from conversation_messages")) == 1
        duplicate_status = conn.scalar(
            text(
                "select status from raw_events "
                "where provider_event_id = 'delivery-same-message-new-delivery'"
            )
        )
    assert duplicate_status == "duplicate"


def test_ingress_state_is_committed_before_workflow_runs(
    client: TestClient,
    env,
    monkeypatch,
) -> None:
    db_path = env["WOOTPILOT_DB_URL"].removeprefix("sqlite+aiosqlite:///")
    observed = {}

    class ObservingWorkflow:
        def __init__(self, **kwargs) -> None:
            del kwargs

        async def run(self, message, state):
            del message, state
            engine = create_engine(f"sqlite:///{db_path}")
            with engine.connect() as conn:
                observed["raw_events"] = conn.scalar(
                    text("select count(*) from raw_events")
                )
                observed["messages"] = conn.scalar(
                    text("select count(*) from conversation_messages")
                )
                observed["states"] = conn.scalar(
                    text("select count(*) from conversation_states")
                )
            return WorkflowDecision(
                status=AgentRunStatus.proposed,
                summary="Observed durable ingress state.",
            )

    monkeypatch.setattr(
        "wootpilot.application.webhooks.RunSupportWorkflow",
        ObservingWorkflow,
    )

    payload = customer_message_payload()
    body, headers = signed_headers(payload)
    response = client.post("/webhooks/chatwoot", content=body, headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "processed"
    assert observed == {"raw_events": 1, "messages": 1, "states": 1}


def test_mismatched_body_signature_is_rejected(client: TestClient) -> None:
    payload = customer_message_payload()
    body, headers = signed_headers(payload)
    tampered = json.dumps(customer_message_payload(content="tampered")).encode()
    response = client.post("/webhooks/chatwoot", content=tampered, headers=headers)
    assert response.status_code == 401


def test_private_note_echo_is_stored_but_does_not_invoke_workflow(
    client: TestClient, env
) -> None:
    payload = customer_message_payload(
        message_id=202,
        content="Private WootPilot note",
        message_type="outgoing",
        private=True,
        sender_type="user",
    )
    body, headers = signed_headers(payload)
    response = client.post("/webhooks/chatwoot", content=body, headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"

    db_path = env["WOOTPILOT_DB_URL"].removeprefix("sqlite+aiosqlite:///")
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        assert conn.scalar(text("select count(*) from raw_events")) == 1
        assert conn.scalar(text("select count(*) from conversation_messages")) == 1
        assert conn.scalar(text("select count(*) from agent_runs")) == 0
        assert conn.scalar(text("select count(*) from outbound_actions")) == 0


def test_assignment_signal_is_stored_in_conversation_state(
    client: TestClient, env
) -> None:
    payload = customer_message_payload(assignee_id=99, team_id=7)
    body, headers = signed_headers(payload)
    response = client.post("/webhooks/chatwoot", content=body, headers=headers)
    assert response.status_code == 200

    db_path = env["WOOTPILOT_DB_URL"].removeprefix("sqlite+aiosqlite:///")
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "select assigned_agent_id, assigned_team_id "
                "from conversation_states"
            )
        ).one()
    assert row.assigned_agent_id == "99"
    assert row.assigned_team_id == "7"


def test_conversation_update_event_updates_state_without_model_run(
    client: TestClient, env
) -> None:
    payload = conversation_event_payload(
        assignee_id=99,
        team_id=7,
        labels=["wootpilot-paused"],
    )
    body, headers = signed_headers(payload)
    response = client.post("/webhooks/chatwoot", content=body, headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "processed"
    assert "channel_event_id" in response.json()

    db_path = env["WOOTPILOT_DB_URL"].removeprefix("sqlite+aiosqlite:///")
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        state = conn.execute(
            text(
                "select status, replyable, paused, assigned_agent_id, "
                "assigned_team_id from conversation_states"
            )
        ).one()
        assert conn.scalar(text("select count(*) from conversation_messages")) == 0
        assert conn.scalar(text("select count(*) from agent_runs")) == 0
        assert conn.scalar(text("select count(*) from audit_records")) == 1
    assert state.status == "open"
    assert state.replyable == 1
    assert state.paused == 1
    assert state.assigned_agent_id == "99"
    assert state.assigned_team_id == "7"


def test_conversation_status_event_marks_resolved_not_replyable(
    client: TestClient, env
) -> None:
    payload = conversation_event_payload(
        event="conversation_status_changed",
        status="resolved",
        can_reply=True,
    )
    body, headers = signed_headers(payload)
    response = client.post("/webhooks/chatwoot", content=body, headers=headers)
    assert response.status_code == 200

    db_path = env["WOOTPILOT_DB_URL"].removeprefix("sqlite+aiosqlite:///")
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        state = conn.execute(
            text("select status, replyable from conversation_states")
        ).one()
    assert state.status == "resolved"
    assert state.replyable == 0
