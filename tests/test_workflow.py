from __future__ import annotations

import runpy
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, text

from wootpilot.application.workflow import RunCustomerSupportWorkflow
from wootpilot.domain.models import (
    AgentActionKind,
    AgentProposal,
    AutomationMode,
    AvailabilitySnapshot,
    CatalogContext,
    CheckpointerProfile,
    ConversationState,
    ConversationStatus,
    MessageAuthorType,
    MessageDirection,
    MessageVisibility,
    ModelProposalResult,
    Money,
    NormalizedMessage,
    PriceSnapshot,
    ProductSnapshot,
    Provider,
    RawEventStatus,
    RuntimeEnvironment,
)
from wootpilot.integrations.model import FakeProposalGenerator
from wootpilot.persistence.database import init_database, make_session_factory
from wootpilot.persistence.repositories import Repository, row_to_state
from wootpilot.settings import Settings
from wootpilot.time import Clock, IdGenerator
from wootpilot.workflow.graph import build_graph


class PublicProposalGenerator:
    async def propose(self, **kwargs):
        return ModelProposalResult(
            proposal=AgentProposal(
                action_kind=AgentActionKind.public_message,
                summary="Public proposal in observe mode.",
                public_message="Thanks, this part may fit.",
                private_note="Suggested reply: Thanks, this part may fit.",
                confidence=0.8,
            ),
            metadata={"provider": "test"},
        )


class PriceProposalGenerator:
    async def propose(self, **kwargs):
        return ModelProposalResult(
            proposal=AgentProposal(
                action_kind=AgentActionKind.public_message,
                summary="Public proposal with exact catalog price.",
                public_message="Demo Aircooled Harness is available for R$ 3.500,00.",
                confidence=0.8,
            ),
            metadata={"provider": "test"},
        )


class HiddenPriceProposalGenerator:
    async def propose(self, **kwargs):
        return ModelProposalResult(
            proposal=AgentProposal(
                action_kind=AgentActionKind.public_message,
                summary="Unsafe hidden price proposal.",
                public_message="The exact hidden price is R$ 999,00.",
                confidence=0.8,
            ),
            metadata={"provider": "test"},
        )


async def test_observe_graph_returns_stable_proposed_decision() -> None:
    graph = build_graph(proposal_generator=FakeProposalGenerator())
    now = datetime.now(UTC)
    result = await graph.ainvoke(
        {
            "normalized_message": NormalizedMessage(
                id="m1",
                raw_event_id="r1",
                tenant_id="t1",
                channel_id="c1",
                conversation_id="v1",
                message_id="101",
                direction=MessageDirection.inbound,
                visibility=MessageVisibility.public,
                author_type=MessageAuthorType.customer,
                content="Do you have TBI?",
                created_at=now,
            ),
            "conversation_state": ConversationState(
                id="s1",
                tenant_id="t1",
                channel_id="c1",
                conversation_id="v1",
                replyable=True,
                updated_at=now,
            ),
            "catalog_context": CatalogContext(query="TBI"),
            "automation_mode": AutomationMode.observe,
        },
        config={"configurable": {"thread_id": "tenant:t1:channel:c1:conversation:v1"}},
    )
    assert result["workflow_decision"].status.value == "proposed"


async def test_observe_graph_keeps_public_proposal_as_non_sending_proposal() -> None:
    graph = build_graph(proposal_generator=PublicProposalGenerator())
    now = datetime.now(UTC)
    result = await graph.ainvoke(
        {
            "normalized_message": NormalizedMessage(
                id="m1",
                raw_event_id="r1",
                tenant_id="t1",
                channel_id="c1",
                conversation_id="v1",
                message_id="101",
                direction=MessageDirection.inbound,
                visibility=MessageVisibility.public,
                author_type=MessageAuthorType.customer,
                content="Do you have TBI?",
                created_at=now,
            ),
            "conversation_state": ConversationState(
                id="s1",
                tenant_id="t1",
                channel_id="c1",
                conversation_id="v1",
                replyable=True,
                updated_at=now,
            ),
            "catalog_context": CatalogContext(query="TBI"),
            "automation_mode": AutomationMode.observe,
        },
        config={"configurable": {"thread_id": "tenant:t1:channel:c1:conversation:v1"}},
    )
    assert result["workflow_decision"].status.value == "proposed"
    assert result["workflow_decision"].action_kind.value == "none"


def test_support_graph_mermaid_includes_command_routed_destinations() -> None:
    script = runpy.run_path("scripts/render-support-workflow-graph.py")
    proposal_generator = script["DiagramProposalGenerator"]()
    script["sync_node_descriptions_for_diagram"](proposal_generator)
    graph = build_graph(proposal_generator=proposal_generator)

    mermaid = graph.get_graph().draw_mermaid()

    assert "should_invoke -.-> triage_message" in mermaid
    assert "should_invoke -.-> __end__" in mermaid
    assert "policy_gate -.-> generate_proposal" in mermaid
    assert "generate_proposal -.-> validate_outbound_action" in mermaid
    assert "validate_outbound_action -.-> build_observe_decision" in mermaid
    assert "validate_outbound_action -.-> build_private_note_action" in mermaid
    assert "validate_outbound_action -.-> build_public_message_action" in mermaid
    assert (
        script["WORKFLOW_NODE_DESCRIPTIONS"]["should_invoke"]
        == "Checks whether this message should run WootPilot."
    )


async def test_public_reply_graph_blocks_assigned_conversations() -> None:
    graph = build_graph(proposal_generator=PublicProposalGenerator())
    now = datetime.now(UTC)
    result = await graph.ainvoke(
        {
            "normalized_message": NormalizedMessage(
                id="m1",
                raw_event_id="r1",
                tenant_id="t1",
                channel_id="c1",
                conversation_id="v1",
                message_id="101",
                direction=MessageDirection.inbound,
                visibility=MessageVisibility.public,
                author_type=MessageAuthorType.customer,
                content="Do you have TBI?",
                created_at=now,
            ),
            "conversation_state": ConversationState(
                id="s1",
                tenant_id="t1",
                channel_id="c1",
                conversation_id="v1",
                assigned_agent_id="42",
                replyable=True,
                updated_at=now,
            ),
            "catalog_context": CatalogContext(query="TBI"),
            "automation_mode": AutomationMode.public_reply,
        },
        config={"configurable": {"thread_id": "tenant:t1:channel:c1:conversation:v1"}},
    )
    decision = result["workflow_decision"]
    assert decision.status.value == "blocked_by_policy"
    assert "conversation.assigned_to_human" in decision.rule_ids


async def test_public_reply_graph_blocks_resolved_conversations() -> None:
    graph = build_graph(proposal_generator=PublicProposalGenerator())
    now = datetime.now(UTC)
    result = await graph.ainvoke(
        {
            "normalized_message": NormalizedMessage(
                id="m1",
                raw_event_id="r1",
                tenant_id="t1",
                channel_id="c1",
                conversation_id="v1",
                message_id="101",
                direction=MessageDirection.inbound,
                visibility=MessageVisibility.public,
                author_type=MessageAuthorType.customer,
                content="Do you have TBI?",
                created_at=now,
            ),
            "conversation_state": ConversationState(
                id="s1",
                tenant_id="t1",
                channel_id="c1",
                conversation_id="v1",
                status=ConversationStatus.resolved,
                replyable=True,
                updated_at=now,
            ),
            "catalog_context": CatalogContext(query="TBI"),
            "automation_mode": AutomationMode.public_reply,
        },
        config={"configurable": {"thread_id": "tenant:t1:channel:c1:conversation:v1"}},
    )
    decision = result["workflow_decision"]
    assert decision.status.value == "blocked_by_policy"
    assert "conversation.resolved" in decision.rule_ids


async def test_public_reply_graph_blocks_portuguese_human_escalation() -> None:
    graph = build_graph(proposal_generator=PublicProposalGenerator())
    now = datetime.now(UTC)
    message = _message(now).model_copy(
        update={"content": "Quero falar com um atendente humano."}
    )

    result = await graph.ainvoke(
        {
            "normalized_message": message,
            "conversation_state": _state(now),
            "catalog_context": CatalogContext(query=message.content),
            "automation_mode": AutomationMode.public_reply,
        },
        config={"configurable": {"thread_id": "tenant:t1:channel:c1:conversation:v1"}},
    )

    decision = result["workflow_decision"]
    assert decision.status.value == "blocked_by_policy"
    assert "intent.human_requested" in decision.rule_ids


async def test_public_reply_graph_routes_portuguese_discount_to_review() -> None:
    graph = build_graph(proposal_generator=PublicProposalGenerator())
    now = datetime.now(UTC)
    message = _message(now).model_copy(
        update={"content": "Tem desconto no pix para esse produto?"}
    )

    result = await graph.ainvoke(
        {
            "normalized_message": message,
            "conversation_state": _state(now),
            "catalog_context": CatalogContext(query=message.content),
            "automation_mode": AutomationMode.public_reply,
        },
        config={"configurable": {"thread_id": "tenant:t1:channel:c1:conversation:v1"}},
    )

    decision = result["workflow_decision"]
    assert decision.status.value == "queued_action"
    assert decision.action_kind.value == "private_note"
    assert "public.risk_requires_review" in decision.rule_ids


async def test_public_reply_allows_exact_mentionable_catalog_price() -> None:
    graph = build_graph(proposal_generator=PriceProposalGenerator())
    now = datetime.now(UTC)
    result = await graph.ainvoke(
        {
            "normalized_message": _message(now),
            "conversation_state": _state(now),
            "catalog_context": CatalogContext(
                query="aircooled harness",
                products=[_product(can_mention_price=True)],
            ),
            "automation_mode": AutomationMode.public_reply,
        },
        config={"configurable": {"thread_id": "tenant:t1:channel:c1:conversation:v1"}},
    )
    decision = result["workflow_decision"]
    assert decision.status.value == "queued_action"
    assert decision.action_kind.value == "public_message"


async def test_public_reply_blocks_exact_price_without_mentionable_snapshot() -> None:
    graph = build_graph(proposal_generator=HiddenPriceProposalGenerator())
    now = datetime.now(UTC)
    result = await graph.ainvoke(
        {
            "normalized_message": _message(now),
            "conversation_state": _state(now),
            "catalog_context": CatalogContext(
                query="hidden price product",
                products=[_product(can_mention_price=False)],
            ),
            "automation_mode": AutomationMode.public_reply,
        },
        config={"configurable": {"thread_id": "tenant:t1:channel:c1:conversation:v1"}},
    )
    decision = result["workflow_decision"]
    assert decision.status.value == "queued_action"
    assert decision.action_kind.value == "private_note"
    assert "public.price_requires_mentionable_snapshot" in decision.rule_ids
    assert "R$ 999,00" not in (decision.content or "")


async def test_public_reply_review_note_is_persisted_as_private_outbound_action(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "workflow-review-note.db"
    settings = Settings(
        env=RuntimeEnvironment.test,
        automation_mode=AutomationMode.public_reply,
        db_url=f"sqlite+aiosqlite:///{db_path}",
        chatwoot_webhook_secret="secret",
    )
    await init_database(settings)
    factory = make_session_factory(settings)
    clock = Clock()
    ids = IdGenerator()
    now = clock.now()
    message = _message(now)
    async with factory() as session:
        repo = Repository(session)
        raw, _ = await repo.insert_raw_event(
            id="raw-1",
            provider=Provider.chatwoot,
            provider_event_id="delivery-1",
            event_type="message_created",
            payload_hash="hash",
            payload={},
            status=RawEventStatus.processed,
            received_at=now,
        )
        message = message.model_copy(update={"raw_event_id": raw.id})
        await repo.insert_message(message)
        state_row = await repo.get_or_create_state(
            id="state-1",
            tenant_id=message.tenant_id,
            channel_id=message.channel_id,
            conversation_id=message.conversation_id,
            now=now,
        )
        decision = await RunCustomerSupportWorkflow(
            settings=settings,
            session=session,
            proposal_generator=HiddenPriceProposalGenerator(),
            clock=clock,
            ids=ids,
        ).run(message, row_to_state(state_row))
        await session.commit()

    assert decision.status.value == "queued_action"
    assert decision.action_kind.value == "private_note"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        action = conn.execute(
            text("select action_kind, status, content from outbound_actions")
        ).one()
    assert action.action_kind == "private_note"
    assert action.status == "queued"
    assert "needs human review" in action.content
    assert "R$ 999,00" not in action.content


async def test_local_workflow_trace_streaming_returns_final_graph_state(
    tmp_path: Path,
    capsys,
) -> None:
    db_path = tmp_path / "workflow-trace.db"
    settings = Settings(
        env=RuntimeEnvironment.local,
        workflow_trace=True,
        automation_mode=AutomationMode.public_reply,
        db_url=f"sqlite+aiosqlite:///{db_path}",
        chatwoot_webhook_secret="secret",
    )
    await init_database(settings)
    factory = make_session_factory(settings)
    clock = Clock()
    ids = IdGenerator()
    now = clock.now()
    message = _message(now)
    async with factory() as session:
        repo = Repository(session)
        raw, _ = await repo.insert_raw_event(
            id="raw-1",
            provider=Provider.chatwoot,
            provider_event_id="delivery-1",
            event_type="message_created",
            payload_hash="hash",
            payload={},
            status=RawEventStatus.processed,
            received_at=now,
        )
        message = message.model_copy(update={"raw_event_id": raw.id})
        await repo.insert_message(message)
        state_row = await repo.get_or_create_state(
            id="state-1",
            tenant_id=message.tenant_id,
            channel_id=message.channel_id,
            conversation_id=message.conversation_id,
            now=now,
        )
        decision = await RunCustomerSupportWorkflow(
            settings=settings,
            session=session,
            proposal_generator=FakeProposalGenerator(),
            clock=clock,
            ids=ids,
        ).run(message, row_to_state(state_row))

    captured = capsys.readouterr()
    assert decision.status.value == "queued_action"
    assert "workflow" in captured.err
    assert "build_private_note_action" in captured.err
    assert "Do you have this product?" in captured.err


async def test_persistent_checkpoints_do_not_replay_policy_state_between_messages(
    tmp_path: Path,
    capsys,
) -> None:
    db_path = tmp_path / "workflow-checkpoint-turns.db"
    settings = Settings(
        env=RuntimeEnvironment.local,
        workflow_trace=True,
        checkpointer=CheckpointerProfile.sqlite,
        automation_mode=AutomationMode.public_reply,
        db_url=f"sqlite+aiosqlite:///{db_path}",
        chatwoot_webhook_secret="secret",
    )
    await init_database(settings)
    factory = make_session_factory(settings)
    clock = Clock()
    ids = IdGenerator()
    now = clock.now()

    async with factory() as session:
        repo = Repository(session)
        state_row = await repo.get_or_create_state(
            id="state-1",
            tenant_id="t1",
            channel_id="c1",
            conversation_id="v1",
            now=now,
        )
        workflow = RunCustomerSupportWorkflow(
            settings=settings,
            session=session,
            proposal_generator=FakeProposalGenerator(),
            clock=clock,
            ids=ids,
        )

        first = await _persist_inbound_message(
            repo=repo,
            now=now,
            raw_id="raw-1",
            message_id="m1",
            provider_message_id="101",
            content="Do you have this product?",
        )
        first_decision = await workflow.run(first, row_to_state(state_row))

        second = await _persist_inbound_message(
            repo=repo,
            now=now,
            raw_id="raw-2",
            message_id="m2",
            provider_message_id="102",
            content="Do you have another product?",
        )
        second_decision = await workflow.run(second, row_to_state(state_row))
        await session.commit()

    captured = capsys.readouterr()
    assert first_decision.status.value == "queued_action"
    assert second_decision.status.value == "queued_action"
    assert "conversation:v1:message:101" in captured.err
    assert "conversation:v1:message:102" in captured.err

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        stage_counts = {
            row[0]: row[1]
            for row in conn.execute(
                text("select stage, count(*) from policy_decisions group by stage")
            )
        }
    assert stage_counts == {"pre_model": 2, "post_model": 2}


async def test_sqlite_loaded_human_active_until_blocks_without_naive_datetime_error(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "workflow-human-active.db"
    settings = Settings(
        env=RuntimeEnvironment.local,
        workflow_trace=True,
        checkpointer=CheckpointerProfile.sqlite,
        automation_mode=AutomationMode.public_reply,
        db_url=f"sqlite+aiosqlite:///{db_path}",
        chatwoot_webhook_secret="secret",
    )
    await init_database(settings)
    factory = make_session_factory(settings)
    clock = Clock()
    ids = IdGenerator()
    now = clock.now()

    async with factory() as session:
        repo = Repository(session)
        row = await repo.get_or_create_state(
            id="state-1",
            tenant_id="t1",
            channel_id="c1",
            conversation_id="v1",
            now=now,
        )
        row.human_active_until = now + timedelta(minutes=30)
        await session.commit()

    async with factory() as session:
        repo = Repository(session)
        row = await repo.get_or_create_state(
            id="state-ignored",
            tenant_id="t1",
            channel_id="c1",
            conversation_id="v1",
            now=now,
        )
        message = await _persist_inbound_message(
            repo=repo,
            now=now,
            raw_id="raw-1",
            message_id="m1",
            provider_message_id="101",
            content="Do you have this product?",
        )
        decision = await RunCustomerSupportWorkflow(
            settings=settings,
            session=session,
            proposal_generator=FakeProposalGenerator(),
            clock=clock,
            ids=ids,
        ).run(message, row_to_state(row))

    assert decision.status.value == "blocked_by_policy"
    assert "conversation.human_active" in decision.rule_ids


async def test_assist_mode_ignores_human_active_window_for_private_notes() -> None:
    graph = build_graph(proposal_generator=PublicProposalGenerator())
    now = datetime.now(UTC)
    result = await graph.ainvoke(
        {
            "normalized_message": _message(now),
            "conversation_state": _state(now).model_copy(
                update={"human_active_until": now + timedelta(minutes=15)}
            ),
            "catalog_context": CatalogContext(query="TBI"),
            "automation_mode": AutomationMode.assist,
        },
        config={"configurable": {"thread_id": "tenant:t1:channel:c1:conversation:v1"}},
    )
    decision = result["workflow_decision"]
    assert decision.status.value == "queued_action"
    assert decision.action_kind.value == "private_note"


async def _persist_inbound_message(
    *,
    repo: Repository,
    now: datetime,
    raw_id: str,
    message_id: str,
    provider_message_id: str,
    content: str,
) -> NormalizedMessage:
    raw, _ = await repo.insert_raw_event(
        id=raw_id,
        provider=Provider.chatwoot,
        provider_event_id=f"delivery-{provider_message_id}",
        event_type="message_created",
        payload_hash=f"hash-{provider_message_id}",
        payload={},
        status=RawEventStatus.processed,
        received_at=now,
    )
    message = _message(now).model_copy(
        update={
            "id": message_id,
            "raw_event_id": raw.id,
            "message_id": provider_message_id,
            "content": content,
        }
    )
    await repo.insert_message(message)
    return message


def _message(now: datetime) -> NormalizedMessage:
    return NormalizedMessage(
        id="m1",
        raw_event_id="r1",
        tenant_id="t1",
        channel_id="c1",
        conversation_id="v1",
        message_id="101",
        direction=MessageDirection.inbound,
        visibility=MessageVisibility.public,
        author_type=MessageAuthorType.customer,
        content="Do you have this product?",
        created_at=now,
    )


def _state(now: datetime) -> ConversationState:
    return ConversationState(
        id="s1",
        tenant_id="t1",
        channel_id="c1",
        conversation_id="v1",
        replyable=True,
        updated_at=now,
    )


def _product(*, can_mention_price: bool) -> ProductSnapshot:
    return ProductSnapshot(
        product_id="p1",
        sku="SKU-1",
        name="Demo Aircooled Harness",
        permalink="https://shop.example.test/products/demo-aircooled-harness",
        price=PriceSnapshot(
            amount=Money(currency="BRL", minor_units=350000)
            if can_mention_price
            else None,
            display_text="R$ 3.500,00" if can_mention_price else None,
            can_mention=can_mention_price,
            hidden=not can_mention_price,
            quote_required=not can_mention_price,
        ),
        availability=AvailabilitySnapshot(
            is_available=True,
            display_text="In stock",
            can_mention=True,
            hidden_quantity=False,
        ),
    )
