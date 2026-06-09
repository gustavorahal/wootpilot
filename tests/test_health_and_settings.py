from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from wootpilot.api.main import app
from wootpilot.settings import Settings, reset_settings_cache


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


def test_production_startup_does_not_create_tables(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    values = {
        "ENV": "production",
        "DB_URL": f"sqlite+aiosqlite:///{tmp_path / 'production.db'}",
        "CHATWOOT_WEBHOOK_SECRET": "secret",
        "MODEL_PROVIDER": "fake",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)

    async def fake_init_database(settings: Settings) -> None:
        calls.append(settings.env.value)

    reset_settings_cache()
    monkeypatch.setattr("wootpilot.api.main.init_database", fake_init_database)
    with TestClient(app) as test_client:
        response = test_client.get("/health")
    reset_settings_cache()

    assert response.json() == {"status": "ok", "env": "production"}
    assert calls == []
