# Connector Model

WootPilot should use the term **connectors** for external small-business systems
that provide business context or business actions around Chatwoot conversations.
Chatwoot itself should be modeled as a channel because it is the primary support
platform WootPilot is built around.

The connector architecture should be designed for both reads and writes, but the
first WooCommerce implementation should be read-only. Read capabilities provide
normalized resource snapshots. Write capabilities should create proposed
connector actions that pass through policy, audit, and explicit execution before
mutating any external system.

Use `Snapshot` suffixes for normalized external resource data:

```text
ProductSnapshot
OrderSnapshot
CustomerSnapshot
```

These objects represent point-in-time observations from external systems of
record, not canonical entities owned by WootPilot. A product price, stock level,
order status, or customer profile can change after the agent run. Persisting the
compact snapshots used by each run preserves causality for audits and debugging.

Raw connector API payloads should stay inside connector packages. Application
services should consume only normalized snapshots, and agent context should
receive only compact, policy-aware context.

Connector adapters own connector boundaries. Connector clients perform raw API
calls, connector translators convert provider DTOs into domain snapshots, and the
connector registry selects configured adapters/installations. Registries should
not translate provider payloads.

Connector packages should expose resource-oriented capability protocols. Workflow
services compose those resources into support-specific context.

Adapters should present capability protocols to the application layer. Clients
and raw DTOs remain internal to the connector package, and translators are used
inside the adapter to turn provider responses into domain snapshots before
anything crosses into services.

## Capabilities

Initial capability names:

```python
from enum import StrEnum


class ConnectorCapability(StrEnum):
    product_catalog_read = "product_catalog_read"
    order_read = "order_read"
    customer_read = "customer_read"
    order_note_write = "order_note_write"
    order_status_update = "order_status_update"
    refund_create = "refund_create"
    coupon_create = "coupon_create"
    customer_tag_write = "customer_tag_write"
```

Reads can be moderately coarse-grained. `product_catalog_read` covers product
search, category listing, and product lookup for version 1. Writes should be
fine-grained because policy and audit need to know exactly which business
mutation was proposed.

Prefer separate protocols per capability rather than one large connector base
class with many optional methods:

```python
from typing import Protocol


class ProductCatalogConnector(Protocol):
    async def search_products(
        self,
        query: ProductSearchQuery,
    ) -> list[ProductSnapshot]:
        ...

    async def get_product(self, external_product_id: str) -> ProductSnapshot | None:
        ...

    async def get_product_by_sku(self, sku: str) -> ProductSnapshot | None:
        ...

    async def list_categories(self) -> list[ProductCategory]:
        ...
```

Each connector implementation declares supported capabilities. Each
tenant-scoped connector installation declares enabled capabilities. Effective
capabilities are the intersection of:

```text
supported_capabilities
enabled_capabilities
policy_allowed_capabilities
```

## Installation Configuration

Connector configuration should be tenant-scoped from day one, even if version 1
only configures one default tenant operationally. Environment variables may seed
the default tenant connector installation for local development.

Conceptual installation model:

```text
connector_installations
  id
  tenant_id
  connector_key
  display_name
  enabled
  supported_capabilities
  enabled_capabilities
  config_json
  credentials_ref
  created_at
  updated_at
```

Vocabulary:

```text
connector_key
  Stable connector type, such as woocommerce.

connector_installation_id
  Tenant-scoped configured instance, such as demo-store.

display_name
  Human-readable label, such as Demo WooCommerce Store.
```

The model should support multiple installations of the same connector per tenant,
even though version 1 should configure only one WooCommerce installation for the
default tenant. Workflow config should explicitly select which connector
installation a service uses. Avoid automatic "find any connector with this
capability" behavior in the agent path because multi-store and multi-brand
setups can become ambiguous.

Credentials should not live inside `config_json`. Store non-secret settings in
config and use `credentials_ref` for secrets:

```text
config_json
  base_url
  mode
  timeout
  selected_capabilities

credentials_ref
  env:WOOCOMMERCE_DEFAULT
  secret-manager:...
  vault:...
```

For version 1, `credentials_ref` can resolve to environment variables. Later it
can resolve to a proper secret store without changing installation records.

Connector reads should be audited when their data influences an agent decision.
The durable audit trail should preserve context snapshots, not every low-level
HTTP request. Connector writes should be represented as proposed connector
actions, then validated, executed, and audited through a shared action pipeline.
Chatwoot outbound messages and connector business mutations should use the same
guardrail philosophy but separate persistence tables.

## WooCommerce Connector

WootPilot should support WooCommerce as the first business-context connector.

The first implementation should include two modes behind the same
`ProductCatalogConnector` capability:

```text
mock
  Reads data/mock-woocommerce/catalog.demo-car-parts.json.

store_api
  Reads public WooCommerce Store API endpoints such as:
  /wp-json/wc/store/v1/products
  /wp-json/wc/store/v1/products/categories
```

Do not implement authenticated WooCommerce REST API support in version 1. The
connector interfaces should leave room for authenticated capabilities such as
`order_read`, `customer_read`, `order_note_write`, `refund_create`, and
`coupon_create`, but those capabilities should remain disabled and unimplemented
initially.

The planned local fixture path is:

```text
data/mock-woocommerce/catalog.demo-car-parts.json
```

It contains:

- A fictional car-parts product catalog;
- Products clearly marked as demo data;
- 3 categories;
- product types covering TBI, kits, modules, harnesses, sensors, ignition, fuel,
  and addons.

The public repository should not include client-specific product data, source
paths, or real storefront URLs. Demo fixtures should be fictionalized before
being committed.

### Product Catalog Capability

`RunSupportWorkflow` should depend on `CatalogContextService`, not directly on
WooCommerce or connector discovery. `CatalogContextService` should use the
connector registry to resolve the tenant's configured product catalog adapter
before the graph is invoked.

```python
catalog_adapter = registry.require_capability(
    tenant_id=tenant_id,
    connector_installation_id=workflow_config.catalog_connector_installation_id,
    capability=ConnectorCapability.product_catalog_read,
)
```

The WooCommerce connector adapter should use translators to convert raw
WooCommerce payloads into shared domain resource snapshots such as
[ProductSnapshot](domain-models/product-snapshots.md) and `ProductCategory`.
Services and graph nodes must not receive raw WooCommerce API responses.

### Product Context Shape

The LLM should not receive raw WooCommerce API responses. A
`CatalogContextService` should convert adapter results into compact,
policy-aware structured context before `RunSupportWorkflow` invokes the graph.

```json
{
  "generatedAt": "2026-06-07T00:00:00Z",
  "query": "tbi 60 ford",
  "candidateProducts": [
    {
      "id": "1399",
      "name": "TBI 60mm FORD",
      "sku": "TBIFORD60",
      "productType": "tbi",
      "publicUrl": "https://example-store.test/products/tbi-60mm-ford",
      "price": {
        "kind": "exact",
        "source": "woocommerce_store_api",
        "capturedAt": "2026-06-07T00:00:00Z",
        "money": {
          "amountMinor": 358000,
          "currency": "BRL",
          "decimalPlaces": 2
        },
        "rangeMin": null,
        "rangeMax": null,
        "displayText": "R$ 3.580,00",
        "taxInclusive": null,
        "priceListId": null,
        "canMention": true,
        "mentionPolicyReason": null
      },
      "availability": {
        "status": "in_stock",
        "source": "woocommerce_store_api",
        "capturedAt": "2026-06-07T00:00:00Z",
        "quantity": 5,
        "quantityVisible": true,
        "canMention": true,
        "mentionPolicyReason": null,
        "uncertaintyReasons": []
      },
      "fitmentHints": ["Maverick", "Galaxie", "Landau", "F100", "Mustang"],
      "riskSignals": ["compatibility_requires_human_review"]
    }
  ],
  "missingInformation": [],
  "riskSignals": ["compatibility_requires_human_review"]
}
```

`price` must be a serialized [PriceSnapshot](domain-models/price-snapshots.md),
not a float, a bare decimal, or a raw `Money` value. `availability` must be a
serialized [AvailabilitySnapshot](domain-models/availability-snapshots.md).
`Money` carries the exact amount and currency; `PriceSnapshot` carries quote
status, source, display text, capture time, and whether policy allows the price
to be mentioned.

### WooCommerce Policy Rules

WooCommerce context should exercise the same safety rules expected from a real
support deployment.

- The agent may send a public product name and public URL for a single safe
  product match.
- The agent may mention price only when `price.canMention=true`.
- The agent may mention availability only when `availability.canMention=true`.
- Kit products, quote placeholders, hidden-price products, or any price snapshot
  with `kind=quote_required` must never be described as free.
- Fitment hints are search aids, not final compatibility claims.
- Any final kit composition, installation promise, warranty claim, or
  performance claim requires human review.
- Multiple product candidates should produce a private note or a public
  clarifying question, depending on bot mode.
