# LangChain And LangGraph

WootPilot uses LangGraph as the workflow runtime and LangChain at the model
adapter boundary.

## Current Roles

LangGraph owns the explicit support workflow:

- node execution;
- command-driven routing;
- checkpointing;
- streaming updates for local terminal traces;
- generated topology diagrams.

LangChain owns model integration concerns:

- `ChatOpenRouter`;
- structured output;
- provider/tool fallback strategy;
- model metadata and usage extraction.

The top-level support workflow is not a broad autonomous LangChain agent. It is a
WootPilot-owned `StateGraph` with deterministic policy and explicit state keys.

## Graph Shape

The support graph is defined in
[`src/wootpilot/workflow/graph.py`](../../src/wootpilot/workflow/graph.py). It
uses `TypedDict` state and Pydantic domain models at the boundaries.

Current nodes:

```text
should_invoke
triage_message
policy_gate
generate_proposal
validate_outbound_action
```

Decision-making nodes return LangGraph `Command` values when they need to both
update workflow state and choose the next node. That keeps route decisions next
to the policy or model result that produced them, while `graph.py` remains a
compact topology skeleton.

## Checkpointing

Checkpointer profile is configured with `CHECKPOINTER`:

```text
memory
sqlite
postgres
```

When a persistent checkpointer is used, WootPilot passes a message-scoped
`thread_id`:

```text
tenant:{tenant_id}:channel:{channel_id}:conversation:{conversation_id}:message:{message_id}
```

This keeps per-turn policy decisions and workflow outputs from leaking into the
next message in the same Chatwoot conversation. Long-lived conversation state is
stored in WootPilot tables instead.

## Streaming

`RunCustomerSupportWorkflow` uses LangGraph streaming directly for
local/public-dev workflow visibility when `WORKFLOW_TRACE=true`. It streams
both:

- `updates`, for node-by-node terminal trace output;
- `values`, to capture the final graph state.

The final state is used by persistence code exactly as a normal `ainvoke` result.

## Model Proposals

`ModelProposalPort` is the boundary between the graph and model providers. The
OpenRouter adapter validates structured model output into a WootPilot-owned
proposal schema before creating a domain `AgentProposal`.

Prompt construction is versioned in the model adapter. Customer text is labeled
as untrusted data, compact conversation safety state is included explicitly, and
catalog rows are serialized from policy-aware prompt-safe snapshots.

`RESPONSE_LOCALE` is passed into prompt construction as an explicit language
profile. The default is `pt-BR`, so public messages, private notes, and summaries
should be written in Brazilian Portuguese while preserving product names, SKUs,
URLs, and catalog-provided price formatting. Locale is configuration, not a
model guess from customer text, because Brazilian customer messages may mix
Portuguese, English product names, codes, and links in one turn.

Model output is a proposal only. Deterministic policy and outbound execution
decide whether the proposal becomes a private note, public reply, audit-only
observation, or blocked run.

## Boundaries

LangGraph owns workflow orchestration. It does not own WootPilot's long-term
conversation memory, audit ledger, connector reads, or Chatwoot writes.

LangChain owns provider-facing model calls. It does not decide final action
status; it returns structured proposals that WootPilot policy and outbound code
validate deterministically.

## Not Currently Used

WootPilot does not currently use:

- LangGraph subgraphs;
- LangGraph stores or long-term memory;
- LangGraph interrupts for human approval;
- a top-level LangChain `create_agent` support agent.

Human review happens in Chatwoot through private notes and labels.
