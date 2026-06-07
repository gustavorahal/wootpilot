# Slice 7: Limited Auto Public Replies

## Running Outcome

- WootPilot can send public replies only for low-risk cases and only after final
  pre-send safety checks.

## Implementation Scope

- Add public-message outbound action support.
- Add outbound policy guard for public messages.
- Add no-leak public message checks.
- Allow exact WooCommerce price mentions by default when `price.canMention=true`
  and the final public content passes policy.
- Add human-active suppression.
- Add final pre-send recheck for conversation id, replyability, bot mode, exact
  content policy, local human-active state, and fresh channel safety state.
- Add SQLite single-worker outbound execution.
- Document that production limited auto replies require Postgres.

## Required Tests

- Low-risk public reply path queues and sends one public message.
- Public action queued while safe is blocked if a human becomes active before
  execution.
- Public action queued while safe is blocked if the conversation is no longer
  replyable before execution.
- Public action queued while safe is blocked if fresh channel safety state
  disagrees with local conversation state.
- Conversation id mismatch guard blocks public execution.
- Public-message leakage guard blocks internal reasoning and unsafe claims.
- Public replies may include exact product prices by default when the selected
  product has a fresh mentionable price snapshot.
- Public replies do not present quote-required, hidden, unavailable, stale, or
  ambiguous prices as exact prices.
- Human-active suppression blocks public sends.
- System status is assigned after policy and action execution.
- Duplicate or concurrent webhook deliveries do not create duplicate public
  messages.

## Manual Verification

- Start the local Chatwoot dev stack with `./scripts/chatwoot-dev-up`.
- Run a low-risk fixture through limited auto mode.
- Confirm one public-message outbound action is queued and sent.
- Repeat with a human-active fixture and confirm execution is blocked.
