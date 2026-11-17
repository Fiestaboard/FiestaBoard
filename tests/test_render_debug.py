"""H7 editor contract: actual formula traces and authored cell origins."""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from src.templates.engine import TemplateEngine

CTX = {"demo": {"word": "A", "words": "ONE TWO THREE FOUR FIVE SIX", "items": ["A", "B", "C", "D"]}}


@pytest.fixture
def client(_isolated_data_dir, monkeypatch):
    from src.api_server import app

    monkeypatch.setattr(TemplateEngine, "_build_context", lambda self, *a, **k: dict(CTX))
    return TestClient(app)


def render(client, template, debug=None, **kwargs):
    request = {"template": template, **kwargs}
    if debug is not None:
        request["debug"] = debug
    response = client.post("/templates/render", json=request)
    assert response.status_code == 200, response.text
    return response.json()


def origin(body, row, col):
    mapping = body["debug"]["source_map"]
    index = mapping["cells"][row][col]
    return None if index is None else mapping["sources"][index]


def test_debug_does_not_add_keys_to_default_response(client):
    assert set(render(client, ["HELLO"])) == {"rendered", "lines", "line_count"}


def test_trace_selects_one_formula_and_implies_h5(client):
    body = render(client, ["{{= 2+3 }} {{= 7*2 }}"], {"trace": {"line": 1, "start": 11}})
    trace = body["debug"]["trace"]
    assert (trace["line"], trace["start"], trace["value"]) == (1, 11, "14")
    assert trace["source"] == "7*2"
    assert trace["events"][0]["value"] == "14"
    assert [f["value"] for f in body["diagnostics"]["formulas"]] == ["5", "14"]
    assert body["debug"]["source_map"] is None
    assert body["debug"]["source_map_status"] == "not_requested"


def test_identical_output_cells_keep_distinct_authored_atoms(client):
    body = render(client, ['A{{demo.word}}A{{= "A" }}'], {"source_map": True})
    assert body["lines"][0] == "AAAA" + " " * 18
    assert [origin(body, 0, col) for col in range(4)] == [
        {"line": 1, "start": 0, "end": 1, "kind": "literal"},
        {"line": 1, "start": 1, "end": 14, "kind": "variable"},
        {"line": 1, "start": 14, "end": 15, "kind": "literal"},
        {"line": 1, "start": 15, "end": 25, "kind": "formula"},
    ]
    assert all(origin(body, 0, col) is None for col in range(4, 22))


def test_alignment_padding_has_no_authored_source(client):
    body = render(client, ["ABC"], {"source_map": True}, line_metadata=[{"alignment": "right"}])
    assert body["lines"][0] == " " * 19 + "ABC"
    assert all(origin(body, 0, col) is None for col in range(19))
    assert origin(body, 0, 19) == {"line": 1, "start": 0, "end": 1, "kind": "literal"}


def test_fill_cells_point_to_fill_directive(client):
    line = "A{{fill_space_repeat:-}}B"
    body = render(client, [line], {"source_map": True})
    assert body["lines"][0] == "A" + "-" * 20 + "B"
    for col in range(1, 21):
        source = origin(body, 0, col)
        assert source["kind"] == "fill"
        assert line[source["start"] : source["end"]] == "{{fill_space_repeat:-}}"


def test_nested_rich_markup_retains_inner_literal_and_variable_origins(client):
    body = render(client, ["{{red:A{{demo.word}}}}"], {"source_map": True})
    assert origin(body, 0, 0) == {"line": 1, "start": 6, "end": 7, "kind": "literal"}
    assert origin(body, 0, 1) == {"line": 1, "start": 7, "end": 20, "kind": "variable"}
    assert origin(body, 0, 2) is None


def test_variable_wrap_attributes_each_output_row_and_preserves_footer(client):
    line = "{{demo.words|wrap}}"
    body = render(client, [line, "", "END"], {"source_map": True}, device_type="note")
    assert body["lines"] == ["ONE TWO THREE  ", "FOUR FIVE SIX  ", "END            "]
    for row in (0, 1):
        for col in range(13):
            assert origin(body, row, col) == {"line": 1, "start": 0, "end": len(line), "kind": "variable"}
    assert origin(body, 2, 0)["line"] == 3


def test_foreach_cells_point_to_formula_and_stop_before_footer(client):
    line = "{{= FOREACH(demo.items, item) }}"
    body = render(client, [line, "", "END"], {"source_map": True, "trace": {"line": 1, "start": 0}}, device_type="note")
    assert body["lines"] == ["A              ", "B              ", "END            "]
    assert origin(body, 0, 0) == origin(body, 1, 0) == {"line": 1, "start": 0, "end": len(line), "kind": "formula"}
    assert origin(body, 2, 0)["line"] == 3
    assert body["diagnostics"]["lines"][0]["clip"] == "stopped_by_line"
    assert body["debug"]["trace"]["value"] == "A\nB\nC\nD"


@pytest.mark.parametrize("template", [[], [""], ["   "]])
def test_blank_template_returns_requested_board_map(client, template):
    body = render(client, template, {"source_map": True}, device_type="note")
    mapping = body["debug"]["source_map"]
    assert (mapping["rows"], mapping["cols"]) == (3, 15)
    assert len(mapping["cells"]) == 3
    assert all(len(row) == 15 for row in mapping["cells"])
    assert all(cell is None for row in mapping["cells"] for cell in row)
    assert body["debug"]["source_map_status"] == "complete"


def test_preview_trace_uses_sample_missing_and_pinned_clock(client):
    line = '{{= DEFAULT(missing.value, "OK") & ":" & demo.word & ":" & YEAR(NOW()) }}'
    body = render(
        client,
        [line],
        {"trace": {"line": 1, "start": 0}, "source_map": True},
        preview={"values": {"demo.word": "S"}, "missing": ["missing"], "at": f"{datetime.now().year}-01-02T03:04:00"},
    )
    expected = f"OK:S:{datetime.now().year}"
    assert body["debug"]["trace"]["value"] == expected
    assert body["lines"][0].strip() == expected
    assert render(client, ["{{demo.word}}"])["lines"][0].strip() == "A"


def test_debug_evaluates_selected_formula_once_even_with_wrap_measure(client, monkeypatch):
    from src.templates import expressions

    calls = 0
    real = expressions._eval_node_unbounded

    def count(node, context):
        nonlocal calls
        if isinstance(node, expressions._Call) and node.name == "REPT":
            calls += 1
        return real(node, context)

    monkeypatch.setattr(expressions, "_eval_node_unbounded", count)
    body = render(client, ['{{= REPT("A", 30) }}'], {"trace": {"line": 1, "start": 0}}, line_metadata=[{"wrap": True}])
    assert body["debug"]["trace"]["value"] == "A" * 30
    assert calls == 1


def test_syntax_error_trace_keeps_position_message_and_empty_events(client):
    body = render(client, ["{{= 1 + }}"], {"trace": {"line": 1, "start": 0}})
    trace = body["debug"]["trace"]
    assert trace["error"] == "#SYNTAX"
    assert isinstance(trace["error_at"], int)
    assert trace["message"]
    assert trace["events"] == []


@pytest.mark.parametrize(
    "payload",
    [
        {"template": "ABC", "debug": {"source_map": True}},
        {"template": ["ABC"], "debug": {"trace": {"line": 1, "start": 0}}},
        {"template": ["{{= 1 }}"], "debug": {"trace": {"line": 0, "start": 0}}},
        {"template": ["{{= 1 }}"], "debug": {"trace": {"line": 1, "start": -1}}},
        {"template": ["ABC"], "debug": {"unknown": True}},
        {"template": ["A"] * 65, "debug": {"source_map": True}},
        {"template": ["A" * 16385], "debug": {"source_map": True}},
        {"template": ["A"], "device_type": "panel", "grid_rows": 96, "grid_cols": 128, "debug": {"source_map": True}},
        {"template": ["{{= " + "1+" * 2100 + "1 }}"], "debug": {"trace": {"line": 1, "start": 0}}},
        {
            "template": ["ABC"],
            "debug": {"source_map": True},
            "canvases": [
                {"id": "test", "area": {"row": 1, "col": 1, "rows": 1, "cols": 2}, "content": {"background": "#ff0000"}}
            ],
        },
    ],
)
def test_invalid_or_oversized_debug_rejected_before_context_fetch(client, monkeypatch, payload):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid debug request fetched context")

    monkeypatch.setattr(TemplateEngine, "_build_context", forbidden)
    response = client.post("/templates/render", json=payload)
    assert response.status_code == 422, response.text


def test_live_render_rejects_debug_before_sending(client):
    response = client.post("/templates/render/live", json={"template": ["ABC"], "debug": {"source_map": True}})
    assert response.status_code == 422, response.text


def test_provenance_budget_exhaustion_keeps_trace_and_render_consistent(client, monkeypatch):
    from src.templates import debug
    from src.templates.source_map import SourceTracker

    monkeypatch.setattr(debug, "SourceTracker", lambda: SourceTracker(limit=8))
    body = render(
        client,
        ['{{= REPT("A", 30) }}'],
        {"source_map": True, "trace": {"line": 1, "start": 0}},
        line_metadata=[{"wrap": True}],
    )
    assert body["debug"]["source_map"] is None
    assert body["debug"]["source_map_status"] == "limit"
    assert body["debug"]["trace"]["value"] == "A" * 30
    assert body["lines"][:2] == ["A" * 22, "A" * 8 + " " * 14]


def test_standalone_raw_markup_cells_point_to_entire_atom(client):
    body = render(client, ["{66}{icon:sun}"], {"source_map": True})
    assert origin(body, 0, 0) == {"line": 1, "start": 0, "end": 4, "kind": "markup"}
    assert origin(body, 0, 1) == {"line": 1, "start": 4, "end": 14, "kind": "markup"}


def test_debug_preserves_protected_ninth_level_formula_as_literal(client):
    line = "{{red:" * 9 + "{{= 1+2 }}" + "}}" * 9
    expected = render(client, [line])["rendered"]
    body = render(client, [line], {"source_map": True})
    assert body["rendered"] == expected
    assert "H7:" not in body["rendered"]


def test_formula_output_is_inserted_after_color_normalization(client):
    line = '{{= "{{red}}" }}'
    assert render(client, [line], {"source_map": True})["rendered"] == render(client, [line])["rendered"]


def test_debug_caps_formula_count_before_fetch(client, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Oversized formula request fetched context")

    monkeypatch.setattr(TemplateEngine, "_build_context", forbidden)
    response = client.post("/templates/render", json={"template": ["{{= 1 }}" * 65], "debug": {"source_map": True}})
    assert response.status_code == 422, response.text


def test_render_debug_matches_native_contract_fixture(client):
    import json
    import os
    from pathlib import Path

    request = {
        "template": ["SUM {{= 2+3 }}"],
        "device_type": "note",
        "debug": {"trace": {"line": 1, "start": 4}, "source_map": True},
    }
    response = client.post("/templates/render", json=request)
    assert response.status_code == 200, response.text
    path = Path(__file__).parent / "fixtures" / "render-debug-v1.json"
    if os.environ.get("H7_RECORD_FIXTURE") == "1":
        path.write_text(json.dumps({"request": request, "response": response.json()}, indent=2) + "\n")
    fixture = json.loads(path.read_text())
    assert fixture["request"] == request
    assert response.json() == fixture["response"]


def test_debug_session_starts_after_plugin_context_is_built(client, monkeypatch):
    observed = []

    def build(engine, *args, **kwargs):
        # A plugin may render a helper string while building its own data.
        value = engine.render("{{= 1+2 }}", context={})
        observed.append(value)
        return {"demo": {"word": value}}

    monkeypatch.setattr(TemplateEngine, "_build_context", build)
    body = render(client, ["{{demo.word}}"], {"source_map": True})
    assert observed == ["3"]
    assert body["lines"][0].strip() == "3"


@pytest.mark.parametrize(
    "atom",
    [
        "{{FILL_SPACE}}",
        "{{FILLED:-}}",
        "{{FILL_SPACE_REPEAT:-}}",
        "{{FILL_SPACE|wrap}}",
        "{{FILLED:-|wrap}}",
        "{{FILL_SPACE|upper}}",
    ],
)
def test_case_insensitive_fill_origins_use_fill_kind(client, atom):
    body = render(client, ["A" + atom + "B"], {"source_map": True})
    assert origin(body, 0, 1) == {"line": 1, "start": 1, "end": 1 + len(atom), "kind": "fill"}


@pytest.mark.parametrize("atom", ["{icon:SUN}", "{icon:heart}", "{ICON:HEART}"])
def test_standalone_icon_origins_follow_renderer_name_rules(client, atom):
    body = render(client, [atom], {"source_map": True})
    assert origin(body, 0, 0) == {"line": 1, "start": 0, "end": len(atom), "kind": "markup"}


@pytest.mark.parametrize(
    "template",
    [
        ['{{= "A|wrap|B" }}'],
        ['{{= "A|wrap|B}}TAIL" }}'],
        ['{{red:{{= "A|wrap|B" }}}}'],
        ["L {{= 1+1 }} {{demo.words|wrap}} {{= 2+2 }} R"],
        ['{{= REPT("A", 30) }}', '{{= "A|wrap|B" }}', "END"],
    ],
)
@pytest.mark.parametrize("tracking_limit", [8, 262144])
def test_formula_with_quoted_wrap_filter_keeps_default_output(client, monkeypatch, template, tracking_limit):
    from src.templates import debug as debug_module
    from src.templates.source_map import SourceTracker

    monkeypatch.setattr(debug_module, "SourceTracker", lambda: SourceTracker(limit=tracking_limit))
    baseline = render(client, template)
    debug = render(client, template, {"source_map": True})
    assert debug["rendered"] == baseline["rendered"]
    assert debug["lines"] == baseline["lines"]


@pytest.mark.parametrize("source", ["fill_space_demo", "fill_space_repeat_demo", "fill_space", "filled"])
def test_variable_names_resembling_fill_directives_remain_variables(client, source):
    atom = "{{" + source + ".word}}"
    body = render(client, [atom], {"source_map": True}, preview={"values": {source + ".word": "A"}})
    assert body["lines"][0].strip() == "A"
    assert origin(body, 0, 0) == {"line": 1, "start": 0, "end": len(atom), "kind": "variable"}


def test_configured_board_over_debug_limit_is_a_semantic_error_before_fetch(client, monkeypatch):
    from src.templates import routes

    monkeypatch.setattr(routes, "_render_geometry", lambda request, board: ("panel", 1, 1, 96, 128))

    def forbidden(*args, **kwargs):
        pytest.fail("Oversized configured board fetched plugin context")

    monkeypatch.setattr(TemplateEngine, "_build_context", forbidden)
    response = client.post("/templates/render", json={"template": ["A"], "debug": {"source_map": True}})
    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "Debug allows at most 4096 board cells"
