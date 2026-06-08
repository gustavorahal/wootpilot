# Public Dev Laptop Harness

This profile makes the public-dev laptop loop repeatable while WootPilot is
implemented locally.

The live channel path is:

```text
customer on WhatsApp
  -> Meta
  -> https://chat.gmrahal.net/
  -> Chatwoot account webhook
  -> public tunnel to this laptop
  -> local WootPilot
  -> Chatwoot API write
  -> Chatwoot delivers through the original channel
```

WootPilot does not talk directly to Meta in this loop. Chatwoot owns the
WhatsApp Cloud integration, inbox, contact identity, conversation thread, human
agent UI, and final delivery.

## Setup

Copy the public-dev template:

```sh
cp .env.public-dev.example .env.local
```

Fill at least:

```text
WOOTPILOT_PUBLIC_BASE_URL=https://wootpilot-local-dev.gmrahal.net
WOOTPILOT_CHATWOOT_ACCOUNT_ID=<chatwoot-account-id>
WOOTPILOT_CHATWOOT_API_TOKEN=<chatwoot-user-api-token>
```

Keep the first live loop conservative:

```text
WOOTPILOT_BOT_MODE=shadow
```

Start WootPilot locally on the implementation's configured port, for example:

```sh
uvicorn wootpilot.api.main:app --reload --host 0.0.0.0 --port 8000
```

Expose that port through a public tunnel and set:

```text
WOOTPILOT_PUBLIC_BASE_URL=https://wootpilot-local-dev.gmrahal.net
```

The Cloudflare tunnel for this profile is:

```text
tunnel name: wootpilot-local-dev
hostname:    wootpilot-local-dev.gmrahal.net
service:     http://localhost:8000
```

Start the tunnel connector:

```sh
./scripts/public-dev-tunnel-run
```

## Sync The Chatwoot Webhook

Create or update the managed Chatwoot webhook:

```sh
./scripts/public-dev-webhook-sync
```

The script uses the Chatwoot account API to create or update a webhook named
`WootPilot laptop tunnel`, sets the subscriptions from
`webhook-subscriptions.json`, and saves the Chatwoot-generated webhook secret
back into `.env.local` as `WOOTPILOT_CHATWOOT_WEBHOOK_SECRET`.

It does not print API tokens or webhook secrets.

Show current account webhooks:

```sh
./scripts/public-dev-webhook-show
```

Run readiness checks:

```sh
./scripts/public-dev-doctor
```

## Managed Webhook

Default webhook URL:

```text
{WOOTPILOT_PUBLIC_BASE_URL}{WOOTPILOT_WEBHOOK_PATH}
```

Default subscriptions:

```text
message_created
message_updated
conversation_updated
conversation_status_changed
```

Chatwoot signs requests with:

```text
X-Chatwoot-Timestamp
X-Chatwoot-Signature
X-Chatwoot-Delivery
```

WootPilot must verify the signature against the raw request body before parsing
or translating the webhook payload.

## Verification Flow

1. Start WootPilot locally.
2. Start the tunnel.
3. Set `WOOTPILOT_PUBLIC_BASE_URL` in `.env.local`.
4. Run `./scripts/public-dev-webhook-sync`.
5. Run `./scripts/public-dev-doctor`.
6. Send a WhatsApp message to the Meta-connected test number.
7. Confirm the message appears in `https://chat.gmrahal.net/`.
8. Confirm WootPilot receives a signed `message_created` webhook.
9. In shadow mode, confirm no Chatwoot write happens.
10. In copilot mode, confirm WootPilot writes one private note.
11. In limited auto mode, confirm only a low-risk fixture sends a public reply.
12. Send a human public reply from Chatwoot.
13. Confirm WootPilot suppresses the next public AI reply until the suppression
    window expires or explicit resume policy applies.

## Failure Checks

- If Chatwoot does not reach WootPilot, check the tunnel URL and
  `WOOTPILOT_PUBLIC_BASE_URL`.
- If WootPilot rejects the webhook, check
  `WOOTPILOT_CHATWOOT_WEBHOOK_SECRET` and make sure signature verification uses
  the raw request body.
- If WootPilot cannot write back, check `WOOTPILOT_CHATWOOT_BASE_URL`,
  `WOOTPILOT_CHATWOOT_ACCOUNT_ID`, and `WOOTPILOT_CHATWOOT_API_TOKEN`.
- If duplicate replies appear, check webhook deduplication and outbound action
  idempotency before enabling public replies again.
