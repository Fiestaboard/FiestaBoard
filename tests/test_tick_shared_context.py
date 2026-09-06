"""Instrumentation tests for the change-driven tick (issue #1752).

Two audited wastes are pinned here by COUNTING, not by timing:

1. Per-tick context fan-out — one ``build_template_context`` call per tick
   per distinct board size, shared across collection resolution and every
   board render of that size. Before the fix each render (and each
   variable-mode collection resolution) built its own full context.
2. The 1 Hz silence probe — ``Config.is_silence_mode_active`` fully
   re-parsed the silence window (behind a config-manager lock + deep copy)
   on every call. After the fix the parsed window is cached per board and
   invalidated by the config manager's write generation.

Send behavior itself is pinned elsewhere (tests/test_engine_equivalence.py);
these tests must pass WITHOUT any golden changing.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import src.config as config_module
from src.collections.models import Collection, VariableModeConfig, VariableRule
from src.collections.service import CollectionService
from src.collections.storage import CollectionStorage
from src.config import Config
from src.main import BoardRuntime, DisplayService
from src.pages.models import Page
from src.pages.service import PageService
from src.pages.storage import PageStorage
from src.templates.engine import TemplateEngine
from tests.engine_harness import SilenceOffConfigManager, make_board, silence_feature
from tests.helpers import decode_board_rows

TRANSITIONS = SimpleNamespace(strategy="instant", step_interval_ms=0, step_size=1)


class CountingRegistry:
    """Plugin-registry double that counts every full context fan-out."""

    def __init__(self):
        self.build_calls = 0
        self.boards_seen = []
        # Board-sensitive payload hook: tests that need a plugin whose data
        # differs between board=None and board-aware builds override this.
        self.payload = lambda board: {}

    def build_template_context(self, board=None, plugin_ids=None):
        self.build_calls += 1
        self.boards_seen.append(board)
        return self.payload(board)

    def build_template_contexts_for(self, boards, plugin_ids=None):
        return {key: self.build_template_context(b) for key, b in boards.items()}

    def get_manifest(self, plugin_id):
        return None


def _engine_with(registry) -> TemplateEngine:
    """A TemplateEngine wired to the counting registry, skipping real plugin init."""
    engine = TemplateEngine.__new__(TemplateEngine)
    engine._display_service = None
    engine._config_manager = None
    engine._plugin_registry = registry
    return engine


def _template_page(page_id: str, text: str, device_type: str = "flagship") -> Page:
    return Page(id=page_id, name=page_id, type="template", device_type=device_type, template=[text])


def _settings_service(boards, active):
    svc = MagicMock()
    svc.get_board_settings.return_value = SimpleNamespace(boards=boards)
    svc.get_primary_board_id.return_value = boards[0]["id"]
    svc.is_paused.side_effect = lambda board_id=None: False
    svc.is_schedule_enabled.side_effect = lambda board_id=None: False
    svc.get_active_page_id.side_effect = lambda board_id=None: active.get(board_id or boards[0]["id"])
    svc.get_transition_settings.return_value = TRANSITIONS
    svc.consume_temporary_override.return_value = None
    svc.should_send_to_board.return_value = True
    return svc


def _display_service(boards):
    svc = DisplayService()
    clients = {}
    for board in boards:
        client = MagicMock()
        client.render.return_value = (True, True)
        client.is_virtual = False
        client.last_send_throttled = False
        clients[board["id"]] = client
        svc.runtimes[board["id"]] = BoardRuntime(client=client, board_id=board["id"])
    svc._primary_board_id = boards[0]["id"]
    return svc, clients


@pytest.fixture
def registry():
    return CountingRegistry()


@pytest.fixture
def wire(monkeypatch, tmp_path, registry):
    """Wire a real PageService + TemplateEngine + DisplayService around stubs.

    Returns a builder: call with boards, the active-page map, the Page objects
    to store, and (optionally) a real CollectionService.
    """

    def _build(boards, active, pages, collections=None):
        storage = PageStorage(storage_file=str(tmp_path / "pages.json"))
        for page in pages:
            storage.create(page)
        page_service = PageService(storage=storage)

        settings = _settings_service(boards, active)
        service, clients = _display_service(boards)
        cm = SilenceOffConfigManager()
        engine = _engine_with(registry)

        monkeypatch.setattr("src.main.get_settings_service", lambda: settings)
        monkeypatch.setattr("src.main.get_page_service", lambda: page_service)
        monkeypatch.setattr("src.main.get_schedule_service", lambda: MagicMock())
        monkeypatch.setattr(
            "src.main.get_collection_service", lambda: collections if collections is not None else MagicMock()
        )
        monkeypatch.setattr("src.config.get_config_manager", lambda: cm)
        monkeypatch.setattr("src.config_manager.get_config_manager", lambda: cm)
        monkeypatch.setattr("src.pages.service.get_template_engine", lambda: engine)
        monkeypatch.setattr("src.plugins.registry.get_plugin_registry", lambda: registry)
        monkeypatch.setattr(service, "_check_trigger_override", lambda: None)
        monkeypatch.setattr(service, "request_board_refresh", lambda *a, **k: None)
        return service, clients

    return _build


class TestSharedContextPerTick:
    def test_two_same_size_boards_share_one_context_build(self, wire, registry):
        """One pass over two flagship boards fans out to plugins exactly once."""
        boards = [make_board("b-1"), make_board("b-2")]
        pages = [_template_page("p-1", "ALPHA"), _template_page("p-2", "BRAVO")]
        service, clients = wire(boards, {"b-1": "p-1", "b-2": "p-2"}, pages)

        service.check_and_send_active_page()

        # Non-vacuity: both boards really rendered and sent this pass.
        assert clients["b-1"].render.call_count == 1
        assert clients["b-2"].render.call_count == 1
        assert registry.build_calls == 1

    def test_unchanged_second_tick_builds_one_context_and_sends_nothing(self, wire, registry):
        """Unchanged inputs: one context build per tick, zero re-sends (dedupe)."""
        boards = [make_board("b-1"), make_board("b-2")]
        pages = [_template_page("p-1", "ALPHA"), _template_page("p-2", "BRAVO")]
        service, clients = wire(boards, {"b-1": "p-1", "b-2": "p-2"}, pages)

        service.check_and_send_active_page()
        service.check_and_send_active_page()

        assert registry.build_calls == 2  # one per tick, never one per board
        assert clients["b-1"].render.call_count == 1  # second tick deduped
        assert clients["b-2"].render.call_count == 1

    def test_distinct_board_sizes_build_one_context_each(self, wire, registry):
        """Sharing is per board size: a flagship and a note board need two contexts."""
        boards = [make_board("b-1"), make_board("b-2", device_type="note")]
        pages = [_template_page("p-1", "ALPHA"), _template_page("p-2", "BRAVO", device_type="note")]
        service, clients = wire(boards, {"b-1": "p-1", "b-2": "p-2"}, pages)

        service.check_and_send_active_page()

        assert clients["b-1"].render.call_count == 1
        assert clients["b-2"].render.call_count == 1
        assert registry.build_calls == 2

    def test_variable_collection_without_rules_builds_no_extra_context(self, wire, registry, tmp_path):
        """A rule-less variable collection resolves to its default with zero fan-out.

        (Rule evaluation itself uses a dedicated shared board=None build —
        see TestVariableRuleContextSemantics — so with no rules the only
        context this tick builds is the render's.)
        """
        collection = Collection(
            name="var",
            page_ids=["p-var"],
            selection_mode="variable",
            variable=VariableModeConfig(rules=[], default_page_id="p-var"),
        )
        collections = CollectionService(storage=CollectionStorage(storage_file=str(tmp_path / "collections.json")))
        collections.storage.create(collection)

        boards = [make_board("b-1")]
        pages = [_template_page("p-var", "VARIABLE")]
        service, clients = wire(boards, {"b-1": collection.id}, pages, collections=collections)

        service.check_and_send_active_page()

        assert clients["b-1"].render.call_count == 1
        assert registry.build_calls == 1  # only the render's context; resolution built none


def _board_sensitive_payload(board):
    """A stub plugin whose data differs between board=None and board-aware builds."""
    return {"stub": {"which": "AGNOSTIC" if board is None else "BOARD"}}


def _variable_collection(tmp_path, rules, default_page_id):
    collection = Collection(
        name="var",
        page_ids=[default_page_id] + [r.page_id for r in rules],
        selection_mode="variable",
        variable=VariableModeConfig(rules=rules, default_page_id=default_page_id),
    )
    collections = CollectionService(storage=CollectionStorage(storage_file=str(tmp_path / "collections.json")))
    collections.storage.create(collection)
    return collection, collections


class TestVariableRuleContextSemantics:
    """Variable-mode rule evaluation must stay board-agnostic (pre-#1752 semantics).

    Board-aware plugins can return different data per geometry, so a rule fed
    a board-aware render context could select a different page per board.
    Rule evaluation therefore gets a dedicated shared ``board=None`` build,
    never the render's board-aware context.
    """

    def test_variable_rules_see_board_agnostic_plugin_data(self, wire, registry, tmp_path):
        """A rule over a board-sensitive plugin evaluates against board=None data."""
        registry.payload = _board_sensitive_payload
        rule = VariableRule(expression='stub.which = "AGNOSTIC"', page_id="p-agnostic")
        collection, collections = _variable_collection(tmp_path, [rule], default_page_id="p-board")

        boards = [make_board("b-1")]
        pages = [_template_page("p-agnostic", "PICKED AGNOSTIC"), _template_page("p-board", "PICKED BOARD")]
        service, clients = wire(boards, {"b-1": collection.id}, pages, collections=collections)

        service.check_and_send_active_page()

        assert clients["b-1"].render.call_count == 1  # non-vacuity: something rendered
        rows = decode_board_rows(clients["b-1"].render.call_args[0][0])
        assert any("AGNOSTIC" in row for row in rows), f"rule saw board-aware data; rendered rows: {rows}"

    def test_one_board_agnostic_build_per_tick_regardless_of_board_count(self, wire, registry, tmp_path):
        """N boards resolving variable collections share ONE board=None build per tick."""
        registry.payload = _board_sensitive_payload
        rule = VariableRule(expression='stub.which = "AGNOSTIC"', page_id="p-agnostic")
        collection, collections = _variable_collection(tmp_path, [rule], default_page_id="p-board")

        boards = [make_board("b-1"), make_board("b-2")]
        pages = [_template_page("p-agnostic", "PICKED AGNOSTIC"), _template_page("p-board", "PICKED BOARD")]
        service, clients = wire(boards, {"b-1": collection.id, "b-2": collection.id}, pages, collections=collections)

        service.check_and_send_active_page()

        assert clients["b-1"].render.call_count == 1
        assert clients["b-2"].render.call_count == 1
        assert registry.boards_seen.count(None) == 1  # one board-agnostic build, shared
        assert registry.build_calls == 2  # + one flagship render context, shared


# ---------------------------------------------------------------------------
# Silence window cache (the 1 Hz probe)
# ---------------------------------------------------------------------------


class GenerationConfigManager:
    """Config-manager double exposing the write-generation the cache keys on."""

    def __init__(self, feature):
        self.feature = feature
        self.config_generation = 0
        self.per_board_migrations = 0
        self.utc_migrations = 0

    def get_feature(self, name):
        return dict(self.feature) if name == "silence_schedule" else {}

    def get_general(self):
        return {}

    def get_board(self):
        return {}

    def migrate_silence_schedule_to_per_board(self):
        self.per_board_migrations += 1
        return 0

    def migrate_silence_schedule_to_utc(self):
        self.utc_migrations += 1
        return False


@pytest.fixture
def counted_resolve(monkeypatch):
    """Count full silence-window parses without changing their result."""
    calls = {"n": 0}
    real = config_module.resolve_silence_schedule

    def counting(feature, board_id=None):
        calls["n"] += 1
        return real(feature, board_id)

    monkeypatch.setattr("src.config.resolve_silence_schedule", counting)
    return calls


@pytest.fixture
def silence_cm(monkeypatch):
    cm = GenerationConfigManager(silence_feature(start_time="20:00+00:00", end_time="07:00+00:00"))
    monkeypatch.setattr("src.config.get_config_manager", lambda: cm)
    monkeypatch.setattr("src.config_manager.get_config_manager", lambda: cm)
    # A fresh cache per test, mirroring a fresh process (guarded so the
    # fail-first run against the pre-cache code still executes).
    getattr(Config, "_silence_cache", {}).clear()
    if hasattr(Config, "_silence_migrations_ran"):
        Config._silence_migrations_ran = None
    return cm


class TestSilenceWindowCache:
    def test_sixty_probes_at_idle_parse_the_window_once(self, silence_cm, counted_resolve):
        """60 simulated 1 Hz probes re-parse (lock + deep-copy) the config once."""
        for _ in range(60):
            Config.is_silence_mode_active("board-1")

        assert counted_resolve["n"] == 1

    def test_sixty_probes_at_idle_run_the_silence_migrations_once(self, silence_cm):
        """The idempotent no-op migrations stop taking the config lock every second."""
        for _ in range(60):
            Config.is_silence_mode_active("board-1")

        assert silence_cm.per_board_migrations <= 1
        assert silence_cm.utc_migrations <= 1

    def test_config_write_invalidates_the_cached_window(self, silence_cm, counted_resolve):
        """A config save (generation bump) must re-parse and reflect the new window."""
        assert Config.silence_config_for("board-1")["enabled"] is True
        parses_before = counted_resolve["n"]

        silence_cm.feature = dict(silence_cm.feature, enabled=False)
        silence_cm.config_generation += 1

        assert Config.silence_config_for("board-1")["enabled"] is False
        assert Config.is_silence_mode_active("board-1") is False
        assert counted_resolve["n"] > parses_before

    def test_cache_is_per_board(self, silence_cm):
        """Two boards with different by_board overrides resolve independently."""
        silence_cm.feature = dict(
            silence_cm.feature,
            by_board={"board-2": {"enabled": False}},
        )
        silence_cm.config_generation += 1

        assert Config.silence_config_for("board-1")["enabled"] is True
        assert Config.silence_config_for("board-2")["enabled"] is False
        # And again, from cache, unchanged:
        assert Config.silence_config_for("board-1")["enabled"] is True
        assert Config.silence_config_for("board-2")["enabled"] is False

    def test_callers_cannot_corrupt_the_cache_by_mutating_the_result(self, silence_cm):
        """silence_config_for hands out a copy, not the cached dict itself."""
        first = Config.silence_config_for("board-1")
        first["enabled"] = False
        assert Config.silence_config_for("board-1")["enabled"] is True

    def test_stub_config_managers_without_generation_bypass_the_cache(self, monkeypatch, counted_resolve):
        """Test doubles lacking config_generation keep the always-fresh behavior."""
        cm = SilenceOffConfigManager()
        monkeypatch.setattr("src.config.get_config_manager", lambda: cm)
        monkeypatch.setattr("src.config_manager.get_config_manager", lambda: cm)

        Config.silence_config_for("board-1")
        Config.silence_config_for("board-1")

        assert counted_resolve["n"] == 2
