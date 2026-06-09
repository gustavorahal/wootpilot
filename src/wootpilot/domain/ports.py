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

__all__ = ["ModelProposalPort", "ProductCatalogConnector"]


class ModelProposalPort(Protocol):
    """Produces a structured support proposal from prepared, policy-safe inputs."""

    async def propose(
        self,
        *,
        message: NormalizedMessage,
        conversation_state: ConversationState,
        catalog_context: StructuredCatalogContext,
    ) -> ModelProposalResult:
        """Return a proposal result without performing customer-visible effects."""
        ...


class ProductCatalogConnector(Protocol):
    """Read-only product catalog capability used to build agent context."""

    async def search(self, query: str, limit: int = 5) -> StructuredCatalogContext:
        """Return lightweight catalog context for free-text customer messages."""
        ...

    async def search_products(
        self,
        query: ProductSearchQuery,
    ) -> list[ProductSnapshot]:
        """Return products matching structured filters from tools or future APIs."""
        ...

    async def get_product(self, external_product_id: str) -> ProductSnapshot | None:
        """Return one product by provider id, or `None` when absent."""
        ...

    async def get_product_by_sku(self, sku: str) -> ProductSnapshot | None:
        """Return one product by SKU, or `None` when absent."""
        ...

    async def list_categories(self) -> list[ProductCategory]:
        """Return catalog categories exposed for guided product search."""
        ...
