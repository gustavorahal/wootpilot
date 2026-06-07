# Architecture Overview

## Proposed Repository Layout

```text
wootpilot/
  README.md
  docs/
    wootpilot-initial-plan.md
    architecture/
      overview.md
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
      services/
        conversation_service.py
        conversation_state_service.py
        triage_service.py
        catalog_context_service.py
        outbound_guard_service.py
        outbound_action_service.py
      channels/
        chatwoot/
          client.py
          schemas.py
          webhook_normalizer.py
      connectors/
        base.py
        capabilities.py
        registry.py
        woocommerce/
          connector.py
          client.py
          mappers.py
          raw_schemas.py
          repositories.py
        http_client.py
      persistence/
        database.py
        models.py
        repositories.py
        outbox.py
      observability/
        tracing.py
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
  -> channel normalizer
  -> application service
  -> LangGraph support workflow
  -> connector registry
  -> connector capability protocol
  -> normalized resource snapshots
  -> policy-aware agent context
  -> guarded action proposal
  -> idempotent outbound action execution
```

The agent graph should orchestrate workflow state. It should not know how to
discover WooCommerce, parse connector payloads, or decide which tenant
installation to use. Application services should handle those details and pass
compact structured context into the graph.

## Boundary Rules

Ingress should finish before agent reasoning starts. FastAPI handlers should
authenticate requests, reject replays, persist raw events, deduplicate provider
events, and normalize channel payloads into internal message models. LangGraph
should receive a trusted, normalized input plus service dependencies.

The agent graph should produce action proposals. It should not directly mark a
message as sent or call Chatwoot APIs. Outbound execution should happen through a
small action service that performs final policy checks, re-reads human operator
state, sends through the channel client, and records the result idempotently.

Connector packages should map raw external payloads into domain snapshots.
Services and graph nodes should not depend on raw WooCommerce Store API fields.

The domain model docs are the source of truth for shared vocabulary. If a concept
appears in persistence, policy, connectors, and agent prompts, define it in
`docs/architecture/domain-models/` before implementing it.

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
