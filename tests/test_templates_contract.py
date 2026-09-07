"""Value-level contract goldens for the /templates API (Phase 2 §2, slice 8).

The template endpoints are what the page editor is built on: the variable
catalog drives autocomplete, the validator drives the inline error markers,
and ``render``/``render/live`` drive the preview and the live-edit send. A
shape golden cannot see a colour code that changed from 63 to 64, a filter
that vanished from the advertised list, or a render that stopped padding
lines to the device width — so these are pinned as values.

Recorded against the UNCONVERTED trunk, then re-pinned by the conventions pass
in this same PR. What deliberately changed, and nothing else:

* A body missing ``template`` answers **422** (was 400 ``{"detail": "template
  parameter required"}``) on ``/templates/validate``, ``/templates/render``
  and ``/templates/render/live``. The hand-rolled ``if "template" not in
  request`` check is now a required Pydantic field, so FastAPI rejects the
  body before the handler runs.

Every other assertion — the advertised colours/symbols/filters, the
validator's verdicts and messages, the rendered strings and their padding,
the board-not-found 404, the render-failure 400 — is unchanged from the
pre-conversion recording. None was weakened.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(_isolated_data_dir):
    from src.api_server import app

    return TestClient(app)


@pytest.fixture
def exploding_engine(monkeypatch):
    """Make the render path raise.

    Patched on ``TemplateEngine`` itself rather than on an accessor bound in
    some module, so the stub survives the handlers moving out of
    ``src.api_server`` into ``src/templates/routes.py``.
    """
    from src.templates.engine import TemplateEngine

    def _boom(self, *args, **kwargs):
        raise RuntimeError("engine exploded")

    monkeypatch.setattr(TemplateEngine, "render", _boom)
    monkeypatch.setattr(TemplateEngine, "render_lines", _boom)


# ---------------------------------------------------------------------------
# GET /templates/variables
# ---------------------------------------------------------------------------


def test_variables_advertises_the_board_colour_codes_by_value(client):
    """These integers are flap codes. A wrong one paints the wrong colour."""
    body = client.get("/templates/variables").json()
    assert body["colors"] == {
        "red": 63,
        "orange": 64,
        "yellow": 65,
        "green": 66,
        "blue": 67,
        "violet": 68,
        "white": 69,
        "black": 70,
    }


def test_variables_advertises_the_symbol_and_filter_catalogs(client):
    body = client.get("/templates/variables").json()
    assert body["symbols"] == [
        "sun",
        "star",
        "cloud",
        "rain",
        "snow",
        "storm",
        "fog",
        "partly",
        "heart",
        "check",
        "x",
    ]
    assert body["filters"] == ["pad:N", "truncate:N", "wrap"]


def test_variables_documents_the_fill_space_syntax_the_editor_inserts(client):
    body = client.get("/templates/variables").json()
    assert body["formatting"]["fill_space"]["syntax"] == "{{fill_space}}"
    assert body["formatting"]["fill_space_repeat"]["syntax"] == "{{fill_space_repeat:pattern}}"
    assert body["syntax_examples"]["variable"] == "{{weather.temperature}}"
    assert body["syntax_examples"]["color_code"] == "{63}"
    assert body["syntax_examples"]["fill_space_three_columns"] == "A{{fill_space}}B{{fill_space}}C"


def test_variables_carries_the_plugin_catalogs_even_when_empty(client):
    body = client.get("/templates/variables").json()
    for key in ("variables", "max_lengths", "variable_metadata", "variable_groups"):
        assert key in body, key
        assert isinstance(body[key], dict)


# ---------------------------------------------------------------------------
# POST /templates/validate
# ---------------------------------------------------------------------------


def test_validate_without_a_template_is_rejected(client):
    # RE-PINNED: 422 (Pydantic) replaces the hand-rolled 400
    # {"detail": "template parameter required"}. See the module docstring.
    assert client.post("/templates/validate", json={}).status_code == 422


def test_validate_accepts_a_plain_template_with_no_errors(client):
    response = client.post("/templates/validate", json={"template": "HELLO"})
    assert response.status_code == 200
    assert response.json() == {"valid": True, "errors": []}


def test_validate_reports_an_unknown_source_at_its_position(client):
    response = client.post("/templates/validate", json={"template": "{{weather.nope}}"})
    assert response.status_code == 200
    assert response.json() == {
        "valid": False,
        "errors": [{"line": 1, "column": 0, "message": "Unknown source: weather"}],
    }


def test_validate_reports_mismatched_braces(client):
    response = client.post("/templates/validate", json={"template": "{{ unclosed"})
    assert response.status_code == 200
    assert response.json() == {
        "valid": False,
        "errors": [{"line": 1, "column": 0, "message": "Mismatched variable braces {{}}"}],
    }


def test_validate_joins_a_list_template_into_lines(client):
    response = client.post("/templates/validate", json={"template": ["HELLO", "{{ unclosed"]})
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert body["errors"][0]["line"] == 2, "the second list entry is line 2, not line 1"


# ---------------------------------------------------------------------------
# GET /templates/formula-functions
# ---------------------------------------------------------------------------


def test_formula_functions_describes_each_function_for_the_picker(client):
    response = client.get("/templates/formula-functions")
    assert response.status_code == 200
    functions = response.json()["functions"]
    assert functions["IF"] == {
        "category": "logic",
        "signature": "IF(cond, then[, else])",
        "summary": "Conditional value",
    }
    assert functions["ROUND"]["category"] == "math"
    assert functions["ROUND"]["signature"] == "ROUND(x[, n])"


# ---------------------------------------------------------------------------
# POST /templates/render
# ---------------------------------------------------------------------------


def test_render_without_a_template_is_rejected(client):
    # RE-PINNED: see the module docstring.
    assert client.post("/templates/render", json={}).status_code == 422


def test_render_of_an_empty_list_short_circuits_to_a_blank_flagship(client):
    response = client.post("/templates/render", json={"template": []})
    assert response.status_code == 200
    assert response.json() == {"rendered": "\n\n\n\n\n", "lines": ["", "", "", "", "", ""], "line_count": 6}


def test_render_of_a_plain_string_returns_it_unpadded(client):
    response = client.post("/templates/render", json={"template": "HELLO"})
    assert response.status_code == 200
    assert response.json() == {"rendered": "HELLO", "lines": ["HELLO"], "line_count": 1}


def test_render_of_lines_pads_to_the_requested_device_width(client):
    response = client.post(
        "/templates/render",
        json={"template": ["HI", "THERE"], "device_type": "note"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["lines"] == ["HI             ", "THERE          ", "               "]
    assert body["line_count"] == 3, "a Note is 3 rows; the third line is padded in"
    assert body["rendered"] == "\n".join(body["lines"])


def test_render_surfaces_an_engine_failure_as_a_400(client, exploding_engine):
    response = client.post("/templates/render", json={"template": "HELLO"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Template rendering failed: engine exploded"


# ---------------------------------------------------------------------------
# POST /templates/render/live
# ---------------------------------------------------------------------------


def test_render_live_without_a_template_is_rejected(client):
    # RE-PINNED: see the module docstring.
    assert client.post("/templates/render/live", json={}).status_code == 422


def test_render_live_404s_an_unknown_board_rather_than_rendering_into_the_void(client):
    response = client.post("/templates/render/live", json={"template": "HI", "board_id": "no-such-board"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Board not found: no-such-board"


def test_render_live_returns_the_render_and_says_it_did_not_reach_a_board(client):
    response = client.post("/templates/render/live", json={"template": "HI"})
    assert response.status_code == 200
    body = response.json()
    assert body["rendered"] == "HI"
    assert body["lines"] == ["HI"]
    assert body["line_count"] == 1
    assert body["sent_to_board"] is False, "the default board has no credentials in a test data dir"
    assert body["paused"] is False
    assert isinstance(body["board_id"], str), "it echoes the board it targeted"
