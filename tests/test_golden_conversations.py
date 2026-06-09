from __future__ import annotations

from pathlib import Path

from wootpilot.evals.golden import load_golden_cases, run_golden_case


async def test_golden_conversation_suite() -> None:
    cases = load_golden_cases(Path("tests/fixtures/golden/conversations.json"))
    assert {case.id for case in cases} == {
        "low_risk_faq_public",
        "catalog_lookup_observe",
        "kit_escalation",
        "account_sensitive_request",
        "technical_support_escalation",
        "prompt_injection",
        "private_internal_information",
        "hidden_price",
        "quote_required_price",
        "zero_value_kit_placeholder",
        "pt_br_human_escalation",
        "pt_br_discount_review",
        "pt_br_prompt_injection",
    }

    failures = []
    for case in cases:
        result = await run_golden_case(case)
        missing_rules = set(case.expected_rule_ids) - set(result["rule_ids"])
        if (
            result["status"] != case.expected_status
            or result["action_kind"] != case.expected_action_kind
            or missing_rules
        ):
            failures.append(
                {
                    "id": case.id,
                    "expected_status": case.expected_status,
                    "actual_status": result["status"],
                    "expected_action_kind": case.expected_action_kind,
                    "actual_action_kind": result["action_kind"],
                    "missing_rules": sorted(missing_rules),
                    "actual_rules": result["rule_ids"],
                }
            )

    assert failures == []
