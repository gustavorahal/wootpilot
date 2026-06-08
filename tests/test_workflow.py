from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, text

from wootpilot.application.workflow import RunSupportWorkflow
from wootpilot.domain.models import (
    AgentActionKind,
    AgentProposal,
    AvailabilitySnapshot,
    BotMode,
    ConversationState,
    ModelProposalResult,
    Money,
    NormalizedMessage,
    PriceSnapshot,
    ProductSnapshot,
    StructuredCatalogContext,
)
from wootpilot.integrations.model import FakeModelProposalPort
from wootpilot.persistence.database import init_database, make_session_factory
from wootpilot.persistence.repositories import Repository, row_to_state
from wootpilot.settings import Settings
from wootpilot.time import Clock, IdGenerator
from wootpilot.workflow.graph import (
    WORKFLOW_NODE_DESCRIPTIONS,
    build_support_graph,
)


class PublicProposalPort:
    async def propose(self, **kwargs):
        return ModelProposalResult(
            proposal=AgentProposal(
                action_kind=AgentActionKind.public_message,
                summary="Public proposal in shadow mode.",
                public_message="Thanks, this part may fit.",
                private_note="Suggested reply: Thanks, this part may fit.",
                confidence=0.8,
            ),
            metadata={"provider": "test"},
        )


class PriceProposalPort:
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


class HiddenPriceProposalPort:
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


async def test_shadow_graph_returns_stable_proposed_decision() -> None:
    graph = build_support_graph(model_port=FakeModelProposalPort())
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
                direction="inbound",
                visibility="public",
                author_type="customer",
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
            "catalog_context": StructuredCatalogContext(query="TBI"),
            "bot_mode": BotMode.shadow,
        },
        config={"configurable": {"thread_id": "tenant:t1:channel:c1:conversation:v1"}},
    )
    assert result["workflow_decision"].status.value == "proposed"


async def test_shadow_graph_keeps_public_proposal_as_non_sending_proposal() -> None:
    graph = build_support_graph(model_port=PublicProposalPort())
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
                direction="inbound",
                visibility="public",
                author_type="customer",
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
            "catalog_context": StructuredCatalogContext(query="TBI"),
            "bot_mode": BotMode.shadow,
        },
        config={"configurable": {"thread_id": "tenant:t1:channel:c1:conversation:v1"}},
    )
    assert result["workflow_decision"].status.value == "proposed"
    assert result["workflow_decision"].action_kind.value == "none"


def test_support_graph_mermaid_includes_descriptive_branch_names() -> None:
    graph = build_support_graph(model_port=PublicProposalPort())

    mermaid = graph.get_graph().draw_mermaid()

    assert "eligible_customer_public_turn" in mermaid
    assert "stop_pre_model_policy_block" in mermaid
    assert "continue_model_proposed_action" in mermaid
    assert "queue_private_review_note" in mermaid
    assert "route_final_decision" in mermaid
    assert "shadow_observe_only" in mermaid
    assert "queue_copilot_or_private_note" in mermaid
    assert "queue_limited_auto_public_reply" in mermaid
    assert (
        WORKFLOW_NODE_DESCRIPTIONS["should_invoke"]
        == "Checks whether this message should run WootPilot."
    )


async def test_limited_auto_graph_blocks_assigned_conversations() -> None:
    graph = build_support_graph(model_port=PublicProposalPort())
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
                direction="inbound",
                visibility="public",
                author_type="customer",
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
            "catalog_context": StructuredCatalogContext(query="TBI"),
            "bot_mode": BotMode.limited_auto,
        },
        config={"configurable": {"thread_id": "tenant:t1:channel:c1:conversation:v1"}},
    )
    decision = result["workflow_decision"]
    assert decision.status.value == "blocked_by_policy"
    assert "conversation.assigned_to_human" in decision.rule_ids


async def test_limited_auto_graph_blocks_resolved_conversations() -> None:
    graph = build_support_graph(model_port=PublicProposalPort())
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
                direction="inbound",
                visibility="public",
                author_type="customer",
                content="Do you have TBI?",
                created_at=now,
            ),
            "conversation_state": ConversationState(
                id="s1",
                tenant_id="t1",
                channel_id="c1",
                conversation_id="v1",
                status="resolved",
                replyable=True,
                updated_at=now,
            ),
            "catalog_context": StructuredCatalogContext(query="TBI"),
            "bot_mode": BotMode.limited_auto,
        },
        config={"configurable": {"thread_id": "tenant:t1:channel:c1:conversation:v1"}},
    )
    decision = result["workflow_decision"]
    assert decision.status.value == "blocked_by_policy"
    assert "conversation.resolved" in decision.rule_ids


async def test_limited_auto_allows_exact_mentionable_catalog_price() -> None:
    graph = build_support_graph(model_port=PriceProposalPort())
    now = datetime.now(UTC)
    result = await graph.ainvoke(
        {
            "normalized_message": _message(now),
            "conversation_state": _state(now),
            "catalog_context": StructuredCatalogContext(
                query="aircooled harness",
                products=[_product(can_mention_price=True)],
            ),
            "bot_mode": BotMode.limited_auto,
        },
        config={"configurable": {"thread_id": "tenant:t1:channel:c1:conversation:v1"}},
    )
    decision = result["workflow_decision"]
    assert decision.status.value == "queued_action"
    assert decision.action_kind.value == "public_message"


async def test_limited_auto_blocks_exact_price_without_mentionable_snapshot() -> None:
    graph = build_support_graph(model_port=HiddenPriceProposalPort())
    now = datetime.now(UTC)
    result = await graph.ainvoke(
        {
            "normalized_message": _message(now),
            "conversation_state": _state(now),
            "catalog_context": StructuredCatalogContext(
                query="hidden price product",
                products=[_product(can_mention_price=False)],
            ),
            "bot_mode": BotMode.limited_auto,
        },
        config={"configurable": {"thread_id": "tenant:t1:channel:c1:conversation:v1"}},
    )
    decision = result["workflow_decision"]
    assert decision.status.value == "queued_action"
    assert decision.action_kind.value == "private_note"
    assert "public.price_requires_mentionable_snapshot" in decision.rule_ids
    assert "R$ 999,00" not in (decision.content or "")


async def test_limited_auto_review_note_is_persisted_as_private_outbound_action(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "workflow-review-note.db"
    settings = Settings(
        env="test",
        bot_mode=BotMode.limited_auto,
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
            provider="chatwoot",
            provider_event_id="delivery-1",
            event_type="message_created",
            payload_hash="hash",
            payload={},
            status="processed",
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
        decision = await RunSupportWorkflow(
            settings=settings,
            session=session,
            model_port=HiddenPriceProposalPort(),
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


def _message(now: datetime) -> NormalizedMessage:
    return NormalizedMessage(
        id="m1",
        raw_event_id="r1",
        tenant_id="t1",
        channel_id="c1",
        conversation_id="v1",
        message_id="101",
        direction="inbound",
        visibility="public",
        author_type="customer",
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
