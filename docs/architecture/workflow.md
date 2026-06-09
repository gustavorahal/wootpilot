# Policy And Support Workflow

WootPilot runs a deterministic support workflow around one public inbound
customer message at a time. The workflow prepares trusted inputs, asks the model
for a structured proposal, validates that proposal with policy, and persists an
auditable outcome.

## Automation Modes

`AutomationMode` is the product switch that controls how far WootPilot may act:

```text
observe
  Run the workflow, persist audit/proposal data, and write nothing to Chatwoot.

assist
  Queue private notes for human review.

public_reply
  Queue customer-visible replies when deterministic policy and conversation
  safety checks pass.
```

`public_reply` is the default alpha setup so local and public-dev testing exercise
the full flow. Public replies are still guarded by policy, human-active
suppression, assignment checks, replyability checks, idempotency, and a final
outbound safety re-check.

## Ingress Boundary

FastAPI handlers stay thin. `HandleWebhookEvent` owns authenticated Chatwoot
ingress:

- verify Chatwoot HMAC headers before processing;
- persist the raw event;
- deduplicate provider deliveries;
- translate Chatwoot payloads into `NormalizedMessage` or `ChannelEvent`;
- update local `ConversationState`;
- ignore private notes, outbound messages, bot echoes, and non-customer events;
- commit durable ingress state before connector/model work begins.

Only public inbound customer messages invoke the support workflow.

## Conversation Safety

`ConversationState` is WootPilot's local view of whether a conversation is safe
for automation. It tracks replyability, resolved status, pause labels, assignment
metadata, customer activity, and recent human public replies.

Human-active suppression is created when a human agent sends a public message.
The default window is 15 minutes. During that window:

- `public_reply` is blocked;
- `observe` can still run;
- `assist` can still create private notes.

Assignment to a human or team also blocks `public_reply`. There is no `auto_ok`
or per-conversation bypass flag. The current design favors sane defaults over
configurable escape hatches.

## LangGraph Workflow

The support graph lives in
[`src/wootpilot/workflow/graph.py`](../../src/wootpilot/workflow/graph.py). It is
a typed LangGraph `StateGraph` whose state is a `TypedDict` containing prepared
domain objects:

```text
normalized_message
conversation_state
catalog_context
automation_mode
triage_result
pre_model_policy_decision
agent_proposal
model_metadata
provider_error
post_model_policy_decision
workflow_decision
```

Current nodes:

```text
should_invoke
triage_message
policy_gate
llm_proposal
validate_outbound_action
route_final_decision
build_observe_decision
build_private_note_action
build_public_message_action
build_missing_proposal_failure
```

The graph does not perform database writes, connector reads, or Chatwoot writes.
`RunCustomerSupportWorkflow` loads catalog context, stores the context snapshot,
invokes the graph, persists policy decisions and audit records, and queues
outbound actions after the graph returns.

Current rendered topology:

![Support workflow graph](../reference/support-workflow-graph.png)

The Mermaid source is versioned at
[support-workflow-graph.mmd](../reference/support-workflow-graph.mmd). Regenerate
both files after graph routing changes:

```bash
uv run python scripts/render-support-workflow-graph.py
```

## Policy

Policy runs twice:

- pre-model policy blocks ineligible turns before model calls;
- post-model policy validates proposed customer-visible content.

Pre-model policy blocks non-public customer turns, non-replyable conversations,
resolved conversations, paused conversations, sensitive handoff requests, and
customer-visible `public_reply` turns where a human is active or assigned.

Post-model policy blocks or downgrades unsafe public proposals. In `public_reply`
mode, risky public proposals become private review notes instead of customer
messages. Price claims must match a mentionable catalog snapshot.

Customer text is normalized for lightweight deterministic matching before policy
rules run. The normalization is case-insensitive and accent-insensitive, so
Brazilian Portuguese terms such as `devolução` and `devolucao` are treated as
the same signal. These keyword rules are deliberately conservative alpha review
gates, not final semantic intelligence; false positives should route to private
review rather than become unsafe public replies.

## Outbound Execution

Outbound execution is separate from the graph. `ExecuteOutboundActions` claims
queued actions, re-checks local conversation state, re-reads fresh Chatwoot
safety state before public replies, sends through Chatwoot, and records the
result idempotently.

A public reply that was safe at proposal time can still be blocked at execution
time if the conversation becomes assigned, resolved, paused, non-replyable, or
human-active while the action waits in the queue.

## Structured Model Output

The model returns proposals only. It does not decide whether an action was sent.
`ModelProposalPort` validates provider output into WootPilot-owned Pydantic
schemas and returns `AgentProposal` plus provider metadata. Final workflow and
outbound statuses are computed by deterministic application code.
