"""Vestaboard and FiestaPanel load from the output seed (Phase 4, P4b).

They live in their own repositories now
(``Fiestaboard/fiestaboard-output--vestaboard`` / ``--fiestapanel``) and reach
the image only through the output seed: the commits ``outputs.lock.json``
pins, fetched and verified at build (``scripts/seed_outputs.py``). Core loads
them from there (:mod:`src.outputs.first_party`). This pins the trust rule:

- only an id core drives itself **and** the seed's lock pins as loadable is
  first-party; anything else is never loaded as one;
- the seed copy must match the lock's ``tree_sha256`` every time it loads: a
  corrupted copy is refused, and only that output is left out;
- an installed plugin can never stand in for one (refused before its code
  is imported), and the seed never installs them as plugins;
- a contributor's ``FIESTABOARD_DEV_OUTPUT_<ID>`` checkout loads instead,
  without the digest check;
- boot needs no network: everything comes from the seed.

The suite runs against a seed built from the repo's lock (``tests/conftest.py``).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from src.outputs.first_party import (
    FIRST_PARTY_OUTPUTS,
    FirstPartyOutputError,
    dev_override_env,
    first_party_source,
    is_first_party_output,
    load_first_party,
    register_first_party_outputs,
)
from src.outputs.registry import FIESTAPANEL, VESTABOARD, OutputRegistry, output_registry
from src.outputs.seed import (
    LOCKFILE,
    SEED_DIR_ENV,
    install_seeded_outputs_for_boards,
    load_lock,
    seed_root,
    seeded_output,
    tree_digest,
)
from src.plugins.loader import PluginLoader

ROOT = Path(__file__).resolve().parents[1]
_PREFIXES = tuple(f"plugins.{output_id}" for output_id in FIRST_PARTY_OUTPUTS)
#: A contributor running the suite against a local checkout
#: (``FIESTABOARD_DEV_OUTPUT_<ID>``) has not loaded the seed's copies.
_OVERRIDDEN = any(os.environ.get(dev_override_env(output_id), "").strip() for output_id in FIRST_PARTY_OUTPUTS)


@pytest.fixture(autouse=True)
def _no_dev_override(monkeypatch):
    """Each test here decides for itself whether an override is set."""
    for output_id in FIRST_PARTY_OUTPUTS:
        monkeypatch.delenv(dev_override_env(output_id), raising=False)


@pytest.fixture
def seed_copy(tmp_path: Path) -> Path:
    """A writable copy of the suite's seed, to corrupt or re-pin."""
    dest = tmp_path / "seed"
    shutil.copytree(seed_root(), dest, ignore=shutil.ignore_patterns("__pycache__"))
    for path in [dest, *dest.rglob("*")]:
        if not path.is_symlink():
            path.chmod(path.stat().st_mode | stat.S_IWUSR)
    return dest


def repin(seed: Path, output_id: str, **changes: object) -> None:
    lock = json.loads((seed / LOCKFILE).read_text())
    if changes.pop("remove", False):
        del lock["outputs"][output_id]
    else:
        lock["outputs"][output_id].update(changes)
    (seed / LOCKFILE).write_text(json.dumps(lock))


@pytest.fixture
def keep_first_party_modules():
    """Put the suite's ``plugins.vestaboard`` / ``plugins.fiestapanel`` modules
    back after a test that loads them from another copy: other tests hold
    references to them (and patch them by name)."""
    import plugins

    saved = {name: module for name, module in sys.modules.items() if name.startswith(_PREFIXES)}
    attrs = {output_id: vars(plugins)[output_id] for output_id in FIRST_PARTY_OUTPUTS if output_id in vars(plugins)}
    yield
    for name in [name for name in sys.modules if name.startswith(_PREFIXES)]:
        del sys.modules[name]
    sys.modules.update(saved)
    for output_id, module in attrs.items():
        setattr(plugins, output_id, module)


# --- loaded from the seed -------------------------------------------------------------------


@pytest.mark.skipif(_OVERRIDDEN, reason="a FIESTABOARD_DEV_OUTPUT_* checkout is loaded, not the seed")
class TestLoadedFromTheSeed:
    def test_the_suites_seed_was_built_from_the_repos_lock(self):
        assert load_lock(seed_root() / LOCKFILE) == load_lock(ROOT / LOCKFILE)

    @pytest.mark.parametrize("output_id", FIRST_PARTY_OUTPUTS)
    def test_each_loads_from_its_seed_copy_at_the_pinned_commit(self, output_id):
        pin = load_lock(ROOT / LOCKFILE)[output_id]
        loaded = load_first_party(output_id)
        assert (loaded.source.origin, loaded.source.commit) == ("seed", pin.commit)
        assert loaded.source.path == seed_root() / output_id
        assert tree_digest(loaded.source.path) == pin.tree_sha256

    @pytest.mark.parametrize("output_id", FIRST_PARTY_OUTPUTS)
    def test_the_code_that_runs_is_the_seed_copys_imported_as_plugins_id(self, output_id):
        board = (
            {"id": "b", "api_mode": "virtual"}
            if output_id == FIESTAPANEL
            else {"id": "b", "host": "192.0.2.1", "local_api_key": "k"}
        )
        plugin = output_registry().get(output_id).build(board).plugin
        module = sys.modules[type(plugin).__module__]
        assert module.__name__.startswith(f"plugins.{output_id}.")
        assert Path(module.__file__).parent == seed_root() / output_id

    @pytest.mark.parametrize("output_id", FIRST_PARTY_OUTPUTS)
    def test_they_are_registered_first_party(self, output_id):
        definition = output_registry().get(output_id)
        assert (definition.plugin, definition.beta_gated) == (False, False)


# --- the trust rule -------------------------------------------------------------------------


class TestTrust:
    def test_a_corrupted_seed_file_is_refused_by_its_digest(self, seed_copy):
        before = sys.modules["plugins.vestaboard"]
        with (seed_copy / VESTABOARD / "transport.py").open("a") as f:
            f.write("\n# tampered\n")
        with pytest.raises(FirstPartyOutputError, match=r"tree digest .* the lock pins"):
            load_first_party(VESTABOARD, seed_dir=seed_copy)
        # Refused before anything was imported from it.
        assert sys.modules["plugins.vestaboard"] is before

    def test_a_refused_output_is_left_out_and_the_other_still_registers(
        self, seed_copy, monkeypatch, caplog, keep_first_party_modules
    ):
        (seed_copy / VESTABOARD / "tiles.py").write_text("raise SystemExit('never imported')\n")
        monkeypatch.setenv(SEED_DIR_ENV, str(seed_copy))
        registry = OutputRegistry()
        with caplog.at_level(logging.ERROR, logger="src.outputs.first_party"):
            register_first_party_outputs(registry)
        assert registry.get(VESTABOARD) is None
        assert registry.get(FIESTAPANEL) is not None
        assert "vestaboard could not be loaded" in caplog.text and "tree digest" in caplog.text

    def test_an_output_the_lock_does_not_pin_is_not_first_party(self, seed_copy):
        repin(seed_copy, VESTABOARD, remove=True)
        with pytest.raises(FirstPartyOutputError, match="not pinned in the output seed's lock"):
            load_first_party(VESTABOARD, seed_dir=seed_copy)

    def test_a_data_only_pin_is_not_loaded(self, seed_copy):
        repin(seed_copy, FIESTAPANEL, loadable=False)
        with pytest.raises(FirstPartyOutputError, match="data only"):
            load_first_party(FIESTAPANEL, seed_dir=seed_copy)

    def test_a_pin_whose_output_api_the_manifest_does_not_declare_is_refused(self, seed_copy):
        repin(seed_copy, FIESTAPANEL, output_api=2)
        with pytest.raises(FirstPartyOutputError, match="output_api is 1, the lock pins 2"):
            load_first_party(FIESTAPANEL, seed_dir=seed_copy)

    def test_a_seeded_output_core_does_not_drive_itself_is_never_first_party(self):
        assert "divoom_pixoo" in load_lock(ROOT / LOCKFILE)
        assert not is_first_party_output("divoom_pixoo")
        with pytest.raises(FirstPartyOutputError, match="not a first-party output"):
            first_party_source("divoom_pixoo")

    @pytest.mark.parametrize("output_id", FIRST_PARTY_OUTPUTS)
    def test_the_seed_never_offers_them_as_installable_plugins(self, output_id):
        assert load_lock(seed_root() / LOCKFILE)[output_id].loadable is True
        assert seeded_output(output_id) is None

    def test_a_board_naming_one_installs_nothing(self, tmp_path):
        external = tmp_path / "external"
        external.mkdir()
        boards = [{"id": "a", "output": VESTABOARD}, {"id": "b", "output": FIESTAPANEL}]
        assert install_seeded_outputs_for_boards(boards, plugin_dirs=[external], external_dir=external) == []
        assert list(external.iterdir()) == []

    def test_an_installed_plugin_with_their_id_is_refused_before_it_is_imported(self, tmp_path):
        external = tmp_path / "external"
        imposter = external / VESTABOARD
        shutil.copytree(seed_root() / VESTABOARD, imposter, ignore=shutil.ignore_patterns("__pycache__", ".git"))
        sentinel = tmp_path / "imported"
        imposter.chmod(0o755)
        (imposter / "__init__.py").chmod(0o644)
        (imposter / "__init__.py").write_text(f"open({str(sentinel)!r}, 'w').close()\n")
        before = sys.modules["plugins.vestaboard"]
        loader = PluginLoader(plugins_dir=tmp_path / "builtin", external_dirs=[external], seed_dir=seed_root())

        assert loader.load_plugin(VESTABOARD) is None
        assert not sentinel.exists()
        assert "first-party output FiestaBoard loads from its bundled seed" in loader.load_errors[VESTABOARD][0]
        assert sys.modules["plugins.vestaboard"] is before
        assert output_registry().get(VESTABOARD).plugin is False


# --- the contributor override ---------------------------------------------------------------


class TestDevOverride:
    def test_a_local_checkout_loads_instead_of_the_seed_without_the_digest_check(
        self, tmp_path, monkeypatch, caplog, keep_first_party_modules
    ):
        checkout = tmp_path / "fiestaboard-output--fiestapanel"
        shutil.copytree(seed_root() / FIESTAPANEL, checkout, ignore=shutil.ignore_patterns("__pycache__"))
        for path in [checkout, *checkout.rglob("*")]:
            path.chmod(path.stat().st_mode | stat.S_IWUSR)
        (checkout / "README.md").write_text("work in progress\n")  # no longer the pinned tree
        monkeypatch.setenv(dev_override_env(FIESTAPANEL), str(checkout))

        with caplog.at_level(logging.WARNING, logger="src.outputs.first_party"):
            loaded = load_first_party(FIESTAPANEL)
        assert (loaded.source.origin, loaded.source.path, loaded.source.commit) == ("dev", checkout.resolve(), None)
        assert Path(sys.modules["plugins.fiestapanel"].__file__).parent == checkout.resolve()
        assert "loaded from a local checkout (FIESTABOARD_DEV_OUTPUT_FIESTAPANEL=" in caplog.text

    def test_an_override_that_names_no_package_is_an_error(self, tmp_path, monkeypatch):
        monkeypatch.setenv(dev_override_env(VESTABOARD), str(tmp_path))
        with pytest.raises(FirstPartyOutputError, match=r"holds no manifest\.json"):
            first_party_source(VESTABOARD)

    def test_the_variable_is_named_after_the_output(self):
        assert dev_override_env(VESTABOARD) == "FIESTABOARD_DEV_OUTPUT_VESTABOARD"


# --- offline boot -----------------------------------------------------------------------------

_OFFLINE_BOOT = """
import json, socket, sys

def refuse(*args, **kwargs):
    raise OSError("the offline-boot test allows no network")

socket.socket.connect = refuse
socket.socket.connect_ex = refuse
socket.create_connection = refuse
socket.getaddrinfo = refuse

from src.outputs.factory import build_driver
from src.outputs.registry import output_registry

registry = output_registry()
panel = build_driver({"id": "tv", "api_mode": "virtual", "device_type": "flagship"})
sent = panel.send_characters([[1] * 22 for _ in range(6)])
vestaboard = build_driver({"id": "sign", "host": "192.0.2.10", "local_api_key": "k"})
print(json.dumps({
    "registered": sorted(i for i in ("vestaboard", "fiestapanel") if registry.get(i) is not None),
    "files": {i: sys.modules["plugins." + i].__file__ for i in ("vestaboard", "fiestapanel")},
    "panel_sent": list(sent),
    "panel_frame": panel.read_current_message() is not None,
    "vestaboard_driver": type(vestaboard).__name__,
}))
"""


def test_boot_needs_no_network_everything_comes_from_the_seed(tmp_path):
    env = {
        **{k: v for k, v in os.environ.items() if not k.startswith("FIESTABOARD_DEV_OUTPUT_")},
        "PYTHONPATH": str(ROOT),
        "FIESTABOARD_DATA_DIR": str(tmp_path / "data"),
        SEED_DIR_ENV: str(seed_root()),
    }
    out = subprocess.run(
        [sys.executable, "-c", _OFFLINE_BOOT], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120
    )
    assert out.returncode == 0, out.stderr[-3000:]
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result["registered"] == ["fiestapanel", "vestaboard"]
    for output_id, path in result["files"].items():
        assert Path(path).parent == seed_root() / output_id
    assert result["panel_sent"] == [True, True]
    assert result["panel_frame"] is True
    assert result["vestaboard_driver"] == "OutputPluginDriver"
