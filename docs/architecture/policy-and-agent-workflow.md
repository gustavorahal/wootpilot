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

## Ingress Before LangGraph

Inbound webhook handling should finish before LangGraph starts. The ingress
pipeline should:

- Authenticate the webhook through Chatwoot signature verification when
  available, or a configured shared-secret fallback.
- Reject stale or replayed requests using provider event ids, timestamps, and a
  short replay window.
- Persist the raw event before channel translation.
- Deduplicate provider events with database uniqueness constraints.
- Normalize Chatwoot payloads into internal message models.
- Mark ignored events without invoking the LLM.

LangGraph should receive a trusted normalized message plus service dependencies.
It should not know how to verify signatures or parse raw webhook envelopes.

## LangGraph Workflow

The first graph should be explicit and boring in the best way.

State:

```text
normalized_message
conversation_context
human_operator_state
triage_result
business_context
catalog_context
bot_mode
agent_proposal
outbound_action_candidate
outbound_result
audit_record
```

Agent nodes:

```text
load_human_operator_state
should_invoke
triage_message
load_catalog_context
policy_gate
llm_proposal
validate_outbound_action
queue_outbound_action
persist_audit
```

Outbound execution should be a separate application service or worker, not an
LLM node. That service should load the queued action, re-check policy, re-read
human operator state, send through the Chatwoot channel client, and update the
action status idempotently.

Branching:

```text
ignored event -> persist audit -> done
shadow mode -> llm proposal -> persist audit -> done
copilot mode -> private note candidate -> guard -> queue note action -> audit
limited auto safe -> public message candidate -> guard -> queue public action -> audit
risky or uncertain -> private note -> guard -> queue note action -> audit
```

Before a public send, the outbound executor must re-check the conversation id,
conversation replyability, bot mode, and human-active state. A case that was safe
at proposal time can become unsafe while waiting in the queue.

## Structured Outputs

Every model call that affects workflow state should return Pydantic-validated
structured output. The model returns proposals only. System execution status is
computed after deterministic checks and channel API results.

Initial proposal and status schema:

```python
from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field


class BotMode(StrEnum):
    shadow = "shadow"
    copilot = "copilot"
    limited_auto = "limited_auto"


class AgentRunStatus(StrEnum):
    ignored = "ignored"
    proposed = "proposed"
    blocked_by_policy = "blocked_by_policy"
    queued_action = "queued_action"
    sent_public_message = "sent_public_message"
    sent_private_note = "sent_private_note"
    failed = "failed"


class AgentActionKind(StrEnum):
    none = "none"
    public_message = "public_message"
    private_note = "private_note"


class AgentProposal(BaseModel):
    """LLM-produced action proposal; never a final execution result."""

    model_config = ConfigDict(strict=True)

    action_kind: AgentActionKind
    summary: str
    public_message: str | None = None
    private_note: str | None = None
    risk_reasons: list[str] = Field(default_factory=list)
    context_snapshot_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    error_code: str | None = None
```

`AgentRunStatus.sent_public_message`, `sent_private_note`, and `failed` are
assigned by WootPilot after action execution. The LLM must not claim that an
action was sent.
