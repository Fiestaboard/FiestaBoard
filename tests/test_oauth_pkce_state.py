"""PKCE and signed-state primitives for the OAuth relay flow.

These are the two things standing between a relayed authorization code and a
token: the verifier that never leaves the board, and the state that proves a
callback belongs to a flow this board started.
"""

import base64
import hashlib
import json
import re
import stat

import pytest

from src.oauth import pkce
from src.oauth.errors import InvalidState
from src.oauth.state import STATE_TTL_SECONDS, StatePayload, StateSigner, load_state_key

KEY = b"k" * 32
NOW = 1_800_000_000
PAYLOAD = StatePayload(
    nonce="nonce-1",
    connection_id="music:kitchen",
    expires_at=NOW + STATE_TTL_SECONDS,
    board_url="http://192.168.1.50:4420",
)


@pytest.fixture
def signer():
    return StateSigner(KEY)


# ── PKCE ────────────────────────────────────────────────────────────────────


def test_verifier_uses_only_the_unreserved_characters_rfc7636_allows():
    assert re.fullmatch(r"[A-Za-z0-9\-._~]{43,128}", pkce.generate_verifier())


def test_each_verifier_is_different():
    assert len({pkce.generate_verifier() for _ in range(50)}) == 50


def test_challenge_matches_the_rfc7636_appendix_b_vector():
    # RFC 7636 Appendix B: the worked example every implementation must reproduce.
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert pkce.challenge_for(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_challenge_is_unpadded_base64url_of_the_sha256():
    verifier = pkce.generate_verifier()
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert pkce.challenge_for(verifier) == expected
    assert "=" not in pkce.challenge_for(verifier)


# ── State: round trip ───────────────────────────────────────────────────────


def test_a_signed_state_verifies_to_the_payload_it_was_made_from(signer):
    assert signer.verify(signer.sign(PAYLOAD), NOW) == PAYLOAD


def test_the_board_address_is_readable_from_the_first_segment_without_the_key(signer):
    """The relay page has no key: it reads the address straight out of the payload."""
    payload = signer.sign(PAYLOAD).split(".")[0]
    body = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    assert body["b"] == "http://192.168.1.50:4420"


def test_state_is_url_safe(signer):
    assert re.fullmatch(r"[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+", signer.sign(PAYLOAD))


# ── State: rejections ───────────────────────────────────────────────────────


@pytest.mark.parametrize("state", [None, "", "no-separator", ".signature-only", "payload-only."])
def test_unsigned_or_empty_state_is_rejected(signer, state):
    with pytest.raises(InvalidState) as excinfo:
        signer.verify(state, NOW)
    assert excinfo.value.reason == "invalid_state"


def test_state_signed_with_another_key_is_rejected(signer):
    forged = StateSigner(b"x" * 32).sign(PAYLOAD)
    with pytest.raises(InvalidState) as excinfo:
        signer.verify(forged, NOW)
    assert excinfo.value.reason == "invalid_state"


def test_a_payload_swapped_under_a_valid_signature_is_rejected(signer):
    """The attack the signature exists for: keep the signature, change who it is for."""
    _, _, signature = signer.sign(PAYLOAD).partition(".")
    body = json.dumps({"n": "nonce-1", "c": "someone_else", "e": NOW + STATE_TTL_SECONDS}, separators=(",", ":"))
    swapped = base64.urlsafe_b64encode(body.encode()).rstrip(b"=").decode()
    with pytest.raises(InvalidState):
        signer.verify(f"{swapped}.{signature}", NOW)


def test_a_single_flipped_signature_character_is_rejected(signer):
    state = signer.sign(PAYLOAD)
    flipped = state[:-1] + ("A" if state[-1] != "A" else "B")
    with pytest.raises(InvalidState):
        signer.verify(flipped, NOW)


def test_state_is_rejected_from_the_second_it_expires(signer):
    state = signer.sign(PAYLOAD)
    assert signer.verify(state, PAYLOAD.expires_at - 1) == PAYLOAD
    with pytest.raises(InvalidState) as excinfo:
        signer.verify(state, PAYLOAD.expires_at)
    assert excinfo.value.reason == "expired"


def test_a_correctly_signed_payload_that_is_not_json_is_rejected(signer):
    encoded = base64.urlsafe_b64encode(b"not json").rstrip(b"=").decode()
    with pytest.raises(InvalidState) as excinfo:
        signer.verify(f"{encoded}.{signer._signature(encoded)}", NOW)
    assert excinfo.value.reason == "invalid_state"


def test_an_oversized_state_is_rejected_before_any_work(signer):
    with pytest.raises(InvalidState):
        signer.verify("a" * 5000 + ".b", NOW)


def test_an_empty_key_is_refused():
    with pytest.raises(ValueError):
        StateSigner(b"")


# ── State key file ──────────────────────────────────────────────────────────


def test_state_key_is_created_once_and_reused(tmp_path):
    first = load_state_key(tmp_path)
    assert len(first) == 32
    assert load_state_key(tmp_path) == first


def test_state_key_file_is_owner_only(tmp_path):
    load_state_key(tmp_path)
    mode = stat.S_IMODE((tmp_path / ".oauth_state_key").stat().st_mode)
    assert mode == 0o600


def test_state_key_is_not_the_session_key(tmp_path):
    """Neither key may be able to mint the other's tokens."""
    load_state_key(tmp_path)
    assert not (tmp_path / ".session_key").exists()
