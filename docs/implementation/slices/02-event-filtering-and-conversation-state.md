# Slice 2: Event Filtering And Conversation State

## Running Outcome

- WootPilot can distinguish customer messages from non-agentable events and keep
  local suppression state for human activity and replyability.

## Implementation Scope

- Ignore private notes, outbound messages, bot echoes, and system events before
  invoking any model workflow.
- Translate conversation or assignment events into state updates.
- Add `ConversationState` model and persistence.
- Track human-active state, last human public message, last customer message,
  and replyability/lock signals when available.
- Track explicit WootPilot pause/resume signals from Chatwoot labels or custom
  attributes when present.
- Add deterministic triage for deciding whether a message should invoke the
  workflow.
- Represent workflow invocation as a use-case result or port call; do not add
  LangGraph or model-provider dependencies in this slice.

## Required Tests

- Private notes, outbound messages, bot echoes, and system events do not invoke a
  workflow.
- Chatwoot conversation or assignment events translate to non-LLM `ChannelEvent`
  handling.
- Conversation or assignment events update `ConversationState` without creating a
  model run.
- Conversation state human-active suppression windows are computed consistently.
- Intent classification assigns stable triage decisions.
- Triage assigns stable risk signal codes.
- Webhook intake commits raw-event and dedupe state before any model or connector
  call.
- Event filtering fixtures cover customer public inbound messages, private
  notes, human public replies, bot echoes, system events, assignment changes,
  and conversation status/replyability changes.
- Pause/resume fixtures cover `wootpilot-paused`, `wootpilot-auto-ok`, and
  human-active suppression windows.

## Manual Verification

- POST fixture private-note, outbound-message, and assignment-change webhooks.
- Confirm ignored message events do not create model workflow records.
- Confirm assignment or conversation events update local conversation state.
- Through the public-dev laptop harness, send a customer message through the
  Meta-connected test channel, then send a human public reply from
  `https://chat.gmrahal.net/` and confirm the next webhook updates human-active
  state.
