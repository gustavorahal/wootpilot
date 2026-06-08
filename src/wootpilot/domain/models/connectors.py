"""Connector configuration models and capability vocabulary."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConnectorCapability(StrEnum):
    """External-system capability names used for connector selection and policy."""

    product_catalog_read = "product_catalog_read"
    order_read = "order_read"
    customer_read = "customer_read"
    order_note_write = "order_note_write"
    order_status_update = "order_status_update"
    refund_create = "refund_create"
    coupon_create = "coupon_create"
    customer_tag_write = "customer_tag_write"


class ConnectorInstallation(BaseModel):
    """Tenant-scoped connector configuration with deterministic capabilities.

    A connector installation represents one configured external business system,
    such as a WooCommerce store. Version 1 seeds this model from environment
    settings, but keeping the shape tenant-scoped now prevents agent code from
    relying on a global connector once multi-store or multi-brand setups exist.

    Secrets do not belong in this model. Store non-secret adapter settings in
    `config` and point `credentials_ref` at the secret location used by the
    deployment environment. Effective capabilities are intentionally calculated
    as the intersection of supported, enabled, and policy-allowed capabilities
    so disabling a capability is fail-closed and deterministic.
    """

    model_config = ConfigDict(strict=True)

    id: str
    tenant_id: str
    connector_key: str
    display_name: str
    enabled: bool = True
    supported_capabilities: list[ConnectorCapability] = Field(default_factory=list)
    enabled_capabilities: list[ConnectorCapability] = Field(default_factory=list)
    policy_allowed_capabilities: list[ConnectorCapability] = Field(
        default_factory=list
    )
    config: dict[str, Any] = Field(default_factory=dict)
    credentials_ref: str | None = None

    @property
    def effective_capabilities(self) -> list[ConnectorCapability]:
        """Return enabled, supported, policy-allowed capabilities in stable order."""

        if not self.enabled:
            return []
        supported = set(self.supported_capabilities)
        enabled = set(self.enabled_capabilities)
        allowed = set(self.policy_allowed_capabilities or self.supported_capabilities)
        return sorted(supported & enabled & allowed, key=lambda item: item.value)
