# Milestones And Open Questions

## Milestones

### Milestone 0: Skeleton

- Create Python package.
- Add FastAPI app.
- Add settings.
- Add health route.
- Add lint/test tooling.
- Add Dockerfile.

### Milestone 1: Chatwoot Webhook Foundation

- Receive webhooks.
- Verify optional signature.
- Normalize message events.
- Deduplicate events.
- Store raw events and normalized messages.
- Ignore non-customer events.

### Milestone 2: WooCommerce Product Context

- Add `ProductSnapshot`, `ProductCategory`, `ProductSearchQuery`, and
  `StructuredCatalogContext` Pydantic models.
- Add connector capability enums and `ProductCatalogConnector` protocol.
- Add connector installation config model and registry.
- Add WooCommerce connector with `mock` mode.
- Load and validate `data/mock-woocommerce/catalog.demo-car-parts.json`.
- Add search by name, SKU, category, tags, and fitment hints.
- Add WooCommerce connector `store_api` mode for public Store API
  product/category reads.
- Add `CatalogContextService`.
- Add agent graph node `load_catalog_context`.
- Persist compact product context snapshots used by agent runs.
- Add policy tests for kit price, stock claims, ambiguous matches, and
  compatibility wording.

### Milestone 3: Copilot Notes

- Add deterministic triage.
- Add LangGraph workflow.
- Add structured model decision.
- Write private notes to Chatwoot.
- Add audit records.

### Milestone 4: Limited Auto Replies

- Add outbound policy guard.
- Add low-risk public reply path.
- Add no-leak public message checks.
- Add human-active suppression.
- Add integration tests.

### Milestone 5: Additional Context Connectors

- Add second read-only connector only after WooCommerce proves the connector
  boundary, for example a documentation/FAQ or generic HTTP context connector.
- Add connector action proposal/guard/execution structure before implementing
  any external write capability.
- Keep context structured before adding vector retrieval.

### Milestone 6: Evals And Hardening

- Add LangSmith tracing.
- Add golden conversation evals.
- Add cost and latency tracking.
- Add production deployment docs.

## Open Questions

- Should the first public release target Chatwoot Cloud, self-hosted Chatwoot, or
  both?
- Should WootPilot write only private notes by default?
- Which model provider should be the default for examples?
- Should WooCommerce price mentions be disabled by default in limited auto mode?
- What fictional demo catalog should be committed for public examples?
- Should the project include a tiny admin UI, or stay API-only initially?
