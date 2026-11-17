"""Origins follow the actual text operations, including markup layout."""

from __future__ import annotations

import importlib
import importlib.util
import re

import pytest

from src.markup import split_rows, take_tiles, wrap_line


@pytest.fixture
def sm():
    assert importlib.util.find_spec("src.templates.source_map") is not None, "source-map helpers are not implemented"
    return importlib.import_module("src.templates.source_map")


def records(result):
    """Resolve the wire IDs without deriving expected origins."""
    return [[None if cell is None else result["sources"][cell] for cell in row] for row in result["cells"]]


def test_identical_values_keep_distinct_authored_atoms(sm):
    tracker = sm.SourceTracker()
    text = sm.concat(
        [
            tracker.mapped("A", sm.Source(1, 0, 12, "variable")),
            tracker.mapped("A", sm.Source(1, 13, 23, "formula")),
        ]
    )
    result = tracker.to_json(text, rows=1, cols=3)
    assert result == {
        "rows": 1,
        "cols": 3,
        "sources": [
            {"line": 1, "start": 0, "end": 12, "kind": "variable"},
            {"line": 1, "start": 13, "end": 23, "kind": "formula"},
        ],
        "cells": [[0, 1, None]],
    }


def test_literal_offsets_survive_slice_concatenation_and_unicode(sm):
    tracker = sm.SourceTracker()
    text = tracker.source("x😀AB", line=3, offset=7)
    result = tracker.to_json(sm.concat([" ", text[1:3], text[-1]]), rows=1, cols=4)
    assert records(result) == [
        [
            None,
            {"line": 3, "start": 8, "end": 9, "kind": "literal"},
            {"line": 3, "start": 9, "end": 10, "kind": "literal"},
            {"line": 3, "start": 10, "end": 11, "kind": "literal"},
        ]
    ]


def test_regex_substitution_keeps_untouched_literals_and_atom_output(sm):
    tracker = sm.SourceTracker()
    template = tracker.source("L {{x.y}} R", line=2)
    text = sm.sub(
        re.compile(r"\{\{x\.y\}\}"), lambda _match: tracker.mapped("AA", sm.Source(2, 2, 9, "variable")), template
    )
    assert text == "L AA R"
    assert sm.origin_at(text, 0) == sm.Source(2, 0, 1, "literal")
    assert sm.origin_at(text, 2) == sm.origin_at(text, 3) == sm.Source(2, 2, 9, "variable")
    assert sm.origin_at(text, 5) == sm.Source(2, 10, 11, "literal")


def test_fill_repetition_is_authored_but_layout_padding_is_not(sm):
    tracker = sm.SourceTracker()
    fill = tracker.mapped("{63}", sm.Source(1, 1, 15, "fill"))
    text = sm.concat([" ", fill * 3, " "])
    result = tracker.to_json(text, rows=1, cols=5)
    assert result["sources"] == [{"line": 1, "start": 1, "end": 15, "kind": "fill"}]
    assert result["cells"] == [[None, 0, 0, 0, None]]


def test_nested_markup_serialization_keeps_inner_character_origins(sm):
    tracker = sm.SourceTracker()
    text = tracker.source("{red:A{blue:B}C}", line=1)
    head, tail = take_tiles(text, 2)
    assert (head, tail) == ("{red:A{blue:B}}", "{red:C}")
    result = tracker.to_json(sm.concat([head, "\n", tail]), rows=2, cols=2)
    assert records(result) == [
        [
            {"line": 1, "start": 5, "end": 6, "kind": "literal"},
            {"line": 1, "start": 12, "end": 13, "kind": "literal"},
        ],
        [
            {"line": 1, "start": 14, "end": 15, "kind": "literal"},
            None,
        ],
    ]


def test_extended_row_split_keeps_the_formula_origin_on_every_row(sm):
    tracker = sm.SourceTracker()
    text = sm.concat(["{red:", tracker.mapped("AA\nBB", sm.Source(1, 6, 28, "formula")), "}"])
    rows = split_rows(text)
    assert rows == ["{red:AA}", "{red:BB}"]
    result = tracker.to_json(sm.concat([rows[0], "\n", rows[1]]), rows=2, cols=3)
    assert result["cells"] == [[0, 0, None], [0, 0, None]]
    assert result["sources"] == [{"line": 1, "start": 6, "end": 28, "kind": "formula"}]


def test_extended_wrap_keeps_origins_across_reopened_spans(sm):
    tracker = sm.SourceTracker()
    text = tracker.source("{red:AB CD EF}", line=1)
    rows = wrap_line(text, 3)
    assert rows == ["{red:AB}", "{red:CD}", "{red:EF}"]
    result = tracker.to_json(sm.concat([rows[0], "\n", rows[1], "\n", rows[2]]), rows=3, cols=3)
    assert [[None if cell is None else cell["start"] for cell in row] for row in records(result)] == [
        [5, 6, None],
        [8, 9, None],
        [11, 12, None],
    ]


def test_wrap_joiner_retains_the_first_whitespace_origin(sm):
    tracker = sm.SourceTracker()
    text = tracker.source("{red:A \t B}", line=1)
    (row,) = wrap_line(text, 5)
    assert row == "{red:A B}"
    result = tracker.to_json(row, rows=1, cols=3)
    assert [cell["start"] for cell in records(result)[0]] == [5, 6, 9]


def test_unrepresentable_markup_cut_keeps_the_original_tail_origins(sm):
    tracker = sm.SourceTracker()
    text = tracker.source("X{red:A{foo}B}", line=1)
    head, tail = take_tiles(text, 3)
    assert (head, tail) == ("X", "{red:A{foo}B}")
    assert sm.origin_at(head, 0) == sm.Source(1, 0, 1, "literal")
    assert sm.origin_at(tail, 5) == sm.Source(1, 6, 7, "literal")


def test_extended_wrap_fallback_keeps_raw_character_origins(sm):
    tracker = sm.SourceTracker()
    text = tracker.source("{red:A{foo}B}", line=1)
    rows = wrap_line(text, 3)
    assert rows == ["{re", "d:A", "{fo", "o}B", "}"]
    assert [sm.origin_at(row, 0).start for row in rows] == [0, 3, 6, 9, 12]


def test_split_replace_translate_and_strip_keep_source_offsets(sm):
    tracker = sm.SourceTracker()
    text = tracker.source("  AB\nCD  ", line=4, offset=10)
    first, second = text.strip().split("\n")
    changed = first.translate(str.maketrans({"A": "XX", "B": None}))
    changed = sm.concat([changed, second.replace("C", "Z")])
    assert changed == "XXZD"
    assert [sm.origin_at(changed, index).start for index in range(4)] == [12, 12, 15, 16]


@pytest.mark.parametrize("table, expected", [({}, "A" * 10_000), ({ord("A"): ord("B")}, "B" * 10_000)])
def test_translation_keeps_one_to_one_literal_runs_compact(sm, table, expected):
    tracker = sm.SourceTracker()
    text = tracker.source("A" * 10_000, line=2, offset=7)
    translated = text.translate(table)

    assert translated == expected
    assert len(translated.runs) == 1
    assert sm.origin_at(translated, 0) == sm.Source(2, 7, 8, "literal")
    assert sm.origin_at(translated, 9_999) == sm.Source(2, 10_006, 10_007, "literal")


def test_sparse_translation_preserves_compact_unchanged_regions(sm):
    tracker = sm.SourceTracker()
    text = tracker.source("A" * 1_000 + "\x01" + "B" * 1_000 + "\x02" + "C" * 1_000, line=3, offset=10)
    translated = text.translate({1: "XY", 2: None})

    assert translated == "A" * 1_000 + "XY" + "B" * 1_000 + "C" * 1_000
    assert len(translated.runs) == 4
    assert [sm.origin_at(translated, at).start for at in (999, 1_000, 1_001, 1_002, 2_001, 2_002, 3_001)] == [
        1_009,
        1_010,
        1_010,
        1_011,
        2_010,
        2_012,
        3_011,
    ]


def test_interning_is_only_for_visible_cells_and_padding_is_null(sm):
    tracker = sm.SourceTracker()
    hidden = tracker.mapped("SECRET", sm.Source(1, 0, 11, "variable"))
    result = tracker.to_json(sm.concat([" ", hidden]), rows=1, cols=1)
    assert result == {"rows": 1, "cols": 1, "sources": [], "cells": [[None]]}


def test_tracking_limit_stops_mapping_without_changing_text(sm):
    tracker = sm.SourceTracker(limit=5)
    first = tracker.source("ABC", line=1)
    text = sm.concat([first, "DEF"])
    assert text == "ABCDEF"
    assert tracker.limited is True
    assert tracker.to_json(text, rows=1, cols=6) is None
    assert tracker.mapped("LATER", sm.Source(2, 0, 4, "formula")) == "LATER"


def test_long_atom_uses_one_source_run_and_shared_budget(sm):
    tracker = sm.SourceTracker()
    text = tracker.mapped("A" * 20_000, sm.Source(1, 0, 20, "formula"))
    assert len(text.runs) == 1
    assert tracker.used == 20_000
    assert sm.origin_at(text, 19_999) == sm.Source(1, 0, 20, "formula")


def test_plain_string_helpers_do_not_start_tracking(sm):
    assert type(sm.concat(["A", "B"])) is str
    assert type(sm.sub(re.compile("A"), "Z", "AB")) is str
    assert sm.origin_at("AB", 0) is None


def test_separate_trackers_do_not_share_sources_or_limit_state(sm):
    first, second = sm.SourceTracker(limit=1), sm.SourceTracker()
    first.source("AA", line=9)
    text = second.mapped("A", sm.Source(1, 0, 8, "variable"))
    assert first.limited is True
    assert second.limited is False
    assert second.to_json(text, rows=1, cols=1)["sources"] == [
        {"line": 1, "start": 0, "end": 8, "kind": "variable"},
    ]
