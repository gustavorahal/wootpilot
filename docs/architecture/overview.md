# Architecture Overview

## Proposed Repository Layout

```text
wootpilot/
  README.md
  docs/
    wootpilot-initial-plan.md
      architecture/
      overview.md
      vocabulary.md
      channels.md
      connectors.md
      domain-models/
        overview.md
        tenants.md
        money.md
        price-snapshots.md
        availability-snapshots.md
        product-snapshots.md
        normalized-messages.md
        conversation-state.md
        triage-results.md
        risk-signals.md
        policy-decisions.md
        agent-proposals.md
        outbound-actions.md
        connector-installations.md
        context-snapshots.md
        audit-records.md
      mvp-conversation-behavior.md
      policy-and-agent-workflow.md
      langchain-langgraph.md
      persistence.md
      observability.md
    configuration.md
    implementation/
      milestones.md
      slices/
        00-runnable-skeleton.md
        01-authenticated-webhook-intake.md
        02-event-filtering-and-conversation-state.md
        03-mock-product-context.md
        04-shadow-workflow.md
        05-openrouter-model-proposals.md
        06-copilot-private-notes.md
        07-limited-auto-public-replies.md
        08-woocommerce-store-api.md
        09-production-readiness.md
  data/
    mock-woocommerce/
      catalog.demo-car-parts.json
  infra/
    chatwoot-dev/
      compose.yml
      chatwoot.env
      README.md
  scripts/
    chatwoot-dev-up
    chatwoot-dev-down
    chatwoot-dev-reset
    chatwoot-dev-logs
  pyproject.toml
  src/
    wootpilot/
      api/
        main.py
        routes/
          health.py
          webhooks.py
        deps.py
      ingress/
        auth.py
        replay.py
        idempotency.py
        webhook_pipeline.py
      agents/
        chatwoot_support_graph.py
        checkpoints.py
        model_adapter.py
        prompts.py
        schemas.py
        state.py
      domain/
        tenants.py
        conversation.py
        money.py
        price_snapshots.py
        availability_snapshots.py
        policy.py
        triage.py
        catalog.py
        actions.py
        audit.py
        resources/
          products.py
          orders.py
          customers.py
      ports/
        clock.py
        ids.py
        model_proposals.py
        unit_of_work.py
        channels.py
        repositories.py
      services/
        handle_webhook_event.py
        run_support_workflow.py
        catalog_context_service.py
        execute_outbound_action.py
        policy_service.py
      channels/
        chatwoot/
          adapter.py
          client.py
          schemas.py
          translators.py
      connectors/
        base.py
        capabilities.py
        registry.py
        woocommerce/
          adapter.py
          client.py
          translators.py
          raw_schemas.py
        http_client.py
      persistence/
        database.py
        profiles.py
        models.py
        repositories.py
        translators.py
        outbox.py
      observability/
        correlation.py
        redaction.py
      settings.py
  .env.example
  .env.public-dev.example
  tests/
    unit/
    integration/
    evals/
```

## Layering

```text
Chatwoot webhook
  -> authenticated ingress pipeline
  -> raw event store
  -> dedupe and replay checks
  -> channel translator
  -> handle-webhook use case
  -> conversation state read
  -> connector registry
  -> connector capability protocol
  -> normalized resource snapshots
  -> policy-aware agent context
  -> LangGraph support workflow
  -> guarded action proposal
  -> idempotent outbound action execution
  -> human-active or explicit resume signal observed through Chatwoot
```

The agent graph should make workflow decisions from prepared inputs. It should
not know how to discover WooCommerce, parse connector payloads, decide which
tenant installation to use, write to Chatwoot, or persist database rows.
Application services should handle those details and pass compact structured
context into the graph.

Use LangGraph as the top-level workflow runtime, not a generic agent loop. The
graph should be a typed `StateGraph` with explicit nodes and stable state keys.
LangChain belongs at the model boundary: chat model adapters, structured output,
messages, and optional middleware when it fits a defined use case. See
[LangChain And LangGraph Guidance](langchain-langgraph.md) for the framework
feature choices that implementation should follow.

Application services should be organized around a few durable use cases, not one
service per tiny operation. Version 1 should start with these use-case modules:

```text
HandleWebhookEvent
  Authenticates and deduplicates a channel event, stores the raw event, stores
  normalized message data when present, and starts the support workflow only for
  eligible customer messages.

RunSupportWorkflow
  Loads conversation state and business context, persists the context snapshots
  used by the run, applies policy, invokes the graph, and turns the graph result
  into an audited decision or queued outbound action.

BuildCatalogContext
  Resolves the configured product catalog connector, reads product snapshots,
  and returns compact policy-aware context for the workflow.

ExecuteOutboundAction
  Claims queued actions, re-checks channel safety and policy, writes through the
  channel port, and updates action status idempotently.
```

These modules may call small helper functions, but the use cases should remain
the main test boundaries. Avoid creating many shallow services whose public API
is just one line of another module.

Repository implementations can be grouped by aggregate or persistence profile
while the codebase is small. Do not create one repository class per table merely
because a table exists. Introduce narrower repositories when a use case needs a
clear testing boundary, a different backend implementation, or concurrency
semantics such as outbox claiming.

## Application Ports

The core workflow should depend on narrow protocols for external effects. This
keeps adapters replaceable without requiring a large abstraction framework.

Initial ports:

```text
RawEventStore
ConversationMessageRepository
ConversationStateRepository
AgentRunRepository
ContextSnapshotRepository
AuditRecordRepository
PolicyDecisionRepository
OutboundActionQueue
ConnectorInstallationRepository
ChannelWriter
ConversationSafetyReader
ModelProposalPort
UnitOfWork
Clock
IdGenerator
```

Use concrete implementations directly when no boundary exists yet. Add a port
when the dependency crosses process, provider, database, model, or time/id
generation boundaries, or when tests need to assert behavior at a meaningful
workflow boundary.

## Boundary Rules

Ingress should finish before agent reasoning starts. FastAPI handlers should stay
thin: parse transport details, call `HandleWebhookEvent`, and translate returned
application errors into HTTP responses. The ingress use case should authenticate
requests, reject replays, persist raw events, deduplicate provider events, and
call channel translators to produce domain event/message objects. LangGraph
should receive trusted domain input and prepared context.

The agent graph should produce workflow decisions and action proposals. It
should not perform connector HTTP reads, write database rows, mark a message as
sent, or call Chatwoot APIs. Outbound execution should happen through a small use
case that performs final policy checks, re-reads human operator and replyability
state through a channel-facing safety port, sends through the channel writer,
and records the result idempotently.

Graph nodes should return partial state updates rather than mutating state.
Use LangGraph node-level retry policies for transient LLM/provider reads, and
route exhausted failures into durable WootPilot decisions instead of letting
exceptions discard run context. Do not retry policy failures or Chatwoot writes
inside the graph.

Connector packages should map raw external payloads into domain snapshots.
Services that build context should consume those snapshots. Graph nodes should
not depend on raw WooCommerce Store API fields or perform connector discovery.

The domain model docs are the source of truth for shared vocabulary. If a concept
appears in persistence, policy, connectors, and agent prompts, define it in
`docs/architecture/domain-models/` before implementing it.

Use [Architecture Vocabulary](vocabulary.md) for code role names. Adapters own
boundaries, translators convert representations, clients perform low-level API
calls, repositories persist domain objects, registries select configured adapters
or installations, and services orchestrate workflows.

The MVP should stay API-only. Do not add an admin UI before webhook intake,
product context, policy, private notes, and limited auto replies work through
the API and local Chatwoot stack.

The live MVP integration target is the public dev Chatwoot server at
`https://chat.gmrahal.net/`. That server should be used to verify Meta-connected
channel back-and-forth: customer message enters Chatwoot, Chatwoot notifies
WootPilot, WootPilot writes through Chatwoot APIs, and human replies or control
signals in Chatwoot affect later automation. See
[MVP Conversation Behavior](mvp-conversation-behavior.md).

For implementation work, the repeatable full-stack testing ground is the
public-dev laptop harness in
[infra/public-dev-laptop](../../infra/public-dev-laptop/README.md). It routes
`https://wootpilot-local-dev.gmrahal.net` through the `wootpilot-local-dev`
Cloudflare tunnel to local WootPilot on port `8000`, syncs the Chatwoot webhook,
and checks readiness before live WhatsApp/Meta smoke tests.

## Python Baseline

The primary runtime should be Python 3.14. Keep Python 3.13 compatibility only
while dependency support makes it useful. Use CI to test the exact supported
versions rather than promising a wider range than the project actually exercises.

Prefer modern Python patterns:

- Pydantic v2 models for validation, settings, JSON schema, and durable snapshots.
- `Protocol` for connector and channel capability boundaries.
- `StrEnum` for persisted vocabulary.
- `type` aliases for important identifiers once the implementation starts to
  accumulate repeated string ids.
- `Field(default_factory=...)` for mutable defaults.
- Ruff for linting, formatting, import sorting, pyupgrade rules, and docstring
  formatting of Python examples.

## Configuration Boundary

Only the app composition layer should read environment variables. Implement
`src/wootpilot/settings.py` with `pydantic-settings` and a `WOOTPILOT_` prefix.
Services, adapters, graph builders, and repositories should receive typed
settings or explicit constructor arguments. Domain models must never read
environment variables.

See [Configuration](../configuration.md) for the live-dev Chatwoot settings,
including the difference between local API access through
`https://chat.gmrahal.net` and server-side Docker network access through
`http://chatwoot-web:3000`.
