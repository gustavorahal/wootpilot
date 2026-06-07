# Persistence Model

WootPilot should support two persistence profiles:

```text
sqlite
  Local development, tests, demos, shadow mode, and early single-worker copilot
  deployments.

postgres
  Production, multiple workers, high webhook volume, and any production limited
  auto-reply deployment.
```

The application should use SQLAlchemy 2 and Alembic so the domain repositories
can target both backends. SQLite support is a product choice for approachability;
Postgres remains the production target for concurrency and operational safety.

Initial tables:

```text
raw_events
  id
  tenant_id
  provider
  provider_account_id
  provider_event_id
  event_type
  payload_json
  payload_hash
  signature_verified
  received_at
  processed_at
  ignored_reason

conversation_messages
  id
  tenant_id
  provider
  provider_account_id
  provider_inbox_id
  provider_conversation_id
  provider_message_id
  provider_contact_id
  author_type
  direction
  visibility
  text
  attachments_json
  created_at

conversation_state
  tenant_id
  provider
  provider_account_id
  provider_conversation_id
  human_operator_active
  human_operator_active_until
  last_human_public_message_at
  last_customer_message_at
  updated_at

agent_runs
  id
  tenant_id
  raw_event_id
  conversation_message_id
  provider
  provider_account_id
  provider_conversation_id
  provider_message_id
  bot_mode
  status
  summary
  model
  input_tokens
  output_tokens
  latency_ms
  correlation_id
  created_at
  completed_at

policy_decisions
  id
  tenant_id
  agent_run_id
  stage
  outcome
  decision_json
  created_at

outbound_actions
  id
  agent_run_id
  tenant_id
  provider
  provider_account_id
  provider_conversation_id
  source_provider_message_id
  kind
  content
  idempotency_key
  provider_message_id
  status
  policy_decision_json
  attempt_count
  next_attempt_at
  locked_at
  locked_by
  error_code
  created_at
  updated_at

audit_records
  id
  tenant_id
  event_type
  raw_event_id
  normalized_message_id
  agent_run_id
  outbound_action_id
  policy_decision_id
  context_snapshot_ids_json
  summary
  created_at

connector_installations
  id
  tenant_id
  connector_key
  display_name
  enabled
  supported_capabilities_json
  enabled_capabilities_json
  config_json
  credentials_ref
  created_at
  updated_at

agent_context_snapshots
  id
  agent_run_id
  connector_key
  connector_installation_id
  resource_type
  external_resource_id
  snapshot_json
  captured_at

connector_actions
  id
  agent_run_id
  connector_key
  connector_installation_id
  capability
  action_kind
  proposed_payload_json
  status
  policy_decision_json
  execution_result_json
  error_code
  created_at
  updated_at
```

## Required Constraints

Use database constraints for correctness, not only application checks:

```text
raw_events
  unique (tenant_id, provider, provider_account_id, provider_event_id)

conversation_messages
  unique (tenant_id, provider, provider_account_id, provider_message_id)
  index (tenant_id, provider, provider_account_id, provider_conversation_id)

conversation_state
  primary key (tenant_id, provider, provider_account_id, provider_conversation_id)

outbound_actions
  unique (idempotency_key)
  index (status, next_attempt_at)

audit_records
  index (tenant_id, agent_run_id, created_at)
  index (tenant_id, raw_event_id, created_at)

policy_decisions
  index (tenant_id, agent_run_id, stage, created_at)

connector_installations
  primary key (id)
  index (tenant_id, connector_key, enabled)
```

`provider_account_id` and `provider_inbox_id` should be carried through every
Chatwoot-facing table where they affect uniqueness, routing, or auditability.
Conversation ids must not be treated as globally unique.

## Transaction Boundaries

Use application-level units of work for correctness-sensitive flows. The goal is
not to abstract every query, but to make duplicate delivery and action execution
predictable.

Recommended boundaries:

```text
webhook ingress transaction
  insert raw_event or load existing duplicate
  insert normalized message when the event is new and translatable
  update conversation_state when the event carries human/replyability signals
  commit before model calls

support workflow transaction
  create/update agent_run
  persist context snapshots used by the proposal
  persist policy decisions that affect execution
  persist audit record
  queue outbound action when allowed

outbound execution transaction
  claim queued action
  record executing status
  commit before external channel call
  re-open transaction to record sent, blocked, or failed result
```

Do not keep a database transaction open across an LLM call, connector HTTP call,
or Chatwoot write. Persist enough state to resume or explain the workflow, then
perform the external effect through the relevant port.

## Database Profiles

### SQLite

SQLite is acceptable when WootPilot runs as a single process or with one outbound
executor worker.

SQLite requirements:

- Use `sqlite+aiosqlite` for the async app runtime.
- Enable WAL mode.
- Set a `busy_timeout`.
- Use foreign keys explicitly.
- Keep the outbound executor single-worker.
- Avoid relying on row-level locking.
- Treat limited auto replies on SQLite as local/demo only unless explicitly
  accepted by the operator.

Suggested local URLs:

```text
WOOTPILOT_DB_URL=sqlite+aiosqlite:///./data/wootpilot.db
WOOTPILOT_CHECKPOINTER=sqlite
WOOTPILOT_LIMITED_AUTO_PRODUCTION_ALLOWED=false
```

### Postgres

Postgres is required when WootPilot needs production-grade concurrent webhook
processing, multiple outbound workers, or production limited auto replies.

Postgres requirements:

- Use `postgresql+psycopg` with SQLAlchemy 2 async sessions.
- Use `jsonb` for payload snapshots and policy decision records.
- Use row-level locking for queue workers.
- Use production backups, monitoring, and migration discipline.
- Add `pgvector` later only when semantic retrieval is needed.

Suggested production URLs:

```text
WOOTPILOT_DB_URL=postgresql+psycopg://wootpilot:...@db.example/wootpilot
WOOTPILOT_CHECKPOINTER=postgres
WOOTPILOT_LIMITED_AUTO_PRODUCTION_ALLOWED=true
```

## LangGraph Checkpoints

LangGraph checkpoint persistence should be configured independently from
WootPilot's application tables, even if both use the same database backend.

Supported checkpointer profiles:

```text
memory
  Tests and short-lived experiments only.

sqlite
  Local development and single-worker alpha workflows using
  langgraph-checkpoint-sqlite.

postgres
  Production workflows using langgraph-checkpoint-postgres.
```

Thread memory, time travel debugging, and fault-tolerant graph resumes depend on
checkpointers. SQLite is enough to start, but production graph state should move
to Postgres with the rest of production persistence.

MVP copilot workflows should complete after producing a Chatwoot private note.
They should not pause on LangGraph interrupts for human approval.

## Idempotent Action Execution

Outbound writes should use an outbox-style flow:

```text
agent graph proposes action
  -> guard validates action
  -> outbound_actions row is inserted with status=queued
  -> executor locks queued row
  -> executor re-checks policy and human-active state
  -> channel client sends
  -> row becomes sent or failed/retryable
```

Statuses:

```text
queued
executing
sent
blocked_by_policy
failed_retryable
failed_permanent
cancelled
```

The executor must update rows transactionally. On Postgres, use row-level locking
such as `SELECT ... FOR UPDATE SKIP LOCKED`. On SQLite, run a single executor
worker and claim queued actions with short transactions guarded by status updates.
Every retry should increment `attempt_count`, set `next_attempt_at`, and preserve
the last `error_code`.

Build `idempotency_key` from stable inputs such as tenant id, provider account
id, source provider message id, action kind, and a content hash. Do not include
retry attempt number or timestamps in the key.

Public-message actions require a final pre-send check:

- Target conversation id still matches the normalized event.
- Conversation is still replyable.
- Bot mode still allows public replies.
- Human operator is not currently active according to local state and, when
  available, fresh channel state.
- The policy decision still permits the exact public content.

Private notes should also be idempotent, but they can use a less restrictive
policy path than public messages.

## Data Types

- Use portable SQLAlchemy JSON columns for payload snapshots and policy decision
  records. They should map to SQLite JSON text/JSON support locally and Postgres
  `jsonb` in production.
- Store product price context as serialized `PriceSnapshot` domain models.
  `Money` inside those snapshots must use integer minor units, never floats.
- Use timezone-aware timestamps.
- Use SQLAlchemy 2 async sessions for both supported backends.
- Keep Pydantic model validation outside SQLAlchemy ORM constructors when doing
  bulk persistence. Validate at service boundaries and persist plain values.

## Migration Discipline

- Every schema change should be represented as an Alembic migration.
- Migrations must run against both SQLite and Postgres in CI.
- Avoid Postgres-only schema features in shared tables unless the SQLite fallback
  is explicitly documented.
- Postgres-only operational behavior, such as `SKIP LOCKED`, should live in
  repository or outbox implementations selected by database profile.
