# Milestones And Open Questions

## Milestones

Each milestone should leave the repository in a runnable and testable state.
Prefer thin vertical slices over broad implementation layers.

### Milestone 0: Runnable Skeleton

Running outcome:

- The service starts locally and exposes a health endpoint.
- The local SQLite database profile can be created and migrated.
- Tests and linting can run in CI and locally.

Implementation scope:

- Create Python package.
- Add FastAPI app.
- Add settings, including OpenRouter model-provider settings.
- Add health route.
- Add lint/test tooling.
- Add Dockerfile.
- Set Python 3.14 as the primary runtime and configure CI for supported Python
  versions.
- Add SQLite database profile for local development.
- Add Alembic baseline migration.
- Add minimal `Clock` and `IdGenerator` ports.

Completion tests:

- `GET /health` returns a successful response.
- Settings load from environment variables and test overrides.
- SQLite database initializes from an empty file.
- Alembic applies the baseline migration to an empty SQLite database.
- Unit test, lint, and type-check commands run in CI.

### Milestone 1: Authenticated Webhook Intake

Running outcome:

- WootPilot can receive a Chatwoot webhook, authenticate it, store the raw event,
  translate eligible customer messages, and ignore duplicate deliveries.

Implementation scope:

- Add `HandleWebhookEvent`.
- Add shared-secret webhook authentication.
- Add Chatwoot signature verification when available.
- Add replay-window rejection.
- Add `raw_events` persistence.
- Add minimal `NormalizedMessage` model and `conversation_messages`
  persistence.
- Translate Chatwoot customer message webhooks into `NormalizedMessage`.
- Deduplicate provider events with database uniqueness constraints.
- Preserve Chatwoot account, inbox, conversation, message, and contact ids.

Completion tests:

- Valid customer message webhook stores one raw event and one normalized message.
- Invalid authentication returns an unauthorized response and stores no event.
- Stale or replayed webhook is rejected.
- Duplicate webhook delivery stores no duplicate normalized message.
- Translated messages preserve account, inbox, conversation, message, and contact
  identifiers.

### Milestone 2: Event Filtering And Conversation State

Running outcome:

- WootPilot can distinguish customer messages from non-agentable events and keep
  local suppression state for human activity and replyability.

Implementation scope:

- Ignore private notes, outbound messages, bot echoes, and system events before
  invoking any model workflow.
- Translate conversation or assignment events into state updates.
- Add `ConversationState` model and persistence.
- Track human-active state, last human public message, last customer message,
  and replyability/lock signals when available.
- Add deterministic triage for deciding whether a message should invoke the
  workflow.

Completion tests:

- Private notes, outbound messages, bot echoes, and system events do not invoke a
  workflow.
- Conversation or assignment events update `ConversationState` without creating a
  model run.
- Human-active suppression windows are computed consistently.
- Triage assigns stable risk signal codes and invocation decisions.
- Webhook intake commits raw-event and dedupe state before any model or connector
  call.

### Milestone 3: Mock Product Context

Running outcome:

- Given a normalized customer message, WootPilot can load policy-aware product
  context from the local mock WooCommerce catalog and persist the exact context
  used by the run.

Implementation scope:

- Add `Money`, `PriceSnapshot`, `AvailabilitySnapshot`, `ProductSnapshot`,
  `ProductCategory`, `ProductSearchQuery`, and `StructuredCatalogContext`.
- Add connector capability enums and `ProductCatalogConnector` protocol using
  `product_catalog_read`.
- Add connector installation config model and registry for selecting configured
  connector adapters.
- Add WooCommerce connector `mock` mode.
- Load and validate `data/mock-woocommerce/catalog.demo-car-parts.json`.
- Add search by name, SKU, category, tags, and fitment hints.
- Add `CatalogContextService`.
- Persist compact context snapshots before invoking the graph.

Completion tests:

- Mock catalog fixture loads and validates.
- Product search works by name, SKU, category, tags, and fitment hints.
- Money and price snapshots reject floats and preserve integer minor units.
- Quote-required, hidden-price, zero-value, and availability cases produce
  policy-aware context.
- Catalog context persists snapshot ids that can be linked to an agent run.
- No raw WooCommerce payload crosses into service or graph inputs.

### Milestone 4: Shadow Workflow

Running outcome:

- WootPilot can run the support workflow in shadow mode from a stored customer
  message, produce an audited decision, and avoid all Chatwoot writes.

Implementation scope:

- Add minimal `AgentRun`, `PolicyDecision`, `AgentProposal`, `AuditRecord`, and
  workflow decision models.
- Add `RunSupportWorkflow`.
- Add pre-model policy gate.
- Add LangGraph workflow that receives prepared normalized message,
  conversation state, bot mode, policy inputs, and catalog context.
- Add an in-memory or fake `ModelProposalPort` for deterministic workflow tests.
- Persist agent run, policy decisions, context snapshot links, and audit records.
- Keep graph nodes free of connector reads, database writes, and Chatwoot writes.

Completion tests:

- Shadow workflow produces an agent run and audit record.
- Shadow workflow creates no outbound action and performs no Chatwoot write.
- Pre-model policy blocks ineligible messages before model proposal.
- Graph receives prepared conversation/catalog context.
- Graph does not perform connector reads, database writes, or Chatwoot writes.
- Audit records link raw event, normalized message, agent run, policy decision,
  and context snapshot ids.

### Milestone 5: OpenRouter Model Proposals

Running outcome:

- WootPilot can call OpenRouter through `ModelProposalPort` and convert a
  structured model response into a WootPilot `AgentProposal`.

Implementation scope:

- Add OpenRouter-backed `ModelProposalPort`.
- Use `langchain-openrouter` for LangChain/LangGraph chat model integration.
- Use direct HTTPX calls to OpenRouter only if the dedicated integration blocks a
  required MVP feature.
- Add structured model proposal schema.
- Capture model provider, model id, latency, token usage, and retryable/permanent
  error outcomes.
- Keep provider-specific schemas outside the domain layer.

Completion tests:

- OpenRouter adapter maps structured responses into `AgentProposal`.
- Usage metadata, model id, latency, and provider error details are captured.
- Retryable OpenRouter errors map to retryable WootPilot result types.
- Permanent OpenRouter errors map to permanent WootPilot result types.
- Provider-specific response shapes do not leak into domain models.
- Shadow workflow can run with the OpenRouter adapter mocked by `respx`.

### Milestone 6: Copilot Private Notes

Running outcome:

- WootPilot can create a Chatwoot private note suggestion for a customer message
  in copilot mode, using the same durable action path that later public replies
  will use.

Implementation scope:

- Add Chatwoot API client for private notes.
- Add `OutboundAction` model and SQLite-compatible outbox for private notes.
- Add `ChannelWriter`.
- Add `ExecuteOutboundAction` for private-note actions.
- Add copilot branching that queues private-note actions after policy checks.
- Keep copilot review inside Chatwoot private notes.
- Do not add LangGraph interrupt approval/resume flows for the MVP.

Completion tests:

- Webhook to copilot workflow queues one private-note outbound action.
- Outbound executor sends the private note through Chatwoot and records the
  provider message id.
- Duplicate webhook delivery creates at most one private note.
- Chatwoot retryable failure schedules a retry without duplicating content.
- Chatwoot permanent failure records a permanent failure status.
- Private-note content redacts internal-only fields and raw payloads.

### Milestone 7: Limited Auto Public Replies

Running outcome:

- WootPilot can send public replies only for low-risk cases and only after final
  pre-send safety checks.

Implementation scope:

- Add public-message outbound action support.
- Add outbound policy guard for public messages.
- Add no-leak public message checks.
- Add human-active suppression.
- Add final pre-send recheck for conversation id, replyability, bot mode, exact
  content policy, local human-active state, and fresh channel safety state.
- Add SQLite single-worker outbound execution.
- Document that production limited auto replies require Postgres.

Completion tests:

- Low-risk public reply path queues and sends one public message.
- Public action queued while safe is blocked if a human becomes active before
  execution.
- Public action queued while safe is blocked if the conversation is no longer
  replyable before execution.
- Public action queued while safe is blocked if fresh channel safety state
  disagrees with local conversation state.
- Public-message leakage guard blocks internal reasoning and unsafe claims.
- Duplicate or concurrent webhook deliveries do not create duplicate public
  messages.

### Milestone 8: WooCommerce Store API

Running outcome:

- WootPilot can use either the mock catalog or the public WooCommerce Store API
  for read-only product context.

Implementation scope:

- Add WooCommerce connector `store_api` mode for public Store API product and
  category reads.
- Map Store API product/category responses into domain snapshots.
- Keep authenticated WooCommerce REST API support out of the MVP.
- Keep context structured before adding vector retrieval.

Completion tests:

- WooCommerce Store API product and category mapping works with recorded
  fixtures.
- `mock` and `store_api` modes satisfy the same `ProductCatalogConnector`
  contract.
- Store API failures produce controlled context-loading failures.
- Product lookup persists the exact policy-aware context used by the agent run.
- Price and availability mention policies behave the same for mock and Store API
  modes.

### Milestone 9: Production Readiness

Running outcome:

- WootPilot has the minimum deployment, evaluation, and operational checks needed
  for an MVP release.

Implementation scope:

- Add Postgres database profile.
- Add Postgres migrations in CI.
- Add Postgres row-level queue locking for outbound action workers.
- Add LangGraph checkpointer factory for memory, SQLite, and Postgres profiles.
- Add golden conversation evals.
- Add cost and latency tracking.
- Add structured log review for failed, blocked, and high-latency workflows.
- Add production deployment docs.
- Revisit optional observability integrations such as LangSmith or OpenTelemetry
  after the MVP audit/logging baseline is stable.

Completion tests:

- Database migrations apply cleanly to empty SQLite and Postgres databases.
- SQLite profile enables WAL mode, foreign keys, and busy timeout.
- Postgres profile uses row-level queue locking for outbound action workers.
- LangGraph memory, SQLite, and Postgres checkpointer factories select the
  expected backend.
- Golden conversations cover low-risk FAQ, catalog lookup, kit escalation,
  account-sensitive requests, prompt injection, hidden prices, quote-required
  prices, and zero-value kit placeholders.
- Production deployment docs include required environment variables and the
  Postgres requirement for production public auto-send.

## Open Questions

- Should the first public release target Chatwoot Cloud, self-hosted Chatwoot, or
  both?
- Should WootPilot write only private notes by default?
- Should WooCommerce price mentions be disabled by default in limited auto mode?
- What fictional demo catalog should be committed for public examples?
- Should the project include a tiny admin UI, or stay API-only initially?
