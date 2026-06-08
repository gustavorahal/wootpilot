"""Application ports implemented by adapters at the system edge."""

from __future__ import annotations

from typing import Protocol

from wootpilot.domain.models import (
    ConversationState,
    ModelProposalResult,
    NormalizedMessage,
    ProductCategory,
    ProductSearchQuery,
    ProductSnapshot,
    StructuredCatalogContext,
)


class ModelProposalPort(Protocol):
    """Produces a structured support proposal from prepared, policy-safe inputs."""

    async def propose(
        self,
        *,
        message: NormalizedMessage,
        conversation_state: ConversationState,
        catalog_context: StructuredCatalogContext,
    ) -> ModelProposalResult: ...


class ProductCatalogConnector(Protocol):
    """Read-only product catalog capability used to build agent context."""

    async def search(self, query: str, limit: int = 5) -> StructuredCatalogContext: ...

    async def search_products(
        self,
        query: ProductSearchQuery,
    ) -> list[ProductSnapshot]: ...

    async def get_product(self, external_product_id: str) -> ProductSnapshot | None: ...

    async def get_product_by_sku(self, sku: str) -> ProductSnapshot | None: ...

    async def list_categories(self) -> list[ProductCategory]: ...
