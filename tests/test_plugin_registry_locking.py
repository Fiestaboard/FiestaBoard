"""Concurrency tests for PluginRegistry/PluginLoader shared state (#1828).

PR #1809 moved plugin install/update work off the event loop and onto worker
threads (``asyncio.to_thread``), which removed the accidental serialization
the loop provided.  Registry mutations now run concurrently with request
handlers that iterate the same dicts, and two updates of the same plugin can
run git in the same directory at once.  These tests drive those exact
interleavings.
"""

import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import src.plugins.sources as sources
from src.plugins.base import PluginBase
from src.plugins.registry import PluginRegistry
from src.plugins.sources import clone_or_update_repo

# ── helpers ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_loader():
    """Create a mock PluginLoader (same shape as tests/test_plugin_registry.py)."""
    loader = MagicMock()
    loader.load_all_plugins.return_value = {}
    loader.load_errors = {}
    loader.get_manifest.return_value = None
    loader.reload_plugin.return_value = None
    return loader


@pytest.fixture
def registry(mock_loader):
    """Create a PluginRegistry with a mocked loader."""
    with patch("src.plugins.registry.PluginLoader", return_value=mock_loader):
        return PluginRegistry(plugins_dir=Path("/fake/plugins"))


def _plugin_stub(plugin_id: str, supports_triggers: bool = True) -> MagicMock:
    """A PluginBase-shaped stub with the attributes the read paths touch."""
    plugin = MagicMock(spec=PluginBase)
    plugin.plugin_id = plugin_id
    plugin.supports_triggers = supports_triggers
    plugin.enabled = True
    return plugin


def _run_concurrently(*fns, join_timeout: float = 60.0) -> list[BaseException]:
    """Run each callable on its own thread, released together by a barrier.

    Returns every exception raised in any thread (empty list = clean run).
    """
    errors: list[BaseException] = []
    errors_lock = threading.Lock()
    start = threading.Barrier(len(fns))

    def _wrap(fn):
        def _inner():
            try:
                start.wait(timeout=10)
                fn()
            except BaseException as exc:
                with errors_lock:
                    errors.append(exc)

        return _inner

    threads = [threading.Thread(target=_wrap(fn)) for fn in fns]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=join_timeout)
    return errors


@pytest.fixture
def fast_thread_switching():
    """Force very frequent thread switches so races interleave reliably."""
    previous = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    yield
    sys.setswitchinterval(previous)


def _seed_plugins(registry: PluginRegistry, count: int = 400) -> None:
    for i in range(count):
        pid = f"seed_{i}"
        registry._plugins[pid] = _plugin_stub(pid)
        registry._enabled[pid] = True


# ── registry iteration vs concurrent mutation ────────────────────────────────


def _churn_until(registry: PluginRegistry, stop: threading.Event) -> None:
    """Mutate ``registry._plugins`` for as long as the reader is running.

    Same dict operations install_from_registry/uninstall perform, driven
    directly so the interleaving does not depend on git or the loader.  Keys
    are added in a batch before being removed so the dict's size actually
    differs from the reader's snapshot for a meaningful window.
    """
    stub = _plugin_stub("churn")
    while not stop.is_set():
        for i in range(10):
            registry._plugins[f"x_{i}"] = stub
        for i in range(10):
            del registry._plugins[f"x_{i}"]


def test_list_plugins_survives_concurrent_mutation(registry, fast_thread_switching):
    """GET /plugins iterating while an install registers a plugin must not
    raise ``RuntimeError: dictionary changed size during iteration``."""
    _seed_plugins(registry)
    stop = threading.Event()

    def reader():
        try:
            for _ in range(300):
                registry.list_plugins()
        finally:
            stop.set()

    errors = _run_concurrently(reader, lambda: _churn_until(registry, stop))
    assert errors == [], f"concurrent list_plugins/mutation raised: {errors!r}"


def test_trigger_plugins_survives_concurrent_mutation(registry, fast_thread_switching):
    """The trigger_plugins property must tolerate a concurrent install/uninstall."""
    _seed_plugins(registry)
    stop = threading.Event()

    def reader():
        try:
            for _ in range(300):
                _ = registry.trigger_plugins
        finally:
            stop.set()

    errors = _run_concurrently(reader, lambda: _churn_until(registry, stop))
    assert errors == [], f"concurrent trigger_plugins/mutation raised: {errors!r}"


# ── per-plugin-directory git serialization ───────────────────────────────────


class _ConcurrencyProbe:
    """subprocess.run stand-in that records how many calls overlap in time."""

    def __init__(self, hold_seconds: float):
        self.hold_seconds = hold_seconds
        self._lock = threading.Lock()
        self.current = 0
        self.max_seen = 0

    def __call__(self, *args, **kwargs):
        with self._lock:
            self.current += 1
            self.max_seen = max(self.max_seen, self.current)
        time.sleep(self.hold_seconds)
        with self._lock:
            self.current -= 1
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result


def _run_repo_ops(plugin_ids: list[str], external_dir: Path, probe) -> list:
    """Call clone_or_update_repo for each id on its own thread, simultaneously."""
    results = []
    results_lock = threading.Lock()

    def _op(plugin_id):
        def _call():
            outcome = clone_or_update_repo("", plugin_id, external_dir=external_dir)
            with results_lock:
                results.append(outcome)

        return _call

    with patch.object(sources.subprocess, "run", probe):
        errors = _run_concurrently(*[_op(pid) for pid in plugin_ids])
    assert errors == [], f"clone_or_update_repo raised: {errors!r}"
    return results


def test_concurrent_same_plugin_repo_ops_serialize(tmp_path):
    """Two updates of the same plugin must never run git in its directory at
    the same time (index.lock contention -> 500s)."""
    (tmp_path / "sameplugin" / ".git").mkdir(parents=True)
    probe = _ConcurrencyProbe(hold_seconds=0.2)

    results = _run_repo_ops(["sameplugin", "sameplugin"], tmp_path, probe)

    assert results == [(True, ""), (True, "")]
    assert probe.max_seen == 1, f"same-directory git ops overlapped (max concurrency {probe.max_seen})"


def test_different_plugin_repo_ops_parallel(tmp_path):
    """Serialization is per plugin directory: distinct plugins stay parallel."""
    (tmp_path / "aaa" / ".git").mkdir(parents=True)
    (tmp_path / "bbb" / ".git").mkdir(parents=True)
    probe = _ConcurrencyProbe(hold_seconds=0.3)

    results = _run_repo_ops(["aaa", "bbb"], tmp_path, probe)

    assert results == [(True, ""), (True, "")]
    assert probe.max_seen == 2, "different-plugin git ops were over-serialized"


# ── public replacement for api_server's direct _update_status.pop ────────────


def test_clear_update_status_removes_cached_flag(registry):
    registry._update_status["foo"] = True
    registry.clear_update_status("foo")
    assert registry.get_update_status() == {}
    # Clearing an id with no cached status is a no-op, not an error.
    registry.clear_update_status("missing")


# ── #1854 review follow-ups ──────────────────────────────────────────────────
#
# Bounded-time concurrency probes.  Each test drives a deterministic
# interleaving with Events; the only timing involved is a generous upper
# bound on operations that must not block.


def _call_on_thread(fn):
    """Run *fn* on a daemon thread; return (thread, done_event, results)."""
    done = threading.Event()
    result: list = []

    def _run():
        result.append(fn())
        done.set()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t, done, result


def test_blocking_instance_cleanup_does_not_stall_readers(registry):
    """delete_instance must not run plugin-authored cleanup() under the
    registry lock: a wedged cleanup (e.g. HA MQTT loop_stop joining a network
    thread) would otherwise stall every render and plugin listing."""
    cleanup_entered = threading.Event()
    cleanup_release = threading.Event()

    stub = _plugin_stub("wedge")

    def _wedged_cleanup():
        cleanup_entered.set()
        assert cleanup_release.wait(timeout=30)

    stub.cleanup.side_effect = _wedged_cleanup

    key = registry.make_instance_key("wedge", "inst")
    registry._plugins["wedge"] = _plugin_stub("wedge")
    registry._plugins[key] = stub
    registry._enabled[key] = True
    registry._configs[key] = {}

    try:
        _del_thread, del_done, _ = _call_on_thread(lambda: registry.delete_instance("wedge", "inst"))
        assert cleanup_entered.wait(timeout=5), "cleanup() was never invoked"

        _read_thread, read_done, read_result = _call_on_thread(registry.list_plugins)
        assert read_done.wait(timeout=2), (
            "list_plugins blocked behind a wedged plugin cleanup — cleanup ran under the registry lock"
        )
        assert isinstance(read_result[0], list)
    finally:
        cleanup_release.set()
    assert del_done.wait(timeout=5)


def test_uninstall_directory_removal_holds_the_plugin_dir_lock(registry, mock_loader, tmp_path):
    """uninstall must take the same per-directory lock as clone_or_update_repo
    so an overlapping update + uninstall of one plugin serialize instead of
    racing rmtree against git."""
    source = MagicMock()
    source.source_type = "external"
    source.local_path = str(tmp_path / "victim")
    mock_loader.get_source.return_value = source

    remove_called = threading.Event()

    with (
        patch("src.plugins.registry.remove_external_plugin") as remove_mock,
        patch("src.config_manager.get_config_manager", return_value=MagicMock()),
    ):
        remove_mock.side_effect = lambda path: (remove_called.set(), True)[1]

        # Simulate an in-flight update of the same plugin holding its lock.
        dir_lock = sources._dir_lock("victim")
        dir_lock.acquire()
        try:
            _t, done, result = _call_on_thread(lambda: registry.uninstall_external_plugin("victim"))
            assert not remove_called.wait(timeout=0.3), (
                "remove_external_plugin ran while another thread held the plugin's directory lock"
            )
        finally:
            dir_lock.release()

        assert done.wait(timeout=5)
        assert remove_called.is_set()
        assert result[0] == []


def test_registry_lock_blocks_readers_while_a_mutator_holds_it(registry):
    """Mutual exclusion, proven end-to-end: a mutator paused inside the lock
    (validate_config runs under it) blocks list_plugins until it releases."""
    entered = threading.Event()
    release = threading.Event()

    stub = _plugin_stub("gate")

    def _paused_validate(config):
        entered.set()
        assert release.wait(timeout=30)
        return []

    stub.validate_config.side_effect = _paused_validate
    stub._validate_refresh_seconds.return_value = []
    registry._plugins["gate"] = stub

    _writer, writer_done, _ = _call_on_thread(lambda: registry.set_plugin_config("gate", {"a": 1}))
    assert entered.wait(timeout=5)

    _reader, reader_done, _ = _call_on_thread(registry.list_plugins)
    assert not reader_done.wait(timeout=0.3), (
        "list_plugins completed while a mutator held the registry lock — no mutual exclusion"
    )

    release.set()
    assert writer_done.wait(timeout=5)
    assert reader_done.wait(timeout=5)


@pytest.mark.parametrize(
    "reader_name",
    ["get_plugin", "get_transition_plugin", "get_manifest", "is_enabled", "get_plugin_config"],
)
def test_point_readers_cannot_observe_the_reload_window(registry, mock_loader, reader_name):
    """The point readers must take the registry lock: during reload_plugin the
    id is briefly absent from _plugins/_manifests, and an unlocked reader
    could observe that window (the documented invariant forbids it)."""
    in_window = threading.Event()
    release = threading.Event()

    new_plugin = _plugin_stub("rw")
    manifest = MagicMock()
    manifest.id = "rw"
    registry._plugins["rw"] = _plugin_stub("rw")
    registry._manifests["rw"] = manifest
    registry._enabled["rw"] = False

    def _paused_reload(plugin_id):
        in_window.set()
        assert release.wait(timeout=30)
        return new_plugin

    mock_loader.reload_plugin.side_effect = _paused_reload
    mock_loader.get_manifest.return_value = manifest

    _writer, writer_done, _ = _call_on_thread(lambda: registry.reload_plugin("rw"))
    assert in_window.wait(timeout=5)

    reader_fn = getattr(registry, reader_name)
    _reader, reader_done, reader_result = _call_on_thread(lambda: reader_fn("rw"))
    assert not reader_done.wait(timeout=0.3), f"{reader_name} returned mid-reload — it does not take the registry lock"

    release.set()
    assert writer_done.wait(timeout=5)
    assert reader_done.wait(timeout=5)
    if reader_name == "get_plugin":
        assert reader_result[0] is new_plugin
