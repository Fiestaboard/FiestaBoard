"""A display's own transition choice (plan D21).

Each board (display) carries ``transition``: the choice its device menu
offers — a split-flap strategy, ``plugin:<id>``, an LED menu id, or
``"none"``. Since settings v6 there is no install-wide default: these files
predate it, so the v5 -> v6 migration copies their ``transitions`` block onto
boards without a choice. A page's own override still wins at the send sites.
"""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.devices import BoardInstance
from src.main import DisplayService
from src.settings.service import SettingsService, is_valid_board_transition


@pytest.fixture
def settings_file(tmp_path):
    return str(tmp_path / "settings.json")


def _service(settings_file, boards, *, strategy="column", transition_plugins=False):
    Path(settings_file).write_text(
        json.dumps(
            {
                "transitions": {"strategy": strategy, "step_interval_ms": 40, "step_size": 2},
                "beta": {"transition_plugins_enabled": transition_plugins},
                "board": {"board_type": "black", "boards": boards},
            }
        )
    )
    return SettingsService(settings_file=settings_file)


VESTA = {"id": "vb", "name": "Kitchen", "device_type": "flagship", "output": "vestaboard"}
PIXOO = {
    "id": "px",
    "name": "Desk",
    "device_type": "panel",
    "grid_rows": 8,
    "grid_cols": 10,
    "output": "divoom_pixoo",
    "device_model": "divoom_pixoo64",
}


class TestBoardInstanceField:
    def test_a_choice_round_trips(self):
        board = BoardInstance.from_dict({**VESTA, "transition": "diagonal"})
        assert board.to_dict()["transition"] == "diagonal"

    def test_an_unset_choice_is_not_stored(self):
        assert "transition" not in BoardInstance.from_dict(VESTA).to_dict()

    def test_a_blank_choice_is_unset(self):
        assert BoardInstance.from_dict({**VESTA, "transition": "  "}).transition is None

    def test_a_non_string_choice_is_unset(self):
        assert BoardInstance.from_dict({**VESTA, "transition": 3}).transition is None


class TestValidity:
    @pytest.mark.parametrize("choice", [None, "none", "column", "plugin:typewriter", "flip", "fade"])
    def test_menu_choices_are_valid(self, choice):
        assert is_valid_board_transition(choice)

    @pytest.mark.parametrize("choice", ["sparkle", "plugin: ", "constructor"])
    def test_anything_else_is_not(self, choice):
        assert not is_valid_board_transition(choice)


class TestResolution:
    def test_a_display_without_a_choice_runs_the_install_default(self, settings_file):
        svc = _service(settings_file, [VESTA])
        assert svc.get_transition_settings("vb").strategy == "column"

    def test_a_display_choice_replaces_the_install_strategy(self, settings_file):
        svc = _service(settings_file, [{**VESTA, "transition": "diagonal"}])
        resolved = svc.get_transition_settings("vb")
        assert (resolved.strategy, resolved.step_interval_ms, resolved.step_size) == ("diagonal", 40, 2)

    def test_another_display_keeps_its_own(self, settings_file):
        svc = _service(settings_file, [{**VESTA, "transition": "diagonal"}, {**VESTA, "id": "vb2"}])
        assert svc.get_transition_settings("vb").strategy == "diagonal"
        assert svc.get_transition_settings("vb2").strategy == "column"

    def test_none_on_a_vestaboard_is_no_strategy(self, settings_file):
        svc = _service(settings_file, [{**VESTA, "transition": "none"}])
        assert svc.get_transition_settings("vb").strategy is None

    def test_none_on_an_output_plugin_board_stays_the_led_none(self, settings_file):
        """Unset would mean the LED model's default (a flip); "none" must snap."""
        svc = _service(settings_file, [VESTA, {**PIXOO, "transition": "none"}])
        assert svc.get_transition_settings("px").strategy == "none"

    def test_an_unknown_board_has_no_transition(self, settings_file):
        svc = _service(settings_file, [{**VESTA, "transition": "diagonal"}])
        assert svc.get_transition_settings("missing").strategy is None


class TestSaving:
    def test_a_menu_choice_saves(self, settings_file):
        svc = _service(settings_file, [VESTA])
        svc.set_boards([{**VESTA, "transition": "row"}])
        assert svc.get_board_settings().boards[0]["transition"] == "row"

    def test_an_unknown_choice_is_refused(self, settings_file):
        svc = _service(settings_file, [VESTA])
        with pytest.raises(ValueError, match="Invalid transition"):
            svc.set_boards([{**VESTA, "transition": "sparkle"}])
        assert svc.get_board_settings().boards[0]["transition"] == "column"

    def test_a_new_plugin_choice_needs_the_beta(self, settings_file):
        svc = _service(settings_file, [VESTA])
        with pytest.raises(ValueError, match="beta"):
            svc.set_boards([{**VESTA, "transition": "plugin:typewriter"}])

    def test_a_stored_plugin_choice_keeps_saving_with_the_beta_off(self, settings_file):
        svc = _service(settings_file, [{**VESTA, "transition": "plugin:typewriter"}])
        svc.set_boards([{**VESTA, "name": "Hall", "transition": "plugin:typewriter"}])
        assert svc.get_board_settings().boards[0]["name"] == "Hall"

    def test_a_plugin_choice_saves_with_the_beta_on(self, settings_file):
        svc = _service(settings_file, [VESTA], transition_plugins=True)
        svc.set_boards([{**VESTA, "transition": "plugin:typewriter"}])
        assert svc.get_board_settings().boards[0]["transition"] == "plugin:typewriter"

    def test_adding_a_board_with_an_unknown_choice_is_refused(self, settings_file):
        svc = _service(settings_file, [VESTA])
        with pytest.raises(ValueError, match="Invalid transition"):
            svc.add_board({"device_type": "note", "transition": "sparkle"})


class TestSendSites:
    def test_a_send_asks_for_the_target_display_transition(self):
        """The engine's sends resolve the transition for the board they write to."""
        service = DisplayService()
        service.vb_client = Mock()
        service.vb_client.render.return_value = (True, True)
        rt = service._ensure_primary_runtime()
        with (
            patch("src.main.get_settings_service") as settings,
            patch.object(service, "_board_dict_for", return_value={"device_type": "flagship"}),
        ):
            settings.return_value.get_transition_settings.return_value = Mock(
                strategy="diagonal", step_interval_ms=None, step_size=None
            )
            service._send_blank_board()

        settings.return_value.get_transition_settings.assert_called_with(rt.board_id)
        assert service.vb_client.render.call_args.kwargs["strategy"] == "diagonal"
