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

This repository is in the initial planning and architecture phase. The first
implementation is planned as a Python 3.14 service using FastAPI, Pydantic v2,
LangGraph, SQLAlchemy/Alembic, SQLite for local alpha workflows, and PostgreSQL
for production.

A disposable local Chatwoot development stack is available for manual
integration testing. The public dev Chatwoot server for Meta-reachable MVP
testing is `https://chat.gmrahal.net/`.

## Planned Capabilities

- Receive and normalize Chatwoot webhook events.
- Ignore private notes, outbound messages, bot echoes, and non-customer events.
- Detect whether a human operator is already active in a conversation.
- Classify customer intent with deterministic rules before model calls.
- Load structured business context through external connectors.
- Use WooCommerce as the first connector for product catalog context.
- Run agent workflows through explicit LangGraph nodes.
- Support shadow mode, copilot private notes, and limited low-risk auto replies.
- Hand off to humans by suppressing public automation and surfacing private
  notes or handoff markers in Chatwoot.
- Let humans explicitly hand a later customer turn back to AI through Chatwoot
  labels or custom attributes, subject to policy.
- Persist audit records, context snapshots, outbound actions, and policy
  decisions.

## Architecture Direction

WootPilot is centered around Chatwoot, so Chatwoot is modeled as a primary
support channel rather than as a generic connector.

External business systems are modeled as connectors. WooCommerce is the first
planned connector, with a read-only product catalog capability in version 1.
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
- [Persistence Model](docs/architecture/persistence.md)
- [Observability](docs/architecture/observability.md)
- [Implementation Slices](docs/implementation/milestones.md)

## Local Chatwoot

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
