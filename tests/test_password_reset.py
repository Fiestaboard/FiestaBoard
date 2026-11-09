# ruff: noqa: F811 - pytest fixtures are imported from their home module
"""H17: the owner recovers a lost password, with no email (program/status/hub-H17.md).

Only someone who controls the container can start a reset: a CLI run inside
it (``python -m src.auth.password_reset``) mints a one-time, 15-minute code,
stored only as a digest. ``POST /auth/password-reset {code, new_password}``
(public: the owner has no session) consumes it once, sets the password and
signs out every browser, TV and phone. No route mints a code, no log carries
one, and every miss looks the same and counts toward the sign-in lockout.
"""

import logging
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.auth import routes as routes_module
from tests.test_auth_phone_tvs import (  # noqa: F401 - fixtures
    IOS,
    PASSWORD,
    TV,
    approved_tv,
    auth,
    bearer_client,
    browser,
    sign_in,
)

NEW_PASSWORD = "a-brand-new-password"


def _module():
    from src.auth import password_reset

    return password_reset


def mint(auth, capsys, *args):
    """Run the CLI against *auth*'s files; return (exit code, what it printed)."""
    code = _module().main(list(args), auth_file=auth._path)
    return code, capsys.readouterr().out


def minted_code(auth, capsys):
    status, out = mint(auth, capsys)
    assert status == 0, out
    return next(word for word in out.split() if word.startswith("fb_reset_"))


def reset(code, password=NEW_PASSWORD, client=None):
    return (client or TestClient(app)).post("/auth/password-reset", json={"code": code, "new_password": password})


def logs_in(password):
    response = TestClient(app).post("/auth/login", json={"username": "admin", "password": password})
    return response.status_code == 200


def rows(auth):
    with auth.sessions.transaction() as db:
        return [dict(row) for row in db.execute("SELECT * FROM password_resets").fetchall()]


@pytest.fixture(autouse=True)
def _fresh_lockout():
    routes_module._FAILED_ATTEMPTS.clear()
    yield
    routes_module._FAILED_ATTEMPTS.clear()


# ── minting, inside the container ───────────────────────────────────────────


def test_the_cli_prints_a_one_time_code_with_where_to_use_it(auth, capsys):
    status, out = mint(auth, capsys)

    assert status == 0
    code = next(word for word in out.split() if word.startswith("fb_reset_"))
    assert len(code) >= len("fb_reset_") + 43  # 256 bits, url-safe
    assert "/reset-password#code=" + code in out
    assert "15 minutes" in out


def test_only_the_codes_digest_is_stored(auth, capsys):
    from src.auth.session_store import digest_secret

    code = minted_code(auth, capsys)

    stored = rows(auth)
    assert [row["digest"] for row in stored] == [digest_secret(code)]
    assert all(code not in str(value) for row in stored for value in row.values())
    assert stored[0]["expires_ms"] - stored[0]["created_ms"] == 15 * 60 * 1000


def test_the_cli_never_writes_the_account_file(auth, capsys):
    before = auth._path.read_bytes()

    minted_code(auth, capsys)

    assert auth._path.read_bytes() == before


def test_no_log_record_carries_the_code(auth, capsys, caplog):
    caplog.set_level(logging.DEBUG)

    code = minted_code(auth, capsys)
    assert reset(code).status_code == 200

    assert all(code not in record.getMessage() for record in caplog.records)


def test_without_an_account_the_cli_stores_nothing(tmp_path, capsys):
    from src.auth import service as auth_module

    empty = auth_module.AuthService(tmp_path / "auth.json")

    status = _module().main([], auth_file=empty._path)

    assert status == 1 and "fb_reset_" not in capsys.readouterr().out
    with empty.sessions.transaction() as db:
        assert db.execute("SELECT COUNT(*) FROM password_resets").fetchone()[0] == 0


def test_the_cli_refuses_another_username(auth, capsys):
    status, out = mint(auth, capsys, "--username", "someone-else")

    assert status == 1 and "fb_reset_" not in out
    assert rows(auth) == []


# ── resetting ───────────────────────────────────────────────────────────────


def test_a_code_sets_the_new_password(auth, capsys):
    response = reset(minted_code(auth, capsys))

    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ok"}
    assert logs_in(NEW_PASSWORD) and not logs_in(PASSWORD)


def test_a_reset_signs_out_every_browser_tv_and_phone(auth, capsys, browser):
    phone = sign_in(IOS)
    tv = approved_tv(auth, browser, TV)

    assert reset(minted_code(auth, capsys)).status_code == 200

    assert browser.get("/auth/sessions").status_code == 401
    assert bearer_client(phone["access_token"]).get("/panels").status_code == 401
    assert bearer_client(tv["access_token"]).get("/panels").status_code == 401


def test_a_reset_does_not_sign_anyone_in(auth, capsys):
    response = reset(minted_code(auth, capsys))

    assert "set-cookie" not in {key.lower() for key in response.headers}


def test_a_reset_is_audited_without_the_code(auth, capsys, caplog):
    caplog.set_level(logging.INFO, logger="src.auth.audit")
    code = minted_code(auth, capsys)

    reset(code)

    lines = [r.getMessage() for r in caplog.records if r.name == "src.auth.audit"]
    assert lines == ["Password reset with a recovery code for admin"]


# ── every miss is the same, and counts ──────────────────────────────────────


def _misses(auth, capsys):
    """One response per kind of miss, each from a fresh lockout window."""
    responses = {}

    routes_module._FAILED_ATTEMPTS.clear()
    responses["wrong"] = reset("fb_reset_" + "x" * 43)

    used = minted_code(auth, capsys)
    assert reset(used, "first-new-password").status_code == 200
    routes_module._FAILED_ATTEMPTS.clear()
    responses["used"] = reset(used)

    older = minted_code(auth, capsys)
    minted_code(auth, capsys)
    routes_module._FAILED_ATTEMPTS.clear()
    responses["superseded"] = reset(older)

    expired = minted_code(auth, capsys)
    now = auth.sessions.clock_ms()
    auth.sessions.clock_ms = lambda: now + 15 * 60 * 1000 + 1
    routes_module._FAILED_ATTEMPTS.clear()
    responses["expired"] = reset(expired)
    return responses


def test_every_kind_of_miss_gets_the_same_answer(auth, capsys):
    responses = _misses(auth, capsys)

    answers = {(r.status_code, r.text, r.headers.get("content-type")) for r in responses.values()}
    assert len(answers) == 1
    status, body, _ = answers.pop()
    assert status == 400 and '"invalid_grant"' in body


def test_a_wrong_code_counts_toward_the_sign_in_lockout(auth, capsys):
    good = minted_code(auth, capsys)
    for _ in range(10):
        assert reset("fb_reset_" + "y" * 43).status_code == 400

    assert reset(good).status_code == 429
    assert logs_in(PASSWORD) is False  # the lockout is the shared one
    routes_module._FAILED_ATTEMPTS.clear()
    assert reset(good).status_code == 200


def test_a_code_minted_before_a_username_change_no_longer_works(auth, capsys):
    code = minted_code(auth, capsys)

    auth.change_username("admin", PASSWORD, "owner")

    assert rows(auth) == []
    assert reset(code).status_code == 400


def test_a_password_change_cancels_pending_codes(auth, capsys):
    code = minted_code(auth, capsys)

    auth.change_password("admin", PASSWORD, "changed-the-normal-way")

    assert rows(auth) == []
    assert reset(code).status_code == 400


# ── validation keeps the code ───────────────────────────────────────────────


def test_a_weak_password_is_refused_and_the_code_still_works(auth, capsys):
    code = minted_code(auth, capsys)

    assert reset(code, "short").status_code == 422
    assert reset(code).status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        {"code": "fb_reset_x"},
        {"new_password": NEW_PASSWORD},
        {"code": "fb_reset_x", "new_password": NEW_PASSWORD, "username": "admin"},
    ],
    ids=["no-password", "no-code", "extra-field"],
)
def test_a_malformed_request_is_refused(auth, body):
    assert TestClient(app).post("/auth/password-reset", json=body).status_code == 422


# ── no route can start a reset ──────────────────────────────────────────────


def test_the_only_reset_route_consumes_a_code():
    from tests.test_route_inventory import build_route_inventory

    routes = [(route["methods"], route["path"]) for route in build_route_inventory() if "reset" in route["path"]]

    assert routes == [(["POST"], "/auth/password-reset")]


def test_the_code_lives_in_a_fragment_never_a_query(auth, capsys):
    _, out = mint(auth, capsys)

    assert "?code=" not in out


def test_the_expiry_is_printed_as_an_instant(auth, capsys):
    _, out = mint(auth, capsys)
    stored = rows(auth)[0]

    expected = datetime.fromtimestamp(stored["expires_ms"] / 1000, UTC).replace(microsecond=0).isoformat()
    assert expected in out
