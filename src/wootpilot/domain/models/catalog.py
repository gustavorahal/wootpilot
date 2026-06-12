"""Catalog and product-context domain models.

These models describe what WootPilot knows about products at one point in time.
They are not WooCommerce DTOs and they are not canonical product records owned
by WootPilot. Connector translators turn raw store payloads into these compact,
policy-aware facts before prompts, policy checks, or audit records see them.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RiskSignal(StrEnum):
    """Stable non-policy risk markers carried through triage and context."""

    catalog_load_failed = "catalog.load_failed"
    catalog_no_match = "catalog.no_match"


class Money(BaseModel):
    """Currency amount stored as integer minor units to avoid float drift.

    `Money` is deliberately small: it knows currency, exact minor units, and
    same-currency arithmetic. It does not know about storefront display text,
    tax rules, quote status, WooCommerce product ids, or whether a support agent
    may mention a price. Those policy and source concerns live on
    `PriceSnapshot`.

    Zero is a valid amount. Whether zero means free, included, unavailable, or
    quote-required is not a `Money` decision.
    """

    model_config = ConfigDict(strict=True)

    currency: str = Field(min_length=3, max_length=3)
    minor_units: int

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()

    def display(self, minor_unit: int = 2, symbol: str | None = None) -> str:
        major = self.minor_units / (10**minor_unit)
        prefix = f"{symbol} " if symbol else f"{self.currency} "
        return f"{prefix}{major:,.{minor_unit}f}"

    def __add__(self, other: Money) -> Money:
        self._require_same_currency(other)
        return Money(
            currency=self.currency,
            minor_units=self.minor_units + other.minor_units,
        )

    def __sub__(self, other: Money) -> Money:
        self._require_same_currency(other)
        return Money(
            currency=self.currency,
            minor_units=self.minor_units - other.minor_units,
        )

    @classmethod
    def zero(cls, currency: str) -> Money:
        return cls(currency=currency, minor_units=0)

    def _require_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise ValueError("Money arithmetic requires matching currencies")


class PriceSnapshot(BaseModel):
    """Point-in-time product price facts with policy visibility flags.

    `can_mention` is the key policy boundary: a price may be known internally
    while still being unsafe for a customer-visible model reply because it is
    hidden, stale, quote-only, or otherwise restricted by connector policy.

    `display_text` preserves source wording for audit/operator context, but it
    should not be sent publicly unless `can_mention` is true. Quote-required,
    hidden, stale, unavailable, or ambiguous prices should use flags/reasons
    here rather than pretending there is a safe exact amount.
    """

    model_config = ConfigDict(strict=True)

    amount: Money | None = None
    display_text: str | None = None
    can_mention: bool = False
    quote_required: bool = False
    hidden: bool = False
    stale: bool = False
    reason: str | None = None


class AvailabilitySnapshot(BaseModel):
    """Point-in-time availability facts with public-disclosure constraints.

    Availability is not just inventory quantity. Storefronts can hide counts,
    publish coarse stock labels, or expose stale state. `hidden_quantity` and
    `can_mention` keep the workflow from turning internal or uncertain stock
    facts into overconfident customer-visible claims.
    """

    model_config = ConfigDict(strict=True)

    is_available: bool | None = None
    display_text: str | None = None
    can_mention: bool = False
    hidden_quantity: bool = True
    uncertain_reasons: list[str] = Field(default_factory=list)


class ProductSnapshot(BaseModel):
    """Policy-safe product facts passed to model and deterministic checks.

    This is a normalized observation from a catalog connector, not a canonical
    product entity owned by WootPilot. Keep raw WooCommerce payloads inside
    connector translators. Treat `fitment_hints` as search/context aids, not as
    final compatibility claims.
    """

    model_config = ConfigDict(strict=True)

    product_id: str
    sku: str | None = None
    name: str
    permalink: str | None = None
    categories: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    fitment_hints: list[str] = Field(default_factory=list)
    price: PriceSnapshot
    availability: AvailabilitySnapshot
    risk_signals: list[str] = Field(default_factory=list)


class ProductCategory(BaseModel):
    """Normalized catalog category safe to expose outside connector packages."""

    model_config = ConfigDict(strict=True)

    category_id: str
    name: str
    slug: str | None = None
    parent_id: str | None = None


class ProductSearchQuery(BaseModel):
    """Structured catalog search request shared by connector adapters."""

    model_config = ConfigDict(strict=True)

    query: str
    limit: int = Field(default=5, ge=1, le=50)
    categories: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    fitment_hints: list[str] = Field(default_factory=list)


class CatalogContext(BaseModel):
    """Catalog context attached to one workflow run.

    The `snapshot_id` points at the persisted copy used by audit records. Model
    prompts and policy checks should use this object rather than reaching back
    into a live connector mid-graph.

    This context should contain compact, policy-aware facts the agent actually
    saw. It is not a dumping ground for every raw connector response.
    """

    model_config = ConfigDict(strict=True)

    query: str
    products: list[ProductSnapshot] = Field(default_factory=list)
    risk_signals: list[str] = Field(default_factory=list)
    snapshot_id: str | None = None
