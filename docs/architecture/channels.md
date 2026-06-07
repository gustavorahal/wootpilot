# Chatwoot Channel Model

WootPilot should integrate with Chatwoot as its primary support channel.
Chatwoot is not a connector because WootPilot is centered around Chatwoot; it is
the conversation platform and handoff surface.

Required Chatwoot inputs:

- Provider event id.
- Event timestamp.
- Account id.
- Inbox id.
- Conversation id.
- Message id.
- Contact id.
- Sender type.
- Message direction.
- Message visibility.
- Message content.
- Attachments metadata.
- Conversation status.
- Conversation replyability or lock state when available.

Chatwoot may send message events and conversation-level events. Version 1 only
needs to invoke the agent for eligible customer message events, but the channel
translator should leave room for a small domain envelope such as:

```text
ChannelEvent
  message_created
  conversation_updated
  assignment_changed
  unknown
```

`message_created` events can carry a `NormalizedMessage`. Conversation or
assignment events can update `ConversationState` without invoking the LLM. This
keeps the message model focused while still letting WootPilot react to human
activity and replyability changes.

Inbound webhooks must be authenticated before translation. Use Chatwoot
signature verification when available. If a Chatwoot deployment does not provide
a signature, require a configured shared-secret fallback such as a header token
or unguessable webhook URL secret. Do not run the agent for unauthenticated
production webhooks.

The Chatwoot channel adapter should use translators to convert raw Chatwoot
webhook DTOs into `NormalizedMessage` domain objects and outbound
`OutboundAction` domain objects into Chatwoot create-message DTOs. Translators
are the only channel code that should understand both Chatwoot payload shape and
WootPilot domain shape.

Required Chatwoot outputs:

- Public message.
- Private note.
- Optional labels.
- Optional custom attributes.
- Optional assignment or team handoff in later versions.

Outbound execution should depend on two small channel-facing ports:

```text
ChannelWriter
  Sends public messages, private notes, labels, and later assignment/handoff
  commands through the selected channel adapter.

ConversationSafetyReader
  Re-reads replyability, lock state, assignment/human activity signals, and the
  target conversation identity immediately before public sends.
```

`ConversationState` is WootPilot's local suppression state. It should be used
for fast workflow decisions, but public outbound execution should also consult
fresh channel state through `ConversationSafetyReader` when the channel supports
it.

The first version should support one Chatwoot account cleanly, but the data model
should include tenant/account boundaries from the start.

Every translated `NormalizedMessage` should preserve:

- `tenant_id`
- `provider`
- `provider_account_id`
- `provider_inbox_id`
- `provider_conversation_id`
- `provider_message_id`
- `provider_contact_id`

Do not rely on conversation id alone as a globally unique identifier. Chatwoot
Cloud, self-hosted Chatwoot, imports, tests, and future multi-account setups can
all make that assumption fragile.
