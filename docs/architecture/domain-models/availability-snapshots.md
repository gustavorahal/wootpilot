# Availability Snapshots

`AvailabilitySnapshot` describes a point-in-time observation about whether a
resource can be sold, shipped, reserved, or discussed as available. Availability
is not just a quantity because storefronts often hide counts, use coarse statuses,
or expose stale inventory.

## Shape

```python
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class AvailabilityStatus(StrEnum):
    in_stock = "in_stock"
    low_stock = "low_stock"
    out_of_stock = "out_of_stock"
    backorder = "backorder"
    preorder = "preorder"
    made_to_order = "made_to_order"
    unknown = "unknown"


class AvailabilitySource(StrEnum):
    woocommerce_store_api = "woocommerce_store_api"
    woocommerce_rest_api = "woocommerce_rest_api"
    manual_fixture = "manual_fixture"
    human_entered = "human_entered"
    derived = "derived"


class AvailabilitySnapshot(BaseModel):
    """Policy-aware availability observation captured for support/audit use."""

    model_config = ConfigDict(frozen=True, strict=True)

    status: AvailabilityStatus
    source: AvailabilitySource
    captured_at: datetime
    quantity: int | None = Field(default=None, ge=0)
    quantity_visible: bool = False
    can_mention: bool = False
    mention_policy_reason: str | None = None
    uncertainty_reasons: list[str] = Field(default_factory=list)
```

## Rules

- Use `quantity=None` when the source does not expose a count.
- Do not mention exact quantity unless `quantity_visible=true` and
  `can_mention=true`.
- Treat availability as stale immediately after capture unless the source gives a
  stronger freshness guarantee.
- Prefer public wording such as "I can share the product page" when availability
  is unknown or policy blocks mention.
- Persist the snapshot used by an agent run so audits can explain availability
  claims.
