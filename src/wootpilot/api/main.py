"""FastAPI entry point for WootPilot."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from wootpilot.application.security import verify_chatwoot_signature
from wootpilot.application.webhooks import HandleWebhookEvent
from wootpilot.domain.models import Provider
from wootpilot.observability import configure_logging, log_event
from wootpilot.persistence.database import init_database, make_session_factory
from wootpilot.settings import Settings, get_settings
from wootpilot.time import Clock

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    await init_database(settings)
    app.state.session_factory = make_session_factory(settings)
    yield


app = FastAPI(title="WootPilot", lifespan=lifespan)


def settings_dependency() -> Settings:
    return get_settings()


async def session_dependency(request: Request):
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@app.get("/health")
async def health(settings: Annotated[Settings, Depends(settings_dependency)]):
    return {"status": "ok", "env": settings.env.value}


@app.post("/webhooks/chatwoot")
async def chatwoot_webhook(
    request: Request,
    settings: Annotated[Settings, Depends(settings_dependency)],
    session: Annotated[AsyncSession, Depends(session_dependency)],
):
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
            provider=Provider.chatwoot.value,
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
        provider=Provider.chatwoot.value,
        status=result.get("status"),
        raw_event_id=result.get("raw_event_id"),
        normalized_message_id=result.get("normalized_message_id"),
        workflow_status=result.get("workflow_status"),
        action_kind=result.get("action_kind"),
        latency_ms=round((time.perf_counter() - started) * 1000),
    )
    return result
