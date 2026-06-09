"""Outbound action execution for Chatwoot writes."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from wootpilot.application.errors import ChatwootApiError
from wootpilot.application.policy import (
    public_internal_reasoning_rule,
    public_price_policy_rule,
)
from wootpilot.domain.models import (
    AgentActionKind,
    AutomationMode,
    ConversationState,
    ConversationStatus,
    OutboundActionStatus,
    PolicyRule,
    QueuedOutboundAction,
    StructuredCatalogContext,
)
from wootpilot.integrations.chatwoot import ChannelSafetyState, ChatwootClient
from wootpilot.observability import log_event, outbound_log_fields
from wootpilot.persistence.repositories import Repository
from wootpilot.settings import Settings
from wootpilot.time import Clock

logger = logging.getLogger(__name__)

__all__ = ["ExecuteOutboundActions"]


class ExecuteOutboundActions:
    """Sends queued actions idempotently after final deterministic checks."""

    def __init__(
        self,
        *,
        settings: Settings,
        session: AsyncSession,
        chatwoot: ChatwootClient | None = None,
        clock: Clock | None = None,
    ):
        self.settings = settings
        self.repo = Repository(session)
        self.chatwoot = chatwoot or ChatwootClient(settings)
        self.clock = clock or Clock()

    async def run_once(self, limit: int = 10) -> dict[str, int]:
        """Execute due outbound actions once.

        Args:
            limit: Maximum number of queued or due retryable actions to inspect.

        Returns:
            Counts for sent, blocked, and failed actions.

        Raises:
            Exception: Unexpected application errors escape so operators see
                bugs instead of persisted provider-failure rows.
        """

        counts = {"sent": 0, "blocked": 0, "failed": 0}
        for _ in range(limit):
            actions = await self.repo.claim_queued_outbound_actions(
                limit=1,
                now=self.clock.now(),
                claimed_at=self.clock.now(),
            )
            await self.repo.session.commit()
            if not actions:
                break
            action = actions[0]
            blocked_reason = await self._blocked_reason(action)
            if blocked_reason:
                await self._mark_blocked(action, blocked_reason)
                counts["blocked"] += 1
                continue
            try:
                provider_message_id = await self.chatwoot.create_message(
                    conversation_id=action.conversation_id,
                    content=action.content,
                    private=action.action_kind is AgentActionKind.private_note,
                )
            except ChatwootApiError as exc:
                await self._mark_send_failure(action, exc)
                counts["failed"] += 1
                continue
            await self._mark_sent(action, provider_message_id)
            counts["sent"] += 1
        return counts

    async def _mark_blocked(
        self, action: QueuedOutboundAction, blocked_reason: PolicyRule | str
    ) -> None:
        failure_reason = _reason_value(blocked_reason)
        await self.repo.mark_outbound_action(
            action_id=action.id,
            status=OutboundActionStatus.blocked_by_policy,
            updated_at=self.clock.now(),
            failure_reason=failure_reason,
            clear_next_attempt_at=True,
        )
        await self.repo.session.commit()
        self._log_action_result(
            action,
            status=OutboundActionStatus.blocked_by_policy,
            failure_reason=failure_reason,
        )

    async def _mark_send_failure(
        self, action: QueuedOutboundAction, exc: ChatwootApiError
    ) -> None:
        attempt_count = action.attempt_count + 1
        status = self._failure_status(exc, attempt_count)
        next_attempt_at = self._next_attempt_at(status)
        failure_reason = exc.code
        await self.repo.mark_outbound_action(
            action_id=action.id,
            status=status,
            updated_at=self.clock.now(),
            failure_reason=failure_reason,
            attempt_count=attempt_count,
            next_attempt_at=next_attempt_at,
            clear_next_attempt_at=next_attempt_at is None,
            error_code=failure_reason,
        )
        await self.repo.session.commit()
        self._log_action_result(
            action,
            status=status,
            failure_reason=failure_reason,
            level=logging.WARNING,
        )

    async def _mark_sent(
        self, action: QueuedOutboundAction, provider_message_id: str
    ) -> None:
        post_send_failure_reason = await self._apply_post_send_updates(action)
        await self.repo.mark_outbound_action(
            action_id=action.id,
            status=OutboundActionStatus.sent,
            updated_at=self.clock.now(),
            provider_message_id=provider_message_id,
            failure_reason=post_send_failure_reason,
            clear_next_attempt_at=True,
        )
        await self.repo.session.commit()
        self._log_action_result(
            action,
            status=OutboundActionStatus.sent,
            provider_message_id=provider_message_id,
            failure_reason=post_send_failure_reason,
        )

    def _failure_status(
        self, exc: ChatwootApiError, attempt_count: int
    ) -> OutboundActionStatus:
        if exc.retryable and attempt_count < self.settings.outbound_max_attempts:
            return OutboundActionStatus.retryable_failure
        return OutboundActionStatus.permanent_failure

    def _next_attempt_at(self, status: OutboundActionStatus) -> datetime | None:
        if status is not OutboundActionStatus.retryable_failure:
            return None
        return self.clock.now() + timedelta(
            seconds=self.settings.outbound_retry_delay_seconds
        )

    async def _apply_post_send_updates(
        self, action: QueuedOutboundAction
    ) -> str | None:
        failure_reasons = []
        if status_failure := await self._apply_success_status_transition(action):
            failure_reasons.append(status_failure)
        if label_failure := await self._apply_private_review_label(action):
            failure_reasons.append(label_failure)
        return ";".join(failure_reasons) if failure_reasons else None

    async def _apply_success_status_transition(
        self, action: QueuedOutboundAction
    ) -> str | None:
        """Optionally move a conversation to a configured post-reply status.

        The customer-visible message has already been sent when this runs. If
        the status update fails, the action stays sent so retries cannot
        duplicate the public reply; the failure is recorded for operators.
        """

        if action.action_kind is not AgentActionKind.public_message:
            return None
        if not self.settings.chatwoot_update_status_after_public_reply:
            return None
        target_status = self.settings.chatwoot_public_reply_status.strip()
        if not target_status:
            return None
        try:
            await self.chatwoot.set_conversation_status(
                conversation_id=action.conversation_id,
                status=target_status,
            )
        except ChatwootApiError as exc:
            log_event(
                logger,
                "outbound_status_update_failed",
                level=logging.WARNING,
                action_id=action.id,
                tenant_id=action.tenant_id,
                channel_id=action.channel_id,
                conversation_id=action.conversation_id,
                action_kind=action.action_kind.value,
                target_status=target_status,
                failure_reason=exc.code,
            )
            return f"status_update_failed:{exc.code}"
        return None

    async def _apply_private_review_label(
        self, action: QueuedOutboundAction
    ) -> str | None:
        if action.action_kind is not AgentActionKind.private_note:
            return None
        if not self.settings.chatwoot_mark_needs_human_on_private_review:
            return None
        target_label = self.settings.chatwoot_needs_human_label.strip()
        if not target_label or not _is_human_review_private_note(action.safety_context):
            return None
        try:
            await self.chatwoot.add_conversation_labels(
                conversation_id=action.conversation_id,
                labels=[target_label],
            )
        except ChatwootApiError as exc:
            log_event(
                logger,
                "outbound_label_update_failed",
                level=logging.WARNING,
                action_id=action.id,
                tenant_id=action.tenant_id,
                channel_id=action.channel_id,
                conversation_id=action.conversation_id,
                action_kind=action.action_kind.value,
                label=target_label,
                failure_reason=exc.code,
            )
            return f"label_update_failed:{exc.code}"
        return None

    def _log_action_result(
        self,
        action: QueuedOutboundAction,
        *,
        status: OutboundActionStatus,
        provider_message_id: str | None = None,
        failure_reason: str | None = None,
        level: int = logging.INFO,
    ) -> None:
        log_event(
            logger,
            "outbound_action_completed",
            level=level,
            **outbound_log_fields(
                action_id=action.id,
                tenant_id=action.tenant_id,
                channel_id=action.channel_id,
                conversation_id=action.conversation_id,
                action_kind=action.action_kind.value,
                status=status.value,
                provider_message_id=provider_message_id,
                failure_reason=failure_reason,
            ),
        )

    async def _blocked_reason(
        self, action: QueuedOutboundAction
    ) -> PolicyRule | str | None:
        if action.action_kind is AgentActionKind.private_note:
            if not action.content.strip():
                return PolicyRule.content_empty
            return None
        if action.action_kind is AgentActionKind.public_message:
            if static_reason := self._public_message_static_blocked_reason(action):
                return static_reason
            state = await self.repo.get_conversation_state(
                tenant_id=action.tenant_id,
                channel_id=action.channel_id,
                conversation_id=action.conversation_id,
            )
            if stored_reason := self._stored_state_blocked_reason(state):
                return stored_reason
            await self.repo.session.commit()
            channel_state = await self.chatwoot.get_conversation_safety(
                conversation_id=action.conversation_id
            )
            return self._channel_state_blocked_reason(action, channel_state)
        return PolicyRule.unknown_action_kind

    def _public_message_static_blocked_reason(
        self, action: QueuedOutboundAction
    ) -> PolicyRule | None:
        if self.settings.automation_mode is not AutomationMode.public_reply:
            return PolicyRule.mode_public_reply_not_enabled
        if not action.content.strip():
            return PolicyRule.content_empty
        if leakage_rule := public_internal_reasoning_rule(action.content):
            return leakage_rule
        return _public_price_rule_from_safety_context(
            action.content,
            action.safety_context,
        )

    def _stored_state_blocked_reason(
        self, state: ConversationState | None
    ) -> PolicyRule | None:
        if state is None:
            return PolicyRule.conversation_safety_state_missing
        if not state.replyable:
            return PolicyRule.conversation_not_replyable
        if state.status is ConversationStatus.resolved:
            return PolicyRule.conversation_resolved
        if state.paused:
            return PolicyRule.conversation_wootpilot_paused
        human_active_until = _aware(state.human_active_until)
        if human_active_until and human_active_until > self.clock.now():
            return PolicyRule.conversation_human_active
        if state.assigned_agent_id or state.assigned_team_id:
            return PolicyRule.conversation_assigned_to_human
        return None

    def _channel_state_blocked_reason(
        self,
        action: QueuedOutboundAction,
        channel_state: ChannelSafetyState,
    ) -> PolicyRule | None:
        if channel_state.conversation_id != action.conversation_id:
            return PolicyRule.conversation_id_mismatch
        if channel_state.replyable is False:
            return PolicyRule.channel_not_replyable
        if channel_state.status is ConversationStatus.resolved:
            return PolicyRule.channel_resolved
        if channel_state.paused:
            return PolicyRule.channel_wootpilot_paused
        if channel_state.assigned_agent_id or channel_state.assigned_team_id:
            return PolicyRule.channel_assigned_to_human
        return None


def _reason_value(reason: PolicyRule | str) -> str:
    return reason.value if isinstance(reason, PolicyRule) else reason


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def _public_price_rule_from_safety_context(
    content: str,
    safety_context: dict | None,
) -> PolicyRule | None:
    """Re-run price policy using the catalog snapshot captured at queue time."""

    catalog_payload = (safety_context or {}).get("catalog_context")
    if not isinstance(catalog_payload, dict):
        catalog_context = StructuredCatalogContext(query="")
    else:
        catalog_context = StructuredCatalogContext.model_validate(catalog_payload)
    return public_price_policy_rule(content, catalog_context)


def _is_human_review_private_note(safety_context: dict | None) -> bool:
    """Return whether a private note represents a human-review handoff."""

    payload = safety_context or {}
    rule_ids = payload.get("workflow_rule_ids") or []
    risk_reasons = payload.get("workflow_risk_reasons") or []
    if not isinstance(rule_ids, list):
        rule_ids = []
    if not isinstance(risk_reasons, list):
        risk_reasons = []
    markers = [str(item) for item in [*rule_ids, *risk_reasons]]
    return any(
        marker.startswith("public.") or marker.startswith("intent.")
        for marker in markers
    )
