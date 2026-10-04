"""The output conformance suite: it passes the test kit and fails the broken.

``src/outputs/conformance.py`` is what output plugin repos run in their CI,
so a rule that cannot fail protects nobody. Each rule is proven here twice:
the core test kit (``tests/fixtures/plugins/recording_output``) passes it,
and a deliberately broken plugin — one fault each — fails it, naming that
rule.
"""

from __future__ import annotations

import contextlib
import json
import shutil
import threading
import time
import uuid
from dataclasses import replace
from pathlib import Path

import pytest

from src.fiestaui import builtin_device_models
from src.outputs.conformance import FakeTransport, OutputConformanceSuite, TransportError, model_cell_grid
from src.plugins import WriteResult
from tests.fixtures.plugins.recording_output import RecordingOutput

KIT = Path(__file__).parent / "fixtures" / "plugins" / "recording_output"
#: Three panels: every write is three device requests, so cancel and partial
#: writes are observable. Secrets set so device_key is checked for leaks.
CONFIG = {
    "host": "192.0.2.50",
    "token": "test_token_conformance",
    "panels": [{"id": "left", "key": "test_key_left"}, {"id": "mid", "key": "test_key_mid"}, {"id": "right"}],
}


def factory_for(cls: type[RecordingOutput]):
    def make(board_id, config, transport):
        plugin = cls(board_id, config)
        plugin.transport = transport
        return plugin

    return make


def decode(payload):
    return payload.get("frame") if isinstance(payload, dict) and payload.get("panel") == "board" else None


def suite(cls: type[RecordingOutput] = RecordingOutput, plugin_dir: Path = KIT, **config) -> OutputConformanceSuite:
    return OutputConformanceSuite(plugin_dir, factory_for(cls), {**CONFIG, **config}, decode=decode, latency=0.15)


def rules_broken(s: OutputConformanceSuite, rule: str) -> set[str]:
    report = s.run((rule,))
    return {v.rule for v in report.violations}


# --- the test kit passes ---------------------------------------------------------------------


class TestTheKitConforms:
    def test_the_recording_output_conforms_as_a_stream_output(self):
        report = suite().assert_conformant()
        assert any(s.startswith("sequence:") for s in report.skipped)  # stream: no sequence rule

    def test_the_recording_output_conforms_as_a_sequence_output(self):
        # One request per frame (no panels), so the uploaded frames decode.
        report = suite(animation="sequence", panels=[]).assert_conformant()
        assert not any(s.startswith("sequence:") for s in report.skipped)

    def test_the_recording_output_conforms_with_a_floor(self):
        report = suite(min_interval_ms=15_000).assert_conformant()
        assert not any(s.startswith("floor:") for s in report.skipped)


# --- broken plugins fail, one rule each --------------------------------------------------------


def manifest_dir(tmp_path: Path, edit) -> Path:
    """A copy of the kit whose manifest *edit* changed."""
    target = tmp_path / "recording_output"
    shutil.copytree(KIT, target, ignore=shutil.ignore_patterns("__pycache__"))
    manifest = json.loads((target / "manifest.json").read_text("utf-8"))
    edit(manifest)
    (target / "manifest.json").write_text(json.dumps(manifest), "utf-8")
    return target


def inline_model(manifest: dict, **model) -> None:
    base = {
        "id": "broken_sign",
        "label": "Broken sign",
        "technology": "split_flap",
        "family": "broken",
        "geometry": {"kind": "cells", "rows": 6, "cols": 22},
        "color": {"kind": "tiles"},
        "charset": "vestaboard_v2",
        "animation": {"delivery": "stream", "maxFps": 10},
    }
    manifest["output"]["device_models"] = [{**base, **model}]


class TestManifestRules:
    def test_an_unsupported_output_api_breaks_manifest(self, tmp_path):
        broken = manifest_dir(tmp_path, lambda m: m["output"].update(output_api=2))
        assert rules_broken(suite(plugin_dir=broken), "manifest") == {"manifest"}

    def test_a_model_embedding_an_unmaterialisable_charset_breaks_character_set(self, tmp_path):
        def edit(m):
            # Schema-valid (a partial set needs only an id), but its parent
            # does not exist, so it can never materialise.
            inline_model(m, charset={"id": "orphan_set", "extends": "no_such_set"})
            del m["output"]["character_set"]

        assert rules_broken(suite(plugin_dir=manifest_dir(tmp_path, edit)), "character_set") == {"character_set"}

    def test_a_model_below_the_note_floor_breaks_geometry_floor(self, tmp_path):
        broken = manifest_dir(tmp_path, lambda m: inline_model(m, geometry={"kind": "cells", "rows": 2, "cols": 10}))
        assert rules_broken(suite(plugin_dir=broken), "geometry_floor") == {"geometry_floor"}

    def test_a_pixel_model_too_small_for_its_font_breaks_geometry_floor(self, tmp_path):
        broken = manifest_dir(
            tmp_path,
            lambda m: inline_model(
                m,
                technology="led_matrix",
                geometry={"kind": "pixels", "width": 32, "height": 32},
                color={"kind": "rgb", "bitDepth": 24},
            ),
        )
        assert rules_broken(suite(plugin_dir=broken), "geometry_floor") == {"geometry_floor"}

    def test_the_pixoo_64_grid_follows_its_font(self):
        pixoo = builtin_device_models()["divoom_pixoo64"]
        assert model_cell_grid(pixoo) == (10, 16)  # led_3x5: clears 3x15
        assert model_cell_grid(pixoo, {"id": "five", "font": "5x7"}) == (8, 10)  # led_5x7: does not

    def test_a_network_call_at_import_breaks_import_network(self, tmp_path):
        broken = manifest_dir(tmp_path, lambda m: None)
        (broken / "__init__.py").write_text(
            "import socket\n\n"
            "from src.plugins import OutputPluginBase, WriteResult\n\n"
            "try:  # 'check for updates' at import\n"
            "    socket.create_connection(('192.0.2.1', 80), timeout=0.1)\n"
            "except OSError:\n"
            "    pass\n\n\n"
            "class Phoner(OutputPluginBase):\n"
            "    def write(self, frame, *, native, cancel):\n"
            "        return WriteResult(True, True)\n",
            "utf-8",
        )
        report = suite(plugin_dir=broken).run(("import_network",))
        assert {v.rule for v in report.violations} == {"import_network"}
        assert "192.0.2.1" in report.summary()


class UnstableKey(RecordingOutput):
    def device_key(self):
        return f"recording:{uuid.uuid4().hex}"


class BoardKeyed(RecordingOutput):
    def device_key(self):
        return f"recording:{self.board_id}"


class LeakyKey(RecordingOutput):
    def device_key(self):
        return f"recording:{self.config['host']}:{self.config['token']}"


class SelfThrottling(RecordingOutput):
    def write(self, frame, *, native, cancel):
        time.sleep(0.6)
        return super().write(frame, native=native, cancel=cancel)


class NegativeFloor(RecordingOutput):
    def capabilities(self):
        return replace(super().capabilities(), min_interval_ms=-1)


class SendsLater(RecordingOutput):
    def write(self, frame, *, native, cancel):
        threading.Timer(0.05, lambda: self.transport.send({"late": True})).start()
        return WriteResult(True, True)


class TupleResult(RecordingOutput):
    def write(self, frame, *, native, cancel):
        return tuple(super().write(frame, native=native, cancel=cancel)[:2])


class RaisesOnFailure(RecordingOutput):
    def write(self, frame, *, native, cancel):
        for panel in self.config["panels"]:
            self.transport.send({"panel": panel["id"]})
        return WriteResult(True, True)


class HidesPartial(RecordingOutput):
    def write(self, frame, *, native, cancel):
        result = super().write(frame, native=native, cancel=cancel)
        return WriteResult(False, result.was_sent) if result.partial else result


class ClaimsThrottle(RecordingOutput):
    def write(self, frame, *, native, cancel):
        return super().write(frame, native=native, cancel=cancel)._replace(throttled=True)


class IgnoresCancel(RecordingOutput):
    def write(self, frame, *, native, cancel):
        for panel in self.config["panels"]:
            self.transport.send({"panel": panel["id"]})
        return WriteResult(True, True)


class SequenceIgnoresCancel(RecordingOutput):
    def write_sequence(self, frames, *, cancel):
        for timed in frames:
            self.transport.send({"panel": "board", "frame": timed.frame})
        return WriteResult(True, True)


class EndsOffTarget(RecordingOutput):
    def write_sequence(self, frames, *, cancel):
        return super().write_sequence(list(reversed(frames)), cancel=cancel)


class OverBudget(RecordingOutput):
    def capabilities(self):
        return replace(super().capabilities(), max_frames=4)

    def write_sequence(self, frames, *, cancel):
        return super().write_sequence([f for f in frames for _ in range(2)], cancel=cancel)


class ProbeRaises(RecordingOutput):
    def check_connection(self):
        self.transport.send({"probe": True})
        return super().check_connection()


class ProbeLies(RecordingOutput):
    def check_connection(self):
        from src.outputs.hooks import ConnectionCheck

        with contextlib.suppress(TransportError):
            self.transport.send({"probe": True})
        return ConnectionCheck(success=True, message="fine")


BROKEN = [
    pytest.param(UnstableKey, {}, "device_key", id="device_key-unstable"),
    pytest.param(BoardKeyed, {}, "device_key", id="device_key-per-board"),
    pytest.param(LeakyKey, {}, "device_key", id="device_key-leaks-secret"),
    pytest.param(SelfThrottling, {}, "floor", id="floor-self-throttles"),
    pytest.param(NegativeFloor, {}, "floor", id="floor-negative"),
    pytest.param(SendsLater, {}, "floor", id="floor-sends-after-write"),
    pytest.param(TupleResult, {}, "write_result", id="write_result-tuple"),
    pytest.param(RaisesOnFailure, {}, "write_result", id="write_result-raises"),
    pytest.param(HidesPartial, {}, "write_result", id="write_result-hides-partial"),
    pytest.param(ClaimsThrottle, {}, "write_result", id="write_result-claims-throttle"),
    pytest.param(IgnoresCancel, {}, "cancel", id="cancel-write"),
    pytest.param(SequenceIgnoresCancel, {"animation": "sequence"}, "cancel", id="cancel-write_sequence"),
    pytest.param(EndsOffTarget, {"animation": "sequence", "panels": []}, "sequence", id="sequence-off-target"),
    pytest.param(OverBudget, {"animation": "sequence", "panels": []}, "sequence", id="sequence-over-max-frames"),
    pytest.param(ProbeRaises, {}, "check_connection", id="check_connection-raises"),
    pytest.param(ProbeLies, {}, "check_connection", id="check_connection-lies"),
]


@pytest.mark.parametrize(("cls", "config", "rule"), BROKEN)
def test_a_broken_plugin_breaks_exactly_its_rule(cls, config, rule):
    assert rules_broken(suite(cls, **config), rule) == {rule}
    # Control: the kit with the same settings keeps that rule.
    assert rules_broken(suite(**config), rule) == set()


def test_assert_conformant_lists_every_violation():
    with pytest.raises(AssertionError) as caught:
        suite(LeakyKey).assert_conformant()
    assert "[device_key]" in str(caught.value)


def test_the_fake_transport_records_delays_and_fails():
    transport = FakeTransport(decode=lambda payload: payload)
    transport.reset(latency=0.05, fail=lambda index: index == 1)
    started = time.monotonic()
    assert transport.send([[1]]) == {"ok": True}
    with pytest.raises(TransportError):
        transport.send([[2]])
    assert time.monotonic() - started >= 0.1
    assert [(r.frame, r.failed) for r in transport.requests] == [([[1]], False), ([[2]], True)]
