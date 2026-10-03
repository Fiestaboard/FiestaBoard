"""Reading what a user pasted after a sign-in did not come back on its own."""

import pytest

from src.oauth.errors import PastedCodeRejected
from src.oauth.paste import PastedAuthorization, parse_pasted


def test_a_full_redirect_address_gives_code_and_state():
    parsed = parse_pasted("https://fiestaboard.app/auth/oauth/redirect?code=abc123&state=s.sig")
    assert parsed == PastedAuthorization(code="abc123", state="s.sig", error="", issued_client_id="")


def test_values_in_the_fragment_are_read_too():
    parsed = parse_pasted("https://example.com/cb#code=abc123&state=s.sig")
    assert (parsed.code, parsed.state) == ("abc123", "s.sig")


def test_the_query_wins_over_the_fragment():
    parsed = parse_pasted("https://example.com/cb?code=fromquery&state=q#code=fromfragment")
    assert parsed.code == "fromquery"


def test_surrounding_whitespace_is_ignored():
    assert parse_pasted("  \\nhttps://example.com/cb?code=abc123&state=s\\n ").code == "abc123"


def test_a_loopback_address_with_a_client_id_reports_it():
    parsed = parse_pasted("http://127.0.0.1:1455/auth/callback?code=abc123&state=s&client_id=oaiapp_test_1")
    assert parsed.issued_client_id == "oaiapp_test_1"


def test_a_provider_error_is_reported():
    parsed = parse_pasted("https://example.com/cb?error=access_denied&state=s")
    assert (parsed.error, parsed.code) == ("access_denied", "")


@pytest.mark.parametrize("code", ["abcd", "a1B2-c3_d4.e5~f6", "x" * 2048])
def test_a_bare_code_is_accepted(code):
    assert parse_pasted(code) == PastedAuthorization(code=code, state="", error="", issued_client_id="")


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "abc",
        "has space in it",
        "x" * 2049,
        "<script>",
        "https://example.com/cb",
        "https://example.com/cb?foo=1",
    ],
)
def test_anything_else_is_unreadable(text):
    with pytest.raises(PastedCodeRejected) as caught:
        parse_pasted(text)
    assert caught.value.reason == "unreadable"
