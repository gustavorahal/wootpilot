"""Runtime configuration vocabulary used across application boundaries."""

from __future__ import annotations

from enum import StrEnum


class BotMode(StrEnum):
    """Operating modes that control how far WootPilot may act on a turn.

    - `shadow` proves webhook, context, model, policy, audit, and logging paths
    without writing to Chatwoot. 
    - `copilot` writes private notes for human review.
    - `limited_auto` may write public replies, but only after deterministic policy
    approves the exact content and the outbound executor re-checks channel
    safety.
    """

    shadow = "shadow"
    copilot = "copilot"
    limited_auto = "limited_auto"


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
