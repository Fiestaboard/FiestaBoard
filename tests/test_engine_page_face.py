"""The display engine shows grid pages on LED boards at their own text size.

An 8 x 10 Pixoo 64 (the 5x7 face) can also produce 10 x 16 (the 3x5 face), so
a 10 x 16 page shows on it: drawn in small text as one opaque full-frame layer
over cells that carry the page text at the board's own 8 x 10 grid (design
section 7). A page the board can't produce at any size is skipped, and the
log says why in the user-facing words. A face page's transition plugin runs
as a fade, because transition plugins step integer grids (design section 6).

The real ``check_and_send_for_board`` runs here, over a real ``PageService``
and an ``OutputPluginDriver`` wrapping a recording LED plugin bound to the 5x7
Pixoo model; only settings, the config store and the clock are stubbed (the
``tests/test_silence_board_layer.py`` harness).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.led.charsets import BUILTIN_CHARACTER_SETS
from src.led.matrix import model_with_led_font
from src.led.page_frame import is_full_frame_layer
from src.main import BoardRuntime, DisplayService
from src.outputs.plugin_base import OutputPluginBase
from src.outputs.plugin_driver import OutputPluginDriver
from src.outputs.registry import OutputCapabilities
from src.pages.models import Page
from src.pages.service import PageService
from src.pages.storage import PageStorage
from src.send_outcome import WriteResult
from tests.fake_clock import FakeClock, install_fake_time_service
from tests.test_led_text_size import PIXOO, _board, pixoo_output  # noqa: F401

LED_5X7 = BUILTIN_CHARACTER_SETS["led_5x7"]
PIXOO_5X7 = model_with_led_font(PIXOO, "5x7")
BOARD = _board(grid_rows=8, grid_cols=10, output_config={"host": "192.0.2.50", "font": "5x7"})
#: The board's own transition: none chosen, so a page's own strategy is what runs.
TRANSITIONS = SimpleNamespace(strategy=None, step_interval_ms=None, step_size=None)

DAYTIME = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
NIGHT = datetime(2026, 7, 15, 23, 30, tzinfo=UTC)


class Sign(OutputPluginBase):
    """An LED output plugin, bound to the 5x7 Pixoo, that records the cells it is sent."""

    plugin_id = "sign"

    def __init__(self):
        super().__init__("sign", {})
        self.sent: list = []
        self.bind_board(device_model=PIXOO_5X7, character_set=LED_5X7, geometry=(8, 10))

    def capabilities(self):
        return OutputCapabilities(
            technology="led_matrix", delivery="push", animation="stream", native_transitions=frozenset()
        )

    def device_key(self):
        return f"sign:{id(self):x}"

    def write(self, frame, *, native, cancel):
        self.sent.append(frame.cells)
        return WriteResult(True, True)

    def write_cells(self, cells, *, native, cancel):
        self.sent.append(cells)
        return WriteResult(True, True)

    @property
    def last_cells(self):
        return self.sent[-1]


class _MemoryStorage(PageStorage):
    def __init__(self, pages):
        self._pages = {p.id: p for p in pages}

    def get(self, page_id):
        return self._pages.get(page_id)

    def list_all(self):
        return list(self._pages.values())


class _ConfigManager:
    """The config store: a generation counter (the render short-circuit),
    silence, and no plugins configured."""

    version_changed_on_load = False

    def __init__(self, silence: dict):
        self.config_generation = 1
        self.silence = silence

    def get_feature(self, name: str) -> dict:
        return dict(self.silence) if name == "silence_schedule" else {}

    def get_general(self) -> dict:
        return {}

    def get_all_plugin_configs(self, include_env_overrides: bool = True) -> dict:
        return {}

    def is_v2_plugin_migration_done(self) -> bool:
        return True

    def get_v2_plugin_failed_installs(self) -> list:
        return []

    def get_board(self) -> dict:
        return {}

    def migrate_silence_schedule_to_utc(self) -> bool:
        return False

    def migrate_silence_schedule_to_per_board(self) -> int:
        return 0


def _silence(page_id: str | None) -> dict:
    """Quiet hours 22:00-07:00 UTC showing *page_id*, or off when it is None."""
    return {
        "enabled": page_id is not None,
        "start_time": "22:00+00:00",
        "end_time": "07:00+00:00",
        "mode": "page",
        "page_id": page_id,
        "indicator_text": "SNOOZING",
        "indicator_position": "center",
        "by_board": {},
    }


def _page(rows: int, cols: int, text: str = "HELLO", *, device_type: str = "panel", **extra) -> Page:
    page_id = f"page-{device_type}-{rows}x{cols}"
    if device_type == "panel":
        return Page(
            id=page_id,
            name=page_id,
            type="template",
            template=[text],
            device_type=device_type,
            grid_rows=rows,
            grid_cols=cols,
            **extra,
        )
    return Page(id=page_id, name=page_id, type="template", template=[text], device_type=device_type, **extra)


class Engine:
    """One display engine driving the 8 x 10 Pixoo, a tick at a time."""

    def __init__(self, monkeypatch):
        self.monkeypatch = monkeypatch
        self.plugin = Sign()
        self.client = OutputPluginDriver(self.plugin, character_set=LED_5X7)
        self.render_calls: list[dict] = []
        original = self.client.render

        def _render(board_array, **kwargs):
            self.render_calls.append(kwargs)
            return original(board_array, **kwargs)

        self.client.render = _render
        self.service = DisplayService()
        self.service.runtimes = {BOARD["id"]: BoardRuntime(client=self.client, board_id=BOARD["id"])}
        self.service._primary_board_id = BOARD["id"]
        self.clock = FakeClock(DAYTIME)
        install_fake_time_service(monkeypatch, self.clock)
        self.renders = 0

    @property
    def client_render_kwargs(self) -> dict:
        return self.render_calls[-1]

    def tick(self, *, active: Page | None = None, silence_page: Page | None = None) -> bool:
        pages = [p for p in (active, silence_page) if p is not None]
        page_service = PageService(storage=_MemoryStorage(pages))
        preview = page_service.preview_page

        def _counted_preview(*args, **kwargs):
            self.renders += 1
            return preview(*args, **kwargs)

        page_service.preview_page = _counted_preview

        settings = MagicMock()
        settings.get_board_settings.return_value = SimpleNamespace(boards=[BOARD])
        settings.get_primary_board_id.return_value = BOARD["id"]
        settings.is_paused.return_value = False
        settings.is_schedule_enabled.return_value = False
        settings.get_active_page_id.return_value = active.id if active is not None else pages[0].id
        settings.get_transition_settings.return_value = TRANSITIONS
        settings.consume_temporary_override.return_value = None

        config = _ConfigManager(_silence(silence_page.id if silence_page is not None else None))
        self.monkeypatch.setattr("src.config.get_config_manager", lambda: config)
        self.monkeypatch.setattr("src.config_manager.get_config_manager", lambda: config)
        self.clock.set(NIGHT if silence_page is not None else DAYTIME)
        with (
            patch("src.main.get_settings_service", return_value=settings),
            patch("src.main.get_page_service", return_value=page_service),
            patch("src.main.get_schedule_service", return_value=MagicMock()),
            patch("src.main.get_collection_service", return_value=MagicMock()),
            patch.object(self.service, "_check_trigger_override", return_value=None),
            patch.object(self.service, "request_board_refresh"),
        ):
            return self.service.check_and_send_active_page()


@pytest.fixture
def engine(pixoo_output, monkeypatch):  # noqa: F811
    return Engine(monkeypatch)


def test_a_10x16_page_reaches_an_8x10_pixoo_as_cells_plus_one_full_frame(engine):
    engine.tick(active=_page(10, 16))
    cells = engine.plugin.last_cells
    assert (len(cells), len(cells[0])) == (8, 10)
    assert len(cells.layers) == 1 and is_full_frame_layer(cells.layers[0], 64, 64)


def test_the_cells_under_the_frame_carry_the_page_text(engine):
    engine.tick(active=_page(10, 16, "HELLO"))
    assert "".join(t.value or "" for t in engine.plugin.last_cells[0]).startswith("HELLO")


def test_a_page_at_the_boards_own_size_is_sent_as_cells_only(engine):
    engine.tick(active=_page(8, 10))
    assert engine.plugin.last_cells.layers == ()


def test_a_flagship_page_is_skipped_with_its_reason_logged(engine, caplog):
    with caplog.at_level(logging.WARNING, logger="src.main"):
        assert engine.tick(active=_page(6, 22, device_type="flagship")) is False
    assert "Made for a 6×22 board" in caplog.text


def test_an_unchanged_face_page_is_not_rendered_twice(engine):
    page = _page(10, 16)
    engine.tick(active=page)
    engine.tick(active=page)
    assert engine.renders == 1


def test_a_silence_page_at_the_other_size_is_shown_not_replaced_by_the_indicator(engine):
    engine.tick(silence_page=_page(10, 16, "SLEEP"))
    assert len(engine.plugin.last_cells.layers) == 1


# [RF5]
def test_a_face_pages_own_transition_plugin_runs_as_fade(engine):
    engine.tick(active=_page(10, 16, transition_strategy="plugin:typewriter"))
    assert engine.client_render_kwargs["strategy"] == "fade"
