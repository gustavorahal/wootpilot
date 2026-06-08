"""Outbound action execution for Chatwoot writes."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from wootpilot.application.policy import public_price_policy_rule
from wootpilot.domain.models import (
    AgentActionKind,
    BotMode,
    OutboundActionStatus,
    StructuredCatalogContext,
)
from wootpilot.integrations.chatwoot import ChatwootClient
from wootpilot.observability import log_event, outbound_log_fields
from wootpilot.persistence.repositories import Repository
from wootpilot.settings import Settings
from wootpilot.time import Clock

logger = logging.getLogger(__name__)


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
        counts = {"sent": 0, "blocked": 0, "failed": 0}
        for action in await self.repo.list_queued_outbound_actions(
            limit=limit,
            now=self.clock.now(),
        ):
            await self.repo.mark_outbound_action(
                action_id=action.id,
                status=OutboundActionStatus.executing.value,
                updated_at=self.clock.now(),
                clear_next_attempt_at=True,
            )
            await self.repo.session.commit()
            blocked_reason = await self._blocked_reason(action)
            if blocked_reason:
                await self.repo.mark_outbound_action(
                    action_id=action.id,
                    status=OutboundActionStatus.blocked_by_policy.value,
                    updated_at=self.clock.now(),
                    failure_reason=blocked_reason,
                    clear_next_attempt_at=True,
                )
                await self.repo.session.commit()
                self._log_action_result(
                    action,
                    status=OutboundActionStatus.blocked_by_policy.value,
                    failure_reason=blocked_reason,
                )
                counts["blocked"] += 1
                continue
            try:
                provider_message_id = await self.chatwoot.create_message(
                    conversation_id=action.conversation_id,
                    content=action.content,
                    private=action.action_kind == AgentActionKind.private_note.value,
                )
            except Exception as exc:
                attempt_count = action.attempt_count + 1
                retryable = _retryable(exc)
                status = (
                    OutboundActionStatus.retryable_failure.value
                    if retryable and attempt_count < self.settings.outbound_max_attempts
                    else OutboundActionStatus.permanent_failure.value
                )
                next_attempt_at = (
                    self.clock.now()
                    + timedelta(seconds=self.settings.outbound_retry_delay_seconds)
                    if status == OutboundActionStatus.retryable_failure.value
                    else None
                )
                await self.repo.mark_outbound_action(
                    action_id=action.id,
                    status=status,
                    updated_at=self.clock.now(),
                    failure_reason=exc.__class__.__name__,
                    attempt_count=attempt_count,
                    next_attempt_at=next_attempt_at,
                    clear_next_attempt_at=next_attempt_at is None,
                    error_code=exc.__class__.__name__,
                )
                await self.repo.session.commit()
                self._log_action_result(
                    action,
                    status=status,
                    failure_reason=exc.__class__.__name__,
                    level=logging.WARNING,
                )
                counts["failed"] += 1
                continue
            post_send_failure_reason = await self._apply_post_send_updates(action)
            await self.repo.mark_outbound_action(
                action_id=action.id,
                status=OutboundActionStatus.sent.value,
                updated_at=self.clock.now(),
                provider_message_id=provider_message_id,
                failure_reason=post_send_failure_reason,
                clear_next_attempt_at=True,
            )
            await self.repo.session.commit()
            self._log_action_result(
                action,
                status=OutboundActionStatus.sent.value,
                provider_message_id=provider_message_id,
                failure_reason=post_send_failure_reason,
            )
            counts["sent"] += 1
        return counts

    async def _apply_post_send_updates(self, action) -> str | None:
        failure_reasons = []
        if status_failure := await self._apply_success_status_transition(action):
            failure_reasons.append(status_failure)
        if label_failure := await self._apply_private_review_label(action):
            failure_reasons.append(label_failure)
        return ";".join(failure_reasons) if failure_reasons else None

    async def _apply_success_status_transition(self, action) -> str | None:
        """Optionally move a conversation to a configured post-reply status.

        The customer-visible message has already been sent when this runs. If
        the status update fails, the action stays sent so retries cannot
        duplicate the public reply; the failure is recorded for operators.
        """

        if action.action_kind != AgentActionKind.public_message.value:
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
        except Exception as exc:
            log_event(
                logger,
                "outbound_status_update_failed",
                level=logging.WARNING,
                action_id=action.id,
                tenant_id=action.tenant_id,
                channel_id=action.channel_id,
                conversation_id=action.conversation_id,
                action_kind=action.action_kind,
                target_status=target_status,
                failure_reason=exc.__class__.__name__,
            )
            return f"status_update_failed:{exc.__class__.__name__}"
        return None

    async def _apply_private_review_label(self, action) -> str | None:
        if action.action_kind != AgentActionKind.private_note.value:
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
        except Exception as exc:
            log_event(
                logger,
                "outbound_label_update_failed",
                level=logging.WARNING,
                action_id=action.id,
                tenant_id=action.tenant_id,
                channel_id=action.channel_id,
                conversation_id=action.conversation_id,
                action_kind=action.action_kind,
                label=target_label,
                failure_reason=exc.__class__.__name__,
            )
            return f"label_update_failed:{exc.__class__.__name__}"
        return None

    def _log_action_result(
        self,
        action,
        *,
        status: str,
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
                action_kind=action.action_kind,
                status=status,
                provider_message_id=provider_message_id,
                failure_reason=failure_reason,
            ),
        )

    async def _blocked_reason(self, action) -> str | None:
        if action.action_kind == AgentActionKind.private_note.value:
            if not action.content.strip():
                return "content.empty"
            return None
        if action.action_kind == AgentActionKind.public_message.value:
            if self.settings.bot_mode is not BotMode.limited_auto:
                return "mode.public_reply_not_enabled"
            if (
                self.settings.env == "production"
                and not self.settings.limited_auto_production_allowed
            ):
                return "production_public_auto_not_enabled"
            if not action.content.strip():
                return "content.empty"
            lowered = action.content.lower()
            if any(
                term in lowered
                for term in ("internal", "triage", "policy", "reasoning")
            ):
                return "public.no_internal_reasoning"
            price_rule = _public_price_rule_from_safety_context(
                action.content,
                action.safety_context,
            )
            if price_rule:
                return price_rule
            state = await self.repo.get_conversation_state(
                tenant_id=action.tenant_id,
                channel_id=action.channel_id,
                conversation_id=action.conversation_id,
            )
            if state is None:
                return "conversation.safety_state_missing"
            if not state.replyable:
                return "conversation.not_replyable"
            if state.status == "resolved":
                return "conversation.resolved"
            if state.paused:
                return "conversation.wootpilot_paused"
            now = self.clock.now()
            human_active_until = _aware(state.human_active_until)
            if (
                human_active_until
                and human_active_until > now
                and not state.auto_ok
            ):
                return "conversation.human_active"
            if (
                self.settings.suppress_public_auto_when_assigned
                and (state.assigned_agent_id or state.assigned_team_id)
                and not state.auto_ok
            ):
                return "conversation.assigned_to_human"
            await self.repo.session.commit()
            channel_state = await self.chatwoot.get_conversation_safety(
                conversation_id=action.conversation_id
            )
            if channel_state.conversation_id != action.conversation_id:
                return "conversation.id_mismatch"
            if channel_state.replyable is False:
                return "channel.not_replyable"
            if channel_state.status == "resolved":
                return "channel.resolved"
            if channel_state.paused:
                return "channel.wootpilot_paused"
            if (
                self.settings.suppress_public_auto_when_assigned
                and (
                    channel_state.assigned_agent_id
                    or channel_state.assigned_team_id
                )
                and not state.auto_ok
            ):
                return "channel.assigned_to_human"
            return None
        return "unknown_action_kind"


def _retryable(exc: Exception) -> bool:
    status_code = getattr(getattr(exc, "response", None), "status_code", None)
    return status_code in {408, 409, 425, 429, 500, 502, 503, 504}


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def _public_price_rule_from_safety_context(
    content: str,
    safety_context: dict | None,
) -> str | None:
    catalog_payload = (safety_context or {}).get("catalog_context")
    if not isinstance(catalog_payload, dict):
        catalog_context = StructuredCatalogContext(query="")
    else:
        catalog_context = StructuredCatalogContext.model_validate(catalog_payload)
    return public_price_policy_rule(content, catalog_context)


def _is_human_review_private_note(safety_context: dict | None) -> bool:
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
