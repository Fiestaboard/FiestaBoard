"""Cross-grammar parity: chat op and MCP tool must persist identical state.

Issue #1764's acceptance test. For every operation both grammars can
express, the same logical call is executed twice against isolated stores —
once through the chat grammar (``src.ops.execute`` with the chat spelling
and chat-shaped args, validated by the same schemas ``parse_tool_call``
applies) and once through the registered MCP tool — and the persisted
state (pages.json, schedules.json, collections.json, config.json,
normalized for generated ids and timestamps) is compared.

Fail-first history
------------------

Run pre-unification with the chat path transcribed from what the web
client executes today (the REST handlers' service calls), three of these
scenarios failed — captured in ``.fail-first-1764.txt`` on the PR:

1. ``update_plugin_config`` replaced the stored config where
   ``configure_plugin`` merges; a partial second write dropped
   previously-set keys and 400'd on required-field validation.
2. ``update_collection`` with only ``interval_seconds`` forced
   ``selection_mode`` back to ``"time"`` on the chat path, while the MCP
   path preserved a variable-mode collection.
3. ``update_schedule`` on the MCP path passed every parameter explicitly,
   so ``model_dump(exclude_unset=True)`` saw the ``None``s as set and
   wiped ``end_time`` on any partial update.

The ops layer resolves both spellings of each op to one executor, which is
what makes these pass now; the remaining scenarios found no divergence and
land as a regression lock.

Not covered: ``set_active_page`` vs ``update_setting(active_page)`` —
both resolve to the same executor (asserted structurally in
tests/test_ops_registry.py), but executing it needs full board/render
wiring, the same reason tests/test_mcp_state_effects.py lists the tool as
UNCOVERED.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("mcp", reason="mcp package not installed")

from src.collections.models import CollectionCreate, TimeModeConfig, VariableModeConfig, VariableRule
from src.collections.service import CollectionService
from src.collections.storage import CollectionStorage
from src.config_manager import ConfigManager
from src.mcp_server import _build_mcp_server
from src.pages.models import PageCreate
from src.pages.service import PageService
from src.pages.storage import PageStorage
from src.schedules.service import ScheduleService
from src.schedules.storage import ScheduleStorage

# Real-plugin fixtures shared with the MCP state-effect suite.
from tests.test_mcp_state_effects import (
    PLUGIN_ID,
    UNINSTALLED_PLUGIN_ID,
    _LocalRegistry,
    _write_plugin,
)

FLAGSHIP_TEMPLATE = ["HELLO", "", "", "", "", ""]


# ---------------------------------------------------------------------------
# Isolated environment — one fresh set of stores per executed path
# ---------------------------------------------------------------------------


@contextmanager
def isolated_env(base: Path, with_plugins: bool = False):
    """Point every service singleton at throwaway storage under ``base``.

    Mirrors the ``services``/``plugins`` fixtures in
    tests/test_mcp_state_effects.py, packaged as a context manager so one
    test can stand up two sequential environments (one per path).
    """
    import src.plugins.registry as registry_module
    import src.templates.engine as engine_module

    base.mkdir(parents=True, exist_ok=True)
    mp = pytest.MonkeyPatch()
    pages = PageService(PageStorage(str(base / "pages.json")))
    schedules = ScheduleService(ScheduleStorage(str(base / "schedules.json")))
    collections = CollectionService(CollectionStorage(str(base / "collections.json")))
    ConfigManager._instance = None  # type: ignore[attr-defined]
    config = ConfigManager(config_path=str(base / "config.json"))

    mp.setattr("src.pages.service._page_service", pages)
    mp.setattr("src.schedules.service._schedule_service", schedules)
    mp.setattr("src.collections.service._collection_service", collections)
    mp.setattr("src.config_manager.ConfigManager._instance", config, raising=False)

    original_registry = registry_module._registry
    if with_plugins:
        builtin_dir = base / "builtin_plugins"
        builtin_dir.mkdir()
        external_dir = base / "external_plugins"
        external_dir.mkdir()
        staging_dir = base / "staged_plugins"
        _write_plugin(staging_dir / PLUGIN_ID, PLUGIN_ID)
        _write_plugin(staging_dir / UNINSTALLED_PLUGIN_ID, UNINSTALLED_PLUGIN_ID)
        registry = _LocalRegistry(builtin_dir, external_dir, staging_dir)
        registry.initialize()
        registry_module._registry = registry
        assert not registry.install_from_registry(PLUGIN_ID), "fixture failed to install the harness plugin"

    try:
        yield SimpleNamespace(base=base, pages=pages, schedules=schedules, collections=collections, config=config)
    finally:
        mp.undo()
        registry_module._registry = original_registry
        if engine_module._template_engine is not None:
            engine_module.reset_template_engine()
        ConfigManager._instance = None  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Snapshot + normalization
# ---------------------------------------------------------------------------

STORE_FILES = ("pages.json", "schedules.json", "collections.json", "config.json")
VOLATILE_KEYS = {"created_at", "updated_at", "installed_at", "last_updated"}


def _collect_ids(node: Any, ids: list[str]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "id" and isinstance(v, str) and v not in ids:
                ids.append(v)
            else:
                _collect_ids(v, ids)
    elif isinstance(node, list):
        for item in node:
            _collect_ids(item, ids)


def _scrub(node: Any, id_map: dict[str, str]) -> Any:
    if isinstance(node, dict):
        return {k: _scrub(v, id_map) for k, v in node.items() if k not in VOLATILE_KEYS}
    if isinstance(node, list):
        return [_scrub(x, id_map) for x in node]
    if isinstance(node, str) and node in id_map:
        return id_map[node]
    return node


def snapshot(env: SimpleNamespace) -> dict[str, Any]:
    """The persisted state, with generated ids and timestamps normalized.

    Ids are canonicalized in encounter order — both paths create objects
    in the same order, so matching structure maps to matching
    placeholders and any structural difference survives normalization.
    """
    raw: dict[str, Any] = {}
    for fname in STORE_FILES:
        path = env.base / fname
        raw[fname] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    ids: list[str] = []
    for fname in STORE_FILES:
        _collect_ids(raw[fname], ids)
    id_map = {v: f"<id{i}>" for i, v in enumerate(ids)}
    return {fname: _scrub(data, id_map) for fname, data in raw.items()}


# ---------------------------------------------------------------------------
# Drivers
# ---------------------------------------------------------------------------


class ChatOpFailure(AssertionError):
    """The chat endpoint refused an operation. Carries the HTTP status + detail."""

    def __init__(self, status_code: int, detail: Any) -> None:
        super().__init__(f"{status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


def chat(op: str, args: dict[str, Any]) -> Any:
    """The chat-grammar path — over HTTP, exactly as the browser calls it.

    Phase 2 Task 11: this driver used to call ``src.ops.execute`` in
    process. That could not see the failure mode this suite exists to
    prevent, because the shipped web client never called the ops layer at
    all — it ran its own per-op REST dispatcher, and had drifted from the
    executors in three places (see
    ``tests/test_chat_op_http_parity.py``). Posting to
    ``POST /ai/operations`` makes the "chat path" here the same code path
    the product ships.

    A refused operation raises, mirroring the MCP side's ``ToolError``.
    """
    from fastapi.testclient import TestClient

    from src.api_server import app

    response = TestClient(app).post("/ai/operations", json={"op": op, "args": args})
    if response.status_code != 200:
        raise ChatOpFailure(response.status_code, response.json().get("detail"))
    body = response.json()
    return {"status": "success", "message": body["message"], **body["result"]}


def mcp_call(mcp: Any, tool: str, /, **kwargs: Any) -> Any:
    """The MCP path: the registered tool, awaited when async."""
    fn = mcp._tool_manager._tools[tool].fn
    result = fn(**kwargs)
    if asyncio.iscoroutine(result):
        result = asyncio.run(result)
    return result


@pytest.fixture(scope="module")
def mcp():
    instance = _build_mcp_server()
    assert instance is not None, "mcp installed but _build_mcp_server() returned None"
    return instance


def assert_parity(tmp_path, chat_steps, mcp_steps, with_plugins=False, setup=None, changes_state=True):
    """Run both paths against fresh stores and compare persisted state.

    ``chat_state == mcp_state`` alone is not evidence. Now that both
    spellings resolve to one executor, two paths that each do *nothing*
    compare equal — so a scenario whose executor silently stopped working
    would still pass. Every scenario therefore also asserts that the run
    moved the store off its baseline; the one scenario that must not change
    state (the guarded ``update_plugin`` refusal) says so with
    ``changes_state=False`` and is checked for the opposite.
    """
    with isolated_env(tmp_path / "chat_path", with_plugins=with_plugins) as env:
        if setup:
            setup(env)
        chat_baseline = snapshot(env)
        chat_steps(env)
        chat_state = snapshot(env)
    with isolated_env(tmp_path / "mcp_path", with_plugins=with_plugins) as env:
        if setup:
            setup(env)
        mcp_baseline = snapshot(env)
        mcp_steps(env)
        mcp_state = snapshot(env)

    if changes_state:
        assert chat_state != chat_baseline, (
            "the chat path persisted no change at all — the parity comparison "
            "below would pass against an executor that does nothing"
        )
        assert mcp_state != mcp_baseline, (
            "the MCP path persisted no change at all — the parity comparison "
            "below would pass against an executor that does nothing"
        )
    else:
        assert chat_state == chat_baseline, "this scenario must leave the store untouched"
        assert mcp_state == mcp_baseline, "this scenario must leave the store untouched"

    assert chat_state == mcp_state, "the two grammars persisted different state for the same logical operation"


def _make_page(env, name: str = "P1") -> str:
    page = env.pages.create_page(
        PageCreate(name=name, type="template", device_type="flagship", template=FLAGSHIP_TEMPLATE)
    )
    return page.id


# ---------------------------------------------------------------------------
# Plugin operations
# ---------------------------------------------------------------------------


def test_parity_update_plugin_config_partial_second_write(tmp_path, mcp):
    """Fail-first divergence 1: replace-vs-merge on partial config updates."""

    def chat_steps(env):
        chat("update_plugin_config", {"plugin_id": PLUGIN_ID, "config": {"station_id": "9447427"}})
        chat("update_plugin_config", {"plugin_id": PLUGIN_ID, "config": {"api_key": "test_secret"}})

    def mcp_steps(env):
        mcp_call(mcp, "configure_plugin", plugin_id=PLUGIN_ID, config={"station_id": "9447427"})
        mcp_call(mcp, "configure_plugin", plugin_id=PLUGIN_ID, config={"api_key": "test_secret"})

    assert_parity(tmp_path, chat_steps, mcp_steps, with_plugins=True)


def test_parity_install_plugin(tmp_path, mcp):
    def chat_steps(env):
        chat("install_plugin", {"plugin_id": UNINSTALLED_PLUGIN_ID, "auto_enable": True})

    def mcp_steps(env):
        mcp_call(mcp, "install_plugin", plugin_id=UNINSTALLED_PLUGIN_ID, auto_enable=True)

    assert_parity(tmp_path, chat_steps, mcp_steps, with_plugins=True)


def test_parity_enable_disable_plugin(tmp_path, mcp):
    def chat_steps(env):
        chat("enable_plugin", {"plugin_id": PLUGIN_ID})
        chat("disable_plugin", {"plugin_id": PLUGIN_ID})
        chat("enable_plugin", {"plugin_id": PLUGIN_ID})

    def mcp_steps(env):
        mcp_call(mcp, "enable_plugin", plugin_id=PLUGIN_ID)
        mcp_call(mcp, "disable_plugin", plugin_id=PLUGIN_ID)
        mcp_call(mcp, "enable_plugin", plugin_id=PLUGIN_ID)

    assert_parity(tmp_path, chat_steps, mcp_steps, with_plugins=True)


def test_parity_uninstall_plugin(tmp_path, mcp):
    def chat_steps(env):
        chat("uninstall_plugin", {"plugin_id": PLUGIN_ID})

    def mcp_steps(env):
        mcp_call(mcp, "uninstall_plugin", plugin_id=PLUGIN_ID)

    assert_parity(tmp_path, chat_steps, mcp_steps, with_plugins=True)


def test_parity_update_plugin_rejects_builtins_identically(tmp_path, mcp):
    """The harness plugin has no git remote, so both paths must refuse and
    leave state untouched — the guarded error path is part of the contract."""

    def chat_steps(env):
        # Task 11: the endpoint turns the executor's error envelope into a
        # 400 rather than a 200 carrying {"status": "error"}.
        with pytest.raises(ChatOpFailure) as refused:
            chat("update_plugin", {"plugin_id": PLUGIN_ID})
        assert refused.value.status_code == 400

    def mcp_steps(env):
        # #1765: the MCP surface converts the executor's error envelope into
        # a raised ToolError (protocol isError). The *state* parity below is
        # unchanged — both grammars refuse and touch nothing.
        from mcp.server.mcpserver.exceptions import ToolError

        with pytest.raises(ToolError):
            mcp_call(mcp, "update_plugin", plugin_id=PLUGIN_ID)

    assert_parity(tmp_path, chat_steps, mcp_steps, with_plugins=True, changes_state=False)


# ---------------------------------------------------------------------------
# Schedule operations
# ---------------------------------------------------------------------------


def test_parity_schedule_lifecycle(tmp_path, mcp):
    """Fail-first divergence 3 lives in the update step: a partial
    update must not wipe the end_time either grammar set at creation."""

    ctx: dict[str, str] = {}

    def setup(env):
        ctx["page_id"] = _make_page(env)

    def chat_steps(env):
        created = chat(
            "create_schedule",
            {"page_id": ctx["page_id"], "start_time": "07:00", "end_time": "09:00", "day_pattern": "weekdays"},
        )
        chat("update_schedule", {"schedule_id": created["schedule_id"], "start_time": "08:00", "enabled": False})
        doomed = chat("create_schedule", {"page_id": ctx["page_id"], "start_time": "10:00", "day_pattern": "all"})
        chat("delete_schedule", {"schedule_id": doomed["schedule_id"]})

    def mcp_steps(env):
        created = mcp_call(
            mcp,
            "create_schedule",
            page_id=ctx["page_id"],
            start_time="07:00",
            end_time="09:00",
            day_pattern="weekdays",
        )
        mcp_call(mcp, "update_schedule", schedule_id=created["schedule_id"], start_time="08:00", enabled=False)
        doomed = mcp_call(mcp, "create_schedule", page_id=ctx["page_id"], start_time="10:00", day_pattern="all")
        mcp_call(mcp, "delete_schedule", schedule_id=doomed["schedule_id"])

    assert_parity(tmp_path, chat_steps, mcp_steps, setup=setup)


# ---------------------------------------------------------------------------
# Collection operations
# ---------------------------------------------------------------------------


def test_parity_update_collection_interval_on_variable_mode(tmp_path, mcp):
    """Fail-first divergence 2: an interval-only update must not flip a
    variable-mode collection back to time mode on either path."""

    ctx: dict[str, str] = {}

    def setup(env):
        page_id = _make_page(env)
        collection = env.collections.create_collection(
            CollectionCreate(
                name="VarCol",
                page_ids=[page_id],
                selection_mode="variable",
                time=TimeModeConfig(interval_seconds=30),
                variable=VariableModeConfig(
                    rules=[VariableRule(expression="1", page_id=page_id)],
                    default_page_id=page_id,
                    poll_seconds=10,
                ),
            )
        )
        ctx["collection_id"] = collection.id

    def chat_steps(env):
        chat("update_collection", {"collection_id": ctx["collection_id"], "interval_seconds": 45})

    def mcp_steps(env):
        mcp_call(mcp, "update_collection", collection_id=ctx["collection_id"], interval_seconds=45)

    assert_parity(tmp_path, chat_steps, mcp_steps, setup=setup)


def test_parity_collection_create_and_update(tmp_path, mcp):
    ctx: dict[str, str] = {}

    def setup(env):
        ctx["p1"] = _make_page(env, "P1")
        ctx["p2"] = _make_page(env, "P2")

    def chat_steps(env):
        created = chat(
            "create_collection",
            {"name": "Morning", "page_ids": [ctx["p1"], ctx["p2"]], "interval_seconds": 30},
        )
        chat(
            "update_collection",
            {"collection_id": created["collection_id"], "page_ids": [ctx["p2"], ctx["p1"]], "interval_seconds": 45},
        )

    def mcp_steps(env):
        created = mcp_call(
            mcp, "create_collection", name="Morning", page_ids=[ctx["p1"], ctx["p2"]], interval_seconds=30
        )
        mcp_call(
            mcp,
            "update_collection",
            collection_id=created["collection_id"],
            page_ids=[ctx["p2"], ctx["p1"]],
            interval_seconds=45,
        )

    assert_parity(tmp_path, chat_steps, mcp_steps, setup=setup)


# ---------------------------------------------------------------------------
# Page operations
# ---------------------------------------------------------------------------


def test_chat_has_no_server_side_page_creation_spelling(tmp_path, mcp):
    """Was ``test_parity_replace_page_vs_create_page`` (Phase 2 Task 11).

    That test asserted #1764's alias of ``replace_page`` onto
    ``create_page``. The alias was wrong: ``replace_page`` rewrites the
    page mounted in the editor — the system prompt calls it "destructive"
    and tells the global drawer to navigate to the editor rather than
    "write template content remotely" — and the shipped browser has always
    applied it there. The alias survived only because nothing on the chat
    path ever called the registry, and it "passed" parity only because
    both paths created a page in an empty store.

    The MCP tool keeps its executor; the chat endpoint refuses the op.
    """

    def chat_steps(env):
        with pytest.raises(ChatOpFailure) as refused:
            chat("replace_page", {"name": "Weather", "template": FLAGSHIP_TEMPLATE, "duration_seconds": 120})
        assert refused.value.status_code == 400
        assert "browser" in refused.value.detail

    def mcp_steps(env):
        pass  # no MCP counterpart: create_page is a different operation

    # Neither path may persist anything, so parity here is "both stores empty".
    assert_parity(tmp_path, chat_steps, mcp_steps)


def test_parity_create_page_is_mcp_only(tmp_path, mcp):
    """``create_page`` still persists a page through the MCP spelling."""
    with isolated_env(tmp_path / "mcp_only") as env:
        mcp_call(
            mcp,
            "create_page",
            name="Weather",
            template_lines=FLAGSHIP_TEMPLATE,
            device_type="flagship",
            duration_seconds=120,
        )
        assert [p.name for p in env.pages.list_pages()] == ["Weather"]


# ---------------------------------------------------------------------------
# Non-vacuity: the comparison must be able to fail
# ---------------------------------------------------------------------------


def test_snapshot_comparison_detects_a_real_state_difference(tmp_path, mcp):
    """Prove assert_parity is not comparing air: paths that genuinely
    persist different state must fail the comparison.

    The two paths here differ *and* one of them does nothing, so the
    do-nothing guard is what reports it. Both halves are exercised: this
    test for the guard, the one below for the comparison itself.
    """
    ctx: dict[str, str] = {}

    with pytest.raises(AssertionError, match="persisted no change at all"):
        assert_parity(
            tmp_path,
            lambda env: chat(
                "create_schedule", {"page_id": ctx["page_id"], "start_time": "07:00", "day_pattern": "all"}
            ),
            lambda env: None,  # the MCP path creates nothing
            setup=lambda env: ctx.__setitem__("page_id", _make_page(env)),
        )


def test_snapshot_comparison_detects_two_paths_that_both_act_but_differ(tmp_path, mcp):
    """Both paths persist something, so only the comparison can catch it.

    Deliberately not ``replace_page`` — that op is client-side since the ops
    wiring, so the chat path would refuse rather than persist and the
    do-nothing guard, not the comparison, would be what fired.
    """
    ctx: dict[str, str] = {}

    with pytest.raises(AssertionError, match="persisted different state"):
        assert_parity(
            tmp_path,
            lambda env: chat(
                "create_schedule", {"page_id": ctx["page_id"], "start_time": "07:00", "day_pattern": "all"}
            ),
            lambda env: mcp_call(
                mcp, "create_schedule", page_id=ctx["page_id"], start_time="09:30", day_pattern="all"
            ),
            setup=lambda env: ctx.__setitem__("page_id", _make_page(env)),
        )


def test_a_do_nothing_executor_no_longer_passes_parity(tmp_path, mcp):
    """The vacuity this guard exists to close.

    Before the baseline check, two paths that both did nothing compared
    equal and the scenario passed — so an executor that silently stopped
    persisting anything was invisible to this whole module.
    """

    with pytest.raises(AssertionError, match="persisted no change at all"):
        assert_parity(tmp_path, lambda env: None, lambda env: None)
