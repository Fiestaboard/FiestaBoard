"""What the render fingerprint costs, counted rather than timed (#1883 tail).

``tests/test_render_short_circuit.py`` pins that the short-circuit FIRES
correctly. This file pins what deciding it COSTS, because the Pi audit found
the deciding cost carried two independent multipliers the short-circuit itself
does not:

* **per board** — four same-size boards on one page serialised the identical
  ``(page, context)`` pair four times per tick, so the cost of deciding "no
  render needed" scaled with board count even though the answer could not;
* **per payload byte** — the whole plugin payload was re-serialised into the
  hash every board every tick, so a single 64 KB plugin multiplied the idle
  tick by 6.4x and a 256 KB one by 23x.

Both are counted here (``json.dumps`` calls, bytes handed to ``json.dumps``,
``Page.model_dump_json`` calls), never timed: counts transfer to a Raspberry
Pi, wall-clock does not.

The safety half matters more than the win. A memo that fired too eagerly, or a
payload hash that missed a change, would strand a board on a stale frame — so
every input that must still move the fingerprint has a test here, and the
fallback that protects an uncovered hash map has one too.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from src.main import DisplayService
from src.pages.models import Page
from src.pages.service import PageService
from src.pages.storage import PageStorage
from src.plugins.base import PluginResult

PAGE_ID = "page:fingerprint"


class _MemoryStorage(PageStorage):
    def __init__(self, pages):
        self._pages = {p.id: p for p in pages}

    def get(self, page_id):
        return self._pages.get(page_id)

    def list_all(self):
        return list(self._pages.values())


class _Registry:
    """Fetch-layer double that models PluginBase's cache the way it matters here.

    Each plugin's payload lives on ONE ``PluginResult`` object which is handed
    back to every build until :meth:`set_data` replaces it — exactly as
    ``PluginBase`` holds a cached result across ticks. That is what makes the
    payload hash a once-per-data-change cost rather than a per-tick one, so
    the byte counts below measure the production shape and not the double.
    """

    def __init__(self, data, *, per_board=None, record_fingerprints=True):
        self.record_fingerprints = record_fingerprints
        self.trigger_plugins: dict = {}
        self.builds = 0
        self.boards_seen: list = []
        self._results = {None: {pid: PluginResult(available=True, data=payload) for pid, payload in data.items()}}
        for device_type, payloads in (per_board or {}).items():
            self._results[device_type] = {
                pid: PluginResult(available=True, data=payload) for pid, payload in payloads.items()
            }

    def set_data(self, plugin_id: str, payload: dict, *, device_type=None) -> None:
        """Replace a plugin's payload, as a fresh upstream fetch would."""
        self._results[device_type][plugin_id] = PluginResult(available=True, data=payload)

    def _source(self, board):
        device_type = None if board is None else board.device_type
        return self._results.get(device_type, self._results[None])

    @property
    def enabled_plugins(self) -> dict:
        return dict.fromkeys(self._results[None])

    def build_template_context(self, board=None, plugin_ids=None, include_trigger_plugins=True, fingerprints=None):
        self.builds += 1
        self.boards_seen.append(None if board is None else (board.device_type, board.rows, board.cols))
        source = self._source(board)
        if plugin_ids is None:
            selected = dict(source)
        else:
            wanted = {str(p).lower() for p in plugin_ids}
            selected = {k: v for k, v in source.items() if k.lower() in wanted}
        built = {}
        for plugin_id, result in selected.items():
            built[plugin_id] = result.data
            if fingerprints is not None and self.record_fingerprints:
                fingerprints[plugin_id] = result.data_fingerprint()
        return built


class _ConfigManager:
    def __init__(self):
        self.config_generation = 1


def _page(template=None, *, device_type="flagship", updated_at=None, **extra) -> Page:
    return Page(
        id=PAGE_ID,
        name="Test",
        type="template",
        device_type=device_type,
        template=template or ["{{stub.value}}", "", "", "", "", ""],
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=updated_at or datetime(2026, 1, 1, tzinfo=UTC),
        **extra,
    )


@pytest.fixture
def rig(monkeypatch):
    """Real ``PageService.shared_context_for`` over a stub fetch layer."""

    def _make(data=None, *, per_board=None, record_fingerprints=True):
        registry = _Registry(
            data if data is not None else {"stub": {"value": "HELLO"}},
            per_board=per_board,
            record_fingerprints=record_fingerprints,
        )
        config = _ConfigManager()
        pages = PageService(storage=_MemoryStorage([]))
        monkeypatch.setattr("src.plugins.registry.get_plugin_registry", lambda: registry)
        monkeypatch.setattr("src.config_manager.get_config_manager", lambda: config)
        return registry, config, pages

    return _make


class _Counter:
    """Counts ``json.dumps`` calls, bytes serialised, and page dumps."""

    def __init__(self, monkeypatch):
        self.dumps = 0
        self.bytes = 0
        self.page_dumps = 0
        real_dumps = json.dumps
        real_mdj = Page.model_dump_json

        def counting_dumps(obj, **kwargs):
            self.dumps += 1
            out = real_dumps(obj, **kwargs)
            self.bytes += len(out)
            return out

        def counting_mdj(page_self, **kwargs):
            self.page_dumps += 1
            return real_mdj(page_self, **kwargs)

        monkeypatch.setattr(json, "dumps", counting_dumps)
        monkeypatch.setattr(Page, "model_dump_json", counting_mdj)


def _fingerprint(page, pages, contexts, *, override=False, page_id=PAGE_ID):
    return DisplayService._render_fingerprint(page, page_id, pages, contexts, override_active=override)


# --------------------------------------------------------------------------
# The per-board multiplier
# --------------------------------------------------------------------------


@pytest.mark.parametrize("boards", [1, 2, 4, 8])
def test_same_size_boards_fingerprint_the_page_once_per_tick(rig, monkeypatch, boards):
    """N same-size boards on one page cost ONE serialisation, not N.

    Before: json.dumps calls per tick tracked board count exactly
    (1 -> 1, 2 -> 2, 4 -> 4, 8 -> 8).
    """
    _registry, _config, pages = rig()
    page = _page()
    # One warm tick first: PluginBase hashes a payload when it CACHES it, so
    # in production that cost lands once per refresh interval, not per tick.
    _fingerprint(page, pages, {})
    counter = _Counter(monkeypatch)

    contexts: dict = {}
    results = [_fingerprint(page, pages, contexts) for _ in range(boards)]

    assert len(set(results)) == 1, "same inputs must produce one fingerprint"
    assert results[0] is not None
    assert counter.dumps == 1, f"{boards} boards serialised the fingerprint {counter.dumps} times"
    assert counter.page_dumps == 1, f"{boards} boards dumped the page {counter.page_dumps} times"


def test_the_memo_dies_with_the_tick(rig, monkeypatch):
    """A fresh ``contexts`` dict — i.e. the next tick — recomputes."""
    _registry, _config, pages = rig()
    page = _page()
    # One warm tick first: PluginBase hashes a payload when it CACHES it, so
    # in production that cost lands once per refresh interval, not per tick.
    _fingerprint(page, pages, {})
    counter = _Counter(monkeypatch)

    for _ in range(3):
        _fingerprint(page, pages, {})

    assert counter.dumps == 3


# --------------------------------------------------------------------------
# The payload multiplier
# --------------------------------------------------------------------------


def _payload(kilobytes: int) -> dict:
    filler = "y" * 200
    return {"value": "HELLO", "blob": {f"k{i}": filler for i in range(max(1, (kilobytes * 1024) // 210))}}


@pytest.mark.parametrize("kilobytes", [64, 256])
def test_plugin_payload_size_does_not_enter_the_fingerprint(rig, monkeypatch, kilobytes):
    """A big plugin payload costs the fingerprint a 32-char hash, not the payload.

    Before: bytes handed to json.dumps per tick were 65,978 at 64 KB and
    262,786 at 256 KB against a 559-byte floor.
    """
    _registry, _config, pages = rig({"stub": _payload(kilobytes)})
    page = _page()

    # One warm tick so the payload's own hash is memoised on its result, as it
    # is in production the moment PluginBase caches that result.
    _fingerprint(page, pages, {})
    counter = _Counter(monkeypatch)
    _fingerprint(page, pages, {})

    assert counter.bytes < 4096, f"{kilobytes} KB payload put {counter.bytes} bytes through json.dumps"


# --------------------------------------------------------------------------
# Safety: everything that must still move the fingerprint
# --------------------------------------------------------------------------


def test_changed_plugin_payload_moves_the_fingerprint(rig):
    registry, _config, pages = rig()
    page = _page()

    before = _fingerprint(page, pages, {})
    registry.set_data("stub", {"value": "GOODBYE"})
    after = _fingerprint(page, pages, {})

    assert before != after


def test_a_payload_change_within_one_tick_is_not_hidden_by_the_memo(rig):
    """The memo keys on page + generation, so it must not span a data change.

    Within one tick the context is built once and shared, so this asserts the
    memo cannot serve a fingerprint for data the shared context no longer
    holds: a second page id gets its own memo entry and its own hash.
    """
    registry, _config, pages = rig({"stub": {"value": "A"}, "other": {"value": "B"}})
    contexts: dict = {}
    one = _fingerprint(_page(["{{stub.value}}", "", "", "", "", ""]), pages, contexts)
    two = _fingerprint(
        _page(["{{other.value}}", "", "", "", "", ""]),
        pages,
        contexts,
        page_id="page:other",
    )
    assert one != two
    assert registry.builds >= 1


def test_edited_page_moves_the_fingerprint_within_the_same_tick(rig):
    """The memo must not survive a page edit that lands mid-pass."""
    _registry, _config, pages = rig()
    contexts: dict = {}
    before = _fingerprint(_page(), pages, contexts)
    edited = _page(["{{stub.value}}!", "", "", "", "", ""], updated_at=datetime(2026, 2, 2, tzinfo=UTC))
    after = _fingerprint(edited, pages, contexts)
    assert before != after


def test_config_generation_moves_the_fingerprint_within_the_same_tick(rig):
    _registry, config, pages = rig()
    page = _page()
    contexts: dict = {}
    before = _fingerprint(page, pages, contexts)
    config.config_generation += 1
    after = _fingerprint(page, pages, contexts)
    assert before != after


def test_override_branch_moves_the_fingerprint_within_the_same_tick(rig):
    _registry, _config, pages = rig()
    page = _page()
    contexts: dict = {}
    normal = _fingerprint(page, pages, contexts, override=False)
    overridden = _fingerprint(page, pages, contexts, override=True)
    assert normal != overridden


def test_board_sizes_never_share_a_memo(rig):
    """Board-aware plugins return different data per geometry (#1243).

    Collapsing the memo across sizes would hand a Note board the Flagship's
    fingerprint, which is exactly the per-board isolation this must not break.
    """
    _registry, _config, pages = rig(
        per_board={
            "flagship": {"stub": {"value": "WIDE"}},
            "note": {"stub": {"value": "NARROW"}},
        }
    )
    contexts: dict = {}
    flagship = _fingerprint(_page(device_type="flagship"), pages, contexts)
    note = _fingerprint(_page(["{{stub.value}}", "", ""], device_type="note"), pages, contexts)
    assert flagship != note


def test_a_registry_that_records_no_hashes_still_detects_a_data_change(rig):
    """The fallback is what makes a partial hash map safe.

    A context whose payload hashes are not provably complete must be hashed
    the old way — payloads and all — because treating an unrecorded plugin as
    "contributed nothing" would swallow a real change.
    """
    registry, _config, pages = rig(record_fingerprints=False)
    page = _page()

    before = _fingerprint(page, pages, {})
    registry.set_data("stub", {"value": "MOVED"})
    after = _fingerprint(page, pages, {})

    assert before is not None
    assert before != after


def test_a_partially_recorded_hash_map_still_detects_a_data_change(rig, monkeypatch):
    """Half a hash map is treated as no hash map, not as half the truth."""
    registry, _config, pages = rig({"stub": {"value": "A"}, "extra": {"value": "B"}})

    real_build = registry.build_template_context

    def half_recording(board=None, plugin_ids=None, include_trigger_plugins=True, fingerprints=None):
        built = real_build(board, plugin_ids, include_trigger_plugins, fingerprints)
        if fingerprints is not None:
            fingerprints.pop("extra", None)
        return built

    monkeypatch.setattr(registry, "build_template_context", half_recording)
    page = _page(["{{stub.value}}{{extra.value}}", "", "", "", "", ""])

    before = _fingerprint(page, pages, {})
    registry.set_data("extra", {"value": "MOVED"})
    after = _fingerprint(page, pages, {})

    assert before is not None
    assert before != after


# --------------------------------------------------------------------------
# The hash itself
# --------------------------------------------------------------------------


def test_data_fingerprint_is_computed_once_per_result(monkeypatch):
    result = PluginResult(available=True, data={"a": 1, "b": [1, 2, 3]})
    calls = {"n": 0}
    real_dumps = json.dumps

    def counting(obj, **kwargs):
        calls["n"] += 1
        return real_dumps(obj, **kwargs)

    monkeypatch.setattr(json, "dumps", counting)
    first = result.data_fingerprint()
    second = result.data_fingerprint()

    assert first == second
    assert calls["n"] == 1


def test_data_fingerprint_separates_different_payloads():
    a = PluginResult(available=True, data={"value": 1})
    b = PluginResult(available=True, data={"value": 2})
    assert a.data_fingerprint() != b.data_fingerprint()


def test_data_fingerprint_is_insensitive_to_key_order():
    a = PluginResult(available=True, data={"x": 1, "y": 2})
    b = PluginResult(available=True, data={"y": 2, "x": 1})
    assert a.data_fingerprint() == b.data_fingerprint()


def test_hashing_does_not_change_result_equality():
    a = PluginResult(available=True, data={"value": 1})
    b = PluginResult(available=True, data={"value": 1})
    a.data_fingerprint()
    assert a == b


def test_unhashable_payload_still_produces_a_fingerprint():
    """``default=str`` keeps a datetime-carrying payload hashable."""
    result = PluginResult(available=True, data={"when": datetime(2026, 1, 1, tzinfo=UTC)})
    assert isinstance(result.data_fingerprint(), str)


def test_fingerprint_is_none_when_the_context_cache_is_absent(rig):
    """Direct callers (MQTT, /refresh) pass no per-pass cache and must render."""
    _registry, _config, pages = rig()
    assert _fingerprint(_page(), pages, None) is None


def test_registry_construction_is_not_required_for_the_memo_key(rig):
    """A note-array page keys its memo on its true geometry, not its type."""
    _registry, _config, pages = rig()
    contexts: dict = {}
    wide = _fingerprint(
        _page(["{{stub.value}}"] * 3, device_type="note_array", notes_wide=2, notes_tall=1),
        pages,
        contexts,
    )
    tall = _fingerprint(
        _page(["{{stub.value}}"] * 6, device_type="note_array", notes_wide=1, notes_tall=2),
        pages,
        contexts,
    )
    assert wide is not None and tall is not None
    assert wide != tall
