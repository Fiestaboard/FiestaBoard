"""Pages carry canvases (design §1): model, validation, storage migration v6, share, retarget."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from src.canvas import Canvas
from src.pages.models import Page, PageCreate, PageImportPreview, PageUpdate
from src.pages.service import PageService
from src.pages.share import decode_page, encode_page
from src.pages.storage import CURRENT_SCHEMA_VERSION, MIGRATIONS, PageStorage, _migrate_v5_to_v6

SKY = {
    "id": "sky",
    "area": {"row": 1, "col": 1, "rows": 2, "cols": 4},
    "bleed": ["top"],
    "text": "flow",
    "content": {
        "palette": {"y": "#ffcc00"},
        "shapes": [
            {"type": "gradient", "from": "#000000", "to": "#0000ff", "if": "{{= 1 }}"},
            {"type": "rect", "x": 0, "y": 0, "w": 1, "h": 1, "fill": "y", "foreach": "{{x.items}}", "as": "p"},
        ],
        "pixels": ["y."],
    },
}


def _page(**kw) -> Page:
    data = {"name": "P", "type": "template", "template": ["HELLO"], "canvases": [SKY]}
    data.update(kw)
    return Page(**data)


@pytest.fixture
def service(tmp_path):
    return PageService(storage=PageStorage(storage_file=str(tmp_path / "pages.json")))


# --- model + validation ------------------------------------------------------


def test_page_holds_validated_canvases():
    page = _page()
    assert isinstance(page.canvases[0], Canvas)
    assert page.canvases[0].text == "flow"


def test_canvases_default_to_none():
    assert Page(name="P", type="template", template=["X"]).canvases is None


def test_dump_uses_the_json_names_if_as_from_and_drops_unset_fields():
    dumped = _page().model_dump()["canvases"][0]
    shapes = dumped["content"]["shapes"]
    assert shapes[0]["from"] == "#000000" and shapes[0]["if"] == "{{= 1 }}"
    assert shapes[1]["as"] == "p"
    assert "from_" not in shapes[0] and "if_" not in shapes[0]
    assert "source" not in dumped  # None fields are not written
    # ...and the dump validates back to the same page.
    assert Page(**_page().model_dump()).canvases == _page().canvases


def test_an_area_that_starts_outside_the_page_grid_is_a_validation_error():
    with pytest.raises(ValidationError, match="outside the page"):
        _page(canvases=[{**SKY, "area": {"row": 7, "col": 1, "rows": 1, "cols": 4}}])  # flagship is 6 x 22
    with pytest.raises(ValidationError, match="outside the page"):
        _page(canvases=[{**SKY, "area": {"row": 1, "col": 23, "rows": 1, "cols": 1}}])
    with pytest.raises(ValidationError):
        _page(canvases=[{**SKY, "area": {"row": 1, "col": 1, "rows": 0, "cols": 1}}])


def test_an_area_running_past_the_grid_edge_is_kept_and_clamped_at_render():
    # "The whole board" on every size: the plugin demos use this.
    page = _page(canvases=[{**SKY, "area": {"row": 1, "col": 1, "rows": 96, "cols": 128}}])
    assert page.canvases[0].area.rows == 96


def test_an_area_that_fits_a_note_array_is_accepted():
    _page(
        device_type="note_array",
        notes_wide=2,
        notes_tall=1,
        canvases=[{**SKY, "area": {"row": 1, "col": 16, "rows": 3, "cols": 15}}],
    )


def test_duplicate_ids_and_too_many_canvases_are_rejected():
    with pytest.raises(ValidationError, match="used twice"):
        _page(canvases=[SKY, SKY])
    with pytest.raises(ValidationError, match="at most 8"):
        _page(canvases=[{**SKY, "id": f"c{i}"} for i in range(9)])


def test_create_and_update_requests_validate_canvases():
    with pytest.raises(ValidationError):
        PageCreate(name="P", type="template", template=["X"], canvases=[{**SKY, "id": "Bad Id"}])
    with pytest.raises(ValidationError, match="outside the page"):
        PageCreate(
            name="P",
            type="template",
            device_type="note",
            template=["X"],
            canvases=[SKY | {"area": {"row": 4, "col": 1, "rows": 1, "cols": 1}}],
        )
    with pytest.raises(ValidationError):
        PageUpdate(canvases=[{**SKY, "scale": 99}])


# --- service + storage -------------------------------------------------------


def test_create_page_persists_canvases_and_reloads_them(service, tmp_path):
    page = service.create_page(PageCreate(name="P", type="template", template=["X"], canvases=[SKY]))
    raw = json.loads((tmp_path / "pages.json").read_text())
    stored = raw["pages"][0]["canvases"][0]
    assert stored["content"]["shapes"][0]["from"] == "#000000"
    reloaded = PageStorage(storage_file=str(tmp_path / "pages.json")).get(page.id)
    assert reloaded.canvases == page.canvases


def test_update_can_set_and_clear_canvases(service):
    page = service.create_page(PageCreate(name="P", type="template", template=["X"]))
    assert service.update_page(page.id, PageUpdate(canvases=[SKY])).canvases[0].id == "sky"
    assert service.update_page(page.id, PageUpdate(canvases=None)).canvases is None


def test_an_update_whose_area_starts_outside_the_grid_is_refused(service):
    page = service.create_page(PageCreate(name="P", type="template", template=["X"]))
    with pytest.raises(ValueError, match="outside the page"):
        service.update_page(page.id, PageUpdate(canvases=[{**SKY, "area": {"row": 7, "col": 1, "rows": 2, "cols": 1}}]))


def test_a_retarget_scales_canvas_areas_to_the_new_grid(service):
    page = service.create_page(
        PageCreate(
            name="P",
            type="template",
            device_type="panel",
            grid_rows=10,
            grid_cols=16,
            template=["X"],
            canvases=[{**SKY, "area": {"row": 1, "col": 9, "rows": 10, "cols": 8}}],
        )
    )
    moved = service.update_page(page.id, PageUpdate(device_type="panel", grid_rows=8, grid_cols=10))
    area = moved.canvases[0].area
    assert (area.row, area.col, area.rows, area.cols) == (1, 6, 8, 5)


def test_retarget_pages_moves_canvases_with_the_page(service, monkeypatch):
    from src.devices import geometry_of
    from src.pages.retarget import add_resize, retarget_pages

    monkeypatch.setattr("src.pages.service.get_page_service", lambda: service)
    page = service.create_page(
        PageCreate(
            name="P",
            type="template",
            device_type="panel",
            grid_rows=10,
            grid_cols=16,
            template=["X"],
            canvases=[{**SKY, "area": {"row": 6, "col": 1, "rows": 5, "cols": 16}}],
        )
    )
    resizes: dict = {}
    old = {"device_type": "panel", "grid_rows": 10, "grid_cols": 16}
    new = {"device_type": "panel", "grid_rows": 8, "grid_cols": 10}
    add_resize(resizes, old, new)
    moved = retarget_pages(resizes, set(), allow_shrink=True)
    assert [m["page_id"] for m in moved] == [page.id]
    stored = service.get_page(page.id)
    assert geometry_of(stored)[3:] == (8, 10)
    area = stored.canvases[0].area
    assert (area.row, area.col, area.rows, area.cols) == (5, 1, 4, 10)


# --- migration v6 ------------------------------------------------------------


def test_schema_version_is_6_with_the_canvases_migration_last():
    assert CURRENT_SCHEMA_VERSION == 6
    assert MIGRATIONS[-1] == (6, _migrate_v5_to_v6)


def test_migration_sets_canvases_null_where_absent_and_is_idempotent():
    pages = [{"id": "a"}, {"id": "b", "canvases": [SKY]}, {"id": "c", "canvases": None}]
    assert _migrate_v5_to_v6(pages) == 1
    assert pages[0]["canvases"] is None
    assert pages[1]["canvases"] == [SKY]
    assert _migrate_v5_to_v6(pages) == 0


def test_a_v5_file_loads_and_is_saved_as_v6(tmp_path):
    path = tmp_path / "pages.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 5,
                "pages": [
                    {
                        "id": "p1",
                        "name": "Old",
                        "type": "template",
                        "template": ["HI"],
                        "notes_wide": 1,
                        "notes_tall": 1,
                        "grid_rows": None,
                        "grid_cols": None,
                        "created_at": "2026-01-01T00:00:00+00:00",
                    }
                ],
            }
        )
    )
    storage = PageStorage(storage_file=str(path))
    assert storage.get("p1").canvases is None
    saved = json.loads(path.read_text())
    assert saved["schema_version"] == 6
    assert saved["pages"][0]["canvases"] is None


# --- share / import ----------------------------------------------------------


def test_share_string_round_trips_canvases():
    page = _page()
    data = decode_page(encode_page(page))
    assert data["canvases"][0]["content"]["shapes"][0]["from"] == "#000000"
    created = PageCreate(**{k: v for k, v in data.items() if k in PageCreate.model_fields})
    assert created.canvases == page.canvases
    assert PageImportPreview(**data).canvases == page.canvases


def test_import_creates_the_page_with_its_canvases(service):
    data = decode_page(encode_page(_page()))
    created = service.create_page(PageCreate(**{k: v for k, v in data.items() if k in PageCreate.model_fields}))
    assert service.get_page(created.id).canvases[0].id == "sky"


# --- plugin demo pages ---------------------------------------------------------


def test_a_demo_page_carries_the_manifests_canvases():
    from src.plugins.manifest import PluginManifest

    whole = {
        "id": "art",
        "area": {"row": 1, "col": 1, "rows": 96, "cols": 128},
        "bleed": ["all"],
        "source": "{{demo_art.canvas}}",
    }
    manifest = PluginManifest.from_dict(
        {
            "id": "demo_art",
            "name": "Demo Art",
            "version": "1.0.0",
            "demo": {"flagship": {"name": "Art", "template": [""], "canvases": [whole]}},
        }
    )
    assert manifest.demo["flagship"].canvases == [whole]


def test_create_demo_page_validates_and_stores_canvases(service):
    from src.plugins.manifest import DemoPageSchema

    whole = {"id": "art", "area": {"row": 1, "col": 1, "rows": 96, "cols": 128}, "source": "{{demo_art.canvas}}"}
    page, _ = service.create_demo_page("demo_art", DemoPageSchema(name="Art", template=[""], canvases=[whole]))
    assert service.get_page(page.id).canvases[0].source == "{{demo_art.canvas}}"
    bad = DemoPageSchema(name="Art", template=["X"], canvases=[{**whole, "id": "Bad Id"}])
    with pytest.raises(ValidationError):
        service.create_demo_page("demo_art", bad)
    assert service.get_page(page.id) is not None  # the old demo survives a bad one
