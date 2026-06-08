# Slice 4: Shadow Workflow

## Running Outcome

- WootPilot can run the support workflow in shadow mode from a stored customer
  message, produce an audited decision, and avoid all Chatwoot writes.

## Implementation Scope

- Add minimal `AgentRun`, `PolicyDecision`, `AgentProposal`, `AuditRecord`, and
  workflow decision models.
- Add `RunSupportWorkflow`.
- Add pre-model policy gate.
- Add LangGraph workflow that receives prepared normalized message,
  conversation state, bot mode, policy inputs, and catalog context.
- Implement the workflow as a typed `StateGraph` with explicit nodes and stable
  state keys documented next to the graph state type.
- Add a LangGraph checkpointer factory with `InMemorySaver` for tests; keep the
  interface ready for SQLite/Postgres profiles added later.
- Add an in-memory or fake `ModelProposalPort` for deterministic workflow tests.
- Persist agent run, policy decisions, context snapshot links, and audit records.
- Keep graph nodes free of connector reads, database writes, and Chatwoot writes.
- Keep this slice deterministic by using the fake model proposal port in default
  tests. Real provider calls belong to Slice 5.

## Required Tests

- Shadow workflow produces an agent run and audit record.
- Shadow workflow creates no outbound action and performs no Chatwoot write.
- Pre-model policy blocks ineligible messages before model proposal.
- Graph returns a stable workflow decision for ignored, blocked, shadow
  proposed, and provider-failure cases.
- Policy decision rule ids and outcomes are stable.
- Graph receives prepared conversation/catalog context.
- Graph invocation uses a stable tenant/channel/conversation `thread_id` when a
  checkpointer is enabled.
- LangGraph workflow does not perform connector reads, database writes, or
  Chatwoot writes.
- Audit records link raw event, normalized message, agent run, policy decision,
  and context snapshot ids.
- Audit records and context snapshots redact secrets, contact data, raw payloads,
  and sensitive pricing text.
- Architecture import boundaries prevent domain models from importing API,
  persistence, channel, connector, or provider SDK modules.

## Manual Verification

- Run a fixture customer message through shadow mode.
- Confirm the database contains an agent run, policy decision, audit record, and
  context snapshot links.
- Confirm no outbound action row or Chatwoot write is created.
- With `WOOTPILOT_BOT_MODE=shadow`, run the public-dev laptop harness and send a
  Meta-connected test message. Confirm the real Chatwoot webhook drives the same
  stored shadow decision while creating no private note or public reply in
  Chatwoot.
