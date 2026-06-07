# Risk Signals

`RiskSignal` is a stable vocabulary item that explains why a workflow needs
guarding, human review, or restricted output.

## Shape

```python
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class RiskSignalCode(StrEnum):
    compatibility_requires_human_review = "compatibility_requires_human_review"
    price_not_mentionable = "price_not_mentionable"
    availability_not_mentionable = "availability_not_mentionable"
    account_sensitive = "account_sensitive"
    billing_sensitive = "billing_sensitive"
    technical_diagnosis = "technical_diagnosis"
    policy_sensitive = "policy_sensitive"
    prompt_injection_attempt = "prompt_injection_attempt"
    ambiguous_product_match = "ambiguous_product_match"
    human_operator_active = "human_operator_active"


class RiskSignal(BaseModel):
    """Machine-readable reason a workflow may need extra guardrails."""

    model_config = ConfigDict(frozen=True, strict=True)

    code: RiskSignalCode
    detail: str | None = None
```

## Rules

- Use stable codes in tests and policy decisions.
- Keep user-facing wording separate from risk signal codes.
- Attach risk signals to snapshots, triage results, policy decisions, and agent
  proposals when they explain behavior.
- Do not let arbitrary LLM strings become new risk categories without review.
