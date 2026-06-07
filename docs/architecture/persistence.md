# Persistence Model

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
  trace_id
  created_at
  completed_at

outbound_actions
  id
  agent_run_id
  tenant_id
  provider
  provider_account_id
  provider_conversation_id
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

connector_installations
  primary key (id)
  index (tenant_id, connector_key, enabled)
```

`provider_account_id` and `provider_inbox_id` should be carried through every
Chatwoot-facing table where they affect uniqueness, routing, or auditability.
Conversation ids must not be treated as globally unique.

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

The executor must update rows transactionally and use a locking strategy such as
`SELECT ... FOR UPDATE SKIP LOCKED` when PostgreSQL is available. Every retry
should increment `attempt_count`, set `next_attempt_at`, and preserve the last
`error_code`.

Build `idempotency_key` from stable inputs such as tenant id, provider account
id, provider message id, action kind, and a content hash. Do not include retry
attempt number or timestamps in the key.

Public-message actions require a final pre-send check:

- Target conversation id still matches the normalized event.
- Conversation is still replyable.
- Bot mode still allows public replies.
- Human operator is not currently active.
- The policy decision still permits the exact public content.

Private notes should also be idempotent, but they can use a less restrictive
policy path than public messages.

## Data Types

- Use PostgreSQL `jsonb` for payload snapshots and policy decision records.
- Store product price context as serialized `PriceSnapshot` domain models.
  `Money` inside those snapshots must use integer minor units, never floats.
- Use timezone-aware timestamps.
- Use SQLAlchemy 2 async sessions with psycopg 3 if the application runtime is
  async end to end.
- Keep Pydantic model validation outside SQLAlchemy ORM constructors when doing
  bulk persistence. Validate at service boundaries and persist plain values.
