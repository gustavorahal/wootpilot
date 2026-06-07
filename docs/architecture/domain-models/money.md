# Money

`Money` is a small immutable value object for monetary arithmetic and equality.
It should not know about WooCommerce, storefront display text, support policy,
tax rules, quote status, or whether an agent may mention a price to a customer.
Those concerns belong to [Price Snapshots](price-snapshots.md).

The core responsibility of `Money` is to make invalid monetary arithmetic hard:

- Store amounts in integer minor units.
- Carry currency with every amount.
- Reject floats at the domain boundary.
- Allow arithmetic only within the same currency.
- Return new values instead of mutating existing values.

## Shape

```python
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Money(BaseModel):
    """Immutable monetary value stored in minor units.

    `amount_minor` is the only arithmetic representation. `decimal_places`
    describes how to interpret that integer for display and parsing, but display
    formatting itself belongs outside this value object.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    amount_minor: int
    currency: str = Field(min_length=3, max_length=3, description="ISO 4217 code")
    decimal_places: int = Field(default=2, ge=0, le=6)

    @classmethod
    def from_major(
        cls,
        amount: Decimal | str,
        currency: str,
        *,
        decimal_places: int = 2,
    ) -> Self:
        """Create money from a major-unit decimal value such as '10.25'."""

        if isinstance(amount, float):
            msg = "Money.from_major does not accept float"
            raise ValueError(msg)
        if not isinstance(amount, Decimal):
            try:
                amount = Decimal(amount)
            except InvalidOperation as exc:
                msg = f"Invalid monetary amount: {amount!r}"
                raise ValueError(msg) from exc
        if not amount.is_finite():
            msg = f"Invalid monetary amount: {amount!r}"
            raise ValueError(msg)

        scale = Decimal(10) ** decimal_places
        minor = amount * scale
        rounded_minor = minor.to_integral_value(rounding=ROUND_HALF_UP)
        if minor != rounded_minor:
            msg = f"Amount must have at most {decimal_places} decimal places"
            raise ValueError(msg)
        return cls(
            amount_minor=int(rounded_minor),
            currency=currency,
            decimal_places=decimal_places,
        )

    @classmethod
    def from_minor(
        cls,
        amount_minor: int,
        currency: str,
        *,
        decimal_places: int = 2,
    ) -> Self:
        """Create money from already-normalized minor units."""

        return cls(
            amount_minor=amount_minor,
            currency=currency,
            decimal_places=decimal_places,
        )

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def validate_currency_scale(self) -> Self:
        if not self.currency.isalpha():
            msg = "Currency must use alphabetic ISO 4217 code characters"
            raise ValueError(msg)
        return self

    def to_major(self) -> Decimal:
        scale = Decimal(10) ** self.decimal_places
        return Decimal(self.amount_minor) / scale

    def plus(self, other: Self) -> Self:
        self._assert_same_currency_and_scale(other)
        return type(self).from_minor(
            self.amount_minor + other.amount_minor,
            self.currency,
            decimal_places=self.decimal_places,
        )

    def minus(self, other: Self) -> Self:
        self._assert_same_currency_and_scale(other)
        return type(self).from_minor(
            self.amount_minor - other.amount_minor,
            self.currency,
            decimal_places=self.decimal_places,
        )

    def negate(self) -> Self:
        return type(self).from_minor(
            -self.amount_minor,
            self.currency,
            decimal_places=self.decimal_places,
        )

    def is_zero(self) -> bool:
        return self.amount_minor == 0

    def _assert_same_currency_and_scale(self, other: Self) -> None:
        if self.currency != other.currency:
            msg = "Currency mismatch"
            raise ValueError(msg)
        if self.decimal_places != other.decimal_places:
            msg = "Currency scale mismatch"
            raise ValueError(msg)
```

## Rules

- Do not store money as `float`.
- Do not use `Decimal` as the main stored representation. Use it at boundaries
  for parsing and converting major-unit values.
- Keep `Money` free of vendor fields such as WooCommerce mode, product id,
  storefront display text, and API source.
- Keep `Money` free of support policy fields such as `can_mention`.
- Allow negative values because refunds, credits, adjustments, and ledger entries
  may need them.
- Treat zero as a valid amount. Whether zero means free, unavailable, included,
  or quote-required is not a `Money` decision.
- Require same currency and same decimal scale for arithmetic.

## JSON Shape

Serialized `Money` should be boring and lossless:

```json
{
  "amountMinor": 358000,
  "currency": "BRL",
  "decimalPlaces": 2
}
```

Any additional meaning around that amount belongs on a separate object.
