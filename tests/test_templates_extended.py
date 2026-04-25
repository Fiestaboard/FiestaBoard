"""Extended tests for template engine - covering additional code paths."""

import pytest
from unittest.mock import Mock, patch

from src.templates.engine import (
    TemplateEngine,
    get_template_engine,
    reset_template_engine,
)


@pytest.fixture
def engine():
    """Create a template engine instance."""
    return TemplateEngine()


# ---------------------------------------------------------------------------
# Init / Singleton / Cache (lines 107-109, 113-116, 121-124, 1467-1469)
# ---------------------------------------------------------------------------

class TestInitAndSingleton:

    def test_init_failure_raises_runtime_error(self):
        with patch('src.templates.engine.get_plugin_registry', side_effect=Exception("boom")):
            with pytest.raises(RuntimeError, match="Plugin system is required"):
                TemplateEngine()

    def test_reset_cache_clears_services(self, engine):
        engine._display_service = "stale_display"
        engine._config_manager = "stale_config"
        engine.reset_cache()
        assert engine._display_service is None
        assert engine._config_manager is None
        assert engine._plugin_registry is not None

    def test_display_service_lazy_load(self, engine):
        assert engine._display_service is None
        ds = engine.display_service
        assert ds is not None
        assert engine.display_service is ds

    def test_get_template_engine_creates_singleton(self):
        import src.templates.engine as mod
        original = mod._template_engine
        try:
            mod._template_engine = None
            eng = get_template_engine()
            assert eng is not None
            assert get_template_engine() is eng
        finally:
            mod._template_engine = original

    def test_reset_template_engine_resets_cache(self):
        import src.templates.engine as mod
        original = mod._template_engine
        try:
            eng = TemplateEngine()
            mod._template_engine = eng
            eng._display_service = "stale"
            reset_template_engine()
            assert eng._display_service is None
        finally:
            mod._template_engine = original

    def test_reset_template_engine_when_none_is_safe(self):
        import src.templates.engine as mod
        original = mod._template_engine
        try:
            mod._template_engine = None
            reset_template_engine()
        finally:
            mod._template_engine = original


# ---------------------------------------------------------------------------
# _count_tiles (lines 190-198)
# ---------------------------------------------------------------------------

class TestCountTiles:

    def test_regular_chars(self, engine):
        assert engine._count_tiles("ABC") == 3

    def test_numeric_color_one_tile(self, engine):
        assert engine._count_tiles("{63}") == 1

    def test_named_color_one_tile(self, engine):
        assert engine._count_tiles("{green}") == 1

    def test_end_tag_not_counted(self, engine):
        assert engine._count_tiles("{/red}") == 0
        assert engine._count_tiles("{/}") == 0

    def test_mixed_color_text_end_tag(self, engine):
        assert engine._count_tiles("{green}AB{/green}") == 3

    def test_multiple_named_colors(self, engine):
        assert engine._count_tiles("{red}{blue}{green}") == 3


# ---------------------------------------------------------------------------
# _truncate_to_tiles (lines 224-245)
# ---------------------------------------------------------------------------

class TestTruncateToTiles:

    def test_truncate_plain_text(self, engine):
        assert engine._truncate_to_tiles("ABCDEF", 3) == "ABC"

    def test_preserves_numeric_color(self, engine):
        assert engine._truncate_to_tiles("{63}ABCDE", 3) == "{63}AB"

    def test_preserves_named_color(self, engine):
        assert engine._truncate_to_tiles("{green}ABCDE", 2) == "{green}A"

    def test_skips_end_tags(self, engine):
        assert engine._truncate_to_tiles("{/red}ABCDE", 2) == "AB"

    def test_no_truncation_needed(self, engine):
        assert engine._truncate_to_tiles("AB", 5) == "AB"


# ---------------------------------------------------------------------------
# _word_wrap (lines 433-468)
# ---------------------------------------------------------------------------

class TestWordWrap:

    def test_empty_text(self, engine):
        assert engine._word_wrap("", 22, 22, 3) == [""]

    def test_single_word_fits(self, engine):
        assert engine._word_wrap("Hello", 22, 22, 3) == ["Hello"]

    def test_wraps_at_word_boundary(self, engine):
        result = engine._word_wrap("Hello World", 6, 22, 3)
        assert result == ["Hello", "World"]

    def test_first_word_too_long_truncated(self, engine):
        result = engine._word_wrap("ABCDEFGHIJ", 5, 5, 3)
        assert result[0] == "ABCDE"

    def test_max_lines_respected(self, engine):
        result = engine._word_wrap("A B C D E F G", 3, 3, 2)
        assert len(result) <= 2

    def test_zero_max_lines(self, engine):
        result = engine._word_wrap("TOOLONG", 0, 0, 0)
        assert result == [""]


# ---------------------------------------------------------------------------
# _split_into_tokens (lines 497-506)
# ---------------------------------------------------------------------------

class TestSplitIntoTokens:

    def test_plain_chars(self, engine):
        assert engine._split_into_tokens("ABC") == ["A", "B", "C"]

    def test_numeric_color_token(self, engine):
        assert engine._split_into_tokens("{63}AB") == ["{63}", "A", "B"]

    def test_named_color_token(self, engine):
        assert engine._split_into_tokens("{green}AB") == ["{green}", "A", "B"]

    def test_end_tag_token(self, engine):
        assert engine._split_into_tokens("{/red}AB") == ["{/red}", "A", "B"]

    def test_mixed_tokens(self, engine):
        tokens = engine._split_into_tokens("X{63}Y{/red}Z")
        assert tokens == ["X", "{63}", "Y", "{/red}", "Z"]


# ---------------------------------------------------------------------------
# _word_wrap_tiles (lines 530, 550-554, 557-559, 579, 608-617, 620-669,
#                   673, 677)
# ---------------------------------------------------------------------------

class TestWordWrapTiles:

    def test_empty_text(self, engine):
        assert engine._word_wrap_tiles("", 22, 22, 3) == [""]

    def test_named_color_in_word(self, engine):
        result = engine._word_wrap_tiles("{green}HI", 22, 22, 3)
        assert len(result) >= 1
        assert "{green}" in result[0]

    def test_spaces_split_words(self, engine):
        result = engine._word_wrap_tiles("A B C", 22, 22, 3)
        assert result == ["A B C"]

    def test_first_word_fits_on_line(self, engine):
        result = engine._word_wrap_tiles("HELLO WORLD", 6, 6, 3)
        assert result[0] == "HELLO"
        assert result[1] == "WORLD"

    def test_last_line_appended(self, engine):
        result = engine._word_wrap_tiles("A B", 22, 22, 5)
        assert result == ["A B"]

    def test_whitespace_only_produces_empty(self, engine):
        result = engine._word_wrap_tiles("   ", 22, 22, 3)
        assert result == [""]

    def test_long_word_broken_across_lines(self, engine):
        result = engine._word_wrap_tiles("A" * 50, 22, 22, 5)
        assert len(result) >= 2
        for line in result:
            assert engine._count_tiles(line) <= 22

    def test_subsequent_word_too_long_broken(self, engine):
        result = engine._word_wrap_tiles("HI " + "B" * 50, 22, 22, 5)
        assert len(result) >= 2
        assert result[0].startswith("HI")

    def test_named_color_word_wrap(self, engine):
        text = "{green}" * 30
        result = engine._word_wrap_tiles(text, 22, 22, 3)
        assert len(result) >= 2
        for line in result:
            assert engine._count_tiles(line) <= 22

    def test_word_fits_on_subsequent_line(self, engine):
        result = engine._word_wrap_tiles("AAAAAAAAAAAA BBB", 12, 12, 3)
        assert result == ["AAAAAAAAAAAA", "BBB"]


# ---------------------------------------------------------------------------
# _render_with_wrap (lines 362-419)
# ---------------------------------------------------------------------------

class TestRenderWithWrap:

    def test_variable_level_wrap(self, engine):
        context = {"test": {"long": "A B C D E F G H I J K"}}
        result = engine._render_with_wrap("{{test.long|wrap}}", context, max_lines=3)
        assert 1 <= len(result) <= 3

    def test_variable_wrap_with_prefix_suffix(self, engine):
        context = {"test": {"val": "AAAA BBBB CCCC DDDD"}}
        result = engine._render_with_wrap("PRE:{{test.val|wrap}}:SUF", context, max_lines=3)
        assert "PRE:" in result[0]
        assert ":SUF" in result[0]

    def test_variable_wrap_with_other_filters(self, engine):
        context = {"test": {"val": "hello world foo bar"}}
        result = engine._render_with_wrap("{{test.val|truncate:11|wrap}}", context, max_lines=3)
        assert len(result) >= 1

    def test_line_level_wrap(self, engine):
        context = {"test": {"val": "SHORT"}}
        result = engine._render_with_wrap(
            "{{test.val}} some extra text here now", context, max_lines=2
        )
        assert len(result) >= 1


# ---------------------------------------------------------------------------
# render_lines with wrap (lines 295-319)
# ---------------------------------------------------------------------------

class TestRenderLinesWrap:

    def test_wrap_prefix(self, engine):
        context = {"test": {"val": "A B C D E F G H I J K L M"}}
        lines = ["{wrap}{{test.val}}", "", "", "", "", ""]
        result = engine.render_lines(lines, context)
        output = result.split('\n')
        assert len(output) == 6

    def test_wrap_respects_non_empty_boundary(self, engine):
        context = {"test": {"val": "A B C D E F G H I J K L M N O P Q R"}}
        lines = ["{wrap}{{test.val}}", "", "FIXED", "", "", ""]
        result = engine.render_lines(lines, context)
        output = result.split('\n')
        assert "FIXED" in output[2]

    def test_pipe_wrap_filter_in_lines(self, engine):
        context = {"test": {"val": "A B C D E F G H I J K L M"}}
        lines = ["{{test.val|wrap}}", "", "", "", "", ""]
        result = engine.render_lines(lines, context)
        assert len(result.split('\n')) == 6


# ---------------------------------------------------------------------------
# render with context=None (line 146)
# ---------------------------------------------------------------------------

class TestRenderContextNone:

    def test_render_builds_context_when_none(self, engine):
        result = engine.render("Hello", context=None)
        assert "Hello" in result

    def test_render_lines_builds_context_when_none(self, engine):
        result = engine.render_lines(["Hello"], context=None)
        assert "Hello" in result


# ---------------------------------------------------------------------------
# Variable edge cases (lines 717-720, 724, 863-864, 976-991, 995)
# ---------------------------------------------------------------------------

class TestVariableEdgeCases:

    def test_single_part_returns_error(self, engine):
        result = engine.render("{{noperiod}}", context={})
        assert "???" in result

    def test_none_value(self, engine):
        context = {"test": {"val": None}}
        assert "???" in engine.render("{{test.val}}", context)

    def test_value_is_color_code(self, engine):
        context = {"test": {"val": "{66}"}}
        assert engine.render("{{test.val}}", context) == "{66}"

    def test_value_starts_with_color_code(self, engine):
        context = {"test": {"val": "{66}RISE"}}
        assert engine.render("{{test.val}}", context) == "{66}RISE"

    def test_fill_space_variable(self, engine):
        result = engine.render("{{fill_space}}", context={})
        assert '\x00FILL_SPACE\x00' in result

    def test_fill_space_repeat_variable(self, engine):
        result = engine.render("{{fill_space_repeat:-}}", context={})
        assert '\x00FILL_SPACE_REPEAT:-\x00' in result

    def test_array_access_by_index(self, engine):
        context = {"test": {"items": ["A", "B", "C"]}}
        assert engine.render("{{test.items.0}}", context) == "A"
        assert engine.render("{{test.items.2}}", context) == "C"

    def test_array_index_out_of_range(self, engine):
        context = {"test": {"items": ["A"]}}
        assert "???" in engine.render("{{test.items.5}}", context)

    def test_array_non_numeric_access(self, engine):
        context = {"test": {"items": ["A", "B"]}}
        assert "???" in engine.render("{{test.items.name}}", context)

    def test_navigate_past_scalar(self, engine):
        context = {"test": {"val": "string"}}
        assert "???" in engine.render("{{test.val.sub}}", context)


# ---------------------------------------------------------------------------
# Home Assistant entity handling (lines 880-945)
# ---------------------------------------------------------------------------

class TestHomeAssistantVariables:

    def test_entity_state(self, engine):
        context = {
            "home_assistant": {
                "sensor.temperature": {"state": "72", "attributes": {}}
            }
        }
        assert engine.render(
            "{{home_assistant.sensor_temperature.state}}", context
        ) == "72"

    def test_entity_attribute(self, engine):
        context = {
            "home_assistant": {
                "sensor.temperature": {
                    "state": "72",
                    "attributes": {"unit_of_measurement": "F"}
                }
            }
        }
        assert engine.render(
            "{{home_assistant.sensor_temperature.unit_of_measurement}}", context
        ) == "F"

    def test_entity_not_found(self, engine):
        context = {"home_assistant": {}}
        assert "???" in engine.render(
            "{{home_assistant.sensor_missing.state}}", context
        )

    def test_attribute_not_found(self, engine):
        context = {
            "home_assistant": {
                "sensor.temperature": {"state": "72", "attributes": {}}
            }
        }
        assert "???" in engine.render(
            "{{home_assistant.sensor_temperature.nonexistent}}", context
        )

    def test_multi_underscore_domain(self, engine):
        context = {
            "home_assistant": {
                "media_player.living_room": {
                    "state": "playing",
                    "attributes": {"media_title": "Song"}
                }
            }
        }
        assert engine.render(
            "{{home_assistant.media_player_living_room.state}}", context
        ) == "playing"

    def test_boolean_attribute(self, engine):
        context = {
            "home_assistant": {
                "switch.light": {
                    "state": "on",
                    "attributes": {"is_on": True}
                }
            }
        }
        assert engine.render(
            "{{home_assistant.switch_light.is_on}}", context
        ) == "Yes"

    def test_boolean_false_attribute(self, engine):
        context = {
            "home_assistant": {
                "switch.light": {
                    "state": "off",
                    "attributes": {"is_on": False}
                }
            }
        }
        assert engine.render(
            "{{home_assistant.switch_light.is_on}}", context
        ) == "No"

    def test_numeric_attribute(self, engine):
        context = {
            "home_assistant": {
                "sensor.temp": {
                    "state": "72",
                    "attributes": {"current": 72.5}
                }
            }
        }
        assert engine.render(
            "{{home_assistant.sensor_temp.current}}", context
        ) == "72.5"

    def test_integer_attribute(self, engine):
        context = {
            "home_assistant": {
                "sensor.temp": {
                    "state": "72",
                    "attributes": {"current": 72.0}
                }
            }
        }
        assert engine.render(
            "{{home_assistant.sensor_temp.current}}", context
        ) == "72"

    def test_none_attribute(self, engine):
        context = {
            "home_assistant": {
                "sensor.temp": {
                    "state": "unknown",
                    "attributes": {"current": None}
                }
            }
        }
        assert "???" in engine.render(
            "{{home_assistant.sensor_temp.current}}", context
        )

    def test_no_underscore_entity(self, engine):
        context = {
            "home_assistant": {
                "sensor": {"state": "ok", "attributes": {}}
            }
        }
        assert engine.render(
            "{{home_assistant.sensor.state}}", context
        ) == "ok"

    def test_top_level_attribute(self, engine):
        context = {
            "home_assistant": {
                "sensor.temp": {
                    "state": "72",
                    "last_updated": "2024-01-01",
                    "attributes": {}
                }
            }
        }
        assert engine.render(
            "{{home_assistant.sensor_temp.last_updated}}", context
        ) == "2024-01-01"

    def test_top_level_bool_attribute(self, engine):
        context = {
            "home_assistant": {
                "sensor.temp": {
                    "state": "72",
                    "is_available": True,
                    "attributes": {}
                }
            }
        }
        assert engine.render(
            "{{home_assistant.sensor_temp.is_available}}", context
        ) == "Yes"

    def test_top_level_numeric_attribute(self, engine):
        context = {
            "home_assistant": {
                "sensor.temp": {
                    "state": "72",
                    "battery": 85.0,
                    "attributes": {}
                }
            }
        }
        assert engine.render(
            "{{home_assistant.sensor_temp.battery}}", context
        ) == "85"

    def test_top_level_none_attribute(self, engine):
        context = {
            "home_assistant": {
                "sensor.temp": {
                    "state": "72",
                    "friendly_name": None,
                    "attributes": {}
                }
            }
        }
        assert "???" in engine.render(
            "{{home_assistant.sensor_temp.friendly_name}}", context
        )

    def test_fallback_first_underscore_replace(self, engine):
        context = {"home_assistant": {}}
        assert "???" in engine.render(
            "{{home_assistant.nonexistent_entity.state}}", context
        )


# ---------------------------------------------------------------------------
# _color suffix (lines 952-955)
# ---------------------------------------------------------------------------

class TestColorSuffix:

    def test_color_suffix_no_rules(self, engine):
        context = {"test": {"temperature": 72}}
        result = engine.render("{{test.temperature_color}}", context)
        assert result == ""


# ---------------------------------------------------------------------------
# _evaluate_condition (lines 805-836)
# ---------------------------------------------------------------------------

class TestEvaluateCondition:

    def test_greater_than(self, engine):
        assert engine._evaluate_condition(10, ">", 5) is True
        assert engine._evaluate_condition(5, ">", 10) is False

    def test_less_than(self, engine):
        assert engine._evaluate_condition(5, "<", 10) is True
        assert engine._evaluate_condition(10, "<", 5) is False

    def test_greater_equal(self, engine):
        assert engine._evaluate_condition(10, ">=", 10) is True
        assert engine._evaluate_condition(10, ">=", 5) is True
        assert engine._evaluate_condition(5, ">=", 10) is False

    def test_less_equal(self, engine):
        assert engine._evaluate_condition(10, "<=", 10) is True
        assert engine._evaluate_condition(5, "<=", 10) is True
        assert engine._evaluate_condition(10, "<=", 5) is False

    def test_equals(self, engine):
        assert engine._evaluate_condition("sunny", "==", "sunny") is True
        assert engine._evaluate_condition("sunny", "==", "cloudy") is False

    def test_not_equals(self, engine):
        assert engine._evaluate_condition("sunny", "!=", "cloudy") is True
        assert engine._evaluate_condition("sunny", "!=", "sunny") is False

    def test_non_numeric_with_numeric_operator(self, engine):
        assert engine._evaluate_condition("abc", ">", "xyz") is False
        assert engine._evaluate_condition("abc", "<", "xyz") is False
        assert engine._evaluate_condition("abc", ">=", "xyz") is False
        assert engine._evaluate_condition("abc", "<=", "xyz") is False

    def test_unknown_condition_returns_false(self, engine):
        assert engine._evaluate_condition("a", "~", "a") is False


# ---------------------------------------------------------------------------
# _get_color_for_value (lines 763-792)
# ---------------------------------------------------------------------------

class TestGetColorForValue:

    def test_no_dot_returns_empty(self, engine):
        assert engine._get_color_for_value("nodot", {}) == ""

    def test_skips_uv_index(self, engine):
        assert engine._get_color_for_value("weather.uv_index", {}) == ""

    def test_skips_temperature(self, engine):
        assert engine._get_color_for_value("weather.temperature", {}) == ""

    def test_rules_from_config(self, engine):
        mock_config = Mock()
        mock_config.get_color_rules.return_value = [
            {"condition": ">", "value": 80, "color": "red"},
        ]
        engine._config_manager = mock_config
        context = {"weather": {"aqi": 90}}
        assert engine._get_color_for_value("weather.aqi", context) == "{63} "

    def test_no_rules_returns_empty(self, engine):
        mock_config = Mock()
        mock_config.get_color_rules.return_value = []
        engine._config_manager = mock_config
        engine._plugin_registry = Mock()
        engine._plugin_registry.get_manifest.return_value = None
        assert engine._get_color_for_value("weather.aqi", {}) == ""

    def test_raw_value_none_returns_empty(self, engine):
        mock_config = Mock()
        mock_config.get_color_rules.return_value = [
            {"condition": ">", "value": 80, "color": "red"},
        ]
        engine._config_manager = mock_config
        context = {"weather": {}}
        assert engine._get_color_for_value("weather.aqi", context) == ""

    def test_rules_from_manifest(self, engine):
        mock_config = Mock()
        mock_config.get_color_rules.return_value = []
        engine._config_manager = mock_config

        mock_manifest = Mock()
        mock_manifest.color_rules_schema = {
            "aqi": {"default_rules": [{"condition": ">", "value": 50, "color": "red"}]}
        }
        engine._plugin_registry = Mock()
        engine._plugin_registry.get_manifest.return_value = mock_manifest

        context = {"weather": {"aqi": 90}}
        assert engine._get_color_for_value("weather.aqi", context) == "{63} "

    def test_no_matching_rule_returns_empty(self, engine):
        mock_config = Mock()
        mock_config.get_color_rules.return_value = [
            {"condition": ">", "value": 100, "color": "red"},
        ]
        engine._config_manager = mock_config
        context = {"weather": {"aqi": 10}}
        assert engine._get_color_for_value("weather.aqi", context) == ""


# ---------------------------------------------------------------------------
# _get_color_only (lines 1014-1050)
# ---------------------------------------------------------------------------

class TestGetColorOnly:

    def test_returns_color_tile(self, engine):
        mock_config = Mock()
        mock_config.get_color_rules.return_value = [
            {"condition": ">=", "value": 0, "color": "green"}
        ]
        engine._config_manager = mock_config
        context = {"test": {"val": 10}}
        assert engine._get_color_only("test", "val", context) == "{66}"

    def test_no_rules_returns_empty(self, engine):
        mock_config = Mock()
        mock_config.get_color_rules.return_value = []
        engine._config_manager = mock_config
        engine._plugin_registry = Mock()
        engine._plugin_registry.get_manifest.return_value = None
        assert engine._get_color_only("test", "val", {}) == ""

    def test_null_raw_value_returns_empty(self, engine):
        mock_config = Mock()
        mock_config.get_color_rules.return_value = [
            {"condition": ">", "value": 0, "color": "red"}
        ]
        engine._config_manager = mock_config
        context = {"test": {}}
        assert engine._get_color_only("test", "val", context) == ""

    def test_rules_from_manifest_fallback(self, engine):
        mock_config = Mock()
        mock_config.get_color_rules.return_value = []
        engine._config_manager = mock_config

        mock_manifest = Mock()
        mock_manifest.color_rules_schema = {
            "val": {"default_rules": [{"condition": "==", "value": "ok", "color": "green"}]}
        }
        engine._plugin_registry = Mock()
        engine._plugin_registry.get_manifest.return_value = mock_manifest

        context = {"test": {"val": "ok"}}
        assert engine._get_color_only("test", "val", context) == "{66}"

    def test_no_matching_rule_returns_empty(self, engine):
        mock_config = Mock()
        mock_config.get_color_rules.return_value = [
            {"condition": ">", "value": 100, "color": "red"},
        ]
        engine._config_manager = mock_config
        context = {"test": {"val": 10}}
        assert engine._get_color_only("test", "val", context) == ""


# ---------------------------------------------------------------------------
# _map_field_for_data_lookup (lines 1067-1070)
# ---------------------------------------------------------------------------

class TestMapFieldForDataLookup:

    def test_weather_temp_maps_to_temperature(self, engine):
        assert engine._map_field_for_data_lookup("weather", "temp") == "temperature"

    def test_other_field_unchanged(self, engine):
        assert engine._map_field_for_data_lookup("weather", "humidity") == "humidity"
        assert engine._map_field_for_data_lookup("stocks", "price") == "price"


# ---------------------------------------------------------------------------
# Filter edge cases (lines 1087-1088, 1094-1097)
# ---------------------------------------------------------------------------

class TestFilterEdgeCases:

    def test_pad_invalid_arg(self, engine):
        assert engine._apply_filter("hello", "pad:abc") == "hello"

    def test_truncate_invalid_arg(self, engine):
        assert engine._apply_filter("hello", "truncate:abc") == "hello"

    def test_unknown_filter_no_colon(self, engine):
        assert engine._apply_filter("hello", "unknown") == "hello"

    def test_pad_truncates_long_value(self, engine):
        result = engine._apply_filter("LONGWORD", "pad:4")
        assert result == "LONG"
        assert len(result) == 4


# ---------------------------------------------------------------------------
# _normalize_colors (line 1120)
# ---------------------------------------------------------------------------

class TestNormalizeColors:

    def test_named_color_to_numeric(self, engine):
        assert engine._normalize_colors("{{red}}") == "{63}"

    def test_numeric_color_preserved(self, engine):
        assert engine._normalize_colors("{{63}}") == "{63}"

    def test_plain_text_unchanged(self, engine):
        assert engine._normalize_colors("some text") == "some text"


# ---------------------------------------------------------------------------
# _extract_alignment with wrap (lines 1141-1142)
# ---------------------------------------------------------------------------

class TestExtractAlignmentWrap:

    def test_wrap_prefix_detected(self, engine):
        alignment, wrap_enabled, content = engine._extract_alignment("{wrap}Hello")
        assert wrap_enabled is True
        assert alignment == "left"
        assert content == "Hello"

    def test_wrap_with_center(self, engine):
        alignment, wrap_enabled, content = engine._extract_alignment("{wrap}{center}Hello")
        assert wrap_enabled is True
        assert alignment == "center"
        assert content == "Hello"


# ---------------------------------------------------------------------------
# _build_context with no registry (line 688)
# ---------------------------------------------------------------------------

class TestBuildContextNoRegistry:

    def test_no_registry_returns_empty(self, engine):
        engine._plugin_registry = None
        assert engine._build_context() == {}


# ---------------------------------------------------------------------------
# Methods with no registry (lines 1266, 1275-1277, 1336, 1417, 1433)
# ---------------------------------------------------------------------------

class TestNoRegistryPaths:

    def test_get_available_variables_empty(self, engine):
        engine._plugin_registry = None
        assert engine.get_available_variables() == {}

    def test_get_available_sources_empty(self, engine):
        engine._plugin_registry = None
        assert engine._get_available_sources() == []

    def test_get_all_known_sources_empty(self, engine):
        engine._plugin_registry = None
        assert engine._get_all_known_sources() == set()

    def test_get_max_lengths_for_validation_empty(self, engine):
        engine._plugin_registry = None
        assert engine._get_max_lengths_for_validation() == {}

    def test_get_variable_max_lengths_empty(self, engine):
        engine._plugin_registry = None
        assert engine.get_variable_max_lengths() == {}


# ---------------------------------------------------------------------------
# strip_formatting (lines 1442-1445)
# ---------------------------------------------------------------------------

class TestStripFormatting:

    def test_removes_unresolved_variables(self, engine):
        assert engine.strip_formatting("Hello {{world}}") == "Hello "

    def test_removes_color_markers(self, engine):
        assert engine.strip_formatting("A{63}B{/red}C") == "ABC"

    def test_plain_text_unchanged(self, engine):
        assert engine.strip_formatting("Hello World") == "Hello World"


# ---------------------------------------------------------------------------
# fill_space repeat patterns (line 1240, 1250)
# ---------------------------------------------------------------------------

class TestFillSpaceRepeat:

    def test_repeat_dash(self, engine):
        marker = '\x00FILL_SPACE_REPEAT:-\x00'
        result = engine._process_fill_space(f"A{marker}B", width=10)
        assert result.startswith("A")
        assert result.endswith("B")
        assert len(result) == 10
        assert "--------" in result

    def test_repeat_color(self, engine):
        marker = '\x00FILL_SPACE_REPEAT:blue\x00'
        result = engine._process_fill_space(f"A{marker}B", width=6)
        assert result.startswith("A")
        assert result.endswith("B")
        assert "{67}" in result

    def test_repeat_multi_char_pattern(self, engine):
        marker = '\x00FILL_SPACE_REPEAT:=-\x00'
        result = engine._process_fill_space(f"A{marker}B", width=10)
        assert result.startswith("A")
        assert result.endswith("B")
        assert len(result) == 10


# ---------------------------------------------------------------------------
# _calculate_max_line_length (lines 1356, 1399-1400)
# ---------------------------------------------------------------------------

class TestCalculateMaxLineLength:

    def test_wrap_filter_returns_22(self, engine):
        assert engine._calculate_max_line_length("{{test.val|wrap}}") == 22

    def test_static_text_measured(self, engine):
        assert engine._calculate_max_line_length("Hello") == 5

    def test_color_markers_replaced_with_single_char(self, engine):
        result = engine._calculate_max_line_length("{red}AB")
        assert result == 3

    def test_color_rules_exception_handled(self, engine):
        mock_config = Mock()
        mock_config.get_color_rules.side_effect = Exception("config error")
        engine._config_manager = mock_config
        result = engine._calculate_max_line_length("{{weather.aqi}}")
        assert isinstance(result, int)
