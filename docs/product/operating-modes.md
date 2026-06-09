# Operating Modes

> Type: Living product reference
> Status: Current

WootPilot uses operating modes as a safety ladder. Each mode controls how far
the workflow may act after receiving an eligible customer message.

## Observe

`observe` evaluates the message, builds catalog context, calls the model,
applies policy, persists the decision, and emits logs/audit records.

It never writes a private note or public reply to Chatwoot. Use this mode for
public-dev smoke tests and early production observation.

## Assist

`assist` queues a private Chatwoot note with the suggested response,
relevant context, and risk reasons. The customer cannot see this note.

A human remains in control of the customer-facing reply. This is the safest
customer-support write mode. The committed alpha templates still default to
`public_reply` so development and public-dev smoke tests exercise the full
customer-visible path.

## Public Reply

`public_reply` may queue a public customer-visible reply only when
deterministic policy says the exact proposed content is safe.

It still hands risky or uncertain cases to humans through private notes. Before
sending, the outbound executor re-checks automation mode, conversation state,
replyability, assignment, human activity, status, content leakage, and
price-claim safety.

`public_reply` is the default alpha setup in committed templates so development
and public-dev exercise the full customer-visible flow. Production can still use
deployment-level guards before enabling public sends.

## Configuration

Set the active mode with:

```text
AUTOMATION_MODE=observe
AUTOMATION_MODE=assist
AUTOMATION_MODE=public_reply
```

Public-dev templates default to `public_reply` so live tests prove webhook,
context, model, policy, audit, outbound queueing, and Chatwoot delivery together.
