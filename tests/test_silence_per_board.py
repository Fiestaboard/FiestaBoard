"""Per-board silence schedule resolution, storage and migrations (issue #1788).

Silence used to be a single global window shared by every board, which made a
Note and a Flagship share one quiet period *and* one silence page (the page
could only ever be one size). Silence settings are now stored per board under
``features.silence_schedule.by_board`` with the legacy top-level keys retained
as the install-wide default.

Covers:
  - the resolution rule (per-board entry wins, unconfigured board falls back
    to the global values, partial entries merge over the global layer)
  - ``Config.is_silence_mode_active(board_id)`` honoring per-board windows
    while the zero-arg call keeps its legacy primary/global meaning
  - per-board round-trip through ``ConfigManager`` (``set_feature`` must not
    silently drop ``by_board``)
  - the structural per-board migration: idempotent, logs the count
  - the UTC migration fanning out across every per-board window
"""

import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from src.config import Config
from src.config_manager import ConfigManager


def _patch_feature(feature_dict):
    """Patch Config._get_feature to return the given silence_schedule dict."""
    return patch.object(Config, "_get_feature", classmethod(lambda cls, name: feature_dict))


GLOBAL = {
    "enabled": True,
    "start_time": "04:00+00:00",
    "end_time": "15:00+00:00",
    "mode": "freeze",
    "page_id": None,
    "indicator_text": "SNOOZING",
    "indicator_position": "center",
}


# ==================== Resolution rule ====================


class TestSilenceConfigResolution:
    def test_board_with_own_entry_wins_over_global(self):
        feature = {
            **GLOBAL,
            "by_board": {
                "note-1": {
                    "enabled": True,
                    "start_time": "06:00+00:00",
                    "end_time": "12:00+00:00",
                    "mode": "page",
                    "page_id": "note-night",
                    "indicator_text": "HUSH",
                    "indicator_position": "top-left",
                }
            },
        }
        with _patch_feature(feature):
            resolved = Config.silence_config_for("note-1")

        assert resolved["start_time"] == "06:00+00:00"
        assert resolved["end_time"] == "12:00+00:00"
        assert resolved["mode"] == "page"
        assert resolved["page_id"] == "note-night"
        assert resolved["indicator_text"] == "HUSH"
        assert resolved["indicator_position"] == "top-left"

    def test_unconfigured_board_falls_back_to_global(self):
        """A board that was never configured inherits the install-wide window.

        Deliberately different from ActivePageSettings (where the legacy mirror
        is only consulted for the primary board): a newly added board should
        inherit the existing quiet hours rather than be unexpectedly loud.
        """
        feature = {**GLOBAL, "by_board": {"note-1": {"start_time": "06:00+00:00"}}}
        with _patch_feature(feature):
            resolved = Config.silence_config_for("brand-new-board")

        assert resolved["enabled"] is True
        assert resolved["start_time"] == "04:00+00:00"
        assert resolved["end_time"] == "15:00+00:00"

    def test_partial_entry_merges_over_global(self):
        feature = {**GLOBAL, "by_board": {"b1": {"mode": "indicator", "indicator_text": "shhh"}}}
        with _patch_feature(feature):
            resolved = Config.silence_config_for("b1")

        assert resolved["mode"] == "indicator"
        assert resolved["indicator_text"] == "SHHH"  # normalized like the global path
        assert resolved["start_time"] == "04:00+00:00"  # inherited

    def test_none_board_id_returns_global_layer(self):
        feature = {**GLOBAL, "by_board": {"b1": {"start_time": "23:00+00:00"}}}
        with _patch_feature(feature):
            resolved = Config.silence_config_for(None)

        assert resolved["start_time"] == "04:00+00:00"

    def test_resolved_dict_never_leaks_by_board(self):
        feature = {**GLOBAL, "by_board": {"b1": {"start_time": "23:00+00:00"}}}
        with _patch_feature(feature):
            assert "by_board" not in Config.silence_config_for("b1")

    def test_missing_feature_yields_documented_defaults(self):
        with _patch_feature({}):
            resolved = Config.silence_config_for("b1")

        assert resolved == {
            "enabled": False,
            "start_time": "20:00",
            "end_time": "07:00",
            "mode": "freeze",
            "page_id": None,
            "indicator_text": "SNOOZING",
            "indicator_position": "center",
        }

    def test_malformed_by_board_is_ignored(self):
        for bad in ("nope", 42, ["b1"], None):
            with _patch_feature({**GLOBAL, "by_board": bad}):
                assert Config.silence_config_for("b1")["start_time"] == "04:00+00:00"

    def test_malformed_board_entry_is_ignored(self):
        with _patch_feature({**GLOBAL, "by_board": {"b1": "garbage"}}):
            assert Config.silence_config_for("b1")["start_time"] == "04:00+00:00"

    def test_per_board_values_are_normalized(self):
        feature = {
            **GLOBAL,
            "by_board": {"b1": {"mode": "GARBAGE", "indicator_position": "sideways", "page_id": "   "}},
        }
        with _patch_feature(feature):
            resolved = Config.silence_config_for("b1")

        assert resolved["mode"] == "freeze"
        assert resolved["indicator_position"] == "center"
        assert resolved["page_id"] is None


class TestClassPropertiesStayGlobal:
    """The seven classproperties keep meaning "the install-wide default"."""

    def test_classproperties_ignore_by_board(self):
        feature = {
            **GLOBAL,
            "by_board": {"b1": {"enabled": False, "start_time": "23:00+00:00", "mode": "indicator"}},
        }
        with _patch_feature(feature):
            assert Config.SILENCE_SCHEDULE_ENABLED is True
            assert Config.SILENCE_SCHEDULE_START_TIME == "04:00+00:00"
            assert Config.SILENCE_SCHEDULE_MODE == "freeze"


# ==================== is_silence_mode_active(board_id) ====================


class TestIsSilenceModeActivePerBoard:
    def _run(self, feature, board_id, *, in_window):
        time_service = patch("src.time_service.get_time_service")
        with _patch_feature(feature), time_service as get_ts:
            get_ts.return_value.is_time_in_window.side_effect = lambda s, e: in_window.get((s, e), False)
            with patch("src.config_manager.get_config_manager"):
                return Config.is_silence_mode_active(board_id)

    def test_board_uses_its_own_window(self):
        feature = {
            **GLOBAL,
            "by_board": {"b1": {"start_time": "06:00+00:00", "end_time": "12:00+00:00"}},
        }
        in_window = {("06:00+00:00", "12:00+00:00"): True, ("04:00+00:00", "15:00+00:00"): False}
        assert self._run(feature, "b1", in_window=in_window) is True

    def test_other_board_uses_global_window(self):
        feature = {
            **GLOBAL,
            "by_board": {"b1": {"start_time": "06:00+00:00", "end_time": "12:00+00:00"}},
        }
        in_window = {("06:00+00:00", "12:00+00:00"): True, ("04:00+00:00", "15:00+00:00"): False}
        assert self._run(feature, "b2", in_window=in_window) is False

    def test_zero_arg_call_keeps_global_meaning(self):
        """Back-compat: ~20 existing fixtures call this with no arguments."""
        feature = {
            **GLOBAL,
            "by_board": {"b1": {"start_time": "06:00+00:00", "end_time": "12:00+00:00"}},
        }
        in_window = {("06:00+00:00", "12:00+00:00"): True, ("04:00+00:00", "15:00+00:00"): False}
        assert self._run(feature, None, in_window=in_window) is False

    def test_board_can_disable_silence_independently(self):
        feature = {**GLOBAL, "by_board": {"b1": {"enabled": False}}}
        in_window = {("04:00+00:00", "15:00+00:00"): True}
        assert self._run(feature, "b1", in_window=in_window) is False
        assert self._run(feature, "b2", in_window=in_window) is True


# ==================== ConfigManager storage ====================


@pytest.fixture
def cm(tmp_path: Path):
    ConfigManager._instance = None
    path = tmp_path / "config.json"
    manager = ConfigManager(config_path=str(path))
    yield manager
    ConfigManager._instance = None


class TestPerBoardStorageRoundTrip:
    def test_by_board_is_not_dropped_by_set_feature(self, cm):
        """set_feature whitelists against DEFAULT_CONFIG - by_board must be in it."""
        cfg = cm.get_feature("silence_schedule")
        cfg["by_board"] = {"b1": {"enabled": True, "start_time": "01:00+00:00", "end_time": "02:00+00:00"}}
        assert cm.set_feature("silence_schedule", cfg) is True

        assert cm.get_feature("silence_schedule")["by_board"]["b1"]["start_time"] == "01:00+00:00"

    def test_set_silence_schedule_for_board_writes_only_that_board(self, cm):
        cm.set_silence_schedule_for_board(
            "b1", {"enabled": True, "start_time": "01:00+00:00", "end_time": "02:00+00:00", "mode": "freeze"}
        )
        cm.set_silence_schedule_for_board(
            "b2", {"enabled": False, "start_time": "03:00+00:00", "end_time": "04:00+00:00", "mode": "indicator"}
        )

        stored = cm.get_feature("silence_schedule")
        assert stored["by_board"]["b1"]["start_time"] == "01:00+00:00"
        assert stored["by_board"]["b2"]["start_time"] == "03:00+00:00"
        # The global layer is untouched by a per-board write.
        assert stored["start_time"] == "20:00"

    def test_per_board_write_survives_reload(self, cm, tmp_path):
        cm.set_silence_schedule_for_board(
            "b1", {"enabled": True, "start_time": "01:00+00:00", "end_time": "02:00+00:00", "mode": "freeze"}
        )
        ConfigManager._instance = None
        reloaded = ConfigManager(config_path=str(tmp_path / "config.json"))
        assert reloaded.get_feature("silence_schedule")["by_board"]["b1"]["enabled"] is True


# ==================== Per-board migration ====================


def _write_config(path: Path, silence: dict):
    path.write_text(json.dumps({"features": {"silence_schedule": silence}}))


class TestPerBoardMigration:
    def _boards(self, *ids):
        return patch(
            "src.settings.service.get_settings_service",
            **{"return_value.get_board_settings.return_value.boards": [{"id": i} for i in ids]},
        )

    def test_seeds_every_configured_board_from_the_global_values(self, tmp_path, caplog):
        path = tmp_path / "config.json"
        _write_config(path, dict(GLOBAL))
        ConfigManager._instance = None
        manager = ConfigManager(config_path=str(path))

        with self._boards("b1", "b2"), caplog.at_level(logging.INFO):
            changed = manager.migrate_silence_schedule_to_per_board()

        assert changed == 2
        by_board = manager.get_feature("silence_schedule")["by_board"]
        assert by_board["b1"]["start_time"] == "04:00+00:00"
        assert by_board["b2"]["end_time"] == "15:00+00:00"
        assert "2" in caplog.text

    def test_is_idempotent(self, tmp_path):
        path = tmp_path / "config.json"
        _write_config(path, dict(GLOBAL))
        ConfigManager._instance = None
        manager = ConfigManager(config_path=str(path))

        with self._boards("b1", "b2"):
            assert manager.migrate_silence_schedule_to_per_board() == 2
            assert manager.migrate_silence_schedule_to_per_board() == 0

    def test_never_overwrites_an_existing_per_board_entry(self, tmp_path):
        path = tmp_path / "config.json"
        _write_config(path, {**GLOBAL, "by_board": {"b1": {"start_time": "23:00+00:00"}}})
        ConfigManager._instance = None
        manager = ConfigManager(config_path=str(path))

        with self._boards("b1", "b2"):
            manager.migrate_silence_schedule_to_per_board()

        by_board = manager.get_feature("silence_schedule")["by_board"]
        assert by_board["b1"]["start_time"] == "23:00+00:00"

    def test_already_migrated_install_is_left_alone(self, tmp_path):
        """The structural guard is the presence of by_board, so a user who
        deleted a board's entry does not get it silently re-seeded."""
        path = tmp_path / "config.json"
        _write_config(path, {**GLOBAL, "by_board": {}})
        ConfigManager._instance = None
        manager = ConfigManager(config_path=str(path))

        with self._boards("b1", "b2"):
            assert manager.migrate_silence_schedule_to_per_board() == 0
        assert manager.get_feature("silence_schedule")["by_board"] == {}


# ==================== UTC migration fan-out ====================


class TestUtcMigrationFansOut:
    def test_converts_every_per_board_window(self, tmp_path):
        path = tmp_path / "config.json"
        _write_config(
            path,
            {
                **GLOBAL,
                "start_time": "20:00",
                "end_time": "07:00",
                "by_board": {
                    "b1": {"start_time": "21:00", "end_time": "06:00"},
                    "b2": {"start_time": "22:00", "end_time": "05:00"},
                },
            },
        )
        ConfigManager._instance = None
        manager = ConfigManager(config_path=str(path))
        manager.set_general({"timezone": "UTC"})

        assert manager.migrate_silence_schedule_to_utc() is True

        stored = manager.get_feature("silence_schedule")
        assert stored["start_time"] == "20:00+00:00"
        assert stored["by_board"]["b1"]["start_time"] == "21:00+00:00"
        assert stored["by_board"]["b1"]["end_time"] == "06:00+00:00"
        assert stored["by_board"]["b2"]["start_time"] == "22:00+00:00"

    def test_is_idempotent(self, tmp_path):
        path = tmp_path / "config.json"
        _write_config(
            path,
            {**GLOBAL, "start_time": "20:00", "end_time": "07:00", "by_board": {"b1": {"start_time": "21:00", "end_time": "06:00"}}},
        )
        ConfigManager._instance = None
        manager = ConfigManager(config_path=str(path))
        manager.set_general({"timezone": "UTC"})

        manager.migrate_silence_schedule_to_utc()
        assert manager.migrate_silence_schedule_to_utc() is False
        assert manager.get_feature("silence_schedule")["by_board"]["b1"]["start_time"] == "21:00+00:00"

    def test_converts_per_board_windows_even_when_global_is_already_utc(self, tmp_path):
        """Regression: the 5-char heuristic must be applied per entry, not once
        for the whole feature - otherwise an already-migrated global window
        strands every per-board window in local time."""
        path = tmp_path / "config.json"
        _write_config(
            path,
            {
                **GLOBAL,
                "start_time": "04:00+00:00",
                "end_time": "15:00+00:00",
                "by_board": {"b1": {"start_time": "21:00", "end_time": "06:00"}},
            },
        )
        ConfigManager._instance = None
        manager = ConfigManager(config_path=str(path))
        manager.set_general({"timezone": "UTC"})

        assert manager.migrate_silence_schedule_to_utc() is True
        assert manager.get_feature("silence_schedule")["by_board"]["b1"]["start_time"] == "21:00+00:00"
