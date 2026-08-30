"""Per-board silence delivery through the display engine (issue #1788).

Silence used to be one global decision applied to every board. Now each board
resolves its own window, mode, page and indicator, so:

  - two boards with different windows go quiet independently
  - each board's silence page is sized to **that board**, not to the page's
    own declared device type (the second half of the issue: a Flagship-sized
    page silently mis-rendered onto a Note)
  - the 1-second boundary detector in ``run()`` fires when ANY board's silence
    state flips, not just the primary's
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.config import resolve_silence_schedule
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


def _settings_service(boards):
    svc = MagicMock()
    svc.get_board_settings.return_value = SimpleNamespace(boards=boards)
    svc.get_primary_board_id.return_value = boards[0]["id"] if boards else None
    svc.is_paused.side_effect = lambda board_id=None: False
    svc.is_schedule_enabled.side_effect = lambda board_id=None: True
    svc.get_active_page_id.side_effect = lambda board_id=None: None
    svc.get_transition_settings.return_value = TRANSITIONS
    svc.consume_temporary_override.return_value = None
    return svc


def _schedule_service(active_by_board):
    svc = MagicMock()
    svc.get_active_page_id.side_effect = lambda t, d, board_id=None: active_by_board.get(board_id)
    return svc


def _service_with_runtimes(boards):
    svc = DisplayService()
    runtimes = {}
    clients = {}
    for board in boards:
        client = MagicMock()
        client.render.return_value = (True, True)
        client._last_characters = None
        clients[board["id"]] = client
        runtimes[board["id"]] = BoardRuntime(client=client, board_id=board["id"])
    svc.runtimes = runtimes
    svc._primary_board_id = boards[0]["id"] if boards else None
    return svc, clients


class _FakeConfig:
    """A stand-in for ``Config`` driven by one silence_schedule feature dict.

    Resolution goes through the real :func:`resolve_silence_schedule`, and
    ``is_silence_mode_active`` consults ``active_boards`` so a test can put one
    board inside its window and another outside it.
    """

    def __init__(self, feature, active_boards):
        self._feature = feature
        self._active = set(active_boards)

    def silence_config_for(self, board_id=None):
        return resolve_silence_schedule(self._feature, board_id)

    def is_silence_mode_active(self, board_id=None):
        return board_id in self._active


def _drive(svc, boards, *, config, pages=None, schedule=None, settings=None):
    settings = settings if settings is not None else _settings_service(boards)
    pages = pages if pages is not None else _page_service({})
    schedule = schedule if schedule is not None else _schedule_service({})
    with (
        patch("src.main.get_settings_service", return_value=settings),
        patch("src.main.get_page_service", return_value=pages),
        patch("src.main.get_schedule_service", return_value=schedule),
        patch("src.main.get_collection_service", return_value=MagicMock()),
        patch("src.time_service.get_time_service", return_value=_time_service()),
        patch("src.main.Config", config),
        patch.object(svc, "_check_trigger_override", return_value=None),
        patch.object(svc, "request_board_refresh"),
    ):
        return svc.check_and_send_active_page()


def _time_service():
    ts = MagicMock()
    ts.get_current_time.return_value = datetime(2026, 7, 15, 12, 0, 0)
    return ts


def _decode(board_array):
    """Turn a board character array back into text for assertions."""
    rev = {0: " "}
    for i, ch in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ", start=1):
        rev[i] = ch
    for i, ch in enumerate("123456789", start=27):
        rev[i] = ch
    rev[36] = "0"
    out = [("".join(rev.get(code, "?") for code in row)).rstrip() for row in board_array]
    return "\n".join(line for line in out if line)


BASE = {
    "enabled": True,
    "start_time": "04:00+00:00",
    "end_time": "15:00+00:00",
    "mode": "indicator",
    "page_id": None,
    "indicator_text": "SNOOZING",
    "indicator_position": "center",
}


class TestIndependentSilenceWindows:
    def test_one_board_silences_while_the_other_keeps_updating(self):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        svc, clients = _service_with_runtimes(boards)
        pages = _page_service({"pA": {"content": "ALPHA"}, "pB": {"content": "BETA"}})
        schedule = _schedule_service({"b1": "pA", "b2": "pB"})
        config = _FakeConfig(BASE, active_boards={"b1"})

        _drive(svc, boards, config=config, pages=pages, schedule=schedule)

        assert _decode(clients["b1"].render.call_args.args[0]).strip() == "SNOOZING"
        assert "BETA" in _decode(clients["b2"].render.call_args.args[0])
        assert svc.runtimes["b1"].snoozing_message_sent is True
        assert svc.runtimes["b2"].snoozing_message_sent is False

    def test_each_board_uses_its_own_indicator_text_and_position(self):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        svc, clients = _service_with_runtimes(boards)
        pages = _page_service({"pA": {"content": "ALPHA"}, "pB": {"content": "BETA"}})
        schedule = _schedule_service({"b1": "pA", "b2": "pB"})
        feature = {
            **BASE,
            "by_board": {
                "b1": {"indicator_text": "bedtime", "indicator_position": "top-left"},
                "b2": {"indicator_text": "quiet"},
            },
        }
        config = _FakeConfig(feature, active_boards={"b1", "b2"})

        _drive(svc, boards, config=config, pages=pages, schedule=schedule)

        rows1 = clients["b1"].render.call_args.args[0]
        assert _decode(rows1).splitlines()[0].startswith("BEDTIME")
        rows2 = clients["b2"].render.call_args.args[0]
        assert _decode(rows2).strip() == "QUIET"

    def test_a_board_can_freeze_while_another_shows_an_indicator(self):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        svc, clients = _service_with_runtimes(boards)
        pages = _page_service({"pA": {"content": "ALPHA"}, "pB": {"content": "BETA"}})
        schedule = _schedule_service({"b1": "pA", "b2": "pB"})
        feature = {**BASE, "by_board": {"b1": {"mode": "freeze"}}}
        config = _FakeConfig(feature, active_boards={"b1", "b2"})

        _drive(svc, boards, config=config, pages=pages, schedule=schedule)

        clients["b1"].render.assert_not_called()
        assert _decode(clients["b2"].render.call_args.args[0]).strip() == "SNOOZING"


class TestSilencePageIsSizedToTheBoard:
    """Issue #1788 bug 2: _send_silence_page ignored the board's geometry."""

    def test_note_board_renders_its_own_note_sized_silence_page(self):
        boards = [_board("b1", "Flag"), _board("b2", "Desk", device_type="note", port=7001)]
        svc, clients = _service_with_runtimes(boards)
        pages = _page_service(
            {
                "pA": {"content": "ALPHA"},
                "pB": {"content": "BETA", "device_type": "note"},
                "night-big": {"content": "GOOD NIGHT", "device_type": "flagship"},
                "night-small": {"content": "NIGHT", "device_type": "note"},
            }
        )
        schedule = _schedule_service({"b1": "pA", "b2": "pB"})
        feature = {
            **BASE,
            "mode": "page",
            "by_board": {
                "b1": {"mode": "page", "page_id": "night-big"},
                "b2": {"mode": "page", "page_id": "night-small"},
            },
        }
        config = _FakeConfig(feature, active_boards={"b1", "b2"})

        _drive(svc, boards, config=config, pages=pages, schedule=schedule)

        rows1 = clients["b1"].render.call_args.args[0]
        assert (len(rows1), len(rows1[0])) == (6, 22)
        assert "GOOD NIGHT" in _decode(rows1)

        rows2 = clients["b2"].render.call_args.args[0]
        assert (len(rows2), len(rows2[0])) == (3, 15)
        assert "NIGHT" in _decode(rows2)

    def test_page_wider_than_the_board_is_rendered_at_board_size(self):
        """Regression: a Flagship-sized page used to be rendered at 22 cols
        onto a 15-col Note, so the array handed to the client did not match
        the hardware."""
        boards = [_board("b1", "Desk", device_type="note")]
        svc, clients = _service_with_runtimes(boards)
        pages = _page_service(
            {
                "pA": {"content": "ALPHA", "device_type": "note"},
                "wide": {"content": "GOOD NIGHT EVERYBODY", "device_type": "flagship"},
            }
        )
        schedule = _schedule_service({"b1": "pA"})
        feature = {**BASE, "mode": "page", "page_id": "wide"}
        config = _FakeConfig(feature, active_boards={"b1"})

        _drive(svc, boards, config=config, pages=pages, schedule=schedule)

        rows = clients["b1"].render.call_args.args[0]
        assert (len(rows), len(rows[0])) == (3, 15)
        assert clients["b1"].render.call_args.kwargs["device_type"] == "note"

    def test_missing_silence_page_falls_back_to_a_board_sized_indicator(self):
        boards = [_board("b1", "Desk", device_type="note")]
        svc, clients = _service_with_runtimes(boards)
        pages = _page_service({"pA": {"content": "ALPHA", "device_type": "note"}})
        schedule = _schedule_service({"b1": "pA"})
        feature = {**BASE, "mode": "page", "page_id": "gone"}
        config = _FakeConfig(feature, active_boards={"b1"})

        _drive(svc, boards, config=config, pages=pages, schedule=schedule)

        rows = clients["b1"].render.call_args.args[0]
        assert (len(rows), len(rows[0])) == (3, 15)
        assert _decode(rows).strip() == "SNOOZING"


class TestBoundaryDetector:
    """The run() loop's 1s detector must watch every board, not just primary."""

    def test_reports_a_change_when_a_secondary_board_crosses_its_boundary(self):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        svc, _clients = _service_with_runtimes(boards)
        settings = _settings_service(boards)

        with patch("src.main.get_settings_service", return_value=settings):
            with patch("src.main.Config", _FakeConfig(BASE, active_boards=set())):
                assert svc._silence_state_changed() is False
            with patch("src.main.Config", _FakeConfig(BASE, active_boards={"b2"})):
                assert svc._silence_state_changed() is True
            # Sticky: no further change until the state flips again.
            with patch("src.main.Config", _FakeConfig(BASE, active_boards={"b2"})):
                assert svc._silence_state_changed() is False

    def test_reports_a_change_when_the_primary_crosses_its_boundary(self):
        boards = [_board("b1", "One")]
        svc, _clients = _service_with_runtimes(boards)
        settings = _settings_service(boards)

        with patch("src.main.get_settings_service", return_value=settings):
            with patch("src.main.Config", _FakeConfig(BASE, active_boards=set())):
                assert svc._silence_state_changed() is False
            with patch("src.main.Config", _FakeConfig(BASE, active_boards={"b1"})):
                assert svc._silence_state_changed() is True
