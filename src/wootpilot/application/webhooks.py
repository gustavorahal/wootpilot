"""Webhook intake use case for authenticated Chatwoot deliveries."""

from __future__ import annotations

import json
from datetime import timedelta
from hashlib import sha256
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from wootpilot.application.workflow import RunSupportWorkflow
from wootpilot.domain.models import ConversationState
from wootpilot.integrations.chatwoot import (
    event_type,
    provider_event_id,
    translate_channel_event,
    translate_message,
)
from wootpilot.integrations.model import model_port_from_settings
from wootpilot.persistence.repositories import Repository, row_to_state
from wootpilot.settings import Settings
from wootpilot.time import Clock, IdGenerator


class HandleWebhookResult(dict):
    """Dictionary response shape returned directly by the ASGI route."""


class HandleWebhookEvent:
    """Authenticates and stores Chatwoot events before any agent workflow runs."""

    def __init__(
        self,
        *,
        settings: Settings,
        session: AsyncSession,
        clock: Clock | None = None,
        ids: IdGenerator | None = None,
    ):
        self.settings = settings
        self.session = session
        self.repo = Repository(session)
        self.clock = clock or Clock()
        self.ids = ids or IdGenerator()

    async def handle(
        self,
        *,
        body: bytes,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        payload = json.loads(body.decode("utf-8"))
        delivery_id = headers.get(
            self.settings.chatwoot_webhook_delivery_header.lower()
        )
        raw, inserted_raw = await self.repo.insert_raw_event(
            id=self.ids.new(),
            provider="chatwoot",
            provider_event_id=provider_event_id(payload, delivery_id),
            event_type=event_type(payload) or "unknown",
            payload_hash=sha256(body).hexdigest(),
            payload=payload,
            status="received",
            received_at=self.clock.now(),
        )
        if not inserted_raw:
            return {"status": "duplicate", "raw_event_id": raw.id}

        message = translate_message(payload=payload, raw_event_id=raw.id, ids=self.ids)
        if message is None:
            channel_event = translate_channel_event(
                payload=payload,
                raw_event_id=raw.id,
                ids=self.ids,
            )
            if channel_event is not None:
                state = await self._update_channel_state(channel_event)
                await self.repo.update_raw_status(raw.id, "processed")
                await self.repo.insert_audit_record(
                    id=self.ids.new(),
                    raw_event_id=raw.id,
                    normalized_message_id=None,
                    agent_run_id=None,
                    policy_decision_id=None,
                    context_snapshot_ids=[],
                    event_type="channel_state_updated",
                    summary="Chatwoot conversation event updated safety state.",
                    details={
                        "event_type": channel_event.event_type,
                        "tenant_id": channel_event.tenant_id,
                        "channel_id": channel_event.channel_id,
                        "conversation_id": channel_event.conversation_id,
                        "status": state.status,
                        "replyable": state.replyable,
                        "paused": state.paused,
                        "auto_ok": state.auto_ok,
                        "assigned_agent_id": state.assigned_agent_id,
                        "assigned_team_id": state.assigned_team_id,
                    },
                    created_at=self.clock.now(),
                )
                return {
                    "status": "processed",
                    "raw_event_id": raw.id,
                    "channel_event_id": channel_event.id,
                }
            await self.repo.update_raw_status(raw.id, "ignored")
            await self.repo.insert_audit_record(
                id=self.ids.new(),
                raw_event_id=raw.id,
                normalized_message_id=None,
                agent_run_id=None,
                policy_decision_id=None,
                context_snapshot_ids=[],
                event_type="webhook_ignored",
                summary="Chatwoot event did not translate to a customer message.",
                details={"event_type": raw.event_type},
                created_at=self.clock.now(),
            )
            return {"status": "ignored", "raw_event_id": raw.id}

        message, inserted_message = await self.repo.insert_message(message)
        state = await self._update_conversation_state(message)
        if not inserted_message:
            await self.repo.update_raw_status(raw.id, "duplicate")
            return {
                "status": "duplicate",
                "raw_event_id": raw.id,
                "message_id": message.id,
            }

        if not self._message_is_agentable(message):
            await self.repo.update_raw_status(raw.id, "ignored")
            await self.repo.insert_audit_record(
                id=self.ids.new(),
                raw_event_id=raw.id,
                normalized_message_id=message.id,
                agent_run_id=None,
                policy_decision_id=None,
                context_snapshot_ids=[],
                event_type="message_ignored",
                summary="Message was stored but is not agentable.",
                details={
                    "direction": message.direction,
                    "visibility": message.visibility,
                    "author_type": message.author_type,
                },
                created_at=self.clock.now(),
            )
            return {
                "status": "ignored",
                "raw_event_id": raw.id,
                "normalized_message_id": message.id,
            }

        # Commit authenticated ingress state before connector/model work. This
        # keeps duplicate delivery and conversation suppression state durable
        # even if the later workflow call fails or times out.
        await self.session.commit()
        workflow = RunSupportWorkflow(
            settings=self.settings,
            session=self.session,
            model_port=model_port_from_settings(self.settings),
            clock=self.clock,
            ids=self.ids,
        )
        decision = await workflow.run(message, state)
        await self.repo.update_raw_status(raw.id, "processed")
        return {
            "status": "processed",
            "raw_event_id": raw.id,
            "normalized_message_id": message.id,
            "workflow_status": decision.status.value,
            "action_kind": decision.action_kind.value,
        }

    async def _update_conversation_state(self, message) -> ConversationState:
        row = await self.repo.get_or_create_state(
            id=self.ids.new(),
            tenant_id=message.tenant_id,
            channel_id=message.channel_id,
            conversation_id=message.conversation_id,
            now=self.clock.now(),
        )
        metadata = message.metadata.get("chatwoot", {})
        self._apply_channel_metadata(row, metadata)
        if metadata.get("can_reply") is not None:
            row.replyable = bool(metadata["can_reply"])
        if message.direction == "inbound" and message.author_type == "customer":
            row.last_customer_message_at = message.created_at
        if (
            message.direction == "outbound"
            and message.visibility == "public"
            and message.author_type == "human_agent"
        ):
            row.last_human_public_message_at = message.created_at
            row.human_active_until = message.created_at + timedelta(
                seconds=self.settings.human_operator_active_ttl_seconds
            )
        row.updated_at = self.clock.now()
        await self.session.flush()
        return row_to_state(row)

    async def _update_channel_state(self, channel_event) -> ConversationState:
        row = await self.repo.get_or_create_state(
            id=self.ids.new(),
            tenant_id=channel_event.tenant_id,
            channel_id=channel_event.channel_id,
            conversation_id=channel_event.conversation_id,
            now=self.clock.now(),
        )
        self._apply_channel_metadata(
            row,
            {
                "status": channel_event.status,
                "can_reply": channel_event.replyable,
                "paused": channel_event.paused,
                "auto_ok": channel_event.auto_ok,
                "assigned_agent_id": channel_event.assigned_agent_id,
                "assigned_team_id": channel_event.assigned_team_id,
            },
        )
        if channel_event.replyable is not None and row.status != "resolved":
            row.replyable = channel_event.replyable
        row.updated_at = self.clock.now()
        await self.session.flush()
        return row_to_state(row)

    def _apply_channel_metadata(self, row, metadata: dict[str, Any]) -> None:
        labels = set(str(item) for item in metadata.get("labels") or [])
        attributes = metadata.get("custom_attributes") or {}
        row.paused = (
            bool(metadata.get("paused"))
            or "wootpilot-paused" in labels
            or bool(attributes.get("wootpilot_paused"))
        )
        row.auto_ok = (
            bool(metadata.get("auto_ok"))
            or "wootpilot-auto-ok" in labels
            or bool(attributes.get("wootpilot_auto_ok"))
        )
        if metadata.get("status") is not None:
            row.status = str(metadata["status"])
            if row.status == "resolved":
                row.replyable = False
        if "assigned_agent_id" in metadata:
            row.assigned_agent_id = metadata.get("assigned_agent_id")
        if "assigned_team_id" in metadata:
            row.assigned_team_id = metadata.get("assigned_team_id")

    def _message_is_agentable(self, message) -> bool:
        if message.visibility != "public" or message.direction != "inbound":
            return False
        return message.author_type == "customer" and bool(message.content.strip())
