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
