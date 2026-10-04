"""The output registry: a board resolves to an output id, the id to its driver.

Pinned here:

- the two built-ins (``vestaboard``, ``fiestapanel``) and their capabilities;
- the ONE derivation rule, one test per branch (plan D8): explicit ``output``
  wins → ``api_mode == "virtual"`` → ``fiestapanel`` (including legacy
  virtual note-array panels) → else ``vestaboard``;
- an unknown explicit id builds no driver, through either factory door, and
  is never coerced to a Vestaboard;
- the factory builds every existing configuration through the registry,
  onto the same client as before;
- the board APIs expose the derived ``output`` additively, and a client
  echoing it back never persists it.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from src.outputs.factory import build_driver, draft_driver
from src.outputs.registry import (
    FIESTAPANEL,
    VESTABOARD,
    OutputCapabilities,
    OutputDefinition,
    OutputRegistry,
    UnknownOutputError,
    capabilities_of,
    output_registry,
    resolve_output_id,
)
from src.outputs.transitions import NATIVE_STRATEGIES

LOCAL = {"api_mode": "local", "local_api_key": "test_key", "host": "192.0.2.10"}
RW_CLOUD = {"api_mode": "cloud", "cloud_key": "test_cloud_key"}
NOTE_ARRAY_CLOUD = {"device_type": "note_array", "note_array_token": "test_token", "notes_wide": 2, "notes_tall": 1}
NOTE_ARRAY_LOCAL = {
    "api_mode": "local",
    "device_type": "note_array",
    "notes_wide": 2,
    "notes_tall": 1,
    "tiles": [
        {"row": 0, "col": 0, "host": "192.0.2.21", "local_api_key": "test_k1", "enabled": True},
        {"row": 0, "col": 1, "host": "192.0.2.22", "local_api_key": "test_k2", "enabled": True},
    ],
}
PANEL = {"id": "panel-b", "api_mode": "virtual", "device_type": "panel", "grid_rows": 6, "grid_cols": 22}
LEGACY_VIRTUAL_NOTE_ARRAY = {
    "id": "legacy-panel",
    "api_mode": "virtual",
    "device_type": "note_array",
    "notes_wide": 2,
    "notes_tall": 2,
}


# --- the built-ins ------------------------------------------------------------------


class TestBuiltIns:
    def test_the_registry_holds_exactly_the_two_built_ins(self):
        assert output_registry().ids() == [FIESTAPANEL, VESTABOARD]

    def test_vestaboard_is_a_pushed_split_flap_with_the_local_apis_native_transitions(self):
        assert capabilities_of(VESTABOARD) == OutputCapabilities(
            technology="split_flap",
            delivery="push",
            animation="stream",
            native_transitions=NATIVE_STRATEGIES,
        )

    def test_fiestapanel_is_a_pulled_screen_with_no_native_transitions(self):
        assert capabilities_of(FIESTAPANEL) == OutputCapabilities(
            technology="screen",
            delivery="pull",
            animation="stream",
            native_transitions=frozenset(),
        )

    def test_an_unknown_id_has_no_capabilities(self):
        assert capabilities_of("pixoo") is None
        assert capabilities_of(None) is None

    def test_registering_an_id_twice_is_refused(self):
        registry = OutputRegistry()
        definition = OutputDefinition(
            id="x", name="X", capabilities=capabilities_of(VESTABOARD), build=lambda board: None
        )
        registry.register(definition)
        with pytest.raises(ValueError, match="already registered"):
            registry.register(definition)


# --- the derivation rule (plan D8), one test per branch ----------------------------


class TestResolveOutputId:
    def test_an_explicit_output_wins_over_api_mode(self):
        assert resolve_output_id({"output": VESTABOARD, "api_mode": "virtual"}) == VESTABOARD
        assert resolve_output_id({"output": FIESTAPANEL, **LOCAL}) == FIESTAPANEL

    def test_a_virtual_board_is_a_fiestapanel(self):
        assert resolve_output_id(PANEL) == FIESTAPANEL

    def test_a_legacy_virtual_note_array_panel_is_a_fiestapanel(self):
        assert resolve_output_id(LEGACY_VIRTUAL_NOTE_ARRAY) == FIESTAPANEL

    @pytest.mark.parametrize("board", [LOCAL, RW_CLOUD, NOTE_ARRAY_CLOUD, NOTE_ARRAY_LOCAL, {}])
    def test_everything_else_is_a_vestaboard(self, board):
        assert resolve_output_id(board) == VESTABOARD

    def test_an_unknown_explicit_id_is_returned_as_given_never_coerced(self):
        assert resolve_output_id({"output": "pixoo", **LOCAL}) == "pixoo"


# --- the factory resolves through the registry --------------------------------------


class TestFactoryBuildsThroughTheRegistry:
    @pytest.mark.parametrize("door", [build_driver, draft_driver])
    def test_an_unknown_explicit_output_builds_no_driver(self, door, caplog):
        board = {"id": "b-unknown", "output": "pixoo", **LOCAL}
        with caplog.at_level(logging.ERROR, logger="src.outputs.registry"), pytest.raises(UnknownOutputError):
            door(board)
        assert "pixoo" in caplog.text

    @pytest.mark.parametrize(
        ("board", "kind"),
        [
            (LOCAL, ("VestaboardOutput", "local")),
            (RW_CLOUD, ("VestaboardOutput", "cloud")),
            (NOTE_ARRAY_CLOUD, ("VestaboardOutput", "note_array_cloud")),
            (NOTE_ARRAY_LOCAL, ("VestaboardOutput", "local_tiles")),
            (PANEL, ("FiestaPanelOutput", None)),
            (LEGACY_VIRTUAL_NOTE_ARRAY, ("FiestaPanelOutput", None)),
        ],
        ids=["local", "rw-cloud", "note-array-cloud", "note-array-local", "panel", "legacy-virtual-note-array"],
    )
    def test_each_existing_configuration_builds_its_client(self, board, kind):
        plugin = build_driver(board).plugin
        connection = getattr(plugin, "connection", None)
        assert (type(plugin).__name__, connection.mode if connection is not None else None) == kind

    def test_an_explicit_fiestapanel_builds_a_virtual_board_whatever_its_api_mode(self):
        board = {"id": "explicit-panel", "output": FIESTAPANEL, "device_type": "flagship", **LOCAL}
        driver = build_driver(board)
        assert type(driver.plugin).__name__ == "FiestaPanelOutput"
        assert driver.is_virtual is True

    def test_the_factory_calls_the_registered_builder(self, monkeypatch):
        import src.outputs.registry as registry_module

        built: list[dict] = []
        fake = OutputRegistry()
        fake.register(
            OutputDefinition(
                id=VESTABOARD,
                name="Vestaboard",
                capabilities=capabilities_of(VESTABOARD),
                build=lambda board: built.append(board),
            )
        )
        monkeypatch.setattr(registry_module, "_registry", fake)
        assert build_driver(LOCAL) is None
        assert built == [LOCAL]

    @pytest.mark.parametrize(
        "board",
        [LOCAL, RW_CLOUD, NOTE_ARRAY_CLOUD, NOTE_ARRAY_LOCAL, PANEL],
        ids=["local", "rw-cloud", "note-array-cloud", "note-array-local", "panel"],
    )
    def test_a_drivers_capabilities_stay_within_its_outputs(self, board):
        caps = capabilities_of(resolve_output_id(board))
        driver = build_driver(board)
        assert driver.animation == caps.animation
        assert driver.native_transitions <= caps.native_transitions


# --- the board APIs expose the derived output -------------------------------------


@pytest.fixture
def api() -> TestClient:
    from src.api_server import app

    return TestClient(app)


@pytest.fixture
def saved_boards(monkeypatch):
    """Two saved boards with live runtimes; a boards PUT rebuilds nothing."""
    from src.settings.service import get_settings_service
    from tests.live_boards import install_live_boards

    install_live_boards(
        [
            {"id": "b-vesta", "name": "Kitchen", "device_type": "flagship", **LOCAL},
            {**PANEL, "id": "b-panel", "name": "TV"},
        ]
    )
    monkeypatch.setattr("src.settings.routes.reinitialize_board_clients", lambda: None)
    return get_settings_service()


class TestBoardApisExposeTheOutput:
    def test_settings_boards_carry_their_derived_output(self, api, saved_boards):
        boards = api.get("/settings/board").json()["boards"]
        assert {b["id"]: b["output"] for b in boards} == {"b-vesta": VESTABOARD, "b-panel": FIESTAPANEL}

    def test_v1_board_summaries_carry_their_derived_output(self, api, saved_boards):
        boards = api.get("/v1/boards").json()["boards"]
        assert {b["id"]: b["output"] for b in boards} == {"b-vesta": VESTABOARD, "b-panel": FIESTAPANEL}

    def test_v1_board_detail_carries_its_derived_output(self, api, saved_boards):
        assert api.get("/v1/boards/b-panel").json()["output"] == FIESTAPANEL

    def test_echoing_the_boards_back_does_not_persist_output(self, api, saved_boards):
        boards = api.get("/settings/board").json()["boards"]
        assert api.put("/settings/board", json={"boards": boards}).status_code == 200
        stored = saved_boards.get_board_settings().to_dict(mask_secrets=False)["boards"]
        assert all("output" not in b for b in stored)
