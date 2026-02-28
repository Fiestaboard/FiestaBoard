"""Tests for template engine."""

import pytest
from unittest.mock import Mock, patch

from src.templates.engine import (
    TemplateEngine,
    COLOR_CODES,
    SYMBOL_CHARS,
    TemplateError,
)
from src.displays.service import DisplayResult


class TestTemplateEngineBasics:
    """Tests for basic template engine functionality."""
    
    @pytest.fixture
    def engine(self):
        """Create a template engine with mocked display service."""
        engine = TemplateEngine()
        return engine
    
    def test_render_plain_text(self, engine):
        """Test rendering plain text without any template syntax."""
        result = engine.render("Hello World", context={})
        assert result == "Hello World"
    
    def test_render_preserves_spaces(self, engine):
        """Test that spaces are preserved."""
        result = engine.render("  Spaced  Text  ", context={})
        assert result == "  Spaced  Text  "


class TestVariableSubstitution:
    """Tests for {{variable}} substitution."""
    
    @pytest.fixture
    def engine(self):
        return TemplateEngine()
    
    def test_simple_variable(self, engine):
        """Test simple variable substitution."""
        context = {"weather": {"temperature": 72}}
        result = engine.render("Temp: {{weather.temperature}}", context)
        assert result == "Temp: 72"
    
    def test_nested_variable(self, engine):
        """Test nested variable access."""
        context = {"weather": {"current": {"temp": 72}}}
        result = engine.render("{{weather.current.temp}}", context)
        assert result == "72"
    
    def test_missing_source(self, engine):
        """Test missing source returns error indicator."""
        result = engine.render("{{missing.field}}", context={})
        assert "???" in result  # Error indicator for missing/unavailable
    
    def test_missing_field(self, engine):
        """Test missing field returns error indicator."""
        context = {"weather": {"temperature": 72}}
        result = engine.render("{{weather.missing}}", context)
        assert "???" in result
    
    def test_boolean_value(self, engine):
        """Test boolean values are converted to Yes/No."""
        context = {"baywheels": {"is_renting": True}}
        result = engine.render("Renting: {{baywheels.is_renting}}", context)
        assert "Yes" in result
        
        context = {"baywheels": {"is_renting": False}}
        result = engine.render("Renting: {{baywheels.is_renting}}", context)
        assert "No" in result
    
    def test_numeric_value(self, engine):
        """Test numeric values are formatted correctly."""
        context = {"weather": {"temperature": 72.5}}
        result = engine.render("{{weather.temperature}}", context)
        assert result == "72.5"
        
        context = {"weather": {"temperature": 72.0}}
        result = engine.render("{{weather.temperature}}", context)
        assert result == "72"  # No decimal for whole numbers


class TestFilters:
    """Tests for value filters (|pad, |upper, etc.)."""
    
    @pytest.fixture
    def engine(self):
        return TemplateEngine()
    
    def test_pad_filter(self, engine):
        """Test |pad:N filter."""
        context = {"weather": {"temperature": 72}}
        result = engine.render("{{weather.temperature|pad:5}}", context)
        assert result == "72   "  # Padded to 5 chars
    
    def test_truncate_filter(self, engine):
        """Test |truncate:N filter."""
        context = {"weather": {"condition": "Partly Cloudy"}}
        result = engine.render("{{weather.condition|truncate:6}}", context)
        assert result == "Partly"


class TestColors:
    """Tests for color code handling."""
    
    @pytest.fixture
    def engine(self):
        return TemplateEngine()
    
    def test_color_codes_defined(self):
        """Test all expected colors are defined."""
        expected = ["red", "orange", "yellow", "green", "blue", "violet", "white", "black"]
        for color in expected:
            assert color in COLOR_CODES
    
    def test_named_color_normalized(self, engine):
        """Test named colors are normalized to codes."""
        result = engine.render("{{red}}Text{{/red}}", context={})
        assert "{63}" in result  # Red = 63
    
    def test_numeric_color_preserved(self, engine):
        """Test numeric color codes are preserved."""
        result = engine.render("{{63}}Text{{/}}", context={})
        assert "{63}" in result
    
    def test_color_end_tag_normalized(self, engine):
        """Test color end tags are normalized."""
        result = engine.render("{{red}}Text{{/red}}", context={})
        # Color end tags become {/color} format after render
        assert "Text" in result


class TestSymbols:
    """Tests for symbol shortcuts."""
    
    @pytest.fixture
    def engine(self):
        return TemplateEngine()
    
    def test_symbols_defined(self):
        """Test all expected symbols are defined."""
        expected = ["sun", "cloud", "rain", "snow", "storm"]
        for symbol in expected:
            assert symbol in SYMBOL_CHARS
    
    def test_sun_symbol(self, engine):
        """Test {sun} symbol."""
        result = engine.render("{sun} Sunny", context={})
        assert SYMBOL_CHARS["sun"] in result
    
    def test_cloud_symbol(self, engine):
        """Test {cloud} symbol."""
        result = engine.render("{cloud} Cloudy", context={})
        assert SYMBOL_CHARS["cloud"] in result
    
    def test_symbol_case_insensitive(self, engine):
        """Test symbols are case insensitive."""
        result = engine.render("{SUN} {Sun} {sun}", context={})
        assert result.count(SYMBOL_CHARS["sun"]) == 3


class TestValidation:
    """Tests for template validation."""
    
    @pytest.fixture
    def engine(self):
        return TemplateEngine()
    
    def test_valid_template(self, engine):
        """Test valid template has no errors."""
        errors = engine.validate_template("{{weather.temperature}} degrees")
        assert len(errors) == 0
    
    def test_mismatched_braces(self, engine):
        """Test mismatched braces are detected."""
        errors = engine.validate_template("{{weather.temperature} degrees")
        assert any("brace" in e.message.lower() for e in errors)
    
    def test_unknown_source(self, engine):
        """Test unknown source is detected."""
        errors = engine.validate_template("{{unknown.field}}")
        assert any("unknown source" in e.message.lower() for e in errors)
    
    def test_line_too_long_warning(self, engine):
        """Test warning for lines over 22 chars."""
        long_text = "This line is way too long for board"
        errors = engine.validate_template(long_text)
        assert any("too long" in e.message.lower() for e in errors)


class TestRenderLines:
    """Tests for render_lines method (template pages)."""
    
    @pytest.fixture
    def engine(self):
        return TemplateEngine()
    
    def test_render_lines_basic(self, engine):
        """Test rendering multiple lines."""
        lines = ["Line 1", "Line 2", "Line 3"]
        context = {}
        result = engine.render_lines(lines, context)
        
        output_lines = result.split('\n')
        assert len(output_lines) == 6  # Padded to 6
        assert "Line 1" in output_lines[0]
    
    def test_render_lines_pads_to_6(self, engine):
        """Test that output is always 6 lines."""
        result = engine.render_lines(["Only one line"], {})
        assert len(result.split('\n')) == 6
    
    def test_render_lines_truncates_to_22(self, engine):
        """Test each line is max 22 chars."""
        lines = ["This is a very long line that exceeds 22 characters"]
        result = engine.render_lines(lines, {})
        output_lines = result.split('\n')
        assert len(output_lines[0]) <= 22
    
    def test_render_lines_multiline_variable(self, engine):
        """Test that variables with newlines are split across multiple output lines."""
        # Create a context with a multi-line variable
        context = {
            "test": {
                "multiline": "Line 1\nLine 2\nLine 3"
            }
        }
        lines = ["{{test.multiline}}"]
        result = engine.render_lines(lines, context)
        
        output_lines = result.split('\n')
        assert len(output_lines) == 6  # Should still be 6 lines total
        assert "Line 1" in output_lines[0]
        assert "Line 2" in output_lines[1]
        assert "Line 3" in output_lines[2]
        # Remaining lines should be empty or padded
        assert output_lines[3] == "" or output_lines[3].strip() == ""
    
    def test_render_lines_multiline_variable_exceeds_6_lines(self, engine):
        """Test that multi-line variables exceeding 6 lines are truncated."""
        # Create a variable with more than 6 lines
        context = {
            "test": {
                "multiline": "\n".join([f"Line {i}" for i in range(1, 10)])
            }
        }
        lines = ["{{test.multiline}}"]
        result = engine.render_lines(lines, context)
        
        output_lines = result.split('\n')
        assert len(output_lines) == 6  # Should be exactly 6 lines
        assert "Line 1" in output_lines[0]
        assert "Line 6" in output_lines[5]  # Last line should be Line 6, not Line 9


class TestAvailableVariables:
    """Tests for available variables listing via plugin system."""
    
    @pytest.fixture
    def engine(self):
        return TemplateEngine()
    
    def test_get_available_variables_returns_dict(self, engine):
        """Test get_available_variables returns a dictionary."""
        variables = engine.get_available_variables()
        assert isinstance(variables, dict)
    
    def test_get_all_known_sources_returns_set(self, engine):
        """Test _get_all_known_sources returns a set of plugin IDs."""
        sources = engine._get_all_known_sources()
        assert isinstance(sources, set)


class TestAlignment:
    """Tests for line alignment handling."""
    
    @pytest.fixture
    def engine(self):
        return TemplateEngine()
    
    def test_extract_alignment_left_implicit(self, engine):
        """Test left alignment is default."""
        alignment, wrap_enabled, content = engine._extract_alignment("Hello World")
        assert alignment == "left"
        assert wrap_enabled is False
        assert content == "Hello World"
    
    def test_extract_alignment_left_explicit(self, engine):
        """Test explicit {left} prefix."""
        alignment, wrap_enabled, content = engine._extract_alignment("{left}Hello World")
        assert alignment == "left"
        assert wrap_enabled is False
        assert content == "Hello World"
    
    def test_extract_alignment_center(self, engine):
        """Test {center} prefix."""
        alignment, wrap_enabled, content = engine._extract_alignment("{center}Hello World")
        assert alignment == "center"
        assert wrap_enabled is False
        assert content == "Hello World"
    
    def test_extract_alignment_right(self, engine):
        """Test {right} prefix."""
        alignment, wrap_enabled, content = engine._extract_alignment("{right}Hello World")
        assert alignment == "right"
        assert wrap_enabled is False
        assert content == "Hello World"
    
    def test_extract_alignment_case_insensitive(self, engine):
        """Test alignment prefix is case insensitive."""
        alignment, wrap_enabled, content = engine._extract_alignment("{CENTER}Hello")
        assert alignment == "center"
        assert wrap_enabled is False
        assert content == "Hello"
    
    def test_apply_alignment_left(self, engine):
        """Test left alignment pads on the right."""
        result = engine._apply_alignment("Hello", "left", width=10)
        assert result == "Hello     "
        assert len(result) == 10
    
    def test_apply_alignment_center(self, engine):
        """Test center alignment pads both sides."""
        result = engine._apply_alignment("Hello", "center", width=10)
        # "Hello" is 5 chars, 5 spaces to add, 2 left + 3 right
        assert result == "  Hello   "
        assert len(result) == 10
    
    def test_apply_alignment_right(self, engine):
        """Test right alignment pads on the left."""
        result = engine._apply_alignment("Hello", "right", width=10)
        assert result == "     Hello"
        assert len(result) == 10
    
    def test_render_lines_with_center_alignment(self, engine):
        """Test render_lines applies center alignment."""
        lines = ["{center}TEST"]
        result = engine.render_lines(lines, {})
        output_lines = result.split('\n')
        # "TEST" is 4 chars, centered in 22 chars: 9 spaces + TEST + 9 spaces
        assert "TEST" in output_lines[0]
        assert output_lines[0].strip() == "TEST"
        assert len(output_lines[0]) == 22
        # Verify it's centered (roughly equal padding on both sides)
        left_pad = len(output_lines[0]) - len(output_lines[0].lstrip())
        right_pad = len(output_lines[0]) - len(output_lines[0].rstrip())
        assert abs(left_pad - right_pad) <= 1  # Allow 1 char difference for odd widths
    
    def test_render_lines_with_right_alignment(self, engine):
        """Test render_lines applies right alignment."""
        lines = ["{right}TEST"]
        result = engine.render_lines(lines, {})
        output_lines = result.split('\n')
        # "TEST" should be at the right
        assert output_lines[0].endswith("TEST")
        assert len(output_lines[0]) == 22

    def test_render_lines_with_line_metadata_center(self, engine):
        """Test render_lines reads alignment from line_metadata."""
        lines = ["TEST"]
        metadata = [{"alignment": "center", "wrap": False}]
        result = engine.render_lines(lines, {}, line_metadata=metadata)
        output_lines = result.split('\n')
        assert output_lines[0].strip() == "TEST"
        assert len(output_lines[0]) == 22
        left_pad = len(output_lines[0]) - len(output_lines[0].lstrip())
        right_pad = len(output_lines[0]) - len(output_lines[0].rstrip())
        assert abs(left_pad - right_pad) <= 1

    def test_render_lines_with_line_metadata_right(self, engine):
        """Test render_lines reads right alignment from line_metadata."""
        lines = ["TEST"]
        metadata = [{"alignment": "right", "wrap": False}]
        result = engine.render_lines(lines, {}, line_metadata=metadata)
        output_lines = result.split('\n')
        assert output_lines[0].endswith("TEST")
        assert len(output_lines[0]) == 22

    def test_render_lines_metadata_overrides_prefix(self, engine):
        """When line_metadata is provided, inline prefixes are NOT parsed."""
        lines = ["{center}TEST"]
        metadata = [{"alignment": "left", "wrap": False}]
        result = engine.render_lines(lines, {}, line_metadata=metadata)
        output_lines = result.split('\n')
        # The {center} prefix is treated as literal content (left-aligned)
        assert output_lines[0].startswith("{center}TEST")


class TestFillSpace:
    """Tests for {{fill_space}} variable."""
    
    # The fill_space marker used internally after variable substitution
    FILL_MARKER = '\x00FILL_SPACE\x00'
    
    @pytest.fixture
    def engine(self):
        return TemplateEngine()
    
    def test_single_fill_space(self, engine):
        """Test single fill_space expands to fill remaining width."""
        # Direct test of _process_fill_space uses the internal marker
        result = engine._process_fill_space(f"A{self.FILL_MARKER}B", width=10)
        # "A" + spaces + "B" = 10 chars
        assert result == "A        B"
        assert len(result) == 10
    
    def test_double_fill_space(self, engine):
        """Test two fill_spaces distribute space evenly."""
        result = engine._process_fill_space(f"A{self.FILL_MARKER}B{self.FILL_MARKER}C", width=11)
        # "A" + 4 spaces + "B" + 4 spaces + "C" = 11 chars (4+4 = 8 spaces for 8 remaining)
        assert result == "A    B    C"
        assert len(result) == 11
    
    def test_fill_space_no_room(self, engine):
        """Test fill_space removed when no room."""
        result = engine._process_fill_space(f"ABCDEFGHIJKLMNOPQRSTUV{self.FILL_MARKER}W", width=22)
        # 23 chars with W, no room for fill, should truncate
        assert self.FILL_MARKER not in result
        assert len(result) <= 22
    
    def test_fill_space_case_insensitive(self, engine):
        """Test fill_space variable is case insensitive (via full render path)."""
        # Test via full render to verify case insensitivity of the variable
        result = engine.render("A{{FILL_SPACE}}B", context={})
        # Should have the marker in it (case insensitive variable lookup)
        assert self.FILL_MARKER in result
    
    def test_render_lines_with_fill_space(self, engine):
        """Test render_lines processes fill_space."""
        lines = ["LEFT{{fill_space}}RIGHT"]
        result = engine.render_lines(lines, {})
        output_lines = result.split('\n')
        # Should have "LEFT" at start and "RIGHT" at end
        assert output_lines[0].startswith("LEFT")
        assert output_lines[0].endswith("RIGHT")
        assert len(output_lines[0]) == 22
    
    def test_fill_space_three_columns(self, engine):
        """Test three-column layout with two fill_spaces."""
        lines = ["A{{fill_space}}B{{fill_space}}C"]
        result = engine.render_lines(lines, {})
        output_lines = result.split('\n')
        # "A", "B", "C" = 3 chars, 19 spaces to distribute
        assert output_lines[0].startswith("A")
        assert output_lines[0].endswith("C")
        assert "B" in output_lines[0]
        assert len(output_lines[0]) == 22
        # B should be roughly in the middle
        b_pos = output_lines[0].index("B")
        assert 9 <= b_pos <= 12  # Roughly centered


class TestAlignmentWithFillSpace:
    """Tests for combining alignment and fill_space."""
    
    @pytest.fixture
    def engine(self):
        return TemplateEngine()
    
    def test_fill_space_with_center_alignment(self, engine):
        """Test fill_space with center alignment - fill_space fills the line first."""
        # When fill_space is present, it fills the remaining space first
        # Then alignment is applied, but since fill_space already fills to 22 chars,
        # the alignment has no additional effect
        lines = ["{center}A{{fill_space}}B"]
        result = engine.render_lines(lines, {})
        output_lines = result.split('\n')
        # fill_space should push A and B apart within the 22 char width
        # "A" + 20 spaces + "B" = 22 chars
        assert "A" in output_lines[0]
        assert "B" in output_lines[0]
        assert len(output_lines[0]) == 22
        # A should be at start, B at end since fill_space expands between them
        assert output_lines[0].strip().startswith("A")
        assert output_lines[0].strip().endswith("B")
    
    def test_alignment_without_fill_space(self, engine):
        """Test alignment works independently of fill_space."""
        # Pure center alignment without fill_space
        lines = ["{center}ABC"]
        result = engine.render_lines(lines, {})
        output_lines = result.split('\n')
        # Should be centered
        stripped = output_lines[0].strip()
        assert stripped == "ABC"
        left_pad = len(output_lines[0]) - len(output_lines[0].lstrip())
        right_pad = len(output_lines[0]) - len(output_lines[0].rstrip())
        assert abs(left_pad - right_pad) <= 1


class TestTemplateAPIEndpoints:
    """Tests for template API endpoints."""
    
    @pytest.fixture
    def client(self):
        from src.api_server import app
        from fastapi.testclient import TestClient
        return TestClient(app)
    
    def test_get_template_variables(self, client):
        """Test GET /templates/variables."""
        response = client.get("/templates/variables")
        
        assert response.status_code == 200
        data = response.json()
        assert "variables" in data
        assert "colors" in data
        assert "symbols" in data
    
    def test_validate_template_valid(self, client):
        """Test POST /templates/validate with valid template."""
        response = client.post("/templates/validate", json={
            "template": "{{weather.temperature}}"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
    
    def test_validate_template_invalid(self, client):
        """Test POST /templates/validate with invalid template."""
        response = client.post("/templates/validate", json={
            "template": "{{weather.temperature"  # Missing closing
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
    
    @patch('src.api_server.get_template_engine')
    def test_render_template(self, mock_get_engine, client):
        """Test POST /templates/render."""
        mock_engine = Mock()
        mock_engine.render.return_value = "72 degrees"
        mock_engine.render_lines.return_value = "72 degrees"
        mock_get_engine.return_value = mock_engine
        
        response = client.post("/templates/render", json={
            "template": "{{weather.temperature}} degrees"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "rendered" in data
    
    def test_render_template_empty_list(self, client):
        """Test POST /templates/render with empty list returns quickly."""
        response = client.post("/templates/render", json={
            "template": []
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "rendered" in data
        assert data["line_count"] == 6
        assert all(line == "" for line in data["lines"])
    
    def test_render_template_all_empty_strings(self, client):
        """Test POST /templates/render with all empty strings."""
        response = client.post("/templates/render", json={
            "template": ["", "", "", "", "", ""]
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "rendered" in data
        assert data["line_count"] == 6
        assert all(line == "" for line in data["lines"])
    
    def test_render_template_empty_string(self, client):
        """Test POST /templates/render with empty string."""
        response = client.post("/templates/render", json={
            "template": ""
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "rendered" in data
        assert data["line_count"] == 6
    
    def test_render_template_whitespace_only(self, client):
        """Test POST /templates/render with whitespace-only strings."""
        response = client.post("/templates/render", json={
            "template": ["   ", "  ", " ", "", "", ""]
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "rendered" in data
        # Should treat as empty and return 6 empty lines
        assert all(not line.strip() for line in data["lines"])


class TestColorWrapping:
    """Tests for color marker wrapping behavior."""
    
    @pytest.fixture
    def engine(self):
        return TemplateEngine()
    
    def test_color_blocks_wrap_correctly(self, engine):
        """Test that color blocks wrap correctly without splitting markers."""
        # Create a string of 120 color blocks (enough to wrap to 5+ lines)
        # Each {67} is 4 characters but 1 tile, so 120 tiles = 5.45 lines at 22 tiles/line
        color_string = "{67}" * 120
        
        # Wrap it to 5 lines
        wrapped = engine._word_wrap_tiles(color_string, first_width=22, subsequent_width=22, max_lines=5)
        
        # Verify we got 5 lines
        assert len(wrapped) == 5
        
        # Verify each line contains only valid color markers
        # No partial markers like {67 or }67} should exist
        for line in wrapped:
            # Count opening braces
            open_braces = line.count("{")
            # Count closing braces
            close_braces = line.count("}")
            # They should be equal (each marker has both)
            assert open_braces == close_braces, f"Line has mismatched braces: {line}"
            
            # Verify no partial markers (opening brace without closing, or closing without opening)
            # Check that every { is followed by a } before the next {
            i = 0
            while i < len(line):
                if line[i] == "{":
                    # Find the closing brace
                    closing = line.find("}", i)
                    assert closing != -1, f"Unclosed brace at position {i} in line: {line}"
                    # Verify the content between is valid (digits 63-70 or color name)
                    content = line[i + 1:closing]
                    assert content.isdigit() or content.lower() in COLOR_CODES or content.startswith("/"), \
                        f"Invalid color marker content: {content} in line: {line}"
                    i = closing + 1
                elif line[i] == "}":
                    # Should not have a closing brace without an opening
                    assert False, f"Closing brace without opening at position {i} in line: {line}"
                else:
                    i += 1
    
    def test_color_blocks_with_text_wrap(self, engine):
        """Test wrapping color blocks mixed with text."""
        # Mix of color blocks and text
        text = "{67}" * 30 + "HELLO" + "{66}" * 30
        
        wrapped = engine._word_wrap_tiles(text, first_width=22, subsequent_width=22, max_lines=5)
        
        # Verify all color markers are intact
        full_text = "".join(wrapped)
        # Count braces should match
        assert full_text.count("{") == full_text.count("}")
        
        # Verify no partial markers
        for line in wrapped:
            open_count = line.count("{")
            close_count = line.count("}")
            assert open_count == close_count, f"Line has mismatched braces: {line}"

