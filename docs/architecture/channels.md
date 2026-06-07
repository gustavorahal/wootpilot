# Chatwoot Channel Model

WootPilot should integrate with Chatwoot as its primary support channel.
Chatwoot is not a connector because WootPilot is centered around Chatwoot; it is
the conversation platform and handoff surface.

Required Chatwoot inputs:

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

Required Chatwoot outputs:

- Public message.
- Private note.
- Optional labels.
- Optional custom attributes.
- Optional assignment or team handoff in later versions.

The first version should support one Chatwoot account cleanly, but the data model
should include tenant/account boundaries from the start.
