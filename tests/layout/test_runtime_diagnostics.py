"""Engine computations remain inspectable without claiming a device write."""

from src.layout.issues import LayoutIssue
from src.send_outcome import WriteResult
from tests.test_native_playlist import native_engine  # noqa: F401
from tests.test_v1_contract import client  # noqa: F401


def test_native_member_issues_survive_a_failed_output_without_claiming_delivery(native_engine):  # noqa: F811
    env = native_engine
    preview = env.pages.preview_page.side_effect

    def with_issue(*args, **kwargs):
        result = preview(*args, **kwargs)
        result.layout_issues = [LayoutIssue(("blocks", "title"), "truncated", "warning", "Text was clipped")]
        result.raw = {"surface": {"kind": "cells", "rows": 6, "cols": 22}}
        return result

    env.pages.preview_page.side_effect = with_issue
    env.plugin.result = WriteResult(False, False)
    env.drive()
    read = getattr(env.service, "layout_diagnostics", None)
    assert callable(read), "retain the engine computation independently of output success"
    snapshot = read("b1")
    assert snapshot["scope"] == "engine_computation"
    assert snapshot["mode"] == "native"
    assert snapshot["complete"] is True
    assert snapshot["reference_id"] == "collection:test"
    assert [page["page_id"] for page in snapshot["pages"]] == ["pA", "pB"]
    assert snapshot["pages"][0]["issues"][0]["code"] == "truncated"
    assert "accepted" not in snapshot and "delivered" not in snapshot
    assert env.rt.last_active_page_id is None
    snapshot["pages"].clear()
    assert len(read("b1")["pages"]) == 2


def test_runtime_diagnostics_do_not_fabricate_a_record_for_an_unrendered_board(native_engine):  # noqa: F811
    read = getattr(native_engine.service, "layout_diagnostics", None)
    assert callable(read), "unrendered boards need an explicit absent computation"
    assert read("b1") is None
    assert read("missing") is None


def test_native_diagnostics_serialize_once_per_pass_and_keep_partial_failure(native_engine, monkeypatch):  # noqa: F811
    from src.layout.diagnostics import ComputationBuilder

    env = native_engine
    original = ComputationBuilder.snapshot
    serializations = []

    def snapshot(builder, *, complete):
        serializations.append(complete)
        return original(builder, complete=complete)

    monkeypatch.setattr(ComputationBuilder, "snapshot", snapshot)
    env.drive()
    assert serializations == [True]
    serializations.clear()
    preview = env.pages.preview_page.side_effect

    def failing_second(page_id, **kwargs):
        if page_id == "pB":
            raise ValueError("fixture render failure")
        return preview(page_id, **kwargs)

    env.pages.preview_page.side_effect = failing_second
    env.drive()
    assert serializations == [False]
    data = env.service.layout_diagnostics("b1")
    assert data["complete"] is False
    assert [page["page_id"] for page in data["pages"]] == ["pA"]


def test_runtime_diagnostics_resolve_the_legacy_primary_runtime_alias(native_engine):  # noqa: F811
    from src.settings.service import PRIMARY_RUNTIME_KEY

    env = native_engine
    env.drive()
    expected = env.service.layout_diagnostics("b1")
    env.service.runtimes = {PRIMARY_RUNTIME_KEY: env.rt}
    env.service._primary_board_id = PRIMARY_RUNTIME_KEY
    assert env.service.layout_diagnostics("b1") == expected


def test_diagnostics_bound_members_issues_paths_and_authored_strings():
    from types import SimpleNamespace

    from src.layout.diagnostics import ComputationBuilder

    builder = ComputationBuilder("collection:test", "native")
    issue = LayoutIssue(tuple("x" * 1000 for _ in range(30)), "truncated", "warning", "m" * 1000)
    result = SimpleNamespace(available=True, layout_issues=[issue] * 200, raw={"context": "must not retain"})
    for index in range(70):
        builder.add(SimpleNamespace(id=f"page-{index}", revision="r1"), result)
    data = builder.snapshot(complete=True).to_json()
    assert len(data["pages"]) == 64
    assert data["omitted_pages"] == 6
    assert sum(len(page["issues"]) for page in data["pages"]) == 128
    assert data["omitted_issues"] == 70 * 200 - 128
    retained = data["pages"][0]["issues"][0]
    assert len(retained["path"]) == 16
    assert retained["omitted_path_segments"] == 14
    assert len(retained["path"][0]) == 512
    assert len(retained["message"]) == 512
    assert data["truncated_strings"] > 0
    assert "must not retain" not in builder.snapshot(complete=True).encoded


def test_board_api_exposes_engine_computation_with_its_explicit_scope(client, monkeypatch):  # noqa: F811
    from types import SimpleNamespace

    from src.layout.diagnostics import ComputationBuilder
    from src.settings.service import get_settings_service
    from tests.test_per_board_engine import _board

    get_settings_service().set_boards([_board("b1", "Test")])
    record = ComputationBuilder("page:test", "page").snapshot(complete=True).to_json()
    service = SimpleNamespace(layout_diagnostics=lambda _: record, runtime_for=lambda _: None)
    monkeypatch.setattr("src.display_runtime.get_service", lambda: service)
    response = client.get("/v1/boards/b1")
    assert response.status_code == 200
    assert response.json()["last_layout_computation"] == record
