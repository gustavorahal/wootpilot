"""WooCommerce public Store API catalog adapter.

The Store API is used read-only and without WooCommerce admin credentials. It
gives WootPilot a realistic catalog source while preserving the same
policy-aware `StructuredCatalogContext` shape used by the mock adapter.
"""

from __future__ import annotations

import html
import logging
import re
import time
from typing import Any

import httpx

from wootpilot.application.errors import ExternalServiceError
from wootpilot.domain.models import (
    AvailabilitySnapshot,
    Money,
    PriceSnapshot,
    ProductCategory,
    ProductSearchQuery,
    ProductSnapshot,
    RiskSignal,
    StructuredCatalogContext,
)
from wootpilot.observability import log_event

logger = logging.getLogger(__name__)

__all__ = [
    "CatalogContextError",
    "StoreApiCatalog",
    "store_api_category_to_snapshot",
    "store_api_product_to_snapshot",
]


class CatalogContextError(ExternalServiceError):
    """Controlled failure raised when a catalog connector cannot load context."""

    def __init__(self, code: str = "woocommerce_store_api_context_failed") -> None:
        super().__init__(
            code,
            operation="catalog_context",
            retryable=True,
            status_code=None,
        )


class StoreApiCatalog:
    """Searches WooCommerce's public `/wc/store/v1/products` endpoint."""

    def __init__(
        self,
        *,
        base_url: str,
        client: httpx.AsyncClient | None = None,
    ):
        """Create a read-only Store API adapter.

        Args:
            base_url: WooCommerce site origin without the Store API path.
            client: Optional HTTP client supplied by tests or shared callers.
        """

        self.base_url = base_url.rstrip("/")
        self.client = client

    async def search(self, query: str, limit: int = 5) -> StructuredCatalogContext:
        """Return policy-aware catalog context for a customer text query.

        Raises:
            CatalogContextError: If WooCommerce cannot be reached or returns an
                invalid Store API response.
        """

        try:
            products = await self._get_products(
                query=query,
                limit=limit,
                capability="product_search",
            )
        except (httpx.HTTPError, ValueError) as exc:
            raise CatalogContextError() from exc
        snapshots = [store_api_product_to_snapshot(product) for product in products]
        risks = (
            [RiskSignal.catalog_no_match.value]
            if query.strip() and not snapshots
            else []
        )
        return StructuredCatalogContext(
            query=query,
            products=snapshots,
            risk_signals=risks,
        )

    async def search_products(self, query: ProductSearchQuery) -> list[ProductSnapshot]:
        """Search Store API products with structured filters applied locally.

        Raises:
            CatalogContextError: If WooCommerce cannot be reached or returns an
                invalid Store API response.
        """

        try:
            products = await self._get_products(
                query=query.query,
                limit=query.limit,
                capability="product_search",
                extra=_store_api_filter_params(query),
            )
        except (httpx.HTTPError, ValueError) as exc:
            raise CatalogContextError() from exc
        snapshots = [store_api_product_to_snapshot(product) for product in products]
        return [
            snapshot
            for snapshot in snapshots
            if _snapshot_matches_structured_filters(snapshot, query)
        ][: query.limit]

    async def get_product(self, external_product_id: str) -> ProductSnapshot | None:
        """Return one product by Store API id, or `None` for a 404."""

        try:
            product = await self._get_product(external_product_id)
        except CatalogContextError:
            raise
        if product is None:
            return None
        return store_api_product_to_snapshot(product)

    async def get_product_by_sku(self, sku: str) -> ProductSnapshot | None:
        """Return one product by exact case-insensitive SKU, if WooCommerce finds it."""

        try:
            products = await self._get_products(
                query="",
                limit=10,
                capability="product_lookup",
                extra={"sku": sku},
            )
        except (httpx.HTTPError, ValueError) as exc:
            raise CatalogContextError() from exc
        for product in products:
            if str(product.get("sku") or "").casefold() == sku.casefold():
                return store_api_product_to_snapshot(product)
        return None

    async def list_categories(self) -> list[ProductCategory]:
        """Return normalized Store API product categories."""

        try:
            categories = await self._get_categories()
        except (httpx.HTTPError, ValueError) as exc:
            raise CatalogContextError() from exc
        return [store_api_category_to_snapshot(item) for item in categories]

    async def _get_products(
        self,
        *,
        query: str,
        limit: int,
        capability: str,
        extra: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        url = f"{self.base_url}/wp-json/wc/store/v1/products"
        params = {"search": query, "per_page": str(limit)}
        if extra:
            params.update(extra)
        return await self._get_collection(
            url=url,
            params=params,
            capability=capability,
        )

    async def _get_product(self, external_product_id: str) -> dict[str, Any] | None:
        url = f"{self.base_url}/wp-json/wc/store/v1/products/{external_product_id}"
        try:
            return await self._get_object(
                url=url,
                params={},
                capability="product_lookup",
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise CatalogContextError() from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise CatalogContextError() from exc

    async def _get_categories(self) -> list[dict[str, Any]]:
        url = f"{self.base_url}/wp-json/wc/store/v1/products/categories"
        return await self._get_collection(
            url=url,
            params={},
            capability="product_categories",
        )

    async def _get_collection(
        self,
        *,
        url: str,
        params: dict[str, str],
        capability: str,
    ) -> list[dict[str, Any]]:
        status_code: int | None = None
        latency_ms = 0
        try:
            response, status_code, latency_ms = await self._get_response(
                url=url, params=params
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, list):
                raise ValueError(
                    "WooCommerce Store API products response must be a list"
                )
            products = [item for item in data if isinstance(item, dict)]
            self._log_store_api_call(
                capability=capability,
                status="success",
                status_code=status_code,
                latency_ms=latency_ms,
                result_count=len(products),
            )
            return products
        except (httpx.HTTPError, ValueError):
            self._log_store_api_call(
                capability=capability,
                status="failed",
                status_code=status_code,
                latency_ms=latency_ms,
                result_count=None,
                level=logging.WARNING,
            )
            raise

    async def _get_object(
        self,
        *,
        url: str,
        params: dict[str, str],
        capability: str,
    ) -> dict[str, Any]:
        status_code: int | None = None
        latency_ms = 0
        try:
            response, status_code, latency_ms = await self._get_response(
                url=url, params=params
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("WooCommerce Store API object response must be a dict")
            self._log_store_api_call(
                capability=capability,
                status="success",
                status_code=status_code,
                latency_ms=latency_ms,
                result_count=1,
            )
            return data
        except (httpx.HTTPError, ValueError):
            self._log_store_api_call(
                capability=capability,
                status="failed",
                status_code=status_code,
                latency_ms=latency_ms,
                result_count=None,
                level=logging.WARNING,
            )
            raise

    async def _get_response(
        self,
        *,
        url: str,
        params: dict[str, str],
    ) -> tuple[httpx.Response, int, int]:
        started = time.perf_counter()
        if self.client:
            response = await self.client.get(url, params=params)
        else:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get(url, params=params)
        return (
            response,
            response.status_code,
            round((time.perf_counter() - started) * 1000),
        )

    def _log_store_api_call(
        self,
        *,
        capability: str,
        status: str,
        status_code: int | None,
        latency_ms: int,
        result_count: int | None,
        level: int = logging.INFO,
    ) -> None:
        log_event(
            logger,
            "catalog_connector_read_completed",
            level=level,
            connector="woocommerce_store_api",
            capability=capability,
            status=status,
            status_code=status_code,
            latency_ms=latency_ms,
            result_count=result_count,
        )


def store_api_product_to_snapshot(product: dict[str, Any]) -> ProductSnapshot:
    """Map a Store API product payload into WootPilot's policy-aware snapshot."""

    prices = product.get("prices") or {}
    currency = str(prices.get("currency_code") or prices.get("currency") or "BRL")
    price_value = _int_or_none(prices.get("price"))
    amount = Money(currency=currency, minor_units=price_value) if price_value else None
    purchasable = bool(
        product.get("is_purchasable", product.get("isPurchasable", True))
    )
    in_stock = bool(product.get("is_in_stock", product.get("isInStock", False)))
    price_is_placeholder = price_value == 0
    price = PriceSnapshot(
        amount=None if price_is_placeholder else amount,
        display_text=_clean_html(product.get("price_html") or product.get("priceHtml")),
        can_mention=bool(
            amount and not price_is_placeholder and purchasable and in_stock
        ),
        quote_required=price_is_placeholder,
        hidden=amount is None,
        reason="catalog.quote_required_placeholder" if price_is_placeholder else None,
    )
    availability = AvailabilitySnapshot(
        is_available=in_stock,
        display_text=str(
            product.get("stock_availability")
            or product.get("stockAvailability")
            or ""
        ),
        can_mention=True,
        hidden_quantity=False,
        uncertain_reasons=[] if in_stock else ["catalog.out_of_stock"],
    )
    return ProductSnapshot(
        product_id=str(product.get("id")),
        sku=str(product.get("sku") or "") or None,
        name=str(product.get("name") or ""),
        permalink=product.get("permalink"),
        categories=[
            _taxonomy_name(item)
            for item in product.get("categories", [])
            if _taxonomy_name(item)
        ],
        tags=[
            _taxonomy_name(item)
            for item in product.get("tags", [])
            if _taxonomy_name(item)
        ],
        fitment_hints=[],
        price=price,
        availability=availability,
        risk_signals=[] if in_stock else ["catalog.out_of_stock"],
    )


def store_api_category_to_snapshot(category: dict[str, Any]) -> ProductCategory:
    """Map a Store API category payload into a normalized category snapshot."""

    category_id = str(
        category.get("id") or category.get("slug") or category.get("name")
    )
    parent = category.get("parent")
    return ProductCategory(
        category_id=category_id,
        name=str(category.get("name") or category.get("slug") or category_id),
        slug=str(category.get("slug")) if category.get("slug") else None,
        parent_id=str(parent) if parent not in {None, 0, ""} else None,
    )


def _store_api_filter_params(query: ProductSearchQuery) -> dict[str, str]:
    params: dict[str, str] = {}
    if query.categories:
        params["category"] = ",".join(query.categories)
    if query.tags:
        params["tag"] = ",".join(query.tags)
    return params


def _snapshot_matches_structured_filters(
    snapshot: ProductSnapshot,
    query: ProductSearchQuery,
) -> bool:
    category_text = " ".join(snapshot.categories).casefold()
    tag_text = " ".join(snapshot.tags).casefold()
    fitment_text = " ".join(snapshot.fitment_hints).casefold()
    return (
        _all_terms_match(query.categories, category_text)
        and _all_terms_match(query.tags, tag_text)
        and _all_terms_match(query.fitment_hints, fitment_text)
    )


def _all_terms_match(terms: list[str], haystack: str) -> bool:
    return all(term.casefold() in haystack for term in terms)


def _taxonomy_name(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("name") or item.get("slug") or "")
    return str(item)


def _clean_html(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"<[^>]+>", "", str(value))
    return html.unescape(text).strip()


def _int_or_none(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    return int(value)
