# WootPilot

WootPilot adds AI-assisted support workflows to
[Chatwoot](https://www.chatwoot.com/).

It is designed for small support teams that want useful automation without
giving up human control. Chatwoot remains the system of record for
conversations, contacts, agents, teams, messages, and handoff. WootPilot runs
alongside Chatwoot, receives webhook events, gathers business context, applies
policy checks, and then drafts private notes or sends approved replies back to
Chatwoot.

## Current Status

This repository contains an alpha Python service for Chatwoot-based AI support
workflows. The first working path receives signed Chatwoot webhooks, records the
event, gathers WooCommerce catalog context, decides whether AI should assist,
and creates either a private note or an approved public reply in Chatwoot.

A disposable local Chatwoot development stack is available for manual
integration testing. A public development Chatwoot server is available at
`https://chat.gmrahal.net/` for opt-in testing with externally delivered
messages.

## Implemented Capabilities

- Receive and normalize Chatwoot webhook events.
- Ignore events that should not trigger AI assistance, such as private notes,
  outbound messages, and bot echoes.
- Detect whether a human agent is already active in a conversation.
- Classify customer intent before deciding whether to call a model.
- Load business context through connectors, starting with WooCommerce product
  catalog data.
- Support observe mode, private-note assistance, and approved public replies.
- Hand off to humans by suppressing public replies and adding review context in
  Chatwoot.
- Store audit records, context snapshots, outbound actions, and policy decisions.
- Execute queued Chatwoot private notes and public replies with retries and
  final pre-send checks.
- Optionally label conversations that need human review and update conversation
  status after public replies.
- Render workflow diagrams for documentation and review.

## Still Planned

- Authenticated WooCommerce write capabilities such as order notes, refunds,
  coupons, and order updates.
- Multi-channel support beyond Chatwoot.
- Production deployment guidance and operational readiness beyond the current
  local and public-dev workflows.

## Architecture Direction

WootPilot is centered around Chatwoot. Chatwoot is treated as the primary
support channel rather than a generic connector.

External business systems are modeled as connectors. WooCommerce is the first
connector, with read-only product catalog support in the current version. Future
connectors may include billing, CRM, documentation, inventory, order management,
or custom HTTP APIs.

The core flow is:

```text
Customer message
  -> Chatwoot
  -> WootPilot webhook endpoint
  -> webhook validation
  -> policy and context loading
  -> AI assistance proposal
  -> outbound checks
  -> queued outbound action
  -> Chatwoot private note or public reply
  -> audit log
```

## Documentation

- [Documentation Index](docs/README.md)
- [Conversation Behavior](docs/product/conversation-behavior.md)
- [Operating Modes](docs/product/operating-modes.md)
- [Architecture Overview](docs/architecture/overview.md)
- [Glossary](docs/reference/glossary.md)
- [Chatwoot Channel](docs/architecture/chatwoot-channel.md)
- [Connector Model](docs/architecture/connectors.md)
- [Workflow Architecture](docs/architecture/workflow.md)
- [Support Workflow Graph](docs/reference/support-workflow-graph.png)
- [Configuration](docs/architecture/configuration.md)
- [Persistence Model](docs/architecture/persistence.md)
- [Observability](docs/architecture/observability.md)
- [ADR Index](docs/adr/README.md)
- [Production Readiness](docs/architecture/production-readiness.md)

## Local Setup

Install dependencies and run the default checks:

```sh
uv sync
uv sync --extra postgres  # only when testing the production Postgres profile
uv run pytest
uv run ruff check .
./scripts/release-check
```

## Local WootPilot Development Loop

For day-to-day development against the public dev Chatwoot server, run WootPilot
and the public tunnel in two separate terminals.

Terminal 1: start the local WootPilot API service.

```sh
uv run uvicorn wootpilot.api.main:app --reload --host 0.0.0.0 --port 8000
```

Terminal 2: expose the local service through the managed Cloudflare tunnel.

```sh
./scripts/public-dev-tunnel-run
```

With `.env.local` configured from [.env.public-dev.example](.env.public-dev.example),
Chatwoot should send webhooks to:

```text
https://wootpilot-local-dev.gmrahal.net/webhooks/chatwoot
```

The WootPilot terminal is also where local JSON logs appear. In `local` and
`public_dev` environments, `WORKFLOW_TRACE=true` prints the workflow steps as
they complete, including the customer message and proposed response text.

Build the application container:

```sh
docker build -t wootpilot:local .
```

Initialize or migrate the local database:

```sh
uv run alembic upgrade head
# or create tables directly for disposable local use
uv run wootpilot init-db
```

Run local helper commands:

```sh
uv run wootpilot catalog-search "chicote aircooled"
uv run wootpilot execute-outbound --limit 10
uv run wootpilot eval-golden
```

Use the disposable local Chatwoot stack for manual integration testing:

```sh
./scripts/chatwoot-dev-up
```

Open `http://localhost:3000`, create the first local account, and generate a
Chatwoot API token for WootPilot development.

Reset the stack to an empty database:

```sh
./scripts/chatwoot-dev-reset
```

See [Local Chatwoot Dev Stack](infra/chatwoot-dev/README.md).

## Public Dev Chatwoot

Use `https://chat.gmrahal.net/` for opt-in manual tests that need a publicly
reachable Chatwoot environment, including Meta-connected channel testing. The
intended MVP loop is: customer message reaches Chatwoot, Chatwoot notifies
WootPilot, WootPilot writes a private note or approved public reply through the
Chatwoot API, a human can reply in Chatwoot, and WootPilot observes that human
activity before deciding whether AI should assist again.

Copy [.env.public-dev.example](.env.public-dev.example) to `.env.local` to run
WootPilot locally against this server. See
[Configuration](docs/architecture/configuration.md) for the available settings.

For the full laptop tunnel loop, use the
[Public Dev Laptop Harness](infra/public-dev-laptop/README.md):

```sh
./scripts/public-dev-webhook-sync
./scripts/public-dev-doctor
```
