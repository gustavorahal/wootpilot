"""Mock WooCommerce catalog adapter used for deterministic local context."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from wootpilot.domain.models import (
    AvailabilitySnapshot,
    Money,
    PriceSnapshot,
    ProductCategory,
    ProductSearchQuery,
    ProductSnapshot,
    StructuredCatalogContext,
)
from wootpilot.text import searchable_text

__all__ = ["MockCatalog"]


class MockCatalog:
    """Searches the committed WooCommerce Store API fixture without network access."""

    def __init__(self, path: Path) -> None:
        """Load the fixture once so searches are deterministic and cheap."""

        self.path = path
        self.data = json.loads(path.read_text(encoding="utf-8"))
        self.products: list[dict[str, Any]] = list(self.data.get("products", []))

    async def search(self, query: str, limit: int = 5) -> StructuredCatalogContext:
        """Return fixture-backed catalog context for a free-text query."""

        return self.search_sync(query=query, limit=limit)

    async def search_products(self, query: ProductSearchQuery) -> list[ProductSnapshot]:
        """Return fixture products matching structured query filters."""

        return self._search_products(query)[: query.limit]

    async def get_product(self, external_product_id: str) -> ProductSnapshot | None:
        """Return one fixture product by external id, if present."""

        for product in self.products:
            if str(product.get("id")) == external_product_id:
                return self._snapshot(product)
        return None

    async def get_product_by_sku(self, sku: str) -> ProductSnapshot | None:
        """Return one fixture product by case-insensitive SKU, if present."""

        normalized = sku.casefold()
        for product in self.products:
            if str(product.get("sku") or "").casefold() == normalized:
                return self._snapshot(product)
        return None

    async def list_categories(self) -> list[ProductCategory]:
        """Return unique fixture categories sorted for stable UI/tool output."""

        categories: dict[str, ProductCategory] = {}
        for product in self.products:
            for item in product.get("categories", []) or []:
                category = self._category(item)
                categories[category.category_id] = category
        return sorted(categories.values(), key=lambda item: item.name.casefold())

    def search_sync(self, query: str, limit: int = 5) -> StructuredCatalogContext:
        """Synchronous search helper used by tests and the async adapter method."""

        products = self._search_products(ProductSearchQuery(query=query, limit=limit))
        risks = ["catalog.no_match"] if not products and query.strip() else []
        return StructuredCatalogContext(
            query=query, products=products, risk_signals=risks
        )

    def _search_products(self, query: ProductSearchQuery) -> list[ProductSnapshot]:
        normalized_terms = [
            term
            for term in searchable_text(query.query).replace("-", " ").split()
            if term
        ]
        scored: list[tuple[int, dict[str, Any]]] = []
        for product in self.products:
            if not self._matches_structured_filters(product, query):
                continue
            haystack = self._search_text(product)
            score = sum(1 for term in normalized_terms if term in haystack)
            if score or not normalized_terms:
                scored.append((score, product))
        scored.sort(key=lambda item: (-item[0], str(item[1].get("name", ""))))
        return [self._snapshot(product) for _, product in scored]

    def _matches_structured_filters(
        self,
        product: dict[str, Any],
        query: ProductSearchQuery,
    ) -> bool:
        category_text = self._taxonomy_text(product, "categories")
        tag_text = self._taxonomy_text(product, "tags")
        search_text = self._search_text(product)
        return (
            _all_terms_match(query.categories, category_text)
            and _all_terms_match(query.tags, tag_text)
            and _all_terms_match(query.fitment_hints, search_text)
        )

    def _taxonomy_text(self, product: dict[str, Any], key: str) -> str:
        parts: list[str] = []
        for item in product.get(key, []) or []:
            parts.extend(
                str(value) for value in (item.get("name"), item.get("slug")) if value
            )
        return searchable_text(" ".join(parts))

    def _search_text(self, product: dict[str, Any]) -> str:
        parts = [
            product.get("name"),
            product.get("sku"),
            product.get("slug"),
            product.get("descriptionText"),
            product.get("shortDescriptionText"),
        ]
        for collection in ("categories", "tags"):
            for item in product.get(collection, []) or []:
                parts.extend([item.get("name"), item.get("slug")])
        client = product.get("clientFacing") or {}
        parts.append(json.dumps(client.get("fitment") or {}, ensure_ascii=False))
        return searchable_text(" ".join(str(part) for part in parts if part))

    def _snapshot(self, product: dict[str, Any]) -> ProductSnapshot:
        prices = product.get("prices") or {}
        currency = str(prices.get("currency") or "BRL").upper()
        minor_unit = int(prices.get("minorUnit") or 2)
        raw_amount = prices.get("price")
        amount = (
            Money(currency=currency, minor_units=int(raw_amount))
            if raw_amount
            else None
        )
        is_in_stock = bool(product.get("isInStock"))
        price = PriceSnapshot(
            amount=amount,
            display_text=product.get("priceHtml")
            or (amount.display(minor_unit) if amount else None),
            can_mention=amount is not None and is_in_stock,
            quote_required=False,
            hidden=amount is None,
            reason=None if amount is not None else "catalog.price_missing",
        )
        availability = AvailabilitySnapshot(
            is_available=is_in_stock,
            display_text=str(product.get("stockAvailability") or ""),
            can_mention=True,
            hidden_quantity=False,
            uncertain_reasons=[] if is_in_stock else ["catalog.out_of_stock"],
        )
        return ProductSnapshot(
            product_id=str(product.get("id")),
            sku=str(product.get("sku") or "") or None,
            name=str(product.get("name") or ""),
            permalink=product.get("permalink"),
            categories=[
                str(item.get("name"))
                for item in product.get("categories", []) or []
                if item.get("name")
            ],
            tags=[
                str(item.get("name"))
                for item in product.get("tags", []) or []
                if item.get("name")
            ],
            fitment_hints=self._fitment_hints(product),
            price=price,
            availability=availability,
            risk_signals=[] if is_in_stock else ["catalog.out_of_stock"],
        )

    def _category(self, item: dict[str, Any]) -> ProductCategory:
        category_id = str(item.get("id") or item.get("slug") or item.get("name"))
        return ProductCategory(
            category_id=category_id,
            name=str(item.get("name") or item.get("slug") or category_id),
            slug=str(item.get("slug")) if item.get("slug") else None,
            parent_id=str(item.get("parent")) if item.get("parent") else None,
        )

    def _fitment_hints(self, product: dict[str, Any]) -> list[str]:
        client = product.get("clientFacing") or {}
        fitment = client.get("fitment") or {}
        hints: list[str] = []
        if isinstance(fitment, dict):
            for value in fitment.values():
                if isinstance(value, str):
                    hints.append(value)
                elif isinstance(value, list):
                    hints.extend(str(item) for item in value)
        return hints[:8]


def _all_terms_match(terms: list[str], haystack: str) -> bool:
    return all(searchable_text(term) in haystack for term in terms)
