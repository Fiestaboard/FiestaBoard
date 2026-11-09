"""H6: preview a template with sample data, missing data, another time, or cached data.

The 2.10 editor's Live · Sample · Missing switch (04c A7, G4) asks the hub
"what would this board show if rain_chance were 70 / weather were down / it
were 7:00 AM", and the 200 ms keystroke preview must not wait on a refetch.
``POST /templates/render`` takes one ``preview`` object; pinned here:

- precedence: the hub's data, then ``missing`` removes, then ``values`` sets;
- missing renders ``???`` for a variable and ``#REF`` for a formula, so
  ``DEFAULT`` fallbacks show; an empty sample is blank;
- ``at`` is the render's pinned clock (``NOW()``, H5 formula values);
- ``data: cached`` serves any earlier result without fetching;
- ``sources`` labels the hub's own data fresh / stale / live / none;
- nothing leaks: the plugin cache is unchanged, the next real render shows
  real data, ``/render/live`` refuses a preview (it writes the board);
- every bound is a 422 before any render.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import src.plugins.registry as registry_module
from src.plugins.base import PluginBase, PluginResult
from src.plugins.registry import PluginRegistry
from src.templates.diagnostics import RenderReport
from src.templates.engine import TemplateEngine
from src.templates.preview import Preview


class Weather(PluginBase):
    """A real cached plugin (refresh 300 s) that counts its fetches."""

    def __init__(self):
        super().__init__({"id": "weather", "settings_schema": {"properties": {"refresh_seconds": {"default": 300}}}})
        self.fetches = 0
        self.temperature = 64

    @property
    def plugin_id(self) -> str:
        return "weather"

    def fetch_data(self) -> PluginResult:
        self.fetches += 1
        return PluginResult(
            available=True,
            data={"temperature": self.temperature, "condition": "CLEAR", "rain_chance": 10, "events": [1, 2]},
        )


class Clock(PluginBase):
    """A ``live_data`` plugin: computed on every render, never cached."""

    def __init__(self):
        super().__init__({"id": "clock", "live_data": True})
        self.fetches = 0

    @property
    def plugin_id(self) -> str:
        return "clock"

    def fetch_data(self) -> PluginResult:
        self.fetches += 1
        return PluginResult(available=True, data={"time": "9:41"})


@pytest.fixture
def registry():
    registry_module.shutdown_plugin_fetch_executor()
    loader = MagicMock()
    loader.load_all_plugins.return_value = {}
    loader.load_errors = {}
    loader.get_manifest.return_value = None
    with patch("src.plugins.registry.PluginLoader", return_value=loader):
        reg = PluginRegistry(plugins_dir=Path("/fake/plugins"))
    for plugin in (Weather(), Clock()):
        reg._plugins[plugin.plugin_id] = plugin
        reg._enabled[plugin.plugin_id] = True
    yield reg
    registry_module.shutdown_plugin_fetch_executor()


@pytest.fixture
def engine(registry):
    engine = TemplateEngine.__new__(TemplateEngine)
    engine._display_service = None
    config = MagicMock()
    config.get_effective_color_rules.return_value = []
    engine._config_manager = config
    engine._plugin_registry = registry
    return engine


def _weather(registry) -> Weather:
    return registry._plugins["weather"]


def _age(plugin: PluginBase, seconds: int) -> None:
    for key in list(plugin._last_fetch_times):
        plugin._last_fetch_times[key] = datetime.now() - timedelta(seconds=seconds)


def _rows(engine, lines, preview=None, **kw) -> list[str]:
    return [row.strip() for row in engine.render_lines(lines, preview=preview, **kw).split("\n")]


# ── sample values and missing data ──────────────────────────────────────────


def test_a_sample_value_replaces_the_live_one(engine):
    assert _rows(engine, ["{{weather.rain_chance}}"])[0] == "10"
    assert _rows(engine, ["{{weather.rain_chance}}"], Preview(values={"weather.rain_chance": 70}))[0] == "70"


def test_a_one_segment_value_replaces_the_whole_plugin(engine):
    preview = Preview(values={"weather": {"temperature": 99}})
    rows = _rows(engine, ["{{weather.temperature}}", "{{weather.condition}}"], preview)

    assert rows[:2] == ["99", "???"]


def test_a_list_sample_drives_count(engine):
    lines = ["{{= COUNT(weather.events) }}"]
    assert _rows(engine, lines, Preview(values={"weather.events": []}))[0] == "0"
    assert _rows(engine, lines, Preview(values={"weather.events": [1, 2, 3]}))[0] == "3"


def test_a_missing_plugin_shows_unavailable_and_ref(engine):
    lines = ["{{weather.temperature}}", "{{= weather.temperature + 1 }}", '{{= DEFAULT(weather.temperature, "--") }}']
    rows = _rows(engine, lines, Preview(missing=["weather"]))

    assert rows[:3] == ["???", "#REF", "--"]


def test_a_missing_field_leaves_the_rest_of_the_plugin(engine):
    rows = _rows(engine, ["{{weather.condition}}", "{{weather.temperature}}"], Preview(missing=["weather.condition"]))

    assert rows[:2] == ["???", "64"]


def test_an_empty_sample_is_blank_and_falls_back(engine):
    lines = ["[{{weather.condition}}]", '{{= DEFAULT(weather.condition, "NONE") }}']
    rows = _rows(engine, lines, Preview(values={"weather.condition": ""}))

    assert rows[:2] == ["[]", "NONE"]


def test_a_value_under_a_missing_root_is_the_only_data_left(engine):
    preview = Preview(missing=["weather"], values={"weather.temperature": 70})
    rows = _rows(engine, ["{{weather.temperature}}", "{{weather.condition}}"], preview)

    assert rows[:2] == ["70", "???"]


# ── render at a time ────────────────────────────────────────────────────────


def test_at_is_the_renders_clock_and_the_formula_report_agrees(engine):
    at = datetime(2026, 11, 9, 7, 0, 0)
    report = RenderReport()
    rows = engine.render_lines(['{{= FORMATDATE(NOW(), "HH:mm") }}'], preview=Preview(at=at), report=report)

    assert rows.split("\n")[0].strip() == "07:00"
    assert report.formulas[0].value == "07:00"


# ── nothing leaks ───────────────────────────────────────────────────────────


def test_a_sampled_render_leaves_the_plugin_cache_untouched(engine, registry):
    _rows(engine, ["{{weather.temperature}}"])
    cached = [dict(result.data) for result in _weather(registry)._cached_results.values()]

    _rows(
        engine, ["{{weather.temperature}}"], Preview(values={"weather.temperature": 1}, missing=["weather.condition"])
    )

    assert [dict(result.data) for result in _weather(registry)._cached_results.values()] == cached


def test_the_next_real_render_shows_real_data(engine):
    _rows(engine, ["{{weather.temperature}}"], Preview(values={"weather.temperature": 1}))

    assert _rows(engine, ["{{weather.temperature}} {{weather.condition}}"])[0] == "64 CLEAR"


# ── cached data ─────────────────────────────────────────────────────────────


def test_cached_mode_serves_a_stale_result_without_fetching(engine, registry):
    _rows(engine, ["{{weather.temperature}}"])
    weather = _weather(registry)
    _age(weather, 3600)
    weather.temperature = 80

    rows = _rows(engine, ["{{weather.temperature}}"], Preview(data="cached"))

    assert rows[0] == "64"
    assert weather.fetches == 1


def test_live_mode_refetches_the_stale_result(engine, registry):
    _rows(engine, ["{{weather.temperature}}"])
    weather = _weather(registry)
    _age(weather, 3600)
    weather.temperature = 80

    assert _rows(engine, ["{{weather.temperature}}"], Preview())[0] == "80"
    assert weather.fetches == 2


def test_cached_mode_fetches_a_plugin_with_no_result_yet(engine, registry):
    rows = _rows(engine, ["{{weather.temperature}} {{clock.time}}"], Preview(data="cached"))

    assert rows[0] == "64 9:41"
    assert _weather(registry).fetches == 1


# ── sources: what the hub's own data is ─────────────────────────────────────


def test_sources_label_fresh_stale_live_and_none(engine, registry):
    _rows(engine, ["{{weather.temperature}}"])
    preview = Preview(data="cached", missing=["muni"])
    _rows(engine, ["{{weather.temperature}} {{clock.time}} {{muni.eta}}"], preview)
    fresh = preview.sources["weather"]
    assert fresh["state"] == "fresh" and fresh["updated_at"].endswith("+00:00")
    assert preview.sources["clock"] == {"state": "live", "updated_at": None}
    assert preview.sources["muni"] == {"state": "none", "updated_at": None}

    _age(_weather(registry), 3600)
    stale = Preview(data="cached")
    _rows(engine, ["{{weather.temperature}}"], stale)
    assert stale.sources["weather"]["state"] == "stale"


# ── the routes ──────────────────────────────────────────────────────────────


@pytest.fixture
def client(_isolated_data_dir, engine, monkeypatch):
    from src.api_server import app

    monkeypatch.setattr("src.templates.routes.get_template_engine", lambda: engine)
    return TestClient(app)


def test_render_without_a_preview_is_unchanged(client):
    body = client.post("/templates/render", json={"template": ["{{weather.temperature}}"]}).json()

    assert set(body) == {"rendered", "lines", "line_count"}
    assert body["lines"][0].strip() == "64"


def test_render_with_a_preview_answers_the_sample_and_its_sources(client):
    request = {"template": ["{{weather.rain_chance}}"], "preview": {"values": {"weather.rain_chance": 70}}}
    response = client.post("/templates/render", json=request)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["lines"][0].strip() == "70"
    assert body["sources"]["weather"]["state"] == "fresh"


def test_a_string_template_takes_a_preview_too(client):
    request = {"template": "T {{weather.temperature}}", "preview": {"values": {"weather.temperature": 5}}}

    assert client.post("/templates/render", json=request).json()["rendered"] == "T 5"


def test_live_refuses_a_preview_and_sends_nothing(client):
    with patch("src.templates.routes.run_board_preview") as send:
        response = client.post(
            "/templates/render/live",
            json={"template": ["HI"], "preview": {"values": {"weather.temperature": 1}}},
        )

    assert response.status_code == 422
    assert "never sent to a board" in response.text
    send.assert_not_called()


def test_a_page_with_canvases_refuses_a_preview(client):
    canvas = {"id": "sun", "area": {"row": 1, "col": 1, "rows": 1, "cols": 2}, "content": {"background": "#ff0000"}}
    request = {
        "template": ["HELLO"],
        "device_type": "panel",
        "grid_rows": 10,
        "grid_cols": 16,
        "canvases": [canvas],
        "preview": {"missing": ["weather"]},
    }

    assert client.post("/templates/render", json=request).status_code == 422


# ── bounds ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "preview",
    [
        {"values": {f"weather.f{n}": n for n in range(65)}},
        {"missing": [f"p{n}" for n in range(65)]},
        {"values": {"weather.condition": "A" * 70_000}},
        {"values": {"weather." + ".".join(["a"] * 8): 1}},
        {"values": {"weather." + "a" * 130: 1}},
        {"values": {"__now__": "2001-01-01"}},
        {"missing": ["__locals__"]},
        {"values": {"weather..temperature": 1}},
        {"values": {"weather.temperature": {"a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": 1}}}}}}}}}},
        {"at": (datetime.now() + timedelta(days=365 * 20)).isoformat()},
        {"data": "yesterday"},
    ],
    ids=[
        "too-many-values",
        "too-many-missing",
        "value-too-large",
        "path-too-deep",
        "path-too-long",
        "reserved-clock",
        "reserved-locals",
        "bad-path",
        "value-too-nested",
        "at-too-far",
        "unknown-data-mode",
    ],
)
def test_an_out_of_bounds_preview_is_rejected(client, preview):
    response = client.post("/templates/render", json={"template": ["HI"], "preview": preview})

    assert response.status_code == 422, response.text


# ── at: the hub's timezone ──────────────────────────────────────────────────


@pytest.fixture
def tokyo_hub(monkeypatch):
    from src.time_service import TimeService

    hub = TimeService("Asia/Tokyo")
    monkeypatch.setattr("src.time_service.get_time_service", lambda: hub)


@pytest.mark.parametrize(
    ("at", "shown"),
    [("2026-11-09T00:00:00+00:00", "09:00"), ("2026-11-09T07:00:00", "07:00")],
    ids=["offset-converted-to-the-hub", "naive-is-the-hubs-time"],
)
def test_at_is_read_in_the_hubs_timezone(client, tokyo_hub, at, shown):
    request = {"template": ['{{= FORMATDATE(NOW(), "HH:mm") }}'], "preview": {"at": at}}

    assert client.post("/templates/render", json=request).json()["lines"][0].strip() == shown


# ── a preview keeps the render's work budget (S2 review T1) ─────────────────


def test_a_preview_at_another_time_keeps_the_render_budget(engine, monkeypatch):
    from src.templates import expressions

    monkeypatch.setattr(expressions, "_eval_clock", lambda: 0.0)  # the step budget, not the deadline

    heavy = '{{= COUNT(FILTER(SPLIT(REPT(REPT("a,",1024),32), ","), LEN(item) = 1 AND item = "a")) }}'
    preview = Preview(at=datetime(2026, 11, 9, 7, 0, 0))

    rows = _rows(engine, [heavy] * 96, preview, device_type="panel", grid_rows=96, grid_cols=128)

    assert rows[0] == "32768"
    assert rows[-1] == "#VALUE"
    assert expressions.MAX_RENDER_STEPS < 96 * 262_158
