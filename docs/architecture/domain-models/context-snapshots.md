# Context Snapshots

`ContextSnapshot` records the compact context that influenced an agent run. It is
not a raw connector payload and not a full copy of every external API response.

## Shape

```python
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class ContextResourceType(StrEnum):
    product = "product"
    price = "price"
    availability = "availability"
    conversation = "conversation"
    custom = "custom"


class ContextSnapshot(BaseModel):
    """Auditable context fragment used by an agent run."""

    model_config = ConfigDict(frozen=True, strict=True)

    id: str
    agent_run_id: str
    connector_key: str | None = None
    connector_installation_id: str | None = None
    resource_type: ContextResourceType
    external_resource_id: str | None = None
    snapshot: dict[str, object]
    captured_at: datetime
```

## Rules

- Store the normalized, policy-aware context the agent saw.
- Do not store every low-level HTTP response as a context snapshot.
- Include connector identity when context came from a connector.
- Include snapshot ids in agent proposals so audits can connect model output to
  source context.
- Redact sensitive fields before context enters LLM prompts, logs, or any future
  external traces.
