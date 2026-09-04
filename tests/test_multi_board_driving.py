"""Tests for building/rebuilding per-board runtimes (issue #1243).

Covers ``DisplayService._build_board_clients`` / ``rebuild_board_clients``:
  - one runtime per configured board, ``vb_client`` pointing at the primary
  - note-array boards (token auth) are not filtered out
  - boards without a usable connection get no runtime
  - a rebuild prunes runtimes for removed boards
  - ``invalidate_board_content`` clears a runtime's dedupe + client cache
    (the local-array identify flash depends on this)

The per-board *driving* behaviour (routing, pause/schedule/silence isolation,
per-board caches) is covered by ``tests/test_per_board_engine.py``, which
exercises the unified ``check_and_send_for_board`` path.
"""

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.main import BoardRuntime, DisplayService


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


def _settings_service(boards):
    svc = MagicMock()
    svc.get_board_settings.return_value = SimpleNamespace(boards=boards)
    svc.get_primary_board_id.return_value = boards[0]["id"] if boards else None
    return svc


@pytest.fixture
def service():
    return DisplayService()


class TestBuildBoardClients:
    def test_builds_one_runtime_per_board_with_credentials(self, service):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        clients = {"b1": MagicMock(), "b2": MagicMock()}
        with (
            patch("src.main.get_settings_service", return_value=_settings_service(boards)),
            patch("src.main.board_client_from_board_dict", side_effect=lambda b: clients[b["id"]]),
        ):
            service._build_board_clients()

        assert service.board_clients == clients
        assert service.vb_client is clients["b1"]
        assert set(service.runtimes) == {"b1", "b2"}
        assert service._primary_board_id == "b1"
        clients["b1"].read_current_message.assert_called_once_with(sync_cache=True)

    def test_note_array_board_with_only_a_token_gets_a_runtime(self, service):
        """Note arrays authenticate with note_array_token, not local/cloud keys —
        the runtime build must not filter them out (issue #1243 item 3)."""
        boards = [
            _board("b1", "One"),
            _board(
                "b2",
                "Array",
                device_type="note_array",
                api_mode="cloud",
                host="",
                local_api_key="",
                cloud_key="",
                note_array_token="test-token",
                notes_wide=2,
                notes_tall=2,
            ),
        ]
        clients = {"b1": MagicMock(), "b2": MagicMock()}
        with (
            patch("src.main.get_settings_service", return_value=_settings_service(boards)),
            patch("src.main.board_client_from_board_dict", side_effect=lambda b: clients.get(b["id"])),
        ):
            service._build_board_clients()

        assert set(service.runtimes) == {"b1", "b2"}

    def test_local_array_board_with_tiles_gets_a_runtime(self, service):
        """Local Array Mode (#1399): a local-mode note array with saved tiles
        must get a runtime via the real client factory (NoteArrayLocalClient)."""
        boards = [
            _board(
                "b1",
                "LocalArray",
                device_type="note_array",
                api_mode="local",
                host="",
                local_api_key="",
                cloud_key="",
                notes_wide=2,
                notes_tall=1,
                tiles=[
                    {"row": 0, "col": 0, "host": "192.0.2.10", "port": 7000, "local_api_key": "test-k1"},
                    {"row": 0, "col": 1, "host": "192.0.2.11", "port": 7000, "local_api_key": "test-k2"},
                ],
            ),
        ]
        with patch("src.main.get_settings_service", return_value=_settings_service(boards)):
            service._build_board_clients(sync_cache=False)

        assert set(service.runtimes) == {"b1"}
        assert type(service.runtimes["b1"].client).__name__ == "NoteArrayLocalClient"

    def test_board_without_credentials_gets_no_runtime(self, service):
        """Uses the REAL client factory: a board with no usable credential
        (no local key, cloud key, or note-array token) must yield no runtime."""
        boards = [_board("b1", "One"), _board("b2", "Two", local_api_key="", cloud_key="")]
        with patch("src.main.get_settings_service", return_value=_settings_service(boards)):
            service._build_board_clients(sync_cache=False)

        assert set(service.runtimes) == {"b1"}

    def test_unchanged_board_keeps_its_runtime_and_caches(self, service):
        """A diff-based rebuild must keep an unchanged board's runtime so its
        caches (last-sent content, silence state) survive editing another board."""
        boards = [_board("b1", "One")]
        original_client = MagicMock()

        with (
            patch("src.main.get_settings_service", return_value=_settings_service(boards)),
            patch("src.main.board_client_from_board_dict", return_value=original_client),
        ):
            service._build_board_clients(sync_cache=False)
            service.runtimes["b1"].last_active_page_content = "REMEMBER ME"

            # Rebuild with the same board config — runtime + cache must survive.
            service._build_board_clients(sync_cache=False)

        assert service.runtimes["b1"].client is original_client
        assert service.runtimes["b1"].last_active_page_content == "REMEMBER ME"

    def test_rebuild_prunes_removed_boards(self, service):
        service.runtimes = {"b-gone": BoardRuntime(client=MagicMock(), board_id="b-gone")}
        service._primary_board_id = "b-gone"
        boards = [_board("b2", "Two", port=7001)]
        with (
            patch("src.main.get_settings_service", return_value=_settings_service(boards)),
            patch("src.main.board_client_from_board_dict", side_effect=lambda b: MagicMock()),
        ):
            assert service.reinitialize_board_client() is True

        assert set(service.runtimes) == {"b2"}
        assert service._primary_board_id == "b2"


class TestInvalidateBoardContent:
    """invalidate_board_content is the Local Array Mode hook (#1399): after an
    out-of-band board write (identify flash) the next tick must re-send."""

    def test_clears_runtime_dedupe_and_client_cache(self, service):
        client = MagicMock()
        rt = BoardRuntime(client=client, board_id="b2")
        rt.last_active_page_content = "CACHED"
        rt.last_active_page_id = "p1"
        service.runtimes = {"b2": rt}

        with patch("src.main.get_settings_service", return_value=_settings_service([_board("b1", "One")])):
            service.invalidate_board_content("b2")

        assert rt.last_active_page_content is None
        assert rt.last_active_page_id is None
        client.clear_cache.assert_called_once()

    def test_unknown_board_is_a_noop(self, service):
        with patch("src.main.get_settings_service", return_value=_settings_service([_board("b1", "One")])):
            service.invalidate_board_content("nope")  # must not raise

    def test_primary_fallback_runtime_is_invalidated_by_primary_id(self, service):
        """Legacy installs key the primary runtime under the fallback sentinel;
        invalidating by the settings primary id must still find it."""
        client = MagicMock()
        service.vb_client = client  # creates the primary runtime
        service._last_active_page_content = "CACHED"

        with patch("src.main.get_settings_service", return_value=_settings_service([_board("b1", "One")])):
            service.invalidate_board_content("b1")

        assert service._last_active_page_content is None
        client.clear_cache.assert_called_once()


class TestPrimaryBoardFailureIsolation:
    """A misconfigured primary board must not take down the rest of the fleet
    (issue #1749).

    Before the fix, ``boards[0]`` failing to yield a client dropped the build
    into the legacy single-board ``Config`` fallback, which raises when no
    legacy credential is configured — aborting ``_build_board_clients`` for
    every board and making ``initialize()`` return False, so ``run()`` bailed
    and no board was driven at all.
    """

    def test_secondary_board_gets_a_runtime_when_the_primary_client_raises(self, service):
        boards = [_board("b1", "Broken"), _board("b2", "Good", port=7001)]
        good = MagicMock()

        def factory(board):
            if board["id"] == "b1":
                raise ValueError("api_key is required")
            return good

        with (
            patch("src.main.get_settings_service", return_value=_settings_service(boards)),
            patch("src.main.board_client_from_board_dict", side_effect=factory),
        ):
            service._build_board_clients(sync_cache=False)

        assert service.get_board_client("b2") is good

    def test_secondary_board_gets_a_runtime_when_the_primary_is_unconfigured(self, service):
        """The primary has no usable credential (factory returns None). The
        legacy Config fallback must not hijack the build."""
        boards = [_board("b1", "Broken", local_api_key="", cloud_key=""), _board("b2", "Good", port=7001)]
        good = MagicMock()

        with (
            patch("src.main.get_settings_service", return_value=_settings_service(boards)),
            patch(
                "src.main.board_client_from_board_dict",
                side_effect=lambda b: None if b["id"] == "b1" else good,
            ),
        ):
            service._build_board_clients(sync_cache=False)

        assert service.get_board_client("b2") is good

    def test_misconfigured_primary_does_not_build_the_legacy_config_client(self, service):
        """With another board up, the legacy single-board fallback must stay
        out of the way — it would claim the primary slot with a client built
        from whatever is left in the legacy env config."""
        boards = [_board("b1", "Broken", local_api_key="", cloud_key=""), _board("b2", "Good", port=7001)]

        with (
            patch("src.main.get_settings_service", return_value=_settings_service(boards)),
            patch(
                "src.main.board_client_from_board_dict",
                side_effect=lambda b: None if b["id"] == "b1" else MagicMock(),
            ),
            patch("src.main.BoardClient") as legacy_client,
        ):
            service._build_board_clients(sync_cache=False)

        legacy_client.assert_not_called()
        assert service._PRIMARY_FALLBACK_KEY not in service.runtimes

    def test_secondary_board_is_still_driven_when_the_primary_is_misconfigured(self, service):
        """Acceptance (issue #1749): primary invalid + secondary valid ->
        the secondary is still driven on the update tick."""
        boards = [_board("b1", "Broken", local_api_key="", cloud_key=""), _board("b2", "Good", port=7001)]
        driven = []

        with (
            patch("src.main.get_settings_service", return_value=_settings_service(boards)),
            patch(
                "src.main.board_client_from_board_dict",
                side_effect=lambda b: None if b["id"] == "b1" else MagicMock(),
            ),
        ):
            service._build_board_clients(sync_cache=False)
            with patch.object(
                service,
                "check_and_send_for_board",
                side_effect=lambda board_id, rt, **kw: driven.append(board_id) or True,
            ):
                service.check_and_send_active_page()

        assert "b2" in driven

    def test_initialize_succeeds_when_only_the_primary_board_is_misconfigured(self, service):
        boards = [_board("b1", "Broken", local_api_key="", cloud_key=""), _board("b2", "Good", port=7001)]

        with (
            patch("src.main.get_settings_service", return_value=_settings_service(boards)),
            patch(
                "src.main.board_client_from_board_dict",
                side_effect=lambda b: None if b["id"] == "b1" else MagicMock(),
            ),
            patch("src.main.Config.validate", return_value=True),
            patch("src.main.Config.get_summary", return_value={}),
            patch("src.main.Config.get_transition_settings", return_value={"strategy": None}),
            patch("src.main.threading.Thread"),
        ):
            assert service.initialize() is True

    def test_initialize_fails_when_no_board_has_a_connection(self, service):
        """The all-boards-down case must still be a hard failure — the fix
        must not turn a fully unconfigured install into a silent success."""
        boards = [_board("b1", "Broken", local_api_key="", cloud_key="")]

        with (
            patch("src.main.get_settings_service", return_value=_settings_service(boards)),
            patch("src.main.board_client_from_board_dict", return_value=None),
            patch("src.main.Config.validate", return_value=True),
            patch("src.main.BoardClient", side_effect=ValueError("api_key is required")),
        ):
            assert service.initialize() is False

    def test_primary_failure_reason_is_recorded_for_surfacing(self, service):
        """The skipped board's reason must be observable, not swallowed —
        /status exposes it per board."""
        boards = [_board("b1", "Broken"), _board("b2", "Good", port=7001)]

        def factory(board):
            if board["id"] == "b1":
                raise ValueError("host is required for Local API")
            return MagicMock()

        with (
            patch("src.main.get_settings_service", return_value=_settings_service(boards)),
            patch("src.main.board_client_from_board_dict", side_effect=factory),
        ):
            service._build_board_clients(sync_cache=False)

        assert "host is required for Local API" in service.board_init_errors["b1"]
        assert "b2" not in service.board_init_errors

    def test_repeated_initialize_reuses_the_live_board_state_poll_thread(self, service):
        """``initialize()`` must not stack a second ``board-state-poll`` thread.

        With the primary clientless, ``vb_client`` stays ``None`` for the life
        of the process, so every startup gate that tests it re-enters
        ``initialize()``: ``get_service()``, ``run_service_background()``'s
        ``if not service.vb_client`` guard, and ``run()``'s
        ``if not self.vb_client and not self.initialize()``. Each pass used to
        start another poll thread, and ``run_service_background``'s backoff
        loop repeated two of them on every auto-restart — an unbounded leak.
        """
        boards = [_board("b1", "Broken", local_api_key="", cloud_key=""), _board("b2", "Good", port=7001)]
        pre_existing = {t.ident for t in threading.enumerate()}
        release = threading.Event()

        def _park(_self):
            release.wait(10)

        with (
            patch("src.main.get_settings_service", return_value=_settings_service(boards)),
            patch(
                "src.main.board_client_from_board_dict",
                side_effect=lambda b: None if b["id"] == "b1" else MagicMock(),
            ),
            patch("src.main.Config.validate", return_value=True),
            patch("src.main.Config.get_summary", return_value={}),
            patch("src.main.Config.get_transition_settings", return_value={"strategy": None}),
            patch.object(DisplayService, "_board_poll_loop", _park),
        ):
            try:
                for _ in range(3):
                    assert service.initialize() is True
                # The condition all three startup gates re-test.
                assert service.vb_client is None
                started = [
                    t
                    for t in threading.enumerate()
                    if t.name == "board-state-poll" and t.is_alive() and t.ident not in pre_existing
                ]
                assert len(started) == 1, f"expected 1 live poll thread, found {len(started)}"
            finally:
                release.set()
                for t in threading.enumerate():
                    if t.name == "board-state-poll" and t.ident not in pre_existing:
                        t.join(timeout=5)

    def test_a_recovered_board_clears_its_recorded_error(self, service):
        boards = [_board("b1", "One")]

        with patch("src.main.get_settings_service", return_value=_settings_service(boards)):
            with patch("src.main.board_client_from_board_dict", side_effect=ValueError("boom")):
                service._build_board_clients(sync_cache=False)
            assert "b1" in service.board_init_errors

            with patch("src.main.board_client_from_board_dict", return_value=MagicMock()):
                service._build_board_clients(sync_cache=False)

        assert service.board_init_errors == {}
