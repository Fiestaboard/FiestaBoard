"""A slow pixel-art plugin puts an OLD piece back on a Pixoo (reproduction).

Live evidence (Divoom Pixoo 64, page "Pixoo 64 - Gen AI Art", 2026-10-29):
the board's layers went 3324e0 -> 2dd68e -> c2ef2c -> 2dd68e. 2dd68e is
byte-identical to the page canvas's STORED ``content`` rendered with no
plugin data -- a snapshot of an earlier piece saved on the page.

Two core defects combine:

1. ``PluginRegistry.build_template_context`` drops a plugin that misses
   ``CONTEXT_BUILD_TIMEOUT_SECONDS`` from the context entirely, even though
   ``PluginBase`` still holds that plugin's last good result for the very same
   board. ``resolve_canvas`` then reads the missing ``source`` as "failed" and
   draws the canvas's stored ``content`` -- the old snapshot -- instead of the
   piece the board was showing a moment ago.

2. ``DisplayService._render_fingerprint`` builds its context WITHOUT the
   board's display, so on a pixel board it hashes a different plugin result
   (the display-less cache entry, a separate AI generation) than the render
   draws. A new pixel piece landing in the display-aware cache does not move
   the fingerprint, the render short-circuit fires, and the board stays on
   whatever it last sent -- here, the old snapshot -- for minutes.
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import src.plugins.registry as registry_module
from src.canvas.layer import render_canvases_on_grid
from src.canvas.models import Canvas
from src.devices import board_context_for
from src.led.matrix import grid_layout
from src.main import BoardRuntime, DisplayService
from src.outputs.display_profile import DisplayProfile
from src.pages.models import Page
from src.plugins.base import PluginBase, PluginResult
from src.plugins.registry import PluginRegistry
from src.templates.engine import get_template_engine, reset_template_engine
from tests.test_render_short_circuit import (
    CountingPageService,
    MemoryPageStorage,
    RecordingClient,
    StubConfigManager,
)

PIXOO = DisplayProfile(
    technology="led_matrix",
    device_model="divoom_pixoo64",
    color="rgb",
    rows=8,
    cols=10,
    width=64,
    height=64,
    font="5x7",
)


def _piece(colour: str) -> dict:
    """A 64x64 one-colour content object, standing in for one AI piece."""
    return {"size": [64, 64], "background": colour}


STORED_SNAPSHOT = _piece("#0000ff")  # what the page saved, long ago
PIECE_A = _piece("#ff0000")  # the piece the board is showing now
PIECE_B = _piece("#00ff00")  # the next piece


def _canvas() -> Canvas:
    return Canvas.model_validate(
        {
            "id": "art",
            "area": {"row": 1, "col": 1, "rows": 8, "cols": 10},
            "bleed": ["all"],
            "scale": 1,
            "text": "hide",
            "source": "{{generative_ai_art.canvas}}",
            "content": STORED_SNAPSHOT,
        }
    )


def _layers(context: dict) -> list:
    layers, _ = render_canvases_on_grid([_canvas()], grid_layout(64, 64, "5x7"), context)
    return [layer.to_json() for layer in layers]


# --------------------------------------------------------------------------
# 1. A context-build timeout drops the plugin; the stored snapshot is drawn
# --------------------------------------------------------------------------


class SlowArtPlugin(PluginBase):
    """A real PluginBase (real per-board cache) whose fetch can be made slow."""

    def __init__(self):
        super().__init__(
            {"id": "generative_ai_art", "settings_schema": {"properties": {"refresh_seconds": {"default": 450}}}}
        )
        self.next_piece = PIECE_A
        self.gate = threading.Event()
        self.gate.set()

    @property
    def plugin_id(self) -> str:
        return "generative_ai_art"

    def fetch_data(self) -> PluginResult:
        self.gate.wait(timeout=10)
        return PluginResult(available=True, data={"canvas": dict(self.next_piece)})


@pytest.fixture
def registry(monkeypatch):
    registry_module.shutdown_plugin_fetch_executor()
    loader = MagicMock()
    loader.load_all_plugins.return_value = {}
    loader.load_errors = {}
    loader.get_manifest.return_value = None
    with patch("src.plugins.registry.PluginLoader", return_value=loader):
        reg = PluginRegistry(plugins_dir=Path("/fake/plugins"))
    monkeypatch.setattr(registry_module, "CONTEXT_BUILD_TIMEOUT_SECONDS", 0.2)
    yield reg
    registry_module.shutdown_plugin_fetch_executor()


def test_slow_refresh_keeps_last_piece_instead_of_the_stored_snapshot(registry):
    plugin = SlowArtPlugin()
    registry._plugins["generative_ai_art"] = plugin
    registry._enabled["generative_ai_art"] = True
    board = board_context_for("panel", grid_rows=8, grid_cols=10, display=PIXOO)

    # Tick 1: the fetch answers in time; the board shows piece A.
    first = registry.build_template_context(board, plugin_ids=["generative_ai_art"])
    assert _layers(first) == _layers({"generative_ai_art": {"canvas": PIECE_A}})

    # refresh_seconds later: the cache entry expires and the next AI call
    # takes longer than the context-build budget (20-60 s live vs 5 s).
    key = plugin._cache_key(board)
    plugin._last_fetch_times[key] -= timedelta(seconds=451)
    plugin.next_piece = PIECE_B
    plugin.gate.clear()
    try:
        second = registry.build_template_context(board, plugin_ids=["generative_ai_art"])
    finally:
        plugin.gate.set()

    shown = _layers(second)
    assert shown != _layers({}), (
        "the board was handed the page's STORED canvas snapshot (an old piece) because the slow "
        "plugin was dropped from the context, although its last result for this board was cached: "
        f"context={second!r}"
    )
    assert shown == _layers({"generative_ai_art": {"canvas": PIECE_A}})


# --------------------------------------------------------------------------
# 2. The render short-circuit hashes the display-less context
# --------------------------------------------------------------------------


class DisplayAwareRegistry:
    """Fetch-layer double that answers per display, as the art plugin does.

    The real plugin keys its cache on ``BoardContext.key`` (display
    included) and draws a pixel piece only when the board has a pixel
    display, so a display-less build is a different, independently
    refreshed result.
    """

    def __init__(self):
        self.trigger_plugins: dict = {}
        self.pixel = {"canvas": PIECE_A}
        self.display_less = {"canvas": STORED_SNAPSHOT, "art": "tile art"}
        self.boards: list = []

    @property
    def enabled_plugins(self) -> dict:
        return {"generative_ai_art": None}

    def build_template_context(self, board=None, plugin_ids=None, include_trigger_plugins=True, fingerprints=None):
        self.boards.append(board)
        data = self.pixel if getattr(board, "display", None) is not None else self.display_less
        if fingerprints is not None:
            fingerprints["generative_ai_art"] = PluginResult(available=True, data=data).data_fingerprint()
        return {"generative_ai_art": dict(data)}

    def get_manifest(self, _plugin_id):
        return None

    def get_plugin(self, _plugin_id):
        return None


@pytest.fixture
def pixel_rig(monkeypatch):
    reset_template_engine()
    page = Page(
        id="pixoo-page",
        name="Pixoo 64 - Gen AI Art",
        type="template",
        device_type="panel",
        grid_rows=8,
        grid_cols=10,
        template=[""] * 8,
        canvases=[_canvas()],
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    pages = CountingPageService(MemoryPageStorage([page]))
    reg = DisplayAwareRegistry()
    config = StubConfigManager()
    client = RecordingClient()
    board = {"id": "pixoo", "name": "Pixoo", "device_type": "panel", "grid_rows": 8, "grid_cols": 10, "enabled": True}
    settings = MagicMock()
    settings.get_board_settings.return_value = MagicMock(boards=[board])
    settings.get_primary_board_id.return_value = "pixoo"
    settings.is_paused.side_effect = lambda board_id=None: False
    settings.is_schedule_enabled.side_effect = lambda board_id=None: False
    settings.get_active_page_id.side_effect = lambda board_id=None: "pixoo-page"
    settings.get_transition_settings.return_value = MagicMock(strategy="instant", step_interval_ms=0, step_size=1)
    settings.should_send_to_board.return_value = True
    settings.consume_temporary_override.side_effect = lambda: None

    service = DisplayService()
    service.runtimes["pixoo"] = BoardRuntime(client=client, board_id="pixoo")
    service._primary_board_id = "pixoo"
    monkeypatch.setattr("src.main.get_settings_service", lambda: settings)
    monkeypatch.setattr("src.main.get_page_service", lambda: pages)
    monkeypatch.setattr("src.main.get_schedule_service", lambda: MagicMock())
    monkeypatch.setattr("src.main.get_collection_service", lambda: MagicMock())
    monkeypatch.setattr("src.config.get_config_manager", lambda: config)
    monkeypatch.setattr("src.config_manager.get_config_manager", lambda: config)
    monkeypatch.setattr("src.plugins.registry.get_plugin_registry", lambda: reg)
    monkeypatch.setattr("src.templates.engine.get_plugin_registry", lambda: reg)
    # The board's driver describes a Divoom Pixoo 64 (render_kw's display).
    monkeypatch.setattr("src.main._extended_kw", lambda _client: {"display": PIXOO})
    monkeypatch.setattr(service, "request_board_refresh", lambda *a, **k: None)
    monkeypatch.setattr(service, "_check_trigger_override", lambda: None)
    engine = get_template_engine()
    monkeypatch.setattr(engine, "_plugin_registry", reg)
    monkeypatch.setattr(engine, "_config_manager", config)

    def tick():
        service.check_and_send_active_page(wait=True)
        assert service.wait_until_idle(timeout=10.0)

    yield pages, reg, tick
    for rt in service.runtimes.values():
        if rt.send_worker is not None:
            rt.send_worker.stop()
    reset_template_engine()


def test_new_pixel_piece_is_rendered_even_when_display_less_data_is_unchanged(pixel_rig):
    pages, reg, tick = pixel_rig

    tick()
    assert pages.previews == 1

    # A new piece lands in the PIXEL cache entry; the display-less entry the
    # fingerprint reads is on its own refresh cycle and has not moved.
    reg.pixel = {"canvas": PIECE_B}
    tick()

    display_less = [b for b in reg.boards if getattr(b, "display", None) is None]
    assert pages.previews == 2, (
        "the render short-circuit kept the board on its previous frame after a new pixel piece "
        f"arrived: the fingerprint hashed a display-less context ({len(display_less)} display-less "
        f"build(s) of {len(reg.boards)}) instead of the one the render draws"
    )


# --------------------------------------------------------------------------
# 3. The breaker gate, and how stale "last result" may be
# --------------------------------------------------------------------------

REFRESH = 450
# The staleness bound for a 450 s refresh: max(2 x 450, 450 + 300) = 900 s.
WITHIN_BOUND = 600
PAST_BOUND = 1000


def _art_board_and_plugin(registry):
    plugin = SlowArtPlugin()
    registry._plugins["generative_ai_art"] = plugin
    registry._enabled["generative_ai_art"] = True
    board = board_context_for("panel", grid_rows=8, grid_cols=10, display=PIXOO)
    first = registry.build_template_context(board, plugin_ids=["generative_ai_art"])
    assert _layers(first) == _layers({"generative_ai_art": {"canvas": PIECE_A}})
    return plugin, board


def _age(plugin, board, seconds: int) -> None:
    plugin._last_fetch_times[plugin._cache_key(board)] = datetime.now() - timedelta(seconds=seconds)


def _quarantine(registry, board) -> None:
    board_key = (board.device_type, board.rows, board.cols, board.display.key)
    registry._fetch_breaker_until[("generative_ai_art", board_key)] = time.monotonic() + 60


def test_quarantined_plugin_keeps_its_recent_last_piece(registry):
    """A slow AI fetch runs up the breaker's timeout streak before it lands;
    while the breaker is open the board must keep its piece, not the snapshot."""
    plugin, board = _art_board_and_plugin(registry)
    _age(plugin, board, WITHIN_BOUND)
    _quarantine(registry, board)
    fingerprints: dict = {}

    context = registry.build_template_context(board, plugin_ids=["generative_ai_art"], fingerprints=fingerprints)

    assert _layers(context) == _layers({"generative_ai_art": {"canvas": PIECE_A}}), (
        f"the quarantined plugin was dropped, so the canvas drew its stored snapshot: context={context!r}"
    )
    assert "generative_ai_art" in fingerprints


def test_quarantined_plugin_past_the_staleness_bound_is_dropped(registry):
    plugin, board = _art_board_and_plugin(registry)
    _age(plugin, board, PAST_BOUND)
    _quarantine(registry, board)

    context = registry.build_template_context(board, plugin_ids=["generative_ai_art"])

    assert "generative_ai_art" not in context


def test_slow_plugin_past_the_staleness_bound_is_dropped(registry):
    """A wedged source must not hold time-sensitive data on the board forever."""
    plugin, board = _art_board_and_plugin(registry)
    _age(plugin, board, PAST_BOUND)
    plugin.gate.clear()
    try:
        context = registry.build_template_context(board, plugin_ids=["generative_ai_art"])
    finally:
        plugin.gate.set()

    assert "generative_ai_art" not in context, f"a {PAST_BOUND}s-old result was served: {context!r}"
