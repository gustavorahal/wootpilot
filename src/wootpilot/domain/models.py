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
    """Operating modes that control how far WootPilot may act on a turn."""

    shadow = "shadow"
    copilot = "copilot"
    limited_auto = "limited_auto"


class RuntimeEnvironment(StrEnum):
    """Deployment profile names that drive safety-sensitive runtime behavior."""

    local = "local"
    test = "test"
    public_dev = "public_dev"
    production = "production"


class Provider(StrEnum):
    """External channel provider identifiers stored on normalized events."""

    chatwoot = "chatwoot"


class MessageDirection(StrEnum):
    """Direction of a message from WootPilot's point of view."""

    inbound = "inbound"
    outbound = "outbound"


class MessageVisibility(StrEnum):
    """Whether a message is customer-visible or an internal note."""

    public = "public"
    private = "private"


class MessageAuthorType(StrEnum):
    """Normalized author roles used by policy and conversation-state updates."""

    customer = "customer"
    human_agent = "human_agent"
    bot = "bot"


class ConversationStatus(StrEnum):
    """Conversation lifecycle states WootPilot currently makes decisions on."""

    open = "open"
    pending = "pending"
    resolved = "resolved"


class AgentRunStatus(StrEnum):
    """Final workflow outcomes stored on an agent run."""

    ignored = "ignored"
    proposed = "proposed"
    blocked_by_policy = "blocked_by_policy"
    queued_action = "queued_action"
    sent_public_message = "sent_public_message"
    sent_private_note = "sent_private_note"
    failed = "failed"


class AgentActionKind(StrEnum):
    """Action shape selected by the workflow before outbound execution."""

    none = "none"
    public_message = "public_message"
    private_note = "private_note"


class PolicyOutcome(StrEnum):
    """Deterministic policy verdict for a checkpoint."""

    allow = "allow"
    block = "block"
    review = "review"


class OutboundActionStatus(StrEnum):
    """Delivery lifecycle for queued provider-side actions."""

    queued = "queued"
    executing = "executing"
    sent = "sent"
    retryable_failure = "retryable_failure"
    permanent_failure = "permanent_failure"
    blocked_by_policy = "blocked_by_policy"


class RawEventStatus(StrEnum):
    """Processing status for an authenticated provider webhook delivery."""

    received = "received"
    processed = "processed"
    ignored = "ignored"
    duplicate = "duplicate"


class WebhookResultStatus(StrEnum):
    """Status values returned by webhook application handling."""

    processed = "processed"
    ignored = "ignored"
    duplicate = "duplicate"


class PolicyStage(StrEnum):
    """Deterministic policy checkpoints inside a workflow run."""

    pre_model = "pre_model"
    post_model = "post_model"


class PolicyRule(StrEnum):
    """Stable rule IDs explaining why a workflow or outbound action was blocked."""

    ingress_customer_public_inbound_required = (
        "ingress.customer_public_inbound_required"
    )
    conversation_not_replyable = "conversation.not_replyable"
    conversation_resolved = "conversation.resolved"
    conversation_wootpilot_paused = "conversation.wootpilot_paused"
    conversation_human_active = "conversation.human_active"
    conversation_assigned_to_human = "conversation.assigned_to_human"
    conversation_safety_state_missing = "conversation.safety_state_missing"
    conversation_id_mismatch = "conversation.id_mismatch"
    channel_not_replyable = "channel.not_replyable"
    channel_resolved = "channel.resolved"
    channel_wootpilot_paused = "channel.wootpilot_paused"
    channel_assigned_to_human = "channel.assigned_to_human"
    intent_human_requested = "intent.human_requested"
    model_no_proposal = "model.no_proposal"
    model_proposal_failed = "model.proposal_failed"
    public_no_internal_reasoning = "public.no_internal_reasoning"
    public_risk_requires_review = "public.risk_requires_review"
    public_proposal_risk_requires_review = "public.proposal_risk_requires_review"
    public_price_requires_mentionable_snapshot = (
        "public.price_requires_mentionable_snapshot"
    )
    mode_public_reply_not_enabled = "mode.public_reply_not_enabled"
    production_public_auto_not_enabled = "production_public_auto_not_enabled"
    content_empty = "content.empty"
    unknown_action_kind = "unknown_action_kind"


class CheckpointerProfile(StrEnum):
    """LangGraph checkpoint backend profiles selected by runtime settings."""

    none = "none"
    memory = "memory"
    sqlite = "sqlite"
    postgres = "postgres"


class ModelProvider(StrEnum):
    """Model proposal adapter selected by runtime settings."""

    fake = "fake"
    openrouter = "openrouter"


class CatalogConnectorMode(StrEnum):
    """WooCommerce catalog adapter profile selected by runtime settings."""

    mock = "mock"
    store_api = "store_api"


class WebhookSignatureMode(StrEnum):
    """Webhook signature verification algorithm profile."""

    chatwoot_hmac_sha256 = "chatwoot-hmac-sha256"


class ContextSnapshotKind(StrEnum):
    """Kinds of context snapshots persisted for auditability."""

    catalog = "catalog"


class AuditEventType(StrEnum):
    """Audit event names emitted by application use cases."""

    channel_state_updated = "channel_state_updated"
    webhook_ignored = "webhook_ignored"
    message_ignored = "message_ignored"
    support_workflow_completed = "support_workflow_completed"


class RiskSignal(StrEnum):
    """Stable non-policy risk markers carried through triage and context."""

    catalog_load_failed = "catalog.load_failed"
    catalog_no_match = "catalog.no_match"


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
    """Point-in-time product price facts with policy visibility flags.

    `can_mention` is the key policy boundary: a price may be known internally
    while still being unsafe for a customer-visible model reply because it is
    hidden, stale, quote-only, or otherwise restricted by connector policy.
    """

    model_config = ConfigDict(strict=True)

    amount: Money | None = None
    display_text: str | None = None
    can_mention: bool = False
    quote_required: bool = False
    hidden: bool = False
    stale: bool = False
    reason: str | None = None


class AvailabilitySnapshot(BaseModel):
    """Point-in-time availability facts with public-disclosure constraints."""

    model_config = ConfigDict(strict=True)

    is_available: bool | None = None
    display_text: str | None = None
    can_mention: bool = False
    hidden_quantity: bool = True
    uncertain_reasons: list[str] = Field(default_factory=list)


class ProductSnapshot(BaseModel):
    """Policy-safe product facts passed to model and deterministic checks."""

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
    """Catalog context attached to one workflow run.

    The `snapshot_id` points at the persisted copy used by audit records. Model
    prompts and policy checks should use this object rather than reaching back
    into a live connector mid-graph.
    """

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
    """Provider message translated into WootPilot's channel-neutral contract."""

    model_config = ConfigDict(strict=True)

    id: str
    raw_event_id: str
    tenant_id: str
    provider: Provider = Provider.chatwoot
    provider_account_id: str = ""
    provider_inbox_id: str = ""
    provider_conversation_id: str = ""
    provider_message_id: str = ""
    provider_contact_id: str | None = None
    channel_id: str
    conversation_id: str
    message_id: str
    contact_id: str | None = None
    direction: MessageDirection
    visibility: MessageVisibility
    author_type: MessageAuthorType
    content: str
    attachments: list[AttachmentMetadata] = Field(default_factory=list)
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("provider", mode="before")
    @classmethod
    def coerce_provider(cls, value: Provider | str) -> Provider:
        return value if isinstance(value, Provider) else Provider(str(value))

    @field_validator("direction", mode="before")
    @classmethod
    def coerce_direction(cls, value: MessageDirection | str) -> MessageDirection:
        return (
            value
            if isinstance(value, MessageDirection)
            else MessageDirection(str(value))
        )

    @field_validator("visibility", mode="before")
    @classmethod
    def coerce_visibility(cls, value: MessageVisibility | str) -> MessageVisibility:
        return (
            value
            if isinstance(value, MessageVisibility)
            else MessageVisibility(str(value))
        )

    @field_validator("author_type", mode="before")
    @classmethod
    def coerce_author_type(cls, value: MessageAuthorType | str) -> MessageAuthorType:
        return (
            value
            if isinstance(value, MessageAuthorType)
            else MessageAuthorType(str(value))
        )

    def is_customer_public_inbound(self) -> bool:
        """Return whether this message is eligible to start agent handling."""

        return (
            self.direction is MessageDirection.inbound
            and self.visibility is MessageVisibility.public
            and self.author_type is MessageAuthorType.customer
            and bool(self.content.strip())
        )

    def is_human_public_reply(self) -> bool:
        """Return whether this message marks a human as active in Chatwoot."""

        return (
            self.direction is MessageDirection.outbound
            and self.visibility is MessageVisibility.public
            and self.author_type is MessageAuthorType.human_agent
        )


class ChannelEvent(BaseModel):
    """Non-message Chatwoot conversation event that updates local safety state."""

    model_config = ConfigDict(strict=True)

    id: str
    raw_event_id: str
    event_type: str
    tenant_id: str
    channel_id: str
    conversation_id: str
    status: ConversationStatus | None = None
    replyable: bool | None = None
    paused: bool = False
    auto_ok: bool = False
    assigned_agent_id: str | None = None
    assigned_team_id: str | None = None
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("status", mode="before")
    @classmethod
    def coerce_status(
        cls, value: ConversationStatus | str | None
    ) -> ConversationStatus | None:
        if value in {None, ""}:
            return None
        return (
            value
            if isinstance(value, ConversationStatus)
            else ConversationStatus(str(value))
        )


class ConversationState(BaseModel):
    """Current safety state for a provider conversation.

    This model is intentionally conservative. `auto_ok` is the explicit escape
    hatch that allows automation to continue despite assignment or recent human
    activity; without it, WootPilot should assume a human is in control.
    """

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
    status: ConversationStatus | None = None
    replyable: bool = True
    paused: bool = False
    auto_ok: bool = False
    updated_at: datetime

    @field_validator("status", mode="before")
    @classmethod
    def coerce_status(
        cls, value: ConversationStatus | str | None
    ) -> ConversationStatus | None:
        if value in {None, ""}:
            return None
        return (
            value
            if isinstance(value, ConversationStatus)
            else ConversationStatus(str(value))
        )


class TriageResult(BaseModel):
    model_config = ConfigDict(strict=True)

    should_invoke: bool
    intent: str
    risk_signals: list[str] = Field(default_factory=list)
    reason: str | None = None


class PolicyDecision(BaseModel):
    model_config = ConfigDict(strict=True)

    id: str
    stage: PolicyStage
    outcome: PolicyOutcome
    rule_ids: list[PolicyRule] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    @field_validator("stage", mode="before")
    @classmethod
    def coerce_stage(cls, value: PolicyStage | str) -> PolicyStage:
        return value if isinstance(value, PolicyStage) else PolicyStage(str(value))

    @field_validator("rule_ids", mode="before")
    @classmethod
    def coerce_rule_ids(cls, value: list[PolicyRule | str]) -> list[PolicyRule]:
        return [
            item if isinstance(item, PolicyRule) else PolicyRule(str(item))
            for item in value
        ]


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
    rule_ids: list[PolicyRule] = Field(default_factory=list)
    risk_reasons: list[str] = Field(default_factory=list)

    @field_validator("rule_ids", mode="before")
    @classmethod
    def coerce_rule_ids(cls, value: list[PolicyRule | str]) -> list[PolicyRule]:
        return [
            item if isinstance(item, PolicyRule) else PolicyRule(str(item))
            for item in value
        ]


class QueuedOutboundAction(BaseModel):
    """Outbound action read model consumed by the executor.

    The repository builds this from SQLAlchemy rows so application services can
    evaluate delivery policy without depending on ORM implementation details.
    """

    model_config = ConfigDict(strict=True)

    id: str
    tenant_id: str
    channel_id: str
    conversation_id: str
    source_message_id: str
    action_kind: AgentActionKind
    content: str
    safety_context: dict[str, Any] = Field(default_factory=dict)
    status: OutboundActionStatus
    attempt_count: int = 0

    @field_validator("action_kind", mode="before")
    @classmethod
    def coerce_action_kind(cls, value: AgentActionKind | str) -> AgentActionKind:
        return (
            value
            if isinstance(value, AgentActionKind)
            else AgentActionKind(str(value))
        )

    @field_validator("status", mode="before")
    @classmethod
    def coerce_status(cls, value: OutboundActionStatus | str) -> OutboundActionStatus:
        return (
            value
            if isinstance(value, OutboundActionStatus)
            else OutboundActionStatus(str(value))
        )
