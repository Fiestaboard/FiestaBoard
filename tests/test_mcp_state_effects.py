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

#: Tools with a state-effect or shape assertion in this module.
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
}

#: Tools not yet covered here, each with the reason. Not an exemption list.
UNCOVERED = {
    "list_registry_plugins": "hits the network-backed registry; needs a fixture",
    "set_active_page": "delegates to the REST handler; needs board render wiring",
    "set_schedule_mode": "routes through SettingsService; needs settings wiring",
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

    ConfigManager._instance = None  # type: ignore[attr-defined]
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

    ConfigManager._instance = None  # type: ignore[attr-defined]


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
                "station_id": {"type": "string", "title": "Station ID"},
                "api_key": {"type": "string", "title": "API Key", "ui:widget": "password"},
                "enabled": {"type": "boolean", "title": "Enabled", "default": False},
            },
            "required": ["station_id"],
        },
        "variables": {
            "simple": {
                "next_high": {
                    "description": "Time of the next high tide",
                    "type": "string",
                    "max_length": 5,
                    "example": "06:12",
                }
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
        return PluginResult(available=True, data={{"next_high": "06:12"}})
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
    result = call(mcp, "update_page", page_id=created["page_id"])
    assert isinstance(result, dict) and result.get("error"), "a no-op update should say so, not report success"


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
    before_ids = {s["id"] for s in before}

    assert_ok(
        call(mcp, "create_schedule", page_id=page_id, start_time="08:00", day_pattern="all"),
        "create_schedule",
    )

    after = assert_ok(call(mcp, "list_schedules"), "list_schedules")
    assert len(({s["id"] for s in after}) - before_ids) == 1


def test_update_schedule_changes_the_stored_start_time(mcp, services):
    page_id = _make_page(mcp)
    created = assert_ok(
        call(mcp, "create_schedule", page_id=page_id, start_time="08:00", day_pattern="all"),
        "create_schedule",
    )
    schedule_id = created["schedule_id"]

    assert_ok(call(mcp, "update_schedule", schedule_id=schedule_id, start_time="09:30"), "update_schedule")

    after = assert_ok(call(mcp, "list_schedules"), "list_schedules")
    stored = next(s for s in after if s["id"] == schedule_id)
    assert stored["start_time"] == "09:30", "update_schedule reported success but start_time did not change"


def test_delete_schedule_removes_it(mcp, services):
    page_id = _make_page(mcp)
    created = assert_ok(
        call(mcp, "create_schedule", page_id=page_id, start_time="08:00", day_pattern="all"),
        "create_schedule",
    )
    schedule_id = created["schedule_id"]

    assert_ok(call(mcp, "delete_schedule", schedule_id=schedule_id), "delete_schedule")

    after = assert_ok(call(mcp, "list_schedules"), "list_schedules")
    assert schedule_id not in {s["id"] for s in after}


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
    result = call(mcp, "configure_plugin", plugin_id=PLUGIN_ID, config={"station_id": ""})

    assert result.get("status") == "error", "an invalid config was reported as a successful update"
    assert "station_id" in str(result.get("error", "")), (
        f"the plugin's own validation message was not surfaced: {result}"
    )


def test_configure_plugin_does_not_overwrite_a_good_config_with_a_rejected_one(mcp, plugins):
    assert_ok(
        call(mcp, "configure_plugin", plugin_id=PLUGIN_ID, config={"station_id": "9447427"}),
        "configure_plugin",
    )

    call(mcp, "configure_plugin", plugin_id=PLUGIN_ID, config={"station_id": ""})

    stored = stored_plugin_config(plugins["config_path"], PLUGIN_ID)
    assert stored["station_id"] == "9447427", "a rejected config was persisted over a valid one"


def test_configure_plugin_reports_an_error_for_an_unknown_plugin(mcp, plugins):
    result = call(mcp, "configure_plugin", plugin_id="not_a_plugin", config={"station_id": "1"})
    assert result.get("status") == "error"
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
    result = call(mcp, "enable_plugin", plugin_id="not_a_plugin")
    assert result.get("status") == "error", "enabling a plugin that does not exist reported success"


def test_disable_plugin_reports_an_error_for_an_unknown_plugin(mcp, plugins):
    result = call(mcp, "disable_plugin", plugin_id="not_a_plugin")
    assert result.get("status") == "error", "disabling a plugin that does not exist reported success"


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
    result = call(mcp, "delete_schedule", schedule_id="no-such-schedule")
    assert result.get("status") == "error", f"deleting a schedule that does not exist reported success: {result}"


def test_delete_collection_reports_an_error_for_an_unknown_id(mcp, services):
    result = call(mcp, "delete_collection", collection_id="no-such-collection")
    assert result.get("status") == "error", f"deleting a collection that does not exist reported success: {result}"


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
    result = call(mcp, "update_plugin", plugin_id=BUILTIN_PLUGIN_ID)

    assert result.get("status") == "error", f"a built-in plugin was reported as updated: {result}"
    assert "built-in" in str(result.get("error", "")).lower(), (
        f"the rejection did not say why a built-in cannot be updated: {result}"
    )


def test_update_plugin_refuses_a_plugin_that_is_not_a_git_checkout(mcp, updatable_plugins):
    """``harness_tide`` was copied into place, not cloned — there is no remote.

    Without the REST path's ``.git`` check the tool reports success for a
    directory it has no way to update.
    """
    result = call(mcp, "update_plugin", plugin_id=PLUGIN_ID)

    assert result.get("status") == "error", f"a plugin with no git checkout was reported as updated: {result}"
    assert "git" in str(result.get("error", "")).lower(), (
        f"the rejection did not name the missing git checkout: {result}"
    )


def test_update_plugin_reports_an_error_for_an_unknown_plugin(mcp, updatable_plugins):
    result = call(mcp, "update_plugin", plugin_id="not_a_plugin")
    assert result.get("status") == "error", f"updating a plugin that does not exist reported success: {result}"
