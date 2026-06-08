# Slice 1: Authenticated Webhook Intake

## Running Outcome

- WootPilot can receive a Chatwoot webhook, authenticate it, store the raw event,
  translate eligible customer messages, and ignore duplicate deliveries.

## Implementation Scope

- Add `HandleWebhookEvent`.
- Add Chatwoot HMAC webhook verification using `X-Chatwoot-Signature`,
  `X-Chatwoot-Timestamp`, and the Chatwoot-generated webhook secret.
- Keep a simple shared-secret fixture path only if it helps local tests before
  signed fixtures exist.
- Add replay-window rejection.
- Add `raw_events` persistence.
- Add minimal `NormalizedMessage` model and `conversation_messages`
  persistence.
- Translate Chatwoot customer message webhooks into `NormalizedMessage`.
- Deduplicate provider events with database uniqueness constraints.
- Preserve Chatwoot account, inbox, conversation, message, and contact ids.
- Keep this slice independent of LangGraph, model providers, connectors, and
  Chatwoot API writes.

## Required Tests

- ASGI route tests exercise webhook handling without a running Chatwoot server.
- Valid customer message webhook stores one raw event and one normalized message.
- Invalid authentication returns an unauthorized response and stores no event.
- Invalid Chatwoot HMAC signature, stale timestamp, and mismatched body are
  rejected.
- Stale or replayed webhook is rejected.
- Duplicate webhook delivery stores no duplicate normalized message.
- Chatwoot webhook DTO translates to `NormalizedMessage`.
- Translated messages preserve account, inbox, conversation, message, and contact
  identifiers.
- Raw event payload hash and ignored/processed status are stable for repeated
  fixtures.

## Manual Verification

- Start the local Chatwoot dev stack with `./scripts/chatwoot-dev-up`.
- Start the app locally.
- POST a fixture Chatwoot customer-message webhook with valid
  `X-Chatwoot-Signature` and `X-Chatwoot-Timestamp` headers.
- Confirm the database contains one raw event and one normalized message.
- POST the same fixture again and confirm no duplicate normalized message is
  created.
- For public-dev testing, copy `.env.public-dev.example` to `.env.local`, fill
  `WOOTPILOT_CHATWOOT_ACCOUNT_ID`, `WOOTPILOT_CHATWOOT_API_TOKEN`, and
  `WOOTPILOT_CHATWOOT_WEBHOOK_SECRET` from the Chatwoot webhook record, expose
  local WootPilot through a public tunnel URL, and configure
  `https://chat.gmrahal.net` to send webhooks to
  `{WOOTPILOT_PUBLIC_BASE_URL}{WOOTPILOT_WEBHOOK_PATH}`.
