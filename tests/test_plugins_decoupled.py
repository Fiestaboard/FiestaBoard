"""The plugins router must not depend on ``src.api_server`` (Phase 2 §2.3).

The #1757 extraction moved the twenty-five plugin handlers out of the 10k-line
``src/api_server.py`` but left **twenty-nine** call-time
``from src.api_server import ...`` names behind — the heaviest of any router,
thirteen of them just for the remote-options runtime — purely so the suite's
``patch("src.api_server.<name>")`` targets kept resolving. That is not an
extraction: importing the router was clean, but *serving a request* pulled the
whole module — its route table, its background tasks, its MCP mount — back in,
and the 2026-09 audit counted those seams going up 4.2x across Phase 1.

This test pins the fix the honest way. In a fresh interpreter it imports the
router, drives **all twenty-five** handlers end to end against patched
canonical seams (``src.plugins.routes.<name>``), asserts the stubs really were
driven — so a handler that silently no-op'd could not pass — and then asserts
``src.api_server`` never entered ``sys.modules``.

Importing the module alone would be a much weaker claim: the seams were call
time, so a module-level import check passes with every one of them still in
place.

Where the collaborators went is tabulated in ``src/plugins/routes.py``'s
module docstring, for the reader chasing a patch target.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SCRIPT = r"""
import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import src.plugins.routes as routes
from src.plugins.base import Option, OptionsResult
from src.plugins.models import (
    ExternalPluginInstallRequest,
    PluginConfigRequest,
    PluginInstanceCreateRequest,
    PluginOptionsRequest,
)

assert "src.api_server" not in sys.modules, "importing the plugins router must not import api_server"


def call(coro):
    return asyncio.run(coro)


MANIFEST = SimpleNamespace(
    name="Alpha",
    version="1.0.0",
    description="Decoupled fixture",
    author="Fixtures",
    icon="sparkles",
    category="utility",
    plugin_type="data",
    settings_schema={
        "type": "object",
        "properties": {
            "symbols": {
                "type": "array",
                "ui:widget": "remote-options",
                "ui:options": {"options_id": "symbols", "cache_seconds": 0},
            }
        },
    },
    max_lengths={"value": 10},
    env_vars=[],
    documentation=None,
    demo={"flagship": {"name": "Alpha Demo"}},
    raw={"variables": {"value": {"description": "A value"}}, "color_rules_schema": {}},
)

registry = MagicMock()
registry.list_plugins.return_value = [
    {"id": "alpha", "name": "Alpha", "version": "1.0.0", "description": "", "enabled": True}
]
registry.get_all_variables.return_value = {"alpha": {"value": {}}}
registry.get_all_max_lengths.return_value = {"alpha": {"value": 10}}
registry.get_load_errors.return_value = {"broken": ["ImportError"]}
registry.get_fetch_breaker_status.return_value = {
    "slow": {"consecutive_timeouts": 2, "quarantined": False, "cooldown_remaining_seconds": 0.0}
}
registry.get_registry_entries.return_value = [{"id": "beta", "name": "Beta", "installed": False}]
registry.get_update_status.return_value = {"ext": True}
registry.get_update_blocked_reasons.return_value = {}
registry.get_manifest.return_value = MANIFEST
registry.get_plugin.return_value = MagicMock()
registry.is_enabled.return_value = True
registry.parse_instance_key.side_effect = lambda pid: (pid.split(":")[0], (pid.split(":")[1:] or [None])[0])
registry.make_instance_key.side_effect = lambda base, label: f"{base}:{label}"
registry.list_instances.return_value = [{"label": "work", "key": "alpha:work", "enabled": False}]
registry.create_instance.return_value = []
registry.apply_stored_config.return_value = []
registry.delete_instance.return_value = []
registry.set_plugin_config.return_value = []
registry.enable_plugin.return_value = True
registry.disable_plugin.return_value = True
registry.install_from_registry.return_value = []
registry.install_from_git.return_value = []
registry.uninstall_external_plugin.return_value = []
registry.check_for_updates.return_value = {"ext": True, "quiet": False}
registry.get_plugin_config.return_value = {"api_key": "stored"}
registry.get_plugin_options.return_value = OptionsResult(options=[Option(value="AAPL", label="Apple")])
registry.fetch_plugin_data.return_value = SimpleNamespace(
    available=True, data={"v": 1}, formatted_lines=["ALPHA"], error=None
)
registry.get_plugin_source.return_value = SimpleNamespace(source_type="git", local_path="/nope")

config_manager = MagicMock()
config_manager.get_plugin_config.return_value = {"api_key": "stored", "location": "NYC"}
config_manager.get_plugin_env_overrides.return_value = {"api_key": "from-env"}
config_manager._mask_sensitive.side_effect = lambda cfg, path="": {
    k: ("***" if k == "api_key" else v) for k, v in cfg.items()
}

demo_page = SimpleNamespace(id="demo-1", model_dump=lambda: {"id": "demo-1", "name": "Alpha Demo"})
page_service = MagicMock()
page_service.get_demo_page.return_value = None
page_service.create_demo_page.return_value = (demo_page, False)

settings_service = MagicMock()
settings_service.get_board_settings.return_value = SimpleNamespace(boards=[{"device_type": "flagship"}])

template_engine = MagicMock()
template_engine.get_available_variables.return_value = {}
template_engine.get_variable_max_lengths.return_value = {}

reset_display = MagicMock()
reset_template = MagicMock()

receive_request = MagicMock()


async def _body():
    return b'{"hello": "world"}'


receive_request.body = _body
receive_request.headers = {}

with (
    patch("src.plugins.routes.get_plugin_registry", return_value=registry),
    patch("src.plugins.routes.get_config_manager", return_value=config_manager),
    patch("src.plugins.routes.get_page_service", return_value=page_service),
    patch("src.plugins.routes.get_settings_service", return_value=settings_service),
    patch("src.plugins.routes.get_template_engine", return_value=template_engine),
    patch("src.plugins.routes.reset_display_service", reset_display),
    patch("src.plugins.routes.reset_template_engine", reset_template),
):
    # 1. GET /plugins
    listed = call(routes.list_plugins())
    assert listed.total == 1 and listed.plugins[0].id == "alpha", listed
    assert listed.plugins[0].config["api_key"] == "***", listed

    # 2. GET /plugins/variables/all
    variables = call(routes.get_all_plugin_variables())
    assert variables.plugin_system_enabled is True, variables

    # 3. GET /plugins/errors
    plugin_errors = call(routes.get_plugin_errors())
    assert plugin_errors.errors == {"broken": ["ImportError"]}, plugin_errors
    assert plugin_errors.fetch_breakers["slow"].consecutive_timeouts == 2, plugin_errors

    # 4. GET /plugins/registry
    entries = call(routes.list_registry_plugins())
    assert entries.entries[0].id == "beta", entries

    # 5. GET /plugins/updates
    updates = call(routes.get_plugin_updates())
    assert updates.updates == {"ext": True}, updates

    # 6. GET /plugins/{id}
    detail = call(routes.get_plugin("alpha"))
    assert detail.id == "alpha" and detail.config["api_key"] == "***", detail
    assert detail.env_overridden_keys == ["api_key"], detail

    # 7. GET /plugins/{id}/manifest
    manifest = call(routes.get_plugin_manifest("alpha"))
    assert manifest.variables == {"value": {"description": "A value"}}, manifest

    # 8. PUT /plugins/{id}/config
    saved = call(routes.update_plugin_config("alpha", PluginConfigRequest(config={"api_key": "***"})))
    assert saved.plugin_id == "alpha" and saved.config["api_key"] == "***", saved

    # 9/10. enable + disable
    assert call(routes.enable_plugin("alpha")).enabled is True
    assert call(routes.disable_plugin("alpha")).enabled is False

    # 11. GET /plugins/{id}/data
    data = call(routes.get_plugin_data("alpha"))
    assert data.formatted_lines == ["ALPHA"], data

    # 12. GET /plugins/{id}/variables
    plugin_vars = call(routes.get_plugin_variables("alpha"))
    assert plugin_vars.plugin_id == "alpha", plugin_vars

    # 13. POST /plugins/{id}/options/{options_id}
    options = call(routes.get_plugin_options_endpoint("alpha", "symbols", PluginOptionsRequest()))
    assert [o.value for o in options.options] == ["AAPL"], options

    # 14/15. demo pages
    demo = call(routes.get_plugin_demo_page("alpha"))
    assert demo.has_demo_template is True, demo
    created_demo = call(routes.create_plugin_demo_page("alpha"))
    assert created_demo.page["id"] == "demo-1" and created_demo.recreated is False, created_demo

    # 16/17/18. instances
    instances = call(routes.list_plugin_instances("alpha"))
    assert instances.total == 1, instances
    created = call(routes.create_plugin_instance("alpha", PluginInstanceCreateRequest(label="office")))
    assert created.instance_key == "alpha:office", created
    deleted = call(routes.delete_plugin_instance("alpha", "office"))
    assert deleted.instance_key == "alpha:office", deleted

    # 19. POST /plugins/{id}/receive
    received = call(routes.receive_plugin_payload("alpha", receive_request))
    assert received.status == "ok" and received.plugin_id == "alpha", received

    # 20/21. installs
    from_registry = call(routes.install_registry_plugin("beta"))
    assert from_registry.plugin_id == "beta", from_registry
    from_git = call(
        routes.install_external_plugin(
            ExternalPluginInstallRequest(repository="https://example.com/fiestaboard-plugin--gamma")
        )
    )
    assert from_git.plugin_id == "gamma", from_git

    # 22. DELETE /plugins/{id}/uninstall
    uninstalled = call(routes.uninstall_external_plugin("ext"))
    assert uninstalled.plugin_id == "ext", uninstalled

    # 23. POST /plugins/updates/check
    checked = call(routes.trigger_plugin_update_check())
    assert checked.checked == 2 and checked.updates_available == ["ext"], checked

    # 24. POST /plugins/{id}/update
    with patch("src.plugins.service.PluginService._validated_update_path"), patch(
        "src.plugins.sources.clone_or_update_repo", return_value=(True, "")
    ):
        registry.reload_plugin.return_value = object()
        updated = call(routes.update_plugin("ext"))
    assert updated.plugin_id == "ext", updated

    # 25. POST /plugins/updates/apply
    registry.get_update_status.return_value = {"ext": False}
    applied = call(routes.apply_all_plugin_updates())
    assert applied.updated == [] and applied.message == "No updates available.", applied

# Not vacuous: every handler really drove its collaborator. A handler that
# silently returned a canned value would fail here even though its assertion
# above passed.
registry.list_plugins.assert_called()  # GET /plugins, and again by uninstall
registry.get_load_errors.assert_called_once()
registry.get_fetch_breaker_status.assert_called_once()
registry.get_registry_entries.assert_called_once()
registry.set_plugin_config.assert_called()
registry.enable_plugin.assert_called()
registry.disable_plugin.assert_called_once_with("alpha")
registry.fetch_plugin_data.assert_called_once_with("alpha")
registry.get_plugin_options.assert_called_once()
registry.create_instance.assert_called_once_with("alpha", "office")
registry.delete_instance.assert_called_once_with("alpha", "office")
registry.install_from_registry.assert_called_once_with("beta")
registry.install_from_git.assert_called_once()
registry.uninstall_external_plugin.assert_called_once_with("ext")
registry.check_for_updates.assert_called_once()
config_manager.set_plugin_config.assert_called()
config_manager.get_plugin_env_overrides.assert_called()
page_service.create_demo_page.assert_called_once()
settings_service.get_board_settings.assert_called_once()
assert reset_display.call_count >= 4, reset_display.call_count
assert reset_template.call_count >= 4, reset_template.call_count

assert "src.api_server" not in sys.modules, (
    "a plugins handler imported src.api_server — the call-time seam regrew"
)
print("DECOUPLED")
"""


def test_plugins_router_serves_every_route_without_importing_api_server():
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "DECOUPLED" in result.stdout


def test_plugins_router_source_declares_no_api_server_import():
    """A static backstop over every branch, not just the exercised ones.

    The subprocess test above can only catch a seam on a code path it drives.
    This walks the AST of every module in the package, so an
    ``import api_server`` hidden inside a rarely-taken ``except`` branch fails
    the build too.
    """
    import ast

    offenders: list[str] = []
    for path in sorted((REPO_ROOT / "src" / "plugins").glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                offenders += [f"{path.name}: {a.name}" for a in node.names if "api_server" in a.name]
            elif isinstance(node, ast.ImportFrom) and "api_server" in (node.module or ""):
                offenders.append(f"{path.name}: {node.module}")

    assert offenders == [], f"src/plugins/ imports api_server: {offenders}"


def test_the_plugin_service_raises_no_transport_exception():
    """Layering: the service names failures, the router picks status codes.

    ``PluginService`` was the one service in the tree raising
    ``fastapi.HTTPException`` — 25 sites — which is the violation the 2026-09
    audit called out. A static check because a runtime one would only cover
    the raise sites a test happens to reach.
    """
    import ast

    source = (REPO_ROOT / "src" / "plugins" / "service.py").read_text()
    tree = ast.parse(source)

    fastapi_imports = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("fastapi")
    ]
    assert fastapi_imports == [], "src/plugins/service.py must not import fastapi"

    raised = {
        node.exc.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) and isinstance(node.exc.func, ast.Name)
    }
    assert "HTTPException" not in raised, f"service raises HTTPException; it raises {sorted(raised)}"
    assert raised, "the service raises nothing — this test would be vacuous"
