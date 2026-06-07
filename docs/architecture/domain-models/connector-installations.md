# Connector Installations

`ConnectorInstallation` is a tenant-scoped configured instance of an external
business system. A connector type such as WooCommerce can have multiple
installations for one tenant, even if version 1 configures only one.

## Shape

```python
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ConnectorCapability(StrEnum):
    product_catalog_read = "product_catalog_read"
    order_read = "order_read"
    customer_read = "customer_read"
    order_note_write = "order_note_write"
    order_status_update = "order_status_update"
    refund_create = "refund_create"
    coupon_create = "coupon_create"
    customer_tag_write = "customer_tag_write"


class ConnectorInstallation(BaseModel):
    """Tenant-scoped configured connector instance."""

    model_config = ConfigDict(frozen=True, strict=True)

    id: str
    tenant_id: str
    connector_key: str
    display_name: str
    enabled: bool
    supported_capabilities: set[ConnectorCapability] = Field(default_factory=set)
    enabled_capabilities: set[ConnectorCapability] = Field(default_factory=set)
    config: dict[str, object] = Field(default_factory=dict)
    credentials_ref: str | None = None
```

## Rules

- Store non-secret settings in `config`.
- Store secrets outside the installation record and reference them through
  `credentials_ref`.
- Effective capabilities are the intersection of supported capabilities, enabled
  capabilities, and policy-allowed capabilities.
- Agent paths should select an explicit installation id. Avoid "find any
  connector with this capability" behavior for customer-facing workflows.
- Disabling an installation should stop new use without deleting historical
  snapshots that were produced from it.
