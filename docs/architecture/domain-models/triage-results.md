# Triage Results

`TriageResult` is the deterministic classification of a message before model
reasoning. It helps decide whether to invoke the LLM, which context to load, and
which policy path applies.

## Shape

```python
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from wootpilot.domain.risk_signals import RiskSignal


class Intent(StrEnum):
    product_lookup = "product_lookup"
    compatibility_question = "compatibility_question"
    billing_or_account = "billing_or_account"
    technical_support = "technical_support"
    order_status = "order_status"
    simple_faq = "simple_faq"
    unknown = "unknown"


class TriageResult(BaseModel):
    """Deterministic pre-model classification."""

    model_config = ConfigDict(frozen=True, strict=True)

    intent: Intent
    should_invoke_agent: bool
    requires_human: bool = False
    risk_signals: list[RiskSignal] = Field(default_factory=list)
    matched_terms: list[str] = Field(default_factory=list)
```

## Rules

- Prefer deterministic rules before model calls.
- Use triage to reduce unnecessary model calls, not to make final public claims.
- Preserve matched terms when they explain why context was loaded.
- Escalate unknown or sensitive intents rather than forcing a confident label.
