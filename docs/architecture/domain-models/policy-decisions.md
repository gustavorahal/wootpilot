# Policy Decisions

`PolicyDecision` is the structured result of deterministic policy. It should be
created before model calls, after model proposals, and immediately before any
public side effect.

## Shape

```python
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class PolicyOutcome(StrEnum):
    allow = "allow"
    block = "block"
    needs_human = "needs_human"
    private_note_only = "private_note_only"
    shadow_only = "shadow_only"


class PolicyRuleSeverity(StrEnum):
    info = "info"
    warning = "warning"
    blocking = "blocking"


class PolicyEvaluationStage(StrEnum):
    pre_model = "pre_model"
    post_model = "post_model"
    pre_send = "pre_send"
    connector_action = "connector_action"


class PolicyRuleResult(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    rule_id: str
    severity: PolicyRuleSeverity
    reason: str


class PolicyDecision(BaseModel):
    """Deterministic policy outcome with auditable rule-level reasons."""

    model_config = ConfigDict(frozen=True, strict=True)

    outcome: PolicyOutcome
    rule_results: list[PolicyRuleResult] = Field(default_factory=list)
    public_message_allowed: bool = False
    private_note_allowed: bool = False
    connector_action_allowed: bool = False
```

## Rules

- Policy decisions should be deterministic and reproducible from their inputs.
- Persist the evaluation stage so audits can distinguish invocation gating,
  proposal validation, and final pre-send checks.
- Include stable `rule_id` values so tests can assert exact behavior.
- Do not use free-form model reasoning as policy.
- Persist decisions that affect agent invocation, outbound execution, or connector
  action execution.
- Public sends require a fresh policy decision immediately before execution.
