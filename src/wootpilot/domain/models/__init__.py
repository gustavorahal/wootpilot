"""Domain models shared by WootPilot application services and workflows.

The modules in this package are intentionally free of FastAPI, SQLAlchemy,
Chatwoot clients, WooCommerce clients, and model-provider SDKs. They are the
language WootPilot uses after raw external data has been authenticated,
translated, and validated.

Most application code imports from `wootpilot.domain.models` rather than a
specific submodule. The re-export keeps that public domain vocabulary stable
while the package remains organized by concept for humans using "go to
definition" one year from now.
"""

from wootpilot.domain.models.audit import AuditEventType, ContextSnapshotKind
from wootpilot.domain.models.catalog import (
    AvailabilitySnapshot,
    CatalogContext,
    Money,
    PriceSnapshot,
    ProductCategory,
    ProductSearchQuery,
    ProductSnapshot,
    RiskSignal,
)
from wootpilot.domain.models.connectors import (
    ConnectorCapability,
    ConnectorInstallation,
)
from wootpilot.domain.models.conversations import (
    ConversationState,
    ConversationStatus,
)
from wootpilot.domain.models.messages import (
    AttachmentMetadata,
    ChannelEvent,
    MessageAuthorType,
    MessageDirection,
    MessageVisibility,
    NormalizedMessage,
)
from wootpilot.domain.models.outbound import (
    OutboundActionStatus,
    QueuedOutboundAction,
)
from wootpilot.domain.models.policy import (
    PolicyDecision,
    PolicyOutcome,
    PolicyRule,
    PolicyStage,
    TriageResult,
)
from wootpilot.domain.models.proposals import (
    AgentActionKind,
    AgentProposal,
    ModelProposalResult,
)
from wootpilot.domain.models.providers import (
    Provider,
    RawEventStatus,
    WebhookResultStatus,
)
from wootpilot.domain.models.runtime import (
    AutomationMode,
    CatalogConnectorMode,
    CheckpointerProfile,
    CustomerLocale,
    ModelProvider,
    RuntimeEnvironment,
    WebhookSignatureMode,
)
from wootpilot.domain.models.workflow import AgentRunStatus, WorkflowDecision

__all__ = [
    "AgentActionKind",
    "AgentProposal",
    "AgentRunStatus",
    "AttachmentMetadata",
    "AuditEventType",
    "AvailabilitySnapshot",
    "AutomationMode",
    "CatalogConnectorMode",
    "ChannelEvent",
    "CheckpointerProfile",
    "ConnectorCapability",
    "ConnectorInstallation",
    "ContextSnapshotKind",
    "ConversationState",
    "ConversationStatus",
    "CustomerLocale",
    "MessageAuthorType",
    "MessageDirection",
    "MessageVisibility",
    "ModelProposalResult",
    "ModelProvider",
    "Money",
    "NormalizedMessage",
    "OutboundActionStatus",
    "PolicyDecision",
    "PolicyOutcome",
    "PolicyRule",
    "PolicyStage",
    "PriceSnapshot",
    "ProductCategory",
    "ProductSearchQuery",
    "ProductSnapshot",
    "Provider",
    "QueuedOutboundAction",
    "RawEventStatus",
    "RiskSignal",
    "RuntimeEnvironment",
    "CatalogContext",
    "TriageResult",
    "WebhookResultStatus",
    "WebhookSignatureMode",
    "WorkflowDecision",
]
