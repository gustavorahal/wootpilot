# Connector Model

WootPilot uses **connectors** for external business systems that provide context
around a Chatwoot conversation. Chatwoot itself is not modeled as a connector; it
is the primary support channel.

The current connector implementation is product-catalog read only. It gives the
support workflow compact product context for customer questions such as parts,
availability, pricing, and fitment.

## Current Catalog Boundary

The application depends on the `ProductCatalogConnector` protocol in
[`src/wootpilot/domain/ports.py`](../../src/wootpilot/domain/ports.py). The
runtime connector is selected by
[`catalog_connector_from_settings`](../../src/wootpilot/catalog/factory.py).

Supported modes:

```text
mock
  Reads data/mock-woocommerce/catalog.demo-car-parts.json.

store_api
  Reads public WooCommerce Store API product endpoints.
```

Both modes return WootPilot-owned domain snapshots instead of raw provider
payloads. `RunSupportWorkflow` calls the selected catalog connector before the
graph is invoked, stores the resulting context snapshot, and passes the compact
context into the graph state.

## Snapshot Vocabulary

Catalog domain models live in
[`src/wootpilot/domain/models/catalog.py`](../../src/wootpilot/domain/models/catalog.py).
The important distinction is that WootPilot stores **snapshots**, not canonical
commerce entities.

```text
ProductSnapshot
  Point-in-time product observation from the configured catalog source.

ProductCategory
  Category or grouping information from the catalog source.

PriceSnapshot
  Price observation plus policy metadata that says whether the model may mention
  the price to the customer.

AvailabilitySnapshot
  Stock observation plus policy metadata that says whether the model may mention
  availability or quantity.

CatalogContext
  The compact, policy-aware context used by a single workflow run.
```

Snapshots preserve causality. If a price, stock level, or product page changes
after a reply was generated, the audit trail still records what WootPilot saw at
decision time.

## Mock Catalog

The committed mock fixture is:

```text
data/mock-woocommerce/catalog.demo-car-parts.json
```

It contains fictionalized demo car-parts data with categories, tags, stock
status, prices, kits, product URLs, and WooCommerce-like fields. This is the
default local and test catalog source.

## WooCommerce Store API

`CATALOG_CONNECTOR_MODE=store_api` enables public WooCommerce Store API reads
using `WOOCOMMERCE_STORE_API_BASE_URL`.

The implementation reads public product data. It does not currently implement
authenticated WooCommerce REST API operations such as order lookup, customer
lookup, refunds, coupons, or order notes.

## Design Rules In Current Code

Raw connector payloads stay inside connector code. Application services consume
domain snapshots, and graph nodes consume compact catalog context.

Connector reads are represented in audit records through `context_snapshots`.
The audit trail records the product context that influenced the workflow rather
than every low-level HTTP request.

There is no persisted connector installation registry in the current schema.
The active catalog source is selected from environment-backed settings.
