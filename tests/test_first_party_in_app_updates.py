"""Vestaboard and FiestaPanel update in-app, like any plugin (plan D8).

The image's seed still carries both at the commits ``outputs.lock.json``
pins, and is what boots them offline. Beside it, each first-party output now
has an **installed copy** in the external plugins directory: a checkout of
its own repository that the Integrations page updates like any plugin. What
is pinned here:

- **boot** puts an installed copy of each in place from the seed (offline),
  replaces one older than the seed's pin (an image upgrade never downgrades),
  and sets aside a copy that came from another repository;
- **load precedence** (gate 3): a valid installed copy newer than the seed's
  pin runs; the pinned copy, an older one, or none at all runs the seed; an
  installed copy that is not valid (another repository, an unsupported
  ``output_api``, does not import) is refused and the seed runs, loudly;
- **update check** (gate 1) against the output's repository: a new release
  is offered, an incoming unsupported ``output_api`` is held back;
- **update** (gate 2): a release that does not load is rolled back to the
  commit it replaced, and the boards are rebuilt on the code that runs;
- they stay first-party: never behind the beta, never a plugin entry in the
  output registry, never uninstallable, never installable from elsewhere.

Every "remote" is a local git repository: the official repository URL is
redirected to it with git's ``url.<base>.insteadOf``, so the installed copy
keeps the origin it really has. Only the remote-head probe is stubbed, as in
``test_output_seed_and_gate.py``: it refuses a non-https remote.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from src.outputs.first_party import FIRST_PARTY_OUTPUTS, dev_override_env, load_first_party
from src.outputs.registry import FIESTAPANEL, VESTABOARD, output_registry
from src.outputs.seed import LOCKFILE, checkout_origin, install_first_party_outputs, load_lock, seed_root, tree_digest
from src.plugins.loader import PluginLoader
from src.plugins.sources import get_external_plugins_dir, get_local_head_sha

ROOT = Path(__file__).resolve().parents[1]
_PREFIXES = tuple(f"plugins.{output_id}" for output_id in FIRST_PARTY_OUTPUTS)

_GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
    "GIT_TERMINAL_PROMPT": "0",
}


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True, env={**os.environ, **_GIT_ENV}
    )
    return result.stdout.strip()


def commit_all(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def pin(output_id: str = VESTABOARD):
    return load_lock(seed_root() / LOCKFILE)[output_id]


def edit_manifest(plugin_dir: Path, **changes) -> None:
    path = plugin_dir / "manifest.json"
    path.chmod(path.stat().st_mode | stat.S_IWUSR)
    manifest = json.loads(path.read_text("utf-8"))
    for key, value in changes.items():
        if key == "output_api":
            manifest["output"]["output_api"] = value
        else:
            manifest[key] = value
    path.write_text(json.dumps(manifest, indent=2), "utf-8")


def set_origin(checkout: Path, url: str) -> None:
    git(checkout, "remote", "set-url", "origin", url)


@pytest.fixture(autouse=True)
def _no_dev_override(monkeypatch):
    for output_id in FIRST_PARTY_OUTPUTS:
        monkeypatch.delenv(dev_override_env(output_id), raising=False)


@pytest.fixture(autouse=True)
def restore_first_party():
    """Put the suite's first-party modules and output registry entries back:
    tests here load other copies of them, and the rest of the suite holds
    references to (and patches) the seed's."""
    import plugins

    registry = output_registry()
    saved_modules = {name: module for name, module in sys.modules.items() if name.startswith(_PREFIXES)}
    saved_attrs = {i: vars(plugins)[i] for i in FIRST_PARTY_OUTPUTS if i in vars(plugins)}
    saved_entries = {i: registry.get(i) for i in FIRST_PARTY_OUTPUTS}
    yield
    for name in [name for name in sys.modules if name.startswith(_PREFIXES)]:
        del sys.modules[name]
    sys.modules.update(saved_modules)
    for output_id, module in saved_attrs.items():
        setattr(plugins, output_id, module)
    with registry._lock:
        for output_id, definition in saved_entries.items():
            if definition is not None:
                registry._outputs[output_id] = definition


@pytest.fixture
def external() -> Path:
    """This test's external plugins dir, the first-party copies installed."""
    path = get_external_plugins_dir()
    assert install_first_party_outputs(external_dir=path) == sorted(FIRST_PARTY_OUTPUTS)
    return path


@pytest.fixture
def origin(tmp_path, monkeypatch) -> Path:
    """The Vestaboard repository's stand-in: a local repo holding the pinned
    tree, which the official URL is redirected to."""
    repo = tmp_path / "origin" / "fiestaboard-output--vestaboard"
    shutil.copytree(seed_root() / VESTABOARD, repo, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    for path in [repo, *repo.rglob("*")]:
        path.chmod(path.stat().st_mode | stat.S_IWUSR)
    git(repo, "init", "--quiet", "--initial-branch=main")
    commit_all(repo, "the pinned tree")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", f"url.{repo.as_uri()}.insteadOf")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", pin().repository)
    # The one probe stubbed: get_remote_head_sha refuses a non-https remote,
    # and the redirect shows it the local one.
    monkeypatch.setattr("src.plugins.sources.get_remote_head_sha", lambda _dir: git(repo, "rev-parse", "HEAD"))
    return repo


def release(origin: Path, version: str, *, output_api: int = 1, init: str | None = None) -> str:
    """Publish a release of the stand-in repository; its commit sha."""
    edit_manifest(origin, version=version, output_api=output_api)
    if init is not None:
        (origin / "__init__.py").write_text(init, "utf-8")
    return commit_all(origin, f"release {version}")


def running_file(output_id: str = VESTABOARD) -> Path:
    """Where the code the output registry builds boards from was loaded."""
    module = sys.modules[output_registry().get(output_id).plugin_class.__module__]
    return Path(module.__file__).resolve()


def make_registry(tmp_path: Path, monkeypatch):
    from src.plugins.registry import PluginRegistry

    registry = PluginRegistry(plugins_dir=tmp_path / "builtin")
    loader = PluginLoader(plugins_dir=tmp_path / "builtin", external_dirs=[get_external_plugins_dir()])
    monkeypatch.setattr(registry, "_loader", loader)
    registry.initialize()
    return registry


# --- boot ---------------------------------------------------------------------------------------


class TestBoot:
    @pytest.mark.parametrize("output_id", FIRST_PARTY_OUTPUTS)
    def test_boot_installs_an_updatable_checkout_of_the_pinned_commit(self, external, output_id):
        copy = external / output_id
        assert tree_digest(copy) == pin(output_id).tree_sha256
        assert get_local_head_sha(copy) == pin(output_id).commit
        assert checkout_origin(copy) == pin(output_id).repository

    def test_a_current_copy_is_left_alone(self, external):
        (external / VESTABOARD / ".git" / "MARK").write_text("mine", "utf-8")
        assert install_first_party_outputs(external_dir=external) == []
        assert (external / VESTABOARD / ".git" / "MARK").read_text("utf-8") == "mine"

    def test_a_newer_copy_is_left_alone(self, external):
        edit_manifest(external / VESTABOARD, version="99.0.0")
        assert install_first_party_outputs(external_dir=external) == []
        assert json.loads((external / VESTABOARD / "manifest.json").read_text())["version"] == "99.0.0"

    def test_a_copy_older_than_the_seeds_pin_is_replaced_by_it(self, external):
        edit_manifest(external / VESTABOARD, version="0.0.1")
        assert install_first_party_outputs(external_dir=external) == [VESTABOARD]
        assert tree_digest(external / VESTABOARD) == pin().tree_sha256

    def test_a_copy_from_another_repository_is_set_aside_and_replaced(self, external):
        set_origin(external / VESTABOARD, "https://github.com/someone/vestaboard-fork")
        assert install_first_party_outputs(external_dir=external) == [VESTABOARD]
        assert checkout_origin(external / VESTABOARD) == pin().repository
        (aside,) = [p for p in external.iterdir() if p.name.startswith(f".{VESTABOARD}.set-aside-")]
        assert checkout_origin(aside) == "https://github.com/someone/vestaboard-fork"


# --- gate 3: load precedence ---------------------------------------------------------------------


class TestLoadPrecedence:
    def test_the_pinned_copy_runs_from_the_seed(self, external):
        loaded = load_first_party(VESTABOARD, external_dir=external)
        assert (loaded.source.origin, loaded.source.path, loaded.fallback) == ("seed", seed_root() / VESTABOARD, None)

    def test_without_an_installed_copy_the_seed_runs(self, tmp_path):
        loaded = load_first_party(VESTABOARD, external_dir=tmp_path / "empty")
        assert (loaded.source.origin, loaded.fallback) == ("seed", None)

    def test_a_newer_installed_copy_runs_instead_of_the_seed(self, external):
        edit_manifest(external / VESTABOARD, version="99.0.0")
        loaded = load_first_party(VESTABOARD, external_dir=external)
        assert (loaded.source.origin, loaded.source.path, loaded.fallback) == (
            "installed",
            external / VESTABOARD,
            None,
        )
        assert loaded.manifest.version == "99.0.0"
        assert Path(sys.modules["plugins.vestaboard"].__file__).parent == external / VESTABOARD

    def test_an_older_installed_copy_never_downgrades_the_seed(self, external):
        edit_manifest(external / VESTABOARD, version="0.0.1")
        loaded = load_first_party(VESTABOARD, external_dir=external)
        assert (loaded.source.origin, loaded.fallback) == ("seed", None)

    def test_a_copy_from_another_repository_is_refused_and_the_seed_runs_loudly(self, external):
        edit_manifest(external / VESTABOARD, version="99.0.0")
        set_origin(external / VESTABOARD, "https://github.com/someone/vestaboard-fork")
        loaded = load_first_party(VESTABOARD, external_dir=external)
        assert loaded.source.origin == "seed"
        assert "https://github.com/someone/vestaboard-fork" in loaded.fallback
        assert pin().repository in loaded.fallback

    def test_a_copy_with_an_unsupported_output_api_falls_back_to_the_seed_loudly(self, external):
        edit_manifest(external / VESTABOARD, version="99.0.0", output_api=2)
        loaded = load_first_party(VESTABOARD, external_dir=external)
        assert loaded.source.origin == "seed"
        assert "output_api" in loaded.fallback

    def test_a_copy_that_does_not_import_falls_back_to_the_seed_loudly(self, external):
        edit_manifest(external / VESTABOARD, version="99.0.0")
        (external / VESTABOARD / "__init__.py").write_text("raise ImportError('broken release')\n", "utf-8")
        loaded = load_first_party(VESTABOARD, external_dir=external)
        assert loaded.source.origin == "seed"
        assert "broken release" in loaded.fallback
        assert Path(sys.modules["plugins.vestaboard"].__file__).parent == seed_root() / VESTABOARD


# --- the plugin loader: what runs is registered first-party -------------------------------------------


class TestLoader:
    def test_the_running_copy_is_registered_as_the_first_party_output(self, external, tmp_path):
        edit_manifest(external / VESTABOARD, version="99.0.0")
        loader = PluginLoader(plugins_dir=tmp_path / "builtin", external_dirs=[external])
        assert loader.load_plugin(VESTABOARD) is not None
        definition = output_registry().get(VESTABOARD)
        assert (definition.plugin, definition.beta_gated) == (False, False)
        assert running_file().parent == external / VESTABOARD
        assert loader.get_source(VESTABOARD).local_path == str(external / VESTABOARD)
        assert loader.seed_fallbacks == {}

    def test_a_seed_fallback_is_a_load_error_naming_why(self, external, tmp_path):
        edit_manifest(external / VESTABOARD, version="99.0.0", output_api=2)
        loader = PluginLoader(plugins_dir=tmp_path / "builtin", external_dirs=[external])
        assert loader.load_plugin(VESTABOARD) is not None
        assert "output_api" in loader.seed_fallbacks[VESTABOARD]
        assert loader.load_errors[VESTABOARD] == [loader.seed_fallbacks[VESTABOARD]]
        assert running_file().parent == seed_root() / VESTABOARD

    def test_a_plugin_claiming_the_id_never_runs_or_becomes_a_plugin_output(self, external, tmp_path):
        imposter = external / VESTABOARD
        edit_manifest(imposter, version="99.0.0")
        set_origin(imposter, "https://github.com/someone/vestaboard-fork")
        sentinel = tmp_path / "imported"
        (imposter / "__init__.py").write_text(f"open({str(sentinel)!r}, 'w').close()\n", "utf-8")
        loader = PluginLoader(plugins_dir=tmp_path / "builtin", external_dirs=[external])

        loader.load_plugin(VESTABOARD)
        assert not sentinel.exists()
        assert output_registry().get(VESTABOARD).plugin is False
        assert running_file().parent == seed_root() / VESTABOARD
        assert "someone/vestaboard-fork" in loader.load_errors[VESTABOARD][0]


# --- the Integrations page: listed, required, updated ------------------------------------------------


class TestIntegrations:
    @pytest.mark.parametrize("output_id", FIRST_PARTY_OUTPUTS)
    def test_each_is_listed_as_a_required_output_plugin(self, tmp_path, monkeypatch, output_id):
        registry = make_registry(tmp_path, monkeypatch)
        (row,) = [p for p in registry.list_plugins() if p["id"] == output_id]
        assert (row["plugin_type"], row["required"], row["source"]["source_type"]) == ("output", True, "external")

    def test_a_new_release_is_offered_even_when_no_board_uses_it(self, tmp_path, monkeypatch, origin):
        from src.settings.service import get_settings_service

        get_settings_service().set_boards(
            [{"id": "tv", "name": "TV", "output": FIESTAPANEL, "api_mode": "virtual", "device_type": "flagship"}]
        )
        registry = make_registry(tmp_path, monkeypatch)
        release(origin, "99.0.0")
        assert registry.check_for_updates()[VESTABOARD] is True
        (row,) = [p for p in registry.list_plugins() if p["id"] == VESTABOARD]
        assert row["update_available"] is True

    def test_a_release_needing_another_output_api_is_held_back(self, tmp_path, monkeypatch, origin):
        registry = make_registry(tmp_path, monkeypatch)
        release(origin, "99.0.0", output_api=2)
        assert registry.check_for_updates()[VESTABOARD] is False
        assert "output_api 2" in registry.get_update_blocked_reasons()[VESTABOARD]

    def test_applying_an_update_runs_the_new_release_and_rebuilds_the_boards(self, tmp_path, monkeypatch, origin):
        import asyncio

        from src.plugins.service import PluginService

        registry = make_registry(tmp_path, monkeypatch)
        head = release(origin, "99.0.0")
        rebuilt: list[bool] = []
        service = PluginService(registry=registry, rebuild_boards=lambda: rebuilt.append(True))

        asyncio.run(service.apply_update(VESTABOARD))
        external = get_external_plugins_dir()
        assert get_local_head_sha(external / VESTABOARD) == head
        assert running_file().parent == external / VESTABOARD
        assert registry.get_manifest(VESTABOARD).version == "99.0.0"
        assert rebuilt == [True]

    def test_a_release_that_does_not_load_is_rolled_back(self, tmp_path, monkeypatch, origin):
        import asyncio

        from src.plugins.errors import PluginOperationFailed
        from src.plugins.service import PluginService

        registry = make_registry(tmp_path, monkeypatch)
        release(origin, "99.0.0", init="raise ImportError('broken release')\n")
        service = PluginService(registry=registry, rebuild_boards=lambda: None)

        with pytest.raises(PluginOperationFailed, match="rolled back"):
            asyncio.run(service.apply_update(VESTABOARD))
        assert get_local_head_sha(get_external_plugins_dir() / VESTABOARD) == pin().commit
        assert running_file().parent == seed_root() / VESTABOARD
        assert registry.get_seed_fallback(VESTABOARD) is None

    @pytest.mark.parametrize("output_id", FIRST_PARTY_OUTPUTS)
    def test_it_cannot_be_uninstalled(self, tmp_path, monkeypatch, output_id):
        registry = make_registry(tmp_path, monkeypatch)
        (error,) = registry.uninstall_external_plugin(output_id)
        assert "comes with FiestaBoard" in error
        assert (get_external_plugins_dir() / output_id / "manifest.json").is_file()
        assert output_registry().get(output_id) is not None

    def test_a_git_install_claiming_the_id_is_refused_before_anything_is_fetched(self, tmp_path, monkeypatch):
        from src.plugins import sources

        registry = make_registry(tmp_path, monkeypatch)
        fetched: list[str] = []
        monkeypatch.setattr(sources, "clone_or_update_repo", lambda *a, **k: fetched.append("x") or (True, ""))
        (error,) = registry.install_from_git("https://github.com/someone/vestaboard-fork", plugin_id=VESTABOARD)
        assert "comes with FiestaBoard" in error
        assert fetched == []

    def test_the_uninstall_api_answers_400(self, tmp_path, monkeypatch):
        from fastapi.testclient import TestClient

        import src.plugins.registry as registry_module
        from src.api_server import app

        monkeypatch.setattr(registry_module, "_registry", make_registry(tmp_path, monkeypatch))
        response = TestClient(app).delete(f"/plugins/{FIESTAPANEL}/uninstall")
        assert response.status_code == 400, response.text
        assert "comes with FiestaBoard" in response.json()["detail"]


# --- boards follow the code that runs -----------------------------------------------------------------


def test_a_boards_runtime_signature_changes_when_its_outputs_code_does(external, tmp_path):
    from src.main import DisplayService

    board = {"id": "sign", "output": VESTABOARD, "output_config": {"host": "192.0.2.1", "local_api_key": "k"}}
    before = DisplayService._config_signature(board)
    assert DisplayService._config_signature(dict(board)) == before
    edit_manifest(external / VESTABOARD, version="99.0.0")
    PluginLoader(plugins_dir=tmp_path / "builtin", external_dirs=[external]).load_plugin(VESTABOARD)
    assert DisplayService._config_signature(board) != before


# --- offline boot ---------------------------------------------------------------------------------------

_OFFLINE_REGISTRY_BOOT = """
import json, socket, sys

def refuse(*args, **kwargs):
    raise OSError("the offline-boot test allows no network")

socket.socket.connect = refuse
socket.socket.connect_ex = refuse
socket.create_connection = refuse
socket.getaddrinfo = refuse

from src.outputs.registry import output_registry
from src.plugins.registry import get_plugin_registry
from src.plugins.sources import get_external_plugins_dir

registry = get_plugin_registry()
registry.initialize()
rows = {p["id"]: p for p in registry.list_plugins()}
print(json.dumps({
    "installed": sorted(p.name for p in get_external_plugins_dir().iterdir() if not p.name.startswith(".")),
    "listed": sorted(i for i in ("vestaboard", "fiestapanel") if i in rows),
    "files": {i: sys.modules[output_registry().get(i).plugin_class.__module__].__file__ for i in ("vestaboard", "fiestapanel")},
    "errors": registry.get_load_errors(),
}))
"""


def test_an_offline_boot_installs_both_from_the_seed_and_runs_them(tmp_path):
    from src.outputs.seed import SEED_DIR_ENV

    env = {
        **{k: v for k, v in os.environ.items() if not k.startswith("FIESTABOARD_DEV_OUTPUT_")},
        "PYTHONPATH": str(ROOT),
        "FIESTABOARD_DATA_DIR": str(tmp_path / "data"),
        SEED_DIR_ENV: str(seed_root()),
    }
    out = subprocess.run(
        [sys.executable, "-c", _OFFLINE_REGISTRY_BOOT], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120
    )
    assert out.returncode == 0, out.stderr[-3000:]
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert {"fiestapanel", "vestaboard"} <= set(result["installed"])
    assert result["listed"] == ["fiestapanel", "vestaboard"]
    for output_id, path in result["files"].items():
        assert Path(path).parent == seed_root() / output_id
    assert not {"vestaboard", "fiestapanel"} & set(result["errors"])
