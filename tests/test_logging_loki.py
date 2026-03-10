"""Tests for the Loki logging handler (src/logging_loki.py)."""

import json
import logging
from unittest.mock import patch

import pytest

from src.logging_loki import LokiHandler, _component_from_logger

# ---------------------------------------------------------------------------
# _component_from_logger
# ---------------------------------------------------------------------------

class TestComponentFromLogger:
    """Verify that logger names are mapped to the correct component labels."""

    def test_mqtt_component(self):
        assert _component_from_logger("src.mqtt.client") == "mqtt"

    def test_mqtt_component_exact(self):
        assert _component_from_logger("src.mqtt") == "mqtt"

    def test_api_component(self):
        assert _component_from_logger("src.api_server") == "api"

    def test_core_component(self):
        assert _component_from_logger("src.main") == "core"

    def test_display_component(self):
        assert _component_from_logger("src.displays.service") == "display"

    def test_plugin_component(self):
        assert _component_from_logger("plugins.weather") == "plugin"

    def test_unknown_falls_back_to_app(self):
        assert _component_from_logger("some.other.module") == "app"


# ---------------------------------------------------------------------------
# LokiHandler
# ---------------------------------------------------------------------------

class TestLokiHandler:
    """Unit tests for the LokiHandler logging handler."""

    @pytest.fixture(autouse=True)
    def handler(self):
        """Create a LokiHandler with a very long flush interval so we control flushing."""
        h = LokiHandler(flush_interval=9999)
        h.setFormatter(logging.Formatter("%(message)s"))
        yield h
        h.close()

    def test_emit_buffers_entry(self, handler):
        """Emitting a record should add it to the internal buffer."""
        record = logging.LogRecord(
            name="src.mqtt.client",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="MQTT disconnected",
            args=(),
            exc_info=None,
        )
        handler.emit(record)

        assert len(handler._buffer) == 1
        entry = handler._buffer[0]
        assert entry["labels"]["level"] == "ERROR"
        assert entry["labels"]["component"] == "mqtt"
        assert entry["labels"]["job"] == "fiestaboard"
        assert "MQTT disconnected" in entry["message"]

    def test_build_entry_structure(self, handler):
        """_build_entry should produce correct labels and nanosecond timestamp."""
        record = logging.LogRecord(
            name="src.api_server",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Request processed",
            args=(),
            exc_info=None,
        )
        entry = handler._build_entry(record)

        assert set(entry["labels"].keys()) == {"job", "level", "component", "logger"}
        assert entry["labels"]["component"] == "api"
        # timestamp_ns should be a numeric string (nanoseconds)
        assert entry["timestamp_ns"].isdigit()

    @patch("src.logging_loki.urllib.request.urlopen")
    def test_push_sends_correct_payload(self, mock_urlopen, handler):
        """_push should POST a valid Loki push payload."""
        entries = [
            {
                "labels": {"job": "fiestaboard", "level": "INFO", "component": "mqtt", "logger": "src.mqtt"},
                "timestamp_ns": "1700000000000000000",
                "message": "connected",
            }
        ]
        handler._push(entries)

        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))

        assert "streams" in payload
        assert len(payload["streams"]) == 1
        stream = payload["streams"][0]
        assert stream["stream"]["component"] == "mqtt"
        assert stream["values"][0] == ["1700000000000000000", "connected"]

    @patch("src.logging_loki.urllib.request.urlopen", side_effect=OSError("connection refused"))
    def test_push_handles_loki_unavailable(self, mock_urlopen, handler):
        """When Loki is not running, _push should fail silently."""
        entries = [
            {
                "labels": {"job": "fiestaboard", "level": "ERROR", "component": "app", "logger": "test"},
                "timestamp_ns": "1700000000000000000",
                "message": "test",
            }
        ]
        # Should not raise
        handler._push(entries)
        assert handler._consecutive_failures == 1

    @patch("src.logging_loki.urllib.request.urlopen")
    def test_batch_triggers_flush(self, mock_urlopen, handler):
        """Reaching batch_size entries should trigger an immediate push."""
        handler._batch_size = 3
        for i in range(3):
            record = logging.LogRecord(
                name="src.main",
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg=f"msg {i}",
                args=(),
                exc_info=None,
            )
            handler.emit(record)

        # Buffer should be empty (flushed on 3rd emit)
        assert len(handler._buffer) == 0
        mock_urlopen.assert_called_once()
