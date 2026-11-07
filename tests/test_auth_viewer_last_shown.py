"""Per-viewer "last shown": when each signed-in TV last fetched a panel frame.

The hub records it from the revocable TV credential on ``GET /panel/{id}/frame``
and reports it only on the browser-gated ``GET /auth/sessions`` list. The
public viewer routes return exactly what they returned before, and anonymous
``/p/`` viewers (and the web editor's own preview poll) record nothing.
"""

import sqlite3
import time
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.auth import service as auth_module
from src.auth.device_models import DeviceMetadata
from src.auth.device_service import DeviceService
from src.auth.session_store import PANEL_VIEW_PERSIST_MS

ORIGIN = "http://testserver"


class Clock:
    def __init__(self):
        # Whole seconds, so reported instants equal the recorded ones exactly.
        self.now = int(time.time()) * 1000

    def __call__(self) -> int:
        return self.now


@pytest.fixture
def hub(tmp_path, monkeypatch):
    auth = auth_module.AuthService(tmp_path / "auth.json")
    auth.create_initial_user("admin", "correct-password")
    auth.sessions.set_enrollment(True)
    clock = Clock()
    monkeypatch.setattr(auth.sessions, "clock_ms", clock)
    monkeypatch.setattr(auth_module, "_service", auth)
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "true")
    browser = TestClient(app)
    browser.cookies.set("fiestaboard_session", auth.authenticate("admin", "correct-password"))
    return auth, clock, browser


def sign_in_tv(auth, name="Living Room", client_id="fiestaboard-tvos"):
    token = DeviceService(auth).login(
        "admin", "correct-password", DeviceMetadata(client_id=client_id, device_name=name, app_version="1.0")
    )
    return TestClient(app, headers={"Authorization": "Bearer " + token.access_token}), token.session_id


def make_panel(browser, name="Living room TV"):
    response = browser.post("/panels", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def listed(browser):
    response = browser.get("/auth/sessions")
    assert response.status_code == 200, response.text
    return {s["id"]: s for s in response.json()["sessions"]}


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms // 1000, UTC).isoformat()


def stored_rows(auth):
    with sqlite3.connect(auth.sessions.path) as db:
        return db.execute("SELECT session_id, panel_id, last_shown_ms FROM panel_views ORDER BY panel_id").fetchall()


# --- recording and reporting ------------------------------------------------


def test_tv_frame_fetch_is_reported_on_the_sessions_list(hub):
    auth, clock, browser = hub
    panel = make_panel(browser)
    tv, session_id = sign_in_tv(auth)
    assert tv.get(f"/panel/{panel['id']}/frame").status_code == 200

    row = listed(browser)[session_id]
    assert row["device_name"] == "Living Room"
    assert row["client_id"] == "fiestaboard-tvos"
    assert row["kind"] == "tv"
    assert row["last_shown_at"] == iso(clock.now)
    assert row["shown_panels"] == [{"panel_id": panel["id"], "last_shown_at": iso(clock.now)}]


def test_sessions_that_never_showed_a_panel_report_nothing(hub):
    auth, _, browser = hub
    _, session_id = sign_in_tv(auth)
    rows = listed(browser)
    assert rows[session_id]["last_shown_at"] is None
    assert rows[session_id]["shown_panels"] == []
    browser_row = next(r for r in rows.values() if r["kind"] != "tv")
    assert browser_row["last_shown_at"] is None
    assert browser_row["shown_panels"] == []


def test_short_code_fetch_records_the_canonical_panel_id(hub):
    auth, _, browser = hub
    panel = make_panel(browser)
    tv, session_id = sign_in_tv(auth)
    assert tv.get(f"/panel/{panel['short_code']}/frame").status_code == 200
    assert listed(browser)[session_id]["shown_panels"][0]["panel_id"] == panel["id"]


def test_config_poll_alone_is_not_a_frame_shown(hub):
    auth, _, browser = hub
    panel = make_panel(browser)
    tv, session_id = sign_in_tv(auth)
    assert tv.get(f"/panel/{panel['id']}").status_code == 200
    assert listed(browser)[session_id]["shown_panels"] == []


def test_unknown_panel_records_nothing(hub):
    auth, _, _ = hub
    tv, _ = sign_in_tv(auth)
    assert tv.get("/panel/no-such-panel/frame").status_code == 404
    assert stored_rows(auth) == []


def test_anonymous_and_browser_frame_fetches_record_nothing(hub):
    auth, _, browser = hub
    panel = make_panel(browser)
    assert TestClient(app).get(f"/panel/{panel['id']}/frame").status_code == 200
    # The web editor's own TV preview polls the same route with the cookie.
    assert browser.get(f"/panel/{panel['id']}/frame").status_code == 200
    assert stored_rows(auth) == []


# --- throttling --------------------------------------------------------------


def test_frame_polls_persist_at_most_once_a_minute(hub, monkeypatch):
    auth, clock, browser = hub
    panel = make_panel(browser)
    tv, session_id = sign_in_tv(auth)
    writes, records = [], []
    original = auth.sessions._write_panel_view
    record = auth.sessions.record_panel_view
    monkeypatch.setattr(auth.sessions, "_write_panel_view", lambda *a: writes.append(a) or original(*a))
    # The route checks the throttle in memory first, so a throttled poll
    # does not even take a threadpool hop into the store.
    monkeypatch.setattr(auth.sessions, "record_panel_view", lambda *a: records.append(a) or record(*a))

    first = clock.now
    # A 2 s poll for just under a minute: one write, from the first poll.
    for _ in range(30):
        assert tv.get(f"/panel/{panel['id']}/frame").status_code == 200
        clock.now += 2_000
    assert clock.now - 2_000 - first < PANEL_VIEW_PERSIST_MS
    assert len(writes) == 1
    assert len(records) == 1
    assert listed(browser)[session_id]["last_shown_at"] == iso(first)

    clock.now = first + PANEL_VIEW_PERSIST_MS
    assert tv.get(f"/panel/{panel['id']}/frame").status_code == 200
    assert len(writes) == 2
    assert listed(browser)[session_id]["last_shown_at"] == iso(clock.now)


def test_throttled_record_opens_no_transaction(hub, monkeypatch):
    auth, clock, _ = hub
    store = auth.sessions
    _, session_id = sign_in_tv(auth)
    assert store.record_panel_view(session_id, "p1") is True

    opened = []
    original = store.transaction
    monkeypatch.setattr(store, "transaction", lambda: opened.append(1) or original())
    clock.now += PANEL_VIEW_PERSIST_MS - 1
    assert store.record_panel_view(session_id, "p1") is False
    assert opened == []
    clock.now += 1
    assert store.record_panel_view(session_id, "p1") is True
    assert opened == [1]


def test_throttle_is_per_viewer_and_per_panel(hub):
    auth, _, _ = hub
    store = auth.sessions
    _, a = sign_in_tv(auth, "Living Room")
    _, b = sign_in_tv(auth, "Guest Room")
    assert store.record_panel_view(a, "p1") is True
    assert store.record_panel_view(b, "p1") is True
    assert store.record_panel_view(a, "p2") is True
    assert store.record_panel_view(a, "p1") is False


def test_failed_write_is_retried_on_the_next_poll(hub, monkeypatch):
    auth, _, _ = hub
    store = auth.sessions
    _, session_id = sign_in_tv(auth)

    def broken(*_args):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(store, "_write_panel_view", broken)
    with pytest.raises(sqlite3.OperationalError):
        store.record_panel_view(session_id, "p1")
    monkeypatch.undo()
    assert store.record_panel_view(session_id, "p1") is True


def test_storage_failure_never_breaks_the_frame(hub, monkeypatch):
    auth, _, browser = hub
    panel = make_panel(browser)
    tv, _ = sign_in_tv(auth)

    def broken(*_args):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(auth.sessions, "record_panel_view", broken)
    assert tv.get(f"/panel/{panel['id']}/frame").status_code == 200


def test_last_shown_survives_restart(hub):
    auth, clock, browser = hub
    panel = make_panel(browser)
    tv, session_id = sign_in_tv(auth)
    tv.get(f"/panel/{panel['id']}/frame")
    restarted = auth_module.AuthService(auth._path)
    views = restarted.sessions.panel_views("admin")
    assert views[session_id] == [(panel["id"], clock.now)]


def test_view_for_an_unknown_or_revoked_session_is_not_stored(hub):
    auth, _, _ = hub
    store = auth.sessions
    _, session_id = sign_in_tv(auth)
    store.record_panel_view("not-a-session", "p1")
    store.revoke_session("admin", session_id)
    # A poll already past the middleware when the TV was revoked.
    store.record_panel_view(session_id, "p1")
    assert stored_rows(auth) == []


def test_views_left_by_an_older_build_revoking_are_hidden(hub):
    """A downgraded hub revokes by flagging the row and leaves views behind."""
    auth, _, _ = hub
    store = auth.sessions
    _, session_id = sign_in_tv(auth)
    store.record_panel_view(session_id, "p1")
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE sessions SET revoked_ms=1 WHERE id=?", (session_id,))
    assert stored_rows(auth)
    assert store.panel_views("admin") == {}


# --- multiple viewers --------------------------------------------------------


def test_two_tvs_on_one_panel_are_listed_separately(hub):
    auth, clock, browser = hub
    panel = make_panel(browser)
    living, living_id = sign_in_tv(auth, "Living Room", "fiestaboard-tvos")
    guest, guest_id = sign_in_tv(auth, "Guest Room", "fiestaboard-androidtv")
    living.get(f"/panel/{panel['id']}/frame")
    living_at = clock.now
    clock.now += 3 * 60_000
    guest.get(f"/panel/{panel['id']}/frame")

    rows = listed(browser)
    viewers = sorted(
        (r["device_name"], r["client_id"], r["shown_panels"])
        for r in rows.values()
        if any(p["panel_id"] == panel["id"] for p in r["shown_panels"])
    )
    assert viewers == [
        ("Guest Room", "fiestaboard-androidtv", [{"panel_id": panel["id"], "last_shown_at": iso(clock.now)}]),
        ("Living Room", "fiestaboard-tvos", [{"panel_id": panel["id"], "last_shown_at": iso(living_at)}]),
    ]
    assert rows[living_id]["last_shown_at"] == iso(living_at)
    assert rows[guest_id]["last_shown_at"] == iso(clock.now)


def test_one_tv_on_two_panels_lists_newest_first(hub):
    auth, clock, browser = hub
    kitchen = make_panel(browser, "Kitchen TV")
    den = make_panel(browser, "Den TV")
    tv, session_id = sign_in_tv(auth)
    tv.get(f"/panel/{kitchen['id']}/frame")
    kitchen_at = clock.now
    clock.now += 5_000
    tv.get(f"/panel/{den['id']}/frame")

    row = listed(browser)[session_id]
    assert row["shown_panels"] == [
        {"panel_id": den["id"], "last_shown_at": iso(clock.now)},
        {"panel_id": kitchen["id"], "last_shown_at": iso(kitchen_at)},
    ]
    assert row["last_shown_at"] == iso(clock.now)


def test_deleted_panel_drops_out_of_the_list(hub):
    auth, _, browser = hub
    panel = make_panel(browser)
    tv, session_id = sign_in_tv(auth)
    tv.get(f"/panel/{panel['id']}/frame")
    assert browser.delete(f"/panels/{panel['id']}").status_code == 200
    row = listed(browser)[session_id]
    assert row["shown_panels"] == []
    assert row["last_shown_at"] is None


# --- revocation --------------------------------------------------------------


def test_revoking_a_tv_removes_it_as_a_viewer(hub):
    auth, _, browser = hub
    panel = make_panel(browser)
    living, living_id = sign_in_tv(auth, "Living Room")
    guest, guest_id = sign_in_tv(auth, "Guest Room")
    living.get(f"/panel/{panel['id']}/frame")
    guest.get(f"/panel/{panel['id']}/frame")

    csrf = browser.get("/auth/sessions/context").json()["csrf_token"]
    response = browser.delete(f"/auth/sessions/{living_id}", headers={"Origin": ORIGIN, "X-CSRF-Token": csrf})
    assert response.status_code == 200

    rows = listed(browser)
    assert living_id not in rows
    assert rows[guest_id]["shown_panels"][0]["panel_id"] == panel["id"]
    assert [r[0] for r in stored_rows(auth)] == [guest_id]
    # The revoked TV can no longer fetch, so it can never reappear.
    assert living.get(f"/panel/{panel['id']}/frame").status_code == 401
    assert [r[0] for r in stored_rows(auth)] == [guest_id]


def test_tv_signing_itself_out_removes_its_views(hub):
    auth, _, browser = hub
    panel = make_panel(browser)
    tv, _ = sign_in_tv(auth)
    tv.get(f"/panel/{panel['id']}/frame")
    assert tv.delete("/auth/device/session").status_code == 200
    assert stored_rows(auth) == []


def test_revoke_others_removes_every_tv_view(hub):
    auth, _, browser = hub
    panel = make_panel(browser)
    for name in ("Living Room", "Guest Room"):
        tv, _ = sign_in_tv(auth, name)
        tv.get(f"/panel/{panel['id']}/frame")
    assert len(stored_rows(auth)) == 2
    csrf = browser.get("/auth/sessions/context").json()["csrf_token"]
    response = browser.post(
        "/auth/sessions/revoke",
        json={"include_current": False},
        headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    assert stored_rows(auth) == []
    assert all(r["shown_panels"] == [] for r in listed(browser).values())


def test_sign_out_everywhere_hides_old_views(hub):
    auth, _, browser = hub
    panel = make_panel(browser)
    tv, session_id = sign_in_tv(auth)
    tv.get(f"/panel/{panel['id']}/frame")
    auth.invalidate_all_sessions("admin")
    fresh = TestClient(app)
    fresh.cookies.set("fiestaboard_session", auth.authenticate("admin", "correct-password"))
    assert session_id not in listed(fresh)
    assert auth.sessions.panel_views("admin").get(session_id) is None


# --- auth boundary -----------------------------------------------------------


def test_public_viewer_routes_carry_no_viewer_data(hub):
    auth, _, browser = hub
    panel = make_panel(browser)
    anonymous = TestClient(app)
    before_config = anonymous.get(f"/panel/{panel['id']}").json()
    before_frame = anonymous.get(f"/panel/{panel['id']}/frame").json()
    tv, _ = sign_in_tv(auth)
    tv.get(f"/panel/{panel['id']}/frame")
    assert stored_rows(auth)

    for client in (anonymous, tv):
        config = client.get(f"/panel/{panel['id']}").json()
        frame = client.get(f"/panel/{panel['id']}/frame").json()
        assert config == before_config
        assert frame == before_frame
        assert "Living Room" not in repr(config) + repr(frame)


def test_panels_list_carries_no_viewer_data(hub):
    auth, _, browser = hub
    panel = make_panel(browser)
    before = browser.get("/panels").json()
    tv, _ = sign_in_tv(auth)
    tv.get(f"/panel/{panel['id']}/frame")
    assert browser.get("/panels").json() == before
    assert tv.get("/panels").json() == before


def test_sessions_list_refuses_tv_and_anonymous_callers(hub):
    auth, _, browser = hub
    panel = make_panel(browser)
    tv, _ = sign_in_tv(auth)
    tv.get(f"/panel/{panel['id']}/frame")
    assert tv.get("/auth/sessions").status_code == 403
    assert TestClient(app).get("/auth/sessions").status_code == 401
