# Chatwoot Channel Model

Chatwoot is WootPilot's primary support channel, not a connector. Chatwoot owns
the customer conversation, agent UI, Meta/WhatsApp channel setup, contact
identity, and message delivery. WootPilot receives Chatwoot webhooks and writes
back through Chatwoot APIs.

The public-dev Chatwoot server used for live testing is:

```text
https://chat.gmrahal.net/
```

## Inbound Translation

The Chatwoot adapter in
[`src/wootpilot/integrations/chatwoot.py`](../../src/wootpilot/integrations/chatwoot.py)
translates raw webhook payloads into domain objects:

```text
message_created -> NormalizedMessage
conversation_created / conversation_updated / conversation_status_changed -> ChannelEvent
```

`HandleWebhookEvent` verifies Chatwoot signatures before translation. Invalid
signatures are rejected before persistence or model work.

Translated messages preserve provider identity:

- tenant/account id;
- inbox/channel id;
- provider conversation id;
- provider message id;
- provider contact id;
- direction;
- visibility;
- author type;
- attachments metadata;
- conversation status, replyability, labels, attributes, and assignment when
  present.

Only public inbound customer messages invoke WootPilot. Private notes, outbound
messages, bot echoes, human-agent public replies, and non-message events are
stored or reflected in conversation state without invoking the model.

## Conversation State

Conversation events and message metadata update `ConversationState`. WootPilot
tracks:

- replyability;
- open/resolved status;
- `wootpilot-paused`;
- assigned agent/team ids;
- last customer message time;
- last human public message time;
- human-active suppression deadline.

The `wootpilot-paused` label blocks automation. A human public reply suppresses
future `public_reply` automation for the configured TTL. Assignment also blocks
`public_reply`.

## Outbound Writes

WootPilot writes to Chatwoot through `ChatwootClient`:

- private notes;
- public messages;
- optional status updates after public replies;
- optional `wootpilot-needs-human` label merging after private review notes.

Public replies are re-checked immediately before sending by reading fresh
Chatwoot conversation safety state. This final check protects against assignment,
resolution, pause labels, replyability changes, and conversation-id mismatches
that happen after a workflow queued an action.

## Local And Public-Dev Flow

Live public-dev traffic follows this path:

```text
Meta-connected customer message
  -> Chatwoot conversation at https://chat.gmrahal.net/
  -> signed Chatwoot webhook to WootPilot
  -> WootPilot workflow and outbound queue
  -> Chatwoot API write
  -> customer-visible reply or private note in Chatwoot
```

Conversation ids are not treated as globally unique. WootPilot scopes state and
audit data by tenant/account, channel/inbox, and conversation identifiers.
