"""The render short-circuit and dedupe cover flexible pages (plan Task 15, spec section 6).

The fingerprint is still "the page document + the referenced plugin data +
config + display key"; a flexible page's size is its board's (it has no grid
of its own), and the content key digests the frame.

The plan's end-to-end clock tests run the real expansion and fit. The same
behaviours are also pinned against stand-ins: ``flexible_plugin_ids`` as in
``tests/layout/test_flexible_render.py``, and an expansion that fills
``{{clock.time}}`` from the context, so the same page renders differently
for different plugin data.
"""

# ruff: noqa: F811  (the tests take fixtures imported from other test modules)

from __future__ import annotations

from dataclasses import replace
from typing import Any
from unittest.mock import patch

import pytest

from src.devices import size_key
from src.layout import engine as engine_module
from src.main import DisplayService
from src.pages.models import Page
from src.pages.service import PageService
from tests.layout.devices import SAMPLE, profile
from tests.layout.test_engine import StubExpanded
from tests.layout.test_flexible_render import stub_refs  # noqa: F401
from tests.test_engine_page_face import BOARD as PIXOO_8X10
from tests.test_engine_page_face import Engine
from tests.test_led_text_size import pixoo_output  # noqa: F401

PIXOO_BOARD = {
    "id": "pixoo",
    "name": "Pixoo",
    "device_type": "panel",
    "grid_rows": 10,
    "grid_cols": 16,
    "device_model": "divoom_pixoo64",
}
FLAGSHIP_BOARD = {"id": "flag", "name": "Flagship", "device_type": "flagship"}
PIX = profile("divoom_pixoo64", "3x5")

#: A clock: its text is the clock plugin's time.
FLEX_CLOCK = Page.model_validate(
    {
        "id": "clock-page",
        "name": "Clock",
        "type": "flexible",
        "blocks": [{"id": "t", "kind": "text", "text": "{{clock.time}}"}],
    }
)
#: A band coloured by plugin data: on a pixel board it changes the frame and nothing else.
FLEX_BAND = Page.model_validate(
    {
        "id": "band-page",
        "name": "Band",
        "type": "flexible",
        "blocks": [{"id": "s", "kind": "spacer", "style": {"height": 4, "background": "{{clock.color}}"}}],
    }
)
FLEX_PAGE = FLEX_BAND


def clock(time: str = "12:45", color: str = "#ff0000") -> dict[str, Any]:
    return {"clock": {"time": time, "color": color}}


@pytest.fixture
def clock_expand(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the engine's ``expand_blocks`` with one that fills ``{{clock.time}}``."""

    def expand_blocks(page, target, context, styles, *, engine=None):
        shown = []
        for index, block in enumerate(page.blocks or []):
            markup = (block.text or "").replace("{{clock.time}}", str(context.get("clock", {}).get("time", "")))
            shown.append(StubExpanded(block.id, block.kind, index, block.priority, block, markup))
        return shown, []

    monkeypatch.setattr(engine_module, "expand_blocks", expand_blocks)


@pytest.fixture
def config() -> None:
    """The config store and plugin registry, set up before the first fingerprint.

    The registry's first access migrates and saves the config, which is a
    config change; a real display loop has done that long before any tick.
    """
    from src.plugins.registry import get_plugin_registry

    get_plugin_registry()


def contexts_for(board: dict, display: Any, context: dict) -> dict:
    """A per-pass cache already holding *context* for *board* on *display*."""
    key = size_key(board["device_type"], 1, 1, board.get("grid_rows"), board.get("grid_cols"))
    return {f"{key}|{display.key}" if display is not None else key: context}


def fp(page: Page = FLEX_PAGE, *, display: Any = PIX, board: dict = PIXOO_BOARD, context: dict | None = None):
    contexts = contexts_for(board, display, context if context is not None else clock())
    return DisplayService._render_fingerprint(
        page, page.id, PageService(), contexts, override_active=False, display=display, board=board
    )


def render(page: Page, time: str = "12:45", *, color: str = "#ff0000", board: dict = PIXOO_BOARD, display: Any = PIX):
    result = PageService().render_page(page, context=clock(time, color), display=display, board=board)
    assert result.available, result.error
    return result


# --- the fingerprint ------------------------------------------------------------


def test_flexible_page_gets_a_fingerprint(stub_refs, config):
    assert DisplayService._render_fingerprint(
        FLEX_PAGE,
        "p",
        PageService(),
        contexts_for(PIXOO_BOARD, PIX, clock()),
        override_active=False,
        display=PIX,
        board=PIXOO_BOARD,
    )


def test_flexible_page_without_blocks_gets_no_fingerprint(stub_refs, config):
    empty = Page.model_validate({"name": "Empty", "type": "flexible", "blocks": []})
    assert fp(empty) is None


def test_identical_inputs_identical_fingerprint(stub_refs, config):  # [RF-5]
    first = fp()
    assert first is not None and first == fp()


def test_plugin_data_change_changes_fingerprint(stub_refs, config):  # [RF-5]
    assert fp(FLEX_CLOCK, context=clock("12:45")) != fp(FLEX_CLOCK, context=clock("12:46"))


def test_fingerprint_differs_by_display_key_at_same_grid(stub_refs, config):  # [RF-5]
    f1 = fp(display=profile("divoom_pixoo64", font="3x5"))
    f2 = fp(display=replace(profile("divoom_pixoo64", font="3x5"), color="mono"))
    assert f1 is not None and f1 != f2


def test_fingerprint_differs_by_board_grid(stub_refs, config):
    other = {**PIXOO_BOARD, "grid_rows": 8, "grid_cols": 10}
    assert fp(board=PIXOO_BOARD, display=None) != fp(board=other, display=None)


# --- the content key --------------------------------------------------------------


def test_identical_clock_inputs_identical_content_key_end_to_end(stub_refs):  # [RF-5]
    page = Page.model_validate(SAMPLE)
    a, b = render(page, "12:45"), render(page, "12:45")
    assert a.content_key() == b.content_key()


def test_minute_change_changes_content_key_end_to_end(stub_refs):  # [RF-5]
    page = Page.model_validate(SAMPLE)
    assert render(page, "12:45").content_key() != render(page, "12:46").content_key()


def test_identical_inputs_identical_content_key(clock_expand, stub_refs):  # [RF-5]
    a, b = render(FLEX_BAND, "12:45"), render(FLEX_BAND, "12:45")
    assert a.layers and a.content_key() == b.content_key()


def test_minute_change_changes_content_key(clock_expand, stub_refs):  # [RF-5]
    a = render(FLEX_CLOCK, "12:45", board=FLAGSHIP_BOARD, display=None)
    b = render(FLEX_CLOCK, "12:46", board=FLAGSHIP_BOARD, display=None)
    assert a.content_key() != b.content_key()


def test_frame_only_change_changes_content_key(clock_expand, stub_refs):
    a, b = render(FLEX_BAND, color="#ff0000"), render(FLEX_BAND, color="#00ff00")
    assert a.formatted == b.formatted and a.content_key() != b.content_key()


# --- the short-circuit ------------------------------------------------------------


@pytest.fixture
def engine_harness_pixoo(pixoo_output, monkeypatch, clock_expand, stub_refs):
    """The 8 x 10 Pixoo engine of ``tests/test_engine_page_face.py``, laying out flexible pages."""
    return Engine(monkeypatch)


def test_unchanged_tick_short_circuits_for_flexible_page(engine_harness_pixoo):
    engine_harness_pixoo.tick(active=FLEX_BAND)
    engine_harness_pixoo.tick(active=FLEX_BAND)
    assert engine_harness_pixoo.renders == 1


def test_engine_fingerprints_a_flexible_page_for_the_board_it_sends_to(engine_harness_pixoo):
    with patch.object(DisplayService, "_render_fingerprint", wraps=DisplayService._render_fingerprint) as spy:
        engine_harness_pixoo.tick(active=FLEX_BAND)
    assert spy.call_args.kwargs["board"]["id"] == PIXOO_8X10["id"]


def test_edited_flexible_page_renders_again(engine_harness_pixoo):
    engine_harness_pixoo.tick(active=FLEX_BAND)
    edited = FLEX_BAND.model_copy(update={"name": "Band, renamed"})
    engine_harness_pixoo.tick(active=edited)
    assert engine_harness_pixoo.renders == 2
