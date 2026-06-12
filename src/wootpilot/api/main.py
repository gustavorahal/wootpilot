"""FastAPI entry point for WootPilot."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from wootpilot.application.security import verify_chatwoot_signature
from wootpilot.application.webhooks import HandleWebhookEvent, HandleWebhookResult
from wootpilot.domain.models import Provider, RuntimeEnvironment
from wootpilot.observability import configure_langsmith, configure_logging, log_event
from wootpilot.persistence.database import init_database, make_session_factory
from wootpilot.settings import Settings, get_settings
from wootpilot.time import Clock

logger = logging.getLogger(__name__)

__all__ = ["app", "chatwoot_webhook", "health"]


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize process-wide dependencies before serving requests.

    The app keeps database setup explicit here so request handlers can receive
    sessions from FastAPI dependencies without importing global engine state.

    Args:
        app: FastAPI application whose state stores the session factory.
    """

    settings = get_settings()
    configure_logging(settings.log_level)
    configure_langsmith(settings)
    if _should_initialize_database_on_startup(settings):
        await init_database(settings)
    app.state.session_factory = make_session_factory(settings)
    yield


app = FastAPI(title="WootPilot", lifespan=_lifespan)


def _settings_dependency() -> Settings:
    """Return cached runtime settings for FastAPI dependency injection."""

    return get_settings()


def _should_initialize_database_on_startup(settings: Settings) -> bool:
    """Return whether startup may create fresh alpha-profile tables.

    Production deployments should run Alembic explicitly so schema drift is
    visible during release, not hidden by application startup.
    """

    return settings.env is not RuntimeEnvironment.production


async def _session_dependency(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield one transactional database session per request.

    The broad exception guard is intentionally limited to rollback cleanup and
    immediately re-raises so route-level errors are not hidden.

    Args:
        request: Current FastAPI request containing the app session factory.
    """

    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@app.get("/health")
async def health(
    settings: Annotated[Settings, Depends(_settings_dependency)],
) -> dict[str, str]:
    """Return a small readiness payload for local tunnels and process checks."""

    return {"status": "ok", "env": settings.env.value}


@app.post("/webhooks/chatwoot")
async def chatwoot_webhook(
    request: Request,
    settings: Annotated[Settings, Depends(_settings_dependency)],
    session: Annotated[AsyncSession, Depends(_session_dependency)],
) -> HandleWebhookResult:
    """Authenticate and ingest one Chatwoot webhook delivery.

    The route performs only HTTP-bound concerns: body/header extraction,
    signature verification, request-level logging, and delegation to the webhook
    use case that owns persistence and workflow execution.
    """

    started = time.perf_counter()
    body = await request.body()
    headers = {key.lower(): value for key, value in request.headers.items()}
    try:
        verify_chatwoot_signature(
            settings=settings,
            headers=headers,
            body=body,
            now=Clock().now(),
        )
    except HTTPException as exc:
        log_event(
            logger,
            "webhook_authentication_failed",
            level=logging.WARNING,
            provider=Provider.chatwoot,
            status_code=exc.status_code,
            reason=str(exc.detail),
            latency_ms=round((time.perf_counter() - started) * 1000),
        )
        raise
    handler = HandleWebhookEvent(settings=settings, session=session)
    result = await handler.handle(body=body, headers=headers)
    log_event(
        logger,
        "webhook_handled",
        provider=Provider.chatwoot,
        status=result.get("status"),
        raw_event_id=result.get("raw_event_id"),
        normalized_message_id=result.get("normalized_message_id"),
        workflow_status=result.get("workflow_status"),
        action_kind=result.get("action_kind"),
        latency_ms=round((time.perf_counter() - started) * 1000),
    )
    return result
