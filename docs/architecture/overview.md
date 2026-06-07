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
      agents/
        chatwoot_support_graph.py
        prompts.py
        schemas.py
        state.py
      domain/
        conversation.py
        policy.py
        triage.py
        catalog.py
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
  -> channel normalizer
  -> LangGraph node
  -> application service
  -> connector registry
  -> connector capability protocol
  -> normalized resource snapshots
  -> policy-aware agent context
```

The agent graph should orchestrate workflow state. It should not know how to
discover WooCommerce, parse connector payloads, or decide which tenant
installation to use. Application services should handle those details and pass
compact structured context into the graph.
