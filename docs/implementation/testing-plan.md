# Testing Plan

## Unit Tests

- Chatwoot webhook DTO to `NormalizedMessage` translation.
- Chatwoot signature verification.
- Shared-secret webhook fallback verification.
- Replay-window rejection.
- Deduplication.
- Tenant id propagation across normalized messages, context snapshots, policy
  decisions, and outbound actions.
- Normalized message identity preservation for account, inbox, conversation,
  message, and contact ids.
- Intent classification.
- Triage result risk-signal assignment.
- Risk signal code stability.
- Money model validation, currency normalization, same-currency arithmetic, and
  zero-value handling.
- Price snapshot validation for quote-required semantics, hidden prices, display
  text, and mention permissions.
- Availability snapshot validation for hidden quantities, mention permissions,
  and uncertainty reasons.
- Product snapshot composition with price, availability, fitment hints, and risk
  signals.
- Mock WooCommerce product search.
- WooCommerce Store API product mapping.
- Connector registry capability resolution to configured adapters.
- Connector installation effective capability calculation.
- Catalog context building.
- Policy gates.
- Policy decision rule ids and outcomes.
- Context snapshot redaction and snapshot id propagation.
- Outbound action idempotency key construction and status transitions.
- Conversation state human-active suppression windows.
- Audit record correlation ids and redaction.
- Public-message leakage guard.
- Conversation id mismatch guard.
- Human-active suppression.
- Kit price `0.00` handling.
- Availability claim gating.
- Agent proposal schema validation.
- System status assignment after policy and action execution.
- Redaction of secrets, contact data, raw payloads, and sensitive pricing text.

## Integration Tests

- Webhook to private note.
- Webhook to public reply in limited auto mode.
- Shadow mode produces no Chatwoot writes.
- Bot echo does not loop.
- Chatwoot API failure creates failed outbound action.
- Chatwoot API retryable failure schedules a retry without duplicating content.
- Duplicate webhook delivery creates one raw event decision and at most one
  outbound action.
- Concurrent duplicate webhook deliveries do not create duplicate public
  messages.
- Public action queued while safe is blocked if a human becomes active before
  execution.
- Public action queued while safe is blocked if the conversation is no longer
  replyable before execution.
- Product lookup conversation against the mock WooCommerce catalog.
- Product lookup persists context snapshots used by the agent run.
- Ambiguous product match produces a clarifying question or private note.
- Price snapshots persist the exact policy-aware price context used by the agent
  run.
- Database migrations apply cleanly to an empty database and preserve required
  uniqueness constraints on both SQLite and Postgres.
- SQLite profile enables WAL mode, foreign keys, and busy timeout.
- Postgres profile uses row-level queue locking for outbound action workers.
- LangGraph memory, SQLite, and Postgres checkpointer factories select the
  expected backend.

## Evaluation Tests

- Golden conversations for low-risk FAQ.
- Golden conversations for WooCommerce catalog lookup.
- Golden conversations for kit quote/composition escalation.
- Golden conversations for billing/account-sensitive requests.
- Golden conversations for technical support escalation.
- Prompt injection attempts.
- Requests for private/internal information.
- Golden conversations where product price is mentionable.
- Golden conversations where product price is hidden or quote-required.
- Golden conversations where zero-value kit placeholders must not be described
  as free.

## Contract Tests

- Chatwoot channel client request/response mapping with respx.
- WooCommerce Store API product and category mapping with recorded fixtures.
- `ProductCatalogConnector` protocol behavior shared by `mock` and `store_api`.
- Outbound action executor state transitions for queued, executing, sent,
  retryable failure, permanent failure, and blocked-by-policy outcomes.
