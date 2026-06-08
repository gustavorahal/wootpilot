from __future__ import annotations

import json
import logging
from pathlib import Path

import respx
from httpx import Response

from wootpilot.catalog.mock import MockCatalog
from wootpilot.catalog.store_api import (
    CatalogContextError,
    StoreApiCatalog,
    store_api_category_to_snapshot,
    store_api_product_to_snapshot,
)
from wootpilot.domain.models import (
    ConnectorCapability,
    ConnectorInstallation,
    Money,
    ProductSearchQuery,
)
from wootpilot.settings import Settings


async def test_mock_catalog_search_by_name_sku_and_category() -> None:
    catalog = MockCatalog(Path("data/mock-woocommerce/catalog.demo-car-parts.json"))
    by_name = await catalog.search("Chicote Aircooled")
    by_sku = await catalog.search("DCP-100-0104")
    by_category = await catalog.search("KITS")
    assert by_name.products
    assert by_sku.products[0].sku == "DCP-100-0104"
    assert by_category.products


def test_money_rejects_float_minor_units() -> None:
    try:
        Money(currency="brl", minor_units=10.5)  # type: ignore[arg-type]
    except Exception as exc:
        assert "minor_units" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("float minor units should be rejected")


def test_money_supports_zero_and_same_currency_arithmetic() -> None:
    subtotal = Money(currency="brl", minor_units=350000)
    addon = Money(currency="BRL", minor_units=25000)

    assert Money.zero("brl") == Money(currency="BRL", minor_units=0)
    assert subtotal + addon == Money(currency="BRL", minor_units=375000)
    assert subtotal - addon == Money(currency="BRL", minor_units=325000)

    try:
        _ = subtotal + Money(currency="USD", minor_units=100)
    except ValueError as exc:
        assert "matching currencies" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("cross-currency arithmetic should fail")


async def test_mock_catalog_capability_methods() -> None:
    catalog = MockCatalog(Path("data/mock-woocommerce/catalog.demo-car-parts.json"))

    products = await catalog.search_products(
        ProductSearchQuery(query="DCP-100-0104", limit=3)
    )
    by_sku = await catalog.get_product_by_sku("DCP-100-0104")
    by_id = await catalog.get_product(products[0].product_id)
    categories = await catalog.list_categories()

    assert products
    assert by_sku is not None
    assert by_sku.sku == "DCP-100-0104"
    assert by_id is not None
    assert categories == sorted(categories, key=lambda item: item.name.casefold())
    assert {category.name for category in categories}


async def test_mock_catalog_structured_query_filters_results() -> None:
    catalog = MockCatalog(Path("data/mock-woocommerce/catalog.demo-car-parts.json"))

    products = await catalog.search_products(
        ProductSearchQuery(
            query="",
            categories=["tbi"],
            tags=["ford"],
            limit=10,
        )
    )
    missing_fitment = await catalog.search_products(
        ProductSearchQuery(query="", fitment_hints=["fusca"], limit=10)
    )

    assert [product.sku for product in products] == ["TBIFORD60"]
    assert missing_fitment == []


@respx.mock
def test_store_api_catalog_search_maps_recorded_fixture(caplog) -> None:
    import asyncio

    fixture = Path("tests/fixtures/woocommerce/store_api_products.json").read_text()
    route = respx.get(
        "https://fictional-woocommerce-demo.test/wp-json/wc/store/v1/products"
    ).mock(return_value=Response(200, content=fixture))
    caplog.set_level(logging.INFO, logger="wootpilot.catalog.store_api")

    context = asyncio.run(
        StoreApiCatalog(
            base_url="https://fictional-woocommerce-demo.test"
        ).search("aircooled")
    )

    assert route.called
    log_record = next(
        record
        for record in caplog.records
        if getattr(record, "wootpilot_event", "")
        == "catalog_connector_read_completed"
    )
    assert log_record.wootpilot_fields["connector"] == "woocommerce_store_api"
    assert log_record.wootpilot_fields["capability"] == "product_search"
    assert log_record.wootpilot_fields["status"] == "success"
    assert log_record.wootpilot_fields["status_code"] == 200
    assert log_record.wootpilot_fields["result_count"] == 2
    assert context.products[0].name == "Demo Aircooled Harness"
    assert context.products[0].price.can_mention is True
    assert context.products[0].price.amount == Money(
        currency="BRL", minor_units=350000
    )
    assert context.products[0].availability.can_mention is True


@respx.mock
def test_store_api_capability_methods_map_recorded_fixtures() -> None:
    import asyncio

    products_fixture = Path("tests/fixtures/woocommerce/store_api_products.json")
    categories_fixture = Path("tests/fixtures/woocommerce/store_api_categories.json")
    product_payloads = json.loads(products_fixture.read_text())
    respx.get(
        "https://fictional-woocommerce-demo.test/wp-json/wc/store/v1/products"
    ).mock(return_value=Response(200, content=products_fixture.read_text()))
    respx.get(
        "https://fictional-woocommerce-demo.test/wp-json/wc/store/v1/products/101"
    ).mock(return_value=Response(200, json=product_payloads[0]))
    respx.get(
        "https://fictional-woocommerce-demo.test/wp-json/wc/store/v1/products/categories"
    ).mock(return_value=Response(200, content=categories_fixture.read_text()))

    async def run() -> None:
        catalog = StoreApiCatalog(base_url="https://fictional-woocommerce-demo.test")
        products = await catalog.search_products(
            ProductSearchQuery(query="aircooled", limit=2)
        )
        product = await catalog.get_product("101")
        by_sku = await catalog.get_product_by_sku("DEMO-HARNESS-001")
        categories = await catalog.list_categories()

        assert products[0].name == "Demo Aircooled Harness"
        assert product is not None
        assert product.product_id == "101"
        assert by_sku is not None
        assert by_sku.sku == "DEMO-HARNESS-001"
        assert [category.name for category in categories] == ["Harnesses", "Kits"]

    asyncio.run(run())


@respx.mock
def test_store_api_structured_filters_and_logs_capabilities(caplog) -> None:
    import asyncio

    products_fixture = Path("tests/fixtures/woocommerce/store_api_products.json")
    categories_fixture = Path("tests/fixtures/woocommerce/store_api_categories.json")
    respx.get(
        "https://fictional-woocommerce-demo.test/wp-json/wc/store/v1/products"
    ).mock(return_value=Response(200, content=products_fixture.read_text()))
    respx.get(
        "https://fictional-woocommerce-demo.test/wp-json/wc/store/v1/products/categories"
    ).mock(return_value=Response(200, content=categories_fixture.read_text()))
    caplog.set_level(logging.INFO, logger="wootpilot.catalog.store_api")

    async def run() -> None:
        catalog = StoreApiCatalog(base_url="https://fictional-woocommerce-demo.test")
        harnesses = await catalog.search_products(
            ProductSearchQuery(query="", categories=["harnesses"])
        )
        missing = await catalog.search_products(
            ProductSearchQuery(query="", tags=["does-not-exist"])
        )
        await catalog.list_categories()

        assert [product.name for product in harnesses] == ["Demo Aircooled Harness"]
        assert missing == []

    asyncio.run(run())

    capabilities = [
        record.wootpilot_fields["capability"]
        for record in caplog.records
        if getattr(record, "wootpilot_event", "")
        == "catalog_connector_read_completed"
    ]
    assert "product_search" in capabilities
    assert "product_categories" in capabilities


def test_store_api_category_mapping() -> None:
    category = store_api_category_to_snapshot(
        {"id": 10, "name": "Harnesses", "slug": "harnesses", "parent": 0}
    )

    assert category.category_id == "10"
    assert category.name == "Harnesses"
    assert category.slug == "harnesses"
    assert category.parent_id is None


def test_store_api_zero_value_kit_is_quote_required_not_free() -> None:
    import json

    products = json.loads(
        Path("tests/fixtures/woocommerce/store_api_products.json").read_text()
    )
    kit = store_api_product_to_snapshot(products[1])

    assert kit.price.amount is None
    assert kit.price.quote_required is True
    assert kit.price.can_mention is False
    assert kit.price.reason == "catalog.quote_required_placeholder"


def test_store_api_settings_require_base_url() -> None:
    from wootpilot.catalog.factory import catalog_connector_from_settings

    settings = Settings(
        catalog_connector_mode="store_api",
        woocommerce_store_api_base_url="",
        chatwoot_webhook_secret="secret",
    )
    try:
        catalog_connector_from_settings(settings)
    except ValueError as exc:
        assert "WOOTPILOT_WOOCOMMERCE_STORE_API_BASE_URL" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("store_api mode should require a Store API base URL")


def test_connector_installation_effective_capabilities_are_deterministic() -> None:
    installation = ConnectorInstallation(
        id="demo-store",
        tenant_id="default",
        connector_key="woocommerce",
        display_name="Demo Store",
        enabled=True,
        supported_capabilities=[
            ConnectorCapability.customer_read,
            ConnectorCapability.product_catalog_read,
            ConnectorCapability.order_read,
        ],
        enabled_capabilities=[
            ConnectorCapability.order_read,
            ConnectorCapability.product_catalog_read,
        ],
        policy_allowed_capabilities=[
            ConnectorCapability.product_catalog_read,
            ConnectorCapability.customer_read,
        ],
    )

    assert installation.effective_capabilities == [
        ConnectorCapability.product_catalog_read
    ]

    disabled = installation.model_copy(update={"enabled": False})
    assert disabled.effective_capabilities == []


def test_connector_registry_resolves_configured_product_catalog_by_capability() -> None:
    from wootpilot.catalog.factory import CatalogConnectorRegistry

    settings = Settings(chatwoot_webhook_secret="secret")
    installation = ConnectorInstallation(
        id="demo-store",
        tenant_id="default",
        connector_key="woocommerce",
        display_name="Demo Store",
        enabled=True,
        supported_capabilities=[ConnectorCapability.product_catalog_read],
        enabled_capabilities=[ConnectorCapability.product_catalog_read],
        policy_allowed_capabilities=[ConnectorCapability.product_catalog_read],
        config={"mode": "mock"},
    )

    catalog = CatalogConnectorRegistry(settings).require_product_catalog(installation)

    assert isinstance(catalog, MockCatalog)


def test_connector_registry_rejects_installation_without_effective_capability() -> None:
    from wootpilot.catalog.factory import CatalogConnectorRegistry

    settings = Settings(chatwoot_webhook_secret="secret")
    installation = ConnectorInstallation(
        id="demo-store",
        tenant_id="default",
        connector_key="woocommerce",
        display_name="Demo Store",
        enabled=False,
        supported_capabilities=[ConnectorCapability.product_catalog_read],
        enabled_capabilities=[ConnectorCapability.product_catalog_read],
        policy_allowed_capabilities=[ConnectorCapability.product_catalog_read],
        config={"mode": "mock"},
    )

    try:
        CatalogConnectorRegistry(settings).require_product_catalog(installation)
    except ValueError as exc:
        assert "product_catalog_read" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("registry should reject disabled catalog installation")


@respx.mock
def test_store_api_failure_raises_controlled_context_error(caplog) -> None:
    import asyncio

    respx.get(
        "https://fictional-woocommerce-demo.test/wp-json/wc/store/v1/products"
    ).mock(return_value=Response(503, json={"code": "temporarily_unavailable"}))
    caplog.set_level(logging.WARNING, logger="wootpilot.catalog.store_api")

    try:
        asyncio.run(
            StoreApiCatalog(
                base_url="https://fictional-woocommerce-demo.test"
            ).search("aircooled")
        )
    except CatalogContextError as exc:
        assert "woocommerce_store_api_context_failed" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Store API failures should be controlled")
    log_record = next(
        record
        for record in caplog.records
        if getattr(record, "wootpilot_event", "")
        == "catalog_connector_read_completed"
    )
    assert log_record.wootpilot_fields["status"] == "failed"
    assert log_record.wootpilot_fields["status_code"] == 503
    assert isinstance(log_record.wootpilot_fields["latency_ms"], int)
