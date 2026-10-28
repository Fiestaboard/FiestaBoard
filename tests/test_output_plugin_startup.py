"""A board driven by an output plugin comes back after a restart.

The owner's Pixoo board went dark on every restart of the beta build:

- ``ConfigManager.validate()`` checked the legacy config.json ``board``
  block (a Vestaboard's host and key) and only waived it when a board in
  ``settings.boards`` reported itself configured. The Pixoo plugin has no
  ``board_status`` hook, so its board never did, and startup failed with
  "Board host is required" in a loop.
- The display service built its boards before the plugin registry had
  loaded (and so registered) the output plugins: "Board … names unknown
  output 'divoom_pixoo'", until something else happened to load the
  registry five minutes later.
- A fresh install, with no board at all, logged an ERROR every 60 s.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.config_manager import ConfigManager
from src.devices import BoardInstance
from src.plugins.loader import PluginLoader

FIXTURES = Path(__file__).parent / "fixtures" / "plugins"
PLUGIN_ID = "recording_output"  # an output plugin with no board_status hook; settings require "host"


@pytest.fixture
def loaded():
    loader = PluginLoader(plugins_dir=FIXTURES, external_dirs=[])
    assert loader.load_plugin(PLUGIN_ID) is not None, loader.load_errors
    yield loader
    loader.unload_plugin(PLUGIN_ID)


def _board(**config) -> dict:
    return {
        "id": "px",
        "name": "Pixel",
        "device_type": "panel",
        "grid_rows": 10,
        "grid_cols": 16,
        "output": PLUGIN_ID,
        "output_config": config,
    }


# --- a status for an output with no board_status hook -------------------------------------


def test_an_output_without_a_status_hook_is_configured_when_its_required_settings_are_set(loaded):
    board = BoardInstance.from_dict(_board(host="192.0.2.50"))

    assert board.is_connection_configured is True
    assert board.status.state == "connected"


def test_an_output_without_a_status_hook_missing_a_required_setting_is_misconfigured(loaded):
    board = BoardInstance.from_dict(_board(token="test_token"))

    assert board.is_connection_configured is False
    assert board.has_connection_attempt is True


def test_an_output_without_a_status_hook_and_no_settings_is_unconfigured(loaded):
    board = BoardInstance.from_dict(_board())

    assert board.is_connection_configured is False
    assert board.has_connection_attempt is False


def test_an_output_not_installed_yet_is_configured_when_it_has_settings():
    """At boot the plugin may not be registered yet: whatever the user saved
    counts, as it already does for first-run detection."""
    board = BoardInstance.from_dict({**_board(host="192.0.2.50"), "output": "not_installed_output"})

    assert board.is_connection_configured is True


# --- startup validation ------------------------------------------------------------------


def _validate_with_boards(tmp_path, monkeypatch, boards):
    cm = ConfigManager(config_path=str(tmp_path / "config.json"))
    settings = MagicMock()
    settings.get_board_settings.return_value = SimpleNamespace(boards=boards)
    monkeypatch.setattr("src.settings.service.get_settings_service", lambda: settings)
    return cm.validate()


def test_the_legacy_board_block_does_not_block_startup_once_a_board_exists(tmp_path, monkeypatch):
    # Its output is not installed yet at validation time (boot order).
    board = {**_board(host="192.0.2.50"), "output": "divoom_pixoo"}
    ok, errors = _validate_with_boards(tmp_path, monkeypatch, [board])

    assert ok, errors


# --- startup ordering --------------------------------------------------------------------


def _build_before_the_registry_loaded(loaded):
    from src.outputs import factory

    loaded.unload_plugin(PLUGIN_ID)
    registry = MagicMock()
    registry.initialize.side_effect = lambda: loaded.load_plugin(PLUGIN_ID)

    with (
        patch("src.plugins.registry.get_plugin_registry", return_value=registry),
        patch("src.plugins.registry.plugin_registry_initialized", return_value=False),
    ):
        return factory.build_driver(_board(host="192.0.2.50"))


def test_building_a_board_loads_the_output_plugins_when_the_registry_has_not(loaded):
    """The factory asks the plugin registry to load once, when a board names an
    output nobody registered yet, instead of failing the board."""
    assert _build_before_the_registry_loaded(loaded) is not None


def test_an_output_not_registered_yet_is_not_logged_as_unknown(loaded, caplog):
    with caplog.at_level(logging.ERROR):
        _build_before_the_registry_loaded(loaded)

    assert [r.getMessage() for r in caplog.records if "unknown output" in r.getMessage()] == []


# --- a fresh install idles quietly -------------------------------------------------------


#: The placeholder board a fresh install's settings seed: no connection at all.
PLACEHOLDER = {"id": "b0", "name": "My Board", "device_type": "flagship", "output": "vestaboard", "output_config": {}}


@pytest.mark.parametrize("boards", [[], [PLACEHOLDER]], ids=["no_boards", "seeded_placeholder"])
def test_a_fresh_install_waits_for_its_first_board_without_errors(caplog, boards):
    from src.main import DisplayService

    settings = MagicMock()
    settings.get_board_settings.return_value = SimpleNamespace(boards=boards)
    service = DisplayService()
    with patch("src.main.get_settings_service", return_value=settings), caplog.at_level(logging.INFO):
        results = [service.initialize() for _ in range(3)]
        waiting_for_board = service.awaiting_first_board

    assert results == [False, False, False]
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []
    waiting = [r for r in caplog.records if "No display" in r.getMessage()]
    assert len(waiting) == 1, "the wait is announced once, not every retry"
    assert waiting_for_board is True
