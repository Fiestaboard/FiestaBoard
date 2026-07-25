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


def _settings_service(boards, *, paused=(), schedule_off=(), manual=None, override=None):
    """A settings service mock with per-board resolution.

    ``manual`` maps board_id -> manual active page id (used when that
    board's schedule mode is off). ``override`` is the consume result.
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

    def _preview(pid, force_refresh=False):
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
        client.send_characters.return_value = (True, True)
        client._last_characters = None
        clients[board["id"]] = client
        runtimes[board["id"]] = BoardRuntime(client=client, board_id=board["id"])
    svc.runtimes = runtimes
    svc._primary_board_id = boards[0]["id"] if boards else None
    return svc, clients


def _drive(svc, boards, *, settings=None, pages=None, schedule=None, silence=False):
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
        patch.object(svc, "_check_trigger_override", return_value=None),
        patch.object(svc, "request_board_refresh"),
    ):
        cfg.is_silence_mode_active.return_value = silence
        cfg.SILENCE_SCHEDULE_MODE = "indicator"
        cfg.SILENCE_SCHEDULE_INDICATOR_TEXT = "SNOOZING"
        cfg.SILENCE_SCHEDULE_INDICATOR_POSITION = "center"
        cfg.SILENCE_SCHEDULE_PAGE_ID = None
        return svc.check_and_send_active_page()


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

        clients["b1"].send_characters.assert_called_once()
        rows1 = clients["b1"].send_characters.call_args.args[0]
        assert len(rows1) == 6 and len(rows1[0]) == 22  # flagship

        clients["b2"].send_characters.assert_called_once()
        rows2 = clients["b2"].send_characters.call_args.args[0]
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
        clients["b1"].send_characters.assert_not_called()
        clients["b2"].send_characters.assert_called_once()

    def test_unchanged_content_is_not_resent(self):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        svc, clients = _service_with_runtimes(boards)
        pages = _page_service({"pB": {"content": "BETA"}})
        schedule = _schedule_service({"b2": "pB"})

        _drive(svc, boards, pages=pages, schedule=schedule)
        _drive(svc, boards, pages=pages, schedule=schedule)

        assert clients["b2"].send_characters.call_count == 1


class TestSkips:
    def test_paused_board_is_skipped(self):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        svc, clients = _service_with_runtimes(boards)
        pages = _page_service({"pB": {"content": "BETA"}})
        schedule = _schedule_service({"b2": "pB"})
        settings = _settings_service(boards, paused=("b2",))

        _drive(svc, boards, settings=settings, pages=pages, schedule=schedule)

        clients["b2"].send_characters.assert_not_called()

    def test_schedule_disabled_board_uses_manual_page(self):
        """Schedule off for a secondary -> its manual by_board page is shown."""
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        svc, clients = _service_with_runtimes(boards)
        pages = _page_service({"pManual": {"content": "MANUAL2"}})
        settings = _settings_service(boards, schedule_off=("b2",), manual={"b2": "pManual"})

        _drive(svc, boards, settings=settings, pages=pages)

        clients["b2"].send_characters.assert_called_once()
        assert svc.runtimes["b2"].last_active_page_id == "pManual"

    def test_secondary_with_no_active_page_goes_dark(self):
        """Unlike the primary, a secondary does NOT default to pages[0]."""
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        svc, clients = _service_with_runtimes(boards)
        pages = _page_service({"pDefault": {"content": "DEFAULT"}})
        settings = _settings_service(boards, schedule_off=("b2",), manual={})

        _drive(svc, boards, settings=settings, pages=pages)

        clients["b2"].send_characters.assert_not_called()

    def test_disabled_board_is_skipped(self):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001, enabled=False)]
        svc, clients = _service_with_runtimes(boards)
        pages = _page_service({"pB": {"content": "BETA"}})
        schedule = _schedule_service({"b2": "pB"})

        _drive(svc, boards, pages=pages, schedule=schedule)

        clients["b2"].send_characters.assert_not_called()


class TestPrimaryFallback:
    def test_primary_defaults_to_first_page_when_no_active_page(self):
        """The primary never goes dark: manual mode with no active page -> pages[0]."""
        boards = [_board("b1", "One", schedule_enabled=False)]
        svc, clients = _service_with_runtimes(boards)
        pages = _page_service({"pFirst": {"content": "FIRST"}})
        settings = _settings_service(boards, schedule_off=("b1",), manual={})

        _drive(svc, boards, settings=settings, pages=pages)

        clients["b1"].send_characters.assert_called_once()
        settings.set_active_page_id.assert_called_once()
        assert svc.runtimes["b1"].last_active_page_id == "pFirst"


class TestPartialFailureIsolation:
    def test_secondary_raising_does_not_block_primary(self):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        svc, clients = _service_with_runtimes(boards)
        clients["b2"].send_characters.side_effect = RuntimeError("board 2 exploded")
        pages = _page_service({"pA": {"content": "ALPHA"}, "pB": {"content": "BETA"}})
        schedule = _schedule_service({"b1": "pA", "b2": "pB"})

        result = _drive(svc, boards, pages=pages, schedule=schedule)

        assert result is True  # primary still sent
        clients["b1"].send_characters.assert_called_once()

    def test_primary_error_isolated_from_secondary(self):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        svc, clients = _service_with_runtimes(boards)
        clients["b1"].send_characters.side_effect = RuntimeError("board 1 exploded")
        pages = _page_service({"pA": {"content": "ALPHA"}, "pB": {"content": "BETA"}})
        schedule = _schedule_service({"b1": "pA", "b2": "pB"})

        result = _drive(svc, boards, pages=pages, schedule=schedule)

        assert result is False  # primary failed gracefully
        clients["b2"].send_characters.assert_called_once()  # secondary unaffected


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
        rows1 = clients["b1"].send_characters.call_args.args[0]
        assert len(rows1) == 6 and len(rows1[0]) == 22
        rows2 = clients["b2"].send_characters.call_args.args[0]
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
        assert clients["b1"].send_characters.call_count == 1
        assert clients["b2"].send_characters.call_count == 1


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
        assert rt.last_silence_mode_active is False
        assert rt.snoozing_message_sent is False
        assert rt.polled_characters is None
        assert rt.polled_at is None
        assert rt.refresh_thread is None
        assert rt.refresh_cancel is None
