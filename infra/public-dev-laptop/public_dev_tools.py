"""Utilities for managing the public-dev Chatwoot laptop loop.

These helpers intentionally use only the Python standard library so the public
dev harness works before WootPilot's application dependencies are installed.
They treat Chatwoot as the source of truth for webhook secrets and avoid
printing sensitive token or secret values.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

WEBHOOK_NAME_DEFAULT = "WootPilot laptop tunnel"
LOCAL_HEALTH_URL_DEFAULT = "http://127.0.0.1:8000/health"


@dataclass(frozen=True)
class RuntimeConfig:
    root: Path
    env_file: Path
    values: dict[str, str]

    def get(self, key: str, default: str = "") -> str:
        return self.values.get(key, default).strip()

    def require(self, key: str) -> str:
        value = self.get(key)
        if is_placeholder(value):
            raise UserFacingError(
                f"{key} is missing or still uses a placeholder in {self.env_file}"
            )
        return value


class UserFacingError(Exception):
    """An expected operator-facing setup error."""


def main_for(command: str) -> int:
    try:
        if command == "sync":
            return sync_webhook()
        if command == "show":
            return show_webhooks()
        if command == "doctor":
            return doctor()
    except UserFacingError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    raise UserFacingError(f"unknown command: {command}")


def load_config() -> RuntimeConfig:
    root = Path(__file__).resolve().parents[2]
    env_file = root / ".env.local"
    if not env_file.exists():
        raise UserFacingError(
            "missing .env.local; copy .env.public-dev.example to .env.local first"
        )

    values = parse_env_file(env_file)
    for key, value in os.environ.items():
        if key.startswith("WOOTPILOT_"):
            values[key] = value
    return RuntimeConfig(root=root, env_file=env_file, values=values)


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def is_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    return (
        not lowered
        or lowered == "change-me"
        or lowered.startswith("<")
        or "<your-" in lowered
        or "<chatwoot-" in lowered
    )


def expected_webhook_url(config: RuntimeConfig) -> str:
    public_base_url = config.require("WOOTPILOT_PUBLIC_BASE_URL").rstrip("/")
    webhook_path = config.get("WOOTPILOT_WEBHOOK_PATH", "/webhooks/chatwoot")
    if not webhook_path.startswith("/"):
        webhook_path = f"/{webhook_path}"
    return f"{public_base_url}{webhook_path}"


def webhook_name(config: RuntimeConfig) -> str:
    return config.get("WOOTPILOT_CHATWOOT_WEBHOOK_NAME", WEBHOOK_NAME_DEFAULT)


def subscriptions(config: RuntimeConfig) -> list[str]:
    path = config.root / "infra" / "public-dev-laptop" / "webhook-subscriptions.json"
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, list) or not all(
        isinstance(item, str) for item in loaded
    ):
        raise UserFacingError(f"invalid subscription list in {path}")
    return loaded


def chatwoot_api_url(config: RuntimeConfig, suffix: str) -> str:
    base_url = config.require("WOOTPILOT_CHATWOOT_BASE_URL").rstrip("/")
    account_id = config.require("WOOTPILOT_CHATWOOT_ACCOUNT_ID")
    return f"{base_url}/api/v1/accounts/{account_id}{suffix}"


def request_json(
    method: str,
    url: str,
    token: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 20,
) -> dict[str, Any]:
    body = None
    headers = {
        "Accept": "application/json",
        "User-Agent": "WootPilotPublicDevHarness/1.0",
        # Use the hyphenated form for public Cloudflare/Caddy paths. Rails still
        # exposes it to Chatwoot as api_access_token, while underscore headers can
        # be stripped before they reach the app.
        "api-access-token": token,
    }
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")[:500]
        raise UserFacingError(
            f"Chatwoot API returned HTTP {exc.code} for {method} {url}: {details}"
        ) from exc
    except urllib.error.URLError as exc:
        raise UserFacingError(f"could not reach Chatwoot API at {url}: {exc}") from exc

    if not response_body.strip():
        return {}
    try:
        loaded = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise UserFacingError(
            f"Chatwoot API returned non-JSON response from {url}"
        ) from exc
    if not isinstance(loaded, dict):
        raise UserFacingError(f"Chatwoot API returned unexpected response from {url}")
    return loaded


def list_webhooks(config: RuntimeConfig) -> list[dict[str, Any]]:
    token = config.require("WOOTPILOT_CHATWOOT_API_TOKEN")
    data = request_json("GET", chatwoot_api_url(config, "/webhooks"), token)
    webhooks = data.get("payload", {}).get("webhooks", [])
    if not isinstance(webhooks, list):
        raise UserFacingError("Chatwoot webhook list response had an unexpected shape")
    return [item for item in webhooks if isinstance(item, dict)]


def webhook_from_response(data: dict[str, Any]) -> dict[str, Any]:
    webhook = data.get("payload", {}).get("webhook")
    if not isinstance(webhook, dict):
        raise UserFacingError("Chatwoot webhook response had an unexpected shape")
    return webhook


def sync_webhook() -> int:
    config = load_config()
    token = config.require("WOOTPILOT_CHATWOOT_API_TOKEN")
    name = webhook_name(config)
    url = expected_webhook_url(config)
    desired_subscriptions = subscriptions(config)
    payload: dict[str, Any] = {
        "webhook": {
            "name": name,
            "url": url,
            "subscriptions": desired_subscriptions,
        }
    }

    inbox_id = config.get("WOOTPILOT_CHATWOOT_WEBHOOK_INBOX_ID")
    if inbox_id and not is_placeholder(inbox_id):
        payload["webhook"]["inbox_id"] = inbox_id

    existing = find_managed_webhook(list_webhooks(config), name, url)
    if existing:
        webhook_id = existing.get("id")
        if webhook_id is None:
            raise UserFacingError("matching Chatwoot webhook did not include an id")
        data = request_json(
            "PATCH",
            chatwoot_api_url(config, f"/webhooks/{webhook_id}"),
            token,
            payload,
        )
        webhook = webhook_from_response(data)
        action = "updated"
    else:
        data = request_json(
            "POST",
            chatwoot_api_url(config, "/webhooks"),
            token,
            payload,
        )
        webhook = webhook_from_response(data)
        action = "created"

    secret = str(webhook.get("secret") or "").strip()
    if is_placeholder(secret):
        raise UserFacingError("Chatwoot did not return a webhook secret")
    update_env_value(config.env_file, "WOOTPILOT_CHATWOOT_WEBHOOK_SECRET", secret)

    print(f"{action} Chatwoot webhook: {name}")
    print(f"id: {webhook.get('id')}")
    print(f"url: {webhook.get('url')}")
    print(f"subscriptions: {', '.join(webhook.get('subscriptions') or [])}")
    print(f"secret: saved to {config.env_file.name}")
    return 0


def find_managed_webhook(
    webhooks: list[dict[str, Any]],
    name: str,
    url: str,
) -> dict[str, Any] | None:
    by_name = [item for item in webhooks if item.get("name") == name]
    if len(by_name) == 1:
        return by_name[0]
    if len(by_name) > 1:
        raise UserFacingError(
            f"multiple Chatwoot webhooks are named {name!r}; remove duplicates first"
        )

    by_url = [item for item in webhooks if item.get("url") == url]
    if len(by_url) == 1:
        return by_url[0]
    if len(by_url) > 1:
        raise UserFacingError(
            "multiple Chatwoot webhooks already use the target URL; "
            "remove duplicates first"
        )
    return None


def update_env_value(path: Path, key: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    updated = False
    output: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{key}="):
            output.append(f"{key}={value}")
            updated = True
        else:
            output.append(line)
    if not updated:
        if output and output[-1] != "":
            output.append("")
        output.append(f"{key}={value}")
    path.write_text("\n".join(output) + "\n", encoding="utf-8")


def show_webhooks() -> int:
    config = load_config()
    webhooks = list_webhooks(config)
    if not webhooks:
        print("No Chatwoot webhooks found for this account.")
        return 0

    for item in webhooks:
        secret_state = "set" if item.get("secret") else "missing"
        print(f"- id: {item.get('id')}")
        print(f"  name: {item.get('name')}")
        print(f"  url: {item.get('url')}")
        print(f"  subscriptions: {', '.join(item.get('subscriptions') or [])}")
        print(f"  secret: {secret_state}")
    return 0


def doctor() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    passes: list[str] = []

    try:
        config = load_config()
        passes.append(".env.local exists")
    except UserFacingError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    required = [
        "WOOTPILOT_PUBLIC_BASE_URL",
        "WOOTPILOT_WEBHOOK_PATH",
        "WOOTPILOT_CHATWOOT_BASE_URL",
        "WOOTPILOT_CHATWOOT_ACCOUNT_ID",
        "WOOTPILOT_CHATWOOT_API_TOKEN",
    ]
    for key in required:
        value = config.get(key)
        if is_placeholder(value):
            errors.append(f"{key} is missing or still uses a placeholder")
        else:
            passes.append(f"{key} is set")

    public_base_url = config.get("WOOTPILOT_PUBLIC_BASE_URL")
    if public_base_url and not public_base_url.startswith("https://"):
        errors.append("WOOTPILOT_PUBLIC_BASE_URL must be an HTTPS tunnel URL")

    if (
        config.get("WOOTPILOT_CHATWOOT_BASE_URL").rstrip("/")
        != "https://chat.gmrahal.net"
    ):
        warnings.append("WOOTPILOT_CHATWOOT_BASE_URL is not https://chat.gmrahal.net")

    if config.get("WOOTPILOT_BOT_MODE", "shadow") != "shadow":
        warnings.append(
            "WOOTPILOT_BOT_MODE is not shadow; be careful with live traffic"
        )

    if config.get("WOOTPILOT_LIMITED_AUTO_PRODUCTION_ALLOWED") == "true":
        warnings.append("WOOTPILOT_LIMITED_AUTO_PRODUCTION_ALLOWED is true")

    if not errors:
        check_chatwoot_root(config, passes, warnings)
        check_webhook_state(config, passes, warnings, errors)
        check_local_health(config, passes, warnings)

    for line in passes:
        print(f"ok: {line}")
    for line in warnings:
        print(f"warn: {line}")
    for line in errors:
        print(f"error: {line}", file=sys.stderr)

    if errors:
        print(
            f"\npublic-dev doctor failed with {len(errors)} error(s).", file=sys.stderr
        )
        return 1
    print("\npublic-dev doctor passed.")
    return 0


def check_chatwoot_root(
    config: RuntimeConfig, passes: list[str], warnings: list[str]
) -> None:
    base_url = config.get("WOOTPILOT_CHATWOOT_BASE_URL").rstrip("/")
    try:
        request = urllib.request.Request(
            base_url,
            headers={"User-Agent": "WootPilotPublicDevHarness/1.0"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            if response.status < 500:
                passes.append(f"Chatwoot is reachable at {base_url}")
            else:
                warnings.append(
                    f"Chatwoot returned HTTP {response.status} at {base_url}"
                )
    except urllib.error.URLError as exc:
        warnings.append(f"could not reach Chatwoot frontend at {base_url}: {exc}")


def check_webhook_state(
    config: RuntimeConfig,
    passes: list[str],
    warnings: list[str],
    errors: list[str],
) -> None:
    name = webhook_name(config)
    url = expected_webhook_url(config)
    desired_subscriptions = set(subscriptions(config))
    try:
        webhooks = list_webhooks(config)
    except UserFacingError as exc:
        errors.append(str(exc))
        return

    webhook = find_managed_webhook(webhooks, name, url)
    if not webhook:
        errors.append(
            f"Chatwoot webhook {name!r} is not configured; "
            "run ./scripts/public-dev-webhook-sync"
        )
        return

    passes.append(f"Chatwoot webhook {name!r} exists")
    if webhook.get("url") == url:
        passes.append("Chatwoot webhook URL matches .env.local")
    else:
        errors.append(
            "Chatwoot webhook URL does not match "
            f"{config.get('WOOTPILOT_PUBLIC_BASE_URL')}{config.get('WOOTPILOT_WEBHOOK_PATH')}"
        )

    actual_subscriptions = set(webhook.get("subscriptions") or [])
    missing = desired_subscriptions - actual_subscriptions
    if missing:
        errors.append(
            f"Chatwoot webhook is missing subscriptions: {', '.join(sorted(missing))}"
        )
    else:
        passes.append("Chatwoot webhook subscriptions are complete")

    chatwoot_secret = str(webhook.get("secret") or "").strip()
    local_secret = config.get("WOOTPILOT_CHATWOOT_WEBHOOK_SECRET")
    if is_placeholder(local_secret):
        errors.append("WOOTPILOT_CHATWOOT_WEBHOOK_SECRET is missing in .env.local")
    elif chatwoot_secret and local_secret != chatwoot_secret:
        errors.append(
            "WOOTPILOT_CHATWOOT_WEBHOOK_SECRET does not match the "
            "Chatwoot webhook secret"
        )
    else:
        passes.append("local webhook secret matches Chatwoot")


def check_local_health(
    config: RuntimeConfig, passes: list[str], warnings: list[str]
) -> None:
    health_url = config.get("WOOTPILOT_LOCAL_HEALTH_URL", LOCAL_HEALTH_URL_DEFAULT)
    if is_placeholder(health_url):
        return
    try:
        with urllib.request.urlopen(health_url, timeout=5) as response:
            if response.status < 500:
                passes.append(
                    f"local WootPilot health endpoint is reachable at {health_url}"
                )
            else:
                warnings.append(
                    f"local WootPilot health endpoint returned HTTP {response.status}"
                )
    except urllib.error.URLError as exc:
        warnings.append(
            "local WootPilot health endpoint is not reachable yet at "
            f"{health_url}: {exc}"
        )
