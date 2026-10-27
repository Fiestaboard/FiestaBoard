"""Page document extensions survive supported edits without gaining runtime behavior."""

import copy
import json
from pathlib import Path

import pytest

from src.canvas.models import Canvas
from src.canvas.refs import canvas_plugin_ids
from src.pages.models import Page, PageCreate, PageUpdate
from src.pages.service import PageService
from src.pages.storage import PageStorage

FIXTURE = Path(__file__).parent / "fixtures/page-editing/rich-extensions-v1.json"


@pytest.fixture
def document():
    return json.loads(FIXTURE.read_text())


@pytest.fixture
def storage(tmp_path, document):
    path = tmp_path / "pages.json"
    path.write_text(json.dumps(document, ensure_ascii=False))
    return PageStorage(str(path))


def test_sparse_edit_preserves_top_level_and_nested_extensions(storage, document):
    original = document["pages"][0]
    page = storage.get(original["id"])
    assert page is not None
    updated = PageService(storage=storage).update_page(
        page.id, PageUpdate(name="Renamed", expected_revision=page.revision)
    )
    saved = json.loads(storage.storage_file.read_text())
    actual = saved["pages"][0]
    assert saved["future_document"] == document["future_document"]
    for field in ("future_page", "rows", "line_metadata", "canvases", "template"):
        assert actual[field] == original[field]
    assert updated.model_dump()["future_page"] == original["future_page"]
    assert "revision" not in actual and "edit_protocol" not in actual
    restarted = PageStorage(str(storage.storage_file))
    assert restarted.get(page.id).model_dump()["canvases"] == original["canvases"]


def test_explicit_nested_nulls_and_omissions_are_distinct(document):
    raw = document["pages"][0]
    page = Page(**raw)
    canvas = page.model_dump()["canvases"][0]
    assert canvas == raw["canvases"][0]
    assert canvas["source"] is None
    assert "scale" not in canvas
    assert canvas["content"]["shapes"][0]["stroke"] is None
    assert "if" not in canvas["content"]["shapes"][0]


def test_unknown_extensions_do_not_gain_render_or_plugin_reference_behavior(document):
    raw = document["pages"][0]
    page = Page(**raw)
    assert canvas_plugin_ids(page.canvases) == set()
    from src.canvas.evaluate import resolve_content

    resolved, issues = resolve_content(page.canvases[0].content, {})
    assert issues == []
    assert len(resolved.shapes) == 1
    assert "future_shape" not in resolved.shapes[0].values


def test_known_list_updates_replace_whole_fields(storage):
    page = storage.get("rich-extension-page")
    assert page is not None
    updated = PageService(storage=storage).update_page(page.id, PageUpdate(line_metadata=[{"alignment": "right"}]))
    assert updated.line_metadata[0].model_dump() == {"alignment": "right", "wrap": False}
    assert updated.model_dump()["future_page"]["ratio"] == 1e100
    cleared = PageService(storage=storage).update_page(page.id, PageUpdate(canvases=None))
    assert cleared.canvases is None


def test_page_update_cannot_overwrite_owned_metadata_or_opaque_top_level_fields(storage):
    page = storage.get("rich-extension-page")
    assert page is not None
    original_extension = copy.deepcopy(page.model_dump()["future_page"])
    updated = storage.update(
        page.id,
        {
            "id": "spoofed",
            "created_at": "2000-01-01T00:00:00Z",
            "demo_plugin_id": "spoofed",
            "future_page": None,
            "revision": "spoofed",
            "edit_protocol": "spoofed",
        },
    )
    assert updated.id == page.id
    assert updated.created_at == page.created_at
    assert updated.demo_plugin_id == page.demo_plugin_id
    assert updated.model_dump()["future_page"] == original_extension
    assert updated.revision != "spoofed"
    assert updated.edit_protocol == "page-revision-v1"


def test_geometry_retarget_preserves_canvas_area_extensions(storage):
    page = storage.get("rich-extension-page")
    assert page is not None
    updated = PageService(storage=storage).update_page(page.id, PageUpdate(grid_cols=30))
    assert updated.canvases[0].model_dump()["area"]["future_area"] == {"nullable": None}
    assert updated.canvases[0].area.cols == 4


@pytest.mark.parametrize("mutation", ["unknown_shape", "bad_coordinate", "bad_area", "bad_grid"])
def test_extensions_do_not_bypass_known_validation(document, mutation):
    raw = document["pages"][0]
    if mutation == "unknown_shape":
        raw["canvases"][0]["content"]["shapes"][0]["type"] = "future_shape"
    elif mutation == "bad_coordinate":
        raw["canvases"][0]["content"]["shapes"][0]["x"] = 100000
    elif mutation == "bad_area":
        raw["canvases"][0]["area"]["row"] = 99
    else:
        raw["grid_cols"] = 0
    with pytest.raises(ValueError):
        Page(**raw)


def test_standalone_canvas_requests_keep_strict_unknown_field_validation(document):
    with pytest.raises(ValueError, match="extra_forbidden"):
        Canvas.model_validate(document["pages"][0]["canvases"][0])


def test_share_copy_and_create_preserve_author_extensions_without_server_metadata(storage, document):
    from src.pages.share import decode_page, encode_page

    page = storage.get("rich-extension-page")
    content = decode_page(encode_page(page))
    for field in ("future_page", "rows", "line_metadata", "canvases"):
        assert content[field] == document["pages"][0][field]
    for field in (
        "id",
        "created_at",
        "updated_at",
        "demo_plugin_id",
        "revision",
        "expected_revision",
        "edit_protocol",
        "document_protocol",
    ):
        assert field not in content
    copied = PageService(storage=storage).create_page(PageCreate(**content))
    assert copied.id != page.id
    assert copied.model_dump()["future_page"] == content["future_page"]
    assert copied.model_copy(deep=True).model_dump()["canvases"] == content["canvases"]


def test_create_metadata_input_cannot_claim_server_tracking(storage, document):
    raw = {
        **document["pages"][0],
        "demo_plugin_id": "spoofed",
        "expected_revision": "spoofed",
        "revision": "spoofed",
        "edit_protocol": "spoofed",
        "document_protocol": "spoofed",
    }
    created = PageService(storage=storage).create_page(PageCreate(**raw))
    assert created.id != raw["id"]
    assert created.created_at.isoformat() != raw["created_at"]
    assert created.updated_at is None
    assert created.demo_plugin_id is None
    assert "expected_revision" not in created.model_dump()
    assert created.revision != "spoofed"
    assert created.edit_protocol == "page-revision-v1"
    assert created.document_protocol == "page-document-v1"
    assert created.model_dump()["future_page"] == raw["future_page"]


def test_document_protocol_cannot_be_overridden_or_persisted(storage):
    page = storage.get("rich-extension-page")
    supplied = Page(**{**page.model_dump(), "document_protocol": "spoofed"})
    assert supplied.document_protocol == "page-document-v1"
    updated = storage.update(page.id, {"document_protocol": "spoofed"})
    assert updated.model_dump()["document_protocol"] == "page-document-v1"
    assert "document_protocol" not in json.loads(storage.storage_file.read_text())["pages"][0]


def test_http_share_preview_import_preserve_extensions_and_reject_metadata(storage, document, monkeypatch):
    prefix = ""
    from fastapi.testclient import TestClient

    from src.api_server import app

    service = PageService(storage=storage)
    monkeypatch.setattr("src.pages.routes.get_page_service", lambda: service)
    client = TestClient(app)
    share = client.get(f"{prefix}/pages/rich-extension-page/share")
    assert share.status_code == 200
    preview = client.post(f"{prefix}/pages/import/preview", json=share.json())
    assert preview.status_code == 200
    assert preview.json()["future_page"] == document["pages"][0]["future_page"]
    imported = client.post(f"{prefix}/pages/import", json=share.json())
    assert imported.status_code == 201
    for field in ("future_page", "rows", "line_metadata", "canvases"):
        assert imported.json()[field] == document["pages"][0][field]
    assert imported.json()["document_protocol"] == "page-document-v1"
    malicious = Page(**{**document["pages"][0], "revision": "spoofed"})
    import base64

    payload = {
        "v": 1,
        "page": {
            **json.loads(malicious.model_dump_json()),
            "demo_plugin_id": "spoofed",
            "expected_revision": "spoofed",
        },
    }
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    preview = client.post(f"{prefix}/pages/import/preview", json={"share_string": encoded})
    assert preview.status_code == 200
    for field in (
        "id",
        "revision",
        "expected_revision",
        "edit_protocol",
        "document_protocol",
        "created_at",
        "demo_plugin_id",
    ):
        assert field not in preview.json()
    imported = client.post(f"{prefix}/pages/import", json={"share_string": encoded})
    assert imported.status_code == 201
    assert imported.json()["demo_plugin_id"] is None
    assert imported.json()["id"] != malicious.id


def test_restore_retains_extensions_with_same_live_owner_and_new_revision(storage, document, monkeypatch):
    from src.backup.service import BACKUP_FILE_MARKER, BACKUP_SCHEMA_VERSION, BackupService

    service = PageService(storage=storage)
    monkeypatch.setattr("src.pages.service.get_page_service", lambda: service)
    original = storage.get("rich-extension-page")
    backup = {BACKUP_FILE_MARKER: True, "schema_version": BACKUP_SCHEMA_VERSION, "data": {"pages": document}}
    from unittest.mock import patch

    with patch("src.backup.service._reload_services", return_value=[]):
        BackupService(data_dir=storage.storage_file.parent).import_from_dict(backup, reinstall_plugins=False)
    restored = service.get_page(original.id)
    assert service.storage is storage
    assert restored.revision != original.revision
    updated = service.update_page(restored.id, PageUpdate(name="Restored edit", expected_revision=restored.revision))
    assert updated.model_dump()["future_page"] == document["pages"][0]["future_page"]
    assert json.loads(storage.storage_file.read_text())["future_document"] == document["future_document"]


def test_tool_share_import_preserves_top_level_author_extensions(storage, document, monkeypatch):
    from src.ops.executors import import_page
    from src.pages.share import encode_page

    service = PageService(storage=storage)
    monkeypatch.setattr("src.pages.service.get_page_service", lambda: service)
    result = import_page(encode_page(storage.get("rich-extension-page")))
    imported = storage.get(result["page_id"])
    assert imported.model_dump()["future_page"] == document["pages"][0]["future_page"]


@pytest.mark.parametrize("prefix", ["", "/v1"])
def test_http_sparse_put_preserves_extensions_and_original_token(prefix, storage, document, monkeypatch):
    from fastapi.testclient import TestClient

    from src.api_server import app

    monkeypatch.setattr("src.pages.routes.get_page_service", lambda: PageService(storage=storage))
    client = TestClient(app)
    original = client.get(f"{prefix}/pages/rich-extension-page")
    assert original.status_code == 200
    body = original.json()
    saved = client.put(
        f"{prefix}/pages/{body['id']}",
        json={
            "name": "HTTP edit",
            "expected_revision": body["revision"],
            "future_page": {"spoofed": True},
            "created_at": "2000-01-01T00:00:00Z",
        },
    )
    assert saved.status_code == 200
    for field in ("future_page", "canvases", "rows", "line_metadata", "created_at"):
        assert saved.json()["page"][field] == body[field]
    assert saved.json()["page"]["document_protocol"] == "page-document-v1"
    stale = client.put(f"{prefix}/pages/{body['id']}", json={"name": "Stale", "expected_revision": body["revision"]})
    assert stale.status_code == 412
    assert storage.get(body["id"]).name == "HTTP edit"


@pytest.mark.parametrize(
    "shape",
    [
        {"type": "rect", "x": 0, "y": 0, "w": 1, "h": 1},
        {"type": "circle", "cx": 0, "cy": 0, "r": 1},
        {"type": "ellipse", "cx": 0, "cy": 0, "rx": 1, "ry": 1},
        {"type": "line", "x1": 0, "y1": 0, "x2": 1, "y2": 1, "stroke": "red"},
        {"type": "polygon", "points": [[0, 0], [1, 0], [0, 1]]},
        {"type": "text", "x": 0, "y": 0, "text": "雪", "color": "red"},
        {"type": "gradient", "from": "red", "to": "blue"},
    ],
)
def test_each_supported_shape_retains_extensions_and_render_defaults(shape, document):
    from src.canvas.evaluate import resolve_content

    raw = document["pages"][0]
    raw["canvases"][0]["content"]["shapes"] = [{**shape, "future": {"value": None}}]
    page = Page(**raw)
    assert page.model_dump(mode="json")["canvases"][0]["content"]["shapes"] == [{**shape, "future": {"value": None}}]
    resolved, issues = resolve_content(page.canvases[0].content, {})
    assert issues == []
    assert len(resolved.shapes) == 1
    assert "future" not in resolved.shapes[0].values
    assert page.canvases[0].scale == 1
    assert page.canvases[0].text == "hide"


def test_extensions_cannot_contain_non_json_runtime_objects(document):
    raw = document["pages"][0]
    raw["future_page"] = object()
    with pytest.raises(ValueError):
        Page(**raw)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_extensions_reject_non_json_nonfinite_numbers(value, document):
    raw = document["pages"][0]
    raw["future_page"] = {"nested": [value]}
    with pytest.raises(ValueError):
        Page(**raw)


def test_persisted_runtime_metadata_is_ignored_before_validation(tmp_path, document):
    raw = document["pages"][0]
    raw.update(
        revision={"spoofed": True}, expected_revision="spoofed", edit_protocol=None, document_protocol=["spoofed"]
    )
    path = tmp_path / "pages.json"
    path.write_text(json.dumps(document))
    storage = PageStorage(str(path))
    page = storage.get(raw["id"])
    assert page is not None
    assert isinstance(page.revision, str)
    assert page.document_protocol == "page-document-v1"
    storage.update(page.id, {"name": "Saved"})
    stored = json.loads(path.read_text())["pages"][0]
    assert not {"revision", "expected_revision", "edit_protocol", "document_protocol"} & stored.keys()
