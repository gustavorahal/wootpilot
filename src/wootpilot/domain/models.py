"""Domain models shared by WootPilot application services and workflows.

These objects intentionally avoid FastAPI, SQLAlchemy, Chatwoot, and provider
SDK imports. They are the boundary between trusted application data and the
LangGraph workflow.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BotMode(StrEnum):
    shadow = "shadow"
    copilot = "copilot"
    limited_auto = "limited_auto"


class AgentRunStatus(StrEnum):
    ignored = "ignored"
    proposed = "proposed"
    blocked_by_policy = "blocked_by_policy"
    queued_action = "queued_action"
    sent_public_message = "sent_public_message"
    sent_private_note = "sent_private_note"
    failed = "failed"


class AgentActionKind(StrEnum):
    none = "none"
    public_message = "public_message"
    private_note = "private_note"


class PolicyOutcome(StrEnum):
    allow = "allow"
    block = "block"
    review = "review"


class OutboundActionStatus(StrEnum):
    queued = "queued"
    executing = "executing"
    sent = "sent"
    retryable_failure = "retryable_failure"
    permanent_failure = "permanent_failure"
    blocked_by_policy = "blocked_by_policy"


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

    Version 1 seeds this model from environment settings, but keeping the shape
    tenant-scoped now prevents agent code from relying on a global connector
    once multi-store or multi-brand setups exist.
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


class Money(BaseModel):
    """Currency amount stored as integer minor units to avoid float drift."""

    model_config = ConfigDict(strict=True)

    currency: str = Field(min_length=3, max_length=3)
    minor_units: int

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()

    def display(self, minor_unit: int = 2, symbol: str | None = None) -> str:
        major = self.minor_units / (10**minor_unit)
        prefix = f"{symbol} " if symbol else f"{self.currency} "
        return f"{prefix}{major:,.{minor_unit}f}"

    def __add__(self, other: Money) -> Money:
        self._require_same_currency(other)
        return Money(
            currency=self.currency,
            minor_units=self.minor_units + other.minor_units,
        )

    def __sub__(self, other: Money) -> Money:
        self._require_same_currency(other)
        return Money(
            currency=self.currency,
            minor_units=self.minor_units - other.minor_units,
        )

    @classmethod
    def zero(cls, currency: str) -> Money:
        return cls(currency=currency, minor_units=0)

    def _require_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise ValueError("Money arithmetic requires matching currencies")


class PriceSnapshot(BaseModel):
    model_config = ConfigDict(strict=True)

    amount: Money | None = None
    display_text: str | None = None
    can_mention: bool = False
    quote_required: bool = False
    hidden: bool = False
    stale: bool = False
    reason: str | None = None


class AvailabilitySnapshot(BaseModel):
    model_config = ConfigDict(strict=True)

    is_available: bool | None = None
    display_text: str | None = None
    can_mention: bool = False
    hidden_quantity: bool = True
    uncertain_reasons: list[str] = Field(default_factory=list)


class ProductSnapshot(BaseModel):
    model_config = ConfigDict(strict=True)

    product_id: str
    sku: str | None = None
    name: str
    permalink: str | None = None
    categories: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    fitment_hints: list[str] = Field(default_factory=list)
    price: PriceSnapshot
    availability: AvailabilitySnapshot
    risk_signals: list[str] = Field(default_factory=list)


class ProductCategory(BaseModel):
    """Normalized catalog category safe to expose outside connector packages."""

    model_config = ConfigDict(strict=True)

    category_id: str
    name: str
    slug: str | None = None
    parent_id: str | None = None


class ProductSearchQuery(BaseModel):
    """Structured catalog search request shared by connector adapters."""

    model_config = ConfigDict(strict=True)

    query: str
    limit: int = Field(default=5, ge=1, le=50)
    categories: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    fitment_hints: list[str] = Field(default_factory=list)


class StructuredCatalogContext(BaseModel):
    model_config = ConfigDict(strict=True)

    query: str
    products: list[ProductSnapshot] = Field(default_factory=list)
    risk_signals: list[str] = Field(default_factory=list)
    snapshot_id: str | None = None


class AttachmentMetadata(BaseModel):
    """Provider attachment metadata safe to carry into policy decisions."""

    model_config = ConfigDict(strict=True)

    provider_attachment_id: str | None = None
    content_type: str | None = None
    file_name: str | None = None
    url: str | None = None


class NormalizedMessage(BaseModel):
    model_config = ConfigDict(strict=True)

    id: str
    raw_event_id: str
    tenant_id: str
    provider: str = "chatwoot"
    provider_account_id: str = ""
    provider_inbox_id: str = ""
    provider_conversation_id: str = ""
    provider_message_id: str = ""
    provider_contact_id: str | None = None
    channel_id: str
    conversation_id: str
    message_id: str
    contact_id: str | None = None
    direction: str
    visibility: str
    author_type: str
    content: str
    attachments: list[AttachmentMetadata] = Field(default_factory=list)
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChannelEvent(BaseModel):
    """Non-message Chatwoot conversation event that updates local safety state."""

    model_config = ConfigDict(strict=True)

    id: str
    raw_event_id: str
    event_type: str
    tenant_id: str
    channel_id: str
    conversation_id: str
    status: str | None = None
    replyable: bool | None = None
    paused: bool = False
    auto_ok: bool = False
    assigned_agent_id: str | None = None
    assigned_team_id: str | None = None
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationState(BaseModel):
    model_config = ConfigDict(strict=True)

    id: str
    tenant_id: str
    channel_id: str
    conversation_id: str
    human_active_until: datetime | None = None
    last_human_public_message_at: datetime | None = None
    last_customer_message_at: datetime | None = None
    assigned_agent_id: str | None = None
    assigned_team_id: str | None = None
    status: str | None = None
    replyable: bool = True
    paused: bool = False
    auto_ok: bool = False
    updated_at: datetime


class TriageResult(BaseModel):
    model_config = ConfigDict(strict=True)

    should_invoke: bool
    intent: str
    risk_signals: list[str] = Field(default_factory=list)
    reason: str | None = None


class PolicyDecision(BaseModel):
    model_config = ConfigDict(strict=True)

    id: str
    stage: str
    outcome: PolicyOutcome
    rule_ids: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AgentProposal(BaseModel):
    """LLM-produced action proposal; never a final execution result."""

    model_config = ConfigDict(strict=True)

    action_kind: AgentActionKind
    summary: str
    public_message: str | None = None
    private_note: str | None = None
    risk_reasons: list[str] = Field(default_factory=list)
    context_snapshot_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    error_code: str | None = None


class ModelProposalResult(BaseModel):
    model_config = ConfigDict(strict=True)

    proposal: AgentProposal | None = None
    retryable_error: str | None = None
    permanent_error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowDecision(BaseModel):
    model_config = ConfigDict(strict=True)

    status: AgentRunStatus
    action_kind: AgentActionKind = AgentActionKind.none
    content: str | None = None
    summary: str
    rule_ids: list[str] = Field(default_factory=list)
    risk_reasons: list[str] = Field(default_factory=list)
