"""Unit tests for the per-board display engine (issue #1243 remainder).

These exercise the ``BoardRuntime`` refactor: every configured board is
driven through one unified per-board path (``check_and_send_for_board``)
with its own cached state living on its runtime, so boards never clobber
each other's caches. Covers:

  - per-board routing / state isolation (flagship + note-array in one tick)
  - primary "never goes dark" fallback vs. secondary go-dark semantics
  - per-board manual active page (schedule mode off -> that board's page)
  - partial-failure isolation (one board raising never blocks others)
  - temporary_override evaluated for the primary board only
  - silence as a global decision with per-board delivery + per-board state
  - the note-array send routes through its own client at its own size
"""

import threading
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.main import BoardRuntime, DisplayService

TRANSITIONS = SimpleNamespace(strategy="instant", step_interval_ms=0, step_size=1)


def _board(board_id: str, name: str, **overrides) -> dict:
    board = {
        "id": board_id,
        "name": name,
        "device_type": "flagship",
        "board_color": "black",
        "enabled": True,
        "paused": False,
        "api_mode": "local",
        "host": "mock-host",
        "port": 7000,
        "local_api_key": "test-key",
        "schedule_enabled": True,
    }
    board.update(overrides)
    return board


def _note_array_board(board_id: str, name: str, notes_wide: int, notes_tall: int, **overrides) -> dict:
    return _board(
        board_id,
        name,
        device_type="note_array",
        api_mode="cloud",
        host="",
        local_api_key="",
        cloud_key="",
        note_array_token="test-token",
        notes_wide=notes_wide,
        notes_tall=notes_tall,
        **overrides,
    )


def _time_service():
    svc = MagicMock()
    svc.get_current_time.return_value = datetime(2026, 7, 15, 12, 0, 0)
    return svc


def _settings_service(boards, *, paused=(), schedule_off=(), manual=None, override=None, send_to_board=True):
    """A settings service mock with per-board resolution.

    ``manual`` maps board_id -> manual active page id (used when that
    board's schedule mode is off). ``override`` is the consume result.
    ``send_to_board`` is the OutputSettings.target decision
    (``target="ui"`` -> False).
    """
    manual = manual or {}
    svc = MagicMock()
    svc.get_board_settings.return_value = SimpleNamespace(boards=boards)
    svc.get_primary_board_id.return_value = boards[0]["id"] if boards else None
    svc.is_paused.side_effect = lambda board_id=None: board_id in paused
    svc.is_schedule_enabled.side_effect = lambda board_id=None: board_id not in schedule_off
    svc.get_active_page_id.side_effect = lambda board_id=None: manual.get(board_id)
    svc.get_transition_settings.return_value = TRANSITIONS
    svc.consume_temporary_override.return_value = override
    svc.should_send_to_board.return_value = send_to_board
    return svc


def _page(page_id, device_type="flagship", notes_wide=1, notes_tall=1):
    return SimpleNamespace(
        id=page_id,
        device_type=device_type,
        notes_wide=notes_wide,
        notes_tall=notes_tall,
        transition_strategy=None,
        transition_interval_ms=None,
        transition_step_size=None,
    )


def _page_service(specs):
    """specs: dict page_id -> {"content", "device_type", "notes_wide", "notes_tall"}."""
    svc = MagicMock()

    def _get_page(pid):
        spec = specs.get(pid)
        if spec is None:
            return None
        return _page(pid, spec.get("device_type", "flagship"), spec.get("notes_wide", 1), spec.get("notes_tall", 1))

    def _preview(pid, force_refresh=False, **_kwargs):
        spec = specs.get(pid)
        if spec is None:
            return SimpleNamespace(available=False, formatted="", error="missing")
        return SimpleNamespace(available=True, formatted=spec["content"], error=None)

    svc.get_page.side_effect = _get_page
    svc.preview_page.side_effect = _preview
    svc.list_pages.return_value = [_page(pid) for pid in specs]
    return svc


def _schedule_service(active_by_board):
    svc = MagicMock()
    svc.get_active_page_id.side_effect = lambda t, d, board_id=None: active_by_board.get(board_id)
    return svc


def _service_with_runtimes(boards):
    """Build a DisplayService with a mock-client runtime per board."""
    svc = DisplayService()
    runtimes = {}
    clients = {}
    for board in boards:
        client = MagicMock()
        client.render.return_value = (True, True)
        client._last_characters = None
        # Physical clients have no ``is_virtual`` attribute; a MagicMock would
        # auto-create a truthy one, which the UI-only exemption (issue #1835)
        # reads. Pin it False so these behave as real hardware clients.
        client.is_virtual = False
        clients[board["id"]] = client
        runtimes[board["id"]] = BoardRuntime(client=client, board_id=board["id"])
    svc.runtimes = runtimes
    svc._primary_board_id = boards[0]["id"] if boards else None
    return svc, clients


def _drive(
    svc,
    boards,
    *,
    settings=None,
    pages=None,
    schedule=None,
    silence=False,
    silence_mode="indicator",
    silence_page_id=None,
    with_status=False,
    wait=True,
    trigger_content=None,
):
    """Run one full pass. ``with_status`` uses the wrapper the API endpoints
    call, returning ``(sent, failure reason)`` instead of just ``sent``.
    ``wait=False`` is the engine tick's fire-and-forget mode (issue #1755);
    ``trigger_content`` makes the pass see an active trigger override."""
    settings = settings if settings is not None else _settings_service(boards)
    pages = pages if pages is not None else _page_service({})
    schedule = schedule if schedule is not None else _schedule_service({})
    with (
        patch("src.main.get_settings_service", return_value=settings),
        patch("src.main.get_page_service", return_value=pages),
        patch("src.main.get_schedule_service", return_value=schedule),
        patch("src.main.get_collection_service", return_value=MagicMock()),
        patch("src.time_service.get_time_service", return_value=_time_service()),
        patch("src.main.Config") as cfg,
        patch.object(svc, "_check_trigger_override", return_value=trigger_content),
        patch.object(svc, "request_board_refresh"),
    ):
        cfg.is_silence_mode_active.return_value = silence
        cfg.SILENCE_SCHEDULE_MODE = silence_mode
        cfg.SILENCE_SCHEDULE_INDICATOR_TEXT = "SNOOZING"
        cfg.SILENCE_SCHEDULE_INDICATOR_POSITION = "center"
        cfg.SILENCE_SCHEDULE_PAGE_ID = silence_page_id
        # Silence is resolved per board since issue #1788; every board here
        # shares the same window, which is what `silence=` toggles. The mode
        # and page id ride on that per-board config, not on the Config class
        # attributes, so `silence_mode=`/`silence_page_id=` must land here to
        # reach the silence dispatch at all.
        cfg.silence_config_for.return_value = {
            "enabled": True,
            "start_time": "04:00+00:00",
            "end_time": "15:00+00:00",
            "mode": silence_mode,
            "page_id": silence_page_id,
            "indicator_text": "SNOOZING",
            "indicator_position": "center",
        }
        if with_status:
            return svc.check_and_send_active_page_with_status()
        return svc.check_and_send_active_page(wait=wait)


class TestPerBoardRouting:
    def test_flagship_and_note_array_each_get_their_own_page_at_their_own_size(self):
        boards = [_board("b1", "One"), _note_array_board("b2", "Two", notes_wide=2, notes_tall=2)]
        svc, clients = _service_with_runtimes(boards)
        pages = _page_service(
            {
                "pA": {"content": "ALPHA", "device_type": "flagship"},
                "pB": {"content": "BETA", "device_type": "note_array", "notes_wide": 2, "notes_tall": 2},
            }
        )
        schedule = _schedule_service({"b1": "pA", "b2": "pB"})

        _drive(svc, boards, pages=pages, schedule=schedule)

        clients["b1"].render.assert_called_once()
        rows1 = clients["b1"].render.call_args.args[0]
        assert len(rows1) == 6 and len(rows1[0]) == 22  # flagship

        clients["b2"].render.assert_called_once()
        rows2 = clients["b2"].render.call_args.args[0]
        assert len(rows2) == 6 and len(rows2[0]) == 30  # note-array 2x2 -> 6x30

        assert svc.runtimes["b1"].last_active_page_id == "pA"
        assert svc.runtimes["b2"].last_active_page_id == "pB"

    def test_state_is_isolated_between_runtimes(self):
        """Editing the primary's cache must not affect a secondary's."""
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        svc, _clients = _service_with_runtimes(boards)
        pages = _page_service({"pA": {"content": "ALPHA"}, "pB": {"content": "BETA"}})
        schedule = _schedule_service({"b1": "pA", "b2": "pB"})

        _drive(svc, boards, pages=pages, schedule=schedule)

        assert svc.runtimes["b1"].last_active_page_content == "ALPHA"
        assert svc.runtimes["b2"].last_active_page_content == "BETA"

    def test_primary_client_never_receives_secondary_content(self):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        svc, clients = _service_with_runtimes(boards)
        pages = _page_service({"pB": {"content": "BETA"}})
        schedule = _schedule_service({"b1": None, "b2": "pB"})

        _drive(svc, boards, pages=pages, schedule=schedule)

        # Primary had no scheduled page and no manual page -> no send.
        clients["b1"].render.assert_not_called()
        clients["b2"].render.assert_called_once()

    def test_unchanged_content_is_not_resent(self):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        svc, clients = _service_with_runtimes(boards)
        pages = _page_service({"pB": {"content": "BETA"}})
        schedule = _schedule_service({"b2": "pB"})

        _drive(svc, boards, pages=pages, schedule=schedule)
        _drive(svc, boards, pages=pages, schedule=schedule)

        assert clients["b2"].render.call_count == 1


class TestSkips:
    def test_paused_board_is_skipped(self):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        svc, clients = _service_with_runtimes(boards)
        pages = _page_service({"pB": {"content": "BETA"}})
        schedule = _schedule_service({"b2": "pB"})
        settings = _settings_service(boards, paused=("b2",))

        _drive(svc, boards, settings=settings, pages=pages, schedule=schedule)

        clients["b2"].render.assert_not_called()

    def test_schedule_disabled_board_uses_manual_page(self):
        """Schedule off for a secondary -> its manual by_board page is shown."""
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        svc, clients = _service_with_runtimes(boards)
        pages = _page_service({"pManual": {"content": "MANUAL2"}})
        settings = _settings_service(boards, schedule_off=("b2",), manual={"b2": "pManual"})

        _drive(svc, boards, settings=settings, pages=pages)

        clients["b2"].render.assert_called_once()
        assert svc.runtimes["b2"].last_active_page_id == "pManual"

    def test_secondary_with_no_active_page_goes_dark(self):
        """Unlike the primary, a secondary does NOT default to pages[0]."""
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        svc, clients = _service_with_runtimes(boards)
        pages = _page_service({"pDefault": {"content": "DEFAULT"}})
        settings = _settings_service(boards, schedule_off=("b2",), manual={})

        _drive(svc, boards, settings=settings, pages=pages)

        clients["b2"].render.assert_not_called()

    def test_disabled_board_is_skipped(self):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001, enabled=False)]
        svc, clients = _service_with_runtimes(boards)
        pages = _page_service({"pB": {"content": "BETA"}})
        schedule = _schedule_service({"b2": "pB"})

        _drive(svc, boards, pages=pages, schedule=schedule)

        clients["b2"].render.assert_not_called()


class TestPrimaryFallback:
    def test_primary_defaults_to_first_page_when_no_active_page(self):
        """The primary never goes dark: manual mode with no active page -> pages[0]."""
        boards = [_board("b1", "One", schedule_enabled=False)]
        svc, clients = _service_with_runtimes(boards)
        pages = _page_service({"pFirst": {"content": "FIRST"}})
        settings = _settings_service(boards, schedule_off=("b1",), manual={})

        _drive(svc, boards, settings=settings, pages=pages)

        clients["b1"].render.assert_called_once()
        settings.set_active_page_id.assert_called_once()
        assert svc.runtimes["b1"].last_active_page_id == "pFirst"


class TestPartialFailureIsolation:
    def test_secondary_raising_does_not_block_primary(self):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        svc, clients = _service_with_runtimes(boards)
        clients["b2"].render.side_effect = RuntimeError("board 2 exploded")
        pages = _page_service({"pA": {"content": "ALPHA"}, "pB": {"content": "BETA"}})
        schedule = _schedule_service({"b1": "pA", "b2": "pB"})

        result = _drive(svc, boards, pages=pages, schedule=schedule)

        assert result is True  # primary still sent
        clients["b1"].render.assert_called_once()

    def test_primary_error_isolated_from_secondary(self):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        svc, clients = _service_with_runtimes(boards)
        clients["b1"].render.side_effect = RuntimeError("board 1 exploded")
        pages = _page_service({"pA": {"content": "ALPHA"}, "pB": {"content": "BETA"}})
        schedule = _schedule_service({"b1": "pA", "b2": "pB"})

        result = _drive(svc, boards, pages=pages, schedule=schedule)

        assert result is False  # primary failed gracefully
        clients["b2"].render.assert_called_once()  # secondary unaffected


class TestTemporaryOverridePrimaryOnly:
    def test_override_consumed_only_for_primary(self):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        svc, _clients = _service_with_runtimes(boards)
        pages = _page_service({"pA": {"content": "ALPHA"}, "pB": {"content": "BETA"}})
        schedule = _schedule_service({"b1": "pA", "b2": "pB"})
        settings = _settings_service(boards)

        _drive(svc, boards, settings=settings, pages=pages, schedule=schedule)

        # The override store is a global consume-once resource: it must be
        # consumed exactly once (for the primary), never per-secondary.
        settings.consume_temporary_override.assert_called_once()


class TestPerBoardSilenceDelivery:
    def test_each_board_gets_its_own_snoozing_indicator_sized_to_its_device(self):
        boards = [_board("b1", "One"), _note_array_board("b2", "Two", notes_wide=2, notes_tall=1)]
        svc, clients = _service_with_runtimes(boards)
        pages = _page_service(
            {
                "pA": {"content": "ALPHA"},
                "pB": {"content": "BETA", "device_type": "note_array", "notes_wide": 2, "notes_tall": 1},
            }
        )
        schedule = _schedule_service({"b1": "pA", "b2": "pB"})

        _drive(svc, boards, pages=pages, schedule=schedule, silence=True)

        # Both boards receive a SNOOZING indicator on entering silence, each
        # sized to its own geometry (flagship 6x22, note-array 2x1 -> 3x30).
        rows1 = clients["b1"].render.call_args.args[0]
        assert len(rows1) == 6 and len(rows1[0]) == 22
        rows2 = clients["b2"].render.call_args.args[0]
        assert len(rows2) == 3 and len(rows2[0]) == 30

        # Silence state is tracked per runtime.
        assert svc.runtimes["b1"].snoozing_message_sent is True
        assert svc.runtimes["b2"].snoozing_message_sent is True

    def test_steady_silence_does_not_resend_per_board(self):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        svc, clients = _service_with_runtimes(boards)
        pages = _page_service({"pA": {"content": "ALPHA"}, "pB": {"content": "BETA"}})
        schedule = _schedule_service({"b1": "pA", "b2": "pB"})

        _drive(svc, boards, pages=pages, schedule=schedule, silence=True)
        _drive(svc, boards, pages=pages, schedule=schedule, silence=True)

        # Exactly one send per board (the entering-silence indicator).
        assert clients["b1"].render.call_count == 1
        assert clients["b2"].render.call_count == 1


class TestEngineTickInFlightDedupe:
    """The engine's fire-and-forget passes (issue #1755) must not re-enqueue a
    send that is still queued or executing on the board's worker.

    The dedupe caches are written by post-send bookkeeping, which runs when
    the worker finishes — so during a long transition every engine pass sees
    a "stale" cache. Without the in-flight guard each pass would enqueue the
    same frame again and the transition would replay forever once it landed.
    """

    @staticmethod
    def _blocked_client(clients, board_id):
        """Make one board's mock render block until released; returns (started, release)."""
        started = threading.Event()
        release = threading.Event()

        def blocking_render(*_a, **_k):
            started.set()
            assert release.wait(timeout=10)
            return True, True

        clients[board_id].render.side_effect = blocking_render
        return started, release

    def test_engine_pass_does_not_reenqueue_the_page_send_in_flight(self):
        boards = [_board("b1", "Primary", schedule_enabled=False)]
        svc, clients = _service_with_runtimes(boards)
        started, release = self._blocked_client(clients, "b1")
        settings = _settings_service(boards, schedule_off=("b1",), manual={"b1": "page-1"})
        pages = _page_service({"page-1": {"content": "HELLO"}})
        try:
            _drive(svc, boards, settings=settings, pages=pages, wait=False)
            assert started.wait(timeout=5)
            _drive(svc, boards, settings=settings, pages=pages, wait=False)
        finally:
            release.set()
        assert svc.wait_until_idle(timeout=5)
        assert clients["b1"].render.call_count == 1

    def test_engine_pass_does_not_reenqueue_the_silence_send_in_flight(self):
        boards = [_board("b1", "Primary", schedule_enabled=False)]
        svc, clients = _service_with_runtimes(boards)
        started, release = self._blocked_client(clients, "b1")
        settings = _settings_service(boards, schedule_off=("b1",), manual={"b1": "page-1"})
        pages = _page_service({"page-1": {"content": "HELLO"}})
        try:
            _drive(svc, boards, settings=settings, pages=pages, silence=True, wait=False)
            assert started.wait(timeout=5)
            _drive(svc, boards, settings=settings, pages=pages, silence=True, wait=False)
        finally:
            release.set()
        assert svc.wait_until_idle(timeout=5)
        assert clients["b1"].render.call_count == 1

    def test_engine_pass_does_not_reenqueue_the_trigger_send_in_flight(self):
        boards = [_board("b1", "Primary", schedule_enabled=False)]
        svc, clients = _service_with_runtimes(boards)
        started, release = self._blocked_client(clients, "b1")
        settings = _settings_service(boards, schedule_off=("b1",), manual={"b1": "page-1"})
        pages = _page_service({"page-1": {"content": "HELLO"}})
        try:
            _drive(svc, boards, settings=settings, pages=pages, trigger_content="DOOR OPEN", wait=False)
            assert started.wait(timeout=5)
            _drive(svc, boards, settings=settings, pages=pages, trigger_content="DOOR OPEN", wait=False)
        finally:
            release.set()
        assert svc.wait_until_idle(timeout=5)
        assert clients["b1"].render.call_count == 1

    def test_enqueue_signals_the_clients_cancel_event_immediately(self):
        """Enqueuing a newer frame preempts a running transition at once.

        A plain render() call sets the client's ``_cancel_transition`` event
        before taking the send lock; with the queue in between, the dispatch
        must mirror that at ENQUEUE time — otherwise an in-flight transition
        would only learn about the newer frame when the worker dequeued it.
        """
        boards = [_board("b1", "Primary", schedule_enabled=False)]
        svc, clients = _service_with_runtimes(boards)
        started, release = self._blocked_client(clients, "b1")
        cancel = threading.Event()
        clients["b1"]._cancel_transition = cancel
        settings = _settings_service(boards, schedule_off=("b1",), manual={"b1": "page-1"})
        pages = _page_service({"page-1": {"content": "HELLO"}, "page-2": {"content": "WORLD"}})
        try:
            _drive(svc, boards, settings=settings, pages=pages, wait=False)
            assert started.wait(timeout=5)
            cancel.clear()  # the first enqueue set it; arm for the observation
            settings2 = _settings_service(boards, schedule_off=("b1",), manual={"b1": "page-2"})
            _drive(svc, boards, settings=settings2, pages=pages, wait=False)
            assert cancel.is_set(), "the newer frame's enqueue must signal the running transition"
        finally:
            release.set()
        assert svc.wait_until_idle(timeout=5)

    def test_wait_mode_still_resends_content_that_is_in_flight(self):
        """A wait=True caller (refresh/force-refresh) skips only on the cache
        dedupe, never on the in-flight guard — while the same frame is still
        being delivered it queues its own send and waits, exactly as an
        inline render() call would have blocked on the send lock."""
        import time as real_time

        boards = [_board("b1", "Primary", schedule_enabled=False)]
        svc, clients = _service_with_runtimes(boards)
        started, release = self._blocked_client(clients, "b1")
        settings = _settings_service(boards, schedule_off=("b1",), manual={"b1": "page-1"})
        pages = _page_service({"page-1": {"content": "HELLO"}})
        _drive(svc, boards, settings=settings, pages=pages, wait=False)
        assert started.wait(timeout=5)

        results: list = []
        caller = threading.Thread(
            target=lambda: results.append(_drive(svc, boards, settings=settings, pages=pages, wait=True))
        )
        caller.start()
        try:
            # The wait=True pass must have QUEUED a second send (same content,
            # first still executing) rather than skipped on the in-flight key.
            worker = svc.runtimes["b1"].send_worker
            deadline = real_time.monotonic() + 5
            while worker._pending is None and real_time.monotonic() < deadline:
                real_time.sleep(0.005)
            assert worker._pending is not None, "wait=True should have queued its own send, not skipped"
        finally:
            release.set()
            caller.join(timeout=5)
        assert svc.wait_until_idle(timeout=5)
        assert results == [True]
        assert clients["b1"].render.call_count == 2


class TestSeams:
    def test_get_board_client_and_get_runtime(self):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        svc, clients = _service_with_runtimes(boards)

        assert svc.get_board_client("b2") is clients["b2"]
        assert svc.get_runtime("b1").board_id == "b1"
        assert svc.get_board_client("nope") is None
        assert svc.get_runtime("nope") is None


class TestBoardRuntime:
    def test_defaults(self):
        rt = BoardRuntime(client=None, board_id="b1")
        assert rt.board_id == "b1"
        assert rt.client is None
        assert rt.last_active_page_content is None
        assert rt.last_active_page_id is None
        assert rt.last_geometry_mismatch is None
        assert rt.last_silence_mode_active is False
        assert rt.snoozing_message_sent is False
        assert rt.polled_characters is None
        assert rt.polled_at is None
        assert rt.refresh_thread is None
        assert rt.refresh_cancel is None


class TestOutputTarget:
    """The display loop must honor OutputSettings.target (issue #1748).

    ``should_send_to_board()`` is False only for ``target="ui"``; the
    background loop used to write to hardware anyway.
    """

    def test_ui_only_target_does_not_write_to_hardware(self):
        boards = [_board("b1", "One")]
        svc, clients = _service_with_runtimes(boards)
        pages = _page_service({"pA": {"content": "ALPHA"}})
        schedule = _schedule_service({"b1": "pA"})
        settings = _settings_service(boards, send_to_board=False)

        sent = _drive(svc, boards, settings=settings, pages=pages, schedule=schedule)

        clients["b1"].render.assert_not_called()
        assert sent is False

    def test_board_target_still_writes_to_hardware(self):
        boards = [_board("b1", "One")]
        svc, clients = _service_with_runtimes(boards)
        pages = _page_service({"pA": {"content": "ALPHA"}})
        schedule = _schedule_service({"b1": "pA"})
        settings = _settings_service(boards, send_to_board=True)

        _drive(svc, boards, settings=settings, pages=pages, schedule=schedule)

        clients["b1"].render.assert_called_once()

    def test_ui_only_target_still_drives_virtual_board(self):
        """A virtual board is the web UI, not hardware (issue #1835).

        ``target="ui"`` means "don't touch hardware", but a FiestaPanel's
        frame is populated only by the render path here. Short-circuiting it
        froze every virtual board on its last frame. ``VirtualBoardClient``
        sets ``is_virtual = True``, which exempts it from the short-circuit.
        """
        boards = [_board("b1", "One")]
        svc, clients = _service_with_runtimes(boards)
        clients["b1"].is_virtual = True
        pages = _page_service({"pA": {"content": "ALPHA"}})
        schedule = _schedule_service({"b1": "pA"})
        settings = _settings_service(boards, send_to_board=False)

        _drive(svc, boards, settings=settings, pages=pages, schedule=schedule)

        clients["b1"].render.assert_called_once()

    def test_paused_virtual_board_is_not_driven_under_ui_only_target(self):
        """The virtual exemption must not reach above the pause short-circuit.

        Pause (issue #970) is hands-off for every board, virtual included.
        The exemption only skips the output-target gate; it must not turn a
        paused panel back on.
        """
        boards = [_board("b1", "One")]
        svc, clients = _service_with_runtimes(boards)
        clients["b1"].is_virtual = True
        pages = _page_service({"pA": {"content": "ALPHA"}})
        schedule = _schedule_service({"b1": "pA"})
        settings = _settings_service(boards, paused=("b1",), send_to_board=False)

        _drive(svc, boards, settings=settings, pages=pages, schedule=schedule)

        clients["b1"].render.assert_not_called()

    def test_silenced_virtual_board_shows_the_indicator_not_its_page(self):
        """The virtual exemption must not reach below into silence handling.

        A driven virtual board still goes through the silence dispatch, so a
        snoozed panel shows the SNOOZING indicator rather than its page.
        """
        boards = [_board("b1", "One")]
        svc, clients = _service_with_runtimes(boards)
        clients["b1"].is_virtual = True
        pages = _page_service({"pA": {"content": "ALPHA"}})
        schedule = _schedule_service({"b1": "pA"})
        settings = _settings_service(boards, send_to_board=False)

        _drive(svc, boards, settings=settings, pages=pages, schedule=schedule, silence=True)

        clients["b1"].render.assert_called_once()
        assert svc.runtimes["b1"].last_active_page_id == "__silence__"
        assert svc.runtimes["b1"].last_active_page_content == "snoozing"

    def test_ui_only_target_does_not_write_to_secondary_hardware(self):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        svc, clients = _service_with_runtimes(boards)
        pages = _page_service({"pA": {"content": "ALPHA"}, "pB": {"content": "BETA"}})
        schedule = _schedule_service({"b1": "pA", "b2": "pB"})
        settings = _settings_service(boards, send_to_board=False)

        _drive(svc, boards, settings=settings, pages=pages, schedule=schedule)

        clients["b2"].render.assert_not_called()


class TestSendTimeGeometryValidation:
    """A page must match its destination board's geometry (issue #1748).

    Render geometry came from the page, so a retargeted page could push a
    6x22 grid at a 3x15 Note.
    """

    def test_page_not_matching_primary_board_geometry_is_not_sent(self):
        boards = [_board("b1", "Small", device_type="note")]
        svc, clients = _service_with_runtimes(boards)
        pages = _page_service({"pA": {"content": "ALPHA", "device_type": "flagship"}})
        schedule = _schedule_service({"b1": "pA"})

        sent = _drive(svc, boards, pages=pages, schedule=schedule)

        clients["b1"].render.assert_not_called()
        assert sent is False

    def test_page_not_matching_secondary_board_geometry_is_not_sent(self):
        boards = [_board("b1", "One"), _board("b2", "Small", device_type="note", port=7001)]
        svc, clients = _service_with_runtimes(boards)
        pages = _page_service(
            {
                "pA": {"content": "ALPHA", "device_type": "flagship"},
                "pB": {"content": "BETA", "device_type": "flagship"},
            }
        )
        schedule = _schedule_service({"b1": "pA", "b2": "pB"})

        _drive(svc, boards, pages=pages, schedule=schedule)

        clients["b1"].render.assert_called_once()
        clients["b2"].render.assert_not_called()

    def test_skipped_mismatch_does_not_poison_the_content_cache(self):
        """After the page is resized to fit, the next tick sends it."""
        boards = [_board("b1", "Small", device_type="note")]
        svc, clients = _service_with_runtimes(boards)
        schedule = _schedule_service({"b1": "pA"})
        mismatched = _page_service({"pA": {"content": "ALPHA", "device_type": "flagship"}})
        fixed = _page_service({"pA": {"content": "ALPHA", "device_type": "note"}})

        _drive(svc, boards, pages=mismatched, schedule=schedule)
        _drive(svc, boards, pages=fixed, schedule=schedule)

        clients["b1"].render.assert_called_once()
        rows = clients["b1"].render.call_args.args[0]
        assert len(rows) == 3 and len(rows[0]) == 15


class TestSilencePageGeometryValidation:
    """The silence page must also match its destination board (issue #1748).

    Since #1788/#1801 silence settings resolve per board from
    ``features.silence_schedule.by_board[board_id]``, with the install-wide
    values as the fallback for every key a board does not override —
    ``page_id`` included. Differently shaped boards therefore inherit the
    *same* silence page, which can only fit one of them.

    #1801 fixed the array's **shape**: ``_send_silence_page`` now sizes the
    array from the board (``_silence_geometry``) instead of the page. But
    ``text_to_board_array`` crops rather than reflows, so a flagship page on a
    Note still arrives 3x15 with its bottom rows and right-hand columns simply
    gone. This gate fixes the **content**: on mismatch we send the board-sized
    SNOOZING indicator instead, so the board reads as snoozing rather than
    showing a mangled page.

    That split is why these tests assert on *which path ran*
    (``last_active_page_id``) and not on dimensions alone — since #1801 both
    paths produce board-sized output, so the shape no longer discriminates
    (issue #1836).
    """

    def test_silence_page_not_matching_board_falls_back_to_board_sized_indicator(self):
        boards = [_board("b1", "Small", device_type="note")]
        svc, clients = _service_with_runtimes(boards)
        pages = _page_service(
            {
                "pA": {"content": "ALPHA", "device_type": "note"},
                "sil": {"content": "QUIET", "device_type": "flagship"},
            }
        )
        schedule = _schedule_service({"b1": "pA"})

        _drive(
            svc,
            boards,
            pages=pages,
            schedule=schedule,
            silence=True,
            silence_mode="page",
            silence_page_id="sil",
        )

        clients["b1"].render.assert_called_once()
        rows = clients["b1"].render.call_args.args[0]
        # Board-shaped (3x15 Note), not the flagship silence page's 6x22.
        assert len(rows) == 3 and len(rows[0]) == 15
        # The shape alone does not discriminate: since #1801 a merely *cropped*
        # page also arrives at 3x15. What pins the gate is that the *indicator*
        # went out (id/content), not a cropped silence page.
        assert svc.runtimes["b1"].last_active_page_id == "__silence__"
        assert svc.runtimes["b1"].last_active_page_content == "snoozing"

    def test_matching_silence_page_is_still_sent(self):
        """Control: a correctly shaped silence page must still reach the board."""
        boards = [_board("b1", "Small", device_type="note")]
        svc, clients = _service_with_runtimes(boards)
        pages = _page_service(
            {
                "pA": {"content": "ALPHA", "device_type": "note"},
                "sil": {"content": "QUIET", "device_type": "note"},
            }
        )
        schedule = _schedule_service({"b1": "pA"})

        _drive(
            svc,
            boards,
            pages=pages,
            schedule=schedule,
            silence=True,
            silence_mode="page",
            silence_page_id="sil",
        )

        clients["b1"].render.assert_called_once()
        assert svc.runtimes["b1"].last_active_page_id == "__silence_page__:sil"

    def test_secondary_board_gets_indicator_when_global_silence_page_is_wrong_shape(self):
        """The flagship silence page fits the primary but not the Note secondary."""
        boards = [_board("b1", "One"), _board("b2", "Small", device_type="note", port=7001)]
        svc, clients = _service_with_runtimes(boards)
        pages = _page_service(
            {
                "pA": {"content": "ALPHA", "device_type": "flagship"},
                "pB": {"content": "BETA", "device_type": "note"},
                "sil": {"content": "QUIET", "device_type": "flagship"},
            }
        )
        schedule = _schedule_service({"b1": "pA", "b2": "pB"})

        _drive(
            svc,
            boards,
            pages=pages,
            schedule=schedule,
            silence=True,
            silence_mode="page",
            silence_page_id="sil",
        )

        # Primary matches the silence page and receives it at 6x22.
        primary_rows = clients["b1"].render.call_args.args[0]
        assert len(primary_rows) == 6 and len(primary_rows[0]) == 22
        assert svc.runtimes["b1"].last_active_page_id == "__silence_page__:sil"

        # Secondary is a Note: indicator at 3x15, never the flagship page.
        secondary_rows = clients["b2"].render.call_args.args[0]
        assert len(secondary_rows) == 3 and len(secondary_rows[0]) == 15
        # Pin the gate: the indicator went out, not a cropped silence page.
        assert svc.runtimes["b2"].last_active_page_id == "__silence__"
        assert svc.runtimes["b2"].last_active_page_content == "snoozing"


class TestSendFailureTracking:
    """check_and_send_for_board records why a send attempt failed on the
    runtime (issue #1791) so API endpoints can report it instead of
    conflating 'failed' with benign skips."""

    def test_render_unavailable_records_error(self):
        boards = [_board("b1", "One")]
        svc, _clients = _service_with_runtimes(boards)
        pages = _page_service({"pA": {"content": "ALPHA"}})
        pages.preview_page.side_effect = lambda pid, force_refresh=False, **_kwargs: SimpleNamespace(
            available=False, formatted="", error="plugin data unavailable"
        )
        schedule = _schedule_service({"b1": "pA"})

        sent = _drive(svc, boards, pages=pages, schedule=schedule)

        assert sent is False
        assert svc.get_last_send_error("b1") == "plugin data unavailable"
        assert svc.get_last_send_error() == "plugin data unavailable"  # default → primary

    def test_board_write_failure_records_error(self):
        boards = [_board("b1", "One")]
        svc, clients = _service_with_runtimes(boards)
        clients["b1"].render.return_value = (False, False)
        pages = _page_service({"pA": {"content": "ALPHA"}})
        schedule = _schedule_service({"b1": "pA"})

        sent = _drive(svc, boards, pages=pages, schedule=schedule)

        assert sent is False
        assert "pA" in (svc.get_last_send_error("b1") or "")

    def test_successful_send_clears_previous_error(self):
        boards = [_board("b1", "One")]
        svc, _clients = _service_with_runtimes(boards)
        svc.runtimes["b1"].last_send_error = "stale error from an earlier tick"
        pages = _page_service({"pA": {"content": "ALPHA"}})
        schedule = _schedule_service({"b1": "pA"})

        sent = _drive(svc, boards, pages=pages, schedule=schedule)

        assert sent is True
        assert svc.get_last_send_error("b1") is None

    def test_unchanged_content_skip_is_not_an_error(self):
        boards = [_board("b1", "One")]
        svc, clients = _service_with_runtimes(boards)
        pages = _page_service({"pA": {"content": "ALPHA"}})
        schedule = _schedule_service({"b1": "pA"})

        _drive(svc, boards, pages=pages, schedule=schedule)
        clients["b1"].render.reset_mock()
        sent = _drive(svc, boards, pages=pages, schedule=schedule)

        assert sent is False
        clients["b1"].render.assert_not_called()
        assert svc.get_last_send_error("b1") is None


class TestSendStatusReporting:
    """``check_and_send_active_page_with_status`` is what /refresh and
    /force-refresh call, so it must report the failure THIS pass produced —
    across every board, and without picking up the engine thread's writes
    (issue #1791)."""

    def test_secondary_board_failure_is_reported_by_the_aggregate_status(self):
        """A failing secondary must not read as an unqualified success. Reading
        only the primary runtime's error (as the endpoint used to) returned
        None here, so /refresh reported success while board 2 went stale."""
        boards = [_board("b1", "One"), _board("b2", "Two")]
        svc, _clients = _service_with_runtimes(boards)
        pages = _page_service({"pA": {"content": "ALPHA"}, "pB": {"content": "BETA"}})

        def _preview(pid, force_refresh=False, **_kwargs):
            if pid == "pB":
                return SimpleNamespace(available=False, formatted="", error="secondary board render failed")
            return SimpleNamespace(available=True, formatted="ALPHA", error=None)

        pages.preview_page.side_effect = _preview
        schedule = _schedule_service({"b1": "pA", "b2": "pB"})

        sent, error = _drive(svc, boards, pages=pages, schedule=schedule, with_status=True)

        assert sent is True  # the primary board was driven fine
        assert error == "board b2: secondary board render failed"

    def test_primary_failure_reason_is_reported_unprefixed(self):
        boards = [_board("b1", "One")]
        svc, _clients = _service_with_runtimes(boards)
        pages = _page_service({"pA": {"content": "ALPHA"}})
        pages.preview_page.side_effect = lambda pid, force_refresh=False, **_kwargs: SimpleNamespace(
            available=False, formatted="", error="plugin data unavailable"
        )
        schedule = _schedule_service({"b1": "pA"})

        sent, error = _drive(svc, boards, pages=pages, schedule=schedule, with_status=True)

        assert sent is False
        assert error == "plugin data unavailable"

    def test_status_ignores_a_concurrent_write_from_another_thread(self):
        """``rt.last_send_error`` is shared with the engine thread, which can
        set it between this pass returning and the endpoint reading it. The
        status wrapper captures per-thread, so only this call's failures count.
        """
        boards = [_board("b1", "One")]
        svc, clients = _service_with_runtimes(boards)
        rt = svc.runtimes["b1"]

        def _render(*args, **kwargs):
            # Stand-in for the engine thread ticking mid-request.
            t = threading.Thread(target=svc._record_send_error, args=(rt, "b1", "engine tick failure"))
            t.start()
            t.join()
            return (True, True)

        clients["b1"].render.side_effect = _render
        pages = _page_service({"pA": {"content": "ALPHA"}})
        schedule = _schedule_service({"b1": "pA"})

        sent, error = _drive(svc, boards, pages=pages, schedule=schedule, with_status=True)

        assert sent is True
        assert error is None
        # The other thread's write did land on the shared runtime attribute —
        # which is exactly why the endpoint must not read it back.
        assert rt.last_send_error == "engine tick failure"

    def test_one_off_override_render_failure_is_reported(self):
        """The one-off send path (#1789) is a second render that can fail. It
        must report too, or /refresh on a failing one-off returns success."""
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
        settings = _settings_service(boards, override=override)
        pages = _page_service({"pA": {"content": "ALPHA"}})
        pages.render_page.side_effect = lambda page, **_kwargs: SimpleNamespace(
            available=False, formatted="", error="one-off render failed"
        )
        schedule = _schedule_service({"b1": "pA"})

        sent, error = _drive(svc, boards, settings=settings, pages=pages, schedule=schedule, with_status=True)

        assert sent is False
        assert error == "one-off render failed"

    def test_successful_pass_reports_no_reason(self):
        boards = [_board("b1", "One")]
        svc, _clients = _service_with_runtimes(boards)
        pages = _page_service({"pA": {"content": "ALPHA"}})
        schedule = _schedule_service({"b1": "pA"})

        sent, error = _drive(svc, boards, pages=pages, schedule=schedule, with_status=True)

        assert sent is True
        assert error is None


class TestThrottledSendDoesNotPrimeDedupeCache:
    """Issue #1794 review: a note-array send skipped by
    ``NOTE_ARRAY_MIN_SEND_INTERVAL`` returns ``(True, False)`` — success, but
    the content never reached the board. Priming the dedupe cache with it
    strands the board on the previous frame forever, because no later tick
    re-attempts unchanged content."""

    @staticmethod
    def _throttled_env():
        boards = [_note_array_board("b1", "Notes", notes_wide=2, notes_tall=2)]
        svc, clients = _service_with_runtimes(boards)
        client = clients["b1"]
        client.render.return_value = (True, False)
        client.last_send_throttled = True
        pages = _page_service(
            {"pA": {"content": "ALPHA", "device_type": "note_array", "notes_wide": 2, "notes_tall": 2}}
        )
        schedule = _schedule_service({"b1": "pA"})
        return svc, boards, client, pages, schedule

    def test_throttled_send_leaves_the_dedupe_cache_clear(self):
        svc, boards, _client, pages, schedule = self._throttled_env()

        _drive(svc, boards, pages=pages, schedule=schedule)

        rt = svc.runtimes["b1"]
        assert rt.last_active_page_content is None, "cached content the board never received"
        assert rt.last_active_page_id is None

    def test_a_later_tick_retries_a_throttled_send(self):
        svc, boards, client, pages, schedule = self._throttled_env()

        _drive(svc, boards, pages=pages, schedule=schedule)
        # Throttle window has passed; this send lands.
        client.render.return_value = (True, True)
        client.last_send_throttled = False
        _drive(svc, boards, pages=pages, schedule=schedule)

        assert client.render.call_count == 2, "board left permanently stale after a throttled send"
        assert svc.runtimes["b1"].last_active_page_content == "ALPHA"

    def test_a_delivered_send_still_primes_the_cache(self):
        """Regression guard: the unchanged-content skip (also (True, False))
        means the frame IS on the board, so it must still prime."""
        boards = [_board("b1", "One")]
        svc, clients = _service_with_runtimes(boards)
        clients["b1"].render.return_value = (True, False)
        clients["b1"].last_send_throttled = False
        pages = _page_service({"pA": {"content": "ALPHA"}})

        _drive(svc, boards, pages=pages, schedule=_schedule_service({"b1": "pA"}))

        assert svc.runtimes["b1"].last_active_page_content == "ALPHA"


class TestOutOfBandContentFlag:
    """Issue #1831: per-board "showing out-of-band content" state.

    Set by the out-of-band write paths (MQTT send_message/blank_board, POST
    /send-message, the /debug/* writes), cleared whenever the engine actually
    delivers a page to that board. The stored active page id is untouched —
    it remains the restore target (issue #1805)."""

    def test_runtime_defaults_to_in_band(self):
        rt = BoardRuntime(client=None, board_id="b1")
        assert rt.showing_out_of_band is False

    def test_mark_and_read_target_the_given_board(self):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        svc, _clients = _service_with_runtimes(boards)

        svc.mark_showing_out_of_band("b2")

        assert svc.is_showing_out_of_band("b2") is True
        assert svc.is_showing_out_of_band("b1") is False

    def test_mark_without_board_id_targets_the_primary_board(self):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        svc, _clients = _service_with_runtimes(boards)

        svc.mark_showing_out_of_band()

        assert svc.is_showing_out_of_band() is True
        assert svc.is_showing_out_of_band("b1") is True
        assert svc.is_showing_out_of_band("b2") is False

    def test_unknown_board_reads_as_in_band(self):
        boards = [_board("b1", "One")]
        svc, _clients = _service_with_runtimes(boards)

        svc.mark_showing_out_of_band("nope")

        assert svc.is_showing_out_of_band("nope") is False
        assert svc.is_showing_out_of_band("b1") is False

    def test_delivering_a_page_clears_the_flag(self):
        boards = [_board("b1", "One")]
        svc, _clients = _service_with_runtimes(boards)
        pages = _page_service({"pA": {"content": "ALPHA"}})
        schedule = _schedule_service({"b1": "pA"})
        svc.mark_showing_out_of_band("b1")

        _drive(svc, boards, pages=pages, schedule=schedule)

        assert svc.is_showing_out_of_band("b1") is False

    def test_deduped_tick_leaves_the_flag_set(self):
        """The engine skipping at the content-unchanged guard has NOT painted
        over the manual content, so the flag must survive the tick."""
        boards = [_board("b1", "One")]
        svc, _clients = _service_with_runtimes(boards)
        pages = _page_service({"pA": {"content": "ALPHA"}})
        schedule = _schedule_service({"b1": "pA"})

        _drive(svc, boards, pages=pages, schedule=schedule)
        svc.mark_showing_out_of_band("b1")
        _drive(svc, boards, pages=pages, schedule=schedule)

        assert svc.is_showing_out_of_band("b1") is True

    def test_failed_send_leaves_the_flag_set(self):
        boards = [_board("b1", "One")]
        svc, clients = _service_with_runtimes(boards)
        clients["b1"].render.return_value = (False, False)
        pages = _page_service({"pA": {"content": "ALPHA"}})
        schedule = _schedule_service({"b1": "pA"})
        svc.mark_showing_out_of_band("b1")

        _drive(svc, boards, pages=pages, schedule=schedule)

        assert svc.is_showing_out_of_band("b1") is True


class TestAdoptedWaiterFailureReason:
    """A superseded wait=True job must inherit the replacement's failure REASON.

    #1867 review (reviewer reproduced): the adopted waiter inherited the
    replacement's boolean but the replacement's error went to ITS submitter's
    sink (the engine's None), so /refresh answered 200 with sent:false,
    reason:None on a real hardware failure.
    """

    def test_adopted_wait_caller_gets_the_replacements_failure_reason(self):
        import time as _time

        from src.displays.send_worker import SendJob

        boards = [_board("b-1", "Primary")]
        svc, clients = _service_with_runtimes(boards)
        rt = svc.runtimes["b-1"]
        client = clients["b-1"]

        active = {"b-1": "p-a"}
        settings = _settings_service(boards, schedule_off=("b-1",))
        settings.get_active_page_id.side_effect = lambda board_id=None: active.get(board_id)
        pages = _page_service({"p-a": {"content": "AAA"}, "p-b": {"content": "BBB"}})

        # Wedge the worker so the API caller's job parks in the pending slot.
        gate = threading.Event()
        started = threading.Event()

        def blocker() -> bool:
            started.set()
            gate.wait(timeout=10)
            return True

        worker = svc._worker_for(rt)
        worker.submit(SendJob(key=("blocker",), run=blocker))
        assert started.wait(timeout=5)

        outcome = {}

        def api_caller():
            outcome["sent"], outcome["reason"] = svc.check_and_send_for_board_with_status(
                "b-1", rt, is_primary=True
            )

        with (
            patch("src.main.get_settings_service", return_value=settings),
            patch("src.main.get_page_service", return_value=pages),
            patch("src.main.get_schedule_service", return_value=_schedule_service({})),
            patch("src.main.get_collection_service", return_value=MagicMock()),
            patch("src.time_service.get_time_service", return_value=_time_service()),
            patch("src.main.Config") as cfg,
            patch.object(svc, "_check_trigger_override", return_value=None),
            patch.object(svc, "request_board_refresh"),
        ):
            cfg.is_silence_mode_active.return_value = False
            caller = threading.Thread(target=api_caller)
            caller.start()
            deadline = _time.monotonic() + 5
            while len(worker.active_keys()) < 2:  # blocker + the caller's parked job
                assert _time.monotonic() < deadline, "API caller's job never reached the pending slot"
                _time.sleep(0.005)

            # Engine tick supersedes the parked job with NEW content whose
            # send fails at the hardware.
            active["b-1"] = "p-b"
            client.render.return_value = (False, False)
            svc.check_and_send_for_board("b-1", rt, is_primary=True, wait=False)

            gate.set()
            caller.join(timeout=10)

        assert not caller.is_alive()
        assert outcome["sent"] is False
        assert outcome["reason"] == "Failed to send active page to board: p-b"
