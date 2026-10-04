"""The output-plugin author API: accessors, the LED transition hand-off, exports.

Feedback from the first external output plugin (Divoom Pixoo) shaped it:

- **Accessors.** ``self.device_model`` (the resolved FiestaUI model dict),
  ``self.character_set`` (materialised) and ``self.board_geometry``
  (rows, cols) — so a plugin stops re-reading its own data files to learn
  what core already resolved for the board.
- **The transition hand-off.** A plugin that overrides ``write_transition``
  receives, for every change of what its board shows, the before and after
  RICH frames and the board's resolved LED transition
  (:func:`src.led.resolve_led_transition` for its device model) — the flip
  FiestaUI previews — instead of a transition plugin's compressed int grids.
  A plugin that implements only ``write_sequence`` is driven exactly as before.
- **Exports.** Everything a plugin needs to render comes from ``src.plugins``.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from src.fiestaui import builtin_device_models
from src.led import resolve_led_transition
from src.led.charsets import BUILTIN_CHARACTER_SETS
from src.outputs.cells import cells_from_codes, project_message
from src.outputs.plugin_base import OutputPluginBase
from src.outputs.plugin_driver import OutputPluginDriver
from src.outputs.registry import OutputCapabilities
from src.plugins.loader import PluginLoader
from src.send_outcome import WriteResult

PIXOO = builtin_device_models()["divoom_pixoo64"]
LED_3X5 = BUILTIN_CHARACTER_SETS["led_3x5"]
ROWS, COLS = 10, 16
FIXTURES = Path(__file__).parent / "fixtures" / "plugins"


def frame(message: str, charset=LED_3X5):
    return project_message(message, ROWS, COLS, charset)


# --- a sequence LED sign that takes the hand-off ------------------------------------------


class LedSign(OutputPluginBase):
    plugin_id = "led_sign"

    def __init__(self, board_id="sign", config=None):
        super().__init__(board_id, config or {})
        self.calls: list[tuple] = []
        self.result = WriteResult(True, True)
        self.bind_board(device_model=PIXOO, character_set=LED_3X5, geometry=(ROWS, COLS))

    def capabilities(self):
        return OutputCapabilities(
            technology="led_matrix",
            delivery="push",
            animation="sequence",
            native_transitions=frozenset(),
            max_frames=32,
        )

    def device_key(self):
        return f"led_sign:{id(self):x}"

    def write(self, frame, *, native, cancel):
        self.calls.append(("write", frame))
        return self.result

    def write_cells(self, cells, *, native, cancel):
        self.calls.append(("write_cells", cells))
        return self.result

    def write_transition(self, before, after, transition, *, cancel):
        self.calls.append(("write_transition", before, after, transition))
        return self.result


class SequenceOnly(LedSign):
    """A plugin written before the hand-off: write_sequence, no write_transition."""

    write_transition = OutputPluginBase.write_transition

    def write_sequence(self, frames, *, cancel):
        self.calls.append(("write_sequence", frames))
        return self.result


def driven(cls=LedSign, charset=LED_3X5):
    plugin = cls()
    return plugin, OutputPluginDriver(plugin, character_set=charset)


def render(driver, message, strategy=None, charset=LED_3X5):
    projected = frame(message, charset)
    kw = {"cells": projected.cells} if projected.cells is not None else {}
    return driver.render(projected.characters, strategy=strategy, **kw)


def kinds(plugin):
    return [call[0] for call in plugin.calls]


class TestTheTransitionHandOff:
    def test_the_first_frame_has_nothing_to_flip_from_and_lands_as_a_still(self):
        plugin, driver = driven()
        render(driver, "HELLO")
        assert kinds(plugin) == ["write_cells"]

    def test_a_change_hands_over_both_rich_frames_and_the_boards_resolved_transition(self):
        plugin, driver = driven()
        render(driver, "{red:HELLO}")
        render(driver, "{green:WORLD} {icon:sun}")
        name, before, after, transition = plugin.calls[-1]
        assert name == "write_transition"
        assert before == frame("{red:HELLO}").cells
        assert after == frame("{green:WORLD} {icon:sun}").cells
        assert transition == resolve_led_transition(None, PIXOO)
        # What FiestaUI previews for a Pixoo: the coarse flip in its 32-frame budget.
        assert (transition.id, transition.source) == ("flip", "default")
        assert (transition.spec.max_frames, transition.spec.half_flap) == (32, False)

    def test_the_change_is_one_write_and_lands_as_the_shown_frame(self):
        plugin, driver = driven()
        render(driver, "HELLO")
        render(driver, "WORLD")
        assert kinds(plugin) == ["write_cells", "write_transition"]
        assert driver._frames.characters == frame("WORLD").characters
        assert driver._frames.cells == frame("WORLD").cells

    def test_an_unchanged_frame_reaches_nothing(self):
        plugin, driver = driven()
        render(driver, "HELLO")
        render(driver, "HELLO")
        assert kinds(plugin) == ["write_cells"]

    def test_a_recolour_is_a_change(self):
        plugin, driver = driven()
        render(driver, "{red:HELLO}")
        render(driver, "{green:HELLO}")
        assert kinds(plugin) == ["write_cells", "write_transition"]

    def test_an_led_transition_named_by_the_strategy_is_the_explicit_choice(self):
        plugin, driver = driven()
        render(driver, "HELLO")
        render(driver, "WORLD", strategy="fade")
        transition = plugin.calls[-1][3]
        assert transition == resolve_led_transition("fade", PIXOO)
        assert (transition.id, transition.source) == ("fade", "explicit")

    def test_none_snaps(self):
        plugin, driver = driven()
        render(driver, "HELLO")
        render(driver, "WORLD", strategy="none")
        assert kinds(plugin) == ["write_cells", "write_cells"]

    @pytest.mark.parametrize("strategy", ["column", "plugin:typewriter"])
    def test_a_split_flap_strategy_means_the_models_default_on_an_led_board(self, strategy):
        plugin, driver = driven()
        render(driver, "HELLO")
        render(driver, "WORLD", strategy=strategy)
        assert plugin.calls[-1][3] == resolve_led_transition(None, PIXOO)

    def test_a_failed_transition_is_not_recorded_so_the_frame_is_retried(self):
        plugin, driver = driven()
        render(driver, "HELLO")
        plugin.result = WriteResult(False, False)
        render(driver, "WORLD")
        plugin.result = WriteResult(True, True)
        render(driver, "WORLD")
        assert kinds(plugin) == ["write_cells", "write_transition", "write_transition"]
        assert plugin.calls[-1][1] == frame("HELLO").cells

    def test_a_board_with_no_rich_cells_flips_from_and_to_its_codes(self):
        plugin, driver = driven(charset=None)
        render(driver, "HELLO", charset=None)
        render(driver, "WORLD", charset=None)
        name, before, after, _ = plugin.calls[-1]
        assert name == "write_transition"
        assert before == cells_from_codes(frame("HELLO", None).characters)
        assert after == cells_from_codes(frame("WORLD", None).characters)


class TestBackwardCompatibility:
    def test_a_plugin_without_write_transition_gets_plain_writes(self):
        plugin, driver = driven(SequenceOnly)
        render(driver, "HELLO")
        render(driver, "WORLD")
        assert kinds(plugin) == ["write_cells", "write_cells"]

    def test_a_sequence_only_plugin_still_uploads_a_transition_plugins_frames(self):
        from unittest.mock import MagicMock

        plugin, driver = driven(SequenceOnly)
        runner = MagicMock()
        runner.collect_frames.return_value = [(frame("AB").characters, 100), (frame("WORLD").characters, 100)]
        driver.set_transition_runner(runner)
        render(driver, "HELLO")
        from unittest.mock import patch

        with patch("src.outputs.plugin_driver.transition_plugins_enabled", return_value=True):
            render(driver, "WORLD", strategy="plugin:typewriter")
        assert kinds(plugin) == ["write_cells", "write_sequence"]


# --- accessors ------------------------------------------------------------------------------


class Bare(OutputPluginBase):
    def write(self, frame, *, native, cancel):
        return WriteResult(True, True)


class TestAccessors:
    def test_nothing_is_known_before_core_binds_anything(self):
        plugin = Bare("b", {})
        assert (plugin.device_model, plugin.character_set, plugin.board_geometry) == (None, None, None)

    def test_core_binds_the_boards_model_set_and_grid(self):
        plugin = LedSign()
        assert plugin.device_model == PIXOO
        assert plugin.character_set == LED_3X5
        assert plugin.board_geometry == (ROWS, COLS)

    def test_the_accessors_hand_out_copies(self):
        model, charset = copy.deepcopy(PIXOO), copy.deepcopy(LED_3X5)
        plugin = LedSign()
        plugin.device_model["geometry"]["width"] = 1
        plugin.character_set["chars"].clear()
        assert plugin.device_model == model and model == PIXOO
        assert plugin.character_set == charset and charset == LED_3X5

    @pytest.fixture
    def loaded(self):
        loader = PluginLoader(plugins_dir=FIXTURES, external_dirs=[])
        assert loader.load_plugin("recording_output") is not None, loader.load_errors
        yield
        loader.unload_plugin("recording_output")

    def test_a_board_built_by_core_sees_its_own_model_set_and_grid(self, loaded):
        from src.outputs.factory import build_driver

        driver = build_driver(
            {
                "id": "px",
                "name": "Pixoo",
                "output": "recording_output",
                "output_config": {"host": "192.0.2.60"},
                "device_model": "divoom_pixoo64",
                "device_type": "panel",
                "grid_rows": 10,
                "grid_cols": 16,
            }
        )
        plugin = driver.plugin
        assert plugin.device_model == PIXOO
        # The plugin's declared set wins over the model's (plan D17), materialised.
        assert plugin.character_set["id"] == "recording_sign_v1"
        assert "€" in plugin.character_set["chars"] and plugin.character_set["font"] == "3x5"
        assert plugin.board_geometry == (10, 16)

    def test_a_board_naming_no_model_gets_the_plugins_default_model(self, loaded):
        from src.outputs.factory import build_driver

        driver = build_driver(
            {"id": "r", "name": "R", "output": "recording_output", "output_config": {"host": "192.0.2.61"}}
        )
        assert driver.plugin.device_model["id"] == "recording_sign"
        assert driver.plugin.board_geometry == (6, 22)

    def test_a_plugin_built_outside_core_reads_its_manifests_default_model(self):
        from src.plugins.manifest import load_manifest

        manifest, errors = load_manifest(FIXTURES / "recording_output" / "manifest.json")
        assert not errors
        plugin = Bare("b", {})
        plugin.bind_manifest(manifest.output)
        assert plugin.device_model["id"] == "recording_sign"
        assert plugin.character_set["id"] == "recording_sign_v1"
        assert plugin.board_geometry == (6, 22)


# --- exports --------------------------------------------------------------------------------

EXPORTS = {
    "BoardToken": "src.markup",
    "characters_to_message": "src.board_chars",
    "cells_from_codes": "src.outputs.cells",
    "layout_message": "src.led",
    "rasterize": "src.led",
    "plan_transition": "src.led",
    "transition_frames": "src.led",
    "resolve_led_transition": "src.led",
    "led_flip_seed": "src.led",
    "led_spec_for_model": "src.led",
    "LedLayoutOptions": "src.led",
    "LedMatrixSpec": "src.led",
    "LedTransitionSpec": "src.led",
    "ResolvedLedTransition": "src.led",
    "OutputHttp": "src.outputs.http",
    "RequestCancelled": "src.outputs.http",
    "OutputHostBlocked": "src.output_allowlist",
    "CellFrame": "src.outputs.plugin_base",
    "RichCellFrame": "src.outputs.plugin_base",
}


@pytest.mark.parametrize("name", sorted(EXPORTS))
def test_the_author_api_is_exported_from_src_plugins(name):
    import importlib

    import src.plugins

    assert name in src.plugins.__all__
    assert getattr(src.plugins, name) is getattr(importlib.import_module(EXPORTS[name]), name)
