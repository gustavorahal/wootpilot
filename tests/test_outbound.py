from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from wootpilot.application.errors import ChatwootResponseError
from wootpilot.application.outbound import ExecuteOutboundActions
from wootpilot.domain.models import (
    AgentActionKind,
    AutomationMode,
    OutboundActionStatus,
    RuntimeEnvironment,
)
from wootpilot.integrations.chatwoot import ChannelSafetyState
from wootpilot.persistence.database import init_database, make_session_factory
from wootpilot.persistence.models import (
    AgentRunRow,
    ConversationMessageRow,
    RawEventRow,
)
from wootpilot.persistence.repositories import Repository
from wootpilot.settings import Settings
from wootpilot.time import Clock, IdGenerator


class FakeChatwootWriter:
    def __init__(self, safety: ChannelSafetyState | None = None) -> None:
        self.calls = []
        self.status_calls = []
        self.label_calls = []
        self.safety = safety

    async def create_message(
        self, *, conversation_id: str, content: str, private: bool
    ):
        self.calls.append(
            {
                "conversation_id": conversation_id,
                "content": content,
                "private": private,
            }
        )
        return "provider-123"

    async def get_conversation_safety(self, *, conversation_id: str):
        return self.safety or ChannelSafetyState(
            conversation_id=conversation_id,
            replyable=True,
        )

    async def set_conversation_status(
        self, *, conversation_id: str, status: str
    ) -> None:
        self.status_calls.append(
            {"conversation_id": conversation_id, "status": status}
        )

    async def add_conversation_labels(
        self, *, conversation_id: str, labels: list[str]
    ) -> None:
        self.label_calls.append(
            {"conversation_id": conversation_id, "labels": labels}
        )


class ObservingChatwootWriter(FakeChatwootWriter):
    def __init__(self, db_path: Path) -> None:
        super().__init__()
        self.db_path = db_path
        self.status_seen_during_safety: tuple[str, str | None] | None = None
        self.status_seen_during_send: tuple[str, str | None] | None = None

    async def get_conversation_safety(self, *, conversation_id: str):
        self.status_seen_during_safety = outbound_status(self.db_path)
        return await super().get_conversation_safety(conversation_id=conversation_id)

    async def create_message(
        self, *, conversation_id: str, content: str, private: bool
    ):
        self.status_seen_during_send = outbound_status(self.db_path)
        return await super().create_message(
            conversation_id=conversation_id,
            content=content,
            private=private,
        )


class RetryableFailingChatwootWriter(FakeChatwootWriter):
    async def create_message(
        self, *, conversation_id: str, content: str, private: bool
    ):
        self.calls.append(
            {
                "conversation_id": conversation_id,
                "content": content,
                "private": private,
            }
        )
        raise ChatwootResponseError(
            "chatwoot_http_503",
            operation="create_message",
            retryable=True,
            status_code=503,
        )


class PermanentFailingChatwootWriter(FakeChatwootWriter):
    async def create_message(
        self, *, conversation_id: str, content: str, private: bool
    ):
        self.calls.append(
            {
                "conversation_id": conversation_id,
                "content": content,
                "private": private,
            }
        )
        raise ChatwootResponseError(
            "chatwoot_http_400",
            operation="create_message",
            retryable=False,
            status_code=400,
        )


class BuggyChatwootWriter(FakeChatwootWriter):
    async def create_message(
        self, *, conversation_id: str, content: str, private: bool
    ):
        del conversation_id, content, private
        raise TypeError("local writer bug")


async def test_outbound_executor_sends_private_note(tmp_path: Path, caplog) -> None:
    db_path = tmp_path / "outbound.db"
    settings = Settings(
        env=RuntimeEnvironment.test,
        db_url=f"sqlite+aiosqlite:///{db_path}",
        chatwoot_webhook_secret="secret",
    )
    await init_database(settings)
    factory = make_session_factory(settings)
    ids = IdGenerator()
    now = Clock().now()
    async with factory() as session:
        await create_parent_agent_run(session, now)
        repo = Repository(session)
        await repo.insert_outbound_action(
            id=ids.new(),
            agent_run_id="agent-run-1",
            tenant_id="1",
            channel_id="2",
            conversation_id="3",
            source_message_id="4",
            action_kind=AgentActionKind.private_note,
            content="Suggested reply",
            status=OutboundActionStatus.queued,
            idempotency_key="1:2:3:4:private_note",
            created_at=now,
        )
        await session.commit()

    writer = FakeChatwootWriter()
    caplog.set_level(logging.INFO, logger="wootpilot.application.outbound")
    async with factory() as session:
        executor = ExecuteOutboundActions(
            settings=settings,
            session=session,
            chatwoot=writer,  # type: ignore[arg-type]
        )
        counts = await executor.run_once()
        await session.commit()

    assert counts == {"sent": 1, "blocked": 0, "failed": 0}
    assert writer.calls == [
        {"conversation_id": "3", "content": "Suggested reply", "private": True}
    ]
    log_record = next(
        record
        for record in caplog.records
        if getattr(record, "wootpilot_event", "") == "outbound_action_completed"
    )
    assert log_record.wootpilot_fields["status"] == "sent"
    assert log_record.wootpilot_fields["provider_message_id"] == "provider-123"
    assert "content" not in log_record.wootpilot_fields
    assert "Suggested reply" not in str(log_record.wootpilot_fields)
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        row = conn.execute(
            text("select status, provider_message_id from outbound_actions")
        ).one()
    assert row.status == "sent"
    assert row.provider_message_id == "provider-123"


async def test_public_reply_executor_sends_public_message_when_state_is_safe(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "public-safe.db"
    settings = Settings(
        env=RuntimeEnvironment.test,
        automation_mode=AutomationMode.public_reply,
        db_url=f"sqlite+aiosqlite:///{db_path}",
        chatwoot_webhook_secret="secret",
    )
    await init_database(settings)
    factory = make_session_factory(settings)
    ids = IdGenerator()
    now = Clock().now()
    async with factory() as session:
        await create_parent_agent_run(session, now)
        repo = Repository(session)
        await repo.get_or_create_state(
            id=ids.new(),
            tenant_id="1",
            channel_id="2",
            conversation_id="3",
            now=now,
        )
        await repo.insert_outbound_action(
            id=ids.new(),
            agent_run_id="agent-run-1",
            tenant_id="1",
            channel_id="2",
            conversation_id="3",
            source_message_id="4",
            action_kind=AgentActionKind.public_message,
            content="Thanks, this product is available.",
            status=OutboundActionStatus.queued,
            idempotency_key="1:2:3:4:public_message",
            created_at=now,
        )
        await session.commit()

    writer = FakeChatwootWriter()
    async with factory() as session:
        counts = await ExecuteOutboundActions(
            settings=settings,
            session=session,
            chatwoot=writer,  # type: ignore[arg-type]
        ).run_once()
        await session.commit()

    assert counts == {"sent": 1, "blocked": 0, "failed": 0}
    assert writer.calls == [
        {
            "conversation_id": "3",
            "content": "Thanks, this product is available.",
            "private": False,
        }
    ]
    assert writer.status_calls == []


async def test_outbound_executor_commits_executing_before_channel_calls(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "public-transaction-boundary.db"
    settings = Settings(
        env=RuntimeEnvironment.test,
        automation_mode=AutomationMode.public_reply,
        db_url=f"sqlite+aiosqlite:///{db_path}",
        chatwoot_webhook_secret="secret",
    )
    await init_database(settings)
    factory = make_session_factory(settings)
    ids = IdGenerator()
    now = Clock().now()
    async with factory() as session:
        await create_parent_agent_run(session, now)
        repo = Repository(session)
        await repo.get_or_create_state(
            id=ids.new(),
            tenant_id="1",
            channel_id="2",
            conversation_id="3",
            now=now,
        )
        await queue_public_action(repo, ids, now)
        await session.commit()

    writer = ObservingChatwootWriter(db_path)
    async with factory() as session:
        counts = await ExecuteOutboundActions(
            settings=settings,
            session=session,
            chatwoot=writer,  # type: ignore[arg-type]
        ).run_once()

    assert counts == {"sent": 1, "blocked": 0, "failed": 0}
    assert writer.status_seen_during_safety == ("executing", None)
    assert writer.status_seen_during_send == ("executing", None)
    assert outbound_status(db_path) == ("sent", None)


async def test_public_reply_executor_sets_status_after_public_message_when_enabled(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "public-status-update.db"
    settings = Settings(
        env=RuntimeEnvironment.test,
        automation_mode=AutomationMode.public_reply,
        db_url=f"sqlite+aiosqlite:///{db_path}",
        chatwoot_webhook_secret="secret",
        chatwoot_update_status_after_public_reply=True,
        chatwoot_public_reply_status="pending",
    )
    await init_database(settings)
    factory = make_session_factory(settings)
    ids = IdGenerator()
    now = Clock().now()
    async with factory() as session:
        await create_parent_agent_run(session, now)
        repo = Repository(session)
        await repo.get_or_create_state(
            id=ids.new(),
            tenant_id="1",
            channel_id="2",
            conversation_id="3",
            now=now,
        )
        await queue_public_action(repo, ids, now)
        await session.commit()

    writer = FakeChatwootWriter()
    async with factory() as session:
        counts = await ExecuteOutboundActions(
            settings=settings,
            session=session,
            chatwoot=writer,  # type: ignore[arg-type]
        ).run_once()
        await session.commit()

    assert counts == {"sent": 1, "blocked": 0, "failed": 0}
    assert writer.calls == [
        {
            "conversation_id": "3",
            "content": "Thanks, this product is available.",
            "private": False,
        }
    ]
    assert writer.status_calls == [{"conversation_id": "3", "status": "pending"}]
    assert outbound_status(db_path) == ("sent", None)


async def test_retryable_chatwoot_failure_schedules_next_attempt(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "private-retryable-failure.db"
    settings = Settings(
        env=RuntimeEnvironment.test,
        db_url=f"sqlite+aiosqlite:///{db_path}",
        chatwoot_webhook_secret="secret",
        outbound_retry_delay_seconds=120,
    )
    await init_database(settings)
    factory = make_session_factory(settings)
    ids = IdGenerator()
    now = Clock().now()
    async with factory() as session:
        await create_parent_agent_run(session, now)
        repo = Repository(session)
        await repo.insert_outbound_action(
            id=ids.new(),
            agent_run_id="agent-run-1",
            tenant_id="1",
            channel_id="2",
            conversation_id="3",
            source_message_id="4",
            action_kind=AgentActionKind.private_note,
            content="Suggested reply",
            status=OutboundActionStatus.queued,
            idempotency_key="1:2:3:4:private_note",
            created_at=now,
        )
        await session.commit()

    writer = RetryableFailingChatwootWriter()
    async with factory() as session:
        counts = await ExecuteOutboundActions(
            settings=settings,
            session=session,
            chatwoot=writer,  # type: ignore[arg-type]
        ).run_once()

    assert counts == {"sent": 0, "blocked": 0, "failed": 1}
    assert writer.calls == [
        {"conversation_id": "3", "content": "Suggested reply", "private": True}
    ]
    state = outbound_retry_state(db_path)
    assert state["status"] == "retryable_failure"
    assert state["attempt_count"] == 1
    assert state["next_attempt_at"] is not None
    assert state["error_code"] == "chatwoot_http_503"
    assert state["row_count"] == 1


async def test_unexpected_chatwoot_writer_error_escapes(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "private-unexpected-failure.db"
    settings = Settings(
        env=RuntimeEnvironment.test,
        db_url=f"sqlite+aiosqlite:///{db_path}",
        chatwoot_webhook_secret="secret",
    )
    await init_database(settings)
    factory = make_session_factory(settings)
    ids = IdGenerator()
    now = Clock().now()
    async with factory() as session:
        await create_parent_agent_run(session, now)
        repo = Repository(session)
        await repo.insert_outbound_action(
            id=ids.new(),
            agent_run_id="agent-run-1",
            tenant_id="1",
            channel_id="2",
            conversation_id="3",
            source_message_id="4",
            action_kind=AgentActionKind.private_note,
            content="Suggested reply",
            status=OutboundActionStatus.queued,
            idempotency_key="1:2:3:4:private_note",
            created_at=now,
        )
        await session.commit()

    async with factory() as session:
        with pytest.raises(TypeError, match="local writer bug"):
            await ExecuteOutboundActions(
                settings=settings,
                session=session,
                chatwoot=BuggyChatwootWriter(),  # type: ignore[arg-type]
            ).run_once()


async def test_private_review_note_marks_conversation_as_needing_human(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "private-review-label.db"
    settings = Settings(
        env=RuntimeEnvironment.test,
        db_url=f"sqlite+aiosqlite:///{db_path}",
        chatwoot_webhook_secret="secret",
    )
    await init_database(settings)
    factory = make_session_factory(settings)
    ids = IdGenerator()
    now = Clock().now()
    async with factory() as session:
        await create_parent_agent_run(session, now)
        repo = Repository(session)
        await repo.insert_outbound_action(
            id=ids.new(),
            agent_run_id="agent-run-1",
            tenant_id="1",
            channel_id="2",
            conversation_id="3",
            source_message_id="4",
            action_kind=AgentActionKind.private_note,
            content="WootPilot did not send a public reply.",
            status=OutboundActionStatus.queued,
            idempotency_key="1:2:3:4:private_review",
            safety_context={
                "workflow_rule_ids": ["public.risk_requires_review"],
                "workflow_risk_reasons": ["intent.refund"],
            },
            created_at=now,
        )
        await session.commit()

    writer = FakeChatwootWriter()
    async with factory() as session:
        counts = await ExecuteOutboundActions(
            settings=settings,
            session=session,
            chatwoot=writer,  # type: ignore[arg-type]
        ).run_once()

    assert counts == {"sent": 1, "blocked": 0, "failed": 0}
    assert writer.label_calls == [
        {"conversation_id": "3", "labels": ["wootpilot-needs-human"]}
    ]
    assert outbound_status(db_path) == ("sent", None)


async def test_plain_private_note_does_not_mark_needs_human(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "private-plain-no-label.db"
    settings = Settings(
        env=RuntimeEnvironment.test,
        db_url=f"sqlite+aiosqlite:///{db_path}",
        chatwoot_webhook_secret="secret",
    )
    await init_database(settings)
    factory = make_session_factory(settings)
    ids = IdGenerator()
    now = Clock().now()
    async with factory() as session:
        await create_parent_agent_run(session, now)
        repo = Repository(session)
        await repo.insert_outbound_action(
            id=ids.new(),
            agent_run_id="agent-run-1",
            tenant_id="1",
            channel_id="2",
            conversation_id="3",
            source_message_id="4",
            action_kind=AgentActionKind.private_note,
            content="Suggested reply",
            status=OutboundActionStatus.queued,
            idempotency_key="1:2:3:4:private_note_plain",
            created_at=now,
        )
        await session.commit()

    writer = FakeChatwootWriter()
    async with factory() as session:
        counts = await ExecuteOutboundActions(
            settings=settings,
            session=session,
            chatwoot=writer,  # type: ignore[arg-type]
        ).run_once()

    assert counts == {"sent": 1, "blocked": 0, "failed": 0}
    assert writer.label_calls == []


async def test_due_retryable_action_is_retried_and_marked_sent(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "private-retryable-due.db"
    settings = Settings(
        env=RuntimeEnvironment.test,
        db_url=f"sqlite+aiosqlite:///{db_path}",
        chatwoot_webhook_secret="secret",
    )
    await init_database(settings)
    factory = make_session_factory(settings)
    ids = IdGenerator()
    now = Clock().now()
    action_id = ids.new()
    async with factory() as session:
        await create_parent_agent_run(session, now)
        repo = Repository(session)
        await repo.insert_outbound_action(
            id=action_id,
            agent_run_id="agent-run-1",
            tenant_id="1",
            channel_id="2",
            conversation_id="3",
            source_message_id="4",
            action_kind=AgentActionKind.private_note,
            content="Suggested reply",
            status=OutboundActionStatus.queued,
            idempotency_key="1:2:3:4:private_note",
            created_at=now,
        )
        await repo.mark_outbound_action(
            action_id=action_id,
            status=OutboundActionStatus.retryable_failure,
            updated_at=now,
            attempt_count=1,
            next_attempt_at=now - timedelta(seconds=1),
            error_code="TimeoutError",
        )
        await session.commit()

    writer = FakeChatwootWriter()
    async with factory() as session:
        counts = await ExecuteOutboundActions(
            settings=settings,
            session=session,
            chatwoot=writer,  # type: ignore[arg-type]
        ).run_once()

    assert counts == {"sent": 1, "blocked": 0, "failed": 0}
    assert writer.calls == [
        {"conversation_id": "3", "content": "Suggested reply", "private": True}
    ]
    state = outbound_retry_state(db_path)
    assert state["status"] == "sent"
    assert state["attempt_count"] == 1
    assert state["next_attempt_at"] is None
    assert state["provider_message_id"] == "provider-123"


async def test_not_due_retryable_action_is_not_retried(tmp_path: Path) -> None:
    db_path = tmp_path / "private-retryable-not-due.db"
    settings = Settings(
        env=RuntimeEnvironment.test,
        db_url=f"sqlite+aiosqlite:///{db_path}",
        chatwoot_webhook_secret="secret",
    )
    await init_database(settings)
    factory = make_session_factory(settings)
    ids = IdGenerator()
    now = Clock().now()
    action_id = ids.new()
    async with factory() as session:
        await create_parent_agent_run(session, now)
        repo = Repository(session)
        await repo.insert_outbound_action(
            id=action_id,
            agent_run_id="agent-run-1",
            tenant_id="1",
            channel_id="2",
            conversation_id="3",
            source_message_id="4",
            action_kind=AgentActionKind.private_note,
            content="Suggested reply",
            status=OutboundActionStatus.queued,
            idempotency_key="1:2:3:4:private_note",
            created_at=now,
        )
        await repo.mark_outbound_action(
            action_id=action_id,
            status=OutboundActionStatus.retryable_failure,
            updated_at=now,
            attempt_count=1,
            next_attempt_at=now + timedelta(hours=1),
            error_code="TimeoutError",
        )
        await session.commit()

    writer = FakeChatwootWriter()
    async with factory() as session:
        counts = await ExecuteOutboundActions(
            settings=settings,
            session=session,
            chatwoot=writer,  # type: ignore[arg-type]
        ).run_once()

    assert counts == {"sent": 0, "blocked": 0, "failed": 0}
    assert writer.calls == []
    state = outbound_retry_state(db_path)
    assert state["status"] == "retryable_failure"
    assert state["attempt_count"] == 1
    assert state["next_attempt_at"] is not None


async def test_retryable_failure_becomes_permanent_at_max_attempts(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "private-retryable-max-attempts.db"
    settings = Settings(
        env=RuntimeEnvironment.test,
        db_url=f"sqlite+aiosqlite:///{db_path}",
        chatwoot_webhook_secret="secret",
        outbound_max_attempts=1,
    )
    await init_database(settings)
    factory = make_session_factory(settings)
    ids = IdGenerator()
    now = Clock().now()
    async with factory() as session:
        await create_parent_agent_run(session, now)
        repo = Repository(session)
        await repo.insert_outbound_action(
            id=ids.new(),
            agent_run_id="agent-run-1",
            tenant_id="1",
            channel_id="2",
            conversation_id="3",
            source_message_id="4",
            action_kind=AgentActionKind.private_note,
            content="Suggested reply",
            status=OutboundActionStatus.queued,
            idempotency_key="1:2:3:4:private_note",
            created_at=now,
        )
        await session.commit()

    writer = RetryableFailingChatwootWriter()
    async with factory() as session:
        counts = await ExecuteOutboundActions(
            settings=settings,
            session=session,
            chatwoot=writer,  # type: ignore[arg-type]
        ).run_once()

    assert counts == {"sent": 0, "blocked": 0, "failed": 1}
    state = outbound_retry_state(db_path)
    assert state["status"] == "permanent_failure"
    assert state["attempt_count"] == 1
    assert state["next_attempt_at"] is None


async def test_public_message_is_blocked_when_human_becomes_active(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "public-blocked.db"
    settings = Settings(
        env=RuntimeEnvironment.test,
        automation_mode=AutomationMode.public_reply,
        db_url=f"sqlite+aiosqlite:///{db_path}",
        chatwoot_webhook_secret="secret",
    )
    await init_database(settings)
    factory = make_session_factory(settings)
    ids = IdGenerator()
    clock = Clock()
    now = clock.now()
    async with factory() as session:
        await create_parent_agent_run(session, now)
        repo = Repository(session)
        state = await repo.get_or_create_state(
            id=ids.new(),
            tenant_id="1",
            channel_id="2",
            conversation_id="3",
            now=now,
        )
        state.human_active_until = now + timedelta(minutes=30)
        await repo.insert_outbound_action(
            id=ids.new(),
            agent_run_id="agent-run-1",
            tenant_id="1",
            channel_id="2",
            conversation_id="3",
            source_message_id="4",
            action_kind=AgentActionKind.public_message,
            content="Thanks, this product is available.",
            status=OutboundActionStatus.queued,
            idempotency_key="1:2:3:4:public_message",
            created_at=now,
        )
        await session.commit()

    writer = FakeChatwootWriter()
    async with factory() as session:
        counts = await ExecuteOutboundActions(
            settings=settings,
            session=session,
            chatwoot=writer,  # type: ignore[arg-type]
            clock=clock,
        ).run_once()
        await session.commit()

    assert counts == {"sent": 0, "blocked": 1, "failed": 0}
    assert writer.calls == []
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        row = conn.execute(
            text("select status, failure_reason from outbound_actions")
        ).one()
    assert row.status == "blocked_by_policy"
    assert row.failure_reason == "conversation.human_active"


async def test_public_message_is_blocked_when_conversation_is_paused(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "public-paused-blocked.db"
    settings = Settings(
        env=RuntimeEnvironment.test,
        automation_mode=AutomationMode.public_reply,
        db_url=f"sqlite+aiosqlite:///{db_path}",
        chatwoot_webhook_secret="secret",
    )
    await init_database(settings)
    factory = make_session_factory(settings)
    ids = IdGenerator()
    now = Clock().now()
    async with factory() as session:
        await create_parent_agent_run(session, now)
        repo = Repository(session)
        state = await repo.get_or_create_state(
            id=ids.new(),
            tenant_id="1",
            channel_id="2",
            conversation_id="3",
            now=now,
        )
        state.paused = True
        await queue_public_action(repo, ids, now)
        await session.commit()

    writer = FakeChatwootWriter()
    async with factory() as session:
        counts = await ExecuteOutboundActions(
            settings=settings,
            session=session,
            chatwoot=writer,  # type: ignore[arg-type]
        ).run_once()
        await session.commit()

    assert counts == {"sent": 0, "blocked": 1, "failed": 0}
    assert writer.calls == []
    assert outbound_status(db_path) == (
        "blocked_by_policy",
        "conversation.wootpilot_paused",
    )


async def test_public_message_is_blocked_when_channel_is_not_replyable(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "public-channel-blocked.db"
    settings = Settings(
        env=RuntimeEnvironment.test,
        automation_mode=AutomationMode.public_reply,
        db_url=f"sqlite+aiosqlite:///{db_path}",
        chatwoot_webhook_secret="secret",
    )
    await init_database(settings)
    factory = make_session_factory(settings)
    ids = IdGenerator()
    now = Clock().now()
    async with factory() as session:
        await create_parent_agent_run(session, now)
        repo = Repository(session)
        await repo.get_or_create_state(
            id=ids.new(),
            tenant_id="1",
            channel_id="2",
            conversation_id="3",
            now=now,
        )
        await repo.insert_outbound_action(
            id=ids.new(),
            agent_run_id="agent-run-1",
            tenant_id="1",
            channel_id="2",
            conversation_id="3",
            source_message_id="4",
            action_kind=AgentActionKind.public_message,
            content="Thanks, this product is available.",
            status=OutboundActionStatus.queued,
            idempotency_key="1:2:3:4:public_message",
            created_at=now,
        )
        await session.commit()

    writer = FakeChatwootWriter(
        safety=ChannelSafetyState(conversation_id="3", replyable=False)
    )
    async with factory() as session:
        counts = await ExecuteOutboundActions(
            settings=settings,
            session=session,
            chatwoot=writer,  # type: ignore[arg-type]
        ).run_once()
        await session.commit()

    assert counts == {"sent": 0, "blocked": 1, "failed": 0}
    assert writer.calls == []
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        row = conn.execute(
            text("select status, failure_reason from outbound_actions")
        ).one()
    assert row.status == "blocked_by_policy"
    assert row.failure_reason == "channel.not_replyable"


async def test_public_message_is_blocked_when_channel_is_paused(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "public-channel-paused-blocked.db"
    settings = Settings(
        env=RuntimeEnvironment.test,
        automation_mode=AutomationMode.public_reply,
        db_url=f"sqlite+aiosqlite:///{db_path}",
        chatwoot_webhook_secret="secret",
    )
    await init_database(settings)
    factory = make_session_factory(settings)
    ids = IdGenerator()
    now = Clock().now()
    async with factory() as session:
        await create_parent_agent_run(session, now)
        repo = Repository(session)
        await repo.get_or_create_state(
            id=ids.new(),
            tenant_id="1",
            channel_id="2",
            conversation_id="3",
            now=now,
        )
        await queue_public_action(repo, ids, now)
        await session.commit()

    writer = FakeChatwootWriter(
        safety=ChannelSafetyState(conversation_id="3", replyable=True, paused=True)
    )
    async with factory() as session:
        counts = await ExecuteOutboundActions(
            settings=settings,
            session=session,
            chatwoot=writer,  # type: ignore[arg-type]
        ).run_once()
        await session.commit()

    assert counts == {"sent": 0, "blocked": 1, "failed": 0}
    assert writer.calls == []
    assert outbound_status(db_path) == (
        "blocked_by_policy",
        "channel.wootpilot_paused",
    )


async def test_public_message_is_blocked_when_channel_id_mismatches(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "public-channel-id-mismatch.db"
    settings = Settings(
        env=RuntimeEnvironment.test,
        automation_mode=AutomationMode.public_reply,
        db_url=f"sqlite+aiosqlite:///{db_path}",
        chatwoot_webhook_secret="secret",
    )
    await init_database(settings)
    factory = make_session_factory(settings)
    ids = IdGenerator()
    now = Clock().now()
    async with factory() as session:
        await create_parent_agent_run(session, now)
        repo = Repository(session)
        await repo.get_or_create_state(
            id=ids.new(),
            tenant_id="1",
            channel_id="2",
            conversation_id="3",
            now=now,
        )
        await queue_public_action(repo, ids, now)
        await session.commit()

    writer = FakeChatwootWriter(
        safety=ChannelSafetyState(conversation_id="different", replyable=True)
    )
    async with factory() as session:
        counts = await ExecuteOutboundActions(
            settings=settings,
            session=session,
            chatwoot=writer,  # type: ignore[arg-type]
        ).run_once()
        await session.commit()

    assert counts == {"sent": 0, "blocked": 1, "failed": 0}
    assert writer.calls == []
    assert outbound_status(db_path) == (
        "blocked_by_policy",
        "conversation.id_mismatch",
    )


async def test_public_message_is_blocked_when_conversation_is_assigned(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "public-assigned-blocked.db"
    settings = Settings(
        env=RuntimeEnvironment.test,
        automation_mode=AutomationMode.public_reply,
        db_url=f"sqlite+aiosqlite:///{db_path}",
        chatwoot_webhook_secret="secret",
    )
    await init_database(settings)
    factory = make_session_factory(settings)
    ids = IdGenerator()
    now = Clock().now()
    async with factory() as session:
        await create_parent_agent_run(session, now)
        repo = Repository(session)
        state = await repo.get_or_create_state(
            id=ids.new(),
            tenant_id="1",
            channel_id="2",
            conversation_id="3",
            now=now,
        )
        state.assigned_agent_id = "99"
        await repo.insert_outbound_action(
            id=ids.new(),
            agent_run_id="agent-run-1",
            tenant_id="1",
            channel_id="2",
            conversation_id="3",
            source_message_id="4",
            action_kind=AgentActionKind.public_message,
            content="Thanks, this product is available.",
            status=OutboundActionStatus.queued,
            idempotency_key="1:2:3:4:public_message",
            created_at=now,
        )
        await session.commit()

    writer = FakeChatwootWriter()
    async with factory() as session:
        counts = await ExecuteOutboundActions(
            settings=settings,
            session=session,
            chatwoot=writer,  # type: ignore[arg-type]
        ).run_once()
        await session.commit()

    assert counts == {"sent": 0, "blocked": 1, "failed": 0}
    assert writer.calls == []
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        row = conn.execute(
            text("select status, failure_reason from outbound_actions")
        ).one()
    assert row.status == "blocked_by_policy"
    assert row.failure_reason == "conversation.assigned_to_human"


async def test_public_message_is_blocked_when_conversation_is_resolved(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "public-resolved-blocked.db"
    settings = Settings(
        env=RuntimeEnvironment.test,
        automation_mode=AutomationMode.public_reply,
        db_url=f"sqlite+aiosqlite:///{db_path}",
        chatwoot_webhook_secret="secret",
    )
    await init_database(settings)
    factory = make_session_factory(settings)
    ids = IdGenerator()
    now = Clock().now()
    async with factory() as session:
        await create_parent_agent_run(session, now)
        repo = Repository(session)
        state = await repo.get_or_create_state(
            id=ids.new(),
            tenant_id="1",
            channel_id="2",
            conversation_id="3",
            now=now,
        )
        state.status = "resolved"
        await repo.insert_outbound_action(
            id=ids.new(),
            agent_run_id="agent-run-1",
            tenant_id="1",
            channel_id="2",
            conversation_id="3",
            source_message_id="4",
            action_kind=AgentActionKind.public_message,
            content="Thanks, this product is available.",
            status=OutboundActionStatus.queued,
            idempotency_key="1:2:3:4:public_message",
            created_at=now,
        )
        await session.commit()

    writer = FakeChatwootWriter()
    async with factory() as session:
        counts = await ExecuteOutboundActions(
            settings=settings,
            session=session,
            chatwoot=writer,  # type: ignore[arg-type]
        ).run_once()
        await session.commit()

    assert counts == {"sent": 0, "blocked": 1, "failed": 0}
    assert writer.calls == []
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        row = conn.execute(
            text("select status, failure_reason from outbound_actions")
        ).one()
    assert row.status == "blocked_by_policy"
    assert row.failure_reason == "conversation.resolved"


async def test_public_message_is_blocked_when_not_public_reply(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "public-observe-blocked.db"
    settings = Settings(
        env=RuntimeEnvironment.test,
        automation_mode=AutomationMode.observe,
        db_url=f"sqlite+aiosqlite:///{db_path}",
        chatwoot_webhook_secret="secret",
    )
    await init_database(settings)
    factory = make_session_factory(settings)
    ids = IdGenerator()
    now = Clock().now()
    async with factory() as session:
        await create_parent_agent_run(session, now)
        repo = Repository(session)
        await repo.get_or_create_state(
            id=ids.new(),
            tenant_id="1",
            channel_id="2",
            conversation_id="3",
            now=now,
        )
        await queue_public_action(repo, ids, now)
        await session.commit()

    writer = FakeChatwootWriter()
    async with factory() as session:
        counts = await ExecuteOutboundActions(
            settings=settings,
            session=session,
            chatwoot=writer,  # type: ignore[arg-type]
        ).run_once()
        await session.commit()

    assert counts == {"sent": 0, "blocked": 1, "failed": 0}
    assert writer.calls == []
    assert outbound_status(db_path) == (
        "blocked_by_policy",
        "mode.public_reply_not_enabled",
    )


async def test_public_message_is_blocked_when_content_leaks_reasoning(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "public-content-leak-blocked.db"
    settings = Settings(
        env=RuntimeEnvironment.test,
        automation_mode=AutomationMode.public_reply,
        db_url=f"sqlite+aiosqlite:///{db_path}",
        chatwoot_webhook_secret="secret",
    )
    await init_database(settings)
    factory = make_session_factory(settings)
    ids = IdGenerator()
    now = Clock().now()
    async with factory() as session:
        await create_parent_agent_run(session, now)
        repo = Repository(session)
        await repo.get_or_create_state(
            id=ids.new(),
            tenant_id="1",
            channel_id="2",
            conversation_id="3",
            now=now,
        )
        await queue_public_action(repo, ids, now, content="Internal policy says yes.")
        await session.commit()

    writer = FakeChatwootWriter()
    async with factory() as session:
        counts = await ExecuteOutboundActions(
            settings=settings,
            session=session,
            chatwoot=writer,  # type: ignore[arg-type]
        ).run_once()
        await session.commit()

    assert counts == {"sent": 0, "blocked": 1, "failed": 0}
    assert writer.calls == []
    assert outbound_status(db_path) == (
        "blocked_by_policy",
        "public.no_internal_reasoning",
    )


async def test_public_message_price_claim_is_blocked_without_safety_snapshot(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "public-price-no-snapshot-blocked.db"
    settings = Settings(
        env=RuntimeEnvironment.test,
        automation_mode=AutomationMode.public_reply,
        db_url=f"sqlite+aiosqlite:///{db_path}",
        chatwoot_webhook_secret="secret",
    )
    await init_database(settings)
    factory = make_session_factory(settings)
    ids = IdGenerator()
    now = Clock().now()
    async with factory() as session:
        await create_parent_agent_run(session, now)
        repo = Repository(session)
        await repo.get_or_create_state(
            id=ids.new(),
            tenant_id="1",
            channel_id="2",
            conversation_id="3",
            now=now,
        )
        await queue_public_action(
            repo,
            ids,
            now,
            content="This product costs R$ 3.500,00.",
        )
        await session.commit()

    writer = FakeChatwootWriter()
    async with factory() as session:
        counts = await ExecuteOutboundActions(
            settings=settings,
            session=session,
            chatwoot=writer,  # type: ignore[arg-type]
        ).run_once()
        await session.commit()

    assert counts == {"sent": 0, "blocked": 1, "failed": 0}
    assert writer.calls == []
    assert outbound_status(db_path) == (
        "blocked_by_policy",
        "public.price_requires_mentionable_snapshot",
    )


async def test_public_message_price_claim_uses_queued_safety_snapshot(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "public-price-snapshot-safe.db"
    settings = Settings(
        env=RuntimeEnvironment.test,
        automation_mode=AutomationMode.public_reply,
        db_url=f"sqlite+aiosqlite:///{db_path}",
        chatwoot_webhook_secret="secret",
    )
    await init_database(settings)
    factory = make_session_factory(settings)
    ids = IdGenerator()
    now = Clock().now()
    async with factory() as session:
        await create_parent_agent_run(session, now)
        repo = Repository(session)
        await repo.get_or_create_state(
            id=ids.new(),
            tenant_id="1",
            channel_id="2",
            conversation_id="3",
            now=now,
        )
        await queue_public_action(
            repo,
            ids,
            now,
            content="This product costs R$ 3.500,00.",
            safety_context={
                "catalog_context": {
                    "query": "product",
                    "products": [
                        {
                            "product_id": "p1",
                            "name": "Safe Product",
                            "price": {
                                "amount": {
                                    "currency": "BRL",
                                    "minor_units": 350000,
                                },
                                "display_text": "R$ 3.500,00",
                                "can_mention": True,
                            },
                            "availability": {
                                "is_available": True,
                                "display_text": "In stock",
                                "can_mention": True,
                                "hidden_quantity": False,
                            },
                        }
                    ],
                }
            },
        )
        await session.commit()

    writer = FakeChatwootWriter()
    async with factory() as session:
        counts = await ExecuteOutboundActions(
            settings=settings,
            session=session,
            chatwoot=writer,  # type: ignore[arg-type]
        ).run_once()
        await session.commit()

    assert counts == {"sent": 1, "blocked": 0, "failed": 0}
    assert writer.calls == [
        {
            "conversation_id": "3",
            "content": "This product costs R$ 3.500,00.",
            "private": False,
        }
    ]


async def create_parent_agent_run(session, now) -> None:
    session.add(
        RawEventRow(
            id="raw-event-1",
            provider="chatwoot",
            provider_event_id=f"event-{id(session)}",
            event_type="message_created",
            payload_hash="hash",
            payload={},
            status="processed",
            received_at=now,
        )
    )
    await session.flush()
    session.add(
        ConversationMessageRow(
            id="message-1",
            raw_event_id="raw-event-1",
            tenant_id="1",
            channel_id="2",
            conversation_id="3",
            message_id="4",
            contact_id="5",
            direction="inbound",
            visibility="public",
            author_type="customer",
            content="Hello",
            created_at=now,
            message_metadata={},
        )
    )
    await session.flush()
    session.add(
        AgentRunRow(
            id="agent-run-1",
            normalized_message_id="message-1",
            raw_event_id="raw-event-1",
            automation_mode="observe",
            status="queued_action",
            workflow_decision={},
            model_metadata={},
            created_at=now,
        )
    )
    await session.flush()


async def queue_public_action(
    repo: Repository,
    ids: IdGenerator,
    now,
    *,
    content: str = "Thanks, this product is available.",
    safety_context: dict | None = None,
) -> None:
    await repo.insert_outbound_action(
        id=ids.new(),
        agent_run_id="agent-run-1",
        tenant_id="1",
        channel_id="2",
        conversation_id="3",
        source_message_id="4",
        action_kind=AgentActionKind.public_message,
        content=content,
        safety_context=safety_context,
        status=OutboundActionStatus.queued,
        idempotency_key=f"1:2:3:4:public_message:{ids.new()}",
        created_at=now,
    )


def outbound_status(db_path: Path) -> tuple[str, str | None]:
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        row = conn.execute(
            text("select status, failure_reason from outbound_actions")
        ).one()
    return row.status, row.failure_reason


def outbound_retry_state(db_path: Path) -> dict:
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "select status, provider_message_id, attempt_count, "
                "next_attempt_at, error_code from outbound_actions"
            )
        ).one()
        row_count = conn.scalar(text("select count(*) from outbound_actions"))
    return {
        "status": row.status,
        "provider_message_id": row.provider_message_id,
        "attempt_count": row.attempt_count,
        "next_attempt_at": row.next_attempt_at,
        "error_code": row.error_code,
        "row_count": row_count,
    }
