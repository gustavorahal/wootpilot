# LangChain And LangGraph Guidance

This document records how WootPilot should use LangChain and LangGraph. The
goal is to benefit from the current framework APIs without turning the product
into a generic autonomous-agent platform.

## Framework Roles

Use LangGraph as the workflow runtime. WootPilot needs explicit durable support
flows, deterministic policy gates, auditable state, and safe handoff between
model proposals and outbound execution. Those are graph concerns.

Use LangChain for model integration primitives that are directly useful:

- Chat model adapters such as `ChatOpenRouter`.
- Structured output helpers and provider/tool strategy selection.
- Message and runnable abstractions when they simplify model adapter code.
- Optional middleware only when it fits an already-defined WootPilot use case.

Do not start with a broad LangChain agent that owns the whole support workflow.
LangChain `create_agent` is useful inside `ModelProposalPort` when its
structured output and middleware features reduce adapter code, but the top-level
workflow should remain a WootPilot `StateGraph`.

## Version And Feature Floor

When implementation starts, prefer the current stable LangChain and LangGraph v1
lines. The planned feature floor is:

```text
langchain >= 1.2
langgraph >= 1.2
langchain-openrouter
langgraph-checkpoint-sqlite
langgraph-checkpoint-postgres
```

This floor is intentional because current docs describe:

- LangChain structured output strategy selection with `ProviderStrategy`,
  `ToolStrategy`, and `strict` provider-schema support.
- LangGraph node-level `retry_policy` and `error_handler` hooks.
- Current checkpoint and store APIs for durable execution and memory.

If dependency availability lags on Python 3.14, keep CI on Python 3.13 until the
feature floor is installable.

## Graph Shape

Build the support workflow as a typed `StateGraph`.

Use `TypedDict` for graph state unless runtime validation inside the graph
itself becomes valuable. Domain models should stay Pydantic v2 objects at the
application boundaries. Graph nodes should return partial state updates instead
of mutating state in place.

The first graph should use explicit nodes:

```text
should_invoke
triage_message
policy_gate
llm_proposal
validate_outbound_action
build_workflow_decision
```

Conditional routing can use normal conditional edges for simple branches. Use
LangGraph `Command` when a node needs to update state and route together, such
as routing exhausted model failures to a blocked or retryable workflow decision.

Do not use subgraphs for the MVP. Add subgraphs only when a real nested workflow
emerges, such as a future multi-step returns workflow or specialist product
research workflow. If subgraphs are added later, prefer per-invocation subgraph
persistence unless that subgraph truly needs memory across calls on the same
thread.

## Durable Execution

Compile graphs with a checkpointer outside short pure-unit tests.

Use these profiles:

```text
InMemorySaver
  Unit tests, experiments, and fixtures.

AsyncSqliteSaver
  Local development, demos, and single-worker alpha workflows.

AsyncPostgresSaver
  Production workflows, concurrent workers, and any production public auto-send.
```

Every graph invocation that uses a checkpointer must pass a stable `thread_id`.
For WootPilot, derive it from tenant, channel, and conversation identifiers so
Chatwoot conversation history does not leak across tenants:

```text
tenant:{tenant_id}:channel:{channel_id}:conversation:{conversation_id}
```

Checkpoint tables are framework-owned operational state. They should be
configured next to, but not treated as, WootPilot's audit ledger. Application
tables remain the source of truth for raw events, normalized messages, policy
decisions, context snapshots, agent runs, and outbound actions.

## Stores And Memory

Do not use LangGraph long-term memory for the MVP support path. WootPilot's
first memory-like data should be explicit domain state: conversation state,
context snapshots, connector snapshots, and audit records.

Add a LangGraph store later only when WootPilot needs cross-thread semantic or
preference memory that is not already a domain model. If added, namespace store
items by tenant and customer/contact, and prefer a persistent Postgres-backed
store in production. Keep customer facts auditable and avoid silently mixing
memory into public responses without policy visibility.

## Model Proposals

`ModelProposalPort` owns prompts, model selection, structured-output strategy,
retry mapping, usage capture, provider metadata, and provider-specific errors.
The domain layer consumes only `AgentProposal` and WootPilot result types.

For OpenRouter, prefer `langchain-openrouter` and `ChatOpenRouter`. Use
`with_structured_output(AgentProposalSchema, method="json_schema")` when the
selected model supports JSON Schema well. Fall back to tool/function-calling
structured output only when model support requires it. Capture the raw model
message or response metadata alongside the parsed Pydantic object so token
usage, model id, provider routing, and safety/debug metadata remain available.

If LangChain `create_agent` is used inside the adapter, use
`response_format=AgentProposalSchema` or an explicit `ProviderStrategy` /
`ToolStrategy`. Do not expose the resulting agent state directly to domain
services; translate the final `structured_response` into WootPilot domain
models.

## Retries And Errors

Use LangGraph node-level retry policies only for transient graph node failures.
For the MVP, the main candidate is `llm_proposal`, where provider timeouts,
rate limits, and temporary 5xx responses can retry safely.

After retries are exhausted, use a node-level `error_handler` or adapter result
type to route into a durable workflow decision instead of letting exceptions
erase context. Persist enough metadata for operators to distinguish retryable
provider failures from permanent schema, policy, or authentication failures.

Do not retry deterministic policy failures, validation failures caused by unsafe
content, or outbound sends inside the graph. Public and private Chatwoot writes
belong to the outbound action executor, which has its own idempotency and retry
rules.

## Human Review

LangGraph interrupts are the right primitive when the product needs to pause a
graph, expose state to a reviewer, and later resume with `Command(resume=...)`.
WootPilot should not use interrupts for MVP copilot mode because Chatwoot
private notes already provide the review surface and keep the graph run simple.

Revisit interrupts only after WootPilot has a first-class approval UI or API.
At that point, use a persistent checkpointer, stable `thread_id`, and a review
payload that contains only redacted decision context.

## Observability

Use WootPilot's local audit records and structured logs as the MVP baseline.
LangSmith remains optional until operators need trace visualization, hosted
debugging, or evaluation workflows that exceed the local audit trail.

When streaming graph events for tests or future UI, treat state keys as a
contract. Document stable output keys next to the graph definition and avoid
coupling clients to incidental internal state.
