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
