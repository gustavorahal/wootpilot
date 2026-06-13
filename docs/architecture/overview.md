# Architecture Overview

WootPilot is an API-first support automation service around Chatwoot. Chatwoot
owns the customer conversation and agent UI. WootPilot receives signed Chatwoot
webhooks, normalizes them into domain objects, prepares business context, runs a
typed LangGraph workflow, persists an audit trail, and writes approved actions
back through Chatwoot.

The current alpha is intentionally small: one Chatwoot channel, one configured
product catalog source, one support workflow, and one outbound action pipeline.

## Documentation Layout

```text
docs/
  README.md
  product/
    conversation-behavior.md
  architecture/
    overview.md
    workflow.md
    chatwoot-channel.md
    connectors.md
    persistence.md
    configuration.md
    observability.md
    production-readiness.md
    langchain-langgraph.md
  reference/
    glossary.md
    support-workflow-graph.mmd
    support-workflow-graph.png
  adr/
    README.md
```

`architecture/` documents the current implementation. Future-facing rationale
belongs in ADRs or in the production-readiness checklist, not mixed into these
current-state pages.

## Runtime Flow

```text
Chatwoot webhook
  -> FastAPI route
  -> Chatwoot signature verification
  -> raw event persistence and dedupe
  -> Chatwoot payload translation
  -> conversation state update
  -> catalog context loading
  -> LangGraph support workflow
  -> policy and audit persistence
  -> outbound action queue
  -> final Chatwoot safety check
  -> private note or public reply
```

Only public inbound customer messages invoke the support workflow. Human public
replies, private notes, bot echoes, outbound messages, and conversation events
update local state or audit data without calling the model.

## Application Boundaries

FastAPI handlers are thin transport adapters. They parse HTTP input, obtain
runtime settings and repositories, and call application use cases.

`HandleWebhookEvent` owns authenticated ingress. It verifies signatures, stores
raw events, deduplicates provider deliveries, translates Chatwoot payloads,
updates `ConversationState`, and commits durable ingress state before model work.

`RunCustomerSupportWorkflow` owns one customer turn. It loads catalog context,
stores the context snapshot used by the run, invokes the LangGraph workflow,
persists policy decisions and audit records, and queues any resulting outbound
action.

`ExecuteOutboundActions` owns effects back to Chatwoot. It claims queued actions,
performs final deterministic checks, sends through `ChatwootClient`, and records
sent, blocked, retryable, superseded, or failed outcomes.

Workflow decisions with `queued_action` are pending outbound effects. A separate
executor must run before Chatwoot or the customer receives the message.
Public replies are debounced before send eligibility so rapid follow-up customer
messages can supersede older queued public replies. Superseded actions remain in
`outbound_actions` as `status="superseded"` with failure reason
`conversation.superseded_by_new_customer_message`.

The graph itself does not call Chatwoot, read connectors, or write database
rows. It receives prepared domain objects and returns workflow decisions.

## Domain And Adapter Shape

Domain models live under
[`src/wootpilot/domain/models/`](../../src/wootpilot/domain/models/). They carry
the vocabulary shared by ingress, policy, workflow, persistence, and outbound
execution: normalized messages, conversation state, catalog snapshots, model
proposals, policy decisions, workflow decisions, runtime modes, and outbound
actions.

Adapters translate provider-specific representations at the boundary:

- `src/wootpilot/integrations/chatwoot.py` translates Chatwoot webhooks and
  performs Chatwoot API writes.
- `src/wootpilot/catalog/` selects and implements the product catalog source.
- `src/wootpilot/persistence/` maps domain objects to SQLAlchemy rows.
- `src/wootpilot/integrations/model.py` adapts model providers into WootPilot
  proposal schemas.

The code uses `Protocol` for meaningful external boundaries, `StrEnum` for
persisted vocabulary, Pydantic models for domain validation, and typed settings
for runtime configuration.

## Current Product Posture

`AUTOMATION_MODE=public_reply` is the default alpha setup so local and
public-dev testing exercises the full customer-visible path. Public replies are
still guarded by pre-model policy, post-model policy, local conversation state,
fresh Chatwoot safety reads, idempotency keys, and outbound retry limits.

The public-dev testing target is `https://chat.gmrahal.net/`, with local
WootPilot exposed through the public-dev tunnel documented in the root
README and `infra/public-dev-laptop/`.
