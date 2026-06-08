"""Repository helpers for WootPilot application use cases."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from wootpilot.domain.models import (
    AttachmentMetadata,
    ConversationState,
    NormalizedMessage,
)
from wootpilot.persistence.models import (
    AgentRunRow,
    AuditRecordRow,
    ContextSnapshotRow,
    ConversationMessageRow,
    ConversationStateRow,
    OutboundActionRow,
    PolicyDecisionRow,
    RawEventRow,
)


def row_to_message(row: ConversationMessageRow) -> NormalizedMessage:
    return NormalizedMessage(
        id=row.id,
        raw_event_id=row.raw_event_id,
        tenant_id=row.tenant_id,
        provider=row.provider,
        provider_account_id=row.provider_account_id,
        provider_inbox_id=row.provider_inbox_id,
        provider_conversation_id=row.provider_conversation_id,
        provider_message_id=row.provider_message_id,
        provider_contact_id=row.provider_contact_id,
        channel_id=row.channel_id,
        conversation_id=row.conversation_id,
        message_id=row.message_id,
        contact_id=row.contact_id,
        direction=row.direction,
        visibility=row.visibility,
        author_type=row.author_type,
        content=row.content,
        attachments=[
            AttachmentMetadata.model_validate(attachment)
            for attachment in row.attachments
        ],
        created_at=row.created_at,
        metadata=row.message_metadata,
    )


def row_to_state(row: ConversationStateRow) -> ConversationState:
    return ConversationState(
        id=row.id,
        tenant_id=row.tenant_id,
        channel_id=row.channel_id,
        conversation_id=row.conversation_id,
        human_active_until=row.human_active_until,
        last_human_public_message_at=row.last_human_public_message_at,
        last_customer_message_at=row.last_customer_message_at,
        assigned_agent_id=row.assigned_agent_id,
        assigned_team_id=row.assigned_team_id,
        status=row.status,
        replyable=row.replyable,
        paused=row.paused,
        auto_ok=row.auto_ok,
        updated_at=row.updated_at,
    )


class Repository:
    """Thin SQLAlchemy repository keeping persistence details out of use cases."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def insert_raw_event(
        self,
        *,
        id: str,
        provider: str,
        provider_event_id: str,
        event_type: str,
        payload_hash: str,
        payload: dict[str, Any],
        status: str,
        received_at: datetime,
    ) -> tuple[RawEventRow, bool]:
        row = RawEventRow(
            id=id,
            provider=provider,
            provider_event_id=provider_event_id,
            event_type=event_type,
            payload_hash=payload_hash,
            payload=payload,
            status=status,
            received_at=received_at,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(row)
                await self.session.flush()
            return row, True
        except IntegrityError:
            existing = await self.session.scalar(
                select(RawEventRow).where(
                    RawEventRow.provider == provider,
                    RawEventRow.provider_event_id == provider_event_id,
                )
            )
            if existing is None:
                raise
            return existing, False

    async def update_raw_status(self, raw_event_id: str, status: str) -> None:
        row = await self.session.get(RawEventRow, raw_event_id)
        if row:
            row.status = status
            await self.session.flush()

    async def insert_message(
        self, message: NormalizedMessage
    ) -> tuple[NormalizedMessage, bool]:
        row = ConversationMessageRow(
            id=message.id,
            raw_event_id=message.raw_event_id,
            tenant_id=message.tenant_id,
            provider=message.provider,
            provider_account_id=message.provider_account_id,
            provider_inbox_id=message.provider_inbox_id,
            provider_conversation_id=message.provider_conversation_id,
            provider_message_id=message.provider_message_id,
            provider_contact_id=message.provider_contact_id,
            channel_id=message.channel_id,
            conversation_id=message.conversation_id,
            message_id=message.message_id,
            contact_id=message.contact_id,
            direction=message.direction,
            visibility=message.visibility,
            author_type=message.author_type,
            content=message.content,
            attachments=[
                attachment.model_dump(mode="json") for attachment in message.attachments
            ],
            created_at=message.created_at,
            message_metadata=message.metadata,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(row)
                await self.session.flush()
            return message, True
        except IntegrityError:
            existing = await self.session.scalar(
                select(ConversationMessageRow).where(
                    ConversationMessageRow.tenant_id == message.tenant_id,
                    ConversationMessageRow.channel_id == message.channel_id,
                    ConversationMessageRow.message_id == message.message_id,
                )
            )
            if existing is None:
                raise
            return row_to_message(existing), False

    async def get_or_create_state(
        self,
        *,
        id: str,
        tenant_id: str,
        channel_id: str,
        conversation_id: str,
        now: datetime,
    ) -> ConversationStateRow:
        row = await self.session.scalar(
            select(ConversationStateRow).where(
                ConversationStateRow.tenant_id == tenant_id,
                ConversationStateRow.channel_id == channel_id,
                ConversationStateRow.conversation_id == conversation_id,
            )
        )
        if row is not None:
            return row
        row = ConversationStateRow(
            id=id,
            tenant_id=tenant_id,
            channel_id=channel_id,
            conversation_id=conversation_id,
            replyable=True,
            paused=False,
            auto_ok=False,
            updated_at=now,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def get_conversation_state(
        self,
        *,
        tenant_id: str,
        channel_id: str,
        conversation_id: str,
    ) -> ConversationStateRow | None:
        return await self.session.scalar(
            select(ConversationStateRow).where(
                ConversationStateRow.tenant_id == tenant_id,
                ConversationStateRow.channel_id == channel_id,
                ConversationStateRow.conversation_id == conversation_id,
            )
        )

    async def insert_context_snapshot(
        self,
        *,
        id: str,
        tenant_id: str,
        conversation_id: str,
        kind: str,
        snapshot: dict[str, Any],
        created_at: datetime,
    ) -> None:
        self.session.add(
            ContextSnapshotRow(
                id=id,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                kind=kind,
                snapshot=snapshot,
                created_at=created_at,
            )
        )
        await self.session.flush()

    async def insert_agent_run(
        self,
        *,
        id: str,
        normalized_message_id: str,
        raw_event_id: str,
        bot_mode: str,
        status: str,
        workflow_decision: dict[str, Any],
        model_metadata: dict[str, Any],
        created_at: datetime,
    ) -> None:
        self.session.add(
            AgentRunRow(
                id=id,
                normalized_message_id=normalized_message_id,
                raw_event_id=raw_event_id,
                bot_mode=bot_mode,
                status=status,
                workflow_decision=workflow_decision,
                model_metadata=model_metadata,
                created_at=created_at,
            )
        )
        await self.session.flush()

    async def insert_policy_decision(
        self,
        *,
        id: str,
        agent_run_id: str | None,
        normalized_message_id: str,
        stage: str,
        outcome: str,
        rule_ids: list[str],
        details: dict[str, Any],
        created_at: datetime,
    ) -> None:
        self.session.add(
            PolicyDecisionRow(
                id=id,
                agent_run_id=agent_run_id,
                normalized_message_id=normalized_message_id,
                stage=stage,
                outcome=outcome,
                rule_ids=rule_ids,
                details=details,
                created_at=created_at,
            )
        )
        await self.session.flush()

    async def insert_outbound_action(
        self,
        *,
        id: str,
        agent_run_id: str,
        tenant_id: str,
        channel_id: str,
        conversation_id: str,
        source_message_id: str,
        action_kind: str,
        content: str,
        status: str,
        idempotency_key: str,
        created_at: datetime,
        safety_context: dict[str, Any] | None = None,
    ) -> bool:
        try:
            async with self.session.begin_nested():
                self.session.add(
                    OutboundActionRow(
                        id=id,
                        agent_run_id=agent_run_id,
                        tenant_id=tenant_id,
                        channel_id=channel_id,
                        conversation_id=conversation_id,
                        source_message_id=source_message_id,
                        action_kind=action_kind,
                        content=content,
                        safety_context=safety_context or {},
                        status=status,
                        idempotency_key=idempotency_key,
                        created_at=created_at,
                        updated_at=created_at,
                    )
                )
                await self.session.flush()
        except IntegrityError:
            return False
        return True

    async def list_queued_outbound_actions(
        self, *, limit: int = 10, now: datetime
    ) -> list[OutboundActionRow]:
        statement = queued_outbound_actions_statement(
            limit=limit,
            now=now,
            dialect_name=self.session.bind.dialect.name if self.session.bind else "",
        )
        result = await self.session.scalars(
            statement
        )
        return list(result)

    async def mark_outbound_action(
        self,
        *,
        action_id: str,
        status: str,
        updated_at: datetime,
        provider_message_id: str | None = None,
        failure_reason: str | None = None,
        attempt_count: int | None = None,
        next_attempt_at: datetime | None = None,
        clear_next_attempt_at: bool = False,
        error_code: str | None = None,
    ) -> None:
        row = await self.session.get(OutboundActionRow, action_id)
        if row is None:
            return
        row.status = status
        row.updated_at = updated_at
        if provider_message_id is not None:
            row.provider_message_id = provider_message_id
        if failure_reason is not None:
            row.failure_reason = failure_reason
        if attempt_count is not None:
            row.attempt_count = attempt_count
        if clear_next_attempt_at:
            row.next_attempt_at = None
        elif next_attempt_at is not None:
            row.next_attempt_at = next_attempt_at
        if error_code is not None:
            row.error_code = error_code
        await self.session.flush()

    async def insert_audit_record(
        self,
        *,
        id: str,
        raw_event_id: str | None,
        normalized_message_id: str | None,
        agent_run_id: str | None,
        policy_decision_id: str | None,
        context_snapshot_ids: list[str],
        event_type: str,
        summary: str,
        details: dict[str, Any],
        created_at: datetime,
    ) -> None:
        self.session.add(
            AuditRecordRow(
                id=id,
                raw_event_id=raw_event_id,
                normalized_message_id=normalized_message_id,
                agent_run_id=agent_run_id,
                policy_decision_id=policy_decision_id,
                context_snapshot_ids=context_snapshot_ids,
                event_type=event_type,
                summary=summary,
                details=details,
                created_at=created_at,
            )
        )
        await self.session.flush()


def queued_outbound_actions_statement(
    *, limit: int, now: datetime, dialect_name: str
):
    """Build the worker dequeue query.

    PostgreSQL workers use row-level locking with SKIP LOCKED so concurrent
    workers do not execute the same action. SQLite intentionally avoids this
    because the alpha profile runs a single executor.
    """

    statement = (
        select(OutboundActionRow)
        .where(
            or_(
                OutboundActionRow.status == "queued",
                and_(
                    OutboundActionRow.status == "retryable_failure",
                    OutboundActionRow.next_attempt_at.is_not(None),
                    OutboundActionRow.next_attempt_at <= now,
                ),
            )
        )
        .order_by(OutboundActionRow.created_at)
        .limit(limit)
    )
    if dialect_name == "postgresql":
        return statement.with_for_update(skip_locked=True)
    return statement
