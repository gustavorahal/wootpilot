from __future__ import annotations

from wootpilot.domain.models import (
    AvailabilitySnapshot,
    Money,
    PriceSnapshot,
    ProductSnapshot,
    StructuredCatalogContext,
)
from wootpilot.integrations.model import catalog_products_for_prompt


def test_catalog_products_for_prompt_redacts_non_mentionable_prices() -> None:
    context = StructuredCatalogContext(
        query="price",
        products=[
            _product(
                name="Safe Product",
                price=PriceSnapshot(
                    amount=Money(currency="BRL", minor_units=350000),
                    display_text="R$ 3.500,00",
                    can_mention=True,
                ),
            ),
            _product(
                name="Hidden Product",
                price=PriceSnapshot(
                    display_text="R$ 999,00",
                    can_mention=False,
                    hidden=True,
                    reason="catalog.price_hidden",
                ),
            ),
            _product(
                name="Quote Product",
                price=PriceSnapshot(
                    display_text="R$ 0,00",
                    can_mention=False,
                    quote_required=True,
                    reason="catalog.quote_required_placeholder",
                ),
            ),
        ],
    )

    rows = catalog_products_for_prompt(context)

    assert rows[0]["price"] == "R$ 3.500,00"
    assert rows[0]["pricePolicy"] == "mention_allowed"
    assert rows[1]["price"] is None
    assert rows[1]["pricePolicy"] == "do_not_mention_exact_price"
    assert rows[2]["price"] is None
    assert rows[2]["pricePolicy"] == "do_not_mention_exact_price"
    assert "999" not in str(rows)
    assert "0,00" not in str(rows[2])


def _product(*, name: str, price: PriceSnapshot) -> ProductSnapshot:
    return ProductSnapshot(
        product_id=name.lower().replace(" ", "-"),
        name=name,
        price=price,
        availability=AvailabilitySnapshot(
            is_available=True,
            display_text="In stock",
            can_mention=True,
            hidden_quantity=False,
        ),
    )
