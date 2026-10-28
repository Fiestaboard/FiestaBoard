"""The upgrade scan for the split-flap extended-markup flip (plan Task 12).

When every board starts speaking extended markup, stored text changes what a
split-flap board draws in two ways, and the scan has to name both:

(a) legacy shortcuts whose rendering changes: ``{sun}`` was ``*`` and is now
    a yellow tile; ``{heart}`` was ``<3`` and is now one ``♥``. ``{fog}`` is
    the one shortcut whose split-flap rendering does not change.
(b) text that now parses as extended markup: board markup ``{red:``,
    ``{black/white:``, ``{icon:`` (already scanned) and the template
    authoring forms ``{{red:``, ``{{black/white:``, ``{{icon:``, which were
    variable lookups on a split-flap board before.

The scan runs at startup (one summary line, then one line per finding) and
on ``GET /system/markup-compat`` so users can see which pages changed.
"""

from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from src.markup_compat import MarkupFinding, scan_document, scan_text, shortcut_change, summarize


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("{sun} 72", [("legacy_shortcut", "{sun}")]),
        ("{SUN}", [("legacy_shortcut", "{SUN}")]),
        ("{heart}{x}", [("legacy_shortcut", "{heart}"), ("legacy_shortcut", "{x}")]),
        ("{storm} {check}", [("legacy_shortcut", "{storm}"), ("legacy_shortcut", "{check}")]),
        ("{{red:HOT}}", [("template_colour_span", "{{red:")]),
        ("{{63:HOT}}", [("template_colour_span", "{{63:")]),
        ("{{black/white:OPEN}}", [("template_block_span", "{{black/white:")]),
        ("{{icon:sun}}", [("template_icon", "{{icon:")]),
        ("{sun} {red:HOT}", [("legacy_shortcut", "{sun}"), ("colour_span", "{red:")]),
    ],
)
def test_scan_text_finds_shortcuts_and_template_forms(text, expected):
    assert scan_text(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "{fog}",  # draws "-" before and after
        "{{sun}}",  # a template variable, not a shortcut
        "{{weather.temperature}}",
        "{{red}}",  # a colour tile, unchanged
        "{sunny}",  # not a shortcut name
    ],
)
def test_scan_text_ignores_what_does_not_change(text):
    assert scan_text(text) == []


@pytest.mark.parametrize(
    ("name", "before", "after"),
    [
        ("sun", "*", "yellow tile"),
        ("star", "*", "yellow tile"),
        ("cloud", "O", "white tile"),
        ("rain", "/", "blue tile"),
        ("snow", "*", "violet tile"),
        ("storm", "!", "orange tile"),
        ("partly", "%", "white tile"),
        ("heart", "<3", "♥"),
        ("check", "+", "green tile"),
        ("x", "X", "red tile"),
    ],
)
def test_shortcut_change_names_what_a_split_flap_drew_and_draws(name, before, after):
    assert shortcut_change(name) == (before, after)


def test_findings_name_the_page_they_belong_to():
    pages = {
        "pages": [{"id": "p1", "name": "Plain", "template": ["HI"]}, {"id": "p2", "name": "Sky", "template": ["{sun}"]}]
    }
    assert scan_document("pages.json", pages) == [
        MarkupFinding("pages.json", "pages[1].template[0]", "legacy_shortcut", "{sun}", "{sun}", "p2", "Sky")
    ]


def test_summarize_counts_findings_by_kind_and_place():
    pages = {
        "pages": [
            {"id": "p1", "name": "Sky", "template": ["{sun} {heart}", "{red:HOT}"]},
            {"id": "p2", "name": "Ok", "template": ["{{icon:sun}}"]},
        ]
    }
    summary = summarize(scan_document("pages.json", pages))
    assert summary == {
        "total": 4,
        "places": 2,
        "counts": {"legacy_shortcut": 2, "colour_span": 1, "template_icon": 1},
    }


# --- startup -------------------------------------------------------------------------------


def _write_pages(pages: list[dict]) -> None:
    from src.paths import get_data_dir

    (get_data_dir() / "pages.json").write_text(json.dumps({"schema_version": 1, "pages": pages}), encoding="utf-8")


def test_startup_logs_a_summary_and_each_affected_page(caplog):
    from src import api_server

    _write_pages([{"id": "p1", "name": "Sky", "type": "template", "template": ["{sun} 72", "{{red:HOT}}"]}])
    with caplog.at_level(logging.INFO, logger="src.markup_compat"):
        api_server._run_startup_migrations()

    warnings = [
        r.getMessage() for r in caplog.records if r.levelno == logging.WARNING and r.name == "src.markup_compat"
    ]
    assert len(warnings) == 1
    assert "2 stored strings" in warnings[0] and "1 place" in warnings[0]
    assert "GET /system/markup-compat" in warnings[0]
    lines = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO and r.name == "src.markup_compat"]
    assert any("Sky" in line and "{sun}" in line and "yellow tile" in line for line in lines)


def test_startup_with_nothing_affected_logs_no_warning(caplog):
    from src import api_server

    _write_pages([{"id": "p1", "name": "Plain", "type": "template", "template": ["HELLO {red}"]}])
    with caplog.at_level(logging.INFO, logger="src.markup_compat"):
        api_server._run_startup_migrations()

    assert not [r for r in caplog.records if r.levelno >= logging.WARNING and r.name == "src.markup_compat"]


# --- GET /system/markup-compat ------------------------------------------------------------------


def test_the_endpoint_lists_what_changed_and_how():
    from src.api_server import app

    _write_pages([{"id": "p1", "name": "Sky", "type": "template", "template": ["{sun} {fog}", "{icon:moon}"]}])
    resp = TestClient(app).get("/system/markup-compat")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    assert body["counts"] == {"legacy_shortcut": 1, "icon": 1}
    assert body["findings"][0] == {
        "store": "pages.json",
        "location": "pages[0].template[0]",
        "kind": "legacy_shortcut",
        "marker": "{sun}",
        "text": "{sun} {fog}",
        "item_id": "p1",
        "item_name": "Sky",
        "before": "*",
        "after": "yellow tile",
    }
    assert body["findings"][1]["before"] is None and body["findings"][1]["after"] is None


def test_the_endpoint_answers_an_empty_report_for_plain_text():
    from src.api_server import app

    _write_pages([{"id": "p1", "name": "Plain", "type": "template", "template": ["HELLO"]}])
    body = TestClient(app).get("/system/markup-compat").json()
    assert body == {"total": 0, "places": 0, "counts": {}, "findings": []}
