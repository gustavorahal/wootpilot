# Slice 3: Mock Product Context

## Running Outcome

- Given a normalized customer message, WootPilot can load policy-aware product
  context from the local mock WooCommerce catalog and persist the exact context
  used by the run.

## Implementation Scope

- Add `Money`, `PriceSnapshot`, `AvailabilitySnapshot`, `ProductSnapshot`,
  `ProductCategory`, `ProductSearchQuery`, and `StructuredCatalogContext`.
- Add connector capability enums and `ProductCatalogConnector` protocol using
  `product_catalog_read`.
- Add connector installation config model and registry for selecting configured
  connector adapters.
- Add WooCommerce connector `mock` mode.
- Load and validate `data/mock-woocommerce/catalog.demo-car-parts.json`.
- Use the committed mock catalog as the canonical fixture for products,
  categories, tags, stock status, prices, kits, and WooCommerce Store API
  response fields needed by translators.
- Add search by name, SKU, category, tags, and fitment hints.
- Add `CatalogContextService`.
- Persist compact context snapshots before invoking the graph.
- Keep lookup deterministic and local: no embeddings, no fuzzy vector search, no
  network access, and no authenticated WooCommerce API calls.

## Required Tests

- Mock catalog fixture loads and validates.
- Mock WooCommerce product search works by name, SKU, category, tags, and
  fitment hints.
- Money model validates currency normalization, same-currency arithmetic, and
  zero-value handling.
- Money and price snapshots reject floats and preserve integer minor units.
- Price snapshot validates quote-required semantics, hidden prices, display text,
  and mention permissions.
- Exact public WooCommerce prices are mentionable by default when fresh and not
  hidden, quote-required, unavailable, or ambiguous.
- Availability snapshot validates hidden quantities, mention permissions, and
  uncertainty reasons.
- Product snapshot composes price, availability, fitment hints, and risk signals.
- Connector registry resolves configured adapters by capability.
- Connector installation effective capability calculation is deterministic.
- Catalog context persists snapshot ids that can be linked to an agent run.
- No raw WooCommerce payload crosses into service or graph inputs.
- Context building returns a compact, policy-aware shape that is stable across
  repeated fixture runs.

## Manual Verification

- Run a local product-context command or test endpoint against the mock catalog.
- Search for products by name, SKU, and fitment hints.
- Inspect the persisted context snapshot for policy-aware price and availability
  fields.
