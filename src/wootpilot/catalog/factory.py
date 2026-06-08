"""Catalog connector selection from runtime connector installations."""

from __future__ import annotations

from wootpilot.catalog.mock import MockCatalog
from wootpilot.catalog.store_api import StoreApiCatalog
from wootpilot.domain.models import (
    CatalogConnectorMode,
    ConnectorCapability,
    ConnectorInstallation,
)
from wootpilot.domain.ports import ProductCatalogConnector
from wootpilot.settings import Settings


class CatalogConnectorRegistry:
    """Selects configured catalog adapters by explicit installation capability."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def require_product_catalog(
        self,
        installation: ConnectorInstallation | None = None,
    ) -> ProductCatalogConnector:
        configured = installation or default_catalog_installation_from_settings(
            self.settings
        )
        if (
            ConnectorCapability.product_catalog_read
            not in configured.effective_capabilities
        ):
            raise ValueError(
                "Configured connector installation does not provide "
                "product_catalog_read"
            )
        if configured.connector_key != "woocommerce":
            raise ValueError(
                f"Unsupported product catalog connector: {configured.connector_key}"
            )

        mode = CatalogConnectorMode(
            configured.config.get("mode") or self.settings.catalog_connector_mode
        )
        if mode is CatalogConnectorMode.store_api:
            base_url = str(
                configured.config.get("base_url")
                or self.settings.woocommerce_store_api_base_url
            )
            if not base_url:
                raise ValueError(
                    "WOOCOMMERCE_STORE_API_BASE_URL is required when "
                    "CATALOG_CONNECTOR_MODE=store_api"
                )
            return StoreApiCatalog(base_url=base_url)
        if mode is CatalogConnectorMode.mock:
            return MockCatalog(self.settings.mock_catalog_path)
        raise ValueError(
            f"Unsupported WooCommerce catalog connector mode: {mode.value}"
        )


def default_catalog_installation_from_settings(
    settings: Settings,
) -> ConnectorInstallation:
    """Seed the default tenant's WooCommerce catalog installation from env settings."""

    capabilities = [ConnectorCapability.product_catalog_read]
    config: dict[str, str] = {"mode": settings.catalog_connector_mode.value}
    if settings.woocommerce_store_api_base_url:
        config["base_url"] = settings.woocommerce_store_api_base_url
    return ConnectorInstallation(
        id="default-woocommerce-catalog",
        tenant_id="default",
        connector_key="woocommerce",
        display_name="Default WooCommerce Catalog",
        enabled=True,
        supported_capabilities=capabilities,
        enabled_capabilities=capabilities,
        policy_allowed_capabilities=capabilities,
        config=config,
        credentials_ref=None,
    )


def catalog_connector_from_settings(settings: Settings) -> ProductCatalogConnector:
    return CatalogConnectorRegistry(settings).require_product_catalog()
