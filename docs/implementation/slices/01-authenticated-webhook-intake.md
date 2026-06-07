# Slice 1: Authenticated Webhook Intake

## Running Outcome

- WootPilot can receive a Chatwoot webhook, authenticate it, store the raw event,
  translate eligible customer messages, and ignore duplicate deliveries.

## Implementation Scope

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

## Required Tests

- Valid customer message webhook stores one raw event and one normalized message.
- Invalid authentication returns an unauthorized response and stores no event.
- Stale or replayed webhook is rejected.
- Duplicate webhook delivery stores no duplicate normalized message.
- Chatwoot webhook DTO translates to `NormalizedMessage`.
- Translated messages preserve account, inbox, conversation, message, and contact
  identifiers.

## Manual Verification

- Start the local Chatwoot dev stack with `./scripts/chatwoot-dev-up`.
- Start the app locally.
- POST a fixture Chatwoot customer-message webhook with a valid shared secret.
- Confirm the database contains one raw event and one normalized message.
- POST the same fixture again and confirm no duplicate normalized message is
  created.
