"""Caught uninstall failures preserve durable settings, code and live state."""

import errno
import json
import shutil
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.atomic_io as atomic_io
import src.plugins.loader as loader_module
from src.config_manager import ConfigManager
from src.plugins.errors import PluginOperationFailed, PluginOperationRejected
from src.plugins.routes import router
from src.plugins.service import PluginService
from src.plugins.sources import _dir_lock
from tests import test_plugin_loader as loader_fixtures
from tests import test_plugin_uninstall_cleanup_ownership as fixtures


class UninstallTransaction(unittest.TestCase):
    def service(self, manager, registry):
        return PluginService(registry=registry, config_manager=manager)

    def test_staging_refusal_preserves_code_live_state_and_settings(self):
        with fixtures.installed_plugin() as (manager, registry, code, path):
            original = registry.plugins
            before = path.read_bytes()
            generation = manager.config_generation
            oauth = Mock()
            with patch("src.oauth.service.get_oauth_service", return_value=oauth), fixtures.join_cleanup_threads():
                with patch(
                    "pathlib.Path.rename", side_effect=PermissionError(errno.EACCES, "synthetic staging refusal")
                ):
                    with self.assertRaises(OSError):
                        self.service(manager, registry).uninstall("qa_uninstall")
            self.assertTrue(code.exists())
            self.assertEqual(registry.plugins, original)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(manager.config_generation, generation)
            self.assertTrue(all(p.cleanup_calls == 0 for p in original.values()))
            oauth.forget.assert_not_called()

    def test_atomic_save_failure_restores_code_and_is_retryable(self):
        with fixtures.installed_plugin() as (manager, registry, code, path):
            original = registry.plugins
            before = path.read_bytes()
            generation = manager.config_generation
            service = self.service(manager, registry)
            module_before = sys.modules.get("plugins.qa_uninstall")
            code_before = (code / "__init__.py").read_bytes()
            oauth = Mock()
            with patch("src.oauth.service.get_oauth_service", return_value=oauth), fixtures.join_cleanup_threads():
                with patch("src.atomic_io.os.replace", side_effect=OSError(errno.ENOSPC, "synthetic save failure")):
                    with self.assertRaises(OSError):
                        service.uninstall("qa_uninstall")
                self.assertTrue(code.is_dir())
                self.assertEqual(registry.plugins, original)
                self.assertEqual(manager.get_all_plugin_configs(), json.loads(before)["plugins"])
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual(manager.config_generation, generation)
                self.assertIs(sys.modules.get("plugins.qa_uninstall"), module_before)
                self.assertEqual((code / "__init__.py").read_bytes(), code_before)
                self.assertTrue(all(p.cleanup_calls == 0 for p in original.values()))
                oauth.forget.assert_not_called()
                service.uninstall("qa_uninstall")
            self.assertFalse(code.exists())
            self.assertTrue(manager.is_plugin_removed("qa_uninstall"))
            self.assertTrue(all(p.cleanup_calls == 1 for p in original.values()))

    def test_purge_and_tombstone_commit_in_one_write_before_retirement(self):
        with fixtures.installed_plugin() as (manager, registry, code, path):
            manager.set_plugin_config("qa_uninstall_neighbor", {"enabled": False, "label": "KEEP"})
            manager.mark_plugin_removed("qa_old")
            observations = []
            retire = loader_module.retire_plugin_object
            replace = atomic_io.os.replace
            writes = []

            def trace_retire(identity, plugin, *, what):
                disk = json.loads(path.read_text())
                observations.append((set(disk["plugins"]), set(disk["removed_plugins"])))
                retire(identity, plugin, what=what)

            def count_replace(source, destination):
                if Path(destination) == path:
                    writes.append(1)
                return replace(source, destination)

            generation = manager.config_generation
            with patch("src.oauth.service.get_oauth_service", return_value=Mock()), fixtures.join_cleanup_threads():
                with (
                    patch("src.plugins.registry.retire_plugin_object", trace_retire),
                    patch("src.plugins.loader.retire_plugin_object", trace_retire),
                    patch("src.atomic_io.os.replace", side_effect=count_replace),
                ):
                    self.service(manager, registry).uninstall("qa_uninstall")
            self.assertEqual(len(writes), 1)
            self.assertEqual(manager.config_generation, generation + 1)
            self.assertEqual(observations, [({"qa_uninstall_neighbor"}, {"qa_old", "qa_uninstall"})] * 3)
            self.assertFalse(code.exists())
            self.assertEqual(manager.get_plugin_config("qa_uninstall_neighbor"), {"enabled": False, "label": "KEEP"})

    def test_tombstone_save_failure_is_an_http_failure_without_partial_purge(self):
        with fixtures.installed_plugin() as (manager, registry, code, path):
            before = path.read_bytes()
            replace = atomic_io.os.replace
            rejected = []

            def fail_config(source, destination):
                marker = "qa_uninstall" in json.loads(Path(source).read_text()).get("removed_plugins", [])
                if Path(destination) == path and marker:
                    rejected.append(1)
                    raise OSError(errno.ENOSPC, "synthetic tombstone save failure")
                return replace(source, destination)

            app = FastAPI()
            app.include_router(router)
            with (
                patch("src.plugins.routes._plugin_service", return_value=self.service(manager, registry)),
                patch("src.plugins.routes._require_plugin_system"),
                patch("src.oauth.service.get_oauth_service", return_value=Mock()),
                TestClient(app, raise_server_exceptions=False) as client,
                fixtures.join_cleanup_threads(),
                patch("src.atomic_io.os.replace", side_effect=fail_config),
            ):
                response = client.delete("/plugins/qa_uninstall/uninstall")
            self.assertGreaterEqual(response.status_code, 400)
            self.assertEqual(len(rejected), 1, "combined tombstone write was not actually faulted")
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(manager.get_all_plugin_configs(), json.loads(before)["plugins"])
            self.assertTrue(code.exists())

    def test_rejected_deletions_cannot_escape_via_unrelated_save_or_cold_load(self):
        with fixtures.installed_plugin() as (manager, registry, _, path):
            manager.set_plugin_config("qa_other", {"enabled": False, "label": "KEEP"})
            expected = manager.get_all_plugin_configs()
            with patch("src.oauth.service.get_oauth_service", return_value=Mock()), fixtures.join_cleanup_threads():
                with patch("src.atomic_io.os.replace", side_effect=OSError(errno.ENOSPC, "synthetic save failure")):
                    with self.assertRaises(OSError):
                        self.service(manager, registry).uninstall("qa_uninstall")
            self.assertTrue(manager.set_general({"instance_name": "accepted-unrelated-change"}))
            with patch.object(ConfigManager, "_instance", None):
                cold = ConfigManager(str(path))
                self.assertIsNot(cold, manager)
                self.assertEqual(cold.get_all_plugin_configs(), expected)
                self.assertFalse(cold.is_plugin_removed("qa_uninstall"))

    def test_rollback_failure_keeps_backup_and_reports_recovery_needed(self):
        with fixtures.installed_plugin() as (manager, registry, code, path):
            before = path.read_bytes()
            rename = Path.rename
            error = None

            def refuse_restore(source, destination):
                if Path(destination) == code:
                    raise PermissionError(errno.EACCES, "synthetic rollback refusal")
                return rename(source, destination)

            with patch("src.oauth.service.get_oauth_service", return_value=Mock()), fixtures.join_cleanup_threads():
                with (
                    patch("pathlib.Path.rename", refuse_restore),
                    patch("src.atomic_io.os.replace", side_effect=OSError(errno.ENOSPC, "synthetic save failure")),
                ):
                    try:
                        self.service(manager, registry).uninstall("qa_uninstall")
                    except Exception as exc:
                        error = exc
            self.assertIsInstance(error, PluginOperationFailed)
            self.assertIn("rollback", str(error).lower())
            self.assertEqual(path.read_bytes(), before)
            self.assertTrue(list(code.parent.rglob("manifest.json")), "rollback copy was lost")
            self.assertIsNotNone(registry.get_plugin("qa_uninstall"))
            with self.assertRaises(PluginOperationFailed):
                self.service(manager, registry).uninstall("qa_uninstall")

    def test_rollback_never_overwrites_an_unexpected_replacement(self):
        with fixtures.installed_plugin() as (manager, registry, code, path):
            before = path.read_bytes()

            def replace_appeared(source, destination):
                code.mkdir(exist_ok=True)
                (code / "replacement.txt").write_text("KEEP REPLACEMENT")
                raise OSError(errno.ENOSPC, "synthetic save failure")

            error = None
            with patch("src.oauth.service.get_oauth_service", return_value=Mock()), fixtures.join_cleanup_threads():
                with patch("src.atomic_io.os.replace", side_effect=replace_appeared):
                    try:
                        self.service(manager, registry).uninstall("qa_uninstall")
                    except Exception as exc:
                        error = exc
            self.assertIsInstance(error, PluginOperationFailed)
            self.assertEqual((code / "replacement.txt").read_text(), "KEEP REPLACEMENT")
            self.assertEqual(path.read_bytes(), before)
            self.assertTrue(any(p.parent != code for p in code.parent.rglob("manifest.json")))

    def test_postcommit_cache_cleanup_failure_does_not_undo_uninstall(self):
        with fixtures.installed_plugin() as (manager, registry, code, _):
            error = None
            with patch("src.oauth.service.get_oauth_service", return_value=Mock()), fixtures.join_cleanup_threads():
                with (
                    self.assertLogs("src.plugins.uninstall", level="WARNING") as logs,
                    patch(
                        "shutil.rmtree", side_effect=PermissionError(errno.EACCES, "synthetic cache cleanup refusal")
                    ),
                ):
                    try:
                        self.service(manager, registry).uninstall("qa_uninstall")
                    except Exception as exc:
                        error = exc
            self.assertIsNone(error)
            self.assertFalse(code.exists())
            self.assertEqual(registry.plugins, {})
            self.assertTrue(manager.is_plugin_removed("qa_uninstall"))
            self.assertEqual(manager.get_all_plugin_configs(), {})
            self.assertTrue(list(code.parent.rglob("manifest.json")), "pending cleanup cache was discarded")
            self.assertTrue(any("cleanup is pending" in line for line in logs.output))

    def test_an_already_missing_code_directory_can_be_uninstalled(self):
        with fixtures.installed_plugin() as (manager, registry, code, _):
            shutil.rmtree(code)
            with patch("src.oauth.service.get_oauth_service", return_value=Mock()), fixtures.join_cleanup_threads():
                self.service(manager, registry).uninstall("qa_uninstall")
            self.assertEqual(registry.plugins, {})
            self.assertEqual(manager.get_all_plugin_configs(), {})
            self.assertTrue(manager.is_plugin_removed("qa_uninstall"))

    def test_staged_uninstall_evicts_bare_modules_before_reinstall(self):
        with fixtures.installed_plugin() as (manager, registry, code, _):
            loader_fixtures._create_flattened_plugin_dir(code.parent, "qa_uninstall", "OLD")
            plugin = registry.reload_plugin("qa_uninstall")
            self.assertEqual(plugin.fetch_data().data["marker"], "OLD")
            with patch("src.oauth.service.get_oauth_service", return_value=Mock()), fixtures.join_cleanup_threads():
                self.service(manager, registry).uninstall("qa_uninstall")
            self.assertFalse("qa_uninstall_impl" in sys.modules)
            self.assertFalse("qa_uninstall_sibling" in sys.modules)
            loader_fixtures._create_flattened_plugin_dir(code.parent, "qa_uninstall", "NEW")
            fresh = registry._loader.load_plugin("qa_uninstall")
            self.assertEqual(fresh.fetch_data().data["marker"], "NEW")
            registry._loader.unload_plugin("qa_uninstall")

    def test_directory_mutation_fence_stays_held_until_save_failure_is_rolled_back(self):
        with fixtures.installed_plugin() as (manager, registry, code, path):
            entered = threading.Event()
            checked = threading.Event()
            acquired = []

            def contender():
                if not entered.wait(3):
                    return
                lock = _dir_lock("qa_uninstall")
                got = lock.acquire(blocking=False)
                acquired.append(got)
                if got:
                    lock.release()
                checked.set()

            worker = threading.Thread(target=contender)
            worker.start()

            def fail_save(source, destination):
                if Path(destination) == path:
                    entered.set()
                    if not checked.wait(3):
                        raise AssertionError("directory contender did not run")
                    raise OSError(errno.ENOSPC, "synthetic save failure")
                raise AssertionError("unexpected replacement")

            try:
                with patch("src.oauth.service.get_oauth_service", return_value=Mock()), fixtures.join_cleanup_threads():
                    with patch("src.atomic_io.os.replace", side_effect=fail_save):
                        with self.assertRaises(OSError):
                            self.service(manager, registry).uninstall("qa_uninstall")
            finally:
                entered.set()
                worker.join(4)
            self.assertFalse(worker.is_alive())
            self.assertEqual(acquired, [False])
            self.assertTrue(code.exists())

    def test_service_does_not_purge_a_later_accepted_reinstall_config(self):
        with fixtures.installed_plugin() as (manager, registry, _, _):
            real_uninstall = registry.uninstall_external_plugin

            def uninstall_then_reconfigure(identity, **kwargs):
                result = real_uninstall(identity, **kwargs)
                manager.clear_plugin_removed(identity)
                manager.set_plugin_config(identity, {"enabled": True, "label": "REINSTALLED"})
                return result

            with patch("src.oauth.service.get_oauth_service", return_value=Mock()), fixtures.join_cleanup_threads():
                with patch.object(registry, "uninstall_external_plugin", side_effect=uninstall_then_reconfigure):
                    self.service(manager, registry).uninstall("qa_uninstall")
            self.assertEqual(manager.get_plugin_config("qa_uninstall"), {"enabled": True, "label": "REINSTALLED"})

    def test_oauth_forget_runs_after_commit_inside_the_directory_fence(self):
        with fixtures.installed_plugin() as (manager, registry, code, path):
            observations = []

            def forget(identity):
                acquired = []

                def contender():
                    lock = _dir_lock("qa_uninstall")
                    got = lock.acquire(blocking=False)
                    acquired.append(got)
                    if got:
                        lock.release()

                worker = threading.Thread(target=contender)
                worker.start()
                worker.join(3)
                self.assertFalse(worker.is_alive())
                self.assertEqual(len(acquired), 1)
                got = acquired[0]
                disk = json.loads(path.read_text())
                observations.append(
                    (identity, got, bool(disk["plugins"]), "qa_uninstall" in disk.get("removed_plugins", []))
                )

            oauth = Mock()
            oauth.forget.side_effect = forget
            with patch("src.oauth.service.get_oauth_service", return_value=oauth), fixtures.join_cleanup_threads():
                self.service(manager, registry).uninstall("qa_uninstall")
            self.assertCountEqual(
                observations,
                [
                    ("qa_uninstall:one", False, False, True),
                    ("qa_uninstall:two", False, False, True),
                    ("qa_uninstall", False, False, True),
                ],
            )
            self.assertFalse(code.exists())

    def test_postcommit_oauth_failure_does_not_restore_uninstalled_code(self):
        with fixtures.installed_plugin() as (manager, registry, code, _):
            oauth = Mock()
            oauth.forget.side_effect = OSError("synthetic OAuth store error")
            error = None
            with patch("src.oauth.service.get_oauth_service", return_value=oauth), fixtures.join_cleanup_threads():
                try:
                    self.service(manager, registry).uninstall("qa_uninstall")
                except Exception as exc:
                    error = exc
            self.assertIsInstance(error, PluginOperationFailed)
            self.assertIn("committed", str(error).lower())
            self.assertFalse(code.exists())
            self.assertEqual(manager.get_all_plugin_configs(), {})
            self.assertTrue(manager.is_plugin_removed("qa_uninstall"))
            self.assertEqual(registry.plugins, {})
            self.assertTrue(list(code.parent.rglob("manifest.json")), "postcommit recovery cache was lost")

    def test_cleanup_never_removes_a_replaced_staging_directory(self):
        with fixtures.installed_plugin() as (manager, registry, code, _):
            replacement = []

            def replace_stage(identity):
                if replacement:
                    return
                stages = list(code.parent.glob(".qa_uninstall.uninstall-*"))
                if not stages:
                    replacement.append((None, None))
                    return
                root = stages[0]
                retained = root.with_name(root.name + "-retained")
                root.rename(retained)
                root.mkdir()
                (root / "sentinel").write_text("UNRELATED REPLACEMENT")
                replacement.append((root, retained))

            oauth = Mock()
            oauth.forget.side_effect = replace_stage
            with patch("src.oauth.service.get_oauth_service", return_value=oauth), fixtures.join_cleanup_threads():
                self.service(manager, registry).uninstall("qa_uninstall")
            root, retained = replacement[0]
            self.assertIsNotNone(root, "no rollback cache was held through committed cleanup")
            self.assertTrue((root / "sentinel").exists(), "an unowned replacement cache was removed")
            self.assertEqual((root / "sentinel").read_text(), "UNRELATED REPLACEMENT")
            self.assertTrue((retained / "qa_uninstall" / "manifest.json").exists())
            self.assertTrue(manager.is_plugin_removed("qa_uninstall"))

    def test_unverified_source_path_cannot_remove_unrelated_directory(self):
        with fixtures.installed_plugin() as (manager, registry, code, path):
            original = registry.plugins
            before = path.read_bytes()
            unrelated = code.parent.parent / "unrelated"
            unrelated.mkdir()
            (unrelated / "sentinel").write_text("KEEP")
            registry.get_plugin_source("qa_uninstall").local_path = str(unrelated)
            with patch("src.oauth.service.get_oauth_service", return_value=Mock()), fixtures.join_cleanup_threads():
                with self.assertRaises(PluginOperationRejected):
                    self.service(manager, registry).uninstall("qa_uninstall")
            self.assertEqual((unrelated / "sentinel").read_text(), "KEEP")
            self.assertEqual(registry.plugins, original)
            self.assertEqual(path.read_bytes(), before)
            self.assertTrue(code.exists())

    def test_metadata_reader_after_failed_commit_sees_restored_live_state(self):
        with fixtures.installed_plugin() as (manager, registry, code, path):
            original = registry.get_plugin("qa_uninstall")
            expected = manager.get_plugin_config("qa_uninstall")
            entered = threading.Event()
            reader_started = threading.Event()
            observed = {}

            def read_metadata():
                if not entered.wait(3):
                    return
                reader_started.set()
                observed["plugin"] = registry.get_plugin("qa_uninstall")
                observed["code"] = code.exists()
                observed["config"] = manager.get_plugin_config("qa_uninstall")

            reader = threading.Thread(target=read_metadata)
            reader.start()

            def fail_commit(source, destination):
                if Path(destination) == path:
                    entered.set()
                    if not reader_started.wait(3):
                        raise AssertionError("metadata reader did not start")
                    raise OSError(errno.ENOSPC, "synthetic commit failure")
                raise AssertionError("unexpected replacement")

            try:
                with patch("src.oauth.service.get_oauth_service", return_value=Mock()), fixtures.join_cleanup_threads():
                    with patch("src.atomic_io.os.replace", side_effect=fail_commit):
                        with self.assertRaises(OSError):
                            self.service(manager, registry).uninstall("qa_uninstall")
            finally:
                entered.set()
                reader.join(4)
            self.assertFalse(reader.is_alive())
            self.assertIs(observed["plugin"], original)
            self.assertTrue(observed["code"])
            self.assertEqual(observed["config"], expected)

    def test_queued_uninstall_rechecks_new_board_usage_before_staging(self):
        self.check_queued_output_guard(unreadable=False)

    def test_queued_uninstall_refuses_when_acceptance_board_read_fails(self):
        self.check_queued_output_guard(unreadable=True)

    def check_queued_output_guard(self, *, unreadable):
        import src.plugins.registry as registry_module
        import src.settings.service as settings_module

        with fixtures.installed_plugin() as (manager, registry, code, path):
            registry._loader.get_manifest("qa_uninstall").plugin_type = "output"
            original = registry.plugins
            before = path.read_bytes()
            generation = manager.config_generation
            initial_read = threading.Event()
            outcome = []
            reads = []
            real_guard = registry_module.boards_using_output

            def observe_guard(identity):
                reads.append(identity)
                if len(reads) > 1 and unreadable:
                    raise OSError("synthetic acceptance settings failure")
                result = real_guard(identity)
                initial_read.set()
                return result

            def uninstall():
                try:
                    outcome.append(registry.uninstall_external_plugin("qa_uninstall"))
                except BaseException as exc:
                    outcome.append(exc)

            with patch.object(settings_module, "_settings_service", None):
                settings = settings_module.get_settings_service()
                settings.set_boards([{"id": "qa-board", "device_type": "flagship", "name": "QA board"}])
                worker = threading.Thread(target=uninstall)
                with patch.object(registry_module, "boards_using_output", side_effect=observe_guard):
                    with _dir_lock("qa_uninstall"):
                        worker.start()
                        self.assertTrue(initial_read.wait(3), "uninstall did not check the initial board state")
                        settings.set_boards(
                            [
                                {
                                    "id": "qa-board",
                                    "device_type": "flagship",
                                    "name": "QA board",
                                    "output": "qa_uninstall",
                                }
                            ]
                        )
                        # Board updates legitimately persist output defaults.
                        # The refused uninstall must preserve that accepted state.
                        before = path.read_bytes()
                        generation = manager.config_generation
                    worker.join(4)
            self.assertFalse(worker.is_alive())
            self.assertEqual(len(outcome), 1)
            self.assertIsInstance(outcome[0], list)
            self.assertTrue(outcome[0], "queued uninstall accepted the stale unused-output decision")
            self.assertIn("Could not confirm" if unreadable else "QA board", outcome[0][0])
            self.assertEqual(reads, ["qa_uninstall", "qa_uninstall"])
            self.assertTrue(code.exists())
            self.assertEqual(registry.plugins, original)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(manager.config_generation, generation)


if __name__ == "__main__":
    unittest.main()
