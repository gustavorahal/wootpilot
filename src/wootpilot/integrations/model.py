"""Model proposal adapters for deterministic tests and OpenRouter live usage."""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, Field

from wootpilot.domain.models import (
    AgentActionKind,
    AgentProposal,
    ConversationState,
    ModelProposalResult,
    ModelProvider,
    NormalizedMessage,
    StructuredCatalogContext,
)
from wootpilot.domain.ports import ModelProposalPort
from wootpilot.settings import Settings


class FakeModelProposalPort(ModelProposalPort):
    """Deterministic adapter used by default CI and local observe smoke tests."""

    async def propose(
        self,
        *,
        message: NormalizedMessage,
        conversation_state: ConversationState,
        catalog_context: StructuredCatalogContext,
    ) -> ModelProposalResult:
        product = catalog_context.products[0] if catalog_context.products else None
        if product:
            public = (
                f"{product.name} may match your request. "
                f"Product page: {product.permalink}"
            )
            private = f"Suggested reply: {public}"
            summary = f"Found catalog context for {product.name}."
        else:
            public = "Thanks for reaching out. Could you share a few more details?"
            private = f"Suggested reply: {public}"
            summary = "No direct catalog match; ask a concise follow-up."
        return ModelProposalResult(
            proposal=AgentProposal(
                action_kind=AgentActionKind.private_note,
                summary=summary,
                public_message=public,
                private_note=private,
                risk_reasons=catalog_context.risk_signals,
                context_snapshot_ids=[catalog_context.snapshot_id]
                if catalog_context.snapshot_id
                else [],
                confidence=0.65 if product else 0.35,
            ),
            metadata={"provider": "fake", "model": "deterministic-local"},
        )


class AgentProposalSchema(BaseModel):
    """Provider-facing structured output schema validated before domain mapping."""

    action_kind: AgentActionKind
    summary: str
    public_message: str | None = None
    private_note: str | None = None
    risk_reasons: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class OpenRouterModelProposalPort(ModelProposalPort):
    """LangChain/OpenRouter adapter hidden behind WootPilot's proposal port."""

    def __init__(self, settings: Settings):
        self.settings = settings

    async def propose(
        self,
        *,
        message: NormalizedMessage,
        conversation_state: ConversationState,
        catalog_context: StructuredCatalogContext,
    ) -> ModelProposalResult:
        if (
            not self.settings.openrouter_api_key
            or self.settings.openrouter_api_key == "change-me"
        ):
            return ModelProposalResult(
                permanent_error="openrouter_api_key_missing",
                metadata={
                    "provider": "openrouter",
                    "model": self.settings.openrouter_model,
                },
            )
        started = time.perf_counter()
        try:
            from langchain_openrouter import ChatOpenRouter

            parsed, raw_metadata, structured_method = await self._invoke_structured(
                ChatOpenRouter,
                message=message,
                catalog_context=catalog_context,
            )
            proposal = AgentProposal(
                action_kind=parsed.action_kind,
                summary=parsed.summary,
                public_message=parsed.public_message,
                private_note=parsed.private_note,
                risk_reasons=parsed.risk_reasons,
                context_snapshot_ids=[catalog_context.snapshot_id]
                if catalog_context.snapshot_id
                else [],
                confidence=parsed.confidence,
            )
            metadata = {
                "provider": "openrouter",
                "model": self.settings.openrouter_model,
                "structured_method": structured_method,
                "latency_ms": round((time.perf_counter() - started) * 1000),
            }
            metadata.update(raw_metadata)
            return ModelProposalResult(
                proposal=proposal,
                metadata=metadata,
            )
        except Exception as exc:  # provider SDK exceptions vary across versions
            name = exc.__class__.__name__
            retryable = any(
                term in name.lower() for term in ("timeout", "rate", "connection")
            )
            payload: dict[str, Any] = {
                "provider": "openrouter",
                "model": self.settings.openrouter_model,
                "error_type": name,
                "latency_ms": round((time.perf_counter() - started) * 1000),
            }
            if retryable:
                return ModelProposalResult(retryable_error=name, metadata=payload)
            return ModelProposalResult(permanent_error=name, metadata=payload)

    async def _invoke_structured(
        self,
        chat_model_class: Any,
        *,
        message: NormalizedMessage,
        catalog_context: StructuredCatalogContext,
    ) -> tuple[AgentProposalSchema, dict[str, Any], str]:
        last_error: Exception | None = None
        for method in ("json_schema", "function_calling"):
            try:
                model = chat_model_class(
                    api_key=self.settings.openrouter_api_key,
                    model=self.settings.openrouter_model,
                    temperature=0.2,
                    max_tokens=800,
                )
                structured = model.with_structured_output(
                    AgentProposalSchema,
                    method=method,
                    include_raw=True,
                )
                result = await structured.ainvoke(
                    self._messages(message, catalog_context)
                )
                parsed = result.get("parsed") if isinstance(result, dict) else result
                if parsed is None:
                    parsing_error = (
                        result.get("parsing_error")
                        if isinstance(result, dict)
                        else "missing parsed output"
                    )
                    raise ValueError(str(parsing_error))
                raw = result.get("raw") if isinstance(result, dict) else None
                metadata = self._raw_metadata(raw)
                if not isinstance(parsed, AgentProposalSchema):
                    parsed = AgentProposalSchema.model_validate(parsed)
                return parsed, metadata, method
            except Exception as exc:
                last_error = exc
                if method == "function_calling":
                    raise
        raise last_error or RuntimeError("structured OpenRouter invocation failed")

    def _raw_metadata(self, raw: Any) -> dict[str, Any]:
        if raw is None:
            return {}
        response_metadata = getattr(raw, "response_metadata", {}) or {}
        usage_metadata = getattr(raw, "usage_metadata", {}) or {}
        return {
            "provider_model_name": response_metadata.get("model_name"),
            "provider_generation_id": response_metadata.get("id"),
            "token_usage": usage_metadata,
        }

    def _messages(
        self, message: NormalizedMessage, catalog_context: StructuredCatalogContext
    ) -> list[tuple[str, str]]:
        products = catalog_products_for_prompt(catalog_context)
        return [
            (
                "system",
                "You draft safe Chatwoot support proposals. Return only "
                "structured output. "
                "Never claim an action was sent. Prefer private_note when uncertain.",
            ),
            (
                "user",
                "Customer message:\n"
                f"{message.content}\n\n"
                f"Catalog context:\n{products}\n\n"
                "Produce a concise proposal.",
            ),
        ]


def model_port_from_settings(settings: Settings) -> ModelProposalPort:
    if settings.model_provider is ModelProvider.openrouter:
        return OpenRouterModelProposalPort(settings)
    return FakeModelProposalPort()


def catalog_products_for_prompt(
    catalog_context: StructuredCatalogContext,
) -> list[dict[str, Any]]:
    """Build model-visible catalog rows without leaking unsafe exact prices."""

    return [
        {
            "name": item.name,
            "sku": item.sku,
            "url": item.permalink,
            "priceCanMention": _price_can_be_shown_to_model(item),
            "price": item.price.display_text
            if _price_can_be_shown_to_model(item)
            else None,
            "pricePolicy": "mention_allowed"
            if _price_can_be_shown_to_model(item)
            else "do_not_mention_exact_price",
            "availability": item.availability.display_text
            if item.availability.can_mention
            else None,
            "riskSignals": item.risk_signals,
        }
        for item in catalog_context.products
    ]


def _price_can_be_shown_to_model(item) -> bool:
    return (
        item.price.can_mention
        and bool(item.price.display_text)
        and not item.price.hidden
        and not item.price.quote_required
        and not item.price.stale
        and item.availability.is_available is not False
    )
