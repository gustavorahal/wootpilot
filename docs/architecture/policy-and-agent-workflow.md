# Policy And Agent Workflow

## Bot Modes

WootPilot should support three operating modes.

### Shadow

The agent evaluates the conversation but does not write to Chatwoot.

Use this mode for early production testing.

### Copilot

The agent writes private notes with suggested replies and reasoning summaries.

Use this mode when humans should remain fully in control of customer-facing
messages.

### Limited Auto

The agent may send public messages only when deterministic policy says the case
is low risk.

Examples:

- Answering simple FAQ questions from approved context.
- Sending a public product or documentation link.
- Asking for missing information.
- Confirming that a human will review the request.

## Deterministic Policy

Policy should run before and after the LLM.

Pre-model policy decides whether a message is eligible for AI handling.

Post-model policy validates any proposed outbound action.

Initial policy rules:

- Ignore private notes.
- Ignore outbound messages.
- Ignore bot or AI echoes.
- Ignore system events.
- Do not reply when Chatwoot or channel policy says replies are closed.
- Do not send public handoff confirmations when a human agent is already active.
- Do not make claims about refunds, discounts, guarantees, legal policy,
  technical compatibility, delivery time, or account changes without approval.
- Do not expose private reasoning or internal triage in public messages.
- Do not send if the target conversation id does not match the current event.

## LangGraph Workflow

The first graph should be explicit and boring in the best way.

State:

```text
raw_event
normalized_message
conversation_context
human_operator_state
triage_result
business_context
catalog_context
bot_mode
agent_decision
outbound_action
outbound_result
audit_record
```

Nodes:

```text
verify_event
dedupe_event
normalize_message
load_human_operator_state
should_invoke
triage_message
load_catalog_context
policy_gate
llm_decision
validate_outbound_action
execute_outbound_action
persist_audit
```

Branching:

```text
ignored event -> persist audit -> done
shadow mode -> llm decision -> persist audit -> done
copilot mode -> private note candidate -> guard -> write note -> audit
limited auto safe -> public message candidate -> guard -> send -> audit
risky or uncertain -> private note -> guard -> write note -> audit
```

## Structured Outputs

Every model call that affects workflow state should return Pydantic-validated
structured output.

Initial decision schema:

```python
from enum import StrEnum
from pydantic import BaseModel


class BotMode(StrEnum):
    shadow = "shadow"
    copilot = "copilot"
    limited_auto = "limited_auto"


class AgentStatus(StrEnum):
    ignored = "ignored"
    shadow_logged = "shadow_logged"
    sent_public_message = "sent_public_message"
    sent_private_note = "sent_private_note"
    failed = "failed"


class OutboundKind(StrEnum):
    none = "none"
    public_message = "public_message"
    private_note = "private_note"


class AgentDecision(BaseModel):
    status: AgentStatus
    bot_mode: BotMode
    outbound_kind: OutboundKind
    summary: str
    public_message: str | None = None
    private_note: str | None = None
    risk_reasons: list[str] = []
    error_code: str | None = None
```
