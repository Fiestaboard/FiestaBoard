"""First-party tools keep the revision read for a draft through mutation."""

import asyncio

import pytest

from src.mcp_server import _build_mcp_server
from src.ops import executors
from src.pages.models import PageCreate, PageUpdate
from src.pages.storage import PageRevisionConflict
from tests.test_op_parity import isolated_env


@pytest.fixture
def env(tmp_path):
    with isolated_env(tmp_path / "tools") as value:
        yield value


@pytest.fixture(scope="module")
def server():
    return _build_mcp_server()


@pytest.mark.parametrize(
    "name,id_field",
    [
        ("update_page", "page_id"),
        ("delete_page", "page_id"),
        ("update_collection", "collection_id"),
        ("delete_collection", "collection_id"),
        ("update_schedule", "schedule_id"),
        ("delete_schedule", "schedule_id"),
        ("set_default_page", "page_id"),
    ],
)
def test_mutation_tool_schema_requires_original_revision(server, name, id_field):
    tools = asyncio.run(server.list_tools())
    tool = next(t for t in tools if t.name == name)
    assert "expected_revision" in tool.input_schema["required"]
    assert tool.input_schema["properties"]["expected_revision"]["type"] == "string"
    assert id_field in tool.input_schema["required"]
    assert tool.annotations.idempotent_hint is False


@pytest.mark.parametrize(
    "name,args",
    [
        ("update_page", {"page_id": "missing", "name": "Draft"}),
        ("delete_page", {"page_id": "missing"}),
        ("update_collection", {"collection_id": "missing", "name": "Draft"}),
        ("delete_collection", {"collection_id": "missing"}),
        ("update_schedule", {"schedule_id": "missing", "enabled": False}),
        ("delete_schedule", {"schedule_id": "missing"}),
        ("set_default_page", {"page_id": None}),
    ],
)
@pytest.mark.parametrize("token", [None, "", "   "])
def test_executors_refuse_missing_original_revision_without_loading_service(monkeypatch, name, args, token):
    def forbidden():
        pytest.fail("A missing revision must not cause a service read or write")

    monkeypatch.setattr("src.pages.service.get_page_service", forbidden)
    monkeypatch.setattr("src.collections.service.get_collection_service", forbidden)
    monkeypatch.setattr("src.schedules.service.get_schedule_service", forbidden)
    result = getattr(executors, name)(**args, expected_revision=token)
    assert result["status"] == "error"
    assert result["error_code"] == "revision_required"
    assert "original" in result["error"].lower()


@pytest.mark.parametrize("first", ["native", "tool"])
def test_page_native_and_tool_save_order_preserves_first_writer(env, first):
    page = env.pages.create_page(
        PageCreate(name="Original", type="template", template=["{{red}}Hi", "", "", "", "", ""])
    )
    original = page.revision
    if first == "native":
        winner = env.pages.update_page(page.id, PageUpdate(name="Native", expected_revision=original))
        result = executors.update_page(page.id, name="Tool draft", expected_revision=original)
        assert result["error_code"] == "revision_conflict"
        assert "reconcile" in result["error"].lower()
    else:
        result = executors.update_page(page.id, name="Tool", expected_revision=original)
        assert result["status"] == "success"
        assert result["revision"] != original
        assert result["edit_protocol"] == "page-revision-v1"
        with pytest.raises(PageRevisionConflict):
            env.pages.update_page(page.id, PageUpdate(name="Native draft", expected_revision=original))
        winner = env.pages.get_page(page.id)
    stored = env.pages.get_page(page.id)
    assert stored.revision == winner.revision
    assert stored.template == page.template
    assert stored.name == ("Native" if first == "native" else "Tool")


def test_stale_page_tool_delete_keeps_page(env):
    page = env.pages.create_page(PageCreate(name="Original", type="template", template=["Hi", "", "", "", "", ""]))
    env.pages.update_page(page.id, PageUpdate(name="Native", expected_revision=page.revision))
    result = executors.delete_page(page.id, expected_revision=page.revision)
    assert result["error_code"] == "revision_conflict"
    assert env.pages.get_page(page.id).name == "Native"


@pytest.mark.parametrize("kind", ["collection", "schedule"])
@pytest.mark.parametrize("first", ["native", "tool"])
def test_content_native_and_tool_save_orders(env, kind, first):
    from src.collections.models import CollectionCreate, CollectionUpdate
    from src.schedules.models import ScheduleCreate, ScheduleUpdate

    page = env.pages.create_page(PageCreate(name="Page", type="template", template=["Hi", "", "", "", "", ""]))
    if kind == "collection":
        svc = env.collections
        content = svc.create_collection(CollectionCreate(name="Group", page_ids=[page.id]))
        change = CollectionUpdate(name="Native", expected_revision=content.revision)
        args = {"name": "Tool"}

        def update_model(revision):
            return CollectionUpdate(name="Native draft", expected_revision=revision)
    else:
        svc = env.schedules
        content = svc.create_schedule(ScheduleCreate(page_id=page.id, start_time="07:00", end_time="09:00"))
        change = ScheduleUpdate(enabled=False, expected_revision=content.revision)
        args = {"enabled": False}

        def update_model(revision):
            return ScheduleUpdate(start_time="08:00", expected_revision=revision)

    update = getattr(svc, "update_" + kind)
    get = getattr(svc, "get_" + kind)
    if first == "native":
        winner = update(content.id, change)
        result = getattr(executors, "update_" + kind)(
            **{kind + "_id": content.id}, **args, expected_revision=content.revision
        )
        assert result["error_code"] == "revision_conflict"
    else:
        result = getattr(executors, "update_" + kind)(
            **{kind + "_id": content.id}, **args, expected_revision=content.revision
        )
        assert result["status"] == "success"
        assert result["edit_protocol"] == kind + "-revision-v1"
        assert result["revision"] != content.revision
        with pytest.raises(PageRevisionConflict):
            update(content.id, update_model(content.revision))
        winner = get(content.id)
    stored = get(content.id)
    assert stored.revision == winner.revision
    if kind == "collection":
        assert stored.page_ids == [page.id]
        assert stored.time == content.time
    else:
        assert stored.page_id == page.id
        assert stored.end_time == "09:00"
    result = getattr(executors, "delete_" + kind)(**{kind + "_id": content.id}, expected_revision=content.revision)
    assert result["error_code"] == "revision_conflict"
    assert get(content.id) is not None


@pytest.mark.parametrize("first", ["native", "tool"])
def test_schedule_default_uses_original_default_revision(env, server, first):
    from tests.test_mcp_state_effects import call

    read = call(server, "list_schedules")
    revision = read["default_page_revision"]
    assert revision
    assert read["default_page_edit_protocol"] == "schedule-default-revision-v1"
    if first == "native":
        env.schedules.set_default_page(None, expected_revision=revision)
        result = executors.set_default_page(None, expected_revision=revision)
        assert result["error_code"] == "revision_conflict"
    else:
        result = executors.set_default_page(None, expected_revision=revision)
        assert result["status"] == "success"
        with pytest.raises(PageRevisionConflict):
            env.schedules.set_default_page(None, expected_revision=revision)


@pytest.mark.parametrize("kind", ["page", "collection", "schedule"])
def test_delayed_approval_keeps_staged_original_revision(env, server, kind):
    from src.ai.mcp_bridge import McpToolBackend
    from src.collections.models import CollectionCreate, CollectionUpdate
    from src.schedules.models import ScheduleCreate, ScheduleUpdate
    from tests.ai.test_agent import ScriptedProvider, _block, _only, _run_turn, _sse

    page = env.pages.create_page(PageCreate(name="Page", type="template", template=["Hi", "", "", "", "", ""]))
    if kind == "page":
        svc, content, change = env.pages, page, PageUpdate(name="Native", expected_revision=page.revision)
    elif kind == "collection":
        svc = env.collections
        content = svc.create_collection(CollectionCreate(name="Group", page_ids=[page.id]))
        change = CollectionUpdate(name="Native", expected_revision=content.revision)
    else:
        svc = env.schedules
        content = svc.create_schedule(ScheduleCreate(page_id=page.id, start_time="07:00"))
        change = ScheduleUpdate(enabled=False, expected_revision=content.revision)
    args = {kind + "_id": content.id, "expected_revision": content.revision}
    backend = McpToolBackend(server=server)
    messages = [{"role": "user", "content": "Delete this content"}]
    events = _run_turn(ScriptedProvider(_sse(_block("delete_" + kind, args))), backend, messages)
    pending = _only(events, "tool_call")[0]
    assert pending["args"] == args
    assert _only(events, "done")[0]["reason"] == "awaiting_approval"
    getattr(svc, "update_" + kind)(content.id, change)
    messages.append(
        {
            "role": "assistant",
            "content": "Delete",
            "tool_calls": [{"id": pending["id"], "name": "delete_" + kind, "args": pending["args"]}],
        }
    )
    provider = ScriptedProvider(_sse("The content changed. Please reconcile before deleting."))
    events = _run_turn(provider, backend, messages, resume={"tool_call_id": pending["id"], "decision": "approve"})
    outcome = _only(events, "tool_result")[0]
    assert outcome["status"] == "error"
    assert "reconcile" in outcome["error"]
    assert getattr(svc, "get_" + kind)(content.id) is not None
    assert "Do not automatically retry" in provider.messages_of(0)[-1]["content"]


@pytest.mark.parametrize(
    "op,args",
    [
        ("update_collection", {"collection_id": "group", "name": "Draft"}),
        ("update_schedule", {"schedule_id": "schedule", "enabled": False}),
        ("delete_schedule", {"schedule_id": "schedule"}),
    ],
)
def test_legacy_chat_grammar_requires_and_retains_original_revision(op, args):
    from src.ops.grammar import ToolCallValidationError, parse_tool_call

    with pytest.raises(ToolCallValidationError, match="expected_revision"):
        parse_tool_call({"op": op, "args": args})
    token = "original-generation"
    call = parse_tool_call({"op": op, "args": {**args, "expected_revision": token}})
    assert call.args.expected_revision == token


def test_catalog_teaches_conflict_reconciliation(server):
    from src.ai.mcp_bridge import McpToolBackend
    from src.ai.tool_catalog import ToolCatalog

    backend = McpToolBackend(server=server)
    catalog = ToolCatalog(asyncio.run(backend.list_tools()))
    prompt = catalog.render_addendum("global")
    assert "keep its original revision" in prompt
    assert "Never fetch a fresh" in prompt


def test_prompt_content_summaries_retain_read_revisions_and_protocols():
    from src.ai.prompt_builder import (
        _format_available_collections,
        _format_available_pages,
        _format_available_schedules,
    )

    for kind, formatter in [
        ("page", _format_available_pages),
        ("collection", _format_available_collections),
        ("schedule", _format_available_schedules),
    ]:
        summary = formatter(
            [{"id": "sample", "revision": "original-generation", "edit_protocol": kind + "-revision-v1"}]
        )
        assert "original-generation" in summary
        assert kind + "-revision-v1" in summary


@pytest.mark.parametrize("kind", ["collection", "schedule"])
def test_legacy_chat_dispatch_retains_expected_revision(env, kind):
    from src.collections.models import CollectionCreate
    from src.ops import execute_sync
    from src.schedules.models import ScheduleCreate

    page = env.pages.create_page(PageCreate(name="Page", type="template", template=["Hi", "", "", "", "", ""]))
    if kind == "collection":
        content = env.collections.create_collection(CollectionCreate(name="Group", page_ids=[page.id]))
        fields = {"name": "Changed"}
    else:
        content = env.schedules.create_schedule(ScheduleCreate(page_id=page.id, start_time="07:00"))
        fields = {"enabled": False}
    result = execute_sync(
        "update_" + kind, {kind + "_id": content.id, "expected_revision": content.revision, **fields}, grammar="chat"
    )
    assert result["status"] == "success"
    assert result["revision"] != content.revision


@pytest.mark.parametrize("kind", ["collection", "schedule"])
def test_legacy_chat_http_reports_stale_revision_as_412(env, kind):
    from fastapi.testclient import TestClient

    from src.api_server import app
    from src.collections.models import CollectionCreate, CollectionUpdate
    from src.schedules.models import ScheduleCreate, ScheduleUpdate

    page = env.pages.create_page(PageCreate(name="Page", type="template", template=["Hi", "", "", "", "", ""]))
    if kind == "collection":
        content = env.collections.create_collection(CollectionCreate(name="Group", page_ids=[page.id]))
        env.collections.update_collection(
            content.id, CollectionUpdate(name="Native", expected_revision=content.revision)
        )
        fields = {"name": "Stale draft"}
    else:
        content = env.schedules.create_schedule(ScheduleCreate(page_id=page.id, start_time="07:00"))
        env.schedules.update_schedule(content.id, ScheduleUpdate(enabled=False, expected_revision=content.revision))
        fields = {"enabled": True}
    response = TestClient(app).post(
        "/ai/operations",
        json={
            "op": "update_" + kind,
            "args": {kind + "_id": content.id, "expected_revision": content.revision, **fields},
        },
    )
    assert response.status_code == 412
    assert "reconcile" in response.json()["detail"]


@pytest.mark.parametrize("kind", ["page", "collection", "schedule"])
@pytest.mark.parametrize("first", ["native", "tool"])
def test_native_http_and_mcp_tool_are_conditional_in_both_save_orders(env, server, kind, first):
    from fastapi.testclient import TestClient

    from src.ai.mcp_bridge import McpToolBackend
    from src.api_server import app
    from src.collections.models import CollectionCreate
    from src.schedules.models import ScheduleCreate

    page = env.pages.create_page(PageCreate(name="Page", type="template", template=["Hi", "", "", "", "", ""]))
    if kind == "page":
        content, changes = page, {"name": "Changed"}
    elif kind == "collection":
        content = env.collections.create_collection(CollectionCreate(name="Group", page_ids=[page.id]))
        changes = {"name": "Changed"}
    else:
        content = env.schedules.create_schedule(ScheduleCreate(page_id=page.id, start_time="07:00"))
        changes = {"enabled": False}
    client = TestClient(app)
    backend = McpToolBackend(server=server)
    path = f"/v1/{kind}s/{content.id}"
    original = client.get(path).json()
    assert original["revision"] == content.revision
    assert original["edit_protocol"] == kind + "-revision-v1"
    if kind == "page":
        assert original["document_protocol"] == "page-document-v1"
    args = {kind + "_id": content.id, "expected_revision": content.revision, **changes}

    def native_save():
        return client.put(path, json={"expected_revision": content.revision, **changes})

    def tool_save():
        return asyncio.run(backend.call_tool("update_" + kind, args))

    if first == "native":
        assert native_save().status_code == 200
        result = tool_save()
        assert result.status == "error"
        assert "reconcile" in result.error
    else:
        assert tool_save().status == "ok"
        assert native_save().status_code == 412
    saved = client.get(path).json()
    assert saved["revision"] != original["revision"]
    assert all(saved[key] == value for key, value in changes.items())


def test_catalog_binds_existing_editor_drafts_to_their_seed_revision(server):
    from src.ai.mcp_bridge import McpToolBackend
    from src.ai.tool_catalog import ToolCatalog

    prompt = ToolCatalog(asyncio.run(McpToolBackend(server=server).list_tools())).render_addendum("editor")
    assert "current_page" in prompt and "supplied revision" in prompt
    assert "never replace it with a later read" in prompt
