# Slice 8: WooCommerce Store API

## Running Outcome

- WootPilot can use either the mock catalog or the public WooCommerce Store API
  for read-only product context.

## Implementation Scope

- Add WooCommerce connector `store_api` mode for public Store API product and
  category reads.
- Map Store API product/category responses into domain snapshots.
- Keep authenticated WooCommerce REST API support out of the MVP.
- Keep context structured before adding vector retrieval.

## Required Tests

- WooCommerce Store API product and category mapping works with recorded
  fixtures.
- `mock` and `store_api` modes satisfy the same `ProductCatalogConnector`
  contract.
- Store API failures produce controlled context-loading failures.
- Product lookup persists the exact policy-aware context used by the agent run.
- Ambiguous product match produces a clarifying question or private note.
- Kit price `0.00` handling does not describe quote placeholders as free.
- Availability claim gating behaves consistently.
- Price and availability mention policies behave the same for mock and Store API
  modes.
- Exact public Store API prices become mentionable by default when the product
  is a single safe match and the price is fresh.

## Manual Verification

- Run product lookup against mock mode.
- Run the same lookup against recorded Store API fixtures.
- Confirm both modes produce the same structured context shape.
- Confirm a safe exact-price product lookup allows the public reply policy to
  include the displayed price.
