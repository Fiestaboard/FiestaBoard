"""State-machine races use real SQLite transactions and controlled time."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from src.auth.device_models import AuthFlowError, DeviceMetadata
from src.auth.device_service import DeviceService
from src.auth.service import AuthService


@pytest.fixture
def flow(tmp_path, monkeypatch):
    auth = AuthService(tmp_path / "auth.json")
    auth.create_initial_user("admin", "correct-password")
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "true")
    auth.sessions.set_enrollment(True)
    token = auth.authenticate("admin", "correct-password")
    browser = auth.resolve_browser_session(token)
    clock = [auth.sessions.clock_ms() + 100]
    monkeypatch.setattr(auth.sessions, "clock_ms", lambda: clock[0])
    return DeviceService(auth), browser, clock


def challenge(service):
    return service.authorize(
        DeviceMetadata(client_id="fiestaboard-tvos", device_name="TV", app_version="1"), "127.0.0.1"
    )


def error_name(call):
    try:
        call()
    except AuthFlowError as exc:
        return exc.error
    pytest.fail("Expected the grant to be rejected")


def test_expiry_includes_exact_deadline(flow):
    service, browser, clock = flow
    grant = challenge(service)
    service.decide(grant.user_code, browser, True)
    clock[0] += 600_000
    assert error_name(lambda: service.exchange(grant.device_code, "fiestaboard-tvos")) == "expired_token"


def test_slow_down_persists_new_interval(flow):
    service, _, clock = flow
    grant = challenge(service)

    def poll():
        return service.exchange(grant.device_code, "fiestaboard-tvos")

    assert error_name(poll) == "authorization_pending"
    assert error_name(poll) == "slow_down"
    clock[0] += 10_000
    assert error_name(poll) == "authorization_pending"
    clock[0] += 5000
    assert error_name(poll) == "slow_down"


def test_concurrent_redemption_has_one_winner(flow):
    service, browser, _ = flow
    grant = challenge(service)
    service.decide(grant.user_code, browser, True)

    def redeem(_):
        try:
            return service.exchange(grant.device_code, "fiestaboard-tvos").access_token
        except AuthFlowError as exc:
            return exc.error

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(redeem, range(4)))
    assert sum(value.startswith("fb_tv_") for value in results) == 1
    assert results.count("invalid_grant") == 3


@pytest.mark.parametrize("action", ["logout", "password", "username", "disable"])
def test_approval_does_not_survive_account_or_browser_invalidation(flow, action):
    service, browser, _ = flow
    grant = challenge(service)
    service.decide(grant.user_code, browser, True)
    if action == "logout":
        service.auth.sessions.revoke_session("admin", browser.id)
    elif action == "password":
        service.auth.change_password("admin", "correct-password", "a-new-password")
    elif action == "username":
        service.auth.change_username("admin", "correct-password", "newadmin")
    else:
        service.auth.disable_auth_for_user("admin", "correct-password")
    assert error_name(lambda: service.exchange(grant.device_code, "fiestaboard-tvos")) in (
        "invalid_grant",
        "setup_required",
    )


def test_wrong_client_cannot_spend_or_cancel_another_valid_exchange(flow):
    service, browser, _ = flow
    grant = challenge(service)
    service.decide(grant.user_code, browser, True)
    assert error_name(lambda: service.exchange(grant.device_code, "fiestaboard-androidtv")) == "invalid_grant"
    assert service.exchange(grant.device_code, "fiestaboard-tvos").access_token.startswith("fb_tv_")


def test_cancel_denial_and_reapproval_are_terminal(flow):
    service, browser, _ = flow
    grant = challenge(service)
    service.decide(grant.user_code, browser, False)
    assert error_name(lambda: service.exchange(grant.device_code, "fiestaboard-tvos")) == "access_denied"
    assert error_name(lambda: service.decide(grant.user_code, browser, True)) == "invalid_grant"
    other = challenge(service)
    service.cancel(other.device_code)
    service.cancel(other.device_code)
    assert error_name(lambda: service.exchange(other.device_code, "fiestaboard-tvos")) == "invalid_grant"


def test_rate_limits_survive_service_recreation(flow):
    service, _, clock = flow
    for _ in range(5):
        challenge(service)
    assert error_name(lambda: challenge(DeviceService(service.auth))) == "rate_limited"
    clock[0] += 60_001
    assert challenge(service).user_code


def test_code_collision_retries_instead_of_overwriting(flow, monkeypatch):
    from src.auth import device_service

    service, _, _ = flow
    values = iter("BBBBBBBB" + "BBBBBBBB" + "CCCCCCCC")
    monkeypatch.setattr(device_service.secrets, "choice", lambda alphabet: next(values))
    first, second = challenge(service), challenge(service)
    assert first.user_code == "BBBB-BBBB" and second.user_code == "CCCC-CCCC"
    assert service.inspect(first.user_code).device_name == "TV"


def test_token_has_fixed_expiry_and_account_rotation_invalidates(flow):
    service, _, clock = flow
    token = service.login(
        "admin",
        "correct-password",
        DeviceMetadata(client_id="fiestaboard-androidtv", device_name="TV", app_version="1"),
    )
    assert service.authenticate_tv(token.access_token) is not None
    clock[0] += 31536000 * 1000
    assert service.authenticate_tv(token.access_token) is None


def test_database_contains_no_private_device_codes(flow):
    service, _, _ = flow
    grant = challenge(service)
    with service.store.transaction() as db:
        stored = repr(db.execute("SELECT * FROM challenges").fetchall())
        row = dict(db.execute("SELECT * FROM challenges").fetchone())
    assert grant.device_code not in stored and grant.user_code not in stored
    assert grant.device_code not in repr(row)
