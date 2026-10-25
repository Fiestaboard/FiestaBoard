"""Rich cells: one parse per render, projected per output (plan D15/D17/D19).

The markup string stays canonical; what each board is sent is projected from
it by the board's resolved character set (:mod:`src.outputs.cells`):

- a split-flap board (a Vestaboard set, a FiestaPanel, no set) gets today's
  0–71 grid byte for byte, and its render calls keep their exact shape;
- a board whose set is rich (colour spans, block spans or icons: the LED
  sets) renders its template with extended markup, is parsed once, and gets
  both the 0–71 flap projection and the rich cells (each through the set's
  fallback, tiles numeric);
- an output plugin opts into rich frames by overriding ``write_cells``;
  core then dedupes colour-aware. One that does not keeps getting ints.

Also pinned: ``/panel/{id}/frame`` serves ``cells`` only for a frame that has
them, and ``POST /templates/render`` with ``board_id`` reports the board's
``charset_issues``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.led.charsets import BUILTIN_CHARACTER_SETS, has_extended_markup
from src.outputs.cells import cells_equal, project_message
from src.outputs.hooks import ReadBack
from src.outputs.plugin_base import OutputPluginBase
from src.outputs.plugin_driver import OutputPluginDriver
from src.outputs.registry import OutputCapabilities
from src.send_outcome import WriteResult
from src.text_to_board import text_to_board_array

LED = BUILTIN_CHARACTER_SETS["led_5x7"]
V1 = BUILTIN_CHARACTER_SETS["vestaboard_v1"]
V2 = BUILTIN_CHARACTER_SETS["vestaboard_v2"]

#: Messages a split-flap board must keep drawing exactly as today — the
#: extended markers included (they stay literal on a flap until FiestaUI's
#: coordinated release).
CORPUS = [
    "HELLO WORLD",
    "hello lower case",
    "{red}{orange}{yellow} {63}{71}{filled}{purple}",
    "{red:HOT} {icon:sun} {black/white:OPEN}",
    "{/}{/red} end tags",
    "72° ♥ ❤ ~ € {} {{x}}",
    "A LINE THAT IS FAR TOO LONG FOR ANY BOARD TO HOLD",
    "ROW 1\nROW 2\nROW 3\nROW 4\nROW 5\nROW 6\nROW 7",
    "",
]


# --- projection ------------------------------------------------------------------


@pytest.mark.parametrize("charset", [None, V1, V2], ids=["none", "vestaboard_v1", "vestaboard_v2"])
@pytest.mark.parametrize("message", CORPUS)
def test_a_split_flap_board_gets_todays_grid_byte_for_byte(charset, message):
    for rows, cols in [(6, 22), (3, 15), (6, 30)]:
        frame = project_message(message, rows, cols, charset)
        assert frame.characters == text_to_board_array(message, rows=rows, cols=cols)
        assert frame.cells is None


@pytest.mark.parametrize("message", CORPUS)
def test_a_rich_boards_codes_are_the_extended_flap_projection(message):
    frame = project_message(message, 6, 22, LED)
    assert frame.characters == text_to_board_array(message, rows=6, cols=22, extended_markup=True)
    assert len(frame.cells) == 6 and all(len(row) == 22 for row in frame.cells)


def test_a_rich_board_keeps_colour_case_and_icons_in_its_cells():
    (row, *_rest) = project_message("{red:Hi} {icon:sun}", 2, 6, LED).cells
    assert [c.to_dict() for c in row] == [
        {"type": "char", "value": "H", "color": "red"},
        {"type": "char", "value": "i", "color": "red"},
        {"type": "char", "value": " "},
        {"type": "color", "code": "65", "icon": "sun"},
        {"type": "char", "value": " "},
        {"type": "char", "value": " "},
    ]


def test_colour_tiles_are_normalised_to_their_numeric_code():
    (row,) = project_message("{red}{filled}{purple}{63}", 1, 4, LED).cells
    assert [c.code for c in row] == ["63", "71", "68", "63"]


def test_cells_have_passed_the_sets_fallback():
    acme = {
        "id": "acme_sign_v1",
        "label": "ACME",
        "version": 1,
        "chars": ["A", "B"],
        "tiles": False,
        "icons": [],
        "mixedCase": False,
        "colorSpans": False,
        "blockSpans": True,
    }
    (row,) = project_message("{red:ab}{63}~{black/white:A}", 1, 5, acme).cells
    assert [c.to_dict() for c in row] == [
        {"type": "char", "value": "A"},
        {"type": "char", "value": "B"},
        {"type": "char", "value": " "},
        {"type": "char", "value": " "},
        {"type": "char", "value": "A", "background": "white"},
    ]


@pytest.mark.parametrize(
    ("charset", "expected"),
    [
        (None, False),
        ("vestaboard_v1", False),
        ("vestaboard_v2", False),
        ("led_5x7", True),
        ("led_3x5", True),
        ({**V2, "id": "only_icons", "icons": ["sun"]}, True),
        ({**V2, "id": "only_blocks", "blockSpans": True}, True),
        ({**V2, "id": "only_colour", "colorSpans": True}, True),
    ],
)
def test_extended_markup_is_on_iff_the_set_is_rich(charset, expected):
    assert has_extended_markup(charset) is expected


def test_cells_equal_is_colour_aware():
    plain = project_message("HOT", 1, 3, LED).cells
    red = project_message("{red:HOT}", 1, 3, LED).cells
    assert cells_equal(plain, project_message("HOT", 1, 3, LED).cells)
    assert not cells_equal(plain, red)
    assert cells_equal(None, None) and not cells_equal(None, plain)


# --- the plugin seam -------------------------------------------------------------------


class _Sign(OutputPluginBase):
    plugin_id = "rich_sign"

    def __init__(self) -> None:
        super().__init__("b1", {})
        self.writes: list = []

    def capabilities(self) -> OutputCapabilities:
        return OutputCapabilities(
            technology="led_matrix",
            delivery="push",
            animation="none",
            native_transitions=frozenset(),
            read_back=ReadBack(supported=False, cost="cheap", suggested_interval_s=30),
        )

    def device_key(self) -> str:
        return "rich:192.0.2.70"

    def write(self, frame, *, native, cancel):
        self.writes.append(("codes", frame))
        return WriteResult(True, True)


class _CellsSign(_Sign):
    def write_cells(self, cells, *, native, cancel):
        self.writes.append(("cells", cells))
        return WriteResult(True, True)


def _driver(plugin: OutputPluginBase, charset=LED) -> OutputPluginDriver:
    return OutputPluginDriver(plugin, character_set=charset)


def test_a_plugin_that_overrides_write_cells_receives_the_rich_frame():
    frame = project_message("{red:HOT}", 1, 3, LED)
    driver = _driver(_CellsSign())
    assert driver.render(frame.characters, cells=frame.cells) == (True, True)
    assert driver.plugin.writes == [("cells", frame.cells)]


def test_a_plugin_that_does_not_opt_in_keeps_receiving_codes():
    frame = project_message("{red:HOT}", 1, 3, LED)
    driver = _driver(_Sign())
    assert driver.render(frame.characters, cells=frame.cells) == (True, True)
    assert driver.plugin.writes == [("codes", frame.characters)]


def test_a_split_flap_set_never_routes_cells_to_the_plugin():
    frame = project_message("{red:HOT}", 1, 3, LED)
    driver = _driver(_CellsSign(), charset=V2)
    driver.render(frame.characters, cells=frame.cells)
    assert [kind for kind, _ in driver.plugin.writes] == ["codes"]


def test_a_rich_output_dedupes_colour_aware():
    plain, red = project_message("HOT", 1, 3, LED), project_message("{red:HOT}", 1, 3, LED)
    assert plain.characters == red.characters  # the same flaps
    driver = _driver(_CellsSign())
    assert driver.render(plain.characters, cells=plain.cells) == (True, True)
    assert driver.render(plain.characters, cells=plain.cells) == (True, False)
    assert driver.render(red.characters, cells=red.cells) == (True, True)
    assert [cells for _, cells in driver.plugin.writes] == [plain.cells, red.cells]


def test_a_plain_output_keeps_todays_dedupe():
    plain, red = project_message("HOT", 1, 3, LED), project_message("{red:HOT}", 1, 3, LED)
    driver = _driver(_Sign())
    driver.render(plain.characters, cells=plain.cells)
    assert driver.render(red.characters, cells=red.cells) == (True, False)
    assert len(driver.plugin.writes) == 1


def test_the_rich_frame_lands_in_the_last_frame_store():
    frame = project_message("{red:HOT}", 1, 3, LED)
    driver = _driver(_CellsSign())
    driver.render(frame.characters, cells=frame.cells)
    assert driver._output_runtime.displayed_cells(1, 3) == frame.cells
    assert driver._output_runtime.displayed_cells(2, 3) is None  # stale shape refused


def test_a_frame_driven_transition_lands_on_the_rich_target(monkeypatch):
    """Intermediate frames are 0–71 grids; the frame that lands carries the cells."""
    target = project_message("{red:HOT}", 1, 3, LED)
    middle = [[1, 2, 3]]

    class Runner:
        def run(self, *, plugin_id, to_grid, board_client, **_kwargs):
            board_client.send_characters(middle)
            board_client.send_characters(to_grid)
            return (True, True)

    monkeypatch.setattr("src.outputs.plugin_driver.transition_plugins_enabled", lambda: True)
    sign = _CellsSign()
    sign.capabilities = lambda: OutputCapabilities(
        technology="led_matrix", delivery="push", animation="stream", native_transitions=frozenset()
    )
    driver = _driver(sign)
    driver.set_transition_runner(Runner())
    assert driver.render(target.characters, strategy="plugin:wipe", cells=target.cells) == (True, True)
    assert sign.writes == [("codes", middle), ("cells", target.cells)]


def test_the_default_write_cells_draws_the_flap_projection():
    frame = project_message("{red:HOT} {63}", 1, 6, LED)
    sign = _Sign()
    sign.write_cells(frame.cells, native=None, cancel=None)
    assert sign.writes == [("codes", frame.characters)]


# --- the engine --------------------------------------------------------------------------


def _engine_send(content: str, character_set):
    from tests.test_per_board_engine import _board, _drive, _page_service, _schedule_service, _service_with_runtimes

    boards = [_board("b1", "One")]
    svc, clients = _service_with_runtimes(boards)
    if character_set is not None:
        clients["b1"].character_set = character_set
    pages = _page_service({"pA": {"content": content}})
    _drive(svc, boards, pages=pages, schedule=_schedule_service({"b1": "pA"}))
    return clients["b1"], pages


def test_the_engine_renders_and_sends_rich_cells_to_a_rich_board():
    client, pages = _engine_send("{red:HOT}", LED)
    assert pages.preview_page.call_args.kwargs.get("extended_markup") is True
    (grid,) = client.render.call_args.args
    expected = project_message("{red:HOT}", 6, 22, LED)
    assert grid == expected.characters
    assert client.render.call_args.kwargs["cells"] == expected.cells


def test_the_engine_call_shape_for_a_split_flap_board_is_unchanged():
    client, pages = _engine_send("{red:HOT}", None)
    assert "extended_markup" not in pages.preview_page.call_args.kwargs
    assert "cells" not in client.render.call_args.kwargs
    assert client.render.call_args.args[0] == text_to_board_array("{red:HOT}", rows=6, cols=22)


# --- the template engine ------------------------------------------------------------------


def test_render_lines_renders_with_the_boards_extended_markup():
    from src.templates.engine import TemplateEngine

    engine = TemplateEngine()
    assert engine.render_lines(["{{red:HOT}}"], context={}, extended_markup=True).split("\n")[0].startswith("{red:HOT}")
    # The default is the split-flap mode, on since the Task 12 flip; off is the old engine.
    assert engine.render_lines(["{{red:HOT}}"], context={}).split("\n")[0].startswith("{red:HOT}")
    off = engine.render_lines(["{{red:HOT}}"], context={}, extended_markup=False)
    assert not off.split("\n")[0].startswith("{red:HOT}")


def test_an_extended_preview_bypasses_the_preview_cache(tmp_path):
    from src.pages.models import PageCreate
    from src.pages.service import PageService
    from src.pages.storage import PageStorage

    service = PageService(PageStorage(str(tmp_path / "pages.json")))
    page = service.create_page(PageCreate(name="Hot", type="template", template=["{{red:HOT}}"]))
    flap = service.preview_page(page.id)
    rich = service.preview_page(page.id, extended_markup=True)
    assert rich.formatted.startswith("{red:HOT}")
    assert service.preview_page(page.id).formatted == flap.formatted


# --- the API --------------------------------------------------------------------------------


def test_render_with_a_board_reports_its_charset_issues(api_client_with_board):
    client, board_id = api_client_with_board
    body = client.post("/templates/render", json={"template": ["Hi {{red:x}}"], "board_id": board_id}).json()
    assert body["charset"] == "vestaboard_v1"
    assert {(i["row"], i["col"], i["reason"]) for i in body["charset_issues"]} >= {(0, 1, "case")}


def test_render_without_a_board_is_unchanged(api_client_with_board):
    client, _ = api_client_with_board
    body = client.post("/templates/render", json={"template": ["HI"]}).json()
    assert set(body) == {"rendered", "lines", "line_count"}


def test_render_for_an_unknown_board_checks_nothing(api_client_with_board):
    client, _ = api_client_with_board
    body = client.post("/templates/render", json={"template": ["HI"], "board_id": "nope"}).json()
    assert body["charset"] is None and body["charset_issues"] is None


@pytest.fixture
def api_client_with_board():
    from fastapi.testclient import TestClient

    from src.api_server import app
    from src.settings.service import get_settings_service

    board = {"id": "vb1", "name": "Lobby", "device_type": "flagship", "code62_glyph": "degree"}
    get_settings_service().set_boards([board])
    return TestClient(app), "vb1"


# --- /panel/{id}/frame -----------------------------------------------------------------------


def _panel_frame(record) -> dict:
    from types import SimpleNamespace
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    from src.api_server import app
    from src.outputs.runtime import OutputRuntime
    from src.panels.models import Panel

    output = OutputRuntime()
    record(output.frames)
    rt = SimpleNamespace(client=object(), output=output)
    service = SimpleNamespace(runtime_for=lambda _board_id: rt)
    panels = MagicMock()
    panels.get_panel_by_ref.return_value = Panel(name="Hall TV", board_id="b1")
    with (
        patch("src.panels.routes.get_panel_service", return_value=panels),
        patch("src.panels.routes.get_service", return_value=service),
    ):
        return TestClient(app).get("/panel/abc123def456/frame").json()


def test_the_panel_frame_serves_rich_cells_beside_the_unchanged_fields():
    from src.outputs.cells import cells_to_json

    frame = project_message("{red:HOT}", 6, 22, LED)
    body = _panel_frame(lambda frames: frames.record_sent(frame.characters, cells=frame.cells))
    assert body["characters"] == frame.characters
    assert body["message"].startswith("HOT")
    assert body["cells"] == cells_to_json(frame.cells)
    assert body["cells"][0][0] == {"type": "char", "value": "H", "color": "red"}


def test_a_panel_frame_without_rich_cells_has_no_cells_key():
    grid = text_to_board_array("HOT", rows=6, cols=22)
    body = _panel_frame(lambda frames: frames.record_sent(grid))
    assert body["characters"] == grid
    assert "cells" not in body


# --- /board/current-message (the home live preview) ----------------------------------------------


def _current_message(record, polled=None) -> dict:
    from types import SimpleNamespace
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    from src.api_server import app
    from src.outputs.runtime import OutputRuntime

    output = OutputRuntime()
    record(output.frames)
    rt = SimpleNamespace(
        client=object(), output=output, polled_characters=polled, polled_at=1.0 if polled is not None else None
    )
    service = SimpleNamespace(vb_client=object(), runtime_for=lambda _board_id: rt)
    settings = MagicMock()
    settings.get_primary_board_id.return_value = "vb1"
    with (
        patch("src.board_api.routes.runtime.get_service", return_value=service),
        patch("src.board_api.routes.runtime.get_settings_service", return_value=settings),
        patch("src.board_api.routes._require_board", return_value={"id": "px1", "device_type": "panel"}),
    ):
        return TestClient(app).get("/board/current-message?board_id=px1").json()


def test_the_current_message_serves_a_rich_boards_cells_beside_the_unchanged_fields():
    from src.outputs.cells import cells_to_json

    frame = project_message("{red:HOT} {icon:heart}", 6, 22, LED)
    body = _current_message(lambda frames: frames.record_sent(frame.characters, cells=frame.cells))
    assert body["characters"] == frame.characters
    assert body["cells"] == cells_to_json(frame.cells)
    assert body["cells"][0][0] == {"type": "char", "value": "H", "color": "red"}


def test_a_polled_frame_that_is_not_the_last_write_has_no_cells():
    """Something else wrote to the board: the last write's cells would
    describe a frame that is not showing."""
    frame = project_message("{red:HOT}", 6, 22, LED)
    other = text_to_board_array("ELSEWHERE", rows=6, cols=22)
    body = _current_message(lambda frames: frames.record_sent(frame.characters, cells=frame.cells), polled=other)
    assert body["characters"] == other
    assert "cells" not in body


def test_a_current_message_without_rich_cells_has_no_cells_key():
    grid = text_to_board_array("HOT", rows=6, cols=22)
    body = _current_message(lambda frames: frames.record_sent(grid))
    assert body["characters"] == grid
    assert "cells" not in body


# --- POST /pages/preview/batch (the Change Page thumbnails) ---------------------------------------


@pytest.fixture
def batch_pages(tmp_path):
    """A real page service with one spans-and-icons page, and a 6x22 board."""
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    from src.api_server import app
    from src.pages.models import PageCreate
    from src.pages.service import PageService
    from src.pages.storage import PageStorage

    service = PageService(PageStorage(str(tmp_path / "pages.json")))
    page = service.create_page(PageCreate(name="Hot", type="template", template=["{{red:HOT}} {{icon:heart}}"]))
    board = {"id": "px1", "name": "Desk", "device_type": "flagship"}
    with (
        patch("src.pages.routes.get_page_service", return_value=service),
        patch("src.pages.routes._find_board", side_effect=lambda board_id: board if board_id == "px1" else None),
    ):
        yield TestClient(app), service, page.id


def _batch(client, page_id, **extra) -> dict:
    resp = client.post("/pages/preview/batch", json={"page_ids": [page_id], **extra})
    assert resp.status_code == 200, resp.text
    return resp.json()["previews"][page_id]


def test_a_batch_preview_for_a_rich_board_renders_its_spans_and_serves_cells(batch_pages):
    from unittest.mock import patch

    from src.outputs.cells import cells_to_json

    client, _, page_id = batch_pages
    with patch("src.pages.routes.board_character_set", return_value=LED):
        preview = _batch(client, page_id, board_id="px1")
    assert preview["message"].startswith("{red:HOT}")
    assert "?" not in preview["message"]
    assert preview["cells"] == cells_to_json(project_message(preview["message"], 6, 22, LED).cells)
    assert preview["cells"][0][0] == {"type": "char", "value": "H", "color": "red"}


def test_a_batch_preview_for_a_split_flap_board_is_unchanged(batch_pages):
    from unittest.mock import patch

    client, _, page_id = batch_pages
    plain = _batch(client, page_id)
    with patch("src.pages.routes.board_character_set", return_value=V1):
        flap = _batch(client, page_id, board_id="px1")
    assert flap == plain
    assert "cells" not in flap


def test_a_rich_batch_preview_leaves_the_split_flap_preview_cache_alone(batch_pages):
    from unittest.mock import patch

    client, service, page_id = batch_pages
    plain = _batch(client, page_id)
    with patch("src.pages.routes.board_character_set", return_value=LED):
        _batch(client, page_id, board_id="px1")
    assert service.preview_page(page_id).formatted == plain["message"]
