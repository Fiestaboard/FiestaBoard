"""Color rules saved per plugin instance, end to end (#2088).

These use a real ConfigManager backed by a config file, so a rule saved the
way the Dynamic Colors editor saves it (``plugins.<id>.color_rules``) is
followed all the way to rendered output and line-length validation.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.config_manager import ConfigManager
from src.templates.engine import TemplateEngine

BLACK_AFTER_8PM = {"condition": ">=", "value": 20, "color": "black"}


def _engine(tmp_path, plugins: dict, features: dict | None = None) -> TemplateEngine:
    config = {"plugins": plugins}
    if features is not None:
        config["features"] = features
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    cm = ConfigManager(config_path=str(path))
    # A stub registry with no manifests: the real one would try to install
    # plugins named in the config from GitHub.
    registry = MagicMock()
    registry.get_manifest.return_value = None
    registry._manifests = {}
    with patch("src.templates.engine.get_plugin_registry", return_value=registry):
        engine = TemplateEngine()
    engine._config_manager = cm
    return engine


def test_saved_rule_colors_the_color_variable(tmp_path):
    engine = _engine(tmp_path, {"clock": {"enabled": True, "color_rules": {"hour": [BLACK_AFTER_8PM]}}})
    assert engine.render("{{clock.hour_color}}", {"clock": {"hour": 21}}) == "{70}"


def test_saved_rule_prefixes_the_plain_field(tmp_path):
    # The editor promises "→ color based on value" for the field itself, and
    # offers {{plugin.field_color}} for just the tile, so the plain field is
    # prefixed exactly as manifest default_rules already prefix it.
    engine = _engine(tmp_path, {"clock": {"enabled": True, "color_rules": {"hour": [BLACK_AFTER_8PM]}}})
    assert engine.render("{{clock.hour}}", {"clock": {"hour": 21}}) == "{70} 21"
    assert engine.render("{{clock.hour}}", {"clock": {"hour": 9}}) == "9"


def test_saved_rule_on_named_instance(tmp_path):
    engine = _engine(
        tmp_path,
        {"clock:pacific": {"enabled": True, "color_rules": {"hour": [BLACK_AFTER_8PM]}}, "clock": {"enabled": True}},
    )
    ctx = {"clock:pacific": {"hour": 21}, "clock": {"hour": 21}}
    assert engine.render("{{clock:pacific.hour_color}}", ctx) == "{70}"
    assert engine.render("{{clock.hour_color}}", ctx) == ""


def test_saved_rule_field_name_is_case_insensitive(tmp_path):
    # The editor's field box is free text; the engine lowercases the field.
    engine = _engine(tmp_path, {"clock": {"enabled": True, "color_rules": {"Hour": [BLACK_AFTER_8PM]}}})
    assert engine.render("{{clock.hour_color}}", {"clock": {"hour": 21}}) == "{70}"


@pytest.mark.parametrize(
    "color_rules",
    [
        "red",
        ["x"],
        {"hour": "red"},
        {"hour": ["x"]},
        {"hour": {"a": 1}},
        {"hour": [{"condition": ">", "value": 0, "color": 63}]},
        {"hour": [{"condition": 5, "value": 0, "color": "red"}]},
        {"hour": [None, 7]},
    ],
)
def test_malformed_saved_rules_never_break_rendering(tmp_path, color_rules):
    # color_rules isn't shape-validated on save (API, MCP), so a bad value must
    # be ignored, not crash the whole page.
    engine = _engine(tmp_path, {"clock": {"enabled": True, "color_rules": color_rules}})
    ctx = {"clock": {"hour": 21}}
    assert engine.render("{{clock.hour}}", ctx) == "21"
    assert engine.render("{{clock.hour_color}}", ctx) == ""


def test_malformed_rule_is_skipped_but_valid_rules_still_apply(tmp_path):
    rules = {"hour": ["x", {"condition": ">", "value": 0, "color": 63}, BLACK_AFTER_8PM]}
    engine = _engine(tmp_path, {"clock": {"enabled": True, "color_rules": rules}})
    assert engine.render("{{clock.hour_color}}", {"clock": {"hour": 21}}) == "{70}"


def test_instance_rule_lookup_skips_env_overlay(tmp_path):
    # Env overrides never carry color_rules, and recomputing them (JSON-parsing
    # HOME_ASSISTANT_ENTITIES, say) for every variable on every render is waste.
    engine = _engine(tmp_path, {"clock": {"enabled": True, "color_rules": {"hour": [BLACK_AFTER_8PM]}}})
    with patch.object(ConfigManager, "_plugin_env_overrides", side_effect=AssertionError("env overlay read")):
        assert engine.render("{{clock.hour_color}}", {"clock": {"hour": 21}}) == "{70}"


def test_get_instance_color_rules_returns_a_copy(tmp_path):
    engine = _engine(tmp_path, {"clock": {"enabled": True, "color_rules": {"hour": [BLACK_AFTER_8PM]}}})
    cm = engine.config_manager
    cm.get_instance_color_rules("clock")["hour"][0]["color"] = "red"
    assert cm.get_instance_color_rules("clock")["hour"][0]["color"] == "black"


# --- line-length validation ---


def test_rule_color_variable_counts_as_one_tile(tmp_path):
    engine = _engine(tmp_path, {"clock": {"enabled": True, "color_rules": {"hour": [BLACK_AFTER_8PM]}}})
    assert engine._calculate_max_line_length("{{clock.hour_color}}") == 1


def test_home_assistant_color_attribute_is_not_one_tile(tmp_path):
    # {{home_assistant.light_living_room.rgb_color}} renders the raw value,
    # e.g. "[255, 180, 120]", not a tile.
    engine = _engine(tmp_path, {"home_assistant": {"enabled": True}})
    for attr in ("rgb_color", "hs_color", "xy_color", "rgbw_color", "rgbww_color"):
        assert engine._calculate_max_line_length(f"{{{{home_assistant.light_living_room.{attr}}}}}") == 22


def test_color_suffix_without_rules_counts_one_tile(tmp_path):
    # {{plugin.<x>_color}} always resolves to a color lookup: one tile, or
    # nothing when no rule matches. It never renders a raw value.
    engine = _engine(tmp_path, {"clock": {"enabled": True}})
    assert engine.render("{{clock.team_color}}", {"clock": {"team_color": "LONG TEAM NAME"}}) == ""
    assert engine._calculate_max_line_length("{{clock.team_color}}") == 1
