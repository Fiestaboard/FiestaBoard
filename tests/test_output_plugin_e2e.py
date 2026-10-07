"""Output plugins end to end: loaded as a class, built per board, driven by core.

The test kit is ``tests/fixtures/plugins/recording_output`` — a test-only
output plugin that records what core hands it. Pinned here:

- the loader loads the CLASS and manifest — no instance — and registers the
  output beside the built-ins; unloading forgets it; an id a built-in holds
  is refused;
- a board whose ``output`` names the plugin gets its own instance, opened,
  and an engine send reaches ``write()`` with the frame; the instance is
  closed when the board's connection changes;
- core's policy holds through the adapter: the floor is keyed by the
  plugin's ``device_key`` (shared across boards on one device), a newer
  write cancels the one in flight, a native transition reaches the plugin
  only when declared, and a ``sequence`` output gets ``write_sequence``;
- an output plugin installed from the marketplace or a git URL builds with
  no opt-in (settings v7), still behind the timeout and breaker;
- the board's ``output_config`` masks declared secrets, nested ones too, and
  restores them when echoed back; legacy boards save unchanged.
"""

from __future__ import annotations

import shutil
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.devices import BUILTIN_OUTPUT_IDS
from src.outputs.factory import build_driver
from src.outputs.plugin_driver import OutputPluginDriver, compress_sequence
from src.outputs.plugin_registration import OutputPluginEntry
from src.outputs.registry import FIESTAPANEL, VESTABOARD, output_registry
from src.plugins.loader import PluginLoader

FIXTURES = Path(__file__).parent / "fixtures" / "plugins"
PLUGIN_ID = "recording_output"
GRID = [[1] * 22 for _ in range(6)]
OTHER = [[2] * 22 for _ in range(6)]


def board(board_id: str = "rec", **config) -> dict:
    return {
        "id": board_id,
        "name": f"Sign {board_id}",
        "device_type": "flagship",
        "output": PLUGIN_ID,
        "output_config": {"host": "192.0.2.50", **config},
    }


@pytest.fixture
def module():
    """The fixture plugin's module, as the loader imported it."""
    import sys

    return sys.modules[f"plugins.{PLUGIN_ID}"]


@pytest.fixture
def loaded():
    """The recording output, loaded from the bundled-plugins position."""
    loader = PluginLoader(plugins_dir=FIXTURES, external_dirs=[])
    entry = loader.load_plugin(PLUGIN_ID)
    assert entry is not None, loader.load_errors
    # Every unload evicts the module, so each load imports it afresh and
    # INSTANCES starts empty: whatever is in it was built after the import.
    yield loader
    loader.unload_plugin(PLUGIN_ID)


@pytest.fixture
def external(tmp_path):
    """The recording output installed as an EXTERNAL plugin (the marketplace's way)."""
    external = tmp_path / "external"
    shutil.copytree(FIXTURES / PLUGIN_ID, external / PLUGIN_ID)
    loader = PluginLoader(plugins_dir=tmp_path / "builtin", external_dirs=[external])
    assert loader.load_plugin(PLUGIN_ID) is not None, loader.load_errors
    yield loader
    loader.unload_plugin(PLUGIN_ID)


# --- the loader ------------------------------------------------------------------------


class TestLoader:
    def test_the_loader_keeps_the_class_and_builds_no_instance(self, loaded, module):
        entry, manifest = loaded.output_plugins[PLUGIN_ID]
        assert isinstance(entry, OutputPluginEntry)
        assert entry.plugin_class is module.RecordingOutput
        assert manifest.output is not None
        assert module.INSTANCES == []

    def test_the_output_registers_beside_the_built_ins(self, loaded):
        assert output_registry().ids() == sorted([FIESTAPANEL, PLUGIN_ID, VESTABOARD])
        assert output_registry().get(PLUGIN_ID).plugin is True

    def test_unloading_forgets_the_output(self, loaded):
        loaded.unload_plugin(PLUGIN_ID)
        assert output_registry().get(PLUGIN_ID) is None
        assert output_registry().ids() == [FIESTAPANEL, VESTABOARD]

    def test_an_output_plugin_cannot_take_a_built_in_id(self, tmp_path):
        target = tmp_path / VESTABOARD
        shutil.copytree(FIXTURES / PLUGIN_ID, target)
        manifest = (target / "manifest.json").read_text("utf-8").replace(f'"{PLUGIN_ID}"', f'"{VESTABOARD}"')
        (target / "manifest.json").write_text(manifest, "utf-8")
        sentinel = tmp_path / "imported"
        (target / "__init__.py").write_text(f"open({str(sentinel)!r}, 'w').close()\n", "utf-8")
        loader = PluginLoader(plugins_dir=tmp_path, external_dirs=[])
        loader.load_plugin(VESTABOARD)
        # The id belongs to the first-party output (src/outputs/first_party.py):
        # this copy is never imported, and the Vestaboard's own code still
        # drives its boards.
        assert not sentinel.exists()
        definition = output_registry().get(VESTABOARD)
        assert definition.plugin is False
        assert "recording" not in definition.plugin_class.__module__
        # The registry's own refusal (put_plugin) stands behind it.
        with pytest.raises(ValueError, match="a plugin cannot replace it"):
            output_registry().put_plugin(replace(definition, plugin=True))

    def test_the_plugin_registry_lists_it_as_an_output(self, loaded, monkeypatch):
        from src.plugins.registry import PluginRegistry

        registry = PluginRegistry(plugins_dir=FIXTURES)
        monkeypatch.setattr(registry, "_loader", loaded)
        registry._plugins[PLUGIN_ID], registry._manifests[PLUGIN_ID] = loaded.output_plugins[PLUGIN_ID]
        (row,) = registry.list_plugins()
        assert (row["id"], row["plugin_type"]) == (PLUGIN_ID, "output")
        # Inert where data plugins are fetched: no plugin code runs.
        assert registry.fetch_plugin_data(PLUGIN_ID).available is False

    def test_the_built_in_output_ids_match_the_registry(self):
        assert frozenset({VESTABOARD, FIESTAPANEL}) == BUILTIN_OUTPUT_IDS


# --- per-board instances ------------------------------------------------------------------


class TestPerBoardInstances:
    def test_each_board_gets_its_own_opened_instance(self, loaded, module):
        first = build_driver(board("a"))
        second = build_driver(board("b"))
        assert isinstance(first, OutputPluginDriver)
        assert first.plugin is not second.plugin
        assert [(i.board_id, i.opened) for i in module.INSTANCES] == [("a", True), ("b", True)]
        assert first.plugin.config["host"] == "192.0.2.50"

    def test_an_engine_send_reaches_write_with_the_frame(self, loaded, module):
        from tests.live_boards import install_live_boards

        install_live_boards([board("rec")])
        response = TestClient(_app()).post("/send-message", json={"text": "HELLO", "board_id": "rec"})
        assert response.status_code == 200, response.text
        (instance,) = module.INSTANCES
        assert len(instance.writes) == 1
        assert len(instance.writes[0]) == 6 and len(instance.writes[0][0]) == 22
        assert any(code != 0 for code in instance.writes[0][0] + instance.writes[0][1] + instance.writes[0][2])

    def test_a_changed_board_closes_the_old_instance(self, loaded, module):
        from src.settings.service import get_settings_service
        from tests.live_boards import install_live_boards

        service = install_live_boards([board("rec")])
        (old,) = module.INSTANCES
        get_settings_service().set_boards([board("rec", host="192.0.2.51")])
        service._build_board_clients(sync_cache=False)
        assert old.closed is True
        assert module.INSTANCES[-1].config["host"] == "192.0.2.51" and not module.INSTANCES[-1].closed


# --- core policy through the adapter -----------------------------------------------------


class TestCorePolicy:
    def test_unchanged_frames_never_reach_the_plugin(self, loaded):
        driver = build_driver(board())
        assert driver.send_characters(GRID) == (True, True)
        assert driver.send_characters(GRID) == (True, False)
        assert len(driver.plugin.writes) == 1

    def test_the_floor_is_keyed_by_the_plugins_device_key(self, loaded):
        one = build_driver(board("a", min_interval_ms=60_000))
        two = build_driver(board("b", min_interval_ms=60_000))  # same host: same device
        elsewhere = build_driver(board("c", min_interval_ms=60_000, host="192.0.2.99"))
        assert one.send_characters(GRID) == (True, True)
        outcome = two.send_characters(OTHER, with_outcome=True)
        assert (outcome.throttled, outcome.was_sent, outcome.floor_seconds) == (True, False, 60)
        assert two.plugin.writes == []
        assert elsewhere.send_characters(OTHER) == (True, True)

    def test_a_newer_write_cancels_the_one_in_flight(self, loaded):
        driver = build_driver(board(wait_for_cancel=True))
        done = threading.Event()
        threading.Thread(target=lambda: (driver.send_characters(GRID), done.set()), daemon=True).start()
        assert driver.plugin.write_started.wait(2)
        driver._output_runtime.preempt()
        assert done.wait(2)
        assert driver.plugin.cancelled_writes == 1

    def test_a_declared_native_transition_reaches_the_plugin(self, loaded):
        driver = build_driver(board())
        driver.render(GRID, strategy="column", step_interval_ms=50)
        (native,) = driver.plugin.natives
        assert (native.strategy, native.step_interval_ms) == ("column", 50)

    def test_an_undeclared_native_transition_is_dropped(self, loaded):
        driver = build_driver(board())
        driver.render(GRID, strategy="diagonal")
        assert driver.plugin.natives == [None]

    def test_a_sequence_output_gets_the_whole_transition_in_one_upload(self, loaded, monkeypatch):
        driver = build_driver(board(animation="sequence"))
        runner = _StubRunner([(OTHER, 120), (OTHER, 40)])
        driver.set_transition_runner(runner)
        monkeypatch.setattr("src.outputs.plugin_driver.transition_plugins_enabled", lambda: True)
        assert driver.render(GRID, strategy="plugin:wipe") == (True, True)
        (sequence,) = driver.plugin.sequences
        assert [(f.frame[0][0], f.duration_ms) for f in sequence] == [(2, 120), (2, 40), (1, 0)]
        assert driver.plugin.writes == []
        assert driver._frames.last_frame == GRID

    def test_a_stream_output_gets_the_frames_one_write_at_a_time(self, loaded, monkeypatch):
        driver = build_driver(board())
        driver.set_transition_runner(_StubRunner([(OTHER, 0)]))
        monkeypatch.setattr("src.outputs.plugin_driver.transition_plugins_enabled", lambda: True)
        driver.render(GRID, strategy="plugin:wipe")
        assert driver.plugin.sequences == []
        assert driver.plugin.writes == [OTHER, GRID]

    def test_a_sequence_is_compressed_to_the_models_budget_never_cut(self):
        from src.outputs.plugin_base import TimedFrame

        frames = [TimedFrame([[i]], 10) for i in range(100)]
        kept = compress_sequence(frames, 32)
        assert len(kept) == 32
        assert kept[0].frame == [[0]] and kept[-1].frame == [[99]]

    def test_a_plugin_exception_is_a_failed_write_not_a_crash(self, loaded, monkeypatch):
        driver = build_driver(board(min_interval_ms=60_000))

        def boom(*_a, **_k):
            raise RuntimeError("device on fire")

        monkeypatch.setattr(driver.plugin, "write", boom)
        assert driver.send_characters(GRID) == (False, False)
        monkeypatch.undo()
        # The floor slot was given back: the retry goes straight out.
        assert driver.send_characters(GRID) == (True, True)


# --- no opt-in (settings v7) ---------------------------------------------------------------


class TestNoOptIn:
    """Display plugins need no opt-in: settings v7 dropped
    ``plugins.output_plugins_enabled``. An output plugin installed from the
    marketplace or a git URL builds like a bundled one — behind the same
    safety fences as before (not core's own output: timeout and breaker)."""

    def test_an_installed_output_plugin_builds_behind_the_safety_fences(self, external):
        driver = build_driver(board())
        assert isinstance(driver, OutputPluginDriver)
        assert driver.first_party is False

    def test_its_board_comes_up(self, external):
        from tests.live_boards import install_live_boards

        service = install_live_boards([board("rec")])
        assert service.runtime_for("rec") is not None
        assert "rec" not in service.board_init_errors

    def test_a_bundled_output_plugin_builds(self, loaded):
        assert isinstance(build_driver(board()), OutputPluginDriver)

    def test_the_plugin_settings_carry_no_opt_in(self):
        from src.settings.service import PluginSettings

        assert "output_plugins_enabled" not in PluginSettings().to_dict()
        assert "output_plugins_enabled" not in PluginSettings.from_dict({"output_plugins_enabled": False}).to_dict()


# --- output_config secrets ------------------------------------------------------------------


class TestOutputConfigSecrets:
    def saved(self):
        from src.settings.service import get_settings_service

        return get_settings_service()

    def test_declared_secrets_are_masked_nested_ones_too(self, loaded):
        self.saved().set_boards(
            [board(token="test_token", panels=[{"id": "p1", "key": "test_key_1"}, {"id": "p2", "key": ""}])]
        )
        (shown,) = TestClient(_app()).get("/settings/board").json()["boards"]
        assert shown["output"] == PLUGIN_ID
        assert shown["output_config"]["token"] == "***"
        assert shown["output_config"]["panels"] == [{"id": "p1", "key": "***"}, {"id": "p2", "key": ""}]
        assert shown["output_config"]["host"] == "192.0.2.50"

    def test_echoed_secrets_are_restored(self, loaded):
        self.saved().set_boards([board(token="test_token", panels=[{"id": "p1", "key": "test_key_1"}])])
        client = TestClient(_app())
        boards = client.get("/settings/board").json()["boards"]
        boards[0]["output_config"]["panels"].insert(0, {"id": "p0", "key": "test_key_0"})
        assert client.put("/settings/board", json={"boards": boards}).status_code == 200
        stored = self.saved().get_board_settings().to_dict(mask_secrets=False)["boards"][0]["output_config"]
        assert stored["token"] == "test_token"
        assert stored["panels"] == [{"id": "p0", "key": "test_key_0"}, {"id": "p1", "key": "test_key_1"}]

    def test_an_unmatched_masked_secret_is_refused_not_saved(self, loaded):
        self.saved().set_boards([board(panels=[{"id": "p1", "key": "test_key_1"}])])
        with pytest.raises(ValueError, match="Re-enter"):
            self.saved().set_boards([board(panels=[{"id": "renamed", "key": "***"}])])

    def test_an_invalid_config_is_refused(self, loaded):
        with pytest.raises(ValueError, match="output_config"):
            self.saved().set_boards([board(min_interval_ms="soon")])

    def test_an_uninstalled_outputs_config_is_withheld_and_kept(self, loaded):
        self.saved().set_boards([board(token="test_token")])
        loaded.unload_plugin(PLUGIN_ID)
        client = TestClient(_app())
        boards = client.get("/settings/board").json()["boards"]
        assert boards[0]["output_config"] == "***"
        assert client.put("/settings/board", json={"boards": boards}).status_code == 200
        stored = self.saved().get_board_settings().to_dict(mask_secrets=False)["boards"][0]
        assert stored["output_config"]["token"] == "test_token"

    def test_a_flat_vestaboard_write_saves_in_the_v4_shape(self):
        """Settings v4 (plan D8) stores every board's output; a Vestaboard's
        connection, written flat, lands in its output_config."""
        self.saved().set_boards([{"id": "v", "api_mode": "local", "host": "192.0.2.10", "output": "vestaboard"}])
        (stored,) = self.saved().get_board_settings().to_dict(mask_secrets=False)["boards"]
        assert stored["output"] == "vestaboard"
        assert (stored["output_config"]["api_mode"], stored["output_config"]["host"]) == ("local", "192.0.2.10")
        assert "host" not in stored and "api_mode" not in stored


# --- helpers ----------------------------------------------------------------------------------


def _app():
    from src.api_server import app

    return app


class _StubRunner:
    """A transition runner whose plugin yields *frames* then lands on the target."""

    def __init__(self, frames):
        self.frames = frames

    def collect_frames(self, *, plugin_id, to_grid, cancel_event, device_type, from_grid, config):
        return [*self.frames, (to_grid, 0)]

    def run(self, *, plugin_id, to_grid, board_client, cancel_event, device_type, from_grid, config):
        for grid, _ in self.frames:
            board_client.send_characters(grid, strategy=None, force=True)
            time.sleep(0)
        return board_client.send_characters(to_grid, strategy=None, force=True)
