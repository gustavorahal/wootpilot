# Price Snapshots

`PriceSnapshot` describes a point-in-time observed or derived price. It wraps
`Money` with the business context needed for catalog support, policy decisions,
and audits.

Use `PriceSnapshot` when WootPilot needs to know what a source said about a
price, how trustworthy or current that observation is, and whether support policy
allows the agent to mention it.

## Shape

```python
from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from wootpilot.domain.money import Money


class PriceKind(StrEnum):
    exact = "exact"
    estimate = "estimate"
    starts_at = "starts_at"
    range = "range"
    quote_required = "quote_required"
    unavailable = "unavailable"


class PriceSource(StrEnum):
    woocommerce_store_api = "woocommerce_store_api"
    woocommerce_rest_api = "woocommerce_rest_api"
    manual_fixture = "manual_fixture"
    human_entered = "human_entered"
    derived = "derived"


class PriceSnapshot(BaseModel):
    """Policy-aware price observation captured for support/audit use.

    `money` may be absent when a product is quote-only, hidden-price, or
    unavailable. `display_text` preserves source presentation for audit and
    operator notes, but policy still decides whether it can be sent publicly.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    kind: PriceKind
    source: PriceSource
    captured_at: datetime
    money: Money | None = None
    range_min: Money | None = None
    range_max: Money | None = None
    display_text: str | None = None
    tax_inclusive: bool | None = None
    price_list_id: str | None = None
    can_mention: bool = False
    mention_policy_reason: str | None = None

    @model_validator(mode="after")
    def validate_price_shape(self) -> Self:
        if self.kind is PriceKind.exact and self.money is None:
            msg = "exact price snapshots require money"
            raise ValueError(msg)
        if self.kind is PriceKind.range:
            if self.range_min is None or self.range_max is None:
                msg = "range price snapshots require range_min and range_max"
                raise ValueError(msg)
            if self.range_min.currency != self.range_max.currency:
                msg = "price range currency mismatch"
                raise ValueError(msg)
            if self.range_min.decimal_places != self.range_max.decimal_places:
                msg = "price range scale mismatch"
                raise ValueError(msg)
        if self.kind in {PriceKind.quote_required, PriceKind.unavailable} and self.can_mention:
            msg = "quote-required or unavailable prices cannot be mentioned as prices"
            raise ValueError(msg)
        return self
```

## Rules

- `PriceSnapshot` may reference WooCommerce or other source systems. `Money` may
  not.
- Use `kind=quote_required` for quote, composition, kit, or hidden-price
  placeholders. These must never be described as free.
- Use `money=None` when the source did not provide a concrete amount.
- Use `range_min` and `range_max` for price ranges. Both values must use the same
  currency and decimal scale.
- Preserve `display_text` when useful, but do not send it to a customer unless
  `can_mention=true`.
- WooCommerce translators should set `can_mention=true` by default for fresh
  exact public prices unless the product is hidden-price, quote-required,
  unavailable, stale, ambiguous, or blocked by tenant policy.
- Persist the `PriceSnapshot` used by the agent run so later audits can explain
  why a price was or was not mentioned.
- Do not infer currency from locale, tenant, or storefront URL at the point of
  model prompting. Resolve currency before building the snapshot.
- Treat `Money.from_minor(0, currency)` as a valid amount only when
  `kind=exact`. Zero-valued quote placeholders should be represented as
  `kind=quote_required` with `money=None`.

## JSON Shape

```json
{
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
}
```
