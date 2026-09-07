"""Value-level contract goldens for the /transitions API (Phase 2 §2, slice 8).

Transition plugins drive the board frame by frame. The Transition Lab in the
web UI replays exactly the grids and delays these endpoints return, so a
dropped ``delay_ms``, an off-by-one ``frame_count`` or a ``capped`` flag that
stopped being set is a user-visible regression a shape golden cannot see.

Unlike the other five domains in this slice, every route here is gated behind
``beta.transition_plugins_enabled`` and answers 404 while it is off — that
gate is itself part of the contract and is pinned first.

Recorded against the UNCONVERTED trunk: every assertion below passed before a
line of this slice's production code changed. The conversion commit re-pins
only what it deliberately changes, and says so inline.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from src.plugins.base import TransitionPluginBase
from src.plugins.manifest import PluginManifest

BETA_OFF_DETAIL = "Transition plugins are an experimental beta. Enable them in Settings → Beta to use this endpoint."


class _TwoFrames(TransitionPluginBase):
    """Yields exactly two frames, so frame_count and delays are checkable."""

    @property
    def plugin_id(self) -> str:
        return "contract_two_frames"

    def generate_frames(self, from_grid, to_grid, device, config) -> Iterator[tuple[list[list[int]], int]]:
        yield [list(row) for row in from_grid], int(config.get("frame_interval_ms", 100))
        yield to_grid, 0


_TWO_FRAMES_MANIFEST = {
    "id": "contract_two_frames",
    "name": "Contract Two Frames",
    "version": "1.0.0",
    "description": "contract fixture",
    "author": "contract",
    "icon": "type",
    "category": "transition",
    "plugin_type": "transition",
    "settings_schema": {
        "type": "object",
        "properties": {"frame_interval_ms": {"type": "integer", "default": 100}},
    },
    "transition_settings": {
        "interruptible": True,
        "min_interval_ms": 25,
        "max_frames": 5,
        "max_runtime_seconds": 60,
    },
}


@pytest.fixture
def client(_isolated_data_dir):
    from src.api_server import app

    return TestClient(app)


@pytest.fixture
def beta_on():
    from src.settings.service import get_settings_service

    settings = get_settings_service()
    settings.update_beta_settings({"transition_plugins_enabled": True})
    return settings


@pytest.fixture
def registry(monkeypatch):
    """A registry holding one hand-built transition plugin.

    Swapped at ``src.plugins.registry._registry`` — the singleton itself, not
    an accessor bound in some module — so the stub survives the handlers
    moving out of ``src.api_server`` into ``src/transitions/routes.py``.
    """
    from src.plugins import registry as registry_mod

    fresh = registry_mod.PluginRegistry()
    plugin = _TwoFrames(_TWO_FRAMES_MANIFEST)
    plugin.config = {"frame_interval_ms": 50}
    fresh._plugins["contract_two_frames"] = plugin
    fresh._manifests["contract_two_frames"] = PluginManifest.from_dict(_TWO_FRAMES_MANIFEST)
    fresh._enabled["contract_two_frames"] = True
    monkeypatch.setattr(registry_mod, "_registry", fresh)
    return fresh


# ---------------------------------------------------------------------------
# The beta gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", "/transitions/plugins", None),
        ("post", "/transitions/preview", {"plugin_id": "contract_two_frames", "to_text": "HI"}),
        ("post", "/transitions/test-live", {"plugin_id": "contract_two_frames", "to_page_id": "p1"}),
        ("post", "/transitions/restore", {}),
    ],
)
def test_every_route_404s_with_the_same_detail_while_the_beta_is_off(client, method, path, body):
    response = client.request(method.upper(), path, json=body)
    assert response.status_code == 404
    assert response.json()["detail"] == BETA_OFF_DETAIL


# ---------------------------------------------------------------------------
# GET /transitions/plugins
# ---------------------------------------------------------------------------


def test_listing_describes_a_plugin_field_by_field(client, beta_on, registry):
    response = client.get("/transitions/plugins")
    assert response.status_code == 200
    (entry,) = [p for p in response.json()["plugins"] if p["id"] == "contract_two_frames"]
    assert entry["name"] == "Contract Two Frames"
    assert entry["description"] == "contract fixture"
    assert entry["icon"] == "type"
    assert entry["version"] == "1.0.0"
    assert entry["author"] == "contract"
    assert entry["settings_schema"]["properties"]["frame_interval_ms"]["default"] == 100
    assert entry["transition_settings"] == {
        "interruptible": True,
        "min_interval_ms": 25,
        "max_frames": 5,
        "max_runtime_seconds": 60,
    }
    assert entry["config"] == {"frame_interval_ms": 50}
    assert entry["strategy"] == "plugin:contract_two_frames", "the strategy string pages store"


def test_listing_is_sorted_by_display_name(client, beta_on, registry):
    names = [p["name"] for p in client.get("/transitions/plugins").json()["plugins"]]
    assert names == sorted(names, key=str.lower)


# ---------------------------------------------------------------------------
# POST /transitions/preview
# ---------------------------------------------------------------------------


def test_preview_without_a_plugin_id_is_rejected(client, beta_on, registry):
    response = client.post("/transitions/preview", json={"to_text": "HI"})
    assert response.status_code == 400
    assert response.json()["detail"] == "plugin_id is required"


def test_preview_of_an_unloaded_plugin_is_a_404_naming_it(client, beta_on, registry):
    response = client.post("/transitions/preview", json={"plugin_id": "ghost", "to_text": "HI"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Transition plugin 'ghost' not loaded or not enabled"


def test_preview_rejects_an_unknown_device_type(client, beta_on, registry):
    response = client.post(
        "/transitions/preview",
        json={"plugin_id": "contract_two_frames", "to_text": "HI", "device_type": "wat"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Unknown device_type: wat"


def test_preview_rejects_an_out_of_range_note_array_geometry(client, beta_on, registry):
    response = client.post(
        "/transitions/preview",
        json={
            "plugin_id": "contract_two_frames",
            "to_text": "HI",
            "device_type": "note_array",
            "notes_wide": 99,
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "notes_wide/notes_tall must be between 1 and 8"


def test_preview_returns_the_frames_and_the_delay_they_add_up_to(client, beta_on, registry):
    response = client.post(
        "/transitions/preview",
        json={
            "plugin_id": "contract_two_frames",
            "from_text": "",
            "to_text": "HELLO",
            "device_type": "flagship",
            "config": {"frame_interval_ms": 50},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["plugin_id"] == "contract_two_frames"
    assert body["device_type"] == "flagship"
    assert body["frame_count"] == 2
    assert body["frame_count"] == len(body["frames"])
    assert body["capped"] is False
    # 50 from the override, then 0 clamped up to the plugin's 25ms floor.
    assert body["total_delay_ms"] == 75
    assert [f["delay_ms"] for f in body["frames"]] == [50, 25]
    for frame in body["frames"]:
        assert len(frame["grid"]) == 6
        assert all(len(row) == 22 for row in frame["grid"])
    assert len(body["from_grid"]) == 6
    assert len(body["to_grid"]) == 6


def test_preview_sizes_the_grids_to_a_note(client, beta_on, registry):
    response = client.post(
        "/transitions/preview",
        json={"plugin_id": "contract_two_frames", "to_text": "HI", "device_type": "note"},
    )
    assert response.status_code == 200
    for frame in response.json()["frames"]:
        assert len(frame["grid"]) == 3
        assert all(len(row) == 15 for row in frame["grid"])


# ---------------------------------------------------------------------------
# POST /transitions/test-live
# ---------------------------------------------------------------------------


def test_live_test_without_a_plugin_id_is_rejected(client, beta_on, registry):
    response = client.post("/transitions/test-live", json={"to_page_id": "p1"})
    assert response.status_code == 400
    assert response.json()["detail"] == "plugin_id is required"


def test_live_test_without_a_to_page_id_is_rejected(client, beta_on, registry):
    response = client.post("/transitions/test-live", json={"plugin_id": "contract_two_frames"})
    assert response.status_code == 400
    assert response.json()["detail"] == "to_page_id is required"


def test_live_test_of_an_unloaded_plugin_is_a_404_naming_it(client, beta_on, registry):
    response = client.post("/transitions/test-live", json={"plugin_id": "ghost", "to_page_id": "p1"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Transition plugin 'ghost' not loaded or not enabled"


def test_live_test_404s_an_unknown_target_board(client, beta_on, registry):
    response = client.post(
        "/transitions/test-live",
        json={"plugin_id": "contract_two_frames", "to_page_id": "p1", "board_id": "no-such-board"},
    )
    assert response.status_code in (404, 503)


# ---------------------------------------------------------------------------
# POST /transitions/restore
# ---------------------------------------------------------------------------


def test_restore_without_a_running_service_is_a_503(client, beta_on, registry):
    response = client.post("/transitions/restore", json={})
    assert response.status_code == 503
    assert response.json()["detail"] == "Service not initialized"


def test_restore_accepts_an_omitted_body(client, beta_on, registry):
    """The body is optional — the primary board is the default target."""
    response = client.post("/transitions/restore")
    assert response.status_code == 503
    assert response.json()["detail"] == "Service not initialized"
