"""Offline regression contracts for the MCP display and plugin audit."""

import json
import shutil
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.canvas.layer import CanvasLayer
from src.fiestaui import builtin_device_models
from src.led.charsets import materialize_character_set
from src.outputs.cells import project_for_output, project_message
from src.outputs.conformance import OutputConformanceSuite
from src.outputs.geometry import model_cell_grid
from src.outputs.output_manifest import parse_output_block
from src.outputs.plugin_base import OutputPluginBase
from src.outputs.plugin_driver import OutputPluginDriver
from src.outputs.plugin_registration import register_output_plugin
from src.outputs.registry import OutputRegistry
from src.plugins.manifest import PluginManifest
from src.send_outcome import WriteResult
from tests.fixtures.plugins.recording_output import RecordingOutput


class CellProbe(OutputPluginBase):
    """An in-memory output; no device or network transport exists."""

    plugin_id = "audit_cell_probe"

    def __init__(self):
        super().__init__("audit-probe", {})
        self.plain = []
        self.rich = []
        self.sequences = []

    def device_key(self):
        return "audit-cell-probe"

    def write(self, frame, *, native, cancel):
        self.plain.append(frame)
        return WriteResult(True, True)

    def write_cells(self, cells, *, native, cancel):
        self.rich.append(cells)
        return WriteResult(True, True)

    def write_sequence(self, frames, *, cancel):
        self.sequences.append(frames)
        return WriteResult(True, True)


def custom_charset(**changes):
    return materialize_character_set(
        {
            "id": "audit_plain_letters",
            "label": "Audit letters",
            "extends": "led_3x5",
            "chars": ["a", "A"],
            "icons": [],
            "colorSpans": False,
            "blockSpans": False,
            "tiles": False,
            **changes,
        }
    )


def output_manifest(models, charset=None):
    block = {"output_api": 1, "device_models": models}
    if charset is not None:
        block["character_set"] = charset
    manifest, errors = parse_output_block(block, base_dir=None, data_files=[])
    assert not errors, errors
    assert manifest is not None
    return manifest


def probe_driver(manifest):
    plugin = CellProbe()
    plugin.bind_manifest(manifest)
    geometry = model_cell_grid(manifest.model(), manifest.character_set)
    plugin.bind_board(device_model=manifest.model(), character_set=manifest.character_set, geometry=geometry)
    return OutputPluginDriver(plugin, character_set=plugin.character_set)


def test_plain_custom_charset_reaches_its_cell_writer_with_case_and_fallbacks():
    charset = custom_charset()
    model = builtin_device_models()["divoom_pixoo64"]
    model = {**model, "color": {"kind": "monochrome", "color": "#ffffff", "bitDepth": 1}}
    driver = probe_driver(output_manifest([model], charset))
    grid, kwargs = project_for_output(driver, "aB{red}", *driver.plugin.board_geometry)
    assert driver.render(grid, **kwargs) == (True, True)
    assert driver.plugin.rich, {"plain_writes": driver.plugin.plain, "rich_writes": driver.plugin.rich}
    assert [cell.value for cell in driver.plugin.rich[0][0][:3]] == ["a", " ", " "]


def test_rich_custom_charset_does_reach_its_cell_writer_with_fallbacks():
    charset = custom_charset(colorSpans=True)
    driver = probe_driver(output_manifest(["vestaboard_flagship"], charset))
    grid, kwargs = project_for_output(driver, "{red:aB}", 6, 22)
    assert driver.render(grid, **kwargs) == (True, True)
    assert [cell.value for cell in driver.plugin.rich[0][0][:2]] == ["a", " "]
    assert driver.plugin.rich[0][0][0].color == "red"


def test_plain_custom_charset_case_changes_are_not_deduplicated():
    driver = probe_driver(output_manifest(["divoom_pixoo64"], custom_charset()))
    first, first_kw = project_for_output(driver, "a", *driver.plugin.board_geometry)
    second, second_kw = project_for_output(driver, "A", *driver.plugin.board_geometry)
    assert first == second
    assert driver.render(first, **first_kw) == (True, True)
    assert driver.render(second, **second_kw) == (True, True)
    assert [frame[0][0].value for frame in driver.plugin.rich] == ["a", "A"]


def test_a_complete_custom_alphabet_reusing_a_builtin_id_still_projects():
    charset = custom_charset(id="vestaboard_v2")
    frame = project_message("aB{red}", 1, 3, charset)
    assert frame.cells is not None
    assert [cell.value for cell in frame.cells[0]] == ["a", " ", " "]


def test_write_only_output_receives_the_custom_alphabet_integer_fallback():
    class WriteOnlyProbe(CellProbe):
        write_cells = OutputPluginBase.write_cells

    manifest = output_manifest(["vestaboard_flagship"], custom_charset(chars=["1", "2"]))
    plugin = WriteOnlyProbe()
    plugin.bind_manifest(manifest)
    driver = OutputPluginDriver(plugin, character_set=plugin.character_set)
    assert not driver.takes_cells
    grid, kwargs = project_for_output(driver, "A1{red}", 6, 22)
    assert driver.render(grid, **kwargs) == (True, True)
    assert plugin.plain[0][0][:3] == [0, 27, 0]
    assert driver._frames.characters[0][:3] == [0, 27, 0]


def test_sequence_throttled_rich_landing_reports_incomplete_target_and_preserves_floor(monkeypatch):
    model = builtin_device_models()["divoom_pixoo64"]
    model = {**model, "animation": {"delivery": "sequence", "maxFps": 10, "maxFrames": 5}}
    driver = probe_driver(output_manifest([model]))
    capabilities = driver.capabilities
    driver.plugin.capabilities = lambda: replace(capabilities, min_interval_ms=60_000)
    frame = project_message("{red:a}", *driver.plugin.board_geometry, driver.character_set)
    driver.plugin.write_cells = lambda cells, *, native, cancel: WriteResult(
        True, False, throttled=True, retry_after_seconds=120
    )
    driver.set_transition_runner(SimpleNamespace(collect_frames=lambda **kwargs: [(kwargs["to_grid"], 100)]))
    monkeypatch.setattr("src.outputs.plugin_driver.transition_plugins_enabled", lambda: True)

    result = driver.render(frame.characters, cells=frame.cells, strategy="plugin:audit", with_outcome=True)
    assert result.success is False
    assert result.was_sent is True
    assert result.throttled is True
    assert result.retry_after_seconds == 120
    assert "rich target" in driver.last_write_error
    assert driver._frames.characters == frame.characters
    assert driver._frames.cells is None
    retry = driver.render(frame.characters, cells=frame.cells, strategy="plugin:audit", with_outcome=True)
    assert retry.throttled
    assert retry.retry_after_seconds >= 119
    assert len(driver.plugin.sequences) == 1


def test_documented_default_capabilities_require_a_multi_model_plugin_override():
    """Characterize an API limitation; the base class documents this default."""
    model = builtin_device_models()["vestaboard_flagship"]
    first = {**model, "id": "audit_animated", "animation": {"delivery": "sequence", "maxFps": 10, "maxFrames": 2}}
    second = {**model, "id": "audit_static", "animation": {"delivery": "none", "maxFps": 0}}
    manifest = output_manifest([first, second])
    driver = probe_driver(manifest)
    driver.plugin.bind_board(device_model=second, geometry=(6, 22))
    assert driver.plugin.device_model["id"] == "audit_static"
    assert driver.animation == "sequence"
    assert driver.capabilities.max_frames == 2


def test_registration_uses_the_plugins_declared_capabilities_hook(monkeypatch):
    class DeclaredCapabilities(CellProbe):
        @classmethod
        def declared_capabilities(cls, manifest):
            return replace(manifest.capabilities, animation="none", native_transitions=frozenset())

    output = output_manifest(["vestaboard_flagship"])
    manifest = PluginManifest(id="audit_capability_hook", name="Audit", version="1.0.0", output=output)
    registry = OutputRegistry()
    monkeypatch.setattr("src.outputs.plugin_registration.output_registry", lambda: registry)
    register_output_plugin(DeclaredCapabilities, manifest)
    assert registry.get(manifest.id).capabilities == DeclaredCapabilities.declared_capabilities(output)


def test_sequence_transition_lands_on_the_rich_target_and_keeps_it_in_readback(monkeypatch):
    model = builtin_device_models()["divoom_pixoo64"]
    model = {**model, "animation": {"delivery": "sequence", "maxFps": 10, "maxFrames": 5}}
    driver = probe_driver(output_manifest([model]))
    layer = CanvasLayer(x=0, y=0, w=1, h=1, rgba=bytes([255, 0, 0, 255]))
    frame = project_message("{red:a}", *driver.plugin.board_geometry, driver.character_set, layers=[layer])
    # A transition runner returns its ordinary integer projections. Core
    # owns the original rich target and must preserve it at the landing.
    runner = SimpleNamespace(collect_frames=lambda **kwargs: [(kwargs["to_grid"], 100)])
    driver.set_transition_runner(runner)
    monkeypatch.setattr("src.outputs.plugin_driver.transition_plugins_enabled", lambda: True)
    assert driver.render(frame.characters, cells=frame.cells, strategy="plugin:audit") == (True, True)
    assert driver.plugin.sequences, "The test must exercise the sequence upload path"
    assert driver._frames.cells == frame.cells, driver._frames.cells
    assert driver.plugin.rich or getattr(driver.plugin.sequences[-1][-1], "cells", None) == frame.cells
    assert driver._frames.cells.layers == (layer,)


class BrokenRichWriter(RecordingOutput):
    def write_cells(self, cells, *, native, cancel):
        raise RuntimeError("audit rich writer fails")


def rich_suite(tmp_path, cls):
    source = Path(__file__).parent / "fixtures" / "plugins" / "recording_output"
    target = tmp_path / "recording_output"
    shutil.copytree(source, target)
    # Keep the suite's real import and manifest validation, including its
    # rich custom character set, while using a controlled implementation.
    assert json.loads((target / "output" / "character-set.json").read_text())["extends"] == "led_3x5"

    def make(board_id, config, transport):
        plugin = cls(board_id, config)
        plugin.transport = transport
        return plugin

    return OutputConformanceSuite(target, make, {"host": "192.0.2.50"}, latency=0)


def test_conformance_rejects_a_rich_writer_that_fails_every_live_send(tmp_path):
    suite = rich_suite(tmp_path, BrokenRichWriter)
    plugin = suite._plugin()
    try:
        driver = OutputPluginDriver(plugin, character_set=plugin.character_set)
        frame = project_message("A", 6, 22, plugin.character_set)
        assert driver.takes_cells
        assert driver.render(frame.characters, cells=frame.cells) == (False, False)
        assert "audit rich writer fails" in driver.last_write_error
    finally:
        plugin.close()
        plugin.http.close()
    report = suite.run(("write_result", "device_traffic"))
    assert not report.ok, report.summary()


def test_conformance_accepts_the_healthy_control(tmp_path):
    report = rich_suite(tmp_path, RecordingOutput).run(("write_result", "device_traffic"))
    assert report.ok, report.summary()


class HealthyRichWriter(RecordingOutput):
    def write_cells(self, cells, *, native, cancel):
        return self.write([[cell.flap_code for cell in row] for row in cells], native=native, cancel=cancel)


class BrokenTransitionWriter(HealthyRichWriter):
    def write_transition(self, before, after, transition, *, cancel):
        raise RuntimeError("audit transition writer fails")


class BrokenNonDefaultRichWriter(HealthyRichWriter):
    def write_cells(self, cells, *, native, cancel):
        if self.device_model["id"] == "divoom_pixoo64":
            raise RuntimeError("audit nondefault rich writer fails")
        return super().write_cells(cells, native=native, cancel=cancel)


@pytest.mark.parametrize("writer", [BrokenTransitionWriter, BrokenNonDefaultRichWriter])
def test_conformance_rejects_broken_paths_on_nondefault_models(tmp_path, writer):
    report = rich_suite(tmp_path, writer).run(("write_result", "device_traffic"))
    assert not report.ok, report.summary()
    assert "divoom_pixoo64" in report.summary()


def test_conformance_binds_each_models_charset_and_geometry_before_open(tmp_path):
    opened = []

    class ModelProbe(HealthyRichWriter):
        def open(self):
            assert self.character_set["id"] == "recording_sign_v1"
            assert self.board_geometry == model_cell_grid(self.device_model, self.character_set)
            opened.append(self.device_model["id"])
            super().open()

        def write_cells(self, cells, *, native, cancel):
            rows, cols = self.board_geometry
            assert len(cells) == rows
            assert all(len(row) == cols for row in cells)
            assert bool(getattr(cells, "layers", ())) == (self.device_model["geometry"]["kind"] == "pixels")
            return super().write_cells(cells, native=native, cancel=cancel)

    report = rich_suite(tmp_path, ModelProbe).run(("write_result",))
    assert report.ok, report.summary()
    assert opened == ["recording_sign", "divoom_pixoo64"]


class RawRichWriter(HealthyRichWriter):
    def write_cells(self, cells, *, native, cancel):
        import socket

        socket.create_connection(("192.0.2.50", 80), timeout=0.01)
        return WriteResult(True, True)


class BrokenNativeWriter(HealthyRichWriter):
    def write_cells(self, cells, *, native, cancel):
        if native is not None:
            raise RuntimeError("audit native rich writer fails")
        return super().write_cells(cells, native=native, cancel=cancel)


def test_conformance_checks_native_transitions_with_rich_cells(tmp_path):
    report = rich_suite(tmp_path, BrokenNativeWriter).run(("write_result",))
    assert not report.ok, report.summary()
    assert "write_cells(native:column)" in report.summary()


def test_conformance_checks_rich_writer_device_traffic(tmp_path):
    report = rich_suite(tmp_path, RawRichWriter).run(("device_traffic",))
    assert not report.ok, report.summary()
    assert "192.0.2.50" in report.summary()


def test_conformance_checks_the_advertised_transition_writer(tmp_path):
    suite = rich_suite(tmp_path, BrokenTransitionWriter)
    # The second model is the LED; a flap model has no LED transitions.
    path = suite.plugin_dir / "output" / "device-models.json"
    models = json.loads(path.read_text())
    path.write_text(json.dumps([models[1]]))
    report = suite.run(("write_result",))
    assert not report.ok, report.summary()
    assert "write_transition" in report.summary()


def test_conformance_accepts_a_healthy_rich_writer(tmp_path):
    report = rich_suite(tmp_path, HealthyRichWriter).run(("write_result", "device_traffic", "cancel"))
    assert report.ok, report.summary()


def test_sequence_rich_landing_obeys_one_floor_and_dedupes(monkeypatch):
    model = builtin_device_models()["divoom_pixoo64"]
    model = {**model, "animation": {"delivery": "sequence", "maxFps": 10, "maxFrames": 5}}
    driver = probe_driver(output_manifest([model]))
    capabilities = driver.capabilities
    driver.plugin.capabilities = lambda: replace(capabilities, min_interval_ms=60_000)
    frame = project_message("{red:a}", *driver.plugin.board_geometry, driver.character_set)
    driver.set_transition_runner(SimpleNamespace(collect_frames=lambda **kwargs: [(kwargs["to_grid"], 100)]))
    monkeypatch.setattr("src.outputs.plugin_driver.transition_plugins_enabled", lambda: True)
    assert driver.render(frame.characters, cells=frame.cells, strategy="plugin:audit") == (True, True)
    assert len(driver.plugin.rich) == 1
    assert driver.send_characters(frame.characters, cells=frame.cells) == (True, False)


def test_sequence_failure_never_delivers_a_rich_landing(monkeypatch):
    model = builtin_device_models()["divoom_pixoo64"]
    model = {**model, "animation": {"delivery": "sequence", "maxFps": 10, "maxFrames": 5}}
    driver = probe_driver(output_manifest([model]))
    frame = project_message("{red:a}", *driver.plugin.board_geometry, driver.character_set)
    driver.plugin.write_sequence = lambda frames, *, cancel: WriteResult(False, False)
    driver.set_transition_runner(SimpleNamespace(collect_frames=lambda **kwargs: [(kwargs["to_grid"], 100)]))
    monkeypatch.setattr("src.outputs.plugin_driver.transition_plugins_enabled", lambda: True)
    assert driver.render(frame.characters, cells=frame.cells, strategy="plugin:audit") == (False, False)
    assert driver.plugin.rich == []
    assert driver._frames.cells is None


@pytest.mark.parametrize("raises", [False, True])
def test_sequence_rich_landing_failure_keeps_the_integer_target_and_consumed_floor(monkeypatch, raises):
    model = builtin_device_models()["divoom_pixoo64"]
    model = {**model, "animation": {"delivery": "sequence", "maxFps": 10, "maxFrames": 5}}
    driver = probe_driver(output_manifest([model]))
    capabilities = driver.capabilities
    driver.plugin.capabilities = lambda: replace(capabilities, min_interval_ms=60_000)
    frame = project_message("{red:a}", *driver.plugin.board_geometry, driver.character_set)

    def fail(cells, *, native, cancel):
        if raises:
            raise RuntimeError("rich landing failed")
        return WriteResult(False, False)

    driver.plugin.write_cells = fail
    driver.set_transition_runner(SimpleNamespace(collect_frames=lambda **kwargs: [(kwargs["to_grid"], 100)]))
    monkeypatch.setattr("src.outputs.plugin_driver.transition_plugins_enabled", lambda: True)
    assert driver.render(frame.characters, cells=frame.cells, strategy="plugin:audit") == (False, True)
    assert driver._frames.characters == frame.characters
    assert driver._frames.cells is None
    outcome = driver.render(frame.characters, cells=frame.cells, strategy="plugin:audit", with_outcome=True)
    assert outcome.throttled
    assert len(driver.plugin.sequences) == 1
