# WootPilot Initial Plan

Date: 2026-06-07

## Summary

WootPilot is an open-source Python service for building safe AI-assisted support
workflows on top of Chatwoot.

The first version should not try to replace Chatwoot. Chatwoot remains the
system of record for inboxes, conversations, agents, teams, contacts, messages,
and human handoff. WootPilot acts as an external AI agent service that receives
Chatwoot webhooks, evaluates policy, gathers context, drafts or sends responses,
and records auditable decisions.

The design goal is a practical production-ready foundation:

- Chatwoot-native integration through webhooks and APIs.
- Public dev-loop validation against `https://chat.gmrahal.net/`, the
  Meta-reachable Chatwoot development server.
- WooCommerce product-context integration for ecommerce support conversations.
- Python-first AI stack using LangGraph as the workflow runtime, OpenRouter as
  the first model provider, Pydantic v2 for domain validation, and narrowly
  scoped LangChain components for chat models and structured output.
- Deterministic policy before and after model calls.
- Human-in-the-loop by default for risky support, sales, billing, technical, or
  account-specific claims.
- Clear separation between raw source data, extracted facts, model judgment, and
  final outbound actions.

## Product Positioning

Working name:

```text
WootPilot
```

Short description:

```text
Open-source AI copilot infrastructure for Chatwoot.
```

Longer description:

```text
WootPilot connects to Chatwoot and helps support teams run safe, auditable AI
workflows. It can classify conversations, load business context, draft replies,
write private notes, and optionally send limited public responses under strict
policy controls.
```

## Initial Use Cases

The first version should support a narrow but useful set of workflows:

1. Receive Chatwoot message webhooks.
2. Ignore private notes, outbound messages, bot echoes, and non-customer events.
3. Detect whether a human operator is already active in the conversation.
4. Classify customer intent with deterministic rules first.
5. Load structured product context from WooCommerce or the local mock
   WooCommerce catalog.
6. Draft a safe response or private note.
7. In shadow mode, log what the agent would have done.
8. In copilot mode, write private notes for human review.
9. In limited auto mode, send public replies only for low-risk cases.
10. Hand off to humans by suppressing public automation and writing private
    notes or labels when policy says human review is needed.
11. Allow humans to hand back to AI through explicit Chatwoot control signals,
    such as a WootPilot resume label, on a later customer turn.
12. Persist an audit trail for every decision.

## Non-Goals For Version 1

The first version should avoid broad autonomy.

Do not include:

- Automatic refunds, discounts, plan changes, cancellations, or account changes.
- Unapproved technical diagnosis.
- Unapproved legal, medical, financial, or policy-sensitive advice.
- Autonomous checkout or payment collection.
- Heavy RAG platform complexity before the structured-context path is proven.
- A custom support inbox UI that competes with Chatwoot.

## Architecture

High-level flow:

```text
Customer message
  -> Chatwoot
  -> WootPilot webhook endpoint
  -> authenticated ingress verification
  -> replay protection
  -> deduplication
  -> channel translation into NormalizedMessage
  -> deterministic triage
  -> WooCommerce product context loading
  -> policy gate
  -> LangGraph agent proposal
  -> outbound guardrails
  -> idempotent outbound action execution
  -> Chatwoot public message or private note
  -> human reply or WootPilot resume/pause signal observed through Chatwoot
  -> audit log and structured operational logs
```

Core architecture:

```text
FastAPI
  Receives webhooks, exposes health/admin endpoints, and owns transport concerns.

Ingress
  Authenticates webhook requests, rejects replays, persists raw events,
  deduplicates provider events, and uses channel translators to convert payloads
  into domain messages before any agent workflow starts.

Channels
  Integrate with the conversation platform WootPilot is centered around.
  Chatwoot is the first channel and should not be mixed with external business
  connectors. Channel adapters coordinate channel clients and translators.

Domain services
  Implement a small set of use cases around webhook handling, support workflow
  execution, catalog context loading, policy, and outbound action execution.
  They depend on narrow ports for persistence, model calls, channel writes,
  channel safety reads, time, and id generation.

LangGraph
  Orchestrates support reasoning as explicit stateful nodes. It receives
  normalized messages and compact context; it should not own raw webhook
  authentication, replay protection, transaction boundaries, outbound execution,
  or low-level connector payload mapping.

Connectors
  Integrate with external small-business systems that provide business context
  or, later, business actions. WooCommerce is the first connector. Later
  connectors may include billing, CRM, docs, inventory, order management, or
  custom HTTP APIs. Connector adapters coordinate connector clients and
  translators.

Persistence
  Stores raw events, normalized messages, decisions, outbound actions, human
  activity state, context snapshots, connector installations, and graph
  checkpoints. Public writes must flow through an idempotent outbox/action
  pipeline.

Observability
  Captures structured logs, model calls, tool calls, policy decisions, connector
  activity, costs, latency, and redacted payload summaries. The MVP should not
  depend on LangSmith or any hosted observability service.
```

Detailed architecture:

- [Architecture Overview](architecture/overview.md)
- [Architecture Vocabulary](architecture/vocabulary.md)
- [Configuration](configuration.md)
- [Public Dev Laptop Harness](../infra/public-dev-laptop/README.md)
- [Chatwoot Channel Model](architecture/channels.md)
- [MVP Conversation Behavior](architecture/mvp-conversation-behavior.md)
- [Connector Model](architecture/connectors.md)
- [Domain Models](architecture/domain-models/overview.md)
- [Policy And Agent Workflow](architecture/policy-and-agent-workflow.md)
- [LangChain And LangGraph Guidance](architecture/langchain-langgraph.md)
- [Persistence Model](architecture/persistence.md)
- [Observability](architecture/observability.md)

Implementation planning:

- [Implementation Slices](implementation/milestones.md)

## Recommended Python Stack

Runtime and API:

- Python 3.14 as the primary development and CI runtime.
- Python 3.13 compatibility only while key dependencies still need it.
- FastAPI
- Uvicorn
- Pydantic v2
- pydantic-settings
- HTTPX
- Tenacity

Configuration:

- Runtime settings read from `WOOTPILOT_*` environment variables through
  `pydantic-settings`.
- Committed templates in `.env.example` and `.env.public-dev.example`.
- Local developer secrets in ignored `.env.local`.
- Server-side live-dev secrets in `/srv/apps/env/clients/wootpilot.env` if
  WootPilot is deployed beside Chatwoot on the GMR platform host.
- Public dev Chatwoot API calls use `https://chat.gmrahal.net` when WootPilot
  runs locally, and `http://chatwoot-web:3000` when WootPilot runs as a
  container on the same server-side Docker network.

Agent and LLM infrastructure:

- LangGraph v1 as the explicit stateful workflow runtime
- LangChain v1, only for components that are directly useful
- OpenRouter as the MVP model provider
- `langchain-openrouter` for LangChain/LangGraph chat model integration
- LangChain structured output APIs through `with_structured_output`,
  `response_format`, `ProviderStrategy`, or `ToolStrategy`, selected per model
  capability inside `ModelProposalPort`
- Direct HTTPX calls to OpenRouter only if the dedicated integration blocks a
  required MVP feature

Persistence:

- SQLAlchemy 2
- Alembic
- SQLite through `aiosqlite` for local development, tests, demos, shadow mode,
  and early single-worker copilot workflows
- PostgreSQL through `psycopg` for production, multiple workers, and production
  limited auto replies
- `langgraph-checkpoint-sqlite` for local and alpha workflows
- `langgraph-checkpoint-postgres` for production workflows
- pgvector, later, only when semantic retrieval is needed

Deferred observability integrations:

- LangSmith, later, only after the local audit/logging path proves useful.
- OpenTelemetry, later, when operators need standard metrics and distributed
  tracing export.

Deferred model provider integrations:

- Direct OpenAI and Anthropic provider integrations, later, when WootPilot needs
  provider-specific behavior that OpenRouter does not expose.

Developer experience:

- uv
- Ruff for linting, import sorting, and formatting
- Pyright or basedpyright for strict type checking
- pytest
- pytest-asyncio
- respx
- pre-commit

## Initial Recommendation

Build the first release as an API-only service with:

- FastAPI.
- LangGraph.
- Pydantic.
- OpenRouter-backed model proposals.
- SQLAlchemy/Alembic persistence with SQLite first and Postgres as the production
  target.
- LangGraph checkpointers configured per environment, with stable tenant/channel
  conversation thread ids.
- Chatwoot API client.
- Public dev Chatwoot integration path for `https://chat.gmrahal.net/`, with
  Meta-connected inbound messages entering Chatwoot and WootPilot writing back
  through Chatwoot APIs.
- Connector registry with tenant-scoped WooCommerce `mock` and `store_api`
  product catalog modes.
- First-class domain models for tenant boundaries, normalized messages, money,
  price snapshots, availability snapshots, product snapshots, triage, risk
  signals, policy decisions, agent proposals, outbound actions, connector
  installations, context snapshots, conversation state, and audit records.
- Idempotent outbound action execution with final policy and human-active
  rechecks.
- Human handoff through Chatwoot: public automation pauses when a human is active
  or policy requires review, and explicit Chatwoot labels/custom attributes can
  allow the next eligible customer turn to return to AI.
- Shadow and copilot modes first.
- Limited auto replies behind an explicit configuration flag, with Postgres
  required before production public auto-send.

This keeps WootPilot focused: a reliable agent runtime for Chatwoot, not a new
helpdesk and not an uncontrolled chatbot.
