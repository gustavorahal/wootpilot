from __future__ import annotations

import json
import logging
import os

import pytest

from wootpilot.observability import (
    JsonEventFormatter,
    configure_langsmith,
    log_event,
    workflow_log_fields,
    workflow_trace_enabled,
    workflow_trace_update,
)
from wootpilot.settings import Settings


def test_configure_langsmith_disables_tracing(monkeypatch) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "true")

    configure_langsmith(Settings(langsmith_tracing=False))

    assert os.environ["LANGSMITH_TRACING"] == "false"


def test_configure_langsmith_sets_standard_environment(monkeypatch) -> None:
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGSMITH_PROJECT", raising=False)
    monkeypatch.delenv("LANGSMITH_ENDPOINT", raising=False)

    configure_langsmith(
        Settings(
            langsmith_tracing=True,
            langsmith_api_key="lsv2-test",
            langsmith_project="wootpilot-tests",
            langsmith_endpoint="https://langsmith.example.test",
        )
    )

    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGSMITH_API_KEY"] == "lsv2-test"
    assert os.environ["LANGSMITH_PROJECT"] == "wootpilot-tests"
    assert os.environ["LANGSMITH_ENDPOINT"] == "https://langsmith.example.test"


def test_configure_langsmith_requires_api_key() -> None:
    with pytest.raises(ValueError, match="LANGSMITH_API_KEY"):
        configure_langsmith(Settings(langsmith_tracing=True, langsmith_api_key=""))


def test_workflow_log_fields_flag_high_latency_without_content() -> None:
    fields = workflow_log_fields(
        agent_run_id="run-1",
        raw_event_id="raw-1",
        normalized_message_id="message-1",
        tenant_id="tenant-1",
        channel_id="channel-1",
        conversation_id="conversation-1",
        automation_mode="observe",
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


def test_workflow_trace_enabled_only_for_local_profiles() -> None:
    assert workflow_trace_enabled(env="local", enabled=True) is True
    assert workflow_trace_enabled(env="public_dev", enabled=True) is True
    assert workflow_trace_enabled(env="test", enabled=True) is False
    assert workflow_trace_enabled(env="production", enabled=True) is False
    assert workflow_trace_enabled(env="local", enabled=False) is False


def test_workflow_trace_update_prints_developer_content(capsys) -> None:
    class Proposal:
        action_kind = "public_message"
        confidence = 0.9
        risk_reasons = []
        public_message = "Customer-visible generated reply"
        private_note = "Internal suggested note"

    workflow_trace_update(
        enabled=True,
        node="generate_proposal",
        update={"agent_proposal": Proposal()},
    )

    captured = capsys.readouterr()
    assert "generate_proposal" in captured.err
    assert '"proposal_action": "public_message"' in captured.err
    assert "Customer-visible generated reply" in captured.err
    assert "Internal suggested note" in captured.err


def test_workflow_trace_update_pretty_prints_json_payload(capsys) -> None:
    workflow_trace_update(
        enabled=True,
        node="metadata",
        update={
            "model_metadata": {
                "provider": "openrouter",
                "model": "openai/gpt-4.1-mini",
                "structured_method": "function_calling",
                "latency_ms": 1234,
            }
        },
    )

    captured = capsys.readouterr()
    assert "metadata" in captured.err
    assert '{\n  "latency_ms": 1234,' in captured.err
    assert '"model": "openai/gpt-4.1-mini"' in captured.err
    assert '"model_provider": "openrouter"' in captured.err
