# Product Snapshots

`ProductSnapshot` is a point-in-time observation of a product from an external
catalog. It is not a canonical product entity owned by WootPilot.

Product snapshots should preserve enough normalized product context for support
workflows while keeping raw connector payloads inside connector packages.

## Shape

```python
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from wootpilot.domain.availability_snapshots import AvailabilitySnapshot
from wootpilot.domain.price_snapshots import PriceSnapshot
from wootpilot.domain.risk_signals import RiskSignal


class ProductSource(StrEnum):
    woocommerce_store_api = "woocommerce_store_api"
    woocommerce_rest_api = "woocommerce_rest_api"
    manual_fixture = "manual_fixture"


class ProductCategory(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    external_id: str
    name: str
    slug: str | None = None


class ProductSnapshot(BaseModel):
    """Normalized product observation used by support workflows."""

    model_config = ConfigDict(frozen=True, strict=True)

    external_product_id: str
    source: ProductSource
    captured_at: datetime
    name: str
    sku: str | None = None
    product_type: str | None = None
    public_url: str | None = None
    categories: list[ProductCategory] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    fitment_hints: list[str] = Field(default_factory=list)
    price: PriceSnapshot | None = None
    availability: AvailabilitySnapshot | None = None
    risk_signals: list[RiskSignal] = Field(default_factory=list)
```

## Rules

- Keep raw WooCommerce payloads out of `ProductSnapshot`.
- Treat fitment hints as search aids, not final compatibility claims.
- Use `PriceSnapshot` for pricing semantics and policy.
- Use `AvailabilitySnapshot` for stock semantics and policy.
- Persist the product snapshot used by an agent run when product facts influence
  the proposal.
- Do not merge snapshots from different capture times into a fake canonical
  product.
