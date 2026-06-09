# Architecture Vocabulary

WootPilot should use one consistent language for architectural roles. These terms
are intentionally narrow so code names stay predictable.

## Boundary Terms

```text
Adapter
  Owns an integration boundary with an outside system or infrastructure concern.
  An adapter coordinates clients, translators, retries, and provider-specific
  behavior for one boundary.

Translator
  Converts between representations. Translators turn external DTOs, provider
  payloads, database rows, or outbound domain objects into the representation
  needed on the other side of a boundary.

Client
  Performs low-level API calls. A client should know HTTP paths, headers,
  authentication, timeouts, and response DTOs. It should not contain domain
  policy or workflow decisions.

Repository
  Persists and loads domain objects. Repositories may use persistence translators
  internally to convert database rows, but application services should interact
  with repositories in domain language.

Port
  A narrow protocol owned by the application core for behavior that crosses an
  external boundary, such as persistence, channel writes, model calls, time, id
  generation, or connector capabilities. A port should be introduced when it
  protects a meaningful use-case boundary, not for every helper function.

Registry
  Selects configured adapters or connector installations. A registry should not
  translate external payloads or execute provider API calls.

Service
  Orchestrates domain workflows. Services compose ports, repositories,
  registries, policy, and domain objects. They should not parse raw provider
  DTOs or depend on concrete provider clients.

DTO
  A data transfer object at a boundary. DTOs are allowed in clients, adapters,
  translators, and persistence code. DTOs should not leak into domain services,
  policy, or agent graph state.
```

## Naming Rules

- Use `integrations/<provider>.py` for provider boundaries that currently fit in
  one module, such as Chatwoot and OpenRouter. Split into package-level
  `client.py`, `translators.py`, or `adapter.py` only when the boundary becomes
  large enough that those names hide real complexity.
- Use `catalog/` for product-catalog connector selection and implementations.
- Use `persistence/repositories.py` for persistence access.
- Use `domain/ports.py` for application-owned `Protocol` definitions that
  represent external effects.
- Use `factory.py` or `registry.py` for selecting configured connector adapters
  or installations.
- Avoid new names such as `mapper`, `normalizer`, `converter`, or `builder` for
  boundary translation unless the code has a clearly different job.

## Representation Flow

Inbound channel flow:

```text
Chatwoot webhook DTO
  -> integrations/chatwoot.py
  -> ChannelEvent / NormalizedMessage
  -> application service
  -> agent graph
```

Connector read flow:

```text
application service
  -> ProductCatalogConnector protocol
  -> catalog/factory.py selects mock or Store API connector
  -> catalog connector reads fixture data or WooCommerce Store API DTOs
  -> ProductSnapshot / PriceSnapshot / AvailabilitySnapshot
  -> application service receives domain snapshots
```

Persistence flow:

```text
database row
  -> persistence/repositories.py
  -> domain object
  -> repository caller
```

Outbound channel flow:

```text
OutboundAction
  -> ExecuteOutboundActions
  -> integrations/chatwoot.py
  -> Chatwoot API
```

## Rule Of Thumb

DTOs die at adapters. Domain objects cross the core.
