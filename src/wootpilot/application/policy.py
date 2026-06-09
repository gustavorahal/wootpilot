"""Deterministic policy and triage rules for the MVP support workflow."""

from __future__ import annotations

import re
from datetime import datetime

from wootpilot.domain.models import (
    AgentActionKind,
    AgentProposal,
    AutomationMode,
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
from wootpilot.text import searchable_text
from wootpilot.time import IdGenerator

__all__ = [
    "pre_model_policy",
    "public_internal_reasoning_rule",
    "public_price_policy_rule",
    "triage_message",
    "validate_proposal",
]

# Alpha note: these terms are intentionally broad and multilingual. They are not
# a claim of semantic intent detection; they are a conservative, deterministic
# review gate. False positives should become private notes or human review
# instead of unsafe public replies. Later versions can replace this with
# categorized policy rules or model-assisted classification while keeping
# deterministic final gates.
HANDOFF_TERMS: dict[str, str] = {
    "account": "account",
    "agent": "agent",
    "atendente": "agent",
    "callback": "callback",
    "cancel": "cancel",
    "cancelamento": "cancel",
    "cancelar": "cancel",
    "cancellation": "cancel",
    "complaint": "complaint",
    "devolucao": "refund",
    "discount": "discount",
    "desconto": "discount",
    "entrega": "delivery",
    "estorno": "refund",
    "garantia": "warranty",
    "gerente": "manager",
    "human": "human",
    "humano": "human",
    "ignore previous": "prompt_injection",
    "ignora as instrucoes": "prompt_injection",
    "instrucoes anteriores": "prompt_injection",
    "internal": "internal",
    "interno": "internal",
    "manager": "manager",
    "nota fiscal": "invoice",
    "pedido": "order",
    "person": "human",
    "pessoa": "human",
    "prazo": "delivery",
    "private": "private",
    "privado": "private",
    "refund": "refund",
    "reembolso": "refund",
    "reclamacao": "complaint",
    "senha": "password",
    "troca": "exchange",
    "warranty": "warranty",
}

PUBLIC_INTERNAL_REASONING_TERMS = {
    "internal",
    "interno",
    "instrucoes",
    "policy",
    "politica",
    "raciocinio",
    "reasoning",
    "triage",
    "triagem",
}


def triage_message(message: NormalizedMessage) -> TriageResult:
    """Classify conservative alpha risk signals before model/provider work.

    The keyword list favors safety over recall precision. A message mentioning
    refunds, discounts, private/internal details, or human escalation may be a
    normal customer question, but alpha public automation should route those
    turns toward review rather than treating this as final intelligence.
    """

    content = searchable_text(message.content)
    risk_signals = [
        f"intent.{signal}" for term, signal in HANDOFF_TERMS.items() if term in content
    ]
    intent = "handoff_requested" if risk_signals else "product_or_support"
    return TriageResult(
        should_invoke=True, intent=intent, risk_signals=sorted(risk_signals)
    )


def pre_model_policy(
    *,
    message: NormalizedMessage,
    state: ConversationState,
    triage: TriageResult,
    automation_mode: AutomationMode,
    now: datetime,
    ids: IdGenerator,
) -> PolicyDecision:
    """Apply deterministic conversation gates before any model call.

    The pre-model policy protects against replying to non-customer turns,
    resolved or paused conversations, human-owned conversations, and explicit
    handoff requests before external model work is attempted.
    """

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
        automation_mode is AutomationMode.public_reply
        and state.human_active_until
        and state.human_active_until > now
    ):
        rule_ids.append(PolicyRule.conversation_human_active)
    if automation_mode is AutomationMode.public_reply and (
        state.assigned_agent_id or state.assigned_team_id
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
            "automation_mode": automation_mode.value,
            "assigned_agent_id": state.assigned_agent_id,
            "assigned_team_id": state.assigned_team_id,
        },
        created_at=now,
    )


def validate_proposal(
    *,
    proposal: AgentProposal | None,
    automation_mode: AutomationMode,
    triage: TriageResult,
    catalog_context: StructuredCatalogContext,
    now: datetime,
    ids: IdGenerator,
) -> PolicyDecision:
    """Validate a model proposal before it can become an outbound action.

    Public replies are held to stricter rules than private notes because they
    can reach customers without human editing in public-reply mode.
    """

    rule_ids: list[PolicyRule] = []
    if proposal is None:
        rule_ids.append(PolicyRule.model_no_proposal)
    elif (
        automation_mode is AutomationMode.public_reply
        and proposal.action_kind == AgentActionKind.public_message
    ):
        text = proposal.public_message or ""
        if public_internal_reasoning_rule(text):
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
        details={
            "automation_mode": automation_mode.value,
            "triage": triage.model_dump(mode="json"),
        },
        created_at=now,
    )


def public_price_policy_rule(
    text: str,
    catalog_context: StructuredCatalogContext,
) -> PolicyRule | None:
    """Return a block rule when public text makes an unsafe price claim.

    Exact prices may be mentioned only when the current catalog snapshot says
    the product price is visible, current, and safe to quote.
    """

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


def public_internal_reasoning_rule(text: str) -> PolicyRule | None:
    """Return a block rule when public text leaks internal reasoning language."""

    lowered = searchable_text(text)
    if any(term in lowered for term in PUBLIC_INTERNAL_REASONING_TERMS):
        return PolicyRule.public_no_internal_reasoning
    return None


def _mentions_exact_price(text: str) -> bool:
    lowered = searchable_text(text)
    price_markers = ("r$", "$", "brl", "usd", "eur", "free", "grátis", "gratis")
    if any(marker in lowered for marker in price_markers):
        return True
    return bool(re.search(r"\b\d{1,3}(?:[.,]\d{3})*[.,]\d{2}\b", lowered))


def _normalize_price_text(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(text.lower().split())
