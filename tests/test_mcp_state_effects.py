"""MCP tools must actually change state — asserted by re-reading, not by mocks.

Why this file exists
--------------------

``tests/test_mcp_server.py`` mocks every service. That is fine for checking
argument plumbing, but it cannot answer the only question that matters to a
user: *did anything happen?* #1559/#1561 is what that gap costs —
``set_active_page`` and ``set_schedule_mode`` called methods that have never
existed, caught their own AttributeError, returned it as an error string, and
were complete no-ops in every release shipped. One of them was never even
reported.

The rule here is simple and is what makes the suite non-vacuous:

    Every assertion is on state read back *after* the call, through a
    different tool or the service itself. Never on a call record.

Nothing is mocked. Real ``PageService``, ``ScheduleService``,
``CollectionService`` and ``ConfigManager`` instances run against files in
``tmp_path``. A tool calling a method that does not exist therefore raises
instead of being conjured, and a tool that returns ``{"status": "ok"}``
while writing nothing fails its re-read.

Coverage floor
--------------

``test_every_tool_has_a_state_effect_case`` fails when a tool is registered
without an entry in ``COVERED`` or ``UNCOVERED``. A new tool cannot be added
without someone deciding, in writing, whether it gets a state-effect test.
Tools in ``UNCOVERED`` carry a reason — that list is a to-do, not a
permanent exemption.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("mcp", reason="mcp package not installed")

from src.collections.service import CollectionService
from src.collections.storage import CollectionStorage
from src.config_manager import ConfigManager
from src.mcp_server import _build_mcp_server
from src.pages.service import PageService
from src.pages.storage import PageStorage
from src.plugins.loader import PluginLoader
from src.plugins.registry import PluginRegistry
from src.schedules.service import ScheduleService
from src.schedules.storage import ScheduleStorage

# ---------------------------------------------------------------------------
# Tool coverage ledger
# ---------------------------------------------------------------------------

#: Tools with a state-effect or shape assertion in this module — or, for the
#: Settings-page tools (boards, panels, network, system, debug), in the
#: sibling module ``tests/test_mcp_state_effects_settings.py``, which reuses
#: the fixtures below and pins the same rule: every assertion is on state
#: read back, or on the call that crossed a patched hardware/sidecar boundary.
COVERED = {
    "list_pages",
    "get_page",
    "create_page",
    "update_page",
    "delete_page",
    "render_page_preview",
    "list_schedules",
    "create_schedule",
    "update_schedule",
    "delete_schedule",
    "list_collections",
    "create_collection",
    "update_collection",
    "delete_collection",
    "get_template_variables",
    "get_system_status",
    "get_settings_summary",
    "list_installed_plugins",
    "install_plugin",
    "enable_plugin",
    "disable_plugin",
    "uninstall_plugin",
    "configure_plugin",
    "get_plugin_data",
    "update_plugin",
    "set_active_page",
    "set_schedule_mode",
    "get_active_page",
    "get_board_content",
    "send_message",
    "preview_saved_page",
    "validate_template",
    "update_setting",
    # Page editor parity: every field the editor saves, share strings,
    # staff picks, the live display, and the Transition Lab.
    "export_page",
    "import_page",
    "list_staff_picks",
    "import_staff_pick",
    "get_current_display",
    "list_transition_plugins",
    "test_transition_live",
    "restore_board",
    "list_formula_functions",
    # Integrations-page coverage: instances, demo pages, updates, discovery.
    "list_plugin_instances",
    "create_plugin_instance",
    "delete_plugin_instance",
    "get_plugin_demo_page",
    "create_plugin_demo_page",
    "list_pending_plugin_updates",
    "check_plugin_updates",
    "update_all_plugins",
    "list_plugin_options",
    "get_plugin_manifest",
    "list_plugin_errors",
    # Schedules-page and Home-page coverage
    "validate_schedules",
    "set_default_page",
    "get_temporary_override",
    "set_temporary_override",
    "cancel_temporary_override",
    "force_refresh",
    "get_silence_status",
    "pause_board",
    "resume_board",
    # Settings-page coverage — tests/test_mcp_state_effects_settings.py
    "update_board",
    "add_board",
    "remove_board",
    "detect_board_size",
    "identify_tile",
    "list_panels",
    "create_panel",
    "update_panel",
    "delete_panel",
    "disconnect_wifi",
    "forget_wifi_network",
    "check_for_update",
    "trigger_system_update",
    "restart_system",
    "shutdown_system",
    "export_backup",
    "test_ai_provider",
    "blank_board",
    "fill_board",
    "show_board_debug_info",
    "run_network_diagnostics",
    "clear_board_cache",
}

#: Tools not yet covered here, each with the reason. Not an exemption list.
UNCOVERED = {
    "list_registry_plugins": "hits the network-backed registry; needs a fixture",
}


# ---------------------------------------------------------------------------
# Fixtures — real services, real files, no mocks
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def mcp():
    instance = _build_mcp_server()
    assert instance is not None, "mcp installed but _build_mcp_server() returned None"
    return instance


@pytest.fixture
def services(tmp_path, monkeypatch):
    """Point every service singleton at throwaway storage under tmp_path."""
    pages = PageService(PageStorage(str(tmp_path / "pages.json")))
    schedules = ScheduleService(ScheduleStorage(str(tmp_path / "schedules.json")))
    collections = CollectionService(CollectionStorage(str(tmp_path / "collections.json")))

    # conftest's autouse ``_isolated_data_dir`` (#1762) dropped the singleton
    # already; constructing installs this one, and conftest drops it again.
    config = ConfigManager(config_path=str(tmp_path / "config.json"))

    monkeypatch.setattr("src.pages.service._page_service", pages)
    monkeypatch.setattr("src.schedules.service._schedule_service", schedules)
    monkeypatch.setattr("src.collections.service._collection_service", collections)
    monkeypatch.setattr("src.config_manager.ConfigManager._instance", config, raising=False)

    yield {
        "pages": pages,
        "schedules": schedules,
        "collections": collections,
        "config": config,
    }


# ---------------------------------------------------------------------------
# Plugin fixture — a real plugin package on disk, loaded by the real loader
# ---------------------------------------------------------------------------

#: Installed by the fixture before each test.
PLUGIN_ID = "harness_tide"

#: Staged but *not* installed, so install_plugin() has something to install.
UNINSTALLED_PLUGIN_ID = "harness_surf"


def _manifest(plugin_id: str, version: str = "1.0.0") -> dict[str, Any]:
    return {
        "id": plugin_id,
        "name": plugin_id.replace("_", " ").title(),
        "version": version,
        "description": "Fixture plugin for MCP state-effect tests.",
        "author": "FiestaBoard Tests",
        "icon": "puzzle",
        "category": "utility",
        "settings_schema": {
            "type": "object",
            "properties": {
                # A remote-options picker, so list_plugin_options has a real
                # provider to browse (the plugin's get_options below).
                "station_id": {
                    "type": "string",
                    "title": "Station ID",
                    "ui:widget": "remote-options",
                    "ui:options": {"options_id": "stations"},
                },
                "api_key": {"type": "string", "title": "API Key", "ui:widget": "password"},
                "enabled": {"type": "boolean", "title": "Enabled", "default": False},
            },
            "required": ["station_id"],
        },
        # One demo template per device shape, so create_plugin_demo_page has
        # something to build and get_plugin_demo_page something to find.
        "demo": {
            "flagship": {
                "name": "Harness Demo",
                "template": [f"TIDE {{{{{plugin_id}.next_high}}}}", "", "", "", "", ""],
            },
            "note": {
                "name": "Harness Demo",
                "template": [f"{{{{{plugin_id}.next_high}}}}", "", ""],
            },
        },
        "variables": {
            "simple": {
                "next_high": {
                    "description": "Time of the next high tide",
                    "type": "string",
                    "max_length": 5,
                    "example": "06:12",
                },
                "board_cols": {
                    "description": "Column count of the board being rendered on",
                    "type": "string",
                    "max_length": 8,
                    "example": "22",
                },
            }
        },
    }


#: ``station_id`` is required by ``validate_config``, which is what makes
#: "configure_plugin swallows validation errors" testable.
_PLUGIN_SOURCE = '''\
"""Fixture plugin for tests/test_mcp_state_effects.py."""

from src.plugins.base import PluginBase, PluginResult


class HarnessPlugin(PluginBase):
    @property
    def plugin_id(self) -> str:
        return "{plugin_id}"

    def validate_config(self, config):
        if not config.get("station_id"):
            return ["station_id is required"]
        return []

    def fetch_data(self) -> PluginResult:
        # board_cols makes render fidelity observable: a render that builds
        # its plugin context WITHOUT a BoardContext sees "no-board" here.
        board = getattr(self, "board", None)
        cols = str(board.cols) if board is not None else "no-board"
        return PluginResult(available=True, data={{"next_high": "06:12", "board_cols": cols}})

    def get_options(self, request):
        # The catalog behind the ``stations`` remote-options picker. Search is
        # server-side so list_plugin_options(query=...) is observable.
        from src.plugins.base import Option, OptionsResult

        stations = [("9414290", "Golden Gate"), ("8518750", "The Battery")]
        query = (request.query or "").lower()
        options = [Option(value=v, label=name) for v, name in stations if query in name.lower()]
        return OptionsResult(options=options, total=len(options))
'''


def _write_plugin(directory: Path, plugin_id: str, version: str = "1.0.0") -> None:
    """Write a real, loadable plugin package to *directory*."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "manifest.json").write_text(json.dumps(_manifest(plugin_id, version)), encoding="utf-8")
    (directory / "__init__.py").write_text(_PLUGIN_SOURCE.format(plugin_id=plugin_id), encoding="utf-8")


class _LocalRegistry(PluginRegistry):
    """A real registry whose "registry install" copies from a local staging dir.

    Everything after the copy is the production code path: the real
    ``PluginLoader`` imports the package, and the real bookkeeping runs. Only
    the git clone is replaced, so ``install_plugin`` can be exercised without
    the network.
    """

    def __init__(self, plugins_dir: Path, external_dir: Path, staging_dir: Path):
        super().__init__(plugins_dir=plugins_dir)
        self._loader = PluginLoader(plugins_dir=plugins_dir, external_dirs=[external_dir])
        self._external_dir = external_dir
        self._staging_dir = staging_dir

    def install_from_registry(self, plugin_id: str) -> list[str]:
        staged = self._staging_dir / plugin_id
        if not staged.is_dir():
            return [f"Plugin '{plugin_id}' not found in the registry"]

        shutil.copytree(staged, self._external_dir / plugin_id, dirs_exist_ok=True)

        plugin = self._loader.load_plugin(plugin_id)
        if plugin is None:
            return self._loader.load_errors.get(plugin_id, []) or [f"Failed to load plugin: {plugin_id}"]

        manifest = self._loader.get_manifest(plugin_id)
        assert manifest is not None
        self._plugins[plugin_id] = plugin
        self._manifests[plugin_id] = manifest
        self._enabled[plugin_id] = False
        self._clear_removed_tombstone(plugin_id)
        return []


@pytest.fixture
def plugins(services, tmp_path):
    """Install ``harness_tide`` into a real registry wired to the singleton.

    ``harness_surf`` is staged but left uninstalled so ``install_plugin`` has
    a target. Both live under ``tmp_path``; nothing touches the repo's own
    ``plugins/`` or ``external_plugins/`` directories.

    Teardown is hand-rolled rather than left to ``monkeypatch`` because the
    order matters. The REST handlers these tools delegate to call
    ``reset_template_engine()``, and ``TemplateEngine.reset_cache()`` binds
    ``get_plugin_registry()`` onto the long-lived engine singleton. Restoring
    ``_registry`` alone would leave that engine holding this throwaway
    registry — which knows only about the harness plugins — and every later
    test in the session would find ``date_time`` and friends missing. So the
    registry is put back first, and only then is the engine rebound to it.
    """
    import src.plugins.registry as registry_module
    import src.templates.engine as engine_module

    builtin_dir = tmp_path / "builtin_plugins"
    builtin_dir.mkdir()
    external_dir = tmp_path / "external_plugins"
    external_dir.mkdir()
    staging_dir = tmp_path / "staged_plugins"

    _write_plugin(staging_dir / PLUGIN_ID, PLUGIN_ID)
    _write_plugin(staging_dir / UNINSTALLED_PLUGIN_ID, UNINSTALLED_PLUGIN_ID)

    original_registry = registry_module._registry

    def build_registry() -> _LocalRegistry:
        registry = _LocalRegistry(builtin_dir, external_dir, staging_dir)
        registry.initialize()
        registry_module._registry = registry
        return registry

    registry = build_registry()
    assert not registry.install_from_registry(PLUGIN_ID), "fixture failed to install the harness plugin"

    try:
        yield {
            "registry": registry,
            "config_path": str(tmp_path / "config.json"),
            # Rebuild the registry and ConfigManager from the same files —
            # what `docker compose up -d` does to a container.
            "restart": lambda: (_restart_config_manager(str(tmp_path / "config.json")), build_registry())[1],
        }
    finally:
        registry_module._registry = original_registry
        if engine_module._template_engine is not None:
            engine_module.reset_template_engine()


def _restart_config_manager(config_path: str) -> ConfigManager:
    """Drop the ConfigManager singleton and re-read the file from disk."""
    ConfigManager._instance = None  # type: ignore[attr-defined]
    return ConfigManager(config_path=config_path)


def stored_plugin_config(config_path: str, plugin_id: str) -> dict[str, Any] | None:
    """Read a plugin's config straight out of ``config.json``.

    Deliberately bypasses ConfigManager: the whole bug is that the in-memory
    copy looked right while the file had nothing in it.
    """
    raw = json.loads(Path(config_path).read_text(encoding="utf-8"))
    return raw.get("plugins", {}).get(plugin_id)


def call(mcp: Any, tool_name: str, /, **kwargs: Any) -> Any:
    """Invoke a registered MCP tool, awaiting it if it is async.

    Both leading parameters are positional-only: several tools take their
    own ``name`` argument, which would otherwise collide with this
    helper's signature.
    """
    tool = mcp._tool_manager._tools.get(tool_name)
    if tool is None:
        raise KeyError(f"tool {tool_name!r} is not registered; have: {sorted(mcp._tool_manager._tools)}")
    result = tool.fn(**kwargs)
    if asyncio.iscoroutine(result):
        result = asyncio.run(result)
    return result


def call_expect_error(mcp: Any, tool_name: str, /, **kwargs: Any) -> str:
    """Invoke a tool whose failure is the point; return its error message.

    #1765 contract reversal: failures used to be *successful* results whose
    payload said ``{"status": "error"}``; a failing tool now raises
    ToolError (protocol ``isError`` on the wire — pinned end-to-end by
    tests/test_mcp_server.py::TestProtocolIsError). Every error-path test
    below asserts on the raised message instead of the old envelope.
    """
    from mcp.server.mcpserver.exceptions import ToolError

    with pytest.raises(ToolError) as excinfo:
        call(mcp, tool_name, **kwargs)
    return str(excinfo.value)


def assert_ok(result: Any, what: str) -> Any:
    """Fail with the tool's own error string rather than a shape mismatch.

    Tools catch their exceptions and return ``{"error": "..."}``. Without
    this, a broken tool surfaces as a confusing KeyError three lines later.
    """
    if isinstance(result, dict) and result.get("error"):
        pytest.fail(f"{what} returned an error instead of doing the work: {result['error']}")
    return result


FLAGSHIP_TEMPLATE = ["HELLO", "", "", "", "", ""]


# ---------------------------------------------------------------------------
# Coverage floor
# ---------------------------------------------------------------------------


def test_every_tool_has_a_state_effect_case(mcp):
    registered = set(mcp._tool_manager._tools)
    accounted = COVERED | set(UNCOVERED)
    unaccounted = registered - accounted
    assert not unaccounted, (
        f"these MCP tools have no state-effect case and no recorded reason for not having one: {sorted(unaccounted)}"
    )


def test_coverage_ledger_has_no_phantom_entries(mcp):
    """The ledger must describe the real registry, not a stale copy."""
    registered = set(mcp._tool_manager._tools)
    phantom = (COVERED | set(UNCOVERED)) - registered
    assert not phantom, f"ledger names tools that are not registered: {sorted(phantom)}"


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


def test_create_page_persists_and_is_visible_to_list_pages(mcp, services):
    before = assert_ok(call(mcp, "list_pages"), "list_pages")
    before_ids = {p["id"] for p in before}

    created = assert_ok(
        call(
            mcp,
            "create_page",
            name="Harness Page",
            template_lines=FLAGSHIP_TEMPLATE,
            device_type="flagship",
        ),
        "create_page",
    )

    after = assert_ok(call(mcp, "list_pages"), "list_pages")
    after_ids = {p["id"] for p in after}
    new_ids = after_ids - before_ids

    assert len(new_ids) == 1, "create_page did not add exactly one page"
    assert created["page_id"] in new_ids
    assert any(p["name"] == "Harness Page" for p in after)


def test_create_page_writes_through_to_storage(mcp, services):
    """Re-read from a *fresh* service over the same file.

    Catches a tool that mutates the in-memory cache but never persists.
    """
    assert_ok(
        call(mcp, "create_page", name="Durable", template_lines=FLAGSHIP_TEMPLATE, device_type="flagship"),
        "create_page",
    )
    reloaded = PageService(PageStorage(str(services["pages"].storage.storage_file)))
    assert any(p.name == "Durable" for p in reloaded.list_pages())


def test_get_page_returns_the_page_that_was_created(mcp, services):
    created = assert_ok(
        call(mcp, "create_page", name="Fetch Me", template_lines=FLAGSHIP_TEMPLATE, device_type="flagship"),
        "create_page",
    )
    fetched = assert_ok(call(mcp, "get_page", page_id=created["page_id"]), "get_page")
    assert fetched["name"] == "Fetch Me"


def test_update_page_changes_the_stored_name(mcp, services):
    created = assert_ok(
        call(mcp, "create_page", name="Before", template_lines=FLAGSHIP_TEMPLATE, device_type="flagship"),
        "create_page",
    )
    page_id = created["page_id"]

    assert_ok(call(mcp, "update_page", page_id=page_id, name="After"), "update_page")

    refetched = assert_ok(call(mcp, "get_page", page_id=page_id), "get_page")
    assert refetched["name"] == "After", "update_page reported success but the name did not change"


def test_update_page_name_only_does_not_wipe_the_template(mcp, services):
    """Regression: a rename over MCP used to fail outright.

    ``PageService.update_page`` merges with
    ``model_dump(exclude_unset=True)``, where "unset" means *not passed to
    the constructor* — an explicit ``None`` counts as set. The tool passed
    name/template/duration unconditionally, so every partial update sent
    ``template=None``, wiped the template, and failed validation with
    "Template page requires template content".
    """
    created = assert_ok(
        call(mcp, "create_page", name="Before", template_lines=FLAGSHIP_TEMPLATE, device_type="flagship"),
        "create_page",
    )
    page_id = created["page_id"]

    assert_ok(call(mcp, "update_page", page_id=page_id, name="After"), "update_page (name only)")

    page = assert_ok(call(mcp, "get_page", page_id=page_id), "get_page")
    assert page["name"] == "After"
    assert page["template"] == FLAGSHIP_TEMPLATE, "renaming a page destroyed its template"


def test_update_page_duration_only_does_not_wipe_the_template(mcp, services):
    created = assert_ok(
        call(mcp, "create_page", name="Timed", template_lines=FLAGSHIP_TEMPLATE, device_type="flagship"),
        "create_page",
    )
    page_id = created["page_id"]

    assert_ok(call(mcp, "update_page", page_id=page_id, duration_seconds=90), "update_page (duration only)")

    page = assert_ok(call(mcp, "get_page", page_id=page_id), "get_page")
    assert page["duration_seconds"] == 90
    assert page["template"] == FLAGSHIP_TEMPLATE, "changing duration destroyed the template"
    assert page["name"] == "Timed", "changing duration destroyed the name"


def test_update_page_with_no_fields_is_reported_not_silently_ignored(mcp, services):
    created = assert_ok(
        call(mcp, "create_page", name="Untouched", template_lines=FLAGSHIP_TEMPLATE, device_type="flagship"),
        "create_page",
    )
    message = call_expect_error(mcp, "update_page", page_id=created["page_id"])
    assert "Nothing to update" in message, "a no-op update should say so, not report success"


def test_delete_page_removes_it_from_list_pages(mcp, services):
    created = assert_ok(
        call(mcp, "create_page", name="Doomed", template_lines=FLAGSHIP_TEMPLATE, device_type="flagship"),
        "create_page",
    )
    page_id = created["page_id"]

    assert_ok(call(mcp, "delete_page", page_id=page_id), "delete_page")

    remaining = assert_ok(call(mcp, "list_pages"), "list_pages")
    assert page_id not in {p["id"] for p in remaining}


def test_render_page_preview_renders_a_template_without_saving_it(mcp, services):
    """Preview takes raw ``template_lines``, not a saved page id.

    Asserts the no-save contract too: previewing must not create a page.
    """
    before = assert_ok(call(mcp, "list_pages"), "list_pages")

    preview = assert_ok(
        call(mcp, "render_page_preview", template_lines=FLAGSHIP_TEMPLATE, device_type="flagship"),
        "render_page_preview",
    )
    assert preview, "render_page_preview returned nothing"

    after = assert_ok(call(mcp, "list_pages"), "list_pages")
    assert len(after) == len(before), "render_page_preview persisted a page; it should not"


# ---------------------------------------------------------------------------
# Schedules
# ---------------------------------------------------------------------------


def _make_page(mcp, name: str = "Scheduled") -> str:
    created = assert_ok(
        call(mcp, "create_page", name=name, template_lines=FLAGSHIP_TEMPLATE, device_type="flagship"),
        "create_page",
    )
    return created["page_id"]


def test_create_schedule_persists_and_is_visible_to_list_schedules(mcp, services):
    page_id = _make_page(mcp)
    before = assert_ok(call(mcp, "list_schedules"), "list_schedules")
    before_ids = {s["id"] for s in before["schedules"]}

    assert_ok(
        call(mcp, "create_schedule", page_id=page_id, start_time="08:00", day_pattern="all"),
        "create_schedule",
    )

    after = assert_ok(call(mcp, "list_schedules"), "list_schedules")
    assert len(({s["id"] for s in after["schedules"]}) - before_ids) == 1


def test_update_schedule_changes_the_stored_start_time(mcp, services):
    page_id = _make_page(mcp)
    created = assert_ok(
        call(mcp, "create_schedule", page_id=page_id, start_time="08:00", day_pattern="all"),
        "create_schedule",
    )
    schedule_id = created["schedule_id"]

    assert_ok(call(mcp, "update_schedule", schedule_id=schedule_id, start_time="09:30"), "update_schedule")

    after = assert_ok(call(mcp, "list_schedules"), "list_schedules")
    stored = next(s for s in after["schedules"] if s["id"] == schedule_id)
    assert stored["start_time"] == "09:30", "update_schedule reported success but start_time did not change"


def test_update_schedule_preserves_end_time_on_partial_update(mcp, services):
    """Wipe-protection: a partial update that does not mention end_time must
    leave a stored end_time untouched (the #1764 exclude_unset contract)."""
    page_id = _make_page(mcp)
    created = assert_ok(
        call(mcp, "create_schedule", page_id=page_id, start_time="08:00", end_time="17:00", day_pattern="all"),
        "create_schedule",
    )
    schedule_id = created["schedule_id"]

    assert_ok(call(mcp, "update_schedule", schedule_id=schedule_id, start_time="09:30"), "update_schedule")

    after = assert_ok(call(mcp, "list_schedules"), "list_schedules")
    stored = next(s for s in after["schedules"] if s["id"] == schedule_id)
    assert stored["end_time"] == "17:00", "a partial update wiped end_time"


def test_update_schedule_clear_end_time_makes_the_entry_open_ended(mcp, services):
    """Intentional clear: clear_end_time=True must null a stored end_time.

    The wipe-protection above means an explicit end_time=None is
    indistinguishable from "unchanged" — the tool silently no-oped with
    success and there was NO way to make a bounded entry open-ended again
    (#1873/#1874 review). The explicit flag is the escape hatch.
    """
    page_id = _make_page(mcp)
    created = assert_ok(
        call(mcp, "create_schedule", page_id=page_id, start_time="08:00", end_time="17:00", day_pattern="all"),
        "create_schedule",
    )
    schedule_id = created["schedule_id"]

    assert_ok(
        call(mcp, "update_schedule", schedule_id=schedule_id, clear_end_time=True),
        "update_schedule",
    )

    after = assert_ok(call(mcp, "list_schedules"), "list_schedules")
    stored = next(s for s in after["schedules"] if s["id"] == schedule_id)
    assert stored.get("end_time") is None, "clear_end_time=True did not clear the stored end_time"


def test_update_schedule_clear_custom_days_drops_the_stale_day_list(mcp, services):
    """clear_custom_days: switching a custom entry back to an every-day
    pattern can drop the stale day list in the same call."""
    from src.ops import executors as ops_executors

    page_id = _make_page(mcp)
    # custom_days exists only on the canonical op / chat grammar (the MCP
    # create tool never sends it), so create through the op layer directly.
    created = assert_ok(
        ops_executors.create_schedule(
            page_id=page_id,
            start_time="08:00",
            day_pattern="custom",
            custom_days=["monday", "friday"],
        ),
        "create_schedule",
    )
    schedule_id = created["schedule_id"]

    assert_ok(
        call(mcp, "update_schedule", schedule_id=schedule_id, day_pattern="all", clear_custom_days=True),
        "update_schedule",
    )

    after = assert_ok(call(mcp, "list_schedules"), "list_schedules")
    stored = next(s for s in after["schedules"] if s["id"] == schedule_id)
    assert stored["day_pattern"] == "all"
    assert not stored.get("custom_days"), "clear_custom_days=True left the stale custom day list behind"


def test_delete_schedule_removes_it(mcp, services):
    page_id = _make_page(mcp)
    created = assert_ok(
        call(mcp, "create_schedule", page_id=page_id, start_time="08:00", day_pattern="all"),
        "create_schedule",
    )
    schedule_id = created["schedule_id"]

    assert_ok(call(mcp, "delete_schedule", schedule_id=schedule_id), "delete_schedule")

    after = assert_ok(call(mcp, "list_schedules"), "list_schedules")
    assert schedule_id not in {s["id"] for s in after["schedules"]}


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------


def test_create_collection_persists_and_is_visible_to_list_collections(mcp, services):
    page_id = _make_page(mcp, "In A Collection")
    before = assert_ok(call(mcp, "list_collections"), "list_collections")
    before_ids = {c["id"] for c in before}

    assert_ok(call(mcp, "create_collection", name="Harness Collection", page_ids=[page_id]), "create_collection")

    after = assert_ok(call(mcp, "list_collections"), "list_collections")
    assert len(({c["id"] for c in after}) - before_ids) == 1
    assert any(c["name"] == "Harness Collection" for c in after)


def test_update_collection_changes_the_stored_name(mcp, services):
    page_id = _make_page(mcp, "Collected")
    created = assert_ok(call(mcp, "create_collection", name="Before", page_ids=[page_id]), "create_collection")
    collection_id = created["collection_id"]

    assert_ok(call(mcp, "update_collection", collection_id=collection_id, name="After"), "update_collection")

    after = assert_ok(call(mcp, "list_collections"), "list_collections")
    stored = next(c for c in after if c["id"] == collection_id)
    assert stored["name"] == "After", "update_collection reported success but the name did not change"


def test_delete_collection_removes_it(mcp, services):
    page_id = _make_page(mcp, "Temporary")
    created = assert_ok(call(mcp, "create_collection", name="Doomed", page_ids=[page_id]), "create_collection")
    collection_id = created["collection_id"]

    assert_ok(call(mcp, "delete_collection", collection_id=collection_id), "delete_collection")

    after = assert_ok(call(mcp, "list_collections"), "list_collections")
    assert collection_id not in {c["id"] for c in after}


# ---------------------------------------------------------------------------
# Read-only tools — shape assertions
# ---------------------------------------------------------------------------


def test_get_template_variables_returns_a_mapping(mcp, services):
    """Shape only.

    The payload is ``{plugin_id: {variable: {...}}}`` and is legitimately
    empty here — the fixture enables no plugins. Asserting non-emptiness
    would be asserting on the fixture, not on the tool.
    """
    result = assert_ok(call(mcp, "get_template_variables"), "get_template_variables")
    assert isinstance(result, dict)


def test_get_system_status_returns_a_payload(mcp, services):
    result = assert_ok(call(mcp, "get_system_status"), "get_system_status")
    assert isinstance(result, dict) and result


def test_get_settings_summary_returns_a_payload(mcp, services):
    result = assert_ok(call(mcp, "get_settings_summary"), "get_settings_summary")
    assert isinstance(result, dict) and result


def test_list_installed_plugins_returns_a_list(mcp, services):
    result = call(mcp, "list_installed_plugins")
    assert isinstance(result, (list, dict))


# -- update_setting ----------------------------------------------------------
#
# The chat's ``update_setting`` op becomes an MCP tool so the in-app chat can
# change settings through the same server external clients use. The read-back
# is ``get_settings_summary``, which is what a model would call to confirm.


def test_update_setting_display_change_is_read_back_by_get_settings_summary(mcp, services, two_boards):
    before = assert_ok(call(mcp, "get_settings_summary"), "get_settings_summary")
    assert before["display"]["reduce_motion"] is False

    result = assert_ok(
        call(mcp, "update_setting", category="display", values={"reduce_motion": True}),
        "update_setting",
    )
    assert result["category"] == "display"

    after = assert_ok(call(mcp, "get_settings_summary"), "get_settings_summary")
    assert after["display"]["reduce_motion"] is True


def test_update_setting_location_change_survives_a_fresh_settings_service(mcp, services, two_boards, tmp_path):
    """Persisted, not just cached: a new service over the same file sees it."""
    import src.settings.service as settings_module

    assert_ok(
        call(mcp, "update_setting", category="location", values={"latitude": 40.7128, "longitude": -74.006}),
        "update_setting",
    )

    reloaded = settings_module.SettingsService(settings_file=str(tmp_path / "settings.json"))
    loc = reloaded.get_location_settings()
    assert (loc.latitude, loc.longitude) == (40.7128, -74.006)


def test_update_setting_active_page_is_the_same_selection_set_active_page_makes(mcp, services, two_boards):
    page = assert_ok(
        call(mcp, "create_page", name="Via setting", template_lines=FLAGSHIP_TEMPLATE, device_type="flagship"),
        "create_page",
    )

    assert_ok(
        call(mcp, "update_setting", category="active_page", values={"page_id": page["page_id"]}), "update_setting"
    )

    assert two_boards.get_active_page_id() == page["page_id"]


def test_update_setting_rejects_an_unknown_category(mcp, services, two_boards):
    # ``mqtt`` used to be the example here; it is a real category now (see
    # tests/test_mcp_state_effects_settings.py), so the unknown one is wifi.
    message = call_expect_error(mcp, "update_setting", category="wifi", values={"ssid": "HomeNet"})
    assert "wifi" in message


# -- read-only honesty --------------------------------------------------------
#
# ``readOnlyHint`` is a promise to clients (and to the in-app chat, which
# runs these tools without asking). This checks the promise against the
# stores: calling every read-only tool leaves every persisted file
# byte-identical. Open-world read tools are exercised too — the fixture
# plugin is local — but the network-backed registry listing is not.


def _persisted_files(root) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }


def test_read_only_tools_leave_every_store_untouched(mcp, services, plugins, engine, tmp_path):
    from tests.test_mcp_annotations import READ_ONLY

    page = assert_ok(
        call(mcp, "create_page", name="Fixture", template_lines=FLAGSHIP_TEMPLATE, device_type="flagship"),
        "create_page",
    )
    args_for: dict[str, dict[str, Any]] = {
        "get_page": {"page_id": page["page_id"]},
        "preview_saved_page": {"page_id": page["page_id"]},
        "render_page_preview": {"template_lines": FLAGSHIP_TEMPLATE, "device_type": "flagship"},
        "validate_template": {"template": "\n".join(FLAGSHIP_TEMPLATE), "device_type": "flagship"},
        "get_plugin_data": {"plugin_id": PLUGIN_ID},
        "export_page": {"page_id": page["page_id"]},
        "list_plugin_instances": {"plugin_id": PLUGIN_ID},
        "get_plugin_demo_page": {"plugin_id": PLUGIN_ID},
        "get_plugin_manifest": {"plugin_id": PLUGIN_ID},
        "list_plugin_options": {"plugin_id": PLUGIN_ID, "options_id": "stations"},
    }
    skipped = {
        "list_registry_plugins",  # network-backed registry
        # Answered by board hardware / the release registries / a third-party
        # AI endpoint / the public internet. Their honesty is checked with
        # patched boundaries in tests/test_mcp_state_effects_settings.py.
        "detect_board_size",
        "check_for_update",
        "test_ai_provider",
        "run_network_diagnostics",
    }
    # get_plugin_data reads a plugin's live values, which needs it enabled
    # and configured — writes that belong BEFORE the snapshot. Likewise
    # get_current_display needs an active page and list_transition_plugins
    # needs the beta gate open.
    assert_ok(call(mcp, "configure_plugin", plugin_id=PLUGIN_ID, config={"station_id": "9414290"}), "configure_plugin")
    assert_ok(call(mcp, "enable_plugin", plugin_id=PLUGIN_ID), "enable_plugin")
    from src.settings.service import get_settings_service

    get_settings_service().set_active_page_id(page["page_id"])
    get_settings_service().update_beta_settings({"transition_plugins_enabled": True})

    before = _persisted_files(tmp_path)
    for name in sorted(READ_ONLY - skipped):
        assert_ok(call(mcp, name, **args_for.get(name, {})), name)
    after = _persisted_files(tmp_path)

    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    assert not changed, f"read-only tools changed persisted state: {changed}"


# ---------------------------------------------------------------------------
# Plugins — #1588
#
# Every one of these tools mutated only the in-memory registry and never
# ConfigManager, so the settings evaporated the next time the container was
# recreated. The assertions below read `config.json` off disk rather than
# asking the registry, because the registry is exactly what lied.
# ---------------------------------------------------------------------------


def test_configure_plugin_writes_the_settings_to_config_json(mcp, plugins):
    assert_ok(
        call(mcp, "configure_plugin", plugin_id=PLUGIN_ID, config={"station_id": "9447427"}),
        "configure_plugin",
    )

    stored = stored_plugin_config(plugins["config_path"], PLUGIN_ID)
    assert stored is not None, "configure_plugin reported success but wrote nothing to config.json"
    assert stored["station_id"] == "9447427"


def test_configure_plugin_returns_the_config_it_saved(mcp, plugins):
    """An empty ``config`` echo was the only hint the write never happened."""
    result = assert_ok(
        call(mcp, "configure_plugin", plugin_id=PLUGIN_ID, config={"station_id": "9447427"}),
        "configure_plugin",
    )
    assert result["config"].get("station_id") == "9447427"


def test_configure_plugin_never_persists_env_overlay_values(mcp, plugins, monkeypatch):
    """The merge base must be the STORED config, not the env-overlaid read.

    configure_plugin merges the caller's keys over the existing config and
    persists the result. Merging over the overlaid read bakes every live
    env override — the api_key itself included, unmasked — into config.json
    on any unrelated MCP save (#1874/#1865 review, regression of the #1864
    env-free-persistence contract).
    """
    from src.config_manager import ENV_PLUGIN_OVERRIDES

    assert_ok(
        call(mcp, "configure_plugin", plugin_id=PLUGIN_ID, config={"station_id": "9447427"}),
        "configure_plugin",
    )
    monkeypatch.setitem(ENV_PLUGIN_OVERRIDES, "HARNESS_TIDE_API_KEY", (PLUGIN_ID, "api_key", str))
    monkeypatch.setenv("HARNESS_TIDE_API_KEY", "test_env_secret_zz99")

    assert_ok(
        call(mcp, "configure_plugin", plugin_id=PLUGIN_ID, config={"station_id": "9447430"}),
        "configure_plugin",
    )

    stored = stored_plugin_config(plugins["config_path"], PLUGIN_ID)
    assert stored["station_id"] == "9447430"
    assert stored.get("api_key", "") == "", "MCP configure persisted an env secret into config.json"


def test_configure_plugin_masks_sensitive_values_in_its_response(mcp, plugins):
    result = assert_ok(
        call(
            mcp,
            "configure_plugin",
            plugin_id=PLUGIN_ID,
            config={"station_id": "9447427", "api_key": "test_secret"},
        ),
        "configure_plugin",
    )
    assert result["config"]["api_key"] == "***", "an API key was echoed back in the clear"
    assert stored_plugin_config(plugins["config_path"], PLUGIN_ID)["api_key"] == "test_secret"


def test_configure_plugin_merges_with_the_existing_stored_config(mcp, plugins):
    assert_ok(
        call(mcp, "configure_plugin", plugin_id=PLUGIN_ID, config={"station_id": "9447427"}),
        "configure_plugin",
    )
    assert_ok(
        call(mcp, "configure_plugin", plugin_id=PLUGIN_ID, config={"api_key": "test_secret"}),
        "configure_plugin (partial)",
    )

    stored = stored_plugin_config(plugins["config_path"], PLUGIN_ID)
    assert stored["station_id"] == "9447427", "a partial update dropped a previously-set field"
    assert stored["api_key"] == "test_secret"


def test_configure_plugin_reports_validation_errors_instead_of_success(mcp, plugins):
    """``registry.set_plugin_config()`` returns errors; the tool discarded them."""
    message = call_expect_error(mcp, "configure_plugin", plugin_id=PLUGIN_ID, config={"station_id": ""})

    assert "station_id" in message, f"the plugin's own validation message was not surfaced: {message}"


def test_configure_plugin_does_not_overwrite_a_good_config_with_a_rejected_one(mcp, plugins):
    assert_ok(
        call(mcp, "configure_plugin", plugin_id=PLUGIN_ID, config={"station_id": "9447427"}),
        "configure_plugin",
    )

    call_expect_error(mcp, "configure_plugin", plugin_id=PLUGIN_ID, config={"station_id": ""})

    stored = stored_plugin_config(plugins["config_path"], PLUGIN_ID)
    assert stored["station_id"] == "9447427", "a rejected config was persisted over a valid one"


def test_configure_plugin_reports_an_error_for_an_unknown_plugin(mcp, plugins):
    call_expect_error(mcp, "configure_plugin", plugin_id="not_a_plugin", config={"station_id": "1"})
    assert stored_plugin_config(plugins["config_path"], "not_a_plugin") is None


def test_enable_plugin_persists_enabled_true(mcp, plugins):
    assert_ok(call(mcp, "enable_plugin", plugin_id=PLUGIN_ID), "enable_plugin")

    stored = stored_plugin_config(plugins["config_path"], PLUGIN_ID)
    assert stored is not None, "enable_plugin reported success but wrote nothing to config.json"
    assert stored["enabled"] is True


def test_disable_plugin_persists_enabled_false(mcp, plugins):
    assert_ok(call(mcp, "enable_plugin", plugin_id=PLUGIN_ID), "enable_plugin")

    assert_ok(call(mcp, "disable_plugin", plugin_id=PLUGIN_ID), "disable_plugin")

    stored = stored_plugin_config(plugins["config_path"], PLUGIN_ID)
    assert stored["enabled"] is False, "disable_plugin reported success but config.json still says enabled"


def test_enable_plugin_reports_an_error_for_an_unknown_plugin(mcp, plugins):
    """``registry.enable_plugin()`` returns False here; the tool ignored it."""
    call_expect_error(mcp, "enable_plugin", plugin_id="not_a_plugin")


def test_disable_plugin_reports_an_error_for_an_unknown_plugin(mcp, plugins):
    call_expect_error(mcp, "disable_plugin", plugin_id="not_a_plugin")


def test_enable_plugin_does_not_disturb_the_stored_settings(mcp, plugins):
    assert_ok(
        call(mcp, "configure_plugin", plugin_id=PLUGIN_ID, config={"station_id": "9447427"}),
        "configure_plugin",
    )

    assert_ok(call(mcp, "enable_plugin", plugin_id=PLUGIN_ID), "enable_plugin")

    stored = stored_plugin_config(plugins["config_path"], PLUGIN_ID)
    assert stored["station_id"] == "9447427", "enabling the plugin wiped its settings"
    assert stored["enabled"] is True


def test_install_plugin_with_auto_enable_persists_enabled(mcp, plugins):
    assert_ok(call(mcp, "install_plugin", plugin_id=UNINSTALLED_PLUGIN_ID), "install_plugin")

    stored = stored_plugin_config(plugins["config_path"], UNINSTALLED_PLUGIN_ID)
    assert stored is not None, "install_plugin(auto_enable=True) never recorded the plugin in config.json"
    assert stored["enabled"] is True


def test_install_plugin_without_auto_enable_does_not_enable_it(mcp, plugins):
    assert_ok(
        call(mcp, "install_plugin", plugin_id=UNINSTALLED_PLUGIN_ID, auto_enable=False),
        "install_plugin",
    )

    stored = stored_plugin_config(plugins["config_path"], UNINSTALLED_PLUGIN_ID)
    assert not (stored or {}).get("enabled"), "auto_enable=False still enabled the plugin"


def test_uninstall_plugin_purges_the_persisted_config(mcp, plugins):
    """A leftover entry is what resurrects a deliberately removed plugin (#937)."""
    assert_ok(
        call(mcp, "configure_plugin", plugin_id=PLUGIN_ID, config={"station_id": "9447427"}),
        "configure_plugin",
    )

    assert_ok(call(mcp, "uninstall_plugin", plugin_id=PLUGIN_ID), "uninstall_plugin")

    assert stored_plugin_config(plugins["config_path"], PLUGIN_ID) is None, (
        "uninstall left the plugin's config behind, so a later boot can reinstall it"
    )


def test_get_plugin_data_returns_the_live_values(mcp, plugins):
    assert_ok(
        call(mcp, "configure_plugin", plugin_id=PLUGIN_ID, config={"station_id": "9447427"}),
        "configure_plugin",
    )
    assert_ok(call(mcp, "enable_plugin", plugin_id=PLUGIN_ID), "enable_plugin")

    result = assert_ok(call(mcp, "get_plugin_data", plugin_id=PLUGIN_ID), "get_plugin_data")
    assert result["data"]["next_high"] == "06:12"


def test_plugin_configured_over_mcp_survives_a_container_recreate(mcp, plugins):
    """The reported bug, end to end.

    Configure and enable over MCP, throw the process away, and bring a fresh
    registry up from the same ``config.json``. Before the fix the plugin came
    back disabled and unconfigured, and every template variable rendered
    ``#REF``.
    """
    assert_ok(
        call(mcp, "configure_plugin", plugin_id=PLUGIN_ID, config={"station_id": "9447427"}),
        "configure_plugin",
    )
    assert_ok(call(mcp, "enable_plugin", plugin_id=PLUGIN_ID), "enable_plugin")

    restarted = plugins["restart"]()

    assert restarted.is_enabled(PLUGIN_ID), "the plugin came back disabled after a restart"
    assert restarted.get_plugin_config(PLUGIN_ID).get("station_id") == "9447427", (
        "the plugin came back unconfigured after a restart"
    )
    assert PLUGIN_ID in restarted.get_all_variables(), "the plugin's template variables did not come back"


# ---------------------------------------------------------------------------
# Deleting something that is not there — #1742
#
# Both services return a boolean; both tools threw it away and reported
# success. REST 404s in the same case, and ``delete_page`` was already fixed
# for exactly this. The assertions below are on the tool's own envelope,
# because there is no state to re-read — that is the whole point.
# ---------------------------------------------------------------------------


def test_delete_schedule_reports_an_error_for_an_unknown_id(mcp, services):
    message = call_expect_error(mcp, "delete_schedule", schedule_id="no-such-schedule")
    assert "not found" in message, f"deleting a schedule that does not exist reported success: {message}"


def test_delete_collection_reports_an_error_for_an_unknown_id(mcp, services):
    message = call_expect_error(mcp, "delete_collection", collection_id="no-such-collection")
    assert "not found" in message, f"deleting a collection that does not exist reported success: {message}"


# ---------------------------------------------------------------------------
# Template variables — #1739
#
# ``get_template_variables`` documents ``{plugin: {var: {description, ...}}}``
# but called ``get_all_variables()``, which returns ``{plugin: [name, ...]}``.
# The existing shape test above passes vacuously: its fixture enables no
# plugin, so the payload is ``{}`` and every nested assertion is skipped.
# These enable one.
# ---------------------------------------------------------------------------


def call_resource(mcp: Any, uri: str) -> Any:
    """Read a registered MCP resource by URI, awaiting it if it is async."""
    resource = mcp._resource_manager._resources.get(uri)
    if resource is None:
        raise KeyError(f"resource {uri!r} is not registered; have: {sorted(mcp._resource_manager._resources)}")
    result = resource.fn()
    if asyncio.iscoroutine(result):
        result = asyncio.run(result)
    return result


def _enable_harness_plugin(mcp: Any) -> None:
    assert_ok(
        call(mcp, "configure_plugin", plugin_id=PLUGIN_ID, config={"station_id": "9447427"}),
        "configure_plugin",
    )
    assert_ok(call(mcp, "enable_plugin", plugin_id=PLUGIN_ID), "enable_plugin")


def test_get_template_variables_describes_each_variable_with_metadata(mcp, plugins):
    _enable_harness_plugin(mcp)

    result = assert_ok(call(mcp, "get_template_variables"), "get_template_variables")

    assert PLUGIN_ID in result, f"an enabled plugin's variables are missing entirely: {result}"
    variables = result[PLUGIN_ID]
    assert isinstance(variables, dict), (
        f"the documented shape is {{variable: {{description, ...}}}}, got {type(variables).__name__}: {variables}"
    )
    assert variables["next_high"]["description"] == "Time of the next high tide"


def test_variables_resource_renders_for_an_enabled_plugin(mcp, plugins):
    """The resource calls ``.items()`` on each plugin's entry.

    Against a list that is an AttributeError, which the resource caught and
    returned as its whole body — so every install with at least one enabled
    plugin got an error string instead of its variables.
    """
    _enable_harness_plugin(mcp)

    content = call_resource(mcp, "fiestaboard://variables")

    assert not content.lstrip().startswith("Error:"), f"the variables resource failed to render: {content}"
    assert f"{{{{{PLUGIN_ID}.next_high}}}}" in content, (
        f"an enabled plugin's variable is not listed in the resource: {content}"
    )


# ---------------------------------------------------------------------------
# update_plugin — #1741
#
# The tool called ``registry.reload_plugin()`` and nothing else: no git
# fetch, so it re-imported the code already on disk and reported "updated
# successfully" without any new code existing. It also skipped every guard
# ``POST /plugins/{id}/update`` applies — built-in rejection, realpath
# containment of ``local_path`` inside the external plugins directory, and
# the ``.git`` check — so it would happily "update" a built-in plugin or a
# directory that is not a checkout at all.
#
# The fixture below is a real local git remote, so the version change is
# observed rather than mocked.
# ---------------------------------------------------------------------------

#: External plugin cloned from a real git remote, so it can actually update.
GIT_PLUGIN_ID = "harness_git"

#: Built-in plugin — must be rejected by update_plugin, never reloaded.
BUILTIN_PLUGIN_ID = "harness_builtin"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=FiestaBoard Tests", "-c", "user.email=tests@example.com", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def updatable_plugins(plugins, tmp_path, monkeypatch):
    """A git-backed external plugin, a built-in plugin, and a plain directory.

    ``publish(version)`` commits a new manifest version to the remote. Nothing
    in the update path is stubbed: the tool has to run a real ``git fetch``
    against a real remote for the version to change.
    """
    external_dir = tmp_path / "external_plugins"
    builtin_dir = tmp_path / "builtin_plugins"

    remote = tmp_path / "remote" / GIT_PLUGIN_ID
    _write_plugin(remote, GIT_PLUGIN_ID, version="1.0.0")
    _git(remote, "init", "--quiet", "--initial-branch=main")
    _git(remote, "add", "-A")
    _git(remote, "commit", "--quiet", "-m", "v1.0.0")

    _git(tmp_path, "clone", "--quiet", f"file://{remote}", str(external_dir / GIT_PLUGIN_ID))

    _write_plugin(builtin_dir / BUILTIN_PLUGIN_ID, BUILTIN_PLUGIN_ID)

    monkeypatch.setattr("src.plugins.sources.get_external_plugins_dir", lambda *a, **k: external_dir)

    registry = plugins["restart"]()
    assert registry.get_manifest(GIT_PLUGIN_ID) is not None, "fixture failed to load the git-backed plugin"
    assert registry.get_manifest(BUILTIN_PLUGIN_ID) is not None, "fixture failed to load the built-in plugin"

    def publish(version: str) -> None:
        _write_plugin(remote, GIT_PLUGIN_ID, version=version)
        _git(remote, "add", "-A")
        _git(remote, "commit", "--quiet", "-m", f"v{version}")

    yield {"registry": registry, "publish": publish, "external_dir": external_dir}


def test_update_plugin_fetches_the_new_version_from_the_remote(mcp, updatable_plugins):
    """The state effect: the manifest on disk and in the registry both move."""
    registry = updatable_plugins["registry"]
    assert registry.get_manifest(GIT_PLUGIN_ID).version == "1.0.0"

    updatable_plugins["publish"]("2.0.0")

    assert_ok(call(mcp, "update_plugin", plugin_id=GIT_PLUGIN_ID), "update_plugin")

    on_disk = json.loads(
        (updatable_plugins["external_dir"] / GIT_PLUGIN_ID / "manifest.json").read_text(encoding="utf-8")
    )
    assert on_disk["version"] == "2.0.0", "update_plugin reported success but never fetched the new code"
    assert registry.get_manifest(GIT_PLUGIN_ID).version == "2.0.0", (
        "the new version was fetched but the registry still serves the old manifest"
    )


def test_update_plugin_refuses_a_builtin_plugin(mcp, updatable_plugins):
    """``POST /plugins/{id}/update`` 400s here; the MCP tool reloaded it."""
    message = call_expect_error(mcp, "update_plugin", plugin_id=BUILTIN_PLUGIN_ID)

    assert "built-in" in message.lower(), f"the rejection did not say why a built-in cannot be updated: {message}"


def test_update_plugin_refuses_a_plugin_that_is_not_a_git_checkout(mcp, updatable_plugins):
    """``harness_tide`` was copied into place, not cloned — there is no remote.

    Without the REST path's ``.git`` check the tool reports success for a
    directory it has no way to update.
    """
    message = call_expect_error(mcp, "update_plugin", plugin_id=PLUGIN_ID)

    assert "git" in message.lower(), f"the rejection did not name the missing git checkout: {message}"


def test_update_plugin_reports_an_error_for_an_unknown_plugin(mcp, updatable_plugins):
    call_expect_error(mcp, "update_plugin", plugin_id="not_a_plugin")


# ---------------------------------------------------------------------------
# Update checks — the Integrations page's "Check for updates" / "Update all"
#
# Real git remote (the ``updatable_plugins`` fixture): the check runs a real
# ``git ls-remote`` and the bulk apply a real fetch, so the version on disk
# has to move. The one seam replaced is ``get_remote_head_sha``'s https-only
# guard on the origin URL — the fixture's origin is ``file://`` — and the
# replacement still asks git for the remote SHA rather than inventing one.
# ---------------------------------------------------------------------------


@pytest.fixture
def file_origin_updates(updatable_plugins, monkeypatch):
    def remote_head_sha(dest_dir: Path) -> str | None:
        url = subprocess.run(
            ["git", "-C", str(dest_dir), "remote", "get-url", "origin"], capture_output=True, text=True, check=True
        ).stdout.strip()
        listed = subprocess.run(["git", "ls-remote", url, "HEAD"], capture_output=True, text=True, check=True)
        return listed.stdout.split()[0] if listed.stdout.strip() else None

    monkeypatch.setattr("src.plugins.sources.get_remote_head_sha", remote_head_sha)
    return updatable_plugins


def test_check_plugin_updates_reports_a_newly_published_version(mcp, file_origin_updates):
    """The state effect: the registry's cached update status is refreshed."""
    updatable_plugins = file_origin_updates
    registry = updatable_plugins["registry"]
    # The check skips plugins that are not in use (no git traffic for idle code).
    assert_ok(call(mcp, "enable_plugin", plugin_id=GIT_PLUGIN_ID), "enable_plugin")
    assert registry.get_update_status() == {}

    updatable_plugins["publish"]("2.0.0")

    result = assert_ok(call(mcp, "check_plugin_updates"), "check_plugin_updates")

    assert GIT_PLUGIN_ID in result["updates_available"]
    assert result["checked"] >= 1
    assert registry.get_update_status().get(GIT_PLUGIN_ID) is True, (
        "check_plugin_updates reported an update but did not refresh the registry cache"
    )


def test_list_pending_plugin_updates_reads_the_cached_check(mcp, file_origin_updates):
    updatable_plugins = file_origin_updates
    assert_ok(call(mcp, "enable_plugin", plugin_id=GIT_PLUGIN_ID), "enable_plugin")
    updatable_plugins["publish"]("2.0.0")
    assert_ok(call(mcp, "check_plugin_updates"), "check_plugin_updates")

    pending = call(mcp, "list_pending_plugin_updates")

    assert pending["updates"].get(GIT_PLUGIN_ID) is True
    assert isinstance(pending["blocked"], dict)


def test_update_all_plugins_fetches_every_pending_update(mcp, file_origin_updates):
    """The state effect: the manifest on disk moves for the pending plugin."""
    updatable_plugins = file_origin_updates
    registry = updatable_plugins["registry"]
    assert_ok(call(mcp, "enable_plugin", plugin_id=GIT_PLUGIN_ID), "enable_plugin")
    updatable_plugins["publish"]("2.0.0")
    assert_ok(call(mcp, "check_plugin_updates"), "check_plugin_updates")

    result = assert_ok(call(mcp, "update_all_plugins"), "update_all_plugins")

    assert result["updated"] == [GIT_PLUGIN_ID]
    assert result["failed"] == {}
    on_disk = json.loads(
        (updatable_plugins["external_dir"] / GIT_PLUGIN_ID / "manifest.json").read_text(encoding="utf-8")
    )
    assert on_disk["version"] == "2.0.0", "update_all_plugins reported success but never fetched the new code"
    assert registry.get_manifest(GIT_PLUGIN_ID).version == "2.0.0"
    assert registry.get_update_status().get(GIT_PLUGIN_ID) is None, "the applied update is still advertised"


def test_update_all_plugins_with_nothing_pending_is_a_clean_no_op(mcp, updatable_plugins):
    result = assert_ok(call(mcp, "update_all_plugins"), "update_all_plugins")
    assert result["updated"] == []
    assert result["failed"] == {}


# ---------------------------------------------------------------------------
# install_plugin from a git URL — the Integrations page's "Add from Git"
#
# ``_validate_git_url`` only accepts https, so a ``file://`` remote cannot
# stand in. The clone (``install_git_plugin``) is the one seam replaced: the
# fake copies the staged package into the external dir, and everything after
# — the loader import, registry bookkeeping, enable, config.json — is real.
# ---------------------------------------------------------------------------

GIT_REPOSITORY = "https://github.com/example/fiestaboard-plugin--harness-surf.git"


@pytest.fixture
def git_clone(plugins, tmp_path, monkeypatch):
    """Replace the network clone with a locally written package; record calls."""
    external_dir = tmp_path / "external_plugins"
    calls: list[dict[str, Any]] = []

    def fake_install_git_plugin(repo_url, plugin_id=None, branch="", external_dir=None):
        calls.append({"repo_url": repo_url, "plugin_id": plugin_id, "branch": branch})
        from src.plugins.sources import plugin_id_from_repo_name, repo_name_from_url

        pid = plugin_id or plugin_id_from_repo_name(repo_name_from_url(repo_url))
        # A clone whose manifest id matches the directory it lands in.
        _write_plugin(tmp_path / "external_plugins" / pid, pid)
        return True, ""

    monkeypatch.setattr("src.plugins.registry.install_git_plugin", fake_install_git_plugin)
    monkeypatch.setattr("src.plugins.registry.get_external_plugins_dir", lambda *a, **k: external_dir)
    monkeypatch.setattr("src.plugins.sources.get_external_plugins_dir", lambda *a, **k: external_dir)
    return calls


def test_install_plugin_from_git_loads_and_enables_the_cloned_plugin(mcp, plugins, git_clone):
    registry = plugins["registry"]
    assert registry.get_plugin(UNINSTALLED_PLUGIN_ID) is None

    result = assert_ok(
        call(mcp, "install_plugin", repository=GIT_REPOSITORY, branch="main"),
        "install_plugin",
    )

    assert result["plugin_id"] == UNINSTALLED_PLUGIN_ID
    assert result["source"] == "git"
    assert git_clone == [{"repo_url": GIT_REPOSITORY, "plugin_id": None, "branch": "main"}], (
        "the clone was not asked for the repository and branch the user gave"
    )
    assert registry.get_plugin(UNINSTALLED_PLUGIN_ID) is not None, "the cloned plugin never reached the registry"
    stored = stored_plugin_config(plugins["config_path"], UNINSTALLED_PLUGIN_ID)
    assert stored and stored.get("enabled") is True, "installed from git but not persisted as enabled"


def test_install_plugin_from_git_honours_the_plugin_id_override(mcp, plugins, git_clone):
    result = assert_ok(
        call(mcp, "install_plugin", repository=GIT_REPOSITORY, plugin_id="harness_custom", auto_enable=False),
        "install_plugin",
    )

    assert result["plugin_id"] == "harness_custom"
    assert git_clone[0]["plugin_id"] == "harness_custom"
    assert plugins["registry"].get_plugin("harness_custom") is not None
    assert not plugins["registry"].is_enabled("harness_custom")


def test_install_plugin_from_git_applies_initial_config(mcp, plugins, git_clone):
    assert_ok(
        call(mcp, "install_plugin", repository=GIT_REPOSITORY, initial_config={"station_id": "9414290"}),
        "install_plugin",
    )
    stored = stored_plugin_config(plugins["config_path"], UNINSTALLED_PLUGIN_ID)
    assert stored["station_id"] == "9414290"


def test_install_plugin_from_git_rejects_an_invalid_branch_before_cloning(mcp, plugins, git_clone):
    message = call_expect_error(mcp, "install_plugin", repository=GIT_REPOSITORY, branch="not a ref")
    assert "branch" in message.lower()
    assert git_clone == [], "an invalid ref must be refused before any clone is attempted"


def test_install_plugin_without_a_target_is_an_error(mcp, plugins, git_clone):
    message = call_expect_error(mcp, "install_plugin")
    assert "plugin_id" in message and "repository" in message
    assert git_clone == []


def test_install_plugin_registry_path_is_unchanged_when_only_plugin_id_is_given(mcp, plugins, git_clone):
    assert_ok(call(mcp, "install_plugin", plugin_id=UNINSTALLED_PLUGIN_ID), "install_plugin")
    assert git_clone == [], "a registry install must not go through the git clone path"
    assert plugins["registry"].get_plugin(UNINSTALLED_PLUGIN_ID) is not None


# ---------------------------------------------------------------------------
# Plugin instances — the Integrations page's "Add instance" / remove
# ---------------------------------------------------------------------------


def test_create_plugin_instance_registers_it_and_persists_its_config(mcp, plugins):
    registry = plugins["registry"]
    assert registry.list_instances(PLUGIN_ID) == []

    result = assert_ok(call(mcp, "create_plugin_instance", plugin_id=PLUGIN_ID, label="SF"), "create_plugin_instance")

    assert result["instance_key"] == f"{PLUGIN_ID}:sf", "the label must be normalised the way the registry stores it"
    assert result["instance_label"] == "sf"
    assert [i["key"] for i in registry.list_instances(PLUGIN_ID)] == [f"{PLUGIN_ID}:sf"]
    assert stored_plugin_config(plugins["config_path"], f"{PLUGIN_ID}:sf") is not None, (
        "the instance exists in memory but nothing was written to config.json"
    )


def test_list_plugin_instances_reads_back_what_was_created(mcp, plugins):
    assert call(mcp, "list_plugin_instances", plugin_id=PLUGIN_ID) == {
        "plugin_id": PLUGIN_ID,
        "instances": [],
        "total": 0,
    }
    assert_ok(call(mcp, "create_plugin_instance", plugin_id=PLUGIN_ID, label="sf"), "create_plugin_instance")

    listed = call(mcp, "list_plugin_instances", plugin_id=PLUGIN_ID)

    assert listed["total"] == 1
    assert listed["instances"][0]["key"] == f"{PLUGIN_ID}:sf"
    assert listed["instances"][0]["enabled"] is False


def test_list_plugin_instances_accepts_an_instance_key(mcp, plugins):
    assert_ok(call(mcp, "create_plugin_instance", plugin_id=PLUGIN_ID, label="sf"), "create_plugin_instance")
    listed = call(mcp, "list_plugin_instances", plugin_id=f"{PLUGIN_ID}:sf")
    assert listed["plugin_id"] == PLUGIN_ID
    assert listed["total"] == 1


def test_create_plugin_instance_twice_is_reported_not_duplicated(mcp, plugins):
    assert_ok(call(mcp, "create_plugin_instance", plugin_id=PLUGIN_ID, label="sf"), "create_plugin_instance")
    message = call_expect_error(mcp, "create_plugin_instance", plugin_id=PLUGIN_ID, label="sf")
    assert "already exists" in message
    assert len(plugins["registry"].list_instances(PLUGIN_ID)) == 1


def test_create_plugin_instance_reports_an_error_for_an_unknown_plugin(mcp, plugins):
    call_expect_error(mcp, "create_plugin_instance", plugin_id="not_a_plugin", label="sf")


def test_instance_can_be_configured_and_enabled_through_the_plugin_tools(mcp, plugins):
    """The compound key is what configure_plugin / enable_plugin take."""
    assert_ok(call(mcp, "create_plugin_instance", plugin_id=PLUGIN_ID, label="sf"), "create_plugin_instance")
    key = f"{PLUGIN_ID}:sf"

    assert_ok(call(mcp, "configure_plugin", plugin_id=key, config={"station_id": "9414290"}), "configure_plugin")
    assert_ok(call(mcp, "enable_plugin", plugin_id=key), "enable_plugin")

    stored = stored_plugin_config(plugins["config_path"], key)
    assert stored["station_id"] == "9414290"
    assert stored["enabled"] is True
    assert plugins["registry"].is_enabled(key)


def test_delete_plugin_instance_removes_it_and_purges_its_config(mcp, plugins):
    registry = plugins["registry"]
    assert_ok(call(mcp, "create_plugin_instance", plugin_id=PLUGIN_ID, label="sf"), "create_plugin_instance")
    assert stored_plugin_config(plugins["config_path"], f"{PLUGIN_ID}:sf") is not None

    assert_ok(call(mcp, "delete_plugin_instance", plugin_id=PLUGIN_ID, label="sf"), "delete_plugin_instance")

    assert registry.list_instances(PLUGIN_ID) == []
    assert stored_plugin_config(plugins["config_path"], f"{PLUGIN_ID}:sf") is None, (
        "the instance was dropped from the registry but its config.json entry survived"
    )
    assert registry.get_plugin(PLUGIN_ID) is not None, "deleting an instance must never touch the base plugin"


def test_delete_plugin_instance_reports_an_error_for_an_unknown_instance(mcp, plugins):
    message = call_expect_error(mcp, "delete_plugin_instance", plugin_id=PLUGIN_ID, label="nope")
    assert "not found" in message.lower()


# ---------------------------------------------------------------------------
# Demo pages — the Integrations page's "Create Demo Page"
# ---------------------------------------------------------------------------


def _configure_harness(mcp: Any) -> None:
    assert_ok(call(mcp, "configure_plugin", plugin_id=PLUGIN_ID, config={"station_id": "9414290"}), "configure_plugin")


def test_get_plugin_demo_page_reports_no_page_before_one_is_created(mcp, plugins):
    assert call(mcp, "get_plugin_demo_page", plugin_id=PLUGIN_ID) == {
        "plugin_id": PLUGIN_ID,
        "device_type": "flagship",
        "has_demo_template": True,
        "exists": False,
        "page_id": None,
    }


def test_create_plugin_demo_page_persists_a_page_visible_to_list_pages(mcp, plugins, services):
    _configure_harness(mcp)

    result = assert_ok(call(mcp, "create_plugin_demo_page", plugin_id=PLUGIN_ID), "create_plugin_demo_page")

    assert result["created"] is True
    assert result["recreated"] is False
    assert result["device_type"] == "flagship"
    page_ids = {p["id"] for p in call(mcp, "list_pages")}
    assert result["page_id"] in page_ids, "create_plugin_demo_page reported a page that list_pages cannot see"
    stored = services["pages"].get_page(result["page_id"])
    assert stored.demo_plugin_id == PLUGIN_ID
    assert stored.template[0] == f"TIDE {{{{{PLUGIN_ID}.next_high}}}}"

    status = call(mcp, "get_plugin_demo_page", plugin_id=PLUGIN_ID)
    assert status["exists"] is True
    assert status["page_id"] == result["page_id"]


def test_create_plugin_demo_page_honours_device_type(mcp, plugins, services):
    _configure_harness(mcp)
    result = assert_ok(
        call(mcp, "create_plugin_demo_page", plugin_id=PLUGIN_ID, device_type="note"), "create_plugin_demo_page"
    )
    assert result["device_type"] == "note"
    assert services["pages"].get_page(result["page_id"]).device_type == "note"
    assert call(mcp, "get_plugin_demo_page", plugin_id=PLUGIN_ID, device_type="note")["exists"] is True
    assert call(mcp, "get_plugin_demo_page", plugin_id=PLUGIN_ID, device_type="flagship")["exists"] is False


def test_create_plugin_demo_page_keeps_an_existing_page_unless_told_to_recreate(mcp, plugins, services):
    _configure_harness(mcp)
    first = assert_ok(call(mcp, "create_plugin_demo_page", plugin_id=PLUGIN_ID), "create_plugin_demo_page")
    services["pages"].update_page(first["page_id"], _page_update(name="Edited By Hand"))

    kept = assert_ok(call(mcp, "create_plugin_demo_page", plugin_id=PLUGIN_ID), "create_plugin_demo_page")

    assert kept["created"] is False
    assert kept["page_id"] == first["page_id"]
    assert services["pages"].get_page(first["page_id"]).name == "Edited By Hand", (
        "a second call without recreate=True must not replace the user's edited demo page"
    )

    rebuilt = assert_ok(
        call(mcp, "create_plugin_demo_page", plugin_id=PLUGIN_ID, recreate=True), "create_plugin_demo_page"
    )
    assert rebuilt["created"] is True
    assert rebuilt["recreated"] is True
    assert rebuilt["page_id"] != first["page_id"]
    assert services["pages"].get_page(first["page_id"]) is None
    assert len([p for p in services["pages"].list_pages() if p.demo_plugin_id == PLUGIN_ID]) == 1


def test_create_plugin_demo_page_refuses_until_required_settings_are_configured(mcp, plugins, services):
    message = call_expect_error(mcp, "create_plugin_demo_page", plugin_id=PLUGIN_ID)
    assert "station_id" in message
    assert services["pages"].list_pages() == []


def test_create_plugin_demo_page_reports_a_plugin_without_a_demo(mcp, plugins):
    _configure_harness(mcp)
    # harness_surf's manifest has a demo too, so strip it off the live manifest.
    manifest = plugins["registry"].get_manifest(PLUGIN_ID)
    manifest.demo = None
    message = call_expect_error(mcp, "create_plugin_demo_page", plugin_id=PLUGIN_ID)
    assert "demo" in message.lower()


def test_create_plugin_demo_page_reports_an_error_for_an_unknown_plugin(mcp, plugins):
    call_expect_error(mcp, "create_plugin_demo_page", plugin_id="not_a_plugin")


def _page_update(**fields: Any) -> Any:
    from src.pages.models import PageUpdate

    return PageUpdate(**fields)


# ---------------------------------------------------------------------------
# Discovery reads the configure flow needs
# ---------------------------------------------------------------------------


def test_list_plugin_options_browses_the_plugin_catalog(mcp, plugins):
    result = call(mcp, "list_plugin_options", plugin_id=PLUGIN_ID, options_id="stations")

    assert result["plugin_id"] == PLUGIN_ID
    assert result["options_id"] == "stations"
    assert [o["value"] for o in result["options"]] == ["9414290", "8518750"]
    assert result["options"][0]["label"] == "Golden Gate"
    assert result["has_more"] is False
    assert result["error"] is None


def test_list_plugin_options_passes_the_query_to_the_provider(mcp, plugins):
    result = call(mcp, "list_plugin_options", plugin_id=PLUGIN_ID, options_id="stations", query="battery")
    assert [o["value"] for o in result["options"]] == ["8518750"]


def test_list_plugin_options_rejects_an_undeclared_options_id(mcp, plugins):
    message = call_expect_error(mcp, "list_plugin_options", plugin_id=PLUGIN_ID, options_id="nope")
    assert "stations" in message, "the error must name the providers the plugin does declare"


def test_list_plugin_options_reports_an_error_for_an_unknown_plugin(mcp, plugins):
    call_expect_error(mcp, "list_plugin_options", plugin_id="not_a_plugin", options_id="stations")


def test_get_plugin_manifest_returns_the_raw_manifest(mcp, plugins):
    manifest = call(mcp, "get_plugin_manifest", plugin_id=PLUGIN_ID)
    assert manifest["id"] == PLUGIN_ID
    assert manifest["version"] == "1.0.0"
    assert "station_id" in manifest["settings_schema"]["properties"]
    assert "flagship" in manifest["demo"]


def test_get_plugin_manifest_reports_an_error_for_an_unknown_plugin(mcp, plugins):
    call_expect_error(mcp, "get_plugin_manifest", plugin_id="not_a_plugin")


def test_list_plugin_errors_returns_both_failure_modes(mcp, plugins):
    result = call(mcp, "list_plugin_errors")
    assert result == {"errors": {}, "fetch_breakers": {}}


def test_list_plugin_errors_surfaces_a_plugin_that_failed_to_load(mcp, plugins, tmp_path):
    broken = tmp_path / "external_plugins" / "harness_broken"
    _write_plugin(broken, "harness_broken")
    (broken / "__init__.py").write_text("raise RuntimeError('boom at import')\n", encoding="utf-8")
    plugins["restart"]()

    result = call(mcp, "list_plugin_errors")

    assert "harness_broken" in result["errors"], f"a plugin that failed to import is not reported: {result}"


# ---------------------------------------------------------------------------
# Multi-board — issue #1765
#
# On a multi-board install, set_active_page and set_schedule_mode silently
# targeted only the primary board while reporting success. These tests run a
# real SettingsService over two configured boards and read the per-board
# state back after each call.
# ---------------------------------------------------------------------------

NOTE_TEMPLATE = ["HI", "", ""]


@pytest.fixture
def two_boards(services, tmp_path, monkeypatch):
    """A real SettingsService over tmp storage with two configured boards."""
    import src.settings.service as settings_module

    svc = settings_module.SettingsService(settings_file=str(tmp_path / "settings.json"))
    svc.set_boards(
        [
            {"id": "board-main", "name": "Living Room", "device_type": "flagship"},
            {"id": "board-note", "name": "Kitchen", "device_type": "note"},
        ]
    )
    monkeypatch.setattr(settings_module, "_settings_service", svc)
    # No display engine in this harness: selection must persist even when the
    # immediate board send is skipped.
    monkeypatch.setattr("src.api_server.get_service", lambda: None)
    return svc


def test_set_active_page_with_board_id_changes_only_that_board(mcp, services, two_boards):
    main_page = assert_ok(
        call(mcp, "create_page", name="Main", template_lines=FLAGSHIP_TEMPLATE, device_type="flagship"),
        "create_page",
    )
    note_page = assert_ok(
        call(mcp, "create_page", name="Note", template_lines=NOTE_TEMPLATE, device_type="note"),
        "create_page",
    )

    assert_ok(call(mcp, "set_active_page", page_id=main_page["page_id"]), "set_active_page (primary)")
    assert_ok(
        call(mcp, "set_active_page", page_id=note_page["page_id"], board_id="board-note"),
        "set_active_page (board-note)",
    )

    assert two_boards.get_active_page_id(board_id="board-note") == note_page["page_id"]
    assert two_boards.get_active_page_id() == main_page["page_id"], (
        "targeting board-note must leave the primary board's active page untouched"
    )


def test_set_active_page_without_board_id_keeps_targeting_the_primary_board(mcp, services, two_boards):
    """Backward compatibility: omitting board_id is the legacy primary-board call."""
    page = assert_ok(
        call(mcp, "create_page", name="Legacy", template_lines=FLAGSHIP_TEMPLATE, device_type="flagship"),
        "create_page",
    )

    assert_ok(call(mcp, "set_active_page", page_id=page["page_id"]), "set_active_page")

    assert two_boards.get_active_page_id() == page["page_id"]
    assert two_boards.get_active_page_id(board_id="board-note") is None


def test_set_schedule_mode_with_board_id_changes_only_that_board(mcp, services, two_boards):
    assert_ok(call(mcp, "set_schedule_mode", enabled=True, board_id="board-note"), "set_schedule_mode")

    assert two_boards.is_schedule_enabled("board-note") is True
    assert two_boards.is_schedule_enabled("board-main") is False, (
        "targeting board-note must leave the primary board's schedule mode untouched"
    )


def test_set_schedule_mode_without_board_id_keeps_targeting_the_primary_board(mcp, services, two_boards):
    assert_ok(call(mcp, "set_schedule_mode", enabled=True), "set_schedule_mode")

    assert two_boards.is_schedule_enabled("board-main") is True
    assert two_boards.is_schedule_enabled("board-note") is False


def test_set_schedule_mode_reports_an_unknown_board(mcp, services, two_boards):
    message = call_expect_error(mcp, "set_schedule_mode", enabled=True, board_id="no-such-board")

    assert "no-such-board" in message
    assert two_boards.is_schedule_enabled("board-main") is False
    assert two_boards.is_schedule_enabled("board-note") is False


def test_get_settings_summary_reports_boards_schedule_and_active_page(mcp, services, two_boards):
    """The troubleshoot prompt walks schedule + active page; the boards list is
    what lets a model target board 2 and pick correct dimensions (#1765)."""
    page = assert_ok(
        call(mcp, "create_page", name="Summary", template_lines=FLAGSHIP_TEMPLATE, device_type="flagship"),
        "create_page",
    )
    assert_ok(call(mcp, "set_active_page", page_id=page["page_id"]), "set_active_page")
    two_boards.set_schedule_enabled(True, board_id="board-note")

    result = assert_ok(call(mcp, "get_settings_summary"), "get_settings_summary")

    assert result.get("active_page_id") == page["page_id"]
    assert result.get("schedule", {}).get("enabled") is False, "schedule reflects the primary board"

    boards = {b["id"]: b for b in result.get("boards", [])}
    assert set(boards) == {"board-main", "board-note"}

    main = boards["board-main"]
    assert main["name"] == "Living Room"
    assert main["device_type"] == "flagship"
    assert (main["rows"], main["cols"]) == (6, 22)
    assert main["primary"] is True
    assert main["active_page_id"] == page["page_id"]
    assert "error" in main, "the #1813 per-board init error surface is part of the contract"

    note = boards["board-note"]
    assert note["device_type"] == "note"
    assert (note["rows"], note["cols"]) == (3, 15)
    assert note["primary"] is False
    assert note["schedule_enabled"] is True
    assert note["paused"] is False and note["enabled"] is True


def test_get_settings_summary_boards_never_leak_credentials(mcp, services, two_boards):
    two_boards.set_boards(
        [
            {
                "id": "board-main",
                "name": "Living Room",
                "device_type": "flagship",
                "host": "192.168.0.99",
                "local_api_key": "test_secret_key",
            },
            {"id": "board-note", "name": "Kitchen", "device_type": "note"},
        ]
    )

    result = assert_ok(call(mcp, "get_settings_summary"), "get_settings_summary")

    flat = json.dumps(result.get("boards", []))
    assert "test_secret_key" not in flat, "a board API key leaked through get_settings_summary"
    assert "192.168.0.99" not in flat, "a board host leaked through get_settings_summary"


# ---------------------------------------------------------------------------
# Read-back and action tools — issue #1765
#
# The MCP surface was write-only: nothing reported the resolved active page,
# the board's current content, or a saved page's rendered output, and there
# was no ad-hoc send. The display engine is faked with a minimal object (not
# a MagicMock) so a tool calling a method that does not exist raises.
# ---------------------------------------------------------------------------


class _FakeClient:
    def __init__(self):
        self.rendered: list[list[list[int]]] = []
        self.render_kwargs: list[dict[str, Any]] = []
        self.snapped: list[list[list[int]]] = []
        self._last_characters = None

    def render(self, board_array, **kwargs):
        self.rendered.append(board_array)
        self.render_kwargs.append(kwargs)
        self._last_characters = board_array
        return (True, True)

    def send_characters(self, board_array, **kwargs):
        # The Transition Lab snaps the from-page onto the board plainly
        # before animating to the to-page.
        self.snapped.append(board_array)
        self._last_characters = board_array
        return True


class _FakeRuntime:
    def __init__(self, client):
        self.client = client
        self.polled_characters = None
        self.polled_at = None


class _FakeEngine:
    """Just the DisplayService surface the board tools are allowed to touch."""

    def __init__(self, board_ids):
        self.runtimes = {bid: _FakeRuntime(_FakeClient()) for bid in board_ids}
        self._primary_id = board_ids[0]
        self.out_of_band: list = []
        self.refreshes = 0
        self._polled_characters = None
        self._polled_at = None

    @property
    def vb_client(self):
        return self.runtimes[self._primary_id].client

    def get_board_client(self, board_id):
        rt = self.runtimes.get(board_id)
        return rt.client if rt else None

    def get_runtime(self, board_id):
        return self.runtimes.get(board_id)

    def mark_showing_out_of_band(self, board_id=None):
        self.out_of_band.append(board_id)

    def request_board_refresh(self):
        self.refreshes += 1


@pytest.fixture
def engine(two_boards, monkeypatch):
    fake = _FakeEngine(["board-main", "board-note"])
    monkeypatch.setattr("src.api_server.get_service", lambda: fake)
    return fake


# -- send_message -----------------------------------------------------------


def test_send_message_renders_to_the_primary_board_client(mcp, services, engine):
    result = assert_ok(call(mcp, "send_message", text="HELLO"), "send_message")

    assert result["status"] == "success"
    grids = engine.vb_client.rendered
    assert len(grids) == 1, "send_message did not render exactly once"
    assert (len(grids[0]), len(grids[0][0])) == (6, 22), "primary flagship grid must be 6x22"
    assert engine.runtimes["board-note"].client.rendered == [], "the other board was touched"


def test_send_message_with_board_id_targets_that_board_at_its_own_size(mcp, services, engine):
    assert_ok(call(mcp, "send_message", text="HI", board_id="board-note"), "send_message")

    grids = engine.runtimes["board-note"].client.rendered
    assert len(grids) == 1
    assert (len(grids[0]), len(grids[0][0])) == (3, 15), "note board grid must be 3x15, not flagship 6x22"
    assert engine.vb_client.rendered == [], "the primary board was touched"


def test_send_message_marks_the_write_out_of_band(mcp, services, engine):
    """Issue #1794/#1831: an ad-hoc send bypasses the display loop and the
    state publisher must know the board no longer shows the configured page."""
    assert_ok(call(mcp, "send_message", text="HELLO"), "send_message")

    assert engine.out_of_band == [None], "primary send must be marked out-of-band"


def test_send_message_to_a_paused_board_is_blocked_without_touching_it(mcp, services, engine, two_boards):
    two_boards.set_paused(True, board_id="board-note")

    result = call(mcp, "send_message", text="HI", board_id="board-note")

    assert result.get("status") == "blocked", f"a paused board accepted a send: {result}"
    assert result.get("paused") is True
    assert engine.runtimes["board-note"].client.rendered == []


def test_send_message_reports_an_unknown_board(mcp, services, engine):
    message = call_expect_error(mcp, "send_message", text="HI", board_id="no-such-board")

    assert "no-such-board" in message
    assert engine.vb_client.rendered == []


class _UnchangedClient(_FakeClient):
    """The board already shows this content: ``(True, False)``, no throttle."""

    def render(self, board_array, **kwargs):
        self.render_kwargs.append(kwargs)
        return (True, False)


def _throttled_client():
    """A REAL cloud client 5s into its 15s send floor: the next write is
    DROPPED with the same ``(True, False)`` an unchanged skip reports (#1794).
    Real, not a stub: the verdict is per call (tests/test_send_outcome.py)."""
    from tests.test_send_outcome import throttled_cloud_client

    return throttled_cloud_client({"t": 1000.0}, elapsed=5.0)


def test_send_message_unchanged_content_is_a_skipped_success_not_an_error(mcp, services, engine):
    engine.runtimes["board-main"].client = _UnchangedClient()

    result = call(mcp, "send_message", text="HELLO")

    assert result["status"] == "success", result
    assert result["skipped"] is True


def test_send_message_dropped_by_the_send_floor_is_an_error_with_a_retry_hint(mcp, services, engine):
    """#1931: a write the board's send floor dropped never reached the board.

    Reporting it as ``skipped`` success told the model both of two rapid
    sends landed. It is now the same refusal REST answers with 429: an
    error (protocol ``isError``) whose text carries the retry window, since
    the MCP error path has neither a ``Retry-After`` header nor
    ``structuredContent`` to put it in.
    """
    engine.runtimes["board-main"].client = _throttled_client()

    message = call_expect_error(mcp, "send_message", text="HELLO")

    assert "every 15s" in message, message
    assert "Retry in 10s" in message, f"the hint must be the REMAINING window, not the whole floor: {message}"


def test_send_message_dropped_by_the_send_floor_does_no_post_send_bookkeeping(mcp, services, engine):
    """Nothing landed, so the board is not marked out-of-band and no adaptive
    refresh is requested — the bookkeeping a delivered write owes."""
    engine.runtimes["board-main"].client = _throttled_client()

    call_expect_error(mcp, "send_message", text="HELLO")

    assert engine.out_of_band == []
    assert engine.refreshes == 0


def test_blank_board_dropped_by_the_send_floor_is_an_error_with_the_retry_window(mcp, services, engine):
    """The forced out-of-band grid sends (blank/fill/debug card) share the
    send_message refusal: the floor, the remaining window, and no bookkeeping
    — not a hand-rolled "every few seconds"."""
    engine.runtimes["board-main"].client = _throttled_client()

    message = call_expect_error(mcp, "blank_board")

    assert "every 15s" in message, message
    assert "Retry in 10s" in message, message
    assert engine.out_of_band == []


# -- get_active_page --------------------------------------------------------


def test_get_active_page_reads_back_the_selection_per_board(mcp, services, two_boards, monkeypatch):
    monkeypatch.setattr("src.api_server.get_service", lambda: None)
    main_page = assert_ok(
        call(mcp, "create_page", name="Main", template_lines=FLAGSHIP_TEMPLATE, device_type="flagship"),
        "create_page",
    )
    note_page = assert_ok(
        call(mcp, "create_page", name="Note", template_lines=NOTE_TEMPLATE, device_type="note"),
        "create_page",
    )
    assert_ok(call(mcp, "set_active_page", page_id=main_page["page_id"]), "set_active_page")
    assert_ok(
        call(mcp, "set_active_page", page_id=note_page["page_id"], board_id="board-note"),
        "set_active_page",
    )

    primary = assert_ok(call(mcp, "get_active_page"), "get_active_page")
    assert primary["active_ref"] == main_page["page_id"]
    assert primary["resolved_page_id"] == main_page["page_id"]
    assert primary["source"] == "manual"
    assert primary["page"]["name"] == "Main"

    note = assert_ok(call(mcp, "get_active_page", board_id="board-note"), "get_active_page")
    assert note["active_ref"] == note_page["page_id"]
    assert note["page"]["device_type"] == "note"


def test_get_active_page_resolves_a_collection_to_its_member(mcp, services, two_boards, monkeypatch):
    monkeypatch.setattr("src.api_server.get_service", lambda: None)
    page = assert_ok(
        call(mcp, "create_page", name="Member", template_lines=FLAGSHIP_TEMPLATE, device_type="flagship"),
        "create_page",
    )
    coll = assert_ok(
        call(mcp, "create_collection", name="Loop", page_ids=[page["page_id"]]),
        "create_collection",
    )
    assert_ok(call(mcp, "set_active_page", page_id=coll["collection_id"]), "set_active_page")

    result = assert_ok(call(mcp, "get_active_page"), "get_active_page")

    assert result["active_ref"] == coll["collection_id"]
    assert result["resolved_page_id"] == page["page_id"]
    assert result["page"]["name"] == "Member"


def test_get_active_page_reports_an_unknown_board(mcp, services, two_boards):
    message = call_expect_error(mcp, "get_active_page", board_id="no-such-board")
    assert "no-such-board" in message


# -- get_board_content ------------------------------------------------------


def test_get_board_content_reads_the_primary_poll_cache(mcp, services, engine):
    grid = [[1] * 22 for _ in range(6)]
    engine._polled_characters = grid

    result = assert_ok(call(mcp, "get_board_content"), "get_board_content")

    assert result["characters"] == grid
    assert result["source"] == "polled"
    assert (result["rows"], result["cols"]) == (6, 22)
    assert result["message"].splitlines()[0] == "A" * 22


def test_get_board_content_reads_a_secondary_boards_runtime_cache(mcp, services, engine):
    """After a send to board-note, its content is readable without a live poll."""
    assert_ok(call(mcp, "send_message", text="HI", board_id="board-note"), "send_message")

    result = assert_ok(call(mcp, "get_board_content", board_id="board-note"), "get_board_content")

    assert result["source"] == "last_sent"
    assert (result["rows"], result["cols"]) == (3, 15)
    assert result["characters"] == engine.runtimes["board-note"].client._last_characters


def test_get_board_content_is_null_when_nothing_was_ever_sent(mcp, services, engine):
    result = assert_ok(call(mcp, "get_board_content", board_id="board-note"), "get_board_content")
    assert result["characters"] is None
    assert result["message"] is None


def test_get_board_content_serves_the_primary_by_its_own_id_when_sentinel_keyed(mcp, services, two_boards, monkeypatch):
    """Legacy installs key the primary runtime under the __primary__ sentinel,
    not its settings board id. Asking for the primary by its OWN id then
    missed every cache and returned nulls, while omitting board_id worked —
    mirror the mark_showing_out_of_band fallback and route the primary's id
    to the primary path (#1874 review).
    """
    fake = _FakeEngine(["__primary__", "board-note"])
    grid = [[1] * 22 for _ in range(6)]
    fake._polled_characters = grid
    monkeypatch.setattr("src.api_server.get_service", lambda: fake)

    result = assert_ok(call(mcp, "get_board_content", board_id="board-main"), "get_board_content")

    assert result["characters"] == grid, "the primary's own id missed the sentinel-keyed cache"
    assert result["source"] == "polled"
    assert result["board_id"] == "board-main"


# -- preview_saved_page -----------------------------------------------------


def test_preview_saved_page_renders_the_stored_page(mcp, services):
    created = assert_ok(
        call(mcp, "create_page", name="Stored", template_lines=FLAGSHIP_TEMPLATE, device_type="flagship"),
        "create_page",
    )

    result = assert_ok(call(mcp, "preview_saved_page", page_id=created["page_id"]), "preview_saved_page")

    assert result["name"] == "Stored"
    assert len(result["rows"]) == 6, "a flagship page must render 6 rows"
    assert result["rows"][0].strip() == "HELLO"
    assert "line_metadata" in result


def test_preview_saved_page_reports_board_fit(mcp, services, two_boards, monkeypatch):
    monkeypatch.setattr("src.api_server.get_service", lambda: None)
    created = assert_ok(
        call(mcp, "create_page", name="Flag", template_lines=FLAGSHIP_TEMPLATE, device_type="flagship"),
        "create_page",
    )

    result = assert_ok(
        call(mcp, "preview_saved_page", page_id=created["page_id"], board_id="board-note"),
        "preview_saved_page",
    )

    assert result["fits_board"] is False, "a flagship page does not fit a note board"


def test_preview_saved_page_reports_an_unknown_board(mcp, services, two_boards):
    """fits_board: true for a board that does not exist is an answer about
    nothing. Same roster existence check as the sibling board tools —
    ToolError "Board not found" (#1874 review)."""
    created = assert_ok(
        call(mcp, "create_page", name="Flag", template_lines=FLAGSHIP_TEMPLATE, device_type="flagship"),
        "create_page",
    )

    message = call_expect_error(mcp, "preview_saved_page", page_id=created["page_id"], board_id="no-such-board")

    assert "no-such-board" in message


def test_preview_saved_page_unknown_page_is_an_error(mcp, services):
    message = call_expect_error(mcp, "preview_saved_page", page_id="no-such-page")
    assert "no-such-page" in message


# -- validate_template ------------------------------------------------------


def test_validate_template_accepts_a_clean_template(mcp, services):
    result = assert_ok(call(mcp, "validate_template", template=["HELLO", ""]), "validate_template")
    assert result["valid"] is True
    assert result["errors"] == []


def test_validate_template_reports_a_broken_formula_with_position(mcp, services):
    result = call(mcp, "validate_template", template="{{= 1 + @ }}")

    assert result["valid"] is False
    assert result["errors"], "a broken formula produced no errors"
    assert all({"line", "column", "message"} <= set(e) for e in result["errors"])


def test_validate_template_rejects_an_unknown_device_type(mcp, services):
    message = call_expect_error(mcp, "validate_template", template="HI", device_type="jumbotron")
    assert "jumbotron" in message


# ---------------------------------------------------------------------------
# render_page_preview fidelity — issue #1765
#
# The ad-hoc preview built its plugin context with NO BoardContext and took
# no line_metadata, so board-aware plugins previewed wrong and alignment/
# wrap could not be previewed at all — unlike the saved-page render path.
# ---------------------------------------------------------------------------


def _enable_harness_plugin(mcp):
    assert_ok(
        call(mcp, "configure_plugin", plugin_id=PLUGIN_ID, config={"station_id": "9447427"}),
        "configure_plugin",
    )
    assert_ok(call(mcp, "enable_plugin", plugin_id=PLUGIN_ID), "enable_plugin")


def test_render_page_preview_gives_plugins_the_real_board_context(mcp, plugins):
    _enable_harness_plugin(mcp)

    result = assert_ok(
        call(
            mcp,
            "render_page_preview",
            template_lines=["{{" + PLUGIN_ID + ".board_cols}}", "", ""],
            device_type="note",
        ),
        "render_page_preview",
    )

    first_row = result["rendered"].split("\n")[0]
    assert "15" in first_row, f"a note render must hand plugins a 15-column BoardContext; the plugin saw: {first_row!r}"
    assert PLUGIN_ID in result["context_plugins"]


def test_render_page_preview_applies_line_metadata(mcp, services):
    result = assert_ok(
        call(
            mcp,
            "render_page_preview",
            template_lines=["HI", "", "", "", "", ""],
            device_type="flagship",
            line_metadata=[{"alignment": "center"}],
        ),
        "render_page_preview",
    )

    first_row = result["rendered"].split("\n")[0]
    assert first_row.strip() == "HI"
    assert first_row.index("HI") > 0, "center alignment from line_metadata was not applied"


# ---------------------------------------------------------------------------
# Page editor parity
#
# Every control the page editor saves must be reachable from update_page /
# create_page, and the sibling editor features — share strings, staff picks,
# the live display, the Transition Lab — need tools of their own. Each test
# reads the state back through get_page / list_pages / the fake board client,
# never through a call record.
# ---------------------------------------------------------------------------


def test_update_page_retargets_device_type_and_get_page_reads_it_back(mcp, services):
    created = assert_ok(
        call(mcp, "create_page", name="Retarget", template_lines=FLAGSHIP_TEMPLATE, device_type="flagship"),
        "create_page",
    )
    page_id = created["page_id"]

    result = assert_ok(
        call(mcp, "update_page", page_id=page_id, device_type="note", template_lines=NOTE_TEMPLATE),
        "update_page (device_type)",
    )
    assert result["incompatible_references"] == [], "no board references this page yet"

    page = assert_ok(call(mcp, "get_page", page_id=page_id), "get_page")
    assert page["device_type"] == "note", "update_page reported success but device_type did not change"
    assert page["template"] == NOTE_TEMPLATE


def test_update_page_sets_note_array_geometry(mcp, services):
    created = assert_ok(
        call(mcp, "create_page", name="Array", template_lines=FLAGSHIP_TEMPLATE, device_type="flagship"),
        "create_page",
    )
    page_id = created["page_id"]

    assert_ok(
        call(
            mcp,
            "update_page",
            page_id=page_id,
            device_type="note_array",
            notes_wide=2,
            notes_tall=1,
            template_lines=NOTE_TEMPLATE,
        ),
        "update_page (note_array)",
    )

    page = assert_ok(call(mcp, "get_page", page_id=page_id), "get_page")
    assert page["device_type"] == "note_array"
    assert (page["notes_wide"], page["notes_tall"]) == (2, 1), "note-array geometry was not persisted"


def test_update_page_persists_line_metadata(mcp, services):
    created = assert_ok(
        call(mcp, "create_page", name="Aligned", template_lines=FLAGSHIP_TEMPLATE, device_type="flagship"),
        "create_page",
    )
    page_id = created["page_id"]

    metadata = [{"alignment": "center", "wrap": True}] + [{"alignment": "left", "wrap": False}] * 5
    assert_ok(call(mcp, "update_page", page_id=page_id, line_metadata=metadata), "update_page (line_metadata)")

    page = assert_ok(call(mcp, "get_page", page_id=page_id), "get_page")
    assert page["line_metadata"] == metadata, "line_metadata was not persisted"
    assert page["template"] == FLAGSHIP_TEMPLATE, "setting line_metadata destroyed the template"


def test_update_page_persists_a_per_page_transition_override(mcp, services):
    created = assert_ok(
        call(mcp, "create_page", name="Animated", template_lines=FLAGSHIP_TEMPLATE, device_type="flagship"),
        "create_page",
    )
    page_id = created["page_id"]

    assert_ok(
        call(
            mcp,
            "update_page",
            page_id=page_id,
            transition_strategy="row",
            transition_interval_ms=120,
            transition_step_size=2,
        ),
        "update_page (transition)",
    )

    page = assert_ok(call(mcp, "get_page", page_id=page_id), "get_page")
    assert page["transition_strategy"] == "row"
    assert page["transition_interval_ms"] == 120
    assert page["transition_step_size"] == 2


def test_update_page_clear_transition_override_restores_the_system_default(mcp, services):
    """``None`` means "unchanged" for every optional argument, so removing an
    override needs an explicit flag — the same escape hatch update_schedule
    has for end_time."""
    created = assert_ok(
        call(
            mcp,
            "create_page",
            name="Animated",
            template_lines=FLAGSHIP_TEMPLATE,
            device_type="flagship",
            transition_strategy="row",
            transition_interval_ms=120,
        ),
        "create_page",
    )
    page_id = created["page_id"]
    assert assert_ok(call(mcp, "get_page", page_id=page_id), "get_page")["transition_strategy"] == "row"

    assert_ok(call(mcp, "update_page", page_id=page_id, clear_transition_override=True), "update_page (clear)")

    page = assert_ok(call(mcp, "get_page", page_id=page_id), "get_page")
    assert page["transition_strategy"] is None, "the override was not cleared"
    assert page["transition_interval_ms"] is None
    assert page["transition_step_size"] is None
    assert page["template"] == FLAGSHIP_TEMPLATE


def test_update_page_reports_the_references_a_retarget_leaves_incompatible(mcp, services, two_boards):
    """Shrinking a flagship page to a note while the flagship board shows it:
    the REST layer answers ``incompatible_references`` and the editor shows
    them; the tool must relay the same list rather than a bare success."""
    created = assert_ok(
        call(mcp, "create_page", name="Shown", template_lines=FLAGSHIP_TEMPLATE, device_type="flagship"),
        "create_page",
    )
    page_id = created["page_id"]
    two_boards.set_active_page_id(page_id, board_id="board-main")

    result = assert_ok(
        call(mcp, "update_page", page_id=page_id, device_type="note", template_lines=NOTE_TEMPLATE),
        "update_page (retarget)",
    )

    refs = result["incompatible_references"]
    assert refs, "the retarget stranded board-main's active page but nothing was reported"
    assert {(r["board_id"], r["surface"]) for r in refs} == {("board-main", "active_page")}
    # Warn-only: the reference itself is left alone, exactly like REST.
    assert two_boards.get_active_page_id(board_id="board-main") == page_id


def test_create_page_persists_every_editor_field(mcp, services):
    metadata = [{"alignment": "right", "wrap": False}] * 3
    created = assert_ok(
        call(
            mcp,
            "create_page",
            name="Everything",
            template_lines=NOTE_TEMPLATE,
            device_type="note_array",
            notes_wide=2,
            notes_tall=1,
            duration_seconds=45,
            line_metadata=metadata,
            transition_strategy="column",
            transition_interval_ms=80,
            transition_step_size=3,
        ),
        "create_page",
    )

    page = assert_ok(call(mcp, "get_page", page_id=created["page_id"]), "get_page")
    assert page["device_type"] == "note_array"
    assert (page["notes_wide"], page["notes_tall"]) == (2, 1)
    assert page["duration_seconds"] == 45
    assert page["line_metadata"] == metadata
    assert page["transition_strategy"] == "column"
    assert page["transition_interval_ms"] == 80
    assert page["transition_step_size"] == 3


def test_render_page_preview_sizes_a_note_array_from_notes_wide(mcp, plugins):
    _enable_harness_plugin(mcp)

    result = assert_ok(
        call(
            mcp,
            "render_page_preview",
            template_lines=["{{" + PLUGIN_ID + ".board_cols}}", "", ""],
            device_type="note_array",
            notes_wide=2,
            notes_tall=1,
        ),
        "render_page_preview",
    )

    rows = result["rendered"].split("\n")
    assert "30" in rows[0], f"a 2-wide note array is 30 columns; the plugin saw: {rows[0]!r}"
    assert len(rows) == 3, "a 2x1 note array is 3 rows tall"
    assert (result["rows"], result["cols"]) == (3, 30)


# -- share strings -----------------------------------------------------------


def test_export_page_then_import_page_round_trips_the_template(mcp, services):
    metadata = [{"alignment": "center", "wrap": False}] * 6
    created = assert_ok(
        call(
            mcp,
            "create_page",
            name="Shared",
            template_lines=FLAGSHIP_TEMPLATE,
            device_type="flagship",
            line_metadata=metadata,
            duration_seconds=60,
        ),
        "create_page",
    )

    exported = assert_ok(call(mcp, "export_page", page_id=created["page_id"]), "export_page")
    assert exported["share_string"], "export_page returned no share string"

    imported = assert_ok(call(mcp, "import_page", share_string=exported["share_string"]), "import_page")
    assert imported["page_id"] != created["page_id"], "import must create a NEW page"

    copy = assert_ok(call(mcp, "get_page", page_id=imported["page_id"]), "get_page")
    assert copy["name"] == "Shared"
    assert copy["template"] == FLAGSHIP_TEMPLATE
    assert copy["line_metadata"] == metadata
    assert copy["duration_seconds"] == 60
    assert len(assert_ok(call(mcp, "list_pages"), "list_pages")) == 2


def test_import_page_rejects_a_string_that_is_not_a_share_string(mcp, services):
    message = call_expect_error(mcp, "import_page", share_string="definitely not base64 json")
    assert "share string" in message.lower()
    assert assert_ok(call(mcp, "list_pages"), "list_pages") == [], "a rejected import must persist nothing"


def test_export_page_reports_an_unknown_page(mcp, services):
    assert "not found" in call_expect_error(mcp, "export_page", page_id="nope").lower()


# -- staff picks -------------------------------------------------------------


def test_list_staff_picks_lists_the_catalog_without_share_strings(mcp, services):
    picks = assert_ok(call(mcp, "list_staff_picks"), "list_staff_picks")
    assert picks, "the checked-in catalog is not empty"
    for pick in picks:
        assert {"id", "name", "device_type", "required_plugins"} <= set(pick)
        assert "share_string" not in pick, "share strings are served only by import_staff_pick"


def test_import_staff_pick_creates_a_page_from_the_catalog(mcp, services):
    pick = assert_ok(call(mcp, "list_staff_picks"), "list_staff_picks")[0]

    imported = assert_ok(call(mcp, "import_staff_pick", pick_id=pick["id"]), "import_staff_pick")

    page = assert_ok(call(mcp, "get_page", page_id=imported["page_id"]), "get_page")
    assert page["template"], "the imported pick has no template"
    assert page["device_type"] == pick["device_type"]
    assert imported["required_plugins"] == pick["required_plugins"]


def test_import_staff_pick_reports_an_unknown_pick(mcp, services):
    assert "not found" in call_expect_error(mcp, "import_staff_pick", pick_id="no-such-pick").lower()
    assert assert_ok(call(mcp, "list_pages"), "list_pages") == []


# -- current display ---------------------------------------------------------


def test_get_current_display_returns_the_active_pages_raw_template(mcp, services, two_boards):
    created = assert_ok(
        call(
            mcp,
            "create_page",
            name="Live",
            template_lines=["{{date_time.time_12h}}", "", "", "", "", ""],
            device_type="flagship",
            line_metadata=[{"alignment": "center", "wrap": False}] * 6,
        ),
        "create_page",
    )
    two_boards.set_active_page_id(created["page_id"])

    shown = assert_ok(call(mcp, "get_current_display"), "get_current_display")

    assert shown["page_id"] == created["page_id"]
    assert shown["template"] == ["{{date_time.time_12h}}", "", "", "", "", ""], "the RAW template, variables intact"
    assert shown["line_metadata"][0] == {"alignment": "center", "wrap": False}
    assert shown["device_type"] == "flagship"


def test_get_current_display_follows_the_named_board(mcp, services, two_boards):
    main = assert_ok(
        call(mcp, "create_page", name="Main", template_lines=FLAGSHIP_TEMPLATE, device_type="flagship"),
        "create_page",
    )
    note = assert_ok(
        call(mcp, "create_page", name="Note", template_lines=NOTE_TEMPLATE, device_type="note"),
        "create_page",
    )
    two_boards.set_active_page_id(main["page_id"], board_id="board-main")
    two_boards.set_active_page_id(note["page_id"], board_id="board-note")

    shown = assert_ok(call(mcp, "get_current_display", board_id="board-note"), "get_current_display")
    assert shown["page_id"] == note["page_id"]
    assert shown["template"] == NOTE_TEMPLATE


def test_get_current_display_without_an_active_page_is_an_error(mcp, services, two_boards):
    assert "no active page" in call_expect_error(mcp, "get_current_display").lower()


# -- formula functions -------------------------------------------------------


def test_list_formula_functions_describes_every_function(mcp, services):
    result = assert_ok(call(mcp, "list_formula_functions"), "list_formula_functions")
    functions = result["functions"]
    assert "IF" in functions and "UPPER" in functions
    for name, entry in functions.items():
        assert set(entry) == {"category", "signature", "summary"}, f"{name}: {entry}"
        assert entry["signature"].startswith(name)


# -- Transition Lab ----------------------------------------------------------

TRANSITION_PLUGIN_ID = "harness_wipe"

_TRANSITION_MANIFEST = {
    "id": TRANSITION_PLUGIN_ID,
    "name": "Harness Wipe",
    "version": "1.0.0",
    "description": "Fixture transition plugin for MCP state-effect tests.",
    "author": "FiestaBoard Tests",
    "icon": "type",
    "category": "transition",
    "plugin_type": "transition",
    "settings_schema": {"type": "object", "properties": {"frame_interval_ms": {"type": "integer", "default": 100}}},
    "transition_settings": {"interruptible": True, "min_interval_ms": 25, "max_frames": 5, "max_runtime_seconds": 60},
}


@pytest.fixture
def transition_lab(engine, monkeypatch):
    """Beta on, one hand-built transition plugin installed, fake board engine.

    The transitions service binds ``get_service`` at import time from
    ``src.display_runtime``, so the engine fake is patched there as well as
    where the ``engine`` fixture already puts it.
    """
    from src.plugins import registry as registry_mod
    from src.plugins.base import TransitionPluginBase
    from src.plugins.manifest import PluginManifest
    from src.settings.service import get_settings_service

    class _Wipe(TransitionPluginBase):
        @property
        def plugin_id(self) -> str:
            return TRANSITION_PLUGIN_ID

        def generate_frames(self, from_grid, to_grid, device, config):
            yield [list(row) for row in from_grid], int(config.get("frame_interval_ms", 100))
            yield to_grid, 0

    fresh = registry_mod.PluginRegistry()
    plugin = _Wipe(_TRANSITION_MANIFEST)
    plugin.config = {"frame_interval_ms": 50}
    fresh._plugins[TRANSITION_PLUGIN_ID] = plugin
    fresh._manifests[TRANSITION_PLUGIN_ID] = PluginManifest.from_dict(_TRANSITION_MANIFEST)
    fresh._enabled[TRANSITION_PLUGIN_ID] = True
    monkeypatch.setattr(registry_mod, "_registry", fresh)
    monkeypatch.setattr("src.transitions.service.get_service", lambda: engine)
    monkeypatch.setattr("src.transitions.service.LIVE_TEST_FROM_HOLD_SECONDS", 0)
    get_settings_service().update_beta_settings({"transition_plugins_enabled": True})
    return engine


def test_list_transition_plugins_is_gated_behind_the_beta_flag(mcp, services, two_boards):
    assert "beta" in call_expect_error(mcp, "list_transition_plugins").lower()


def test_list_transition_plugins_lists_the_installed_transition_plugins(mcp, services, transition_lab):
    result = assert_ok(call(mcp, "list_transition_plugins"), "list_transition_plugins")
    by_id = {p["id"]: p for p in result["plugins"]}
    assert TRANSITION_PLUGIN_ID in by_id
    entry = by_id[TRANSITION_PLUGIN_ID]
    assert entry["strategy"] == f"plugin:{TRANSITION_PLUGIN_ID}", "the string a page stores as transition_strategy"
    assert entry["config"] == {"frame_interval_ms": 50}
    assert entry["transition_settings"]["max_frames"] == 5


def test_test_transition_live_drives_the_plugin_on_the_board(mcp, services, transition_lab):
    target = assert_ok(
        call(mcp, "create_page", name="Target", template_lines=FLAGSHIP_TEMPLATE, device_type="flagship"),
        "create_page",
    )
    origin = assert_ok(
        call(mcp, "create_page", name="Origin", template_lines=["BYE", "", "", "", "", ""], device_type="flagship"),
        "create_page",
    )

    result = assert_ok(
        call(
            mcp,
            "test_transition_live",
            plugin_id=TRANSITION_PLUGIN_ID,
            to_page_id=target["page_id"],
            from_page_id=origin["page_id"],
            config={"frame_interval_ms": 30},
        ),
        "test_transition_live",
    )

    assert result["sent"] is True
    client = transition_lab.vb_client
    assert len(client.snapped) == 1, "the from-page must be snapped onto the board first"
    assert len(client.rendered) == 1, "the to-page must be rendered exactly once"
    assert (len(client.rendered[0]), len(client.rendered[0][0])) == (6, 22)
    kwargs = client.render_kwargs[0]
    assert kwargs["strategy"] == f"plugin:{TRANSITION_PLUGIN_ID}"
    assert kwargs["transition_config"] == {"frame_interval_ms": 30}, "per-run config overrides the bound config"
    assert transition_lab.runtimes["board-note"].client.rendered == [], "the other board was touched"


def test_test_transition_live_on_a_paused_board_is_blocked_without_touching_it(mcp, services, transition_lab):
    from src.settings.service import get_settings_service

    target = assert_ok(
        call(mcp, "create_page", name="Target", template_lines=NOTE_TEMPLATE, device_type="note"),
        "create_page",
    )
    get_settings_service().set_paused(True, board_id="board-note")

    result = call(
        mcp,
        "test_transition_live",
        plugin_id=TRANSITION_PLUGIN_ID,
        to_page_id=target["page_id"],
        board_id="board-note",
    )

    assert result["status"] == "blocked", result
    assert result["paused"] is True
    assert transition_lab.runtimes["board-note"].client.rendered == []


def test_test_transition_live_reports_an_unknown_plugin(mcp, services, transition_lab):
    target = assert_ok(
        call(mcp, "create_page", name="Target", template_lines=FLAGSHIP_TEMPLATE, device_type="flagship"),
        "create_page",
    )
    message = call_expect_error(mcp, "test_transition_live", plugin_id="no_such_plugin", to_page_id=target["page_id"])
    assert "no_such_plugin" in message
    assert transition_lab.vb_client.rendered == []


def test_restore_board_snaps_the_board_back_to_its_active_page(mcp, services, transition_lab):
    from src.settings.service import get_settings_service

    active = assert_ok(
        call(mcp, "create_page", name="Active", template_lines=FLAGSHIP_TEMPLATE, device_type="flagship"),
        "create_page",
    )
    get_settings_service().set_active_page_id(active["page_id"])

    result = assert_ok(call(mcp, "restore_board"), "restore_board")

    assert result["page_id"] == active["page_id"]
    assert result["sent"] is True
    client = transition_lab.vb_client
    assert len(client.rendered) == 1
    assert client.render_kwargs[0]["strategy"] is None, "restore sends plainly, with no transition"


def test_restore_board_without_an_active_page_is_an_error(mcp, services, transition_lab):
    assert "no active page" in call_expect_error(mcp, "restore_board").lower()
    assert transition_lab.vb_client.rendered == []


# ---------------------------------------------------------------------------
# Schedules — every field the Schedules page's entry form saves
#
# The tools used to accept five of the sixteen ScheduleCreate fields, so the
# chat could not build an annual, one-off, sunrise/sunset or per-board entry
# at all. Each test re-reads the stored entry through the real service.
# ---------------------------------------------------------------------------


def _stored_schedule(services, schedule_id: str):
    entry = services["schedules"].get_schedule(schedule_id)
    assert entry is not None, f"schedule {schedule_id} is not in the store"
    return entry


def test_create_schedule_persists_the_annual_recurrence_fields(mcp, services):
    page_id = _make_page(mcp)

    created = assert_ok(
        call(
            mcp,
            "create_schedule",
            page_id=page_id,
            start_time="08:00",
            end_time="20:00",
            recurrence_type="annual_date",
            annual_date="12-24",
            annual_end_date="12-26",
        ),
        "create_schedule",
    )

    stored = _stored_schedule(services, created["schedule_id"])
    assert stored.recurrence_type == "annual_date"
    assert (stored.annual_date, stored.annual_end_date) == ("12-24", "12-26")


def test_create_schedule_persists_a_one_off_date_window(mcp, services):
    page_id = _make_page(mcp)

    created = assert_ok(
        call(
            mcp,
            "create_schedule",
            page_id=page_id,
            start_time="09:00",
            recurrence_type="one_off_date",
            one_off_date="2030-07-04",
            one_off_end_date="2030-07-05",
        ),
        "create_schedule",
    )

    stored = _stored_schedule(services, created["schedule_id"])
    assert stored.recurrence_type == "one_off_date"
    assert (stored.one_off_date, stored.one_off_end_date) == ("2030-07-04", "2030-07-05")


def test_create_schedule_persists_sun_times_and_custom_days(mcp, services):
    page_id = _make_page(mcp)

    created = assert_ok(
        call(
            mcp,
            "create_schedule",
            page_id=page_id,
            start_time="06:00",
            end_time="21:00",
            day_pattern="custom",
            custom_days=["monday", "friday"],
            start_type="sunrise",
            start_sun_offset=-30,
            end_type="sunset",
            end_sun_offset=45,
        ),
        "create_schedule",
    )

    stored = _stored_schedule(services, created["schedule_id"])
    assert stored.custom_days == ["monday", "friday"]
    assert (stored.start_type, stored.start_sun_offset) == ("sunrise", -30)
    assert (stored.end_type, stored.end_sun_offset) == ("sunset", 45)


def test_create_schedule_with_board_id_parents_the_entry_to_that_board(mcp, services, two_boards):
    page = assert_ok(
        call(mcp, "create_page", name="Note", template_lines=NOTE_TEMPLATE, device_type="note"),
        "create_page",
    )

    created = assert_ok(
        call(mcp, "create_schedule", page_id=page["page_id"], start_time="08:00", board_id="board-note"),
        "create_schedule",
    )

    assert _stored_schedule(services, created["schedule_id"]).board_id == "board-note"
    listed = assert_ok(call(mcp, "list_schedules", board_id="board-note"), "list_schedules")
    assert [s["id"] for s in listed["schedules"]] == [created["schedule_id"]]
    primary = assert_ok(call(mcp, "list_schedules"), "list_schedules")
    assert created["schedule_id"] not in {s["id"] for s in primary["schedules"]}


def test_create_schedule_reports_an_unknown_board_and_stores_nothing(mcp, services, two_boards):
    page_id = _make_page(mcp)

    message = call_expect_error(mcp, "create_schedule", page_id=page_id, start_time="08:00", board_id="no-such-board")

    assert "no-such-board" in message
    assert services["schedules"].list_schedules(board_id="*") == []


def test_update_schedule_changes_recurrence_and_sun_fields(mcp, services):
    page_id = _make_page(mcp)
    created = assert_ok(
        call(mcp, "create_schedule", page_id=page_id, start_time="08:00", end_time="17:00"),
        "create_schedule",
    )
    schedule_id = created["schedule_id"]

    assert_ok(
        call(
            mcp,
            "update_schedule",
            schedule_id=schedule_id,
            recurrence_type="annual_date",
            annual_date="01-01",
            end_type="sunset",
            end_sun_offset=-15,
        ),
        "update_schedule",
    )

    stored = _stored_schedule(services, schedule_id)
    assert (stored.recurrence_type, stored.annual_date) == ("annual_date", "01-01")
    assert (stored.end_type, stored.end_sun_offset) == ("sunset", -15)
    assert stored.end_time == "17:00", "the untouched fallback end_time was wiped by a partial update"


def test_update_schedule_clear_annual_end_date_makes_it_a_single_day(mcp, services):
    page_id = _make_page(mcp)
    created = assert_ok(
        call(
            mcp,
            "create_schedule",
            page_id=page_id,
            start_time="08:00",
            recurrence_type="annual_date",
            annual_date="12-24",
            annual_end_date="12-26",
        ),
        "create_schedule",
    )
    schedule_id = created["schedule_id"]

    assert_ok(call(mcp, "update_schedule", schedule_id=schedule_id, clear_annual_end_date=True), "update_schedule")

    stored = _stored_schedule(services, schedule_id)
    assert stored.annual_end_date is None, "clear_annual_end_date=True left the range end behind"
    assert stored.annual_date == "12-24"


def test_update_schedule_clear_one_off_end_date_makes_it_a_single_day(mcp, services):
    page_id = _make_page(mcp)
    created = assert_ok(
        call(
            mcp,
            "create_schedule",
            page_id=page_id,
            start_time="08:00",
            recurrence_type="one_off_date",
            one_off_date="2030-07-04",
            one_off_end_date="2030-07-05",
        ),
        "create_schedule",
    )
    schedule_id = created["schedule_id"]

    assert_ok(call(mcp, "update_schedule", schedule_id=schedule_id, clear_one_off_end_date=True), "update_schedule")

    assert _stored_schedule(services, schedule_id).one_off_end_date is None


# -- list_schedules: the Schedules page's view ---------------------------------


def test_list_schedules_reports_the_boards_default_page_and_schedule_mode(mcp, services, two_boards):
    page_id = _make_page(mcp)
    assert_ok(call(mcp, "set_default_page", page_id=page_id), "set_default_page")
    assert_ok(call(mcp, "set_schedule_mode", enabled=True), "set_schedule_mode")

    result = assert_ok(call(mcp, "list_schedules"), "list_schedules")

    assert result["board_id"] == "board-main"
    assert result["default_page_id"] == page_id
    assert result["schedule_enabled"] is True
    other = assert_ok(call(mcp, "list_schedules", board_id="board-note"), "list_schedules")
    assert other["default_page_id"] is None
    assert other["schedule_enabled"] is False


def test_list_schedules_resolves_a_sunrise_entry_to_todays_time(mcp, services, two_boards):
    """The stored start_time of a sun entry is only a fallback; the page
    shows the computed time, and so must the tool (resolved_start_time)."""
    # A public landmark, never a personal location: the Statue of Liberty.
    two_boards.update_location_settings({"latitude": 40.6892, "longitude": -74.0445})
    page_id = _make_page(mcp)
    created = assert_ok(
        call(mcp, "create_schedule", page_id=page_id, start_time="00:01", start_type="sunrise"),
        "create_schedule",
    )

    result = assert_ok(call(mcp, "list_schedules"), "list_schedules")

    entry = next(s for s in result["schedules"] if s["id"] == created["schedule_id"])
    assert entry["start_time"] == "00:01", "the stored fallback must still be reported as start_time"
    assert entry["start_type"] == "sunrise"
    assert entry["resolved_start_time"] != "00:01", "resolved_start_time must be today's sunrise, not the fallback"
    assert entry["resolved_end_time"] is None


def test_list_schedules_for_every_board_has_no_per_board_fields(mcp, services, two_boards):
    page_id = _make_page(mcp)
    assert_ok(call(mcp, "set_default_page", page_id=page_id), "set_default_page")

    result = assert_ok(call(mcp, "list_schedules", board_id="*"), "list_schedules")

    assert result["board_id"] == "*"
    assert result["default_page_id"] is None and result["schedule_enabled"] is None


def test_list_schedules_reports_an_unknown_board(mcp, services, two_boards):
    message = call_expect_error(mcp, "list_schedules", board_id="no-such-board")
    assert "no-such-board" in message


# -- validate_schedules ---------------------------------------------------------


def test_validate_schedules_reports_an_overlap_between_two_entries(mcp, services):
    page_id = _make_page(mcp)
    first = assert_ok(
        call(mcp, "create_schedule", page_id=page_id, start_time="08:00", end_time="12:00"),
        "create_schedule",
    )
    second = assert_ok(
        call(mcp, "create_schedule", page_id=page_id, start_time="11:00", end_time="13:00"),
        "create_schedule",
    )

    result = assert_ok(call(mcp, "validate_schedules"), "validate_schedules")

    assert result["valid"] is False
    pairs = {frozenset((o["schedule1_id"], o["schedule2_id"])) for o in result["overlaps"]}
    assert pairs == {frozenset((first["schedule_id"], second["schedule_id"]))}
    assert result["gaps"], "the uncovered hours must be reported as gaps"


def test_validate_schedules_is_clean_for_non_overlapping_entries(mcp, services):
    page_id = _make_page(mcp)
    assert_ok(call(mcp, "create_schedule", page_id=page_id, start_time="08:00", end_time="12:00"), "create_schedule")
    assert_ok(call(mcp, "create_schedule", page_id=page_id, start_time="12:00", end_time="18:00"), "create_schedule")

    result = assert_ok(call(mcp, "validate_schedules"), "validate_schedules")

    assert result["valid"] is True
    assert result["overlaps"] == []


# -- set_default_page -----------------------------------------------------------


def test_set_default_page_is_stored_per_board(mcp, services, two_boards):
    page_id = _make_page(mcp)
    note = assert_ok(
        call(mcp, "create_page", name="Note", template_lines=NOTE_TEMPLATE, device_type="note"),
        "create_page",
    )

    assert_ok(call(mcp, "set_default_page", page_id=page_id), "set_default_page (primary)")
    assert_ok(call(mcp, "set_default_page", page_id=note["page_id"], board_id="board-note"), "set_default_page")

    assert services["schedules"].get_default_page(board_id="board-main") == page_id
    assert services["schedules"].get_default_page(board_id="board-note") == note["page_id"]


def test_set_default_page_null_clears_it(mcp, services, two_boards):
    page_id = _make_page(mcp)
    assert_ok(call(mcp, "set_default_page", page_id=page_id), "set_default_page")

    result = assert_ok(call(mcp, "set_default_page", page_id=None), "set_default_page (clear)")

    assert result["default_page_id"] is None
    assert services["schedules"].get_default_page(board_id="board-main") is None
    assert assert_ok(call(mcp, "list_schedules"), "list_schedules")["default_page_id"] is None


def test_set_default_page_accepts_a_collection(mcp, services, two_boards):
    page_id = _make_page(mcp)
    coll = assert_ok(call(mcp, "create_collection", name="Gaps", page_ids=[page_id]), "create_collection")

    assert_ok(call(mcp, "set_default_page", page_id=coll["collection_id"]), "set_default_page")

    assert services["schedules"].get_default_page(board_id="board-main") == coll["collection_id"]


def test_set_default_page_rejects_an_unknown_page_and_stores_nothing(mcp, services, two_boards):
    message = call_expect_error(mcp, "set_default_page", page_id="no-such-page")

    assert "no-such-page" in message
    assert services["schedules"].get_default_page(board_id="board-main") is None


def test_set_default_page_reports_an_unknown_board(mcp, services, two_boards):
    page_id = _make_page(mcp)
    message = call_expect_error(mcp, "set_default_page", page_id=page_id, board_id="no-such-board")
    assert "no-such-board" in message


# -- update_setting('schedule_behavior') ---------------------------------------


def test_update_setting_schedule_behavior_persists_defer_on_reenable(mcp, services, two_boards, tmp_path):
    assert two_boards.get_schedule_settings().defer_on_reenable is False

    result = assert_ok(
        call(mcp, "update_setting", category="schedule_behavior", values={"defer_on_reenable": True}),
        "update_setting",
    )

    assert result["defer_on_reenable"] is True
    assert two_boards.get_schedule_settings().defer_on_reenable is True
    assert _reloaded_settings(tmp_path).get_schedule_settings().defer_on_reenable is True, "not persisted"


def test_update_setting_schedule_behavior_rejects_a_non_boolean(mcp, services, two_boards):
    """StrictBool on purpose: "yes" must not silently become True."""
    message = call_expect_error(
        mcp, "update_setting", category="schedule_behavior", values={"defer_on_reenable": "yes"}
    )

    assert "schedule_behavior" in message
    assert two_boards.get_schedule_settings().defer_on_reenable is False


# ---------------------------------------------------------------------------
# Collections — random mode and merge-on-update
# ---------------------------------------------------------------------------


def _stored_collection(services, collection_id: str):
    collection = services["collections"].get_collection(collection_id)
    assert collection is not None, f"collection {collection_id} is not in the store"
    return collection


def _variable_collection(mcp, services) -> tuple[str, str, str]:
    """A variable-mode collection with one rule; returns (collection_id, p1, p2)."""
    p1 = _make_page(mcp, "Rule Target")
    p2 = _make_page(mcp, "Fallback")
    created = assert_ok(
        call(
            mcp,
            "create_collection",
            name="Var",
            page_ids=[p1, p2],
            selection_mode="variable",
            rules=[{"expression": "1", "page_id": p1}],
            default_page_id=p2,
            poll_seconds=10,
        ),
        "create_collection",
    )
    return created["collection_id"], p1, p2


def test_create_collection_random_mode_stores_the_random_block(mcp, services):
    p1 = _make_page(mcp, "R1")
    p2 = _make_page(mcp, "R2")

    created = assert_ok(
        call(mcp, "create_collection", name="Shuffle", page_ids=[p1, p2], selection_mode="random", interval_seconds=45),
        "create_collection",
    )

    stored = _stored_collection(services, created["collection_id"])
    assert stored.selection_mode == "random"
    assert stored.random is not None and stored.random.interval_seconds == 45
    listed = next(c for c in call(mcp, "list_collections") if c["id"] == created["collection_id"])
    assert listed["random"] == {"interval_seconds": 45}


def test_update_collection_poll_seconds_alone_keeps_rules_and_default_page(mcp, services):
    """The old tool demanded default_page_id on every variable-mode touch;
    the form lets you change the poll cadence by itself."""
    collection_id, p1, p2 = _variable_collection(mcp, services)

    assert_ok(call(mcp, "update_collection", collection_id=collection_id, poll_seconds=30), "update_collection")

    stored = _stored_collection(services, collection_id)
    assert stored.variable.poll_seconds == 30
    assert stored.variable.default_page_id == p2, "a poll-only update wiped default_page_id"
    assert [r.page_id for r in stored.variable.rules] == [p1], "a poll-only update wiped the rules"


def test_update_collection_rules_alone_keeps_default_page_and_poll(mcp, services):
    collection_id, _p1, p2 = _variable_collection(mcp, services)

    assert_ok(
        call(mcp, "update_collection", collection_id=collection_id, rules=[{"expression": "0", "page_id": p2}]),
        "update_collection",
    )

    stored = _stored_collection(services, collection_id)
    assert [(r.expression, r.page_id) for r in stored.variable.rules] == [("0", p2)]
    assert stored.variable.default_page_id == p2
    assert stored.variable.poll_seconds == 10


def test_update_collection_switch_to_random_carries_the_interval_over(mcp, services):
    p1 = _make_page(mcp, "T1")
    p2 = _make_page(mcp, "T2")
    created = assert_ok(
        call(mcp, "create_collection", name="Rot", page_ids=[p1, p2], interval_seconds=20),
        "create_collection",
    )

    assert_ok(call(mcp, "update_collection", collection_id=created["collection_id"], selection_mode="random"), "update")

    stored = _stored_collection(services, created["collection_id"])
    assert stored.selection_mode == "random"
    assert stored.random is not None and stored.random.interval_seconds == 20


def test_update_collection_interval_in_random_mode_updates_the_random_block(mcp, services):
    p1 = _make_page(mcp, "S1")
    p2 = _make_page(mcp, "S2")
    created = assert_ok(
        call(mcp, "create_collection", name="Shuffle", page_ids=[p1, p2], selection_mode="random", interval_seconds=30),
        "create_collection",
    )

    assert_ok(call(mcp, "update_collection", collection_id=created["collection_id"], interval_seconds=90), "update")

    stored = _stored_collection(services, created["collection_id"])
    assert stored.selection_mode == "random"
    assert stored.random.interval_seconds == 90, "the interval landed somewhere random mode does not read"


def test_update_collection_switch_to_variable_still_needs_a_default_page(mcp, services):
    p1 = _make_page(mcp, "V1")
    created = assert_ok(call(mcp, "create_collection", name="Rot", page_ids=[p1]), "create_collection")

    message = call_expect_error(
        mcp, "update_collection", collection_id=created["collection_id"], selection_mode="variable"
    )

    assert "default_page_id" in message
    assert _stored_collection(services, created["collection_id"]).selection_mode == "time"


# ---------------------------------------------------------------------------
# Board state — the Home page's controls
# ---------------------------------------------------------------------------


def _reloaded_settings(tmp_path):
    """A fresh SettingsService over the same file: persisted, not just cached."""
    import src.settings.service as settings_module

    return settings_module.SettingsService(settings_file=str(tmp_path / "settings.json"))


# -- temporary override ---------------------------------------------------------


def test_set_temporary_override_with_a_saved_page_is_read_back(mcp, services, two_boards, tmp_path):
    page_id = _make_page(mcp)

    result = assert_ok(
        call(mcp, "set_temporary_override", page_id=page_id, duration_minutes=15),
        "set_temporary_override",
    )

    assert result["override"]["active"] is True
    status = assert_ok(call(mcp, "get_temporary_override"), "get_temporary_override")
    assert status["active"] is True
    assert status["page_id"] == page_id
    assert 0 < status["remaining_seconds"] <= 15 * 60
    assert status["revert_mode"] == "schedule"
    stored = _reloaded_settings(tmp_path).get_temporary_override()
    assert stored is not None and stored.page_id == page_id, "the override was not persisted to settings.json"


def test_set_temporary_override_with_one_off_lines_is_never_a_page(mcp, services, two_boards):
    before = {p.id for p in services["pages"].list_pages()}

    assert_ok(
        call(
            mcp,
            "set_temporary_override",
            template_lines=["BACK AT 3", "", ""],
            device_type="note",
            line_metadata=[{"alignment": "center"}],
        ),
        "set_temporary_override",
    )

    status = assert_ok(call(mcp, "get_temporary_override"), "get_temporary_override")
    assert status["active"] is True
    assert status["page_id"] is None
    assert status["template"] == ["BACK AT 3", "", ""]
    assert status["device_type"] == "note"
    assert status["line_metadata"] == [{"alignment": "center"}]
    assert status["expires_at"] is None and status["remaining_seconds"] is None, "no duration = indefinite"
    assert {p.id for p in services["pages"].list_pages()} == before, "a one-off must not be persisted as a page"


def test_get_active_page_reports_the_temporary_override(mcp, services, two_boards):
    page_id = _make_page(mcp)
    assert assert_ok(call(mcp, "get_active_page"), "get_active_page")["temporary_override"]["active"] is False

    assert_ok(call(mcp, "set_temporary_override", page_id=page_id, duration_minutes=5), "set_temporary_override")

    active = assert_ok(call(mcp, "get_active_page"), "get_active_page")
    assert active["temporary_override"]["active"] is True
    assert active["temporary_override"]["page_id"] == page_id


def test_set_temporary_override_rejects_both_forms_and_stores_nothing(mcp, services, two_boards):
    page_id = _make_page(mcp)

    message = call_expect_error(mcp, "set_temporary_override", page_id=page_id, template_lines=FLAGSHIP_TEMPLATE)

    assert "not both" in message
    assert two_boards.get_temporary_override() is None


def test_set_temporary_override_rejects_an_unknown_page(mcp, services, two_boards):
    message = call_expect_error(mcp, "set_temporary_override", page_id="no-such-page", duration_minutes=5)

    assert "no-such-page" in message
    assert two_boards.get_temporary_override() is None


def test_set_temporary_override_rejects_an_out_of_range_duration(mcp, services, two_boards):
    page_id = _make_page(mcp)

    message = call_expect_error(mcp, "set_temporary_override", page_id=page_id, duration_minutes=481)

    assert "480" in message
    assert two_boards.get_temporary_override() is None


def test_cancel_temporary_override_clears_it_and_applies_a_page_revert(mcp, services, two_boards):
    shown = _make_page(mcp, "Shown")
    after = _make_page(mcp, "After")
    assert_ok(
        call(
            mcp,
            "set_temporary_override",
            page_id=shown,
            duration_minutes=30,
            revert_mode="page",
            revert_page_id=after,
        ),
        "set_temporary_override",
    )

    result = assert_ok(call(mcp, "cancel_temporary_override"), "cancel_temporary_override")

    assert result["was_active"] is True and result["revert_mode"] == "page"
    assert two_boards.get_temporary_override() is None
    assert two_boards.get_active_page_id() == after, "the 'page' revert must be applied on cancel"
    assert assert_ok(call(mcp, "get_temporary_override"), "get_temporary_override")["active"] is False


def test_cancel_temporary_override_with_nothing_active_is_a_reported_no_op(mcp, services, two_boards):
    result = assert_ok(call(mcp, "cancel_temporary_override"), "cancel_temporary_override")

    assert result["was_active"] is False and result["revert_mode"] is None


# -- force_refresh ----------------------------------------------------------------


class _FakeCacheClient:
    def __init__(self):
        self.cache_cleared = False

    def clear_cache(self):
        self.cache_cleared = True


class _FakeRefreshEngine:
    """Just the DisplayService surface POST /force-refresh touches."""

    def __init__(self, sent: bool = True, error: str | None = None):
        self.vb_client = _FakeCacheClient()
        self.board_clients = {"board-note": _FakeCacheClient()}
        self.invalidated = False
        self.passes = 0
        self._outcome = (sent, error)

    def invalidate_all_board_content(self):
        self.invalidated = True

    def check_and_send_active_page_with_status(self):
        self.passes += 1
        return self._outcome


def test_force_refresh_clears_every_cache_and_drives_one_send_pass(mcp, services, two_boards, monkeypatch):
    fake = _FakeRefreshEngine(sent=True)
    monkeypatch.setattr("src.display_runtime.get_service", lambda: fake)

    result = assert_ok(call(mcp, "force_refresh"), "force_refresh")

    assert result["sent"] is True
    assert fake.invalidated, "the display loop's dedupe guard was not invalidated (#1794)"
    assert fake.vb_client.cache_cleared and fake.board_clients["board-note"].cache_cleared, (
        "every board client's cache must be cleared, not just the primary's"
    )
    assert fake.passes == 1


def test_force_refresh_reports_when_nothing_was_sent(mcp, services, two_boards, monkeypatch):
    monkeypatch.setattr("src.display_runtime.get_service", lambda: _FakeRefreshEngine(sent=False))

    result = assert_ok(call(mcp, "force_refresh"), "force_refresh")

    assert result["sent"] is False


def test_force_refresh_surfaces_a_send_failure_as_an_error(mcp, services, two_boards, monkeypatch):
    monkeypatch.setattr(
        "src.display_runtime.get_service", lambda: _FakeRefreshEngine(sent=False, error="board offline")
    )

    message = call_expect_error(mcp, "force_refresh")

    assert "board offline" in message


def test_force_refresh_without_a_display_service_is_an_error(mcp, services, two_boards, monkeypatch):
    monkeypatch.setattr("src.display_runtime.get_service", lambda: None)

    message = call_expect_error(mcp, "force_refresh")

    assert "not initialized" in message


# -- get_silence_status ------------------------------------------------------------


def test_get_silence_status_reads_the_window_update_setting_wrote(mcp, services, two_boards):
    before = assert_ok(call(mcp, "get_silence_status"), "get_silence_status")
    assert before["enabled"] is False and before["active"] is False
    assert before["board_id"] == "board-main", "omitted board_id must resolve to the primary board"

    assert_ok(
        call(
            mcp,
            "update_setting",
            category="silence_schedule",
            values={
                "enabled": True,
                "start_time": "22:00+00:00",
                "end_time": "07:00+00:00",
                "board_id": "board-note",
            },
        ),
        "update_setting",
    )

    note = assert_ok(call(mcp, "get_silence_status", board_id="board-note"), "get_silence_status")
    assert note["enabled"] is True
    assert note["board_id"] == "board-note"
    assert (note["start_time_utc"], note["end_time_utc"]) == ("22:00+00:00", "07:00+00:00")
    assert note["mode"] == "freeze"
    assert isinstance(note["seconds_until_next_change"], int)
    primary = assert_ok(call(mcp, "get_silence_status"), "get_silence_status")
    assert primary["enabled"] is False, "a per-board window must not leak onto the primary board"


# -- pause_board / resume_board -------------------------------------------------------


def test_pause_board_persists_and_blocks_sends_until_resumed(mcp, services, engine, two_boards):
    result = assert_ok(call(mcp, "pause_board", board_id="board-note"), "pause_board")

    assert result["paused"] is True and result["board_id"] == "board-note"
    assert two_boards.is_paused(board_id="board-note") is True
    assert two_boards.is_paused(board_id="board-main") is False, "pausing one board must not pause another"
    blocked = call(mcp, "send_message", text="HI", board_id="board-note")
    assert blocked.get("status") == "blocked" and blocked.get("paused") is True
    assert engine.runtimes["board-note"].client.rendered == []

    resumed = assert_ok(call(mcp, "resume_board", board_id="board-note"), "resume_board")

    assert resumed["paused"] is False
    assert two_boards.is_paused(board_id="board-note") is False
    assert_ok(call(mcp, "send_message", text="HI", board_id="board-note"), "send_message after resume")
    assert len(engine.runtimes["board-note"].client.rendered) == 1


def test_pause_board_without_board_id_targets_the_primary_board(mcp, services, two_boards, tmp_path):
    assert_ok(call(mcp, "pause_board"), "pause_board")

    assert two_boards.is_paused(board_id="board-main") is True
    assert two_boards.is_paused(board_id="board-note") is False
    assert _reloaded_settings(tmp_path).is_paused(board_id="board-main") is True, "not persisted to settings.json"
    boards = {b["id"]: b for b in assert_ok(call(mcp, "get_settings_summary"), "get_settings_summary")["boards"]}
    assert boards["board-main"]["paused"] is True


def test_pause_board_reports_an_unknown_board_and_pauses_nothing(mcp, services, two_boards):
    message = call_expect_error(mcp, "pause_board", board_id="no-such-board")

    assert "no-such-board" in message
    assert two_boards.is_paused(board_id="board-main") is False
    assert two_boards.is_paused(board_id="board-note") is False


def test_resume_board_reports_an_unknown_board(mcp, services, two_boards):
    message = call_expect_error(mcp, "resume_board", board_id="no-such-board")
    assert "no-such-board" in message
