# Tenants

`Tenant` is the ownership and configuration boundary for WootPilot. Version 1 may
operate with a single default tenant, but the domain model should make tenant
scope explicit from the start.

## Shape

```python
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Tenant(BaseModel):
    """Configuration and ownership boundary for WootPilot data and workflows."""

    model_config = ConfigDict(frozen=True, strict=True)

    id: str
    name: str
    default_locale: str | None = None
    default_currency: str | None = Field(default=None, min_length=3, max_length=3)
    enabled: bool = True
    created_at: datetime
```

## Rules

- Every persisted business object should be tenant-scoped.
- Do not infer money currency from tenant default when source data provides a
  concrete currency.
- Tenant defaults can seed local development, but connector installation config
  should own connector-specific behavior.
- Tenant deletion should be treated as a product/data-retention decision, not a
  casual cascade.
