from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from wootpilot.settings import Settings


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "env": "test"}


def test_public_dev_settings_parse_native_chatwoot_headers() -> None:
    settings_values: dict[str, Any] = {
        "env": "public_dev",
        "public_base_url": "https://wootpilot-local-dev.gmrahal.net",
        "chatwoot_base_url": "https://chat.gmrahal.net",
        "chatwoot_public_url": "https://chat.gmrahal.net",
        "chatwoot_webhook_signature_header": "x-chatwoot-signature",
        "chatwoot_webhook_timestamp_header": "x-chatwoot-timestamp",
        "chatwoot_webhook_delivery_header": "x-chatwoot-delivery",
    }
    settings = Settings(**settings_values)
    assert str(settings.chatwoot_base_url).rstrip("/") == "https://chat.gmrahal.net"
    assert settings.chatwoot_webhook_signature_header == "x-chatwoot-signature"
