"""The Vestaboard plugin on its own: settings, capabilities and the wire.

FiestaBoard core's own tests drive the plugin through the board driver and
pin its wire byte for byte (``tests/golden/wire``); these pin what the
plugin itself decides, against a scripted device behind ``self.http``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import requests

from first_party_outputs.vestaboard import VestaboardOutput
from first_party_outputs.vestaboard.connection import board_config, normalize_tiles, resolve
from first_party_outputs.vestaboard.output import CLOUD_READ_BACK, LOCAL_READ_BACK, classify_grid, credential_digest
from first_party_outputs.vestaboard.tests.conftest import (
    CLOUD,
    LOCAL,
    NOTE_ARRAY_CLOUD,
    TILES,
    grid,
    response,
    tile,
    token,
)
from first_party_outputs.vestaboard.tiles import identify_pattern, slice_grid, stitch_grid
from first_party_outputs.vestaboard.transport import (
    CLOUD_API_URL,
    CLOUD_NOTE_ARRAY_API_URL,
    VALID_STRATEGIES,
    retry_after_seconds,
)


def pair(result):
    """A write's ``(success, was_sent)``."""
    return (result.success, result.was_sent)


def native(strategy=None, step_interval_ms=None, step_size=None):
    return SimpleNamespace(strategy=strategy, step_interval_ms=step_interval_ms, step_size=step_size)


# --- which connection a board's settings make --------------------------------------------


class TestResolve:
    def test_local_needs_a_host_and_a_key(self):
        assert resolve(LOCAL).mode == "local"
        assert resolve({**LOCAL, "host": ""}) is None
        assert resolve({**LOCAL, "local_api_key": ""}) is None

    def test_api_mode_defaults_to_local(self):
        assert resolve({"host": "192.0.2.10", "local_api_key": "k"}).mode == "local"

    def test_the_port_defaults_to_7000_and_a_bad_one_falls_back(self):
        assert resolve(LOCAL).port == 7000
        assert resolve({**LOCAL, "port": "7001"}).port == 7001
        assert resolve({**LOCAL, "port": "not-a-port"}).port == 7000

    def test_cloud_needs_its_key(self):
        assert resolve(CLOUD).mode == "cloud"
        assert resolve({"api_mode": "CLOUD", "cloud_key": "k"}).mode == "cloud"
        assert resolve({"api_mode": "cloud"}) is None

    def test_a_note_array_without_tiles_uses_its_cloud_token(self):
        connection = resolve(NOTE_ARRAY_CLOUD)
        assert (connection.mode, connection.key, connection.use_cloud) == ("note_array_cloud", "test_token", True)
        assert resolve({**NOTE_ARRAY_CLOUD, "note_array_token": ""}) is None

    def test_a_local_note_array_with_tiles_is_driven_tile_by_tile(self):
        connection = resolve(TILES)
        assert connection.mode == "local_tiles"
        assert [(t.row, t.col, t.port) for t in connection.tiles] == [(0, 0, 7000), (0, 1, 7001)]

    def test_only_in_range_enabled_credentialed_tiles_are_driven(self):
        tiles = [
            tile(0, 0, "192.0.2.21"),
            tile(0, 5, "192.0.2.25"),  # out of range for a 2-wide array
            tile(0, 1, "192.0.2.22", enabled=False),
        ]
        connection = resolve({**TILES, "tiles": tiles})
        assert [(t.row, t.col) for t in connection.tiles] == [(0, 0)]

    def test_a_tile_array_with_nothing_to_drive_is_not_configured(self):
        assert resolve({**TILES, "tiles": [tile(0, 0, "")]}) is None

    def test_a_cloud_note_array_ignores_saved_tiles(self):
        assert resolve({**TILES, "api_mode": "cloud", "note_array_token": "t"}).mode == "note_array_cloud"

    def test_tiles_are_cleaned(self):
        tiles = normalize_tiles(
            [
                "junk",
                {"row": True, "col": 0},
                {"row": -1, "col": 0},
                {"row": "x", "col": 0},
                {"row": 0, "col": 0, "host": " 192.0.2.1 ", "port": "bad", "local_api_key": " k "},
            ]
        )
        assert tiles == [{"row": 0, "col": 0, "host": "192.0.2.1", "port": 7000, "local_api_key": "k", "enabled": True}]
        assert normalize_tiles("nope") == []


class TestConfigFromBoard:
    def test_a_saved_boards_flat_fields_are_its_config(self):
        board = {"id": "b1", "name": "Kitchen", "board_color": "white", **LOCAL, "device_type": "flagship"}
        assert VestaboardOutput.config_from_board(board) == {**LOCAL, "device_type": "flagship"}

    def test_an_output_config_is_laid_over_the_flat_fields(self):
        board = {**LOCAL, "output_config": {"host": "192.0.2.99"}}
        assert board_config(board)["host"] == "192.0.2.99"

    def test_a_board_without_a_usable_connection_has_no_config(self):
        assert VestaboardOutput.config_from_board({"api_mode": "local", "host": "192.0.2.10"}) is None

    def test_constructing_without_a_connection_is_refused(self):
        with pytest.raises(ValueError, match="not configured"):
            VestaboardOutput(None, {"api_mode": "cloud"})


# --- what the board can do ------------------------------------------------------------------


class TestCapabilities:
    def test_the_output_streams_a_split_flap_with_every_native_strategy(self, manifest):
        caps = VestaboardOutput.declared_capabilities(manifest.output)
        assert (caps.technology, caps.delivery, caps.animation) == ("split_flap", "push", "stream")
        assert caps.native_transitions == frozenset(VALID_STRATEGIES)
        assert (caps.min_interval_ms, caps.read_back, caps.device_models, caps.charset) == (0, None, (), None)

    def test_a_local_board_animates_and_is_unfloored(self, make):
        caps = make(LOCAL)[0].capabilities()
        assert caps.native_transitions == frozenset(VALID_STRATEGIES)
        assert (caps.min_interval_ms, caps.read_back) == (0, LOCAL_READ_BACK)

    @pytest.mark.parametrize("config", [CLOUD, NOTE_ARRAY_CLOUD], ids=["rw-cloud", "note-array-cloud"])
    def test_a_cloud_board_has_a_15s_floor_and_no_native_strategy(self, make, config):
        caps = make(config)[0].capabilities()
        assert (caps.native_transitions, caps.min_interval_ms, caps.read_back) == (frozenset(), 15000, CLOUD_READ_BACK)

    def test_capabilities_need_a_bound_manifest(self):
        with pytest.raises(RuntimeError):
            VestaboardOutput(None, LOCAL).capabilities()

    @pytest.mark.parametrize(
        ("config", "label"),
        [(LOCAL, "Local API"), (CLOUD, "Cloud API"), (NOTE_ARRAY_CLOUD, "Cloud API"), (TILES, "Local API")],
    )
    def test_the_connection_label(self, make, config, label):
        assert make(config)[0].connection_label() == label


class TestDeviceKey:
    def test_a_local_board_is_its_endpoint(self, make):
        assert make({**LOCAL, "port": 7001})[0].device_key() == "vestaboard-local:192.0.2.10:7001"

    def test_cloud_boards_are_a_hash_of_their_credential(self, make):
        assert make(CLOUD)[0].device_key() == f"vestaboard-rw-cloud:{credential_digest('test_cloud_key')}"
        assert (
            make(NOTE_ARRAY_CLOUD)[0].device_key() == f"vestaboard-note-array-cloud:{credential_digest('test_token')}"
        )

    def test_a_tile_array_is_its_tiles_endpoints(self, make):
        assert make(TILES)[0].device_key() == "note-array-local:192.0.2.21:7000,192.0.2.22:7001"


# --- writes ------------------------------------------------------------------------------------


class TestWrite:
    def test_a_local_write_carries_the_grid_and_the_native_transition(self, make):
        plugin, device = make(LOCAL)
        result = plugin.write(grid(1), native=native("column", 250, 2), cancel=token())
        assert (result.success, result.was_sent) == (True, True)
        sent = device.requests[0]
        assert sent.url == "http://192.0.2.10:7000/local-api/message"
        assert sent.json == {"characters": grid(1), "strategy": "column", "step_interval_ms": 250, "step_size": 2}
        assert sent.kwargs["headers"]["X-Vestaboard-Local-Api-Key"] == "test_local_key"
        assert sent.timeout == (3.0, 10.0)

    def test_rw_cloud_takes_the_bare_grid(self, make):
        plugin, device = make(CLOUD)
        plugin.write(grid(1), native=None, cancel=token())
        assert (device.requests[0].url, device.requests[0].json) == (CLOUD_API_URL, grid(1))
        assert device.requests[0].kwargs["headers"]["X-Vestaboard-Read-Write-Key"] == "test_cloud_key"
        assert device.requests[0].timeout == (5.0, 10.0)

    def test_a_note_array_cloud_write_drops_any_transition(self, make):
        plugin, device = make(NOTE_ARRAY_CLOUD)
        plugin.write(grid(1, 3, 30), native=native("column"), cancel=token())
        assert (device.requests[0].url, device.requests[0].json) == (
            CLOUD_NOTE_ARRAY_API_URL,
            {"characters": grid(1, 3, 30)},
        )
        assert device.requests[0].kwargs["headers"]["X-Vestaboard-Token"] == "test_token"

    def test_a_grid_no_vestaboard_has_is_refused_without_a_request(self, make):
        plugin, device = make(LOCAL)
        assert plugin.accepts_frame(grid(0, 5, 22)) is False
        assert pair(plugin.write(grid(0, 5, 22), native=None, cancel=token())) == (False, False)
        assert device.requests == []

    def test_a_refused_connection_is_retried_once(self, make):
        plugin, device = make(LOCAL)
        answers = iter([requests.exceptions.ConnectionError("refused"), None])
        device.answer = lambda request: next(answers)
        assert pair(plugin.write(grid(1), native=None, cancel=token())) == (True, True)
        assert len(device.requests) == 2

    def test_a_board_that_went_quiet_is_not_retried(self, make):
        plugin, device = make(LOCAL)
        device.answer = lambda request: requests.exceptions.ReadTimeout("quiet")
        assert pair(plugin.write(grid(1), native=None, cancel=token())) == (False, False)
        assert len(device.requests) == 1

    def test_an_http_error_is_a_failed_write(self, make):
        plugin, device = make(LOCAL)
        device.answer = lambda request: response(500, {"error": "boom"})
        assert pair(plugin.write(grid(1), native=None, cancel=token())) == (False, False)

    def test_a_cloud_429_is_the_devices_floor_with_its_retry_after(self, make):
        plugin, device = make(CLOUD)
        device.answer = lambda request: response(429, headers={"Retry-After": "40"})
        result = plugin.write(grid(1), native=None, cancel=token())
        assert (result.success, result.was_sent, result.throttled, result.retry_after_seconds) == (
            True,
            False,
            True,
            40,
        )

    def test_a_cloud_429_without_retry_after_holds_the_declared_floor(self, make):
        plugin, device = make(NOTE_ARRAY_CLOUD)
        device.answer = lambda request: response(429)
        assert plugin.write(grid(1), native=None, cancel=token()).retry_after_seconds == 15

    def test_a_local_429_is_just_a_failure(self, make):
        plugin, device = make(LOCAL)
        device.answer = lambda request: response(429)
        assert pair(plugin.write(grid(1), native=None, cancel=token())) == (False, False)

    def test_retry_after_reads_both_forms(self):
        assert retry_after_seconds(response(429, headers={"Retry-After": "7"}), 15) == 7
        assert retry_after_seconds(response(429, headers={"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"}), 15) == 1
        assert retry_after_seconds(response(429, headers={"Retry-After": "soon"}), 15) == 15
        assert retry_after_seconds(response(429), None) is None


class TestTiles:
    def test_each_tile_gets_its_slice_on_its_own_endpoint(self, make):
        plugin, device = make(TILES)
        frame = [[(r * 30 + c) % 70 for c in range(30)] for r in range(3)]
        assert pair(plugin.write(frame, native=None, cancel=token())) == (True, True)
        by_url = {r.url: r.json["characters"] for r in device.requests}
        assert by_url["http://192.0.2.21:7000/local-api/message"] == [row[:15] for row in frame]
        assert by_url["http://192.0.2.22:7001/local-api/message"] == [row[15:] for row in frame]

    def test_a_tile_skips_a_slice_it_already_shows_unless_forced(self, make):
        plugin, device = make(TILES)
        plugin.write(grid(1, 3, 30), native=None, cancel=token())
        assert pair(plugin.write(grid(1, 3, 30), native=None, cancel=token())) == (True, False)
        assert len(device.requests) == 2
        plugin.forced = True
        assert pair(plugin.write(grid(1, 3, 30), native=None, cancel=token())) == (True, True)
        assert len(device.requests) == 4

    def test_one_failed_tile_is_a_partial_write_with_its_region(self, make):
        plugin, device = make(TILES)
        device.answer = lambda request: response(500) if "192.0.2.22" in request.url else None
        result = plugin.write(grid(1, 3, 30), native=None, cancel=token())
        assert (result.success, result.was_sent, result.partial) == (False, True, True)
        assert [(r.row, r.col, r.rows, r.cols) for r in result.failed_regions] == [(0, 15, 3, 15)]
        assert plugin.last_tile_results == {(0, 0): (True, True), (0, 1): (False, False)}

    def test_every_tile_failing_is_a_failed_write(self, make):
        plugin, device = make(TILES)
        device.answer = lambda request: response(500)
        result = plugin.write(grid(1, 3, 30), native=None, cancel=token())
        assert (result.success, result.was_sent, result.partial) == (False, False, False)

    def test_a_frame_of_the_wrong_shape_is_refused(self, make):
        plugin, device = make(TILES)
        assert pair(plugin.write(grid(1), native=None, cancel=token())) == (False, False)
        assert device.requests == []

    def test_a_read_is_the_tiles_stitched(self, make):
        plugin, device = make(TILES)
        frame = [[(r * 30 + c) % 70 for c in range(30)] for r in range(3)]
        halves = {"192.0.2.21": [row[:15] for row in frame], "192.0.2.22": [row[15:] for row in frame]}
        device.answer = lambda request: response(200, {"message": halves[request.url.split("//")[1].split(":")[0]]})
        assert plugin.read_current() == frame

    def test_a_read_with_a_failed_tile_is_none_but_the_good_tiles_can_adopt_theirs(self, make):
        plugin, device = make(TILES)
        device.answer = lambda request: (
            response(500) if "192.0.2.22" in request.url else response(200, {"message": grid(4, 3, 15)})
        )
        assert plugin.read_current() is None
        plugin.cache_synced(None)
        # The tile that read back now dedupes against what it showed.
        device.answer = lambda request: None
        device.requests.clear()
        plugin.write([[4] * 15 + [5] * 15 for _ in range(3)], native=None, cancel=token())
        assert [r.url for r in device.requests] == ["http://192.0.2.22:7001/local-api/message"]

    def test_clearing_the_cache_resends_every_tile(self, make):
        plugin, device = make(TILES)
        plugin.write(grid(1, 3, 30), native=None, cancel=token())
        plugin.cache_cleared()
        plugin.write(grid(1, 3, 30), native=None, cancel=token())
        assert len(device.requests) == 4

    def test_a_partly_assigned_array_reads_nothing(self, make):
        plugin, device = make({**TILES, "tiles": [tile(0, 0, "192.0.2.21")]})
        assert plugin.read_current() is None
        assert device.requests == []

    def test_identify_flashes_each_tiles_position_forced(self, make):
        plugin, device = make(TILES)
        assert plugin.identify_tiles([(0, 1), (0, 9)]) == {(0, 1): True, (0, 9): False}
        assert device.requests[0].json["characters"] == identify_pattern(0, 1, 2)
        assert plugin.identify_tiles([(0, 1)]) == {(0, 1): True}
        assert len(device.requests) == 2, "identify is forced: the same flash goes out again"

    def test_identify_all(self, make):
        plugin, device = make(TILES)
        plugin.identify()
        assert len(device.requests) == 2

    def test_only_a_tile_array_identifies_tiles(self, make):
        assert make(LOCAL)[0].identify_tiles is None

    def test_any_answering_tile_is_reachable(self, make):
        plugin, device = make(TILES)
        device.answer = lambda request: (
            response(500) if "192.0.2.22" in request.url else response(200, {"message": grid(0, 3, 15)})
        )
        assert plugin.test_connection() is True
        assert plugin.check_connection().success is True
        device.answer = lambda request: response(500)
        assert plugin.check_connection().failure == "unreachable"

    def test_slice_and_stitch_are_inverses(self):
        frame = [[(r * 30 + c) % 70 for c in range(30)] for r in range(6)]
        assert stitch_grid(slice_grid(frame, 2, 2), 2, 2) == frame
        assert stitch_grid({(9, 9): grid(1, 3, 15), (0, 0): [[1]]}, 1, 1) == grid(0, 3, 15)


# --- reads and probes -------------------------------------------------------------------------


class TestReadAndProbe:
    def test_a_read_parses_the_cloud_layout(self, make):
        plugin, device = make(CLOUD)
        device.answer = lambda request: response(200, {"currentMessage": {"layout": "[[1]]"}})
        assert plugin.read_current() is None  # 1x1 is no Vestaboard
        device.answer = lambda request: response(200, {"message": grid(2)})
        assert plugin.read_current() == grid(2)

    def test_a_failed_read_is_none(self, make):
        plugin, device = make(LOCAL)
        device.answer = lambda request: requests.exceptions.ConnectionError("down")
        assert plugin.read_current() is None
        assert plugin.test_connection() is False

    def test_the_probe_of_a_note_array_uses_its_token_on_the_rw_cloud(self, make):
        plugin, device = make(NOTE_ARRAY_CLOUD)
        device.answer = lambda request: response(200, {"currentMessage": None})
        assert plugin.check_connection().success is True
        assert device.requests[0].url == CLOUD_API_URL
        assert device.requests[0].kwargs["headers"]["X-Vestaboard-Read-Write-Key"] == "test_token"

    def test_detect_geometry_classifies_what_the_board_shows(self, make):
        plugin, device = make(LOCAL)
        device.answer = lambda request: response(200, {"message": grid(0, 3, 15)})
        assert plugin.detect_geometry() == {"device_type": "note", "rows": 3, "cols": 15}
        device.answer = lambda request: requests.exceptions.ConnectionError("down")
        assert plugin.detect_geometry() is None
        assert make(TILES)[0].detect_geometry() is None

    def test_classify_grid(self):
        assert classify_grid(6, 22)["device_type"] == "flagship"
        assert classify_grid(6, 30)["matched_preset"] == "2×2 grid"
        assert classify_grid(9, 45)["matched_preset"] is None
        assert classify_grid(4, 10) is None

    def test_diagnostics_are_the_boards_checks(self, make, monkeypatch):
        from first_party_outputs.vestaboard import diagnostics

        section = {
            "ok": False,
            "mode": "local",
            "steps": {"dns": {"ok": True}, "port": {"ok": False, "error": "closed"}},
        }
        monkeypatch.setattr(diagnostics, "diagnose", lambda board: section)
        checks = make(LOCAL)[0].diagnostics()
        assert [(c.name, c.ok, c.detail) for c in checks] == [("dns", True, ""), ("port", False, "closed")]


class TestEnableLocalApi:
    def test_the_key_comes_back_secret(self, make, monkeypatch):
        from first_party_outputs.vestaboard import local_api

        async def exchange(request):
            assert (request.host, request.enablement_token) == ("192.0.2.10", "test_token")
            return {"success": True, "api_key": "test_new_key", "message": "Local API enabled successfully!"}

        monkeypatch.setattr(local_api, "exchange_enablement_token", exchange)
        outcome = make(LOCAL)[0].action_enable_local_api({"enablement_token": "test_token"})
        assert (outcome.status, outcome.fields["api_key"].value, outcome.fields["api_key"].secret) == (
            "ok",
            "test_new_key",
            True,
        )

    def test_a_refused_token_is_an_error_with_guidance(self, make, monkeypatch):
        from first_party_outputs.vestaboard import local_api

        async def exchange(request):
            return {"success": False, "message": "Invalid enablement token.", "error": "HTTP 401: Unauthorized"}

        monkeypatch.setattr(local_api, "exchange_enablement_token", exchange)
        outcome = make(LOCAL)[0].action_enable_local_api({"enablement_token": "bad"})
        assert (outcome.status, outcome.guidance) == ("error", ("HTTP 401: Unauthorized",))

    def test_the_hook_core_runs_by_name(self, monkeypatch):
        import asyncio

        from first_party_outputs.vestaboard import local_api

        async def exchange(request):
            return {"success": True}

        monkeypatch.setattr(local_api, "exchange_enablement_token", exchange)
        hook = VestaboardOutput.hook_actions()["enable_local_api"]
        assert asyncio.run(hook(SimpleNamespace(host="h", enablement_token="t"))) == {"success": True}
