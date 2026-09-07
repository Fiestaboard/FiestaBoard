"""nginx must outwait the backend on the API proxy (issue #1886).

``src.main.SEND_WAIT_TIMEOUT`` is how long a ``wait=True`` send blocks for its
board job — 240s, sized in #1868 for a 120s transition ahead of us in the queue
plus 15s cloud frame pacing plus our own paced send. nginx's API proxy was
still on the stock ``proxy_read_timeout 60s``, so every send that legitimately
took longer than a minute returned 504 to the browser while the backend went on
working for up to four times as long: the UI reported failure for a send that
succeeded, and the "please wait, the service is starting" body replaced the
real JSON.

That drift is the bug, so this test pins the RELATIONSHIP rather than the
numbers. Raising SEND_WAIT_TIMEOUT without raising nginx fails here.
"""

import re
from pathlib import Path

import pytest

from src.main import SEND_WAIT_TIMEOUT

CONFIGS = ("nginx.conf", "nginx.https.conf", "nginx-dev.conf")
API_LOCATIONS = ("/api/mcp", "/api/")

REPO_ROOT = Path(__file__).resolve().parent.parent

_DURATION = re.compile(r"^(\d+(?:\.\d+)?)(ms|s|m|h)?$")
_UNIT_SECONDS = {None: 1.0, "ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}


def _seconds(value: str) -> float:
    """Parse an nginx time literal ("300s", "5m", "250ms") into seconds."""
    match = _DURATION.match(value)
    assert match, f"unparseable nginx duration: {value!r}"
    return float(match.group(1)) * _UNIT_SECONDS[match.group(2)]


def _location_body(text: str, location: str) -> str:
    """The brace-matched body of ``location <location> { ... }``."""
    opener = f"location {location} {{"
    start = text.index(opener) + len(opener)
    depth = 1
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start:index]
    raise AssertionError(f"unbalanced braces in `location {location}`")


def _directive(body: str, name: str) -> float:
    match = re.search(rf"^\s*{name}\s+(\S+?);", body, re.MULTILINE)
    assert match, f"`{name}` is not declared in this location block"
    return _seconds(match.group(1))


@pytest.mark.parametrize("config_name", CONFIGS)
@pytest.mark.parametrize("location", API_LOCATIONS)
@pytest.mark.parametrize("directive", ("proxy_read_timeout", "proxy_send_timeout"))
def test_api_proxy_outwaits_the_backend_send_budget(config_name: str, location: str, directive: str) -> None:
    body = _location_body((REPO_ROOT / config_name).read_text(encoding="utf-8"), location)
    value = _directive(body, directive)

    assert value > SEND_WAIT_TIMEOUT, (
        f"{config_name} `location {location}` has {directive} {value:g}s but "
        f"src.main.SEND_WAIT_TIMEOUT is {SEND_WAIT_TIMEOUT:g}s: a wait-mode send that runs "
        f"longer than {value:g}s returns 504 to the browser while the backend is still working. "
        "Raise the nginx timeout whenever SEND_WAIT_TIMEOUT rises."
    )
