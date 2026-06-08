# WootPilot

WootPilot is an AI copilot infrastructure project for
[Chatwoot](https://www.chatwoot.com/).

The goal is to help small support teams run safe, auditable AI-assisted
workflows without replacing their helpdesk. Chatwoot remains the system of
record for conversations, contacts, agents, teams, messages, and human handoff.
WootPilot sits beside it as an external service that receives webhooks, gathers
business context, applies deterministic policy, and drafts or sends responses
back to Chatwoot.

## Current Status

This repository now contains an alpha Python 3.14 service using FastAPI,
Pydantic v2, LangGraph, LangChain/OpenRouter, SQLAlchemy/Alembic, and SQLite for
local workflows. The implemented vertical path receives signed Chatwoot
webhooks, stores raw and normalized events, builds deterministic WooCommerce
catalog context from either the mock catalog or the public Store API, runs the
support workflow in LangGraph, audits the decision, and queues/executes
Chatwoot outbound actions through an idempotent outbox.

A disposable local Chatwoot development stack is available for manual
integration testing. The public dev Chatwoot server for Meta-reachable MVP
testing is `https://chat.gmrahal.net/`.

## Implemented Capabilities

- Receive and normalize Chatwoot webhook events.
- Ignore private notes, outbound messages, bot echoes, and non-customer events.
- Detect whether a human operator is already active in a conversation.
- Classify customer intent with deterministic rules before model calls.
- Load structured business context through external connectors.
- Use WooCommerce as the first connector for product catalog context, with both
  mock-catalog and public Store API profiles.
- Run agent workflows through explicit, documented LangGraph nodes and named
  conditional branches.
- Support shadow mode, copilot private notes, and limited low-risk auto replies.
- Hand off to humans by suppressing public automation and surfacing private
  notes or handoff markers in Chatwoot.
- Let humans explicitly hand a later customer turn back to AI through Chatwoot
  labels or custom attributes such as `wootpilot-auto-ok`, subject to policy.
- Persist audit records, context snapshots, outbound actions, and policy
  decisions.
- Execute queued Chatwoot private notes and public replies with retry scheduling,
  permanent-failure handling, and final pre-send safety checks.
- Optionally mark private-review conversations with a needs-human label and move
  conversations to a configured Chatwoot status after public replies.
- Render the support workflow topology as versioned Mermaid and PNG
  documentation artifacts.

## Still Planned

- Authenticated WooCommerce write capabilities such as order notes, refunds,
  coupons, and order mutations.
- Multi-channel support beyond Chatwoot.
- Production-grade Postgres deployment and operational hardening beyond the
  current optional dependency/readiness checks.

## Architecture Direction

WootPilot is centered around Chatwoot, so Chatwoot is modeled as a primary
support channel rather than as a generic connector.

External business systems are modeled as connectors. WooCommerce is the first
connector, with a read-only product catalog capability in version 1.
Future connectors may include billing, CRM, documentation, inventory, order
management, or custom HTTP APIs.

The core flow is:

```text
Customer message
  -> Chatwoot
  -> WootPilot webhook endpoint
  -> authenticated ingress and replay protection
  -> policy and context loading
  -> LangGraph agent proposal
  -> outbound guardrails
  -> idempotent outbound action execution
  -> Chatwoot private note or public reply
  -> audit log
```

## Documentation

- [WootPilot Initial Plan](docs/wootpilot-initial-plan.md)
- [Architecture Overview](docs/architecture/overview.md)
- [Architecture Vocabulary](docs/architecture/vocabulary.md)
- [Chatwoot Channel Model](docs/architecture/channels.md)
- [MVP Conversation Behavior](docs/architecture/mvp-conversation-behavior.md)
- [Connector Model](docs/architecture/connectors.md)
- [Configuration](docs/configuration.md)
- [Domain Models](docs/architecture/domain-models/overview.md)
- [Policy And Agent Workflow](docs/architecture/policy-and-agent-workflow.md)
- [Support Workflow Graph](docs/architecture/support-workflow-graph.png)
- [Persistence Model](docs/architecture/persistence.md)
- [Observability](docs/architecture/observability.md)
- [Implementation Slices](docs/implementation/milestones.md)
- [Production Readiness](docs/production-readiness.md)

## Local Chatwoot

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

The WootPilot terminal is also where local JSON logs appear, including
`webhook_handled`, `webhook_authentication_failed`, and
`support_workflow_completed` events.

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

Use `https://chat.gmrahal.net/` for opt-in manual smoke tests that need a
publicly reachable Chatwoot environment, including Meta-connected channel
back-and-forth. The intended MVP loop is: customer message reaches Chatwoot,
Chatwoot notifies WootPilot, WootPilot writes a private note or safe public
reply through the Chatwoot API, a human can reply in Chatwoot, and WootPilot
observes that human activity before deciding whether a later customer turn is
eligible for AI again.

Copy [.env.public-dev.example](.env.public-dev.example) to `.env.local` to run
WootPilot locally against this server. The implementation should read these
values through `pydantic-settings` from `WOOTPILOT_*` environment variables; see
[Configuration](docs/configuration.md).

For the full laptop tunnel loop, use the
[Public Dev Laptop Harness](infra/public-dev-laptop/README.md):

```sh
./scripts/public-dev-webhook-sync
./scripts/public-dev-doctor
```
