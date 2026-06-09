# Persistence Model

WootPilot persists application state with SQLAlchemy models in
[`src/wootpilot/persistence/models.py`](../../src/wootpilot/persistence/models.py).
Alembic is configured in [`alembic/`](../../alembic/), and every persisted schema
change must be represented as a migration.

## Database Profiles

Supported profiles:

```text
sqlite
  Local development, tests, public-dev laptop runs, and single-worker alpha use.

postgres
  Production target for concurrent webhook processing and multiple outbound
  workers.
```

SQLite uses `sqlite+aiosqlite`, WAL mode, foreign keys, and a busy timeout.
Postgres uses `postgresql+psycopg` and supports row-level locking for queue
workers.

## Current Tables

Current WootPilot-owned tables:

```text
raw_events
conversation_messages
conversation_states
context_snapshots
agent_runs
policy_decisions
outbound_actions
audit_records
```

LangGraph checkpointer tables are framework-owned operational state and are not
part of WootPilot's audit ledger.

## Table Roles

`raw_events` stores authenticated provider webhook payloads, payload hashes,
event types, processing status, and provider-event dedupe keys.

`conversation_messages` stores normalized Chatwoot messages with tenant,
account, inbox, conversation, message, contact, direction, visibility, author,
content, attachment, and metadata fields.

`conversation_states` stores WootPilot's local view of conversation safety:
replyability, open/resolved status, paused state, assignment, customer activity,
human public reply timestamps, and human-active windows.

`context_snapshots` stores compact context used by a workflow run. The current
snapshot kind is catalog context.

`agent_runs` stores one workflow run for one normalized message, including
automation mode, status, final workflow decision, model metadata, and links to
the raw event and normalized message.

`policy_decisions` stores every deterministic pre-model and post-model decision
with stable rule ids and details. A successful model-assisted turn normally has
both a pre-model allow row and a post-model validation row linked to the same
`agent_run`.

`outbound_actions` is the outbox for private notes and public replies. It tracks
tenant/channel/conversation identity, source message id, action kind, content,
safety context, status, provider message id, retry attempts, next attempt time,
error code, failure reason, timestamps, and a unique idempotency key.

`audit_records` ties raw events, normalized messages, agent runs, policy
decisions, context snapshots, and workflow outcomes into an operator-readable
ledger.

## Transaction Boundaries

Webhook ingress commits raw events, normalized messages, and conversation state
before connector or model work begins. This makes duplicate detection and human
suppression durable even if later workflow execution fails.

Support workflow execution stores context snapshots, policy decisions, agent
runs, audit records, and queued outbound actions after the graph returns.

Outbound execution atomically claims due actions by moving them to `executing`,
commits that claim before channel calls, performs the external Chatwoot write
outside a long database transaction, then records sent, blocked, retryable
failure, or permanent failure status.

## Constraints And Idempotency

Important correctness constraints include:

- unique provider event ids for raw webhook dedupe;
- unique normalized message identity per tenant/channel/message;
- unique conversation state per tenant/channel/conversation;
- unique outbound idempotency keys;
- status/next-attempt indexes for queue claiming.

Outbound idempotency keys include tenant, channel, conversation, source message,
and action kind. This prevents repeated webhook deliveries from producing
duplicate customer-visible writes for the same source turn.

Repository code normalizes SQLite datetime values back to timezone-aware UTC
objects when reading rows, because SQLite does not preserve timezone awareness
reliably.

## LangGraph Checkpoints

Checkpointer profile is configured independently from application tables:

```text
none
memory
sqlite
postgres
```

For checkpointed graph invocations, WootPilot uses a message-scoped LangGraph
`thread_id`:

```text
tenant:{tenant_id}:channel:{channel_id}:conversation:{conversation_id}:message:{message_id}
```

Long-lived conversation memory lives in WootPilot application tables, not in
LangGraph checkpoint state.

## Migrations

Release checks run:

```bash
uv run alembic upgrade head
```

Application startup may create tables for fresh non-production alpha profiles,
but production startup relies on explicit Alembic migration. The app does not
contain ad hoc schema upgrade helpers. If a persisted table changes, add an
Alembic migration.
