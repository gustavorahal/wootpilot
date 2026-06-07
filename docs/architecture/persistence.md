# Persistence Model

Initial tables:

```text
raw_events
  id
  tenant_id
  provider
  provider_event_id
  event_type
  payload_json
  received_at
  processed_at

conversation_messages
  id
  tenant_id
  provider
  provider_conversation_id
  provider_message_id
  author_type
  direction
  visibility
  text
  created_at

conversation_state
  tenant_id
  provider_conversation_id
  human_operator_active
  human_operator_active_until
  last_human_public_message_at

agent_runs
  id
  tenant_id
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

outbound_actions
  id
  agent_run_id
  kind
  content
  provider_message_id
  status
  error_code
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
```
