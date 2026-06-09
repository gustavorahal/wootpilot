from __future__ import annotations

import sys
import types
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from wootpilot.domain.models import (
    AgentActionKind,
    ConversationState,
    MessageAuthorType,
    MessageDirection,
    MessageVisibility,
    NormalizedMessage,
    StructuredCatalogContext,
)
from wootpilot.integrations.model import (
    AgentProposalSchema,
    OpenRouterModelProposalPort,
)
from wootpilot.settings import Settings


def test_agent_proposal_schema_rejects_malformed_model_output() -> None:
    with pytest.raises(ValidationError):
        AgentProposalSchema.model_validate(
            {
                "action_kind": "public_message",
                "summary": "Invalid confidence",
                "confidence": 1.5,
            }
        )


async def test_openrouter_adapter_maps_structured_response_and_metadata(
    monkeypatch,
) -> None:
    _install_fake_langchain_openrouter(monkeypatch, SuccessfulChatOpenRouter)
    port = OpenRouterModelProposalPort(_openrouter_settings())

    result = await port.propose(
        message=_message(),
        conversation_state=_state(),
        catalog_context=StructuredCatalogContext(
            query="aircooled",
            snapshot_id="snapshot-1",
        ),
    )

    assert result.retryable_error is None
    assert result.permanent_error is None
    assert result.proposal is not None
    assert result.proposal.action_kind is AgentActionKind.private_note
    assert result.proposal.private_note == "Suggested private note"
    assert result.proposal.context_snapshot_ids == ["snapshot-1"]
    assert result.metadata["provider"] == "openrouter"
    assert result.metadata["model"] == "openai/gpt-4.1-mini"
    assert result.metadata["structured_method"] == "json_schema"
    assert result.metadata["provider_model_name"] == "fake/openrouter-model"
    assert result.metadata["provider_generation_id"] == "generation-1"
    assert result.metadata["token_usage"] == {"input_tokens": 10, "output_tokens": 5}
    assert isinstance(result.metadata["latency_ms"], int)


async def test_openrouter_adapter_falls_back_to_function_calling(monkeypatch) -> None:
    FallbackChatOpenRouter.calls = []
    _install_fake_langchain_openrouter(monkeypatch, FallbackChatOpenRouter)
    port = OpenRouterModelProposalPort(_openrouter_settings())

    result = await port.propose(
        message=_message(),
        conversation_state=_state(),
        catalog_context=StructuredCatalogContext(query="aircooled"),
    )

    assert result.proposal is not None
    assert result.metadata["structured_method"] == "function_calling"
    assert FallbackChatOpenRouter.calls == ["json_schema", "function_calling"]


async def test_openrouter_adapter_classifies_retryable_errors(monkeypatch) -> None:
    _install_fake_langchain_openrouter(monkeypatch, TimeoutChatOpenRouter)
    port = OpenRouterModelProposalPort(_openrouter_settings())

    result = await port.propose(
        message=_message(),
        conversation_state=_state(),
        catalog_context=StructuredCatalogContext(query="aircooled"),
    )

    assert result.proposal is None
    assert result.retryable_error == "TimeoutError"
    assert result.permanent_error is None
    assert result.metadata["provider"] == "openrouter"
    assert result.metadata["error_type"] == "TimeoutError"


async def test_openrouter_adapter_classifies_permanent_errors(monkeypatch) -> None:
    _install_fake_langchain_openrouter(monkeypatch, PermanentChatOpenRouter)
    port = OpenRouterModelProposalPort(_openrouter_settings())

    result = await port.propose(
        message=_message(),
        conversation_state=_state(),
        catalog_context=StructuredCatalogContext(query="aircooled"),
    )

    assert result.proposal is None
    assert result.retryable_error is None
    assert result.permanent_error == "ValueError"
    assert result.metadata["error_type"] == "ValueError"


async def test_openrouter_adapter_fails_closed_without_api_key() -> None:
    port = OpenRouterModelProposalPort(Settings(openrouter_api_key=""))

    result = await port.propose(
        message=_message(),
        conversation_state=_state(),
        catalog_context=StructuredCatalogContext(query="aircooled"),
    )

    assert result.proposal is None
    assert result.permanent_error == "openrouter_api_key_missing"
    assert result.metadata == {
        "provider": "openrouter",
        "model": "openai/gpt-4.1-mini",
    }


async def test_openrouter_adapter_does_not_classify_unexpected_errors(
    monkeypatch,
) -> None:
    _install_fake_langchain_openrouter(monkeypatch, BuggyChatOpenRouter)
    port = OpenRouterModelProposalPort(_openrouter_settings())

    with pytest.raises(RuntimeError, match="local adapter bug"):
        await port.propose(
            message=_message(),
            conversation_state=_state(),
            catalog_context=StructuredCatalogContext(query="aircooled"),
        )


class SuccessfulChatOpenRouter:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    def with_structured_output(self, schema, *, method: str, include_raw: bool):
        assert schema is AgentProposalSchema
        assert method == "json_schema"
        assert include_raw is True
        return FakeStructuredRunnable()


class FallbackChatOpenRouter:
    calls: list[str] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    def with_structured_output(self, schema, *, method: str, include_raw: bool):
        del schema, include_raw
        self.calls.append(method)
        if method == "json_schema":
            raise ValueError("json schema unsupported")
        return FakeStructuredRunnable()


class TimeoutChatOpenRouter:
    def __init__(self, **kwargs) -> None:
        raise TimeoutError("provider timeout")


class PermanentChatOpenRouter:
    def __init__(self, **kwargs) -> None:
        raise ValueError("provider rejected request")


class BuggyChatOpenRouter:
    def __init__(self, **kwargs) -> None:
        del kwargs
        raise RuntimeError("local adapter bug")


class FakeStructuredRunnable:
    async def ainvoke(self, messages):
        assert messages[0][0] == "system"
        assert "Customer message" in messages[1][1]
        return {
            "parsed": {
                "action_kind": "private_note",
                "summary": "Mapped proposal",
                "public_message": "Public draft",
                "private_note": "Suggested private note",
                "risk_reasons": ["catalog.uncertain"],
                "confidence": 0.7,
            },
            "raw": FakeRawMessage(),
        }


class FakeRawMessage:
    response_metadata = {
        "model_name": "fake/openrouter-model",
        "id": "generation-1",
    }
    usage_metadata = {"input_tokens": 10, "output_tokens": 5}


def _install_fake_langchain_openrouter(monkeypatch, chat_model_class) -> None:
    module: Any = types.ModuleType("langchain_openrouter")
    module.ChatOpenRouter = chat_model_class
    monkeypatch.setitem(sys.modules, "langchain_openrouter", module)


def _openrouter_settings() -> Settings:
    return Settings(
        openrouter_api_key="test-key",
        openrouter_model="openai/gpt-4.1-mini",
        chatwoot_webhook_secret="secret",
    )


def _message() -> NormalizedMessage:
    now = datetime.now(UTC)
    return NormalizedMessage(
        id="message-1",
        raw_event_id="raw-1",
        tenant_id="tenant-1",
        channel_id="channel-1",
        conversation_id="conversation-1",
        message_id="provider-message-1",
        direction=MessageDirection.inbound,
        visibility=MessageVisibility.public,
        author_type=MessageAuthorType.customer,
        content="Do you have an aircooled harness?",
        created_at=now,
    )


def _state() -> ConversationState:
    now = datetime.now(UTC)
    return ConversationState(
        id="state-1",
        tenant_id="tenant-1",
        channel_id="channel-1",
        conversation_id="conversation-1",
        updated_at=now,
    )
