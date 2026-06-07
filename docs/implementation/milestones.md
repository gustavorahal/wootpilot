# Implementation Slices

Each implementation slice should leave the repository in a runnable and testable
state. Prefer thin vertical slices over broad implementation layers.

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

## Open Questions

- Should the first public release target Chatwoot Cloud, self-hosted Chatwoot, or
  both?
- Should WootPilot write only private notes by default?
- Should WooCommerce price mentions be disabled by default in limited auto mode?
- What fictional demo catalog should be committed for public examples?
- Should the project include a tiny admin UI, or stay API-only initially?
