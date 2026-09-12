"""nginx must outwait the backend on the API proxy (issue #1886).

A ``wait``-mode send (``/refresh``, ``/force-refresh``, ``/pages/{id}/send``,
``PUT /settings/active-page``) runs the board send synchronously inside the
HTTP request, and that send may drive a transition animation: the runner in
``src/transitions/runner.py`` honors the manifest cap ``max_runtime_seconds``
(default 120s), and cloud note-array boards additionally pace every frame —
including the final snap-to-target — ``NOTE_ARRAY_MIN_SEND_INTERVAL`` (15s)
apart. Minute-plus sends are therefore routine, not pathological.

nginx's API proxy was on the stock ``proxy_read_timeout 60s`` /
``proxy_send_timeout 30s``, so any send that legitimately ran longer than a
minute returned 504 to the browser while the backend went on working for
up to twice as long: the UI reported failure for a send that succeeded, and
because /api 502/504s fall through to ``@api_starting``, the real JSON was
replaced by "Service is starting up".

That drift is the bug, so this test pins the RELATIONSHIP rather than the
numbers: raising the backend's send budget without raising nginx fails here.
(On the ``next`` rework branch the budget is ``src.main.SEND_WAIT_TIMEOUT`` =
240s; the 300s the configs carry already outwaits that too.)
"""

import re
from pathlib import Path

import pytest

from src.board_client import NOTE_ARRAY_MIN_SEND_INTERVAL
from src.plugins.manifest import MANIFEST_SCHEMA

# Worst-case wall clock for one in-request board send: a transition running to
# its default manifest cap, plus the paced final snap-to-target on a cloud
# note-array board. Derived from the real constants, not restated, so the
# assertion moves when the backend budget moves.
_TRANSITION_RUNTIME_CAP = float(
    MANIFEST_SCHEMA["properties"]["transition_settings"]["properties"]["max_runtime_seconds"]["default"]
)
BACKEND_SEND_BUDGET = _TRANSITION_RUNTIME_CAP + NOTE_ARRAY_MIN_SEND_INTERVAL

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

    assert value > BACKEND_SEND_BUDGET, (
        f"{config_name} `location {location}` has {directive} {value:g}s but a wait-mode "
        f"board send can legitimately run {BACKEND_SEND_BUDGET:g}s (transition "
        f"max_runtime_seconds default {_TRANSITION_RUNTIME_CAP:g}s + {NOTE_ARRAY_MIN_SEND_INTERVAL:g}s "
        f"cloud frame pacing for the final snap): the browser gets 504 while the backend is "
        "still working (issue #1886). Raise the nginx timeout whenever the backend send "
        "budget rises."
    )
