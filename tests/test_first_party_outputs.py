"""The first-party outputs load through the output-plugin path (Phase 4, P4a).

Vestaboard and FiestaPanel are output plugin packages staged in-repo
(``first_party_outputs/``). Core loads them as first-party outputs
(:mod:`src.outputs.first_party`) and their boards keep behaving exactly as
they did when they were in-core clients — the wire goldens
(``tests/test_wire_goldens.py``) pin the bytes; this module pins the seams
the move added:

- the registry entries: loaded from the packages, never beta-gated, never
  replaceable, presented exactly as before (``GET /outputs``);
- the driver adapter's first-party mode and the contract additions the
  packages use (``config_from_board``, ``accepts_frame``, a device's own
  rate limit, ``forced``, ``cache_synced``/``cache_cleared``, pull reads,
  ``markup_follows_charset``, ``connection_label``, ``test_connection``);
- ``OutputHttp.for_first_party``: the requests the legacy clients made.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

from src.outputs.actions import list_outputs
from src.outputs.first_party import FIRST_PARTY_DIR, FIRST_PARTY_OUTPUTS, load_first_party
from src.outputs.hooks import ReadBack
from src.outputs.http import OutputHttp
from src.outputs.plugin_driver import OutputPluginDriver
from src.outputs.registry import FIESTAPANEL, VESTABOARD, OutputDefinition, output_registry
from src.outputs.runtime import OutputRuntime
from src.plugins import OutputPluginBase, WriteResult
from tests.first_party_drivers import cloud_driver, frames_of, local_driver, panel_driver

GOLDEN = Path(__file__).parent / "golden" / "outputs" / "first_party_presentation.json"


def _grid(fill: int = 0, rows: int = 6, cols: int = 22) -> list[list[int]]:
    return [[fill] * cols for _ in range(rows)]


# --- loading ----------------------------------------------------------------------------


class TestLoading:
    @pytest.mark.parametrize("output_id", FIRST_PARTY_OUTPUTS)
    def test_each_package_loads_from_the_staging_dir_with_a_valid_manifest(self, output_id):
        loaded = load_first_party(output_id)
        assert loaded.manifest.id == output_id
        assert loaded.manifest.plugin_type == "output"
        assert loaded.manifest.output.output_api == 1
        assert issubclass(loaded.plugin_class, OutputPluginBase)
        assert (FIRST_PARTY_DIR / output_id / "manifest.json").is_file()

    def test_the_staging_dir_is_not_the_bundled_plugins_dir(self):
        # Bundled plugins/ always win over an installed copy (plan D8): staged
        # there, the released repositories could never update them.
        assert FIRST_PARTY_DIR.name == "first_party_outputs"
        assert not (FIRST_PARTY_DIR.parent / "plugins" / "vestaboard").exists()
        assert not (FIRST_PARTY_DIR.parent / "plugins" / "fiestapanel").exists()

    @pytest.mark.parametrize(
        ("output_id", "plugin"), [(VESTABOARD, "VestaboardOutput"), (FIESTAPANEL, "FiestaPanelOutput")]
    )
    def test_the_registry_entry_builds_the_packages_plugin_in_first_party_mode(self, output_id, plugin):
        board = (
            {"id": "b1", "api_mode": "virtual"}
            if output_id == FIESTAPANEL
            else {"id": "b1", "host": "192.0.2.1", "local_api_key": "k"}
        )
        driver = output_registry().get(output_id).build(board)
        assert isinstance(driver, OutputPluginDriver)
        assert type(driver.plugin).__name__ == plugin
        assert driver.first_party is True

    @pytest.mark.parametrize("output_id", FIRST_PARTY_OUTPUTS)
    def test_first_party_entries_are_never_beta_gated_nor_replaceable(self, output_id):
        definition = output_registry().get(output_id)
        assert (definition.plugin, definition.beta_gated) == (False, False)
        imposter = OutputDefinition(
            id=output_id, name="Imposter", capabilities=definition.capabilities, build=lambda b: None, plugin=True
        )
        with pytest.raises(ValueError, match="built in"):
            output_registry().put_plugin(imposter)

    def test_get_outputs_presents_them_exactly_as_before_the_move(self):
        """Recorded from the in-core built-ins (before this layer); P4c/P4d
        change the presentation on purpose, with the settings."""
        presented = [o for o in list_outputs() if o["id"] in FIRST_PARTY_OUTPUTS]
        assert presented == json.loads(GOLDEN.read_text())

    def test_a_board_with_no_usable_connection_builds_no_driver(self):
        assert output_registry().get(VESTABOARD).build({"api_mode": "cloud", "cloud_key": ""}) is None


# --- the driver's first-party mode --------------------------------------------------------


class _Raising(OutputPluginBase):
    def write(self, frame, *, native, cancel):
        raise RuntimeError("bug")

    def capabilities(self):
        from src.outputs.registry import OutputCapabilities

        return OutputCapabilities(
            technology="split_flap", delivery="push", animation="stream", native_transitions=frozenset()
        )


class TestFirstPartyMode:
    def test_an_unanticipated_error_reaches_the_caller_as_it_always_did(self):
        with pytest.raises(RuntimeError, match="bug"):
            OutputPluginDriver(_Raising("b1", {}), first_party=True).send_characters(_grid())

    def test_a_third_party_plugins_error_is_a_failed_write(self):
        assert OutputPluginDriver(_Raising("b1", {})).send_characters(_grid()) == (False, False)

    @patch("requests.post", side_effect=requests.exceptions.ConnectionError("down"))
    def test_failures_open_no_breaker_and_leave_no_write_error(self, _post, monkeypatch):
        monkeypatch.setattr("first_party_outputs.vestaboard.tiles.SEND_RETRY_BACKOFF_SECONDS", 0.0)
        driver = local_driver("test_key", "192.0.2.77")
        for _ in range(8):
            assert driver.send_characters(_grid(), force=True) == (False, False)
        assert driver.last_write_error is None

    def test_writes_run_on_the_callers_thread(self):
        seen: list[int] = []

        class _Where(_Raising):
            def write(self, frame, *, native, cancel):
                seen.append(threading.get_ident())
                return WriteResult(True, True)

        OutputPluginDriver(_Where("b1", {}), first_party=True).send_characters(_grid())
        assert seen == [threading.get_ident()]


# --- contract additions ---------------------------------------------------------------------


class _Recorder(OutputPluginBase):
    """A plugin that records what core told it."""

    def __init__(self, board_id, config):
        super().__init__(board_id, config)
        self.forced_seen: list[bool] = []
        self.synced: list = []
        self.cleared = 0
        self.answer = WriteResult(True, True)

    def capabilities(self):
        from src.outputs.registry import OutputCapabilities

        return OutputCapabilities(
            technology="split_flap",
            delivery="push",
            animation="stream",
            native_transitions=frozenset(),
            min_interval_ms=int(self.config.get("floor_ms", 0)),
            read_back=ReadBack(True, "cheap", 30),
        )

    def accepts_frame(self, frame):
        return len(frame) == 6

    def write(self, frame, *, native, cancel):
        self.forced_seen.append(self.forced)
        return self.answer

    def read_current(self):
        return _grid(3)

    def cache_synced(self, frame):
        self.synced.append(frame)

    def cache_cleared(self):
        self.cleared += 1

    def connection_label(self):
        return "Recorder API"

    def test_connection(self):
        return False


class TestContractAdditions:
    def test_a_refused_frame_costs_nothing(self):
        plugin = _Recorder("b1", {})
        driver = OutputPluginDriver(plugin)
        runtime = OutputRuntime("b1")
        driver.set_output_runtime(runtime)
        token = runtime.cancel_event
        assert driver.send_characters(_grid(rows=3)) == (False, False)
        assert plugin.forced_seen == []
        assert not token.is_set(), "a refused frame must not preempt the run in flight"

    def test_the_plugin_knows_when_a_write_is_forced(self):
        plugin = _Recorder("b1", {})
        driver = OutputPluginDriver(plugin)
        driver.send_characters(_grid(1))
        driver.send_characters(_grid(1), force=True)
        assert plugin.forced_seen == [False, True]
        assert plugin.forced is False

    def test_a_devices_own_rate_limit_holds_the_slot_for_its_retry_after(self):
        now = [1000.0]
        plugin = _Recorder("b1", {"floor_ms": 15000})
        plugin.device_key = lambda: "recorder:rate-limited"
        driver = OutputPluginDriver(plugin, clock=lambda: now[0])
        plugin.answer = WriteResult(True, False, throttled=True, retry_after_seconds=40)
        outcome = driver.send_characters(_grid(1), with_outcome=True)
        assert (outcome.throttled, outcome.retry_after_seconds, outcome.floor_seconds) == (True, 40, 15)
        assert driver.last_send_throttled is True
        assert frames_of(driver).last_frame is None
        plugin.answer = WriteResult(True, True)
        now[0] += 20.0  # past the 15 s floor, inside the device's 40 s
        assert driver.send_characters(_grid(2), with_outcome=True).throttled is True
        assert len(plugin.forced_seen) == 1, "the held slot kept the plugin from being called"

    def test_core_tells_the_plugin_when_it_syncs_or_forgets_the_board(self):
        plugin = _Recorder("b1", {})
        driver = OutputPluginDriver(plugin)
        driver.read_current_message()
        assert plugin.synced == []
        driver.read_current_message(sync_cache=True)
        driver.clear_cache()
        assert (plugin.synced, plugin.cleared) == ([_grid(3)], 1)

    def test_the_label_and_reachability_are_the_plugins(self):
        driver = OutputPluginDriver(_Recorder("b1", {}))
        assert (driver.connection_label, driver.test_connection()) == ("Recorder API", False)

    def test_a_pull_board_reads_back_what_core_stored_in_its_shape(self):
        driver = panel_driver("note")
        assert driver.read_current_message() is None
        driver.send_characters(_grid(5, 3, 15))
        assert driver.read_current_message() == _grid(5, 3, 15)
        frames_of(driver).record_sent(_grid(6))  # a frame of another shape (a re-fit)
        assert driver.read_current_message() is None

    def test_an_output_whose_markup_does_not_follow_its_set_gets_none(self):
        # A FiestaPanel's LED look draws with a rich set; its content keeps
        # split-flap markup all the same (the viewer draws the 0-71 grid).
        from src.outputs.board_profile import board_character_set

        board = {"id": "led-panel", "api_mode": "virtual", "device_type": "flagship"}
        with patch("src.outputs.board_profile._panel_render_style", return_value="led_matrix"):
            led_set = board_character_set(board)
            assert led_set["id"] == "led_5x7"
            assert output_registry().get(FIESTAPANEL).build(board).character_set is None
        # The driver keeps the rule whoever builds it.
        panel = load_first_party(FIESTAPANEL).plugin_class("led-panel", {"device_type": "flagship"})
        assert OutputPluginDriver(panel, character_set=led_set).character_set is None

    def test_a_vestaboard_draws_its_flagship_set(self):
        assert local_driver("k", "192.0.2.1").character_set["id"] == "vestaboard_v1"


# --- OutputHttp.for_first_party ----------------------------------------------------------------


class TestFirstPartyHttp:
    def test_a_first_party_request_is_the_requests_module_call_in_the_callers_order(self):
        with patch("requests.post") as post:
            OutputHttp.for_first_party().post("http://192.0.2.1/x", headers={"h": "1"}, json=[1], timeout=(3.0, 10.0))
        assert post.call_args.args == ("http://192.0.2.1/x",)
        assert list(post.call_args.kwargs.items()) == [("headers", {"h": "1"}), ("json", [1]), ("timeout", (3.0, 10.0))]

    def test_a_third_party_request_never_follows_a_redirect(self):
        with patch("requests.Session.request") as request:
            OutputHttp().post("http://192.0.2.1/x", json=[1])
        assert request.call_args.kwargs["allow_redirects"] is False

    def test_the_fence_still_applies_to_first_party_requests(self, monkeypatch):
        from src.output_allowlist import OutputHostBlocked

        monkeypatch.setenv("FIESTABOARD_OUTPUTS_ALLOW_HOSTS", "fiestaboard-mock-board")
        with patch("requests.post") as post, pytest.raises(OutputHostBlocked):
            OutputHttp.for_first_party().post("http://192.0.2.1/x", json=[1])
        post.assert_not_called()

    def test_the_rw_cloud_floor_is_keyed_by_the_plugins_device_key(self):
        driver = cloud_driver("test_floor_key", clock=lambda: 50.0)
        with patch("requests.post", return_value=Mock(raise_for_status=Mock())):
            assert driver.send_characters(_grid(1)) == (True, True)
            assert cloud_driver("test_floor_key", clock=lambda: 55.0).send_characters(_grid(2)) == (True, False)
