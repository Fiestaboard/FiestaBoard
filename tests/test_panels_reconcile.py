"""Startup re-fit of panels created before per-character fitting.

Panels used to be fit in whole 15 × 3 Note blocks and stored as
``note_array`` boards (a 55" 16:9 TV: one block wide, 12 × 15). On upgrade,
``reconcile_panel_boards`` re-fits every such board to the per-character
grid (12 × 29) and carries pages sized for the old grid along with it, so
the TV keeps showing what it showed — now across the whole screen.
"""

from __future__ import annotations

import pytest

from src.pages.models import PageCreate
from src.panels.models import Panel
from src.panels.reconcile import reconcile_panel_boards


@pytest.fixture
def services(_isolated_data_dir):
    from src.pages.service import get_page_service
    from src.panels.service import get_panel_service
    from src.settings.service import get_settings_service

    return get_settings_service(), get_panel_service(), get_page_service()


def _legacy_panel(services, *, name="Kitchen TV", board_id="panel-board", diagonal=55.0, notes=(1, 4)):
    """A panel exactly as the Note-block fit stored it."""
    settings, panels, _pages = services
    board = {
        "id": board_id,
        "name": f"{name} (Panel)",
        "device_type": "note_array",
        "api_mode": "virtual",
        "notes_wide": notes[0],
        "notes_tall": notes[1],
    }
    existing = [b for b in settings.get_board_settings().boards or [] if b.get("id") != board_id]
    settings.set_boards([*existing, board])
    return panels.storage.create(Panel(name=name, board_id=board_id, screen_diagonal_inches=diagonal))


def _note_array_page(services, notes=(1, 4), name="Wall"):
    _settings, _panels, pages = services
    return pages.create_page(
        PageCreate(
            name=name,
            type="template",
            template=["HELLO"],
            device_type="note_array",
            notes_wide=notes[0],
            notes_tall=notes[1],
        )
    )


def _board(services, board_id):
    settings, _panels, _pages = services
    return next(b for b in settings.get_board_settings().boards if b["id"] == board_id)


def test_a_note_block_panel_is_re_fit_per_character(services):
    _legacy_panel(services)

    assert reconcile_panel_boards() == 1

    board = _board(services, "panel-board")
    assert (board["device_type"], board["grid_rows"], board["grid_cols"]) == ("panel", 12, 29)


def test_a_page_sized_for_the_old_grid_moves_with_the_panel(services):
    _legacy_panel(services)
    page = _note_array_page(services)

    reconcile_panel_boards()

    moved = services[2].get_page(page.id)
    assert (moved.device_type, moved.grid_rows, moved.grid_cols) == ("panel", 12, 29)
    assert moved.template == ["HELLO"], "content is untouched — it only gains room"


def test_a_page_of_another_size_is_left_alone(services):
    _legacy_panel(services)
    other = _note_array_page(services, notes=(2, 2), name="Other")

    reconcile_panel_boards()

    kept = services[2].get_page(other.id)
    assert (kept.device_type, kept.notes_wide, kept.notes_tall) == ("note_array", 2, 2)


def test_reconcile_is_idempotent(services):
    _legacy_panel(services)
    reconcile_panel_boards()

    assert reconcile_panel_boards() == 0


def test_a_page_a_physical_note_array_still_needs_is_not_moved(services):
    """A real 1x4 note array shares the old size: its pages must stay put."""
    settings, _panels, _pages = services
    settings.set_boards(
        [
            *(settings.get_board_settings().boards or []),
            {"id": "real-array", "device_type": "note_array", "api_mode": "cloud", "notes_wide": 1, "notes_tall": 4},
        ]
    )
    _legacy_panel(services)
    page = _note_array_page(services)

    reconcile_panel_boards()

    kept = services[2].get_page(page.id)
    assert (kept.device_type, kept.notes_wide, kept.notes_tall) == ("note_array", 1, 4)
    assert _board(services, "panel-board")["device_type"] == "panel", "the panel is still re-fit"


def test_pages_stay_put_when_panels_sharing_the_old_size_now_differ(services):
    """A 55" and a 58" TV were both one Note block wide; per character they
    are 29 and 30 columns. A page can only have one size, so neither wins."""
    _legacy_panel(services, name="Kitchen TV", board_id="kitchen", diagonal=55.0)
    _legacy_panel(services, name="Den TV", board_id="den", diagonal=58.0)
    page = _note_array_page(services)

    reconcile_panel_boards()

    assert _board(services, "kitchen")["grid_cols"] != _board(services, "den")["grid_cols"]
    assert services[2].get_page(page.id).device_type == "note_array"


def test_pages_move_when_panels_sharing_the_old_size_fit_the_same(services):
    _legacy_panel(services, name="Kitchen TV", board_id="kitchen", diagonal=55.0)
    _legacy_panel(services, name="Den TV", board_id="den", diagonal=55.0)
    page = _note_array_page(services)

    reconcile_panel_boards()

    assert services[2].get_page(page.id).grid_cols == 29


def test_a_shrinking_re_fit_does_not_crop_pages(services):
    """A stored grid larger than the screen now fits (e.g. a corrupted or
    hand-edited board) is re-fit, but its pages are not shrunk."""
    _legacy_panel(services, notes=(4, 8))  # 60x24 on a 55" TV
    page = _note_array_page(services, notes=(4, 8))

    reconcile_panel_boards()

    assert _board(services, "panel-board")["grid_cols"] == 29
    kept = services[2].get_page(page.id)
    assert (kept.device_type, kept.notes_wide, kept.notes_tall) == ("note_array", 4, 8)


def test_a_re_fit_drops_the_old_shape_frame(services):
    from src.virtual_board_client import VirtualBoardClient

    _legacy_panel(services)
    old = VirtualBoardClient(device_type="note_array", board_id="panel-board", notes_wide=1, notes_tall=4)
    old.send_characters([[1] * 15 for _ in range(12)])
    assert old.read_current_message() is not None, "seed frame never landed"

    reconcile_panel_boards()

    fresh = VirtualBoardClient(device_type="panel", board_id="panel-board", grid_rows=12, grid_cols=29)
    assert fresh._last_characters is None


def test_an_install_without_panels_changes_nothing(services):
    settings, _panels, _pages = services
    before = settings.get_board_settings().boards

    assert reconcile_panel_boards() == 0
    assert settings.get_board_settings().boards == before


def test_a_failure_is_logged_not_raised(services, monkeypatch, caplog):
    import src.panels.reconcile as reconcile

    def boom():
        raise RuntimeError("settings unreadable")

    monkeypatch.setattr(reconcile, "_reconcile", boom)
    assert reconcile_panel_boards() == 0
    assert "Panel grid reconcile failed" in caplog.text


def test_startup_runs_the_reconcile(services):
    """Wired into the one-shot startup migrations, before the engine builds clients."""
    from src import api_server

    _legacy_panel(services)
    api_server._run_startup_migrations()

    assert _board(services, "panel-board")["device_type"] == "panel"
