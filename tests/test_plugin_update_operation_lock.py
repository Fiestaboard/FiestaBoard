"""An older refused output update cannot undo another accepted operation."""

import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from src.config_manager import ConfigManager
from src.outputs.registry import output_registry
from src.plugins import sources
from src.plugins.registry import PluginRegistry
from src.plugins.service import reload_installed_copy

PLUGIN_ID = "recording_output"
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


def commit(path, message):
    git(path, "add", "-A")
    git(path, "commit", "--quiet", "-m", message)
    return git(path, "rev-parse", "HEAD")


def fence_available(plugin_id):
    """Probe from another thread: a reentrant fence must not look free."""
    result = []

    def probe():
        lock = sources._dir_lock(plugin_id)
        available = lock.acquire(blocking=False)
        result.append(available)
        if available:
            lock.release()

    worker = threading.Thread(target=probe)
    worker.start()
    worker.join(3)
    if worker.is_alive() or len(result) != 1:
        raise AssertionError("directory-fence probe did not complete")
    return result[0]


@contextmanager
def installed_output():
    with (
        tempfile.TemporaryDirectory() as directory,
        patch.dict(os.environ, {"FIESTABOARD_DATA_DIR": directory}),
        patch.object(ConfigManager, "_instance", None),
        patch("src.plugins.sources._validate_git_url", return_value=(True, "")),
    ):
        root = Path(directory)
        origin = root / "origin"
        shutil.copytree(Path(__file__).parent / "fixtures/plugins/recording_output", origin)
        git(origin, "init", "--quiet", "--initial-branch=main")
        base = commit(origin, "initial")
        external = sources.get_external_plugins_dir()
        assert sources.clone_or_update_repo(origin.as_uri(), PLUGIN_ID, external_dir=external) == (True, "")
        manager = ConfigManager(str(root / "config.json"))
        builtin = root / "builtin"
        builtin.mkdir()
        registry = PluginRegistry(builtin)
        with patch.object(registry, "_auto_install_seeded_outputs", return_value=[]):
            registry.initialize()
        assert registry.get_plugin(PLUGIN_ID) is not None
        try:
            yield root, origin, external, base, manager, registry
        finally:
            registry._loader.unload_plugin(PLUGIN_ID)
            output_registry().remove_plugin(PLUGIN_ID)


class PluginUpdateOperationLock(unittest.TestCase):
    def test_failed_update_cannot_roll_back_a_newer_accepted_update(self):
        self.check_competing_rollback(install_over=False)

    def test_refused_reinstall_cannot_roll_back_a_newer_accepted_update(self):
        self.check_competing_rollback(install_over=True)

    def test_queued_failed_update_uses_the_previous_commit_after_rollback(self):
        self.check_competing_rollback(install_over=False, second_fails=True)

    def check_competing_rollback(self, *, install_over, second_fails=False):
        with installed_output() as (_, origin, external, base, manager, registry):
            healthy = (origin / "__init__.py").read_text()
            manifest = json.loads((origin / "manifest.json").read_text())
            if install_over:
                manifest["output"]["output_api"] = 2
                (origin / "manifest.json").write_text(json.dumps(manifest))
            else:
                (origin / "__init__.py").write_text("raise ImportError('synthetic refused release')\n")
            rejected = commit(origin, "refused release")
            paused = threading.Event()
            resume = threading.Event()
            outcomes = {}
            real_verify = sources.verify_installed_plugin
            real_dir_lock = sources._dir_lock
            second_waiting = threading.Event()

            def notify_fence(identity):
                if threading.current_thread() is second:
                    second_waiting.set()
                return real_dir_lock(identity)

            def pause_after_failure(error):
                if not paused.is_set():
                    if not error:
                        raise AssertionError("the first release was unexpectedly usable")
                    paused.set()
                    if not resume.wait(5):
                        raise AssertionError("failed-operation barrier was not resumed")

            def reload_first():
                error = reload_installed_copy(registry, PLUGIN_ID)
                pause_after_failure(error)
                return error

            def verify_first(identity, path):
                result = real_verify(identity, path)
                if install_over and threading.current_thread() is first:
                    pause_after_failure(not result[0])
                return result

            def run_first():
                try:
                    if install_over:
                        outcomes["first"] = sources.install_git_plugin(
                            origin.as_uri(), plugin_id=PLUGIN_ID, external_dir=external
                        )
                    else:
                        outcomes["first"] = sources.update_external_plugin(PLUGIN_ID, external, reload=reload_first)
                except BaseException as exc:
                    outcomes["first"] = exc

            def run_second():
                try:
                    outcomes["second"] = sources.update_external_plugin(
                        PLUGIN_ID, external, reload=lambda: reload_installed_copy(registry, PLUGIN_ID)
                    )
                except BaseException as exc:
                    outcomes["second"] = exc

            first = threading.Thread(target=run_first, daemon=True)
            second = threading.Thread(target=run_second, daemon=True)
            with (
                patch.object(sources, "verify_installed_plugin", side_effect=verify_first),
                patch.object(sources, "_dir_lock", side_effect=notify_fence),
            ):
                first.start()
                try:
                    self.assertTrue(paused.wait(5), "first operation never reached its actual failure")
                    (origin / "__init__.py").write_text(
                        "raise ImportError('synthetic second refused release')\n" if second_fails else healthy
                    )
                    manifest["version"] = "0.3.0"
                    manifest["output"]["output_api"] = 1
                    (origin / "manifest.json").write_text(json.dumps(manifest))
                    incoming = commit(origin, "replacement")
                    # Force the damaging baseline interleave if its fence is
                    # absent. With a fence, let the second request queue instead.
                    # Final expectations below do not derive from this probe.
                    unfenced = fence_available(PLUGIN_ID)
                    second.start()
                    if unfenced:
                        second.join(5)
                        self.assertFalse(second.is_alive(), "unfenced competing update did not finish")
                    else:
                        self.assertTrue(second_waiting.wait(5), "second update never reached the directory fence")
                finally:
                    resume.set()
                    first.join(6)
                    if second.ident is not None:
                        second.join(6)
            self.assertFalse(first.is_alive())
            self.assertFalse(second.is_alive())
            self.assertNotIsInstance(outcomes.get("first"), BaseException)
            self.assertNotIsInstance(outcomes.get("second"), BaseException)
            if install_over:
                self.assertFalse(outcomes["first"][0])
                self.assertIn("rolled back", outcomes["first"][1])
            else:
                self.assertEqual((outcomes["first"].ok, outcomes["first"].stage), (False, "rolled_back"))
            if second_fails:
                self.assertEqual((outcomes["second"].ok, outcomes["second"].stage), (False, "rolled_back"))
            else:
                self.assertTrue(outcomes["second"].ok)
            self.assertNotEqual(base, incoming)
            with self.subTest(state="checkout"):
                self.assertEqual(sources.get_local_head_sha(external / PLUGIN_ID), base if second_fails else incoming)
            with self.subTest(state="loaded version"):
                self.assertEqual(
                    getattr(registry._loader.get_manifest(PLUGIN_ID), "version", None),
                    "0.1.0" if second_fails else "0.3.0",
                )
            with self.subTest(state="refusal provenance"):
                self.assertEqual(
                    manager.get_refused_plugin_update(PLUGIN_ID)["sha"], incoming if second_fails else rejected
                )

    def test_other_plugin_can_install_while_output_reload_is_paused(self):
        with installed_output() as (root, _, external, _, _, registry):
            paused = threading.Event()
            resume = threading.Event()
            result = []

            def reload():
                paused.set()
                if not resume.wait(5):
                    raise AssertionError("reload was not resumed")
                return reload_installed_copy(registry, PLUGIN_ID)

            worker = threading.Thread(
                target=lambda: result.append(sources.update_external_plugin(PLUGIN_ID, external, reload=reload)),
                daemon=True,
            )
            worker.start()
            try:
                self.assertTrue(paused.wait(5))
                other = root / "other"
                other.mkdir()
                (other / "manifest.json").write_text(
                    json.dumps({"id": "healthy_other", "name": "Other", "version": "1.0.0"})
                )
                (other / "__init__.py").write_text("")
                git(other, "init", "--quiet", "--initial-branch=main")
                other_sha = commit(other, "other")
                self.assertEqual(
                    sources.install_git_plugin(other.as_uri(), "healthy_other", external_dir=external), (True, "")
                )
                self.assertEqual(sources.get_local_head_sha(external / "healthy_other"), other_sha)
            finally:
                resume.set()
                worker.join(6)
            self.assertFalse(worker.is_alive())
            self.assertTrue(result[0].ok)

    def test_operation_fence_is_released_after_fetch_failure_and_reload_exception(self):
        with installed_output() as (_, _, external, _, _, _):
            with patch.object(sources, "clone_or_update_repo", return_value=(False, "synthetic fetch failure")):
                outcome = sources.update_external_plugin(PLUGIN_ID, external)
            self.assertEqual((outcome.ok, outcome.stage), (False, "fetch"))
            self.assertTrue(fence_available(PLUGIN_ID))

            def crash():
                raise RuntimeError("synthetic reload exception")

            with self.assertRaisesRegex(RuntimeError, "synthetic reload exception"):
                sources.update_external_plugin(PLUGIN_ID, external, reload=crash)
            self.assertTrue(fence_available(PLUGIN_ID))


if __name__ == "__main__":
    unittest.main()
