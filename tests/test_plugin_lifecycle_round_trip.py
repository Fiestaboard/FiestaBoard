"""Plugin lifecycle round-trips driven through the HTTP API.

Part of #1730 Phase 0 (issue #1735). The existing plugin suite is either
registry-level (`test_plugin_instances.py`) or mocks the registry away at the
route boundary (`test_plugin_detail_plugin_type.py`), and the browser specs
stub the network. So three things nothing currently pins:

* **Fan-out isolation** — one plugin raising in ``fetch_data`` must not take
  the render down with it, and must not leak its exception text onto a board.
* **Secret masking** — reading a config back gives ``"***"``; writing that
  same document back must leave the stored credential intact. This is the
  round-trip #1743 exists to protect; the assertions below hold on today's
  code and are here so the Phase-1 rework of the config-write path cannot
  quietly regress them.
* **Instances** — configs keyed by ``INSTANCE_SEPARATOR`` are independent of
  the base plugin's, render under their own namespace, and are purged when the
  instance (or the whole plugin) goes away.

Nothing is mocked. Two stub plugins are written to disk and loaded by the real
``PluginLoader``; a real ``ConfigManager`` writes a real ``config.json``. Only
the git clone is replaced, by a copy from a local staging directory, so
install works without the network.

Data isolation (see #1762): ``PluginLoader`` with no ``external_dirs``
resolves — and *creates* — ``<repo>/data/external_plugins``, and
``ConfigManager`` defaults to ``<repo>/data/config.json``. The fixture below
has to override both by hand; there is no data-directory seam to point at
a temp path.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import src.plugins.registry as registry_module
import src.templates.engine as engine_module
from src.config_manager import ConfigManager
from src.plugins.loader import PluginLoader
from src.plugins.registry import INSTANCE_SEPARATOR, PluginRegistry

# ── stub plugins ────────────────────────────────────────────────────────────

HEALTHY = "stub_ok"
RAISING = "stub_broken"
EXTERNAL = "stub_external"

#: What the healthy stub reports. Distinctive enough to spot in board output.
HEALTHY_VALUE = "OKDATA"

#: The message the raising stub blows up with. Must never reach a board.
BOOM = "STUBBOOM"

#: A placeholder credential — never a real key.
SECRET = "test_secret_key_abcd"

#: What the API substitutes for a stored secret on the way out.
MASK = "***"


def _manifest(plugin_id: str) -> dict[str, Any]:
    return {
        "id": plugin_id,
        "name": plugin_id.replace("_", " ").title(),
        "version": "1.0.0",
        "description": "Fixture plugin for tests/test_plugin_lifecycle_round_trip.py.",
        "author": "FiestaBoard Tests",
        "icon": "puzzle",
        "category": "utility",
        "settings_schema": {
            "type": "object",
            "properties": {
                "label": {"type": "string", "title": "Label"},
                "api_key": {"type": "string", "title": "API Key", "ui:widget": "password"},
                "enabled": {"type": "boolean", "title": "Enabled", "default": False},
            },
        },
        "variables": {
            "simple": {
                "value": {"description": "A constant", "type": "string", "max_length": 12, "example": HEALTHY_VALUE},
                "key_tail": {
                    "description": "Last 4 chars of the live api_key",
                    "type": "string",
                    "max_length": 8,
                    "example": "abcd",
                },
            }
        },
    }


#: ``key_tail`` is the only HTTP-observable window onto the credential the
#: *live* plugin object is holding — which is the half of the masking contract
#: that a config.json assertion cannot see.
#:
#: Placeholders are substituted with ``str.replace``, not ``str.format``: the
#: plugin bodies are full of braces and every one of them would have to be
#: doubled.
_HEALTHY_SOURCE = """\
\"\"\"Fixture plugin: always succeeds.\"\"\"

from src.plugins.base import PluginBase, PluginResult


class HealthyStub(PluginBase):
    @property
    def plugin_id(self) -> str:
        return "__PLUGIN_ID__"

    def fetch_data(self) -> PluginResult:
        key = self.config.get("api_key") or ""
        return PluginResult(available=True, data={"value": "__HEALTHY_VALUE__", "key_tail": key[-4:]})
"""

_RAISING_SOURCE = """\
\"\"\"Fixture plugin: always raises.\"\"\"

from src.plugins.base import PluginBase, PluginResult


class RaisingStub(PluginBase):
    @property
    def plugin_id(self) -> str:
        return "__PLUGIN_ID__"

    def fetch_data(self) -> PluginResult:
        raise RuntimeError("__BOOM__")
"""


def _write_plugin(directory: Path, plugin_id: str, source: str) -> None:
    """Write a real, loadable plugin package to *directory*."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "manifest.json").write_text(json.dumps(_manifest(plugin_id)), encoding="utf-8")
    body = source.replace("__PLUGIN_ID__", plugin_id).replace("__HEALTHY_VALUE__", HEALTHY_VALUE)
    (directory / "__init__.py").write_text(body.replace("__BOOM__", BOOM), encoding="utf-8")


class _LocalRegistry(PluginRegistry):
    """A real registry whose "registry install" copies from a local directory.

    Everything after the copy is production code — the real loader imports the
    package and the real bookkeeping runs. Only the network fetch is replaced.
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


# ── fixtures ────────────────────────────────────────────────────────────────


#: Every ConfigManager ``plugin_env`` has constructed. The leak guard below
#: is scoped to these so an unrelated singleton leak elsewhere in the suite
#: (there are known ones — see #1730) cannot make this module fail.
_MANAGERS_CREATED_HERE: list[ConfigManager] = []


@pytest.fixture(autouse=True)
def _config_manager_leak_guard():
    """Fail if a previous test left ``plugin_env``'s ConfigManager installed.

    Checked at *setup*, not teardown, because the leak is not observable from
    inside the test that causes it: ``monkeypatch.undo()`` runs after every
    fixture finalizer, so a singleton it restores only becomes visible to the
    next test in the same xdist worker. That is exactly why the leak survived
    ``plugin_env``'s ``finally``.
    """
    installed = ConfigManager._instance  # type: ignore[attr-defined]
    assert installed is None or installed not in _MANAGERS_CREATED_HERE, (
        "a previous test leaked plugin_env's ConfigManager "
        f"({getattr(installed, '_config_path', '?')}); it points at a deleted "
        "temp dir and every later test in this worker inherits it"
    )
    yield


@pytest.fixture
def plugin_env(tmp_path):
    """A real registry over stub plugins, wired to the app singletons.

    Teardown order matters and is hand-rolled. The plugin routes call
    ``reset_template_engine()``, which binds ``get_plugin_registry()`` onto the
    long-lived engine singleton — so the engine is dropped *after* the registry
    is put back, or every later test in the session inherits an engine that has
    never heard of ``date_time``.
    """
    builtin_dir = tmp_path / "builtin_plugins"
    builtin_dir.mkdir()
    external_dir = tmp_path / "external_plugins"
    external_dir.mkdir()
    staging_dir = tmp_path / "staged_plugins"

    _write_plugin(builtin_dir / HEALTHY, HEALTHY, _HEALTHY_SOURCE)
    _write_plugin(builtin_dir / RAISING, RAISING, _RAISING_SOURCE)
    _write_plugin(staging_dir / EXTERNAL, EXTERNAL, _HEALTHY_SOURCE)

    config_path = tmp_path / "config.json"
    ConfigManager._instance = None  # type: ignore[attr-defined]
    # Constructing it installs it: ``ConfigManager.__new__`` assigns
    # ``cls._instance``. Do NOT also pin it with ``monkeypatch.setattr`` —
    # ``monkeypatch.undo()`` runs after every fixture finalizer in this test,
    # so it would restore this temp-dir instance *after* the ``finally`` below
    # cleared it, handing every later test in this xdist worker a
    # ConfigManager pointing at a deleted ``tmp_path/config.json``. See
    # ``test_monkeypatching_the_config_manager_singleton_outlives_a_fixture``.
    config_manager = ConfigManager(config_path=str(config_path))
    _MANAGERS_CREATED_HERE.append(config_manager)

    original_registry = registry_module._registry
    original_engine = engine_module._template_engine

    registry = _LocalRegistry(builtin_dir, external_dir, staging_dir)
    registry.initialize()
    registry_module._registry = registry
    engine_module._template_engine = None

    try:
        yield {
            "registry": registry,
            "config_path": config_path,
            "external_dir": external_dir,
        }
    finally:
        registry_module._registry = original_registry
        engine_module._template_engine = original_engine
        ConfigManager._instance = None  # type: ignore[attr-defined]


@pytest.fixture
def client(plugin_env):
    from src.api_server import app

    return TestClient(app)


# ── helpers ─────────────────────────────────────────────────────────────────


def _stored_config(config_path: Path, plugin_id: str) -> dict[str, Any] | None:
    """Read a plugin's config straight out of ``config.json``.

    Deliberately bypasses ConfigManager: the in-memory copy looking right
    while the file holds the mask is exactly the failure mode under test.
    """
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    return raw.get("plugins", {}).get(plugin_id)


def _enable(client: TestClient, plugin_id: str) -> None:
    response = client.post(f"/plugins/{plugin_id}/enable")
    assert response.status_code == 200, response.text


def _put_config(client: TestClient, plugin_id: str, config: dict[str, Any]) -> dict[str, Any]:
    response = client.put(f"/plugins/{plugin_id}/config", json={"config": config})
    assert response.status_code == 200, response.text
    return response.json()


def _render(client: TestClient, line: str) -> str:
    response = client.post("/templates/render", json={"template": [line, "", "", "", "", ""]})
    assert response.status_code == 200, response.text
    return response.json()["rendered"]


def _plugin_entry(client: TestClient, plugin_id: str) -> dict[str, Any]:
    response = client.get("/plugins")
    assert response.status_code == 200, response.text
    for entry in response.json()["plugins"]:
        if entry["id"] == plugin_id:
            return entry
    raise AssertionError(f"{plugin_id} is missing from GET /plugins")


# ── fan-out isolation ───────────────────────────────────────────────────────


def test_a_raising_plugin_does_not_block_a_healthy_plugins_variable(client):
    """One plugin exploding must not cost the others their data."""
    _enable(client, HEALTHY)
    _enable(client, RAISING)

    rendered = _render(client, f"{{{{{HEALTHY}.value}}}}")

    assert HEALTHY_VALUE in rendered


def test_a_raising_plugins_error_text_never_reaches_the_board(client):
    """An exception message is not board content."""
    _enable(client, HEALTHY)
    _enable(client, RAISING)

    rendered = _render(client, f"{{{{{RAISING}.value}}}}")

    assert BOOM not in rendered


def test_a_raising_plugin_is_reported_unavailable_on_its_own_data_endpoint(client):
    """The failure is surfaced where it belongs, not silently reported OK."""
    _enable(client, RAISING)

    response = client.get(f"/plugins/{RAISING}/data")

    assert response.status_code == 503, response.text


def test_a_healthy_plugin_still_serves_its_own_data_endpoint_alongside_a_raising_one(client):
    """A sibling's failure must not be mistaken for this plugin's own."""
    _enable(client, HEALTHY)
    _enable(client, RAISING)

    response = client.get(f"/plugins/{HEALTHY}/data")

    assert response.status_code == 200, response.text
    assert response.json()["data"]["value"] == HEALTHY_VALUE


# ── secret masking round-trip ───────────────────────────────────────────────


def test_a_stored_api_key_is_masked_when_the_plugin_list_is_read_back(client):
    """The browser must never hold the real credential."""
    _put_config(client, HEALTHY, {"label": "primary", "api_key": SECRET})

    assert _plugin_entry(client, HEALTHY)["config"]["api_key"] == MASK


def test_a_stored_api_key_is_masked_on_the_plugin_detail_endpoint(client):
    """The single-plugin route masks too — not just the list."""
    _put_config(client, HEALTHY, {"label": "primary", "api_key": SECRET})

    response = client.get(f"/plugins/{HEALTHY}")

    assert response.status_code == 200, response.text
    assert response.json()["config"]["api_key"] == MASK


def test_writing_the_masked_api_key_back_preserves_the_stored_secret(client, plugin_env):
    """The #1743 contract: a form re-save must not destroy the credential."""
    _put_config(client, HEALTHY, {"label": "primary", "api_key": SECRET})

    _put_config(client, HEALTHY, {"label": "renamed", "api_key": MASK})

    stored = _stored_config(plugin_env["config_path"], HEALTHY)
    assert stored is not None
    assert stored["api_key"] == SECRET
    assert stored["label"] == "renamed", "the non-secret edit was dropped"


def test_writing_the_masked_api_key_back_leaves_the_live_plugin_using_the_real_secret(client):
    """Persisting the key is not enough — the running plugin needs it too."""
    _enable(client, HEALTHY)
    _put_config(client, HEALTHY, {"label": "primary", "api_key": SECRET})

    _put_config(client, HEALTHY, {"label": "renamed", "api_key": MASK})

    assert SECRET[-4:] in _render(client, f"{{{{{HEALTHY}.key_tail}}}}")


def test_writing_a_new_api_key_replaces_the_stored_secret(client, plugin_env):
    """Preserving masked values must not also freeze real ones."""
    _put_config(client, HEALTHY, {"label": "primary", "api_key": SECRET})

    _put_config(client, HEALTHY, {"label": "primary", "api_key": "test_rotated_key_wxyz"})

    assert _stored_config(plugin_env["config_path"], HEALTHY)["api_key"] == "test_rotated_key_wxyz"


def test_writing_the_masked_api_key_back_over_mcp_preserves_the_stored_secret(client, plugin_env):
    """The MCP tool round-trips the masked config it just handed the model."""
    pytest.importorskip("mcp", reason="mcp package not installed")

    from src.mcp_server import _build_mcp_server

    _put_config(client, HEALTHY, {"label": "primary", "api_key": SECRET})

    mcp = _build_mcp_server()
    assert mcp is not None, "mcp installed but _build_mcp_server() returned None"
    tool = mcp._tool_manager._tools["configure_plugin"]
    result = tool.fn(plugin_id=HEALTHY, config={"label": "renamed", "api_key": MASK})
    if asyncio.iscoroutine(result):
        result = asyncio.run(result)
    assert not result.get("error"), result

    assert _stored_config(plugin_env["config_path"], HEALTHY)["api_key"] == SECRET


# ── instances ───────────────────────────────────────────────────────────────


def test_creating_an_instance_registers_it_under_the_compound_key(client):
    """The instance is addressable as ``<base><SEPARATOR><label>``."""
    created = client.post(f"/plugins/{HEALTHY}/instances", json={"label": "sf"})
    assert created.status_code == 200, created.text

    listed = client.get(f"/plugins/{HEALTHY}/instances")
    assert listed.status_code == 200, listed.text
    assert [i["key"] for i in listed.json()["instances"]] == [f"{HEALTHY}{INSTANCE_SEPARATOR}sf"]


def test_an_instance_config_is_independent_of_the_base_plugin_config(client, plugin_env):
    """Configuring one must not overwrite the other."""
    instance = f"{HEALTHY}{INSTANCE_SEPARATOR}sf"
    assert client.post(f"/plugins/{HEALTHY}/instances", json={"label": "sf"}).status_code == 200

    _put_config(client, HEALTHY, {"label": "base"})
    _put_config(client, instance, {"label": "san francisco"})

    assert _stored_config(plugin_env["config_path"], HEALTHY)["label"] == "base"
    assert _stored_config(plugin_env["config_path"], instance)["label"] == "san francisco"


def test_an_instance_secret_is_masked_independently_of_the_base(client):
    """Masking follows the compound key, not the base id."""
    instance = f"{HEALTHY}{INSTANCE_SEPARATOR}sf"
    assert client.post(f"/plugins/{HEALTHY}/instances", json={"label": "sf"}).status_code == 200
    _put_config(client, instance, {"api_key": SECRET})

    response = client.get(f"/plugins/{instance}")

    assert response.status_code == 200, response.text
    assert response.json()["config"]["api_key"] == MASK


def test_an_instance_renders_under_its_own_template_namespace(client):
    """``{{base:label.var}}`` resolves to the instance's own data."""
    instance = f"{HEALTHY}{INSTANCE_SEPARATOR}sf"
    assert client.post(f"/plugins/{HEALTHY}/instances", json={"label": "sf"}).status_code == 200
    _put_config(client, instance, {"api_key": SECRET})
    _enable(client, instance)

    assert SECRET[-4:] in _render(client, f"{{{{{instance}.key_tail}}}}")


def test_deleting_an_instance_purges_its_stored_config(client, plugin_env):
    """A deleted instance must not leave configuration behind to be adopted."""
    instance = f"{HEALTHY}{INSTANCE_SEPARATOR}sf"
    assert client.post(f"/plugins/{HEALTHY}/instances", json={"label": "sf"}).status_code == 200
    _put_config(client, instance, {"api_key": SECRET})

    deleted = client.delete(f"/plugins/{HEALTHY}/instances/sf")
    assert deleted.status_code == 200, deleted.text

    assert _stored_config(plugin_env["config_path"], instance) is None


def test_deleting_an_instance_leaves_the_base_plugin_config_alone(client, plugin_env):
    """Prefix-based purging must not swallow the base plugin's own entry."""
    assert client.post(f"/plugins/{HEALTHY}/instances", json={"label": "sf"}).status_code == 200
    _put_config(client, HEALTHY, {"label": "base"})

    assert client.delete(f"/plugins/{HEALTHY}/instances/sf").status_code == 200

    assert _stored_config(plugin_env["config_path"], HEALTHY)["label"] == "base"


# ── install → configure → uninstall ─────────────────────────────────────────


def test_installing_from_the_registry_makes_the_plugin_configurable(client, plugin_env):
    """The freshly installed plugin accepts and stores a config."""
    installed = client.post(f"/plugins/registry/{EXTERNAL}/install")
    assert installed.status_code == 200, installed.text

    _put_config(client, EXTERNAL, {"label": "fresh", "api_key": SECRET})

    assert _stored_config(plugin_env["config_path"], EXTERNAL)["api_key"] == SECRET


def test_uninstalling_removes_the_plugin_from_the_listing(client):
    assert client.post(f"/plugins/registry/{EXTERNAL}/install").status_code == 200

    uninstalled = client.delete(f"/plugins/{EXTERNAL}/uninstall")
    assert uninstalled.status_code == 200, uninstalled.text

    assert client.get(f"/plugins/{EXTERNAL}").status_code == 404


def test_uninstalling_purges_the_plugin_config(client, plugin_env):
    """#948/#1102: a stale config resurrects the plugin on the next upgrade."""
    assert client.post(f"/plugins/registry/{EXTERNAL}/install").status_code == 200
    _put_config(client, EXTERNAL, {"label": "fresh", "api_key": SECRET})

    assert client.delete(f"/plugins/{EXTERNAL}/uninstall").status_code == 200

    assert _stored_config(plugin_env["config_path"], EXTERNAL) is None


def test_uninstalling_purges_the_configs_of_its_instances_too(client, plugin_env):
    """Instance keys are separate config entries and must go with the base."""
    instance = f"{EXTERNAL}{INSTANCE_SEPARATOR}sf"
    assert client.post(f"/plugins/registry/{EXTERNAL}/install").status_code == 200
    assert client.post(f"/plugins/{EXTERNAL}/instances", json={"label": "sf"}).status_code == 200
    _put_config(client, instance, {"api_key": SECRET})

    assert client.delete(f"/plugins/{EXTERNAL}/uninstall").status_code == 200

    assert _stored_config(plugin_env["config_path"], instance) is None


def test_uninstalling_removes_the_plugin_directory_from_disk(client, plugin_env):
    assert client.post(f"/plugins/registry/{EXTERNAL}/install").status_code == 200
    assert (plugin_env["external_dir"] / EXTERNAL).is_dir()

    assert client.delete(f"/plugins/{EXTERNAL}/uninstall").status_code == 200

    assert not (plugin_env["external_dir"] / EXTERNAL).exists()


def test_uninstalling_a_builtin_plugin_is_refused(client, plugin_env):
    """Refusal must also leave the config untouched."""
    _put_config(client, HEALTHY, {"label": "base"})

    refused = client.delete(f"/plugins/{HEALTHY}/uninstall")

    assert refused.status_code == 400
    assert _stored_config(plugin_env["config_path"], HEALTHY)["label"] == "base"


# ── isolation guard ─────────────────────────────────────────────────────────


def test_the_fixture_keeps_plugin_writes_out_of_the_repo_data_dir(client, plugin_env):
    """Guard for #1762: no stub plugin may land in the developer's data/."""
    repo_data = Path(__file__).resolve().parent.parent / "data"
    assert client.post(f"/plugins/registry/{EXTERNAL}/install").status_code == 200
    _put_config(client, HEALTHY, {"label": "base", "api_key": SECRET})

    assert (plugin_env["external_dir"] / EXTERNAL).is_dir(), "the fixture never redirected the external dir"
    assert plugin_env["config_path"].exists(), "the fixture never redirected config.json"
    assert not (repo_data / "external_plugins" / EXTERNAL).exists()
    if (repo_data / "config.json").exists():
        assert HEALTHY not in json.loads((repo_data / "config.json").read_text()).get("plugins", {})


def test_monkeypatching_the_config_manager_singleton_outlives_a_fixture(tmp_path):
    """``monkeypatch.undo()`` runs after a fixture's own teardown, not before.

    Deterministic reproduction of the hazard ``plugin_env`` used to have: it
    both constructed the temp ConfigManager (which installs it) *and* pinned it
    with ``monkeypatch.setattr``. The undo restored the pinned value after the
    ``finally`` had cleared it, so the temp-dir singleton escaped the fixture.
    ``_config_manager_leak_guard`` above catches a live regression; this pins
    the mechanism so the comment in ``plugin_env`` cannot rot into folklore.
    """
    from _pytest.monkeypatch import MonkeyPatch

    original = ConfigManager._instance  # type: ignore[attr-defined]
    monkeypatch = MonkeyPatch()
    try:
        ConfigManager._instance = None  # type: ignore[attr-defined]
        temp_manager = ConfigManager(config_path=str(tmp_path / "config.json"))
        monkeypatch.setattr("src.config_manager.ConfigManager._instance", temp_manager, raising=False)

        ConfigManager._instance = None  # type: ignore[attr-defined]  # the fixture's own teardown
        monkeypatch.undo()  # ...which pytest runs afterwards, not before

        assert ConfigManager._instance is temp_manager, (
            "monkeypatch.undo() no longer resurrects the value — if pytest changed "
            "this ordering, plugin_env's hand-rolled teardown can be simplified"
        )
    finally:
        monkeypatch.undo()
        ConfigManager._instance = original  # type: ignore[attr-defined]
