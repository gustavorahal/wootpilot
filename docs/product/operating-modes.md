# Operating Modes

> Type: Living product reference
> Status: Current

WootPilot uses operating modes as a safety ladder. Each mode controls how far
the workflow may act after receiving an eligible customer message.

## Shadow

Shadow mode evaluates the message, builds catalog context, calls the model,
applies policy, persists the decision, and emits logs/audit records.

It never writes a private note or public reply to Chatwoot. Use this mode for
public-dev smoke tests and early production observation.

## Copilot

Copilot mode queues a private Chatwoot note with the suggested response,
relevant context, and risk reasons. The customer cannot see this note.

A human remains in control of the customer-facing reply. This is the safest
write mode and the default practical mode for early support usage.

## Limited Auto

Limited auto mode may queue a public customer-visible reply only when
deterministic policy says the exact proposed content is safe.

It still hands risky or uncertain cases to humans through private notes. Before
sending, the outbound executor re-checks bot mode, conversation state,
replyability, assignment, human activity, status, content leakage, and
price-claim safety.

Limited auto should require explicit configuration and should not be the default
for new tenants or local development.

## Configuration

Set the active mode with:

```text
WOOTPILOT_BOT_MODE=shadow
WOOTPILOT_BOT_MODE=copilot
WOOTPILOT_BOT_MODE=limited_auto
```

Public-dev templates default to `shadow` so live tests can prove webhook,
context, model, policy, and audit behavior before WootPilot writes back to
Chatwoot.
