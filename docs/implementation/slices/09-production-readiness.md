# Slice 9: Production Readiness

## Running Outcome

- WootPilot has the minimum deployment, evaluation, and operational checks needed
  for an MVP release.

## Implementation Scope

- Add Postgres database profile.
- Add Postgres migrations in CI.
- Add Postgres row-level queue locking for outbound action workers.
- Add LangGraph checkpointer factory for memory, SQLite, and Postgres profiles.
- Use async saver implementations for the FastAPI runtime: `AsyncSqliteSaver`
  locally and `AsyncPostgresSaver` in production.
- Add a review for whether LangSmith, LangGraph interrupts, subgraphs, or
  persistent LangGraph stores have become useful. Keep them deferred unless a
  concrete product workflow needs them.
- Add golden conversation evals.
- Add cost and latency tracking.
- Add structured log review for failed, blocked, and high-latency workflows.
- Add production deployment docs.
- Add Chatwoot Cloud compatibility notes for webhook authentication, API base
  URLs, account ids, inbox ids, and outbound message permissions.
- Revisit optional observability integrations such as LangSmith or OpenTelemetry
  after the MVP audit/logging baseline is stable.

## Required Tests

- Database migrations apply cleanly to empty SQLite and Postgres databases.
- SQLite profile enables WAL mode, foreign keys, and busy timeout.
- Postgres profile uses row-level queue locking for outbound action workers.
- LangGraph memory, SQLite, and Postgres checkpointer factories select the
  expected backend.
- Checkpointed graph runs pass tenant/channel/conversation-scoped `thread_id`
  values.
- Golden conversations cover low-risk FAQ, catalog lookup, kit escalation,
  account-sensitive requests, technical support escalation, prompt injection,
  requests for private/internal information, hidden prices, quote-required
  prices, and zero-value kit placeholders.
- Production deployment docs include required environment variables and the
  Postgres requirement for production public auto-send.
- Chatwoot Cloud configuration docs map to the same channel adapter contract used
  by local self-hosted Chatwoot.

## Manual Verification

- Run migrations against fresh SQLite and Postgres databases.
- Run the golden conversation suite.
- Review structured logs for at least one successful, blocked, retryable, and
  permanently failed workflow.
