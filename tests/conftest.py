from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wootpilot.api.main import app
from wootpilot.settings import reset_settings_cache


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[dict[str, str]]:
    values = {
        "ENV": "test",
        "DB_URL": f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        "CHATWOOT_WEBHOOK_SECRET": "test-secret",
        "MODEL_PROVIDER": "fake",
        "AUTOMATION_MODE": "observe",
        "MOCK_CATALOG_PATH": (
            "./data/mock-woocommerce/catalog.demo-car-parts.json"
        ),
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    reset_settings_cache()
    yield values
    reset_settings_cache()


@pytest.fixture
def client(env: dict[str, str]) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
