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
      policy-and-agent-workflow.md
      persistence.md
      observability.md
    implementation/
      testing-plan.md
      milestones.md
  data/
    mock-woocommerce/
      catalog.demo-car-parts.json
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
```

The agent graph should make workflow decisions from prepared inputs. It should
not know how to discover WooCommerce, parse connector payloads, decide which
tenant installation to use, write to Chatwoot, or persist database rows.
Application services should handle those details and pass compact structured
context into the graph.

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
