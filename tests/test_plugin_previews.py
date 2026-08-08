"""Tests for the plugin board-preview contract (``teaser`` + ``previews``).

Covers the rules that make a preview renderable without a running plugin:
tile counting (colour markers occupy one flap, not four characters), device
geometry, and the overflow/unmappable-character cases that
``text_to_board_array`` would otherwise swallow silently.
"""

import pytest

from src.plugins.previews import (
    MAX_PREVIEW_NOTES_PER_AXIS,
    MAX_PREVIEWS,
    MAX_TEASER_TILES,
    BoardPreview,
    count_tiles,
    parse_previews,
    validate_previews,
    validate_teaser,
)


class TestCountTiles:
    """Tiles are flaps, not characters."""

    def test_plain_text_counts_characters(self):
        assert count_tiles("AAPL") == 4

    def test_empty_string_is_zero(self):
        assert count_tiles("") == 0

    def test_numeric_colour_marker_is_one_tile(self):
        assert count_tiles("{66}") == 1

    def test_named_colour_marker_is_one_tile(self):
        assert count_tiles("{green}") == 1

    def test_colour_marker_plus_text(self):
        # One green flap, then four letters.
        assert count_tiles("{66}AAPL") == 5

    def test_end_tags_occupy_no_tile(self):
        # {/green} is a formatting artefact, not a flap — matches
        # text_to_board_array, which skips end tags without advancing col_idx.
        assert count_tiles("{green}AAPL{/green}") == 5

    def test_bare_end_tag_occupies_no_tile(self):
        assert count_tiles("AB{/}") == 2

    def test_unclosed_brace_counts_as_literal_characters(self):
        # Not a valid marker, so each character is its own flap.
        assert count_tiles("{66") == 3

    def test_unknown_brace_content_counts_as_literal_characters(self):
        assert count_tiles("{nope}") == 6

    def test_spaces_count(self):
        assert count_tiles("A B") == 3


class TestValidateTeaser:
    """Teasers are literal, non-empty, and fit the narrowest board (15)."""

    def test_accepts_plain_teaser(self):
        assert validate_teaser("AAPL +1.88%") == []

    def test_accepts_exactly_max_tiles(self):
        assert count_tiles("A" * MAX_TEASER_TILES) == MAX_TEASER_TILES
        assert validate_teaser("A" * MAX_TEASER_TILES) == []

    def test_rejects_one_tile_over(self):
        errors = validate_teaser("A" * (MAX_TEASER_TILES + 1))
        assert len(errors) == 1
        assert "16" in errors[0] and str(MAX_TEASER_TILES) in errors[0]

    def test_colour_marker_costs_one_tile_not_four(self):
        # 15 characters of markup, but only 12 flaps — must pass.
        teaser = "{66}AAPL +1.88%"
        assert count_tiles(teaser) == 12
        assert validate_teaser(teaser) == []

    def test_rejects_empty(self):
        errors = validate_teaser("")
        assert len(errors) == 1
        assert "empty" in errors[0].lower()

    def test_rejects_whitespace_only(self):
        errors = validate_teaser("   ")
        assert len(errors) == 1
        assert "empty" in errors[0].lower()

    def test_rejects_non_string(self):
        errors = validate_teaser(["AAPL"])
        assert len(errors) == 1
        assert "string" in errors[0].lower()

    def test_rejects_template_variable(self):
        # There is no data to resolve against at render time.
        errors = validate_teaser("{{stocks.symbol}}")
        assert len(errors) == 1
        assert "literal" in errors[0].lower()

    def test_rejects_newline(self):
        errors = validate_teaser("AAPL\n+1.88%")
        assert len(errors) == 1
        assert "single line" in errors[0].lower()

    def test_rejects_unmappable_character(self):
        errors = validate_teaser("AAPL ☃")
        assert len(errors) == 1
        assert "☃" in errors[0]

    def test_lowercase_is_accepted(self):
        # The board uppercases on render; authors should not have to shout.
        assert validate_teaser("aapl +1.88%") == []


class TestValidatePreviewGeometry:
    """Rows are checked against resolved device dimensions."""

    def _flagship(self, rows):
        return [{"device_type": "flagship", "rows": rows}]

    def test_accepts_full_flagship(self):
        assert validate_previews(self._flagship(["A" * 22] * 6)) == []

    def test_accepts_fewer_rows_than_device(self):
        # Short previews are padded with blanks, not rejected.
        assert validate_previews(self._flagship(["HELLO"])) == []

    def test_rejects_too_many_rows(self):
        errors = validate_previews(self._flagship(["A"] * 7))
        assert len(errors) == 1
        assert "7" in errors[0] and "6" in errors[0]

    def test_rejects_row_wider_than_device(self):
        errors = validate_previews(self._flagship(["A" * 23]))
        assert len(errors) == 1
        assert "23" in errors[0] and "22" in errors[0]

    def test_accepts_note_geometry(self):
        assert validate_previews([{"device_type": "note", "rows": ["A" * 15] * 3}]) == []

    def test_rejects_note_row_over_15(self):
        errors = validate_previews([{"device_type": "note", "rows": ["A" * 16]}])
        assert len(errors) == 1
        assert "16" in errors[0] and "15" in errors[0]

    def test_accepts_note_array_geometry(self):
        preview = {
            "device_type": "note_array",
            "notes_wide": 2,
            "notes_tall": 1,
            "rows": ["A" * 30] * 3,
        }
        assert validate_previews([preview]) == []

    def test_rejects_note_array_row_over_resolved_width(self):
        preview = {
            "device_type": "note_array",
            "notes_wide": 2,
            "notes_tall": 1,
            "rows": ["A" * 31],
        }
        errors = validate_previews([preview])
        assert len(errors) == 1
        assert "31" in errors[0] and "30" in errors[0]

    def test_colour_markers_counted_as_one_column_each(self):
        # 22 markers = 22 flaps = exactly a flagship row, despite being
        # 88 characters of source text.
        row = "{66}" * 22
        assert validate_previews(self._flagship([row])) == []

    def test_colour_markers_overflow_detected(self):
        errors = validate_previews(self._flagship(["{66}" * 23]))
        assert len(errors) == 1
        assert "23" in errors[0]

    def test_rejects_unmappable_character_in_row(self):
        errors = validate_previews(self._flagship(["HELLO ☃"]))
        assert len(errors) == 1
        assert "☃" in errors[0]


class TestValidatePreviewStructure:
    """Shape, caps, and required fields."""

    def test_rejects_non_list(self):
        errors = validate_previews({"device_type": "flagship"})
        assert len(errors) == 1
        assert "array" in errors[0].lower()

    def test_rejects_empty_list(self):
        errors = validate_previews([])
        assert len(errors) == 1
        assert "at least one" in errors[0].lower()

    def test_rejects_entry_without_rows(self):
        errors = validate_previews([{"device_type": "flagship"}])
        assert len(errors) == 1
        assert "rows" in errors[0]

    def test_rejects_non_string_row(self):
        errors = validate_previews([{"device_type": "flagship", "rows": [42]}])
        assert len(errors) == 1
        assert "string" in errors[0].lower()

    def test_rejects_unknown_device_type(self):
        errors = validate_previews([{"device_type": "billboard", "rows": ["HI"]}])
        assert len(errors) == 1
        assert "billboard" in errors[0]

    def test_defaults_device_type_to_flagship(self):
        assert validate_previews([{"rows": ["A" * 22]}]) == []

    def test_rejects_more_than_max_previews(self):
        previews = [{"device_type": "note", "rows": ["HI"]} for _ in range(MAX_PREVIEWS + 1)]
        errors = validate_previews(previews)
        assert len(errors) == 1
        assert str(MAX_PREVIEWS) in errors[0]

    def test_accepts_exactly_max_previews(self):
        previews = [{"device_type": "note", "rows": ["HI"]} for _ in range(MAX_PREVIEWS)]
        assert validate_previews(previews) == []

    def test_rejects_note_array_beyond_preview_cap(self):
        preview = {
            "device_type": "note_array",
            "notes_wide": MAX_PREVIEW_NOTES_PER_AXIS + 1,
            "notes_tall": 1,
            "rows": ["HI"],
        }
        errors = validate_previews([preview])
        assert any(str(MAX_PREVIEW_NOTES_PER_AXIS) in e for e in errors)

    def test_rejects_zero_notes(self):
        preview = {"device_type": "note_array", "notes_wide": 0, "notes_tall": 1, "rows": ["HI"]}
        errors = validate_previews([preview])
        assert len(errors) >= 1

    def test_errors_identify_the_offending_entry(self):
        previews = [
            {"device_type": "flagship", "rows": ["OK"]},
            {"device_type": "flagship", "rows": ["A" * 99]},
        ]
        errors = validate_previews(previews)
        assert len(errors) == 1
        assert "previews[1]" in errors[0]


class TestParsePreviews:
    """Parsing into BoardPreview objects."""

    def test_parses_flagship(self):
        parsed = parse_previews([{"device_type": "flagship", "rows": ["HI"]}])
        assert len(parsed) == 1
        assert isinstance(parsed[0], BoardPreview)
        assert parsed[0].device_type == "flagship"
        assert parsed[0].rows == ["HI"]

    def test_resolves_dimensions(self):
        parsed = parse_previews([{"device_type": "note", "rows": ["HI"]}])
        assert parsed[0].dimensions.rows == 3
        assert parsed[0].dimensions.cols == 15

    def test_resolves_note_array_dimensions(self):
        parsed = parse_previews([{"device_type": "note_array", "notes_wide": 2, "notes_tall": 2, "rows": ["HI"]}])
        assert parsed[0].dimensions.rows == 6
        assert parsed[0].dimensions.cols == 30

    def test_default_label_describes_shape(self):
        parsed = parse_previews([{"device_type": "flagship", "rows": ["HI"]}])
        assert parsed[0].label == "Flagship"

    def test_default_label_for_note_array_includes_grid(self):
        parsed = parse_previews([{"device_type": "note_array", "notes_wide": 2, "notes_tall": 1, "rows": ["HI"]}])
        assert "2" in parsed[0].label and "1" in parsed[0].label

    def test_explicit_label_wins(self):
        parsed = parse_previews([{"device_type": "flagship", "rows": ["HI"], "label": "Morning"}])
        assert parsed[0].label == "Morning"

    def test_ignores_malformed_entries(self):
        # Parsing is lenient; validate_previews is what rejects.
        parsed = parse_previews(["nonsense", {"device_type": "note", "rows": ["HI"]}])
        assert len(parsed) == 1

    def test_parses_empty_to_empty_list(self):
        assert parse_previews(None) == []
        assert parse_previews([]) == []


class TestPreviewToGrid:
    """A preview must survive the same path the hardware uses."""

    @pytest.mark.parametrize(
        ("device_type", "kwargs", "rows", "cols"),
        [
            ("flagship", {}, 6, 22),
            ("note", {}, 3, 15),
            ("note_array", {"notes_wide": 2, "notes_tall": 1}, 3, 30),
        ],
    )
    def test_grid_matches_declared_geometry(self, device_type, kwargs, rows, cols):
        preview = BoardPreview(rows=["HELLO"], device_type=device_type, **kwargs)
        grid = preview.to_grid()
        assert len(grid) == rows
        assert all(len(row) == cols for row in grid)

    def test_short_preview_is_padded_with_blanks(self):
        preview = BoardPreview(rows=["HI"], device_type="flagship")
        grid = preview.to_grid()
        assert len(grid) == 6
        # Rows beyond the supplied content are all blank.
        assert all(cell == 0 for row in grid[1:] for cell in row)

    def test_colour_marker_becomes_a_colour_code(self):
        preview = BoardPreview(rows=["{66}"], device_type="flagship")
        assert preview.to_grid()[0][0] == 66
