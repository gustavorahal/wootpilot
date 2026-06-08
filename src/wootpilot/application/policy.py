"""Deterministic policy and triage rules for the MVP support workflow."""

from __future__ import annotations

import re
from datetime import datetime

from wootpilot.domain.models import (
    AgentActionKind,
    AgentProposal,
    BotMode,
    ConversationState,
    ConversationStatus,
    NormalizedMessage,
    PolicyDecision,
    PolicyOutcome,
    PolicyRule,
    PolicyStage,
    StructuredCatalogContext,
    TriageResult,
)
from wootpilot.time import IdGenerator

HANDOFF_TERMS = {
    "account",
    "agent",
    "callback",
    "cancel",
    "cancellation",
    "complaint",
    "discount",
    "ignore previous",
    "internal",
    "manager",
    "private",
    "refund",
    "senha",
    "warranty",
    "garantia",
    "human",
    "person",
}


def triage_message(message: NormalizedMessage) -> TriageResult:
    content = message.content.lower()
    risk_signals = [f"intent.{term}" for term in HANDOFF_TERMS if term in content]
    intent = "handoff_requested" if risk_signals else "product_or_support"
    return TriageResult(
        should_invoke=True, intent=intent, risk_signals=sorted(risk_signals)
    )


def pre_model_policy(
    *,
    message: NormalizedMessage,
    state: ConversationState,
    triage: TriageResult,
    bot_mode: BotMode,
    suppress_public_auto_when_assigned: bool,
    now: datetime,
    ids: IdGenerator,
) -> PolicyDecision:
    rule_ids: list[PolicyRule] = []
    if not message.is_customer_public_inbound():
        rule_ids.append(PolicyRule.ingress_customer_public_inbound_required)
    if not state.replyable:
        rule_ids.append(PolicyRule.conversation_not_replyable)
    if state.status is ConversationStatus.resolved:
        rule_ids.append(PolicyRule.conversation_resolved)
    if state.paused:
        rule_ids.append(PolicyRule.conversation_wootpilot_paused)
    if (
        state.human_active_until
        and state.human_active_until > now
        and not state.auto_ok
    ):
        rule_ids.append(PolicyRule.conversation_human_active)
    if (
        bot_mode is BotMode.limited_auto
        and suppress_public_auto_when_assigned
        and (state.assigned_agent_id or state.assigned_team_id)
        and not state.auto_ok
    ):
        rule_ids.append(PolicyRule.conversation_assigned_to_human)
    if "intent.human" in triage.risk_signals or "intent.agent" in triage.risk_signals:
        rule_ids.append(PolicyRule.intent_human_requested)

    outcome = PolicyOutcome.block if rule_ids else PolicyOutcome.allow
    return PolicyDecision(
        id=ids.new(),
        stage=PolicyStage.pre_model,
        outcome=outcome,
        rule_ids=rule_ids,
        details={
            "intent": triage.intent,
            "risk_signals": triage.risk_signals,
            "bot_mode": bot_mode.value,
            "assigned_agent_id": state.assigned_agent_id,
            "assigned_team_id": state.assigned_team_id,
        },
        created_at=now,
    )


def validate_proposal(
    *,
    proposal: AgentProposal | None,
    bot_mode: BotMode,
    triage: TriageResult,
    catalog_context: StructuredCatalogContext,
    now: datetime,
    ids: IdGenerator,
) -> PolicyDecision:
    rule_ids: list[PolicyRule] = []
    if proposal is None:
        rule_ids.append(PolicyRule.model_no_proposal)
    elif (
        bot_mode is BotMode.limited_auto
        and proposal.action_kind == AgentActionKind.public_message
    ):
        text = proposal.public_message or ""
        lowered = text.lower()
        if any(
            term in lowered for term in ("internal", "triage", "policy", "reasoning")
        ):
            rule_ids.append(PolicyRule.public_no_internal_reasoning)
        if triage.risk_signals:
            rule_ids.append(PolicyRule.public_risk_requires_review)
        if proposal.risk_reasons:
            rule_ids.append(PolicyRule.public_proposal_risk_requires_review)
        price_rule = public_price_policy_rule(text, catalog_context)
        if price_rule:
            rule_ids.append(price_rule)
    outcome = PolicyOutcome.block if rule_ids else PolicyOutcome.allow
    return PolicyDecision(
        id=ids.new(),
        stage=PolicyStage.post_model,
        outcome=outcome,
        rule_ids=rule_ids,
        details={"bot_mode": bot_mode.value, "triage": triage.model_dump(mode="json")},
        created_at=now,
    )


def public_price_policy_rule(
    text: str,
    catalog_context: StructuredCatalogContext,
) -> PolicyRule | None:
    """Return a block rule when public text makes an unsafe price claim."""

    if not _mentions_exact_price(text):
        return None
    mentionable_prices = {
        _normalize_price_text(product.price.display_text)
        for product in catalog_context.products
        if product.price.can_mention
        and product.price.display_text
        and not product.price.hidden
        and not product.price.quote_required
        and not product.price.stale
        and product.availability.is_available is not False
    }
    normalized_text = _normalize_price_text(text)
    if any(price and price in normalized_text for price in mentionable_prices):
        return None
    return PolicyRule.public_price_requires_mentionable_snapshot


def _mentions_exact_price(text: str) -> bool:
    lowered = text.lower()
    price_markers = ("r$", "$", "brl", "usd", "eur", "free", "grátis", "gratis")
    if any(marker in lowered for marker in price_markers):
        return True
    return bool(re.search(r"\b\d{1,3}(?:[.,]\d{3})*[.,]\d{2}\b", lowered))


def _normalize_price_text(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(text.lower().split())
