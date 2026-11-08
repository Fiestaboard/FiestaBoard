"""MQTT ``current_page`` reports the page the board shows (issue #2436).

Before this fix the sensor was built from the *manual* active page in
settings. Whenever something else picked the page — a schedule, a collection
rotation, a temporary override, silence — MQTT kept reporting the stale
manual page, and because that value never changed, nothing was published
when the board switched pages.

These tests drive the real per-board engine (``check_and_send_active_page``)
with the harness from ``tests/test_per_board_engine.py``, then gather MQTT
state from a ``StatePublisher`` that peeks at that same ``DisplayService``.
"""

import json
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.mqtt.client import MQTTClient
from src.mqtt.config import MQTTConfig
from src.mqtt.discovery import NO_ACTIVE_PAGE_OPTION
from src.mqtt.state import StatePublisher
from tests.test_per_board_engine import (
    _board,
    _drive,
    _page_service,
    _schedule_service,
    _service_with_runtimes,
    _settings_service,
)

# Page ids the engine sends, and the names MQTT should report for them.
PAGE_NAMES = {"pA": "Scheduled", "pX": "Manual", "pS": "Quiet", "pB": "Second"}


def _mqtt_client():
    client = MagicMock(spec=MQTTClient)
    client.publish_state = MagicMock()
    client.publish_attributes = MagicMock()
    client.config = MQTTConfig(enabled=True, base_topic="fiestaboard")
    return client


def _publisher_settings(boards, manual):
    """Settings as the publisher reads them: ``board_id=None`` is the primary."""
    primary = boards[0]["id"]
    svc = MagicMock()
    svc.get_board_settings.return_value = SimpleNamespace(boards=boards)
    svc.get_primary_board_id.return_value = primary
    svc.get_active_page_id.side_effect = lambda board_id=None: manual.get(board_id or primary)
    svc.is_schedule_enabled.return_value = True
    svc.is_paused.return_value = False
    svc.get_transition_settings.return_value = SimpleNamespace(strategy="")
    svc.get_polling_interval.return_value = 60
    return svc


def _publisher_pages():
    pages = [SimpleNamespace(id=pid, name=name) for pid, name in PAGE_NAMES.items()]
    svc = MagicMock()
    svc.list_pages.return_value = pages
    svc.get_page.side_effect = lambda pid: next((p for p in pages if p.id == pid), None)
    return svc


def _gather(svc, boards, manual):
    """Publish once from a fresh publisher; return (state, attributes)."""
    client = _mqtt_client()
    with (
        patch("src.display_runtime.peek_service", return_value=svc),
        patch("src.api_server.peek_service", return_value=svc),
        patch("src.settings.service.get_settings_service", return_value=_publisher_settings(boards, manual)),
        patch("src.pages.service.get_page_service", return_value=_publisher_pages()),
        patch("src.config.Config") as cfg,
    ):
        cfg.is_silence_mode_active.return_value = False
        StatePublisher(client).gather_and_publish()
    state = {c.args[0]: c.args[1] for c in client.publish_state.call_args_list}
    attrs = {c.args[0]: json.loads(c.args[1]) for c in client.publish_attributes.call_args_list}
    return state, attrs


def _engine_pages():
    return _page_service({pid: {"content": name.upper()} for pid, name in PAGE_NAMES.items()})


class TestCurrentPageFollowsTheBoard:
    def test_current_page_reports_the_scheduled_page_not_the_manual_one(self):
        boards = [_board("b1", "One")]
        manual = {"b1": "pX"}
        svc, _clients = _service_with_runtimes(boards)
        _drive(svc, boards, pages=_engine_pages(), schedule=_schedule_service({"b1": "pA"}))

        state, _attrs = _gather(svc, boards, manual)

        assert state["current_page"] == "Scheduled"

    def test_active_page_select_still_reports_the_manual_selection(self):
        """The select is the control, so it keeps the configured page."""
        boards = [_board("b1", "One")]
        manual = {"b1": "pX"}
        svc, _clients = _service_with_runtimes(boards)
        _drive(svc, boards, pages=_engine_pages(), schedule=_schedule_service({"b1": "pA"}))

        state, _attrs = _gather(svc, boards, manual)

        assert state["active_page"] == "Manual"

    def test_current_page_attributes_carry_the_shown_page_and_the_selection(self):
        boards = [_board("b1", "One")]
        manual = {"b1": "pX"}
        svc, _clients = _service_with_runtimes(boards)
        _drive(svc, boards, pages=_engine_pages(), schedule=_schedule_service({"b1": "pA"}))

        _state, attrs = _gather(svc, boards, manual)

        assert attrs["current_page"]["page_id"] == "pA"
        assert attrs["current_page"]["page_index"] == 0
        assert attrs["current_page"]["reference_id"] == "pX"

    def test_secondary_board_attributes_report_its_shown_page(self):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        manual = {"b1": "pX", "b2": "pX"}
        svc, _clients = _service_with_runtimes(boards)
        _drive(svc, boards, pages=_engine_pages(), schedule=_schedule_service({"b1": "pA", "b2": "pB"}))

        _state, attrs = _gather(svc, boards, manual)

        by_board = attrs["current_page"]["by_board"]
        assert by_board["b2"]["page_id"] == "pB"
        assert by_board["b2"]["page_name"] == "Second"
        assert by_board["b2"]["reference_id"] == "pX"

    def test_before_any_send_current_page_falls_back_to_the_selection(self):
        """Nothing sent yet (fresh start): the selection is the best answer.

        A guard on behaviour that must not change, so it passes with or
        without the fix."""
        boards = [_board("b1", "One")]
        svc, _clients = _service_with_runtimes(boards)

        state, attrs = _gather(svc, boards, {"b1": "pX"})

        assert state["current_page"] == "Manual"
        assert attrs["current_page"]["page_id"] == "pX"

    def test_attributes_omit_reference_id_when_the_board_shows_the_selection(self):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        manual = {"b1": "pA", "b2": "pB"}
        svc, _clients = _service_with_runtimes(boards)
        _drive(svc, boards, pages=_engine_pages(), schedule=_schedule_service({"b1": "pA", "b2": "pB"}))

        _state, attrs = _gather(svc, boards, manual)

        assert "reference_id" not in attrs["current_page"]
        assert "reference_id" not in attrs["current_page"]["by_board"]["b2"]

    def test_attributes_omit_reference_id_when_there_is_no_selection(self):
        """A board with no selected page showing no page has nothing to refer to."""
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        svc, _clients = _service_with_runtimes(boards)
        _drive(
            svc,
            boards,
            settings=_settings_service(boards, manual={"b2": "pB"}),
            pages=_engine_pages(),
            schedule=_schedule_service({"b1": "pA", "b2": "pB"}),
            silence=True,
        )

        _state, attrs = _gather(svc, boards, {"b1": "pX"})

        assert attrs["current_page"]["by_board"]["b2"]["page_id"] == ""
        assert "reference_id" not in attrs["current_page"]["by_board"]["b2"]

    def test_temporary_override_reports_the_override_page(self):
        boards = [_board("b1", "One")]
        svc, _clients = _service_with_runtimes(boards)
        override = SimpleNamespace(
            is_inline=False,
            is_expired=lambda: False,
            page_id="pS",
            revert_mode="schedule",
            revert_page_id=None,
        )
        _drive(
            svc,
            boards,
            settings=_settings_service(boards, override=override),
            pages=_engine_pages(),
            schedule=_schedule_service({"b1": "pA"}),
        )

        state, _attrs = _gather(svc, boards, {"b1": "pX"})

        assert state["current_page"] == "Quiet"

    def test_inline_one_off_override_reports_no_page(self):
        """One-off content is recorded as ``__adhoc__``: no stored page."""
        boards = [_board("b1", "One")]
        svc, _clients = _service_with_runtimes(boards)
        override = SimpleNamespace(
            is_inline=True,
            is_expired=lambda: False,
            template=["ONE OFF"],
            line_metadata=None,
            device_type="flagship",
            notes_wide=1,
            notes_tall=1,
            revert_mode="schedule",
            revert_page_id=None,
            page_id=None,
        )
        pages = _engine_pages()
        pages.render_page.side_effect = lambda page, **_kwargs: SimpleNamespace(
            available=True, formatted="ONE OFF", error=None
        )
        _drive(
            svc,
            boards,
            settings=_settings_service(boards, override=override),
            pages=pages,
            schedule=_schedule_service({"b1": "pA"}),
        )
        assert svc.runtimes["b1"].last_active_page_id == "__adhoc__"

        state, _attrs = _gather(svc, boards, {"b1": "pX"})

        assert state["current_page"] == NO_ACTIVE_PAGE_OPTION

    def test_trigger_message_reports_no_page(self):
        boards = [_board("b1", "One")]
        svc, _clients = _service_with_runtimes(boards)
        _drive(
            svc, boards, pages=_engine_pages(), schedule=_schedule_service({"b1": "pA"}), trigger_content="DOOR OPEN"
        )

        state, _attrs = _gather(svc, boards, {"b1": "pX"})

        assert state["current_page"] == NO_ACTIVE_PAGE_OPTION

    def test_silence_indicator_reports_no_page(self):
        boards = [_board("b1", "One")]
        svc, _clients = _service_with_runtimes(boards)
        _drive(svc, boards, pages=_engine_pages(), schedule=_schedule_service({"b1": "pA"}), silence=True)

        state, attrs = _gather(svc, boards, {"b1": "pX"})

        assert state["current_page"] == NO_ACTIVE_PAGE_OPTION
        assert attrs["current_page"]["page_id"] == ""

    def test_silence_page_reports_that_page(self):
        boards = [_board("b1", "One")]
        svc, _clients = _service_with_runtimes(boards)
        _drive(
            svc,
            boards,
            pages=_engine_pages(),
            schedule=_schedule_service({"b1": "pA"}),
            silence=True,
            silence_mode="page",
            silence_page_id="pS",
        )

        state, attrs = _gather(svc, boards, {"b1": "pX"})

        assert state["current_page"] == "Quiet"
        assert attrs["current_page"]["page_id"] == "pS"


class TestPageSendPublishesPromptly:
    def test_page_send_pushes_mqtt_state(self):
        boards = [_board("b1", "One")]
        svc, _clients = _service_with_runtimes(boards)
        with patch("src.display_runtime._publish_mqtt_state_update") as push:
            _drive(svc, boards, pages=_engine_pages(), schedule=_schedule_service({"b1": "pA"}))

        push.assert_called_once_with()

    def test_silence_indicator_send_pushes_mqtt_state(self):
        boards = [_board("b1", "One")]
        svc, _clients = _service_with_runtimes(boards)
        with patch("src.display_runtime._publish_mqtt_state_update") as push:
            _drive(svc, boards, pages=_engine_pages(), schedule=_schedule_service({"b1": "pA"}), silence=True)

        push.assert_called_once_with()

    def test_trigger_message_send_pushes_mqtt_state(self):
        boards = [_board("b1", "One")]
        svc, _clients = _service_with_runtimes(boards)
        with patch("src.display_runtime._publish_mqtt_state_update") as push:
            _drive(
                svc,
                boards,
                pages=_engine_pages(),
                schedule=_schedule_service({"b1": "pA"}),
                trigger_content="DOOR OPEN",
            )

        push.assert_called_once_with()

    def test_unchanged_pass_does_not_push_again(self):
        boards = [_board("b1", "One")]
        svc, _clients = _service_with_runtimes(boards)
        schedule = _schedule_service({"b1": "pA"})
        with patch("src.display_runtime._publish_mqtt_state_update") as push:
            _drive(svc, boards, pages=_engine_pages(), schedule=schedule)
            _drive(svc, boards, pages=_engine_pages(), schedule=schedule)

        assert push.call_count == 1

    def test_failed_page_send_does_not_push(self):
        boards = [_board("b1", "One")]
        svc, clients = _service_with_runtimes(boards)
        clients["b1"].render.return_value = (False, False)
        with patch("src.display_runtime._publish_mqtt_state_update") as push:
            _drive(
                svc,
                boards,
                settings=_settings_service(boards),
                pages=_engine_pages(),
                schedule=_schedule_service({"b1": "pA"}),
            )

        push.assert_not_called()


class TestConcurrentGathers:
    def test_a_slow_gather_cannot_publish_a_stale_value_over_a_newer_one(self):
        """The send worker and the 30 s sync loop both publish. A gather that
        read the old page before the send must not land after the new one."""
        client = _mqtt_client()
        pub = StatePublisher(client)
        first_entered = threading.Event()
        release_first = threading.Event()
        calls = {"n": 0}

        def gather_state():
            calls["n"] += 1
            if calls["n"] == 1:
                first_entered.set()
                release_first.wait(timeout=5)
                return {"current_page": "Old"}
            return {"current_page": "New"}

        with (
            patch.object(pub, "_gather_state", side_effect=gather_state),
            patch.object(pub, "_gather_attributes", return_value={}),
        ):
            slow = threading.Thread(target=pub.gather_and_publish)
            slow.start()
            assert first_entered.wait(timeout=5)
            fast_done = threading.Event()

            def fast_pass():
                pub.gather_and_publish()
                fast_done.set()

            fast = threading.Thread(target=fast_pass)
            fast.start()
            # Unserialized, the fast pass finishes while the slow one is
            # parked; serialized, it cannot start until the slow one ends.
            fast_done.wait(timeout=0.2)
            release_first.set()
            slow.join(timeout=5)
            fast.join(timeout=5)

        published = [c.args[1] for c in client.publish_state.call_args_list if c.args[0] == "current_page"]
        assert published[-1] == "New"
