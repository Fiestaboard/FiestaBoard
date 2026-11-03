"""The flexible page document: validation, extension preservation and dump shape."""

import pytest
from pydantic import ValidationError

from src.pages.flexible import MAX_BLOCKS, BlockStyle
from src.pages.models import Page, PageCreate, PageImportPreview, PageUpdate

FLEX = {
    "name": "Morning",
    "type": "flexible",
    "blocks": [
        {"id": "b1", "kind": "text", "text": "{{date_time.time}}", "style": {"size": "large"}, "priority": 1},
        {"id": "b2", "kind": "text", "text": "HI", "if": "{{weather.temp}} > 50"},
    ],
}


def test_flexible_page_validates_and_round_trips_if_alias():
    page = Page.model_validate(FLEX)
    assert page.type == "flexible" and page.blocks[1].if_ == "{{weather.temp}} > 50"
    dumped = page.model_dump()
    assert dumped["blocks"][1]["if"] == "{{weather.temp}} > 50" and "if_" not in dumped["blocks"][1]


def test_flexible_dump_has_no_grid_fields():
    dumped = Page.model_validate(FLEX).model_dump()
    for key in ("device_type", "notes_wide", "notes_tall", "grid_rows", "grid_cols", "template", "rows", "canvases"):
        assert key not in dumped


def test_grid_page_dump_has_no_flexible_fields():
    dumped = Page(name="G", type="template", template=["HI"]).model_dump()
    for key in ("style", "layout", "blocks", "targets"):
        assert key not in dumped


def test_flexible_page_rejects_template_and_explicit_device_type():
    with pytest.raises(ValidationError, match="flexible page has no"):
        Page.model_validate({**FLEX, "template": ["X"]})
    with pytest.raises(ValidationError, match="flexible page has no"):
        PageCreate.model_validate({**FLEX, "device_type": "note"})


def test_grid_page_rejects_blocks():
    with pytest.raises(ValidationError, match="only a flexible page"):
        PageCreate.model_validate({"name": "G", "type": "template", "template": ["X"], "blocks": []})


def test_duplicate_block_ids_rejected():
    with pytest.raises(ValidationError, match="duplicate block id"):
        Page.model_validate({**FLEX, "blocks": [{"id": "a", "kind": "spacer"}, {"id": "a", "kind": "spacer"}]})


def test_unknown_block_kind_and_style_property_survive_round_trip():
    raw = {**FLEX, "blocks": [{"id": "x", "kind": "progress", "value": 3, "style": {"glow": 2}}]}
    dumped = Page.model_validate(raw).model_dump()
    assert dumped["blocks"][0]["kind"] == "progress" and dumped["blocks"][0]["value"] == 3
    assert dumped["blocks"][0]["style"]["glow"] == 2


def test_unknown_layout_kind_is_preserved():
    assert Page.model_validate({**FLEX, "layout": {"kind": "regions"}}).model_dump()["layout"]["kind"] == "regions"


def test_validate_config_requires_a_block_and_text_for_text_blocks():
    assert "at least one block" in "; ".join(Page.model_validate({**FLEX, "blocks": []}).validate_config())
    bad = Page.model_validate({**FLEX, "blocks": [{"id": "a", "kind": "text"}]})
    assert any("text block 'a' needs text" in e for e in bad.validate_config())


def test_validate_config_requires_content_or_source_for_canvas_blocks():
    bad = Page.model_validate({**FLEX, "blocks": [{"id": "c", "kind": "canvas", "canvas": {}}]})
    assert any("canvas block 'c'" in e for e in bad.validate_config())


def test_more_than_max_blocks_rejected():
    blocks = [{"id": f"s{i}", "kind": "spacer"} for i in range(MAX_BLOCKS + 1)]
    with pytest.raises(ValidationError, match=f"at most {MAX_BLOCKS} blocks"):
        Page.model_validate({**FLEX, "blocks": blocks})


def test_block_id_pattern_enforced():
    with pytest.raises(ValidationError, match=r"blocks\.0\.id"):
        Page.model_validate({**FLEX, "blocks": [{"id": "has space", "kind": "spacer"}]})


@pytest.mark.parametrize("color", ["red", "Violet", "#ff8800", "63", "{71}", "{{weather.temp_color}}"])
def test_style_color_accepts_board_names_hex_tile_codes_and_one_expression(color):
    assert BlockStyle.model_validate({"color": color, "background": color}).color == color


@pytest.mark.parametrize("color", ["#f80", "chartreuse", "72", "{{a}}{{b}}", "x{{a}}"])
def test_style_color_rejects_anything_else(color):
    with pytest.raises(ValidationError, match="colour"):
        BlockStyle.model_validate({"color": color})


def test_style_size_int_out_of_range_rejected():
    with pytest.raises(ValidationError):
        BlockStyle.model_validate({"size": 257})


def test_document_protocol_is_v2_for_flexible_pages_only():
    assert Page.model_validate(FLEX).document_protocol == "page-document-v2"
    assert Page(name="G", type="template", template=["HI"]).document_protocol == "page-document-v1"


def test_page_update_carries_flexible_fields_with_if_alias():
    dumped = PageUpdate.model_validate({"blocks": FLEX["blocks"]}).model_dump(exclude_unset=True)
    assert dumped["blocks"][1]["if"] == "{{weather.temp}} > 50"


def test_import_preview_dump_drops_grid_fields_for_flexible():
    dumped = PageImportPreview.model_validate(FLEX).model_dump()
    assert "device_type" not in dumped and dumped["blocks"][0]["id"] == "b1"


def test_create_page_keeps_flexible_fields_and_adds_no_grid(tmp_path):
    from src.pages.service import PageService
    from src.pages.storage import PageStorage

    service = PageService(storage=PageStorage(str(tmp_path / "pages.json")))
    created = service.create_page(PageCreate.model_validate({**FLEX, "layout": {"valign": "middle"}}))
    dumped = created.model_dump()
    assert dumped["blocks"][1]["if"] == "{{weather.temp}} > 50" and dumped["layout"]["valign"] == "middle"
    assert "device_type" not in dumped


def test_update_page_replaces_blocks_whole(tmp_path):
    from src.pages.service import PageService
    from src.pages.storage import PageStorage

    service = PageService(storage=PageStorage(str(tmp_path / "pages.json")))
    page = service.create_page(PageCreate.model_validate(FLEX))
    updated = service.update_page(page.id, PageUpdate(blocks=[{"id": "only", "kind": "spacer"}]))
    assert [b.id for b in updated.blocks] == ["only"]
