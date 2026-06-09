"""Application service for one customer-support workflow turn."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from wootpilot.catalog.factory import catalog_connector_from_settings
from wootpilot.catalog.store_api import CatalogContextError
from wootpilot.domain.models import (
    AgentActionKind,
    AgentRunStatus,
    AuditEventType,
    AutomationMode,
    ContextSnapshotKind,
    ConversationState,
    NormalizedMessage,
    OutboundActionStatus,
    PolicyDecision,
    RiskSignal,
    StructuredCatalogContext,
    WorkflowDecision,
)
from wootpilot.domain.ports import ModelProposalPort
from wootpilot.observability import (
    log_event,
    workflow_log_fields,
    workflow_trace_complete,
    workflow_trace_enabled,
    workflow_trace_start,
    workflow_trace_update,
)
from wootpilot.persistence.repositories import Repository
from wootpilot.settings import Settings
from wootpilot.time import Clock, IdGenerator
from wootpilot.workflow.checkpoints import checkpointer_from_settings
from wootpilot.workflow.graph import build_support_graph

logger = logging.getLogger(__name__)

__all__ = ["RunCustomerSupportWorkflow"]


class RunCustomerSupportWorkflow:
    """Run WootPilot's customer-support decision workflow for one message.

    This use case is the boundary between durable application state and the
    LangGraph graph. It gathers the catalog snapshot for the inbound customer
    message, invokes the graph with prepared domain objects, then persists the
    resulting policy decisions, audit record, and queued outbound action. The
    graph decides what WootPilot proposes; this service records why that
    proposal happened and prepares any effect for the outbound executor.
    """

    def __init__(
        self,
        *,
        settings: Settings,
        session: AsyncSession,
        model_port: ModelProposalPort,
        clock: Clock | None = None,
        ids: IdGenerator | None = None,
    ):
        self.settings = settings
        self.repo = Repository(session)
        self.model_port = model_port
        self.clock = clock or Clock()
        self.ids = ids or IdGenerator()

    async def run(
        self, message: NormalizedMessage, state: ConversationState
    ) -> WorkflowDecision:
        catalog = catalog_connector_from_settings(self.settings)
        try:
            context = await catalog.search(message.content)
        except CatalogContextError:
            context = StructuredCatalogContext(
                query=message.content,
                products=[],
                risk_signals=[RiskSignal.catalog_load_failed.value],
            )
        context_snapshot_id = self.ids.new()
        context = StructuredCatalogContext(
            query=context.query,
            products=context.products,
            risk_signals=context.risk_signals,
            snapshot_id=context_snapshot_id,
        )
        await self.repo.insert_context_snapshot(
            id=context_snapshot_id,
            tenant_id=message.tenant_id,
            conversation_id=message.conversation_id,
            kind=ContextSnapshotKind.catalog,
            snapshot=context.model_dump(mode="json", exclude={"snapshot_id"}),
            created_at=self.clock.now(),
        )

        thread_id = _workflow_thread_id(message)
        async with checkpointer_from_settings(self.settings) as checkpointer:
            graph = build_support_graph(
                model_port=self.model_port,
                clock=self.clock,
                ids=self.ids,
                checkpointer=checkpointer,
            )
            graph_input = {
                "normalized_message": message,
                "conversation_state": state,
                "catalog_context": context,
                "automation_mode": self.settings.automation_mode,
            }
            graph_config = {"configurable": {"thread_id": thread_id}}
            result = await self._invoke_graph(
                graph=graph,
                graph_input=graph_input,
                graph_config=graph_config,
                thread_id=thread_id,
                message=message,
            )
        decision: WorkflowDecision = result["workflow_decision"]
        pre_policy: PolicyDecision | None = result.get("pre_model_policy_decision")
        post_policy: PolicyDecision | None = result.get("post_model_policy_decision")
        policy = post_policy or pre_policy
        model_metadata = result.get("model_metadata") or {}
        agent_run_id = self.ids.new()
        await self.repo.insert_agent_run(
            id=agent_run_id,
            normalized_message_id=message.id,
            raw_event_id=message.raw_event_id,
            automation_mode=self.settings.automation_mode,
            status=decision.status,
            workflow_decision=decision.model_dump(mode="json"),
            model_metadata=model_metadata,
            created_at=self.clock.now(),
        )
        policy_id: str | None = None
        if policy:
            policy_id = policy.id
            await self.repo.insert_policy_decision(
                id=policy.id,
                agent_run_id=agent_run_id,
                normalized_message_id=message.id,
                stage=policy.stage,
                outcome=policy.outcome,
                rule_ids=policy.rule_ids,
                details=policy.details,
                created_at=policy.created_at,
            )
        if decision.status is AgentRunStatus.queued_action and decision.content:
            await self._queue_action(agent_run_id, message, decision, context)
        await self.repo.insert_audit_record(
            id=self.ids.new(),
            raw_event_id=message.raw_event_id,
            normalized_message_id=message.id,
            agent_run_id=agent_run_id,
            policy_decision_id=policy_id,
            context_snapshot_ids=[context_snapshot_id],
            event_type=AuditEventType.support_workflow_completed,
            summary=decision.summary,
            details={
                "status": decision.status.value,
                "action_kind": decision.action_kind.value,
                "rule_ids": [item.value for item in decision.rule_ids],
                "risk_reasons": decision.risk_reasons,
            },
            created_at=self.clock.now(),
        )
        log_event(
            logger,
            "support_workflow_completed",
            **workflow_log_fields(
                agent_run_id=agent_run_id,
                raw_event_id=message.raw_event_id,
                normalized_message_id=message.id,
                tenant_id=message.tenant_id,
                channel_id=message.channel_id,
                conversation_id=message.conversation_id,
                automation_mode=self.settings.automation_mode.value,
                status=decision.status.value,
                action_kind=decision.action_kind.value,
                rule_ids=[item.value for item in decision.rule_ids],
                risk_reasons=decision.risk_reasons,
                model_metadata=model_metadata,
                high_latency_threshold_ms=self.settings.model_high_latency_ms,
            ),
        )
        return decision

    async def _invoke_graph(
        self,
        *,
        graph,
        graph_input: dict,
        graph_config: dict,
        thread_id: str,
        message: NormalizedMessage,
    ) -> dict:
        """Invoke LangGraph with optional local-only trace output.

        Tracing intentionally uses content-rich developer output only in local
        and public-dev environments. Production observability remains structured
        logs plus durable audit records.
        """

        trace_enabled = workflow_trace_enabled(
            env=self.settings.env.value,
            enabled=self.settings.workflow_trace,
        )
        if not trace_enabled:
            return await graph.ainvoke(graph_input, config=graph_config)

        workflow_trace_start(
            enabled=True,
            thread_id=thread_id,
            tenant_id=message.tenant_id,
            channel_id=message.channel_id,
            conversation_id=message.conversation_id,
            message_id=message.message_id,
            automation_mode=self.settings.automation_mode.value,
            content=message.content,
        )
        result = dict(graph_input)
        async for chunk in graph.astream(
            graph_input,
            config=graph_config,
            stream_mode=["updates", "values"],
        ):
            stream_mode, payload = chunk
            if stream_mode == "values":
                result = dict(payload)
                continue
            for node, update in payload.items():
                workflow_trace_update(enabled=True, node=node, update=update)
        decision = result["workflow_decision"]
        workflow_trace_complete(
            enabled=True,
            status=decision.status.value,
            action_kind=decision.action_kind.value,
            rule_ids=[item.value for item in decision.rule_ids],
        )
        return result

    async def _queue_action(
        self,
        agent_run_id: str,
        message: NormalizedMessage,
        decision: WorkflowDecision,
        context: StructuredCatalogContext,
    ) -> None:
        """Persist a workflow decision as an idempotent outbound action.

        The queue stores the catalog and policy context used at decision time so
        outbound execution can re-check safety without asking the model again.
        """

        if decision.action_kind is AgentActionKind.none:
            return
        if (
            decision.action_kind is AgentActionKind.public_message
            and self.settings.automation_mode is not AutomationMode.public_reply
        ):
            return
        key = (
            f"{message.tenant_id}:{message.channel_id}:{message.conversation_id}:"
            f"{message.message_id}:{decision.action_kind.value}"
        )
        await self.repo.insert_outbound_action(
            id=self.ids.new(),
            agent_run_id=agent_run_id,
            tenant_id=message.tenant_id,
            channel_id=message.channel_id,
            conversation_id=message.conversation_id,
            source_message_id=message.message_id,
            action_kind=decision.action_kind,
            content=decision.content or "",
            safety_context={
                "catalog_context": context.model_dump(mode="json"),
                "workflow_rule_ids": [item.value for item in decision.rule_ids],
                "workflow_risk_reasons": decision.risk_reasons,
            },
            status=OutboundActionStatus.queued,
            idempotency_key=key,
            created_at=self.clock.now(),
        )


def _workflow_thread_id(message: NormalizedMessage) -> str:
    """Return the LangGraph checkpoint scope for one support workflow turn.

    WootPilot stores long-lived Chatwoot conversation state in application
    tables. The LangGraph checkpoint is narrower: it captures execution state
    for the graph run triggered by one normalized inbound message. Including the
    provider message id prevents per-turn artifacts such as policy decision ids
    from being replayed into the next customer message in the same conversation.
    """

    return (
        f"tenant:{message.tenant_id}:channel:{message.channel_id}:"
        f"conversation:{message.conversation_id}:message:{message.message_id}"
    )
