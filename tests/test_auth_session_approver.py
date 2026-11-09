# ruff: noqa: F811 - pytest fixtures are imported from their home module
"""Who approved each TV, in the browser's Signed-in devices (web 07e).

``GET /auth/sessions`` (browser-only) gains ``approved_by`` on each TV that
signed in with a code: the approving session's id, kind and a label, "Maya's
iPhone" for a phone or "<Browser> on <OS>" for a browser ("a web browser"
when its user agent says neither). ``DELETE /auth/sessions/{phone}`` with
``include_approved=true`` also signs out the TVs that phone approved, through
the same revoke path. Phones still see no approver ids (H10b, Jev D14).
"""

import logging

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.auth import session_store
from tests.test_auth_phone_tvs import (  # noqa: F401 - fixtures
    ANDROID,
    GTV,
    PASSWORD,
    TV,
    approved_tv,
    auth,
    bearer_client,
    browser,
    phone,
    sign_in,
    tvs,
)

CHROME_MAC = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)


def browser_with(user_agent):
    client = TestClient(app, headers={"User-Agent": user_agent})
    assert client.post("/auth/login", json={"username": "admin", "password": PASSWORD}).status_code == 200
    context = client.get("/auth/sessions/context")
    client.headers.update({"Origin": "http://testserver", "X-CSRF-Token": context.json()["csrf_token"]})
    return client


def rows(client):
    response = client.get("/auth/sessions")
    assert response.status_code == 200, response.text
    return {row["id"]: row for row in response.json()["sessions"]}


def works(token):
    return bearer_client(token).get("/panels").status_code == 200


# ── the label ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("user_agent", "label"),
    [
        (CHROME_MAC, "Chrome on macOS"),
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
            "Edge on Windows",
        ),
        ("Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0", "Firefox on Linux"),
        (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/18.0 Safari/605.1.15",
            "Safari on macOS",
        ),
        (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/18.0 Mobile/15E148 Safari/604.1",
            "Safari on iOS",
        ),
        (
            "Mozilla/5.0 (iPad; CPU OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "CriOS/130.0.0.0 Mobile/15E148 Safari/604.1",
            "Chrome on iPadOS",
        ),
        (
            "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/130.0.0.0 Mobile Safari/537.36",
            "Chrome on Android",
        ),
        (
            "Mozilla/5.0 (Linux; Android 14; SM-S921B) AppleWebKit/537.36 (KHTML, like Gecko) "
            "SamsungBrowser/26.0 Chrome/122.0.0.0 Mobile Safari/537.36",
            "Samsung Internet on Android",
        ),
        (
            "Mozilla/5.0 (X11; CrOS x86_64 14541.0.0) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/130.0.0.0 Safari/537.36",
            "Chrome on ChromeOS",
        ),
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/130.0.0.0 Safari/537.36 OPR/115.0.0.0",
            "Opera on Windows",
        ),
        ("Mozilla/5.0 Test browser", "a web browser"),
        ("curl/8.7.1", "a web browser"),
        ("", "a web browser"),
    ],
)
def test_a_browser_approver_is_named_by_browser_and_os(user_agent, label):
    assert session_store.browser_label(user_agent) == label


# ── approved_by on GET /auth/sessions ───────────────────────────────────────


def test_a_tv_approved_by_a_phone_names_the_phone(auth, browser, phone):
    phone_client, phone_token = phone
    tv = approved_tv(auth, phone_client)

    row = rows(browser)[tv["session_id"]]

    assert row["approved_by"] == {
        "session_id": phone_token["session_id"],
        "kind": "mobile",
        "label": "Maya's iPhone",
        "signed_in": True,
    }


def test_a_tv_approved_in_a_browser_names_the_browser(auth):
    chrome = browser_with(CHROME_MAC)
    tv = approved_tv(auth, chrome)

    approver = rows(chrome)[tv["session_id"]]["approved_by"]

    assert (approver["kind"], approver["label"], approver["signed_in"]) == ("browser", "Chrome on macOS", True)


def test_an_unrecognised_browser_is_a_web_browser(auth, browser):
    tv = approved_tv(auth, browser)

    assert rows(browser)[tv["session_id"]]["approved_by"]["label"] == "a web browser"


def test_sessions_nobody_approved_have_no_approver(auth, browser, phone):
    sign_in(TV)  # a TV signed in with the password

    listed = rows(browser)

    assert len(listed) == 3
    assert all(row["approved_by"] is None for row in listed.values())


def test_a_signed_out_approver_is_still_named(auth, browser, phone):
    phone_client, phone_token = phone
    tv = approved_tv(auth, phone_client)
    assert browser.delete("/auth/sessions/" + phone_token["session_id"]).status_code == 200

    approver = rows(browser)[tv["session_id"]]["approved_by"]

    assert (approver["label"], approver["signed_in"]) == ("Maya's iPhone", False)


def test_a_phone_still_sees_no_approver_ids(auth, browser, phone):
    phone_client, _ = phone
    approved_tv(auth, phone_client)
    approved_tv(auth, browser, GTV)

    listed = tvs(phone_client)

    assert len(listed) == 2
    assert all("approved_by" not in row and "approver_session_id" not in row for row in listed)
    assert {row["approved_by_you"] for row in listed} == {True, False}
    assert phone_client.get("/auth/sessions").status_code in (401, 403)


# ── the cascade on DELETE /auth/sessions/{phone} ────────────────────────────


@pytest.fixture
def two_phones(auth, browser, phone):
    """Maya's iPhone approved two TVs, the Pixel one, the browser one."""
    maya, maya_token = phone
    pixel_token = sign_in(ANDROID)
    pixel = bearer_client(pixel_token["access_token"])
    return {
        "maya": maya_token,
        "pixel": pixel_token,
        "maya_tvs": [approved_tv(auth, maya), approved_tv(auth, maya, GTV)],
        "pixel_tv": approved_tv(auth, pixel),
        "browser_tv": approved_tv(auth, browser),
    }


def test_signing_out_a_phone_can_also_sign_out_the_tvs_it_approved(auth, browser, two_phones):
    response = browser.delete("/auth/sessions/" + two_phones["maya"]["session_id"], params={"include_approved": True})

    assert response.status_code == 200, response.text
    assert sorted(response.json()["also_signed_out"]) == sorted(tv["session_id"] for tv in two_phones["maya_tvs"])
    assert not works(two_phones["maya"]["access_token"])
    assert not any(works(tv["access_token"]) for tv in two_phones["maya_tvs"])
    assert works(two_phones["pixel_tv"]["access_token"]) and works(two_phones["browser_tv"]["access_token"])
    assert works(two_phones["pixel"]["access_token"])


def test_without_the_option_the_tvs_stay_signed_in(auth, browser, two_phones):
    response = browser.delete("/auth/sessions/" + two_phones["maya"]["session_id"])

    assert response.json()["also_signed_out"] == []
    assert not works(two_phones["maya"]["access_token"])
    assert all(works(tv["access_token"]) for tv in two_phones["maya_tvs"])


@pytest.mark.parametrize("target", ["browser_tv", "pixel_tv"])
def test_the_option_only_cascades_from_a_phone(auth, browser, two_phones, target):
    """Signing out a TV with the option signs out that TV, nothing more."""
    response = browser.delete("/auth/sessions/" + two_phones[target]["session_id"], params={"include_approved": True})

    assert response.json()["also_signed_out"] == []
    assert works(two_phones["maya"]["access_token"]) and works(two_phones["pixel"]["access_token"])
    assert all(works(tv["access_token"]) for tv in two_phones["maya_tvs"])


def test_signing_out_ones_own_browser_does_not_cascade(auth, browser, two_phones):
    current = browser.get("/auth/sessions").json()["current_session_id"]

    response = browser.delete("/auth/sessions/" + current, params={"include_approved": True})

    assert response.json()["also_signed_out"] == []
    assert works(two_phones["browser_tv"]["access_token"])


def test_the_cascade_skips_tvs_already_signed_out(auth, browser, two_phones):
    first, second = two_phones["maya_tvs"]
    assert browser.delete("/auth/sessions/" + first["session_id"]).status_code == 200

    response = browser.delete("/auth/sessions/" + two_phones["maya"]["session_id"], params={"include_approved": True})

    assert response.json()["also_signed_out"] == [second["session_id"]]


def test_the_cascade_uses_the_shared_revoke_path(auth, browser, two_phones, caplog):
    """Each TV is audited like any other sign-out, and its panel views go."""
    first, _ = two_phones["maya_tvs"]
    auth.sessions.record_panel_view(first["session_id"], "panel-1")
    caplog.set_level(logging.INFO, logger="src.auth.audit")

    browser.delete("/auth/sessions/" + two_phones["maya"]["session_id"], params={"include_approved": True})

    lines = [r.getMessage() for r in caplog.records if r.name == "src.auth.audit"]
    assert len(lines) == 3  # the phone, then its two TVs
    assert all(tv["session_id"] in "\n".join(lines) for tv in two_phones["maya_tvs"])
    assert first["session_id"] not in auth.sessions.panel_views("admin")


def test_the_cascade_needs_a_browser_mutation(auth, browser, two_phones):
    """No CSRF token, or a phone's Bearer: refused, and nothing is signed out."""
    path = "/auth/sessions/" + two_phones["maya"]["session_id"]
    no_csrf = TestClient(app, cookies=browser.cookies, headers={"Origin": "http://testserver"})
    phone = bearer_client(two_phones["pixel"]["access_token"])

    assert no_csrf.delete(path, params={"include_approved": True}).status_code == 403
    assert phone.delete(path, params={"include_approved": True}).status_code in (401, 403)
    assert works(two_phones["maya"]["access_token"])
    assert all(works(tv["access_token"]) for tv in two_phones["maya_tvs"])
