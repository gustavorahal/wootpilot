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

Registry
  Selects configured adapters or connector installations. A registry should not
  translate external payloads or execute provider API calls.

Service
  Orchestrates domain workflows. Services compose repositories, registries,
  adapters, policy, and domain objects. They should not parse raw provider DTOs.

DTO
  A data transfer object at a boundary. DTOs are allowed in clients, adapters,
  translators, and persistence code. DTOs should not leak into domain services,
  policy, or agent graph state.
```

## Naming Rules

- Use `adapter.py` for boundary orchestration around one provider or
  infrastructure concern.
- Use `client.py` for low-level HTTP/API interaction.
- Use `translators.py` for conversion functions at a boundary.
- Use `repositories.py` for persistence access.
- Use `registry.py` for selecting configured connector adapters or installations.
- Avoid new names such as `mapper`, `normalizer`, `converter`, or `builder` for
  boundary translation unless the code has a clearly different job.

## Representation Flow

Inbound channel flow:

```text
Chatwoot webhook DTO
  -> channels/chatwoot/translators.py
  -> NormalizedMessage
  -> application service
  -> agent graph
```

Connector read flow:

```text
WooCommerce API DTO
  -> connectors/woocommerce/translators.py
  -> ProductSnapshot / PriceSnapshot / AvailabilitySnapshot
  -> connector adapter
  -> application service
```

Persistence flow:

```text
database row
  -> persistence/translators.py
  -> domain object
  -> repository caller
```

Outbound channel flow:

```text
OutboundAction
  -> channels/chatwoot/translators.py
  -> Chatwoot create-message DTO
  -> channels/chatwoot/client.py
```

## Rule Of Thumb

DTOs die at adapters. Domain objects cross the core.
