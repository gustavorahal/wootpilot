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
- Add public dev Chatwoot runbook for `https://chat.gmrahal.net/`, including
  webhook configuration, API token scope, Meta channel setup expectations, and
  safe test-number handling.
- If WootPilot is deployed on the GMR platform host, add infra support for
  `/srv/apps/env/clients/wootpilot.env`, a WootPilot Compose service on the
  internal and egress networks, and a Caddy route such as
  `wootpilot.gmrahal.net`.
- Revisit optional observability integrations such as LangSmith or OpenTelemetry
  after the MVP audit/logging baseline is stable.
- Add release-readiness checks for secret scanning, dependency audit, and public
  repository fixture review.

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
- Public dev Chatwoot runbook covers Meta-connected inbound messages, WootPilot
  webhook delivery, Chatwoot API writes, human reply suppression, and explicit
  resume signals.
- Server-side public-dev deployment docs explain why
  `WOOTPILOT_CHATWOOT_BASE_URL=http://chatwoot-web:3000` is used for internal
  API calls while `WOOTPILOT_CHATWOOT_PUBLIC_URL=https://chat.gmrahal.net` is
  used for links and manual verification.
- Secret scanning runs against the repository history or is documented as a
  required release command.
- Deployment docs include rollback, migration, worker, and queue-draining notes.

## Manual Verification

- Run migrations against fresh SQLite and Postgres databases.
- Run the golden conversation suite.
- Review structured logs for at least one successful, blocked, retryable, and
  permanently failed workflow.
- Run an opt-in Chatwoot integration smoke test for webhook intake, private
  notes, and one blocked public auto-send case.
- Run the public dev Meta-connected loop against `https://chat.gmrahal.net/`:
  inbound customer message, AI private note or public reply, human public reply,
  public automation suppression, explicit resume signal, and next eligible
  customer message.
- Review committed fixtures and example environment files for real customer
  data, secrets, and private storefront URLs before release.
