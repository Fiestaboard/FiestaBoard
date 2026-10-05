"""The output seed and the output_api gate (plan D8).

A board must never go dark because of its output plugin. Pinned here:

- **the lockfile** (``outputs.lock.json``) is strict, the repo's own lock is
  valid, and the image builds the seed from it with the same script tests
  run (``scripts/seed_outputs.py``);
- **the seed build** fetches each pinned commit and refuses a tree whose
  digest, commit or manifest disagrees with the lock — nothing is left behind;
- **auto-install**: at boot a board naming a seeded output that is not
  installed gets it copied from the seed (no network), as an ordinary
  updatable checkout; legacy boards, installed plugins and data-only entries
  are left alone;
- **precedence** (gate 3, load): a valid installed copy wins; one whose
  output_api is unsupported, that does not import, or that fails its
  self-check falls back to the seed, loudly;
- **update check** (gate 1): an incoming output_api this core does not
  implement is never offered, decided before anything is pulled;
- **update** (gate 2): an output plugin's update that cannot run is rolled
  back to the commit it replaced; a data plugin's keeps today's rule;
- **uninstall guard**: an output plugin a board uses cannot be uninstalled,
  through the registry or the API.

Tests never reach the network: every "remote" is a local git repository.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from src.outputs.registry import output_registry
from src.outputs.seed import (
    DEFAULT_SEED_DIR,
    LOCKFILE,
    LockError,
    build_seed,
    fetch_entry,
    install_from_seed,
    install_seeded_outputs_for_boards,
    load_lock,
    parse_lock,
    seeded_output,
    tree_digest,
)
from src.plugins import sources
from src.plugins.loader import PluginLoader
from src.plugins.sources import (
    check_plugin_update_available,
    clone_or_update_repo,
    get_local_head_sha,
    install_git_plugin,
    update_external_plugin,
)

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = Path(__file__).parent / "fixtures" / "plugins" / "recording_output"
PLUGIN_ID = "recording_output"
FAKE_REPO_URL = "https://example.invalid/Fiestaboard/fiestaboard-output--recording-output"

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
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **_GIT_ENV},
    )
    return result.stdout.strip()


def commit_all(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def set_output_api(plugin_dir: Path, api: int) -> None:
    manifest = json.loads((plugin_dir / "manifest.json").read_text("utf-8"))
    manifest["output"]["output_api"] = api
    (plugin_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), "utf-8")


def output_repo(base: Path) -> tuple[Path, str]:
    """A local git repo holding the recording output plugin; (path, head)."""
    repo = base / "fiestaboard-output--recording-output"
    shutil.copytree(FIXTURE, repo, ignore=shutil.ignore_patterns("__pycache__"))
    git(repo, "init", "--quiet", "--initial-branch=main")
    return repo, commit_all(repo, "initial")


def lock_for(repo: Path, commit: str, *, loadable: bool = True, digest: str | None = None) -> dict:
    """A lock pinning *repo* at *commit* (digest computed from that tree)."""
    if digest is None:
        snapshot = repo.parent / f"snapshot-{commit[:7]}"
        shutil.rmtree(snapshot, ignore_errors=True)
        subprocess.run(
            ["git", "clone", "--quiet", str(repo), str(snapshot)], check=True, env={**os.environ, **_GIT_ENV}
        )
        git(snapshot, "checkout", "--quiet", commit)
        digest = tree_digest(snapshot)
    return {
        "lock_version": 1,
        "outputs": {
            PLUGIN_ID: {
                "repository": FAKE_REPO_URL,
                "commit": commit,
                "output_api": 1,
                "tree_sha256": digest,
                "loadable": loadable,
            }
        },
    }


def write_lock(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data), "utf-8")
    return path


@pytest.fixture
def seed(tmp_path) -> Path:
    """A built seed holding the recording output (loadable)."""
    repo, head = output_repo(tmp_path / "origin")
    lock = write_lock(tmp_path / LOCKFILE, lock_for(repo, head))
    root = tmp_path / "seed"
    build_seed(lock, root, repositories={PLUGIN_ID: repo.as_uri()})
    return root


@pytest.fixture
def loaders():
    """Loaders a test makes; their output plugins are unloaded afterwards."""
    made: list[PluginLoader] = []
    yield made
    for loader in made:
        loader.unload_plugin(PLUGIN_ID)
    output_registry().remove_plugin(PLUGIN_ID)


def make_loader(loaders, tmp_path: Path, seed_root: Path, external: Path) -> PluginLoader:
    loader = PluginLoader(plugins_dir=tmp_path / "builtin", external_dirs=[external], seed_dir=seed_root)
    loaders.append(loader)
    return loader


def installed_copy(tmp_path: Path) -> Path:
    """The recording output installed in an external plugins dir."""
    external = tmp_path / "external"
    shutil.copytree(FIXTURE, external / PLUGIN_ID, ignore=shutil.ignore_patterns("__pycache__"))
    return external


# --- the lockfile ------------------------------------------------------------------------------


GOOD_ENTRY = {
    "repository": "https://github.com/Fiestaboard/fiestaboard-output--x",
    "commit": "a" * 40,
    "output_api": 1,
    "tree_sha256": "b" * 64,
}


class TestLockfile:
    def test_a_well_formed_entry_parses(self):
        (entry,) = parse_lock({"lock_version": 1, "outputs": {"x": GOOD_ENTRY}}).values()
        assert (entry.plugin_id, entry.commit, entry.output_api, entry.loadable) == ("x", "a" * 40, 1, True)

    @pytest.mark.parametrize(
        ("change", "complaint"),
        [
            ({"repository": "http://github.com/x"}, "https://"),
            ({"commit": "main"}, "40-character"),
            ({"output_api": "1"}, "positive integer"),
            ({"tree_sha256": "B" * 64}, "64 lowercase hex"),
            ({"loadable": "no"}, "true or false"),
            ({"branch": "main"}, "unknown keys"),
        ],
    )
    def test_a_malformed_entry_is_refused(self, change, complaint):
        with pytest.raises(LockError, match=complaint):
            parse_lock({"lock_version": 1, "outputs": {"x": {**GOOD_ENTRY, **change}}})

    def test_an_unknown_lock_version_is_refused(self):
        with pytest.raises(LockError, match="lock_version"):
            parse_lock({"lock_version": 2, "outputs": {}})

    def test_the_repos_lock_is_valid_and_pins_pixoo_as_data_only(self):
        entries = load_lock(ROOT / LOCKFILE)
        pixoo = entries["divoom_pixoo"]
        assert pixoo.repository == "https://github.com/Fiestaboard/fiestaboard-output--divoom-pixoo"
        assert pixoo.commit == "01e9ee21548012a007ef7aef78cdfe1a16cad678"
        # The repo holds device data only (no __init__.py / manifest.json yet):
        # it must never be loaded or auto-installed as a plugin.
        assert pixoo.loadable is False

    def test_the_image_builds_the_seed_with_the_script_into_the_default_dir(self):
        dockerfile = (ROOT / "Dockerfile").read_text("utf-8")
        assert "COPY outputs.lock.json" in dockerfile
        assert f"scripts/seed_outputs.py build --lock outputs.lock.json --dest {DEFAULT_SEED_DIR}" in dockerfile


# --- the tree digest ----------------------------------------------------------------------------


class TestTreeDigest:
    def make(self, root: Path) -> Path:
        (root / "pkg").mkdir(parents=True)
        (root / "a.txt").write_text("alpha", "utf-8")
        (root / "pkg" / "b.py").write_text("beta", "utf-8")
        return root

    def test_git_data_and_bytecode_are_not_part_of_the_tree(self, tmp_path):
        tree = self.make(tmp_path / "t")
        before = tree_digest(tree)
        (tree / ".git").mkdir()
        (tree / ".git" / "HEAD").write_text("ref", "utf-8")
        (tree / "pkg" / "__pycache__").mkdir()
        (tree / "pkg" / "__pycache__" / "b.pyc").write_bytes(b"\0")
        assert tree_digest(tree) == before

    def test_content_changes_the_digest(self, tmp_path):
        tree = self.make(tmp_path / "t")
        before = tree_digest(tree)
        (tree / "a.txt").write_text("alpha!", "utf-8")
        assert tree_digest(tree) != before

    def test_the_executable_bit_changes_the_digest(self, tmp_path):
        tree = self.make(tmp_path / "t")
        before = tree_digest(tree)
        (tree / "a.txt").chmod(0o755)
        assert tree_digest(tree) != before

    def test_the_same_content_elsewhere_has_the_same_digest(self, tmp_path):
        assert tree_digest(self.make(tmp_path / "one")) == tree_digest(self.make(tmp_path / "two"))

    def test_a_symlink_is_refused(self, tmp_path):
        tree = self.make(tmp_path / "t")
        (tree / "link").symlink_to(tree / "a.txt")
        with pytest.raises(LockError, match="symlinks"):
            tree_digest(tree)


# --- the seed build -------------------------------------------------------------------------------


class TestSeedBuild:
    def test_the_build_fetches_the_pinned_commit_and_writes_the_lock_beside_it(self, tmp_path):
        repo, head = output_repo(tmp_path / "origin")
        (repo / "LATER.txt").write_text("after the pin", "utf-8")
        later = commit_all(repo, "later")
        lock = write_lock(tmp_path / LOCKFILE, lock_for(repo, head))
        root = tmp_path / "seed"
        build_seed(lock, root, repositories={PLUGIN_ID: repo.as_uri()})
        assert git(root / PLUGIN_ID, "rev-parse", "HEAD") == head != later
        assert not (root / PLUGIN_ID / "LATER.txt").exists()
        assert load_lock(root / LOCKFILE) == load_lock(lock)
        # The checkout's origin is the repository the lock names, so an
        # installed copy of it updates from upstream.
        assert git(root / PLUGIN_ID, "remote", "get-url", "origin") == FAKE_REPO_URL

    def test_a_tree_that_does_not_match_the_digest_is_refused_and_removed(self, tmp_path):
        repo, head = output_repo(tmp_path / "origin")
        (entry,) = parse_lock(lock_for(repo, head, digest="0" * 64)).values()
        with pytest.raises(LockError, match="tree digest"):
            fetch_entry(entry, tmp_path / "seed", repository=repo.as_uri())
        assert not (tmp_path / "seed" / PLUGIN_ID).exists()

    def test_a_loadable_entry_whose_manifest_targets_another_output_api_is_refused(self, tmp_path):
        repo, _ = output_repo(tmp_path / "origin")
        set_output_api(repo, 2)
        head = commit_all(repo, "api 2")
        (entry,) = parse_lock(lock_for(repo, head)).values()
        with pytest.raises(LockError, match="output_api is 2, the lock pins 1"):
            fetch_entry(entry, tmp_path / "seed", repository=repo.as_uri())

    def test_a_data_only_entry_needs_no_manifest(self, tmp_path):
        repo, _ = output_repo(tmp_path / "origin")
        for name in ("manifest.json", "__init__.py"):
            (repo / name).unlink()
        head = commit_all(repo, "data only")
        (entry,) = parse_lock(lock_for(repo, head, loadable=False)).values()
        assert (fetch_entry(entry, tmp_path / "seed", repository=repo.as_uri()) / "output").is_dir()

    def test_the_script_exits_non_zero_on_a_bad_lock(self, tmp_path, capsys):
        from scripts.seed_outputs import main

        lock = write_lock(tmp_path / LOCKFILE, {"lock_version": 1, "outputs": {"x": {**GOOD_ENTRY, "commit": "main"}}})
        assert main(["check", "--lock", str(lock)]) == 1
        assert "40-character" in capsys.readouterr().err

    def test_the_script_prints_a_trees_digest(self, tmp_path, capsys):
        from scripts.seed_outputs import main

        repo, _ = output_repo(tmp_path / "origin")
        assert main(["digest", str(repo)]) == 0
        assert capsys.readouterr().out.strip() == tree_digest(repo)

    def test_the_script_checks_the_repos_lock(self, capsys):
        from scripts.seed_outputs import main

        assert main(["check", "--lock", str(ROOT / LOCKFILE)]) == 0
        assert "1 pinned output(s) OK" in capsys.readouterr().out


# --- auto-install from the seed ---------------------------------------------------------------------


def named(output: str | None = PLUGIN_ID, board_id: str = "sign") -> dict:
    board = {"id": board_id, "name": f"Board {board_id}", "device_type": "flagship"}
    if output is not None:
        board["output"] = output
    return board


class TestAutoInstall:
    def test_a_board_naming_a_seeded_output_gets_it_installed(self, seed, tmp_path):
        external = tmp_path / "external"
        external.mkdir()
        installed = install_seeded_outputs_for_boards(
            [named()], plugin_dirs=[external], external_dir=external, root=seed
        )
        assert installed == [PLUGIN_ID]
        target = external / PLUGIN_ID
        assert tree_digest(target) == seeded_output(PLUGIN_ID, seed).entry.tree_sha256
        # An ordinary checkout at the pinned commit: it updates like any
        # installed plugin.
        assert get_local_head_sha(target) == seeded_output(PLUGIN_ID, seed).entry.commit

    def test_the_installed_copy_is_writable_even_from_a_read_only_seed(self, seed, tmp_path):
        for dirpath, _dirs, files in os.walk(seed):
            for name in files:
                os.chmod(os.path.join(dirpath, name), 0o444)
        external = tmp_path / "external"
        external.mkdir()
        assert install_from_seed(PLUGIN_ID, external, seed) == (True, "")
        assert os.access(external / PLUGIN_ID / "manifest.json", os.W_OK)

    def test_legacy_boards_installed_plugins_and_unseeded_ids_are_left_alone(self, seed, tmp_path):
        external = installed_copy(tmp_path)
        (external / PLUGIN_ID / "MARK").write_text("mine", "utf-8")
        boards = [named(None, "legacy"), named("vestaboard", "vb"), named(), named("not_seeded", "x")]
        assert install_seeded_outputs_for_boards(boards, plugin_dirs=[external], external_dir=external, root=seed) == []
        assert (external / PLUGIN_ID / "MARK").read_text("utf-8") == "mine"
        assert not (external / "not_seeded").exists()

    def test_a_data_only_seed_entry_is_never_installed(self, tmp_path):
        repo, head = output_repo(tmp_path / "origin")
        lock = write_lock(tmp_path / LOCKFILE, lock_for(repo, head, loadable=False))
        root = tmp_path / "seed"
        build_seed(lock, root, repositories={PLUGIN_ID: repo.as_uri()})
        external = tmp_path / "external"
        external.mkdir()
        assert (
            install_seeded_outputs_for_boards([named()], plugin_dirs=[external], external_dir=external, root=root) == []
        )
        assert seeded_output(PLUGIN_ID, root) is None

    def test_a_tampered_seed_copy_is_not_installed(self, seed, tmp_path):
        (seed / PLUGIN_ID / "__init__.py").write_text("raise SystemExit\n", "utf-8")
        external = tmp_path / "external"
        external.mkdir()
        ok, err = install_from_seed(PLUGIN_ID, external, seed)
        assert ok is False and "does not match the lock" in err
        assert sorted(p.name for p in external.iterdir()) == []

    def test_boot_installs_and_loads_what_the_saved_boards_need(self, seed, tmp_path, loaders, monkeypatch):
        from src.plugins.registry import PluginRegistry
        from src.settings.service import get_settings_service

        external = tmp_path / "external"
        external.mkdir()
        get_settings_service().set_boards([named()])
        registry = PluginRegistry(plugins_dir=tmp_path / "builtin")
        monkeypatch.setattr(registry, "_loader", make_loader(loaders, tmp_path, seed, external))
        registry.initialize()
        assert (external / PLUGIN_ID / "manifest.json").is_file()
        assert registry.get_plugin_source(PLUGIN_ID).local_path == str((external / PLUGIN_ID).resolve())
        assert output_registry().get(PLUGIN_ID) is not None


# --- gate 3: load precedence ------------------------------------------------------------------------


class TestLoadPrecedence:
    def test_a_valid_installed_copy_wins_over_the_seed(self, seed, tmp_path, loaders):
        external = installed_copy(tmp_path)
        loader = make_loader(loaders, tmp_path, seed, external)
        assert loader.load_plugin(PLUGIN_ID) is not None
        assert loader.seed_fallbacks == {}
        assert PLUGIN_ID not in loader.load_errors
        import sys

        assert Path(sys.modules[f"plugins.{PLUGIN_ID}"].__file__).resolve().parent == (external / PLUGIN_ID).resolve()

    def test_an_unsupported_output_api_falls_back_to_the_seed_loudly(self, seed, tmp_path, loaders):
        external = installed_copy(tmp_path)
        set_output_api(external / PLUGIN_ID, 2)
        loader = make_loader(loaders, tmp_path, seed, external)
        assert loader.load_plugin(PLUGIN_ID) is not None
        import sys

        assert Path(sys.modules[f"plugins.{PLUGIN_ID}"].__file__).resolve().parent == (seed / PLUGIN_ID).resolve()
        (error,) = loader.load_errors[PLUGIN_ID]
        assert "cannot run" in error and "output_api 2" in error and "bundled with FiestaBoard" in error
        assert loader.seed_fallbacks[PLUGIN_ID] == error
        # Update, reinstall and uninstall still act on the installed copy.
        assert loader.get_source(PLUGIN_ID).local_path == str((external / PLUGIN_ID).resolve())
        assert output_registry().get(PLUGIN_ID) is not None

    def test_a_copy_that_does_not_import_falls_back_to_the_seed(self, seed, tmp_path, loaders):
        external = installed_copy(tmp_path)
        (external / PLUGIN_ID / "__init__.py").write_text("raise ImportError('broken release')\n", "utf-8")
        loader = make_loader(loaders, tmp_path, seed, external)
        assert loader.load_plugin(PLUGIN_ID) is not None
        assert "broken release" in loader.seed_fallbacks[PLUGIN_ID]

    def test_a_copy_failing_its_self_check_falls_back_to_the_seed(self, seed, tmp_path, loaders):
        external = installed_copy(tmp_path)
        (external / PLUGIN_ID / "requirements.txt").write_text("fiestaboard-no-such-package-xyz\n", "utf-8")
        loader = make_loader(loaders, tmp_path, seed, external)
        assert loader.load_plugin(PLUGIN_ID) is not None
        assert "fiestaboard-no-such-package-xyz" in loader.seed_fallbacks[PLUGIN_ID]

    def test_without_a_seed_copy_an_unsupported_output_api_is_refused(self, tmp_path, loaders):
        external = installed_copy(tmp_path)
        set_output_api(external / PLUGIN_ID, 2)
        loader = make_loader(loaders, tmp_path, tmp_path / "no-seed", external)
        assert loader.load_plugin(PLUGIN_ID) is None
        assert any("output_api 2" in e for e in loader.load_errors[PLUGIN_ID])
        assert loader.seed_fallbacks == {}

    def test_a_plugin_nobody_installed_is_not_loaded_from_the_seed(self, seed, tmp_path, loaders):
        loader = make_loader(loaders, tmp_path, seed, tmp_path / "external")
        assert loader.load_plugin(PLUGIN_ID) is None
        assert output_registry().get(PLUGIN_ID) is None

    def test_a_seed_copy_runs_behind_the_output_plugins_beta(self, seed, tmp_path, loaders):
        from src.outputs.factory import build_driver
        from src.outputs.plugin_registration import OutputPluginsDisabledError

        external = installed_copy(tmp_path)
        set_output_api(external / PLUGIN_ID, 2)
        make_loader(loaders, tmp_path, seed, external).load_plugin(PLUGIN_ID)
        board = {**named(), "output_config": {"host": "192.0.2.50"}}
        with pytest.raises(OutputPluginsDisabledError):
            build_driver(board)


# --- gate 1: the update check ---------------------------------------------------------------------


def origin_and_clone(tmp_path: Path, incoming_api: int | None) -> tuple[Path, Path]:
    """An origin holding the recording output and a clone one commit behind;
    the incoming commit declares *incoming_api* (``None`` = no manifest)."""
    origin, _ = output_repo(tmp_path / "origin")
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "--quiet", str(origin), str(clone)], check=True, env={**os.environ, **_GIT_ENV})
    if incoming_api is None:
        (origin / "manifest.json").unlink()
    else:
        set_output_api(origin, incoming_api)
        (origin / "CHANGELOG.txt").write_text("next", "utf-8")
    commit_all(origin, "incoming")
    return origin, clone


def check(origin: Path, clone: Path):
    """The update check against the real remote manifest (only the SHA
    probes are stubbed: get_remote_head_sha refuses non-https remotes)."""
    with (
        mock.patch("src.plugins.sources.get_local_head_sha", return_value=git(clone, "rev-parse", "HEAD")),
        mock.patch("src.plugins.sources.get_remote_head_sha", return_value=git(origin, "rev-parse", "HEAD")),
    ):
        return check_plugin_update_available(clone)


class TestUpdateCheckGate:
    def test_an_incoming_unsupported_output_api_is_not_offered(self, tmp_path):
        result = check(*origin_and_clone(tmp_path, 2))
        assert result.available is False
        assert result.blocked_reason == "The update needs output_api 2; this FiestaBoard supports output_api 1."

    def test_the_refusal_leaves_the_checkout_untouched(self, tmp_path):
        origin, clone = origin_and_clone(tmp_path, 2)
        before = git(clone, "rev-parse", "HEAD")
        check(origin, clone)
        assert git(clone, "rev-parse", "HEAD") == before
        assert json.loads((clone / "manifest.json").read_text("utf-8"))["output"]["output_api"] == 1

    def test_an_incoming_supported_output_api_is_offered(self, tmp_path):
        result = check(*origin_and_clone(tmp_path, 1))
        assert (result.available, result.blocked_reason) == (True, "")

    def test_an_output_plugin_is_never_updated_blind(self, tmp_path):
        result = check(*origin_and_clone(tmp_path, None))
        assert result.available is False
        assert "could not be read" in result.blocked_reason


# --- gate 2: install/update verification and rollback ---------------------------------------------


@pytest.fixture
def installed(tmp_path, monkeypatch):
    """The recording output installed from a local origin; (origin, external, head)."""
    monkeypatch.setattr(sources, "_validate_git_url", lambda url: (True, ""))
    origin, head = output_repo(tmp_path / "origin")
    external = tmp_path / "external"
    external.mkdir()
    assert clone_or_update_repo(origin.as_uri(), PLUGIN_ID, external_dir=external) == (True, "")
    return origin, external, head


class TestUpdateRollback:
    def test_an_update_with_an_unsupported_output_api_is_rolled_back(self, installed):
        origin, external, head = installed
        set_output_api(origin, 2)
        commit_all(origin, "api 2")
        outcome = update_external_plugin(PLUGIN_ID, external)
        assert (outcome.ok, outcome.stage) == (False, "rolled_back")
        assert head[:12] in outcome.error and "output_api 2" in outcome.error
        assert get_local_head_sha(external / PLUGIN_ID) == head
        assert json.loads((external / PLUGIN_ID / "manifest.json").read_text("utf-8"))["output"]["output_api"] == 1

    def test_an_update_that_does_not_load_is_rolled_back_and_reloaded(self, installed):
        origin, external, head = installed
        (origin / "__init__.py").write_text("raise ImportError('broken release')\n", "utf-8")
        commit_all(origin, "broken")
        calls: list[str] = []

        def reload() -> str | None:
            calls.append(get_local_head_sha(external / PLUGIN_ID))
            return "Failed to import plugin module: broken release" if len(calls) == 1 else None

        outcome = update_external_plugin(PLUGIN_ID, external, reload=reload)
        assert (outcome.ok, outcome.stage) == (False, "rolled_back")
        assert calls[1] == head != calls[0]
        assert get_local_head_sha(external / PLUGIN_ID) == head

    def test_a_good_update_applies(self, installed):
        origin, external, head = installed
        (origin / "CHANGELOG.txt").write_text("next", "utf-8")
        new = commit_all(origin, "good")
        assert update_external_plugin(PLUGIN_ID, external, reload=lambda: None).ok is True
        assert get_local_head_sha(external / PLUGIN_ID) == new != head

    def test_a_data_plugins_failed_update_is_still_left_installed(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sources, "_validate_git_url", lambda url: (True, ""))
        origin = tmp_path / "origin" / "fiestaboard-plugin--data-thing"
        origin.mkdir(parents=True)
        (origin / "manifest.json").write_text(json.dumps({"id": "data_thing", "name": "D", "version": "1.0.0"}))
        (origin / "__init__.py").write_text("")
        git(origin, "init", "--quiet", "--initial-branch=main")
        commit_all(origin, "initial")
        external = tmp_path / "external"
        external.mkdir()
        assert clone_or_update_repo(origin.as_uri(), "data_thing", external_dir=external)[0]
        (origin / "requirements.txt").write_text("fiestaboard-no-such-package-xyz\n")
        new = commit_all(origin, "needs a package")
        assert update_external_plugin("data_thing", external).ok is True
        assert get_local_head_sha(external / "data_thing") == new

    def test_reinstalling_over_an_output_plugin_rolls_a_bad_update_back(self, installed):
        origin, external, head = installed
        set_output_api(origin, 2)
        commit_all(origin, "api 2")
        ok, err = install_git_plugin(origin.as_uri(), plugin_id=PLUGIN_ID, external_dir=external)
        assert ok is False and "rolled back" in err
        assert get_local_head_sha(external / PLUGIN_ID) == head

    def test_a_seed_fallback_counts_as_a_failed_reload(self):
        from src.plugins.service import reload_installed_copy

        registry = mock.Mock()
        registry.reload_plugin.return_value = object()
        registry.get_seed_fallback.return_value = "running the seed"
        assert reload_installed_copy(registry, PLUGIN_ID) == "running the seed"
        registry.get_seed_fallback.return_value = None
        assert reload_installed_copy(registry, PLUGIN_ID) is None


# --- the uninstall guard ---------------------------------------------------------------------------


@pytest.fixture
def live_registry(tmp_path, loaders, monkeypatch):
    """A real registry over the recording output installed externally."""
    import src.plugins.registry as registry_module
    from src.plugins.registry import PluginRegistry

    external = installed_copy(tmp_path)
    registry = PluginRegistry(plugins_dir=tmp_path / "builtin")
    monkeypatch.setattr(registry, "_loader", make_loader(loaders, tmp_path, tmp_path / "no-seed", external))
    registry.initialize()
    monkeypatch.setattr(registry_module, "_registry", registry)
    return registry, external


class TestUninstallGuard:
    def test_an_output_plugin_a_board_uses_cannot_be_uninstalled(self, live_registry):
        from src.settings.service import get_settings_service

        registry, external = live_registry
        get_settings_service().set_boards([named(board_id="kitchen"), named(None, "legacy")])
        errors = registry.uninstall_external_plugin(PLUGIN_ID)
        assert errors == [
            f"Output plugin '{PLUGIN_ID}' drives 1 board(s): 'Board kitchen'. "
            "Switch those boards to another output, or delete them, before uninstalling it."
        ]
        assert (external / PLUGIN_ID).is_dir()
        assert output_registry().get(PLUGIN_ID) is not None

    def test_an_unused_output_plugin_uninstalls(self, live_registry):
        registry, external = live_registry
        assert registry.uninstall_external_plugin(PLUGIN_ID) == []
        assert not (external / PLUGIN_ID).exists()

    def test_unreadable_boards_refuse_the_uninstall(self, live_registry, monkeypatch):
        import src.plugins.registry as registry_module

        registry, external = live_registry

        def unreadable():
            raise OSError("settings.json is locked")

        monkeypatch.setattr(registry_module, "_saved_boards", unreadable)
        (error,) = registry.uninstall_external_plugin(PLUGIN_ID)
        assert "Could not confirm" in error
        assert (external / PLUGIN_ID).is_dir()

    def test_the_api_answers_400_with_the_reason(self, live_registry):
        from fastapi.testclient import TestClient

        from src.api_server import app
        from src.settings.service import get_settings_service

        get_settings_service().set_boards([named(board_id="kitchen")])
        response = TestClient(app).delete(f"/plugins/{PLUGIN_ID}/uninstall")
        assert response.status_code == 400, response.text
        assert "drives 1 board(s): 'Board kitchen'" in response.json()["detail"]
