# Public Dev Laptop Loop

Use this runbook when WootPilot runs on this laptop and the public dev Chatwoot
server receives real customer messages from a Meta-connected channel such as
WhatsApp Cloud.

## Goal

Prove the MVP back-and-forth loop:

```text
customer sends WhatsApp message
  -> Meta delivers to https://chat.gmrahal.net/
  -> Chatwoot creates/updates a conversation
  -> Chatwoot sends a signed webhook to the laptop tunnel
  -> WootPilot records and decides the action
  -> WootPilot writes a private note or safe public reply to Chatwoot
  -> Chatwoot delivers the public reply through the original channel
  -> a human replies in Chatwoot
  -> WootPilot observes the human reply and suppresses public automation
```

WootPilot does not talk directly to Meta in this loop.

## One-Time Local Setup

Copy the public-dev template:

```sh
cp .env.public-dev.example .env.local
```

Fill these values in `.env.local`:

```text
WOOTPILOT_PUBLIC_BASE_URL=https://<your-tunnel-url>
WOOTPILOT_CHATWOOT_ACCOUNT_ID=<chatwoot-account-id>
WOOTPILOT_CHATWOOT_API_TOKEN=<chatwoot-user-api-token>
WOOTPILOT_CHATWOOT_WEBHOOK_SECRET=<chatwoot-generated-webhook-secret>
WOOTPILOT_OPENROUTER_API_KEY=<optional-until-live-model-test>
```

Keep the first live loop conservative:

```text
WOOTPILOT_BOT_MODE=shadow
```

Move to `copilot` only after webhook intake is proven. Move to `limited_auto`
only after public reply guards are implemented and manually verified.

## Start WootPilot And Tunnel

Start WootPilot locally on the implementation's configured port, for example:

```sh
uvicorn wootpilot.api.main:app --reload --host 0.0.0.0 --port 8000
```

Expose the same local port through a public tunnel. The tunnel URL becomes:

```text
WOOTPILOT_PUBLIC_BASE_URL=https://<your-tunnel-url>
```

Chatwoot must call:

```text
https://<your-tunnel-url>/webhooks/chatwoot
```

## Configure Chatwoot Webhook

Create or update a Chatwoot account webhook in `https://chat.gmrahal.net/`.

Webhook URL:

```text
{WOOTPILOT_PUBLIC_BASE_URL}{WOOTPILOT_WEBHOOK_PATH}
```

Subscriptions:

```text
message_created
message_updated
conversation_updated
conversation_status_changed
```

Chatwoot generates a webhook secret and sends signed requests using:

```text
X-Chatwoot-Timestamp
X-Chatwoot-Signature
X-Chatwoot-Delivery
```

Copy the generated secret to:

```text
WOOTPILOT_CHATWOOT_WEBHOOK_SECRET
```

## Optional API Setup

The Chatwoot account API accepts the user API token in the `api_access_token`
header. This can be useful when the tunnel URL changes often.

Create a webhook:

```sh
curl -sS \
  -X POST "https://chat.gmrahal.net/api/v1/accounts/$WOOTPILOT_CHATWOOT_ACCOUNT_ID/webhooks" \
  -H "api_access_token: $WOOTPILOT_CHATWOOT_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "webhook": {
      "name": "WootPilot laptop tunnel",
      "url": "'"$WOOTPILOT_PUBLIC_BASE_URL$WOOTPILOT_WEBHOOK_PATH"'",
      "subscriptions": [
        "message_created",
        "message_updated",
        "conversation_updated",
        "conversation_status_changed"
      ]
    }
  }'
```

The response includes `secret`. Copy it into `.env.local` as
`WOOTPILOT_CHATWOOT_WEBHOOK_SECRET`.

If the tunnel URL changes, update the webhook URL through the Chatwoot UI or API.

## Verification Checklist

1. Start WootPilot locally.
2. Start the tunnel.
3. Confirm `.env.local` has the tunnel URL and Chatwoot webhook secret.
4. Send a WhatsApp message to the Meta-connected test number.
5. Confirm the message appears in `https://chat.gmrahal.net/`.
6. Confirm WootPilot receives a signed `message_created` webhook.
7. Confirm WootPilot stores the raw event and normalized message.
8. In shadow mode, confirm no Chatwoot write happens.
9. In copilot mode, confirm WootPilot writes one private note.
10. In limited auto mode, confirm only a low-risk fixture sends a public reply.
11. Send a human public reply from Chatwoot.
12. Confirm WootPilot observes the human reply and suppresses the next public AI
    reply until the suppression window expires or explicit resume policy applies.

## Failure Checks

- If Chatwoot does not reach WootPilot, check the tunnel URL and
  `WOOTPILOT_PUBLIC_BASE_URL`.
- If WootPilot rejects the webhook, check `WOOTPILOT_CHATWOOT_WEBHOOK_SECRET`
  and ensure signature verification uses the raw request body.
- If WootPilot cannot write back, check `WOOTPILOT_CHATWOOT_BASE_URL`,
  `WOOTPILOT_CHATWOOT_ACCOUNT_ID`, and `WOOTPILOT_CHATWOOT_API_TOKEN`.
- If duplicate replies appear, check webhook deduplication and outbound action
  idempotency before enabling public replies again.
