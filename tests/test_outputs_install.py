"""Choosing an output before it is installed (plan D18).

The setup wizard's first step lists every output the user can pick — even
one not installed yet — and installs the chosen one. Pinned here:

- **listing** ``GET /outputs/available``: the installed outputs (built-ins
  first), then the seed's loadable first-party outputs, then registry
  entries whose ``plugin_type`` is ``output``; never the same id twice, never
  a data-only seed entry or a data plugin; an unreadable registry leaves the
  installed and seeded ones;
- **install** ``POST /outputs/{output_id}/install``: from the seed with no
  network at all, from the registry through the normal install path (so the
  ``output_api`` gate refuses a plugin this core cannot run), idempotent
  (200 with the same entry once installed), refused while the output plugins
  beta is off, 404 for an id nothing offers, 503 when the registry's
  repository cannot be fetched.

Tests never reach the network: a registry "clone" copies the fixture plugin.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.outputs.registry import output_registry
from src.outputs.seed import LOCKFILE, build_seed, tree_digest
from src.plugins import sources
from src.plugins.loader import PluginLoader
from src.plugins.sources import RegistryEntry

FIXTURE = Path(__file__).parent / "fixtures" / "plugins" / "recording_output"
PLUGIN_ID = "recording_output"
REPO_URL = "https://github.com/Fiestaboard/fiestaboard-output--recording-output"

_GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
    "GIT_TERMINAL_PROMPT": "0",
}


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True, env={**os.environ, **_GIT_ENV}
    )
    return result.stdout.strip()


def _build_seed(tmp_path: Path, *, loadable: bool = True) -> Path:
    """A seed holding the recording output, built from a local repo."""
    repo = tmp_path / "origin" / "fiestaboard-output--recording-output"
    shutil.copytree(FIXTURE, repo, ignore=shutil.ignore_patterns("__pycache__"))
    _git(repo, "init", "--quiet", "--initial-branch=main")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "initial")
    head = _git(repo, "rev-parse", "HEAD")
    lock = tmp_path / LOCKFILE
    lock.write_text(
        json.dumps(
            {
                "lock_version": 1,
                "outputs": {
                    PLUGIN_ID: {
                        "repository": REPO_URL,
                        "commit": head,
                        "output_api": 1,
                        "tree_sha256": tree_digest(repo),
                        "loadable": loadable,
                    }
                },
            }
        ),
        "utf-8",
    )
    root = tmp_path / "seed"
    build_seed(lock, root, repositories={PLUGIN_ID: repo.as_uri()})
    return root


def _registry_entry(plugin_type: str = "output", plugin_id: str = PLUGIN_ID) -> RegistryEntry:
    return RegistryEntry(
        plugin_id=plugin_id,
        name="Recording Sign",
        description="A sign from the registry.",
        repository=REPO_URL if plugin_type == "output" else "https://github.com/x/fiestaboard-plugin--weather_x",
        icon="lightbulb",
        plugin_type=plugin_type,
    )


@pytest.fixture
def plugins(tmp_path, monkeypatch):
    """A live plugin registry with nothing installed, and no seed or registry entries."""
    import src.plugins.registry as registry_module
    from src.plugins.registry import PluginRegistry

    monkeypatch.setenv("FIESTABOARD_OUTPUT_SEED_DIR", str(tmp_path / "no-seed"))
    loader = PluginLoader(plugins_dir=tmp_path / "builtin", external_dirs=[], seed_dir=tmp_path / "no-seed")
    registry = PluginRegistry(plugins_dir=tmp_path / "builtin")
    monkeypatch.setattr(registry, "_loader", loader)
    registry.initialize()
    monkeypatch.setattr(registry_module, "_registry", registry)
    set_registry([])
    yield registry
    loader.unload_plugin(PLUGIN_ID)
    output_registry().remove_plugin(PLUGIN_ID)


_REGISTRY: list[RegistryEntry] = []


def set_registry(entries: list[RegistryEntry]) -> None:
    _REGISTRY[:] = entries


@pytest.fixture(autouse=True)
def _registry_file(monkeypatch):
    """``plugin-registry.json`` as the test says it is (both readers of it)."""
    import src.plugins.registry as registry_module

    monkeypatch.setattr(sources, "load_registry", lambda *a, **k: list(_REGISTRY))
    monkeypatch.setattr(registry_module, "load_registry", lambda *a, **k: list(_REGISTRY))


@pytest.fixture
def seeded(plugins, tmp_path, monkeypatch):
    root = _build_seed(tmp_path)
    monkeypatch.setenv("FIESTABOARD_OUTPUT_SEED_DIR", str(root))
    monkeypatch.setattr(plugins._loader, "seed_dir", root)
    return root


@pytest.fixture
def no_network(monkeypatch):
    """Any git fetch fails the test: the seed install must not need one."""

    def refuse(*args, **kwargs):
        raise AssertionError("the seed install reached for the network")

    monkeypatch.setattr(sources, "clone_or_update_repo", refuse)


def fake_clone(monkeypatch, *, output_api: int = 1) -> list[str]:
    """Make a registry "clone" copy the fixture plugin; returns the URLs cloned."""
    cloned: list[str] = []

    def clone(repo_url, plugin_id, branch="", *, external_dir=None):
        cloned.append(repo_url)
        target = Path(external_dir or sources.get_external_plugins_dir()) / plugin_id
        shutil.copytree(FIXTURE, target, ignore=shutil.ignore_patterns("__pycache__"))
        manifest = json.loads((target / "manifest.json").read_text("utf-8"))
        manifest["output"]["output_api"] = output_api
        (target / "manifest.json").write_text(json.dumps(manifest), "utf-8")
        return True, ""

    monkeypatch.setattr(sources, "clone_or_update_repo", clone)
    return cloned


def beta(on: bool) -> None:
    from src.settings.service import get_settings_service

    get_settings_service().update_beta_settings({"output_plugins_enabled": on})


@pytest.fixture
def client():
    from src.api_server import app

    return TestClient(app)


def _available(client) -> list[dict]:
    resp = client.get("/outputs/available")
    assert resp.status_code == 200, resp.text
    return resp.json()


# --- the listing ------------------------------------------------------------------------------------


class TestListing:
    def test_the_installed_built_ins_come_first(self, client, plugins):
        listed = _available(client)
        assert [(o["id"], o["source"], o["installed"]) for o in listed[:2]] == [
            ("vestaboard", "installed", True),
            ("fiestapanel", "installed", True),
        ]
        assert listed[0]["builtin"] is True and listed[0]["available"] is True

    def test_a_seeded_output_is_offered_before_it_is_installed(self, client, seeded):
        entry = next(o for o in _available(client) if o["id"] == PLUGIN_ID)
        assert entry["source"] == "seed"
        assert entry["installed"] is False
        assert entry["needs_network"] is False
        # Name, description and icon come from the seed's own manifest.
        assert (entry["name"], entry["icon"]) == ("Recording Output", "monitor")
        assert entry["description"].startswith("Test-only output plugin")
        assert entry["output_api"] == 1
        assert (entry["builtin"], entry["beta_gated"]) == (False, True)

    def test_a_not_installed_output_is_unavailable_until_the_beta_is_on(self, client, seeded):
        assert next(o for o in _available(client) if o["id"] == PLUGIN_ID)["available"] is False
        beta(True)
        assert next(o for o in _available(client) if o["id"] == PLUGIN_ID)["available"] is True

    def test_a_data_only_seed_entry_is_not_offered(self, client, plugins, tmp_path, monkeypatch):
        root = _build_seed(tmp_path, loadable=False)
        monkeypatch.setenv("FIESTABOARD_OUTPUT_SEED_DIR", str(root))
        assert PLUGIN_ID not in [o["id"] for o in _available(client)]

    def test_registry_outputs_are_offered_and_data_plugins_are_not(self, client, plugins):
        set_registry([_registry_entry(), _registry_entry("data", "weather_x")])
        listed = _available(client)
        entry = next(o for o in listed if o["id"] == PLUGIN_ID)
        assert (entry["source"], entry["installed"], entry["needs_network"]) == ("registry", False, True)
        assert (entry["name"], entry["icon"]) == ("Recording Sign", "lightbulb")
        assert entry["output_api"] is None
        assert "weather_x" not in [o["id"] for o in listed]

    def test_the_seed_wins_over_the_registry_for_the_same_id(self, client, seeded):
        set_registry([_registry_entry()])
        entries = [o for o in _available(client) if o["id"] == PLUGIN_ID]
        assert [o["source"] for o in entries] == ["seed"]

    def test_an_installed_output_is_listed_once_as_installed(self, client, seeded):
        beta(True)
        assert client.post(f"/outputs/{PLUGIN_ID}/install").status_code == 201
        set_registry([_registry_entry()])
        entries = [o for o in _available(client) if o["id"] == PLUGIN_ID]
        assert [(o["source"], o["installed"]) for o in entries] == [("installed", True)]

    def test_an_unreadable_registry_still_lists_installed_and_seeded(self, client, seeded, monkeypatch):
        def broken(*args, **kwargs):
            raise OSError("registry unreachable")

        monkeypatch.setattr(sources, "load_registry", broken)
        ids = [o["id"] for o in _available(client)]
        assert ids[:2] == ["vestaboard", "fiestapanel"]
        assert PLUGIN_ID in ids


# --- install -------------------------------------------------------------------------------------------


class TestInstallFromSeed:
    def test_installs_offline_and_answers_the_output(self, client, seeded, no_network):
        beta(True)
        resp = client.post(f"/outputs/{PLUGIN_ID}/install")
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["id"] == PLUGIN_ID
        assert body["available"] is True
        assert body["device_models"], "the installed output carries its device models"
        assert (sources.get_external_plugins_dir() / PLUGIN_ID / "manifest.json").is_file()
        assert output_registry().get(PLUGIN_ID) is not None
        assert PLUGIN_ID in [o["id"] for o in client.get("/outputs").json()]

    def test_a_second_install_answers_200_with_the_same_output(self, client, seeded, no_network):
        beta(True)
        first = client.post(f"/outputs/{PLUGIN_ID}/install")
        second = client.post(f"/outputs/{PLUGIN_ID}/install")
        assert (first.status_code, second.status_code) == (201, 200)
        assert second.json() == first.json()

    def test_refused_while_the_output_plugins_beta_is_off(self, client, seeded, no_network):
        resp = client.post(f"/outputs/{PLUGIN_ID}/install")
        assert resp.status_code == 409
        assert "output plugins beta" in resp.json()["detail"]
        assert not (sources.get_external_plugins_dir() / PLUGIN_ID).exists()
        assert output_registry().get(PLUGIN_ID) is None


class TestInstallFromRegistry:
    def test_installs_through_the_normal_install_path(self, client, plugins, monkeypatch):
        set_registry([_registry_entry()])
        cloned = fake_clone(monkeypatch)
        beta(True)
        resp = client.post(f"/outputs/{PLUGIN_ID}/install")
        assert resp.status_code == 201, resp.text
        assert cloned == [REPO_URL]
        assert resp.json()["id"] == PLUGIN_ID
        assert output_registry().get(PLUGIN_ID) is not None

    def test_the_output_api_gate_refuses_a_plugin_this_core_cannot_run(self, client, plugins, monkeypatch):
        set_registry([_registry_entry()])
        fake_clone(monkeypatch, output_api=99)
        beta(True)
        resp = client.post(f"/outputs/{PLUGIN_ID}/install")
        assert resp.status_code == 400
        assert "output_api 99" in resp.json()["detail"]
        assert not (sources.get_external_plugins_dir() / PLUGIN_ID).exists()
        assert output_registry().get(PLUGIN_ID) is None

    def test_refused_while_the_beta_is_off_before_anything_is_fetched(self, client, plugins, monkeypatch):
        set_registry([_registry_entry()])
        cloned = fake_clone(monkeypatch)
        resp = client.post(f"/outputs/{PLUGIN_ID}/install")
        assert resp.status_code == 409
        assert cloned == []

    def test_an_unreachable_repository_is_a_503(self, client, plugins, monkeypatch):
        set_registry([_registry_entry()])
        monkeypatch.setattr(
            sources,
            "clone_or_update_repo",
            lambda *a, **k: (False, "git clone failed: fatal: unable to access: Could not resolve host"),
        )
        beta(True)
        resp = client.post(f"/outputs/{PLUGIN_ID}/install")
        assert resp.status_code == 503
        assert "Could not resolve host" in resp.json()["detail"]

    def test_a_data_plugin_in_the_registry_is_not_installed_here(self, client, plugins, monkeypatch):
        set_registry([_registry_entry("data", "weather_x")])
        cloned = fake_clone(monkeypatch)
        beta(True)
        assert client.post("/outputs/weather_x/install").status_code == 404
        assert cloned == []


class TestInstallOther:
    def test_an_id_nothing_offers_is_a_404(self, client, plugins):
        beta(True)
        resp = client.post("/outputs/no_such_sign/install")
        assert resp.status_code == 404
        assert "no_such_sign" in resp.json()["detail"]

    def test_a_built_in_is_already_installed(self, client, plugins):
        resp = client.post("/outputs/vestaboard/install")
        assert resp.status_code == 200
        assert resp.json()["id"] == "vestaboard"
