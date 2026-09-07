"""The render short-circuit #1752's acceptance asked for and did not get (#1883).

#1752 shipped "change-driven tick" in its title. Measurement afterwards found
the FETCH set had become demand-driven while the RENDER stayed time-driven on
the same 1 Hz wake: ``preview_page`` / ``render_page`` calls per 10 unchanged
ticks stayed at 10 out of 10. The render result was produced and then thrown
away at the content dedupe.

These tests pin both halves of the fix:

* the win — an unchanged input set renders ONCE across ten drive passes;
* the safety — every input that can move the rendered bytes still forces a
  render, so a real change is never swallowed. Those are the tests that make
  the optimization non-vacuous: a short-circuit that always fires would pass
  the first test and fail every other one here.

Everything below drives the REAL ``DisplayService.check_and_send_for_board``
pass over a REAL ``PageService`` and a REAL ``TemplateEngine`` — the fetch
layer is the only stub, because plugin data freshness is exactly the input
being varied.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from src.main import BoardRuntime, DisplayService
from src.pages.models import Page
from src.pages.service import PageService
from src.pages.storage import PageStorage
from src.templates.engine import get_template_engine, reset_template_engine
from tests.fake_clock import FakeClock, install_fake_time_service

BOARD_ID = "board-1"
PAGE_ID = "page-1"
TICKS = 10


# --------------------------------------------------------------------------
# Doubles
# --------------------------------------------------------------------------


class RecordingClient:
    """Board client that records each frame and can be made to fail."""

    def __init__(self):
        self.frames: list[list[list[int]]] = []
        self.fail = False
        self.last_send_throttled = False
        self.use_cloud = False

    def render(self, board_array, **_kwargs):
        self.frames.append([row[:] for row in board_array])
        if self.fail:
            return False, False
        return True, True

    def read_current_message(self, sync_cache: bool = False):
        return None

    def clear_cache(self):
        return None


class StubRegistry:
    """Fetch layer stub: returns whatever ``data`` currently holds."""

    def __init__(self, data: dict):
        self.data = data
        self.trigger_plugins: dict = {}
        self.builds = 0

    @property
    def enabled_plugins(self) -> dict:
        return dict.fromkeys(self.data)

    def build_template_context(self, board=None, plugin_ids=None, include_trigger_plugins=True):
        self.builds += 1
        if plugin_ids is None:
            return {k: dict(v) for k, v in self.data.items()}
        wanted = {str(p).lower() for p in plugin_ids}
        return {k: dict(v) for k, v in self.data.items() if k.lower() in wanted}

    def get_manifest(self, _plugin_id):
        return None

    def get_plugin(self, _plugin_id):
        return None


class StubConfigManager:
    """Config store with silence off and a bumpable generation counter."""

    def __init__(self):
        self.config_generation = 1
        self.color_rules: dict[tuple[str, str], list] = {}

    def get_feature(self, name: str) -> dict:
        if name == "silence_schedule":
            return {"enabled": False, "by_board": {}}
        return {}

    def get_general(self) -> dict:
        return {}

    def get_board(self) -> dict:
        return {}

    def get_color_rules(self, feature_name: str, field_name: str) -> list:
        return self.color_rules.get((feature_name, field_name), [])

    def migrate_silence_schedule_to_utc(self) -> bool:
        return False

    def migrate_silence_schedule_to_per_board(self) -> int:
        return 0


class CountingPageService(PageService):
    """Real PageService that counts the two render entry points."""

    def __init__(self, storage):
        super().__init__(storage=storage)
        self.previews = 0
        self.renders = 0

    def preview_page(self, *args, **kwargs):
        self.previews += 1
        return super().preview_page(*args, **kwargs)

    def render_page(self, *args, **kwargs):
        self.renders += 1
        return super().render_page(*args, **kwargs)


class MemoryPageStorage(PageStorage):
    """In-memory page store; keeps the suite off the filesystem."""

    def __init__(self, pages: list[Page]):
        self._pages = {p.id: p for p in pages}

    def get(self, page_id):
        return self._pages.get(page_id)

    def list_all(self):
        return list(self._pages.values())

    def put(self, page: Page) -> None:
        self._pages[page.id] = page


# --------------------------------------------------------------------------
# Rig
# --------------------------------------------------------------------------


class Rig:
    """One board, one template page, one stub plugin — driven pass by pass."""

    def __init__(
        self,
        monkeypatch,
        *,
        template: list[str],
        data: dict,
        silence: dict | None = None,
        clock: FakeClock | None = None,
    ):
        self.clock = clock
        self.page = Page(
            id=PAGE_ID,
            name="Test",
            type="template",
            device_type="flagship",
            template=template,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        self.storage = MemoryPageStorage([self.page])
        self.pages = CountingPageService(self.storage)
        self.registry = StubRegistry(data)
        self.config = StubConfigManager()
        if silence is not None:
            self.config.get_feature = lambda name: dict(silence) if name == "silence_schedule" else {}
        self.client = RecordingClient()

        board = {
            "id": BOARD_ID,
            "name": "Board",
            "device_type": "flagship",
            "enabled": True,
            "api_mode": "local",
            "host": "mock-host",
            "port": 7000,
            "local_api_key": "k",
        }
        settings = MagicMock()
        settings.get_board_settings.return_value = MagicMock(boards=[board])
        settings.get_primary_board_id.return_value = BOARD_ID
        settings.is_paused.side_effect = lambda board_id=None: False
        settings.is_schedule_enabled.side_effect = lambda board_id=None: False
        settings.get_active_page_id.side_effect = lambda board_id=None: PAGE_ID
        settings.get_transition_settings.return_value = MagicMock(strategy="instant", step_interval_ms=0, step_size=1)
        settings.should_send_to_board.return_value = True
        settings.consume_temporary_override.side_effect = lambda: None
        self.settings = settings

        self.service = DisplayService()
        self.service.runtimes[BOARD_ID] = BoardRuntime(client=self.client, board_id=BOARD_ID)
        self.service._primary_board_id = BOARD_ID

        monkeypatch.setattr("src.main.get_settings_service", lambda: settings)
        monkeypatch.setattr("src.main.get_page_service", lambda: self.pages)
        monkeypatch.setattr("src.main.get_schedule_service", lambda: MagicMock())
        monkeypatch.setattr("src.main.get_collection_service", lambda: MagicMock())
        monkeypatch.setattr("src.config.get_config_manager", lambda: self.config)
        monkeypatch.setattr("src.config_manager.get_config_manager", lambda: self.config)
        monkeypatch.setattr("src.plugins.registry.get_plugin_registry", lambda: self.registry)
        monkeypatch.setattr("src.templates.engine.get_plugin_registry", lambda: self.registry)
        monkeypatch.setattr(self.service, "request_board_refresh", lambda *a, **k: None)
        monkeypatch.setattr(self.service, "_check_trigger_override", lambda: None)
        if clock is not None:
            install_fake_time_service(monkeypatch, clock)

        engine = get_template_engine()
        monkeypatch.setattr(engine, "_plugin_registry", self.registry)
        monkeypatch.setattr(engine, "_config_manager", self.config)

    @property
    def runtime(self) -> BoardRuntime:
        return self.service.runtimes[BOARD_ID]

    def tick(self, n: int = 1) -> None:
        for _ in range(n):
            self.service.check_and_send_active_page(wait=True)
        assert self.service.wait_until_idle(timeout=10.0), "send workers never went idle"

    def edit_page(self, **fields) -> None:
        updated = self.page.model_copy(update={**fields, "updated_at": datetime.now(UTC)})
        self.storage.put(updated)
        self.page = updated

    def stop(self) -> None:
        for rt in self.service.runtimes.values():
            if rt.send_worker is not None:
                rt.send_worker.stop()


@pytest.fixture(autouse=True)
def _fresh_template_engine():
    reset_template_engine()
    yield
    reset_template_engine()


@pytest.fixture
def rig(monkeypatch):
    rigs: list[Rig] = []

    def _make(**kwargs):
        r = Rig(monkeypatch, **kwargs)
        rigs.append(r)
        return r

    yield _make
    for r in rigs:
        r.stop()


def _default(**overrides):
    base = {
        "template": ["{{stub.value}}", "", "", "", "", ""],
        "data": {"stub": {"value": "HELLO"}},
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------
# The win
# --------------------------------------------------------------------------


def test_ten_unchanged_ticks_render_once(rig):
    """The measurement #1752's acceptance named: renders / 10 unchanged ticks."""
    r = rig(**_default())

    r.tick(TICKS)

    assert len(r.client.frames) == 1, "content changed on the board across unchanged ticks"
    assert r.pages.previews == 1, (
        f"{r.pages.previews} renders across {TICKS} unchanged ticks; "
        "the loop is still rendering every tick and diffing after"
    )


def test_unchanged_ticks_do_not_stop_fetching(rig):
    """The short-circuit skips the RENDER, never the freshness check.

    Skipping the fetch too would make the engine blind: nothing would ever
    observe that the plugin data moved, so the board would freeze on its
    first frame. The fingerprint is computed FROM the fetched context, so a
    fetch must still happen on every tick.
    """
    r = rig(**_default())

    r.tick(TICKS)

    assert r.registry.builds >= TICKS, (
        f"only {r.registry.builds} context builds across {TICKS} ticks — "
        "the short-circuit skipped the freshness check, not just the render"
    )


# --------------------------------------------------------------------------
# The safety: every input that moves the bytes must still force a render
# --------------------------------------------------------------------------


def test_changed_plugin_data_renders_and_sends(rig):
    """Non-vacuity: a short-circuit that always fired would fail here."""
    r = rig(**_default())
    r.tick(TICKS)
    assert len(r.client.frames) == 1

    r.registry.data["stub"]["value"] = "GOODBYE"
    r.tick()

    assert r.pages.previews == 2, "the changed plugin value never reached a render"
    assert len(r.client.frames) == 2, "the changed value never reached the board"
    assert r.runtime.last_active_page_content.startswith("GOODBYE")


def test_edited_page_renders_and_sends(rig):
    """A page edit moves ``updated_at`` and the template bytes."""
    r = rig(**_default())
    r.tick(TICKS)

    r.edit_page(template=["{{stub.value}} WORLD", "", "", "", "", ""])
    r.tick()

    assert r.pages.previews == 2
    assert len(r.client.frames) == 2
    assert r.runtime.last_active_page_content.startswith("HELLO WORLD")


def test_color_rule_change_renders_and_sends(rig):
    """Color rules live in config, not in the page or the plugin data.

    They are the input that proves the fingerprint needs ``config_generation``:
    nothing about the page or the fetched context moves when a user edits one,
    yet the rendered bytes gain a colour tile.
    """
    r = rig(**_default(data={"stub": {"value": "42", "temperature": "42"}}))
    r.tick(TICKS)
    baseline = r.runtime.last_active_page_content

    r.config.color_rules[("stub", "value")] = [{"condition": ">", "value": 0, "color": "red"}]
    r.config.config_generation += 1
    r.tick()

    assert r.pages.previews == 2, "a config write did not invalidate the render memo"
    assert r.runtime.last_active_page_content != baseline
    assert len(r.client.frames) == 2


def test_failed_send_re_renders_and_retries_next_tick(rig):
    """A send that never reached the board must be retried, not memoized away."""
    r = rig(**_default())
    r.client.fail = True

    r.tick(3)

    assert len(r.client.frames) == 3, (
        f"only {len(r.client.frames)} send attempts across 3 ticks after a failure — "
        "the short-circuit swallowed the retry"
    )
    assert r.pages.previews == 3


def test_throttled_send_re_renders_and_retries_next_tick(rig):
    """A throttled send reports success but never reached the board (#1794)."""

    class ThrottlingClient(RecordingClient):
        def render(self, board_array, **kwargs):
            self.frames.append([row[:] for row in board_array])
            self.last_send_throttled = True
            return True, False

    r = rig(**_default())
    r.client = ThrottlingClient()
    r.runtime.client = r.client

    r.tick(3)

    assert len(r.client.frames) == 3, (
        f"only {len(r.client.frames)} attempts across 3 ticks — a throttled send was memoized as delivered"
    )


def test_invalidate_board_content_forces_a_render(rig):
    """ "Resend to board" must repaint even when nothing changed (#1794)."""
    r = rig(**_default())
    r.tick(TICKS)
    assert len(r.client.frames) == 1

    r.service.invalidate_board_content(BOARD_ID)
    r.tick()

    assert r.pages.previews == 2
    assert len(r.client.frames) == 2


def test_silence_starting_on_the_clock_is_dispatched_after_short_circuited_ticks(rig):
    """The silence dispatch lives BELOW the render; skipping must not skip it.

    Silence turns on by the CLOCK crossing the window boundary — no config
    write, so no ``config_generation`` bump, and the page and plugin data are
    untouched. The render fingerprint is therefore byte-identical across the
    boundary: only the pass's explicit ``not silence_mode_active`` guard stops
    the memo from swallowing the board's entry into silence.
    """
    clock = FakeClock(datetime(2026, 7, 15, 21, 0, tzinfo=UTC))
    r = rig(
        clock=clock,
        **_default(
            silence={
                "enabled": True,
                "start_time": "22:00+00:00",
                "end_time": "06:00+00:00",
                "mode": "indicator",
                "page_id": None,
                "indicator_text": "SNOOZING",
                "indicator_position": "center",
                "by_board": {},
            }
        ),
    )
    r.tick(TICKS)
    assert len(r.client.frames) == 1
    assert r.pages.previews == 1, "the memo never armed, so this proves nothing about the guard"

    clock.advance(3600)  # 22:00 — inside the window, nothing else moved
    r.tick()

    assert len(r.client.frames) == 2, "entering silence did not reach the board"
    assert r.runtime.snoozing_message_sent is True


def test_formula_page_never_short_circuits(rig):
    """``{{= ... }}`` hides its variable owners, so the memo must not arm."""
    r = rig(
        **_default(
            template=["{{= stub.value }}", "", "", "", "", ""],
            data={"stub": {"value": "HELLO"}},
        )
    )

    r.tick(TICKS)

    assert r.pages.previews == TICKS, (
        "a formula page was short-circuited; its referenced plugins are not statically knowable"
    )


def test_direct_callers_without_a_pass_cache_never_short_circuit(rig):
    """MQTT / ``/refresh`` call the per-board path with ``contexts=None``."""
    r = rig(**_default())

    for _ in range(TICKS):
        r.service.check_and_send_for_board(BOARD_ID, r.runtime, is_primary=True, contexts=None, wait=True)
    assert r.service.wait_until_idle(timeout=10.0)

    assert r.pages.previews == TICKS


def test_short_circuit_is_thread_safe_against_a_concurrent_cache_clear(rig):
    """The memo carries its own validity proof, so a torn read cannot skip.

    Clearing the dedupe cache from another thread between the memo write and
    the next pass must make the memo stale rather than leave a fingerprint
    that matches a cache it no longer describes.
    """
    r = rig(**_default())
    r.tick()

    done = threading.Event()

    def _clear():
        r.runtime.last_active_page_content = None
        done.set()

    t = threading.Thread(target=_clear)
    t.start()
    done.wait(5)
    t.join(5)

    r.tick()
    assert r.pages.previews == 2
