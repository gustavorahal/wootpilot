# Implementation Slices

Each implementation slice should leave the repository in a runnable and testable
state. Prefer thin vertical slices over broad implementation layers.

## Planning Review Notes

The implementation plan should optimize for a short, reliable path to a working
Chatwoot copilot before adding broader agent-platform features.

Keep:

- Chatwoot webhook intake, filtering, and local conversation state as the first
  durable product spine.
- The public dev Chatwoot server, `https://chat.gmrahal.net/`, as the live
  Meta-reachable integration target for MVP back-and-forth checks.
- Product context as structured snapshots, not vector retrieval.
- LangGraph as explicit workflow orchestration, not a broad autonomous agent
  loop.
- Outbound Chatwoot writes behind an idempotent action executor.
- SQLite for local and alpha workflows, with Postgres required for production
  public auto-send.

Defer:

- Admin UI, approval UI, and LangGraph interrupt/resume flows.
- RAG, embeddings, pgvector, and LangGraph long-term stores.
- Authenticated WooCommerce REST API writes, refunds, coupons, order mutations,
  and other connector actions.
- Multi-channel support beyond Chatwoot.
- Hosted observability requirements such as LangSmith or OpenTelemetry.

The main simplification is to make each slice prove one user-visible capability
through a narrow vertical path. Shared domain models and ports are welcome when
they remove duplication, but avoid creating one shallow class per future table
or future integration before a slice has a caller.

## Current Baseline

- Disposable local Chatwoot is available through `./scripts/chatwoot-dev-up`.
- Chatwoot runs at `http://localhost:3000` with Chatwoot web, Sidekiq,
  Postgres with pgvector, and Redis.
- Use the local Chatwoot stack for manual integration checks in webhook,
  private-note, and public-reply slices.
- Use `https://chat.gmrahal.net/` for public dev checks that must be reachable
  by Meta channel infrastructure.

Do not require the Chatwoot Docker stack to start in the default CI path. The
Compose file and helper scripts should be validated automatically, while live
Chatwoot startup remains a manual or opt-in integration smoke test.

## Definition Of Done

Each slice is done only when:

- The app still starts.
- The default automated test, lint, and type-check commands pass.
- New behavior has automated unit or integration coverage at the use-case
  boundary.
- Database schema changes have Alembic migrations and apply from an empty local
  database.
- External HTTP integrations are covered by fixtures, fakes, or `respx` in CI.
- Manual verification steps are specific enough for another contributor to run.
- Any behavior that cannot be automated is explicitly called out as manual or
  opt-in live smoke verification.

## Verification Strategy

Use three levels of verification:

```text
default CI
  Fast, deterministic checks: unit tests, ASGI route tests, repository tests,
  migration tests, linting, type checking, fixture validation, and mocked HTTP.

opt-in integration
  Local services such as Chatwoot Docker Compose and Postgres, enabled by an
  explicit command or CI label when needed.

manual smoke
  Browser/UI checks, public dev Chatwoot checks at chat.gmrahal.net, real
  Meta-connected message checks, and optional live provider calls that require
  credentials or human inspection.
```

Never require real OpenRouter, WooCommerce, Chatwoot Cloud, or production
credentials in default CI. Live checks should prove wiring, not correctness; the
correctness contract belongs in deterministic tests.

## Slices

- [Slice 0: Runnable Skeleton](slices/00-runnable-skeleton.md)
- [Slice 1: Authenticated Webhook Intake](slices/01-authenticated-webhook-intake.md)
- [Slice 2: Event Filtering And Conversation State](slices/02-event-filtering-and-conversation-state.md)
- [Slice 3: Mock Product Context](slices/03-mock-product-context.md)
- [Slice 4: Shadow Workflow](slices/04-shadow-workflow.md)
- [Slice 5: OpenRouter Model Proposals](slices/05-openrouter-model-proposals.md)
- [Slice 6: Copilot Private Notes](slices/06-copilot-private-notes.md)
- [Slice 7: Limited Auto Public Replies](slices/07-limited-auto-public-replies.md)
- [Slice 8: WooCommerce Store API](slices/08-woocommerce-store-api.md)
- [Slice 9: Production Readiness](slices/09-production-readiness.md)
