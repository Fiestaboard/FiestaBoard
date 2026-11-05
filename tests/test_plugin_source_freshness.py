"""Plugin source must win over timestamp/size collisions in old bytecode."""

import importlib
import importlib.machinery
import importlib.util
import json
import os
import pkgutil
import py_compile
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src import __version__
from src.config_manager import ConfigManager
from src.outputs.registry import output_registry
from src.plugins import routes, sources
from src.plugins.loader import PluginLoader
from src.plugins.registry import PluginRegistry
from src.plugins.service import PluginService, reload_installed_copy

STAMP = 1_700_000_000.25
GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
    "GIT_TERMINAL_PROMPT": "0",
}


def git(path, *args):
    return subprocess.check_output(
        ["git", "-C", str(path), *args], env={**os.environ, **GIT_ENV}, stderr=subprocess.PIPE, text=True
    ).strip()


def commit(path):
    git(path, "add", "manifest.json", "__init__.py")
    git(path, "commit", "--quiet", "-m", "fixture")
    return git(path, "rev-parse", "HEAD")


def code_for(identity, marker="OLD"):
    return (
        "from src.plugins.base import PluginBase, PluginResult\n"
        f"MARKER = {marker!r}\n"
        "class Fixture(PluginBase):\n"
        "    @property\n"
        f"    def plugin_id(self): return {identity!r}\n"
        "    def fetch_data(self): return PluginResult(available=True,data={'marker':MARKER})\n"
    ).encode()


def prime(path):
    os.utime(path, (STAMP, STAMP))
    cached = Path(
        py_compile.compile(str(path), doraise=True, invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
    )
    assert cached.exists()
    return cached


def replace_same_key(path, before, after):
    old = path.read_bytes()
    new = old.replace(before, after)
    assert old != new and len(old) == len(new)
    path.write_bytes(new)
    os.utime(path, (STAMP + 0.5, STAMP + 0.5))
    assert int(path.stat().st_mtime) == int(STAMP)


def data_plugin(parent, identity, source=None):
    code = parent / identity
    code.mkdir(parents=True)
    (code / "manifest.json").write_text(
        json.dumps({"id": identity, "name": identity, "version": "1.0.0", "variables": {"simple": ["marker"]}})
    )
    (code / "__init__.py").write_bytes(source or code_for(identity))
    return code


class PluginSourceFreshness(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.path_before = list(sys.path)
        self.context = patch.dict(os.environ, {"FIESTABOARD_DATA_DIR": str(self.root / "data")})
        self.context.start()
        self.manager_patch = patch.object(ConfigManager, "_instance", None)
        self.manager_patch.start()

    def tearDown(self):
        for worker in threading.enumerate():
            if worker.name.startswith("plugin-cleanup-qa_cache"):
                worker.join(3)
                self.assertFalse(worker.is_alive())
        for name, module in list(sys.modules.items()):
            path = getattr(module, "__file__", None)
            if name == "qa_virtual_helper" or (path and str(path).startswith(str(self.root) + os.sep)):
                sys.modules.pop(name, None)
        for path in list(sys.path_importer_cache):
            if isinstance(path, str) and path.startswith(str(self.root)):
                sys.path_importer_cache.pop(path, None)
        sys.path[:] = self.path_before
        output_registry().remove_plugin("recording_output")
        self.manager_patch.stop()
        self.context.stop()
        self.directory.cleanup()

    def loader(self, parent):
        return PluginLoader(plugins_dir=parent, external_dirs=[], seed_dir=self.root / "no-seed")

    def registry(self, identity, code):
        config = self.root / "data/config.json"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "app_version_seen": __version__,
                    "plugins": {},
                    "plugin_migrations": {"v2_completed": True},
                }
            )
        )
        manager = ConfigManager(str(config))
        registry = PluginRegistry(self.root / "builtin")
        with patch.object(registry, "_auto_install_seeded_outputs", return_value=[]):
            registry.initialize()
        self.assertIsNotNone(registry.get_plugin(identity))
        return manager, registry

    def test_reload_reads_current_entry_source_with_matching_cached_metadata(self):
        code = data_plugin(self.root, "qa_cache_entry")
        prime(code / "__init__.py")
        loader = self.loader(self.root)
        self.assertEqual(loader.load_plugin("qa_cache_entry").fetch_data().data["marker"], "OLD")
        replace_same_key(code / "__init__.py", b"'OLD'", b"'NEW'")
        self.assertEqual(loader.reload_plugin("qa_cache_entry").fetch_data().data["marker"], "NEW")

    def test_flattened_and_nested_siblings_read_current_source(self):
        code = data_plugin(self.root, "qa_cache_flat")
        (code / "__init__.py").write_text(
            "import sys\nfrom pathlib import Path\n"
            "sys.path.insert(0,str(Path(__file__).parent))\nfrom qa_cache_impl import Fixture\n"
        )
        (code / "qa_cache_impl.py").write_bytes(
            code_for("qa_cache_flat")
            .replace(b"MARKER = 'OLD'", b"from qa_cache_nested.values import MARKER\nPREFIX = 'aaa'")
            .replace(b"'marker':MARKER", b"'marker':PREFIX+MARKER")
        )
        nested = code / "qa_cache_nested"
        nested.mkdir()
        (nested / "__init__.py").write_text("")
        (nested / "values.py").write_text("MARKER = 'OLD'\n")
        for file in code.rglob("*.py"):
            prime(file)
        loader = self.loader(self.root)
        self.assertEqual(loader.load_plugin("qa_cache_flat").fetch_data().data["marker"], "aaaOLD")
        replace_same_key(code / "qa_cache_impl.py", b"'aaa'", b"'bbb'")
        replace_same_key(nested / "values.py", b"'OLD'", b"'NEW'")
        self.assertEqual(loader.reload_plugin("qa_cache_flat").fetch_data().data["marker"], "bbbNEW")

    def test_current_source_wins_with_an_external_pycache_prefix(self):
        with patch.object(sys, "pycache_prefix", str(self.root / "bytecode")):
            code = data_plugin(self.root / "plugins", "qa_cache_prefix")
            cached = prime(code / "__init__.py")
            self.assertFalse(cached.is_relative_to(code))
            loader = self.loader(code.parent)
            loader.load_plugin("qa_cache_prefix")
            replace_same_key(code / "__init__.py", b"'OLD'", b"'NEW'")
            self.assertEqual(loader.reload_plugin("qa_cache_prefix").fetch_data().data["marker"], "NEW")

    def test_current_import_error_is_not_hidden_by_previously_valid_bytecode(self):
        code = data_plugin(self.root, "qa_cache_error")
        prime(code / "__init__.py")
        loader = self.loader(self.root)
        self.assertIsNotNone(loader.load_plugin("qa_cache_error"))
        replace_same_key(code / "__init__.py", b"'OLD'", b"BOGUS")
        self.assertIsNone(loader.reload_plugin("qa_cache_error"))
        self.assertIn("BOGUS", ";".join(loader.load_errors["qa_cache_error"]))
        replace_same_key(code / "__init__.py", b"BOGUS", b"'OLD'")
        self.assertEqual(loader.reload_plugin("qa_cache_error").fetch_data().data["marker"], "OLD")

    def test_preexisting_finder_notices_new_source_despite_matching_directory_time(self):
        source = code_for("qa_cache_added").replace(b"MARKER = 'OLD'", b"from .added import MARKER")
        code = data_plugin(self.root, "qa_cache_added", source)
        finder = importlib.machinery.FileFinder(
            str(code), (importlib.machinery.SourceFileLoader, importlib.machinery.SOURCE_SUFFIXES)
        )
        os.utime(code, (STAMP, STAMP))
        self.assertIsNone(finder.find_spec("absent"))
        sys.path_importer_cache[str(code)] = finder
        (code / "added.py").write_text("MARKER = 'ADDED'\n")
        os.utime(code, (STAMP, STAMP))
        # Python 3.15's missing-module traceback formatter tries to reimport
        # the removed parent. Keep this discovery probe independent of logging.
        with patch("src.plugins.loader.logger.exception"):
            plugin = self.loader(code.parent).load_plugin("qa_cache_added")
        self.assertIsNotNone(plugin)
        self.assertEqual(plugin.fetch_data().data["marker"], "ADDED")

    def test_encoding_and_future_annotations_survive_current_source_execution(self):
        source = (
            b"# coding: latin-1\nfrom __future__ import annotations\n"
            + code_for("qa_cache_encoding").replace(b"'OLD'", b"'caf\xe9OLD'")
            + b"def annotated(value: Missing) -> Missing: return value\n"
        )
        code = data_plugin(self.root, "qa_cache_encoding", source)
        prime(code / "__init__.py")
        loader = self.loader(self.root)
        loader.load_plugin("qa_cache_encoding")
        replace_same_key(code / "__init__.py", b"OLD", b"NEW")
        self.assertEqual(loader.reload_plugin("qa_cache_encoding").fetch_data().data["marker"], "caféNEW")
        self.assertEqual(
            sys.modules["plugins.qa_cache_encoding"].annotated.__annotations__,
            {"value": "Missing", "return": "Missing"},
        )

    def test_unrelated_cached_import_and_custom_plugin_finder_keep_their_semantics(self):
        outside = self.root / "outside"
        outside.mkdir()
        other = outside / "qa_outside.py"
        other.write_text("VALUE = 'OLD'\n")
        prime(other)
        replace_same_key(other, b"'OLD'", b"'NEW'")
        code = data_plugin(self.root / "plugins", "qa_cache_scoped")
        virtual = code / "virtual"
        virtual.mkdir()
        (virtual / "qa_virtual_helper.py").write_text("VALUE = 'FILE'\n")

        class InlineLoader:
            def create_module(self, spec):
                return None

            def exec_module(self, module):
                module.VALUE = "VIRTUAL"

        class InlineFinder:
            def find_spec(self, fullname, target=None):
                if fullname == "qa_virtual_helper":
                    return importlib.machinery.ModuleSpec(fullname, InlineLoader())
                return None

        class CustomFileFinder(InlineFinder, importlib.machinery.FileFinder):
            def __init__(self):
                importlib.machinery.FileFinder.__init__(self, str(virtual))

        class CustomSourceLoader(importlib.machinery.SourceFileLoader):
            def get_code(self, fullname):
                return self.source_to_code(b"VALUE = 'VIRTUAL'\n", self.get_filename(fullname))

        sys.path[:0] = [str(outside), str(virtual)]
        loader = self.loader(code.parent)
        configured = importlib.machinery.FileFinder(
            str(virtual), (CustomSourceLoader, importlib.machinery.SOURCE_SUFFIXES)
        )
        for finder in (InlineFinder(), CustomFileFinder(), configured):
            with self.subTest(finder=type(finder).__name__):
                sys.path_importer_cache[str(virtual)] = finder
                sys.modules.pop("qa_virtual_helper", None)
                sys.modules.pop("qa_outside", None)
                self.assertIsNotNone(loader.reload_plugin("qa_cache_scoped"))
                self.assertEqual(importlib.import_module("qa_outside").VALUE, "OLD")
                self.assertEqual(importlib.import_module("qa_virtual_helper").VALUE, "VIRTUAL")
                if isinstance(finder, importlib.machinery.FileFinder):
                    self.assertIn("qa_virtual_helper", [item.name for item in pkgutil.iter_modules([str(virtual)])])

    def test_package_resource_reader_survives_fresh_source_loading(self):
        source = code_for("qa_cache_resources").replace(
            b"from src.plugins.base",
            b"import sys\nfrom importlib import resources\nfrom src.plugins.base",
        ).replace(
            b"'marker':MARKER",
            b"'marker':resources.files(sys.modules[__name__]).joinpath('payload.txt').read_text()+MARKER",
        )
        code = data_plugin(self.root, "qa_cache_resources", source)
        (code / "payload.txt").write_text("PAYLOAD:")
        manifest = json.loads((code / "manifest.json").read_text())
        manifest["data_files"] = ["payload.txt"]
        (code / "manifest.json").write_text(json.dumps(manifest))
        prime(code / "__init__.py")
        loader = self.loader(self.root)
        self.assertEqual(loader.load_plugin("qa_cache_resources").fetch_data().data["marker"], "PAYLOAD:OLD")
        replace_same_key(code / "__init__.py", b"'OLD'", b"'NEW'")
        self.assertEqual(loader.reload_plugin("qa_cache_resources").fetch_data().data["marker"], "PAYLOAD:NEW")

    def test_relative_bytecode_only_module_keeps_standard_sourceless_loading(self):
        source = code_for("qa_cache_sourceless").replace(b"MARKER = 'OLD'", b"from .byte_only import MARKER")
        code = data_plugin(self.root, "qa_cache_sourceless", source)
        leaf = code / "byte_only.py"
        leaf.write_text("MARKER = 'BYTECODE'\n")
        py_compile.compile(str(leaf), cfile=str(code / "byte_only.pyc"), doraise=True)
        leaf.unlink()
        self.assertEqual(
            self.loader(code.parent).load_plugin("qa_cache_sourceless").fetch_data().data["marker"], "BYTECODE"
        )

    def test_http_update_executes_the_successfully_checked_out_source(self):
        identity = "qa_cache_http"
        external = sources.get_external_plugins_dir()
        code = data_plugin(external, identity)
        prime(code / "__init__.py")
        _, registry = self.registry(identity, code)
        origin = self.root / "origin"
        shutil.copytree(code, origin, ignore=shutil.ignore_patterns("__pycache__"))
        git(origin, "init", "--quiet", "--initial-branch=main")
        commit(origin)
        git(code, "init", "--quiet", "--initial-branch=main")
        commit(code)
        git(code, "remote", "add", "origin", origin.as_uri())
        (origin / "__init__.py").write_bytes(code_for(identity, "NEW"))
        incoming = commit(origin)
        real_clone = sources.clone_or_update_repo

        def collide(*args, **kwargs):
            result = real_clone(*args, **kwargs)
            if result[0]:
                os.utime(code / "__init__.py", (STAMP + 0.5, STAMP + 0.5))
            return result

        app = FastAPI()
        app.include_router(routes.router)
        with (
            patch.object(routes, "_plugin_service", return_value=PluginService(registry=registry)),
            patch.object(sources, "clone_or_update_repo", side_effect=collide),
        ):
            response = TestClient(app).post(f"/plugins/{identity}/update")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(sources.get_local_head_sha(code), incoming)
        self.assertIn(b"'NEW'", (code / "__init__.py").read_bytes())
        self.assertEqual(registry.get_plugin(identity).fetch_data().data["marker"], "NEW")

    def test_output_import_failure_rolls_back_instead_of_accepting_cached_good_code(self):
        identity = "recording_output"
        external = sources.get_external_plugins_dir()
        code = external / identity
        shutil.copytree(Path(__file__).parent / "fixtures/plugins/recording_output", code)
        init = code / "__init__.py"
        init.write_bytes(
            init.read_bytes().replace(
                b"from __future__ import annotations\n",
                b"from __future__ import annotations\nGENERATION = 'OLD'\n",
                1,
            )
        )
        prime(init)
        manager, registry = self.registry(identity, code)
        origin = self.root / "origin"
        shutil.copytree(code, origin, ignore=shutil.ignore_patterns("__pycache__"))
        git(origin, "init", "--quiet", "--initial-branch=main")
        previous = commit(origin)
        git(code, "init", "--quiet", "--initial-branch=main")
        commit(code)
        git(code, "remote", "add", "origin", origin.as_uri())
        (origin / "__init__.py").write_bytes(init.read_bytes().replace(b"'OLD'", b"BOGUS", 1))
        refused = commit(origin)
        real_clone = sources.clone_or_update_repo

        def collide(*args, **kwargs):
            result = real_clone(*args, **kwargs)
            if result[0]:
                os.utime(init, (STAMP + 0.5, STAMP + 0.5))
            return result

        with patch.object(sources, "clone_or_update_repo", side_effect=collide):
            result = sources.update_external_plugin(
                identity, external, reload=lambda: reload_installed_copy(registry, identity)
            )
        self.assertEqual((result.ok, result.stage), (False, "rolled_back"))
        self.assertEqual(sources.get_local_head_sha(code), previous)
        self.assertEqual(manager.get_refused_plugin_update(identity)["sha"], refused)
        self.assertEqual(sys.modules[f"plugins.{identity}"].GENERATION, "OLD")


if __name__ == "__main__":
    unittest.main()
