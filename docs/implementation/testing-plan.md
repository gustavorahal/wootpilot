# Testing Plan

## Unit Tests

- Chatwoot webhook normalization.
- Signature verification.
- Deduplication.
- Intent classification.
- Mock WooCommerce product search.
- WooCommerce Store API product mapping.
- Connector registry capability resolution.
- Connector installation effective capability calculation.
- Catalog context building.
- Policy gates.
- Public-message leakage guard.
- Conversation id mismatch guard.
- Human-active suppression.
- Kit price `0.00` handling.
- Availability claim gating.

## Integration Tests

- Webhook to private note.
- Webhook to public reply in limited auto mode.
- Shadow mode produces no Chatwoot writes.
- Bot echo does not loop.
- Chatwoot API failure creates failed outbound action.
- Product lookup conversation against the mock WooCommerce catalog.
- Product lookup persists context snapshots used by the agent run.
- Ambiguous product match produces a clarifying question or private note.

## Evaluation Tests

- Golden conversations for low-risk FAQ.
- Golden conversations for WooCommerce catalog lookup.
- Golden conversations for kit quote/composition escalation.
- Golden conversations for billing/account-sensitive requests.
- Golden conversations for technical support escalation.
- Prompt injection attempts.
- Requests for private/internal information.
