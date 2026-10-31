"""Transitions fall back to fade for flexible pages on pixel boards (plan Task 18).

A flexible page on a pixel board reaches the board as one opaque full-frame
layer over cells at the board's grid. A per-cell transition (flip, cascade)
would animate the cells under that picture, and a transition plugin steps
integer grids, so both run as ``fade`` instead (design section 6). On a
split-flap board a flexible page is an ordinary grid, so its transition is
unchanged.

Phase 0 already maps a strategy for a full frame
(:func:`src.outputs.transitions.strategy_for_full_frame`); these tests pin
that every send of a flexible page applies it, as a face page's send does.
The layout engine's expansion and plugin references are stood in for exactly
as in ``tests/layout/test_flexible_render.py``.
"""

# ruff: noqa: F811  (the tests take fixtures imported from other test modules)

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

import pytest

from src.pages.fit import PageFit, delivers_full_frame
from src.pages.models import Page
from src.pages.service import PageService, get_page_service
from src.pages.storage import PageStorage
from src.settings.service import get_settings_service, page_transition
from tests.layout.devices import profile
from tests.layout.test_engine import stub_expand  # noqa: F401
from tests.layout.test_flexible_render import CTX, FLAGSHIP_BOARD, PIXOO_BOARD, stub_refs  # noqa: F401
from tests.test_engine_page_face import Engine
from tests.test_led_text_size import pixoo_output  # noqa: F401
from tests.test_routes_page_face import ENDPOINTS, LEGACY_ENDPOINTS, _send
from tests.test_routes_page_face import board as pixoo_route_board  # noqa: F401
from tests.test_v1_contract import client  # noqa: F401

#: The display's own transition: plain, so a page's own strategy is what runs.
DISPLAY = SimpleNamespace(strategy=None, step_interval_ms=None, step_size=None)


def red_band(**fields: Any) -> Page:
    block = {"id": "s", "kind": "spacer", "style": {"height": 4, "background": "#ff0000"}}
    return Page.model_validate({"name": "Flex", "type": "flexible", "blocks": [block], **fields})


def stored(page: Page) -> Page:
    return get_page_service().storage.create(page)


# --- page_transition(full_frame=...) -------------------------------------------


@pytest.mark.parametrize("strategy", ["flip", "cascade", "plugin:typewriter"])
def test_a_full_frame_send_runs_a_per_cell_or_plugin_strategy_as_fade(strategy):
    page = red_band(transition_strategy=strategy)
    assert page_transition(DISPLAY, page, full_frame=True).strategy == "fade"


def test_a_full_frame_send_keeps_a_per_pixel_strategy():
    page = red_band(transition_strategy="slide")
    assert page_transition(DISPLAY, page, full_frame=True).strategy == "slide"


def test_a_full_frame_send_falls_back_from_the_displays_own_flip_too():
    display = SimpleNamespace(strategy="flip", step_interval_ms=None, step_size=None)
    assert page_transition(display, red_band(), full_frame=True).strategy == "fade"


def test_a_full_frame_send_maps_the_pages_plugin_to_fade_before_asking_the_board():
    # A board whose driver runs fade but not a page's transition plugin: the
    # page's plugin still arrives as fade, not as the display's own strategy.
    display = SimpleNamespace(strategy="none", step_interval_ms=None, step_size=None)
    page = red_band(transition_strategy="plugin:typewriter")
    runs = lambda strategy: not strategy.startswith("plugin:")  # noqa: E731
    assert page_transition(display, page, runs, full_frame=True).strategy == "fade"


def test_without_a_full_frame_the_strategy_is_unchanged():
    page = red_band(transition_strategy="plugin:typewriter")
    assert page_transition(DISPLAY, page).strategy == "plugin:typewriter"


# --- delivers_full_frame: which sends carry a full frame -----------------------


@pytest.fixture
def service(tmp_path) -> PageService:
    return PageService(PageStorage(str(tmp_path / "pages.json")))


def test_a_flexible_page_on_a_pixel_board_delivers_a_full_frame(service, stub_expand, stub_refs):
    page = red_band()
    result = service.render_page(page, context=CTX, display=profile("divoom_pixoo64", "3x5"), board=PIXOO_BOARD)
    assert delivers_full_frame(page, PageFit(True, None, None), result) is True


def test_a_flexible_page_on_a_flagship_delivers_no_full_frame(service, stub_expand, stub_refs):
    page = red_band()
    result = service.render_page(page, context=CTX, board=FLAGSHIP_BOARD)
    assert delivers_full_frame(page, PageFit(True, None, None), result) is False


def test_a_grid_page_drawn_at_another_face_delivers_a_full_frame():
    page = Page(name="G", type="template", template=["HI"])
    assert delivers_full_frame(page, PageFit(True, "5x7", None), SimpleNamespace(layers=[])) is True


def test_a_grid_page_at_the_boards_own_size_delivers_no_full_frame_even_with_canvas_layers():
    page = Page(name="G", type="template", template=["HI"])
    assert delivers_full_frame(page, PageFit(True, None, None), SimpleNamespace(layers=[object()])) is False


# --- the display engine (src/main.py) -------------------------------------------


@pytest.fixture
def engine(pixoo_output, monkeypatch, stub_expand, stub_refs):
    """The 8 x 10 Pixoo engine of ``tests/test_engine_page_face.py``, laying out flexible pages."""
    return Engine(monkeypatch)


def test_the_engine_sends_a_flexible_pages_transition_plugin_to_a_pixel_board_as_fade(engine):
    engine.tick(active=red_band(id="flex-1", transition_strategy="plugin:typewriter"))
    assert engine.client_render_kwargs["strategy"] == "fade"


def test_the_engine_sends_a_flexible_page_to_a_pixel_board_set_to_flip_as_fade(engine, monkeypatch):
    # The engine's test board takes no LED transitions, so a page's own flip
    # never runs there; the board's own flip is what reaches the send.
    flip = SimpleNamespace(strategy="flip", step_interval_ms=None, step_size=None)
    monkeypatch.setattr("tests.test_engine_page_face.TRANSITIONS", flip)
    engine.tick(active=red_band(id="flex-1"))
    assert engine.client_render_kwargs["strategy"] == "fade"


def test_a_flexible_silence_page_on_a_pixel_board_is_sent_with_a_fade(engine):
    engine.tick(silence_page=red_band(id="flex-silence", transition_strategy="plugin:typewriter"))
    assert engine.client_render_kwargs["strategy"] == "fade"


# --- sends over the API -----------------------------------------------------------


@pytest.mark.parametrize("endpoint", ENDPOINTS + LEGACY_ENDPOINTS)
def test_a_flip_into_a_flexible_page_on_a_pixel_board_by_any_route_runs_as_fade(
    client, pixoo_route_board, stub_expand, stub_refs, endpoint
):
    _, render = pixoo_route_board
    _send(client, endpoint, stored(red_band(transition_strategy="flip")).id, strategy="flip")
    assert render.call_args.kwargs["strategy"] == "fade"


def test_a_transition_plugin_asked_for_with_a_flexible_page_on_a_pixel_board_runs_as_fade(
    client, pixoo_route_board, stub_expand, stub_refs
):
    # The route board takes LED transitions, so only the message call's
    # explicit strategy (not a page's own) carries a plugin: strategy here.
    _, render = pixoo_route_board
    _send(client, "message", stored(red_band()).id, strategy="plugin:typewriter")
    assert render.call_args.kwargs["strategy"] == "fade"


@pytest.mark.parametrize("endpoint", ["active-page", "pages-send", *LEGACY_ENDPOINTS])
def test_a_flexible_pages_own_transition_plugin_on_a_pixel_board_runs_as_fade(
    client, pixoo_route_board, stub_expand, stub_refs, endpoint
):
    _, render = pixoo_route_board
    _send(client, endpoint, stored(red_band(transition_strategy="plugin:typewriter")).id)
    assert render.call_args.kwargs["strategy"] == "fade"


@pytest.fixture
def flagship_route_board(client):
    """A Flagship as the only board, its client a mock that runs every split-flap strategy."""
    get_settings_service().set_boards([FLAGSHIP_BOARD])
    driver = Mock(spec=["render"])
    driver.render.return_value = (True, True)
    service = Mock(vb_client=driver)
    service.get_board_client.return_value = driver
    with (
        patch("src.api_server.get_service", return_value=service),
        patch("src.display_runtime.get_service", return_value=service),
        patch("src.pages.routes.get_service", return_value=service),
        patch("src.pages.routes.driver_runs_strategy", return_value=True),
        patch("src.settings.routes.driver_runs_strategy", return_value=True),
    ):
        yield driver.render


@pytest.mark.parametrize("strategy", ["flip", "plugin:typewriter"])
def test_a_flexible_page_sent_to_a_flagship_keeps_its_transition(
    client, flagship_route_board, stub_expand, stub_refs, strategy
):
    page_id = stored(red_band(transition_strategy=strategy)).id
    response = client.post(f"/pages/{page_id}/send", params={"board_id": FLAGSHIP_BOARD["id"], "target": "board"})
    assert response.status_code == 200, response.text
    assert flagship_route_board.call_args.kwargs["strategy"] == strategy
