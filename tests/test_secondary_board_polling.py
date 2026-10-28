"""The board-state poll reads every readable hardware board (issue #1945, PR C).

Board-state polling used to read the PRIMARY board only (#1243), so a
secondary board never got the "another app changed this board" banner, its
"Save as page", or a remembered external frame. The ONE poll thread now reads
every readable hardware board, sequentially and primary first — still a single
thread, so the single-threaded send invariant the note-array throttle relies on
holds — each at the cadence its own read costs:

* skipped: no client, a virtual (FiestaPanel) board, a driver whose read-back
  is unsupported, a paused board;
* read on a tick only once its own interval has passed since the poll last
  read it — ``board_read_interval_cloud`` for a ``read_back.cost ==
  "network"`` driver, else ``board_read_interval_local``;
* the loop ticks at the shorter of the two, so a local primary keeps its
  cadence exactly.

The post-send refresh follows suit: ``request_board_refresh(board_id)``
refreshes the board that was just written, and the engine asks for it after
every page send to a hardware board — without it a secondary's own send would
read as an external write until the next poll.
"""

from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import src.main as main_module
from src.main import BoardRuntime, DisplayService
from tests.test_per_board_engine import (
    _board,
    _page_service,
    _schedule_service,
    _settings_service,
    _time_service,
)

SENT = {"b1": [[1, 1, 1]], "b2": [[2, 2, 2]]}
EXTERNAL = [[7, 7, 7]]

LOCAL = 30
CLOUD = 180


def _client(*, cost="local", supported=True, virtual=False):
    client = MagicMock()
    client.is_virtual = virtual
    client.read_back = SimpleNamespace(supported=supported, cost=cost, suggested_interval_s=30)
    return client


def _service(clients: dict[str, MagicMock]):
    svc = DisplayService()
    runtimes = {}
    for board_id, client in clients.items():
        rt = BoardRuntime(client=client, board_id=board_id) if client is not None else BoardRuntime(None, board_id)
        if client is not None and board_id in SENT:
            rt.output.frames.record_sent(SENT[board_id])
        runtimes[board_id] = rt
    svc.runtimes = runtimes
    svc._primary_board_id = next(iter(clients))
    return svc


def _settings(board_ids, *, paused=()):
    settings = MagicMock()
    settings.get_primary_board_id.return_value = board_ids[0]
    settings.get_board_settings.return_value = SimpleNamespace(boards=[{"id": b} for b in board_ids])
    settings.is_paused.side_effect = lambda board_id=None: board_id in paused
    settings.get_polling_settings.return_value = SimpleNamespace(
        board_read_interval_local=LOCAL, board_read_interval_cloud=CLOUD
    )
    return settings


@pytest.fixture
def clock(monkeypatch):
    """A controllable ``time.monotonic``/``time.time`` for src.main."""
    now = {"t": 10_000.0}

    class _Time:
        @staticmethod
        def time():
            return now["t"]

        @staticmethod
        def monotonic():
            return now["t"]

        @staticmethod
        def sleep(_seconds):
            pass

    monkeypatch.setattr(main_module, "time", _Time)
    return now


class TestPollEveryBoard:
    def test_poll_reads_every_hardware_board_in_order(self, clock):
        order = []
        b1, b2 = _client(), _client()
        b1.read_current_message.side_effect = lambda: order.append("b1") or SENT["b1"]
        b2.read_current_message.side_effect = lambda: order.append("b2") or SENT["b2"]
        svc = _service({"b1": b1, "b2": b2})

        with patch("src.main.get_settings_service", return_value=_settings(["b1", "b2"])):
            svc._poll_all_boards_once()

        assert order == ["b1", "b2"]
        assert svc.runtimes["b1"].polled_characters == SENT["b1"]
        assert svc.runtimes["b2"].polled_characters == SENT["b2"]

    @pytest.mark.parametrize(
        "case",
        ["paused", "virtual", "read_back_unsupported", "no_client"],
    )
    def test_poll_skips_paused_virtual_and_unreadable_boards(self, clock, case):
        b1 = _client()
        b1.read_current_message.return_value = SENT["b1"]
        b2 = {
            "paused": _client(),
            "virtual": _client(virtual=True),
            "read_back_unsupported": _client(supported=False),
            "no_client": None,
        }[case]
        svc = _service({"b1": b1, "b2": b2})
        settings = _settings(["b1", "b2"], paused=("b2",) if case == "paused" else ())

        with patch("src.main.get_settings_service", return_value=settings):
            svc._poll_all_boards_once()

        if b2 is not None:
            b2.read_current_message.assert_not_called()
        assert svc.runtimes["b2"].polled_characters is None
        b1.read_current_message.assert_called_once()

    def test_cloud_cost_board_waits_for_cloud_interval(self, clock):
        b1, b2 = _client(), _client(cost="network")
        b1.read_current_message.return_value = SENT["b1"]
        b2.read_current_message.return_value = SENT["b2"]
        svc = _service({"b1": b1, "b2": b2})

        with patch("src.main.get_settings_service", return_value=_settings(["b1", "b2"])):
            svc._poll_all_boards_once()
            assert b2.read_current_message.call_count == 1
            clock["t"] += LOCAL  # the next local tick: 30 s later
            svc._poll_all_boards_once()
            assert b1.read_current_message.call_count == 2
            assert b2.read_current_message.call_count == 1, "a cloud board was re-read on the local tick"
            clock["t"] += CLOUD - LOCAL  # 180 s after its last read
            svc._poll_all_boards_once()

        assert b2.read_current_message.call_count == 2

    def test_local_primary_cadence_unchanged(self, clock):
        """Every local tick reads a local primary, as the primary-only poll did."""
        b1 = _client()
        b1.read_current_message.return_value = SENT["b1"]
        svc = _service({"b1": b1})

        with patch("src.main.get_settings_service", return_value=_settings(["b1"])):
            for _ in range(4):
                svc._poll_all_boards_once()
                clock["t"] += LOCAL

        assert b1.read_current_message.call_count == 4

    @pytest.mark.parametrize("concurrent_sleep", [False, True])
    def test_poll_loop_checks_live_cadence_changes_every_second(self, monkeypatch, concurrent_sleep):
        """Reads retain independent gates while settings are checked each second."""
        b1, b2 = _client(cost="network"), _client()
        b1.read_current_message.return_value = SENT["b1"]
        b2.read_current_message.return_value = SENT["b2"]
        svc = _service({"b1": b1, "b2": b2})
        slept = []
        test_thread = threading.current_thread()
        real_time = main_module.time

        def _sleep(seconds):
            if threading.current_thread() is not test_thread:
                real_time.sleep(seconds)
            else:
                slept.append(seconds)
                svc.running = False

        # Keep stdlib time.sleep intact, and leave other services' poll threads
        # alone even when they resolve src.main.time during this test.
        monkeypatch.setattr(
            main_module,
            "time",
            SimpleNamespace(**(vars(real_time) | {"sleep": _sleep})),
        )
        monkeypatch.setattr(svc, "_retry_failed_board_inits", lambda: None)
        if concurrent_sleep:

            def _read_cloud():
                # A background poll from another service can sleep during this
                # pass. It must neither stop this loop nor enter its capture.
                other = threading.Thread(target=lambda: main_module.time.sleep(0))
                other.start()
                other.join(timeout=2)
                assert not other.is_alive()
                return SENT["b1"]

            b1.read_current_message.side_effect = _read_cloud
        with patch("src.main.get_settings_service", return_value=_settings(["b1", "b2"])):
            svc.running = True
            svc._board_poll_loop()

        assert slept == [1]

    def test_secondary_external_write_marks_that_runtime_only(self, clock):
        b1, b2 = _client(), _client()
        b1.read_current_message.return_value = SENT["b1"]
        b2.read_current_message.return_value = EXTERNAL
        svc = _service({"b1": b1, "b2": b2})

        with patch("src.main.get_settings_service", return_value=_settings(["b1", "b2"])):
            svc._poll_all_boards_once()
            clock["t"] += LOCAL
            svc._poll_all_boards_once()

        assert svc.runtimes["b2"].showing_out_of_band is True
        assert svc.runtimes["b2"].external_frame[0] == EXTERNAL
        assert svc.runtimes["b1"].showing_out_of_band is False
        assert svc.runtimes["b1"].external_frame is None

    def test_poll_board_state_once_without_args_still_polls_the_primary(self, clock):
        b1, b2 = _client(), _client()
        b1.read_current_message.return_value = SENT["b1"]
        b2.read_current_message.return_value = SENT["b2"]
        svc = _service({"b1": b1, "b2": b2})

        with patch("src.main.get_settings_service", return_value=_settings(["b1", "b2"])):
            svc._poll_board_state_once()

        b1.read_current_message.assert_called_once()
        b2.read_current_message.assert_not_called()


class TestPerBoardRefresh:
    def test_request_board_refresh_targets_the_named_board(self):
        b1, b2 = _client(), _client()
        b1.read_current_message.return_value = SENT["b1"]
        b2.read_current_message.return_value = SENT["b2"]
        svc = _service({"b1": b1, "b2": b2})
        earlier_b1 = svc.runtimes["b1"].refresh_cancel = MagicMock()
        earlier_b2 = svc.runtimes["b2"].refresh_cancel = MagicMock()

        svc.request_board_refresh("b2", initial_delay_seconds=0.0, max_total_seconds=0.5)
        svc.runtimes["b2"].refresh_thread.join(timeout=2)

        b2.read_current_message.assert_called()
        b1.read_current_message.assert_not_called()
        assert svc.runtimes["b2"].polled_characters == SENT["b2"]
        assert svc.runtimes["b1"].polled_characters is None
        earlier_b2.set.assert_called_once()
        earlier_b1.set.assert_not_called()

    def test_request_board_refresh_without_a_board_is_the_primary(self):
        b1, b2 = _client(), _client()
        b1.read_current_message.return_value = SENT["b1"]
        svc = _service({"b1": b1, "b2": b2})

        svc.request_board_refresh(initial_delay_seconds=0.0, max_total_seconds=0.5)
        svc.runtimes["b1"].refresh_thread.join(timeout=2)

        b1.read_current_message.assert_called()
        b2.read_current_message.assert_not_called()

    def _drive_page_send(self, svc, boards, board_id):
        settings = _settings_service(boards)
        with (
            patch("src.main.get_settings_service", return_value=settings),
            patch("src.main.get_page_service", return_value=_page_service({"pA": {"content": "ALPHA"}})),
            patch("src.main.get_schedule_service", return_value=_schedule_service({b["id"]: "pA" for b in boards})),
            patch("src.main.get_collection_service", return_value=MagicMock()),
            patch("src.time_service.get_time_service", return_value=_time_service()),
            patch("src.main.Config") as cfg,
            patch.object(svc, "_check_trigger_override", return_value=None),
            patch.object(svc, "request_board_refresh") as refresh,
        ):
            cfg.is_silence_mode_active.return_value = False
            cfg.silence_config_for.return_value = {"enabled": False}
            rt = svc.runtimes[board_id]
            svc.check_and_send_for_board(board_id, rt, is_primary=board_id == boards[0]["id"])
        return refresh

    def test_page_send_to_secondary_requests_its_own_refresh(self):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        svc = _service({"b1": _client(), "b2": _client()})
        for client in (svc.runtimes["b1"].client, svc.runtimes["b2"].client):
            client.render.return_value = (True, True)
            client.last_send_throttled = False
            client.last_send_preempted = False

        refresh = self._drive_page_send(svc, boards, "b2")

        refresh.assert_called_once_with("b2")

    def test_page_send_to_a_virtual_board_requests_no_refresh(self):
        boards = [_board("b1", "One"), _board("tv", "TV")]
        svc = _service({"b1": _client(), "tv": _client(virtual=True)})
        tv = svc.runtimes["tv"].client
        tv.render.return_value = (True, True)
        tv.last_send_throttled = False
        tv.last_send_preempted = False

        refresh = self._drive_page_send(svc, boards, "tv")

        refresh.assert_not_called()


class TestPollThreadStartsWithTheEngine:
    """A board added after startup (the setup wizard on a fresh install)
    builds its client through the settings route, so ``vb_client`` is already
    set when the background loop starts the engine — and neither gate enters
    ``initialize()``, the only place the poll thread started. Board-state
    polling then never ran until a restart: no external-write detection, no
    out-of-sync banner, no remembered frame."""

    def test_the_background_loop_starts_the_poll_thread_when_the_client_already_exists(self):
        import threading

        import src.api_server as api

        svc = DisplayService()
        svc.vb_client = _client()
        release = threading.Event()

        def _park(_self):
            release.wait(10)

        def _run():
            api._shutting_down = True

        api._shutting_down = False
        try:
            with (
                patch("src.api_server.get_service", return_value=svc),
                patch.object(DisplayService, "_board_poll_loop", _park),
                patch.object(svc, "initialize") as initialize,
                patch.object(svc, "run", side_effect=_run),
            ):
                api.run_service_background()
            initialize.assert_not_called()
            assert svc._poll_thread is not None
            assert svc._poll_thread.name == "board-state-poll"
            assert svc._poll_thread.is_alive()
        finally:
            api._shutting_down = False
            api._service_running = False
            release.set()
            if svc._poll_thread is not None:
                svc._poll_thread.join(timeout=5)

    def test_a_restart_after_stop_starts_a_poll_loop_that_sees_the_engine_running(self):
        """``POST /stop`` clears ``running``, which ends the poll loop. On
        ``POST /start`` the background loop must set ``running`` before it
        starts the poll thread: started first, the loop's ``while
        self.running`` can read the stale False and exit at once, leaving the
        board unpolled until a restart."""
        import threading

        import src.api_server as api

        svc = DisplayService()
        svc.vb_client = _client()
        svc.running = False  # what POST /stop leaves behind
        seen = []
        entered = threading.Event()

        def _record(self):
            seen.append(self.running)
            entered.set()

        def _run():
            api._shutting_down = True

        api._shutting_down = False
        try:
            with (
                patch("src.api_server.get_service", return_value=svc),
                patch.object(DisplayService, "_board_poll_loop", _record),
                patch.object(svc, "initialize"),
                patch.object(svc, "run", side_effect=_run),
            ):
                api.run_service_background()
            assert entered.wait(5)
            assert seen == [True]
        finally:
            api._shutting_down = False
            api._service_running = False
            svc.running = False
            if svc._poll_thread is not None:
                svc._poll_thread.join(timeout=5)
