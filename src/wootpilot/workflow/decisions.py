"""Workflow decision builders used by graph nodes."""

from __future__ import annotations

from wootpilot.domain.models import (
    AgentActionKind,
    AgentProposal,
    AgentRunStatus,
    AutomationMode,
    PolicyDecision,
    PolicyRule,
    TriageResult,
    WorkflowDecision,
)

__all__ = [
    "missing_model_proposal_decision",
    "model_proposal_failed_decision",
    "non_customer_turn_decision",
    "observe_decision",
    "post_model_policy_blocked_decision",
    "pre_model_policy_blocked_decision",
    "private_note_decision",
    "public_message_decision",
    "public_reply_review_decision",
    "public_reply_review_note",
]


def non_customer_turn_decision() -> WorkflowDecision:
    """Return the terminal decision for turns WootPilot should ignore."""

    return WorkflowDecision(
        status=AgentRunStatus.ignored,
        summary="Message is not an eligible public inbound customer turn.",
        rule_ids=[PolicyRule.ingress_customer_public_inbound_required],
    )


def pre_model_policy_blocked_decision(
    *, decision: PolicyDecision, triage: TriageResult
) -> WorkflowDecision:
    """Return the terminal decision for deterministic pre-model policy blocks."""

    return WorkflowDecision(
        status=AgentRunStatus.blocked_by_policy,
        summary="Pre-model policy blocked the workflow.",
        rule_ids=decision.rule_ids,
        risk_reasons=triage.risk_signals,
    )


def model_proposal_failed_decision(error: str | None) -> WorkflowDecision:
    """Return the terminal decision for provider/model proposal failures."""

    return WorkflowDecision(
        status=AgentRunStatus.failed,
        summary="Model proposal failed.",
        rule_ids=[PolicyRule.model_proposal_failed],
        risk_reasons=[error or "unknown"],
    )


def public_reply_review_decision(
    *,
    proposal: AgentProposal | None,
    decision: PolicyDecision,
    triage: TriageResult,
    note: str,
) -> WorkflowDecision:
    """Queue a private handoff note when an unsafe public reply is denied."""

    return WorkflowDecision(
        status=AgentRunStatus.queued_action,
        action_kind=AgentActionKind.private_note,
        content=note,
        summary="Public reply requires human review.",
        rule_ids=decision.rule_ids,
        risk_reasons=triage.risk_signals
        + (proposal.risk_reasons if proposal else []),
    )


def post_model_policy_blocked_decision(
    *, proposal: AgentProposal | None, decision: PolicyDecision
) -> WorkflowDecision:
    """Return the terminal decision for post-model policy blocks."""

    return WorkflowDecision(
        status=AgentRunStatus.blocked_by_policy,
        summary="Post-model policy blocked the proposed action.",
        rule_ids=decision.rule_ids,
        risk_reasons=proposal.risk_reasons if proposal else [],
    )


def observe_decision(proposal: AgentProposal) -> WorkflowDecision:
    """Record a proposal without creating an outbound action."""

    return WorkflowDecision(
        status=AgentRunStatus.proposed,
        action_kind=AgentActionKind.none,
        summary=proposal.summary,
        risk_reasons=proposal.risk_reasons,
    )


def private_note_decision(proposal: AgentProposal) -> WorkflowDecision:
    """Queue an internal note for a human agent."""

    content = proposal.private_note or proposal.public_message or proposal.summary
    return WorkflowDecision(
        status=AgentRunStatus.queued_action,
        action_kind=AgentActionKind.private_note,
        content=content,
        summary=proposal.summary,
        risk_reasons=proposal.risk_reasons,
    )


def public_message_decision(proposal: AgentProposal) -> WorkflowDecision:
    """Queue a customer-visible reply for delivery."""

    return WorkflowDecision(
        status=AgentRunStatus.queued_action,
        action_kind=AgentActionKind.public_message,
        content=proposal.public_message,
        summary=proposal.summary,
        risk_reasons=proposal.risk_reasons,
    )


def missing_model_proposal_decision() -> WorkflowDecision:
    """Fail defensively when a graph path needs a missing proposal."""

    return WorkflowDecision(
        status=AgentRunStatus.failed,
        summary="No proposal was available after validation.",
        rule_ids=[PolicyRule.model_no_proposal],
    )


def public_reply_review_note(
    *,
    proposal: AgentProposal | None,
    automation_mode: AutomationMode,
    rule_ids: list[PolicyRule],
    triage: TriageResult,
) -> str | None:
    """Build a private handoff note when a public reply is denied.

    The unsafe public draft is intentionally not copied into the note. A human
    gets the review reason and model summary, while customer-visible text still
    requires human composition inside Chatwoot.
    """

    if automation_mode is not AutomationMode.public_reply or proposal is None:
        return None
    if proposal.action_kind is not AgentActionKind.public_message:
        return None
    reasons = sorted(
        {item.value for item in rule_ids}
        | set(triage.risk_signals)
        | set(proposal.risk_reasons)
    )
    lines = [
        "WootPilot did not send a public reply because this turn needs human review.",
        f"Summary: {proposal.summary}",
    ]
    if reasons:
        lines.append(f"Review reasons: {', '.join(reasons)}")
    return "\n".join(lines)
