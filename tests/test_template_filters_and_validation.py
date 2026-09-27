"""Filters that were documented but absent, and validation that stayed silent.

Three silent failures an author could not diagnose from the board:

* ``|upper`` / ``|lower`` were advertised in the engine's own module docstring
  but never implemented — an unknown filter is a no-op, so the value rendered
  unchanged and nothing said why.
* Filter chains (``|upper|pad:3``) were documented as chainable but the whole
  remaining chain was parsed as one filter name, so every chain was a no-op.
* ``validate_template`` checked only the plugin id, so a misspelled field
  (``{{weather.temperatur}}``) validated clean and rendered ``???``.
"""

from contextlib import contextmanager
from unittest.mock import patch

import pytest

from src.templates.engine import TemplateEngine

CTX = {"weather": {"condition": "sunny", "temperature": 72}}

KNOWN = {"weather": ["condition", "temperature", "forecast", "forecast.*.high"]}


@contextmanager
def catalog(variables: dict[str, list[str]], extra_sources: set[str] | None = None):
    """Pin the variable catalog so validation has a known world.

    ``extra_sources`` mirrors what the registry really reports: an instanced
    plugin is a source under its instance key (``weather:sf``) while its
    variables stay catalogued under the base id.
    """
    with (
        patch.object(TemplateEngine, "get_available_variables", return_value=variables),
        patch.object(
            TemplateEngine,
            "get_all_known_sources",
            return_value=set(variables) | (extra_sources or set()),
        ),
    ):
        yield


@pytest.fixture
def engine() -> TemplateEngine:
    return TemplateEngine()


class TestCaseFilters:
    def test_upper_filter_uppercases(self):
        engine = TemplateEngine()
        assert engine.render("{{weather.condition|upper}}", CTX) == "SUNNY"

    def test_lower_filter_lowercases(self):
        engine = TemplateEngine()
        assert engine.render("{{weather.condition|lower}}", {"weather": {"condition": "SUNNY"}}) == "sunny"

    def test_filters_chain_left_to_right(self):
        engine = TemplateEngine()
        assert engine.render("{{weather.condition|upper|truncate:3}}", CTX) == "SUN"

    def test_chain_of_argument_filters(self):
        engine = TemplateEngine()
        assert engine.render("{{weather.temperature|zeropad:4|truncate:2}}", CTX) == "00"

    def test_unknown_filter_leaves_the_value_alone(self):
        # Still a no-op at render time (the board must show something), but
        # validation now reports it — see TestFilterValidation.
        engine = TemplateEngine()
        assert engine.render("{{weather.condition|shout}}", CTX) == "sunny"


class TestFilterValidation:
    def test_unknown_filter_is_reported(self):
        engine = TemplateEngine()
        messages = [e.message for e in engine.validate_template("{{weather.condition|shout}}")]
        assert any("shout" in m for m in messages)

    def test_known_filters_are_not_reported(self):
        engine = TemplateEngine()
        for spelling in ("upper", "lower", "wrap", "pad:3", "truncate:3", "zeropad:2"):
            messages = [e.message for e in engine.validate_template(f"{{{{weather.condition|{spelling}}}}}")]
            assert not any("filter" in m.lower() for m in messages), spelling


class TestFieldValidation:
    def test_misspelled_field_is_reported(self, engine):
        with catalog(KNOWN):
            messages = [e.message for e in engine.validate_template("{{weather.temperatur}}")]
        assert any("temperatur" in m for m in messages)

    def test_known_field_is_accepted(self, engine):
        with catalog(KNOWN):
            assert engine.validate_template("{{weather.temperature}}") == []

    def test_array_index_path_is_accepted(self, engine):
        with catalog(KNOWN):
            assert engine.validate_template("{{weather.forecast.0.high}}") == []

    def test_color_suffix_is_accepted(self, engine):
        with catalog(KNOWN):
            assert engine.validate_template("{{weather.temperature_color}}") == []

    def test_plugin_instance_key_uses_the_base_catalog(self, engine):
        with catalog(KNOWN, extra_sources={"weather:sf"}):
            assert engine.validate_template("{{weather:sf.temperature}}") == []

    def test_misspelled_field_on_an_instance_is_still_reported(self, engine):
        with catalog(KNOWN, extra_sources={"weather:sf"}):
            messages = [e.message for e in engine.validate_template("{{weather:sf.temperatur}}")]
        assert any("temperatur" in m for m in messages)

    def test_home_assistant_entity_paths_are_never_flagged(self, engine):
        with catalog({"home_assistant": ["state"]}):
            assert engine.validate_template("{{home_assistant.sensor_porch_temp.state}}") == []

    def test_plugin_with_no_declared_variables_is_not_flagged(self, engine):
        # auto_discover plugins can have an empty catalog when the discovery
        # fetch failed; guessing would flag every field they expose.
        with catalog({"mystery": []}):
            assert engine.validate_template("{{mystery.whatever}}") == []


class TestListRendering:
    def test_a_list_valued_variable_renders_the_missing_marker(self):
        # Previously rendered the Python repr: "[{'high': 70}]".
        engine = TemplateEngine()
        rendered = engine.render("{{weather.forecast}}", {"weather": {"forecast": [{"high": 70}]}})
        assert rendered == "???"

    def test_a_dict_valued_variable_renders_the_missing_marker(self):
        engine = TemplateEngine()
        rendered = engine.render("{{weather.detail}}", {"weather": {"detail": {"high": 70}}})
        assert rendered == "???"


class TestRowEmittingFormulaLength:
    def test_foreach_line_is_not_flagged_as_too_long(self):
        engine = TemplateEngine()
        line = 'NEXT: {{= FOREACH(transit.stops, item.eta & " " & item.name) }}'
        messages = [e.message for e in engine.validate_template(line, cols=22)]
        assert not any("too long" in m for m in messages)
