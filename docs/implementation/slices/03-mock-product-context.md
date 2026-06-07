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
- Add search by name, SKU, category, tags, and fitment hints.
- Add `CatalogContextService`.
- Persist compact context snapshots before invoking the graph.

## Required Tests

- Mock catalog fixture loads and validates.
- Mock WooCommerce product search works by name, SKU, category, tags, and
  fitment hints.
- Money model validates currency normalization, same-currency arithmetic, and
  zero-value handling.
- Money and price snapshots reject floats and preserve integer minor units.
- Price snapshot validates quote-required semantics, hidden prices, display text,
  and mention permissions.
- Availability snapshot validates hidden quantities, mention permissions, and
  uncertainty reasons.
- Product snapshot composes price, availability, fitment hints, and risk signals.
- Connector registry resolves configured adapters by capability.
- Connector installation effective capability calculation is deterministic.
- Catalog context persists snapshot ids that can be linked to an agent run.
- No raw WooCommerce payload crosses into service or graph inputs.

## Manual Verification

- Run a local product-context command or test endpoint against the mock catalog.
- Search for products by name, SKU, and fitment hints.
- Inspect the persisted context snapshot for policy-aware price and availability
  fields.
