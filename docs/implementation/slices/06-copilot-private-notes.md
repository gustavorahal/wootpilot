# Slice 6: Copilot Private Notes

## Running Outcome

- WootPilot can create a Chatwoot private note suggestion for a customer message
  in copilot mode, using the same durable action path that later public replies
  will use.

## Implementation Scope

- Add Chatwoot API client for private notes.
- Add `OutboundAction` model and SQLite-compatible outbox for private notes.
- Add `ChannelWriter`.
- Add `ExecuteOutboundAction` for private-note actions.
- Add copilot branching that queues private-note actions after policy checks.
- Keep copilot review inside Chatwoot private notes.
- Do not add LangGraph interrupt approval/resume flows for the MVP.

## Required Tests

- Webhook to copilot workflow queues one private-note outbound action.
- Outbound executor sends the private note through Chatwoot and records the
  provider message id.
- Outbound action idempotency key construction is stable.
- Outbound action source message id and provider-created message id stay
  separate.
- Duplicate webhook delivery creates at most one private note.
- Chatwoot API request/response mapping works with `respx`.
- Chatwoot retryable failure schedules a retry without duplicating content.
- Chatwoot permanent failure records a permanent failure status.
- Outbound action executor state transitions cover queued, executing, sent,
  retryable failure, permanent failure, and blocked-by-policy outcomes.
- Private-note content redacts internal-only fields and raw payloads.

## Manual Verification

- Run a fixture customer message through copilot mode.
- Confirm one queued private-note outbound action.
- Run the outbound executor.
- Confirm the Chatwoot private note request is sent and the outbound action is
  marked sent.
