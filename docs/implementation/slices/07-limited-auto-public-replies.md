# Slice 7: Limited Auto Public Replies

## Running Outcome

- WootPilot can send public replies only for low-risk cases and only after final
  pre-send safety checks.

## Implementation Scope

- Add public-message outbound action support.
- Add outbound policy guard for public messages.
- Add no-leak public message checks.
- Add public-dev Chatwoot configuration for writing replies through
  `https://chat.gmrahal.net/` in opt-in manual tests.
- Allow exact WooCommerce price mentions by default when `price.canMention=true`
  and the final public content passes policy.
- Add human-active suppression.
- Add final pre-send recheck for conversation id, replyability, bot mode, exact
  content policy, local human-active state, and fresh channel safety state.
- Add SQLite single-worker outbound execution.
- Document that production limited auto replies require Postgres.
- Keep limited auto disabled by default in all local and new-tenant
  configuration.
- Treat SQLite limited auto as local/demo only. Production public auto-send waits
  for Slice 9 Postgres readiness.

## Required Tests

- Low-risk public reply path queues and sends one public message.
- Public action queued while safe is blocked if a human becomes active before
  execution.
- Public action queued while safe is blocked if `wootpilot-paused` appears before
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
- Limited auto configuration defaults to disabled, and public sends fail closed
  when configuration is missing or inconsistent.
- SQLite profile refuses production public auto-send unless an explicit operator
  override is set for a local/demo environment.
- Explicit `wootpilot-auto-ok` can make a later customer turn eligible after
  human-active suppression, but it does not bypass deterministic policy.

## Manual Verification

- Start the local Chatwoot dev stack with `./scripts/chatwoot-dev-up`.
- Run a low-risk fixture through limited auto mode.
- Confirm one public-message outbound action is queued and sent.
- Repeat with a human-active fixture and confirm execution is blocked.
- Open the local Chatwoot conversation and confirm the sent message is public and
  contains no private reasoning, internal triage, or unsafe product claim.
- Run an opt-in public dev smoke test: send a customer message through the
  Meta-connected channel into `https://chat.gmrahal.net/`, confirm WootPilot
  writes one safe public reply through Chatwoot, then send a human reply and
  confirm the next public AI reply is suppressed.
