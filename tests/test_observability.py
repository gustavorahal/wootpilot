from __future__ import annotations

import json
import logging

from wootpilot.observability import (
    JsonEventFormatter,
    log_event,
    workflow_log_fields,
)


def test_workflow_log_fields_flag_high_latency_without_content() -> None:
    fields = workflow_log_fields(
        agent_run_id="run-1",
        raw_event_id="raw-1",
        normalized_message_id="message-1",
        tenant_id="tenant-1",
        channel_id="channel-1",
        conversation_id="conversation-1",
        bot_mode="shadow",
        status="proposed",
        action_kind="none",
        rule_ids=["policy.safe"],
        risk_reasons=[],
        model_metadata={
            "provider": "openrouter",
            "model": "openai/gpt-4.1-mini",
            "structured_method": "json_schema",
            "latency_ms": 12001,
            "token_usage": {"input_tokens": 100},
        },
        high_latency_threshold_ms=10000,
    )

    assert fields["high_latency"] is True
    assert fields["latency_ms"] == 12001
    assert fields["model_provider"] == "openrouter"
    assert "content" not in fields
    assert "token_usage" not in fields


def test_json_event_formatter_renders_structured_fields() -> None:
    logger = logging.getLogger("wootpilot.tests.observability")
    record = logger.makeRecord(
        name=logger.name,
        level=logging.INFO,
        fn=__file__,
        lno=1,
        msg="support_workflow_completed",
        args=(),
        exc_info=None,
    )
    record.wootpilot_event = "support_workflow_completed"
    record.wootpilot_fields = {"status": "proposed", "high_latency": False}

    payload = json.loads(JsonEventFormatter().format(record))

    assert payload == {
        "event": "support_workflow_completed",
        "high_latency": False,
        "level": "info",
        "logger": "wootpilot.tests.observability",
        "status": "proposed",
    }


def test_log_event_attaches_safe_structured_fields(caplog) -> None:
    logger = logging.getLogger("wootpilot.tests.log_event")
    caplog.set_level(logging.INFO, logger=logger.name)

    log_event(logger, "outbound_action_completed", action_id="a1", status="sent")

    record = caplog.records[-1]
    assert record.wootpilot_event == "outbound_action_completed"
    assert record.wootpilot_fields == {"action_id": "a1", "status": "sent"}
