# Domain Models

Domain models define shared vocabulary that should stay independent of FastAPI
handlers, Chatwoot payloads, WooCommerce payloads, database rows, and LLM
provider schemas. These objects are the language the rest of WootPilot should use
when it needs durable meaning.

## Current Models

- [Tenants](tenants.md)
- [Money](money.md)
- [Price Snapshots](price-snapshots.md)
- [Availability Snapshots](availability-snapshots.md)
- [Product Snapshots](product-snapshots.md)
- [Normalized Messages](normalized-messages.md)
- [Conversation State](conversation-state.md)
- [Triage Results](triage-results.md)
- [Risk Signals](risk-signals.md)
- [Policy Decisions](policy-decisions.md)
- [Agent Proposals](agent-proposals.md)
- [Outbound Actions](outbound-actions.md)
- [Connector Installations](connector-installations.md)
- [Context Snapshots](context-snapshots.md)
- [Audit Records](audit-records.md)

## Boundary Rules

- Domain models should express WootPilot concepts, not vendor payload shapes.
- Channel and connector packages should map raw external data into domain models
  before services or agent workflows consume it.
- Database rows may persist serialized domain models, but ORM models should not
  become the domain language.
- LLM provider schemas may mirror domain models for structured output, but the
  provider-specific details should stay outside the domain layer.

## Pythonic Modeling Guidelines

- Prefer small immutable Pydantic v2 models for externally sourced snapshots and
  policy decisions.
- Prefer dataclasses or plain functions for internal algorithms that do not need
  validation, serialization, or JSON schema.
- Use `Protocol` for connector capabilities and dependency boundaries.
- Use `Field(default_factory=...)` for all mutable defaults.
- Keep Pydantic validators deterministic and side-effect free. Do not perform
  database or network access inside validators.
- Use explicit type aliases for identifiers once the codebase grows enough to
  benefit from them, for example `type TenantId = str`.
