"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

from functools import cache
from pathlib import Path

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from wootpilot.domain.models import (
    AutomationMode,
    CatalogConnectorMode,
    CheckpointerProfile,
    CustomerLocale,
    ModelProvider,
    RuntimeEnvironment,
    WebhookSignatureMode,
)

__all__ = ["Settings", "get_settings", "reset_settings_cache"]


class Settings(BaseSettings):
    """Runtime settings are injected into services instead of read globally."""

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        extra="ignore",
    )

    env: RuntimeEnvironment = RuntimeEnvironment.local
    log_level: str = "info"
    workflow_trace: bool = True
    model_high_latency_ms: int = 10000
    public_base_url: AnyHttpUrl = "http://localhost:8000"  # type: ignore[assignment]
    webhook_path: str = "/webhooks/chatwoot"
    local_health_url: str = "http://127.0.0.1:8000/health"

    db_url: str = "sqlite+aiosqlite:///./data/wootpilot.db"
    checkpointer: CheckpointerProfile = CheckpointerProfile.memory

    automation_mode: AutomationMode = AutomationMode.public_reply
    response_locale: CustomerLocale = CustomerLocale.pt_br
    human_operator_active_ttl_seconds: int = 900
    webhook_replay_window_seconds: int = 300
    outbound_retry_delay_seconds: int = 60
    outbound_max_attempts: int = 3

    chatwoot_base_url: AnyHttpUrl = "http://localhost:3000"  # type: ignore[assignment]
    chatwoot_public_url: AnyHttpUrl = "http://localhost:3000"  # type: ignore[assignment]
    chatwoot_account_id: str = "change-me"
    chatwoot_api_token: str = "change-me"
    chatwoot_webhook_name: str = "WootPilot laptop tunnel"
    chatwoot_webhook_secret: str = "change-me"
    chatwoot_webhook_signature_mode: WebhookSignatureMode = (
        WebhookSignatureMode.chatwoot_hmac_sha256
    )
    chatwoot_webhook_signature_header: str = "x-chatwoot-signature"
    chatwoot_webhook_timestamp_header: str = "x-chatwoot-timestamp"
    chatwoot_webhook_delivery_header: str = "x-chatwoot-delivery"
    chatwoot_update_status_after_public_reply: bool = False
    chatwoot_public_reply_status: str = "pending"
    chatwoot_mark_needs_human_on_private_review: bool = True
    chatwoot_needs_human_label: str = "wootpilot-needs-human"

    model_provider: ModelProvider = ModelProvider.fake
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4.1-mini"

    catalog_connector_mode: CatalogConnectorMode = CatalogConnectorMode.mock
    mock_catalog_path: Path = Field(
        default=Path("./data/mock-woocommerce/catalog.demo-car-parts.json")
    )
    woocommerce_store_api_base_url: str = ""


@cache
def get_settings() -> Settings:
    """Return process-cached settings loaded from environment and `.env` files."""

    return Settings()


def reset_settings_cache() -> None:
    """Clear cached settings so tests can observe environment changes."""

    get_settings.cache_clear()
