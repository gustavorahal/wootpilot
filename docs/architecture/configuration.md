# Configuration

WootPilot reads runtime configuration from environment variables using
`pydantic-settings`. The implementation entry point is
[`src/wootpilot/settings.py`](../../src/wootpilot/settings.py). In abbreviated
form, the settings boundary looks like this:

```python
from functools import cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        extra="ignore",
    )


@cache
def get_settings() -> Settings:
    return Settings()
```

Application code receives `Settings` through FastAPI dependencies, service
constructors, or test fixtures. Domain models do not read environment variables
directly.

## Where Values Live

Committed templates:

```text
.env.example
.env.public-dev.example
```

Local developer secrets:

```text
.env.local
```

Server-side live-dev secrets, if WootPilot is deployed beside Chatwoot on the
GMR platform host:

```text
/srv/apps/env/clients/wootpilot.env
```

The sibling `gmr-clients-apps/infra` repository already uses this convention
for deployed client services. Real server env files are not committed; examples
belong in infra env-example directories.

## Core Variables

```text
ENV
LOG_LEVEL
WORKFLOW_TRACE
LANGSMITH_TRACING
LANGSMITH_API_KEY
LANGSMITH_PROJECT
LANGSMITH_ENDPOINT
PUBLIC_BASE_URL
WEBHOOK_PATH

DB_URL
CHECKPOINTER

AUTOMATION_MODE
RESPONSE_LOCALE
HUMAN_OPERATOR_ACTIVE_TTL_SECONDS
OUTBOUND_RETRY_DELAY_SECONDS
OUTBOUND_MAX_ATTEMPTS
```

`PUBLIC_BASE_URL` is the URL Chatwoot uses to call WootPilot webhooks.
It is not necessarily the same as the Chatwoot URL.
`WORKFLOW_TRACE=true` prints a local-only developer LangGraph node
trace in `local` and `public_dev` environments, including customer messages and
model-proposed text. It is ignored in `test` and `production`, where structured
JSON logs and audit records remain the observability path.
`LANGSMITH_TRACING=true` enables hosted LangSmith tracing for LangChain and
LangGraph runs. It requires `LANGSMITH_API_KEY`; `LANGSMITH_PROJECT` selects the
destination project, and `LANGSMITH_ENDPOINT` is only needed for self-hosted
LangSmith. Hosted traces may include customer messages, catalog context,
prompts, model outputs, and provider metadata, so keep this disabled unless the
deployment is allowed to send that data to LangSmith.
`RESPONSE_LOCALE` controls the language profile used for model prompts and
deterministic fake proposals. The default is `pt-BR`, because the first live
customer target is Brazilian Portuguese. Keep this explicit in deployments so
reviewers can see that Portuguese behavior is a product choice, not an
accidental prompt side effect.
`HUMAN_OPERATOR_ACTIVE_TTL_SECONDS` controls how long WootPilot treats
a conversation as human-active after a human sends a public Chatwoot reply. The
default is `900` seconds, or 15 minutes. During this window, `public_reply`
automation is blocked; `observe` and `assist` can still run because they do not
send customer-visible messages.
Retryable outbound channel failures are retried after
`OUTBOUND_RETRY_DELAY_SECONDS` until `OUTBOUND_MAX_ATTEMPTS`
is reached, then the action is marked as a permanent failure.

## Chatwoot Variables

```text
CHATWOOT_BASE_URL
CHATWOOT_PUBLIC_URL
CHATWOOT_ACCOUNT_ID
CHATWOOT_API_TOKEN
CHATWOOT_WEBHOOK_SECRET
CHATWOOT_WEBHOOK_SIGNATURE_MODE
CHATWOOT_WEBHOOK_SIGNATURE_HEADER
CHATWOOT_WEBHOOK_TIMESTAMP_HEADER
CHATWOOT_WEBHOOK_DELIVERY_HEADER
CHATWOOT_UPDATE_STATUS_AFTER_PUBLIC_REPLY
CHATWOOT_PUBLIC_REPLY_STATUS
CHATWOOT_MARK_NEEDS_HUMAN_ON_PRIVATE_REVIEW
CHATWOOT_NEEDS_HUMAN_LABEL
```

Use `CHATWOOT_BASE_URL` for API calls from WootPilot to Chatwoot.
Use `CHATWOOT_PUBLIC_URL` only for links, logs, and manual
verification instructions.
When `CHATWOOT_UPDATE_STATUS_AFTER_PUBLIC_REPLY=true`, WootPilot sets
the conversation to `CHATWOOT_PUBLIC_REPLY_STATUS` after a successful
public reply. The default target is `pending`, and the feature is disabled by
default to keep live test traffic conservative.
When `CHATWOOT_MARK_NEEDS_HUMAN_ON_PRIVATE_REVIEW=true`, WootPilot
adds `CHATWOOT_NEEDS_HUMAN_LABEL` after a private note produced by a
human-review path. The label writer first reads existing labels and merges the
WootPilot label because Chatwoot's labels endpoint replaces the full label set.

For local disposable Chatwoot:

```text
CHATWOOT_BASE_URL=http://localhost:3000
CHATWOOT_PUBLIC_URL=http://localhost:3000
```

For local WootPilot talking to the public dev Chatwoot:

```text
CHATWOOT_BASE_URL=https://chat.gmrahal.net
CHATWOOT_PUBLIC_URL=https://chat.gmrahal.net
```

For WootPilot deployed as a container on the same GMR Docker network as
Chatwoot:

```text
CHATWOOT_BASE_URL=http://chatwoot-web:3000
CHATWOOT_PUBLIC_URL=https://chat.gmrahal.net
```

This internal URL follows the existing GMR platform Compose setup, where Caddy
serves `https://chat.gmrahal.net` publicly and the `chatwoot-web` container is
available on the internal Docker network.

## Webhook Configuration

Chatwoot calls:

```text
{PUBLIC_BASE_URL}{WEBHOOK_PATH}
```

For local WootPilot, `PUBLIC_BASE_URL` must be a tunnel or other
public URL reachable by `https://chat.gmrahal.net`.

For server-side WootPilot, use a real public route such as:

```text
https://wootpilot.gmrahal.net/webhooks/chatwoot
```

Do not put the Chatwoot API token in the webhook URL. Chatwoot account webhooks
already have a generated secret and send signed requests when the secret is
present.

For local and public-dev testing, configure a Chatwoot webhook for these event
families when the Chatwoot UI/API supports them:

```text
message_created
conversation_updated
conversation_status_changed
message_updated
```

`message_created` drives customer turns, human public reply detection, private
note filtering, outbound/bot echo filtering, and duplicate delivery handling.
`message_updated` can capture later delivery/status changes. Conversation
updates, including status or assignment-related changes when Chatwoot emits them
through `conversation_updated`, update local suppression, replyability, and
pause/resume state without invoking the model.

The native Chatwoot webhook signature is verified as:

```text
signature header: X-Chatwoot-Signature
timestamp header: X-Chatwoot-Timestamp
delivery header:  X-Chatwoot-Delivery
signature body:   "{timestamp}.{raw_json_body}"
algorithm:        HMAC-SHA256 with CHATWOOT_WEBHOOK_SECRET
header format:    sha256={hex_digest}
```

The webhook secret is generated by Chatwoot when the account webhook is created.
Copy that value into `.env.local` as `CHATWOOT_WEBHOOK_SECRET` for
laptop tunnel testing. Use the same value in `/srv/apps/env/clients/wootpilot.env`
if WootPilot is later deployed server-side.

## Public Dev Profiles

### Local WootPilot, Public Chatwoot

Use this when developing WootPilot on your machine while testing against the
live Chatwoot server:

```text
CHATWOOT_BASE_URL=https://chat.gmrahal.net
CHATWOOT_PUBLIC_URL=https://chat.gmrahal.net
PUBLIC_BASE_URL=https://wootpilot-local-dev.gmrahal.net
```

Chatwoot must be configured to send webhooks to
`{PUBLIC_BASE_URL}{WEBHOOK_PATH}`.

This public base URL is backed by the `wootpilot-local-dev` Cloudflare tunnel
and managed through the public-dev laptop harness in
`infra/public-dev-laptop`.

### Server-Side WootPilot, Public Chatwoot

Use this when WootPilot is deployed as a container on the same GMR platform host
as Chatwoot:

```text
CHATWOOT_BASE_URL=http://chatwoot-web:3000
CHATWOOT_PUBLIC_URL=https://chat.gmrahal.net
PUBLIC_BASE_URL=https://wootpilot.gmrahal.net
```

In this profile, WootPilot API calls stay on the Docker internal network while
Chatwoot webhooks and human browser access use public HTTPS.

## Model Variables

```text
MODEL_PROVIDER=openrouter
OPENROUTER_API_KEY
OPENROUTER_MODEL
```

Default CI does not require `OPENROUTER_API_KEY`. Provider calls are mocked
unless an opt-in live smoke test is being run.

## Catalog Variables

```text
CATALOG_CONNECTOR_MODE=mock
MOCK_CATALOG_PATH=./data/mock-woocommerce/catalog.demo-car-parts.json
WOOCOMMERCE_STORE_API_BASE_URL
```

The default catalog is the committed mock catalog. Public Store API reads are
enabled by setting `CATALOG_CONNECTOR_MODE=store_api`.

## Public Dev Chatwoot

The public dev Chatwoot server is:

```text
https://chat.gmrahal.net
```

The underlying GMR platform host is managed by `../gmr-clients-apps/infra`:

```text
ssh deploy@167.172.143.73
app root: /srv/apps
repo: /srv/apps/repo
env root: /srv/apps/env
Chatwoot env: /srv/apps/env/platform/chatwoot.env
client envs: /srv/apps/env/clients/*.env
```

Use the public dev server for opt-in live back-and-forth tests with Meta. Use
fixtures and mocked HTTP in default CI.

For the local tunnel workflow and Chatwoot webhook sync commands, see
[Public Dev Laptop Harness](../infra/public-dev-laptop/README.md).
