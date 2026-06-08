"""Runtime configuration vocabulary used across application boundaries."""

from __future__ import annotations

from enum import StrEnum


class AutomationMode(StrEnum):
    """How far WootPilot may act on a customer turn.

    - `observe` runs the workflow, stores audit/proposal data, and writes
      nothing back to Chatwoot.
    - `assist` writes private notes for human review.
    - `public_reply` may write customer-visible replies, but only after
      deterministic policy approves the exact content and the outbound executor
      re-checks channel safety.
    """

    observe = "observe"
    assist = "assist"
    public_reply = "public_reply"


class RuntimeEnvironment(StrEnum):
    """Deployment profile names that drive safety-sensitive behavior.

    The environment is not just a label for logs. WootPilot uses it to fail
    closed around customer-visible automation, especially production public
    replies.
    """

    local = "local"
    test = "test"
    public_dev = "public_dev"
    production = "production"


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
    """Catalog adapter profile selected by runtime settings."""

    mock = "mock"
    store_api = "store_api"


class WebhookSignatureMode(StrEnum):
    """Webhook signature verification algorithm profile."""

    chatwoot_hmac_sha256 = "chatwoot-hmac-sha256"
